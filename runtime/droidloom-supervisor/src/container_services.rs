//! Host system-manager transactions for the root-selected shared-kernel cell.
//! A successful transaction describes the service lifetime only. Android boot
//! and application readiness still come from the production control protocol.

use std::collections::BTreeMap;
use std::io;
use std::os::unix::fs::MetadataExt;
use std::process::{Command, Stdio};

const TARGET: &str = "droidloom-container-services.target";
const OCI: &str = "droidloom-container-oci.service";
const ENTRY: &str = "droidloom-container-entry.service";
const PROGRAM: &str = "/usr/lib/droidloom/production/current/droidloomd";
/// Layout detection only prevents desktop fallback. The original production
/// broker must validate the private selection under its own configuration lock.
pub(super) fn requires_production_control() -> io::Result<bool> {
    if std::env::current_exe()?
        == std::path::Path::new("/usr/lib/droidloom/production/current/droidloomctl")
    {
        return Ok(true);
    }
    match std::fs::symlink_metadata("/etc/droidloom/production") {
        Ok(directory)
            if directory.is_dir()
                && directory.uid() == 0
                && directory.gid() == 0
                && directory.mode() & 0o022 == 0 =>
        {
            Ok(true)
        }
        Ok(_) => Err(io::Error::other("unsafe production selection directory")),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(error),
    }
}

type Properties = BTreeMap<String, String>;

fn property<'a>(properties: &'a Properties, key: &str) -> &'a str {
    properties.get(key).map_or("", String::as_str)
}

fn matches(properties: &Properties, expected: &[(&str, &str)]) -> bool {
    expected
        .iter()
        .all(|(key, value)| properties.get(*key).is_some_and(|actual| actual == value))
}

fn members<'a>(properties: &'a Properties, key: &str) -> impl Iterator<Item = &'a str> {
    property(properties, key).split_ascii_whitespace()
}

fn provider_command(value: &str) -> bool {
    let Some(fields) = value
        .trim()
        .strip_prefix('{')
        .and_then(|v| v.strip_suffix('}'))
    else {
        return false;
    };
    if fields.contains(['{', '}']) {
        return false;
    }
    let fields: Vec<_> = fields.split(';').map(str::trim).collect();
    let exact = |key: &str, expected: &str| {
        let mut values = fields.iter().filter_map(|field| field.strip_prefix(key));
        values.next() == Some(expected) && values.next().is_none()
    };
    exact("path=", PROGRAM)
        && exact("argv[]=", &format!("{PROGRAM} --manage-container"))
        && exact("ignore_errors=", "no")
}

fn verify_contract(target: &Properties, entry: &Properties) -> io::Result<()> {
    if !matches(target, &[("Id", TARGET), ("LoadState", "loaded")])
        || !["After", "BindsTo", "PropagatesStopTo"]
            .iter()
            .all(|key| members(target, key).any(|unit| unit == ENTRY))
    {
        return Err(io::Error::other(
            "shared-kernel target is missing its required container entry dependency",
        ));
    }
    if !matches(
        entry,
        &[
            ("Id", ENTRY),
            ("LoadState", "loaded"),
            ("Type", "notify"),
            ("NotifyAccess", "main"),
            ("KillMode", "control-group"),
            ("Restart", "no"),
            ("RemainAfterExit", "no"),
        ],
    ) || !members(entry, "PartOf").any(|unit| unit == TARGET)
        || !["BindsTo", "PropagatesStopTo"]
            .iter()
            .all(|key| members(entry, key).any(|unit| unit == OCI))
        || !provider_command(property(entry, "ExecStart"))
    {
        return Err(io::Error::other(
            "fixed host-managed container entry is unavailable or has a different service contract",
        ));
    }
    Ok(())
}

fn running(target: &Properties, entry: &Properties) -> bool {
    let generation = property(entry, "InvocationID");
    matches(target, &[("ActiveState", "active"), ("SubState", "active")])
        && matches(
            entry,
            &[
                ("ActiveState", "active"),
                ("SubState", "running"),
                ("Result", "success"),
            ],
        )
        && property(entry, "MainPID")
            .parse::<u32>()
            .is_ok_and(|pid| pid > 1)
        && generation.len() == 32
        && generation.bytes().all(|c| c.is_ascii_hexdigit())
        && generation.bytes().any(|c| c != b'0')
}

fn systemctl() -> Command {
    let mut command = Command::new("/usr/bin/systemctl");
    command
        .env_clear()
        .env("LC_ALL", "C")
        .args(["--system", "--no-pager", "--no-ask-password"])
        .stdin(Stdio::null());
    command
}

fn show(unit: &str, fields: &str) -> io::Result<Properties> {
    let output = systemctl()
        .args(["show", "--all", "--property", fields, unit])
        .output()?;
    if !output.status.success() {
        return Err(io::Error::other(format!(
            "system manager could not inspect {unit}: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        )));
    }
    let mut properties = Properties::new();
    for line in std::str::from_utf8(&output.stdout)
        .map_err(io::Error::other)?
        .lines()
    {
        let (key, value) = line
            .split_once('=')
            .ok_or_else(|| io::Error::other("invalid system manager response"))?;
        if properties
            .insert(key.to_owned(), value.to_owned())
            .is_some()
        {
            return Err(io::Error::other("ambiguous system manager response"));
        }
    }
    Ok(properties)
}

const TARGET_FIELDS: &str = "Id,LoadState,ActiveState,SubState,BindsTo,After,PropagatesStopTo";
const ENTRY_FIELDS: &str = "Id,LoadState,ActiveState,SubState,Type,NotifyAccess,KillMode,Restart,RemainAfterExit,ExecStart,PartOf,BindsTo,PropagatesStopTo,MainPID,InvocationID,Result";

fn snapshot() -> io::Result<(Properties, Properties)> {
    Ok((show(TARGET, TARGET_FIELDS)?, show(ENTRY, ENTRY_FIELDS)?))
}

#[derive(Debug, Eq, PartialEq)]
pub(super) struct Generation {
    pub(super) pid: u32,
    invocation: String,
}

impl Generation {
    fn from_running(target: &Properties, entry: &Properties) -> Option<Self> {
        if !running(target, entry) {
            return None;
        }
        Some(Self {
            pid: property(entry, "MainPID").parse().ok()?,
            invocation: property(entry, "InvocationID").to_owned(),
        })
    }

    pub(super) fn verify_current(&self) -> io::Result<()> {
        let (target, entry) = snapshot()?;
        verify_contract(&target, &entry)?;
        if Self::from_running(&target, &entry).as_ref() == Some(self) {
            return Ok(());
        }
        Err(io::Error::other(
            "container service generation changed during the Android request",
        ))
    }
}

pub(super) fn lifecycle(operation: &str) -> io::Result<Option<Generation>> {
    if !matches!(operation, "start" | "restart" | "stop" | "status") {
        return Err(io::Error::other("invalid container lifecycle operation"));
    }
    if operation != "stop" {
        let (target, entry) = snapshot()?;
        verify_contract(&target, &entry)?;
        if operation == "start" {
            if let Some(generation) = Generation::from_running(&target, &entry) {
                return Ok(Some(generation));
            }
        }
        if operation == "status" {
            if let Some(generation) = Generation::from_running(&target, &entry) {
                return Ok(Some(generation));
            }
            if property(&target, "ActiveState") == "inactive"
                && property(&entry, "ActiveState") == "inactive"
                && property(&entry, "MainPID") == "0"
            {
                return Ok(None);
            }
            return Err(io::Error::other(format!(
                "container service is changing state or failed: target={}, entry={}/{}, result={}",
                property(&target, "ActiveState"),
                property(&entry, "ActiveState"),
                property(&entry, "SubState"),
                property(&entry, "Result")
            )));
        }
    }
    // Each mutation is a single job submitted to the real manager. Competing
    // jobs are rejected instead of replacing another caller's transaction.
    let result = systemctl()
        .args(["--job-mode=fail", operation, TARGET])
        .status()?;
    if !result.success() {
        return Err(io::Error::other(format!(
            "container services {operation} failed ({result})"
        )));
    }
    let (target, entry) = snapshot()?;
    if operation == "stop" {
        if property(&target, "ActiveState") == "inactive"
            && matches!(property(&entry, "ActiveState"), "inactive" | "failed")
            && property(&entry, "MainPID") == "0"
            && property(&entry, "LoadState") == "loaded"
        {
            return Ok(None);
        }
        return Err(io::Error::other("container service stop has not completed"));
    }
    verify_contract(&target, &entry)?;
    Generation::from_running(&target, &entry)
        .map(Some)
        .ok_or_else(|| {
            io::Error::other("the container entry did not remain running after activation")
        })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn props(fields: &[(&str, &str)]) -> Properties {
        fields
            .iter()
            .map(|(k, v)| (k.to_string(), v.to_string()))
            .collect()
    }

    fn contract() -> (Properties, Properties) {
        let target = props(&[
            ("Id", TARGET),
            ("LoadState", "loaded"),
            ("After", ENTRY),
            ("BindsTo", ENTRY),
            ("PropagatesStopTo", ENTRY),
            ("ActiveState", "active"),
            ("SubState", "active"),
        ]);
        let mut entry = props(&[
            ("Id", ENTRY),
            ("LoadState", "loaded"),
            ("Type", "notify"),
            ("NotifyAccess", "main"),
            ("KillMode", "control-group"),
            ("Restart", "no"),
            ("RemainAfterExit", "no"),
            ("PartOf", TARGET),
            ("BindsTo", OCI),
            ("PropagatesStopTo", OCI),
            ("ActiveState", "active"),
            ("SubState", "running"),
            ("Result", "success"),
            ("MainPID", "4631"),
            ("InvocationID", "dd9bcfcc18e541e5a1723a6825ee13e1"),
        ]);
        entry.insert(
            "ExecStart".into(),
            format!("{{ path={PROGRAM} ; argv[]={PROGRAM} --manage-container ; ignore_errors=no ; pid=4631 }}"),
        );
        (target, entry)
    }

    #[test]
    fn requires_an_ordered_dependency_with_runtime_death_and_stop_propagation() {
        let (target, entry) = contract();
        assert!(verify_contract(&target, &entry).is_ok());
        for key in ["Id", "LoadState", "BindsTo", "After", "PropagatesStopTo"] {
            let mut changed = target.clone();
            changed.remove(key);
            assert!(verify_contract(&changed, &entry).is_err(), "{key}");
        }
        for key in [
            "Id",
            "LoadState",
            "Type",
            "NotifyAccess",
            "KillMode",
            "Restart",
            "RemainAfterExit",
            "PartOf",
            "BindsTo",
            "PropagatesStopTo",
            "ExecStart",
        ] {
            let mut changed = entry.clone();
            changed.remove(key);
            assert!(verify_contract(&target, &changed).is_err(), "{key}");
        }
    }

    #[test]
    fn stock_init_wrappers_extra_commands_and_ignore_failure_have_no_service_role() {
        let (_, entry) = contract();
        let valid = &entry["ExecStart"];
        for invalid in [
            valid.replace(PROGRAM, "/system/bin/init"),
            valid.replace(PROGRAM, "/usr/bin/env"),
            valid.replace(
                &format!("argv[]={PROGRAM}"),
                &format!("argv[]={PROGRAM} second_stage"),
            ),
            valid.replace("ignore_errors=no", "ignore_errors=yes"),
            format!("{valid} ; {valid}"),
            valid.replace("pid=4631", &format!("path={PROGRAM}")),
        ] {
            assert!(!provider_command(&invalid), "{invalid}");
        }
    }

    #[test]
    fn reused_pid_with_another_invocation_is_a_different_generation() {
        let (target, mut entry) = contract();
        let original = Generation::from_running(&target, &entry).unwrap();
        entry.insert(
            "InvocationID".into(),
            "bb9bcfcc18e541e5a1723a6825ee13e1".into(),
        );
        assert_ne!(Some(original), Generation::from_running(&target, &entry));
    }

    #[test]
    fn target_activity_alone_or_dead_service_cannot_report_running() {
        let (target, entry) = contract();
        assert!(running(&target, &entry));
        for (key, value) in [
            ("ActiveState", "failed"),
            ("SubState", "exited"),
            ("Result", "exit-code"),
            ("MainPID", "0"),
            ("InvocationID", "00000000000000000000000000000000"),
        ] {
            let mut changed = entry.clone();
            changed.insert(key.into(), value.into());
            assert!(!running(&target, &changed), "{key}");
        }
        let mut inactive = target;
        inactive.insert("ActiveState".into(), "inactive".into());
        assert!(!running(&inactive, &entry));
    }
}
