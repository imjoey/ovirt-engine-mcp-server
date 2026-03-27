#!/usr/bin/env python3
"""Decorators for oVirt MCP modules."""

import functools
from typing import Callable, TypeVar, Any

from .errors import OvirtConnectionError

T = TypeVar("T")


def require_connection(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator that checks if oVirt connection is established before executing the method.

    Raises:
        OvirtConnectionError: If not connected to oVirt

    Usage:
        @require_connection
        def some_method(self, ...):
            # Method implementation
            pass
    """
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs) -> T:
        if not self.ovirt.connected:
            raise OvirtConnectionError()
        return func(self, *args, **kwargs)
    return wrapper
