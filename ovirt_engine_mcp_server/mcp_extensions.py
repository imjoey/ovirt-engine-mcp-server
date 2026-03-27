#!/usr/bin/env python3
"""
Ovirt MCP Server - 网络和集群增强模块
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


class NetworkMCP(BaseMCP):
    """网络管理 MCP"""

    def __init__(self, ovirt_mcp):
        super().__init__(ovirt_mcp)

    def list_networks(self, cluster: str = None, datacenter: str = None) -> List[Dict]:
        """列出网络"""
        return self.ovirt.list_networks(cluster)

    @require_connection
    def get_network(self, name_or_id: str) -> Optional[Dict]:
        """获取网络详情

        Args:
            name_or_id: 网络名称或 ID

        Returns:
            网络详情
        """
        network = self._find_network(name_or_id)
        if not network:
            return None

        return {
            "id": network.id,
            "name": network.name,
            "description": network.description or "",
            "data_center": network.data_center.name if network.data_center else "",
            "data_center_id": network.data_center.id if network.data_center else "",
            "vlan_id": network.vlan.id if network.vlan else None,
            "mtu": network.mtu if hasattr(network, 'mtu') else 0,
            "stp": network.stp if hasattr(network, 'stp') else False,
            "usages": [str(u.value) for u in network.usages] if network.usages else [],
        }

    @require_connection
    def list_vnics(self, name_or_id: str) -> List[Dict]:
        """列出 VM 的网卡"""
        vm = self.ovirt._find_vm(name_or_id)
        if not vm: raise ValueError(f"VM not found: {name_or_id}")

        nics_service = self.connection.system_service().vms_service().vm_service(vm["id"]).nics_service()
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

    @require_connection
    def add_nic(self, name_or_id: str, nic_name: str, network: str,
               interface: str = "virtio") -> Dict[str, Any]:
        """添加网卡"""
        vm = self.ovirt._find_vm(name_or_id)
        if not vm:
            raise ValueError(f"VM 不存在: {name_or_id}")

        # 查找网络
        net = self._find_network(network)

        nics_service = self.connection.system_service().vms_service().vm_service(vm["id"]).nics_service()

        try:
            nic = nics_service.add(
                sdk.types.Nic(
                    name=nic_name,
                    interface=sdk.types.NicInterface(interface),
                    network=sdk.types.Network(id=net.id) if net else None,
                )
            )
            return {"success": True, "message": f"网卡 {nic_name} 已添加", "nic_id": nic.id}
        except Exception as e:
            raise RuntimeError(f"添加网卡失败: {e}")

    @require_connection
    def remove_nic(self, name_or_id: str, nic_name: str) -> Dict[str, Any]:
        """移除网卡"""
        vm = self.ovirt._find_vm(name_or_id)
        if not vm:
            raise ValueError(f"VM 不存在: {name_or_id}")

        nics_service = self.connection.system_service().vms_service().vm_service(vm["id"]).nics_service()
        nics = nics_service.list()

        nic_id = None
        for n in nics:
            if n.name == nic_name:
                nic_id = n.id
                break

        if not nic_id:
            raise ValueError(f"网卡不存在: {nic_name}")

        nics_service.nic_service(nic_id).remove()
        return {"success": True, "message": f"网卡 {nic_name} 已移除"}

    @require_connection
    def create_network(self, name: str, datacenter: str, vlan: str = None,
                      description: str = "", mtu: int = 0) -> Dict[str, Any]:
        """创建网络"""
        # 获取数据中心
        dcs = self.connection.system_service().data_centers_service().list(search=f"name={_sanitize_search_value(datacenter)}")
        if not dcs: raise ValueError(f"数据中心不存在: {datacenter}")

        # 创建网络
        network = self.connection.system_service().networks_service().add(
            sdk.types.Network(
                name=name,
                description=description,
                data_center=sdk.types.DataCenter(id=dcs[0].id),
                vlan=sdk.types.Vlan(id=int(vlan)) if vlan else None,
                mtu=mtu if mtu > 0 else None,
            )
        )

        return {"success": True, "message": f"网络 {name} 已创建", "network_id": network.id}

    @require_connection
    def update_network(self, name: str, new_name: str = None, description: str = None,
                      mtu: int = None) -> Dict[str, Any]:
        """更新网络"""
        networks = self.connection.system_service().networks_service().list(search=f"name={_sanitize_search_value(name)}")
        if not networks: raise ValueError(f"网络不存在: {name}")

        network_service = self.connection.system_service().networks_service().network_service(networks[0].id)
        network = network_service.get()

        if new_name:
            network.name = new_name
        if description is not None:
            network.description = description
        if mtu is not None:
            network.mtu = mtu

        network_service.update(network)

        return {"success": True, "message": f"网络已更新"}

    @require_connection
    def delete_network(self, name: str) -> Dict[str, Any]:
        """删除网络"""
        networks = self.connection.system_service().networks_service().list(search=f"name={_sanitize_search_value(name)}")
        if not networks: raise ValueError(f"网络不存在: {name}")

        self.connection.system_service().networks_service().network_service(networks[0].id).remove()

        return {"success": True, "message": f"网络 {name} 已删除"}

    # ── VNIC Profile 管理 ──────────────────────────────────────────────────

    @require_connection
    def list_vnic_profiles(self, network: str = None) -> List[Dict]:
        """列出 VNIC Profile

        Args:
            network: 网络名称（可选）

        Returns:
            VNIC Profile 列表
        """
        profiles_service = self.connection.system_service().vnic_profiles_service()

        search = None
        if network:
            search = f"network={_sanitize_search_value(network)}"

        try:
            profiles = profiles_service.list(search=search)
        except Exception as e:
            logger.error(f"获取 VNIC Profile 列表失败: {e}")
            return []

        return [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description or "",
                "network": p.network.name if p.network else "",
                "network_id": p.network.id if p.network else "",
                "pass_through": str(p.pass_through.value) if hasattr(p, 'pass_through') and p.pass_through else "disabled",
                "port_mirroring": p.port_mirroring if hasattr(p, 'port_mirroring') else False,
            }
            for p in profiles
        ]

    @require_connection
    def get_vnic_profile(self, name_or_id: str) -> Optional[Dict]:
        """获取 VNIC Profile 详情

        Args:
            name_or_id: Profile 名称或 ID

        Returns:
            Profile 详情
        """
        profiles_service = self.connection.system_service().vnic_profiles_service()

        try:
            profile = profiles_service.vnic_profile_service(name_or_id).get()
            if profile:
                return self._format_vnic_profile(profile)
        except Exception:
            pass

        profiles = profiles_service.list(search=f"name={_sanitize_search_value(name_or_id)}")
        if not profiles:
            return None

        return self._format_vnic_profile(profiles[0])

    def _format_vnic_profile(self, profile) -> Dict:
        """格式化 VNIC Profile"""
        return {
            "id": profile.id,
            "name": profile.name,
            "description": profile.description or "",
            "network": profile.network.name if profile.network else "",
            "network_id": profile.network.id if profile.network else "",
            "pass_through": str(profile.pass_through.value) if hasattr(profile, 'pass_through') and profile.pass_through else "disabled",
            "port_mirroring": profile.port_mirroring if hasattr(profile, 'port_mirroring') else False,
            "custom_properties": [
                {"name": cp.name, "value": cp.value}
                for cp in profile.custom_properties
            ] if hasattr(profile, 'custom_properties') and profile.custom_properties else [],
        }

    @require_connection
    def create_vnic_profile(self, name: str, network: str,
                           description: str = "",
                           port_mirroring: bool = False) -> Dict[str, Any]:
        """创建 VNIC Profile

        Args:
            name: Profile 名称
            network: 网络名称
            description: 描述
            port_mirroring: 是否启用端口镜像

        Returns:
            创建结果
        """
        # 查找网络
        net = self._find_network(network)
        if not net:
            raise ValueError(f"网络不存在: {network}")

        profiles_service = self.connection.system_service().vnic_profiles_service()

        try:
            profile = profiles_service.add(
                sdk.types.VnicProfile(
                    name=name,
                    description=description,
                    network=sdk.types.Network(id=net.id),
                    port_mirroring=port_mirroring,
                )
            )
            return {
                "success": True,
                "message": f"VNIC Profile {name} 已创建",
                "profile_id": profile.id,
            }
        except Exception as e:
            raise RuntimeError(f"创建 VNIC Profile 失败: {e}")

    @require_connection
    def update_vnic_profile(self, name_or_id: str, new_name: str = None,
                           description: str = None,
                           port_mirroring: bool = None) -> Dict[str, Any]:
        """更新 VNIC Profile

        Args:
            name_or_id: Profile 名称或 ID
            new_name: 新名称
            description: 新描述
            port_mirroring: 端口镜像设置

        Returns:
            更新结果
        """
        profiles_service = self.connection.system_service().vnic_profiles_service()

        # 查找 profile
        profile_id = None
        try:
            profile_service = profiles_service.vnic_profile_service(name_or_id)
            profile = profile_service.get()
            profile_id = name_or_id
        except Exception:
            profiles = profiles_service.list(search=f"name={_sanitize_search_value(name_or_id)}")
            if not profiles:
                raise ValueError(f"VNIC Profile 不存在: {name_or_id}")
            profile_id = profiles[0].id
            profile = profiles[0]
            profile_service = profiles_service.vnic_profile_service(profile_id)

        if new_name:
            profile.name = new_name
        if description is not None:
            profile.description = description
        if port_mirroring is not None:
            profile.port_mirroring = port_mirroring

        profile_service.update(profile)
        return {"success": True, "message": f"VNIC Profile 已更新"}

    @require_connection
    def delete_vnic_profile(self, name_or_id: str) -> Dict[str, Any]:
        """删除 VNIC Profile

        Args:
            name_or_id: Profile 名称或 ID

        Returns:
            删除结果
        """
        profiles_service = self.connection.system_service().vnic_profiles_service()

        # 查找 profile
        profile_id = None
        try:
            profile_service = profiles_service.vnic_profile_service(name_or_id)
            profile_service.get()
            profile_id = name_or_id
        except Exception:
            profiles = profiles_service.list(search=f"name={_sanitize_search_value(name_or_id)}")
            if not profiles:
                raise ValueError(f"VNIC Profile 不存在: {name_or_id}")
            profile_id = profiles[0].id

        profiles_service.vnic_profile_service(profile_id).remove()
        return {"success": True, "message": f"VNIC Profile 已删除"}

    # ── Network Filter 管理 ────────────────────────────────────────────────

    @require_connection
    def list_network_filters(self) -> List[Dict]:
        """列出网络过滤器

        Returns:
            网络过滤器列表
        """
        filters_service = self.connection.system_service().network_filters_service()

        try:
            filters = filters_service.list()
        except Exception as e:
            logger.error(f"获取网络过滤器列表失败: {e}")
            return []

        return [
            {
                "id": f.id,
                "name": f.name,
                "version": f.version if hasattr(f, 'version') else "",
            }
            for f in filters
        ]

    # ── MAC Pool 管理 ──────────────────────────────────────────────────────

    @require_connection
    def list_mac_pools(self) -> List[Dict]:
        """列出 MAC 地址池

        Returns:
            MAC 地址池列表
        """
        pools_service = self.connection.system_service().mac_pools_service()

        try:
            pools = pools_service.list()
        except Exception as e:
            logger.error(f"获取 MAC 地址池列表失败: {e}")
            return []

        return [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description or "",
                "allow_duplicates": p.allow_duplicates if hasattr(p, 'allow_duplicates') else False,
                "ranges": [
                    {"from": r.from_, "to": r.to}
                    for r in p.ranges
                ] if p.ranges else [],
            }
            for p in pools
        ]

    # ── QoS 管理 ────────────────────────────────────────────────────────────

    @require_connection
    def list_qos(self, datacenter: str = None) -> List[Dict]:
        """列出 QoS 配置

        Args:
            datacenter: 数据中心名称（可选）

        Returns:
            QoS 列表
        """
        qos_service = self.connection.system_service().qoss_service()

        try:
            qoss = qos_service.list()
        except Exception as e:
            logger.error(f"获取 QoS 列表失败: {e}")
            return []

        result = []
        for qos in qoss:
            # 过滤数据中心
            if datacenter and qos.data_center:
                if qos.data_center.name != datacenter:
                    continue

            result.append({
                "id": qos.id,
                "name": qos.name,
                "description": qos.description or "",
                "datacenter": qos.data_center.name if qos.data_center else "",
                "type": str(qos.type_.value) if hasattr(qos, 'type_') and qos.type_ else "",
                "max_inbound": qos.max_inbound if hasattr(qos, 'max_inbound') else 0,
                "max_outbound": qos.max_outbound if hasattr(qos, 'max_outbound') else 0,
            })

        return result


class ClusterMCP(BaseMCP):
    """集群管理 MCP"""

    def __init__(self, ovirt_mcp):
        super().__init__(ovirt_mcp)

    def list_clusters(self) -> List[Dict]:
        """列出集群"""
        return self.ovirt.list_clusters()

    @require_connection
    def get_cluster(self, name: str) -> Optional[Dict]:
        """获取集群详情"""
        clusters = self.connection.system_service().clusters_service().list(search=f"name={_sanitize_search_value(name)}")
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
            "status": str(c.status.value) if c.status else "up",
            "data_center": c.data_center.name if c.data_center else "",
            "data_center_id": c.data_center.id if c.data_center else "",
            "gluster_service": c.gluster_service if hasattr(c, 'gluster_service') else False,
            "virt_service": c.virt_service if hasattr(c, 'virt_service') else True,
            "threads_per_core": c.threads_per_core if hasattr(c, 'threads_per_core') else 1,
            "ha_reservation": c.ha_reservation if hasattr(c, 'ha_reservation') else False,
            "trusted_service": c.trusted_service if hasattr(c, 'trusted_service') else False,
        }

    @require_connection
    def create_cluster(self, name: str, datacenter: str, cpu_type: str,
                      description: str = "",
                      gluster_service: bool = False,
                      threads_per_core: int = 1) -> Dict[str, Any]:
        """创建集群

        Args:
            name: 集群名称
            datacenter: 数据中心名称
            cpu_type: CPU 类型
            description: 描述
            gluster_service: 是否启用 Gluster 服务
            threads_per_core: 每核心线程数

        Returns:
            创建结果
        """
        # 查找数据中心
        dcs = self.connection.system_service().data_centers_service().list(
            search=f"name={_sanitize_search_value(datacenter)}"
        )
        if not dcs:
            raise ValueError(f"数据中心不存在: {datacenter}")

        clusters_service = self.connection.system_service().clusters_service()

        # 检查是否已存在
        existing = clusters_service.list(search=f"name={_sanitize_search_value(name)}")
        if existing:
            raise ValueError(f"集群已存在: {name}")

        try:
            cluster = clusters_service.add(
                sdk.types.Cluster(
                    name=name,
                    description=description,
                    data_center=sdk.types.DataCenter(id=dcs[0].id),
                    cpu=sdk.types.Cpu(
                        architecture=sdk.types.Architecture.X86_64,
                        type=cpu_type,
                    ),
                    gluster_service=gluster_service,
                    threads_per_core=threads_per_core,
                )
            )

            return {
                "success": True,
                "message": f"集群 {name} 已创建",
                "cluster_id": cluster.id,
            }
        except Exception as e:
            raise RuntimeError(f"创建集群失败: {e}")

    @require_connection
    def update_cluster(self, name_or_id: str, new_name: str = None,
                      description: str = None,
                      threads_per_core: int = None) -> Dict[str, Any]:
        """更新集群

        Args:
            name_or_id: 集群名称或 ID
            new_name: 新名称
            description: 新描述
            threads_per_core: 每核心线程数

        Returns:
            更新结果
        """
        cluster = self._find_cluster(name_or_id)
        if not cluster:
            raise ValueError(f"集群不存在: {name_or_id}")

        clusters_service = self.connection.system_service().clusters_service()
        cluster_service = clusters_service.cluster_service(cluster.id)

        if new_name:
            cluster.name = new_name
        if description is not None:
            cluster.description = description
        if threads_per_core is not None:
            cluster.threads_per_core = threads_per_core

        try:
            cluster_service.update(cluster)
            return {"success": True, "message": f"集群已更新"}
        except Exception as e:
            raise RuntimeError(f"更新集群失败: {e}")

    @require_connection
    def delete_cluster(self, name_or_id: str) -> Dict[str, Any]:
        """删除集群

        Args:
            name_or_id: 集群名称或 ID

        Returns:
            删除结果
        """
        cluster = self._find_cluster(name_or_id)
        if not cluster:
            raise ValueError(f"集群不存在: {name_or_id}")

        clusters_service = self.connection.system_service().clusters_service()
        cluster_service = clusters_service.cluster_service(cluster.id)

        try:
            cluster_service.remove()
            return {"success": True, "message": f"集群 {cluster.name} 已删除"}
        except Exception as e:
            raise RuntimeError(f"删除集群失败: {e}")

    def list_cluster_hosts(self, name: str) -> List[Dict]:
        """列出集群主机"""
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

    # ── CPU Profile 管理 ────────────────────────────────────────────────────

    @require_connection
    def list_cpu_profiles(self, cluster: str) -> List[Dict]:
        """列出集群的 CPU Profile

        Args:
            cluster: 集群名称或 ID

        Returns:
            CPU Profile 列表
        """
        cluster_obj = self._find_cluster(cluster)
        if not cluster_obj:
            raise ValueError(f"集群不存在: {cluster}")

        cluster_service = self.connection.system_service().clusters_service().cluster_service(cluster_obj.id)
        profiles_service = cluster_service.cpu_profiles_service()

        try:
            profiles = profiles_service.list()
        except Exception as e:
            logger.error(f"获取 CPU Profile 列表失败: {e}")
            return []

        return [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description or "",
                "cluster": cluster_obj.name,
            }
            for p in profiles
        ]

    @require_connection
    def get_cpu_profile(self, cluster: str, name_or_id: str) -> Optional[Dict]:
        """获取 CPU Profile 详情

        Args:
            cluster: 集群名称或 ID
            name_or_id: Profile 名称或 ID

        Returns:
            CPU Profile 详情
        """
        cluster_obj = self._find_cluster(cluster)
        if not cluster_obj:
            raise ValueError(f"集群不存在: {cluster}")

        cluster_service = self.connection.system_service().clusters_service().cluster_service(cluster_obj.id)
        profiles_service = cluster_service.cpu_profiles_service()

        try:
            profile = profiles_service.cpu_profile_service(name_or_id).get()
            return {
                "id": profile.id,
                "name": profile.name,
                "description": profile.description or "",
                "cluster": cluster_obj.name,
                "cluster_id": cluster_obj.id,
            }
        except Exception:
            profiles = profiles_service.list(search=f"name={_sanitize_search_value(name_or_id)}")
            if not profiles:
                return None
            profile = profiles[0]
            return {
                "id": profile.id,
                "name": profile.name,
                "description": profile.description or "",
                "cluster": cluster_obj.name,
                "cluster_id": cluster_obj.id,
            }


class TemplateMCP(BaseMCP):
    """模板管理 MCP"""

    def __init__(self, ovirt_mcp):
        super().__init__(ovirt_mcp)

    def list_templates(self, cluster: str = None) -> List[Dict]:
        """列出模板"""
        return self.ovirt.list_templates(cluster)

    @require_connection
    def get_template(self, name: str) -> Optional[Dict]:
        """获取模板详情"""
        templates = self.connection.system_service().templates_service().list(search=f"name={_sanitize_search_value(name)}")
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
    "network_get": {"method": "get_network", "description": "获取网络详情"},
    "network_create": {"method": "create_network", "description": "创建网络"},
    "network_update": {"method": "update_network", "description": "更新网络"},
    "network_delete": {"method": "delete_network", "description": "删除网络"},
    "nic_list": {"method": "list_vnics", "description": "列出网卡"},
    "nic_add": {"method": "add_nic", "description": "添加网卡"},
    "nic_remove": {"method": "remove_nic", "description": "移除网卡"},

    # VNIC Profile 管理
    "vnic_profile_list": {"method": "list_vnic_profiles", "description": "列出 VNIC Profile"},
    "vnic_profile_get": {"method": "get_vnic_profile", "description": "获取 VNIC Profile 详情"},
    "vnic_profile_create": {"method": "create_vnic_profile", "description": "创建 VNIC Profile"},
    "vnic_profile_update": {"method": "update_vnic_profile", "description": "更新 VNIC Profile"},
    "vnic_profile_delete": {"method": "delete_vnic_profile", "description": "删除 VNIC Profile"},

    # Network Filter 管理
    "network_filter_list": {"method": "list_network_filters", "description": "列出网络过滤器"},

    # MAC Pool 管理
    "mac_pool_list": {"method": "list_mac_pools", "description": "列出 MAC 地址池"},

    # QoS 管理
    "qos_list": {"method": "list_qos", "description": "列出 QoS 配置"},

    # 主机管理
    "host_list": {"method": "list_hosts", "description": "列出主机"},
    "host_activate": {"method": "activate_host", "description": "激活主机"},
    "host_deactivate": {"method": "deactivate_host", "description": "维护主机"},

    # 集群管理
    "cluster_list": {"method": "list_clusters", "description": "列出集群"},
    "cluster_get": {"method": "get_cluster", "description": "获取集群详情"},
    "cluster_create": {"method": "create_cluster", "description": "创建集群"},
    "cluster_update": {"method": "update_cluster", "description": "更新集群"},
    "cluster_delete": {"method": "delete_cluster", "description": "删除集群"},
    "cluster_hosts": {"method": "list_cluster_hosts", "description": "集群主机"},
    "cluster_vms": {"method": "list_cluster_vms", "description": "集群 VM"},
    "cluster_cpu_load": {"method": "get_cluster_cpu_load", "description": "集群 CPU 负载"},
    "cluster_memory_usage": {"method": "get_cluster_memory_usage", "description": "集群内存使用"},

    # CPU Profile 管理
    "cpu_profile_list": {"method": "list_cpu_profiles", "description": "列出 CPU Profile"},
    "cpu_profile_get": {"method": "get_cpu_profile", "description": "获取 CPU Profile 详情"},

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
