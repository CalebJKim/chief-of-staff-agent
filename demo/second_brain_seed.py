"""Restore only the repository's demo vault; never reset a connected personal vault."""
from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4
from zipfile import ZipFile


def check_reset(root: Path, profile: Path) -> None:
    demo = root.resolve() / "demo"
    for path in (demo, demo / "CoS_SecondBrain", demo / ".second-brain-backups"):
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


def reset_second_brain(root: Path, profile: Path) -> dict:
    check_reset(root, profile)
    demo = root.resolve() / "demo"
    vault = demo / "CoS_SecondBrain"
    backup = None
    # Stage first; a bad archive never replaces the working notes.
    with tempfile.TemporaryDirectory(prefix=".second-brain-reset-", dir=demo) as temporary:
        restored = Path(temporary) / "vault"
        with ZipFile(demo / "templates" / "CoS_SecondBrain.zip") as archive:
            archive.extractall(restored)
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
    return {"vault": str(vault), "backup": str(backup) if backup else None}
