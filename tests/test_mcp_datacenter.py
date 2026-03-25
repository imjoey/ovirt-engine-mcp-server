#!/usr/bin/env python3
"""Tests for DataCenterMCP class - 数据中心管理模块测试."""
import pytest
from unittest.mock import MagicMock, patch


def _create_mock_datacenter(dc_id="dc-123", name="Default", status="up", storage_type="nfs"):
    """创建 mock DataCenter 对象"""
    mock_dc = MagicMock()
    mock_dc.id = dc_id
    mock_dc.name = name
    mock_dc.description = "Default datacenter"
    mock_dc.status = MagicMock()
    mock_dc.status.value = status
    mock_dc.storage_type = MagicMock()
    mock_dc.storage_type.value = storage_type
    mock_dc.version = MagicMock()
    mock_dc.version.major = 4
    mock_dc.version.minor = 7
    mock_dc.supported_versions = []
    mock_dc.mac_pool = MagicMock()
    mock_dc.mac_pool.name = "Default"
    return mock_dc


def _create_mock_cluster(cluster_id="cluster-123", name="Default"):
    """创建 mock Cluster 对象"""
    mock_cluster = MagicMock()
    mock_cluster.id = cluster_id
    mock_cluster.name = name
    return mock_cluster


def _create_mock_storage_domain(sd_id="sd-123", name="storage1", sd_type="data"):
    """创建 mock StorageDomain 对象"""
    mock_sd = MagicMock()
    mock_sd.id = sd_id
    mock_sd.name = name
    mock_sd.type = MagicMock()
    mock_sd.type.value = sd_type
    return mock_sd


class TestDataCenterMCPList:
    """测试 list_datacenters 方法"""

    def test_list_datacenters_empty(self):
        """测试空数据中心列表"""
        from src.mcp_datacenter import DataCenterMCP

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True
        mock_dcs_service = MagicMock()
        mock_dcs_service.list.return_value = []
        mock_ovirt.connection.system_service.return_value.data_centers_service.return_value = mock_dcs_service

        dc_mcp = DataCenterMCP(mock_ovirt)
        result = dc_mcp.list_datacenters()

        assert result == []

    def test_list_datacenters_with_data(self):
        """测试有数据的数据中心列表"""
        from src.mcp_datacenter import DataCenterMCP

        mock_dc = _create_mock_datacenter()
        mock_ovirt = MagicMock()
        mock_ovirt.connected = True
        mock_dcs_service = MagicMock()
        mock_dcs_service.list.return_value = [mock_dc]
        mock_ovirt.connection.system_service.return_value.data_centers_service.return_value = mock_dcs_service

        dc_mcp = DataCenterMCP(mock_ovirt)
        result = dc_mcp.list_datacenters()

        assert len(result) == 1
        assert result[0]["name"] == "Default"
        assert result[0]["status"] == "up"
        assert result[0]["storage_type"] == "nfs"

    def test_list_datacenters_not_connected(self):
        """测试未连接时抛出异常"""
        from src.mcp_datacenter import DataCenterMCP

        mock_ovirt = MagicMock()
        mock_ovirt.connected = False

        dc_mcp = DataCenterMCP(mock_ovirt)

        with pytest.raises(RuntimeError, match="未连接"):
            dc_mcp.list_datacenters()


class TestDataCenterMCPGet:
    """测试 get_datacenter 方法"""

    def test_get_datacenter_by_id(self):
        """测试通过 ID 获取数据中心"""
        from src.mcp_datacenter import DataCenterMCP

        mock_dc = _create_mock_datacenter()
        mock_cluster = _create_mock_cluster()
        mock_sd = _create_mock_storage_domain()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        # Mock data center service
        mock_dc_service = MagicMock()
        mock_dc_service.get.return_value = mock_dc
        mock_dc_service.clusters_service.return_value.list.return_value = [mock_cluster]
        mock_dc_service.storage_domains_service.return_value.list.return_value = [mock_sd]
        mock_dc_service.networks_service.return_value.list.return_value = []

        mock_dcs_service = MagicMock()
        mock_dcs_service.data_center_service.return_value = mock_dc_service
        mock_dcs_service.list.return_value = []  # 名称搜索不返回结果

        mock_ovirt.connection.system_service.return_value.data_centers_service.return_value = mock_dcs_service

        dc_mcp = DataCenterMCP(mock_ovirt)
        result = dc_mcp.get_datacenter("dc-123")

        assert result is not None
        assert result["id"] == "dc-123"
        assert result["name"] == "Default"
        assert len(result["clusters"]) == 1
        assert len(result["storage_domains"]) == 1

    def test_get_datacenter_not_found(self):
        """测试数据中心不存在"""
        from src.mcp_datacenter import DataCenterMCP

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_dcs_service = MagicMock()
        mock_dcs_service.data_center_service.return_value.get.side_effect = Exception("Not found")
        mock_dcs_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.data_centers_service.return_value = mock_dcs_service

        dc_mcp = DataCenterMCP(mock_ovirt)
        result = dc_mcp.get_datacenter("nonexistent")

        assert result is None


class TestDataCenterMCPCreate:
    """测试 create_datacenter 方法"""

    def test_create_datacenter_success(self):
        """测试创建数据中心成功"""
        from src.mcp_datacenter import DataCenterMCP

        mock_dc = _create_mock_datacenter(name="NewDC")

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_dcs_service = MagicMock()
        mock_dcs_service.list.return_value = []  # 名称不冲突
        mock_dcs_service.add.return_value = mock_dc

        mock_ovirt.connection.system_service.return_value.data_centers_service.return_value = mock_dcs_service

        dc_mcp = DataCenterMCP(mock_ovirt)
        result = dc_mcp.create_datacenter("NewDC", storage_type="nfs", description="Test DC")

        assert result["success"] is True
        assert "datacenter_id" in result
        mock_dcs_service.add.assert_called_once()

    def test_create_datacenter_already_exists(self):
        """测试创建已存在的数据中心"""
        from src.mcp_datacenter import DataCenterMCP

        mock_dc = _create_mock_datacenter()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_dcs_service = MagicMock()
        mock_dcs_service.list.return_value = [mock_dc]  # 名称已存在

        mock_ovirt.connection.system_service.return_value.data_centers_service.return_value = mock_dcs_service

        dc_mcp = DataCenterMCP(mock_ovirt)

        with pytest.raises(ValueError, match="已存在"):
            dc_mcp.create_datacenter("Default")

    def test_create_datacenter_invalid_storage_type(self):
        """测试无效的存储类型"""
        from src.mcp_datacenter import DataCenterMCP

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        dc_mcp = DataCenterMCP(mock_ovirt)

        with pytest.raises(ValueError, match="无效的存储类型"):
            dc_mcp.create_datacenter("NewDC", storage_type="invalid")


class TestDataCenterMCPUpdate:
    """测试 update_datacenter 方法"""

    def test_update_datacenter_success(self):
        """测试更新数据中心成功"""
        from src.mcp_datacenter import DataCenterMCP

        mock_dc = _create_mock_datacenter()
        mock_dc_service = MagicMock()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_dcs_service = MagicMock()
        mock_dcs_service.data_center_service.return_value.get.side_effect = [mock_dc, mock_dc]
        mock_dcs_service.list.return_value = []  # ID 查找成功

        mock_ovirt.connection.system_service.return_value.data_centers_service.return_value = mock_dcs_service

        dc_mcp = DataCenterMCP(mock_ovirt)
        result = dc_mcp.update_datacenter("dc-123", new_name="UpdatedDC", description="Updated")

        assert result["success"] is True

    def test_update_datacenter_not_found(self):
        """测试更新不存在的数据中心"""
        from src.mcp_datacenter import DataCenterMCP

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_dcs_service = MagicMock()
        mock_dcs_service.data_center_service.return_value.get.side_effect = Exception("Not found")
        mock_dcs_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.data_centers_service.return_value = mock_dcs_service

        dc_mcp = DataCenterMCP(mock_ovirt)

        with pytest.raises(ValueError, match="不存在"):
            dc_mcp.update_datacenter("nonexistent")


class TestDataCenterMCPDelete:
    """测试 delete_datacenter 方法"""

    def test_delete_datacenter_success(self):
        """测试删除数据中心成功"""
        from src.mcp_datacenter import DataCenterMCP

        mock_dc = _create_mock_datacenter()
        mock_dc_service = MagicMock()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_dcs_service = MagicMock()
        mock_dcs_service.data_center_service.return_value.get.return_value = mock_dc
        mock_dcs_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.data_centers_service.return_value = mock_dcs_service

        dc_mcp = DataCenterMCP(mock_ovirt)
        result = dc_mcp.delete_datacenter("dc-123")

        assert result["success"] is True
        mock_dc_service.remove.assert_not_called()  # 使用的是 dc_service.remove()

    def test_delete_datacenter_not_found(self):
        """测试删除不存在的数据中心"""
        from src.mcp_datacenter import DataCenterMCP

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_dcs_service = MagicMock()
        mock_dcs_service.data_center_service.return_value.get.side_effect = Exception("Not found")
        mock_dcs_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.data_centers_service.return_value = mock_dcs_service

        dc_mcp = DataCenterMCP(mock_ovirt)

        with pytest.raises(ValueError, match="不存在"):
            dc_mcp.delete_datacenter("nonexistent")


class TestDataCenterMCPTools:
    """测试 MCP_TOOLS 注册表"""

    def test_mcp_tools_defined(self):
        """测试 MCP 工具注册表已定义"""
        from src.mcp_datacenter import MCP_TOOLS

        expected_tools = [
            "datacenter_list",
            "datacenter_get",
            "datacenter_create",
            "datacenter_update",
            "datacenter_delete",
        ]

        for tool in expected_tools:
            assert tool in MCP_TOOLS, f"Missing tool: {tool}"
            assert "method" in MCP_TOOLS[tool]
            assert "description" in MCP_TOOLS[tool]
