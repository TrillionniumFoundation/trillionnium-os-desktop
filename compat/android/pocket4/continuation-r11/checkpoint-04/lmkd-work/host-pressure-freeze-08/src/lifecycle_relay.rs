// Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
//! Production-callable listener/admission owner. No test peer or PID discovery.
//!
//! Lifecycle first prepares the private endpoint, projects only that socket,
//! and supplies its held CellAuthority before it releases LMKD's startup
//! barrier. CellRelay owns the accept loop and PSI owner on a separate thread;
//! lifecycle must obtain a RetirementReceipt before cell teardown/replacement.
use super::*;
use std::sync::atomic::AtomicU8;
use std::sync::OnceLock;

#[derive(Default)]
pub(super) struct OnceClaim(AtomicBool);
impl OnceClaim {
    pub(super) fn claim(&self) -> Result<()> {
        self.0.compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
            .map(|_| ()).map_err(|_| Error::Reject("cell lifecycle slot is already claimed"))
    }
}

// The current Droidloom lifecycle daemon owns one active cell. Retain this
// process-wide slot across Arc/authority recreation as well as object Drop.
// A new generation is admitted only after both exact old lifecycle processes
// are dead AND the old admission/PSI thread chain certified retirement.
struct RegistryEntry { owner: OwnedFd, init: OwnedFd, retired: Arc<AtomicBool> }
static REGISTRY: OnceLock<Mutex<Option<RegistryEntry>>> = OnceLock::new();
fn pidfd_dead(fd: RawFd) -> Result<bool> {
    let mut descriptor = libc::pollfd { fd, events: libc::POLLIN, revents: 0 };
    if unsafe { libc::poll(&mut descriptor, 1, 0) } < 0 { return Err(err("poll previous lifecycle pidfd")); }
    if descriptor.revents & (libc::POLLERR | libc::POLLNVAL) != 0 {
        return Err(Error::Reject("previous lifecycle pidfd lost"));
    }
    Ok(descriptor.revents & libc::POLLIN != 0)
}
fn reserve_process_slot(authority: &CellAuthority) -> Result<Arc<AtomicBool>> {
    reserve_lifecycle_process_slot(authority.owner.pidfd.as_raw_fd(), authority.init.pidfd.as_raw_fd())
}
pub(super) fn reserve_lifecycle_process_slot(owner: RawFd, init: RawFd) -> Result<Arc<AtomicBool>> {
    let mut registry = REGISTRY.get_or_init(|| Mutex::new(None)).lock()
        .map_err(|_| Error::Reject("lifecycle slot registry poisoned"))?;
    if let Some(old) = registry.as_ref() {
        if !old.retired.load(Ordering::Acquire) || !pidfd_dead(old.owner.as_raw_fd())? ||
            !pidfd_dead(old.init.as_raw_fd())? {
            return Err(Error::Reject("previous cell has not retired and exited"));
        }
    }
    let retired = Arc::new(AtomicBool::new(false));
    *registry = Some(RegistryEntry { owner: duplicate(owner)?,
        init: duplicate(init)?, retired: Arc::clone(&retired) });
    Ok(retired)
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(u8)]
pub enum RelayPhase { Listening = 1, Enrolling = 2, Active = 3, Retiring = 4, Retired = 5, Poisoned = 6 }

/// Only the joined admission thread constructs this receipt. It certifies the
/// PSI worker joined and every host sender/PSI/control/listener owner was
/// dropped; it does not certify Android foreground protection or real events.
#[derive(Debug)]
pub struct RetirementReceipt {
    granted: bool,
    diagnostics: Option<WorkerDiagnostics>,
    registration_audit: Option<RegistrationAudit>,
    reason: Option<String>,
}
impl RetirementReceipt {
    pub fn was_granted(&self) -> bool { self.granted }
    pub fn diagnostics(&self) -> Option<WorkerDiagnostics> { self.diagnostics }
    pub fn registration_audit(&self) -> Option<RegistrationAudit> { self.registration_audit }
    pub fn reason(&self) -> Option<&str> { self.reason.as_deref() }
}

pub struct PreparedRelay {
    listener: Listener,
    uid: u32,
    gid: u32,
}
impl PreparedRelay {
    /// `endpoint` comes from a private lifecycle-owned runtime directory. The
    /// caller must bind-project only this inode at /dev/socket/droidloom-lmkd-psi.
    /// Never derive it from an Android request, service name or process scan.
    pub fn bind(endpoint: &Path, uid: u32, gid: u32) -> Result<Self> {
        if endpoint.file_name().and_then(|s| s.to_str()) != Some("droidloom-lmkd-psi") {
            return Err(Error::Reject("unexpected fixed relay endpoint basename"));
        }
        if unsafe { libc::geteuid() } != 0 || unsafe { libc::getegid() } != 0 {
            return Err(Error::Reject("relay listener requires lifecycle root UID/GID"));
        }
        Ok(Self { listener: Listener::bind_for_role(endpoint, uid, gid)?, uid, gid })
    }
    pub fn endpoint(&self) -> &Path { &self.listener.path }
    pub fn endpoint_identity(&self) -> FileId { self.listener.path_id }
    /// Descriptor-only variant for an inherited trusted lifecycle channel.
    /// The caller projects the fixed socket from its already-held directory.
    pub fn bind_at(directory: File, uid: u32, gid: u32) -> Result<Self> {
        if unsafe { libc::geteuid() } != 0 || unsafe { libc::getegid() } != 0 {
            return Err(Error::Reject("relay listener requires lifecycle root UID/GID"));
        }
        Ok(Self { listener: Listener::bind_in_directory(directory, uid, gid)?, uid, gid })
    }
    /// Authority must contain the exact live owner/init, already frozen role
    /// namespaces and executable, and fixed accounted root/budget. Activate
    /// before releasing LMKD. The handle is retained even on protocol failure.
    pub fn activate(self, host: Arc<HostContext>, authority: Arc<CellAuthority>) -> Result<CellRelay> {
        host.validate_host_view()?;
        authority.validate()?;
        if self.uid != authority.role.uid || self.gid != authority.role.gid ||
            FileId::path(&self.listener.path)? != self.listener.path_id {
            return Err(Error::Reject("prepared endpoint role/identity mismatch"));
        }
        authority.service_claimed.claim()?;
        let raw = unsafe { libc::eventfd(0, libc::EFD_CLOEXEC | libc::EFD_NONBLOCK) };
        if raw < 0 { return Err(err("create lifecycle relay cancellation")); }
        let cancel = unsafe { OwnedFd::from_raw_fd(raw) };
        let worker_cancel = duplicate(cancel.as_raw_fd())?;
        let phase = Arc::new(AtomicU8::new(RelayPhase::Listening as u8));
        let worker_phase = Arc::clone(&phase);
        let retired = reserve_process_slot(&authority)?;
        let worker = match thread::Builder::new().name("p4-psi-admit".into()).spawn(move || {
            serve(self.listener, host, authority, worker_cancel, &worker_phase)
        }) {
            Ok(worker) => worker,
            Err(error) => {
                // No worker or PSI monitor was created. The old lifecycle
                // owner/init must still exit before another cell may claim.
                retired.store(true, Ordering::Release);
                return Err(io_err("spawn lifecycle relay admission", error));
            }
        };
        Ok(CellRelay { cancel, worker: Some(worker), phase, retired, receipt: None, poisoned: false })
    }
}

pub struct CellRelay {
    cancel: OwnedFd,
    worker: Option<JoinHandle<RetirementReceipt>>,
    phase: Arc<AtomicU8>,
    retired: Arc<AtomicBool>,
    receipt: Option<RetirementReceipt>,
    poisoned: bool,
}
impl CellRelay {
    pub fn phase(&self) -> RelayPhase {
        match self.phase.load(Ordering::Acquire) {
            1 => RelayPhase::Listening, 2 => RelayPhase::Enrolling, 3 => RelayPhase::Active,
            4 => RelayPhase::Retiring, 5 => RelayPhase::Retired, _ => RelayPhase::Poisoned,
        }
    }
    pub fn request_retirement(&self) {
        let value = 1u64;
        // An already pending nonblocking eventfd notification is sufficient.
        unsafe { libc::write(self.cancel.as_raw_fd(), (&value as *const u64).cast(), size_of::<u64>()) };
    }
    /// None means the owner is STILL retained: no cell replacement, namespace
    /// cleanup, or success acknowledgment is allowed. A panic is permanently
    /// poisoned; it cannot be converted into a completed-retirement receipt.
    pub fn finish_retirement(&mut self, timeout: Duration) -> Result<Option<&RetirementReceipt>> {
        if self.poisoned { return Err(Error::Reject("relay retirement is poisoned")); }
        if self.receipt.is_some() { return Ok(self.receipt.as_ref()); }
        self.request_retirement();
        let deadline = Instant::now().checked_add(timeout).ok_or(Error::Reject("relay retirement deadline overflow"))?;
        while self.worker.as_ref().is_some_and(|h| !h.is_finished()) {
            if Instant::now() >= deadline { return Ok(None); }
            thread::sleep(Duration::from_millis(1));
        }
        let worker = self.worker.take().ok_or(Error::Reject("relay worker handle missing"))?;
        match worker.join() {
            Ok(receipt) => {
                self.retired.store(true, Ordering::Release);
                self.receipt = Some(receipt);
                Ok(self.receipt.as_ref())
            }
            Err(_) => {
                self.poisoned = true;
                self.phase.store(RelayPhase::Poisoned as u8, Ordering::Release);
                Err(Error::Reject("relay admission thread panicked; cleanup unproven"))
            }
        }
    }
}
impl Drop for CellRelay {
    fn drop(&mut self) {
        self.request_retirement();
        // A detached admission thread retains its pending owner and all
        // authority handles until the PSI worker joins. Drop cannot provide a
        // retirement certificate, and does not reset either one-shot latch.
        if self.worker.as_ref().is_some_and(|h| h.is_finished()) {
            if let Some(worker) = self.worker.take() {
                if worker.join().is_ok() { self.retired.store(true, Ordering::Release); }
            }
        }
    }
}

fn cancelled(cancel: RawFd) -> Result<bool> {
    let mut descriptor = libc::pollfd { fd: cancel, events: libc::POLLIN, revents: 0 };
    if unsafe { libc::poll(&mut descriptor, 1, 0) } < 0 { return Err(err("poll relay cancellation")); }
    if descriptor.revents & (libc::POLLHUP | libc::POLLERR | libc::POLLNVAL) != 0 {
        return Err(Error::Reject("relay cancellation descriptor failed"));
    }
    Ok(descriptor.revents & libc::POLLIN != 0)
}

fn serve(listener: Listener, host: Arc<HostContext>, authority: Arc<CellAuthority>,
         cancel: OwnedFd, phase: &AtomicU8) -> RetirementReceipt {
    let mut listener = Some(listener);
    let mut pending: Option<PendingGrant> = None;
    let mut granted = false;
    let mut reason = None;
    let outcome = (|| -> Result<()> {
        loop {
            if cancelled(cancel.as_raw_fd())? { return Ok(()); }
            host.validate_host_view()?;
            authority.validate()?;
            if let Some(grant) = pending.as_mut() {
                if grant.owner().is_retired() { return Err(Error::Reject("active PSI lease revoked")); }
                let mut descriptor = libc::pollfd { fd: cancel.as_raw_fd(), events: libc::POLLIN, revents: 0 };
                if unsafe { libc::poll(&mut descriptor, 1, 100) } < 0 {
                    if io::Error::last_os_error().kind() == io::ErrorKind::Interrupted { continue; }
                    return Err(err("wait lifecycle relay cancellation"));
                }
                continue;
            }
            let listening = listener.as_ref().ok_or(Error::Reject("relay listener lost before admission"))?;
            let mut descriptors = [
                libc::pollfd { fd: cancel.as_raw_fd(), events: libc::POLLIN, revents: 0 },
                libc::pollfd { fd: listening.socket.as_raw_fd(), events: libc::POLLIN, revents: 0 },
            ];
            let ready = unsafe { libc::poll(descriptors.as_mut_ptr(), descriptors.len() as libc::nfds_t, 100) };
            if ready < 0 {
                if io::Error::last_os_error().kind() == io::ErrorKind::Interrupted { continue; }
                return Err(err("poll lifecycle relay listener"));
            }
            if descriptors[0].revents != 0 { return Ok(()); }
            if descriptors[1].revents & (libc::POLLHUP | libc::POLLERR | libc::POLLNVAL) != 0 {
                return Err(Error::Reject("relay listener failed"));
            }
            if descriptors[1].revents & libc::POLLIN == 0 { continue; }
            let Some(connection) = listening.accept()? else { continue; };
            // One accepted connection per service; no reconnect/error retry.
            // Closing the listener also drops all queued unaccepted clients.
            drop(listener.take());
            phase.store(RelayPhase::Enrolling as u8, Ordering::Release);
            let grant = host.admit_enrollment(connection, Arc::clone(&authority), Duration::from_millis(1000))?;
            pending = Some(grant);  // retain ownership before another fallible call
            if cancelled(cancel.as_raw_fd())? { return Ok(()); }
            pending.as_mut().expect("just stored pending grant").send_once(&host, &authority)?;
            granted = true;
            phase.store(RelayPhase::Active as u8, Ordering::Release);
        }
    })();
    if let Err(error) = outcome { reason = Some(error.to_string()); }
    phase.store(RelayPhase::Retiring as u8, Ordering::Release);
    drop(listener.take());
    let mut diagnostics = None;
    let registration_audit = pending.as_ref().map(PendingGrant::registration_audit);
    if let Some(grant) = pending.as_mut() {
        grant.owner().retire();
        loop {
            match grant.owner().finish_retirement(Duration::from_millis(25)) {
                Ok(true) => { diagnostics = Some(grant.owner().diagnostics()); break; }
                Ok(false) => {}  // retain owner and keep servicing retirement
                Err(error) => {
                    // A worker panic cannot produce a cleanup receipt. Retain
                    // this entire generation; lifecycle's bounded join fails.
                    // This path never returns a receipt. Record both causes
                    // now instead of overwriting a value that can never be
                    // observed while permanently retaining the poisoned owner.
                    eprintln!("droidloom-psi-owner: retirement unproven; admission={reason:?}; retirement={error}");
                    phase.store(RelayPhase::Poisoned as u8, Ordering::Release);
                    loop { thread::park_timeout(Duration::from_millis(100)); }
                }
            }
        }
    }
    drop(pending);
    // The receipt is returned only after all live owner values are dropped.
    drop(authority);
    drop(host);
    drop(cancel);
    phase.store(RelayPhase::Retired as u8, Ordering::Release);
    RetirementReceipt { granted, diagnostics, registration_audit, reason }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn one_lifecycle_claim_survives_failure_and_concurrent_clones() {
        let latch = Arc::new(OnceClaim::default());
        let barrier = Arc::new(std::sync::Barrier::new(16));
        let threads: Vec<_> = (0..16).map(|_| {
            let latch = Arc::clone(&latch);
            let barrier = Arc::clone(&barrier);
            thread::spawn(move || { barrier.wait(); latch.claim().is_ok() })
        }).collect();
        let successes = threads.into_iter().map(|t| usize::from(t.join().unwrap())).sum::<usize>();
        assert_eq!(successes, 1);
        // No success/failure/drop reset exists on this generation's latch.
        assert!(latch.claim().is_err());
    }
    #[test]
    fn cancellation_fd_is_real_bounded_and_idempotent() {
        let fd = unsafe { libc::eventfd(0, libc::EFD_CLOEXEC | libc::EFD_NONBLOCK) };
        assert!(fd >= 0);
        let fd = unsafe { OwnedFd::from_raw_fd(fd) };
        assert!(!cancelled(fd.as_raw_fd()).unwrap());
        let value = 1u64;
        assert_eq!(unsafe { libc::write(fd.as_raw_fd(), (&value as *const u64).cast(), size_of::<u64>()) }, 8);
        assert!(cancelled(fd.as_raw_fd()).unwrap());
        assert!(cancelled(fd.as_raw_fd()).unwrap());
    }
    #[test]
    fn live_lifecycle_pidfd_is_not_a_replacement_certificate() {
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, libc::getpid(), 0) };
        assert!(raw >= 0);
        let pidfd = unsafe { OwnedFd::from_raw_fd(raw as RawFd) };
        assert!(!pidfd_dead(pidfd.as_raw_fd()).unwrap());
    }
}
