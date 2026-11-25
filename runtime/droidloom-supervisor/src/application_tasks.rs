//! Package-scoped observations of the actual ActivityTaskManager task list.
//!
//! This records framework metadata only. A saved record is not execution or
//! close authority and proves neither rendered pixels nor a business gate.
use super::application_probe::ApplicationInspection;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;

/// Version of the fixed, package-scoped task observation.
pub const TASK_SNAPSHOT_SCHEMA: &str = "droidloom.application-task-snapshot.v1";
const LISTING_LIMIT: usize = 65_536;
const TASK_LIMIT: usize = 256;

/// One real leaf task whose base identity belongs to the selected package/user.
#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ApplicationTask {
    /// Positive ActivityTaskManager leaf-task identity; not a close capability.
    pub task: u32,
    /// Actual containing root-task identity.
    pub root_task: u32,
    /// Android display reported by the root-task record.
    pub display: u32,
    /// Android user explicitly reported by this leaf-task record.
    pub user: u32,
    /// Exact package or normalized base component from the task record.
    pub name: String,
    /// Android's task visibility flag, not proof of host pixels or usability.
    pub visible: bool,
    /// Actual top component, possibly a foreign permission/login activity.
    pub top_activity: Option<String>,
}

/// Bounded task metadata bracketed by complete installed-identity observations.
#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ApplicationTaskSnapshot {
    /// Fixed schema; unknown versions are rejected by the live consumer.
    pub schema: String,
    /// Complete installed APK, UID and physical framework-generation binding.
    pub application: ApplicationInspection,
    /// Length of the actual fixed command stdout, including unrelated rows.
    pub listing_bytes: u64,
    /// SHA-256 of that stdout; unrelated task details are not exposed here.
    pub listing_sha256: String,
    /// Only the selected package/user's tasks, ordered by leaf-task identity.
    pub tasks: Vec<ApplicationTask>,
}

fn number(value: &str, positive: bool) -> Result<u32, String> {
    if value.is_empty() || !value.bytes().all(|b| b.is_ascii_digit()) {
        return Err("task list contains a malformed integer".into());
    }
    let value: u32 = value.parse().map_err(|_| "task list integer overflow")?;
    if value > i32::MAX as u32 || (positive && value == 0) {
        return Err("task list integer is outside Android's range".into());
    }
    Ok(value)
}

fn field<'a>(line: &'a str, prefix: &str) -> Result<&'a str, String> {
    let mut values = line
        .split_ascii_whitespace()
        .filter_map(|part| part.strip_prefix(prefix));
    let value = values
        .next()
        .ok_or_else(|| format!("task list field {prefix} is missing"))?;
    if values.next().is_some() {
        return Err(format!("task list field {prefix} is repeated"));
    }
    Ok(value)
}

fn component(value: &str) -> Result<String, String> {
    super::validate_component(value).map_err(|e| e.to_string())?;
    let (package, activity) = value
        .split_once('/')
        .ok_or("task component has no activity")?;
    if activity.starts_with('.') {
        Ok(format!("{package}/{package}{activity}"))
    } else {
        Ok(value.to_owned())
    }
}

fn task_name(value: &str) -> Result<String, String> {
    if value.contains('/') {
        component(value)
    } else {
        super::validate_package(value).map_err(|e| e.to_string())?;
        Ok(value.to_owned())
    }
}

fn owner(value: &str) -> &str {
    value.split_once('/').map_or(value, |(package, _)| package)
}

impl ApplicationTaskSnapshot {
    /// Validate a response obtained from the current authorized broker exchange.
    ///
    /// This is shape/identity validation, not authentication of saved JSON.
    pub fn validate(&self, expected: &ApplicationInspection) -> Result<(), String> {
        super::validate_package(&expected.package).map_err(|e| e.to_string())?;
        super::validate_android_user(expected.user).map_err(|e| e.to_string())?;
        if self.schema != TASK_SNAPSHOT_SCHEMA
            || self.application != *expected
            || self.listing_bytes > LISTING_LIMIT as u64
            || self.listing_sha256.len() != 64
            || !self
                .listing_sha256
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
            || self.tasks.len() > TASK_LIMIT
        {
            return Err("task snapshot schema, complete identity or bounds differ".into());
        }
        let mut previous = 0;
        for task in &self.tasks {
            if task.task <= previous
                || task.task > i32::MAX as u32
                || task.root_task == 0
                || task.root_task > i32::MAX as u32
                || task.display > i32::MAX as u32
                || task.user != expected.user
                || owner(&task.name) != expected.package
                || task_name(&task.name)? != task.name
                || task.top_activity.as_deref().map(component).transpose()? != task.top_activity
            {
                return Err("task snapshot contains an ambiguous or unscoped task".into());
            }
            previous = task.task;
        }
        Ok(())
    }
}

/// Parse only the fixed command's actual stdout, after successful retirement.
pub(crate) fn parse(
    expected: &ApplicationInspection,
    listing: &str,
) -> Result<ApplicationTaskSnapshot, String> {
    if listing.len() > LISTING_LIMIT
        || listing
            .bytes()
            .any(|b| b.is_ascii_control() && !matches!(b, b'\n' | b'\r' | b'\t'))
    {
        return Err("task list output exceeds the fixed text bound".into());
    }
    let mut root = None;
    let mut tasks = Vec::new();
    let mut identities = BTreeSet::new();
    for line in listing
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
    {
        if let Some(header) = line.strip_prefix("RootTask ") {
            let id = number(field(header, "id=")?, true)?;
            let display = number(field(header, "displayId=")?, false)?;
            number(field(header, "userId=")?, false)?;
            root = Some((id, display));
            continue;
        }
        if line.starts_with("configuration=") && root.is_some() {
            continue;
        }
        let body = line
            .strip_prefix("taskId=")
            .ok_or("unexpected task list output")?;
        let (id, fields) = body
            .split_once(':')
            .ok_or("task list leaf has no identity separator")?;
        let task = number(id, true)?;
        if !identities.insert(task) {
            return Err("task list repeats a leaf-task identity".into());
        }
        let (root_task, display) = root.ok_or("task list leaf precedes its root")?;
        let name = fields
            .split_ascii_whitespace()
            .next()
            .ok_or("task name is missing")?;
        if owner(name) != expected.package {
            continue;
        }
        let name = task_name(name)?;
        let user = number(field(fields, "userId=")?, false)?;
        if user != expected.user {
            continue;
        }
        let visible = match field(fields, "visible=")? {
            "true" => true,
            "false" => false,
            _ => return Err("task visibility is malformed".into()),
        };
        let top = field(fields, "topActivity=")?;
        let top_activity = if top == "null" {
            None
        } else {
            Some(component(
                top.strip_prefix("ComponentInfo{")
                    .and_then(|v| v.strip_suffix('}'))
                    .ok_or("task top activity is malformed")?,
            )?)
        };
        tasks.push(ApplicationTask {
            task,
            root_task,
            display,
            user,
            name,
            visible,
            top_activity,
        });
        if tasks.len() > TASK_LIMIT {
            return Err("selected package task count exceeds the fixed bound".into());
        }
    }
    tasks.sort_by_key(|task| task.task);
    let snapshot = ApplicationTaskSnapshot {
        schema: TASK_SNAPSHOT_SCHEMA.into(),
        application: expected.clone(),
        listing_bytes: listing.len() as u64,
        listing_sha256: format!("{:x}", Sha256::digest(listing.as_bytes())),
        tasks,
    };
    snapshot.validate(expected)?;
    Ok(snapshot)
}

#[cfg(test)]
mod tests {
    use super::super::application_probe::{InstalledApk, RuntimeEpoch};
    use super::*;

    fn expected() -> ApplicationInspection {
        ApplicationInspection {
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
                path: "/data/app/owned/base.apk".into(),
                bytes: 17,
                sha256: "a".repeat(64),
            }],
        }
    }

    fn row(id: u32, package: &str, user: u32, display: u32, visible: bool) -> String {
        format!(
            "RootTask id={id} displayId={display} userId={user}\n configuration={{}}\n  taskId={id}: {package}/.Main userId={user} visible={visible} topActivity=ComponentInfo{{{package}/.Main}}\n"
        )
    }

    #[test]
    fn snapshot_is_scoped_and_retains_actual_visibility_display_and_foreign_top() {
        let e = expected();
        let listing = row(9, &e.package, 0, 0, true)
            + &row(8, &e.package, 10, 0, true)
            + &row(7, "org.example.app.extra", 0, 0, true)
            + &row(6, &e.package, 0, 2, false).replace(
                "topActivity=ComponentInfo{org.example.app/.Main}",
                "topActivity=ComponentInfo{com.android.permissioncontroller/.Grant}",
            );
        let observed = parse(&e, &listing).unwrap();
        assert_eq!(observed.tasks.len(), 2);
        assert_eq!(observed.tasks[0].task, 6);
        assert_eq!(observed.tasks[0].display, 2);
        assert!(!observed.tasks[0].visible);
        assert_eq!(
            observed.tasks[0].top_activity.as_deref(),
            Some("com.android.permissioncontroller/com.android.permissioncontroller.Grant")
        );
        assert_eq!(observed.tasks[1].task, 9);
        assert_eq!(observed.listing_bytes, listing.len() as u64);
        assert_eq!(
            observed.listing_sha256,
            format!("{:x}", Sha256::digest(listing.as_bytes()))
        );
        assert!(
            !serde_json::to_string(&observed)
                .unwrap()
                .contains("org.example.app.extra")
        );
    }

    #[test]
    fn malformed_or_ambiguous_output_cannot_be_reported_as_absence() {
        let e = expected();
        let valid = row(9, &e.package, 0, 0, true);
        for invalid in [
            "Error: service unavailable".to_owned(),
            valid.replace("displayId=0", ""),
            valid.replace("userId=0 visible", "visible"),
            valid.replace("visible=true", ""),
            valid.replace("visible=true", "visible=true visible=false"),
            valid.replace("taskId=9", "taskId=2147483648"),
            valid.replace("taskId=9", "taskId=0"),
            valid.replace("taskId=9", "taskId=+9"),
            valid.replace(
                "topActivity=ComponentInfo{org.example.app/.Main}",
                "topActivity=broken",
            ),
            valid.clone() + &valid,
            valid.clone() + "\0",
            "x".repeat(LISTING_LIMIT + 1),
            valid.lines().skip(2).collect::<Vec<_>>().join("\n"),
        ] {
            assert!(parse(&e, &invalid).is_err(), "{invalid:?}");
        }
        assert!(parse(&e, "").unwrap().tasks.is_empty());
        assert!(
            parse(&e, &row(1, "com.android.launcher3", 0, 0, true))
                .unwrap()
                .tasks
                .is_empty()
        );
    }

    #[test]
    fn public_task_request_cannot_select_a_task_command_or_descriptor() {
        let e = expected();
        let request = serde_json::json!({"command":"observe_application_tasks","expected":e});
        assert!(serde_json::from_value::<super::super::ControlRequest>(request.clone()).is_ok());
        for (key, value) in [
            ("task", serde_json::json!(9)),
            ("object", serde_json::json!(7)),
            (
                "command_line",
                serde_json::json!("cmd activity remove-task 9"),
            ),
            ("namespace_pid", serde_json::json!(100)),
            ("close", serde_json::json!(true)),
        ] {
            let mut changed = request.clone();
            changed.as_object_mut().unwrap().insert(key.into(), value);
            assert!(serde_json::from_value::<super::super::ControlRequest>(changed).is_err());
        }
    }

    #[test]
    fn live_consumer_rejects_cross_epoch_identity_or_unscoped_rows() {
        let e = expected();
        let snapshot = parse(&e, &row(9, &e.package, 0, 0, true)).unwrap();
        for kind in 0..8 {
            let mut changed = snapshot.clone();
            match kind {
                0 => changed.application.epoch.framework_start_ticks += 1,
                1 => changed.application.apks[0].sha256 = "b".repeat(64),
                2 => changed.application.uid += 1,
                3 => changed.tasks[0].user = 10,
                4 => changed.tasks[0].name = "org.example.foreign/.Main".into(),
                5 => changed.tasks.push(changed.tasks[0].clone()),
                6 => changed.schema = "future".into(),
                _ => changed.listing_sha256 = "A".repeat(64),
            }
            assert!(changed.validate(&e).is_err(), "{kind}");
        }
    }
}
