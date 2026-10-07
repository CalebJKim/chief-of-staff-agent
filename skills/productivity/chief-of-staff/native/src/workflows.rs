use super::*;
use clap::{Arg, Command};

#[derive(Debug)]
pub struct StageError {
    pub stage: &'static str,
    pub detail: String,
}
impl std::fmt::Display for StageError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.detail)
    }
}
impl std::error::Error for StageError {}

fn daily(a: &Args) -> Result<()> {
    let mut stage = "prepare";
    let result = (|| -> Result<()> {
        let state = state_dir()?.join("chief-of-staff");
        fs::create_dir_all(&state)?;
        let folder = tempfile::Builder::new()
            .prefix("daily-brief-")
            .tempdir_in(state)?
            .keep();
        stage = "ingest";
        let api = if a.opts.contains_key("fixture") {
            None
        } else {
            Some(Api::new()?)
        };
        let snapshot = ingest::collect(a, api.as_ref())?;
        write_json(&folder.join("snapshot.json"), &snapshot)?;
        stage = "brief";
        let mut a = a.clone();
        for (k, v) in [
            ("max-meetings", "10"),
            ("max-mail", "8"),
            ("max-files", "8"),
            ("max-chars", "14000"),
            ("work-end", "17"),
        ] {
            a.opts.insert(k.into(), v.into());
        }
        let encoded = packet(&snapshot, &a)?;
        stage = "save";
        let path = folder.join("packet.json");
        fs::write(&path, format!("{encoded}\n"))?;
        emit(json!({"packet_path":path}));
        println!("{encoded}");
        Ok(())
    })();
    result.map_err(|e| {
        StageError {
            stage,
            detail: cut(&format!("{e:#}"), 2000),
        }
        .into()
    })
}
pub fn add(mut root: Command) -> Command {
    for (name, fields) in [
        (
            "ingest",
            vec![
                ("date", None),
                ("days-ahead", Some("2")),
                ("days-back", Some("30")),
                ("max-events", Some("60")),
                ("max-messages", Some("50")),
                ("max-files", Some("30")),
                ("task-list", Some("@default")),
                ("max-tasks", Some("20")),
                ("gmail-query", None),
                ("output", None),
                ("fixture", None),
                ("stdout", Some("summary")),
            ],
        ),
        (
            "brief",
            vec![
                ("mode", Some("daily-brief")),
                ("snapshot", None),
                ("max-meetings", Some("15")),
                ("max-mail", Some("12")),
                ("max-files", Some("12")),
                ("max-tasks", Some("8")),
                ("max-chars", Some("14000")),
                ("work-start", Some("8")),
                ("work-end", Some("18")),
                ("min-focus-minutes", Some("30")),
            ],
        ),
        (
            "daily-brief",
            vec![("mode", Some("daily-brief")), ("fixture", None)],
        ),
        ("verify", vec![]),
    ] {
        let mut cmd = Command::new(name);
        for (key, default) in fields {
            let mut arg = Arg::new(key).long(key);
            if let Some(v) = default {
                arg = arg.default_value(v);
            }
            if key == "mode" {
                arg = arg.value_parser(["daily-brief", "second-brain-update"]);
            }
            if key == "stdout" {
                arg = arg.value_parser(["none", "summary", "json"]);
            }
            cmd = cmd.arg(arg);
        }
        root = root.subcommand(cmd);
    }
    root
}
pub fn args(name: &str, m: &clap::ArgMatches) -> Result<Args> {
    let mut a = Args {
        group: name.into(),
        command: String::new(),
        pos: vec![],
        opts: HashMap::new(),
        multi: HashMap::new(),
    };
    for id in m.ids() {
        if id == "help" {
            continue;
        }
        if let Some(v) = m.get_one::<String>(id.as_str()) {
            a.opts.insert(id.as_str().into(), v.clone());
        }
    }
    for (key, value) in &a.opts {
        if key.starts_with("max-")
            || key.starts_with("days-")
            || key.starts_with("work-")
            || key == "min-focus-minutes"
        {
            let n: i64 = value
                .parse()
                .with_context(|| format!("Invalid integer for --{key}"))?;
            ensure!(n >= 0, "--{key} must not be negative");
            if key.starts_with("days-")
                || key == "max-tasks"
                || a.group == "ingest" && key.starts_with("max-")
            {
                ensure!(n >= 1, "all numeric bounds must be positive");
            }
            if a.group == "ingest" && key == "max-tasks" {
                ensure!(n <= 100, "--max-tasks must be between 1 and 100");
            }
        }
    }
    Ok(a)
}
fn write_json(path: &std::path::Path, value: &Value) -> Result<()> {
    if let Some(p) = path.parent().filter(|p| !p.as_os_str().is_empty()) {
        fs::create_dir_all(p)?;
    }
    fs::write(path, serde_json::to_string_pretty(value)?)?;
    Ok(())
}
fn packet(snapshot: &Value, a: &Args) -> Result<String> {
    let mut p = brief::build(snapshot, a)?;
    brief::fit(&mut p, a.number("max-chars", 14000)?)?;
    if let Some(context) = brain::context(&p) {
        p["second_brain"] = context;
    }
    brief::fit(&mut p, a.number("max-chars", 14000)?)
}
pub fn run(a: &Args) -> Result<()> {
    match a.group.as_str() {
        "ingest" => {
            let api = if a.opts.contains_key("fixture") {
                None
            } else {
                Some(Api::new()?)
            };
            let snapshot = ingest::collect(a, api.as_ref())?;
            let path = if let Some(path) = a.opts.get("output") {
                PathBuf::from(path)
            } else {
                state_dir()?.join("chief-of-staff/snapshot.json")
            };
            write_json(&path, &snapshot)?;
            match a.option("stdout", "summary") {
                "json" => emit(snapshot),
                "summary" => emit(
                    json!({"ok":true,"snapshot":path,"coverage":snapshot.get("coverage").cloned().unwrap_or(json!({}))}),
                ),
                _ => {}
            }
        }
        "brief" => {
            let path = if let Some(path) = a.opts.get("snapshot") {
                PathBuf::from(path)
            } else {
                state_dir()?.join("chief-of-staff/snapshot.json")
            };
            ensure!(path.is_file(), "Snapshot not found: {}", path.display());
            let snapshot = serde_json::from_str(&fs::read_to_string(path)?)?;
            println!("{}", packet(&snapshot, a)?);
        }
        "daily-brief" => daily(a)?,
        "verify" => {
            let result = verify(&Api::new()?);
            let ok = result["ok"] == true;
            emit(result);
            if !ok {
                bail!("One or more Workspace API checks failed")
            }
        }
        _ => bail!("Unknown workflow"),
    }
    Ok(())
}
fn verify(api: &Api) -> Value {
    let mut checks = json!({});
    for name in ["gmail", "calendar", "drive", "docs", "sheets", "slides"] {
        let r = (|| -> Result<Value> {
            match name {
                "gmail" => {
                    let r = api.get(
                        "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                        vec![("maxResults", "1".into())],
                    )?;
                    Ok(json!({"sample_count":items(&r["messages"]).len()}))
                }
                "calendar" => {
                    let r = api.get(
                        "https://www.googleapis.com/calendar/v3/users/me/calendarList",
                        vec![("showHidden", "false".into())],
                    )?;
                    let mut count = 0;
                    for c in items(&r["items"]) {
                        let events = api.get(
                            &format!(
                                "https://www.googleapis.com/calendar/v3/calendars/{}/events",
                                enc(s(&c["id"]))
                            ),
                            vec![
                                ("timeMin", Utc::now().to_rfc3339()),
                                ("timeMax", (Utc::now() + Duration::days(30)).to_rfc3339()),
                                ("singleEvents", "true".into()),
                                ("showDeleted", "false".into()),
                                ("maxResults", "50".into()),
                            ],
                        )?;
                        count += items(&events["items"]).len();
                    }
                    Ok(
                        json!({"calendar_count":items(&r["items"]).len(),"next_30d_event_count":count}),
                    )
                }
                "drive" => {
                    let r = api.get(
                        "https://www.googleapis.com/drive/v3/files",
                        vec![
                            ("q", "trashed = false".into()),
                            ("pageSize", "10".into()),
                            ("fields", "files(id)".into()),
                        ],
                    )?;
                    Ok(json!({"sample_count":items(&r["files"]).len()}))
                }
                _ => {
                    let mime = match name {
                        "docs" => "document",
                        "sheets" => "spreadsheet",
                        _ => "presentation",
                    };
                    let r=api.get("https://www.googleapis.com/drive/v3/files",vec![("q",format!("trashed = false and mimeType = 'application/vnd.google-apps.{mime}'")),("pageSize","1".into()),("fields","files(id)".into())])?;
                    let Some(f) = items(&r["files"]).first() else {
                        return Ok(json!({"sample":"no_file_available"}));
                    };
                    let (url, key, count_key) = match name {
                        "docs" => (
                            format!(
                                "https://docs.googleapis.com/v1/documents/{}",
                                enc(s(&f["id"]))
                            ),
                            "content",
                            "structural_items",
                        ),
                        "sheets" => (
                            format!(
                                "https://sheets.googleapis.com/v4/spreadsheets/{}",
                                enc(s(&f["id"]))
                            ),
                            "sheets",
                            "tab_count",
                        ),
                        _ => (
                            format!(
                                "https://slides.googleapis.com/v1/presentations/{}",
                                enc(s(&f["id"]))
                            ),
                            "slides",
                            "slide_count",
                        ),
                    };
                    let data = api.get(&url, vec![])?;
                    let count = if name == "docs" {
                        items(&data["body"][key]).len()
                    } else {
                        items(&data[key]).len()
                    };
                    Ok(json!({"sample":"read",count_key:count}))
                }
            }
        })();
        checks[name] = match r {
            Ok(mut v) => {
                v["ok"] = json!(true);
                v
            }
            Err(e) => json!({"ok":false,"error_type":"ApiError","error":cut(&e.to_string(),400)}),
        };
    }
    json!({"ok":checks.as_object().unwrap().values().all(|v|v["ok"]==true),"services":checks})
}
