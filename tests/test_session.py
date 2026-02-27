"""
CrawlerSession 单元测试

测试策略：
  - BrowserManager 全部 mock，不依赖真实浏览器
  - is_logged_in 函数 mock，隔离网络调用
  - 覆盖：初始状态、生命周期、并发锁、登录态检查
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

# 以下导入在 src/session.py 实现之前会失败（RED 状态预期）
from src.session import CrawlerSession


class TestCrawlerSessionInitialState:
    """测试初始状态（未启动浏览器）。"""

    def test_not_running_initially(self):
        """新实例的 is_running() 应为 False。"""
        session = CrawlerSession()
        assert session.is_running() is False

    def test_default_headless_is_true(self):
        """MCP 服务默认使用 headless 模式。"""
        session = CrawlerSession()
        assert session._headless is True

    def test_custom_headless_false(self):
        """可以显式指定 headless=False（供调试使用）。"""
        session = CrawlerSession(headless=False)
        assert session._headless is False


class TestCrawlerSessionLifecycle:
    """测试浏览器生命周期管理。"""

    async def test_start_sets_running(self):
        """start() 成功后 is_running() 应为 True。"""
        with patch("src.session.BrowserManager") as MockBM:
            mock_bm = AsyncMock()
            MockBM.return_value = mock_bm
            mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
            mock_bm.__aexit__ = AsyncMock(return_value=None)

            session = CrawlerSession()
            await session.start()

            assert session.is_running() is True

    async def test_stop_clears_running(self):
        """stop() 后 is_running() 应为 False。"""
        with patch("src.session.BrowserManager") as MockBM:
            mock_bm = AsyncMock()
            MockBM.return_value = mock_bm
            mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
            mock_bm.__aexit__ = AsyncMock(return_value=None)

            session = CrawlerSession()
            await session.start()
            await session.stop()

            assert session.is_running() is False

    async def test_stop_when_not_running_is_safe(self):
        """未启动时调用 stop() 不应抛出异常。"""
        session = CrawlerSession()
        await session.stop()  # 不应抛出
        assert session.is_running() is False

    async def test_double_start_is_idempotent(self):
        """重复调用 start() 不应重复创建浏览器实例。"""
        with patch("src.session.BrowserManager") as MockBM:
            mock_bm = AsyncMock()
            MockBM.return_value = mock_bm
            mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
            mock_bm.__aexit__ = AsyncMock(return_value=None)

            session = CrawlerSession()
            await session.start()
            await session.start()  # 第二次调用应幂等

            # BrowserManager 只应被实例化一次
            assert MockBM.call_count == 1

    async def test_stop_calls_aexit(self):
        """stop() 应正确调用 BrowserManager.__aexit__。"""
        with patch("src.session.BrowserManager") as MockBM:
            mock_bm = AsyncMock()
            MockBM.return_value = mock_bm
            mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
            mock_bm.__aexit__ = AsyncMock(return_value=None)

            session = CrawlerSession()
            await session.start()
            await session.stop()

            mock_bm.__aexit__.assert_called_once_with(None, None, None)


class TestCrawlerSessionLock:
    """测试并发锁确保操作串行化。"""

    async def test_lock_serializes_concurrent_access(self):
        """并发调用 browser_lock() 时，操作应串行执行（无交错）。"""
        session = CrawlerSession()
        execution_order: list[str] = []

        async def task(name: str) -> None:
            async with session.browser_lock():
                execution_order.append(f"enter_{name}")
                await asyncio.sleep(0.01)
                execution_order.append(f"exit_{name}")

        await asyncio.gather(task("a"), task("b"))

        # 验证没有交错：enter_x 之后的下一个事件必须是 exit_x
        a_enter = execution_order.index("enter_a")
        a_exit = execution_order.index("exit_a")
        b_enter = execution_order.index("enter_b")
        b_exit = execution_order.index("exit_b")

        # a 先完成后 b 才开始，或 b 先完成后 a 才开始
        assert (a_exit < b_enter) or (b_exit < a_enter)

    async def test_lock_yields_browser_manager(self):
        """browser_lock() 应 yield BrowserManager 实例（启动后）。"""
        with patch("src.session.BrowserManager") as MockBM:
            mock_bm = AsyncMock()
            MockBM.return_value = mock_bm
            mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
            mock_bm.__aexit__ = AsyncMock(return_value=None)

            session = CrawlerSession()
            await session.start()

            async with session.browser_lock() as bm:
                assert bm is mock_bm


class TestCrawlerSessionLoginStatus:
    """测试登录态检查接口。"""

    async def test_check_login_when_not_running(self):
        """浏览器未启动时，返回 browser_running=False。"""
        session = CrawlerSession()
        result = await session.check_login_status()

        assert result["logged_in"] is False
        assert result["browser_running"] is False
        assert "message" in result
        assert isinstance(result["message"], str)

    async def test_check_login_returns_true_when_logged_in(self):
        """已登录时，返回 logged_in=True, browser_running=True。"""
        with patch("src.session.BrowserManager") as MockBM:
            with patch("src.session.is_logged_in", return_value=True):
                mock_bm = AsyncMock()
                MockBM.return_value = mock_bm
                mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
                mock_bm.__aexit__ = AsyncMock(return_value=None)
                mock_page = AsyncMock()
                mock_bm.new_page = AsyncMock(return_value=mock_page)

                session = CrawlerSession()
                await session.start()
                result = await session.check_login_status()

                assert result["logged_in"] is True
                assert result["browser_running"] is True
                assert "message" in result

    async def test_check_login_returns_false_when_not_logged_in(self):
        """未登录时，返回 logged_in=False, browser_running=True。"""
        with patch("src.session.BrowserManager") as MockBM:
            with patch("src.session.is_logged_in", return_value=False):
                mock_bm = AsyncMock()
                MockBM.return_value = mock_bm
                mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
                mock_bm.__aexit__ = AsyncMock(return_value=None)
                mock_page = AsyncMock()
                mock_bm.new_page = AsyncMock(return_value=mock_page)

                session = CrawlerSession()
                await session.start()
                result = await session.check_login_status()

                assert result["logged_in"] is False
                assert result["browser_running"] is True
                assert "message" in result

    async def test_check_login_closes_page_after_check(self):
        """登录态检查完成后应关闭页面，防止资源泄漏。"""
        with patch("src.session.BrowserManager") as MockBM:
            with patch("src.session.is_logged_in", return_value=True):
                mock_bm = AsyncMock()
                MockBM.return_value = mock_bm
                mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
                mock_bm.__aexit__ = AsyncMock(return_value=None)
                mock_page = AsyncMock()
                mock_bm.new_page = AsyncMock(return_value=mock_page)

                session = CrawlerSession()
                await session.start()
                await session.check_login_status()

                mock_page.close.assert_called_once()
