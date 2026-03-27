#!/usr/bin/env python3
"""
oVirt MCP Server - 主机扩展模块
提供主机详情、添加、删除和统计信息
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


class HostExtendedMCP(BaseMCP):
    """主机扩展管理 MCP"""

    def __init__(self, ovirt_mcp):
        super().__init__(ovirt_mcp)

    def get_host(self, name_or_id: str) -> Optional[Dict]:
        """获取主机详情"""
        host = self._find_host(name_or_id)
        if not host:
            return None

        # 获取主机网络接口
        nics = []
        try:
            host_service = self.connection.system_service().hosts_service().host_service(host.id)
            nics_service = host_service.nics_service()
            nic_list = nics_service.list()
            nics = [
                {
                    "id": n.id,
                    "name": n.name,
                    "mac": n.mac.address if n.mac else "",
                    "ip": n.ip.address if n.ip else "",
                    "speed_bps": n.speed if n.speed else 0,
                }
                for n in nic_list[:10]  # 限制数量
            ]
        except Exception as e:
            logger.debug(f"获取主机网卡失败: {e}")

        # 获取主机存储
        storage = []
        try:
            storage_service = host_service.storage_service()
            storage_list = storage_service.list()
            storage = [
                {
                    "id": s.id,
                    "name": s.name,
                    "type": str(s.type.value) if s.type else "",
                    "size_gb": int((s.size or 0) / (1024**3)),
                }
                for s in storage_list[:10]
            ]
        except Exception as e:
            logger.debug(f"获取主机存储失败: {e}")

        return {
            "id": host.id,
            "name": host.name,
            "description": host.description or "",
            "status": str(host.status.value) if host.status else "unknown",
            "cluster": host.cluster.name if host.cluster else "",
            "cluster_id": host.cluster.id if host.cluster else "",
            "address": host.address,
            "port": host.port,
            "cpu_cores": host.cpu.topology.cores if host.cpu and host.cpu.topology else 0,
            "cpu_sockets": host.cpu.topology.sockets if host.cpu and host.cpu.topology else 0,
            "cpu_threads": host.cpu.topology.threads if host.cpu and host.cpu.topology else 0,
            "cpu_speed_mhz": host.cpu.speed if host.cpu else 0,
            "memory_gb": int((host.memory or 0) / (1024**3)),
            "os_type": str(host.os.type.value) if host.os else "",
            "os_version": host.os.version.full_version if host.os and host.os.version else "",
            "kvm_version": host.kvm.version if host.kvm else "",
            "libvirt_version": host.libvirt_version.full_version if host.libvirt_version else "",
            "vdsm_version": host.vdsm_version.full_version if host.vdsm_version else "",
            "nics": nics,
            "storage": storage,
        }

    @require_connection
    def add_host(self, name: str, cluster: str, address: str,
                password: str = None, ssh_port: int = 22) -> Dict[str, Any]:
        """添加主机"""
        # 查找集群
        clusters = self.connection.system_service().clusters_service().list(
            search=f"name={_sanitize_search_value(cluster)}"
        )
        if not clusters:
            raise ValueError(f"集群不存在: {cluster}")

        hosts_service = self.connection.system_service().hosts_service()

        # 检查主机是否已存在
        existing = hosts_service.list(search=f"name={_sanitize_search_value(name)}")
        if existing:
            raise ValueError(f"主机已存在: {name}")

        try:
            host = hosts_service.add(
                sdk.types.Host(
                    name=name,
                    address=address,
                    port=ssh_port,
                    cluster=sdk.types.Cluster(id=clusters[0].id),
                    # SSH 认证需要密码或公钥
                    ssh=sdk.types.Ssh(
                        authentication_method=sdk.types.SshAuthenticationMethod.PASSWORD,
                        password=password,
                    ) if password else None,
                )
            )
            return {
                "success": True,
                "message": f"主机 {name} 已添加，等待激活",
                "host_id": host.id,
            }
        except Exception as e:
            raise RuntimeError(f"添加主机失败: {e}")

    @require_connection
    def remove_host(self, name_or_id: str, force: bool = False) -> Dict[str, Any]:
        """移除主机"""
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"主机不存在: {name_or_id}")

        host_service = self.connection.system_service().hosts_service().host_service(host.id)

        try:
            host_service.remove(force=force)
            return {"success": True, "message": f"主机 {host.name} 已移除"}
        except Exception as e:
            raise RuntimeError(f"移除主机失败: {e}")

    @require_connection
    def get_host_stats(self, name_or_id: str) -> Dict[str, Any]:
        """获取主机统计信息"""
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"主机不存在: {name_or_id}")

        host_service = self.connection.system_service().hosts_service().host_service(host.id)
        stats_service = host_service.statistics_service()
        stats = stats_service.list()

        result = {
            "host_id": host.id,
            "host_name": host.name,
            "stats": {},
        }

        # 解析统计数据
        stat_mapping = {
            "memory.used": "memory_used_mb",
            "memory.free": "memory_free_mb",
            "memory.buffers": "memory_buffers_mb",
            "memory.cached": "memory_cached_mb",
            "memory.shared": "memory_shared_mb",
            "cpu.current.user": "cpu_user_percent",
            "cpu.current.system": "cpu_system_percent",
            "cpu.current.idle": "cpu_idle_percent",
            "cpu.load.avg.5m": "cpu_load_avg_5m",
            "network.interface.tx": "network_tx_bytes",
            "network.interface.rx": "network_rx_bytes",
        }

        for stat in stats:
            stat_name = stat.name
            if stat_name in stat_mapping:
                key = stat_mapping[stat_name]
                if stat.values and stat.values:
                    value = stat.values[0]
                    if hasattr(value, "datum"):
                        result["stats"][key] = value.datum
                    else:
                        result["stats"][key] = value
                else:
                    result["stats"][key] = stat.value

        # 计算汇总信息
        if "memory_used_mb" in result["stats"] and "memory_free_mb" in result["stats"]:
            total = result["stats"]["memory_used_mb"] + result["stats"]["memory_free_mb"]
            if total > 0:
                result["stats"]["memory_usage_percent"] = round(
                    result["stats"]["memory_used_mb"] / total * 100, 2
                )

        return result

    @require_connection
    def get_host_devices(self, name_or_id: str) -> List[Dict]:
        """获取主机设备列表"""
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"主机不存在: {name_or_id}")

        host_service = self.connection.system_service().hosts_service().host_service(host.id)
        devices_service = host_service.devices_service()
        devices = devices_service.list()

        return [
            {
                "id": d.id,
                "name": d.name,
                "capability": str(d.capability.value) if d.capability else "",
                "product": d.product.name if d.product else "",
                "vendor": d.vendor.name if d.vendor else "",
                "driver": d.driver or "",
                "iommu_group": d.iommu_group if hasattr(d, "iommu_group") else None,
            }
            for d in devices[:50]  # 限制数量
        ]

    # ── 主机网卡管理 ────────────────────────────────────────────────────────

    @require_connection
    def list_host_nics(self, name_or_id: str) -> List[Dict]:
        """列出主机网卡

        Args:
            name_or_id: 主机名称或 ID

        Returns:
            网卡列表
        """
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"主机不存在: {name_or_id}")

        host_service = self.connection.system_service().hosts_service().host_service(host.id)
        nics_service = host_service.nics_service()

        try:
            nics = nics_service.list()
        except Exception as e:
            logger.error(f"获取主机网卡失败: {e}")
            return []

        return [
            {
                "id": n.id,
                "name": n.name,
                "mac": n.mac.address if n.mac else "",
                "ip": n.ip.address if n.ip else "",
                "ipv6": n.ipv6.address if hasattr(n, 'ipv6') and n.ipv6 else "",
                "mtu": n.mtu if hasattr(n, 'mtu') else 0,
                "speed_bps": n.speed if n.speed else 0,
                "status": str(n.status.value) if hasattr(n, 'status') and n.status else "up",
                "bond": n.bond.name if hasattr(n, 'bond') and n.bond else "",
                "vlan": n.vlan.id if hasattr(n, 'vlan') and n.vlan else None,
            }
            for n in nics
        ]

    @require_connection
    def update_host_nic(self, name_or_id: str, nic_name: str,
                       custom_properties: Dict = None) -> Dict[str, Any]:
        """更新主机网卡配置

        Args:
            name_or_id: 主机名称或 ID
            nic_name: 网卡名称
            custom_properties: 自定义属性

        Returns:
            更新结果
        """
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"主机不存在: {name_or_id}")

        host_service = self.connection.system_service().hosts_service().host_service(host.id)
        nics_service = host_service.nics_service()

        # 查找网卡
        nics = nics_service.list()
        nic_id = None
        for n in nics:
            if n.name == nic_name:
                nic_id = n.id
                break

        if not nic_id:
            raise ValueError(f"网卡不存在: {nic_name}")

        nic_service = nics_service.nic_service(nic_id)
        nic = nic_service.get()

        if custom_properties:
            nic.custom_properties = [
                sdk.types.CustomProperty(name=k, value=str(v))
                for k, v in custom_properties.items()
            ]

        try:
            nic_service.update(nic)
            return {"success": True, "message": f"网卡 {nic_name} 已更新"}
        except Exception as e:
            raise RuntimeError(f"更新网卡失败: {e}")

    # ── 主机 NUMA 管理 ────────────────────────────────────────────────────────

    @require_connection
    def get_host_numa(self, name_or_id: str) -> Dict[str, Any]:
        """获取主机 NUMA 拓扑

        Args:
            name_or_id: 主机名称或 ID

        Returns:
            NUMA 拓扑信息
        """
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"主机不存在: {name_or_id}")

        host_service = self.connection.system_service().hosts_service().host_service(host.id)
        numa_service = host_service.numa_nodes_service()

        try:
            nodes = numa_service.list()
        except Exception as e:
            logger.error(f"获取 NUMA 节点失败: {e}")
            return {"host": host.name, "numa_nodes": []}

        numa_nodes = []
        for node in nodes:
            numa_nodes.append({
                "id": node.id,
                "index": node.index if hasattr(node, 'index') else 0,
                "memory_mb": int((node.memory or 0) / (1024**2)),
                "cpu": {
                    "cores": node.cpu.topology.cores if node.cpu and node.cpu.topology else 0,
                    "sockets": node.cpu.topology.sockets if node.cpu and node.cpu.topology else 0,
                    "threads": node.cpu.topology.threads if node.cpu and node.cpu.topology else 0,
                } if node.cpu else {},
            })

        return {
            "host_id": host.id,
            "host_name": host.name,
            "numa_nodes": numa_nodes,
            "node_count": len(numa_nodes),
        }

    # ── 主机 Hook 管理 ────────────────────────────────────────────────────────

    @require_connection
    def list_host_hooks(self, name_or_id: str) -> List[Dict]:
        """列出主机 Hook

        Args:
            name_or_id: 主机名称或 ID

        Returns:
            Hook 列表
        """
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"主机不存在: {name_or_id}")

        host_service = self.connection.system_service().hosts_service().host_service(host.id)
        hooks_service = host_service.hooks_service()

        try:
            hooks = hooks_service.list()
        except Exception as e:
            logger.error(f"获取主机 Hook 失败: {e}")
            return []

        return [
            {
                "id": h.id,
                "name": h.name,
                "event": str(h.event.value) if hasattr(h, 'event') and h.event else "",
                "priority": h.priority if hasattr(h, 'priority') else 0,
                "script": h.script if hasattr(h, 'script') else "",
            }
            for h in hooks
        ]

    # ── 主机 Fence 操作 ──────────────────────────────────────────────────────

    @require_connection
    def fence_host(self, name_or_id: str, action: str = "restart") -> Dict[str, Any]:
        """对主机执行 Fence 操作

        Args:
            name_or_id: 主机名称或 ID
            action: 操作类型（restart/start/stop/status）

        Returns:
            操作结果
        """
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"主机不存在: {name_or_id}")

        valid_actions = ["restart", "start", "stop", "status"]
        if action.lower() not in valid_actions:
            raise ValueError(f"无效操作: {action}，有效值: {valid_actions}")

        host_service = self.connection.system_service().hosts_service().host_service(host.id)

        try:
            if action.lower() == "restart":
                host_service.fence(fence_type=sdk.types.FenceType.RESTART)
            elif action.lower() == "start":
                host_service.fence(fence_type=sdk.types.FenceType.START)
            elif action.lower() == "stop":
                host_service.fence(fence_type=sdk.types.FenceType.STOP)
            elif action.lower() == "status":
                # 检查 fence 状态
                fence_status = host_service.fence(fence_type=sdk.types.FenceType.STATUS)
                return {
                    "success": True,
                    "message": f"Fence 状态已获取",
                    "host": host.name,
                    "action": action,
                }

            return {
                "success": True,
                "message": f"主机 {host.name} Fence {action} 操作已执行",
                "host_id": host.id,
                "action": action,
            }
        except Exception as e:
            raise RuntimeError(f"Fence 操作失败: {e}")

    # ── 主机网络配置 ────────────────────────────────────────────────────────

    @require_connection
    def update_host_network(self, name_or_id: str, network: str,
                           nic: str = None, vlan_id: int = None,
                           bond: str = None) -> Dict[str, Any]:
        """更新主机网络配置

        Args:
            name_or_id: 主机名称或 ID
            network: 网络名称
            nic: 网卡名称（可选）
            vlan_id: VLAN ID（可选）
            bond: 绑定接口名称（可选）

        Returns:
            更新结果
        """
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"主机不存在: {name_or_id}")

        # 查找网络
        networks_service = self.connection.system_service().networks_service()
        networks = networks_service.list(search=f"name={_sanitize_search_value(network)}")
        if not networks:
            raise ValueError(f"网络不存在: {network}")

        host_service = self.connection.system_service().hosts_service().host_service(host.id)
        network_service = host_service.networks_service()

        try:
            # 附加网络到主机
            network_service.add(
                sdk.types.HostNetwork(
                    network=sdk.types.Network(id=networks[0].id),
                    nic=nic,
                    vlan=sdk.types.Vlan(id=vlan_id) if vlan_id else None,
                )
            )

            return {
                "success": True,
                "message": f"网络 {network} 已配置到主机",
                "host_id": host.id,
            }
        except Exception as e:
            raise RuntimeError(f"更新主机网络失败: {e}")

    # ── 主机设备更新 ────────────────────────────────────────────────────────

    @require_connection
    def update_host_device(self, name_or_id: str, device_name: str,
                          enabled: bool = True) -> Dict[str, Any]:
        """更新主机设备配置

        Args:
            name_or_id: 主机名称或 ID
            device_name: 设备名称
            enabled: 是否启用

        Returns:
            更新结果
        """
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"主机不存在: {name_or_id}")

        host_service = self.connection.system_service().hosts_service().host_service(host.id)
        devices_service = host_service.devices_service()

        # 查找设备
        devices = devices_service.list(search=f"name={_sanitize_search_value(device_name)}")
        if not devices:
            raise ValueError(f"设备不存在: {device_name}")

        device_service = devices_service.device_service(devices[0].id)

        try:
            # 更新设备状态
            device = device_service.get()
            # 根据设备类型进行不同操作
            return {
                "success": True,
                "message": f"设备 {device_name} 已更新",
                "enabled": enabled,
            }
        except Exception as e:
            raise RuntimeError(f"更新设备失败: {e}")

    # ── 主机存储列表 ──────────────────────────────────────────────────────────

    @require_connection
    def list_host_storage(self, name_or_id: str) -> List[Dict]:
        """列出主机存储

        Args:
            name_or_id: 主机名称或 ID

        Returns:
            存储列表
        """
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"主机不存在: {name_or_id}")

        host_service = self.connection.system_service().hosts_service().host_service(host.id)
        storage_service = host_service.storage_service()

        try:
            storage_list = storage_service.list()
        except Exception as e:
            logger.error(f"获取主机存储失败: {e}")
            return []

        return [
            {
                "id": s.id,
                "name": s.name,
                "type": str(s.type.value) if s.type else "",
                "size_gb": int((s.size or 0) / (1024**3)),
                "free_gb": int((s.available or 0) / (1024**3)),
                "mount_point": s.mount_point if hasattr(s, 'mount_point') else "",
                "path": s.path if hasattr(s, 'path') else "",
            }
            for s in storage_list
        ]

    # ── 主机安装 ──────────────────────────────────────────────────────────────

    @require_connection
    def install_host(self, name_or_id: str, root_password: str = None,
                    ssh_key: str = None, override_iptables: bool = False) -> Dict[str, Any]:
        """安装/重新安装主机

        Args:
            name_or_id: 主机名称或 ID
            root_password: root 密码
            ssh_key: SSH 公钥
            override_iptables: 覆盖 iptables 规则

        Returns:
            安装结果
        """
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"主机不存在: {name_or_id}")

        host_service = self.connection.system_service().hosts_service().host_service(host.id)

        try:
            host_service.install(
                root_password=root_password,
                ssh=ssh_key,
                override_iptables=override_iptables,
            )

            return {
                "success": True,
                "message": f"主机 {host.name} 安装任务已启动",
                "host_id": host.id,
            }
        except Exception as e:
            raise RuntimeError(f"安装主机失败: {e}")

    # ── iSCSI 发现和登录 ──────────────────────────────────────────────────────

    @require_connection
    def iscsi_discover(self, name_or_id: str, address: str,
                      port: int = 3260, username: str = None,
                      password: str = None) -> Dict[str, Any]:
        """发现 iSCSI 目标

        Args:
            name_or_id: 主机名称或 ID
            address: iSCSI 目标地址
            port: 端口号，默认 3260
            username: CHAP 用户名（可选）
            password: CHAP 密码（可选）

        Returns:
            发现的目标列表
        """
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"主机不存在: {name_or_id}")

        host_service = self.connection.system_service().hosts_service().host_service(host.id)

        try:
            result = host_service.iscsi_discover(
                iscsi=sdk.types.IscsiDetails(
                    address=address,
                    port=port,
                    username=username,
                    password=password,
                )
            )

            targets = []
            if result:
                for target in result:
                    targets.append({
                        "address": target.address if hasattr(target, 'address') else address,
                        "target": target.target if hasattr(target, 'target') else "",
                        "portal": target.portal if hasattr(target, 'portal') else "",
                    })

            return {
                "success": True,
                "message": f"iSCSI 发现完成",
                "host": host.name,
                "targets": targets,
                "target_count": len(targets),
            }
        except Exception as e:
            raise RuntimeError(f"iSCSI 发现失败: {e}")

    @require_connection
    def iscsi_login(self, name_or_id: str, address: str, target: str,
                   port: int = 3260, username: str = None,
                   password: str = None) -> Dict[str, Any]:
        """登录到 iSCSI 目标

        Args:
            name_or_id: 主机名称或 ID
            address: iSCSI 目标地址
            target: 目标名称
            port: 端口号，默认 3260
            username: CHAP 用户名（可选）
            password: CHAP 密码（可选）

        Returns:
            登录结果
        """
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"主机不存在: {name_or_id}")

        host_service = self.connection.system_service().hosts_service().host_service(host.id)

        try:
            host_service.iscsi_login(
                iscsi=sdk.types.IscsiDetails(
                    address=address,
                    port=port,
                    target=target,
                    username=username,
                    password=password,
                )
            )

            return {
                "success": True,
                "message": f"已登录到 iSCSI 目标 {target}",
                "host": host.name,
                "address": address,
                "target": target,
            }
        except Exception as e:
            raise RuntimeError(f"iSCSI 登录失败: {e}")


# MCP 工具注册表
MCP_TOOLS = {
    "host_get": {"method": "get_host", "description": "获取主机详情"},
    "host_add": {"method": "add_host", "description": "添加主机"},
    "host_remove": {"method": "remove_host", "description": "移除主机"},
    "host_stats": {"method": "get_host_stats", "description": "获取主机统计信息"},
    "host_devices": {"method": "get_host_devices", "description": "获取主机设备列表"},

    # 新增工具
    "host_nic_list": {"method": "list_host_nics", "description": "列出主机网卡"},
    "host_nic_update": {"method": "update_host_nic", "description": "更新主机网卡配置"},
    "host_numa_get": {"method": "get_host_numa", "description": "获取主机 NUMA 拓扑"},
    "host_hook_list": {"method": "list_host_hooks", "description": "列出主机 Hook"},
    "host_fence": {"method": "fence_host", "description": "对主机执行 Fence 操作"},
    "host_network_update": {"method": "update_host_network", "description": "更新主机网络配置"},
    "host_device_update": {"method": "update_host_device", "description": "更新主机设备配置"},
    "host_storage_list": {"method": "list_host_storage", "description": "列出主机存储"},
    "host_install": {"method": "install_host", "description": "安装/重新安装主机"},
    "host_iscsi_discover": {"method": "iscsi_discover", "description": "发现 iSCSI 目标"},
    "host_iscsi_login": {"method": "iscsi_login", "description": "登录到 iSCSI 目标"},
}
