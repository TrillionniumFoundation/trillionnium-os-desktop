//! Fail-closed Settings page admission. The selected runtime has no verified
//! framework-created-task authority, so the production entry sends no Android
//! command. Differential task/window/cleanup preparation is compiled only in
//! tests; a snapshot, successful start or JSON declaration cannot authorize it.
use serde::{Deserialize, Serialize};
#[cfg(test)]
use sha2::{Digest, Sha256};
#[cfg(test)]
use std::time::Duration;
use std::time::Instant;

#[cfg(test)]
use super::application_probe::{self, RuntimeEpoch};
use super::application_probe::{AndroidProbe, ApplicationInspection};
#[path = "application_action_scope.rs"]
mod action_scope;
#[path = "application_settings_protocol.rs"]
mod protocol;
#[cfg(test)]
use action_scope::ActionScope;
pub use protocol::{Bounds, Focus, TaskCandidate, WindowObservation};
#[cfg(test)]
use protocol::{SETTINGS, Tasks};

#[cfg(test)]
const LAUNCHER: &str = "/vendor/bin/droidloom-task-launcher";
#[cfg(test)]
const HELPER: &str = "local.pocket4.actions.v2";
#[cfg(test)]
const HELPER_SHA: &str = "a5368465d5f6faef3299bf1ba6d6bde268cc8b37c72401c6e668872b24725058";
#[cfg(test)]
const HELPER_BYTES: u64 = 20847;
#[cfg(test)]
const CLEANUP_RESERVE: Duration = Duration::from_secs(25);
// Exact source-observed ActionRunner v2 request, not caller-provided instructions:
// {"op":"dump","expected_package":"com.android.settings","display":0,"accessibility_mode":"none"}
#[cfg(test)]
const DUMP_REQUEST: &str = "eyJvcCI6ImR1bXAiLCJleHBlY3RlZF9wYWNrYWdlIjoiY29tLmFuZHJvaWQuc2V0dGluZ3MiLCJkaXNwbGF5IjowLCJhY2Nlc3NpYmlsaXR5X21vZGUiOiJub25lIn0=";

/// Fixed page requests. Execution remains blocked until actual framework task
/// creation authority is implemented and qualified for the selected runtime.
#[derive(Clone, Copy, Debug, Deserialize, Serialize, Eq, PartialEq, Ord, PartialOrd)]
#[serde(rename_all = "snake_case")]
pub enum SettingsPage {
    /// Main system Settings page.
    System,
    /// Network settings page; no network state is changed.
    Network,
    /// Display settings page; no display setting is changed.
    Display,
    /// Internal storage settings page; no file or app data is touched.
    Storage,
    /// Application settings list; no grant, install or uninstall is requested.
    Applications,
}

#[cfg(test)]
impl SettingsPage {
    fn action(self) -> &'static str {
        match self {
            Self::System => "android.settings.SETTINGS",
            Self::Network => "android.settings.WIRELESS_SETTINGS",
            Self::Display => "android.settings.DISPLAY_SETTINGS",
            Self::Storage => "android.settings.INTERNAL_STORAGE_SETTINGS",
            Self::Applications => "android.settings.APPLICATION_SETTINGS",
        }
    }
}

/// Structured observations, including uncertain cleanup; never an app approval.
#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct SettingsObservation {
    /// Requested fixed page.
    pub page: SettingsPage,
    /// Actual Settings PM/APK identity rechecked for this invocation.
    pub inspection: ApplicationInspection,
    /// Actual helper PM identity; its UID is queried rather than hardcoded.
    pub helper_inspection: ApplicationInspection,
    /// Actual PackageManager resolution for the fixed page action.
    pub resolved_component: String,
    /// Actual single-launch ACK, if obtained.
    pub launch_output: Option<String>,
    /// Fresh task snapshot before launch.
    pub tasks_before: String,
    /// Fresh task snapshot after launch, if obtained.
    pub tasks_after_launch: Option<String>,
    /// Differential candidate only; not a framework-created-task authority.
    pub task_candidate: Option<TaskCandidate>,
    /// WindowManager and complete native node observation, if obtained.
    pub window: Option<WindowObservation>,
    /// Readback before the only permitted removal command.
    pub tasks_before_cleanup: Option<String>,
    /// Every bounded removal-completion readback, including failures.
    pub cleanup_readbacks: Vec<String>,
    /// True only after the task disappeared and other task topology was restored.
    pub cleanup_confirmed: bool,
    /// Failure detail; a failed page is never automatically rerun.
    pub failure: Option<String>,
    /// Unknown work keeps the shared flock and durable pending intent.
    pub action_scope_retained: bool,
    /// Always false. Caller must inspect an uncertain result explicitly.
    pub automatic_retry: bool,
    /// Always zero; all Settings and common gates remain pending.
    pub accepted_gates: u32,
    /// Always false; this partial page entry is not runtime qualification.
    pub runtime_qualified: bool,
    /// Always false; no ProductionCell admission is provided here.
    pub production_ready: bool,
}

impl SettingsObservation {
    /// No JSON receipt can manufacture the absent framework creation authority.
    /// Even a complete synthetic fixture therefore grants no executable success.
    pub fn completed_partial(&self) -> bool {
        false
    }
}

/// Only the lifecycle daemon implements the deadline-aware held-FD transport.
pub(super) trait SettingsProbe: AndroidProbe {
    fn command_until(&mut self, args: &[String], deadline: Instant) -> Result<String, String>;
}

#[cfg(test)]
struct Bounded<'a, P> {
    inner: &'a mut P,
    deadline: Instant,
}
#[cfg(test)]
impl<P: SettingsProbe> AndroidProbe for Bounded<'_, P> {
    fn epoch(&mut self) -> Result<RuntimeEpoch, String> {
        within(self.deadline)?;
        let value = self.inner.epoch()?;
        within(self.deadline)?;
        Ok(value)
    }
    fn command(&mut self, args: &[String]) -> Result<String, String> {
        within(self.deadline)?;
        let output = self.inner.command_until(args, self.deadline)?;
        within(self.deadline)?;
        Ok(output)
    }
}

#[cfg(test)]
fn within(deadline: Instant) -> Result<(), String> {
    if Instant::now() >= deadline {
        Err("Settings observation absolute lease expired".into())
    } else {
        Ok(())
    }
}
#[cfg(test)]
fn args(values: &[&str]) -> Vec<String> {
    values.iter().map(|s| (*s).to_owned()).collect()
}
#[cfg(test)]
fn run(probe: &mut impl AndroidProbe, values: &[&str]) -> Result<String, String> {
    probe.command(&args(values))
}
#[cfg(test)]
fn snapshot(probe: &mut impl AndroidProbe) -> Result<String, String> {
    run(probe, &["/system/bin/cmd", "activity", "stack", "list"])
}
#[cfg(test)]
fn same_epoch(
    probe: &mut impl AndroidProbe,
    expected: &ApplicationInspection,
) -> Result<(), String> {
    if probe.epoch()? != expected.epoch {
        return Err("Settings framework generation changed".into());
    }
    Ok(())
}
#[cfg(test)]
fn same_installed(
    probe: &mut impl AndroidProbe,
    expected: &ApplicationInspection,
) -> Result<(), String> {
    if application_probe::inspect(probe, &expected.package, expected.user)? != *expected {
        return Err("Settings invocation installed identity changed".into());
    }
    Ok(())
}
#[cfg(test)]
fn pinned_helper(helper: &ApplicationInspection) -> Result<(), String> {
    let [apk] = helper.apks.as_slice() else {
        return Err("native UI helper APK set differs from the reviewed artifact".into());
    };
    if helper.package != HELPER
        || helper.user != 0
        || helper.version_code != 2
        || apk.name != "base.apk"
        || apk.bytes != HELPER_BYTES
        || apk.sha256 != HELPER_SHA
    {
        return Err("native UI helper is absent or differs from its reviewed v2 APK bytes".into());
    }
    Ok(())
}

pub(super) const FRAMEWORK_AUTHORITY_BLOCKER: &str = "Settings page execution blocked: selected framework created-task authority is unavailable; no launch, registration or cleanup authorized";

pub(super) fn require_clear_pending() -> Result<(), String> {
    action_scope::ensure_no_pending().map_err(|e| e.to_string())
}

#[cfg(test)]
pub(super) fn pending_guard_at(path: &std::path::Path, owner: u32) -> Result<(), String> {
    action_scope::ensure_no_pending_in(path, owner).map_err(|e| e.to_string())
}

pub(super) fn observe(
    _expected: &ApplicationInspection,
    _page: SettingsPage,
) -> Result<SettingsObservation, String> {
    // This is an unconditional code gate, not a config, JSON boolean, ACK, or
    // task-difference assertion. A future provider must carry real framework
    // creation semantics before this production entry can call any UI path.
    Err(FRAMEWORK_AUTHORITY_BLOCKER.into())
}

#[cfg(test)]
fn observe_with_scope(
    probe: &mut impl SettingsProbe,
    expected: &ApplicationInspection,
    page: SettingsPage,
    deadline: Instant,
    mut scope: ActionScope<'_>,
) -> Result<SettingsObservation, String> {
    if expected.package != SETTINGS || expected.user != 0 {
        return Err("only the selected user-0 Settings package supports this page entry".into());
    }
    let deadline = deadline.min(Instant::now() + Duration::from_secs(90));
    let business_deadline = deadline
        .checked_sub(CLEANUP_RESERVE)
        .ok_or("Settings cleanup reserve unavailable")?;
    let mut business = Bounded {
        inner: probe,
        deadline: business_deadline,
    };
    within(business_deadline)?;
    same_installed(&mut business, expected)?;
    let helper = application_probe::inspect(&mut business, HELPER, 0)?;
    pinned_helper(&helper)?;
    if helper.epoch != expected.epoch {
        return Err("helper belongs to another framework generation".into());
    }
    let protocol = run(
        &mut business,
        &[LAUNCHER, "--settings-observation-protocol"],
    )?;
    if protocol != "droidloom-settings-observation-v1" {
        return Err("installed vendor launcher has no exact Settings observation protocol; rebuild/deploy required".into());
    }
    let resolved = protocol::resolved_component(&run(
        &mut business,
        &[
            "/system/bin/cmd",
            "package",
            "resolve-activity",
            "--brief",
            "--user",
            "0",
            "-a",
            page.action(),
        ],
    )?)?;
    let before_raw = snapshot(&mut business)?;
    let before = Tasks::parse(&before_raw)?;
    if before.has_settings() {
        return Err("preexisting Settings tasks are preserved; observation not started".into());
    }
    same_epoch(&mut business, expected)?;
    let intent = serde_json::to_vec(&serde_json::json!({
        "schema":"droidloom-settings-observation-intent-v1","page":page,
        "expected":expected,"helper":helper,"resolved_component":resolved,
        "tasks_before_sha256":format!("{:x}",Sha256::digest(before_raw.as_bytes())),
        "automatic_retry":false,"production_ready":false,"runtime_qualified":false,
    }))
    .map_err(|e| e.to_string())?;
    scope.before_start(&intent).map_err(|e| e.to_string())?;
    let mut report = SettingsObservation {
        page,
        inspection: expected.clone(),
        helper_inspection: helper.clone(),
        resolved_component: resolved.clone(),
        launch_output: None,
        tasks_before: before_raw,
        tasks_after_launch: None,
        task_candidate: None,
        window: None,
        tasks_before_cleanup: None,
        cleanup_readbacks: Vec::new(),
        cleanup_confirmed: false,
        failure: None,
        action_scope_retained: true,
        automatic_retry: false,
        accepted_gates: 0,
        runtime_qualified: false,
        production_ready: false,
    };
    let mut helper_settled = true;
    let observation = (|| -> Result<(), String> {
        let launch = run(
            &mut business,
            &[
                LAUNCHER,
                "--observe-settings-page",
                page.action(),
                "--user",
                "0",
                "--component",
                &resolved,
                SETTINGS,
            ],
        )?;
        report.launch_output = Some(launch.clone());
        let id = protocol::launch_task(&launch)?;
        let after_raw = snapshot(&mut business)?;
        report.tasks_after_launch = Some(after_raw.clone());
        let owned = Tasks::parse(&after_raw)?.candidate_after(&before, id)?;
        report.task_candidate = Some(owned.clone());
        if owned.component != resolved {
            return Err("created task base differs from the page's PM resolution".into());
        }
        // The helper's APK identity is rechecked immediately before asking it
        // to connect UIAutomation. No caller-supplied instrumentation is allowed.
        same_installed(&mut business, &helper)?;
        let front = protocol::focus(
            &run(
                &mut business,
                &["/system/bin/dumpsys", "window", "displays"],
            )?,
            &owned,
        )?;
        helper_settled = false;
        let native = run(
            &mut business,
            &[
                "/system/bin/am",
                "instrument",
                "-w",
                "-r",
                "-e",
                "request",
                DUMP_REQUEST,
                "local.pocket4.actions.v2/.ActionRunner",
            ],
        )?;
        let (dump, json) = protocol::native_dump(&native)?;
        if !dump.accessibility_mode_restoration_verified {
            return Err(
                "native helper did not prove accessibility-state restoration; scope retained"
                    .into(),
            );
        }
        helper_settled = true;
        if !dump.ok {
            return Err("native helper returned a settled observation failure".into());
        }
        let window = protocol::validate_dump(json, &owned, front.clone())?;
        let after_focus = protocol::focus(
            &run(
                &mut business,
                &["/system/bin/dumpsys", "window", "displays"],
            )?,
            &owned,
        )?;
        if after_focus != front {
            return Err("Settings focus token changed during native collection".into());
        }
        let still = Tasks::parse(&snapshot(&mut business)?)?.candidate_after(&before, id)?;
        if still != owned {
            return Err("owned Settings task changed during native collection".into());
        }
        same_installed(&mut business, expected)?;
        same_installed(&mut business, &helper)?;
        same_epoch(&mut business, expected)?;
        report.window = Some(window);
        Ok(())
    })();
    if let Err(error) = observation {
        report.failure = Some(error);
    }
    drop(business);

    // A native helper timeout or malformed/restoration-unknown response can
    // outlive the host am process. Never confuse cgroup retirement with that
    // Android instrumentation's completion or release its action scope.
    if helper_settled {
        if let Some(owned) = report.task_candidate.clone() {
            match cleanup_task(probe, expected, &before, &owned, deadline, &mut report) {
                Ok(()) => match scope.finish_after_verified_cleanup() {
                    Ok(()) => {
                        report.cleanup_confirmed = true;
                    }
                    Err(e) => append_failure(
                        &mut report,
                        format!("task removed but pending intent retirement failed: {e}"),
                    ),
                },
                Err(e) => {
                    append_failure(&mut report, format!("owned task cleanup unconfirmed: {e}"))
                }
            }
        }
    }
    if let Err(e) = within(deadline) {
        append_failure(&mut report, e);
    }
    report.action_scope_retained = scope.pending();
    if report.failure.is_none() && (!report.cleanup_confirmed || report.window.is_none()) {
        append_failure(
            &mut report,
            "Settings page observation is incomplete".into(),
        );
    }
    Ok(report)
}

#[cfg(test)]
fn append_failure(report: &mut SettingsObservation, error: String) {
    let error: String = error.chars().take(1024).collect();
    report.failure = Some(match report.failure.take() {
        Some(old) => format!("{old}; {error}"),
        None => error,
    });
}

#[cfg(test)]
fn cleanup_task(
    probe: &mut impl SettingsProbe,
    expected: &ApplicationInspection,
    before: &Tasks,
    owned: &TaskCandidate,
    deadline: Instant,
    report: &mut SettingsObservation,
) -> Result<(), String> {
    let mut probe = Bounded {
        inner: probe,
        deadline,
    };
    same_epoch(&mut probe, expected)?;
    let raw = snapshot(&mut probe)?;
    report.tasks_before_cleanup = Some(raw.clone());
    if Tasks::parse(&raw)?.candidate_after(before, owned.id)? != *owned {
        return Err("current task differs from the exact causal claim; removal not sent".into());
    }
    within(deadline)?;
    // Exactly one normal task removal. No force-stop, package data deletion,
    // cell retirement, or removal retry exists in this entry.
    run(
        &mut probe,
        &[
            "/system/bin/cmd",
            "activity",
            "stack",
            "remove",
            &owned.id.to_string(),
        ],
    )?;
    let completion = deadline.min(Instant::now() + Duration::from_secs(8));
    probe.deadline = completion;
    for _ in 0..32 {
        within(completion)?;
        let raw = snapshot(&mut probe)?;
        report.cleanup_readbacks.push(raw.clone());
        let current = Tasks::parse(&raw)?;
        within(completion)?;
        if current.removed_to(before, owned.id) {
            same_epoch(&mut probe, expected)?;
            return Ok(());
        }
        current.removal_pending(before, owned)?;
        let remaining = completion.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Err("Settings removal completion lease expired".into());
        }
        std::thread::sleep(remaining.min(Duration::from_millis(250)));
    }
    Err("Settings task removal remains unconfirmed after bounded readbacks".into())
}

#[cfg(test)]
#[path = "application_settings_tests.rs"]
mod tests;
