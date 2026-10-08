use anyhow::{Context, Result, bail, ensure};
use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use chrono::{Duration, NaiveDateTime, Utc};
use reqwest::{Method, blocking::Client};
use serde_json::{Value, json};
use std::{
    collections::{HashMap, HashSet},
    env, fs,
    io::{self, Read},
    path::PathBuf,
};
mod brain;
mod brief;
mod cli;
mod drafts;
mod formatting;
mod gmail_batch;
mod gmail_evidence;
mod ingest;
mod mutations;
mod preview;
mod tracker_receipt;
mod workflows;

fn s(v: &Value) -> &str {
    v.as_str().unwrap_or("")
}
fn read_input(path: &str) -> Result<String> {
    if path == "-" {
        let mut text = String::new();
        io::stdin().read_to_string(&mut text)?;
        Ok(text)
    } else {
        Ok(fs::read_to_string(path)?.replace("\r\n", "\n"))
    }
}
fn state_dir() -> Result<PathBuf> {
    let p = PathBuf::from(env::var("COS_STATE_DIR").context(
        "COS_STATE_DIR is missing. Run the Perplexity launcher from the current thread workspace.",
    )?);
    ensure!(
        p.is_absolute() && p.is_dir(),
        "COS_STATE_DIR must point to an existing absolute workspace directory."
    );
    Ok(p)
}
fn items(v: &Value) -> &[Value] {
    v.as_array().map(Vec::as_slice).unwrap_or(&[])
}
fn cut(text: &str, n: usize) -> String {
    text.chars().take(n).collect()
}
fn enc(text: &str) -> String {
    text.as_bytes()
        .iter()
        .map(|b| {
            if b.is_ascii_alphanumeric() || b"_.-~".contains(b) {
                (*b as char).to_string()
            } else {
                format!("%{b:02X}")
            }
        })
        .collect()
}
fn emit(value: Value) {
    println!("{}", value);
}
fn obj(fields: Vec<(&str, Value)>) -> Value {
    Value::Object(
        fields
            .into_iter()
            .map(|(k, v)| (k.to_string(), v))
            .collect(),
    )
}
fn headers(payload: &Value) -> HashMap<String, String> {
    items(&payload["headers"])
        .iter()
        .map(|h| (s(&h["name"]).to_lowercase(), s(&h["value"]).to_string()))
        .collect()
}
fn body(payload: &Value) -> String {
    fn walk(p: &Value, out: &mut Vec<(String, String)>) {
        if !s(&p["filename"]).is_empty() {
            return;
        }
        let mime = s(&p["mimeType"]);
        let data = s(&p["body"]["data"]);
        if !data.is_empty() && ["text/plain", "text/html"].contains(&mime) {
            if let Ok(bytes) = URL_SAFE_NO_PAD.decode(data.trim_end_matches('=')) {
                out.push((mime.into(), String::from_utf8_lossy(&bytes).into_owned()));
            }
        }
        for child in items(&p["parts"]) {
            walk(child, out)
        }
    }
    let mut parts = vec![];
    walk(payload, &mut parts);
    let selected = parts
        .iter()
        .find(|(mime, _)| mime == "text/plain")
        .or(parts.first());
    let Some((mime, text)) = selected else {
        return String::new();
    };
    let text = if mime == "text/html" {
        html_escape::decode_html_entities(
            &regex::Regex::new(r"<[^>]+>")
                .unwrap()
                .replace_all(text, " "),
        )
        .into_owned()
    } else {
        text.clone()
    };
    regex::Regex::new(r"\n{3,}")
        .unwrap()
        .replace_all(&text, "\n\n")
        .trim()
        .into()
}
fn mail_url(id: &Value) -> Value {
    if id.is_null() {
        Value::Null
    } else {
        json!(format!("https://mail.google.com/mail/u/0/#all/{}", s(id)))
    }
}
struct Api {
    client: Client,
    token: String,
    #[cfg(test)]
    mock: Option<std::sync::Mutex<MockState>>,
}
#[cfg(test)]
#[derive(Default)]
struct MockState {
    responses: std::collections::VecDeque<Value>,
    calls: Vec<Value>,
}

impl Api {
    #[cfg(test)]
    fn mock(responses: Vec<Value>) -> Self {
        Self {
            client: Client::new(),
            token: String::new(),
            mock: Some(std::sync::Mutex::new(MockState {
                responses: responses.into(),
                calls: vec![],
            })),
        }
    }
    #[cfg(test)]
    fn calls(&self) -> Vec<Value> {
        self.mock.as_ref().unwrap().lock().unwrap().calls.clone()
    }
    fn new() -> Result<Self> {
        let state=PathBuf::from(env::var("COS_STATE_DIR").context("COS_STATE_DIR is missing. Run the Perplexity launcher from the current thread workspace.")?);
        ensure!(
            state.is_absolute() && state.is_dir(),
            "COS_STATE_DIR must point to an existing absolute workspace directory."
        );
        let path = state.join("google_token.json");
        let mut token: Value = serde_json::from_str(&fs::read_to_string(&path)?)?;
        let client = Client::builder()
            .timeout(std::time::Duration::from_secs(120))
            .build()?;
        let expiry = s(&token["expiry"]);
        let expired = if expiry.is_empty() {
            false
        } else {
            NaiveDateTime::parse_from_str(expiry.trim_end_matches('Z'), "%Y-%m-%dT%H:%M:%S%.f")
                .map(|d| d.and_utc() < Utc::now() + Duration::seconds(225))
                .unwrap_or(true)
        };
        if expired || s(&token["token"]).is_empty() {
            ensure!(
                !s(&token["refresh_token"]).is_empty(),
                "Google OAuth token is invalid"
            );
            let endpoint = if s(&token["token_uri"]).is_empty() {
                "https://oauth2.googleapis.com/token"
            } else {
                s(&token["token_uri"])
            };
            let response = client
                .post(endpoint)
                .form(&[
                    ("grant_type", "refresh_token"),
                    ("refresh_token", s(&token["refresh_token"])),
                    ("client_id", s(&token["client_id"])),
                    ("client_secret", s(&token["client_secret"])),
                ])
                .send()?;
            ensure!(
                response.status().is_success(),
                "Google OAuth refresh failed (HTTP {})",
                response.status()
            );
            let refresh: Value = response.json()?;
            token["token"] = refresh["access_token"].clone();
            token["expiry"] = json!(
                (Utc::now() + Duration::seconds(refresh["expires_in"].as_i64().unwrap_or(3600)))
                    .format("%Y-%m-%dT%H:%M:%S%.6fZ")
                    .to_string()
            );
            fs::write(&path, serde_json::to_string_pretty(&token)?)?;
        }
        let access = s(&token["token"]).to_string();
        ensure!(!access.is_empty(), "Google OAuth token is invalid");
        Ok(Self {
            client,
            token: access,
            #[cfg(test)]
            mock: None,
        })
    }
    fn call(
        &self,
        method: Method,
        url: &str,
        query: &[(String, String)],
        body: Option<Value>,
    ) -> Result<Value> {
        #[cfg(test)]
        if let Some(mock) = &self.mock {
            let mut m = mock.lock().unwrap();
            m.calls
                .push(json!({"method":method.as_str(),"url":url,"query":query,"body":body}));
            let response = m.responses.pop_front().context("Unexpected API call")?;
            if let Some(error) = response.get("__error") {
                bail!("Mock API error: {}", error)
            }
            return Ok(response);
        }
        let mut request = self
            .client
            .request(method, url)
            .bearer_auth(&self.token)
            .query(query);
        if let Some(body) = body {
            request = request.json(&body)
        }
        let response = request.send()?;
        let status = response.status();
        let text = response.text()?;
        if !status.is_success() {
            bail!("Google API error HTTP {}: {}", status, text)
        }
        if text.is_empty() {
            Ok(json!({}))
        } else {
            Ok(serde_json::from_str(&text)?)
        }
    }
    fn get(&self, url: &str, query: Vec<(&str, String)>) -> Result<Value> {
        self.call(
            Method::GET,
            url,
            &query
                .into_iter()
                .map(|(k, v)| (k.into(), v))
                .collect::<Vec<_>>(),
            None,
        )
    }
    fn post(&self, url: &str, body: Value) -> Result<Value> {
        self.call(Method::POST, url, &[], Some(body))
    }
    fn message(&self, id: &str, full: bool) -> Result<Value> {
        let mut query = vec![("format", if full { "full" } else { "metadata" }.to_string())];
        if !full {
            for field in ["From", "To", "Cc", "Reply-To", "Subject", "Date"] {
                query.push(("metadataHeaders", field.into()));
            }
        }
        self.get(
            &format!(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/{}",
                enc(id)
            ),
            query,
        )
    }
}
#[derive(Clone)]
struct Args {
    group: String,
    command: String,
    pos: Vec<String>,
    opts: HashMap<String, String>,
    multi: HashMap<String, Vec<String>>,
}
impl Args {
    fn option<'a>(&'a self, key: &str, default: &'a str) -> &'a str {
        self.opts.get(key).map(String::as_str).unwrap_or(default)
    }
    fn number(&self, key: &str, default: usize) -> Result<usize> {
        Ok(self.option(key, &default.to_string()).parse()?)
    }
    fn required(&self, key: &str) -> Result<&str> {
        self.opts
            .get(key)
            .map(String::as_str)
            .with_context(|| format!("Missing --{key}"))
    }
    fn id(&self) -> Result<&str> {
        self.pos
            .first()
            .map(String::as_str)
            .context("Missing resource ID/query")
    }
    fn confirm(&self) -> Result<()> {
        ensure!(
            self.opts.contains_key("confirm"),
            "Refusing mutation without --confirm after user approval"
        );
        Ok(())
    }
}
fn full_message(msg: &Value, max: usize, include_header: bool) -> Value {
    let h = headers(&msg["payload"]);
    let mut fields = vec![
        ("id", msg["id"].clone()),
        ("thread_id", msg["threadId"].clone()),
        ("url", mail_url(&msg["threadId"])),
    ];
    for key in ["from", "to", "cc", "subject", "date"] {
        fields.push((key, json!(h.get(key).map(String::as_str).unwrap_or(""))));
    }
    if include_header {
        fields.push((
            "message_id_header",
            json!(h.get("message-id").map(String::as_str).unwrap_or("")),
        ));
    }
    fields.push(("body", json!(cut(&body(&msg["payload"]), max))));
    obj(fields)
}
fn read_thread(api: &Api, id: &str, a: &Args) -> Result<Value> {
    let thread = api.get(
        &format!(
            "https://gmail.googleapis.com/gmail/v1/users/me/threads/{}",
            enc(id)
        ),
        vec![("format", "full".into())],
    )?;
    thread_view(&thread, id, a)
}
fn thread_view(thread: &Value, id: &str, a: &Args) -> Result<Value> {
    let source = items(&thread["messages"]);
    let count = a.number("max-messages", 12)?;
    let max = a.number("max-chars", 8000)?;
    let start = if count == 0 {
        0
    } else {
        source.len().saturating_sub(count)
    };
    let mut messages = vec![];
    for msg in &source[start..] {
        let h = headers(&msg["payload"]);
        let mut fields = vec![("id", msg["id"].clone())];
        for key in ["from", "to", "subject", "date"] {
            fields.push((key, json!(h.get(key).map(String::as_str).unwrap_or(""))));
        }
        fields.push(("body", json!(cut(&body(&msg["payload"]), max))));
        messages.push(obj(fields));
    }
    Ok(obj(vec![
        ("thread_id", json!(id)),
        (
            "url",
            mail_url(&json!(if s(&thread["id"]).is_empty() {
                id
            } else {
                s(&thread["id"])
            })),
        ),
        ("messages", json!(messages)),
    ]))
}
fn tracker_view(values: &Value) -> Option<Value> {
    let rows = values.as_array()?;
    for (i, row) in rows.iter().enumerate() {
        let labels: Vec<String> = items(row)
            .iter()
            .map(|v| s(v).trim().to_lowercase())
            .collect();
        if !labels.iter().any(|k| k == "lane") || !labels.iter().any(|k| k == "status") {
            continue;
        }
        let keys: Vec<String> = labels
            .into_iter()
            .map(|k| match k.as_str() {
                "pic" => "owner".into(),
                "latest update" => "latest".into(),
                "next action" => "next".into(),
                "dependency / blocker" => "blocker".into(),
                _ => k,
            })
            .collect();
        if keys.iter().any(|k| k.is_empty())
            || keys.iter().collect::<HashSet<_>>().len() != keys.len()
            || rows[i + 1..].iter().any(|r| items(r).len() > keys.len())
        {
            return None;
        }
        let lanes: Vec<Value> = rows[i + 1..]
            .iter()
            .filter(|r| items(r).iter().any(|v| v != &json!("")))
            .map(|r| {
                Value::Object(
                    keys.iter()
                        .enumerate()
                        .map(|(i, k)| (k.clone(), items(r).get(i).cloned().unwrap_or(json!(""))))
                        .collect(),
                )
            })
            .collect();
        return Some(obj(vec![
            ("context", json!(&rows[..i])),
            ("lanes", json!(lanes)),
        ]));
    }
    None
}
const STATUSES: [&str; 5] = [
    "On track",
    "In progress",
    "Awaiting update",
    "Blocked",
    "Complete",
];
fn update_lanes(api: &Api, a: &Args) -> Result<Value> {
    a.confirm()?;
    let text = if let Some(s) = a.opts.get("updates") {
        s.clone()
    } else {
        let f = a.required("updates-file")?;
        if f == "-" {
            let mut text = String::new();
            io::stdin().read_to_string(&mut text)?;
            text
        } else {
            fs::read_to_string(f)?
        }
    };
    let updates: Value = serde_json::from_str(text.trim_start_matches('\u{feff}'))?;
    let updates = updates
        .as_array()
        .context("--updates must be a non-empty JSON array")?;
    ensure!(
        !updates.is_empty(),
        "--updates must be a non-empty JSON array"
    );
    let details = a.opts.contains_key("include-details");
    ensure!(
        !(details && a.opts.contains_key("status-only")),
        "Choose --status-only or --include-details"
    );
    let mut names = vec![];
    let mut seen = HashSet::new();
    for u in updates {
        let o = u.as_object().context("Every tracker update needs a lane")?;
        let lane = s(&u["lane"]).trim();
        ensure!(!lane.is_empty(), "Every tracker update needs a lane");
        ensure!(
            seen.insert(lane),
            "Each tracker lane may be updated only once"
        );
        ensure!(
            o.keys().all(|k| [
                "lane", "status", "latest", "next", "due", "blocker", "evidence"
            ]
            .contains(&k.as_str())),
            "Unsupported tracker fields; use lane, status, latest, next, due, blocker, evidence"
        );
        ensure!(
            details || o.keys().all(|k| ["lane", "status"].contains(&k.as_str())),
            "Status-only updates accept only lane and status; remove other fields and retry. Nothing was written. Use --include-details only when the user explicitly requested non-status edits."
        );
        ensure!(
            STATUSES.contains(&s(&u["status"])),
            "Invalid status for {}; use one of {:?}",
            lane,
            STATUSES
        );
        names.push(lane.to_string());
    }
    let id = a.id()?;
    let sheet = a.option("sheet", "Campaign Lanes");
    let range = format!("'{sheet}'!A6:H100");
    let current = api.get(
        &format!(
            "https://sheets.googleapis.com/v4/spreadsheets/{}/values/{}",
            enc(id),
            enc(&range)
        ),
        vec![],
    )?;
    let rows = items(&current["values"]);
    let by_name: HashMap<&str, usize> = rows
        .iter()
        .skip(1)
        .enumerate()
        .filter(|(_, r)| !items(r).is_empty())
        .map(|(i, r)| (s(&r[0]), i + 7))
        .collect();
    let missing: Vec<_> = names
        .iter()
        .filter(|n| !by_name.contains_key(n.as_str()))
        .collect();
    ensure!(
        missing.is_empty(),
        "Tracker lane(s) not found: {:?}. Use exact lane names from this sheet: {:?}. Nothing was written.",
        missing,
        by_name.keys().collect::<Vec<_>>()
    );
    let mut data = vec![];
    let mut before = vec![];
    let mut unchecked = vec![];
    for u in updates {
        let lane = s(&u["lane"]).trim();
        let row = by_name[lane];
        before.push(rows[row - 6].clone());
        if !details {
            data.push(json!({"range":format!("'{sheet}'!C{row}"),"values":[[u["status"]]]}));
            continue;
        }
        let existing = &rows[row - 6];
        if !s(&existing[6]).trim().is_empty()
            && u["status"] != existing[2]
            && !u["blocker"].is_string()
        {
            unchecked.push(lane)
        }
        data.push(json!({"range":format!("'{sheet}'!C{row}:H{row}"),"values":[[u["status"],u["latest"],u["next"],u["due"],u["blocker"],u["evidence"]]]}));
    }
    ensure!(
        unchecked.is_empty(),
        "Status changes need explicit blocker text for {:?}: preserve or revise each dependency, or use an empty string if resolved. Nothing was written.",
        unchecked
    );
    let r = api.post(
        &format!(
            "https://sheets.googleapis.com/v4/spreadsheets/{}/values:batchUpdate",
            enc(id)
        ),
        json!({
            "valueInputOption":"USER_ENTERED", "data":data,
            "includeValuesInResponse":true,
            "responseValueRenderOption":"UNFORMATTED_VALUE"
        }),
    )?;
    let mut receipt = obj(vec![
        ("status", json!("updated")),
        ("spreadsheet_id", json!(id)),
        ("lanes", json!(names)),
        (
            "updated_rows",
            r.get("totalUpdatedRows").cloned().unwrap_or(json!(0)),
        ),
        (
            "updated_cells",
            r.get("totalUpdatedCells").cloned().unwrap_or(json!(0)),
        ),
    ]);
    tracker_receipt::verify(&mut receipt, &data, &before, &r)?;
    Ok(receipt)
}
fn slide_text(slide: &Value) -> String {
    fn append(elements: &Value, out: &mut String) {
        for e in items(elements) {
            out.push_str(s(&e["textRun"]["content"]));
        }
    }
    let mut out = String::new();
    for e in items(&slide["pageElements"]) {
        append(&e["shape"]["text"]["textElements"], &mut out);
        for row in items(&e["table"]["tableRows"]) {
            for cell in items(&row["tableCells"]) {
                append(&cell["text"]["textElements"], &mut out);
            }
        }
    }
    regex::Regex::new(r"\n{3,}")
        .unwrap()
        .replace_all(&out, "\n\n")
        .trim()
        .into()
}
fn run() -> Result<()> {
    let matches = cli::command().get_matches();
    if let Some((name, m)) = matches.subcommand() {
        if ["ingest", "brief", "daily-brief", "verify"].contains(&name) {
            return workflows::run(&workflows::args(name, m)?);
        }
    }
    let a = cli::from_matches(&matches)?;
    if a.group == "second-brain" {
        emit(brain::run(&a)?);
        return Ok(());
    }
    let api = Api::new()?;
    dispatch(&api, &a)
}
fn dispatch(api: &Api, a: &Args) -> Result<()> {
    match (a.group.as_str(), a.command.as_str()) {
        ("gmail", "evidence") => emit(gmail_evidence::run(api, a)?),
        ("gmail", "drafts") => emit(drafts::list(api)?),
        ("gmail", "draft") => emit(drafts::save(api, a)?),
        ("docs" | "slides", "inspect" | "format") => emit(formatting::run(api, a)?),
        ("docs" | "slides", "preview") => emit(preview::run(api, a)?),
        ("docs", "append" | "replace-text")
        | ("slides", "replace-text" | "delete")
        | ("calendar", "create") => emit(mutations::run(api, a)?),
        ("gmail", "get") => emit(full_message(
            &api.message(a.id()?, true)?,
            a.number("max-chars", 12000)?,
            true,
        )),
        ("gmail", "thread") => emit(read_thread(&api, a.id()?, &a)?),
        ("gmail", "threads") => {
            let ids = gmail_batch::unique_ids(&a.pos);
            for group in ids.chunks(gmail_batch::BATCH_SIZE) {
                let results = gmail_batch::read_threads(api, group)?;
                for (id, result) in group.iter().zip(results) {
                    emit(thread_view(&result?, id, a)?);
                }
            }
        }
        ("gmail", "search") => {
            let query = a.id()?;
            let limit = a.number("max", 5)?.clamp(1, 10);
            let refs = api.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                vec![("q", query.into()), ("maxResults", limit.to_string())],
            )?;
            let mut matches = vec![];
            for r in items(&refs["messages"]).iter().take(limit) {
                let m = api.message(s(&r["id"]), false)?;
                let h = headers(&m["payload"]);
                let mut fields = vec![
                    ("id", m["id"].clone()),
                    ("thread_id", m["threadId"].clone()),
                    ("labels", m.get("labelIds").cloned().unwrap_or(json!([]))),
                    ("url", mail_url(&m["threadId"])),
                ];
                for key in ["from", "to", "cc", "reply_to", "subject", "date"] {
                    let header = if key == "reply_to" { "reply-to" } else { key };
                    fields.push((key, json!(h.get(header).map(String::as_str).unwrap_or(""))));
                }
                matches.push(obj(fields));
            }
            emit(obj(vec![
                ("query", json!(query)),
                ("matches", json!(matches)),
            ]));
        }
        ("gmail", "important") => {
            let limit = a.number("max", 12)?.clamp(1, 20);
            let query = format!(
                "is:important newer_than:{}d",
                a.number("newer-than-days", 2)?.clamp(1, 30)
            );
            let refs = api.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                vec![("q", query.clone()), ("maxResults", limit.to_string())],
            )?;
            let mut messages = vec![];
            for r in items(&refs["messages"]).iter().take(limit) {
                messages.push(full_message(
                    &api.message(s(&r["id"]), true)?,
                    a.number("max-chars", 8000)?,
                    false,
                ));
            }
            emit(obj(vec![
                ("query", json!(query)),
                ("messages", json!(messages)),
            ]));
        }
        ("drive", "search") => {
            let query = if a.opts.contains_key("raw-query") {
                a.id()?.to_string()
            } else {
                format!(
                    "trashed = false and fullText contains '{}'",
                    a.id()?.replace("'", "\\'")
                )
            };
            let result=api.get("https://www.googleapis.com/drive/v3/files",vec![("q",query),("orderBy","modifiedTime desc".into()),("pageSize",a.number("max",10)?.to_string()),("fields","files(id,name,mimeType,modifiedTime,webViewLink,owners(displayName,emailAddress),description)".into())])?;
            emit(result.get("files").cloned().unwrap_or(json!([])));
        }
        ("docs", "get") => {
            let id = a.id()?;
            let doc = api.get(
                &format!("https://docs.googleapis.com/v1/documents/{}", enc(id)),
                vec![],
            )?;
            let mut text = String::new();
            for block in items(&doc["body"]["content"]) {
                for element in items(&block["paragraph"]["elements"]) {
                    text.push_str(s(&element["textRun"]["content"]));
                }
            }
            emit(obj(vec![
                ("id", json!(id)),
                ("title", json!(s(&doc["title"]))),
                ("text", json!(cut(&text, a.number("max-chars", 30000)?))),
            ]));
        }
        ("slides", "get") => {
            let id = a.id()?;
            let deck = api.get(
                &format!("https://slides.googleapis.com/v1/presentations/{}", enc(id)),
                vec![],
            )?;
            let mut slides = vec![];
            for (i, slide) in items(&deck["slides"]).iter().enumerate() {
                slides.push(obj(vec![
                    ("number", json!(i + 1)),
                    ("object_id", slide["objectId"].clone()),
                    (
                        "text",
                        json!(cut(
                            &slide_text(slide),
                            a.number("max-chars-per-slide", 4000)?
                        )),
                    ),
                ]));
            }
            emit(obj(vec![
                ("id", json!(id)),
                ("title", json!(s(&deck["title"]))),
                (
                    "url",
                    json!(format!("https://docs.google.com/presentation/d/{id}/edit")),
                ),
                ("slides", json!(slides)),
            ]));
        }
        ("sheets", "get") => {
            let id = a.id()?;
            let range = a.pos.get(1).map(String::as_str).unwrap_or("A1:J80");
            let result = api.get(
                &format!(
                    "https://sheets.googleapis.com/v4/spreadsheets/{}/values/{}",
                    enc(id),
                    enc(range)
                ),
                vec![],
            )?;
            let values = result.get("values").cloned().unwrap_or(json!([]));
            let mut output = obj(vec![
                ("spreadsheet_id", json!(id)),
                ("range", result["range"].clone()),
            ]);
            if let Some(view) = tracker_view(&values) {
                for (k, v) in view.as_object().unwrap() {
                    output[k] = v.clone();
                }
                println!("{}", serde_json::to_string_pretty(&output)?)
            } else {
                output["values"] = values;
                emit(output)
            }
        }
        ("sheets", "update-lanes") => emit(update_lanes(&api, &a)?),
        ("sheets", "update") => {
            a.confirm()?;
            ensure!(a.pos.len() > 1, "Missing range");
            let values: Value = serde_json::from_str(a.required("values")?)?;
            ensure!(values.is_array(), "--values must be a JSON array of rows");
            let r = api.call(
                Method::PUT,
                &format!(
                    "https://sheets.googleapis.com/v4/spreadsheets/{}/values/{}",
                    enc(a.id()?),
                    enc(&a.pos[1])
                ),
                &[("valueInputOption".into(), "USER_ENTERED".into())],
                Some(json!({"values":values})),
            )?;
            let mut out = json!({"status":"updated"});
            for (k, v) in r.as_object().context("Unexpected Sheets response")? {
                out[k] = v.clone()
            }
            emit(out);
        }
        _ => bail!(
            "Unknown command {} {}. Use --help for supported commands.",
            a.group,
            a.command
        ),
    }
    Ok(())
}
fn main() {
    if let Err(err) = run() {
        let mut payload = json!({"ok":false,"error":format!("{err:#}")});
        if let Some(error) = err.downcast_ref::<workflows::StageError>() {
            payload["stage"] = json!(error.stage);
        }
        if let Some(error) = err.downcast_ref::<tracker_receipt::VerificationError>() {
            payload["receipt"] = error.0.clone();
        }
        eprintln!("{payload}");
        std::process::exit(1)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn tracker_bom_status_only_and_scope_guards() {
        let m = cli::command()
            .try_get_matches_from([
                "cos-actions",
                "sheets",
                "update-lanes",
                "sheet",
                "--updates",
                "\u{feff}[{\"lane\":\"Alpha\",\"status\":\"Complete\"}]",
                "--confirm",
            ])
            .unwrap();
        let mut a = cli::from_matches(&m).unwrap();
        let current = json!({"values":[["Lane","PIC","Status","Latest","Next","Due","Blocker","Evidence"],["Alpha","Pat","In progress","keep","keep","keep","keep","keep"]]});
        let api = Api::mock(vec![
            current.clone(),
            json!({"totalUpdatedRows":1,"totalUpdatedCells":1,"responses":[{
                "updatedData":{"range":"'Campaign Lanes'!C7","values":[["Complete"]]}
            }]}),
        ]);
        let receipt = update_lanes(&api, &a).unwrap();
        assert_eq!(receipt["updated_cells"], 1);
        assert_eq!(receipt["verified"], true);
        assert_eq!(receipt["changes"][0]["before"]["status"], "In progress");
        assert_eq!(receipt["changes"][0]["after"]["status"], "Complete");
        assert_eq!(api.calls().len(), 2); // One pre-read and one write; no readback.
        assert_eq!(api.calls()[1]["body"]["includeValuesInResponse"], true);
        assert_eq!(
            api.calls()[1]["body"]["data"],
            json!([{"range":"'Campaign Lanes'!C7","values":[["Complete"]]}])
        );
        a.opts.insert(
            "updates".into(),
            r#"[{"lane":"Alpha","status":"Complete","latest":"no"}]"#.into(),
        );
        let api = Api::mock(vec![]);
        assert!(update_lanes(&api, &a).is_err());
        assert!(api.calls().is_empty());
        a.opts.insert("include-details".into(), "true".into());
        let api = Api::mock(vec![current]);
        assert!(update_lanes(&api, &a).is_err());
        assert_eq!(api.calls().len(), 1); // Unreviewed blocker prohibits writing.
    }
    #[test]
    fn tracker_failed_verification_does_not_retry_or_read_back() {
        let m = cli::command().try_get_matches_from([
            "cos-actions", "sheets", "update-lanes", "sheet", "--updates",
            r#"[{"lane":"Alpha","status":"Complete"}]"#, "--confirm",
        ]).unwrap();
        let a = cli::from_matches(&m).unwrap();
        let api = Api::mock(vec![
            json!({"values":[["Lane","PIC","Status"],["Alpha","Pat","In progress"]]}),
            json!({"totalUpdatedCells":1,"responses":[{"updatedData":{
                "range":"'Campaign Lanes'!C7","values":[["In progress"]]
            }}]}),
        ]);
        let err = update_lanes(&api, &a).unwrap_err();
        let receipt = &err.downcast_ref::<tracker_receipt::VerificationError>().unwrap().0;
        assert_eq!(receipt["verified"], false);
        assert_eq!(receipt["changes"][0]["after"]["status"], "In progress");
        assert_eq!(api.calls().len(), 2);
    }
    #[test]
    fn unicode_body_and_html() {
        assert_eq!(
            body(
                &json!({"mimeType":"text/plain","body":{"data":URL_SAFE_NO_PAD.encode("Hi â€” dÃ©jÃ  vu")}})
            ),
            "Hi â€” dÃ©jÃ  vu"
        );
        assert_eq!(
            body(
                &json!({"mimeType":"text/html","body":{"data":URL_SAFE_NO_PAD.encode("<b>A &amp; B</b>")}})
            ),
            "A & B"
        );
    }
    #[test]
    fn tracker_preserves_all_cells() {
        let view = tracker_view(&json!([
            ["Title"],
            ["Lane", "PIC", "Status", "Notes"],
            ["Alpha", "Someone", "Complete", "Scope"]
        ]))
        .unwrap();
        assert_eq!(view["lanes"][0]["owner"], "Someone");
        assert_eq!(view["lanes"][0]["notes"], "Scope");
        assert!(tracker_view(&json!([["Lane", "Status"], ["a", "b", "extra"]])).is_none());
    }
    #[test]
    fn attachment_not_body() {
        assert_eq!(
            body(
                &json!({"filename":"file.txt","mimeType":"text/plain","body":{"data":URL_SAFE_NO_PAD.encode("ignore")}})
            ),
            ""
        );
    }
    #[test]
    fn spaces_in_sheet_paths() {
        assert_eq!(enc("'Sample Tab'!A1:C9"), "%27Sample%20Tab%27%21A1%3AC9");
    }
}
