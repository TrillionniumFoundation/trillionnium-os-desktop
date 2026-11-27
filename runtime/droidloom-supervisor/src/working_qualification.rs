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
#[path = "working_qualification_publication.rs"]
mod publication;
#[path = "working_qualification_source.rs"]
mod source;
#[path = "working_qualification_watchdog.rs"]
mod watchdog;
#[path = "working_qualification_witness.rs"]
mod witness;
pub use witness::WorkingSourceWitness;
use source::require;
pub use source::{
    WorkingCurrentPreimage, WorkingForegroundOwner, WorkingLeafManifest, WorkingProgramPin,
    WorkingSourceFilePin, WorkingSourceOrigin, WorkingUnitIdentity,
};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Phase {
    Preparing,
    PublishingSource,
    SourcePublished,
    PlanBound,
    Running,
    Complete,
    Failed,
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
            phase: Phase::Preparing,
        };
        value.local_guard(None, bootstrap_end)?;
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
            self.phase == Phase::Preparing && self.publication.is_none(),
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
    pub fn observation(&self) -> Value {
        json!({"schema":"droidloom.live-working-qualification-owner.v1",
            "phase":format!("{:?}",self.phase),
            "original_start_monotonic_ns":self.original_start_ns,"original_end_monotonic_ns":self.original_end_ns,
            "boot":self.boot.observation(),"source_origin":self.origin,
            "source_publication":self.published_source(),"watchdog":self.watchdog.observation(),
            "retirement_observed":false,"permanent_acceptance_granted":false})
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
    /// Reopens only the actual canonical CURRENT and its fixed root manifest.
    /// It compares the real retained old inode, exact three-field successor,
    /// full normal source bytes and initial owner before retaining publication.
    pub fn finish_after_cas(mut self) -> Result<WorkingSourceFilePin, String> {
        require(
            self.owner.phase == Phase::PublishingSource && !self.finished,
            "initial source permit already consumed",
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
