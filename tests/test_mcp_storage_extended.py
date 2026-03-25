#!/usr/bin/env python3
"""Tests for StorageExtendedMCP class - 存储扩展模块测试."""
import pytest
from unittest.mock import MagicMock


def _create_mock_storage_domain(sd_id="sd-123", name="storage1", sd_type="data", status="active"):
    """创建 mock StorageDomain 对象"""
    mock_sd = MagicMock()
    mock_sd.id = sd_id
    mock_sd.name = name
    mock_sd.description = "Test storage"
    mock_sd.type = MagicMock()
    mock_sd.type.value = sd_type
    mock_sd.status = MagicMock()
    mock_sd.status.value = status
    mock_sd.available = 107374182400  # 100GB
    mock_sd.used = 107374182400  # 100GB
    mock_sd.storage = MagicMock()
    mock_sd.storage.type = MagicMock()
    mock_sd.storage.type.value = "nfs"
    mock_sd.storage.data_center = MagicMock()
    mock_sd.storage.data_center.name = "Default"
    mock_sd.storage.data_center.id = "dc-123"
    mock_sd.master = False
    mock_sd.wipe_after_delete = False
    mock_sd.supports_discard = True
    return mock_sd


def _create_mock_datacenter(dc_id="dc-123", name="Default"):
    """创建 mock DataCenter 对象"""
    mock_dc = MagicMock()
    mock_dc.id = dc_id
    mock_dc.name = name
    return mock_dc


class TestStorageExtendedMCPGetStorageDomain:
    """测试 get_storage_domain 方法"""

    def test_get_storage_domain_by_id(self):
        """测试通过 ID 获取存储域"""
        from src.mcp_storage_extended import StorageExtendedMCP

        mock_sd = _create_mock_storage_domain()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_sd_service = MagicMock()
        mock_sd_service.get.return_value = mock_sd
        mock_sd_service.files_service.return_value.list.return_value = []

        mock_sds_service = MagicMock()
        mock_sds_service.storage_domain_service.return_value = mock_sd_service
        mock_sds_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.storage_domains_service.return_value = mock_sds_service

        storage_mcp = StorageExtendedMCP(mock_ovirt)
        result = storage_mcp.get_storage_domain("sd-123")

        assert result is not None
        assert result["id"] == "sd-123"
        assert result["name"] == "storage1"
        assert result["type"] == "data"

    def test_get_storage_domain_not_found(self):
        """测试存储域不存在"""
        from src.mcp_storage_extended import StorageExtendedMCP

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_sds_service = MagicMock()
        mock_sds_service.storage_domain_service.return_value.get.side_effect = Exception("Not found")
        mock_sds_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.storage_domains_service.return_value = mock_sds_service

        storage_mcp = StorageExtendedMCP(mock_ovirt)
        result = storage_mcp.get_storage_domain("nonexistent")

        assert result is None

    def test_get_storage_domain_with_files(self):
        """测试获取存储域包含文件列表"""
        from src.mcp_storage_extended import StorageExtendedMCP

        mock_sd = _create_mock_storage_domain()
        mock_file = MagicMock()
        mock_file.name = "disk1.img"
        mock_file.size = 10737418240

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_sd_service = MagicMock()
        mock_sd_service.get.return_value = mock_sd
        mock_sd_service.files_service.return_value.list.return_value = [mock_file]

        mock_sds_service = MagicMock()
        mock_sds_service.storage_domain_service.return_value = mock_sd_service
        mock_sds_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.storage_domains_service.return_value = mock_sds_service

        storage_mcp = StorageExtendedMCP(mock_ovirt)
        result = storage_mcp.get_storage_domain("sd-123")

        assert result is not None
        assert len(result["files"]) == 1
        assert result["files"][0]["name"] == "disk1.img"


class TestStorageExtendedMCPCreateStorageDomain:
    """测试 create_storage_domain 方法"""

    def test_create_storage_domain_success(self):
        """测试创建存储域成功"""
        from src.mcp_storage_extended import StorageExtendedMCP

        mock_sd = _create_mock_storage_domain()
        mock_host = MagicMock()
        mock_host.id = "host-123"

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_hosts_service = MagicMock()
        mock_hosts_service.list.return_value = [mock_host]

        mock_sds_service = MagicMock()
        mock_sds_service.list.return_value = []  # 名称不冲突
        mock_sds_service.add.return_value = mock_sd

        mock_ovirt.connection.system_service.return_value.hosts_service.return_value = mock_hosts_service
        mock_ovirt.connection.system_service.return_value.storage_domains_service.return_value = mock_sds_service

        storage_mcp = StorageExtendedMCP(mock_ovirt)
        result = storage_mcp.create_storage_domain(
            name="new-storage",
            storage_type="nfs",
            host="host1",
            path="192.168.1.100:/export/data"
        )

        assert result["success"] is True
        assert "storage_domain_id" in result

    def test_create_storage_domain_invalid_type(self):
        """测试无效的存储类型"""
        from src.mcp_storage_extended import StorageExtendedMCP

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        storage_mcp = StorageExtendedMCP(mock_ovirt)

        with pytest.raises(ValueError, match="无效的存储类型"):
            storage_mcp.create_storage_domain("new-storage", "invalid", "host1", "/path")

    def test_create_storage_domain_host_not_found(self):
        """测试主机不存在"""
        from src.mcp_storage_extended import StorageExtendedMCP

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_hosts_service = MagicMock()
        mock_hosts_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.hosts_service.return_value = mock_hosts_service

        storage_mcp = StorageExtendedMCP(mock_ovirt)

        with pytest.raises(ValueError, match="主机不存在"):
            storage_mcp.create_storage_domain("new-storage", "nfs", "nonexistent", "/path")

    def test_create_storage_domain_already_exists(self):
        """测试存储域已存在"""
        from src.mcp_storage_extended import StorageExtendedMCP

        mock_sd = _create_mock_storage_domain()
        mock_host = MagicMock()
        mock_host.id = "host-123"

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_hosts_service = MagicMock()
        mock_hosts_service.list.return_value = [mock_host]

        mock_sds_service = MagicMock()
        mock_sds_service.list.return_value = [mock_sd]  # 名称已存在

        mock_ovirt.connection.system_service.return_value.hosts_service.return_value = mock_hosts_service
        mock_ovirt.connection.system_service.return_value.storage_domains_service.return_value = mock_sds_service

        storage_mcp = StorageExtendedMCP(mock_ovirt)

        with pytest.raises(ValueError, match="已存在"):
            storage_mcp.create_storage_domain("storage1", "nfs", "host1", "/path")


class TestStorageExtendedMCPDeleteStorageDomain:
    """测试 delete_storage_domain 方法"""

    def test_delete_storage_domain_success(self):
        """测试删除存储域成功"""
        from src.mcp_storage_extended import StorageExtendedMCP

        mock_sd = _create_mock_storage_domain()
        mock_sd_service = MagicMock()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_sds_service = MagicMock()
        mock_sds_service.storage_domain_service.return_value.get.return_value = mock_sd
        mock_sds_service.storage_domain_service.return_value = mock_sd_service
        mock_sds_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.storage_domains_service.return_value = mock_sds_service
        mock_ovirt.connection.system_service.return_value.storage_domains_service.return_value.storage_domain_service.return_value = mock_sd_service
        mock_ovirt.connection.system_service.return_value.storage_domains_service.return_value.list.return_value = []

        storage_mcp = StorageExtendedMCP(mock_ovirt)
        result = storage_mcp.delete_storage_domain("sd-123")

        assert result["success"] is True

    def test_delete_storage_domain_not_found(self):
        """测试删除不存在的存储域"""
        from src.mcp_storage_extended import StorageExtendedMCP

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_sds_service = MagicMock()
        mock_sds_service.storage_domain_service.return_value.get.side_effect = Exception("Not found")
        mock_sds_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.storage_domains_service.return_value = mock_sds_service

        storage_mcp = StorageExtendedMCP(mock_ovirt)

        with pytest.raises(ValueError, match="不存在"):
            storage_mcp.delete_storage_domain("nonexistent")


class TestStorageExtendedMCPDetachStorageDomain:
    """测试 detach_storage_domain 方法"""

    def test_detach_storage_domain_success(self):
        """测试分离存储域成功"""
        from src.mcp_storage_extended import StorageExtendedMCP

        mock_sd = _create_mock_storage_domain()
        mock_dc = _create_mock_datacenter()
        mock_sd_service = MagicMock()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        # Storage domain service
        mock_sds_service = MagicMock()
        mock_sds_service.storage_domain_service.return_value.get.return_value = mock_sd
        mock_sds_service.list.return_value = []

        # Datacenter service
        mock_dcs_service = MagicMock()
        mock_dcs_service.data_center_service.return_value.get.return_value = mock_dc
        mock_dcs_service.list.return_value = []
        mock_dcs_service.data_center_service.return_value.storage_domains_service.return_value.storage_domain_service.return_value = mock_sd_service

        mock_ovirt.connection.system_service.return_value.storage_domains_service.return_value = mock_sds_service
        mock_ovirt.connection.system_service.return_value.data_centers_service.return_value = mock_dcs_service

        storage_mcp = StorageExtendedMCP(mock_ovirt)
        result = storage_mcp.detach_storage_domain("sd-123", datacenter="Default")

        assert result["success"] is True


class TestStorageExtendedMCPAttachStorageDomain:
    """测试 attach_storage_domain 方法"""

    def test_attach_storage_domain_success(self):
        """测试附加存储域成功"""
        from src.mcp_storage_extended import StorageExtendedMCP

        mock_sd = _create_mock_storage_domain()
        mock_dc = _create_mock_datacenter()
        mock_sd_service = MagicMock()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_sds_service = MagicMock()
        mock_sds_service.storage_domain_service.return_value.get.return_value = mock_sd
        mock_sds_service.list.return_value = []

        mock_dcs_service = MagicMock()
        mock_dcs_service.data_center_service.return_value.get.return_value = mock_dc
        mock_dcs_service.list.return_value = []
        mock_dcs_service.data_center_service.return_value.storage_domains_service.return_value = mock_sd_service

        mock_ovirt.connection.system_service.return_value.storage_domains_service.return_value = mock_sds_service
        mock_ovirt.connection.system_service.return_value.data_centers_service.return_value = mock_dcs_service

        storage_mcp = StorageExtendedMCP(mock_ovirt)
        result = storage_mcp.attach_storage_domain("sd-123", "Default")

        assert result["success"] is True


class TestStorageExtendedMCPGetStats:
    """测试 get_storage_domain_stats 方法"""

    def test_get_storage_domain_stats_success(self):
        """测试获取存储域统计信息成功"""
        from src.mcp_storage_extended import StorageExtendedMCP

        mock_sd = _create_mock_storage_domain()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_sds_service = MagicMock()
        mock_sds_service.storage_domain_service.return_value.get.return_value = mock_sd
        mock_sds_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.storage_domains_service.return_value = mock_sds_service

        storage_mcp = StorageExtendedMCP(mock_ovirt)
        result = storage_mcp.get_storage_domain_stats("sd-123")

        assert result["id"] == "sd-123"
        assert result["name"] == "storage1"
        assert "available_gb" in result
        assert "used_gb" in result
        assert "usage_percent" in result


class TestStorageExtendedMCPTools:
    """测试 MCP_TOOLS 注册表"""

    def test_mcp_tools_defined(self):
        """测试 MCP 工具注册表已定义"""
        from src.mcp_storage_extended import MCP_TOOLS

        expected_tools = [
            "storage_get",
            "storage_create",
            "storage_delete",
            "storage_detach",
            "storage_attach_to_dc",
            "storage_stats",
        ]

        for tool in expected_tools:
            assert tool in MCP_TOOLS, f"Missing tool: {tool}"
            assert "method" in MCP_TOOLS[tool]
            assert "description" in MCP_TOOLS[tool]
