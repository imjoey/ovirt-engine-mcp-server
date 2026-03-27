#!/usr/bin/env python3
"""Base class for MCP extension modules with common resource finding utilities."""

from typing import Any, Callable, Dict, Optional
import logging

from .search_utils import sanitize_search_value as _sanitize_search_value

logger = logging.getLogger(__name__)


# Resource type to service getter mapping
# Each entry maps a resource type to a function that gets the service from system_service
RESOURCE_SERVICE_GETTERS: Dict[str, Callable[[Any], Any]] = {
    "vm": lambda s: s.vms_service(),
    "host": lambda s: s.hosts_service(),
    "cluster": lambda s: s.clusters_service(),
    "datacenter": lambda s: s.data_centers_service(),
    "storage_domain": lambda s: s.storage_domains_service(),
    "network": lambda s: s.networks_service(),
    "template": lambda s: s.templates_service(),
    "disk": lambda s: s.disks_service(),
    "vnic_profile": lambda s: s.vnic_profiles_service(),
    "vm_pool": lambda s: s.vm_pools_service(),
    "user": lambda s: s.users_service(),
    "role": lambda s: s.roles_service(),
    "permission": lambda s: s.permissions_service(),
    "event": lambda s: s.events_service(),
    "job": lambda s: s.jobs_service(),
    # Note: quota is under datacenter, not system_service
    # Note: affinity_group is under cluster, not system_service
    "mac_pool": lambda s: s.mac_pools_service(),
    "network_filter": lambda s: s.network_filters_service(),
    "qos": lambda s: s.qoss_service(),
    "iscsi_bond": lambda s: s.iscsi_bonds_service(),
    "storage_connection": lambda s: s.storage_connections_service(),
}

# Resource type to service method name mapping (for getting individual resource service)
RESOURCE_SERVICE_NAMES: Dict[str, str] = {
    "vm": "vm_service",
    "host": "host_service",
    "cluster": "cluster_service",
    "datacenter": "data_center_service",
    "storage_domain": "storage_domain_service",
    "network": "network_service",
    "template": "template_service",
    "disk": "disk_service",
    "vnic_profile": "vnic_profile_service",
    "vm_pool": "vm_pool_service",
    "user": "user_service",
    "role": "role_service",
    "permission": "permission_service",
    "event": "event_service",
    "job": "job_service",
    # Note: quota is under datacenter, not system_service
    # Note: affinity_group is under cluster, not system_service
    "mac_pool": "mac_pool_service",
    "network_filter": "network_filter_service",
    "qos": "qos_service",
    "iscsi_bond": "iscsi_bond_service",
    "storage_connection": "storage_connection_service",
}


class BaseMCP:
    """Base class for MCP extension modules.

    Provides common utilities for resource lookup and connection management.

    Usage:
        class MyMCP(BaseMCP):
            def __init__(self, ovirt_mcp):
                super().__init__(ovirt_mcp)

            def get_something(self, name_or_id: str):
                vm = self._find_resource("vm", name_or_id)
                if not vm:
                    return None
                # Work with vm object...
    """

    def __init__(self, ovirt_mcp):
        """Initialize the MCP extension module.

        Args:
            ovirt_mcp: The main OvirtMCP instance providing connection management
        """
        self.ovirt = ovirt_mcp

    @property
    def connection(self):
        """Get the oVirt connection from the main OvirtMCP instance."""
        return self.ovirt.connection

    @property
    def connected(self) -> bool:
        """Check if connected to oVirt."""
        return self.ovirt.connected

    def _find_resource(self, resource_type: str, name_or_id: str) -> Optional[Any]:
        """Find a resource by name or ID.

        This is a generic finder that first tries to get the resource by ID,
        and if that fails, searches by name.

        Args:
            resource_type: Type of resource (e.g., "vm", "host", "cluster")
            name_or_id: Resource name or ID

        Returns:
            The SDK resource object if found, None otherwise
        """
        service_getter = RESOURCE_SERVICE_GETTERS.get(resource_type)
        service_name = RESOURCE_SERVICE_NAMES.get(resource_type)

        if not service_getter or not service_name:
            raise ValueError(f"Unknown resource type: {resource_type}")

        try:
            service = service_getter(self.connection.system_service())
            resource_service = getattr(service, service_name)(name_or_id)
            resource = resource_service.get()
            if resource:
                return resource
        except Exception as e:
            logger.debug(f"{resource_type} lookup by ID failed: {e}")

        # Try searching by name
        try:
            service = service_getter(self.connection.system_service())
            resources = service.list(search=f"name={_sanitize_search_value(name_or_id)}")
            return resources[0] if resources else None
        except Exception as e:
            logger.debug(f"{resource_type} search by name failed: {e}")
            return None

    # Convenience methods for common resource types
    def _find_vm(self, name_or_id: str) -> Optional[Any]:
        """Find a VM by name or ID."""
        return self._find_resource("vm", name_or_id)

    def _find_host(self, name_or_id: str) -> Optional[Any]:
        """Find a host by name or ID."""
        return self._find_resource("host", name_or_id)

    def _find_cluster(self, name_or_id: str) -> Optional[Any]:
        """Find a cluster by name or ID."""
        return self._find_resource("cluster", name_or_id)

    def _find_datacenter(self, name_or_id: str) -> Optional[Any]:
        """Find a datacenter by name or ID."""
        return self._find_resource("datacenter", name_or_id)

    def _find_storage_domain(self, name_or_id: str) -> Optional[Any]:
        """Find a storage domain by name or ID."""
        return self._find_resource("storage_domain", name_or_id)

    def _find_network(self, name_or_id: str) -> Optional[Any]:
        """Find a network by name or ID."""
        return self._find_resource("network", name_or_id)

    def _find_template(self, name_or_id: str) -> Optional[Any]:
        """Find a template by name or ID."""
        return self._find_resource("template", name_or_id)

    def _find_disk(self, name_or_id: str) -> Optional[Any]:
        """Find a disk by name or ID."""
        return self._find_resource("disk", name_or_id)

    def _find_vnic_profile(self, name_or_id: str) -> Optional[Any]:
        """Find a VNIC profile by name or ID."""
        return self._find_resource("vnic_profile", name_or_id)

    def _find_vm_pool(self, name_or_id: str) -> Optional[Any]:
        """Find a VM pool by name or ID."""
        return self._find_resource("vm_pool", name_or_id)

    def _find_user(self, name_or_id: str) -> Optional[Any]:
        """Find a user by name or ID."""
        return self._find_resource("user", name_or_id)

    def _find_role(self, name_or_id: str) -> Optional[Any]:
        """Find a role by name or ID."""
        return self._find_resource("role", name_or_id)
