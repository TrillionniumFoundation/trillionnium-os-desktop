// SPDX-License-Identifier: MPL-2.0

use alloc::sync::Arc;
use core::sync::atomic::{AtomicU32, Ordering};

use aster_systree::{Error, MAX_ATTR_SIZE, Result, SysAttrSetBuilder, SysPerms, SysStr};
use aster_util::{per_cpu_counter::PerCpuCounter, printer::VmPrinter};
use ostd::{
    arch::{read_tsc, tsc_freq},
    cpu::CpuId,
    mm::{VmReader, VmWriter},
    sync::{LocalIrqDisabled, SpinLock},
    task::{Task, atomic_mode::AsAtomicModeGuard},
    timer::Jiffies,
    warn,
};

use crate::{
    fs::cgroupfs::systree_node::{CgroupSysNode, CgroupSystem},
    process::{Process, posix_thread::AsPosixThread},
    thread::AsThread,
    util::ReadCString,
};

/// A sub-controller responsible for CPU resource management in the cgroup subsystem.
///
/// This controller always exists so that `cpu.stat` remains readable even before `+cpu`
/// is enabled. When inactive, only the base usage fields are exposed and the non-root
/// CPU control files are hidden.
pub(crate) struct CpuController {
    /// Persistent CPU usage accounting for this cgroup.
    stats: CpuStats,
    /// Optional CPU resource control attributes exposed only when `+cpu` is active.
    control: Option<CpuControl>,
}

/// CPU usage accounting that survives CPU controller toggles.
struct CpuStats {
    /// A counter accumulates CPU time spent executing user-space code.
    ///
    /// The counter is in units of one [`Jiffies`] per increment.
    user: PerCpuCounter,
    /// A counter accumulates CPU time spent executing kernel code on behalf of tasks.
    ///
    /// The counter is in units of one [`Jiffies`] per increment.
    system: PerCpuCounter,
}

/// CPU resource controls that are reset whenever `+cpu` is re-enabled.
struct CpuControl {
    /// A value stores the configured relative CPU share for scheduler integration.
    weight: AtomicU32,
    /// A value stores the configured CPU bandwidth limit for scheduler integration.
    max: SpinLock<CpuMax, LocalIrqDisabled>,
}

/// A CPU bandwidth limit.
#[derive(Clone, Copy)]
struct CpuMax {
    quota_usec: u64,
    period_usec: u64,
    window_start: u64,
    used_clocks: u64,
    /// Positive overrun from earlier quota windows. Never grants unused credit.
    carry_debt_clocks: u64,
    nr_periods: u64,
    nr_throttled: u64,
    throttled_since: Option<u64>,
    throttled_clocks: u64,
}

impl CpuMax {
    /// N0 uses a single vCPU and invariant TSC; these fields are not nanoseconds.
    fn us_to_clocks(us: u64) -> u64 {
        (u128::from(tsc_freq()) * u128::from(us) / 1_000_000)
            .try_into()
            .unwrap_or(u64::MAX)
    }

    fn period_clocks(&self) -> u64 {
        Self::us_to_clocks(self.period_usec).max(1)
    }

    /// Compute the periods visible to a cpu.stat observer WITHOUT closing a
    /// quota window. The running task's interval may not have been charged
    /// yet, so an observational read must not call advance() and erase it.
    fn observed_nr_periods(&self, now: u64) -> u64 {
        let period = self.period_clocks();
        let start = now / period * period;
        if self.window_start == 0 || start <= self.window_start {
            self.nr_periods
        } else {
            self.nr_periods
                .saturating_add((start - self.window_start) / period)
        }
    }

    fn advance(&mut self, now: u64) {
        let period = self.period_clocks();
        let start = now / period * period;
        // A stale timestamp must not rewind the accounting window and grant
        // the same CPU quota again. N0's invariant TSC is monotonic, but the
        // state transition still needs to fail closed on an old observation.
        if start > self.window_start {
            if let Some(since) = self.throttled_since.take() {
                self.throttled_clocks = self
                    .throttled_clocks
                    .saturating_add(start.max(since).min(now).saturating_sub(since));
            }
            if self.window_start != 0 && start > self.window_start {
                self.nr_periods = self
                    .nr_periods
                    .saturating_add((start - self.window_start) / period);
            }
            // When a 1000Hz tick preempts after a small quota is spent,
            // discarding the overrun on every period would systematically
            // grant another full quota. Repay *positive* debt from elapsed
            // budgets; do not bank unused runtime as transferable credit.
            let elapsed = start.saturating_sub(self.window_start) / period;
            let allowance = if self.quota_usec == u64::MAX {
                u64::MAX
            } else {
                Self::us_to_clocks(self.quota_usec).saturating_mul(elapsed)
            };
            self.carry_debt_clocks = self
                .carry_debt_clocks
                .saturating_add(self.used_clocks)
                .saturating_sub(allowance);
            self.window_start = start;
            self.used_clocks = 0;
        }
    }

    /// Settle the positive debt of completed windows touched by a runtime
    /// interval. A timer tick may straddle a quota boundary: charging only
    /// the current window loses the CPU time before that boundary.
    ///
    /// This is O(1), even if the scheduler reports an unusually long interval.
    /// Empty periods repay existing debt but do not accumulate positive credit.
    fn debt_after_crossing(&self, from: u64, new_start: u64, period: u64) -> u64 {
        let quota = Self::us_to_clocks(self.quota_usec);
        let old_end = self.window_start.saturating_add(period);
        let old_spent = old_end.saturating_sub(from.max(self.window_start));
        let mut debt = self
            .carry_debt_clocks
            .saturating_add(self.used_clocks)
            .saturating_add(old_spent)
            .saturating_sub(quota);

        // Completed periods after the old window and before the new one.
        let middle_start = old_end;
        let middle_count = new_start.saturating_sub(middle_start) / period;
        if middle_count == 0 {
            return debt;
        }
        // Process completely idle periods before the first execution period.
        let idle_count =
            (from.max(middle_start).saturating_sub(middle_start) / period).min(middle_count);
        debt = debt.saturating_sub(quota.saturating_mul(idle_count));
        let first_active = middle_start.saturating_add(period.saturating_mul(idle_count));
        if first_active == new_start {
            return debt;
        }

        // The first non-idle completed period may contain only a suffix of
        // the interval; all remaining completed periods ran continuously.
        let first_spent = first_active
            .saturating_add(period)
            .saturating_sub(from.max(first_active));
        debt = debt.saturating_add(first_spent).saturating_sub(quota);
        let full_count = new_start.saturating_sub(first_active.saturating_add(period)) / period;
        if period >= quota {
            debt.saturating_add(period.saturating_sub(quota).saturating_mul(full_count))
        } else {
            debt.saturating_sub(quota.saturating_sub(period).saturating_mul(full_count))
        }
    }

    fn charge(&mut self, from: u64, until: u64) {
        if until < from {
            return;
        }
        let period = self.period_clocks();
        let new_start = until / period * period;
        // Never re-open an earlier accounting window on a backward clock.
        if new_start < self.window_start {
            return;
        }

        // Save the true debt from completed periods before the normal advance
        // updates nr_periods/throttled_usec and resets used_clocks. This avoids
        // counting older idle periods as transferable positive CPU credit.
        let corrected_debt = if new_start > self.window_start && self.quota_usec != u64::MAX {
            Some(self.debt_after_crossing(from, new_start, period))
        } else {
            None
        };
        self.advance(until);
        if let Some(debt) = corrected_debt {
            self.carry_debt_clocks = debt;
        }
        self.used_clocks = self
            .used_clocks
            .saturating_add(until.saturating_sub(from.max(self.window_start)));
    }

    fn eligible(&mut self, now: u64) -> bool {
        self.advance(now);
        if self.quota_usec == u64::MAX
            || self.used_clocks.saturating_add(self.carry_debt_clocks)
                < Self::us_to_clocks(self.quota_usec)
        {
            if let Some(since) = self.throttled_since.take() {
                self.throttled_clocks = self
                    .throttled_clocks
                    .saturating_add(now.saturating_sub(since));
            }
            return true;
        }
        if self.throttled_since.is_none() {
            self.nr_throttled = self.nr_throttled.saturating_add(1);
            self.throttled_since = Some(now);
        }
        false
    }

    fn reconfigure(&mut self, quota_usec: u64, period_usec: u64, now: u64) {
        self.advance(now);
        let already_used = self.used_clocks;
        self.quota_usec = quota_usec;
        self.period_usec = period_usec;
        let period = self.period_clocks();
        self.window_start = now / period * period;
        self.used_clocks = already_used;
        if quota_usec == u64::MAX {
            if let Some(since) = self.throttled_since.take() {
                self.throttled_clocks = self
                    .throttled_clocks
                    .saturating_add(now.saturating_sub(since));
            }
        }
    }

    fn throttled_usec(&self, now: u64) -> u64 {
        let clocks = self.throttled_clocks.saturating_add(
            self.throttled_since
                .map_or(0, |since| now.saturating_sub(since)),
        );
        (u128::from(clocks) * 1_000_000 / u128::from(tsc_freq()))
            .try_into()
            .unwrap_or(u64::MAX)
    }
}

/// Specifies the cgroup CPU sub-controller receives one [`Jiffies`] of charge.
#[derive(Clone, Copy)]
pub(crate) enum CpuStatKind {
    /// Charges one [`Jiffies`] to `user_usec`.
    User,
    /// Charges one [`Jiffies`] to `system_usec`.
    System,
}

impl CpuController {
    pub(super) fn init_attr_set(builder: &mut SysAttrSetBuilder, is_root: bool) {
        builder.add(SysStr::from("cpu.stat"), SysPerms::DEFAULT_RO_ATTR_PERMS);

        if !is_root {
            builder.add(SysStr::from("cpu.weight"), SysPerms::DEFAULT_RW_ATTR_PERMS);
            builder.add(SysStr::from("cpu.max"), SysPerms::DEFAULT_RW_ATTR_PERMS);
        }
    }

    fn new(is_active: bool) -> Self {
        Self {
            stats: CpuStats::new(),
            control: is_active.then(CpuControl::new),
        }
    }

    /// Initializes CPU usage statistics from the previous sub-controller.
    ///
    /// Toggling `+cpu` must reset some controller attributes such as `cpu.weight`
    /// and `cpu.max`, but `cpu.stat` remains visible and continues to report the
    /// accumulated CPU usage.
    pub(super) fn init_stats(&mut self, previous: &Self) {
        // No one cares which CPU the count is on. Therefore, choose the BSP for simplicity.
        self.stats.user.add_on_cpu(
            CpuId::bsp(),
            isize::try_from(previous.stats.user.sum_all_cpus()).unwrap_or(isize::MAX),
        );
        self.stats.system.add_on_cpu(
            CpuId::bsp(),
            isize::try_from(previous.stats.system.sum_all_cpus()).unwrap_or(isize::MAX),
        );
    }

    fn control(&self) -> Result<&CpuControl> {
        self.control.as_ref().ok_or(Error::AttributeError)
    }

    fn read_cpu_stat(&self, printer: &mut VmPrinter) -> Result<usize> {
        /// Converts a per-CPU counter expressed in jiffies to microseconds.
        fn counter_usec(counter: &PerCpuCounter) -> u64 {
            let jiffies = u64::try_from(counter.sum_all_cpus()).unwrap_or(u64::MAX);
            u64::try_from(Jiffies::new(jiffies).as_duration().as_micros()).unwrap_or(u64::MAX)
        }

        let user_usec = counter_usec(&self.stats.user);
        let system_usec = counter_usec(&self.stats.system);
        writeln!(
            printer,
            "usage_usec {}",
            user_usec.saturating_add(system_usec)
        )?;
        writeln!(printer, "user_usec {}", user_usec)?;
        writeln!(printer, "system_usec {}", system_usec)?;

        if self.control.is_some() {
            // User-memory writes can fault and reschedule: never hold the
            // scheduler's bandwidth lock while writing through VmPrinter.
            let (nr_periods, nr_throttled, throttled_usec) = {
                let max = self.control.as_ref().unwrap().max.lock();
                let now = read_tsc();
                // A read must not roll a shared cgroup ahead of the running
                // task's pending scheduler CPU charge. In particular, never
                // grant a fresh quota merely by reading cpu.stat.
                (
                    max.observed_nr_periods(now),
                    max.nr_throttled,
                    max.throttled_usec(now),
                )
            };
            writeln!(printer, "nr_periods {}", nr_periods)?;
            writeln!(printer, "nr_throttled {}", nr_throttled)?;
            writeln!(printer, "throttled_usec {}", throttled_usec)?;
            writeln!(printer, "nr_bursts 0")?;
            writeln!(printer, "burst_usec 0")?;
        }

        Ok(printer.bytes_written())
    }

    /// Accounts one [`Jiffies`] of CPU time on `cpu`.
    fn account(&self, cpu: CpuId, stat_kind: CpuStatKind) {
        match stat_kind {
            CpuStatKind::User => self.stats.user.add_on_cpu(cpu, 1),
            CpuStatKind::System => self.stats.system.add_on_cpu(cpu, 1),
        }
    }
}

impl CpuControl {
    fn new() -> Self {
        // The default CPU weight is 100 and the default CPU bandwidth limit is
        // unlimited quota with a 100ms period.
        //
        // Reference: <https://docs.kernel.org/admin-guide/cgroup-v2.html#cpu-interface-files>
        const DEFAULT_WEIGHT: u32 = 100;
        const DEFAULT_QUOTA_USEC: u64 = u64::MAX;
        const DEFAULT_PERIOD_USEC: u64 = 100_000;

        Self {
            weight: AtomicU32::new(DEFAULT_WEIGHT),
            max: SpinLock::new(CpuMax {
                quota_usec: DEFAULT_QUOTA_USEC,
                period_usec: DEFAULT_PERIOD_USEC,
                window_start: 0,
                used_clocks: 0,
                carry_debt_clocks: 0,
                nr_periods: 0,
                nr_throttled: 0,
                throttled_since: None,
                throttled_clocks: 0,
            }),
        }
    }
}

impl CpuStats {
    fn new() -> Self {
        Self {
            user: PerCpuCounter::new(),
            system: PerCpuCounter::new(),
        }
    }
}

impl super::SubControl for CpuController {
    fn is_attr_absent(&self, name: &str) -> bool {
        matches!(name, "cpu.weight" | "cpu.max") && self.control.is_none()
    }

    fn read_attr_at(&self, name: &str, offset: usize, writer: &mut VmWriter) -> Result<usize> {
        let mut printer = VmPrinter::new_skip(writer, offset);

        match name {
            "cpu.stat" => return self.read_cpu_stat(&mut printer),
            "cpu.weight" => {
                let weight = self.control()?.weight.load(Ordering::Relaxed);
                writeln!(printer, "{}", weight)?;
            }
            "cpu.max" => {
                let max = *self.control()?.max.lock();
                if max.quota_usec == u64::MAX {
                    writeln!(printer, "max {}", max.period_usec)?;
                } else {
                    writeln!(printer, "{} {}", max.quota_usec, max.period_usec)?;
                }
            }
            _ => return Err(Error::AttributeError),
        }

        Ok(printer.bytes_written())
    }

    fn write_attr(&self, name: &str, reader: &mut VmReader) -> Result<usize> {
        match name {
            "cpu.weight" => {
                let control = self.control()?;

                // The cgroup v2 CPU weight is a scheduling weight in the range 1..=10000.
                //
                // Reference: <https://docs.kernel.org/admin-guide/cgroup-v2.html#cpu-interface-files>
                const MIN_WEIGHT: u32 = 1;
                const MAX_WEIGHT: u32 = 10_000;

                let (content, len) = reader
                    .read_cstring_until_end(MAX_ATTR_SIZE)
                    .map_err(|_| Error::PageFault)?;
                let weight = content
                    .to_str()
                    .map_err(|_| Error::InvalidOperation)?
                    .trim()
                    .parse::<u32>()
                    .map_err(|_| Error::InvalidOperation)?;
                if !(MIN_WEIGHT..=MAX_WEIGHT).contains(&weight) {
                    return Err(Error::InvalidOperation);
                }

                // TODO: Enforce cgroup CPU weight for scheduling and remove this warning.
                warn!(
                    "`cpu.weight` is accepted but not enforced yet; weight = {}",
                    weight
                );
                control.weight.store(weight, Ordering::Relaxed);

                Ok(len)
            }
            "cpu.max" => {
                let control = self.control()?;

                // The cgroup v2 CPU bandwidth limit is `$MAX $PERIOD`, where `$MAX` is
                // either `max` or at least 1ms and `$PERIOD` is in the range 1ms..=1s.
                //
                // Reference: <https://docs.kernel.org/admin-guide/cgroup-v2.html#cpu-interface-files>
                const MIN_QUOTA_USEC: u64 = 1_000;
                const MIN_PERIOD_USEC: u64 = 1_000;
                const MAX_PERIOD_USEC: u64 = 1_000_000;

                let (content, len) = reader
                    .read_cstring_until_end(MAX_ATTR_SIZE)
                    .map_err(|_| Error::PageFault)?;
                let content = content
                    .to_str()
                    .map_err(|_| Error::InvalidOperation)?
                    .trim();
                let mut tokens = content.split_whitespace();

                let Some(quota_token) = tokens.next() else {
                    return Err(Error::InvalidOperation);
                };
                let period_token = tokens.next();

                // Check whether `quota_usec` is valid.
                let quota_usec = if quota_token == "max" {
                    u64::MAX
                } else if let Ok(quota_usec) = quota_token.parse::<u64>() {
                    if quota_usec < MIN_QUOTA_USEC {
                        return Err(Error::InvalidOperation);
                    }
                    quota_usec
                } else {
                    return Err(Error::InvalidOperation);
                };

                // Check whether `period_usec` is valid.
                let period_usec = if let Some(period_usec) =
                    period_token.and_then(|period_token| period_token.parse::<u64>().ok())
                {
                    if !(MIN_PERIOD_USEC..=MAX_PERIOD_USEC).contains(&period_usec) {
                        return Err(Error::InvalidOperation);
                    }
                    Some(period_usec)
                } else {
                    None
                };

                let mut max = control.max.lock();
                let next_period = period_usec.unwrap_or(max.period_usec);
                max.reconfigure(quota_usec, next_period, read_tsc());

                Ok(len)
            }
            _ => Err(Error::AttributeError),
        }
    }
}

impl super::SubControlStatic for CpuController {
    fn new(is_root: bool, is_active: bool) -> Self {
        Self::new(is_root || is_active)
    }

    fn type_() -> super::SubCtrlType {
        super::SubCtrlType::Cpu
    }

    fn read_from(controller: &super::Controller) -> Arc<super::SubController<Self>> {
        controller.cpu.read().get().clone()
    }
}

impl super::SubController<CpuController> {
    /// Accounts one [`Jiffies`] of CPU time for this cgroup and all of its ancestors.
    fn charge_bandwidth_hierarchy(&self, from: u64, until: u64) {
        let mut node = Some(self);
        while let Some(current) = node {
            if let Some(control) = current.inner.as_ref().unwrap().control.as_ref() {
                control.max.lock().charge(from, until);
            }
            node = current.parent.as_deref();
        }
    }

    fn bandwidth_available_hierarchy(&self, now: u64) -> bool {
        let mut node = Some(self);
        let mut available = true;
        while let Some(current) = node {
            if let Some(control) = current.inner.as_ref().unwrap().control.as_ref() {
                available &= control.max.lock().eligible(now);
            }
            node = current.parent.as_deref();
        }
        available
    }

    fn account_hierarchy(&self, stat_kind: CpuStatKind) {
        // This is race-free because `charge_cpu_time` holds `cgroup_guard` when
        // invoking this method.
        let cpu = CpuId::current_racy();

        let mut current = Some(self);
        while let Some(node) = current {
            node.inner.as_ref().unwrap().account(cpu, stat_kind);
            current = node.parent.as_deref();
        }
    }
}

impl super::Controller {
    /// Charges one [`Jiffies`] in the CPU sub-controller hierarchy.
    fn charge_cpu_time<G: AsAtomicModeGuard + ?Sized>(&self, guard: &G, stat_kind: CpuStatKind) {
        self.cpu.read_with(guard).account_hierarchy(stat_kind);
    }
}

/// Uses the existing cgroup controller for both Linux and future HOS callers.
pub(crate) fn task_cpu_eligible(task: &Task, now: u64) -> bool {
    let Some(thread) = task.as_posix_thread() else {
        return true;
    };
    let Some(process) = thread.weak_process().upgrade() else {
        // On SMP a POSIX task can still be visible to the scheduler while
        // its Process Arc has already been destroyed. Only an already-exited
        // thread may finish that cleanup without its old cgroup identity.
        return task.as_thread().is_some_and(|thread| thread.is_exited());
    };
    let guard = process.cgroup();
    if let Some(group) = guard.get() {
        group
            .controller()
            .cpu
            .read_with(&guard)
            .bandwidth_available_hierarchy(now)
    } else {
        CgroupSystem::singleton()
            .controller()
            .cpu
            .read_with(&guard)
            .bandwidth_available_hierarchy(now)
    }
}

pub(crate) fn charge_task_cpu(task: &Task, from: u64, until: u64) {
    let Some(thread) = task.as_posix_thread() else {
        return;
    };
    let Some(process) = thread.weak_process().upgrade() else {
        // The Process owner may be gone while the scheduler still settles the
        // final interval.  The thread-owned lease is the only valid identity
        // for that deferred debit; never guess a replacement cgroup or charge
        // root when the lease is absent.
        if let Some(cgroup) = thread.cpu_cgroup() {
            cgroup
                .controller()
                .cpu
                .read()
                .get()
                .charge_bandwidth_hierarchy(from, until);
        }
        return;
    };
    let guard = process.cgroup();
    if let Some(group) = guard.get() {
        group
            .controller()
            .cpu
            .read_with(&guard)
            .charge_bandwidth_hierarchy(from, until);
    } else {
        let root_cpu = CgroupSystem::singleton().controller().cpu.read();
        root_cpu.get().charge_bandwidth_hierarchy(from, until);
    }
}

/// Charges one [`Jiffies`] of CPU time to `process`'s cgroup hierarchy.
///
/// If `process` is not attached to a non-root cgroup, the charge is applied to the root cgroup.
pub(crate) fn charge_cpu_time(process: &Process, stat_kind: CpuStatKind) {
    let cgroup_guard = process.cgroup();

    if let Some(cgroup) = cgroup_guard.get() {
        cgroup
            .controller()
            .charge_cpu_time(&cgroup_guard, stat_kind);
    } else {
        CgroupSystem::singleton()
            .controller()
            .charge_cpu_time(&cgroup_guard, stat_kind);
    }
}

#[cfg(ktest)]
mod quota_debt_regressions {
    use ostd::prelude::ktest;

    use super::CpuMax;

    fn sample(quota_usec: u64, period_usec: u64, start: u64) -> CpuMax {
        CpuMax {
            quota_usec,
            period_usec,
            window_start: start,
            used_clocks: 0,
            carry_debt_clocks: 0,
            nr_periods: 0,
            nr_throttled: 0,
            throttled_since: None,
            throttled_clocks: 0,
        }
    }

    #[ktest]
    fn cpu_stat_projection_must_not_close_unsettled_quota_window() {
        let period = CpuMax::us_to_clocks(100_000).max(1);
        let quota = CpuMax::us_to_clocks(1_000);
        let start = period.saturating_mul(2);
        let mut budget = sample(1_000, 100_000, start);
        budget.nr_periods = 7;
        budget.used_clocks = quota.saturating_mul(2);
        budget.throttled_since = Some(start + period / 2);
        let from = start + period - quota / 2;
        let until = start + period + quota / 2;

        // cpu.stat can run while a scheduling interval is not yet charged.
        // Its projected number of periods may change, but it must not
        // mutate used clocks, positive debt, throttling or window origin.
        let before = budget;
        assert_eq!(budget.observed_nr_periods(until), 8);
        assert_eq!(budget.window_start, before.window_start);
        assert_eq!(budget.nr_periods, before.nr_periods);
        assert_eq!(budget.used_clocks, before.used_clocks);
        assert_eq!(budget.carry_debt_clocks, before.carry_debt_clocks);
        assert_eq!(budget.throttled_since, before.throttled_since);

        // The later scheduler debit can still account the old-period tail.
        budget.charge(from, until);
        assert_eq!(budget.window_start, start + period);
        assert_eq!(budget.used_clocks, quota / 2);
        assert_eq!(budget.carry_debt_clocks, quota + quota / 2);
        assert_eq!(budget.nr_periods, 8);
        assert!(!budget.eligible(until));
    }

    #[ktest]
    fn cpu_stat_projection_cannot_rewind_accounting_or_mint_credit() {
        let period = CpuMax::us_to_clocks(100_000).max(1);
        let quota = CpuMax::us_to_clocks(1_000);
        let start = period.saturating_mul(4);
        let mut budget = sample(1_000, 100_000, start);
        budget.nr_periods = 9;
        budget.used_clocks = quota;
        budget.carry_debt_clocks = quota / 2;
        assert_eq!(budget.observed_nr_periods(start - period / 2), 9);
        assert_eq!(budget.observed_nr_periods(start + 3 * period + 1), 12);
        assert_eq!(budget.window_start, start);
        assert_eq!(budget.used_clocks, quota);
        assert_eq!(budget.carry_debt_clocks, quota / 2);
        // Unlike a statistics read, the real scheduler advances and settles.
        budget.advance(start + 3 * period + 1);
        assert_eq!(budget.nr_periods, 12);
        assert_eq!(budget.carry_debt_clocks, 0);
    }

    #[ktest]
    fn overrun_must_carry_then_repay_without_refill() {
        let period = CpuMax::us_to_clocks(100_000).max(1);
        let quota = CpuMax::us_to_clocks(1_000);
        let start = period.saturating_mul(2);
        let mut budget = sample(1_000, 100_000, start);
        budget.used_clocks = quota.saturating_mul(2);
        budget.advance(start + period);
        assert_eq!(budget.used_clocks, 0);
        assert_eq!(budget.carry_debt_clocks, quota);
        assert!(!budget.eligible(start + period));
        budget.advance(start + period * 2);
        assert_eq!(budget.carry_debt_clocks, 0);
        assert!(budget.eligible(start + period * 2));
    }

    #[ktest]
    fn unused_budget_must_not_accumulate_as_credit() {
        let period = CpuMax::us_to_clocks(100_000).max(1);
        let quota = CpuMax::us_to_clocks(1_000);
        let start = period.saturating_mul(2);
        let mut budget = sample(1_000, 100_000, start);
        budget.used_clocks = quota / 2;
        budget.advance(start + period);
        assert_eq!(budget.carry_debt_clocks, 0);
        budget.used_clocks = quota;
        assert!(!budget.eligible(start + period));
    }

    #[ktest]
    fn reconfiguration_in_same_window_must_not_refill() {
        let period = CpuMax::us_to_clocks(100_000).max(1);
        let quota = CpuMax::us_to_clocks(1_000);
        let start = period.saturating_mul(2);
        let mut budget = sample(1_000, 100_000, start);
        budget.used_clocks = quota;
        budget.carry_debt_clocks = quota / 2;
        let now = start + period / 2;
        budget.reconfigure(1_000, 100_000, now);
        assert_eq!(budget.used_clocks, quota);
        assert_eq!(budget.carry_debt_clocks, quota / 2);
        assert!(!budget.eligible(now));
    }

    #[ktest]
    fn scheduler_runtime_crossing_tick_window_keeps_previous_cpu_charge() {
        let period = CpuMax::us_to_clocks(100_000).max(1);
        let quota = CpuMax::us_to_clocks(1_000);
        let start = period.saturating_mul(2);
        let mut budget = sample(1_000, 100_000, start);
        // A non-preemptible interval extends two quotas before the 100ms
        // boundary, and another quarter quota into the next period.
        budget.charge(start + period - quota * 2, start + period + quota / 4);
        assert_eq!(budget.window_start, start + period);
        assert_eq!(budget.carry_debt_clocks, quota);
        assert_eq!(budget.used_clocks, quota / 4);
        assert!(!budget.eligible(start + period + quota / 4));
    }

    #[ktest]
    fn crossing_splits_already_charged_and_new_cpu_without_double_count() {
        let period = CpuMax::us_to_clocks(100_000).max(1);
        let quota = CpuMax::us_to_clocks(1_000);
        let start = period.saturating_mul(2);
        let mut budget = sample(1_000, 100_000, start);
        budget.used_clocks = quota / 2;
        budget.charge(start + period - quota * 3, start + period + quota / 2);
        assert_eq!(budget.carry_debt_clocks, quota * 2 + quota / 2);
        assert_eq!(budget.used_clocks, quota / 2);
    }

    #[ktest]
    fn idle_skipped_periods_never_subsidize_late_burst() {
        let period = CpuMax::us_to_clocks(100_000).max(1);
        let quota = CpuMax::us_to_clocks(1_000);
        let start = period.saturating_mul(2);
        let mut budget = sample(1_000, 100_000, start);
        let last_completed = start + 6 * period;
        budget.charge(
            last_completed + period / 2,
            last_completed + period + quota / 2,
        );
        assert_eq!(budget.window_start, last_completed + period);
        assert_eq!(budget.carry_debt_clocks, period.saturating_sub(period / 2) - quota);
        assert_eq!(budget.used_clocks, quota / 2);
        assert!(!budget.eligible(last_completed + period + quota / 2));
    }

    #[ktest]
    fn long_continuous_interval_has_constant_time_bounded_debt_accounting() {
        let period = CpuMax::us_to_clocks(100_000).max(1);
        let quota = CpuMax::us_to_clocks(1_000);
        let start = period.saturating_mul(2);
        let mut budget = sample(1_000, 100_000, start);
        budget.charge(start + period / 2, start + 5 * period + quota / 2);
        // First completed period: P/2 work - Q budget. The following four
        // completed periods were fully busy; no per-period heap work or loop.
        let expected = period.saturating_sub(period / 2) - quota + 4 * (period - quota);
        assert_eq!(budget.carry_debt_clocks, expected);
        assert_eq!(budget.used_clocks, quota / 2);
    }

    #[ktest]
    fn earlier_clock_value_cannot_reopen_or_refill_previous_period() {
        let period = CpuMax::us_to_clocks(100_000).max(1);
        let quota = CpuMax::us_to_clocks(1_000);
        let start = period.saturating_mul(4);
        let mut budget = sample(1_000, 100_000, start);
        budget.used_clocks = quota;
        budget.carry_debt_clocks = quota / 2;
        budget.advance(start - period / 2);
        budget.charge(start - period / 2, start - 1);
        assert_eq!(budget.window_start, start);
        assert_eq!(budget.used_clocks, quota);
        assert_eq!(budget.carry_debt_clocks, quota / 2);
        assert!(!budget.eligible(start));
    }

    #[ktest]
    fn charging_500_intervals_matches_simple_period_by_period_reference() {
        // Adversarial reference oracle runs only in ktest; the real scheduler
        // hot path remains O(1) even if multiple windows elapsed between ticks.
        fn next(seed: &mut u64) -> u64 {
            *seed = seed
                .wrapping_mul(6364136223846793005)
                .wrapping_add(1442695040888963407);
            *seed
        }

        let period = CpuMax::us_to_clocks(100_000).max(1);
        let start = period.saturating_mul(2);
        let mut seed = 0xA03A06_A11CEu64;
        for _ in 0..500 {
            let quota_us = 1_000 + next(&mut seed) % 99_001;
            let quota = CpuMax::us_to_clocks(quota_us);
            let mut budget = sample(quota_us, 100_000, start);
            let old_used = next(&mut seed) % period;
            let old_debt = next(&mut seed) % period;
            budget.used_clocks = old_used;
            budget.carry_debt_clocks = old_debt;

            let from = start + (next(&mut seed) % 10) * period + next(&mut seed) % period;
            let until = from + next(&mut seed) % (period * 11);
            let new_start = until / period * period;
            let mut slow_debt = old_debt;
            let mut window = start;
            while window < new_start {
                let work = (window + period)
                    .min(until)
                    .saturating_sub(from.max(window));
                let spent = work + if window == start { old_used } else { 0 };
                slow_debt = slow_debt.saturating_add(spent).saturating_sub(quota);
                window += period;
            }
            let slow_used = if new_start == start {
                old_used.saturating_add(until.saturating_sub(from.max(start)))
            } else {
                until.saturating_sub(from.max(new_start))
            };
            budget.charge(from, until);
            assert_eq!(budget.window_start, new_start);
            assert_eq!(budget.used_clocks, slow_used);
            assert_eq!(budget.carry_debt_clocks, slow_debt);
        }
    }

    #[ktest]
    fn skipped_periods_pay_down_debt_but_never_mint_credit() {
        let period = CpuMax::us_to_clocks(100_000).max(1);
        let quota = CpuMax::us_to_clocks(1_000);
        let start = period.saturating_mul(2);
        let mut budget = sample(1_000, 100_000, start);
        budget.used_clocks = quota.saturating_mul(3);
        budget.advance(start + period * 4);
        assert_eq!(budget.carry_debt_clocks, 0);
        assert_eq!(budget.used_clocks, 0);
        budget.used_clocks = quota;
        assert!(!budget.eligible(start + period * 4));
    }
}
