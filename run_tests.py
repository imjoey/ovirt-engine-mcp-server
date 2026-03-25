#!/usr/bin/env python3
"""
Ovirt-MCP Test Runner

Usage:
    python run_tests.py              # Run all tests
    python run_tests.py -k "skill"   # Run tests matching "skill"
    python run_tests.py -m "not integration"  # Skip integration tests
"""

import sys
import pytest
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

if __name__ == "__main__":
    # Default arguments if none provided
    args = sys.argv[1:] if len(sys.argv) > 1 else [
        "tests/",
        "-v",
        "--tb=short",
        "-ra",
    ]
    sys.exit(pytest.main(args))
