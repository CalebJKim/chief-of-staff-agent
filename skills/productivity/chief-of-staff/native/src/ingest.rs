use super::*;
use chrono::{NaiveDate, TimeZone};
use chrono_tz::Tz;
const CAL: &str = "https://www.googleapis.com/calendar/v3";
pub fn compact(text: &str) -> String {
    regex::Regex::new(r"\s+")
        .unwrap()
        .replace_all(text, " ")
        .trim()
        .into()
}
pub fn links(text: &str) -> Vec<String> {
    let re = regex::Regex::new(r#"https?://[^\s<>'"]+"#).unwrap();
    let mut found = vec![];
    for m in re.find_iter(text) {
        let u = m
            .as_str()
            .trim_end_matches(['.', ',', ')', ';', ']'])
            .to_string();
        if !found.contains(&u) {
            found.push(u)
        }
        if found.len() >= 6 {
            break;
        }
    }
    found
}
pub fn redact(text: &str) -> String {
    regex::Regex::new(r"(?i)\b(verification(?:\s+code)?|security\s+code|one[- ]time\s+(?:code|password)|otp|code)(\s*(?:is|:)?\s*)\d{4,8}\b").unwrap().replace_all(text,"${1}${2}[REDACTED]").into()
}
fn truth(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
        _ => true,
    }
}
pub fn collect(a: &Args, api: Option<&Api>) -> Result<Value> {
    if let Some(path) = a.opts.get("fixture") {
        let mut data: Value = serde_json::from_str(&fs::read_to_string(path)?)?;
        if data.get("source").is_none() {
            data["source"] = json!("fixture");
        }
        return Ok(data);
    }
    let api = api.context("Google API client is required")?;
    let now = Utc::now();
    let tz_name = api
        .get(&format!("{CAL}/users/me/settings/timezone"), vec![])
        .ok()
        .and_then(|r| r["value"].as_str().map(str::to_string))
        .unwrap_or("UTC".into());
    let tz: Tz = tz_name.parse().unwrap_or(chrono_tz::UTC);
    let tz_name = tz.name();
    let date = if let Some(d) = a.opts.get("date") {
        NaiveDate::parse_from_str(d, "%Y-%m-%d")?
    } else {
        now.with_timezone(&tz).date_naive()
    };
    let start = tz
        .from_local_datetime(&date.and_hms_opt(0, 0, 0).unwrap())
        .single()
        .context("Invalid calendar date")?;
    let end = tz
        .from_local_datetime(
            &(date + Duration::days(a.number("days-ahead", 2)? as i64))
                .and_hms_opt(0, 0, 0)
                .unwrap(),
        )
        .single()
        .context("Invalid calendar end date")?;
    let mut errors = vec![];
    let mut events = vec![];
    let event_result = (|| -> Result<()> {
        let mut calendars = vec![];
        let mut page = String::new();
        loop {
            let mut q = vec![
                ("minAccessRole", "reader".into()),
                ("showHidden", "false".into()),
            ];
            if !page.is_empty() {
                q.push(("pageToken", page.clone()));
            }
            let r = api.get(&format!("{CAL}/users/me/calendarList"), q)?;
            calendars.extend(items(&r["items"]).iter().cloned());
            let next = s(&r["nextPageToken"]);
            if next.is_empty() {
                break;
            }
            ensure!(next != page, "Repeated calendar list page token");
            page = next.into();
        }
        let mut selected: Vec<_> = calendars
            .iter()
            .filter(|c| truth(c.get("selected").unwrap_or(&c["primary"])))
            .collect();
        if selected.is_empty() {
            selected = calendars
                .iter()
                .filter(|c| truth(&c["primary"]))
                .take(1)
                .collect();
        }
        let max = a.number("max-events", 60)?;
        for cal in selected {
            if events.len() >= max {
                break;
            }
            let result = (|| -> Result<()> {
                let mut page = String::new();
                while events.len() < max {
                    let mut q = vec![
                        ("timeMin", start.with_timezone(&Utc).to_rfc3339()),
                        ("timeMax", end.with_timezone(&Utc).to_rfc3339()),
                        ("singleEvents", "true".into()),
                        ("orderBy", "startTime".into()),
                        ("showDeleted", "false".into()),
                        ("maxResults", 250.min(max - events.len()).to_string()),
                    ];
                    if !page.is_empty() {
                        q.push(("pageToken", page.clone()));
                    }
                    let r =
                        api.get(&format!("{CAL}/calendars/{}/events", enc(s(&cal["id"]))), q)?;
                    for e in items(&r["items"]) {
                        if e["status"] == "cancelled" {
                            continue;
                        }
                        let self_status = items(&e["attendees"])
                            .iter()
                            .find(|v| truth(&v["self"]))
                            .map(|v| v["responseStatus"].clone())
                            .unwrap_or(Value::Null);
                        if self_status == "declined" {
                            continue;
                        }
                        let attendees:Vec<_>=items(&e["attendees"]).iter().take(20).map(|v|json!({"email":s(&v["email"]),"name":s(&v["displayName"]),"status":s(&v["responseStatus"]),"self":truth(&v["self"])})).collect();
                        let text = format!(
                            "{} {} {}",
                            s(&e["description"]),
                            s(&e["location"]),
                            s(&e["hangoutLink"])
                        );
                        let mut ls: Vec<String> = items(&e["attachments"])
                            .iter()
                            .filter_map(|v| {
                                v["fileUrl"]
                                    .as_str()
                                    .filter(|s| !s.is_empty())
                                    .map(str::to_string)
                            })
                            .collect();
                        ls.extend(links(&text));
                        let mut seen = HashSet::new();
                        ls.retain(|v| seen.insert(v.clone()));
                        events.push(json!({"id":e["id"],"calendar_id":cal["id"],"calendar":s(&cal["summary"]),"title":e["summary"].as_str().unwrap_or("(untitled)"),"start":e["start"].get("dateTime").or(e["start"].get("date")),"end":e["end"].get("dateTime").or(e["end"].get("date")),"all_day":e["start"].get("date").is_some(),"status":e["status"],"self_status":self_status,"organizer":s(&e["organizer"]["email"]),"attendees":attendees,"location":s(&e["location"]),"meeting_url":s(&e["hangoutLink"]),"links":ls,"html_link":s(&e["htmlLink"])}));
                    }
                    let next = s(&r["nextPageToken"]);
                    if next.is_empty() {
                        break;
                    }
                    ensure!(next != page, "Repeated events page token");
                    page = next.into();
                }
                Ok(())
            })();
            if let Err(e) = result {
                errors.push(format!(
                    "calendar:{}: {e}",
                    cal["summary"].as_str().unwrap_or(s(&cal["id"]))
                ));
            }
        }
        let mut dedup = serde_json::Map::new();
        for e in events.drain(..) {
            dedup.insert(json!([e["title"], e["start"], e["end"]]).to_string(), e);
        }
        events = dedup.into_iter().map(|(_, v)| v).collect();
        events.sort_by(|a, b| {
            (s(&a["start"]), s(&a["title"])).cmp(&(s(&b["start"]), s(&b["title"])))
        });
        events.truncate(max);
        Ok(())
    })();
    if let Err(e) = event_result {
        events.clear();
        errors.push(format!("calendar: {e}"));
    }
    let mut messages = vec![];
    let mut identity = json!({});
    let mail_result = (|| -> Result<()> {
        let profile = api.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/profile",
            vec![],
        )?;
        let query = a.option(
            "gmail-query",
            "in:inbox -category:promotions -category:social",
        );
        let max = a.number("max-messages", 50)?;
        let mut refs = vec![];
        let mut page = String::new();
        while refs.len() < max {
            let mut q = vec![
                ("q", query.into()),
                ("maxResults", 100.min(max - refs.len()).to_string()),
            ];
            if !page.is_empty() {
                q.push(("pageToken", page.clone()));
            }
            let r = api.get("https://gmail.googleapis.com/gmail/v1/users/me/messages", q)?;
            refs.extend(items(&r["messages"]).iter().cloned());
            let next = s(&r["nextPageToken"]);
            if next.is_empty() {
                break;
            }
            ensure!(next != page, "Repeated Gmail page token");
            page = next.into();
        }
        for r in refs.iter().take(max) {
            let m = api.message(s(&r["id"]), true)?;
            let h = headers(&m["payload"]);
            let decoded = body(&m["payload"]);
            let text = redact(&compact(if decoded.is_empty() {
                s(&m["snippet"])
            } else {
                &decoded
            }));
            let preview = if text.chars().count() <= 500 {
                text.clone()
            } else {
                format!(
                    "{}…",
                    cut(&text, 499)
                        .rsplit_once(' ')
                        .map(|(s, _)| s.to_string())
                        .unwrap_or(cut(&text, 499))
                )
            };
            messages.push(json!({"id":m["id"],"thread_id":m["threadId"],"from":h.get("from").map(String::as_str).unwrap_or(""),"to":h.get("to").map(String::as_str).unwrap_or(""),"cc":h.get("cc").map(String::as_str).unwrap_or(""),"subject":h.get("subject").filter(|s|!s.is_empty()).map(String::as_str).unwrap_or("(no subject)"),"date":h.get("date").map(String::as_str).unwrap_or(""),"internal_ms":s(&m["internalDate"]).parse::<i64>().unwrap_or(0),"unread":items(&m["labelIds"]).iter().any(|v|v=="UNREAD"),"important":items(&m["labelIds"]).iter().any(|v|v=="IMPORTANT"),"labels":m.get("labelIds").cloned().unwrap_or(json!([])),"snippet":preview,"links":links(&text)}));
        }
        messages.sort_by_key(|m| -m["internal_ms"].as_i64().unwrap_or(0));
        identity = json!({"email":s(&profile["emailAddress"]),"query":query});
        Ok(())
    })();
    if let Err(e) = mail_result {
        messages.clear();
        errors.push(format!("gmail: {e}"));
    }
    let mut files = vec![];
    let drive_result = (|| -> Result<()> {
        let max = a.number("max-files", 30)?;
        let cutoff = now - Duration::days(a.number("days-back", 30)? as i64);
        let r=api.get("https://www.googleapis.com/drive/v3/files",vec![("q",format!("trashed = false and modifiedTime >= '{}'",cutoff.to_rfc3339())),("orderBy","modifiedTime desc".into()),("pageSize",max.min(100).to_string()),("fields","nextPageToken,files(id,name,mimeType,modifiedTime,createdTime,webViewLink,owners(displayName,emailAddress),lastModifyingUser(displayName,emailAddress),starred,description)".into())])?;
        for f in items(&r["files"]).iter().take(max) {
            let mime = s(&f["mimeType"]);
            let kind = match mime {
                "application/vnd.google-apps.document" => "doc",
                "application/vnd.google-apps.spreadsheet" => "sheet",
                "application/vnd.google-apps.presentation" => "slides",
                "application/vnd.google-apps.folder" => "folder",
                _ => mime,
            };
            files.push(json!({"id":f["id"],"name":s(&f["name"]),"kind":kind,"mime_type":mime,"modified":s(&f["modifiedTime"]),"url":s(&f["webViewLink"]),"starred":truth(&f["starred"]),"last_editor":s(&f["lastModifyingUser"]["displayName"]),"description":cut(&compact(s(&f["description"])),240)}));
        }
        Ok(())
    })();
    if let Err(e) = drive_result {
        files.clear();
        errors.push(format!("drive: {e}"));
    }
    let mut trackers = vec![];
    let tracker_result = (|| -> Result<()> {
        for f in files
            .iter()
            .filter(|v| v["kind"] == "sheet" && s(&v["name"]).to_lowercase().contains("tracker"))
            .take(2)
        {
            let r = api.get(
                &format!(
                    "https://sheets.googleapis.com/v4/spreadsheets/{}/values/{}",
                    enc(s(&f["id"])),
                    enc("'Campaign Lanes'!A6:J20")
                ),
                vec![],
            )?;
            let mut rows = vec![];
            for (i, c) in items(&r["values"]).iter().skip(1).enumerate() {
                if s(&c[0]).is_empty() {
                    continue;
                }
                let get = |n| items(c).get(n).cloned().unwrap_or(json!(""));
                rows.push(json!({"row":i+7,"lane":get(0),"pic":get(1),"status":get(2),"latest":get(3),"next":get(4),"blocker":get(6),"evidence":get(7),"artifact":get(8)}));
            }
            if !rows.is_empty() {
                trackers.push(json!({"id":f["id"],"name":f["name"],"url":f["url"],"rows":rows}));
            }
        }
        Ok(())
    })();
    if let Err(e) = tracker_result {
        trackers.clear();
        errors.push(format!("sheets: {e}"));
    }
    let mut tasks = vec![];
    let mut has_more = false;
    let task_result = (|| -> Result<()> {
        let max = a.number("max-tasks", 20)?;
        ensure!(
            (1..=100).contains(&max),
            "max_tasks must be between 1 and 100"
        );
        let r=api.get(&format!("https://tasks.googleapis.com/tasks/v1/lists/{}/tasks",enc(a.option("task-list","@default"))),vec![("maxResults",max.to_string()),("showCompleted","false".into()),("showDeleted","false".into()),("showHidden","false".into()),("showAssigned","true".into()),("fields","nextPageToken,items(id,title,status,due,notes,webViewLink,links,deleted,hidden)".into())])?;
        has_more = !s(&r["nextPageToken"]).is_empty();
        tasks = task_items(&r, max);
        Ok(())
    })();
    if let Err(e) = task_result {
        tasks.clear();
        errors.push(format!("tasks: {e}"));
    }
    Ok(
        json!({"schema":1,"source":"google_workspace","generated_at":Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Micros,true),"timezone":tz_name,"window":{"start":start.to_rfc3339(),"end":end.to_rfc3339()},"identity":identity,"coverage":{"events":events.len(),"messages":messages.len(),"files":files.len(),"tasks":tasks.len(),"tasks_has_more":has_more,"errors":errors},"events":events,"messages":messages,"files":files,"trackers":trackers,"tasks":tasks}),
    )
}
pub fn task_items(r: &Value, max: usize) -> Vec<Value> {
    let mut tasks = vec![];
    let mut seen = HashSet::new();
    for t in items(&r["items"]).iter().take(max) {
        if s(&t["id"]).is_empty()
            || !seen.insert(s(&t["id"]))
            || t["status"] != "needsAction"
            || truth(&t["deleted"])
            || truth(&t["hidden"])
        {
            continue;
        }
        let notes = redact(&compact(s(&t["notes"])));
        let extra = items(&t["links"])
            .iter()
            .map(|l| s(&l["link"]))
            .collect::<Vec<_>>()
            .join(" ");
        tasks.push(json!({"id":t["id"],"title":cut(&redact(t["title"].as_str().filter(|s|!s.is_empty()).unwrap_or("(untitled)")),200),"status":t["status"],"due":cut(s(&t["due"]),10),"notes":cut(&notes,500),"links":links(&format!("{notes} {extra}")),"url":t["webViewLink"].as_str().filter(|s|!s.is_empty()).unwrap_or("https://tasks.google.com/")}));
    }
    tasks
}
#[cfg(test)]
mod tests {
    use super::*;
    fn test_args() -> Args {
        let m = cli::command()
            .try_get_matches_from(["cos-actions", "ingest", "--date", "2026-10-07"])
            .unwrap();
        workflows::args("ingest", m.subcommand().unwrap().1).unwrap()
    }
    #[test]
    fn collects_bounded_sources_and_retains_links_beyond_preview() {
        let text = format!("{} https://example.com/source", "Evidence ".repeat(100));
        let api = Api::mock(vec![
            json!({"value":"America/Los_Angeles"}),
            json!({"items":[{"id":"cal","primary":true}]}),
            json!({"items":[{"id":"yes","summary":"Review","start":{"dateTime":"2026-10-07T19:00:00-07:00"},"end":{"dateTime":"2026-10-07T20:00:00-07:00"}}, {"id":"no","status":"cancelled"}]}),
            json!({"emailAddress":"owner@example.com"}),
            json!({"messages":[{"id":"mail"}]}),
            json!({"id":"mail","threadId":"thread","internalDate":"1791417600000","payload":{"mimeType":"text/plain","body":{"data":URL_SAFE_NO_PAD.encode(text)}}}),
            json!({"files":[{"id":"doc","name":"Project","mimeType":"application/vnd.google-apps.document"}]}),
            json!({"items":[{"id":"task","title":"Design","status":"needsAction","due":"2026-10-07T00:00:00Z"}]}),
        ]);
        let snapshot = collect(&test_args(), Some(&api)).unwrap();
        assert_eq!(snapshot["coverage"]["errors"], json!([]));
        for key in ["events", "messages", "files", "tasks"] {
            assert_eq!(snapshot["coverage"][key], 1);
        }
        assert_eq!(snapshot["window"]["start"], "2026-10-07T00:00:00-07:00");
        assert!(s(&snapshot["messages"][0]["snippet"]).chars().count() <= 500);
        assert_eq!(
            snapshot["messages"][0]["links"],
            json!(["https://example.com/source"])
        );
        assert!(api.calls().iter().all(|c| c["method"] == "GET"));
    }
    #[test]
    fn partial_failures_are_reported_not_disguised_as_empty_success() {
        let api = Api::mock(vec![
            json!({"value":"UTC"}),
            json!({"__error":"calendar denied"}),
            json!({"__error":"gmail denied"}),
            json!({"__error":"drive denied"}),
            json!({"__error":"tasks denied"}),
        ]);
        let snapshot = collect(&test_args(), Some(&api)).unwrap();
        assert_eq!(items(&snapshot["coverage"]["errors"]).len(), 4);
        assert_eq!(api.calls().len(), 5);
    }
    #[test]
    fn redaction_and_dates() {
        assert_eq!(
            redact("Verification code: 123456"),
            "Verification code: [REDACTED]"
        );
        let r = task_items(
            &json!({"items":[{"id":"a","status":"needsAction","due":"2026-10-07T00:00:00Z"},{"id":"a","status":"needsAction"},{"id":"b","status":"completed"}]}),
            20,
        );
        assert_eq!(r.len(), 1);
        assert_eq!(r[0]["due"], "2026-10-07");
    }
}
