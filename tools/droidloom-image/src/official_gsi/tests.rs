use super::*;
use flate2::{Compression, write::DeflateEncoder};
use std::os::unix::fs::symlink;

fn fixture(root: &Path) -> (PathBuf, Profile) {
    let mut profile = reviewed_profile().unwrap();
    let mut archive = Vec::new();
    for member in &mut profile.archive_members {
        let body = format!("synthetic ordinary control for {}\n", member.name).into_bytes();
        let mut encoder = DeflateEncoder::new(Vec::new(), Compression::default());
        encoder.write_all(&body).unwrap();
        let compressed = encoder.finish().unwrap();
        member.local_header_offset = archive.len() as u64;
        member.compressed_bytes = compressed.len() as u64;
        member.bytes = body.len() as u64;
        member.sha256 = hex::encode(Sha256::digest(&body));
        let mut header = [0u8; 30];
        header[..4].copy_from_slice(b"PK\x03\x04");
        header[4..6].copy_from_slice(&20u16.to_le_bytes());
        header[8..10].copy_from_slice(&8u16.to_le_bytes());
        header[18..22].copy_from_slice(&(compressed.len() as u32).to_le_bytes());
        header[22..26].copy_from_slice(&(body.len() as u32).to_le_bytes());
        header[26..28].copy_from_slice(&(member.name.len() as u16).to_le_bytes());
        archive.extend_from_slice(&header);
        archive.extend_from_slice(member.name.as_bytes());
        archive.extend_from_slice(&compressed);
    }
    profile.archive_bytes = archive.len() as u64;
    profile.archive_sha256 = hex::encode(Sha256::digest(&archive));
    let path = root.join("control.zip");
    fs::write(&path, archive).unwrap();
    (path, profile)
}

#[test]
fn original_binary_preparation_preserves_members_without_vendor_or_runtime_credit() {
    let directory = tempfile::tempdir().unwrap();
    let (archive, profile) = fixture(directory.path());
    let output = directory.path().join("prepared");
    let result = prepare_with_profile(&archive, &output, &profile, "synthetic-control").unwrap();
    for member in &profile.archive_members {
        let path = output.join(&member.output);
        assert_eq!(fs::metadata(&path).unwrap().len(), member.bytes);
        assert_eq!(
            hex::encode(Sha256::digest(fs::read(path).unwrap())),
            member.sha256
        );
    }
    assert!(!output.join("images/vendor.img").exists());
    assert!(!output.join("images/product.img").exists());
    assert!(!output.join("images/system_ext.img").exists());
    let report = serde_json::to_value(result).unwrap();
    assert_eq!(report["binary_inputs_verified"], true);
    for field in [
        "vendor_compatibility_qualified",
        "source_revision_equivalence_qualified",
        "avb_signature_qualified",
        "runtime_qualified",
        "production_ready",
    ] {
        assert_eq!(report[field], false, "{field}");
    }
    assert_eq!(
        report["schema"],
        "droidloom-prepared-official-gsi-binary-v1"
    );
}

#[test]
fn official_entry_rejects_synthetic_archive_even_with_an_edited_source_lock() {
    let directory = tempfile::tempdir().unwrap();
    let (archive, _) = fixture(directory.path());
    fs::write(
        directory.path().join("source-lock-x86_64.json"),
        br#"{"aosp_ci_base":{"build_id":"CP3A.260905.010","artifact_sha256":"edited"}}"#,
    )
    .unwrap();
    let output = directory.path().join("prepared");
    assert!(prepare_official_gsi(&archive, &output).is_err());
    assert!(!output.exists());
}

#[test]
fn mismatched_archive_and_member_hashes_never_publish() {
    for which in 0..2 {
        let directory = tempfile::tempdir().unwrap();
        let (archive, mut profile) = fixture(directory.path());
        if which == 0 {
            profile.archive_sha256 = "0".repeat(64);
        } else {
            profile.archive_members[0].sha256 = "0".repeat(64);
        }
        let output = directory.path().join("prepared");
        assert!(prepare_with_profile(&archive, &output, &profile, "control").is_err());
        assert!(!output.exists());
        assert_eq!(fs::read_dir(directory.path()).unwrap().count(), 1);
    }
}

#[test]
fn input_links_alias_parents_and_replacements_are_rejected() {
    let directory = tempfile::tempdir().unwrap();
    let (archive, profile) = fixture(directory.path());
    let alias = directory.path().join("alias.zip");
    symlink(&archive, &alias).unwrap();
    let output = directory.path().join("prepared");
    assert!(prepare_with_profile(&alias, &output, &profile, "control").is_err());
    fs::remove_file(&alias).unwrap();
    fs::hard_link(&archive, &alias).unwrap();
    assert!(prepare_with_profile(&archive, &output, &profile, "control").is_err());
    fs::remove_file(&alias).unwrap();
    let held = open_absolute(&archive, false).unwrap();
    let before = identity(&held.metadata().unwrap()).unwrap();
    let renamed = directory.path().join("previous.zip");
    fs::rename(&archive, &renamed).unwrap();
    fs::copy(&renamed, &archive).unwrap();
    assert!(require_original(&held, &archive, &before).is_err());
    let parent_alias = directory.path().join("parent-link");
    symlink(directory.path(), &parent_alias).unwrap();
    assert!(
        prepare_with_profile(&archive, &parent_alias.join("out"), &profile, "control").is_err()
    );
    assert!(!output.exists());
}

#[test]
fn existing_files_directories_and_dangling_output_links_are_preserved() {
    for which in 0..3 {
        let directory = tempfile::tempdir().unwrap();
        let (archive, profile) = fixture(directory.path());
        let output = directory.path().join("prepared");
        match which {
            0 => fs::write(&output, b"original").unwrap(),
            1 => fs::create_dir(&output).unwrap(),
            _ => symlink("absent", &output).unwrap(),
        }
        let before = identity(&fs::symlink_metadata(&output).unwrap()).unwrap();
        assert!(prepare_with_profile(&archive, &output, &profile, "control").is_err());
        assert_eq!(
            identity(&fs::symlink_metadata(output).unwrap()).unwrap(),
            before
        );
    }
}

#[test]
fn malformed_header_and_expansion_overflow_leave_no_output() {
    for which in 0..3 {
        let directory = tempfile::tempdir().unwrap();
        let (archive, mut profile) = fixture(directory.path());
        let mut body = fs::read(&archive).unwrap();
        match which {
            0 => body[6] = 1,     // An encrypted entry is not the reviewed stream.
            1 => body[30] = b'X', // Same length, foreign member name.
            _ => {
                profile.archive_members[0].bytes -= 1;
                body[22..26]
                    .copy_from_slice(&(profile.archive_members[0].bytes as u32).to_le_bytes());
            }
        }
        fs::write(&archive, &body).unwrap();
        profile.archive_sha256 = hex::encode(Sha256::digest(&body));
        let output = directory.path().join("prepared");
        assert!(prepare_with_profile(&archive, &output, &profile, "control").is_err());
        assert!(!output.exists());
        assert_eq!(fs::read_dir(directory.path()).unwrap().count(), 1);
    }
}
