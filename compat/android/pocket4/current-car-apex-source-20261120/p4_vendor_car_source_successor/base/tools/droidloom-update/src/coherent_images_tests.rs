use super::*;
use std::os::unix::fs::symlink;

fn file_member(body: &[u8]) -> Member {
    Member {
        kind: "file".into(),
        bytes: body.len() as u64,
        sha256: Some(hex::encode(Sha256::digest(body))),
        link: None,
        identity: [0; 9],
    }
}
fn directory() -> Member {
    Member {
        kind: "directory".into(),
        bytes: 0,
        sha256: None,
        link: None,
        identity: [0; 9],
    }
}
fn files(rows: &[(&str, &[u8])]) -> Members {
    rows.iter()
        .map(|(n, b)| (PathBuf::from(n), file_member(b)))
        .collect()
}
fn full_targets() -> Vec<String> {
    IMAGE_TARGETS
        .into_iter()
        .chain([
            "services",
            "framework-minus-apex",
            "telephony-common",
            "TelephonyProvider",
            "framework-res",
            "module-info",
            "IntentResolver",
            "Settings",
            "DroidloomSystemUI",
            "DroidloomIME",
            "DroidloomHome",
            "com.android.media.swcodec",
            "com.android.art",
            "com.android.virt",
            "com.android.tethering",
            "com.android.profiling",
            "service-profiling",
            "libfs_mgr",
            "apexd",
            "droidloom-native-bridge",
            "ExternalStorageProvider",
            "libandroidfw",
            "libhwui",
        ])
        .map(str::to_owned)
        .collect()
}

#[test]
fn complete_target_contract_requires_every_partition_and_actual_runtime_consumer() {
    let targets = full_targets();
    validate_full_targets(&targets).unwrap();
    assert!(INSTALLED.contains(&(
        "telephony-common",
        "frameworks/opt/telephony",
        "system/framework/telephony-common.jar",
    )));
    assert!(INSTALLED.contains(&(
        "TelephonyProvider",
        "packages/providers/TelephonyProvider",
        "system/priv-app/TelephonyProvider/TelephonyProvider.apk",
    )));
    for index in 0..targets.len() {
        let mut missing = targets.clone();
        missing.remove(index);
        assert!(
            validate_full_targets(&missing).is_err(),
            "{}",
            targets[index]
        );
    }
    let mut duplicate = targets.clone();
    duplicate.push(targets[0].clone());
    assert!(validate_full_targets(&duplicate).is_err());
    assert!(validate_full_targets(&["vendorimage".into(), "services".into()]).is_err());
}

#[test]
fn fixed_classpath_projection_rejects_unknown_members_and_changed_source_roles() {
    let t = tempfile::tempdir().unwrap();
    let prefix = Path::new("usr/lib/droidloom/runtime/compat/classpath-compat");
    let mut records = vec![];
    for (origin, relative) in auxiliary_layout() {
        let path = t.path().join(&relative);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(&path, b"ordinary-normal-member").unwrap();
        records.push(AuxiliaryProjection {
            origin,
            copied_relative: relative,
            staged_file: pin(&path, 1024).unwrap(),
        });
    }
    validate_auxiliary_layout(&records).unwrap();
    validate_classpath_namespace(t.path()).unwrap();
    let extra = t.path().join(prefix).join("foreign.jar");
    fs::write(&extra, b"wrong epoch").unwrap();
    assert!(validate_classpath_namespace(t.path()).is_err());
    fs::remove_file(&extra).unwrap();
    symlink("/unrelated", &extra).unwrap();
    assert!(validate_classpath_namespace(t.path()).is_err());
    fs::remove_file(extra).unwrap();
    let mut wrong = records.clone();
    wrong[5].origin = AuxiliaryOrigin::Apex {
        module: "com.android.art".into(),
        member: "javalib/foreign.jar".into(),
    };
    assert!(validate_auxiliary_layout(&wrong).is_err());
    assert!(validate_auxiliary_layout(&records[..records.len() - 1]).is_err());
    let expected = file_member(b"ordinary-normal-member");
    let changed = t.path().join(&records[5].copied_relative);
    fs::write(&changed, b"different-normal-copy").unwrap();
    assert!(!override_identical(
        &expected,
        &pin(&changed, 1024).unwrap()
    ));
}

#[test]
fn image_content_rejects_changed_framework_missing_preopt_and_extra_apex() {
    let normal = files(&[
        ("framework/framework.jar", b"new"),
        ("framework/services.jar", b"srv"),
        ("framework/oat/x86_64/services.odex", b"opt"),
        ("apex/com.android.art.apex", b"art"),
    ]);
    compare_members(&normal, &normal).unwrap();
    let mut changed = normal.clone();
    changed.insert("framework/framework.jar".into(), file_member(b"old"));
    assert!(compare_members(&normal, &changed).is_err());
    let mut missing = normal.clone();
    missing.remove(Path::new("framework/oat/x86_64/services.odex"));
    assert!(compare_members(&normal, &missing).is_err());
    let mut extra = normal.clone();
    extra.insert("apex/foreign.apex".into(), file_member(b"bad"));
    assert!(compare_members(&normal, &extra).is_err());
}

#[test]
fn complete_system_image_merge_retains_normal_root_and_rejects_uninspected_root_files() {
    let mut root = files(&[
        ("init", b"same-normal-init"),
        ("system/obsolete", b"excluded-by-real-builder"),
    ]);
    root.insert("".into(), directory());
    root.insert("system".into(), directory());
    let mut system = files(&[("framework/framework.jar", b"normal-client")]);
    system.insert("".into(), directory());
    let expected = expected_partition_members("system", &system, Some(&root)).unwrap();
    assert!(expected.contains_key(Path::new("init")));
    assert!(expected.contains_key(Path::new("system/framework/framework.jar")));
    assert!(!expected.contains_key(Path::new("system/obsolete")));
    let mut cropped = expected.clone();
    cropped.remove(Path::new("init"));
    assert!(compare_members(&expected, &cropped).is_err());
    let mut unknown = expected.clone();
    unknown.insert("extra-init".into(), file_member(b"foreign"));
    assert!(compare_members(&expected, &unknown).is_err());
    assert!(expected_partition_members("system", &system, None).is_err());
    assert!(expected_partition_members("product", &system, Some(&root)).is_err());
}

#[test]
fn original_file_binding_rejects_same_bytes_replacement_links_and_fifo_without_blocking() {
    let d = tempfile::tempdir().unwrap();
    let path = d.path().join("normal");
    fs::write(&path, b"body").unwrap();
    let original = pin(&path, 1024).unwrap();
    recheck(&original, 1024).unwrap();
    fs::rename(&path, d.path().join("old")).unwrap();
    fs::write(&path, b"body").unwrap();
    assert!(recheck(&original, 1024).is_err());
    fs::hard_link(&path, d.path().join("hard")).unwrap();
    assert!(pin(&path, 1024).is_err());
    symlink(&path, d.path().join("link")).unwrap();
    assert!(pin(&d.path().join("link"), 1024).is_err());
    let fifo = d.path().join("fifo");
    let c = std::ffi::CString::new(fifo.as_os_str().as_bytes()).unwrap();
    assert_eq!(unsafe { libc::mkfifo(c.as_ptr(), 0o600) }, 0);
    assert!(pin(&fifo, 1024).is_err());
}

#[test]
fn complete_tree_second_pass_detects_parent_rename_and_same_size_body_change() {
    let d = tempfile::tempdir().unwrap();
    let root = d.path().join("product");
    fs::create_dir(&root).unwrap();
    fs::write(root.join("file"), b"one").unwrap();
    let before = inventory(&root, true).unwrap();
    unchanged_tree(&root, &before).unwrap();
    fs::rename(&root, d.path().join("old-product")).unwrap();
    fs::create_dir(&root).unwrap();
    fs::write(root.join("file"), b"one").unwrap();
    assert!(unchanged_tree(&root, &before).is_err());
    let replacement = inventory(&root, true).unwrap();
    fs::write(root.join("file"), b"two").unwrap();
    assert!(unchanged_tree(&root, &replacement).is_err());
    let after = inventory(&root, true).unwrap();
    assert!(compare_members(&replacement, &after).is_err());
}

#[test]
fn actual_build_identity_requires_user_and_exact_generation_fields() {
    let d = tempfile::tempdir().unwrap();
    let path = d.path().join("build.prop");
    let text = "ro.system.build.id=CP3A.260905.010\nro.system.build.uuid=one\nro.system.build.version.incremental=123\nro.system.build.version.sdk=37\nro.system.build.version.sdk_full=3700000\nro.system.build.version.release=17\nro.system.build.type=user\n";
    fs::write(&path, text).unwrap();
    let (_, props) = build_properties(&path, "system").unwrap();
    let identity = property_identity(&props, "system").unwrap();
    let mut other = props.clone();
    other.insert("ro.system.build.uuid".into(), "two".into());
    assert_ne!(identity, property_identity(&other, "system").unwrap());
    other.remove("ro.system.build.version.sdk_full");
    assert!(property_identity(&other, "system").is_err());
    fs::write(&path, text.replace("type=user", "type=userdebug")).unwrap();
    assert!(build_properties(&path, "system").is_err());
    fs::write(&path, format!("{text}ro.system.build.id=CP2A.260605.016\n")).unwrap();
    assert!(build_properties(&path, "system").is_err());
}

#[test]
fn missing_reviewed_cp3a_source_identity_is_not_created_or_inferred_from_a_build_label() {
    let d = tempfile::tempdir().unwrap();
    let lock = d.path().join("lock");
    fs::write(&lock, b"source lock").unwrap();
    assert!(release_map(d.path(), &pin(&lock, 1024).unwrap()).is_err());
    assert!(
        !d.path()
            .join("android/manifest/source-runtime-coherence-x86_64.json")
            .exists()
    );
    assert_eq!(fs::read(&lock).unwrap(), b"source lock");
}

#[test]
fn release_mapping_cannot_relabel_the_actual_selected_cp2a_lock() {
    let original = include_bytes!("../../../android/manifest/source-lock-x86_64.json");
    assert_eq!(
        hex::encode(Sha256::digest(original)),
        "35a001b392b7202e9b963e8f218406dd47ed506556de0e8b5bb375c6e6137236"
    );
    let d = tempfile::tempdir().unwrap();
    let manifest = d.path().join("android/manifest");
    let evidence_root = manifest.join("runtime-coherence-evidence");
    fs::create_dir_all(&evidence_root).unwrap();
    let selected_path = manifest.join("source-lock-x86_64.json");
    fs::write(&selected_path, original).unwrap();
    let selected = pin(&selected_path, MAX_JSON).unwrap();
    let source_path = manifest.join("production-full-source-lock.json");
    fs::write(&source_path, b"private source-lock test fixture").unwrap();
    let source = pin(&source_path, MAX_JSON).unwrap();
    // These private bytes only exercise the mapping parser's other existing
    // checks. They do not supply source, ART/APEX or runtime qualification.
    let mut evidence = Vec::new();
    for name in ["source.json", "art.json"] {
        let path = evidence_root.join(name);
        fs::write(&path, b"private unqualified evidence fixture").unwrap();
        let bound = pin(&path, MAX_JSON).unwrap();
        evidence.push(RecipeEvidence {
            relative: path.strip_prefix(d.path()).unwrap().to_owned(),
            bytes: bound.bytes,
            sha256: bound.sha256,
        });
    }
    let mapping = ReleaseMap {
        schema: "droidloom-source-runtime-coherence-v1".into(),
        source_lock_sha256: source.sha256.clone(),
        selected_gsi_lock_sha256: selected.sha256.clone(),
        selected_build_id: "CP3A.260905.010".into(),
        source_build_id: "CP3A.260905.010".into(),
        target_product: PRODUCT.into(),
        target_release: "private-test-release".into(),
        source_identity_evidence: evidence[0].clone(),
        art_apex_abi_evidence: evidence[1].clone(),
    };
    fs::write(
        manifest.join("source-runtime-coherence-x86_64.json"),
        serde_json::to_vec(&mapping).unwrap(),
    )
    .unwrap();
    let error = release_map(d.path(), &source).unwrap_err().to_string();
    assert!(error.contains("selected GSI lock body differs"), "{error}");
    assert_eq!(fs::read(&selected_path).unwrap(), original);
    recheck(&selected, MAX_JSON).unwrap();
}

#[test]
fn selected_lock_identity_requires_exact_typed_and_unique_identity_fields() {
    let original = include_bytes!("../../../android/manifest/source-lock-x86_64.json");
    // Matching the actual CP2A identity here proves only this local predicate.
    // The production release_map still separately requires the selected CP3A
    // generation and its reviewed source/ART/APEX mapping.
    require_selected_lock_identity(original, "CP2A.260605.016").unwrap();
    assert!(require_selected_lock_identity(original, "CP3A.260905.010").is_err());
    let parsed: Value = serde_json::from_slice(original).unwrap();
    for (pointer, replacement) in [
        ("/schema_version", json!(2)),
        ("/schema_version", json!("1")),
        ("/architecture", json!("arm64")),
        ("/architecture", Value::Null),
        ("/aosp_ci_base/cpu_abi", json!("arm64-v8a")),
        ("/aosp_ci_base/cpu_abi", json!(["x86_64"])),
        ("/aosp_ci_base/build_id", json!("CP3A.260905.010")),
        ("/aosp_ci_base/build_id", Value::Null),
    ] {
        let mut changed = parsed.clone();
        *changed.pointer_mut(pointer).unwrap() = replacement;
        assert!(
            require_selected_lock_identity(
                &serde_json::to_vec(&changed).unwrap(),
                "CP2A.260605.016",
            )
            .is_err(),
            "{pointer}"
        );
    }
    for (parent, field) in [
        ("", "schema_version"),
        ("", "architecture"),
        ("/aosp_ci_base", "cpu_abi"),
        ("/aosp_ci_base", "build_id"),
    ] {
        let mut changed = parsed.clone();
        changed
            .pointer_mut(parent)
            .unwrap()
            .as_object_mut()
            .unwrap()
            .remove(field);
        assert!(
            require_selected_lock_identity(
                &serde_json::to_vec(&changed).unwrap(),
                "CP2A.260605.016",
            )
            .is_err(),
            "{parent}/{field}"
        );
    }
    let original_text = std::str::from_utf8(original).unwrap();
    for (needle, duplicate) in [
        (
            "\"schema_version\": 1",
            "\"schema_version\": 1, \"schema_version\": 1",
        ),
        (
            "\"architecture\": \"x86_64\"",
            "\"architecture\": \"arm64\", \"architecture\": \"x86_64\"",
        ),
        (
            "\"cpu_abi\": \"x86_64\"",
            "\"cpu_abi\": \"arm64-v8a\", \"cpu_abi\": \"x86_64\"",
        ),
        (
            "\"build_id\": \"CP2A.260605.016\"",
            "\"build_id\": \"CP3A.260905.010\", \"build_id\": \"CP2A.260605.016\"",
        ),
    ] {
        assert_eq!(original_text.matches(needle).count(), 1);
        let changed = original_text.replacen(needle, duplicate, 1);
        assert!(require_selected_lock_identity(changed.as_bytes(), "CP2A.260605.016").is_err());
    }
}

fn elf() -> Vec<u8> {
    let mut b = vec![0; 768];
    b[..7].copy_from_slice(b"\x7fELF\x02\x01\x01");
    b[16..18].copy_from_slice(&3u16.to_le_bytes());
    b[18..20].copy_from_slice(&62u16.to_le_bytes());
    b[20..24].copy_from_slice(&1u32.to_le_bytes());
    b[52..54].copy_from_slice(&64u16.to_le_bytes());
    b[32..40].copy_from_slice(&64u64.to_le_bytes());
    b[54..56].copy_from_slice(&56u16.to_le_bytes());
    b[56..58].copy_from_slice(&2u16.to_le_bytes());
    b[64..68].copy_from_slice(&1u32.to_le_bytes());
    b[80..88].copy_from_slice(&0x400000u64.to_le_bytes());
    b[96..104].copy_from_slice(&768u64.to_le_bytes());
    b[120..124].copy_from_slice(&2u32.to_le_bytes());
    b[128..136].copy_from_slice(&512u64.to_le_bytes());
    b[152..160].copy_from_slice(&64u64.to_le_bytes());
    let strings = b"\0libFraunhoferAAC.so\0";
    b[640..640 + strings.len()].copy_from_slice(strings);
    for (n, (tag, value)) in [
        (1u64, 1u64),
        (5, 0x400280),
        (10, strings.len() as u64),
        (0, 0),
    ]
    .into_iter()
    .enumerate()
    {
        let offset = 512 + n * 16;
        b[offset..offset + 8].copy_from_slice(&tag.to_le_bytes());
        b[offset + 8..offset + 16].copy_from_slice(&value.to_le_bytes());
    }
    b
}

#[test]
fn aac_consumer_requires_real_bounded_x86_64_dynamic_dependency() {
    let d = tempfile::tempdir().unwrap();
    let p = d.path().join("decoder.so");
    let original = elf();
    fs::write(&p, &original).unwrap();
    assert_eq!(
        elf_needed(&p).unwrap(),
        BTreeSet::from(["libFraunhoferAAC.so".into()])
    );
    let mut wrong = original.clone();
    wrong[18..20].copy_from_slice(&183u16.to_le_bytes());
    fs::write(&p, wrong).unwrap();
    assert!(elf_needed(&p).is_err());
    let mut escaped = original.clone();
    escaped[536..544].copy_from_slice(&u64::MAX.to_le_bytes());
    fs::write(&p, escaped).unwrap();
    assert!(elf_needed(&p).is_err());
    fs::write(&p, &original[..80]).unwrap();
    assert!(elf_needed(&p).is_err());
}

fn directory_zip(names: &[(&str, u32)]) -> Vec<u8> {
    let mut b = Vec::new();
    for (name, size) in names {
        let mut h = vec![0; 46];
        h[..4].copy_from_slice(b"PK\x01\x02");
        h[24..28].copy_from_slice(&size.to_le_bytes());
        h[28..30].copy_from_slice(&(name.len() as u16).to_le_bytes());
        b.extend(h);
        b.extend(name.as_bytes());
    }
    let len = b.len() as u32;
    let mut end = vec![0; 22];
    end[..4].copy_from_slice(b"PK\x05\x06");
    end[8..10].copy_from_slice(&(names.len() as u16).to_le_bytes());
    end[10..12].copy_from_slice(&(names.len() as u16).to_le_bytes());
    end[12..16].copy_from_slice(&len.to_le_bytes());
    b.extend(end);
    b
}

#[test]
fn apex_directory_bounds_reject_duplicate_missing_zip64_and_truncated_selected_members() {
    let d = tempfile::tempdir().unwrap();
    let p = d.path().join("input.apex");
    fs::write(&p, directory_zip(&[("apex_payload.img", 4096)])).unwrap();
    assert_eq!(zip_member_size(&p, "apex_payload.img").unwrap(), 4096);
    for entries in [
        vec![("other", 4096)],
        vec![("apex_payload.img", u32::MAX)],
        vec![("apex_payload.img", 1), ("apex_payload.img", 1)],
    ] {
        fs::write(&p, directory_zip(&entries)).unwrap();
        assert!(zip_member_size(&p, "apex_payload.img").is_err());
    }
    let mut truncated = directory_zip(&[("apex_payload.img", 1)]);
    truncated.pop();
    fs::write(&p, truncated).unwrap();
    assert!(zip_member_size(&p, "apex_payload.img").is_err());
}

#[test]
fn normal_copy_is_create_only_and_keeps_original_and_copy_identities_separate() {
    let d = tempfile::tempdir().unwrap();
    let original = d.path().join("normal.img");
    fs::write(&original, b"whole image").unwrap();
    let source = pin(&original, 1024).unwrap();
    let dest = d.path().join("staged/image.img");
    let copy = copy_bound(&source, &dest).unwrap();
    assert_eq!(source.sha256, copy.sha256);
    assert_eq!(source.bytes, copy.bytes);
    assert_ne!(source.identity, copy.identity);
    assert!(copy_bound(&source, &dest).is_err());
    assert_eq!(fs::read(&original).unwrap(), b"whole image");
}

#[test]
fn complete_product_cannot_enter_legacy_image_rewrite_even_with_dangling_receipt() {
    let d = tempfile::tempdir().unwrap();
    let product = d.path().join("target/product/droidloom_x86_64");
    fs::create_dir_all(&product).unwrap();
    reject_legacy_mutation(&product).unwrap();
    symlink("absent", d.path().join(INPUTS)).unwrap();
    assert!(reject_legacy_mutation(&product).is_err());
    fs::remove_file(d.path().join(INPUTS)).unwrap();
    fs::write(d.path().join(NORMAL), b"old incomplete receipt").unwrap();
    assert!(reject_legacy_mutation(&product).is_err());
}

#[test]
fn runtime_override_cannot_substitute_same_size_new_jar_for_the_normal_image() {
    let d = tempfile::tempdir().unwrap();
    let p = d.path().join("framework.jar");
    fs::write(&p, b"new").unwrap();
    let actual = pin(&p, 1024).unwrap();
    assert!(!override_identical(&file_member(b"old"), &actual));
    assert!(override_identical(&file_member(b"new"), &actual));
    assert!(!override_identical(&directory(), &actual));
    let good = json!({"android_file_overrides":[{"source":"/usr/lib/droidloom/current/framework/services.jar",
        "target":"/system/framework/services.jar"}]});
    let actual = projection_paths(&good).unwrap();
    assert_eq!(
        actual.get("/system/framework/services.jar"),
        Some(&PathBuf::from(
            "usr/lib/droidloom/runtime/framework/services.jar"
        ))
    );
    for source in [
        "/usr/lib/droidloom/current/../foreign",
        "/usr/lib/droidloom/current/framework//services.jar",
        "/foreign/source",
    ] {
        let mut wrong = good.clone();
        wrong["android_file_overrides"][0]["source"] = json!(source);
        assert!(projection_paths(&wrong).is_err());
    }
    let mut duplicate = good.clone();
    let row = duplicate["android_file_overrides"][0].clone();
    duplicate["android_file_overrides"]
        .as_array_mut()
        .unwrap()
        .push(row);
    assert!(projection_paths(&duplicate).is_err());
}

#[test]
fn product_path_aliases_and_symbolic_parent_are_rejected() {
    let d = tempfile::tempdir().unwrap();
    let p = d.path().join("file");
    fs::write(&p, b"body").unwrap();
    symlink(d.path(), d.path().join("alias")).unwrap();
    assert!(pin(&d.path().join("alias/file"), 1024).is_err());
    assert!(
        ordinary_absolute(Path::new(&format!("{}/./file", d.path().display())), false).is_err()
    );
    assert!(ordinary_absolute(Path::new(&format!("{}//file", d.path().display())), false).is_err());
}


#[test]
fn complete_product_cmake_header_rejects_old_schema_and_source_pair() {
    let targets = full_targets();
    let actual_lock = include_bytes!("../../../android/manifest/production-full-apex-tests-source-lock.json");
    let actual_sha = hex::encode(Sha256::digest(actual_lock));
    let current = json!({
        "schema": "droidloom-production-full652-inputs-v1",
        "source_lock": {"sha256": actual_sha},
        "strict_allow_missing_dependencies": "false",
        "selinux_ignore_neverallows": "false",
        "requested_targets": targets,
    });
    validate_full_source_header(&current, &targets).unwrap();
    for (schema, source_sha) in [
        ("droidloom-production-full652-inputs-v1", "aa14d968c14c2febcfacbb90e82598e2ba8e57f4bbb2cfc8f1f2a741555153ca"),
        ("droidloom-production-full652-inputs-v1", "2e9877a58ebbc3625c7411d3573951afa409d9b13692468b825b4c25961ffffb"),
        ("droidloom-production-full651-inputs-v1", actual_sha.as_str()),
        ("droidloom-production-full652-inputs-v1", "30dcc1b5b090530b3fc06aeb3e489a961b0fc7c6368ed9d19eb0a1b2054e3eb4"),
        ("droidloom-production-full651-inputs-v1", "30dcc1b5b090530b3fc06aeb3e489a961b0fc7c6368ed9d19eb0a1b2054e3eb4"),
    ] {
        let mut old = current.clone();
        old["schema"] = schema.into();
        old["source_lock"]["sha256"] = source_sha.into();
        assert!(validate_full_source_header(&old, &targets).is_err());
    }
    for field in ["strict_allow_missing_dependencies", "selinux_ignore_neverallows"] {
        let mut relaxed = current.clone();
        relaxed[field] = "true".into();
        assert!(validate_full_source_header(&relaxed, &targets).is_err());
    }
    let mut missing = current;
    missing["requested_targets"].as_array_mut().unwrap().pop();
    assert!(validate_full_source_header(&missing, &targets).is_err());
}
