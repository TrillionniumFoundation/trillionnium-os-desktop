//! One source-owned, same-boot physical application qualification run.
//!
//! Saved plans/results select inputs and permit comparisons; they never mint
//! completed gates. Only the existing live factories below can create the
//! move-only case histories retained by CompletePhysicalApplicationRun.
use super::clock_timer::{self, ClockResultCustody};
use super::common_gate::{self, CommonGateFact};
use super::family_observation::{self, FamilyObservation};
use super::leaf_release::{self, NativeRelease};
use super::leaf_routes::{self, LeafPlan, Route};
use super::native_business::{self, NativeBusinessFact, NativeCaseEvidence};
use super::native_camera_photo::{self, CameraPhotoBusinessFact};
use super::native_settings_permissions::{self, SettingsPermissionsBusinessFact};
use super::physical_gate_roster as roster;
use super::runtime_identity::{IdentityObservation, VerifiedMaterialBatch};
use super::*;
use droidloom_supervisor::control::physical_qualification_channel::{
    self as owned_channel, ChildChannel, QualificationCase,
};
use droidloom_supervisor::main_custody::RuntimeMainCustody;
use serde_json::Value;
#[path = "physical_release_scope.rs"]
mod release_scope;
use release_scope::{ReleaseScopeFact, ReleaseScopeReview, ScopeEvidence};

const SCHEMA: &str = "droidloom.physical-application-plan.v1";
const REPORT_SCHEMA: &str = "droidloom.physical-application-run.v1";
const SOURCE_AND_CAPTURE_SECONDS: u64 = owned_channel::budget::SOURCE_AND_CAPTURE_SECONDS;
const MAIN_SECONDS: u64 = owned_channel::budget::MAIN_SECONDS;
const INSPECT_SECONDS: u64 = owned_channel::budget::INSPECT_SECONDS;

/// Comparison document only. Each package occurs once; its exact executable
/// case order comes from the compiled roster, including empty unsupported rows.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PhysicalPlan {
    schema: String,
    runtime_plan: FilePin,
    applications: Vec<PhysicalApplicationPlan>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PhysicalApplicationPlan {
    package: String,
    cases: Vec<PhysicalCasePlan>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PhysicalCasePlan {
    leaf: LeafPlan,
    main_qualification: FilePin,
}

fn require(value: bool, reason: &str) -> Result<(), String> {
    if value { Ok(()) } else { Err(reason.into()) }
}
fn deadline(end: Instant) -> Result<(), String> {
    require(
        Instant::now() < end,
        "physical qualification's original absolute deadline expired",
    )
}

/// The native fourteen keep their original work/retirement bounds. The fixed
/// thirty-three family observations each add their reviewed UI/stability window
/// to the existing pre-inspection. All cases share one original suite end;
/// the extra single-shutter/reopen Camera case appends its own original window.
/// No case lease is renewed by this source-owned sum.
pub fn physical_qualification_window_seconds() -> u64 {
    owned_channel::SUITE_SECONDS
}
fn actual_source_window_seconds() -> u64 {
    SOURCE_AND_CAPTURE_SECONDS
        + 2 * MAIN_SECONDS
        + roster::PACKAGES
            .iter()
            .map(|row| {
                if row.cases.is_empty() {
                    family_window_seconds(row.package)
                } else {
                    row.cases.iter().copied().map(case_window_seconds).sum()
                }
            })
            .sum::<u64>()
        + camera_photo_window_seconds()
        + settings_permission_window_seconds()
}
fn family_window_seconds(package: &str) -> u64 {
    INSPECT_SECONDS + family_observation::window_seconds_for(package)
}
fn family_work_end(package: &str, now: Instant, case_end: Instant) -> Result<Instant, String> {
    require(now < case_end, "family pre-inspection consumed its original case deadline")?;
    Ok(now.checked_add(Duration::from_secs(family_observation::window_seconds_for(package)))
        .ok_or("family work deadline overflow")?.min(case_end))
}
fn camera_photo_window_seconds() -> u64 {
    INSPECT_SECONDS + native_camera_photo::window_seconds()
}
fn camera_photo_work_end(now: Instant, case_end: Instant) -> Result<Instant, String> {
    require(now < case_end, "Camera photo pre-inspection consumed its original case deadline")?;
    Ok(now.checked_add(Duration::from_secs(native_camera_photo::window_seconds()))
        .ok_or("Camera photo work deadline overflow")?.min(case_end))
}
fn settings_permission_window_seconds() -> u64 {
    INSPECT_SECONDS + native_settings_permissions::window_seconds()
}
fn settings_permission_work_end(now: Instant, case_end: Instant) -> Result<Instant, String> {
    require(now < case_end, "Settings interface pre-inspection consumed its original case deadline")?;
    Ok(now.checked_add(Duration::from_secs(native_settings_permissions::window_seconds()))
        .ok_or("Settings interface work deadline overflow")?.min(case_end))
}
fn case_window_seconds(route: Route) -> u64 {
    if route == Route::ClockTimerPair {
        clock_timer::pair_window_seconds()
    } else {
        route.inspection_seconds() + leaf_routes::original_window_seconds(route)
    }
}

/// This bridge is compiled from the actual case roster, never selected by an external ordinal.
fn qualification_case(route: Route) -> Result<QualificationCase, String> {
    Ok(match route {
        Route::CalendarCore => QualificationCase::CalendarCore,
        Route::CalendarReminder => QualificationCase::CalendarReminder,
        Route::CameraPhoto => QualificationCase::CameraPhoto,
        Route::ContactsSearch => QualificationCase::ContactsSearch,
        Route::ClockTimerPair => QualificationCase::ClockTimerPair,
        Route::ClockAlarm => QualificationCase::ClockAlarm,
        Route::DocumentsSaf => QualificationCase::DocumentsSaf,
        Route::DocumentsSearchSort => QualificationCase::DocumentsSearchSort,
        Route::GalleryRotation => QualificationCase::GalleryRotation,
        Route::GalleryVideo => QualificationCase::GalleryVideo,
        Route::GallerySeek => QualificationCase::GallerySeek,
        Route::GalleryAlbum => QualificationCase::GalleryAlbum,
        Route::SettingsSupportedPages => QualificationCase::SettingsSupportedPages,
        Route::IhgLondon => QualificationCase::IhgLondon,
        _ => {
            return Err(
                "physical channel has no source-owned case for this legacy single route".into(),
            );
        }
    })
}

fn require_channel_roster() -> Result<(), String> {
    require(
        actual_source_window_seconds() == owned_channel::SUITE_SECONDS
            && family_observation::window_seconds() == owned_channel::budget::FAMILY_WORK_SECONDS
            && native_camera_photo::window_seconds() == owned_channel::budget::CAMERA_PHOTO_WORK_SECONDS
            && native_settings_permissions::window_seconds() == owned_channel::budget::SETTINGS_PERMISSION_WORK_SECONDS,
        "physical producer and normal parent suite bounds differ",
    )?;
    let mut ordinal = 0usize;
    for row in roster::PACKAGES {
        for route in row.cases {
            let case = qualification_case(*route)?;
            require(
                case as usize == ordinal && case.window_seconds() == case_window_seconds(*route),
                "physical producer case order or original bound differs from its normal parent",
            )?;
            ordinal += 1;
        }
    }
    // Preserve all original native ordinals before appending the fixed family
    // sequence. An external plan cannot move a family ahead of those cases.
    for row in roster::PACKAGES.iter().filter(|row| row.cases.is_empty()) {
        let case = QualificationCase::for_family(row.package).map_err(|e| e.to_string())?;
        require(
            case as usize == ordinal && case.window_seconds() == family_window_seconds(row.package),
            "physical family order or original bound differs from its normal parent",
        )?;
        ordinal += 1;
    }
    let photo = QualificationCase::CameraPhotoCaptureReopen;
    require(
        photo as usize == ordinal && photo.window_seconds() == camera_photo_window_seconds()
            && owned_channel::PHOTO_CASE_COUNT == 1,
        "physical Camera photo append order or original bound differs from its normal parent",
    )?;
    ordinal += 1;
    let settings = QualificationCase::SettingsPermissionInterfaces;
    require(
        settings as usize == ordinal
            && settings.window_seconds() == settings_permission_window_seconds()
            && owned_channel::SETTINGS_CASE_COUNT == 1,
        "physical Settings append order or original bound differs from its normal parent",
    )?;
    ordinal += 1;
    require(
        ordinal == owned_channel::CASE_COUNT,
        "physical parent case coverage differs",
    )
}

fn require_compiled_roster(
    plan: &PhysicalPlan,
    runtime: &RuntimePlan,
    registry: &GateRegistry,
) -> Result<(), String> {
    require(
        plan.schema == SCHEMA
            && plan.applications.len() == roster::PACKAGE_COUNT
            && runtime.applications.len() == roster::PACKAGE_COUNT
            && runtime.android_user == 0
            && runtime.schema == 3
            && !runtime.execute_public_browser,
        "complete physical qualification requires the fixed 41-package user-zero source roster",
    )?;
    require(
        runtime.gate_registry.bytes == roster::REGISTRY_BYTES
            && runtime.gate_registry.sha256 == roster::REGISTRY_SHA256
            && runtime.source_selection.as_ref().is_some_and(|pin| {
                pin.bytes == roster::CURRENT_SELECTION_BYTES
                    && pin.sha256 == roster::CURRENT_SELECTION_SHA256
            }),
        "physical qualification changed the reviewed complete registry or current material cohort",
    )?;
    let mut seen = BTreeSet::new();
    let runtime_rows: BTreeMap<_, _> = runtime
        .applications
        .iter()
        .map(|row| (row.package.as_str(), row))
        .collect();
    require(
        runtime_rows.len() == roster::PACKAGE_COUNT,
        "physical runtime plan repeats a package",
    )?;
    let mut gate_count = 0;
    for (row, fixed) in plan.applications.iter().zip(roster::PACKAGES) {
        require(
            row.package == fixed.package
                && seen.insert(row.package.as_str())
                && row.cases.len() == fixed.cases.len()
                && row.cases.iter().zip(fixed.cases).all(|(case, route)| {
                    case.leaf.route == *route && route.package() == fixed.package
                }),
            "physical case package/order differs, is repeated, or omits a source-owned case",
        )?;
        let requested = runtime_rows
            .get(fixed.package)
            .ok_or("physical package is absent from the source-admitted runtime plan")?;
        require(
            requested.expected_input.is_some() && requested.binding_failure.is_none(),
            "a complete physical row lacks a successful installed-source preparation binding",
        )?;
        let registered = registry
            .packages
            .get(fixed.package)
            .ok_or("physical package is absent from the reviewed gate registry")?;
        require(
            registered.profile == fixed.profile,
            "physical package changed its registered business profile",
        )?;
        let common = registry
            .common_gates
            .keys()
            .map(String::as_str)
            .collect::<BTreeSet<_>>();
        let business = registry
            .profiles
            .get(fixed.profile)
            .ok_or("physical business profile missing")?
            .checks
            .keys()
            .map(String::as_str)
            .collect::<BTreeSet<_>>();
        require(
            common == roster::COMMON.into_iter().collect()
                && business == fixed.business.iter().copied().collect(),
            "physical registry substituted or omitted a complete named gate",
        )?;
        gate_count += common.len() + business.len();
    }
    require(
        gate_count == roster::GATE_COUNT,
        "complete physical roster does not contain exactly its reviewed 401 distinct per-App gates",
    )
}

// General case input custody uses the existing held-document mechanism, whose
// parent identities permit the case's legitimate new child directories. Source
// and owner inputs keep NativeRelease's stricter unchanged parent custody.
struct PlanInputs {
    documents: Vec<ClockResultCustody>,
}
impl PlanInputs {
    fn new() -> Self {
        Self {
            documents: Vec::new(),
        }
    }
    fn read(&mut self, pin: &FilePin) -> Result<Value, String> {
        if let Some(held) = self
            .documents
            .iter()
            .find(|held| held.reference().path == pin.path)
        {
            require(
                held.reference() == pin,
                "one physical input path has conflicting pins",
            )?;
            return held.read();
        }
        let (held, value) = ClockResultCustody::capture(pin)?;
        self.documents.push(held);
        Ok(value)
    }
    fn initial(&mut self, path: &Path, sha256: &str) -> Result<(FilePin, Value), String> {
        require(
            crate::release::valid_sha(sha256),
            "physical plan requires its complete external SHA",
        )?;
        let (held, value) = ClockResultCustody::capture_path(path)?;
        require(
            held.reference().sha256 == sha256,
            "physical plan differs from its explicit whole-file commitment",
        )?;
        let pin = held.reference().clone();
        self.documents.push(held);
        Ok((pin, value))
    }
    fn guard(&self) -> Result<(), String> {
        for held in &self.documents {
            held.guard()?;
        }
        Ok(())
    }
}

/// Public output comparison, never an input or a replacement for the opaque run.
#[derive(Debug, Serialize)]
pub struct PhysicalApplicationSummary {
    schema: &'static str,
    plan: FilePin,
    runtime_plan: FilePin,
    source_selection: FilePin,
    gate_registry: FilePin,
    native_preparation_selection: FilePin,
    epoch: RuntimeEpoch,
    original_window_seconds: u64,
    selected_applications: usize,
    required_gates: usize,
    observed_cases: usize,
    accepted_gates: usize,
    accepted_applications: usize,
    runtime_qualified: bool,
    production_ready: bool,
    automatic_retry: bool,
    retained_failure: Option<String>,
    applications: Vec<ApplicationSummary>,
}
impl PhysicalApplicationSummary {
    pub fn selected_applications(&self) -> usize {
        self.selected_applications
    }
    pub fn required_gates(&self) -> usize {
        self.required_gates
    }
    pub fn accepted_gates(&self) -> usize {
        self.accepted_gates
    }
    pub fn accepted_applications(&self) -> usize {
        self.accepted_applications
    }
}
#[derive(Debug, Serialize)]
struct ApplicationSummary {
    package: String,
    profile: &'static str,
    cases: Vec<Value>,
    gate_assertions: Vec<PhysicalGateSummary>,
    native_business_facts: Vec<Value>,
    release_scope_fact: Option<Value>,
    blocked_gates: Vec<Value>,
    blocked: Option<String>,
    accepted_gates: usize,
    runtime_qualified: bool,
    production_ready: bool,
}
#[derive(Debug, Serialize)]
struct PhysicalGateSummary {
    id: &'static str,
    status: &'static str,
    completed_cases: Vec<usize>,
    reason: &'static str,
}
#[derive(Debug, Serialize)]
struct CaseSummary {
    route: Route,
    actual: ApplicationInspection,
    evidence: Value,
    common: Vec<CommonGateFact>,
    business_gates: Vec<&'static str>,
    source_release: Value,
    sealed_inside_original_case_window: bool,
    historical_observation: bool,
    continuous_app_or_target_directory_custody_after_case_claimed: bool,
}

// Every variant is constructed by consuming a successful original execution
// object while its live source lease and original deadline still hold.
enum HistoricalCaseCustody {
    Leaf(leaf_routes::HistoricalLeafObservation),
    Clock(clock_timer::HistoricalClockTimerEvidence),
}
struct HistoricalCompletedCase {
    summary: CaseSummary,
    custody: HistoricalCaseCustody,
    // Minted from this live leaf's held result before its consuming history seal.
    // It remains paired with the source/result/Main/PM/Engine custody below.
    native: Option<NativeCaseEvidence>,
}
impl HistoricalCompletedCase {
    fn from_leaf(observation: leaf_routes::LeafObservation, end: Instant) -> Result<Self, String> {
        deadline(end)?;
        let native = native_business::from_leaf(&observation)?;
        let native_common = common_gate::from_native_case(
            &native,
            observation
                .main_observation()
                .ok_or("native common history lacks actual Main custody")?
                .facts(),
            observation.actual_application()?,
        )?;
        let (custody, mut common, business, evidence, actual, source_release) =
            observation.seal_history_before(end)?;
        for fact in native_common {
            require(
                !common.iter().any(|existing| existing.id() == fact.id()),
                "native common history repeats an independently supplied gate",
            )?;
            common.push(fact);
        }
        deadline(end)?;
        Ok(Self {
            summary: CaseSummary {
                route: custody.route(),
                actual,
                evidence,
                common,
                business_gates: business,
                source_release,
                sealed_inside_original_case_window: true,
                historical_observation: true,
                continuous_app_or_target_directory_custody_after_case_claimed: false,
            },
            custody: HistoricalCaseCustody::Leaf(custody),
            native: Some(native),
        })
    }
    fn from_clock(
        observation: clock_timer::ClockTimerEvidence,
        end: Instant,
    ) -> Result<Self, String> {
        let (custody, common, business, evidence, actual, source_release) =
            observation.seal_history_before(end)?;
        Ok(Self {
            summary: CaseSummary {
                route: Route::ClockTimerPair,
                actual,
                evidence,
                common,
                business_gates: business,
                source_release,
                sealed_inside_original_case_window: true,
                historical_observation: true,
                continuous_app_or_target_directory_custody_after_case_claimed: false,
            },
            custody: HistoricalCaseCustody::Clock(custody),
            native: None,
        })
    }
    fn binding(&self) -> &RuntimeMainCustody {
        match &self.custody {
            HistoricalCaseCustody::Leaf(value) => value.binding(),
            HistoricalCaseCustody::Clock(value) => value.binding(),
        }
    }
    fn guard(&self) -> Result<(), String> {
        match &self.custody {
            HistoricalCaseCustody::Leaf(value) => value.guard_immutable()?,
            HistoricalCaseCustody::Clock(value) => value.guard_immutable()?,
        }
        require(
            self.binding().epoch == self.summary.actual.epoch,
            "case history differs from its actual Main epoch",
        )?;
        for fact in &self.summary.common {
            fact.require_subject(&self.summary.actual.package, &self.summary.actual.epoch)?;
        }
        if let Some(native) = &self.native {
            native.require_subject(
                &self.summary.actual.package,
                self.binding(),
                &self.summary.actual,
            )?;
        }
        Ok(())
    }
}


#[derive(Debug, Serialize)]
struct FamilyCaseSummary {
    kind: &'static str,
    actual: ApplicationInspection,
    evidence: Value,
    material_identity: Value,
    common: Vec<CommonGateFact>,
    business_gates: Vec<&'static str>,
    sealed_inside_original_case_window: bool,
    historical_observation: bool,
    continuous_app_or_target_directory_custody_after_case_claimed: bool,
}

/// A successful normal close may leave explicit source-owned business blocks.
/// This type owns the actual evidence and pre-PM token; it is not constructed
/// from a report, a result flag, or an error interpreted as "safe".
struct HistoricalFamilyCase {
    summary: FamilyCaseSummary,
    custody: FamilyObservation,
    material_identity: IdentityObservation,
    before: control::ActualApplicationObservation,
}
impl HistoricalFamilyCase {
    fn from_observed(
        observation: FamilyObservation,
        mut identity: IdentityObservation,
        before: control::ActualApplicationObservation,
        main: &control::MainCustodyObservation,
        end: Instant,
    ) -> Result<Self, String> {
        deadline(end)?;
        let actual = before.facts();
        observation.require_subject(main.facts(), actual)?;
        identity.bind_stability_execution(actual, main, observation.stability())?;
        let common = common_gate::from_family(
            &observation, &identity, main.facts(), actual,
        )?;
        let fixed = roster::package(&actual.package)?;
        require(fixed.cases.is_empty(), "native package cannot acquire family history")?;
        let mut business = Vec::new();
        for fact in observation.business_facts() {
            fact.require_subject(main.facts(), actual)?;
            require(
                fixed.business.contains(&fact.id()) && !business.contains(&fact.id()),
                "family business history repeats or substitutes a source-owned gate",
            )?;
            business.push(fact.id());
        }
        let summary = FamilyCaseSummary {
            kind: "family_observation",
            actual: actual.clone(),
            evidence: observation.comparison()?,
            material_identity: serde_json::to_value(&identity).map_err(|e|e.to_string())?,
            common,
            business_gates: business,
            sealed_inside_original_case_window: true,
            historical_observation: true,
            continuous_app_or_target_directory_custody_after_case_claimed: false,
        };
        let history = Self { summary, custody:observation, material_identity:identity, before };
        history.guard()?;
        deadline(end)?;
        Ok(history)
    }
    fn binding(&self) -> &RuntimeMainCustody {
        &self.custody.stability().transcript().engine().facts().main
    }
    fn guard(&self) -> Result<(), String> {
        let actual = self.before.facts();
        require(
            actual == &self.summary.actual && roster::package(&actual.package)?.cases.is_empty(),
            "family history changed its actual package or complete installed identity",
        )?;
        // The family's immutable custody also owns its real before/open/close/after
        // PM samples and all four generated records. This remains a partial
        // preservation fact; no whole data_permissions gate is manufactured.
        self.custody.require_subject(self.binding(), actual)?;
        self.material_identity.require_application(actual)?;
        require(
            self.material_identity.complete_identity_gate_passed(),
            "family history lost its actual signed-material/Engine join",
        )?;
        for fact in &self.summary.common {
            fact.require_subject(&actual.package, &actual.epoch)?;
        }
        for fact in self.custody.business_facts() {
            fact.require_subject(self.binding(), actual)?;
        }
        Ok(())
    }
}


/// The supplementary photo owns both actual Finished journals, the original
/// complete PM token and its admitted material comparison. Finished is never
/// converted to Stability or another common/business gate.
#[derive(Debug, Serialize)]
struct CameraPhotoCaseSummary {
    kind: &'static str,
    actual: ApplicationInspection,
    evidence: Value,
    material_identity: Value,
    business_gates: [&'static str; 1],
    common_gates_supplied: bool,
    sealed_inside_original_case_window: bool,
    historical_observation: bool,
    continuous_app_or_target_directory_custody_after_case_claimed: bool,
}
struct HistoricalCameraPhotoCase {
    summary: CameraPhotoCaseSummary,
    fact: CameraPhotoBusinessFact,
    material_identity: IdentityObservation,
    before: control::ActualApplicationObservation,
}
impl HistoricalCameraPhotoCase {
    fn from_observed(
        fact: CameraPhotoBusinessFact,
        identity: IdentityObservation,
        before: control::ActualApplicationObservation,
        main: &control::MainCustodyObservation,
        end: Instant,
    ) -> Result<Self, String> {
        deadline(end)?;
        let actual = before.facts();
        require(
            actual.package == "com.android.camera2" && actual.user == 0
                && fact.gate() == "camera.photo"
                && roster::package(&actual.package)?.business.contains(&fact.gate()),
            "photo history has a different selected Camera or business assertion",
        )?;
        fact.require_subject(main.facts(), actual)?;
        identity.require_application(actual)?;
        for retained in [fact.observation().first(), fact.observation().reopened()] {
            let engine = retained.transcript().engine();
            require(
                engine.peer() == main.peer() && engine.application() == actual
                    && &engine.facts().main == main.facts(),
                "photo history changed its actual Main peer or complete installed identity",
            )?;
        }
        let summary = CameraPhotoCaseSummary {
            kind: "camera_photo_capture_reopen",
            actual: actual.clone(),
            evidence: fact.comparison()?,
            material_identity: serde_json::to_value(&identity).map_err(|e|e.to_string())?,
            business_gates: [fact.gate()],
            common_gates_supplied: false,
            sealed_inside_original_case_window: true,
            historical_observation: true,
            continuous_app_or_target_directory_custody_after_case_claimed: false,
        };
        let value = Self { summary, fact, material_identity: identity, before };
        value.guard()?;
        deadline(end)?;
        Ok(value)
    }
    fn binding(&self) -> &RuntimeMainCustody {
        &self.fact.observation().first().transcript().engine().facts().main
    }
    fn require_original_case(&self, histories: &[HistoricalCompletedCase]) -> Result<(), String> {
        require_camera_photo_predecessor(histories, self.before.facts(), self.binding())
    }
    fn guard(&self) -> Result<(), String> {
        let actual = self.before.facts();
        require(
            actual == &self.summary.actual && actual.package == "com.android.camera2"
                && actual.user == 0 && self.summary.business_gates == [self.fact.gate()]
                && self.fact.gate() == "camera.photo" && !self.summary.common_gates_supplied,
            "retained photo history changed its actual subject or exact business assertion",
        )?;
        self.fact.guard_immutable()?;
        self.fact.require_subject(self.binding(), actual)?;
        self.material_identity.require_application(actual)
    }
}

fn require_camera_photo_predecessor(
    histories: &[HistoricalCompletedCase],
    actual: &ApplicationInspection,
    main: &RuntimeMainCustody,
) -> Result<(), String> {
    let mut matching = histories.iter().filter(|case|
        case.summary.route == Route::CameraPhoto && case.summary.actual.package == "com.android.camera2");
    let original = matching.next().ok_or("supplementary photo lacks its original Camera case")?;
    require(matching.next().is_none(), "supplementary photo has ambiguous original Camera histories")?;
    original.guard()?;
    require_same_main(original.binding(), main)?;
    require(
        &original.summary.actual == actual,
        "Camera photo cannot join another UID/version/full APK identity to its original Camera case",
    )
}

// Only the completed fixed Settings factory can supply this historical gate.
#[derive(Debug, Serialize)]
struct SettingsPermissionCaseSummary {
    kind: &'static str,
    actual: ApplicationInspection,
    evidence: Value,
    material_identity: Value,
    business_gates: [&'static str; 1],
    common_gates_supplied: bool,
    sealed_inside_original_case_window: bool,
    historical_observation: bool,
    continuous_app_or_target_directory_custody_after_case_claimed: bool,
}
struct HistoricalSettingsPermissionCase {
    summary: SettingsPermissionCaseSummary,
    fact: SettingsPermissionsBusinessFact,
    material_identity: IdentityObservation,
    before: control::ActualApplicationObservation,
}
impl HistoricalSettingsPermissionCase {
    fn from_observed(
        fact: SettingsPermissionsBusinessFact,
        identity: IdentityObservation,
        before: control::ActualApplicationObservation,
        main: &control::MainCustodyObservation,
        end: Instant,
    ) -> Result<Self, String> {
        deadline(end)?;
        let actual = before.facts();
        require(
            actual.package == "com.android.settings" && actual.user == 0
                && fact.gate() == "settings.permissions"
                && roster::package(&actual.package)?.business.contains(&fact.gate()),
            "Settings interface history has a different selected Settings or business assertion",
        )?;
        fact.require_subject(main.facts(), actual)?;
        identity.require_application(actual)?;
        let engine = fact.observation().transcript().engine();
        require(
            engine.peer() == main.peer() && engine.application() == actual
                && &engine.facts().main == main.facts(),
            "Settings interface history changed its actual Main peer or complete installed identity",
        )?;
        let summary = SettingsPermissionCaseSummary {
            kind: "settings_permission_interfaces",
            actual: actual.clone(),
            evidence: fact.comparison()?,
            material_identity: serde_json::to_value(&identity).map_err(|e|e.to_string())?,
            business_gates: [fact.gate()],
            common_gates_supplied: false,
            sealed_inside_original_case_window: true,
            historical_observation: true,
            continuous_app_or_target_directory_custody_after_case_claimed: false,
        };
        let value = Self { summary, fact, material_identity: identity, before };
        value.guard()?;
        deadline(end)?;
        Ok(value)
    }
    fn binding(&self) -> &RuntimeMainCustody {
        &self.fact.observation().transcript().engine().facts().main
    }
    fn require_original_case(&self, histories: &[HistoricalCompletedCase]) -> Result<(), String> {
        require_settings_permission_predecessor(histories, self.before.facts(), self.binding())
    }
    fn guard(&self) -> Result<(), String> {
        let actual = self.before.facts();
        require(
            actual == &self.summary.actual && actual.package == "com.android.settings"
                && actual.user == 0 && self.summary.business_gates == [self.fact.gate()]
                && self.fact.gate() == "settings.permissions" && !self.summary.common_gates_supplied,
            "retained Settings interface history changed its actual subject or exact business assertion",
        )?;
        self.fact.guard_immutable()?;
        self.fact.require_subject(self.binding(), actual)?;
        self.material_identity.require_application(actual)
    }
}

fn require_settings_permission_predecessor(
    histories: &[HistoricalCompletedCase],
    actual: &ApplicationInspection,
    main: &RuntimeMainCustody,
) -> Result<(), String> {
    let mut matching = histories.iter().filter(|case|
        case.summary.route == Route::SettingsSupportedPages && case.summary.actual.package == "com.android.settings");
    let original = matching.next().ok_or("supplementary Settings interface lacks its original Settings case")?;
    require(matching.next().is_none(), "supplementary Settings interface has ambiguous original Settings histories")?;
    original.guard()?;
    require_same_main(original.binding(), main)?;
    require(
        &original.summary.actual == actual,
        "Settings permissions cannot join another UID/version/full APK identity to its original Settings case",
    )
}

fn require_main(binding: &RuntimeMainCustody, expected_epoch: &RuntimeEpoch) -> Result<(), String> {
    require(
        binding.epoch == *expected_epoch,
        "physical Main changed its fixed boot/framework epoch",
    )?;
    let data = &binding.persistent_data;
    let origin = data
        .original_copy_origin
        .as_ref()
        .ok_or("physical qualification requires the actual original-to-working-copy lineage")?;
    require(
        origin.working
            == [
                data.backings[0].backing.stable7(),
                data.backings[1].backing.stable7(),
            ],
        "physical Main no longer owns the admitted working data and metadata inodes",
    )
}
fn require_same_main(left: &RuntimeMainCustody, right: &RuntimeMainCustody) -> Result<(), String> {
    require(
        left == right,
        "physical cases cannot be joined across Main owner/epoch, selection/runtime, normal host release, source cohort or data lineage",
    )
}

// This index relation only locates the histories already owned by this process.
// It cannot create a business fact from route names, result JSON or a saved map.
fn native_basis_indices(
    package: &str,
    routes: &[Route],
    available: &[(usize, Route)],
) -> Result<Vec<usize>, String> {
    require(
        !routes.is_empty() && routes.len() <= available.len(),
        "native fact has an empty or oversized historical basis",
    )?;
    let mut indices = Vec::new();
    let mut seen = BTreeSet::new();
    for route in routes {
        require(route.package() == package, "native fact basis crossed a package")?;
        let matching = available
            .iter()
            .filter(|(_, present)| present == route)
            .map(|(index, _)| *index)
            .collect::<Vec<_>>();
        require(
            matching.len() == 1 && seen.insert(matching[0]),
            "native fact basis is missing, ambiguous or repeats a historical case",
        )?;
        indices.push(matching[0]);
    }
    Ok(indices)
}

struct HistoricalNativeBusinessFact {
    fact: NativeBusinessFact,
    case_indices: Vec<usize>,
}
impl HistoricalNativeBusinessFact {
    // All histories must have passed guard() before this immutable typed join.
    fn require_retained_binding(&self, histories: &[HistoricalCompletedCase]) -> Result<(), String> {
        let first = histories
            .get(*self.case_indices.first().ok_or("native fact lost its case basis")?)
            .ok_or("native fact basis is outside the retained histories")?;
        let actual = &first.summary.actual;
        let package = actual.package.as_str();
        self.fact.require_subject(package, first.binding(), actual)?;
        let available = histories
            .iter()
            .enumerate()
            .filter(|(_, case)| case.summary.actual.package == package && case.native.is_some())
            .map(|(index, case)| (index, case.summary.route))
            .collect::<Vec<_>>();
        let routes = self.fact.contributing_routes().collect::<Vec<_>>();
        require(
            native_basis_indices(package, &routes, &available)? == self.case_indices,
            "native fact no longer names exactly its contributing retained histories",
        )?;
        for index in &self.case_indices {
            let case = histories.get(*index).ok_or("native historical case disappeared")?;
            require_same_main(first.binding(), case.binding())?;
            require(case.summary.actual == *actual,
                "native historical cases differ in actual package, UID or complete APK identity")?;
            case.native.as_ref().ok_or("native historical case lost its typed evidence")?
                .require_subject(package, first.binding(), actual)?;
        }
        Ok(())
    }
}

fn join_native_histories(
    histories: &[HistoricalCompletedCase],
) -> Result<Vec<HistoricalNativeBusinessFact>, String> {
    // The factories retain source/result descriptors through this join and the
    // final Complete guard. No expired case lease is renewed or used for work.
    for history in histories {
        history.guard()?;
    }
    let mut joined = Vec::new();
    for fixed in roster::PACKAGES {
        let selected = histories
            .iter()
            .enumerate()
            .filter(|(_, case)| case.summary.actual.package == fixed.package && case.native.is_some())
            .collect::<Vec<_>>();
        if selected.is_empty() {
            continue;
        }
        let available = selected.iter()
            .map(|(index, case)| (*index, case.summary.route)).collect::<Vec<_>>();
        let cases = selected.iter()
            .map(|(_, case)| case.native.as_ref().expect("selected typed native case"))
            .collect::<Vec<_>>();
        let mut gate_ids = BTreeSet::new();
        for fact in native_business::join_cases(&cases)? {
            require(
                fixed.business.contains(&fact.gate()) && gate_ids.insert(fact.gate()),
                "native factory returned an unregistered or repeated complete assertion",
            )?;
            let routes = fact.contributing_routes().collect::<Vec<_>>();
            let case_indices = native_basis_indices(fixed.package, &routes, &available)?;
            let held = HistoricalNativeBusinessFact { fact, case_indices };
            held.require_retained_binding(histories)?;
            joined.push(held);
        }
    }
    Ok(joined)
}

struct RunCustody {
    inspector: control::NativeApplicationInspector,
    original_main: control::MainCustodyObservation,
    final_main: Option<control::MainCustodyObservation>,
    materials: VerifiedMaterialBatch,
    inputs: PlanInputs,
    source_owner: NativeRelease,
    histories: Vec<HistoricalCompletedCase>,
    family_histories: Vec<HistoricalFamilyCase>,
    photo_history: Option<HistoricalCameraPhotoCase>,
    settings_history: Option<HistoricalSettingsPermissionCase>,
    native_facts: Vec<HistoricalNativeBusinessFact>,
    release_review: ReleaseScopeReview,
    release_scopes: Vec<ReleaseScopeFact>,
    retained_errors: BTreeMap<String, String>,
    retained_failure: Option<String>,
    channel: ChildChannel,
    end: Instant,
}
impl RunCustody {
    fn scope_evidence(&self) -> ScopeEvidence<'_> {
        ScopeEvidence {
            original_main:&self.original_main, final_main:self.final_main.as_ref(),
            histories:&self.histories, native_facts:&self.native_facts,
            families:&self.family_histories, photo:self.photo_history.as_ref(),
            settings:self.settings_history.as_ref(), errors:&self.retained_errors,
            retained_failure:self.retained_failure.as_deref(),
        }
    }
    fn guard_immutable(&self) -> Result<(), String> {
        deadline(self.end)?;
        self.inspector
            .observation()
            .map_err(|error| error.to_string())?;
        self.materials.revalidate()?;
        self.inputs.guard()?;
        self.source_owner.guard()?;
        require_same_main(
            self.original_main.facts(),
            self.final_main
                .as_ref()
                .ok_or("physical run lacks its actual final Main observation")?
                .facts(),
        )?;
        for history in &self.histories {
            history.guard()?;
            require_same_main(history.binding(), self.original_main.facts())?;
        }
        for family in &self.family_histories {
            family.guard()?;
            require_same_main(family.binding(), self.original_main.facts())?;
        }
        if let Some(photo) = &self.photo_history {
            photo.guard()?;
            photo.require_original_case(&self.histories)?;
            require_same_main(photo.binding(), self.original_main.facts())?;
        }
        if let Some(settings) = &self.settings_history {
            settings.guard()?;
            settings.require_original_case(&self.histories)?;
            require_same_main(settings.binding(), self.original_main.facts())?;
        }
        for fact in &self.native_facts {
            fact.require_retained_binding(&self.histories)?;
        }
        self.release_review.guard(&self.inputs)?;
        require(self.release_scopes.len() == roster::PACKAGE_COUNT
            && self.release_scopes.iter().zip(roster::PACKAGES)
                .all(|(fact, fixed)| fact.package() == fixed.package)
            && self.retained_errors.is_empty() && self.retained_failure.is_none(),
            "complete run lost a source-owned whole-App release review or retained a failure")?;
        let evidence = self.scope_evidence();
        for fact in &self.release_scopes { fact.guard(&self.release_review, &evidence)?; }
        deadline(self.end)
    }
    fn refresh(&mut self) -> Result<(), String> {
        self.guard_immutable()?;
        self.final_main = Some(
            self.inspector
                .refresh_main_until(&self.original_main, self.end)
                .map_err(|error| error.to_string())?,
        );
        self.guard_immutable()
    }
}

/// The only whole-run authority value. There is deliberately no Deserialize,
/// Clone, public field, from-report, passed-map or caller-hash constructor.
pub struct CompletePhysicalApplicationRun {
    summary: PhysicalApplicationSummary,
    custody: RunCustody,
}
impl CompletePhysicalApplicationRun {
    pub fn binding(&self) -> &RuntimeMainCustody {
        self.custody
            .final_main
            .as_ref()
            .expect("Complete requires a real final Main")
            .facts()
    }
    pub fn summary(&self) -> &PhysicalApplicationSummary {
        &self.summary
    }
    /// Historical case evidence is checked immutably; only this still-owned
    /// suite's current Main is refreshed within the original suite deadline.
    pub fn guard(&mut self) -> Result<(), String> {
        self.custody.refresh()
    }
    /// Only this actual opaque Complete can publish the matching normal stdout
    /// and private frame. All source/results/Main facts stay held until ACK.
    pub fn write_owned_completion(&mut self) -> Result<(), String> {
        use std::io::Write;
        self.guard()?;
        let mut bytes = serde_json::to_vec_pretty(self.summary()).map_err(|e| e.to_string())?;
        bytes.push(b'\n');
        {
            let mut output = std::io::stdout().lock();
            output
                .write_all(&bytes)
                .and_then(|_| output.flush())
                .map_err(|e| e.to_string())?;
        }
        self.custody.guard_immutable()?;
        let binding = self
            .custody
            .final_main
            .as_ref()
            .ok_or("Complete lost its actual final Main")?
            .facts();
        self.custody
            .channel
            .complete(&bytes, binding, self.custody.end)
            .map_err(|e| e.to_string())?;
        self.custody.guard_immutable()
    }
}
struct PartialPhysicalApplicationRun {
    summary: PhysicalApplicationSummary,
    // Successful histories stay held through submission even when other
    // assertions are missing. They cannot be converted into a Complete value.
    _custody: RunCustody,
}
enum Outcome {
    Complete(CompletePhysicalApplicationRun),
    Partial(PartialPhysicalApplicationRun),
}
pub struct PhysicalRunOutcome {
    outcome: Outcome,
}
impl PhysicalRunOutcome {
    pub fn summary(&self) -> &PhysicalApplicationSummary {
        match &self.outcome {
            Outcome::Complete(value) => &value.summary,
            Outcome::Partial(value) => &value.summary,
        }
    }
    pub fn into_complete(self) -> Result<CompletePhysicalApplicationRun, Self> {
        match self.outcome {
            Outcome::Complete(value) => Ok(value),
            Outcome::Partial(value) => Err(Self {
                outcome: Outcome::Partial(value),
            }),
        }
    }
}

fn summarize_rows(
    histories: &[HistoricalCompletedCase],
    native_facts: &[HistoricalNativeBusinessFact],
    family_histories: &[HistoricalFamilyCase],
    photo_history: Option<&HistoricalCameraPhotoCase>,
    settings_history: Option<&HistoricalSettingsPermissionCase>,
    release_scopes: &[ReleaseScopeFact],
    errors: &BTreeMap<String, String>,
) -> Result<Vec<ApplicationSummary>, String> {
    if let Some(photo) = photo_history {
        photo.guard()?;
        photo.require_original_case(histories)?;
        require(
            histories.len() == owned_channel::NATIVE_CASE_COUNT
                && family_histories.len() == owned_channel::FAMILY_CASE_COUNT,
            "supplementary photo history lacks its complete original preceding cases",
        )?;
    }
    if let Some(settings) = settings_history {
        settings.guard()?;
        settings.require_original_case(histories)?;
        require(
            histories.len() == owned_channel::NATIVE_CASE_COUNT
                && family_histories.len() == owned_channel::FAMILY_CASE_COUNT
                && photo_history.is_some(),
            "Settings interface history lacks its complete original preceding cases",
        )?;
    }
    let mut rows = Vec::new();
    for fixed in roster::PACKAGES {
        let cases = histories
            .iter()
            .enumerate()
            .filter(|(_, case)| case.summary.actual.package == fixed.package)
            .collect::<Vec<_>>();
        let families = family_histories.iter().enumerate()
            .filter(|(_, history)| history.summary.actual.package == fixed.package)
            .collect::<Vec<_>>();
        require(
            families.len() <= usize::from(fixed.cases.is_empty()),
            "family history is duplicated or attached to a native package",
        )?;
        for (_, family) in &families { family.guard()?; }
        // IDs come only from consuming original factories and their retained
        // opaque objects. A serialized blocked row is never a passed map.
        let mut assertions = Vec::new();
        for id in roster::required(fixed) {
            let mut indices = cases
                .iter()
                .filter(|(_, case)| {
                    case.summary.common.iter().any(|fact| fact.id() == id)
                        || case.summary.business_gates.contains(&id)
                })
                .map(|(index, _)| *index)
                .collect::<Vec<_>>();
            for fact in native_facts.iter().filter(|fact| fact.fact.gate() == id) {
                fact.require_retained_binding(histories)?;
                if fact.case_indices.iter().all(|index| {
                    histories.get(*index)
                        .is_some_and(|case| case.summary.actual.package == fixed.package)
                }) {
                    indices.extend(fact.case_indices.iter().copied());
                }
            }
            for (index, family) in &families {
                if family.summary.common.iter().any(|fact| fact.id() == id)
                    || family.summary.business_gates.contains(&id)
                {
                    indices.push(histories.len() + *index);
                }
            }
            if let Some(photo) = photo_history.filter(|photo|
                photo.summary.actual.package == fixed.package && photo.fact.gate() == id)
            {
                photo.guard()?;
                indices.push(QualificationCase::CameraPhotoCaptureReopen as usize);
            }
            if let Some(settings) = settings_history.filter(|settings|
                settings.summary.actual.package == fixed.package && settings.fact.gate() == id)
            {
                settings.guard()?;
                indices.push(QualificationCase::SettingsPermissionInterfaces as usize);
            }
            if id == "release_scope" {
                require(indices.is_empty(),
                    "release_scope may only come from the retained whole-App release factory")?;
                let scopes = release_scopes.iter().filter(|fact| fact.package() == fixed.package)
                    .collect::<Vec<_>>();
                require(scopes.len() <= 1, "whole-App release scope is duplicated")?;
                if let Some(scope) = scopes.first() {
                    indices.extend(scope.completed_cases().iter().copied());
                }
            }
            indices.sort_unstable();
            indices.dedup();
            let passed = !indices.is_empty() && !errors.contains_key(fixed.package);
            assertions.push(PhysicalGateSummary {
                id,
                status: if passed { "passed" } else { "pending" },
                completed_cases: indices,
                reason: if passed {
                    "Proved by this run's actual source-owned case factory"
                } else {
                    "The complete named assertion has no successful normal factory in this run"
                },
            });
        }
        let expected = fixed.cases;
        require(
            cases.len() <= expected.len()
                && cases
                    .iter()
                    .zip(expected)
                    .all(|((_, case), route)| case.summary.route == *route),
            "historical execution repeated or reordered a source-owned package case",
        )?;
        let complete = cases.len() == expected.len()
            && families.len() == usize::from(expected.is_empty())
            && (fixed.package != "com.android.camera2" || photo_history.is_some())
            && (fixed.package != "com.android.settings" || settings_history.is_some())
            && !errors.contains_key(fixed.package)
            && assertions.iter().all(|gate| gate.status == "passed");
        rows.push(ApplicationSummary {
            package: fixed.package.into(),
            profile: fixed.profile,
            // The facts remain in custody. The public comparison below is
            // copied through serialization, never used to construct authority.
            cases: Vec::new(),
            gate_assertions: assertions,
            native_business_facts: native_facts.iter()
                .filter(|fact| fact.case_indices.first().is_some_and(|index| {
                    histories.get(*index)
                        .is_some_and(|case| case.summary.actual.package == fixed.package)
                }))
                .map(|fact| fact.fact.comparison())
                .chain(photo_history.filter(|photo| photo.summary.actual.package == fixed.package)
                    .map(|photo| photo.fact.comparison()))
                .chain(settings_history.filter(|settings| settings.summary.actual.package == fixed.package)
                    .map(|settings| settings.fact.comparison()))
                .collect::<Result<Vec<_>, _>>()?,
            release_scope_fact: release_scopes.iter()
                .find(|fact| fact.package() == fixed.package).map(|fact| fact.comparison()).transpose()?,
            blocked_gates: families.iter().flat_map(|(_, history)| history.custody.blocked())
                .map(|blocked| serde_json::to_value(blocked).map_err(|e|e.to_string()))
                .collect::<Result<Vec<_>,_>>()?,
            blocked: errors.get(fixed.package).cloned(),
            accepted_gates: 0,
            runtime_qualified: complete,
            production_ready: complete,
        });
    }
    for row in &mut rows {
        row.accepted_gates = row
            .gate_assertions
            .iter()
            .filter(|gate| gate.status == "passed")
            .count();
    }
    Ok(rows)
}

/// Execute the fixed complete roster using the canonical installed application
/// ELF and source-admitted material/peer factories. A partial report never
/// contains or reconstructs a CompletePhysicalApplicationRun.
/// Source-only validation of inputs produced by this actual private preparation.
/// This is not a runtime result or a constructor for Complete.
pub(super) fn validate_prepared_working_plan(
    value: &Value, runtime: &RuntimePlan, gates: &GateRegistry,
) -> Result<(), String> {
    let plan: PhysicalPlan=serde_json::from_value(value.clone()).map_err(|e|e.to_string())?;
    validate(runtime,gates,roster::PACKAGE_COUNT)?;
    require_compiled_roster(&plan,runtime,gates)?;
    require_channel_roster()
}

pub fn run_physical_files(
    path: &Path,
    expected_sha256: &str,
) -> Result<PhysicalRunOutcome, String> {
    let started = Instant::now();
    let seconds = physical_qualification_window_seconds();
    let end = started
        .checked_add(Duration::from_secs(seconds))
        .ok_or("suite deadline overflow")?;
    let mut inputs = PlanInputs::new();
    let (plan_pin, value) = inputs.initial(path, expected_sha256)?;
    let plan: PhysicalPlan = serde_json::from_value(value).map_err(|error| error.to_string())?;
    let mut runtime: RuntimePlan = serde_json::from_value(inputs.read(&plan.runtime_plan)?)
        .map_err(|error| error.to_string())?;
    let gates: GateRegistry = serde_json::from_value(inputs.read(&runtime.gate_registry)?)
        .map_err(|error| error.to_string())?;
    validate(&runtime, &gates, roster::PACKAGE_COUNT)?;
    require_compiled_roster(&plan, &runtime, &gates)?;
    require_channel_roster()?;
    let release_review = ReleaseScopeReview::capture(&gates, &runtime.gate_registry, &inputs)?;
    // Acquire the fixed parent's actual private channel before any PM/Main or leaf action.
    let mut channel = ChildChannel::acquire(
        &plan_pin.path,
        plan_pin.bytes,
        &plan_pin.sha256,
        &runtime.expected_epoch,
        end,
    )
    .map_err(|e| e.to_string())?;
    let end = channel.deadline();
    let selection = runtime
        .preparation_selection
        .clone()
        .ok_or("physical plan lacks the source-owned native preparation selection")?;
    leaf_routes::validate_selection(&selection)?;
    inputs.read(&selection)?;
    let source_selection = runtime
        .source_selection
        .clone()
        .ok_or("current material selection absent")?;
    inputs.read(&source_selection)?;
    for requested in &runtime.applications {
        inputs.read(
            &requested
                .expected_input
                .as_ref()
                .ok_or("complete row source absent")?
                .source_receipt,
        )?;
    }
    // Freeze all explicit requests before any case action. Their respective
    // original factories still validate every transitive source and input.
    for row in &plan.applications {
        for case in &row.cases {
            inputs.read(&case.leaf.request)?;
            inputs.read(&case.main_qualification)?;
        }
    }
    let materials = runtime_identity::admit_plan(&runtime)?.ok_or(
        "complete physical qualification requires the source-admitted current normal batch",
    )?;
    let source_owner = leaf_routes::qualification_release(&selection)?;
    source_owner.cover_window(
        end.checked_duration_since(Instant::now())
            .ok_or("physical source preflight consumed its original window")?
            .as_secs()
            .saturating_add(1),
    )?;
    let mut inspector =
        control::NativeApplicationInspector::acquire(Path::new(control::DEFAULT_CONTROL_SOCKET))
            .map_err(|error| error.to_string())?;
    let main = inspector
        .observe_main_until(&runtime.expected_epoch, end)
        .map_err(|error| error.to_string())?;
    require_main(main.facts(), &runtime.expected_epoch)?;
    source_owner.compare_working_main(&main)?;
    let mut histories = Vec::new();
    let mut family_histories = Vec::new();
    let mut photo_history = None;
    let mut settings_history = None;
    let mut errors = BTreeMap::new();
    let mut first_failure: Option<String> = None;
    // Preserve the original fourteen native cases, then append the fixed
    // thirty-three family observations. The input document still has each package
    // once in canonical order; it cannot choose a different execution order.
    for row in plan.applications.iter().filter(|row| !row.cases.is_empty())
        .chain(plan.applications.iter().filter(|row| row.cases.is_empty()))
    {
        if let Some(reason) = &first_failure {
            errors.insert(
                row.package.clone(),
                format!("not executed after an earlier retained failure: {reason}"),
            );
            continue;
        }
        let requested = runtime
            .applications
            .iter()
            .find(|app| app.package == row.package)
            .ok_or("physical row not in normal runtime selection")?
            .clone();
        if row.cases.is_empty() {
            let result = (|| -> Result<HistoricalFamilyCase, String> {
                deadline(end)?;
                let case_end = (Instant::now() + Duration::from_secs(family_window_seconds(&row.package))).min(end);
                let case_owner = channel.begin_case(
                    QualificationCase::for_family(&row.package).map_err(|e|e.to_string())?,
                    case_end,
                ).map_err(|e|e.to_string())?;
                let cutoff = (Instant::now() + Duration::from_secs(INSPECT_SECONDS)).min(case_end);
                let before = inspector.inspect_observed_until(&row.package, 0, cutoff)
                    .map_err(|error| error.to_string())?;
                let actual = before.facts();
                require(
                    actual.package == row.package && actual.user == 0
                        && actual.epoch == runtime.expected_epoch,
                    "family pre-inspection changed its fixed actual package/user/epoch",
                )?;
                let identity = materials.observe(
                    &requested, 0, &runtime.expected_epoch, actual, actual,
                )?;
                let work_end = family_work_end(&row.package, Instant::now(), case_end)?;
                let observation = {
                    let mut baseline =
                        droidloom_supervisor::native_leaf_baseline::NativeLeafBaselineObservation::capture_from_observed(
                            &inspector, &main, &before, work_end,
                        ).map_err(|e|e.to_string())?;
                    family_observation::run_family_case(&mut inspector, &mut baseline, work_end)?
                };
                let completed = HistoricalFamilyCase::from_observed(
                    observation, identity, before, &main, case_end,
                )?;
                completed.guard()?;
                require_same_main(completed.binding(), main.facts())?;
                inputs.guard()?;
                materials.revalidate()?;
                source_owner.guard()?;
                deadline(case_end)?;
                case_owner.finish_after_history(case_end).map_err(|e|e.to_string())?;
                Ok(completed)
            })();
            match result {
                // Only the actual successful close/window/history constructor
                // reaches here. Missing business assertions remain structured
                // blocks and permit the next independent source-owned case.
                Ok(history) => family_histories.push(history),
                Err(error) => {
                    errors.insert(row.package.clone(), error.clone());
                    first_failure = Some(error);
                }
            }
            continue;
        }
        for case in &row.cases {
            let result = (|| -> Result<HistoricalCompletedCase, String> {
                deadline(end)?;
                let case_end = (Instant::now()
                    + Duration::from_secs(case_window_seconds(case.leaf.route)))
                .min(end);
                let case_owner = channel
                    .begin_case(qualification_case(case.leaf.route)?, case_end)
                    .map_err(|e| e.to_string())?;
                let inspection_end =
                    (Instant::now() + Duration::from_secs(case.leaf.route.inspection_seconds())).min(case_end);
                let before = inspector
                    .inspect_observed_until(&row.package, 0, inspection_end)
                    .map_err(|error| error.to_string())?;
                let actual = before.facts().clone();
                require(
                    actual.epoch == runtime.expected_epoch
                        && actual.package == row.package
                        && actual.user == 0,
                    "physical pre-inspection changed package/user/Main epoch",
                )?;
                materials.observe(&requested, 0, &runtime.expected_epoch, &actual, &actual)?;
                runtime.main_qualification = case.main_qualification.clone();
                let completed = if case.leaf.route == Route::ClockTimerPair {
                    let (after, observation) = clock_timer::observe_pair_from_observed_until(
                        &mut inspector,
                        &materials,
                        &runtime,
                        &requested,
                        &actual,
                        &case.leaf,
                        &selection,
                        before,
                        case_end,
                    )?;
                    require(
                        after == actual,
                        "Clock completed with another installed application",
                    )?;
                    HistoricalCompletedCase::from_clock(observation, case_end)?
                } else {
                    let (after, observation) = leaf_routes::execute_admitted_until(
                        &mut inspector,
                        &materials,
                        &runtime,
                        &requested,
                        &case.leaf,
                        &selection,
                        before,
                        case_end,
                    )?;
                    require(
                        after == actual,
                        "leaf completed with another installed application",
                    )?;
                    HistoricalCompletedCase::from_leaf(observation, case_end)?
                };
                completed.guard()?;
                require_same_main(completed.binding(), main.facts())?;
                inputs.guard()?;
                materials.revalidate()?;
                source_owner.guard()?;
                deadline(case_end)?;
                // The original factory has consumed its live lease into immutable history;
                // the parent also checks the actual prior child cgroups are empty.
                case_owner
                    .finish_after_history(case_end)
                    .map_err(|e| e.to_string())?;
                Ok(completed)
            })();
            match result {
                Ok(history) => histories.push(history),
                Err(error) => {
                    errors.insert(row.package.clone(), error.clone());
                    first_failure = Some(error);
                    break;
                }
            }
        }
    }

    // This extra source-owned case is deliberately after all 14 native and 33 Family cases.
    // It is not selected by a caller route, nor substituted for the old Camera
    // leaf. The same suite end caps the pre-PM, actual work, retention and ACK.
    if let Some(reason) = &first_failure {
        errors.entry("com.android.camera2".into()).or_insert_with(||
            format!("photo capture/reopen not executed after an earlier retained failure: {reason}"));
    } else {
        let result = (|| -> Result<HistoricalCameraPhotoCase, String> {
            deadline(end)?;
            let case_end = (Instant::now()
                + Duration::from_secs(camera_photo_window_seconds())).min(end);
            let case_owner = channel.begin_case(
                QualificationCase::CameraPhotoCaptureReopen, case_end,
            ).map_err(|e|e.to_string())?;
            let requested = runtime.applications.iter()
                .find(|app| app.package == "com.android.camera2")
                .ok_or("source-admitted Camera photo row absent")?;
            let cutoff = (Instant::now() + Duration::from_secs(INSPECT_SECONDS)).min(case_end);
            let before = inspector.inspect_observed_until("com.android.camera2", 0, cutoff)
                .map_err(|error| error.to_string())?;
            let actual = before.facts();
            require(
                actual.package == "com.android.camera2" && actual.user == 0
                    && actual.epoch == runtime.expected_epoch,
                "photo pre-inspection changed actual Camera/user/Main epoch",
            )?;
            let identity = materials.observe(
                requested, 0, &runtime.expected_epoch, actual, actual,
            )?;
            require_camera_photo_predecessor(&histories, actual, main.facts())?;
            let work_end = camera_photo_work_end(Instant::now(), case_end)?;
            let fact = {
                let mut baseline =
                    droidloom_supervisor::native_leaf_baseline::NativeLeafBaselineObservation::capture_from_observed(
                        &inspector, &main, &before, work_end,
                    ).map_err(|e|e.to_string())?;
                native_camera_photo::run(&mut inspector, &mut baseline, work_end)?
            };
            let completed = HistoricalCameraPhotoCase::from_observed(
                fact, identity, before, &main, case_end,
            )?;
            completed.guard()?;
            require_same_main(completed.binding(), main.facts())?;
            inputs.guard()?;
            materials.revalidate()?;
            source_owner.guard()?;
            deadline(case_end)?;
            case_owner.finish_after_history(case_end).map_err(|e|e.to_string())?;
            Ok(completed)
        })();
        match result {
            Ok(history) => photo_history = Some(history),
            Err(error) => {
                errors.insert("com.android.camera2".into(), error.clone());
                first_failure = Some(error);
            }
        }
    }

    // This extra source-owned Settings case follows the complete original 46.
    // It is not selected by a caller route, nor substituted for the old Settings
    // leaf. The same suite end caps the pre-PM, actual work, retention and ACK.
    if let Some(reason) = &first_failure {
        errors.entry("com.android.settings".into()).or_insert_with(||
            format!("Settings permission interface not executed after an earlier retained failure: {reason}"));
    } else {
        let result = (|| -> Result<HistoricalSettingsPermissionCase, String> {
            deadline(end)?;
            let case_end = (Instant::now()
                + Duration::from_secs(settings_permission_window_seconds())).min(end);
            let case_owner = channel.begin_case(
                QualificationCase::SettingsPermissionInterfaces, case_end,
            ).map_err(|e|e.to_string())?;
            let requested = runtime.applications.iter()
                .find(|app| app.package == "com.android.settings")
                .ok_or("source-admitted Settings permission interface row absent")?;
            let cutoff = (Instant::now() + Duration::from_secs(INSPECT_SECONDS)).min(case_end);
            let before = inspector.inspect_observed_until("com.android.settings", 0, cutoff)
                .map_err(|error| error.to_string())?;
            let actual = before.facts();
            require(
                actual.package == "com.android.settings" && actual.user == 0
                    && actual.epoch == runtime.expected_epoch,
                "Settings pre-inspection changed actual Settings/user/Main epoch",
            )?;
            let identity = materials.observe(
                requested, 0, &runtime.expected_epoch, actual, actual,
            )?;
            require_settings_permission_predecessor(&histories, actual, main.facts())?;
            let work_end = settings_permission_work_end(Instant::now(), case_end)?;
            let fact = {
                let mut baseline =
                    droidloom_supervisor::native_leaf_baseline::NativeLeafBaselineObservation::capture_from_observed(
                        &inspector, &main, &before, work_end,
                    ).map_err(|e|e.to_string())?;
                native_settings_permissions::run(&mut inspector, &mut baseline, work_end)?
            };
            let completed = HistoricalSettingsPermissionCase::from_observed(
                fact, identity, before, &main, case_end,
            )?;
            completed.guard()?;
            require_same_main(completed.binding(), main.facts())?;
            inputs.guard()?;
            materials.revalidate()?;
            source_owner.guard()?;
            deadline(case_end)?;
            case_owner.finish_after_history(case_end).map_err(|e|e.to_string())?;
            Ok(completed)
        })();
        match result {
            Ok(history) => settings_history = Some(history),
            Err(error) => {
                errors.insert("com.android.settings".into(), error.clone());
                first_failure = Some(error);
            }
        }
    }

    let final_main = match (|| -> Result<control::MainCustodyObservation, String> {
        inputs.guard()?;
        materials.revalidate()?;
        source_owner.guard()?;
        deadline(end)?;
        let actual = inspector
            .refresh_main_until(&main, end)
            .map_err(|error| error.to_string())?;
        require_same_main(main.facts(), actual.facts())?;
        source_owner.compare_working_main(&actual)?;
        for history in &histories {
            history.guard()?;
        }
        for history in &family_histories {
            history.guard()?;
            require_same_main(history.binding(), main.facts())?;
        }
        if let Some(photo) = &photo_history {
            photo.guard()?;
            photo.require_original_case(&histories)?;
            require_same_main(photo.binding(), main.facts())?;
        }
        if let Some(settings) = &settings_history {
            settings.guard()?;
            settings.require_original_case(&histories)?;
            require_same_main(settings.binding(), main.facts())?;
        }
        Ok(actual)
    })() {
        Ok(actual) => Some(actual),
        Err(error) => {
            let reason = format!("final physical Main/source bookend failed: {error}");
            for row in roster::PACKAGES {
                errors
                    .entry(row.package.into())
                    .and_modify(|prior| {
                        prior.push_str("; ");
                        prior.push_str(&reason);
                    })
                    .or_insert_with(|| reason.clone());
            }
            if first_failure.is_none() {
                first_failure = Some(reason);
            }
            None
        }
    };
    let native_facts = join_native_histories(&histories)?;
    let release_scopes = release_review.reconcile(&inputs, &ScopeEvidence {
        original_main:&main, final_main:final_main.as_ref(), histories:&histories,
        native_facts:&native_facts, families:&family_histories, photo:photo_history.as_ref(),
        settings:settings_history.as_ref(), errors:&errors, retained_failure:first_failure.as_deref(),
    })?;
    let applications = summarize_rows(&histories, &native_facts, &family_histories,
        photo_history.as_ref(), settings_history.as_ref(), &release_scopes, &errors)?;
    let accepted_gates = applications.iter().map(|row| row.accepted_gates).sum();
    let accepted_applications = applications
        .iter()
        .filter(|row| row.production_ready)
        .count();
    let observed_cases = histories.len() + family_histories.len() + usize::from(photo_history.is_some())
        + usize::from(settings_history.is_some());
    let qualified = first_failure.is_none()
        && observed_cases == owned_channel::CASE_COUNT
        && final_main.is_some()
        && accepted_gates == roster::GATE_COUNT
        && accepted_applications == roster::PACKAGE_COUNT;
    let mut summary = PhysicalApplicationSummary {
        schema: REPORT_SCHEMA,
        plan: plan_pin,
        runtime_plan: plan.runtime_plan,
        source_selection,
        gate_registry: runtime.gate_registry,
        native_preparation_selection: selection,
        epoch: runtime.expected_epoch,
        original_window_seconds: seconds,
        selected_applications: roster::PACKAGE_COUNT,
        required_gates: roster::GATE_COUNT,
        observed_cases,
        accepted_gates,
        accepted_applications,
        runtime_qualified: qualified,
        production_ready: qualified,
        automatic_retry: false,
        retained_failure: first_failure.clone(),
        applications,
    };
    // Keep detailed executed comparisons in output separately from the retained
    // opaque histories. The deserializer is intentionally absent.
    for row in &mut summary.applications {
        for history in histories
            .iter()
            .filter(|case| case.summary.actual.package == row.package)
        {
            row.cases
                .push(serde_json::to_value(&history.summary).map_err(|error| error.to_string())?);
        }
    }
    for row in &mut summary.applications {
        for history in family_histories.iter()
            .filter(|case| case.summary.actual.package == row.package)
        {
            row.cases.push(serde_json::to_value(&history.summary).map_err(|e|e.to_string())?);
        }
    }
    if let Some(photo) = &photo_history {
        let row = summary.applications.iter_mut()
            .find(|row| row.package == "com.android.camera2")
            .ok_or("photo history lost its fixed summary row")?;
        row.cases.push(serde_json::to_value(&photo.summary).map_err(|e|e.to_string())?);
    }
    if let Some(settings) = &settings_history {
        let row = summary.applications.iter_mut()
            .find(|row| row.package == "com.android.settings")
            .ok_or("Settings history lost its fixed summary row")?;
        row.cases.push(serde_json::to_value(&settings.summary).map_err(|e|e.to_string())?);
    }
    let custody = RunCustody {
        inspector,
        original_main: main,
        final_main,
        materials,
        inputs,
        source_owner,
        histories,
        family_histories,
        photo_history,
        settings_history,
        native_facts,
        release_review,
        release_scopes,
        retained_errors:errors,
        retained_failure:first_failure,
        channel,
        end,
    };
    let outcome = if qualified {
        custody.guard_immutable()?;
        Outcome::Complete(CompletePhysicalApplicationRun { summary, custody })
    } else {
        Outcome::Partial(PartialPhysicalApplicationRun {
            summary,
            _custody: custody,
        })
    };
    Ok(PhysicalRunOutcome { outcome })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fixture() -> (PhysicalPlan, RuntimePlan, GateRegistry) {
        let gates: GateRegistry = serde_json::from_slice(include_bytes!(
            "../tests/fixtures/physical-gates41-registry.json"
        ))
        .unwrap();
        let pin = FilePin {
            path: "/fixture/input.json".into(),
            bytes: 2,
            sha256: "a".repeat(64),
        };
        let runtime = RuntimePlan {
            schema: 3,
            android_user: 0,
            main_qualification: pin.clone(),
            expected_epoch: RuntimeEpoch {
                boot_id: "00000000-0000-0000-0000-000000000001".into(),
                cell_host_pid: 100,
                framework_host_pid: 200,
                framework_start_ticks: 300,
            },
            gate_registry: FilePin {
                bytes: roster::REGISTRY_BYTES,
                sha256: roster::REGISTRY_SHA256.into(),
                ..pin.clone()
            },
            applications: roster::PACKAGES
                .iter()
                .map(|row| ApplicationPlan {
                    package: row.package.into(),
                    expected_input: Some(ExpectedInput {
                        version_code: 1,
                        apks: vec![ApkInput {
                            name: "base.apk".into(),
                            bytes: 8,
                            sha256: "b".repeat(64),
                        }],
                        source_receipt: pin.clone(),
                    }),
                    leaf: None,
                    launch: None,
                    binding_failure: None,
                })
                .collect(),
            execute_public_browser: false,
            browser_fixture: None,
            preparation_selection: Some(pin.clone()),
            source_selection: Some(FilePin {
                bytes: roster::CURRENT_SELECTION_BYTES,
                sha256: roster::CURRENT_SELECTION_SHA256.into(),
                ..pin.clone()
            }),
        };
        let plan = PhysicalPlan {
            schema: SCHEMA.into(),
            runtime_plan: pin.clone(),
            applications: roster::PACKAGES
                .iter()
                .map(|row| PhysicalApplicationPlan {
                    package: row.package.into(),
                    cases: row
                        .cases
                        .iter()
                        .map(|route| PhysicalCasePlan {
                            leaf: LeafPlan {
                                route: *route,
                                request: pin.clone(),
                                output: None,
                            },
                            main_qualification: pin.clone(),
                        })
                        .collect(),
                })
                .collect(),
        };
        (plan, runtime, gates)
    }
    #[test]
    fn physical_native_basis_keeps_exact_distinct_history_indices() {
        let available = [(4, Route::GalleryRotation), (7, Route::GalleryVideo),
            (8, Route::GallerySeek), (9, Route::GalleryAlbum)];
        assert_eq!(
            native_basis_indices("com.android.gallery3d",
                &[Route::GalleryRotation, Route::GalleryAlbum], &available).unwrap(),
            vec![4, 9],
        );
        assert_eq!(
            native_basis_indices("com.android.documentsui",
                &[Route::DocumentsSaf, Route::DocumentsSearchSort],
                &[(2, Route::DocumentsSaf), (3, Route::DocumentsSearchSort)]).unwrap(),
            vec![2, 3],
        );
    }

    #[test]
    fn physical_native_basis_rejects_missing_duplicate_and_foreign_cases() {
        let one = [(4, Route::GalleryRotation)];
        assert!(native_basis_indices("com.android.gallery3d", &[], &one).is_err());
        assert!(native_basis_indices("com.android.gallery3d",
            &[Route::GalleryAlbum], &one).is_err());
        assert!(native_basis_indices("com.android.gallery3d",
            &[Route::ContactsSearch], &[(1, Route::ContactsSearch)]).is_err());
        let ambiguous = [(4, Route::GalleryRotation), (5, Route::GalleryRotation)];
        assert!(native_basis_indices("com.android.gallery3d",
            &[Route::GalleryRotation], &ambiguous).is_err());
        assert!(native_basis_indices("com.android.gallery3d",
            &[Route::GalleryRotation, Route::GalleryRotation], &ambiguous).is_err());
        let aliased = [(4, Route::GalleryRotation), (4, Route::GalleryAlbum)];
        assert!(native_basis_indices("com.android.gallery3d",
            &[Route::GalleryRotation, Route::GalleryAlbum], &aliased).is_err());
    }

    #[test]
    fn physical_channel_uses_exact_source_order_windows_and_no_legacy_single_case() {
        require_channel_roster().unwrap();
        assert_eq!(physical_qualification_window_seconds(), 342_457);
        assert_eq!(camera_photo_window_seconds(), 5_185);
        assert_eq!(QualificationCase::CameraPhotoCaptureReopen as usize, 47);
        assert_eq!(case_window_seconds(Route::CameraPhoto), 1_810);
        assert_eq!(family_window_seconds("com.android.quicksearchbox"), 7_160);
        assert_eq!(family_window_seconds("com.amazon.mShop.android.shopping"), 15_250);
        assert_eq!(roster::PACKAGES.iter().filter(|row| row.cases.is_empty()).count(), 33);
        assert_eq!(owned_channel::CASE_COUNT, 49);
        assert_eq!(settings_permission_window_seconds(), 6_300);
        assert_eq!(QualificationCase::SettingsPermissionInterfaces as usize, 48);
        for route in [
            Route::ClockTimer,
            Route::ClockTimerRemaining,
            Route::ClockExpiry,
        ] {
            assert!(qualification_case(route).is_err());
        }
    }


    #[test]
    fn physical_settings_work_window_keeps_original_end_and_absent_fact_cannot_pass() {
        let now = Instant::now();
        let whole = now + Duration::from_secs(settings_permission_window_seconds());
        assert_eq!(settings_permission_work_end(now, whole).unwrap(), now + Duration::from_secs(6_050));
        assert_eq!(settings_permission_work_end(now + Duration::from_secs(300), whole).unwrap(), whole);
        assert!(settings_permission_work_end(whole, whole).is_err());
        let rows = summarize_rows(&[], &[], &[], None, None, &[], &BTreeMap::new()).unwrap();
        let settings = rows.iter().find(|row| row.package == "com.android.settings").unwrap();
        assert!(!settings.runtime_qualified && !settings.production_ready);
        let gate = settings.gate_assertions.iter().find(|gate| gate.id == "settings.permissions").unwrap();
        assert_eq!(gate.status, "pending");
        assert!(gate.completed_cases.is_empty());
        assert!(settings.native_business_facts.is_empty());
    }

    #[test]
    fn physical_family_work_window_cannot_reborrow_preinspection_or_extend_case() {
        let now = Instant::now();
        for package in ["com.android.quicksearchbox", "com.amazon.mShop.android.shopping"] {
            let whole_case = now + Duration::from_secs(family_window_seconds(package));
            let first = family_work_end(package, now, whole_case).unwrap();
            assert_eq!(first, now + Duration::from_secs(family_observation::window_seconds_for(package)));
            let late = now + Duration::from_secs(300);
            assert_eq!(family_work_end(package, late, whole_case).unwrap(), whole_case);
            assert!(family_work_end(package, whole_case, whole_case).is_err());
            assert!(family_work_end(package, whole_case + Duration::from_nanos(1), whole_case).is_err());
        }
    }

    #[test]
    fn physical_photo_work_window_cannot_reborrow_preinspection_or_extend_case() {
        let now = Instant::now();
        let whole_case = now + Duration::from_secs(camera_photo_window_seconds());
        let first = camera_photo_work_end(now, whole_case).unwrap();
        assert_eq!(first, now + Duration::from_secs(4_935));
        assert_eq!(camera_photo_work_end(now + Duration::from_secs(100), whole_case).unwrap(),
            now + Duration::from_secs(5_035));
        let late = now + Duration::from_secs(300);
        assert_eq!(camera_photo_work_end(late, whole_case).unwrap(), whole_case);
        assert!(camera_photo_work_end(whole_case, whole_case).is_err());
        assert!(camera_photo_work_end(whole_case + Duration::from_nanos(1), whole_case).is_err());
    }

    #[test]
    fn physical_family_rows_without_opaque_history_never_get_gate_credit() {
        let rows = summarize_rows(&[], &[], &[], None, None, &[], &BTreeMap::new()).unwrap();
        assert_eq!(rows.len(), roster::PACKAGE_COUNT);
        assert_eq!(rows.iter().map(|row| row.gate_assertions.len()).sum::<usize>(), 401);
        for row in rows {
            assert_eq!(row.accepted_gates, 0);
            assert!(!row.runtime_qualified && !row.production_ready);
            assert!(row.cases.is_empty() && row.blocked_gates.is_empty());
            assert!(row.release_scope_fact.is_none());
            assert!(row.gate_assertions.iter().all(|gate|
                gate.status == "pending" && gate.completed_cases.is_empty()));
        }
    }

    #[test]
    fn physical_family_source_inputs_cannot_select_a_native_case_or_unbound_material() {
        let (mut plan, runtime, gates) = fixture();
        let native = plan.applications.iter().find(|row| !row.cases.is_empty()).unwrap()
            .cases[0].leaf.clone();
        let family = plan.applications.iter_mut().find(|row| row.cases.is_empty()).unwrap();
        family.cases.push(PhysicalCasePlan {
            leaf:native, main_qualification:runtime.main_qualification.clone(),
        });
        assert!(require_compiled_roster(&plan, &runtime, &gates).is_err());
        let (plan, mut runtime, gates) = fixture();
        let selected = roster::PACKAGES.iter().find(|row| row.cases.is_empty()).unwrap().package;
        runtime.applications.iter_mut().find(|row| row.package == selected).unwrap()
            .expected_input = None;
        assert!(require_compiled_roster(&plan, &runtime, &gates).is_err());
    }

    #[test]
    fn physical_roster_rejects_a_same_count_gate_substitution_or_stale_materials() {
        let (plan, runtime, mut gates) = fixture();
        require_compiled_roster(&plan, &runtime, &gates).unwrap();
        let body = include_bytes!("../tests/fixtures/physical-gates41-registry.json");
        assert_eq!(body.len() as u64, roster::REGISTRY_BYTES);
        assert_eq!(hex::encode(Sha256::digest(body)), roster::REGISTRY_SHA256);
        let description = gates
            .profiles
            .get_mut("hotel")
            .unwrap()
            .checks
            .remove("hotel.query")
            .unwrap();
        gates
            .profiles
            .get_mut("hotel")
            .unwrap()
            .checks
            .insert("hotel.declared_query".into(), description);
        assert!(require_compiled_roster(&plan, &runtime, &gates).is_err());
        let (plan, mut runtime, gates) = fixture();
        runtime.source_selection.as_mut().unwrap().sha256 = "b".repeat(64);
        assert!(require_compiled_roster(&plan, &runtime, &gates).is_err());
    }
    #[test]
    fn selected41_preserves_every_original_gate_and_requires_both_added_app_contracts() {
        let (plan, runtime, current) = fixture();
        let original: GateRegistry = serde_json::from_slice(include_bytes!(
            "../tests/fixtures/physical-gates39-registry.json"
        )).unwrap();
        assert_eq!(original.common_gates, current.common_gates);
        let mut original_count = 0;
        for row in &roster::PACKAGES[..39] {
            assert_eq!(original.profiles[row.profile].checks, current.profiles[row.profile].checks);
            original_count += original.common_gates.len() + original.profiles[row.profile].checks.len();
        }
        assert_eq!(original_count, 377);
        for package in ["com.ss.android.lark", "com.ss.android.article.news"] {
            let fixed = roster::package(package).unwrap();
            assert_eq!(fixed.business.len(), 6);
            assert!(fixed.cases.is_empty());
            let mut missing: GateRegistry = serde_json::from_slice(include_bytes!(
                "../tests/fixtures/physical-gates41-registry.json"
            )).unwrap();
            missing.profiles.get_mut(fixed.profile).unwrap().checks.remove(fixed.business[0]);
            assert!(require_compiled_roster(&plan, &runtime, &missing).is_err());
        }
    }

    #[test]
    fn physical_roster_preserves_unique_packages_and_each_required_case_order() {
        let (mut plan, runtime, gates) = fixture();
        plan.applications[1].package = plan.applications[0].package.clone();
        assert!(require_compiled_roster(&plan, &runtime, &gates).is_err());
        let (mut plan, runtime, gates) = fixture();
        let clock = plan
            .applications
            .iter_mut()
            .find(|row| row.package == "com.android.deskclock")
            .unwrap();
        clock.cases.swap(0, 1);
        assert!(require_compiled_roster(&plan, &runtime, &gates).is_err());
        let (mut plan, runtime, gates) = fixture();
        let gallery = plan
            .applications
            .iter_mut()
            .find(|row| row.package == "com.android.gallery3d")
            .unwrap();
        gallery.cases.pop();
        assert!(require_compiled_roster(&plan, &runtime, &gates).is_err());
    }
    #[test]
    fn physical_plan_never_accepts_a_saved_passed_map_or_caller_budget() {
        let pin =
            serde_json::json!({"path":"/fixture/input.json","bytes":2,"sha256":"a".repeat(64)});
        let base = serde_json::json!({"schema":SCHEMA,"runtime_plan":pin,"applications":[]});
        // Parsing a comparison shape is not runtime validation or authority.
        assert!(serde_json::from_value::<PhysicalPlan>(base.clone()).is_ok());
        for key in [
            "passed",
            "gate_assertions",
            "budget_seconds",
            "complete",
            "production_ready",
        ] {
            let mut value = base.clone();
            value[key] = serde_json::json!(true);
            assert!(serde_json::from_value::<PhysicalPlan>(value).is_err());
        }
        let mut value = base;
        value["applications"] =
            serde_json::json!([{"package":"com.android.settings","cases":[],"passed":true}]);
        assert!(serde_json::from_value::<PhysicalPlan>(value).is_err());
    }
}

