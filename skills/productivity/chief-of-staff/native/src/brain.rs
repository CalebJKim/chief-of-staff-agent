use super::*;
use std::path::Path;
use unicode_casefold::UnicodeCaseFold;
fn fold(s: &str) -> String {
    s.case_fold().collect()
}
fn terms(text: &str) -> HashSet<String> {
    let stops: HashSet<&str> =
        "the and for from with this that today please update updated review notes needs into your"
            .split_whitespace()
            .collect();
    regex::Regex::new(r"[\p{L}\p{N}]+")
        .unwrap()
        .find_iter(&fold(text))
        .map(|m| m.as_str().to_string())
        .filter(|t| {
            t.chars().count() > 2 && !stops.contains(t.as_str()) && !t.chars().all(char::is_numeric)
        })
        .collect()
}
fn clean_path(path: &Path) -> String {
    let raw = path.to_string_lossy();
    if let Some(p) = raw.strip_prefix(r"\\?\UNC\") {
        format!(r"\\{p}")
    } else {
        raw.strip_prefix(r"\\?\").unwrap_or(&raw).to_string()
    }
}
fn quote(text: &str) -> String {
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
fn read(root: &Path, note: &str, max: usize) -> Result<Value> {
    let path = root.join(note).canonicalize()?;
    ensure!(
        path.starts_with(root)
            && path.extension().map(|e| e.to_string_lossy().to_lowercase()) == Some("md".into()),
        "Read only Markdown notes inside the configured Second Brain"
    );
    let relative = path.strip_prefix(root)?;
    ensure!(
        !relative
            .components()
            .any(|p| p.as_os_str().to_string_lossy().starts_with(['.', '_'])),
        "Hidden or archived notes are excluded"
    );
    ensure!(
        fs::metadata(&path)?.len() <= 128 * 1024,
        "Note exceeds the bounded reader's size limit"
    );
    let text = fs::read_to_string(&path)?
        .trim_start_matches('\u{feff}')
        .replace("\r\n", "\n");
    let front = regex::Regex::new(r"(?s)\A---\s*\n(.*?)\n---\s*\n").unwrap();
    let capture = front.captures(&text);
    let (meta, body) = if let Some(ref c) = capture {
        (c.get(1).unwrap().as_str(), &text[c.get(0).unwrap().end()..])
    } else {
        ("", text.as_str())
    };
    let title_re = regex::Regex::new(r"(?m)^title:\s*(.+)$").unwrap();
    let heading_re = regex::Regex::new(r"(?m)^#\s+(.+)$").unwrap();
    let date_re = regex::Regex::new(r"(?m)^(?:updated|source_date):\s*(.+)$").unwrap();
    let title = title_re
        .captures(meta)
        .map(|c| c[1].trim_matches([' ', '"', '\'']).to_string())
        .or_else(|| heading_re.captures(body).map(|c| c[1].to_string()))
        .unwrap_or_else(|| path.file_stem().unwrap().to_string_lossy().into_owned());
    let updated = date_re
        .captures(meta)
        .map(|c| c[1].trim_matches([' ', '"', '\'']).to_string());
    Ok(obj(vec![
        ("note", json!(relative.to_string_lossy().replace('\\', "/"))),
        ("title", json!(title)),
        ("updated", json!(updated)),
        (
            "url",
            json!(format!(
                "obsidian://open?path={}",
                quote(&clean_path(&path))
            )),
        ),
        ("text", json!(cut(body.trim(), max))),
        ("truncated", json!(body.trim().chars().count() > max)),
    ]))
}
fn excerpt(text: &str, query: &HashSet<String>, max: usize) -> String {
    let text = regex::Regex::new(r"\s+")
        .unwrap()
        .replace_all(text, " ")
        .trim()
        .to_string();
    let chars: Vec<char> = text.chars().collect();
    if max < 4 || chars.len() <= max {
        return chars.into_iter().take(max).collect();
    }
    let pattern = regex::Regex::new(r"[\p{L}\p{N}]+").unwrap();
    let matched = pattern
        .find_iter(&text)
        .find(|m| query.contains(&fold(m.as_str())));
    let mut start = matched
        .map(|m| text[..m.start()].chars().count().saturating_sub(max / 4))
        .unwrap_or(0);
    if start > 0 && !chars[start - 1].is_whitespace() {
        start = chars[start..]
            .iter()
            .position(|c| *c == ' ')
            .map(|i| start + i + 1)
            .unwrap_or(0)
    }
    let prefix = if start > 0 { "… " } else { "" };
    let available = max - prefix.chars().count();
    if chars.len() - start <= available {
        return format!("{prefix}{}", chars[start..].iter().collect::<String>());
    }
    let text: String = chars[start..start + available - 2].iter().collect();
    let passage = text.rsplit_once(' ').map(|(p, _)| p).unwrap_or(&text);
    format!("{prefix}{passage} …")
}
fn scan(
    root: &Path,
    dir: &Path,
    notes: &mut Vec<Value>,
    count: &mut usize,
    dirs: &mut usize,
) -> Result<()> {
    if *dirs >= 1000 || *count > 1000 {
        return Ok(());
    }
    *dirs += 1;
    let mut entries: Vec<_> = fs::read_dir(dir)?.filter_map(Result::ok).collect();
    entries.sort_by_key(|e| e.file_name());
    for e in &entries {
        let name = e.file_name().to_string_lossy().into_owned();
        if name.starts_with(['.', '_']) || !name.to_lowercase().ends_with(".md") {
            continue;
        }
        if !e.path().is_file() {
            continue;
        }
        *count += 1;
        if *count > 1000 {
            break;
        }
        if let Ok(note) = read(
            root,
            &e.path().strip_prefix(root)?.to_string_lossy(),
            128 * 1024,
        ) {
            notes.push(note)
        }
    }
    for e in entries {
        if e.file_name().to_string_lossy().starts_with(['.', '_']) || !e.file_type()?.is_dir() {
            continue;
        }
        let metadata = fs::symlink_metadata(e.path())?;
        if metadata.file_type().is_symlink() {
            continue;
        }
        #[cfg(windows)]
        {
            use std::os::windows::fs::MetadataExt;
            if metadata.file_attributes() & 0x400 != 0 {
                continue;
            }
        }
        scan(root, &e.path(), notes, count, dirs)?
    }
    Ok(())
}
pub(super) fn run(a: &Args) -> Result<Value> {
    let state = PathBuf::from(env::var("COS_STATE_DIR")?);
    ensure!(
        state.is_absolute() && state.is_dir(),
        "COS_STATE_DIR must point to an existing absolute workspace directory."
    );
    let config: Value =
        serde_json::from_str(&fs::read_to_string(state.join("second-brain.json"))?)?;
    let mut root = PathBuf::from(s(&config["vault_path"]));
    if !root.is_absolute() {
        root = state.join(root)
    }
    let root = root.canonicalize()?;
    ensure!(
        root.is_dir(),
        "Configured Second Brain folder is unavailable"
    );
    if a.command == "read" {
        return read(&root, a.id()?, a.number("max-chars", 4000)?.clamp(1, 8000));
    }
    let query = terms(a.id()?);
    if query.is_empty() {
        return Ok(json!({"notes":[]}));
    }
    let mut notes = vec![];
    scan(&root, &root, &mut notes, &mut 0, &mut 0)?;
    let mut ranked = vec![];
    for note in notes {
        let title = terms(s(&note["title"]));
        let body = terms(s(&note["text"]));
        let th = query.intersection(&title).count();
        let bh = query.intersection(&body).count();
        if th < 2.min(query.len()) && bh < 1.max(3.min(query.len())) {
            continue;
        }
        let score = 4. * th as f64 / (title.len().max(1) as f64).sqrt()
            + bh as f64 / (body.len().max(1) as f64).sqrt();
        ranked.push((score, note))
    }
    ranked.sort_by(|(a, av), (b, bv)| b.total_cmp(a).then(s(&av["note"]).cmp(s(&bv["note"]))));
    let results: Vec<_> = ranked
        .into_iter()
        .take(a.number("max", 3)?.clamp(1, 5))
        .map(|(_, mut note)| {
            let passage = excerpt(s(&note["text"]), &query, 280);
            let o = note.as_object_mut().unwrap();
            o.shift_remove("text");
            o.shift_remove("truncated");
            o.insert("excerpt".into(), json!(passage));
            note
        })
        .collect();
    Ok(json!({"notes":results}))
}

pub fn context(packet: &Value) -> Option<Value> {
    let result = (|| -> Result<Option<Value>> {
        let state = state_dir()?;
        let config = state.join("second-brain.json");
        if !config.exists() {
            return Ok(None);
        }
        let config: Value = serde_json::from_str(&fs::read_to_string(config)?)?;
        let mut root = PathBuf::from(
            config["vault_path"]
                .as_str()
                .context("Missing vault_path")?,
        );
        if !root.is_absolute() {
            root = state.join(root)
        }
        let root = root.canonicalize()?;
        ensure!(
            root.is_dir(),
            "Configured Second Brain folder is unavailable"
        );
        let mut notes = vec![];
        scan(&root, &root, &mut notes, &mut 0, &mut 0)?;
        let mut queries = vec![];
        for (list, key) in [
            ("mail", "subject"),
            ("recent_files", "name"),
            ("meetings", "title"),
        ] {
            queries.extend(items(&packet[list]).iter().map(|v| s(&v[key]).to_string()));
        }
        let mut selected = vec![];
        let mut used = HashSet::new();
        for query in queries {
            let query = terms(&query);
            if query.is_empty() {
                continue;
            }
            let mut ranked = vec![];
            for note in &notes {
                if used.contains(s(&note["note"])) {
                    continue;
                }
                let title = terms(s(&note["title"]));
                let text = terms(s(&note["text"]));
                let th = query.intersection(&title).count();
                let bh = query.intersection(&text).count();
                if th < 2.min(query.len()) && bh < 1.max(3.min(query.len())) {
                    continue;
                }
                let score = 4. * th as f64 / (title.len().max(1) as f64).sqrt()
                    + bh as f64 / (text.len().max(1) as f64).sqrt();
                ranked.push((score, note));
            }
            ranked.sort_by(|(a, av), (b, bv)| {
                b.total_cmp(a).then(s(&av["note"]).cmp(s(&bv["note"])))
            });
            if let Some((_, n)) = ranked.first() {
                let mut n = (*n).clone();
                used.insert(s(&n["note"]).to_string());
                let passage = excerpt(s(&n["text"]), &query, 280);
                let o = n.as_object_mut().unwrap();
                o.shift_remove("text");
                o.shift_remove("truncated");
                o.insert("excerpt".into(), json!(passage));
                selected.push(n);
            }
            if selected.len() >= 5 {
                break;
            }
        }
        let mut out = json!({"status":"ok","role":"Background notes, not live status or write authorization.","notes":selected});
        while out.to_string().chars().count() > 3000 && !items(&out["notes"]).is_empty() {
            out["notes"].as_array_mut().unwrap().pop();
        }
        if items(&out["notes"]).is_empty() {
            out["status"] = json!("ok_empty");
        }
        Ok(Some(out))
    })();
    match result {
        Ok(v) => v,
        Err(e) => Some(json!({"status":"error","error":e.to_string()})),
    }
}
