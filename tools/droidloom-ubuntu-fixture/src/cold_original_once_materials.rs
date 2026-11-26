//! Actual once preparation: reuse normal package, full ended guest and MAC
//! producers. The returned private object is constructed by these operations,
//! never deserialized from a claimed success record.
use super::{
    OriginalQualificationAuthority, RetirementSource, cell, labels,
    owner::{OriginalOwner, SealedInput},
    state::{Journal, Phase},
};
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    boot_runtime::LabelTools,
    cold_original_data::{self, labels::OriginalLabelSources},
    cold_original_once_recovery::contract::{self, EarlyConfiguration, RecoveryBootSpec},
    ensure, fs,
    model::Identity,
};
use rustix::fs::{FileType, Mode, OFlags};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    cell::RefCell,
    collections::{BTreeMap, BTreeSet},
    fs::File,
    io::Seek,
    os::{fd::AsRawFd, unix::fs::FileExt},
    path::{Path, PathBuf},
    rc::Rc,
};

const BASE: &str = "/var/lib/droidloom-qualification";
const EXT4_SHA: &str = "ad1cf15518ad638e016278312739166b89e88b5c7299caeac41501bcb6da840b";
const DEBUGFS_SHA: &str = "864e1d7b445e7b5bfc831da78330dbcafc590fa82b89ea9de60b7527f989954f";
const PYTHON_SHA: &str = "52e0a13e60a981d8c4b6478be2ba5176f69da07948a056bf49cf6f077e30cb41";
const MAC_NAMES: [&str; 5] = [
    "contract.json",
    "manager-label.json",
    "policy.bin",
    "policy-export.bin",
    "derivation.json",
];

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Plan {
    schema: String,
    candidate_id: String,
    original_boot_id: String,
    normal_producer: FilePin,
    prepared_initramfs: FilePin,
    owned_verification_input: FilePin,
    cold_clone: FilePin,
    original_ext4_metadata: FilePin,
    label_tools: LabelTools,
    collect_at_boot_seconds: u32,
    return_at_boot_seconds: u32,
    watchdog_seconds: u32,
}

struct Guard {
    pin: FilePin,
    file: File,
    identity: Identity,
}
impl Guard {
    fn open(pin: &FilePin) -> Result<Self> {
        let tree = fs::Tree::open("/", 0)?;
        tree.parent(&fs::absolute_string(&pin.path)?)?;
        let (file, identity) = files::open_pin(pin)?;
        ensure(
            identity.uid == 0
                && identity.gid == 0
                && identity.nlink == 1
                && identity.mode & 0o7022 == 0
                && fs::xattrs(&file)?.is_empty(),
            "normal once material lost root custody or acquired extra attributes",
        )?;
        let result = Self {
            pin: pin.clone(),
            file,
            identity,
        };
        result.revalidate()?;
        Ok(result)
    }
    fn revalidate(&self) -> Result<()> {
        (&self.file).rewind()?;
        ensure(
            fs::stat(&self.file)? == self.identity
                && fs::hash(&self.file)? == self.pin.sha256
                && fs::stat(&self.file)? == self.identity
                && fs::Tree::open("/", 0)?.identity(&fs::absolute_string(&self.pin.path)?)?
                    == self.identity,
            "normal once material changed its complete bytes or inode",
        )
    }
    fn command_path(&self) -> Result<String> {
        self.revalidate()?;
        Ok(format!(
            "/proc/{}/fd/{}",
            std::process::id(),
            self.file.as_raw_fd()
        ))
    }
}

/// Retained by the sole authority. In particular the real normal label factory
/// stays alive; its source-pin JSON is not substituted for that custody.
pub(super) struct Materials {
    sources: OriginalLabelSources,
    guards: Vec<Guard>,
    report: SealedInput,
    recovery: RecoveryBootSpec,
    early_configuration: SealedInput,
    recovery_recipe: SealedInput,
    mac_files: Vec<SealedInput>,
}
impl Materials {
    pub(super) fn sources(&self) -> &OriginalLabelSources {
        &self.sources
    }
    pub(super) fn report(&self) -> &FilePin {
        self.report.pin()
    }
    pub(super) fn recipe(&self) -> &FilePin {
        self.recovery_recipe.pin()
    }
    pub(super) fn recovery(&self) -> &RecoveryBootSpec {
        &self.recovery
    }
    pub(super) fn revalidate(&self) -> Result<()> {
        self.sources.revalidate()?;
        self.report.revalidate()?;
        self.early_configuration.revalidate()?;
        self.recovery_recipe.revalidate()?;
        for file in &self.mac_files {
            file.revalidate()?;
        }
        for file in &self.guards {
            file.revalidate()?;
        }
        self.recovery.validate()?;
        Ok(())
    }
}
fn text<'a>(value: &'a Value, key: &str) -> Result<&'a str> {
    value[key]
        .as_str()
        .ok_or_else(|| format!("actual normal evidence lacks {key}").into())
}
fn pin(value: &Value) -> Result<FilePin> {
    Ok(serde_json::from_value(value.clone())?)
}
fn same_bytes(a: &FilePin, b: &FilePin) -> bool {
    a.bytes == b.bytes && a.sha256 == b.sha256
}
fn save(path: &Path, value: &impl Serialize) -> Result<FilePin> {
    let mut bytes = serde_json::to_vec_pretty(value)?;
    bytes.push(b'\n');
    ensure(
        bytes.len() <= 128 * 1024 * 1024,
        "bounded once material record required",
    )?;
    files::write_new(path, &bytes, 0o400)?;
    File::open(path.parent().ok_or("once record parent absent")?)?.sync_all()?;
    let p = files::pin_file(path)?;
    SealedInput::open(&p)?;
    Ok(p)
}

fn compare_candidates(
    candidate: &str,
    normal: &Value,
    owned: &Value,
    producer: &FilePin,
) -> Result<()> {
    let m = &normal["normal_materials"];
    let actual = &owned["actual"];
    ensure(
        normal["schema"] == "droidloom.original-initramfs-readback.v1"
            && owned["schema"] == "droidloom.original-once-owned-readback.v1"
            && actual["schema"] == "droidloom.owned-full-guest-evidence.v1"
            && actual["boot_phase"] == "mac_calibration"
            && actual["actual_native_observations"]["ordinary_guest_shutdown"] == true
            && actual["actual_native_observations"]["calibration_capture_proven"] == true,
        "once preparation requires a fresh actual ordinary calibration from the full guest verifier",
    )?;
    // These values come directly from the freshly run normal/full verifiers,
    // not from caller-supplied pass fields. Byte-bound objects are compared too.
    ensure(
        m["deployment_id"] == candidate
            && fs::valid_digest(candidate)
            && m["root_uuid"] == contract::ROOT_UUID
            && m["original_kernel"] == contract::ORIGINAL_KERNEL
            && m["kernel_release"] == contract::KERNEL
            && m["kernel_sha256"] == contract::KERNEL_SHA
            && actual["shared_kernel"]["sha256"] == contract::KERNEL_SHA
            && actual["shared_kernel"]["bytes"] == 16_855_552
            && actual["cohort"]["sha256"] == m["cohort_sha256"]
            && actual["runtime"]["sha256"] == m["runtime_sha256"],
        "owned calibration and original normal materials are different candidates",
    )?;
    for (normal_key, owned_key) in [
        ("host_source_commit", "source_commit"),
        ("host_source_tree", "source_tree"),
    ] {
        let expected = text(normal, normal_key)?;
        ensure(
            contract::commit(expected)
                && actual[owned_key] == expected
                && normal["normal_producer"][owned_key] == expected,
            "normal host, original initramfs producer and owned calibration source differ",
        )?;
    }
    ensure(
        same_bytes(producer, &pin(&normal["normal_producer"]["producer"])?),
        "the running once helper is not the same normal producer admitted for this candidate",
    )?;
    let packages = m["packages"]
        .as_array()
        .ok_or("normal complete native package array absent")?;
    ensure(
        packages.len() == 24,
        "original normal initramfs package closure changed",
    )?;
    let mut by_name = BTreeMap::new();
    for package in packages {
        let name = text(package, "name")?;
        ensure(
            by_name.insert(name, package).is_none(),
            "duplicate original normal package",
        )?;
    }
    let families = actual["normal_native_packages"]["families"]
        .as_object()
        .ok_or("owned normal native families missing")?;
    ensure(
        families.keys().map(String::as_str).collect::<BTreeSet<_>>()
            == BTreeSet::from(["systemd", "libselinux", "apparmor", "gdm"]),
        "owned native family roster changed",
    )?;
    let mut count = 0;
    for rows in families.values() {
        for row in rows.as_array().ok_or("owned family rows absent")? {
            let old = by_name
                .get(text(row, "package")?)
                .ok_or("owned package is absent from normal original native22")?;
            ensure(
                row["version"] == old["version"] && row["architecture"] == old["architecture"],
                "owned calibration used a different normally built native package version",
            )?;
            count += 1;
        }
    }
    ensure(
        count == 16,
        "owned calibration lacks the complete sixteen installed native packages",
    )
}

fn f9(id: &Identity) -> Value {
    json!([
        id.dev,
        id.ino,
        id.mode,
        id.uid,
        id.gid,
        id.nlink,
        id.size,
        i128::from(id.mtime_sec) * 1_000_000_000 + i128::from(id.mtime_nsec),
        i128::from(id.ctime_sec) * 1_000_000_000 + i128::from(id.ctime_nsec)
    ])
}
fn le32(bytes: &[u8], offset: usize) -> Result<u32> {
    Ok(u32::from_le_bytes(
        bytes
            .get(offset..offset + 4)
            .ok_or("truncated ext4 superblock")?
            .try_into()?,
    ))
}
fn ext4_fields(sb: &[u8]) -> Result<Value> {
    ensure(
        sb.len() == 1024 && &sb[0x38..0x3a] == b"\x53\xef",
        "actual cold clone has no ext4 superblock",
    )?;
    let u = &sb[0x68..0x78];
    let uuid = format!(
        "{}-{}-{}-{}-{}",
        hex::encode(&u[..4]),
        hex::encode(&u[4..6]),
        hex::encode(&u[6..8]),
        hex::encode(&u[8..10]),
        hex::encode(&u[10..])
    );
    Ok(
        json!({"feature_compat":le32(sb,0x5c)?,"feature_incompat":le32(sb,0x60)?,
        "feature_ro_compat":le32(sb,0x64)?,"filesystem_uuid":uuid,
        "filesystem_state":u16::from_le_bytes(sb[0x3a..0x3c].try_into()?)}),
    )
}

fn original_ext4(plan: &Plan, work: &Path) -> Result<(cell::PersistentData, FilePin)> {
    ensure(
        plan.original_ext4_metadata.bytes == 4970 && plan.original_ext4_metadata.sha256 == EXT4_SHA,
        "exact original cold-clone filesystem observation required",
    )?;
    let historical: Value =
        serde_json::from_slice(&files::read_pin(&plan.original_ext4_metadata, 65536)?)?;
    let clone: Value = serde_json::from_slice(&files::read_pin(&plan.cold_clone, 65536)?)?;
    ensure(
        historical["schema"] == "droidloom.original-cold-clone-ext4-metadata.v1"
            && same_bytes(
                &pin(&historical["sources"]["COLD-CLONE-VERIFIED.json"])?,
                &plan.cold_clone,
            ),
        "filesystem metadata lost its exact original clone source",
    )?;
    let debugfs = pin(&historical["tool"])?;
    ensure(
        debugfs.path == Path::new("/usr/sbin/debugfs")
            && debugfs.bytes == 231368
            && debugfs.sha256 == DEBUGFS_SHA,
        "original normal read-only filesystem tool changed",
    )?;
    let debugfs_guard = Guard::open(&debugfs)?;
    let rows = historical["filesystems"]
        .as_array()
        .ok_or("original filesystem metadata absent")?;
    let clone_rows = clone["rows"]
        .as_array()
        .ok_or("original cold clone member array absent")?;
    ensure(
        rows.len() == 2 && clone_rows.len() == 2,
        "exact two original filesystems required",
    )?;
    let mut policies = Vec::new();
    let mut observations = Vec::new();
    for (index, role) in ["data", "metadata"].iter().enumerate() {
        let row = &rows[index];
        let prior = &clone_rows[index];
        let path = PathBuf::from(text(row, "clone_path")?);
        ensure(row["role"]==*role && prior["role"]==*role && prior["clone_path"]==row["clone_path"]
            && prior["clone_f9"]==row["clone_f9_before"] && prior["sha256"]==row["source_sha256"]
            && path==Path::new("/home/alex/work/p4-r88-original-data-compat-qualification-20261124-r1/cold-clone").join(format!("{role}.img")),
            "read-only ext4 observation is not the retained original cold clone")?;
        let tree = fs::Tree::open("/", 0)?;
        let held = tree.file(&fs::absolute_string(&path)?)?;
        let before = fs::stat(&held)?;
        ensure(
            FileType::from_raw_mode(before.mode) == FileType::RegularFile
                && f9(&before) == row["clone_f9_before"],
            "original clone inode changed before bounded metadata read",
        )?;
        let mut sb = [0u8; 1024];
        held.read_exact_at(&mut sb, 1024)?;
        ensure(
            fs::digest(&sb) == row["superblock_sha256"],
            "original clone superblock changed",
        )?;
        let actual = ext4_fields(&sb)?;
        for key in [
            "feature_compat",
            "feature_incompat",
            "feature_ro_compat",
            "filesystem_uuid",
            "filesystem_state",
        ] {
            ensure(
                actual[key] == row[key],
                "actual original filesystem metadata differs from the retained clone",
            )?;
        }
        ensure(
            actual["filesystem_state"] == 1,
            "original cold clone was not cleanly retired",
        )?;
        // The tool reads the held parent's O_RDONLY descriptor, never a newly
        // resolved source pathname, and no write flag or mount is available.
        let command = files::run_logged(
            work,
            &format!("original-{role}-root-inode"),
            &debugfs_guard.command_path()?,
            &[
                "-R".into(),
                "stat <2>".into(),
                format!("/proc/{}/fd/{}", std::process::id(), held.as_raw_fd()),
            ],
            30,
        )?;
        let log = String::from_utf8(files::read_pin(&command.log, 65536)?)?;
        let expected = format!(
            "{}{}",
            text(row, "root_inode_stat_stderr")?,
            text(row, "root_inode_stat_stdout")?
        );
        ensure(
            log == expected,
            "actual original root inode differs from the exact normal debugfs observation",
        )?;
        ensure(
            fs::stat(&held)? == before && tree.identity(&fs::absolute_string(&path)?)? == before,
            "cold clone changed across read-only filesystem metadata observation",
        )?;
        policies.push(json!({"image_bytes":before.size,"filesystem_uuid":actual["filesystem_uuid"],
            "feature_compat":actual["feature_compat"],"feature_incompat":actual["feature_incompat"],
            "feature_ro_compat":actual["feature_ro_compat"],"guest_root_uid":if index==0{1000}else{0},
            "guest_root_gid":if index==0{1000}else{0},"guest_root_mode":if index==0{0o771}else{0o755}}));
        observations.push(json!({"role":role,"clone_path":path,"identity_before":before,
            "identity_after":fs::stat(&held)?,"superblock":actual,"superblock_sha256":fs::digest(&sb),
            "normal_readonly_root_inode":command}));
    }
    let persistent: cell::PersistentData =
        serde_json::from_value(json!({"mode":"original-ext4-v1",
        "data":policies[0],"metadata":policies[1]}))?;
    debugfs_guard.revalidate()?;
    let proof = save(
        &work.join("ORIGINAL-EXT4-READBACK.json"),
        &json!({
        "schema":"droidloom.original-once-ext4-readback.v1","historical":plan.original_ext4_metadata,
        "cold_clone":plan.cold_clone,"normal_tool":debugfs,"normal_tool_identity":debugfs_guard.identity,"filesystems":observations,
        "persistent_data":persistent,"original_image_bodies_opened":false,"runtime_accepted":false}),
    )?;
    Ok((persistent, proof))
}

fn normal_mac(
    sources: &OriginalLabelSources,
    owned: &Value,
    work: &Path,
    guards: &mut Vec<Guard>,
) -> Result<(FilePin, Vec<SealedInput>)> {
    let report = sources.fresh_initramfs_report();
    let m = &report["normal_materials"];
    let actual = &owned["actual"];
    let host_pin = pin(&actual["normal_host_manifest"])?;
    let host: crate::boot_host::HostManifest =
        serde_json::from_slice(&files::read_pin(&host_pin, 1024 * 1024)?)?;
    crate::boot_host::validate_manifest(&host)?;
    ensure(
        host.commit == text(report, "host_source_commit")?
            && host.tree == text(report, "host_source_tree")?,
        "actual normal host export differs from the admitted initramfs host",
    )?;
    let row = host
        .files
        .iter()
        .filter(|f| f.path == "usr/bin/droidloom-update")
        .collect::<Vec<_>>();
    ensure(
        row.len() == 1 && row[0].mode == 0o755,
        "one normal MAC stage executable required",
    )?;
    let root = sources
        .source_pin()
        .path
        .parent()
        .ok_or("normal source record parent absent")?
        .join("normal-host-payload");
    let tool = FilePin {
        path: root.join(&row[0].path),
        bytes: row[0].size,
        sha256: row[0].sha256.clone(),
    };
    guards.push(Guard::open(&host_pin)?);
    let tool_index = guards.len();
    guards.push(Guard::open(&tool)?);
    let capture = pin(&actual["actual_native_observations"]["capture"])?;
    guards.push(Guard::open(&capture)?);
    let output = work.join("five-mac-files");
    let command = files::run_logged(
        work,
        "normal-five-mac-stage",
        &guards[tool_index].command_path()?,
        &[
            "package-kernel-first-mac".into(),
            "--capture".into(),
            fs::absolute_string(&capture.path)?,
            "--capture-sha256".into(),
            capture.sha256.clone(),
            "--base-sha256".into(),
            text(m, "cohort_sha256")?.into(),
            "--runtime-sha256".into(),
            text(m, "runtime_sha256")?.into(),
            "--output".into(),
            fs::absolute_string(&output)?,
        ],
        90,
    )?;
    let directory = output.join("etc/droidloom/host-mac");
    let names = std::fs::read_dir(&directory)?
        .map(|e| {
            Ok(e?
                .file_name()
                .into_string()
                .map_err(|_| "non UTF-8 MAC filename")?)
        })
        .collect::<Result<BTreeSet<_>>>()?;
    ensure(
        names == MAC_NAMES.into_iter().map(String::from).collect(),
        "normal MAC stage produced a different member roster",
    )?;
    let mut sealed = Vec::new();
    for name in MAC_NAMES {
        sealed.push(SealedInput::open(&files::pin_file(&directory.join(name))?)?);
    }
    let source: Value =
        serde_json::from_slice(&files::read_pin(sources.source_pin(), 2 * 1024 * 1024)?)?;
    ensure(
        same_bytes(sealed[2].pin(), &pin(&source["joint_policy"])?),
        "calibrated five-file policy differs from the normal package's complete selected policy",
    )?;
    let receipt = save(
        &work.join("FIVE-MAC-PREPARED.json"),
        &json!({
        "schema":"droidloom.original-once-five-mac-prepared.v1","fresh_owned_receipt":owned["receipt"],
        "actual_capture":capture,"normal_host_manifest":host_pin,"normal_producer":tool,"command":command,
        "files":sealed.iter().map(SealedInput::pin).collect::<Vec<_>>(),
        "host_source_commit":host.commit,"host_source_tree":host.tree,"production_selected":false}),
    )?;
    Ok((receipt, sealed))
}

fn original_grub(work: &Path, guards: &mut Vec<Guard>) -> Result<FilePin> {
    let modules = work.join("cold-source");
    files::private_dir(&modules)?;
    for (name, body) in crate::boot_host::cold_modules::FILES {
        let path = modules.join(
            Path::new(name)
                .file_name()
                .ok_or("normal cold module basename absent")?,
        );
        files::write_new(&path, body, 0o444)?;
        guards.push(Guard::open(&files::pin_file(&path)?)?);
    }
    let python = FilePin {
        path: "/usr/bin/python3.14".into(),
        bytes: 7_477_160,
        sha256: PYTHON_SHA.into(),
    };
    let python_guard = Guard::open(&python)?;
    let mut preserved = Vec::new();
    let mut original_guards = Vec::new();
    for (path, bytes, sha) in [
        (
            "/boot/grub/grub.cfg",
            13794,
            "5a4bc7834d5d60ac57b25182edad08e0cb6f30981e90c049d38335ae07a8cd40",
        ),
        (
            "/boot/grub/grubenv",
            1024,
            "0e8344eff0b558d225092d5ccc2aef2247f81e3d829e2edfe48eb04a19fdbc11",
        ),
        (
            "/boot/vmlinuz-7.0.14-p4cred1",
            17134080,
            "83d50d51be0f6a2d574f6b04ab80205613383c60da7b96788c9c3122efb7b5ad",
        ),
        (
            "/boot/initrd.img-7.0.14-p4cred1",
            92292985,
            "d9fd106a34f018fcf9805ce740b7aa3ab45cf18f3aaa1ba1335be4d4c6f8866d",
        ),
    ] {
        let p = FilePin {
            path: path.into(),
            bytes,
            sha256: sha.into(),
        };
        let guard = Guard::open(&p)?;
        let copy = work.join(format!(
            "ORIGINAL-{}",
            p.path.file_name().unwrap().to_string_lossy()
        ));
        files::copy_pin(&p, &copy, 0o400)?;
        guard.revalidate()?;
        let copied = files::pin_file(&copy)?;
        guards.push(Guard::open(&copied)?);
        preserved.push(json!({"source":p,"identity":guard.identity,"preserved":copied}));
        original_guards.push(guard);
        // grub.cfg/env intentionally evolve only through the later source-owned
        // transaction. Their originals remain independently sealed preimages.
    }
    let script = "import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from release import verify_original_grub_entry,original_grub_entry,ORIGINAL_ROOT_UUID,ORIGINAL_KERNEL;print(json.dumps(verify_original_grub_entry(Path('/boot/grub/grub.cfg').read_bytes(),ORIGINAL_ROOT_UUID,original_grub_entry(ORIGINAL_ROOT_UUID),ORIGINAL_KERNEL),sort_keys=True))";
    let command = files::run_logged(
        work,
        "normal-original-grub-readback",
        &python_guard.command_path()?,
        &[
            "-I".into(),
            "-B".into(),
            "-c".into(),
            script.into(),
            fs::absolute_string(&modules)?,
        ],
        30,
    )?;
    let actual: Value = serde_json::from_slice(&files::read_pin(&command.log, 65536)?)?;
    ensure(
        actual["original_entry"] == contract::ORIGINAL_ENTRY
            && actual["original_default"] == contract::ORIGINAL_ENTRY
            && actual["original_kernel"] == contract::ORIGINAL_KERNEL
            && actual["root_uuid"] == contract::ROOT_UUID,
        "the real original GRUB body does not return to its admitted kernel and root",
    )?;
    for guard in &original_guards {
        guard.revalidate()?;
    }
    python_guard.revalidate()?;
    save(
        &work.join("ORIGINAL-GRUB.json"),
        &json!({"schema":"droidloom.original-once-grub-preimage.v1",
        "original":actual,"normal_parser_command":command,"normal_python":python,"normal_python_identity":python_guard.identity,
        "preserved":preserved,"default_changed":false}),
    )
}

/// No caller can manufacture the result by deserializing any of the receipts.
/// This remains a private preparation entry until the physical dispatcher has
/// every mutation/recovery stage wired to the same retained owner.
pub(super) fn admit(input: &FilePin) -> Result<Rc<OriginalQualificationAuthority>> {
    let input_guard = SealedInput::open(input)?;
    let plan: Plan = serde_json::from_slice(&input_guard.read()?)?;
    ensure(
        plan.schema == "droidloom.original-once-plan.v1"
            && fs::valid_digest(&plan.candidate_id)
            && contract::uuid(&plan.original_boot_id),
        "bounded original once plan identity required",
    )?;
    let owner = OriginalOwner::acquire(&plan.original_boot_id, &plan.candidate_id)?;
    let work = Path::new(BASE).join(format!("original-once-{}", plan.candidate_id));
    files::private_dir(&work)?;
    let work_fd = File::from(rustix::fs::open(
        &work,
        OFlags::PATH | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::empty(),
    )?);
    let work_identity = fs::stat(&work_fd)?;
    let mut guards = Vec::new();
    for p in [
        &plan.normal_producer,
        &plan.prepared_initramfs,
        &plan.owned_verification_input,
        &plan.cold_clone,
        &plan.original_ext4_metadata,
    ] {
        guards.push(Guard::open(p)?);
    }
    let actual_exe = File::open("/proc/self/exe")?;
    ensure(
        fs::stat(&actual_exe)? == guards[0].identity
            && fs::hash(&actual_exe)? == plan.normal_producer.sha256,
        "once preparation is not executing its actual normal producer",
    )?;
    let data_before = cold_original_data::assert_initial_pair_retired(&plan.cold_clone)?;
    let source_work = Path::new(BASE).join(format!(
        "original-initramfs-label-once-{}",
        &plan.candidate_id[..24]
    ));
    let sources =
        OriginalLabelSources::admit(&plan.prepared_initramfs, &plan.label_tools, &source_work)?;
    let owned = crate::boot_owned_evidence::verify_for_original_once(
        &plan.owned_verification_input,
        &work.join("OWNED-VERIFY-INPUTS.json"),
        &format!("once-{}", &plan.candidate_id[..24]),
    )?;
    compare_candidates(
        &plan.candidate_id,
        sources.fresh_initramfs_report(),
        &owned,
        &plan.normal_producer,
    )?;
    let (mac_receipt, mac_files) = normal_mac(&sources, &owned, &work, &mut guards)?;
    let (persistent, ext4_readback) = original_ext4(&plan, &work)?;
    let actual_cell = files::pin_file(Path::new("/etc/droidloom/cell.json"))?;
    let actual_cell_guard = Guard::open(&actual_cell)?;
    let original_cell = work.join("ORIGINAL-CELL.json");
    files::copy_pin(&actual_cell, &original_cell, 0o400)?;
    let original_cell_pin = files::pin_file(&original_cell)?;
    let normal = sources.fresh_initramfs_report();
    let m = &normal["normal_materials"];
    let derived = cell::derive_original(
        &files::read_pin(&original_cell_pin, 1024 * 1024)?,
        text(m, "cohort_sha256")?,
        text(m, "runtime_sha256")?,
        &persistent,
    )?;
    files::write_new(&work.join("CANDIDATE-CELL.json"), &derived.cell, 0o400)?;
    files::write_new(&work.join("SELECTION.json"), &derived.selection, 0o400)?;
    let new_cell = files::pin_file(&work.join("CANDIDATE-CELL.json"))?;
    let selection = files::pin_file(&work.join("SELECTION.json"))?;
    let grub = original_grub(&work, &mut guards)?;
    let report = save(
        &work.join("ADMITTED-MATERIALS.json"),
        &json!({
        "schema":"droidloom.original-once-admitted-materials.v1","input":input,"candidate_id":plan.candidate_id,
        "normal_sources":sources.source_pin(),"normal_initramfs":normal,"fresh_owned":owned,
        "five_mac_files":mac_receipt,"original_data_before":data_before,"original_ext4":ext4_readback,
        "original_grub":grub,"original_cell":original_cell_pin,"actual_original_cell":actual_cell,
        "actual_original_cell_identity":actual_cell_guard.identity,"candidate_cell":new_cell,"selection":selection,
        "preserved_cell_fields":derived.preserved_fields,"changed_cell_fields":derived.changed_fields,
        "actual_owner":owner.evidence(),"runtime_or_migration_accepted":false,"production_ready":false}),
    )?;
    let recovery = RecoveryBootSpec {
        schema: "droidloom.original-once-recovery-boot.v1".into(),
        candidate_id: plan.candidate_id.clone(),
        helper_bytes: plan.normal_producer.bytes,
        helper_sha256: plan.normal_producer.sha256.clone(),
        kernel_release: contract::KERNEL.into(),
        kernel_sha256: contract::KERNEL_SHA.into(),
        kernel_config_sha256: contract::CONFIG_SHA.into(),
        module_relative: contract::MODULE_REL.into(),
        module_bytes: contract::MODULE_BYTES,
        module_sha256: contract::MODULE_SHA.into(),
        watchdog_seconds: plan.watchdog_seconds,
        collect_at_boot_seconds: plan.collect_at_boot_seconds,
        return_at_boot_seconds: plan.return_at_boot_seconds,
        panic_seconds: 10,
    };
    recovery.validate()?;
    let intent = save(
        &work.join("INTENT.json"),
        &json!({"schema":"droidloom.original-once-intent.v1",
        "candidate_id":plan.candidate_id,"work_directory":work,"original_boot_id":plan.original_boot_id,
        "root_uuid":contract::ROOT_UUID,"original_kernel":contract::ORIGINAL_KERNEL,"original_entry":contract::ORIGINAL_ENTRY,
        "public_release_id":m["public_release_id"],"native_release_id":m["native_release_id"],
        "admitted_materials":report,"normal_sources":sources.source_pin(),"normal_producer":plan.normal_producer,
        "original_cell":original_cell_pin,"candidate_cell":new_cell,"selection":selection,"cold_clone":plan.cold_clone,
        "original_grub":grub,"recovery":recovery}),
    )?;
    let early = save(
        &work.join("EARLY.json"),
        &EarlyConfiguration {
            schema: "droidloom.original-once-early.v1".into(),
            intent_sha256: intent.sha256.clone(),
            recovery: recovery.clone(),
        },
    )?;
    let recipe = save(
        &work.join("RECOVERY-RECIPE.json"),
        &json!({"schema":"droidloom.original-once-initramfs-recipe.v1",
        "normal_producer":plan.normal_producer,"base_intent":intent,"early_configuration":early}),
    )?;
    crate::cold_original_once_initramfs::admit_recovery_recipe(&recipe, &plan.normal_producer, m)?;
    sources.revalidate()?;
    for g in &guards {
        g.revalidate()?;
    }
    owner.revalidate()?;
    input_guard.revalidate()?;
    actual_cell_guard.revalidate()?;
    ensure(
        cold_original_data::assert_initial_pair_retired(&plan.cold_clone)?["original"]
            == data_before["original"],
        "original pair changed across normal once preparation",
    )?;
    let mut journal = Journal::create(&work.join("journal"), &plan.candidate_id, &intent.sha256)?;
    journal.append(
        Phase::Admitted,
        &plan.original_boot_id,
        json!({"materials":report,"recovery_recipe":recipe,"actual_owner":owner.evidence()}),
    )?;
    let expected_cell = FilePin {
        path: "/etc/droidloom/cell.json".into(),
        bytes: new_cell.bytes,
        sha256: new_cell.sha256.clone(),
    };
    let admitted_inputs = vec![
        input_guard,
        SealedInput::open(&grub)?,
        SealedInput::open(&ext4_readback)?,
        SealedInput::open(&mac_receipt)?,
        SealedInput::open(sources.source_pin())?,
    ];
    let materials = Materials {
        sources,
        guards,
        report: SealedInput::open(&report)?,
        recovery,
        early_configuration: SealedInput::open(&early)?,
        recovery_recipe: SealedInput::open(&recipe)?,
        mac_files,
    };
    let result = Rc::new(OriginalQualificationAuthority {
        owner: RefCell::new(owner),
        candidate_id: plan.candidate_id,
        work,
        work_fd,
        work_identity,
        intent: SealedInput::open(&intent)?,
        admitted_inputs,
        original_cell: SealedInput::open(&original_cell_pin)?,
        new_cell: SealedInput::open(&new_cell)?,
        expected_cell,
        selection: SealedInput::open(&selection)?,
        cold_clone: SealedInput::open(&plan.cold_clone)?,
        retirement: RefCell::new(RetirementSource::Initial),
        journal: RefCell::new(journal),
        label_plan: RefCell::new(None::<labels::LabelPlanBinding>),
        materials,
    });
    result.verify_current_owner()?;
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn candidate_binding_rejects_claim_only_and_mixed_source_or_native_versions() -> Result<()> {
        let producer = FilePin {
            path: "/a".into(),
            bytes: 2048,
            sha256: "a".repeat(64),
        };
        let mut rows = Vec::new();
        let mut families = serde_json::Map::new();
        for (family, count) in [
            ("systemd", 10),
            ("libselinux", 1),
            ("apparmor", 2),
            ("gdm", 3),
        ] {
            let mut family_rows = Vec::new();
            for i in 0..count {
                let name = format!("{family}{i}");
                rows.push(json!({"name":name,"version":"normal2","architecture":"amd64"}));
                family_rows
                    .push(json!({"package":name,"version":"normal2","architecture":"amd64"}));
            }
            families.insert(family.into(), json!(family_rows));
        }
        for i in 0..8 {
            rows.push(
                json!({"name":format!("extra{i}"),"version":"normal2","architecture":"amd64"}),
            );
        }
        let normal = json!({"schema":"droidloom.original-initramfs-readback.v1","host_source_commit":"b".repeat(40),"host_source_tree":"c".repeat(40),
            "normal_producer":{"source_commit":"b".repeat(40),"source_tree":"c".repeat(40),"producer":producer},
            "normal_materials":{"deployment_id":"d".repeat(64),"root_uuid":contract::ROOT_UUID,"original_kernel":contract::ORIGINAL_KERNEL,
                "kernel_release":contract::KERNEL,"kernel_sha256":contract::KERNEL_SHA,"cohort_sha256":"e".repeat(64),"runtime_sha256":"f".repeat(64),"packages":rows}});
        let owned = json!({"schema":"droidloom.original-once-owned-readback.v1","actual":{"schema":"droidloom.owned-full-guest-evidence.v1",
            "boot_phase":"mac_calibration","actual_native_observations":{"ordinary_guest_shutdown":true,"calibration_capture_proven":true},
            "source_commit":"b".repeat(40),"source_tree":"c".repeat(40),"shared_kernel":{"bytes":16855552,"sha256":contract::KERNEL_SHA},
            "cohort":{"sha256":"e".repeat(64)},"runtime":{"sha256":"f".repeat(64)},"normal_native_packages":{"families":families}}});
        compare_candidates(&"d".repeat(64), &normal, &owned, &producer)?;
        for pointer in [
            "/actual/source_commit",
            "/actual/cohort/sha256",
            "/actual/shared_kernel/sha256",
            "/actual/normal_native_packages/families/systemd/0/version",
        ] {
            let mut bad = owned.clone();
            *bad.pointer_mut(pointer).unwrap() = json!("changed");
            assert!(compare_candidates(&"d".repeat(64), &normal, &bad, &producer).is_err());
        }
        assert!(
            compare_candidates(
                &"d".repeat(64),
                &normal,
                &json!({"success":true}),
                &producer
            )
            .is_err()
        );
        Ok(())
    }
    #[test]
    fn ext4_fields_read_real_endian_slots_and_reject_foreign_magic() -> Result<()> {
        let mut sb = [0u8; 1024];
        sb[0x38..0x3a].copy_from_slice(b"\x53\xef");
        sb[0x3a] = 1;
        sb[0x5c..0x60].copy_from_slice(&4156u32.to_le_bytes());
        sb[0x60..0x64].copy_from_slice(&8898u32.to_le_bytes());
        sb[0x64..0x68].copy_from_slice(&33899u32.to_le_bytes());
        sb[0x68..0x78].copy_from_slice(&hex::decode("c2e0701ff5d5423487a7506b21fe62cb")?);
        let fields = ext4_fields(&sb)?;
        assert_eq!(
            fields["filesystem_uuid"],
            "c2e0701f-f5d5-4234-87a7-506b21fe62cb"
        );
        assert_eq!(fields["feature_ro_compat"], 33899);
        sb[0x38] = 0;
        assert!(ext4_fields(&sb).is_err());
        Ok(())
    }
}
