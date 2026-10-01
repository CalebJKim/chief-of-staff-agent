#!/usr/bin/env python
"""Collect once and deliver a saved, bounded daily-brief packet."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

from brief import hermes_home

MAX_CHARS = 14000


def run(script: Path, *args: str) -> str:
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(script), *args],
        capture_output=True, encoding="utf-8", check=True,
    )
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('daily-brief', 'second-brain-update'), default='daily-brief')
    parser.add_argument("--fixture", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    scripts = Path(__file__).resolve().parent
    # Perplexity bundles ingest here. Hermes keeps it in the sibling skill.
    ingest = scripts / "ingest.py"
    if not ingest.is_file():
        ingest = scripts.parents[1] / "ingest/scripts/ingest.py"
    stage = "prepare"
    try:
        state = hermes_home() / "chief-of-staff"
        state.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            # Inherit the workspace's access rules on Windows.
            folder = (state / f"daily-brief-{uuid4().hex}").resolve()
            folder.mkdir()
        else:
            folder = Path(tempfile.mkdtemp(prefix="daily-brief-", dir=state)).resolve()
        snapshot = folder / "snapshot.json"
        packet_path = folder / "packet.json"
        stage = "ingest"
        fixture = ["--fixture", str(args.fixture)] if args.fixture else []
        run(ingest, "--output", str(snapshot), "--stdout", "none", *fixture)
        stage = "brief"
        encoded = run(
            scripts / "brief.py", "--snapshot", str(snapshot),
            "--mode", args.mode,
            "--max-meetings", "10", "--max-mail", "8", "--max-files", "8",
            "--max-chars", str(MAX_CHARS), "--work-end", "17",
        ).strip()
        json.loads(encoded)  # Never publish an incomplete or malformed packet.
        if len(encoded) > MAX_CHARS:
            raise ValueError("Brief packet exceeds its output budget")
        stage = "save"
        packet_path.write_text(encoded + "\n", encoding="utf-8", newline="\n")
        # Emit the fallback path first so it survives tail truncation by a tool.
        print(json.dumps({"packet_path": str(packet_path)}, ensure_ascii=False))
        print(encoded)
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        print(json.dumps({"ok": False, "stage": stage, "error": (detail or str(exc))[:2000]}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
