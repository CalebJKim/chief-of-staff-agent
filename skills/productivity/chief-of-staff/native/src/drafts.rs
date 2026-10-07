use super::*;
use mail_builder::{
    MessageBuilder,
    headers::{address::Address, raw::Raw},
};
use mailparse::{MailAddr, addrparse};
use unicode_casefold::UnicodeCaseFold;

fn addresses(value: &str) -> Result<Vec<(Option<String>, String)>> {
    ensure!(
        !value.contains(['\r', '\n']),
        "Email headers cannot contain line breaks"
    );
    let mut out = vec![];
    for entry in addrparse(value)?.iter() {
        match entry {
            MailAddr::Single(m) => out.push((m.display_name.clone(), m.addr.clone())),
            MailAddr::Group(g) => {
                for m in &g.addrs {
                    out.push((m.display_name.clone(), m.addr.clone()))
                }
            }
        }
    }
    Ok(out)
}
fn validate(value: &str, field: &str) -> Result<Vec<(Option<String>, String)>> {
    let a = addresses(value)
        .with_context(|| format!("{field} must include a complete email address"))?;
    ensure!(
        !a.is_empty()
            && a.iter().all(|(_, v)| v
                .rsplit_once('@')
                .is_some_and(|(l, r)| !l.is_empty() && !r.is_empty())),
        "{field} must include a complete email address; search Gmail or reply to a verified message instead"
    );
    Ok(a)
}
fn mailboxes(value: &str) -> Result<std::collections::BTreeSet<String>> {
    Ok(addresses(value)?
        .iter()
        .map(|(_, v)| v.trim().case_fold().collect())
        .collect())
}
fn as_header(value: &str) -> Result<Address<'static>> {
    Ok(Address::new_list(
        addresses(value)?
            .into_iter()
            .map(|(n, a)| Address::new_address(n, a))
            .collect(),
    ))
}
fn verify_recipients(api: &Api, values: &[&str]) -> Result<()> {
    let mut wanted = std::collections::BTreeSet::new();
    for v in values {
        if !v.is_empty() {
            wanted.extend(mailboxes(v)?);
        }
    }
    for address in wanted {
        let quoted = address.replace('\\', "\\\\").replace('"', "\\\"");
        let query = format!("-in:drafts {{from:\"{quoted}\" to:\"{quoted}\" cc:\"{quoted}\"}}");
        let refs = api.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            vec![("q", query), ("maxResults", "5".into())],
        )?;
        let mut verified = false;
        for r in items(&refs["messages"]).iter().take(5) {
            let m = api.message(s(&r["id"]), false)?;
            if items(&m["labelIds"]).iter().any(|l| l == "DRAFT") {
                continue;
            }
            for h in items(&m["payload"]["headers"]) {
                if ["from", "reply-to", "to", "cc"].contains(&s(&h["name"]).to_lowercase().as_str())
                    && mailboxes(s(&h["value"]))?.contains(&address)
                {
                    verified = true;
                    break;
                }
            }
            if verified {
                break;
            }
        }
        ensure!(
            verified,
            "Recipient {address:?} not verified in bounded non-draft Gmail evidence; use a verified address, or --allow-new-recipient only for an address explicitly supplied or confirmed by the user"
        );
    }
    Ok(())
}
pub fn list(api: &Api) -> Result<Value> {
    let mut drafts = vec![];
    let mut page = String::new();
    let mut seen = HashSet::new();
    loop {
        let mut q = vec![("maxResults", "500".into())];
        if !page.is_empty() {
            q.push(("pageToken", page.clone()));
        }
        let r = api.get("https://gmail.googleapis.com/gmail/v1/users/me/drafts", q)?;
        for reference in items(&r["drafts"]) {
            let draft = api.get(
                &format!(
                    "https://gmail.googleapis.com/gmail/v1/users/me/drafts/{}",
                    enc(s(&reference["id"]))
                ),
                vec![("format", "full".into())],
            )?;
            let m = &draft["message"];
            let h = headers(&m["payload"]);
            drafts.push(json!({"draft_id":draft["id"],"message_id":m["id"],"thread_id":m["threadId"],"url":mail_url(&m["threadId"]),"to":h.get("to").map(String::as_str).unwrap_or(""),"cc":h.get("cc").map(String::as_str).unwrap_or(""),"bcc":h.get("bcc").map(String::as_str).unwrap_or(""),"subject":h.get("subject").map(String::as_str).unwrap_or(""),"body":body(&m["payload"])}));
        }
        page = s(&r["nextPageToken"]).into();
        if page.is_empty() {
            break;
        }
        ensure!(
            seen.insert(page.clone()),
            "Repeated Gmail drafts page token; no complete draft list was returned"
        );
    }
    Ok(json!({"complete":true,"count":drafts.len(),"drafts":drafts}))
}
pub fn save(api: &Api, a: &Args) -> Result<Value> {
    let text = if let Some(file) = a.opts.get("body-file") {
        read_input(file)?
    } else {
        a.option("body", "").into()
    };
    ensure!(!text.trim().is_empty(), "A draft needs a nonempty body");
    let reply = a.option("reply-to-message", "");
    let expected = a.option("expected-to", "");
    let explicit = a.option("to", "");
    let cc = a.option("cc", "");
    ensure!(
        reply.is_empty() || !explicit.is_empty() || !expected.is_empty(),
        "A reply without --to requires --expected-to from the intended recipient's verified email address"
    );
    if !expected.is_empty() {
        validate(expected, "--expected-to")?;
    }
    let mut to = explicit.to_string();
    let mut subject = a.option("subject", "").to_string();
    let mut thread = a.option("thread-id", "").to_string();
    let mut message = MessageBuilder::new();
    if !reply.is_empty() {
        let original = api.get(
            &format!(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/{}",
                enc(reply)
            ),
            vec![
                ("format", "metadata".into()),
                ("metadataHeaders", "From".into()),
                ("metadataHeaders", "Reply-To".into()),
                ("metadataHeaders", "Subject".into()),
                ("metadataHeaders", "Message-ID".into()),
                ("metadataHeaders", "References".into()),
            ],
        )?;
        let h = headers(&original["payload"]);
        if to.is_empty() {
            to = h
                .get("reply-to")
                .filter(|s| !s.is_empty())
                .or(h.get("from"))
                .cloned()
                .unwrap_or_default();
        }
        if subject.is_empty() {
            let old = h.get("subject").cloned().unwrap_or_default();
            subject = if old.to_lowercase().starts_with("re:") {
                old
            } else {
                format!("Re: {old}")
            };
        }
        let mid = h.get("message-id").cloned().unwrap_or_default();
        let refs = [
            h.get("references").cloned().unwrap_or_default(),
            mid.clone(),
        ]
        .into_iter()
        .filter(|s| !s.is_empty())
        .collect::<Vec<_>>()
        .join(" ");
        ensure!(
            !mid.contains(['\r', '\n']) && !refs.contains(['\r', '\n']),
            "Unsafe reply headers"
        );
        if !mid.is_empty() {
            message = message.header("In-Reply-To", Raw::new(mid));
        }
        if !refs.is_empty() {
            message = message.header("References", Raw::new(refs));
        }
        if let Some(t) = original.get("threadId") {
            thread = s(t).into();
        }
    }
    ensure!(
        !to.is_empty() && !subject.is_empty(),
        "A draft needs recipients and a subject"
    );
    ensure!(
        !subject.contains(['\r', '\n']),
        "Email headers cannot contain line breaks"
    );
    validate(&to, "To")?;
    if !expected.is_empty() {
        ensure!(
            mailboxes(expected)? == mailboxes(&to)?,
            "Draft recipient mismatch: expected {expected:?}, resolved {to:?}. Read the intended thread and correct the source message or recipient before retrying"
        );
    }
    if !cc.is_empty() {
        validate(cc, "Cc")?;
    }
    if !a.opts.contains_key("allow-new-recipient") && (!explicit.is_empty() || !cc.is_empty()) {
        verify_recipients(api, &[explicit, cc])?;
    }
    message = message
        .to(as_header(&to)?)
        .subject(subject.clone())
        .text_body(if text.ends_with('\n') {
            text
        } else {
            format!("{text}\n")
        });
    if !cc.is_empty() {
        message = message.cc(as_header(cc)?);
    }
    let mut request = json!({"message":{"raw":URL_SAFE_NO_PAD.encode(message.write_to_vec()?)}});
    if !thread.is_empty() {
        request["message"]["threadId"] = json!(thread);
    }
    let result = api.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/drafts",
        request,
    )?;
    Ok(
        json!({"status":"drafted","to":to,"subject":subject,"draft_id":result["id"],"message_id":result["message"]["id"]}),
    )
}
#[cfg(test)]
mod tests {
    use super::*;
    fn args(v: &[&str]) -> Args {
        cli::from_matches(&cli::command().try_get_matches_from(v).unwrap()).unwrap()
    }
    #[test]
    fn reply_preserves_thread_unicode_and_recipient() {
        let api = Api::mock(vec![
            json!({"threadId":"t","payload":{"headers":[{"name":"Reply-To","value":"Leah <leah@example.com>"},{"name":"Subject","value":"Réseau"},{"name":"Message-ID","value":"<source@example.com>"}]}}),
            json!({"id":"draft","message":{"id":"message"}}),
        ]);
        let a = args(&[
            "cos-actions",
            "gmail",
            "draft",
            "--reply-to-message",
            "m",
            "--expected-to",
            "leah@example.com",
            "--body",
            "Hi Leah,\n\nRésumé — details.\n\nThanks",
        ]);
        let r = save(&api, &a).unwrap();
        assert_eq!(r["status"], "drafted");
        let calls = api.calls();
        assert_eq!(calls.len(), 2);
        assert_eq!(calls[1]["body"]["message"]["threadId"], "t");
        let raw = URL_SAFE_NO_PAD
            .decode(s(&calls[1]["body"]["message"]["raw"]))
            .unwrap();
        let m = mailparse::parse_mail(&raw).unwrap();
        assert!(m.get_body().unwrap().contains("Résumé — details."));
        use mailparse::MailHeaderMap;
        assert_eq!(m.headers.get_first_value("Subject").unwrap(), "Re: Réseau");
        assert_eq!(
            m.headers.get_first_value("In-Reply-To").unwrap(),
            "<source@example.com>"
        );
    }
    #[test]
    fn mismatch_and_unverified_never_write() {
        let api = Api::mock(vec![]);
        let a = args(&[
            "cos-actions",
            "gmail",
            "draft",
            "--to",
            "a@example.com",
            "--expected-to",
            "b@example.com",
            "--subject",
            "x",
            "--body",
            "Hi",
        ]);
        assert!(save(&api, &a).is_err());
        assert!(api.calls().is_empty());
        let api = Api::mock(vec![json!({"messages":[]})]);
        let a = args(&[
            "cos-actions",
            "gmail",
            "draft",
            "--to",
            "a@example.com",
            "--subject",
            "x",
            "--body",
            "Hi",
        ]);
        assert!(save(&api, &a).is_err());
        assert!(api.calls().iter().all(|c| c["method"] == "GET"));
    }
    #[test]
    fn listing_requires_all_pages() {
        let api = Api::mock(vec![
            json!({"drafts":[],"nextPageToken":"p"}),
            json!({"__error":"denied"}),
        ]);
        assert!(list(&api).is_err());
        let api = Api::mock(vec![
            json!({"drafts":[],"nextPageToken":"p"}),
            json!({"drafts":[]}),
        ]);
        assert_eq!(
            list(&api).unwrap(),
            json!({"complete":true,"count":0,"drafts":[]})
        );
    }
    #[test]
    fn new_draft_file_input_preserves_body_and_cc() {
        let folder = tempfile::tempdir().unwrap();
        let file = folder.path().join("body.txt");
        fs::write(&file, "Hi Leah,\r\n\r\nRésumé 🧭\r\n\r\n").unwrap();
        let a = args(&[
            "cos-actions",
            "gmail",
            "draft",
            "--to",
            "Leah <leah@example.com>",
            "--cc",
            "Pat <pat@example.com>",
            "--subject",
            "Project resources",
            "--body-file",
            file.to_str().unwrap(),
            "--allow-new-recipient",
        ]);
        let api = Api::mock(vec![json!({"id":"draft1","message":{"id":"message1"}})]);
        assert_eq!(save(&api, &a).unwrap()["draft_id"], "draft1");
        let calls = api.calls();
        assert_eq!(calls.len(), 1);
        assert_eq!(
            calls[0]["url"],
            "https://gmail.googleapis.com/gmail/v1/users/me/drafts"
        );
        let raw = URL_SAFE_NO_PAD
            .decode(s(&calls[0]["body"]["message"]["raw"]))
            .unwrap();
        let parsed = mailparse::parse_mail(&raw).unwrap();
        assert_eq!(
            parsed.get_body().unwrap().replace("\r\n", "\n"),
            "Hi Leah,\n\nRésumé 🧭\n\n"
        );
        use mailparse::MailHeaderMap;
        assert!(
            parsed
                .headers
                .get_first_value("Cc")
                .unwrap()
                .contains("pat@example.com")
        );
    }
    #[test]
    fn header_injection_never_writes() {
        let a = args(&[
            "cos-actions",
            "gmail",
            "draft",
            "--to",
            "a@example.com",
            "--subject",
            "Hello\r\nBcc: bad@example.com",
            "--body",
            "Hi",
            "--allow-new-recipient",
        ]);
        let api = Api::mock(vec![]);
        assert!(save(&api, &a).is_err());
        assert!(api.calls().is_empty());
    }
}
