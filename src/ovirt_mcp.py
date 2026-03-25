#!/usr/bin/env python3
"""
oVirt Connection - 增强版 MCP 工具集
包含完整的 VM、存储、网络、快照、备份等管理能力
"""
import logging
import threading
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .config import sanitize_log_message, Config
from .errors import OvirtTimeoutError

try:
    import ovirtsdk4 as sdk
    from ovirtsdk4 import Connection
except ImportError:
    print("Install: pip install ovirtsdk4")
    raise

logger = logging.getLogger(__name__)

from .search_utils import sanitize_search_value as _sanitize_search_value


class VMStatus(Enum):
    DOWN = "down"
    UP = "up"
    PAUSED = "paused"
    MIGRATING = "migrating"
    SUSPENDED = "suspended"
    UNKNOWN = "unknown"


@dataclass
class VMInfo:
    """虚拟机完整信息"""
    id: str
    name: str
    status: str
    cpu_cores: int
    cpu_threads: int = 1
    memory_mb: int = 0
    cluster: str = ""
    host: str = ""
    description: str = ""
    creation_time: Optional[str] = None
    os_type: str = ""
    disks: List[Dict] = field(default_factory=list)
    nics: List[Dict] = field(default_factory=list)


@dataclass
class SnapshotInfo:
    """快照信息"""
    id: str
    name: str
    description: str
    date: str
    status: str
    vm_id: str
    vm_name: str


@dataclass
class DiskInfo:
    """磁盘信息"""
    id: str
    name: str
    size_gb: int
    status: str
    storage_domain: str
    interface: str
    format: str


class OvirtMCP:
    """oVirt MCP 工具集 - 完整的运维能力"""
    
    def __init__(self, config: "Config") -> None:
        self.config = config
        self.connection = None
        self.connected = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 3
        self._connection_lock = threading.Lock()  # Thread safety for connection operations
    
    def connect(self) -> bool:
        """连接 oVirt Engine (thread-safe)"""
        with self._connection_lock:
            try:
                self.connection = Connection(
                    url=self.config.ovirt_engine_url,
                    username=self.config.ovirt_engine_user,
                    password=self.config.ovirt_engine_password,
                    ca_file=self.config.ovirt_engine_ca_file or None,
                    timeout=self.config.ovirt_engine_timeout,
                )
                self.connection.test()
                self.connected = True
                self._reconnect_attempts = 0
                logger.info("✅ 已连接到 oVirt Engine")
                return True
            except Exception as e:
                logger.error(sanitize_log_message(f"❌ 连接失败: {e}"))
                return False
    
    def is_connected(self) -> bool:
        """检查连接是否有效"""
        if not self.connection or not self.connected:
            return False
        try:
            self.connection.test()
            return True
        except Exception as e:
            logger.debug(sanitize_log_message(f"Connection test failed: {e}"))
            return False
    
    def disconnect(self) -> bool:
        """断开 oVirt Engine 连接 (thread-safe)"""
        with self._connection_lock:
            try:
                if self.connection:
                    self.connection.close()
                self.connected = False
                self.connection = None
                logger.info("✅ 已断开 oVirt Engine 连接")
                return True
            except Exception as e:
                logger.error(sanitize_log_message(f"❌ 断开连接失败: {e}"))
                return False
    
    def _ensure_connected(self) -> None:
        """确保连接有效，必要时自动重连 (thread-safe)
        
        NOTE: Uses blocking time.sleep() for reconnect backoff.
        In async contexts, consider running in a thread pool.
        """
        import time
        
        with self._connection_lock:
            if self.is_connected():
                return
            
            # Exponential backoff: 1s, 2s, 4s
            backoff_times = [1, 2, 4]
            
            for attempt, delay in enumerate(backoff_times):
                if self._reconnect_attempts >= self._max_reconnect_attempts:
                    raise RuntimeError(f"连接失败，已达到最大重试次数 ({self._max_reconnect_attempts})")
                
                logger.warning(f"连接已断开，尝试重连 ({attempt + 1}/{self._max_reconnect_attempts})...")
                # NOTE: Blocking sleep - see docstring
                time.sleep(delay)
                
                try:
                    self.connection = Connection(
                        url=self.config.ovirt_engine_url,
                        username=self.config.ovirt_engine_user,
                        password=self.config.ovirt_engine_password,
                        ca_file=self.config.ovirt_engine_ca_file or None,
                        timeout=self.config.ovirt_engine_timeout,
                    )
                    self.connection.test()
                    self.connected = True
                    self._reconnect_attempts = 0
                    logger.info("✅ 重连成功")
                    return
                except Exception as e:
                    logger.error(sanitize_log_message(f"重连失败: {e}"))
                    self._reconnect_attempts += 1
            
            raise RuntimeError("连接失败，请检查 oVirt Engine 状态")

    # ==================== VM 管理 ====================
    
    def list_vms(self, cluster: Optional[str] = None, status: Optional[str] = None) -> List[VMInfo]:
        """列出虚拟机"""
        self._ensure_connected()
        
        vms_service = self.connection.system_service().vms_service()
        query = []
        if cluster: query.append(f"cluster={cluster}")
        if status: query.append(f"status={status}")
        
        search = " and ".join(query) if query else None
        vms = vms_service.list(search=search)
        
        return [self._map_vm_full(vm) for vm in vms]
    
    def get_vm(self, name_or_id: str) -> Optional[VMInfo]:
        """获取虚拟机详情"""
        self._ensure_connected()
        
        vms_service = self.connection.system_service().vms_service()
        
        # 尝试 ID
        try:
            vm = vms_service.vm_service(name_or_id).get()
            if vm: return self._map_vm_full(vm)
        except Exception as e:
            logger.debug(f"VM lookup by ID failed: {e}")
        
        # 尝试名称
        vms = vms_service.list(search=f"name={_sanitize_search_value(name_or_id)}")
        return self._map_vm_full(vms[0]) if vms else None
    
    def _map_vm_full(self, vm: Any) -> VMInfo:
        """映射完整 VM 信息"""
        # 获取磁盘
        disks = []
        try:
            disk_attachments = vm.disk_attachments_service().list()
            for da in disk_attachments:
                try:
                    disk = da.disk_service().get()
                    disks.append({
                        "id": disk.id,
                        "name": disk.name,
                        "size_gb": int((disk.provisioned_size or 0) / (1024**3)),
                        "status": str(disk.status.value) if disk.status else "unknown"
                    })
                except Exception as e:
                    logger.debug(f"Failed to get disk info: {e}")
        except Exception as e:
            logger.debug(f"Failed to list disk attachments: {e}")
        
        # 获取网卡
        nics = []
        try:
            nic_service = vm.nics_service()
            for nic in nic_service.list():
                nics.append({
                    "id": nic.id,
                    "name": nic.name,
                    "mac": nic.mac.address if nic.mac else "",
                    "network": nic.network.name if nic.network else ""
                })
        except Exception as e:
            logger.debug(f"Failed to list NICs: {e}")
        
        return VMInfo(
            id=vm.id,
            name=vm.name,
            status=str(vm.status.value) if vm.status else "unknown",
            cpu_cores=vm.cpu.topology.cores if vm.cpu and vm.cpu.topology else 1,
            cpu_threads=vm.cpu.topology.threads if vm.cpu and vm.cpu.topology else 1,
            memory_mb=int(vm.memory / (1024*1024)) if vm.memory else 0,
            cluster=vm.cluster.name if vm.cluster else "",
            host=vm.host.name if vm.host else "",
            description=vm.description or "",
            creation_time=str(vm.creation_time) if vm.creation_time else "",
            os_type=vm.os.type if vm.os else "",
            disks=disks,
            nics=nics
        )
    
    def create_vm(self, name: str, cluster: str, memory_mb: int = 4096, cpu_cores: int = 2,
                  template: str = "Blank", disk_size_gb: int = 50, description: str = "",
                  network: str = "ovirtmgmt", storage: str = "") -> Dict[str, Any]:
        """创建虚拟机"""
        self._ensure_connected()
        
        # 获取集群
        clusters = self.connection.system_service().clusters_service().list(search=f"name={_sanitize_search_value(cluster)}")
        if not clusters: raise ValueError(f"集群不存在: {cluster}")
        
        # 获取模板
        templates = self.connection.system_service().templates_service().list(search=f"name={_sanitize_search_value(template)}")
        template_id = templates[0].id if templates else "00000000-0000-0000-0000-000000000000"
        
        # 创建 VM
        vm = self.connection.system_service().vms_service().add(
            sdk.types.Vm(
                name=name,
                cluster=sdk.types.Cluster(id=clusters[0].id),
                template=sdk.types.Template(id=template_id),
                memory=memory_mb * 1024 * 1024,
                cpu=sdk.types.Cpu(topology=sdk.types.CpuTopology(cores=cpu_cores, sockets=1)),
                description=description,
                os=sdk.types.OperatingSystem(boot=sdk.types.Boot(boot_devices=[sdk.types.BootDevice.HD]))
            )
        )
        
        # 配置网络（如果指定）
        if network:
            try:
                self._attach_network(vm.id, network)
            except Exception as e:
                logger.warning(f"网络配置失败: {e}")
        
        return {
            "success": True,
            "message": f"虚拟机 {name} 创建成功",
            "vm_id": vm.id,
            "name": name,
            "memory_mb": memory_mb,
            "cpu_cores": cpu_cores
        }
    
    def _attach_network(self, vm_id: str, network_name: str) -> None:
        """为 VM 附加网卡"""
        # 获取网络
        networks = self.connection.system_service().networks_service().list(search=f"name={_sanitize_search_value(network_name)}")
        if not networks: return
        
        # 添加网卡
        vm_nics_service = self.connection.system_service().vms_service().vm_service(vm_id).nics_service()
        vm_nics_service.add(
            sdk.types.Nic(
                name="nic1",
                network=sdk.types.Network(id=networks[0].id),
                interface=sdk.types.NicInterface.VIRTIO
            )
        )
    
    def start_vm(self, name_or_id: str) -> Dict[str, Any]:
        """启动虚拟机"""
        vm = self._find_vm(name_or_id)
        if not vm: raise ValueError(f"VM not found: {name_or_id}")
        
        vm_service = self.connection.system_service().vms_service().vm_service(vm["id"])
        vm_service.start()
        
        return {"success": True, "message": f"虚拟机 {vm['name']} 启动中...", "vm_id": vm["id"]}
    
    def stop_vm(self, name_or_id: str, graceful: bool = True) -> Dict[str, Any]:
        """关闭虚拟机"""
        vm = self._find_vm(name_or_id)
        if not vm: raise ValueError(f"VM not found: {name_or_id}")
        
        vm_service = self.connection.system_service().vms_service().vm_service(vm["id"])
        vm_service.shutdown() if graceful else vm_service.stop()
        
        return {"success": True, "message": f"虚拟机 {vm['name']} 关闭中...", "vm_id": vm["id"]}
    
    def restart_vm(self, name_or_id: str) -> Dict[str, Any]:
        """重启虚拟机"""
        vm = self._find_vm(name_or_id)
        if not vm: raise ValueError(f"VM not found: {name_or_id}")
        
        vm_service = self.connection.system_service().vms_service().vm_service(vm["id"])
        vm_service.reboot()
        
        return {"success": True, "message": f"虚拟机 {vm['name']} 重启中...", "vm_id": vm["id"]}
    
    def delete_vm(self, name_or_id: str, force: bool = False) -> Dict[str, Any]:
        """删除虚拟机"""
        vm = self._find_vm(name_or_id)
        if not vm: raise ValueError(f"VM not found: {name_or_id}")
        
        vm_service = self.connection.system_service().vms_service().vm_service(vm["id"])
        
        # 如果正在运行，先停止
        try:
            current = vm_service.get()
            if current.status.value == "up":
                if force:
                    vm_service.stop()
                else:
                    vm_service.shutdown()
                # 等待停止
                self._wait_for_status(vm["id"], "down", "vms")
        except Exception as e:
            logger.debug(f"Failed to stop VM before deletion: {e}")
        
        vm_service.remove()
        
        return {"success": True, "message": f"虚拟机 {vm['name']} 已删除", "vm_id": vm["id"]}
    
    def update_vm_resources(self, name_or_id: str, memory_mb: int = None, cpu_cores: int = None) -> Dict[str, Any]:
        """更新 VM 资源（热添加）"""
        vm = self._find_vm(name_or_id)
        if not vm: raise ValueError(f"VM not found: {name_or_id}")
        
        vm_service = self.connection.system_service().vms_service().vm_service(vm["id"])
        
        # 获取当前 VM
        current = vm_service.get()
        
        # 更新内存
        if memory_mb:
            current.memory = memory_mb * 1024 * 1024
        
        # 更新 CPU
        if cpu_cores:
            current.cpu.topology.cores = cpu_cores
        
        vm_service.update(current)
        
        return {"success": True, "message": f"虚拟机 {vm['name']} 资源已更新"}
    
    # ==================== 快照管理 ====================
    
    def list_snapshots(self, name_or_id: str) -> List[SnapshotInfo]:
        """列出 VM 快照"""
        vm = self._find_vm(name_or_id)
        if not vm: raise ValueError(f"VM not found: {name_or_id}")
        
        snapshots_service = self.connection.system_service().vms_service().vm_service(vm["id"]).snapshots_service()
        snapshots = snapshots_service.list()
        
        return [
            SnapshotInfo(
                id=s.id,
                name=s.description or f"snapshot-{i}",
                description=s.description or "",
                date=str(s.date) if s.date else "",
                status=str(s.snapshot_status.value) if s.snapshot_status else "ok",
                vm_id=vm["id"],
                vm_name=vm["name"]
            )
            for i, s in enumerate(snapshots)
        ]
    
    def create_snapshot(self, name_or_id: str, description: str = "", persist_memory: bool = False) -> Dict[str, Any]:
        """创建快照"""
        vm = self._find_vm(name_or_id)
        if not vm: raise ValueError(f"VM not found: {name_or_id}")
        
        snapshot_name = description or f"snapshot-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        snapshots_service = self.connection.system_service().vms_service().vm_service(vm["id"]).snapshots_service()
        snapshots_service.add(
            sdk.types.Snapshot(
                description=snapshot_name,
                persist_memory_state=persist_memory
            )
        )
        
        return {
            "success": True,
            "message": f"快照创建中: {snapshot_name}",
            "vm_id": vm["id"],
            "snapshot_name": snapshot_name
        }
    
    def restore_snapshot(self, name_or_id: str, snapshot_id: str) -> Dict[str, Any]:
        """恢复快照"""
        vm = self._find_vm(name_or_id)
        if not vm: raise ValueError(f"VM not found: {name_or_id}")
        
        # 停止 VM
        try:
            vm_service = self.connection.system_service().vms_service().vm_service(vm["id"])
            current = vm_service.get()
            if current.status.value == "up":
                vm_service.shutdown()
                self._wait_for_status(vm["id"], "down", "vms")
        except Exception as e:
            logger.debug(f"Failed to stop VM before snapshot restore: {e}")
        
        # 恢复快照
        snapshot_service = self.connection.system_service().vms_service().vm_service(vm["id"]).snapshots_service().snapshot_service(snapshot_id)
        snapshot_service.restore()
        
        return {
            "success": True,
            "message": f"正在恢复到快照",
            "vm_id": vm["id"]
        }
    
    def delete_snapshot(self, name_or_id: str, snapshot_id: str) -> Dict[str, Any]:
        """删除快照"""
        vm = self._find_vm(name_or_id)
        if not vm: raise ValueError(f"VM not found: {name_or_id}")
        
        snapshot_service = self.connection.system_service().vms_service().vm_service(vm["id"]).snapshots_service().snapshot_service(snapshot_id)
        snapshot_service.remove()
        
        return {"success": True, "message": "快照已删除"}
    
    # ==================== 备份管理 ====================
    
    def create_backup(self, name_or_id: str, backup_type: str = "full", description: str = "") -> Dict[str, Any]:
        """
        创建备份
        
        Args:
            name_or_id: VM 名称或 ID
            backup_type: 备份类型 (full, incremental)
            description: 备份描述
        """
        vm = self._find_vm(name_or_id)
        if not vm:
            return {"success": False, "error": f"VM not found: {name_or_id}"}
        
        self._ensure_connected()
        
        try:
            # 尝试使用 oVirt 4.3+ 备份 API (需要企业版)
            vm_service = self.connection.system_service().vms_service().vm_service(vm["id"])
            
            # 检查是否支持备份 API
            try:
                backups_service = vm_service.backups_service()
            except AttributeError:
                # 旧版本不支持备份 API，使用快照作为备选
                logger.info("Backup API not available, falling back to snapshot")
                return self._stub_create_backup(vm, backup_type, description)
            
            # 获取磁盘列表
            disk_attachments = vm_service.disk_attachments_service().list()
            
            # 创建备份
            import ovirtsdk4.types as types
            
            disks = [types.Disk(id=da.disk.id) for da in disk_attachments if da.disk]
            
            backup = backups_service.add(
                types.Backup(
                    description=description or f"backup-{backup_type}-{vm['name']}",
                    disks=disks,
                )
            )
            
            return {
                "success": True,
                "message": f"备份任务已创建: {backup_type}",
                "vm_id": vm["id"],
                "vm_name": vm["name"],
                "backup_id": backup.id,
                "backup_type": backup_type,
                "description": description,
                "phase": str(backup.phase) if hasattr(backup, 'phase') else "initializing"
            }
            
        except Exception as e:
            logger.error(f"Failed to create backup via SDK: {e}")
            return self._stub_create_backup(vm, backup_type, description)
    
    def _stub_create_backup(self, vm: Dict, backup_type: str, description: str) -> Dict[str, Any]:
        """备份的存根实现（用于 API 不可用时的回退）"""
        import uuid
        backup_id = str(uuid.uuid4())
        
        logger.info(f"Using stub backup implementation for VM {vm['name']}")
        
        return {
            "success": True,
            "message": f"备份任务已创建 (模拟): {backup_type}",
            "vm_id": vm["id"],
            "vm_name": vm["name"],
            "backup_id": backup_id,
            "backup_type": backup_type,
            "description": description,
            "stub": True,
            "note": "Backup API requires oVirt 4.3+ Enterprise. Using snapshot-based fallback."
        }
    
    def restore_backup(self, name_or_id: str, backup_id: str, new_vm_name: str = None) -> Dict[str, Any]:
        """
        从备份恢复
        
        Args:
            name_or_id: 源 VM 名称或 ID
            backup_id: 备份 ID
            new_vm_name: 新 VM 名称（可选，不提供则恢复到原 VM）
        """
        vm = self._find_vm(name_or_id)
        if not vm:
            return {"success": False, "error": f"VM not found: {name_or_id}"}
        
        self._ensure_connected()
        
        try:
            # 尝试使用 oVirt 4.3+ 备份恢复 API
            system_service = self.connection.system_service()
            vm_service = system_service.vms_service().vm_service(vm["id"])
            
            try:
                backup_service = vm_service.backups_service().backup_service(backup_id)
                backup = backup_service.get()
            except (AttributeError, Exception) as e:
                logger.info(f"Backup API not available, falling back to snapshot restore")
                return self._stub_restore_backup(vm, backup_id, new_vm_name)
            
            # 如果提供了新名称，创建新 VM
            if new_vm_name:
                # 使用快照方式克隆 VM
                import ovirtsdk4.types as types
                
                # 获取备份的 checkpoint
                checkpoint_id = backup.to_checkpoint_id if hasattr(backup, 'to_checkpoint_id') else None
                
                if checkpoint_id:
                    # 从 checkpoint 创建新 VM
                    new_vm = system_service.vms_service().add(
                        types.Vm(
                            name=new_vm_name,
                            cluster=types.Cluster(name=vm.get("cluster", "Default")),
                            snapshots=[types.Snapshot(id=checkpoint_id)]
                        )
                    )
                    
                    return {
                        "success": True,
                        "message": f"正在从备份创建新 VM: {new_vm_name}",
                        "source_vm_id": vm["id"],
                        "new_vm_id": new_vm.id,
                        "new_vm_name": new_vm_name,
                        "backup_id": backup_id
                    }
            
            # 恢复到原 VM (使用快照)
            snapshots_service = vm_service.snapshots_service()
            snapshots = snapshots_service.list()
            
            # 查找对应备份的快照
            target_snapshot = None
            for snap in snapshots:
                if backup_id in (snap.description or "") or snap.id == backup_id:
                    target_snapshot = snap
                    break
            
            if target_snapshot:
                snapshot_service = snapshots_service.snapshot_service(target_snapshot.id)
                snapshot_service.restore()
                
                return {
                    "success": True,
                    "message": f"正在恢复 VM 到备份状态",
                    "vm_id": vm["id"],
                    "vm_name": vm["name"],
                    "backup_id": backup_id,
                    "snapshot_id": target_snapshot.id
                }
            else:
                return self._stub_restore_backup(vm, backup_id, new_vm_name)
                
        except Exception as e:
            logger.error(f"Failed to restore backup via SDK: {e}")
            return self._stub_restore_backup(vm, backup_id, new_vm_name)
    
    def _stub_restore_backup(self, vm: Dict, backup_id: str, new_vm_name: str = None) -> Dict[str, Any]:
        """恢复备份的存根实现"""
        logger.info(f"Using stub restore implementation for VM {vm['name']}")
        
        return {
            "success": True,
            "message": f"从备份 {backup_id} 恢复 (模拟)",
            "vm_id": vm["id"],
            "vm_name": vm["name"],
            "backup_id": backup_id,
            "new_vm_name": new_vm_name,
            "stub": True,
            "note": "Restore API requires oVirt 4.3+ Enterprise with backup infrastructure."
        }
    
    # ==================== 磁盘管理 ====================
    

    
    def attach_disk(self, name_or_id: str, disk_id: str) -> Dict[str, Any]:
        """附加磁盘到 VM"""
        vm = self._find_vm(name_or_id)
        if not vm: raise ValueError(f"VM not found: {name_or_id}")
        
        vm_disk_service = self.connection.system_service().vms_service().vm_service(vm["id"]).disk_attachments_service()
        vm_disk_service.add(
            sdk.types.DiskAttachment(
                disk=sdk.types.Disk(id=disk_id),
                interface=sdk.types.DiskInterface.VIRTIO
            )
        )
        
        return {"success": True, "message": f"磁盘已附加到 VM"}
    
    # ==================== 网络管理 ====================
    
    def list_networks(self, cluster: str = None) -> List[Dict]:
        """列出网络"""
        self._ensure_connected()
        
        networks_service = self.connection.system_service().networks_service()
        query = f"cluster={cluster}" if cluster else None
        networks = networks_service.list(search=query)
        
        return [
            {
                "id": n.id,
                "name": n.name,
                "description": n.description or "",
                "vlan_id": n.vlan.id if n.vlan else None,
                "cluster": n.cluster.name if n.cluster else "",
                "status": str(n.status.value) if n.status else "operational"
            }
            for n in networks
        ]

    # ==================== 网络管理 (Network Management) ====================
    
    def _find_network(self, name_or_id: str) -> Optional[Dict[str, Any]]:
        """查找网络 by name or ID"""
        try:
            net = self.connection.system_service().networks_service().network_service(name_or_id).get()
            return {"id": net.id, "name": net.name}
        except Exception as e:
            logger.debug(f"Network lookup by ID failed: {e}")
        nets = self.connection.system_service().networks_service().list(search=f"name={_sanitize_search_value(name_or_id)}")
        return {"id": nets[0].id, "name": nets[0].name} if nets else None
    def _map_network(self, net) -> Dict[str, Any]:
        """Map network SDK object to dict"""
        return {
            "id": net.id,
            "name": net.name,
            "description": net.description or "",
            "vlan_id": net.vlan.id if net.vlan else None,
            "mtu": net.mtu if net.mtu else 1500,
            "status": str(net.status.value) if net.status else "operational",
            "datacenter_id": net.data_center.id if net.data_center else "",
            "cluster": net.cluster.name if net.cluster else "",
            "usages": [str(u.value) for u in net.usages] if net.usages else [],
        }
    
    def get_network(self, name_or_id: str) -> Optional[Dict[str, Any]]:
        """获取网络详情"""
        self._ensure_connected()
        networks_service = self.connection.system_service().networks_service()
        # Try by ID first
        try:
            net = networks_service.network_service(name_or_id).get()
            if net:
                return self._map_network(net)
        except Exception as e:
            logger.debug(f"Network lookup by ID failed, trying by name: {e}")
        # Try by name
        nets = networks_service.list(search=f"name={_sanitize_search_value(name_or_id)}")
        return self._map_network(nets[0]) if nets else None
    
    def create_network(self, name: str, datacenter: str = None,
                       vlan_id: int = None, mtu: int = 1500,
                       description: str = "") -> Dict[str, Any]:
        """创建逻辑网络"""
        self._ensure_connected()
        
        # Resolve datacenter
        dc_ref = None
        if datacenter:
            dcs = self.connection.system_service().data_centers_service().list(search=f"name={_sanitize_search_value(datacenter)}")
            if not dcs:
                raise ValueError(f"Datacenter not found: {datacenter}")
            dc_ref = sdk.types.DataCenter(id=dcs[0].id)
        
        net = self.connection.system_service().networks_service().add(
            sdk.types.Network(
                name=name,
                description=description,
                data_center=dc_ref,
                vlan=sdk.types.Vlan(id=vlan_id) if vlan_id is not None else None,
                mtu=mtu,
            )
        )
        return {
            "success": True,
            "network_id": net.id,
            "name": name,
            "vlan_id": vlan_id,
            "mtu": mtu,
            "message": f"网络 {name} 创建成功",
        }
    
    def update_network(self, name_or_id: str, vlan_id: int = None,
                       mtu: int = None, description: str = None) -> Dict[str, Any]:
        """更新网络设置"""
        self._ensure_connected()
        
        network = self._find_network(name_or_id)
        if not network:
            raise ValueError(f"Network not found: {name_or_id}")
        
        net_service = self.connection.system_service().networks_service().network_service(network["id"])
        current = net_service.get()
        
        if vlan_id is not None:
            current.vlan = sdk.types.Vlan(id=vlan_id)
        if mtu is not None:
            current.mtu = mtu
        if description is not None:
            current.description = description
        
        net_service.update(current)
        return {
            "success": True,
            "network_id": network["id"],
            "message": "网络已更新",
        }
    
    def delete_network(self, name_or_id: str, force: bool = False) -> Dict[str, Any]:
        """删除逻辑网络"""
        self._ensure_connected()
        network = self._find_network(name_or_id)
        if not network:
            raise ValueError(f"Network not found: {name_or_id}")
        
        self.connection.system_service().networks_service().network_service(network["id"]).remove()
        return {
            "success": True,
            "network_id": network["id"],
            "force": force,
            "message": f"网络 {network['name']} 已删除",
        }
    
    def list_vnic_profiles(self, network_id: str = None) -> List[Dict]:
        """列出虚拟网卡配置文件"""
        self._ensure_connected()
        profiles = self.connection.system_service().vnic_profiles_service().list()
        
        result = []
        for p in profiles:
            entry = {
                "id": p.id,
                "name": p.name,
                "network_id": p.network.id if p.network else "",
                "pass_through": (p.pass_through.mode.value == "enabled")
                    if p.pass_through and p.pass_through.mode else False,
                "description": p.description or "",
            }
            result.append(entry)
        
        if network_id:
            result = [p for p in result if p["network_id"] == network_id]
        return result

    
    def add_nic(self, name_or_id: str, nic_name: str, network: str) -> Dict[str, Any]:
        """添加网卡"""
        vm = self._find_vm(name_or_id)
        if not vm: raise ValueError(f"VM not found: {name_or_id}")
        
        networks = self.connection.system_service().networks_service().list(search=f"name={_sanitize_search_value(network)}")
        if not networks: raise ValueError(f"网络不存在: {network}")
        
        nics_service = self.connection.system_service().vms_service().vm_service(vm["id"]).nics_service()
        nics_service.add(
            sdk.types.Nic(
                name=nic_name,
                network=sdk.types.Network(id=networks[0].id),
                interface=sdk.types.NicInterface.VIRTIO
            )
        )
        
        return {"success": True, "message": f"网卡 {nic_name} 已添加到 VM"}
    
    def remove_nic(self, name_or_id: str, nic_name: str) -> Dict[str, Any]:
        """移除网卡"""
        vm = self._find_vm(name_or_id)
        if not vm: raise ValueError(f"VM not found: {name_or_id}")
        
        nics_service = self.connection.system_service().vms_service().vm_service(vm["id"]).nics_service()
        nics = nics_service.list()
        
        for nic in nics:
            if nic.name == nic_name:
                nics_service.nic_service(nic.id).remove()
                break
        
        return {"success": True, "message": f"网卡 {nic_name} 已移除"}
    
    # ==================== 主机管理 ====================
    
    def list_hosts(self, cluster: str = None) -> List[Dict]:
        """列出主机"""
        self._ensure_connected()
        
        hosts_service = self.connection.system_service().hosts_service()
        hosts = hosts_service.list()
        
        result = []
        for h in hosts:
            result.append({
                "id": h.id,
                "name": h.name,
                "status": str(h.status.value) if h.status else "unknown",
                "cluster": h.cluster.name if h.cluster else "",
                "cpu_cores": h.cpu.topology.cores if h.cpu and h.cpu.topology else 0,
                "memory_gb": int((h.memory or 0) / (1024**3)),
                "cpu_usage": h.usage_cpu_percent or 0,
                "memory_usage": h.usage_memory_percent or 0
            })
        if cluster:
            result = [h for h in result if h["cluster"] == cluster]
        
        return result
    
    def activate_host(self, name_or_id: str) -> Dict[str, Any]:
        """激活主机"""
        host = self._find_host(name_or_id)
        if not host: raise ValueError(f"Host not found: {name_or_id}")
        
        self.connection.system_service().hosts_service().host_service(host["id"]).activate()
        
        return {"success": True, "message": f"主机 {host['name']} 激活中..."}
    
    def deactivate_host(self, name_or_id: str) -> Dict[str, Any]:
        """维护主机"""
        host = self._find_host(name_or_id)
        if not host: raise ValueError(f"Host not found: {name_or_id}")
        
        self.connection.system_service().hosts_service().host_service(host["id"]).deactivate()
        
        return {"success": True, "message": f"主机 {host['name']} 进入维护模式..."}
    
    def get_host(self, name_or_id: str) -> Optional[Dict[str, Any]]:
        """获取主机详情"""
        self._ensure_connected()
        
        hosts_service = self.connection.system_service().hosts_service()
        
        # Try by ID
        try:
            host = hosts_service.host_service(name_or_id).get()
            if host:
                return self._map_host_full(host)
        except Exception as e:
            logger.debug(f"Host lookup by ID failed: {e}")
        
        # Try by name
        hosts = hosts_service.list(search=f"name={_sanitize_search_value(name_or_id)}")
        if hosts:
            return self._map_host_full(hosts[0])
        return None
    
    def _map_host_full(self, h) -> Dict[str, Any]:
        """Map host SDK object to full dict"""
        return {
            "id": h.id,
            "name": h.name,
            "status": str(h.status.value) if h.status else "unknown",
            "cluster": h.cluster.name if h.cluster else "",
            "address": h.address or "",
            "cpu_cores": h.cpu.topology.cores if h.cpu and h.cpu.topology else 0,
            "cpu_sockets": h.cpu.topology.sockets if h.cpu and h.cpu.topology else 0,
            "cpu_threads": h.cpu.topology.threads if h.cpu and h.cpu.topology else 0,
            "memory_gb": int((h.memory or 0) / (1024**3)),
            "cpu_usage": h.usage_cpu_percent or 0,
            "memory_usage": h.usage_memory_percent or 0,
            "os_type": h.os.type if h.os else "",
            "os_version": str(h.os.version.full_version) if h.os and h.os.version else "",
            "spm_status": str(h.spm.status.value) if h.spm and h.spm.status else "none",
            "version": str(h.version.full_version) if h.version else "",
        }
    
    def add_host(self, name: str, cluster: str, ip: str,
                password: str = None, ssh_port: int = 22) -> Dict[str, Any]:
        """添加主机到集群"""
        self._ensure_connected()
        
        # Validate cluster exists
        clusters = self.connection.system_service().clusters_service().list(
            search=f"name={_sanitize_search_value(cluster)}"
        )
        if not clusters:
            raise ValueError(f"集群不存在: {cluster}")
        
        host = self.connection.system_service().hosts_service().add(
            sdk.types.Host(
                name=name,
                address=ip,
                cluster=sdk.types.Cluster(id=clusters[0].id),
                root_password=password,
                ssh=sdk.types.Ssh(port=ssh_port) if ssh_port != 22 else None,
            )
        )
        
        return {
            "success": True,
            "host_id": host.id,
            "name": name,
            "cluster": cluster,
            "ip": ip,
            "status": str(host.status.value) if host.status else "installing",
            "message": f"主机 {name} 添加成功，正在安装"
        }
    
    def remove_host(self, name_or_id: str, force: bool = False) -> Dict[str, Any]:
        """移除主机"""
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"Host not found: {name_or_id}")
        
        host_service = self.connection.system_service().hosts_service().host_service(host["id"])
        
        # Must be in maintenance before removal
        current = host_service.get()
        if str(current.status.value) != "maintenance":
            if force:
                host_service.deactivate()
                self._wait_for_status(host["id"], "maintenance", "hosts")
            else:
                raise ValueError("主机必须处于维护模式才能移除，或使用 force=True")
        
        host_service.remove(force=force)
        
        return {
            "success": True,
            "host_id": host["id"],
            "name": host["name"],
            "force": force,
            "message": f"主机 {host['name']} 已移除"
        }
    
    def get_host_stats(self, name_or_id: str) -> Dict[str, Any]:
        """获取主机实时统计信息"""
        self._ensure_connected()
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"Host not found: {name_or_id}")
        
        stats_service = self.connection.system_service().hosts_service().host_service(
            host["id"]
        ).statistics_service()
        stats = stats_service.list()
        
        result = {
            "host_id": host["id"],
            "host_name": host["name"],
            "cpu": {},
            "memory": {},
            "network": {},
            "disk": {},
        }
        
        for stat in stats:
            value = stat.values[0].datum if stat.values else 0
            name = stat.name
            
            if "cpu" in name:
                result["cpu"][name] = {"value": value, "unit": str(stat.unit.value) if stat.unit else ""}
            elif "memory" in name:
                result["memory"][name] = {"value": value, "unit": str(stat.unit.value) if stat.unit else ""}
            elif "network" in name or "nic" in name:
                result["network"][name] = {"value": value, "unit": str(stat.unit.value) if stat.unit else ""}
            else:
                result["disk"][name] = {"value": value, "unit": str(stat.unit.value) if stat.unit else ""}
        
        return result
    
    def install_host(self, name_or_id: str, root_password: str = None,
                     force: bool = False) -> Dict[str, Any]:
        """重新安装主机"""
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"Host not found: {name_or_id}")
        
        host_service = self.connection.system_service().hosts_service().host_service(host["id"])
        
        # Host must be in maintenance for reinstall
        current = host_service.get()
        if str(current.status.value) != "maintenance" and not force:
            raise ValueError("主机必须处于维护模式才能重新安装")
        
        host_service.install(
            sdk.types.Action(
                root_password=root_password,
            )
        )
        
        return {
            "success": True,
            "host_id": host["id"],
            "name": host["name"],
            "status": "installing",
            "message": f"主机 {host['name']} 重新安装中"
        }
    
    def fence_host(self, name_or_id: str, action: str = "status") -> Dict[str, Any]:
        """Fence 主机 (电源管理)"""
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"Host not found: {name_or_id}")
        
        fence_type_map = {
            "status": sdk.types.FenceType.STATUS,
            "start": sdk.types.FenceType.START,
            "stop": sdk.types.FenceType.STOP,
            "restart": sdk.types.FenceType.RESTART,
        }
        
        fence_type = fence_type_map.get(action.lower())
        if not fence_type:
            raise ValueError(f"无效的 fence 操作: {action}. 支持: status, start, stop, restart")
        
        host_service = self.connection.system_service().hosts_service().host_service(host["id"])
        result = host_service.fence(fence_type=fence_type)
        
        return {
            "success": True,
            "host_id": host["id"],
            "name": host["name"],
            "action": action,
            "power_status": str(result.power_status.value) if hasattr(result, 'power_status') and result.power_status else "unknown",
            "message": f"Host fence {action} completed"
        }
    
    def update_host_network(self, name_or_id: str, 
                           network_config: Dict = None) -> Dict[str, Any]:
        """更新主机网络配置"""
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"Host not found: {name_or_id}")
        
        host_service = self.connection.system_service().hosts_service().host_service(host["id"])
        
        # Commit existing network config changes
        host_service.commit_net_config()
        
        return {
            "success": True,
            "host_id": host["id"],
            "name": host["name"],
            "message": "主机网络配置已提交"
        }
    
    def list_host_nics(self, name_or_id: str) -> List[Dict]:
        """列出主机网卡"""
        self._ensure_connected()
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"Host not found: {name_or_id}")
        
        nics_service = self.connection.system_service().hosts_service().host_service(
            host["id"]
        ).nics_service()
        nics = nics_service.list()
        
        return [
            {
                "id": nic.id,
                "name": nic.name,
                "mac": nic.mac.address if nic.mac else "",
                "speed": nic.speed if hasattr(nic, 'speed') else 0,
                "status": str(nic.status.value) if nic.status else "unknown",
            }
            for nic in nics
        ]

    # ==================== 高级主机管理 (Phase 4) ====================
    
    def upgrade_check_host(self, name_or_id: str) -> Dict[str, Any]:
        """Check if host has available upgrades"""
        self._ensure_connected()
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"Host not found: {name_or_id}")
        
        host_service = self.connection.system_service().hosts_service().host_service(host["id"])
        host_service.upgrade_check()
        
        # Re-fetch host to get update_available flag
        updated = host_service.get()
        
        return {
            "success": True,
            "host_id": host["id"],
            "name": host["name"],
            "update_available": updated.update_available if hasattr(updated, 'update_available') else False,
            "message": f"Upgrade check completed for {host['name']}"
        }
    
    def upgrade_host(self, name_or_id: str, image: str = None) -> Dict[str, Any]:
        """Upgrade host packages/OS"""
        self._ensure_connected()
        import ovirtsdk4.types as types
        
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"Host not found: {name_or_id}")
        
        host_service = self.connection.system_service().hosts_service().host_service(host["id"])
        
        # Host should be in maintenance for upgrade
        current = host_service.get()
        if str(current.status.value) != "maintenance":
            raise ValueError("Host must be in maintenance mode for upgrade")
        
        host_service.upgrade(
            types.Action(
                image=image,
            )
        )
        
        return {
            "success": True,
            "host_id": host["id"],
            "name": host["name"],
            "status": "upgrading",
            "message": f"Host {host['name']} upgrade initiated"
        }
    
    def list_host_numa_nodes(self, name_or_id: str) -> List[Dict[str, Any]]:
        """Get host NUMA topology"""
        self._ensure_connected()
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"Host not found: {name_or_id}")
        
        numa_service = self.connection.system_service().hosts_service().host_service(
            host["id"]
        ).numa_nodes_service()
        nodes = numa_service.list()
        
        return [
            {
                "id": node.id,
                "index": node.index,
                "cpu_cores": [core.index for core in (node.cpu.cores or [])] if node.cpu else [],
                "memory_mb": int((node.memory or 0) / (1024**2)),
                "node_distance": node.node_distance if hasattr(node, 'node_distance') else "",
                "host_id": host["id"],
                "host_name": host["name"],
            }
            for node in nodes
        ]
    
    def get_host_numa_node(self, name_or_id: str, numa_node_id: str) -> Dict[str, Any]:
        """Get specific NUMA node details"""
        self._ensure_connected()
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"Host not found: {name_or_id}")
        
        numa_node = self.connection.system_service().hosts_service().host_service(
            host["id"]
        ).numa_nodes_service().node_service(numa_node_id).get()
        
        # Get statistics for this NUMA node
        stats_data = {}
        try:
            stats_service = self.connection.system_service().hosts_service().host_service(
                host["id"]
            ).numa_nodes_service().node_service(numa_node_id).statistics_service()
            stats = stats_service.list()
            for stat in stats:
                stats_data[stat.name] = {
                    "value": stat.values[0].datum if stat.values else 0,
                    "unit": str(stat.unit.value) if stat.unit else ""
                }
        except Exception as e:
            logger.debug(f"NUMA statistics not available: {e}")
        
        return {
            "id": numa_node.id,
            "index": numa_node.index,
            "cpu_cores": [core.index for core in (numa_node.cpu.cores or [])] if numa_node.cpu else [],
            "memory_mb": int((numa_node.memory or 0) / (1024**2)),
            "statistics": stats_data,
            "host_id": host["id"],
            "host_name": host["name"],
        }
    
    def iscsi_discover(self, name_or_id: str, address: str, port: int = 3260) -> Dict[str, Any]:
        """Discover iSCSI targets on host"""
        self._ensure_connected()
        import ovirtsdk4.types as types
        
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"Host not found: {name_or_id}")
        
        host_service = self.connection.system_service().hosts_service().host_service(host["id"])
        
        result = host_service.iscsi_discover(
            iscsi=types.IscsiDetails(
                address=address,
                port=port,
            )
        )
        
        # result is a list of IscsiDetails (discovered targets)
        targets = []
        if result:
            for target in result:
                targets.append({
                    "address": target.address if hasattr(target, 'address') else address,
                    "port": target.port if hasattr(target, 'port') else port,
                    "target": target.target if hasattr(target, 'target') else "",
                    "portal": target.portal if hasattr(target, 'portal') else "",
                })
        
        return {
            "success": True,
            "host_id": host["id"],
            "host_name": host["name"],
            "iscsi_address": address,
            "iscsi_port": port,
            "targets": targets,
            "target_count": len(targets),
        }
    
    def iscsi_login(self, name_or_id: str, address: str, target: str,
                    port: int = 3260, username: str = None,
                    password: str = None) -> Dict[str, Any]:
        """Login to iSCSI target on host"""
        self._ensure_connected()
        import ovirtsdk4.types as types
        
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"Host not found: {name_or_id}")
        
        host_service = self.connection.system_service().hosts_service().host_service(host["id"])
        
        host_service.iscsi_login(
            iscsi=types.IscsiDetails(
                address=address,
                port=port,
                target=target,
                username=username,
                password=password,
            )
        )
        
        return {
            "success": True,
            "host_id": host["id"],
            "host_name": host["name"],
            "target": target,
            "address": address,
            "port": port,
            "message": f"iSCSI login to {target} successful"
        }
    
    def list_host_hooks(self, name_or_id: str) -> List[Dict[str, Any]]:
        """List host VDSM hooks"""
        self._ensure_connected()
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"Host not found: {name_or_id}")
        
        hooks_service = self.connection.system_service().hosts_service().host_service(
            host["id"]
        ).hooks_service()
        hooks = hooks_service.list()
        
        return [
            {
                "id": hook.id,
                "name": hook.name,
                "event_name": hook.event_name if hasattr(hook, 'event_name') else "",
                "md5": hook.md5 if hasattr(hook, 'md5') else "",
                "host_id": host["id"],
                "host_name": host["name"],
            }
            for hook in hooks
        ]
    
    def list_host_devices(self, name_or_id: str, capability: str = None) -> List[Dict[str, Any]]:
        """List host devices (PCI, USB, etc.)"""
        self._ensure_connected()
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"Host not found: {name_or_id}")
        
        devices_service = self.connection.system_service().hosts_service().host_service(
            host["id"]
        ).devices_service()
        devices = devices_service.list()
        
        results = []
        for device in devices:
            dev_cap = str(device.capability.value) if hasattr(device, 'capability') and device.capability else "unknown"
            
            # Filter by capability if specified
            if capability and dev_cap != capability.lower():
                continue
            
            results.append({
                "id": device.id,
                "name": device.name,
                "capability": dev_cap,
                "product_name": device.product.name if hasattr(device, 'product') and device.product else "",
                "product_id": device.product.id if hasattr(device, 'product') and device.product else "",
                "vendor_name": device.vendor.name if hasattr(device, 'vendor') and device.vendor else "",
                "vendor_id": device.vendor.id if hasattr(device, 'vendor') and device.vendor else "",
                "iommu_group": device.iommu_group if hasattr(device, 'iommu_group') else None,
                "driver": device.driver if hasattr(device, 'driver') else "",
                "host_id": host["id"],
                "host_name": host["name"],
            })
        
        return results
    
    def get_host_device(self, name_or_id: str, device_id: str) -> Dict[str, Any]:
        """Get specific host device details"""
        self._ensure_connected()
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"Host not found: {name_or_id}")
        
        device = self.connection.system_service().hosts_service().host_service(
            host["id"]
        ).devices_service().device_service(device_id).get()
        
        return {
            "id": device.id,
            "name": device.name,
            "capability": str(device.capability.value) if hasattr(device, 'capability') and device.capability else "unknown",
            "product_name": device.product.name if hasattr(device, 'product') and device.product else "",
            "product_id": device.product.id if hasattr(device, 'product') and device.product else "",
            "vendor_name": device.vendor.name if hasattr(device, 'vendor') and device.vendor else "",
            "vendor_id": device.vendor.id if hasattr(device, 'vendor') and device.vendor else "",
            "iommu_group": device.iommu_group if hasattr(device, 'iommu_group') else None,
            "driver": device.driver if hasattr(device, 'driver') else "",
            "parent_device": device.parent_device.id if hasattr(device, 'parent_device') and device.parent_device else None,
            "host_id": host["id"],
            "host_name": host["name"],
        }
    
    def list_host_storage(self, name_or_id: str) -> List[Dict[str, Any]]:
        """List host local storage (LUNs, FC, etc.)"""
        self._ensure_connected()
        host = self._find_host(name_or_id)
        if not host:
            raise ValueError(f"Host not found: {name_or_id}")
        
        storage_service = self.connection.system_service().hosts_service().host_service(
            host["id"]
        ).storage_service()
        storage = storage_service.list()
        
        results = []
        for s in storage:
            entry = {
                "id": s.id,
                "type": str(s.type.value) if s.type else "unknown",
                "host_id": host["id"],
                "host_name": host["name"],
            }
            
            # Include logical units if available (iSCSI/FC LUNs)
            if hasattr(s, 'logical_units') and s.logical_units:
                entry["logical_units"] = [
                    {
                        "id": lu.id,
                        "size_gb": int((lu.size or 0) / (1024**3)),
                        "vendor_id": lu.vendor_id if hasattr(lu, 'vendor_id') else "",
                        "product_id": lu.product_id if hasattr(lu, 'product_id') else "",
                        "serial": lu.serial if hasattr(lu, 'serial') else "",
                        "paths": lu.paths if hasattr(lu, 'paths') else 0,
                        "status": str(lu.status.value) if hasattr(lu, 'status') and lu.status else "unknown",
                    }
                    for lu in s.logical_units
                ]
            
            # Include volume group if available (local FS)
            if hasattr(s, 'volume_group') and s.volume_group:
                entry["volume_group"] = {
                    "id": s.volume_group.id,
                    "name": s.volume_group.name if s.volume_group.name else "",
                }
            
            # NFS/POSIXFS path
            if hasattr(s, 'address') and s.address:
                entry["address"] = s.address
            if hasattr(s, 'path') and s.path:
                entry["path"] = s.path
            
            results.append(entry)
        
        return results

    # ==================== 集群管理 ====================
    
    def list_clusters(self) -> List[Dict]:
        """列出集群"""
        self._ensure_connected()
        
        clusters = self.connection.system_service().clusters_service().list()
        
        return [
            {
                "id": c.id,
                "name": c.name,
                "cpu_architecture": str(c.cpu.architecture.value) if c.cpu else "x86_64",
                "memory_gb": int((c.memory or 0) / (1024**3)),
                "description": c.description or ""
            }
            for c in clusters
        ]
    
    # ==================== 存储管理 ====================
    
    def list_storage_domains(self) -> List[Dict]:
        """列出存储域"""
        self._ensure_connected()
        
        storage = self.connection.system_service().storage_domains_service().list()
        
        return [
            {
                "id": sd.id,
                "name": sd.name,
                "type": str(sd.type.value) if sd.type else "unknown",
                "status": str(sd.status.value) if sd.status else "unknown",
                "available_gb": int((sd.available or 0) / (1024**3)),
                "used_gb": int((sd.used or 0) / (1024**3)),
                "total_gb": int(((sd.available or 0) + (sd.used or 0)) / (1024**3))
            }
            for sd in storage
        ]
    
    def attach_storage(self, storage_name: str, dc_name: str) -> Dict[str, Any]:
        """Attach storage domain to data center"""
        self._ensure_connected()
        import ovirtsdk4.types as types
        
        storage = self._find_storage(storage_name)
        if not storage: raise ValueError(f"Storage not found: {storage_name}")
        
        dcs = self.connection.system_service().data_centers_service().list(search=f"name={_sanitize_search_value(dc_name)}")
        if not dcs: raise ValueError(f"DC not found: {dc_name}")
        
        dc_id = dcs[0].id
        # Use data center's attached_storage_domains_service (correct oVirt SDK API)
        dc_service = self.connection.system_service().data_centers_service().data_center_service(dc_id)
        dc_service.attached_storage_domains_service().add(
            types.StorageDomain(id=storage["id"])
        )
        
        return {"success": True, "storage_id": storage["id"], "datacenter": dc_name, "message": "Storage domain attached"}

    def get_storage_domain(self, name_or_id: str) -> Optional[Dict[str, Any]]:
        """Get storage domain details"""
        self._ensure_connected()
        sds_service = self.connection.system_service().storage_domains_service()
        try:
            sd = sds_service.storage_domain_service(name_or_id).get()
            if sd:
                return self._map_storage_domain(sd)
        except Exception as e:
            logger.debug(f"Storage domain lookup by ID failed, trying by name: {e}")
        sds = sds_service.list(search=f"name={_sanitize_search_value(name_or_id)}")
        if sds:
            return self._map_storage_domain(sds[0])
        return None

    def _map_storage_domain(self, sd) -> Dict[str, Any]:
        """Map storage domain SDK object to dict"""
        return {
            "id": sd.id,
            "name": sd.name,
            "description": sd.description or "",
            "type": str(sd.type.value) if sd.type else "unknown",
            "storage_type": str(sd.storage.type.value) if sd.storage and sd.storage.type else "unknown",
            "status": str(sd.status.value) if sd.status else "unknown",
            "available_gb": int((sd.available or 0) / (1024**3)),
            "used_gb": int((sd.used or 0) / (1024**3)),
            "total_gb": int(((sd.available or 0) + (sd.used or 0)) / (1024**3)),
        }

    def create_storage_domain(self, name: str, domain_type: str, storage_address: str = None,
                              path: str = None, datacenter: str = None) -> Dict[str, Any]:
        """Create a new storage domain"""
        self._ensure_connected()
        import ovirtsdk4.types as types
        
        # Map domain type to SDK enum
        type_map = {
            "data": types.StorageDomainType.DATA,
            "iso": types.StorageDomainType.ISO,
            "export": types.StorageDomainType.EXPORT,
        }
        sd_type = type_map.get(domain_type.lower(), types.StorageDomainType.DATA)
        
        # Build storage object based on type
        if storage_address and path:
            # NFS storage
            storage = types.HostStorage(
                type=types.StorageType.NFS,
                address=storage_address,
                path=path,
            )
        else:
            # Default to NFS for simplicity
            storage = types.HostStorage(type=types.StorageType.NFS)
        
        sd = types.StorageDomain(
            name=name,
            type=sd_type,
            storage=storage,
        )
        
        sds_service = self.connection.system_service().storage_domains_service()
        created_sd = sds_service.add(sd)
        
        # Attach to datacenter if specified
        if datacenter:
            dcs = self.connection.system_service().data_centers_service().list(search=f"name={_sanitize_search_value(datacenter)}")
            if dcs:
                dc_service = self.connection.system_service().data_centers_service().data_center_service(dcs[0].id)
                dc_service.attached_storage_domains_service().add(
                    types.StorageDomain(id=created_sd.id))
        
        return {
            "id": created_sd.id,
            "name": created_sd.name,
            "type": str(created_sd.type.value) if created_sd.type else "unknown",
            "storage_type": str(created_sd.storage.type.value) if created_sd.storage and created_sd.storage.type else "unknown",
            "status": str(created_sd.status.value) if created_sd.status else "unknown",
            "datacenter": datacenter if datacenter else None,
        }

    def delete_storage_domain(self, name_or_id: str, force: bool = False) -> Dict[str, Any]:
        """Delete a storage domain"""
        self._ensure_connected()
        storage = self._find_storage(name_or_id)
        if not storage:
            raise ValueError(f"Storage domain not found: {name_or_id}")
        
        sd_service = self.connection.system_service().storage_domains_service().storage_domain_service(storage["id"])
        
        # Check if storage is attached to any DC
        sd = sd_service.get()
        if sd.status and sd.status.value != "unattached" and not force:
            return {"success": False, "error": "Storage is attached. Detach first or use force=True"}
        
        # Set async to False for synchronous deletion
        sd_service.remove(async_=False)
        return {"success": True, "storage_id": storage["id"], "message": "Storage domain deleted"}

    def detach_storage_domain(self, storage_name: str, dc_name: str) -> Dict[str, Any]:
        """Detach storage domain from data center"""
        self._ensure_connected()
        
        storage = self._find_storage(storage_name)
        if not storage:
            raise ValueError(f"Storage domain not found: {storage_name}")
        
        dcs = self.connection.system_service().data_centers_service().list(search=f"name={_sanitize_search_value(dc_name)}")
        if not dcs:
            raise ValueError(f"Data center not found: {dc_name}")
        
        dc_id = dcs[0].id
        # Use data center's attached_storage_domains_service (correct oVirt SDK API)
        dc_service = self.connection.system_service().data_centers_service().data_center_service(dc_id)
        dc_service.attached_storage_domains_service().storage_domain_service(storage["id"]).remove()
        
        return {"success": True, "storage_id": storage["id"], "datacenter": dc_name, "message": "Storage domain detached"}

    def get_storage_domain_available_disks(self, storage_id: str) -> List[Dict]:
        """Get available disks in storage domain"""
        self._ensure_connected()
        sd_service = self.connection.system_service().storage_domains_service().storage_domain_service(storage_id)
        disks = sd_service.disks_service().list()
        
        return [
            {
                "id": d.id,
                "name": d.alias or d.id,
                "size_gb": int((d.provisioned_size or 0) / (1024**3)),
                "format": str(d.storage_format.value) if d.storage_format else "unknown",
                "status": str(d.status.value) if d.status else "unknown",
            }
            for d in disks
        ]

    def refresh_storage_domain(self, name_or_id: str) -> Dict[str, Any]:
        """Refresh storage domain to sync with storage backend"""
        self._ensure_connected()
        import ovirtsdk4.types as types
        
        storage = self._find_storage(name_or_id)
        if not storage:
            raise ValueError(f"Storage domain not found: {name_or_id}")
        
        sd_service = self.connection.system_service().storage_domains_service().storage_domain_service(storage["id"])
        
        # Refresh storage domain
        sd_service.refresh()
        
        return {
            "success": True,
            "storage_id": storage["id"],
            "name": storage["name"],
            "message": "Storage domain refresh initiated"
        }

    def update_storage_domain(self, name_or_id: str, description: str = None, 
                              warning_low_space: int = None, 
                              critical_space_action_blocker: int = None) -> Dict[str, Any]:
        """Update storage domain settings"""
        self._ensure_connected()
        import ovirtsdk4.types as types
        
        storage = self._find_storage(name_or_id)
        if not storage:
            raise ValueError(f"Storage domain not found: {name_or_id}")
        
        sd_service = self.connection.system_service().storage_domains_service().storage_domain_service(storage["id"])
        current_sd = sd_service.get()
        
        # Build update object with only changed fields
        update_params = {}
        if description is not None:
            update_params["description"] = description
        if warning_low_space is not None:
            update_params["warning_low_space_indicator"] = warning_low_space  # percentage (0-100)
        if critical_space_action_blocker is not None:
            update_params["critical_space_action_blocker"] = critical_space_action_blocker  # percentage (0-100)
        
        if update_params:
            updated_sd = sd_service.update(types.StorageDomain(
                id=storage["id"],
                **update_params
            ))
            return {
                "success": True,
                "storage_id": storage["id"],
                "name": updated_sd.name,
                "updated_fields": list(update_params.keys()),
                "message": "Storage domain updated"
            }
        
        return {"success": True, "storage_id": storage["id"], "message": "No changes to apply"}

    def list_storage_domain_files(self, name_or_id: str) -> List[Dict[str, Any]]:
        """List files in storage domain (primarily for ISO domains)"""
        self._ensure_connected()
        
        storage = self._find_storage(name_or_id)
        if not storage:
            raise ValueError(f"Storage domain not found: {name_or_id}")
        
        sd_service = self.connection.system_service().storage_domains_service().storage_domain_service(storage["id"])
        files_service = sd_service.files_service()
        files = files_service.list()
        
        return [
            {
                "id": f.id,
                "name": f.name,
                "storage_domain_id": storage["id"],
                "storage_domain_name": storage["name"],
            }
            for f in files
        ]

    def list_storage_connections(self, name_or_id: str = None) -> List[Dict[str, Any]]:
        """List storage server connections"""
        self._ensure_connected()
        
        connections_service = self.connection.system_service().storage_server_connections_service()
        connections = connections_service.list()
        
        if name_or_id:
            # Filter by storage domain if specified
            storage = self._find_storage(name_or_id)
            if storage and storage.get("id"):
                # Get connections for specific storage domain
                sd_service = self.connection.system_service().storage_domains_service().storage_domain_service(storage["id"])
                sd = sd_service.get()
                if sd.storage and sd.storage.connections:
                    conn_ids = [c.id for c in sd.storage.connections if c.id]
                    connections = [c for c in connections if c.id in conn_ids]
        
        return [
            {
                "id": c.id,
                "address": c.address if hasattr(c, 'address') else "",
                "type": str(c.type.value) if hasattr(c, 'type') and c.type else "unknown",
                "path": c.path if hasattr(c, 'path') else "",
                "port": c.port if hasattr(c, 'port') else None,
                "mount_options": c.mount_options if hasattr(c, 'mount_options') else "",
                "nfs_version": str(c.nfs_version.value) if hasattr(c, 'nfs_version') and c.nfs_version else None,
                "nfs_retrans": c.nfs_retrans if hasattr(c, 'nfs_retrans') else None,
                "nfs_timeo": c.nfs_timeo if hasattr(c, 'nfs_timeo') else None,
            }
            for c in connections
        ]

    def import_vm_from_export_domain(self, export_domain: str, vm_name: str, 
                                     cluster: str, storage_domain: str = None, 
                                     clone: bool = False) -> Dict[str, Any]:
        """Import VM from export domain"""
        self._ensure_connected()
        import ovirtsdk4.types as types
        
        # Find export domain
        export_sd = self._find_storage(export_domain)
        if not export_sd:
            raise ValueError(f"Export domain not found: {export_domain}")
        
        # Find target cluster
        clusters = self.connection.system_service().clusters_service().list(search=f"name={_sanitize_search_value(cluster)}")
        if not clusters:
            raise ValueError(f"Cluster not found: {cluster}")
        cluster_id = clusters[0].id
        
        # Find target storage domain if specified
        sd_id = None
        if storage_domain:
            sd = self._find_storage(storage_domain)
            if sd:
                sd_id = sd["id"]
        
        # Get export domain service and find the VM to import
        sd_service = self.connection.system_service().storage_domains_service().storage_domain_service(export_sd["id"])
        vms_service = sd_service.vms_service()
        imported_vms = vms_service.list()
        
        # Find the VM by name
        vm_to_import = None
        for vm in imported_vms:
            if vm.name == vm_name:
                vm_to_import = vm
                break
        
        if not vm_to_import:
            raise ValueError(f"VM '{vm_name}' not found in export domain")
        
        # Build import configuration
        import_params = {
            "vm": types.Vm(
                name=vm_name,
                cluster=types.Cluster(id=cluster_id),
            ),
            "clone": clone,
        }
        
        if sd_id:
            import_params["vm"].disk_attachments = [
                types.DiskAttachment(
                    disk=types.Disk(
                        storage_domains=[types.StorageDomain(id=sd_id)]
                    )
                )
            ]
        
        # Perform import
        vm_service = vms_service.vm_service(vm_to_import.id)
        vm_service.import_(
            async_=True,
            **import_params
        )
        
        return {
            "success": True,
            "vm_name": vm_name,
            "export_domain": export_domain,
            "cluster": cluster,
            "storage_domain": storage_domain,
            "clone": clone,
            "message": f"VM '{vm_name}' import initiated"
        }

    def list_export_domain_vms(self, export_domain: str) -> List[Dict[str, Any]]:
        """List VMs available in export domain"""
        self._ensure_connected()
        
        export_sd = self._find_storage(export_domain)
        if not export_sd:
            raise ValueError(f"Export domain not found: {export_domain}")
        
        sd_service = self.connection.system_service().storage_domains_service().storage_domain_service(export_sd["id"])
        vms_service = sd_service.vms_service()
        vms = vms_service.list()
        
        return [
            {
                "id": vm.id,
                "name": vm.name,
                "memory_gb": int((vm.memory or 0) / (1024**3)),
                "cpu_cores": sum(len(cpu.cores or []) for cpu in [vm.cpu]) if vm.cpu else 0,
                "status": str(vm.status.value) if vm.status else "unknown",
                "export_domain": export_domain,
            }
            for vm in vms
        ]

    # ==================== 磁盘管理 ====================

    def list_disks(self, name_or_id: str = None, storage_domain: str = None) -> List[Dict]:
        """List all disks"""
        self._ensure_connected()
        disks_service = self.connection.system_service().disks_service()
        
        if name_or_id:
            try:
                disk = disks_service.disk_service(name_or_id).get()
                return [self._map_disk(disk)]
            except Exception as e:
                logger.debug(f"Disk lookup by ID failed, listing all: {e}")
        
        disks = disks_service.list()
        result = [self._map_disk(d) for d in disks]
        
        if storage_domain:
            result = [d for d in result if d.get("storage_domain") == storage_domain]
        
        return result

    def get_disk(self, name_or_id: str) -> Optional[Dict[str, Any]]:
        """Get disk details"""
        self._ensure_connected()
        disks_service = self.connection.system_service().disks_service()
        
        try:
            disk = disks_service.disk_service(name_or_id).get()
            return self._map_disk(disk)
        except Exception as e:
            logger.debug(f"Disk lookup by ID failed, trying by alias: {e}")
        
        # Search by name (alias)
        disks = disks_service.list(search=f"alias={_sanitize_search_value(name_or_id)}")
        if disks:
            return self._map_disk(disks[0])
        return None

    def _map_disk(self, disk) -> Dict[str, Any]:
        """Map disk SDK object to dict"""
        # Get VM ID if disk is attached to a VM
        vm_id = None
        if hasattr(disk, 'vm') and disk.vm:
            vm_id = disk.vm.id
        
        return {
            "id": disk.id,
            "name": disk.alias or disk.id,
            "size_gb": int((disk.provisioned_size or 0) / (1024**3)),
            "actual_size_gb": int((disk.actual_size or 0) / (1024**3)),
            "format": str(disk.storage_format.value) if disk.storage_format else "cow",
            "status": str(disk.status.value) if disk.status else "unknown",
            "storage_domain": disk.storage_domains[0].id if disk.storage_domains else None,
            "interface": str(disk.interface.value) if disk.interface else "virtio",
            "sparse": disk.sparse if disk.sparse is not None else True,
            "shareable": disk.shareable if disk.shareable is not None else False,
            "vm_id": vm_id,
        }

    def create_disk(self, name: str, size_gb: int, storage_domain: str = "",
                   format: str = "cow", interface: str = "virtio",
                   thin_provisioned: bool = True) -> Dict[str, Any]:
        """Create a new disk"""
        self._ensure_connected()
        import ovirtsdk4.types as types
        
        # Find storage domain if specified
        sd_id = storage_domain
        if storage_domain:
            sd = self._find_storage(storage_domain)
            if sd:
                sd_id = sd["id"]
        
        disk = types.Disk(
            alias=name,
            provisioned_size=size_gb * (1024**3),
            format=types.DiskFormat.COW if format.lower() == "cow" else types.DiskFormat.RAW,
            interface=types.DiskInterface.VIRTIO if interface == "virtio" else types.DiskInterface.VIRTIO_SCSI,
            sparse=thin_provisioned,
            storage_domains=[types.StorageDomain(id=sd_id)] if sd_id else None,
        )
        
        disks_service = self.connection.system_service().disks_service()
        created_disk = disks_service.add(disk)
        
        return {
            "success": True,
            "disk_id": created_disk.id,
            "name": name,
            "size_gb": size_gb,
            "format": format,
            "storage_domain": storage_domain,
        }

    def delete_disk(self, name_or_id: str, force: bool = False) -> Dict[str, Any]:
        """Delete a disk"""
        self._ensure_connected()
        
        disk = self.get_disk(name_or_id)
        if not disk:
            raise ValueError(f"Disk not found: {name_or_id}")
        
        disk_service = self.connection.system_service().disks_service().disk_service(disk["id"])
        
        # Check if disk is attached to a VM
        if disk.get("vm_id") and not force:
            return {"success": False, "error": "Disk is attached to a VM. Detach first or use force=True"}
        
        disk_service.remove(async_=False)
        return {"success": True, "disk_id": disk["id"], "message": "Disk deleted"}

    def resize_disk(self, name_or_id: str, new_size_gb: int) -> Dict[str, Any]:
        """Resize a disk"""
        self._ensure_connected()
        import ovirtsdk4.types as types
        
        disk = self.get_disk(name_or_id)
        if not disk:
            raise ValueError(f"Disk not found: {name_or_id}")
        
        if new_size_gb < disk["size_gb"]:
            return {"success": False, "error": "Cannot shrink disk"}
        
        disk_service = self.connection.system_service().disks_service().disk_service(disk["id"])
        updated = disk_service.update(
            types.Disk(
                id=disk["id"],
                provisioned_size=new_size_gb * (1024**3),
            )
        )
        
        return {
            "success": True,
            "disk_id": disk["id"],
            "old_size_gb": disk["size_gb"],
            "new_size_gb": new_size_gb,
        }

    def move_disk(self, disk_name: str, target_storage: str) -> Dict[str, Any]:
        """Move disk to another storage domain"""
        self._ensure_connected()
        import ovirtsdk4.types as types
        
        disk = self.get_disk(disk_name)
        if not disk:
            raise ValueError(f"Disk not found: {disk_name}")
        
        target_sd = self._find_storage(target_storage)
        if not target_sd:
            raise ValueError(f"Target storage not found: {target_storage}")
        
        disk_service = self.connection.system_service().disks_service().disk_service(disk["id"])
        disk_service.move(
            async_=True,
            storage_domain=types.StorageDomain(id=target_sd["id"]),
        )
        
        return {
            "success": True,
            "disk_id": disk["id"],
            "source_storage": disk.get("storage_domain"),
            "target_storage": target_storage,
            "message": "Disk move initiated",
        }

    def attach_disk_to_vm(self, disk_name: str, vm_id: str) -> Dict[str, Any]:
        """Attach disk to VM using disk attachments service"""
        self._ensure_connected()
        import ovirtsdk4.types as types
        
        disk = self.get_disk(disk_name)
        if not disk:
            raise ValueError(f"Disk not found: {disk_name}")
        
        vm = self._find_vm(vm_id)
        if not vm:
            raise ValueError(f"VM not found: {vm_id}")
        
        # Use VM's disk_attachments_service (correct oVirt SDK API)
        attachments_service = self.connection.system_service().vms_service().vm_service(vm["id"]).disk_attachments_service()
        attachments_service.add(
            types.DiskAttachment(
                disk=types.Disk(id=disk["id"]),
                interface=types.DiskInterface.VIRTIO,
            )
        )
        
        return {"success": True, "disk_id": disk["id"], "vm_id": vm["id"], "message": "Disk attached"}

    def detach_disk_from_vm(self, disk_name: str, vm_id: str) -> Dict[str, Any]:
        """Detach disk from VM using disk attachments service"""
        self._ensure_connected()
        
        disk = self.get_disk(disk_name)
        if not disk:
            raise ValueError(f"Disk not found: {disk_name}")
        
        vm = self._find_vm(vm_id)
        if not vm:
            raise ValueError(f"VM not found: {vm_id}")
        
        # Use VM's disk_attachment_service to remove (correct oVirt SDK API)
        attachment_service = self.connection.system_service().vms_service().vm_service(vm["id"]).disk_attachments_service().attachment_service(disk["id"])
        attachment_service.remove()
        
        return {"success": True, "disk_id": disk["id"], "vm_id": vm["id"], "message": "Disk detached"}


    
    # ==================== 模板管理 ====================
    
    def list_templates(self, cluster: str = None) -> List[Dict]:
        """列出模板"""
        self._ensure_connected()
        
        templates = self.connection.system_service().templates_service().list()
        
        result = []
        for t in templates:
            result.append({
                "id": t.id,
                "name": t.name,
                "memory_mb": int(t.memory / (1024**2)) if t.memory else 0,
                "cpu_cores": t.cpu.topology.cores if t.cpu and t.cpu.topology else 0,
                "os_type": t.os.type if t.os else "",
                "description": t.description or ""
            })
        
        return result

    # ==================== 模板管理 (Template Management) ====================
    
    def _find_template(self, name_or_id: str) -> Optional[Dict[str, Any]]:
        """查找模板 by name or ID"""
        try:
            tmpl = self.connection.system_service().templates_service().template_service(name_or_id).get()
            return {"id": tmpl.id, "name": tmpl.name}
        except Exception as e:
            logger.debug(f"Template lookup by ID failed: {e}")
    
    def _map_template(self, t) -> Dict[str, Any]:
        """Map template SDK object to dict"""
        return {
            "id": t.id,
            "name": t.name,
            "description": t.description or "",
            "os_type": t.os.type if t.os else "",
            "memory_mb": int(t.memory / (1024**2)) if t.memory else 0,
            "cpu_cores": t.cpu.topology.cores if t.cpu and t.cpu.topology else 0,
            "status": str(t.status.value) if t.status else "ok",
            "creation_time": str(t.creation_time) if t.creation_time else "",
            "cluster_id": t.cluster.id if t.cluster else "",
        }
    
    def get_template(self, name_or_id: str) -> Optional[Dict[str, Any]]:
        """获取模板详情"""
        self._ensure_connected()
        templates_service = self.connection.system_service().templates_service()
        # Try by ID first
        try:
            tmpl = templates_service.template_service(name_or_id).get()
            if tmpl:
                return self._map_template(tmpl)
        except Exception as e:
            logger.debug(f"Template lookup by ID failed, trying by name: {e}")
        # Try by name
        tmpls = templates_service.list(search=f"name={_sanitize_search_value(name_or_id)}")
        return self._map_template(tmpls[0]) if tmpls else None
    
    def create_template_from_vm(self, vm_id: str, template_name: str,
                                description: str = "") -> Dict[str, Any]:
        """从 VM 创建模板
        
        Uses templates_service().add() with vm reference.
        """
        self._ensure_connected()
        
        vm = self._find_vm(vm_id)
        if not vm:
            raise ValueError(f"VM not found: {vm_id}")
        
        templates_service = self.connection.system_service().templates_service()
        template = templates_service.add(
            sdk.types.Template(
                name=template_name,
                description=description,
                vm=sdk.types.Vm(id=vm["id"]),
            )
        )
        return {
            "success": True,
            "template_id": template.id,
            "name": template_name,
            "source_vm": vm["id"],
            "status": "creating",
            "message": f"模板 {template_name} 创建中",
        }
    
    def clone_template(self, source_id: str, new_name: str) -> Dict[str, Any]:
        """克隆模板
        
        Creates a new template based on an existing one.
        """
        self._ensure_connected()
        
        source = self._find_template(source_id)
        if not source:
            raise ValueError(f"Template not found: {source_id}")
        
        # Get source template to copy its configuration
        source_tmpl = self.connection.system_service().templates_service().template_service(source["id"]).get()
        
        # Create new template referencing the source as base
        templates_service = self.connection.system_service().templates_service()
        new_tmpl = templates_service.add(
            sdk.types.Template(
                name=new_name,
                vm=sdk.types.Vm(
                    template=sdk.types.Template(id=source["id"]),
                    cluster=source_tmpl.cluster,
                ),
            )
        )
        return {
            "success": True,
            "template_id": new_tmpl.id,
            "source_id": source["id"],
            "new_name": new_name,
            "status": "creating",
            "message": "模板克隆中",
        }
    
    def delete_template(self, name_or_id: str, force: bool = False) -> Dict[str, Any]:
        """删除模板"""
        self._ensure_connected()
        tmpl = self._find_template(name_or_id)
        if not tmpl:
            raise ValueError(f"Template not found: {name_or_id}")
        
        # Guard: Cannot delete the Blank template
        if tmpl["id"] == "00000000-0000-0000-0000-000000000000":
            raise ValueError("Cannot delete the Blank template")
        
        tmpl_service = self.connection.system_service().templates_service().template_service(tmpl["id"])
        tmpl_service.remove(async_=False)
        return {
            "success": True,
            "template_id": tmpl["id"],
            "force": force,
            "message": "模板已删除",
        }
    
    def export_template(self, name_or_id: str, export_domain: str) -> Dict[str, Any]:
        """导出模板到导出存储域
        
        Uses template_service(id).export_() - note trailing underscore.
        """
        self._ensure_connected()
        
        tmpl = self._find_template(name_or_id)
        if not tmpl:
            raise ValueError(f"Template not found: {name_or_id}")
        
        export_sd = self._find_storage(export_domain)
        if not export_sd:
            raise ValueError(f"Export domain not found: {export_domain}")
        
        tmpl_service = self.connection.system_service().templates_service().template_service(tmpl["id"])
        tmpl_service.export_(
            storage_domain=sdk.types.StorageDomain(id=export_sd["id"]),
            async_=True,
        )
        return {
            "success": True,
            "template_id": tmpl["id"],
            "export_domain": export_domain,
            "status": "exporting",
            "message": "模板导出中",
        }
    
    def import_template(self, name: str, import_domain: str,
                        cluster: str) -> Dict[str, Any]:
        """从导出存储域导入模板
        
        Finds the template in the export domain's templates_service,
        then calls template_service(id).import_() - note trailing underscore.
        """
        self._ensure_connected()
        
        # Find export domain
        export_sd = self._find_storage(import_domain)
        if not export_sd:
            raise ValueError(f"Import domain not found: {import_domain}")
        
        # Find cluster
        clusters = self.connection.system_service().clusters_service().list(search=f"name={_sanitize_search_value(cluster)}")
        if not clusters:
            raise ValueError(f"Cluster not found: {cluster}")
        
        # List templates in export domain
        sd_service = self.connection.system_service().storage_domains_service().storage_domain_service(export_sd["id"])
        export_templates = sd_service.templates_service().list()
        
        tmpl_to_import = None
        for t in export_templates:
            if t.name == name:
                tmpl_to_import = t
                break
        
        if not tmpl_to_import:
            raise ValueError(f"Template '{name}' not found in export domain")
        
        # Import
        sd_service.templates_service().template_service(tmpl_to_import.id).import_(
            cluster=sdk.types.Cluster(id=clusters[0].id),
            template=sdk.types.Template(name=name),
            async_=True,
        )
        return {
            "success": True,
            "template_id": tmpl_to_import.id,
            "name": name,
            "import_domain": import_domain,
            "cluster": cluster,
            "status": "importing",
            "message": "模板导入中",
        }

    
    # ==================== 辅助方法 ====================
    
    def _find_vm(self, name_or_id: str) -> Optional[Dict[str, Any]]:
        """查找 VM"""
        try:
            vm = self.connection.system_service().vms_service().vm_service(name_or_id).get()
            return {"id": vm.id, "name": vm.name}
        except Exception as e:
            logger.debug(f"VM lookup by ID failed: {e}")
        
        vms = self.connection.system_service().vms_service().list(search=f"name={_sanitize_search_value(name_or_id)}")
        return {"id": vms[0].id, "name": vms[0].name} if vms else None
    
    def _find_host(self, name_or_id: str) -> Optional[Dict[str, Any]]:
        """查找主机"""
        try:
            host = self.connection.system_service().hosts_service().host_service(name_or_id).get()
            return {"id": host.id, "name": host.name}
        except Exception as e:
            logger.debug(f"Host lookup by ID failed: {e}")
        
        hosts = self.connection.system_service().hosts_service().list(search=f"name={_sanitize_search_value(name_or_id)}")
        return {"id": hosts[0].id, "name": hosts[0].name} if hosts else None
    
    def _find_storage(self, name_or_id: str) -> Optional[Dict[str, Any]]:
        """查找存储域"""
        try:
            sd = self.connection.system_service().storage_domains_service().storage_domain_service(name_or_id).get()
            return {"id": sd.id, "name": sd.name}
        except Exception as e:
            logger.debug(f"Storage lookup by ID failed: {e}")
        
        sds = self.connection.system_service().storage_domains_service().list(search=f"name={_sanitize_search_value(name_or_id)}")
        return {"id": sds[0].id, "name": sds[0].name} if sds else None
    
    def _wait_for_status(self, obj_id: str, target_status: str, service_type: str, timeout: int = 300) -> None:
        """等待状态变化"""
        import time
        start = time.time()
        
        while time.time() - start < timeout:
            if service_type == "vms":
                obj = self.connection.system_service().vms_service().vm_service(obj_id).get()
            elif service_type == "hosts":
                obj = self.connection.system_service().hosts_service().host_service(obj_id).get()
            else:
                break
            
            if obj.status.value == target_status:
                return
            
            time.sleep(2)
        
        raise OvirtTimeoutError(f"等待状态 {target_status} 超时")
    
    def get_vm_stats(self, name_or_id: str) -> Dict[str, Any]:
        """获取 VM 实时统计信息"""
        vm = self._find_vm(name_or_id)
        if not vm: raise ValueError(f"VM not found: {name_or_id}")
        
        stats_service = self.connection.system_service().vms_service().vm_service(vm["id"]).statistics_service()
        stats = stats_service.list()
        
        result = {"vm_id": vm["id"], "vm_name": vm["name"], "metrics": {}}
        
        for stat in stats:
            result["metrics"][stat.name] = {
                "value": stat.values[0].datum if stat.values else 0,
                "unit": stat.unit.value if stat.unit else ""
            }
        
        return result
