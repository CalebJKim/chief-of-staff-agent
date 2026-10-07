use super::*;
pub fn run(api: &Api, a: &Args) -> Result<Value> {
    a.confirm()?;
    let id = if a.group == "calendar" { "" } else { a.id()? };
    match (a.group.as_str(), a.command.as_str()) {
        ("docs", "append") => {
            let doc = api.get(
                &format!("https://docs.googleapis.com/v1/documents/{}", enc(id)),
                vec![],
            )?;
            let end = items(&doc["body"]["content"])
                .last()
                .and_then(|b| b["endIndex"].as_i64())
                .unwrap_or(1)
                .saturating_sub(1)
                .max(1);
            let text = a.required("text")?;
            api.post(
                &format!(
                    "https://docs.googleapis.com/v1/documents/{}:batchUpdate",
                    enc(id)
                ),
                json!({"requests":[{"insertText":{"location":{"index":end},"text":text}}]}),
            )?;
            Ok(json!({"status":"appended","document_id":id,"characters":text.chars().count()}))
        }
        ("docs" | "slides", "replace-text") => {
            let mut replacement = json!({"containsText":{"text":a.required("find")?,"matchCase":a.opts.contains_key("match-case")},"replaceText":a.required("replace")?});
            if a.group == "slides" {
                if let Some(slide) = a.opts.get("slide-id") {
                    ensure!(
                        !slide.trim().is_empty(),
                        "--slide-id cannot be empty; use an object_id returned by slides get"
                    );
                    replacement["pageObjectIds"] = json!([slide]);
                }
            }
            let url = if a.group == "docs" {
                format!(
                    "https://docs.googleapis.com/v1/documents/{}:batchUpdate",
                    enc(id)
                )
            } else {
                format!(
                    "https://slides.googleapis.com/v1/presentations/{}:batchUpdate",
                    enc(id)
                )
            };
            let r = api.post(&url, json!({"requests":[{"replaceAllText":replacement}]}))?;
            let n: i64 = items(&r["replies"])
                .iter()
                .map(|v| {
                    v["replaceAllText"]["occurrencesChanged"]
                        .as_i64()
                        .unwrap_or(0)
                })
                .sum();
            if a.group == "slides" {
                ensure!(
                    n > 0,
                    "No matching slide text was replaced; read the intended slide and correct the target before continuing"
                );
            }
            let mut out = json!({"status":"updated","occurrences_changed":n});
            out[if a.group == "docs" {
                "document_id"
            } else {
                "presentation_id"
            }] = json!(id);
            Ok(out)
        }
        ("slides", "delete") => {
            let slide = a.required("slide-id")?;
            let deck = api.get(
                &format!("https://slides.googleapis.com/v1/presentations/{}", enc(id)),
                vec![("fields", "revisionId,slides(objectId)".into())],
            )?;
            ensure!(
                items(&deck["slides"])
                    .iter()
                    .any(|s| s["objectId"] == slide),
                "Slide not found in this presentation; read the deck again before deleting"
            );
            let mut request = json!({"requests":[{"deleteObject":{"objectId":slide}}]});
            if !s(&deck["revisionId"]).is_empty() {
                request["writeControl"] = json!({"requiredRevisionId":deck["revisionId"]});
            }
            api.post(
                &format!(
                    "https://slides.googleapis.com/v1/presentations/{}:batchUpdate",
                    enc(id)
                ),
                request,
            )?;
            Ok(json!({"status":"deleted","presentation_id":id,"slide_id":slide}))
        }
        ("calendar", "create") => {
            let mut event = json!({"summary":a.required("title")?,"start":{"dateTime":a.required("start")?},"end":{"dateTime":a.required("end")?}});
            let description = a.option("description", "");
            if !description.is_empty() {
                event["description"] = json!(description);
            }
            let attendees = a.option("attendees", "");
            if !attendees.is_empty() {
                event["attendees"] = json!(
                    attendees
                        .split(',')
                        .map(str::trim)
                        .filter(|s| !s.is_empty())
                        .map(|s| json!({"email":s}))
                        .collect::<Vec<_>>()
                );
            }
            let r = api.call(
                Method::POST,
                &format!(
                    "https://www.googleapis.com/calendar/v3/calendars/{}/events",
                    enc(a.option("calendar", "primary"))
                ),
                &[(
                    "sendUpdates".into(),
                    if attendees.is_empty() { "none" } else { "all" }.into(),
                )],
                Some(event),
            )?;
            Ok(json!({"status":"created","id":r["id"],"url":r["htmlLink"]}))
        }
        _ => bail!("Unsupported mutation"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn args(args: &[&str]) -> Args {
        cli::from_matches(&cli::command().try_get_matches_from(args).unwrap()).unwrap()
    }
    #[test]
    fn guarded_document_and_slide_writes() {
        let mut a = args(&["cos-actions", "docs", "append", "doc", "--text", "Résumé"]);
        let api = Api::mock(vec![
            json!({"body":{"content":[{"endIndex":12}]}}),
            json!({}),
        ]);
        assert!(run(&api, &a).is_err());
        assert!(api.calls().is_empty());
        a.opts.insert("confirm".into(), "true".into());
        assert_eq!(run(&api, &a).unwrap()["characters"], 6);
        assert_eq!(
            api.calls()[1]["body"]["requests"][0]["insertText"]["location"]["index"],
            11
        );
        let a = args(&[
            "cos-actions",
            "slides",
            "replace-text",
            "deck",
            "--slide-id",
            "slide",
            "--find",
            "Old",
            "--replace",
            "New",
            "--confirm",
        ]);
        let api = Api::mock(vec![
            json!({"replies":[{"replaceAllText":{"occurrencesChanged":1}}]}),
        ]);
        assert_eq!(run(&api, &a).unwrap()["occurrences_changed"], 1);
        assert_eq!(
            api.calls()[0]["body"]["requests"][0]["replaceAllText"]["pageObjectIds"],
            json!(["slide"])
        );
        assert!(run(&Api::mock(vec![json!({"replies":[]})]), &a).is_err());
    }
    #[test]
    fn delete_uses_revision_and_refuses_wrong_slide() {
        let a = args(&[
            "cos-actions",
            "slides",
            "delete",
            "deck",
            "--slide-id",
            "slide",
            "--confirm",
        ]);
        let api = Api::mock(vec![
            json!({"revisionId":"revision","slides":[{"objectId":"slide"}]}),
            json!({}),
        ]);
        run(&api, &a).unwrap();
        assert_eq!(
            api.calls()[1]["body"]["writeControl"]["requiredRevisionId"],
            "revision"
        );
        let api = Api::mock(vec![json!({"slides":[]})]);
        assert!(run(&api, &a).is_err());
        assert_eq!(api.calls().len(), 1);
    }
    #[test]
    fn calendar_attendee_contract_mock_only() {
        for (extra, send) in [
            (vec![], "none"),
            (
                vec!["--attendees", "one@example.com, two@example.com"],
                "all",
            ),
        ] {
            let mut input = vec![
                "cos-actions",
                "calendar",
                "create",
                "--title",
                "Review",
                "--start",
                "2026-10-08T09:00:00-07:00",
                "--end",
                "2026-10-08T10:00:00-07:00",
                "--confirm",
            ];
            input.extend(extra);
            let api = Api::mock(vec![
                json!({"id":"event", "htmlLink":"https://example.com"}),
            ]);
            assert_eq!(run(&api, &args(&input)).unwrap()["status"], "created");
            assert_eq!(api.calls()[0]["query"], json!([["sendUpdates", send]]));
        }
    }
}
