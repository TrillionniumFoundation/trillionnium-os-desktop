//! Actual before/open/normal-close/after PM-permission custody for one UI case.
//!
//! The only constructor borrows the admitted Inspector and original Main/PM
//! objects. It compares complete user-zero PM state, including a shared UID,
//! after the real session has closed and finished its normal bookends. It does
//! not prove AppOps, accounts, persistent application data or a complete gate.
use super::*;
use super::common::{JournalKind, RetainedJournal};
use crate::control::{ActualApplicationPermissionObservation, application_probe::ApplicationInspection};

const QUERY_CAP: Duration = Duration::from_secs(70);
const RECORD_BOUND: usize = crate::application_permission_state::MAX_WIRE_BYTES;
const BEGIN: &str = "PERMISSION-BEGIN.json";
const BEFORE: &str = "PERMISSION-BEFORE.json";
const AFTER: &str = "PERMISSION-AFTER.json";
const COMPLETE: &str = "PERMISSION-COMPLETE.json";
type GeneratedRecords = BTreeMap<String, (u64, String)>;

/// Exactly two existing fixed queries for each real window. This function
/// allocates no lease and never extends a caller's original deadline.
pub fn permission_preservation_additional_window_seconds() -> u64 {
    2 * QUERY_CAP.as_secs()
}

fn ui_deadline(now: Instant, original_end: Instant, baseline_end: Instant) -> Result<Instant, String> {
    need(now < original_end && original_end <= baseline_end,
        "PM permission window is outside its original baseline deadline")?;
    let cutoff = original_end.checked_sub(QUERY_CAP)
        .filter(|end| end.saturating_duration_since(now) > QUERY_CAP)
        .ok_or("PM permission window cannot fit both fixed queries and actual UI work")?;
    Ok(cutoff)
}

fn require_order(
    started: Instant, before_at: Instant, opened_at: Instant, finished_at: Instant,
    after_at: Instant, session_end: Instant, ui_end: Instant, original_end: Instant,
) -> Result<(), String> {
    need(started <= before_at && before_at < opened_at && opened_at < finished_at
        && finished_at < session_end && finished_at < after_at && after_at < original_end
        && session_end <= ui_end && ui_end.checked_add(QUERY_CAP) == Some(original_end),
        "PM permission samples do not enclose this actual finished UI session under the original end")
}

fn offset_nanos(started: Instant, at: Instant) -> Result<u64, String> {
    at.checked_duration_since(started)
        .and_then(|v| u64::try_from(v.as_nanos()).ok())
        .ok_or_else(|| "PM permission monotonic observation interval differs".into())
}

fn write_record(
    journal: &Journal, generated: &mut GeneratedRecords, name: &'static str, value: &impl Serialize,
) -> Result<(), String> {
    need([BEGIN, BEFORE, AFTER, COMPLETE].contains(&name) && !generated.contains_key(name),
        "PM permission record is not a unique source-owned member")?;
    let bytes = serde_json::to_vec(value).map_err(|e| e.to_string())?;
    need(!bytes.is_empty() && bytes.len() <= RECORD_BOUND,
        "PM permission record exceeds its fixed complete bound")?;
    journal.write(name, &bytes)?;
    generated.insert(name.into(), (bytes.len() as u64, format!("{:x}", Sha256::digest(&bytes))));
    Ok(())
}

fn failure(journal: &Journal, error: String) -> String {
    // Diagnostics cannot construct success. A failed or abandoned window
    // keeps its original records; it never retries a query or an Android action.
    let diagnostic: String = error.chars().take(4096).collect();
    let record = serde_json::json!({
        "schema":"droidloom.native-ui-pm-permission-failed.v1",
        "error":diagnostic,"diagnostic_truncated":diagnostic.len()!=error.len(),
        "permission_preservation_observed":false,
        "automatic_retry":false,"complete_data_permissions_accepted":false
    });
    match journal.json("PERMISSION-FAILED.json", &record) {
        Ok(()) => format!("{error}; PM permission failure retained at {}", journal.path.display()),
        Err(record_error) => format!("{error}; PM permission failure record also failed: {record_error}; original journal {}", journal.path.display()),
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
            "PM permission custody belongs to another actual UI task, journal or lifetime")?;
        transcript.journal_custody.verify()
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
                "schema":"droidloom.native-ui-pm-permission-begin.v1",
                "main":main,"application":application,"fixed_queries":2,
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
            before(ui_end)?;
            Ok::<_, String>(observation)
        })();
        let observed = match observed {
            Ok(value) => value,
            Err(error) => return Err(failure(&journal, error)),
        };
        Ok(Self { main, application, started, end:original_end, ui_end,
            journal, generated, before:observed })
    }

    /// The original end minus the one fixed after-query reserve. The normal
    /// session may choose an earlier source bound, never a later one.
    pub fn ui_deadline(&self) -> Instant { self.ui_end }

    /// Retain the real UI failure without retrying, claiming normal close or
    /// manufacturing a permission result. The original error remains primary.
    pub fn fail(self, error: String) -> String { failure(&self.journal, error) }

    pub fn finish(
        mut self,
        inspector: &mut NativeApplicationInspector,
        baseline: &NativeLeafBaselineObservation<'_>,
        transcript: &NativeUiTranscript,
    ) -> Result<NativeUiPermissionPreservation, String> {
        let (after, ui, retained) = match self.finish_inner(inspector, baseline, transcript) {
            Ok(value) => value,
            Err(error) => return Err(failure(&self.journal, error)),
        };
        let result = NativeUiPermissionPreservation {
            main:self.main, application:self.application, started:self.started, end:self.end,
            ui_end:self.ui_end, before:self.before, after, ui,
            journal:self.journal, generated:self.generated, retained,
        };
        if let Err(error) = result.require_transcript(transcript).and_then(|_| before(result.end)) {
            return Err(failure(&result.journal, error));
        }
        Ok(result)
    }

    fn finish_inner(
        &mut self,
        inspector: &mut NativeApplicationInspector,
        baseline: &NativeLeafBaselineObservation<'_>,
        transcript: &NativeUiTranscript,
    ) -> Result<(ActualApplicationPermissionObservation, UiBoundary, RetainedJournal), String> {
        before(self.end)?;
        need(self.end <= baseline.deadline() && baseline.main().facts() == &self.main
            && baseline.application() == &self.application
            && transcript.engine().facts().main == self.main
            && transcript.engine().application() == &self.application,
            "PM permission window lost its original complete Main or installed application")?;
        baseline.verify_local(inspector, self.end).map_err(|e| e.to_string())?;
        inspector.require_permission_state_local(
            baseline.main(), baseline.actual_application(), &self.before, self.end,
        ).map_err(|e| e.to_string())?;
        let ui = UiBoundary::capture(transcript)?;
        // Reject a saved or earlier session before issuing the second query.
        need(self.before.observed_at() < ui.opened_at && ui.opened_at < ui.finished_at
            && ui.finished_at < ui.end && ui.end <= self.ui_end && ui.finished_at < Instant::now(),
            "PM permission post-query requires the fresh normal close from this window")?;
        let after = inspector.observe_application_permission_state_until(
            baseline.main(), baseline.actual_application(), self.end,
        ).map_err(|e| e.to_string())?;
        inspector.require_permission_state_local(
            baseline.main(), baseline.actual_application(), &after, self.end,
        ).map_err(|e| e.to_string())?;
        after.facts().require_application(&self.application)?;
        // Preserve the actual differing after table before refusing a result.
        write_record(&self.journal, &mut self.generated, AFTER, after.facts())?;
        require_order(self.started, self.before.observed_at(), ui.opened_at, ui.finished_at,
            after.observed_at(), ui.end, self.ui_end, self.end)?;
        self.before.facts().same_permissions(after.facts())?;
        write_record(&self.journal, &mut self.generated, COMPLETE, &serde_json::json!({
            "schema":"droidloom.native-ui-pm-permission-complete.v1",
            "application":self.application,
            "main_sha256":format!("{:x}",Sha256::digest(serde_json::to_vec(&self.main).map_err(|e|e.to_string())?)),
            "ui_journal":ui.journal,"ui_journal_identity":ui.journal_identity,"task":ui.task,
            "before_nanoseconds":offset_nanos(self.started,self.before.observed_at())?,
            "opened_nanoseconds":offset_nanos(self.started,ui.opened_at)?,
            "finished_nanoseconds":offset_nanos(self.started,ui.finished_at)?,
            "after_nanoseconds":offset_nanos(self.started,after.observed_at())?,
            "before_state_sha256":self.before.facts().state_sha256(),
            "after_state_sha256":after.facts().state_sha256(),
            "before_stdout_sha256":self.before.facts().stdout_sha256(),
            "after_stdout_sha256":after.facts().stdout_sha256(),
            "pm_requested_install_runtime_and_shared_uid_unchanged":true,
            "normal_owned_close_and_bookends_completed":true,
            "complete_data_permissions_or_accounts_accepted":false,
            "query_receipts_compared_for_equality":false,
            "automatic_retry":false,"original_deadline_extended":false
        }))?;
        let retained = RetainedJournal::capture(&self.journal, self.end, JournalKind::Permissions)?;
        retained.require_generated_permission_records(&self.generated)?;
        ui.require_transcript(transcript)?;
        before(self.end)?;
        Ok((after, ui, retained))
    }
}

/// Immutable historical PM-only preservation, sealed before the original end.
/// The full tables/actual query retirements and every generated record remain
/// held. Historical guarding does not renew a lease or assert later liveness.
pub struct NativeUiPermissionPreservation {
    main: RuntimeMainCustody,
    application: ApplicationInspection,
    started: Instant,
    end: Instant,
    ui_end: Instant,
    before: ActualApplicationPermissionObservation,
    after: ActualApplicationPermissionObservation,
    ui: UiBoundary,
    journal: Journal,
    generated: GeneratedRecords,
    retained: RetainedJournal,
}
impl NativeUiPermissionPreservation {
    pub fn require_subject(
        &self, main: &RuntimeMainCustody, application: &ApplicationInspection,
    ) -> Result<(), String> {
        need(&self.main == main && &self.application == application,
            "PM permission preservation belongs to another actual Main or complete PM identity")?;
        self.guard_immutable()
    }
    pub fn require_transcript(&self, transcript: &NativeUiTranscript) -> Result<(), String> {
        self.ui.require_transcript(transcript)?;
        self.require_subject(&transcript.engine().facts().main, transcript.engine().application())
    }
    pub fn guard_immutable(&self) -> Result<(), String> {
        self.before.facts().require_application(&self.application)?;
        self.after.facts().require_application(&self.application)?;
        self.before.facts().same_permissions(self.after.facts())?;
        require_order(self.started, self.before.observed_at(), self.ui.opened_at, self.ui.finished_at,
            self.after.observed_at(), self.ui.end, self.ui_end, self.end)?;
        self.retained.guard(&self.journal)?;
        self.retained.require_generated_permission_records(&self.generated)
    }
    pub fn comparison(&self) -> Result<Value, String> {
        self.guard_immutable()?;
        // Full tables are retained in their four private records. Duplicating
        // them for 31 histories would unnecessarily enlarge the capture frame.
        let records = self.generated.iter().map(|(name, (bytes, sha256))|
            serde_json::json!({"name":name,"bytes":bytes,"sha256":sha256})).collect::<Vec<_>>();
        Ok(serde_json::json!({
            "schema":"droidloom.native-ui-pm-permission-preservation.v1",
            "package":self.application.package,"uid":self.application.uid,"epoch":self.application.epoch,
            "main_sha256":format!("{:x}",Sha256::digest(serde_json::to_vec(&self.main).map_err(|e|e.to_string())?)),
            "application_sha256":format!("{:x}",Sha256::digest(serde_json::to_vec(&self.application).map_err(|e|e.to_string())?)),
            "ui_task":self.ui.task,"ui_journal":self.ui.journal,"ui_journal_identity":self.ui.journal_identity,
            "permission_journal":self.journal.path,"permission_journal_identity":self.journal.identity,
            "records":records,
            "before_state_sha256":self.before.facts().state_sha256(),
            "after_state_sha256":self.after.facts().state_sha256(),
            "before_stdout_sha256":self.before.facts().stdout_sha256(),
            "after_stdout_sha256":self.after.facts().stdout_sha256(),
            "before_nanoseconds":offset_nanos(self.started,self.before.observed_at())?,
            "opened_nanoseconds":offset_nanos(self.started,self.ui.opened_at)?,
            "finished_nanoseconds":offset_nanos(self.started,self.ui.finished_at)?,
            "after_nanoseconds":offset_nanos(self.started,self.after.observed_at())?,
            "pm_requested_install_runtime_and_shared_uid_unchanged":true,
            "normal_owned_close_and_full_bookends_completed":true,
            "actual_queries_retired":true,"retained_source_result_fds":true,
            "live_execution_authority_retained":false,"query_receipt_equality_required":false,
            "complete_data_permissions_or_accounts_accepted":false,
            "appops_or_persistent_data_acceptance_inferred":false,
            "automatic_retry":false,"original_deadline_extended":false
        }))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pm_permission_window_reserves_two_real_queries_inside_the_original_end() {
        let now=Instant::now();
        let end=now+Duration::from_secs(2755);
        assert_eq!(permission_preservation_additional_window_seconds(),140);
        assert_eq!(ui_deadline(now,end,end).unwrap(),end-QUERY_CAP);
        assert!(ui_deadline(now,end,end-Duration::from_nanos(1)).is_err());
        assert!(ui_deadline(now,now,end).is_err());
        assert!(ui_deadline(now,now+2*QUERY_CAP,end).is_err());
        let request=ControlRequest::ObserveApplicationPermissionState{
            package:"com.android.settings".into(),
            expected_epoch:crate::control::application_probe::RuntimeEpoch{
                boot_id:"11111111-1111-4111-8111-111111111111".into(),
                cell_host_pid:11,framework_host_pid:12,framework_start_ticks:13,
            },
        };
        assert_eq!(crate::control::progress::response_timeout(&request),QUERY_CAP);
    }

    #[test]
    fn pm_permission_window_rejects_reused_sessions_early_after_samples_and_renewed_reserves() {
        let base=Instant::now();
        let at=|s|base+Duration::from_secs(s);
        require_order(base,at(1),at(2),at(3),at(4),at(30),at(30),at(100)).unwrap();
        for (pre,open,finish,post,session,ui,end) in [
            (2,2,3,4,30,30,100), (3,2,3,4,30,30,100), (1,3,3,4,30,30,100),
            (1,2,3,3,30,30,100), (1,2,3,2,30,30,100), (1,2,3,100,30,30,100),
            (1,2,30,31,30,30,100), (1,2,3,4,31,30,100), (1,2,3,4,30,31,100),
            (1,2,3,4,30,30,101),
        ] {
            assert!(require_order(base,at(pre),at(open),at(finish),at(post),at(session),at(ui),at(end)).is_err());
        }
        assert!(require_order(at(2),at(1),at(2),at(3),at(4),at(30),at(30),at(100)).is_err());
    }
}
