use super::*;
use droidloom_supervisor::control::application_probe::InstalledApk;
use tempfile::TempDir;

#[test]
fn compiled_current_physical_selection_has_one_exact_r7_material_admission() {
    use crate::runtime_plan::physical_gate_roster as roster;
    let compiled = admissions().unwrap();
    let current: Vec<_> = compiled
        .iter()
        .filter(|row| {
            row.selection.bytes == roster::CURRENT_SELECTION_BYTES
                && row.selection.sha256 == roster::CURRENT_SELECTION_SHA256
        })
        .collect();
    assert_eq!(current.len(), 1);
    assert_eq!(current[0].id, "p4-public-apk-candidate-4b91-r7");
    assert_eq!(current[0].package_count, roster::PACKAGE_COUNT);
    assert_eq!(current[0].apk_file_count, 65);
}

fn write_pin(root: &Path, name: &str, raw: &[u8]) -> FilePin {
    let path = root.join(name);
    std::fs::write(&path, raw).unwrap();
    FilePin {
        path,
        bytes: raw.len() as u64,
        sha256: hex::encode(Sha256::digest(raw)),
    }
}

fn materials() -> (
    TempDir,
    VerifiedMaterialBatch,
    ApplicationPlan,
    ApplicationInspection,
) {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().canonicalize().unwrap();
    let package = "org.example.normal";
    let signer = "c".repeat(64);
    let mut signed_files = Vec::new();
    let mut selected_files = Vec::new();
    let mut live = Vec::new();
    for (name, split, byte, size) in [
        ("base.apk", None, 'a', 40u64),
        (
            "split_config.arm64_v8a.apk",
            Some("config.arm64_v8a"),
            'b',
            20u64,
        ),
    ] {
        let hash = byte.to_string().repeat(64);
        let metadata = json!({"name":package,"versionCode":"901",
            "versionName":if split.is_none() { "9.0.1" } else { "" },"split":split});
        let signed = json!({
            "path":format!("/normal/{hash}.apk"),"bytes":size,"sha256":hash,
            "sdk37_signature_valid":true,
            "verified_signer_certificates_sha256":[signer],"metadata":metadata,
        });
        let mut selected = signed.clone();
        selected["expected_normalized_pm_name"] = if split.is_none() {
            json!("base.apk")
        } else {
            Value::Null
        };
        selected["manifest_split_name"] = json!(split);
        signed_files.push(signed);
        selected_files.push(selected);
        live.push(InstalledApk {
            name: name.into(),
            path: format!("/data/app/normal/{name}"),
            bytes: size,
            sha256: hash,
        });
    }
    let signed = json!({"schema":"p4-selected39-materials-and-original-signers-handoff-v1",
        "package_count":1,"file_count":2,"all_selected_materials_verified":true,
        "rows":[{"package":package,"role":"third_party","version_code":901,
            "version_name":"9.0.1","signer_certificates_sha256":[signer],
            "all_file_signatures_and_hashes_verified":true,"files":signed_files}]});
    let signature = write_pin(
        &root,
        "signature.json",
        &serde_json::to_vec(&signed).unwrap(),
    );
    let selected = json!({"schema":"p4-selected39-static-launch-inputs-v1",
        "package_count":1,"apk_file_count":2,"apk_total_bytes":60,
        "this_is_an_executable_runtime_plan":false,
        "all_current_apk_hashes_match_verified_signature_receipt":true,
        "applications":[{"package":package,"role":"third_party","version_code":901,
            "version_name":"9.0.1","signature_verification_source":signature,
            "signer_certificates_sha256":[signer],"material_files":selected_files}]});
    let selection = write_pin(
        &root,
        "selection.json",
        &serde_json::to_vec(&selected).unwrap(),
    );
    let neutral = BytesPin {
        bytes: 1,
        sha256: "0".repeat(64),
    };
    let admission = Admission {
        id: "normal-model-next-batch".into(),
        selection: BytesPin::of(&selection),
        signature_receipt: BytesPin::of(&signature),
        normal_import: neutral.clone(),
        normal_input_verification: neutral,
        package_count: 1,
        apk_file_count: 2,
        apk_total_bytes: 60,
    };
    let (held_selection, selected_raw) = HeldDocument::open(&selection).unwrap();
    let (held_signature, signed_raw) = HeldDocument::open(&signature).unwrap();
    let applications = parse_materials(&admission, &selected_raw, &signed_raw).unwrap();
    let batch = VerifiedMaterialBatch {
        admission,
        selection,
        signature_receipt: signature.clone(),
        applications,
        held_selection,
        held_signature,
    };
    let epoch = RuntimeEpoch {
        boot_id: "00000000-0000-0000-0000-000000000001".into(),
        cell_host_pid: 100,
        framework_host_pid: 101,
        framework_start_ticks: 50,
    };
    let actual = ApplicationInspection {
        package: package.into(),
        user: 0,
        uid: 10042,
        version_code: 901,
        epoch,
        apks: live,
    };
    let requested = ApplicationPlan {
        package: package.into(),
        expected_input: Some(ExpectedInput {
            version_code: 901,
            apks: actual
                .apks
                .iter()
                .map(|apk| ApkInput {
                    name: apk.name.clone(),
                    bytes: apk.bytes,
                    sha256: apk.sha256.clone(),
                })
                .collect(),
            source_receipt: signature,
        }),
        leaf: None,
        launch: None,
        binding_failure: None,
    };
    (temp, batch, requested, actual)
}

#[test]
fn normal_batch_binds_live_complete_splits_without_claiming_remaining_gates() {
    let (_temp, batch, requested, actual) = materials();
    let observed = batch
        .observe(&requested, 0, &actual.epoch, &actual, &actual)
        .unwrap();
    assert_eq!(observed.apks.len(), 2);
    assert_eq!(observed.verified_facets.len(), 8);
    assert_eq!(
        observed.apks[1].manifest_split.as_deref(),
        Some("config.arm64_v8a")
    );
    assert_eq!(observed.version_name_from_verified_apk, "9.0.1");
    assert!(!observed.complete_identity_gate_passed);
    assert!(!observed.latest_version_qualified);
    assert!(!observed.original_data_migration_accepted);
    assert!(!observed.application_accepted);
    assert!(!observed.production_ready);
    batch.revalidate().unwrap();
}

#[test]
fn live_epoch_uid_version_hash_split_and_base_changes_fail_closed() {
    let (_temp, batch, requested, actual) = materials();
    let mut variants = Vec::new();
    let mut other = actual.clone();
    other.epoch.framework_start_ticks += 1;
    variants.push(other);
    let mut other = actual.clone();
    other.uid += 1;
    variants.push(other);
    let mut other = actual.clone();
    other.version_code += 1;
    variants.push(other);
    let mut other = actual.clone();
    other.apks.pop();
    variants.push(other);
    let mut other = actual.clone();
    other.apks[1].sha256 = "d".repeat(64);
    variants.push(other);
    let mut other = actual.clone();
    other.apks[0].name = "split_base.apk".into();
    variants.push(other);
    let mut other = actual.clone();
    other.apks[1].path = "/data/app/replaced/split.apk".into();
    variants.push(other);
    for other in variants {
        assert!(
            batch
                .observe(&requested, 0, &actual.epoch, &actual, &other)
                .is_err()
        );
    }
    let mut wrong_user = actual.clone();
    wrong_user.uid = 110042;
    assert!(
        batch
            .observe(&requested, 0, &actual.epoch, &wrong_user, &wrong_user)
            .is_err()
    );
}

#[test]
fn caller_expected_input_cannot_replace_the_admitted_source_hashes() {
    let (_temp, batch, mut requested, mut actual) = materials();
    actual.apks[1].sha256 = "d".repeat(64);
    requested.expected_input.as_mut().unwrap().apks[1].sha256 = "d".repeat(64);
    assert!(source_matches(
        &actual,
        requested.expected_input.as_ref().unwrap()
    ));
    assert!(
        batch
            .observe(&requested, 0, &actual.epoch, &actual, &actual)
            .is_err()
    );
}

#[test]
fn self_asserted_signer_and_passed_document_cannot_change_admitted_bytes() {
    let (_temp, batch, _, _) = materials();
    let mut signed: Value = serde_json::from_slice(&batch.held_signature.read().unwrap()).unwrap();
    signed["rows"][0]["signer_certificates_sha256"] = json!(["e".repeat(64)]);
    signed["passed"] = json!(true);
    let forged = serde_json::to_vec(&signed).unwrap();
    assert!(
        parse_materials(
            &batch.admission,
            &batch.held_selection.read().unwrap(),
            &forged
        )
        .is_err()
    );
}

#[test]
fn malformed_exact_source_relationship_is_rejected_even_in_a_review_candidate() {
    let (_temp, batch, _, _) = materials();
    let mut selected: Value =
        serde_json::from_slice(&batch.held_selection.read().unwrap()).unwrap();
    let signed = batch.held_signature.read().unwrap();
    selected["applications"][0]["material_files"][1]["manifest_split_name"] = Value::Null;
    let raw = serde_json::to_vec(&selected).unwrap();
    let mut candidate = batch.admission.clone();
    candidate.selection = BytesPin {
        bytes: raw.len() as u64,
        sha256: hex::encode(Sha256::digest(&raw)),
    };
    assert!(parse_materials(&candidate, &raw, &signed).is_err());
}

#[test]
fn equal_byte_named_replacement_does_not_replace_held_material_generation() {
    let (temp, batch, _, _) = materials();
    let bytes = batch.held_selection.read().unwrap();
    let replacement = temp.path().join("replacement.json");
    std::fs::write(&replacement, &bytes).unwrap();
    std::fs::rename(&replacement, &batch.selection.path).unwrap();
    assert!(batch.revalidate().is_err());
}

#[test]
fn changed_material_body_is_rejected_after_live_observation() {
    let (_temp, batch, _, _) = materials();
    std::fs::write(&batch.signature_receipt.path, b"changed").unwrap();
    assert!(batch.revalidate().is_err());
}

fn plan(
    requested: ApplicationPlan,
    actual: &ApplicationInspection,
    selection: FilePin,
) -> RuntimePlan {
    RuntimePlan {
        schema: 3,
        android_user: 0,
        main_qualification: selection.clone(),
        expected_epoch: actual.epoch.clone(),
        gate_registry: selection.clone(),
        applications: vec![requested],
        execute_public_browser: false,
        browser_fixture: None,
        preparation_selection: None,
        source_selection: Some(selection),
    }
}

#[test]
fn unreviewed_normal_batch_cannot_admit_itself_by_passing_a_new_hash() {
    let (_temp, batch, requested, actual) = materials();
    let plan = plan(requested, &actual, batch.selection.clone());
    assert!(admit_plan(&plan).unwrap().is_none());
    assert!(
        admissions()
            .unwrap()
            .iter()
            .all(|a| a.id != "normal-model-next-batch")
    );
}

struct InspectOnly {
    before: ApplicationInspection,
    after: ApplicationInspection,
    calls: usize,
}
impl RuntimeClient for InspectOnly {
    fn inspect(&mut self, _: &str, _: u32) -> Result<ApplicationInspection, String> {
        self.calls += 1;
        Ok(if self.calls == 1 {
            self.before.clone()
        } else {
            self.after.clone()
        })
    }
    fn browser(
        &mut self,
        _: &ApplicationInspection,
        _: &str,
    ) -> Result<(ApplicationInspection, String), String> {
        panic!("identity-only test must not launch a browser")
    }
    fn leaf(
        &mut self,
        _: &ApplicationInspection,
        _: &LeafPlan,
        _: &FilePin,
    ) -> Result<(ApplicationInspection, LeafObservation), String> {
        panic!("identity-only test must not execute a leaf")
    }
    fn launch(
        &mut self,
        _: &ApplicationInspection,
        _: &LaunchPlan,
        _: &FilePin,
    ) -> Result<(ApplicationInspection, LaunchObservation), String> {
        panic!("identity-only test must not launch an activity")
    }
}
fn gates(package: &str) -> GateRegistry {
    GateRegistry {
        schema: "pocket4-app-release-gates-v1".into(),
        common_gates: crate::release::COMMON_GATES
            .iter()
            .map(|k| (k.to_string(), "common gate".into()))
            .collect(),
        profiles: BTreeMap::from([(
            "test".into(),
            GateProfile {
                checks: BTreeMap::from([("test.business".into(), "business".into())]),
            },
        )]),
        packages: BTreeMap::from([(
            package.into(),
            PackageProfile {
                app: package.into(),
                kind: "third_party".into(),
                profile: "test".into(),
                prerequisites: Vec::new(),
            },
        )]),
    }
}
#[test]
fn dispatcher_runs_real_factory_boundary_and_keeps_complete_gate_pending() {
    let (_temp, batch, requested, actual) = materials();
    let plan = plan(requested, &actual, batch.selection.clone());
    let mut client = InspectOnly {
        before: actual.clone(),
        after: actual.clone(),
        calls: 0,
    };
    let report = dispatch_with_materials(
        &plan,
        &gates(&actual.package),
        &mut client,
        Some(&batch),
        false,
    );
    assert_eq!(client.calls, 2);
    assert_eq!(report.material_identity_observations, 1);
    assert_eq!(report.accepted_applications, 0);
    assert_eq!(
        report.applications[0]
            .gate_assertions
            .iter()
            .find(|g| g.id == "identity")
            .unwrap()
            .status,
        "partial"
    );
    assert!(
        report.applications[0]
            .pending_gates
            .iter()
            .any(|g| g == "identity")
    );
    assert!(!report.runtime_qualified);
}

#[test]
fn dispatcher_does_not_credit_a_different_final_main() {
    let (_temp, batch, requested, actual) = materials();
    let plan = plan(requested, &actual, batch.selection.clone());
    let mut after = actual.clone();
    after.epoch.framework_start_ticks += 1;
    let mut client = InspectOnly {
        before: actual.clone(),
        after,
        calls: 0,
    };
    let report = dispatch_with_materials(
        &plan,
        &gates(&actual.package),
        &mut client,
        Some(&batch),
        false,
    );
    assert_eq!(report.material_identity_observations, 0);
    assert_eq!(report.applications[0].status, "blocked");
    assert!(
        report.applications[0]
            .gate_assertions
            .iter()
            .all(|g| g.status == "blocked")
    );
}

#[test]
fn readonly_identity_mode_cannot_execute_a_selected_leaf_or_launcher() {
    let (_temp, batch, mut requested, actual) = materials();
    requested.launch = Some(LaunchPlan {
        component: "org.example.normal/.Main".into(),
        specification: batch.selection.clone(),
    });
    let plan = plan(requested, &actual, batch.selection.clone());
    let mut client = InspectOnly {
        before: actual.clone(),
        after: actual.clone(),
        calls: 0,
    };
    let report = dispatch_with_materials(
        &plan,
        &gates(&actual.package),
        &mut client,
        Some(&batch),
        true,
    );
    assert_eq!(client.calls, 2);
    assert_eq!(report.material_identity_observations, 1);
    assert_eq!(report.applications[0].status, "identity_observation_only");
}

#[test]
fn an_approved_document_prefix_is_not_the_complete_admitted_file() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("material.json");
    let original = b"{\"normal\":true}";
    let pin = FilePin {
        path: path.clone(),
        bytes: original.len() as u64,
        sha256: hex::encode(Sha256::digest(original)),
    };
    let mut with_unpinned_tail = original.to_vec();
    with_unpinned_tail.extend_from_slice(b" caller-controlled trailing bytes");
    std::fs::write(&path, with_unpinned_tail).unwrap();
    assert!(HeldDocument::open(&pin).is_err());
}
