//! Independent fixed H2 return entry. A real retired parent and normal
//! protected capture are consumed without recreating live execution authority.
use super::{
    boot::BootOwner,
    watchdog::{ArmedWatchdog, monotonic_ns},
};
use crate::control::application_command::application_leaf_unit::qualification::retirement::capabilities as caps;
use crate::control::application_command::application_leaf_unit::qualification::retirement::{
    MaintenanceOperation, RetiredWorkingParent,
};
use crate::{native_hardware_label as held, native_working_contract as c};
use c::layout;
use serde_json::{Value, json};
use std::{
    ffi::OsString,
    io, thread,
    time::{Duration, Instant},
};
#[path = "working_qualification_return_files.rs"]
mod files;
use files::{Evidence, ProtectedRun, Record};

fn denied(s: &str) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, s)
}
fn checked<T>(value: Result<T, String>) -> io::Result<T> {
    value.map_err(|e| denied(&e))
}
fn guard(
    boot: &BootOwner,
    parent: &RetiredWorkingParent,
    watchdog: &ArmedWatchdog,
    evidence: &Evidence,
    capture: Option<&ProtectedRun>,
) -> io::Result<()> {
    checked(parent.guard(boot))?;
    watchdog.guard()?;
    evidence.guard()?;
    if let Some(capture) = capture {
        capture.guard()?;
    }
    Ok(())
}
fn command(
    boot: &BootOwner,
    parent: &RetiredWorkingParent,
    watchdog: &ArmedWatchdog,
    evidence: &Evidence,
    capture: Option<&ProtectedRun>,
    operation: MaintenanceOperation,
) -> io::Result<Value> {
    guard(boot, parent, watchdog, evidence, capture)?;
    let outputs = evidence.command_outputs(operation)?;
    evidence.record(Record::CommandIntent(operation),json!({
        "schema":"droidloom.working-return-maintenance-command.v1","candidate_id":boot.config().candidate_id,
        "intent_sha256":boot.config().intent_sha256,"boot_id":boot.boot_id(),"operation":operation.name(),
        "started_monotonic_ns":monotonic_ns()?,"original_return_end_monotonic_ns":checked(parent.normal_return_end_ns())?,
        "operation_cap_seconds":operation.seconds(),"completed":false,
        "working_capture_authenticated":capture.is_some(),"production_ready":false}),parent.deadline())?;
    let start = Instant::now();
    let mut actual =
        checked(parent.spawn_maintenance(boot, operation, &outputs.stdout, &outputs.stderr))?;
    let status = loop {
        evidence.output_bounds(&outputs)?;
        match checked(actual.poll(boot))? {
            Some(status) => break status,
            None => {
                watchdog.guard()?;
                evidence.guard()?;
                if let Some(capture) = capture {
                    capture.guard()?;
                }
                if Instant::now() >= actual.deadline() {
                    return Err(denied("actual normal maintenance operation timed out"));
                }
                thread::sleep(Duration::from_millis(50));
            }
        }
    };
    let (pins, raw) = evidence.seal_outputs(outputs, parent.deadline())?;
    evidence.record(Record::CommandResult(operation),json!({
        "schema":"droidloom.working-return-maintenance-command.v1","candidate_id":boot.config().candidate_id,
        "intent_sha256":boot.config().intent_sha256,"boot_id":boot.boot_id(),"operation":operation.name(),
        "exit_code":status.code(),"elapsed_seconds":start.elapsed().as_secs_f64(),"completed":true,
        "direct_child_reaped":true,"actual_child_pidfd_retired":true,"actual_service_descendants_absent":true,
        "outputs":pins,"production_ready":false}),parent.deadline())?;
    if !status.success() {
        return Err(denied("actual normal maintenance returned failure"));
    }
    guard(boot, parent, watchdog, evidence, capture)?;
    serde_json::from_slice(&raw).map_err(io::Error::other)
}
fn normal_collection(v: &Value, boot: &str) -> bool {
    let status = |v: &Value| {
        v["boot_id"] == boot
            && v["kernel"] == c::KERNEL
            && v["selinux_enforcing"] == true
            && v["selinux_context"] == "u:system_r:p4_linux_maintenance_t:s0"
            && v["system_units"]["exit"] == 0
            && v["user_units"]["exit"] == 0
            && v["system_units"]["observation_failed"] != true
            && v["user_units"]["observation_failed"] != true
    };
    v["schema"] == "droidloom-maintenance-evidence-v1"
        && v["same_boot"] == true
        && v["journal_exit"] == 0
        && v["journal"].is_array()
        && status(v)
        && status(&v["status_after"])
}
fn original_selected(v: &Value) -> bool {
    v["schema"] == "droidloom-maintenance-rollback-v1"
        && v["original_entry"] == c::ORIGINAL_ENTRY
        && v["reboot_requested"] == false
}
fn original_requested(v: &Value) -> bool {
    v["schema"] == "droidloom-maintenance-reboot-v1"
        && v["requested"] == true
        && v["target"] == c::ORIGINAL_ENTRY
        && v["completed"] == false
}
pub(crate) fn dispatch(args: &[OsString]) -> io::Result<bool> {
    let requested = args.first().is_some_and(|v| v == c::RETURN_MODE);
    let own = held::current(101)
        .as_ref()
        .is_ok_and(|v| v == layout::WORKING_RETURN_ROLE);
    if !requested && !own {
        return Ok(false);
    }
    if !requested
        || !own
        || args.len() != 1
        || held::current(104)? != layout::WORKING_RETURN_PROFILE
        || ["LD_PRELOAD", "LD_AUDIT", "LD_LIBRARY_PATH"]
            .iter()
            .any(|name| std::env::var_os(name).is_some())
    {
        return Err(denied(
            "working return requires its one fixed mode, normal ELF and independent MAC entries",
        ));
    }
    // Admission consumes a prefix of the same actual return interval. It
    // cannot refresh the original parent-exit based 180-second end.
    let admission_end = Instant::now() + Duration::from_secs(30);
    caps::seal()?;
    let boot = BootOwner::for_return()?;
    let watchdog = ArmedWatchdog::observe()?;
    let parent = checked(RetiredWorkingParent::observe(&boot, admission_end))?;
    let evidence = Evidence::create(&boot)?;
    guard(&boot, &parent, &watchdog, &evidence, None)?;
    evidence.record(Record::CandidateObserved,json!({
        "schema":"droidloom.working-return-candidate-observed.v1","candidate_id":boot.config().candidate_id,
        "intent_sha256":boot.config().intent_sha256,"first_once_candidate":boot.config().first_once_candidate,
        "boot_id":boot.boot_id(),"original_boot_id":boot.config().original_boot_id,
        "original_kernel":c::ORIGINAL_KERNEL,"candidate_kernel":c::KERNEL,
        "host_source_commit":boot.config().host_source_commit,"host_source_tree":boot.config().host_source_tree,
        "admitted_materials_sha256":boot.config().admitted_materials_sha256,
        "parent_retirement":parent.observation(),"watchdog_observed_active_nowayout":true,
        "watchdog_driver_opened_by_return":false,"watchdog_fed_by_return":false,
        "original_return_observed":false,"production_ready":false}),parent.deadline())?;
    let capture = match ProtectedRun::observe(&boot, &parent) {
        Ok(capture) => {
            evidence.record(
                Record::CaptureObserved,
                capture.observation()?,
                parent.deadline(),
            )?;
            Some(capture)
        }
        Err(error) => {
            // A missing/incomplete capture is a failed qualification, but the
            // independently admitted normal recovery still returns this boot.
            // It never becomes a successful capture or permanent activation.
            let reason = error.to_string().chars().take(4096).collect::<String>();
            evidence.record(Record::CaptureRejected,json!({
                "schema":"droidloom.working-return-capture-rejected.v1","candidate_id":boot.config().candidate_id,
                "intent_sha256":boot.config().intent_sha256,"boot_id":boot.boot_id(),"reason":reason,
                "working_capture_authenticated":false,"runtime_qualified":false,"production_ready":false
            }),parent.deadline())?;
            None
        }
    };
    let collected = command(
        &boot,
        &parent,
        &watchdog,
        &evidence,
        capture.as_ref(),
        MaintenanceOperation::Collect,
    )?;
    let complete_collection = normal_collection(&collected, boot.boot_id());
    evidence.record(Record::CollectionObserved,json!({
        "schema":"droidloom.working-return-collection-observed.v1","candidate_id":boot.config().candidate_id,
        "intent_sha256":boot.config().intent_sha256,"boot_id":boot.boot_id(),
        "normal_maintenance_collection_complete":complete_collection,
        "working_capture_authenticated":capture.is_some(),"original_return_observed":false,"production_ready":false
    }),parent.deadline())?;
    let selected = command(
        &boot,
        &parent,
        &watchdog,
        &evidence,
        capture.as_ref(),
        MaintenanceOperation::Rollback,
    )?;
    if !original_selected(&selected) {
        return Err(denied(
            "normal maintenance did not read back the original entry",
        ));
    }
    evidence.record(Record::ReturnSelected,json!({
        "schema":"droidloom.working-return-selected.v1","candidate_id":boot.config().candidate_id,
        "intent_sha256":boot.config().intent_sha256,"boot_id":boot.boot_id(),
        "normal_maintenance_collection_complete":complete_collection,
        "working_capture_authenticated":capture.is_some(),"maintenance":selected,
        "original_return_observed":false,"production_ready":false
    }),parent.deadline())?;
    let requested = command(
        &boot,
        &parent,
        &watchdog,
        &evidence,
        capture.as_ref(),
        MaintenanceOperation::Reboot,
    )?;
    if !original_requested(&requested) {
        return Err(denied(
            "normal maintenance did not accept the fixed original return request",
        ));
    }
    evidence.record(Record::ReturnRequested,json!({
        "schema":"droidloom.working-return-requested.v1","candidate_id":boot.config().candidate_id,
        "intent_sha256":boot.config().intent_sha256,"boot_id":boot.boot_id(),"original_boot_id":boot.config().original_boot_id,
        "normal_maintenance_collection_complete":complete_collection,
        "working_capture_authenticated":capture.is_some(),"maintenance":requested,
        "parent_retirement":parent.observation(),
        "actual_original_kernel_and_new_boot_still_required":true,"actual_private_working_copy_return_still_required":true,
        "original_return_observed":false,"production_ready":false
    }),parent.deadline())?;
    guard(&boot, &parent, &watchdog, &evidence, capture.as_ref())?;
    Ok(true)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn working_return_other_role_cannot_select_entry_or_caller_configuration() {
        assert!(dispatch(&[c::RETURN_MODE.into()]).is_err());
        assert!(dispatch(&[c::RETURN_MODE.into(), "/tmp/config.json".into()]).is_err());
    }
    #[test]
    fn working_return_requires_the_actual_fixed_normal_maintenance_protocol() {
        let selected = json!({"schema":"droidloom-maintenance-rollback-v1","original_entry":c::ORIGINAL_ENTRY,"reboot_requested":false});
        assert!(original_selected(&selected));
        assert!(!original_selected(
            &json!({"next_entry":c::ORIGINAL_ENTRY,"passed":true})
        ));
        let mut requested = json!({"schema":"droidloom-maintenance-reboot-v1","requested":true,"target":c::ORIGINAL_ENTRY,"completed":false});
        assert!(original_requested(&requested));
        requested["completed"] = true.into();
        assert!(!original_requested(&requested));
    }
    #[test]
    fn working_return_incomplete_collection_and_another_boot_are_rejected() {
        let boot = "11111111-1111-1111-1111-111111111111";
        let status = json!({"boot_id":boot,"kernel":c::KERNEL,"selinux_enforcing":true,
            "selinux_context":"u:system_r:p4_linux_maintenance_t:s0","system_units":{"exit":0},"user_units":{"exit":0}});
        let mut v = status.clone();
        v["schema"] = "droidloom-maintenance-evidence-v1".into();
        v["same_boot"] = true.into();
        v["journal_exit"] = 0.into();
        v["journal"] = json!([]);
        v["status_after"] = status;
        assert!(normal_collection(&v, boot));
        assert!(!normal_collection(
            &v,
            "22222222-2222-2222-2222-222222222222"
        ));
        v["status_after"]["user_units"]["exit"] = Value::Null;
        assert!(!normal_collection(&v, boot));
    }
}
