//! One explicit launcher observation through the existing owned supervisor API.
//! This does not close an Android task, prove a fresh task, or grant business gates.
use super::{ApplicationInspection, FilePin, INPUT_LIMIT, consume_inspection, pinned};
use droidloom_supervisor::control::application_tasks::ApplicationTaskSnapshot;
use droidloom_supervisor::control::{self, CellState, ControlRequest, ControlResponse};
use serde::{Deserialize, Serialize};
use std::path::Path;

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct LaunchPlan {
    pub(super) specification: FilePin,
    pub(super) component: String,
}

/// The current supervisor's authenticated RegisterDirect result. Numeric values
/// are observations, never inputs that construct authority or permission to close.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub(super) struct OwnedTaskObservation {
    object: u64,
    composer_display: u64,
    android_display: u64,
    task: u64,
}

#[derive(Clone, Debug, Serialize)]
pub(super) struct LaunchObservation {
    pub(super) scope: &'static str,
    pub(super) requested_component: String,
    pub(super) catalog_component: String,
    pub(super) task: OwnedTaskObservation,
    pub(super) tasks_before: ApplicationTaskSnapshot,
    pub(super) tasks_after: ApplicationTaskSnapshot,
    pub(super) business_pending: bool,
    pub(super) close_observed: bool,
    pub(super) reopen_observed: bool,
    pub(super) fresh_task_proven: bool,
}

impl LaunchPlan {
    pub(super) fn validate(&self, package: &str) -> Result<(), String> {
        if !crate::valid_package(package)
            || !crate::valid_component(&self.component, package)
            || self.specification.bytes == 0
            || self.specification.bytes > INPUT_LIMIT
            || !crate::release::valid_sha(&self.specification.sha256)
            || !self.specification.path.is_absolute()
        {
            return Err("launch-only route needs the exact package component and pinned absolute cell specification".into());
        }
        Ok(())
    }
}

pub(super) fn normalized(component: &str, package: &str) -> Result<String, String> {
    if !crate::valid_component(component, package) {
        return Err(
            "launcher catalog component belongs to a different package or is malformed".into(),
        );
    }
    let (_, activity) = component
        .split_once('/')
        .ok_or("missing activity component")?;
    Ok(if activity.starts_with('.') {
        format!("{package}/{package}{activity}")
    } else {
        component.to_owned()
    })
}

fn running_owner(reply: &ControlResponse, expected: &ApplicationInspection) -> Result<(), String> {
    if !reply.ok {
        return Err(reply.message.clone());
    }
    if reply.state != CellState::Running || reply.host_pid != Some(expected.epoch.cell_host_pid) {
        return Err(
            "launch-only response does not belong to the selected running Android owner".into(),
        );
    }
    Ok(())
}

fn parse_binding(output: &str) -> Result<OwnedTaskObservation, String> {
    if output.is_empty() || output.len() > 256 || !output.is_ascii() {
        return Err("owned launch response exceeds its exact bounded task binding".into());
    }
    let mut values = std::collections::BTreeMap::new();
    for field in output.split_ascii_whitespace() {
        let (key, value) = field
            .split_once('=')
            .ok_or("malformed owned task binding")?;
        if !matches!(
            key,
            "object" | "composer_display" | "android_display" | "task"
        ) || value.is_empty()
            || !value.bytes().all(|v| v.is_ascii_digit())
            || values.contains_key(key)
        {
            return Err(
                "owned task binding contains an unknown, repeated or malformed field".into(),
            );
        }
        values.insert(
            key,
            value
                .parse::<u64>()
                .map_err(|_| "task binding integer overflow")?,
        );
    }
    if values.len() != 4 {
        return Err("owned task binding is incomplete".into());
    }
    let task = OwnedTaskObservation {
        object: values["object"],
        composer_display: values["composer_display"],
        android_display: values["android_display"],
        task: values["task"],
    };
    if task.object == 0
        || task.composer_display == 0
        || task.task == 0
        || task.task > i32::MAX as u64
        || task.android_display != 0
    {
        return Err("owned task binding is not a real task on the built-in display".into());
    }
    Ok(task)
}

fn same_inspection(reply: ControlResponse, expected: &ApplicationInspection) -> Result<(), String> {
    running_owner(&reply, expected)?;
    let (actual, _) = consume_inspection(reply, &expected.package, expected.user)?;
    if actual != *expected {
        return Err("complete installed package/UID/APK identity or Main epoch changed".into());
    }
    Ok(())
}

fn task_snapshot(
    reply: ControlResponse,
    expected: &ApplicationInspection,
) -> Result<ApplicationTaskSnapshot, String> {
    running_owner(&reply, expected)?;
    if reply.inspection.as_ref() != Some(expected) {
        return Err(
            "task observation returned a different installed identity or Main epoch".into(),
        );
    }
    let raw = reply
        .diagnostics
        .ok_or("broker returned no typed task observation")?;
    if raw.len() > 262_144 {
        return Err("task observation exceeds the bounded response".into());
    }
    let snapshot: ApplicationTaskSnapshot =
        serde_json::from_str(&raw).map_err(|e| format!("task observation JSON differs: {e}"))?;
    snapshot.validate(expected)?;
    Ok(snapshot)
}

pub(super) fn execute(
    socket: &Path,
    expected: &ApplicationInspection,
    plan: &LaunchPlan,
    source_receipt: &FilePin,
) -> Result<LaunchObservation, String> {
    execute_with(expected, plan, source_receipt, |request| {
        control::request(socket, request).map_err(|error| error.to_string())
    })
}

fn execute_with(
    expected: &ApplicationInspection,
    plan: &LaunchPlan,
    source_receipt: &FilePin,
    mut request: impl FnMut(&ControlRequest) -> Result<ControlResponse, String>,
) -> Result<LaunchObservation, String> {
    plan.validate(&expected.package)?;
    pinned(&plan.specification)?;
    pinned(source_receipt)?;
    let reply = request(&ControlRequest::ListApplications {
        user: expected.user,
    })?;
    running_owner(&reply, expected)?;
    let catalog = reply
        .applications
        .ok_or("daemon returned no current launcher catalog")?;
    let selected = normalized(&plan.component, &expected.package)?;
    let candidates: Vec<_> = catalog
        .iter()
        .filter(|entry| entry.package == expected.package)
        .filter(|entry| {
            normalized(&entry.component, &entry.package).is_ok_and(|value| value == selected)
        })
        .collect();
    if candidates.len() != 1 {
        return Err("reviewed component is missing or ambiguous in the current enabled MAIN/LAUNCHER catalog".into());
    }
    let catalog_component = candidates[0].component.clone();
    let inspect = ControlRequest::InspectApplication {
        package: expected.package.clone(),
        user: expected.user,
    };
    // Catalog discovery cannot substitute for actual PM, complete split hashes,
    // UID, physical framework generation or whole-image custody.
    same_inspection(request(&inspect)?, expected)?;
    pinned(&plan.specification)?;
    pinned(source_receipt)?;
    let observe = ControlRequest::ObserveApplicationTasks {
        expected: expected.clone(),
    };
    let tasks_before = task_snapshot(request(&observe)?, expected)?;
    pinned(&plan.specification)?;
    pinned(source_receipt)?;
    let reply = request(&ControlRequest::Launch {
        spec: plan.specification.path.clone(),
        package: expected.package.clone(),
        component: Some(plan.component.clone()),
        // A resolution adds -S to the existing primitive. This route never
        // requests a force-stop and cannot call that an observed close/reopen.
        resolution: None,
        user: expected.user,
    })?;
    // A failure after this point may follow a real launch. Preserve its binding
    // in the error, never replay it or use numeric IDs to attempt cleanup.
    let retained = reply
        .launch
        .as_deref()
        .unwrap_or("<missing>")
        .chars()
        .take(256)
        .collect::<String>();
    let observed = (|| {
        running_owner(&reply, expected)?;
        if reply.inspection.as_ref() != Some(expected) {
            return Err("owned launch returned a different or missing installed identity".into());
        }
        let task = parse_binding(
            reply
                .launch
                .as_deref()
                .ok_or("owned launch returned no actual task binding")?,
        )?;
        let tasks_after = task_snapshot(request(&observe)?, expected)?;
        if !tasks_after.tasks.iter().any(|row| {
            u64::from(row.task) == task.task
                && u64::from(row.display) == task.android_display
                && row.visible
        }) {
            return Err("launched binding is not listed for this package/user under a visible Android root task".into());
        }
        same_inspection(request(&inspect)?, expected)?;
        pinned(&plan.specification)?;
        pinned(source_receipt)?;
        Ok(LaunchObservation {
            scope: "launch_only",
            requested_component: plan.component.clone(),
            catalog_component,
            task,
            tasks_before,
            tasks_after,
            business_pending: true,
            close_observed: false,
            reopen_observed: false,
            fresh_task_proven: false,
        })
    })();
    observed.map_err(|error: String| {
        format!("{error}; retained owned launch binding: {retained}; no automatic retry")
    })
}

#[cfg(test)]
pub(super) fn test_observation(
    component: &str,
    expected: &ApplicationInspection,
) -> LaunchObservation {
    LaunchObservation {
        scope: "launch_only",
        requested_component: component.into(),
        catalog_component: component.into(),
        task: parse_binding("object=7 composer_display=8 android_display=0 task=9").unwrap(),
        tasks_before: test_snapshot(expected, false),
        tasks_after: test_snapshot(expected, true),
        business_pending: true,
        close_observed: false,
        reopen_observed: false,
        fresh_task_proven: false,
    }
}

#[cfg(test)]
fn test_snapshot(expected: &ApplicationInspection, launched: bool) -> ApplicationTaskSnapshot {
    use droidloom_supervisor::control::application_tasks::{ApplicationTask, TASK_SNAPSHOT_SCHEMA};
    ApplicationTaskSnapshot {
        schema: TASK_SNAPSHOT_SCHEMA.into(),
        application: expected.clone(),
        listing_bytes: if launched { 200 } else { 0 },
        listing_sha256: "c".repeat(64),
        tasks: if launched {
            vec![ApplicationTask {
                task: 9,
                root_task: 9,
                display: 0,
                user: expected.user,
                name: format!("{}/{}.Main", expected.package, expected.package),
                visible: true,
                top_activity: Some(format!("{}/{}.Main", expected.package, expected.package)),
            }]
        } else {
            vec![]
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use droidloom_supervisor::control::{
        AndroidApplication,
        application_probe::{InstalledApk, RuntimeEpoch},
    };
    use sha2::{Digest, Sha256};
    use std::collections::VecDeque;

    fn pin(path: &Path, content: &[u8]) -> FilePin {
        std::fs::write(path, content).unwrap();
        FilePin {
            path: path.to_owned(),
            bytes: content.len() as u64,
            sha256: hex::encode(Sha256::digest(content)),
        }
    }
    fn fixture() -> (
        tempfile::TempDir,
        ApplicationInspection,
        LaunchPlan,
        FilePin,
    ) {
        let dir = tempfile::tempdir().unwrap();
        let specification = pin(&dir.path().join("cell.json"), b"reviewed-cell");
        let source = pin(&dir.path().join("source.json"), b"reviewed-source");
        let expected = ApplicationInspection {
            package: "org.example.app".into(),
            user: 0,
            uid: 10123,
            version_code: 42,
            epoch: RuntimeEpoch {
                boot_id: "00000000-0000-0000-0000-000000000001".into(),
                cell_host_pid: 100,
                framework_host_pid: 101,
                framework_start_ticks: 102,
            },
            apks: vec![InstalledApk {
                name: "base.apk".into(),
                path: "/data/app/reviewed/base.apk".into(),
                bytes: 17,
                sha256: "a".repeat(64),
            }],
        };
        let plan = LaunchPlan {
            specification,
            component: "org.example.app/.Main".into(),
        };
        (dir, expected, plan, source)
    }
    fn reply(expected: &ApplicationInspection) -> ControlResponse {
        ControlResponse {
            ok: true,
            state: CellState::Running,
            host_pid: Some(expected.epoch.cell_host_pid),
            message: "unit-test transport model, not runtime evidence".into(),
            launch: None,
            applications: None,
            application_icon: None,
            diagnostics: None,
            inspection: Some(expected.clone()),
            image_custody: None,
            runtime_vintf: None,
        }
    }
    fn responses(expected: &ApplicationInspection) -> VecDeque<ControlResponse> {
        let mut catalog = reply(expected);
        catalog.applications = Some(vec![AndroidApplication {
            name: "Fixture".into(),
            package: expected.package.clone(),
            component: "org.example.app/org.example.app.Main".into(),
            icon_key: "1".into(),
        }]);
        let mut launched = reply(expected);
        launched.launch = Some("object=7 composer_display=8 android_display=0 task=9".into());
        let mut before = reply(expected);
        before.diagnostics = Some(serde_json::to_string(&test_snapshot(expected, false)).unwrap());
        let mut after = reply(expected);
        after.diagnostics = Some(serde_json::to_string(&test_snapshot(expected, true)).unwrap());
        VecDeque::from([
            catalog,
            reply(expected),
            before,
            launched,
            after,
            reply(expected),
        ])
    }

    #[test]
    fn real_typed_launch_shape_keeps_all_observation_limits_explicit() {
        let (_dir, expected, plan, source) = fixture();
        let mut replies = responses(&expected);
        let mut calls = Vec::new();
        let result = execute_with(&expected, &plan, &source, |request| {
            calls.push(request.clone());
            Ok(replies.pop_front().unwrap())
        })
        .unwrap();
        assert_eq!(calls.len(), 6);
        assert!(matches!(&calls[3], ControlRequest::Launch {
            spec, package, component: Some(component), resolution: None, user: 0,
        } if spec == &plan.specification.path && package == &expected.package && component == &plan.component));
        assert_eq!(result.scope, "launch_only");
        assert_eq!(result.task.task, 9);
        assert!(result.tasks_before.tasks.is_empty());
        assert_eq!(result.tasks_after.tasks[0].task, 9);
        assert!(result.tasks_after.tasks[0].visible);
        assert_eq!(
            result.catalog_component,
            "org.example.app/org.example.app.Main"
        );
        assert!(result.business_pending);
        assert!(!result.close_observed && !result.reopen_observed && !result.fresh_task_proven);
    }

    #[test]
    fn absent_or_ambiguous_enabled_component_never_launches() {
        for duplicate in [false, true] {
            let (_dir, expected, plan, source) = fixture();
            let mut replies = responses(&expected);
            let catalog = replies[0].applications.as_mut().unwrap();
            if duplicate {
                catalog.push(catalog[0].clone());
            } else {
                catalog.clear();
            }
            let mut calls = 0;
            assert!(
                execute_with(&expected, &plan, &source, |_| {
                    calls += 1;
                    Ok(replies.pop_front().unwrap())
                })
                .is_err()
            );
            assert_eq!(calls, 1);
        }
    }

    #[test]
    fn changed_identity_or_epoch_before_mutation_never_launches() {
        for kind in 0..4 {
            let (_dir, expected, plan, source) = fixture();
            let mut replies = responses(&expected);
            let actual = replies[1].inspection.as_mut().unwrap();
            match kind {
                0 => actual.epoch.framework_start_ticks += 1,
                1 => actual.apks[0].sha256 = "b".repeat(64),
                2 => actual.uid += 1,
                _ => actual.user += 1,
            }
            let mut calls = 0;
            assert!(
                execute_with(&expected, &plan, &source, |_| {
                    calls += 1;
                    Ok(replies.pop_front().unwrap())
                })
                .is_err()
            );
            assert_eq!(calls, 2);
        }
    }

    #[test]
    fn wrong_owner_and_stale_source_pin_cannot_start_an_activity() {
        let (_dir, expected, plan, source) = fixture();
        let mut replies = responses(&expected);
        replies[0].host_pid = Some(999);
        let mut calls = 0;
        assert!(
            execute_with(&expected, &plan, &source, |_| {
                calls += 1;
                Ok(replies.pop_front().unwrap())
            })
            .is_err()
        );
        assert_eq!(calls, 1);
        std::fs::write(&source.path, b"changed-source").unwrap();
        assert!(
            execute_with(&expected, &plan, &source, |_| {
                calls += 1;
                unreachable!()
            })
            .is_err()
        );
        assert_eq!(calls, 1);
    }

    #[test]
    fn catalog_time_specification_change_is_rejected_before_launch() {
        let (_dir, expected, plan, source) = fixture();
        let mut replies = responses(&expected);
        let mut calls = 0;
        assert!(
            execute_with(&expected, &plan, &source, |_| {
                calls += 1;
                if calls == 1 {
                    std::fs::write(&plan.specification.path, b"changed-cell").unwrap();
                }
                Ok(replies.pop_front().unwrap())
            })
            .is_err()
        );
        assert_eq!(calls, 2);
    }

    #[test]
    fn post_launch_failure_keeps_binding_and_never_retries() {
        let (_dir, expected, plan, source) = fixture();
        let mut replies = responses(&expected);
        replies[5].inspection.as_mut().unwrap().version_code += 1;
        let mut calls = 0;
        let failure = execute_with(&expected, &plan, &source, |_| {
            calls += 1;
            Ok(replies.pop_front().unwrap())
        })
        .unwrap_err();
        assert_eq!(calls, 6);
        assert!(failure.contains("task=9") && failure.contains("no automatic retry"));
    }

    #[test]
    fn changed_or_absent_snapshot_before_launch_cannot_start_an_activity() {
        for kind in 0..3 {
            let (_dir, expected, plan, source) = fixture();
            let mut replies = responses(&expected);
            let mut before = test_snapshot(&expected, false);
            match kind {
                0 => before.application.epoch.framework_start_ticks += 1,
                1 => before.schema = "unsupported".into(),
                _ => replies[2].inspection.as_mut().unwrap().uid += 1,
            }
            replies[2].diagnostics = Some(serde_json::to_string(&before).unwrap());
            let mut calls = Vec::new();
            assert!(
                execute_with(&expected, &plan, &source, |request| {
                    calls.push(request.clone());
                    Ok(replies.pop_front().unwrap())
                })
                .is_err()
            );
            assert_eq!(calls.len(), 3);
            assert!(
                !calls
                    .iter()
                    .any(|call| matches!(call, ControlRequest::Launch { .. }))
            );
        }
    }

    #[test]
    fn post_launch_task_must_match_actual_binding_user_visibility_and_epoch() {
        for kind in 0..5 {
            let (_dir, expected, plan, source) = fixture();
            let mut replies = responses(&expected);
            let mut after = test_snapshot(&expected, true);
            match kind {
                0 => after.tasks[0].task += 1,
                1 => after.tasks[0].user += 1,
                2 => after.tasks[0].display += 1,
                3 => after.tasks[0].visible = false,
                _ => after.application.epoch.framework_start_ticks += 1,
            }
            replies[4].diagnostics = Some(serde_json::to_string(&after).unwrap());
            let mut calls = Vec::new();
            let failure = execute_with(&expected, &plan, &source, |request| {
                calls.push(request.clone());
                Ok(replies.pop_front().unwrap())
            })
            .unwrap_err();
            assert_eq!(calls.len(), 5);
            assert_eq!(
                calls
                    .iter()
                    .filter(|call| matches!(call, ControlRequest::Launch { .. }))
                    .count(),
                1
            );
            assert!(failure.contains("task=9") && failure.contains("no automatic retry"));
        }
    }

    #[test]
    fn preexisting_visible_task_is_observed_without_freshness_or_close_authority() {
        let (_dir, expected, plan, source) = fixture();
        let mut replies = responses(&expected);
        replies[2].diagnostics =
            Some(serde_json::to_string(&test_snapshot(&expected, true)).unwrap());
        let observed = execute_with(&expected, &plan, &source, |_| {
            Ok(replies.pop_front().unwrap())
        })
        .unwrap();
        assert_eq!(observed.tasks_before.tasks, observed.tasks_after.tasks);
        assert!(
            !observed.fresh_task_proven && !observed.close_observed && !observed.reopen_observed
        );
        assert!(observed.business_pending);
    }

    #[test]
    fn binding_parser_rejects_diagnostics_duplicates_wrong_display_and_non_tasks() {
        for invalid in [
            "success",
            "object=7 composer_display=8 android_display=0",
            "object=7 composer_display=8 android_display=0 task=9 extra=1",
            "object=7 composer_display=8 android_display=0 task=9 task=10",
            "object=7 composer_display=8 android_display=1 task=9",
            "object=0 composer_display=8 android_display=0 task=9",
            "object=7 composer_display=8 android_display=0 task=0",
            "object=7 composer_display=8 android_display=0 task=2147483648",
            "object=18446744073709551616 composer_display=8 android_display=0 task=9",
            "object=7 composer_display=8 android_display=0 task=+9",
        ] {
            assert!(parse_binding(invalid).is_err(), "{invalid}");
        }
    }
}
