//! Exact production source union and receipts for the real user vendor producer.
use super::*;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::os::unix::fs::MetadataExt;

pub(super) const LOCK_PATH: &str = "android/manifest/production-full-source-lock.json";
pub(super) const LOCK_SHA: &str =
    "30dcc1b5b090530b3fc06aeb3e489a961b0fc7c6368ed9d19eb0a1b2054e3eb4";
const LOCK_BYTES: usize = 400363;

fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn exact_file(path: &Path, bytes: usize, expected: &str) -> Result<Vec<u8>> {
    for parent in path.ancestors().skip(1) {
        let metadata = fs::symlink_metadata(parent)?;
        if !metadata.is_dir() || metadata.file_type().is_symlink() {
            return fail("production source identity requires real parent directories");
        }
    }
    let before = fs::symlink_metadata(path)?;
    if !before.is_file()
        || before.file_type().is_symlink()
        || before.nlink() != 1
        || before.len() != bytes as u64
    {
        return fail(format!(
            "production source input is not the exact ordinary file: {}",
            path.display()
        ));
    }
    let raw = fs::read(path)?;
    let after = fs::symlink_metadata(path)?;
    if before.dev() != after.dev()
        || before.ino() != after.ino()
        || before.mode() != after.mode()
        || before.len() != after.len()
        || before.mtime_nsec() != after.mtime_nsec()
        || before.mtime() != after.mtime()
        || before.ctime_nsec() != after.ctime_nsec()
        || before.ctime() != after.ctime()
        || digest(&raw) != expected
    {
        return fail(format!(
            "production source file changed: {}",
            path.display()
        ));
    }
    Ok(raw)
}

fn union(audio: &Value, native: &Value) -> Result<Value> {
    let mut audio_header = audio.clone();
    let mut native_header = native.clone();
    audio_header
        .as_object_mut()
        .ok_or("Audio source object missing")?
        .remove("projects");
    native_header
        .as_object_mut()
        .ok_or("Native source object missing")?
        .remove("projects");
    if audio_header != native_header {
        return fail(
            "production source profiles must retain the same exact superproject and policy",
        );
    }
    let audio_rows = audio["projects"]
        .as_array()
        .ok_or("Audio projects missing")?;
    let native_rows = native["projects"]
        .as_array()
        .ok_or("Native projects missing")?;
    if audio_rows.len() != 541 || native_rows.len() != 645 {
        return fail("production union requires the two unchanged concrete original profiles");
    }
    let mut expected = native.clone();
    let rows = expected["projects"]
        .as_array_mut()
        .ok_or("Native projects missing")?;
    let mut common = 0;
    for row in rows.iter_mut() {
        let Some(other) = audio_rows.iter().find(|p| p["path"] == row["path"]) else {
            continue;
        };
        common += 1;
        for key in ["path", "name", "commit"] {
            if row[key] != other[key] {
                return fail("production source common project identity conflicts");
            }
        }
        let old = row["sparse_paths"].as_array().cloned().unwrap_or_default();
        let extra = other["sparse_paths"]
            .as_array()
            .cloned()
            .unwrap_or_default();
        let mut merged = old.clone();
        if old.is_empty() || extra.is_empty() {
            merged.clear();
        } else {
            for item in extra {
                if !merged.contains(&item) {
                    merged.push(item);
                }
            }
        }
        if old != merged {
            row["sparse_paths"] = json!(merged);
        }
    }
    for row in audio_rows {
        if !native_rows.iter().any(|p| p["path"] == row["path"]) {
            rows.push(row.clone());
        }
    }
    if common != 535 || rows.len() != 651 {
        return fail("production source union dimensions changed");
    }
    Ok(expected)
}

pub(super) fn source_lock_path(repo: &Path) -> Result<PathBuf> {
    let audio_path = selected_source_lock(repo, SoongDependencyMode::AudioApexTargetClosure)?;
    let native_path = crate::native_generation_pair_build::source_lock_path(repo)?;
    let audio = exact_file(&audio_path, 287615, AUDIO_SOURCE_LOCK_SHA256)?;
    let native = exact_file(
        &native_path,
        369917,
        "e07f2fac7e7a22c331cffc9a37d57706d64a4550165823afb2ef65c12b0d4a40",
    )?;
    droidloom_source::build_plan(&droidloom_source::load_lock(&audio_path)?)?;
    let expected = union(
        &serde_json::from_slice(&audio)?,
        &serde_json::from_slice(&native)?,
    )?;
    let path = repo.join(LOCK_PATH);
    let raw = exact_file(&path, LOCK_BYTES, LOCK_SHA)?;
    let actual: Value = serde_json::from_slice(&raw)?;
    if actual != expected {
        return fail("production source differs from the complete monotonic union");
    }
    droidloom_source::production_full::build_plan(&droidloom_source::load_lock(&path)?)?;
    Ok(path)
}

/// Shared source must already have the exact normal-materializer manifest.
/// Existing trees are expanded only by the separately recorded reconcile step.
pub(super) fn verify_source_workspace(
    lock_path: &Path,
    lock: &droidloom_source::SparseSourceLock,
    source: &Path,
) -> Result<()> {
    for parent in source.ancestors().skip(1) {
        let metadata = fs::symlink_metadata(parent)?;
        if !metadata.is_dir() || metadata.file_type().is_symlink() {
            return fail("production source parent must be a real directory");
        }
    }
    match fs::symlink_metadata(source) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error.into()),
        Ok(metadata) if metadata.is_dir() && !metadata.file_type().is_symlink() => {
            let expected = droidloom_source::MaterializedManifest {
                schema_version: 1,
                source_lock_sha256: LOCK_SHA.to_owned(),
                plan: droidloom_source::production_full::build_plan(lock)?,
            };
            let bytes = serde_json::to_vec_pretty(&expected)?;
            exact_file(
                &source.join(".droidloom-source-manifest.json"),
                bytes.len(),
                &digest(&bytes),
            )?;
            droidloom_source::production_full::verify_materialized(lock_path, lock, source)?;
            Ok(())
        }
        Ok(_) => fail("production source workspace must be a real directory"),
    }
}

pub(super) fn input_receipt(
    repo: &Path,
    source: &Path,
    out: &Path,
    product: &str,
    request: FixedProductionRequest<'_>,
    projection: &Projection,
) -> Result<()> {
    if !request.uses_production_full_source()
        || request.source_mode() != SoongDependencyMode::Strict
    {
        return fail("production receipt requires the complete strict source profile");
    }
    let lock = source_lock_path(repo)?;
    let mut receipt = request.description(product)?;
    receipt["schema"] = "droidloom-production-full651-inputs-v1".into();
    receipt["source_lock"] = json!({"path": lock, "bytes": LOCK_BYTES, "sha256": LOCK_SHA});
    receipt["source_manifest"] = json!({"path": source.join(".droidloom-source-manifest.json"),
        "sha256": hash(&source.join(".droidloom-source-manifest.json"))?});
    receipt["effective_projection"] = projection.effective_inventory(repo, source)?;
    receipt["strict_allow_missing_dependencies"] = "false".into();
    receipt["selinux_ignore_neverallows"] = "false".into();
    receipt["Audio_original_providers_retained"] = true.into();
    receipt["Native_original_providers_retained"] = true.into();
    receipt["production_signing_qualified"] = false.into();
    receipt["whole_security_bulletin_qualified"] = false.into();
    write(
        &out.join("droidloom-production-full651-inputs.json"),
        serde_json::to_vec_pretty(&receipt)?,
    )
}

fn artifact(path: &Path) -> Result<Value> {
    let metadata = fs::symlink_metadata(path)?;
    if !metadata.is_file() || metadata.file_type().is_symlink() || metadata.len() == 0 {
        return fail(format!(
            "normal vendor producer did not create an ordinary nonempty artifact: {}",
            path.display()
        ));
    }
    Ok(json!({"path":path,"bytes":metadata.len(),"sha256":hash(path)?}))
}

fn inventory(root: &Path) -> Result<Value> {
    if !root.exists() {
        return Ok(json!({"path":root,"exists":false,"files":[]}));
    }
    let mut pending = vec![root.to_owned()];
    let mut files = Vec::new();
    while let Some(path) = pending.pop() {
        let metadata = fs::symlink_metadata(&path)?;
        if metadata.file_type().is_symlink() {
            files.push(json!({"path":path,"kind":"symlink","target":fs::read_link(&path)?}));
        } else if metadata.is_dir() {
            let mut children = fs::read_dir(&path)?.collect::<std::io::Result<Vec<_>>>()?;
            children.sort_by_key(|entry| entry.file_name());
            pending.extend(children.into_iter().rev().map(|entry| entry.path()));
        } else if metadata.is_file() {
            files.push(json!({"path":path,"bytes":metadata.len(),"sha256":hash(&path)?}));
        } else {
            return fail("vendor output inventory contains an unsupported file kind");
        }
    }
    Ok(json!({"path":root,"exists":true,"files":files}))
}

pub(super) fn vendor_result(
    out: &Path,
    product: &str,
    request: FixedProductionRequest<'_>,
) -> Result<()> {
    if !request.uses_production_full_source()
        || !request.requested_targets().contains(&"vendorimage")
    {
        return fail("vendor result requires the real strict complete-source vendor image request");
    }
    let product_out = out.join("target/product").join(product);
    let vendor = product_out.join("vendor");
    let property_path = vendor.join("build.prop");
    let properties = fs::read_to_string(&property_path)?;
    let observed: BTreeMap<&str, &str> = properties
        .lines()
        .filter(|line| !line.starts_with('#'))
        .filter_map(|line| line.split_once('='))
        .collect();
    if observed.get("ro.vendor.build.type") != Some(&"user") {
        return fail("actual vendor build.prop must identify the user build");
    }
    let tool = out.join("host/linux-x86/bin/secilc");
    let input = out.join("droidloom-production-full651-inputs.json");
    let receipt = json!({
        "schema":"droidloom-production-full651-vendor-normal-result-v1",
        "inputs":artifact(&input)?,
        "requested_targets":request.requested_targets(),
        "vendor_image":artifact(&product_out.join("vendor.img"))?,
        "vendor_build_prop":artifact(&property_path)?,
        "observed_vendor_properties":observed,
        "vendor_sepolicy_cil":artifact(&vendor.join("etc/selinux/vendor_sepolicy.cil"))?,
        "plat_pub_versioned_cil":artifact(&vendor.join("etc/selinux/plat_pub_versioned.cil"))?,
        "complete_vendor_selinux_inventory":inventory(&vendor.join("etc/selinux"))?,
        "complete_vendor_vintf_inventory":inventory(&vendor.join("etc/vintf"))?,
        "vendor_manifest":artifact(&vendor.join("etc/vintf/manifest.xml"))?,
        "vendor_compatibility_matrix":artifact(&vendor.join("etc/vintf/compatibility_matrix.xml"))?,
        "odm_actual_output":inventory(&product_out.join("odm"))?,
        "odm_image_present":product_out.join("odm.img").exists(),
        "normal_host_secilc":artifact(&tool)?,
        "host_runtime_outputs_to_retain":[out.join("host/linux-x86/bin/secilc"),
            out.join("host/linux-x86/lib"),out.join("host/linux-x86/lib64")],
        "normal_command_returned_success":true,"source_projection_restored":true,
        "source_release":PRODUCTION_TARGET_RELEASE,"build_variant":PRODUCTION_BUILD_VARIANT,
        "QPR1_source_identity_claim":false,"selected_CP3A_system_policy_qualified":false,
        "production_signing_qualified":false,"whole_security_bulletin_qualified":false,
        "Audio_runtime_qualified":false,"runtime_qualified":false,"production_ready":false
    });
    write(
        &out.join("droidloom-production-full651-vendor-normal-result.json"),
        serde_json::to_vec_pretty(&receipt)?,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn actual_production_requests_use_fixed_union_and_independent_pair_targets() {
        let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../..")
            .canonicalize()
            .unwrap();
        let path = source_lock_path(&repo).unwrap();
        let plan = droidloom_source::production_full::build_plan(
            &droidloom_source::load_lock(&path).unwrap(),
        )
        .unwrap();
        assert_eq!(plan.projects.len(), 651);
        assert_eq!(hash(&path).unwrap(), LOCK_SHA);
        for request in [
            FixedProductionRequest::Existing(SoongDependencyMode::Strict, TARGETS),
            FixedProductionRequest::Existing(SoongDependencyMode::Strict, &["services"]),
            FixedProductionRequest::WmSecurityOnProductionSource,
            FixedProductionRequest::VendorImageOnProductionSource,
        ] {
            assert!(request.uses_production_full_source());
            assert_eq!(request.source_lock(&repo).unwrap(), path);
            assert_eq!(request.source_mode(), SoongDependencyMode::Strict);
            assert!(request.validate("droidloom_arm64").is_err());
            let mut command = Command::new("not-executed");
            request
                .configure_dependencies(&mut command, "droidloom_x86_64")
                .unwrap();
            for required in ["ALLOW_MISSING_DEPENDENCIES", "SELINUX_IGNORE_NEVERALLOWS"] {
                assert!(
                    command.get_envs().any(|(key, value)| key == required
                        && value == Some(std::ffi::OsStr::new("false")))
                );
            }
            assert!(!command.get_args().any(|arg| arg == "--soong-only"));
        }
        let vendor = FixedProductionRequest::VendorImageOnProductionSource;
        assert_eq!(vendor.requested_targets(), ["vendorimage", "secilc"]);
        assert_eq!(vendor.projection_targets(), TARGETS);
        assert_eq!(
            vendor
                .soong_targets(Path::new("/out"), "droidloom_x86_64")
                .unwrap(),
            vec![PathBuf::from("vendorimage"), PathBuf::from("secilc")]
        );
        let pair = FixedProductionRequest::NativePair;
        assert!(!pair.uses_production_full_source());
        assert_ne!(pair.source_lock(&repo).unwrap(), path);
        assert_eq!(
            pair.requested_targets(),
            crate::native_generation_pair_build::TARGETS
        );
        assert_eq!(pair.requested_targets(), pair.projection_targets());
    }

    #[test]
    fn union_retains_original_scopes_and_rejects_different_common_pins() {
        let audio: Value = serde_json::from_str(include_str!(
            "../../../android/manifest/audio-bridge-source-lock.json"
        ))
        .unwrap();
        let native: Value = serde_json::from_str(include_str!(
            "../../../android/native-generation-pair/source-lock.json"
        ))
        .unwrap();
        let full: Value = serde_json::from_str(include_str!(
            "../../../android/manifest/production-full-source-lock.json"
        ))
        .unwrap();
        assert_eq!(union(&audio, &native).unwrap(), full);
        let mut drift = native.clone();
        drift["projects"][0]["commit"] = json!("0000000000000000000000000000000000000000");
        assert!(union(&audio, &drift).is_err());
        let mut drift = native.clone();
        drift["superproject"]["commit"] = json!("0000000000000000000000000000000000000000");
        assert!(union(&audio, &drift).is_err());
        let mut drift = audio;
        drift["projects"].as_array_mut().unwrap().pop();
        assert!(union(&drift, &native).is_err());
    }

    #[test]
    fn old_native_manifest_is_not_silently_expanded_by_product_request() {
        let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../..")
            .canonicalize()
            .unwrap();
        let path = source_lock_path(&repo).unwrap();
        let full = droidloom_source::load_lock(&path).unwrap();
        let d = tempfile::tempdir().unwrap();
        let source = d.path().join("source");
        fs::create_dir(&source).unwrap();
        let native = droidloom_source::load_lock(
            &repo.join("android/native-generation-pair/source-lock.json"),
        )
        .unwrap();
        let prior = droidloom_source::MaterializedManifest {
            schema_version: 1,
            source_lock_sha256: "e07f2fac7e7a22c331cffc9a37d57706d64a4550165823afb2ef65c12b0d4a40"
                .into(),
            plan: droidloom_source::native_pair::build_plan(&native).unwrap(),
        };
        let original = serde_json::to_vec_pretty(&prior).unwrap();
        let manifest = source.join(".droidloom-source-manifest.json");
        fs::write(&manifest, &original).unwrap();
        assert!(verify_source_workspace(&path, &full, &source).is_err());
        assert_eq!(fs::read(&manifest).unwrap(), original);
        assert_eq!(fs::read_dir(&source).unwrap().count(), 1);
    }
}
