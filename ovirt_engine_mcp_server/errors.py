#!/usr/bin/env python3
"""Structured error types for oVirt MCP."""


class OvirtMCPError(Exception):
    """Base exception for all oVirt MCP errors."""

    def __init__(self, message: str, code: str = "UNKNOWN", retryable: bool = False):
        self.message = message
        self.code = code
        self.retryable = retryable
        super().__init__(message)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON response."""
        return {
            "error": True,
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }


class OvirtConnectionError(OvirtMCPError):
    """Failed to connect to oVirt Engine."""

    def __init__(self, message: str = "无法连接到 oVirt Engine"):
        super().__init__(message, code="CONNECTION_ERROR", retryable=True)


class NotFoundError(OvirtMCPError):
    """Requested resource not found."""

    def __init__(self, message: str = "未找到请求的资源"):
        super().__init__(message, code="NOT_FOUND", retryable=False)


class OvirtPermissionError(OvirtMCPError):
    """Permission denied."""

    def __init__(self, message: str = "权限不足"):
        super().__init__(message, code="PERMISSION_DENIED", retryable=False)


class ValidationError(OvirtMCPError):
    """Input validation failed."""

    def __init__(self, message: str = "参数验证失败"):
        super().__init__(message, code="VALIDATION_ERROR", retryable=False)


class OvirtTimeoutError(OvirtMCPError):
    """Operation timed out."""

    def __init__(self, message: str = "操作超时"):
        super().__init__(message, code="TIMEOUT", retryable=True)


class SDKError(OvirtMCPError):
    """oVirt SDK error."""

    def __init__(self, message: str = "oVirt SDK 错误"):
        super().__init__(message, code="SDK_ERROR", retryable=True)


# NOTE: The Ovirt-prefixed names should always be used.
# Aliases that shadow Python builtins have been removed to prevent confusion.
