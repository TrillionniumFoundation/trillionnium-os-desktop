//! Project the four complete official libpng ownership corrections through v2 recovery.
//! The original same-SP project pin and Android.bp remain unchanged. The selected
//! five original C bodies equal the official patch preimages; the source pin is
//! not claimed to be the first fix's Git parent.
use super::*;
use std::os::unix::fs::MetadataExt;

pub(super) const TARGETS: &[&str] = &["libpng", "pngtest"];
const PROJECT: &str = "external/libpng";
const ORIGINAL_PIN: &str = "f3997b4b299d808f122ab1d999556d57abf5540d";
const FIRST_PARENT: &str = "7d98050ef8d9d17d495eb178b8217548437cedf1";
const COMMITS: &[&str] = &[
    "1e67678cb923d1b224bd768a987951b1995b9f5d",
    "d4c64e23f33097bd9440181cbba39677345529ba",
    "4312997903c32f588780d73c225d7a7045decde0",
    "81e0588c9fa6f3260e198cf6144e44bc9d3e1390",
];
const PATCHES: &[(&str, u64, &str)] = &[
    (
        "android/security/libpng-ownership/0001-1e67678cb923d1b224bd768a987951b1995b9f5d.patch",
        3853,
        "269007b2ea1d0306f53e5ff825804d8eef398d2d58237cdbf343adbb7bdebeb5",
    ),
    (
        "android/security/libpng-ownership/0002-d4c64e23f33097bd9440181cbba39677345529ba.patch",
        1202,
        "9196ff4297dd46a623923b7b71361b7b379c7a7666ea8cddfebf3cbd29f2e049",
    ),
    (
        "android/security/libpng-ownership/0003-4312997903c32f588780d73c225d7a7045decde0.patch",
        5065,
        "b5213ecf98b6d045c1d53b8abaa33487de09ed32c694c8710e50979c81a2bc5c",
    ),
    (
        "android/security/libpng-ownership/0004-81e0588c9fa6f3260e198cf6144e44bc9d3e1390.patch",
        843,
        "97898d809fbc6f7a45b66c418599a5d401c9d761a0f9fbfba414f0f1c02a6a17",
    ),
];
const ORIGINALS: &[(&str, u64, &str)] = &[
    (
        "pngread.c",
        141758,
        "c12022962f04abe1f7156753315bf68091398711025450803d0506dcefda3552",
    ),
    (
        "pngrtran.c",
        171557,
        "459764ff11de7d7f9db6be3fc10861d4902b4459dfe9f04719dc8d48b2102d9f",
    ),
    (
        "pngrutil.c",
        153123,
        "2042d92c70b587a4ad2cf98f0e74279b12ceb11a88fd1f6622306928c9af68fd",
    ),
    (
        "pngset.c",
        57534,
        "9bd59a79669db37b2ecc481439481eb5f49bf77bee0de4b1aba649915609b3d0",
    ),
    (
        "pngwrite.c",
        78658,
        "2fef768041d8e4676e500a63fde87e2eceec6bc892bba53ec0b96981669daa98",
    ),
];
const FIXED: &[(&str, u64, &str)] = &[
    (
        "pngread.c",
        141831,
        "2baf700d970d5b0aec4e65d697c88cd6705ee890db58f6e1daba1a8010c3c097",
    ),
    (
        "pngrtran.c",
        172472,
        "3ad540901bc41f9f6bcf3294f3d84e32d69620faf21c90fbfd857b6b1804485e",
    ),
    (
        "pngrutil.c",
        152234,
        "15034d2dc6faa272956760c1af48f9fea1db16e5ed3aef48b1e335b229583346",
    ),
    (
        "pngset.c",
        58671,
        "6b673b0324495abc603ddf012b7aa62ac975f028ec3eeff5f10b65e17d9f7612",
    ),
    (
        "pngwrite.c",
        78985,
        "25516314bcfc1480d3808e1465e700ab5610422b6855f62ac364343730aa4150",
    ),
];
const BP: (&str, u64, &str) = (
    "Android.bp",
    4344,
    "d8c18a4d178b7223d820d0d186b548a7f006462f86cc98625299245e954aad10",
);

/// The normal vendor image producer must use the same official five-file projection.
pub(super) fn required_for_targets(targets: &[&str]) -> bool {
    targets
        .iter()
        .any(|name| matches!(*name, "libpng" | "pngtest" | "vendorimage"))
}

pub(super) fn validate_request(request: FixedProductionRequest<'_>, product: &str) -> Result<()> {
    request.validate(product)?;
    if !required_for_targets(request.requested_targets())
        || !(matches!(request, FixedProductionRequest::LibpngSecurityOnAudioSource)
            || request.source_mode() == SoongDependencyMode::Strict)
    {
        return fail("libpng production requires an actual library or vendor image target");
    }
    Ok(())
}

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

fn original_path(root: &Path, relative: &str) -> Result<PathBuf> {
    if !root.is_absolute() || root.canonicalize()? != root {
        return fail("libpng source and recipe roots must be canonical absolute directories");
    }
    let mut path = root.to_path_buf();
    for component in Path::new(relative).components() {
        if !matches!(component, std::path::Component::Normal(_)) {
            return fail("libpng input must have only confined relative components");
        }
        path.push(component.as_os_str());
        let meta = fs::symlink_metadata(&path)?;
        if meta.file_type().is_symlink() {
            return fail("libpng original input or parent is an alias");
        }
    }
    Ok(path)
}

fn exact(root: &Path, relative: &str, bytes: u64, expected: &str) -> Result<PathBuf> {
    let path = original_path(root, relative)?;
    let before = fs::symlink_metadata(&path)?;
    if !before.is_file()
        || before.nlink() != 1
        || before.mode() & 0o111 != 0
        || before.len() != bytes
        || hash(&path)? != expected
    {
        return fail(format!(
            "libpng original or official fixed input differs: {relative}"
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
        return fail("libpng input changed during complete verification");
    }
    Ok(path)
}

fn original_bp(source: &Path) -> Result<()> {
    exact(source, &format!("{PROJECT}/{}", BP.0), BP.1, BP.2)?;
    Ok(())
}

pub(super) fn validate_original(repo: &Path, source: &Path) -> Result<()> {
    for (relative, bytes, expected) in ORIGINALS {
        exact(source, &format!("{PROJECT}/{relative}"), *bytes, expected)?;
    }
    original_bp(source)?;
    for (relative, bytes, expected) in PATCHES {
        exact(repo, relative, *bytes, expected)?;
    }
    Ok(())
}

fn validate_fixed(source: &Path) -> Result<()> {
    for (relative, bytes, expected) in FIXED {
        exact(source, &format!("{PROJECT}/{relative}"), *bytes, expected)?;
    }
    original_bp(source)
}

pub(super) fn project(projection: &mut Projection, repo: &Path, source: &Path) -> Result<()> {
    validate_original(repo, source)?;
    // Capture all five original bodies, modes and nanosecond mtimes before
    // the first patch. Later patches may touch the same file more than once.
    for (relative, _, _) in ORIGINALS {
        projection.save(&source.join(PROJECT).join(relative))?;
    }
    for (relative, _, _) in PATCHES {
        projection.patch(source, PROJECT, &repo.join(relative))?;
    }
    validate_fixed(source)
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
    validate_fixed(source)?;
    validate_request(request, product)?;
    let mut inputs = request.description(product)?;
    let mut patches = Vec::new();
    for (number, (relative, bytes, expected)) in PATCHES.iter().enumerate() {
        let path = exact(repo, relative, *bytes, expected)?;
        patches.push(
            serde_json::json!({"path": path, "bytes": bytes, "sha256": expected,
            "official_commit": COMMITS[number]}),
        );
    }
    let effective: Vec<_> = FIXED.iter().map(|(relative, bytes, expected)|
        serde_json::json!({"path": source.join(PROJECT).join(relative), "bytes": bytes, "sha256": expected})).collect();
    inputs["schema"] = "droidloom-libpng-security-inputs-v1".into();
    inputs["CVE"] = "CVE-2026-58936".into();
    inputs["source_lock"] = serde_json::json!({"path": lock, "sha256": hash(lock)?});
    inputs["original_project_pin"] = ORIGINAL_PIN.into();
    inputs["first_official_fix_parent"] = FIRST_PARENT.into();
    inputs["original_project_pin_is_first_fix_parent"] = false.into();
    inputs["all_five_original_files_equal_official_patch_preimages"] = true.into();
    inputs["official_patches_in_order"] = patches.into();
    inputs["effective_upstream_files"] = effective.into();
    inputs["original_Android_bp_sha256"] = BP.2.into();
    inputs["effective_projection"] = projection.effective_inventory(repo, source)?;
    inputs["strict_allow_missing_dependencies"] = "false".into();
    inputs["selinux_ignore_neverallows"] = "false".into();
    inputs["regression_executed"] = false.into();
    inputs["vendor_artifact_identity_qualified"] = false.into();
    inputs["whole_security_bulletin_qualified"] = false.into();
    let path = out.join("droidloom-libpng-security-inputs.json");
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
    let input = out.join("droidloom-libpng-security-inputs.json");
    write(
        &out.join("droidloom-libpng-security-normal-result.json"),
        serde_json::to_vec_pretty(&serde_json::json!({
            "schema": "droidloom-libpng-security-normal-result-v1", "CVE": "CVE-2026-58936",
            "inputs": {"path": input, "sha256": hash(&input)?}, "requested_targets": request.requested_targets(),
            "product": product, "normal_command_returned_success": true,
            "all_five_original_source_files_restored": true, "original_Android_bp_preserved": true,
            "source_release": PRODUCTION_TARGET_RELEASE, "build_variant": PRODUCTION_BUILD_VARIANT,
            "QPR1_source_identity_claim": false, "vendor_artifact_identity_qualified": false,
            "regression_executed": false, "binary_semantic_fix_qualified": false,
            "whole_security_bulletin_qualified": false, "runtime_qualified": false, "production_ready": false,
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
        for (name, body) in [
            (
                "pngread.c",
                include_bytes!("../../../android/security/libpng-fixtures/pngread.c").as_slice(),
            ),
            (
                "pngrtran.c",
                include_bytes!("../../../android/security/libpng-fixtures/pngrtran.c").as_slice(),
            ),
            (
                "pngrutil.c",
                include_bytes!("../../../android/security/libpng-fixtures/pngrutil.c").as_slice(),
            ),
            (
                "pngset.c",
                include_bytes!("../../../android/security/libpng-fixtures/pngset.c").as_slice(),
            ),
            (
                "pngwrite.c",
                include_bytes!("../../../android/security/libpng-fixtures/pngwrite.c").as_slice(),
            ),
            (
                "Android.bp",
                include_bytes!("../../../android/security/libpng-fixtures/Android.bp").as_slice(),
            ),
        ] {
            write(&source.join(PROJECT).join(name), body).unwrap();
        }
        for (name, body) in [
            ("android/security/libpng-ownership/0001-1e67678cb923d1b224bd768a987951b1995b9f5d.patch", include_bytes!("../../../android/security/libpng-ownership/0001-1e67678cb923d1b224bd768a987951b1995b9f5d.patch").as_slice()),
            ("android/security/libpng-ownership/0002-d4c64e23f33097bd9440181cbba39677345529ba.patch", include_bytes!("../../../android/security/libpng-ownership/0002-d4c64e23f33097bd9440181cbba39677345529ba.patch").as_slice()),
            ("android/security/libpng-ownership/0003-4312997903c32f588780d73c225d7a7045decde0.patch", include_bytes!("../../../android/security/libpng-ownership/0003-4312997903c32f588780d73c225d7a7045decde0.patch").as_slice()),
            ("android/security/libpng-ownership/0004-81e0588c9fa6f3260e198cf6144e44bc9d3e1390.patch", include_bytes!("../../../android/security/libpng-ownership/0004-81e0588c9fa6f3260e198cf6144e44bc9d3e1390.patch").as_slice()),
        ] {
            write(&repo.join(name), body).unwrap();
        }
        (repo, source)
    }

    #[test]
    fn libpng_official_four_patch_chain_recovers_all_five_originals() {
        for prefix in 0..=4 {
            let d = tempfile::tempdir().unwrap();
            let (repo, source) = fixture(d.path());
            let mut before = Vec::new();
            for (number, (relative, _, _)) in ORIGINALS.iter().enumerate() {
                let path = source.join(PROJECT).join(relative);
                fs::set_permissions(
                    &path,
                    fs::Permissions::from_mode(if number % 2 == 0 { 0o600 } else { 0o640 }),
                )
                .unwrap();
                let modified = std::time::UNIX_EPOCH
                    + std::time::Duration::new(1_700_000_001, 987_654_321 + number as u32);
                fs::File::open(&path)
                    .unwrap()
                    .set_modified(modified)
                    .unwrap();
                before.push((
                    path.clone(),
                    fs::metadata(&path).unwrap().permissions().mode(),
                    modified,
                ));
            }
            let journal = d.path().join("source-projection.json");
            let mut projection = Projection::new(journal.clone()).unwrap();
            if prefix == 4 {
                project(&mut projection, &repo, &source).unwrap();
                validate_fixed(&source).unwrap();
            } else {
                validate_original(&repo, &source).unwrap();
                for (relative, _, _) in ORIGINALS {
                    projection
                        .save(&source.join(PROJECT).join(relative))
                        .unwrap();
                }
                for (relative, _, _) in PATCHES.iter().take(prefix) {
                    projection
                        .patch(&source, PROJECT, &repo.join(relative))
                        .unwrap();
                }
            }
            assert_eq!(projection.originals.len(), 5);
            assert!(
                projection
                    .originals
                    .iter()
                    .all(|row| row.path.parent() == Some(source.join(PROJECT).as_path()))
            );
            if prefix % 2 == 0 {
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
    fn libpng_changed_original_patch_alias_hardlink_or_mode_is_rejected() {
        for which in 0..14 {
            let d = tempfile::tempdir().unwrap();
            let (repo, source) = fixture(d.path());
            validate_original(&repo, &source).unwrap();
            let path = if which < 5 {
                source.join(PROJECT).join(ORIGINALS[which].0)
            } else if which < 9 {
                repo.join(PATCHES[which - 5].0)
            } else if which == 9 {
                source.join(PROJECT).join(BP.0)
            } else {
                source.join(PROJECT).join(ORIGINALS[0].0)
            };
            if which < 10 {
                let mut changed = fs::read(&path).unwrap();
                changed.push(b'\n');
                fs::write(&path, changed).unwrap();
            } else if which == 10 {
                let target = d.path().join("aliased-original");
                fs::rename(&path, &target).unwrap();
                std::os::unix::fs::symlink(target, &path).unwrap();
            } else if which == 11 {
                fs::hard_link(&path, d.path().join("second-link")).unwrap();
            } else if which == 12 {
                fs::set_permissions(&path, fs::Permissions::from_mode(0o700)).unwrap();
            } else {
                let target = d.path().join("aliased-project");
                fs::rename(source.join(PROJECT), &target).unwrap();
                std::os::unix::fs::symlink(target, source.join(PROJECT)).unwrap();
            }
            let journal = d.path().join("source-projection.json");
            let mut projection = Projection::new(journal.clone()).unwrap();
            assert!(project(&mut projection, &repo, &source).is_err());
            assert!(projection.originals.is_empty());
            assert!(!journal.exists());
        }
    }

    #[test]
    fn libpng_default_vendor_image_uses_actual_targets_and_strict_user_command() {
        let d = tempfile::tempdir().unwrap();
        let request =
            FixedProductionRequest::Existing(SoongDependencyMode::Strict, crate::android::TARGETS);
        assert!(request.requested_targets().contains(&"vendorimage"));
        assert!(required_for_targets(request.requested_targets()));
        validate_request(request, "droidloom_x86_64").unwrap();
        let targets = request.soong_targets(d.path(), "droidloom_x86_64").unwrap();
        assert!(targets.contains(&PathBuf::from("vendorimage")));
        let mut command = production_soong_command(
            d.path(),
            d.path(),
            d.path(),
            "droidloom_x86_64",
            1,
            &targets,
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
                    .any(|(k, v)| k == key && v == Some(std::ffi::OsStr::new(value)))
            );
        }
        assert_eq!(
            request.description("droidloom_x86_64").unwrap()["requested_targets"],
            serde_json::json!(crate::android::TARGETS)
        );
    }

    #[test]
    fn vendor_image_and_default_full_select_the_complete_production651_profile() {
        let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../..")
            .canonicalize()
            .unwrap();
        let request = FixedProductionRequest::VendorImageOnProductionSource;
        assert!(request.uses_production_full_source());
        assert_eq!(
            request.source_lock(&repo).unwrap(),
            repo.join(production_source::LOCK_PATH)
        );
        assert_ne!(
            request.source_lock(&repo).unwrap(),
            FixedProductionRequest::NativePair
                .source_lock(&repo)
                .unwrap()
        );
        assert_eq!(request.projection_targets(), crate::android::TARGETS);
        assert_eq!(request.requested_targets(), ["vendorimage", "secilc"]);
        assert_eq!(request.source_mode(), SoongDependencyMode::Strict);
        assert_eq!(
            request
                .soong_targets(Path::new("/not-executed"), "droidloom_x86_64")
                .unwrap(),
            [PathBuf::from("vendorimage"), PathBuf::from("secilc")]
        );
        assert!(request.validate("another_product").is_err());
        let full =
            FixedProductionRequest::Existing(SoongDependencyMode::Strict, crate::android::TARGETS);
        assert_eq!(
            full.source_lock(&repo).unwrap(),
            request.source_lock(&repo).unwrap()
        );
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
                    .any(|(k, v)| k == key && v == Some(std::ffi::OsStr::new(value)))
            );
        }
    }

    #[test]
    fn libpng_fixed_request_keeps_strict_user_source_and_original_targets() {
        const PROBE: &str = "DROIDLOOM_TEST_LIBPNG_SECURITY_ENV_CHILD";
        if std::env::var_os(PROBE).is_none() {
            let child = Command::new(std::env::current_exe().unwrap())
                .args(["--exact", "android::libpng_security::tests::libpng_fixed_request_keeps_strict_user_source_and_original_targets", "--test-threads=1"])
                .env(PROBE, "1").env("TARGET_BUILD_VARIANT", "eng").env("TARGET_RELEASE", "cp3a")
                .env("ALLOW_MISSING_DEPENDENCIES", "true").env("SELINUX_IGNORE_NEVERALLOWS", "true")
                .output().unwrap();
            assert!(
                child.status.success(),
                "{}",
                String::from_utf8_lossy(&child.stderr)
            );
            assert!(String::from_utf8_lossy(&child.stdout).contains("1 passed; 0 failed"));
            return;
        }
        let request = FixedProductionRequest::LibpngSecurityOnAudioSource;
        assert_eq!(
            request.source_mode(),
            SoongDependencyMode::AudioApexTargetClosure
        );
        assert_eq!(
            request.projection_targets(),
            ["com.android.hardware.audio.droidloom"]
        );
        assert_eq!(request.requested_targets(), TARGETS);
        assert_eq!(
            request
                .soong_targets(Path::new("/not-executed"), "droidloom_x86_64")
                .unwrap(),
            [PathBuf::from("libpng"), PathBuf::from("pngtest")]
        );
        assert!(request.validate("another_product").is_err());
        let d = tempfile::tempdir().unwrap();
        let executable = d.path().join("soong_ui");
        fs::write(&executable, b"#!/bin/sh\nset -eu\nprintf '%s\\n' \"$TARGET_BUILD_VARIANT\" \"$TARGET_RELEASE\" \"$ALLOW_MISSING_DEPENDENCIES\" \"$SELINUX_IGNORE_NEVERALLOWS\" \"$@\"\n").unwrap();
        fs::set_permissions(&executable, fs::Permissions::from_mode(0o700)).unwrap();
        let targets = request.soong_targets(d.path(), "droidloom_x86_64").unwrap();
        let mut command = production_soong_command(
            d.path(),
            d.path(),
            d.path(),
            "droidloom_x86_64",
            2,
            &targets,
        )
        .unwrap();
        request
            .configure_dependencies(&mut command, "droidloom_x86_64")
            .unwrap();
        let output = command.output().unwrap();
        assert!(output.status.success());
        assert_eq!(
            output.stdout,
            b"user\ncp2a\nfalse\nfalse\n--make-mode\n-j2\nlibpng\npngtest\n"
        );
        assert_eq!(PRODUCTION_TARGET_RELEASE, "cp2a");
        assert_eq!(PRODUCTION_BUILD_VARIANT, "user");
        assert_ne!(ORIGINAL_PIN, FIRST_PARENT);
        assert_eq!(
            request.description("droidloom_x86_64").unwrap()["runtime_qualified"],
            false
        );
    }
}
