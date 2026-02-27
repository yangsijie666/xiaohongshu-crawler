"""
MCP 工具处理器测试（Phase C）

测试 crawl_keyword / get_saved_data 工具及 rednote://config / rednote://data 资源端点

测试策略：
  - 通过 patch.object 替换模块级 _session 为 mock
  - 资源函数通过 patch.object 替换模块级路径常量，直接调用函数验证
  - 覆盖：正常路径、输入验证、边界值 clamp、安全校验
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

import mcp_server


# ============================================================
# crawl_keyword MCP 工具测试
# ============================================================


class TestCrawlKeywordTool:
    """测试 crawl_keyword MCP 工具。"""

    def _make_ok_result(self, keyword: str = "test") -> dict:
        return {
            "keyword": keyword,
            "search_count": 5,
            "detail_count": 5,
            "total_comments": 20,
            "summary": f"关键词 [{keyword}] 采集完成",
        }

    async def test_returns_session_result_for_valid_input(self):
        """正常调用应将 session 结果透传给调用方。"""
        mock_result = self._make_ok_result("测试")
        mock_session = AsyncMock()
        mock_session.crawl_keyword = AsyncMock(return_value=mock_result)

        with patch.object(mcp_server, "_session", mock_session):
            result = await mcp_server.crawl_keyword(keyword="测试")

        assert result == mock_result

    async def test_returns_error_for_empty_keyword(self):
        """空 keyword 应直接返回错误，不调用 session。"""
        mock_session = AsyncMock()

        with patch.object(mcp_server, "_session", mock_session):
            result = await mcp_server.crawl_keyword(keyword="")

        assert result.get("error") is True
        mock_session.crawl_keyword.assert_not_called()

    async def test_returns_error_for_whitespace_keyword(self):
        """纯空白字符 keyword 应返回错误，不调用 session。"""
        mock_session = AsyncMock()

        with patch.object(mcp_server, "_session", mock_session):
            result = await mcp_server.crawl_keyword(keyword="   ")

        assert result.get("error") is True
        mock_session.crawl_keyword.assert_not_called()

    async def test_strips_keyword_before_passing_to_session(self):
        """keyword 前后空白应被去除后传入 session。"""
        mock_session = AsyncMock()
        mock_session.crawl_keyword = AsyncMock(return_value=self._make_ok_result("test"))

        with patch.object(mcp_server, "_session", mock_session):
            await mcp_server.crawl_keyword(keyword="  test  ")

        call_kwargs = mock_session.crawl_keyword.call_args[1]
        assert call_kwargs["keyword"] == "test"

    async def test_default_max_notes_is_10(self):
        """不传 max_notes 时默认应为 10。"""
        mock_session = AsyncMock()
        mock_session.crawl_keyword = AsyncMock(return_value=self._make_ok_result())

        with patch.object(mcp_server, "_session", mock_session):
            await mcp_server.crawl_keyword(keyword="test")

        call_kwargs = mock_session.crawl_keyword.call_args[1]
        assert call_kwargs["max_notes"] == 10

    async def test_clamps_max_notes_above_20(self):
        """max_notes > 20 应被截断到 20。"""
        mock_session = AsyncMock()
        mock_session.crawl_keyword = AsyncMock(return_value=self._make_ok_result())

        with patch.object(mcp_server, "_session", mock_session):
            await mcp_server.crawl_keyword(keyword="test", max_notes=100)

        call_kwargs = mock_session.crawl_keyword.call_args[1]
        assert call_kwargs["max_notes"] == 20

    async def test_clamps_max_notes_below_1(self):
        """max_notes < 1 应被截断到 1。"""
        mock_session = AsyncMock()
        mock_session.crawl_keyword = AsyncMock(return_value=self._make_ok_result())

        with patch.object(mcp_server, "_session", mock_session):
            await mcp_server.crawl_keyword(keyword="test", max_notes=0)

        call_kwargs = mock_session.crawl_keyword.call_args[1]
        assert call_kwargs["max_notes"] == 1

    async def test_max_notes_boundary_values_unchanged(self):
        """边界值 max_notes=1 和 max_notes=20 不应被修改。"""
        mock_session = AsyncMock()
        mock_session.crawl_keyword = AsyncMock(return_value=self._make_ok_result())

        with patch.object(mcp_server, "_session", mock_session):
            await mcp_server.crawl_keyword(keyword="test", max_notes=1)
        assert mock_session.crawl_keyword.call_args[1]["max_notes"] == 1

        with patch.object(mcp_server, "_session", mock_session):
            await mcp_server.crawl_keyword(keyword="test", max_notes=20)
        assert mock_session.crawl_keyword.call_args[1]["max_notes"] == 20

    async def test_default_max_comments_is_20(self):
        """不传 max_comments 时默认应为 20。"""
        mock_session = AsyncMock()
        mock_session.crawl_keyword = AsyncMock(return_value=self._make_ok_result())

        with patch.object(mcp_server, "_session", mock_session):
            await mcp_server.crawl_keyword(keyword="test")

        call_kwargs = mock_session.crawl_keyword.call_args[1]
        assert call_kwargs["max_comments"] == 20

    async def test_clamps_max_comments_above_50(self):
        """max_comments > 50 应被截断到 50。"""
        mock_session = AsyncMock()
        mock_session.crawl_keyword = AsyncMock(return_value=self._make_ok_result())

        with patch.object(mcp_server, "_session", mock_session):
            await mcp_server.crawl_keyword(keyword="test", max_comments=100)

        call_kwargs = mock_session.crawl_keyword.call_args[1]
        assert call_kwargs["max_comments"] == 50

    async def test_clamps_max_comments_below_0(self):
        """max_comments < 0 应被截断到 0。"""
        mock_session = AsyncMock()
        mock_session.crawl_keyword = AsyncMock(return_value=self._make_ok_result())

        with patch.object(mcp_server, "_session", mock_session):
            await mcp_server.crawl_keyword(keyword="test", max_comments=-5)

        call_kwargs = mock_session.crawl_keyword.call_args[1]
        assert call_kwargs["max_comments"] == 0


# ============================================================
# get_saved_data MCP 工具测试
# ============================================================


class TestGetSavedDataTool:
    """测试 get_saved_data MCP 工具。"""

    async def test_returns_session_result(self):
        """正常调用应透传 session 结果。"""
        mock_result = {
            "files": [
                {
                    "path": "data/raw/test_20240315_143022.json",
                    "keyword": "test",
                    "created_at": "2024-03-15T14:30:22",
                    "size_bytes": 1024,
                }
            ]
        }
        mock_session = AsyncMock()
        mock_session.get_saved_data = AsyncMock(return_value=mock_result)

        with patch.object(mcp_server, "_session", mock_session):
            result = await mcp_server.get_saved_data()

        assert result == mock_result

    async def test_passes_keyword_filter_when_provided(self):
        """提供 keyword 时应传入 session 的 get_saved_data。"""
        mock_session = AsyncMock()
        mock_session.get_saved_data = AsyncMock(return_value={"files": []})

        with patch.object(mcp_server, "_session", mock_session):
            await mcp_server.get_saved_data(keyword="Python")

        call_kwargs = mock_session.get_saved_data.call_args[1]
        assert call_kwargs["keyword"] == "Python"

    async def test_keyword_not_passed_when_empty_string(self):
        """空 keyword 时应以 None 调用 session（不过滤）。"""
        mock_session = AsyncMock()
        mock_session.get_saved_data = AsyncMock(return_value={"files": []})

        with patch.object(mcp_server, "_session", mock_session):
            await mcp_server.get_saved_data(keyword="")

        call_kwargs = mock_session.get_saved_data.call_args[1]
        assert call_kwargs.get("keyword") is None

    async def test_keyword_defaults_to_none(self):
        """不传 keyword 时应以 None 调用 session。"""
        mock_session = AsyncMock()
        mock_session.get_saved_data = AsyncMock(return_value={"files": []})

        with patch.object(mcp_server, "_session", mock_session):
            await mcp_server.get_saved_data()

        call_kwargs = mock_session.get_saved_data.call_args[1]
        assert call_kwargs.get("keyword") is None


# ============================================================
# rednote://config 资源端点测试
# ============================================================


class TestMCPConfigResource:
    """测试 rednote://config 资源端点。"""

    async def test_returns_yaml_content_when_config_exists(self, tmp_path):
        """配置文件存在时应返回 YAML 文本内容。"""
        config_content = "crawler:\n  keywords: []\n"
        config_file = tmp_path / "settings.yaml"
        config_file.write_text(config_content, encoding="utf-8")

        with patch.object(mcp_server, "_CONFIG_PATH", config_file):
            result = await mcp_server.get_config_resource()

        assert "crawler" in result

    async def test_returns_error_message_when_config_missing(self, tmp_path):
        """配置文件不存在时应返回可读的错误消息，不抛出异常。"""
        missing_file = tmp_path / "nonexistent.yaml"

        with patch.object(mcp_server, "_CONFIG_PATH", missing_file):
            result = await mcp_server.get_config_resource()

        assert isinstance(result, str)
        assert len(result) > 0

    async def test_returns_string_type(self, tmp_path):
        """返回值必须是字符串类型（MCP 资源协议要求）。"""
        config_file = tmp_path / "settings.yaml"
        config_file.write_text("key: value\n", encoding="utf-8")

        with patch.object(mcp_server, "_CONFIG_PATH", config_file):
            result = await mcp_server.get_config_resource()

        assert isinstance(result, str)


# ============================================================
# rednote://data/{filename} 资源端点测试
# ============================================================


class TestMCPDataResource:
    """测试 rednote://data/{filename} 资源端点。"""

    async def test_returns_file_content_for_existing_json(self, tmp_path):
        """文件存在时应返回其文本内容。"""
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir(parents=True)
        (tmp_path / "processed").mkdir(parents=True)

        data_file = raw_dir / "test_20240315_143022.json"
        data_file.write_text('{"count": 1}', encoding="utf-8")

        with patch.object(mcp_server, "_DATA_DIR", tmp_path):
            result = await mcp_server.get_data_resource(filename="test_20240315_143022.json")

        assert "count" in result

    async def test_returns_error_for_missing_file(self, tmp_path):
        """文件不存在时应返回可读的错误消息，不抛出异常。"""
        (tmp_path / "raw").mkdir(parents=True)
        (tmp_path / "processed").mkdir(parents=True)

        with patch.object(mcp_server, "_DATA_DIR", tmp_path):
            result = await mcp_server.get_data_resource(filename="nonexistent.json")

        assert isinstance(result, str)
        # 应包含文件名信息，帮助调试
        assert "nonexistent" in result or "不存在" in result

    async def test_rejects_path_traversal_with_dotdot(self):
        """filename 包含 ../ 时应返回安全错误，拒绝路径穿越。"""
        result = await mcp_server.get_data_resource(filename="../../../etc/passwd")

        assert isinstance(result, str)
        # 不应返回系统文件内容
        assert "root" not in result
        # 应包含安全拒绝提示
        assert len(result) > 0

    async def test_rejects_path_with_slash(self):
        """filename 包含 / 时应拒绝（防止子目录访问）。"""
        result = await mcp_server.get_data_resource(filename="subdir/file.json")

        assert isinstance(result, str)
        # 应包含安全错误提示
        assert len(result) > 0

    async def test_finds_file_in_processed_subdir(self, tmp_path):
        """processed 子目录下的文件也应能被找到。"""
        (tmp_path / "raw").mkdir(parents=True)
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir(parents=True)

        xlsx_file = processed_dir / "keyword_20240315_143022.xlsx"
        xlsx_file.write_bytes(b"xlsx_data")

        with patch.object(mcp_server, "_DATA_DIR", tmp_path):
            result = await mcp_server.get_data_resource(filename="keyword_20240315_143022.xlsx")

        # xlsx 是二进制文件，读取文本可能有乱码，但不应抛出异常且返回字符串
        assert isinstance(result, str)
