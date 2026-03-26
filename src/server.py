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
from .mcp_rbac import RbacMCP, MCP_TOOLS as RBAC_MCP_TOOLS
from .mcp_vm_extended import VmExtendedMCP, MCP_TOOLS as VM_EXTENDED_MCP_TOOLS
from .mcp_template_extended import TemplateExtendedMCP, MCP_TOOLS as TEMPLATE_EXTENDED_MCP_TOOLS
from .mcp_quota import QuotaMCP, MCP_TOOLS as QUOTA_MCP_TOOLS
from .mcp_system import SystemMCP, MCP_TOOLS as SYSTEM_MCP_TOOLS

# 合并所有 MCP_TOOLS
MCP_TOOLS = {
    **EXTENSIONS_MCP_TOOLS,
    **DATACENTER_MCP_TOOLS,
    **HOST_EXTENDED_MCP_TOOLS,
    **STORAGE_EXTENDED_MCP_TOOLS,
    **DISK_EXTENDED_MCP_TOOLS,
    **EVENTS_MCP_TOOLS,
    **AFFINITY_MCP_TOOLS,
    **RBAC_MCP_TOOLS,
    **VM_EXTENDED_MCP_TOOLS,
    **TEMPLATE_EXTENDED_MCP_TOOLS,
    **QUOTA_MCP_TOOLS,
    **SYSTEM_MCP_TOOLS,
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

    # RBAC - User tools
    "user_list": {
        "type": "object",
        "properties": {"search": {"type": "string", "description": "搜索条件（可选）"}},
    },
    "user_get": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "用户名称或 ID"}},
        "required": ["name_or_id"],
    },

    # RBAC - Group tools
    "group_list": {
        "type": "object",
        "properties": {"search": {"type": "string", "description": "搜索条件（可选）"}},
    },
    "group_get": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "组名称或 ID"}},
        "required": ["name_or_id"],
    },

    # RBAC - Role tools
    "role_list": {"type": "object", "properties": {}},
    "role_get": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "角色名称或 ID"}},
        "required": ["name_or_id"],
    },
    "role_create": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "角色名称"},
            "description": {"type": "string", "description": "描述（可选）"},
            "administrative": {"type": "boolean", "description": "是否为管理员角色，默认 false"},
            "permit_ids": {"type": "array", "items": {"type": "string"}, "description": "权限 ID 列表"},
        },
        "required": ["name"],
    },
    "role_delete": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "角色名称或 ID"}},
        "required": ["name_or_id"],
    },

    # RBAC - Permit tools
    "permit_list": {"type": "object", "properties": {}},

    # RBAC - Permission tools
    "permission_list": {
        "type": "object",
        "properties": {
            "resource_type": {"type": "string", "description": "资源类型（vm/host/cluster/datacenter/network/storagedomain/template）"},
            "resource_id": {"type": "string", "description": "资源 ID 或名称"},
        },
        "required": ["resource_type", "resource_id"],
    },
    "permission_assign": {
        "type": "object",
        "properties": {
            "resource_type": {"type": "string", "description": "资源类型（vm/host/cluster/datacenter/network/storagedomain/template）"},
            "resource_id": {"type": "string", "description": "资源 ID 或名称"},
            "user_or_group": {"type": "string", "description": "主体类型（user 或 group）"},
            "role_name": {"type": "string", "description": "角色名称或 ID"},
            "principal_name": {"type": "string", "description": "用户名或组名"},
        },
        "required": ["resource_type", "resource_id", "user_or_group", "role_name", "principal_name"],
    },
    "permission_revoke": {
        "type": "object",
        "properties": {
            "resource_type": {"type": "string", "description": "资源类型"},
            "resource_id": {"type": "string", "description": "资源 ID 或名称"},
            "permission_id": {"type": "string", "description": "权限 ID"},
        },
        "required": ["resource_type", "resource_id", "permission_id"],
    },

    # RBAC - Tag tools
    "tag_list": {"type": "object", "properties": {}},
    "tag_create": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "标签名称"},
            "description": {"type": "string", "description": "描述（可选）"},
            "parent_name": {"type": "string", "description": "父标签名称（可选）"},
        },
        "required": ["name"],
    },
    "tag_delete": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "标签名称或 ID"}},
        "required": ["name_or_id"],
    },
    "tag_assign": {
        "type": "object",
        "properties": {
            "resource_type": {"type": "string", "description": "资源类型（vm/host/cluster/datacenter/network/storagedomain/template）"},
            "resource_id": {"type": "string", "description": "资源 ID 或名称"},
            "tag_name": {"type": "string", "description": "标签名称或 ID"},
        },
        "required": ["resource_type", "resource_id", "tag_name"],
    },
    "tag_unassign": {
        "type": "object",
        "properties": {
            "resource_type": {"type": "string", "description": "资源类型"},
            "resource_id": {"type": "string", "description": "资源 ID 或名称"},
            "tag_name": {"type": "string", "description": "标签名称或 ID"},
        },
        "required": ["resource_type", "resource_id", "tag_name"],
    },
    "tag_list_resources": {
        "type": "object",
        "properties": {
            "resource_type": {"type": "string", "description": "资源类型"},
            "resource_id": {"type": "string", "description": "资源 ID 或名称"},
        },
        "required": ["resource_type", "resource_id"],
    },

    # ── VM Extended tools ─────────────────────────────────────────────────────
    "vm_migrate": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "VM 名称或 ID"},
            "target_host": {"type": "string", "description": "目标主机名称或 ID（可选）"},
        },
        "required": ["name_or_id"],
    },
    "vm_console": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "VM 名称或 ID"},
            "console_type": {"type": "string", "description": "控制台类型（spice/vnc），默认 spice"},
        },
        "required": ["name_or_id"],
    },
    "vm_cdrom_list": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "VM 名称或 ID"}},
        "required": ["name_or_id"],
    },
    "vm_cdrom_update": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "VM 名称或 ID"},
            "cdrom_id": {"type": "string", "description": "CDROM ID"},
            "iso_file": {"type": "string", "description": "ISO 文件路径"},
            "eject": {"type": "boolean", "description": "是否弹出光盘"},
        },
        "required": ["name_or_id", "cdrom_id"],
    },
    "vm_hostdevice_list": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "VM 名称或 ID"}},
        "required": ["name_or_id"],
    },
    "vm_hostdevice_attach": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "VM 名称或 ID"},
            "device_name": {"type": "string", "description": "设备名称"},
        },
        "required": ["name_or_id", "device_name"],
    },
    "vm_hostdevice_detach": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "VM 名称或 ID"},
            "device_name": {"type": "string", "description": "设备名称"},
        },
        "required": ["name_or_id", "device_name"],
    },
    "vm_mediated_device_list": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "VM 名称或 ID"}},
        "required": ["name_or_id"],
    },
    "vm_numa_list": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "VM 名称或 ID"}},
        "required": ["name_or_id"],
    },
    "vm_watchdog_list": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "VM 名称或 ID"}},
        "required": ["name_or_id"],
    },
    "vm_watchdog_update": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "VM 名称或 ID"},
            "watchdog_id": {"type": "string", "description": "Watchdog ID"},
            "action": {"type": "string", "description": "触发动作（none/reset/poweroff/shutdown/dump）"},
        },
        "required": ["name_or_id", "watchdog_id"],
    },
    "vm_pin_to_host": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "VM 名称或 ID"},
            "host": {"type": "string", "description": "主机名称或 ID"},
            "pin_policy": {"type": "string", "description": "固定策略（user/resizable/migratable）"},
        },
        "required": ["name_or_id", "host"],
    },
    "vm_session_list": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "VM 名称或 ID"}},
        "required": ["name_or_id"],
    },
    "vm_pool_list": {
        "type": "object",
        "properties": {"cluster": {"type": "string", "description": "集群名称（可选）"}},
    },
    "vm_pool_get": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "VM 池名称或 ID"}},
        "required": ["name_or_id"],
    },
    "vm_pool_create": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "池名称"},
            "template": {"type": "string", "description": "模板名称"},
            "cluster": {"type": "string", "description": "集群名称"},
            "size": {"type": "number", "description": "池大小，默认 5"},
            "description": {"type": "string", "description": "描述"},
            "max_user_vms": {"type": "number", "description": "每用户最大 VM 数，默认 1"},
            "prestarted_vms": {"type": "number", "description": "预启动 VM 数，默认 0"},
            "stateful": {"type": "boolean", "description": "是否有状态，默认 false"},
        },
        "required": ["name", "template", "cluster"],
    },
    "vm_pool_delete": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "VM 池名称或 ID"},
            "force": {"type": "boolean", "description": "强制删除"},
        },
        "required": ["name_or_id"],
    },
    "vm_pool_update": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "VM 池名称或 ID"},
            "new_name": {"type": "string", "description": "新名称"},
            "size": {"type": "number", "description": "新大小"},
            "description": {"type": "string", "description": "新描述"},
            "prestarted_vms": {"type": "number", "description": "预启动 VM 数"},
        },
        "required": ["name_or_id"],
    },
    "vm_checkpoint_list": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "VM 名称或 ID"}},
        "required": ["name_or_id"],
    },
    "vm_checkpoint_create": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "VM 名称或 ID"},
            "description": {"type": "string", "description": "检查点描述"},
        },
        "required": ["name_or_id"],
    },
    "vm_checkpoint_restore": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "VM 名称或 ID"},
            "checkpoint_id": {"type": "string", "description": "检查点 ID"},
        },
        "required": ["name_or_id", "checkpoint_id"],
    },
    "vm_checkpoint_delete": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "VM 名称或 ID"},
            "checkpoint_id": {"type": "string", "description": "检查点 ID"},
        },
        "required": ["name_or_id", "checkpoint_id"],
    },

    # ── Template Extended tools ───────────────────────────────────────────────
    "template_get": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "模板名称或 ID"}},
        "required": ["name_or_id"],
    },
    "template_create": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "模板名称"},
            "vm": {"type": "string", "description": "源虚拟机名称或 ID"},
            "description": {"type": "string", "description": "描述"},
            "cluster": {"type": "string", "description": "目标集群（可选）"},
        },
        "required": ["name", "vm"],
    },
    "template_delete": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "模板名称或 ID"},
            "force": {"type": "boolean", "description": "强制删除"},
        },
        "required": ["name_or_id"],
    },
    "template_update": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "模板名称或 ID"},
            "new_name": {"type": "string", "description": "新名称"},
            "description": {"type": "string", "description": "新描述"},
            "memory_mb": {"type": "number", "description": "内存（MB）"},
            "cpu_cores": {"type": "number", "description": "CPU 核数"},
        },
        "required": ["name_or_id"],
    },
    "template_disk_list": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "模板名称或 ID"}},
        "required": ["name_or_id"],
    },
    "template_nic_list": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "模板名称或 ID"}},
        "required": ["name_or_id"],
    },
    "instance_type_list": {"type": "object", "properties": {}},
    "instance_type_get": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "实例类型名称或 ID"}},
        "required": ["name_or_id"],
    },

    # ── Quota tools ───────────────────────────────────────────────────────────
    "quota_list": {
        "type": "object",
        "properties": {"datacenter": {"type": "string", "description": "数据中心名称或 ID"}},
        "required": ["datacenter"],
    },
    "quota_get": {
        "type": "object",
        "properties": {
            "datacenter": {"type": "string", "description": "数据中心名称或 ID"},
            "name_or_id": {"type": "string", "description": "配额名称或 ID"},
        },
        "required": ["datacenter", "name_or_id"],
    },
    "quota_create": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "配额名称"},
            "datacenter": {"type": "string", "description": "数据中心名称"},
            "description": {"type": "string", "description": "描述"},
            "cluster_hard_limit_pct": {"type": "number", "description": "集群硬限制百分比"},
            "storage_hard_limit_pct": {"type": "number", "description": "存储硬限制百分比"},
        },
        "required": ["name", "datacenter"],
    },
    "quota_update": {
        "type": "object",
        "properties": {
            "datacenter": {"type": "string", "description": "数据中心名称或 ID"},
            "name_or_id": {"type": "string", "description": "配额名称或 ID"},
            "new_name": {"type": "string", "description": "新名称"},
            "description": {"type": "string", "description": "新描述"},
            "cluster_hard_limit_pct": {"type": "number", "description": "集群硬限制百分比"},
            "storage_hard_limit_pct": {"type": "number", "description": "存储硬限制百分比"},
        },
        "required": ["datacenter", "name_or_id"],
    },
    "quota_delete": {
        "type": "object",
        "properties": {
            "datacenter": {"type": "string", "description": "数据中心名称或 ID"},
            "name_or_id": {"type": "string", "description": "配额名称或 ID"},
        },
        "required": ["datacenter", "name_or_id"],
    },
    "quota_cluster_limit_list": {
        "type": "object",
        "properties": {
            "datacenter": {"type": "string", "description": "数据中心名称或 ID"},
            "name_or_id": {"type": "string", "description": "配额名称或 ID"},
        },
        "required": ["datacenter", "name_or_id"],
    },
    "quota_storage_limit_list": {
        "type": "object",
        "properties": {
            "datacenter": {"type": "string", "description": "数据中心名称或 ID"},
            "name_or_id": {"type": "string", "description": "配额名称或 ID"},
        },
        "required": ["datacenter", "name_or_id"],
    },

    # ── System tools ──────────────────────────────────────────────────────────
    "system_get": {"type": "object", "properties": {}},
    "system_option_list": {
        "type": "object",
        "properties": {"category": {"type": "string", "description": "选项分类（可选）"}},
    },
    "job_list": {
        "type": "object",
        "properties": {
            "page": {"type": "number", "description": "页码"},
            "page_size": {"type": "number", "description": "每页数量"},
        },
    },
    "job_get": {
        "type": "object",
        "properties": {"job_id": {"type": "string", "description": "任务 ID"}},
        "required": ["job_id"],
    },
    "job_cancel": {
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "description": "任务 ID"},
            "force": {"type": "boolean", "description": "强制取消"},
        },
        "required": ["job_id"],
    },
    "system_statistics": {"type": "object", "properties": {}},

    # ── Network Extended tools ────────────────────────────────────────────────
    "network_get": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "网络名称或 ID"}},
        "required": ["name_or_id"],
    },
    "vnic_profile_list": {
        "type": "object",
        "properties": {"network": {"type": "string", "description": "网络名称（可选）"}},
    },
    "vnic_profile_get": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "Profile 名称或 ID"}},
        "required": ["name_or_id"],
    },
    "vnic_profile_create": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Profile 名称"},
            "network": {"type": "string", "description": "网络名称"},
            "description": {"type": "string", "description": "描述"},
            "port_mirroring": {"type": "boolean", "description": "是否启用端口镜像"},
        },
        "required": ["name", "network"],
    },
    "vnic_profile_update": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "Profile 名称或 ID"},
            "new_name": {"type": "string", "description": "新名称"},
            "description": {"type": "string", "description": "新描述"},
            "port_mirroring": {"type": "boolean", "description": "端口镜像设置"},
        },
        "required": ["name_or_id"],
    },
    "vnic_profile_delete": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "Profile 名称或 ID"}},
        "required": ["name_or_id"],
    },
    "network_filter_list": {"type": "object", "properties": {}},
    "mac_pool_list": {"type": "object", "properties": {}},
    "qos_list": {
        "type": "object",
        "properties": {"datacenter": {"type": "string", "description": "数据中心名称（可选）"}},
    },

    # ── Cluster Extended tools ────────────────────────────────────────────────
    "cluster_create": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "集群名称"},
            "datacenter": {"type": "string", "description": "数据中心名称"},
            "cpu_type": {"type": "string", "description": "CPU 类型"},
            "description": {"type": "string", "description": "描述"},
            "gluster_service": {"type": "boolean", "description": "是否启用 Gluster 服务"},
            "threads_per_core": {"type": "number", "description": "每核心线程数"},
        },
        "required": ["name", "datacenter", "cpu_type"],
    },
    "cluster_update": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "集群名称或 ID"},
            "new_name": {"type": "string", "description": "新名称"},
            "description": {"type": "string", "description": "新描述"},
            "threads_per_core": {"type": "number", "description": "每核心线程数"},
        },
        "required": ["name_or_id"],
    },
    "cluster_delete": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "集群名称或 ID"}},
        "required": ["name_or_id"],
    },
    "cpu_profile_list": {
        "type": "object",
        "properties": {"cluster": {"type": "string", "description": "集群名称或 ID"}},
        "required": ["cluster"],
    },
    "cpu_profile_get": {
        "type": "object",
        "properties": {
            "cluster": {"type": "string", "description": "集群名称或 ID"},
            "name_or_id": {"type": "string", "description": "Profile 名称或 ID"},
        },
        "required": ["cluster", "name_or_id"],
    },

    # ── Host Extended tools ───────────────────────────────────────────────────
    "host_nic_list": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "主机名称或 ID"}},
        "required": ["name_or_id"],
    },
    "host_nic_update": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "主机名称或 ID"},
            "nic_name": {"type": "string", "description": "网卡名称"},
            "custom_properties": {"type": "object", "description": "自定义属性"},
        },
        "required": ["name_or_id", "nic_name"],
    },
    "host_numa_get": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "主机名称或 ID"}},
        "required": ["name_or_id"],
    },
    "host_hook_list": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "主机名称或 ID"}},
        "required": ["name_or_id"],
    },
    "host_fence": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "主机名称或 ID"},
            "action": {"type": "string", "description": "操作类型（restart/start/stop/status）"},
        },
        "required": ["name_or_id"],
    },
    "host_network_update": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "主机名称或 ID"},
            "network": {"type": "string", "description": "网络名称"},
            "nic": {"type": "string", "description": "网卡名称（可选）"},
            "vlan_id": {"type": "number", "description": "VLAN ID（可选）"},
            "bond": {"type": "string", "description": "绑定接口名称（可选）"},
        },
        "required": ["name_or_id", "network"],
    },
    "host_device_update": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "主机名称或 ID"},
            "device_name": {"type": "string", "description": "设备名称"},
            "enabled": {"type": "boolean", "description": "是否启用"},
        },
        "required": ["name_or_id", "device_name"],
    },
    "host_storage_list": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "主机名称或 ID"}},
        "required": ["name_or_id"],
    },
    "host_install": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "主机名称或 ID"},
            "root_password": {"type": "string", "description": "root 密码"},
            "ssh_key": {"type": "string", "description": "SSH 公钥"},
            "override_iptables": {"type": "boolean", "description": "覆盖 iptables 规则"},
        },
        "required": ["name_or_id"],
    },
    "host_iscsi_discover": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "主机名称或 ID"},
            "address": {"type": "string", "description": "iSCSI 目标地址"},
            "port": {"type": "number", "description": "端口号，默认 3260"},
            "username": {"type": "string", "description": "CHAP 用户名（可选）"},
            "password": {"type": "string", "description": "CHAP 密码（可选）"},
        },
        "required": ["name_or_id", "address"],
    },
    "host_iscsi_login": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "主机名称或 ID"},
            "address": {"type": "string", "description": "iSCSI 目标地址"},
            "target": {"type": "string", "description": "目标名称"},
            "port": {"type": "number", "description": "端口号，默认 3260"},
            "username": {"type": "string", "description": "CHAP 用户名（可选）"},
            "password": {"type": "string", "description": "CHAP 密码（可选）"},
        },
        "required": ["name_or_id", "address", "target"],
    },

    # ── Storage Extended tools ────────────────────────────────────────────────
    "storage_refresh": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "存储域名称或 ID"}},
        "required": ["name_or_id"],
    },
    "storage_update": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "存储域名称或 ID"},
            "new_name": {"type": "string", "description": "新名称"},
            "description": {"type": "string", "description": "新描述"},
            "warning_low_space": {"type": "number", "description": "低空间警告阈值（GB）"},
            "critical_low_space": {"type": "number", "description": "临界空间阈值（GB）"},
        },
        "required": ["name_or_id"],
    },
    "storage_files": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "存储域名称或 ID"}},
        "required": ["name_or_id"],
    },
    "storage_connections_list": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "存储域名称或 ID（可选）"}},
    },
    "storage_available_disks": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "存储域名称或 ID"}},
        "required": ["name_or_id"],
    },
    "storage_export_vms": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "导出域名称或 ID"}},
        "required": ["name_or_id"],
    },
    "storage_import_vm": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "导出域名称或 ID"},
            "vm_name": {"type": "string", "description": "要导入的 VM 名称"},
            "cluster": {"type": "string", "description": "目标集群"},
            "storage_domain": {"type": "string", "description": "目标存储域（可选）"},
            "clone": {"type": "boolean", "description": "是否克隆"},
        },
        "required": ["name_or_id", "vm_name", "cluster"],
    },
    "disk_snapshot_list": {
        "type": "object",
        "properties": {"disk_name_or_id": {"type": "string", "description": "磁盘名称或 ID"}},
        "required": ["disk_name_or_id"],
    },
    "iscsi_bond_list": {"type": "object", "properties": {}},

    # ── Disk Extended tools ───────────────────────────────────────────────────
    "disk_update": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "磁盘名称或 ID"},
            "new_name": {"type": "string", "description": "新名称"},
            "description": {"type": "string", "description": "新描述"},
            "shareable": {"type": "boolean", "description": "是否可共享"},
            "wipe_after_delete": {"type": "boolean", "description": "删除后擦除"},
        },
        "required": ["name_or_id"],
    },
    "disk_sparsify": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "磁盘名称或 ID"}},
        "required": ["name_or_id"],
    },
    "disk_export": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "磁盘名称或 ID"},
            "export_domain": {"type": "string", "description": "导出域名称"},
        },
        "required": ["name_or_id", "export_domain"],
    },

    # ── Events Extended tools ─────────────────────────────────────────────────
    "event_subscription_list": {
        "type": "object",
        "properties": {"user": {"type": "string", "description": "用户名称（可选）"}},
    },
    "bookmark_list": {"type": "object", "properties": {}},

    # ── Affinity Extended tools ───────────────────────────────────────────────
    "affinity_label_list": {"type": "object", "properties": {}},
    "affinity_label_get": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "标签名称或 ID"}},
        "required": ["name_or_id"],
    },
    "affinity_label_create": {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "标签名称"}},
        "required": ["name"],
    },
    "affinity_label_delete": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "标签名称或 ID"}},
        "required": ["name_or_id"],
    },
    "affinity_label_assign": {
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": "标签名称或 ID"},
            "resource_type": {"type": "string", "description": "资源类型（vm 或 host）"},
            "resource": {"type": "string", "description": "资源名称或 ID"},
        },
        "required": ["label", "resource_type", "resource"],
    },
    "affinity_label_unassign": {
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": "标签名称或 ID"},
            "resource_type": {"type": "string", "description": "资源类型（vm 或 host）"},
            "resource": {"type": "string", "description": "资源名称或 ID"},
        },
        "required": ["label", "resource_type", "resource"],
    },

    # ── RBAC Extended tools ───────────────────────────────────────────────────
    "user_create": {
        "type": "object",
        "properties": {
            "username": {"type": "string", "description": "用户名"},
            "email": {"type": "string", "description": "邮箱"},
            "first_name": {"type": "string", "description": "名"},
            "last_name": {"type": "string", "description": "姓"},
        },
        "required": ["username"],
    },
    "user_update": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "用户名称或 ID"},
            "email": {"type": "string", "description": "新邮箱"},
            "first_name": {"type": "string", "description": "新名"},
            "last_name": {"type": "string", "description": "新姓"},
        },
        "required": ["name_or_id"],
    },
    "user_delete": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "用户名称或 ID"}},
        "required": ["name_or_id"],
    },
    "user_group_list": {
        "type": "object",
        "properties": {"name_or_id": {"type": "string", "description": "用户名称或 ID"}},
        "required": ["name_or_id"],
    },
    "role_update": {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string", "description": "角色名称或 ID"},
            "new_name": {"type": "string", "description": "新名称"},
            "description": {"type": "string", "description": "新描述"},
        },
        "required": ["name_or_id"],
    },
    "filter_list": {"type": "object", "properties": {}},
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
    # RbacMCP
    "list_users": "rbac_mcp",
    "get_user": "rbac_mcp",
    "create_user": "rbac_mcp",
    "update_user": "rbac_mcp",
    "delete_user": "rbac_mcp",
    "list_user_groups": "rbac_mcp",
    "list_groups": "rbac_mcp",
    "get_group": "rbac_mcp",
    "list_roles": "rbac_mcp",
    "get_role": "rbac_mcp",
    "create_role": "rbac_mcp",
    "update_role": "rbac_mcp",
    "delete_role": "rbac_mcp",
    "list_permits": "rbac_mcp",
    "list_permissions": "rbac_mcp",
    "assign_permission": "rbac_mcp",
    "revoke_permission": "rbac_mcp",
    "list_tags": "rbac_mcp",
    "create_tag": "rbac_mcp",
    "delete_tag": "rbac_mcp",
    "assign_tag": "rbac_mcp",
    "unassign_tag": "rbac_mcp",
    "list_resource_tags": "rbac_mcp",
    "list_filters": "rbac_mcp",

    # VmExtendedMCP
    "migrate_vm": "vm_extended_mcp",
    "get_vm_console": "vm_extended_mcp",
    "list_vm_cdroms": "vm_extended_mcp",
    "update_vm_cdrom": "vm_extended_mcp",
    "list_vm_host_devices": "vm_extended_mcp",
    "attach_vm_host_device": "vm_extended_mcp",
    "detach_vm_host_device": "vm_extended_mcp",
    "list_vm_mediated_devices": "vm_extended_mcp",
    "list_vm_numa_nodes": "vm_extended_mcp",
    "list_vm_watchdogs": "vm_extended_mcp",
    "update_vm_watchdog": "vm_extended_mcp",
    "pin_vm_to_host": "vm_extended_mcp",
    "list_vm_sessions": "vm_extended_mcp",
    "list_vm_pools": "vm_extended_mcp",
    "get_vm_pool": "vm_extended_mcp",
    "create_vm_pool": "vm_extended_mcp",
    "delete_vm_pool": "vm_extended_mcp",
    "update_vm_pool": "vm_extended_mcp",
    "list_vm_checkpoints": "vm_extended_mcp",
    "create_vm_checkpoint": "vm_extended_mcp",
    "restore_vm_checkpoint": "vm_extended_mcp",
    "delete_vm_checkpoint": "vm_extended_mcp",

    # TemplateExtendedMCP
    "get_template_extended": "template_extended_mcp",
    "create_template": "template_extended_mcp",
    "delete_template": "template_extended_mcp",
    "update_template": "template_extended_mcp",
    "list_template_disks": "template_extended_mcp",
    "list_template_nics": "template_extended_mcp",
    "list_instance_types": "template_extended_mcp",
    "get_instance_type": "template_extended_mcp",

    # QuotaMCP
    "list_quotas": "quota_mcp",
    "get_quota": "quota_mcp",
    "create_quota": "quota_mcp",
    "update_quota": "quota_mcp",
    "delete_quota": "quota_mcp",
    "list_quota_cluster_limits": "quota_mcp",
    "list_quota_storage_limits": "quota_mcp",

    # SystemMCP
    "get_system_info": "system_mcp",
    "list_system_options": "system_mcp",
    "list_jobs": "system_mcp",
    "get_job": "system_mcp",
    "cancel_job": "system_mcp",
    "get_system_statistics": "system_mcp",

    # NetworkMCP extended
    "get_network": "network_mcp",
    "list_vnic_profiles": "network_mcp",
    "get_vnic_profile": "network_mcp",
    "create_vnic_profile": "network_mcp",
    "update_vnic_profile": "network_mcp",
    "delete_vnic_profile": "network_mcp",
    "list_network_filters": "network_mcp",
    "list_mac_pools": "network_mcp",
    "list_qos": "network_mcp",

    # ClusterMCP extended
    "create_cluster": "cluster_mcp",
    "update_cluster": "cluster_mcp",
    "delete_cluster": "cluster_mcp",
    "list_cpu_profiles": "cluster_mcp",
    "get_cpu_profile": "cluster_mcp",

    # HostExtendedMCP extended
    "list_host_nics": "host_extended_mcp",
    "update_host_nic": "host_extended_mcp",
    "get_host_numa": "host_extended_mcp",
    "list_host_hooks": "host_extended_mcp",
    "fence_host": "host_extended_mcp",
    "update_host_network": "host_extended_mcp",
    "update_host_device": "host_extended_mcp",
    "list_host_storage": "host_extended_mcp",
    "install_host": "host_extended_mcp",
    "iscsi_discover": "host_extended_mcp",
    "iscsi_login": "host_extended_mcp",

    # StorageExtendedMCP extended
    "refresh_storage_domain": "storage_extended_mcp",
    "update_storage_domain": "storage_extended_mcp",
    "list_storage_files": "storage_extended_mcp",
    "list_storage_connections": "storage_extended_mcp",
    "list_available_disks": "storage_extended_mcp",
    "list_export_vms": "storage_extended_mcp",
    "import_vm_from_export": "storage_extended_mcp",
    "list_disk_snapshots": "storage_extended_mcp",
    "list_iscsi_bonds": "storage_extended_mcp",

    # DiskExtendedMCP extended
    "update_disk": "disk_extended_mcp",
    "sparsify_disk": "disk_extended_mcp",
    "export_disk": "disk_extended_mcp",

    # EventsMCP extended
    "list_event_subscriptions": "events_mcp",
    "list_bookmarks": "events_mcp",

    # AffinityMCP extended
    "list_affinity_labels": "affinity_mcp",
    "get_affinity_label": "affinity_mcp",
    "create_affinity_label": "affinity_mcp",
    "delete_affinity_label": "affinity_mcp",
    "assign_affinity_label": "affinity_mcp",
    "unassign_affinity_label": "affinity_mcp",
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
        self.rbac_mcp = RbacMCP(self.connection)
        self.datacenter_mcp = DataCenterMCP(self.connection)
        self.host_extended_mcp = HostExtendedMCP(self.connection)
        self.storage_extended_mcp = StorageExtendedMCP(self.connection)
        self.disk_extended_mcp = DiskExtendedMCP(self.connection)
        self.events_mcp = EventsMCP(self.connection)
        self.affinity_mcp = AffinityMCP(self.connection)
        self.vm_extended_mcp = VmExtendedMCP(self.connection)
        self.template_extended_mcp = TemplateExtendedMCP(self.connection)
        self.quota_mcp = QuotaMCP(self.connection)
        self.system_mcp = SystemMCP(self.connection)

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
