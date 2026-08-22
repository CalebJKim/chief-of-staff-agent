#!/usr/bin/env python
"""Execute one data-derived chief-of-staff workstream action plan."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def hermes_home() -> Path:
    override = os.environ.get("HERMES_HOME")
    if override:
        return Path(override).expanduser()
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "hermes"
    return Path.home() / ".hermes"


def run_step(step: list[str], home: Path) -> dict[str, Any]:
    if not isinstance(step, list) or len(step) < 2 or not all(isinstance(item, str) for item in step):
        raise RuntimeError("Invalid action-plan step")
    command = [sys.executable, str(home / "skills" / "productivity" / "ingest" / "scripts" / "actions.py"), *step]
    if step[:2] == ["gmail", "draft"] and (home / "chief-of-staff-workspace-state.json").is_file():
        command.append("--track-demo-state")
    command.append("--confirm") if step[0] in {"calendar", "sheets", "slides", "docs"} else None
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise RuntimeError(detail)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Action helper returned invalid JSON: {result.stdout[:200]}") from exc


def execute(index: int, plan_path: Path, home: Path, confirmed: bool) -> dict[str, Any]:
    if not confirmed:
        raise RuntimeError("Workstream actions require --confirm")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    workstreams = plan.get("workstreams", [])
    if index < 1 or index > len(workstreams):
        raise RuntimeError(f"Workstream {index} is not in the current action plan")
    entry = workstreams[index - 1]
    action = entry.get("action") or {}
    steps = action.get("steps") or []
    if not steps:
        raise RuntimeError(f"Workstream {index} has no executable action")
    results = [run_step(step, home) for step in steps]
    target = entry.get("target") or {}
    urls = []
    for result in results:
        if result.get("url") and result["url"] not in urls:
            urls.append(result["url"])
    if target.get("url") and target["url"] not in urls:
        urls.append(target["url"])
    return {
        "status": "completed",
        "workstream": index,
        "outcome": entry.get("outcome"),
        "action_kind": action.get("kind"),
        "target": target,
        "results": results,
        "urls": urls,
        "verified": all(result.get("verified", True) for result in results),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute a ranked chief-of-staff workstream")
    parser.add_argument("index", type=int)
    parser.add_argument("--plan", type=Path, default=hermes_home() / "chief-of-staff" / "action-plan.json")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(execute(args.index, args.plan, hermes_home(), args.confirm), ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
