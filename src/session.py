"""
MCP 服务级浏览器会话管理模块

职责：
  - 管理 Playwright 浏览器实例的服务级生命周期（长驻进程，区别于单次 async with）
  - 通过 asyncio.Lock 序列化所有浏览器操作，防止并发竞争
  - 提供登录态检查接口，供 MCP 工具调用
  - 健康检查 + 自动重建（Phase D 实现）

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
from src.storage import Storage

logger = logging.getLogger(__name__)

# 浏览器未启动时的统一错误消息
_ERR_BROWSER_NOT_RUNNING = "浏览器未启动。请确保 MCP 服务正常运行后重试。"

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

        Args:
            keyword: 搜索关键词（调用方负责确保非空）
            max_count: 最多返回条数（默认 20）

        Returns:
            {
                "keyword": str,     # 搜索关键词
                "count": int,       # 实际返回条数
                "results": list     # 笔记摘要列表
            }
            或 {"error": True, "message": str, "results": []}（浏览器未启动）
        """
        # 快速路径：浏览器明确未启动时提前返回
        if not self._running:
            return {"error": True, "message": _ERR_BROWSER_NOT_RUNNING, "results": []}

        async with self._lock:
            # 二次防护：stop() 可能在获取锁前被调用（_bm 变为 None）
            if self._bm is None:
                return {"error": True, "message": _ERR_BROWSER_NOT_RUNNING, "results": []}
            results = await src.search.search_notes(
                self._bm, keyword=keyword, max_count=max_count
            )

        return {
            "keyword": keyword,
            "count": len(results),
            "results": results,
        }

    async def get_note_detail(self, note_url: str, max_comments: int = 20) -> dict:
        """采集单篇笔记详情 + 评论（MCP 工具调用入口）。

        Args:
            note_url: 笔记详情页完整 URL
            max_comments: 最多采集评论数（默认 20）

        Returns:
            笔记详情字典（包含 comments 字段），
            或 {"error": True, "message": str}（浏览器未启动 / 采集失败）
            — 始终返回 dict，不返回 None
        """
        # 快速路径：浏览器明确未启动时提前返回
        if not self._running:
            return {"error": True, "message": _ERR_BROWSER_NOT_RUNNING}

        async with self._lock:
            # 二次防护：stop() 可能在获取锁前被调用（_bm 变为 None）
            if self._bm is None:
                return {"error": True, "message": _ERR_BROWSER_NOT_RUNNING}
            result = await src.note.fetch_single_note(
                self._bm, note_url=note_url, max_comments=max_comments
            )

        if result is None:
            return {"error": True, "message": "笔记采集失败，URL 无效或页面无法加载"}
        return result

    async def check_login_status(self) -> dict:
        """检查当前小红书登录状态。

        不需要手动调用 browser_lock()，内部已自动加锁。

        Returns:
            {
                "logged_in": bool,         # 是否已登录小红书
                "browser_running": bool,   # 浏览器是否在运行
                "message": str             # 状态说明（含操作建议）
            }
        """
        if not self._running:
            return {
                "logged_in": False,
                "browser_running": False,
                "message": _ERR_BROWSER_NOT_RUNNING,
            }

        async with self._lock:
            if self._bm is None:
                return {
                    "logged_in": False,
                    "browser_running": False,
                    "message": _ERR_BROWSER_NOT_RUNNING,
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
                # 确保页面始终被关闭，防止资源泄漏
                await page.close()

    async def crawl_keyword(
        self,
        keyword: str,
        max_notes: int = 10,
        max_comments: int = 20,
    ) -> dict:
        """执行完整采集流程：搜索 → 详情 → 评论 → 存储（MCP 工具调用入口）。

        Args:
            keyword: 搜索关键词（调用方负责确保非空）
            max_notes: 最多采集笔记数（默认 10，自动限制到 20 以内）
            max_comments: 每条笔记最多采集评论数（默认 20）

        Returns:
            {
                "keyword": str,
                "search_count": int,   # 搜索阶段获得的笔记数
                "detail_count": int,   # 成功采集详情的笔记数
                "total_comments": int, # 所有笔记的评论总数
                "summary": str         # 人类可读的采集摘要
            }
            或 {"error": True, "message": str}（浏览器未启动 / 竞态）
        """
        # 快速路径：浏览器明确未启动时提前返回
        if not self._running:
            return {"error": True, "message": _ERR_BROWSER_NOT_RUNNING}

        # 限制 max_notes 到上限，避免单次任务耗时过长
        clamped_max_notes = min(max_notes, _MAX_NOTES_LIMIT)

        async with self._lock:
            # 二次防护：stop() 可能在获取锁前被调用（_bm 变为 None）
            if self._bm is None:
                return {"error": True, "message": _ERR_BROWSER_NOT_RUNNING}

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
                        "path": str,         # 文件相对路径
                        "keyword": str,      # 从文件名提取的关键词
                        "created_at": str,   # 文件创建时间（ISO 8601）
                        "size_bytes": int    # 文件大小（字节）
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
