#!/usr/bin/env python3
"""Tests for AffinityMCP class - 亲和性组管理模块测试."""
import pytest
from unittest.mock import MagicMock


def _create_mock_cluster(cluster_id="cluster-123", name="Default"):
    """创建 mock Cluster 对象"""
    mock_cluster = MagicMock()
    mock_cluster.id = cluster_id
    mock_cluster.name = name
    return mock_cluster


def _create_mock_affinity_group(group_id="ag-123", name="web-servers", positive=True, enforcing=False):
    """创建 mock AffinityGroup 对象"""
    mock_group = MagicMock()
    mock_group.id = group_id
    mock_group.name = name
    mock_group.positive = positive
    mock_group.enforcing = enforcing
    mock_group.vms = []
    return mock_group


def _create_mock_vm(vm_id="vm-123", name="test-vm"):
    """创建 mock VM 对象"""
    mock_vm = MagicMock()
    mock_vm.id = vm_id
    mock_vm.name = name
    return mock_vm


class TestAffinityMCPListAffinityGroups:
    """测试 list_affinity_groups 方法"""

    def test_list_affinity_groups_empty(self):
        """测试空亲和性组列表"""
        from src.mcp_affinity import AffinityMCP

        mock_cluster = _create_mock_cluster()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_clusters_service = MagicMock()
        mock_clusters_service.cluster_service.return_value.get.return_value = mock_cluster
        mock_clusters_service.list.return_value = [mock_cluster]

        mock_affinity_groups_service = MagicMock()
        mock_affinity_groups_service.list.return_value = []

        mock_cluster_service = MagicMock()
        mock_cluster_service.affinity_groups_service.return_value = mock_affinity_groups_service

        mock_clusters_service.cluster_service.return_value = mock_cluster_service

        mock_ovirt.connection.system_service.return_value.clusters_service.return_value = mock_clusters_service

        affinity_mcp = AffinityMCP(mock_ovirt)
        result = affinity_mcp.list_affinity_groups("Default")

        assert result == []

    def test_list_affinity_groups_with_data(self):
        """测试有数据的亲和性组列表"""
        from src.mcp_affinity import AffinityMCP

        mock_cluster = _create_mock_cluster()
        mock_group = _create_mock_affinity_group()
        mock_vm = _create_mock_vm()
        mock_group.vms = [mock_vm]

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_clusters_service = MagicMock()
        mock_clusters_service.cluster_service.return_value.get.return_value = mock_cluster
        mock_clusters_service.list.return_value = [mock_cluster]

        mock_affinity_groups_service = MagicMock()
        mock_affinity_groups_service.list.return_value = [mock_group]

        mock_cluster_service = MagicMock()
        mock_cluster_service.affinity_groups_service.return_value = mock_affinity_groups_service

        mock_clusters_service.cluster_service.return_value = mock_cluster_service

        mock_ovirt.connection.system_service.return_value.clusters_service.return_value = mock_clusters_service

        affinity_mcp = AffinityMCP(mock_ovirt)
        result = affinity_mcp.list_affinity_groups("Default")

        assert len(result) == 1
        assert result[0]["name"] == "web-servers"
        assert result[0]["positive"] is True
        assert result[0]["vm_count"] == 1

    def test_list_affinity_groups_cluster_not_found(self):
        """测试集群不存在"""
        from src.mcp_affinity import AffinityMCP

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_clusters_service = MagicMock()
        mock_clusters_service.cluster_service.return_value.get.side_effect = Exception("Not found")
        mock_clusters_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.clusters_service.return_value = mock_clusters_service

        affinity_mcp = AffinityMCP(mock_ovirt)

        with pytest.raises(ValueError, match="集群不存在"):
            affinity_mcp.list_affinity_groups("Nonexistent")


class TestAffinityMCPGetAffinityGroup:
    """测试 get_affinity_group 方法"""

    def test_get_affinity_group_by_id(self):
        """测试通过 ID 获取亲和性组"""
        from src.mcp_affinity import AffinityMCP

        mock_cluster = _create_mock_cluster()
        mock_group = _create_mock_affinity_group()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_clusters_service = MagicMock()
        mock_clusters_service.cluster_service.return_value.get.return_value = mock_cluster
        mock_clusters_service.list.return_value = [mock_cluster]

        mock_group_service = MagicMock()
        mock_group_service.get.return_value = mock_group

        mock_affinity_groups_service = MagicMock()
        mock_affinity_groups_service.affinity_group_service.return_value = mock_group_service

        mock_cluster_service = MagicMock()
        mock_cluster_service.affinity_groups_service.return_value = mock_affinity_groups_service

        mock_clusters_service.cluster_service.return_value = mock_cluster_service

        mock_ovirt.connection.system_service.return_value.clusters_service.return_value = mock_clusters_service

        affinity_mcp = AffinityMCP(mock_ovirt)
        result = affinity_mcp.get_affinity_group("Default", "ag-123")

        assert result is not None
        assert result["id"] == "ag-123"
        assert result["name"] == "web-servers"

    def test_get_affinity_group_not_found(self):
        """测试亲和性组不存在"""
        from src.mcp_affinity import AffinityMCP

        mock_cluster = _create_mock_cluster()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_clusters_service = MagicMock()
        mock_clusters_service.cluster_service.return_value.get.return_value = mock_cluster
        mock_clusters_service.list.return_value = [mock_cluster]

        mock_group_service = MagicMock()
        mock_group_service.get.side_effect = Exception("Not found")

        mock_affinity_groups_service = MagicMock()
        mock_affinity_groups_service.affinity_group_service.return_value = mock_group_service
        mock_affinity_groups_service.list.return_value = []

        mock_cluster_service = MagicMock()
        mock_cluster_service.affinity_groups_service.return_value = mock_affinity_groups_service

        mock_clusters_service.cluster_service.return_value = mock_cluster_service

        mock_ovirt.connection.system_service.return_value.clusters_service.return_value = mock_clusters_service

        affinity_mcp = AffinityMCP(mock_ovirt)
        result = affinity_mcp.get_affinity_group("Default", "nonexistent")

        assert result is None


class TestAffinityMCPCreateAffinityGroup:
    """测试 create_affinity_group 方法"""

    def test_create_affinity_group_success(self):
        """测试创建亲和性组成功"""
        from src.mcp_affinity import AffinityMCP

        mock_cluster = _create_mock_cluster()
        mock_group = _create_mock_affinity_group()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_clusters_service = MagicMock()
        mock_clusters_service.cluster_service.return_value.get.return_value = mock_cluster
        mock_clusters_service.list.return_value = [mock_cluster]

        mock_affinity_groups_service = MagicMock()
        mock_affinity_groups_service.list.return_value = []  # 名称不冲突
        mock_affinity_groups_service.add.return_value = mock_group

        mock_cluster_service = MagicMock()
        mock_cluster_service.affinity_groups_service.return_value = mock_affinity_groups_service

        mock_clusters_service.cluster_service.return_value = mock_cluster_service

        mock_ovirt.connection.system_service.return_value.clusters_service.return_value = mock_clusters_service

        affinity_mcp = AffinityMCP(mock_ovirt)
        result = affinity_mcp.create_affinity_group(
            name="db-servers",
            cluster="Default",
            positive=True,
            enforcing=True
        )

        assert result["success"] is True
        assert result["enforcing"] is True

    def test_create_affinity_group_already_exists(self):
        """测试亲和性组已存在"""
        from src.mcp_affinity import AffinityMCP

        mock_cluster = _create_mock_cluster()
        mock_group = _create_mock_affinity_group()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_clusters_service = MagicMock()
        mock_clusters_service.cluster_service.return_value.get.return_value = mock_cluster
        mock_clusters_service.list.return_value = [mock_cluster]

        mock_affinity_groups_service = MagicMock()
        mock_affinity_groups_service.list.return_value = [mock_group]  # 名称已存在

        mock_cluster_service = MagicMock()
        mock_cluster_service.affinity_groups_service.return_value = mock_affinity_groups_service

        mock_clusters_service.cluster_service.return_value = mock_cluster_service

        mock_ovirt.connection.system_service.return_value.clusters_service.return_value = mock_clusters_service

        affinity_mcp = AffinityMCP(mock_ovirt)

        with pytest.raises(ValueError, match="已存在"):
            affinity_mcp.create_affinity_group("web-servers", "Default")


class TestAffinityMCPUpdateAffinityGroup:
    """测试 update_affinity_group 方法"""

    def test_update_affinity_group_success(self):
        """测试更新亲和性组成功"""
        from src.mcp_affinity import AffinityMCP

        mock_cluster = _create_mock_cluster()
        mock_group = _create_mock_affinity_group()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_clusters_service = MagicMock()
        mock_clusters_service.cluster_service.return_value.get.return_value = mock_cluster
        mock_clusters_service.list.return_value = [mock_cluster]

        mock_group_service = MagicMock()
        mock_group_service.get.return_value = mock_group

        mock_affinity_groups_service = MagicMock()
        mock_affinity_groups_service.affinity_group_service.return_value = mock_group_service

        mock_cluster_service = MagicMock()
        mock_cluster_service.affinity_groups_service.return_value = mock_affinity_groups_service

        mock_clusters_service.cluster_service.return_value = mock_cluster_service

        mock_ovirt.connection.system_service.return_value.clusters_service.return_value = mock_clusters_service

        affinity_mcp = AffinityMCP(mock_ovirt)
        result = affinity_mcp.update_affinity_group(
            "Default",
            "ag-123",
            new_name="updated-group",
            enforcing=True
        )

        assert result["success"] is True


class TestAffinityMCPDeleteAffinityGroup:
    """测试 delete_affinity_group 方法"""

    def test_delete_affinity_group_success(self):
        """测试删除亲和性组成功"""
        from src.mcp_affinity import AffinityMCP

        mock_cluster = _create_mock_cluster()
        mock_group = _create_mock_affinity_group()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_clusters_service = MagicMock()
        mock_clusters_service.cluster_service.return_value.get.return_value = mock_cluster
        mock_clusters_service.list.return_value = [mock_cluster]

        mock_group_service = MagicMock()
        mock_group_service.get.return_value = mock_group

        mock_affinity_groups_service = MagicMock()
        mock_affinity_groups_service.affinity_group_service.return_value = mock_group_service

        mock_cluster_service = MagicMock()
        mock_cluster_service.affinity_groups_service.return_value = mock_affinity_groups_service

        mock_clusters_service.cluster_service.return_value = mock_cluster_service

        mock_ovirt.connection.system_service.return_value.clusters_service.return_value = mock_clusters_service

        affinity_mcp = AffinityMCP(mock_ovirt)
        result = affinity_mcp.delete_affinity_group("Default", "ag-123")

        assert result["success"] is True


class TestAffinityMCPAddVMToAffinityGroup:
    """测试 add_vm_to_affinity_group 方法"""

    def test_add_vm_to_affinity_group_success(self):
        """测试添加 VM 到亲和性组成功"""
        from src.mcp_affinity import AffinityMCP

        mock_cluster = _create_mock_cluster()
        mock_group = _create_mock_affinity_group()
        mock_vm = _create_mock_vm()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        # Cluster service
        mock_clusters_service = MagicMock()
        mock_clusters_service.cluster_service.return_value.get.return_value = mock_cluster
        mock_clusters_service.list.return_value = [mock_cluster]

        # VM service
        mock_vms_service = MagicMock()
        mock_vms_service.vm_service.return_value.get.return_value = mock_vm
        mock_vms_service.list.return_value = [mock_vm]

        # Group service
        mock_group_service = MagicMock()
        mock_group_service.get.return_value = mock_group

        mock_vms_in_group_service = MagicMock()

        mock_affinity_groups_service = MagicMock()
        mock_affinity_groups_service.affinity_group_service.return_value = mock_group_service
        mock_affinity_groups_service.affinity_group_service.return_value.vms_service.return_value = mock_vms_in_group_service

        mock_cluster_service = MagicMock()
        mock_cluster_service.affinity_groups_service.return_value = mock_affinity_groups_service

        mock_clusters_service.cluster_service.return_value = mock_cluster_service

        mock_ovirt.connection.system_service.return_value.clusters_service.return_value = mock_clusters_service
        mock_ovirt.connection.system_service.return_value.vms_service.return_value = mock_vms_service

        affinity_mcp = AffinityMCP(mock_ovirt)
        result = affinity_mcp.add_vm_to_affinity_group("Default", "ag-123", "test-vm")

        assert result["success"] is True


class TestAffinityMCPRemoveVMFromAffinityGroup:
    """测试 remove_vm_from_affinity_group 方法"""

    def test_remove_vm_from_affinity_group_success(self):
        """测试从亲和性组移除 VM 成功"""
        from src.mcp_affinity import AffinityMCP

        mock_cluster = _create_mock_cluster()
        mock_group = _create_mock_affinity_group()
        mock_vm = _create_mock_vm()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        # Cluster service
        mock_clusters_service = MagicMock()
        mock_clusters_service.cluster_service.return_value.get.return_value = mock_cluster
        mock_clusters_service.list.return_value = [mock_cluster]

        # VM service
        mock_vms_service = MagicMock()
        mock_vms_service.vm_service.return_value.get.return_value = mock_vm
        mock_vms_service.list.return_value = [mock_vm]

        # Group service
        mock_group_service = MagicMock()
        mock_group_service.get.return_value = mock_group

        mock_vm_in_group_service = MagicMock()

        mock_vms_in_group_service = MagicMock()
        mock_vms_in_group_service.vm_service.return_value = mock_vm_in_group_service

        mock_affinity_groups_service = MagicMock()
        mock_affinity_groups_service.affinity_group_service.return_value = mock_group_service
        mock_affinity_groups_service.affinity_group_service.return_value.vms_service.return_value = mock_vms_in_group_service

        mock_cluster_service = MagicMock()
        mock_cluster_service.affinity_groups_service.return_value = mock_affinity_groups_service

        mock_clusters_service.cluster_service.return_value = mock_cluster_service

        mock_ovirt.connection.system_service.return_value.clusters_service.return_value = mock_clusters_service
        mock_ovirt.connection.system_service.return_value.vms_service.return_value = mock_vms_service

        affinity_mcp = AffinityMCP(mock_ovirt)
        result = affinity_mcp.remove_vm_from_affinity_group("Default", "ag-123", "test-vm")

        assert result["success"] is True


class TestAffinityMCPTools:
    """测试 MCP_TOOLS 注册表"""

    def test_mcp_tools_defined(self):
        """测试 MCP 工具注册表已定义"""
        from src.mcp_affinity import MCP_TOOLS

        expected_tools = [
            "affinity_group_list",
            "affinity_group_get",
            "affinity_group_create",
            "affinity_group_update",
            "affinity_group_delete",
            "affinity_group_add_vm",
            "affinity_group_remove_vm",
        ]

        for tool in expected_tools:
            assert tool in MCP_TOOLS, f"Missing tool: {tool}"
            assert "method" in MCP_TOOLS[tool]
            assert "description" in MCP_TOOLS[tool]
