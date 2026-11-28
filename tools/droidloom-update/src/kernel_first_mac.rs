//! Stage the five files from an independently pinned capture of the selected board.
use crate::{coherent_images, util::*};
use droidloom_contracts::mac_release::{MAX_ENCODED, NAMES, Release};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, fs, path::Path};

const BOARD_LOCK: &[u8] = include_bytes!(
    "../../../android/framework/droidloom-readiness/board-policy/pocket4-board-inputs.lock.json"
);

fn fixed_digest(v: &Value) -> bool {
    v.as_str().is_some_and(|s| {
        s.len() == 64
            && s.bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    })
}

fn sha(b: &[u8]) -> String {
    hex::encode(Sha256::digest(b))
}

fn validate(files: &[Vec<u8>], cohort: &str, runtime: &str) -> Result<()> {
    let contract: Value = serde_json::from_slice(&files[0])?;
    let manager: Value = serde_json::from_slice(&files[1])?;
    let derivation: Value = serde_json::from_slice(&files[4])?;
    let lock: Value = serde_json::from_slice(BOARD_LOCK)?;
    if contract["schema"] != 5
        || contract["scope"] != "droidloom_linux_android_mac_v5"
        || contract["context_routing"] != "selinux_first_kernel_early_android_v1"
        || manager["schema"] != "droidloom-original-systemd-label-v1"
        || manager["original_server_context"] != "u:object_r:p4_linux_manager_socket_initial_t:s0"
        || derivation["scope"] != "android_kernel_first_mac_observation_v1"
        || derivation["schema"] != 1
        || derivation["board_lock_sha256"] != sha(BOARD_LOCK)
        || derivation["kernel_named_create_checks"] != 7
        || derivation["original_four_images_read"] != 4
        || derivation["loader_role"] != "u:r:droidloom_policy_loader:s0"
        || derivation["manager_role"] != "u:system_r:init_t:s0"
        || derivation["android_business_qualified"] != false
        || contract["active_lsms"] != lock["kernel"]["lsm"]
        || contract["kernel_notes_bytes"] != derivation["kernel_notes_bytes"]
        || contract["kernel_notes_sha256"] != derivation["kernel_notes_sha256"]
        || !fixed_digest(&contract["kernel_notes_sha256"])
        || !fixed_digest(&manager["manager_elf_sha256"])
        || !fixed_digest(&manager["labeler_elf_sha256"])
        || manager["manager_elf_bytes"]
            .as_u64()
            .is_none_or(|n| !(64..=64 * 1024 * 1024).contains(&n))
        || manager["labeler_elf_bytes"]
            .as_u64()
            .is_none_or(|n| !(64..=64 * 1024 * 1024).contains(&n))
        || contract["kernel_notes_bytes"]
            .as_u64()
            .is_none_or(|n| !(1..=1024 * 1024).contains(&n))
        || derivation["selinux"]["enforcing"] != 1
        || derivation["selinux"]["policyload"] != 1
        || derivation["selinux"]["version"] != 1
        || derivation["selinux"]["deny_unknown"] != 1
        || derivation["selinux"]["sequence"]
            .as_u64()
            .is_none_or(|v| v & 1 != 0)
        || derivation["apparmor_revision"]
            .as_u64()
            .is_none_or(|v| v == 0)
        || contract["kernel_release"] != lock["kernel"]["release"]
        || contract["policy_input_bytes"] != lock["files"]["joint.policy"]["size"]
        || contract["policy_input_sha256"] != lock["files"]["joint.policy"]["sha256"]
    {
        return fail(
            "capture does not match the kernel-first board, installation, or enforcing boot",
        );
    }
    for doc in [&contract, &manager, &derivation] {
        if doc["base_cohort_sha256"] != cohort
            || doc["runtime_manifest_sha256"] != runtime
            || doc["policy_input_bytes"] != files[2].len()
            || doc["policy_input_sha256"] != sha(&files[2])
            || doc["policy_export_bytes"] != files[3].len()
            || doc["policy_export_sha256"] != sha(&files[3])
        {
            return fail(
                "board capture documents differ from their exact selected policy/firmware",
            );
        }
    }
    let roles = &lock["files"]["ubuntu-apparmor.profiles"]["board_profiles"];
    for (key, role) in [
        ("apparmor_loader_policy_sha256", "droidloom-policy-loader"),
        (
            "apparmor_android_policy_sha256",
            "droidloom-production-android",
        ),
        (
            "apparmor_broker_policy_sha256",
            "droidloom-production-broker",
        ),
    ] {
        if roles[role]["kernel_profile_sha256"]
            .as_str()
            .is_none_or(|s| s.len() != 64)
            || contract[key] != roles[role]["kernel_profile_sha256"]
        {
            return fail("kernel-exported AppArmor identity differs from board release");
        }
    }
    if contract["derivation_sha256"] != sha(&files[4])
        || contract["derivation_bytes"] != files[4].len()
        || manager["manager_elf_sha256"] != derivation["manager_elf_sha256"]
        || manager["manager_elf_bytes"] != derivation["manager_elf_bytes"]
        || manager["labeler_elf_sha256"] != derivation["labeler_elf_sha256"]
        || manager["labeler_elf_bytes"] != derivation["labeler_elf_bytes"]
    {
        return fail("original executables or sealed derivation were replaced");
    }
    Ok(())
}

pub fn stage(
    capture: &Path,
    capture_sha256: &str,
    cohort: &str,
    runtime: &str,
    destination: &Path,
) -> Result<Value> {
    coherent_images::ordinary_absolute(destination, false)?;
    let size = fs::symlink_metadata(capture)?.len();
    if !(1..=MAX_ENCODED).contains(&size) {
        return fail("bounded genuine kernel-first capture required");
    }
    let raw = coherent_images::read_release_input(capture, size, capture_sha256)?;
    let release: Release = serde_json::from_slice(&raw)?;
    let files = release.files(cohort, runtime)?;
    let provenance: Value = serde_json::from_slice(&files[4])?;
    if provenance["boot_id"] != release.calibration_boot_id
        || provenance["systemd_invocation_id"] != release.systemd_invocation_id
    {
        return fail("calibration boot or systemd invocation differs from the observed provenance");
    }
    validate(&files, cohort, runtime)?;
    let parent = destination
        .parent()
        .filter(|p| p.is_dir())
        .ok_or("existing release output parent required")?;
    let staging = tempfile::Builder::new()
        .prefix(".kernel-first-mac-")
        .tempdir_in(parent)?;
    let relative = Path::new("etc/droidloom/host-mac");
    let mut hashes = BTreeMap::new();
    for (name, data) in NAMES.iter().zip(&files) {
        let file = staging.path().join(relative).join(name);
        durable_write(&file, data)?;
        mode(&file, 0o400)?;
        hashes.insert(*name, sha(data));
    }
    sync_tree(staging.path())?;
    if let Err(error) = coherent_images::official_base::rename_new(staging.path(), destination) {
        if !destination.is_dir() {
            return Err(error);
        }
    }
    let dir = destination.join(relative);
    coherent_images::ordinary_absolute(&dir, true)?;
    if fs::read_dir(&dir)?.count() != 5 {
        return fail("existing output contains a different board release");
    }
    for (name, data) in NAMES.iter().zip(&files) {
        use std::os::unix::fs::PermissionsExt;
        let target = dir.join(name);
        if fs::symlink_metadata(&target)?.permissions().mode() & 0o7777 != 0o400 {
            return fail("existing board release file permissions changed");
        }
        if coherent_images::read_release_input(&target, data.len() as u64, &hashes[name])? != *data
        {
            return fail("existing output differs from the captured board release");
        }
    }
    fs::File::open(parent)?.sync_all()?;
    Ok(
        json!({"schema":1,"cohort":cohort,"runtime_manifest_sha256":runtime,
        "capture_sha256":capture_sha256,"root":destination,"files":hashes,
        "production_selected":false,"android_business_qualified":false}),
    )
}
