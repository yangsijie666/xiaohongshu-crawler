"""
MCP 工具处理器测试（Phase A + Phase B）

测试 check_login_status / search_notes / get_note_detail MCP 工具及 lifespan 钩子

测试策略：
  - 通过 patch.object 替换模块级 _session 为 mock
  - 直接调用工具函数，验证参数传递与返回值格式
  - 覆盖：正常路径、输入验证、边界值 clamp、session 返回 None 的处理
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import mcp_server


class TestCheckLoginStatusTool:
    """测试 check_login_status MCP 工具（Phase A）。"""

    async def test_returns_session_result(self):
        """应将 session.check_login_status() 结果直接返回给调用方。"""
        mock_result = {"logged_in": True, "browser_running": True, "message": "已登录"}
        mock_session = AsyncMock()
        mock_session.check_login_status = AsyncMock(return_value=mock_result)

        with patch.object(mcp_server, "_session", mock_session):
            result = await mcp_server.check_login_status()

        mock_session.check_login_status.assert_called_once()
        assert result == mock_result

    async def test_returns_not_logged_in_response(self):
        """未登录时应透传 session 返回的状态字典。"""
        mock_result = {
            "logged_in": False,
            "browser_running": True,
            "message": "未登录，请扫码",
        }
        mock_session = AsyncMock()
        mock_session.check_login_status = AsyncMock(return_value=mock_result)

        with patch.object(mcp_server, "_session", mock_session):
            result = await mcp_server.check_login_status()

        assert result["logged_in"] is False


class TestLifespan:
    """测试 lifespan 启停钩子。"""

    async def test_lifespan_starts_and_stops_session(self):
        """进入 lifespan 应启动 session，退出时停止 session。"""
        mock_session = AsyncMock()
        mock_session.start = AsyncMock()
        mock_session.stop = AsyncMock()

        with patch.object(mcp_server, "_session", mock_session):
            async with mcp_server.lifespan(MagicMock()):
                mock_session.start.assert_called_once()
                mock_session.stop.assert_not_called()

        mock_session.stop.assert_called_once()

    async def test_lifespan_stops_session_on_exception(self):
        """即使 yield 内抛出异常，lifespan 的 finally 也应确保 stop() 被调用。"""
        mock_session = AsyncMock()
        mock_session.start = AsyncMock()
        mock_session.stop = AsyncMock()

        with patch.object(mcp_server, "_session", mock_session):
            try:
                async with mcp_server.lifespan(MagicMock()):
                    raise RuntimeError("模拟服务崩溃")
            except RuntimeError:
                pass

        mock_session.stop.assert_called_once()


class TestSearchNotesTool:
    """测试 search_notes MCP 工具。"""

    async def test_returns_results_from_session(self):
        """正常调用应返回 session 结果，max_count 默认 20。"""
        mock_result = {
            "keyword": "测试",
            "count": 2,
            "results": [{"note_id": "1"}, {"note_id": "2"}],
        }
        mock_session = AsyncMock()
        mock_session.search_notes = AsyncMock(return_value=mock_result)

        with patch.object(mcp_server, "_session", mock_session):
            result = await mcp_server.search_notes(keyword="测试")

        mock_session.search_notes.assert_called_once_with(keyword="测试", max_count=20)
        assert result == mock_result

    async def test_clamps_max_count_above_50(self):
        """max_count > 50 应被截断到 50。"""
        mock_session = AsyncMock()
        mock_session.search_notes = AsyncMock(return_value={"keyword": "k", "count": 0, "results": []})

        with patch.object(mcp_server, "_session", mock_session):
            await mcp_server.search_notes(keyword="test", max_count=100)

        call_kwargs = mock_session.search_notes.call_args[1]
        assert call_kwargs["max_count"] == 50

    async def test_clamps_max_count_below_1(self):
        """max_count < 1 应被截断到 1。"""
        mock_session = AsyncMock()
        mock_session.search_notes = AsyncMock(return_value={"keyword": "k", "count": 0, "results": []})

        with patch.object(mcp_server, "_session", mock_session):
            await mcp_server.search_notes(keyword="test", max_count=0)

        call_kwargs = mock_session.search_notes.call_args[1]
        assert call_kwargs["max_count"] == 1

    async def test_returns_error_for_empty_keyword(self):
        """空 keyword 应直接返回错误，不调用 session。"""
        mock_session = AsyncMock()

        with patch.object(mcp_server, "_session", mock_session):
            result = await mcp_server.search_notes(keyword="")

        assert result.get("error") is True
        mock_session.search_notes.assert_not_called()

    async def test_returns_error_for_whitespace_only_keyword(self):
        """纯空白字符 keyword 应视为空，返回错误。"""
        mock_session = AsyncMock()

        with patch.object(mcp_server, "_session", mock_session):
            result = await mcp_server.search_notes(keyword="   ")

        assert result.get("error") is True
        mock_session.search_notes.assert_not_called()

    async def test_strips_keyword_before_calling_session(self):
        """keyword 前后空白应被去除后传入 session。"""
        mock_session = AsyncMock()
        mock_session.search_notes = AsyncMock(return_value={"keyword": "test", "count": 0, "results": []})

        with patch.object(mcp_server, "_session", mock_session):
            await mcp_server.search_notes(keyword="  test  ")

        call_kwargs = mock_session.search_notes.call_args[1]
        assert call_kwargs["keyword"] == "test"

    async def test_valid_max_count_at_boundary(self):
        """边界值 max_count=1 和 max_count=50 应不被修改。"""
        mock_session = AsyncMock()
        mock_session.search_notes = AsyncMock(return_value={"keyword": "k", "count": 0, "results": []})

        with patch.object(mcp_server, "_session", mock_session):
            await mcp_server.search_notes(keyword="test", max_count=1)
        assert mock_session.search_notes.call_args[1]["max_count"] == 1

        with patch.object(mcp_server, "_session", mock_session):
            await mcp_server.search_notes(keyword="test", max_count=50)
        assert mock_session.search_notes.call_args[1]["max_count"] == 50


class TestGetNoteDetailTool:
    """测试 get_note_detail MCP 工具。"""

    async def test_returns_detail_from_session(self):
        """正常调用应返回 session 结果，max_comments 默认 20。"""
        mock_detail = {"note_id": "abc123", "title": "测试笔记", "comments": []}
        mock_session = AsyncMock()
        mock_session.get_note_detail = AsyncMock(return_value=mock_detail)
        note_url = "https://www.xiaohongshu.com/explore/abc123"

        with patch.object(mcp_server, "_session", mock_session):
            result = await mcp_server.get_note_detail(note_url=note_url)

        mock_session.get_note_detail.assert_called_once_with(note_url=note_url, max_comments=20)
        assert result == mock_detail

    async def test_returns_error_when_session_returns_none(self):
        """session 返回 None 时应返回含 error=True 的字典。"""
        mock_session = AsyncMock()
        mock_session.get_note_detail = AsyncMock(return_value=None)
        note_url = "https://www.xiaohongshu.com/explore/abc123"

        with patch.object(mcp_server, "_session", mock_session):
            result = await mcp_server.get_note_detail(note_url=note_url)

        assert result.get("error") is True
        assert "message" in result

    async def test_clamps_max_comments_above_50(self):
        """max_comments > 50 应被截断到 50。"""
        mock_session = AsyncMock()
        mock_session.get_note_detail = AsyncMock(return_value={"note_id": "x"})
        note_url = "https://www.xiaohongshu.com/explore/abc123"

        with patch.object(mcp_server, "_session", mock_session):
            await mcp_server.get_note_detail(note_url=note_url, max_comments=100)

        call_kwargs = mock_session.get_note_detail.call_args[1]
        assert call_kwargs["max_comments"] == 50

    async def test_clamps_max_comments_below_0(self):
        """max_comments < 0 应被截断到 0。"""
        mock_session = AsyncMock()
        mock_session.get_note_detail = AsyncMock(return_value={"note_id": "x"})
        note_url = "https://www.xiaohongshu.com/explore/abc123"

        with patch.object(mcp_server, "_session", mock_session):
            await mcp_server.get_note_detail(note_url=note_url, max_comments=-5)

        call_kwargs = mock_session.get_note_detail.call_args[1]
        assert call_kwargs["max_comments"] == 0

    async def test_returns_error_for_empty_url(self):
        """空 note_url 应直接返回错误，不调用 session。"""
        mock_session = AsyncMock()

        with patch.object(mcp_server, "_session", mock_session):
            result = await mcp_server.get_note_detail(note_url="")

        assert result.get("error") is True
        mock_session.get_note_detail.assert_not_called()

    async def test_valid_max_comments_at_boundaries(self):
        """边界值 max_comments=0 和 max_comments=50 应不被修改。"""
        mock_session = AsyncMock()
        mock_session.get_note_detail = AsyncMock(return_value={"note_id": "x"})
        note_url = "https://www.xiaohongshu.com/explore/abc123"

        with patch.object(mcp_server, "_session", mock_session):
            await mcp_server.get_note_detail(note_url=note_url, max_comments=0)
        assert mock_session.get_note_detail.call_args[1]["max_comments"] == 0

        with patch.object(mcp_server, "_session", mock_session):
            await mcp_server.get_note_detail(note_url=note_url, max_comments=50)
        assert mock_session.get_note_detail.call_args[1]["max_comments"] == 50

    async def test_error_response_contains_note_url(self):
        """错误响应应包含原始 note_url，方便调试。"""
        mock_session = AsyncMock()
        mock_session.get_note_detail = AsyncMock(return_value=None)
        note_url = "https://www.xiaohongshu.com/explore/abc123"

        with patch.object(mcp_server, "_session", mock_session):
            result = await mcp_server.get_note_detail(note_url=note_url)

        assert note_url in result.get("message", "")
