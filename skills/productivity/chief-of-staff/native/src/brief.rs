use super::*;
use chrono::{DateTime, TimeZone, Timelike};
use chrono_tz::Tz;
use unicode_casefold::UnicodeCaseFold;
fn fold(s: &str) -> String {
    s.case_fold().collect()
}
fn pick(v: &Value, keys: &[&str]) -> Value {
    obj(keys.iter().map(|k| (*k, v[*k].clone())).collect())
}
fn tok(text: &str) -> HashSet<String> {
    let stops = [
        "about", "after", "before", "could", "from", "have", "into", "meeting", "notes", "that",
        "their", "there", "these", "this", "today", "update", "with", "your",
    ];
    regex::Regex::new(r"[a-z0-9][a-z0-9_-]{3,}")
        .unwrap()
        .find_iter(&fold(text))
        .map(|m| m.as_str().to_string())
        .filter(|t| !stops.contains(&t.as_str()) && !t.chars().all(|c| c.is_ascii_digit()))
        .collect()
}
fn score(text: &str) -> i64 {
    let text = fold(text);
    [
        ("urgent", 8),
        ("blocker", 8),
        ("deadline", 7),
        ("decision", 7),
        ("approve", 6),
        ("approval", 6),
        ("customer", 6),
        ("launch", 6),
        ("exec", 6),
        ("board", 7),
        ("investor", 6),
        ("follow up", 5),
        ("action required", 7),
        ("review", 3),
        ("update", 2),
    ]
    .iter()
    .filter(|(k, _)| text.contains(k))
    .map(|(_, v)| v)
    .sum()
}
pub fn dt(value: &str, tz: Tz) -> Option<DateTime<Tz>> {
    if !value.contains('T') {
        return None;
    }
    DateTime::parse_from_rfc3339(value)
        .ok()
        .map(|d| d.with_timezone(&tz))
        .or_else(|| {
            NaiveDateTime::parse_from_str(value, "%Y-%m-%dT%H:%M:%S%.f")
                .ok()
                .and_then(|d| tz.from_local_datetime(&d).single())
        })
}
fn overlap(a: &HashSet<String>, b: &HashSet<String>) -> Vec<String> {
    let mut v: Vec<_> = a.intersection(b).cloned().collect();
    v.sort();
    v
}
fn related(e: &Value, messages: &[Value], files: &[Value]) -> Value {
    let t = tok(&format!("{} {}", s(&e["title"]), s(&e["organizer"])));
    let mut mail = vec![];
    for m in messages {
        let mut matches = overlap(
            &t,
            &tok(&format!(
                "{} {} {}",
                s(&m["subject"]),
                s(&m["from"]),
                s(&m["snippet"])
            )),
        );
        if matches.len() >= 2
            || (!matches.is_empty()
                && !s(&e["organizer"]).is_empty()
                && fold(s(&m["from"])).contains(&fold(s(&e["organizer"]))))
        {
            matches.truncate(5);
            let mut v = pick(m, &["id", "thread_id", "subject", "from"]);
            v["match"] = json!(matches);
            mail.push(v);
        }
    }
    let mut fs = vec![];
    for f in files {
        let mut matches = overlap(
            &t,
            &tok(&format!("{} {}", s(&f["name"]), s(&f["description"]))),
        );
        if !matches.is_empty() {
            matches.truncate(5);
            let mut v = pick(f, &["id", "name", "kind", "url"]);
            v["match"] = json!(matches);
            fs.push(v);
        }
    }
    mail.truncate(4);
    fs.truncate(5);
    json!({"mail":mail,"files":fs})
}
fn conflicts(events: &[Value], tz: Tz) -> Vec<Value> {
    let mut timed: Vec<_> = events
        .iter()
        .filter_map(|e| Some((dt(s(&e["start"]), tz)?, dt(s(&e["end"]), tz)?, e)))
        .collect();
    timed.sort_by_key(|x| x.0);
    let mut groups: Vec<Vec<_>> = vec![];
    let mut current = vec![];
    let mut max_end = None;
    for item in timed {
        if !current.is_empty() && max_end.is_some_and(|end| item.0 < end) {
            max_end = Some(max_end.unwrap().max(item.1));
            current.push(item)
        } else {
            if current.len() > 1 {
                groups.push(std::mem::take(&mut current));
            }
            current = vec![item];
            max_end = Some(item.1);
        }
    }
    if current.len() > 1 {
        groups.push(current);
    }
    groups.into_iter().map(|g|{let es:Vec<_>=g.iter().map(|(_,_,e)|{let mut v=pick(e,&["id","title","start","end","organizer"]);v["attendee_count"]=json!(items(&e["attendees"]).len());v["url"]=if s(&e["html_link"]).is_empty(){e["meeting_url"].clone()}else{e["html_link"].clone()};v}).collect();json!({"start":g.iter().map(|x|x.0).min().unwrap().to_rfc3339(),"end":g.iter().map(|x|x.1).max().unwrap().to_rfc3339(),"events":es})}).collect()
}
fn focus(
    events: &[Value],
    tz: Tz,
    window: &str,
    planning: DateTime<Tz>,
    a: &Args,
) -> Result<Vec<Value>> {
    let day = dt(window, tz).context("Invalid window start")?.date_naive();
    let start_hour = a.number("work-start", 8)? as u32;
    let end_hour = a.number("work-end", 18)? as u32;
    let mut cursor = tz
        .from_local_datetime(
            &day.and_hms_opt(start_hour, 0, 0)
                .context("Invalid work start hour")?,
        )
        .single()
        .context("Invalid work start")?
        .max(planning);
    let end = tz
        .from_local_datetime(
            &day.and_hms_opt(end_hour, 0, 0)
                .context("Invalid work end hour")?,
        )
        .single()
        .context("Invalid work end")?;
    let min = a.number("min-focus-minutes", 30)? as i64;
    let mut intervals: Vec<_> = events
        .iter()
        .filter_map(|e| Some((dt(s(&e["start"]), tz)?, dt(s(&e["end"]), tz)?)))
        .filter(|(s, e)| *e > cursor && *s < end)
        .map(|(s, e)| (s.max(cursor), e.min(end)))
        .collect();
    intervals.sort();
    let mut merged: Vec<(DateTime<Tz>, DateTime<Tz>)> = vec![];
    for (s, e) in intervals {
        if let Some(last) = merged.last_mut() {
            if s <= last.1 {
                last.1 = last.1.max(e);
                continue;
            }
        }
        merged.push((s, e));
    }
    let mut out = vec![];
    for (s, e) in merged {
        if s > cursor && (s - cursor).num_minutes() >= min {
            out.push(json!({"start":cursor.to_rfc3339(),"end":s.to_rfc3339(),"minutes":(s-cursor).num_minutes()}));
        }
        cursor = cursor.max(e);
    }
    if end > cursor && (end - cursor).num_minutes() >= min {
        out.push(json!({"start":cursor.to_rfc3339(),"end":end.to_rfc3339(),"minutes":(end-cursor).num_minutes()}));
    }
    Ok(out)
}
pub fn build(snapshot: &Value, a: &Args) -> Result<Value> {
    let tz: Tz = s(&snapshot["timezone"]).parse().unwrap_or(chrono_tz::UTC);
    let events = items(&snapshot["events"]);
    let messages = items(&snapshot["messages"]);
    let files = items(&snapshot["files"]);
    let email = s(&snapshot["identity"]["email"]);
    let generated = dt(s(&snapshot["generated_at"]), tz).unwrap_or(Utc::now().with_timezone(&tz));
    let update = a.option("mode", "daily-brief") == "second-brain-update";
    let planning = if update {
        generated
    } else {
        generated
            .with_hour(9)
            .unwrap()
            .with_minute(30)
            .unwrap()
            .with_second(0)
            .unwrap()
            .with_nanosecond(0)
            .unwrap()
    };
    let mut meetings = vec![];
    for e in events {
        let mut rank = score(&format!("{} {}", s(&e["title"]), s(&e["location"])));
        let others: Vec<_> = items(&e["attendees"])
            .iter()
            .filter(|x| x["self"] != true)
            .collect();
        if others.len() >= 5 {
            rank += 3;
        }
        if !email.is_empty() && fold(s(&e["organizer"])) == fold(email) {
            rank += 2;
        }
        let own = email
            .rsplit_once('@')
            .map(|(_, d)| fold(d))
            .unwrap_or_default();
        if others.iter().any(|v| {
            s(&v["email"])
                .rsplit_once('@')
                .is_some_and(|(_, d)| !d.is_empty() && fold(d) != own)
        }) {
            rank += 4;
        }
        let status = match (dt(s(&e["start"]), tz), dt(s(&e["end"]), tz)) {
            (Some(s), Some(e)) => {
                if planning >= e {
                    "ended"
                } else if planning < s {
                    "upcoming"
                } else {
                    "in_progress"
                }
            }
            _ => "unknown",
        };
        let mut v = pick(
            e,
            &[
                "id",
                "title",
                "start",
                "end",
                "all_day",
                "organizer",
                "self_status",
                "meeting_url",
            ],
        );
        v["time_status"] = json!(status);
        v["attendee_count"] = json!(items(&e["attendees"]).len());
        v["calendar_url"] = e["html_link"].clone();
        v["links"] = e.get("links").cloned().unwrap_or(json!([]));
        v["related"] = related(e, messages, files);
        meetings.push((rank, v));
    }
    meetings.sort_by(|(ar, av), (br, bv)| br.cmp(ar).then(s(&av["start"]).cmp(s(&bv["start"]))));
    let meetings: Vec<_> = meetings
        .into_iter()
        .take(a.number("max-meetings", 15)?)
        .map(|(_, v)| v)
        .collect();
    let mut mail = vec![];
    for m in messages {
        let mut rank = score(&format!("{} {}", s(&m["subject"]), s(&m["snippet"])));
        if m["unread"] == true {
            rank += 2;
        }
        if m["important"] == true {
            rank += 4;
        }
        if !email.is_empty()
            && fold(&format!("{} {}", s(&m["to"]), s(&m["cc"]))).contains(&fold(email))
            && !s(&m["to"]).contains(',')
        {
            rank += 3;
        }
        let ms = m["internal_ms"].as_i64().unwrap_or(0);
        let age = if ms == 0 {
            None
        } else {
            DateTime::from_timestamp_millis(ms).map(|d| {
                (generated.date_naive() - d.with_timezone(&tz).date_naive())
                    .num_days()
                    .max(0)
            })
        };
        let mut v = pick(
            m,
            &[
                "id",
                "thread_id",
                "from",
                "subject",
                "date",
                "snippet",
                "unread",
            ],
        );
        v["url"] = json!(format!(
            "https://mail.google.com/mail/u/0/#all/{}",
            m["thread_id"].as_str().unwrap_or("None")
        ));
        v["age_days"] = json!(age);
        v["stale_timing"] = json!(age.is_some_and(|v| v > 1));
        v["links"] = m.get("links").cloned().unwrap_or(json!([]));
        mail.push((rank, ms, v));
    }
    mail.sort_by(|a, b| b.0.cmp(&a.0).then(b.1.cmp(&a.1)));
    let mail: Vec<_> = mail
        .into_iter()
        .take(a.number("max-mail", 12)?)
        .map(|(_, _, v)| v)
        .collect();
    let recent: Vec<_> = files
        .iter()
        .take(a.number("max-files", 12)?)
        .map(|f| {
            pick(
                f,
                &[
                    "id",
                    "name",
                    "kind",
                    "modified",
                    "url",
                    "starred",
                    "last_editor",
                ],
            )
        })
        .collect();
    let coverage = snapshot.get("coverage").cloned().unwrap_or(json!({}));
    let err = items(&coverage["errors"])
        .iter()
        .map(|v| fold(s(v)))
        .collect::<Vec<_>>()
        .join(" ");
    let mut source = json!({});
    for (name, values) in [("calendar", events), ("gmail", messages), ("drive", files)] {
        source[name] = json!(if err.contains(name) {
            "error"
        } else if values.is_empty() {
            "ok_empty"
        } else {
            "ok"
        });
    }
    let instructions: Value = serde_json::from_str(include_str!("../instructions.json"))?;
    let mut instruction = s(&instructions["daily"]).to_string();
    let mut tasks_out = None;
    if snapshot.get("tasks").is_some() {
        source["tasks"] = json!(if err.contains("tasks:") {
            "error"
        } else if items(&snapshot["tasks"]).is_empty() {
            "ok_empty"
        } else {
            "ok"
        });
        let mut tasks: Vec<_> = items(&snapshot["tasks"])
            .iter()
            .filter(|t| t["status"] == "needsAction" && t["deleted"] != true && t["hidden"] != true)
            .collect();
        let due = |t: &Value| {
            t["due"]
                .as_str()
                .filter(|s| !s.is_empty())
                .unwrap_or("9999-12-31")
                .to_string()
        };
        tasks.sort_by(|a, b| (due(a), s(&a["title"])).cmp(&(due(b), s(&b["title"]))));
        let mut out = vec![];
        for t in tasks.into_iter().take(a.number("max-tasks", 8)?) {
            let mut v = pick(t, &["id", "title", "status", "due", "url", "links"]);
            v["notes"] = json!(cut(s(&t["notes"]), 240));
            let mut threads = HashSet::new();
            for link in items(&t["links"]) {
                if let Ok(url) = url::Url::parse(s(link)) {
                    if url.host_str() == Some("mail.google.com") {
                        if let Some(f) = url.fragment().filter(|s| s.contains('/')) {
                            let decoded = percent_decode(f);
                            threads.insert(decoded.rsplit('/').next().unwrap_or("").to_string());
                        }
                    }
                }
            }
            v["related_mail_ids"] = json!(
                mail.iter()
                    .filter(|m| !s(&m["id"]).is_empty() && threads.contains(s(&m["thread_id"])))
                    .map(|m| m["id"].clone())
                    .collect::<Vec<_>>()
            );
            out.push(v);
        }
        tasks_out = Some(out);
        instruction.push_str(s(&instructions["tasks"]));
    }
    if update {
        instruction = s(&instructions["update"]).into();
    }
    let window = snapshot["window"]["start"]
        .as_str()
        .filter(|s| !s.is_empty())
        .map(str::to_string)
        .unwrap_or(planning.to_rfc3339());
    let mut packet = json!({"schema":1,"instruction":instruction,"freshness":{"generated_at":snapshot["generated_at"],"local_time":planning.to_rfc3339(),"timezone":tz.name(),"window":snapshot["window"]},"coverage":coverage,"source_status":source,"conflicts":conflicts(events,tz),"focus_blocks":focus(events,tz,&window,planning,a)?,"meetings":meetings,"mail":mail,"recent_files":recent});
    if let Some(t) = tasks_out {
        packet["tasks"] = json!(t);
    }
    if update {
        packet["mode"] = json!("second-brain-update");
    }
    Ok(packet)
}
fn percent_decode(s: &str) -> String {
    let b = s.as_bytes();
    let mut out = vec![];
    let mut i = 0;
    while i < b.len() {
        if b[i] == b'%' && i + 2 < b.len() {
            if let (Some(hi), Some(lo)) = (
                (b[i + 1] as char).to_digit(16),
                (b[i + 2] as char).to_digit(16),
            ) {
                let v = (hi * 16 + lo) as u8;
                out.push(v);
                i += 3;
                continue;
            }
        }
        out.push(b[i]);
        i += 1;
    }
    String::from_utf8_lossy(&out).into()
}
pub fn fit(p: &mut Value, max: usize) -> Result<String> {
    fn size(p: &Value) -> usize {
        p.to_string().chars().count()
    }
    if size(p) > max {
        if let Some(ms) = p["meetings"].as_array_mut() {
            for m in ms {
                m.as_object_mut().unwrap().shift_remove("related");
            }
        }
    }
    if size(p) > max && !items(&p["second_brain"]["notes"]).is_empty() {
        p["second_brain"]["truncated"] = json!(true);
        for n in p["second_brain"]["notes"].as_array_mut().unwrap() {
            let e = s(&n["excerpt"]);
            if e.chars().count() > 160 {
                let shortened = cut(e, 158);
                n["excerpt"] = json!(format!(
                    "{} …",
                    shortened
                        .rsplit_once(' ')
                        .map(|(s, _)| s)
                        .unwrap_or(&shortened)
                ));
            }
        }
        while size(p) > max && !items(&p["second_brain"]["notes"]).is_empty() {
            p["second_brain"]["notes"].as_array_mut().unwrap().pop();
            p["second_brain"]["omitted_notes"] =
                json!(p["second_brain"]["omitted_notes"].as_u64().unwrap_or(0) + 1);
        }
    }
    while size(p) > max && !items(&p["conflicts"]).is_empty() {
        p["conflicts"].as_array_mut().unwrap().pop();
        p["omitted_conflict_groups"] =
            json!(p["omitted_conflict_groups"].as_u64().unwrap_or(0) + 1);
    }
    while size(p) > max {
        let target = if items(&p["meetings"]).len() > 1 {
            "meetings"
        } else {
            let mut best = "mail";
            for key in ["recent_files", "meetings", "tasks"] {
                if items(&p[key]).len() > items(&p[best]).len() {
                    best = key
                }
            }
            best
        };
        if items(&p[target]).len() <= 1 {
            break;
        }
        p[target].as_array_mut().unwrap().pop();
    }
    if size(p) > max {
        if let Some(ms) = p["mail"].as_array_mut() {
            for m in ms {
                m["snippet"] = json!(cut(s(&m["snippet"]), 160));
            }
        }
    }
    ensure!(
        size(p) <= max,
        "Brief packet exceeds --max-chars ({} > {max})",
        size(p)
    );
    Ok(p.to_string())
}
