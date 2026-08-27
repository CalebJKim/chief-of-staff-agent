"""Hermes hook that enforces one Chief of Staff write per user turn.

The guard recognizes the repository-managed action wrapper and generic mutating
subcommands.  It deliberately knows nothing about demo people, subjects, file
IDs, slide names, tracker values, or seeded content.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from collections import OrderedDict
from difflib import SequenceMatcher
from email.utils import parseaddr
from typing import Any


_PLUGIN_NAME = "chief-of-staff-scope-guard"
_MAX_TRACKED_TURNS = 512
_SUCCESS_STATUSES = {"ok", "success", "completed"}
_MUTATION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bgmail\s+(?:draft|reply-draft)\b",
        r"\bcalendar\s+(?:create|move|reschedule)\b",
        r"\bdocs\s+(?:append|replace-text)\b",
        r"\bsheets\s+(?:update|set-cell)\b",
        r"\bslides\s+replace-text\b",
    )
)
_PREPARATION_PATTERN = re.compile(r"\bhelp\s+me\s+(?:get\s+)?prepare\b", re.IGNORECASE)
_DAILY_BRIEF_PATTERN = re.compile(
    r"\b(?:what\s+should\s+i\s+work\s+on\s+today|"
    r"(?:top|prioriti(?:ze|es))\b[^\r\n]{0,80}\btoday\b)",
    re.IGNORECASE,
)
_BULLET_SUMMARY_PATTERN = re.compile(
    r"(?=.*\b(?:summar(?:ize|y)|condense|recap)\b)(?=.*\b(?:bullet|bullets)\b)",
    re.IGNORECASE | re.DOTALL,
)
_WRITE_VERB = (
    r"(?:append\w*|chang\w*|creat\w*|draft\w*|edit\w*|email\w*|mark\w*|"
    r"mov\w*|put|replac\w*|repl(?:y|ies|ied|ying)|reschedul\w*|schedul\w*|"
    r"send\w*|set|updat\w*|writ\w*)"
)
_EXPLICIT_WRITE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        rf"^\s*(?:(?:hey\s+)?chief\s+of\s+staff[,:]?\s*)?(?:(?:please|kindly)\s+)?{_WRITE_VERB}\b",
        rf"\b(?:can|could|would|will)\s+you\s+(?:please\s+)?{_WRITE_VERB}\b",
        rf"\b(?:can|could)\s+we\s+(?:please\s+)?{_WRITE_VERB}\b",
        rf"\bi\s+(?:want|need|would\s+like|'d\s+like)\s+you\s+to\s+{_WRITE_VERB}\b",
        rf"\b(?:let['’]?s|go\s+ahead(?:\s+and)?)\s+(?:please\s+)?{_WRITE_VERB}\b",
        rf"\b(?:yes|yeah|yep|sure)[,:\s]+(?:please\s+)?{_WRITE_VERB}\b",
        rf"(?:[,;]|\bthen\b|\band\b)\s+(?:please\s+)?{_WRITE_VERB}\b",
        rf"\bhelp\s+me\b[^.!?\r\n]{{0,80}}\bby\s+{_WRITE_VERB}\b",
    )
)
_PREPARATION_COMPLETE_COMMAND = (
    'echo "PREPARATION_COMPLETE: Return the final numbered task list now with no more tool calls."'
)

_lock = threading.Lock()
_claims: "OrderedDict[str, str]" = OrderedDict()
_preparation_turns: "OrderedDict[str, str | None]" = OrderedDict()
_daily_brief_turns: "OrderedDict[str, int]" = OrderedDict()
_bullet_summary_turns: "OrderedDict[str, bool]" = OrderedDict()
_explicit_write_turns: "OrderedDict[str, bool]" = OrderedDict()
_pending_confirmations: "OrderedDict[str, str]" = OrderedDict()
_rejected_attempts: "OrderedDict[str, int]" = OrderedDict()
_pending_read_links: "OrderedDict[str, str]" = OrderedDict()
_preparation_links: "OrderedDict[str, list[tuple[str, str]]]" = OrderedDict()
_preparation_tasks: "OrderedDict[str, list[str]]" = OrderedDict()
_daily_brief_mail: "OrderedDict[str, dict[int, list[str]]]" = OrderedDict()
_allowed_urls: "OrderedDict[str, set[str]]" = OrderedDict()


def _command(args: Any) -> str:
    if not isinstance(args, dict):
        return ""
    for key in ("command", "cmd"):
        value = args.get(key)
        if isinstance(value, str):
            return value
    return ""


def _managed_mutation(tool_name: Any, args: Any) -> bool:
    if str(tool_name).casefold() != "terminal":
        return False
    command = _command(args)
    normalized = command.replace("\\", "/").casefold()
    if "action.sh" not in normalized or "chief-of-staff" not in normalized:
        return False
    return any(pattern.search(command) for pattern in _MUTATION_PATTERNS)


def _managed_helper(tool_name: Any, args: Any) -> bool:
    if str(tool_name).casefold() != "terminal":
        return False
    normalized = _command(args).replace("\\", "/").casefold()
    return "action.sh" in normalized and "chief-of-staff" in normalized


def _managed_doc_read(tool_name: Any, args: Any) -> bool:
    return _managed_helper(tool_name, args) and bool(
        re.search(r"\bdocs\s+get\b", _command(args), re.IGNORECASE)
    )


def _managed_start_day(tool_name: Any, args: Any) -> bool:
    if str(tool_name).casefold() != "terminal":
        return False
    normalized = _command(args).replace("\\", "/").casefold()
    return "chief-of-staff/scripts/start_day.sh" in normalized


def _focused_thread_read_args(args: Any) -> dict[str, Any] | None:
    """Strip unsupported trailing arguments from a focused Gmail thread read."""

    if not isinstance(args, dict):
        return None
    command = _command(args)
    match = re.match(
        r"^(.*?action\.sh[\"']?\s+gmail\s+thread\s+)([A-Za-z0-9_-]+)",
        command,
        flags=re.IGNORECASE,
    )
    if not match or not command[match.end() :].strip():
        return None
    updated = dict(args)
    key = "command" if isinstance(args.get("command"), str) else "cmd"
    updated[key] = f"{match.group(1)}{match.group(2)}"
    return updated


def _read_only_preparation(user_message: Any) -> bool:
    if isinstance(user_message, dict):
        user_message = user_message.get("content", user_message)
    text = user_message if isinstance(user_message, str) else str(user_message or "")
    return bool(_PREPARATION_PATTERN.search(text)) and not _explicit_write_request(text)


def _explicit_write_request(user_message: Any) -> bool:
    """Return whether the current user message directly requests a write.

    Authorization comes only from the current user's words. Workspace content,
    prior plans, and a helper command's mutation verb cannot grant it.
    """

    if isinstance(user_message, dict):
        user_message = user_message.get("content", user_message)
    text = user_message if isinstance(user_message, str) else str(user_message or "")
    return any(pattern.search(text) for pattern in _EXPLICIT_WRITE_PATTERNS)


def _daily_brief(user_message: Any) -> bool:
    if isinstance(user_message, dict):
        user_message = user_message.get("content", user_message)
    text = user_message if isinstance(user_message, str) else str(user_message or "")
    return bool(_DAILY_BRIEF_PATTERN.search(text))


def _daily_brief_limit(user_message: Any) -> int:
    """Return the requested daily-brief size, using the documented default."""

    if isinstance(user_message, dict):
        user_message = user_message.get("content", user_message)
    text = user_message if isinstance(user_message, str) else str(user_message or "")
    match = re.search(
        r"\btop\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return 3
    words = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    }
    value = match.group(1).casefold()
    return max(1, int(value) if value.isdigit() else words[value])


def _bullet_summary(user_message: Any) -> bool:
    if isinstance(user_message, dict):
        user_message = user_message.get("content", user_message)
    text = user_message if isinstance(user_message, str) else str(user_message or "")
    return bool(_BULLET_SUMMARY_PATTERN.search(text))


def _scope_id(kwargs: dict[str, Any]) -> str:
    return str(kwargs.get("session_id") or kwargs.get("task_id") or "").strip()


def _call_token(kwargs: dict[str, Any]) -> str:
    opaque_id = str(kwargs.get("tool_call_id") or kwargs.get("api_request_id") or "").strip()
    if opaque_id:
        return opaque_id
    command = _command(kwargs.get("args"))
    return hashlib.sha256(command.encode("utf-8")).hexdigest()


def _remember(scope_id: str, token: str) -> None:
    _claims[scope_id] = token
    _claims.move_to_end(scope_id)
    while len(_claims) > _MAX_TRACKED_TURNS:
        _claims.popitem(last=False)


def _remember_confirmation(session_id: str, confirmation: str) -> None:
    _pending_confirmations[session_id] = confirmation
    _pending_confirmations.move_to_end(session_id)
    while len(_pending_confirmations) > _MAX_TRACKED_TURNS:
        _pending_confirmations.popitem(last=False)


def _remember_read_link(session_id: str, result: Any) -> None:
    parsed = _result_payload(result)
    if not parsed:
        return
    url = parsed.get("url")
    if not isinstance(url, str) or not url.startswith("https://docs.google.com/document/"):
        return
    title = parsed.get("title")
    label = title.strip() if isinstance(title, str) and title.strip() else "Google Doc"
    _pending_read_links[session_id] = f"[{label}]({url})"
    _pending_read_links.move_to_end(session_id)
    while len(_pending_read_links) > _MAX_TRACKED_TURNS:
        _pending_read_links.popitem(last=False)


def _result_payload(result: Any) -> dict[str, Any] | None:
    if not isinstance(result, str):
        return None
    try:
        parsed = json.loads(result)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    output = parsed.get("output")
    if isinstance(output, str):
        try:
            nested = json.loads(output)
        except (TypeError, ValueError):
            nested = None
        if isinstance(nested, dict):
            return nested
    return parsed


def _terminal_result_succeeded(result: Any) -> bool:
    if not isinstance(result, str):
        return False
    try:
        parsed = json.loads(result)
    except (TypeError, ValueError):
        return False
    if not isinstance(parsed, dict):
        return False
    exit_code = parsed.get("exit_code")
    return exit_code in {None, 0} and not parsed.get("error")


def _confirmation_markdown(result: Any) -> str | None:
    parsed = _result_payload(result)
    if parsed is None:
        return None
    confirmation = parsed.get("confirmation_markdown")
    if isinstance(confirmation, str) and confirmation.strip():
        return confirmation
    return None


def _result_status(result: Any) -> str:
    parsed = _result_payload(result)
    return str(parsed.get("status") or "").strip().casefold() if parsed else ""


def _temporary_google_message(result: Any) -> str | None:
    parsed = _result_payload(result)
    if not parsed or _result_status(result) != "temporarily_unavailable":
        return None
    message = parsed.get("user_message")
    return message.strip() if isinstance(message, str) and message.strip() else None


def _prewrite_rejection(result: Any) -> bool:
    parsed = _result_payload(result)
    if not parsed or _result_status(result) != "rejected":
        return False
    return any(parsed.get(field) is False for field in ("created", "moved", "updated"))


def _daily_brief_mail_links(result: Any) -> dict[int, list[str]]:
    parsed = _result_payload(result)
    if not parsed:
        return {}
    links: dict[int, list[str]] = {}
    for item in parsed.get("mail", []):
        if not isinstance(item, dict):
            continue
        order = item.get("selection_order") or item.get("supports_selection_order")
        if not isinstance(order, int) or order < 1:
            continue
        url = item.get("url")
        sender = item.get("from")
        if not isinstance(url, str) or not url.startswith("https://mail.google.com/"):
            continue
        if not isinstance(sender, str):
            continue
        name, address = parseaddr(sender)
        label = name.strip() or address.strip()
        if label:
            links.setdefault(order, []).append(f"[Mail — {label}]({url})")
    return links


def _result_urls(result: Any) -> set[str]:
    parsed = _result_payload(result)
    urls: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, str):
            urls.update(
                match.rstrip(".,;)")
                for match in re.findall(r"https://[^\s<>\"\\]+", value)
            )
        elif isinstance(value, dict):
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    if parsed:
        collect(parsed)
    return urls


def _url_kind(url: str) -> str:
    for marker in (
        "docs.google.com/document/",
        "docs.google.com/presentation/",
        "docs.google.com/spreadsheets/",
        "drive.google.com/drive/",
        "mail.google.com/mail/",
        "google.com/calendar/",
    ):
        if marker in url:
            return marker
    return ""


def _repair_workspace_urls(response_text: Any, allowed_urls: set[str] | None) -> Any:
    """Repair only a strong, unique near-match to a live Google URL."""
    if not isinstance(response_text, str) or not allowed_urls:
        return response_text

    def replace(match: re.Match[str]) -> str:
        url = match.group(2)
        if url in allowed_urls:
            return match.group(0)
        kind = _url_kind(url)
        candidates = [candidate for candidate in allowed_urls if _url_kind(candidate) == kind]
        if not kind or not candidates:
            return match.group(0)
        ranked = sorted(
            ((SequenceMatcher(None, url, candidate).ratio(), candidate) for candidate in candidates),
            reverse=True,
        )
        best_score, best_url = ranked[0]
        runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
        if best_score < 0.92 or best_score - runner_up < 0.05:
            return match.group(0)
        return f"{match.group(1)}{best_url}{match.group(3)}"

    return re.sub(r"(\[[^\]]+\]\()(https://[^)\s]+)(\))", replace, response_text)


def _word_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", value.casefold())
        if token not in {
            "and", "for", "from", "into", "once", "that", "the", "then", "this",
            "use", "with", "your",
        }
    }


def _labeled_workspace_links(result: Any) -> list[tuple[str, str]]:
    """Extract exact live resource links and their evidence-supplied labels."""
    parsed = _result_payload(result)
    if not parsed:
        return []
    strings: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, str):
            strings.append(value)
        elif isinstance(value, dict):
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(parsed)
    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for value in strings:
        previous = ""
        for line in value.splitlines():
            stripped = line.strip()
            for match in re.finditer(r"https://[^\s<>\"\\]+", stripped):
                url = match.group(0).rstrip(".,;)")
                kind = _url_kind(url)
                if not kind or kind == "mail.google.com/mail/" or url in seen:
                    continue
                prefix = stripped[:match.start()].strip(" \t:-")
                label = prefix or previous.strip(" \t:-") or "Workspace resource"
                label = re.sub(r"[\[\]]", "", label).strip()
                links.append((label, url))
                seen.add(url)
            if stripped:
                previous = stripped
    return links


def _explicit_requested_tasks(result: Any) -> list[str]:
    """Extract conservative English request clauses from focused live mail."""
    parsed = _result_payload(result)
    if not parsed:
        return []
    messages = parsed.get("messages", [])
    if not isinstance(messages, list):
        return []
    tasks: list[str] = []
    patterns = (
        r"\bplease\s+(.+)$",
        r"^(?:then|next|afterward)\s+(.+)$",
        r"^(?:once|after|when)\b[^,]*,\s*(.+)$",
        r"^(?:could|can|would)\s+you\s+(.+)$",
        r"\bi\s+need\s+you\s+to\s+(.+)$",
    )
    for message in messages:
        if not isinstance(message, dict):
            continue
        body = str(message.get("body", ""))
        prose = " ".join(
            line.strip()
            for line in body.splitlines()
            if line.strip() and "https://" not in line and not line.strip().startswith("[")
        )
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", prose):
            sentence = sentence.strip()
            for pattern in patterns:
                match = re.search(pattern, sentence, flags=re.IGNORECASE)
                if not match:
                    continue
                task = match.group(1).strip().rstrip(".!?")
                if task and task.casefold() not in {item.casefold() for item in tasks}:
                    tasks.append(task[0].upper() + task[1:])
                break
    return tasks


def _numbered_tasks_only(
    response_text: Any,
    live_links: list[tuple[str, str]] | None = None,
    requested_tasks: list[str] | None = None,
) -> str | None:
    if not isinstance(response_text, str):
        return None
    if requested_tasks:
        tasks = [[str(index), task] for index, task in enumerate(requested_tasks, 1)]
    else:
        matches = re.findall(r"(?m)^\s*(\d+)\.\s+([^\r\n]+)", response_text)
        if not matches:
            return None
        numbers = [int(number) for number, _text in matches]
        if numbers != list(range(1, len(numbers) + 1)):
            return None
        tasks = [[number, text.strip()] for number, text in matches]
    used_urls = set(
        re.findall(r"https://[^)\s]+", "\n".join(task[1] for task in tasks))
    )
    for task in tasks:
        if re.search(r"https://[^)\s]+", task[1]):
            continue
        task_tokens = _word_tokens(task[1])
        ranked = sorted(
            (
                (len(task_tokens & _word_tokens(label)), -index, label, url)
                for index, (label, url) in enumerate(live_links or [])
                if url not in used_urls
            ),
            reverse=True,
        )
        if not ranked or ranked[0][0] < 1:
            continue
        _score, _source_order, label, url = ranked[0]
        task[1] = f"{task[1]} [{label}]({url})"
        used_urls.add(url)
    return "\n".join(f"{number}. {text}" for number, text in tasks)


def _bullet_summary_only(response_text: Any) -> str | None:
    """Normalize a requested prose summary into sentence-level bullets."""
    if not isinstance(response_text, str):
        return None
    if len(re.findall(r"(?m)^\s*[-*]\s+\S", response_text)) >= 2:
        return response_text
    links = [
        f"[{label}]({url})"
        for label, url in re.findall(r"\[([^\]]+)\]\((https://[^)\s]+)\)", response_text)
    ]
    prose = re.sub(r"\[[^\]]+\]\(https://[^)\s]+\)", "", response_text)
    prose = re.sub(
        r"^\s*(?:here(?:'s| is)\s+)?(?:a\s+)?(?:concise\s+)?summary[^:]*:\s*",
        "",
        prose,
        flags=re.IGNORECASE,
    )
    prose = re.sub(r"\s+", " ", prose).strip()
    numbered = list(re.finditer(r"(?<![A-Za-z0-9])(\d+)[.)]\s*", prose))
    if len(numbered) >= 2:
        numbers = [int(match.group(1)) for match in numbered]
        if numbers == list(range(1, len(numbers) + 1)):
            items = [
                prose[match.end() : numbered[index + 1].start() if index + 1 < len(numbered) else len(prose)].strip()
                for index, match in enumerate(numbered)
            ]
            if all(items):
                rendered = [f"- {item}" for item in items]
                for link in dict.fromkeys(links):
                    rendered.extend(("", link))
                return "\n".join(rendered)
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", prose)
        if sentence.strip()
    ]
    if len(sentences) < 2:
        return response_text
    rendered = [f"- {sentence}" for sentence in sentences]
    for link in dict.fromkeys(links):
        rendered.extend(("", link))
    return "\n".join(rendered)


def _daily_heading(line: str) -> tuple[int, str, str] | None:
    patterns = (
        r"^\s*(\d+)\.\s+\*\*(.+?)\*\*(?:\s*(?:\u2014|-)\s*(.+))?\s*$",
        r"^\s*\*\*(\d+)\.\s+(.+?)\*\*(?:\s*(?:\u2014|-)\s*(.+))?\s*$",
        r"^\s*(\d+)\.\s+([^\r\n]+?)\s*$",
    )
    for pattern in patterns:
        match = re.match(pattern, line)
        if match:
            context = match.group(3).strip() if match.lastindex and match.lastindex >= 3 and match.group(3) else ""
            return int(match.group(1)), match.group(2).strip(" *"), context
    return None


def _compact_daily_context(context: str, mail_links: list[str]) -> str:
    context = re.sub(
        r"^\s*-\s*(?:(?:\*\*)?Context:(?:\*\*)?\s*)?",
        "",
        context,
        flags=re.IGNORECASE,
    )
    markdown_links = re.findall(r"\[([^\]]+)\]\((https://[^)\s]+)\)", context)
    model_mail_links = [
        f"[{label}]({url})"
        for label, url in markdown_links
        if label.casefold().startswith("mail") or _url_kind(url) == "mail.google.com/mail/"
    ]
    resource_link = next(
        (
            f"[{label}]({url})"
            for label, url in markdown_links
            if not label.casefold().startswith("mail")
            and _url_kind(url) != "mail.google.com/mail/"
        ),
        "",
    )
    prose = re.sub(r"\s*\[[^\]]+\]\(https://[^)\s]+\)", "", context)
    prose = re.sub(r"\s+", " ", prose).strip()
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", prose)
    prose = " ".join(sentences[:2]).strip()
    additions = ([resource_link] if resource_link else []) + (mail_links or model_mail_links)
    return " ".join([prose, *additions]).strip()


def _daily_brief_only(
    response_text: Any,
    mail_links: dict[int, list[str]] | None = None,
    max_items: int = 3,
) -> str | None:
    """Normalize a model-rendered brief without interpreting or reranking it."""
    if not isinstance(response_text, str):
        return None
    lines = response_text.splitlines()
    if not any((heading := _daily_heading(line)) and heading[0] == 1 for line in lines):
        numbered_lines = list(lines)
        next_number = 1
        for index, line in enumerate(lines):
            inline_item = re.match(r"^\s*\*\*(.+?)\*\*\s+(.+?)\s*$", line)
            if inline_item:
                numbered_lines[index] = (
                    f"{next_number}. **{inline_item.group(1).strip()}** — "
                    f"{inline_item.group(2).strip()}"
                )
                next_number += 1
                continue
            if not line.strip():
                continue
            next_line = next(
                (candidate.strip() for candidate in lines[index + 1:] if candidate.strip()),
                "",
            )
            if not re.match(
                r"^-\s+.+$",
                next_line,
            ):
                continue
            title = line.strip()
            if not re.match(r"^\*\*.+?\*\*$", title):
                title = f"**{title}**"
            numbered_lines[index] = f"{next_number}. {title}"
            next_number += 1
        lines = numbered_lines
    headings = [
        (index, heading)
        for index, line in enumerate(lines)
        if (heading := _daily_heading(line)) is not None
    ]
    first_item = next(
        (index for index, heading in headings if heading[0] == 1),
        None,
    )
    if first_item is None:
        return None
    opening = next(
        (line.strip() for line in lines[:first_item] if line.strip()),
        "Here are your priorities for today:",
    )
    items: list[tuple[int, str, str]] = []
    for heading_index, (line_index, heading) in enumerate(headings):
        number, title, context = heading
        if not context:
            end_index = headings[heading_index + 1][0] if heading_index + 1 < len(headings) else len(lines)
            paragraph: list[str] = []
            for candidate in lines[line_index + 1:end_index]:
                stripped = candidate.strip()
                if not stripped:
                    if paragraph:
                        break
                    continue
                paragraph.append(stripped)
            context = " ".join(paragraph)
        if not context:
            return None
        context = _compact_daily_context(context, (mail_links or {}).get(number, []))
        items.append((number, title, context))
    items = items[:max_items]
    numbers = [number for number, _title, _context in items]
    if numbers != list(range(1, len(numbers) + 1)):
        return None
    rendered = [opening]
    for number, title, context in items:
        rendered.extend(("", f"{number}. **{title}**", f"   - **Context:** {context}"))
    return "\n".join(rendered)


def pre_llm_call(**kwargs: Any) -> dict[str, str] | None:
    """Start a fresh authorization boundary for each user message."""
    scope_id = _scope_id(kwargs)
    if not scope_id:
        return
    with _lock:
        _pending_confirmations.pop(scope_id, None)
        _claims.pop(scope_id, None)
        _preparation_turns.pop(scope_id, None)
        _daily_brief_turns.pop(scope_id, None)
        _bullet_summary_turns.pop(scope_id, None)
        _explicit_write_turns.pop(scope_id, None)
        _rejected_attempts.pop(scope_id, None)
        _pending_read_links.pop(scope_id, None)
        _preparation_links.pop(scope_id, None)
        _preparation_tasks.pop(scope_id, None)
        _daily_brief_mail.pop(scope_id, None)
        _allowed_urls.pop(scope_id, None)
        if _daily_brief(kwargs.get("user_message")):
            _daily_brief_turns[scope_id] = _daily_brief_limit(kwargs.get("user_message"))
            _daily_brief_turns.move_to_end(scope_id)
            while len(_daily_brief_turns) > _MAX_TRACKED_TURNS:
                _daily_brief_turns.popitem(last=False)
        if _bullet_summary(kwargs.get("user_message")):
            _bullet_summary_turns[scope_id] = True
            _bullet_summary_turns.move_to_end(scope_id)
            while len(_bullet_summary_turns) > _MAX_TRACKED_TURNS:
                _bullet_summary_turns.popitem(last=False)
        if _explicit_write_request(kwargs.get("user_message")):
            _explicit_write_turns[scope_id] = True
            _explicit_write_turns.move_to_end(scope_id)
            while len(_explicit_write_turns) > _MAX_TRACKED_TURNS:
                _explicit_write_turns.popitem(last=False)
        if _read_only_preparation(kwargs.get("user_message")):
            _preparation_turns[scope_id] = None
            _preparation_turns.move_to_end(scope_id)
            while len(_preparation_turns) > _MAX_TRACKED_TURNS:
                _preparation_turns.popitem(last=False)
            return {
                "context": (
                    "Chief of Staff scope guard: this is a read-only preparation request. "
                    "Do not answer from prior summaries. Make exactly one focused action.sh "
                    "gmail thread read for the primary message, then return only the tasks the "
                    "sender explicitly asks the recipient to do, in the same order, with one "
                    "numbered line per task and useful links already in that message. Do not "
                    "turn a stated date, time, or scheduled event into a task unless the sender "
                    "explicitly asks the recipient to schedule or attend it. Do not open linked "
                    "files, add other context, or end with a question or offer."
                )
            }
    return {
        "context": (
            "Chief of Staff scope guard: this user message starts a new authorization "
            "boundary. Any read-only, stop-after-write, or tool-limit instruction from a "
            "prior user message is historical and does not restrict the current request. "
            "Follow the current request and the Chief of Staff skill."
        )
    }


def pre_tool_call(**kwargs: Any) -> dict[str, str] | None:
    scope_id = _scope_id(kwargs)
    token = _call_token(kwargs)
    if scope_id and _managed_helper(kwargs.get("tool_name"), kwargs.get("args")):
        with _lock:
            if scope_id in _preparation_turns:
                claimed_read = _preparation_turns[scope_id]
                if _managed_mutation(kwargs.get("tool_name"), kwargs.get("args")):
                    return {
                        "action": "block",
                        "message": (
                            "Chief of Staff scope guard: this is a read-only preparation turn. "
                            "Do not make a Workspace change. Return only the explicit tasks from "
                            "the focused evidence already read."
                        ),
                    }
                if claimed_read is None:
                    _preparation_turns[scope_id] = token
                    sanitized = _focused_thread_read_args(kwargs.get("args"))
                    if sanitized:
                        return {"action": "modify", "args": sanitized}
                    return None
                if claimed_read == token:
                    return None
                return {
                    "action": "modify",
                    "args": {
                        "command": _PREPARATION_COMPLETE_COMMAND,
                        "timeout": 5,
                    },
                }
    if not _managed_mutation(kwargs.get("tool_name"), kwargs.get("args")):
        return None
    if not scope_id:
        return {
            "action": "block",
            "message": (
                "Chief of Staff scope guard: this Workspace write has no current user "
                "authorization boundary, so it was not run."
            ),
        }
    with _lock:
        if scope_id not in _explicit_write_turns:
            return {
                "action": "block",
                "message": (
                    "Chief of Staff scope guard: the current user message did not explicitly "
                    "request a Workspace change, so this write was not run. Return the "
                    "read-only result or plan and wait for a specific write request."
                ),
            }
        claimed = _claims.get(scope_id)
        if claimed is None:
            _remember(scope_id, token)
            return None
        if claimed == token:
            return None
    return {
        "action": "block",
        "message": (
            "Chief of Staff scope guard: a Workspace write already ran in this user turn. "
            "Do not run another tool. Return the first write's verified confirmation only; "
            "the user can request the next change in a separate message."
        ),
    }


def post_tool_call(**kwargs: Any) -> None:
    managed_mutation = _managed_mutation(kwargs.get("tool_name"), kwargs.get("args"))
    managed_helper = _managed_helper(kwargs.get("tool_name"), kwargs.get("args"))
    if not managed_mutation and not managed_helper:
        return
    scope_id = _scope_id(kwargs)
    if not scope_id:
        return
    status = str(kwargs.get("status") or "").casefold()
    if status in _SUCCESS_STATUSES:
        return
    token = _call_token(kwargs)
    with _lock:
        if scope_id in _preparation_turns and _preparation_turns.get(scope_id) == token:
            _preparation_turns[scope_id] = None
        if _claims.get(scope_id) == token:
            _claims.pop(scope_id, None)


def transform_tool_result(**kwargs: Any) -> str | None:
    scope_id = _scope_id(kwargs)
    if not scope_id:
        return None
    status = str(kwargs.get("status") or "").casefold()
    if status not in _SUCCESS_STATUSES:
        return None
    token = _call_token(kwargs)
    result = str(kwargs.get("result") or "")
    if _managed_start_day(kwargs.get("tool_name"), kwargs.get("args")):
        mail_links = _daily_brief_mail_links(result)
        result_urls = _result_urls(result)
        if mail_links or result_urls:
            with _lock:
                if mail_links:
                    _daily_brief_mail[scope_id] = mail_links
                    _daily_brief_mail.move_to_end(scope_id)
                    while len(_daily_brief_mail) > _MAX_TRACKED_TURNS:
                        _daily_brief_mail.popitem(last=False)
                if result_urls:
                    _allowed_urls[scope_id] = result_urls
                    _allowed_urls.move_to_end(scope_id)
                    while len(_allowed_urls) > _MAX_TRACKED_TURNS:
                        _allowed_urls.popitem(last=False)
    temporary_message = _temporary_google_message(result)
    if temporary_message and _managed_helper(kwargs.get("tool_name"), kwargs.get("args")):
        return (
            result
            + "\n\n[Chief of Staff scope guard]\n"
            + "Google Workspace remained unavailable after bounded retries. Make no more "
            + "tool calls in this turn. Return the user_message from this result exactly as "
            + "the entire final answer."
        )
    if _managed_helper(kwargs.get("tool_name"), kwargs.get("args")):
        result_urls = _result_urls(result)
        if result_urls:
            with _lock:
                _allowed_urls[scope_id] = result_urls
                _allowed_urls.move_to_end(scope_id)
                while len(_allowed_urls) > _MAX_TRACKED_TURNS:
                    _allowed_urls.popitem(last=False)
        if _managed_doc_read(kwargs.get("tool_name"), kwargs.get("args")):
            with _lock:
                _remember_read_link(scope_id, result)
        with _lock:
            explicit_write = scope_id in _explicit_write_turns
        if (
            explicit_write
            and not _managed_mutation(kwargs.get("tool_name"), kwargs.get("args"))
            and _terminal_result_succeeded(result)
        ):
            return (
                result
                + "\n\n[Chief of Staff scope guard]\n"
                + "The current user explicitly requested one Workspace change, so that scoped "
                + "change is already authorized. Use this successful live read to execute exactly "
                + "one matching managed mutation now. Do not ask for confirmation, merely describe "
                + "a planned change, or offer to do it later."
            )
        with _lock:
            preparation_read = _preparation_turns.get(scope_id) == token
        if preparation_read:
            live_links = _labeled_workspace_links(result)
            requested_tasks = _explicit_requested_tasks(result)
            if live_links:
                with _lock:
                    _preparation_links[scope_id] = live_links
                    _preparation_links.move_to_end(scope_id)
                    while len(_preparation_links) > _MAX_TRACKED_TURNS:
                        _preparation_links.popitem(last=False)
            if requested_tasks:
                with _lock:
                    _preparation_tasks[scope_id] = requested_tasks
                    _preparation_tasks.move_to_end(scope_id)
                    while len(_preparation_tasks) > _MAX_TRACKED_TURNS:
                        _preparation_tasks.popitem(last=False)
            return (
                str(kwargs.get("result") or "")
                + "\n\n[Chief of Staff scope guard]\n"
                + "The single allowed evidence read is complete. Your next response must be the "
                + "final answer with zero tool calls. This is a read-only preparation request; "
                + "use only this result. Return only the tasks the sender explicitly asks the recipient "
                + "to do, in the same order, with one numbered item per task and existing useful "
                + "links. A stated date, time, or event is context unless the sender explicitly "
                + "asks the recipient to schedule or attend it. Do not inspect status or permissions. "
                + "Do not open linked files, summarize their contents, add optional work, ask a closing "
                + "question, or call another tool. Return the final numbered list now."
            )
    if not _managed_mutation(kwargs.get("tool_name"), kwargs.get("args")):
        return None
    with _lock:
        if _claims.get(scope_id) != token:
            return None
    if _prewrite_rejection(result):
        with _lock:
            rejected_attempts = _rejected_attempts.get(scope_id, 0) + 1
            _rejected_attempts[scope_id] = rejected_attempts
            _rejected_attempts.move_to_end(scope_id)
            if rejected_attempts == 1 and _claims.get(scope_id) == token:
                _claims.pop(scope_id, None)
        if rejected_attempts == 1:
            return (
                result
                + "\n\n[Chief of Staff scope guard]\n"
                + "No Workspace write occurred. Correct only the rejected arguments using "
                + "the reason in this result, then retry the same requested write once."
            )
        return (
            result
            + "\n\n[Chief of Staff scope guard]\n"
            + "No Workspace write occurred after the one allowed correction. Make no more "
            + "tool calls; briefly explain the reason from this result to the user."
        )
    confirmation = _confirmation_markdown(result)
    if confirmation:
        with _lock:
            _remember_confirmation(scope_id, confirmation)
    return (
        result
        + "\n\n[Chief of Staff scope guard]\n"
        + "The requested Workspace write succeeded, so this user turn is complete. "
        + "Make no more tool calls. Return confirmation_markdown from this result "
        + "exactly as the entire final answer."
    )


def transform_llm_output(**kwargs: Any) -> str | None:
    """Return only the helper's verified confirmation after a guarded write."""
    scope_id = _scope_id(kwargs)
    if not scope_id:
        return None
    with _lock:
        confirmation = _pending_confirmations.pop(scope_id, None)
        read_link = _pending_read_links.pop(scope_id, None)
        preparation = scope_id in _preparation_turns
        preparation_links = _preparation_links.pop(scope_id, None)
        preparation_tasks = _preparation_tasks.pop(scope_id, None)
        daily_brief_limit = _daily_brief_turns.pop(scope_id, None)
        bullet_summary = scope_id in _bullet_summary_turns
        daily_brief_mail = _daily_brief_mail.pop(scope_id, None)
        allowed_urls = _allowed_urls.pop(scope_id, None)
        _preparation_turns.pop(scope_id, None)
        _bullet_summary_turns.pop(scope_id, None)
        _explicit_write_turns.pop(scope_id, None)
    if confirmation:
        return confirmation
    response_text = _repair_workspace_urls(kwargs.get("response_text"), allowed_urls)
    if bullet_summary:
        response_text = _bullet_summary_only(response_text)
    if read_link and isinstance(response_text, str):
        url = re.search(r"\((https://docs\.google\.com/document/[^)]+)\)", read_link)
        if url and url.group(1) not in response_text:
            return f"{response_text.rstrip()}\n\n{read_link}"
    if preparation:
        return _numbered_tasks_only(response_text, preparation_links, preparation_tasks)
    if daily_brief_limit is not None:
        return _daily_brief_only(response_text, daily_brief_mail, daily_brief_limit)
    return None


def register(ctx: Any) -> None:
    ctx.register_hook("pre_llm_call", pre_llm_call)
    ctx.register_hook("pre_tool_call", pre_tool_call)
    ctx.register_hook("post_tool_call", post_tool_call)
    ctx.register_hook("transform_tool_result", transform_tool_result)
    ctx.register_hook("transform_llm_output", transform_llm_output)


def _reset_state_for_tests() -> None:
    with _lock:
        _claims.clear()
        _preparation_turns.clear()
        _daily_brief_turns.clear()
        _bullet_summary_turns.clear()
        _explicit_write_turns.clear()
        _pending_confirmations.clear()
        _rejected_attempts.clear()
        _pending_read_links.clear()
        _preparation_links.clear()
        _preparation_tasks.clear()
        _daily_brief_mail.clear()
        _allowed_urls.clear()
