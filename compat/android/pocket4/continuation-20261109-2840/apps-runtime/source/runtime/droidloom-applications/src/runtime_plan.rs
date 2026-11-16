//! Executable per-application admission and explicit business-flow routing.
//!
//! This preserves every selected row. A real browser invocation remains partial
//! progress; unsupported profiles and pending gates never become acceptance.
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

use droidloom_supervisor::control::application_probe::{
    ApplicationInspection, RuntimeEpoch, validate_https_url,
};
use droidloom_supervisor::control::{self, ControlRequest};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

const INPUT_LIMIT: u64 = 8 * 1024 * 1024;
const BROWSER_GATES: [&str; 5] = [
    "browser.external_https",
    "browser.document",
    "browser.media",
    "browser.return",
    "browser.recovery",
];

#[derive(Clone, Debug, Deserialize, Serialize)]
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
struct AppDispatch {
    package: String,
    profile: String,
    status: &'static str,
    reason: String,
    inspection: Option<ApplicationInspection>,
    invocation_output: Option<String>,
    pending_gates: Vec<String>,
    accepted_gates: usize,
    runtime_qualified: bool,
    production_ready: bool,
}

/// Actual metadata observations and invoked partial flows, never a release approval.
#[derive(Debug, Serialize)]
pub struct RuntimeReport {
    schema: u32,
    selected_applications: usize,
    blocked_applications: usize,
    unsupported_business_flows: usize,
    partial_browser_invocations: usize,
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
}

struct SocketClient<'a> {
    socket: &'a Path,
}

impl RuntimeClient for SocketClient<'_> {
    fn inspect(&mut self, package: &str, user: u32) -> Result<ApplicationInspection, String> {
        let reply = control::request(
            self.socket,
            &ControlRequest::InspectApplication {
                package: package.into(),
                user,
            },
        )
        .map_err(|e| e.to_string())?;
        if !reply.ok {
            return Err(reply.message);
        }
        reply
            .inspection
            .ok_or("Daemon returned no current package inspection; update both tools".into())
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
    if plan.schema != 1
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
    let mut seen = BTreeSet::new();
    for app in &plan.applications {
        if !seen.insert(&app.package) {
            return Err("runtime selection repeats a package".into());
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
            profile: package.profile.clone(),
            status: "blocked",
            reason: String::new(),
            inspection: None,
            invocation_output: None,
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
                } else if app.expected_input.is_none() {
                    row.reason = "current package observed, but reviewed current official source/split delivery is missing".into();
                } else if !source_matches(
                    &actual,
                    app.expected_input.as_ref().expect("checked above"),
                ) {
                    row.reason = "installed version or complete APK byte identities differ from the reviewed official input".into();
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
                            row.status = "partial_observation";
                            row.reason = "actual implicit HTTPS activity invocation observed; rendered document/input/image, media, return/reopen, recovery and all common release gates remain pending".into();
                            row.invocation_output = Some(output);
                        }
                        Ok(_) => row.reason = "browser invocation returned a different installed identity or Main generation".into(),
                    }
                }
                row.inspection = Some(actual);
            }
        }
        applications.push(row);
    }
    RuntimeReport {
        schema: 1,
        selected_applications: applications.len(),
        blocked_applications: applications
            .iter()
            .filter(|r| r.status == "blocked")
            .count(),
        unsupported_business_flows: applications
            .iter()
            .filter(|r| r.status == "unsupported")
            .count(),
        partial_browser_invocations: applications
            .iter()
            .filter(|r| r.status == "partial_observation")
            .count(),
        accepted_applications: 0,
        runtime_qualified: false,
        production_ready: false,
        automatic_retry: false,
        main_qualification_semantics_checked: false,
        meaning: "Live Package Manager/APK observations and actual bounded entry invocation only. All required gates remain pending; neither Main qualification nor whole-application production readiness is granted.",
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
    pinned(&plan.main_qualification)?;
    for app in &plan.applications {
        if let Some(input) = &app.expected_input {
            pinned(&input.source_receipt)?;
        }
    }
    Ok(dispatch(&plan, &gates, &mut SocketClient { socket }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use droidloom_supervisor::control::application_probe::InstalledApk;
    struct Fake {
        identities: BTreeMap<String, ApplicationInspection>,
        opens: usize,
    }
    impl RuntimeClient for Fake {
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
            Ok((
                x.clone(),
                "Status: ok\nActivity: org.mozilla.firefox/.HomeActivity".into(),
            ))
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
}
