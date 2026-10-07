"""ID-preserving demo resets. Google operations use the seeder's bounded batches."""
from collections import Counter
from datetime import date, datetime
from email.utils import getaddresses
import json
import re
from types import SimpleNamespace


def pages(request, key, **kwargs):
    result = []
    while True:
        page = request(**kwargs).execute()
        result.extend(page.get(key, []))
        if not page.get("nextPageToken"):
            return result
        kwargs["pageToken"] = page["nextPageToken"]


def evidence_from_state(state):
    evidence = {}
    for index, item in enumerate(state["emails"]):
        key = item.get("evidence_key") or item.get("news_key") or item.get("task_key")
        if not key and index < 6:
            key = ("elena", "mike", "aisha", "daniel", "priya", "prd")[index]
        if key:
            evidence[key] = item["url"]
    return evidence


def calendar_baseline(seed, state, week, reference_day):
    counts = Counter()
    result = []
    for day, begin, end, title, description in seed.calendar_event_specs(
            week, state["slides"]["url"], state["doc"]["url"], state["sheet"]["url"],
            reference_day=reference_day):
        counts[title] += 1
        result.append({"seed_key": f"{title}#{counts[title]}", "baseline": {
            "summary": title, "description": f"{description}\n[{seed.MARKER}]",
            "start": {"dateTime": seed.iso(day, begin), "timeZone": seed.TZ_NAME},
            "end": {"dateTime": seed.iso(day, end), "timeZone": seed.TZ_NAME},
        }})
    return result


def _missing(label):
    raise RuntimeError(f"Quick reset cannot preserve missing or inconsistent {label}. Run --full-reset. No reset writes started.")


def reconcile_email_ids(seed, gmail, state, found_ids):
    """Resolve stale import IDs by exact RFC Message-ID, never subject similarity."""
    missing = [(i, item) for i, item in enumerate(state["emails"]) if item["id"] not in found_ids]
    if not missing:
        return

    def header(message):
        return next((h["value"] for h in message.get("payload", {}).get("headers", [])
                     if h["name"].lower() == "message-id"), None)

    def read(message_id):
        return gmail.users().messages().get(userId="me", id=message_id,
            format="metadata", metadataHeaders=["Message-ID"])

    # Older states did not save RFC IDs. Recover the import-run identifier from
    # a surviving original message, verifying its ordinal before using it.
    run = None
    for i, item in enumerate(state["emails"][:6]):
        if item["id"] in found_ids:
            rfc = header(read(item["id"]).execute())
            match = re.fullmatch(r"<" + re.escape(seed.MARKER) + r"-([0-9a-f]{32})-(\d+)@demo\.invalid>", rfc or "")
            if match and int(match[2]) == i + 1:
                run = match[1]
                break
    expected = {}
    for i, item in missing:
        rfc = item.get("rfc_message_id") or (f"<{seed.MARKER}-{run}-{i + 1}@demo.invalid>" if run else None)
        if not rfc:
            _missing("emails (no exact Message-ID available for recovery)")
        expected[rfc] = item
    # Inspect only IDs not already accounted for. This avoids search-index
    # timing and does not read email bodies or modify Gmail.
    candidates = sorted(found_ids - {item["id"] for item in state["emails"]})
    matches = {}
    for message in seed.execute_batched(gmail, [read(message_id) for message_id in candidates]):
        rfc = header(message)
        if rfc in expected:
            matches.setdefault(rfc, []).append(message)
    if any(len(matches.get(rfc, [])) != 1 for rfc in expected):
        _missing("emails (exact Message-ID missing or ambiguous)")
    repairs = []
    for rfc, item in expected.items():
        message = matches[rfc][0]
        repairs.append({"previous_id": item["id"], "id": message["id"]})
        item.update(id=message["id"], thread_id=message["threadId"],
                    url=f"https://mail.google.com/mail/u/0/#all/{message['threadId']}", rfc_message_id=rfc)
    state["email_id_repairs"] = repairs


def preflight(seed, svc, state, *, full_reset):
    """Validate before any writes; migrate legacy event records without new IDs."""
    if not full_reset and state.get("reset_incomplete"):
        _missing("state from an interrupted reset")
    for key in ("folder", "slides", "sheet", "doc"):
        if not state.get(key, {}).get("id"):
            raise RuntimeError(f"Missing {key} ID in demo state; restore the state file before resetting.")
    resources = [state[k] for k in ("folder", "slides", "sheet", "doc")]
    resources += list(state.get("task_resources", {}).values())
    if state.get("original_sheet"):
        resources.append(state["original_sheet"])
    try:
        found = seed.execute_batched(svc["drive"], [
            svc["drive"].files().get(fileId=item["id"], fields="id,trashed") for item in resources])
    except Exception as error:
        raise RuntimeError("Cannot access required Drive resources. No reset writes started. Restore missing files before resetting.") from error
    if any(item.get("trashed") for item in found):
        raise RuntimeError("A demo Drive file is trashed. Restore it before resetting to preserve its ID.")

    live_events = {item["id"]: item for item in pages(svc["calendar"].events().list,
        "items", calendarId="primary", q=seed.MARKER, maxResults=2500, showDeleted=False)}
    # Marked events whose descriptions were edited are still tracked by ID.
    absent = [item for item in state.get("events", []) if item["id"] not in live_events]
    for item in absent:
        try:
            event = svc["calendar"].events().get(calendarId="primary", eventId=item["id"]).execute()
        except seed.HttpError as error:
            if error.resp.status not in (404, 410):
                raise
            event = {"status": "cancelled"}
        if event.get("status") != "cancelled":
            live_events[item["id"]] = event
        elif not full_reset:
            _missing("calendar events")

    if not full_reset:
        if not state.get("emails") or not state.get("events"):
            _missing("email/calendar records")
        found_mail = {item["id"] for item in pages(svc["gmail"].users().messages().list,
            "messages", userId="me", includeSpamTrash=True, maxResults=500)}
        reconcile_email_ids(seed, svc["gmail"], state, found_mail)
        if set(state.get("task_resources", {})) != set(seed.task_scenario.RESOURCES):
            _missing("task resources")
        if svc["tasks"] is not None:
            if not state.get("task_list") or len(state.get("tasks", [])) != len(seed.task_scenario.TASKS):
                _missing("Google Tasks records")
            tasks = {item["id"]: item for item in pages(svc["tasks"].tasks().list, "items",
                tasklist=state["task_list"]["id"], maxResults=100, showCompleted=True, showHidden=True)}
            if any(item["id"] not in tasks or tasks[item["id"]].get("deleted") for item in state["tasks"]):
                _missing("Google Tasks")
        expected = {"elena", "mike", "aisha", "daniel", "priya", "prd"}
        expected.update(item["key"] for item in seed.task_scenario.TASKS)
        if not expected <= evidence_from_state(state).keys():
            _missing("email evidence mappings")
        validate_saved_brief(seed.ROOT, state)

    # Existing states lack event templates. Reconstruct with the original seed
    # date, not today's date (which would silently move meetings on quick reset).
    if any("baseline" not in item for item in state.get("events", [])):
        reference_day = date.fromisoformat(state["week_of"])
        if state.get("emails"):
            try:
                mail = svc["gmail"].users().messages().get(userId="me", id=state["emails"][0]["id"], format="minimal").execute()
                reference_day = datetime.fromtimestamp(int(mail["internalDate"]) / 1000,
                    seed.ZoneInfo(seed.TZ_NAME)).date()
            except seed.HttpError as error:
                if not full_reset or error.resp.status not in (404, 410):
                    raise
                # Full reset can recover missing emails; locate the old review.
                for event in live_events.values():
                    if event.get("summary", "").startswith("NeoAgent V2 Exec Review"):
                        reference_day = date.fromisoformat(event["start"]["dateTime"][:10])
                        break
        baseline = calendar_baseline(seed, state, date.fromisoformat(state["week_of"]), reference_day)
        if len(baseline) != len(state.get("events", [])) and not full_reset:
            _missing("calendar baseline")
        for item, original in zip(state.get("events", []), baseline):
            if "baseline" not in item:
                item.update(original)
    return live_events


def validate_saved_brief(root, state):
    """A pre-existing stale brief must not silently survive its first quick reset."""
    folder = root / "CoS_Workspace/DailyBriefs"
    briefs = []
    for path in folder.glob("*.md"):
        try:
            if date.fromisoformat(path.stem).isoformat() == path.stem:
                briefs.append(path)
        except ValueError:
            pass
    if not briefs:
        return
    text = max(briefs).read_text(encoding="utf-8")
    mail_ids = {value for item in state["emails"] for value in (item["id"], item.get("thread_id", item["id"]))}
    if any(value not in mail_ids for value in re.findall(r"mail\.google\.com/mail/[^\s)\"]*#(?:all|inbox)/([a-zA-Z0-9_-]+)", text)):
        _missing("email links in the saved daily brief")
    task_urls = {item.get("url", "").split("?")[0] for item in state.get("tasks", [])}
    if any(url not in task_urls for url in re.findall(r"https://tasks\.google\.com/task/[^\s)?\"]+", text)):
        _missing("task links in the saved daily brief")


def restore_mail_labels(seed, svc, state):
    groups = {}
    for index, item in enumerate(state["emails"]):
        labels = item.setdefault("baseline_labels", ["INBOX", "UNREAD"] +
            (["IMPORTANT"] if index < seed.MEANINGFUL_EMAIL_COUNT else []))
        groups.setdefault(tuple(labels), []).append(item["id"])
    for labels, ids in groups.items():
        svc["gmail"].users().messages().batchModify(userId="me", body={
            "ids": ids, "addLabelIds": list(labels),
            "removeLabelIds": [label for label in ("TRASH", "SPAM", "STARRED", "IMPORTANT") if label not in labels],
        }).execute()


def clear_demo_drafts(seed, gmail):
    """Keep unrelated drafts. Inspect only drafts, never send messages."""
    drafts = pages(gmail.users().drafts().list, "drafts", userId="me", maxResults=500)
    results = seed.execute_batched(gmail, [gmail.users().drafts().get(userId="me", id=d["id"], format="full") for d in drafts])
    requests = []
    demo_recipients = {
        "elena.example@nvidia.com", "mike.example@nvidia.com", "aisha.example@nvidia.com",
        "daniel.example@nvidia.com", "priya.example@nvidia.com", "rafael.example@nvidia.com",
        "leah.moreno@example.com", "tessa.ellis@example.com", "evan.mercer@example.com",
    }
    for draft, result in zip(drafts, results):
        payload = result.get("message", {}).get("payload", {})
        subject = next((h["value"] for h in payload.get("headers", []) if h["name"].lower() == "subject"), "").lower()
        recipients = {address.lower() for _, address in getaddresses([
            h["value"] for h in payload.get("headers", []) if h["name"].lower() in ("to", "cc", "bcc")])}
        if recipients & demo_recipients or any(term in subject for term in ("neoagent", "gtc 2027", "financial analysis", "local ai meeting notes", "superbox", "autonomous robot")):
            requests.append(gmail.users().drafts().delete(userId="me", id=draft["id"]))
    seed.execute_batched(gmail, requests)


def restore_calendar(seed, svc, state, live, week, *, full_reset):
    wanted = calendar_baseline(seed, state, week, seed.local_now().date()) if full_reset else [
        {"seed_key": e["seed_key"], "baseline": e["baseline"]} for e in state["events"]]
    previous = {item["seed_key"]: item for item in state.get("events", []) if "seed_key" in item}
    output = []
    for spec in wanted:
        old = previous.get(spec["seed_key"], {})
        if old.get("id") in live:
            spec.update(id=old["id"], url=old.get("url", ""))
        elif not full_reset:
            _missing("calendar events")
        output.append(spec)
    requests, targets = [], []
    for item in output:
        body = item["baseline"]
        current = live.get(item.get("id"), {})
        if current and all(current.get(k) == v for k, v in body.items()):
            continue
        if current:
            request = svc["calendar"].events().update(calendarId="primary", eventId=item["id"], body=body, sendUpdates="none")
        else:
            request = svc["calendar"].events().insert(calendarId="primary", body=body, sendUpdates="none")
        requests.append(request)
        targets.append(item)
    for target, result in zip(targets, seed.execute_batched(svc["calendar"], requests)):
        target.update(id=result["id"], url=result.get("htmlLink", target.get("url", "")))
    keep = {item["id"] for item in output}
    extras = [svc["calendar"].events().delete(calendarId="primary", eventId=event_id, sendUpdates="none")
              for event_id, event in live.items() if event_id not in keep and seed.MARKER in event.get("description", "")]
    seed.execute_batched(svc["calendar"], extras)
    state["events"] = output


def reset_in_place(seed, state, week, *, full_reset=False):
    svc = seed.services(tasks_required=bool(state.get("task_list")))
    if not full_reset and state.get("week_of") != week.isoformat():
        raise RuntimeError("Quick reset preserves existing dates. Run --full-reset to move the demo to another workweek.")
    live = preflight(seed, svc, state, full_reset=full_reset)
    before = {key: [item["id"] for item in state.get(key, [])] for key in ("emails", "tasks", "events")}
    def save():
        seed.state_path().write_text(json.dumps(state, indent=2), encoding="utf-8")
    state["reset_incomplete"] = True
    save()
    # Invalidate cached links before the first ID-changing write, even if a
    # later operation fails. Quick reset preserves the latest saved brief.
    if full_reset:
        seed.clear_evidence_cache(seed.ROOT, preserve_latest_brief=False)
    template_hash = seed.deck_template_hash()
    seed.reset_deck_baseline(svc["slides"], state["slides"]["id"], drive=svc["drive"],
        restore_template=state["slides"].get("template_sha256") != template_hash)
    state["slides"]["template_sha256"] = template_hash
    seed.task_scenario.ensure_resources(SimpleNamespace(ROOT=seed.ROOT, upload_template=seed.upload_template), svc, state, restore=True, checkpoint=save)
    # Restore the main campaign document too; it was previously omitted.
    from googleapiclient.http import MediaFileUpload
    svc["drive"].files().update(fileId=state["doc"]["id"], body={"mimeType": "application/vnd.google-apps.document"},
        media_body=MediaFileUpload(str(seed.ROOT / "demo/templates/neoagent-v2-campaign-plan.docx"),
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document", resumable=False), fields="id").execute()
    clear_demo_drafts(seed, svc["gmail"])
    if full_reset:
        seed.clear_seeded_tasks(svc["tasks"], state)
        mail_ids = {item["id"] for item in state.get("emails", [])} | seed.seeded_gmail_message_ids(svc["gmail"])
        if mail_ids:
            svc["gmail"].users().messages().batchDelete(userId="me", body={"ids": sorted(mail_ids)}).execute()
        state["emails"], evidence = seed.create_emails(svc["gmail"], state["slides"]["url"], state["sheet"]["url"], state["doc"]["url"], state["task_resources"])
        save()
        seed.create_tasks(svc["tasks"], state, evidence)
        state["task_scenario_date"] = seed.local_now().date().isoformat()
        save()
    else:
        evidence = evidence_from_state(state)
        restore_mail_labels(seed, svc, state)
    seed.reset_sheet_baseline(svc["sheets"], state, evidence, seed.local_now().date().isoformat())
    seed.reset_original_sheet(svc["drive"], svc["sheets"], state, evidence, seed.local_now().date().isoformat())
    restore_calendar(seed, svc, state, live, week, full_reset=full_reset)
    state["week_of"] = week.isoformat()
    after = {key: [item["id"] for item in state.get(key, [])] for key in before}
    if not full_reset and before != after:
        raise RuntimeError("Quick reset unexpectedly changed resource IDs; reset is incomplete.")
    state["last_reset"] = {"mode": "full" if full_reset else "quick", "changed_ids": {
        key: {"removed": sorted(set(before[key]) - set(after[key])), "added": sorted(set(after[key]) - set(before[key]))}
        for key in before}}
    save()
    return state
