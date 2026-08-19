#!/usr/bin/env python
"""Seed/cleanup a portable Chief of Staff demo in the connected Google account."""
from __future__ import annotations
import argparse, base64, json, os, sys
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "productivity" / "ingest" / "scripts"))
from actions import credentials
from googleapiclient.discovery import build

MARKER = "chief-of-staff-public-demo-v1"
TZ = os.environ.get("CHIEF_OF_STAFF_DEMO_TZ", "America/Los_Angeles")
STATUSES = ["On track", "In review", "Awaiting update", "Blocked", "Complete"]

def home():
    if os.environ.get("HERMES_HOME"): return Path(os.environ["HERMES_HOME"]).expanduser()
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"): return Path(os.environ["LOCALAPPDATA"]) / "hermes"
    return Path.home() / ".hermes"
def state_path(): return home() / "chief-of-staff-demo-state.json"
def next_monday(d): return d + timedelta(days=(7 - d.weekday()) % 7)
def iso(d, hm):
    z = datetime.now(ZoneInfo(TZ)).strftime("%z")
    return f"{d.isoformat()}T{hm}:00{z[:3]}:{z[3:]}"
def event_templates():
    return [("08:00","08:30","Chief of Staff daily priorities"),("08:30","09:30","Campaign leadership pre-wire"),("09:00","10:00","IFA keynote working session"),("09:15","09:45","Marketing PMO stand-up"),("10:00","11:00","Creative and claims review"),("10:30","11:30","RTX Spark deck working session"),("11:00","12:00","Product + Legal escalation"),("12:00","13:00","Working lunch — campaign decisions"),("13:00","14:00","Local AI Summit readiness"),("13:30","14:30","Agency production sync — Northstar"),("14:00","15:00","Partner enablement review"),("15:00","16:00","Launch storyboard review"),("15:00","16:00","Demo and AV readiness review"),("15:30","16:30","Executive narrative prep"),("16:00","17:00","IFA program decision review"),("16:30","17:30","Launch budget approval"),("17:00","18:00","RTX Spark Exec Review"),("17:00","17:30","Decision follow-up triage"),("18:00","18:45","APAC handoff — decisions and risks")]

def create_sheet(api):
    rows = [["Lane","PIC","Status","Latest update","Next action","Due","Dependency / blocker","Evidence","Artifact","Notes"],["Product performance claims","Mike Chen","Awaiting update","Performance validation is pending.","Get approved package and update slide 4.","","Awaiting Product evidence","Pending confirmation","","PUBLIC DEMO"],["Exec Review deck","Elena Park","Awaiting update","Deck uses provisional wording.","Apply figures and reconcile slides 6, 7, and 10.","","Blocked on figures","Pending Mike and Aisha","","PUBLIC DEMO"],["Agent Messaging","Demo User","Awaiting update","Messaging carries provisional wording.","Align wording with slide 4.","","Awaiting approved wording","Pending Product and Legal","","PUBLIC DEMO"],["Marketing shoot","Priya Nair","Blocked","Planned venue is unavailable.","Choose Studio B Friday or Studio C Tuesday.","","Replacement-date decision","Priya update","","PUBLIC DEMO"],["Partner enablement","Aisha Rahman","On track","Partner slides are ready.","Decide pilot inclusion.","","Demo-owner decisions open","Aisha update","","PUBLIC DEMO"],["Social rollout","Rafael Costa","Awaiting update","No current status.","Request readiness and blockers.","","PIC status","Email or chat","","PUBLIC DEMO"],["Retail demo readiness","Grant Walker","Blocked","No final retail demo owner.","Assign owner before Exec Review.","","Owner unassigned","Aisha update","","PUBLIC DEMO"],["Legal intake DEMO-0847","Daniel Cho","Awaiting update","No recorded clearance.","Confirm scope and qualification.","","Awaiting Legal","Pending evidence","","PUBLIC DEMO"]]
    r = api.spreadsheets().create(body={"properties":{"title":"RTX Spark Campaign Tracker — Public Demo"},"sheets":[{"properties":{"title":"Campaign Lanes"}}]}).execute(); sid=r["spreadsheetId"]; shid=r["sheets"][0]["properties"]["sheetId"]
    api.spreadsheets().values().update(spreadsheetId=sid, range="Campaign Lanes!A1:J9", valueInputOption="USER_ENTERED", body={"values":rows}).execute()
    api.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests":[{"setDataValidation":{"range":{"sheetId":shid,"startRowIndex":1,"endRowIndex":9,"startColumnIndex":2,"endColumnIndex":3},"rule":{"condition":{"type":"ONE_OF_LIST","values":[{"userEnteredValue":x} for x in STATUSES]},"strict":True,"showCustomUi":True}}}]}).execute()
    return {"id":sid,"url":r.get("spreadsheetUrl",f"https://docs.google.com/spreadsheets/d/{sid}/edit")}

def create_doc(api):
    r=api.documents().create(body={"title":"RTX Spark Campaign Plan — Public Demo"}).execute(); did=r["documentId"]
    text="RTX Spark Campaign Plan — Public Demo\n\nAgent-first narrative\nLead with useful local AI coworkers; use specifications as evidence.\n\nOpen work\n- Confirm performance wording\n- Assign retail demo owner\n- Choose replacement shoot date\n- Prepare Exec Review decisions\n"
    api.documents().batchUpdate(documentId=did, body={"requests":[{"insertText":{"location":{"index":1},"text":text}}]}).execute()
    return {"id":did,"url":f"https://docs.google.com/document/d/{did}/edit"}

def create_slides(api):
    r=api.presentations().create(body={"title":"RTX Spark Exec Review — Public Demo"}).execute(); pid=r["presentationId"]; req=[]
    if r.get("slides"): req.append({"deleteObject":{"objectId":r["slides"][0]["objectId"]}})
    texts=[("RTX Spark Exec Review","Campaign plan — public demo"),("Lead with the agent","Approve the agent-first keynote storyline."),("Campaign state","Awaiting owner updates and decisions."),("Inference performance — update required","Performance to go here - Mike Chen to provide"),("One claim across every surface","Approve wording once, then propagate."),("Move the detail out of the live flow","Cut this detail slide; carry the point into slide 7."),("IFA demos — alignment needed","Confirm demo slate and owners."),("Execution dependencies","Claims, owners, and partners."),("Marketing shoot — decision required","Choose a replacement shoot date."),("Two decisions to leave with","1. Approve storyline\n2. Align demos and owners")]
    for i,(title,body) in enumerate(texts,1):
        sid=f"demo_slide_{i}"; a=f"demo_title_{i}"; b=f"demo_body_{i}"
        req += [{"createSlide":{"objectId":sid,"slideLayoutReference":{"predefinedLayout":"BLANK"}}},{"createShape":{"objectId":a,"shapeType":"TEXT_BOX","elementProperties":{"pageObjectId":sid,"size":{"width":{"magnitude":600,"unit":"PT"},"height":{"magnitude":60,"unit":"PT"}},"transform":{"scaleX":1,"scaleY":1,"translateX":50,"translateY":40,"unit":"PT"}}}},{"insertText":{"objectId":a,"text":title}},{"createShape":{"objectId":b,"shapeType":"TEXT_BOX","elementProperties":{"pageObjectId":sid,"size":{"width":{"magnitude":600,"unit":"PT"},"height":{"magnitude":260,"unit":"PT"}},"transform":{"scaleX":1,"scaleY":1,"translateX":50,"translateY":130,"unit":"PT"}}}},{"insertText":{"objectId":b,"text":body}}]
    api.presentations().batchUpdate(presentationId=pid,body={"requests":req}).execute()
    return {"id":pid,"url":f"https://docs.google.com/presentation/d/{pid}/edit"}

def create_calendar(api,start,deck,doc):
    out=[]
    for n in range(5):
        d=start+timedelta(days=n)
        for begin,end,title in event_templates():
            links=f"\nDeck: {deck}" if title=="RTX Spark Exec Review" else f"\nNotes: {doc}" if title=="Launch storyboard review" else ""
            e=api.events().insert(calendarId="primary",body={"summary":title,"description":f"Public demo event with intentional overlaps.{links}\n[{MARKER}]","start":{"dateTime":iso(d,begin),"timeZone":TZ},"end":{"dateTime":iso(d,end),"timeZone":TZ}},sendUpdates="none").execute(); out.append({"id":e["id"]})
    return out

def import_mail(api,account,sender,subject,body,index):
    m=EmailMessage(); m["From"]=sender; m["To"]=account; m["Subject"]=subject; m["Date"]=format_datetime(datetime.now().astimezone()); m["Message-ID"]=f"<{MARKER}-{index}@example.invalid>"; m.set_content(body+f"\n\n[{MARKER}]")
    raw=base64.urlsafe_b64encode(m.as_bytes()).decode("ascii")
    r=api.users().messages().import_(userId="me",body={"raw":raw,"labelIds":["INBOX","UNREAD","IMPORTANT"]},internalDateSource="dateHeader",neverMarkSpam=True,processForCalendar=False).execute(); return {"id":r["id"]}

def create_emails(api,deck,sheet):
    account=api.users().getProfile(userId="me").execute()["emailAddress"]
    data=[("Elena Park <elena.park@example.invalid>","URGENT: RTX Spark Exec Review moved to 5 PM today",f"Leadership moved the decision meeting to 5 PM today. Prepare storyline and demo owners. Deck: {deck}"),("Mike Chen <mike.chen@example.invalid>","APPROVED: RTX Spark inference numbers for slide 4","Approved: 2.1x faster time-to-first-token, 38 tokens/second, and 22% lower energy. Keep the qualification."),("Aisha Rahman <aisha.rahman@example.invalid>","Exec Review deck pass: cut slide 6; protect slide 10","Cut slide 6, carry its point into slide 7, and protect slide 10. Retail demo owner remains unassigned."),("Daniel Cho <daniel.cho@example.invalid>","Legal scope: wording cleared for leadership review","Wording is cleared for leadership review, not blanket external use."),("Priya Nair <priya.nair@example.invalid>","Decision by 4:30 PM today: marketing shoot venue hold",f"Choose Studio B Friday or Studio C Tuesday before 4:30 PM. Tracker: {sheet}"),("Elena Park <elena.park@example.invalid>","Agent Security PRD needs to reach Engineering today","Finish the PRD today. Skip optional storyboard session if needed.")]
    return [import_mail(api,account,*x,i) for i,x in enumerate(data,1)]

def cleanup(state):
    c=credentials(); gmail=build("gmail","v1",credentials=c,cache_discovery=False); cal=build("calendar","v3",credentials=c,cache_discovery=False); drive=build("drive","v3",credentials=c,cache_discovery=False)
    for x in state.get("emails",[]):
        try: gmail.users().messages().delete(userId="me",id=x["id"]).execute()
        except Exception: pass
    for x in state.get("events",[]):
        try: cal.events().delete(calendarId="primary",eventId=x["id"],sendUpdates="none").execute()
        except Exception: pass
    for k in ("sheet","doc","slides"):
        try: drive.files().update(fileId=state[k]["id"],body={"trashed":True}).execute()
        except Exception: pass

def main():
    p=argparse.ArgumentParser(description="Seed or clean the public Chief of Staff demo"); p.add_argument("--week-of"); p.add_argument("--cleanup",action="store_true"); p.add_argument("--confirm",action="store_true"); a=p.parse_args(); path=state_path()
    if not a.confirm: raise SystemExit("Refusing Google writes without --confirm")
    if a.cleanup:
        if not path.exists(): raise SystemExit(f"No state file at {path}")
        cleanup(json.loads(path.read_text(encoding="utf-8"))); path.unlink(); print(json.dumps({"ok":True,"status":"cleaned"})); return
    if path.exists(): raise SystemExit(f"Demo already exists; clean it first: {path}")
    start=date.fromisoformat(a.week_of) if a.week_of else next_monday(datetime.now(ZoneInfo(TZ)).date()); c=credentials(); state={"schema":1,"marker":MARKER,"week_of":start.isoformat(),"events":[],"emails":[]}
    try:
        state["sheet"]=create_sheet(build("sheets","v4",credentials=c,cache_discovery=False)); state["doc"]=create_doc(build("docs","v1",credentials=c,cache_discovery=False)); state["slides"]=create_slides(build("slides","v1",credentials=c,cache_discovery=False)); state["events"]=create_calendar(build("calendar","v3",credentials=c,cache_discovery=False),start,state["slides"]["url"],state["doc"]["url"]); state["emails"]=create_emails(build("gmail","v1",credentials=c,cache_discovery=False),state["slides"]["url"],state["sheet"]["url"]); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(state,indent=2),encoding="utf-8")
    except Exception: cleanup(state); raise
    print(json.dumps({"ok":True,"state":str(path),"week_of":start.isoformat(),"events":len(state["events"]),"emails":len(state["emails"]),"sheet":state["sheet"],"doc":state["doc"],"slides":state["slides"]},indent=2))
if __name__=="__main__": main()
