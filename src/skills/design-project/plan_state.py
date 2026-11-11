#!/usr/bin/env python3
"""
Entry point of the planning conductor state script.

Run `plan_state.py --help` for the commands. The package next to this file holds the
store, engine, registry, checks and cli modules.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_state.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
