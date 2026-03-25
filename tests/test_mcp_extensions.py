#!/usr/bin/env python3
"""Tests for MCP extensions - 网络和集群扩展模块测试."""
import pytest
from unittest.mock import MagicMock


def _create_mock_network(net_id="net-123", name="ovirtmgmt"):
    """创建 mock Network 对象"""
    mock_net = MagicMock()
    mock_net.id = net_id
    mock_net.name = name
    mock_net.description = "Management network"
    mock_net.vlan = None
    mock_net.mtu = 1500
    mock_net.status = MagicMock()
    mock_net.status.value = "operational"
    mock_net.data_center = MagicMock()
    mock_net.data_center.id = "dc-123"
    mock_net.cluster = MagicMock()
    mock_net.cluster.name = "Default"
    mock_net.usages = []
    return mock_net


def _create_mock_cluster(cluster_id="cluster-123", name="Default"):
    """创建 mock Cluster 对象"""
    mock_cluster = MagicMock()
    mock_cluster.id = cluster_id
    mock_cluster.name = name
    mock_cluster.description = "Default cluster"
    mock_cluster.cpu = MagicMock()
    mock_cluster.cpu.architecture = MagicMock()
    mock_cluster.cpu.architecture.value = "x86_64"
    mock_cluster.cpu.id = "Intel"
    mock_cluster.memory = 137438953472  # 128GB
    mock_cluster.version = MagicMock()
    mock_cluster.version.major = 4
    mock_cluster.version.minor = 7
    mock_cluster.status = MagicMock()
    mock_cluster.status.value = "up"
    return mock_cluster


def _create_mock_template(template_id="tpl-123", name="CentOS8"):
    """创建 mock Template 对象"""
    mock_tpl = MagicMock()
    mock_tpl.id = template_id
    mock_tpl.name = name
    mock_tpl.description = "CentOS 8 template"
    mock_tpl.memory = 4294967296  # 4GB
    mock_tpl.cpu = MagicMock()
    mock_tpl.cpu.topology = MagicMock()
    mock_tpl.cpu.topology.cores = 2
    mock_tpl.os = MagicMock()
    mock_tpl.os.type = "linux"
    mock_tpl.creation_time = "2024-01-01"
    mock_tpl.disk_attachments_service = MagicMock()
    mock_tpl.disk_attachments_service.return_value.list.return_value = []
    return mock_tpl


class TestNetworkMCP:
    """测试 NetworkMCP 类"""

    def test_list_networks(self):
        """测试列出网络"""
        from src.mcp_extensions import NetworkMCP

        mock_networks = [_create_mock_network()]

        mock_ovirt = MagicMock()
        mock_ovirt.list_networks.return_value = [
            {"id": "net-123", "name": "ovirtmgmt"}
        ]

        net_mcp = NetworkMCP(mock_ovirt)
        result = net_mcp.list_networks()

        assert len(result) == 1
        assert result[0]["name"] == "ovirtmgmt"

    def test_list_vnics(self):
        """测试列出 VM 网卡"""
        from src.mcp_extensions import NetworkMCP

        mock_nic = MagicMock()
        mock_nic.id = "nic-123"
        mock_nic.name = "nic1"
        mock_nic.mac = MagicMock()
        mock_nic.mac.address = "00:11:22:33:44:55"
        mock_nic.network = MagicMock()
        mock_nic.network.name = "ovirtmgmt"
        mock_nic.interface = MagicMock()
        mock_nic.interface.value = "virtio"
        mock_nic.linked = True

        mock_vm = {"id": "vm-123", "name": "test-vm"}

        mock_ovirt = MagicMock()
        mock_ovirt._find_vm.return_value = mock_vm
        mock_ovirt.connection.system_service.return_value.vms_service.return_value.vm_service.return_value.nics_service.return_value.list.return_value = [mock_nic]

        net_mcp = NetworkMCP(mock_ovirt)
        result = net_mcp.list_vnics("test-vm")

        assert len(result) == 1
        assert result[0]["name"] == "nic1"
        assert result[0]["mac"] == "00:11:22:33:44:55"

    def test_list_vnics_vm_not_found(self):
        """测试 VM 不存在时列出网卡"""
        from src.mcp_extensions import NetworkMCP

        mock_ovirt = MagicMock()
        mock_ovirt._find_vm.return_value = None

        net_mcp = NetworkMCP(mock_ovirt)

        with pytest.raises(ValueError, match="VM not found"):
            net_mcp.list_vnics("nonexistent")

    def test_create_network(self):
        """测试创建网络"""
        from src.mcp_extensions import NetworkMCP

        mock_dc = MagicMock()
        mock_dc.id = "dc-123"
        mock_network = _create_mock_network()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True
        mock_ovirt.connection.system_service.return_value.data_centers_service.return_value.list.return_value = [mock_dc]
        mock_ovirt.connection.system_service.return_value.networks_service.return_value.add.return_value = mock_network

        net_mcp = NetworkMCP(mock_ovirt)
        result = net_mcp.create_network("new-net", "Default", vlan="100")

        assert result["success"] is True
        assert "network_id" in result

    def test_create_network_datacenter_not_found(self):
        """测试数据中心不存在时创建网络"""
        from src.mcp_extensions import NetworkMCP

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True
        mock_ovirt.connection.system_service.return_value.data_centers_service.return_value.list.return_value = []

        net_mcp = NetworkMCP(mock_ovirt)

        with pytest.raises(ValueError, match="数据中心不存在"):
            net_mcp.create_network("new-net", "Nonexistent")

    def test_update_network(self):
        """测试更新网络"""
        from src.mcp_extensions import NetworkMCP

        mock_network = _create_mock_network()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True
        mock_ovirt.connection.system_service.return_value.networks_service.return_value.list.return_value = [mock_network]
        mock_ovirt.connection.system_service.return_value.networks_service.return_value.network_service.return_value.get.return_value = mock_network

        net_mcp = NetworkMCP(mock_ovirt)
        result = net_mcp.update_network("ovirtmgmt", new_name="mgmt-net")

        assert result["success"] is True

    def test_delete_network(self):
        """测试删除网络"""
        from src.mcp_extensions import NetworkMCP

        mock_network = _create_mock_network()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True
        mock_ovirt.connection.system_service.return_value.networks_service.return_value.list.return_value = [mock_network]

        net_mcp = NetworkMCP(mock_ovirt)
        result = net_mcp.delete_network("ovirtmgmt")

        assert result["success"] is True


class TestClusterMCP:
    """测试 ClusterMCP 类"""

    def test_list_clusters(self):
        """测试列出集群"""
        from src.mcp_extensions import ClusterMCP

        mock_ovirt = MagicMock()
        mock_ovirt.list_clusters.return_value = [
            {"id": "cluster-123", "name": "Default"}
        ]

        cluster_mcp = ClusterMCP(mock_ovirt)
        result = cluster_mcp.list_clusters()

        assert len(result) == 1
        assert result[0]["name"] == "Default"

    def test_get_cluster(self):
        """测试获取集群详情"""
        from src.mcp_extensions import ClusterMCP

        mock_cluster = _create_mock_cluster()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True
        mock_ovirt.connection.system_service.return_value.clusters_service.return_value.list.return_value = [mock_cluster]

        cluster_mcp = ClusterMCP(mock_ovirt)
        result = cluster_mcp.get_cluster("Default")

        assert result is not None
        assert result["name"] == "Default"
        assert "cpu" in result

    def test_get_cluster_not_found(self):
        """测试集群不存在"""
        from src.mcp_extensions import ClusterMCP

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True
        mock_ovirt.connection.system_service.return_value.clusters_service.return_value.list.return_value = []

        cluster_mcp = ClusterMCP(mock_ovirt)
        result = cluster_mcp.get_cluster("Nonexistent")

        assert result is None

    def test_list_cluster_hosts(self):
        """测试列出集群主机"""
        from src.mcp_extensions import ClusterMCP

        mock_hosts = [{"id": "host-123", "name": "host1"}]

        mock_ovirt = MagicMock()
        mock_ovirt.list_hosts.return_value = mock_hosts

        cluster_mcp = ClusterMCP(mock_ovirt)
        result = cluster_mcp.list_cluster_hosts("Default")

        assert len(result) == 1
        mock_ovirt.list_hosts.assert_called_with(cluster="Default")

    def test_list_cluster_vms(self):
        """测试列出集群虚拟机"""
        from src.mcp_extensions import ClusterMCP

        mock_vms = [{"id": "vm-123", "name": "vm1"}]

        mock_ovirt = MagicMock()
        mock_ovirt.list_vms.return_value = mock_vms

        cluster_mcp = ClusterMCP(mock_ovirt)
        result = cluster_mcp.list_cluster_vms("Default")

        assert len(result) == 1

    def test_get_cluster_cpu_load(self):
        """测试获取集群 CPU 负载"""
        from src.mcp_extensions import ClusterMCP

        mock_hosts = [
            {"id": "host-1", "name": "host1", "cpu_usage": 30},
            {"id": "host-2", "name": "host2", "cpu_usage": 50},
        ]

        mock_ovirt = MagicMock()
        mock_ovirt.list_hosts.return_value = mock_hosts

        cluster_mcp = ClusterMCP(mock_ovirt)
        result = cluster_mcp.get_cluster_cpu_load("Default")

        assert result["cluster"] == "Default"
        assert result["host_count"] == 2
        assert result["cpu_load_avg"] == 40.0

    def test_get_cluster_cpu_load_empty(self):
        """测试空集群的 CPU 负载"""
        from src.mcp_extensions import ClusterMCP

        mock_ovirt = MagicMock()
        mock_ovirt.list_hosts.return_value = []

        cluster_mcp = ClusterMCP(mock_ovirt)
        result = cluster_mcp.get_cluster_cpu_load("Default")

        assert result["cpu_load"] == 0
        assert result["host_count"] == 0

    def test_get_cluster_memory_usage(self):
        """测试获取集群内存使用"""
        from src.mcp_extensions import ClusterMCP

        mock_hosts = [
            {"id": "host-1", "name": "host1", "memory_gb": 64, "memory_usage": 50},
            {"id": "host-2", "name": "host2", "memory_gb": 64, "memory_usage": 75},
        ]

        mock_ovirt = MagicMock()
        mock_ovirt.list_hosts.return_value = mock_hosts

        cluster_mcp = ClusterMCP(mock_ovirt)
        result = cluster_mcp.get_cluster_memory_usage("Default")

        assert result["cluster"] == "Default"
        assert result["memory_total_gb"] == 128
        assert result["host_count"] == 2


class TestTemplateMCP:
    """测试 TemplateMCP 类"""

    def test_list_templates(self):
        """测试列出模板"""
        from src.mcp_extensions import TemplateMCP

        mock_ovirt = MagicMock()
        mock_ovirt.list_templates.return_value = [
            {"id": "tpl-123", "name": "CentOS8"}
        ]

        tpl_mcp = TemplateMCP(mock_ovirt)
        result = tpl_mcp.list_templates()

        assert len(result) == 1
        assert result[0]["name"] == "CentOS8"

    def test_get_template(self):
        """测试获取模板详情"""
        from src.mcp_extensions import TemplateMCP

        mock_tpl = _create_mock_template()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True
        mock_ovirt.connection.system_service.return_value.templates_service.return_value.list.return_value = [mock_tpl]

        tpl_mcp = TemplateMCP(mock_ovirt)
        result = tpl_mcp.get_template("CentOS8")

        assert result is not None
        assert result["name"] == "CentOS8"
        assert result["cpu_cores"] == 2

    def test_get_template_not_found(self):
        """测试模板不存在"""
        from src.mcp_extensions import TemplateMCP

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True
        mock_ovirt.connection.system_service.return_value.templates_service.return_value.list.return_value = []

        tpl_mcp = TemplateMCP(mock_ovirt)
        result = tpl_mcp.get_template("Nonexistent")

        assert result is None

    def test_create_vm_from_template(self):
        """测试从模板创建 VM"""
        from src.mcp_extensions import TemplateMCP

        mock_ovirt = MagicMock()
        mock_ovirt.create_vm.return_value = {
            "success": True,
            "vm_id": "vm-123"
        }

        tpl_mcp = TemplateMCP(mock_ovirt)
        result = tpl_mcp.create_vm_from_template(
            name="new-vm",
            template="CentOS8",
            cluster="Default",
            memory_mb=8192,
            cpu_cores=4
        )

        assert result["success"] is True
        mock_ovirt.create_vm.assert_called_with(
            name="new-vm",
            cluster="Default",
            memory_mb=8192,
            cpu_cores=4,
            template="CentOS8"
        )


class TestMCPExtensionsTools:
    """测试 MCP_TOOLS 注册表"""

    def test_mcp_tools_defined(self):
        """测试 MCP 工具注册表已定义"""
        from src.mcp_extensions import MCP_TOOLS

        expected_tools = [
            "vm_list",
            "vm_get",
            "vm_create",
            "vm_delete",
            "vm_start",
            "vm_stop",
            "vm_restart",
            "snapshot_list",
            "snapshot_create",
            "snapshot_restore",
            "snapshot_delete",
            "disk_list",
            "disk_create",
            "disk_attach",
            "network_list",
            "nic_list",
            "nic_add",
            "nic_remove",
            "host_list",
            "cluster_list",
            "template_list",
        ]

        for tool in expected_tools:
            assert tool in MCP_TOOLS, f"Missing tool: {tool}"
            assert "method" in MCP_TOOLS[tool]
            assert "description" in MCP_TOOLS[tool]
