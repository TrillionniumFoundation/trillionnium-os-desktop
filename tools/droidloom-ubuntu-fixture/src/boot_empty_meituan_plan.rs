//! Derive ordinary EMPTY guest inputs from actual pinned files. This writes
//! comparison configuration only; it never boots a guest or grants acceptance.
use crate::{
    Result,
    boot_files::{self, FilePin},
    ensure, fs,
};
use clap::ValueEnum;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::File,
    io::{Read, Seek, SeekFrom},
    path::{Path, PathBuf},
};

const BASE: &str = "/var/lib/droidloom-qualification";
const MAC: [&str; 5] = [
    "contract.json",
    "manager-label.json",
    "policy.bin",
    "policy-export.bin",
    "derivation.json",
];

#[derive(Clone, Copy, ValueEnum)]
pub enum Phase {
    Native,
    Boot,
    Run,
    Collect,
    Verify,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Inputs {
    schema: String,
    output_directory: PathBuf,
    native_work_directory: PathBuf,
    native_reference: FilePin,
    boot_reference: FilePin,
    collect_reference: FilePin,
    android_reopened: FilePin,
    normal_producer: FilePin,
    // Native planning can precede the real build. All later phases require
    // these actual files; no placeholder digest or old MAC is synthesized.
    release: Option<Release>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Release {
    host_manifest: FilePin,
    host_archive: FilePin,
    mac_release: BTreeMap<String, FilePin>,
    official_apk: FilePin,
}

#[derive(Serialize)]
pub struct ControllerBudget {
    admission_seconds: u64,
    prepare_native_seconds: u64,
    prepare_boot_seconds: u64,
    boot_seconds: u64,
    collect_seconds: u64,
    verify_seconds: u64,
    retirement_margin_seconds: u64,
    pub total_seconds: u64,
    guest: crate::boot_empty_meituan::RunBudget,
}
pub fn controller_budget() -> Result<ControllerBudget> {
    let guest = crate::boot_empty_meituan::run_budget()?;
    let boot_seconds = guest.observation_seconds + guest.shutdown_seconds + 600;
    Ok(ControllerBudget {
        admission_seconds: 300,
        prepare_native_seconds: 1800,
        prepare_boot_seconds: 1800,
        boot_seconds,
        collect_seconds: 1200,
        verify_seconds: 900,
        retirement_margin_seconds: 60,
        total_seconds: 300 + 1800 + 1800 + boot_seconds + 1200 + 900 + 60,
        guest,
    })
}

#[derive(Default)]
struct Sources(BTreeMap<PathBuf, (FilePin, crate::model::Identity, File)>);
impl Sources {
    fn admit(&mut self, pin: &FilePin) -> Result<()> {
        ensure(
            !pin.path.starts_with("/var/lib/droidloom/users"),
            "EMPTY planning never admits a protected original-userdata input",
        )?;
        if let Some((old, _, _)) = self.0.get(&pin.path) {
            return ensure(
                old.bytes == pin.bytes && old.sha256 == pin.sha256,
                "one input path has conflicting whole-byte pins",
            );
        }
        ensure(
            self.0.len() < 128,
            "EMPTY public input closure exceeded its bound",
        )?;
        let file = boot_files::checked_file(pin)?;
        let identity = fs::stat(&file)?;
        ensure(
            identity.nlink == 1 && identity.mode & 0o022 == 0,
            "normal input must be one protected regular file",
        )?;
        self.0
            .insert(pin.path.clone(), (pin.clone(), identity, file));
        Ok(())
    }
    fn json(&mut self, pin: &FilePin, limit: u64) -> Result<Value> {
        ensure(
            pin.bytes > 0 && pin.bytes <= limit,
            "input JSON exceeds its fixed bound",
        )?;
        self.admit(pin)?;
        let (_, before, file) = &self.0[&pin.path];
        let mut reader = file;
        reader.seek(SeekFrom::Start(0))?;
        let mut bytes = Vec::new();
        Read::by_ref(&mut reader)
            .take(limit + 1)
            .read_to_end(&mut bytes)?;
        ensure(
            bytes.len() as u64 == pin.bytes
                && fs::digest(&bytes) == pin.sha256
                && fs::stat(file)? == *before,
            "held JSON source changed during derivation",
        )?;
        Ok(serde_json::from_slice(&bytes)?)
    }
    fn tree(&mut self, value: &Value) -> Result<()> {
        match value {
            Value::Object(fields)
                if fields.contains_key("path")
                    && fields.contains_key("bytes")
                    && fields.contains_key("sha256") =>
            {
                self.admit(&serde_json::from_value::<FilePin>(value.clone())?)?
            }
            Value::Object(fields) => {
                for child in fields.values() {
                    self.tree(child)?;
                }
            }
            Value::Array(items) => {
                for child in items {
                    self.tree(child)?;
                }
            }
            _ => (),
        }
        Ok(())
    }
    fn guard(&self) -> Result<()> {
        for (pin, before, file) in self.0.values() {
            ensure(
                fs::stat(file)? == *before && boot_files::open_pin(pin)?.1 == *before,
                "held or named whole-checked source changed during input derivation",
            )?;
        }
        Ok(())
    }
}

fn workspace(path: &Path) -> Result<()> {
    ensure(
        path.parent() == Some(Path::new(BASE)),
        "EMPTY output must be a direct private qualification child",
    )?;
    let name = path
        .file_name()
        .and_then(|v| v.to_str())
        .ok_or("invalid EMPTY workspace name")?;
    ensure(
        !name.is_empty()
            && name.len() <= 96
            && name
                .bytes()
                .all(|v| v.is_ascii_alphanumeric() || b"-_".contains(&v)),
        "EMPTY workspace name is not canonical",
    )
}
fn absent(path: &Path) -> Result<()> {
    ensure(
        std::fs::symlink_metadata(path).is_err_and(|e| e.kind() == std::io::ErrorKind::NotFound),
        "EMPTY planning requires an unused destination; a failed generation is never replayed",
    )
}
fn uuid(seed: &str, kind: &str) -> String {
    // These UUIDs only distinguish independently produced roots. The live
    // EMPTY capability still requires both actual complete initial image bytes.
    let hash = fs::digest(format!("droidloom.empty-native.v1:{kind}:{seed}").as_bytes());
    format!(
        "{}-{}-4{}-a{}-{}",
        &hash[..8],
        &hash[8..12],
        &hash[13..16],
        &hash[17..20],
        &hash[20..32]
    )
}
fn derive_native(input: &Inputs, sources: &mut Sources) -> Result<Value> {
    let original = sources.json(&input.native_reference, 65536)?;
    let mut native: crate::boot_complete::CompleteNativePlan = serde_json::from_value(original)?;
    ensure(
        native.schema == "droidloom.complete-ubuntu-native-boot-plan.v1"
            && native.work_directory != input.native_work_directory
            && native.fixture_root != input.native_work_directory.join("root"),
        "independent EMPTY native root cannot reuse a prior mutable root",
    )?;
    crate::boot_complete::admitted_manifest(&native.fixture_manifest)?;
    sources.admit(&native.fixture_manifest)?;
    let name = fs::absolute_string(&input.native_work_directory)?;
    let digest = fs::digest(name.as_bytes());
    native.work_directory = input.native_work_directory.clone();
    native.native.hostname = format!("p4-empty-meituan-{}", &digest[..12]);
    native.native.root_filesystem_uuid = uuid(&name, "root");
    native.native.network_connection_uuid = uuid(&name, "network");
    Ok(serde_json::to_value(native)?)
}

/// Permit only relocation of the very same whole normal Android members.
fn relocated(original: &Value, current: &Value) -> Result<usize> {
    match (original, current) {
        (Value::Object(a), Value::Object(_))
            if a.contains_key("path") && a.contains_key("bytes") && a.contains_key("sha256") =>
        {
            let left: FilePin = serde_json::from_value(original.clone())?;
            let right: FilePin = serde_json::from_value(current.clone())?;
            ensure(
                left.bytes == right.bytes && left.sha256 == right.sha256,
                "reopened Android changed a complete normal member",
            )?;
            Ok(usize::from(left.path != right.path))
        }
        (Value::Object(a), Value::Object(b)) => {
            ensure(
                a.keys().eq(b.keys()),
                "reopened Android changes semantic fields",
            )?;
            let mut n = 0;
            for (key, value) in a {
                n += relocated(value, &b[key])?;
            }
            Ok(n)
        }
        (Value::Array(a), Value::Array(b)) => {
            ensure(a.len() == b.len(), "reopened Android changes an array")?;
            let mut n = 0;
            for (a, b) in a.iter().zip(b) {
                n += relocated(a, b)?;
            }
            Ok(n)
        }
        _ => {
            ensure(
                original == current,
                "reopened Android changed a normal value",
            )?;
            Ok(0)
        }
    }
}
fn actual_pin(path: PathBuf, sources: &mut Sources) -> Result<(FilePin, Value)> {
    let pin = boot_files::pin_file(&path)?;
    let value = sources.json(&pin, 8 * 1024 * 1024)?;
    Ok((pin, value))
}
fn native_receipt(input: &Inputs, sources: &mut Sources) -> Result<FilePin> {
    let generated = derive_native(input, sources)?;
    let (plan, body) = actual_pin(input.output_directory.join("NATIVE-PLAN.json"), sources)?;
    ensure(
        body == generated,
        "previous normal native plan differs from this derivation",
    )?;
    let (pin, value) = actual_pin(
        input.native_work_directory.join("NATIVE-PREPARED.json"),
        sources,
    )?;
    ensure(
        value["schema"] == crate::boot_complete::PREPARED_SCHEMA
            && value["input_sha256"] == plan.sha256
            && value["work_directory"] == serde_json::to_value(&input.native_work_directory)?
            && value["complete_fixture_manifest"] == generated["fixture_manifest"],
        "actual normal native producer has not prepared this independent input",
    )?;
    Ok(pin)
}
fn derive_boot(input: &Inputs, sources: &mut Sources) -> Result<Value> {
    let release = input.release.as_ref().ok_or(
        "actual new host-stage, five-file MAC and official APK release are still required",
    )?;
    ensure(
        release
            .mac_release
            .keys()
            .map(String::as_str)
            .collect::<BTreeSet<_>>()
            == BTreeSet::from(MAC),
        "EMPTY requires the complete actual normal five-file MAC release",
    )?;
    let native = native_receipt(input, sources)?;
    let reference = sources.json(&input.boot_reference, 1024 * 1024)?;
    let mut boot: crate::boot::BootPlan = serde_json::from_value(reference.clone())?;
    ensure(
        boot.android.calibrate
            && boot.android.persistent_data.is_none()
            && boot.android.mac_release.is_none()
            && boot.android.empty_meituan_diagnostic.is_none()
            && boot.public_apks.is_none(),
        "reference is not the original public calibration material",
    )?;
    let reopened = sources.json(&input.android_reopened, 1024 * 1024)?;
    ensure(
        reopened["schema"] == "pocket4.normal-android-input-reopen.v1"
            && reopened["original_boot_plan"] == serde_json::to_value(&input.boot_reference)?
            && relocated(&reference["android"], &reopened["android"])? == 13,
        "reopened normal Android must retain the exact selected thirteen members",
    )?;
    boot.android = serde_json::from_value(reopened["android"].clone())?;
    boot.native_receipt = native;
    boot.host_manifest = release.host_manifest.clone();
    boot.host_archive = release.host_archive.clone();
    boot.android.calibrate = false;
    boot.android.mac_release = Some(release.mac_release.clone());
    boot.android.empty_meituan_diagnostic = Some(crate::boot_empty_meituan::Inputs {
        official_apk: release.official_apk.clone(),
    });
    crate::boot::admit_boot_mode(&boot, true)?;
    let manifest: crate::boot_host::HostManifest =
        serde_json::from_value(sources.json(&release.host_manifest, 1024 * 1024)?)?;
    crate::boot_host::validate_manifest(&manifest)?;
    let value = serde_json::to_value(boot)?;
    sources.tree(&value)?;
    Ok(value)
}

pub fn run(path: &Path, expected: &str, phase: Phase) -> Result<()> {
    ensure(
        rustix::process::geteuid().is_root(),
        "normal EMPTY planner writes only root-private configurations",
    )?;
    let input: Inputs = fs::read_json(&fs::absolute_string(path)?, expected)?;
    ensure(
        input.schema == "droidloom.empty-meituan-input-plan.v1",
        "unsupported independent EMPTY planning schema",
    )?;
    workspace(&input.output_directory)?;
    workspace(&input.native_work_directory)?;
    ensure(
        input.output_directory != input.native_work_directory,
        "planning and native roots must be independent",
    )?;
    ensure(
        input
            .native_work_directory
            .join("boot/empty1/qmp.sock")
            .as_os_str()
            .len()
            < 104,
        "independent EMPTY work name exceeds the actual QMP pathname limit",
    )?;
    let output = fs::Tree::open(&fs::absolute_string(&input.output_directory)?, 0)?;
    let node = fs::stat(&output.root)?;
    ensure(
        node.uid == 0 && node.gid == 0 && node.mode == 0o40700,
        "EMPTY plan output is not root private",
    )?;
    let mut sources = Sources::default();
    let input_pin = boot_files::pin_file(path)?;
    ensure(
        input_pin.sha256 == expected,
        "planning input changed after its original read",
    )?;
    sources.admit(&input_pin)?;
    sources.admit(&input.normal_producer)?;
    let executable = File::open("/proc/self/exe")?;
    ensure(
        fs::stat(&executable)? == sources.0[&input.normal_producer.path].1,
        "plan command must be this actual whole-pinned normal producer",
    )?;
    let budget = controller_budget()?;
    let (filename, command, seconds, value) = match phase {
        Phase::Native => {
            absent(&input.native_work_directory)?;
            (
                "NATIVE-PLAN.json",
                "prepare-complete-native",
                budget.prepare_native_seconds,
                derive_native(&input, &mut sources)?,
            )
        }
        Phase::Boot => (
            "BOOT-PLAN.json",
            "prepare-boot",
            budget.prepare_boot_seconds,
            derive_boot(&input, &mut sources)?,
        ),
        Phase::Run => {
            let (plan, _) =
                actual_pin(input.output_directory.join("BOOT-PLAN.json"), &mut sources)?;
            let (prepared, value) = actual_pin(
                input.native_work_directory.join("boot/BOOT-PREPARED.json"),
                &mut sources,
            )?;
            ensure(
                value["input_sha256"] == plan.sha256
                    && value["android_release"]["empty_meituan_diagnostic"].is_object(),
                "actual prepared EMPTY boot is absent",
            )?;
            (
                "RUN-PLAN.json",
                "boot",
                budget.boot_seconds,
                json!({"schema":"droidloom.full-ubuntu-run-plan.v1",
                "prepared":prepared,"run_name":"empty1","cpus":4,"memory_mib":5120,
                "duration_seconds":budget.guest.observation_seconds,"network":false,"ssh_port":null}),
            )
        }
        Phase::Collect => {
            let mut value = sources.json(&input.collect_reference, 65536)?;
            let expected_keys = BTreeSet::from([
                "schema",
                "ended",
                "collection_name",
                "e2fsck",
                "debugfs",
                "journalctl",
            ]);
            ensure(
                value.as_object().is_some_and(|v| {
                    v.keys().map(String::as_str).collect::<BTreeSet<_>>() == expected_keys
                }) && value["schema"] == "droidloom.full-ubuntu-boot-collect-plan.v1",
                "normal collect reference differs",
            )?;
            let (ended, body) = actual_pin(
                input
                    .native_work_directory
                    .join("boot/empty1/RUN-ENDED.json"),
                &mut sources,
            )?;
            let (prepared, _) = actual_pin(
                input.native_work_directory.join("boot/BOOT-PREPARED.json"),
                &mut sources,
            )?;
            ensure(
                body["prepared"] == serde_json::to_value(prepared)?,
                "ended guest is from another prepared image",
            )?;
            value["ended"] = serde_json::to_value(ended)?;
            value["collection_name"] = "collect1".into();
            sources.tree(&value)?;
            (
                "COLLECT-PLAN.json",
                "collect-boot",
                budget.collect_seconds,
                value,
            )
        }
        Phase::Verify => {
            let (boot, _) =
                actual_pin(input.output_directory.join("BOOT-PLAN.json"), &mut sources)?;
            let (collect, _) = actual_pin(
                input.output_directory.join("COLLECT-PLAN.json"),
                &mut sources,
            )?;
            let (collected, _) = actual_pin(
                input
                    .native_work_directory
                    .join("boot/empty1/collect1/COLLECTED.json"),
                &mut sources,
            )?;
            (
                "VERIFY-PLAN.json",
                "verify-owned-guest",
                budget.verify_seconds,
                json!({
                "schema":"droidloom.owned-full-guest-evidence-plan.v1","boot_plan":boot,"collect_plan":collect,
                "collected":collected,"expected_boot_phase":"android_runtime","verification_name":"verify1"}),
            )
        }
    };
    let destination = input.output_directory.join(filename);
    absent(&destination)?;
    sources.guard()?;
    let digest = fs::write_json(&fs::absolute_string(&destination)?, &value, 0)?;
    let pin = boot_files::pin_file(&destination)?;
    ensure(pin.sha256 == digest, "new plan readback differs")?;
    sources.guard()?;
    println!(
        "{}",
        json!({"plan":pin,"command":[input.normal_producer.path.to_string_lossy(),command,
        "--config",destination.to_string_lossy(),"--config-sha256",digest],"stage_seconds":seconds,
        "controller_budget":budget,"input_sources":sources.0.values().map(|(p,id,_)|json!({"pin":p,"identity":id})).collect::<Vec<_>>(),
        "plans_only":true,"guest_started":false,"runtime_qualified":false,"production_ready":false,"original_data_migration":false})
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn empty_meituan_plan_relocation_cannot_replace_bytes_or_introduce_userdata() {
        let old = json!({"images":{"system":{"path":"/old/system","bytes":10,"sha256":"a".repeat(64)}},"persistent_data":null,"calibrate":true});
        let mut new = old.clone();
        new["images"]["system"]["path"] = "/new/system".into();
        assert_eq!(relocated(&old, &new).unwrap(), 1);
        new["images"]["system"]["sha256"] = "b".repeat(64).into();
        assert!(relocated(&old, &new).is_err());
        new = old.clone();
        new["persistent_data"] = json!({"receipt":"old"});
        assert!(relocated(&old, &new).is_err());
        assert_ne!(uuid("same", "root"), uuid("same", "network"));
    }
    #[test]
    fn empty_meituan_controller_budget_covers_source_windows_without_renewal() -> Result<()> {
        let b = controller_budget()?;
        assert_eq!(b.total_seconds, 8700);
        assert_eq!(
            b.boot_seconds,
            b.guest.observation_seconds + b.guest.shutdown_seconds + 600
        );
        assert!(b.boot_seconds > 2040 && b.total_seconds > 3000);
        Ok(())
    }
    #[test]
    fn empty_meituan_planner_rejects_replaced_and_mutated_held_sources() -> Result<()> {
        use std::io::Write;
        use std::os::unix::fs::PermissionsExt;
        let root = tempfile::tempdir()?;
        let path = root.path().join("source.json");
        std::fs::write(&path, b"{\"real\":1}")?;
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600))?;
        let pin = boot_files::pin_file(&path)?;
        let mut sources = Sources::default();
        assert_eq!(sources.json(&pin, 100)?, json!({"real":1}));
        sources.guard()?;
        let replacement = root.path().join("replacement.json");
        std::fs::write(&replacement, b"{\"real\":1}")?;
        std::fs::rename(&replacement, &path)?;
        assert!(sources.guard().is_err());
        let pin = boot_files::pin_file(&path)?;
        let mut sources = Sources::default();
        sources.admit(&pin)?;
        let mut writer = std::fs::OpenOptions::new().write(true).open(&path)?;
        writer.write_all(b"{\"real\":2}")?;
        writer.sync_all()?;
        assert!(sources.json(&pin, 100).is_err());
        assert!(sources.guard().is_err());
        Ok(())
    }
}
