#!/usr/bin/env python3
"""Shared test fixtures and setup."""
import sys
import pytest
from unittest.mock import MagicMock

# 在任何导入之前 mock ovirtsdk4 模块
mock_sdk = MagicMock()
mock_sdk.types = MagicMock()
mock_sdk.types.Vm = MagicMock
mock_sdk.types.Cluster = MagicMock
mock_sdk.types.Template = MagicMock
mock_sdk.types.Cpu = MagicMock
mock_sdk.types.CpuTopology = MagicMock
mock_sdk.types.OperatingSystem = MagicMock
mock_sdk.types.Boot = MagicMock
mock_sdk.types.BootDevice = MagicMock
mock_sdk.types.BootDevice.HD = "hd"
mock_sdk.types.Nic = MagicMock
mock_sdk.types.NicInterface = MagicMock
mock_sdk.types.NicInterface.VIRTIO = "virtio"
mock_sdk.types.Network = MagicMock
mock_sdk.types.Disk = MagicMock
mock_sdk.types.DiskAttachment = MagicMock
mock_sdk.types.DiskInterface = MagicMock
mock_sdk.types.DiskInterface.VIRTIO = "virtio"
mock_sdk.types.Snapshot = MagicMock
mock_sdk.types.DataCenter = MagicMock
mock_sdk.types.Host = MagicMock
mock_sdk.types.HostStorage = MagicMock
mock_sdk.types.StorageDomain = MagicMock
mock_sdk.types.StorageDomainType = MagicMock
mock_sdk.types.StorageType = MagicMock
mock_sdk.types.StorageType.NFS = "nfs"
mock_sdk.types.StorageType.LOCALFS = "localfs"
mock_sdk.types.Vlan = MagicMock
mock_sdk.types.Ssh = MagicMock
mock_sdk.types.SshAuthenticationMethod = MagicMock
mock_sdk.types.SshAuthenticationMethod.PASSWORD = "password"
mock_sdk.types.AffinityGroup = MagicMock
mock_sdk.types.User = MagicMock
mock_sdk.types.Group = MagicMock
mock_sdk.types.Role = MagicMock
mock_sdk.types.Permission = MagicMock
mock_sdk.types.Permit = MagicMock
mock_sdk.types.Tag = MagicMock
mock_sdk.types.Version = MagicMock

mock_connection = MagicMock()
mock_sdk.Connection = mock_connection

# 注册 mock 模块
sys.modules['ovirtsdk4'] = mock_sdk
sys.modules['ovirtsdk4.types'] = mock_sdk.types

from src.config import Config


@pytest.fixture
def mock_config():
    """Create a test Config."""
    return Config(
        ovirt_engine_url="https://ovirt.test",
        ovirt_engine_user="admin@internal",
        ovirt_engine_password="test",
    )


@pytest.fixture
def mock_ovirt_connection():
    """Create a mock oVirt SDK connection."""
    conn = MagicMock()
    conn.test.return_value = True
    return conn


@pytest.fixture
def mock_sdk_module():
    """Return the mocked SDK module for use in tests."""
    return mock_sdk
