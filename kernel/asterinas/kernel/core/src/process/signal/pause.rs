// SPDX-License-Identifier: MPL-2.0

use ostd::sync::{WaitQueue, Waiter};

use super::{constants::SIGCONT, sig_mask::SigMask};
use crate::{
    prelude::*,
    process::{
        posix_thread::{AsPosixThread, ContextPthreadAdminApi, PosixThread},
        signal::HandlePendingSignal,
    },
    thread::AsThread,
    time::{
        timer::TimerGuard,
        wait::{ManagedTimeout, TimeoutExt},
    },
};

/// `Pause` is an extension trait to make [`Waiter`] and [`WaitQueue`] signal aware.
///
/// The original methods of `Waiter` and `WaitQueue` only allow a thread
/// to wait (via `wait`) until it is woken up (via `wake_up`, `wake_one`, or `wake_all`)
/// or a condition is met (via `wait_until`).
/// The `WaitTimeout` extension trait grants the extra ability
/// to wait until a timeout (via `wait_until_or_timeout`).
/// On top of `WaitTimeout`, this `Pause` trait provides the `pause`-family methods,
/// which are similar to the `wait`-family methods except that the methods also return
/// when the waiting thread is interrupted by a POSIX signal.
/// When this happens, the `pause`-family methods return `Err(EINTR)`.
pub(crate) trait Pause: WaitTimeout {
    /// Pauses until the condition is met or a signal interrupts.
    ///
    /// # Errors
    ///
    /// This method will return an error with [`EINTR`] if a signal is received before the
    /// condition is met.
    ///
    /// [`EINTR`]: crate::error::Errno::EINTR
    #[track_caller]
    fn pause_until<F, R>(&self, cond: F) -> Result<R>
    where
        F: FnMut() -> Option<R>,
    {
        self.pause_until_or_timeout_impl(cond, None, PauseReason::Sleep)
    }

    /// Pauses until the condition is met or a signal interrupts.
    ///
    /// This pause happens due to the reason specified. If the reason is `PauseReason::Sleep`,
    /// the caller should use `pause_until` straightforwardly.
    ///
    /// If the reason is `PauseReason::StopByPtrace`, it can only be interrupted by `SIGKILL`.
    ///
    /// # Errors
    ///
    /// This method will return an error with [`EINTR`] if a signal is received before the
    /// condition is met.
    ///
    /// [`EINTR`]: crate::error::Errno::EINTR
    #[track_caller]
    fn pause_until_by<F, R>(&self, cond: F, reason: PauseReason) -> Result<R>
    where
        F: FnMut() -> Option<R>,
    {
        self.pause_until_or_timeout_impl(cond, None, reason)
    }

    /// Pauses until the condition is met, the timeout is reached, or a signal interrupts.
    ///
    /// # Errors
    ///
    /// Before the condition is met, this method will return an error with
    ///  - [`EINTR`] if a signal is received;
    ///  - [`ETIME`] if the timeout is reached.
    ///
    /// [`ETIME`]: crate::error::Errno::ETIME
    /// [`EINTR`]: crate::error::Errno::EINTR
    #[track_caller]
    fn pause_until_or_timeout<'a, F, T, R>(&self, mut cond: F, timeout: T) -> Result<R>
    where
        F: FnMut() -> Option<R>,
        T: Into<TimeoutExt<'a>>,
    {
        let timeout = timeout.into();
        let timeout_inner = match timeout.check_expired() {
            Ok(inner) => inner,
            Err(err) => return cond().ok_or(err),
        };

        self.pause_until_or_timeout_impl(cond, timeout_inner, PauseReason::Sleep)
    }

    /// Pauses until the condition is met, the timeout is reached, or a signal interrupts.
    ///
    /// # Errors
    ///
    /// Before the condition is met, this method will return an error with
    ///  - [`EINTR`] if a signal is received;
    ///  - [`ETIME`] if the timeout is reached.
    ///
    /// [`ETIME`]: crate::error::Errno::ETIME
    /// [`EINTR`]: crate::error::Errno::EINTR
    #[doc(hidden)]
    #[track_caller]
    fn pause_until_or_timeout_impl<F, R>(
        &self,
        cond: F,
        timeout: Option<&ManagedTimeout>,
        reason: PauseReason,
    ) -> Result<R>
    where
        F: FnMut() -> Option<R>;

    /// Pauses until the thread is woken up, the timeout is reached, or a signal interrupts.
    ///
    /// # Errors
    ///
    /// This method will return an error with
    ///  - [`EINTR`] if a signal is received;
    ///  - [`ETIME`] if the timeout is reached.
    ///
    /// [`ETIME`]: crate::error::Errno::ETIME
    /// [`EINTR`]: crate::error::Errno::EINTR
    #[track_caller]
    fn pause_timeout(&self, timeout: &TimeoutExt<'_>) -> Result<()>;
}

impl Pause for Waiter {
    fn pause_until_or_timeout_impl<F, R>(
        &self,
        cond: F,
        timeout: Option<&ManagedTimeout>,
        reason: PauseReason,
    ) -> Result<R>
    where
        F: FnMut() -> Option<R>,
    {
        // No fast paths for `Waiter`. If the caller wants a fast path, it should do so _before_
        // the waiter is created.

        let Some(posix_thread) = self
            .task()
            .as_thread()
            .and_then(|thread| thread.as_posix_thread())
        else {
            return self.wait_until_or_timeout_cancelled(cond, || Ok(()), timeout);
        };

        let cancel_cond = || {
            if matches!(reason, PauseReason::Sleep) {
                wait_for_group_resume(self, posix_thread)?;
            }
            let has_pending = match reason {
                PauseReason::StopByPtrace => posix_thread.has_pending_sigkill(),
                _ => posix_thread.has_pending(),
            };

            if has_pending {
                return Err(Error::with_message(
                    Errno::EINTR,
                    "the current thread is interrupted by a signal",
                ));
            }
            Ok(())
        };

        posix_thread.set_signalled_waker(self.waker(), reason);
        let res = self.wait_until_or_timeout_cancelled(cond, cancel_cond, timeout);
        posix_thread.clear_signalled_waker();

        res
    }

    fn pause_timeout(&self, timeout: &TimeoutExt<'_>) -> Result<()> {
        let timer = timeout.check_expired()?.map(|timeout| {
            let waker = self.waker();
            timeout.create_timer(move |_guard: TimerGuard| {
                waker.wake_up();
            })
        });

        let posix_thread_opt = self
            .task()
            .as_thread()
            .and_then(|thread| thread.as_posix_thread());

        if let Some(posix_thread) = posix_thread_opt {
            posix_thread.set_signalled_waker(self.waker(), PauseReason::Sleep);
            // Check the stop condition and pending signals only after
            // registration, so publishing either condition cannot lose a wake.
            let result = (|| {
                wait_for_group_resume(self, posix_thread)?;
                if posix_thread.has_pending() {
                    return_errno_with_message!(
                        Errno::EINTR,
                        "the current thread is interrupted by a signal"
                    );
                }
                self.wait();
                wait_for_group_resume(self, posix_thread)
            })();
            posix_thread.clear_signalled_waker();
            if let Err(error) = result {
                if let Some(timer) = timer {
                    timer.lock().cancel();
                }
                return Err(error);
            }
        } else {
            self.wait();
        }

        if let Some(timer) = timer {
            let timer_guard = timer.lock();
            if timer_guard.remain().is_zero() {
                return_errno_with_message!(Errno::ETIME, "the time limit is reached");
            }
            // If the timeout is not expired, cancel the timer manually.
            timer_guard.cancel();
        }

        if posix_thread_opt
            .as_ref()
            .is_some_and(|posix_thread| posix_thread.has_pending())
        {
            return_errno_with_message!(
                Errno::EINTR,
                "the current thread is interrupted by a signal"
            );
        }

        Ok(())
    }
}

/// Joins an already-published process stop without completing the original
/// interruptible wait on ordinary I/O/timer wakes. Registrations and the
/// original timeout stay live. SIGKILL or an unmasked targeted SIGCONT instead
/// return to the original signal handling path; no signal is synthesized.
fn wait_for_group_resume(waiter: &Waiter, posix_thread: &PosixThread) -> Result<()> {
    let process = posix_thread.process();
    if !process.is_stopped() {
        return Ok(());
    }

    struct RestoreReason<'a>(&'a PosixThread, PauseReason);
    impl Drop for RestoreReason<'_> {
        fn drop(&mut self) {
            self.0.replace_pause_reason(self.1);
        }
    }
    let previous = posix_thread.replace_pause_reason(PauseReason::StopBySignal);
    let restore = RestoreReason(posix_thread, previous);
    // No process/task-set or condition lock is held while waiting. The thread
    // that handles the stopping signal remains in the user-return stop loop,
    // where it can process process-directed SIGCONT. A thread-directed SIGCONT
    // can instead be queued only to this sleeping sibling: return through the
    // original signal path so that it is dequeued and handled exactly once.
    // Do not repeatedly resume from a pending CONT level; a blocked old CONT
    // must not cancel a subsequent stop. The existing masked/ignored CONT
    // generation-time semantics are not changed by this wait implementation.
    let result = waiter.wait_until_or_cancelled(
        || (!process.is_stopped()).then_some(()),
        || {
            if posix_thread.has_pending_sigkill()
                || (!posix_thread.sig_mask().contains(SIGCONT)
                    && posix_thread.sig_queues().has_pending_signal(SIGCONT))
            {
                return_errno_with_message!(
                    Errno::EINTR,
                    "group-stopped wait requires signal handling"
                );
            }
            Ok(())
        },
    );
    drop(restore);
    // The nested stop wait may have consumed the original I/O or timer wake.
    // Force the outer wait to recheck its condition and original deadline;
    // do not restart a relative timeout or wait for an event already delivered.
    waiter.waker().wake_up();
    result
}

impl Pause for WaitQueue {
    fn pause_until_or_timeout_impl<F, R>(
        &self,
        mut cond: F,
        timeout: Option<&ManagedTimeout>,
        reason: PauseReason,
    ) -> Result<R>
    where
        F: FnMut() -> Option<R>,
    {
        // Fast path:
        if let Some(res) = cond() {
            return Ok(res);
        }

        let (waiter, _) = Waiter::new_pair();
        let cond = || {
            self.enqueue(waiter.waker());
            cond()
        };
        waiter.pause_until_or_timeout_impl(cond, timeout, reason)
    }

    fn pause_timeout(&self, _timeout: &TimeoutExt<'_>) -> Result<()> {
        panic!("`pause_timeout` can only be used on `Waiter`");
    }
}

/// The reason why a process is paused by a `pause`-family method.
#[derive(Debug, Clone, Copy)]
pub(crate) enum PauseReason {
    Sleep,
    StopBySignal,
    StopByPtrace,
}

/// Executes a closure after temporarily adjusting the signal mask of the current POSIX thread.
pub(crate) fn with_sigmask_changed<R>(
    ctx: &Context,
    mask_op: impl FnOnce(SigMask) -> SigMask,
    operate: impl FnOnce() -> R,
) -> R {
    // Save the original signal mask and apply the mask updates.
    let old_mask = ctx.posix_thread.sig_mask();
    ctx.set_sig_mask(mask_op(old_mask));

    // Perform the operation.
    let res = operate();

    // Restore the original signal mask.
    ctx.set_sig_mask(old_mask);

    res
}

#[cfg(ktest)]
mod test {
    use core::sync::atomic::{AtomicBool, Ordering};

    use ostd::prelude::*;

    use super::*;
    use crate::thread::{Thread, kernel_thread::ThreadOptions};

    #[ktest]
    fn waiter_pause() {
        let wait_queue = Arc::new(WaitQueue::new());
        let wait_queue_cloned = wait_queue.clone();

        let boolean = Arc::new(AtomicBool::new(false));
        let boolean_cloned = boolean.clone();

        let thread = ThreadOptions::new(move || {
            Thread::yield_now();

            boolean_cloned.store(true, Ordering::Relaxed);
            wait_queue_cloned.wake_all();
        })
        .spawn();

        wait_queue
            .pause_until(|| boolean.load(Ordering::Relaxed).then_some(()))
            .unwrap();

        thread.join();
    }
}
