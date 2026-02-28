"""
CrawlerSession Phase D 测试 — 健康检查、自动恢复、登录态检测、结构化错误

测试策略：
  - BrowserManager 全部 mock，不依赖真实浏览器
  - 模拟浏览器崩溃（is_connected 返回 False）验证自动恢复
  - 模拟登录态失效验证结构化错误返回
  - 所有错误响应统一包含 error/code/message/action 四个字段
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from src.session import CrawlerSession


def _make_mock_bm(*, connected: bool = True) -> AsyncMock:
    """创建标准 mock BrowserManager，可控制 is_connected 状态。"""
    mock_bm = AsyncMock()
    mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
    mock_bm.__aexit__ = AsyncMock(return_value=None)

    # 模拟 context.browser.is_connected()
    mock_browser = MagicMock()
    mock_browser.is_connected.return_value = connected
    mock_context = MagicMock()
    mock_context.browser = mock_browser
    type(mock_bm).context = PropertyMock(return_value=mock_context)

    # 默认 new_page
    mock_page = AsyncMock()
    mock_bm.new_page = AsyncMock(return_value=mock_page)

    return mock_bm


class TestBrowserHealthCheck:
    """D1: 浏览器健康检查。"""

    async def test_healthy_browser_returns_true(self):
        """浏览器正常连接时，_is_browser_healthy() 返回 True。"""
        with patch("src.session.BrowserManager") as MockBM:
            MockBM.return_value = _make_mock_bm(connected=True)

            session = CrawlerSession()
            await session.start()

            assert await session._is_browser_healthy() is True

    async def test_disconnected_browser_returns_false(self):
        """浏览器断开连接时，_is_browser_healthy() 返回 False。"""
        with patch("src.session.BrowserManager") as MockBM:
            mock_bm = _make_mock_bm(connected=False)
            MockBM.return_value = mock_bm

            session = CrawlerSession()
            await session.start()

            assert await session._is_browser_healthy() is False

    async def test_none_bm_returns_false(self):
        """_bm 为 None 时，_is_browser_healthy() 返回 False。"""
        session = CrawlerSession()
        assert await session._is_browser_healthy() is False

    async def test_none_context_returns_false(self):
        """context 为 None 时，_is_browser_healthy() 返回 False。"""
        with patch("src.session.BrowserManager") as MockBM:
            mock_bm = _make_mock_bm(connected=True)
            type(mock_bm).context = PropertyMock(return_value=None)
            MockBM.return_value = mock_bm

            session = CrawlerSession()
            await session.start()

            assert await session._is_browser_healthy() is False

    async def test_exception_during_check_returns_false(self):
        """健康检查过程中抛出异常时，返回 False（不传播异常）。"""
        with patch("src.session.BrowserManager") as MockBM:
            mock_bm = _make_mock_bm(connected=True)
            # context 属性访问时抛异常
            type(mock_bm).context = PropertyMock(side_effect=RuntimeError("boom"))
            MockBM.return_value = mock_bm

            session = CrawlerSession()
            await session.start()

            assert await session._is_browser_healthy() is False


class TestBrowserAutoRecovery:
    """D1: 浏览器崩溃自动恢复。"""

    async def test_auto_recovery_on_crashed_browser(self):
        """浏览器崩溃后，_ensure_browser() 应自动重建浏览器。"""
        call_count = 0

        # 第一次创建：disconnected（模拟崩溃）
        # 第二次创建：connected（恢复成功）
        def make_bm_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_mock_bm(connected=False)
            return _make_mock_bm(connected=True)

        with patch("src.session.BrowserManager", side_effect=make_bm_side_effect):
            session = CrawlerSession()
            await session.start()

            # 第一次检查：崩溃，应触发恢复
            bm = await session._ensure_browser()
            assert bm is not None
            assert session.is_running() is True

    async def test_auto_recovery_failure_returns_none(self):
        """自动恢复也失败时，_ensure_browser() 应返回 None。"""
        call_count = 0

        def make_bm_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_mock_bm(connected=False)
            # 第二次创建抛异常（恢复失败）
            mock_bm = AsyncMock()
            mock_bm.__aenter__ = AsyncMock(side_effect=RuntimeError("恢复失败"))
            mock_bm.__aexit__ = AsyncMock(return_value=None)
            return mock_bm

        with patch("src.session.BrowserManager", side_effect=make_bm_side_effect):
            session = CrawlerSession()
            await session.start()

            bm = await session._ensure_browser()
            assert bm is None

    async def test_ensure_browser_returns_bm_when_healthy(self):
        """浏览器健康时，_ensure_browser() 直接返回当前 BrowserManager。"""
        with patch("src.session.BrowserManager") as MockBM:
            mock_bm = _make_mock_bm(connected=True)
            MockBM.return_value = mock_bm

            session = CrawlerSession()
            await session.start()

            bm = await session._ensure_browser()
            assert bm is mock_bm

    async def test_ensure_browser_when_not_running(self):
        """未启动时，_ensure_browser() 返回 None。"""
        session = CrawlerSession()
        bm = await session._ensure_browser()
        assert bm is None


class TestStructuredErrors:
    """D1 + D3: 各方法应返回统一格式的结构化错误。"""

    async def test_search_notes_returns_structured_error_when_not_running(self):
        """浏览器未启动时，search_notes 应返回包含 code 字段的错误。"""
        session = CrawlerSession()
        result = await session.search_notes("测试")

        assert result["error"] is True
        assert "code" in result
        assert result["code"] == "BROWSER_NOT_RUNNING"
        assert "action" in result

    async def test_get_note_detail_returns_structured_error_when_not_running(self):
        """浏览器未启动时，get_note_detail 应返回结构化错误。"""
        session = CrawlerSession()
        result = await session.get_note_detail("https://example.com/explore/123")

        assert result["error"] is True
        assert result["code"] == "BROWSER_NOT_RUNNING"
        assert "action" in result

    async def test_crawl_keyword_returns_structured_error_when_not_running(self):
        """浏览器未启动时，crawl_keyword 应返回结构化错误。"""
        session = CrawlerSession()
        result = await session.crawl_keyword("测试")

        assert result["error"] is True
        assert result["code"] == "BROWSER_NOT_RUNNING"
        assert "action" in result

    async def test_check_login_returns_structured_error_when_not_running(self):
        """浏览器未启动时，check_login_status 应返回结构化错误。"""
        session = CrawlerSession()
        result = await session.check_login_status()

        assert result["logged_in"] is False
        assert result["browser_running"] is False
        assert "code" in result
        assert result["code"] == "BROWSER_NOT_RUNNING"

    async def test_search_notes_returns_structured_error_on_browser_crash(self):
        """浏览器崩溃且恢复失败时，search_notes 返回 BROWSER_CRASHED。"""
        call_count = 0

        def make_bm_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_mock_bm(connected=False)
            mock_bm = AsyncMock()
            mock_bm.__aenter__ = AsyncMock(side_effect=RuntimeError("恢复失败"))
            mock_bm.__aexit__ = AsyncMock(return_value=None)
            return mock_bm

        with patch("src.session.BrowserManager", side_effect=make_bm_side_effect):
            session = CrawlerSession()
            await session.start()

            result = await session.search_notes("test")
            assert result["error"] is True
            assert result["code"] == "BROWSER_CRASHED"


class TestLoginDetection:
    """D2: 操作中的登录态失效检测。"""

    async def test_search_detects_login_expired(self):
        """search_notes 返回空结果时，应检测登录态并返回 LOGIN_EXPIRED。"""
        with patch("src.session.BrowserManager") as MockBM:
            mock_bm = _make_mock_bm(connected=True)
            MockBM.return_value = mock_bm

            session = CrawlerSession()
            await session.start()

            # search 返回空 + 登录态检测为未登录
            with patch("src.search.search_notes", new_callable=AsyncMock, return_value=[]):
                with patch("src.session.is_logged_in", new_callable=AsyncMock, return_value=False):
                    result = await session.search_notes("test")

                    assert result["error"] is True
                    assert result["code"] == "LOGIN_EXPIRED"
                    assert "verify_login" in result["action"]

    async def test_search_returns_normal_empty_when_logged_in(self):
        """已登录但搜索无结果时，返回正常空结果（不误报 LOGIN_EXPIRED）。"""
        with patch("src.session.BrowserManager") as MockBM:
            mock_bm = _make_mock_bm(connected=True)
            MockBM.return_value = mock_bm

            session = CrawlerSession()
            await session.start()

            with patch("src.search.search_notes", new_callable=AsyncMock, return_value=[]):
                with patch("src.session.is_logged_in", new_callable=AsyncMock, return_value=True):
                    result = await session.search_notes("test")

                    # 正常空结果，不是错误
                    assert result.get("error") is not True
                    assert result["count"] == 0

    async def test_get_note_detail_detects_login_expired(self):
        """get_note_detail 返回 None 时，应检测登录态并返回 LOGIN_EXPIRED。"""
        with patch("src.session.BrowserManager") as MockBM:
            mock_bm = _make_mock_bm(connected=True)
            MockBM.return_value = mock_bm

            session = CrawlerSession()
            await session.start()

            with patch("src.note.fetch_single_note", new_callable=AsyncMock, return_value=None):
                with patch("src.session.is_logged_in", new_callable=AsyncMock, return_value=False):
                    result = await session.get_note_detail(
                        "https://www.xiaohongshu.com/explore/abc123"
                    )

                    assert result["error"] is True
                    assert result["code"] == "LOGIN_EXPIRED"

    async def test_get_note_detail_returns_crawl_failed_when_logged_in(self):
        """已登录但采集失败时，返回 CRAWL_FAILED（不是 LOGIN_EXPIRED）。"""
        with patch("src.session.BrowserManager") as MockBM:
            mock_bm = _make_mock_bm(connected=True)
            MockBM.return_value = mock_bm

            session = CrawlerSession()
            await session.start()

            with patch("src.note.fetch_single_note", new_callable=AsyncMock, return_value=None):
                with patch("src.session.is_logged_in", new_callable=AsyncMock, return_value=True):
                    result = await session.get_note_detail(
                        "https://www.xiaohongshu.com/explore/abc123"
                    )

                    assert result["error"] is True
                    assert result["code"] == "CRAWL_FAILED"
