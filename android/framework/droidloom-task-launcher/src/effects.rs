//! Launch resolution driven by a borrowed, externally owned executor.
//!
//! This module opens no paths, sockets or processes. The executor supplies
//! authenticated command results and task-control exchanges. In particular,
//! implementing this interface does not create production execution authority:
//! a production adapter must borrow the original Ready owner, retain its
//! admission and package/APK identity, and retire every command before returning.
//! The existing process-spawning launcher is not such an adapter.

use std::collections::BTreeSet;
use std::process::Output;
use std::time::{Duration, Instant};

use droidloom_task_control::{
    ControlRequest, ControlResponse, MAX_PACKAGE_BYTES, MAX_RECORD_BYTES, PROTOCOL_MAJOR,
    encode_request, encode_response,
};

use super::{
    ACTIVITY_DISCOVERY_ATTEMPTS, DISCOVERY_INTERVAL, LaunchError, LaunchRequest, TaskBinding,
    bounded_text, checked_activity_output, completed_alias, completed_launch_activity,
    discover_launch_candidates, is_pending_display_error, is_play_store_sign_in,
    matching_tasks_with, normalized_component, permission_dialog_component, response_error,
    validate_request,
};

/// Maximum remaining time accepted for one prepared launch operation.
pub const LAUNCH_LIMIT: Duration = Duration::from_secs(120);
/// Combined stdout/stderr bound, matching the production command executor.
pub const COMMAND_OUTPUT_LIMIT: usize = 65_536;

/// Only these four command shapes belong to task resolution and launch.
/// Executable paths, credentials, namespaces and MAC roles belong to the owner.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum AndroidCommand {
    /// Observe tasks on Android's built-in display.
    ListTasks,
    /// Resolve the framework's system-only permission activity.
    ResolvePermissionDialog {
        /// Android user bound by the operation's owner.
        user: u32,
    },
    /// Start the exact package or owned component on display zero.
    Start {
        /// Validated inputs of this one operation.
        request: LaunchRequest,
    },
    /// Resolve an alias for the same launch intent, without starting it again.
    ResolveAlias {
        /// The same package, component and user used for the start.
        request: LaunchRequest,
    },
}

impl AndroidCommand {
    /// Return literal arguments for the owner's fixed Android `cmd` asset.
    /// No shell command, binary path, arbitrary intent or extra flag is accepted.
    ///
    /// # Errors
    /// Rejects invalid request values before constructing any command.
    pub fn arguments(&self) -> Result<Vec<String>, LaunchError> {
        let mut values: Vec<String> = match self {
            Self::ListTasks => vec!["activity".into(), "stack".into(), "list".into()],
            Self::ResolvePermissionDialog { user } => {
                if *user > i32::MAX as u32 {
                    return Err(LaunchError::InvalidRequest(
                        "Android user exceeds i32".into(),
                    ));
                }
                vec![
                    "package".into(),
                    "resolve-activity".into(),
                    "--components".into(),
                    "--query-flags".into(),
                    "1048576".into(),
                    "--user".into(),
                    user.to_string(),
                    "-a".into(),
                    "android.content.pm.action.REQUEST_PERMISSIONS".into(),
                ]
            }
            Self::Start { request } => {
                validate_bound_request(request)?;
                let mut values = vec![
                    "activity".into(),
                    "start-activity".into(),
                    "-W".into(),
                    "--display".into(),
                    "0".into(),
                    "--windowingMode".into(),
                    "5".into(),
                    "--user".into(),
                    request.user.to_string(),
                ];
                if let Some((width, height)) = request.resolution {
                    values.extend([
                        "-S".into(),
                        "--droidloom-resolution".into(),
                        format!("{width}x{height}"),
                    ]);
                }
                values
            }
            Self::ResolveAlias { request } => {
                validate_bound_request(request)?;
                vec![
                    "package".into(),
                    "resolve-activity".into(),
                    "--user".into(),
                    request.user.to_string(),
                ]
            }
        };
        if let Self::Start { request } | Self::ResolveAlias { request } = self {
            if let Some(component) = &request.component {
                values.extend(["-n".into(), component.clone()]);
            } else {
                values.extend([
                    "-a".into(),
                    "android.intent.action.MAIN".into(),
                    "-c".into(),
                    "android.intent.category.LAUNCHER".into(),
                    "-p".into(),
                    request.package.clone(),
                ]);
            }
        }
        Ok(values)
    }
}

/// Effects supplied by the caller that owns the live execution tree.
///
/// A production implementation must borrow the original Ready witness; it must
/// not rediscover a PID, create an admission from a receipt, reconnect to a
/// different Composer, or call the development launcher. A successful method
/// return must follow actual command retirement (including descendants), or
/// the original owner must remain fenced. The same absolute `deadline` applies
/// to command I/O, IPC, waiting and all revalidation. This module also checks it
/// before and after every effect, but cannot preempt a blocking implementation.
///
/// The adapter must already hold the prepared display policy and authenticated
/// task-control endpoint. This interface grants no policy mutation, installation,
/// account, URI, arbitrary command or whole-application acceptance capability.
pub trait LaunchEffects {
    /// Revalidate the original Ready owner, framework epoch and bound request.
    /// Package/UID/version/APK-set identity must be fixed before entry and checked
    /// again before a successful result is exposed to a control client.
    fn revalidate(&mut self, request: &LaunchRequest, deadline: Instant)
    -> Result<(), LaunchError>;

    /// Execute one closed command through the owner's fixed executable/MAC role.
    /// Enforce the output bound while reading and finish its retirement before
    /// returning either its actual exit status/output or an error.
    fn android(
        &mut self,
        command: &AndroidCommand,
        deadline: Instant,
    ) -> Result<Output, LaunchError>;

    /// Exchange one record on one dedicated, authenticated task-control channel.
    /// Enforce the protocol record bound and reject received descriptors. The
    /// operation negotiates Hello once, then sends only RegisterDirect(id=1).
    fn exchange(
        &mut self,
        request: &ControlRequest,
        deadline: Instant,
    ) -> Result<ControlResponse, LaunchError>;

    /// Wait at most `interval`, cooperatively checking the same owner/deadline.
    /// This must not reset the operation's time budget or leave a background task.
    fn wait(&mut self, interval: Duration, deadline: Instant) -> Result<(), LaunchError>;
}

/// Resolve, start, discover and bind one task using caller-owned effects.
///
/// This is the lower interface for a future production Ready-owner adapter.
/// It deliberately does not construct that adapter or enable `ControlRequest::Launch`.
/// The returned binding acknowledges task-control only; it is not rendering,
/// business-flow, Android-runtime or whole-app qualification.
///
/// # Errors
/// Rejects invalid inputs, expired/oversized budgets, owner changes, command or
/// control failures, and ambiguous tasks. An error after start/registration can
/// follow an already performed Android side effect. The caller must preserve
/// that failure; there is no automatic relaunch, unregister or false success.
pub fn launch_prepared(
    effects: &mut impl LaunchEffects,
    request: &LaunchRequest,
    deadline: Instant,
) -> Result<TaskBinding, LaunchError> {
    validate_bound_request(request)?;
    let remaining = deadline
        .checked_duration_since(Instant::now())
        .ok_or(LaunchError::Deadline)?;
    if remaining.is_zero() || remaining > LAUNCH_LIMIT {
        return Err(LaunchError::Deadline);
    }
    let hello = effect(effects, request, deadline, |effects| {
        effects.exchange(
            &ControlRequest::Hello {
                min_major: PROTOCOL_MAJOR,
                max_major: PROTOCOL_MAJOR,
            },
            deadline,
        )
    })?;
    check_hello(hello)?;

    let before = command(
        effects,
        request,
        AndroidCommand::ListTasks,
        deadline,
        "stack list before launch",
    )?;
    let preexisting =
        matching_tasks_with(&before, 0, &request.package, Some(request.user), |_| true)?
            .into_iter()
            .collect::<BTreeSet<_>>();
    let permission = command(
        effects,
        request,
        AndroidCommand::ResolvePermissionDialog { user: request.user },
        deadline,
        "resolve system permission dialog",
    )?;
    let permission = permission_dialog_component(&permission)?;
    let completed = start(effects, request, permission.as_deref(), deadline)?;
    let alias = if permission.as_deref() == Some(completed.as_str())
        || is_play_store_sign_in(&request.package, &completed)
        || request
            .component
            .as_deref()
            .and_then(normalized_component)
            .as_deref()
            == Some(completed.as_str())
    {
        None
    } else {
        let output = command(
            effects,
            request,
            AndroidCommand::ResolveAlias {
                request: request.clone(),
            },
            deadline,
            "resolve launch alias",
        )?;
        completed_alias(&output, &request.package, &completed)
    };

    let mut last_listing = String::new();
    for attempt in 0..ACTIVITY_DISCOVERY_ATTEMPTS {
        last_listing = command(
            effects,
            request,
            AndroidCommand::ListTasks,
            deadline,
            "stack list",
        )?;
        let tasks = discover_launch_candidates(
            &last_listing,
            0,
            request,
            &completed,
            alias.as_deref(),
            permission.as_deref(),
            &preexisting,
        )?;
        match tasks.as_slice() {
            [task] => {
                if *task > i32::MAX as u64 {
                    return Err(LaunchError::Discovery(
                        "task identity exceeds Android's signed range".into(),
                    ));
                }
                let response = effect(effects, request, deadline, |effects| {
                    effects.exchange(
                        &ControlRequest::RegisterDirect {
                            request_id: 1,
                            package: request.package.clone(),
                            task: *task,
                            android_display: 0,
                        },
                        deadline,
                    )
                })?;
                let binding = check_binding(1, *task, 0, response)?;
                checkpoint(effects, request, deadline)?;
                return Ok(binding);
            }
            [] if attempt + 1 < ACTIVITY_DISCOVERY_ATTEMPTS => pause(effects, request, deadline)?,
            [] => break,
            _ => {
                return Err(LaunchError::Discovery(format!(
                    "package {} created multiple tasks {tasks:?} on Android display 0",
                    request.package
                )));
            }
        }
    }
    Err(LaunchError::Discovery(format!(
        "package {} has no unambiguous completed activity task on Android display 0; preexisting tasks: {preexisting:?}; last activity listing: {}",
        request.package,
        bounded_text(&last_listing)
    )))
}

fn validate_bound_request(request: &LaunchRequest) -> Result<(), LaunchError> {
    // Check lengths before walking attacker-supplied text. Components use our
    // fixed protocol-record-size ceiling; this is not an Android platform limit.
    if request.package.len() > MAX_PACKAGE_BYTES
        || request
            .component
            .as_ref()
            .is_some_and(|value| value.len() > MAX_RECORD_BYTES)
    {
        return Err(LaunchError::InvalidRequest(
            "launch identity exceeds its fixed text bound".into(),
        ));
    }
    validate_request(request)?;
    // Fail before starting an activity if its package cannot form the eventual
    // protocol request. This uses the actual protocol's fixed package bound.
    encode_request(&ControlRequest::RegisterDirect {
        request_id: 1,
        package: request.package.clone(),
        task: 1,
        android_display: 0,
    })?;
    Ok(())
}

fn checkpoint(
    effects: &mut impl LaunchEffects,
    request: &LaunchRequest,
    deadline: Instant,
) -> Result<(), LaunchError> {
    if Instant::now() >= deadline {
        return Err(LaunchError::Deadline);
    }
    effects.revalidate(request, deadline)?;
    if Instant::now() >= deadline {
        return Err(LaunchError::Deadline);
    }
    Ok(())
}

fn effect<T>(
    effects: &mut impl LaunchEffects,
    request: &LaunchRequest,
    deadline: Instant,
    run: impl FnOnce(&mut dyn LaunchEffects) -> Result<T, LaunchError>,
) -> Result<T, LaunchError> {
    checkpoint(effects, request, deadline)?;
    let result = run(effects);
    // Run the post-effect fence even on an I/O/retirement error. Preserve that
    // original error instead of replacing it with a secondary fence failure.
    let after = checkpoint(effects, request, deadline);
    let value = result?;
    after?;
    Ok(value)
}

fn command(
    effects: &mut impl LaunchEffects,
    request: &LaunchRequest,
    operation: AndroidCommand,
    deadline: Instant,
    description: &str,
) -> Result<String, LaunchError> {
    operation.arguments()?;
    let output = effect(effects, request, deadline, |effects| {
        effects.android(&operation, deadline)
    })?;
    if output
        .stdout
        .len()
        .checked_add(output.stderr.len())
        .is_none_or(|size| size > COMMAND_OUTPUT_LIMIT)
    {
        return Err(LaunchError::Activity(
            "command output exceeds its combined bound".into(),
        ));
    }
    if std::str::from_utf8(&output.stdout).is_err() || std::str::from_utf8(&output.stderr).is_err()
    {
        return Err(LaunchError::Activity("command output is not UTF-8".into()));
    }
    checked_activity_output(&output, description)
}

fn pause(
    effects: &mut impl LaunchEffects,
    request: &LaunchRequest,
    deadline: Instant,
) -> Result<(), LaunchError> {
    let remaining = deadline
        .checked_duration_since(Instant::now())
        .ok_or(LaunchError::Deadline)?;
    effect(effects, request, deadline, |effects| {
        effects.wait(DISCOVERY_INTERVAL.min(remaining), deadline)
    })
}

fn start(
    effects: &mut impl LaunchEffects,
    request: &LaunchRequest,
    permission: Option<&str>,
    deadline: Instant,
) -> Result<String, LaunchError> {
    for attempt in 0..ACTIVITY_DISCOVERY_ATTEMPTS {
        match command(
            effects,
            request,
            AndroidCommand::Start {
                request: request.clone(),
            },
            deadline,
            "start-activity",
        ) {
            Ok(output) => return completed_launch_activity(&output, &request.package, permission),
            Err(error)
                if is_pending_display_error(&error, 0)
                    && attempt + 1 < ACTIVITY_DISCOVERY_ATTEMPTS =>
            {
                pause(effects, request, deadline)?;
            }
            Err(error) => return Err(error),
        }
    }
    unreachable!("the final attempt returns its result")
}

pub(super) fn check_hello(response: ControlResponse) -> Result<(), LaunchError> {
    encode_response(&response)?;
    match response {
        ControlResponse::ServerHello { major, .. } if major == PROTOCOL_MAJOR => Ok(()),
        response => Err(LaunchError::Control(format!(
            "unexpected hello response {response:?}"
        ))),
    }
}

pub(super) fn check_binding(
    request_id: u64,
    task: u64,
    android_display: u32,
    response: ControlResponse,
) -> Result<TaskBinding, LaunchError> {
    encode_response(&response)?;
    match response {
        ControlResponse::Bound {
            request_id: actual,
            object,
            task: actual_task,
            display,
            android_display: actual_android_display,
        } if actual == request_id
            && actual_task == task
            && actual_android_display == android_display =>
        {
            Ok(TaskBinding {
                object,
                composer_display: display,
                android_display: u64::from(android_display),
                task,
            })
        }
        response => Err(response_error(request_id, response)),
    }
}

#[cfg(test)]
#[path = "effects_tests.rs"]
mod tests;
