//! Bind the reviewed source selection to fresh read-only daemon observations.
//!
//! The manifest's downloaded filenames and default activity flags are not PM
//! identities. This module cannot install, launch, close, or modify Android.
use super::*;
use droidloom_supervisor::control::{AndroidApplication, CellState};
use serde_json::Value;

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct PreparationIntent {
    schema: u32,
    selection: FilePin,
    /// Admitted byte-identical copy of the reviewed signature/material receipt.
    source_receipt: FilePin,
    main_qualification: FilePin,
    expected_epoch: RuntimeEpoch,
    gate_registry: FilePin,
    specification: FilePin,
    android_user: u32,
}

// The source producer also records static manifest diagnostics and historical
// provenance. Consume only the documented fields below; ignored annotations
// never create runtime authority or imply acceptance.
#[derive(Clone, Debug, Deserialize, Serialize)]
struct StaticSelection {
    schema: String,
    package_count: usize,
    apk_file_count: usize,
    apk_total_bytes: u64,
    this_is_an_executable_runtime_plan: bool,
    all_current_apk_hashes_match_verified_signature_receipt: bool,
    applications: Vec<SourceApplication>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct MaterialFile {
    path: PathBuf,
    bytes: u64,
    sha256: String,
    expected_normalized_pm_name: Option<String>,
    sdk37_signature_valid: bool,
    verified_signer_certificates_sha256: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct LauncherCandidate {
    component: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct SourceApplication {
    package: String,
    application_label: String,
    role: String,
    version_code: u64,
    version_name: String,
    latest_material_status: String,
    latest_device_delivery_verified: bool,
    current_payload_hashes_rechecked: bool,
    material_files: Vec<MaterialFile>,
    signer_certificates_sha256: Vec<String>,
    signature_verification_source: FilePin,
    launcher_candidates: Vec<LauncherCandidate>,
    preferred_manifest_component: Option<String>,
    original_registry_preconditions: Value,
}

/// Source facts retained even when a schema-3 plan is extracted from its
/// preparation report. These facts never become installed-identity or gate credit.
#[derive(Clone, Debug, Serialize)]
pub(super) struct SourceAnnotations {
    application_label: String,
    role: String,
    version_code: u64,
    version_name: String,
    material_files: Vec<MaterialFile>,
    signature_verification_source: FilePin,
    latest_material_status: String,
    latest_device_delivery_verified: bool,
    original_registry_preconditions: Value,
}

/// Bind annotations to the exact full selected roster before any runtime action.
pub(super) fn source_annotations(
    plan: &RuntimePlan,
) -> Result<BTreeMap<String, SourceAnnotations>, String> {
    let Some(pin) = &plan.source_selection else {
        return Ok(BTreeMap::new());
    };
    let selection: StaticSelection = serde_json::from_slice(&pinned(pin)?)
        .map_err(|error| format!("runtime source_selection: {error}"))?;
    validate_selection(&selection, plan.applications.len())?;
    let selected: BTreeMap<_, _> = selection
        .applications
        .iter()
        .map(|app| (app.package.as_str(), app))
        .collect();
    let mut annotations = BTreeMap::new();
    for requested in &plan.applications {
        let app = selected
            .get(requested.package.as_str())
            .ok_or("runtime plan package differs from the complete pinned source selection")?;
        if let Some(input) = &requested.expected_input {
            validate_source(app, &input.source_receipt)?;
            let source: BTreeSet<_> = app
                .material_files
                .iter()
                .map(|file| (file.bytes, file.sha256.as_str()))
                .collect();
            let expected: BTreeSet<_> = input
                .apks
                .iter()
                .map(|file| (file.bytes, file.sha256.as_str()))
                .collect();
            let base = app
                .material_files
                .iter()
                .find(|file| file.expected_normalized_pm_name.as_deref() == Some("base.apk"))
                .ok_or("source base APK missing")?;
            let expected_base = input.apks.iter().find(|file| file.name == "base.apk");
            if input.version_code != app.version_code
                || source != expected
                || expected.len() != input.apks.len()
                || !expected_base
                    .is_some_and(|file| file.bytes == base.bytes && file.sha256 == base.sha256)
            {
                return Err("runtime version or complete APK identities differ from pinned source_selection".into());
            }
        }
        if let Some(launch) = &requested.launch {
            let component = launch_route::normalized(&launch.component, &app.package)?;
            if !app.launcher_candidates.iter().any(|candidate| {
                launch_route::normalized(&candidate.component, &app.package)
                    .is_ok_and(|value| value == component)
            }) {
                return Err(
                    "runtime launch route is not in the pinned source candidate set".into(),
                );
            }
        }
        if annotations
            .insert(
                app.package.clone(),
                SourceAnnotations {
                    application_label: app.application_label.clone(),
                    role: app.role.clone(),
                    version_code: app.version_code,
                    version_name: app.version_name.clone(),
                    material_files: app.material_files.clone(),
                    signature_verification_source: app.signature_verification_source.clone(),
                    latest_material_status: app.latest_material_status.clone(),
                    latest_device_delivery_verified: app.latest_device_delivery_verified,
                    original_registry_preconditions: app.original_registry_preconditions.clone(),
                },
            )
            .is_some()
        {
            return Err("runtime plan repeats a package from source_selection".into());
        }
    }
    Ok(annotations)
}

#[derive(Debug, Serialize)]
struct PreparedApplication {
    package: String,
    application: String,
    role: String,
    version_code: u64,
    version_name: String,
    source_selection: FilePin,
    admitted_source_receipt: FilePin,
    material_files: Vec<MaterialFile>,
    latest_material_status: String,
    latest_device_delivery_verified: bool,
    original_registry_preconditions: Value,
    inspection: Option<ApplicationInspection>,
    enabled_reviewed_components: Vec<String>,
    selected_component: Option<String>,
    binding_failure: Option<String>,
    prerequisites: Vec<String>,
    gate_assertions: Vec<GateAssertion>,
    app_launches: usize,
    production_ready: bool,
}

/// Complete read-only preparation, including every blocked source row. The
/// nested runtime_plan is the existing schema-3 input, not a success receipt.
#[derive(Debug, Serialize)]
pub struct PreparationReport {
    schema: &'static str,
    intent: FilePin,
    /// Every selected row has a matching live PM identity and enabled launch route.
    pub bindings_complete: bool,
    selected_applications: usize,
    routable_applications: usize,
    blocked_applications: usize,
    source_apk_files: usize,
    runtime_plan: RuntimePlan,
    applications: Vec<PreparedApplication>,
    app_launches: usize,
    app_installs: usize,
    accepted_applications: usize,
    main_qualification_semantics_checked: bool,
    runtime_qualified: bool,
    production_ready: bool,
    meaning: &'static str,
}

/// Deliberately excludes every mutating control operation.
trait PreparationClient {
    fn catalog(
        &mut self,
        user: u32,
        epoch: &RuntimeEpoch,
    ) -> Result<Vec<AndroidApplication>, String>;
    fn inspect(&mut self, package: &str, user: u32) -> Result<ApplicationInspection, String>;
}

impl PreparationClient for SocketClient<'_> {
    fn catalog(
        &mut self,
        user: u32,
        epoch: &RuntimeEpoch,
    ) -> Result<Vec<AndroidApplication>, String> {
        let reply = control::request(self.socket, &ControlRequest::ListApplications { user })
            .map_err(|error| error.to_string())?;
        if !reply.ok {
            return Err(reply.message);
        }
        if reply.state != CellState::Running || reply.host_pid != Some(epoch.cell_host_pid) {
            return Err(
                "launcher catalog belongs to a different or non-running Android owner".into(),
            );
        }
        reply
            .applications
            .ok_or("daemon omitted the current enabled launcher catalog".into())
    }

    fn inspect(&mut self, package: &str, user: u32) -> Result<ApplicationInspection, String> {
        // In particular, preserve Gallery's whole-image custody requirement.
        inspect_package_with_custody(self.socket, package, user).map(|(application, _)| application)
    }
}

fn same_bytes(left: &FilePin, right: &FilePin) -> bool {
    left.bytes == right.bytes && left.sha256 == right.sha256
}

fn validate_selection(selection: &StaticSelection, expected_count: usize) -> Result<(), String> {
    if selection.schema != "p4-selected39-static-launch-inputs-v1"
        || selection.this_is_an_executable_runtime_plan
        || !selection.all_current_apk_hashes_match_verified_signature_receipt
        || !(1..=1024).contains(&expected_count)
        || selection.package_count != expected_count
        || selection.applications.len() != expected_count
    {
        return Err(
            "selection schema, complete selected count, or reviewed source-only scope differs"
                .into(),
        );
    }
    let mut packages = BTreeSet::new();
    let mut count = 0usize;
    let mut bytes = 0u64;
    for app in &selection.applications {
        if !crate::valid_package(&app.package) || !packages.insert(&app.package) {
            return Err(format!(
                "selection contains an invalid or repeated package: {}",
                app.package
            ));
        }
        count = count
            .checked_add(app.material_files.len())
            .ok_or("source APK count overflow")?;
        for file in &app.material_files {
            bytes = bytes
                .checked_add(file.bytes)
                .ok_or("source APK byte count overflow")?;
        }
    }
    if count != selection.apk_file_count || bytes != selection.apk_total_bytes {
        return Err("complete selected APK file/byte totals differ from the source receipt".into());
    }
    Ok(())
}

fn validate_source(app: &SourceApplication, admitted_receipt: &FilePin) -> Result<(), String> {
    if app.version_code == 0
        || app.version_name.is_empty()
        || app.version_name.len() > 256
        || app.application_label.is_empty()
        || app.application_label.len() > 256
        || !matches!(app.role.as_str(), "system" | "third_party")
        || !app.current_payload_hashes_rechecked
        || app.material_files.is_empty()
        || app.material_files.len() > 64
        || !same_bytes(&app.signature_verification_source, admitted_receipt)
    {
        return Err("selected version/material set or admitted signature receipt does not match the reviewed source".into());
    }
    let signers: BTreeSet<_> = app.signer_certificates_sha256.iter().collect();
    if signers.is_empty()
        || signers.len() > 16
        || signers.len() != app.signer_certificates_sha256.len()
        || !signers.iter().all(|value| crate::release::valid_sha(value))
    {
        return Err("reviewed source signer set is empty, repeated or malformed".into());
    }
    let mut identities = BTreeSet::new();
    let mut paths = BTreeSet::new();
    let mut bases = 0;
    for file in &app.material_files {
        if !file.path.is_absolute()
            || !paths.insert(&file.path)
            || file.bytes == 0
            || file.bytes > 1024 * 1024 * 1024
            || !crate::release::valid_sha(&file.sha256)
            || !file.sdk37_signature_valid
            || !identities.insert((file.bytes, &file.sha256))
            || file.verified_signer_certificates_sha256.len() != signers.len()
            || file
                .verified_signer_certificates_sha256
                .iter()
                .collect::<BTreeSet<_>>()
                != signers
        {
            return Err("source APK byte identity or verified signer set is invalid, ambiguous or inconsistent".into());
        }
        match file.expected_normalized_pm_name.as_deref() {
            Some("base.apk") => bases += 1,
            None => (),
            Some(_) => {
                return Err(
                    "source must not infer split names before a live PM observation".into(),
                );
            }
        }
    }
    if bases != 1 {
        return Err("source does not identify exactly one base APK".into());
    }
    if app.launcher_candidates.is_empty() || app.launcher_candidates.len() > 128 {
        return Err("reviewed manifest has no bounded launcher candidate set".into());
    }
    let mut components = BTreeSet::new();
    for candidate in &app.launcher_candidates {
        if !components.insert(launch_route::normalized(
            &candidate.component,
            &app.package,
        )?) {
            return Err("reviewed launcher candidates repeat a normalized component".into());
        }
    }
    if let Some(preferred) = &app.preferred_manifest_component {
        if !components.contains(&launch_route::normalized(preferred, &app.package)?) {
            return Err("preferred launcher is not in the reviewed candidate set".into());
        }
    }
    Ok(())
}

fn bind_installed(
    app: &SourceApplication,
    actual: &ApplicationInspection,
    intent: &PreparationIntent,
) -> Result<ExpectedInput, String> {
    if actual.package != app.package
        || actual.user != intent.android_user
        || actual.uid / 100_000 != intent.android_user
        || actual.epoch != intent.expected_epoch
    {
        return Err("PM observation differs from the selected package/user or independently pinned physical Main epoch".into());
    }
    if actual.version_code != app.version_code || actual.apks.len() != app.material_files.len() {
        return Err(
            "installed version or complete APK count differs from the selected source".into(),
        );
    }
    let source: BTreeMap<_, _> = app
        .material_files
        .iter()
        .map(|file| ((file.bytes, file.sha256.as_str()), file))
        .collect();
    let mut names = BTreeSet::new();
    let mut identities = BTreeSet::new();
    let mut apks = Vec::new();
    for apk in &actual.apks {
        if apk.name.is_empty()
            || apk.name.len() > 255
            || !apk.name.ends_with(".apk")
            || apk.name.contains(['/', '\\'])
            || !names.insert(apk.name.as_str())
            || !identities.insert((apk.bytes, apk.sha256.as_str()))
        {
            return Err(
                "PM APK names or byte identities are invalid, repeated or ambiguous".into(),
            );
        }
        let material = source
            .get(&(apk.bytes, apk.sha256.as_str()))
            .ok_or("installed complete APK byte identities differ from the reviewed source")?;
        if (apk.name == "base.apk")
            != (material.expected_normalized_pm_name.as_deref() == Some("base.apk"))
        {
            return Err("PM base APK bytes do not identify the selected source base".into());
        }
        apks.push(ApkInput {
            name: apk.name.clone(),
            bytes: apk.bytes,
            sha256: apk.sha256.clone(),
        });
    }
    if !names.contains("base.apk") || identities.len() != source.len() {
        return Err("complete PM APK set omits or duplicates a source identity".into());
    }
    apks.sort_by(|a, b| a.name.cmp(&b.name));
    Ok(ExpectedInput {
        version_code: app.version_code,
        apks,
        source_receipt: intent.source_receipt.clone(),
    })
}

fn enabled_candidates(
    app: &SourceApplication,
    catalog: &[AndroidApplication],
) -> Result<Vec<String>, String> {
    let reviewed = app
        .launcher_candidates
        .iter()
        .map(|candidate| launch_route::normalized(&candidate.component, &app.package))
        .collect::<Result<BTreeSet<_>, _>>()?;
    catalog
        .iter()
        .filter(|entry| entry.package == app.package)
        .map(|entry| launch_route::normalized(&entry.component, &app.package))
        .filter(|component| {
            component
                .as_ref()
                .map_or(true, |value| reviewed.contains(value))
        })
        .collect()
}

fn select_component(app: &SourceApplication, enabled: &[String]) -> Result<String, String> {
    if enabled.iter().collect::<BTreeSet<_>>().len() != enabled.len() {
        return Err("current enabled MAIN/LAUNCHER catalog repeats a reviewed component".into());
    }
    if let Some(preferred) = &app.preferred_manifest_component {
        let preferred = launch_route::normalized(preferred, &app.package)?;
        if enabled.contains(&preferred) {
            return Ok(preferred);
        }
    }
    if enabled.len() != 1 {
        return Err(
            "reviewed launcher is absent or ambiguous in the current enabled MAIN/LAUNCHER catalog"
                .into(),
        );
    }
    Ok(enabled[0].clone())
}

fn skeleton(intent: &PreparationIntent, selection: &StaticSelection) -> RuntimePlan {
    RuntimePlan {
        schema: 3,
        android_user: intent.android_user,
        main_qualification: intent.main_qualification.clone(),
        expected_epoch: intent.expected_epoch.clone(),
        gate_registry: intent.gate_registry.clone(),
        applications: selection
            .applications
            .iter()
            .map(|app| ApplicationPlan {
                package: app.package.clone(),
                expected_input: None,
                leaf: None,
                launch: None,
                binding_failure: None,
            })
            .collect(),
        execute_public_browser: false,
        browser_fixture: None,
        preparation_selection: None,
        source_selection: Some(intent.selection.clone()),
    }
}

fn prepare(
    intent: &PreparationIntent,
    intent_pin: FilePin,
    selection: &StaticSelection,
    gates: &GateRegistry,
    client: &mut impl PreparationClient,
) -> Result<PreparationReport, String> {
    let mut plan = skeleton(intent, selection);
    validate(&plan, gates, selection.package_count)?;
    let catalog = client.catalog(intent.android_user, &intent.expected_epoch);
    let mut applications = Vec::new();
    for (app, destination) in selection.applications.iter().zip(&mut plan.applications) {
        let profile = &gates.packages[&app.package];
        let mut row = PreparedApplication {
            package: app.package.clone(),
            application: app.application_label.clone(),
            role: app.role.clone(),
            version_code: app.version_code,
            version_name: app.version_name.clone(),
            source_selection: intent.selection.clone(),
            admitted_source_receipt: intent.source_receipt.clone(),
            material_files: app.material_files.clone(),
            latest_material_status: app.latest_material_status.clone(),
            latest_device_delivery_verified: app.latest_device_delivery_verified,
            original_registry_preconditions: app.original_registry_preconditions.clone(),
            inspection: None,
            enabled_reviewed_components: Vec::new(),
            selected_component: None,
            binding_failure: None,
            prerequisites: profile.prerequisites.clone(),
            gate_assertions: pending_assertions(gates, &profile.profile),
            app_launches: 0,
            production_ready: false,
        };
        let binding = (|| {
            validate_source(app, &intent.source_receipt)?;
            let actual = client.inspect(&app.package, intent.android_user)?;
            row.inspection = Some(actual.clone());
            destination.expected_input = Some(bind_installed(app, &actual, intent)?);
            let catalog = catalog
                .as_ref()
                .map_err(|error| format!("current launcher catalog unavailable: {error}"))?;
            row.enabled_reviewed_components = enabled_candidates(app, catalog)?;
            let component = select_component(app, &row.enabled_reviewed_components)?;
            let launch = LaunchPlan {
                specification: intent.specification.clone(),
                component: component.clone(),
            };
            launch.validate(&app.package)?;
            row.selected_component = Some(component);
            destination.launch = Some(launch);
            Ok::<(), String>(())
        })();
        if let Err(error) = binding {
            let bounded: String = error.chars().take(1000).collect();
            destination.binding_failure = Some(bounded.clone());
            row.binding_failure = Some(bounded.clone());
            for gate in &mut row.gate_assertions {
                gate.status = "blocked";
                gate.reason =
                    format!("Plan binding failed: {bounded}; no business assertion was executed");
            }
        }
        applications.push(row);
    }
    validate(&plan, gates, selection.package_count)?;
    let routable = plan
        .applications
        .iter()
        .filter(|app| app.launch.is_some())
        .count();
    Ok(PreparationReport {
        schema: "droidloom-runtime-plan-preparation-v1",
        intent: intent_pin,
        bindings_complete: routable == selection.package_count,
        selected_applications: selection.package_count,
        routable_applications: routable,
        blocked_applications: selection.package_count - routable,
        source_apk_files: selection.apk_file_count,
        runtime_plan: plan,
        applications,
        app_launches: 0,
        app_installs: 0,
        accepted_applications: 0,
        main_qualification_semantics_checked: false,
        runtime_qualified: false,
        production_ready: false,
        meaning: "Source pins, full live PM byte identities and enabled launcher bindings only. The nested schema-3 plan retains every blocked row. Main semantics, freshness/device delivery, data continuity and all application business/common assertions still require their actual qualified evidence. No Android mutation or business action was executed.",
    })
}

/// Prepare an existing runtime-plan schema without launching/installing apps.
/// The caller supplies the independently reviewed intent digest and full count.
pub fn prepare_files(
    socket: &Path,
    intent_path: &Path,
    expected_sha256: &str,
    expected_count: usize,
) -> Result<PreparationReport, String> {
    let raw =
        crate::release::read_frozen(intent_path, INPUT_LIMIT).map_err(|error| error.to_string())?;
    if !crate::release::valid_sha(expected_sha256)
        || hex::encode(Sha256::digest(&raw)) != expected_sha256
    {
        return Err("externally pinned runtime preparation intent SHA-256 differs".into());
    }
    let intent: PreparationIntent = serde_json::from_slice(&raw)
        .map_err(|error| format!("runtime preparation intent binding: {error}"))?;
    if intent.schema != 1 {
        return Err("runtime preparation intent schema must be 1".into());
    }
    let selection: StaticSelection = serde_json::from_slice(&pinned(&intent.selection)?)
        .map_err(|error| format!("static selected source: {error}"))?;
    validate_selection(&selection, expected_count)?;
    let gates: GateRegistry = serde_json::from_slice(&pinned(&intent.gate_registry)?)
        .map_err(|error| format!("gate_registry: {error}"))?;
    for app in &selection.applications {
        if !gates.packages.contains_key(&app.package) {
            return Err(format!(
                "gate_registry.packages lacks the selected package {}",
                app.package
            ));
        }
    }
    for pin in [
        &intent.source_receipt,
        &intent.main_qualification,
        &intent.specification,
    ] {
        pinned(pin)?;
    }
    let intent_pin = FilePin {
        path: intent_path.into(),
        bytes: raw.len() as u64,
        sha256: expected_sha256.into(),
    };
    let report = prepare(
        &intent,
        intent_pin.clone(),
        &selection,
        &gates,
        &mut SocketClient { socket },
    )?;
    for pin in [
        &intent_pin,
        &intent.selection,
        &intent.source_receipt,
        &intent.main_qualification,
        &intent.gate_registry,
        &intent.specification,
    ] {
        pinned(pin)?;
    }
    Ok(report)
}

#[cfg(test)]
#[path = "runtime_prepare_tests.rs"]
mod tests;
