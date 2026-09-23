from __future__ import annotations

STATUS_GUIDE = (
    "Status guide (lane scope, not downstream work): Awaiting update = missing input; "
    "In progress = input received, own drafting/edits pending; Complete = own deliverable done; "
    "Blocked = unresolved dependency; On track = progressing without a blocker."
)

PRE_EMAIL_ROWS = [
    ["Product performance claims", "Mike Chen", "Awaiting update", "Performance validation is still pending; the tracker does not yet contain approved inference figures.", "Obtain Mike’s approved performance package for leadership review.", "", "Awaiting approved Product performance evidence.", "Pending Product confirmation", "DECK_URL", "This lane delivers the approved evidence and qualification. Applying it is tracked separately under Exec Review deck and Agent Messaging."],
    ["Exec Review deck", "Elena Park", "Awaiting update", "The Exec Review deck still uses provisional performance language and has not incorporated the latest review notes.", "Apply approved numbers when received; reconcile slide 6, slide 7, and slide 10 feedback before the Exec Review.", "", "Blocked on approved figures and final review direction.", "Pending Mike and Aisha updates", "DECK_URL", "Two decisions: keynote storyline and GTC demos/owners."],
    ["Agent Messaging", "Workspace Owner", "Awaiting update", "Agent Messaging still carries provisional performance wording and is waiting on the approved claims package.", "Draft the messaging using Product's approved wording and qualification, aligned with the deck.", "", "Awaiting approved performance wording and qualification.", "Pending Product / Legal confirmation", "DOC_URL", "This lane prepares draft messaging from approved Product evidence. Final external publication needs a separate Legal review after the draft is ready."],
    ["Marketing shoot", "Priya Nair", "Blocked", "The planned venue is unavailable. Northstar is holding Studio B Friday and Studio C Tuesday until 4:30 PM today.", "Choose Studio B Friday or Studio C Tuesday before the hold expires.", "", "Executive replacement-date decision; venue and preferred crew will be released without it.", "EMAIL_PRIYA", "SHEET_URL", "Missing the hold risks a campaign slip."],
    ["Partner enablement", "Aisha Rahman", "On track", "The VP requested a review of the partner slides, and the staged Windows pilot passed its smoke check and is ready for an inclusion decision.", "Review the partner section and decide whether the pilot belongs in the demo.", "", "Keynote and GTC demo-owner decisions remain open.", "Partner review evidence", "DECK_URL", "Production inclusion is not yet approved."],
    ["Social rollout", "Rafael Costa", "Awaiting update", "No current status has been received.", "Request asset readiness, timing, and blockers from Rafael.", "", "PIC status", "Email / Slack", "", "Follow-up draft needed."],
    ["Retail demo readiness", "Unassigned", "Blocked", "The retail demo lane still has no final owner, so the GTC demo slate cannot be presented as closed.", "Assign the final retail demo owner and confirm coverage during the Exec Review.", "", "Final retail demo owner is unassigned.", "Tracker owner field", "DECK_URL", "No owner has been assigned."],
    ["Legal intake LGL-2026-0847", "Daniel Cho", "Awaiting update", "Legal intake is open and the tracker has no recorded clearance for the performance wording.", "Obtain Daniel’s clearance of the performance wording and qualification for leadership review.", "", "Awaiting legal confirmation of wording and disclaimer.", "Pending Daniel / Product evidence", "SHEET_URL", "This intake covers leadership-review clearance only. Final external-copy review is a separate requirement, not a condition for closing this intake."],
]


def replace_tokens(text: str, replacements: dict[str, str]) -> str:
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def reset_sheet_baseline(sheets, state: dict, evidence: dict[str, str], refreshed: str) -> None:
    replacements = {"DECK_URL": state["slides"]["url"], "DOC_URL": state["doc"]["url"], "SHEET_URL": state["sheet"]["url"], "EMAIL_PRIYA": evidence["priya"], "EMAIL_AISHA": evidence["aisha"]}
    rows = [[replace_tokens(cell, replacements) for cell in row] for row in PRE_EMAIL_ROWS]
    summary = [["Awaiting updates", "4", "", "Blocked", "2", "", "Active lanes", "8", "Last refreshed", refreshed]]
    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=state["sheet"]["id"],
        body={
            "valueInputOption": "USER_ENTERED",
            "data": [
                {"range": "'Campaign Lanes'!A7:J14", "values": rows},
                {"range": "'Campaign Lanes'!A3:J3", "values": summary},
                {"range": "'Campaign Lanes'!A4", "values": [[STATUS_GUIDE]]},
            ],
        },
    ).execute()
