//! One source-owned, same-boot physical application qualification run.
//!
//! Saved plans/results select inputs and permit comparisons; they never mint
//! completed gates. Only the existing live factories below can create the
//! move-only case histories retained by CompletePhysicalApplicationRun.
use super::clock_timer::{self, ClockResultCustody};
use super::common_gate::CommonGateFact;
use super::leaf_release::{self, NativeRelease};
use super::leaf_routes::{self, LeafPlan, Route};
use super::physical_gate_roster as roster;
use super::runtime_identity::VerifiedMaterialBatch;
use super::*;
use droidloom_supervisor::main_custody::RuntimeMainCustody;
use serde_json::Value;

const SCHEMA: &str = "droidloom.physical-application-plan.v1";
const REPORT_SCHEMA: &str = "droidloom.physical-application-run.v1";
const SOURCE_AND_CAPTURE_SECONDS: u64 = 120;
const MAIN_SECONDS: u64 = 70;
const INSPECT_SECONDS: u64 = 250;

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

/// This initial source roster has fourteen native case entries. Each entry
/// retains its original source-owned work/retirement bound. The timer pair
/// consumes its supplied pre-inspection inside its existing 2100-second window.
pub fn physical_qualification_window_seconds() -> u64 {
    SOURCE_AND_CAPTURE_SECONDS
        + 2 * MAIN_SECONDS
        + roster::PACKAGES
            .iter()
            .map(|row| {
                if row.cases.is_empty() {
                    INSPECT_SECONDS
                } else {
                    row.cases.iter().copied().map(case_window_seconds).sum()
                }
            })
            .sum::<u64>()
}
fn case_window_seconds(route: Route) -> u64 {
    if route == Route::ClockTimerPair {
        clock_timer::pair_window_seconds()
    } else {
        INSPECT_SECONDS + leaf_routes::original_window_seconds(route)
    }
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
        "complete physical qualification requires the fixed 39-package user-zero source roster",
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
        "complete physical roster does not contain exactly its reviewed 377 distinct per-App gates",
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
}
impl HistoricalCompletedCase {
    fn from_leaf(observation: leaf_routes::LeafObservation, end: Instant) -> Result<Self, String> {
        let (custody, common, business, evidence, actual, source_release) =
            observation.seal_history_before(end)?;
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
        Ok(())
    }
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

struct RunCustody {
    inspector: control::NativeApplicationInspector,
    original_main: control::MainCustodyObservation,
    final_main: Option<control::MainCustodyObservation>,
    materials: VerifiedMaterialBatch,
    inputs: PlanInputs,
    source_owner: NativeRelease,
    histories: Vec<HistoricalCompletedCase>,
    end: Instant,
}
impl RunCustody {
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
    errors: &BTreeMap<String, String>,
) -> Result<Vec<ApplicationSummary>, String> {
    let mut rows = Vec::new();
    for fixed in roster::PACKAGES {
        let cases = histories
            .iter()
            .enumerate()
            .filter(|(_, case)| case.summary.actual.package == fixed.package)
            .collect::<Vec<_>>();
        // Do not borrow an arbitrary caller gate map: these IDs come only from
        // the two consuming original-factory constructors above.
        let mut assertions = Vec::new();
        for id in roster::required(fixed) {
            let indices = cases
                .iter()
                .filter(|(_, case)| {
                    case.summary.common.iter().any(|fact| fact.id() == id)
                        || case.summary.business_gates.contains(&id)
                })
                .map(|(index, _)| *index)
                .collect::<Vec<_>>();
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
            && !errors.contains_key(fixed.package)
            && assertions.iter().all(|gate| gate.status == "passed");
        rows.push(ApplicationSummary {
            package: fixed.package.into(),
            profile: fixed.profile,
            // The facts remain in custody. The public comparison below is
            // copied through serialization, never used to construct authority.
            cases: Vec::new(),
            gate_assertions: assertions,
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
    let mut histories = Vec::new();
    let mut errors = BTreeMap::new();
    let mut first_failure: Option<String> = None;
    for row in &plan.applications {
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
            let inspected = (|| -> Result<(), String> {
                deadline(end)?;
                let cutoff = (Instant::now() + Duration::from_secs(INSPECT_SECONDS)).min(end);
                let actual = inspector
                    .inspect_observed_until(&row.package, 0, cutoff)
                    .map_err(|error| error.to_string())?;
                materials.observe(
                    &requested,
                    0,
                    &runtime.expected_epoch,
                    actual.facts(),
                    actual.facts(),
                )?;
                // A single actual PM read is a precondition, not a complete
                // identity/lifecycle/business gate or an Engine observation.
                Ok(())
            })();
            if let Err(error) = inspected {
                errors.insert(row.package.clone(), error.clone());
                first_failure = Some(error);
            }
            continue;
        }
        for case in &row.cases {
            let result = (|| -> Result<HistoricalCompletedCase, String> {
                deadline(end)?;
                let case_end = (Instant::now()
                    + Duration::from_secs(case_window_seconds(case.leaf.route)))
                .min(end);
                let inspection_end =
                    (Instant::now() + Duration::from_secs(INSPECT_SECONDS)).min(case_end);
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
    let final_main = match (|| -> Result<control::MainCustodyObservation, String> {
        inputs.guard()?;
        materials.revalidate()?;
        source_owner.guard()?;
        deadline(end)?;
        let actual = inspector
            .refresh_main_until(&main, end)
            .map_err(|error| error.to_string())?;
        require_same_main(main.facts(), actual.facts())?;
        for history in &histories {
            history.guard()?;
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
    let applications = summarize_rows(&histories, &errors)?;
    let accepted_gates = applications.iter().map(|row| row.accepted_gates).sum();
    let accepted_applications = applications
        .iter()
        .filter(|row| row.production_ready)
        .count();
    let qualified = first_failure.is_none()
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
        observed_cases: histories.len(),
        accepted_gates,
        accepted_applications,
        runtime_qualified: qualified,
        production_ready: qualified,
        automatic_retry: false,
        retained_failure: first_failure,
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
    let custody = RunCustody {
        inspector,
        original_main: main,
        final_main,
        materials,
        inputs,
        source_owner,
        histories,
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
            "../tests/fixtures/physical-gates39-registry.json"
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
    fn physical_roster_rejects_a_same_count_gate_substitution_or_stale_materials() {
        let (plan, runtime, mut gates) = fixture();
        require_compiled_roster(&plan, &runtime, &gates).unwrap();
        let body = include_bytes!("../tests/fixtures/physical-gates39-registry.json");
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
