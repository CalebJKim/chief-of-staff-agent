#!/usr/bin/env python
"""Reset Google Workspace and the repository's demo Second Brain to their baselines."""
from __future__ import annotations
import subprocess, sys
from pathlib import Path
script = Path(__file__).with_name("seed_workspace.py")
raise SystemExit(subprocess.call([sys.executable, str(script), "--reset", "--confirm", *sys.argv[1:]]))
