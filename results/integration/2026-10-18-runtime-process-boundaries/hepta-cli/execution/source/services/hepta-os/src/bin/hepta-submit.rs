//! One explicit trusted-host invocation of the original ObjectiveStart route.
//!
//! The caller retains the issuer's envelope before launching this command. A
//! missing result (including a killed process or a broken stdout) is unknown,
//! never permission to replay. This command owns no key or persistent ledger.

#[cfg(target_os = "linux")]
mod trusted_host {
    use hepta_os_observer::objective::{
        AdmissionDisposition, ObjectiveTransport, PrePublicationRefusal, ProvidedObjective,
        SubmissionAttempt, SubmissionStatus,
    };
    use hepta_os_observer::{EndpointConfig, MAX_FRAME_BYTES};
    use serde_json::{json, Value};
    use std::io::{Read, Write};
    use std::path::PathBuf;

    pub fn main() -> std::process::ExitCode {
        let arguments: Result<Vec<_>, _> = std::env::args_os()
            .skip(1)
            .take(8)
            .map(|value| {
                value
                    .into_string()
                    .map_err(|_| "objective_invalid_arguments")
            })
            .collect();
        if arguments.as_ref().is_ok_and(|arguments| {
            arguments.len() == 1 && matches!(arguments[0].as_str(), "--help" | "-h")
        }) {
            let help = b"hepta-submit <absolute-socket> <agent-uuid> <spawn-generation> <peer-uid> <peer-pid> <request-id>\n\
                Reads one compact original issuer envelope from stdin until EOF (no outer newline).\n\
                Keep the original input before invoking; lost output or process loss means unknown.\n\
                Exactly one trusted-host attempt. No signing, retry, cancellation or effect completion.\n\
                Exit: 0 admitted, 10 not-sent, 11 pre-publication refusal, 12 unknown, 13 conflict, 74 output lost.\n";
            return match std::io::stdout().lock().write_all(help) {
                Ok(()) => std::process::ExitCode::SUCCESS,
                Err(_) => std::process::ExitCode::from(74),
            };
        }
        let (document, code) = arguments.and_then(execute).unwrap_or_else(|issue| {
            (
                json!({"schema_version": 1, "status": "not_sent", "issue": issue,
                    "bytes_written": 0}),
                10,
            )
        });
        // Only finite issue codes and bounded identity/receipt fields reach
        // stdout. No socket path, source JSON, signature or raw owner error.
        let mut encoded = match serde_json::to_vec(&document) {
            Ok(value) => value,
            Err(_) => return std::process::ExitCode::from(74),
        };
        encoded.push(b'\n');
        if std::io::stdout().lock().write_all(&encoded).is_err() {
            return std::process::ExitCode::from(74);
        }
        std::process::ExitCode::from(code)
    }

    fn execute(arguments: Vec<String>) -> Result<(Value, u8), &'static str> {
        if arguments.len() != 6 {
            return Err("objective_invalid_arguments");
        }
        let endpoint = EndpointConfig::new(
            PathBuf::from(&arguments[0]),
            arguments[1].clone(),
            arguments[2]
                .parse()
                .map_err(|_| "objective_invalid_arguments")?,
            arguments[3]
                .parse()
                .map_err(|_| "objective_invalid_arguments")?,
        )
        .map_err(|error| error.code())?;
        let transport = ObjectiveTransport::new(
            endpoint,
            arguments[4]
                .parse()
                .map_err(|_| "objective_invalid_arguments")?,
            arguments[5]
                .parse()
                .map_err(|_| "objective_invalid_arguments")?,
        )
        .map_err(|error| error.code())?;
        // Input acquisition precedes the transport deadline and sends nothing.
        // A trusted process caller must close stdin and bound the child lifetime.
        let mut raw = String::new();
        std::io::stdin()
            .take(MAX_FRAME_BYTES + 1)
            .read_to_string(&mut raw)
            .map_err(|_| "objective_input_unreadable")?;
        let objective = ProvidedObjective::parse_json(raw).map_err(|error| error.code())?;
        Ok(project(&transport.submit_once(objective)))
    }

    fn project(attempt: &SubmissionAttempt) -> (Value, u8) {
        let identity = attempt.identity();
        let objective = &identity.objective;
        let mut document = json!({
            "schema_version": 1,
            "identity": {
                "request_id": identity.request_id,
                "agent_id": identity.agent_id,
                "spawn_generation": identity.spawn_generation,
                "peer_uid": identity.expected_peer_uid,
                "peer_pid": identity.expected_peer_pid,
                "issuer_id": objective.issuer_id,
                "key_epoch": objective.key_epoch,
                "message_id": objective.message_id,
                "sequence": objective.sequence,
                "expires_at_ms": objective.expires_at_ms,
                "run_id": objective.run_id,
                "objective_revision": objective.objective_revision,
                "authority_epoch": objective.authority_epoch,
                "runtime_body_digest": objective.runtime_body_digest,
                "preference_state_digest": objective.preference_state_digest,
                "model_tuple_digest": objective.model_tuple_digest,
                "prompt_registry_digest": objective.prompt_registry_digest,
                "artifact_set_digest": objective.artifact_set_digest,
            },
            "bytes_written": attempt.bytes_written(),
            "request_frame_bytes": attempt.request_frame_bytes(),
        });
        let (status, exit) = match attempt.status() {
            SubmissionStatus::NotSent(issue) => {
                document["issue"] = json!(issue.code());
                ("not_sent", 10)
            }
            SubmissionStatus::SubmitUnknown(issue) => {
                document["issue"] = json!(issue.code());
                ("submit_unknown", 12)
            }
            SubmissionStatus::RefusedBeforePublication {
                reason,
                response_generation,
            } => {
                document["reason"] = json!(match reason {
                    PrePublicationRefusal::ObjectiveUnavailable => "objective_unavailable",
                    PrePublicationRefusal::UnsupportedSchema => "unsupported_schema",
                });
                document["response_generation"] = json!(response_generation);
                ("refused_before_publication", 11)
            }
            SubmissionStatus::Admitted(receipt) => {
                document["receipt"] = json!({
                    "run_id": receipt.run_id,
                    "objective_digest": receipt.objective_digest,
                    "hard_constraint_digest": receipt.hard_constraint_digest,
                    "publication_digest": receipt.publication_digest,
                    "chain_digest": receipt.chain_digest,
                    "disposition": match receipt.disposition {
                        AdmissionDisposition::Compiled => "compiled",
                        AdmissionDisposition::ExplicitAbstain => "explicit_abstain",
                        AdmissionDisposition::CanonicalReady => "canonical_ready",
                        AdmissionDisposition::CanonicalAbstained => "canonical_abstained",
                        AdmissionDisposition::CanonicalSlowPath => "canonical_slow_path",
                    },
                    "idempotent": receipt.idempotent,
                    "response_generation": receipt.response_generation,
                });
                ("admitted", 0)
            }
            SubmissionStatus::Conflict(receipt) => {
                document["receipt"] = json!({
                    "run_id": receipt.run_id,
                    "conflict_digest": receipt.conflict_digest,
                    "response_generation": receipt.response_generation,
                });
                ("conflict", 13)
            }
        };
        document["status"] = json!(status);
        (document, exit)
    }
}

#[cfg(target_os = "linux")]
fn main() -> std::process::ExitCode {
    trusted_host::main()
}

#[cfg(not(target_os = "linux"))]
fn main() -> std::process::ExitCode {
    eprintln!("hepta-submit: unsupported_platform");
    std::process::ExitCode::from(2)
}
