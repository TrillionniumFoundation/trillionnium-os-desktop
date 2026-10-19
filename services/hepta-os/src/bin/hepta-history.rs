//! Explicit read of one retained request through its original journal owner.

#[cfg(target_os = "linux")]
mod trusted_host {
    use hepta_os_observer::objective::history::{
        HistoryAnchor, HistoryAttempt, HistoryStatus, ObjectiveHistoryClient,
    };
    use hepta_os_observer::objective::ProvidedObjective;
    use hepta_os_observer::{EndpointConfig, MAX_FRAME_BYTES};
    use serde_json::{json, Value};
    use std::io::{Read, Write};
    use std::path::PathBuf;

    pub fn main() -> std::process::ExitCode {
        let arguments: Result<Vec<_>, _> = std::env::args_os()
            .skip(1)
            .take(10)
            .map(|value| value.into_string().map_err(|_| "history_invalid_arguments"))
            .collect();
        if arguments.as_ref().is_ok_and(|arguments| {
            arguments.len() == 1 && matches!(arguments[0].as_str(), "--help" | "-h")
        }) {
            return output(b"hepta-history <absolute-socket> <agent-uuid> <current-spawn> <peer-uid> <peer-pid> <request-id> [<anchor-sequence> <anchor-chain-digest>]\n\
                Reads the exact retained original issuer envelope from stdin until EOF (no outer newline).\n\
                The optional anchor must come from a previously trusted owner response.\n\
                A historical publication includes its disposition; conflict is not admission.\n\
                Unknown or query-not-sent never means the original was not admitted.\n\
                One read only. No signing, submission, journal access, retry or effect authority.\n\
                Exit: 0 historical publication, 10 query not sent, 12 unknown, 74 output lost.\n", 0);
        }
        let (document, code) = arguments.and_then(execute).unwrap_or_else(|issue| (
            json!({"schema_version":1,"status":"query_not_sent","issue":issue,"bytes_written":0}), 10,
        ));
        let mut bytes = match serde_json::to_vec(&document) {
            Ok(bytes) => bytes,
            Err(_) => return std::process::ExitCode::from(74),
        };
        bytes.push(b'\n');
        output(&bytes, code)
    }

    fn output(bytes: &[u8], code: u8) -> std::process::ExitCode {
        if std::io::stdout().lock().write_all(bytes).is_err() {
            std::process::ExitCode::from(74)
        } else {
            std::process::ExitCode::from(code)
        }
    }

    fn execute(arguments: Vec<String>) -> Result<(Value, u8), &'static str> {
        if !matches!(arguments.len(), 6 | 8) {
            return Err("history_invalid_arguments");
        }
        let endpoint = EndpointConfig::new(
            PathBuf::from(&arguments[0]),
            arguments[1].clone(),
            arguments[2]
                .parse()
                .map_err(|_| "history_invalid_arguments")?,
            arguments[3]
                .parse()
                .map_err(|_| "history_invalid_arguments")?,
        )
        .map_err(|error| error.code())?;
        let client = ObjectiveHistoryClient::new(
            endpoint,
            arguments[4]
                .parse()
                .map_err(|_| "history_invalid_arguments")?,
            arguments[5]
                .parse()
                .map_err(|_| "history_invalid_arguments")?,
        )
        .map_err(|error| error.code())?;
        let anchor = if arguments.len() == 8 {
            Some(
                HistoryAnchor::new(
                    arguments[6].parse().map_err(|_| "history_invalid_anchor")?,
                    arguments[7].clone(),
                )
                .map_err(|_| "history_invalid_anchor")?,
            )
        } else {
            None
        };
        // Input acquisition precedes the five-second read deadline. The trusted
        // caller closes stdin and bounds this child; the CLI owns no saved input.
        let mut raw = String::new();
        std::io::stdin()
            .take(MAX_FRAME_BYTES + 1)
            .read_to_string(&mut raw)
            .map_err(|_| "history_input_unreadable")?;
        let objective = ProvidedObjective::parse_json(raw).map_err(|error| error.code())?;
        Ok(project(&client.query_once(objective, anchor)))
    }

    fn project(attempt: &HistoryAttempt) -> (Value, u8) {
        let identity = attempt.identity();
        let original = &identity.objective;
        let mut result = json!({
            "schema_version":1,
            "identity":{
                "request_id":identity.request_id,"agent_id":identity.agent_id,
                "spawn_generation":identity.spawn_generation,
                "peer_uid":identity.expected_peer_uid,"peer_pid":identity.expected_peer_pid,
                "original_spawn_generation":original.spawn_generation,
                "issuer_id":original.issuer_id,"key_epoch":original.key_epoch,
                "message_id":original.message_id,"message_sequence":original.sequence,
                "expires_at_ms":original.expires_at_ms,"run_id":original.run_id,
            },
            "anchor":attempt.anchor(),"bytes_written":attempt.bytes_written(),
            "request_frame_bytes":attempt.request_frame_bytes(),
        });
        let (status, code) = match attempt.status() {
            HistoryStatus::HistoricalPublication {
                publication,
                response_generation,
            } => {
                result["publication"] = json!(publication);
                result["response_generation"] = json!(response_generation);
                result["anchor_coverage"] = json!(if attempt.anchor().is_some() {
                    "retained_anchor"
                } else {
                    "current_owner_journal"
                });
                ("historical_publication", 0)
            }
            HistoryStatus::Unknown(issue) => {
                result["issue"] = json!(issue.code());
                ("unknown", 12)
            }
            HistoryStatus::QueryNotSent(issue) => {
                result["issue"] = json!(issue.code());
                ("query_not_sent", 10)
            }
        };
        result["status"] = json!(status);
        (result, code)
    }
}

#[cfg(target_os = "linux")]
fn main() -> std::process::ExitCode {
    trusted_host::main()
}

#[cfg(not(target_os = "linux"))]
fn main() -> std::process::ExitCode {
    eprintln!("hepta-history: unsupported_platform");
    std::process::ExitCode::from(2)
}
