use super::*;

struct Request {
    key: String,
    query: String,
    limit: usize,
    thread_ids: Vec<String>,
}

fn requests(value: &Value, default_limit: usize) -> Result<Vec<Request>> {
    let rows = value.as_array().context("Expected a JSON array of search strings or request objects")?;
    ensure!(!rows.is_empty() && rows.len() <= 30, "Supply 1–30 evidence requests");
    let mut keys = HashSet::new();
    let mut result = vec![];
    for (i, row) in rows.iter().enumerate() {
        let (key, query, limit, thread_ids) = if let Some(query) = row.as_str() {
            (format!("query-{}", i + 1), query.to_string(), default_limit, vec![])
        } else {
            let object = row.as_object().context("Each evidence request must be a string or object")?;
            ensure!(object.keys().all(|key| ["key", "query", "max", "thread_ids"].contains(&key.as_str())),
                "Supported request fields: key, query, max, thread_ids");
            let key = match object.get("key") {
                Some(v) => v.as_str().context("key must be a string")?.to_string(),
                None => format!("query-{}", i + 1),
            };
            let query = match object.get("query") {
                Some(v) => v.as_str().context("query must be a string")?.to_string(),
                None => String::new(),
            };
            let limit = match object.get("max") {
                Some(v) => v.as_u64().context("max must be an integer from 1 to 10")? as usize,
                None => default_limit,
            };
            let mut ids = vec![];
            if let Some(v) = object.get("thread_ids") {
                for id in v.as_array().context("thread_ids must be an array")? {
                    let id = id.as_str().context("Thread IDs must be strings")?;
                    ensure!(!id.is_empty() && id.len() <= 200 && id.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_'),
                        "Supply native thread IDs from prior results, not URLs");
                    ids.push(id.to_string());
                }
            }
            ensure!(ids.len() <= 10, "At most 10 known threads per request");
            (key, query, limit, gmail_batch::unique_ids(&ids))
        };
        ensure!(!key.trim().is_empty() && key.len() <= 200 && keys.insert(key.clone()), "Request keys must be nonempty and unique (maximum 200 bytes)");
        ensure!((1..=10).contains(&limit), "max must be from 1 to 10");
        ensure!(query.len() <= 2048, "Search query exceeds 2048 bytes");
        ensure!(!query.trim().is_empty() || !thread_ids.is_empty(), "Supply a query or known thread_ids for each request");
        result.push(Request { key, query, limit, thread_ids });
    }
    Ok(result)
}

pub fn run(api: &Api, a: &Args) -> Result<Value> {
    let text = read_input(a.required("requests-file")?)?;
    let value: Value = serde_json::from_str(text.trim_start_matches('\u{feff}'))
        .context("Invalid evidence request JSON")?;
    gather(api, a, &value)
}

fn gather(api: &Api, a: &Args, value: &Value) -> Result<Value> {
    let started = std::time::Instant::now();
    let requests = requests(value, a.number("max", 3)?)?;
    let max_threads = a.number("max-threads", 30)?;
    let mut budget = a.number("max-total-chars", 100000)?;
    let max_messages = a.number("max-messages", 6)?;
    let max_chars = a.number("max-chars", 5000)?;
    ensure!((1..=60).contains(&max_threads), "max-threads must be 1–60");
    ensure!((1000..=300000).contains(&budget), "max-total-chars must be 1000–300000");
    ensure!((1..=30).contains(&max_messages) && (1..=30000).contains(&max_chars), "Invalid email content limits");

    // Exact duplicate searches share a result while retaining each request's key.
    let mut searches: Vec<(String, usize)> = vec![];
    for request in &requests {
        if !request.query.trim().is_empty() {
            let signature = (request.query.clone(), request.limit);
            if !searches.contains(&signature) { searches.push(signature); }
        }
    }
    let mut search_results = HashMap::new();
    let mut search_batches = 0;
    for group in searches.chunks(gmail_batch::BATCH_SIZE) {
        let paths: Vec<_> = group.iter().map(|(query, limit)| format!(
            "/gmail/v1/users/me/messages?q={}&maxResults={limit}", enc(query)
        )).collect();
        search_batches += 1;
        let results = match gmail_batch::get_many(api, &paths) {
            Ok(results) => results,
            Err(error) => group.iter().map(|_| Err(anyhow::anyhow!("Search batch failed: {error}"))).collect(),
        };
        for (signature, result) in group.iter().zip(results) {
            search_results.insert(signature.clone(), result.map_err(|e| e.to_string()));
        }
    }
    let mut mappings = vec![];
    let mut all_ids = vec![];
    let mut any_incomplete = false;
    for request in &requests {
        let mut ids = request.thread_ids.clone();
        let mut mapping = json!({"key":request.key, "query":request.query, "max":request.limit,
            "search_performed":!request.query.trim().is_empty(), "search_has_more":false});
        if !request.query.trim().is_empty() {
            match &search_results[&(request.query.clone(), request.limit)] {
                Ok(result) => {
                    for message in items(&result["messages"]).iter().take(request.limit) {
                        let id = s(&message["threadId"]);
                        if !id.is_empty() { ids.push(id.to_string()); }
                        else { mapping["error"] = json!("Search result is missing its thread ID"); any_incomplete = true; }
                    }
                    if !s(&result["nextPageToken"]).is_empty() {
                        mapping["search_has_more"] = json!(true);
                        any_incomplete = true;
                    }
                }
                Err(error) => { mapping["error"] = json!(error); any_incomplete = true; }
            }
        }
        ids = gmail_batch::unique_ids(&ids);
        all_ids.extend(ids.iter().cloned());
        mapping["thread_ids"] = json!(ids);
        mappings.push(mapping);
    }
    let all_ids = gmail_batch::unique_ids(&all_ids);
    let omitted_ids: Vec<_> = all_ids.iter().skip(max_threads).cloned().collect();
    any_incomplete |= !omitted_ids.is_empty();
    let selected: Vec<_> = all_ids.iter().take(max_threads).cloned().collect();
    let mut threads = vec![];
    let mut errors = vec![];
    let mut read_batches = 0;
    // Preserve the established view contract, explicitly adding omission flags.
    let mut view_args = a.clone();
    view_args.opts.insert("max-messages".into(), max_messages.to_string());
    view_args.opts.insert("max-chars".into(), max_chars.to_string());
    for group in selected.chunks(gmail_batch::BATCH_SIZE) {
        read_batches += 1;
        let results = match gmail_batch::read_threads(api, group) {
            Ok(results) => results,
            Err(error) => group.iter().map(|_| Err(anyhow::anyhow!("Thread batch failed: {error}"))).collect(),
        };
        for (id, result) in group.iter().zip(results) {
            match result {
                Err(error) => { errors.push(json!({"thread_id":id,"error":error.to_string()})); any_incomplete = true; }
                Ok(raw) => {
                    let source = items(&raw["messages"]);
                    let mut view = thread_view(&raw, id, &view_args)?;
                    let omitted = source.len().saturating_sub(max_messages);
                    view["omitted_messages"] = json!(omitted);
                    any_incomplete |= omitted > 0;
                    for (message, original) in view["messages"].as_array_mut().unwrap().iter_mut().zip(&source[omitted..]) {
                        let original_len = body(&original["payload"]).chars().count();
                        let text = cut(s(&message["body"]), budget);
                        let returned = text.chars().count();
                        budget = budget.saturating_sub(returned);
                        message["body"] = json!(text);
                        message["body_truncated"] = json!(returned < original_len);
                        any_incomplete |= returned < original_len;
                    }
                    threads.push(view);
                }
            }
        }
    }
    let fetched: HashSet<_> = threads.iter().map(|v| s(&v["thread_id"]).to_string()).collect();
    for mapping in &mut mappings {
        mapping["unavailable_thread_ids"] = json!(items(&mapping["thread_ids"]).iter()
            .filter(|v| !fetched.contains(s(v))).cloned().collect::<Vec<_>>());
    }
    Ok(json!({
        "searches":mappings, "threads":threads, "errors":errors,
        "omitted_thread_ids":omitted_ids, "has_gaps_or_truncation":any_incomplete,
        "stats":{"requests":requests.len(),"unique_searches":searches.len(),"unique_threads":all_ids.len(),
            "threads_read":fetched.len(),"search_batches":search_batches,"read_batches":read_batches,
            "elapsed_ms":started.elapsed().as_millis()},
        "note":"Search matches are leads. Evaluate relevance and status from message content. Empty searches do not prove missing inputs. Read more only for evidence still needed; inspect errors and truncation flags."
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn batch(parts: Vec<(u16, Value)>) -> Value {
        let mut body = String::new();
        // Reverse the multipart order to exercise Content-ID association.
        for (i, (status, value)) in parts.into_iter().enumerate().rev() {
            body.push_str(&format!("--reply\r\nContent-Type: application/http\r\nContent-ID: <response-cos-{i}>\r\n\r\nHTTP/1.1 {status} Status\r\n\r\n{value}\r\n"));
        }
        body.push_str("--reply--\r\n");
        json!({"content_type":"multipart/mixed; boundary=reply","body":body})
    }
    fn thread(id: &str, text: &str) -> Value {
        json!({"id":id,"messages":[{"id":"message","payload":{"mimeType":"text/plain",
            "headers":[{"name":"Subject","value":"Approval"}],"body":{"data":URL_SAFE_NO_PAD.encode(text)}}}]})
    }
    fn args() -> Args {
        Args {group:"gmail".into(),command:"evidence".into(),pos:vec![],opts:HashMap::new(),multi:HashMap::new()}
    }
    #[test]
    fn batches_searches_then_reads_shared_threads_once() {
        let api = Api::mock(vec![
            batch(vec![(200,json!({"messages":[{"id":"m1","threadId":"a"},{"id":"m2","threadId":"b"}]})),
                       (200,json!({"messages":[{"id":"m3","threadId":"a"}]}))]),
            batch(vec![(200,thread("a","Café approved")),(200,thread("b","Still drafting")),(200,thread("known","Ready"))]),
        ]);
        let result = gather(&api,&args(),&json!([
            {"key":"lane-a","query":"subject:approval"},
            {"key":"lane-b","query":"from:person@example.com"},
            {"key":"lane-c","query":"subject:approval","thread_ids":["known"]}
        ])).unwrap();
        assert_eq!(api.calls().len(),2);
        assert_eq!(result["stats"]["unique_searches"],2);
        assert_eq!(result["stats"]["threads_read"],3);
        assert_eq!(result["searches"][1]["thread_ids"],json!(["a"]));
        assert_eq!(result["threads"][0]["messages"][0]["body"],"Café approved");
        assert_eq!(result["has_gaps_or_truncation"],false);
        let calls=api.calls();
        assert!(s(&calls[0]["body"]).contains("subject%3Aapproval"));
        assert_eq!(s(&calls[1]["body"]).matches("/threads/a?").count(),1);
    }
    #[test]
    fn empty_failed_and_truncated_searches_are_distinct() {
        let api=Api::mock(vec![batch(vec![
            (200,json!({})),(429,json!({"error":"limited"})),
            (200,json!({"messages":[{"threadId":"a"}],"nextPageToken":"more"}))
        ]),batch(vec![(403,json!({"error":"denied"}))])]);
        let result=gather(&api,&args(),&json!(["empty","failed","more"])).unwrap();
        assert_eq!(result["searches"][0]["thread_ids"],json!([]));
        assert!(result["searches"][0].get("error").is_none());
        assert!(s(&result["searches"][1]["error"]).contains("429"));
        assert_eq!(result["searches"][2]["search_has_more"],true);
        assert_eq!(result["searches"][2]["unavailable_thread_ids"],json!(["a"]));
        assert_eq!(result["errors"].as_array().unwrap().len(),1);
    }
    #[test]
    fn known_ids_skip_search_and_limits_are_explicit() {
        let api=Api::mock(vec![batch(vec![(200,thread("a","Café"))])]);
        let mut a=args();
        a.opts.insert("max-threads".into(),"1".into());
        a.opts.insert("max-chars".into(),"3".into());
        let result=gather(&api,&a,&json!([{"thread_ids":["a","b","a"]}])).unwrap();
        assert_eq!(result["stats"]["search_batches"],0);
        assert_eq!(result["omitted_thread_ids"],json!(["b"]));
        assert_eq!(result["threads"][0]["messages"][0]["body"],"Caf");
        assert_eq!(result["threads"][0]["messages"][0]["body_truncated"],true);
        assert_eq!(api.calls().len(),1);
    }
    #[test]
    fn invalid_input_makes_no_api_calls() {
        let api=Api::mock(vec![]);
        for value in [json!([]),json!([""]),json!([{"query":"x","max":0}]),
            json!([{"query":"x","max":100}]),json!([{"query":"x","typo":1}]),
            json!([{"thread_ids":["https://mail.google.com"]}]),
            json!([{"key":"same","query":"a"},{"key":"same","query":"b"}])] {
            assert!(gather(&api,&args(),&value).is_err());
        }
        assert!(api.calls().is_empty());
    }
    #[test]
    fn failed_whole_batch_is_reported_without_retries() {
        let api=Api::mock(vec![json!({"__error":"timeout"})]);
        let result=gather(&api,&args(),&json!(["first","second"])).unwrap();
        assert_eq!(api.calls().len(),1);
        assert_eq!(result["threads"],json!([]));
        assert!(s(&result["searches"][0]["error"]).contains("timeout"));
        assert!(s(&result["searches"][1]["error"]).contains("timeout"));
    }
}
