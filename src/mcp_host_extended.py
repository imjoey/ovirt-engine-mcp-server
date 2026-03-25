#!/usr/bin/env python3
"""
oVirt MCP Server - 主机扩展模块
提供主机详情、添加、删除和统计信息
"""
from typing import Dict, List, Any, Optional
import logging

from .search_utils import sanitize_search_value as _sanitize_search_value

try:
    import ovirtsdk4 as sdk
except ImportError:
    sdk = None

logger = logging.getLogger(__name__)


class HostExtendedMCP:
    """主机扩展管理 MCP"""

    def __init__(self, ovirt_mcp):
        self.ovirt = ovirt_mcp

    def _find_host(self, name_or_id: str) -> Optional[Any]:
        """查找主机（按名称或ID）"""
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        hosts_service = self.ovirt.connection.system_service().hosts_service()

        # 先尝试按 ID 查找
        try:
            host = hosts_service.host_service(name_or_id).get()
            if host:
                return host
        except Exception:
            pass

        # 按名称搜索
        hosts = hosts_service.list(search=f"name={_sanitize_search_value(name_or_id)}")
        return hosts[0] if hosts else None

    def get_host(self, name_or_id: str) -> Optional[Dict]:
        """获取主机详情"""
        host = self._find_host(name_or_id)
        if not host:
            return None

        # 获取主机网络接口
        nics = []
        try:
            host_service = self.ovirt.connection.system_service().hosts_service().host_service(host.id)
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

    def add_host(self, name: str, cluster: str, address: str,
                password: str = None, ssh_port: int = 22) -> Dict[str, Any]:
        """添加主机"""
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        # 查找集群
        clusters = self.ovirt.connection.system_service().clusters_service().list(
            search=f"name={_sanitize_search_value(cluster)}"
        )
        if not clusters:
            raise ValueError(f"集群不存在: {cluster}")

        hosts_service = self.ovirt.connection.system_service().hosts_service()

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

    def remove_host(self, name_or_id: str, force: bool = False) -> Dict[str, Any]:
        """移除主机"""
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"主机不存在: {name_or_id}")

        host_service = self.ovirt.connection.system_service().hosts_service().host_service(host.id)

        try:
            host_service.remove(force=force)
            return {"success": True, "message": f"主机 {host.name} 已移除"}
        except Exception as e:
            raise RuntimeError(f"移除主机失败: {e}")

    def get_host_stats(self, name_or_id: str) -> Dict[str, Any]:
        """获取主机统计信息"""
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"主机不存在: {name_or_id}")

        host_service = self.ovirt.connection.system_service().hosts_service().host_service(host.id)
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

    def get_host_devices(self, name_or_id: str) -> List[Dict]:
        """获取主机设备列表"""
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"主机不存在: {name_or_id}")

        host_service = self.ovirt.connection.system_service().hosts_service().host_service(host.id)
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


# MCP 工具注册表
MCP_TOOLS = {
    "host_get": {"method": "get_host", "description": "获取主机详情"},
    "host_add": {"method": "add_host", "description": "添加主机"},
    "host_remove": {"method": "remove_host", "description": "移除主机"},
    "host_stats": {"method": "get_host_stats", "description": "获取主机统计信息"},
    "host_devices": {"method": "get_host_devices", "description": "获取主机设备列表"},
}
