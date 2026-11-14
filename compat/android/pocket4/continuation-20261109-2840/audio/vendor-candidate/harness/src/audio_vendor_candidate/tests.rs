use super::*;
use flate2::{Compression, write::DeflateEncoder};
use std::os::unix::fs::symlink;
use tempfile::TempDir;

// Synthetic containers exercise packaging boundaries only. Their dummy payload
// bytes must never acquire signature, filesystem, ABI or runtime qualification.
struct Fixture {
    root: TempDir,
    apex: std::path::PathBuf,
    terminal: std::path::PathBuf,
    destination: std::path::PathBuf,
    work: std::path::PathBuf,
}

fn crc(bytes: &[u8]) -> u32 {
    let mut value = !0u32;
    for &byte in bytes {
        value ^= u32::from(byte);
        for _ in 0..8 {
            value = (value >> 1) ^ (0xedb88320 & 0u32.wrapping_sub(value & 1));
        }
    }
    !value
}

fn short(raw: &mut Vec<u8>, value: u16) {
    raw.extend_from_slice(&value.to_le_bytes());
}
fn word(raw: &mut Vec<u8>, value: u32) {
    raw.extend_from_slice(&value.to_le_bytes());
}

fn archive(entries: &[(String, Vec<u8>, u16)]) -> Vec<u8> {
    let mut raw = Vec::new();
    let mut central = Vec::new();
    for (name, data, method) in entries {
        let compressed = if *method == 8 {
            let mut encoder = DeflateEncoder::new(Vec::new(), Compression::default());
            encoder.write_all(data).unwrap();
            encoder.finish().unwrap()
        } else {
            data.clone()
        };
        let offset = raw.len() as u32;
        word(&mut raw, 0x04034b50);
        short(&mut raw, 20);
        short(&mut raw, 0);
        short(&mut raw, *method);
        word(&mut raw, 0);
        word(&mut raw, crc(data));
        word(&mut raw, compressed.len() as u32);
        word(&mut raw, data.len() as u32);
        short(&mut raw, name.len() as u16);
        short(&mut raw, 0);
        raw.extend_from_slice(name.as_bytes());
        raw.extend_from_slice(&compressed);
        word(&mut central, 0x02014b50);
        short(&mut central, 20);
        short(&mut central, 20);
        short(&mut central, 0);
        short(&mut central, *method);
        word(&mut central, 0);
        word(&mut central, crc(data));
        word(&mut central, compressed.len() as u32);
        word(&mut central, data.len() as u32);
        short(&mut central, name.len() as u16);
        short(&mut central, 0);
        short(&mut central, 0);
        short(&mut central, 0);
        short(&mut central, 0);
        word(&mut central, 0);
        word(&mut central, offset);
        central.extend_from_slice(name.as_bytes());
    }
    let offset = raw.len() as u32;
    let size = central.len() as u32;
    raw.extend_from_slice(&central);
    word(&mut raw, 0x06054b50);
    short(&mut raw, 0);
    short(&mut raw, 0);
    short(&mut raw, entries.len() as u16);
    short(&mut raw, entries.len() as u16);
    word(&mut raw, size);
    word(&mut raw, offset);
    short(&mut raw, 0);
    raw
}

fn entries(package: &str) -> Vec<(String, Vec<u8>, u16)> {
    let mut protobuf = vec![10, package.len() as u8];
    protobuf.extend_from_slice(package.as_bytes());
    protobuf.extend_from_slice(&[16, 1]);
    vec![
        ("apex_manifest.pb".into(), protobuf, 0),
        (
            "apex_pubkey".into(),
            b"synthetic-test-public-key".to_vec(),
            0,
        ),
        (
            "AndroidManifest.xml".into(),
            b"synthetic-binary-xml".to_vec(),
            0,
        ),
        (
            "apex_payload.img".into(),
            b"synthetic-unqualified-payload".to_vec(),
            0,
        ),
    ]
}

impl Fixture {
    fn new() -> Self {
        let root = tempfile::tempdir().unwrap();
        let work = root.path().join("work");
        let apex = work
            .join("android-audio-closure-out/target/product/droidloom_x86_64")
            .join(VENDOR_PATH);
        fs::create_dir_all(apex.parent().unwrap()).unwrap();
        fs::write(&apex, archive(&entries(PACKAGE))).unwrap();
        let terminal = root.path().join("terminal.json");
        let destination = root.path().join("candidate");
        Self {
            root,
            apex,
            terminal,
            destination,
            work,
        }
    }

    fn record(&self) -> Value {
        let raw = fs::read(&self.apex).unwrap();
        let argv = json!([
            "/qualified/tools/droidloom-update",
            "--source",
            "/qualified/recipe",
            "-j6",
            "audio-apex-build",
            "--work",
            self.work
        ]);
        let input_ref = json!({"path": "/synthetic/non-authoritative/input.json", "bytes": 1,
                              "sha256": "1".repeat(64)});
        json!({"schema": "pocket4-audio-desktop-normal-full-build-v1",
            "state": "BUILT_PENDING_PAYLOAD_AND_COMPILED_QUALIFICATION",
            "build_success": true, "owned_retirement_complete": true, "input_after_qualified": true,
            "source_projection_restored": true, "resource_gate_passed": true, "owned_work_budget_passed": true,
            "errors": [], "signals": [], "source_project_count": 430,
            "argv": argv,
            "configuration": input_ref, "source_qualification": input_ref,
            "materialized_manifest_before": input_ref, "materialized_manifest_after": input_ref,
            "normal_build": {"name": "normal-full-audio-apex", "owned_retirement_complete": true,
                "errors": [], "lifecycle": {"returncode": 0}, "argv": argv},
            "whole_apex": {"path": self.apex, "bytes": raw.len(), "sha256": hex::encode(Sha256::digest(&raw)),
                "identity": file_identity(&fs::metadata(&self.apex).unwrap()).unwrap()},
            "complete_apex_qualified": true, "runtime_qualified": true, "production_ready": true})
    }

    fn freeze(&self, record: Value) -> String {
        let raw = serde_json::to_vec(&record).unwrap();
        fs::write(&self.terminal, &raw).unwrap();
        hex::encode(Sha256::digest(&raw))
    }

    fn stage(&self) -> Result<Value> {
        stage(
            &self.terminal,
            &self.freeze(self.record()),
            &self.destination,
        )
    }
    fn no_receipt(&self) {
        assert!(!self.destination.join("CANDIDATE.json").exists());
    }
}

#[test]
fn stages_only_vendor_path_and_never_inherits_readiness_claims() {
    let f = Fixture::new();
    let result = f.stage().unwrap();
    assert_eq!(
        fs::read(f.destination.join("payload").join(VENDOR_PATH)).unwrap(),
        fs::read(&f.apex).unwrap()
    );
    assert_eq!(fs::read_dir(&f.destination).unwrap().count(), 2);
    assert_eq!(
        fs::read_dir(f.destination.join("payload")).unwrap().count(),
        1
    );
    assert_eq!(
        fs::read_dir(f.destination.join("payload/vendor/apex"))
            .unwrap()
            .count(),
        1
    );
    assert_eq!(result["state"], "UNQUALIFIED_VENDOR_AUDIO_CANDIDATE");
    for key in [
        "complete_apex_qualified",
        "compiled_elf_qualified",
        "apex_signatures_qualified",
        "vintf_qualified",
        "runtime_qualified",
        "production_ready",
    ] {
        assert_eq!(result[key], false, "{key}");
    }
    for key in [
        "system_overrides",
        "system_ext_overrides",
        "product_overrides",
    ] {
        assert_eq!(result[key], json!([]));
    }
    assert_eq!(
        result["recorded_normal_full_inputs"]["configuration"],
        f.record()["configuration"]
    );
    assert_eq!(
        result["recorded_normal_full_inputs"]["referenced_input_files_reverified_by_this_tool"],
        false
    );
}

#[test]
fn source_only_terminal_cannot_be_promoted_to_full_build() {
    let f = Fixture::new();
    let source = json!({"schema": "audio-original-sdk-normal-reconcile-v1",
        "state": "SOURCE_RECONCILED_AND_NORMAL_VERIFIED", "source_materialization_verified": true,
        "source_commit": "557bff5c84eef7eea9af4533ac7391e3ae676d0f", "builds_started": 0});
    assert!(stage(&f.terminal, &f.freeze(source), &f.destination).is_err());
    assert!(!f.destination.exists());
}

#[test]
fn incorrect_terminal_digest_fails_before_creating_output() {
    let f = Fixture::new();
    f.freeze(f.record());
    assert!(stage(&f.terminal, &"0".repeat(64), &f.destination).is_err());
    assert!(!f.destination.exists());
}

#[test]
fn rejects_invalid_success_exit_signal_command_and_input_references() {
    for mode in 0..6 {
        let f = Fixture::new();
        let mut record = f.record();
        match mode {
            0 => record["build_success"] = json!(1),
            1 => record["normal_build"]["lifecycle"]["returncode"] = json!(1),
            2 => record["normal_build"]["lifecycle"]["returncode"] = json!(false),
            3 => record["pending_signals_at_commit"] = json!([15]),
            4 => record["normal_build"]["argv"][4] = json!("plan"),
            _ => record["configuration"]["sha256"] = json!("not-a-frozen-input"),
        }
        assert!(stage(&f.terminal, &f.freeze(record), &f.destination).is_err());
        assert!(!f.destination.exists());
    }
}

#[test]
fn rejects_system_projection_as_artifact_reference() {
    let f = Fixture::new();
    let mut record = f.record();
    record["whole_apex"]["path"] = json!(f.root.path().join("system/apex/com.android.art.apex"));
    assert!(stage(&f.terminal, &f.freeze(record), &f.destination).is_err());
    assert!(!f.destination.exists());
}

#[test]
fn source_inode_or_bytes_drift_fails_before_output_creation() {
    let f = Fixture::new();
    let digest = f.freeze(f.record());
    OpenOptions::new()
        .append(true)
        .open(&f.apex)
        .unwrap()
        .write_all(b"changed")
        .unwrap();
    assert!(stage(&f.terminal, &digest, &f.destination).is_err());
    assert!(!f.destination.exists());
}

#[test]
fn rejects_source_hardlink_and_symlink() {
    let f = Fixture::new();
    let second = f.root.path().join("hardlink.apex");
    fs::hard_link(&f.apex, &second).unwrap();
    assert!(f.stage().is_err());
    assert!(!f.destination.exists());
    fs::remove_file(second).unwrap();
    let digest = f.freeze(f.record());
    let real = f.apex.with_extension("real");
    fs::rename(&f.apex, &real).unwrap();
    symlink(&real, &f.apex).unwrap();
    assert!(stage(&f.terminal, &digest, &f.destination).is_err());
    assert!(!f.destination.exists());
}

#[test]
fn duplicate_terminal_json_keys_are_rejected() {
    let f = Fixture::new();
    f.freeze(f.record());
    let raw = fs::read_to_string(&f.terminal).unwrap();
    let replaced = format!("{{\"build_success\":false,{}", &raw[1..]);
    fs::write(&f.terminal, &replaced).unwrap();
    assert!(
        stage(
            &f.terminal,
            &hex::encode(Sha256::digest(replaced.as_bytes())),
            &f.destination
        )
        .is_err()
    );
    assert!(!f.destination.exists());
}

#[test]
fn availability_alias_is_not_installed_package_identity() {
    let f = Fixture::new();
    fs::write(&f.apex, archive(&entries("com.android.hardware.audio"))).unwrap();
    assert!(f.stage().is_err());
    f.no_receipt();
}

#[test]
fn duplicate_zip_members_do_not_publish_candidate() {
    let f = Fixture::new();
    let mut data = entries(PACKAGE);
    data.push(data[0].clone());
    fs::write(&f.apex, archive(&data)).unwrap();
    assert!(f.stage().is_err());
    f.no_receipt();
}

#[test]
fn zip_traversal_never_writes_system_paths() {
    let f = Fixture::new();
    let mut data = entries(PACKAGE);
    data.push(("../system/lib64/libbinder.so".into(), vec![1], 0));
    fs::write(&f.apex, archive(&data)).unwrap();
    assert!(f.stage().is_err());
    f.no_receipt();
    assert!(!f.destination.join("system").exists());
}

#[test]
fn compressed_payload_is_not_accepted_as_the_apex_payload_format() {
    let f = Fixture::new();
    let mut data = entries(PACKAGE);
    data[3].2 = 8;
    fs::write(&f.apex, archive(&data)).unwrap();
    assert!(f.stage().is_err());
    f.no_receipt();
}

#[test]
fn rejects_excessive_zip_directory_before_any_metadata_read() {
    let f = Fixture::new();
    let mut raw = fs::read(&f.apex).unwrap();
    let end = raw.len() - 22;
    raw[end + 8..end + 10].copy_from_slice(&5000u16.to_le_bytes());
    raw[end + 10..end + 12].copy_from_slice(&5000u16.to_le_bytes());
    fs::write(&f.apex, raw).unwrap();
    assert!(f.stage().is_err());
    f.no_receipt();
}

#[test]
fn existing_destination_is_preserved() {
    let f = Fixture::new();
    fs::create_dir(&f.destination).unwrap();
    let marker = f.destination.join("existing");
    fs::write(&marker, b"keep").unwrap();
    assert!(f.stage().is_err());
    assert_eq!(fs::read(marker).unwrap(), b"keep");
}

#[test]
fn ancestor_symlink_cannot_redirect_new_files() {
    let f = Fixture::new();
    let outside = f.root.path().join("outside");
    fs::create_dir(&outside).unwrap();
    let alias = f.root.path().join("alias");
    symlink(&outside, &alias).unwrap();
    assert!(stage(&f.terminal, &f.freeze(f.record()), &alias.join("candidate")).is_err());
    assert_eq!(fs::read_dir(outside).unwrap().count(), 0);
}

#[test]
fn writable_parent_is_not_a_trusted_staging_boundary() {
    let f = Fixture::new();
    let parent = f.root.path().join("unsafe");
    fs::create_dir(&parent).unwrap();
    fs::set_permissions(&parent, Permissions::from_mode(0o777)).unwrap();
    assert!(
        stage(
            &f.terminal,
            &f.freeze(f.record()),
            &parent.join("candidate")
        )
        .is_err()
    );
    assert_eq!(fs::read_dir(parent).unwrap().count(), 0);
}

#[test]
fn directory_replacement_is_detected_before_manifest_publication() {
    let f = Fixture::new();
    let moved = f.root.path().join("moved");
    let result = stage_inner(&f.terminal, &f.freeze(f.record()), &f.destination, |path| {
        fs::rename(path, &moved)?;
        fs::create_dir(path)?;
        Ok(())
    });
    assert!(result.is_err());
    f.no_receipt();
    assert!(!moved.join("CANDIDATE.json").exists());
    assert_eq!(fs::read_dir(&f.destination).unwrap().count(), 0);
}

#[test]
fn lzma_metadata_is_refused_without_creating_a_decoder() {
    let f = Fixture::new();
    let mut data = entries(PACKAGE);
    data[0].2 = 14;
    fs::write(&f.apex, archive(&data)).unwrap();
    assert!(f.stage().is_err());
    f.no_receipt();
}
