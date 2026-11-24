//! Host system-manager transactions for the root-selected shared-kernel cell.
//! A successful transaction describes the service lifetime only. Android boot
//! and application readiness still come from the production control protocol.

use std::collections::BTreeMap;
use std::io;
use std::os::unix::fs::MetadataExt;
use std::process::{Command, Stdio};

const TARGET: &str = "droidloom-container-services.target";
const SOCKET: &str = "droidloom-container-guest.socket";
const OCI: &str = "droidloom-container-oci.service";
const ENTRY: &str = "droidloom-container-entry.service";
const EARLY: &str = "droidloom-early-observer.service";
const EARLY_OWNER: &str = "droidloom-production.service";
const EARLY_OWNER_FIELDS: &str = "Id,LoadState,ActiveState,SubState,Type,KillMode,Restart,RemainAfterExit,User,Group,ExecStart,ExecStop,ExecStopPost,Requires,After,MainPID,InvocationID,Result,ExecMainPID,ExecMainCode,ExecMainStatus,SELinuxContext,AppArmorProfile,NoNewPrivileges";
const EARLY_OBSERVER_FIELDS: &str = "Id,LoadState,ActiveState,SubState,Type,NotifyAccess,KillMode,Restart,RemainAfterExit,ExecStart,BindsTo,After,Requires,MainPID,InvocationID,Result,ExecMainPID,ExecMainCode,ExecMainStatus";
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

use droidloom_supervisor::control::EarlyUnitReferences;

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

fn fixed_command(value: &str, action: &str) -> bool {
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
        && exact("argv[]=", &format!("{PROGRAM} {action}"))
        && exact("ignore_errors=", "no")
}

fn provider_command(value: &str) -> bool {
    fixed_command(value, "--manage-container")
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
        || !["BindsTo", "After", "PropagatesStopTo"]
            .iter()
            .all(|key| members(entry, key).any(|unit| unit == OCI))
        || !["After", "Requires"]
            .iter()
            .all(|key| members(entry, key).any(|unit| unit == SOCKET))
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
const ENTRY_FIELDS: &str = "Id,LoadState,ActiveState,SubState,Type,NotifyAccess,KillMode,Restart,RemainAfterExit,ExecStart,PartOf,BindsTo,After,Requires,PropagatesStopTo,MainPID,InvocationID,Result";

fn snapshot() -> io::Result<(Properties, Properties)> {
    Ok((show(TARGET, TARGET_FIELDS)?, show(ENTRY, ENTRY_FIELDS)?))
}

#[derive(Debug, Eq, PartialEq)]
pub(super) struct Generation {
    pub(super) pid: u32,
    invocation: String,
    early: bool,
}

impl Generation {
    fn from_running(target: &Properties, entry: &Properties) -> Option<Self> {
        if !running(target, entry) {
            return None;
        }
        Some(Self {
            pid: property(entry, "MainPID").parse().ok()?,
            invocation: property(entry, "InvocationID").to_owned(),
            early: false,
        })
    }

    pub(super) fn verify_current(&self) -> io::Result<()> {
        if self.early {
            return if early_generation()?.as_ref() == Some(self) {
                Ok(())
            } else {
                Err(io::Error::other(
                    "early Android observer changed during the request",
                ))
            };
        }
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

fn retired(
    target: &Properties,
    entry: &Properties,
    oci: &Properties,
    socket: &Properties,
    public_absent: bool,
) -> io::Result<bool> {
    for (properties, id) in [
        (target, TARGET),
        (entry, ENTRY),
        (oci, OCI),
        (socket, SOCKET),
    ] {
        if !matches(properties, &[("Id", id), ("LoadState", "loaded")]) {
            return Err(io::Error::other(format!(
                "cannot verify retirement of {id}"
            )));
        }
        let state = property(properties, "ActiveState");
        if state == "failed"
            || state == "inactive" && properties.get("Result").is_some_and(|v| v != "success")
        {
            return Err(io::Error::other(format!(
                "{id} failed to retire cleanly: {}",
                property(properties, "Result")
            )));
        }
    }
    Ok(public_absent
        && [target, entry, oci, socket]
            .iter()
            .all(|p| property(p, "ActiveState") == "inactive")
        && [entry, oci]
            .iter()
            .all(|p| property(p, "MainPID") == "0" && property(p, "Result") == "success"))
}

fn wait_for_retirement() -> io::Result<()> {
    let end = std::time::Instant::now() + std::time::Duration::from_secs(300);
    loop {
        let (target, entry) = snapshot()?;
        let oci = show(OCI, "Id,LoadState,ActiveState,MainPID,Result")?;
        let socket = show(SOCKET, "Id,LoadState,ActiveState,Result")?;
        let absent = match std::fs::symlink_metadata("/run/droidloom-container/readiness.sock") {
            Ok(_) => false,
            Err(e) if e.kind() == io::ErrorKind::NotFound => true,
            Err(e) => return Err(e),
        };
        if retired(&target, &entry, &oci, &socket, absent)? {
            return Ok(());
        }
        if std::time::Instant::now() >= end {
            return Err(io::Error::other(
                "container manager, OCI owner or readiness socket did not finish retirement",
            ));
        }
        std::thread::sleep(std::time::Duration::from_millis(100));
    }
}

fn verify_early_observer(s: &Properties) -> io::Result<()> {
    if !matches(
        s,
        &[
            ("Id", EARLY),
            ("LoadState", "loaded"),
            ("Type", "notify"),
            ("NotifyAccess", "main"),
            ("KillMode", "control-group"),
            ("Restart", "no"),
            ("RemainAfterExit", "no"),
        ],
    ) || !["Requires", "After"]
        .iter()
        .all(|key| members(s, key).any(|unit| unit == "droidloom-manager-label.service"))
        || !["BindsTo", "After"]
            .iter()
            .all(|key| members(s, key).any(|unit| unit == EARLY_OWNER))
        || !fixed_command(property(s, "ExecStart"), "--observe-early-container")
    {
        return Err(io::Error::other(
            "kernel-booted Android observer has an incorrect service contract",
        ));
    }
    Ok(())
}

fn early_generation() -> io::Result<Option<Generation>> {
    let s = show(EARLY, EARLY_OBSERVER_FIELDS)?;
    verify_early_observer(&s)?;
    if matches(
        &s,
        &[
            ("ActiveState", "inactive"),
            ("MainPID", "0"),
            ("Result", "success"),
        ],
    ) {
        return Ok(None);
    }
    let id = property(&s, "InvocationID");
    let pid = property(&s, "MainPID").parse::<u32>().unwrap_or(0);
    if !matches(
        &s,
        &[
            ("ActiveState", "active"),
            ("SubState", "running"),
            ("Result", "success"),
        ],
    ) || pid < 2
        || id.len() != 32
        || !id.bytes().all(|v| v.is_ascii_hexdigit())
        || !id.bytes().any(|v| v != b'0')
    {
        return Err(io::Error::other(format!(
            "kernel-booted Android observer is {}/{} ({})",
            property(&s, "ActiveState"),
            property(&s, "SubState"),
            property(&s, "Result")
        )));
    }
    Ok(Some(Generation {
        pid,
        invocation: id.to_owned(),
        early: true,
    }))
}

// Only the production owner can request Android shutdown and verify retirement
// of its original data, metadata, namespaces and cgroup. Stopping the observer
// withdraws readiness but does not stop Android.
fn verify_early_owner(owner: &Properties) -> io::Result<()> {
    if !matches(
        owner,
        &[
            ("Id", EARLY_OWNER),
            ("LoadState", "loaded"),
            ("Type", "exec"),
            ("User", "root"),
            ("Group", "root"),
            ("KillMode", "mixed"),
            ("Restart", "no"),
            ("RemainAfterExit", "no"),
            ("SELinuxContext", "u:r:droidloom_broker:s0"),
            ("AppArmorProfile", "droidloom-production-broker"),
            ("NoNewPrivileges", "yes"),
        ],
    ) || !["Requires", "After"]
        .iter()
        .all(|key| members(owner, key).any(|unit| unit == "droidloom-manager-label.service"))
        || !fixed_command(
            property(owner, "ExecStart"),
            "--socket /run/droidloom/control.sock",
        )
        || !property(owner, "ExecStop").is_empty()
        || !property(owner, "ExecStopPost").is_empty()
    {
        return Err(io::Error::other(
            "early Android production owner has an incorrect service contract",
        ));
    }
    Ok(())
}

fn early_owner_invocation(owner: &Properties) -> io::Result<String> {
    let id = property(owner, "InvocationID");
    if id.len() != 32
        || !id.bytes().all(|v| v.is_ascii_hexdigit())
        || !id.bytes().any(|v| v != b'0')
    {
        return Err(io::Error::other(
            "early Android has no retained production owner invocation",
        ));
    }
    Ok(id.to_owned())
}

fn early_retired(
    owner: &Properties,
    observer: &Properties,
    invocation: &str,
    public_absent: bool,
) -> io::Result<bool> {
    verify_early_owner(owner)?;
    verify_early_observer(observer)?;
    if early_owner_invocation(owner)? != invocation {
        return Err(io::Error::other(
            "early Android production owner changed during shutdown",
        ));
    }
    for (s, id) in [(owner, EARLY_OWNER), (observer, EARLY)] {
        if property(s, "ActiveState") == "failed"
            || property(s, "ActiveState") == "inactive" && property(s, "Result") != "success"
        {
            return Err(io::Error::other(format!(
                "{id} failed to retire cleanly: {}",
                property(s, "Result")
            )));
        }
    }
    if property(owner, "ActiveState") != "inactive" || property(owner, "MainPID") != "0" {
        return Ok(false);
    }
    // systemd treats some signal deaths as success. Only the owner's ordinary
    // exit(0) follows the successful orderly request AND actual resource cleanup.
    // Never accept reset-failed, an unstarted unit, SIGTERM or SIGKILL as that exit.
    if property(owner, "ExecMainCode") != "1"
        || property(owner, "ExecMainStatus") != "0"
        || !property(owner, "ExecMainPID")
            .parse::<u32>()
            .is_ok_and(|pid| pid > 1)
    {
        return Err(io::Error::other(
            "early Android owner did not complete its orderly shutdown and retirement",
        ));
    }
    if property(observer, "ActiveState") != "inactive" || property(observer, "MainPID") != "0" {
        return Ok(false);
    }
    if property(observer, "ExecMainPID")
        .parse::<u32>()
        .is_ok_and(|pid| pid > 1)
        && (property(observer, "ExecMainCode") != "1"
            || property(observer, "ExecMainStatus") != "0")
    {
        return Err(io::Error::other(
            "early Android observer exited without completing its shutdown",
        ));
    }
    Ok(public_absent)
}

fn public_readiness_absent() -> io::Result<bool> {
    match std::fs::symlink_metadata("/run/droidloom-container/readiness.sock") {
        Ok(_) => Ok(false),
        Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(true),
        Err(e) => Err(e),
    }
}

fn stop_early() -> io::Result<()> {
    let _references = EarlyUnitReferences::early()?;
    let owner = show(EARLY_OWNER, EARLY_OWNER_FIELDS)?;
    verify_early_owner(&owner)?;
    let invocation = early_owner_invocation(&owner)?;
    let observer = show(EARLY, EARLY_OBSERVER_FIELDS)?;
    if early_retired(&owner, &observer, &invocation, public_readiness_absent()?)? {
        return Ok(());
    }
    if !matches(
        &owner,
        &[
            ("ActiveState", "active"),
            ("SubState", "running"),
            ("Result", "success"),
        ],
    ) || !property(&owner, "MainPID")
        .parse::<u32>()
        .is_ok_and(|pid| pid > 1)
    {
        return Err(io::Error::other(
            "early Android production owner is not ready for an orderly stop",
        ));
    }
    // Submit the normal manager transaction once. It signals the real owner's
    // signalfd; StopRequest and mount retirement remain inside that owner.
    // --no-block acknowledges only the job. The observations below establish
    // completion and never convert that acknowledgement into a success result.
    let status = systemctl()
        .args(["--job-mode=fail", "--no-block", "stop", EARLY_OWNER])
        .status()?;
    if !status.success() {
        return Err(io::Error::other(
            "could not submit early Android production-owner shutdown",
        ));
    }
    let end = std::time::Instant::now() + std::time::Duration::from_secs(180);
    loop {
        let owner = show(EARLY_OWNER, EARLY_OWNER_FIELDS)?;
        let observer = show(EARLY, EARLY_OBSERVER_FIELDS)?;
        if early_retired(&owner, &observer, &invocation, public_readiness_absent()?)? {
            return Ok(());
        }
        if std::time::Instant::now() >= end {
            return Err(io::Error::other(
                "early Android orderly shutdown or observer retirement exceeded its deadline",
            ));
        }
        std::thread::sleep(std::time::Duration::from_millis(100));
    }
}

pub(super) fn early_lifecycle(operation: &str) -> io::Result<Option<Generation>> {
    match operation {
        "status" => early_generation(),
        "start" => {
            if let Some(current) = early_generation()? {
                return Ok(Some(current));
            }
            let status = systemctl()
                .args(["--job-mode=fail", "start", EARLY])
                .status()?;
            if !status.success() {
                return Err(io::Error::other(
                    "could not attach the trusted observer to the kernel-booted Android instance",
                ));
            }
            early_generation()?.map(Some).ok_or_else(|| {
                io::Error::other("kernel-booted Android observer did not remain attached")
            })
        }
        "stop" => {
            stop_early()?;
            Ok(None)
        }
        "restart" => Err(io::Error::new(
            io::ErrorKind::Unsupported,
            "the selected early Android instance is created once during kernel boot; a same-boot relaunch endpoint is not available",
        )),
        _ => Err(io::Error::other(
            "invalid early Android lifecycle operation",
        )),
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
    if operation == "stop" {
        wait_for_retirement()?;
        return Ok(None);
    }
    let (target, entry) = snapshot()?;
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
            (
                "After",
                "droidloom-container-oci.service droidloom-container-guest.socket",
            ),
            ("Requires", SOCKET),
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
            "After",
            "Requires",
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
    fn stopping_the_target_alone_or_force_killing_a_guest_cannot_report_clean_stop() {
        let stopped = |id: &str| {
            props(&[
                ("Id", id),
                ("LoadState", "loaded"),
                ("ActiveState", "inactive"),
                ("MainPID", "0"),
                ("Result", "success"),
            ])
        };
        let target = stopped(TARGET);
        let entry = stopped(ENTRY);
        let oci = stopped(OCI);
        let socket = stopped(SOCKET);
        assert!(retired(&target, &entry, &oci, &socket, true).unwrap());
        let mut pending = oci.clone();
        pending.insert("ActiveState".into(), "deactivating".into());
        assert!(!retired(&target, &entry, &pending, &socket, true).unwrap());
        assert!(!retired(&target, &entry, &oci, &socket, false).unwrap());
        let mut failed = entry.clone();
        failed.insert("Result".into(), "exit-code".into());
        assert!(retired(&target, &failed, &oci, &socket, true).is_err());
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
    fn early_contract() -> (Properties, Properties) {
        let mut owner = props(&[
            ("Id", EARLY_OWNER),
            ("LoadState", "loaded"),
            ("Type", "exec"),
            ("User", "root"),
            ("Group", "root"),
            ("KillMode", "mixed"),
            ("Restart", "no"),
            ("RemainAfterExit", "no"),
            ("SELinuxContext", "u:r:droidloom_broker:s0"),
            ("AppArmorProfile", "droidloom-production-broker"),
            ("NoNewPrivileges", "yes"),
            ("Requires", "droidloom-manager-label.service"),
            ("After", "local-fs.target droidloom-manager-label.service"),
            ("ActiveState", "inactive"),
            ("SubState", "dead"),
            ("MainPID", "0"),
            ("InvocationID", "123456789abcdef0123456789abcdef0"),
            ("Result", "success"),
            ("ExecMainPID", "4631"),
            ("ExecMainCode", "1"),
            ("ExecMainStatus", "0"),
        ]);
        owner.insert("ExecStart".into(), format!(
            "{{ path={PROGRAM} ; argv[]={PROGRAM} --socket /run/droidloom/control.sock ; ignore_errors=no ; pid=4631 }}"));
        let mut observer = props(&[
            ("Id", EARLY),
            ("LoadState", "loaded"),
            ("Type", "notify"),
            ("NotifyAccess", "main"),
            ("KillMode", "control-group"),
            ("Restart", "no"),
            ("RemainAfterExit", "no"),
            ("Requires", "droidloom-manager-label.service"),
            (
                "After",
                "droidloom-manager-label.service droidloom-production.service",
            ),
            ("BindsTo", EARLY_OWNER),
            ("ActiveState", "inactive"),
            ("MainPID", "0"),
            ("Result", "success"),
            ("ExecMainPID", "4632"),
            ("ExecMainCode", "1"),
            ("ExecMainStatus", "0"),
        ]);
        observer.insert("ExecStart".into(), format!(
            "{{ path={PROGRAM} ; argv[]={PROGRAM} --observe-early-container ; ignore_errors=no ; pid=4632 }}"));
        (owner, observer)
    }

    #[test]
    fn early_stop_requires_the_original_owners_normal_exit_and_withdrawn_readiness() {
        let (owner, observer) = early_contract();
        let invocation = early_owner_invocation(&owner).unwrap();
        assert!(early_retired(&owner, &observer, &invocation, true).unwrap());
        assert!(!early_retired(&owner, &observer, &invocation, false).unwrap());
        let mut running = owner.clone();
        running.insert("ActiveState".into(), "deactivating".into());
        running.insert("MainPID".into(), "4631".into());
        assert!(!early_retired(&running, &observer, &invocation, true).unwrap());
        for (key, value) in [
            ("Result", "timeout"),
            ("Result", "exit-code"),
            ("ExecMainCode", "2"),
            ("ExecMainCode", "3"),
            ("ExecMainCode", "0"),
            ("ExecMainStatus", "1"),
            ("ExecMainPID", "0"),
            ("InvocationID", "223456789abcdef0123456789abcdef0"),
        ] {
            let mut changed = owner.clone();
            changed.insert(key.into(), value.into());
            assert!(
                early_retired(&changed, &observer, &invocation, true).is_err(),
                "{key}={value}"
            );
        }
        let mut signaled = observer.clone();
        signaled.insert("ExecMainCode".into(), "2".into());
        assert!(early_retired(&owner, &signaled, &invocation, true).is_err());
        let mut active_observer = observer.clone();
        active_observer.insert("ActiveState".into(), "active".into());
        active_observer.insert("MainPID".into(), "4632".into());
        assert!(!early_retired(&owner, &active_observer, &invocation, true).unwrap());
    }

    #[test]
    fn early_stop_cannot_replace_the_orderly_owner_with_an_unconfined_or_kill_command() {
        let (owner, observer) = early_contract();
        let invocation = early_owner_invocation(&owner).unwrap();
        for (key, value) in [
            ("KillMode", "control-group"),
            ("Restart", "always"),
            ("SELinuxContext", "-u:r:droidloom_broker:s0"),
            ("AppArmorProfile", "-droidloom-production-broker"),
            ("NoNewPrivileges", "no"),
            ("ExecStart", "/bin/true"),
            ("ExecStop", "/bin/kill"),
            ("ExecStopPost", "/bin/true"),
            ("Requires", ""),
            ("User", "qq"),
        ] {
            let mut changed = owner.clone();
            changed.insert(key.into(), value.into());
            assert!(
                early_retired(&changed, &observer, &invocation, true).is_err(),
                "{key}={value}"
            );
        }
        let mut detached = observer.clone();
        detached.remove("BindsTo");
        assert!(early_retired(&owner, &detached, &invocation, true).is_err());
    }

    #[test]
    fn early_restart_refuses_before_any_service_or_runtime_operation() {
        let error = early_lifecycle("restart").unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::Unsupported);
        assert!(error.to_string().contains("once during kernel boot"));
    }
}
