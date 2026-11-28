//! Separate source-owned collaboration business sessions after the full common pair.
//! The reviewed executor, both real finished histories and independent
//! PM/AppOps/account observations remain held. No saved comparison is admitted.
use super::family_collaboration as collaboration;
use droidloom_supervisor::control::application_probe::ApplicationInspection;
use droidloom_supervisor::control::{
    NativeApplicationInspector, NativeUiPermissionPreservation, NativeUiPermissionWindow,
    NativeUiSession, NativeUiTranscript, RetainedNativeUiTranscript,
    permission_preservation_additional_window_seconds,
};
use droidloom_supervisor::main_custody::RuntimeMainCustody;
use droidloom_supervisor::native_leaf_baseline::NativeLeafBaselineObservation;
use serde_json::{Value, json};
use std::time::{Duration, Instant};

const OPEN_SECONDS: u64 = 250 + 3 * 15 + 250 + 250 + 2 * 15 + 70;
const FINISH_SECONDS: u64 = 250 + 70 + 250 + 70 + 60;

const NORMAL_OPEN_COMMANDS: u32 = 5;
const NORMAL_CLOSE_MIN_COMMANDS: u32 = 3;
const NORMAL_CLOSE_MAX_COMMANDS: u32 = 34;

pub(super) fn supports(package: &str) -> bool {
    collaboration::supports(package)
}
pub(super) fn window_seconds() -> u64 {
    2 * (OPEN_SECONDS + FINISH_SECONDS)
        + collaboration::additional_window_seconds()
        + permission_preservation_additional_window_seconds()
}
fn second_seconds() -> u64 {
    OPEN_SECONDS + FINISH_SECONDS + collaboration::second_business_seconds()
}
pub(super) fn retained_journal_members_bound() -> usize {
    let first = NORMAL_OPEN_COMMANDS
        + NORMAL_CLOSE_MAX_COMMANDS
        + collaboration::first_max_extra_ui_commands();
    let second =
        NORMAL_OPEN_COMMANDS + NORMAL_CLOSE_MAX_COMMANDS + collaboration::reopen_max_ui_commands();
    // Four command records each, sixteen fixed records for each actual
    // journal, thirteen scoped PNG/comparison pairs, and eight permission records.
    4 * (first + second) as usize + 2 * 16 + 13 * 2 + 8
}
fn need(ok: bool, why: &str) -> Result<(), String> {
    if ok { Ok(()) } else { Err(why.into()) }
}
fn first_end(now: Instant, ui_end: Instant) -> Result<Instant, String> {
    ui_end
        .checked_sub(Duration::from_secs(second_seconds()))
        .filter(|value| now < *value)
        .ok_or_else(|| {
            "collaboration original window cannot reserve its separate reopen and close".into()
        })
}
fn normal_history(
    transcript: &NativeUiTranscript,
    observed: (u32, u32),
    second: bool,
) -> Result<(), String> {
    let max = if second {
        collaboration::reopen_max_ui_commands()
    } else {
        collaboration::first_max_extra_ui_commands()
    };
    let action_max = if second {
        collaboration::reopen_max_actions()
    } else {
        collaboration::first_max_extra_actions()
    };
    let base = transcript
        .operations()
        .checked_sub(observed.0)
        .ok_or("collaboration commands exceed its actual finished history")?;
    need(
        observed.0 <= max
            && observed.1 <= action_max
            && (NORMAL_OPEN_COMMANDS + NORMAL_CLOSE_MIN_COMMANDS
                ..=NORMAL_OPEN_COMMANDS + NORMAL_CLOSE_MAX_COMMANDS)
                .contains(&base)
            && transcript.actions() == observed.1 + 1,
        "collaboration requires its exact bounded business sequence and one normal owned task removal",
    )
}
fn failed_close(
    session: NativeUiSession<'_, '_>,
    inspector: &mut NativeApplicationInspector,
    original: String,
) -> String {
    match session.finish(inspector) {
        Ok(_) => {
            format!(
                "{original}; failed collaboration execution retained; normal owned close completed"
            )
        }
        Err(error) => format!(
            "{original}; failed collaboration execution retained; normal finish also failed: {error}"
        ),
    }
}

/// Only run() creates this in-process history. Comparison JSON has no factory.
pub(super) struct CollaborationCaseObservation {
    first: RetainedNativeUiTranscript,
    reopened: Option<RetainedNativeUiTranscript>,
    execution: collaboration::CollaborationExecution,
    permissions: NativeUiPermissionPreservation,
}
impl CollaborationCaseObservation {
    pub(super) fn completed_gates(&self) -> Vec<&'static str> {
        self.execution.completed_gates()
    }
    pub(super) fn permissions(&self) -> &NativeUiPermissionPreservation {
        &self.permissions
    }
    pub(super) fn require_subject(
        &self,
        main: &RuntimeMainCustody,
        application: &ApplicationInspection,
    ) -> Result<(), String> {
        self.first.require_subject(main, application)?;
        if let Some(next) = &self.reopened {
            next.require_subject(main, application)?;
        }
        self.permissions.require_subject(main, application)?;
        self.guard_immutable()
    }
    pub(super) fn guard_immutable(&self) -> Result<(), String> {
        self.first.guard_immutable()?;
        let first = self.first.transcript();
        need(
            supports(&first.engine().application().package),
            "collaboration history is outside the one compiled original source contract",
        )?;
        normal_history(first, self.execution.first_counts(), false)?;
        match (&self.reopened, self.execution.reopened_counts()) {
            (Some(next), Some(counts)) => {
                next.guard_immutable()?;
                normal_history(next.transcript(), counts, true)?;
                self.permissions.require_pair(first, next.transcript())?;
            }
            (None, None) => self.permissions.require_transcript(first)?,
            _ => {
                return Err(
                    "collaboration second execution lacks its actual retained second history"
                        .into(),
                );
            }
        }
        self.execution.guard_immutable(
            first,
            self.reopened.as_ref().map(|value| value.transcript()),
        )?;
        need(
            self.execution.target_owned_accounts()
                == self.permissions.target_owned_account_count()?,
            "collaboration target account scope differs from its actual retained before/after window",
        )?;
        let complete = self.completed_gates();
        need(
            complete.iter().all(|gate| {
                [
                    "collaboration.account",
                    "collaboration.navigation",
                    "collaboration.search",
                    "collaboration.documents",
                ]
                .contains(gate)
            }) && complete
                .iter()
                .collect::<std::collections::BTreeSet<_>>()
                .len()
                == complete.len(),
            "collaboration executor cannot infer draft or recovery acceptance",
        )
    }
    pub(super) fn comparison(&self) -> Result<Value, String> {
        self.guard_immutable()?;
        Ok(json!({
            "schema":"droidloom.native-collaboration-business-case.v1",
            "first":self.first.comparison()?,
            "reopened":self.reopened.as_ref().map(|value|value.comparison()).transpose()?,
            "execution":self.execution.comparison()?,
            "pm_permission_preservation":self.permissions.comparison()?,
            "source_window_seconds":window_seconds(),
            "source_maximum_retained_journal_members":retained_journal_members_bound(),
            "account_or_complete_data_acceptance_inferred":false,
            "runtime_qualified":false,"production_ready":false,"comparison_only":true
        }))
    }
}

/// The caller's original family end bounds the independent fixed collaboration window.
/// Unused common time never increases this factory's own fixed maximum.
pub(super) fn run(
    inspector: &mut NativeApplicationInspector,
    baseline: &mut NativeLeafBaselineObservation<'_>,
    fixture: Option<&droidloom_supervisor::working_qualification::FeishuReadonlyFixture>,
    original_end: Instant,
) -> Result<CollaborationCaseObservation, String> {
    let now = Instant::now();
    let application = baseline.application().clone();
    let main = baseline.main().facts().clone();
    collaboration::require_application(&application)?;
    need(
        supports(&application.package)
            && now < original_end
            && original_end <= baseline.deadline()
            && original_end.duration_since(now) <= Duration::from_secs(window_seconds()),
        "collaboration needs its source-fixed package and bounded original baseline window",
    )?;
    let permission = NativeUiPermissionWindow::begin(inspector, baseline, original_end)?;
    let ui_end = permission.ui_deadline();
    let observed = (|| {
        let first_deadline = first_end(Instant::now(), ui_end)?;
        let mut session = NativeUiSession::open(inspector, baseline, first_deadline)?;
        let mut execution = match collaboration::run(
            &mut session,
            inspector,
            &permission,
            &main,
            &application,
            fixture,
            ui_end,
        ) {
            Ok(value) => value,
            Err(error) => return Err(failed_close(session, inspector, error)),
        };
        let first = session.finish(inspector)?.into_retained()?;
        first.require_subject(&main, &application)?;
        normal_history(first.transcript(), execution.first_counts(), false)?;
        let reopened = if execution.should_reopen() {
            let mut next = NativeUiSession::open(inspector, baseline, ui_end)?;
            if let Err(error) =
                execution.observe_reopen(&mut next, inspector, first.transcript(), ui_end)
            {
                return Err(failed_close(next, inspector, error));
            }
            let finished = next.finish(inspector)?.into_retained()?;
            finished.require_subject(&main, &application)?;
            Some(finished)
        } else {
            None
        };
        execution.guard_immutable(
            first.transcript(),
            reopened.as_ref().map(|value| value.transcript()),
        )?;
        Ok::<_, String>((first, reopened, execution))
    })();
    let (first, reopened, execution) = match observed {
        Ok(value) => value,
        Err(error) => return Err(permission.fail(error)),
    };
    let permissions = match &reopened {
        Some(next) => {
            permission.finish_pair(inspector, baseline, first.transcript(), next.transcript())?
        }
        None => permission.finish(inspector, baseline, first.transcript())?,
    };
    let result = CollaborationCaseObservation {
        first,
        reopened,
        execution,
        permissions,
    };
    result.require_subject(&main, &application)?;
    need(
        Instant::now() < original_end,
        "collaboration sealing exceeded its original window",
    )?;
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn collaboration_separate_business_pair_has_bounded_commands_and_unchanged_common_reserve() {
        assert_eq!(OPEN_SECONDS, 895);
        assert_eq!(FINISH_SECONDS, 700);
        assert_eq!(second_seconds(), 1965);
        assert_eq!(window_seconds(), 10320);
        assert_eq!(retained_journal_members_bound(), 1282);
        let now = Instant::now();
        let end = now + Duration::from_secs(5810);
        assert_eq!(
            first_end(now, end).unwrap(),
            end - Duration::from_secs(1965)
        );
        assert_eq!(
            first_end(now + Duration::from_secs(1), end).unwrap(),
            first_end(now, end).unwrap()
        );
        assert!(first_end(now, now + Duration::from_secs(1965)).is_err());
        assert!(first_end(end, end).is_err());
    }
}
