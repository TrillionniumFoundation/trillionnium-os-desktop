//! Real, bounded Package Manager sessions borrowed from the original early owner.
//! Android enforces signer continuity. No uninstall, downgrade, signature repair,
//! data copy or caller-provided package-manager flags exist in this adapter.
use super::install_input::{Payload, SegmentInput, SegmentObservation};
use super::*;
use crate::production_selection::early_generation::EarlyApplicationAuthority;
use std::time::{Duration, Instant};
const SESSION_LIMIT: Duration = Duration::from_secs(110);

#[derive(Clone, Copy)]
enum SessionMode {
    Replace { user: u32 },
    CreateOnlyUserZero,
}
impl SessionMode {
    fn user(self) -> u32 {
        match self { Self::Replace { user } => user, Self::CreateOnlyUserZero => 0 }
    }
    fn create(self, bytes: u64) -> InstallCommand {
        match self {
            Self::Replace { user } => InstallCommand::Create { user, bytes },
            Self::CreateOnlyUserZero => InstallCommand::CreateOnly { bytes },
        }
    }
    fn require_normal_output(self, retired_successfully: bool, stdout: &str, stderr: &str) -> Result<()> {
        if !retired_successfully || (matches!(self, Self::CreateOnlyUserZero) && !stderr.is_empty()) {
            return Err(reject(format!(
                "Android installation command failed: {} {}",
                stdout.trim(), stderr.trim()
            )));
        }
        Ok(())
    }
}

#[derive(Debug, Serialize)]
struct CommandObservation {
    command: InstallCommand,
    receipt: ReadReceipt,
}
#[derive(Debug, Serialize)]
pub(crate) struct InstallObservation {
    pub(crate) session: u32,
    pub(crate) user: u32,
    pub(crate) bytes: u64,
    pub(crate) segments: Vec<SegmentObservation>,
    commands: Vec<CommandObservation>,
}
fn confirm(output: &str, expected: &str) -> Result<()> {
    if output
        .lines()
        .filter(|line| line.trim() == expected)
        .count()
        == 1
        && !output.contains("Failure")
        && !output.contains("Error:")
    {
        Ok(())
    } else {
        Err(reject(format!(
            "Android did not confirm {expected:?}: {}",
            output.trim()
        )))
    }
}

fn session(output: &str) -> Result<u32> {
    let ids = output
        .lines()
        .filter_map(|line| {
            line.trim()
                .strip_prefix("Success: created install session [")
                .and_then(|v| v.strip_suffix(']'))
                .and_then(|v| {
                    v.parse::<u32>()
                        .ok()
                        .filter(|id| *id > 0 && *id <= i32::MAX as u32 && id.to_string() == v)
                })
        })
        .collect::<Vec<_>>();
    require(
        ids.len() == 1 && !output.contains("Failure") && !output.contains("Error:"),
        "Android did not return one unambiguous install session; inspect outstanding sessions before retry",
    )?;
    Ok(ids[0])
}
fn transact(
    payload: &Payload,
    mode: SessionMode,
    deadline: Instant,
    call: &mut dyn FnMut(&InstallCommand, Option<SegmentInput>, Instant) -> Result<String>,
    progress: &mut dyn FnMut() -> Result<()>,
) -> Result<u32> {
    let create = mode.create(payload.total());
    create.validate()?;
    require(
        Instant::now() < deadline,
        "installation deadline already expired",
    )?;
    let id = session(&call(&create, None, deadline)?)?;
    let mut commit_attempted = false;
    let outcome = (|| -> Result<()> {
        for index in 0..payload.len() {
            let input = payload.segment(index)?;
            let bytes = input.bytes();
            let write = InstallCommand::Write {
                session: id,
                index: index as u32,
                bytes,
            };
            confirm(
                &call(&write, Some(input), deadline)?,
                &format!("Success: streamed {bytes} bytes"),
            )?;
        }
        payload.revalidate(deadline, progress)?;
        require(
            Instant::now() < deadline,
            "installation expired before commit",
        )?;
        commit_attempted = true;
        confirm(
            &call(&InstallCommand::Commit { session: id }, None, deadline)?,
            "Success",
        )
    })();
    if let Err(error) = outcome {
        if matches!(error, ApplicationError::RetirementUnproven) {
            return Err(error);
        }
        let cleanup = call(
            &InstallCommand::Abandon { session: id },
            None,
            (Instant::now() + Duration::from_secs(5)).min(deadline),
        )
        .and_then(|value| confirm(&value, "Success"));
        return Err(reject(format!(
            "{error}; session {id} abandonment: {}; {}",
            match cleanup {
                Ok(()) => "confirmed".to_owned(),
                Err(ApplicationError::RetirementUnproven) =>
                    return Err(ApplicationError::RetirementUnproven),
                Err(e) => format!("NOT confirmed ({e})"),
            },
            if commit_attempted {
                "commit was NOT confirmed: inspect installed version before any retry"
            } else {
                "commit was not attempted; existing installed application was not uninstalled"
            }
        )));
    }
    Ok(id)
}
pub(crate) fn install_early(
    authority: &EarlyApplicationAuthority<'_>,
    user: u32,
    file: File,
    lengths: &[u64],
    overall_deadline: Instant,
) -> Result<InstallObservation> {
    install_with_mode(authority, SessionMode::Replace { user }, file, lengths, overall_deadline)
}

/// Source-private fixture birth. Callers must hold their normal fixed material,
/// prove absence and retain the returned real transaction through later PM/Main
/// checks. This entry has no package, user, path, flags or replacement input.
pub(crate) fn install_create_only_early(
    authority: &EarlyApplicationAuthority<'_>,
    file: File,
    lengths: &[u64],
    overall_deadline: Instant,
) -> Result<InstallObservation> {
    install_with_mode(authority, SessionMode::CreateOnlyUserZero, file, lengths, overall_deadline)
}

fn install_with_mode(
    authority: &EarlyApplicationAuthority<'_>,
    mode: SessionMode,
    file: File,
    lengths: &[u64],
    overall_deadline: Instant,
) -> Result<InstallObservation> {
    let user = mode.user();
    let deadline = (Instant::now() + SESSION_LIMIT).min(overall_deadline);
    require(Instant::now() < deadline, "installation original deadline already expired")?;
    authority.ready().map_err(external)?;
    let framework = authority.observe_framework().map_err(external)?;
    let epoch = authority.epoch(&framework).map_err(external)?;
    let mut progress = || {
        authority
            .progress_inherited_native(deadline)
            .map_err(external)
    };
    crate::control::apk_payload::validate_production_context(&file).map_err(external)?;
    let payload = Payload::prepare(file, lengths, deadline, &mut progress)?;
    let mut records = Vec::new();
    let mut call = |command: &InstallCommand,
                    input: Option<SegmentInput>,
                    command_deadline: Instant|
     -> Result<String> {
        require(
            Instant::now() < command_deadline,
            "installation command deadline",
        )?;
        require(
            authority.epoch(&framework).map_err(external)? == epoch,
            "Android framework changed during installation",
        )?;
        let operation = ApplicationOperation::Install {
            value: command.clone(),
        };
        let result = factory_query::run_with_input(authority, &operation, input, command_deadline);
        // Run the real owner postcheck even on rejection, without replacing a
        // stronger original-child retirement failure with a later ready error.
        let result = workflow::finish_effect(
            result,
            || authority.ready().map_err(external),
            command_deadline,
        )?;
        require(
            authority.epoch(&framework).map_err(external)? == epoch,
            "Android framework changed after installation command",
        )?;
        let normal = result.output.status.success() && result.receipt.successful_retirement();
        let stdout = String::from_utf8(result.output.stdout).map_err(external)?;
        let stderr = String::from_utf8(result.output.stderr).map_err(external)?;
        let record = CommandObservation {
            command: command.clone(),
            receipt: result.receipt,
        };
        eprintln!(
            "droidloom-install-command {}",
            serde_json::to_string(&record).map_err(external)?
        );
        records.push(record);
        mode.require_normal_output(normal, &stdout, &stderr)?;
        Ok(stdout)
    };
    let session = transact(&payload, mode, deadline, &mut call, &mut progress)?;
    authority.ready().map_err(external)?;
    require(
        authority.epoch(&framework).map_err(external)? == epoch,
        "Android framework changed after install commit",
    )?;
    let observed = InstallObservation {
        session,
        user,
        bytes: payload.total(),
        segments: payload.observations(),
        commands: records,
    };
    eprintln!(
        "droidloom-install-session {}",
        serde_json::to_string(&observed).map_err(external)?
    );
    Ok(observed)
}
#[cfg(test)]
mod tests {
    use super::*;
    fn payload() -> Payload {
        let file = crate::control::apk_payload::test_payload(b"PK\x03\x04basePK\x03\x04split");
        Payload::prepare(
            file,
            &[8, 9],
            Instant::now() + Duration::from_secs(5),
            &mut || Ok(()),
        )
        .unwrap()
    }
    #[test]
    fn installation_session_uses_atomic_create_all_writes_then_commit() {
        let payload = payload();
        let mut calls = Vec::new();
        let mut call = |command: &InstallCommand, input: Option<SegmentInput>, _: Instant| {
            calls.push(command.clone());
            assert_eq!(
                input.as_ref().map(SegmentInput::bytes),
                command.input_bytes()
            );
            Ok(match command {
                InstallCommand::Create { .. } => "Success: created install session [23]".into(),
                InstallCommand::Write { bytes, .. } => format!("Success: streamed {bytes} bytes"),
                _ => "Success".into(),
            })
        };
        assert_eq!(
            transact(
                &payload,
                SessionMode::Replace { user: 0 },
                Instant::now() + Duration::from_secs(5),
                &mut call,
                &mut || Ok(())
            )
            .unwrap(),
            23
        );
        assert_eq!(
            calls,
            [
                InstallCommand::Create { user: 0, bytes: 17 },
                InstallCommand::Write {
                    session: 23,
                    index: 0,
                    bytes: 8
                },
                InstallCommand::Write {
                    session: 23,
                    index: 1,
                    bytes: 9
                },
                InstallCommand::Commit { session: 23 }
            ]
        );
    }
    #[test]
    fn installation_session_never_commits_a_failed_segment_or_hides_uncertain_commit() {
        for failing_commit in [false, true] {
            let payload = payload();
            let mut calls = Vec::new();
            let mut call = |command: &InstallCommand, _: Option<SegmentInput>, _: Instant| {
                calls.push(command.clone());
                Ok(match command {
                    InstallCommand::Create { .. } => "Success: created install session [42]".into(),
                    InstallCommand::Write { index: 1, .. } if !failing_commit => {
                        "Failure [INSTALL_FAILED_INVALID_APK]".into()
                    }
                    InstallCommand::Write { bytes, .. } => {
                        format!("Success: streamed {bytes} bytes")
                    }
                    InstallCommand::Commit { .. } => "unconfirmed response".into(),
                    _ => "Success".into(),
                })
            };
            let error = transact(
                &payload,
                SessionMode::Replace { user: 0 },
                Instant::now() + Duration::from_secs(5),
                &mut call,
                &mut || Ok(()),
            )
            .unwrap_err()
            .to_string();
            assert_eq!(calls.last(), Some(&InstallCommand::Abandon { session: 42 }));
            assert_eq!(
                calls
                    .iter()
                    .any(|v| matches!(v, InstallCommand::Commit { .. })),
                failing_commit
            );
            assert!(error.contains(if failing_commit {
                "inspect installed version before any retry"
            } else {
                "commit was not attempted"
            }));
        }
    }
    #[test]
    fn installation_session_rejects_duplicate_success_and_foreign_or_ambiguous_identity() {
        assert_eq!(
            session("Success: created install session [12]\n").unwrap(),
            12
        );
        for value in [
            "Success",
            "Success: created install session [01]",
            "Success: created install session [0]",
            "Success: created install session [1]\nSuccess: created install session [2]",
            "Success: created install session [1]\nFailure [bad]",
        ] {
            assert!(session(value).is_err());
        }
        for value in [
            "",
            "Success\nSuccess\n",
            "Success\nFailure [signature mismatch]",
        ] {
            assert!(confirm(value, "Success").is_err());
        }
    }
    #[test]
    fn installation_create_only_preserves_real_session_order_and_original_end_on_failure() {
        for fail_commit in [false, true] {
            let payload = payload();
            let original_end = Instant::now() + Duration::from_secs(2);
            let mut calls = Vec::new();
            let mut call = |command: &InstallCommand, input: Option<SegmentInput>, end: Instant| {
                assert!(end <= original_end);
                assert_eq!(input.as_ref().map(SegmentInput::bytes), command.input_bytes());
                calls.push(command.clone());
                Ok(match command {
                    InstallCommand::CreateOnly { bytes: 17 } => "Success: created install session [23]".into(),
                    InstallCommand::Write { bytes, .. } => format!("Success: streamed {bytes} bytes"),
                    InstallCommand::Commit { .. } if fail_commit => "Failure [INSTALL_FAILED_ALREADY_EXISTS]".into(),
                    InstallCommand::Create { .. } => panic!("fixture must never request replacement"),
                    _ => "Success".into(),
                })
            };
            let result = transact(&payload, SessionMode::CreateOnlyUserZero, original_end, &mut call, &mut || Ok(()));
            assert_eq!(calls.first(), Some(&InstallCommand::CreateOnly { bytes: 17 }));
            assert_eq!(calls.iter().filter(|v| matches!(v, InstallCommand::Write { .. })).count(), 2);
            assert_eq!(calls.iter().filter(|v| matches!(v, InstallCommand::Commit { .. })).count(), 1);
            if fail_commit {
                assert!(result.unwrap_err().to_string().contains("commit was NOT confirmed"));
                assert_eq!(calls.last(), Some(&InstallCommand::Abandon { session: 23 }));
            } else {
                assert_eq!(result.unwrap(), 23);
                assert_eq!(calls.last(), Some(&InstallCommand::Commit { session: 23 }));
            }
        }
    }

    #[test]
    fn installation_create_only_requires_actual_retirement_and_exact_empty_stderr() {
        let fixture = SessionMode::CreateOnlyUserZero;
        assert!(fixture.require_normal_output(true, "Success\n", "").is_ok());
        assert!(fixture.require_normal_output(false, "Success\n", "").is_err());
        for stderr in ["\n", " ", "RuntimeException\n"] {
            assert!(fixture.require_normal_output(true, "Success\n", stderr).is_err());
        }
        // The pre-existing replace adapter keeps its original stderr contract.
        assert!(SessionMode::Replace { user: 0 }.require_normal_output(true, "Success\n", "diagnostic").is_ok());
    }

}
