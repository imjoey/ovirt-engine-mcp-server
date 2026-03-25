#!/usr/bin/env python3
"""
oVirt MCP Server - 存储扩展模块
提供存储域详情、创建、删除和分离操作
"""
from typing import Dict, List, Any, Optional
import logging

from .search_utils import sanitize_search_value as _sanitize_search_value

try:
    import ovirtsdk4 as sdk
except ImportError:
    sdk = None

logger = logging.getLogger(__name__)


class StorageExtendedMCP:
    """存储扩展管理 MCP"""

    def __init__(self, ovirt_mcp):
        self.ovirt = ovirt_mcp

    def _find_storage_domain(self, name_or_id: str) -> Optional[Any]:
        """查找存储域（按名称或ID）"""
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        sds_service = self.ovirt.connection.system_service().storage_domains_service()

        # 先尝试按 ID 查找
        try:
            sd = sds_service.storage_domain_service(name_or_id).get()
            if sd:
                return sd
        except Exception:
            pass

        # 按名称搜索
        sds = sds_service.list(search=f"name={_sanitize_search_value(name_or_id)}")
        return sds[0] if sds else None

    def _find_datacenter(self, name_or_id: str) -> Optional[Any]:
        """查找数据中心"""
        dcs_service = self.ovirt.connection.system_service().data_centers_service()

        try:
            dc = dcs_service.data_center_service(name_or_id).get()
            if dc:
                return dc
        except Exception:
            pass

        dcs = dcs_service.list(search=f"name={_sanitize_search_value(name_or_id)}")
        return dcs[0] if dcs else None

    def get_storage_domain(self, name_or_id: str) -> Optional[Dict]:
        """获取存储域详情"""
        sd = self._find_storage_domain(name_or_id)
        if not sd:
            return None

        # 获取存储域的文件列表（如果支持）
        files = []
        try:
            sd_service = self.ovirt.connection.system_service().storage_domains_service().storage_domain_service(sd.id)
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

    def create_storage_domain(self, name: str, storage_type: str, host: str,
                             path: str, datacenter: str = None,
                             description: str = "",
                             domain_type: str = "data") -> Dict[str, Any]:
        """创建存储域"""
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        # 验证存储类型
        valid_storage_types = ["nfs", "fc", "iscsi", "localfs", "posixfs", "glusterfs"]
        if storage_type.lower() not in valid_storage_types:
            raise ValueError(f"无效的存储类型: {storage_type}，有效值: {valid_storage_types}")

        # 验证域类型
        valid_domain_types = ["data", "iso", "export"]
        if domain_type.lower() not in valid_domain_types:
            raise ValueError(f"无效的域类型: {domain_type}，有效值: {valid_domain_types}")

        # 查找主机
        hosts = self.ovirt.connection.system_service().hosts_service().list(
            search=f"name={_sanitize_search_value(host)}"
        )
        if not hosts:
            raise ValueError(f"主机不存在: {host}")

        sds_service = self.ovirt.connection.system_service().storage_domains_service()

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

    def delete_storage_domain(self, name_or_id: str, force: bool = False) -> Dict[str, Any]:
        """删除存储域"""
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        sd = self._find_storage_domain(name_or_id)
        if not sd:
            raise ValueError(f"存储域不存在: {name_or_id}")

        sd_service = self.ovirt.connection.system_service().storage_domains_service().storage_domain_service(sd.id)

        try:
            sd_service.remove(force=force)
            return {"success": True, "message": f"存储域 {sd.name} 已删除"}
        except Exception as e:
            raise RuntimeError(f"删除存储域失败: {e}")

    def detach_storage_domain(self, name_or_id: str, datacenter: str = None) -> Dict[str, Any]:
        """从数据中心分离存储域"""
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

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
            dc_service = self.ovirt.connection.system_service().data_centers_service().data_center_service(dc.id)
            sd_service = dc_service.storage_domains_service().storage_domain_service(sd.id)
            sd_service.remove()

            return {"success": True, "message": f"存储域 {sd.name} 已从数据中心 {datacenter} 分离"}
        except Exception as e:
            raise RuntimeError(f"分离存储域失败: {e}")

    def attach_storage_domain(self, name_or_id: str, datacenter: str) -> Dict[str, Any]:
        """将存储域附加到数据中心"""
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        sd = self._find_storage_domain(name_or_id)
        if not sd:
            raise ValueError(f"存储域不存在: {name_or_id}")

        dc = self._find_datacenter(datacenter)
        if not dc:
            raise ValueError(f"数据中心不存在: {datacenter}")

        try:
            dc_service = self.ovirt.connection.system_service().data_centers_service().data_center_service(dc.id)
            sd_service = dc_service.storage_domains_service()

            sd_service.add(
                sdk.types.StorageDomain(id=sd.id)
            )

            return {"success": True, "message": f"存储域 {sd.name} 已附加到数据中心 {datacenter}"}
        except Exception as e:
            raise RuntimeError(f"附加存储域失败: {e}")

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


# MCP 工具注册表
MCP_TOOLS = {
    "storage_get": {"method": "get_storage_domain", "description": "获取存储域详情"},
    "storage_create": {"method": "create_storage_domain", "description": "创建存储域"},
    "storage_delete": {"method": "delete_storage_domain", "description": "删除存储域"},
    "storage_detach": {"method": "detach_storage_domain", "description": "分离存储域"},
    "storage_attach_to_dc": {"method": "attach_storage_domain", "description": "附加存储域到数据中心"},
    "storage_stats": {"method": "get_storage_domain_stats", "description": "获取存储域统计信息"},
}
