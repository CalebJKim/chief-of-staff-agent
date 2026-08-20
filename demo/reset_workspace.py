#!/usr/bin/env python
"""Reset the reference Workspace to its original seeded state."""
from __future__ import annotations
import subprocess, sys
from pathlib import Path
script = Path(__file__).with_name("seed_workspace.py")
raise SystemExit(subprocess.call([sys.executable, str(script), "--reset", "--confirm", *sys.argv[1:]]))
