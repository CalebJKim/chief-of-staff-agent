"""Guarded formatting and rendered previews for actions.py.

No Google calls at import time. Existing actions and compact reads stay unchanged.
Selectors are literal and case-sensitive. Formatting requires --confirm.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import stat
import sys
import tempfile
import urllib.request
from pathlib import Path


def utf16(text):
    return len(text.encode("utf-16-le")) // 2


def _runs(elements):
    return [{"start": e.get("startIndex", 0), "end": e.get("endIndex", 0),
             "text": e["textRun"].get("content", ""),
             "style": e["textRun"].get("textStyle", e["textRun"].get("style", {}))}
            for e in elements if "textRun" in e]


def _doc_list_kind(bullet, lists):
    if not bullet:
        return "none"
    levels = (lists or {}).get(bullet.get("listId"), {}).get("listProperties", {}).get("nestingLevels", [])
    level = bullet.get("nestingLevel", 0)
    if level >= len(levels):
        return "unknown"
    return "numbered" if levels[level].get("glyphType") else "bulleted" if levels[level].get("glyphSymbol") else "unknown"


def _paragraphs(content, tab_id, named_styles=None, lists=None):
    named = {s["namedStyleType"]: s for s in (named_styles or {}).get("styles", [])}
    for block in content:
        if "paragraph" in block:
            p = block["paragraph"]
            base = named.get("NORMAL_TEXT", {})
            inherited = named.get(p.get("paragraphStyle", {}).get("namedStyleType", "NORMAL_TEXT"), {})
            paragraph_style = {**base.get("paragraphStyle", {}), **inherited.get("paragraphStyle", {}), **p.get("paragraphStyle", {})}
            runs = _runs(p.get("elements", []))
            for run in runs:
                run["explicit_style"] = run["style"]
                # Google omits properties equal to the paragraph's named style.
                run["style"] = {**base.get("textStyle", {}), **inherited.get("textStyle", {}), **run["style"]}
            yield {"tab_id": tab_id, "start": block.get("startIndex", 0),
                   "end": block.get("endIndex", 0), "runs": runs,
                   "paragraph_style": paragraph_style, "bullet": p.get("bullet"),
                   "list_kind": _doc_list_kind(p.get("bullet"), lists)}
        for row in block.get("table", {}).get("tableRows", []):
            for cell in row.get("tableCells", []):
                yield from _paragraphs(cell.get("content", []), tab_id, named_styles, lists)
        if "tableOfContents" in block:
            yield from _paragraphs(block["tableOfContents"].get("content", []), tab_id, named_styles, lists)


def doc_records(doc):
    def walk(tabs):
        for tab in tabs:
            yield from _paragraphs(tab.get("documentTab", {}).get("body", {}).get("content", []),
                                   tab.get("tabProperties", {}).get("tabId"), tab.get("documentTab", {}).get("namedStyles"),
                                   tab.get("documentTab", {}).get("lists"))
            yield from walk(tab.get("childTabs", []))
    return list(walk(doc["tabs"])) if doc.get("tabs") else list(_paragraphs(doc.get("body", {}).get("content", []), None, doc.get("namedStyles"), doc.get("lists")))


def _slide_list_kind(bullet):
    if not bullet:
        return "none"
    glyph = bullet.get("glyph", "")
    if not glyph:
        return "unknown"
    return "numbered" if re.fullmatch(r"[0-9A-Za-z]+[.)]?", glyph.strip()) else "bulleted"


def slide_records(deck):
    def elements(items, slide_id):
        for e in items:
            if "elementGroup" in e:
                yield from elements(e["elementGroup"].get("children", []), slide_id)
            targets = [(None, e["shape"].get("text", {}))] if "shape" in e else []
            for r, row in enumerate(e.get("table", {}).get("tableRows", [])):
                targets.extend(({"rowIndex": r, "columnIndex": c}, cell.get("text", {}))
                               for c, cell in enumerate(row.get("tableCells", [])))
            for cell, text in targets:
                elems = text.get("textElements", [])
                yield {"slide_id": slide_id, "element_id": e["objectId"], "cell": cell,
                       "runs": _runs(elems),
                       "paragraphs": [{"start": p.get("startIndex", 0), "end": p.get("endIndex", 0),
                                       "paragraph_style": p["paragraphMarker"].get("style", {}),
                                       "bullet": p["paragraphMarker"].get("bullet"),
                                       "list_kind": _slide_list_kind(p["paragraphMarker"].get("bullet"))}
                                      for p in elems if "paragraphMarker" in p]}
    return [record for slide in deck.get("slides", [])
            for record in elements(slide.get("pageElements", []), slide["objectId"])]


def text_chunks(record):
    """Do not match across embedded objects or gaps omitted by the API."""
    chunks = []
    for run in record["runs"]:
        if chunks and chunks[-1][0] + utf16(chunks[-1][1]) == run["start"]:
            chunks[-1] = (chunks[-1][0], chunks[-1][1] + run["text"])
        else:
            chunks.append((run["start"], run["text"]))
    return chunks


def locate(records, find, all_matches=False):
    if not find or not find.strip():
        raise ValueError("--find must contain nonempty literal text")
    matches = []
    for record in records:
        for base, text in text_chunks(record):
            at = 0
            while (at := text.find(find, at)) >= 0:
                matches.append({"record": record, "start": base + utf16(text[:at]),
                                "end": base + utf16(text[:at + len(find)])})
                at += len(find)
    if not matches:
        raise ValueError("No matching text. Nothing was changed.")
    if len(matches) > 1 and not all_matches:
        raise ValueError(f"Ambiguous text: {len(matches)} matches. Narrow the target or explicitly use --all-matches.")
    if len(matches) > 100:
        raise ValueError("More than 100 matches. Narrow the target.")
    return matches


def style_requests(style, kind):
    """Translate a small documented schema; never accept arbitrary API requests."""
    if not isinstance(style, dict) or not style:
        raise ValueError("Style must be a nonempty JSON object")
    allowed = {"bold", "italic", "underline", "font_family", "font_size", "color", "link",
               "alignment", "space_before", "space_after", "line_spacing", "list"}
    if kind == "docs":
        allowed.add("heading")
    unknown = set(style) - allowed
    if unknown:
        raise ValueError(f"Unsupported style properties: {', '.join(sorted(unknown))}")
    text, paragraph = {}, {}
    for key, value in style.items():
        if key in {"bold", "italic", "underline"}:
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be true or false")
            text[key] = value
        elif key == "font_family":
            if not isinstance(value, str) or not value.strip():
                raise ValueError("font_family must be nonempty")
            if kind == "docs":
                text["weightedFontFamily"] = {"fontFamily": value}
            else:
                text["fontFamily"] = value
        elif key in {"font_size", "space_before", "space_after", "line_spacing"}:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{key} must be a finite number")
            minimum, maximum = ((1, 400) if key == "font_size" else (50, 500) if key == "line_spacing" else (0, 400))
            if not minimum <= value <= maximum:
                raise ValueError(f"{key} must be between {minimum} and {maximum}")
            if key == "font_size":
                text["fontSize"] = {"magnitude": value, "unit": "PT"}
            elif key == "line_spacing":
                paragraph["lineSpacing"] = value
            else:
                paragraph[{"space_before": "spaceAbove", "space_after": "spaceBelow"}[key]] = {"magnitude": value, "unit": "PT"}
        elif key == "color":
            if not isinstance(value, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
                raise ValueError("color must be #RRGGBB")
            rgb = dict(zip(("red", "green", "blue"), (int(value[i:i+2], 16) / 255 for i in (1, 3, 5))))
            text["foregroundColor"] = {"color": {"rgbColor": rgb}} if kind == "docs" else {"opaqueColor": {"rgbColor": rgb}}
        elif key == "link":
            if value is None:
                text["link"] = None
            elif isinstance(value, str) and re.match(r"^https?://[^\s]+$", value):
                text["link"] = {"url": value}
            else:
                raise ValueError("link must be an http(s) URL or null to remove it")
        elif key == "alignment":
            if value not in {"START", "CENTER", "END", "JUSTIFIED"}:
                raise ValueError("alignment must be START, CENTER, END, or JUSTIFIED")
            paragraph["alignment"] = value
        elif key == "heading":
            if isinstance(value, bool) or not isinstance(value, int) or value not in range(7):
                raise ValueError("heading must be 0 (normal text) through 6")
            paragraph["namedStyleType"] = f"HEADING_{value}" if value else "NORMAL_TEXT"
        elif key == "list" and value not in {"bulleted", "numbered", "none"}:
            raise ValueError("list must be bulleted, numbered, or none")
    return text, paragraph


def make_requests(kind, matches, style):
    text, paragraph = style_requests(style, kind)
    requests = []
    for match in matches:
        record = match["record"]
        if kind == "docs":
            span = {"startIndex": match["start"], "endIndex": match["end"]}
            if record["tab_id"]:
                span["tabId"] = record["tab_id"]
            target = {"range": span}
        else:
            target = {"objectId": record["element_id"], "textRange": {
                "type": "FIXED_RANGE", "startIndex": match["start"], "endIndex": match["end"]}}
            if record["cell"] is not None:
                target["cellLocation"] = record["cell"]
        if "list" in style:
            # Google strips leading tabs when creating bullets, shifting indices.
            if any(line.startswith("\t") for _, chunk in text_chunks(record) for line in chunk.splitlines()):
                raise ValueError("List formatting of tab-indented text is unsupported; indices could shift. Nothing was changed.")
            if style["list"] == "none":
                requests.append({"deleteParagraphBullets": dict(target)})
            else:
                numbered = "NUMBERED_DECIMAL_ALPHA_ROMAN" if kind == "docs" else "NUMBERED_DIGIT_ALPHA_ROMAN"
                preset = "BULLET_DISC_CIRCLE_SQUARE" if style["list"] == "bulleted" else numbered
                requests.append({"createParagraphBullets": {**target, "bulletPreset": preset}})
        if paragraph:
            property_name = "paragraphStyle" if kind == "docs" else "style"
            requests.append({"updateParagraphStyle": {**target, property_name: paragraph,
                                                      "fields": ",".join(sorted(paragraph))}})
        if text:
            property_name = "textStyle" if kind == "docs" else "style"
            requests.append({"updateTextStyle": {**target, property_name: {k: v for k, v in text.items() if v is not None},
                                                 "fields": ",".join("weightedFontFamily.fontFamily" if k == "weightedFontFamily" else k for k in sorted(text))}})
        # Adding/removing a Google hyperlink can implicitly reset color/underline.
        # Restore existing values per run unless the caller requested new values.
        if "link" in style:
            for run in record["runs"]:
                start, end = max(run["start"], match["start"]), min(run["end"], match["end"])
                if start >= end:
                    continue
                preserved = link_preserved_styles(run, style)
                if not preserved:
                    continue
                span_key = "range" if kind == "docs" else "textRange"
                partial = {**target, span_key: {**target[span_key], "startIndex": start, "endIndex": end}}
                property_name = "textStyle" if kind == "docs" else "style"
                requests.append({"updateTextStyle": {**partial, property_name: preserved,
                                                     "fields": ",".join(sorted(preserved))}})
    return requests


def link_preserved_styles(run, requested):
    preserved = {}
    for public, api_name in (("color", "foregroundColor"), ("underline", "underline")):
        if public not in requested:
            if api_name == "foregroundColor" and api_name not in run["style"]:
                raise ValueError("Cannot resolve existing text color for a link edit. Supply color explicitly.")
            preserved[api_name] = run["style"].get(api_name, False)
    return preserved


def _same(actual, expected):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(_same(actual.get(k), v) for k, v in expected.items())
    if isinstance(expected, bool):
        return (False if actual is None else actual) == expected
    if isinstance(expected, (int, float)):
        return isinstance(actual, (int, float, type(None))) and math.isclose(actual or 0, expected, abs_tol=0.0001)
    return actual == expected


def _identity(record):
    return (record.get("tab_id"), record.get("start")) if "tab_id" in record else (record["slide_id"], record["element_id"], json.dumps(record["cell"], sort_keys=True))


def verify(kind, before_matches, after_records, style):
    text, paragraph = style_requests(style, kind)
    index = {_identity(r): r for r in after_records}
    for match in before_matches:
        before = match["record"]
        after = index.get(_identity(before))
        if after is None or text_chunks(before) != text_chunks(after):
            raise RuntimeError("Formatting write completed, but read-back text/target changed. Do not retry blindly.")
        runs = [r for r in after["runs"] if r["start"] < match["end"] and r["end"] > match["start"]]
        if text and (not runs or any(not _same(r["style"], text) for r in runs)):
            raise RuntimeError("Formatting write completed, but text-style verification failed.")
        if "link" in style:
            for old in before["runs"]:
                start, end = max(old["start"], match["start"]), min(old["end"], match["end"])
                if start >= end:
                    continue
                overlapping = [r for r in after["runs"] if r["start"] < end and r["end"] > start]
                expected = link_preserved_styles(old, style)
                if not overlapping or any(not _same(r["style"], expected) for r in overlapping):
                    raise RuntimeError("Formatting write completed, but link edit changed unrelated color/underline.")
        paragraphs = [after] if kind == "docs" else [p for p in after["paragraphs"] if p["start"] < match["end"] and p["end"] > match["start"]]
        if paragraph and (not paragraphs or any(not _same(p["paragraph_style"], paragraph) for p in paragraphs)):
            raise RuntimeError("Formatting write completed, but paragraph-style verification failed.")
        if "list" in style and (not paragraphs or any(p.get("list_kind") != style["list"] for p in paragraphs)):
            raise RuntimeError("Formatting write completed, but list verification failed.")


def _fetch(kind, api, identifier):
    if kind == "docs":
        return api.documents().get(documentId=identifier, includeTabsContent=True).execute()
    return api.presentations().get(presentationId=identifier).execute()


def _selected(kind, data, args):
    records = doc_records(data) if kind == "docs" else slide_records(data)
    if kind == "docs" and args.tab_id:
        records = [r for r in records if r["tab_id"] == args.tab_id]
    if kind == "slides":
        if args.slide_id:
            records = [r for r in records if r["slide_id"] == args.slide_id]
        if args.element_id:
            records = [r for r in records if r["element_id"] == args.element_id]
    return records


def inspect(args, service):
    data = _fetch(args.kind, service(args.kind, "v1"), args.identifier)
    records = _selected(args.kind, data, args)
    if args.find:
        records = [r for r in records if any(args.find in text for _, text in text_chunks(r))]
    selected, used, truncated = [], 0, False
    for record in records:
        # Return only the style properties supported by this extension.
        record = json.loads(json.dumps(record))
        text_fields = {"bold", "italic", "underline", "fontFamily", "weightedFontFamily", "fontSize", "foregroundColor", "link"}
        paragraph_fields = {"namedStyleType", "alignment", "lineSpacing", "spaceAbove", "spaceBelow"}
        for run in record["runs"]:
            run["style"] = {k: v for k, v in run["style"].items() if k in text_fields}
            run.pop("explicit_style", None)
        for p in ([record] if args.kind == "docs" else record["paragraphs"]):
            p["paragraph_style"] = {k: v for k, v in p["paragraph_style"].items() if k in paragraph_fields}
        length = len(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
        if len(selected) >= args.max_items or used + length > args.max_chars:
            truncated = True
            break
        selected.append(record)
        used += length
    return {"id": args.identifier, "title": data.get("title"), "revision_id": data.get("revisionId"),
            "records": selected, "matching_records": len(records), "truncated": truncated,
            "scope": "body paragraphs, including tables and document tabs" if args.kind == "docs" else "shape and table-cell text"}


def format_content(args, service):
    if not args.confirm:
        raise ValueError("Formatting requires --confirm after user approval")
    style_file = getattr(args, "style_file", None)
    if style_file:
        payload = sys.stdin.read() if style_file == "-" else Path(style_file).read_text(encoding="utf-8-sig")
    else:
        payload = args.style
    if len(payload) > 65536:
        raise ValueError("Style JSON exceeds 64 KiB")
    style = json.loads(payload)
    style_requests(style, args.kind)
    api = service(args.kind, "v1")
    data = _fetch(args.kind, api, args.identifier)
    matches = locate(_selected(args.kind, data, args), args.find, args.all_matches)
    requests = make_requests(args.kind, matches, style)
    revision = data.get("revisionId")
    if not revision:
        raise RuntimeError("No revision ID returned; refusing an unguarded formatting write")
    body = {"requests": requests, "writeControl": {"requiredRevisionId": revision}}
    if args.kind == "docs":
        api.documents().batchUpdate(documentId=args.identifier, body=body).execute()
    else:
        api.presentations().batchUpdate(presentationId=args.identifier, body=body).execute()
    try:
        after = _fetch(args.kind, api, args.identifier)
        verify(args.kind, matches, _selected(args.kind, after, args), style)
    except Exception as exc:
        raise RuntimeError(f"Write succeeded; verification did not complete: {exc}") from exc
    return {"status": "formatting_verified", "id": args.identifier, "matches": len(matches),
            "properties": sorted(style), "visual_check": "not performed"}


def checked_output(workspace, output):
    raw_root = Path(workspace).expanduser().absolute()
    root = raw_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Workspace must be an existing directory")
    requested = Path(output).expanduser()
    if not requested.is_absolute():
        requested = raw_root / requested
    requested = requested.absolute()
    # Check lexical components too: a junction can resolve back inside the root.
    requested.relative_to(raw_root)
    for p in [requested, *requested.parents]:
        if p.exists() or p.is_symlink():
            info = p.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("Preview paths cannot use symlinks or junctions")
        if p == raw_root:
            break
    resolved = requested.resolve()
    resolved.relative_to(root)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def select_pages(value, total):
    if value is None:
        return list(range(1, min(total, 3) + 1))
    pages = set()
    for part in value.split(","):
        if not re.fullmatch(r"[1-9]\d*(?:-[1-9]\d*)?", part):
            raise ValueError("Pages must look like 1,3-5")
        ends = [int(x) for x in part.split("-")]
        start, end = ends[0], ends[-1]
        if start > end or end > total or end - start >= 20:
            raise ValueError("Invalid page range, or more than 20 pages requested")
        pages.update(range(start, end + 1))
    if len(pages) > 20:
        raise ValueError("Preview at most 20 pages per call")
    return sorted(pages)


def render_pdf(payload, output, pages=None, dpi=144):
    import pymupdf
    if not 72 <= dpi <= 200:
        raise ValueError("DPI must be between 72 and 200")
    if not isinstance(payload, bytes) or not payload.startswith(b"%PDF-"):
        raise ValueError("Export did not return a PDF")
    with pymupdf.open(stream=payload, filetype="pdf") as doc:
        selected = select_pages(pages, len(doc))
        for number in selected:
            rect = doc[number - 1].rect
            if rect.width * rect.height * (dpi / 72) ** 2 > 20_000_000:
                raise ValueError("Page dimensions exceed the preview pixel limit")
        folder = Path(tempfile.mkdtemp(prefix="docs-preview-", dir=output))
        (folder / "document.pdf").write_bytes(payload)
        files = []
        for number in selected:
            path = folder / f"page-{number:03}.png"
            doc[number - 1].get_pixmap(dpi=dpi, alpha=False).save(path)
            files.append(str(path))
        return {"pdf_path": str(folder / "document.pdf"), "images": files,
                "pages": selected, "total_pages": len(doc), "visual_check": "not performed"}


def download_png(url):
    if not url.startswith("https://"):
        raise ValueError("Thumbnail URL must use HTTPS")
    with urllib.request.urlopen(url, timeout=30) as response:
        if not response.geturl().startswith("https://"):
            raise ValueError("Thumbnail download redirected to a non-HTTPS URL")
        payload = response.read(20 * 1024 * 1024 + 1)
    if len(payload) > 20 * 1024 * 1024 or not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Thumbnail did not return a bounded PNG image")
    return payload


def preview(args, service):
    if args.kind == "docs":
        try:
            import pymupdf  # fail before network access if rendering dependency is missing
        except ImportError as exc:
            raise RuntimeError("Docs preview requires PyMuPDF in the selected Python. No export was attempted.") from exc
    output = checked_output(args.workspace_root, args.output_dir)
    if args.kind == "docs":
        payload = service("drive", "v3").files().export(fileId=args.identifier, mimeType="application/pdf").execute()
        return render_pdf(payload, output, args.pages, args.dpi)
    ids = list(dict.fromkeys(args.slide_id))
    if len(ids) > 10:
        raise ValueError("Preview at most 10 slides per call")
    api = service("slides", "v1")
    # Validate every selected slide before downloading or creating result files.
    deck = api.presentations().get(presentationId=args.identifier, fields="slides(objectId)").execute()
    available = {s["objectId"] for s in deck.get("slides", [])}
    if not set(ids) <= available:
        raise ValueError("Requested slide ID is not in this presentation")
    folder = Path(tempfile.mkdtemp(prefix="slides-preview-", dir=output))
    images = []
    for n, slide_id in enumerate(ids, 1):
        metadata = api.presentations().pages().getThumbnail(
            presentationId=args.identifier, pageObjectId=slide_id,
            thumbnailProperties_mimeType="PNG", thumbnailProperties_thumbnailSize="LARGE").execute()
        path = folder / f"slide-{n:03}.png"
        path.write_bytes(download_png(metadata["contentUrl"]))
        images.append({"slide_id": slide_id, "path": str(path), "width": metadata["width"], "height": metadata["height"]})
    return {"images": images, "visual_check": "not performed"}


def _bounded(low, high):
    def parse(value):
        number = int(value)
        if not low <= number <= high:
            raise argparse.ArgumentTypeError(f"Expected {low}–{high}")
        return number
    return parse


def register_commands(groups, service):
    """Add formatting and preview verbs to the existing docs/slides parser groups."""
    def emit_result(handler):
        def run(args):
            print(json.dumps(handler(args, service), ensure_ascii=False, separators=(",", ":")))
        return run
    for kind in ("docs", "slides"):
        parent = groups.choices[kind]
        sub = next(action for action in parent._actions if isinstance(action, argparse._SubParsersAction))
        for verb, handler in (("inspect", inspect), ("format", format_content), ("preview", preview)):
            p = sub.add_parser(verb, help=f"{kind} {verb}")
            p.add_argument("identifier")
            p.set_defaults(kind=kind, func=emit_result(handler))
            if verb != "preview":
                if kind == "docs":
                    p.add_argument("--tab-id")
                else:
                    p.add_argument("--slide-id", required=verb == "format")
                    p.add_argument("--element-id")
                p.add_argument("--find", required=verb == "format")
            if verb == "inspect":
                p.add_argument("--max-items", type=_bounded(1, 100), default=20)
                p.add_argument("--max-chars", type=_bounded(100, 30000), default=12000)
            elif verb == "format":
                style_input = p.add_mutually_exclusive_group(required=True)
                style_input.add_argument("--style", help="JSON formatting properties")
                style_input.add_argument("--style-file", help="JSON file, or - for standard input")
                p.add_argument("--all-matches", action="store_true")
                p.add_argument("--confirm", action="store_true")
            else:
                p.add_argument("--workspace-root", required=True)
                p.add_argument("--output-dir", required=True, help="Folder within workspace root")
                if kind == "slides":
                    p.add_argument("--slide-id", action="append", required=True)
                else:
                    p.add_argument("--pages", help="1-based pages, e.g. 1,3-4; default first three")
                    p.add_argument("--dpi", type=_bounded(72, 200), default=144)
