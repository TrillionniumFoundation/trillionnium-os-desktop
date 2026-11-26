//! Executable per-application admission and explicit business-flow routing.
//!
//! This preserves every selected row. A real browser invocation remains partial
//! progress; unsupported profiles and pending gates never become acceptance.
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

use droidloom_supervisor::control::application_probe::{
    ApplicationInspection, RuntimeEpoch, validate_https_url,
};
use droidloom_supervisor::control::application_custody::ImageApplicationCustody;
use droidloom_supervisor::control::{self, ControlRequest};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

#[path = "firefox_wait_result.rs"]
mod firefox_wait_result;
use firefox_wait_result::{FirefoxActivityStart, firefox_activity_start};

#[path = "leaf_routes.rs"]
mod leaf_routes;
#[path = "leaf_release.rs"]
mod leaf_release;
#[path = "leaf_adoption.rs"]
mod leaf_adoption;
#[path = "leaf_unit_entry.rs"]
mod leaf_unit_entry;
use leaf_routes::{LeafObservation, LeafPlan};
#[path = "launch_route.rs"]
mod launch_route;
use launch_route::{LaunchObservation, LaunchPlan};

#[path = "runtime_prepare.rs"]
mod runtime_prepare;
pub use runtime_prepare::{PreparationReport, prepare_files};

/// Execute only a root content-addressed single-app plan in its fixed installed
/// unit. This preserves the original dispatcher and never grants acceptance.
pub fn run_owned_leaf_plan(profile: &str, expected_sha256: &str) -> Result<(), String> {
    leaf_unit_entry::run(profile, expected_sha256)
}

/// Publish one explicitly pinned root CI/source release pairing under the
/// original owner locks. This installs nothing and grants no Android success.
pub fn adopt_native_leaf_release(path: &Path, expected_sha256: &str) -> Result<serde_json::Value, String> {
    leaf_adoption::adopt(path, expected_sha256)
}

const INPUT_LIMIT: u64 = 8 * 1024 * 1024;
const BROWSER_GATES: [&str; 5] = [
    "browser.external_https",
    "browser.document",
    "browser.media",
    "browser.return",
    "browser.recovery",
];

#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct FilePin {
    path: PathBuf,
    bytes: u64,
    sha256: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct ApkInput {
    name: String,
    bytes: u64,
    sha256: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct ExpectedInput {
    version_code: u64,
    apks: Vec<ApkInput>,
    /// Independently reviewed official-artifact/signature receipt; not a new signature claim.
    source_receipt: FilePin,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct ApplicationPlan {
    package: String,
    expected_input: Option<ExpectedInput>,
    #[serde(default)]
    leaf: Option<LeafPlan>,
    #[serde(default)]
    launch: Option<LaunchPlan>,
    /// A failed read-only binding stays blocked until a new plan is prepared.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    binding_failure: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct BrowserFixture {
    url: String,
    input_scope: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct RuntimePlan {
    schema: u32,
    android_user: u32,
    main_qualification: FilePin,
    expected_epoch: RuntimeEpoch,
    gate_registry: FilePin,
    applications: Vec<ApplicationPlan>,
    execute_public_browser: bool,
    browser_fixture: Option<BrowserFixture>,
    #[serde(default)]
    preparation_selection: Option<FilePin>,
    /// Current application source roster; distinct from the fixed native-leaf selector.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    source_selection: Option<FilePin>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct GateProfile {
    checks: BTreeMap<String, String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct PackageProfile {
    app: String,
    kind: String,
    profile: String,
    prerequisites: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct GateRegistry {
    schema: String,
    common_gates: BTreeMap<String, String>,
    profiles: BTreeMap<String, GateProfile>,
    packages: BTreeMap<String, PackageProfile>,
}

#[derive(Debug, Serialize)]
struct GateAssertion {
    id: String,
    description: String,
    scope: &'static str,
    status: &'static str,
    reason: String,
    evidence: Option<FilePin>,
}

fn pending_assertions(gates: &GateRegistry, profile: &str) -> Vec<GateAssertion> {
    gates.common_gates.iter().map(|(id, description)| (id, description, "common"))
        .chain(gates.profiles[profile].checks.iter()
            .map(|(id, description)| (id, description, "business")))
        .map(|(id, description, scope)| GateAssertion {
            id: id.clone(), description: description.clone(), scope,
            status: "pending", reason: "No complete assertion result for this gate in this run".into(),
            evidence: None,
        }).collect()
}

#[derive(Debug, Serialize)]
struct AppDispatch {
    package: String,
    application: String,
    profile: String,
    status: &'static str,
    reason: String,
    expected_input: Option<ExpectedInput>,
    source_context: Option<runtime_prepare::SourceAnnotations>,
    requested_launch: Option<LaunchPlan>,
    requested_leaf: Option<LeafPlan>,
    prerequisites: Vec<String>,
    gate_assertions: Vec<GateAssertion>,
    inspection: Option<ApplicationInspection>,
    invocation_output: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    firefox_activity_start: Option<FirefoxActivityStart>,
    leaf_observation: Option<LeafObservation>,
    #[serde(skip_serializing_if = "Option::is_none")]
    launch_observation: Option<LaunchObservation>,
    pending_gates: Vec<String>,
    accepted_gates: usize,
    runtime_qualified: bool,
    production_ready: bool,
}

/// Actual metadata observations and invoked partial flows, never a release approval.
#[derive(Debug, Serialize)]
pub struct RuntimeReport {
    schema: u32,
    runtime_plan: Option<FilePin>,
    source_selection: Option<FilePin>,
    main_qualification: FilePin,
    expected_epoch: RuntimeEpoch,
    gate_registry: FilePin,
    selected_applications: usize,
    blocked_applications: usize,
    unsupported_business_flows: usize,
    partial_browser_invocations: usize,
    partial_leaf_invocations: usize,
    launch_only_invocations: usize,
    accepted_applications: usize,
    runtime_qualified: bool,
    production_ready: bool,
    automatic_retry: bool,
    main_qualification_semantics_checked: bool,
    meaning: &'static str,
    applications: Vec<AppDispatch>,
}

trait RuntimeClient {
    fn inspect(&mut self, package: &str, user: u32) -> Result<ApplicationInspection, String>;
    fn browser(
        &mut self,
        expected: &ApplicationInspection,
        url: &str,
    ) -> Result<(ApplicationInspection, String), String>;
    fn leaf(
        &mut self,
        expected: &ApplicationInspection,
        plan: &LeafPlan,
        selection: &FilePin,
    ) -> Result<(ApplicationInspection, LeafObservation), String>;
    fn launch(
        &mut self,
        expected: &ApplicationInspection,
        plan: &LaunchPlan,
        source_receipt: &FilePin,
    ) -> Result<(ApplicationInspection, LaunchObservation), String>;
}

struct SocketClient<'a> {
    socket: &'a Path,
}

impl RuntimeClient for SocketClient<'_> {
    fn launch(
        &mut self,
        expected: &ApplicationInspection,
        plan: &LaunchPlan,
        source_receipt: &FilePin,
    ) -> Result<(ApplicationInspection, LaunchObservation), String> {
        let observed = launch_route::execute(self.socket, expected, plan, source_receipt)?;
        Ok((expected.clone(), observed))
    }
    fn inspect(&mut self, package: &str, user: u32) -> Result<ApplicationInspection, String> {
        inspect_package_with_custody(self.socket, package, user).map(|(application, _)| application)
    }
    fn browser(
        &mut self,
        expected: &ApplicationInspection,
        url: &str,
    ) -> Result<(ApplicationInspection, String), String> {
        let reply = control::request(
            self.socket,
            &ControlRequest::OpenBrowser {
                expected: expected.clone(),
                url: url.into(),
            },
        )
        .map_err(|e| e.to_string())?;
        if !reply.ok {
            return Err(reply.message);
        }
        Ok((
            reply
                .inspection
                .ok_or("Browser response lacks post-invocation identity")?,
            reply
                .launch
                .ok_or("Browser response lacks actual activity output")?,
        ))
    }
    fn leaf(
        &mut self,
        expected: &ApplicationInspection,
        plan: &LeafPlan,
        selection: &FilePin,
    ) -> Result<(ApplicationInspection, LeafObservation), String> {
        let result = leaf_routes::execute(plan, selection, expected)?;
        let after = self.inspect(&expected.package, expected.user)?;
        if after != *expected {
            return Err("Main or complete installed identity changed after the original leaf; retained result cannot qualify this plan".into());
        }
        Ok((after, result))
    }
}

fn pinned(reference: &FilePin) -> Result<Vec<u8>, String> {
    if reference.bytes == 0
        || reference.bytes > INPUT_LIMIT
        || !crate::release::valid_sha(&reference.sha256)
    {
        return Err("runtime input has an invalid bounded file identity".into());
    }
    let raw =
        crate::release::read_frozen(&reference.path, reference.bytes).map_err(|e| e.to_string())?;
    if raw.len() as u64 != reference.bytes || hex::encode(Sha256::digest(&raw)) != reference.sha256
    {
        return Err("runtime input file bytes differ from the reviewed pin".into());
    }
    Ok(raw)
}

fn validate(plan: &RuntimePlan, gates: &GateRegistry, expected_count: usize) -> Result<(), String> {
    if !matches!(plan.schema, 1 | 2 | 3)
        || !(1..=1024).contains(&expected_count)
        || plan.applications.len() != expected_count
        || gates.schema != "pocket4-app-release-gates-v1"
        || plan.android_user > 21_474
        || plan.expected_epoch.boot_id.len() != 36
        || plan.expected_epoch.cell_host_pid == 0
        || plan.expected_epoch.framework_host_pid == 0
        || plan.expected_epoch.framework_start_ticks == 0
    {
        return Err(
            "runtime plan schema, complete selected count, or physical Main epoch is invalid"
                .into(),
        );
    }
    if !crate::release::COMMON_GATES.iter().all(|id| {
        gates
            .common_gates
            .get(*id)
            .is_some_and(|s| !s.trim().is_empty())
    }) {
        return Err("runtime registry omits a required common gate".into());
    }
    let has_leaves = plan.applications.iter().any(|app| app.leaf.is_some());
    if has_leaves && (!matches!(plan.schema, 2 | 3) || plan.preparation_selection.is_none()) {
        return Err(
            "finite leaf execution requires schema 2 or 3 and the complete selected preparation receipt"
                .into(),
        );
    }
    let mut seen = BTreeSet::new();
    for app in &plan.applications {
        if !seen.insert(&app.package) {
            return Err("runtime selection repeats a package".into());
        }
        if let Some(error) = &app.binding_failure {
            if error.trim().is_empty() || error.len() > 4096 || app.launch.is_some() || app.leaf.is_some() {
                return Err("a failed preparation binding must retain one bounded reason and no executable route".into());
            }
        }
        if let Some(launch) = &app.launch {
            launch.validate(&app.package)?;
            if plan.schema != 3 || app.expected_input.is_none() || app.leaf.is_some()
                || (app.package == "org.mozilla.firefox" && plan.execute_public_browser)
            {
                return Err("launch-only execution requires schema 3, complete reviewed input, and one explicit route per application".into());
            }
        }
        if let Some(leaf) = &app.leaf {
            if leaf.route.package() != app.package || app.expected_input.is_none() {
                return Err(
                    "leaf route package and complete official application source must match".into(),
                );
            }
        }
        let package = gates
            .packages
            .get(&app.package)
            .ok_or("runtime selection has no registered package profile")?;
        let profile = gates
            .profiles
            .get(&package.profile)
            .ok_or("registered business profile is missing")?;
        if profile.checks.is_empty()
            || profile.checks.len() > 128
            || profile.checks.values().any(|v| v.trim().is_empty())
            || profile.checks.keys().any(|id| gates.common_gates.contains_key(id))
        {
            return Err("business gate definitions are empty or unbounded".into());
        }
        if app.package == "org.mozilla.firefox"
            && (package.profile != "browser"
                || !BROWSER_GATES
                    .iter()
                    .all(|id| profile.checks.contains_key(*id)))
        {
            return Err(
                "Firefox browser profile does not contain the complete reviewed five-gate contract"
                    .into(),
            );
        }
        if let Some(input) = &app.expected_input {
            let mut names = BTreeSet::new();
            if input.version_code == 0 || input.apks.is_empty() || input.apks.len() > 64 {
                return Err("expected source APK set is invalid".into());
            }
            for apk in &input.apks {
                if !names.insert(apk.name.as_str())
                    || apk.bytes == 0
                    || apk.bytes > 1024 * 1024 * 1024
                    || !crate::release::valid_sha(&apk.sha256)
                {
                    return Err("expected source APK role/bytes/hash is invalid".into());
                }
            }
            if !names.contains("base.apk") {
                return Err("source input omits the normalized base APK".into());
            }
        }
    }
    if plan.execute_public_browser {
        let fixture = plan
            .browser_fixture
            .as_ref()
            .ok_or("browser execution needs a reviewed fixture")?;
        if fixture.input_scope != "public_owned_https"
            || !seen.contains(&"org.mozilla.firefox".to_string())
        {
            return Err("browser operation is outside the selected public-fixture scope".into());
        }
        validate_https_url(&fixture.url)?;
    }
    Ok(())
}

fn source_matches(actual: &ApplicationInspection, expected: &ExpectedInput) -> bool {
    let got: BTreeMap<_, _> = actual
        .apks
        .iter()
        .map(|a| (a.name.as_str(), (a.bytes, a.sha256.as_str())))
        .collect();
    let wanted: BTreeMap<_, _> = expected
        .apks
        .iter()
        .map(|a| (a.name.as_str(), (a.bytes, a.sha256.as_str())))
        .collect();
    actual.version_code == expected.version_code && actual.apks.len() == got.len() && got == wanted
}

fn dispatch(
    plan: &RuntimePlan,
    gates: &GateRegistry,
    client: &mut impl RuntimeClient,
) -> RuntimeReport {
    let mut applications = Vec::new();
    for app in &plan.applications {
        let package = &gates.packages[&app.package];
        let mut pending: Vec<_> = gates
            .common_gates
            .keys()
            .chain(gates.profiles[&package.profile].checks.keys())
            .cloned()
            .collect();
        pending.sort();
        let mut row = AppDispatch {
            package: app.package.clone(),
            application: package.app.clone(),
            profile: package.profile.clone(),
            status: "blocked",
            reason: String::new(),
            expected_input: app.expected_input.clone(),
            source_context: None,
            requested_launch: app.launch.clone(),
            requested_leaf: app.leaf.clone(),
            prerequisites: package.prerequisites.clone(),
            gate_assertions: pending_assertions(gates, &package.profile),
            inspection: None,
            invocation_output: None,
            firefox_activity_start: None,
            leaf_observation: None,
            launch_observation: None,
            pending_gates: pending,
            accepted_gates: 0,
            runtime_qualified: false,
            production_ready: false,
        };
        match client.inspect(&app.package, plan.android_user) {
            Err(error) => {
                row.reason = format!("runtime or installed-package precondition failed: {error}")
            }
            Ok(actual) => {
                if actual.package != app.package
                    || actual.user != plan.android_user
                    || actual.epoch != plan.expected_epoch
                {
                    row.reason = "current PM observation does not match the selected package/user and independently pinned live Main epoch".into();
                } else if let Some(reason) = &app.binding_failure {
                    row.reason = format!("read-only plan preparation remains blocked: {reason}; prepare a new pinned plan after resolution");
                } else if app.expected_input.is_none() {
                    row.reason = "current package observed, but reviewed current official source/split delivery is missing".into();
                } else if !source_matches(
                    &actual,
                    app.expected_input.as_ref().expect("checked above"),
                ) {
                    row.reason = "installed version or complete APK byte identities differ from the reviewed official input".into();
                } else if let Some(launch) = &app.launch {
                    let source = &app.expected_input.as_ref().expect("checked above").source_receipt;
                    match client.launch(&actual, launch, source) {
                        Ok((after, observation)) if after == actual => {
                            row.status = "launch_only_business_pending";
                            row.reason = "The current enabled launcher reached the original owned task-binding primitive with unchanged installed identity and Main epoch. Rendering, close/reopen, recovery and all business/common gates remain pending; a fresh task is not claimed.".into();
                            row.launch_observation = Some(observation);
                        }
                        Ok(_) => {
                            row.reason = "launch returned a different Main epoch or installed identity; no automatic retry".into();
                        }
                        Err(error) => {
                            row.reason = format!("launch-only observation failed; retain any actual task binding before an explicit retry: {error}");
                        }
                    }
                } else if let Some(leaf) = &app.leaf {
                    match client.leaf(
                        &actual,
                        leaf,
                        plan.preparation_selection
                            .as_ref()
                            .expect("validated selection"),
                    ) {
                        Ok((after, result)) if after == actual => {
                            row.status = "partial_leaf_observation";
                            row.reason = "The selected original leaf actually completed with its saved result and retired host owner. Its scoped result does not complete all common or application release gates.".into();
                            for assertion in &mut row.gate_assertions {
                                if result.verified_business_gates().contains(&assertion.id.as_str())
                                    && assertion.scope == "business"
                                {
                                    assertion.status = "passed";
                                    assertion.reason = "Verified by the original finite leaf's saved result, cleanup and unchanged installed identity/Main epoch".into();
                                    assertion.evidence = Some(result.result.clone());
                                }
                            }
                            row.leaf_observation = Some(result);
                        }
                        Ok(_) => {
                            row.reason =
                                "leaf returned a different Main epoch or installed identity".into()
                        }
                        Err(error) => {
                            row.reason = format!(
                                "selected leaf precondition or execution failed; retain its original claim and logs, with no automatic replay: {error}"
                            )
                        }
                    }
                } else if app.package != "org.mozilla.firefox" {
                    row.status = "unsupported";
                    row.reason = "identity observed; this entry has no executable whole-business flow for this registered profile; use its separately qualified existing leaf or implement the missing flow".into();
                } else if !plan.execute_public_browser {
                    row.reason = "browser identity observed; explicit reviewed public-fixture execution was not requested".into();
                } else {
                    let url = &plan
                        .browser_fixture
                        .as_ref()
                        .expect("validated fixture")
                        .url;
                    match client.browser(&actual, url) {
                        Err(error) => row.reason = format!("browser flow invocation failed; inspect retained observations before any explicit retry: {error}"),
                        Ok((after, output)) if after == actual => {
                            match firefox_activity_start(&output) {
                                Ok(observation) => {
                                    row.status = "partial_observation";
                                    row.reason = "Implicit HTTPS Activity invocation observed. Gecko isolated tab process, rendered page, media, return/reopen, recovery and common release gates remain pending.".into();
                                    row.firefox_activity_start = observation;
                                }
                                Err(error) => row.reason = format!("invalid browser activity observation: {error}"),
                            }
                            row.invocation_output = Some(output);
                        }
                        Ok(_) => row.reason = "browser invocation returned a different installed identity or Main generation".into(),
                    }
                }
                row.inspection = Some(actual);
            }
        }
        for assertion in &mut row.gate_assertions {
            if assertion.status == "passed" { continue; }
            if row.status == "blocked" {
                assertion.status = "blocked";
                assertion.reason = row.reason.clone();
            } else if assertion.scope == "business"
                && matches!(row.status, "unsupported" | "launch_only_business_pending")
            {
                assertion.status = "unsupported";
                assertion.reason = "This plan has no executable assertion for this business gate; an observed launcher task cannot satisfy it".into();
            }
        }
        row.pending_gates = row.gate_assertions.iter()
            .filter(|gate| gate.status != "passed").map(|gate| gate.id.clone()).collect();
        row.pending_gates.sort();
        row.accepted_gates = row.gate_assertions.iter().filter(|gate| gate.status == "passed").count();
        applications.push(row);
    }
    RuntimeReport {
        schema: 1,
        runtime_plan: None,
        source_selection: plan.source_selection.clone(),
        main_qualification: plan.main_qualification.clone(),
        expected_epoch: plan.expected_epoch.clone(),
        gate_registry: plan.gate_registry.clone(),
        selected_applications: applications.len(),
        blocked_applications: applications
            .iter()
            .filter(|r| r.status == "blocked")
            .count(),
        unsupported_business_flows: applications
            .iter()
            .filter(|r| matches!(r.status, "unsupported" | "launch_only_business_pending"))
            .count(),
        partial_browser_invocations: applications
            .iter()
            .filter(|r| r.status == "partial_observation")
            .count(),
        partial_leaf_invocations: applications
            .iter()
            .filter(|r| r.status == "partial_leaf_observation")
            .count(),
        launch_only_invocations: applications
            .iter()
            .filter(|r| r.status == "launch_only_business_pending")
            .count(),
        accepted_applications: applications.iter().filter(|row| {
            row.status != "blocked" && !row.gate_assertions.is_empty()
                && row.gate_assertions.iter().all(|gate| gate.status == "passed")
        }).count(),
        runtime_qualified: false,
        production_ready: false,
        automatic_retry: false,
        main_qualification_semantics_checked: false,
        meaning: "Live Package Manager/APK observations and actual bounded entry results. Only business assertions explicitly verified by the original leaf carry scoped evidence; untested common/business gates remain incomplete. Neither Main qualification nor whole-application production readiness is granted.",
        applications,
    }
}

/// Query one actual installed identity, with daemon-enforced current-runtime admission.
pub fn inspect_package(
    socket: &Path,
    package: &str,
    user: u32,
) -> Result<ApplicationInspection, String> {
    SocketClient { socket }.inspect(package, user)
}

/// Preserve the actual daemon's readonly whole-image/query provenance when
/// present. The original installed identity is unchanged. A legacy or missing
/// Gallery custody result cannot stand in for the current image-installed path.
pub fn inspect_package_with_custody(
    socket: &Path,
    package: &str,
    user: u32,
) -> Result<(ApplicationInspection, Option<ImageApplicationCustody>), String> {
    let reply = control::request(
        socket,
        &ControlRequest::InspectApplication { package: package.into(), user },
    ).map_err(|error| error.to_string())?;
    consume_inspection(reply, package, user)
}

fn consume_inspection(
    reply: control::ControlResponse,
    package: &str,
    user: u32,
) -> Result<(ApplicationInspection, Option<ImageApplicationCustody>), String> {
    if !reply.ok { return Err(reply.message); }
    let application = reply.inspection
        .ok_or("Daemon returned no current package inspection; update both tools")?;
    if application.package != package || application.user != user {
        return Err("Daemon returned a different installed package or Android user".into());
    }
    if package == "com.android.gallery3d" && user == 0 && reply.image_custody.is_none() {
        return Err("Gallery requires the actual owned whole-image inspection; an APK-only or historical install result is insufficient".into());
    }
    if let Some(custody) = &reply.image_custody {
        if reply.state != control::CellState::Running
            || reply.host_pid != Some(application.epoch.cell_host_pid)
        {
            return Err("Image custody does not belong to the current running daemon owner".into());
        }
        custody.validate(&application)?;
    }
    Ok((application, reply.image_custody))
}

#[cfg(test)]
mod image_custody_consumer_tests {
    use super::*;

    fn reply(package: &str) -> control::ControlResponse {
        control::ControlResponse {
            ok: true, state: control::CellState::Running, message: "unit metadata model".into(),
            host_pid: Some(321), launch: None, applications: None, application_icon: None,
            diagnostics: None, image_custody: None, runtime_vintf: None,
            inspection: Some(ApplicationInspection {
                package: package.into(), user: 0, uid: 10064, version_code: 40030,
                epoch: RuntimeEpoch {
                    boot_id: "00000000-0000-0000-0000-000000000001".into(),
                    cell_host_pid: 321, framework_host_pid: 322, framework_start_ticks: 101,
                },
                apks: Vec::new(),
            }),
        }
    }

    #[test]
    fn gallery_legacy_metadata_cannot_substitute_for_the_owned_image_producer() {
        assert!(consume_inspection(reply("com.android.gallery3d"), "com.android.gallery3d", 0).is_err());
    }

    #[test]
    fn unchanged_non_gallery_identity_shape_remains_available() {
        let response = reply("org.mozilla.firefox");
        let expected = response.inspection.clone().unwrap();
        let (application, custody) = consume_inspection(response, "org.mozilla.firefox", 0).unwrap();
        assert_eq!(application, expected);
        assert!(custody.is_none());
    }

    #[test]
    fn consumer_rejects_a_different_actual_package_or_user() {
        assert!(consume_inspection(reply("org.mozilla.firefox"), "com.android.gallery3d", 0).is_err());
        assert!(consume_inspection(reply("org.mozilla.firefox"), "org.mozilla.firefox", 1).is_err());
    }
}

/// Execute the selected plan without omitting unsupported or blocked applications.
pub fn run_files(
    socket: &Path,
    path: &Path,
    expected_sha256: &str,
    expected_count: usize,
) -> Result<RuntimeReport, String> {
    let raw = crate::release::read_frozen(path, INPUT_LIMIT).map_err(|e| e.to_string())?;
    if !crate::release::valid_sha(expected_sha256)
        || hex::encode(Sha256::digest(&raw)) != expected_sha256
    {
        return Err("externally pinned runtime plan SHA-256 differs".into());
    }
    let plan: RuntimePlan = serde_json::from_slice(&raw).map_err(|e| e.to_string())?;
    let gates: GateRegistry =
        serde_json::from_slice(&pinned(&plan.gate_registry)?).map_err(|e| e.to_string())?;
    validate(&plan, &gates, expected_count)?;
    let mut source_annotations = runtime_prepare::source_annotations(&plan)?;
    pinned(&plan.main_qualification)?;
    if let Some(selection) = &plan.preparation_selection {
        leaf_routes::validate_selection(selection)?;
    }
    for app in &plan.applications {
        if let Some(input) = &app.expected_input {
            pinned(&input.source_receipt)?;
        }
        if let Some(launch) = &app.launch {
            pinned(&launch.specification)?;
        }
    }
    let mut report = dispatch(&plan, &gates, &mut SocketClient { socket });
    for row in &mut report.applications {
        row.source_context = source_annotations.remove(&row.package);
    }
    report.runtime_plan = Some(FilePin { path: path.into(), bytes: raw.len() as u64,
        sha256: expected_sha256.into() });
    pinned(&plan.main_qualification)?;
    pinned(&plan.gate_registry)?;
    for app in &plan.applications {
        if let Some(input) = &app.expected_input {
            pinned(&input.source_receipt)?;
        }
        if let Some(launch) = &app.launch {
            pinned(&launch.specification)?;
        }
    }
    if let Some(selection) = &plan.preparation_selection {
        leaf_routes::validate_selection(selection)?;
    }
    if let Some(selection) = &plan.source_selection { pinned(selection)?; }
    if hex::encode(Sha256::digest(
        crate::release::read_frozen(path, INPUT_LIMIT).map_err(|e| e.to_string())?,
    )) != expected_sha256
    {
        return Err(
            "runtime plan changed during execution; no result can qualify the old selection".into(),
        );
    }
    Ok(report)
}

#[cfg(test)]
mod tests {
    use super::*;
    use droidloom_supervisor::control::application_probe::InstalledApk;
    struct Fake {
        identities: BTreeMap<String, ApplicationInspection>,
        opens: usize,
        browser_output: String,
        leaf_calls: usize,
        leaf_output: Option<LeafObservation>,
        launch_calls: usize,
    }
    impl RuntimeClient for Fake {
        fn launch(
            &mut self,
            expected: &ApplicationInspection,
            plan: &LaunchPlan,
            _: &FilePin,
        ) -> Result<(ApplicationInspection, LaunchObservation), String> {
            self.launch_calls += 1;
            Ok((
                expected.clone(),
                launch_route::test_observation(&plan.component, expected),
            ))
        }
        fn inspect(&mut self, p: &str, _: u32) -> Result<ApplicationInspection, String> {
            self.identities
                .get(p)
                .cloned()
                .ok_or("not installed or boot unavailable".into())
        }
        fn browser(
            &mut self,
            x: &ApplicationInspection,
            _: &str,
        ) -> Result<(ApplicationInspection, String), String> {
            self.opens += 1;
            Ok((x.clone(), self.browser_output.clone()))
        }
        fn leaf(
            &mut self,
            expected: &ApplicationInspection,
            _: &LeafPlan,
            _: &FilePin,
        ) -> Result<(ApplicationInspection, LeafObservation), String> {
            self.leaf_calls += 1;
            self.leaf_output.take().map(|observation| (expected.clone(), observation))
                .ok_or("fake fixture does not execute Android leaves".into())
        }
    }
    fn fixture() -> (RuntimePlan, GateRegistry, Fake) {
        let epoch = RuntimeEpoch {
            boot_id: "97d9600f-e081-465c-9e6e-62651e09806b".into(),
            cell_host_pid: 10,
            framework_host_pid: 20,
            framework_start_ticks: 30,
        };
        let pin = FilePin {
            path: "/fixture".into(),
            bytes: 1,
            sha256: "1".repeat(64),
        };
        let expected = ExpectedInput {
            version_code: 2,
            apks: vec![ApkInput {
                name: "base.apk".into(),
                bytes: 3,
                sha256: "a".repeat(64),
            }],
            source_receipt: pin.clone(),
        };
        let mut gates = GateRegistry {
            schema: "pocket4-app-release-gates-v1".into(),
            common_gates: crate::release::COMMON_GATES
                .iter()
                .map(|s| ((*s).into(), "fixture".into()))
                .collect(),
            profiles: BTreeMap::from([
                (
                    "browser".into(),
                    GateProfile {
                        checks: BROWSER_GATES
                            .iter()
                            .map(|s| ((*s).into(), "fixture".into()))
                            .collect(),
                    },
                ),
                (
                    "retail".into(),
                    GateProfile {
                        checks: BTreeMap::from([("retail.search".into(), "fixture".into())]),
                    },
                ),
            ]),
            packages: BTreeMap::new(),
        };
        let mut client = Fake {
            identities: BTreeMap::new(),
            opens: 0,
            browser_output: "Status: ok\nActivity: org.mozilla.firefox/.HomeActivity".into(),
            leaf_calls: 0,
            leaf_output: None,
            launch_calls: 0,
        };
        let mut applications = Vec::new();
        for n in 0..42 {
            let package = if n == 0 {
                "org.mozilla.firefox".into()
            } else {
                format!("org.example.app{n}")
            };
            gates.packages.insert(
                package.clone(),
                PackageProfile {
                    app: package.clone(),
                    kind: "third_party".into(),
                    profile: if n == 0 {
                        "browser".into()
                    } else {
                        "retail".into()
                    },
                    prerequisites: Vec::new(),
                },
            );
            client.identities.insert(
                package.clone(),
                ApplicationInspection {
                    package: package.clone(),
                    user: 0,
                    uid: 10000 + n,
                    version_code: 2,
                    epoch: epoch.clone(),
                    apks: vec![InstalledApk {
                        name: "base.apk".into(),
                        path: "/data/app/fixture/base.apk".into(),
                        bytes: 3,
                        sha256: "a".repeat(64),
                    }],
                },
            );
            applications.push(ApplicationPlan {
                package,
                expected_input: Some(expected.clone()),
                leaf: None,
                launch: None,
                binding_failure: None,
            });
        }
        (
            RuntimePlan {
                schema: 1,
                android_user: 0,
                main_qualification: pin.clone(),
                expected_epoch: epoch,
                gate_registry: pin,
                applications,
                execute_public_browser: true,
                preparation_selection: None,
                source_selection: None,
                browser_fixture: Some(BrowserFixture {
                    url: "https://example.com/".into(),
                    input_scope: "public_owned_https".into(),
                }),
            },
            gates,
            client,
        )
    }
    #[test]
    fn all_42_rows_survive_missing_runtime_without_any_invocation() {
        let (p, g, mut c) = fixture();
        c.identities.clear();
        validate(&p, &g, 42).unwrap();
        let r = dispatch(&p, &g, &mut c);
        assert_eq!(r.selected_applications, 42);
        assert_eq!(r.blocked_applications, 42);
        assert_eq!(c.opens, 0);
        assert_eq!(r.accepted_applications, 0);
    }
    #[test]
    fn one_real_entry_route_does_not_promote_41_unsupported_profiles() {
        let (p, g, mut c) = fixture();
        validate(&p, &g, 42).unwrap();
        let r = dispatch(&p, &g, &mut c);
        assert_eq!(c.opens, 1);
        assert_eq!(r.partial_browser_invocations, 1);
        assert_eq!(r.unsupported_business_flows, 41);
        assert!(!r.production_ready && !r.runtime_qualified);
        assert_eq!(r.accepted_applications, 0);
        assert!(
            r.applications
                .iter()
                .all(|a| a.accepted_gates == 0 && !a.pending_gates.is_empty())
        );
    }
    #[test]
    fn activity_wait_result_reaches_only_the_partial_firefox_row() {
        let (p, g, mut client) = fixture();
        client.browser_output = "Status: ok\nLaunchState: COLD\nActivity: org.mozilla.firefox/.HomeActivity\nWaitTime: 17\nComplete".into();
        let report = dispatch(&p, &g, &mut client);
        let row = &report.applications[0];
        let observed = row.firefox_activity_start.as_ref().unwrap();
        assert_eq!(observed.wait_time_ms, 17);
        assert_eq!(observed.launch_state,
            firefox_wait_result::ActivityLaunchState::Cold);
        assert_eq!(report.partial_browser_invocations, 1);
        assert_eq!(report.unsupported_business_flows, 41);
        assert_eq!(row.accepted_gates, 0);
        assert!(row.pending_gates.iter().any(|g| g == "browser.return"));
        assert!(!row.runtime_qualified && !row.production_ready);
        assert!(report.applications[1..].iter().all(|r| r.firefox_activity_start.is_none()));

        client.browser_output.push_str("\nStatus: timeout");
        let rejected = dispatch(&p, &g, &mut client);
        assert_eq!(rejected.partial_browser_invocations, 0);
        let row = &rejected.applications[0];
        assert!(row.firefox_activity_start.is_none());
        assert_eq!(row.invocation_output.as_ref(), Some(&client.browser_output));
        assert_eq!(row.status, "blocked");
    }
    #[test]
    fn stale_main_or_changed_source_never_opens_browser() {
        let (p, g, mut c) = fixture();
        c.identities
            .get_mut("org.mozilla.firefox")
            .unwrap()
            .epoch
            .framework_start_ticks += 1;
        assert_eq!(dispatch(&p, &g, &mut c).blocked_applications, 1);
        assert_eq!(c.opens, 0);
        let (p, g, mut c) = fixture();
        c.identities.get_mut("org.mozilla.firefox").unwrap().apks[0].sha256 = "b".repeat(64);
        assert_eq!(dispatch(&p, &g, &mut c).blocked_applications, 1);
        assert_eq!(c.opens, 0);
    }
    #[test]
    fn missing_delivery_or_unrequested_execution_is_blocked() {
        let (mut p, g, mut c) = fixture();
        p.applications[0].expected_input = None;
        assert_eq!(dispatch(&p, &g, &mut c).blocked_applications, 1);
        assert_eq!(c.opens, 0);
        let (mut p, g, mut c) = fixture();
        p.execute_public_browser = false;
        assert_eq!(dispatch(&p, &g, &mut c).blocked_applications, 1);
        assert_eq!(c.opens, 0);
    }
    #[test]
    fn reduced_duplicate_selection_and_incomplete_firefox_contract_are_rejected() {
        let (mut p, mut g, _) = fixture();
        p.applications.truncate(13);
        assert!(validate(&p, &g, 42).is_err());
        let (mut p, _, _) = fixture();
        p.applications[1] = p.applications[0].clone();
        assert!(validate(&p, &g, 42).is_err());
        let (p, _, _) = fixture();
        g.profiles
            .get_mut("browser")
            .unwrap()
            .checks
            .remove("browser.media");
        assert!(validate(&p, &g, 42).is_err());
    }
    #[test]
    fn full_apk_set_and_dynamic_uid_are_preserved() {
        let (p, g, mut c) = fixture();
        c.identities.get_mut("org.mozilla.firefox").unwrap().uid = 10987;
        let r = dispatch(&p, &g, &mut c);
        assert_eq!(r.applications[0].inspection.as_ref().unwrap().uid, 10987);
        assert_eq!(c.opens, 1);
        let (p, g, mut c) = fixture();
        let mut split = c.identities["org.mozilla.firefox"].apks[0].clone();
        split.name = "split_extra.apk".into();
        c.identities
            .get_mut("org.mozilla.firefox")
            .unwrap()
            .apks
            .push(split);
        assert_eq!(dispatch(&p, &g, &mut c).blocked_applications, 1);
        assert_eq!(c.opens, 0);
    }
    #[test]
    fn finite_leaf_dispatch_reaches_executor_and_keeps_all_42_gate_rows() {
        let (mut p, mut g, mut c) = fixture();
        let old = p.applications[1].package.clone();
        let package = "com.android.contacts".to_string();
        let mut observed = c.identities.remove(&old).unwrap();
        observed.package = package.clone();
        c.identities.insert(package.clone(), observed);
        let profile = g.packages.remove(&old).unwrap();
        g.packages.insert(package.clone(), profile);
        p.applications[1].package = package;
        p.applications[1].leaf = Some(LeafPlan {
            route: leaf_routes::Route::ContactsSearch,
            request: p.main_qualification.clone(),
            output: None,
        });
        p.schema = 2;
        p.preparation_selection = Some(p.main_qualification.clone());
        validate(&p, &g, 42).unwrap();
        let report = dispatch(&p, &g, &mut c);
        assert_eq!(c.leaf_calls, 1);
        assert_eq!(report.selected_applications, 42);
        assert_eq!(report.blocked_applications, 1);
        assert_eq!(report.unsupported_business_flows, 40);
        assert_eq!(report.partial_leaf_invocations, 0);
        assert_eq!(report.accepted_applications, 0);
        assert!(
            report
                .applications
                .iter()
                .all(|x| x.accepted_gates == 0 && !x.pending_gates.is_empty())
        );
        p.schema = 1;
        assert!(validate(&p, &g, 42).is_err());
    }
    #[test]
    fn all_39_explicit_launch_routes_keep_business_and_common_gates_pending() {
        let (mut plan, gates, mut client) = fixture();
        plan.schema = 3;
        plan.execute_public_browser = false;
        plan.applications.truncate(39);
        for app in &mut plan.applications {
            app.launch = Some(LaunchPlan {
                specification: plan.main_qualification.clone(),
                component: format!("{}/.Main", app.package),
            });
        }
        validate(&plan, &gates, 39).unwrap();
        let report = dispatch(&plan, &gates, &mut client);
        assert_eq!(client.launch_calls, 39);
        assert_eq!(client.opens, 0);
        assert_eq!(report.selected_applications, 39);
        assert_eq!(report.launch_only_invocations, 39);
        assert_eq!(report.unsupported_business_flows, 39);
        assert_eq!(report.accepted_applications, 0);
        assert!(!report.production_ready && !report.runtime_qualified);
        assert!(report.applications.iter().all(|row| {
            row.status == "launch_only_business_pending"
                && row.accepted_gates == 0 && !row.pending_gates.is_empty()
                && row.launch_observation.as_ref().is_some_and(|observation| {
                    observation.business_pending && !observation.close_observed
                        && !observation.reopen_observed && !observation.fresh_task_proven
                })
        }));
        // Even a fully routed selection cannot silently shrink the release set.
        assert!(validate(&plan, &gates, 42).is_err());
    }

    #[test]
    fn launch_routes_require_explicit_schema_source_and_unambiguous_operation() {
        let (mut plan, gates, _) = fixture();
        plan.applications[0].launch = Some(LaunchPlan {
            specification: plan.main_qualification.clone(),
            component: "org.mozilla.firefox/.App".into(),
        });
        assert!(validate(&plan, &gates, 42).is_err());
        plan.schema = 3;
        assert!(validate(&plan, &gates, 42).is_err());
        plan.execute_public_browser = false;
        validate(&plan, &gates, 42).unwrap();
        plan.applications[0].expected_input = None;
        assert!(validate(&plan, &gates, 42).is_err());
    }

    #[test]
    fn preparation_failures_remain_explicit_and_cannot_reach_a_launch() {
        let (mut plan, gates, mut client) = fixture();
        plan.schema = 3;
        plan.execute_public_browser = false;
        plan.applications[1].binding_failure = Some("selected split does not match live PM bytes".into());
        validate(&plan, &gates, 42).unwrap();
        let report = dispatch(&plan, &gates, &mut client);
        let row = &report.applications[1];
        assert_eq!(row.status, "blocked");
        assert!(row.reason.contains("selected split does not match"));
        assert!(row.expected_input.is_some() && row.inspection.is_some());
        assert!(row.gate_assertions.iter().all(|gate| gate.status == "blocked" && gate.evidence.is_none()));
        assert_eq!(client.launch_calls, 0);
        plan.applications[1].launch = Some(LaunchPlan {
            specification: plan.main_qualification.clone(), component: "org.example.app1/.Main".into(),
        });
        assert!(validate(&plan, &gates, 42).is_err());
    }

    #[test]
    fn only_the_verified_settings_assertions_are_credited_and_the_app_remains_incomplete() {
        for unknown in [false, true] {
            let (mut plan, mut gates, mut client) = fixture();
            let old = plan.applications[1].package.clone();
            let package = "com.android.settings".to_string();
            let mut actual = client.identities.remove(&old).unwrap();
            actual.package = package.clone();
            client.identities.insert(package.clone(), actual);
            let mut profile = gates.packages.remove(&old).unwrap();
            profile.profile = "settings".into();
            gates.packages.insert(package.clone(), profile);
            gates.profiles.insert("settings".into(), GateProfile { checks: [
                "settings.pages", "settings.roundtrip", "settings.permissions",
            ].iter().map(|id| (id.to_string(), format!("Required {id}"))).collect() });
            let pin = plan.main_qualification.clone();
            plan.applications[1].package = package;
            plan.applications[1].leaf = Some(LeafPlan {
                route: leaf_routes::Route::SettingsSupportedPages, request: pin.clone(), output: None,
            });
            plan.schema = 3;
            plan.preparation_selection = Some(pin.clone());
            client.leaf_output = Some(LeafObservation {
                route: leaf_routes::Route::SettingsSupportedPages, request: pin.clone(), preparation: pin.clone(),
                entry_source: pin.clone(), result: pin.clone(), state: "SETTINGS_PAGES_ROUNDTRIP_VERIFIED_RESTORED".into(),
                original_entry_result_verified: true, original_business_success_reported: true,
                business_outcome_unknown: unknown, main_epoch_unchanged: true, owned_host_tree_retired: true,
                automatic_retry: false, whole_app_business_accepted: false, production_ready: false,
                remaining_scope: "unit transport model; permissions and common gates remain incomplete",
            });
            validate(&plan, &gates, 42).unwrap();
            let report = dispatch(&plan, &gates, &mut client);
            let row = &report.applications[1];
            assert_eq!(row.accepted_gates, if unknown { 0 } else { 2 });
            assert_eq!(row.pending_gates.len(), if unknown { 9 } else { 7 });
            for gate in &row.gate_assertions {
                if !unknown && ["settings.pages", "settings.roundtrip"].contains(&gate.id.as_str()) {
                    assert_eq!(gate.status, "passed");
                    assert_eq!(gate.evidence.as_ref(), Some(&pin));
                } else {
                    assert_ne!(gate.status, "passed");
                    assert!(gate.evidence.is_none());
                }
            }
            assert_eq!(report.accepted_applications, 0);
            assert!(!report.production_ready && !row.production_ready);
        }
    }

    #[test]
    fn source_or_epoch_mismatch_blocks_the_generic_launch_before_invocation() {
        for changed_epoch in [false, true] {
            let (mut plan, gates, mut client) = fixture();
            plan.schema = 3;
            plan.execute_public_browser = false;
            plan.applications[0].launch = Some(LaunchPlan {
                specification: plan.main_qualification.clone(),
                component: "org.mozilla.firefox/.App".into(),
            });
            let actual = client.identities.get_mut("org.mozilla.firefox").unwrap();
            if changed_epoch {
                actual.epoch.framework_start_ticks += 1;
            } else {
                actual.apks[0].sha256 = "b".repeat(64);
            }
            validate(&plan, &gates, 42).unwrap();
            let report = dispatch(&plan, &gates, &mut client);
            assert_eq!(client.launch_calls, 0);
            assert_eq!(report.launch_only_invocations, 0);
            assert_eq!(report.applications[0].status, "blocked");
        }
    }

}
