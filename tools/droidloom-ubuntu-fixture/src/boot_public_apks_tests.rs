use super::*;
use std::os::unix::fs::PermissionsExt;

const CANONICAL_REGISTRY: &[u8] = include_bytes!("../tests/fixtures/app-release-gates.json");
const TEST_APKS: usize = 65;

fn selected_apps() -> Vec<Value> {
    SELECTED_PACKAGES
        .iter()
        .map(|package| json!({"package":package}))
        .collect()
}

fn fake_pin() -> FilePin {
    FilePin {
        path: "/reviewed/receipt.json".into(),
        bytes: 42,
        sha256: "a".repeat(64),
    }
}
fn synthetic() -> (ImportPlan, Value, Value, Value) {
    synthetic_with_splits(26)
}

fn synthetic_with_splits(two_part_apps: usize) -> (ImportPlan, Value, Value, Value) {
    assert!(two_part_apps <= PACKAGES);
    let apk_count = PACKAGES + two_part_apps;
    let receipt_pin = fake_pin();
    let exemptions = json!([
        {"package":"com.enflick.android.TextNow","status":"exempt_unverified"},
        {"package":"com.pinger.textfree","status":"exempt_unverified"},
        {"package":"com.ubercab","status":"exempt_unverified"}
    ]);
    let mut execution_rows = Vec::new();
    let mut source_rows = Vec::new();
    let mut signed_rows = Vec::new();
    let mut total = 0;
    for app in 0..PACKAGES {
        let package = SELECTED_PACKAGES[app];
        let signers = vec!["b".repeat(64)];
        let mut parts = Vec::new();
        let mut materials = Vec::new();
        for part in 0..if app < two_part_apps { 2 } else { 1 } {
            let split = if part == 0 {
                None
            } else {
                Some("config.arm64_v8a")
            };
            let bytes = format!("PK\u{3}\u{4}public-{app}-{part}").into_bytes();
            let sha256 = fs::digest(&bytes);
            total += bytes.len();
            let metadata = json!({"name":package,"versionCode":"42","split":split});
            let path = format!("/home/alex/work/current/{package}/{part}.apk");
            materials.push(json!({
                "path":path,"bytes":bytes.len(),"sha256":sha256,
                "manifest_split_name":split,"metadata":metadata,
                "sdk37_signature_valid":true,"verified_signer_certificates_sha256":signers
            }));
            parts.push(json!({"name":format!("{sha256}.apk"),"bytes":bytes.len(),
                "sha256":sha256,"split":split}));
        }
        execution_rows.push(json!({
            "package":package,"version_code":42,"version_name":"current","role":"third_party",
            "signers_sha256":signers,"files":parts,
            "original_account_install_blocked":app == 7,"original_signer_precondition":app != 7
        }));
        source_rows.push(json!({
            "package":package,"version_code":42,"version_name":"current","role":"third_party",
            "signer_certificates_sha256":signers,"material_files":materials,
            "signature_verification_source":receipt_pin
        }));
        signed_rows.push(json!({
            "package":package,"version_code":42,"version_name":"current","role":"third_party",
            "signer_certificates_sha256":signers,"files":materials,
            "all_file_signatures_and_hashes_verified":true
        }));
    }
    let execution = json!({
        "schema":"p4-selected39-execution-v3","scope":"fresh_isolated_vm_only",
        "guest_stage":STAGE,"package_count":PACKAGES,"file_count":apk_count,
        "source_materials":receipt_pin,"excluded_packages":exemptions,"rows":execution_rows
    });
    let selection = json!({
        "schema":"p4-selected39-static-launch-inputs-v1","package_count":PACKAGES,
        "apk_file_count":apk_count,"apk_total_bytes":total,
        "all_current_apk_hashes_match_verified_signature_receipt":true,
        "excluded_packages":exemptions,"applications":source_rows
    });
    let receipt = json!({
        "schema":"p4-selected39-materials-and-original-signers-handoff-v1",
        "all_selected_materials_verified":true,"package_count":PACKAGES,"file_count":apk_count,
        "excluded_packages":exemptions,"rows":signed_rows
    });
    (
        ImportPlan {
            schema: "droidloom.public-apk-import.v1".into(),
            execution: fake_pin(),
            selection: fake_pin(),
            source_receipt: receipt_pin,
            gate_registry: None,
        },
        execution,
        selection,
        receipt,
    )
}

#[test]
fn complete_public_split_plan_keeps_all_39_and_blocks_original_account_shortcuts() {
    let (plan, execution, selection, receipt) = synthetic();
    let (files, apps) = validate(&plan, &execution, &selection, &receipt).unwrap();
    assert_eq!(files.len(), TEST_APKS);
    assert_eq!(apps.len(), PACKAGES);
    assert_eq!(apps[7]["original_account_install_blocked"], true);
    assert_eq!(apps[0]["install_argv"][2], "install-multiple");
    assert_eq!(apps[38]["install_argv"][2], "install");
    assert!(apps.iter().all(|a| a["commands_executed"] == false
        && a["application_business_accepted"] == false
        && a["runtime_epoch_binding_required"] == true));
    let base = files
        .iter()
        .find(|f| f.package.as_deref() == Some(SELECTED_PACKAGES[0]) && f.split.is_none())
        .unwrap();
    assert_eq!(apps[0]["install_argv"][5], base.guest_path);
    assert!(
        admit(&fake_pin(), false)
            .unwrap_err()
            .to_string()
            .contains("fresh normal")
    );
}

#[test]
fn pinned_public_selection_rejects_incomplete_mixed_or_rewritten_material() {
    for case in 0..16 {
        let (plan, mut e, mut s, mut r) = synthetic();
        match case {
            0 => {
                e["rows"].as_array_mut().unwrap().pop();
            }
            1 => {
                e["rows"][0]["files"].as_array_mut().unwrap().pop();
            }
            2 => {
                let first = e["rows"][0].clone();
                e["rows"][1] = first;
            }
            3 => e["guest_stage"] = "/home/alex".into(),
            4 => e["rows"][0]["files"][0]["name"] = "../escape.apk".into(),
            5 => e["rows"][0]["version_code"] = 41.into(),
            6 => e["rows"][0]["files"][0]["split"] = "unexpected".into(),
            7 => s["applications"][0]["material_files"][0]["sdk37_signature_valid"] = false.into(),
            8 => {
                s["applications"][0]["material_files"][0]["path"] =
                    "/data/user/0/private.apk".into()
            }
            9 => {
                s["applications"][0]["material_files"][0]["path"] =
                    "/home/alex/work/../private.apk".into()
            }
            10 => s["applications"][0]["signer_certificates_sha256"] = json!(["c".repeat(64)]),
            11 => r["rows"][0]["files"][0]["sha256"] = "c".repeat(64).into(),
            12 => r["rows"][0]["all_file_signatures_and_hashes_verified"] = false.into(),
            13 => r["rows"][0]["files"].as_array_mut().unwrap().reverse(),
            14 => e["scope"] = "existing_account".into(),
            _ => e["excluded_packages"][0]["package"] = "org.mozilla.firefox".into(),
        }
        if case == 13 {
            // Split identity, not incidental source ordering, is authoritative.
            assert!(validate(&plan, &e, &s, &r).is_ok());
        } else {
            assert!(validate(&plan, &e, &s, &r).is_err(), "case {case}");
        }
    }
}

#[test]
fn public_source_preflight_preserves_hardlinks_but_rejects_aliases_non_zip_and_foreign_writes()
-> Result<()> {
    let directory = tempfile::tempdir()?;
    let file = directory.path().join("original.apk");
    std::fs::write(&file, b"PK\x03\x04original")?;
    let pin = boot_files::pin_file(&file)?;
    check_source(&pin, true)?;
    std::fs::set_permissions(&file, std::fs::Permissions::from_mode(0o666))?;
    assert!(check_source(&pin, true).is_err());
    std::fs::set_permissions(&file, std::fs::Permissions::from_mode(0o600))?;
    let linked = directory.path().join("linked.apk");
    std::fs::hard_link(&file, &linked)?;
    let linked_identity = check_source(&pin, true)?;
    assert_eq!(linked_identity.nlink, 2);
    let independent = directory.path().join("independent.apk");
    let copied_identity = boot_files::copy_pin_with_identity(&pin, &independent, 0o400)?;
    assert_eq!(copied_identity, linked_identity);
    assert_eq!(
        boot_files::open_pin(&boot_files::pin_file(&independent)?)?
            .1
            .nlink,
        1
    );
    assert_eq!(check_source(&pin, true)?, linked_identity);
    std::fs::remove_file(linked)?;
    let alias = directory.path().join("alias.apk");
    std::os::unix::fs::symlink(&file, &alias)?;
    let mut alias_pin = pin.clone();
    alias_pin.path = alias;
    assert!(check_source(&alias_pin, true).is_err());
    std::fs::write(&file, b"not-an-apk")?;
    assert!(check_source(&boot_files::pin_file(&file)?, true).is_err());
    Ok(())
}

fn staged() -> Staged {
    staged_with_split_count(26)
}

fn staged_with_split_count(two_part_apps: usize) -> Staged {
    let (plan, e, s, r) = synthetic_with_splits(two_part_apps);
    let (mut files, applications) = validate(&plan, &e, &s, &r).unwrap();
    let apk_file_count = files.len();
    for name in [
        "selected39-execution.json",
        "selected39-source-selection.json",
        "selected39-signature-receipt.json",
    ] {
        files.push(Material {
            source: fake_pin(),
            source_identity_before: None,
            source_identity_after: None,
            destination_identity: None,
            guest_path: format!("{STAGE}/{name}"),
            package: None,
            split: None,
        });
    }
    Staged {
        schema: "droidloom.public-apks-staged.v1",
        import: fake_pin(),
        files,
        applications,
        package_count: PACKAGES,
        apk_file_count,
        runtime_preparation_inputs: None,
        original_userdata_imported: false,
        applications_installed: 0,
        application_business_accepted: false,
        guest_qualified: false,
        production_ready: false,
    }
}

#[test]
fn public_material_labels_require_exact_uid_boundary_and_input_roles() {
    let staged = staged_with_registry();
    let rows: Vec<_> = std::iter::once(ROOT.to_owned()).chain(guest_paths(&staged)).map(|path| {
        let kind=if path == ROOT { "root" } else if path == STAGE { "dir" } else { "input" };
        json!({"path":path,"label_hex":hex::encode(format!("u:object_r:droidloom_public_apk_{kind}:s0\0"))})
    }).collect();
    let valid = json!({"labels":rows});
    validate_labels(&staged, &valid).unwrap();
    let mut missing = valid.clone();
    missing["labels"].as_array_mut().unwrap().pop();
    assert!(validate_labels(&staged, &missing).is_err());
    let mut wrong = valid.clone();
    wrong["labels"][2]["label_hex"] =
        hex::encode("u:object_r:p4_linux_product_store_t:s0\0").into();
    assert!(validate_labels(&staged, &wrong).is_err());
    let mut duplicate = valid.clone();
    let row = duplicate["labels"][2].clone();
    duplicate["labels"].as_array_mut().unwrap().push(row);
    assert!(validate_labels(&staged, &duplicate).is_err());
}

fn staged_with_registry() -> Staged {
    add_registry(staged())
}

fn add_registry(mut material: Staged) -> Staged {
    let registry = FilePin {
        path: "/reviewed/app-release-gates.json".into(),
        bytes: REGISTRY_BYTES,
        sha256: REGISTRY_SHA256.into(),
    };
    material.files.push(Material {
        source: registry.clone(),
        source_identity_before: None,
        source_identity_after: None,
        destination_identity: None,
        guest_path: format!("{STAGE}/{REGISTRY_NAME}"),
        package: None,
        split: None,
    });
    material.runtime_preparation_inputs = Some(PreparationInputs {
        selection: guest_pin(&fake_pin(), "selected39-source-selection.json"),
        source_receipt: guest_pin(&fake_pin(), "selected39-signature-receipt.json"),
        gate_registry: guest_pin(&registry, REGISTRY_NAME),
        required_gates: registry_coverage(
            &serde_json::from_slice(CANONICAL_REGISTRY).unwrap(),
            &material.applications,
        )
        .unwrap(),
    });
    material
}

#[test]
fn canonical_registry_covers_every_original_selected_gate_without_runtime_placeholders()
-> Result<()> {
    assert_eq!(CANONICAL_REGISTRY.len() as u64, REGISTRY_BYTES);
    assert_eq!(fs::digest(CANONICAL_REGISTRY), REGISTRY_SHA256);
    let temp = tempfile::tempdir()?;
    let registry_path = temp.path().join(REGISTRY_NAME);
    std::fs::write(&registry_path, CANONICAL_REGISTRY)?;
    let (mut plan, _, _, _) = synthetic();
    assert!(preparation_inputs(&plan, &selected_apps())?.is_none());
    plan.gate_registry = Some(boot_files::pin_file(&registry_path)?);
    let prepared = preparation_inputs(&plan, &selected_apps())?.unwrap();
    assert_eq!(prepared.required_gates.len(), PACKAGES);
    assert_eq!(prepared.required_gates["org.mozilla.firefox"].len(), 11);
    assert_eq!(prepared.required_gates["com.android.camera2"].len(), 11);
    assert_eq!(prepared.required_gates["com.android.settings"].len(), 9);
    assert!(prepared.required_gates["com.android.dialer"].contains(&"dialer.call".into()));
    assert!(prepared.required_gates["com.tencent.mm"].contains(&"messaging.delivery".into()));
    assert_eq!(
        prepared.gate_registry.path,
        Path::new(STAGE).join(REGISTRY_NAME)
    );
    assert_eq!(prepared.gate_registry.sha256, REGISTRY_SHA256);
    assert_eq!(
        prepared.selection.path,
        Path::new(STAGE).join("selected39-source-selection.json")
    );
    let serialized = serde_json::to_value(&prepared)?;
    for field in [
        "main_qualification",
        "expected_epoch",
        "intent",
        "production_ready",
    ] {
        assert!(serialized.get(field).is_none(), "{field} was synthesized");
    }
    assert_eq!(std::fs::read(&registry_path)?, CANONICAL_REGISTRY);
    Ok(())
}

#[test]
fn optional_registry_rejects_replacement_bytes_missing_coverage_and_weaker_contracts() -> Result<()>
{
    let temp = tempfile::tempdir()?;
    let path = temp.path().join(REGISTRY_NAME);
    let (mut plan, _, _, _) = synthetic();
    let mut weaker: Value = serde_json::from_slice(CANONICAL_REGISTRY)?;
    weaker["profiles"]["messaging"]["checks"]
        .as_object_mut()
        .unwrap()
        .remove("messaging.delivery");
    std::fs::write(&path, serde_json::to_vec(&weaker)?)?;
    plan.gate_registry = Some(boot_files::pin_file(&path)?);
    assert!(
        preparation_inputs(&plan, &selected_apps())
            .unwrap_err()
            .to_string()
            .contains("canonical contract")
    );
    for case in 0..6 {
        let mut registry: Value = serde_json::from_slice(CANONICAL_REGISTRY)?;
        let mut apps = selected_apps();
        match case {
            0 => {
                registry["common_gates"]
                    .as_object_mut()
                    .unwrap()
                    .remove("stability");
            }
            1 => {
                registry["profiles"]["camera"]["checks"] = json!({});
            }
            2 => {
                registry["packages"]
                    .as_object_mut()
                    .unwrap()
                    .remove("org.mozilla.firefox");
            }
            3 => registry["packages"]["org.mozilla.firefox"]["profile"] = "missing".into(),
            4 => {
                apps[0]["package"] = "org.example.unreviewed".into();
            }
            _ => {
                apps[1] = apps[0].clone();
            }
        }
        let typed: GateRegistry = serde_json::from_value(registry)?;
        assert!(registry_coverage(&typed, &apps).is_err(), "case {case}");
    }
    let mut unknown: Value = serde_json::from_slice(CANONICAL_REGISTRY)?;
    unknown["profiles"]["camera"]["passed"] = true.into();
    assert!(serde_json::from_value::<GateRegistry>(unknown).is_err());
    let legacy: ImportPlan = serde_json::from_value(json!({
        "schema":"droidloom.public-apk-import.v1","execution":fake_pin(),
        "selection":fake_pin(),"source_receipt":fake_pin()
    }))?;
    assert!(legacy.gate_registry.is_none());
    Ok(())
}

#[test]
fn public_material_roster_accepts_only_complete_declared_apks_and_provenance() {
    assert_eq!(provenance_count(&staged().files).unwrap(), 3);
    assert_eq!(provenance_count(&staged_with_registry().files).unwrap(), 4);
    for case in 0..5 {
        let mut material = staged_with_registry();
        match case {
            0 => {
                material.files.remove(TEST_APKS);
            }
            1 => {
                let extra = material.files.last().unwrap().clone();
                material.files.push(extra);
            }
            2 => {
                material.files.last_mut().unwrap().guest_path = format!("{STAGE}/weaker-gates.json")
            }
            3 => {
                material.files.last_mut().unwrap().guest_path =
                    "/home/alex/app-release-gates.json".into()
            }
            _ => {
                material.files.last_mut().unwrap().guest_path =
                    format!("{STAGE}/nested/{REGISTRY_NAME}")
            }
        }
        assert!(provenance_count(&material.files).is_err(), "case {case}");
    }
}

#[test]
fn actual_ext4_public_material_readback_detects_tampered_bytes_and_is_create_only() -> Result<()> {
    // Preserve the historical three-document case, the current 65+4-file
    // import, and a complete future split-count change. All use real ext4
    // dump/readback, including the source registry bytes.
    for (with_registry, split_apps) in [(false, 26), (true, 26), (true, 27)] {
        let temp = tempfile::tempdir()?;
        let root = temp.path().join("root");
        let stage = root.join(STAGE.trim_start_matches('/'));
        std::fs::create_dir_all(&stage)?;
        let mut material = if with_registry {
            add_registry(staged_with_split_count(split_apps))
        } else {
            staged_with_split_count(split_apps)
        };
        for (index, item) in material.files.iter_mut().enumerate() {
            let path = root.join(item.guest_path.trim_start_matches('/'));
            if item.guest_path.ends_with(REGISTRY_NAME) {
                std::fs::write(&path, CANONICAL_REGISTRY)?;
            } else {
                let bytes = if let Some(package) = item.package.as_deref() {
                    let app = SELECTED_PACKAGES
                        .iter()
                        .position(|v| *v == package)
                        .unwrap();
                    let part = usize::from(item.split.is_some());
                    format!("PK\u{3}\u{4}public-{app}-{part}")
                } else {
                    format!("PK\u{3}\u{4}exact original {index}")
                };
                std::fs::write(&path, bytes)?;
            }
            item.source = boot_files::pin_file(&path)?;
        }
        let disk = temp.path().join("test.ext4");
        let image = boot_files::new_file(&disk, 0o600)?;
        image.set_len(32 * 1024 * 1024)?;
        boot_files::run_logged(
            temp.path(),
            "make-test-ext4",
            "/usr/sbin/mke2fs",
            &[
                "-q".into(),
                "-F".into(),
                "-t".into(),
                "ext4".into(),
                "-d".into(),
                root.to_string_lossy().into(),
                disk.to_string_lossy().into(),
            ],
            30,
        )?;
        let good = temp.path().join("good");
        boot_files::private_dir(&good)?;
        let receipt = readback_bodies(&good, &disk, &material.files)?;
        let provenance = if with_registry { 4 } else { 3 };
        if with_registry && split_apps == 26 {
            assert_eq!(material.files.len(), 69);
        }
        assert_eq!(
            receipt["files"].as_array().unwrap().len(),
            material.apk_file_count + provenance
        );
        assert_eq!(receipt["apk_file_count"], material.apk_file_count);
        assert_eq!(receipt["provenance_file_count"], provenance);
        assert_eq!(receipt["gate_registry_imported"], with_registry);
        assert_eq!(receipt["all_original_bytes_matched"], true);
        assert_eq!(receipt["production_ready"], false);
        if with_registry {
            let row = receipt["files"].as_array().unwrap().last().unwrap();
            assert_eq!(row["actual"]["sha256"], REGISTRY_SHA256);
            assert_eq!(row["actual"]["bytes"], REGISTRY_BYTES);
        }
        assert!(readback_bodies(&good, &disk, &material.files).is_err());
        let bad = temp.path().join("bad");
        boot_files::private_dir(&bad)?;
        let index = if with_registry {
            material.files.len() - 1
        } else {
            0
        };
        material.files[index].source.sha256 = "0".repeat(64);
        assert!(readback_bodies(&bad, &disk, &material.files).is_err());
    }
    Ok(())
}

#[test]
fn exact_pinned_sets_allow_changed_split_counts_without_replacing_selected_packages() {
    for split_apps in [0, 25, 27, 39] {
        let (plan, e, s, r) = synthetic_with_splits(split_apps);
        let (files, apps) = validate(&plan, &e, &s, &r).unwrap();
        assert_eq!(files.len(), PACKAGES + split_apps);
        assert_eq!(apps.len(), PACKAGES);
        for (field, value) in [
            ("file_count", PACKAGES + split_apps + 1),
            ("file_count", MAX_APKS + 1),
        ] {
            let mut bad = e.clone();
            bad[field] = value.into();
            assert!(validate(&plan, &bad, &s, &r).is_err());
        }
        let mut bad = r.clone();
        bad["file_count"] = (PACKAGES + split_apps + 1).into();
        assert!(validate(&plan, &e, &s, &bad).is_err());
        let mut bad = s.clone();
        bad["apk_file_count"] = (PACKAGES + split_apps + 1).into();
        assert!(validate(&plan, &e, &bad, &r).is_err());
    }
    let (plan, mut e, mut s, mut r) = synthetic();
    for (document, key) in [(&mut e, "rows"), (&mut s, "applications"), (&mut r, "rows")] {
        document[key][0]["package"] = "org.example.replacement".into();
    }
    assert!(validate(&plan, &e, &s, &r).is_err());
    let (plan, e, mut s, mut r) = synthetic();
    // The independent SDK metadata must agree with the selected manifest split,
    // even if both metadata copies carry the same erroneous value.
    r["rows"][0]["files"][0]["metadata"]["split"] = "different".into();
    s["applications"][0]["material_files"][0]["metadata"]["split"] = "different".into();
    assert!(validate(&plan, &e, &s, &r).is_err());
}

#[test]
fn offline_public_input_check_hashes_actual_bytes_and_rejects_named_inode_replacement() -> Result<()>
{
    let directory = tempfile::tempdir()?;
    let path = directory.path().join("original.apk");
    std::fs::write(&path, b"PK\x03\x04actual public bytes")?;
    let pin = boot_files::pin_file(&path)?;
    let (held, before) = hold_verified_source(&pin, true)?;
    recheck_held_source(&pin, true, &held, &before)?;
    let mut wrong = pin.clone();
    wrong.sha256 = "0".repeat(64);
    assert!(hold_verified_source(&wrong, true).is_err());
    let original = directory.path().join("preserved-original.apk");
    std::fs::rename(&path, &original)?;
    std::fs::write(&path, b"PK\x03\x04actual public bytes")?;
    assert_eq!(boot_files::pin_file(&path)?.sha256, pin.sha256);
    assert!(recheck_held_source(&pin, true, &held, &before).is_err());
    assert_eq!(boot_files::pin_file(&original)?.sha256, pin.sha256);
    Ok(())
}
