#!/usr/bin/env python
"""Small, read-only Markdown vault search; no index, embeddings, or network calls."""
from __future__ import annotations

import argparse
import json
import os
import re
from itertools import islice
from pathlib import Path
from urllib.parse import quote

MAX_FILES = 1000
MAX_DIRECTORIES = 1000
MAX_FILE_BYTES = 128 * 1024
CONTEXT_CHARS = 1800
STOPWORDS = set("the and for from with this that today please update updated review notes needs into your".split())


def home() -> Path:
    if os.environ.get("HERMES_HOME"):
        return Path(os.environ["HERMES_HOME"]).expanduser()
    return Path(os.environ["LOCALAPPDATA"]) / "hermes" if os.name == "nt" and os.environ.get("LOCALAPPDATA") else Path.home() / ".hermes"


def configured_vault(profile: Path) -> Path | None:
    config = profile / "second-brain.json"
    if not config.exists():
        return None
    root = Path(json.loads(config.read_text(encoding="utf-8"))["vault_path"]).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("Configured Second Brain folder is unavailable")
    return root


def terms(text: str) -> set[str]:
    return {t for t in re.findall(r"[^\W_]+", text.casefold()) if len(t) > 2 and t not in STOPWORDS and not t.isdigit()}


def read_note(root: Path, relative: str, max_chars: int = 4000) -> dict:
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or path.suffix.casefold() != ".md":
        raise ValueError("Read only Markdown notes inside the configured Second Brain")
    if any(part.startswith((".", "_")) for part in path.relative_to(root).parts):
        raise ValueError("Hidden or archived notes are excluded")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Note exceeds the bounded reader's size limit")
    text = path.read_text(encoding="utf-8-sig")
    front = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, re.S)
    metadata = front.group(1) if front else ""
    body = text[front.end():] if front else text
    title = re.search(r"(?m)^title:\s*(.+)$", metadata)
    heading = re.search(r"(?m)^#\s+(.+)$", body)
    date = re.search(r"(?m)^(?:updated|source_date):\s*(.+)$", metadata)
    return {
        "note": path.relative_to(root).as_posix(),
        "title": title.group(1).strip(" \"'") if title else heading.group(1) if heading else path.stem,
        "updated": date.group(1).strip(" \"'") if date else None,
        "url": "obsidian://open?path=" + quote(str(path), safe=""),
        "text": body.strip()[:max_chars],
        "truncated": len(body.strip()) > max_chars,
    }


def matched_excerpt(text: str, query_terms: set[str], max_chars: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if max_chars < 4:
        return text[:max(0, max_chars)]
    if len(text) <= max_chars:
        return text
    match = next((m for m in re.finditer(r"[^\W_]+", text) if m.group().casefold() in query_terms), None)
    start = max(0, match.start() - max_chars // 4) if match else 0
    if start and not text[start - 1].isspace():
        start = text.find(" ", start) + 1
    prefix = "… " if start else ""
    available = max_chars - len(prefix)
    if len(text) - start <= available:
        return prefix + text[start:]
    passage = text[start:start + available - 2].rsplit(" ", 1)[0]
    return prefix + passage + " …"


def search(root: Path, queries: list[str], limit: int = 3, excerpt_chars: int = 280) -> list[dict]:
    """Match query words to note titles/content, keeping one best match per query."""
    query_sets = [terms(query) for query in queries]
    if limit <= 0 or not any(query_sets):
        return []
    notes = []
    seen = 0
    for directory, dirs, files in islice(os.walk(root, followlinks=False), MAX_DIRECTORIES):
        dirs[:] = sorted(d for d in dirs if not d.startswith((".", "_")))
        for filename in sorted(files):
            if not filename.lower().endswith(".md") or filename.startswith((".", "_")):
                continue
            seen += 1
            if seen > MAX_FILES:
                break
            try:
                note = read_note(root, str((Path(directory) / filename).relative_to(root)), MAX_FILE_BYTES)
                notes.append((note, terms(note["title"]), terms(note["text"])))
            except (OSError, ValueError, RuntimeError):
                continue
        if seen > MAX_FILES:
            break
    selected = []
    used = set()
    for query_terms in query_sets:
        ranked = []
        for note, title_terms, body_terms in notes:
            if note["note"] in used:
                continue
            title_hits = len(query_terms & title_terms)
            body_hits = len(query_terms & body_terms)
            if title_hits < min(2, len(query_terms)) and body_hits < max(1, min(3, len(query_terms))):
                continue
            if not query_terms:
                continue
            score = 4 * title_hits / max(1, len(title_terms)) ** .5 + body_hits / max(1, len(body_terms)) ** .5
            ranked.append((score, note["note"], note))
        if ranked:
            note = sorted(ranked, key=lambda item: (-item[0], item[1]))[0][2]
            used.add(note["note"])
            selected.append({k: v for k, v in note.items() if k not in {"text", "truncated"}} | {"excerpt": matched_excerpt(note["text"], query_terms, excerpt_chars)})
        if len(selected) >= limit:
            break
    return selected


def packet_context(packet: dict, profile: Path) -> dict | None:
    try:
        root = configured_vault(profile)
        if root is None:
            return None
        queries = [m.get("subject", "") for m in packet.get("mail", [])]
        queries += [f.get("name", "") for f in packet.get("recent_files", [])]
        queries += [m.get("title", "") for m in packet.get("meetings", [])]
        context = {"status": "ok", "role": "Background notes, not live status or write authorization.", "notes": search(root, queries)}
        while len(json.dumps(context, ensure_ascii=False, separators=(",", ":"))) > CONTEXT_CHARS and context["notes"]:
            context["notes"].pop()
        if not context["notes"]:
            context["status"] = "ok_empty"
        return context
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        return {"status": "error", "error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    p = commands.add_parser("search")
    p.add_argument("query")
    p.add_argument("--max", type=int, default=3)
    p = commands.add_parser("read")
    p.add_argument("note")
    p.add_argument("--max-chars", type=int, default=4000)
    args = parser.parse_args()
    try:
        root = configured_vault(home())
        if root is None:
            raise ValueError("Second Brain is not connected; configure it with install.py --second-brain PATH")
        if args.operation == "search":
            # Repeat the query to retrieve successive distinct matches.
            result = {"notes": search(root, [args.query] * min(max(args.max, 1), 5), limit=min(max(args.max, 1), 5))}
        else:
            result = read_note(root, args.note, min(max(args.max_chars, 1), 8000))
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
