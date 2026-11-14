//! Apply four complete official framework corrections in the normal services producer.
//! These are source and build records; device tests, DEX semantics and whole-CVE
//! acceptance remain separate from a successful ordinary build.
use super::*;
use std::os::unix::fs::MetadataExt;

pub(super) const TARGETS: &[&str] = &[
    "services",
    "WmTests",
    "FrameworksServicesTests",
    "UsbTests",
    "module-info",
];
const PROJECT: &str = "frameworks/base";
const PROJECT_PIN: &str = "94b4c163b7dfe5ce3607f7bb8456f9573f7de57d";
const CVES: &[&str] = &[
    "CVE-2026-58836",
    "CVE-2026-58866",
    "CVE-2026-28645",
    "CVE-2026-45514",
];
const PATCHES: &[(&str, u64, &str, &str)] = &[
    (
        "android/security/framework-asb/9444f519c4e55123c11a7ce92a960bb38486dbab.patch",
        2875,
        "b088d7f1d355b08166ab02ef03f6615056c4c7be3d60ef7f610bcc198b5e5ddc",
        "9444f519c4e55123c11a7ce92a960bb38486dbab",
    ),
    (
        "android/security/framework-asb/8e0e0f7728ff147c2aecc24fca1a6b53e3b62b54.patch",
        7886,
        "1466c54ca227db1466c241b5dd53200764211a459257ea4f472d84c2e93ae970",
        "8e0e0f7728ff147c2aecc24fca1a6b53e3b62b54",
    ),
    (
        "android/security/framework-asb/7a1a896e52d35ee502fd7140d37bed53651a6daa.patch",
        8890,
        "a6a6923b720963c7cc59c7daedd1c057b5462b5cec97d8dbcee0df95796f3035",
        "7a1a896e52d35ee502fd7140d37bed53651a6daa",
    ),
    (
        "android/security/framework-asb/4d1f600cbcbbeb990e19bec4a386fb64f922ddd1.patch",
        6167,
        "3efaf6b185d90b0c711d3d738ed06e026ba8c0ab60f441d25ed59266996d8d1f",
        "4d1f600cbcbbeb990e19bec4a386fb64f922ddd1",
    ),
];
const ALIASES_NOT_REPLAYED: &[(&str, &str)] = &[
    (
        "9444f519c4e55123c11a7ce92a960bb38486dbab",
        "ec56593e44df7847b614c1fbdb44feaf2d75623e",
    ),
    (
        "8e0e0f7728ff147c2aecc24fca1a6b53e3b62b54",
        "a84ccbdd9c61336d8abe6ec15c766b9ce454483e",
    ),
    (
        "7a1a896e52d35ee502fd7140d37bed53651a6daa",
        "cabd39ad7bd18387802dcb9f2fd27a251d9966f2",
    ),
    (
        "4d1f600cbcbbeb990e19bec4a386fb64f922ddd1",
        "fb6a81e33d54baecf5b05ad81b4522433f710b94",
    ),
];
const ORIGINALS: &[(&str, u64, &str)] = &[
    (
        "services/accessibility/java/com/android/server/accessibility/AccessibilityWindowManager.java",
        102156,
        "e7c68f37e87a79eee3cbf408d2f963c9a1387d90fa0ee7a50c886e46fc2f24c5",
    ),
    (
        "services/core/java/com/android/server/pm/InstallPackageHelper.java",
        279969,
        "00a61a16e9a209f8c8be39bb997f63e3a7235c1214faab9a56157e619f1104ee",
    ),
    (
        "services/usb/java/com/android/server/usb/UsbService.java",
        89524,
        "7735afea26ad9b72bdb7d9ff9c18835dbd07b8b1ee093a42b0d1e244b6c6fc52",
    ),
    (
        "services/autofill/java/com/android/server/autofill/ui/SaveUi.java",
        35174,
        "72c58ec2e6292403c404ccf14676ed6e093ea8fc03ed5915cc9b0c4e3d1a7482",
    ),
    (
        "services/tests/servicestests/src/com/android/server/accessibility/AccessibilityWindowManagerTest.java",
        70025,
        "2bdbc4dd273f059a0e04c18f20d4edba1f9d559977ee49155e156eb4748a80ec",
    ),
    (
        "tests/UsbTests/src/com/android/server/usb/UsbServiceTest.java",
        15048,
        "03fcdb103b2ae24d03a92b6c05731d8617415c1451d5feab27ef702dfc864c0d",
    ),
    (
        "core/java/android/content/pm/PackageInstaller.java",
        254629,
        "4994cdfeb29aa136f6889c3d2ef4a531e9a05fc80f8a45387fa5e2da633b826f",
    ),
    (
        "services/Android.bp",
        18005,
        "01a1e03080a8d10e0344551fe75f067d94881d139c2c42c17b96ed702a898d5b",
    ),
    (
        "services/core/Android.bp",
        12364,
        "1c8e701380a377e034da9d5224d4040657666bedafeb862f4e6e7a0959a9717a",
    ),
    (
        "services/tests/servicestests/Android.bp",
        30725,
        "051e4d6be23025177ff185a189f58d93839cce47986fe409328aec2a322b2dae",
    ),
    (
        "tests/UsbTests/Android.bp",
        1706,
        "4cde9add294521d36a98c56ce0861745e2d0845e8448ec58bc5ff0a0d0263258",
    ),
];
const FIXED: &[(&str, u64, &str)] = &[
    (
        "services/accessibility/java/com/android/server/accessibility/AccessibilityWindowManager.java",
        102906,
        "95890fa47be8425e8ea0063487ad1e5418344124d0e3c83a1a9a542852af4376",
    ),
    (
        "services/core/java/com/android/server/pm/InstallPackageHelper.java",
        279425,
        "f9c83556d2ffc4f47dafd3a0db4d44eb288e5ba26bc7269c46db51bb45777fe3",
    ),
    (
        "services/usb/java/com/android/server/usb/UsbService.java",
        90577,
        "f9b730b03961f56461af5b1a7a1c621a4b2e4ad7eda688e00d6a4c15e3d9d946",
    ),
    (
        "services/autofill/java/com/android/server/autofill/ui/SaveUi.java",
        37086,
        "73b8331607e0f1581f6e94a4d0632c198a25a94d931ef16f3f643a33a5898655",
    ),
    (
        "services/tests/servicestests/src/com/android/server/accessibility/AccessibilityWindowManagerTest.java",
        74021,
        "0fb855b7db7ce6eaf4461f27dc934ff276afb1ce34dac199f8ea065c889c3722",
    ),
    (
        "tests/UsbTests/src/com/android/server/usb/UsbServiceTest.java",
        18540,
        "711222bcdcac6e6431be7869cc5c7a381041dbc38471dab5c533eb67b2966759",
    ),
    (
        "core/java/android/content/pm/PackageInstaller.java",
        254629,
        "4994cdfeb29aa136f6889c3d2ef4a531e9a05fc80f8a45387fa5e2da633b826f",
    ),
];
const PROVIDERS: &[(&str, u64, &str)] = &[
    (
        "services/Android.bp",
        18005,
        "01a1e03080a8d10e0344551fe75f067d94881d139c2c42c17b96ed702a898d5b",
    ),
    (
        "services/core/Android.bp",
        12364,
        "1c8e701380a377e034da9d5224d4040657666bedafeb862f4e6e7a0959a9717a",
    ),
    (
        "services/tests/servicestests/Android.bp",
        30725,
        "051e4d6be23025177ff185a189f58d93839cce47986fe409328aec2a322b2dae",
    ),
    (
        "tests/UsbTests/Android.bp",
        1706,
        "4cde9add294521d36a98c56ce0861745e2d0845e8448ec58bc5ff0a0d0263258",
    ),
];

/// The ordinary full TARGETS set contains services. This is not confined to an
/// otherwise unused security-only command.
pub(super) fn required_for_targets(targets: &[&str]) -> bool {
    targets.iter().any(|name| {
        matches!(
            *name,
            "services"
                | "services.core"
                | "services.accessibility"
                | "services.usb"
                | "services.autofill"
                | "WmTests"
                | "FrameworksServicesTests"
                | "UsbTests"
        )
    })
}

pub(super) fn validate_request(request: FixedProductionRequest<'_>, product: &str) -> Result<()> {
    request.validate(product)?;
    if !request.uses_production_full_source()
        || request.source_mode() != SoongDependencyMode::Strict
        || !required_for_targets(request.requested_targets())
    {
        return fail(
            "framework ASB production requires the normal strict source and an actual services target",
        );
    }
    Ok(())
}

fn original_path(root: &Path, relative: &str) -> Result<PathBuf> {
    if !root.is_absolute() || root.canonicalize()? != root {
        return fail(
            "framework ASB source and recipe roots must be canonical absolute directories",
        );
    }
    let mut path = root.to_path_buf();
    for component in Path::new(relative).components() {
        if !matches!(component, std::path::Component::Normal(_)) {
            return fail("framework ASB input path must have only original relative components");
        }
        path.push(component.as_os_str());
        let meta = fs::symlink_metadata(&path)?;
        if meta.file_type().is_symlink() {
            return fail("framework ASB original or patch path is an alias");
        }
    }
    Ok(path)
}

fn exact(root: &Path, relative: &str, bytes: u64, expected: &str) -> Result<PathBuf> {
    let path = original_path(root, relative)?;
    let before = fs::symlink_metadata(&path)?;
    if !before.is_file() || before.nlink() != 1 || before.len() != bytes || hash(&path)? != expected
    {
        return fail(format!(
            "framework ASB exact original or official fixed input differs: {relative}"
        ));
    }
    let after = fs::symlink_metadata(&path)?;
    let identity = |m: &fs::Metadata| {
        (
            m.dev(),
            m.ino(),
            m.mode(),
            m.uid(),
            m.gid(),
            m.nlink(),
            m.len(),
            (m.mtime(), m.mtime_nsec()),
            (m.ctime(), m.ctime_nsec()),
        )
    };
    if identity(&before) != identity(&after) {
        return fail("framework ASB input changed during complete verification");
    }
    Ok(path)
}

pub(super) fn validate_original(repo: &Path, source: &Path) -> Result<()> {
    for (relative, bytes, expected) in ORIGINALS {
        exact(source, &format!("{PROJECT}/{relative}"), *bytes, expected)?;
    }
    for (relative, bytes, expected, _) in PATCHES {
        exact(repo, relative, *bytes, expected)?;
    }
    Ok(())
}

fn validate_fixed(source: &Path) -> Result<()> {
    for (relative, bytes, expected) in FIXED.iter().chain(PROVIDERS) {
        exact(source, &format!("{PROJECT}/{relative}"), *bytes, expected)?;
    }
    Ok(())
}

pub(super) fn project(projection: &mut Projection, repo: &Path, source: &Path) -> Result<()> {
    validate_original(repo, source)?;
    for (relative, _, _, _) in PATCHES {
        projection.patch(source, PROJECT, &repo.join(relative))?;
    }
    validate_fixed(source)
}

/// Keep the selected user/cp2a build and dependency enforcement explicit for
/// both the normal full producer and the ordinary services/WmTests producer.
pub(super) fn configure_command(
    request: FixedProductionRequest<'_>,
    product: &str,
    command: &mut Command,
) -> Result<()> {
    validate_request(request, product)?;
    enforce_strict_soong_dependencies(command);
    command.env("SELINUX_IGNORE_NEVERALLOWS", "false");
    Ok(())
}

pub(super) fn input_receipt(
    repo: &Path,
    source: &Path,
    lock: &Path,
    out: &Path,
    product: &str,
    request: FixedProductionRequest<'_>,
    projection: &Projection,
) -> Result<PathBuf> {
    validate_request(request, product)?;
    validate_fixed(source)?;
    let mut inputs = request.description(product)?;
    let mut effective = Vec::new();
    for (relative, bytes, expected) in FIXED.iter().chain(PROVIDERS) {
        let path = exact(source, &format!("{PROJECT}/{relative}"), *bytes, expected)?;
        effective.push(serde_json::json!({"path": path, "bytes": bytes, "sha256": expected}));
    }
    let mut patches = Vec::new();
    for (relative, bytes, expected, commit) in PATCHES {
        let path = exact(repo, relative, *bytes, expected)?;
        patches.push(serde_json::json!({
            "path": path, "bytes": bytes, "sha256": expected, "commit": commit,
            "url": format!("https://android.googlesource.com/platform/frameworks/base/+/{commit}"),
        }));
    }
    inputs["schema"] = "droidloom-framework-asb-security-inputs-v1".into();
    inputs["CVE_rows"] = serde_json::json!(CVES);
    inputs["source_lock"] = serde_json::json!({"path": lock, "sha256": hash(lock)?});
    inputs["original_frameworks_base_pin"] = PROJECT_PIN.into();
    inputs["official_complete_patches"] = patches.into();
    inputs["same_fix_aliases_not_replayed"] = serde_json::json!(ALIASES_NOT_REPLAYED);
    inputs["official_test_modules"] = serde_json::json!(["FrameworksServicesTests", "UsbTests"]);
    inputs["effective_upstream_files_and_providers"] = effective.into();
    inputs["effective_projection"] = projection.effective_inventory(repo, source)?;
    inputs["strict_allow_missing_dependencies"] = "false".into();
    inputs["selinux_ignore_neverallows"] = "false".into();
    inputs["artifact_identity_qualified"] = false.into();
    inputs["official_device_tests_executed"] = false.into();
    inputs["binary_semantic_fix_qualified"] = false.into();
    inputs["production_signing_qualified"] = false.into();
    inputs["whole_security_bulletin_qualified"] = false.into();
    inputs["runtime_qualified"] = false.into();
    inputs["production_ready"] = false.into();
    let path = out.join("droidloom-framework-asb-security-inputs.json");
    write(&path, serde_json::to_vec_pretty(&inputs)?)?;
    Ok(path)
}

pub(super) fn normal_result(
    repo: &Path,
    source: &Path,
    out: &Path,
    product: &str,
    request: FixedProductionRequest<'_>,
) -> Result<()> {
    validate_request(request, product)?;
    validate_original(repo, source)?;
    let artifacts = completed_artifacts(out, product, request)?;
    let input = out.join("droidloom-framework-asb-security-inputs.json");
    write(
        &out.join("droidloom-framework-asb-security-normal-result.json"),
        serde_json::to_vec_pretty(&serde_json::json!({
            "schema": "droidloom-framework-asb-security-normal-result-v1",
            "CVE_rows": CVES,
            "inputs": {"path": input, "sha256": hash(&input)?},
            "requested_targets": request.requested_targets(),
            "product": product,
            "normal_command_returned_success": true,
            "actual_output_files": artifacts,
            "same_fix_aliases_not_replayed": ALIASES_NOT_REPLAYED,
            "original_source_files_and_providers_restored": true,
            "source_release": PRODUCTION_TARGET_RELEASE,
            "build_variant": PRODUCTION_BUILD_VARIANT,
            "strict_allow_missing_dependencies": "false",
            "selinux_ignore_neverallows": "false",
            "QPR1_source_identity_claim": false,
            "artifact_identity_qualified": false,
            "official_device_tests_executed": false,
            "binary_semantic_fix_qualified": false,
            "production_signing_qualified": false,
            "whole_security_bulletin_qualified": false,
            "runtime_qualified": false,
            "production_ready": false,
        }))?,
    )?;
    Ok(())
}

/// Bind outputs produced by this successful normal command. Device execution and
/// DEX semantic review are deliberately not inferred from artifact existence.
fn output_file(out: &Path, path: &Path) -> Result<serde_json::Value> {
    let relative = path
        .strip_prefix(out)
        .map_err(|_| "framework output escaped its owned output root")?;
    let text = relative
        .to_str()
        .ok_or("framework output path is not UTF-8")?;
    let original = original_path(out, text)?;
    let before = fs::symlink_metadata(&original)?;
    if !before.is_file() || before.nlink() != 1 || before.len() == 0 {
        return fail("normal framework command did not produce a nonempty single-link artifact");
    }
    let digest = hash(&original)?;
    exact(out, text, before.len(), &digest)?;
    let after = fs::symlink_metadata(&original)?;
    let identity = |m: &fs::Metadata| {
        (
            m.dev(),
            m.ino(),
            m.mode(),
            m.uid(),
            m.gid(),
            m.nlink(),
            m.len(),
            m.mtime(),
            m.mtime_nsec(),
            m.ctime(),
            m.ctime_nsec(),
        )
    };
    if identity(&before) != identity(&after) {
        return fail("framework output changed during complete hashing");
    }
    Ok(
        serde_json::json!({"path": original, "bytes": after.len(), "sha256": digest,
        "device": after.dev(), "inode": after.ino(), "mode": after.mode(),
        "uid": after.uid(), "gid": after.gid(), "nlink": after.nlink(),
        "mtime_seconds": after.mtime(), "mtime_nanoseconds": after.mtime_nsec(),
        "ctime_seconds": after.ctime(), "ctime_nanoseconds": after.ctime_nsec()}),
    )
}

// Pinned Make 5ce6f787 core/tasks/module-info.mk exposes the `module-info`
// phony goal and writes PRODUCT_OUT/module-info.json. Pinned Soong 6722dd88
// retains the absolute OUT_DIR through InstallPath.fullPath and serializes
// katiInstalls.InstallPaths().Strings() unchanged. This producer always passes
// a canonical absolute OUT_DIR; a relative path is not an alternate identity.
fn completed_artifacts(
    out: &Path,
    product: &str,
    request: FixedProductionRequest<'_>,
) -> Result<Vec<serde_json::Value>> {
    let product_out = out.join("target/product").join(product);
    let mut outputs = Vec::new();
    if request.requested_targets().contains(&"services") {
        outputs.push(output_file(
            out,
            &product_out.join("system/framework/services.jar"),
        )?);
    }
    if matches!(
        request,
        FixedProductionRequest::FrameworkAsbOnProductionSource
    ) {
        let info_path = product_out.join("module-info.json");
        let info_ref = output_file(out, &info_path)?;
        if fs::metadata(&info_path)?.len() > 128 * 1024 * 1024 {
            return fail("normal framework module metadata exceeds its bounded reader");
        }
        let info: serde_json::Value = serde_json::from_reader(fs::File::open(&info_path)?)?;
        for (module, provider) in [
            ("WmTests", "frameworks/base/services/tests/wmtests"),
            (
                "FrameworksServicesTests",
                "frameworks/base/services/tests/servicestests",
            ),
            ("UsbTests", "frameworks/base/tests/UsbTests"),
        ] {
            let row = info
                .get(module)
                .ok_or("requested official test missing from actual module metadata")?;
            let source_paths = row
                .get("path")
                .and_then(|x| x.as_array())
                .ok_or("test provider metadata missing")?;
            if !source_paths.iter().any(|p| p.as_str() == Some(provider)) {
                return fail("official test output is bound to a different source provider");
            }
            let installed = row
                .get("installed")
                .and_then(|x| x.as_array())
                .ok_or("official test has no installed artifact metadata")?;
            let mut apks = 0;
            for value in installed {
                let name = value.as_str().ok_or("invalid installed artifact path")?;
                let path = Path::new(name);
                if path.extension().and_then(|x| x.to_str()) != Some("apk") {
                    continue;
                }
                if !path.is_absolute() || !path.starts_with(&product_out) {
                    return fail(
                        "official test APK metadata does not identify this exact absolute product output",
                    );
                }
                let artifact = output_file(out, path)?;
                outputs.push(serde_json::json!({"module": module, "provider": provider, "artifact": artifact}));
                apks += 1;
            }
            if apks == 0 {
                return fail("requested official test produced no actual installed APK");
            }
        }
        if output_file(out, &info_path)? != info_ref {
            return fail("module metadata changed while binding actual test artifacts");
        }
        outputs.push(serde_json::json!({"module_info": info_ref}));
    }
    Ok(outputs)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;
    fn fixture(root: &Path) -> (PathBuf, PathBuf) {
        let repo = root.join("recipe");
        let source = root.join("source");
        for (name, bytes) in [
            ("services/accessibility/java/com/android/server/accessibility/AccessibilityWindowManager.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/accessibility/java/com/android/server/accessibility/AccessibilityWindowManager.java").as_slice()),
            ("services/core/java/com/android/server/pm/InstallPackageHelper.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/core/java/com/android/server/pm/InstallPackageHelper.java").as_slice()),
            ("services/usb/java/com/android/server/usb/UsbService.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/usb/java/com/android/server/usb/UsbService.java").as_slice()),
            ("services/autofill/java/com/android/server/autofill/ui/SaveUi.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/autofill/java/com/android/server/autofill/ui/SaveUi.java").as_slice()),
            ("services/tests/servicestests/src/com/android/server/accessibility/AccessibilityWindowManagerTest.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/tests/servicestests/src/com/android/server/accessibility/AccessibilityWindowManagerTest.java").as_slice()),
            ("tests/UsbTests/src/com/android/server/usb/UsbServiceTest.java", include_bytes!("../../../android/security/framework-asb/fixtures/tests/UsbTests/src/com/android/server/usb/UsbServiceTest.java").as_slice()),
            ("core/java/android/content/pm/PackageInstaller.java", include_bytes!("../../../android/security/framework-asb/fixtures/core/java/android/content/pm/PackageInstaller.java").as_slice()),
            ("services/Android.bp", include_bytes!("../../../android/security/framework-asb/fixtures/services/Android.bp").as_slice()),
            ("services/core/Android.bp", include_bytes!("../../../android/security/framework-asb/fixtures/services/core/Android.bp").as_slice()),
            ("services/tests/servicestests/Android.bp", include_bytes!("../../../android/security/framework-asb/fixtures/services/tests/servicestests/Android.bp").as_slice()),
            ("tests/UsbTests/Android.bp", include_bytes!("../../../android/security/framework-asb/fixtures/tests/UsbTests/Android.bp").as_slice()),
        ] { write(&source.join(PROJECT).join(name), bytes).unwrap(); }
        for (name, bytes) in [
            ("android/security/framework-asb/9444f519c4e55123c11a7ce92a960bb38486dbab.patch", include_bytes!("../../../android/security/framework-asb/9444f519c4e55123c11a7ce92a960bb38486dbab.patch").as_slice()),
            ("android/security/framework-asb/8e0e0f7728ff147c2aecc24fca1a6b53e3b62b54.patch", include_bytes!("../../../android/security/framework-asb/8e0e0f7728ff147c2aecc24fca1a6b53e3b62b54.patch").as_slice()),
            ("android/security/framework-asb/7a1a896e52d35ee502fd7140d37bed53651a6daa.patch", include_bytes!("../../../android/security/framework-asb/7a1a896e52d35ee502fd7140d37bed53651a6daa.patch").as_slice()),
            ("android/security/framework-asb/4d1f600cbcbbeb990e19bec4a386fb64f922ddd1.patch", include_bytes!("../../../android/security/framework-asb/4d1f600cbcbbeb990e19bec4a386fb64f922ddd1.patch").as_slice()),
        ] { write(&repo.join(name), bytes).unwrap(); }
        (repo, source)
    }
    #[test]
    fn framework_four_official_patches_restore_complete_original_bytes_and_metadata() {
        for interrupted in [false, true] {
            let d = tempfile::tempdir().unwrap();
            let (repo, source) = fixture(d.path());
            let mut before = Vec::new();
            for (relative, _, _) in ORIGINALS {
                let path = source.join(PROJECT).join(relative);
                fs::set_permissions(&path, fs::Permissions::from_mode(0o640)).unwrap();
                let meta = fs::metadata(&path).unwrap();
                before.push((path, meta.permissions().mode(), meta.modified().unwrap()));
            }
            let journal = d.path().join("source-projection.json");
            let mut projection = Projection::new(journal.clone()).unwrap();
            project(&mut projection, &repo, &source).unwrap();
            assert_eq!(projection.originals.len(), 6);
            validate_fixed(&source).unwrap();
            if interrupted {
                std::mem::forget(projection);
                recover(&journal, &source).unwrap();
            } else {
                projection.restore().unwrap();
            }
            validate_original(&repo, &source).unwrap();
            for (path, mode, modified) in before {
                let after = fs::metadata(path).unwrap();
                assert_eq!(after.permissions().mode(), mode);
                assert_eq!(after.modified().unwrap(), modified);
            }
            assert!(!journal.exists());
        }
    }

    #[test]
    fn framework_focused_selects_complete_production651_lock_and_original_providers() {
        let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../..")
            .canonicalize()
            .unwrap();
        let request = FixedProductionRequest::FrameworkAsbOnProductionSource;
        let selected = request.source_lock(&repo).unwrap();
        assert_eq!(selected, repo.join(production_source::LOCK_PATH));
        assert_ne!(
            selected,
            FixedProductionRequest::NativePair
                .source_lock(&repo)
                .unwrap()
        );
        let lock = droidloom_source::production_full::load_lock(&selected).unwrap();
        let plan = droidloom_source::production_full::build_plan(&lock).unwrap();
        assert_eq!(plan.projects.len(), 651);
        assert_eq!(plan.links.len(), 8);
        assert!(!plan.unrestricted_repo_sync);
        assert_eq!(request.projection_targets(), TARGETS);
        assert_eq!(request.requested_targets(), TARGETS);
        assert_eq!(TARGETS.last(), Some(&"module-info"));
        assert!(!TARGETS.contains(&"module-info.json"));
        assert_eq!(request.source_mode(), SoongDependencyMode::Strict);
        assert_eq!(hash(&selected).unwrap(), production_source::LOCK_SHA);
    }

    #[test]
    fn framework_default_full_and_focused_services_commands_use_strict_user_source() {
        for request in [
            FixedProductionRequest::Existing(SoongDependencyMode::Strict, crate::android::TARGETS),
            FixedProductionRequest::FrameworkAsbOnProductionSource,
        ] {
            assert!(required_for_targets(request.requested_targets()));
            validate_request(request, "droidloom_x86_64").unwrap();
            let d = tempfile::tempdir().unwrap();
            let selected = request.soong_targets(d.path(), "droidloom_x86_64").unwrap();
            let mut command = production_soong_command(
                d.path(),
                d.path(),
                d.path(),
                "droidloom_x86_64",
                1,
                &selected,
            )
            .unwrap();
            request
                .configure_dependencies(&mut command, "droidloom_x86_64")
                .unwrap();
            configure_command(request, "droidloom_x86_64", &mut command).unwrap();
            for (key, value) in [
                ("TARGET_BUILD_VARIANT", "user"),
                ("TARGET_RELEASE", "cp2a"),
                ("ALLOW_MISSING_DEPENDENCIES", "false"),
                ("SELINUX_IGNORE_NEVERALLOWS", "false"),
            ] {
                assert!(
                    command
                        .get_envs()
                        .any(|(k, v)| k == key && v == Some(std::ffi::OsStr::new(value))),
                    "{key}"
                );
            }
            let mut args = vec![
                std::ffi::OsString::from("--make-mode"),
                std::ffi::OsString::from("-j1"),
            ];
            args.extend(selected.iter().map(|p| p.as_os_str().to_owned()));
            assert_eq!(
                command.get_args().map(|v| v.to_owned()).collect::<Vec<_>>(),
                args
            );
        }
    }
}
