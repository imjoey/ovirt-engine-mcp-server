#!/usr/bin/env python3
"""
Ovirt MCP Server - 网络和集群增强模块
"""
from typing import Dict, List, Any, Optional
import logging
from .search_utils import sanitize_search_value as _sanitize_search_value
try:
    import ovirtsdk4 as sdk
except ImportError:
    sdk = None

logger = logging.getLogger(__name__)


class NetworkMCP:
    """网络管理 MCP"""
    
    def __init__(self, ovirt_mcp):
        self.ovirt = ovirt_mcp
    
    def list_networks(self, cluster: str = None, datacenter: str = None) -> List[Dict]:
        """列出网络"""
        return self.ovirt.list_networks(cluster)
    
    def list_vnics(self, name_or_id: str) -> List[Dict]:
        """列出 VM 的网卡"""
        vm = self.ovirt._find_vm(name_or_id)
        if not vm: raise ValueError(f"VM not found: {name_or_id}")
        
        nics_service = self.ovirt.connection.system_service().vms_service().vm_service(vm["id"]).nics_service()
        nics = nics_service.list()
        
        return [
            {
                "id": n.id,
                "name": n.name,
                "mac": n.mac.address if n.mac else "",
                "network": n.network.name if n.network else "",
                "interface": str(n.interface.value) if n.interface else "virtio",
                "linked": n.linked
            }
            for n in nics
        ]
    
    def create_network(self, name: str, datacenter: str, vlan: str = None, 
                      description: str = "") -> Dict[str, Any]:
        """创建网络"""
        if not self.ovirt.connected: raise RuntimeError("未连接")
        
        # 获取数据中心
        dcs = self.ovirt.connection.system_service().data_centers_service().list(search=f"name={_sanitize_search_value(datacenter)}")
        if not dcs: raise ValueError(f"数据中心不存在: {datacenter}")
        
        # 创建网络
        network = self.ovirt.connection.system_service().networks_service().add(
            sdk.types.Network(
                name=name,
                description=description,
                data_center=sdk.types.DataCenter(id=dcs[0].id),
                vlan=sdk.types.Vlan(id=vlan) if vlan else None
            )
        )
        
        return {"success": True, "message": f"网络 {name} 已创建", "network_id": network.id}
    
    def update_network(self, name: str, new_name: str = None, description: str = None) -> Dict[str, Any]:
        """更新网络"""
        if not self.ovirt.connected: raise RuntimeError("未连接")
        
        networks = self.ovirt.connection.system_service().networks_service().list(search=f"name={_sanitize_search_value(name)}")
        if not networks: raise ValueError(f"网络不存在: {name}")
        
        network_service = self.ovirt.connection.system_service().networks_service().network_service(networks[0].id)
        network = network_service.get()
        
        if new_name:
            network.name = new_name
        if description is not None:
            network.description = description
        
        network_service.update(network)
        
        return {"success": True, "message": f"网络已更新"}
    
    def delete_network(self, name: str) -> Dict[str, Any]:
        """删除网络"""
        if not self.ovirt.connected: raise RuntimeError("未连接")
        
        networks = self.ovirt.connection.system_service().networks_service().list(search=f"name={_sanitize_search_value(name)}")
        if not networks: raise ValueError(f"网络不存在: {name}")
        
        self.ovirt.connection.system_service().networks_service().network_service(networks[0].id).remove()
        
        return {"success": True, "message": f"网络 {name} 已删除"}


class ClusterMCP:
    """集群管理 MCP"""
    
    def __init__(self, ovirt_mcp):
        self.ovirt = ovirt_mcp
    
    def list_clusters(self) -> List[Dict]:
        """列出集群"""
        return self.ovirt.list_clusters()
    
    def get_cluster(self, name: str) -> Optional[Dict]:
        """获取集群详情"""
        if not self.ovirt.connected: raise RuntimeError("未连接")
        
        clusters = self.ovirt.connection.system_service().clusters_service().list(search=f"name={_sanitize_search_value(name)}")
        if not clusters: return None
        
        c = clusters[0]
        
        # 获取集群 CPU
        cpu_info = {}
        if c.cpu:
            cpu_info = {
                "architecture": str(c.cpu.architecture.value) if c.cpu.architecture else "x86_64",
                "型号": str(c.cpu.id) if c.cpu.id else ""
            }
        
        return {
            "id": c.id,
            "name": c.name,
            "description": c.description or "",
            "cpu_architecture": str(c.cpu.architecture.value) if c.cpu else "x86_64",
            "cpu": cpu_info,
            "memory_gb": int((c.memory or 0) / (1024**3)),
            "version": f"{c.version.major}.{c.version.minor}" if c.version else "4.7",
            "status": str(c.status.value) if c.status else "up"
        }
    
    def list_cluster_hosts(self, name: str) -> List[Dict]:
        """列出集群主机"""
        if not self.ovirt.connected: raise RuntimeError("未连接")
        
        hosts = self.ovirt.list_hosts(cluster=name)
        return hosts
    
    def list_cluster_vms(self, name: str, status: str = None) -> List[Dict]:
        """列出集群虚拟机"""
        return self.ovirt.list_vms(cluster=name, status=status)
    
    def get_cluster_cpu_load(self, name: str) -> Dict[str, Any]:
        """获取集群 CPU 负载"""
        hosts = self.list_cluster_hosts(name)
        
        if not hosts:
            return {"cluster": name, "cpu_load": 0, "host_count": 0}
        
        total_load = sum(h.get("cpu_usage", 0) for h in hosts)
        
        return {
            "cluster": name,
            "cpu_load_avg": total_load / len(hosts),
            "cpu_load_total": total_load,
            "host_count": len(hosts),
            "hosts": hosts
        }
    
    def get_cluster_memory_usage(self, name: str) -> Dict[str, Any]:
        """获取集群内存使用"""
        hosts = self.list_cluster_hosts(name)
        
        if not hosts:
            return {"cluster": name, "memory_usage": 0}
        
        total_mem = sum(h.get("memory_gb", 0) for h in hosts)
        # 简化计算
        avg_usage = sum(h.get("memory_usage", 0) for h in hosts) / len(hosts)
        
        return {
            "cluster": name,
            "memory_usage_avg": avg_usage,
            "memory_total_gb": total_mem,
            "host_count": len(hosts)
        }


class TemplateMCP:
    """模板管理 MCP"""
    
    def __init__(self, ovirt_mcp):
        self.ovirt = ovirt_mcp
    
    def list_templates(self, cluster: str = None) -> List[Dict]:
        """列出模板"""
        return self.ovirt.list_templates(cluster)
    
    def get_template(self, name: str) -> Optional[Dict]:
        """获取模板详情"""
        if not self.ovirt.connected: raise RuntimeError("未连接")
        
        templates = self.ovirt.connection.system_service().templates_service().list(search=f"name={_sanitize_search_value(name)}")
        if not templates: return None
        
        t = templates[0]
        
        # 获取磁盘信息
        disks = []
        try:
            disk_attachments = t.disk_attachments_service().list()
            for da in disk_attachments:
                disk = da.disk_service().get()
                disks.append({
                    "name": disk.name,
                    "size_gb": int((disk.provisioned_size or 0) / (1024**3))
                })
        except Exception as e:
            logger.debug(f"Failed to get template disk info: {e}")
        
        return {
            "id": t.id,
            "name": t.name,
            "description": t.description or "",
            "memory_mb": int(t.memory / (1024**2)) if t.memory else 0,
            "cpu_cores": t.cpu.topology.cores if t.cpu and t.cpu.topology else 0,
            "os_type": t.os.type if t.os else "",
            "disks": disks,
            "creation_time": str(t.creation_time) if t.creation_time else ""
        }
    
    def create_vm_from_template(self, name: str, template: str, cluster: str, 
                                memory_mb: int = None, cpu_cores: int = None) -> Dict[str, Any]:
        """从模板创建 VM"""
        return self.ovirt.create_vm(
            name=name,
            cluster=cluster,
            memory_mb=memory_mb or 4096,
            cpu_cores=cpu_cores or 2,
            template=template
        )
    
    def clone_template(self, name: str, new_name: str, cluster: str) -> Dict[str, Any]:
        """克隆模板"""
        # 先从模板创建 VM
        result = self.create_vm_from_template(new_name, name, cluster)
        return result


# MCP 工具注册表
MCP_TOOLS = {
    # 核心 VM 操作
    "vm_list": {"method": "list_vms", "description": "列出虚拟机"},
    "vm_get": {"method": "get_vm", "description": "获取虚拟机详情"},
    "vm_create": {"method": "create_vm", "description": "创建虚拟机"},
    "vm_delete": {"method": "delete_vm", "description": "删除虚拟机"},
    "vm_start": {"method": "start_vm", "description": "启动虚拟机"},
    "vm_stop": {"method": "stop_vm", "description": "关闭虚拟机"},
    "vm_restart": {"method": "restart_vm", "description": "重启虚拟机"},
    "vm_update_resources": {"method": "update_vm_resources", "description": "更新 VM 资源"},
    "vm_stats": {"method": "get_vm_stats", "description": "获取 VM 统计"},
    
    # 快照管理
    "snapshot_list": {"method": "list_snapshots", "description": "列出快照"},
    "snapshot_create": {"method": "create_snapshot", "description": "创建快照"},
    "snapshot_restore": {"method": "restore_snapshot", "description": "恢复快照"},
    "snapshot_delete": {"method": "delete_snapshot", "description": "删除快照"},
    
    # 磁盘管理
    "disk_list": {"method": "list_disks", "description": "列出磁盘"},
    "disk_create": {"method": "create_disk", "description": "创建磁盘"},
    "disk_attach": {"method": "attach_disk", "description": "附加磁盘"},
    
    # 网络管理
    "network_list": {"method": "list_networks", "description": "列出网络"},
    "nic_list": {"method": "list_vnics", "description": "列出网卡"},
    "nic_add": {"method": "add_nic", "description": "添加网卡"},
    "nic_remove": {"method": "remove_nic", "description": "移除网卡"},
    
    # 主机管理
    "host_list": {"method": "list_hosts", "description": "列出主机"},
    "host_activate": {"method": "activate_host", "description": "激活主机"},
    "host_deactivate": {"method": "deactivate_host", "description": "维护主机"},
    
    # 集群管理
    "cluster_list": {"method": "list_clusters", "description": "列出集群"},
    "cluster_hosts": {"method": "list_cluster_hosts", "description": "集群主机"},
    "cluster_vms": {"method": "list_cluster_vms", "description": "集群 VM"},
    "cluster_cpu_load": {"method": "get_cluster_cpu_load", "description": "集群 CPU 负载"},
    
    # 存储管理
    "storage_list": {"method": "list_storage_domains", "description": "列出存储域"},
    "storage_attach": {"method": "attach_storage", "description": "挂载存储"},
    
    # 模板管理
    "template_list": {"method": "list_templates", "description": "列出模板"},
    "template_vm_create": {"method": "create_vm_from_template", "description": "从模板创建 VM"},
}


def get_tool_list() -> List[Dict]:
    """获取所有 MCP 工具定义"""
    return [
        {"name": name, "description": info["description"]}
        for name, info in MCP_TOOLS.items()
    ]
