#!/usr/bin/env python3
"""Input validation for MCP tool arguments."""

import re
from typing import Any, Dict

from .errors import ValidationError


# Reusable validators

# Reusable validators
NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,253}$")


def validate_name(value: str, field: str = "name") -> str:
    """Validate a name field."""
    if not value or not value.strip():
        raise ValidationError(f"{field} 不能为空")
    value = value.strip()
    if len(value) > 254:
        raise ValidationError(f"{field} 长度不能超过 254 字符")
    return value


def validate_name_or_id(value: str, field: str = "name_or_id") -> str:
    """Validate a name_or_id field (more permissive)."""
    if not value or not value.strip():
        raise ValidationError(f"{field} 不能为空")
    return value.strip()


def validate_positive_int(
    value: Any, field: str, min_val: int = 1, max_val: int = None
) -> int:
    """Validate a positive integer field."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} 必须是整数")
    if v < min_val:
        raise ValidationError(f"{field} 必须 >= {min_val}")
    if max_val and v > max_val:
        raise ValidationError(f"{field} 必须 <= {max_val}")
    return v


def validate_bool(value: Any, field: str) -> bool:
    """Validate a boolean field."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    return bool(value)


# Per-tool validation rules
TOOL_VALIDATORS = {
    "vm_create": {
        "name": lambda v: validate_name(v, "VM 名称"),
        "cluster": lambda v: validate_name(v, "集群"),
        "memory_mb": lambda v: validate_positive_int(
            v, "内存(MB)", min_val=256, max_val=1048576
        )
        if v
        else v,
        "cpu_cores": lambda v: validate_positive_int(
            v, "CPU 核数", min_val=1, max_val=256
        )
        if v
        else v,
        "disk_size_gb": lambda v: validate_positive_int(
            v, "磁盘(GB)", min_val=1, max_val=65536
        )
        if v
        else v,
    },
    "vm_start": {"name_or_id": lambda v: validate_name_or_id(v)},
    "vm_stop": {"name_or_id": lambda v: validate_name_or_id(v)},
    "vm_restart": {"name_or_id": lambda v: validate_name_or_id(v)},
    "vm_delete": {"name_or_id": lambda v: validate_name_or_id(v)},
    "vm_update_resources": {
        "name_or_id": lambda v: validate_name_or_id(v),
        "memory_mb": lambda v: validate_positive_int(v, "内存(MB)", min_val=256)
        if v
        else v,
        "cpu_cores": lambda v: validate_positive_int(v, "CPU 核数", min_val=1)
        if v
        else v,
    },
    "snapshot_create": {
        "name_or_id": lambda v: validate_name_or_id(v),
        "description": lambda v: str(v)[:500] if v else v,
    },
    "snapshot_restore": {"name_or_id": lambda v: validate_name_or_id(v)},
    "snapshot_delete": {"name_or_id": lambda v: validate_name_or_id(v)},
    "disk_create": {
        "name": lambda v: validate_name(v, "磁盘名称"),
        "size_gb": lambda v: validate_positive_int(v, "磁盘(GB)", min_val=1),
    },
    "host_activate": {"name_or_id": lambda v: validate_name_or_id(v)},
    "host_deactivate": {"name_or_id": lambda v: validate_name_or_id(v)},
    "storage_attach": {
        "storage_name": lambda v: validate_name(v, "存储名称"),
        "dc_name": lambda v: validate_name(v, "数据中心"),
    },
}


def validate_tool_args(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and sanitize tool arguments.

    Args:
        tool_name: Name of the MCP tool
        args: Arguments to validate

    Returns:
        Sanitized arguments dict

    Raises:
        ValidationError: If validation fails
    """
    validators = TOOL_VALIDATORS.get(tool_name)
    if not validators:
        return args  # No validation rules for this tool

    sanitized = dict(args)
    for field, validator in validators.items():
        if field in sanitized and sanitized[field] is not None:
            try:
                sanitized[field] = validator(sanitized[field])
            except ValidationError:
                raise
            except Exception as e:
                raise ValidationError(f"{field} 验证失败: {e}")
    return sanitized
