#!/usr/bin/env python
"""Reset this Perplexity demo using its CoS_Workspace state and Second Brain."""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate local setup without resetting or calling Google")
    parser.add_argument("--week-of", help="Monday date (YYYY-MM-DD); otherwise reuse the saved demo week")
    args = parser.parse_args(argv)
    state = ROOT / "CoS_Workspace" / ".chief-of-staff-state"
    # The reset always targets this checkout, regardless of inherited settings.
    os.environ["COS_STATE_DIR"] = str(state)
    for name in ("chief-of-staff-workspace-state.json", "google_token.json"):
        path = state / name
        if not path.is_file():
            raise SystemExit(f"Required demo state file is missing: {path}. Restore the Perplexity demo state before resetting.")
        json.loads(path.read_text(encoding="utf-8"))
    if sys.version_info < (3, 10):
        raise SystemExit("Python 3.10 or newer is required")
    import google.auth.transport.requests
    import google.oauth2.credentials
    import googleapiclient.discovery
    from zoneinfo import ZoneInfo
    from second_brain_seed import check_reset
    ZoneInfo("America/Los_Angeles")
    check_reset(ROOT, state)
    if args.check:
        print(json.dumps({"ok": True, "mode": "check", "python": sys.executable,
                          "state": str(state), "vault": str(ROOT / "CoS_Workspace" / "CoS_SecondBrain")}, indent=2))
        return 0
    command = [sys.executable, str(ROOT / "demo" / "seed_workspace.py"), "--reset", "--confirm"]
    if args.week_of:
        command.extend(["--week-of", args.week_of])
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
