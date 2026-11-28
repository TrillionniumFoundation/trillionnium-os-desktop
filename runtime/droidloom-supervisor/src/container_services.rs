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
const EARLY_LAUNCHER: &str = "droidloom-instance-launcher.service";
const EARLY_LAUNCHER_FIELDS: &str = "Id,LoadState,ActiveState,SubState,Type,NotifyAccess,KillMode,Restart,RemainAfterExit,User,Group,ExecStart,ExecStop,ExecStopPost,Requires,After,PartOf,MainPID,InvocationID,Result,ExecMainPID,ExecMainCode,ExecMainStatus,SELinuxContext,AppArmorProfile,NoNewPrivileges,SendSIGKILL,PrivateMounts";
const EARLY_OWNER_FIELDS: &str = "Id,LoadState,ActiveState,SubState,Type,KillMode,Restart,RemainAfterExit,User,Group,ExecStart,ExecStop,ExecStopPost,Requires,After,BindsTo,Conflicts,MainPID,InvocationID,Result,ExecMainPID,ExecMainCode,ExecMainStatus,SELinuxContext,AppArmorProfile,NoNewPrivileges";
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
    early: Option<EarlyInstance>,
}

impl Generation {
    fn from_running(target: &Properties, entry: &Properties) -> Option<Self> {
        if !running(target, entry) {
            return None;
        }
        Some(Self {
            pid: property(entry, "MainPID").parse().ok()?,
            invocation: property(entry, "InvocationID").to_owned(),
            early: None,
        })
    }

    pub(super) fn verify_current(&self) -> io::Result<()> {
        if self.early.is_some() {
            return if early_generation()?.as_ref() == Some(self) {
                Ok(())
            } else {
                Err(io::Error::other(
                    "early Android launcher, owner or observer changed during the request",
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

fn verify_early_launcher(launcher: &Properties) -> io::Result<()> {
    if !matches(
        launcher,
        &[
            ("Id", EARLY_LAUNCHER),
            ("LoadState", "loaded"),
            ("Type", "notify"),
            ("NotifyAccess", "main"),
            ("User", "root"),
            ("Group", "root"),
            ("KillMode", "process"),
            ("Restart", "no"),
            ("RemainAfterExit", "no"),
            ("SendSIGKILL", "no"),
            ("PrivateMounts", "no"),
            ("SELinuxContext", "u:r:droidloom_instance_launcher:s0"),
            ("AppArmorProfile", "droidloom-instance-launcher"),
            ("NoNewPrivileges", "yes"),
        ],
    ) || !["Requires", "After"]
        .iter()
        .all(|key| members(launcher, key).any(|unit| unit == "droidloom-manager-label.service"))
        || !members(launcher, "PartOf").any(|unit| unit == EARLY_OWNER)
        || !fixed_command(property(launcher, "ExecStart"), "--launch-early-instance")
        || !property(launcher, "ExecStop").is_empty()
        || !property(launcher, "ExecStopPost").is_empty()
    {
        return Err(io::Error::other(
            "early Android original-instance launcher has an incorrect service contract",
        ));
    }
    Ok(())
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct EarlyIdentity {
    pid: u32,
    invocation: String,
}

impl EarlyIdentity {
    fn retained(unit: &Properties, allow_unstarted: bool) -> io::Result<Option<Self>> {
        let id = property(unit, "InvocationID");
        // The observer need not have been attached before an orderly stop.
        // This is the only accepted absence of a previous service invocation.
        if allow_unstarted
            && (id.is_empty() || id == "00000000000000000000000000000000")
            && matches(
                unit,
                &[
                    ("ActiveState", "inactive"),
                    ("SubState", "dead"),
                    ("MainPID", "0"),
                    ("ExecMainPID", "0"),
                    ("ExecMainCode", "0"),
                    ("ExecMainStatus", "0"),
                    ("Result", "success"),
                ],
            )
        {
            return Ok(None);
        }
        let pid = property(unit, "ExecMainPID").parse::<u32>().unwrap_or(0);
        let main = property(unit, "MainPID")
            .parse::<u32>()
            .map_err(io::Error::other)?;
        if pid < 2
            || main != 0 && main != pid
            || id.len() != 32
            || !id.bytes().all(|v| v.is_ascii_hexdigit())
            || !id.bytes().any(|v| v != b'0')
        {
            return Err(io::Error::other(format!(
                "{} has no consistent original process and invocation",
                property(unit, "Id")
            )));
        }
        Ok(Some(Self {
            pid,
            invocation: id.to_owned(),
        }))
    }

    fn required(unit: &Properties) -> io::Result<Self> {
        Self::retained(unit, false)?.ok_or_else(|| io::Error::other("missing early unit identity"))
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct EarlyInstance {
    launcher: EarlyIdentity,
    owner: EarlyIdentity,
    observer: Option<EarlyIdentity>,
}

struct EarlySnapshot {
    launcher: Properties,
    owner: Properties,
    observer: Properties,
}

impl EarlySnapshot {
    fn read() -> io::Result<Self> {
        Ok(Self {
            launcher: show(EARLY_LAUNCHER, EARLY_LAUNCHER_FIELDS)?,
            owner: show(EARLY_OWNER, EARLY_OWNER_FIELDS)?,
            observer: show(EARLY, EARLY_OBSERVER_FIELDS)?,
        })
    }

    fn verify_contracts(&self) -> io::Result<()> {
        verify_early_launcher(&self.launcher)?;
        verify_early_owner(&self.owner)?;
        verify_early_observer(&self.observer)
    }

    fn identity(&self) -> io::Result<EarlyInstance> {
        self.verify_contracts()?;
        Ok(EarlyInstance {
            launcher: EarlyIdentity::required(&self.launcher)?,
            owner: EarlyIdentity::required(&self.owner)?,
            observer: EarlyIdentity::retained(&self.observer, true)?,
        })
    }

    fn running(&self) -> io::Result<Option<(Generation, EarlyInstance)>> {
        self.verify_contracts()?;
        for unit in [&self.launcher, &self.owner, &self.observer] {
            if property(unit, "ActiveState") == "failed" {
                return Err(io::Error::other(format!(
                    "{} failed: {}",
                    property(unit, "Id"),
                    property(unit, "Result")
                )));
            }
        }
        if matches(
            &self.observer,
            &[
                ("ActiveState", "inactive"),
                ("MainPID", "0"),
                ("Result", "success"),
            ],
        ) {
            return Ok(None);
        }
        for unit in [&self.launcher, &self.owner, &self.observer] {
            if !matches(
                unit,
                &[
                    ("ActiveState", "active"),
                    ("SubState", "running"),
                    ("Result", "success"),
                ],
            ) || !property(unit, "MainPID")
                .parse::<u32>()
                .is_ok_and(|pid| pid > 1)
            {
                return Err(io::Error::other(format!(
                    "{} is {}/{} ({})",
                    property(unit, "Id"),
                    property(unit, "ActiveState"),
                    property(unit, "SubState"),
                    property(unit, "Result")
                )));
            }
        }
        let identity = self.identity()?;
        let observer = identity
            .observer
            .as_ref()
            .ok_or_else(|| io::Error::other("running early observer has no invocation"))?;
        Ok(Some((
            Generation {
                pid: observer.pid,
                invocation: observer.invocation.clone(),
                early: Some(identity.clone()),
            },
            identity,
        )))
    }
}

fn early_generation() -> io::Result<Option<Generation>> {
    Ok(EarlySnapshot::read()?
        .running()?
        .map(|(generation, _)| generation))
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
    ) || !["Requires", "After"].iter().all(|key| {
        [
            "droidloom-manager-label.service",
            "systemd-tmpfiles-setup.service",
        ]
        .iter()
        .all(|required| members(owner, key).any(|unit| unit == *required))
    }) || !members(owner, "Conflicts").any(|unit| unit == "droidloomd.service")
        || !members(owner, "After").any(|unit| unit == "droidloomd.service")
        || !["Requires", "After", "BindsTo"]
            .iter()
            .all(|key| members(owner, key).any(|unit| unit == EARLY_LAUNCHER))
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

fn early_retired(
    snapshot: &EarlySnapshot,
    original: &EarlyInstance,
    public_absent: bool,
) -> io::Result<bool> {
    if snapshot.identity()? != *original {
        return Err(io::Error::other(
            "early Android launcher, owner or observer changed during shutdown",
        ));
    }
    let mut complete = true;
    for (unit, identity) in [
        (&snapshot.launcher, Some(&original.launcher)),
        (&snapshot.owner, Some(&original.owner)),
        (&snapshot.observer, original.observer.as_ref()),
    ] {
        if property(unit, "ActiveState") == "failed"
            || property(unit, "ActiveState") == "inactive" && property(unit, "Result") != "success"
        {
            return Err(io::Error::other(format!(
                "{} failed to retire cleanly: {}",
                property(unit, "Id"),
                property(unit, "Result")
            )));
        }
        if property(unit, "ActiveState") != "inactive" || property(unit, "MainPID") != "0" {
            complete = false;
            continue;
        }
        // The identities above bind ExecMainPID to each originally held MainPID.
        // The launcher's ordinary exit(0) follows the factory's DLDONE01, after
        // actual owner/init retirement and waitid. A signal or reset-failed is
        // never evidence of that complete transaction.
        if identity.is_some()
            && !matches(
                unit,
                &[
                    ("SubState", "dead"),
                    ("ExecMainCode", "1"),
                    ("ExecMainStatus", "0"),
                ],
            )
        {
            return Err(io::Error::other(format!(
                "{} did not complete its original orderly shutdown",
                property(unit, "Id")
            )));
        }
    }
    Ok(complete && public_absent)
}

fn public_readiness_absent() -> io::Result<bool> {
    match std::fs::symlink_metadata("/run/droidloom-container/readiness.sock") {
        Ok(_) => Ok(false),
        Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(true),
        Err(e) => Err(e),
    }
}

// The caller keeps all three RefUnit references through stop and any subsequent
// start, so systemd cannot discard the original exit records in between.
fn stop_early() -> io::Result<EarlyInstance> {
    let snapshot = EarlySnapshot::read()?;
    let original = snapshot.identity()?;
    if early_retired(&snapshot, &original, public_readiness_absent()?)? {
        return Ok(original);
    }
    for unit in [&snapshot.launcher, &snapshot.owner] {
        if !matches(
            unit,
            &[
                ("ActiveState", "active"),
                ("SubState", "running"),
                ("Result", "success"),
            ],
        ) || !property(unit, "MainPID")
            .parse::<u32>()
            .is_ok_and(|pid| pid > 1)
        {
            return Err(io::Error::other(
                "early Android launcher and owner are not ready for an orderly stop",
            ));
        }
    }
    // Recheck the same original generations before submitting the one normal
    // manager transaction. --no-block acknowledges only that job, not retirement.
    if EarlySnapshot::read()?.identity()? != original {
        return Err(io::Error::other(
            "early Android changed before orderly shutdown",
        ));
    }
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
        let snapshot = EarlySnapshot::read()?;
        if early_retired(&snapshot, &original, public_readiness_absent()?)? {
            return Ok(original);
        }
        if std::time::Instant::now() >= end {
            return Err(io::Error::other(
                "early Android owner, observer or original launcher retirement exceeded its deadline",
            ));
        }
        std::thread::sleep(std::time::Duration::from_millis(100));
    }
}

fn fresh_early(previous: &EarlyInstance, current: &EarlyInstance) -> io::Result<()> {
    if previous.launcher.invocation == current.launcher.invocation
        || previous.owner.invocation == current.owner.invocation
        || current.observer.is_none()
        || previous.observer.as_ref().is_some_and(|old| {
            current
                .observer
                .as_ref()
                .is_some_and(|new| old.invocation == new.invocation)
        })
    {
        return Err(io::Error::other(
            "early Android restart did not replace all three original service invocations",
        ));
    }
    Ok(())
}

fn start_early() -> io::Result<(Generation, EarlyInstance)> {
    let status = systemctl()
        .args(["--job-mode=fail", "start", EARLY])
        .status()?;
    if !status.success() {
        return Err(io::Error::other(
            "could not start the original Android instance and its trusted observer",
        ));
    }
    EarlySnapshot::read()?.running()?.ok_or_else(|| {
        io::Error::other("early Android launcher, owner and observer did not remain running")
    })
}

pub(super) fn early_lifecycle(operation: &str) -> io::Result<Option<Generation>> {
    match operation {
        "status" => early_generation(),
        "start" => {
            let _references = EarlyUnitReferences::early()?;
            if let Some(current) = early_generation()? {
                return Ok(Some(current));
            }
            Ok(Some(start_early()?.0))
        }
        "stop" => {
            let _references = EarlyUnitReferences::early()?;
            stop_early()?;
            Ok(None)
        }
        "restart" => {
            let _references = EarlyUnitReferences::early()?;
            let previous = stop_early()?;
            let (generation, current) = start_early()?;
            fresh_early(&previous, &current)?;
            // Native readiness is still authenticated by the caller's existing
            // production control protocol, including its final generation check.
            Ok(Some(generation))
        }
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
    fn early_contract() -> EarlySnapshot {
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
            (
                "Requires",
                "systemd-tmpfiles-setup.service droidloom-manager-label.service droidloom-instance-launcher.service",
            ),
            (
                "After",
                "local-fs.target systemd-tmpfiles-setup.service droidloomd.service droidloom-manager-label.service droidloom-instance-launcher.service",
            ),
            ("BindsTo", EARLY_LAUNCHER),
            ("Conflicts", "droidloomd.service"),
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
            ("SubState", "dead"),
            ("MainPID", "0"),
            ("InvocationID", "223456789abcdef0123456789abcdef0"),
            ("Result", "success"),
            ("ExecMainPID", "4632"),
            ("ExecMainCode", "1"),
            ("ExecMainStatus", "0"),
        ]);
        observer.insert("ExecStart".into(), format!(
            "{{ path={PROGRAM} ; argv[]={PROGRAM} --observe-early-container ; ignore_errors=no ; pid=4632 }}"));
        let mut launcher = props(&[
            ("Id", EARLY_LAUNCHER),
            ("LoadState", "loaded"),
            ("Type", "notify"),
            ("NotifyAccess", "main"),
            ("User", "root"),
            ("Group", "root"),
            ("KillMode", "process"),
            ("Restart", "no"),
            ("RemainAfterExit", "no"),
            ("SendSIGKILL", "no"),
            ("PrivateMounts", "no"),
            ("SELinuxContext", "u:r:droidloom_instance_launcher:s0"),
            ("AppArmorProfile", "droidloom-instance-launcher"),
            ("NoNewPrivileges", "yes"),
            ("Requires", "droidloom-manager-label.service"),
            ("After", "local-fs.target droidloom-manager-label.service"),
            ("PartOf", EARLY_OWNER),
            ("ActiveState", "inactive"),
            ("SubState", "dead"),
            ("MainPID", "0"),
            ("InvocationID", "323456789abcdef0123456789abcdef0"),
            ("Result", "success"),
            ("ExecMainPID", "4630"),
            ("ExecMainCode", "1"),
            ("ExecMainStatus", "0"),
        ]);
        launcher.insert("ExecStart".into(), format!(
            "{{ path={PROGRAM} ; argv[]={PROGRAM} --launch-early-instance ; ignore_errors=no ; pid=4630 }}"));
        EarlySnapshot {
            launcher,
            owner,
            observer,
        }
    }

    fn early_unit(snapshot: &mut EarlySnapshot, index: usize) -> &mut Properties {
        match index {
            0 => &mut snapshot.launcher,
            1 => &mut snapshot.owner,
            2 => &mut snapshot.observer,
            _ => panic!("invalid test unit"),
        }
    }

    fn running_early_contract() -> EarlySnapshot {
        let mut snapshot = early_contract();
        for unit in [
            &mut snapshot.launcher,
            &mut snapshot.owner,
            &mut snapshot.observer,
        ] {
            unit.insert("ActiveState".into(), "active".into());
            unit.insert("SubState".into(), "running".into());
            unit.insert("MainPID".into(), unit["ExecMainPID"].clone());
            unit.insert("ExecMainCode".into(), "0".into());
        }
        snapshot
    }

    #[test]
    fn early_stop_requires_all_original_normal_exits_and_withdrawn_readiness() {
        let snapshot = early_contract();
        let original = snapshot.identity().unwrap();
        assert!(early_retired(&snapshot, &original, true).unwrap());
        assert!(!early_retired(&snapshot, &original, false).unwrap());
        for index in 0..3 {
            let mut pending = early_contract();
            let unit = early_unit(&mut pending, index);
            unit.insert("ActiveState".into(), "deactivating".into());
            unit.insert("SubState".into(), "stop-sigterm".into());
            unit.insert("MainPID".into(), unit["ExecMainPID"].clone());
            unit.insert("ExecMainCode".into(), "0".into());
            assert!(
                !early_retired(&pending, &original, true).unwrap(),
                "unit {index}"
            );
            for (key, value) in [
                ("Result", "timeout"),
                ("Result", "exit-code"),
                ("ExecMainCode", "2"),
                ("ExecMainCode", "3"),
                ("ExecMainCode", "0"),
                ("ExecMainStatus", "1"),
                ("ExecMainPID", "0"),
                ("ExecMainPID", "94631"),
                ("MainPID", "94631"),
                ("InvocationID", "423456789abcdef0123456789abcdef0"),
            ] {
                let mut changed = early_contract();
                early_unit(&mut changed, index).insert(key.into(), value.into());
                assert!(
                    early_retired(&changed, &original, true).is_err(),
                    "unit {index}: {key}={value}"
                );
            }
        }
    }

    #[test]
    fn early_stop_cannot_replace_the_orderly_owner_or_original_launcher_with_a_kill_command() {
        let original = early_contract().identity().unwrap();
        for (index, key, value) in [
            (1, "KillMode", "control-group"),
            (1, "Restart", "always"),
            (1, "SELinuxContext", "-u:r:droidloom_broker:s0"),
            (1, "AppArmorProfile", "-droidloom-production-broker"),
            (1, "NoNewPrivileges", "no"),
            (1, "ExecStart", "/bin/true"),
            (1, "ExecStop", "/bin/kill"),
            (1, "ExecStopPost", "/bin/true"),
            (1, "Requires", ""),
            (
                1,
                "Requires",
                "droidloom-manager-label.service droidloom-instance-launcher.service",
            ),
            (
                1,
                "After",
                "local-fs.target droidloomd.service droidloom-manager-label.service droidloom-instance-launcher.service",
            ),
            (1, "Conflicts", ""),
            (1, "User", "qq"),
            (1, "BindsTo", ""),
            (0, "KillMode", "control-group"),
            (0, "SendSIGKILL", "yes"),
            (0, "PrivateMounts", "yes"),
            (0, "PartOf", ""),
            (0, "NotifyAccess", "all"),
            (0, "SELinuxContext", "u:r:kernel:s0"),
            (0, "AppArmorProfile", ""),
            (0, "NoNewPrivileges", "no"),
            (0, "ExecStart", "/bin/true"),
            (0, "ExecStop", "/bin/kill"),
            (0, "ExecStopPost", "/bin/true"),
            (0, "Requires", ""),
            (0, "User", "qq"),
            (2, "BindsTo", ""),
        ] {
            let mut changed = early_contract();
            early_unit(&mut changed, index).insert(key.into(), value.into());
            assert!(
                early_retired(&changed, &original, true).is_err(),
                "unit {index}: {key}={value}"
            );
        }
    }

    #[test]
    fn an_unattached_observer_is_allowed_only_with_a_complete_unstarted_record() {
        let mut snapshot = early_contract();
        for (key, value) in [
            ("InvocationID", ""),
            ("ExecMainPID", "0"),
            ("ExecMainCode", "0"),
        ] {
            snapshot.observer.insert(key.into(), value.into());
        }
        let original = snapshot.identity().unwrap();
        assert!(original.observer.is_none());
        assert!(early_retired(&snapshot, &original, true).unwrap());
        snapshot
            .observer
            .insert("ExecMainPID".into(), "4632".into());
        assert!(early_retired(&snapshot, &original, true).is_err());
    }

    #[test]
    fn early_running_needs_all_three_original_processes_not_observer_activity_alone() {
        let snapshot = running_early_contract();
        let (generation, identity) = snapshot.running().unwrap().unwrap();
        assert_eq!(generation.pid, 4632);
        assert_eq!(generation.invocation, identity.observer.unwrap().invocation);
        for index in 0..3 {
            for (key, value) in [
                ("MainPID", "0"),
                ("ExecMainPID", "94631"),
                ("InvocationID", ""),
                ("ActiveState", "failed"),
                ("SubState", "exited"),
            ] {
                let mut changed = running_early_contract();
                early_unit(&mut changed, index).insert(key.into(), value.into());
                assert!(changed.running().is_err(), "unit {index}: {key}={value}");
            }
        }
    }

    #[test]
    fn early_restart_requires_three_new_invocations_even_if_a_numeric_pid_is_reused() {
        let previous = running_early_contract().identity().unwrap();
        let mut snapshot = running_early_contract();
        for (index, id) in [
            (0, "423456789abcdef0123456789abcdef0"),
            (1, "523456789abcdef0123456789abcdef0"),
            (2, "623456789abcdef0123456789abcdef0"),
        ] {
            early_unit(&mut snapshot, index).insert("InvocationID".into(), id.into());
        }
        let (_, current) = snapshot.running().unwrap().unwrap();
        assert_eq!(previous.owner.pid, current.owner.pid);
        assert!(fresh_early(&previous, &current).is_ok());
        for index in 0..3 {
            let mut reused = current.clone();
            match index {
                0 => reused.launcher = previous.launcher.clone(),
                1 => reused.owner = previous.owner.clone(),
                2 => reused.observer = previous.observer.clone(),
                _ => unreachable!(),
            }
            assert!(fresh_early(&previous, &reused).is_err(), "unit {index}");
        }
        let mut absent = current;
        absent.observer = None;
        assert!(fresh_early(&previous, &absent).is_err());
    }
    #[test]
    fn readiness_cannot_survive_a_launcher_or_owner_generation_replacement() {
        let (original, _) = running_early_contract().running().unwrap().unwrap();
        for index in 0..2 {
            let mut snapshot = running_early_contract();
            early_unit(&mut snapshot, index).insert(
                "InvocationID".into(),
                "423456789abcdef0123456789abcdef0".into(),
            );
            let (changed, _) = snapshot.running().unwrap().unwrap();
            assert_eq!(original.pid, changed.pid);
            assert_eq!(original.invocation, changed.invocation);
            assert_ne!(original, changed, "unit {index}");
        }
    }
}
