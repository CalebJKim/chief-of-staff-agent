use super::*;
use mailparse::MailHeaderMap;

// Keep batches small to limit per-user concurrent requests and response sizes.
pub const BATCH_SIZE: usize = 10;
const ENDPOINT: &str = "https://gmail.googleapis.com/batch/gmail/v1";
const BOUNDARY: &str = "cos_gmail_read_batch";

pub fn unique_ids(ids: &[String]) -> Vec<String> {
    let mut seen = HashSet::new();
    ids.iter()
        .filter(|id| seen.insert(id.as_str()))
        .cloned()
        .collect()
}

fn request_body(ids: &[String]) -> String {
    let mut body = String::new();
    for (i, id) in ids.iter().enumerate() {
        body.push_str(&format!(
            "--{BOUNDARY}\r\nContent-Type: application/http\r\nContent-ID: <cos-{i}>\r\n\r\nGET /gmail/v1/users/me/threads/{}?format=full HTTP/1.1\r\nAccept: application/json\r\n\r\n",
            enc(id)
        ));
    }
    body.push_str(&format!("--{BOUNDARY}--\r\n"));
    body
}

impl Api {
    fn gmail_batch_post(&self, body: String) -> Result<(String, Vec<u8>)> {
        let content_type = format!("multipart/mixed; boundary={BOUNDARY}");
        #[cfg(test)]
        if let Some(mock) = &self.mock {
            let mut mock = mock.lock().unwrap();
            mock.calls.push(
                json!({"method":"POST","url":ENDPOINT,"content_type":content_type,"body":body}),
            );
            let response = mock
                .responses
                .pop_front()
                .context("Unexpected batch API call")?;
            if let Some(error) = response.get("__error") {
                bail!("Mock batch API error: {error}");
            }
            return Ok((
                s(&response["content_type"]).into(),
                s(&response["body"]).as_bytes().to_vec(),
            ));
        }
        let response = self
            .client
            .post(ENDPOINT)
            .bearer_auth(&self.token)
            .header(reqwest::header::CONTENT_TYPE, content_type)
            .body(body)
            .send()?;
        let status = response.status();
        ensure!(
            status.is_success(),
            "Gmail batch request failed (HTTP {status}); thread reads were not confirmed"
        );
        let content_type = response
            .headers()
            .get(reqwest::header::CONTENT_TYPE)
            .context("Gmail batch response missing Content-Type")?
            .to_str()?
            .to_string();
        Ok((content_type, response.bytes()?.to_vec()))
    }
}

pub fn read_threads(api: &Api, ids: &[String]) -> Result<Vec<Result<Value>>> {
    ensure!(
        !ids.is_empty() && ids.len() <= BATCH_SIZE,
        "Invalid Gmail batch size"
    );
    let (content_type, body) = api.gmail_batch_post(request_body(ids))?;
    parse_response(&content_type, &body, ids)
}

// Internal, read-only Gmail requests. Callers construct paths and encode every
// user-supplied query value; Content-ID preserves order in reordered responses.
pub fn get_many(api: &Api, paths: &[String]) -> Result<Vec<Result<Value>>> {
    ensure!(!paths.is_empty() && paths.len() <= BATCH_SIZE, "Invalid Gmail batch size");
    let mut request = String::new();
    for (i, path) in paths.iter().enumerate() {
        ensure!(path.starts_with("/gmail/v1/users/me/") && !path.contains(['\r', '\n', ' ']),
            "Invalid Gmail batch read path");
        request.push_str(&format!(
            "--{BOUNDARY}\r\nContent-Type: application/http\r\nContent-ID: <cos-{i}>\r\n\r\nGET {path} HTTP/1.1\r\nAccept: application/json\r\n\r\n"
        ));
    }
    request.push_str(&format!("--{BOUNDARY}--\r\n"));
    let (content_type, body) = api.gmail_batch_post(request)?;
    parse_response(&content_type, &body, &vec![String::new(); paths.len()])
}

fn parse_response(content_type: &str, body: &[u8], ids: &[String]) -> Result<Vec<Result<Value>>> {
    ensure!(
        !content_type.contains(['\r', '\n']),
        "Invalid Gmail batch Content-Type"
    );
    let kind = mailparse::parse_content_type(content_type);
    ensure!(
        kind.mimetype.eq_ignore_ascii_case("multipart/mixed"),
        "Expected multipart Gmail batch response"
    );
    let boundary = kind
        .params
        .get("boundary")
        .filter(|b| !b.is_empty())
        .context("Missing Gmail batch boundary")?;
    let closing = format!("--{boundary}--");
    ensure!(
        body.split(|b| *b == b'\n')
            .any(|line| line.strip_suffix(b"\r").unwrap_or(line) == closing.as_bytes()),
        "Incomplete Gmail batch response"
    );
    let mut mime = format!("Content-Type: {content_type}\r\n\r\n").into_bytes();
    mime.extend_from_slice(body);
    let parsed = mailparse::parse_mail(&mime)?;
    ensure!(
        parsed.subparts.len() == ids.len(),
        "Gmail batch returned missing or unexpected thread results"
    );
    let mut results: Vec<Option<Result<Value>>> = (0..ids.len()).map(|_| None).collect();
    for part in &parsed.subparts {
        ensure!(
            part.ctype.mimetype.eq_ignore_ascii_case("application/http"),
            "Unexpected Gmail batch part type"
        );
        let content_id = part
            .headers
            .get_first_value("Content-ID")
            .context("Missing Gmail batch Content-ID")?;
        let index: usize = content_id
            .trim()
            .trim_start_matches('<')
            .trim_end_matches('>')
            .strip_prefix("response-cos-")
            .context("Unknown Gmail batch Content-ID")?
            .parse()?;
        ensure!(
            index < ids.len() && results[index].is_none(),
            "Unknown or duplicate Gmail batch result"
        );
        let raw = part.get_body_raw()?;
        results[index] = Some(parse_part(&raw, &ids[index]));
    }
    results
        .into_iter()
        .map(|v| v.context("Missing Gmail thread result"))
        .collect()
}

fn parse_part(raw: &[u8], id: &str) -> Result<Value> {
    let text = std::str::from_utf8(raw).context("Invalid UTF-8 in Gmail batch part")?;
    let (headers, body) = text
        .split_once("\r\n\r\n")
        .or_else(|| text.split_once("\n\n"))
        .context("Malformed Gmail batch HTTP response")?;
    let mut status = headers.lines().next().unwrap_or("").split_whitespace();
    ensure!(
        status.next() == Some("HTTP/1.1"),
        "Invalid Gmail batch HTTP status line"
    );
    let code: u16 = status
        .next()
        .context("Missing Gmail batch HTTP status")?
        .parse()?;
    ensure!(
        (200..300).contains(&code),
        "Gmail thread {id} failed (HTTP {code}); its contents were not read"
    );
    let value: Value = serde_json::from_str(body)
        .with_context(|| format!("Invalid JSON for Gmail thread {id}"))?;
    ensure!(
        id.is_empty() || s(&value["id"]) == id,
        "Gmail batch returned the wrong thread for {id}"
    );
    Ok(value)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn response(parts: Vec<(usize, u16, Value)>) -> Value {
        let mut body = String::new();
        for (i, code, value) in parts {
            body.push_str(&format!("--response_boundary\r\nContent-Type: application/http\r\nContent-ID: <response-cos-{i}>\r\n\r\nHTTP/1.1 {code} Status\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{value}\r\n"));
        }
        body.push_str("--response_boundary--\r\n");
        json!({"content_type":"multipart/mixed; boundary=\"response_boundary\"","body":body})
    }
    fn args(ids: &[&str]) -> Args {
        let mut argv = vec!["cos-actions", "gmail", "threads"];
        argv.extend(ids);
        argv.extend(["--max-messages", "1", "--max-chars", "4"]);
        cli::from_matches(&cli::command().try_get_matches_from(argv).unwrap()).unwrap()
    }
    #[test]
    fn one_http_request_preserves_order_unicode_limits_and_output_contract() {
        let a = args(&["abc", "def", "abc"]);
        let ids = unique_ids(&a.pos);
        let thread = json!({"id":"abc","messages":[
            {"id":"old","payload":{}},
            {"id":"new","payload":{"mimeType":"text/plain","headers":[{"name":"Subject","value":"Café"}],
                "body":{"data":URL_SAFE_NO_PAD.encode("Café notes")}}}
        ]});
        let api = Api::mock(vec![response(vec![
            (1, 200, json!({"id":"def","messages":[]})),
            (0, 200, thread.clone()),
        ])]);
        let received: Vec<_> = read_threads(&api, &ids)
            .unwrap()
            .into_iter()
            .map(Result::unwrap)
            .collect();
        assert_eq!(received[0], thread);
        assert_eq!(received[1]["id"], "def");
        let view = thread_view(&received[0], "abc", &a).unwrap();
        assert_eq!(view["messages"].as_array().unwrap().len(), 1);
        assert_eq!(view["messages"][0]["body"], "Café");
        assert_eq!(view["messages"][0]["subject"], "Café");
        assert_eq!(api.calls().len(), 1);
        let request = &api.calls()[0];
        assert_eq!(request["url"], ENDPOINT);
        assert_eq!(s(&request["body"]).matches("GET /gmail/").count(), 2);
        assert!(s(&request["body"]).contains("threads/abc?format=full HTTP/1.1"));
    }
    #[test]
    fn bounded_batches_and_global_deduplication() {
        let ids: Vec<_> = (0..23).map(|i| format!("id{i}")).collect();
        let mut all = ids.clone();
        all.push(ids[0].clone());
        let refs: Vec<_> = all.iter().map(String::as_str).collect();
        let a = args(&refs);
        let replies = ids
            .chunks(BATCH_SIZE)
            .map(|group| {
                response(
                    group
                        .iter()
                        .enumerate()
                        .map(|(i, id)| (i, 200, json!({"id":id,"messages":[]})))
                        .collect(),
                )
            })
            .collect();
        let api = Api::mock(replies);
        dispatch(&api, &a).unwrap();
        let sizes: Vec<_> = api
            .calls()
            .iter()
            .map(|call| s(&call["body"]).matches("GET /gmail/").count())
            .collect();
        assert_eq!(sizes, vec![10, 10, 3]);
    }
    #[test]
    fn partial_http_failures_are_explicit_without_retries() {
        for code in [401, 403, 404, 429, 500] {
            let api = Api::mock(vec![response(vec![
                (0, 200, json!({"id":"abc"})),
                (1, code, json!({"error":"failure"})),
            ])]);
            let results = read_threads(&api, &["abc".into(), "def".into()]).unwrap();
            assert!(results[0].is_ok());
            let error = results[1].as_ref().unwrap_err().to_string();
            assert!(error.contains("thread def") && error.contains(&code.to_string()));
            assert_eq!(api.calls().len(), 1);
        }
    }
    #[test]
    fn malformed_missing_duplicate_and_wrong_thread_results_are_rejected() {
        let ids = vec!["abc".into(), "def".into()];
        for reply in [
            response(vec![(0, 200, json!({"id":"abc"}))]),
            response(vec![
                (0, 200, json!({"id":"abc"})),
                (0, 200, json!({"id":"def"})),
            ]),
            json!({"content_type":"application/json","body":"{}"}),
            json!({"content_type":"multipart/mixed; boundary=b","body":"--b\r\n"}),
        ] {
            assert!(read_threads(&Api::mock(vec![reply]), &ids).is_err());
        }
        assert!(parse_part(b"HTTP/1.1 200 OK\r\n\r\n{}", "abc").is_err());
        assert!(parse_part(b"HTTP/1.1 200 OK\r\n\r\n{bad", "abc").is_err());
        assert!(parse_part(b"not http", "abc").is_err());
    }
    #[test]
    fn ids_cannot_inject_requests() {
        let request = request_body(&["id\r\nGET /other".into()]);
        assert_eq!(request.matches("\r\nGET ").count(), 1);
        assert!(request.contains("id%0D%0AGET%20%2Fother"));
    }
}
