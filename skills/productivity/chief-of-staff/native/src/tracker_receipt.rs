use super::*;

#[derive(Debug)]
pub struct VerificationError(pub Value);
impl std::fmt::Display for VerificationError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("Google accepted the tracker write, but receipt verification failed. Report the saved values and verification errors; do not retry writes automatically.")
    }
}
impl std::error::Error for VerificationError {}

fn same_range(a: &str, b: &str) -> bool {
    fn normalized(range: &str) -> Option<(String, String, String)> {
        let (sheet, cells) = range.rsplit_once('!')?;
        let sheet = sheet
            .strip_prefix('\'')
            .and_then(|s| s.strip_suffix('\''))
            .unwrap_or(sheet)
            .replace("''", "'");
        let (start, end) = cells.split_once(':').unwrap_or((cells, cells));
        Some((sheet, start.into(), end.into()))
    }
    normalized(a).is_some() && normalized(a) == normalized(b)
}

pub fn verify(
    receipt: &mut Value,
    data: &[Value],
    before: &[Value],
    response: &Value,
) -> Result<()> {
    let responses = items(&response["responses"]);
    let mut errors = vec![];
    let mut changes = vec![];
    if responses.len() != data.len() {
        errors.push(json!("Missing or unexpected per-range update responses"));
    }
    for (i, request) in data.iter().enumerate() {
        let lane = receipt["lanes"][i].clone();
        let saved = responses.get(i).unwrap_or(&Value::Null);
        let returned = &saved["updatedData"];
        let range_ok = same_range(s(&request["range"]), s(&returned["range"]));
        if !range_ok {
            errors.push(json!({"lane":lane,"error":"Missing or mismatched saved range"}));
        }
        let mut old = json!({});
        let mut after = json!({});
        for (column, expected) in items(&request["values"][0]).iter().enumerate() {
            // Sheets skips null input cells; they are not writes to verify.
            if expected.is_null() {
                continue;
            }
            let field = ["status", "latest", "next", "due", "blocker", "evidence"][column];
            old[field] = before[i].get(column + 2).cloned().unwrap_or(json!(""));
            // Sheets omits trailing empty cells. Only infer blanks for a valid returned range.
            let actual = if range_ok {
                returned["values"][0]
                    .get(column)
                    .cloned()
                    .unwrap_or(json!(""))
            } else {
                Value::Null
            };
            after[field] = actual.clone();
            if actual != *expected {
                errors.push(json!({"lane":lane,"field":field,"expected":expected,"saved":actual}));
            }
        }
        changes.push(json!({"lane":lane,"before":old,"after":after}));
    }
    receipt["changes"] = json!(changes);
    receipt["verified"] = json!(errors.is_empty());
    if !errors.is_empty() {
        receipt["status"] = json!("verification_failed");
        receipt["verification_errors"] = json!(errors);
        return Err(VerificationError(receipt.clone()).into());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn details_include_saved_fields_preserve_omissions_and_accept_trimmed_blanks() {
        let mut receipt = json!({"status":"updated","lanes":["Alpha","Beta"]});
        let data = vec![
            json!({"range":"'Campaign Lanes'!C7:H7","values":[["Complete","Done",null,null,"",null]]}),
            json!({"range":"'Campaign Lanes'!C8","values":[["In progress"]]}),
        ];
        let before = vec![
            json!([
                "Alpha",
                "Pat",
                "Blocked",
                "Waiting",
                "keep",
                "keep",
                "Pending approval"
            ]),
            json!(["Beta", "Lee", "Awaiting update"]),
        ];
        let response = json!({"responses":[
            {"updatedData":{"range":"'Campaign Lanes'!C7:H7","values":[["Complete","Done","keep","keep"]]}},
            {"updatedData":{"range":"'Campaign Lanes'!C8:C8","values":[["In progress"]]}}
        ]});
        verify(&mut receipt, &data, &before, &response).unwrap();
        assert_eq!(receipt["verified"], true);
        assert_eq!(
            receipt["changes"][0]["after"],
            json!({"status":"Complete","latest":"Done","blocker":""})
        );
        assert_eq!(
            receipt["changes"][0]["before"]["blocker"],
            "Pending approval"
        );
        assert_eq!(receipt["changes"][1]["after"]["status"], "In progress");
    }
    #[test]
    fn missing_wrong_range_and_mismatched_values_never_verify() {
        let data = vec![json!({"range":"'Lanes'!C7","values":[["Complete"]]})];
        let before = vec![json!(["Alpha", "Pat", "In progress"])];
        for response in [
            json!({}),
            json!({"responses":[{}]}),
            json!({"responses":[{"updatedData":{"range":"Lanes!C8","values":[["Complete"]]}}]}),
            json!({"responses":[{"updatedData":{"range":"Lanes!C7","values":[["On track"]]}}]}),
            json!({"responses":[{"updatedData":{"range":"Lanes!C7"}}]}),
        ] {
            let mut receipt = json!({"status":"updated","lanes":["Alpha"]});
            assert!(verify(&mut receipt, &data, &before, &response).is_err());
            assert_eq!(receipt["verified"], false);
            assert_eq!(receipt["status"], "verification_failed");
        }
    }
}
