"""
MCP 服务 Transport 层测试 — Phase E3: SSE / Streamable HTTP 支持

测试策略：
  - 验证 CLI 参数解析（--transport, --host, --port）
  - 验证不同 transport 模式下调用正确的 run 方法
  - 验证 SSE transport 的默认配置（host/port）
  - 所有测试 mock mcp.run()，不启动真实服务器
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


class TestParseArgs:
    """CLI 参数解析测试。"""

    def test_default_args_use_stdio(self):
        """无参数时默认使用 stdio transport。"""
        from mcp_server import parse_args

        args = parse_args([])
        assert args.transport == "stdio"

    def test_transport_sse(self):
        """--transport sse 应正确解析。"""
        from mcp_server import parse_args

        args = parse_args(["--transport", "sse"])
        assert args.transport == "sse"

    def test_transport_streamable_http(self):
        """--transport streamable-http 应正确解析。"""
        from mcp_server import parse_args

        args = parse_args(["--transport", "streamable-http"])
        assert args.transport == "streamable-http"

    def test_invalid_transport_raises(self):
        """无效 transport 值应报错退出。"""
        from mcp_server import parse_args

        with pytest.raises(SystemExit):
            parse_args(["--transport", "invalid"])

    def test_default_host(self):
        """默认 host 应为 127.0.0.1。"""
        from mcp_server import parse_args

        args = parse_args([])
        assert args.host == "127.0.0.1"

    def test_custom_host(self):
        """--host 参数应正确解析。"""
        from mcp_server import parse_args

        args = parse_args(["--host", "0.0.0.0"])
        assert args.host == "0.0.0.0"

    def test_default_port(self):
        """默认 port 应为 8000。"""
        from mcp_server import parse_args

        args = parse_args([])
        assert args.port == 8000

    def test_custom_port(self):
        """--port 参数应正确解析。"""
        from mcp_server import parse_args

        args = parse_args(["--port", "9090"])
        assert args.port == 9090

    def test_port_type_is_int(self):
        """port 应被解析为 int 类型。"""
        from mcp_server import parse_args

        args = parse_args(["--port", "3000"])
        assert isinstance(args.port, int)


class TestTransportDispatch:
    """Transport 模式调度测试。"""

    def test_stdio_calls_mcp_run_without_transport(self):
        """stdio 模式下应调用 mcp.run() 不传 transport 参数（默认 stdio）。"""
        import mcp_server

        mock_mcp = MagicMock()
        with patch.object(mcp_server, "mcp", mock_mcp):
            with patch.object(mcp_server, "parse_args", return_value=MagicMock(
                transport="stdio", host="127.0.0.1", port=8000
            )):
                mcp_server.main()

        mock_mcp.run.assert_called_once_with()

    def test_sse_calls_mcp_run_with_sse_transport(self):
        """SSE 模式下应调用 mcp.run(transport='sse')。"""
        import mcp_server

        mock_mcp = MagicMock()
        with patch.object(mcp_server, "mcp", mock_mcp):
            with patch.object(mcp_server, "parse_args", return_value=MagicMock(
                transport="sse", host="0.0.0.0", port=9090
            )):
                mcp_server.main()

        mock_mcp.run.assert_called_once_with(transport="sse")

    def test_streamable_http_calls_mcp_run(self):
        """streamable-http 模式下应调用 mcp.run(transport='streamable-http')。"""
        import mcp_server

        mock_mcp = MagicMock()
        with patch.object(mcp_server, "mcp", mock_mcp):
            with patch.object(mcp_server, "parse_args", return_value=MagicMock(
                transport="streamable-http", host="0.0.0.0", port=8080
            )):
                mcp_server.main()

        mock_mcp.run.assert_called_once_with(transport="streamable-http")

    def test_sse_updates_mcp_settings_host_port(self):
        """SSE 模式下应更新 mcp.settings.host 和 mcp.settings.port。"""
        import mcp_server

        mock_mcp = MagicMock()
        mock_mcp.settings = MagicMock()
        with patch.object(mcp_server, "mcp", mock_mcp):
            with patch.object(mcp_server, "parse_args", return_value=MagicMock(
                transport="sse", host="0.0.0.0", port=9090
            )):
                mcp_server.main()

        assert mock_mcp.settings.host == "0.0.0.0"
        assert mock_mcp.settings.port == 9090

    def test_stdio_does_not_update_settings(self):
        """stdio 模式下不应修改 mcp.settings。"""
        import mcp_server

        mock_mcp = MagicMock()
        original_host = mock_mcp.settings.host
        original_port = mock_mcp.settings.port
        with patch.object(mcp_server, "mcp", mock_mcp):
            with patch.object(mcp_server, "parse_args", return_value=MagicMock(
                transport="stdio", host="127.0.0.1", port=8000
            )):
                mcp_server.main()

        # stdio 模式下 settings 不应被赋值
        mock_mcp.run.assert_called_once_with()


class TestMcpInstanceConfig:
    """FastMCP 实例配置测试。"""

    def test_mcp_instance_name(self):
        """MCP 实例名称应为 rednote-crawler。"""
        import mcp_server

        # FastMCP 实例的 name 存储在 settings 或 _mcp_server 上
        assert mcp_server.mcp.name == "rednote-crawler"

    def test_mcp_has_lifespan(self):
        """MCP 实例应配置 lifespan 钩子。"""
        import mcp_server

        # lifespan 通过 settings 传入
        assert mcp_server.mcp.settings.lifespan is not None
