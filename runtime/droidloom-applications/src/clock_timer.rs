//! Actual Clock timer15 + expiry06 observations joined to normal Main/copy custody.
//!
//! Only the source-admitted material/peer factory can construct the result.
//! Saved JSON is never execution authority. One held Main, source/owner lease
//! and both first-read result FDs span the unchanged cases and their cleanup.
//! The resulting credit is only clock.timer; engine and whole-app gates remain.
use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, File, OpenOptions};
use std::os::fd::AsRawFd;
use std::os::unix::fs::OpenOptionsExt;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use droidloom_supervisor::control::{
    self, application_probe::ApplicationInspection,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};

use super::leaf_release::{self, Inputs, NativeRelease};
use super::leaf_routes::{self, ExecutedClockCase, HeldMainCustody, LeafObservation, LeafPlan, Route};
use super::runtime_identity::{IdentityObservation, VerifiedMaterialBatch};
use super::{ApplicationPlan, FilePin, RuntimePlan, consume_inspection};

const PACKAGE: &str = "com.android.deskclock";
const REQUEST_SCHEMA: &str = "droidloom.clock-timer-pair-request.v1";
const RESULT_SCHEMA: &str = "pocket4-current-clock-original-case-result-v1";
const UNUSED: i64 = i64::MIN;
// Two unchanged 510-second original leaf limits, three normal 250-second
// package inspections, 120 seconds for finite source/owner bookends, and
// exactly three normal Main transport allowances (observe + two revalidate).
// This covers 2100 seconds of factory work/retirement on one original lease;
// it never extends the lease or claims the outer dispatch/transport budget.
const PAIR_WINDOW_SECONDS: u64 = 2 * 510 + 3 * 250 + 120 + 3 * 70;
const SOURCE_NAMES: [&str; 27] = [
    "app_common.py", "app_runtime.py", "clock_alarm_flow.py", "clock_alarm_reader.py",
    "clock_api.py", "clock_audio_observe.py", "clock_case.py", "clock_continuation.py",
    "clock_delivery.py", "clock_delivery_trial.py", "clock_entry.py", "clock_expiry_flow.py",
    "clock_model.py", "clock_monitor_channel.py", "clock_notify_binding.py", "clock_notify_proof.py",
    "clock_notify_supervisor.py", "clock_plan.py", "clock_policy.py", "clock_preservation.py",
    "clock_profiles.py", "clock_protection.py", "clock_selectors.py", "clock_session.py",
    "clock_timer_core.py", "clock_transport_base.py", "runtime_dependencies.json",
];


// Clock's original case creates protection/commands/api directories beside its
// execution-plan.json. Parent inode/mode/owner custody remains exact, but a
// directory's link count legitimately changes with those normal children.
// Source/owner material still uses the unchanged, stricter Inputs guard.
// Every case input/result keeps the full nine-field held/named file identity.
struct ParentHold { path: PathBuf, file: File, identity: [u64; 5] }
struct CaseHold { pin: FilePin, file: File, identity: [u64; 9] }
struct CaseInputs {
    parents: BTreeMap<PathBuf, ParentHold>,
    files: Vec<CaseHold>,
    sources: Inputs,
}
impl CaseInputs {
    fn new() -> Self {
        Self { parents:BTreeMap::new(),files:Vec::new(),sources:Inputs::new() }
    }
    fn anchored(&self, path: &Path) -> Result<PathBuf, String> {
        if path == Path::new("/") { return Ok(path.into()); }
        let parent = self.parents.get(path.parent().ok_or("Clock input has no parent")?)
            .ok_or("Clock parent descriptor not held")?;
        Ok(PathBuf::from(format!("/proc/self/fd/{}",parent.file.as_raw_fd()))
            .join(path.file_name().ok_or("Clock input basename missing")?))
    }
    fn parent(&mut self, path: &Path) -> Result<(), String> {
        if self.parents.contains_key(path) { return Ok(()); }
        if let Some(parent) = path.parent() { self.parent(parent)?; }
        let anchored = self.anchored(path)?;
        let file = OpenOptions::new().read(true).custom_flags(0x20000 | 0x10000)
            .open(&anchored).map_err(|e| e.to_string())?;
        let identity: [u64;5] = leaf_release::f9(&file.metadata().map_err(|e| e.to_string())?)?[..5]
            .try_into().map_err(|_| "Clock parent identity".to_string())?;
        require(identity[2] & 0o170000 == 0o040000
            && leaf_release::f9(&fs::symlink_metadata(path).map_err(|e| e.to_string())?)?[..5] == identity
            && leaf_release::f9(&fs::symlink_metadata(anchored).map_err(|e| e.to_string())?)?[..5] == identity,
            "Clock parent is not the same held no-link directory")?;
        self.parents.insert(path.into(),ParentHold {path:path.into(),file,identity});
        Ok(())
    }
    fn read(&mut self, path: &Path, expected: Option<&FilePin>, maximum: u64) -> Result<Vec<u8>,String> {
        require(path.is_absolute() && path.canonicalize().map_err(|e|e.to_string())? == path,
            "Clock input path must be canonical")?;
        self.parent(path.parent().ok_or("Clock input has no parent")?)?;
        let anchored = self.anchored(path)?;
        let file = OpenOptions::new().read(true).custom_flags(0x20000)
            .open(&anchored).map_err(|e|e.to_string())?;
        let identity = leaf_release::f9(&file.metadata().map_err(|e|e.to_string())?)?;
        require(identity[2] & 0o170000 == 0o100000 && identity[5] == 1
            && identity[6] > 0 && identity[6] <= maximum,
            "Clock case input must be a bounded single-link regular file")?;
        let raw = leaf_release::body(&file,identity[6])?;
        let pin = FilePin {path:path.into(),bytes:raw.len() as u64,sha256:hex::encode(Sha256::digest(&raw))};
        require(expected.is_none_or(|v| v == &pin)
            && leaf_release::f9(&file.metadata().map_err(|e|e.to_string())?)? == identity
            && leaf_release::f9(&fs::symlink_metadata(path).map_err(|e|e.to_string())?)? == identity
            && leaf_release::f9(&fs::symlink_metadata(anchored).map_err(|e|e.to_string())?)? == identity,
            "Clock held case input changed or differs from its exact pin")?;
        self.files.push(CaseHold {pin,file,identity});
        Ok(raw)
    }
    fn identity(&self, path:&Path) -> Result<[u64;9],String> {
        self.files.iter().find(|f| f.pin.path == path).map(|f|f.identity)
            .ok_or("Clock case file not held".into())
    }
    fn guard(&self) -> Result<(),String> {
        self.sources.guard()?;
        for parent in self.parents.values() {
            require(leaf_release::f9(&parent.file.metadata().map_err(|e|e.to_string())?)?[..5] == parent.identity
                && leaf_release::f9(&fs::symlink_metadata(&parent.path).map_err(|e|e.to_string())?)?[..5] == parent.identity
                && leaf_release::f9(&fs::symlink_metadata(self.anchored(&parent.path)?).map_err(|e|e.to_string())?)?[..5] == parent.identity,
                "Clock case parent inode/mode/owner changed")?;
        }
        for held in &self.files {
            require(leaf_release::f9(&held.file.metadata().map_err(|e|e.to_string())?)? == held.identity
                && leaf_release::f9(&fs::symlink_metadata(&held.pin.path).map_err(|e|e.to_string())?)? == held.identity
                && leaf_release::f9(&fs::symlink_metadata(self.anchored(&held.pin.path)?).map_err(|e|e.to_string())?)? == held.identity,
                "Clock case held/named file identity changed")?;
            let digest = hex::encode(Sha256::digest(leaf_release::body(&held.file,held.identity[6])?));
            require(digest == held.pin.sha256
                && leaf_release::f9(&held.file.metadata().map_err(|e|e.to_string())?)? == held.identity
                && leaf_release::f9(&fs::symlink_metadata(&held.pin.path).map_err(|e|e.to_string())?)? == held.identity,
                "Clock full case body changed during final bookend")?;
        }
        Ok(())
    }
}


/// Read-only custody captured by the actual leaf executor at its first result
/// read. Custody alone grants no execution or acceptance authority.
pub(super) struct ClockResultCustody {
    reference: FilePin,
    inputs: CaseInputs,
}
impl ClockResultCustody {
    pub(super) fn capture_path(path: &Path) -> Result<(Self, Value), String> {
        let mut inputs = CaseInputs::new();
        let raw = inputs.read(path, None, super::INPUT_LIMIT)?;
        let reference = inputs.files.first().ok_or("executed result descriptor missing")?.pin.clone();
        let result = leaf_release::json(&raw)?;
        inputs.guard()?;
        Ok((Self { reference, inputs }, result))
    }
    pub(super) fn reference(&self) -> &FilePin { &self.reference }
    pub(super) fn capture(reference: &FilePin) -> Result<(Self, Value), String> {
        let mut inputs = CaseInputs::new();
        let result = read(&mut inputs, reference, super::INPUT_LIMIT)?;
        inputs.guard()?;
        Ok((Self { reference:reference.clone(),inputs }, result))
    }
    pub(super) fn read(&self) -> Result<Value, String> {
        self.guard()?;
        let held = self.inputs.files.first().ok_or("Clock execution result descriptor missing")?;
        require(self.inputs.files.len() == 1 && held.pin == self.reference,
            "Clock execution result custody is not its one original descriptor")?;
        let raw = leaf_release::body(&held.file,held.identity[6])?;
        self.guard()?;
        leaf_release::json(&raw)
    }
    pub(super) fn guard(&self) -> Result<(),String> { self.inputs.guard() }
    pub(super) fn identity(&self) -> Result<[u64;9],String> { self.inputs.identity(&self.reference.path) }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PairRequest {
    schema: String,
    timer15: FilePin,
    expiry06: FilePin,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
enum Kind { Timer15, Expiry06 }

impl Kind {
    fn name(self) -> &'static str {
        match self { Self::Timer15 => "timer15", Self::Expiry06 => "expiry06" }
    }
    fn route(self) -> Route {
        match self { Self::Timer15 => Route::ClockTimerRemaining, Self::Expiry06 => Route::ClockExpiry }
    }
    fn duration(self) -> i64 {
        match self { Self::Timer15 => 900_000, Self::Expiry06 => 60_000 }
    }
    fn action_limit(self) -> u64 {
        match self { Self::Timer15 => 20, Self::Expiry06 => 12 }
    }
}

fn require(ok: bool, reason: &str) -> Result<(), String> {
    if ok { Ok(()) } else { Err(reason.into()) }
}

fn pin(value: &Value) -> Result<FilePin, String> {
    serde_json::from_value(value.clone()).map_err(|error| error.to_string())
}

fn read(held: &mut CaseInputs, reference: &FilePin, maximum: u64) -> Result<Value, String> {
    leaf_release::json(&held.read(&reference.path, Some(reference), maximum)?)
}

fn reference(value: &Value, field: &str) -> Result<FilePin, String> {
    pin(value.get(field).ok_or_else(|| format!("Clock input lacks {field}"))?)
}

fn array<'a>(value: &'a Value, reason: &str) -> Result<&'a [Value], String> {
    value.as_array().map(Vec::as_slice).ok_or_else(|| reason.into())
}

fn integer(value: &Value, reason: &str) -> Result<i64, String> {
    value.as_i64().ok_or_else(|| reason.into())
}

fn empty_array(value: &Value) -> bool {
    value.as_array().is_some_and(Vec::is_empty)
}

fn nonempty_object(value: &Value) -> bool {
    value.as_object().is_some_and(|value| !value.is_empty())
}

fn same_objects(before: &Value, after: &Value) -> bool {
    nonempty_object(before) && before == after
}

fn empty_timer(value: &Value) -> Result<(), String> {
    require(empty_array(&value["ids"]) && empty_array(&value["timers"])
        && value["stopwatch"].as_object().is_some_and(|v| v.is_empty())
        && value["values"].as_object().is_some_and(|v|
            v.keys().all(|key| matches!(key.as_str(), "timers_list" | "next_timer_id"))),
        "Clock timer or stopwatch remains, or empty snapshot is incomplete")
}

struct Timer {
    remaining: i64,
    start: i64,
}

fn timer(value: &Value, id: i64, duration: i64, state: i64) -> Result<Timer, String> {
    let rows = array(&value["timers"], "Clock timer rows absent")?;
    require(value["ids"] == serde_json::json!([id]) && rows.len() == 1
        && value["stopwatch"].as_object().is_some_and(|v| v.is_empty()),
        "Clock snapshot does not contain exactly its one owned timer")?;
    let row = &rows[0];
    require(row["id"].as_i64() == Some(id) && row["state"].as_i64() == Some(state)
        && row["length_ms"].as_i64() == Some(duration)
        && row["total_length_ms"].as_i64() == Some(if state == 3 { 0 } else { duration })
        && (matches!(row.get("label"), Some(Value::Null)) || row["label"].as_str() == Some("")),
        "Clock timer identity, duration or label differs")?;
    let remaining = integer(&row["remaining_ms"], "Clock remaining time is not an integer")?;
    let start = integer(&row["last_start_ms"], "Clock monotonic start is not an integer")?;
    let wall = integer(&row["last_wall_ms"], "Clock wall start is not an integer")?;
    require(row["delete_after_use"] == false, "Clock timer auto-deletion changed")?;
    if state == 3 {
        require(remaining <= 0 && start > 0 && wall > 0, "Clock expiry state lacks actual expiry times")?;
    } else if state == 1 {
        require(remaining > 0 && remaining <= duration && start > 0 && wall > 0,
            "Clock running state lacks positive bounded time")?;
    } else {
        require(start == UNUSED && wall == UNUSED && remaining > 0 && remaining <= duration,
            "Clock paused/reset state lacks the exact unused-clock sentinel")?;
    }
    Ok(Timer { remaining, start })
}

#[derive(Debug, Serialize)]
struct CaseDetails {
    kind: Kind,
    owned_timer_id: i64,
    duration_ms: i64,
    native_launches: u64,
    normal_closes: u64,
    ui_actions: u64,
    natural_expiry_observed_uptime_ms: Option<i64>,
}

fn common_cleanup(result: &Value, kind: Kind) -> Result<(), String> {
    require(result["schema"] == RESULT_SCHEMA && result["kind"] == kind.name()
        && result["state"] == "ORIGINAL_CLOCK_SCOPE_VERIFIED_CLEAN",
        "Clock result is not the exact successful original case")?;
    for key in ["case_business_success_verified", "business_scope_completed", "task_set_restored",
        "protected_business_and_sound_state_preserved", "actual_Main_and_APIs_closed",
        "whole_case_OFD_closed", "source_and_receipt_witness_closed",
        "final_source_and_identity_chain_unchanged"] {
        require(result[key] == true, "Clock original business, source or cleanup chain did not complete")?;
    }
    for key in ["automatic_retry", "whole_app_business_accepted", "outcome_unknown",
        "host_cancellation_observed", "old_binary_or_epoch_business_credit_inherited",
        "automatic_rollback", "Binder_UID_cleanup_verified", "continuous_runtime_sampling_verified",
        "soak_or_stress_verified", "physical_audio_qualification", "desktop_popup_qualification"] {
        require(result[key] == false, "Clock result contains an unknown outcome or unsupported qualification")?;
    }
    require(result.get("error").is_none_or(Value::is_null)
        && result.get("entry_error").is_none()
        && empty_array(&result["secondary_errors"]) && empty_array(&result["received_signals"])
        && result["cancellation_commit"]["decision_frozen_after_context_exit"] == true
        && empty_array(&result["cancellation_commit"]["observed_before_commit"])
        && empty_array(&result["cancellation_commit"]["pending_at_commit"]),
        "Clock retained an error, signal or uncommitted cancellation")?;
    let pending = result["pending"].as_object().ok_or("Clock pending-action map missing")?;
    require(pending.keys().map(String::as_str).collect::<BTreeSet<_>>()
        == BTreeSet::from(["input", "effect", "close"])
        && pending.values().all(Value::is_null)
        && result.get("owned_task_remaining").is_some_and(Value::is_null),
        "Clock retains an input, effect, task or close obligation")?;
    require(same_objects(&result["identity_before"], &result["identity_after"])
        && same_objects(&result["guard_before"], &result["guard_after"])
        && nonempty_object(&result["actual_final_caller"])
        && result["alarms_before"].is_object() && result["alarms_before"] == result["alarms_after"]
        && result["templates_sha_before"].as_str().is_some_and(crate::release::valid_sha)
        && result["templates_sha_before"] == result["templates_sha_after"],
        "Clock identity, Main guard or preserved alarms changed")?;
    for key in ["SQL_write_commands", "provider_write_commands", "settings_writes",
        "permission_writes", "global_volume_or_ringtone_changes"] {
        require(result[key].as_u64() == Some(0), "Clock used a forbidden data/settings write")?;
    }
    let tasks = array(&result["owned_tasks"], "Clock owned-task list absent")?;
    require(tasks.len() == 2 && tasks.iter().all(|v| v.as_u64().is_some_and(|v| v > 0))
        && tasks[0] != tasks[1] && result["owned_tasks"] == result["closed_tasks"]
        && result["native_launch_calls"].as_u64() == Some(2)
        && result["normal_remove_calls"].as_u64() == Some(2)
        && result["ui_actions"].as_u64().is_some_and(|v| v <= kind.action_limit()),
        "Clock did not retire exactly its two ordinary launches within the original action limit")?;
    empty_timer(&result["timer_final"])?;
    empty_timer(&result["phases"]["before"])?;
    empty_timer(&result["phases"]["before-start"])
}

fn validate_case_details(result: &Value, kind: Kind) -> Result<CaseDetails, String> {
    common_cleanup(result, kind)?;
    let id = integer(&result["owned_timer_id"], "Clock owned timer ID missing")?;
    require(id >= 0, "Clock timer ID is outside the original source range")?;
    let phases = &result["phases"];
    let created = timer(&phases["created-running"], id, kind.duration(), 1)?;
    let expiry = match kind {
        Kind::Timer15 => {
            let paused = timer(&phases["paused"], id, kind.duration(), 2)?;
            require(paused.remaining < kind.duration()
                && phases["paused"] == phases["paused-stable"]
                && phases["paused"] == phases["after-normal-close"]
                && phases["paused"] == phases["after-reopen"],
                "Clock pause did not remain identical through ordinary close and reopen")?;
            let resumed = timer(&phases["resumed"], id, kind.duration(), 1)?;
            let later = timer(&phases["paused-after-resume"], id, kind.duration(), 2)?;
            require(resumed.start > created.start && resumed.remaining <= paused.remaining
                && later.remaining < paused.remaining,
                "Clock resume did not continue the same owned timer and decrease its remaining time")?;
            let reset = timer(&phases["reset"], id, kind.duration(), 4)?;
            require(reset.remaining == kind.duration(), "Clock reset did not restore the full duration")?;
            empty_timer(&phases["deleted"])?;
            None
        }
        Kind::Expiry06 => {
            let expired = timer(&phases["expired"], id, kind.duration(), 3)?;
            let reset = timer(&phases["stopped-reset"], id, kind.duration(), 4)?;
            require(reset.remaining == kind.duration(), "Clock expiry stop did not reset the same timer")?;
            empty_timer(&phases["final-deleted"])?;
            let timing = &result["expiry_timing"];
            let due = created.start.checked_add(created.remaining).ok_or("Clock due-time overflow")?;
            let observed = integer(&timing["observed_uptime_ms"], "Clock observed expiry uptime absent")?;
            let lower = due.checked_sub(1000).ok_or("Clock expiry lower bound overflow")?;
            let upper = due.checked_add(25_000).ok_or("Clock expiry upper bound overflow")?;
            require(timing["expected_due_ms"].as_i64() == Some(due)
                && timing["created_start_ms"].as_i64() == Some(created.start)
                && expired.start >= lower && expired.start <= observed.saturating_add(10)
                && observed >= lower && observed <= upper,
                "Clock expiry lacks the original natural-expiry monotonic-time bounds")?;
            let samples = array(&timing["samples"], "Clock expiry samples absent")?;
            require(!samples.is_empty() && samples.len() <= 240,
                "Clock natural-expiry sample set is empty or unbounded")?;
            let mut previous = created.start;
            for (index, sample) in samples.iter().enumerate() {
                let uptime = integer(&sample["uptime_ms"], "Clock sample uptime missing")?;
                let last = index + 1 == samples.len();
                require(uptime >= previous && uptime <= upper
                    && sample["state"].as_i64() == Some(if last { 3 } else { 1 })
                    && (!last || uptime == observed),
                    "Clock expiry samples are out of order or omit the actual transition")?;
                previous = uptime;
            }
            require(result["actual_expiry_verified"] == true
                && result["actual_expired_notification_posted"] == true
                && result["notify_monitor_closed_verified"] == true
                && result["stop_reconciliation"]["input_acknowledged"] == true
                && result["stop_reconciliation"]["same_id_reset_verified"] == true
                && result["stop_reconciliation"]["action_replayed"] == false,
                "Clock expiry, acknowledged stop or monitor completion missing")?;
            let notifications = &result["notifications"];
            require(empty_array(&notifications["before"]["records"]),
                "Clock expiry notification baseline was not empty")?;
            let active = array(&notifications["actual-expired"]["records"],
                "Clock active expiry notification missing")?;
            require(active.len() == 1 && active[0]["key"]
                    == "0|com.android.deskclock|2147483644|null|10063"
                && active[0]["uid"].as_u64() == Some(10063)
                && active[0]["android_user"].as_u64() == Some(0)
                && active[0]["timer_channel"] == true
                && active[0]["record_sha256"].as_str().is_some_and(crate::release::valid_sha),
                "Clock expiry notification is not the source-bound owned timer")?;
            let cleared = ["deleted", "deleted-readback-0", "deleted-readback-1"].into_iter()
                .filter_map(|key| notifications.get(key)).next_back()
                .ok_or("Clock final notification readback absent")?;
            require(empty_array(&cleared["records"]), "Clock expiry notification remains")?;
            let stop = &result["notify_watch_stop"];
            require(stop["child_joined"] == true && stop["reader_joined"] == true
                && stop["all_owned_monitor_writers_closed"] == true
                && stop["pipe_eof"] == serde_json::json!({"stdout":true,"stderr":true})
                && stop.get("cleanup_error").is_some_and(Value::is_null)
                && result["monitor_control_FD_closed"] == true,
                "Clock expiry monitor child, reader, writer or control FD was not retired")?;
            Some(observed)
        }
    };
    Ok(CaseDetails { kind, owned_timer_id:id, duration_ms:kind.duration(),
        native_launches:2, normal_closes:2, ui_actions:result["ui_actions"].as_u64().unwrap(),
        natural_expiry_observed_uptime_ms:expiry })
}

struct CaseInput {
    kind: Kind,
    request: FilePin,
    plan: FilePin,
    baseline: FilePin,
    qualification: FilePin,
    framework_epoch_sha256: String,
    support_manifest: FilePin,
    case_root: String,
}

fn case_input(held: &mut CaseInputs, request: &FilePin, kind: Kind,
    preparation: &FilePin) -> Result<CaseInput, String> {
    let value = read(held, request, 131_072)?;
    require(value.as_object().is_some_and(|v| v.len() == 1 && v.contains_key("plan")),
        "Clock pair accepts only the original single-plan request")?;
    let plan = reference(&value, "plan")?;
    let document = read(held, &plan, 131_072)?;
    require(document["schema"] == "pocket4-clock-current-execution-plan-v1"
        && document["kind"] == kind.name() && reference(&document, "source_preparation")? == *preparation
        && document["automatic_retry"] == false && document["whole_app_business_accepted"] == false,
        "Clock pair's original plan has the wrong kind, source or scope")?;
    let baseline = reference(&document, "baseline")?;
    let qualification = reference(&document, "qualification")?;
    let baseline_value = read(held, &baseline, super::INPUT_LIMIT)?;
    read(held, &qualification, super::INPUT_LIMIT)?;
    let epoch = document["framework_epoch_sha256"].as_str().ok_or("Clock source epoch absent")?;
    require(crate::release::valid_sha(epoch)
        && baseline_value["framework_epoch"]["sha256"] == epoch,
        "Clock original plan and held baseline have different epoch commitments")?;
    let case_root = document["case_root"].as_str().ok_or("Clock original case root absent")?.to_owned();
    Ok(CaseInput { kind, request:request.clone(), plan, baseline, qualification,
        framework_epoch_sha256:epoch.into(), support_manifest:reference(&document, "support_manifest")?,
        case_root })
}

fn same_pair_inputs(timer: &CaseInput, expiry: &CaseInput) -> Result<(), String> {
    require(timer.kind == Kind::Timer15 && expiry.kind == Kind::Expiry06
        && timer.request.path != expiry.request.path && timer.request.sha256 != expiry.request.sha256
        && timer.plan.path != expiry.plan.path && timer.case_root != expiry.case_root
        && timer.baseline == expiry.baseline && timer.qualification == expiry.qualification
        && timer.framework_epoch_sha256 == expiry.framework_epoch_sha256
        && timer.support_manifest == expiry.support_manifest,
        "Clock pair must contain two distinct fixed cases under the same held Main baseline")
}

fn hold_sources(held: &mut Inputs, preparation: &FilePin) -> Result<(), String> {
    let value = leaf_release::json(&held.read(&preparation.path, Some(preparation), 131_072, true, false)?)?;
    require(value["schema"] == "pocket4-final-clock-original-case-preparation-v1"
        && value["code_entrypoints_complete"] == true
        && value["Android_execution_authorized_by_publication"] == false,
        "Clock source preparation is not the original non-authorizing source packet")?;
    let rows = array(&value["files"], "Clock full source list absent")?;
    let mut names = BTreeSet::new();
    require(rows.len() == SOURCE_NAMES.len(), "Clock source closure is not the fixed 27-member graph")?;
    for row in rows {
        let reference = pin(row)?;
        let name = reference.path.file_name().and_then(|v| v.to_str())
            .ok_or("Clock source basename absent")?.to_owned();
        require(names.insert(name), "Clock source graph repeats a member")?;
        held.read(&reference.path, Some(&reference), 1024 * 1024, true, false)?;
    }
    require(names.iter().map(String::as_str).collect::<BTreeSet<_>>()
        == SOURCE_NAMES.into_iter().collect(),
        "Clock source graph differs from the fixed original dependency roster")
}

// These facts have no Clone/Deserialize and cannot be built by a receipt reader.
// The lifetime pins both cases to the same still-held normal source/owner lease.
struct CaseFact<'a> {
    lease: &'a NativeRelease,
    main: &'a HeldMainCustody,
    result_custody: ClockResultCustody,
    actual: ApplicationInspection,
    observation: LeafObservation,
    details: CaseDetails,
    baseline: FilePin,
    qualification: FilePin,
    framework_epoch_sha256: String,
}

fn case_fact<'a>(executed: ExecutedClockCase, lease: &'a NativeRelease,
    main: &'a HeldMainCustody, input: &CaseInput,
    actual: &ApplicationInspection) -> Result<CaseFact<'a>, String> {
    main.require_application(actual)?;
    let (observation, result_custody) = executed.into_parts();
    require(observation.result == result_custody.reference,
        "Clock executed result differs from its held file custody")?;
    let result = result_custody.read()?;
    require(observation.route == input.kind.route() && observation.request == input.request
        && reference(&result, "plan")? == input.plan
        && reference(&result, "source_preparation")? == observation.preparation
        && result["framework_epoch_sha256"] == input.framework_epoch_sha256
        && reference(&result, "support_manifest")? == input.support_manifest
        && result["identity_before"]["uid"].as_u64() == Some(u64::from(actual.uid))
        && result["identity_before"]["version"].as_u64() == Some(actual.version_code),
        "Clock execution token does not bind this original case, source and epoch")?;
    let details = validate_case_details(&result, input.kind)?;
    lease.guard()?;
    Ok(CaseFact { lease, main, result_custody, actual:actual.clone(), observation, details,
        baseline:input.baseline.clone(), qualification:input.qualification.clone(),
        framework_epoch_sha256:input.framework_epoch_sha256.clone() })
}

struct ClockPairCustody {
    lease: NativeRelease,
    timer15: ClockResultCustody,
    expiry06: ClockResultCustody,
}
impl std::fmt::Debug for ClockPairCustody {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("ClockPairCustody").finish_non_exhaustive()
    }
}
impl ClockPairCustody {
    fn guard(&self) -> Result<(), String> {
        self.lease.guard()?;
        self.timer15.guard()?;
        self.expiry06.guard()
    }
}

/// Output-only completed facts. No deserializer, clone, public fields or
/// receipt constructor can mint this scoped gate or its opaque Main custody.
#[derive(Debug, Serialize)]
pub(super) struct ClockTimerEvidence {
    schema: &'static str,
    pair_request: FilePin,
    native_release: FilePin,
    original_owner_current: FilePin,
    original_owner_current_f9: [u64; 9],
    selection: FilePin,
    #[serde(skip_serializing_if = "Option::is_none")]
    identity: Option<IdentityObservation>,
    main_custody: HeldMainCustody,
    #[serde(skip)]
    custody: ClockPairCustody,
    timer15: LeafObservation,
    expiry06: LeafObservation,
    timer15_details: CaseDetails,
    expiry06_details: CaseDetails,
    timer15_result_f9: [u64; 9],
    expiry06_result_f9: [u64; 9],
    same_normal_peer_source_owner_and_epoch: bool,
    original_host_process_trees_retired: bool,
    original_source_and_owner_bookends_verified: bool,
    remaining_common_requirements: [&'static str; 2],
    clock_timer_gate_passed: bool,
    application_accepted: bool,
    runtime_qualified: bool,
    production_ready: bool,
    automatic_retry: bool,
}

impl ClockTimerEvidence {
    pub(super) fn take_final_identity(&mut self) -> Result<IdentityObservation, String> {
        self.retained_bookends()?;
        self.identity.take().ok_or("Clock pair final identity already consumed".into())
    }
    pub(super) fn retained_bookends(&self) -> Result<(), String> {
        self.main_custody.guard_projection()?;
        self.custody.guard()
    }
    pub(super) fn verified_business_gates(&self) -> &'static [&'static str] {
        if self.clock_timer_gate_passed { &["clock.timer"] } else { &[] }
    }
    pub(super) fn evidence_pin(&self) -> &FilePin { &self.timer15.result }
    pub(super) fn main_observation(&self) -> &control::MainCustodyObservation {
        self.main_custody.normal_observation()
    }
}

fn inspect(inspector: &mut control::NativeApplicationInspector,
    expected: &ApplicationInspection) -> Result<ApplicationInspection, String> {
    let reply = inspector.inspect(PACKAGE, 0).map_err(|e| e.to_string())?;
    let (actual, _) = consume_inspection(reply, PACKAGE, 0)?;
    require(&actual == expected,
        "Clock normal peer observed a different package, UID, version, complete APK set or Main epoch")?;
    Ok(actual)
}

fn window(end: Instant, seconds: u64) -> Result<(), String> {
    require(end.checked_duration_since(Instant::now())
        .is_some_and(|left| left >= Duration::from_secs(seconds)),
        "Clock pair's existing bounded work/retirement window is exhausted")
}

pub(super) fn observe_pair(
    inspector: &mut control::NativeApplicationInspector,
    materials: &VerifiedMaterialBatch,
    runtime: &RuntimePlan,
    requested: &ApplicationPlan,
    expected: &ApplicationInspection,
    leaf: &LeafPlan,
    selection: &FilePin,
) -> Result<(ApplicationInspection, ClockTimerEvidence), String> {
    require(leaf.route == Route::ClockTimerPair && leaf.output.is_none()
        && requested.package == PACKAGE && expected.package == PACKAGE
        && runtime.android_user == 0 && expected.user == 0
        && expected.epoch == runtime.expected_epoch,
        "Clock pair is limited to the two explicit original user-zero cases")?;
    let mut held = CaseInputs::new();
    let request: PairRequest = serde_json::from_value(read(&mut held, &leaf.request, 131_072)?)
        .map_err(|e| e.to_string())?;
    require(request.schema == REQUEST_SCHEMA, "Clock pair request schema differs")?;
    let (lease, preparation, _) = leaf_routes::clock_pair_release(selection)?;
    lease.cover_window(PAIR_WINDOW_SECONDS)?;
    let end = Instant::now() + Duration::from_secs(PAIR_WINDOW_SECONDS);
    let current_path = Path::new(leaf_release::CURRENT);
    let current_raw = held.read(current_path, None, 2 * 1024 * 1024)?;
    let current_value = leaf_release::json(&current_raw)?;
    let current = FilePin { path:current_path.into(), bytes:current_raw.len() as u64,
        sha256:hex::encode(Sha256::digest(&current_raw)) };
    let current_f9 = held.identity(current_path)?;
    let native_release = reference(&current_value, "native_application_leaf_release")?;
    hold_sources(&mut held.sources, &preparation)?;
    let timer = case_input(&mut held, &request.timer15, Kind::Timer15, &preparation)?;
    let expiry = case_input(&mut held, &request.expiry06, Kind::Expiry06, &preparation)?;
    same_pair_inputs(&timer, &expiry)?;
    require(timer.qualification == runtime.main_qualification,
        "Clock pair differs from this runtime plan's recorded Main prerequisite")?;
    materials.revalidate()?;
    held.guard()?;
    lease.guard()?;
    window(end, 3 * 250 + 2 * 510 + 3 * 70 + 30)?;
    let before = inspect(inspector, expected)?;
    materials.observe(requested, 0, &runtime.expected_epoch, &before, &before)?;

    window(end, 2 * 250 + 2 * 510 + 3 * 70 + 30)?;
    let main = HeldMainCustody::observe(inspector, &before)?;
    lease.guard()?;

    let timer_plan = LeafPlan { route:Kind::Timer15.route(), request:timer.request.clone(), output:None };
    window(end, 2 * 510 + 2 * 250 + 2 * 70 + 30)?;
    let timer_executed = leaf_routes::execute_clock_case(&timer_plan, selection, &before, &main, &lease)?;
    let timer_fact = case_fact(timer_executed, &lease, &main, &timer, &before)?;
    held.guard()?; materials.revalidate()?; lease.guard()?;
    window(end, 2 * 250 + 510 + 2 * 70 + 30)?;
    let between = inspect(inspector, &before)?;
    materials.observe(requested, 0, &runtime.expected_epoch, &before, &between)?;
    window(end, 250 + 510 + 2 * 70 + 30)?;
    main.revalidate(inspector, &between)?;

    let expiry_plan = LeafPlan { route:Kind::Expiry06.route(), request:expiry.request.clone(), output:None };
    window(end, 510 + 250 + 70 + 30)?;
    timer_fact.result_custody.guard()?;
    let expiry_executed = leaf_routes::execute_clock_case(&expiry_plan, selection, &between, &main, &lease)?;
    let expiry_fact = case_fact(expiry_executed, &lease, &main, &expiry, &between)?;
    held.guard()?; materials.revalidate()?; lease.guard()?;
    window(end, 250 + 70 + 30)?;
    let after = inspect(inspector, &before)?;
    let identity = materials.observe(requested, 0, &runtime.expected_epoch, &before, &after)?;
    window(end, 70 + 30)?;
    main.revalidate(inspector, &after)?;
    held.guard()?; materials.revalidate()?; lease.guard()?;
    window(end, 0)?;
    timer_fact.result_custody.guard()?;
    expiry_fact.result_custody.guard()?;
    require(std::ptr::eq(timer_fact.lease, expiry_fact.lease)
        && std::ptr::eq(timer_fact.main, expiry_fact.main)
        && timer_fact.actual == expiry_fact.actual
        && timer_fact.baseline == expiry_fact.baseline
        && timer_fact.qualification == expiry_fact.qualification
        && timer_fact.framework_epoch_sha256 == expiry_fact.framework_epoch_sha256
        && timer_fact.observation.preparation == expiry_fact.observation.preparation
        && timer_fact.observation.entry_source == expiry_fact.observation.entry_source
        && timer_fact.observation.result.path != expiry_fact.observation.result.path,
        "Clock observations cannot be joined across source, owner, identity or epoch")?;
    let timer15_result_f9 = timer_fact.result_custody.identity()?;
    let expiry06_result_f9 = expiry_fact.result_custody.identity()?;
    let CaseFact { result_custody:timer_result, observation:timer15,
        details:timer15_details, .. } = timer_fact;
    let CaseFact { result_custody:expiry_result, observation:expiry06,
        details:expiry06_details, .. } = expiry_fact;
    let evidence = ClockTimerEvidence {
        schema:"droidloom.clock-timer-pair-observation.v2", pair_request:leaf.request.clone(),
        native_release, original_owner_current:current, original_owner_current_f9:current_f9,
        selection:selection.clone(), identity:Some(identity), main_custody:main,
        custody:ClockPairCustody { lease, timer15:timer_result, expiry06:expiry_result },
        timer15, expiry06, timer15_details, expiry06_details,
        timer15_result_f9, expiry06_result_f9,
        same_normal_peer_source_owner_and_epoch:true, original_host_process_trees_retired:true,
        original_source_and_owner_bookends_verified:true,
        remaining_common_requirements:["actual_per_application_engine_mapping", "other_registry_gates"],
        clock_timer_gate_passed:true, application_accepted:false,
        runtime_qualified:false, production_ready:false, automatic_retry:false,
    };
    evidence.retained_bookends()?;
    Ok((after, evidence))
}


#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    // Synthetic parser models only. These helpers cannot create an
    // ExecutedClockCase, NativeRelease, normal peer or ClockTimerEvidence.
    fn empty() -> Value { json!({"ids":[],"timers":[],"values":{},"stopwatch":{}}) }
    fn snapshot(kind: Kind, state: i64, remaining: i64, start: i64) -> Value {
        json!({"ids":[7],"timers":[{"id":7,"state":state,"length_ms":kind.duration(),
            "total_length_ms":if state == 3 {0} else {kind.duration()},
            "remaining_ms":remaining,"last_start_ms":start,
            "last_wall_ms":if state == 1 || state == 3 {1_700_000_000_000_i64} else {UNUSED},
            "label":null,"delete_after_use":false}],"values":{},"stopwatch":{}})
    }
    fn model(kind: Kind) -> Value {
        let duration = kind.duration();
        let mut value = json!({
            "schema":RESULT_SCHEMA,"kind":kind.name(),"state":"ORIGINAL_CLOCK_SCOPE_VERIFIED_CLEAN",
            "case_business_success_verified":true,"business_scope_completed":true,
            "task_set_restored":true,"protected_business_and_sound_state_preserved":true,
            "actual_Main_and_APIs_closed":true,"whole_case_OFD_closed":true,
            "source_and_receipt_witness_closed":true,"final_source_and_identity_chain_unchanged":true,
            "automatic_retry":false,"whole_app_business_accepted":false,"outcome_unknown":false,
            "host_cancellation_observed":false,"old_binary_or_epoch_business_credit_inherited":false,
            "automatic_rollback":false,"Binder_UID_cleanup_verified":false
        });
        value.as_object_mut().unwrap().extend(json!({
            "continuous_runtime_sampling_verified":false,"soak_or_stress_verified":false,
            "physical_audio_qualification":false,"desktop_popup_qualification":false,
            "secondary_errors":[],"received_signals":[],"cancellation_commit":{
                "decision_frozen_after_context_exit":true,"observed_before_commit":[],"pending_at_commit":[]},
            "pending":{"input":null,"effect":null,"close":null},"owned_task_remaining":null,
            "identity_before":{"uid":10063,"version":37},"identity_after":{"uid":10063,"version":37},
            "guard_before":{"source":"synthetic-test"},"guard_after":{"source":"synthetic-test"},
            "actual_final_caller":{"pid":99},"alarms_before":{"ids":[]},"alarms_after":{"ids":[]},
            "templates_sha_before":"a".repeat(64),"templates_sha_after":"a".repeat(64)
        }).as_object().unwrap().clone());
        value.as_object_mut().unwrap().extend(json!({
            "SQL_write_commands":0,"provider_write_commands":0,"settings_writes":0,
            "permission_writes":0,"global_volume_or_ringtone_changes":0,
            "owned_tasks":[11,12],"closed_tasks":[11,12],"native_launch_calls":2,
            "normal_remove_calls":2,"ui_actions":10,"owned_timer_id":7,"timer_final":empty(),
            "phases":{"before":empty(),"before-start":empty(),
                "created-running":snapshot(kind,1,duration,100_000)}
        }).as_object().unwrap().clone());
        if kind == Kind::Timer15 {
            for name in ["paused","paused-stable","after-normal-close","after-reopen"] {
                value["phases"][name] = snapshot(kind,2,duration-1000,UNUSED);
            }
            value["phases"]["resumed"] = snapshot(kind,1,duration-1000,110_000);
            value["phases"]["paused-after-resume"] = snapshot(kind,2,duration-2000,UNUSED);
            value["phases"]["reset"] = snapshot(kind,4,duration,UNUSED);
            value["phases"]["deleted"] = empty();
        } else {
            value["phases"]["expired"] = snapshot(kind,3,0,160_000);
            value["phases"]["stopped-reset"] = snapshot(kind,4,duration,UNUSED);
            value["phases"]["final-deleted"] = empty();
            value["expiry_timing"] = json!({"expected_due_ms":160_000,"created_start_ms":100_000,
                "observed_uptime_ms":160_300,"samples":[{"uptime_ms":159_000,"state":1},
                    {"uptime_ms":160_300,"state":3}]});
            value["actual_expiry_verified"] = json!(true);
            value["actual_expired_notification_posted"] = json!(true);
            value["notify_monitor_closed_verified"] = json!(true);
            value["stop_reconciliation"] = json!({"input_acknowledged":true,
                "same_id_reset_verified":true,"action_replayed":false});
            value["notifications"] = json!({"before":{"records":[]},"actual-expired":{"records":[{
                "key":"0|com.android.deskclock|2147483644|null|10063","uid":10063,"android_user":0,
                "timer_channel":true,"record_sha256":"b".repeat(64)}]},"deleted":{"records":[]}});
            value["notify_watch_stop"] = json!({"child_joined":true,"reader_joined":true,
                "all_owned_monitor_writers_closed":true,"pipe_eof":{"stdout":true,"stderr":true},
                "cleanup_error":null});
            value["monitor_control_FD_closed"] = json!(true);
        }
        value
    }
    fn test_pin(name: &str) -> FilePin {
        FilePin { path:format!("/synthetic/{name}").into(),bytes:1,
            sha256:hex::encode(Sha256::digest(name.as_bytes())) }
    }
    fn input(kind: Kind) -> CaseInput {
        CaseInput { kind, request:test_pin(kind.name()),plan:test_pin(&format!("{}.plan",kind.name())),
            baseline:test_pin("baseline"),qualification:test_pin("qualification"),
            framework_epoch_sha256:"e".repeat(64),support_manifest:test_pin("support"),
            case_root:format!("/synthetic/{}",kind.name()) }
    }

    #[test]
    fn complete_source_models_parse_without_creating_runtime_authority() {
        for kind in [Kind::Timer15, Kind::Expiry06] {
            let details = validate_case_details(&model(kind),kind).unwrap();
            assert_eq!(details.duration_ms,kind.duration());
            assert_eq!(details.natural_expiry_observed_uptime_ms.is_some(),kind == Kind::Expiry06);
        }
        let mut value=model(Kind::Timer15);
        value["phases"]["created-running"]["timers"][0]["label"]=json!("");
        assert!(validate_case_details(&value,Kind::Timer15).is_ok());
    }

    #[test]
    fn reported_success_without_owned_timer_phases_is_not_a_fact() {
        let mut value=model(Kind::Timer15);
        value["phases"]=json!({});
        assert!(validate_case_details(&value,Kind::Timer15).is_err());
        let mut value=model(Kind::Expiry06);
        value["expiry_timing"]=json!({});
        assert!(validate_case_details(&value,Kind::Expiry06).is_err());
    }

    #[test]
    fn pause_reopen_resume_and_reset_are_independent_required_observations() {
        for (pointer, replacement) in [
            ("/phases/paused-stable/timers/0/remaining_ms",900_000),
            ("/phases/after-normal-close/timers/0/remaining_ms",900_000),
            ("/phases/after-reopen/timers/0/remaining_ms",900_000),
            ("/phases/resumed/timers/0/last_start_ms",100_000),
            ("/phases/paused-after-resume/timers/0/remaining_ms",900_000),
            ("/phases/reset/timers/0/remaining_ms",899_999)] {
            let mut value=model(Kind::Timer15);
            *value.pointer_mut(pointer).unwrap()=json!(replacement);
            assert!(validate_case_details(&value,Kind::Timer15).is_err(),"{pointer}");
        }
    }

    #[test]
    fn another_timer_or_non_source_numeric_form_is_rejected() {
        for replacement in [json!(8),json!(true),json!("7"),json!(7.0)] {
            let mut value=model(Kind::Timer15);
            value["phases"]["resumed"]["timers"][0]["id"]=replacement;
            assert!(validate_case_details(&value,Kind::Timer15).is_err());
        }
        let mut value=model(Kind::Timer15);
        value["phases"]["paused"]["timers"][0]["last_start_ms"]=json!(-1);
        assert!(validate_case_details(&value,Kind::Timer15).is_err());
    }

    #[test]
    fn expiry_requires_natural_due_window_order_and_same_timer_stop() {
        for (pointer,replacement) in [
            ("/expiry_timing/observed_uptime_ms",json!(190_000)),
            ("/expiry_timing/expected_due_ms",json!(160_001)),
            ("/expiry_timing/samples/0/state",json!(3)),
            ("/expiry_timing/samples/1/uptime_ms",json!(160_301)),
            ("/phases/expired/timers/0/total_length_ms",json!(60_000)),
            ("/phases/stopped-reset/timers/0/id",json!(8)),
            ("/stop_reconciliation/action_replayed",json!(true))] {
            let mut value=model(Kind::Expiry06);
            *value.pointer_mut(pointer).unwrap()=replacement;
            assert!(validate_case_details(&value,Kind::Expiry06).is_err(),"{pointer}");
        }
    }

    #[test]
    fn notification_identity_clear_and_every_monitor_retirement_are_required() {
        for (pointer,replacement) in [
            ("/notifications/actual-expired/records/0/uid",json!(10064)),
            ("/notifications/actual-expired/records/0/timer_channel",json!(false)),
            ("/notifications/deleted/records",json!([{}])),
            ("/notify_watch_stop/child_joined",json!(false)),
            ("/notify_watch_stop/reader_joined",json!(false)),
            ("/notify_watch_stop/all_owned_monitor_writers_closed",json!(false)),
            ("/notify_watch_stop/pipe_eof/stderr",json!(false)),
            ("/notify_watch_stop/cleanup_error",json!("unproven")),
            ("/monitor_control_FD_closed",json!(false))] {
            let mut value=model(Kind::Expiry06);
            *value.pointer_mut(pointer).unwrap()=replacement;
            assert!(validate_case_details(&value,Kind::Expiry06).is_err(),"{pointer}");
        }
    }

    #[test]
    fn cancellation_unknown_outcome_and_cleanup_debt_never_become_facts() {
        for (pointer,replacement) in [
            ("/pending/effect",json!({"unconfirmed":true})),
            ("/owned_task_remaining",json!(11)),
            ("/secondary_errors",json!([{"retirement":"unproven"}])),
            ("/received_signals",json!([15])),
            ("/cancellation_commit/pending_at_commit",json!([2])),
            ("/source_and_receipt_witness_closed",json!(false)),
            ("/actual_Main_and_APIs_closed",json!(false)),
            ("/outcome_unknown",json!(true)),
            ("/identity_after/uid",json!(10064)),
            ("/normal_remove_calls",json!(1)),
            ("/closed_tasks",json!([11,13])),
            ("/settings_writes",json!(1))] {
            let mut value=model(Kind::Timer15);
            *value.pointer_mut(pointer).unwrap()=replacement;
            assert!(validate_case_details(&value,Kind::Timer15).is_err(),"{pointer}");
        }
    }

    #[test]
    fn pair_cannot_join_duplicate_kind_or_another_source_epoch_or_main_receipt() {
        assert!(same_pair_inputs(&input(Kind::Timer15),&input(Kind::Expiry06)).is_ok());
        assert!(same_pair_inputs(&input(Kind::Timer15),&input(Kind::Timer15)).is_err());
        for change in 0..6 {
            let timer=input(Kind::Timer15);
            let mut expiry=input(Kind::Expiry06);
            match change {
                0=>expiry.baseline=test_pin("different-baseline"),
                1=>expiry.qualification=test_pin("different-qualification"),
                2=>expiry.framework_epoch_sha256="f".repeat(64),
                3=>expiry.support_manifest=test_pin("different-source"),
                4=>expiry.request=timer.request.clone(),
                _=>expiry.case_root=timer.case_root.clone(),
            }
            assert!(same_pair_inputs(&timer,&expiry).is_err());
        }
    }

    #[test]
    fn pair_request_has_no_caller_success_receipt_command_or_limit_interface() {
        let good=serde_json::json!({"schema":REQUEST_SCHEMA,
            "timer15":test_pin("timer15"),"expiry06":test_pin("expiry06")});
        assert!(serde_json::from_value::<PairRequest>(good.clone()).is_ok());
        for key in ["accepted","main_qualified","result","pid","argv","deadline","limits","owner"] {
            let mut bad=good.clone();bad[key]=json!(true);
            assert!(serde_json::from_value::<PairRequest>(bad).is_err(),"{key}");
        }
    }

    #[test]
    fn actual_case_children_may_be_created_but_input_inode_and_body_cannot_change() {
        let root=tempfile::tempdir_in(env!("CARGO_MANIFEST_DIR")).unwrap();
        let path=root.path().join("plan.json");
        fs::write(&path,b"{\"fixed\":true}\n").unwrap();
        let mut held=CaseInputs::new();
        held.read(&path,None,1024).unwrap();
        fs::create_dir(root.path().join("protection")).unwrap();
        fs::create_dir(root.path().join("commands")).unwrap();
        held.guard().unwrap();
        fs::write(&path,b"{\"fixed\":false}\n").unwrap();
        assert!(held.guard().is_err());
    }

    #[test]
    fn same_bytes_at_replaced_case_parent_or_file_are_rejected() {
        for replace_parent in [false,true] {
            let root=tempfile::tempdir_in(env!("CARGO_MANIFEST_DIR")).unwrap();
            let parent=root.path().join("case");
            fs::create_dir(&parent).unwrap();
            let path=parent.join("plan.json");
            fs::write(&path,b"{}\n").unwrap();
            let mut held=CaseInputs::new();
            held.read(&path,None,1024).unwrap();
            if replace_parent {
                fs::rename(&parent,root.path().join("old")).unwrap();
                fs::create_dir(&parent).unwrap();
            } else {
                fs::rename(&path,parent.join("old.json")).unwrap();
            }
            fs::write(&path,b"{}\n").unwrap();
            assert!(held.guard().is_err());
        }
    }


    #[test]
    fn execution_result_handoff_keeps_original_fd_and_rejects_same_byte_replacement() {
        let root=tempfile::tempdir_in(env!("CARGO_MANIFEST_DIR")).unwrap();
        let path=root.path().join("result.json");
        let raw=b"{\"synthetic_parser_model\":true}\n";
        fs::write(&path,raw).unwrap();
        let reference=FilePin {path:path.clone(),bytes:raw.len() as u64,
            sha256:hex::encode(Sha256::digest(raw))};
        let (custody,parsed)=ClockResultCustody::capture(&reference).unwrap();
        let (discovered,from_path)=ClockResultCustody::capture_path(&path).unwrap();
        assert_eq!(discovered.reference(), &reference);
        assert_eq!(from_path, parsed);
        assert_eq!(custody.read().unwrap(),parsed);
        assert_eq!(discovered.read().unwrap(),parsed);
        fs::rename(&path,root.path().join("original-result.json")).unwrap();
        fs::write(&path,raw).unwrap();
        // The pin and bytes still match. Only the retained descriptor/inode
        // distinguishes the executed result from a replacement at handoff.
        assert_eq!(super::super::pinned(&reference).unwrap(),raw);
        assert!(custody.read().is_err());
        assert!(custody.guard().is_err());
        assert!(discovered.read().is_err());
        assert!(discovered.guard().is_err());
    }

}
