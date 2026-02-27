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
import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncGenerator, Optional

from src.auth import is_logged_in
from src.browser import BrowserManager

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


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
        self._running: bool = False
        self._lock = asyncio.Lock()

    def is_running(self) -> bool:
        """返回浏览器是否已成功启动并运行中。"""
        return self._running

    async def start(self) -> None:
        """启动浏览器（幂等：已在运行则直接返回）。

        Raises:
            Exception: 浏览器启动失败时透传异常
        """
        if self._running:
            logger.debug("浏览器会话已在运行，跳过重复启动")
            return

        logger.info("启动 MCP 浏览器会话（headless=%s）", self._headless)
        self._bm = BrowserManager(headless=self._headless)
        await self._bm.__aenter__()
        self._running = True
        logger.info("MCP 浏览器会话启动成功")

    async def stop(self) -> None:
        """关闭浏览器并释放所有资源（幂等：未运行时安全调用）。"""
        if self._bm is not None:
            logger.info("关闭 MCP 浏览器会话")
            await self._bm.__aexit__(None, None, None)
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
                "message": "浏览器未启动。请确保 MCP 服务正常运行后重试。",
            }

        async with self._lock:
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
