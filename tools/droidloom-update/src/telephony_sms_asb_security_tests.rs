use super::*;
use std::os::unix::fs::{PermissionsExt, symlink};

const BEFORE: &[u8] = include_bytes!(
    "../../../android/security/telephony-sms-asb/fixtures/SmsUsageMonitor.before.java"
);
const AFTER: &[u8] = include_bytes!(
    "../../../android/security/telephony-sms-asb/fixtures/SmsUsageMonitor.after.java"
);
const TEST_BEFORE: &[u8] = include_bytes!(
    "../../../android/security/telephony-sms-asb/fixtures/SmsUsageMonitorShortCodeTest.before.java"
);
const TEST_AFTER: &[u8] = include_bytes!(
    "../../../android/security/telephony-sms-asb/fixtures/SmsUsageMonitorShortCodeTest.after.java"
);
const PROVIDER_BP: &[u8] =
    include_bytes!("../../../android/security/telephony-sms-asb/fixtures/Android.bp");
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
    write(&source.join(PROJECT).join(TEST), TEST_BEFORE).unwrap();
    write(&source.join(PROJECT).join("Android.bp"), PROVIDER_BP).unwrap();
    fs::create_dir_all(&out).unwrap();
    fs::create_dir_all(journal.parent().unwrap()).unwrap();
    (source, out, journal)
}

// This private byte string exercises artifact identity only. It is not a JAR,
// Android build, DEX execution, official device test, signing or runtime evidence.
fn output_fixture(out: &Path) -> Value {
    let root = out.join("target/product").join(PRODUCT);
    let jar = root.join("system/framework/telephony-common.jar");
    write(&jar, b"synthetic ordinary artifact identity fixture").unwrap();
    let info = json!({
        "telephony-common": {"path": [PROJECT], "installed": [jar]}
    });
    write(
        &root.join("module-info.json"),
        serde_json::to_vec(&info).unwrap(),
    )
    .unwrap();
    info
}

#[test]
fn telephony_sms_official_patch_is_exact_and_journal_recovers_both_originals() {
    // Every combination of the three original providers is restored, including
    // the sparse checkout's all-absent state and partial prior materialization.
    for presence in 0u8..8 {
        let temporary = tempfile::tempdir().unwrap();
        let root = temporary.path().canonicalize().unwrap();
        let (source, _, journal) = fixture(&root);
        let java = source.join(PROJECT).join(JAVA);
        let test = source.join(PROJECT).join(TEST);
        let modified = std::time::UNIX_EPOCH + std::time::Duration::new(1_700_000_003, 123_456_789);
        let mut original_paths = vec![java.clone(), test.clone()];
        for (index, provider) in PROVIDERS.iter().enumerate() {
            if presence & (1 << index) != 0 {
                let path = source.join(PROJECT).join(provider.relative);
                write(&path, provider.bytes).unwrap();
                original_paths.push(path);
            }
        }
        for path in &original_paths {
            fs::set_permissions(path, fs::Permissions::from_mode(0o640)).unwrap();
            fs::File::open(path)
                .unwrap()
                .set_modified(modified)
                .unwrap();
        }
        let before = originals(&repo(), &source).unwrap();
        let mut projection = Projection::new(journal.clone()).unwrap();
        project(&mut projection, &repo(), &source).unwrap();
        assert_eq!(fs::read(&java).unwrap(), AFTER);
        assert_eq!(fs::read(&test).unwrap(), TEST_AFTER);
        let remembered = decode_projection_journal(&fs::read(&journal).unwrap(), &source).unwrap();
        assert_eq!(remembered.len(), 5);
        for (path, body) in [(&java, BEFORE), (&test, TEST_BEFORE)] {
            let original = remembered.iter().find(|item| item.path == *path).unwrap();
            assert_eq!(original.bytes.as_deref(), Some(body));
        }
        for (index, provider) in PROVIDERS.iter().enumerate() {
            let path = source.join(PROJECT).join(provider.relative);
            let original = remembered.iter().find(|item| item.path == path).unwrap();
            assert_eq!(fs::read(&path).unwrap(), provider.bytes);
            if presence & (1 << index) != 0 {
                assert_eq!(original.bytes.as_deref(), Some(provider.bytes));
            } else {
                assert!(original.bytes.is_none());
                assert!(original.permissions_mode.is_none());
                assert!(original.modified.is_none());
            }
        }
        assert_eq!(
            projection.applied_patches.get(&repo().join(PATCH)),
            Some(&PATCH_SHA.to_owned())
        );
        projection.stabilize_all().unwrap();
        fs::write(&java, b"interrupted private Java projection").unwrap();
        fs::write(&test, b"interrupted private test projection").unwrap();
        for provider in PROVIDERS {
            fs::write(
                source.join(PROJECT).join(provider.relative),
                b"interrupted private provider",
            )
            .unwrap();
        }
        std::mem::forget(projection);
        recover(&journal, &source).unwrap();
        restored(&before.original_java).unwrap();
        restored(&before.original_test).unwrap();
        for original in &before.original_blueprints {
            recheck(original).unwrap();
        }
        for (provider, original) in PROVIDERS.iter().zip(&before.original_providers) {
            match original {
                Some(reference) => {
                    restored(reference).unwrap();
                }
                None => assert!(optional_provider(&source, provider).unwrap().is_none()),
            }
        }
        assert_eq!(fs::read(&java).unwrap(), BEFORE);
        assert_eq!(fs::read(&test).unwrap(), TEST_BEFORE);
        assert!(!journal.exists());
    }
}
#[test]
fn telephony_sms_changed_originals_recipe_and_aliases_fail_before_source_writes() {
    for mutation in 0..13 {
        let temporary = tempfile::tempdir().unwrap();
        let root = temporary.path().canonicalize().unwrap();
        let (source, _, journal) = fixture(&root);
        let recipe = root.join("recipe");
        write(&recipe.join(PATCH), fs::read(repo().join(PATCH)).unwrap()).unwrap();
        for provider in PROVIDERS {
            write(&recipe.join(provider.recipe), provider.bytes).unwrap();
        }
        let java = source.join(PROJECT).join(JAVA);
        let test = source.join(PROJECT).join(TEST);
        let blueprint = source.join(PROJECT).join("Android.bp");
        match mutation {
            0 => fs::write(&java, b"foreign complete Java").unwrap(),
            1 => fs::write(&test, b"foreign complete test").unwrap(),
            2 => fs::write(&blueprint, b"foreign normal module provider").unwrap(),
            3 => fs::write(recipe.join(PATCH), b"changed official patch").unwrap(),
            4 => {
                fs::remove_file(&java).unwrap();
                symlink(
                    repo().join(
                        "android/security/telephony-sms-asb/fixtures/SmsUsageMonitor.before.java",
                    ),
                    &java,
                )
                .unwrap();
            }
            5 => fs::hard_link(&java, root.join("second-java-name")).unwrap(),
            6 => {
                fs::remove_file(&test).unwrap();
                symlink(repo().join("android/security/telephony-sms-asb/fixtures/SmsUsageMonitorShortCodeTest.before.java"), &test).unwrap();
            }
            7 => fs::hard_link(&test, root.join("second-test-name")).unwrap(),
            8 => fs::write(
                recipe.join(PROVIDERS[0].recipe),
                b"changed supplemental recipe",
            )
            .unwrap(),
            9 => write(
                &source.join(PROJECT).join(PROVIDERS[1].relative),
                b"foreign existing provider",
            )
            .unwrap(),
            10 => symlink(
                recipe.join(PROVIDERS[0].recipe),
                source.join(PROJECT).join(PROVIDERS[0].relative),
            )
            .unwrap(),
            11 => fs::hard_link(
                recipe.join(PROVIDERS[2].recipe),
                source.join(PROJECT).join(PROVIDERS[2].relative),
            )
            .unwrap(),
            _ => fs::remove_file(recipe.join(PROVIDERS[2].recipe)).unwrap(),
        }
        let provider_before: Vec<_> = PROVIDERS
            .iter()
            .map(|provider| {
                let path = source.join(PROJECT).join(provider.relative);
                match fs::symlink_metadata(&path) {
                    Ok(meta) => Some((identity(&meta).unwrap(), fs::read(&path).unwrap())),
                    Err(error) if error.kind() == std::io::ErrorKind::NotFound => None,
                    Err(error) => panic!("{error}"),
                }
            })
            .collect();
        let before = [
            fs::read(&java).unwrap(),
            fs::read(&test).unwrap(),
            fs::read(&blueprint).unwrap(),
        ];
        let mut projection = Projection::new(journal.clone()).unwrap();
        assert!(
            project(&mut projection, &recipe, &source).is_err(),
            "{mutation}"
        );
        assert!(projection.originals.is_empty());
        assert!(projection.applied_patches.is_empty());
        assert!(!journal.exists());
        assert_eq!(fs::read(&java).unwrap(), before[0]);
        assert_eq!(fs::read(&test).unwrap(), before[1]);
        assert_eq!(fs::read(&blueprint).unwrap(), before[2]);
        for (provider, original) in PROVIDERS.iter().zip(provider_before) {
            let path = source.join(PROJECT).join(provider.relative);
            match original {
                Some((id, bytes)) => {
                    assert_eq!(identity(&fs::symlink_metadata(&path).unwrap()).unwrap(), id);
                    assert_eq!(fs::read(&path).unwrap(), bytes);
                }
                None => assert!(optional_provider(&source, provider).unwrap().is_none()),
            }
        }
    }
}

#[test]
fn telephony_sms_journal_failure_does_not_modify_either_original_source() {
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
    assert_eq!(
        fs::read(source.join(PROJECT).join(TEST)).unwrap(),
        TEST_BEFORE
    );
    for provider in PROVIDERS {
        assert!(optional_provider(&source, provider).unwrap().is_none());
    }
    fs::remove_dir(&journal).unwrap();
}

#[test]
fn telephony_sms_requests_use_existing_complete_product_and_unchanged_651_lock() {
    validate_request(request(), PRODUCT).unwrap();
    validate_source_lock(&repo(), &repo().join(production_source::LOCK_PATH)).unwrap();
    assert_eq!(
        hash(&repo().join(production_source::LOCK_PATH)).unwrap(),
        production_source::LOCK_SHA
    );
    assert!(validate_request(request(), "droidloom_arm64").is_err());
    let component_only = FixedProductionRequest::Existing(
        SoongDependencyMode::Strict,
        &["telephony-common", "module-info"],
    );
    assert!(validate_request(component_only, PRODUCT).is_err());
    for missing in ["telephony-common", "module-info"] {
        let targets: Vec<_> = TARGETS
            .iter()
            .copied()
            .filter(|name| *name != missing)
            .collect();
        let partial = FixedProductionRequest::Existing(SoongDependencyMode::Strict, &targets);
        assert!(validate_request(partial, PRODUCT).is_err(), "{missing}");
    }
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
            .any(|(key, _)| key.to_string_lossy().starts_with("RELEASE_"))
    );
}

#[test]
fn telephony_sms_artifact_metadata_rejects_wrong_provider_alias_and_foreign_jar() {
    for mutation in 0..7 {
        let temporary = tempfile::tempdir().unwrap();
        let root = temporary.path().canonicalize().unwrap();
        let (_, out, _) = fixture(&root);
        let mut info = output_fixture(&out);
        completed_artifacts(&out, PRODUCT).unwrap();
        let product = out.join("target/product").join(PRODUCT);
        let jar = product.join("system/framework/telephony-common.jar");
        match mutation {
            0 => info["telephony-common"]["path"] = json!(["foreign/provider"]),
            1 => info["telephony-common"]["path"] = json!([PROJECT, "foreign/provider"]),
            2 => info["telephony-common"]["installed"] = json!([jar.clone(), jar.clone()]),
            3 => {
                info["telephony-common"]["installed"] =
                    json!(["system/framework/telephony-common.jar"])
            }
            4 => {
                let saved = root.join("synthetic-artifact");
                fs::rename(&jar, &saved).unwrap();
                symlink(&saved, &jar).unwrap();
            }
            5 => info["telephony-common"]["installed"] = json!([root.join("foreign.jar")]),
            _ => fs::write(&jar, b"").unwrap(),
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
fn telephony_sms_normal_receipt_requires_both_restored_originals_and_unqualified_scope() {
    for tamper in 0..5 {
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
        assert_eq!(recorded["effective_test"]["sha256"], FIXED_TEST_SHA);
        assert_eq!(recorded["source_project_revision"], PROJECT_PIN);
        assert_eq!(recorded["original_source_lock_changed"], false);
        assert_eq!(recorded["additional_inputs_in_original_sparse_lock"], false);
        let providers = recorded["additional_original_provider_inputs"]
            .as_array()
            .unwrap();
        assert_eq!(providers.len(), 3);
        for (record, provider) in providers.iter().zip(PROVIDERS) {
            assert_eq!(record["project_relative_path"], provider.relative);
            assert_eq!(record["source_project_revision"], PROJECT_PIN);
            assert_eq!(record["original_git_blob"], provider.git_blob);
            assert_eq!(record["originally_absent"], true);
            assert_eq!(record["effective"]["sha256"], provider.sha256);
        }
        assert_eq!(
            recorded["required_system_image_member"],
            "framework/telephony-common.jar"
        );
        if tamper != 2 {
            projection.restore().unwrap();
            restored(&before.original_java).unwrap();
            restored(&before.original_test).unwrap();
        }
        for original in &before.original_blueprints {
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
            restored(&before.original_test).unwrap();
        } else if tamper == 3 {
            fs::write(&before.original_test.path, b"changed restored test only").unwrap();
            restored(&before.original_java).unwrap();
            assert!(normal_result(&repo(), &source, &out, PRODUCT, request(), input).is_err());
            assert!(!out.join(NORMAL).exists());
            fs::write(&before.original_test.path, TEST_BEFORE).unwrap();
            fs::File::open(&before.original_test.path)
                .unwrap()
                .set_modified(
                    std::time::UNIX_EPOCH
                        + std::time::Duration::from_nanos(before.original_test.identity[7]),
                )
                .unwrap();
            restored(&before.original_test).unwrap();
        } else if tamper == 4 {
            let path = source.join(PROJECT).join(PROVIDERS[0].relative);
            write(&path, PROVIDERS[0].bytes).unwrap();
            assert!(normal_result(&repo(), &source, &out, PRODUCT, request(), input).is_err());
            assert!(!out.join(NORMAL).exists());
            fs::remove_file(&path).unwrap();
        } else {
            normal_result(&repo(), &source, &out, PRODUCT, request(), input).unwrap();
            let result: Value =
                serde_json::from_slice(&fs::read(out.join(NORMAL)).unwrap()).unwrap();
            assert_eq!(result["inputs"]["sha256"], input_ref.sha256);
            assert_eq!(
                result["original_source_bytes_mode_mtime_and_absence_restored"],
                true
            );
            let providers = result["restored_supplemental_providers"]
                .as_array()
                .unwrap();
            assert_eq!(providers.len(), 3);
            for provider in providers {
                assert_eq!(provider["originally_absent"], true);
                assert!(provider["restored"].is_null());
            }
            assert_eq!(
                result["system_image_JAR_verification_required_by_complete_normal"],
                true
            );
            for field in [
                "source_inode_or_ctime_restoration_claim",
                "telephony_feature_flags_overridden",
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
        assert_eq!(
            fs::read(source.join(PROJECT).join(TEST)).unwrap(),
            TEST_BEFORE
        );
        for provider in PROVIDERS {
            assert!(optional_provider(&source, provider).unwrap().is_none());
        }
        assert!(!journal.exists());
    }
}
