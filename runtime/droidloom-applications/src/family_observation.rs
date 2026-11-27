//! Actual native UI and stability custody for the thirty-one non-leaf families.
//! A completed observation can retain blocked business gates after a proven
//! normal close. It cannot manufacture a business pass from a launch, text,
//! screenshot, elapsed duration, or a saved comparison report.
use super::physical_gate_roster as roster;
use droidloom_supervisor::control::application_probe::ApplicationInspection;
use droidloom_supervisor::control::{
    NativeApplicationInspector, NativeUiSession, NativeUiStabilityEvidence,
    RetainedScopedWindowPixels, stability_additional_window_seconds,
    NativeUiPermissionWindow, NativeUiPermissionPreservation,
    permission_preservation_additional_window_seconds,
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
pub(super) fn retained_journal_members_bound() -> usize {
    4 * MAX_UI_COMMANDS as usize + 16 + 4 // Separate fixed PM-permission journal.
}
fn fixed_history_shape(operations: u32, actions: u32) -> bool {
    (operations == 29 && actions == 0)
        || ((31..=MAX_UI_COMMANDS).contains(&operations) && actions == 1)
}

fn ui_window_seconds() -> u64 {
    OPEN_SECONDS
        + ORIGINAL_FINISH_SECONDS
        + stability_additional_window_seconds()
        + PIXEL_COMMAND_SECONDS
        + LOCAL_CAPTURE_SECONDS
}
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
    stability: NativeUiStabilityEvidence,
    permissions: NativeUiPermissionPreservation,
    pixels: [RetainedScopedWindowPixels; 2],
    business_facts: Vec<FamilyBusinessFact>,
    blocked: Vec<FamilyBlockedGate>,
}
impl FamilyObservation {
    pub(super) fn stability(&self) -> &NativeUiStabilityEvidence {
        &self.stability
    }
    pub(super) fn pixels(&self) -> &[RetainedScopedWindowPixels; 2] {
        &self.pixels
    }
    pub(super) fn business_facts(&self) -> &[FamilyBusinessFact] {
        &self.business_facts
    }
    pub(super) fn blocked(&self) -> &[FamilyBlockedGate] {
        &self.blocked
    }
    pub(super) fn require_subject(
        &self,
        main: &RuntimeMainCustody,
        application: &ApplicationInspection,
    ) -> Result<(), String> {
        self.stability.require_subject(main, application)?;
        self.guard_immutable()
    }
    pub(super) fn guard_immutable(&self) -> Result<(), String> {
        self.stability.guard_immutable()?;
        let transcript = self.stability.transcript();
        let engine = transcript.engine();
        // A mandatory partial PM fact, bound to this exact normal-close
        // transcript. It never supplies common.data_permissions or accounts.
        self.permissions.require_transcript(transcript)?;
        require(
            fixed_history_shape(transcript.operations(), transcript.actions()),
            "family history is outside its fixed read sequence and single owned close",
        )?;
        let row = family(&engine.application().package)?;
        require(
            self.business_facts.is_empty()
                && self.blocked.len() == row.business.len()
                && self
                    .blocked
                    .iter()
                    .zip(row.business)
                    .all(|(blocked, required)| blocked.id == *required),
            "read-only family evidence cannot mint business success or drop a required gate",
        )?;
        for pixels in &self.pixels {
            // This joins the actual complete Main/PM, task and journal of the
            // consumed session. Two observations from different tasks cannot
            // be spliced merely because their package and epoch match.
            pixels.require_transcript(transcript)?;
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
            "package":row.package,
            "profile":row.profile,
            "application":engine.application(),
            "main":engine.facts().main,
            "stability":self.stability.summary(),
            "pm_permission_preservation":self.permissions.comparison()?,
            "scoped_pixels":pixel_comparison,
            "business_facts":self.business_facts,
            "blocked":self.blocked,
            "decoded_pixels_retained_in_history":false,
            "business_input_actions_attempted":false,
            "business_fixture_state_created":false,
            "input_readback_inferred":false,
            "independent_reopen_inferred":false,
            "complete_data_permissions_or_account_acceptance_inferred":false,
            "source_window_seconds":window_seconds(),
            "source_maximum_retained_journal_members":retained_journal_members_bound(),
            "runtime_qualified":false,
            "production_ready":false,
            "comparison_only":true
        }))
    }
}

/// The only family observation constructor. Every command uses the original
/// session, actual installed material identity and caller's already-started
/// absolute deadline. Unknown command outcome, cleanup failure, changed epoch,
/// failed resource fence, or any lost custody remains an ordinary Err.
pub(super) fn run_family_case(
    inspector: &mut NativeApplicationInspector,
    baseline: &mut NativeLeafBaselineObservation<'_>,
    original_end: Instant,
) -> Result<FamilyObservation, String> {
    require_window(Instant::now(), original_end, baseline.deadline())?;
    let application = baseline.application().clone();
    let main = baseline.main().facts().clone();
    let row = family(&application.package)?;
    baseline
        .verify_local(inspector, original_end)
        .map_err(|error| error.to_string())?;
    let permission_window = NativeUiPermissionWindow::begin(inspector, baseline, original_end)?;
    // Keep the original 2615-second UI maximum and reserve the actual after
    // query under the same case end. Fast pre-query completion cannot renew it.
    let ui_end = (Instant::now() + Duration::from_secs(ui_window_seconds()))
        .min(permission_window.ui_deadline());
    let ui = (|| {
        let mut session = NativeUiSession::open(inspector, baseline, ui_end)?;
        let mut window = session.begin_stability(inspector)?;
        window.sample(&mut session, inspector)?;
        let first_pixels = session.scoped_window_pixels(inspector)?.into_retained()?;
        window.sample(&mut session, inspector)?;
        let second_pixels = session.scoped_window_pixels(inspector)?.into_retained()?;
        window.sample(&mut session, inspector)?;
        // No business input, form submission, outbound communication, permission
        // change, owned document, or account mutation occurs in this constructor.
        // finish proves the actual single owned close and full normal bookends.
        let stability = window.finish(session, inspector)?;
        stability.require_subject(&main, &application)?;
        first_pixels.require_transcript(stability.transcript())?;
        second_pixels.require_transcript(stability.transcript())?;
        Ok::<_, String>((stability, first_pixels, second_pixels))
    })();
    let (stability, first_pixels, second_pixels) = match ui {
        Ok(value) => value,
        Err(error) => return Err(permission_window.fail(error)),
    };
    let permissions = permission_window.finish(inspector, baseline, stability.transcript())?;
    let observation = FamilyObservation {
        stability,
        permissions,
        pixels: [first_pixels, second_pixels],
        business_facts: Vec::new(),
        blocked: blocked(row),
    };
    observation.guard_immutable()?;
    require(
        Instant::now() < original_end,
        "family custody sealing exceeded the original case deadline",
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
        assert_eq!(ui_window_seconds(), 2615);
        assert_eq!(permission_preservation_additional_window_seconds(), 140);
        assert_eq!(window_seconds(), 2755);
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
    fn family_observation_history_bounds_allow_only_fixed_reads_and_one_owned_close() {
        assert_eq!(MAX_UI_COMMANDS, 62);
        assert_eq!(retained_journal_members_bound(), 268);
        assert!(fixed_history_shape(29, 0));
        for operations in 31..=62 {
            assert!(fixed_history_shape(operations, 1));
        }
        for (operations, actions) in [(0, 0), (28, 0), (29, 1), (30, 1), (31, 0), (62, 2), (63, 1)]
        {
            assert!(!fixed_history_shape(operations, actions));
        }
    }
}
