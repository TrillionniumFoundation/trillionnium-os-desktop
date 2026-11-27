//! Exact public configuration migration for the original Pocket4 account.
//! Producing these bytes cannot activate a cell. The once transaction owns
//! atomic publication, while the normal v4 reader still admits the live cell.
use crate::{Result, ensure, fs};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::BTreeSet;

const FIXED_DATA: &str = "/var/lib/droidloom/users/1000/data";
const FIXED_RUNTIME: &str = "/run/droidloom/cells/u1000";
const ORIGINAL_CELL_SHA: &str = "f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc";
const ORIGINAL_CELL_BYTES: usize = 7656;

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(super) struct PersistentImage {
    image_bytes: u64,
    filesystem_uuid: String,
    feature_compat: u32,
    feature_incompat: u32,
    feature_ro_compat: u32,
    guest_root_uid: u32,
    guest_root_gid: u32,
    guest_root_mode: u32,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(super) struct PersistentData {
    mode: String,
    data: PersistentImage,
    metadata: PersistentImage,
}

impl PersistentData {
    fn validate(&self) -> Result<()> {
        ensure(
            self.mode == "original-ext4-v1",
            "original ext4 policy required",
        )?;
        for item in [&self.data, &self.metadata] {
            ensure(
                item.filesystem_uuid.len() == 36
                    && item.filesystem_uuid.bytes().enumerate().all(|(i, b)| {
                        if [8, 13, 18, 23].contains(&i) {
                            b == b'-'
                        } else {
                            b.is_ascii_digit() || (b'a'..=b'f').contains(&b)
                        }
                    }),
                "invalid observed filesystem UUID",
            )?;
        }
        ensure(
            self.data.filesystem_uuid != self.metadata.filesystem_uuid,
            "data and metadata must be independent observed filesystems",
        )?;
        // These are the actual normal, read-only ext4 observations for this
        // original pair. Its UUIDs remain private transaction inputs. The
        // caller must separately bind them to the admitted cold-clone proof.
        ensure(
            (
                self.data.image_bytes,
                self.data.feature_compat,
                self.data.feature_incompat,
                self.data.feature_ro_compat,
                self.data.guest_root_uid,
                self.data.guest_root_gid,
                self.data.guest_root_mode,
            ) == (34_359_738_368, 4156, 8898, 33899, 1000, 1000, 0o771),
            "observed original data filesystem contract differs",
        )?;
        ensure(
            (
                self.metadata.image_bytes,
                self.metadata.feature_compat,
                self.metadata.feature_incompat,
                self.metadata.feature_ro_compat,
                self.metadata.guest_root_uid,
                self.metadata.guest_root_gid,
                self.metadata.guest_root_mode,
            ) == (134_217_728, 4156, 8898, 1131, 0, 0, 0o755),
            "observed original metadata filesystem contract differs",
        )
    }
}

pub(super) struct DerivedCell {
    pub(super) cell: Vec<u8>,
    pub(super) selection: Vec<u8>,
    pub(super) preserved_fields: Vec<String>,
    pub(super) changed_fields: Vec<String>,
}

fn canonical(value: &Value) -> Result<Vec<u8>> {
    let mut out = serde_json::to_vec_pretty(value)?;
    out.push(b'\n');
    Ok(out)
}

/// Called only with bytes freshly read from the sealed original configuration
/// and actual independently admitted ext4 metadata. No account files are read.
pub(super) fn derive_original(
    original: &[u8],
    cohort: &str,
    runtime: &str,
    persistent: &PersistentData,
    normal_host_release: &crate::normal_host_release::NormalHostRelease,
) -> Result<DerivedCell> {
    ensure(
        original.len() == ORIGINAL_CELL_BYTES && fs::digest(original) == ORIGINAL_CELL_SHA,
        "original public cell is not the reviewed actual configuration",
    )?;
    derive(original, cohort, runtime, persistent, normal_host_release)
}

fn derive(
    original: &[u8],
    cohort: &str,
    runtime: &str,
    persistent: &PersistentData,
    normal_host_release: &crate::normal_host_release::NormalHostRelease,
) -> Result<DerivedCell> {
    ensure(
        original.len() <= 1024 * 1024 && fs::valid_digest(cohort) && fs::valid_digest(runtime),
        "cell source or cohort identity is invalid",
    )?;
    persistent.validate()?;
    normal_host_release.validate().map_err(str::to_owned)?;
    let old: Value = serde_json::from_slice(original)?;
    let object = old.as_object().ok_or("original cell is not an object")?;
    let permitted: BTreeSet<&str> = [
        "host_uid",
        "subordinate_uids",
        "subordinate_gids",
        "image_dir",
        "image_layout",
        "gapps_dir",
        "vendor_image",
        "android_init",
        "android_file_overrides",
        "android_runtime_directories",
        "shared_storage_directories",
        "data_dir",
        "runtime_dir",
        "render_node",
        "graphics_backend",
        "denial_socket",
    ]
    .into_iter()
    .collect();
    ensure(
        object.keys().all(|k| permitted.contains(k.as_str())),
        "unreviewed original cell field",
    )?;
    ensure(
        old["host_uid"] == 1000
            && old["data_dir"] == FIXED_DATA
            && old["runtime_dir"] == FIXED_RUNTIME,
        "original account identity or fixed data path differs",
    )?;
    for field in ["subordinate_uids", "subordinate_gids"] {
        ensure(
            old[field] == json!({"start":100000,"count":100000}),
            "original subordinate range differs; fresh fixture IDs cannot replace it",
        )?;
    }
    ensure(
        old["render_node"] == "/dev/dri/renderD128"
            && old["graphics_backend"] == "drm_media_dma_heap"
            && old["denial_socket"] == "/run/user/1000/droidloom/native-bridge.sock",
        "original device or socket configuration differs",
    )?;
    ensure(
        old.get("gapps_dir").is_none_or(Value::is_null)
            && old
                .get("shared_storage_directories")
                .is_none_or(|v| v == &json!([])),
        "existing account shares or optional Google configuration require explicit review",
    )?;
    ensure(
        old["android_init"].is_string()
            && old["android_file_overrides"]
                .as_array()
                .is_some_and(|v| v.len() == 43)
            && old["android_runtime_directories"]
                .as_array()
                .is_some_and(|v| v.len() == 4),
        "reviewed legacy public configuration closure differs",
    )?;
    let mut new = old.clone();
    let new_object = new.as_object_mut().ok_or("cell object disappeared")?;
    for field in [
        "android_init",
        "android_file_overrides",
        "android_runtime_directories",
    ] {
        new_object.remove(field);
    }
    let images = format!("/var/lib/droidloom/cohorts/{cohort}/images");
    new_object.insert("image_dir".into(), json!(images));
    new_object.insert("vendor_image".into(), json!(format!("{images}/vendor.img")));
    new_object.insert("image_layout".into(), json!("gsi_system_as_root"));
    let changed: BTreeSet<_> = [
        "image_dir",
        "vendor_image",
        "image_layout",
        "android_init",
        "android_file_overrides",
        "android_runtime_directories",
    ]
    .into_iter()
    .collect();
    let mut preserved = Vec::new();
    for (name, value) in object {
        if !changed.contains(name.as_str()) {
            ensure(
                new.get(name) == Some(value),
                "original cell field changed outside exact migration",
            )?;
            preserved.push(name.clone());
        }
    }
    let cell = canonical(&new)?;
    // This adds only the fixed public comparison projection. The actual cold
    // COPY/CLONE lineage and four inodes are independently checked before
    // admission and again by the data transaction before any exchange.
    let mut persistent = serde_json::to_value(persistent)?;
    persistent.as_object_mut().ok_or("persistent policy object missing")?.insert(
        "original_copy".into(),
        serde_json::to_value(crate::cold_original_once_recovery::contract::OriginalCopyPolicy::reviewed())?,
    );
    let selected = json!({"schema":"droidloom-production-selection-v4",
        "launcher":"early_boot_shared_kernel_v1", "host_uid":1000,
        "cell_spec_bytes":cell.len(), "cell_spec_sha256":fs::digest(&cell),
        "base_cohort_sha256":cohort,"runtime_manifest_sha256":runtime,"persistent_data":persistent,"normal_host_release":normal_host_release});
    let selection = canonical(&selected)?;
    ensure(
        selection.len() <= 16 * 1024,
        "selected configuration exceeds normal reader bound",
    )?;
    Ok(DerivedCell {
        cell,
        selection,
        preserved_fields: preserved,
        changed_fields: changed.into_iter().map(str::to_owned).collect(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn persistent() -> PersistentData {
        serde_json::from_value(json!({"mode":"original-ext4-v1",
            "data":{"image_bytes":34359738368_u64,"filesystem_uuid":"11111111-1111-4111-8111-111111111111",
                "feature_compat":4156,"feature_incompat":8898,"feature_ro_compat":33899,
                "guest_root_uid":1000,"guest_root_gid":1000,"guest_root_mode":505},
            "metadata":{"image_bytes":134217728,"filesystem_uuid":"22222222-2222-4222-8222-222222222222",
                "feature_compat":4156,"feature_incompat":8898,"feature_ro_compat":1131,
                "guest_root_uid":0,"guest_root_gid":0,"guest_root_mode":493}})).unwrap()
    }
    fn normal_release() -> crate::normal_host_release::NormalHostRelease {
        use crate::normal_host_release::{NormalHostRelease, NormalHostProgramPin, SCHEMA, MANAGER, PRESENTER};
        NormalHostRelease {
            schema: SCHEMA.into(),
            manager: NormalHostProgramPin {path: MANAGER.into(), bytes: 1024, sha256: "d".repeat(64)},
            presenter: NormalHostProgramPin {path: PRESENTER.into(), bytes: 2048, sha256: "e".repeat(64)},
        }
    }
    fn original() -> Value {
        json!({"host_uid":1000,"subordinate_uids":{"start":100000,"count":100000},
            "subordinate_gids":{"start":100000,"count":100000},"image_dir":"/usr/lib/droidloom/images",
            "vendor_image":"/usr/lib/droidloom/images/vendor.img","android_init":"/usr/lib/droidloom/init",
            "android_file_overrides":vec![json!({"old":"public"});43],
            "android_runtime_directories":vec![json!({"old":"public"});4],
            "shared_storage_directories":[],"data_dir":FIXED_DATA,"runtime_dir":FIXED_RUNTIME,
            "render_node":"/dev/dri/renderD128","graphics_backend":"drm_media_dma_heap",
            "denial_socket":"/run/user/1000/droidloom/native-bridge.sock"})
    }
    #[test]
    fn migration_preserves_actual_account_ranges_devices_sockets_and_binds_exact_cell_bytes()
    -> Result<()> {
        let old = original();
        let bytes = canonical(&old)?;
        let result = derive(&bytes, &"a".repeat(64), &"b".repeat(64), &persistent(), &normal_release())?;
        let cell: Value = serde_json::from_slice(&result.cell)?;
        let selection: Value = serde_json::from_slice(&result.selection)?;
        for name in &result.preserved_fields {
            assert_eq!(cell[name], old[name]);
        }
        assert!(cell.get("android_init").is_none());
        assert!(cell.get("android_file_overrides").is_none());
        assert!(cell.get("android_runtime_directories").is_none());
        assert_eq!(cell["image_layout"], "gsi_system_as_root");
        assert_eq!(selection["cell_spec_sha256"], fs::digest(&result.cell));
        assert_eq!(selection["cell_spec_bytes"], result.cell.len());
        assert_eq!(selection.as_object().unwrap().len(), 9);
        assert_eq!(selection["normal_host_release"], serde_json::to_value(normal_release())?);
        let mut other_release = normal_release();
        other_release.presenter.sha256 = "f".repeat(64);
        let changed_program = derive(&bytes, &"a".repeat(64), &"b".repeat(64), &persistent(), &other_release)?;
        assert_eq!(result.cell, changed_program.cell);
        assert_ne!(result.selection, changed_program.selection);
        assert_eq!(selection["persistent_data"]["original_copy"],
            serde_json::to_value(crate::cold_original_once_recovery::contract::OriginalCopyPolicy::reviewed())?);
        // The metadata input cannot supply its own lineage. Only this normal
        // source producer adds the fixed, separately checked projection.
        assert!(serde_json::from_value::<PersistentData>(selection["persistent_data"].clone()).is_err());
        assert_eq!(result.changed_fields.len(), 6);
        // The production entry also requires the actual original bytes. This
        // synthetic test record never becomes real-machine admission.
        assert!(derive_original(&bytes, &"a".repeat(64), &"b".repeat(64), &persistent(), &normal_release()).is_err());
        Ok(())
    }
    #[test]
    fn fresh_fixture_identity_and_unreviewed_original_shares_are_rejected() -> Result<()> {
        let mut old = original();
        old["subordinate_uids"]["start"] = json!(655360);
        assert!(
            derive(
                &canonical(&old)?,
                &"a".repeat(64),
                &"b".repeat(64),
                &persistent(),
                &normal_release()
            )
            .is_err()
        );
        old = original();
        old["shared_storage_directories"] = json!([{"source":"/home/alex/Documents"}]);
        assert!(
            derive(
                &canonical(&old)?,
                &"a".repeat(64),
                &"b".repeat(64),
                &persistent(),
                &normal_release()
            )
            .is_err()
        );
        old = original();
        old["unlisted_override"] = json!(true);
        assert!(
            derive(
                &canonical(&old)?,
                &"a".repeat(64),
                &"b".repeat(64),
                &persistent(),
                &normal_release()
            )
            .is_err()
        );
        Ok(())
    }
}
