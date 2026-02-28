"""
MCP 工具 Phase D 测试 — 超时控制 + 日志文件输出 + 结构化错误传递

测试策略：
  - D4: 验证各工具的 asyncio.wait_for 超时行为
  - D5: 验证日志文件输出配置
  - 结构化错误: 验证 MCP 层正确传递 session 层的结构化错误
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

import mcp_server


class TestToolTimeouts:
    """D4: 工具超时控制。"""

    async def test_search_notes_timeout_returns_structured_error(self):
        """search_notes 超时应返回 TIMEOUT 结构化错误。"""
        # 模拟 session.search_notes 永远不返回
        async def slow_search(*args, **kwargs):
            await asyncio.sleep(999)

        mock_session = AsyncMock()
        mock_session.search_notes = slow_search

        with patch.object(mcp_server, "_session", mock_session):
            # 临时将超时设为极短值以加速测试
            with patch.object(mcp_server, "TOOL_TIMEOUTS", {"search_notes": 0.01, "get_note_detail": 0.01, "crawl_keyword": 0.01}):
                result = await mcp_server.search_notes(keyword="test")

        assert result["error"] is True
        assert result["code"] == "TIMEOUT"
        assert "search_notes" in result["message"]

    async def test_get_note_detail_timeout_returns_structured_error(self):
        """get_note_detail 超时应返回 TIMEOUT 结构化错误。"""
        async def slow_detail(*args, **kwargs):
            await asyncio.sleep(999)

        mock_session = AsyncMock()
        mock_session.get_note_detail = slow_detail

        with patch.object(mcp_server, "_session", mock_session):
            with patch.object(mcp_server, "TOOL_TIMEOUTS", {"search_notes": 0.01, "get_note_detail": 0.01, "crawl_keyword": 0.01}):
                result = await mcp_server.get_note_detail(
                    note_url="https://www.xiaohongshu.com/explore/abc123"
                )

        assert result["error"] is True
        assert result["code"] == "TIMEOUT"
        assert "get_note_detail" in result["message"]

    async def test_crawl_keyword_timeout_returns_structured_error(self):
        """crawl_keyword 超时应返回 TIMEOUT 结构化错误。"""
        async def slow_crawl(*args, **kwargs):
            await asyncio.sleep(999)

        mock_session = AsyncMock()
        mock_session.crawl_keyword = slow_crawl

        with patch.object(mcp_server, "_session", mock_session):
            with patch.object(mcp_server, "TOOL_TIMEOUTS", {"search_notes": 0.01, "get_note_detail": 0.01, "crawl_keyword": 0.01}):
                result = await mcp_server.crawl_keyword(keyword="test")

        assert result["error"] is True
        assert result["code"] == "TIMEOUT"
        assert "crawl_keyword" in result["message"]

    async def test_search_notes_normal_within_timeout(self):
        """正常返回时（未超时）不受超时控制影响。"""
        mock_result = {"keyword": "ok", "count": 1, "results": [{"note_id": "1"}]}
        mock_session = AsyncMock()
        mock_session.search_notes = AsyncMock(return_value=mock_result)

        with patch.object(mcp_server, "_session", mock_session):
            result = await mcp_server.search_notes(keyword="ok")

        assert result == mock_result

    async def test_timeout_values_match_spec(self):
        """超时值应与 PLAN 规格匹配：search 120s / detail 90s / crawl 600s。"""
        assert mcp_server.TOOL_TIMEOUTS["search_notes"] == 120
        assert mcp_server.TOOL_TIMEOUTS["get_note_detail"] == 90
        assert mcp_server.TOOL_TIMEOUTS["crawl_keyword"] == 600


class TestStructuredErrorPassthrough:
    """验证 MCP 工具层正确传递 session 层的结构化错误。"""

    async def test_search_passes_through_session_error_with_code(self):
        """session 返回含 code 的错误应被 MCP 工具层透传。"""
        mock_error = {
            "error": True,
            "code": "LOGIN_EXPIRED",
            "message": "登录已过期",
            "action": "请重新登录",
        }
        mock_session = AsyncMock()
        mock_session.search_notes = AsyncMock(return_value=mock_error)

        with patch.object(mcp_server, "_session", mock_session):
            result = await mcp_server.search_notes(keyword="test")

        assert result["code"] == "LOGIN_EXPIRED"

    async def test_get_note_detail_passes_through_crawl_failed(self):
        """session 返回 CRAWL_FAILED 应被透传。"""
        mock_error = {
            "error": True,
            "code": "CRAWL_FAILED",
            "message": "采集失败",
            "action": "请检查 URL",
        }
        mock_session = AsyncMock()
        mock_session.get_note_detail = AsyncMock(return_value=mock_error)

        with patch.object(mcp_server, "_session", mock_session):
            result = await mcp_server.get_note_detail(
                note_url="https://www.xiaohongshu.com/explore/abc123"
            )

        assert result["code"] == "CRAWL_FAILED"


class TestFileLogging:
    """D5: 日志文件输出配置。"""

    def test_setup_file_logging_creates_handler(self):
        """setup_file_logging 应向 root logger 添加 RotatingFileHandler。"""
        from logging.handlers import RotatingFileHandler

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / "logs"
            mcp_server.setup_file_logging(log_dir=log_dir)

            root_logger = logging.getLogger()
            # 查找我们添加的 file handler
            file_handlers = [
                h for h in root_logger.handlers
                if isinstance(h, RotatingFileHandler)
            ]
            assert len(file_handlers) >= 1

            # 验证日志文件已创建
            log_files = list(log_dir.glob("*.log"))
            assert len(log_files) >= 1

            # 清理：移除我们添加的 handler
            for h in file_handlers:
                root_logger.removeHandler(h)
                h.close()

    def test_setup_file_logging_creates_log_directory(self):
        """setup_file_logging 应自动创建日志目录。"""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / "nested" / "logs"
            assert not log_dir.exists()

            mcp_server.setup_file_logging(log_dir=log_dir)

            assert log_dir.exists()

            # 清理
            from logging.handlers import RotatingFileHandler
            root_logger = logging.getLogger()
            for h in list(root_logger.handlers):
                if isinstance(h, RotatingFileHandler):
                    root_logger.removeHandler(h)
                    h.close()

    def test_log_message_appears_in_file(self):
        """写入的日志应出现在文件中。"""
        from logging.handlers import RotatingFileHandler

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / "logs"
            mcp_server.setup_file_logging(log_dir=log_dir)

            # 使用 root logger 直接写入，避免子 logger 传播问题
            root_logger = logging.getLogger()
            root_logger.info("测试日志写入验证")

            # 强制 flush
            file_handlers = [
                h for h in root_logger.handlers
                if isinstance(h, RotatingFileHandler)
            ]
            for h in file_handlers:
                h.flush()

            log_file = log_dir / "mcp_server.log"
            content = log_file.read_text(encoding="utf-8")
            assert "测试日志写入验证" in content

            # 清理
            for h in file_handlers:
                root_logger.removeHandler(h)
                h.close()
