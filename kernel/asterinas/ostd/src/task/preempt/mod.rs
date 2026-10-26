// SPDX-License-Identifier: MPL-2.0

pub(super) mod cpu_local;
mod guard;

pub use self::guard::{DisabledPreemptGuard, disable_preempt};

/// Halts the CPU until interrupts if no preemption is required.
///
/// This function will return if:
///  - preemption is required when calling this function,
///  - preemption is required during halting the CPU, or
///  - interrupts occur during halting the CPU.
///
/// This function will perform preemption before returning if
/// preemption is required.
///
/// # Panics
///
/// This function will panic if it is called in the atomic mode
/// ([`crate::task::atomic_mode`]).
#[track_caller]
pub fn halt_cpu() {
    crate::task::atomic_mode::might_sleep();

    // An idle CPU may never switch tasks, but it must still report quiescent
    // states so deferred frame destruction and other RCU callbacks progress.
    // `might_sleep` permits bootstrap callers in atomic mode. Check the raw
    // state too, so that exemption can never publish a false quiescent state.
    if cpu_local::get_guard_count() == 0 && crate::arch::irq::is_local_enabled() {
        // SAFETY: RCU read-side critical sections require atomic mode. The raw
        // checks above exclude both preemption guards and disabled local IRQs,
        // including in bootstrap. Report before disabling IRQs or halting.
        unsafe {
            crate::sync::finish_grace_period();
        }
    }

    let irq_guard = crate::irq::disable_local();

    if cpu_local::need_preempt() {
        drop(irq_guard);
    } else {
        core::mem::forget(irq_guard);
        // IRQs were previously enabled (checked by `might_sleep`). So we can re-enable them now.
        crate::arch::irq::enable_local_and_halt();
    }

    super::scheduler::might_preempt();
}
