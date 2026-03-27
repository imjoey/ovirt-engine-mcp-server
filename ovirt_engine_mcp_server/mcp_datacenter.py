#!/usr/bin/env python3
"""
oVirt MCP Server - 数据中心管理模块
提供数据中心的 CRUD 操作
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


class DataCenterMCP(BaseMCP):
    """数据中心管理 MCP"""

    def __init__(self, ovirt_mcp):
        super().__init__(ovirt_mcp)

    @require_connection
    def list_datacenters(self) -> List[Dict]:
        """列出所有数据中心"""
        dcs_service = self.connection.system_service().data_centers_service()
        dcs = dcs_service.list()

        result = []
        for dc in dcs:
            result.append({
                "id": dc.id,
                "name": dc.name,
                "description": dc.description or "",
                "status": str(dc.status.value) if dc.status else "unknown",
                "storage_type": str(dc.storage_type.value) if dc.storage_type else "nfs",
                "version": f"{dc.version.major}.{dc.version.minor}" if dc.version else "",
                "supported_versions": [
                    f"{v.major}.{v.minor}" for v in dc.supported_versions
                ] if dc.supported_versions else [],
            })

        return result

    @require_connection
    def get_datacenter(self, name_or_id: str) -> Optional[Dict]:
        """获取数据中心详情"""
        dc = self._find_datacenter(name_or_id)
        if not dc:
            return None

        # 获取关联的集群
        clusters = []
        try:
            dc_service = self.connection.system_service().data_centers_service().data_center_service(dc.id)
            clusters_service = dc_service.clusters_service()
            cluster_list = clusters_service.list()
            clusters = [{"id": c.id, "name": c.name} for c in cluster_list]
        except Exception as e:
            logger.debug(f"获取数据中心集群失败: {e}")

        # 获取关联的存储域
        storage_domains = []
        try:
            sd_service = dc_service.storage_domains_service()
            sd_list = sd_service.list()
            storage_domains = [{"id": s.id, "name": s.name, "type": str(s.type.value)} for s in sd_list]
        except Exception as e:
            logger.debug(f"获取数据中心存储域失败: {e}")

        # 获取关联的网络
        networks = []
        try:
            networks_service = dc_service.networks_service()
            net_list = networks_service.list()
            networks = [{"id": n.id, "name": n.name} for n in net_list[:10]]  # 限制数量
        except Exception as e:
            logger.debug(f"获取数据中心网络失败: {e}")

        return {
            "id": dc.id,
            "name": dc.name,
            "description": dc.description or "",
            "status": str(dc.status.value) if dc.status else "unknown",
            "storage_type": str(dc.storage_type.value) if dc.storage_type else "nfs",
            "version": f"{dc.version.major}.{dc.version.minor}" if dc.version else "",
            "mac_pool": dc.mac_pool.name if dc.mac_pool else "",
            "clusters": clusters,
            "storage_domains": storage_domains,
            "networks": networks,
        }

    @require_connection
    def create_datacenter(self, name: str, storage_type: str = "nfs",
                         description: str = "") -> Dict[str, Any]:
        """创建数据中心"""
        # 验证存储类型
        valid_types = ["nfs", "fc", "iscsi", "localfs", "posixfs", "glusterfs"]
        if storage_type.lower() not in valid_types:
            raise ValueError(f"无效的存储类型: {storage_type}，有效值: {valid_types}")

        dcs_service = self.connection.system_service().data_centers_service()

        # 检查是否已存在
        existing = dcs_service.list(search=f"name={_sanitize_search_value(name)}")
        if existing:
            raise ValueError(f"数据中心已存在: {name}")

        # 创建数据中心
        try:
            dc = dcs_service.add(
                sdk.types.DataCenter(
                    name=name,
                    description=description,
                    storage_type=sdk.types.StorageType(storage_type.lower()),
                    version=sdk.types.Version(major=4, minor=7),  # 默认版本
                )
            )
            return {
                "success": True,
                "message": f"数据中心 {name} 已创建",
                "datacenter_id": dc.id,
            }
        except Exception as e:
            raise RuntimeError(f"创建数据中心失败: {e}")

    @require_connection
    def update_datacenter(self, name_or_id: str, new_name: str = None,
                         description: str = None) -> Dict[str, Any]:
        """更新数据中心"""
        dc = self._find_datacenter(name_or_id)
        if not dc:
            raise ValueError(f"数据中心不存在: {name_or_id}")

        dc_service = self.connection.system_service().data_centers_service().data_center_service(dc.id)

        # 获取当前数据中心信息
        current_dc = dc_service.get()

        # 更新属性
        if new_name:
            current_dc.name = new_name
        if description is not None:
            current_dc.description = description

        try:
            dc_service.update(current_dc)
            return {"success": True, "message": f"数据中心已更新"}
        except Exception as e:
            raise RuntimeError(f"更新数据中心失败: {e}")

    @require_connection
    def delete_datacenter(self, name_or_id: str) -> Dict[str, Any]:
        """删除数据中心"""
        dc = self._find_datacenter(name_or_id)
        if not dc:
            raise ValueError(f"数据中心不存在: {name_or_id}")

        dc_service = self.connection.system_service().data_centers_service().data_center_service(dc.id)

        try:
            dc_service.remove()
            return {"success": True, "message": f"数据中心 {dc.name} 已删除"}
        except Exception as e:
            raise RuntimeError(f"删除数据中心失败: {e}")


# MCP 工具注册表
MCP_TOOLS = {
    "datacenter_list": {"method": "list_datacenters", "description": "列出数据中心"},
    "datacenter_get": {"method": "get_datacenter", "description": "获取数据中心详情"},
    "datacenter_create": {"method": "create_datacenter", "description": "创建数据中心"},
    "datacenter_update": {"method": "update_datacenter", "description": "更新数据中心"},
    "datacenter_delete": {"method": "delete_datacenter", "description": "删除数据中心"},
}
