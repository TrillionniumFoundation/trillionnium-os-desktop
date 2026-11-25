//! Admission of the complete, normally installed native package closure.
//! Source receipts, durable normal dpkg events and every installed package
//! member are independently linked. Baseline booleans cannot manufacture an
//! installed root.
use crate::complete_native::{
    self, CompleteManifest, EvidencePin, HeldInput, Package, RecordedJson, RootIdentity,
    SourceReceipt,
};
use crate::model::Content;
use crate::{Result, ensure, fs, paths};
use rustix::fs::{self as rfs, AtFlags, FileType};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};
#[cfg(test)]
use std::path::Path;
use std::path::PathBuf;

const JSON_LIMIT: u64 = 16 * 1024 * 1024;
const MATERIAL_LIMIT: u64 = 128 * 1024 * 1024;
const RELEASE_ID: &str = "27aa919057651931545bbf16edca2375decb23f3c5ee7c6e8b6c9ac95db55d51";
const CLOSURE_SHA: &str = "e2313acff5f71ecfbd01c903451ff9a1575c15179ad2b29f0baa709e7d8a9d10";
const CORE_ID: &str = "6ebb7aa9fa3641236eaef37dee825663014f1a4e5d248099d90e9201c8819913";
const SYSTEMD_ID: &str = "139c6ad8cb0a7d619ff09f88100c437efc04fc76fd3fca30ffcef16566596341";
const CREDSTORE_SHA: &str = "2bafed09323dcb75c9c59ffd863510c2d05b6939fbcda267a82198875d1b4ddb";
const SYSTEMD_NAMES: &[&str] = &[
    "systemd",
    "systemd-sysv",
    "systemd-timesyncd",
    "libpam-systemd",
    "libnss-systemd",
    "libsystemd0",
    "libsystemd-shared",
    "udev",
    "libudev1",
    "systemd-resolved",
];

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct RelativePin {
    path: String,
    bytes: u64,
    sha256: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Pair {
    package: RelativePin,
    inventory: RelativePin,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Role {
    role: String,
    name: String,
    source: String,
    old_version: String,
    new_version: String,
    old: Pair,
    new: Pair,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Component {
    directory: String,
    release_id: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Release {
    schema: String,
    release_id: String,
    closure_sha256: String,
    components: BTreeMap<String, Component>,
    files: Vec<RelativePin>,
    package_names: Vec<String>,
    package_roles: Vec<Role>,
    normal_archives_verified: bool,
    whole_payload_verified: bool,
    package_database_modified: bool,
    physical_install: bool,
    runtime_qualified: bool,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Attempt {
    release: EvidencePin,
    snapshot: EvidencePin,
    events: Vec<EvidencePin>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Installation {
    schema: String,
    root: RootIdentity,
    baseline_receipt: EvidencePin,
    native_release: EvidencePin,
    attempts: Vec<Attempt>,
    packages: EvidencePin,
    dpkg_status: EvidencePin,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Inventory {
    control: BTreeMap<String, Value>,
    payload: Vec<Payload>,
    runtime_elfs: Vec<Payload>,
}
#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct SystemdInventory {
    schema: String,
    archive: Value,
    control: BTreeMap<String, Value>,
    kind: String,
    package: String,
    payload: Vec<Payload>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Payload {
    path: String,
    bytes: u64,
    uid: u32,
    gid: u32,
    mode: u32,
    #[serde(rename = "type")]
    kind: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    sha256: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    target: Option<String>,
}

fn safe_relative(value: &str) -> Result<()> {
    ensure(
        !value.is_empty()
            && value.len() <= 4096
            && !value.starts_with('/')
            && !value
                .bytes()
                .any(|b| b.is_ascii_control() || b.is_ascii_whitespace()),
        "invalid normal native relative path",
    )?;
    paths::parts(&format!("/{value}"))?;
    Ok(())
}
fn relative(pin: &RelativePin) -> Result<()> {
    safe_relative(&pin.path)?;
    ensure(
        pin.bytes <= MATERIAL_LIMIT && fs::valid_digest(&pin.sha256),
        "invalid normal native material pin",
    )
}
fn source_versions(name: &str) -> Result<(&'static str, &'static str, &'static str)> {
    Ok(match name {
        "libselinux1" => ("libselinux", "3.9-4build1", "3.9-4build1+p4lsmexec4"),
        "libapparmor1" => (
            "apparmor",
            "5.0.2-0ubuntu1~26.04.1",
            "5.0.2-0ubuntu1~26.04.1+p4peer1",
        ),
        "gdm3" | "libgdm1" | "gir1.2-gdm-1.0" => {
            ("gdm3", "50.1-0ubuntu0.1", "50.1-0ubuntu0.1+p4fsuser3")
        }
        n if SYSTEMD_NAMES.contains(&n) => {
            ("systemd", "259.9-0ubuntu0.1", "259.9-0ubuntu0.1+p4gentmp1")
        }
        _ => return Err("unreviewed normal native package".into()),
    })
}
fn release(document: &RecordedJson) -> Result<Release> {
    let mut descriptor = document.validate()?;
    let r: Release = serde_json::from_value(descriptor.clone())?;
    descriptor
        .as_object_mut()
        .ok_or("normal release object absent")?
        .remove("release_id");
    ensure(
        r.release_id == RELEASE_ID
            && r.closure_sha256 == CLOSURE_SHA
            && fs::digest(&canonical(&descriptor)?) == r.release_id,
        "normal native source release digest differs",
    )?;
    ensure(
        r.schema == "droidloom-normal-native-package-release-v2"
            && fs::valid_digest(&r.release_id)
            && fs::valid_digest(&r.closure_sha256)
            && r.normal_archives_verified
            && r.whole_payload_verified
            && !r.package_database_modified
            && !r.physical_install
            && !r.runtime_qualified
            && r.package_roles.len() == 15
            && (30..=512).contains(&r.files.len()),
        "normal complete native release contract differs",
    )?;
    ensure(
        r.components
            .keys()
            .map(String::as_str)
            .collect::<BTreeSet<_>>()
            == BTreeSet::from(["native-five", "systemd"]),
        "normal release component closure differs",
    )?;
    for (name, c) in &r.components {
        ensure(
            c.directory == *name
                && c.release_id
                    == if name == "native-five" {
                        CORE_ID
                    } else {
                        SYSTEMD_ID
                    },
            "normal component identity differs",
        )?;
    }
    let mut files = BTreeMap::new();
    let mut total = 0u64;
    for p in &r.files {
        relative(p)?;
        ensure(
            ["native-five", "systemd"].contains(&p.path.split('/').next().unwrap_or(""))
                && files.insert(p.path.as_str(), p).is_none(),
            "duplicate or foreign native release file",
        )?;
        total = total
            .checked_add(p.bytes)
            .ok_or("native material size overflow")?;
    }
    ensure(
        total <= 2 * 1024 * 1024 * 1024,
        "normal native material closure too large",
    )?;
    let mut names = BTreeSet::new();
    let mut roles = BTreeSet::new();
    for role in &r.package_roles {
        let (source, old, new) = source_versions(&role.name)?;
        ensure(
            role.source == source
                && role.old_version == old
                && role.new_version == new
                && names.insert(role.name.as_str())
                && roles.insert(role.role.as_str())
                && !role.role.is_empty()
                && role
                    .role
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b)),
            "normal native role/version/source differs",
        )?;
        for pair in [&role.old, &role.new] {
            for p in [&pair.package, &pair.inventory] {
                relative(p)?;
                ensure(
                    files.get(p.path.as_str()) == Some(&p),
                    "package/inventory is outside exact normal release",
                )?;
            }
            ensure(
                pair.package.path.ends_with(".deb") && pair.inventory.path.ends_with(".json"),
                "normal native package/inventory type differs",
            )?;
        }
    }
    let expected: Vec<String> = [
        "libselinux1",
        "libapparmor1",
        "libgdm1",
        "gir1.2-gdm-1.0",
        "gdm3",
    ]
    .into_iter()
    .chain(SYSTEMD_NAMES.iter().copied())
    .map(str::to_owned)
    .collect();
    ensure(
        r.package_names == expected
            && r.package_names
                == r.package_roles
                    .iter()
                    .map(|r| r.name.clone())
                    .collect::<Vec<_>>(),
        "normal native package order differs",
    )?;
    Ok(r)
}
fn selected_pin<'a>(proofs: &'a [RecordedJson], pin: &EvidencePin) -> Result<&'a RecordedJson> {
    complete_native::proof(proofs, pin)
}
fn named_proof<'a>(
    proofs: &'a [RecordedJson],
    release_pin: &EvidencePin,
    pin: &RelativePin,
) -> Result<&'a RecordedJson> {
    let path = release_pin
        .path
        .parent()
        .ok_or("release parent absent")?
        .join(&pin.path);
    let rows: Vec<_> = proofs
        .iter()
        .filter(|p| p.pin.path == path && p.pin.bytes == pin.bytes && p.pin.sha256 == pin.sha256)
        .collect();
    ensure(
        rows.len() == 1,
        "normal release inventory proof absent or duplicated",
    )?;
    Ok(rows[0])
}
fn components(proofs: &[RecordedJson], release_pin: &EvidencePin, r: &Release) -> Result<()> {
    for (name, component) in &r.components {
        let relative = format!("{name}/NATIVE-RELEASE.json");
        let pin = r
            .files
            .iter()
            .find(|p| p.path == relative)
            .ok_or("normal component release absent")?;
        let raw = named_proof(proofs, release_pin, pin)?.validate()?;
        let mut descriptor = raw.clone();
        descriptor
            .as_object_mut()
            .ok_or("normal component object absent")?
            .remove("release_id");
        ensure(
            raw["release_id"] == component.release_id
                && fs::digest(&canonical(&descriptor)?) == component.release_id,
            "normal component source release changed",
        )?;
        let files = raw["files"]
            .as_array()
            .ok_or("normal component inventory absent")?;
        let mut expected = BTreeMap::new();
        for file in files {
            let p: RelativePin = serde_json::from_value(file.clone())?;
            relative_pin_flat(&p)?;
            ensure(
                expected
                    .insert(format!("{name}/{}", p.path), (p.bytes, p.sha256))
                    .is_none(),
                "normal component inventory duplicated",
            )?;
        }
        expected.insert(relative.clone(), (pin.bytes, pin.sha256.clone()));
        let actual: BTreeMap<_, _> = r
            .files
            .iter()
            .filter(|p| p.path.starts_with(&format!("{name}/")))
            .map(|p| (p.path.clone(), (p.bytes, p.sha256.clone())))
            .collect();
        ensure(
            expected == actual,
            "combined native release is not both complete normal components",
        )?;
    }
    Ok(())
}
fn relative_pin_flat(pin: &RelativePin) -> Result<()> {
    relative(pin)?;
    ensure(
        !pin.path.contains('/'),
        "normal component member is not a fixed flat file",
    )
}

fn read_installation(input: &SourceReceipt, proofs: &[RecordedJson]) -> Result<Installation> {
    let pin = input
        .native_transaction
        .as_ref()
        .ok_or("normal installation receipt absent")?;
    let value: Installation = serde_json::from_value(selected_pin(proofs, pin)?.validate()?)?;
    ensure(
        value.schema == "droidloom.complete-native-installation.v1"
            && value.root == input.root
            && Some(&value.baseline_receipt) == input.baseline_receipt.as_ref()
            && Some(&value.native_release) == input.native_release.as_ref()
            && value.packages == input.packages
            && value.dpkg_status == input.dpkg_status
            && value.attempts.len() == 1,
        "normal installation is not this complete source",
    )?;
    Ok(value)
}
fn add(pin: &EvidencePin, held: &mut Vec<HeldInput>, proofs: &mut Vec<RecordedJson>) -> Result<()> {
    ensure(
        pin.uid == 0 && pin.gid == 0 && pin.mode & 0o022 == 0,
        "complete normal evidence is not root protected",
    )?;
    if let Some(old) = proofs.iter().find(|v| v.pin.path == pin.path) {
        return ensure(old.pin == *pin, "same evidence path has different pins");
    }
    let mut file = HeldInput::open(pin.clone(), JSON_LIMIT)?;
    proofs.push(file.json()?);
    held.push(file);
    Ok(())
}
fn actual_evidence(path: PathBuf, bytes: u64, sha256: String) -> Result<EvidencePin> {
    let (parent, name) = fs::absolute_parent(&fs::absolute_string(&path)?)?;
    let id = fs::identity(&rfs::statat(&parent, name, AtFlags::SYMLINK_NOFOLLOW)?);
    ensure(
        FileType::from_raw_mode(id.mode) == FileType::RegularFile
            && id.nlink == 1
            && id.uid == 0
            && id.gid == 0
            && id.mode & 0o022 == 0
            && id.size == bytes,
        "normal material metadata differs",
    )?;
    Ok(EvidencePin {
        path,
        bytes,
        sha256,
        device: id.dev,
        inode: id.ino,
        mode: id.mode & 0o7777,
        uid: id.uid,
        gid: id.gid,
    })
}

fn release_materials(
    release_pin: &EvidencePin,
    held: &mut Vec<HeldInput>,
    proofs: &mut Vec<RecordedJson>,
) -> Result<Release> {
    add(release_pin, held, proofs)?;
    let r = release(selected_pin(proofs, release_pin)?)?;
    let parent = release_pin
        .path
        .parent()
        .ok_or("native release parent absent")?;
    for p in &r.files {
        let pin = actual_evidence(parent.join(&p.path), p.bytes, p.sha256.clone())?;
        if p.path.ends_with(".json") {
            add(&pin, held, proofs)?;
        } else {
            held.push(HeldInput::open(pin, MATERIAL_LIMIT)?);
        }
    }
    components(proofs, release_pin, &r)?;
    Ok(r)
}

pub(super) fn gather(
    input: &SourceReceipt,
    held: &mut Vec<HeldInput>,
    proofs: &mut Vec<RecordedJson>,
) -> Result<()> {
    let baseline_pin = input
        .baseline_receipt
        .as_ref()
        .ok_or("installed source lacks original baseline")?;
    add(baseline_pin, held, proofs)?;
    let baseline = complete_native::source(selected_pin(proofs, baseline_pin)?)?;
    ensure(
        baseline.stage == "baseline",
        "installed source baseline is not original",
    )?;
    for p in std::iter::once(&baseline.bootstrap_receipt)
        .chain(baseline.package_transactions.iter())
        .chain(std::iter::once(&baseline.packages))
    {
        add(p, held, proofs)?;
    }
    for p in [
        input
            .native_release
            .as_ref()
            .ok_or("native release absent")?,
        input
            .native_transaction
            .as_ref()
            .ok_or("native transaction absent")?,
        &input.packages,
    ] {
        add(p, held, proofs)?;
    }
    let release_pin = input.native_release.as_ref().unwrap();
    let _release = release_materials(release_pin, held, proofs)?;
    let install = read_installation(input, proofs)?;
    for attempt in &install.attempts {
        ensure(
            attempt.release == *release_pin && (8..=16).contains(&attempt.events.len()),
            "normal attempt release/events differ",
        )?;
        add(&attempt.snapshot, held, proofs)?;
        for pin in &attempt.events {
            add(pin, held, proofs)?;
        }
        // Ended commands are the actual fixed dpkg calls; their original
        // bounded stdout/stderr and executable bytes remain held throughout.
        for pin in &attempt.events {
            let event = selected_pin(proofs, pin)?.validate()?;
            if [
                "unpack-new-prerequisite-ended",
                "configure-new-prerequisite-ended",
                "unpack-new-ended",
                "configure-new-ended",
            ]
            .contains(&event["stage"].as_str().unwrap_or(""))
            {
                for stream in ["stdout", "stderr"] {
                    let value = &event[stream];
                    let name = value["file"]
                        .as_str()
                        .ok_or("normal command log name absent")?;
                    safe_relative(name)?;
                    ensure(!name.contains('/'), "command log escapes original attempt")?;
                    let bytes = value["bytes"]
                        .as_u64()
                        .ok_or("normal command log size absent")?;
                    let sha = value["sha256"]
                        .as_str()
                        .ok_or("normal command log digest absent")?;
                    ensure(
                        bytes <= JSON_LIMIT && fs::valid_digest(sha),
                        "normal command log pin invalid",
                    )?;
                    let p =
                        actual_evidence(pin.path.parent().unwrap().join(name), bytes, sha.into())?;
                    held.push(HeldInput::open(p, JSON_LIMIT)?);
                }
                let tool = &event["tool"];
                ensure(
                    tool["path"] == "/usr/bin/dpkg",
                    "normal transaction used another executable",
                )?;
                let p = actual_evidence(
                    PathBuf::from("/usr/bin/dpkg"),
                    tool["bytes"].as_u64().ok_or("dpkg bytes absent")?,
                    tool["sha256"].as_str().ok_or("dpkg hash absent")?.into(),
                )?;
                held.push(HeldInput::open(p, MATERIAL_LIMIT)?);
            }
        }
    }
    Ok(())
}

fn canonical(value: &Value) -> Result<Vec<u8>> {
    let mut bytes = serde_json::to_vec(value)?;
    bytes.push(b'\n');
    Ok(bytes)
}
fn actual_rows(packages: &[Package]) -> Result<Value> {
    let mut values = BTreeMap::new();
    for p in packages {
        ensure(
            p.package.is_ascii()
                && p.version.is_ascii()
                && values
                    .insert(
                        p.package.clone(),
                        json!({"version":p.version,"status":p.status}),
                    )
                    .is_none(),
            "normal package state names are ambiguous",
        )?;
    }
    Ok(serde_json::to_value(values)?)
}
fn baseline<'a>(
    input: &SourceReceipt,
    proofs: &'a [RecordedJson],
) -> Result<(SourceReceipt, Vec<Package>)> {
    let document = selected_pin(
        proofs,
        input
            .baseline_receipt
            .as_ref()
            .ok_or("original baseline absent")?,
    )?;
    let baseline = complete_native::source(document)?;
    ensure(
        baseline.stage == "baseline"
            && input.bootstrap_receipt == baseline.bootstrap_receipt
            && input.package_transactions == baseline.package_transactions,
        "installed source baseline transaction authority changed",
    )?;
    let packages = complete_native::baseline_package_proofs(&baseline, proofs)?;
    Ok((baseline, packages))
}

fn events(
    input: &SourceReceipt,
    proofs: &[RecordedJson],
    r: &Release,
    before: &[Package],
    after: &[Package],
) -> Result<Value> {
    let install = read_installation(input, proofs)?;
    let attempt = &install.attempts[0];
    ensure(
        Some(&attempt.release) == input.native_release.as_ref(),
        "attempt release differs",
    )?;
    let directory = attempt
        .snapshot
        .path
        .parent()
        .ok_or("normal attempt directory absent")?;
    let name = directory
        .file_name()
        .and_then(|s| s.to_str())
        .ok_or("normal attempt name invalid")?;
    let prefix = format!("{}-", r.release_id);
    let suffix = name
        .strip_prefix(&prefix)
        .ok_or("normal attempt release name differs")?;
    ensure(
        suffix.len() == 16
            && suffix
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
            && directory.parent()
                == Some(
                    input
                        .root
                        .path
                        .join("var/lib/droidloom-maintenance/native-transactions")
                        .as_path(),
                )
            && attempt.snapshot.path == directory.join("SNAPSHOT.json"),
        "normal attempt is not beneath its original complete root",
    )?;
    let snap = selected_pin(proofs, &attempt.snapshot)?.validate()?;
    ensure(
        snap["schema"] == "droidloom-normal-native-snapshot-v1"
            && snap["release_id"] == r.release_id
            && snap["closure_sha256"] == r.closure_sha256
            && snap["root_identity"] == json!([input.root.device, input.root.inode])
            && snap["all_packages"] == actual_rows(before)?,
        "normal transaction snapshot authority differs",
    )?;
    let mut ordered = Vec::new();
    let mut prior = 0u64;
    for (i, pin) in attempt.events.iter().enumerate() {
        ensure(
            pin.path == directory.join(format!("EVENT-{:04}.json", i + 1)),
            "normal event sequence path differs",
        )?;
        let event = selected_pin(proofs, pin)?.validate()?;
        let time = event["monotonic_ns"]
            .as_u64()
            .ok_or("normal event time absent")?;
        ensure(
            event["schema"] == "droidloom-normal-native-event-v1"
                && event["attempt"] == name
                && event["sequence"] == Value::from(i + 1)
                && time > prior,
            "normal durable event identity/sequence changed",
        )?;
        prior = time;
        ordered.push(event);
    }
    let stages: Vec<_> = ordered
        .iter()
        .map(|e| e["stage"].as_str().unwrap_or(""))
        .collect();
    let mut expected = vec!["snapshot-complete"];
    if stages.get(1) == Some(&"service-policy-prepared") {
        expected.push("service-policy-prepared");
    }
    expected.extend([
        "service-policy-held",
        "unpack-new-prerequisite-started",
        "unpack-new-prerequisite-ended",
        "configure-new-prerequisite-started",
        "configure-new-prerequisite-ended",
        "unpack-new-started",
        "unpack-new-ended",
        "configure-new-started",
        "configure-new-ended",
        "verified-new",
        "service-policy-restored",
        "normal-native-installed",
    ]);
    ensure(
        stages == expected,
        "normal installation contains missing, failed, rollback, or extra stages",
    )?;
    let event =
        |stage: &str| -> &Value { &ordered[stages.iter().position(|s| *s == stage).unwrap()] };
    let guard = event("service-policy-held");
    ensure(
        guard["guard"]["sha256"] == fs::digest(b"#!/bin/sh\nexit 101\n")
            && guard["guard"]["node"]["uid"] == 0
            && guard["guard"]["node"]["gid"] == 0
            && guard["guard"]["node"]["mode"] == 0o755
            && guard["guard"]["node"]["nlink"] == 1
            && event("service-policy-restored")["owned_guard_removed"] == guard["guard"]["owned"],
        "normal cold service guard differs or was not restored",
    )?;
    for (stage, count) in [
        ("unpack-new-prerequisite-started", 1),
        ("unpack-new-started", 14),
    ] {
        let unpack = event(stage)["arguments"]
            .as_array()
            .ok_or("normal unpack argv absent")?;
        ensure(
            unpack.len() == count + 2 && unpack[0] == "--no-triggers" && unpack[1] == "--unpack",
            "normal unpack package count/flags differ",
        )?;
        let mut fds = BTreeSet::new();
        for value in &unpack[2..] {
            let fd = value
                .as_str()
                .and_then(|s| s.strip_prefix("/proc/self/fd/"))
                .and_then(|s| s.parse::<u32>().ok())
                .ok_or("normal unpack did not use held package FD")?;
            ensure(
                fd >= 3 && fds.insert(fd),
                "normal package descriptor aliases or is invalid",
            )?;
        }
    }
    ensure(
        event("configure-new-prerequisite-started")["arguments"]
            == json!(["--configure", "libsystemd-shared:amd64"]),
        "normal systemd pre-dependency configuration differs",
    )?;
    let expected_config: Vec<_> = std::iter::once("--configure".to_owned())
        .chain(
            r.package_names
                .iter()
                .filter(|n| *n != "libsystemd-shared")
                .map(|n| format!("{n}:amd64")),
        )
        .collect();
    ensure(
        event("configure-new-started")["arguments"] == serde_json::to_value(expected_config)?,
        "normal configuration package closure differs",
    )?;
    for stage in [
        "unpack-new-prerequisite-ended",
        "configure-new-prerequisite-ended",
        "unpack-new-ended",
        "configure-new-ended",
    ] {
        ensure(
            event(stage)["exit_code"] == 0
                && event(stage)["tool"]["path"] == "/usr/bin/dpkg"
                && event(stage)["tool"]["bytes"]
                    .as_u64()
                    .is_some_and(|n| n > 0)
                && event(stage)["tool"]["sha256"]
                    .as_str()
                    .is_some_and(fs::valid_digest),
            "actual normal dpkg command did not succeed",
        )?;
    }
    let verified = event("verified-new");
    let rows: BTreeMap<_, _> = r
        .package_roles
        .iter()
        .map(|r| {
            (
                r.role.clone(),
                json!({"version":r.new_version,"status":"ii "}),
            )
        })
        .collect();
    ensure(
        verified["actual_package_rows"] == serde_json::to_value(rows)?
            && verified["package_state_sha256"] == fs::digest(&canonical(&actual_rows(after)?)?)
            && verified["configuration_semantics_preserved"] == true
            && verified["private_metadata_unchanged"] == true
            && verified["whole_payload_members"]
                .as_u64()
                .is_some_and(|n| n > 0)
            && event("normal-native-installed")["members"] == verified["whole_payload_members"]
            && event("normal-native-installed")["runtime_qualified"] == false
            && event("normal-native-installed")["physical_activation"] == false,
        "normal installation does not bind the complete actual final package state",
    )?;
    Ok(snap)
}

pub(super) fn packages(input: &SourceReceipt, proofs: &[RecordedJson]) -> Result<Vec<Package>> {
    let (_, before) = baseline(input, proofs)?;
    let r = release(selected_pin(
        proofs,
        input
            .native_release
            .as_ref()
            .ok_or("normal native release absent")?,
    )?)?;
    components(proofs, input.native_release.as_ref().unwrap(), &r)?;
    let package_value = selected_pin(proofs, &input.packages)?.validate()?;
    ensure(
        package_value["schema"] == "droidloom.actual-native-package-state.v1"
            && package_value["configured"] == true
            && package_value["original_requested_count"] == 971
            && package_value["original_requested_versions_exact"] == false,
        "installed package roster is not the actual complete query",
    )?;
    let after: Vec<Package> = serde_json::from_value(package_value["packages"].clone())?;
    let mut expected = complete_native::package_map(&before)?;
    for role in &r.package_roles {
        let key = format!("{}:amd64", role.name);
        ensure(
            expected.get(&key) == Some(&role.old_version),
            "normal native original version/architecture differs",
        )?;
        expected.insert(key, role.new_version.clone());
    }
    ensure(
        complete_native::package_map(&after)? == expected,
        "normal installed source changed a package outside the exact native release",
    )?;
    events(input, proofs, &r, &before, &after)?;
    Ok(after)
}

fn conffiles(status: &str, r: &Release) -> Result<BTreeSet<String>> {
    let names: BTreeSet<_> = r.package_names.iter().map(String::as_str).collect();
    let mut result = BTreeSet::from([
        "/etc/gdm3/greeter.dconf-defaults".to_owned(),
        "/etc/X11/default-display-manager".to_owned(),
        "/etc/systemd/system/display-manager.service".to_owned(),
    ]);
    for paragraph in status.split("\n\n") {
        let name = paragraph.lines().find_map(|l| l.strip_prefix("Package: "));
        if !name.is_some_and(|n| names.contains(n)) {
            continue;
        }
        let mut active = false;
        for line in paragraph.lines() {
            if !line.starts_with(' ') {
                active = line == "Conffiles:";
                continue;
            }
            if !active {
                continue;
            }
            let row: Vec<_> = line.split_whitespace().collect();
            ensure(
                row.len() == 2
                    && row[0].starts_with("/etc/")
                    && row[1].len() == 32
                    && row[1].bytes().all(|b| b.is_ascii_hexdigit()),
                "normal selected conffile declaration differs",
            )?;
            paths::parts(row[0])?;
            result.insert(row[0].to_owned());
        }
    }
    Ok(result)
}
fn inventory(
    proofs: &[RecordedJson],
    release_pin: &EvidencePin,
    role: &Role,
    kind: &str,
) -> Result<Inventory> {
    let pair = match kind {
        "old" => &role.old,
        "new" => &role.new,
        _ => return Err("native inventory direction differs".into()),
    };
    let raw = named_proof(proofs, release_pin, &pair.inventory)?.validate()?;
    let value: Inventory = if role.source == "systemd" {
        let v: SystemdInventory = serde_json::from_value(raw)?;
        ensure(
            v.schema == "droidloom-normal-native-package-inventory-v1"
                && v.kind == kind
                && v.package == role.name
                && v.archive["bytes"] == pair.package.bytes
                && v.archive["sha256"] == pair.package.sha256,
            "normal systemd inventory source/package differs",
        )?;
        Inventory {
            control: v.control,
            payload: v.payload,
            runtime_elfs: Vec::new(),
        }
    } else {
        serde_json::from_value(raw)?
    };
    ensure(
        !value.payload.is_empty()
            && value.payload.len() <= 65536
            && value.control.contains_key("control"),
        "normal native inventory lacks complete payload/control",
    )?;
    let mut paths_seen = BTreeSet::new();
    for row in &value.payload {
        safe_relative(&row.path)?;
        ensure(
            paths_seen.insert(&row.path)
                && ["0", "1", "2", "5"].contains(&row.kind.as_str())
                && row.mode & !0o7777 == 0
                && row.bytes <= MATERIAL_LIMIT,
            "normal native inventory path/type/mode differs",
        )?;
        if row.kind == "0" {
            ensure(
                row.sha256.as_deref().is_some_and(fs::valid_digest) && row.target.is_none(),
                "normal regular payload lacks exact content",
            )?;
        }
    }
    for elf in &value.runtime_elfs {
        let found = value
            .payload
            .iter()
            .find(|p| p.path == elf.path)
            .ok_or("normal runtime ELF outside payload")?;
        ensure(
            elf.kind == "0"
                && found.kind == "0"
                && elf.sha256 == found.sha256
                && elf.bytes == found.bytes
                && elf.mode == found.mode
                && elf.uid == found.uid
                && elf.gid == found.gid,
            "normal runtime ELF inventory changed",
        )?;
    }
    Ok(value)
}
fn configured_mode(role: &Role, row: &Payload) -> Result<u32> {
    if role.name == "systemd"
        && ["etc/credstore", "etc/credstore.encrypted"].contains(&row.path.as_str())
    {
        ensure(
            row.kind == "5" && row.mode == 0o755 && row.uid == 0 && row.gid == 0,
            "normal stock credential directory declaration changed",
        )?;
        return Ok(0o700);
    }
    Ok(row.mode)
}
fn same_config(
    entry: Option<&&crate::complete_snapshot::CompleteEntry>,
    old: &Value,
) -> Result<()> {
    if old["absent"] == true {
        return ensure(entry.is_none(), "normal removed conffile reappeared");
    }
    let entry = entry.ok_or("normal preserved conffile absent")?;
    ensure(
        old["node"]["mode"] == (entry.source.mode & 0o7777)
            && old["node"]["uid"] == entry.source.uid
            && old["node"]["gid"] == entry.source.gid,
        "normal preserved conffile metadata differs",
    )?;
    match &entry.content {
        Content::Regular { sha256 } | Content::Hardlink { sha256, .. } => ensure(
            old["type"] == "0" && old["bytes"] == entry.source.size && old["sha256"] == *sha256,
            "normal conffile body was not preserved",
        ),
        Content::Symlink { target } => ensure(
            old["type"] == "2" && old["target"] == *target,
            "normal selection alias changed",
        ),
        Content::Directory => ensure(old["type"] == "5", "normal config object type changed"),
    }
}

fn private_metadata(
    entries: &BTreeMap<&str, &crate::complete_snapshot::CompleteEntry>,
    snapshot: &Value,
) -> Result<()> {
    const PATHS: &[&str] = &[
        "etc/passwd",
        "etc/group",
        "etc/shadow",
        "etc/gshadow",
        "etc/ssh/sshd_config",
        "etc/ssh/ssh_host_ed25519_key",
        "etc/ssh/ssh_host_rsa_key",
        "home",
        "home/alex",
    ];
    let original = snapshot["private_metadata"]
        .as_object()
        .ok_or("normal original metadata custody absent")?;
    ensure(
        original.keys().map(String::as_str).collect::<BTreeSet<_>>()
            == PATHS.iter().copied().collect(),
        "normal private metadata scope differs",
    )?;
    for path in PATHS {
        let old = &original[*path];
        let entry = entries.get(format!("/{path}").as_str());
        if old["absent"] == true {
            ensure(
                entry.is_none(),
                "normal native transaction created a private identity",
            )?;
            continue;
        }
        let entry = entry.ok_or("normal original private object absent")?;
        let id = &entry.source;
        let mtime = id
            .mtime_sec
            .checked_mul(1_000_000_000)
            .and_then(|n| n.checked_add(id.mtime_nsec))
            .ok_or("private timestamp overflow")?;
        let ctime = id
            .ctime_sec
            .checked_mul(1_000_000_000)
            .and_then(|n| n.checked_add(id.ctime_nsec))
            .ok_or("private timestamp overflow")?;
        ensure(
            old["f9"]
                == json!([
                    id.dev, id.ino, id.mode, id.uid, id.gid, id.nlink, id.size, mtime, ctime
                ])
                && old["node"]
                    == json!({"device":id.dev,"inode":id.ino,"mode":id.mode&0o7777,
                "uid":id.uid,"gid":id.gid,"nlink":id.nlink}),
            "original account/SSH/home metadata changed during native installation",
        )?;
        match &entry.content {
            Content::Regular { .. } | Content::Hardlink { .. } => {
                ensure(old["type"] == "0", "private type differs")?
            }
            Content::Directory => ensure(old["type"] == "5", "private type differs")?,
            Content::Symlink { target } => ensure(
                old["type"] == "2" && old["target"] == *target,
                "private alias differs",
            )?,
        }
    }
    Ok(())
}

/// Uses the whole normal root capture, not just ELF projections. Conffiles
/// retain their real pre-transaction semantics, as proven by the original
/// durable snapshot. Only the two stock configured credstore directories have
/// the explicitly source-bound 0755 archive -> 0700 installed rule.
pub(super) fn verify_payload(manifest: &CompleteManifest) -> Result<usize> {
    let input = complete_native::source(&manifest.source)?;
    ensure(
        input.stage == "installed",
        "whole native installed payload requires installed source",
    )?;
    let release_pin = input
        .native_release
        .as_ref()
        .ok_or("native release missing")?;
    let r = release(selected_pin(&manifest.proofs, release_pin)?)?;
    let (_, before) = baseline(&input, &manifest.proofs)?;
    let snap = events(&input, &manifest.proofs, &r, &before, &manifest.packages)?;
    let status = manifest
        .package_status
        .as_ref()
        .ok_or("installed status body absent")?;
    ensure(
        status.len() as u64 == input.dpkg_status.bytes
            && fs::digest(status.as_bytes()) == input.dpkg_status.sha256,
        "installed actual database body differs",
    )?;
    let configs = conffiles(status, &r)?;
    let configured = snap["public_configs"]
        .as_object()
        .ok_or("normal original config custody absent")?;
    ensure(
        configured
            .keys()
            .map(|p| format!("/{p}"))
            .collect::<BTreeSet<_>>()
            == configs,
        "normal preserved conffile scope differs from actual selected package database",
    )?;
    let entries: BTreeMap<_, _> = manifest
        .entries
        .iter()
        .map(|e| (e.path.as_str(), e))
        .collect();
    private_metadata(&entries, &snap)?;
    for (path, old) in configured {
        same_config(entries.get(format!("/{path}").as_str()), old)?;
    }
    let mut count = 0usize;
    for role in &r.package_roles {
        let old = inventory(&manifest.proofs, release_pin, role, "old")?;
        let new = inventory(&manifest.proofs, release_pin, role, "new")?;
        for script in [
            "preinst",
            "postinst",
            "prerm",
            "postrm",
            "conffiles",
            "triggers",
        ] {
            ensure(
                old.control.get(script) == new.control.get(script),
                "normal native maintainer/conffile semantics changed",
            )?;
        }
        if role.name == "systemd" {
            let rule = new
                .payload
                .iter()
                .find(|p| p.path == "usr/lib/tmpfiles.d/credstore.conf")
                .ok_or("normal credential directory rule absent")?;
            ensure(
                rule.kind == "0"
                    && rule.bytes == 474
                    && rule.sha256.as_deref() == Some(CREDSTORE_SHA),
                "normal configured credential directory source differs",
            )?;
        }
        for row in &new.payload {
            let path = format!("/{}", row.path);
            if configs.contains(&path) {
                continue;
            }
            let entry = entries
                .get(path.as_str())
                .ok_or("complete normal package member absent")?;
            ensure(
                entry.source.uid == row.uid
                    && entry.source.gid == row.gid
                    && entry.source.mode & 0o7777 == configured_mode(role, row)?,
                &format!("normal installed member metadata differs: {path}"),
            )?;
            match row.kind.as_str() {
                "0" => ensure(
                    entry.source.size == row.bytes
                        && matches!(&entry.content,Content::Regular{sha256}|Content::Hardlink{sha256,..} if Some(sha256)==row.sha256.as_ref()),
                    &format!("normal installed member body differs: {path}"),
                )?,
                "2" => ensure(
                    matches!(&entry.content,Content::Symlink{target}if Some(target)==row.target.as_ref()),
                    "normal installed alias differs",
                )?,
                "5" => ensure(
                    entry.content == Content::Directory,
                    "normal installed directory differs",
                )?,
                "1" => {
                    let target = row
                        .target
                        .as_ref()
                        .ok_or("normal hardlink target missing")?;
                    safe_relative(target)?;
                    let original = entries
                        .get(format!("/{target}").as_str())
                        .ok_or("normal hardlink target absent")?;
                    ensure(
                        entry.source.dev == original.source.dev
                            && entry.source.ino == original.source.ino
                            && matches!(
                                entry.content,
                                Content::Regular { .. } | Content::Hardlink { .. }
                            ),
                        "normal installed hardlink identity differs",
                    )?;
                }
                _ => return Err("normal special payload refused".into()),
            }
            count += 1;
        }
    }
    let install = read_installation(&input, &manifest.proofs)?;
    let verified = install.attempts[0]
        .events
        .iter()
        .map(|p| selected_pin(&manifest.proofs, p).and_then(RecordedJson::validate))
        .collect::<Result<Vec<_>>>()?
        .into_iter()
        .find(|v| v["stage"] == "verified-new")
        .ok_or("verified normal event absent")?;
    ensure(
        verified["whole_payload_members"] == count,
        "actual complete package member count differs from normal transaction",
    )?;
    Ok(count)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn fixed_normal_native_versions_and_configured_directory_rules_are_closed() {
        assert!(source_versions("systemd").is_ok());
        assert!(source_versions("gdm3").is_ok());
        assert!(source_versions("unreviewed").is_err());
        for path in [
            "../foreign",
            "/etc/passwd",
            "native-five/../x",
            "systemd//x",
        ] {
            assert!(safe_relative(path).is_err());
        }
        let role = Role {
            role: "systemd".into(),
            name: "systemd".into(),
            source: "systemd".into(),
            old_version: "259.9-0ubuntu0.1".into(),
            new_version: "259.9-0ubuntu0.1+p4gentmp1".into(),
            old: Pair {
                package: RelativePin {
                    path: "x".into(),
                    bytes: 1,
                    sha256: "a".repeat(64),
                },
                inventory: RelativePin {
                    path: "y".into(),
                    bytes: 1,
                    sha256: "b".repeat(64),
                },
            },
            new: Pair {
                package: RelativePin {
                    path: "z".into(),
                    bytes: 1,
                    sha256: "c".repeat(64),
                },
                inventory: RelativePin {
                    path: "w".into(),
                    bytes: 1,
                    sha256: "d".repeat(64),
                },
            },
        };
        let mut row = Payload {
            path: "etc/credstore".into(),
            kind: "5".into(),
            bytes: 0,
            uid: 0,
            gid: 0,
            mode: 0o755,
            sha256: None,
            target: None,
        };
        assert_eq!(configured_mode(&role, &row).unwrap(), 0o700);
        row.path = "etc/other".into();
        assert_eq!(configured_mode(&role, &row).unwrap(), 0o755);
        row.path = "etc/credstore".into();
        row.mode = 0o777;
        assert!(configured_mode(&role, &row).is_err());
    }
    #[test]
    #[ignore = "requires the actual frozen root-protected normal fifteen-package material"]
    fn actual_frozen_normal_release_and_every_payload_inventory() {
        let path = Path::new(
            "/var/lib/droidloom-qualification/p4-native-fifteen-release-516eec-r1/NATIVE-RELEASE.json",
        );
        let pin = actual_evidence(
            path.to_path_buf(),
            26397,
            "a949654c4e3ad4e3b8a8df9e7dfcbc077042fb81061c9c08f28221aedc19c792".into(),
        )
        .unwrap();
        let mut held = Vec::new();
        let mut proofs = Vec::new();
        let r = release_materials(&pin, &mut held, &mut proofs).unwrap();
        assert_eq!(r.package_roles.len(), 15);
        assert_eq!(r.files.len(), 108);
        let mut total = 0;
        for role in &r.package_roles {
            for kind in ["old", "new"] {
                let v = inventory(&proofs, &pin, role, kind).unwrap();
                total += v.payload.len();
                if role.name == "libselinux1" && kind == "new" {
                    assert!(v.runtime_elfs.iter().any(|p| p.mode == 0o644));
                }
            }
        }
        assert!(total > 3000);
        let original = selected_pin(&proofs, &pin).unwrap().clone();
        for mutate in [0, 1, 2, 3] {
            let mut value = original.validate().unwrap();
            match mutate {
                0 => value["package_roles"][0]["new_version"] = "3.9-4build1+foreign".into(),
                1 => value["files"][0]["sha256"] = "0".repeat(64).into(),
                2 => value["components"]["systemd"]["release_id"] = "0".repeat(64).into(),
                _ => value["normal_archives_verified"] = false.into(),
            }
            let body = String::from_utf8(canonical(&value).unwrap()).unwrap();
            let mut changed = original.clone();
            changed.pin.bytes = body.len() as u64;
            changed.pin.sha256 = fs::digest(body.as_bytes());
            changed.body = body;
            assert!(release(&changed).is_err());
        }
        for file in &mut held {
            file.revalidate().unwrap();
        }
        println!(
            "actual normal release: 108 original files; 15 old/new payload inventories; four source-change refusals; no installation performed"
        );
    }
}
