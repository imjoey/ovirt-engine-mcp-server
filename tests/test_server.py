"""Tests for MCP server tool registration."""
import pytest
from unittest.mock import MagicMock, patch

from ovirt_engine_mcp_server.config import Config


@pytest.fixture
def mock_config():
    return Config(
        ovirt_engine_url="https://ovirt.test",
        ovirt_engine_user="admin@internal",
        ovirt_engine_password="test",
    )


# 检查 mcp 模块是否可用
try:
    import mcp
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False


@pytest.mark.skipif(not MCP_AVAILABLE, reason="mcp module not installed")
@patch("ovirt_engine_mcp_server.ovirt_mcp.Connection")
class TestOvirtMCPServer:
    """Tests for the MCP server."""

    def test_tool_registration(self, mock_conn_class, mock_config):
        from ovirt_engine_mcp_server.server import OvirtMCPServer

        mock_conn = MagicMock()
        mock_conn.test.return_value = True
        mock_conn_class.return_value = mock_conn

        server = OvirtMCPServer(mock_config)
        # Should have registered all tools from MCP_TOOLS
        assert len(server.tool_handlers) > 20

    def test_core_tools_present(self, mock_conn_class, mock_config):
        from ovirt_engine_mcp_server.server import OvirtMCPServer

        mock_conn = MagicMock()
        mock_conn.test.return_value = True
        mock_conn_class.return_value = mock_conn

        server = OvirtMCPServer(mock_config)

        core_tools = [
            "vm_list", "vm_create", "vm_start", "vm_stop", "vm_delete",
            "host_list", "cluster_list", "network_list", "storage_list",
            "template_list", "snapshot_list", "disk_list",
        ]
        for tool in core_tools:
            assert tool in server.tool_handlers, f"Missing tool: {tool}"

    def test_all_tools_have_descriptions(self, mock_conn_class, mock_config):
        from ovirt_engine_mcp_server.server import OvirtMCPServer

        mock_conn = MagicMock()
        mock_conn.test.return_value = True
        mock_conn_class.return_value = mock_conn

        server = OvirtMCPServer(mock_config)

        for tool_name in server.tool_handlers:
            assert tool_name in server.tool_descriptions, \
                f"Tool {tool_name} missing description"

    def test_all_tools_have_schemas(self, mock_conn_class, mock_config):
        from ovirt_engine_mcp_server.server import OvirtMCPServer, TOOL_SCHEMAS, DEFAULT_SCHEMA

        mock_conn = MagicMock()
        mock_conn.test.return_value = True
        mock_conn_class.return_value = mock_conn

        server = OvirtMCPServer(mock_config)

        for tool_name in server.tool_descriptions:
            schema = TOOL_SCHEMAS.get(tool_name, DEFAULT_SCHEMA)
            assert schema["type"] == "object"
            assert "properties" in schema

    def test_format_result_none(self, mock_conn_class, mock_config):
        from ovirt_engine_mcp_server.server import OvirtMCPServer

        result = OvirtMCPServer._format_result(None)
        assert "成功" in result

    def test_format_result_string(self, mock_conn_class, mock_config):
        from ovirt_engine_mcp_server.server import OvirtMCPServer

        result = OvirtMCPServer._format_result("hello")
        assert result == "hello"

    def test_format_result_dict_success(self, mock_conn_class, mock_config):
        from ovirt_engine_mcp_server.server import OvirtMCPServer

        result = OvirtMCPServer._format_result({"success": True, "message": "done"})
        assert "done" in result

    def test_format_result_dict_error(self, mock_conn_class, mock_config):
        from ovirt_engine_mcp_server.server import OvirtMCPServer

        result = OvirtMCPServer._format_result({"error": "not found"})
        assert "not found" in result
