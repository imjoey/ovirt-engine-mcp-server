# oVirt MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io/) (MCP) server for [oVirt](https://www.ovirt.org/) / RHV virtualization management. Provides 150+ tools for managing VMs, hosts, clusters, networks, storage, templates, snapshots, disks, events, affinity groups, RBAC, quotas, checkpoints, migrations, VM pools, and more — enabling AI assistants like Claude to interact with your virtualization infrastructure.

## Features

- **150+ MCP Tools** — Full lifecycle management for VMs, hosts, clusters, networks, storage, templates, snapshots, disks, events, affinity groups, RBAC, quotas, checkpoints, migrations, VM pools, and more
- **Real SDK Integration** — Built on [ovirtsdk4](https://github.com/oVirt/ovirt-engine-sdk-python), the official oVirt Python SDK
- **Stdio Transport** — Works out of the box with Claude Desktop, OpenClaw, and any MCP-compatible client
- **Structured Errors** — Clear error codes and retry guidance
- **Input Validation** — Type-safe parameter validation for all tools

## Quick Start

### 1. Install

```bash
pip install ovirt-mcp-server
```

Or from source:

```bash
git clone https://github.com/imjoey/ovirt-mcp-server.git
cd ovirt-mcp-server
pip install -e .
```

### 2. Configure

Set environment variables (recommended):

```bash
export OVIRT_ENGINE_URL="https://ovirt-engine.example.com"
export OVIRT_ENGINE_USER="admin@internal"
export OVIRT_ENGINE_PASSWORD="your-password"
```

Or create a `config.yaml`:

```yaml
OVIRT_ENGINE_URL: https://ovirt-engine.example.com
OVIRT_ENGINE_USER: admin@internal
# OVIRT_ENGINE_PASSWORD should be set via environment variable
```

### 3. Run

```bash
ovirt-mcp
```

## Claude Desktop Integration

Add to your Claude Desktop config file (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "ovirt": {
      "command": "ovirt-mcp",
      "env": {
        "OVIRT_ENGINE_URL": "https://ovirt-engine.example.com",
        "OVIRT_ENGINE_USER": "admin@internal",
        "OVIRT_ENGINE_PASSWORD": "your-password"
      }
    }
  }
}
```

## Docker

```bash
docker build -t ovirt-mcp-server .
docker run -e OVIRT_ENGINE_URL=https://ovirt-engine.example.com \
           -e OVIRT_ENGINE_USER=admin@internal \
           -e OVIRT_ENGINE_PASSWORD=your-password \
           ovirt-mcp-server
```

## Available Tools

### Virtual Machines (Core)

| Tool | Description |
|------|-------------|
| `vm_list` | List virtual machines (filter by cluster/status) |
| `vm_get` | Get VM details |
| `vm_create` | Create a new VM |
| `vm_start` | Start a VM |
| `vm_stop` | Stop a VM |
| `vm_restart` | Restart a VM |
| `vm_delete` | Delete a VM |
| `vm_update_resources` | Update VM CPU/memory |
| `vm_stats` | Get VM statistics |

### VM Extended Operations

| Tool | Description |
|------|-------------|
| `vm_migrate` | Migrate VM to another host |
| `vm_console` | Get VM console access info |
| `vm_cdrom_list` | List VM CDROM devices |
| `vm_cdrom_update` | Mount/eject ISO on VM |
| `vm_hostdevice_list` | List VM host devices |
| `vm_hostdevice_attach` | Attach host device to VM |
| `vm_hostdevice_detach` | Detach host device from VM |
| `vm_numa_list` | List VM NUMA nodes |
| `vm_watchdog_list` | List VM watchdog devices |
| `vm_watchdog_update` | Update VM watchdog config |
| `vm_pin_to_host` | Pin VM to specific host |
| `vm_session_list` | List active VM sessions |

### VM Pools

| Tool | Description |
|------|-------------|
| `vm_pool_list` | List VM pools |
| `vm_pool_get` | Get VM pool details |
| `vm_pool_create` | Create VM pool |
| `vm_pool_update` | Update VM pool |
| `vm_pool_delete` | Delete VM pool |

### VM Checkpoints

| Tool | Description |
|------|-------------|
| `vm_checkpoint_list` | List VM checkpoints |
| `vm_checkpoint_create` | Create VM checkpoint |
| `vm_checkpoint_restore` | Restore VM to checkpoint |
| `vm_checkpoint_delete` | Delete VM checkpoint |

### Snapshots

| Tool | Description |
|------|-------------|
| `snapshot_list` | List VM snapshots |
| `snapshot_create` | Create a snapshot |
| `snapshot_restore` | Restore a snapshot |
| `snapshot_delete` | Delete a snapshot |

### Disks (Core)

| Tool | Description |
|------|-------------|
| `disk_list` | List disks |
| `disk_create` | Create a disk |
| `disk_attach` | Attach disk into VM |

### Disks (Extended)

| Tool | Description |
|------|-------------|
| `disk_get` | Get disk details |
| `disk_delete` | Delete disk |
| `disk_resize` | Resize disk |
| `disk_detach` | Detach disk from VM |
| `disk_move` | Move disk into another storage domain |
| `disk_stats` | Get disk statistics |
| `disk_update` | Update disk configuration |
| `disk_sparsify` | Sparsify disk (eliminate blank blocks) |
| `disk_export` | Export disk into export domain |

### Networks (Core)

| Tool | Description |
|------|-------------|
| `network_list` | List networks |
| `network_get` | Get network details |
| `network_create` | Create network |
| `network_update` | Update network |
| `network_delete` | Delete network |
| `nic_list` | List VM NICs |
| `nic_add` | Add NIC into VM |
| `nic_remove` | Remove NIC from VM |

### VNIC Profiles

| Tool | Description |
|------|-------------|
| `vnic_profile_list` | List VNIC profiles |
| `vnic_profile_get` | Get VNIC profile details |
| `vnic_profile_create` | Create VNIC profile |
| `vnic_profile_update` | Update VNIC profile |
| `vnic_profile_delete` | Delete VNIC profile |

### Network Filters & QoS

| Tool | Description |
|------|-------------|
| `network_filter_list` | List network filters |
| `mac_pool_list` | List MAC address pools |
| `qos_list` | List QoS configurations |

### Hosts (Core)

| Tool | Description |
|------|-------------|
| `host_list` | List hosts |
| `host_activate` | Activate a host |
| `host_deactivate` | Deactivate a host (maintenance mode) |

### Hosts (Extended)

| Tool | Description |
|------|-------------|
| `host_get` | Get host details |
| `host_add` | Add new host |
| `host_remove` | Remove host |
| `host_stats` | Get host statistics |
| `host_devices` | Get host device list |
| `host_nic_list` | List host NICs |
| `host_nic_update` | Update host NIC config |
| `host_numa_get` | Get host NUMA topology |
| `host_hook_list` | List host hooks |
| `host_fence` | Execute fence operation (restart/start/stop/status) |
| `host_network_update` | Update host network config |
| `host_device_update` | Update host device config |
| `host_storage_list` | List host storage |
| `host_install` | Install/reinstall host |
| `host_iscsi_discover` | Discover iSCSI targets |
| `host_iscsi_login` | Login into iSCSI target |

### Clusters (Core)

| Tool | Description |
|------|-------------|
| `cluster_list` | List clusters |
| `cluster_get` | Get cluster details |
| `cluster_create` | Create cluster |
| `cluster_update` | Update cluster |
| `cluster_delete` | Delete cluster |
| `cluster_hosts` | List hosts in a cluster |
| `cluster_vms` | List VMs in a cluster |
| `cluster_cpu_load` | Get cluster CPU load |
| `cluster_memory_usage` | Get cluster memory usage |

### CPU Profiles

| Tool | Description |
|------|-------------|
| `cpu_profile_list` | List CPU profiles |
| `cpu_profile_get` | Get CPU profile details |

### Data Centers

| Tool | Description |
|------|-------------|
| `datacenter_list` | List data centers |
| `datacenter_get` | Get data center details |
| `datacenter_create` | Create data center |
| `datacenter_update` | Update data center |
| `datacenter_delete` | Delete data center |

### Storage (Core)

| Tool | Description |
|------|-------------|
| `storage_list` | List storage domains |
| `storage_get` | Get storage domain details |
| `storage_create` | Create storage domain |
| `storage_delete` | Delete storage domain |
| `storage_detach` | Detach storage domain from data center |
| `storage_attach_to_dc` | Attach storage domain into data center |
| `storage_stats` | Get storage domain statistics |
| `storage_attach` | Attach storage domain |

### Storage (Extended)

| Tool | Description |
|------|-------------|
| `storage_refresh` | Refresh storage domain |
| `storage_update` | Update storage domain config |
| `storage_files` | List storage domain files |
| `storage_connections_list` | List storage connections |
| `storage_available_disks` | List available disks on storage domain |
| `storage_export_vms` | List VMs on export domain |
| `storage_import_vm` | Import VM from export domain |
| `disk_snapshot_list` | List disk snapshots |
| `iscsi_bond_list` | List iSCSI bonds |

### Templates (Core)

| Tool | Description |
|------|-------------|
| `template_list` | List templates |
| `template_vm_create` | Create VM from template |

### Templates (Extended)

| Tool | Description |
|------|-------------|
| `template_get` | Get template details |
| `template_create` | Create template from VM |
| `template_delete` | Delete template |
| `template_update` | Update template |
| `template_disk_list` | List template disks |
| `template_nic_list` | List template NICs |

### Instance Types

| Tool | Description |
|------|-------------|
| `instance_type_list` | List instance types |
| `instance_type_get` | Get instance type details |

### Affinity Groups

| Tool | Description |
|------|-------------|
| `affinity_group_list` | List affinity groups |
| `affinity_group_get` | Get affinity group details |
| `affinity_group_create` | Create affinity group |
| `affinity_group_update` | Update affinity group |
| `affinity_group_delete` | Delete affinity group |
| `affinity_group_add_vm` | Add VM into affinity group |
| `affinity_group_remove_vm` | Remove VM from affinity group |

### Affinity Labels

| Tool | Description |
|------|-------------|
| `affinity_label_list` | List affinity labels |
| `affinity_label_get` | Get affinity label details |
| `affinity_label_create` | Create affinity label |
| `affinity_label_delete` | Delete affinity label |
| `affinity_label_assign` | Assign affinity label into VM/host |
| `affinity_label_unassign` | Unassign affinity label from VM/host |

### Events

| Tool | Description |
|------|-------------|
| `event_list` | List events |
| `event_get` | Get event details |
| `event_search` | Search events |
| `event_alerts` | Get alert events |
| `event_errors` | Get error events |
| `event_warnings` | Get warning events |
| `event_summary` | Get events summary |
| `event_acknowledge` | Acknowledge event |
| `event_clear_alerts` | Clear all alert events |
| `event_subscription_list` | List event subscriptions |
| `bookmark_list` | List bookmarks |

### RBAC - Users

| Tool | Description |
|------|-------------|
| `user_list` | List users |
| `user_get` | Get user details |
| `user_create` | Create user |
| `user_update` | Update user |
| `user_delete` | Delete user |
| `user_group_list` | List user's groups |

### RBAC - Groups

| Tool | Description |
|------|-------------|
| `group_list` | List groups |
| `group_get` | Get group details |

### RBAC - Roles

| Tool | Description |
|------|-------------|
| `role_list` | List roles |
| `role_get` | Get role details |
| `role_create` | Create role |
| `role_update` | Update role |
| `role_delete` | Delete role |

### RBAC - Permissions

| Tool | Description |
|------|-------------|
| `permit_list` | List permits |
| `permission_list` | List permissions |
| `permission_assign` | Assign permission |
| `permission_revoke` | Revoke permission |

### RBAC - Tags

| Tool | Description |
|------|-------------|
| `tag_list` | List tags |
| `tag_create` | Create tag |
| `tag_delete` | Delete tag |
| `tag_assign` | Assign tag into resource |
| `tag_unassign` | Unassign tag from resource |
| `tag_list_resources` | List resources with tag |

### Quotas

| Tool | Description |
|------|-------------|
| `quota_list` | List quotas in data center |
| `quota_get` | Get quota details |
| `quota_create` | Create quota |
| `quota_update` | Update quota |
| `quota_delete` | Delete quota |
| `quota_cluster_limit_list` | List quota cluster limits |
| `quota_storage_limit_list` | List quota storage limits |

### System & Jobs

| Tool | Description |
|------|-------------|
| `system_get` | Get system info |
| `system_option_list` | List system options |
| `job_list` | List jobs |
| `job_get` | Get job details |
| `job_cancel` | Cancel job |
| `system_statistics` | Get system statistics |

## Architecture

```
┌──────────────────────────────┐
│  MCP Client (Claude / etc.)  │
│         stdio (JSON-RPC)     │
└──────────────┬───────────────┘
               │
┌──────────────▼───────────────┐
│     MCP Server (server.py)   │
│                              │
│  ┌─────────────────────────┐ │
│  │  OvirtMCP (ovirt_mcp)   │ │  ← Core SDK wrapper
│  │  150+ methods            │ │
│  ├─────────────────────────┤ │
│  │  Extension Modules      │ │
│  │  - NetworkMCP           │ │
│  │  - ClusterMCP           │ │
│  │  - TemplateMCP          │ │
│  │  - DataCenterMCP        │ │
│  │  - HostExtendedMCP      │ │
│  │  - StorageExtendedMCP   │ │
│  │  - DiskExtendedMCP      │ │
│  │  - EventsMCP            │ │
│  │  - AffinityMCP          │ │
│  │  - RbacMCP              │ │
│  │  - VmExtendedMCP        │ │
│  │  - TemplateExtendedMCP  │ │
│  │  - QuotaMCP             │ │
│  │  - SystemMCP            │ │
│  └─────────────────────────┘ │
└──────────────┬───────────────┘
               │
┌──────────────▼───────────────┐
│     oVirt Engine REST API    │
└──────────────────────────────┘
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Lint
ruff check src/ tests/
```

## Requirements

- Python >= 3.10
- oVirt Engine 4.4+

## License

MIT License — see [LICENSE](LICENSE) for details.

## Author

Joey Ma ([@imjoey](https://github.com/imjoey))

## Related Projects

- [oVirt](https://www.ovirt.org/) — Open-source virtualization management
- [ovirtsdk4](https://github.com/oVirt/ovirt-engine-sdk-python) — Official oVirt Python SDK
- [Model Context Protocol](https://modelcontextprotocol.io/) — The MCP specification
