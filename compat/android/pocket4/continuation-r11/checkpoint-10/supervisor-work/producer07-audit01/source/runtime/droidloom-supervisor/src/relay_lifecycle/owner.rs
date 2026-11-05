//! One retained supervisor owner for claim, finite domain, real init and broker.
use super::capability::{Artifact, Process};
use super::audit::{Audit, Event, FailureOrigin, RelayLifecycleAudit, RetirementRecord};
use super::domain::{self, Domain, Identity};
use super::entry;
use super::init_peer::{self, Hello, InitPeer};
use super::policy::{self, PressureRelaySpec};
use super::worker::Worker;
use crate::CellSpec;
use crate::generation_claim::{Claim, Store};
use droidloom_pressure_relay::{
    BootstrapSpec, BootstrapState, BootstrapStatus, ExecutablePin, HostContext, LifecycleBroker,
    MAX_LIFECYCLE_IO_TIMEOUT,
};
use std::ffi::CString;
use std::fs::File;
use std::io::{self, Read};
use std::os::fd::{AsFd, AsRawFd, BorrowedFd, FromRawFd};
use std::os::unix::fs::{FileExt, FileTypeExt, MetadataExt};
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{
    Arc,
    atomic::{AtomicU8, Ordering},
};
use std::time::{Duration, Instant};

const ENDPOINT_CLAIM: &str = "droidloom-lmkd-psi.claim";
const WAITING: u8 = 1;
const COMMITTED: u8 = 2;
const ACTIVE: u8 = 3;
const RETIRING: u8 = 4;
const RETIRED: u8 = 5;
const FAILED: u8 = 6;
fn error(message: &'static str) -> io::Error {
    domain::error(message)
}
fn relay<T>(result: droidloom_pressure_relay::Result<T>) -> io::Result<T> {
    result.map_err(io::Error::other)
}

struct Cancel(File);
impl Cancel {
    fn new() -> io::Result<Self> {
        let fd = unsafe { libc::eventfd(0, libc::EFD_CLOEXEC | libc::EFD_NONBLOCK) };
        if fd < 0 {
            Err(io::Error::last_os_error())
        } else {
            Ok(Self(unsafe { File::from_raw_fd(fd) }))
        }
    }
    fn request(&self) -> io::Result<()> {
        let value = 1u64.to_ne_bytes();
        loop {
            let count =
                unsafe { libc::write(self.0.as_raw_fd(), value.as_ptr().cast(), value.len()) };
            if count == value.len() as isize {
                return Ok(());
            }
            let e = io::Error::last_os_error();
            if e.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            if e.kind() == io::ErrorKind::WouldBlock {
                return Ok(());
            }
            return Err(e);
        }
    }
    fn requested(&self) -> io::Result<bool> {
        let mut poll = libc::pollfd {
            fd: self.0.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        let result = unsafe { libc::poll(&mut poll, 1, 0) };
        if result < 0 {
            return Err(io::Error::last_os_error());
        }
        if poll.revents & (libc::POLLERR | libc::POLLHUP | libc::POLLNVAL) != 0 {
            return Err(error("lifecycle cancellation FD fault"));
        }
        Ok(poll.revents & libc::POLLIN != 0)
    }
}

struct Endpoint {
    parent: File,
    directory: File,
    name: CString,
    identity: Identity,
    removed: bool,
    poisoned: bool,
}
struct EndpointProof {
    socket: File,
    marker: File,
    marker_bytes: [u8; 104],
}
impl Endpoint {
    fn create(runtime: &Path, nonce: &[u8; 32]) -> io::Result<Self> {
        let parent = domain::directory(runtime)?;
        let m = parent.metadata()?;
        if m.uid() != 0 || m.gid() != 0 || m.mode() & 0o077 != 0 {
            return Err(error("relay runtime directory is not private root-owned"));
        }
        let name =
            CString::new(format!("lmkd-relay-{}", policy::hex(nonce))).expect("hex component");
        if unsafe { libc::mkdirat(parent.as_raw_fd(), name.as_ptr(), 0o700) } != 0 {
            return Err(io::Error::last_os_error());
        }
        let directory = domain::at(
            parent.as_raw_fd(),
            &name,
            libc::O_RDONLY | libc::O_DIRECTORY,
            0,
        )?;
        let identity = Identity::of(&directory)?;
        Ok(Self {
            parent,
            directory,
            name,
            identity,
            removed: false,
            poisoned: false,
        })
    }
    fn validate(&self) -> io::Result<()> {
        if self.removed || self.poisoned {
            return Err(error("endpoint directory retired or poisoned"));
        }
        let named = domain::at(
            self.parent.as_raw_fd(),
            &self.name,
            libc::O_RDONLY | libc::O_DIRECTORY,
            0,
        )?;
        let m = named.metadata()?;
        if Identity::of(&named)? != self.identity
            || Identity::of(&self.directory)? != self.identity
            || m.uid() != 0
            || m.gid() != 0
            || m.mode() & 0o077 != 0
        {
            return Err(error("endpoint directory identity or ownership changed"));
        }
        Ok(())
    }
    fn remove_after(
        &mut self,
        proof: &EndpointProof,
        processes_retired: impl FnOnce() -> io::Result<()>,
    ) -> io::Result<()> {
        if self.poisoned {
            return Err(error("endpoint cleanup is poisoned"));
        }
        if self.removed {
            return Ok(());
        }
        let result = (|| {
            processes_retired()?;
            self.validate()?;
            for item in std::fs::read_dir(format!("/proc/self/fd/{}", self.directory.as_raw_fd()))?
            {
                let name = item?.file_name();
                if name != init_peer::ENDPOINT && name != ENDPOINT_CLAIM {
                    return Err(error("unexpected entry in owned relay endpoint directory"));
                }
            }
            match domain::named(&self.directory, init_peer::ENDPOINT, libc::O_PATH) {
                Ok(named) => {
                    if Identity::of(&named)? != Identity::of(&proof.socket)?
                        || !named.metadata()?.file_type().is_socket()
                    {
                        return Err(error("relay endpoint replaced before exact cleanup"));
                    }
                    if unsafe {
                        libc::unlinkat(
                            self.directory.as_raw_fd(),
                            c"droidloom-lmkd-psi".as_ptr(),
                            0,
                        )
                    } != 0
                    {
                        return Err(io::Error::last_os_error());
                    }
                }
                // The joined broker normally removes its own listener.
                Err(e) if e.kind() == io::ErrorKind::NotFound => {}
                Err(e) => return Err(e),
            }
            let marker = domain::named(&self.directory, ENDPOINT_CLAIM, libc::O_RDONLY)?;
            validate_marker(&marker, &proof.marker_bytes)?;
            if Identity::of(&marker)? != Identity::of(&proof.marker)? {
                return Err(error("relay endpoint claim replaced"));
            }
            if unsafe {
                libc::unlinkat(
                    self.directory.as_raw_fd(),
                    c"droidloom-lmkd-psi.claim".as_ptr(),
                    0,
                )
            } != 0
            {
                return Err(io::Error::last_os_error());
            }
            self.validate()?;
            if unsafe {
                libc::unlinkat(
                    self.parent.as_raw_fd(),
                    self.name.as_ptr(),
                    libc::AT_REMOVEDIR,
                )
            } != 0
            {
                return Err(io::Error::last_os_error());
            }
            Ok(())
        })();
        if result.is_ok() {
            self.removed = true;
        } else {
            self.poisoned = true;
        }
        result
    }
    fn prove_removed(&self) -> io::Result<()> {
        if !self.removed || self.poisoned {
            return Err(error("endpoint has no completed removal proof"));
        }
        match domain::at(self.parent.as_raw_fd(), &self.name, libc::O_PATH, 0) {
            Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(()),
            _ => Err(error("retired endpoint name reappeared")),
        }
    }
}
fn validate_marker(marker: &File, expected: &[u8; 104]) -> io::Result<()> {
    let m = marker.metadata()?;
    if !m.is_file()
        || m.uid() != 0
        || m.gid() != 0
        || m.mode() & 0o7777 != 0o600
        || m.nlink() != 1
        || m.size() != 104
    {
        return Err(error("broker one-shot marker type/owner/length differs"));
    }
    validate_marker_bytes(marker, expected)
}
fn validate_marker_bytes(marker: &File, expected: &[u8; 104]) -> io::Result<()> {
    if marker.metadata()?.size() != expected.len() as u64 {
        return Err(error("broker marker length differs"));
    }
    let mut actual = [0; 104];
    let mut filled = 0;
    while filled != actual.len() {
        let count = marker.read_at(&mut actual[filled..], filled as u64)?;
        if count == 0 {
            return Err(error("broker one-shot marker truncated"));
        }
        filled += count;
    }
    if &actual != expected {
        return Err(error(
            "broker one-shot marker differs from owned generation",
        ));
    }
    Ok(())
}
fn endpoint_proof(
    directory: &File,
    nonce: &[u8; 32],
    ready: &BootstrapStatus,
    owner: &Process,
    init: &Process,
) -> io::Result<EndpointProof> {
    let socket = domain::named(directory, init_peer::ENDPOINT, libc::O_PATH)?;
    if Identity::of(&socket)?
        != (Identity {
            device: ready.endpoint.device,
            inode: ready.endpoint.inode,
        })
    {
        return Err(error("actual listener inode differs from broker READY"));
    }
    let mut bytes = [0; 104];
    bytes[..8].copy_from_slice(b"P4SLOT1!");
    bytes[8..40].copy_from_slice(nonce);
    bytes[40..72].copy_from_slice(&ready.generation);
    for (at, value) in [
        (72, ready.cgroup.device),
        (80, ready.cgroup.inode),
        (88, owner.start()),
        (96, init.start()),
    ] {
        bytes[at..at + 8].copy_from_slice(&value.to_le_bytes());
    }
    let marker = domain::named(directory, ENDPOINT_CLAIM, libc::O_RDONLY)?;
    validate_marker(&marker, &bytes)?;
    Ok(EndpointProof {
        socket,
        marker,
        marker_bytes: bytes,
    })
}

struct Session {
    audit: Audit,
    host: Option<HostContext>,
    owner: Process,
    domain: Option<Arc<Domain>>,
    peer: InitPeer,
    policy: PressureRelaySpec,
    nonce: [u8; 32],
    directory: File,
    barrier: Artifact,
    lmkd: Artifact,
    broker_image: Artifact,
    cancel: Arc<Cancel>,
    phase: Arc<AtomicU8>,
    hello: Option<Hello>,
    broker: Option<LifecycleBroker>,
    initialize_started: bool,
    endpoint: Option<EndpointProof>,
    retired_init: Option<Process>,
    reason: Option<String>,
    retirement_error: Option<String>,
}
impl Session {
    fn run(&mut self) {
        let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| self.run_inner()));
        if let Err(payload) = outcome {
            self.audit.failure(FailureOrigin::Panic, "lifecycle worker panicked; generation remains persistently closed");
            self.phase.store(FAILED, Ordering::Release);
            self.retirement_error =
                Some("lifecycle worker panicked; generation remains persistently closed".into());
            self.peer.close();
            if let Some(broker) = &mut self.broker {
                let _ = relay(broker.revoke_unproven_control());
            }
            let _ = self.stop_exact_processes();
            // Worker::join records permanent poison and keeps this exact
            // Session in its poisoned mutex. No handle is substituted.
            std::panic::resume_unwind(payload);
        }
    }
    fn run_inner(&mut self) {
        let outcome = self.run_generation();
        if let Err(e) = outcome {
            self.audit.failure(FailureOrigin::Runtime, &e.to_string());
            self.reason = Some(e.to_string());
        }
        self.phase.store(RETIRING, Ordering::Release);
        self.audit.record(Ok(Event::Retiring));
        self.peer.close();
        let retired = self.retire_generation();
        if let Err(e) = retired {
            self.audit.failure(FailureOrigin::Retirement, &e.to_string());
            self.retirement_error = Some(e.to_string());
            self.phase.store(FAILED, Ordering::Release);
        } else {
            self.phase.store(RETIRED, Ordering::Release);
            self.audit.record(Ok(Event::Retired));
        }
    }
    fn run_generation(&mut self) -> io::Result<()> {
        let domain = Arc::clone(
            self.domain
                .as_ref()
                .ok_or_else(|| error("worker domain missing"))?,
        );
        self.hello = Some(self.peer.accept(
            &self.owner,
            &domain,
            &self.policy,
            &self.barrier,
            &self.cancel.0,
            &self.audit,
        )?);
        let hello = self.hello.as_ref().expect("retained actual init HELLO");
        let spec = BootstrapSpec {
            nonce: self.nonce,
            uid: self.policy.lmkd_uid,
            gid: self.policy.lmkd_gid,
            lmkd_sha256: self.lmkd.digest(),
            init_sha256: hello.executable.digest(),
        };
        let handles: [BorrowedFd<'_>; 16] = std::array::from_fn(|index| match index {
            0 => domain.android().as_fd(),
            1 => self.owner.fd().as_fd(),
            2 => hello.process.fd().as_fd(),
            3 => self.lmkd.file().as_fd(),
            4 => hello.executable.file().as_fd(),
            5 => self.directory.as_fd(),
            i => hello.namespaces[i - 6].as_fd(),
        });
        let executable = relay(ExecutablePin::from_lifecycle(
            self.broker_image.file().try_clone()?,
            self.broker_image.digest(),
        ))?;
        let host = self
            .host
            .take()
            .ok_or_else(|| error("host origin token already consumed"))?;
        // spawn returns actual Child ownership before any protocol I/O.
        self.broker = Some(relay(LifecycleBroker::spawn_in_context(
            host, executable, spec, &handles,
        ))?);
        self.initialize_started = true;
        let broker = self.broker.as_mut().expect("retained real broker");
        let ready = relay(broker.initialize())?.clone();
        self.audit.record(relay(broker.process_observation()).map(|process| Event::BrokerReady {
            process: process.into(), status: (&ready).into(),
        }));
        self.endpoint = Some(endpoint_proof(
            &self.directory,
            &self.nonce,
            &ready,
            &self.owner,
            &hello.process,
        )?);
        self.peer.commit(
            hello,
            &self.owner,
            &domain,
            &self.policy,
            &self.barrier,
            &ready,
            &self.endpoint.as_ref().expect("held endpoint proof").socket,
            &self.cancel.0,
            &mut || relay(broker.ready_for_init_commit()),
            &self.audit,
        )?;
        self.phase.store(COMMITTED, Ordering::Release);
        // Enrollment has a finite window separate from the constructor's
        // handshake. Values come from the explicit cell entry policy.
        let enrollment_deadline =
            Instant::now() + Duration::from_millis(self.policy.entry_timeout_ms as u64);
        let mut enrolled = false;
        loop {
            if self.cancel.requested()? {
                return Ok(());
            }
            self.owner.live()?;
            hello.process.live()?;
            domain.validate()?;
            if relay(broker.progress_available())? {
                let status = relay(broker.receive_progress(Duration::from_secs(1)))?;
                match status.state {
                    BootstrapState::Active if status.granted && !status.faulted => {
                        enrolled = true;
                        self.phase.store(ACTIVE, Ordering::Release);
                        self.audit.record(Ok(Event::BrokerActive { status: status.into() }));
                    }
                    BootstrapState::Retired => {
                        return Err(error(
                            "real broker retired; complete old cell recovery is required",
                        ));
                    }
                    _ => return Err(error("unexpected broker progress after init release")),
                }
            }
            if !enrolled && Instant::now() >= enrollment_deadline {
                return Err(error(
                    "native LMKD did not enroll before its finite startup deadline",
                ));
            }
            std::thread::sleep(Duration::from_millis(50));
        }
    }
    fn retire_generation(&mut self) -> io::Result<()> {
        // Preserve the first retirement failure, while still terminating the
        // exact owned processes. No missing receipt is replaced by exit alone.
        let mut failure = None;
        if let Some(broker) = self.broker.as_mut() {
            let result = if self.initialize_started {
                match relay(broker.retire(MAX_LIFECYCLE_IO_TIMEOUT)) {
                    Ok(true) => Ok(()),
                    Ok(false) => Err(error("broker retirement remains incomplete")),
                    Err(e) => Err(e),
                }
            } else {
                relay(broker.abort_before_initialize())
            };
            if let Err(e) = result {
                failure = Some(e);
                // Revokes the owned transport but explicitly supplies no
                // retirement receipt. The broker handle remains in Session.
                let _ = relay(broker.revoke_unproven_control());
            } else if self.initialize_started {
                self.audit.record(RetirementRecord::capture(broker).map(|receipt| Event::BrokerRetired { receipt }));
            }
        }
        if let Err(e) = self.stop_exact_processes() {
            if failure.is_none() {
                failure = Some(e);
            }
        }
        if let Some(e) = failure {
            return Err(e);
        }
        if self.hello.is_none() {
            return Err(error(
                "no authenticated actual init peer; generation remains persistently closed",
            ));
        }
        self.audit.record(Ok(Event::ProcessesDead));
        if self
            .broker
            .as_ref()
            .is_some_and(|b| !b.retirement_complete())
            || self.endpoint.is_none()
        {
            return Err(error(
                "generation lacks a complete broker/endpoint retirement chain",
            ));
        }
        self.domain
            .as_ref()
            .ok_or_else(|| error("retirement domain missing"))?
            .prove_empty()?;
        self.audit.record(Ok(Event::DomainEmpty));
        // Release all init root/mount/namespace file references after its
        // exact death. Keep the pidfd as final immutable retirement evidence.
        let Hello { process, .. } = self.hello.take().expect("checked actual init");
        self.retired_init = Some(process);
        self.domain = None;
        Ok(())
    }
    fn stop_exact_processes(&self) -> io::Result<()> {
        self.owner.signal(libc::SIGTERM)?;
        let deadline = Instant::now() + Duration::from_secs(2);
        loop {
            let init_dead = match self.hello.as_ref() {
                Some(h) => h.process.dead()?,
                None => true,
            };
            if self.owner.dead()? && init_dead {
                return Ok(());
            }
            if Instant::now() >= deadline {
                break;
            }
            std::thread::sleep(Duration::from_millis(10));
        }
        if let Some(hello) = self.hello.as_ref() {
            hello.process.signal(libc::SIGKILL)?;
        }
        self.owner.signal(libc::SIGKILL)?;
        if let Some(hello) = self.hello.as_ref() {
            hello.process.require_dead(Duration::from_secs(2))?;
        }
        self.owner.require_dead(Duration::from_secs(2))
    }
    fn prove_retired(&self) -> io::Result<()> {
        if let Some(retirement) = &self.retirement_error {
            let first = self
                .reason
                .as_deref()
                .unwrap_or("lifecycle retirement requested");
            return Err(io::Error::other(format!(
                "{first}; retirement remains incomplete: {retirement}"
            )));
        }
        if self.phase.load(Ordering::Acquire) != RETIRED
            || self.domain.is_some()
            || self.hello.is_some()
            || self
                .broker
                .as_ref()
                .is_none_or(|b| !b.retirement_complete())
        {
            return Err(error("worker has no complete generation retirement proof"));
        }
        self.owner.require_dead(Duration::ZERO)?;
        self.retired_init
            .as_ref()
            .ok_or_else(|| error("retired init pidfd missing"))?
            .require_dead(Duration::ZERO)
    }
}

pub(crate) struct Owner {
    audit: Audit,
    policy: PressureRelaySpec,
    nonce: [u8; 32],
    canonical_spec: [u8; 32],
    runtime: PathBuf,
    claim: Claim,
    domain: Arc<Domain>,
    endpoint: Option<Endpoint>,
    host: Option<HostContext>,
    entry_image: Artifact,
    broker_image: Option<Artifact>,
    barrier_image: Option<Artifact>,
    lmkd_image: Option<Artifact>,
    channel_host: Option<File>,
    channel_child: Option<File>,
    transfers: Option<[File; 3]>,
    cancel: Arc<Cancel>,
    phase: Arc<AtomicU8>,
    process: Option<Process>,
    worker: Option<Worker<Session>>,
    failure: Option<String>,
    termination_reason: Option<String>,
    resources_removed: bool,
    released: bool,
}
impl Owner {
    /// All read-only image/ABI checks precede the durable claim. The claim
    /// precedes the first finite-domain/runtime/network resource mutation.
    pub(crate) fn prepare(spec: &CellSpec, entry_path: &Path) -> io::Result<Option<Self>> {
        let Some(policy) = spec.pressure_relay.as_ref() else {
            return Ok(None);
        };
        if entry_path != policy.entry_supervisor.path {
            return Err(error(
                "configured entry path differs from the explicit relay package",
            ));
        }
        let entry_image = Artifact::open(&policy.entry_supervisor, true)?;
        query_entry_abi(&entry_image)?;
        let broker_image = Artifact::open(&policy.broker, true)?;
        let barrier_image = Artifact::open(&policy.init_barrier, false)?;
        let lmkd_image = Artifact::open(&policy.lmkd, true)?;
        let host = relay(HostContext::open())?;
        let nonce = PressureRelaySpec::nonce()?;
        let canonical_spec = entry::spec_digest(spec)?;
        let audit = Audit::new(&nonce, &canonical_spec, spec.host_uid, policy);
        let record = serde_json::to_vec(&serde_json::json!({"schema":1,"entry_abi":entry::ABI,
            "host_uid":spec.host_uid,"nonce":policy::hex(&nonce),"canonical_spec_sha256":policy::hex(&canonical_spec),
            "runtime":spec.runtime_dir,"domain_name":format!("g-{}",policy::hex(&nonce)),"pressure_relay":policy}))
            .map_err(io::Error::other)?;
        let store =
            Store::production(true)?.ok_or_else(|| error("generation store unavailable"))?;
        let claim = store.claim(spec.host_uid, &record)?;
        let domain = Arc::new(Domain::create(policy, &nonce)?);
        audit.record(Ok(Event::Prepared { domain: domain.identity().into() }));
        let (channel_host, channel_child) = init_peer::pair()?;
        Ok(Some(Self {
            audit,
            policy: policy.clone(),
            nonce,
            canonical_spec,
            runtime: spec.runtime_dir.clone(),
            claim,
            domain,
            endpoint: None,
            host: Some(host),
            entry_image,
            broker_image: Some(broker_image),
            barrier_image: Some(barrier_image),
            lmkd_image: Some(lmkd_image),
            channel_host: Some(channel_host),
            channel_child: Some(channel_child),
            transfers: None,
            cancel: Arc::new(Cancel::new()?),
            phase: Arc::new(AtomicU8::new(WAITING)),
            process: None,
            worker: None,
            failure: None,
            termination_reason: None,
            resources_removed: false,
            released: false,
        }))
    }
    pub(crate) fn prepare_endpoint(&mut self) -> io::Result<()> {
        if self.endpoint.is_some() {
            return Err(error("generation endpoint is one attempt"));
        }
        self.endpoint = Some(Endpoint::create(&self.runtime, &self.nonce)?);
        Ok(())
    }
    /// The returned path resolves only inside the spawned child's FD table.
    pub(crate) fn entry_path(&self) -> PathBuf {
        PathBuf::from(format!("/proc/self/fd/{}", init_peer::ENTRY_FD))
    }
    pub(crate) fn configure_command(&mut self, command: &mut Command) -> io::Result<()> {
        if self.transfers.is_some() || self.process.is_some() {
            return Err(error("generation spawn is one attempt"));
        }
        self.domain.validate()?;
        self.entry_image.validate(true)?;
        self.endpoint
            .as_ref()
            .ok_or_else(|| error("private endpoint not provisioned"))?
            .validate()?;
        let sources = [
            self.channel_child
                .as_ref()
                .ok_or_else(|| error("child init channel missing"))?
                .as_raw_fd(),
            self.domain.android().as_raw_fd(),
            self.entry_image.file().as_raw_fd(),
        ];
        let pinned = sources.map(|fd| {
            let raw = unsafe { libc::fcntl(fd, libc::F_DUPFD_CLOEXEC, 256) };
            if raw < 0 {
                Err(io::Error::last_os_error())
            } else {
                Ok(unsafe { File::from_raw_fd(raw) })
            }
        });
        let [a, b, c] = pinned;
        self.transfers = Some([a?, b?, c?]);
        let raw = self
            .transfers
            .as_ref()
            .expect("retained transfers")
            .each_ref()
            .map(AsRawFd::as_raw_fd);
        let parent = unsafe { libc::getpid() };
        entry::clean_command_environment(command);
        command
            .env(entry::ENTRY_ENV[0], entry::ABI)
            .env(entry::ENTRY_ENV[1], policy::hex(&self.nonce))
            .env(entry::ENTRY_ENV[2], policy::hex(&self.canonical_spec));
        unsafe {
            command.pre_exec(move || {
                if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) < 0
                    || libc::getppid() != parent
                {
                    return Err(io::Error::other(
                        "relay daemon disappeared before namespace owner exec",
                    ));
                }
                for (source, target) in raw.into_iter().zip([
                    init_peer::CONTROL_FD,
                    init_peer::DOMAIN_FD,
                    init_peer::ENTRY_FD,
                ]) {
                    if libc::dup2(source, target) < 0 || libc::fcntl(target, libc::F_SETFD, 0) < 0 {
                        return Err(io::Error::last_os_error());
                    }
                }
                // This is the exact still-unshared outer Child, not a PID supplied
                // by a request. Its inherited pidfd closes the PID1 pre-arm race.
                let owned = libc::syscall(libc::SYS_pidfd_open, libc::getpid(), 0) as i32;
                if owned < 0 {
                    return Err(io::Error::last_os_error());
                }
                let result = if owned == init_peer::OWNER_FD {
                    0
                } else {
                    libc::dup2(owned, init_peer::OWNER_FD)
                };
                if owned != init_peer::OWNER_FD {
                    libc::close(owned);
                }
                if result < 0 || libc::fcntl(init_peer::OWNER_FD, libc::F_SETFD, 0) < 0 {
                    return Err(io::Error::last_os_error());
                }
                Ok(())
            });
        }
        Ok(())
    }
    /// Called only after DevelopmentCell already owns Child/network/self.
    /// Every failure is stored in that Cell; no post-spawn error drops it.
    pub(crate) fn attach(&mut self, child: &mut Child) {
        self.transfers = None;
        self.channel_child = None;
        let result = self.attach_inner(child);
        if let Err(error) = result {
            self.audit.failure(FailureOrigin::Admission, &error.to_string());
            self.failure = Some(error.to_string());
            self.phase.store(FAILED, Ordering::Release);
            self.channel_host = None;
            let _ = self.cancel.request();
        }
    }
    fn attach_inner(&mut self, child: &mut Child) -> io::Result<()> {
        if self.worker.is_some() || self.process.is_some() {
            return Err(error("generation child attached twice"));
        }
        self.process = Some(Process::from_child(child)?);
        self.audit.record(self.process.as_ref().expect("retained exact owner").observation()
            .map(|process| Event::OwnerAttached { process }));
        let process = self
            .process
            .as_ref()
            .expect("retained exact owner")
            .try_clone()?;
        let session = Session {
            audit: self.audit.clone(),
            host: self.host.take(),
            owner: process,
            domain: Some(Arc::clone(&self.domain)),
            peer: InitPeer::new(
                self.channel_host
                    .take()
                    .ok_or_else(|| error("host init channel missing"))?,
                self.nonce,
                &self.policy,
            )?,
            policy: self.policy.clone(),
            nonce: self.nonce,
            directory: self
                .endpoint
                .as_ref()
                .ok_or_else(|| error("endpoint missing at attach"))?
                .directory
                .try_clone()?,
            barrier: self
                .barrier_image
                .take()
                .ok_or_else(|| error("barrier image already consumed"))?,
            lmkd: self
                .lmkd_image
                .take()
                .ok_or_else(|| error("LMKD image already consumed"))?,
            broker_image: self
                .broker_image
                .take()
                .ok_or_else(|| error("broker image already consumed"))?,
            cancel: Arc::clone(&self.cancel),
            phase: Arc::clone(&self.phase),
            hello: None,
            broker: None,
            initialize_started: false,
            endpoint: None,
            retired_init: None,
            reason: None,
            retirement_error: None,
        };
        self.worker = Some(Worker::new(session));
        self.worker
            .as_mut()
            .expect("retained worker")
            .start(Session::run)
    }
    pub(crate) fn poll(&self) -> io::Result<()> {
        if let Some(reason) = &self.failure {
            return Err(io::Error::other(format!(
                "relay generation admission failed: {reason}"
            )));
        }
        if self.phase.load(Ordering::Acquire) == FAILED {
            return Err(error(
                "relay worker retained an incomplete generation retirement",
            ));
        }
        if self.worker.as_ref().is_some_and(Worker::finished)
            && self.phase.load(Ordering::Acquire) != RETIRED
        {
            return Err(error(
                "relay worker ended without complete generation retirement",
            ));
        }
        Ok(())
    }
    pub(crate) fn request_stop(&self) -> io::Result<()> {
        self.cancel.request()
    }
    pub(crate) fn audit(&self) -> RelayLifecycleAudit { self.audit.snapshot() }
    pub(crate) fn record_cleanup_failure(&self, message: &str) {
        self.audit.failure(FailureOrigin::Cleanup, message);
    }
    pub(crate) fn termination_reason(&self) -> Option<&str> {
        self.termination_reason.as_deref()
    }
    pub(crate) fn enrolled(&self) -> bool {
        // ACTIVE can only follow the actual init COMMIT/DONE and the exact
        // broker's authenticated grant-delivery status. It proves no PSI event.
        self.failure.is_none() && self.phase.load(Ordering::Acquire) == ACTIVE
    }
    pub(crate) fn retire_before_network(&mut self, child: &mut Child) -> io::Result<()> {
        if self.resources_removed {
            return Ok(());
        }
        self.cancel.request()?;
        if child.try_wait()?.is_none() {
            return Err(error(
                "namespace Child has not been reaped before relay cleanup",
            ));
        }
        if let Some(reason) = &self.failure {
            return Err(io::Error::other(format!(
                "relay generation is persistently closed: {reason}"
            )));
        }
        let worker = self
            .worker
            .as_mut()
            .ok_or_else(|| error("actual lifecycle worker missing"))?;
        // A bounded join timeout retains its real handle and every resource;
        // it cannot make the next poll or stop return a synthetic success.
        worker.join(Duration::from_secs(10))?;
        let resources = worker.resources()?;
        resources.prove_retired()?;
        // Snapshot the original run failure while ownership is still held.
        // Releasing resources successfully must not erase why the cell died.
        self.termination_reason = resources.reason.clone();
        let process = self
            .process
            .as_ref()
            .ok_or_else(|| error("owned namespace process pin missing"))?;
        if process.pid() as u32 != child.id() {
            return Err(error("cleanup Child differs from retained owner"));
        }
        process.require_dead(Duration::ZERO)?;
        let domain = Arc::get_mut(&mut self.domain)
            .ok_or_else(|| error("worker still owns a live domain reference"))?;
        domain.remove_after(|| resources.prove_retired())?;
        let endpoint = self
            .endpoint
            .as_mut()
            .ok_or_else(|| error("retirement endpoint missing"))?;
        endpoint.remove_after(
            resources
                .endpoint
                .as_ref()
                .ok_or_else(|| error("retired endpoint inode proof missing"))?,
            || resources.prove_retired(),
        )?;
        self.resources_removed = true;
        self.audit.record(Ok(Event::ResourcesRemoved));
        Ok(())
    }
    /// Only after the exact network owner and entire runtime have cleaned up.
    /// Marker unlink is the final fallible operation in successful retirement.
    pub(crate) fn finish_after_runtime(&mut self, child: &mut Child) -> io::Result<()> {
        if self.released {
            return Ok(());
        }
        if !self.resources_removed || self.failure.is_some() {
            return Err(error("generation resources are not retired"));
        }
        let resources = self
            .worker
            .as_ref()
            .ok_or_else(|| error("retired worker missing"))?
            .resources()?;
        let domain = &self.domain;
        let endpoint = self
            .endpoint
            .as_ref()
            .ok_or_else(|| error("retired endpoint missing"))?;
        let owner = self
            .process
            .as_ref()
            .ok_or_else(|| error("retired owner missing"))?;
        let runtime = &self.runtime;
        self.claim.release_after(|| {
            resources.prove_retired()?;
            owner.require_dead(Duration::ZERO)?;
            if child.id() != owner.pid() as u32 || child.try_wait()?.is_none() {
                return Err(error("exact Child reap proof changed"));
            }
            domain.prove_removed()?;
            endpoint.prove_removed()?;
            match std::fs::symlink_metadata(runtime) {
                Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(()),
                _ => Err(error("runtime still exists at final generation release")),
            }
        })?;
        self.released = true;
        self.audit.record(Ok(Event::ClaimReleased));
        Ok(())
    }
}
impl Drop for Owner {
    fn drop(&mut self) {
        if !self.released {
            let _ = self.cancel.request();
        }
        // The persistent claim deliberately survives dropping this owner.
    }
}

fn query_entry_abi(executable: &Artifact) -> io::Result<()> {
    executable.validate(true)?;
    let mut command = Command::new(format!("/proc/self/fd/{}", executable.file().as_raw_fd()));
    command
        .arg("relay-entry-abi")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    entry::clean_command_environment(&mut command);
    let parent = unsafe { libc::getpid() };
    unsafe {
        command.pre_exec(move || {
            if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) < 0 || libc::getppid() != parent {
                return Err(io::Error::other("entry ABI parent disappeared"));
            }
            Ok(())
        });
    }
    let mut child = command.spawn()?;
    let deadline = Instant::now() + Duration::from_secs(2);
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Ok(status),
            Ok(None) if Instant::now() < deadline => std::thread::sleep(Duration::from_millis(5)),
            Ok(None) => break Err(error("entry ABI query timed out")),
            Err(e) => break Err(e),
        }
    };
    if status.is_err() {
        let _ = child.kill();
        let _ = child.wait();
    }
    let status = status?;
    let mut output = child
        .stdout
        .take()
        .ok_or_else(|| error("entry ABI output missing"))?;
    let flags = unsafe { libc::fcntl(output.as_raw_fd(), libc::F_GETFL) };
    if flags < 0
        || unsafe { libc::fcntl(output.as_raw_fd(), libc::F_SETFL, flags | libc::O_NONBLOCK) } < 0
    {
        return Err(io::Error::last_os_error());
    }
    let mut bytes = Vec::new();
    output.by_ref().take(129).read_to_end(&mut bytes)?;
    if !status.success() || bytes != format!("{}\n", entry::ABI).as_bytes() {
        return Err(error("paired entry ABI is unavailable or differs"));
    }
    executable.validate(true)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn cancellation_remains_latched_across_repeated_stop_requests() {
        let cancel = Cancel::new().unwrap();
        assert!(!cancel.requested().unwrap());
        cancel.request().unwrap();
        cancel.request().unwrap();
        assert!(cancel.requested().unwrap());
        assert!(cancel.requested().unwrap());
        let flags = unsafe { libc::fcntl(cancel.0.as_raw_fd(), libc::F_GETFD) };
        assert_ne!(flags & libc::FD_CLOEXEC, 0);
    }
    #[test]
    fn altered_broker_marker_cannot_authorize_directory_cleanup() {
        let mut file = tempfile::tempfile().unwrap();
        use std::io::Write;
        file.write_all(&[7; 104]).unwrap();
        validate_marker_bytes(&file, &[7; 104]).unwrap();
        assert!(validate_marker_bytes(&file, &[8; 104]).is_err());
        // Deliberately no source-side UID or mode relaxation: a normal
        // caller-owned temporary file cannot become production authority.
        file.set_len(103).unwrap();
        assert!(validate_marker_bytes(&file, &[7; 104]).is_err());
    }
}
