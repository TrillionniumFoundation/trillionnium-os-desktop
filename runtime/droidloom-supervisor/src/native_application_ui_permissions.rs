//! Actual before/open/normal-close/after PM, AppOps and account custody for one bounded UI case with one session or a genuine close/reopen pair.
//!
//! The only constructor borrows the admitted Inspector and original Main/PM
//! objects. Complete user-zero PM permissions, scoped AppOps modes and registered-account samples
//! enclose the real session and its normal close/bookends. This partial evidence
//! does not prove credentials, login state, persistent application data or a complete gate.
use super::*;
use super::common::{JournalKind, RetainedJournal};
use crate::control::{ActualApplicationPermissionObservation, ActualApplicationAppOpsObservation, ActualApplicationAccountObservation, application_probe::ApplicationInspection};

const QUERY_CAP: Duration = Duration::from_secs(70);
const APPOPS_QUERY_CAP: Duration = Duration::from_secs(70);
const ACCOUNT_QUERY_CAP: Duration = Duration::from_secs(70);
const AFTER_RESERVE: Duration = Duration::from_secs(
    QUERY_CAP.as_secs() + APPOPS_QUERY_CAP.as_secs() + ACCOUNT_QUERY_CAP.as_secs());
const RECORD_BOUND: usize = crate::application_permission_state::MAX_WIRE_BYTES;
const _: () = assert!(RECORD_BOUND == crate::application_appops_state::MAX_WIRE_BYTES);
const _: () = assert!(RECORD_BOUND == crate::application_account_state::MAX_WIRE_BYTES);
const BEGIN: &str = "PERMISSION-BEGIN.json";
const BEFORE: &str = "PERMISSION-BEFORE.json";
const AFTER: &str = "PERMISSION-AFTER.json";
const COMPLETE: &str = "PERMISSION-COMPLETE.json";
const APPOPS_BEFORE: &str = "APPOPS-BEFORE.json";
const APPOPS_AFTER: &str = "APPOPS-AFTER.json";
const ACCOUNT_BEFORE: &str = "ACCOUNT-BEFORE.json";
const ACCOUNT_AFTER: &str = "ACCOUNT-AFTER.json";
type GeneratedRecords = BTreeMap<String, (u64, String)>;

/// Two fixed queries for each of PM, AppOps and registered accounts. This function
/// allocates no lease and never extends a caller's original deadline.
pub fn permission_preservation_additional_window_seconds() -> u64 {
    2 * (QUERY_CAP.as_secs() + APPOPS_QUERY_CAP.as_secs() + ACCOUNT_QUERY_CAP.as_secs())
}

fn ui_deadline(now: Instant, original_end: Instant, baseline_end: Instant) -> Result<Instant, String> {
    need(now < original_end && original_end <= baseline_end,
        "PM/AppOps/account permission window is outside its original baseline deadline")?;
    let cutoff = original_end.checked_sub(AFTER_RESERVE)
        .filter(|end| end.saturating_duration_since(now) > AFTER_RESERVE)
        .ok_or("PM/AppOps/account permission window cannot fit all six fixed queries and actual UI work")?;
    Ok(cutoff)
}

fn require_order(
    started: Instant, before_at: Instant, opened_at: Instant, finished_at: Instant,
    after_at: Instant, session_end: Instant, ui_end: Instant, original_end: Instant,
) -> Result<(), String> {
    need(started <= before_at && before_at < opened_at && opened_at < finished_at
        && finished_at < session_end && finished_at < after_at && after_at < original_end
        && session_end <= ui_end && ui_end.checked_add(AFTER_RESERVE) == Some(original_end),
        "PM/AppOps/account permission samples do not enclose this actual finished UI session under the original end")
}

fn require_appops_order(
    pm_before: Instant, appops_before: Instant, opened: Instant, finished: Instant,
    appops_after: Instant, pm_after: Instant,
) -> Result<(), String> {
    need(pm_before < appops_before && appops_before < opened
        && finished < appops_after && appops_after < pm_after,
        "AppOps samples must enclose the same actual UI lifetime inside the PM samples")
}

fn require_account_order(
    appops_before: Instant, account_before: Instant, opened: Instant, finished: Instant,
    account_after: Instant, appops_after: Instant,
) -> Result<(), String> {
    need(appops_before < account_before && account_before < opened
        && finished < account_after && account_after < appops_after,
        "registered account samples must enclose the same actual UI inside the AppOps samples")
}

fn offset_nanos(started: Instant, at: Instant) -> Result<u64, String> {
    at.checked_duration_since(started)
        .and_then(|v| u64::try_from(v.as_nanos()).ok())
        .ok_or_else(|| "PM/AppOps/account permission monotonic observation interval differs".into())
}

fn write_record(
    journal: &Journal, generated: &mut GeneratedRecords, name: &'static str, value: &impl Serialize,
) -> Result<(), String> {
    need([BEGIN, BEFORE, APPOPS_BEFORE, ACCOUNT_BEFORE, ACCOUNT_AFTER, APPOPS_AFTER, AFTER, COMPLETE].contains(&name) && !generated.contains_key(name),
        "PM/AppOps/account permission record is not a unique source-owned member")?;
    let bytes = serde_json::to_vec(value).map_err(|e| e.to_string())?;
    need(!bytes.is_empty() && bytes.len() <= RECORD_BOUND,
        "PM/AppOps/account permission record exceeds its fixed complete bound")?;
    journal.write(name, &bytes)?;
    generated.insert(name.into(), (bytes.len() as u64, format!("{:x}", Sha256::digest(&bytes))));
    Ok(())
}

fn failure(journal: &Journal, error: String) -> String {
    // Diagnostics cannot construct success. A failed or abandoned window
    // keeps its original records; it never retries a query or an Android action.
    let diagnostic: String = error.chars().take(4096).collect();
    let record = serde_json::json!({
        "schema":"droidloom.native-ui-pm-permission-failed.v3",
        "error":diagnostic,"diagnostic_truncated":diagnostic.len()!=error.len(),
        "permission_preservation_observed":false,
        "automatic_retry":false,"complete_data_permissions_accepted":false
    });
    match journal.json("PERMISSION-FAILED.json", &record) {
        Ok(()) => format!("{error}; PM/AppOps/account permission failure retained at {}", journal.path.display()),
        Err(record_error) => format!("{error}; PM/AppOps/account permission failure record also failed: {record_error}; original journal {}", journal.path.display()),
    }
}

/// The real UI transcript's private birth/finish and held journal identity.
/// These fields are copied only from a successful NativeUiSession constructor.
struct UiBoundary {
    journal: PathBuf,
    journal_identity: [u64; 5],
    task: u32,
    opened_at: Instant,
    finished_at: Instant,
    end: Instant,
}
impl UiBoundary {
    fn capture(transcript: &NativeUiTranscript) -> Result<Self, String> {
        transcript.journal_custody.verify()?;
        Ok(Self {
            journal:transcript.path.clone(), journal_identity:transcript.journal_custody.identity,
            task:transcript.task, opened_at:transcript.opened_at, finished_at:transcript.finished_at,
            end:transcript.original_end,
        })
    }
    fn require_transcript(&self, transcript: &NativeUiTranscript) -> Result<(), String> {
        need(self.journal == transcript.path && self.journal_identity == transcript.journal_custody.identity
            && self.task == transcript.task && self.opened_at == transcript.opened_at
            && self.finished_at == transcript.finished_at && self.end == transcript.original_end,
            "PM/AppOps/account permission custody belongs to another actual UI task, journal or lifetime")?;
        transcript.journal_custody.verify()
    }
}


/// One source-owned interval around either one actual session or the actual
/// first/closed/reopened pair. No transcript or comparison JSON constructor is
/// exposed; a pair cannot be accepted through the single-session interface.
struct UiInterval {
    first: UiBoundary,
    reopened: Option<UiBoundary>,
}
impl UiInterval {
    fn capture(
        first: &NativeUiTranscript, reopened: Option<&NativeUiTranscript>,
        main: &RuntimeMainCustody, application: &ApplicationInspection, ui_end: Instant,
    ) -> Result<Self, String> {
        for transcript in std::iter::once(first).chain(reopened) {
            need(&transcript.engine().facts().main == main
                && transcript.engine().application() == application,
                "each actual UI session must retain the original complete Main and PM identity")?;
        }
        let result = Self {
            first: UiBoundary::capture(first)?,
            reopened: reopened.map(UiBoundary::capture).transpose()?,
        };
        result.require_shape(ui_end)?;
        Ok(result)
    }
    fn require_shape(&self, ui_end: Instant) -> Result<(), String> {
        for boundary in std::iter::once(&self.first).chain(self.reopened.as_ref()) {
            need(boundary.opened_at < boundary.finished_at && boundary.finished_at < boundary.end
                && boundary.end <= ui_end,
                "actual UI session is unfinished or exceeds the original shared UI cutoff")?;
        }
        if let Some(reopened) = &self.reopened {
            need(self.first.task != reopened.task && self.first.journal != reopened.journal
                && self.first.journal_identity[..2] != reopened.journal_identity[..2]
                && self.first.finished_at < reopened.opened_at,
                "actual reopened session must follow the first normal close with a distinct task and held journal")?;
        }
        Ok(())
    }
    fn opened_at(&self) -> Instant { self.first.opened_at }
    fn finished_at(&self) -> Instant { self.last().finished_at }
    fn end(&self) -> Instant { self.last().end }
    fn last(&self) -> &UiBoundary { self.reopened.as_ref().unwrap_or(&self.first) }
    fn require_transcripts(
        &self, first: &NativeUiTranscript, reopened: Option<&NativeUiTranscript>,
    ) -> Result<(), String> {
        self.first.require_transcript(first)?;
        match (&self.reopened, reopened) {
            (None, None) => Ok(()),
            (Some(boundary), Some(transcript)) => boundary.require_transcript(transcript),
            _ => Err("single-session and close/reopen preservation interfaces cannot substitute for each other".into()),
        }
    }
    fn comparison(&self, started: Instant) -> Result<Vec<Value>, String> {
        std::iter::once(&self.first).chain(self.reopened.as_ref()).enumerate().map(|(index, boundary)| {
            Ok(serde_json::json!({
                "session_index":index, "task":boundary.task,
                "journal":boundary.journal, "journal_identity":boundary.journal_identity,
                "opened_nanoseconds":offset_nanos(started,boundary.opened_at)?,
                "finished_nanoseconds":offset_nanos(started,boundary.finished_at)?,
                "original_end_nanoseconds":offset_nanos(started,boundary.end)?
            }))
        }).collect()
    }
}

/// Source-created live recorder. No public fields, Clone or Deserialize exist.
/// A caller cannot supply a permission table, a passed flag or a receipt.
pub struct NativeUiPermissionWindow {
    main: RuntimeMainCustody,
    application: ApplicationInspection,
    started: Instant,
    end: Instant,
    ui_end: Instant,
    journal: Journal,
    generated: GeneratedRecords,
    before: ActualApplicationPermissionObservation,
    before_appops: ActualApplicationAppOpsObservation,
    before_account: ActualApplicationAccountObservation,
}
impl NativeUiPermissionWindow {
    pub fn begin(
        inspector: &mut NativeApplicationInspector,
        baseline: &NativeLeafBaselineObservation<'_>,
        original_end: Instant,
    ) -> Result<Self, String> {
        let started = Instant::now();
        let ui_end = ui_deadline(started, original_end, baseline.deadline())?;
        baseline.verify_local(inspector, original_end).map_err(|e| e.to_string())?;
        let main = baseline.main().facts().clone();
        let application = baseline.application().clone();
        let journal = Journal::create()?;
        let mut generated = GeneratedRecords::new();
        let observed = (|| {
            write_record(&journal, &mut generated, BEGIN, &serde_json::json!({
                "schema":"droidloom.native-ui-pm-permission-begin.v3",
                "main":main,"application":application,"fixed_queries":6,
                "pm_queries":2,"appops_queries":2,"registered_account_queries":2,
                "original_remaining_nanoseconds":offset_nanos(started, original_end)?,
                "ui_cutoff_nanoseconds":offset_nanos(started, ui_end)?,
                "automatic_retry":false,"comparison_documents_create_authority":false
            }))?;
            let observation = inspector.observe_application_permission_state_until(
                baseline.main(), baseline.actual_application(), ui_end,
            ).map_err(|e| e.to_string())?;
            inspector.require_permission_state_local(
                baseline.main(), baseline.actual_application(), &observation, ui_end,
            ).map_err(|e| e.to_string())?;
            observation.facts().require_application(&application)?;
            write_record(&journal, &mut generated, BEFORE, observation.facts())?;
            let appops = inspector.observe_application_appops_state_until(
                baseline.main(), baseline.actual_application(), ui_end,
            ).map_err(|e| e.to_string())?;
            inspector.require_appops_state_local(
                baseline.main(), baseline.actual_application(), &appops, ui_end,
            ).map_err(|e| e.to_string())?;
            appops.facts().require_application(&application)?;
            need(observation.observed_at() < appops.observed_at(),
                "PM/AppOps/account pre-observations did not follow the fixed query order")?;
            write_record(&journal, &mut generated, APPOPS_BEFORE, appops.facts())?;
            // Both actual account tokens retain this same original case end.
            // The fixed 70-second request plus the separate UI cutoff still
            // bounds pre-observation; no time or peer lease is renewed.
            need(ui_end.saturating_duration_since(Instant::now()) >= ACCOUNT_QUERY_CAP,
                "original pre-UI window cannot fit the fixed account request")?;
            let account = inspector.observe_application_account_state_until(
                baseline.main(), baseline.actual_application(), original_end,
            ).map_err(|e| e.to_string())?;
            inspector.require_account_state_local(
                baseline.main(), baseline.actual_application(), &account, original_end,
            ).map_err(|e| e.to_string())?;
            account.facts().require_application(&application)?;
            need(appops.observed_at() < account.observed_at(),
                "registered account pre-observation did not follow AppOps")?;
            write_record(&journal, &mut generated, ACCOUNT_BEFORE, account.facts())?;
            before(ui_end)?;
            Ok::<_, String>((observation, appops, account))
        })();
        let (observed, before_appops, before_account) = match observed {
            Ok(value) => value,
            Err(error) => return Err(failure(&journal, error)),
        };
        Ok(Self { main, application, started, end:original_end, ui_end,
            journal, generated, before:observed, before_appops, before_account })
    }

    /// The original end minus all three fixed after-query reserves. The normal
    /// session may choose an earlier source bound, never a later one.
    pub fn ui_deadline(&self) -> Instant { self.ui_end }

    /// Retain the real UI failure without retrying, claiming normal close or
    /// manufacturing a permission result. The original error remains primary.
    pub fn fail(self, error: String) -> String { failure(&self.journal, error) }

    pub fn finish(
        self,
        inspector: &mut NativeApplicationInspector,
        baseline: &NativeLeafBaselineObservation<'_>,
        transcript: &NativeUiTranscript,
    ) -> Result<NativeUiPermissionPreservation, String> {
        self.finish_sessions(inspector, baseline, transcript, None)
    }

    /// One original window encloses both actual sessions and both normal closes.
    /// No query is repeated between sessions and no later end is minted.
    pub fn finish_pair(
        self,
        inspector: &mut NativeApplicationInspector,
        baseline: &NativeLeafBaselineObservation<'_>,
        first: &NativeUiTranscript,
        reopened: &NativeUiTranscript,
    ) -> Result<NativeUiPermissionPreservation, String> {
        self.finish_sessions(inspector, baseline, first, Some(reopened))
    }

    fn finish_sessions(
        mut self,
        inspector: &mut NativeApplicationInspector,
        baseline: &NativeLeafBaselineObservation<'_>,
        transcript: &NativeUiTranscript,
        reopened: Option<&NativeUiTranscript>,
    ) -> Result<NativeUiPermissionPreservation, String> {
        let (after, after_appops, after_account, ui, retained) = match self.finish_inner(inspector, baseline, transcript, reopened) {
            Ok(value) => value,
            Err(error) => return Err(failure(&self.journal, error)),
        };
        let result = NativeUiPermissionPreservation {
            main:self.main, application:self.application, started:self.started, end:self.end,
            ui_end:self.ui_end, before:self.before, before_appops:self.before_appops,
            before_account:self.before_account, after, after_appops, after_account, ui,
            journal:self.journal, generated:self.generated, retained,
        };
        if let Err(error) = result.require_sessions(transcript, reopened).and_then(|_| before(result.end)) {
            return Err(failure(&result.journal, error));
        }
        Ok(result)
    }

    fn finish_inner(
        &mut self,
        inspector: &mut NativeApplicationInspector,
        baseline: &NativeLeafBaselineObservation<'_>,
        transcript: &NativeUiTranscript,
        reopened: Option<&NativeUiTranscript>,
    ) -> Result<(ActualApplicationPermissionObservation, ActualApplicationAppOpsObservation, ActualApplicationAccountObservation, UiInterval, RetainedJournal), String> {
        before(self.end)?;
        need(self.end <= baseline.deadline() && baseline.main().facts() == &self.main
            && baseline.application() == &self.application,
            "PM/AppOps/account permission window lost its original complete Main or installed application")?;
        baseline.verify_local(inspector, self.end).map_err(|e| e.to_string())?;
        inspector.require_permission_state_local(
            baseline.main(), baseline.actual_application(), &self.before, self.end,
        ).map_err(|e| e.to_string())?;
        inspector.require_appops_state_local(
            baseline.main(), baseline.actual_application(), &self.before_appops, self.end,
        ).map_err(|e| e.to_string())?;
        inspector.require_account_state_local(
            baseline.main(), baseline.actual_application(), &self.before_account, self.end,
        ).map_err(|e| e.to_string())?;
        let ui = UiInterval::capture(transcript, reopened, &self.main, &self.application, self.ui_end)?;
        // Reject a saved or earlier session before issuing any after-query.
        need(self.before.observed_at() < self.before_appops.observed_at()
            && self.before_appops.observed_at() < self.before_account.observed_at()
            && self.before_account.observed_at() < ui.opened_at() && ui.opened_at() < ui.finished_at()
            && ui.finished_at() < ui.end() && ui.end() <= self.ui_end && ui.finished_at() < Instant::now(),
            "PM/AppOps/account permission post-query requires the fresh normal close from this window")?;
        let after_account = inspector.observe_application_account_state_until(
            baseline.main(), baseline.actual_application(), self.end,
        ).map_err(|e| e.to_string())?;
        inspector.require_account_state_local(
            baseline.main(), baseline.actual_application(), &after_account, self.end,
        ).map_err(|e| e.to_string())?;
        after_account.facts().require_application(&self.application)?;
        write_record(&self.journal, &mut self.generated, ACCOUNT_AFTER, after_account.facts())?;
        let after_appops = inspector.observe_application_appops_state_until(
            baseline.main(), baseline.actual_application(), self.end,
        ).map_err(|e| e.to_string())?;
        inspector.require_appops_state_local(
            baseline.main(), baseline.actual_application(), &after_appops, self.end,
        ).map_err(|e| e.to_string())?;
        after_appops.facts().require_application(&self.application)?;
        write_record(&self.journal, &mut self.generated, APPOPS_AFTER, after_appops.facts())?;
        let after = inspector.observe_application_permission_state_until(
            baseline.main(), baseline.actual_application(), self.end,
        ).map_err(|e| e.to_string())?;
        inspector.require_permission_state_local(
            baseline.main(), baseline.actual_application(), &after, self.end,
        ).map_err(|e| e.to_string())?;
        after.facts().require_application(&self.application)?;
        // Preserve the actual differing after table before refusing a result.
        write_record(&self.journal, &mut self.generated, AFTER, after.facts())?;
        require_order(self.started, self.before.observed_at(), ui.opened_at(), ui.finished_at(),
            after.observed_at(), ui.end(), self.ui_end, self.end)?;
        require_appops_order(self.before.observed_at(), self.before_appops.observed_at(),
            ui.opened_at(), ui.finished_at(), after_appops.observed_at(), after.observed_at())?;
        require_account_order(self.before_appops.observed_at(), self.before_account.observed_at(),
            ui.opened_at(), ui.finished_at(), after_account.observed_at(), after_appops.observed_at())?;
        self.before.facts().same_permissions(after.facts())?;
        self.before_appops.facts().same_modes(after_appops.facts())?;
        inspector.require_account_state_pair_local(
            baseline.main(), baseline.actual_application(), &self.before_account, &after_account, self.end,
        ).map_err(|e| e.to_string())?;
        write_record(&self.journal, &mut self.generated, COMPLETE, &serde_json::json!({
            "schema":"droidloom.native-ui-pm-permission-complete.v3",
            "application":self.application,
            "main_sha256":format!("{:x}",Sha256::digest(serde_json::to_vec(&self.main).map_err(|e|e.to_string())?)),
            "ui_journal":ui.first.journal,"ui_journal_identity":ui.first.journal_identity,"task":ui.first.task,
            "ui_sessions":ui.comparison(self.started)?,
            "normal_closed_ui_sessions":if ui.reopened.is_some() {2} else {1},
            "before_nanoseconds":offset_nanos(self.started,self.before.observed_at())?,
            "opened_nanoseconds":offset_nanos(self.started,ui.opened_at())?,
            "finished_nanoseconds":offset_nanos(self.started,ui.finished_at())?,
            "after_nanoseconds":offset_nanos(self.started,after.observed_at())?,
            "appops_before_nanoseconds":offset_nanos(self.started,self.before_appops.observed_at())?,
            "appops_after_nanoseconds":offset_nanos(self.started,after_appops.observed_at())?,
            "appops_before_state_sha256":self.before_appops.facts().state_sha256(),
            "appops_after_state_sha256":after_appops.facts().state_sha256(),
            "appops_before_stdout_sha256":self.before_appops.facts().stdout_sha256(),
            "appops_after_stdout_sha256":after_appops.facts().stdout_sha256(),
            "account_before_nanoseconds":offset_nanos(self.started,self.before_account.observed_at())?,
            "account_after_nanoseconds":offset_nanos(self.started,after_account.observed_at())?,
            "account_before_state_sha256":self.before_account.facts().state_sha256(),
            "account_after_state_sha256":after_account.facts().state_sha256(),
            "account_before_stdout_sha256":self.before_account.facts().stdout_sha256(),
            "account_after_stdout_sha256":after_account.facts().stdout_sha256(),
            "before_state_sha256":self.before.facts().state_sha256(),
            "after_state_sha256":after.facts().state_sha256(),
            "before_stdout_sha256":self.before.facts().stdout_sha256(),
            "after_stdout_sha256":after.facts().stdout_sha256(),
            "pm_requested_install_runtime_and_shared_uid_unchanged":true,
            "appops_defaults_uid_and_package_modes_unchanged":true,
            "registered_accounts_authenticators_and_target_visibility_unchanged":true,
            "normal_owned_close_and_bookends_completed":true,
            "complete_data_permissions_or_accounts_accepted":false,
            "query_receipts_compared_for_equality":false,
            "automatic_retry":false,"original_deadline_extended":false
        }))?;
        let retained = RetainedJournal::capture(&self.journal, self.end, JournalKind::Permissions)?;
        retained.require_generated_permission_records(&self.generated)?;
        ui.require_transcripts(transcript, reopened)?;
        before(self.end)?;
        Ok((after, after_appops, after_account, ui, retained))
    }
}

/// Immutable historical PM/AppOps/account preservation, sealed before the original end.
/// The full tables/actual query retirements and every generated record remain
/// held. Historical guarding does not renew a lease or assert later liveness.
pub struct NativeUiPermissionPreservation {
    main: RuntimeMainCustody,
    application: ApplicationInspection,
    started: Instant,
    end: Instant,
    ui_end: Instant,
    before: ActualApplicationPermissionObservation,
    before_appops: ActualApplicationAppOpsObservation,
    before_account: ActualApplicationAccountObservation,
    after: ActualApplicationPermissionObservation,
    after_appops: ActualApplicationAppOpsObservation,
    after_account: ActualApplicationAccountObservation,
    ui: UiInterval,
    journal: Journal,
    generated: GeneratedRecords,
    retained: RetainedJournal,
}
impl NativeUiPermissionPreservation {
    pub fn require_subject(
        &self, main: &RuntimeMainCustody, application: &ApplicationInspection,
    ) -> Result<(), String> {
        need(&self.main == main && &self.application == application,
            "PM/AppOps/account permission preservation belongs to another actual Main or complete PM identity")?;
        self.guard_immutable()
    }
    pub fn require_transcript(&self, transcript: &NativeUiTranscript) -> Result<(), String> {
        self.require_sessions(transcript, None)
    }
    pub fn require_pair(
        &self, first: &NativeUiTranscript, reopened: &NativeUiTranscript,
    ) -> Result<(), String> {
        self.require_sessions(first, Some(reopened))
    }
    fn require_sessions(
        &self, first: &NativeUiTranscript, reopened: Option<&NativeUiTranscript>,
    ) -> Result<(), String> {
        self.ui.require_transcripts(first, reopened)?;
        for transcript in std::iter::once(first).chain(reopened) {
            need(transcript.engine().facts().main == self.main
                && transcript.engine().application() == &self.application,
                "preserved UI sessions differ from the original complete Main or PM identity")?;
        }
        self.guard_immutable()
    }
    pub fn guard_immutable(&self) -> Result<(), String> {
        self.ui.require_shape(self.ui_end)?;
        self.before.facts().require_application(&self.application)?;
        self.after.facts().require_application(&self.application)?;
        self.before.facts().same_permissions(self.after.facts())?;
        self.before_appops.facts().require_application(&self.application)?;
        self.after_appops.facts().require_application(&self.application)?;
        self.before_appops.facts().same_modes(self.after_appops.facts())?;
        self.before_account.facts().require_application(&self.application)?;
        self.after_account.facts().require_application(&self.application)?;
        self.before_account.facts().same_registered_accounts(self.after_account.facts())?;
        require_account_order(self.before_appops.observed_at(), self.before_account.observed_at(),
            self.ui.opened_at(), self.ui.finished_at(), self.after_account.observed_at(),
            self.after_appops.observed_at())?;
        require_appops_order(self.before.observed_at(), self.before_appops.observed_at(),
            self.ui.opened_at(), self.ui.finished_at(), self.after_appops.observed_at(),
            self.after.observed_at())?;
        require_order(self.started, self.before.observed_at(), self.ui.opened_at(), self.ui.finished_at(),
            self.after.observed_at(), self.ui.end(), self.ui_end, self.end)?;
        self.retained.guard(&self.journal)?;
        self.retained.require_generated_permission_records(&self.generated)
    }
    pub fn comparison(&self) -> Result<Value, String> {
        self.guard_immutable()?;
        // Full tables are retained in their eight private records. Duplicating
        // them for 31 histories would unnecessarily enlarge the capture frame.
        let records = self.generated.iter().map(|(name, (bytes, sha256))|
            serde_json::json!({"name":name,"bytes":bytes,"sha256":sha256})).collect::<Vec<_>>();
        // Construct bounded sections so added account evidence does not exceed
        // serde_json's macro recursion limit. The externally visible flat
        // object retains every original field and rejects duplicate keys.
        let mut comparison = serde_json::Map::new();
        for section in [
            serde_json::json!({
                "schema":"droidloom.native-ui-pm-permission-preservation.v3",
                "package":self.application.package,"uid":self.application.uid,"epoch":self.application.epoch,
                "main_sha256":format!("{:x}",Sha256::digest(serde_json::to_vec(&self.main).map_err(|e|e.to_string())?)),
                "application_sha256":format!("{:x}",Sha256::digest(serde_json::to_vec(&self.application).map_err(|e|e.to_string())?)),
                "ui_task":self.ui.first.task,"ui_journal":self.ui.first.journal,"ui_journal_identity":self.ui.first.journal_identity,
                "ui_sessions":self.ui.comparison(self.started)?,
                "normal_closed_ui_sessions":if self.ui.reopened.is_some() {2} else {1},
                "permission_journal":self.journal.path,"permission_journal_identity":self.journal.identity,
                "records":records,
                "before_state_sha256":self.before.facts().state_sha256(),
                "after_state_sha256":self.after.facts().state_sha256(),
                "before_stdout_sha256":self.before.facts().stdout_sha256(),
                "after_stdout_sha256":self.after.facts().stdout_sha256(),
                "before_nanoseconds":offset_nanos(self.started,self.before.observed_at())?,
                "opened_nanoseconds":offset_nanos(self.started,self.ui.opened_at())?,
                "finished_nanoseconds":offset_nanos(self.started,self.ui.finished_at())?,
                "after_nanoseconds":offset_nanos(self.started,self.after.observed_at())?
            }),
            serde_json::json!({
                "appops_before_nanoseconds":offset_nanos(self.started,self.before_appops.observed_at())?,
                "appops_after_nanoseconds":offset_nanos(self.started,self.after_appops.observed_at())?,
                "appops_before_state_sha256":self.before_appops.facts().state_sha256(),
                "appops_after_state_sha256":self.after_appops.facts().state_sha256(),
                "appops_before_stdout_sha256":self.before_appops.facts().stdout_sha256(),
                "appops_after_stdout_sha256":self.after_appops.facts().stdout_sha256(),
                "account_before_nanoseconds":offset_nanos(self.started,self.before_account.observed_at())?,
                "account_after_nanoseconds":offset_nanos(self.started,self.after_account.observed_at())?,
                "account_before_state_sha256":self.before_account.facts().state_sha256(),
                "account_after_state_sha256":self.after_account.facts().state_sha256(),
                "account_before_stdout_sha256":self.before_account.facts().stdout_sha256(),
                "account_after_stdout_sha256":self.after_account.facts().stdout_sha256(),
                "pm_requested_install_runtime_and_shared_uid_unchanged":true,
                "appops_defaults_uid_and_package_modes_unchanged":true,
                "registered_accounts_authenticators_and_target_visibility_unchanged":true,
                "normal_owned_close_and_full_bookends_completed":true,
                "actual_queries_retired":true,"retained_source_result_fds":true,
                "live_execution_authority_retained":false,"query_receipt_equality_required":false,
                "complete_data_permissions_or_accounts_accepted":false,
                "persistent_data_or_accounts_acceptance_inferred":false,
                "automatic_retry":false,"original_deadline_extended":false
            }),
        ] {
            let Value::Object(fields) = section else {
                return Err("permission comparison section is not an object".into());
            };
            for (key, value) in fields {
                need(comparison.insert(key, value).is_none(),
                    "permission comparison contains a duplicate field")?;
            }
        }
        Ok(Value::Object(comparison))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pm_permission_window_reserves_six_real_queries_inside_the_original_end() {
        let now=Instant::now();
        let end=now+Duration::from_secs(3035);
        assert_eq!(permission_preservation_additional_window_seconds(),420);
        assert_eq!(ui_deadline(now,end,end).unwrap(),end-AFTER_RESERVE);
        assert!(ui_deadline(now,end,end-Duration::from_nanos(1)).is_err());
        assert!(ui_deadline(now,now,end).is_err());
        assert!(ui_deadline(now,now+2*AFTER_RESERVE,end).is_err());
        let epoch=crate::control::application_probe::RuntimeEpoch{
            boot_id:"11111111-1111-4111-8111-111111111111".into(),
            cell_host_pid:11,framework_host_pid:12,framework_start_ticks:13,
        };
        let pm=ControlRequest::ObserveApplicationPermissionState{
            package:"com.android.settings".into(), expected_epoch:epoch.clone(),
        };
        let appops=ControlRequest::ObserveApplicationAppOpsState{
            package:"com.android.settings".into(), expected_epoch:epoch.clone(),
        };
        let accounts=ControlRequest::ObserveApplicationAccountState{
            package:"com.android.settings".into(), expected_epoch:epoch,
        };
        assert_eq!(crate::control::progress::response_timeout(&accounts),ACCOUNT_QUERY_CAP);
        assert_eq!(crate::control::progress::response_timeout(&pm),QUERY_CAP);
        assert_eq!(crate::control::progress::response_timeout(&appops),APPOPS_QUERY_CAP);
    }


    #[test]
    fn pm_permission_window_pair_rejects_reused_tasks_journals_order_and_extended_cutoffs() {
        let base=Instant::now();
        let at=|seconds|base+Duration::from_secs(seconds);
        // These private comparator fixtures cannot construct an actual
        // transcript, permission observation or preservation result.
        let boundary=|task, inode, path:&str, open, finish, end|UiBoundary{
            journal:PathBuf::from(path),journal_identity:[1,inode,0o40700,1000,1000],
            task,opened_at:at(open),finished_at:at(finish),end:at(end),
        };
        let valid=UiInterval{
            first:boundary(11,101,"/first",1,2,30),
            reopened:Some(boundary(12,102,"/reopened",3,4,30)),
        };
        valid.require_shape(at(30)).unwrap();
        assert_eq!(valid.opened_at(),at(1));
        assert_eq!(valid.finished_at(),at(4));
        assert_eq!(valid.comparison(base).unwrap().len(),2);
        for (task,inode,path,open,finish,end) in [
            (11,102,"/reopened",3,4,30),
            (12,101,"/reopened",3,4,30),
            (12,102,"/first",3,4,30),
            (12,102,"/reopened",2,4,30),
            (12,102,"/reopened",1,4,30),
            (12,102,"/reopened",3,3,30),
            (12,102,"/reopened",3,30,30),
            (12,102,"/reopened",3,4,31),
        ] {
            let invalid=UiInterval{
                first:boundary(11,101,"/first",1,2,30),
                reopened:Some(boundary(task,inode,path,open,finish,end)),
            };
            assert!(invalid.require_shape(at(30)).is_err());
        }
        let invalid_first=UiInterval{
            first:boundary(11,101,"/first",1,2,31),
            reopened:Some(boundary(12,102,"/reopened",3,4,30)),
        };
        assert!(invalid_first.require_shape(at(30)).is_err());
        let single=UiInterval{first:boundary(11,101,"/first",1,2,30),reopened:None};
        single.require_shape(at(30)).unwrap();
        assert_eq!(single.comparison(base).unwrap().len(),1);
    }

    #[test]
    fn pm_permission_window_rejects_reused_sessions_early_after_samples_and_renewed_reserves() {
        let base=Instant::now();
        let at=|s|base+Duration::from_secs(s);
        require_order(base,at(1),at(2),at(3),at(4),at(30),at(30),at(240)).unwrap();
        for (pre,open,finish,post,session,ui,end) in [
            (2,2,3,4,30,30,240), (3,2,3,4,30,30,240), (1,3,3,4,30,30,240),
            (1,2,3,3,30,30,240), (1,2,3,2,30,30,240), (1,2,3,240,30,30,240),
            (1,2,30,31,30,30,240), (1,2,3,4,31,30,240), (1,2,3,4,30,31,240),
            (1,2,3,4,30,30,241),
        ] {
            assert!(require_order(base,at(pre),at(open),at(finish),at(post),at(session),at(ui),at(end)).is_err());
        }
        assert!(require_order(at(2),at(1),at(2),at(3),at(4),at(30),at(30),at(240)).is_err());
        require_appops_order(at(1),at(2),at(3),at(4),at(5),at(6)).unwrap();
        for (pm_pre,ops_pre,open,finish,ops_post,pm_post) in [
            (1,1,3,4,5,6), (2,1,3,4,5,6), (1,3,3,4,5,6),
            (1,4,3,4,5,6), (1,2,3,4,4,6), (1,2,3,4,3,6),
            (1,2,3,4,6,6), (1,2,3,4,7,6),
        ] {
            assert!(require_appops_order(at(pm_pre),at(ops_pre),at(open),at(finish),
                at(ops_post),at(pm_post)).is_err());
        }
        require_account_order(at(1),at(2),at(3),at(4),at(5),at(6)).unwrap();
        for (ops_pre,account_pre,open,finish,account_post,ops_post) in [
            (1,1,3,4,5,6), (2,1,3,4,5,6), (1,3,3,4,5,6),
            (1,4,3,4,5,6), (1,2,3,4,4,6), (1,2,3,4,3,6),
            (1,2,3,4,6,6), (1,2,3,4,7,6),
        ] {
            assert!(require_account_order(at(ops_pre),at(account_pre),at(open),at(finish),
                at(account_post),at(ops_post)).is_err());
        }
    }
}
