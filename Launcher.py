#!/usr/bin/env python3
"""Compatibility entry point; the same safe implementation as start.py."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from start import main

if __name__ == "__main__":
    raise SystemExit(main())
