#!/usr/bin/env python3
"""
oVirt MCP Server - 磁盘扩展模块
提供磁盘详情、删除、调整大小和分离操作
"""
from typing import Dict, List, Any, Optional
import logging

from .base_mcp import BaseMCP
from .decorators import require_connection
from .search_utils import sanitize_search_value as _sanitize_search_value

try:
    import ovirtsdk4 as sdk
except ImportError:
    sdk = None

logger = logging.getLogger(__name__)


class DiskExtendedMCP(BaseMCP):
    """磁盘扩展管理 MCP"""

    def __init__(self, ovirt_mcp):
        super().__init__(ovirt_mcp)

    @require_connection
    def get_disk(self, name_or_id: str) -> Optional[Dict]:
        """获取磁盘详情"""
        disk = self._find_disk(name_or_id)
        if not disk:
            return None

        # 获取磁盘附加信息
        attachments = []
        try:
            disk_service = self.connection.system_service().disks_service().disk_service(disk.id)
            attachments_service = disk_service.disk_attachments_service() if hasattr(disk_service, 'disk_attachments_service') else None

            # 通过全局磁盘附件服务查找
            all_attachments = self.connection.system_service().disk_attachments_service().list(
                search=f"disk_id={disk.id}"
            ) if hasattr(self.connection.system_service(), 'disk_attachments_service') else []

            for att in all_attachments:
                attachments.append({
                    "vm_id": att.vm.id if att.vm else "",
                    "vm_name": att.vm.name if att.vm else "",
                    "active": att.active if hasattr(att, 'active') else False,
                    "bootable": att.bootable if hasattr(att, 'bootable') else False,
                    "interface": str(att.interface.value) if att.interface else "virtio",
                })
        except Exception as e:
            logger.debug(f"获取磁盘附件失败: {e}")

        return {
            "id": disk.id,
            "name": disk.name,
            "description": disk.description or "",
            "status": str(disk.status.value) if disk.status else "unknown",
            "provisioned_size_gb": int((disk.provisioned_size or 0) / (1024**3)),
            "actual_size_gb": int((disk.actual_size or 0) / (1024**3)),
            "format": str(disk.format.value) if disk.format else "cow",
            "storage_type": str(disk.storage_type.value) if disk.storage_type else "image",
            "sparse": disk.sparse if hasattr(disk, 'sparse') else True,
            "interface": str(disk.interface.value) if disk.interface else "virtio",
            "storage_domain": disk.storage_domain.name if disk.storage_domain else "",
            "storage_domain_id": disk.storage_domain.id if disk.storage_domain else "",
            "shareable": disk.shareable if hasattr(disk, 'shareable') else False,
            "wipe_after_delete": disk.wipe_after_delete if hasattr(disk, 'wipe_after_delete') else False,
            "propagate_errors": disk.propagate_errors if hasattr(disk, 'propagate_errors') else False,
            "qcow_version": str(disk.qcow_version.value) if hasattr(disk, 'qcow_version') and disk.qcow_version else "",
            "attachments": attachments[:10],  # 限制数量
        }

    @require_connection
    def delete_disk(self, name_or_id: str, force: bool = False) -> Dict[str, Any]:
        """删除磁盘"""
        disk = self._find_disk(name_or_id)
        if not disk:
            raise ValueError(f"磁盘不存在: {name_or_id}")

        # 检查磁盘状态
        if disk.status and disk.status.value != "ok" and not force:
            raise RuntimeError(f"磁盘状态异常: {disk.status.value}，使用 force=True 强制删除")

        disk_service = self.connection.system_service().disks_service().disk_service(disk.id)

        try:
            disk_service.remove()
            return {"success": True, "message": f"磁盘 {disk.name} 已删除"}
        except Exception as e:
            raise RuntimeError(f"删除磁盘失败: {e}")

    @require_connection
    def resize_disk(self, name_or_id: str, new_size_gb: int) -> Dict[str, Any]:
        """调整磁盘大小"""
        if new_size_gb <= 0:
            raise ValueError("磁盘大小必须大于 0")

        disk = self._find_disk(name_or_id)
        if not disk:
            raise ValueError(f"磁盘不存在: {name_or_id}")

        current_size_gb = int((disk.provisioned_size or 0) / (1024**3))

        # 只能扩容，不能缩容
        if new_size_gb < current_size_gb:
            raise ValueError(f"不能缩小磁盘: 当前 {current_size_gb}GB，请求 {new_size_gb}GB")

        disk_service = self.connection.system_service().disks_service().disk_service(disk.id)

        try:
            # 更新磁盘大小
            updated_disk = sdk.types.Disk(
                id=disk.id,
                provisioned_size=new_size_gb * 1024**3,
            )
            disk_service.update(updated_disk)

            return {
                "success": True,
                "message": f"磁盘 {disk.name} 大小已从 {current_size_gb}GB 调整为 {new_size_gb}GB",
                "old_size_gb": current_size_gb,
                "new_size_gb": new_size_gb,
            }
        except Exception as e:
            raise RuntimeError(f"调整磁盘大小失败: {e}")

    @require_connection
    def detach_disk(self, name_or_id: str, vm_name_or_id: str) -> Dict[str, Any]:
        """从虚拟机分离磁盘"""
        disk = self._find_disk(name_or_id)
        if not disk:
            raise ValueError(f"磁盘不存在: {name_or_id}")

        vm = self._find_vm(vm_name_or_id)
        if not vm:
            raise ValueError(f"虚拟机不存在: {vm_name_or_id}")

        try:
            # 获取 VM 的磁盘附件
            vm_service = self.connection.system_service().vms_service().vm_service(vm.id)
            attachments_service = vm_service.disk_attachments_service()
            attachments = attachments_service.list()

            # 找到对应的附件
            attachment_id = None
            for att in attachments:
                if att.disk and att.disk.id == disk.id:
                    attachment_id = att.id
                    break

            if not attachment_id:
                raise ValueError(f"磁盘 {disk.name} 未附加到虚拟机 {vm.name}")

            # 分离磁盘
            attachment_service = attachments_service.attachment_service(attachment_id)
            attachment_service.remove()

            return {
                "success": True,
                "message": f"磁盘 {disk.name} 已从虚拟机 {vm.name} 分离",
            }
        except ValueError:
            raise
        except Exception as e:
            raise RuntimeError(f"分离磁盘失败: {e}")

    @require_connection
    def move_disk(self, name_or_id: str, target_storage_domain: str) -> Dict[str, Any]:
        """移动磁盘到另一个存储域"""
        disk = self._find_disk(name_or_id)
        if not disk:
            raise ValueError(f"磁盘不存在: {name_or_id}")

        # 查找目标存储域
        sds = self.connection.system_service().storage_domains_service().list(
            search=f"name={_sanitize_search_value(target_storage_domain)}"
        )
        if not sds:
            raise ValueError(f"存储域不存在: {target_storage_domain}")

        disk_service = self.connection.system_service().disks_service().disk_service(disk.id)

        try:
            # 执行移动操作
            disk_service.move(
                storage_domain=sdk.types.StorageDomain(id=sds[0].id)
            )

            return {
                "success": True,
                "message": f"磁盘 {disk.name} 正在移动到存储域 {target_storage_domain}",
            }
        except Exception as e:
            raise RuntimeError(f"移动磁盘失败: {e}")

    @require_connection
    def get_disk_stats(self, name_or_id: str) -> Dict[str, Any]:
        """获取磁盘统计信息"""
        disk = self._find_disk(name_or_id)
        if not disk:
            raise ValueError(f"磁盘不存在: {name_or_id}")

        provisioned = disk.provisioned_size or 0
        actual = disk.actual_size or 0

        return {
            "id": disk.id,
            "name": disk.name,
            "status": str(disk.status.value) if disk.status else "unknown",
            "provisioned_gb": int(provisioned / (1024**3)),
            "actual_gb": int(actual / (1024**3)),
            "used_percent": round(actual / provisioned * 100, 2) if provisioned > 0 else 0,
            "format": str(disk.format.value) if disk.format else "cow",
            "sparse": disk.sparse if hasattr(disk, 'sparse') else True,
        }

    @require_connection
    def update_disk(self, name_or_id: str, new_name: str = None,
                   description: str = None, shareable: bool = None,
                   wipe_after_delete: bool = None) -> Dict[str, Any]:
        """更新磁盘配置

        Args:
            name_or_id: 磁盘名称或 ID
            new_name: 新名称
            description: 新描述
            shareable: 是否可共享
            wipe_after_delete: 删除后擦除

        Returns:
            更新结果
        """
        disk = self._find_disk(name_or_id)
        if not disk:
            raise ValueError(f"磁盘不存在: {name_or_id}")

        disk_service = self.connection.system_service().disks_service().disk_service(disk.id)

        if new_name:
            disk.name = new_name
        if description is not None:
            disk.description = description
        if shareable is not None:
            disk.shareable = shareable
        if wipe_after_delete is not None:
            disk.wipe_after_delete = wipe_after_delete

        try:
            disk_service.update(disk)
            return {"success": True, "message": f"磁盘配置已更新"}
        except Exception as e:
            raise RuntimeError(f"更新磁盘失败: {e}")

    @require_connection
    def sparsify_disk(self, name_or_id: str) -> Dict[str, Any]:
        """精简磁盘（消除空白块）

        Args:
            name_or_id: 磁盘名称或 ID

        Returns:
            操作结果
        """
        disk = self._find_disk(name_or_id)
        if not disk:
            raise ValueError(f"磁盘不存在: {name_or_id}")

        # 检查磁盘格式
        if disk.format and disk.format.value != "cow":
            raise ValueError("只有 COW 格式的磁盘支持精简操作")

        disk_service = self.connection.system_service().disks_service().disk_service(disk.id)

        try:
            disk_service.sparsify()
            return {
                "success": True,
                "message": f"磁盘 {disk.name} 精简任务已启动",
                "disk_id": disk.id,
            }
        except Exception as e:
            raise RuntimeError(f"精简磁盘失败: {e}")

    @require_connection
    def export_disk(self, name_or_id: str, export_domain: str) -> Dict[str, Any]:
        """导出磁盘到导出域

        Args:
            name_or_id: 磁盘名称或 ID
            export_domain: 导出域名称

        Returns:
            导出结果
        """
        disk = self._find_disk(name_or_id)
        if not disk:
            raise ValueError(f"磁盘不存在: {name_or_id}")

        # 查找导出域
        sds = self.connection.system_service().storage_domains_service().list(
            search=f"name={_sanitize_search_value(export_domain)}"
        )
        if not sds:
            raise ValueError(f"存储域不存在: {export_domain}")

        # 检查是否为导出域
        if sds[0].type and sds[0].type.value != "export":
            raise ValueError(f"存储域 {export_domain} 不是导出域")

        disk_service = self.connection.system_service().disks_service().disk_service(disk.id)

        try:
            disk_service.export(
                storage_domain=sdk.types.StorageDomain(id=sds[0].id)
            )
            return {
                "success": True,
                "message": f"磁盘 {disk.name} 导出任务已启动",
                "disk_id": disk.id,
                "export_domain": export_domain,
            }
        except Exception as e:
            raise RuntimeError(f"导出磁盘失败: {e}")


# MCP 工具注册表
MCP_TOOLS = {
    "disk_get": {"method": "get_disk", "description": "获取磁盘详情"},
    "disk_delete": {"method": "delete_disk", "description": "删除磁盘"},
    "disk_resize": {"method": "resize_disk", "description": "调整磁盘大小"},
    "disk_detach": {"method": "detach_disk", "description": "从虚拟机分离磁盘"},
    "disk_move": {"method": "move_disk", "description": "移动磁盘到另一个存储域"},
    "disk_stats": {"method": "get_disk_stats", "description": "获取磁盘统计信息"},

    # 新增工具
    "disk_update": {"method": "update_disk", "description": "更新磁盘配置"},
    "disk_sparsify": {"method": "sparsify_disk", "description": "精简磁盘（消除空白块）"},
    "disk_export": {"method": "export_disk", "description": "导出磁盘到导出域"},
}
