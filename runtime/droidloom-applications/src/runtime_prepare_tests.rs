use super::*;
use droidloom_supervisor::control::application_probe::InstalledApk;
use serde_json::json;

struct ReadOnlyFake {
    catalog: Result<Vec<AndroidApplication>, String>,
    identities: BTreeMap<String, ApplicationInspection>,
    inspected: Vec<String>,
}

impl PreparationClient for ReadOnlyFake {
    fn catalog(&mut self, _: u32, _: &RuntimeEpoch) -> Result<Vec<AndroidApplication>, String> {
        self.catalog.clone()
    }
    fn inspect(&mut self, package: &str, _: u32) -> Result<ApplicationInspection, String> {
        self.inspected.push(package.into());
        self.identities
            .get(package)
            .cloned()
            .ok_or("package is not installed".into())
    }
}

fn pin(name: &str) -> FilePin {
    FilePin {
        path: PathBuf::from(format!("/fixture/{name}")),
        bytes: 20,
        sha256: "c".repeat(64),
    }
}

fn fixture() -> (
    PreparationIntent,
    StaticSelection,
    GateRegistry,
    ReadOnlyFake,
) {
    let epoch = RuntimeEpoch {
        boot_id: "97d9600f-e081-465c-9e6e-62651e09806b".into(),
        cell_host_pid: 10,
        framework_host_pid: 20,
        framework_start_ticks: 30,
    };
    let intent = PreparationIntent {
        schema: 1,
        selection: pin("selected.json"),
        source_receipt: pin("admitted-source.json"),
        main_qualification: pin("main.json"),
        expected_epoch: epoch.clone(),
        gate_registry: pin("gates.json"),
        specification: pin("cell.json"),
        android_user: 0,
    };
    let mut selection = StaticSelection {
        schema: "p4-selected39-static-launch-inputs-v1".into(),
        package_count: 39,
        apk_file_count: 65,
        apk_total_bytes: 0,
        this_is_an_executable_runtime_plan: false,
        all_current_apk_hashes_match_verified_signature_receipt: true,
        applications: Vec::new(),
    };
    let mut gates = GateRegistry {
        schema: "pocket4-app-release-gates-v1".into(),
        common_gates: crate::release::COMMON_GATES
            .iter()
            .map(|gate| (gate.to_string(), format!("Required {gate}")))
            .collect(),
        profiles: BTreeMap::from([(
            "retail".into(),
            GateProfile {
                checks: BTreeMap::from([
                    (
                        "retail.search".into(),
                        "Verify matching populated results in the owned foreground UI".into(),
                    ),
                    (
                        "retail.account".into(),
                        "Authorized test account only; no paid order".into(),
                    ),
                ]),
            },
        )]),
        packages: BTreeMap::new(),
    };
    let mut client = ReadOnlyFake {
        catalog: Ok(Vec::new()),
        identities: BTreeMap::new(),
        inspected: Vec::new(),
    };
    for index in 0..39 {
        let package = format!("org.example.app{index}");
        let signer = "d".repeat(64);
        let base = MaterialFile {
            path: PathBuf::from(format!("/download/{package}/original.apk")),
            bytes: 101,
            sha256: "a".repeat(64),
            expected_normalized_pm_name: Some("base.apk".into()),
            sdk37_signature_valid: true,
            verified_signer_certificates_sha256: vec![signer.clone()],
        };
        let mut materials = vec![base];
        if index < 26 {
            materials.push(MaterialFile {
                path: PathBuf::from(format!("/download/{package}/not-the-pm-filename.apk")),
                bytes: 43,
                sha256: "b".repeat(64),
                expected_normalized_pm_name: None,
                sdk37_signature_valid: true,
                verified_signer_certificates_sha256: vec![signer.clone()],
            });
        }
        selection.apk_total_bytes += materials.iter().map(|file| file.bytes).sum::<u64>();
        let component = format!("{package}/.Main");
        let actual = ApplicationInspection {
            package: package.clone(),
            user: 0,
            uid: 10_000 + index,
            version_code: 42,
            epoch: epoch.clone(),
            apks: materials
                .iter()
                .enumerate()
                .map(|(i, file)| InstalledApk {
                    name: if i == 0 {
                        "base.apk".into()
                    } else {
                        "split_config.arm64.apk".into()
                    },
                    path: format!("/data/app/current/{package}/{i}.apk"),
                    bytes: file.bytes,
                    sha256: file.sha256.clone(),
                })
                .collect(),
        };
        client.identities.insert(package.clone(), actual);
        client.catalog.as_mut().unwrap().push(AndroidApplication {
            package: package.clone(),
            component: format!("{package}/{package}.Main"),
            name: format!("App {index}"),
            icon_key: "fixture".into(),
        });
        selection.applications.push(SourceApplication {
            package: package.clone(), application_label: format!("App {index}"), role: "third_party".into(),
            version_code: 42, version_name: "42.0".into(), latest_material_status: "public_release_version_matches_selected".into(),
            latest_device_delivery_verified: false, current_payload_hashes_rechecked: true, material_files: materials,
            signer_certificates_sha256: vec![signer], signature_verification_source: pin("original-source.json"),
            launcher_candidates: vec![LauncherCandidate { component: component.clone() }],
            preferred_manifest_component: Some(component), original_registry_preconditions: json!({"in_place_update_signer_precondition_met":true}),
        });
        gates.packages.insert(
            package.clone(),
            PackageProfile {
                app: package,
                kind: "third_party".into(),
                profile: "retail".into(),
                prerequisites: vec!["authorized test account".into()],
            },
        );
    }
    (intent, selection, gates, client)
}

#[test]
fn all_39_and_65_apks_become_the_existing_runtime_schema_without_business_credit() {
    let (intent, selection, gates, mut client) = fixture();
    validate_selection(&selection, 39).unwrap();
    let report = prepare(&intent, pin("intent"), &selection, &gates, &mut client).unwrap();
    assert!(report.bindings_complete);
    assert_eq!(report.selected_applications, 39);
    assert_eq!(report.routable_applications, 39);
    assert_eq!(report.source_apk_files, 65);
    assert_eq!(report.accepted_applications, 0);
    assert_eq!(report.app_launches, 0);
    assert_eq!(report.app_installs, 0);
    assert_eq!(client.inspected.len(), 39);
    assert!(
        !report.production_ready
            && !report.runtime_qualified
            && !report.main_qualification_semantics_checked
    );
    let encoded = serde_json::to_vec(&report.runtime_plan).unwrap();
    let parsed: RuntimePlan = serde_json::from_slice(&encoded).unwrap();
    validate(&parsed, &gates, 39).unwrap();
    assert_eq!(parsed.schema, 3);
    assert!(!parsed.execute_public_browser);
    assert_eq!(
        parsed.applications[0].expected_input.as_ref().unwrap().apks[1].name,
        "split_config.arm64.apk"
    );
    assert!(report.applications.iter().all(|app| {
        app.gate_assertions.len() == 8
            && app
                .gate_assertions
                .iter()
                .all(|gate| gate.status == "pending" && gate.evidence.is_none())
    }));
    assert_eq!(report.applications[0].version_name, "42.0");
    assert_eq!(
        report.applications[0].admitted_source_receipt.path,
        Path::new("/fixture/admitted-source.json")
    );
}

#[test]
fn unavailable_catalog_or_packages_never_shrinks_selection() {
    for missing_catalog in [false, true] {
        let (intent, selection, gates, mut client) = fixture();
        if missing_catalog {
            client.catalog = Err("framework is not Ready".into());
        } else {
            client.identities.clear();
        }
        let report = prepare(&intent, pin("intent"), &selection, &gates, &mut client).unwrap();
        assert!(!report.bindings_complete);
        assert_eq!(report.blocked_applications, 39);
        assert_eq!(report.applications.len(), 39);
        assert_eq!(client.inspected.len(), 39);
        assert_eq!(report.runtime_plan.applications.len(), 39);
        assert!(
            report
                .runtime_plan
                .applications
                .iter()
                .all(|app| app.launch.is_none() && app.binding_failure.is_some())
        );
        assert!(report.applications.iter().all(|app| {
            app.gate_assertions
                .iter()
                .all(|gate| gate.status == "blocked")
        }));
        validate(&report.runtime_plan, &gates, 39).unwrap();
    }
}

#[test]
fn changed_epoch_user_version_and_full_apk_set_are_per_app_blockers() {
    for change in 0..8 {
        let (intent, selection, gates, mut client) = fixture();
        let actual = client.identities.get_mut("org.example.app0").unwrap();
        match change {
            0 => actual.epoch.framework_start_ticks += 1,
            1 => actual.user += 1,
            2 => actual.version_code += 1,
            3 => actual.apks[0].sha256 = "e".repeat(64),
            4 => {
                actual.apks.pop();
            }
            5 => {
                actual.apks.push(actual.apks[0].clone());
            }
            6 => actual.apks[0].name = "split_other.apk".into(),
            _ => actual.uid += 100_000,
        }
        let report = prepare(&intent, pin("intent"), &selection, &gates, &mut client).unwrap();
        assert_eq!(report.blocked_applications, 1, "change {change}");
        assert_eq!(report.routable_applications, 38);
        assert!(report.applications[0].inspection.is_some());
        assert!(report.runtime_plan.applications[0].launch.is_none());
        assert!(
            report.runtime_plan.applications[0]
                .binding_failure
                .is_some()
        );
    }
}

#[test]
fn source_signers_receipt_and_duplicate_byte_mapping_cannot_be_invented() {
    for change in 0..7 {
        let (intent, mut selection, gates, mut client) = fixture();
        let source = &mut selection.applications[0];
        match change {
            0 => source.signature_verification_source.sha256 = "e".repeat(64),
            1 => source.material_files[0].sdk37_signature_valid = false,
            2 => source.material_files[1].verified_signer_certificates_sha256[0] = "e".repeat(64),
            3 => {
                source.material_files[1].expected_normalized_pm_name =
                    Some("split_config.arm64.apk".into())
            }
            4 => {
                source.material_files[1].bytes = source.material_files[0].bytes;
                source.material_files[1].sha256 = source.material_files[0].sha256.clone();
            }
            5 => source.signer_certificates_sha256.clear(),
            _ => source.current_payload_hashes_rechecked = false,
        }
        let report = prepare(&intent, pin("intent"), &selection, &gates, &mut client).unwrap();
        assert_eq!(report.blocked_applications, 1, "change {change}");
        assert!(report.applications[0].inspection.is_none());
        assert_eq!(client.inspected.len(), 38);
    }
}

#[test]
fn current_enabled_alias_is_required_and_ambiguity_is_not_a_default_flag() {
    let (intent, mut selection, gates, mut client) = fixture();
    let source = &mut selection.applications[0];
    source.launcher_candidates.push(LauncherCandidate {
        component: "org.example.app0/.Alternate".into(),
    });
    client.catalog.as_mut().unwrap()[0].component = "org.example.app0/.Alternate".into();
    let report = prepare(&intent, pin("intent"), &selection, &gates, &mut client).unwrap();
    assert_eq!(
        report.applications[0].selected_component.as_deref(),
        Some("org.example.app0/org.example.app0.Alternate")
    );
    let original = client.catalog.as_ref().unwrap()[0].clone();
    client.catalog.as_mut().unwrap().push(original);
    let report = prepare(&intent, pin("intent"), &selection, &gates, &mut client).unwrap();
    assert_eq!(report.blocked_applications, 1);
    client
        .catalog
        .as_mut()
        .unwrap()
        .retain(|entry| entry.package != "org.example.app0");
    let report = prepare(&intent, pin("intent"), &selection, &gates, &mut client).unwrap();
    assert_eq!(report.blocked_applications, 1);
}

#[test]
fn source_freshness_and_signer_migration_remain_unresolved_after_matching_launch_binding() {
    let (intent, mut selection, gates, mut client) = fixture();
    selection.applications[0].latest_material_status =
        "public_release_version_differs_requires_resolution".into();
    selection.applications[0].original_registry_preconditions = json!({
        "current_signer_set_matches_candidate":false,"in_place_update_signer_precondition_met":false,
        "business_data_migration_accepted":false,"runtime_data_compatibility_accepted":false,
    });
    let report = prepare(&intent, pin("intent"), &selection, &gates, &mut client).unwrap();
    assert_eq!(report.routable_applications, 39);
    assert_eq!(
        report.applications[0].original_registry_preconditions["business_data_migration_accepted"],
        false
    );
    assert_eq!(
        report.applications[0].latest_material_status,
        "public_release_version_differs_requires_resolution"
    );
    assert_eq!(report.accepted_applications, 0);
    assert!(
        !report.applications[0].latest_device_delivery_verified
            && !report.applications[0].production_ready
    );
}

#[test]
fn missing_or_duplicate_rows_and_inconsistent_totals_are_rejected() {
    let (_, selection, _, _) = fixture();
    assert!(validate_selection(&selection, 42).is_err());
    for change in 0..5 {
        let mut changed = selection.clone();
        match change {
            0 => {
                changed.applications.pop();
            }
            1 => changed.applications[1] = changed.applications[0].clone(),
            2 => changed.apk_total_bytes += 1,
            3 => changed.apk_file_count -= 1,
            _ => changed.this_is_an_executable_runtime_plan = true,
        }
        assert!(validate_selection(&changed, 39).is_err(), "change {change}");
    }
}

#[test]
fn missing_explicit_live_binding_fails_before_any_daemon_connection() {
    let (intent, _, _, _) = fixture();
    let directory = tempfile::tempdir().unwrap();
    for field in [
        "expected_epoch",
        "android_user",
        "source_receipt",
        "main_qualification",
        "gate_registry",
        "specification",
    ] {
        let mut value = serde_json::to_value(&intent).unwrap();
        value.as_object_mut().unwrap().remove(field);
        let raw = serde_json::to_vec(&value).unwrap();
        let path = directory.path().join(format!("missing-{field}.json"));
        std::fs::write(&path, &raw).unwrap();
        let error = prepare_files(
            Path::new("/no-runtime-socket"),
            &path,
            &hex::encode(Sha256::digest(&raw)),
            39,
        )
        .unwrap_err();
        assert!(error.contains(field), "{error}");
        assert!(error.contains("missing field"), "{error}");
    }
}

#[test]
fn source_selection_cannot_change_behind_an_external_intent_pin() {
    let (mut intent, _, _, _) = fixture();
    let directory = tempfile::tempdir().unwrap();
    let source_path = directory.path().join("source.json");
    std::fs::write(&source_path, b"original").unwrap();
    intent.selection = FilePin {
        path: source_path.clone(),
        bytes: 8,
        sha256: hex::encode(Sha256::digest(b"original")),
    };
    let raw = serde_json::to_vec(&intent).unwrap();
    let path = directory.path().join("intent.json");
    std::fs::write(&path, &raw).unwrap();
    std::fs::write(source_path, b"replaced").unwrap();
    let error = prepare_files(
        Path::new("/no-runtime-socket"),
        &path,
        &hex::encode(Sha256::digest(raw)),
        39,
    )
    .unwrap_err();
    assert!(error.contains("bytes differ"), "{error}");
}
