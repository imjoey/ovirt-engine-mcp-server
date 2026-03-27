#!/usr/bin/env python3
"""Docker healthcheck script for oVirt MCP Server.

This script performs a real health check by:
1. Verifying the configuration is loaded
2. Attempting to connect to the oVirt Engine
3. Checking that basic SDK operations work

Exit codes:
    0: Healthy - oVirt connection successful
    1: Unhealthy - connection or configuration failure
"""

import sys
import logging

# Suppress ovirtsdk4 INFO logs during healthcheck
logging.getLogger("ovirtsdk4").setLevel(logging.WARNING)

try:
    from .config import load_config, Config
    from ovirtsdk4 import Connection
except ImportError:
    # If imports fail, we're definitely unhealthy
    print("FAIL: Required modules not available")
    sys.exit(1)


def check_ovirt_connection(config: Config) -> bool:
    """Attempt to connect to oVirt Engine and verify connectivity.
    
    Args:
        config: The configuration object with oVirt credentials
        
    Returns:
        True if connection successful, False otherwise
    """
    if not config.ovirt_engine_url:
        print("FAIL: OVIRT_ENGINE_URL not configured")
        return False
    
    if not config.ovirt_engine_user:
        print("FAIL: OVIRT_ENGINE_USER not configured")
        return False
    
    if not config.ovirt_engine_password:
        print("FAIL: OVIRT_ENGINE_PASSWORD not configured")
        return False
    
    try:
        # Create connection to oVirt Engine
        connection = Connection(
            url=config.ovirt_engine_url,
            username=config.ovirt_engine_user,
            password=config.ovirt_engine_password,
            ca_file=config.ovirt_engine_ca_file or None,
            insecure=not bool(config.ovirt_engine_ca_file),
            timeout=max(5, config.ovirt_engine_timeout // 2),  # Use shorter timeout for healthcheck
        )
        if not connection.test():
            print("FAIL: oVirt connection test failed")
            return False
        
        # Try to fetch system information to verify the connection is working
        system_service = connection.system_service()
        api_summary = system_service.get()
        
        if api_summary is None:
            print("FAIL: Could not retrieve oVirt system info")
            return False
        
        # Log basic info for debugging
        print(f"OK: Connected to oVirt {getattr(api_summary, 'product_info', 'unknown')}")
        return True
        
    except Exception as e:
        print(f"FAIL: oVirt connection error: {type(e).__name__}")
        return False
    finally:
        # Ensure connection is closed
        if 'connection' in locals():
            try:
                connection.close()
            except Exception as e:
                logging.debug(f"Connection cleanup failed: {e}")


def main():
    """Main healthcheck entry point."""
    try:
        config = load_config()
    except Exception as e:
        print(f"FAIL: Configuration error: {type(e).__name__}")
        sys.exit(1)
    
    if check_ovirt_connection(config):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()