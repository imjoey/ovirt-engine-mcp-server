#!/usr/bin/env python3
"""Tests for OvirtMCP class."""
import pytest
from unittest.mock import MagicMock, patch

from src.config import Config


@pytest.fixture
def mock_config():
    """Create a mock Config."""
    return Config(
        ovirt_engine_url="https://ovirt.test",
        ovirt_engine_user="admin@internal",
        ovirt_engine_password="test",
    )


class TestOvirtMCPConnection:
    """Tests for OvirtMCP connection handling."""

    def test_init_with_config(self, mock_config):
        from src.ovirt_mcp import OvirtMCP

        mcp = OvirtMCP(mock_config)
        assert mcp.config == mock_config
        assert mcp.connection is None
        assert mcp.connected is False

    @patch("src.ovirt_mcp.Connection")
    def test_connect_success(self, mock_conn_class, mock_config):
        from src.ovirt_mcp import OvirtMCP

        mock_conn = MagicMock()
        mock_conn.test.return_value = True
        mock_conn_class.return_value = mock_conn

        mcp = OvirtMCP(mock_config)
        result = mcp.connect()

        assert result is True
        assert mcp.connected is True

    @patch("src.ovirt_mcp.Connection")
    def test_connect_failure(self, mock_conn_class, mock_config):
        from src.ovirt_mcp import OvirtMCP

        mock_conn_class.side_effect = Exception("Connection refused")

        mcp = OvirtMCP(mock_config)
        result = mcp.connect()

        assert result is False
        assert mcp.connected is False

    @patch("src.ovirt_mcp.Connection")
    def test_is_connected(self, mock_conn_class, mock_config):
        from src.ovirt_mcp import OvirtMCP

        mock_conn = MagicMock()
        mock_conn.test.return_value = True
        mock_conn_class.return_value = mock_conn

        mcp = OvirtMCP(mock_config)
        assert mcp.is_connected() is False

        mcp.connect()
        assert mcp.is_connected() is True


class TestOvirtMCPVMOperations:
    """Tests for VM-related operations."""

    @patch("src.ovirt_mcp.Connection")
    def test_list_vms_empty(self, mock_conn_class, mock_config):
        from src.ovirt_mcp import OvirtMCP

        mock_conn = MagicMock()
        mock_conn.test.return_value = True
        mock_vms_service = MagicMock()
        mock_vms_service.list.return_value = []
        mock_conn.system_service.return_value.vms_service.return_value = mock_vms_service
        mock_conn_class.return_value = mock_conn

        mcp = OvirtMCP(mock_config)
        mcp.connect()
        assert mcp.list_vms() == []

    @patch("src.ovirt_mcp.Connection")
    def test_start_vm(self, mock_conn_class, mock_config):
        from src.ovirt_mcp import OvirtMCP

        mock_vm = MagicMock()
        mock_vm.id = "vm-123"
        mock_vm.name = "test-vm"

        mock_conn = MagicMock()
        mock_conn.test.return_value = True
        mock_vms_service = MagicMock()
        mock_vms_service.list.return_value = [mock_vm]
        mock_vm_service = MagicMock()
        mock_conn.system_service.return_value.vms_service.return_value = mock_vms_service
        mock_conn.system_service.return_value.vms_service.return_value.vm_service.return_value = mock_vm_service
        mock_conn_class.return_value = mock_conn

        mcp = OvirtMCP(mock_config)
        mcp.connect()
        result = mcp.start_vm("test-vm")
        assert result["success"] is True


class TestOvirtMCPHostOperations:
    """Tests for host-related operations."""

    @patch("src.ovirt_mcp.Connection")
    def test_list_hosts_empty(self, mock_conn_class, mock_config):
        from src.ovirt_mcp import OvirtMCP

        mock_conn = MagicMock()
        mock_conn.test.return_value = True
        mock_hosts_service = MagicMock()
        mock_hosts_service.list.return_value = []
        mock_conn.system_service.return_value.hosts_service.return_value = mock_hosts_service
        mock_conn_class.return_value = mock_conn

        mcp = OvirtMCP(mock_config)
        mcp.connect()
        assert mcp.list_hosts() == []


class TestValidation:
    """Tests for input validation."""

    def test_validate_name_ok(self):
        from src.validation import validate_name
        assert validate_name("test-vm") == "test-vm"

    def test_validate_name_empty(self):
        from src.validation import validate_name, ValidationError
        with pytest.raises(ValidationError):
            validate_name("")

    def test_validate_name_or_id(self):
        from src.validation import validate_name_or_id
        assert validate_name_or_id("vm-123") == "vm-123"

    def test_validate_positive_int(self):
        from src.validation import validate_positive_int
        assert validate_positive_int(4096, "memory") == 4096

    def test_validate_positive_int_too_small(self):
        from src.validation import validate_positive_int, ValidationError
        with pytest.raises(ValidationError):
            validate_positive_int(0, "memory", min_val=1)

    def test_validate_tool_args_no_rules(self):
        from src.validation import validate_tool_args
        args = {"name_or_id": "test"}
        assert validate_tool_args("vm_start", args) == args


class TestErrors:
    """Tests for error types."""

    def test_ovirt_mcp_error(self):
        from src.errors import OvirtMCPError
        err = OvirtMCPError("test", code="TEST", retryable=True)
        assert err.code == "TEST"
        assert err.retryable is True
        assert err.to_dict()["error"] is True

    def test_connection_error(self):
        from src.errors import OvirtConnectionError
        err = OvirtConnectionError()
        assert err.code == "CONNECTION_ERROR"
        assert err.retryable is True

    def test_not_found_error(self):
        from src.errors import NotFoundError
        err = NotFoundError("not here")
        assert err.retryable is False

    def test_timeout_error(self):
        from src.errors import OvirtTimeoutError
        err = OvirtTimeoutError()
        assert err.retryable is True
