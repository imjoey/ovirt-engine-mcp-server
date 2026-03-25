#!/usr/bin/env python3
"""Tests for DiskExtendedMCP class - 磁盘扩展模块测试."""
import pytest
from unittest.mock import MagicMock


def _create_mock_disk(disk_id="disk-123", name="disk1", status="ok", size=53687091200):
    """创建 mock Disk 对象"""
    mock_disk = MagicMock()
    mock_disk.id = disk_id
    mock_disk.name = name
    mock_disk.description = "Test disk"
    mock_disk.status = MagicMock()
    mock_disk.status.value = status
    mock_disk.provisioned_size = size
    mock_disk.actual_size = size // 2
    mock_disk.format = MagicMock()
    mock_disk.format.value = "cow"
    mock_disk.storage_type = MagicMock()
    mock_disk.storage_type.value = "image"
    mock_disk.sparse = True
    mock_disk.interface = MagicMock()
    mock_disk.interface.value = "virtio"
    mock_disk.storage_domain = MagicMock()
    mock_disk.storage_domain.name = "storage1"
    mock_disk.storage_domain.id = "sd-123"
    mock_disk.shareable = False
    mock_disk.wipe_after_delete = False
    return mock_disk


def _create_mock_vm(vm_id="vm-123", name="test-vm"):
    """创建 mock VM 对象"""
    mock_vm = MagicMock()
    mock_vm.id = vm_id
    mock_vm.name = name
    return mock_vm


class TestDiskExtendedMCPGetDisk:
    """测试 get_disk 方法"""

    def test_get_disk_by_id(self):
        """测试通过 ID 获取磁盘"""
        from src.mcp_disk_extended import DiskExtendedMCP

        mock_disk = _create_mock_disk()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_disk_service = MagicMock()
        mock_disk_service.get.return_value = mock_disk

        mock_disks_service = MagicMock()
        mock_disks_service.disk_service.return_value = mock_disk_service
        mock_disks_service.list.return_value = []

        # Mock disk attachments
        mock_ovirt.connection.system_service.return_value.disk_attachments_service.return_value.list.return_value = []

        mock_ovirt.connection.system_service.return_value.disks_service.return_value = mock_disks_service

        disk_mcp = DiskExtendedMCP(mock_ovirt)
        result = disk_mcp.get_disk("disk-123")

        assert result is not None
        assert result["id"] == "disk-123"
        assert result["name"] == "disk1"
        assert result["provisioned_size_gb"] == 50

    def test_get_disk_not_found(self):
        """测试磁盘不存在"""
        from src.mcp_disk_extended import DiskExtendedMCP

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_disks_service = MagicMock()
        mock_disks_service.disk_service.return_value.get.side_effect = Exception("Not found")
        mock_disks_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.disks_service.return_value = mock_disks_service

        disk_mcp = DiskExtendedMCP(mock_ovirt)
        result = disk_mcp.get_disk("nonexistent")

        assert result is None


class TestDiskExtendedMCPDeleteDisk:
    """测试 delete_disk 方法"""

    def test_delete_disk_success(self):
        """测试删除磁盘成功"""
        from src.mcp_disk_extended import DiskExtendedMCP

        mock_disk = _create_mock_disk()
        mock_disk_service = MagicMock()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        # 创建服务链 mock
        system_service = mock_ovirt.connection.system_service.return_value
        disks_service = system_service.disks_service.return_value

        # 设置 disk_service 返回正确的 mock
        disk_service_mock = disks_service.disk_service.return_value
        disk_service_mock.get.return_value = mock_disk
        disk_service_mock.remove.return_value = None

        # 按名称搜索返回空（使用ID查找）
        disks_service.list.return_value = []

        disk_mcp = DiskExtendedMCP(mock_ovirt)
        result = disk_mcp.delete_disk("disk-123")

        assert result["success"] is True

    def test_delete_disk_not_found(self):
        """测试删除不存在的磁盘"""
        from src.mcp_disk_extended import DiskExtendedMCP

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_disks_service = MagicMock()
        mock_disks_service.disk_service.return_value.get.side_effect = Exception("Not found")
        mock_disks_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.disks_service.return_value = mock_disks_service

        disk_mcp = DiskExtendedMCP(mock_ovirt)

        with pytest.raises(ValueError, match="不存在"):
            disk_mcp.delete_disk("nonexistent")

    def test_delete_disk_status_not_ok(self):
        """测试磁盘状态异常时删除"""
        from src.mcp_disk_extended import DiskExtendedMCP

        mock_disk = _create_mock_disk(status="locked")

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_disks_service = MagicMock()
        mock_disks_service.disk_service.return_value.get.return_value = mock_disk
        mock_disks_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.disks_service.return_value = mock_disks_service

        disk_mcp = DiskExtendedMCP(mock_ovirt)

        with pytest.raises(RuntimeError, match="状态异常"):
            disk_mcp.delete_disk("disk-123")


class TestDiskExtendedMCPResizeDisk:
    """测试 resize_disk 方法"""

    def test_resize_disk_success(self):
        """测试调整磁盘大小成功"""
        from src.mcp_disk_extended import DiskExtendedMCP

        mock_disk = _create_mock_disk()
        mock_disk_service = MagicMock()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        # 创建服务链 mock
        system_service = mock_ovirt.connection.system_service.return_value
        disks_service = system_service.disks_service.return_value

        # 设置 disk_service 返回正确的 mock
        disk_service_mock = disks_service.disk_service.return_value
        disk_service_mock.get.return_value = mock_disk
        disk_service_mock.update.return_value = None

        # 按名称搜索返回空（使用ID查找）
        disks_service.list.return_value = []

        disk_mcp = DiskExtendedMCP(mock_ovirt)
        result = disk_mcp.resize_disk("disk-123", 100)

        assert result["success"] is True
        assert result["old_size_gb"] == 50
        assert result["new_size_gb"] == 100

    def test_resize_disk_invalid_size(self):
        """测试无效的磁盘大小"""
        from src.mcp_disk_extended import DiskExtendedMCP

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        disk_mcp = DiskExtendedMCP(mock_ovirt)

        with pytest.raises(ValueError, match="必须大于 0"):
            disk_mcp.resize_disk("disk-123", 0)

    def test_resize_disk_shrink_not_allowed(self):
        """测试不允许缩小磁盘"""
        from src.mcp_disk_extended import DiskExtendedMCP

        mock_disk = _create_mock_disk()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_disks_service = MagicMock()
        mock_disks_service.disk_service.return_value.get.return_value = mock_disk
        mock_disks_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.disks_service.return_value = mock_disks_service

        disk_mcp = DiskExtendedMCP(mock_ovirt)

        with pytest.raises(ValueError, match="不能缩小磁盘"):
            disk_mcp.resize_disk("disk-123", 10)  # 当前 50GB，请求缩小到 10GB


class TestDiskExtendedMCPDetachDisk:
    """测试 detach_disk 方法"""

    def test_detach_disk_success(self):
        """测试分离磁盘成功"""
        from src.mcp_disk_extended import DiskExtendedMCP

        mock_disk = _create_mock_disk()
        mock_vm = _create_mock_vm()
        mock_attachment = MagicMock()
        mock_attachment.id = "att-123"
        mock_attachment.disk = MagicMock()
        mock_attachment.disk.id = "disk-123"

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        # Disk service
        mock_disk_service = MagicMock()
        mock_disk_service.get.return_value = mock_disk
        mock_disks_service = MagicMock()
        mock_disks_service.disk_service.return_value = mock_disk_service
        mock_disks_service.list.return_value = []

        # VM service
        mock_vm_service = MagicMock()
        mock_vm_service.get.return_value = mock_vm
        mock_vms_service = MagicMock()
        mock_vms_service.vm_service.return_value = mock_vm_service
        mock_vms_service.list.return_value = []

        # Attachments
        mock_attachments_service = MagicMock()
        mock_attachments_service.list.return_value = [mock_attachment]
        mock_attachment_service = MagicMock()
        mock_attachments_service.attachment_service.return_value = mock_attachment_service

        mock_vm_service.disk_attachments_service.return_value = mock_attachments_service

        mock_ovirt.connection.system_service.return_value.disks_service.return_value = mock_disks_service
        mock_ovirt.connection.system_service.return_value.vms_service.return_value = mock_vms_service

        disk_mcp = DiskExtendedMCP(mock_ovirt)
        result = disk_mcp.detach_disk("disk-123", "vm-123")

        assert result["success"] is True


class TestDiskExtendedMCPMoveDisk:
    """测试 move_disk 方法"""

    def test_move_disk_success(self):
        """测试移动磁盘成功"""
        from src.mcp_disk_extended import DiskExtendedMCP

        mock_disk = _create_mock_disk()
        mock_target_sd = MagicMock()
        mock_target_sd.id = "sd-456"

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_disk_service = MagicMock()
        mock_disk_service.get.return_value = mock_disk
        mock_disks_service = MagicMock()
        mock_disks_service.disk_service.return_value = mock_disk_service
        mock_disks_service.list.return_value = []

        mock_sds_service = MagicMock()
        mock_sds_service.list.return_value = [mock_target_sd]

        mock_ovirt.connection.system_service.return_value.disks_service.return_value = mock_disks_service
        mock_ovirt.connection.system_service.return_value.storage_domains_service.return_value = mock_sds_service

        disk_mcp = DiskExtendedMCP(mock_ovirt)
        result = disk_mcp.move_disk("disk-123", "storage2")

        assert result["success"] is True

    def test_move_disk_storage_not_found(self):
        """测试目标存储域不存在"""
        from src.mcp_disk_extended import DiskExtendedMCP

        mock_disk = _create_mock_disk()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_disk_service = MagicMock()
        mock_disk_service.get.return_value = mock_disk
        mock_disks_service = MagicMock()
        mock_disks_service.disk_service.return_value = mock_disk_service
        mock_disks_service.list.return_value = []

        mock_sds_service = MagicMock()
        mock_sds_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.disks_service.return_value = mock_disks_service
        mock_ovirt.connection.system_service.return_value.storage_domains_service.return_value = mock_sds_service

        disk_mcp = DiskExtendedMCP(mock_ovirt)

        with pytest.raises(ValueError, match="存储域不存在"):
            disk_mcp.move_disk("disk-123", "nonexistent")


class TestDiskExtendedMCPGetStats:
    """测试 get_disk_stats 方法"""

    def test_get_disk_stats_success(self):
        """测试获取磁盘统计信息成功"""
        from src.mcp_disk_extended import DiskExtendedMCP

        mock_disk = _create_mock_disk()

        mock_ovirt = MagicMock()
        mock_ovirt.connected = True

        mock_disk_service = MagicMock()
        mock_disk_service.get.return_value = mock_disk
        mock_disks_service = MagicMock()
        mock_disks_service.disk_service.return_value = mock_disk_service
        mock_disks_service.list.return_value = []

        mock_ovirt.connection.system_service.return_value.disks_service.return_value = mock_disks_service

        disk_mcp = DiskExtendedMCP(mock_ovirt)
        result = disk_mcp.get_disk_stats("disk-123")

        assert result["id"] == "disk-123"
        assert result["name"] == "disk1"
        assert "provisioned_gb" in result
        assert "actual_gb" in result
        assert "used_percent" in result


class TestDiskExtendedMCPTools:
    """测试 MCP_TOOLS 注册表"""

    def test_mcp_tools_defined(self):
        """测试 MCP 工具注册表已定义"""
        from src.mcp_disk_extended import MCP_TOOLS

        expected_tools = [
            "disk_get",
            "disk_delete",
            "disk_resize",
            "disk_detach",
            "disk_move",
            "disk_stats",
        ]

        for tool in expected_tools:
            assert tool in MCP_TOOLS, f"Missing tool: {tool}"
            assert "method" in MCP_TOOLS[tool]
            assert "description" in MCP_TOOLS[tool]
