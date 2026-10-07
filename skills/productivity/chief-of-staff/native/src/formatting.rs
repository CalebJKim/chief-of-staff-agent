use super::*;
fn merge(values: &[&Value]) -> Value {
    let mut out = json!({});
    for v in values {
        if let Some(o) = v.as_object() {
            for (k, v) in o {
                out[k] = v.clone();
            }
        }
    }
    out
}
fn num(v: &Value) -> i64 {
    v.as_i64().unwrap_or(0)
}
fn runs(elements: &Value) -> Vec<Value> {
    items(elements).iter().filter(|e|e.get("textRun").is_some()).map(|e|json!({"start":num(&e["startIndex"]),"end":num(&e["endIndex"]),"text":s(&e["textRun"]["content"]),"style":e["textRun"].get("textStyle").or(e["textRun"].get("style")).cloned().unwrap_or(json!({}))})).collect()
}
fn list_kind(b: &Value, lists: Option<&Value>) -> &'static str {
    if b.is_null() || b.as_object().is_some_and(|o| o.is_empty()) {
        return "none";
    }
    if let Some(lists) = lists {
        let n = b["nestingLevel"].as_u64().unwrap_or(0) as usize;
        let levels = items(&lists[s(&b["listId"])]["listProperties"]["nestingLevels"]);
        if let Some(l) = levels.get(n) {
            if !s(&l["glyphType"]).is_empty() {
                return "numbered";
            }
            if !s(&l["glyphSymbol"]).is_empty() {
                return "bulleted";
            }
        }
        return "unknown";
    }
    let glyph = s(&b["glyph"]);
    if glyph.is_empty() {
        "unknown"
    } else if regex::Regex::new(r"^[0-9A-Za-z]+[.)]?$")
        .unwrap()
        .is_match(glyph.trim())
    {
        "numbered"
    } else {
        "bulleted"
    }
}
fn paragraphs(content: &Value, tab: &Value, named: &Value, lists: &Value, out: &mut Vec<Value>) {
    for b in items(content) {
        if let Some(p) = b.get("paragraph") {
            let base = items(&named["styles"])
                .iter()
                .find(|v| v["namedStyleType"] == "NORMAL_TEXT")
                .cloned()
                .unwrap_or(json!({}));
            let name = p["paragraphStyle"]["namedStyleType"]
                .as_str()
                .unwrap_or("NORMAL_TEXT");
            let inherited = items(&named["styles"])
                .iter()
                .find(|v| v["namedStyleType"] == name)
                .cloned()
                .unwrap_or(json!({}));
            let mut r = runs(&p["elements"]);
            for run in &mut r {
                run["explicit_style"] = run["style"].clone();
                run["style"] = merge(&[&base["textStyle"], &inherited["textStyle"], &run["style"]]);
            }
            out.push(json!({"tab_id":tab,"start":num(&b["startIndex"]),"end":num(&b["endIndex"]),"runs":r,"paragraph_style":merge(&[&base["paragraphStyle"],&inherited["paragraphStyle"],&p["paragraphStyle"]]),"bullet":p["bullet"],"list_kind":list_kind(&p["bullet"],Some(lists))}));
        }
        for row in items(&b["table"]["tableRows"]) {
            for cell in items(&row["tableCells"]) {
                paragraphs(&cell["content"], tab, named, lists, out)
            }
        }
        if b.get("tableOfContents").is_some() {
            paragraphs(&b["tableOfContents"]["content"], tab, named, lists, out)
        }
    }
}
fn tabs(t: &Value, out: &mut Vec<Value>) {
    for tab in items(t) {
        let d = &tab["documentTab"];
        paragraphs(
            &d["body"]["content"],
            &tab["tabProperties"]["tabId"],
            &d["namedStyles"],
            &d["lists"],
            out,
        );
        tabs(&tab["childTabs"], out)
    }
}
fn elements(elems: &Value, slide: &Value, out: &mut Vec<Value>) {
    for e in items(elems) {
        elements(&e["elementGroup"]["children"], slide, out);
        let mut targets = vec![];
        if e.get("shape").is_some() {
            targets.push((Value::Null, e["shape"]["text"].clone()));
        }
        for (r, row) in items(&e["table"]["tableRows"]).iter().enumerate() {
            for (c, cell) in items(&row["tableCells"]).iter().enumerate() {
                targets.push((json!({"rowIndex":r,"columnIndex":c}), cell["text"].clone()));
            }
        }
        for (cell, text) in targets {
            let ps:Vec<_>=items(&text["textElements"]).iter().filter(|v|v.get("paragraphMarker").is_some()).map(|p|json!({"start":num(&p["startIndex"]),"end":num(&p["endIndex"]),"paragraph_style":p["paragraphMarker"].get("style").cloned().unwrap_or(json!({})),"bullet":p["paragraphMarker"]["bullet"],"list_kind":list_kind(&p["paragraphMarker"]["bullet"],None)})).collect();
            out.push(json!({"slide_id":slide,"element_id":e["objectId"],"cell":cell,"runs":runs(&text["textElements"]),"paragraphs":ps}));
        }
    }
}
pub fn records(kind: &str, data: &Value) -> Vec<Value> {
    let mut out = vec![];
    if kind == "docs" {
        if !items(&data["tabs"]).is_empty() {
            tabs(&data["tabs"], &mut out)
        } else {
            paragraphs(
                &data["body"]["content"],
                &Value::Null,
                &data["namedStyles"],
                &data["lists"],
                &mut out,
            )
        }
    } else {
        for slide in items(&data["slides"]) {
            elements(&slide["pageElements"], &slide["objectId"], &mut out)
        }
    }
    out
}
fn chunks(record: &Value) -> Vec<(i64, String)> {
    let mut out: Vec<(i64, String)> = vec![];
    for run in items(&record["runs"]) {
        if let Some(last) = out.last_mut() {
            if last.0 + last.1.encode_utf16().count() as i64 == num(&run["start"]) {
                last.1.push_str(s(&run["text"]));
                continue;
            }
        }
        out.push((num(&run["start"]), s(&run["text"]).into()));
    }
    out
}
fn selected(data: &Value, a: &Args) -> Vec<Value> {
    records(&a.group, data)
        .into_iter()
        .filter(|r| {
            ["tab-id", "slide-id", "element-id"].iter().all(|key| {
                a.option(key, "").is_empty() || r[key.replace('-', "_")] == a.option(key, "")
            })
        })
        .collect()
}
fn fetch(api: &Api, a: &Args) -> Result<Value> {
    let kind = if a.group == "docs" {
        "documents"
    } else {
        "presentations"
    };
    api.get(
        &format!(
            "https://{}.googleapis.com/v1/{}/{}",
            a.group,
            kind,
            enc(a.id()?)
        ),
        if a.group == "docs" {
            vec![("includeTabsContent", "true".into())]
        } else {
            vec![]
        },
    )
}
#[derive(Clone)]
struct Match {
    record: Value,
    start: i64,
    end: i64,
}
fn locate(records: &[Value], find: &str, all: bool) -> Result<Vec<Match>> {
    ensure!(
        !find.trim().is_empty(),
        "--find must contain nonempty literal text"
    );
    let mut out = vec![];
    for r in records {
        for (base, text) in chunks(r) {
            for (at, _) in text.match_indices(find) {
                out.push(Match {
                    record: r.clone(),
                    start: base + text[..at].encode_utf16().count() as i64,
                    end: base + text[..at + find.len()].encode_utf16().count() as i64,
                });
            }
        }
    }
    ensure!(!out.is_empty(), "No matching text. Nothing was changed.");
    ensure!(
        out.len() == 1 || all,
        "Ambiguous text: {} matches. Narrow the target or explicitly use --all-matches.",
        out.len()
    );
    ensure!(
        out.len() <= 100,
        "More than 100 matches. Narrow the target."
    );
    Ok(out)
}
fn styles(style: &Value, kind: &str) -> Result<(Value, Value)> {
    let object = style
        .as_object()
        .context("Style must be a nonempty JSON object")?;
    ensure!(!object.is_empty(), "Style must be a nonempty JSON object");
    let (mut text, mut para) = (json!({}), json!({}));
    for (k, v) in object {
        match k.as_str() {
            "bold" | "italic" | "underline" => {
                ensure!(v.is_boolean(), "{k} must be true or false");
                text[k] = v.clone();
            }
            "font_family" => {
                ensure!(!s(v).trim().is_empty(), "font_family must be nonempty");
                if kind == "docs" {
                    text["weightedFontFamily"] = json!({"fontFamily":v})
                } else {
                    text["fontFamily"] = v.clone()
                }
            }
            "font_size" | "space_before" | "space_after" | "line_spacing" => {
                let n = v
                    .as_f64()
                    .with_context(|| format!("{k} must be a finite number"))?;
                let (lo, hi) = match k.as_str() {
                    "font_size" => (1., 400.),
                    "line_spacing" => (50., 500.),
                    _ => (0., 400.),
                };
                ensure!(
                    n.is_finite() && (lo..=hi).contains(&n),
                    "{k} must be between {lo} and {hi}"
                );
                match k.as_str() {
                    "font_size" => text["fontSize"] = json!({"magnitude":v,"unit":"PT"}),
                    "line_spacing" => para["lineSpacing"] = v.clone(),
                    _ => {
                        para[if k == "space_before" {
                            "spaceAbove"
                        } else {
                            "spaceBelow"
                        }] = json!({"magnitude":v,"unit":"PT"})
                    }
                }
            }
            "color" => {
                let t = s(v);
                ensure!(
                    regex::Regex::new(r"^#[0-9A-Fa-f]{6}$").unwrap().is_match(t),
                    "color must be #RRGGBB"
                );
                let rgb = json!({"red":u8::from_str_radix(&t[1..3],16)? as f64/255.,"green":u8::from_str_radix(&t[3..5],16)? as f64/255.,"blue":u8::from_str_radix(&t[5..7],16)? as f64/255.});
                text["foregroundColor"] = if kind == "docs" {
                    json!({"color":{"rgbColor":rgb}})
                } else {
                    json!({"opaqueColor":{"rgbColor":rgb}})
                };
            }
            "link" => {
                ensure!(
                    v.is_null()
                        || regex::Regex::new(r"^https?://[^\s]+$")
                            .unwrap()
                            .is_match(s(v)),
                    "link must be an http(s) URL or null to remove it"
                );
                text["link"] = if v.is_null() {
                    Value::Null
                } else {
                    json!({"url":v})
                };
            }
            "alignment" => {
                ensure!(
                    ["START", "CENTER", "END", "JUSTIFIED"].contains(&s(v)),
                    "alignment must be START, CENTER, END, or JUSTIFIED"
                );
                para["alignment"] = v.clone();
            }
            "heading" if kind == "docs" => {
                let n = v
                    .as_u64()
                    .context("heading must be 0 (normal text) through 6")?;
                ensure!(n <= 6, "heading must be 0 (normal text) through 6");
                para["namedStyleType"] = json!(if n == 0 {
                    "NORMAL_TEXT".into()
                } else {
                    format!("HEADING_{n}")
                });
            }
            "list" => ensure!(
                ["bulleted", "numbered", "none"].contains(&s(v)),
                "list must be bulleted, numbered, or none"
            ),
            _ => bail!("Unsupported style properties: {k}"),
        }
    }
    Ok((text, para))
}
fn preserved(run: &Value, style: &Value) -> Result<Value> {
    let mut out = json!({});
    for (public, key) in [("color", "foregroundColor"), ("underline", "underline")] {
        if style.get(public).is_none() {
            ensure!(
                key != "foregroundColor" || run["style"].get(key).is_some(),
                "Cannot resolve existing text color for a link edit. Supply color explicitly."
            );
            out[key] = run["style"].get(key).cloned().unwrap_or(json!(false));
        }
    }
    Ok(out)
}
fn keys(v: &Value) -> Vec<String> {
    let mut k: Vec<_> = v.as_object().unwrap().keys().cloned().collect();
    k.sort();
    k
}
fn requests(kind: &str, matches: &[Match], style: &Value) -> Result<Vec<Value>> {
    let (text, para) = styles(style, kind)?;
    let mut out = vec![];
    for m in matches {
        let r = &m.record;
        let mut target = if kind == "docs" {
            json!({"range":{"startIndex":m.start,"endIndex":m.end}})
        } else {
            json!({"objectId":r["element_id"],"textRange":{"type":"FIXED_RANGE","startIndex":m.start,"endIndex":m.end}})
        };
        if kind == "docs" && !r["tab_id"].is_null() {
            target["range"]["tabId"] = r["tab_id"].clone();
        }
        if kind == "slides" && !r["cell"].is_null() {
            target["cellLocation"] = r["cell"].clone();
        }
        if let Some(list) = style.get("list") {
            ensure!(
                !chunks(r)
                    .iter()
                    .any(|(_, t)| t.lines().any(|l| l.starts_with('\t'))),
                "List formatting of tab-indented text is unsupported; indices could shift. Nothing was changed."
            );
            if list == "none" {
                out.push(json!({"deleteParagraphBullets":target.clone()}))
            } else {
                let mut t = target.clone();
                t["bulletPreset"] = json!(if list == "bulleted" {
                    "BULLET_DISC_CIRCLE_SQUARE"
                } else if kind == "docs" {
                    "NUMBERED_DECIMAL_ALPHA_ROMAN"
                } else {
                    "NUMBERED_DIGIT_ALPHA_ROMAN"
                });
                out.push(json!({"createParagraphBullets":t}));
            }
        }
        for (is_text, v) in [(false, &para), (true, &text)] {
            if v.as_object().unwrap().is_empty() {
                continue;
            }
            let mut t = target.clone();
            let property = if kind == "slides" {
                "style"
            } else if is_text {
                "textStyle"
            } else {
                "paragraphStyle"
            };
            t[property] = Value::Object(
                v.as_object()
                    .unwrap()
                    .iter()
                    .filter(|(_, v)| !v.is_null())
                    .map(|(k, v)| (k.clone(), v.clone()))
                    .collect(),
            );
            t["fields"] = json!(
                keys(v)
                    .into_iter()
                    .map(|k| if k == "weightedFontFamily" {
                        "weightedFontFamily.fontFamily".into()
                    } else {
                        k
                    })
                    .collect::<Vec<_>>()
                    .join(",")
            );
            out.push(json!({if is_text{"updateTextStyle"}else{"updateParagraphStyle"}:t}));
        }
        if style.get("link").is_some() {
            for run in items(&r["runs"]) {
                let start = num(&run["start"]).max(m.start);
                let end = num(&run["end"]).min(m.end);
                if start >= end {
                    continue;
                }
                let keep = preserved(run, style)?;
                if keep.as_object().unwrap().is_empty() {
                    continue;
                }
                let mut t = target.clone();
                let span = if kind == "docs" { "range" } else { "textRange" };
                t[span]["startIndex"] = json!(start);
                t[span]["endIndex"] = json!(end);
                t[if kind == "docs" { "textStyle" } else { "style" }] = keep.clone();
                t["fields"] = json!(keys(&keep).join(","));
                out.push(json!({"updateTextStyle":t}));
            }
        }
    }
    Ok(out)
}
fn same(actual: &Value, expected: &Value) -> bool {
    if let Some(o) = expected.as_object() {
        return actual.is_object() && o.iter().all(|(k, v)| same(&actual[k], v));
    }
    if let Some(b) = expected.as_bool() {
        return actual.as_bool().unwrap_or(false) == b;
    }
    if let Some(n) = expected.as_f64() {
        return (actual.is_number() || actual.is_null())
            && (actual.as_f64().unwrap_or(0.) - n).abs() <= 0.0001;
    }
    actual == expected
}
fn identity(r: &Value) -> Value {
    if r.get("tab_id").is_some() {
        json!([r["tab_id"], r["start"]])
    } else {
        json!([r["slide_id"], r["element_id"], r["cell"]])
    }
}
fn overlaps(r: &Value, start: i64, end: i64) -> bool {
    num(&r["start"]) < end && num(&r["end"]) > start
}
fn verify(kind: &str, matches: &[Match], after: &[Value], style: &Value) -> Result<()> {
    let (text, para) = styles(style, kind)?;
    for m in matches {
        let old = &m.record;
        let new = after
            .iter()
            .find(|r| identity(r) == identity(old))
            .context("Formatting write completed, but read-back target changed")?;
        ensure!(
            chunks(old) == chunks(new),
            "Formatting write completed, but read-back text/target changed. Do not retry blindly."
        );
        let runs: Vec<_> = items(&new["runs"])
            .iter()
            .filter(|r| overlaps(r, m.start, m.end))
            .collect();
        if !text.as_object().unwrap().is_empty() {
            ensure!(
                !runs.is_empty() && runs.iter().all(|r| same(&r["style"], &text)),
                "Formatting write completed, but text-style verification failed."
            );
        }
        if style.get("link").is_some() {
            for r in items(&old["runs"]) {
                let start = num(&r["start"]).max(m.start);
                let end = num(&r["end"]).min(m.end);
                if start >= end {
                    continue;
                }
                let keep = preserved(r, style)?;
                let rs: Vec<_> = runs.iter().filter(|r| overlaps(r, start, end)).collect();
                ensure!(
                    !rs.is_empty() && rs.iter().all(|r| same(&r["style"], &keep)),
                    "Formatting write completed, but link edit changed unrelated color/underline."
                );
            }
        }
        let paragraphs: Vec<_> = if kind == "docs" {
            vec![new]
        } else {
            items(&new["paragraphs"])
                .iter()
                .filter(|p| overlaps(p, m.start, m.end))
                .collect()
        };
        if !para.as_object().unwrap().is_empty() {
            ensure!(
                !paragraphs.is_empty()
                    && paragraphs
                        .iter()
                        .all(|p| same(&p["paragraph_style"], &para)),
                "Formatting write completed, but paragraph-style verification failed."
            );
        }
        if let Some(list) = style.get("list") {
            ensure!(
                !paragraphs.is_empty() && paragraphs.iter().all(|p| p["list_kind"] == *list),
                "Formatting write completed, but list verification failed."
            );
        }
    }
    Ok(())
}
pub fn run(api: &Api, a: &Args) -> Result<Value> {
    if a.command == "inspect" {
        let data = fetch(api, a)?;
        let records: Vec<_> = selected(&data, a)
            .into_iter()
            .filter(|r| {
                a.option("find", "").is_empty()
                    || chunks(r)
                        .iter()
                        .any(|(_, t)| t.contains(a.option("find", "")))
            })
            .collect();
        let total = records.len();
        let mut selected = vec![];
        let mut used = 0;
        let mut truncated = false;
        for mut r in records {
            for run in r["runs"].as_array_mut().unwrap() {
                run.as_object_mut().unwrap().shift_remove("explicit_style");
                run["style"].as_object_mut().unwrap().retain(|k, _| {
                    [
                        "bold",
                        "italic",
                        "underline",
                        "fontFamily",
                        "weightedFontFamily",
                        "fontSize",
                        "foregroundColor",
                        "link",
                    ]
                    .contains(&k.as_str())
                });
            }
            let fields = [
                "namedStyleType",
                "alignment",
                "lineSpacing",
                "spaceAbove",
                "spaceBelow",
            ];
            if a.group == "docs" {
                r["paragraph_style"]
                    .as_object_mut()
                    .unwrap()
                    .retain(|k, _| fields.contains(&k.as_str()))
            } else {
                for p in r["paragraphs"].as_array_mut().unwrap() {
                    p["paragraph_style"]
                        .as_object_mut()
                        .unwrap()
                        .retain(|k, _| fields.contains(&k.as_str()));
                }
            }
            let len = r.to_string().chars().count();
            if selected.len() >= a.number("max-items", 20)?
                || used + len > a.number("max-chars", 12000)?
            {
                truncated = true;
                break;
            }
            used += len;
            selected.push(r);
        }
        return Ok(
            json!({"id":a.id()?,"title":data["title"],"revision_id":data["revisionId"],"records":selected,"matching_records":total,"truncated":truncated,"scope":if a.group=="docs"{"body paragraphs, including tables and document tabs"}else{"shape and table-cell text"}}),
        );
    }
    ensure!(
        a.opts.contains_key("confirm"),
        "Formatting requires --confirm after user approval"
    );
    let payload = if let Some(f) = a.opts.get("style-file") {
        read_input(f)?.trim_start_matches('\u{feff}').into()
    } else {
        a.required("style")?.to_string()
    };
    ensure!(
        payload.chars().count() <= 65536,
        "Style JSON exceeds 64 KiB"
    );
    let style: Value = serde_json::from_str(&payload)?;
    styles(&style, &a.group)?;
    let data = fetch(api, a)?;
    let matches = locate(
        &selected(&data, a),
        a.required("find")?,
        a.opts.contains_key("all-matches"),
    )?;
    let req = requests(&a.group, &matches, &style)?;
    ensure!(
        !s(&data["revisionId"]).is_empty(),
        "No revision ID returned; refusing an unguarded formatting write"
    );
    let path = if a.group == "docs" {
        "documents"
    } else {
        "presentations"
    };
    api.post(
        &format!(
            "https://{}.googleapis.com/v1/{}/{}:batchUpdate",
            a.group,
            path,
            enc(a.id()?)
        ),
        json!({"requests":req,"writeControl":{"requiredRevisionId":data["revisionId"]}}),
    )?;
    let after = fetch(api, a).context("Write succeeded; verification did not complete")?;
    verify(&a.group, &matches, &selected(&after, a), &style)
        .context("Write succeeded; verification did not complete")?;
    Ok(
        json!({"status":"formatting_verified","id":a.id()?,"matches":matches.len(),"properties":keys(&style),"visual_check":"not performed"}),
    )
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn python_contract_fixtures() {
        let cases: Value = serde_json::from_str(include_str!("../tests/formatting.json")).unwrap();
        for case in items(&cases) {
            let kind = s(&case["kind"]);
            let actual = records(kind, &case["data"]);
            assert_eq!(json!(actual), case["records"]);
            let matches = locate(&actual, "Target", true).unwrap();
            assert_eq!(
                json!(requests(kind, &matches, &case["style"]).unwrap()),
                case["requests"]
            );
        }
    }
    #[test]
    fn formatting_checks_revision_and_readback() {
        let before = json!({"revisionId":"r1","body":{"content":[{"startIndex":1,"endIndex":7,"paragraph":{"elements":[{"startIndex":1,"endIndex":7,"textRun":{"content":"Target","textStyle":{}}}]}}]}});
        let mut after = before.clone();
        after["body"]["content"][0]["paragraph"]["elements"][0]["textRun"]["textStyle"]["bold"] =
            json!(true);
        let a = cli::from_matches(
            &cli::command()
                .try_get_matches_from([
                    "cos-actions",
                    "docs",
                    "format",
                    "d",
                    "--find",
                    "Target",
                    "--style",
                    r#"{"bold":true}"#,
                    "--confirm",
                ])
                .unwrap(),
        )
        .unwrap();
        let api = Api::mock(vec![before.clone(), json!({}), after]);
        assert_eq!(run(&api, &a).unwrap()["status"], "formatting_verified");
        assert_eq!(
            api.calls()[1]["body"]["writeControl"]["requiredRevisionId"],
            "r1"
        );
        let api = Api::mock(vec![before.clone(), json!({}), before.clone()]);
        assert!(run(&api, &a).is_err());
        assert_eq!(api.calls().len(), 3); // No automatic retry after a write.
        let mut no_revision = before;
        no_revision
            .as_object_mut()
            .unwrap()
            .shift_remove("revisionId");
        let api = Api::mock(vec![no_revision]);
        assert!(run(&api, &a).is_err());
        assert_eq!(api.calls().len(), 1);
    }
    #[test]
    fn literal_utf16_and_guards() {
        let r = json!({"tab_id":null,"start":1,"runs":[{"start":1,"end":8,"text":"😀 hello","style":{}}]});
        let m = locate(&[r.clone()], "hello", false).unwrap();
        assert_eq!((m[0].start, m[0].end), (4, 9));
        assert!(locate(&[r.clone(), r], "hello", false).is_err());
        assert!(styles(&json!({"font_size":0}), "docs").is_err());
        assert!(styles(&json!({"heading":1}), "slides").is_err());
    }
    #[test]
    fn inherited_styles_and_revision() {
        let d = json!({"namedStyles":{"styles":[{"namedStyleType":"NORMAL_TEXT","textStyle":{"bold":true}}]},"body":{"content":[{"startIndex":1,"paragraph":{"elements":[{"startIndex":1,"endIndex":3,"textRun":{"content":"hi"}}]}}]}});
        assert_eq!(records("docs", &d)[0]["runs"][0]["style"]["bold"], true);
    }
}
