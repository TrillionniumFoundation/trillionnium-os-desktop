// SPDX-License-Identifier: MPL-2.0

use alloc::sync::Arc;
use core::sync::atomic::{AtomicU32, Ordering};

use ostd::arch::{read_tsc, tsc_freq};
use ostd::task::Task;

use aster_systree::{Error, MAX_ATTR_SIZE, Result, SysAttrSetBuilder, SysPerms, SysStr};
use aster_util::{per_cpu_counter::PerCpuCounter, printer::VmPrinter};
use ostd::{
    cpu::CpuId,
    mm::{VmReader, VmWriter},
    sync::SpinLock,
    task::atomic_mode::AsAtomicModeGuard,
    timer::Jiffies,
    warn,
};

use crate::{
    fs::cgroupfs::systree_node::{CgroupSysNode, CgroupSystem},
    process::{Process, posix_thread::AsPosixThread},
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
    max: SpinLock<CpuMax>,
}

/// A CPU bandwidth limit.
#[derive(Clone, Copy)]
struct CpuMax {
    quota_usec: u64,
    period_usec: u64,
    window_start: u64,
    used_clocks: u64,
    nr_periods: u64,
    nr_throttled: u64,
    throttled_since: Option<u64>,
    throttled_clocks: u64,
}

impl CpuMax {
    /// N0 uses a single vCPU and invariant TSC; these fields are not nanoseconds.
    fn us_to_clocks(us: u64) -> u64 {
        (u128::from(tsc_freq()) * u128::from(us) / 1_000_000)
            .try_into().unwrap_or(u64::MAX)
    }

    fn period_clocks(&self) -> u64 {
        Self::us_to_clocks(self.period_usec).max(1)
    }

    fn advance(&mut self, now: u64) {
        let period = self.period_clocks();
        let start = now / period * period;
        if start != self.window_start {
            if let Some(since) = self.throttled_since.take() {
                self.throttled_clocks = self.throttled_clocks.saturating_add(
                    start.max(since).min(now).saturating_sub(since));
            }
            if self.window_start != 0 && start > self.window_start {
                self.nr_periods = self.nr_periods.saturating_add(
                    (start - self.window_start) / period);
            }
            self.window_start = start;
            self.used_clocks = 0;
        }
    }

    fn charge(&mut self, from: u64, until: u64) {
        if until < from { return; }
        self.advance(until);
        self.used_clocks = self.used_clocks.saturating_add(
            until.saturating_sub(from.max(self.window_start)));
    }

    fn eligible(&mut self, now: u64) -> bool {
        self.advance(now);
        if self.quota_usec == u64::MAX ||
            self.used_clocks < Self::us_to_clocks(self.quota_usec) {
            if let Some(since) = self.throttled_since.take() {
                self.throttled_clocks = self.throttled_clocks.saturating_add(
                    now.saturating_sub(since));
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
                self.throttled_clocks = self.throttled_clocks.saturating_add(
                    now.saturating_sub(since));
            }
        }
    }

    fn throttled_usec(&self, now: u64) -> u64 {
        let clocks = self.throttled_clocks.saturating_add(
            self.throttled_since.map_or(0, |since| now.saturating_sub(since)));
        (u128::from(clocks) * 1_000_000 / u128::from(tsc_freq()))
            .try_into().unwrap_or(u64::MAX)
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
            let mut max = self.control.as_ref().unwrap().max.lock();
            let now = read_tsc();
            max.advance(now);
            writeln!(printer, "nr_periods {}", max.nr_periods)?;
            writeln!(printer, "nr_throttled {}", max.nr_throttled)?;
            writeln!(printer, "throttled_usec {}", max.throttled_usec(now))?;
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
    let Some(thread) = task.as_posix_thread() else { return true; };
    let process = thread.process();
    let guard = process.cgroup();
    if let Some(group) = guard.get() {
        group.controller().cpu.read_with(&guard).bandwidth_available_hierarchy(now)
    } else {
        CgroupSystem::singleton().controller().cpu.read_with(&guard)
            .bandwidth_available_hierarchy(now)
    }
}

pub(crate) fn charge_task_cpu(task: &Task, from: u64, until: u64) {
    let Some(thread) = task.as_posix_thread() else { return; };
    let process = thread.process();
    let guard = process.cgroup();
    if let Some(group) = guard.get() {
        group.controller().cpu.read_with(&guard).charge_bandwidth_hierarchy(from, until);
    } else {
        CgroupSystem::singleton().controller().cpu.read_with(&guard)
            .charge_bandwidth_hierarchy(from, until);
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
