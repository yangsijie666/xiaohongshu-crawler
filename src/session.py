"""
MCP 服务级浏览器会话管理模块

职责：
  - 管理 Playwright 浏览器实例的服务级生命周期（长驻进程，区别于单次 async with）
  - 通过 asyncio.Lock 序列化所有浏览器操作，防止并发竞争
  - 提供登录态检查接口，供 MCP 工具调用
  - 浏览器健康检查 + 崩溃自动恢复（Phase D）
  - 操作中登录态失效检测（Phase D）
  - 统一结构化错误格式（Phase D）

与 BrowserManager 的区别：
  - BrowserManager：单次采集的 async with 上下文管理器
  - CrawlerSession：MCP 进程生命周期内持续运行的服务对象，
    通过 start()/stop() 手动管理生命周期

用法：
    session = CrawlerSession(headless=True)
    await session.start()
    result = await session.check_login_status()
    async with session.browser_lock() as bm:
        page = await bm.new_page()
        # ... 采集操作
    await session.stop()
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Optional

import src.note
import src.search
from src.auth import is_logged_in
from src.browser import BrowserManager
from src.errors import (
    browser_crashed_error,
    browser_not_running_error,
    crawl_failed_error,
    login_expired_error,
)
from src.storage import Storage

logger = logging.getLogger(__name__)

# crawl_keyword 工具使用的默认存储配置
_DEFAULT_STORAGE_CONFIG: dict = {
    "output_dir": "data",
    "save_raw_json": True,
    "save_xlsx": True,
}

# 采集完整流程的 max_notes 上限（避免单次任务耗时过长）
_MAX_NOTES_LIMIT = 20


def _extract_keyword_from_stem(stem: str) -> str:
    """从文件名（不含扩展名）提取关键词。

    文件名格式：[notes_]{keyword}_{YYYYMMDD}_{HHMMSS}
    例如：Python教程_20240315_143022  →  Python教程
          notes_小红书技巧_20240315_143022  →  小红书技巧

    Args:
        stem: 文件名（不含扩展名）

    Returns:
        提取到的关键词字符串
    """
    # 去掉 notes_ 前缀（笔记详情文件的命名约定）
    if stem.startswith("notes_"):
        stem = stem[6:]

    # 时间戳由两段组成：{YYYYMMDD}_{HHMMSS}，占最后两个 "_" 分隔块
    parts = stem.rsplit("_", 2)
    if len(parts) >= 3:
        return parts[0]
    return stem


class CrawlerSession:
    """服务级浏览器会话，供 MCP 服务进程长驻使用。

    设计约束：
      - 同一时刻只有一个 CrawlerSession 实例应处于运行状态（调用方负责保证）
      - 所有浏览器操作必须通过 browser_lock() 上下文管理器串行执行
      - MCP stdio 模式下默认 headless=True，节省资源
      - 浏览器崩溃时自动尝试恢复一次（Phase D）
      - 操作失败时检测登录态，返回精确错误码（Phase D）
    """

    def __init__(self, headless: bool = True) -> None:
        """初始化会话（不启动浏览器）。

        Args:
            headless: 是否无头模式。MCP 服务默认 True；调试时可设为 False。
        """
        self._headless = headless
        self._bm: Optional[BrowserManager] = None
        self._exit_stack: Optional[contextlib.AsyncExitStack] = None
        self._running: bool = False
        self._lock = asyncio.Lock()

    def is_running(self) -> bool:
        """返回浏览器是否已成功启动并运行中。"""
        return self._running

    async def start(self) -> None:
        """启动浏览器（幂等：已在运行则直接返回）。

        使用 AsyncExitStack 管理 BrowserManager 生命周期：
          - 若 BrowserManager.__aenter__ 抛出异常，ExitStack 自动清理已注册资源
          - self._exit_stack / self._bm 仅在启动成功后赋值，确保一致性

        Raises:
            Exception: 浏览器启动失败时透传异常
        """
        if self._running:
            logger.debug("浏览器会话已在运行，跳过重复启动")
            return

        logger.info("启动 MCP 浏览器会话（headless=%s）", self._headless)
        exit_stack = contextlib.AsyncExitStack()
        # enter_async_context 内部调用 __aenter__，失败时 exit_stack 自动清理
        bm = await exit_stack.enter_async_context(BrowserManager(headless=self._headless))
        # 全部成功后才赋值，确保 stop() 始终处理完整状态
        self._exit_stack = exit_stack
        self._bm = bm
        self._running = True
        logger.info("MCP 浏览器会话启动成功")

    async def stop(self) -> None:
        """关闭浏览器并释放所有资源（幂等：未运行时安全调用）。"""
        if self._exit_stack is not None:
            logger.info("关闭 MCP 浏览器会话")
            await self._exit_stack.aclose()  # 调用已注册的 __aexit__(None, None, None)
            self._exit_stack = None
            self._bm = None
        self._running = False
        logger.info("MCP 浏览器会话已关闭")

    # ============================================================
    # Phase D: 健康检查与自动恢复
    # ============================================================

    async def _is_browser_healthy(self) -> bool:
        """检查浏览器是否仍然存活且可用。

        通过 Playwright context.browser.is_connected() 判断浏览器进程是否正常。

        Returns:
            True 表示浏览器健康可用，False 表示不可用
        """
        if self._bm is None:
            return False
        try:
            ctx = self._bm.context
            if ctx is None:
                return False
            return ctx.browser.is_connected()
        except Exception:
            return False

    async def _ensure_browser(self) -> Optional[BrowserManager]:
        """确保浏览器可用，崩溃时尝试自动恢复。

        检查浏览器健康状态，不健康时执行一次 stop → start 恢复流程。

        Returns:
            BrowserManager 实例（可用时），或 None（恢复失败）
        """
        if not self._running:
            return None

        if await self._is_browser_healthy():
            return self._bm

        # 浏览器不健康，尝试恢复
        logger.warning("浏览器健康检查失败，尝试自动恢复...")
        await self.stop()
        try:
            await self.start()
            logger.info("浏览器自动恢复成功")
            return self._bm
        except Exception as e:
            logger.error("浏览器自动恢复失败：%s", e)
            return None

    # ============================================================
    # Phase D: 登录态失效检测
    # ============================================================

    async def _check_login_in_lock(self) -> bool:
        """在已持有锁的情况下检测登录态（内部方法）。

        创建临时页面执行登录态检查，确保页面在检查后关闭。

        Returns:
            True 表示已登录，False 表示未登录或检查失败
        """
        if self._bm is None:
            return False
        try:
            page = await self._bm.new_page()
            try:
                return await is_logged_in(page)
            finally:
                await page.close()
        except Exception as e:
            logger.warning("锁内登录态检测异常：%s", e)
            return False

    @asynccontextmanager
    async def browser_lock(self) -> AsyncGenerator[Optional[BrowserManager], None]:
        """获取浏览器独占锁，确保操作串行执行。

        用法：
            async with session.browser_lock() as bm:
                page = await bm.new_page()
                # ... 独占操作

        Yields:
            BrowserManager 实例（已启动时），或 None（未启动时）
        """
        async with self._lock:
            yield self._bm

    async def search_notes(self, keyword: str, max_count: int = 20) -> dict:
        """按关键词搜索笔记，返回摘要列表（MCP 工具调用入口）。

        Phase D 增强：
          - 浏览器未启动/崩溃时返回结构化错误（含 code/action）
          - 搜索空结果时检测登录态，区分 LOGIN_EXPIRED 和正常空结果

        Args:
            keyword: 搜索关键词（调用方负责确保非空）
            max_count: 最多返回条数（默认 20）

        Returns:
            正常：{ keyword, count, results }
            错误：{ error, code, message, action }
        """
        # 快速路径：浏览器明确未启动时提前返回
        if not self._running:
            return browser_not_running_error().to_dict()

        async with self._lock:
            # 健康检查 + 自动恢复（释放锁前完成，恢复期间其他请求排队等待）
            bm = await self._ensure_browser()
            if bm is None:
                return browser_crashed_error().to_dict()

            # 二次防护：_ensure_browser 可能在恢复过程中改变 _bm
            if self._bm is None:
                return browser_crashed_error().to_dict()

            results = await src.search.search_notes(
                self._bm, keyword=keyword, max_count=max_count
            )

            # 空结果时检测登录态（区分"真的没搜到"和"登录态失效"）
            if not results:
                logged_in = await self._check_login_in_lock()
                if not logged_in:
                    return login_expired_error().to_dict()

        return {
            "keyword": keyword,
            "count": len(results),
            "results": results,
        }

    async def get_note_detail(self, note_url: str, max_comments: int = 20) -> dict:
        """采集单篇笔记详情 + 评论（MCP 工具调用入口）。

        Phase D 增强：
          - 浏览器未启动/崩溃时返回结构化错误
          - 采集失败时检测登录态，区分 LOGIN_EXPIRED 和 CRAWL_FAILED

        Args:
            note_url: 笔记详情页完整 URL
            max_comments: 最多采集评论数（默认 20）

        Returns:
            成功：笔记详情字典（包含 comments 字段）
            错误：{ error, code, message, action }
        """
        # 快速路径：浏览器明确未启动时提前返回
        if not self._running:
            return browser_not_running_error().to_dict()

        async with self._lock:
            bm = await self._ensure_browser()
            if bm is None:
                return browser_crashed_error().to_dict()

            if self._bm is None:
                return browser_crashed_error().to_dict()

            result = await src.note.fetch_single_note(
                self._bm, note_url=note_url, max_comments=max_comments
            )

            # 采集失败时检测登录态
            if result is None:
                logged_in = await self._check_login_in_lock()
                if not logged_in:
                    return login_expired_error().to_dict()
                return crawl_failed_error("URL 无效或页面无法加载").to_dict()

        return result

    async def check_login_status(self) -> dict:
        """检查当前小红书登录状态。

        Phase D 增强：
          - 未运行时返回包含 code 字段的结构化错误

        Returns:
            {
                "logged_in": bool,
                "browser_running": bool,
                "message": str,
                "code": str (仅错误时)
            }
        """
        if not self._running:
            err = browser_not_running_error()
            return {
                "logged_in": False,
                "browser_running": False,
                "message": err.message,
                "code": err.code,
            }

        async with self._lock:
            if self._bm is None:
                err = browser_not_running_error()
                return {
                    "logged_in": False,
                    "browser_running": False,
                    "message": err.message,
                    "code": err.code,
                }
            page = await self._bm.new_page()
            try:
                logged_in = await is_logged_in(page)
                if logged_in:
                    message = "已登录，可正常使用采集功能。"
                else:
                    message = (
                        "未登录。请先在终端运行 "
                        "`uv run python scripts/verify_login.py` 完成登录，"
                        "然后重启 MCP 服务。"
                    )
                return {
                    "logged_in": logged_in,
                    "browser_running": True,
                    "message": message,
                }
            finally:
                await page.close()

    async def crawl_keyword(
        self,
        keyword: str,
        max_notes: int = 10,
        max_comments: int = 20,
    ) -> dict:
        """执行完整采集流程：搜索 → 详情 → 评论 → 存储（MCP 工具调用入口）。

        Phase D 增强：
          - 浏览器未启动/崩溃时返回结构化错误

        Args:
            keyword: 搜索关键词（调用方负责确保非空）
            max_notes: 最多采集笔记数（默认 10，自动限制到 20 以内）
            max_comments: 每条笔记最多采集评论数（默认 20）

        Returns:
            正常：{ keyword, search_count, detail_count, total_comments, summary }
            错误：{ error, code, message, action }
        """
        # 快速路径：浏览器明确未启动时提前返回
        if not self._running:
            return browser_not_running_error().to_dict()

        # 限制 max_notes 到上限，避免单次任务耗时过长
        clamped_max_notes = min(max_notes, _MAX_NOTES_LIMIT)

        async with self._lock:
            bm = await self._ensure_browser()
            if bm is None:
                return browser_crashed_error().to_dict()

            if self._bm is None:
                return browser_crashed_error().to_dict()

            # Step 1: 搜索
            search_results = await src.search.search_notes(
                self._bm, keyword=keyword, max_count=clamped_max_notes
            )

            # Step 2: 批量采集详情 + 评论（无结果时跳过）
            if search_results:
                note_details = await src.note.fetch_note_details(
                    self._bm, search_results=search_results, max_comments=max_comments
                )
            else:
                note_details = []

            # Step 3: 持久化（JSON + Excel）
            storage = Storage(_DEFAULT_STORAGE_CONFIG)
            storage.save_all(keyword, search_results, note_details)

        total_comments = sum(len(note.get("comments", [])) for note in note_details)
        summary = (
            f"关键词 [{keyword}] 采集完成："
            f"搜索 {len(search_results)} 条，"
            f"详情 {len(note_details)} 条，"
            f"评论 {total_comments} 条"
        )
        logger.info(summary)
        return {
            "keyword": keyword,
            "search_count": len(search_results),
            "detail_count": len(note_details),
            "total_comments": total_comments,
            "summary": summary,
        }

    async def get_saved_data(
        self,
        keyword: Optional[str] = None,
        data_dir: Path = Path("data"),
    ) -> dict:
        """查询本地已保存的采集数据文件（不依赖浏览器）。

        扫描 data/raw/ 和 data/processed/ 目录，返回文件元数据列表。
        可通过 keyword 参数进行模糊过滤（不区分大小写）。

        Args:
            keyword: 关键词过滤（可选，空值 / None 表示返回所有文件）
            data_dir: 数据根目录（默认 "data"；测试时传入 tmp_path）

        Returns:
            {
                "files": [
                    {
                        "path": str,
                        "keyword": str,
                        "created_at": str,
                        "size_bytes": int
                    },
                    ...
                ]
            }
        """
        files: list[dict] = []
        # 只识别 raw 和 processed 两个子目录
        for subdir in ("raw", "processed"):
            dir_path = data_dir / subdir
            if not dir_path.exists():
                continue

            for file_path in sorted(dir_path.iterdir()):
                if not file_path.is_file():
                    continue

                # 只处理 JSON 和 xlsx 文件
                if file_path.suffix not in (".json", ".xlsx"):
                    continue

                extracted_keyword = _extract_keyword_from_stem(file_path.stem)

                # keyword 过滤：大小写不敏感的模糊匹配
                if keyword and keyword.lower() not in extracted_keyword.lower():
                    continue

                stat = file_path.stat()
                files.append({
                    "path": str(file_path),
                    "keyword": extracted_keyword,
                    "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(timespec="seconds"),
                    "size_bytes": stat.st_size,
                })

        return {"files": files}
