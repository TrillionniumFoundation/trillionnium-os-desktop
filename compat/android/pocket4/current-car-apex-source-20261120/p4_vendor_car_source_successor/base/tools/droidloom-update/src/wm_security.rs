//! Apply three complete official WindowManager corrections through the normal
//! source-projection journal. Normal builds that compile services use this path.
//! Source application and a successful build do not qualify a device or a CVE.
use super::*;
use std::os::unix::fs::MetadataExt;

pub(super) const TARGETS: &[&str] = &["services", "framework-minus-apex", "WmTests", "module-info"];
const PROJECT: &str = "frameworks/base";
const PROJECT_PIN: &str = "94b4c163b7dfe5ce3607f7bb8456f9573f7de57d";
const CVES: &[&str] = &[
    "CVE-2026-58946",
    "CVE-2026-58944",
    "CVE-2026-58961",
    "CVE-2026-58962",
    "CVE-2026-58886",
];
const PATCHES: &[(&str, u64, &str, &str)] = &[
    (
        "android/security/wm/creator-token.patch",
        879,
        "552013cbe3ab2ce2a77201158b7ee3d564ec7541bff85ade708a2f652855d621",
        "0a387476e98f851b1a445d3aa0f1f1ccbec50fb3",
    ),
    (
        "android/security/wm/activity-options.patch",
        1190,
        "877a7f9e62f4304a9620fdbc41802f8ada48220002b90f665961cef72bede0ae",
        "4c71997176db9c2fa05deb7e5b9d872de53753b3",
    ),
    (
        "android/security/wm/pip-input-consumer.patch",
        3620,
        "fd3af3131dfc3c96a71b30f5a9641f1ced6fccd5bdf13ee5b82e579f48777b69",
        "bcf19c956e5ae49b6dbf748afa7c6201a5c0b4e7",
    ),
];
const ORIGINALS: &[(&str, u64, &str)] = &[
    (
        "services/core/java/com/android/server/wm/ActivityClientController.java",
        90859,
        "1ca6c2fbe4dbd572229e62b0fc8d6192e1efce58fb7a171e127ecb48cdc9df13",
    ),
    (
        "services/core/java/com/android/server/wm/ActivityTaskManagerService.java",
        371557,
        "25ffd4166d7244379b5624c784c29659b5ecdcbdbd1c60d3c7fdab38693388a9",
    ),
    (
        "services/core/java/com/android/server/wm/InputMonitor.java",
        35975,
        "9cf0b0936f61a9a013032c07c5de6486e7538893102b6f0264da1080359d401b",
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
        "services/tests/wmtests/Android.bp",
        51079,
        "23b4082ab5de81b25facce2629fcf65a34c01e057399fb385a13a825d269b87c",
    ),
];
const FIXED: &[(&str, u64, &str)] = &[
    (
        "services/core/java/com/android/server/wm/ActivityClientController.java",
        91006,
        "40bdaef1bbd4129cd7f92d944b6de542d303a75b349f534fd6b06eb250cfc5f4",
    ),
    (
        "services/core/java/com/android/server/wm/ActivityTaskManagerService.java",
        371811,
        "92f9eee62790b31a0f07f910bfc98531d8b9451f2c80bc8fea182c3f1987ec63",
    ),
    (
        "services/core/java/com/android/server/wm/InputMonitor.java",
        36107,
        "27a41b91b6599987400d64dae6b281d1831335b69f9703234d7a3d1b9b061ced",
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
        "services/tests/wmtests/Android.bp",
        51079,
        "23b4082ab5de81b25facce2629fcf65a34c01e057399fb385a13a825d269b87c",
    ),
];

/// The ordinary full TARGETS set contains services. This is not confined to an
/// otherwise unused security-only command.
pub(super) fn required_for_targets(targets: &[&str]) -> bool {
    targets
        .iter()
        .any(|name| matches!(*name, "services" | "services.core" | "WmTests"))
}

pub(super) fn validate_request(request: FixedProductionRequest<'_>, product: &str) -> Result<()> {
    request.validate(product)?;
    if request.source_mode() != SoongDependencyMode::Strict
        || !required_for_targets(request.requested_targets())
    {
        return fail(
            "WindowManager production requires the normal strict source and an actual services target",
        );
    }
    Ok(())
}

fn original_path(root: &Path, relative: &str) -> Result<PathBuf> {
    if !root.is_absolute() || root.canonicalize()? != root {
        return fail(
            "WindowManager source and recipe roots must be canonical absolute directories",
        );
    }
    let mut path = root.to_path_buf();
    for component in Path::new(relative).components() {
        if !matches!(component, std::path::Component::Normal(_)) {
            return fail("WindowManager input path must have only original relative components");
        }
        path.push(component.as_os_str());
        let meta = fs::symlink_metadata(&path)?;
        if meta.file_type().is_symlink() {
            return fail("WindowManager original or patch path is an alias");
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
            "WindowManager exact original or official fixed input differs: {relative}"
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
        return fail("WindowManager input changed during complete verification");
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
    inputs["schema"] = "droidloom-wm-security-inputs-v1".into();
    inputs["CVE_rows"] = serde_json::json!(CVES);
    inputs["source_lock"] = serde_json::json!({"path": lock, "sha256": hash(lock)?});
    inputs["original_frameworks_base_pin"] = PROJECT_PIN.into();
    inputs["official_complete_patches"] = patches.into();
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
    let path = out.join("droidloom-wm-security-inputs.json");
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
    let input = out.join("droidloom-wm-security-inputs.json");
    write(
        &out.join("droidloom-wm-security-normal-result.json"),
        serde_json::to_vec_pretty(&serde_json::json!({
            "schema": "droidloom-wm-security-normal-result-v1",
            "CVE_rows": CVES,
            "inputs": {"path": input, "sha256": hash(&input)?},
            "requested_targets": request.requested_targets(),
            "product": product,
            "normal_command_returned_success": true,
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;

    fn fixture(root: &Path) -> (PathBuf, PathBuf) {
        let repo = root.join("recipe");
        let source = root.join("source");
        for (name, bytes) in [
            ("services/core/java/com/android/server/wm/ActivityClientController.java", include_bytes!("../../../android/security/wm/fixtures/services/core/java/com/android/server/wm/ActivityClientController.java").as_slice()),
            ("services/core/java/com/android/server/wm/ActivityTaskManagerService.java", include_bytes!("../../../android/security/wm/fixtures/services/core/java/com/android/server/wm/ActivityTaskManagerService.java").as_slice()),
            ("services/core/java/com/android/server/wm/InputMonitor.java", include_bytes!("../../../android/security/wm/fixtures/services/core/java/com/android/server/wm/InputMonitor.java").as_slice()),
            ("services/Android.bp", include_bytes!("../../../android/security/wm/fixtures/services/Android.bp").as_slice()),
            ("services/core/Android.bp", include_bytes!("../../../android/security/wm/fixtures/services/core/Android.bp").as_slice()),
            ("services/tests/wmtests/Android.bp", include_bytes!("../../../android/security/wm/fixtures/services/tests/wmtests/Android.bp").as_slice()),
        ] {
            write(&source.join(PROJECT).join(name), bytes).unwrap();
        }
        for (name, bytes) in [
            (
                "android/security/wm/creator-token.patch",
                include_bytes!("../../../android/security/wm/creator-token.patch").as_slice(),
            ),
            (
                "android/security/wm/activity-options.patch",
                include_bytes!("../../../android/security/wm/activity-options.patch").as_slice(),
            ),
            (
                "android/security/wm/pip-input-consumer.patch",
                include_bytes!("../../../android/security/wm/pip-input-consumer.patch").as_slice(),
            ),
        ] {
            write(&repo.join(name), bytes).unwrap();
        }
        (repo, source)
    }

    #[test]
    fn wm_three_official_patches_restore_complete_original_bytes_and_metadata() {
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
            assert_eq!(projection.originals.len(), 3);
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
    fn wm_focused_selects_complete_production651_lock_and_original_providers() {
        let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../..")
            .canonicalize()
            .unwrap();
        let request = FixedProductionRequest::WmSecurityOnProductionSource;
        let selected = request.source_lock(&repo).unwrap();
        assert_eq!(selected, repo.join(production_source::LOCK_PATH));
        assert_ne!(
            selected,
            FixedProductionRequest::NativePair
                .source_lock(&repo)
                .unwrap()
        );
        let lock = droidloom_source::load_lock(&selected).unwrap();
        let plan = droidloom_source::production_apex_tests::build_plan(&lock).unwrap();
        assert_eq!(plan.projects.len(), 652);
        let original = droidloom_source::load_lock(
            &repo.join("android/manifest/production-full-source-lock.json"),
        ).unwrap();
        let original_plan = droidloom_source::production_full::build_plan(&original).unwrap();
        assert_eq!(original_plan.projects.len(), 651);
        let mut expected_projects = original_plan.projects.clone();
        expected_projects.iter_mut()
            .find(|project| project.path == Path::new(droidloom_source::production_lint::HEALTH_PATH))
            .unwrap().sparse_paths.push(droidloom_source::production_lint::LINT_PATH.into());
        for &(path, _, cone) in droidloom_source::production_apex_tests::PROVIDERS {
            expected_projects.iter_mut()
                .find(|project| project.path == Path::new(path))
                .unwrap().sparse_paths.push(cone.into());
        }
        assert_eq!(&plan.projects[..651], expected_projects.as_slice());
        assert_eq!(plan.links.len(), 8);
        assert!(!plan.unrestricted_repo_sync);
        assert_eq!(request.projection_targets(), TARGETS);
        assert_eq!(request.requested_targets(), TARGETS);
        assert_eq!(request.source_mode(), SoongDependencyMode::Strict);
        assert_eq!(hash(&selected).unwrap(), production_source::LOCK_SHA);
    }

    #[test]
    fn wm_default_full_and_focused_services_commands_use_strict_user_source() {
        for request in [
            FixedProductionRequest::Existing(SoongDependencyMode::Strict, crate::android::TARGETS),
            FixedProductionRequest::WmSecurityOnProductionSource,
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
