#!/usr/bin/env python3
"""
oVirt MCP Server - Quota 管理模块
提供配额的创建、查询、更新、删除以及集群和存储限制管理
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


class QuotaMCP(BaseMCP):
    """Quota 管理 MCP"""

    def __init__(self, ovirt_mcp):
        super().__init__(ovirt_mcp)

    def _find_quota(self, datacenter: str, name_or_id: str) -> Optional[Any]:
        """查找配额"""
        dc = self._find_datacenter(datacenter)
        if not dc:
            return None

        dc_service = self.connection.system_service().data_centers_service().data_center_service(dc.id)
        quotas_service = dc_service.quotas_service()

        try:
            quota = quotas_service.quota_service(name_or_id).get()
            if quota:
                return quota
        except Exception:
            pass

        quotas = quotas_service.list(search=f"name={_sanitize_search_value(name_or_id)}")
        return quotas[0] if quotas else None

    @require_connection
    def list_quotas(self, datacenter: str) -> List[Dict]:
        """列出数据中心的配额

        Args:
            datacenter: 数据中心名称或 ID

        Returns:
            配额列表
        """
        dc = self._find_datacenter(datacenter)
        if not dc:
            raise ValueError(f"数据中心不存在: {datacenter}")

        dc_service = self.connection.system_service().data_centers_service().data_center_service(dc.id)
        quotas_service = dc_service.quotas_service()

        try:
            quotas = quotas_service.list()
        except Exception as e:
            logger.error(f"获取配额列表失败: {e}")
            return []

        return [
            {
                "id": q.id,
                "name": q.name,
                "description": q.description if hasattr(q, 'description') else "",
                "data_center": dc.name,
                "cluster_hard_limit_pct": q.cluster_hard_limit_pct if hasattr(q, 'cluster_hard_limit_pct') else 0,
                "storage_hard_limit_pct": q.storage_hard_limit_pct if hasattr(q, 'storage_hard_limit_pct') else 0,
            }
            for q in quotas
        ]

    @require_connection
    def get_quota(self, datacenter: str, name_or_id: str) -> Optional[Dict]:
        """获取配额详情

        Args:
            datacenter: 数据中心名称或 ID
            name_or_id: 配额名称或 ID

        Returns:
            配额详情
        """
        dc = self._find_datacenter(datacenter)
        if not dc:
            raise ValueError(f"数据中心不存在: {datacenter}")

        quota = self._find_quota(datacenter, name_or_id)
        if not quota:
            return None

        # 获取集群限制
        cluster_limits = []
        if hasattr(quota, 'cluster_hard_limit_pct') and quota.cluster_hard_limit_pct:
            cluster_limits.append({
                "type": "hard_limit_pct",
                "value": quota.cluster_hard_limit_pct,
            })

        # 获取存储限制
        storage_limits = []
        if hasattr(quota, 'storage_hard_limit_pct') and quota.storage_hard_limit_pct:
            storage_limits.append({
                "type": "hard_limit_pct",
                "value": quota.storage_hard_limit_pct,
            })

        return {
            "id": quota.id,
            "name": quota.name,
            "description": quota.description if hasattr(quota, 'description') else "",
            "data_center": dc.name,
            "data_center_id": dc.id,
            "cluster_hard_limit_pct": quota.cluster_hard_limit_pct if hasattr(quota, 'cluster_hard_limit_pct') else 0,
            "storage_hard_limit_pct": quota.storage_hard_limit_pct if hasattr(quota, 'storage_hard_limit_pct') else 0,
            "cluster_limits": cluster_limits,
            "storage_limits": storage_limits,
        }

    @require_connection
    def create_quota(self, name: str, datacenter: str,
                    description: str = "",
                    cluster_hard_limit_pct: int = 0,
                    storage_hard_limit_pct: int = 0) -> Dict[str, Any]:
        """创建配额

        Args:
            name: 配额名称
            datacenter: 数据中心名称
            description: 描述
            cluster_hard_limit_pct: 集群硬限制百分比
            storage_hard_limit_pct: 存储硬限制百分比

        Returns:
            创建结果
        """
        dc = self._find_datacenter(datacenter)
        if not dc:
            raise ValueError(f"数据中心不存在: {datacenter}")

        dc_service = self.connection.system_service().data_centers_service().data_center_service(dc.id)
        quotas_service = dc_service.quotas_service()

        # 检查是否已存在
        existing = quotas_service.list(search=f"name={_sanitize_search_value(name)}")
        if existing:
            raise ValueError(f"配额已存在: {name}")

        try:
            quota = quotas_service.add(
                sdk.types.Quota(
                    name=name,
                    description=description,
                    cluster_hard_limit_pct=cluster_hard_limit_pct if cluster_hard_limit_pct > 0 else None,
                    storage_hard_limit_pct=storage_hard_limit_pct if storage_hard_limit_pct > 0 else None,
                )
            )

            return {
                "success": True,
                "message": f"配额 {name} 已创建",
                "quota_id": quota.id,
                "data_center": dc.name,
            }
        except Exception as e:
            raise RuntimeError(f"创建配额失败: {e}")

    @require_connection
    def update_quota(self, datacenter: str, name_or_id: str,
                    new_name: str = None, description: str = None,
                    cluster_hard_limit_pct: int = None,
                    storage_hard_limit_pct: int = None) -> Dict[str, Any]:
        """更新配额

        Args:
            datacenter: 数据中心名称或 ID
            name_or_id: 配额名称或 ID
            new_name: 新名称
            description: 新描述
            cluster_hard_limit_pct: 集群硬限制百分比
            storage_hard_limit_pct: 存储硬限制百分比

        Returns:
            更新结果
        """
        dc = self._find_datacenter(datacenter)
        if not dc:
            raise ValueError(f"数据中心不存在: {datacenter}")

        quota = self._find_quota(datacenter, name_or_id)
        if not quota:
            raise ValueError(f"配额不存在: {name_or_id}")

        dc_service = self.connection.system_service().data_centers_service().data_center_service(dc.id)
        quotas_service = dc_service.quotas_service()
        quota_service = quotas_service.quota_service(quota.id)

        if new_name:
            quota.name = new_name
        if description is not None:
            quota.description = description
        if cluster_hard_limit_pct is not None:
            quota.cluster_hard_limit_pct = cluster_hard_limit_pct
        if storage_hard_limit_pct is not None:
            quota.storage_hard_limit_pct = storage_hard_limit_pct

        try:
            quota_service.update(quota)
            return {"success": True, "message": f"配额已更新"}
        except Exception as e:
            raise RuntimeError(f"更新配额失败: {e}")

    @require_connection
    def delete_quota(self, datacenter: str, name_or_id: str) -> Dict[str, Any]:
        """删除配额

        Args:
            datacenter: 数据中心名称或 ID
            name_or_id: 配额名称或 ID

        Returns:
            删除结果
        """
        dc = self._find_datacenter(datacenter)
        if not dc:
            raise ValueError(f"数据中心不存在: {datacenter}")

        quota = self._find_quota(datacenter, name_or_id)
        if not quota:
            raise ValueError(f"配额不存在: {name_or_id}")

        dc_service = self.connection.system_service().data_centers_service().data_center_service(dc.id)
        quotas_service = dc_service.quotas_service()
        quota_service = quotas_service.quota_service(quota.id)

        try:
            quota_service.remove()
            return {"success": True, "message": f"配额 {quota.name} 已删除"}
        except Exception as e:
            raise RuntimeError(f"删除配额失败: {e}")

    @require_connection
    def list_quota_cluster_limits(self, datacenter: str, name_or_id: str) -> List[Dict]:
        """列出配额的集群限制

        Args:
            datacenter: 数据中心名称或 ID
            name_or_id: 配额名称或 ID

        Returns:
            集群限制列表
        """
        quota = self._find_quota(datacenter, name_or_id)
        if not quota:
            raise ValueError(f"配额不存在: {name_or_id}")

        dc = self._find_datacenter(datacenter)
        dc_service = self.connection.system_service().data_centers_service().data_center_service(dc.id)
        quotas_service = dc_service.quotas_service()
        quota_service = quotas_service.quota_service(quota.id)

        try:
            limits = quota_service.quota_cluster_limits_service().list()
        except Exception as e:
            logger.error(f"获取集群限制失败: {e}")
            return []

        return [
            {
                "id": l.id,
                "cluster": l.cluster.name if hasattr(l, 'cluster') and l.cluster else "",
                "memory_mb": int(l.memory_limit) if hasattr(l, 'memory_limit') else 0,
                "cpu": l.cpu_limit if hasattr(l, 'cpu_limit') else 0,
                "vcpu": l.vcpu_limit if hasattr(l, 'vcpu_limit') else 0,
            }
            for l in limits
        ]

    @require_connection
    def list_quota_storage_limits(self, datacenter: str, name_or_id: str) -> List[Dict]:
        """列出配额的存储限制

        Args:
            datacenter: 数据中心名称或 ID
            name_or_id: 配额名称或 ID

        Returns:
            存储限制列表
        """
        quota = self._find_quota(datacenter, name_or_id)
        if not quota:
            raise ValueError(f"配额不存在: {name_or_id}")

        dc = self._find_datacenter(datacenter)
        dc_service = self.connection.system_service().data_centers_service().data_center_service(dc.id)
        quotas_service = dc_service.quotas_service()
        quota_service = quotas_service.quota_service(quota.id)

        try:
            limits = quota_service.quota_storage_limits_service().list()
        except Exception as e:
            logger.error(f"获取存储限制失败: {e}")
            return []

        return [
            {
                "id": l.id,
                "storage_domain": l.storage_domain.name if hasattr(l, 'storage_domain') and l.storage_domain else "",
                "limit_gb": int((l.limit or 0) / (1024**3)),
                "usage_gb": int((l.usage or 0) / (1024**3)),
            }
            for l in limits
        ]


# MCP 工具注册表
MCP_TOOLS = {
    "quota_list": {"method": "list_quotas", "description": "列出数据中心的配额"},
    "quota_get": {"method": "get_quota", "description": "获取配额详情"},
    "quota_create": {"method": "create_quota", "description": "创建配额"},
    "quota_update": {"method": "update_quota", "description": "更新配额"},
    "quota_delete": {"method": "delete_quota", "description": "删除配额"},
    "quota_cluster_limit_list": {"method": "list_quota_cluster_limits", "description": "列出配额的集群限制"},
    "quota_storage_limit_list": {"method": "list_quota_storage_limits", "description": "列出配额的存储限制"},
}
