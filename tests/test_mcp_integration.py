"""
MCP 工具集成测试（Phase B）

测试完整调用链：MCP 工具处理器 → 真实 CrawlerSession → 底层采集模块

与 test_mcp_tools.py（单元测试）的区别：
  - 不 mock _session，使用真实 CrawlerSession 实例
  - mock 在 BrowserManager 和采集模块层（src.search、src.note）
  - 覆盖：完整调用链、会话生命周期、lifespan 管理、session 未启动时的降级路径
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import mcp_server
from src.session import CrawlerSession


class TestMCPIntegrationSearchNotes:
    """通过真实 CrawlerSession 测试 search_notes 工具的完整调用链。"""

    async def test_full_chain_returns_structured_result(self):
        """完整链路：mcp_server.search_notes → CrawlerSession.search_notes → src.search.search_notes。"""
        mock_results = [{"note_id": "abc", "title": "测试笔记"}]
        real_session = CrawlerSession(headless=True)

        with patch("src.session.BrowserManager") as MockBM:
            with patch("src.search.search_notes", new=AsyncMock(return_value=mock_results)) as mock_search:
                mock_bm = AsyncMock()
                MockBM.return_value = mock_bm
                mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
                mock_bm.__aexit__ = AsyncMock(return_value=None)

                await real_session.start()

                with patch.object(mcp_server, "_session", real_session):
                    result = await mcp_server.search_notes(keyword="Python")

                await real_session.stop()

        assert result["keyword"] == "Python"
        assert result["count"] == 1
        assert result["results"] == mock_results
        mock_search.assert_called_once_with(mock_bm, keyword="Python", max_count=20)

    async def test_full_chain_input_validation_before_session(self):
        """空 keyword 在 session 调用之前被拦截，session 不启动。"""
        real_session = CrawlerSession(headless=True)

        with patch.object(mcp_server, "_session", real_session):
            result = await mcp_server.search_notes(keyword="")

        assert result.get("error") is True
        assert real_session.is_running() is False  # session 从未启动

    async def test_full_chain_max_count_clamped_before_session(self):
        """max_count > 50 在到达 session 前被截断为 50。"""
        real_session = CrawlerSession(headless=True)

        with patch("src.session.BrowserManager") as MockBM:
            with patch("src.search.search_notes", new=AsyncMock(return_value=[])) as mock_search:
                mock_bm = AsyncMock()
                MockBM.return_value = mock_bm
                mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
                mock_bm.__aexit__ = AsyncMock(return_value=None)

                await real_session.start()

                with patch.object(mcp_server, "_session", real_session):
                    await mcp_server.search_notes(keyword="test", max_count=200)

                await real_session.stop()

        call_kwargs = mock_search.call_args[1]
        assert call_kwargs["max_count"] == 50

    async def test_full_chain_keyword_stripped_before_session(self):
        """keyword 前后空白在传入 session 前被去除。"""
        real_session = CrawlerSession(headless=True)

        with patch("src.session.BrowserManager") as MockBM:
            with patch("src.search.search_notes", new=AsyncMock(return_value=[])) as mock_search:
                mock_bm = AsyncMock()
                MockBM.return_value = mock_bm
                mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
                mock_bm.__aexit__ = AsyncMock(return_value=None)

                await real_session.start()

                with patch.object(mcp_server, "_session", real_session):
                    await mcp_server.search_notes(keyword="  Python  ")

                await real_session.stop()

        call_kwargs = mock_search.call_args[1]
        assert call_kwargs["keyword"] == "Python"


class TestMCPIntegrationGetNoteDetail:
    """通过真实 CrawlerSession 测试 get_note_detail 工具的完整调用链。"""

    async def test_full_chain_returns_note_detail(self):
        """完整链路：mcp_server.get_note_detail → CrawlerSession.get_note_detail → src.note.fetch_single_note。"""
        mock_detail = {"note_id": "abc123", "title": "测试笔记", "comments": []}
        note_url = "https://www.xiaohongshu.com/explore/abc123?xsec_token=xyz"
        real_session = CrawlerSession(headless=True)

        with patch("src.session.BrowserManager") as MockBM:
            with patch("src.note.fetch_single_note", new=AsyncMock(return_value=mock_detail)) as mock_fetch:
                mock_bm = AsyncMock()
                MockBM.return_value = mock_bm
                mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
                mock_bm.__aexit__ = AsyncMock(return_value=None)

                await real_session.start()

                with patch.object(mcp_server, "_session", real_session):
                    result = await mcp_server.get_note_detail(note_url=note_url)

                await real_session.stop()

        assert result == mock_detail
        mock_fetch.assert_called_once_with(mock_bm, note_url=note_url, max_comments=20)

    async def test_full_chain_fetch_returns_none_becomes_error_dict(self):
        """采集模块返回 None 时，最终 MCP 工具应返回 error dict（不透传 None）。"""
        note_url = "https://www.xiaohongshu.com/explore/invalid"
        real_session = CrawlerSession(headless=True)

        with patch("src.session.BrowserManager") as MockBM:
            with patch("src.note.fetch_single_note", new=AsyncMock(return_value=None)):
                mock_bm = AsyncMock()
                MockBM.return_value = mock_bm
                mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
                mock_bm.__aexit__ = AsyncMock(return_value=None)

                await real_session.start()

                with patch.object(mcp_server, "_session", real_session):
                    result = await mcp_server.get_note_detail(note_url=note_url)

                await real_session.stop()

        assert isinstance(result, dict)
        assert result.get("error") is True
        assert "message" in result

    async def test_full_chain_max_comments_clamped_before_session(self):
        """max_comments > 50 在到达 session 前被截断为 50。"""
        note_url = "https://www.xiaohongshu.com/explore/abc123"
        real_session = CrawlerSession(headless=True)

        with patch("src.session.BrowserManager") as MockBM:
            with patch("src.note.fetch_single_note", new=AsyncMock(return_value={})) as mock_fetch:
                mock_bm = AsyncMock()
                MockBM.return_value = mock_bm
                mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
                mock_bm.__aexit__ = AsyncMock(return_value=None)

                await real_session.start()

                with patch.object(mcp_server, "_session", real_session):
                    await mcp_server.get_note_detail(note_url=note_url, max_comments=100)

                await real_session.stop()

        call_kwargs = mock_fetch.call_args[1]
        assert call_kwargs["max_comments"] == 50

    async def test_full_chain_max_comments_clamped_below_zero(self):
        """max_comments < 0 在到达 session 前被截断为 0。"""
        note_url = "https://www.xiaohongshu.com/explore/abc123"
        real_session = CrawlerSession(headless=True)

        with patch("src.session.BrowserManager") as MockBM:
            with patch("src.note.fetch_single_note", new=AsyncMock(return_value={})) as mock_fetch:
                mock_bm = AsyncMock()
                MockBM.return_value = mock_bm
                mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
                mock_bm.__aexit__ = AsyncMock(return_value=None)

                await real_session.start()

                with patch.object(mcp_server, "_session", real_session):
                    await mcp_server.get_note_detail(note_url=note_url, max_comments=-5)

                await real_session.stop()

        call_kwargs = mock_fetch.call_args[1]
        assert call_kwargs["max_comments"] == 0


class TestMCPIntegrationLifespan:
    """测试 lifespan 钩子与真实 CrawlerSession 的集成。"""

    async def test_lifespan_starts_and_stops_real_session(self):
        """lifespan 应启动和停止真实 CrawlerSession（而非 mock）。"""
        real_session = CrawlerSession(headless=True)

        with patch("src.session.BrowserManager") as MockBM:
            mock_bm = AsyncMock()
            MockBM.return_value = mock_bm
            mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
            mock_bm.__aexit__ = AsyncMock(return_value=None)

            with patch.object(mcp_server, "_session", real_session):
                assert real_session.is_running() is False

                async with mcp_server.lifespan(MagicMock()):
                    assert real_session.is_running() is True

                assert real_session.is_running() is False

    async def test_lifespan_cleans_up_bm_on_exception(self):
        """lifespan 内部抛出异常时，session 内部状态应被完整清理。"""
        real_session = CrawlerSession(headless=True)

        with patch("src.session.BrowserManager") as MockBM:
            mock_bm = AsyncMock()
            MockBM.return_value = mock_bm
            mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
            mock_bm.__aexit__ = AsyncMock(return_value=None)

            with patch.object(mcp_server, "_session", real_session):
                try:
                    async with mcp_server.lifespan(MagicMock()):
                        raise RuntimeError("模拟服务崩溃")
                except RuntimeError:
                    pass

                assert real_session.is_running() is False
                assert real_session._bm is None
                assert real_session._exit_stack is None


class TestMCPIntegrationSessionNotRunning:
    """测试 MCP 工具在 session 未运行时的降级路径（未经 lifespan 启动）。"""

    async def test_search_notes_without_lifespan_returns_error(self):
        """未经 lifespan 启动时，search_notes 应优雅返回错误字典，不崩溃。"""
        real_session = CrawlerSession(headless=True)
        assert real_session.is_running() is False

        with patch.object(mcp_server, "_session", real_session):
            result = await mcp_server.search_notes(keyword="test")

        assert result.get("error") is True
        assert "message" in result

    async def test_get_note_detail_without_lifespan_returns_error(self):
        """未经 lifespan 启动时，get_note_detail 应优雅返回错误字典，不崩溃。"""
        real_session = CrawlerSession(headless=True)

        with patch.object(mcp_server, "_session", real_session):
            result = await mcp_server.get_note_detail(
                note_url="https://www.xiaohongshu.com/explore/abc123"
            )

        assert result.get("error") is True
        assert "message" in result

    async def test_check_login_status_without_lifespan_returns_not_running(self):
        """未经 lifespan 启动时，check_login_status 应返回 browser_running=False。"""
        real_session = CrawlerSession(headless=True)

        with patch.object(mcp_server, "_session", real_session):
            result = await mcp_server.check_login_status()

        assert result["browser_running"] is False
        assert result["logged_in"] is False

    async def test_search_notes_not_running_has_empty_results(self):
        """浏览器未运行时的错误响应应包含 results=[]，保持结构一致性。"""
        real_session = CrawlerSession(headless=True)

        with patch.object(mcp_server, "_session", real_session):
            result = await mcp_server.search_notes(keyword="test")

        assert result.get("results") == []
