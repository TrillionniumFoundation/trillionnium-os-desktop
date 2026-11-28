//! The one live owner of the separately admitted H2 working-qualification boot.
//!
//! Construction takes no PID, epoch, file pin, unit name, resource size or
//! success assertion. The fixed normal entry opens the actual boot inputs,
//! PID1 owner, already-armed watchdog and authenticated current Main. Its one
//! end is fixed before any preparation or source publication.
use super::{BoundProcess, application_leaf_unit::qualification::UnitOwner};
use crate::control::{
    DEFAULT_CONTROL_SOCKET, MainCustodyObservation, NativeApplicationInspector,
    NativeApplicationSourceLocks,
};
use crate::native_working_contract as c;
use serde_json::{Value, json};
use std::{
    path::Path,
    time::{Duration, Instant},
};
#[path = "working_qualification_boot.rs"]
mod boot;
#[path = "working_qualification_caps.rs"]
mod caps;
#[path = "working_qualification_child_exec.rs"]
pub(crate) mod child_exec;
#[path = "working_qualification_evidence.rs"]
mod evidence;
#[path = "working_qualification_publication.rs"]
mod publication;
#[path = "working_qualification_source.rs"]
mod source;
#[path = "working_qualification_watchdog.rs"]
mod watchdog;
#[path = "working_qualification_witness.rs"]
mod witness;
use source::require;
pub use source::{
    WorkingCurrentPreimage, WorkingForegroundOwner, WorkingLeafManifest, WorkingProgramPin,
    WorkingSourceFilePin, WorkingSourceOrigin, WorkingUnitIdentity,
};
pub use witness::WorkingSourceWitness;
pub use crate::native_working_contract::feishu::FeishuReadonlyFixture;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Phase {
    Preparing,
    PublishingSource,
    SourcePublished,
    PreparingCases,
    Prepared,
    PlanBound,
    Running,
    Complete,
    Committing,
    Failed,
}

/// Reduce the two fixed working children before any normal CLI dispatch.
/// This cannot create a Main, source, execution or completion qualification.
pub fn seal_initial_child_entry() -> Result<(), String> {
    boot::BootOwner::seal_initial_child_entry().map_err(|e| e.to_string())
}

/// No Deserialize, Clone or public constructor from comparison records.
pub struct WorkingQualificationOwner {
    boot: boot::BootOwner,
    unit: UnitOwner,
    watchdog: watchdog::SoftwareWatchdog,
    inspector: NativeApplicationInspector,
    main: MainCustodyObservation,
    original_start_ns: u64,
    original_end_ns: u64,
    end: Instant,
    origin: WorkingSourceOrigin,
    publication: Option<publication::Publication>,
    source_current_replaced: bool,
    preparation: Option<super::physical_qualification_channel::PreparationHistory>,
    evidence: evidence::Evidence,
    phase: Phase,
}
impl WorkingQualificationOwner {
    /// Enter the fixed installed singleton. The initial Main request consumes
    /// the existing source/capture allowance; it does not start a second clock.
    pub fn acquire() -> Result<Self, String> {
        let schedule = c::WorkingSchedule::selected();
        schedule.validate().map_err(|e| e.to_string())?;
        let boot = boot::BootOwner::open().map_err(|e| e.to_string())?;
        let provisional_end = Instant::now()
            .checked_add(Duration::from_secs(schedule.whole_suite_seconds))
            .ok_or("working source deadline overflow")?;
        let unit = UnitOwner::capture_working(provisional_end)?;
        let original_start_ns = unit.manager_start_ns()?;
        let original_end_ns = schedule
            .authorization_end_ns(original_start_ns)
            .map_err(|e| e.to_string())?;
        require(
            unit.manager_deadline_ns()? == original_end_ns,
            "working unit and source authorization ends differ",
        )?;
        let end =
            super::physical_qualification_channel::instant_until(original_end_ns, provisional_end)
                .map_err(|e| e.to_string())?;
        let bootstrap_ns = original_start_ns
            .checked_add(c::budget::SOURCE_AND_CAPTURE_SECONDS * 1_000_000_000)
            .ok_or("working source bootstrap overflow")?;
        let bootstrap_end = super::physical_qualification_channel::instant_until(bootstrap_ns, end)
            .map_err(|e| e.to_string())?;
        // Pre-open checks require the exact early owner's already-active timer.
        // This constructor neither loads softdog nor changes its interval.
        let mut watchdog = watchdog::SoftwareWatchdog::open().map_err(|e| e.to_string())?;
        let mut inspector = NativeApplicationInspector::acquire_until(
            Path::new(DEFAULT_CONTROL_SOCKET),
            bootstrap_end,
        )
        .map_err(|e| e.to_string())?;
        let main = inspector
            .observe_current_main_until(bootstrap_end)
            .map_err(|e| e.to_string())?;
        boot.compare_main(&main).map_err(|e| e.to_string())?;
        unit.boundary(None, bootstrap_end)?;
        require(
            Instant::now() < bootstrap_end,
            "actual initial Main exhausted the original source/capture allowance",
        )?;
        watchdog
            .keepalive(original_start_ns, original_end_ns)
            .map_err(|e| e.to_string())?;
        let origin = WorkingSourceOrigin::capture(&boot, &unit, &main, original_end_ns)?;
        let evidence = evidence::Evidence::open(&boot).map_err(|e| e.to_string())?;
        let value = Self {
            boot,
            unit,
            watchdog,
            inspector,
            main,
            original_start_ns,
            original_end_ns,
            end,
            origin,
            publication: None,
            source_current_replaced: false,
            preparation: None,
            evidence,
            phase: Phase::Preparing,
        };
        value.local_guard(None, bootstrap_end)?;
        value
            .evidence
            .record("OWNER-START.json", &value.observation())
            .map_err(|e| e.to_string())?;
        Ok(value)
    }
    pub fn deadline(&self) -> Instant {
        self.end
    }
    pub fn main(&self) -> &MainCustodyObservation {
        &self.main
    }
    pub fn source_origin(&self) -> &WorkingSourceOrigin {
        &self.origin
    }
    pub fn published_source(&self) -> Option<WorkingSourceFilePin> {
        self.publication
            .as_ref()
            .map(publication::Publication::reference)
    }
    fn local_guard(&self, child: Option<&BoundProcess>, deadline: Instant) -> Result<(), String> {
        require(
            self.phase != Phase::Failed && Instant::now() < self.end.min(deadline),
            "working owner failed or exhausted its one original end",
        )?;
        self.boot.guard().map_err(|e| e.to_string())?;
        self.evidence.guard().map_err(|e| e.to_string())?;
        self.unit.local_guard(child, deadline)?;
        self.inspector.revalidate().map_err(|e| e.to_string())?;
        self.boot
            .compare_main(&self.main)
            .map_err(|e| e.to_string())?;
        self.origin.matches_main(&self.main)?;
        self.watchdog.guard().map_err(|e| e.to_string())?;
        if let Some(publication) = &self.publication {
            publication.guard()?;
        }
        if let Some(history) = &self.preparation {
            history.guard()?;
        }
        c::WorkingSchedule::selected()
            .check_keepalive_time(
                self.original_end_ns,
                self.original_start_ns,
                watchdog::monotonic_ns().map_err(|e| e.to_string())?,
            )
            .map_err(|e| e.to_string())?;
        require(
            Instant::now() < self.end.min(deadline),
            "working local guard exhausted the original end",
        )
    }
    /// Only the fixed owner loops may supply an actual held direct child. This
    /// does not claim nested retirement; boundary() remains a separate gate.
    pub(super) fn pump(
        &mut self,
        child: Option<&BoundProcess>,
        deadline: Instant,
    ) -> Result<(), String> {
        self.local_guard(child, deadline)?;
        let now = watchdog::monotonic_ns().map_err(|e| e.to_string())?;
        if self.watchdog.due(now) {
            // One normal Main request (70s) and one existing shared 15s PID1
            // observation. Both consume the caller's same original phase end.
            let feed_end = deadline
                .min(self.end)
                .min(Instant::now() + Duration::from_secs(c::MAIN_REVALIDATION_SECONDS + 15));
            require(
                feed_end.saturating_duration_since(Instant::now())
                    >= Duration::from_secs(c::MAIN_REVALIDATION_SECONDS),
                "original working phase cannot fit its guarded watchdog observation",
            )?;
            let after = self
                .inspector
                .refresh_main_until(&self.main, feed_end)
                .map_err(|e| e.to_string())?;
            self.boot.compare_main(&after).map_err(|e| e.to_string())?;
            self.origin.matches_main(&after)?;
            self.unit.live_guard(child, feed_end)?;
            self.main = after;
            self.local_guard(child, feed_end)?;
            self.watchdog
                .keepalive(self.original_start_ns, self.original_end_ns)
                .map_err(|e| e.to_string())?;
            self.local_guard(child, feed_end)?;
        }
        Ok(())
    }
    /// A first and only source lease. The original two exclusive OFDs are
    /// acquired before capturing actual CURRENT. Failed/unknown publication
    /// poisons this owner; a later call cannot silently renew or retry it.
    pub fn begin_initial_source(&mut self) -> Result<InitialWorkingSource<'_>, String> {
        require(
            self.phase == Phase::Preparing
                && self.publication.is_none()
                && !self.source_current_replaced,
            "working source owner may be initially acquired exactly once",
        )?;
        self.pump(None, self.end)?;
        self.unit.boundary(None, self.end)?;
        let locks =
            NativeApplicationSourceLocks::acquire_for_adoption().map_err(|e| e.to_string())?;
        let previous = publication::CurrentBefore::capture()?;
        locks.validate().map_err(|e| e.to_string())?;
        self.local_guard(None, self.end)?;
        self.phase = Phase::PublishingSource;
        Ok(InitialWorkingSource {
            owner: self,
            locks,
            previous: Some(previous),
            finished: false,
        })
    }
    pub fn guard_until(&mut self, deadline: Instant) -> Result<(), String> {
        require(
            deadline <= self.end,
            "working caller cannot extend the original end",
        )?;
        self.pump(None, deadline)
    }
    pub(super) fn close_in_child(&self) -> libc::c_int {
        self.watchdog.child_close_fd()
    }
    pub(crate) fn unit(&self) -> &UnitOwner {
        &self.unit
    }
    pub(crate) fn unit_mut(&mut self) -> &mut UnitOwner {
        &mut self.unit
    }
    pub(crate) fn guard_local(
        &self,
        child: Option<&BoundProcess>,
        end: Instant,
    ) -> Result<(), String> {
        self.local_guard(child, end)
    }

    pub(crate) fn preparation_output(
        &self,
        name: &str,
    ) -> Result<(std::fs::File, std::path::PathBuf), String> {
        require(
            self.phase == Phase::PreparingCases,
            "preparation output requires its live fixed phase",
        )?;
        if !matches!(name, "PREPARATION.stdout" | "PREPARATION.stderr") {
            return Err("unreviewed preparation output name".into());
        }
        self.local_guard(None, self.end)?;
        let file = self.evidence.create(name).map_err(|e| e.to_string())?;
        Ok((file, self.evidence.root().join(name)))
    }
    pub(crate) fn record_preparation(&self, value: &Value) -> Result<Value, String> {
        self.evidence
            .record("PREPARATION-OWNER-RESULT.json", value)
            .map_err(|e| e.to_string())
    }
    pub(crate) fn begin_preparation(&mut self) -> Result<(Instant, u64), String> {
        require(
            self.phase == Phase::SourcePublished && self.preparation.is_none(),
            "preparation requires the actual one-shot source publication",
        )?;
        let wire = self
            .original_start_ns
            .checked_add(
                c::PREPARATION_WORK_SECONDS
                    .checked_mul(1_000_000_000)
                    .ok_or("preparation source window overflow")?,
            )
            .ok_or("preparation original end overflow")?;
        let end = super::physical_qualification_channel::instant_until(wire, self.end)
            .map_err(|e| e.to_string())?;
        self.pump(None, end)?;
        self.unit.boundary(None, end)?;
        self.phase = Phase::PreparingCases;
        Ok((end, wire))
    }
    pub(crate) fn preparation_retirement_end(&self) -> Result<Instant, String> {
        let wire = self
            .original_start_ns
            .checked_add(
                c::PREPARATION_SECONDS
                    .checked_mul(1_000_000_000)
                    .ok_or("preparation retirement source window overflow")?,
            )
            .ok_or("preparation retirement end overflow")?;
        super::physical_qualification_channel::instant_until(wire, self.end)
            .map_err(|e| e.to_string())
    }
    pub(crate) fn finish_preparation(
        &mut self,
        history: super::physical_qualification_channel::PreparationHistory,
        end: Instant,
    ) -> Result<(), String> {
        require(
            self.phase == Phase::PreparingCases && self.preparation.is_none(),
            "preparation completion is out of order",
        )?;
        history.guard()?;
        self.pump(None, end)?;
        self.unit.boundary(None, end)?;
        self.preparation = Some(history);
        self.phase = Phase::Prepared;
        Ok(())
    }

    pub(crate) fn bind_physical_plan(&mut self, digest: &str, end: Instant) -> Result<(), String> {
        require(
            self.phase == Phase::Prepared
                && self.publication.is_some()
                && self.preparation.is_some(),
            "physical stage requires this owner's actual completed and retired preparation",
        )?;
        self.pump(None, end)?;
        self.unit.bind_working_plan(digest, end)?;
        self.phase = Phase::PlanBound;
        Ok(())
    }
    pub(crate) fn begin_physical(&mut self, end: Instant) -> Result<(), String> {
        require(
            self.phase == Phase::PlanBound,
            "physical stage may begin only once",
        )?;
        self.pump(None, end)?;
        self.unit.boundary(None, end)?;
        self.phase = Phase::Running;
        Ok(())
    }
    pub(crate) fn compare_physical_epoch(
        &self,
        epoch: &crate::control::application_probe::RuntimeEpoch,
    ) -> Result<(), String> {
        require(
            self.main.facts().epoch == *epoch,
            "actual physical child belongs to another normal Main epoch",
        )
    }
    pub(crate) fn compare_physical_binding(
        &self,
        binding: &crate::main_custody::RuntimeMainCustody,
    ) -> Result<(), String> {
        require(
            self.main.facts() == binding,
            "actual child's Complete differs from the parent's opaque Main resources",
        )
    }
    pub(crate) fn finish_physical(&mut self, end: Instant) -> Result<(), String> {
        require(
            self.phase == Phase::Running,
            "physical completion is out of order",
        )?;
        self.pump(None, end)?;
        self.unit.boundary(None, end)?;
        self.phase = Phase::Complete;
        Ok(())
    }
    pub(crate) fn begin_production_commit(
        &mut self,
        binding: &crate::main_custody::RuntimeMainCustody,
    ) -> Result<(crate::production_commit_contract::BytesPin, Instant), String> {
        require(
            self.phase == Phase::Complete,
            "production requires this owner's actual completed capture",
        )?;
        self.compare_physical_binding(binding)?;
        let selected = self
            .boot
            .config()
            .production_commit
            .as_ref()
            .ok_or("this actual working boot has no source-prepared production continuation")?;
        let selected = crate::production_commit_contract::BytesPin {
            bytes: selected.bytes,
            sha256: selected.sha256.clone(),
        };
        require(
            c::PRODUCTION_COMMIT_SECONDS == crate::production_commit_contract::COMMIT_SECONDS,
            "working and production tail budgets differ",
        )?;
        let end = self
            .end
            .min(Instant::now() + Duration::from_secs(c::PRODUCTION_COMMIT_SECONDS));
        self.unit.begin_production_commit(end)?;
        self.phase = Phase::Committing;
        let after = self
            .inspector
            .refresh_main_until(&self.main, end)
            .map_err(|e| e.to_string())?;
        self.boot.compare_main(&after).map_err(|e| e.to_string())?;
        require(
            after.facts() == binding,
            "Main changed before production commit",
        )?;
        self.main = after;
        self.local_guard(None, end)?;
        Ok((selected, end))
    }
    /// Preserve the actual publication phase even when later preparation or
    /// execution fails. Existing evidence is never overwritten or retried.
    pub fn record_failure(&mut self, reason: &str) -> Result<Value, String> {
        let reason_truncated = reason.chars().count() > 4096;
        let reason = reason.chars().take(4096).collect::<String>();
        let observed = self.observation();
        self.phase = Phase::Failed;
        self.evidence
            .record(
                "OWNER-FAILURE.json",
                &json!({
                    "schema":"droidloom.working-qualification-owner-failed.v1",
                    "observed_owner":observed,"reason":reason,"reason_truncated":reason_truncated,
                    "source_publication_already_committed":self.source_current_replaced,
                    "automatic_retry":false,"parent_retirement_observed":false,
                    "normal_return_required":true,"production_ready":false
                }),
            )
            .map_err(|e| e.to_string())
    }
    pub fn observation(&self) -> Value {
        json!({"schema":"droidloom.live-working-qualification-owner.v1",
            "phase":format!("{:?}",self.phase),
            "original_start_monotonic_ns":self.original_start_ns,"original_end_monotonic_ns":self.original_end_ns,
            "boot":self.boot.observation(),"source_origin":self.origin,
            "source_publication":self.published_source(),"source_current_replacement_committed":self.source_current_replaced,
            "watchdog":self.watchdog.observation(),
            "retired_preparation":self.preparation.as_ref().map(|v|v.observation()),
            "retirement_observed":false,"permanent_acceptance_granted":false})
    }
}

impl Drop for WorkingQualificationOwner {
    fn drop(&mut self) {
        if !matches!(self.phase, Phase::Complete | Phase::Failed) {
            // Best-effort preservation only. Drop cannot manufacture retirement
            // or turn a failed write into a successful evidence receipt.
            let _=self.record_failure("normal owner dropped before its physical completion; retain all prior stage records");
        }
    }
}

/// Borrowed only from the actual live parent. JSON types below are comparisons;
/// this private-field type is the only authorization for initial publication.
pub struct InitialWorkingSource<'a> {
    owner: &'a mut WorkingQualificationOwner,
    locks: NativeApplicationSourceLocks,
    previous: Option<publication::CurrentBefore>,
    finished: bool,
}
impl InitialWorkingSource<'_> {
    pub fn origin(&self) -> &WorkingSourceOrigin {
        &self.owner.origin
    }
    pub fn original_current_bytes(&self) -> &[u8] {
        self.previous
            .as_ref()
            .expect("live initial source preimage")
            .raw()
    }
    pub fn original_current(&self) -> WorkingCurrentPreimage {
        self.previous
            .as_ref()
            .expect("live initial source preimage")
            .reference()
    }
    /// Must be the final check immediately before the publisher's single CAS.
    pub fn guard_before_cas(&mut self) -> Result<(), String> {
        require(
            !self.finished && self.owner.phase == Phase::PublishingSource,
            "initial source permit already consumed",
        )?;
        self.owner.pump(None, self.owner.end)?;
        self.locks.validate().map_err(|e| e.to_string())?;
        self.previous
            .as_ref()
            .ok_or("initial source preimage already consumed")?
            .guard()?;
        self.owner.unit.boundary(None, self.owner.end)
    }
    /// Perform only this initial owner's fixed CURRENT CAS. No path or UID is
    /// accepted. The actual rename flag survives every later validation error.
    pub fn replace_current_source(
        &mut self,
        after: &[u8],
        release_sha256: &str,
    ) -> Result<[u64; 9], String> {
        require(
            !self.owner.source_current_replaced,
            "initial source CAS cannot be retried",
        )?;
        self.guard_before_cas()?;
        let end = self.owner.end;
        self.previous
            .as_ref()
            .ok_or("initial CURRENT preimage absent")?
            .replace(
                after,
                release_sha256,
                end,
                &mut self.owner.source_current_replaced,
            )
    }
    /// Reopens only the actual canonical CURRENT and its fixed root manifest.
    /// It compares the real retained old inode, exact three-field successor,
    /// full normal source bytes and initial owner before retaining publication.
    pub fn finish_after_cas(mut self) -> Result<WorkingSourceFilePin, String> {
        require(
            self.owner.phase == Phase::PublishingSource
                && !self.finished
                && self.owner.source_current_replaced,
            "initial source CAS was not performed by this owner",
        )?;
        self.owner.local_guard(None, self.owner.end)?;
        self.locks.validate().map_err(|e| e.to_string())?;
        let publication = publication::Publication::capture(
            self.previous.take().ok_or("initial CURRENT absent")?,
            &self.owner.origin,
        )?;
        self.locks.validate().map_err(|e| e.to_string())?;
        self.owner.unit.boundary(None, self.owner.end)?;
        self.owner.local_guard(None, self.owner.end)?;
        let reference = publication.reference();
        self.owner.publication = Some(publication);
        self.owner.phase = Phase::SourcePublished;
        self.finished = true;
        Ok(reference)
    }
}
impl Drop for InitialWorkingSource<'_> {
    fn drop(&mut self) {
        if !self.finished {
            self.owner.phase = Phase::Failed;
        }
    }
}
