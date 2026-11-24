//! Validate and stage the normal five-file MAC transport.
//! Calibration records describe a previous observation; they never stand in
//! for the target boot's LoadedPolicyWitness or confer a runtime permit.
use super::{
    Result,
    activation_files::{self as files, FilePin, HeldFile},
};
use droidloom_contracts::mac_release::{LIMITS, MAX_ENCODED, NAMES, Release};
use serde::Deserialize;
use serde_json::{Value, json};
use std::path::Path;
const BOARD: &[u8] = include_bytes!(
    "../../../android/framework/droidloom-readiness/board-policy/pocket4-board-inputs.lock.json"
);

fn require(ok: bool, message: &str) -> Result<()> {
    if ok { Ok(()) } else { Err(message.into()) }
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Declaration {
    schema: u32,
    scope: String,
    base_cohort_sha256: String,
    runtime_manifest_sha256: String,
    kernel_release: String,
    kernel_notes_bytes: u64,
    kernel_notes_sha256: String,
    active_lsms: Vec<String>,
    context_routing: String,
    apparmor_broker_policy_sha256: String,
    apparmor_android_policy_sha256: String,
    apparmor_loader_policy_sha256: String,
    policy_input_bytes: u64,
    policy_input_sha256: String,
    policy_export_bytes: u64,
    policy_export_sha256: String,
    derivation_bytes: u64,
    derivation_sha256: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Manager {
    schema: String,
    base_cohort_sha256: String,
    runtime_manifest_sha256: String,
    policy_input_bytes: u64,
    policy_input_sha256: String,
    policy_export_bytes: u64,
    policy_export_sha256: String,
    manager_elf_bytes: u64,
    manager_elf_sha256: String,
    labeler_elf_bytes: u64,
    labeler_elf_sha256: String,
    original_server_context: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Epoch {
    version: u32,
    sequence: u32,
    policyload: u32,
    enforcing: u32,
    deny_unknown: u32,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Derivation {
    schema: u32,
    scope: String,
    base_cohort_sha256: String,
    runtime_manifest_sha256: String,
    board_lock_sha256: String,
    boot_id: String,
    systemd_invocation_id: String,
    apparmor_revision: u64,
    selinux: Epoch,
    policy_input_bytes: u64,
    policy_input_sha256: String,
    policy_export_bytes: u64,
    policy_export_sha256: String,
    kernel_notes_bytes: u64,
    kernel_notes_sha256: String,
    loader_role: String,
    manager_role: String,
    manager_elf_bytes: u64,
    manager_elf_sha256: String,
    labeler_elf_bytes: u64,
    labeler_elf_sha256: String,
    kernel_named_create_checks: u32,
    original_four_images_read: u32,
    android_business_qualified: bool,
}
struct Admitted {
    files: Vec<Vec<u8>>,
    manager: Manager,
    boot: String,
    invocation: String,
}
fn admit(raw: &[u8], base: &str, runtime: &str, loader: &FilePin) -> Result<Admitted> {
    let release: Release = serde_json::from_slice(raw)?;
    let members = release
        .files(base, runtime)
        .map_err(|e| format!("MAC transport: {e}"))?;
    let declaration: Declaration = serde_json::from_slice(&members[0])?;
    let manager: Manager = serde_json::from_slice(&members[1])?;
    let derivation: Derivation = serde_json::from_slice(&members[4])?;
    let board: Value = serde_json::from_slice(BOARD)?;
    let d = &declaration;
    let m = &manager;
    let r = &derivation;
    require(
        d.schema == 5
            && d.scope == "droidloom_linux_android_mac_v5"
            && d.context_routing == "selinux_first_kernel_early_android_v1"
            && d.base_cohort_sha256 == base
            && d.runtime_manifest_sha256 == runtime
            && board["kernel"]["release"] == d.kernel_release
            && board["kernel"]["lsm"] == serde_json::to_value(&d.active_lsms)?
            && board["files"]["joint.policy"]["size"] == d.policy_input_bytes
            && board["files"]["joint.policy"]["sha256"] == d.policy_input_sha256,
        "MAC contract is not the compiled kernel-first board and selected runtime",
    )?;
    for (raw, size, sha) in [
        (&members[2], d.policy_input_bytes, &d.policy_input_sha256),
        (&members[3], d.policy_export_bytes, &d.policy_export_sha256),
        (&members[4], d.derivation_bytes, &d.derivation_sha256),
    ] {
        require(
            raw.len() as u64 == size && files::valid_digest(sha) && files::digest(raw) == *sha,
            "MAC release member differs from its contract",
        )?;
    }
    for (role, sha) in [
        (
            "droidloom-production-broker",
            &d.apparmor_broker_policy_sha256,
        ),
        (
            "droidloom-production-android",
            &d.apparmor_android_policy_sha256,
        ),
        ("droidloom-policy-loader", &d.apparmor_loader_policy_sha256),
    ] {
        require(
            board["files"]["ubuntu-apparmor.profiles"]["board_profiles"][role]["kernel_profile_sha256"]
                == *sha,
            "MAC release names a different admitted AppArmor role",
        )?;
    }
    require(
        m.schema == "droidloom-original-systemd-label-v1"
            && m.base_cohort_sha256 == base
            && m.runtime_manifest_sha256 == runtime
            && m.policy_input_bytes == d.policy_input_bytes
            && m.policy_input_sha256 == d.policy_input_sha256
            && m.policy_export_bytes == d.policy_export_bytes
            && m.policy_export_sha256 == d.policy_export_sha256
            && m.original_server_context == "u:object_r:p4_linux_manager_socket_initial_t:s0"
            && m.labeler_elf_bytes == loader.bytes
            && m.labeler_elf_sha256 == loader.sha256
            && (64..=64 * 1024 * 1024).contains(&m.manager_elf_bytes)
            && files::valid_digest(&m.manager_elf_sha256),
        "MAC manager declaration is outside the same selected input and normal loader",
    )?;
    require(
        r.schema == 1
            && r.scope == "android_kernel_first_mac_observation_v1"
            && r.base_cohort_sha256 == base
            && r.runtime_manifest_sha256 == runtime
            && r.board_lock_sha256 == files::digest(BOARD)
            && r.boot_id == release.calibration_boot_id
            && r.systemd_invocation_id == release.systemd_invocation_id
            && r.apparmor_revision > 0
            && r.selinux.version == 1
            && r.selinux.sequence % 2 == 0
            && r.selinux.policyload == 1
            && r.selinux.enforcing == 1
            && r.selinux.deny_unknown <= 1
            && r.policy_input_bytes == d.policy_input_bytes
            && r.policy_input_sha256 == d.policy_input_sha256
            && r.policy_export_bytes == d.policy_export_bytes
            && r.policy_export_sha256 == d.policy_export_sha256
            && r.kernel_notes_bytes == d.kernel_notes_bytes
            && r.kernel_notes_sha256 == d.kernel_notes_sha256
            && (16..=1024 * 1024).contains(&r.kernel_notes_bytes)
            && files::valid_digest(&r.kernel_notes_sha256)
            && r.loader_role == "u:r:droidloom_policy_loader:s0"
            && r.manager_role == "u:system_r:init_t:s0"
            && r.manager_elf_bytes == m.manager_elf_bytes
            && r.manager_elf_sha256 == m.manager_elf_sha256
            && r.labeler_elf_bytes == m.labeler_elf_bytes
            && r.labeler_elf_sha256 == m.labeler_elf_sha256
            && r.kernel_named_create_checks == 7
            && r.original_four_images_read == 4
            && !r.android_business_qualified,
        "MAC derivation is not the producer's internally consistent original observation",
    )?;
    Ok(Admitted {
        files: members,
        manager,
        boot: release.calibration_boot_id,
        invocation: release.systemd_invocation_id,
    })
}
pub(super) fn stage(root: &Path, transport: &FilePin, base: &str, runtime: &str) -> Result<Value> {
    let original = HeldFile::open(transport, MAX_ENCODED as u64)?;
    let loader =
        files::pin_file(&root.join("usr/lib/droidloom/production/current/droidloom-host-mac"))?;
    let admitted = admit(
        &original.read_all(MAX_ENCODED as u64)?,
        base,
        runtime,
        &loader,
    )?;
    // The release may be transported, but the actual physical manager ELF must
    // match the normal Ubuntu binary that was captured. No arbitrary replacement.
    let manager = files::pin_file(Path::new("/usr/lib/systemd/systemd"))?;
    require(
        manager.bytes == admitted.manager.manager_elf_bytes
            && manager.sha256 == admitted.manager.manager_elf_sha256,
        "target's normal systemd ELF differs from the MAC release manager",
    )?;
    let manager = HeldFile::open(&manager, 64 * 1024 * 1024)?;
    require(
        manager.identity().uid == 0
            && manager.identity().gid == 0
            && manager.identity().mode & 0o111 != 0,
        "target manager executable is not protected root-owned executable input",
    )?;
    files::ensure_dir(root, "etc/droidloom/host-mac")?;
    let mut rows = Vec::new();
    for ((name, bytes), limit) in NAMES.iter().zip(&admitted.files).zip(LIMITS) {
        require(bytes.len() <= limit, "MAC member exceeded its role limit")?;
        let path = root.join("etc/droidloom/host-mac").join(name);
        rows.push(files::write_new(&path, bytes, 0o400)?);
    }
    original.revalidate()?;
    manager.revalidate()?;
    Ok(
        json!({"transport":transport,"files":rows,"calibration_boot_id":admitted.boot,
    "calibration_systemd_invocation_id":admitted.invocation,
    "target_loaded_policy_observed":false,"target_mac_admitted":false,"production_ready":false}),
    )
}

pub(super) fn verify_staged(
    root: &Path,
    transport: &FilePin,
    base: &str,
    runtime: &str,
) -> Result<()> {
    let original = HeldFile::open(transport, MAX_ENCODED as u64)?;
    let loader =
        files::pin_file(&root.join("usr/lib/droidloom/production/current/droidloom-host-mac"))?;
    let admitted = admit(
        &original.read_all(MAX_ENCODED as u64)?,
        base,
        runtime,
        &loader,
    )?;
    for ((name, bytes), limit) in NAMES.iter().zip(&admitted.files).zip(LIMITS) {
        let pin = FilePin {
            path: root.join("etc/droidloom/host-mac").join(name),
            bytes: bytes.len() as u64,
            sha256: files::digest(bytes),
        };
        let file = HeldFile::open(&pin, limit as u64)?;
        require(
            file.identity().uid == 0
                && file.identity().gid == 0
                && file.identity().mode & 0o7777 == 0o400,
            "staged MAC input no longer has the exact sealed root custody",
        )?;
        files::no_privilege_xattrs(file.file())?;
    }
    let manager = files::pin_file(Path::new("/usr/lib/systemd/systemd"))?;
    require(
        manager.bytes == admitted.manager.manager_elf_bytes
            && manager.sha256 == admitted.manager.manager_elf_sha256,
        "actual target manager changed since the MAC release was staged",
    )?;
    original.revalidate()
}
