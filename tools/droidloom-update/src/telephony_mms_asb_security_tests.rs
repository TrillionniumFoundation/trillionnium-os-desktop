use super::*;
use std::os::unix::fs::{PermissionsExt, symlink};

const BEFORE: &[u8] =
    include_bytes!("../../../android/security/telephony-mms-asb/fixtures/MmsProvider.before.java");
const AFTER: &[u8] =
    include_bytes!("../../../android/security/telephony-mms-asb/fixtures/MmsProvider.after.java");
const DEPENDENCY_FIXTURES: &[(&str, &[u8])] = &[
    (
        "Android.bp",
        include_bytes!("../../../android/security/telephony-mms-asb/fixtures/Android.bp"),
    ),
    (
        "AndroidManifest.xml",
        include_bytes!("../../../android/security/telephony-mms-asb/fixtures/AndroidManifest.xml"),
    ),
    (
        "AndroidManifestHsum.xml",
        include_bytes!(
            "../../../android/security/telephony-mms-asb/fixtures/AndroidManifestHsum.xml"
        ),
    ),
    (
        "src/com/android/providers/telephony/ProviderUtil.java",
        include_bytes!("../../../android/security/telephony-mms-asb/fixtures/ProviderUtil.java"),
    ),
];
const PRODUCT: &str = "droidloom_x86_64";

fn repo() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap()
}

fn request() -> FixedProductionRequest<'static> {
    FixedProductionRequest::Existing(SoongDependencyMode::Strict, TARGETS)
}

fn fixture(root: &Path) -> (PathBuf, PathBuf, PathBuf) {
    let source = root.join("source");
    let out = root.join("out");
    let journal = root.join("work/source-projection.json");
    write(&source.join(PROJECT).join(JAVA), BEFORE).unwrap();
    for (relative, body) in DEPENDENCY_FIXTURES {
        write(&source.join(PROJECT).join(relative), body).unwrap();
    }
    fs::create_dir_all(&out).unwrap();
    fs::create_dir_all(journal.parent().unwrap()).unwrap();
    (source, out, journal)
}

// These bytes exercise only metadata/artifact binding. They are not an APK,
// an Android build, provider request, DEX test, signing result or runtime evidence.
fn output_fixture(out: &Path) -> Value {
    let root = out.join("target/product").join(PRODUCT);
    let apk = root.join(INSTALLED_APK);
    write(&apk, b"synthetic ordinary APK identity fixture").unwrap();
    let info = json!({"TelephonyProvider": {"path": [PROJECT], "installed": [apk]}});
    write(
        &root.join("module-info.json"),
        serde_json::to_vec(&info).unwrap(),
    )
    .unwrap();
    info
}

#[test]
fn telephony_mms_official_patch_is_exact_and_journal_recovers_one_original() {
    // Static source assertions only: do not invoke an Android provider.
    assert_eq!(BEFORE.len() as u64, ORIGINAL_BYTES);
    assert_eq!(AFTER.len() as u64, FIXED_BYTES);
    assert_eq!(hex::encode(Sha256::digest(BEFORE)), ORIGINAL_SHA);
    assert_eq!(hex::encode(Sha256::digest(AFTER)), FIXED_SHA);
    let original = std::str::from_utf8(BEFORE).unwrap();
    let fixed = std::str::from_utf8(AFTER).unwrap();
    assert!(original.contains("if (table.equals(TABLE_PDU)) {\n            if (!ProviderUtil.allowInteractingWithEntryOfSubscription"));
    assert!(!fixed.contains("if (table.equals(TABLE_PDU)) {\n            if (!ProviderUtil.allowInteractingWithEntryOfSubscription"));
    assert!(fixed.contains("if (!ProviderUtil.allowInteractingWithEntryOfSubscription(\n                getContext(), subId, callerUserHandle))"));
    let guard = fixed
        .find("if (!ProviderUtil.allowInteractingWithEntryOfSubscription(")
        .unwrap();
    let table_branch = fixed[guard..]
        .find("if (table.equals(TABLE_PDU)) {")
        .unwrap()
        + guard;
    assert!(guard < table_branch);
    assert!(fixed[guard..table_branch].contains("return null;"));
    assert_eq!(DEPENDENCY_FIXTURES.len(), DEPENDENCIES.len());
    for ((path, body), (expected_path, size, sha)) in DEPENDENCY_FIXTURES.iter().zip(DEPENDENCIES) {
        assert_eq!(path, expected_path);
        assert_eq!(body.len() as u64, *size);
        assert_eq!(hex::encode(Sha256::digest(body)), *sha);
    }
    let temporary = tempfile::tempdir().unwrap();
    let root = temporary.path().canonicalize().unwrap();
    let (source, _, journal) = fixture(&root);
    let java = source.join(PROJECT).join(JAVA);
    let modified = std::time::UNIX_EPOCH + std::time::Duration::new(1_700_000_003, 123_456_789);
    fs::set_permissions(&java, fs::Permissions::from_mode(0o640)).unwrap();
    fs::File::open(&java)
        .unwrap()
        .set_modified(modified)
        .unwrap();
    let before = originals(&repo(), &source).unwrap();
    let mut projection = Projection::new(journal.clone()).unwrap();
    project(&mut projection, &repo(), &source).unwrap();
    assert_eq!(fs::read(&java).unwrap(), AFTER);
    let remembered = decode_projection_journal(&fs::read(&journal).unwrap(), &source).unwrap();
    assert_eq!(remembered.len(), 1);
    assert_eq!(remembered[0].path, java);
    assert_eq!(remembered[0].bytes.as_deref(), Some(BEFORE));
    assert_eq!(
        projection.applied_patches.get(&repo().join(PATCH)),
        Some(&PATCH_SHA.to_owned())
    );
    projection.stabilize_all().unwrap();
    fs::write(&java, b"interrupted private source projection").unwrap();
    std::mem::forget(projection);
    recover(&journal, &source).unwrap();
    restored(&before.original_java).unwrap();
    for original in &before.original_dependencies {
        recheck(original).unwrap();
    }
    assert_eq!(fs::read(&java).unwrap(), BEFORE);
    assert!(!journal.exists());
}

#[test]
fn telephony_mms_changed_originals_recipe_and_aliases_fail_before_source_writes() {
    for mutation in 0..8 {
        let temporary = tempfile::tempdir().unwrap();
        let root = temporary.path().canonicalize().unwrap();
        let (source, _, journal) = fixture(&root);
        let recipe = root.join("recipe");
        write(&recipe.join(PATCH), fs::read(repo().join(PATCH)).unwrap()).unwrap();
        let java = source.join(PROJECT).join(JAVA);
        let dependencies: Vec<_> = DEPENDENCIES
            .iter()
            .map(|(path, _, _)| source.join(PROJECT).join(path))
            .collect();
        match mutation {
            0 => fs::write(&java, b"foreign complete source").unwrap(),
            1 => fs::write(&dependencies[0], b"foreign source provider").unwrap(),
            2 => fs::write(recipe.join(PATCH), b"changed production patch").unwrap(),
            3 => {
                fs::remove_file(&java).unwrap();
                symlink(
                    repo().join(
                        "android/security/telephony-mms-asb/fixtures/MmsProvider.before.java",
                    ),
                    &java,
                )
                .unwrap();
            }
            4 => fs::hard_link(&java, root.join("second-java-name")).unwrap(),
            5 => fs::write(&dependencies[1], b"foreign manifest").unwrap(),
            6 => fs::write(&dependencies[2], b"foreign HSUM manifest").unwrap(),
            _ => fs::write(&dependencies[3], b"changed subscription policy").unwrap(),
        }
        let paths: Vec<_> = std::iter::once(java).chain(dependencies).collect();
        let before: Vec<_> = paths.iter().map(|p| fs::read(p).unwrap()).collect();
        let mut projection = Projection::new(journal.clone()).unwrap();
        assert!(
            project(&mut projection, &recipe, &source).is_err(),
            "{mutation}"
        );
        assert!(projection.originals.is_empty());
        assert!(projection.applied_patches.is_empty());
        assert!(!journal.exists());
        for (path, expected) in paths.iter().zip(before) {
            assert_eq!(fs::read(path).unwrap(), expected);
        }
    }
}

#[test]
fn telephony_mms_journal_failure_does_not_modify_the_original_source() {
    let temporary = tempfile::tempdir().unwrap();
    let root = temporary.path().canonicalize().unwrap();
    let (source, _, journal) = fixture(&root);
    fs::create_dir(&journal).unwrap();
    let mut projection = Projection {
        journal: journal.clone(),
        originals: Vec::new(),
        applied_patches: BTreeMap::new(),
    };
    assert!(project(&mut projection, &repo(), &source).is_err());
    assert!(projection.originals.is_empty());
    assert!(projection.applied_patches.is_empty());
    assert_eq!(fs::read(source.join(PROJECT).join(JAVA)).unwrap(), BEFORE);
    // Avoid asking Drop to remove the deliberately invalid journal directory.
    fs::remove_dir(&journal).unwrap();
}

#[test]
fn telephony_mms_requests_use_existing_complete_product_and_unchanged_651_lock() {
    validate_request(request(), PRODUCT).unwrap();
    validate_source_lock(&repo(), &repo().join(production_source::LOCK_PATH)).unwrap();
    assert_eq!(
        hash(&repo().join(production_source::LOCK_PATH)).unwrap(),
        production_source::LOCK_SHA
    );
    assert!(validate_request(request(), "droidloom_arm64").is_err());
    let component_only = FixedProductionRequest::Existing(
        SoongDependencyMode::Strict,
        &["TelephonyProvider", "module-info"],
    );
    assert!(validate_request(component_only, PRODUCT).is_err());
    for missing in ["TelephonyProvider", "module-info"] {
        let targets: Vec<_> = TARGETS
            .iter()
            .copied()
            .filter(|name| *name != missing)
            .collect();
        let partial = FixedProductionRequest::Existing(SoongDependencyMode::Strict, &targets);
        assert!(validate_request(partial, PRODUCT).is_err(), "{missing}");
    }
    let mut with_hsum = TARGETS.to_vec();
    with_hsum.push("TelephonyProviderHsum");
    assert!(required_for_targets(&["TelephonyProviderHsum"]));
    assert!(
        validate_request(
            FixedProductionRequest::Existing(SoongDependencyMode::Strict, &with_hsum),
            PRODUCT
        )
        .is_err()
    );
    let mut duplicate = TARGETS.to_vec();
    duplicate.push("TelephonyProvider");
    assert!(
        validate_request(
            FixedProductionRequest::Existing(SoongDependencyMode::Strict, &duplicate),
            PRODUCT
        )
        .is_err()
    );
    let mut command = Command::new("not-executed");
    configure_command(request(), PRODUCT, &mut command).unwrap();
    for key in ["ALLOW_MISSING_DEPENDENCIES", "SELINUX_IGNORE_NEVERALLOWS"] {
        assert!(
            command
                .get_envs()
                .any(|(name, value)| name == key && value == Some(std::ffi::OsStr::new("false")))
        );
    }
    assert!(
        !command
            .get_envs()
            .any(|(key, _)| key == "PRODUCT_USE_HSUM" || key == "PRODUCT_PACKAGES")
    );
}

#[test]
fn telephony_mms_artifact_metadata_rejects_wrong_provider_variant_and_aliases() {
    for mutation in 0..9 {
        let temporary = tempfile::tempdir().unwrap();
        let root = temporary.path().canonicalize().unwrap();
        let (_, out, _) = fixture(&root);
        let mut info = output_fixture(&out);
        completed_artifacts(&out, PRODUCT).unwrap();
        let product = out.join("target/product").join(PRODUCT);
        let apk = product.join(INSTALLED_APK);
        match mutation {
            0 => info["TelephonyProvider"]["path"] = json!(["foreign/provider"]),
            1 => info["TelephonyProvider"]["path"] = json!([PROJECT, "foreign/provider"]),
            2 => info["TelephonyProvider"]["installed"] = json!([apk.clone(), apk.clone()]),
            3 => {
                info["TelephonyProvider"]["installed"] =
                    json!([product
                        .join("system/priv-app/TelephonyProviderHsum/TelephonyProviderHsum.apk")])
            }
            4 => {
                let saved = root.join("synthetic-apk");
                fs::rename(&apk, &saved).unwrap();
                symlink(&saved, &apk).unwrap();
            }
            5 => info["TelephonyProvider"]["installed"] = json!([root.join("foreign.apk")]),
            6 => info["TelephonyProvider"]["installed"] = json!([42]),
            7 => fs::write(&apk, b"").unwrap(),
            _ => fs::hard_link(&apk, root.join("second-apk-name")).unwrap(),
        }
        write(
            &product.join("module-info.json"),
            serde_json::to_vec(&info).unwrap(),
        )
        .unwrap();
        assert!(completed_artifacts(&out, PRODUCT).is_err(), "{mutation}");
    }
}

#[test]
fn telephony_mms_normal_receipt_requires_restoration_and_preserves_unqualified_scope() {
    for tamper in 0..3 {
        let temporary = tempfile::tempdir().unwrap();
        let root = temporary.path().canonicalize().unwrap();
        let (source, out, journal) = fixture(&root);
        let before = originals(&repo(), &source).unwrap();
        let mut projection = Projection::new(journal.clone()).unwrap();
        let projected = project(&mut projection, &repo(), &source).unwrap();
        projection.stabilize_all().unwrap();
        let input = input_receipt(
            &repo(),
            &source,
            &repo().join(production_source::LOCK_PATH),
            &out,
            PRODUCT,
            request(),
            &projection,
            projected,
        )
        .unwrap();
        let input_ref = input.reference.clone();
        let recorded: Value = serde_json::from_slice(&fs::read(&input_ref.path).unwrap()).unwrap();
        assert_eq!(recorded["effective_java"]["sha256"], FIXED_SHA);
        assert_eq!(recorded["source_project_revision"], PROJECT_PIN);
        assert_eq!(recorded["original_source_lock_changed"], false);
        assert_eq!(recorded["required_installed_APK"], INSTALLED_APK);
        assert_eq!(
            recorded["required_normal_modules"],
            json!(["TelephonyProvider"])
        );
        assert_eq!(recorded["official_test_hunks_included"], false);
        if tamper != 2 {
            projection.restore().unwrap();
            restored(&before.original_java).unwrap();
        }
        for original in &before.original_dependencies {
            recheck(original).unwrap();
        }
        output_fixture(&out);
        if tamper == 1 {
            fs::write(&input_ref.path, b"changed private input receipt").unwrap();
            assert!(normal_result(&repo(), &source, &out, PRODUCT, request(), input).is_err());
            assert!(!out.join(NORMAL).exists());
        } else if tamper == 2 {
            assert!(normal_result(&repo(), &source, &out, PRODUCT, request(), input).is_err());
            assert!(!out.join(NORMAL).exists());
            projection.restore().unwrap();
            restored(&before.original_java).unwrap();
        } else {
            normal_result(&repo(), &source, &out, PRODUCT, request(), input).unwrap();
            let result: Value =
                serde_json::from_slice(&fs::read(out.join(NORMAL)).unwrap()).unwrap();
            assert_eq!(result["inputs"]["sha256"], input_ref.sha256);
            assert_eq!(result["original_source_bytes_mode_mtime_restored"], true);
            assert_eq!(
                result["installed_APK_verification_required_by_complete_normal"],
                true
            );
            for field in [
                "source_inode_or_ctime_restoration_claim",
                "subscription_policy_or_HSUM_selection_overridden",
                "headless_system_user_variant_qualified",
                "QPR1_source_identity_claim",
                "artifact_identity_qualified",
                "binary_semantic_fix_qualified",
                "official_device_tests_executed",
                "production_signing_qualified",
                "whole_CVE_qualified",
                "runtime_qualified",
                "production_ready",
            ] {
                assert_eq!(result[field], false, "{field}");
            }
            recheck(&input_ref).unwrap();
        }
        assert_eq!(fs::read(source.join(PROJECT).join(JAVA)).unwrap(), BEFORE);
        assert!(!journal.exists());
    }
}
