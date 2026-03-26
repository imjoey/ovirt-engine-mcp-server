#!/usr/bin/env python3
"""
oVirt MCP Server - VM 扩展模块
提供 VM 迁移、控制台、CDROM、主机设备、NUMA、Watchdog、会话、VM池、检查点等高级管理功能
"""
from typing import Dict, List, Any, Optional
import logging

from .search_utils import sanitize_search_value as _sanitize_search_value

try:
    import ovirtsdk4 as sdk
except ImportError:
    sdk = None

logger = logging.getLogger(__name__)


class VmExtendedMCP:
    """VM 扩展管理 MCP"""

    def __init__(self, ovirt_mcp):
        self.ovirt = ovirt_mcp

    def _find_vm(self, name_or_id: str) -> Optional[Any]:
        """查找虚拟机（按名称或ID）"""
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        vms_service = self.ovirt.connection.system_service().vms_service()

        try:
            vm = vms_service.vm_service(name_or_id).get()
            if vm:
                return vm
        except Exception:
            pass

        vms = vms_service.list(search=f"name={_sanitize_search_value(name_or_id)}")
        return vms[0] if vms else None

    def _find_host(self, name_or_id: str) -> Optional[Any]:
        """查找主机"""
        hosts_service = self.ovirt.connection.system_service().hosts_service()

        try:
            host = hosts_service.host_service(name_or_id).get()
            if host:
                return host
        except Exception:
            pass

        hosts = hosts_service.list(search=f"name={_sanitize_search_value(name_or_id)}")
        return hosts[0] if hosts else None

    # ── VM 迁移 ──────────────────────────────────────────────────────────

    def migrate_vm(self, name_or_id: str, target_host: str = None) -> Dict[str, Any]:
        """迁移虚拟机到另一台主机

        Args:
            name_or_id: VM 名称或 ID
            target_host: 目标主机名称或 ID（可选，不指定则自动选择）

        Returns:
            迁移结果
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        vm = self._find_vm(name_or_id)
        if not vm:
            raise ValueError(f"VM 不存在: {name_or_id}")

        vm_service = self.ovirt.connection.system_service().vms_service().vm_service(vm.id)

        # 构建迁移参数
        host_ref = None
        if target_host:
            host = self._find_host(target_host)
            if not host:
                raise ValueError(f"目标主机不存在: {target_host}")
            host_ref = sdk.types.Host(id=host.id)

        try:
            vm_service.migrate(host=host_ref)
            return {
                "success": True,
                "message": f"VM {vm.name} 正在迁移" + (f" 到主机 {target_host}" if target_host else ""),
                "vm_id": vm.id,
                "target_host": target_host,
            }
        except Exception as e:
            raise RuntimeError(f"迁移 VM 失败: {e}")

    # ── VM 控制台 ────────────────────────────────────────────────────────

    def get_vm_console(self, name_or_id: str, console_type: str = "spice") -> Dict[str, Any]:
        """获取虚拟机控制台访问信息

        Args:
            name_or_id: VM 名称或 ID
            console_type: 控制台类型（spice/vnc），默认 spice

        Returns:
            控制台连接信息
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        vm = self._find_vm(name_or_id)
        if not vm:
            raise ValueError(f"VM 不存在: {name_or_id}")

        vm_service = self.ovirt.connection.system_service().vms_service().vm_service(vm.id)

        # 获取图形控制台
        consoles = []
        try:
            graphics_consoles_service = vm_service.graphics_consoles_service()
            console_list = graphics_consoles_service.list()

            for console in console_list:
                # 获取控制台票据
                ticket = None
                try:
                    console_service = graphics_consoles_service.console_service(console.id)
                    ticket_response = console_service.ticket()
                    ticket = ticket_response.value if ticket_response else None
                except Exception as e:
                    logger.debug(f"获取控制台票据失败: {e}")

                consoles.append({
                    "id": console.id,
                    "protocol": str(console.protocol.value) if console.protocol else "",
                    "address": console.address if hasattr(console, 'address') else "",
                    "port": console.port if hasattr(console, 'port') else 0,
                    "tls_port": console.tls_port if hasattr(console, 'tls_port') else 0,
                    "ticket": ticket,
                })
        except Exception as e:
            logger.error(f"获取控制台失败: {e}")

        # 过滤指定类型
        if console_type:
            consoles = [c for c in consoles if c["protocol"].lower() == console_type.lower()]

        return {
            "vm_id": vm.id,
            "vm_name": vm.name,
            "consoles": consoles,
            "console_count": len(consoles),
        }

    # ── CDROM 管理 ────────────────────────────────────────────────────────

    def list_vm_cdroms(self, name_or_id: str) -> List[Dict]:
        """列出 VM 的 CDROM 设备

        Args:
            name_or_id: VM 名称或 ID

        Returns:
            CDROM 列表
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        vm = self._find_vm(name_or_id)
        if not vm:
            raise ValueError(f"VM 不存在: {name_or_id}")

        vm_service = self.ovirt.connection.system_service().vms_service().vm_service(vm.id)
        cdroms_service = vm_service.cdroms_service()

        try:
            cdroms = cdroms_service.list()
        except Exception as e:
            logger.error(f"获取 CDROM 列表失败: {e}")
            return []

        result = []
        for cdrom in cdroms:
            result.append({
                "id": cdrom.id,
                "file": cdrom.file.id if cdrom.file else "",
                "storage_domain": cdrom.storage_domain.name if cdrom.storage_domain else "",
            })

        return result

    def update_vm_cdrom(self, name_or_id: str, cdrom_id: str,
                       iso_file: str = None, eject: bool = False) -> Dict[str, Any]:
        """更新 VM 的 CDROM（挂载/弹出 ISO）

        Args:
            name_or_id: VM 名称或 ID
            cdrom_id: CDROM ID
            iso_file: ISO 文件路径（可选）
            eject: 是否弹出光盘

        Returns:
            更新结果
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        vm = self._find_vm(name_or_id)
        if not vm:
            raise ValueError(f"VM 不存在: {name_or_id}")

        vm_service = self.ovirt.connection.system_service().vms_service().vm_service(vm.id)
        cdroms_service = vm_service.cdroms_service()
        cdrom_service = cdroms_service.cdrom_service(cdrom_id)

        # 获取当前 CDROM
        cdrom = cdrom_service.get()

        # 更新文件
        if eject:
            cdrom.file = None
        elif iso_file:
            cdrom.file = sdk.types.File(id=iso_file)

        try:
            cdrom_service.update(cdrom)
            return {
                "success": True,
                "message": f"CDROM 已更新",
                "vm_id": vm.id,
                "cdrom_id": cdrom_id,
                "iso_file": iso_file if not eject else "ejected",
            }
        except Exception as e:
            raise RuntimeError(f"更新 CDROM 失败: {e}")

    # ── 主机设备管理 ──────────────────────────────────────────────────────

    def list_vm_host_devices(self, name_or_id: str) -> List[Dict]:
        """列出 VM 的主机设备

        Args:
            name_or_id: VM 名称或 ID

        Returns:
            主机设备列表
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        vm = self._find_vm(name_or_id)
        if not vm:
            raise ValueError(f"VM 不存在: {name_or_id}")

        vm_service = self.ovirt.connection.system_service().vms_service().vm_service(vm.id)
        host_devices_service = vm_service.host_devices_service()

        try:
            devices = host_devices_service.list()
        except Exception as e:
            logger.error(f"获取主机设备列表失败: {e}")
            return []

        return [
            {
                "id": d.id,
                "name": d.name,
                "device": d.device if hasattr(d, 'device') else "",
                "vendor": d.vendor if hasattr(d, 'vendor') else "",
                "product": d.product if hasattr(d, 'product') else "",
            }
            for d in devices
        ]

    def attach_vm_host_device(self, name_or_id: str, device_name: str) -> Dict[str, Any]:
        """将主机设备附加到 VM

        Args:
            name_or_id: VM 名称或 ID
            device_name: 设备名称

        Returns:
            附加结果
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        vm = self._find_vm(name_or_id)
        if not vm:
            raise ValueError(f"VM 不存在: {name_or_id}")

        # 获取 VM 所在主机的设备
        if not vm.host:
            raise ValueError("VM 未运行在主机上，无法附加设备")

        host_service = self.ovirt.connection.system_service().hosts_service().host_service(vm.host.id)
        devices_service = host_service.devices_service()

        # 查找设备
        devices = devices_service.list(search=f"name={_sanitize_search_value(device_name)}")
        if not devices:
            raise ValueError(f"设备不存在: {device_name}")

        device = devices[0]

        vm_service = self.ovirt.connection.system_service().vms_service().vm_service(vm.id)
        host_devices_service = vm_service.host_devices_service()

        try:
            host_devices_service.add(
                sdk.types.HostDevice(id=device.id, name=device.name)
            )
            return {
                "success": True,
                "message": f"设备 {device_name} 已附加到 VM",
                "vm_id": vm.id,
                "device_id": device.id,
            }
        except Exception as e:
            raise RuntimeError(f"附加设备失败: {e}")

    def detach_vm_host_device(self, name_or_id: str, device_name: str) -> Dict[str, Any]:
        """从 VM 分离主机设备

        Args:
            name_or_id: VM 名称或 ID
            device_name: 设备名称

        Returns:
            分离结果
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        vm = self._find_vm(name_or_id)
        if not vm:
            raise ValueError(f"VM 不存在: {name_or_id}")

        vm_service = self.ovirt.connection.system_service().vms_service().vm_service(vm.id)
        host_devices_service = vm_service.host_devices_service()

        # 查找设备
        devices = host_devices_service.list()
        device = None
        for d in devices:
            if d.name == device_name:
                device = d
                break

        if not device:
            raise ValueError(f"VM 没有附加设备: {device_name}")

        device_service = host_devices_service.host_device_service(device.id)

        try:
            device_service.remove()
            return {
                "success": True,
                "message": f"设备 {device_name} 已从 VM 分离",
                "vm_id": vm.id,
            }
        except Exception as e:
            raise RuntimeError(f"分离设备失败: {e}")

    # ── 介导设备管理 ──────────────────────────────────────────────────────

    def list_vm_mediated_devices(self, name_or_id: str) -> List[Dict]:
        """列出 VM 的介导设备（vGPU 等）

        Args:
            name_or_id: VM 名称或 ID

        Returns:
            介导设备列表
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        vm = self._find_vm(name_or_id)
        if not vm:
            raise ValueError(f"VM 不存在: {name_or_id}")

        vm_service = self.ovirt.connection.system_service().vms_service().vm_service(vm.id)
        mediated_devices_service = vm_service.mediated_devices_service()

        try:
            devices = mediated_devices_service.list()
        except Exception as e:
            logger.error(f"获取介导设备列表失败: {e}")
            return []

        return [
            {
                "id": d.id,
                "name": d.name,
                "spec": d.spec_params if hasattr(d, 'spec_params') else {},
                "driver": d.driver if hasattr(d, 'driver') else "",
            }
            for d in devices
        ]

    # ── NUMA 管理 ──────────────────────────────────────────────────────────

    def list_vm_numa_nodes(self, name_or_id: str) -> List[Dict]:
        """列出 VM 的 NUMA 节点

        Args:
            name_or_id: VM 名称或 ID

        Returns:
            NUMA 节点列表
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        vm = self._find_vm(name_or_id)
        if not vm:
            raise ValueError(f"VM 不存在: {name_or_id}")

        vm_service = self.ovirt.connection.system_service().vms_service().vm_service(vm.id)
        numa_service = vm_service.numa_nodes_service()

        try:
            nodes = numa_service.list()
        except Exception as e:
            logger.error(f"获取 NUMA 节点失败: {e}")
            return []

        result = []
        for node in nodes:
            result.append({
                "id": node.id,
                "index": node.index if hasattr(node, 'index') else 0,
                "memory_mb": int((node.memory or 0) / (1024**2)),
                "cpu": {
                    "cores": node.cpu.topology.cores if node.cpu and node.cpu.topology else 0,
                    "sockets": node.cpu.topology.sockets if node.cpu and node.cpu.topology else 0,
                    "threads": node.cpu.topology.threads if node.cpu and node.cpu.topology else 0,
                } if node.cpu else {},
            })

        return result

    # ── Watchdog 管理 ──────────────────────────────────────────────────────

    def list_vm_watchdogs(self, name_or_id: str) -> List[Dict]:
        """列出 VM 的 Watchdog 设备

        Args:
            name_or_id: VM 名称或 ID

        Returns:
            Watchdog 列表
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        vm = self._find_vm(name_or_id)
        if not vm:
            raise ValueError(f"VM 不存在: {name_or_id}")

        vm_service = self.ovirt.connection.system_service().vms_service().vm_service(vm.id)
        watchdogs_service = vm_service.watchdogs_service()

        try:
            watchdogs = watchdogs_service.list()
        except Exception as e:
            logger.error(f"获取 Watchdog 列表失败: {e}")
            return []

        return [
            {
                "id": w.id,
                "model": str(w.model.value) if w.model else "",
                "action": str(w.action.value) if w.action else "",
            }
            for w in watchdogs
        ]

    def update_vm_watchdog(self, name_or_id: str, watchdog_id: str,
                          action: str = None) -> Dict[str, Any]:
        """更新 VM 的 Watchdog 配置

        Args:
            name_or_id: VM 名称或 ID
            watchdog_id: Watchdog ID
            action: 触发动作（none/reset/poweroff/shutdown/dump）

        Returns:
            更新结果
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        vm = self._find_vm(name_or_id)
        if not vm:
            raise ValueError(f"VM 不存在: {name_or_id}")

        vm_service = self.ovirt.connection.system_service().vms_service().vm_service(vm.id)
        watchdogs_service = vm_service.watchdogs_service()
        watchdog_service = watchdogs_service.watchdog_service(watchdog_id)

        watchdog = watchdog_service.get()

        if action:
            valid_actions = ["none", "reset", "poweroff", "shutdown", "dump"]
            if action.lower() not in valid_actions:
                raise ValueError(f"无效动作: {action}，有效值: {valid_actions}")
            watchdog.action = sdk.types.WatchdogAction(action.lower())

        try:
            watchdog_service.update(watchdog)
            return {
                "success": True,
                "message": f"Watchdog 已更新",
                "vm_id": vm.id,
                "watchdog_id": watchdog_id,
                "action": action,
            }
        except Exception as e:
            raise RuntimeError(f"更新 Watchdog 失败: {e}")

    # ── VM 固定到主机 ──────────────────────────────────────────────────────

    def pin_vm_to_host(self, name_or_id: str, host: str,
                      pin_policy: str = "user") -> Dict[str, Any]:
        """将 VM 固定到指定主机

        Args:
            name_or_id: VM 名称或 ID
            host: 主机名称或 ID
            pin_policy: 固定策略（user/resizable/migratable）

        Returns:
            固定结果
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        vm = self._find_vm(name_or_id)
        if not vm:
            raise ValueError(f"VM 不存在: {name_or_id}")

        host_obj = self._find_host(host)
        if not host_obj:
            raise ValueError(f"主机不存在: {host}")

        vm_service = self.ovirt.connection.system_service().vms_service().vm_service(vm.id)

        # 设置固定主机
        vm_update = sdk.types.Vm(
            host=sdk.types.Host(id=host_obj.id),
        )

        # 设置固定策略（如果有）
        if hasattr(sdk.types, 'VmPlacementPolicy'):
            valid_policies = ["user", "resizable", "migratable"]
            if pin_policy.lower() not in valid_policies:
                raise ValueError(f"无效策略: {pin_policy}，有效值: {valid_policies}")

        try:
            vm_service.update(vm_update)
            return {
                "success": True,
                "message": f"VM {vm.name} 已固定到主机 {host}",
                "vm_id": vm.id,
                "host_id": host_obj.id,
                "pin_policy": pin_policy,
            }
        except Exception as e:
            raise RuntimeError(f"固定 VM 失败: {e}")

    # ── VM 会话管理 ────────────────────────────────────────────────────────

    def list_vm_sessions(self, name_or_id: str) -> List[Dict]:
        """列出 VM 的活跃会话

        Args:
            name_or_id: VM 名称或 ID

        Returns:
            会话列表
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        vm = self._find_vm(name_or_id)
        if not vm:
            raise ValueError(f"VM 不存在: {name_or_id}")

        vm_service = self.ovirt.connection.system_service().vms_service().vm_service(vm.id)
        sessions_service = vm_service.sessions_service()

        try:
            sessions = sessions_service.list()
        except Exception as e:
            logger.error(f"获取会话列表失败: {e}")
            return []

        return [
            {
                "id": s.id,
                "user": s.user.name if s.user else "",
                "user_id": s.user.id if s.user else "",
                "protocol": str(s.protocol.value) if s.protocol else "",
                "console_user": s.console_user if hasattr(s, 'console_user') else False,
            }
            for s in sessions
        ]

    # ── VM 池管理 ──────────────────────────────────────────────────────────

    def list_vm_pools(self, cluster: str = None) -> List[Dict]:
        """列出虚拟机池

        Args:
            cluster: 集群名称（可选）

        Returns:
            VM 池列表
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        pools_service = self.ovirt.connection.system_service().vm_pools_service()

        search = None
        if cluster:
            search = f"cluster={_sanitize_search_value(cluster)}"

        try:
            pools = pools_service.list(search=search)
        except Exception as e:
            logger.error(f"获取 VM 池列表失败: {e}")
            return []

        return [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description or "",
                "size": p.size if hasattr(p, 'size') else 0,
                "max_user_vms": p.max_user_vms if hasattr(p, 'max_user_vms') else 0,
                "prestarted_vms": p.prestarted_vms if hasattr(p, 'prestarted_vms') else 0,
                "cluster": p.cluster.name if p.cluster else "",
                "template": p.vm.name if p.vm else "",
                "stateful": p.stateful if hasattr(p, 'stateful') else False,
            }
            for p in pools
        ]

    def get_vm_pool(self, name_or_id: str) -> Optional[Dict]:
        """获取虚拟机池详情

        Args:
            name_or_id: VM 池名称或 ID

        Returns:
            VM 池详情
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        pools_service = self.ovirt.connection.system_service().vm_pools_service()

        # 尝试按 ID 获取
        try:
            pool = pools_service.vm_pool_service(name_or_id).get()
            if pool:
                return self._format_pool_detail(pool)
        except Exception:
            pass

        # 按名称搜索
        pools = pools_service.list(search=f"name={_sanitize_search_value(name_or_id)}")
        if not pools:
            return None

        return self._format_pool_detail(pools[0])

    def _format_pool_detail(self, pool) -> Dict:
        """格式化池详情"""
        return {
            "id": pool.id,
            "name": pool.name,
            "description": pool.description or "",
            "size": pool.size if hasattr(pool, 'size') else 0,
            "max_user_vms": pool.max_user_vms if hasattr(pool, 'max_user_vms') else 0,
            "prestarted_vms": pool.prestarted_vms if hasattr(pool, 'prestarted_vms') else 0,
            "cluster": pool.cluster.name if pool.cluster else "",
            "cluster_id": pool.cluster.id if pool.cluster else "",
            "template": pool.vm.name if pool.vm else "",
            "template_id": pool.vm.id if pool.vm else "",
            "stateful": pool.stateful if hasattr(pool, 'stateful') else False,
            "display": {
                "type": str(pool.display.type.value) if pool.display else "",
            } if pool.display else {},
            "rng_device": str(pool.rng_device.source.value) if hasattr(pool, 'rng_device') and pool.rng_device else "",
        }

    def create_vm_pool(self, name: str, template: str, cluster: str,
                      size: int = 5, description: str = "",
                      max_user_vms: int = 1, prestarted_vms: int = 0,
                      stateful: bool = False) -> Dict[str, Any]:
        """创建虚拟机池

        Args:
            name: 池名称
            template: 模板名称
            cluster: 集群名称
            size: 池大小，默认 5
            description: 描述
            max_user_vms: 每用户最大 VM 数，默认 1
            prestarted_vms: 预启动 VM 数，默认 0
            stateful: 是否有状态，默认 False

        Returns:
            创建结果
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        # 查找模板
        templates = self.ovirt.connection.system_service().templates_service().list(
            search=f"name={_sanitize_search_value(template)}"
        )
        if not templates:
            raise ValueError(f"模板不存在: {template}")

        # 查找集群
        clusters = self.ovirt.connection.system_service().clusters_service().list(
            search=f"name={_sanitize_search_value(cluster)}"
        )
        if not clusters:
            raise ValueError(f"集群不存在: {cluster}")

        pools_service = self.ovirt.connection.system_service().vm_pools_service()

        try:
            pool = pools_service.add(
                sdk.types.VmPool(
                    name=name,
                    description=description,
                    size=size,
                    max_user_vms=max_user_vms,
                    prestarted_vms=prestarted_vms,
                    stateful=stateful,
                    cluster=sdk.types.Cluster(id=clusters[0].id),
                    vm=sdk.types.Vm(id=templates[0].id),
                )
            )

            return {
                "success": True,
                "message": f"VM 池 {name} 已创建",
                "pool_id": pool.id,
                "size": size,
            }
        except Exception as e:
            raise RuntimeError(f"创建 VM 池失败: {e}")

    def delete_vm_pool(self, name_or_id: str, force: bool = False) -> Dict[str, Any]:
        """删除虚拟机池

        Args:
            name_or_id: VM 池名称或 ID
            force: 强制删除

        Returns:
            删除结果
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        pools_service = self.ovirt.connection.system_service().vm_pools_service()

        # 查找池
        pool_id = None
        pool_name = None
        try:
            pool_service = pools_service.vm_pool_service(name_or_id)
            pool = pool_service.get()
            pool_id = name_or_id
            pool_name = pool.name
        except Exception:
            pools = pools_service.list(search=f"name={_sanitize_search_value(name_or_id)}")
            if not pools:
                raise ValueError(f"VM 池不存在: {name_or_id}")
            pool_id = pools[0].id
            pool_name = pools[0].name

        pool_service = pools_service.vm_pool_service(pool_id)

        try:
            pool_service.remove(force=force)
            return {"success": True, "message": f"VM 池 {pool_name} 已删除"}
        except Exception as e:
            raise RuntimeError(f"删除 VM 池失败: {e}")

    def update_vm_pool(self, name_or_id: str, new_name: str = None,
                      size: int = None, description: str = None,
                      prestarted_vms: int = None) -> Dict[str, Any]:
        """更新虚拟机池

        Args:
            name_or_id: VM 池名称或 ID
            new_name: 新名称（可选）
            size: 新大小（可选）
            description: 新描述（可选）
            prestarted_vms: 预启动 VM 数（可选）

        Returns:
            更新结果
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        pools_service = self.ovirt.connection.system_service().vm_pools_service()

        # 查找池
        pool_id = None
        try:
            pool_service = pools_service.vm_pool_service(name_or_id)
            pool = pool_service.get()
            pool_id = name_or_id
        except Exception:
            pools = pools_service.list(search=f"name={_sanitize_search_value(name_or_id)}")
            if not pools:
                raise ValueError(f"VM 池不存在: {name_or_id}")
            pool_id = pools[0].id
            pool = pools[0]
            pool_service = pools_service.vm_pool_service(pool_id)

        # 更新属性
        if new_name:
            pool.name = new_name
        if size is not None:
            pool.size = size
        if description is not None:
            pool.description = description
        if prestarted_vms is not None:
            pool.prestarted_vms = prestarted_vms

        try:
            pool_service.update(pool)
            return {"success": True, "message": f"VM 池已更新"}
        except Exception as e:
            raise RuntimeError(f"更新 VM 池失败: {e}")

    # ── VM 检查点管理 ──────────────────────────────────────────────────────

    def list_vm_checkpoints(self, name_or_id: str) -> List[Dict]:
        """列出 VM 的检查点

        Args:
            name_or_id: VM 名称或 ID

        Returns:
            检查点列表
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        vm = self._find_vm(name_or_id)
        if not vm:
            raise ValueError(f"VM 不存在: {name_or_id}")

        vm_service = self.ovirt.connection.system_service().vms_service().vm_service(vm.id)
        checkpoints_service = vm_service.checkpoints_service()

        try:
            checkpoints = checkpoints_service.list()
        except Exception as e:
            logger.error(f"获取检查点列表失败: {e}")
            return []

        return [
            {
                "id": c.id,
                "name": c.name if hasattr(c, 'name') else c.id,
                "creation_time": str(c.creation_time) if hasattr(c, 'creation_time') else "",
                "description": c.description if hasattr(c, 'description') else "",
            }
            for c in checkpoints
        ]

    def create_vm_checkpoint(self, name_or_id: str, description: str = "") -> Dict[str, Any]:
        """创建 VM 检查点

        Args:
            name_or_id: VM 名称或 ID
            description: 检查点描述

        Returns:
            创建结果
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        vm = self._find_vm(name_or_id)
        if not vm:
            raise ValueError(f"VM 不存在: {name_or_id}")

        vm_service = self.ovirt.connection.system_service().vms_service().vm_service(vm.id)
        checkpoints_service = vm_service.checkpoints_service()

        try:
            checkpoint = checkpoints_service.add(
                sdk.types.Checkpoint(
                    description=description,
                )
            )

            return {
                "success": True,
                "message": f"检查点已创建",
                "vm_id": vm.id,
                "checkpoint_id": checkpoint.id,
            }
        except Exception as e:
            raise RuntimeError(f"创建检查点失败: {e}")

    def restore_vm_checkpoint(self, name_or_id: str, checkpoint_id: str) -> Dict[str, Any]:
        """恢复 VM 到检查点

        Args:
            name_or_id: VM 名称或 ID
            checkpoint_id: 检查点 ID

        Returns:
            恢复结果
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        vm = self._find_vm(name_or_id)
        if not vm:
            raise ValueError(f"VM 不存在: {name_or_id}")

        vm_service = self.ovirt.connection.system_service().vms_service().vm_service(vm.id)
        checkpoints_service = vm_service.checkpoints_service()
        checkpoint_service = checkpoints_service.checkpoint_service(checkpoint_id)

        try:
            checkpoint_service.restore()
            return {
                "success": True,
                "message": f"VM 已恢复到检查点",
                "vm_id": vm.id,
                "checkpoint_id": checkpoint_id,
            }
        except Exception as e:
            raise RuntimeError(f"恢复检查点失败: {e}")

    def delete_vm_checkpoint(self, name_or_id: str, checkpoint_id: str) -> Dict[str, Any]:
        """删除 VM 检查点

        Args:
            name_or_id: VM 名称或 ID
            checkpoint_id: 检查点 ID

        Returns:
            删除结果
        """
        if not self.ovirt.connected:
            raise RuntimeError("未连接到 oVirt")

        vm = self._find_vm(name_or_id)
        if not vm:
            raise ValueError(f"VM 不存在: {name_or_id}")

        vm_service = self.ovirt.connection.system_service().vms_service().vm_service(vm.id)
        checkpoints_service = vm_service.checkpoints_service()
        checkpoint_service = checkpoints_service.checkpoint_service(checkpoint_id)

        try:
            checkpoint_service.remove()
            return {
                "success": True,
                "message": f"检查点已删除",
                "vm_id": vm.id,
                "checkpoint_id": checkpoint_id,
            }
        except Exception as e:
            raise RuntimeError(f"删除检查点失败: {e}")


# MCP 工具注册表
MCP_TOOLS = {
    # VM 迁移和控制台
    "vm_migrate": {"method": "migrate_vm", "description": "迁移虚拟机到另一台主机"},
    "vm_console": {"method": "get_vm_console", "description": "获取虚拟机控制台访问信息"},

    # CDROM 管理
    "vm_cdrom_list": {"method": "list_vm_cdroms", "description": "列出 VM 的 CDROM 设备"},
    "vm_cdrom_update": {"method": "update_vm_cdrom", "description": "更新 VM 的 CDROM（挂载/弹出 ISO）"},

    # 主机设备管理
    "vm_hostdevice_list": {"method": "list_vm_host_devices", "description": "列出 VM 的主机设备"},
    "vm_hostdevice_attach": {"method": "attach_vm_host_device", "description": "将主机设备附加到 VM"},
    "vm_hostdevice_detach": {"method": "detach_vm_host_device", "description": "从 VM 分离主机设备"},

    # 介导设备管理
    "vm_mediated_device_list": {"method": "list_vm_mediated_devices", "description": "列出 VM 的介导设备（vGPU）"},

    # NUMA 管理
    "vm_numa_list": {"method": "list_vm_numa_nodes", "description": "列出 VM 的 NUMA 节点"},

    # Watchdog 管理
    "vm_watchdog_list": {"method": "list_vm_watchdogs", "description": "列出 VM 的 Watchdog 设备"},
    "vm_watchdog_update": {"method": "update_vm_watchdog", "description": "更新 VM 的 Watchdog 配置"},

    # VM 固定
    "vm_pin_to_host": {"method": "pin_vm_to_host", "description": "将 VM 固定到指定主机"},

    # 会话管理
    "vm_session_list": {"method": "list_vm_sessions", "description": "列出 VM 的活跃会话"},

    # VM 池管理
    "vm_pool_list": {"method": "list_vm_pools", "description": "列出虚拟机池"},
    "vm_pool_get": {"method": "get_vm_pool", "description": "获取虚拟机池详情"},
    "vm_pool_create": {"method": "create_vm_pool", "description": "创建虚拟机池"},
    "vm_pool_delete": {"method": "delete_vm_pool", "description": "删除虚拟机池"},
    "vm_pool_update": {"method": "update_vm_pool", "description": "更新虚拟机池"},

    # 检查点管理
    "vm_checkpoint_list": {"method": "list_vm_checkpoints", "description": "列出 VM 的检查点"},
    "vm_checkpoint_create": {"method": "create_vm_checkpoint", "description": "创建 VM 检查点"},
    "vm_checkpoint_restore": {"method": "restore_vm_checkpoint", "description": "恢复 VM 到检查点"},
    "vm_checkpoint_delete": {"method": "delete_vm_checkpoint", "description": "删除 VM 检查点"},
}
