// SPDX-License-Identifier: MPL-2.0

//! Fixed G1-d failover, independent of either user-space management image.
//!
//! The timer owns no quota or revision. It uses the original local-runqueue ->
//! bandwidth-lock settlement path and the original NativeResourceState::apply.
//! Registration allocates before any role runs; a tick allocates nothing, does
//! not wait, does not print, and never calls Process::resume or sends SIGCONT.

use os_control::NativeResourceReceipt;

use super::*;
use crate::process::{Process, ProcessStatusObserver};

/// Immutable boot policy, strictly inside the existing recovery grace period.
pub(super) const WATCHDOG_DELAY_NS: u64 = 5_000_000_000;
const _: () = assert!(WATCHDOG_DELAY_NS < RECOVERY_GRACE_NS);

/// A bounded, immutable outcome for this boot policy, not a D namespace.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) enum WatchdogOutcome {
    Restored(NativeResourceReceipt),
    Ineligible,
    JobStopped,
    Expired,
    ClockUnavailable,
    Closed,
    AccountingFault,
}

impl WatchdogOutcome {
    fn code(self) -> u8 {
        match self {
            Self::Restored(_) => 1,
            Self::Ineligible => 2,
            Self::JobStopped => 3,
            Self::Expired => 4,
            Self::ClockUnavailable => 5,
            Self::Closed => 6,
            Self::AccountingFault => 7,
        }
    }
}

pub(super) struct WatchdogState {
    pub(super) armed: bool,
    // Diagnostic callback count only; never a UsageSnapshot event sequence.
    ticks: u64,
    // Read-only view of the original status; never a second stop-state owner.
    pub(super) workload: Option<ProcessStatusObserver>,
    pub(super) terminal: Option<(WatchdogOutcome, Option<u64>)>,
}

impl WatchdogState {
    pub(super) fn new() -> Self {
        Self {
            armed: false,
            ticks: 0,
            workload: None,
            terminal: None,
        }
    }
}

impl NativeCpuManager {
    /// Only the stopped, sealed bootstrap calls this once for the manager.
    /// The timer observes the original status without keeping Process alive;
    /// caller-supplied booleans, PIDs and labels cannot establish pause intent.
    pub(crate) fn arm_watchdog(
        self: &Arc<Self>,
        workload: Arc<Process>,
    ) -> crate::prelude::Result<()> {
        use crate::prelude::*;

        if self.index != 0 || ostd::cpu::all_cpus().count() != 1 {
            return_errno_with_message!(Errno::EOPNOTSUPP, "watchdog requires the fixed N0 manager")
        }
        let manager = self.clone();
        let status = workload.status_observer();
        drop(workload);
        let _irq = ostd::irq::disable_local();
        {
            let control = self.observer.owner.inner.as_ref().unwrap().control()?;
            let mut state = control.max.lock();
            let policy = state
                .trusted_management
                .as_mut()
                .ok_or_else(|| Error::with_message(Errno::ESTALE, "watchdog owner is closed"))?;
            if policy.watchdog.armed {
                return_errno_with_message!(Errno::EALREADY, "watchdog already registered")
            }
            policy.watchdog.workload = Some(status.clone());
            policy.watchdog.armed = true;
        }
        // OSTD's existing interrupt callback list is allocated here, not on
        // expiry (unlike TimerManager's Vec/Arc expiry machinery). This one
        // immutable registration lasts for the fixed qualification boot.
        ostd::timer::register_callback_on_cpu(move || {
            manager.watchdog_timer_tick(&status);
        });
        Ok(())
    }

    fn watchdog_timer_tick(&self, workload: &ProcessStatusObserver) {
        let now = aster_time::try_read_monotonic_sample().and_then(|sample| sample.checked_nanos());
        let current = self.observer.node.controller().cpu.read();
        if !Arc::ptr_eq(&current.get(), &self.observer.owner) {
            return;
        }
        let Some(control) = self
            .observer
            .owner
            .inner
            .as_ref()
            .and_then(|cpu| cpu.control.as_ref())
        else {
            return;
        };
        {
            // A healthy/not-yet-due/terminal tick needs no second runqueue
            // settlement. Release this owner lock before acquiring the
            // runqueue; the final path revalidates everything after settling.
            let mut state = control.max.lock();
            let Some(policy) = state.trusted_management.as_mut() else {
                return;
            };
            if !policy.watchdog.armed {
                return;
            }
            policy.watchdog.ticks = policy.watchdog.ticks.saturating_add(1);
            if !state.watchdog_ready(
                now,
                self.issued_ns,
                workload.is_stopped(),
                !workload.is_zombie(),
            ) {
                return;
            }
        }
        crate::sched::with_current_cpu_bandwidth_settled(|now| {
            self.watchdog_tick_at(now, workload)
        });
    }

    pub(super) fn watchdog_tick_at(&self, now: Option<u64>, workload: &ProcessStatusObserver) {
        let current = self.observer.node.controller().cpu.read();
        if !Arc::ptr_eq(&current.get(), &self.observer.owner) {
            return;
        }
        let Some(control) = self
            .observer
            .owner
            .inner
            .as_ref()
            .and_then(|cpu| cpu.control.as_ref())
        else {
            return;
        };
        // N0: IRQ exclusion prevents another task changing job-control state
        // between this original atomic observation and the CPU-owner check.
        // No Process/TaskSet/image lock is acquired while holding the runqueue.
        let stopped = workload.is_stopped();
        let alive = !workload.is_zombie();
        control
            .max
            .lock()
            .watchdog_tick(now, self.issued_ns, stopped, alive);
    }
}

impl CpuBandwidthState {
    pub(super) fn watchdog_ready(
        &mut self,
        now: Option<u64>,
        issued: u64,
        stopped: bool,
        alive: bool,
    ) -> bool {
        let Some(policy) = self.trusted_management.as_ref() else {
            return false;
        };
        if !policy.watchdog.armed {
            return false;
        }
        if policy.watchdog.terminal.is_some() {
            return false;
        }
        let finish = |state: &mut Self, outcome| {
            state.trusted_management.as_mut().unwrap().watchdog.terminal = Some((outcome, now));
        };
        if self.is_detached || !alive || self.native.as_ref().is_none_or(|state| state.is_fenced())
        {
            finish(self, WatchdogOutcome::Closed);
            return false;
        }
        let Some(now) = now.filter(|now| *now >= issued && *now >= self.max.last_observed_ns)
        else {
            finish(self, WatchdogOutcome::ClockUnavailable);
            return false;
        };
        let cut = match policy.manager_closed {
            ManagerClosure::At(cut) => cut.min(policy.manager_expires_ns),
            ManagerClosure::ClockUnavailable => {
                finish(self, WatchdogOutcome::ClockUnavailable);
                return false;
            }
            ManagerClosure::Open if policy.grants[0].is_revoked() => {
                finish(self, WatchdogOutcome::ClockUnavailable);
                return false;
            }
            ManagerClosure::Open if now < policy.manager_expires_ns => return false,
            ManagerClosure::Open => policy.manager_expires_ns,
        };
        // prepare_pair validated expiry + grace. Earlier first-close cuts
        // can only shorten both endpoints; duplicate revocation cannot renew.
        if now < cut {
            finish(self, WatchdogOutcome::ClockUnavailable);
            return false;
        }
        if now < cut + WATCHDOG_DELAY_NS {
            return false;
        }
        if now >= cut + RECOVERY_GRACE_NS {
            finish(self, WatchdogOutcome::Expired);
            return false;
        }
        if stopped {
            finish(self, WatchdogOutcome::JobStopped);
            return false;
        }
        if !policy.recovery_budget_allowed(self.max.quota_ns(), policy.restore_cap_ns) {
            finish(self, WatchdogOutcome::Ineligible);
            return false;
        }
        true
    }

    fn watchdog_tick(&mut self, now: Option<u64>, issued: u64, stopped: bool, alive: bool) {
        if !self.watchdog_ready(now, issued, stopped, alive) {
            return;
        }
        let now = now.unwrap(); // Admitted by watchdog_ready under this same owner lock.
        let usage = match self.sample_usage(now) {
            Ok(usage) => usage,
            Err(_) => {
                self.trusted_management.as_mut().unwrap().watchdog.terminal =
                    Some((WatchdogOutcome::AccountingFault, Some(now)));
                return;
            }
        };
        let native = self.native.as_mut().unwrap();
        let policy = self.trusted_management.as_mut().unwrap();
        let update = NativeResourceUpdate {
            target: native.id(),
            stable_object_id: native.stable_object_id(),
            expected_revision: native.revision(),
            period_ns: CPU_PERIOD_NS,
            cap_ns: policy.restore_cap_ns,
        };
        let max = &mut self.max;
        let outcome = match native.apply(update, now, usage.window_consumed_ns, &mut || {
            // Preserve settled consumption and positive carry debt. Consume
            // the very same one-effect recovery allowance as the recovery
            // delegation, so no late role can perform another restoration.
            max.reconfigure_native(update.cap_ns, now);
            policy.applied(1, update.cap_ns, true);
        }) {
            Ok(receipt) => WatchdogOutcome::Restored(receipt),
            Err(_) => WatchdogOutcome::AccountingFault,
        };
        policy.watchdog.terminal = Some((outcome, Some(now)));
    }
}

/// Copies bounded diagnostics, then releases the owner before any user copy.
/// The job-stop value is a fresh read of Process::status, not a retained pause
/// state. Zero available means the process no longer exists, not "running".
impl CpuController {
    pub(in crate::fs::cgroupfs::controller::cpu) fn read_watchdog_stat(
        &self,
        printer: &mut aster_util::printer::VmPrinter,
    ) -> aster_systree::Result<()> {
        let Some(control) = &self.control else {
            return Ok(());
        };
        let (armed, terminal, workload, cut, ticks) = {
            let state = control.max.lock();
            let Some(policy) = state.trusted_management.as_ref() else {
                return Ok(());
            };
            (
                policy.watchdog.armed,
                policy.watchdog.terminal,
                policy.watchdog.workload.clone(),
                match policy.manager_closed {
                    ManagerClosure::At(cut) => Some(cut.min(policy.manager_expires_ns)),
                    ManagerClosure::Open => Some(policy.manager_expires_ns),
                    ManagerClosure::ClockUnavailable => None,
                },
                policy.watchdog.ticks,
            )
        };
        let stopped = workload
            .as_ref()
            .filter(|status| !status.is_zombie())
            .map(|status| status.is_stopped());
        // This is a view of the original status allocation, not a Process
        // reference. Neither observation is represented as trusted user intent.
        drop(workload);
        writeln!(printer, "hepta_watchdog_armed {}", u8::from(armed))?;
        writeln!(printer, "hepta_watchdog_ticks {}", ticks)?;
        writeln!(
            printer,
            "hepta_watchdog_due_ns {}",
            cut.map_or(0, |cut| cut + WATCHDOG_DELAY_NS)
        )?;
        writeln!(
            printer,
            "hepta_watchdog_expires_ns {}",
            cut.map_or(0, |cut| cut + RECOVERY_GRACE_NS)
        )?;
        writeln!(
            printer,
            "hepta_watchdog_status {}",
            terminal.map_or(0, |(outcome, _)| outcome.code())
        )?;
        writeln!(
            printer,
            "hepta_watchdog_evaluated_ns {}",
            terminal.and_then(|(_, time)| time).unwrap_or(0)
        )?;
        writeln!(
            printer,
            "hepta_job_stop_available {}",
            u8::from(stopped.is_some())
        )?;
        writeln!(
            printer,
            "hepta_job_stopped {}",
            u8::from(stopped.unwrap_or(false))
        )?;
        writeln!(printer, "hepta_user_pause_intent_available 0")?;
        if let Some((WatchdogOutcome::Restored(receipt), _)) = terminal {
            let stable_id = u128::from_le_bytes(receipt.stable_object_id().bytes());
            writeln!(printer, "hepta_watchdog_stable_id_low {}", stable_id as u64)?;
            writeln!(
                printer,
                "hepta_watchdog_stable_id_high {}",
                (stable_id >> 64) as u64
            )?;
            writeln!(
                printer,
                "hepta_watchdog_previous_revision {}",
                receipt.previous_revision()
            )?;
            writeln!(printer, "hepta_watchdog_revision {}", receipt.revision())?;
            writeln!(
                printer,
                "hepta_watchdog_effective_ns {}",
                receipt.effective_boottime_ns()
            )?;
            writeln!(
                printer,
                "hepta_watchdog_consumed_ns {}",
                receipt.consumed_at_apply_ns()
            )?;
        }
        Ok(())
    }
}
