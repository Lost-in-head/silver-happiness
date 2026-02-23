#!/usr/bin/env python3
"""Run CLI from project root: python run_cli.py ask 'Hello' or python run_cli.py teach."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.cli import main

if __name__ == "__main__":
    main()
