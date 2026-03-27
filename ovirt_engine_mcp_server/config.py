#!/usr/bin/env python3
"""Config loader for oVirt MCP Server."""

import os
import logging
from dataclasses import dataclass
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

# Mapping from env var names to dataclass field names
ENV_TO_FIELD_MAP = {
    "OVIRT_ENGINE_URL": "ovirt_engine_url",
    "OVIRT_ENGINE_USER": "ovirt_engine_user",
    "OVIRT_ENGINE_PASSWORD": "ovirt_engine_password",
    "OVIRT_ENGINE_CA_FILE": "ovirt_engine_ca_file",
    "OVIRT_ENGINE_TIMEOUT": "ovirt_engine_timeout",
    "OVIRT_ENGINE_INSECURE": "ovirt_engine_insecure",
    "MCP_LOG_LEVEL": "mcp_log_level",
}


@dataclass
class Config:
    """oVirt MCP Server configuration."""

    ovirt_engine_url: str = ""
    ovirt_engine_user: str = ""
    ovirt_engine_password: str = ""
    ovirt_engine_ca_file: str = ""
    ovirt_engine_timeout: int = 30
    ovirt_engine_insecure: bool = False
    mcp_log_level: str = "INFO"


def _convert_value(value, target_type):
    """Convert value to target type."""
    if value is None:
        return None
    if target_type == bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")
        return bool(value)
    if target_type == int:
        return int(value)
    return str(value)


def load_config(path: str = "config.yaml") -> Config:
    """
    Load configuration from YAML file and environment variables.

    Environment variables take precedence over YAML file values.
    """
    data = {}

    # Load from YAML file
    if os.path.exists(path):
        try:
            with open(path) as f:
                yaml_data = yaml.safe_load(f) or {}
                for key, value in yaml_data.items():
                    normalized_key = ENV_TO_FIELD_MAP.get(key, key.lower())
                    data[normalized_key] = value
                logger.debug(f"Loaded config from {path}")
        except Exception as e:
            logger.warning(f"Failed to load config from {path}: {e}")

    # Override with environment variables (highest priority)
    for env_key, field_name in ENV_TO_FIELD_MAP.items():
        env_value = os.environ.get(env_key)
        if env_value is not None:
            field_type = Config.__dataclass_fields__[field_name].type
            if hasattr(field_type, "__origin__") and field_type.__origin__ is Optional:
                field_type = field_type.__args__[0]
            try:
                data[field_name] = _convert_value(env_value, field_type)
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to convert env var {env_key}={env_value}: {e}")

    # Build Config with valid fields only
    valid_fields = {}
    for field_name in Config.__dataclass_fields__:
        if field_name in data:
            valid_fields[field_name] = data[field_name]

    return Config(**valid_fields)


# Fields that should be sanitized in logs
SENSITIVE_FIELDS = {"ovirt_engine_password"}


def sanitize_log_message(message: str) -> str:
    """Sanitize a log message by masking sensitive credential values."""
    import re
    sanitized = message
    for pattern, replacement in [
        (r'(password[=:]\s*)[^\s,\]]+', r'\1***'),
        (r'(api_key[=:]\s*)[^\s,\]]+', r'\1***'),
        (r'(token[=:]\s*)[^\s,\]]+', r'\1***'),
        (r'(secret[=:]\s*)[^\s,\]]+', r'\1***'),
    ]:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
    return sanitized
