//! Initial v2 source publication by the actual H2 installed applications owner.
//!
//! The boot selection is the selected runtime configuration. The different
//! leaf selection below is this same verified ELF's compiled preparation
//! catalog. Neither a caller path nor a saved Main record selects either input.
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::os::fd::AsRawFd;
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt, chown};
use std::path::{Path, PathBuf};

use droidloom_supervisor::working_qualification::{
    WorkingForegroundOwner, WorkingLeafManifest, WorkingQualificationOwner, WorkingSourceFilePin,
};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

use super::{FilePin, leaf_adoption, leaf_release, leaf_routes};
use leaf_release::{CLI, CURRENT, Inputs, body, f9};

fn need(value: bool, reason: &str) -> Result<(), String> {
    if value { Ok(()) } else { Err(reason.into()) }
}
fn source_pin(value: &FilePin) -> WorkingSourceFilePin {
    WorkingSourceFilePin {
        path: value.path.clone(),
        bytes: value.bytes,
        sha256: value.sha256.clone(),
    }
}
fn local_pin(value: &WorkingSourceFilePin) -> FilePin {
    FilePin {
        path: value.path.clone(),
        bytes: value.bytes,
        sha256: value.sha256.clone(),
    }
}
fn reference(path: PathBuf, raw: &[u8]) -> FilePin {
    FilePin {
        path,
        bytes: raw.len() as u64,
        sha256: hex::encode(Sha256::digest(raw)),
    }
}
fn successor(
    before: &Value,
    owner: &WorkingForegroundOwner,
    selection: &WorkingSourceFilePin,
    release: &FilePin,
) -> Result<Value, String> {
    let mut after = before.clone();
    let map = after
        .as_object_mut()
        .ok_or("whole original CURRENT is not an object")?;
    map.insert(
        "foreground_owner".into(),
        serde_json::to_value(owner).map_err(|e| e.to_string())?,
    );
    map.insert(
        "application_qualification_preparations".into(),
        serde_json::to_value(selection).map_err(|e| e.to_string())?,
    );
    map.insert(
        "native_application_leaf_release".into(),
        serde_json::to_value(release).map_err(|e| e.to_string())?,
    );
    Ok(after)
}

/// Only the real, zero-argument WorkingQualificationOwner can supply this
/// borrowed permit. All comparison fields are derived from that owner and
/// independently compiled source. This is not a JSON admission endpoint.
pub(super) fn publish(owner: &mut WorkingQualificationOwner) -> Result<FilePin, String> {
    let mut permit = owner.begin_initial_source()?;
    let origin = permit.origin().clone();
    origin.validate()?;
    let (selection, catalog) = leaf_routes::compiled_release_sources();
    leaf_routes::validate_selection(&selection)?;

    let mut inputs = Inputs::new();
    inputs.read(&selection.path, Some(&selection), 1024 * 1024, true, false)?;
    let before = permit.original_current();
    let before_pin = FilePin {
        path: before.path.clone(),
        bytes: before.bytes,
        sha256: before.sha256.clone(),
    };
    let before_raw = inputs.read(
        Path::new(CURRENT),
        Some(&before_pin),
        2 * 1024 * 1024,
        false,
        false,
    )?;
    need(
        before_raw == permit.original_current_bytes()
            && inputs.identity(Path::new(CURRENT))? == before.f9,
        "publisher did not retain the same actual pre-lock CURRENT inode and full bytes",
    )?;
    let before_json = leaf_release::json(&before_raw)?;
    let binary = FilePin {
        path: PathBuf::from(CLI),
        bytes: origin.applications.bytes,
        sha256: origin.applications.sha256.clone(),
    };
    inputs.read(Path::new(CLI), Some(&binary), 64 * 1024 * 1024, true, true)?;
    let actual_exe = File::open("/proc/self/exe").map_err(|e| e.to_string())?;
    let exe_identity = f9(&actual_exe.metadata().map_err(|e| e.to_string())?)?;
    need(
        exe_identity == inputs.identity(Path::new(CLI))?
            && hex::encode(Sha256::digest(body(&actual_exe, exe_identity[6])?)) == binary.sha256
            && f9(&actual_exe.metadata().map_err(|e| e.to_string())?)? == exe_identity,
        "initial source publisher is not the actual normal H2 applications ELF",
    )?;

    // These are normal source-only content publications. Their parent .layout
    // and exact root custody use the unchanged legacy publication primitive.
    // The selected runtime JSON is not confused with the compiled leaf selector.
    let catalog_pin = leaf_adoption::content_file("catalogs", catalog.as_bytes())?;
    let before_copy = leaf_adoption::content_file("current-preimages", &before_raw)?;
    let manifest = WorkingLeafManifest {
        schema: "pocket4-native-application-leaf-release-v2".into(),
        protocol: leaf_release::PROTOCOL.into(),
        binary: source_pin(&binary),
        selection: source_pin(&selection),
        catalog: source_pin(&catalog_pin),
        foreground_owner: origin.foreground_owner()?,
        owner_expires_unix_seconds: origin.owner_expires_unix_seconds,
        before_current: before,
        before_current_copy: source_pin(&before_copy),
        source_tree: origin.source_tree.clone(),
        source_commit: origin.source_commit.clone(),
        working_owner: origin,
        runtime_qualified: false,
        production_ready: false,
    };
    manifest.validate()?;
    let mut manifest_raw = serde_json::to_vec(&manifest).map_err(|e| e.to_string())?;
    manifest_raw.push(b'\n');
    need(
        manifest_raw.len() <= 65536,
        "working source manifest exceeds normal bound",
    )?;
    let release = leaf_adoption::content_file("releases", &manifest_raw)?;
    let after = successor(
        &before_json,
        &manifest.foreground_owner,
        &manifest.selection,
        &release,
    )?;
    let mut after_raw = serde_json::to_vec(&after).map_err(|e| e.to_string())?;
    after_raw.push(b'\n');
    need(
        after_raw.len() < 2 * 1024 * 1024,
        "working CURRENT exceeds original whole-body bound",
    )?;
    let parent = Path::new(CURRENT).parent().ok_or("CURRENT parent absent")?;
    let temporary = parent.join(format!(
        ".working-native-source-{}-{}.new",
        std::process::id(),
        release.sha256
    ));
    inputs.guard()?;
    let anchored_temporary = inputs.anchored(&temporary)?;
    let anchored_current = inputs.anchored(Path::new(CURRENT))?;
    let mut file = OpenOptions::new()
        .write(true)
        .read(true)
        .create_new(true)
        .mode(0o600)
        .custom_flags(0x20000)
        .open(&anchored_temporary)
        .map_err(|e| e.to_string())?;
    file.write_all(&after_raw)
        .and_then(|()| file.sync_all())
        .map_err(|e| e.to_string())?;
    chown(
        format!("/proc/self/fd/{}", file.as_raw_fd()),
        Some(1000),
        Some(1000),
    )
    .map_err(|e| e.to_string())?;
    file.set_permissions(fs::Permissions::from_mode(0o600))
        .map_err(|e| e.to_string())?;
    file.sync_all().map_err(|e| e.to_string())?;
    let temporary_identity = f9(&file.metadata().map_err(|e| e.to_string())?)?;
    need(
        f9(&fs::symlink_metadata(&temporary).map_err(|e| e.to_string())?)? == temporary_identity
            && f9(&fs::symlink_metadata(&anchored_temporary).map_err(|e| e.to_string())?)?
                == temporary_identity
            && body(&file, after_raw.len() as u64)? == after_raw,
        "working CURRENT temporary inode or whole body changed",
    )?;
    // No partial field patch and no synthetic preimage: both actual original
    // lock OFDs, the retained old inode and full body are checked before CAS.
    inputs.guard()?;
    permit.guard_before_cas()?;
    fs::rename(&anchored_temporary, &anchored_current).map_err(|e| e.to_string())?;
    inputs.sync_parent(Path::new(CURRENT))?;
    let mut readback = Inputs::new();
    let after_pin = reference(CURRENT.into(), &after_raw);
    let actual = readback.read(
        Path::new(CURRENT),
        Some(&after_pin),
        2 * 1024 * 1024,
        false,
        false,
    )?;
    need(
        actual == after_raw
            && leaf_release::json(&actual)? == after
            && readback.identity(Path::new(CURRENT))?
                == f9(&file.metadata().map_err(|e| e.to_string())?)?,
        "initial working CURRENT full readback/inode differs",
    )?;
    readback.read(&release.path, Some(&release), 65536, true, false)?;
    readback.read(&catalog_pin.path, Some(&catalog_pin), 65536, true, false)?;
    readback.read(&selection.path, Some(&selection), 1024 * 1024, true, false)?;
    readback.read(
        &before_copy.path,
        Some(&before_copy),
        2 * 1024 * 1024,
        true,
        false,
    )?;
    readback.read(Path::new(CLI), Some(&binary), 64 * 1024 * 1024, true, true)?;
    readback.guard()?;
    let retained = permit.finish_after_cas()?;
    need(
        local_pin(&retained) == release,
        "actual owner retained a different committed source publication",
    )?;
    Ok(release)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn working_source_successor_preserves_every_unrelated_current_field() {
        let before = json!({
            "untouched": {"enabled": true, "count": 1},
            "foreground_owner": {"old": true},
            "application_qualification_preparations": null,
            "native_application_leaf_release": null
        });
        let owner = WorkingForegroundOwner {
            acquisition: "normal".into(),
            acquisition_id: "a".repeat(32),
            active_until_utc: "2026-11-27T00:00:00Z".into(),
            generation: "b".repeat(64),
            name: "source".into(),
            scope: "candidate".into(),
        };
        let selected = WorkingSourceFilePin {
            path: "/selection".into(),
            bytes: 4,
            sha256: "c".repeat(64),
        };
        let release = FilePin {
            path: "/release".into(),
            bytes: 8,
            sha256: "d".repeat(64),
        };
        let expected = successor(&before, &owner, &selected, &release).unwrap();
        assert_eq!(
            expected["foreground_owner"],
            serde_json::to_value(owner).unwrap()
        );
        assert_eq!(
            expected["application_qualification_preparations"],
            serde_json::to_value(selected).unwrap()
        );
        assert_eq!(
            expected["native_application_leaf_release"],
            serde_json::to_value(release).unwrap()
        );
        assert!(
            successor(
                &json!([]),
                &WorkingForegroundOwner {
                    acquisition: "n".into(),
                    acquisition_id: "i".into(),
                    active_until_utc: "t".into(),
                    generation: "g".into(),
                    name: "n".into(),
                    scope: "s".into()
                },
                &WorkingSourceFilePin {
                    path: "/s".into(),
                    bytes: 1,
                    sha256: "a".repeat(64)
                },
                &FilePin {
                    path: "/r".into(),
                    bytes: 1,
                    sha256: "b".repeat(64)
                }
            )
            .is_err()
        );
        let keys = before
            .as_object()
            .unwrap()
            .keys()
            .cloned()
            .collect::<Vec<_>>();
        assert_eq!(
            expected
                .as_object()
                .unwrap()
                .keys()
                .cloned()
                .collect::<Vec<_>>(),
            keys
        );
        assert_eq!(expected["untouched"], before["untouched"]);
        assert_ne!(
            expected["untouched"]["enabled"],
            expected["untouched"]["count"]
        );
    }
}
