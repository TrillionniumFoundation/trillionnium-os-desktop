//! Actual native UI and stability custody for the thirty-one non-leaf families.
//! A completed observation can retain blocked business gates after a proven
//! normal close. It cannot manufacture a business pass from a launch, text,
//! screenshot, elapsed duration, or a saved comparison report.
use super::{family_retail as retail, physical_gate_roster as roster};
use droidloom_supervisor::control::application_probe::ApplicationInspection;
use droidloom_supervisor::control::{
    NativeApplicationInspector, NativeFamilyUiEvidence, NativeUiPermissionPreservation,
    NativeUiPermissionWindow, NativeUiSession, NativeUiStabilityEvidence, NativeUiTranscript,
    RetainedNativeUiTranscript, RetainedScopedWindowPixels, family_ui_retained_members_bound,
    family_ui_window_seconds, observe_native_family_ui,
    permission_preservation_additional_window_seconds, stability_additional_window_seconds,
};
use droidloom_supervisor::main_custody::RuntimeMainCustody;
use droidloom_supervisor::native_leaf_baseline::NativeLeafBaselineObservation;
use serde::Serialize;
use serde_json::{Value, json};
use std::time::{Duration, Instant};

// Normal UI opening: helper PM, three entry checks, catalog, launch, the two
// task lists, and running Engine. These are existing source command maxima.
const OPEN_SECONDS: u64 = 250 + 3 * 15 + 250 + 250 + 2 * 15 + 70;
// The existing session reserves target PM, Main, helper PM, running Engine,
// and one bounded owned-task close. None is borrowed by the business phase.
const ORIGINAL_FINISH_SECONDS: u64 = 250 + 70 + 250 + 70 + 60;
// Each scoped capture has two task lists, two Meta calls, two WM calls, and
// one screencap. Full decode, crop, retained hashes and local guards share a
// separate finite allowance within the same original window.
const PIXEL_COMMAND_SECONDS: u64 = 2 * (2 * 15 + 2 * 15 + 2 * 15 + 20);
const LOCAL_CAPTURE_SECONDS: u64 = 120;
const FAMILY_COUNT: usize = 31;
const FAMILY_BUSINESS_GATE_COUNT: usize = 114;
// A successful close issues one task-list read when already absent, or one
// read, one removal and 1..=32 bounded asynchronous confirmation reads.
const MAX_UI_COMMANDS: u32 = 5 + 3 * 3 + 2 * 7 + 2 + 32;
fn retail_base_retained_journal_members_bound() -> usize {
    4 * MAX_UI_COMMANDS as usize + 16
}
pub(super) fn retained_journal_members_bound() -> usize {
    family_ui_retained_members_bound() + 8
}
fn fixed_history_shape(operations: u32, actions: u32) -> bool {
    (operations == 29 && actions == 0)
        || ((31..=MAX_UI_COMMANDS).contains(&operations) && actions == 1)
}
fn reopen_history_shape(operations: u32, actions: u32) -> bool {
    // Five source-owned opening commands, then the original bounded close.
    (operations == 6 && actions == 0) || ((8..=39).contains(&operations) && actions == 1)
}
fn subtract_business_counts(
    operations: u32,
    actions: u32,
    business: (u32, u32),
) -> Result<(u32, u32), String> {
    Ok((
        operations
            .checked_sub(business.0)
            .ok_or("business commands exceed the actual finished history")?,
        actions
            .checked_sub(business.1)
            .ok_or("business mutations exceed the actual finished history")?,
    ))
}

fn retail_base_ui_window_seconds() -> u64 {
    OPEN_SECONDS
        + ORIGINAL_FINISH_SECONDS
        + stability_additional_window_seconds()
        + PIXEL_COMMAND_SECONDS
        + LOCAL_CAPTURE_SECONDS
}

/// The ordinary pair and five actual retail factories have different finite
/// command sequences. Both borrow one normal permission/account window.
pub(super) fn window_seconds() -> u64 {
    family_ui_window_seconds() + permission_preservation_additional_window_seconds()
}
fn ui_window_seconds_for(package: &str) -> u64 {
    if retail::supports(package) {
        retail_base_ui_window_seconds()
            + retail::additional_window_seconds()
            + OPEN_SECONDS
            + ORIGINAL_FINISH_SECONDS
    } else {
        family_ui_window_seconds()
    }
}
pub(super) fn window_seconds_for(package: &str) -> u64 {
    ui_window_seconds_for(package) + permission_preservation_additional_window_seconds()
}
fn journal_members_bound_for(package: &str) -> usize {
    if retail::supports(package) {
        4 * (MAX_UI_COMMANDS + retail::first_max_extra_ui_commands()
            + 39 + retail::reopen_max_ui_commands()) as usize + 2 * 16
            // Each of the four extra business captures also writes its held
            // scoped-source PNG and SCOPED-PIXELS comparison outside commands.
            + 4 * 2 + 8
    } else {
        retained_journal_members_bound()
    }
}

fn require(value: bool, reason: &str) -> Result<(), String> {
    if value { Ok(()) } else { Err(reason.into()) }
}
fn family(package: &str) -> Result<&'static roster::PackageGates, String> {
    let row = roster::package(package)?;
    require(
        row.cases.is_empty(),
        "native leaf packages cannot select the family observation factory",
    )?;
    Ok(row)
}
fn require_window(
    package: &str,
    now: Instant,
    original_end: Instant,
    baseline_end: Instant,
) -> Result<(), String> {
    family(package)?;
    require(
        now < original_end
            && original_end <= baseline_end
            && original_end.duration_since(now) <= Duration::from_secs(window_seconds_for(package)),
        "family observation needs its original source-bounded case and baseline deadline",
    )
}

#[derive(Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub(super) enum FamilyBlockCode {
    BusinessFlowNotObserved,
    OwnedCommunicationPeerCasePending,
    DependentServiceConsumerCasePending,
    RenderedAudioVideoCasePending,
    BrowserFixtureCasePending,
    InputMethodConsumerCasePending,
}

/// Source-owned missing assertion, never a success or a claim about whether an
/// account, service, payment method or third-party endpoint is available.
#[derive(Debug, PartialEq, Eq, Serialize)]
pub(super) struct FamilyBlockedGate {
    id: &'static str,
    code: FamilyBlockCode,
}
impl FamilyBlockedGate {
    pub(super) fn id(&self) -> &'static str {
        self.id
    }
    pub(super) fn code(&self) -> &FamilyBlockCode {
        &self.code
    }
}
fn blocked(row: &'static roster::PackageGates) -> Vec<FamilyBlockedGate> {
    row.business
        .iter()
        .copied()
        .map(|id| {
            let code = match row.profile {
                "dialer" | "messaging" => FamilyBlockCode::OwnedCommunicationPeerCasePending,
                "gms" => FamilyBlockCode::DependentServiceConsumerCasePending,
                "video" => FamilyBlockCode::RenderedAudioVideoCasePending,
                "browser" => FamilyBlockCode::BrowserFixtureCasePending,
                "ime" => FamilyBlockCode::InputMethodConsumerCasePending,
                _ => FamilyBlockCode::BusinessFlowNotObserved,
            };
            FamilyBlockedGate { id, code }
        })
        .collect()
}

/// No public constructor or deserializer exists. These facts are minted only
/// after the actual source-owned executor, complete finished histories and
/// their held immutable members have all been joined to this same subject.
#[derive(Debug, Serialize)]
pub(super) struct FamilyBusinessFact {
    id: &'static str,
    package: String,
    main: RuntimeMainCustody,
    application: ApplicationInspection,
    basis: Value,
}
impl FamilyBusinessFact {
    pub(super) fn id(&self) -> &'static str {
        self.id
    }
    pub(super) fn require_subject(
        &self,
        main: &RuntimeMainCustody,
        application: &ApplicationInspection,
    ) -> Result<(), String> {
        require(
            self.package == application.package
                && &self.main == main
                && &self.application == application
                && family(&self.package)?.business.contains(&self.id),
            "family business assertion belongs to a different actual subject or source gate",
        )
    }
}

/// Private actual executions; a comparison document cannot select a variant.
enum BusinessExecution {
    ReadOnly,
    Retail(retail::RetailExecution),
}
impl BusinessExecution {
    fn completed_gates(&self) -> &[&'static str] {
        match self {
            Self::ReadOnly => &[],
            Self::Retail(value) => value.completed_gates(),
        }
    }
    fn first_counts(&self) -> (u32, u32) {
        match self {
            Self::ReadOnly => (0, 0),
            Self::Retail(value) => value.first_counts(),
        }
    }
    fn reopened_counts(&self) -> Option<(u32, u32)> {
        match self {
            Self::ReadOnly => None,
            Self::Retail(value) => value.reopened_counts(),
        }
    }
    fn should_reopen(&self) -> bool {
        matches!(self, Self::Retail(value) if value.should_reopen())
    }
    fn observe_reopen(
        &mut self,
        session: &mut NativeUiSession<'_, '_>,
        inspector: &mut NativeApplicationInspector,
        first: &NativeUiTranscript,
        end: Instant,
    ) -> Result<(), String> {
        match self {
            Self::Retail(value) => value.observe_reopen(session, inspector, first, end),
            Self::ReadOnly => Err("read-only family cannot request a business reopen".into()),
        }
    }
    fn guard(
        &self,
        first: &NativeUiTranscript,
        reopened: Option<&NativeUiTranscript>,
    ) -> Result<(), String> {
        let row = family(&first.engine().application().package)?;
        require(
            retail::supports(row.package) == matches!(self, Self::Retail(_)),
            "family history selected a different source-owned business factory",
        )?;
        match self {
            Self::ReadOnly => require(
                reopened.is_none() && fixed_history_shape(first.operations(), first.actions()),
                "read-only family history differs from its fixed reads and single owned close",
            )?,
            Self::Retail(value) => {
                let counts = value.first_counts();
                require(
                    counts.0 <= retail::first_max_extra_ui_commands()
                        && counts.1 <= retail::first_max_extra_actions(),
                    "retail first execution exceeded its fixed source command/action set",
                )?;
                let base = subtract_business_counts(first.operations(), first.actions(), counts)?;
                require(
                    fixed_history_shape(base.0, base.1),
                    "retail first history lost the original stability/pixel/close sequence",
                )?;
                match (value.reopened_counts(), reopened) {
                    (None, None) => (),
                    (Some(counts), Some(next)) => {
                        require(
                            counts.0 <= retail::reopen_max_ui_commands()
                                && counts.1 <= retail::reopen_max_actions(),
                            "retail second execution exceeded its fixed source command/action set",
                        )?;
                        let base =
                            subtract_business_counts(next.operations(), next.actions(), counts)?;
                        require(
                            reopen_history_shape(base.0, base.1),
                            "retail second history lost its actual independent opening and owned close",
                        )?;
                    }
                    _ => {
                        return Err(
                            "retail second execution has no exact finished second history".into(),
                        );
                    }
                }
                // This is the actual opaque executor's check. It requires all
                // retained source replies/pixels to belong to these histories.
                value.guard_immutable(first, reopened)?;
            }
        }
        let complete = self.completed_gates();
        let unique = complete
            .iter()
            .copied()
            .collect::<std::collections::BTreeSet<_>>();
        require(
            unique.len() == complete.len()
                && complete.iter().all(|gate| row.business.contains(gate)),
            "family executor repeated or substituted a compiled business gate",
        )?;
        Ok(())
    }
    fn comparison(&self) -> Result<Value, String> {
        match self {
            Self::ReadOnly => {
                Ok(json!({"factory":"read_only_ui_and_stability","comparison_only":true}))
            }
            Self::Retail(value) => value.comparison(),
        }
    }
}

fn remaining(
    row: &'static roster::PackageGates,
    complete: &[&'static str],
) -> Vec<FamilyBlockedGate> {
    blocked(row)
        .into_iter()
        .filter(|gate| !complete.contains(&gate.id))
        .collect()
}

/// Complete in-process custody. Ok does not mean that the application passed.
/// Both finished histories, original replies and pixels remain held. A caller
/// may continue only after the same original source lease also passes.
struct RetailObservation {
    stability: NativeUiStabilityEvidence,
    pixels: [RetainedScopedWindowPixels; 2],
    reopened: Option<RetainedNativeUiTranscript>,
    execution: BusinessExecution,
    business_facts: Vec<FamilyBusinessFact>,
    blocked: Vec<FamilyBlockedGate>,
}
impl RetailObservation {
    pub(super) fn stability(&self) -> &NativeUiStabilityEvidence {
        &self.stability
    }
    pub(super) fn pixels(&self) -> &[RetainedScopedWindowPixels; 2] {
        &self.pixels
    }
    pub(super) fn reopened(&self) -> Option<&RetainedNativeUiTranscript> {
        self.reopened.as_ref()
    }
    pub(super) fn business_facts(&self) -> &[FamilyBusinessFact] {
        &self.business_facts
    }
    pub(super) fn blocked(&self) -> &[FamilyBlockedGate] {
        &self.blocked
    }
    pub(super) fn complete_ui_input(&self) -> Result<bool, String> {
        self.guard_immutable()?;
        Ok(matches!(&self.execution, BusinessExecution::Retail(value)
            if value.completed_gates().contains(&"retail.search")))
    }
    pub(super) fn complete_lifecycle(&self) -> Result<bool, String> {
        self.guard_immutable()?;
        Ok(matches!(&self.execution, BusinessExecution::Retail(value)
            if value.completed_gates().contains(&"retail.navigation") && value.preserves_reopen_state()))
    }
    pub(super) fn require_subject(
        &self,
        main: &RuntimeMainCustody,
        application: &ApplicationInspection,
    ) -> Result<(), String> {
        self.stability.require_subject(main, application)?;
        if let Some(next) = &self.reopened {
            next.require_subject(main, application)?;
        }
        self.guard_immutable()
    }
    pub(super) fn guard_immutable(&self) -> Result<(), String> {
        self.stability.guard_immutable()?;
        let first = self.stability.transcript();
        let engine = first.engine();
        let row = family(&engine.application().package)?;
        if let Some(next) = &self.reopened {
            next.require_subject(&engine.facts().main, engine.application())?;
            require(
                next.transcript().task() != first.task()
                    && next.transcript().journal() != first.journal(),
                "family reopen repeats the first owned task or its finished journal",
            )?;
        }
        for pixels in &self.pixels {
            pixels.require_transcript(first)?;
        }
        self.execution
            .guard(first, self.reopened.as_ref().map(|next| next.transcript()))?;
        let complete = self.execution.completed_gates();
        let ordered = row
            .business
            .iter()
            .copied()
            .filter(|id| complete.contains(id))
            .collect::<Vec<_>>();
        require(
            self.business_facts
                .iter()
                .map(|fact| fact.id())
                .collect::<Vec<_>>()
                == ordered
                && self.blocked == remaining(row, complete),
            "family facts or blocked remainder differ from the retained actual executor",
        )?;
        for fact in &self.business_facts {
            fact.require_subject(&engine.facts().main, engine.application())?;
        }
        Ok(())
    }
    pub(super) fn comparison(&self) -> Result<Value, String> {
        self.guard_immutable()?;
        let engine = self.stability.transcript().engine();
        let row = family(&engine.application().package)?;
        let pixel_comparison = [self.pixels[0].comparison()?, self.pixels[1].comparison()?];
        Ok(json!({
            "schema":"droidloom.physical-family-observation.v2",
            "package":row.package,"profile":row.profile,
            "application":engine.application(),"main":engine.facts().main,
            "stability":self.stability.summary(),"scoped_pixels":pixel_comparison,
            "business_execution":self.execution.comparison()?,
            "reopened":self.reopened.as_ref().map(|value| value.comparison()).transpose()?,
            "business_facts":self.business_facts,"blocked":self.blocked,
            "decoded_pixels_retained_in_history":false,
            "business_input_actions_attempted":self.execution.first_counts().1 > 0
                || self.execution.reopened_counts().is_some_and(|counts| counts.1 > 0),
            "input_readback_inferred":false,"independent_reopen_inferred":false,
            "complete_data_permissions_or_account_acceptance_inferred":false,
            "source_window_seconds":window_seconds_for(row.package),
            "source_maximum_retained_journal_members":journal_members_bound_for(row.package),
            "runtime_qualified":false,"production_ready":false,"comparison_only":true
        }))
    }
}

/// Preserve the first business error. Normal finish may clean a known owned
/// task; it cannot retry an uncertain mutation or turn the failed case into Ok.
fn finish_after_business_error(
    session: NativeUiSession<'_, '_>,
    inspector: &mut NativeApplicationInspector,
    first: String,
) -> String {
    match session.finish(inspector) {
        Ok(_) => {
            format!("{first}; failed business case retained; normal owned-task close completed")
        }
        Err(cleanup) => {
            format!("{first}; failed business case retained; normal finish also failed: {cleanup}")
        }
    }
}

/// Every command uses the actual installed material and caller's already
/// started absolute deadline. Semantic partial results can preserve facts;
/// uncertain commands, cleanup, epoch or source custody remain ordinary Err.
fn run_retail_case(
    inspector: &mut NativeApplicationInspector,
    baseline: &mut NativeLeafBaselineObservation<'_>,
    original_end: Instant,
) -> Result<RetailObservation, String> {
    let application = baseline.application().clone();
    let main = baseline.main().facts().clone();
    let row = family(&application.package)?;
    require(
        retail::supports(row.package),
        "retail custody requires its source-owned retail package",
    )?;
    require_window(
        row.package,
        Instant::now(),
        original_end,
        baseline.deadline(),
    )?;
    baseline
        .verify_local(inspector, original_end)
        .map_err(|error| error.to_string())?;
    let mut session = NativeUiSession::open(inspector, baseline, original_end)?;
    let mut window = session.begin_stability(inspector)?;
    window.sample(&mut session, inspector)?;
    let first_pixels = session.scoped_window_pixels(inspector)?.into_retained()?;
    let mut execution = if retail::supports(row.package) {
        match retail::run(&mut session, inspector, row.package, original_end) {
            Ok(value) => BusinessExecution::Retail(value),
            Err(first) => return Err(finish_after_business_error(session, inspector, first)),
        }
    } else {
        BusinessExecution::ReadOnly
    };
    window.sample(&mut session, inspector)?;
    let second_pixels = session.scoped_window_pixels(inspector)?.into_retained()?;
    window.sample(&mut session, inspector)?;
    let stability = window.finish(session, inspector)?;
    stability.require_subject(&main, &application)?;
    first_pixels.require_transcript(stability.transcript())?;
    second_pixels.require_transcript(stability.transcript())?;
    let reopened = if execution.should_reopen() {
        let mut next = NativeUiSession::open(inspector, baseline, original_end)?;
        if let Err(first) =
            execution.observe_reopen(&mut next, inspector, stability.transcript(), original_end)
        {
            return Err(finish_after_business_error(next, inspector, first));
        }
        let held = next.finish(inspector)?.into_retained()?;
        held.require_subject(&main, &application)?;
        Some(held)
    } else {
        None
    };
    execution.guard(
        stability.transcript(),
        reopened.as_ref().map(|next| next.transcript()),
    )?;
    require(
        Instant::now() < original_end,
        "family fact sealing exceeded the original case deadline",
    )?;
    let complete = execution.completed_gates();
    let facts = row
        .business
        .iter()
        .copied()
        .filter(|id| complete.contains(id))
        .map(|id| FamilyBusinessFact {
            id,
            package: application.package.clone(),
            main: main.clone(),
            application: application.clone(),
            basis: json!({"factory":"retained_source_owned_family_business",
                "first_finished_journal":stability.transcript().journal(),
                "second_finished_journal":reopened.as_ref().map(|next| next.transcript().journal()),
                "gate":id,"comparison_document_grants_acceptance":false}),
        })
        .collect();
    let blocked = remaining(row, complete);
    let observation = RetailObservation {
        stability,
        pixels: [first_pixels, second_pixels],
        reopened,
        execution,
        business_facts: facts,
        blocked,
    };
    observation.guard_immutable()?;
    require(
        Instant::now() < original_end,
        "family custody sealing exceeded the original case deadline",
    )?;
    Ok(observation)
}

/// Separate opaque execution histories. Only the actual normal constructors
/// below can choose a branch; a saved report cannot enter either one.
enum FamilyHistory {
    Ordinary {
        ui: NativeFamilyUiEvidence,
        blocked: Vec<FamilyBlockedGate>,
    },
    Retail(RetailObservation),
}

/// The actual before/after PM, AppOps and anonymous-account samples enclose
/// the executed sessions. They remain partial preservation evidence.
pub(super) struct FamilyObservation {
    history: FamilyHistory,
    permissions: NativeUiPermissionPreservation,
}
impl FamilyObservation {
    pub(super) fn stability(&self) -> &NativeUiStabilityEvidence {
        match &self.history {
            FamilyHistory::Ordinary { ui, .. } => ui.stability(),
            FamilyHistory::Retail(value) => value.stability(),
        }
    }
    pub(super) fn ordinary_ui(&self) -> Option<&NativeFamilyUiEvidence> {
        match &self.history {
            FamilyHistory::Ordinary { ui, .. } => Some(ui),
            FamilyHistory::Retail(_) => None,
        }
    }
    pub(super) fn reopened(&self) -> Option<&RetainedNativeUiTranscript> {
        match &self.history {
            FamilyHistory::Ordinary { ui, .. } => Some(ui.reopened()),
            FamilyHistory::Retail(value) => value.reopened(),
        }
    }
    pub(super) fn business_facts(&self) -> &[FamilyBusinessFact] {
        match &self.history {
            FamilyHistory::Ordinary { .. } => &[],
            FamilyHistory::Retail(value) => value.business_facts(),
        }
    }
    pub(super) fn blocked(&self) -> &[FamilyBlockedGate] {
        match &self.history {
            FamilyHistory::Ordinary { blocked, .. } => blocked,
            FamilyHistory::Retail(value) => value.blocked(),
        }
    }
    pub(super) fn complete_ui_input(&self) -> Result<bool, String> {
        self.guard_immutable()?;
        match &self.history {
            FamilyHistory::Ordinary { .. } => Ok(true),
            FamilyHistory::Retail(value) => value.complete_ui_input(),
        }
    }
    pub(super) fn complete_lifecycle(&self) -> Result<bool, String> {
        self.guard_immutable()?;
        match &self.history {
            FamilyHistory::Ordinary { .. } => Ok(true),
            FamilyHistory::Retail(value) => value.complete_lifecycle(),
        }
    }
    pub(super) fn require_subject(
        &self,
        main: &RuntimeMainCustody,
        application: &ApplicationInspection,
    ) -> Result<(), String> {
        match &self.history {
            FamilyHistory::Ordinary { ui, .. } => ui.require_subject(main, application)?,
            FamilyHistory::Retail(value) => value.require_subject(main, application)?,
        }
        self.guard_immutable()
    }
    pub(super) fn guard_immutable(&self) -> Result<(), String> {
        match &self.history {
            FamilyHistory::Ordinary {
                ui,
                blocked: pending,
            } => {
                ui.guard_immutable()?;
                let row = family(&ui.stability().transcript().engine().application().package)?;
                require(
                    !retail::supports(row.package) && pending == &blocked(row),
                    "ordinary family custody cannot replace a retail factory or omit a business gate",
                )?;
            }
            FamilyHistory::Retail(value) => value.guard_immutable()?,
        }
        let first = self.stability().transcript();
        match self.reopened() {
            Some(second) => self.permissions.require_pair(first, second.transcript()),
            // A semantic retail partial result may have no second business
            // session. Its single-session receipt cannot supply lifecycle,
            // account, data, or whole-release acceptance.
            None => self.permissions.require_transcript(first),
        }
    }
    pub(super) fn comparison(&self) -> Result<Value, String> {
        self.guard_immutable()?;
        let engine = self.stability().transcript().engine();
        let row = family(&engine.application().package)?;
        let execution = match &self.history {
            FamilyHistory::Ordinary { ui, .. } => ui.comparison()?,
            FamilyHistory::Retail(value) => value.comparison()?,
        };
        Ok(json!({
            "schema":"droidloom.physical-family-observation.v3",
            "package":row.package,"profile":row.profile,
            "application":engine.application(),"main":engine.facts().main,
            "stability":self.stability().summary(),
            "actual_execution":execution,
            "pm_permission_preservation":self.permissions.comparison()?,
            "business_facts":self.business_facts(),"blocked":self.blocked(),
            "decoded_pixels_retained_in_history":false,
            "complete_data_permissions_or_account_acceptance_inferred":false,
            "source_window_seconds":window_seconds_for(row.package),
            "source_maximum_retained_journal_members":journal_members_bound_for(row.package),
            "runtime_qualified":false,"production_ready":false,"comparison_only":true
        }))
    }
}

/// One original case window owns the actual state samples and selected normal
/// UI factory. No intermediate sample renews the original end or adds a grant.
pub(super) fn run_family_case(
    inspector: &mut NativeApplicationInspector,
    baseline: &mut NativeLeafBaselineObservation<'_>,
    original_end: Instant,
) -> Result<FamilyObservation, String> {
    let application = baseline.application().clone();
    let main = baseline.main().facts().clone();
    let row = family(&application.package)?;
    require_window(
        row.package,
        Instant::now(),
        original_end,
        baseline.deadline(),
    )?;
    baseline
        .verify_local(inspector, original_end)
        .map_err(|e| e.to_string())?;
    let permission_window = NativeUiPermissionWindow::begin(inspector, baseline, original_end)?;
    let ui_end = (Instant::now() + Duration::from_secs(ui_window_seconds_for(row.package)))
        .min(permission_window.ui_deadline());
    let history = match (|| -> Result<FamilyHistory, String> {
        if retail::supports(row.package) {
            let value = run_retail_case(inspector, baseline, ui_end)?;
            value.require_subject(&main, &application)?;
            Ok(FamilyHistory::Retail(value))
        } else {
            let ui = observe_native_family_ui(inspector, baseline, ui_end)?;
            ui.require_subject(&main, &application)?;
            Ok(FamilyHistory::Ordinary {
                ui,
                blocked: blocked(row),
            })
        }
    })() {
        Ok(value) => value,
        Err(first) => return Err(permission_window.fail(first)),
    };
    let permissions = match &history {
        FamilyHistory::Ordinary { ui, .. } => permission_window.finish_pair(
            inspector,
            baseline,
            ui.stability().transcript(),
            ui.reopened().transcript(),
        )?,
        FamilyHistory::Retail(value) => match value.reopened() {
            Some(second) => permission_window.finish_pair(
                inspector,
                baseline,
                value.stability().transcript(),
                second.transcript(),
            )?,
            None => {
                permission_window.finish(inspector, baseline, value.stability().transcript())?
            }
        },
    };
    let observation = FamilyObservation {
        history,
        permissions,
    };
    observation.guard_immutable()?;
    require(
        Instant::now() < original_end,
        "family custody sealing exceeded its original case end",
    )?;
    Ok(observation)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn family_observation_source_scope_rejects_native_leaves_and_excluded_apps() {
        let rows: Vec<_> = roster::PACKAGES
            .iter()
            .filter(|row| row.cases.is_empty())
            .collect();
        assert_eq!(rows.len(), FAMILY_COUNT);
        assert_eq!(
            rows.iter().map(|row| row.business.len()).sum::<usize>(),
            FAMILY_BUSINESS_GATE_COUNT
        );
        for row in roster::PACKAGES {
            assert_eq!(family(row.package).is_ok(), row.cases.is_empty());
        }
        for package in [
            "com.enflick.android.TextNow",
            "com.pinger.textfree",
            "com.ubercab",
            "com.android.settings.other",
            "",
        ] {
            assert!(family(package).is_err());
        }
    }

    #[test]
    fn family_observation_blocked_history_cannot_omit_or_duplicate_business_gates() {
        let mut seen = std::collections::BTreeSet::new();
        for row in roster::PACKAGES.iter().filter(|row| row.cases.is_empty()) {
            let pending = blocked(row);
            assert_eq!(pending.len(), row.business.len());
            for (observed, expected) in pending.iter().zip(row.business) {
                assert_eq!(observed.id(), *expected);
                assert!(seen.insert((row.package, observed.id())));
                let serialized = serde_json::to_value(observed).unwrap();
                assert!(serialized.get("passed").is_none());
                assert!(serialized.get("safe_to_continue").is_none());
            }
        }
        assert_eq!(seen.len(), FAMILY_BUSINESS_GATE_COUNT);
    }

    #[test]
    fn family_observation_budget_rejects_renewal_and_outliving_original_baseline() {
        assert_eq!(stability_additional_window_seconds(), 680);
        assert_eq!(retail_base_ui_window_seconds(), 2615);
        assert_eq!(family_ui_window_seconds(), 6490);
        assert_eq!(permission_preservation_additional_window_seconds(), 420);
        assert_eq!(window_seconds(), 6910);
        let now = Instant::now();
        let end = now + Duration::from_secs(window_seconds());
        require_window("com.Hyatt.hyt", now, end, end).unwrap();
        require_window("com.Hyatt.hyt", now, end - Duration::from_secs(1), end).unwrap();
        assert!(require_window("com.Hyatt.hyt", now, end + Duration::from_nanos(1), end).is_err());
        assert!(require_window("com.Hyatt.hyt", now, end, end - Duration::from_nanos(1)).is_err());
        assert!(require_window("com.Hyatt.hyt", now, now, end).is_err());
        assert!(require_window("com.Hyatt.hyt", now, now - Duration::from_nanos(1), end).is_err());
        assert!(
            require_window(
                "com.Hyatt.hyt",
                now,
                end + Duration::from_secs(1),
                end + Duration::from_secs(1)
            )
            .is_err()
        );
    }

    #[test]
    fn family_observation_history_bounds_allow_only_fixed_reads_and_one_owned_close() {
        assert_eq!(MAX_UI_COMMANDS, 62);
        assert_eq!(retail_base_retained_journal_members_bound(), 264);
        assert_eq!(family_ui_retained_members_bound(), 768);
        assert_eq!(retained_journal_members_bound(), 776);
        assert!(fixed_history_shape(29, 0));
        for operations in 31..=62 {
            assert!(fixed_history_shape(operations, 1));
        }
        for (operations, actions) in [(0, 0), (28, 0), (29, 1), (30, 1), (31, 0), (62, 2), (63, 1)]
        {
            assert!(!fixed_history_shape(operations, actions));
        }
    }
    #[test]
    fn family_retail_windows_and_history_remainder_are_package_specific() {
        let now = Instant::now();
        let mut retail_count = 0;
        for row in roster::PACKAGES.iter().filter(|row| row.cases.is_empty()) {
            let seconds = window_seconds_for(row.package);
            if retail::supports(row.package) {
                retail_count += 1;
                assert_eq!(row.profile, "retail");
                assert_eq!(ui_window_seconds_for(row.package), 8690);
                assert_eq!(seconds, 9110);
                assert_eq!(journal_members_bound_for(row.package), 1020);
            } else {
                assert_eq!(seconds, 6910);
                assert_eq!(journal_members_bound_for(row.package), 776);
            }
            let end = now + Duration::from_secs(seconds);
            require_window(row.package, now, end, end).unwrap();
            assert!(
                require_window(
                    row.package,
                    now,
                    end + Duration::from_nanos(1),
                    end + Duration::from_nanos(1)
                )
                .is_err()
            );
            assert!(require_window(row.package, now, end, end - Duration::from_nanos(1)).is_err());
        }
        assert_eq!(retail_count, 5);
        assert!(
            require_window(
                "com.android.settings",
                now,
                now + Duration::from_secs(1),
                now + Duration::from_secs(1)
            )
            .is_err()
        );
        assert!(
            require_window(
                "com.ubercab",
                now,
                now + Duration::from_secs(1),
                now + Duration::from_secs(1)
            )
            .is_err()
        );
        assert_eq!(
            subtract_business_counts(121, 11, (92, 11)).unwrap(),
            (29, 0)
        );
        assert!(subtract_business_counts(91, 11, (92, 11)).is_err());
        assert!(subtract_business_counts(121, 10, (92, 11)).is_err());
        assert!(reopen_history_shape(6, 0));
        for operations in 8..=39 {
            assert!(reopen_history_shape(operations, 1));
        }
        for (operations, actions) in [(0, 0), (5, 0), (6, 1), (7, 1), (8, 0), (39, 2), (40, 1)] {
            assert!(!reopen_history_shape(operations, actions));
        }
        let row = family("com.amazon.mShop.android.shopping").unwrap();
        let pending = remaining(
            row,
            &["retail.search", "retail.detail", "retail.navigation"],
        );
        assert_eq!(pending.len(), 1);
        assert_eq!(pending[0].id(), "retail.account");
    }
}
