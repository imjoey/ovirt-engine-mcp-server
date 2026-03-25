# oVirt MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io/) (MCP) server for [oVirt](https://www.ovirt.org/) / RHV virtualization management. Provides 30+ tools for managing VMs, hosts, clusters, networks, storage, templates, and more — enabling AI assistants like Claude to interact with your virtualization infrastructure.

## Features

- **30+ MCP Tools** — Full lifecycle management for VMs, hosts, clusters, networks, storage, templates, snapshots, and disks
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

### Virtual Machines

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

### Snapshots

| Tool | Description |
|------|-------------|
| `snapshot_list` | List VM snapshots |
| `snapshot_create` | Create a snapshot |
| `snapshot_restore` | Restore a snapshot |
| `snapshot_delete` | Delete a snapshot |

### Disks

| Tool | Description |
|------|-------------|
| `disk_list` | List disks |
| `disk_create` | Create a disk |
| `disk_attach` | Attach disk to VM |

### Networks

| Tool | Description |
|------|-------------|
| `network_list` | List networks |
| `nic_list` | List VM NICs |
| `nic_add` | Add NIC to VM |
| `nic_remove` | Remove NIC from VM |

### Hosts

| Tool | Description |
|------|-------------|
| `host_list` | List hosts |
| `host_activate` | Activate a host |
| `host_deactivate` | Deactivate a host (maintenance mode) |

### Clusters

| Tool | Description |
|------|-------------|
| `cluster_list` | List clusters |
| `cluster_hosts` | List hosts in a cluster |
| `cluster_vms` | List VMs in a cluster |
| `cluster_cpu_load` | Get cluster CPU load |

### Storage

| Tool | Description |
|------|-------------|
| `storage_list` | List storage domains |
| `storage_attach` | Attach storage domain |

### Templates

| Tool | Description |
|------|-------------|
| `template_list` | List templates |
| `template_vm_create` | Create VM from template |

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
│  │  30+ methods            │ │
│  ├─────────────────────────┤ │
│  │  NetworkMCP             │ │  ← Extension modules
│  │  ClusterMCP             │ │
│  │  TemplateMCP            │ │
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
