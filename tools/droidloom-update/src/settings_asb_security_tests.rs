use super::*;
use std::os::unix::fs::{PermissionsExt, symlink};

const BEFORE: &[u8] = include_bytes!(
    "../../../android/security/settings-asb/fixtures/AddAccountSettings.before.java"
);
const AFTER: &[u8] =
    include_bytes!("../../../android/security/settings-asb/fixtures/AddAccountSettings.after.java");
const BLUEPRINT: &[u8] =
    include_bytes!("../../../android/native-generation-pair/provider-fixtures/Settings.Android.bp");
const PRODUCT: &str = "droidloom_x86_64";
const COMPONENT_TARGETS: &[&str] = &["Settings", "module-info"];

fn repo() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap()
}

fn fixture(root: &Path) -> (PathBuf, PathBuf, PathBuf) {
    let source = root.join("source");
    let out = root.join("out");
    let journal = root.join("work/source-projection.json");
    write(&source.join(PROJECT).join(JAVA), BEFORE).unwrap();
    write(&source.join(PROJECT).join("Android.bp"), BLUEPRINT).unwrap();
    fs::create_dir_all(&out).unwrap();
    fs::create_dir_all(journal.parent().unwrap()).unwrap();
    (source, out, journal)
}

fn request() -> FixedProductionRequest<'static> {
    FixedProductionRequest::Existing(SoongDependencyMode::Strict, COMPONENT_TARGETS)
}

fn assert_absent_providers(source: &Path) {
    for provider in PROVIDERS {
        let error = fs::symlink_metadata(source.join(PROJECT).join(provider.relative)).unwrap_err();
        assert_eq!(error.kind(), std::io::ErrorKind::NotFound);
    }
}

fn output_fixture(out: &Path) -> Value {
    let root = out.join("target/product").join(PRODUCT);
    let apk = root.join(INSTALLED_APK);
    write(
        &apk,
        b"ordinary artifact-identity fixture; not an executable APK",
    )
    .unwrap();
    let info = json!({"Settings": {"path": [PROJECT], "installed": [apk]}});
    write(
        &root.join("module-info.json"),
        serde_json::to_vec(&info).unwrap(),
    )
    .unwrap();
    info
}

#[test]
fn settings_official_patch_preregisters_five_paths_and_recovers_original_absence() {
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
    let original = exact(&java, ORIGINAL_BYTES, ORIGINAL_SHA).unwrap();
    let bp = exact(&source.join(PROJECT).join("Android.bp"), BP_BYTES, BP_SHA).unwrap();
    let mut projection = Projection::new(journal.clone()).unwrap();
    let projected = project(&mut projection, &repo(), &source).unwrap();
    assert_eq!(fs::read(&java).unwrap(), AFTER);
    assert_eq!(projected.original_java.sha256, ORIGINAL_SHA);
    let raw = fs::read(&journal).unwrap();
    let remembered = decode_projection_journal(&raw, &source).unwrap();
    assert_eq!(remembered.len(), 5);
    assert_eq!(
        remembered.iter().filter(|row| row.bytes.is_none()).count(),
        4
    );
    assert_eq!(
        projection.applied_patches.get(&repo().join(PATCH)),
        Some(&PATCH_SHA.to_owned())
    );
    for provider in PROVIDERS {
        assert_eq!(
            fs::read(source.join(PROJECT).join(provider.relative)).unwrap(),
            provider.bytes
        );
    }
    projection.stabilize_all().unwrap();
    // The durable journal must recover a later interrupted mutation too.
    fs::write(&java, b"incomplete private projection").unwrap();
    std::mem::forget(projection);
    recover(&journal, &source).unwrap();
    assert_eq!(fs::read(&java).unwrap(), BEFORE);
    restored(&original).unwrap();
    restored(&bp).unwrap();
    assert_absent_providers(&source);
    assert!(!journal.exists());
}

#[test]
fn settings_existing_providers_restore_metadata_and_normal_receipt_keeps_scope_false() {
    let temporary = tempfile::tempdir().unwrap();
    let root = temporary.path().canonicalize().unwrap();
    let (source, out, journal) = fixture(&root);
    for (index, provider) in PROVIDERS.iter().enumerate() {
        let path = source.join(PROJECT).join(provider.relative);
        write(&path, provider.bytes).unwrap();
        fs::set_permissions(
            &path,
            fs::Permissions::from_mode(0o640 + (index as u32 & 1)),
        )
        .unwrap();
        fs::File::open(&path)
            .unwrap()
            .set_modified(
                std::time::UNIX_EPOCH
                    + std::time::Duration::new(1_700_000_020 + index as u64, 765_432_100),
            )
            .unwrap();
    }
    let original = originals(&repo(), &source).unwrap();
    let mut projection = Projection::new(journal.clone()).unwrap();
    let projected = project(&mut projection, &repo(), &source).unwrap();
    projection.stabilize_all().unwrap();
    let lock = repo().join(production_source::LOCK_PATH);
    let input = input_receipt(
        &repo(),
        &source,
        &lock,
        &out,
        PRODUCT,
        request(),
        &projection,
        projected,
    )
    .unwrap();
    let input_ref = input.reference.clone();
    let inputs: Value = serde_json::from_slice(&fs::read(&input_ref.path).unwrap()).unwrap();
    assert_eq!(inputs["source_project_revision"], PROJECT_PIN);
    assert_eq!(inputs["additional_inputs_in_original_sparse_lock"], false);
    assert_eq!(inputs["original_source_lock_changed"], false);
    assert_eq!(
        inputs["additional_original_provider_inputs"]
            .as_array()
            .unwrap()
            .len(),
        4
    );
    assert!(
        inputs["additional_original_provider_inputs"]
            .as_array()
            .unwrap()
            .iter()
            .all(|row| row["originally_absent"] == false)
    );
    projection.restore().unwrap();
    restored(&original.original_java).unwrap();
    restored(&original.original_bp).unwrap();
    for reference in original.original_providers.iter().flatten() {
        restored(reference).unwrap();
    }
    output_fixture(&out);
    normal_result(&repo(), &source, &out, PRODUCT, request(), input).unwrap();
    let result: Value = serde_json::from_slice(&fs::read(out.join(NORMAL)).unwrap()).unwrap();
    assert_eq!(result["inputs"]["sha256"], input_ref.sha256);
    assert_eq!(
        result["APK"]["sha256"],
        hash(&out.join("target/product").join(PRODUCT).join(INSTALLED_APK)).unwrap()
    );
    assert_eq!(
        result["original_source_bytes_mode_mtime_and_absence_restored"],
        true
    );
    for field in [
        "source_inode_or_ctime_restoration_claim",
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
    assert!(!journal.exists());
}

#[test]
fn settings_changed_preimages_recipe_or_alias_fail_before_source_mutation() {
    for mutation in 0..7 {
        let temporary = tempfile::tempdir().unwrap();
        let root = temporary.path().canonicalize().unwrap();
        let (source, _, journal) = fixture(&root);
        let recipe = root.join("recipe");
        for path in std::iter::once(PATCH).chain(PROVIDERS.iter().map(|p| p.recipe)) {
            write(&recipe.join(path), fs::read(repo().join(path)).unwrap()).unwrap();
        }
        let java = source.join(PROJECT).join(JAVA);
        let provider = source.join(PROJECT).join(PROVIDERS[0].relative);
        let bp = source.join(PROJECT).join("Android.bp");
        match mutation {
            0 => fs::write(&java, b"foreign AddAccount preimage").unwrap(),
            1 => fs::write(&provider, b"foreign supplemental original").unwrap(),
            2 => fs::write(recipe.join(PATCH), b"changed official patch").unwrap(),
            3 => symlink(recipe.join(PROVIDERS[0].recipe), &provider).unwrap(),
            4 => fs::hard_link(&java, root.join("second-java-name")).unwrap(),
            5 => fs::write(&bp, b"foreign Settings build provider").unwrap(),
            _ => fs::write(
                source.join(PROJECT).join("lint-baseline.xml"),
                b"foreign lint baseline",
            )
            .unwrap(),
        }
        let before_java = fs::read(&java).unwrap();
        let before_bp = fs::read(&bp).unwrap();
        let before_provider = fs::read(&provider).ok();
        let before_lint = fs::read(source.join(PROJECT).join("lint-baseline.xml")).ok();
        let mut projection = Projection::new(journal.clone()).unwrap();
        assert!(
            project(&mut projection, &recipe, &source).is_err(),
            "{mutation}"
        );
        assert!(projection.originals.is_empty(), "{mutation}");
        assert!(projection.applied_patches.is_empty(), "{mutation}");
        assert!(!journal.exists(), "{mutation}");
        assert_eq!(fs::read(&java).unwrap(), before_java);
        assert_eq!(fs::read(&bp).unwrap(), before_bp);
        assert_eq!(fs::read(&provider).ok(), before_provider);
        assert_eq!(
            fs::read(source.join(PROJECT).join("lint-baseline.xml")).ok(),
            before_lint
        );
        for remaining in &PROVIDERS[1..3] {
            assert!(!source.join(PROJECT).join(remaining.relative).exists());
        }
    }
}

#[test]
fn settings_journal_publication_failure_precedes_all_source_writes() {
    let temporary = tempfile::tempdir().unwrap();
    let root = temporary.path().canonicalize().unwrap();
    let (source, _, _) = fixture(&root);
    let blocker = root.join("not-a-directory");
    fs::write(&blocker, b"private journal failure fixture").unwrap();
    let journal = blocker.join("source-projection.json");
    let java = exact(
        &source.join(PROJECT).join(JAVA),
        ORIGINAL_BYTES,
        ORIGINAL_SHA,
    )
    .unwrap();
    let bp = exact(&source.join(PROJECT).join("Android.bp"), BP_BYTES, BP_SHA).unwrap();
    let mut projection = Projection::new(journal).unwrap();
    assert!(project(&mut projection, &repo(), &source).is_err());
    assert!(projection.originals.is_empty());
    assert!(projection.applied_patches.is_empty());
    recheck(&java).unwrap();
    recheck(&bp).unwrap();
    assert_absent_providers(&source);
    assert_eq!(
        fs::read(blocker).unwrap(),
        b"private journal failure fixture"
    );
}

#[test]
fn settings_requests_keep_exact_651_lock_strict_user_and_actual_module_targets() {
    let recipe = repo();
    let full = FixedProductionRequest::Existing(SoongDependencyMode::Strict, super::super::TARGETS);
    for selected in [full, request()] {
        validate_request(selected, PRODUCT).unwrap();
        assert!(selected.uses_production_full_source());
        assert!(required_for_targets(selected.requested_targets()));
        let lock = selected.source_lock(&recipe).unwrap();
        assert_eq!(lock, recipe.join(production_source::LOCK_PATH));
        validate_source_lock(&recipe, &lock).unwrap();
        assert_eq!(hash(&lock).unwrap(), production_source::LOCK_SHA);
        let parsed = droidloom_source::load_lock(&lock).unwrap();
        assert_eq!(parsed.projects.len(), 653);
        let original = droidloom_source::load_lock(
            &recipe.join("android/manifest/production-full-source-lock.json"),
        )
        .unwrap();
        assert_eq!(original.projects.len(), 651);
        for (current, previous) in parsed.projects[..651].iter().zip(&original.projects) {
            // Exhaustive destructuring keeps this check tied to every
            // SparseProject field without changing the production type.
            let droidloom_source::SparseProject {
                path,
                name,
                commit,
                purpose,
                sparse_paths,
            } = current;
            // Keep all original cones, the complete lint provider and both
            // complete APEX test providers at their original superproject pins.
            let mut expected_sparse = previous.sparse_paths.clone();
            if path == Path::new(droidloom_source::production_lint::HEALTH_PATH) {
                expected_sparse.push(droidloom_source::production_lint::LINT_PATH.into());
            }
            for &(provider, _, cone) in droidloom_source::production_apex_tests::PROVIDERS {
                if path == Path::new(provider) {
                    expected_sparse.push(cone.into());
                }
            }
            for &(provider, _, cone) in droidloom_source::production_car::PROVIDERS {
                if path == Path::new(provider) {
                    expected_sparse.push(cone.into());
                }
            }
            assert_eq!(
                (path, name, commit, purpose, sparse_paths),
                (
                    &previous.path,
                    &previous.name,
                    &previous.commit,
                    &previous.purpose,
                    &expected_sparse,
                )
            );
        }
        let cmake = &parsed.projects[651];
        assert_eq!(
            cmake.path,
            Path::new(droidloom_source::production_cmake::CMAKE_PATH)
        );
        assert_eq!(cmake.name, droidloom_source::production_cmake::CMAKE_NAME);
        assert_eq!(
            cmake.commit,
            droidloom_source::production_cmake::CMAKE_COMMIT
        );
        let service = &parsed.projects[652];
        assert_eq!(service.path, Path::new(droidloom_source::production_car::SERVICES_PATH));
        assert_eq!(service.name, droidloom_source::production_car::SERVICES_NAME);
        assert_eq!(service.commit, droidloom_source::production_car::SERVICES_COMMIT);
        assert_eq!(service.purpose, droidloom_source::production_car::SERVICES_PURPOSE);
        assert_eq!(service.sparse_paths, droidloom_source::production_car::SERVICES_CONES
            .iter().map(PathBuf::from).collect::<Vec<_>>());
        let settings = parsed
            .projects
            .iter()
            .find(|p| p.path == Path::new(PROJECT))
            .unwrap();
        assert_eq!(settings.commit, PROJECT_PIN);
        let temporary = tempfile::tempdir().unwrap();
        let selected_targets = selected.soong_targets(temporary.path(), PRODUCT).unwrap();
        assert!(selected_targets.contains(&PathBuf::from("Settings")));
        let mut command = production_soong_command(
            temporary.path(),
            temporary.path(),
            temporary.path(),
            PRODUCT,
            1,
            &selected_targets,
        )
        .unwrap();
        command.env("ALLOW_MISSING_DEPENDENCIES", "true");
        command.env("SELINUX_IGNORE_NEVERALLOWS", "true");
        selected
            .configure_dependencies(&mut command, PRODUCT)
            .unwrap();
        configure_command(selected, PRODUCT, &mut command).unwrap();
        let env: BTreeMap<_, _> = command
            .get_envs()
            .map(|(k, v)| {
                (
                    k.to_string_lossy().into_owned(),
                    v.map(|s| s.to_string_lossy().into_owned()),
                )
            })
            .collect();
        assert_eq!(
            env.get("ALLOW_MISSING_DEPENDENCIES"),
            Some(&Some("false".into()))
        );
        assert_eq!(
            env.get("SELINUX_IGNORE_NEVERALLOWS"),
            Some(&Some("false".into()))
        );
        assert_eq!(env.get("TARGET_BUILD_VARIANT"), Some(&Some("user".into())));
        assert_eq!(
            env.get("TARGET_RELEASE"),
            Some(&Some(PRODUCTION_TARGET_RELEASE.into()))
        );
        assert!(command.get_args().any(|arg| arg == "Settings"));
    }
    for targets in [
        &["Settings"][..],
        &["Settings-core", "module-info"][..],
        &["Settings", "Settings", "module-info"][..],
        &["Settings", "module-info", "module-info"][..],
    ] {
        assert!(
            validate_request(
                FixedProductionRequest::Existing(SoongDependencyMode::Strict, targets),
                PRODUCT,
            )
            .is_err()
        );
    }
    assert!(validate_request(request(), "foreign_product").is_err());
    assert!(
        validate_request(
            FixedProductionRequest::Existing(
                SoongDependencyMode::AudioApexTargetClosure,
                COMPONENT_TARGETS
            ),
            PRODUCT,
        )
        .is_err()
    );
    assert!(!required_for_targets(&["IntentResolver", "services"]));
    assert!(required_for_targets(&["Settings-core"]));

    let temporary = tempfile::tempdir().unwrap();
    let private_repo = temporary.path().canonicalize().unwrap();
    let lock_path = private_repo.join(production_source::LOCK_PATH);
    write(
        &lock_path,
        fs::read(recipe.join(production_source::LOCK_PATH)).unwrap(),
    )
    .unwrap();
    validate_source_lock(&private_repo, &lock_path).unwrap();
    assert!(validate_source_lock(&recipe, &lock_path).is_err());
    let mut changed = fs::read(&lock_path).unwrap();
    changed.push(b' ');
    fs::write(&lock_path, changed).unwrap();
    assert!(validate_source_lock(&private_repo, &lock_path).is_err());
}

#[test]
fn settings_normal_artifact_rejects_foreign_provider_paths_duplicates_and_aliases() {
    let temporary = tempfile::tempdir().unwrap();
    let out = temporary.path().canonicalize().unwrap();
    let root = out.join("target/product").join(PRODUCT);
    let info_path = root.join("module-info.json");
    let good = output_fixture(&out);
    let (info, apk) = completed_artifacts(&out, PRODUCT).unwrap();
    assert_eq!(info.sha256, hash(&info_path).unwrap());
    assert_eq!(apk.path, root.join(INSTALLED_APK));
    for mutation in 0..7 {
        let mut wrong = good.clone();
        match mutation {
            0 => {
                wrong.as_object_mut().unwrap().remove("Settings");
            }
            1 => wrong["Settings"]["path"] = json!(["packages/apps/ForeignSettings"]),
            2 => wrong["Settings"]["path"] = json!([PROJECT, PROJECT]),
            3 => {
                wrong["Settings"]["installed"] =
                    json!([root.join("system/priv-app/Settings/Settings.apk")])
            }
            4 => {
                let leaf = wrong["Settings"]["installed"][0].clone();
                wrong["Settings"]["installed"] = json!([leaf.clone(), leaf]);
            }
            5 => {
                wrong["Settings"]["installed"] = json!([format!(
                    "{}/system_ext/priv-app/Settings/./Settings.apk",
                    root.display()
                )])
            }
            _ => {
                wrong["Settings"]["installed"] = json!([format!(
                    "{}/system_ext//priv-app/Settings/Settings.apk",
                    root.display()
                )])
            }
        }
        write(&info_path, serde_json::to_vec(&wrong).unwrap()).unwrap();
        assert!(completed_artifacts(&out, PRODUCT).is_err(), "{mutation}");
    }
    write(&info_path, serde_json::to_vec(&good).unwrap()).unwrap();
    let original = root.join(INSTALLED_APK);
    let saved = out.join("saved-original.apk");
    fs::rename(&original, &saved).unwrap();
    assert!(completed_artifacts(&out, PRODUCT).is_err());
    symlink(&saved, &original).unwrap();
    assert!(completed_artifacts(&out, PRODUCT).is_err());
    fs::remove_file(&original).unwrap();
    fs::hard_link(&saved, &original).unwrap();
    assert!(completed_artifacts(&out, PRODUCT).is_err());
    fs::remove_file(&original).unwrap();
    fs::rename(&saved, &original).unwrap();
    completed_artifacts(&out, PRODUCT).unwrap();
    fs::write(&original, b"").unwrap();
    assert!(completed_artifacts(&out, PRODUCT).is_err());
}

#[test]
fn settings_normal_completion_rejects_unrestored_or_changed_source_and_input_receipt() {
    for mutation in 0..6 {
        let temporary = tempfile::tempdir().unwrap();
        let root = temporary.path().canonicalize().unwrap();
        let (source, out, journal) = fixture(&root);
        let mut projection = Projection::new(journal).unwrap();
        let projected = project(&mut projection, &repo(), &source).unwrap();
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
        if mutation != 0 {
            projection.restore().unwrap();
        }
        let mut selected_out = out.clone();
        match mutation {
            0 => (), // A successful child must not bypass projection restoration.
            1 => {
                let path = out.join(INPUTS);
                let mut bytes = fs::read(&path).unwrap();
                bytes.push(b' ');
                fs::write(path, bytes).unwrap();
            }
            2 => write(
                &source.join(PROJECT).join(PROVIDERS[0].relative),
                PROVIDERS[0].bytes,
            )
            .unwrap(),
            3 => selected_out = root.join("foreign-out"),
            4 => fs::write(
                source.join(PROJECT).join(JAVA),
                b"post-restore source drift",
            )
            .unwrap(),
            _ => fs::write(
                source.join(PROJECT).join("lint-baseline.xml"),
                PROVIDERS[3].bytes,
            )
            .unwrap(),
        }
        output_fixture(&selected_out);
        assert!(
            normal_result(&repo(), &source, &selected_out, PRODUCT, request(), input,).is_err(),
            "{mutation}"
        );
        assert!(!selected_out.join(NORMAL).exists());
    }
}
