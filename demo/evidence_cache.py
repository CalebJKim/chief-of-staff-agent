"""Remove generated Perplexity evidence only from this checkout's workspace."""
from __future__ import annotations

import re
import shutil
import stat
from pathlib import Path


RUN_FOLDER = re.compile(r"daily-brief-(?:[0-9a-f]{32}|[a-z0-9_]{8})")


def _check_path(path: Path, workspace: Path) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        info = None
    if info and (stat.S_ISLNK(info.st_mode) or
                 getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        raise RuntimeError(f"Refusing evidence cleanup through a linked path: {path}")
    resolved = path.resolve()
    if resolved != path.absolute() or not resolved.is_relative_to(workspace):
        raise RuntimeError(f"Evidence cleanup path must stay inside the workspace: {path}")


def check_evidence_cache(root: Path) -> tuple[list[Path], list[Path], int]:
    """Validate all cleanup targets without writing or following directory links."""
    workspace = root.resolve() / "CoS_Workspace"
    state = workspace / ".chief-of-staff-state"
    parents = (state, state / "chief-of-staff")
    for path in (workspace, *parents):
        _check_path(path, workspace)
    directories, standalone = [], []
    file_count = 0
    for parent in parents:
        if not parent.exists():
            continue
        for path in sorted(parent.iterdir()):
            if path.name in ("snapshot.json", "packet.json"):
                _check_path(path, workspace)
                if not path.is_file():
                    raise RuntimeError(f"Expected an evidence file: {path}")
                standalone.append(path)
                file_count += 1
            elif RUN_FOLDER.fullmatch(path.name):
                _check_path(path, workspace)
                if not path.is_dir():
                    continue
                directories.append(path)
                pending = [path]
                while pending:
                    for child in pending.pop().iterdir():
                        _check_path(child, workspace)
                        if child.is_dir():
                            pending.append(child)
                        else:
                            file_count += 1
    return directories, standalone, file_count


def clear_evidence_cache(root: Path) -> dict:
    directories, standalone, file_count = check_evidence_cache(root)
    # All resolved targets were checked before any recursive deletion.
    for directory in directories:
        shutil.rmtree(directory)
    for path in standalone:
        path.unlink()
    return {"run_folders_removed": len(directories), "files_removed": file_count}
