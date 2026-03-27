#!/usr/bin/env python3
"""
oVirt MCP Server - 亲和性组管理模块
提供虚拟机亲和性组的创建和管理
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


class AffinityMCP(BaseMCP):
    """亲和性组管理 MCP"""

    def __init__(self, ovirt_mcp):
        super().__init__(ovirt_mcp)

    def _find_affinity_label(self, name_or_id: str) -> Optional[Any]:
        """查找亲和性标签"""
        labels_service = self.connection.system_service().affinity_labels_service()

        try:
            label = labels_service.affinity_label_service(name_or_id).get()
            if label:
                return label
        except Exception:
            pass

        labels = labels_service.list(search=f"name={_sanitize_search_value(name_or_id)}")
        return labels[0] if labels else None

    @require_connection
    def list_affinity_groups(self, cluster: str) -> List[Dict]:
        """列出集群的亲和性组

        Args:
            cluster: 集群名称或 ID

        Returns:
            亲和性组列表
        """
        cluster_obj = self._find_cluster(cluster)
        if not cluster_obj:
            raise ValueError(f"集群不存在: {cluster}")

        cluster_service = self.connection.system_service().clusters_service().cluster_service(cluster_obj.id)
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

    @require_connection
    def get_affinity_group(self, cluster: str, name_or_id: str) -> Optional[Dict]:
        """获取亲和性组详情"""
        cluster_obj = self._find_cluster(cluster)
        if not cluster_obj:
            raise ValueError(f"集群不存在: {cluster}")

        cluster_service = self.connection.system_service().clusters_service().cluster_service(cluster_obj.id)
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

    @require_connection
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
        cluster_obj = self._find_cluster(cluster)
        if not cluster_obj:
            raise ValueError(f"集群不存在: {cluster}")

        cluster_service = self.connection.system_service().clusters_service().cluster_service(cluster_obj.id)
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

    @require_connection
    def update_affinity_group(self, cluster: str, name_or_id: str,
                             new_name: str = None,
                             positive: bool = None,
                             enforcing: bool = None) -> Dict[str, Any]:
        """更新亲和性组"""
        cluster_obj = self._find_cluster(cluster)
        if not cluster_obj:
            raise ValueError(f"集群不存在: {cluster}")

        cluster_service = self.connection.system_service().clusters_service().cluster_service(cluster_obj.id)
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

    @require_connection
    def delete_affinity_group(self, cluster: str, name_or_id: str) -> Dict[str, Any]:
        """删除亲和性组"""
        cluster_obj = self._find_cluster(cluster)
        if not cluster_obj:
            raise ValueError(f"集群不存在: {cluster}")

        cluster_service = self.connection.system_service().clusters_service().cluster_service(cluster_obj.id)
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

    @require_connection
    def add_vm_to_affinity_group(self, cluster: str, affinity_group: str,
                                 vm: str) -> Dict[str, Any]:
        """将 VM 添加到亲和性组"""
        cluster_obj = self._find_cluster(cluster)
        if not cluster_obj:
            raise ValueError(f"集群不存在: {cluster}")

        vm_obj = self._find_vm(vm)
        if not vm_obj:
            raise ValueError(f"VM 不存在: {vm}")

        cluster_service = self.connection.system_service().clusters_service().cluster_service(cluster_obj.id)
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

    @require_connection
    def remove_vm_from_affinity_group(self, cluster: str, affinity_group: str,
                                      vm: str) -> Dict[str, Any]:
        """从亲和性组移除 VM"""
        cluster_obj = self._find_cluster(cluster)
        if not cluster_obj:
            raise ValueError(f"集群不存在: {cluster}")

        vm_obj = self._find_vm(vm)
        if not vm_obj:
            raise ValueError(f"VM 不存在: {vm}")

        cluster_service = self.connection.system_service().clusters_service().cluster_service(cluster_obj.id)
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

    # ── Affinity Label 管理 ──────────────────────────────────────────────────

    @require_connection
    def list_affinity_labels(self) -> List[Dict]:
        """列出亲和性标签

        Returns:
            亲和性标签列表
        """
        labels_service = self.connection.system_service().affinity_labels_service()

        try:
            labels = labels_service.list()
        except Exception as e:
            logger.error(f"获取亲和性标签失败: {e}")
            return []

        return [
            {
                "id": l.id,
                "name": l.name,
                "description": l.read_only if hasattr(l, 'read_only') else False,
                "vm_count": len(l.vms) if l.vms else 0,
                "host_count": len(l.hosts) if l.hosts else 0,
            }
            for l in labels
        ]

    @require_connection
    def get_affinity_label(self, name_or_id: str) -> Optional[Dict]:
        """获取亲和性标签详情

        Args:
            name_or_id: 标签名称或 ID

        Returns:
            标签详情
        """
        label = self._find_affinity_label(name_or_id)
        if not label:
            return None

        # 获取关联的 VM
        vms = []
        if label.vms:
            vms = [
                {"id": vm.id, "name": vm.name}
                for vm in label.vms
            ]

        # 获取关联的主机
        hosts = []
        if label.hosts:
            hosts = [
                {"id": h.id, "name": h.name}
                for h in label.hosts
            ]

        return {
            "id": label.id,
            "name": label.name,
            "read_only": label.read_only if hasattr(label, 'read_only') else False,
            "vms": vms,
            "vm_count": len(vms),
            "hosts": hosts,
            "host_count": len(hosts),
        }

    @require_connection
    def create_affinity_label(self, name: str) -> Dict[str, Any]:
        """创建亲和性标签

        Args:
            name: 标签名称

        Returns:
            创建结果
        """
        labels_service = self.connection.system_service().affinity_labels_service()

        # 检查是否已存在
        existing = labels_service.list(search=f"name={_sanitize_search_value(name)}")
        if existing:
            raise ValueError(f"亲和性标签已存在: {name}")

        try:
            label = labels_service.add(
                sdk.types.AffinityLabel(name=name)
            )

            return {
                "success": True,
                "message": f"亲和性标签 {name} 已创建",
                "label_id": label.id,
            }
        except Exception as e:
            raise RuntimeError(f"创建亲和性标签失败: {e}")

    @require_connection
    def delete_affinity_label(self, name_or_id: str) -> Dict[str, Any]:
        """删除亲和性标签

        Args:
            name_or_id: 标签名称或 ID

        Returns:
            删除结果
        """
        label = self._find_affinity_label(name_or_id)
        if not label:
            raise ValueError(f"亲和性标签不存在: {name_or_id}")

        labels_service = self.connection.system_service().affinity_labels_service()
        label_service = labels_service.affinity_label_service(label.id)

        try:
            label_service.remove()
            return {"success": True, "message": f"亲和性标签 {label.name} 已删除"}
        except Exception as e:
            raise RuntimeError(f"删除亲和性标签失败: {e}")

    @require_connection
    def assign_affinity_label(self, label: str, resource_type: str,
                             resource: str) -> Dict[str, Any]:
        """为资源分配亲和性标签

        Args:
            label: 标签名称或 ID
            resource_type: 资源类型（vm 或 host）
            resource: 资源名称或 ID

        Returns:
            分配结果
        """
        if resource_type.lower() not in ["vm", "host"]:
            raise ValueError("resource_type 必须是 'vm' 或 'host'")

        label_obj = self._find_affinity_label(label)
        if not label_obj:
            raise ValueError(f"亲和性标签不存在: {label}")

        labels_service = self.connection.system_service().affinity_labels_service()
        label_service = labels_service.affinity_label_service(label_obj.id)

        try:
            if resource_type.lower() == "vm":
                vm = self._find_vm(resource)
                if not vm:
                    raise ValueError(f"VM 不存在: {resource}")
                vms_service = label_service.vms_service()
                vms_service.add(sdk.types.Vm(id=vm.id))
            else:
                host = self._find_host(resource)
                if not host:
                    raise ValueError(f"主机不存在: {resource}")
                hosts_service = label_service.hosts_service()
                hosts_service.add(sdk.types.Host(id=host.id))

            return {
                "success": True,
                "message": f"亲和性标签 {label_obj.name} 已分配给 {resource_type}",
            }
        except Exception as e:
            raise RuntimeError(f"分配亲和性标签失败: {e}")

    @require_connection
    def unassign_affinity_label(self, label: str, resource_type: str,
                               resource: str) -> Dict[str, Any]:
        """移除资源的亲和性标签

        Args:
            label: 标签名称或 ID
            resource_type: 资源类型（vm 或 host）
            resource: 资源名称或 ID

        Returns:
            移除结果
        """
        if resource_type.lower() not in ["vm", "host"]:
            raise ValueError("resource_type 必须是 'vm' 或 'host'")

        label_obj = self._find_affinity_label(label)
        if not label_obj:
            raise ValueError(f"亲和性标签不存在: {label}")

        labels_service = self.connection.system_service().affinity_labels_service()
        label_service = labels_service.affinity_label_service(label_obj.id)

        try:
            if resource_type.lower() == "vm":
                vm = self._find_vm(resource)
                if not vm:
                    raise ValueError(f"VM 不存在: {resource}")
                vms_service = label_service.vms_service()
                vm_service = vms_service.vm_service(vm.id)
                vm_service.remove()
            else:
                host = self._find_host(resource)
                if not host:
                    raise ValueError(f"主机不存在: {resource}")
                hosts_service = label_service.hosts_service()
                host_service = hosts_service.host_service(host.id)
                host_service.remove()

            return {
                "success": True,
                "message": f"亲和性标签 {label_obj.name} 已从 {resource_type} 移除",
            }
        except Exception as e:
            raise RuntimeError(f"移除亲和性标签失败: {e}")


# MCP 工具注册表
MCP_TOOLS = {
    # 亲和性组
    "affinity_group_list": {"method": "list_affinity_groups", "description": "列出亲和性组"},
    "affinity_group_get": {"method": "get_affinity_group", "description": "获取亲和性组详情"},
    "affinity_group_create": {"method": "create_affinity_group", "description": "创建亲和性组"},
    "affinity_group_update": {"method": "update_affinity_group", "description": "更新亲和性组"},
    "affinity_group_delete": {"method": "delete_affinity_group", "description": "删除亲和性组"},
    "affinity_group_add_vm": {"method": "add_vm_to_affinity_group", "description": "添加 VM 到亲和性组"},
    "affinity_group_remove_vm": {"method": "remove_vm_from_affinity_group", "description": "从亲和性组移除 VM"},

    # 亲和性标签
    "affinity_label_list": {"method": "list_affinity_labels", "description": "列出亲和性标签"},
    "affinity_label_get": {"method": "get_affinity_label", "description": "获取亲和性标签详情"},
    "affinity_label_create": {"method": "create_affinity_label", "description": "创建亲和性标签"},
    "affinity_label_delete": {"method": "delete_affinity_label", "description": "删除亲和性标签"},
    "affinity_label_assign": {"method": "assign_affinity_label", "description": "为资源分配亲和性标签"},
    "affinity_label_unassign": {"method": "unassign_affinity_label", "description": "移除资源的亲和性标签"},
}
