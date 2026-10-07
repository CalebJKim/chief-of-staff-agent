"""Restore only CoS_Workspace/CoS_SecondBrain; never follow personal vault settings."""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4
from zipfile import ZipFile


def check_reset(root: Path, profile: Path) -> None:
    demo = root.resolve() / "demo"
    workspace = root.resolve() / "CoS_Workspace"
    for path in (demo, workspace, workspace / "CoS_SecondBrain", demo / ".second-brain-backups"):
        if path.resolve() != path.absolute():
            raise RuntimeError(f"Refusing Second Brain reset through a linked path: {path}")
    jobs = profile / "cron" / "jobs.json"
    if jobs.exists() and any(job.get("fire_claim") for job in json.loads(jobs.read_text(encoding="utf-8"))["jobs"]):
        raise RuntimeError("A cron job is running in this profile. Let it finish before resetting the demo.")
    with ZipFile(demo / "templates" / "CoS_SecondBrain.zip") as archive:
        for item in archive.infolist():
            name = PurePosixPath(item.filename)
            if name.is_absolute() or ".." in name.parts or "\\" in item.filename or ":" in item.filename:
                raise RuntimeError(f"Unsafe Second Brain baseline entry: {item.filename}")
            if name.parts and name.parts[0] == ".obsidian":
                raise RuntimeError("The baseline must not contain machine-specific Obsidian settings")
        if "index.md" not in archive.namelist() or archive.testzip() is not None:
            raise RuntimeError("Second Brain baseline is missing index.md or contains corrupt files")


def reset_second_brain(root: Path, profile: Path, *, resources: dict | None = None) -> dict:
    check_reset(root, profile)
    demo = root.resolve() / "demo"
    workspace = root.resolve() / "CoS_Workspace"
    workspace.mkdir(exist_ok=True)
    vault = workspace / "CoS_SecondBrain"
    backup = None
    # Inherit the selected workspace's access grants. On Windows, staging in a
    # TemporaryDirectory can carry its private ACL into the replacement vault.
    # Stage first; a bad archive never replaces the working notes.
    restored = workspace / (".second-brain-reset-" + uuid4().hex)
    restored.mkdir()
    try:
        with ZipFile(demo / "templates" / "CoS_SecondBrain.zip") as archive:
            archive.extractall(restored)
        links_updated = 0
        if resources is not None:
            from second_brain_links import refresh_links
            links_updated = refresh_links(restored, demo, resources)
        settings = vault / ".obsidian"
        if settings.is_dir():
            shutil.copytree(settings, restored / ".obsidian", symlinks=True)
        if vault.exists():
            backup = demo / ".second-brain-backups" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8])
            backup.parent.mkdir(parents=True, exist_ok=True)
            vault.rename(backup)
        try:
            restored.rename(vault)
        except OSError:
            if backup is not None and not vault.exists():
                backup.rename(vault)
            raise
    finally:
        if restored.exists():
            if restored.resolve() != restored or restored.parent != workspace:
                raise RuntimeError(f"Refusing cleanup through a linked staging path: {restored}")
            shutil.rmtree(restored)
    return {"vault": str(vault), "backup": str(backup) if backup else None, "links_updated": links_updated}
