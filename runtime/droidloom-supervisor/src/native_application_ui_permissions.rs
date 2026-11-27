//! Actual before/open/normal-close/after PM and AppOps custody for one UI case.
//!
//! The only constructor borrows the admitted Inspector and original Main/PM
//! objects. Complete user-zero PM permissions and scoped AppOps mode samples
//! enclose the real session and its normal close/bookends. This partial evidence
//! does not prove accounts, persistent application data or a complete gate.
use super::*;
use super::common::{JournalKind, RetainedJournal};
use crate::control::{ActualApplicationPermissionObservation, ActualApplicationAppOpsObservation, application_probe::ApplicationInspection};

const QUERY_CAP: Duration = Duration::from_secs(70);
const APPOPS_QUERY_CAP: Duration = Duration::from_secs(70);
const AFTER_RESERVE: Duration = Duration::from_secs(QUERY_CAP.as_secs() + APPOPS_QUERY_CAP.as_secs());
const RECORD_BOUND: usize = crate::application_permission_state::MAX_WIRE_BYTES;
const _: () = assert!(RECORD_BOUND == crate::application_appops_state::MAX_WIRE_BYTES);
const BEGIN: &str = "PERMISSION-BEGIN.json";
const BEFORE: &str = "PERMISSION-BEFORE.json";
const AFTER: &str = "PERMISSION-AFTER.json";
const COMPLETE: &str = "PERMISSION-COMPLETE.json";
const APPOPS_BEFORE: &str = "APPOPS-BEFORE.json";
const APPOPS_AFTER: &str = "APPOPS-AFTER.json";
type GeneratedRecords = BTreeMap<String, (u64, String)>;

/// Two PM and two AppOps fixed queries for each real window. This function
/// allocates no lease and never extends a caller's original deadline.
pub fn permission_preservation_additional_window_seconds() -> u64 {
    2 * (QUERY_CAP.as_secs() + APPOPS_QUERY_CAP.as_secs())
}

fn ui_deadline(now: Instant, original_end: Instant, baseline_end: Instant) -> Result<Instant, String> {
    need(now < original_end && original_end <= baseline_end,
        "PM/AppOps permission window is outside its original baseline deadline")?;
    let cutoff = original_end.checked_sub(AFTER_RESERVE)
        .filter(|end| end.saturating_duration_since(now) > AFTER_RESERVE)
        .ok_or("PM/AppOps permission window cannot fit all four fixed queries and actual UI work")?;
    Ok(cutoff)
}

fn require_order(
    started: Instant, before_at: Instant, opened_at: Instant, finished_at: Instant,
    after_at: Instant, session_end: Instant, ui_end: Instant, original_end: Instant,
) -> Result<(), String> {
    need(started <= before_at && before_at < opened_at && opened_at < finished_at
        && finished_at < session_end && finished_at < after_at && after_at < original_end
        && session_end <= ui_end && ui_end.checked_add(AFTER_RESERVE) == Some(original_end),
        "PM/AppOps permission samples do not enclose this actual finished UI session under the original end")
}

fn require_appops_order(
    pm_before: Instant, appops_before: Instant, opened: Instant, finished: Instant,
    appops_after: Instant, pm_after: Instant,
) -> Result<(), String> {
    need(pm_before < appops_before && appops_before < opened
        && finished < appops_after && appops_after < pm_after,
        "AppOps samples must enclose the same actual UI lifetime inside the PM samples")
}

fn offset_nanos(started: Instant, at: Instant) -> Result<u64, String> {
    at.checked_duration_since(started)
        .and_then(|v| u64::try_from(v.as_nanos()).ok())
        .ok_or_else(|| "PM/AppOps permission monotonic observation interval differs".into())
}

fn write_record(
    journal: &Journal, generated: &mut GeneratedRecords, name: &'static str, value: &impl Serialize,
) -> Result<(), String> {
    need([BEGIN, BEFORE, APPOPS_BEFORE, APPOPS_AFTER, AFTER, COMPLETE].contains(&name) && !generated.contains_key(name),
        "PM/AppOps permission record is not a unique source-owned member")?;
    let bytes = serde_json::to_vec(value).map_err(|e| e.to_string())?;
    need(!bytes.is_empty() && bytes.len() <= RECORD_BOUND,
        "PM/AppOps permission record exceeds its fixed complete bound")?;
    journal.write(name, &bytes)?;
    generated.insert(name.into(), (bytes.len() as u64, format!("{:x}", Sha256::digest(&bytes))));
    Ok(())
}

fn failure(journal: &Journal, error: String) -> String {
    // Diagnostics cannot construct success. A failed or abandoned window
    // keeps its original records; it never retries a query or an Android action.
    let diagnostic: String = error.chars().take(4096).collect();
    let record = serde_json::json!({
        "schema":"droidloom.native-ui-pm-permission-failed.v2",
        "error":diagnostic,"diagnostic_truncated":diagnostic.len()!=error.len(),
        "permission_preservation_observed":false,
        "automatic_retry":false,"complete_data_permissions_accepted":false
    });
    match journal.json("PERMISSION-FAILED.json", &record) {
        Ok(()) => format!("{error}; PM/AppOps permission failure retained at {}", journal.path.display()),
        Err(record_error) => format!("{error}; PM/AppOps permission failure record also failed: {record_error}; original journal {}", journal.path.display()),
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
            "PM/AppOps permission custody belongs to another actual UI task, journal or lifetime")?;
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
    before_appops: ActualApplicationAppOpsObservation,
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
                "schema":"droidloom.native-ui-pm-permission-begin.v2",
                "main":main,"application":application,"fixed_queries":4,
                "pm_queries":2,"appops_queries":2,
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
                "PM/AppOps pre-observations did not follow the fixed query order")?;
            write_record(&journal, &mut generated, APPOPS_BEFORE, appops.facts())?;
            before(ui_end)?;
            Ok::<_, String>((observation, appops))
        })();
        let (observed, before_appops) = match observed {
            Ok(value) => value,
            Err(error) => return Err(failure(&journal, error)),
        };
        Ok(Self { main, application, started, end:original_end, ui_end,
            journal, generated, before:observed, before_appops })
    }

    /// The original end minus the two fixed after-query reserves. The normal
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
        let (after, after_appops, ui, retained) = match self.finish_inner(inspector, baseline, transcript) {
            Ok(value) => value,
            Err(error) => return Err(failure(&self.journal, error)),
        };
        let result = NativeUiPermissionPreservation {
            main:self.main, application:self.application, started:self.started, end:self.end,
            ui_end:self.ui_end, before:self.before, before_appops:self.before_appops,
            after, after_appops, ui,
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
    ) -> Result<(ActualApplicationPermissionObservation, ActualApplicationAppOpsObservation, UiBoundary, RetainedJournal), String> {
        before(self.end)?;
        need(self.end <= baseline.deadline() && baseline.main().facts() == &self.main
            && baseline.application() == &self.application
            && transcript.engine().facts().main == self.main
            && transcript.engine().application() == &self.application,
            "PM/AppOps permission window lost its original complete Main or installed application")?;
        baseline.verify_local(inspector, self.end).map_err(|e| e.to_string())?;
        inspector.require_permission_state_local(
            baseline.main(), baseline.actual_application(), &self.before, self.end,
        ).map_err(|e| e.to_string())?;
        inspector.require_appops_state_local(
            baseline.main(), baseline.actual_application(), &self.before_appops, self.end,
        ).map_err(|e| e.to_string())?;
        let ui = UiBoundary::capture(transcript)?;
        // Reject a saved or earlier session before issuing either after-query.
        need(self.before.observed_at() < self.before_appops.observed_at()
            && self.before_appops.observed_at() < ui.opened_at && ui.opened_at < ui.finished_at
            && ui.finished_at < ui.end && ui.end <= self.ui_end && ui.finished_at < Instant::now(),
            "PM/AppOps permission post-query requires the fresh normal close from this window")?;
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
        require_order(self.started, self.before.observed_at(), ui.opened_at, ui.finished_at,
            after.observed_at(), ui.end, self.ui_end, self.end)?;
        require_appops_order(self.before.observed_at(), self.before_appops.observed_at(),
            ui.opened_at, ui.finished_at, after_appops.observed_at(), after.observed_at())?;
        self.before.facts().same_permissions(after.facts())?;
        self.before_appops.facts().same_modes(after_appops.facts())?;
        write_record(&self.journal, &mut self.generated, COMPLETE, &serde_json::json!({
            "schema":"droidloom.native-ui-pm-permission-complete.v2",
            "application":self.application,
            "main_sha256":format!("{:x}",Sha256::digest(serde_json::to_vec(&self.main).map_err(|e|e.to_string())?)),
            "ui_journal":ui.journal,"ui_journal_identity":ui.journal_identity,"task":ui.task,
            "before_nanoseconds":offset_nanos(self.started,self.before.observed_at())?,
            "opened_nanoseconds":offset_nanos(self.started,ui.opened_at)?,
            "finished_nanoseconds":offset_nanos(self.started,ui.finished_at)?,
            "after_nanoseconds":offset_nanos(self.started,after.observed_at())?,
            "appops_before_nanoseconds":offset_nanos(self.started,self.before_appops.observed_at())?,
            "appops_after_nanoseconds":offset_nanos(self.started,after_appops.observed_at())?,
            "appops_before_state_sha256":self.before_appops.facts().state_sha256(),
            "appops_after_state_sha256":after_appops.facts().state_sha256(),
            "appops_before_stdout_sha256":self.before_appops.facts().stdout_sha256(),
            "appops_after_stdout_sha256":after_appops.facts().stdout_sha256(),
            "before_state_sha256":self.before.facts().state_sha256(),
            "after_state_sha256":after.facts().state_sha256(),
            "before_stdout_sha256":self.before.facts().stdout_sha256(),
            "after_stdout_sha256":after.facts().stdout_sha256(),
            "pm_requested_install_runtime_and_shared_uid_unchanged":true,
            "appops_defaults_uid_and_package_modes_unchanged":true,
            "normal_owned_close_and_bookends_completed":true,
            "complete_data_permissions_or_accounts_accepted":false,
            "query_receipts_compared_for_equality":false,
            "automatic_retry":false,"original_deadline_extended":false
        }))?;
        let retained = RetainedJournal::capture(&self.journal, self.end, JournalKind::Permissions)?;
        retained.require_generated_permission_records(&self.generated)?;
        ui.require_transcript(transcript)?;
        before(self.end)?;
        Ok((after, after_appops, ui, retained))
    }
}

/// Immutable historical PM/AppOps preservation, sealed before the original end.
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
    after: ActualApplicationPermissionObservation,
    after_appops: ActualApplicationAppOpsObservation,
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
            "PM/AppOps permission preservation belongs to another actual Main or complete PM identity")?;
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
        self.before_appops.facts().require_application(&self.application)?;
        self.after_appops.facts().require_application(&self.application)?;
        self.before_appops.facts().same_modes(self.after_appops.facts())?;
        require_appops_order(self.before.observed_at(), self.before_appops.observed_at(),
            self.ui.opened_at, self.ui.finished_at, self.after_appops.observed_at(),
            self.after.observed_at())?;
        require_order(self.started, self.before.observed_at(), self.ui.opened_at, self.ui.finished_at,
            self.after.observed_at(), self.ui.end, self.ui_end, self.end)?;
        self.retained.guard(&self.journal)?;
        self.retained.require_generated_permission_records(&self.generated)
    }
    pub fn comparison(&self) -> Result<Value, String> {
        self.guard_immutable()?;
        // Full tables are retained in their six private records. Duplicating
        // them for 31 histories would unnecessarily enlarge the capture frame.
        let records = self.generated.iter().map(|(name, (bytes, sha256))|
            serde_json::json!({"name":name,"bytes":bytes,"sha256":sha256})).collect::<Vec<_>>();
        Ok(serde_json::json!({
            "schema":"droidloom.native-ui-pm-permission-preservation.v2",
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
            "appops_before_nanoseconds":offset_nanos(self.started,self.before_appops.observed_at())?,
            "appops_after_nanoseconds":offset_nanos(self.started,self.after_appops.observed_at())?,
            "appops_before_state_sha256":self.before_appops.facts().state_sha256(),
            "appops_after_state_sha256":self.after_appops.facts().state_sha256(),
            "appops_before_stdout_sha256":self.before_appops.facts().stdout_sha256(),
            "appops_after_stdout_sha256":self.after_appops.facts().stdout_sha256(),
            "pm_requested_install_runtime_and_shared_uid_unchanged":true,
            "appops_defaults_uid_and_package_modes_unchanged":true,
            "normal_owned_close_and_full_bookends_completed":true,
            "actual_queries_retired":true,"retained_source_result_fds":true,
            "live_execution_authority_retained":false,"query_receipt_equality_required":false,
            "complete_data_permissions_or_accounts_accepted":false,
            "persistent_data_or_accounts_acceptance_inferred":false,
            "automatic_retry":false,"original_deadline_extended":false
        }))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pm_permission_window_reserves_four_real_queries_inside_the_original_end() {
        let now=Instant::now();
        let end=now+Duration::from_secs(2895);
        assert_eq!(permission_preservation_additional_window_seconds(),280);
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
            package:"com.android.settings".into(), expected_epoch:epoch,
        };
        assert_eq!(crate::control::progress::response_timeout(&pm),QUERY_CAP);
        assert_eq!(crate::control::progress::response_timeout(&appops),APPOPS_QUERY_CAP);
    }

    #[test]
    fn pm_permission_window_rejects_reused_sessions_early_after_samples_and_renewed_reserves() {
        let base=Instant::now();
        let at=|s|base+Duration::from_secs(s);
        require_order(base,at(1),at(2),at(3),at(4),at(30),at(30),at(170)).unwrap();
        for (pre,open,finish,post,session,ui,end) in [
            (2,2,3,4,30,30,170), (3,2,3,4,30,30,170), (1,3,3,4,30,30,170),
            (1,2,3,3,30,30,170), (1,2,3,2,30,30,170), (1,2,3,170,30,30,170),
            (1,2,30,31,30,30,170), (1,2,3,4,31,30,170), (1,2,3,4,30,31,170),
            (1,2,3,4,30,30,171),
        ] {
            assert!(require_order(base,at(pre),at(open),at(finish),at(post),at(session),at(ui),at(end)).is_err());
        }
        assert!(require_order(at(2),at(1),at(2),at(3),at(4),at(30),at(30),at(170)).is_err());
        require_appops_order(at(1),at(2),at(3),at(4),at(5),at(6)).unwrap();
        for (pm_pre,ops_pre,open,finish,ops_post,pm_post) in [
            (1,1,3,4,5,6), (2,1,3,4,5,6), (1,3,3,4,5,6),
            (1,4,3,4,5,6), (1,2,3,4,4,6), (1,2,3,4,3,6),
            (1,2,3,4,6,6), (1,2,3,4,7,6),
        ] {
            assert!(require_appops_order(at(pm_pre),at(ops_pre),at(open),at(finish),
                at(ops_post),at(pm_post)).is_err());
        }
    }
}
