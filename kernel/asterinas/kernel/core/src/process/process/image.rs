// SPDX-License-Identifier: MPL-2.0

//! Process-image lifetime for the read-only HOS2 bootstrap.
//!
//! An image key identifies an allocation; it grants no resource authority.
//! Closing only fences discovery and sessions here. Canonical resource-owner
//! admission and revocation must be added together before enabling effects.

use core::sync::atomic::{AtomicU64, Ordering};

use super::Process;
use crate::prelude::*;

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
}

impl ProcessImageState {
    pub(super) fn new() -> Self {
        Self {
            epoch: 0,
            nonce: 0,
            phase: ImagePhase::Live,
            first_run: FirstRun::Unprepared,
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
        if self.phase == ImagePhase::Live {
            self.phase = ImagePhase::Closing;
        }
    }

    fn close(&mut self) {
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
}

impl Process {
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
        self.hepta_image.lock().close();
    }

    /// Commits a successful exec as a new image with no session or grant.
    /// An old image can never transition back to Live with its old key.
    pub(in crate::process) fn commit_hepta_exec_image(&self) -> Result<u64> {
        self.hepta_image.lock().commit_exec()
    }
}

#[cfg(ktest)]
mod tests {
    use ostd::prelude::ktest;

    use super::*;
    use crate::process::{posix_thread::AsPosixThread, test_util};

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
