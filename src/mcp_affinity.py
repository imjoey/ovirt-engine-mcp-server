#!/usr/bin/env python3
"""
oVirt MCP Server - 亲和性组管理模块
提供虚拟机亲和性组的创建和管理
"""
from typing import Dict, List, Any, Optional
import logging

from .search_utils import sanitize_search_value as _sanitize_search_value

try:
    import ovirtsdk4 as sdk
except ImportError:
    sdk = None

logger = logging.getLogger(__name__)


class AffinityMCP:
    """亲和性组管理 MCP"""

    def __init__(self, ovirt_mcp):
        self.ovirt = ovirt_mcp

    def _find_cluster(self, name_or_id: str) -> Optional[Any]:
        """查找集群"""
        clusters_service = self.ovirt.connection.system_service().clusters_service()

        try:
            cluster = clusters_service.cluster_service(name_or_id).get()
            if cluster:
                return cluster
        except Exception:
            pass

        clusters = clusters_service.list(search=f"name={_sanitize_search_value(name_or_id)}")
        return clusters[0] if clusters else None

    def _find_vm(self, name_or_id: str) -> Optional[Any]:
        """查找虚拟机"""
        vms_service = self.ovirt.connection.system_service().vms_service()

        try:
            vm = vms_service.vm_service(name_or_id).get()
            if vm:
                return vm
        except Exception:
            pass

        vms = vms_service.list(search=f"name={_sanitize_search_value(name_or_id)}")
        return vms[0] if vms else None

    def list_affinity_groups(self, cluster: str) -> List[Dict]:
        """列出集群的亲和性组

        Args:
            cluster: 集群名称或 ID

        Returns:
            亲和性组列表
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        cluster_obj = self._find_cluster(cluster)
        if not cluster_obj:
            raise ValueError(f"集群不存在: {cluster}")

        cluster_service = self.ovirt.connection.system_service().clusters_service().cluster_service(cluster_obj.id)
        affinity_groups_service = cluster_service.affinity_groups_service()

        try:
            groups = affinity_groups_service.list()
        except Exception as e:
            logger.error(f"获取亲和性组失败: {e}")
            groups = []

        result = []
        for group in groups:
            # 获取关联的 VM
            vms = []
            if group.vms:
                vms = [{"id": vm.id, "name": vm.name} for vm in group.vms]

            result.append({
                "id": group.id,
                "name": group.name,
                "cluster_id": cluster_obj.id,
                "cluster_name": cluster_obj.name,
                "positive": group.positive if hasattr(group, 'positive') else True,
                "enforcing": group.enforcing if hasattr(group, 'enforcing') else False,
                "vms": vms,
                "vm_count": len(vms),
            })

        return result

    def get_affinity_group(self, cluster: str, name_or_id: str) -> Optional[Dict]:
        """获取亲和性组详情"""
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        cluster_obj = self._find_cluster(cluster)
        if not cluster_obj:
            raise ValueError(f"集群不存在: {cluster}")

        cluster_service = self.ovirt.connection.system_service().clusters_service().cluster_service(cluster_obj.id)
        affinity_groups_service = cluster_service.affinity_groups_service()

        # 查找亲和性组
        try:
            # 尝试按 ID 获取
            group_service = affinity_groups_service.affinity_group_service(name_or_id)
            group = group_service.get()
        except Exception:
            # 按名称搜索
            groups = affinity_groups_service.list(search=f"name={_sanitize_search_value(name_or_id)}")
            if not groups:
                return None
            group = groups[0]

        # 获取关联的 VM
        vms = []
        if group.vms:
            vms = [
                {
                    "id": vm.id,
                    "name": vm.name,
                    "status": "",  # 需要额外查询
                }
                for vm in group.vms
            ]

        return {
            "id": group.id,
            "name": group.name,
            "cluster_id": cluster_obj.id,
            "cluster_name": cluster_obj.name,
            "positive": group.positive if hasattr(group, 'positive') else True,
            "enforcing": group.enforcing if hasattr(group, 'enforcing') else False,
            "vms": vms,
            "vm_count": len(vms),
            "description": "",  # affinity group 没有 description 字段
        }

    def create_affinity_group(self, name: str, cluster: str,
                             positive: bool = True,
                             enforcing: bool = False,
                             vms: List[str] = None) -> Dict[str, Any]:
        """创建亲和性组

        Args:
            name: 亲和性组名称
            cluster: 集群名称或 ID
            positive: True=亲和性（同主机），False=反亲和性（不同主机）
            enforcing: True=强制执行，False=软性规则
            vms: VM 名称或 ID 列表

        Returns:
            创建结果
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        cluster_obj = self._find_cluster(cluster)
        if not cluster_obj:
            raise ValueError(f"集群不存在: {cluster}")

        cluster_service = self.ovirt.connection.system_service().clusters_service().cluster_service(cluster_obj.id)
        affinity_groups_service = cluster_service.affinity_groups_service()

        # 检查是否已存在
        existing = affinity_groups_service.list(search=f"name={_sanitize_search_value(name)}")
        if existing:
            raise ValueError(f"亲和性组已存在: {name}")

        # 解析 VM 列表
        vm_refs = []
        if vms:
            for vm_name in vms:
                vm = self._find_vm(vm_name)
                if vm:
                    vm_refs.append(sdk.types.Vm(id=vm.id))

        try:
            group = affinity_groups_service.add(
                sdk.types.AffinityGroup(
                    name=name,
                    positive=positive,
                    enforcing=enforcing,
                    vms=vm_refs if vm_refs else None,
                )
            )

            return {
                "success": True,
                "message": f"亲和性组 {name} 已创建",
                "affinity_group_id": group.id,
                "positive": positive,
                "enforcing": enforcing,
                "vm_count": len(vm_refs),
            }
        except Exception as e:
            raise RuntimeError(f"创建亲和性组失败: {e}")

    def update_affinity_group(self, cluster: str, name_or_id: str,
                             new_name: str = None,
                             positive: bool = None,
                             enforcing: bool = None) -> Dict[str, Any]:
        """更新亲和性组"""
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        cluster_obj = self._find_cluster(cluster)
        if not cluster_obj:
            raise ValueError(f"集群不存在: {cluster}")

        cluster_service = self.ovirt.connection.system_service().clusters_service().cluster_service(cluster_obj.id)
        affinity_groups_service = cluster_service.affinity_groups_service()

        # 查找亲和性组
        group = None
        group_id = None
        try:
            group_service = affinity_groups_service.affinity_group_service(name_or_id)
            group = group_service.get()
            group_id = name_or_id
        except Exception:
            groups = affinity_groups_service.list(search=f"name={_sanitize_search_value(name_or_id)}")
            if not groups:
                raise ValueError(f"亲和性组不存在: {name_or_id}")
            group = groups[0]
            group_id = group.id

        group_service = affinity_groups_service.affinity_group_service(group_id)

        # 更新属性
        if new_name:
            group.name = new_name
        if positive is not None:
            group.positive = positive
        if enforcing is not None:
            group.enforcing = enforcing

        try:
            group_service.update(group)
            return {"success": True, "message": f"亲和性组已更新"}
        except Exception as e:
            raise RuntimeError(f"更新亲和性组失败: {e}")

    def delete_affinity_group(self, cluster: str, name_or_id: str) -> Dict[str, Any]:
        """删除亲和性组"""
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        cluster_obj = self._find_cluster(cluster)
        if not cluster_obj:
            raise ValueError(f"集群不存在: {cluster}")

        cluster_service = self.ovirt.connection.system_service().clusters_service().cluster_service(cluster_obj.id)
        affinity_groups_service = cluster_service.affinity_groups_service()

        # 查找亲和性组
        group_id = None
        group_name = None
        try:
            group_service = affinity_groups_service.affinity_group_service(name_or_id)
            group = group_service.get()
            group_id = name_or_id
            group_name = group.name
        except Exception:
            groups = affinity_groups_service.list(search=f"name={_sanitize_search_value(name_or_id)}")
            if not groups:
                raise ValueError(f"亲和性组不存在: {name_or_id}")
            group_id = groups[0].id
            group_name = groups[0].name

        group_service = affinity_groups_service.affinity_group_service(group_id)

        try:
            group_service.remove()
            return {"success": True, "message": f"亲和性组 {group_name} 已删除"}
        except Exception as e:
            raise RuntimeError(f"删除亲和性组失败: {e}")

    def add_vm_to_affinity_group(self, cluster: str, affinity_group: str,
                                 vm: str) -> Dict[str, Any]:
        """将 VM 添加到亲和性组"""
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        cluster_obj = self._find_cluster(cluster)
        if not cluster_obj:
            raise ValueError(f"集群不存在: {cluster}")

        vm_obj = self._find_vm(vm)
        if not vm_obj:
            raise ValueError(f"VM 不存在: {vm}")

        cluster_service = self.ovirt.connection.system_service().clusters_service().cluster_service(cluster_obj.id)
        affinity_groups_service = cluster_service.affinity_groups_service()

        # 查找亲和性组
        group_id = None
        try:
            group_service = affinity_groups_service.affinity_group_service(affinity_group)
            group = group_service.get()
            group_id = affinity_group
        except Exception:
            groups = affinity_groups_service.list(search=f"name={_sanitize_search_value(affinity_group)}")
            if not groups:
                raise ValueError(f"亲和性组不存在: {affinity_group}")
            group_id = groups[0].id

        group_service = affinity_groups_service.affinity_group_service(group_id)
        vms_service = group_service.vms_service()

        try:
            vms_service.add(sdk.types.Vm(id=vm_obj.id))
            return {
                "success": True,
                "message": f"VM {vm_obj.name} 已添加到亲和性组",
            }
        except Exception as e:
            raise RuntimeError(f"添加 VM 到亲和性组失败: {e}")

    def remove_vm_from_affinity_group(self, cluster: str, affinity_group: str,
                                      vm: str) -> Dict[str, Any]:
        """从亲和性组移除 VM"""
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        cluster_obj = self._find_cluster(cluster)
        if not cluster_obj:
            raise ValueError(f"集群不存在: {cluster}")

        vm_obj = self._find_vm(vm)
        if not vm_obj:
            raise ValueError(f"VM 不存在: {vm}")

        cluster_service = self.ovirt.connection.system_service().clusters_service().cluster_service(cluster_obj.id)
        affinity_groups_service = cluster_service.affinity_groups_service()

        # 查找亲和性组
        group_id = None
        try:
            group_service = affinity_groups_service.affinity_group_service(affinity_group)
            group = group_service.get()
            group_id = affinity_group
        except Exception:
            groups = affinity_groups_service.list(search=f"name={_sanitize_search_value(affinity_group)}")
            if not groups:
                raise ValueError(f"亲和性组不存在: {affinity_group}")
            group_id = groups[0].id

        group_service = affinity_groups_service.affinity_group_service(group_id)
        vms_service = group_service.vms_service()
        vm_service = vms_service.vm_service(vm_obj.id)

        try:
            vm_service.remove()
            return {
                "success": True,
                "message": f"VM {vm_obj.name} 已从亲和性组移除",
            }
        except Exception as e:
            raise RuntimeError(f"从亲和性组移除 VM 失败: {e}")


# MCP 工具注册表
MCP_TOOLS = {
    "affinity_group_list": {"method": "list_affinity_groups", "description": "列出亲和性组"},
    "affinity_group_get": {"method": "get_affinity_group", "description": "获取亲和性组详情"},
    "affinity_group_create": {"method": "create_affinity_group", "description": "创建亲和性组"},
    "affinity_group_update": {"method": "update_affinity_group", "description": "更新亲和性组"},
    "affinity_group_delete": {"method": "delete_affinity_group", "description": "删除亲和性组"},
    "affinity_group_add_vm": {"method": "add_vm_to_affinity_group", "description": "添加 VM 到亲和性组"},
    "affinity_group_remove_vm": {"method": "remove_vm_from_affinity_group", "description": "从亲和性组移除 VM"},
}
