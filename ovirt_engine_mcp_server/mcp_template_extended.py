#!/usr/bin/env python3
"""
oVirt MCP Server - 模板扩展模块
提供模板详情、创建、删除、更新以及磁盘、网卡、实例类型等管理功能
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


class TemplateExtendedMCP(BaseMCP):
    """模板扩展管理 MCP"""

    def __init__(self, ovirt_mcp):
        super().__init__(ovirt_mcp)

    @require_connection
    def get_template(self, name_or_id: str) -> Optional[Dict]:
        """获取模板详情

        Args:
            name_or_id: 模板名称或 ID

        Returns:
            模板详情
        """
        template = self._find_template(name_or_id)
        if not template:
            return None

        # 获取磁盘信息
        disks = []
        try:
            disk_attachments = template.disk_attachments_service().list()
            for da in disk_attachments:
                disk = da.disk_service().get()
                disks.append({
                    "id": disk.id,
                    "name": disk.name,
                    "size_gb": int((disk.provisioned_size or 0) / (1024**3)),
                    "format": str(disk.format.value) if disk.format else "cow",
                    "interface": str(da.interface.value) if da.interface else "virtio",
                })
        except Exception as e:
            logger.debug(f"获取模板磁盘信息失败: {e}")

        # 获取网卡信息
        nics = []
        try:
            nics_service = template.nics_service()
            nic_list = nics_service.list()
            nics = [
                {
                    "id": n.id,
                    "name": n.name,
                    "mac": n.mac.address if n.mac else "",
                    "interface": str(n.interface.value) if n.interface else "virtio",
                }
                for n in nic_list
            ]
        except Exception as e:
            logger.debug(f"获取模板网卡信息失败: {e}")

        return {
            "id": template.id,
            "name": template.name,
            "description": template.description or "",
            "memory_mb": int(template.memory / (1024**2)) if template.memory else 0,
            "cpu_cores": template.cpu.topology.cores if template.cpu and template.cpu.topology else 0,
            "cpu_sockets": template.cpu.topology.sockets if template.cpu and template.cpu.topology else 1,
            "cpu_threads": template.cpu.topology.threads if template.cpu and template.cpu.topology else 1,
            "os_type": template.os.type if template.os else "",
            "cluster": template.cluster.name if template.cluster else "",
            "cluster_id": template.cluster.id if template.cluster else "",
            "status": str(template.status.value) if template.status else "ok",
            "disks": disks,
            "nics": nics,
            "creation_time": str(template.creation_time) if template.creation_time else "",
            "bios_type": str(template.bios.type.value) if template.bios else "",
        }

    @require_connection
    def create_template(self, name: str, vm: str, description: str = "",
                       cluster: str = None) -> Dict[str, Any]:
        """从虚拟机创建模板

        Args:
            name: 模板名称
            vm: 源虚拟机名称或 ID
            description: 描述
            cluster: 目标集群（可选）

        Returns:
            创建结果
        """
        # 查找 VM
        vm_obj = self._find_vm(vm)
        if not vm_obj:
            raise ValueError(f"VM 不存在: {vm}")

        vms_service = self.connection.system_service().vms_service()
        vm_service = vms_service.vm_service(vm_obj.id)

        # 构建模板
        template_params = sdk.types.Template(
            name=name,
            description=description,
        )

        if cluster:
            cluster_obj = self._find_cluster(cluster)
            if cluster_obj:
                template_params.cluster = sdk.types.Cluster(id=cluster_obj.id)

        try:
            template = vm_service.export(template_params)

            return {
                "success": True,
                "message": f"模板 {name} 正在创建",
                "template_id": template.id,
                "source_vm": vm_obj.name,
            }
        except Exception as e:
            raise RuntimeError(f"创建模板失败: {e}")

    @require_connection
    def delete_template(self, name_or_id: str, force: bool = False) -> Dict[str, Any]:
        """删除模板

        Args:
            name_or_id: 模板名称或 ID
            force: 强制删除

        Returns:
            删除结果
        """
        template = self._find_template(name_or_id)
        if not template:
            raise ValueError(f"模板不存在: {name_or_id}")

        # 不能删除 Blank 模板
        if template.name.lower() == "blank":
            raise ValueError("不能删除 Blank 模板")

        templates_service = self.connection.system_service().templates_service()
        template_service = templates_service.template_service(template.id)

        try:
            template_service.remove(force=force)
            return {"success": True, "message": f"模板 {template.name} 已删除"}
        except Exception as e:
            raise RuntimeError(f"删除模板失败: {e}")

    @require_connection
    def update_template(self, name_or_id: str, new_name: str = None,
                       description: str = None, memory_mb: int = None,
                       cpu_cores: int = None) -> Dict[str, Any]:
        """更新模板

        Args:
            name_or_id: 模板名称或 ID
            new_name: 新名称
            description: 新描述
            memory_mb: 内存（MB）
            cpu_cores: CPU 核数

        Returns:
            更新结果
        """
        template = self._find_template(name_or_id)
        if not template:
            raise ValueError(f"模板不存在: {name_or_id}")

        templates_service = self.connection.system_service().templates_service()
        template_service = templates_service.template_service(template.id)

        # 更新属性
        if new_name:
            template.name = new_name
        if description is not None:
            template.description = description
        if memory_mb is not None:
            template.memory = memory_mb * 1024 * 1024
        if cpu_cores is not None and template.cpu:
            template.cpu.topology.cores = cpu_cores

        try:
            template_service.update(template)
            return {"success": True, "message": f"模板已更新"}
        except Exception as e:
            raise RuntimeError(f"更新模板失败: {e}")

    @require_connection
    def list_template_disks(self, name_or_id: str) -> List[Dict]:
        """列出模板的磁盘

        Args:
            name_or_id: 模板名称或 ID

        Returns:
            磁盘列表
        """
        template = self._find_template(name_or_id)
        if not template:
            raise ValueError(f"模板不存在: {name_or_id}")

        disks = []
        try:
            disk_attachments = template.disk_attachments_service().list()
            for da in disk_attachments:
                disk = da.disk_service().get()
                disks.append({
                    "id": disk.id,
                    "name": disk.name,
                    "size_gb": int((disk.provisioned_size or 0) / (1024**3)),
                    "actual_size_gb": int((disk.actual_size or 0) / (1024**3)),
                    "format": str(disk.format.value) if disk.format else "cow",
                    "storage_domain": disk.storage_domain.name if disk.storage_domain else "",
                    "interface": str(da.interface.value) if da.interface else "virtio",
                    "bootable": da.bootable if hasattr(da, 'bootable') else False,
                })
        except Exception as e:
            logger.error(f"获取模板磁盘失败: {e}")

        return disks

    @require_connection
    def list_template_nics(self, name_or_id: str) -> List[Dict]:
        """列出模板的网卡

        Args:
            name_or_id: 模板名称或 ID

        Returns:
            网卡列表
        """
        template = self._find_template(name_or_id)
        if not template:
            raise ValueError(f"模板不存在: {name_or_id}")

        nics = []
        try:
            nics_service = template.nics_service()
            nic_list = nics_service.list()
            nics = [
                {
                    "id": n.id,
                    "name": n.name,
                    "mac": n.mac.address if n.mac else "",
                    "interface": str(n.interface.value) if n.interface else "virtio",
                    "linked": n.linked if hasattr(n, 'linked') else True,
                    "vnic_profile": n.vnic_profile.name if n.vnic_profile else "",
                }
                for n in nic_list
            ]
        except Exception as e:
            logger.error(f"获取模板网卡失败: {e}")

        return nics

    # ── Instance Type 管理 ──────────────────────────────────────────────────

    @require_connection
    def list_instance_types(self) -> List[Dict]:
        """列出实例类型

        Returns:
            实例类型列表
        """
        instance_types_service = self.connection.system_service().instance_types_service()

        try:
            types = instance_types_service.list()
        except Exception as e:
            logger.error(f"获取实例类型列表失败: {e}")
            return []

        return [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description or "",
                "memory_mb": int(t.memory / (1024**2)) if t.memory else 0,
                "cpu_cores": t.cpu.topology.cores if t.cpu and t.cpu.topology else 0,
                "cpu_sockets": t.cpu.topology.sockets if t.cpu and t.cpu.topology else 1,
            }
            for t in types
        ]

    @require_connection
    def get_instance_type(self, name_or_id: str) -> Optional[Dict]:
        """获取实例类型详情

        Args:
            name_or_id: 实例类型名称或 ID

        Returns:
            实例类型详情
        """
        instance_types_service = self.connection.system_service().instance_types_service()

        # 尝试按 ID 获取
        try:
            it = instance_types_service.instance_type_service(name_or_id).get()
            if it:
                return self._format_instance_type(it)
        except Exception:
            pass

        # 按名称搜索
        types = instance_types_service.list(search=f"name={_sanitize_search_value(name_or_id)}")
        if not types:
            return None

        return self._format_instance_type(types[0])

    def _format_instance_type(self, it) -> Dict:
        """格式化实例类型"""
        return {
            "id": it.id,
            "name": it.name,
            "description": it.description or "",
            "memory_mb": int(it.memory / (1024**2)) if it.memory else 0,
            "cpu_cores": it.cpu.topology.cores if it.cpu and it.cpu.topology else 0,
            "cpu_sockets": it.cpu.topology.sockets if it.cpu and it.cpu.topology else 1,
            "cpu_threads": it.cpu.topology.threads if it.cpu and it.cpu.topology else 1,
            "os_type": it.os.type if it.os else "",
            "bios_type": str(it.bios.type.value) if it.bios else "",
        }


# MCP 工具注册表
MCP_TOOLS = {
    # 模板管理
    "template_get": {"method": "get_template", "description": "获取模板详情"},
    "template_create": {"method": "create_template", "description": "从虚拟机创建模板"},
    "template_delete": {"method": "delete_template", "description": "删除模板"},
    "template_update": {"method": "update_template", "description": "更新模板"},

    # 模板磁盘和网卡
    "template_disk_list": {"method": "list_template_disks", "description": "列出模板的磁盘"},
    "template_nic_list": {"method": "list_template_nics", "description": "列出模板的网卡"},

    # 实例类型
    "instance_type_list": {"method": "list_instance_types", "description": "列出实例类型"},
    "instance_type_get": {"method": "get_instance_type", "description": "获取实例类型详情"},
}
