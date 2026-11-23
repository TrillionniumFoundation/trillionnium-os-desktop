use super::*;
use std::os::unix::fs::{PermissionsExt, symlink};

const BEFORE: &[u8] =
    include_bytes!("../../../android/security/profiling-asb/fixtures/ProfilingService.before.java");
const AFTER: &[u8] =
    include_bytes!("../../../android/security/profiling-asb/fixtures/ProfilingService.after.java");
const SERVICE_BP: &[u8] =
    include_bytes!("../../../android/security/profiling-asb/fixtures/service.Android.bp");
const APEX_BP: &[u8] = include_bytes!(
    "../../../android/native-generation-pair/apex-provider-fixtures/Profiling.Android.bp"
);
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
    write(&source.join(PROJECT).join("service/Android.bp"), SERVICE_BP).unwrap();
    write(&source.join(PROJECT).join("apex/Android.bp"), APEX_BP).unwrap();
    fs::create_dir_all(&out).unwrap();
    fs::create_dir_all(journal.parent().unwrap()).unwrap();
    (source, out, journal)
}

// These bytes exercise only metadata/artifact binding. They are not an APEX,
// an Android build, a DEX semantic test, a signing result or runtime evidence.
fn output_fixture(out: &Path) -> Value {
    let root = out.join("target/product").join(PRODUCT);
    let apex = root.join("system/apex/com.android.profiling.apex");
    write(&apex, b"synthetic ordinary container identity fixture").unwrap();
    let info = json!({
        "com.android.profiling": {"path": ["packages/modules/Profiling/apex"], "installed": [apex]},
        "service-profiling": {"path": ["packages/modules/Profiling/service"]}
    });
    write(
        &root.join("module-info.json"),
        serde_json::to_vec(&info).unwrap(),
    )
    .unwrap();
    info
}

#[test]
fn profiling_official_patch_is_exact_and_journal_recovers_one_original() {
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
    for original in &before.original_blueprints {
        recheck(original).unwrap();
    }
    assert_eq!(fs::read(&java).unwrap(), BEFORE);
    assert!(!journal.exists());
}

#[test]
fn profiling_changed_originals_recipe_and_aliases_fail_before_source_writes() {
    for mutation in 0..6 {
        let temporary = tempfile::tempdir().unwrap();
        let root = temporary.path().canonicalize().unwrap();
        let (source, _, journal) = fixture(&root);
        let recipe = root.join("recipe");
        write(&recipe.join(PATCH), fs::read(repo().join(PATCH)).unwrap()).unwrap();
        let java = source.join(PROJECT).join(JAVA);
        let service_bp = source.join(PROJECT).join("service/Android.bp");
        let apex_bp = source.join(PROJECT).join("apex/Android.bp");
        match mutation {
            0 => fs::write(&java, b"foreign complete source").unwrap(),
            1 => fs::write(&service_bp, b"foreign service provider").unwrap(),
            2 => fs::write(recipe.join(PATCH), b"changed official patch").unwrap(),
            3 => {
                fs::remove_file(&java).unwrap();
                symlink(
                    repo().join(
                        "android/security/profiling-asb/fixtures/ProfilingService.before.java",
                    ),
                    &java,
                )
                .unwrap();
            }
            4 => fs::hard_link(&java, root.join("second-java-name")).unwrap(),
            _ => fs::write(&apex_bp, b"foreign APEX provider").unwrap(),
        }
        let before = [
            fs::read(&java).unwrap(),
            fs::read(&service_bp).unwrap(),
            fs::read(&apex_bp).unwrap(),
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
        assert_eq!(fs::read(&service_bp).unwrap(), before[1]);
        assert_eq!(fs::read(&apex_bp).unwrap(), before[2]);
    }
}

#[test]
fn profiling_journal_failure_does_not_modify_the_original_source() {
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
fn profiling_requests_use_existing_complete_product_and_unchanged_651_lock() {
    validate_request(request(), PRODUCT).unwrap();
    validate_source_lock(&repo(), &repo().join(production_source::LOCK_PATH)).unwrap();
    assert_eq!(
        hash(&repo().join(production_source::LOCK_PATH)).unwrap(),
        production_source::LOCK_SHA
    );
    assert!(validate_request(request(), "droidloom_arm64").is_err());
    let component_only = FixedProductionRequest::Existing(
        SoongDependencyMode::Strict,
        &["com.android.profiling", "service-profiling", "module-info"],
    );
    assert!(validate_request(component_only, PRODUCT).is_err());
    for missing in ["com.android.profiling", "service-profiling", "module-info"] {
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
            .any(|(key, _)| key == "RELEASE_PACKAGE_PROFILING_MODULE"
                || key == "RELEASE_ANOMALY_DETECTOR")
    );
}

#[test]
fn profiling_artifact_metadata_rejects_wrong_provider_alias_and_ambiguous_container() {
    for mutation in 0..6 {
        let temporary = tempfile::tempdir().unwrap();
        let root = temporary.path().canonicalize().unwrap();
        let (_, out, _) = fixture(&root);
        let mut info = output_fixture(&out);
        completed_artifacts(&out, PRODUCT).unwrap();
        let product = out.join("target/product").join(PRODUCT);
        let apex = product.join("system/apex/com.android.profiling.apex");
        match mutation {
            0 => info["service-profiling"]["path"] = json!(["foreign/service"]),
            1 => {
                info["com.android.profiling"]["path"] =
                    json!(["packages/modules/Profiling/apex", "foreign/apex"])
            }
            2 => info["com.android.profiling"]["installed"] = json!([apex.clone(), apex.clone()]),
            3 => {
                info["com.android.profiling"]["installed"] = json!([
                    apex.clone(),
                    product.join("system/apex/com.android.profiling.capex")
                ])
            }
            4 => {
                let saved = root.join("synthetic-container");
                fs::rename(&apex, &saved).unwrap();
                symlink(&saved, &apex).unwrap();
            }
            _ => info["com.android.profiling"]["installed"] = json!([root.join("foreign.apex")]),
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
fn profiling_normal_receipt_requires_restoration_and_preserves_unqualified_scope() {
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
        assert_eq!(
            recorded["required_APEX_payload_members"],
            json!(crate::coherent_images::PROFILING_APEX_MEMBERS)
        );
        if tamper != 2 {
            projection.restore().unwrap();
            restored(&before.original_java).unwrap();
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
        } else {
            normal_result(&repo(), &source, &out, PRODUCT, request(), input).unwrap();
            let result: Value =
                serde_json::from_slice(&fs::read(out.join(NORMAL)).unwrap()).unwrap();
            assert_eq!(result["inputs"]["sha256"], input_ref.sha256);
            assert_eq!(result["original_source_bytes_mode_mtime_restored"], true);
            assert_eq!(
                result["APEX_payload_verification_required_by_complete_normal"],
                true
            );
            for field in [
                "source_inode_or_ctime_restoration_claim",
                "Profiling_release_flags_overridden",
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
