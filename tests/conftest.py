"""Shared test fixtures."""
import pytest
from unittest.mock import MagicMock

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
