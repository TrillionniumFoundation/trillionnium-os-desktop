//! Apply the complete upstream AAC reset-ownership correction through the normal journal.
//! The selected source stays at its original pin; the four upstream files are a
//! temporary, recoverable build projection. No APEX installation occurs here.
use super::*;
use std::os::unix::fs::MetadataExt;

pub(super) const TARGETS: &[&str] = &["com.android.media.swcodec", "libSBRdec_test"];
const PROJECT: &str = "external/aac";
const PATCH: &str = "android/security/0002-aac-reset-ownership.patch";
const PATCH_SHA: &str = "ab9f6ad9fc6bc32825ef2c3ae4e88e6aea7e5a1e3c43a379fb9b50665ac3eb7d";
const COMMIT: &str = "6b8c6cbab2b747ffc0c39721ca18651cddc8a373";
const PARENT: &str = "41f344ffc0bacea87cac5bb1756bd40761265d1e";
const TEST: &str = "cpp/libSBRdec/tests/libSBRdec_test.cpp";
const ORIGINALS: &[(&str, u64, &str)] = &[
    ("cpp/Android.bp", 1636, "3cdd1f65bb8de19ee91b131aac2e7a290528bcc601d283678f7e7215310bfbbe"),
    ("cpp/libSBRdec/src/psdec.cpp", 27371, "a38554afdf0d02c0388c934be163e56066410a6ce55f512d8c2191588610e987"),
    ("cpp/libSBRdec/src/sbrdecoder.cpp", 65966, "6a0f806599be04f3e658953484f6f2cc7e06c9941cb7b9235d036db8435fb7df"),
];
const FIXED: &[(&str, u64, &str)] = &[
    ("cpp/Android.bp", 2113, "9d820e211a87fee61bb9449d346b2be0a464b3ba5a723f824e5c02fd37d2bcc9"),
    ("cpp/libSBRdec/src/psdec.cpp", 27498, "63d58b903db01bde2c0bf281abb8fbf6d352a2ded8d9893ad9edd7a3cc12dab6"),
    ("cpp/libSBRdec/src/sbrdecoder.cpp", 66018, "af68a4e9e589618e59957947d964afaa3f3173244aee03614d9f524e11f4a665"),
    (TEST, 2170, "67c67bdfffe4215f860ac798d6bffd25bdec493597958c49b395de2696c98078"),
];

fn original_path(root: &Path, relative: &str) -> Result<PathBuf> {
    if !root.is_absolute() || root.canonicalize()? != root {
        return fail("AAC source and recipe roots must be canonical absolute directories");
    }
    let mut path = root.to_path_buf();
    for component in Path::new(relative).components() {
        if !matches!(component, std::path::Component::Normal(_)) {
            return fail("AAC input path must have only original relative components");
        }
        path.push(component.as_os_str());
        match fs::symlink_metadata(&path) {
            Ok(meta) if meta.file_type().is_symlink() => return fail("AAC input parent or file is an alias"),
            Ok(_) => (),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => (),
            Err(error) => return Err(error.into()),
        }
    }
    Ok(path)
}

fn exact(root: &Path, relative: &str, bytes: u64, expected: &str) -> Result<PathBuf> {
    let path = original_path(root, relative)?;
    let before = fs::symlink_metadata(&path)?;
    if !before.is_file() || before.nlink() != 1 || before.len() != bytes || hash(&path)? != expected {
        return fail(format!("AAC original or official fixed input differs: {relative}"));
    }
    let after = fs::symlink_metadata(&path)?;
    let identity = |m: &fs::Metadata| (m.dev(), m.ino(), m.mode(), m.uid(), m.gid(), m.nlink(),
        m.len(), (m.mtime(), m.mtime_nsec()), (m.ctime(), m.ctime_nsec()));
    if identity(&before) != identity(&after) {
        return fail("AAC input changed during complete verification");
    }
    Ok(path)
}

pub(super) fn validate_original(repo: &Path, source: &Path) -> Result<()> {
    for (relative, bytes, expected) in ORIGINALS {
        exact(source, &format!("{PROJECT}/{relative}"), *bytes, expected)?;
    }
    exact(repo, PATCH, 4443, PATCH_SHA)?;
    let added = original_path(source, &format!("{PROJECT}/{TEST}"))?;
    match fs::symlink_metadata(added) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error.into()),
        Ok(_) => fail("AAC official new test already exists in the original source"),
    }
}

pub(super) fn project(projection: &mut Projection, repo: &Path, source: &Path) -> Result<()> {
    validate_original(repo, source)?;
    projection.patch(source, PROJECT, &repo.join(PATCH))?;
    for (relative, bytes, expected) in FIXED {
        exact(source, &format!("{PROJECT}/{relative}"), *bytes, expected)?;
    }
    Ok(())
}

pub(super) fn input_receipt(
    repo: &Path, source: &Path, lock: &Path, out: &Path, product: &str, projection: &Projection,
) -> Result<PathBuf> {
    let mut inputs = FixedProductionRequest::AacSecurityOnAudioSource.description(product)?;
    let mut effective = Vec::new();
    for (relative, bytes, expected) in FIXED {
        let path = exact(source, &format!("{PROJECT}/{relative}"), *bytes, expected)?;
        effective.push(serde_json::json!({"path": path, "bytes": bytes, "sha256": expected}));
    }
    inputs["schema"] = "droidloom-aac-security-inputs-v1".into();
    inputs["CVE"] = "CVE-2026-58876".into();
    inputs["source_lock"] = serde_json::json!({"path": lock, "sha256": hash(lock)?});
    inputs["official_patch"] = serde_json::json!({"path": repo.join(PATCH), "sha256": PATCH_SHA,
        "commit": COMMIT, "parent": PARENT, "original_project_pin": PARENT});
    inputs["effective_upstream_files"] = effective.into();
    inputs["effective_projection"] = projection.effective_inventory(repo, source)?;
    inputs["strict_allow_missing_dependencies"] = "false".into();
    inputs["selinux_ignore_neverallows"] = "false".into();
    inputs["official_regression_executed"] = false.into();
    inputs["production_signing_qualified"] = false.into();
    inputs["whole_security_bulletin_qualified"] = false.into();
    let path = out.join("droidloom-aac-security-inputs.json");
    write(&path, serde_json::to_vec_pretty(&inputs)?)?;
    Ok(path)
}

pub(super) fn normal_result(repo: &Path, source: &Path, out: &Path, product: &str) -> Result<()> {
    validate_original(repo, source)?;
    let input = out.join("droidloom-aac-security-inputs.json");
    write(&out.join("droidloom-aac-security-normal-result.json"),
        serde_json::to_vec_pretty(&serde_json::json!({
            "schema": "droidloom-aac-security-normal-result-v1", "CVE": "CVE-2026-58876",
            "inputs": {"path": input, "sha256": hash(&input)?}, "requested_targets": TARGETS,
            "product": product, "normal_command_returned_success": true,
            "original_source_files_restored": true, "source_release": PRODUCTION_TARGET_RELEASE,
            "build_variant": PRODUCTION_BUILD_VARIANT, "QPR1_source_identity_claim": false,
            "artifact_identity_qualified": false, "official_regression_executed": false,
            "binary_semantic_fix_qualified": false, "production_signing_qualified": false,
            "whole_security_bulletin_qualified": false, "runtime_qualified": false,
            "production_ready": false,
        }))?)?;
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
            ("cpp/Android.bp", include_bytes!("../../../android/security/aac-fixtures/cpp/Android.bp").as_slice()),
            ("cpp/libSBRdec/src/psdec.cpp", include_bytes!("../../../android/security/aac-fixtures/cpp/libSBRdec/src/psdec.cpp").as_slice()),
            ("cpp/libSBRdec/src/sbrdecoder.cpp", include_bytes!("../../../android/security/aac-fixtures/cpp/libSBRdec/src/sbrdecoder.cpp").as_slice()),
        ] {
            write(&source.join(PROJECT).join(name), bytes).unwrap();
        }
        write(&repo.join(PATCH), include_bytes!("../../../android/security/0002-aac-reset-ownership.patch")).unwrap();
        (repo, source)
    }

    #[test]
    fn aac_official_four_file_patch_recovers_originals_after_interruption() {
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
            assert_eq!(projection.originals.len(), 4);
            if interrupted {
                std::mem::forget(projection);
                recover(&journal, &source).unwrap();
            } else {
                projection.restore().unwrap();
            }
            validate_original(&repo, &source).unwrap();
            for (path, mode, modified) in before {
                let after = fs::metadata(&path).unwrap();
                assert_eq!(after.permissions().mode(), mode);
                assert_eq!(after.modified().unwrap(), modified);
            }
            assert!(!journal.exists());
            assert!(!source.join(PROJECT).join(TEST).exists());
        }
    }

    #[test]
    fn aac_changed_original_patch_alias_or_preexisting_test_is_rejected() {
        for which in 0..6 {
            let d = tempfile::tempdir().unwrap();
            let (repo, source) = fixture(d.path());
            validate_original(&repo, &source).unwrap();
            let path = if which < 3 { source.join(PROJECT).join(ORIGINALS[which].0) }
                else if which == 3 { repo.join(PATCH) } else { source.join(PROJECT).join(TEST) };
            if which < 4 {
                let mut changed = fs::read(&path).unwrap();
                changed.push(b'\n');
                fs::write(&path, changed).unwrap();
            } else {
                fs::create_dir_all(path.parent().unwrap()).unwrap();
                if which == 4 { fs::write(&path, b"foreign test").unwrap(); }
                else { std::os::unix::fs::symlink(repo.join(PATCH), &path).unwrap(); }
            }
            let journal = d.path().join("source-projection.json");
            let mut projection = Projection::new(journal.clone()).unwrap();
            assert!(project(&mut projection, &repo, &source).is_err());
            assert!(!journal.exists());
            assert!(projection.originals.is_empty());
        }
    }

    #[test]
    fn aac_fixed_request_keeps_strict_user_source_and_official_targets() {
        const PROBE: &str = "DROIDLOOM_TEST_AAC_SECURITY_ENV_CHILD";
        if std::env::var_os(PROBE).is_none() {
            let child = Command::new(std::env::current_exe().unwrap())
                .args(["--exact", "android::aac_security::tests::aac_fixed_request_keeps_strict_user_source_and_official_targets", "--test-threads=1"])
                .env(PROBE, "1").env("TARGET_BUILD_VARIANT", "eng").env("TARGET_RELEASE", "cp3a")
                .env("ALLOW_MISSING_DEPENDENCIES", "true").env("SELINUX_IGNORE_NEVERALLOWS", "true")
                .output().unwrap();
            assert!(child.status.success(), "{}", String::from_utf8_lossy(&child.stderr));
            assert!(String::from_utf8_lossy(&child.stdout).contains("1 passed; 0 failed"));
            return;
        }
        let request = FixedProductionRequest::AacSecurityOnAudioSource;
        assert_eq!(request.source_mode(), SoongDependencyMode::AudioApexTargetClosure);
        assert_eq!(request.projection_targets(), ["com.android.hardware.audio.droidloom"]);
        assert_eq!(request.requested_targets(), TARGETS);
        assert!(request.validate("droidloom_arm64").is_err());
        let d = tempfile::tempdir().unwrap();
        let executable = d.path().join("soong_ui");
        fs::write(&executable, b"#!/bin/sh\nset -eu\nprintf '%s\\n' \"$TARGET_BUILD_VARIANT\" \"$TARGET_RELEASE\" \"$ALLOW_MISSING_DEPENDENCIES\" \"$SELINUX_IGNORE_NEVERALLOWS\" \"$@\"\n").unwrap();
        fs::set_permissions(&executable, fs::Permissions::from_mode(0o700)).unwrap();
        let targets = request.soong_targets(d.path(), "droidloom_x86_64").unwrap();
        let mut command = production_soong_command(d.path(), d.path(), d.path(), "droidloom_x86_64", 2, &targets).unwrap();
        request.configure_dependencies(&mut command, "droidloom_x86_64").unwrap();
        let output = command.output().unwrap();
        assert!(output.status.success());
        assert_eq!(output.stdout, b"user\ncp2a\nfalse\nfalse\n--make-mode\n-j2\ncom.android.media.swcodec\nlibSBRdec_test\n");
    }
}
