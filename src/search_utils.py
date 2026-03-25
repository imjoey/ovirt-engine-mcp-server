#!/usr/bin/env python3
"""Search query utilities for oVirt MCP.

Provides sanitization functions to prevent search query injection attacks.
"""


def sanitize_search_value(value: str) -> str:
    """Sanitize a value for use in oVirt search queries.

    Prevents search query injection by escaping special characters.
    oVirt search syntax uses: ; & | ( ) " and spaces as special chars.

    Args:
        value: The raw user-provided value

    Returns:
        Sanitized value safe for use in search queries
    """
    if not value:
        return value
    # Escape backslashes and double quotes
    sanitized = value.replace("\\", "\\\\").replace('"', '\\"')
    # If contains special chars or spaces, wrap in quotes
    special_chars = {" ", ";", "&", "|", "(", ")", "<", ">", "=", "!"}
    if any(c in sanitized for c in special_chars):
        return f'"{sanitized}"'
    return sanitized
