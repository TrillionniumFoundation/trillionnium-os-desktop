// SPDX-License-Identifier: MPL-2.0

//! Process-image lifetime for the HOS2 bootstrap profiles.
//!
//! An image key identifies an allocation; it grants no resource authority.
//! Closing fences discovery and sessions and drops any initial observe slot.
//! G1-d also synchronizes admitted operations before revoking its canonical CPU
//! delegation outside this mutex. Recovery retains the original D namespace;
//! a replacement image receives no inherited management or history capability.

use core::sync::atomic::{AtomicU64, Ordering};

use super::Process;
#[cfg(feature = "g1c-trusted-observe")]
use super::postexec_observe::ObserveIssuer;
#[cfg(feature = "g1d-trusted-control")]
use super::trusted_control::TrustedControlSlots;
#[cfg(feature = "g1c-trusted-observe")]
use crate::fs::cgroupfs::{CpuUsageError, NativeCpuObserver};
#[cfg(any(ktest, feature = "g1c-trusted-observe"))]
use crate::hos2_os_abi::Status;
use crate::prelude::*;

#[cfg(any(ktest, feature = "g1c-trusted-observe"))]
fn check_initial_observe_lease(
    issued_ns: u64,
    expires_ns: u64,
    sample_ns: u64,
) -> core::result::Result<(), Status> {
    if sample_ns < issued_ns {
        Err(Status::Indeterminate)
    } else if sample_ns >= expires_ns {
        Err(Status::Revoked)
    } else {
        Ok(())
    }
}

/// The one observe-only slot in this actual initial Process CapSpace. Its
/// lease and scope have no userspace constructor; slot/generation are merely
/// discovery. Closing this image removes the only authority record.
#[cfg(feature = "g1c-trusted-observe")]
pub(super) struct InitialObserveGrant {
    observer: Arc<NativeCpuObserver>,
    issued_ns: u64,
    expires_ns: u64,
    issuer: Option<ObserveIssuer>,
}

#[cfg(feature = "g1c-trusted-observe")]
impl InitialObserveGrant {
    pub(super) fn for_launch(
        observer: Arc<NativeCpuObserver>,
        issued_ns: u64,
        expires_ns: u64,
        issuer: ObserveIssuer,
    ) -> Self {
        Self {
            observer,
            issued_ns,
            expires_ns,
            issuer: Some(issuer),
        }
    }
}

/// A checked slot reservation borrowing the actual image state. No authority
/// is installed until the external Process and VMAR fences are committed.
#[cfg(feature = "g1c-trusted-observe")]
pub(super) struct PreparedPostexecObserve<'a> {
    slot: &'a mut Option<InitialObserveGrant>,
    grant: Option<InitialObserveGrant>,
}

#[cfg(feature = "g1c-trusted-observe")]
impl PreparedPostexecObserve<'_> {
    pub(super) fn commit(self) {
        if let Some(grant) = self.grant {
            *self.slot = Some(grant);
        }
    }
}

/// Never reuse a boot-local HOS2 process-image namespace, including after PID
/// reuse. Zero is reserved for an image that has not opened a session yet.
static NEXT_HEPTA_CAPSPACE_NONCE: AtomicU64 = AtomicU64::new(1);

/// The identity of one image of one Process, not a grant or a principal.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct ProcessImageKey {
    epoch: u64,
    nonce: u64,
}

impl ProcessImageKey {
    pub(crate) fn nonce(self) -> u64 {
        self.nonce
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum ImagePhase {
    Live,
    Closing,
    Closed,
}

/// First scheduling is independent of exec: exec replaces an already running
/// image and must never restore permission to schedule its main task again.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum FirstRun {
    Unprepared,
    Prepared,
    Started,
}

/// The original Process owns this state under one mutex. The epoch, nonce,
/// phase and first-run claim are never published independently.
pub(super) struct ProcessImageState {
    epoch: u64,
    nonce: u64,
    phase: ImagePhase,
    first_run: FirstRun,
    #[cfg(feature = "g1c-trusted-observe")]
    initial_observe: Option<InitialObserveGrant>,
    #[cfg(feature = "g1c-trusted-observe")]
    observe_launcher: bool,
    #[cfg(feature = "g1d-trusted-control")]
    initial_control: Option<Arc<TrustedControlSlots>>,
}

impl ProcessImageState {
    pub(super) fn new() -> Self {
        Self {
            epoch: 0,
            nonce: 0,
            phase: ImagePhase::Live,
            first_run: FirstRun::Unprepared,
            #[cfg(feature = "g1c-trusted-observe")]
            initial_observe: None,
            #[cfg(feature = "g1c-trusted-observe")]
            observe_launcher: false,
            #[cfg(feature = "g1d-trusted-control")]
            initial_control: None,
        }
    }

    fn session(&mut self, next_nonce: &AtomicU64) -> Result<ProcessImageKey> {
        if self.phase != ImagePhase::Live {
            return_errno_with_message!(Errno::ESTALE, "HOS2 process image is closing or closed");
        }
        if self.nonce == 0 {
            self.nonce =
                match next_nonce.fetch_update(Ordering::AcqRel, Ordering::Acquire, |current| {
                    current.checked_add(1)
                }) {
                    Ok(nonce) => nonce,
                    Err(_) => {
                        self.phase = ImagePhase::Closed;
                        return_errno_with_message!(Errno::ENOSPC, "HOS2 CapSpace nonce exhausted");
                    }
                };
        }
        Ok(ProcessImageKey {
            epoch: self.epoch,
            nonce: self.nonce,
        })
    }

    fn check_session(&self, key: ProcessImageKey) -> Result<()> {
        if self.phase != ImagePhase::Live
            || self.nonce == 0
            || self.epoch != key.epoch
            || self.nonce != key.nonce
        {
            return_errno_with_message!(Errno::ESTALE, "HOS2 control fd belongs to an ended image");
        }
        Ok(())
    }

    fn begin_close(&mut self) {
        #[cfg(feature = "g1c-trusted-observe")]
        {
            self.initial_observe = None;
            self.observe_launcher = false;
        }
        if self.phase == ImagePhase::Live {
            self.phase = ImagePhase::Closing;
        }
    }

    fn close(&mut self) {
        #[cfg(feature = "g1c-trusted-observe")]
        {
            self.initial_observe = None;
            self.observe_launcher = false;
        }
        self.phase = ImagePhase::Closed;
    }

    fn commit_exec(&mut self) -> Result<u64> {
        if self.phase != ImagePhase::Closing {
            return_errno_with_message!(
                Errno::ESTALE,
                "HOS2 exec image is not awaiting replacement"
            );
        }
        // End the old image even if no new epoch can be allocated. Neither an
        // error nor a later open may make its old namespace live again.
        self.phase = ImagePhase::Closed;
        #[cfg(feature = "g1c-trusted-observe")]
        {
            self.initial_observe = None;
            self.observe_launcher = false;
        }
        let next = self
            .epoch
            .checked_add(1)
            .ok_or_else(|| Error::with_message(Errno::EOVERFLOW, "HOS2 exec epoch exhausted"))?;
        self.epoch = next;
        self.nonce = 0;
        self.phase = ImagePhase::Live;
        Ok(next)
    }

    pub(super) fn claim_unprepared_run(&mut self) -> Result<()> {
        if self.phase != ImagePhase::Live || self.first_run != FirstRun::Unprepared {
            return_errno_with_message!(Errno::ESTALE, "process first run has already been claimed");
        }
        self.first_run = FirstRun::Started;
        Ok(())
    }

    pub(super) fn prepare_initial(&mut self) -> Result<ProcessImageKey> {
        if self.first_run != FirstRun::Unprepared {
            return_errno_with_message!(Errno::ESTALE, "process is already prepared or started");
        }
        let key = self.session(&NEXT_HEPTA_CAPSPACE_NONCE)?;
        self.first_run = FirstRun::Prepared;
        Ok(key)
    }

    pub(super) fn consume_initial(&mut self, key: ProcessImageKey) -> Result<()> {
        self.check_session(key)?;
        if self.first_run != FirstRun::Prepared {
            return_errno_with_message!(
                Errno::ESTALE,
                "initial preparation has already been consumed"
            );
        }
        self.first_run = FirstRun::Started;
        Ok(())
    }

    pub(super) fn cancel_initial(&mut self, key: ProcessImageKey) {
        if self.first_run == FirstRun::Prepared
            && self.epoch == key.epoch
            && self.nonce == key.nonce
        {
            self.close();
        }
    }

    #[cfg(feature = "g1c-trusted-observe")]
    pub(super) fn activate_initial_observer(
        &mut self,
        key: ProcessImageKey,
        observer: Arc<NativeCpuObserver>,
        issued_ns: u64,
    ) -> Result<()> {
        self.check_session(key)?;
        if self.first_run != FirstRun::Prepared
            || self.initial_observe.is_some()
            || self.observe_launcher
        {
            return_errno_with_message!(Errno::ESTALE, "initial observe slot cannot be reactivated")
        }
        let expires_ns = issued_ns.checked_add(300_000_000_000).ok_or_else(|| {
            Error::with_message(Errno::EOVERFLOW, "initial observe lease overflow")
        })?;
        self.initial_observe = Some(InitialObserveGrant {
            observer,
            issued_ns,
            expires_ns,
            issuer: None,
        });
        Ok(())
    }

    #[cfg(feature = "g1c-trusted-observe")]
    pub(super) fn arm_initial_observe_launcher(&mut self, key: ProcessImageKey) -> Result<()> {
        self.check_session(key)?;
        if self.first_run != FirstRun::Prepared
            || self.observe_launcher
            || self.initial_observe.is_some()
        {
            return_errno_with_message!(
                Errno::ESTALE,
                "observe launcher is not a fresh initial image"
            );
        }
        #[cfg(feature = "g1d-trusted-control")]
        if self.initial_control.is_some() {
            return_errno_with_message!(Errno::EPERM, "control role is not an observe launcher");
        }
        self.observe_launcher = true;
        Ok(())
    }

    #[cfg(feature = "g1c-trusted-observe")]
    pub(super) fn check_observe_launcher(&self, key: ProcessImageKey) -> Result<()> {
        self.check_session(key)?;
        if !self.observe_launcher || self.first_run != FirstRun::Started {
            return_errno_with_message!(Errno::EPERM, "image has no live observe launch authority");
        }
        Ok(())
    }

    #[cfg(feature = "g1c-trusted-observe")]
    pub(super) fn postexec_observe_session(&mut self) -> Result<ProcessImageKey> {
        if self.first_run != FirstRun::Started || self.epoch == 0 {
            return_errno_with_message!(Errno::ESTALE, "observe recipient has not completed exec");
        }
        self.session(&NEXT_HEPTA_CAPSPACE_NONCE)
    }

    #[cfg(feature = "g1c-trusted-observe")]
    pub(super) fn check_postexec_observe_recipient(&self, key: ProcessImageKey) -> Result<()> {
        self.check_session(key)?;
        if self.first_run != FirstRun::Started || self.epoch == 0 || self.observe_launcher {
            return_errno_with_message!(Errno::ESTALE, "invalid post-exec observe recipient");
        }
        #[cfg(feature = "g1d-trusted-control")]
        if self.initial_control.is_some() {
            return_errno_with_message!(
                Errno::EPERM,
                "post-exec observe cannot replace control slots"
            );
        }
        Ok(())
    }

    #[cfg(feature = "g1c-trusted-observe")]
    pub(super) fn prepare_postexec_observer(
        &mut self,
        key: ProcessImageKey,
        grant: InitialObserveGrant,
        already_installed: bool,
    ) -> Result<PreparedPostexecObserve<'_>> {
        self.check_postexec_observe_recipient(key)?;
        if already_installed {
            let Some(existing) = self.initial_observe.as_ref() else {
                return_errno_with_message!(
                    Errno::ESTALE,
                    "installed observe slot no longer exists"
                );
            };
            if !Arc::ptr_eq(&existing.observer, &grant.observer)
                || existing.issued_ns != grant.issued_ns
                || existing.expires_ns != grant.expires_ns
                || !existing
                    .issuer
                    .as_ref()
                    .zip(grant.issuer.as_ref())
                    .is_some_and(|(a, b)| a.same_issuer(b))
            {
                return_errno_with_message!(
                    Errno::ESTALE,
                    "observe retry does not match installed slot"
                );
            }
            return Ok(PreparedPostexecObserve {
                slot: &mut self.initial_observe,
                grant: None,
            });
        }
        if self.initial_observe.is_some() {
            return_errno_with_message!(Errno::ESTALE, "observe slot cannot be overwritten");
        }
        Ok(PreparedPostexecObserve {
            slot: &mut self.initial_observe,
            grant: Some(grant),
        })
    }

    #[cfg(feature = "g1c-trusted-observe")]
    fn initial_observer(
        &self,
        key: ProcessImageKey,
        slot: u64,
        generation: u64,
    ) -> core::result::Result<&InitialObserveGrant, Status> {
        self.check_session(key).map_err(|_| Status::StaleHandle)?;
        let grant = self
            .initial_observe
            .as_ref()
            .ok_or(Status::PermissionDenied)?;
        if slot != 1 || generation != 1 {
            return Err(Status::StaleHandle);
        }
        Ok(grant)
    }

    #[cfg(feature = "g1d-trusted-control")]
    pub(super) fn activate_initial_control(
        &mut self,
        key: ProcessImageKey,
        slots: Arc<TrustedControlSlots>,
    ) -> Result<()> {
        self.check_session(key)?;
        if self.first_run != FirstRun::Prepared
            || self.initial_control.is_some()
            || self.initial_observe.is_some()
            || self.observe_launcher
            || !slots.belongs_to(key)
        {
            return_errno_with_message!(Errno::ESTALE, "initial control binding cannot be activated")
        }
        self.initial_control = Some(slots);
        Ok(())
    }

    #[cfg(feature = "g1d-trusted-control")]
    pub(super) fn initial_control(
        &self,
        key: ProcessImageKey,
    ) -> core::result::Result<&Arc<TrustedControlSlots>, Status> {
        self.check_session(key).map_err(|_| Status::StaleHandle)?;
        self.initial_control
            .as_ref()
            .ok_or(Status::PermissionDenied)
    }

    #[cfg(feature = "g1d-trusted-control")]
    pub(super) fn closing_control(&self) -> Option<Arc<TrustedControlSlots>> {
        if self.phase == ImagePhase::Live {
            None
        } else {
            self.initial_control.clone()
        }
    }
}

impl Process {
    /// Attach and writable proc-memory access must not change the initial
    /// image's registers or data through another Process, even as Linux root.
    #[cfg(feature = "g1c-trusted-observe")]
    pub(crate) fn has_initial_observe_authority(&self) -> bool {
        // Unlike the image grant, this external-control fence deliberately
        // survives later execs of the same Process allocation.
        if self.external_control_fence().is_fenced() {
            return true;
        }
        let image = self.hepta_image.lock();
        let has_authority = image.initial_observe.is_some() || image.observe_launcher;
        #[cfg(feature = "g1d-trusted-control")]
        let has_authority = has_authority || image.initial_control.is_some();
        image.phase == ImagePhase::Live && has_authority
    }

    /// Resolves the actual Process-owned slot around a read of the real CPU
    /// owner. No image mutex spans membership, runqueue or bandwidth locking.
    /// Because an image key/slot cannot close and then become live again, the
    /// successful checks bracket a valid read linearization point. A concurrent
    /// exec/exit loses the observation, without an effect needing rollback.
    #[cfg(feature = "g1c-trusted-observe")]
    pub(crate) fn read_hepta_initial_usage(
        &self,
        key: ProcessImageKey,
        slot: u64,
        generation: u64,
    ) -> core::result::Result<os_control::UsageSnapshot, Status> {
        let (observer, issued_ns, expires_ns, issuer) = {
            let image = self.hepta_image.lock();
            let grant = image.initial_observer(key, slot, generation)?;
            (
                grant.observer.clone(),
                grant.issued_ns,
                grant.expires_ns,
                grant.issuer.clone(),
            )
        };
        if let Some(issuer) = issuer.as_ref() {
            issuer.check().map_err(|_| Status::Revoked)?;
        }
        let usage =
            observer
                .read_usage_during(issued_ns, expires_ns)
                .map_err(|error| match error {
                    CpuUsageError::Unbound | CpuUsageError::Closed | CpuUsageError::Expired => {
                        Status::Revoked
                    }
                    CpuUsageError::Indeterminate
                    | CpuUsageError::ClockUnavailable
                    | CpuUsageError::UnsupportedProfile
                    | CpuUsageError::InconsistentAccounting => Status::Indeterminate,
                })?;
        let image = self.hepta_image.lock();
        let grant = image.initial_observer(key, slot, generation)?;
        if !Arc::ptr_eq(&grant.observer, &observer) {
            return Err(Status::StaleHandle);
        }
        check_initial_observe_lease(grant.issued_ns, grant.expires_ns, usage.sample_boottime_ns)?;
        drop(image);
        // Never take the issuer image lock while holding the recipient image.
        // A closed issuer/image cannot become live again with the same key.
        if let Some(issuer) = issuer.as_ref() {
            issuer.check().map_err(|_| Status::Revoked)?;
        }
        Ok(usage)
    }

    /// Assigns one checked, boot-local namespace to the current live image.
    /// Two opens share the same key. Closing/closed images cannot allocate one.
    pub(crate) fn hepta_capspace_session(&self) -> Result<ProcessImageKey> {
        self.hepta_image.lock().session(&NEXT_HEPTA_CAPSPACE_NONCE)
    }

    /// Checks the complete key and phase in the same Process-owned state.
    /// Callers must separately verify the exact Process allocation.
    pub(crate) fn check_hepta_capspace_session(&self, key: ProcessImageKey) -> Result<()> {
        self.hepta_image.lock().check_session(key)
    }

    /// Fences old-image sessions at irreversible exec or process-exit admission.
    ///
    /// Lifecycle callers hold TaskSet before taking this image mutex. This
    /// method never takes TaskSet, VMAR, membership, runqueue or resource locks.
    /// It does not release retained CPU debit owners or reset their accounting.
    pub(in crate::process) fn begin_hepta_image_close(&self) {
        self.hepta_image.lock().begin_close();
    }

    /// Completes a failed replacement or process exit without reopening it.
    pub(in crate::process) fn close_hepta_image(&self) {
        #[cfg(not(feature = "g1d-trusted-control"))]
        self.hepta_image.lock().close();
        #[cfg(feature = "g1d-trusted-control")]
        {
            let slots = {
                let mut image = self.hepta_image.lock();
                image.close();
                image.initial_control.take()
            };
            if let Some(slots) = slots {
                slots.revoke_after_image_close();
            }
        }
    }

    /// Commits a successful exec as a new image with no session or grant.
    /// An old image can never transition back to Live with its old key.
    pub(in crate::process) fn commit_hepta_exec_image(&self) -> Result<u64> {
        #[cfg(not(feature = "g1d-trusted-control"))]
        return self.hepta_image.lock().commit_exec();
        #[cfg(feature = "g1d-trusted-control")]
        {
            self.revoke_closing_hepta_control();
            let (result, slots) = {
                let mut image = self.hepta_image.lock();
                let slots = if image.phase == ImagePhase::Closing {
                    image.initial_control.take()
                } else {
                    None
                };
                (image.commit_exec(), slots)
            };
            // Namespace and resource pins may have meaningful destructors.
            // Release them after the image lock, including on epoch overflow.
            drop(slots);
            result
        }
    }
}

#[cfg(ktest)]
mod tests {
    use ostd::prelude::ktest;

    use super::*;
    use crate::process::{posix_thread::AsPosixThread, test_util};

    #[ktest]
    fn initial_observe_lease_includes_issue_and_excludes_expiry() {
        let issued = 123;
        let expires = issued + 300_000_000_000;
        assert_eq!(check_initial_observe_lease(issued, expires, issued), Ok(()));
        assert_eq!(
            check_initial_observe_lease(issued, expires, expires - 1),
            Ok(())
        );
        assert_eq!(
            check_initial_observe_lease(issued, expires, expires),
            Err(Status::Revoked)
        );
        assert_eq!(
            check_initial_observe_lease(issued, expires, expires + 1),
            Err(Status::Revoked)
        );
    }

    #[ktest]
    fn initial_observe_lease_does_not_accept_a_pre_issue_clock_cut() {
        assert_eq!(
            check_initial_observe_lease(10, 20, 9),
            Err(Status::Indeterminate)
        );
        assert_eq!(
            check_initial_observe_lease(u64::MAX - 1, u64::MAX, u64::MAX - 2),
            Err(Status::Indeterminate)
        );
    }

    // These use actual unstarted Process/Task allocations. They do not execute
    // execve/exit syscalls or establish resource grants; the ordinary guest
    // regression covers the syscall path independently.

    #[track_caller]
    fn assert_stale<T: Debug>(result: Result<T>) {
        assert_eq!(result.unwrap_err().error(), Errno::ESTALE);
    }

    #[ktest]
    fn repeated_opens_share_one_process_image_namespace() {
        let (process, _task) = test_util::new_unstarted_process();
        let key = process.hepta_capspace_session().unwrap();
        assert_ne!(key.nonce(), 0);
        assert_eq!(key, process.hepta_capspace_session().unwrap());
        assert!(process.check_hepta_capspace_session(key).is_ok());
    }

    #[ktest]
    fn separately_allocated_process_rejects_foreign_image_key() {
        let (parent, _parent_task) = test_util::new_unstarted_process();
        let (child, _child_task) = test_util::new_unstarted_process();
        let parent_key = parent.hepta_capspace_session().unwrap();
        let child_key = child.hepta_capspace_session().unwrap();
        assert_ne!(parent_key.nonce(), child_key.nonce());
        assert_stale(child.check_hepta_capspace_session(parent_key));
    }

    #[ktest]
    fn same_process_tasks_observe_one_live_image() {
        let (process, tasks) = test_util::new_unstarted_process_with_threads(2);
        let key = tasks[0]
            .as_posix_thread()
            .unwrap()
            .process()
            .hepta_capspace_session()
            .unwrap();
        assert!(Arc::ptr_eq(
            &tasks[1].as_posix_thread().unwrap().process(),
            &process
        ));
        assert_eq!(
            tasks[1]
                .as_posix_thread()
                .unwrap()
                .process()
                .hepta_capspace_session()
                .unwrap(),
            key
        );
    }

    #[ktest]
    fn closing_fences_old_sessions_before_image_replacement() {
        let (process, _task) = test_util::new_unstarted_process();
        let key = process.hepta_capspace_session().unwrap();
        process.begin_hepta_image_close();
        assert_stale(process.check_hepta_capspace_session(key));
        assert_stale(process.hepta_capspace_session());
        assert_eq!(process.hepta_image.lock().nonce, key.nonce);
    }

    #[ktest]
    fn failed_irreversible_replacement_never_reopens_the_old_image() {
        let (process, _task) = test_util::new_unstarted_process();
        let key = process.hepta_capspace_session().unwrap();
        process.begin_hepta_image_close();
        process.close_hepta_image();
        process.begin_hepta_image_close();
        assert_stale(process.commit_hepta_exec_image());
        assert_stale(process.hepta_capspace_session());
        assert_eq!(process.hepta_image.lock().nonce, key.nonce);
        assert_eq!(process.hepta_image.lock().phase, ImagePhase::Closed);
    }

    #[ktest]
    fn successful_replacement_has_new_epoch_and_fresh_namespace() {
        let (process, _task) = test_util::new_unstarted_process();
        process.hepta_image.lock().claim_unprepared_run().unwrap();
        let old_key = process.hepta_capspace_session().unwrap();
        process.begin_hepta_image_close();
        assert_eq!(
            process.commit_hepta_exec_image().unwrap(),
            old_key.epoch + 1
        );
        let new_key = process.hepta_capspace_session().unwrap();
        assert_ne!(new_key.nonce, old_key.nonce);
        assert_eq!(new_key.epoch, old_key.epoch + 1);
        assert_stale(process.check_hepta_capspace_session(old_key));
        assert!(process.check_hepta_capspace_session(new_key).is_ok());
        assert_stale(process.hepta_image.lock().claim_unprepared_run());
    }

    #[ktest]
    fn epoch_exhaustion_closes_the_real_process_without_wraparound() {
        let (process, _task) = test_util::new_unstarted_process();
        // Set only the counter boundary on the original Process state; the
        // production commit/open functions must provide the refusal.
        process.hepta_image.lock().epoch = u64::MAX;
        let key = process.hepta_capspace_session().unwrap();
        process.begin_hepta_image_close();
        assert_eq!(
            process.commit_hepta_exec_image().unwrap_err().error(),
            Errno::EOVERFLOW
        );
        assert_stale(process.check_hepta_capspace_session(key));
        assert_stale(process.hepta_capspace_session());
        assert_eq!(process.hepta_image.lock().epoch, u64::MAX);
    }

    #[ktest]
    fn nonce_exhaustion_is_sticky_for_the_real_process_image() {
        let (process, _task) = test_util::new_unstarted_process();
        // A private allocator avoids poisoning other tests' boot-global nonce.
        // The same production allocation and failure path updates this Process.
        let exhausted = AtomicU64::new(u64::MAX);
        assert_eq!(
            process
                .hepta_image
                .lock()
                .session(&exhausted)
                .unwrap_err()
                .error(),
            Errno::ENOSPC
        );
        assert_eq!(exhausted.load(Ordering::Acquire), u64::MAX);
        assert_stale(process.hepta_capspace_session());
        assert_eq!(process.hepta_image.lock().nonce, 0);
    }

    #[ktest]
    fn closed_image_cannot_be_prepared_or_scheduled_for_the_first_time() {
        let (process, _task) = test_util::new_unstarted_process();
        process.close_hepta_image();
        assert_stale(process.hepta_image.lock().prepare_initial());
        assert_stale(process.hepta_image.lock().claim_unprepared_run());
    }
}
