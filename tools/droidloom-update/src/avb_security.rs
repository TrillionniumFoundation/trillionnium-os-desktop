//! Apply the complete upstream AVB allocation-failure correction to every
//! production651 projection, including transitive libavb consumers. The project
//! revision and Android.bp remain unchanged; projection v2 restores the original
//! body, permissions and nanosecond modification time.
use super::*;
use std::os::unix::fs::MetadataExt;

const PROJECT: &str = "external/avb";
const ORIGINAL_PIN: &str = "ba2dec4b035b0a3b61c5f8f8a74d86bcd450b1ee";
const COMMITS: &[&str] = &["2264ece3807d01298a23e5ef3cafa6de3772b994"];
const ALTERNATE_COMMIT: &str = "119d66ea37241def63e715658ac02c414bd3d0e5";
const PATCHES: &[(&str, u64, &str)] = &[(
    "android/security/avb-rsa/2264ece3807d01298a23e5ef3cafa6de3772b994.patch",
    1199,
    "fe9f6e5906f7bba4985036d5848ab7afc3f7cb3c5a0c268fe87036e55bf91edc",
)];
const ORIGINALS: &[(&str, u64, &str)] = &[(
    "libavb/avb_rsa.c",
    33474,
    "cd2d62fe8107bf72632d64d80a95a78c6d93ff4c25ab2b490824c21d21e874d3",
)];
const FIXED: &[(&str, u64, &str)] = &[(
    "libavb/avb_rsa.c",
    33612,
    "1820b82a68e77b70732e50918927bd2bfc37855c6ca7285bdd1b30f425e60151",
)];
const BP: (&str, u64, &str) = (
    "Android.bp",
    11126,
    "c383995eff501f09a7041dab473748c5e05baa6c3fe5b987e8bb3af68c5580d7",
);

pub(super) fn validate_request(request: FixedProductionRequest<'_>, product: &str) -> Result<()> {
    request.validate(product)?;
    if !request.uses_production_full_source()
        || request.source_mode() != SoongDependencyMode::Strict
    {
        return fail("AVB security projection requires the complete strict production651 source");
    }
    Ok(())
}

pub(super) fn validate_source_lock(repo: &Path, lock: &Path) -> Result<()> {
    if lock != production_source::source_lock_path(repo)? {
        return fail("AVB security projection lost the original production651 source lock");
    }
    let value: serde_json::Value = serde_json::from_slice(&fs::read(lock)?)?;
    let projects = value["projects"]
        .as_array()
        .ok_or("AVB source projects missing")?;
    let selected: Vec<_> = projects
        .iter()
        .filter(|row| row["path"] == PROJECT)
        .collect();
    if selected.len() != 1 || selected[0]["commit"] != ORIGINAL_PIN {
        return fail("AVB original production project revision differs");
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
        return fail("avb source and recipe roots must be canonical absolute directories");
    }
    let mut path = root.to_path_buf();
    for component in Path::new(relative).components() {
        if !matches!(component, std::path::Component::Normal(_)) {
            return fail("avb input must have only confined relative components");
        }
        path.push(component.as_os_str());
        let meta = fs::symlink_metadata(&path)?;
        if meta.file_type().is_symlink() {
            return fail("avb original input or parent is an alias");
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
            "avb original or official fixed input differs: {relative}"
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
        return fail("avb input changed during complete verification");
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
    // Capture the complete original body and metadata before the official patch.
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
    validate_source_lock(repo, lock)?;
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
    inputs["schema"] = "droidloom-avb-security-inputs-v1".into();
    inputs["CVE"] = "CVE-2026-58956".into();
    inputs["source_lock"] = serde_json::json!({"path": lock, "sha256": hash(lock)?});
    inputs["original_project_pin"] = ORIGINAL_PIN.into();
    inputs["upstream_bug"] = "A-461507723".into();
    inputs["alternate_commit_not_replayed"] = ALTERNATE_COMMIT.into();
    inputs["original_file_equals_official_patch_preimage"] = true.into();
    inputs["official_patches_in_order"] = patches.into();
    inputs["effective_upstream_files"] = effective.into();
    inputs["original_Android_bp_sha256"] = BP.2.into();
    inputs["effective_projection"] = projection.effective_inventory(repo, source)?;
    inputs["strict_allow_missing_dependencies"] = "false".into();
    inputs["selinux_ignore_neverallows"] = "false".into();
    inputs["regression_executed"] = false.into();
    inputs["artifact_identity_qualified"] = false.into();
    inputs["whole_security_bulletin_qualified"] = false.into();
    inputs["binary_semantic_fix_qualified"] = false.into();
    inputs["runtime_qualified"] = false.into();
    inputs["production_ready"] = false.into();
    let path = out.join("droidloom-avb-security-inputs.json");
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
    let input = out.join("droidloom-avb-security-inputs.json");
    write(
        &out.join("droidloom-avb-security-normal-result.json"),
        serde_json::to_vec_pretty(&serde_json::json!({
            "schema": "droidloom-avb-security-normal-result-v1", "CVE": "CVE-2026-58956",
            "inputs": {"path": input, "sha256": hash(&input)?}, "requested_targets": request.requested_targets(),
            "product": product, "normal_command_returned_success": true,
            "original_source_restored": true, "original_Android_bp_preserved": true,
            "source_release": PRODUCTION_TARGET_RELEASE, "build_variant": PRODUCTION_BUILD_VARIANT,
            "QPR1_source_identity_claim": false, "artifact_identity_qualified": false,
            "regression_executed": false, "binary_semantic_fix_qualified": false,
            "whole_security_bulletin_qualified": false, "runtime_qualified": false, "production_ready": false,
        }))?,
    )?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::{PermissionsExt, symlink};

    fn fixture(root: &Path) -> (PathBuf, PathBuf) {
        let repo = root.join("recipe");
        let source = root.join("source");
        write(
            &source.join(PROJECT).join(ORIGINALS[0].0),
            include_bytes!("../../../android/security/avb-rsa/fixtures/libavb/avb_rsa.c"),
        )
        .unwrap();
        write(
            &source.join(PROJECT).join(BP.0),
            include_bytes!("../../../android/security/avb-rsa/fixtures/Android.bp"),
        )
        .unwrap();
        write(
            &repo.join(PATCHES[0].0),
            include_bytes!(
                "../../../android/security/avb-rsa/2264ece3807d01298a23e5ef3cafa6de3772b994.patch"
            ),
        )
        .unwrap();
        (repo, source)
    }

    fn unchanged_file_identity(
        path: &Path,
    ) -> (u64, u64, u32, u32, u32, u64, u64, i64, i64, i64, i64) {
        let m = fs::symlink_metadata(path).unwrap();
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
    }

    #[test]
    fn avb_official_projection_restores_single_original_after_save_and_apply() {
        // Cover a durable save before any patch, ordinary successful restore,
        // and recovery after the official patch completed but its owner was lost.
        for stage in 0..3 {
            let d = tempfile::tempdir().unwrap();
            let (repo, source) = fixture(d.path());
            let original = source.join(PROJECT).join(ORIGINALS[0].0);
            let bp = source.join(PROJECT).join(BP.0);
            let patch = repo.join(PATCHES[0].0);
            fs::set_permissions(&original, fs::Permissions::from_mode(0o640)).unwrap();
            let modified =
                std::time::UNIX_EPOCH + std::time::Duration::new(1_700_000_123, 987_654_321);
            fs::File::open(&original)
                .unwrap()
                .set_modified(modified)
                .unwrap();
            let original_bytes = fs::read(&original).unwrap();
            let original_mode = fs::metadata(&original).unwrap().mode();
            let preserved =
                [&bp, &patch].map(|p| (fs::read(p).unwrap(), unchanged_file_identity(p)));
            let journal = d.path().join("source-projection.json");
            let mut projection = Projection::new(journal.clone()).unwrap();
            if stage == 0 {
                validate_original(&repo, &source).unwrap();
                projection.save(&original).unwrap();
                assert!(projection.applied_patches.is_empty());
            } else {
                project(&mut projection, &repo, &source).unwrap();
                validate_fixed(&source).unwrap();
                assert_eq!(projection.applied_patches.len(), 1);
                assert_eq!(
                    projection.applied_patches.get(&patch).unwrap(),
                    PATCHES[0].2
                );
                assert_ne!(fs::read(&original).unwrap(), original_bytes);
            }
            assert_eq!(projection.originals.len(), 1);
            assert_eq!(projection.originals[0].path, original);
            let saved = decode_projection_journal(&fs::read(&journal).unwrap(), &source).unwrap();
            assert_eq!(saved.len(), 1);
            assert_eq!(saved[0].bytes.as_ref().unwrap(), &original_bytes);
            assert_eq!(saved[0].permissions_mode, Some(original_mode));
            assert_eq!(saved[0].modified, Some(modified));
            if stage == 1 {
                projection.restore().unwrap();
            } else {
                std::mem::forget(projection);
                recover(&journal, &source).unwrap();
            }
            validate_original(&repo, &source).unwrap();
            assert_eq!(fs::read(&original).unwrap(), original_bytes);
            let after = fs::metadata(&original).unwrap();
            assert_eq!(after.mode(), original_mode);
            assert_eq!(after.modified().unwrap(), modified);
            for (p, before) in [&bp, &patch].into_iter().zip(preserved) {
                assert_eq!((fs::read(p).unwrap(), unchanged_file_identity(p)), before);
            }
            assert!(!journal.exists());
        }
    }
    #[test]
    fn avb_changed_inputs_alias_hardlink_and_exec_mode_fail_before_journal() {
        // Each source, unchanged build definition and official patch is checked
        // independently. A failure must not capture or mutate any input.
        for role in 0..3 {
            for kind in 0..6 {
                let d = tempfile::tempdir().unwrap();
                let (repo, source) = fixture(d.path());
                validate_original(&repo, &source).unwrap();
                let paths = [
                    source.join(PROJECT).join(ORIGINALS[0].0),
                    source.join(PROJECT).join(BP.0),
                    repo.join(PATCHES[0].0),
                ];
                let selected = &paths[role];
                match kind {
                    0 | 1 => {
                        let mut body = fs::read(selected).unwrap();
                        if kind == 0 {
                            body[0] ^= 1;
                        } else {
                            body.push(b'\n');
                        }
                        fs::write(selected, body).unwrap();
                    }
                    2 => {
                        let target = d.path().join("aliased-file");
                        fs::rename(selected, &target).unwrap();
                        symlink(target, selected).unwrap();
                    }
                    3 => {
                        let parent = selected.parent().unwrap();
                        let target = d.path().join("aliased-parent");
                        fs::rename(parent, &target).unwrap();
                        symlink(target, parent).unwrap();
                    }
                    4 => fs::hard_link(selected, d.path().join("second-link")).unwrap(),
                    5 => fs::set_permissions(selected, fs::Permissions::from_mode(0o700)).unwrap(),
                    _ => unreachable!(),
                }
                let before = paths
                    .each_ref()
                    .map(|p| (fs::read(p).unwrap(), unchanged_file_identity(p)));
                let journal = d.path().join("source-projection.json");
                let mut projection = Projection::new(journal.clone()).unwrap();
                assert!(
                    project(&mut projection, &repo, &source).is_err(),
                    "role {role} kind {kind}"
                );
                assert!(projection.originals.is_empty());
                assert!(projection.applied_patches.is_empty());
                assert!(!journal.exists());
                assert_eq!(
                    paths
                        .each_ref()
                        .map(|p| (fs::read(p).unwrap(), unchanged_file_identity(p))),
                    before
                );
            }
        }
    }
    #[test]
    fn avb_production651_requests_keep_original_lock_targets_and_strict_user() {
        const PROBE: &str = "DROIDLOOM_TEST_AVB_STRICT_ENV_CHILD";
        const CASE: &str = "android::avb_security::tests::avb_production651_requests_keep_original_lock_targets_and_strict_user";
        if std::env::var_os(PROBE).is_none() {
            let child = Command::new(std::env::current_exe().unwrap())
                .args(["--exact", CASE, "--test-threads=1"])
                .env(PROBE, "1")
                .env("TARGET_BUILD_VARIANT", "eng")
                .env("TARGET_RELEASE", "cp3a")
                .env("ALLOW_MISSING_DEPENDENCIES", "true")
                .env("SELINUX_IGNORE_NEVERALLOWS", "true")
                .output()
                .unwrap();
            assert!(
                child.status.success(),
                "{}",
                String::from_utf8_lossy(&child.stderr)
            );
            assert!(String::from_utf8_lossy(&child.stdout).contains("1 passed; 0 failed"));
            return;
        }
        let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../..")
            .canonicalize()
            .unwrap();
        let lock = production_source::source_lock_path(&repo).unwrap();
        assert_eq!(lock, repo.join(production_source::LOCK_PATH));
        assert_eq!(hash(&lock).unwrap(), production_source::LOCK_SHA);
        validate_source_lock(&repo, &lock).unwrap();
        let d = tempfile::tempdir().unwrap();
        let foreign_lock = d.path().join("copied-lock.json");
        fs::write(&foreign_lock, fs::read(&lock).unwrap()).unwrap();
        assert!(validate_source_lock(&repo, &foreign_lock).is_err());
        let native_lock = FixedProductionRequest::NativePair
            .source_lock(&repo)
            .unwrap();
        assert_ne!(native_lock, lock);
        assert!(validate_source_lock(&repo, &native_lock).is_err());
        for request in [
            FixedProductionRequest::Existing(SoongDependencyMode::Strict, crate::android::TARGETS),
            FixedProductionRequest::VendorImageOnProductionSource,
            FixedProductionRequest::WmSecurityOnProductionSource,
            FixedProductionRequest::FrameworkAsbOnProductionSource,
        ] {
            validate_request(request, "droidloom_x86_64").unwrap();
            assert!(validate_request(request, "another_product").is_err());
            assert_eq!(request.source_lock(&repo).unwrap(), lock);
            assert_eq!(request.source_mode(), SoongDependencyMode::Strict);
            let targets = request.soong_targets(d.path(), "droidloom_x86_64").unwrap();
            // Preserve the existing three APEX output selections as well as
            // every ordinary named target; AVB must not rewrite the final argv.
            let expected_targets = request.requested_targets().iter().map(|name| {
                match *name {
                    "netbpfload" => d.path().join("soong/.intermediates/packages/modules/Connectivity/bpf/loader/netbpfload/android_x86_64/netbpfload"),
                    "libservice-connectivity" => d.path().join("soong/.intermediates/packages/modules/Connectivity/service/libservice-connectivity/android_x86_64_shared/libservice-connectivity.so"),
                    "libnetd_updatable" => d.path().join("soong/.intermediates/packages/modules/Connectivity/bpf/netd/libnetd_updatable/android_x86_64_shared_cfi/libnetd_updatable.so"),
                    _ => PathBuf::from(*name),
                }
            }).collect::<Vec<_>>();
            assert_eq!(targets, expected_targets);
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
            let mut expected = vec![std::ffi::OsString::from("--make-mode"), "-j2".into()];
            expected.extend(targets.iter().map(|p| p.as_os_str().to_owned()));
            assert_eq!(
                command.get_args().collect::<Vec<_>>(),
                expected.iter().map(|s| s.as_os_str()).collect::<Vec<_>>()
            );
            assert_eq!(
                request.description("droidloom_x86_64").unwrap()["runtime_qualified"],
                false
            );
        }
        for request in [
            FixedProductionRequest::NativePair,
            FixedProductionRequest::LibpngSecurityOnAudioSource,
            FixedProductionRequest::Existing(
                SoongDependencyMode::AudioApexTargetClosure,
                &["com.android.hardware.audio.droidloom"],
            ),
        ] {
            assert!(validate_request(request, "droidloom_x86_64").is_err());
        }
    }
}
