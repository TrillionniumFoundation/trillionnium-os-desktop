//! Test/operator CLI for the unprivileged host session. Not an OS terminal.
use std::process::ExitCode;
use trill_ui_core::{request, AppKind, Request, Response, TaskState, Workspace};

fn usage() -> ! {
    eprintln!("Usage: trill-ctl snapshot | launch <personal|research|build> <notes|calculator|terminal> | cancel <task-id> <session-generation>");
    std::process::exit(2);
}

fn parse_workspace(value: &str) -> Workspace {
    match value {
        "personal" => Workspace::Personal,
        "research" => Workspace::Research,
        "build" => Workspace::Build,
        _ => usage(),
    }
}

fn parse_app(value: &str) -> AppKind {
    match value {
        "notes" => AppKind::Notes,
        "calculator" => AppKind::Calculator,
        "terminal" => AppKind::Terminal,
        _ => usage(),
    }
}

fn observe_generation() -> Result<String, String> {
    match request(&Request::Snapshot).map_err(|err| err.to_string())? {
        Response::Snapshot {
            session_instance, ..
        } => Ok(session_instance),
        Response::Error { message, .. } => Err(message),
        _ => Err("session did not return a snapshot".into()),
    }
}

/// An acknowledged IPC message is not necessarily a successful action.
/// A failed spawn remains a failed CLI invocation even though the transport
/// returned a well-formed Task rather than an Error.
fn acknowledged(response: &Response) -> bool {
    match response {
        Response::Snapshot { .. } => true,
        Response::Error { .. } | Response::Objective { .. } => false,
        Response::Task { task, .. } => !matches!(
            task.state,
            TaskState::Failed | TaskState::Partial | TaskState::Unknown | TaskState::Pending,
        ),
    }
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let request_message = match args.as_slice() {
        [command] if command == "snapshot" => Request::Snapshot,
        [command, workspace, kind] if command == "launch" => {
            let expected_instance = match observe_generation() {
                Ok(id) => id,
                Err(error) => {
                    eprintln!("trill-ctl: cannot fence launch without session snapshot: {error}");
                    return ExitCode::FAILURE;
                }
            };
            Request::Launch {
                workspace: parse_workspace(workspace),
                app: parse_app(kind),
                expected_instance,
            }
        }
        [command, id, expected_instance] if command == "cancel" => {
            let Ok(id) = id.parse::<u64>() else { usage() };
            if expected_instance.is_empty() {
                usage()
            }
            Request::Cancel {
                id,
                expected_instance: expected_instance.clone(),
            }
        }
        _ => usage(),
    };
    let response = match request(&request_message) {
        Ok(result) => result,
        Err(err) => {
            eprintln!("trill-ctl: host session unavailable: {err}");
            return ExitCode::FAILURE;
        }
    };
    match serde_json::to_string_pretty(&response) {
        Ok(json) => println!("{json}"),
        Err(err) => {
            eprintln!("trill-ctl: response JSON error: {err}");
            return ExitCode::FAILURE;
        }
    }
    if acknowledged(&response) {
        ExitCode::SUCCESS
    } else {
        ExitCode::FAILURE
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn workspace_codes_are_not_dynamic_os_permissions() {
        assert_eq!(parse_workspace("build"), Workspace::Build);
        assert_eq!(parse_app("notes"), AppKind::Notes);
    }

    #[test]
    fn failed_spawn_and_unknown_effect_cannot_exit_successfully() {
        let mut task = trill_ui_core::TaskRecord::new(1, Workspace::Build, AppKind::Notes);
        task.state = TaskState::Failed;
        assert!(!acknowledged(&Response::Task {
            task: task.clone(),
            session_instance: "test".into(),
        }));
        task.state = TaskState::Unknown;
        assert!(!acknowledged(&Response::Task {
            task: task.clone(),
            session_instance: "test".into(),
        }));
        task.state = TaskState::Running;
        assert!(acknowledged(&Response::Task {
            task,
            session_instance: "test".into(),
        }));
        assert!(!acknowledged(&Response::Error {
            message: "not attempted".into(),
            session_instance: "test".into(),
        }));
    }
}
