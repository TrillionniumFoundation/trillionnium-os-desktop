//! Actual native UI and stability custody for the thirty-one non-leaf families.
//! A completed observation can retain blocked business gates after a proven
//! normal close. It cannot manufacture a business pass from a launch, text,
//! screenshot, elapsed duration, or a saved comparison report.
use super::physical_gate_roster as roster;
use droidloom_supervisor::control::application_probe::ApplicationInspection;
use droidloom_supervisor::control::{
    NativeApplicationInspector, NativeFamilyUiEvidence, NativeUiStabilityEvidence,
    observe_native_family_ui, family_ui_window_seconds, family_ui_retained_members_bound,
    NativeUiPermissionWindow, NativeUiPermissionPreservation,
    permission_preservation_additional_window_seconds,
};
use droidloom_supervisor::main_custody::RuntimeMainCustody;
use droidloom_supervisor::native_leaf_baseline::NativeLeafBaselineObservation;
use serde::Serialize;
use serde_json::{Value, json};
use std::time::{Duration, Instant};

const FAMILY_COUNT: usize = 31;
const FAMILY_BUSINESS_GATE_COUNT: usize = 114;
pub(super) fn retained_journal_members_bound() -> usize {
    // Root's normal preservation factory owns its separate fixed journal.
    // Eight records cover the same PM/AppOps/account interval around both sessions.
    family_ui_retained_members_bound() + 8
}
fn ui_window_seconds() -> u64 { family_ui_window_seconds() }
pub(super) fn window_seconds() -> u64 {
    ui_window_seconds() + permission_preservation_additional_window_seconds()
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
    now: Instant,
    original_end: Instant,
    baseline_end: Instant,
) -> Result<(), String> {
    require(
        now < original_end
            && original_end <= baseline_end
            && original_end.duration_since(now) <= Duration::from_secs(window_seconds()),
        "family observation needs its original source-bounded case and baseline deadline",
    )
}

#[derive(Debug, Serialize)]
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
#[derive(Debug, Serialize)]
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

/// No public constructor or deserializer exists. Only an actual source-owned
/// business executor in this module may later add a completed assertion. The
/// present read-only UI/stability factory creates no instance of this type.
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

/// Complete in-process custody. Ok does not mean that the application passed.
/// A caller may continue another independent case only after this object's
/// immutable checks and the original source lease have both been validated.
pub(super) struct FamilyObservation {
    ui: NativeFamilyUiEvidence,
    permissions: NativeUiPermissionPreservation,
    business_facts: Vec<FamilyBusinessFact>,
    blocked: Vec<FamilyBlockedGate>,
}
impl FamilyObservation {
    pub(super) fn stability(&self) -> &NativeUiStabilityEvidence { self.ui.stability() }
    pub(super) fn ui(&self) -> &NativeFamilyUiEvidence { &self.ui }
    pub(super) fn business_facts(&self) -> &[FamilyBusinessFact] { &self.business_facts }
    pub(super) fn blocked(&self) -> &[FamilyBlockedGate] { &self.blocked }
    pub(super) fn require_subject(
        &self, main: &RuntimeMainCustody, application: &ApplicationInspection,
    ) -> Result<(), String> {
        self.ui.require_subject(main, application)?;
        self.guard_immutable()
    }
    pub(super) fn guard_immutable(&self) -> Result<(), String> {
        self.ui.guard_immutable()?;
        let first = self.ui.stability().transcript();
        let reopened = self.ui.reopened().transcript();
        // A single-session preservation receipt cannot cover this pair.
        // The normal window's actual before/after observations enclose both
        // closes and the strict first.finished < reopened.opened boundary.
        self.permissions.require_pair(first, reopened)?;
        let row = family(&first.engine().application().package)?;
        require(
            self.business_facts.is_empty()
                && self.blocked.len() == row.business.len()
                && self.blocked.iter().zip(row.business)
                    .all(|(blocked, required)| blocked.id == *required),
            "Family common evidence cannot create business success or drop a required gate",
        )?;
        Ok(())
    }
    pub(super) fn comparison(&self) -> Result<Value, String> {
        self.guard_immutable()?;
        let engine = self.ui.stability().transcript().engine();
        let row = family(&engine.application().package)?;
        Ok(json!({
            "schema":"droidloom.physical-family-observation.v3",
            "package":row.package,"profile":row.profile,
            "application":engine.application(),"main":engine.facts().main,
            "stability":self.ui.stability().summary(),
            "actual_ui_lifecycle":self.ui.comparison()?,
            "pm_permission_preservation":self.permissions.comparison()?,
            "business_facts":self.business_facts,"blocked":self.blocked,
            "decoded_pixels_retained_in_history":false,
            "business_fixture_state_created":false,
            "complete_data_permissions_or_account_acceptance_inferred":false,
            "source_window_seconds":window_seconds(),
            "source_maximum_retained_journal_members":retained_journal_members_bound(),
            "runtime_qualified":false,"production_ready":false,"comparison_only":true
        }))
    }
}

/// Both UI sessions use the one normal context and original absolute end.
/// A failure remains a failure after any certain, source-owned cleanup. Saved
/// comparison JSON and a partial visual result cannot enter this constructor.
pub(super) fn run_family_case(
    inspector: &mut NativeApplicationInspector,
    baseline: &mut NativeLeafBaselineObservation<'_>,
    original_end: Instant,
) -> Result<FamilyObservation, String> {
    require_window(Instant::now(), original_end, baseline.deadline())?;
    let application = baseline.application().clone();
    let main = baseline.main().facts().clone();
    let row = family(&application.package)?;
    baseline.verify_local(inspector, original_end).map_err(|e|e.to_string())?;
    let permission_window = NativeUiPermissionWindow::begin(inspector, baseline, original_end)?;
    let ui_end = (Instant::now() + Duration::from_secs(ui_window_seconds()))
        .min(permission_window.ui_deadline());
    let ui = match observe_native_family_ui(inspector, baseline, ui_end) {
        Ok(value) => value,
        Err(error) => return Err(permission_window.fail(error)),
    };
    ui.require_subject(&main, &application)?;
    let permissions = permission_window.finish_pair(
        inspector, baseline, ui.stability().transcript(), ui.reopened().transcript(),
    )?;
    let observation = FamilyObservation {
        ui, permissions, business_facts: Vec::new(), blocked: blocked(row),
    };
    observation.guard_immutable()?;
    require(Instant::now() < original_end,
        "Family custody sealing exceeded the original case deadline")?;
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
        assert_eq!(ui_window_seconds(), 6490);
        assert_eq!(permission_preservation_additional_window_seconds(), 420);
        assert_eq!(window_seconds(), 6910);
        let now = Instant::now();
        let end = now + Duration::from_secs(window_seconds());
        require_window(now, end, end).unwrap();
        require_window(now, end - Duration::from_secs(1), end).unwrap();
        assert!(require_window(now, end + Duration::from_nanos(1), end).is_err());
        assert!(require_window(now, end, end - Duration::from_nanos(1)).is_err());
        assert!(require_window(now, now, end).is_err());
        assert!(require_window(now, now - Duration::from_nanos(1), end).is_err());
        assert!(
            require_window(
                now,
                end + Duration::from_secs(1),
                end + Duration::from_secs(1)
            )
            .is_err()
        );
    }

    #[test]
    fn family_observation_pair_has_finite_retained_inputs_without_rgb_history() {
        assert_eq!(family_ui_retained_members_bound(), 768);
        assert_eq!(retained_journal_members_bound(), 776);
        assert!(31 * retained_journal_members_bound() < 32_768);
    }
}
