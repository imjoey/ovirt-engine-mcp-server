#!/usr/bin/env python3
"""
oVirt MCP Server - Model Context Protocol server for oVirt/RHV.

Provides 30+ tools for managing VMs, hosts, clusters, networks,
storage domains, templates, snapshots, and disks via MCP protocol.
"""

import asyncio
import functools
import logging
import signal
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .config import Config, load_config, sanitize_log_message
from .errors import (
    OvirtMCPError,
    OvirtConnectionError,
    NotFoundError,
    OvirtPermissionError,
    ValidationError as OvirtValidationError,
    OvirtTimeoutError,
    SDKError,
)
from .ovirt_mcp import OvirtMCP
from .validation import validate_tool_args, ValidationError
from .mcp_extensions import (
    NetworkMCP,
    ClusterMCP,
    TemplateMCP,
    MCP_TOOLS as EXTENSIONS_MCP_TOOLS,
)
from .mcp_datacenter import DataCenterMCP, MCP_TOOLS as DATACENTER_MCP_TOOLS
from .mcp_host_extended import HostExtendedMCP, MCP_TOOLS as HOST_EXTENDED_MCP_TOOLS
from .mcp_storage_extended import StorageExtendedMCP, MCP_TOOLS as STORAGE_EXTENDED_MCP_TOOLS
from .mcp_disk_extended import DiskExtendedMCP, MCP_TOOLS as DISK_EXTENDED_MCP_TOOLS
from .mcp_events import EventsMCP, MCP_TOOLS as EVENTS_MCP_TOOLS
from .mcp_affinity import AffinityMCP, MCP_TOOLS as AFFINITY_MCP_TOOLS

# 合并所有 MCP_TOOLS
MCP_TOOLS = {
    **EXTENSIONS_MCP_TOOLS,
    **DATACENTER_MCP_TOOLS,
    **HOST_EXTENDED_MCP_TOOLS,
    **STORAGE_EXTENDED_MCP_TOOLS,
    **DISK_EXTENDED_MCP_TOOLS,
    **EVENTS_MCP_TOOLS,
    **AFFINITY_MCP_TOOLS,
}

logger = logging.getLogger(__name__)

# ── Tool schemas ──────────────────────────────────────────────────────

TOOL_SCHEMAS: Dict[str, dict] = {
    # VM tools
    "vm_list": {
        "type": "object",
        "properties": {
            "cluster": {"type": "string", "description": "集群名称（可选，用于过滤）"},
            "status": {"type": "string", "description": "VM 状态过滤（up/down）"},
        },
    },
    "vm_get": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "VM 名称或 ID"}},
        "required": ["name_or_id"],
    },
    "vm_create": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "VM 名称"},
            "cluster": {"type": "string", "description": "目标集群"},
            "memory_mb": {"type": "number", "description": "内存（MB），默认 4096"},
            "cpu_cores": {"type": "number", "description": "CPU 核数，默认 2"},
            "template": {"type": "string", "description": "模板名称，默认 Blank"},
            "disk_size_gb": {"type": "number", "description": "磁盘大小（GB），默认 50"},
            "description": {"type": "string", "description": "VM 描述"},
        },
        "required": ["name", "cluster"],
    },
    "vm_start": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "VM 名称或 ID"}},
        "required": ["name_or_id"],
    },
    "vm_stop": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "VM 名称或 ID"},
            "graceful": {"type": "boolean", "description": "优雅关机，默认 true"},
        },
        "required": ["name_or_id"],
    },
    "vm_restart": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "VM 名称或 ID"}},
        "required": ["name_or_id"],
    },
    "vm_delete": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "VM 名称或 ID"},
            "force": {"type": "boolean", "description": "强制删除，默认 false"},
        },
        "required": ["name_or_id"],
    },
    "vm_update_resources": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "VM 名称或 ID"},
            "memory_mb": {"type": "number", "description": "新内存（MB）"},
            "cpu_cores": {"type": "number", "description": "新 CPU 核数"},
        },
        "required": ["name_or_id"],
    },
    "vm_stats": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "VM 名称或 ID"}},
        "required": ["name_or_id"],
    },

    # Snapshot tools
    "snapshot_list": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "VM 名称或 ID"}},
        "required": ["name_or_id"],
    },
    "snapshot_create": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "VM 名称或 ID"},
            "description": {"type": "string", "description": "快照描述"},
        },
        "required": ["name_or_id"],
    },
    "snapshot_restore": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "VM 名称或 ID"},
            "snapshot_id": {"type": "string", "description": "快照 ID"},
        },
        "required": ["name_or_id", "snapshot_id"],
    },
    "snapshot_delete": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "VM 名称或 ID"},
            "snapshot_id": {"type": "string", "description": "快照 ID"},
        },
        "required": ["name_or_id", "snapshot_id"],
    },

    # Disk tools
    "disk_list": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "VM 名称或 ID（可选）"},
            "storage_domain": {"type": "string", "description": "存储域名称（可选）"},
        },
    },
    "disk_create": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "磁盘名称"},
            "size_gb": {"type": "number", "description": "磁盘大小（GB）"},
            "storage_domain": {"type": "string", "description": "存储域名称"},
            "format": {"type": "string", "description": "磁盘格式（cow/raw），默认 cow"},
        },
        "required": ["name", "size_gb"],
    },
    "disk_attach": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "VM 名称或 ID"},
            "disk_id": {"type": "string", "description": "磁盘 ID"},
        },
        "required": ["name_or_id", "disk_id"],
    },

    # Network tools
    "network_list": {
        "type": "object",
        "properties": {"cluster": {"type": "string", "description": "集群名称（可选）"}},
    },
    "nic_list": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "VM 名称或 ID"}},
        "required": ["name_or_id"],
    },
    "nic_add": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "VM 名称或 ID"},
            "nic_name": {"type": "string", "description": "网卡名称"},
            "network": {"type": "string", "description": "网络名称"},
        },
        "required": ["name_or_id", "nic_name", "network"],
    },
    "nic_remove": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "VM 名称或 ID"},
            "nic_name": {"type": "string", "description": "网卡名称"},
        },
        "required": ["name_or_id", "nic_name"],
    },

    # Host tools
    "host_list": {
        "type": "object",
        "properties": {"cluster": {"type": "string", "description": "集群名称（可选）"}},
    },
    "host_activate": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "主机名称或 ID"}},
        "required": ["name_or_id"],
    },
    "host_deactivate": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "主机名称或 ID"}},
        "required": ["name_or_id"],
    },

    # Cluster tools
    "cluster_list": {"type": "object", "properties": {}},
    "cluster_hosts": {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "集群名称"}},
        "required": ["name"],
    },
    "cluster_vms": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "集群名称"},
            "status": {"type": "string", "description": "VM 状态过滤（可选）"},
        },
        "required": ["name"],
    },
    "cluster_cpu_load": {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "集群名称"}},
        "required": ["name"],
    },

    # Storage tools
    "storage_list": {"type": "object", "properties": {}},
    "storage_attach": {
        "type": "object",
        "properties": {
            "storage_name": {"type": "string", "description": "存储域名称"},
            "dc_name": {"type": "string", "description": "数据中心名称"},
        },
        "required": ["storage_name", "dc_name"],
    },

    # Template tools
    "template_list": {
        "type": "object",
        "properties": {"cluster": {"type": "string", "description": "集群名称（可选）"}},
    },
    "template_vm_create": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "VM 名称"},
            "template": {"type": "string", "description": "模板名称"},
            "cluster": {"type": "string", "description": "目标集群"},
            "memory_mb": {"type": "number", "description": "内存（MB），可选"},
            "cpu_cores": {"type": "number", "description": "CPU 核数，可选"},
        },
        "required": ["name", "template", "cluster"],
    },

    # DataCenter tools
    "datacenter_list": {"type": "object", "properties": {}},
    "datacenter_get": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "数据中心名称或 ID"}},
        "required": ["name_or_id"],
    },
    "datacenter_create": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "数据中心名称"},
            "storage_type": {"type": "string", "description": "存储类型（nfs/fc/iscsi等），默认 nfs"},
            "description": {"type": "string", "description": "描述"},
        },
        "required": ["name"],
    },
    "datacenter_update": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "数据中心名称或 ID"},
            "new_name": {"type": "string", "description": "新名称（可选）"},
            "description": {"type": "string", "description": "新描述（可选）"},
        },
        "required": ["name_or_id"],
    },
    "datacenter_delete": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "数据中心名称或 ID"}},
        "required": ["name_or_id"],
    },

    # Host Extended tools
    "host_get": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "主机名称或 ID"}},
        "required": ["name_or_id"],
    },
    "host_add": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "主机名称"},
            "cluster": {"type": "string", "description": "集群名称"},
            "address": {"type": "string", "description": "主机地址"},
            "password": {"type": "string", "description": "SSH 密码（可选）"},
            "ssh_port": {"type": "number", "description": "SSH 端口，默认 22"},
        },
        "required": ["name", "cluster", "address"],
    },
    "host_remove": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "主机名称或 ID"},
            "force": {"type": "boolean", "description": "强制移除，默认 false"},
        },
        "required": ["name_or_id"],
    },
    "host_stats": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "主机名称或 ID"}},
        "required": ["name_or_id"],
    },
    "host_devices": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "主机名称或 ID"}},
        "required": ["name_or_id"],
    },

    # Storage Extended tools
    "storage_get": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "存储域名称或 ID"}},
        "required": ["name_or_id"],
    },
    "storage_create": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "存储域名称"},
            "storage_type": {"type": "string", "description": "存储类型（nfs/fc/iscsi等）"},
            "host": {"type": "string", "description": "主机名称"},
            "path": {"type": "string", "description": "存储路径"},
            "datacenter": {"type": "string", "description": "数据中心名称（可选）"},
            "description": {"type": "string", "description": "描述"},
            "domain_type": {"type": "string", "description": "域类型（data/iso/export），默认 data"},
        },
        "required": ["name", "storage_type", "host", "path"],
    },
    "storage_delete": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "存储域名称或 ID"},
            "force": {"type": "boolean", "description": "强制删除，默认 false"},
        },
        "required": ["name_or_id"],
    },
    "storage_detach": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "存储域名称或 ID"},
            "datacenter": {"type": "string", "description": "数据中心名称（可选）"},
        },
        "required": ["name_or_id"],
    },
    "storage_attach_to_dc": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "存储域名称或 ID"},
            "datacenter": {"type": "string", "description": "数据中心名称"},
        },
        "required": ["name_or_id", "datacenter"],
    },
    "storage_stats": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "存储域名称或 ID"}},
        "required": ["name_or_id"],
    },

    # Disk Extended tools
    "disk_get": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "磁盘名称或 ID"}},
        "required": ["name_or_id"],
    },
    "disk_delete": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "磁盘名称或 ID"},
            "force": {"type": "boolean", "description": "强制删除，默认 false"},
        },
        "required": ["name_or_id"],
    },
    "disk_resize": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "磁盘名称或 ID"},
            "new_size_gb": {"type": "number", "description": "新大小（GB）"},
        },
        "required": ["name_or_id", "new_size_gb"],
    },
    "disk_detach": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "磁盘名称或 ID"},
            "vm_name_or_id": {"type": "string", "description": "VM 名称或 ID"},
        },
        "required": ["name_or_id", "vm_name_or_id"],
    },
    "disk_move": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "磁盘名称或 ID"},
            "target_storage_domain": {"type": "string", "description": "目标存储域名称"},
        },
        "required": ["name_or_id", "target_storage_domain"],
    },
    "disk_stats": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "磁盘名称或 ID"}},
        "required": ["name_or_id"],
    },

    # Events tools
    "event_list": {
        "type": "object",
        "properties": {
            "search": {"type": "string", "description": "搜索条件（可选）"},
            "severity": {"type": "string", "description": "严重级别过滤（error/warning/info/alert）"},
            "page": {"type": "number", "description": "页码，默认 1"},
            "page_size": {"type": "number", "description": "每页数量，默认 50"},
        },
    },
    "event_get": {
        "type": "object",
        "properties": {"event_id": {"type": "string", "description": "事件 ID"}},
        "required": ["event_id"],
    },
    "event_search": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索查询"},
            "page": {"type": "number", "description": "页码，默认 1"},
            "page_size": {"type": "number", "description": "每页数量，默认 50"},
        },
        "required": ["query"],
    },
    "event_alerts": {
        "type": "object",
        "properties": {
            "page": {"type": "number", "description": "页码，默认 1"},
            "page_size": {"type": "number", "description": "每页数量，默认 50"},
        },
    },
    "event_errors": {
        "type": "object",
        "properties": {
            "page": {"type": "number", "description": "页码，默认 1"},
            "page_size": {"type": "number", "description": "每页数量，默认 50"},
        },
    },
    "event_warnings": {
        "type": "object",
        "properties": {
            "page": {"type": "number", "description": "页码，默认 1"},
            "page_size": {"type": "number", "description": "每页数量，默认 50"},
        },
    },
    "event_summary": {
        "type": "object",
        "properties": {"hours": {"type": "number", "description": "统计最近 N 小时，默认 24"}},
    },
    "event_acknowledge": {
        "type": "object",
        "properties": {"event_id": {"type": "string", "description": "事件 ID"}},
        "required": ["event_id"],
    },
    "event_clear_alerts": {"type": "object", "properties": {}},

    # Affinity Group tools
    "affinity_group_list": {
        "type": "object",
        "properties": {"cluster": {"type": "string", "description": "集群名称"}},
        "required": ["cluster"],
    },
    "affinity_group_get": {
        "type": "object",
        "properties": {
            "cluster": {"type": "string", "description": "集群名称"},
            "name_or_id": {"type": "string", "description": "亲和性组名称或 ID"},
        },
        "required": ["cluster", "name_or_id"],
    },
    "affinity_group_create": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "亲和性组名称"},
            "cluster": {"type": "string", "description": "集群名称"},
            "positive": {"type": "boolean", "description": "True=亲和性，False=反亲和性，默认 True"},
            "enforcing": {"type": "boolean", "description": "True=强制执行，False=软性规则，默认 False"},
            "vms": {"type": "array", "items": {"type": "string"}, "description": "VM 名称或 ID 列表"},
        },
        "required": ["name", "cluster"],
    },
    "affinity_group_update": {
        "type": "object",
        "properties": {
            "cluster": {"type": "string", "description": "集群名称"},
            "name_or_id": {"type": "string", "description": "亲和性组名称或 ID"},
            "new_name": {"type": "string", "description": "新名称（可选）"},
            "positive": {"type": "boolean", "description": "True=亲和性，False=反亲和性"},
            "enforcing": {"type": "boolean", "description": "True=强制执行，False=软性规则"},
        },
        "required": ["cluster", "name_or_id"],
    },
    "affinity_group_delete": {
        "type": "object",
        "properties": {
            "cluster": {"type": "string", "description": "集群名称"},
            "name_or_id": {"type": "string", "description": "亲和性组名称或 ID"},
        },
        "required": ["cluster", "name_or_id"],
    },
    "affinity_group_add_vm": {
        "type": "object",
        "properties": {
            "cluster": {"type": "string", "description": "集群名称"},
            "affinity_group": {"type": "string", "description": "亲和性组名称或 ID"},
            "vm": {"type": "string", "description": "VM 名称或 ID"},
        },
        "required": ["cluster", "affinity_group", "vm"],
    },
    "affinity_group_remove_vm": {
        "type": "object",
        "properties": {
            "cluster": {"type": "string", "description": "集群名称"},
            "affinity_group": {"type": "string", "description": "亲和性组名称或 ID"},
            "vm": {"type": "string", "description": "VM 名称或 ID"},
        },
        "required": ["cluster", "affinity_group", "vm"],
    },
}

DEFAULT_SCHEMA = {"type": "object", "properties": {}}

# ── Extension method mapping ─────────────────────────────────────────
# Methods that live on extension classes rather than OvirtMCP directly
EXTENSION_METHODS = {
    # NetworkMCP
    "list_vnics": "network_mcp",
    "create_network": "network_mcp",
    "update_network": "network_mcp",
    "delete_network": "network_mcp",
    # ClusterMCP
    "get_cluster": "cluster_mcp",
    "get_cluster_memory_usage": "cluster_mcp",
    # TemplateMCP
    "get_template": "template_mcp",
    "clone_template": "template_mcp",
    # DataCenterMCP
    "list_datacenters": "datacenter_mcp",
    "get_datacenter": "datacenter_mcp",
    "create_datacenter": "datacenter_mcp",
    "update_datacenter": "datacenter_mcp",
    "delete_datacenter": "datacenter_mcp",
    # HostExtendedMCP
    "get_host": "host_extended_mcp",
    "add_host": "host_extended_mcp",
    "remove_host": "host_extended_mcp",
    "get_host_stats": "host_extended_mcp",
    "get_host_devices": "host_extended_mcp",
    # StorageExtendedMCP
    "get_storage_domain": "storage_extended_mcp",
    "create_storage_domain": "storage_extended_mcp",
    "delete_storage_domain": "storage_extended_mcp",
    "detach_storage_domain": "storage_extended_mcp",
    "attach_storage_domain": "storage_extended_mcp",
    "get_storage_domain_stats": "storage_extended_mcp",
    # DiskExtendedMCP
    "get_disk": "disk_extended_mcp",
    "delete_disk": "disk_extended_mcp",
    "resize_disk": "disk_extended_mcp",
    "detach_disk": "disk_extended_mcp",
    "move_disk": "disk_extended_mcp",
    "get_disk_stats": "disk_extended_mcp",
    # EventsMCP
    "list_events": "events_mcp",
    "get_event": "events_mcp",
    "search_events": "events_mcp",
    "get_alerts": "events_mcp",
    "get_errors": "events_mcp",
    "get_warnings": "events_mcp",
    "get_events_summary": "events_mcp",
    "acknowledge_event": "events_mcp",
    "clear_alerts": "events_mcp",
    # AffinityMCP
    "list_affinity_groups": "affinity_mcp",
    "get_affinity_group": "affinity_mcp",
    "create_affinity_group": "affinity_mcp",
    "update_affinity_group": "affinity_mcp",
    "delete_affinity_group": "affinity_mcp",
    "add_vm_to_affinity_group": "affinity_mcp",
    "remove_vm_from_affinity_group": "affinity_mcp",
}


class OvirtMCPServer:
    """oVirt MCP Server — bridges MCP protocol to oVirt Engine SDK."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.server = Server("ovirt-mcp")
        self.connection = OvirtMCP(config)

        # Initialize extension modules
        self.network_mcp = NetworkMCP(self.connection)
        self.cluster_mcp = ClusterMCP(self.connection)
        self.template_mcp = TemplateMCP(self.connection)

        # Build tool registry
        self.tool_handlers: Dict[str, Callable[..., Any]] = {}
        self.tool_descriptions: Dict[str, str] = {}
        self._build_tool_registry()
        self._register_handlers()

        logger.info(f"Registered {len(self.tool_handlers)} MCP tools")

    def _resolve_handler(self, method_name: str) -> Optional[Callable[..., Any]]:
        """Resolve a method name to its handler function."""
        # Check extension classes first
        ext_attr = EXTENSION_METHODS.get(method_name)
        if ext_attr:
            instance = getattr(self, ext_attr, None)
            if instance and hasattr(instance, method_name):
                return getattr(instance, method_name)

        # Fall back to OvirtMCP
        if hasattr(self.connection, method_name):
            return getattr(self.connection, method_name)

        return None

    def _build_tool_registry(self) -> None:
        """Build unified tool registry from MCP_TOOLS definition."""
        for tool_name, tool_info in MCP_TOOLS.items():
            method_name = tool_info.get("method")
            description = tool_info.get("description", tool_name)

            handler = self._resolve_handler(method_name)
            if handler:
                self.tool_handlers[tool_name] = handler
                self.tool_descriptions[tool_name] = description
            else:
                logger.warning(f"Method not found for tool {tool_name}: {method_name}")

    def _register_handlers(self) -> None:
        """Register MCP protocol handlers."""

        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            tools = []
            for name, description in self.tool_descriptions.items():
                schema = TOOL_SCHEMAS.get(name, DEFAULT_SCHEMA)
                tools.append(
                    Tool(name=name, description=description, inputSchema=schema)
                )
            return tools

        @self.server.call_tool()
        async def call_tool(
            name: str, arguments: Dict[str, Any]
        ) -> List[TextContent]:
            try:
                # Validate input
                validated = validate_tool_args(name, arguments or {})

                handler = self.tool_handlers.get(name)
                if not handler:
                    return [
                        TextContent(type="text", text=f"Unknown tool: {name}")
                    ]

                # Execute handler in thread pool (SDK calls are sync)
                result = await asyncio.get_event_loop().run_in_executor(
                    None, functools.partial(handler, **validated)
                )
                return [TextContent(type="text", text=self._format_result(result))]

            except OvirtMCPError as e:
                logger.error(f"Tool error [{name}]: {e.code} - {e.message}")
                return [
                    TextContent(
                        type="text",
                        text=f"[{e.code}] {e.message}"
                        + (" (可重试)" if e.retryable else ""),
                    )
                ]
            except Exception as e:
                logger.error(f"Tool execution failed [{name}]", exc_info=True)
                return [
                    TextContent(
                        type="text",
                        text=f"操作失败: {type(e).__name__}: {e}",
                    )
                ]

    def initialize(self) -> None:
        """Connect to oVirt Engine."""
        logger.info("Connecting to oVirt Engine...")
        if not self.connection.connect():
            raise RuntimeError("Failed to connect to oVirt Engine")
        logger.info("Connected to oVirt Engine")

    async def start(self) -> None:
        """Start the MCP server using stdio transport."""
        async with stdio_server() as streams:
            await self.server.run(
                streams[0], streams[1], self.server.create_initialization_options()
            )

    @staticmethod
    def _format_result(data: Any) -> str:
        """Format tool result for MCP text response."""
        if not data:
            return "✅ 操作成功"
        if isinstance(data, str):
            return data
        if isinstance(data, list):
            if not data:
                return "没有找到匹配的结果"
            items = []
            for x in data[:20]:
                if isinstance(x, dict):
                    items.append(
                        "  - " + ", ".join(f"{k}: {v}" for k, v in list(x.items())[:6])
                    )
                else:
                    items.append(f"  - {x}")
            return "查询结果：\n" + "\n".join(items)
        if isinstance(data, dict):
            if data.get("error"):
                return f"❌ {data['error']}"
            if data.get("success"):
                return f"✅ {data.get('message', '操作成功')}"
            return "结果：\n" + "\n".join(
                f"  {k}: {v}" for k, v in list(data.items())[:15]
            )
        return str(data)


def main() -> None:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="oVirt MCP Server - MCP protocol server for oVirt/RHV"
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )
    args = parser.parse_args()

    # Setup logging
    config = load_config(args.config)
    logging.basicConfig(
        level=getattr(logging, config.mcp_log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    server = OvirtMCPServer(config)
    server.initialize()

    # Graceful shutdown
    def _shutdown(signum: int, frame: Any) -> None:
        logger.info(f"Received signal {signum}, shutting down...")
        if server.connection:
            try:
                server.connection.disconnect()
            except Exception:
                pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info("Starting oVirt MCP Server (stdio transport)...")
    asyncio.run(server.start())


if __name__ == "__main__":
    main()
