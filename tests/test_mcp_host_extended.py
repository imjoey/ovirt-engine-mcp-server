#!/usr/bin/env python3
"""Tests for HostExtendedMCP class - 主机扩展模块测试."""
import pytest
from unittest.mock import MagicMock


def _create_mock_host(host_id="host-123", name="host1", status="up"):
    """创建 mock Host 对象"""
    mock_host = MagicMock()
    mock_host.id = host_id
    mock_host.name = name
    mock_host.description = "Test host"
    mock_host.status = MagicMock()
    mock_host.status.value = status
    mock_host.address = "192.168.1.1"
    mock_host.port = 54321
    mock_host.cluster = MagicMock()
    mock_host.cluster.name = "Default"
    mock_host.cluster.id = "cluster-123"
    mock_host.cpu = MagicMock()
    mock_host.cpu.topology = MagicMock()
    mock_host.cpu.topology.cores = 8
    mock_host.cpu.topology.sockets = 1
    mock_host.cpu.topology.threads = 2
    mock_host.cpu.speed = 3000
    mock_host.memory = 68719476736  # 64GB
    mock_host.os = MagicMock()
    mock_host.os.type = MagicMock()
    mock_host.os.type.value = "rhel"
    mock_host.os.version = MagicMock()
    mock_host.os.version.full_version = "8.6"
    mock_host.kvm = MagicMock()
    mock_host.kvm.version = "4.0"
    mock_host.libvirt_version = MagicMock()
    mock_host.libvirt_version.full_version = "8.0.0"
    mock_host.vdsm_version = MagicMock()
    mock_host.vdsm_version.full_version = "4.50"
    return mock_host


def _create_mock_stat(stat_name, stat_value):
    """创建 mock Stat 对象"""
    mock_stat = MagicMock()
    mock_stat.name = stat_name
    mock_stat.values = [MagicMock()]
    mock_stat.values[0].datum = stat_value
    return mock_stat


def _create_mock_device(device_id="dev-123", name="eth0"):
    """创建 mock Device 对象"""
    mock_device = MagicMock()
    mock_device.id = device_id
    mock_device.name = name
    mock_device.capability = MagicMock()
    mock_device.capability.value = "nic"
    mock_device.product = MagicMock()
    mock_device.product.name = "Intel Ethernet"
    mock_device.vendor = MagicMock()
    mock_device.vendor.name = "Intel"
    mock_device.driver = "igb"
    return mock_device


class TestHostExtendedMCPGetHost:
    """测试 get_host 方法"""

    def test_get_host_by_id(self):
        """测试通过 ID 获取主机"""
        from src.mcp_host_extended import HostExtendedMCP

        mock_host = _create_mock_host()
        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_host_service = MagicMock()
        mock_host_service.get.return_value = mock_host
        mock_host_service.nics_service.return_value.list.return_value = []
        mock_host_service.storage_service.return_value.list.return_value = []

        mock_hosts_service = MagicMock()
        mock_hosts_service.host_service.return_value = mock_host_service
        mock_hosts_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.hosts_service.return_value = mock_hosts_service

        host_mcp = HostExtendedMCP(mock_ovirt)
        result = host_mcp.get_host("host-123")

        assert result is not None
        assert result["id"] == "host-123"
        assert result["name"] == "host1"
        assert result["status"] == "up"

    def test_get_host_not_found(self):
        """测试主机不存在"""
        from src.mcp_host_extended import HostExtendedMCP

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_hosts_service = MagicMock()
        mock_hosts_service.host_service.return_value.get.side_effect = Exception("Not found")
        mock_hosts_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.hosts_service.return_value = mock_hosts_service

        host_mcp = HostExtendedMCP(mock_ovirt)
        result = host_mcp.get_host("nonexistent")

        assert result is None

    def test_get_host_with_nics(self):
        """测试获取主机包含网卡信息"""
        from src.mcp_host_extended import HostExtendedMCP

        mock_host = _create_mock_host()
        mock_nic = MagicMock()
        mock_nic.id = "nic-123"
        mock_nic.name = "eth0"
        mock_nic.mac = MagicMock()
        mock_nic.mac.address = "00:11:22:33:44:55"
        mock_nic.ip = MagicMock()
        mock_nic.ip.address = "192.168.1.100"
        mock_nic.speed = 1000000000

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_host_service = MagicMock()
        mock_host_service.get.return_value = mock_host
        mock_host_service.nics_service.return_value.list.return_value = [mock_nic]
        mock_host_service.storage_service.return_value.list.return_value = []

        mock_hosts_service = MagicMock()
        mock_hosts_service.host_service.return_value = mock_host_service
        mock_hosts_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.hosts_service.return_value = mock_hosts_service

        host_mcp = HostExtendedMCP(mock_ovirt)
        result = host_mcp.get_host("host-123")

        assert result is not None
        assert len(result["nics"]) == 1
        assert result["nics"][0]["name"] == "eth0"


class TestHostExtendedMCPAddHost:
    """测试 add_host 方法"""

    def test_add_host_success(self):
        """测试添加主机成功"""
        from src.mcp_host_extended import HostExtendedMCP

        mock_host = _create_mock_host()
        mock_cluster = MagicMock()
        mock_cluster.id = "cluster-123"

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_clusters_service = MagicMock()
        mock_clusters_service.list.return_value = [mock_cluster]

        mock_hosts_service = MagicMock()
        mock_hosts_service.list.return_value = []  # 名称不冲突
        mock_hosts_service.add.return_value = mock_host

        mock_ovirt.connection.system_service.return_value.clusters_service.return_value = mock_clusters_service
        mock_ovirt.connection.system_service.return_value.hosts_service.return_value = mock_hosts_service

        host_mcp = HostExtendedMCP(mock_ovirt)
        result = host_mcp.add_host(
            name="new-host",
            cluster="Default",
            address="192.168.1.10",
            password="secret"
        )

        assert result["success"] is True
        assert "host_id" in result

    def test_add_host_cluster_not_found(self):
        """测试添加主机时集群不存在"""
        from src.mcp_host_extended import HostExtendedMCP

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_clusters_service = MagicMock()
        mock_clusters_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.clusters_service.return_value = mock_clusters_service

        host_mcp = HostExtendedMCP(mock_ovirt)

        with pytest.raises(ValueError, match="集群不存在"):
            host_mcp.add_host("new-host", "Nonexistent", "192.168.1.10")

    def test_add_host_already_exists(self):
        """测试添加已存在的主机"""
        from src.mcp_host_extended import HostExtendedMCP

        mock_host = _create_mock_host()
        mock_cluster = MagicMock()
        mock_cluster.id = "cluster-123"

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_clusters_service = MagicMock()
        mock_clusters_service.list.return_value = [mock_cluster]

        mock_hosts_service = MagicMock()
        mock_hosts_service.list.return_value = [mock_host]  # 名称已存在

        mock_ovirt.connection.system_service.return_value.clusters_service.return_value = mock_clusters_service
        mock_ovirt.connection.system_service.return_value.hosts_service.return_value = mock_hosts_service

        host_mcp = HostExtendedMCP(mock_ovirt)

        with pytest.raises(ValueError, match="已存在"):
            host_mcp.add_host("host1", "Default", "192.168.1.10")


class TestHostExtendedMCPRemoveHost:
    """测试 remove_host 方法"""

    def test_remove_host_success(self):
        """测试移除主机成功"""
        from src.mcp_host_extended import HostExtendedMCP

        mock_host = _create_mock_host()
        mock_host_service = MagicMock()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_hosts_service = MagicMock()
        mock_hosts_service.host_service.return_value.get.return_value = mock_host
        mock_hosts_service.host_service.return_value = mock_host_service
        mock_hosts_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.hosts_service.return_value = mock_hosts_service

        # 需要重新设置 mock_host_service
        mock_ovirt.connection.system_service.return_value.hosts_service.return_value.host_service.return_value = mock_host_service
        mock_ovirt.connection.system_service.return_value.hosts_service.return_value.list.return_value = []

        host_mcp = HostExtendedMCP(mock_ovirt)
        result = host_mcp.remove_host("host-123")

        assert result["success"] is True

    def test_remove_host_not_found(self):
        """测试移除不存在的主机"""
        from src.mcp_host_extended import HostExtendedMCP

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_hosts_service = MagicMock()
        mock_hosts_service.host_service.return_value.get.side_effect = Exception("Not found")
        mock_hosts_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.hosts_service.return_value = mock_hosts_service

        host_mcp = HostExtendedMCP(mock_ovirt)

        with pytest.raises(ValueError, match="不存在"):
            host_mcp.remove_host("nonexistent")


class TestHostExtendedMCPGetHostStats:
    """测试 get_host_stats 方法"""

    def test_get_host_stats_success(self):
        """测试获取主机统计信息成功"""
        from src.mcp_host_extended import HostExtendedMCP

        mock_host = _create_mock_host()
        mock_stats = [
            _create_mock_stat("memory.used", 32768),
            _create_mock_stat("memory.free", 32768),
            _create_mock_stat("cpu.current.user", 15.5),
            _create_mock_stat("cpu.current.system", 5.2),
            _create_mock_stat("cpu.load.avg.5m", 2.5),
        ]

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_host_service = MagicMock()
        mock_host_service.get.return_value = mock_host
        mock_host_service.statistics_service.return_value.list.return_value = mock_stats

        mock_hosts_service = MagicMock()
        mock_hosts_service.host_service.return_value = mock_host_service
        mock_hosts_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.hosts_service.return_value = mock_hosts_service

        host_mcp = HostExtendedMCP(mock_ovirt)
        result = host_mcp.get_host_stats("host-123")

        assert result["host_id"] == "host-123"
        assert "stats" in result
        assert "memory_used_mb" in result["stats"]
        assert "memory_usage_percent" in result["stats"]


class TestHostExtendedMCPGetHostDevices:
    """测试 get_host_devices 方法"""

    def test_get_host_devices_success(self):
        """测试获取主机设备列表成功"""
        from src.mcp_host_extended import HostExtendedMCP

        mock_host = _create_mock_host()
        mock_devices = [_create_mock_device(f"dev-{i}", f"device{i}") for i in range(3)]

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_host_service = MagicMock()
        mock_host_service.get.return_value = mock_host
        mock_host_service.devices_service.return_value.list.return_value = mock_devices

        mock_hosts_service = MagicMock()
        mock_hosts_service.host_service.return_value = mock_host_service
        mock_hosts_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.hosts_service.return_value = mock_hosts_service

        host_mcp = HostExtendedMCP(mock_ovirt)
        result = host_mcp.get_host_devices("host-123")

        assert len(result) == 3
        assert result[0]["name"] == "device0"

    def test_get_host_devices_not_found(self):
        """测试主机不存在时获取设备"""
        from src.mcp_host_extended import HostExtendedMCP

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_hosts_service = MagicMock()
        mock_hosts_service.host_service.return_value.get.side_effect = Exception("Not found")
        mock_hosts_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.hosts_service.return_value = mock_hosts_service

        host_mcp = HostExtendedMCP(mock_ovirt)

        with pytest.raises(ValueError, match="不存在"):
            host_mcp.get_host_devices("nonexistent")


class TestHostExtendedMCPTools:
    """测试 MCP_TOOLS 注册表"""

    def test_mcp_tools_defined(self):
        """测试 MCP 工具注册表已定义"""
        from src.mcp_host_extended import MCP_TOOLS

        expected_tools = [
            "host_get",
            "host_add",
            "host_remove",
            "host_stats",
            "host_devices",
        ]

        for tool in expected_tools:
            assert tool in MCP_TOOLS, f"Missing tool: {tool}"
            assert "method" in MCP_TOOLS[tool]
            assert "description" in MCP_TOOLS[tool]
