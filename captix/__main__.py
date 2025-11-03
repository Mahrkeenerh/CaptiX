#!/usr/bin/env python3
"""
Entry point for python -m captix execution.

This module enables running CaptiX as a Python module:
    python3 -m captix --ui
    python3 -m captix --screenshot
    python3 -m captix --info

The actual CLI logic is in captix.cli module.
"""

from captix.cli import main
import sys

if __name__ == "__main__":
    sys.exit(main())
