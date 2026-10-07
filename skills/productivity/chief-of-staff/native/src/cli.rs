use super::*;
use clap::{Arg, ArgAction, ArgGroup, Command};

pub fn schema() -> Value {
    serde_json::from_str(include_str!("../commands.json")).unwrap()
}

pub fn command() -> Command {
    let mut root = Command::new("cos-actions")
        .about("Focused Google Workspace actions")
        .subcommand_required(true)
        .arg_required_else_help(true);
    let schema = schema();
    for resource in ["gmail", "drive", "docs", "sheets", "slides", "calendar"] {
        let mut group = Command::new(resource).subcommand_required(true);
        for spec in items(&schema)
            .iter()
            .filter(|v| s(&v["resource"]) == resource)
        {
            let mut cmd = Command::new(s(&spec["command"]).to_string());
            if resource == "gmail" && spec["command"] == "draft" {
                cmd = cmd.visible_alias("save-draft");
            }
            for field in items(&spec["fields"]) {
                let id = s(&field["id"]).to_string();
                let mut arg = Arg::new(id).help(s(&field["help"]).to_string());
                if let Some(option) = items(&field["options"]).first() {
                    arg = arg.long(s(option).trim_start_matches("--").to_string());
                }
                if field["flag"] == true {
                    arg = arg.action(ArgAction::SetTrue);
                } else {
                    arg = arg.action(if field["append"] == true {
                        ArgAction::Append
                    } else {
                        ArgAction::Set
                    });
                    if field["nargs"] == "+" {
                        arg = arg.num_args(1..)
                    }
                    if field["nargs"] == "?" {
                        arg = arg.num_args(0..=1)
                    }
                    if s(&field["type"]) == "int" {
                        arg = arg.allow_negative_numbers(true)
                    }
                    if !field["default"].is_null() {
                        arg = arg.default_value(if field["default"].is_string() {
                            s(&field["default"]).to_string()
                        } else {
                            field["default"].to_string()
                        });
                    }
                }
                // Positional '?' arguments are not required, even though argparse labels them so.
                arg = arg.required(field["required"] == true && field["nargs"] != "?");
                cmd = cmd.arg(arg);
            }
            for (i, g) in items(&spec["exclusive"]).iter().enumerate() {
                cmd = cmd.group(
                    ArgGroup::new(format!("exclusive-{i}"))
                        .args(items(&g["args"]).iter().map(|v| s(v).to_string()))
                        .required(g["required"] == true),
                );
            }
            group = group.subcommand(cmd);
        }
        root = root.subcommand(group);
    }
    workflows::add(root).subcommand(
        Command::new("second-brain")
            .subcommand_required(true)
            .subcommand(
                Command::new("search")
                    .arg(Arg::new("query").required(true))
                    .arg(
                        Arg::new("max")
                            .long("max")
                            .default_value("3")
                            .allow_negative_numbers(true),
                    ),
            )
            .subcommand(
                Command::new("read")
                    .arg(Arg::new("note").required(true))
                    .arg(
                        Arg::new("max-chars")
                            .long("max-chars")
                            .default_value("4000")
                            .allow_negative_numbers(true),
                    ),
            ),
    )
}

pub fn from_matches(matches: &clap::ArgMatches) -> Result<Args> {
    let (group, parent) = matches.subcommand().context("Missing service")?;
    let (command, m) = parent.subcommand().context("Missing command")?;
    let mut a = Args {
        group: group.into(),
        command: command.into(),
        pos: vec![],
        opts: HashMap::new(),
        multi: HashMap::new(),
    };
    if group == "second-brain" {
        a.pos.push(
            m.get_one::<String>(if command == "search" { "query" } else { "note" })
                .unwrap()
                .clone(),
        );
        let key = if command == "search" {
            "max"
        } else {
            "max-chars"
        };
        a.opts
            .insert(key.into(), m.get_one::<String>(key).unwrap().clone());
        return Ok(a);
    }
    let schema = schema();
    let spec = items(&schema)
        .iter()
        .find(|v| s(&v["resource"]) == group && s(&v["command"]) == command)
        .unwrap();
    for field in items(&spec["fields"]) {
        let id = s(&field["id"]);
        let option = items(&field["options"])
            .first()
            .map(|v| s(v).trim_start_matches("--"));
        if field["flag"] == true {
            if m.get_flag(id) {
                a.opts.insert(option.unwrap().into(), "true".into());
            }
            continue;
        }
        if let Some(values) = m.get_many::<String>(id) {
            let values: Vec<_> = values.cloned().collect();
            if field["type"] == "int" {
                for value in &values {
                    let n: i64 = value
                        .parse()
                        .with_context(|| format!("Invalid integer for {id}: {value}"))?;
                    if let Some(bounds) = field["bounds"].as_array() {
                        ensure!(
                            (bounds[0].as_i64().unwrap()..=bounds[1].as_i64().unwrap())
                                .contains(&n),
                            "Expected {}–{}",
                            bounds[0],
                            bounds[1]
                        );
                    }
                }
            }
            if let Some(key) = option {
                a.opts.insert(key.into(), values.last().unwrap().clone());
                a.multi.insert(key.into(), values);
            } else {
                a.pos.extend(values);
            }
        }
    }
    if a.command == "read" && ["docs", "slides"].contains(&group) {
        a.command = "get".into();
    }
    Ok(a)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn save_draft_alias_preserves_arguments_and_validation() {
        for name in ["draft", "save-draft"] {
            let m = command().try_get_matches_from([
                "cos-actions", "gmail", name, "--reply-to-message", "message-id",
                "--expected-to", "person@example.com", "--body-file", "-",
            ]).unwrap();
            let a = from_matches(&m).unwrap();
            assert_eq!(a.command, "draft");
            assert_eq!(a.required("reply-to-message").unwrap(), "message-id");
            assert_eq!(a.required("expected-to").unwrap(), "person@example.com");
            assert_eq!(a.required("body-file").unwrap(), "-");
            assert!(command().try_get_matches_from([
                "cos-actions", "gmail", name, "--body", "Hi", "--body-file", "-",
            ]).is_err());
        }
    }
    #[test]
    fn cli_contract() {
        let c = command();
        c.clone().debug_assert();
        for args in [
            vec![
                "cos-actions",
                "gmail",
                "draft",
                "--body",
                "Hi",
                "--to",
                "a@b.com",
                "--subject",
                "Hello",
            ],
            vec![
                "cos-actions",
                "slides",
                "preview",
                "id",
                "--workspace-root",
                "C:/w",
                "--output-dir",
                "p",
                "--slide-id",
                "a",
                "--slide-id",
                "b",
            ],
        ] {
            let m = c.clone().try_get_matches_from(args).unwrap();
            from_matches(&m).unwrap();
        }
        for args in [
            vec!["cos-actions", "gmail", "draft", "--body", "Hi", "--confirm"],
            vec![
                "cos-actions",
                "gmail",
                "draft",
                "--body",
                "a",
                "--body-file",
                "b",
            ],
            vec![
                "cos-actions",
                "sheets",
                "update-lanes",
                "id",
                "--updates",
                "[]",
                "--status-only",
                "--include-details",
            ],
            vec!["cos-actions", "docs", "inspect", "id", "--max-items", "0"],
        ] {
            let parsed = c.clone().try_get_matches_from(args);
            assert!(parsed.is_err() || from_matches(&parsed.unwrap()).is_err());
        }
    }
}
