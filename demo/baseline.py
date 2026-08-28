from __future__ import annotations

PRE_EMAIL_ROWS = [
    ["Product performance claims", "Mike Chen", "Awaiting update", "Performance validation is still pending; the tracker does not yet contain approved inference figures.", "Get Mike’s approved performance package, then update slide 4 and dependent campaign copy.", "", "Awaiting approved Product performance evidence.", "Pending Product confirmation", "DECK_URL", "Required qualification must accompany all figures."],
    ["Exec Review deck", "Elena Park", "Awaiting update", "The Exec Review deck still uses provisional performance language and has not incorporated the latest review notes.", "Apply approved numbers when received; reconcile slide 6, slide 7, and slide 10 feedback before the Exec Review.", "", "Blocked on approved figures and final review direction.", "Pending Mike and Aisha updates", "DECK_URL", "Two decisions: keynote storyline and IFA demos/owners."],
    ["Agent Messaging", "Workspace Owner", "Awaiting update", "Agent Messaging still carries provisional performance wording and is waiting on the approved claims package.", "Replace provisional wording after Product confirmation and align it exactly with slide 4.", "", "Awaiting approved performance wording and qualification.", "Pending Product / Legal confirmation", "DOC_URL", "Lead with agents; use specifications as proof."],
    ["Marketing shoot", "Priya Nair", "Blocked", "The planned venue is unavailable. Northstar is holding Studio B Friday and Studio C Tuesday until 4:30 PM today.", "Choose Studio B Friday or Studio C Tuesday before the hold expires.", "", "Executive replacement-date decision; venue and preferred crew will be released without it.", "EMAIL_PRIYA", "SHEET_URL", "Missing the hold risks a campaign slip."],
    ["Partner enablement", "Aisha Rahman", "On track", "The VP requested a review of the partner slides, and the staged Windows pilot passed its smoke check and is ready for an inclusion decision.", "Review the partner section and decide whether the pilot belongs in the demo.", "", "Keynote and IFA demo-owner decisions remain open.", "Partner review evidence", "DECK_URL", "Production inclusion is not yet approved."],
    ["Social rollout", "Rafael Costa", "Awaiting update", "No current status has been received.", "Request asset readiness, timing, and blockers from Rafael.", "", "PIC status", "Email / Slack", "", "Follow-up draft needed."],
    ["Retail demo readiness", "Grant Walker", "Blocked", "Aisha confirmed that the retail demo lane still has no final owner, so the IFA demo slate cannot be presented as closed.", "Assign the final retail demo owner and confirm coverage during the Exec Review.", "", "Final retail demo owner is unassigned.", "EMAIL_AISHA", "DECK_URL", "No direct current update from Grant was received."],
    ["Legal intake LGL-2026-0847", "Daniel Cho", "Awaiting update", "Legal intake is open and the tracker has no recorded clearance for the performance wording.", "Confirm Daniel’s clearance and record the required qualification before campaign-wide propagation.", "", "Awaiting legal confirmation of wording and disclaimer.", "Pending Daniel / Product evidence", "SHEET_URL", "Leadership review and external-copy clearance may differ."],
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
            ],
        },
    ).execute()
