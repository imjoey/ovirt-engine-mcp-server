#!/usr/bin/env python3
"""
oVirt MCP Server - 存储扩展模块
提供存储域详情、创建、删除和分离操作
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


class StorageExtendedMCP(BaseMCP):
    """存储扩展管理 MCP"""

    def __init__(self, ovirt_mcp):
        super().__init__(ovirt_mcp)

    @require_connection
    def get_storage_domain(self, name_or_id: str) -> Optional[Dict]:
        """获取存储域详情"""
        sd = self._find_storage_domain(name_or_id)
        if not sd:
            return None

        # 获取存储域的文件列表（如果支持）
        files = []
        try:
            sd_service = self.connection.system_service().storage_domains_service().storage_domain_service(sd.id)
            files_service = sd_service.files_service()
            file_list = files_service.list()
            files = [
                {"name": f.name, "size": f.size if hasattr(f, "size") else 0}
                for f in file_list[:20]  # 限制数量
            ]
        except Exception as e:
            logger.debug(f"获取存储域文件失败: {e}")

        # 获取关联的数据中心
        data_centers = []
        try:
            dc_service = sd_service.storage_domains_service() if hasattr(sd_service, 'storage_domains_service') else None
            # 通过存储域的数据中心链接获取
            if sd.storage_connections:
                data_centers = [
                    {"id": dc.id, "name": dc.name}
                    for dc in [sd.storage_connections]
                ]
        except Exception as e:
            logger.debug(f"获取存储域数据中心失败: {e}")

        return {
            "id": sd.id,
            "name": sd.name,
            "description": sd.description or "",
            "type": str(sd.type.value) if sd.type else "data",
            "status": str(sd.status.value) if sd.status else "unknown",
            "storage_type": str(sd.storage.type.value) if sd.storage else "nfs",
            "available_space_gb": int((sd.available or 0) / (1024**3)),
            "used_space_gb": int((sd.used or 0) / (1024**3)),
            "total_space_gb": int(((sd.available or 0) + (sd.used or 0)) / (1024**3)),
            "master": sd.master if hasattr(sd, 'master') else False,
            "wipe_after_delete": sd.wipe_after_delete if hasattr(sd, 'wipe_after_delete') else False,
            "supports_discard": sd.supports_discard if hasattr(sd, 'supports_discard') else False,
            "warning_low_space": sd.warning_low_space_indicator if hasattr(sd, 'warning_low_space_indicator') else 0,
            "critical_low_space": sd.critical_space_action_blocker if hasattr(sd, 'critical_space_action_blocker') else 0,
            "data_center": sd.storage.data_center.name if sd.storage and sd.storage.data_center else "",
            "data_center_id": sd.storage.data_center.id if sd.storage and sd.storage.data_center else "",
            "files": files,
        }

    @require_connection
    def create_storage_domain(self, name: str, storage_type: str, host: str,
                             path: str, datacenter: str = None,
                             description: str = "",
                             domain_type: str = "data") -> Dict[str, Any]:
        """创建存储域"""
        # 验证存储类型
        valid_storage_types = ["nfs", "fc", "iscsi", "localfs", "posixfs", "glusterfs"]
        if storage_type.lower() not in valid_storage_types:
            raise ValueError(f"无效的存储类型: {storage_type}，有效值: {valid_storage_types}")

        # 验证域类型
        valid_domain_types = ["data", "iso", "export"]
        if domain_type.lower() not in valid_domain_types:
            raise ValueError(f"无效的域类型: {domain_type}，有效值: {valid_domain_types}")

        # 查找主机
        hosts = self.connection.system_service().hosts_service().list(
            search=f"name={_sanitize_search_value(host)}"
        )
        if not hosts:
            raise ValueError(f"主机不存在: {host}")

        sds_service = self.connection.system_service().storage_domains_service()

        # 检查存储域是否已存在
        existing = sds_service.list(search=f"name={_sanitize_search_value(name)}")
        if existing:
            raise ValueError(f"存储域已存在: {name}")

        try:
            # 根据存储类型创建不同的存储配置
            if storage_type.lower() == "nfs":
                storage = sdk.types.HostStorage(
                    type=sdk.types.StorageType.NFS,
                    address=path.split(":")[0] if ":" in path else path,
                    path=path.split(":")[1] if ":" in path else "",
                )
            elif storage_type.lower() == "localfs":
                storage = sdk.types.HostStorage(
                    type=sdk.types.StorageType.LOCALFS,
                    path=path,
                )
            else:
                storage = sdk.types.HostStorage(
                    type=sdk.types.StorageType(storage_type.upper()),
                    address=path,
                )

            sd = sds_service.add(
                sdk.types.StorageDomain(
                    name=name,
                    description=description,
                    type=sdk.types.StorageDomainType(domain_type.upper()),
                    storage=storage,
                    host=sdk.types.Host(id=hosts[0].id),
                    data_center=sdk.types.DataCenter(
                        name=datacenter
                    ) if datacenter else None,
                )
            )
            return {
                "success": True,
                "message": f"存储域 {name} 已创建",
                "storage_domain_id": sd.id,
            }
        except Exception as e:
            raise RuntimeError(f"创建存储域失败: {e}")

    @require_connection
    def delete_storage_domain(self, name_or_id: str, force: bool = False) -> Dict[str, Any]:
        """删除存储域"""
        sd = self._find_storage_domain(name_or_id)
        if not sd:
            raise ValueError(f"存储域不存在: {name_or_id}")

        sd_service = self.connection.system_service().storage_domains_service().storage_domain_service(sd.id)

        try:
            sd_service.remove(force=force)
            return {"success": True, "message": f"存储域 {sd.name} 已删除"}
        except Exception as e:
            raise RuntimeError(f"删除存储域失败: {e}")

    @require_connection
    def detach_storage_domain(self, name_or_id: str, datacenter: str = None) -> Dict[str, Any]:
        """从数据中心分离存储域"""
        sd = self._find_storage_domain(name_or_id)
        if not sd:
            raise ValueError(f"存储域不存在: {name_or_id}")

        # 获取数据中心
        if not datacenter and sd.storage and sd.storage.data_center:
            datacenter = sd.storage.data_center.name

        if not datacenter:
            raise ValueError("需要指定数据中心名称")

        dc = self._find_datacenter(datacenter)
        if not dc:
            raise ValueError(f"数据中心不存在: {datacenter}")

        try:
            # 通过数据中心的存储域服务分离
            dc_service = self.connection.system_service().data_centers_service().data_center_service(dc.id)
            sd_service = dc_service.storage_domains_service().storage_domain_service(sd.id)
            sd_service.remove()

            return {"success": True, "message": f"存储域 {sd.name} 已从数据中心 {datacenter} 分离"}
        except Exception as e:
            raise RuntimeError(f"分离存储域失败: {e}")

    @require_connection
    def attach_storage_domain(self, name_or_id: str, datacenter: str) -> Dict[str, Any]:
        """将存储域附加到数据中心"""
        sd = self._find_storage_domain(name_or_id)
        if not sd:
            raise ValueError(f"存储域不存在: {name_or_id}")

        dc = self._find_datacenter(datacenter)
        if not dc:
            raise ValueError(f"数据中心不存在: {datacenter}")

        try:
            dc_service = self.connection.system_service().data_centers_service().data_center_service(dc.id)
            sd_service = dc_service.storage_domains_service()

            sd_service.add(
                sdk.types.StorageDomain(id=sd.id)
            )

            return {"success": True, "message": f"存储域 {sd.name} 已附加到数据中心 {datacenter}"}
        except Exception as e:
            raise RuntimeError(f"附加存储域失败: {e}")

    @require_connection
    def get_storage_domain_stats(self, name_or_id: str) -> Dict[str, Any]:
        """获取存储域统计信息"""
        sd = self._find_storage_domain(name_or_id)
        if not sd:
            raise ValueError(f"存储域不存在: {name_or_id}")

        available = sd.available or 0
        used = sd.used or 0
        total = available + used

        return {
            "id": sd.id,
            "name": sd.name,
            "type": str(sd.type.value) if sd.type else "data",
            "status": str(sd.status.value) if sd.status else "unknown",
            "available_gb": int(available / (1024**3)),
            "used_gb": int(used / (1024**3)),
            "total_gb": int(total / (1024**3)),
            "usage_percent": round(used / total * 100, 2) if total > 0 else 0,
            "master": sd.master if hasattr(sd, 'master') else False,
        }

    @require_connection
    def refresh_storage_domain(self, name_or_id: str) -> Dict[str, Any]:
        """刷新存储域

        Args:
            name_or_id: 存储域名称或 ID

        Returns:
            刷新结果
        """
        sd = self._find_storage_domain(name_or_id)
        if not sd:
            raise ValueError(f"存储域不存在: {name_or_id}")

        sd_service = self.connection.system_service().storage_domains_service().storage_domain_service(sd.id)

        try:
            sd_service.refresh()
            return {"success": True, "message": f"存储域 {sd.name} 刷新任务已启动"}
        except Exception as e:
            raise RuntimeError(f"刷新存储域失败: {e}")

    @require_connection
    def update_storage_domain(self, name_or_id: str, new_name: str = None,
                             description: str = None,
                             warning_low_space: int = None,
                             critical_low_space: int = None) -> Dict[str, Any]:
        """更新存储域

        Args:
            name_or_id: 存储域名称或 ID
            new_name: 新名称
            description: 新描述
            warning_low_space: 低空间警告阈值（GB）
            critical_low_space: 临界空间阈值（GB）

        Returns:
            更新结果
        """
        sd = self._find_storage_domain(name_or_id)
        if not sd:
            raise ValueError(f"存储域不存在: {name_or_id}")

        sd_service = self.connection.system_service().storage_domains_service().storage_domain_service(sd.id)

        if new_name:
            sd.name = new_name
        if description is not None:
            sd.description = description
        if warning_low_space is not None:
            sd.warning_low_space_indicator = warning_low_space * 1024**3
        if critical_low_space is not None:
            sd.critical_space_action_blocker = critical_low_space * 1024**3

        try:
            sd_service.update(sd)
            return {"success": True, "message": f"存储域已更新"}
        except Exception as e:
            raise RuntimeError(f"更新存储域失败: {e}")

    @require_connection
    def list_storage_files(self, name_or_id: str) -> List[Dict]:
        """列出存储域的文件

        Args:
            name_or_id: 存储域名称或 ID

        Returns:
            文件列表
        """
        sd = self._find_storage_domain(name_or_id)
        if not sd:
            raise ValueError(f"存储域不存在: {name_or_id}")

        sd_service = self.connection.system_service().storage_domains_service().storage_domain_service(sd.id)
        files_service = sd_service.files_service()

        try:
            files = files_service.list()
        except Exception as e:
            logger.error(f"获取存储域文件失败: {e}")
            return []

        return [
            {
                "id": f.id,
                "name": f.name,
                "size": f.size if hasattr(f, 'size') else 0,
            }
            for f in files
        ]

    @require_connection
    def list_storage_connections(self, name_or_id: str = None) -> List[Dict]:
        """列出存储连接

        Args:
            name_or_id: 存储域名称或 ID（可选，不指定则列出所有）

        Returns:
            存储连接列表
        """
        connections_service = self.connection.system_service().storage_connections_service()

        try:
            connections = connections_service.list()
        except Exception as e:
            logger.error(f"获取存储连接失败: {e}")
            return []

        return [
            {
                "id": c.id,
                "address": c.address if hasattr(c, 'address') else "",
                "type": str(c.type.value) if hasattr(c, 'type') and c.type else "",
                "path": c.path if hasattr(c, 'path') else "",
                "port": c.port if hasattr(c, 'port') else 0,
                "mount_options": c.mount_options if hasattr(c, 'mount_options') else "",
                "nfs_version": str(c.nfs_version.value) if hasattr(c, 'nfs_version') and c.nfs_version else "",
            }
            for c in connections
        ]

    @require_connection
    def list_available_disks(self, name_or_id: str) -> List[Dict]:
        """列出存储域上的可用磁盘

        Args:
            name_or_id: 存储域名称或 ID

        Returns:
            可用磁盘列表
        """
        sd = self._find_storage_domain(name_or_id)
        if not sd:
            raise ValueError(f"存储域不存在: {name_or_id}")

        sd_service = self.connection.system_service().storage_domains_service().storage_domain_service(sd.id)
        disks_service = sd_service.disk_service()

        try:
            disks = disks_service.list()
        except Exception as e:
            logger.error(f"获取可用磁盘失败: {e}")
            return []

        return [
            {
                "id": d.id,
                "name": d.name,
                "size_gb": int((d.provisioned_size or 0) / (1024**3)),
                "actual_size_gb": int((d.actual_size or 0) / (1024**3)),
                "format": str(d.format.value) if d.format else "cow",
                "status": str(d.status.value) if d.status else "ok",
                "sparse": d.sparse if hasattr(d, 'sparse') else True,
            }
            for d in disks
        ]

    @require_connection
    def list_export_vms(self, name_or_id: str) -> List[Dict]:
        """列出导出域上的 VM

        Args:
            name_or_id: 导出域名称或 ID

        Returns:
            VM 列表
        """
        sd = self._find_storage_domain(name_or_id)
        if not sd:
            raise ValueError(f"存储域不存在: {name_or_id}")

        # 检查是否为导出域
        if sd.type and sd.type.value != "export":
            raise ValueError("此存储域不是导出域")

        sd_service = self.connection.system_service().storage_domains_service().storage_domain_service(sd.id)
        vms_service = sd_service.vms_service()

        try:
            vms = vms_service.list()
        except Exception as e:
            logger.error(f"获取导出 VM 列表失败: {e}")
            return []

        return [
            {
                "id": vm.id,
                "name": vm.name,
                "description": vm.description or "",
                "memory_mb": int(vm.memory / (1024**2)) if vm.memory else 0,
                "cpu_cores": vm.cpu.topology.cores if vm.cpu and vm.cpu.topology else 0,
                "os_type": vm.os.type if vm.os else "",
            }
            for vm in vms
        ]

    @require_connection
    def import_vm_from_export(self, name_or_id: str, vm_name: str,
                             cluster: str, storage_domain: str = None,
                             clone: bool = False) -> Dict[str, Any]:
        """从导出域导入 VM

        Args:
            name_or_id: 导出域名称或 ID
            vm_name: 要导入的 VM 名称
            cluster: 目标集群
            storage_domain: 目标存储域（可选）
            clone: 是否克隆

        Returns:
            导入结果
        """
        sd = self._find_storage_domain(name_or_id)
        if not sd:
            raise ValueError(f"存储域不存在: {name_or_id}")

        # 查找集群
        clusters = self.connection.system_service().clusters_service().list(
            search=f"name={_sanitize_search_value(cluster)}"
        )
        if not clusters:
            raise ValueError(f"集群不存在: {cluster}")

        sd_service = self.connection.system_service().storage_domains_service().storage_domain_service(sd.id)
        vms_service = sd_service.vms_service()

        # 查找要导入的 VM
        vms = vms_service.list(search=f"name={_sanitize_search_value(vm_name)}")
        if not vms:
            raise ValueError(f"导出域中不存在 VM: {vm_name}")

        vm = vms[0]
        vm_service = vms_service.vm_service(vm.id)

        try:
            # 导入 VM
            import_params = sdk.types.Vm(
                cluster=sdk.types.Cluster(id=clusters[0].id),
            )
            if storage_domain:
                sd_target = self._find_storage_domain(storage_domain)
                if sd_target:
                    import_params.placement_policy = sdk.types.VmPlacementPolicy(
                        host=sdk.types.Host(id=sd_target.id)
                    )

            result = vm_service.import_(
                storage_domain=sdk.types.StorageDomain(id=sd.id) if storage_domain else None,
                cluster=sdk.types.Cluster(id=clusters[0].id),
                clone=clone,
            )

            return {
                "success": True,
                "message": f"VM {vm_name} 导入任务已启动",
                "vm_id": vm.id,
                "cluster": cluster,
            }
        except Exception as e:
            raise RuntimeError(f"导入 VM 失败: {e}")

    @require_connection
    def list_disk_snapshots(self, disk_name_or_id: str) -> List[Dict]:
        """列出磁盘快照

        Args:
            disk_name_or_id: 磁盘名称或 ID

        Returns:
            磁盘快照列表
        """
        # 查找磁盘
        disks_service = self.connection.system_service().disks_service()

        disk_id = None
        try:
            disk = disks_service.disk_service(disk_name_or_id).get()
            disk_id = disk_name_or_id
        except Exception:
            disks = disks_service.list(search=f"name={_sanitize_search_value(disk_name_or_id)}")
            if not disks:
                raise ValueError(f"磁盘不存在: {disk_name_or_id}")
            disk_id = disks[0].id

        disk_service = disks_service.disk_service(disk_id)
        snapshots_service = disk_service.disk_snapshots_service()

        try:
            snapshots = snapshots_service.list()
        except Exception as e:
            logger.error(f"获取磁盘快照失败: {e}")
            return []

        return [
            {
                "id": s.id,
                "description": s.description if hasattr(s, 'description') else "",
                "size_gb": int((s.provisioned_size or 0) / (1024**3)),
                "creation_time": str(s.creation_time) if hasattr(s, 'creation_time') else "",
                "status": str(s.status.value) if s.status else "ok",
            }
            for s in snapshots
        ]

    @require_connection
    def list_iscsi_bonds(self) -> List[Dict]:
        """列出 iSCSI Bond

        Returns:
            iSCSI Bond 列表
        """
        bonds_service = self.connection.system_service().iscsi_bonds_service()

        try:
            bonds = bonds_service.list()
        except Exception as e:
            logger.error(f"获取 iSCSI Bond 列表失败: {e}")
            return []

        return [
            {
                "id": b.id,
                "name": b.name,
                "description": b.description if hasattr(b, 'description') else "",
                "data_center": b.data_center.name if hasattr(b, 'data_center') and b.data_center else "",
            }
            for b in bonds
        ]


# MCP 工具注册表
MCP_TOOLS = {
    "storage_get": {"method": "get_storage_domain", "description": "获取存储域详情"},
    "storage_create": {"method": "create_storage_domain", "description": "创建存储域"},
    "storage_delete": {"method": "delete_storage_domain", "description": "删除存储域"},
    "storage_detach": {"method": "detach_storage_domain", "description": "分离存储域"},
    "storage_attach_to_dc": {"method": "attach_storage_domain", "description": "附加存储域到数据中心"},
    "storage_stats": {"method": "get_storage_domain_stats", "description": "获取存储域统计信息"},

    # 新增工具
    "storage_refresh": {"method": "refresh_storage_domain", "description": "刷新存储域"},
    "storage_update": {"method": "update_storage_domain", "description": "更新存储域配置"},
    "storage_files": {"method": "list_storage_files", "description": "列出存储域的文件"},
    "storage_connections_list": {"method": "list_storage_connections", "description": "列出存储连接"},
    "storage_available_disks": {"method": "list_available_disks", "description": "列出存储域上的可用磁盘"},
    "storage_export_vms": {"method": "list_export_vms", "description": "列出导出域上的 VM"},
    "storage_import_vm": {"method": "import_vm_from_export", "description": "从导出域导入 VM"},
    "disk_snapshot_list": {"method": "list_disk_snapshots", "description": "列出磁盘快照"},
    "iscsi_bond_list": {"method": "list_iscsi_bonds", "description": "列出 iSCSI Bond"},
}
