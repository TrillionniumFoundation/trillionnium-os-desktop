//! Actual parent-owned watchdog lifetime for one fixed working boot.
//! Progress on this same thread drives keepalive. There is no detached feeder,
//! public constructor from JSON, renewed deadline or inherited child ownership.
use super::super::application_leaf_unit::qualification::UnitOwner;
use super::working_config::AdmittedWorkingConfiguration;
use super::{BoundProcess, RuntimeMainCustody};
use crate::control::{DEFAULT_CONTROL_SOCKET, MainCustodyObservation, NativeApplicationInspector};
use crate::native_leaf_baseline_data::working_main::HeldWorkingMain;
use crate::native_leaf_baseline_programs::NormalHostPrograms;
use std::{
    cell::{Cell, RefCell},
    io,
    os::fd::AsRawFd,
    path::Path,
    rc::{Rc, Weak},
    sync::Arc,
    time::{Duration, Instant},
};

#[path = "working_qualification_boot.rs"]
pub(crate) mod boot;
#[path = "working_qualification_return.rs"]
mod return_entry;
#[path = "working_qualification_watchdog.rs"]
mod watchdog;
pub(super) use return_entry::dispatch as dispatch_working_return;

thread_local! {
    static CURRENT: RefCell<Option<Weak<LivePulse>>> = const { RefCell::new(None) };
}
fn failed(why: &str) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, why)
}
fn io_result<T>(value: Result<T, String>) -> io::Result<T> {
    value.map_err(|e| failed(&e))
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Phase {
    Preparation,
    Suite,
    Captured,
}

pub(super) struct LivePulse {
    owner: Rc<UnitOwner>,
    configuration: Arc<AdmittedWorkingConfiguration>,
    boot: boot::BootOwner,
    main: HeldWorkingMain,
    programs: NormalHostPrograms,
    watchdog: RefCell<watchdog::SoftwareWatchdog>,
    child: RefCell<Option<Rc<BoundProcess>>>,
    retained: RefCell<Option<Rc<crate::control::working_retained_peer::RetainedHelperPeer>>>,
    phase: Cell<Phase>,
    busy: Cell<bool>,
    poisoned: Cell<bool>,
    pid: u32,
    start_ns: u64,
    end_ns: u64,
    end: Instant,
    preparation_end: Instant,
}
impl LivePulse {
    /// Called only after actual UnitOwner and boot configuration admission.
    pub(super) fn acquire(
        owner: Rc<UnitOwner>,
        configuration: Arc<AdmittedWorkingConfiguration>,
        start_ns: u64,
        end_ns: u64,
        end: Instant,
        preparation_end: Instant,
    ) -> Result<(Rc<Self>, NativeApplicationInspector, MainCustodyObservation), String> {
        // Derive the initial prefix from the same actual PID1 start. It spends
        // the already-counted local/Main components and never resets at acquire.
        let sampled_instant = Instant::now();
        let sampled_ns = watchdog::monotonic_ns().map_err(|e| e.to_string())?;
        let first_feed_ns = start_ns
            .checked_add(
                crate::native_working_contract::budget::PREPARATION_BOOTSTRAP_SECONDS
                    .checked_mul(1_000_000_000)
                    .ok_or("working bootstrap duration overflow")?,
            )
            .ok_or("working bootstrap monotonic end overflow")?;
        let remaining = first_feed_ns
            .checked_sub(sampled_ns)
            .filter(|remaining| *remaining != 0)
            .ok_or("working initial bootstrap already exceeded its original prefix")?;
        let bootstrap_end = sampled_instant
            .checked_add(Duration::from_nanos(remaining))
            .ok_or("working initial bootstrap Instant overflow")?
            .min(preparation_end);
        configuration.guard().map_err(|e| e.to_string())?;
        let boot = boot::BootOwner::open().map_err(|e| e.to_string())?;
        configuration
            .require_same_return(boot.config())
            .map_err(|e| e.to_string())?;
        let watchdog = watchdog::SoftwareWatchdog::open().map_err(|e| e.to_string())?;
        // This is the original single 70-second bootstrap allowance. It precedes
        // the first PM request and the exact actual token is moved to preparation.
        let mut inspector = NativeApplicationInspector::acquire_until(
            Path::new(DEFAULT_CONTROL_SOCKET),
            bootstrap_end,
        )
        .map_err(|e| e.to_string())?;
        let main = inspector
            .observe_current_main_until(bootstrap_end)
            .map_err(|e| e.to_string())?;
        boot.compare_main(&main).map_err(|e| e.to_string())?;
        let programs =
            NormalHostPrograms::capture(&main, bootstrap_end).map_err(|e| e.to_string())?;
        let kernel_main = HeldWorkingMain::capture(&main).map_err(|e| e.to_string())?;
        inspector.revalidate().map_err(|e| e.to_string())?;
        if Instant::now() >= bootstrap_end {
            return Err("working initial Main/source capture exhausted its original prefix".into());
        }
        let value = Rc::new(Self {
            owner,
            configuration,
            boot,
            main: kernel_main,
            programs,
            watchdog: RefCell::new(watchdog),
            child: RefCell::new(None),
            retained: RefCell::new(None),
            phase: Cell::new(Phase::Preparation),
            busy: Cell::new(false),
            poisoned: Cell::new(false),
            pid: std::process::id(),
            start_ns,
            end_ns,
            end,
            preparation_end,
        });
        CURRENT.with(|slot| -> Result<(), String> {
            let mut slot = slot
                .try_borrow_mut()
                .map_err(|_| "working keepalive installation reentered")?;
            if slot.as_ref().and_then(Weak::upgrade).is_some() {
                return Err("working keepalive already has a live original owner".into());
            }
            *slot = Some(Rc::downgrade(&value));
            Ok(())
        })?;
        value.guard().map_err(|e| e.to_string())?;
        Ok((value, inspector, main))
    }
    fn until(&self) -> Instant {
        if self.phase.get() == Phase::Preparation {
            self.preparation_end
        } else {
            self.end
        }
    }
    fn cheap_guard(&self) -> io::Result<()> {
        if self.pid != std::process::id() || self.poisoned.get() || Instant::now() >= self.until() {
            return Err(failed(
                "working watchdog left its original live owner/window",
            ));
        }
        Ok(())
    }
    pub(super) fn guard(&self) -> io::Result<()> {
        self.cheap_guard()?;
        if self.busy.replace(true) {
            self.poisoned.set(true);
            return Err(failed("working keepalive full guard reentered"));
        }
        let result = (|| {
            self.configuration.guard()?;
            self.boot.guard()?;
            let child = self
                .child
                .try_borrow()
                .map_err(|_| failed("working child pulse state reentered"))?;
            let retained = self.retained.try_borrow().map_err(|_|failed("retained helper guard reentered"))?;
            if let Some(helper) = retained.as_ref() {
                if self.phase.get()!=Phase::Preparation || child.is_some() {
                    return Err(failed("retained helper is outside actual preparation"));
                }
                io_result(self.owner.retained_boundary(helper,self.until()))?;
            } else {
            io_result(self.owner.watchdog_boundary(
                child.as_deref(),
                self.phase.get() == Phase::Preparation,
                self.until(),
            ))?;
            }
            self.programs.verify(self.until())?;
            self.main.guard()?;
            self.configuration.guard()?;
            self.boot.guard()?;
            self.cheap_guard()?;
            let now = watchdog::monotonic_ns()?;
            let mut watchdog = self
                .watchdog
                .try_borrow_mut()
                .map_err(|_| failed("working watchdog custody reentered"))?;
            watchdog.guard()?;
            if watchdog.due(now) {
                watchdog.keepalive(self.start_ns, self.end_ns)?;
            }
            self.cheap_guard()
        })();
        self.busy.set(false);
        if result.is_err() {
            self.poisoned.set(true);
        }
        result
    }
    fn progress(&self) -> io::Result<()> {
        self.cheap_guard()?;
        // Reentry can only be the same thread reading a source file inside its
        // current full guard. It cannot feed until that outer guard completes.
        if self.busy.get() {
            return Ok(());
        }
        let now = watchdog::monotonic_ns()?;
        let due = self
            .watchdog
            .try_borrow()
            .map_err(|_| failed("working watchdog progress reentered"))?
            .due(now);
        if due {
            self.guard()?;
        }
        Ok(())
    }
    pub(super) fn retained_boot(&self) -> &boot::BootOwner { &self.boot }
    pub(super) fn bind_retained(&self, helper:Rc<crate::control::working_retained_peer::RetainedHelperPeer>) -> Result<(),String> {
        self.cheap_guard().map_err(|e|e.to_string())?;
        if self.phase.get()!=Phase::Preparation || self.child.borrow().is_some()
            || self.retained.borrow().is_some() { return Err("retained helper already active or outside preparation".into()); }
        helper.guard().map_err(|e|e.to_string())?;
        *self.retained.borrow_mut()=Some(helper);
        self.guard().map_err(|e|e.to_string())
    }
    pub(super) fn retired_retained(&self) -> Result<(),String> {
        if self.phase.get()!=Phase::Preparation { return Err("retained helper retirement is outside preparation".into()); }
        {
            let slot=self.retained.borrow();
            let helper=slot.as_ref().ok_or("retained helper owner absent")?;
            let mut poll=libc::pollfd{fd:helper.pidfd().as_raw_fd(),events:libc::POLLIN,revents:0};
            if unsafe{libc::poll(&mut poll,1,0)}!=1 || poll.revents&libc::POLLIN==0 {
                return Err("retained helper original PIDFD has not exited".into());
            }
        }
        self.retained.borrow_mut().take();
        self.owner.preparation_boundary(self.until())?;
        self.guard().map_err(|e|e.to_string())
    }
    pub(super) fn begin_suite(
        &self,
        child: Rc<BoundProcess>,
        actual_epoch: &crate::control::application_probe::RuntimeEpoch,
    ) -> Result<RuntimeMainCustody, String> {
        self.cheap_guard().map_err(|e| e.to_string())?;
        if self.phase.get() != Phase::Preparation
            || self.child.borrow().is_some()
            || self.retained.borrow().is_some()
            || &self.main.facts().epoch != actual_epoch
        {
            return Err("working child HELLO differs from this actual bootstrap Main".into());
        }
        self.owner.child_guard(&child)?;
        self.owner.boundary(Some(&child), self.end)?;
        *self.child.borrow_mut() = Some(child);
        self.phase.set(Phase::Suite);
        self.guard().map_err(|e| e.to_string())?;
        // Only this actual admitted parent can publish its retained bootstrap
        // comparison after the same child and complete Main still pass guard.
        Ok(self.main.facts().clone())
    }
    pub(super) fn require_preparation_binding(
        &self,
        actual: &RuntimeMainCustody,
    ) -> Result<(), String> {
        self.guard().map_err(|e| e.to_string())?;
        if self.phase.get() != Phase::Preparation || self.main.facts() != actual {
            return Err("working preparation belongs to another complete actual Main custody".into());
        }
        self.main.guard().map_err(|e| e.to_string())
    }
    pub(super) fn require_complete_binding(
        &self,
        actual: &RuntimeMainCustody,
    ) -> Result<(), String> {
        if self.phase.get() != Phase::Suite || self.main.facts() != actual {
            return Err("private Complete belongs to another actual Main custody".into());
        }
        self.main.guard().map_err(|e| e.to_string())
    }
    pub(super) fn retired_suite(&self) -> Result<(), String> {
        if self.phase.get() != Phase::Suite {
            return Err("actual suite retirement is out of order".into());
        }
        // The caller has already reaped its real Child. Require the same held
        // PIDFD to report exit and the manager-bound entire unit to be empty of
        // all children before relinquishing that retained process.
        {
            let child = self.child.borrow();
            let child = child.as_ref().ok_or("working suite child absent")?;
            if !super::super::pidfd_exited(&child.pidfd).map_err(|e| e.to_string())? {
                return Err("working suite retained PIDFD has not exited".into());
            }
        }
        self.owner.boundary(None, self.end)?;
        self.child.borrow_mut().take();
        self.phase.set(Phase::Captured);
        self.guard().map_err(|e| e.to_string())
    }
    pub(super) fn poison(&self) {
        self.poisoned.set(true);
    }
    pub(super) fn child_close_fd(&self) -> io::Result<i32> {
        self.cheap_guard()?;
        Ok(self
            .watchdog
            .try_borrow()
            .map_err(|_| failed("working watchdog FD reentered"))?
            .child_close_fd())
    }
    pub(super) fn observation(&self) -> io::Result<serde_json::Value> {
        self.guard()?;
        Ok(serde_json::json!({
            "schema":"droidloom.working-owner-progress-custody.v1",
            "owner_start_monotonic_ns":self.start_ns,"original_authorization_end_monotonic_ns":self.end_ns,
            "boot":self.boot.observation(),"watchdog":self.watchdog.borrow().observation(),
            "bootstrap_main_observed_once":true,
            "local_kernel_bookends":["normal-peer","init","zygote","framework","seven-namespaces","data-mount","metadata-mount"],
            "full_main_rpc_at_existing_business_bookends":true,
            "detached_feeder":false,"private_original_data_opened":false
        }))
    }
}

/// Crate-private loop hook. Only the actual parent owner installs its weak
/// context; other ordinary clients and an exec'd suite have no feeder.
pub(crate) fn progress() -> Result<(), String> {
    let owner = CURRENT.with(|slot| {
        slot.try_borrow()
            .map_err(|_| "working progress context reentered")
            .map(|slot| slot.as_ref().and_then(Weak::upgrade))
    })?;
    match owner {
        Some(owner) => owner.progress().map_err(|e| e.to_string()),
        None => Ok(()),
    }
}
pub(crate) fn inherited_watchdog_fd() -> Result<Option<i32>, String> {
    let owner = CURRENT.with(|slot| {
        slot.try_borrow()
            .map_err(|_| "working progress context reentered")
            .map(|slot| slot.as_ref().and_then(Weak::upgrade))
    })?;
    owner
        .map(|owner| owner.child_close_fd().map_err(|e| e.to_string()))
        .transpose()
}

/// Read-only adapters keep full-content comparisons unchanged while allowing
/// the actual parent to check progress between at most 64 KiB read operations.
pub(crate) struct ProgressReader<'a, R: std::io::Read + ?Sized>(&'a mut R);
pub(crate) fn progress_reader<R: std::io::Read + ?Sized>(reader: &mut R) -> ProgressReader<'_, R> {
    ProgressReader(reader)
}
impl<R: std::io::Read + ?Sized> std::io::Read for ProgressReader<'_, R> {
    fn read(&mut self, output: &mut [u8]) -> io::Result<usize> {
        progress().map_err(|e| failed(&e))?;
        let limit = output.len().min(65536);
        let count = self.0.read(&mut output[..limit])?;
        progress().map_err(|e| failed(&e))?;
        Ok(count)
    }
}
pub(crate) fn read_exact_at_progress(
    file: &std::fs::File,
    output: &mut [u8],
    mut offset: u64,
) -> io::Result<()> {
    use std::os::unix::fs::FileExt;
    for chunk in output.chunks_mut(65536) {
        progress().map_err(|e| failed(&e))?;
        file.read_exact_at(chunk, offset)?;
        offset = offset
            .checked_add(chunk.len() as u64)
            .ok_or_else(|| failed("working content offset overflow"))?;
        progress().map_err(|e| failed(&e))?;
    }
    Ok(())
}
