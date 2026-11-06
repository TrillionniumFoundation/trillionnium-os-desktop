//! Bounded observations of the existing owner, never lifecycle authority.
//!
//! A reader must independently bind this producer to its held process/ELF,
//! outer unit/cgroup and initial Main fence. No API accepts these serialized
//! values as permission to spawn, commit, signal, retire or release a claim.
use super::capability::{self, Process};
use super::domain::{self, Identity};
use super::init_peer::Hello;
use super::init_log;
use super::policy::{self, PressureRelaySpec};
use droidloom_pressure_relay::{BootstrapStatus, LifecycleBroker};
use serde::{Deserialize, Serialize};
use std::fs::File;
use std::io;
use std::os::unix::fs::MetadataExt;
use std::os::unix::process::ExitStatusExt;
use std::process::ExitStatus;
use std::sync::{Arc, Mutex, MutexGuard};

const MAX_RECORDS: usize = 16;
const MAX_ERROR_BYTES: usize = 512;

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub(crate) struct FileRecord { pub device: u64, pub inode: u64 }
impl From<Identity> for FileRecord {
    fn from(id: Identity) -> Self { Self { device: id.device, inode: id.inode } }
}
impl From<droidloom_pressure_relay::FileId> for FileRecord {
    fn from(id: droidloom_pressure_relay::FileId) -> Self {
        Self { device: id.device, inode: id.inode }
    }
}
fn file_record(file: &File) -> io::Result<FileRecord> { Ok(Identity::of(file)?.into()) }

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub(crate) struct ProcessRecord {
    pub pid: i32,
    pub birth: u64,
    pub pidfd: FileRecord,
    pub proc_dir: FileRecord,
}
impl From<droidloom_pressure_relay::LifecycleProcessObservation> for ProcessRecord {
    fn from(value: droidloom_pressure_relay::LifecycleProcessObservation) -> Self {
        Self { pid: value.pid, birth: value.birth, pidfd: value.pidfd.into(), proc_dir: value.proc_dir.into() }
    }
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
struct ProducerRecord {
    process: ProcessRecord,
    namespaces: [FileRecord; 10],
    executable: FileRecord,
    executable_sha256: String,
}
impl ProducerRecord {
    fn capture() -> io::Result<Self> {
        let process = Process::current_leader_for_observation()?;
        let namespaces = process.namespaces_for_observation()?;
        let executable = process.executable()?;
        let before = executable.metadata()?;
        let digest = capability::hash(&executable)?;
        let after = executable.metadata()?;
        let stamp = |m: &std::fs::Metadata| {
            (m.dev(), m.ino(), m.size(), m.mtime(), m.mtime_nsec(), m.ctime(), m.ctime_nsec())
        };
        if stamp(&before) != stamp(&after) {
            return Err(domain::error("audit producer executable changed while hashing"));
        }
        let result = Self {
            process: process.observation()?,
            namespaces,
            executable: file_record(&executable)?,
            executable_sha256: policy::hex(&digest),
        };
        process.live()?;
        Ok(result)
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub(crate) struct BrokerRecord {
    state: u32,
    nonce: String,
    generation: String,
    budget: String,
    endpoint: FileRecord,
    cgroup: FileRecord,
    granted: bool,
    faulted: bool,
}
impl From<&BootstrapStatus> for BrokerRecord {
    fn from(status: &BootstrapStatus) -> Self {
        Self {
            state: status.state as u32, nonce: policy::hex(&status.nonce),
            generation: policy::hex(&status.generation), budget: policy::hex(&status.budget),
            endpoint: status.endpoint.into(), cgroup: status.cgroup.into(),
            granted: status.granted, faulted: status.faulted,
        }
    }
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub(crate) struct InitRecord {
    process: ProcessRecord,
    namespaces: [FileRecord; 10],
    root: FileRecord,
    cgroup: FileRecord,
    executable: FileRecord,
    executable_sha256: String,
    compat: FileRecord,
    compat_sha256: String,
    linker: FileRecord,
    linker_sha256: String,
    hello_wire_hex: String,
}
impl InitRecord {
    pub(crate) fn capture(hello: &Hello, wire: &[u8; 128]) -> io::Result<Self> {
        let namespaces = hello.namespaces.iter().map(file_record).collect::<io::Result<Vec<_>>>()?;
        Ok(Self {
            process: hello.process.observation()?,
            namespaces: namespaces.try_into().map_err(|_| domain::error("audit init namespace count differs"))?,
            root: file_record(&hello.root)?, cgroup: file_record(&hello.guest_domain)?,
            executable: hello.executable.identity().into(),
            executable_sha256: policy::hex(&hello.executable.digest()),
            compat: hello.compat.identity().into(), compat_sha256: policy::hex(&hello.compat.digest()),
            linker: hello.linker.identity().into(), linker_sha256: policy::hex(&hello.linker.digest()),
            hello_wire_hex: policy::hex(wire),
        })
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
struct RegistrationRecord {
    level: u32,
    window_us: u64,
    stall_us: u64,
    pressure: FileRecord,
    write_started_ns: u64,
    write_completed_ns: u64,
    bytes_written: u64,
    trigger: String,
}
/// Only the bounded registration/retirement summary is exposed here. Event
/// correlation, native expiry and kill effects need their separate evidence.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub(crate) struct RetirementRecord {
    status: BrokerRecord,
    authority_generation: String,
    lease_generation: String,
    cgroup: FileRecord,
    budget: String,
    granted: bool,
    faulted: bool,
    incomplete: bool,
    registrations: Vec<RegistrationRecord>,
    observations: u64,
    packets_queued: u64,
    event_records: u32,
    event_overflow: bool,
    stop_reason: u32,
    retired_monotonic_ns: u64,
}
impl RetirementRecord {
    pub(crate) fn capture(broker: &LifecycleBroker) -> io::Result<Self> {
        if !broker.retirement_complete() {
            return Err(domain::error("audit broker has not joined"));
        }
        let status = broker.latest_status().ok_or_else(|| domain::error("audit terminal status missing"))?;
        let audit = broker.pressure_audit().ok_or_else(|| domain::error("audit joined pressure receipt missing"))?;
        audit.validate().map_err(io::Error::other)?;
        let registrations = audit.registrations.records[..audit.registrations.count as usize].iter()
            .map(|r| Ok(RegistrationRecord {
                level: r.level, window_us: r.window_us, stall_us: r.stall_us,
                pressure: FileRecord { device: r.pressure_device, inode: r.pressure_inode },
                write_started_ns: r.write_started_ns, write_completed_ns: r.write_completed_ns,
                bytes_written: r.bytes_written, trigger: r.trigger_text().map_err(io::Error::other)?.to_owned(),
            })).collect::<io::Result<Vec<_>>>()?;
        Ok(Self {
            status: status.into(), authority_generation: policy::hex(&audit.authority_generation),
            lease_generation: policy::hex(&audit.registrations.lease_generation),
            cgroup: audit.cgroup.into(), budget: policy::hex(&audit.budget),
            granted: audit.granted, faulted: audit.faulted, incomplete: audit.incomplete,
            registrations, observations: audit.observations, packets_queued: audit.packets_queued,
            event_records: audit.events.count, event_overflow: audit.events.overflow,
            stop_reason: audit.stop_reason, retired_monotonic_ns: audit.retired_monotonic_ns,
        })
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(tag = "event", rename_all = "snake_case")]
pub(crate) enum Event {
    Prepared { domain: FileRecord },
    OwnerAttached { process: ProcessRecord },
    InitHello { init: InitRecord },
    BrokerReady { process: ProcessRecord, status: BrokerRecord },
    InitProjectSent { wire_hex: String },
    InitProjectedAccepted { wire_hex: String },
    InitCommitSent { wire_hex: String },
    InitDoneAccepted { wire_hex: String },
    BrokerActive { status: BrokerRecord },
    Retiring,
    BrokerRetired { receipt: RetirementRecord },
    ProcessesDead,
    DomainEmpty,
    Retired,
    ResourcesRemoved,
    ClaimReleased,
}
impl Event {
    fn bounded(&self) -> bool {
        let hex = |value: &str, bytes: usize| value.len() == bytes * 2
            && value.bytes().all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c));
        let broker = |value: &BrokerRecord| hex(&value.nonce, 32)
            && hex(&value.generation, 32) && hex(&value.budget, 32);
        match self {
            Self::InitHello { init } => hex(&init.hello_wire_hex, 128)
                && hex(&init.executable_sha256, 32) && hex(&init.compat_sha256, 32) && hex(&init.linker_sha256, 32),
            Self::BrokerReady { status, .. } | Self::BrokerActive { status } => broker(status),
            Self::InitProjectSent { wire_hex } | Self::InitProjectedAccepted { wire_hex }
                | Self::InitCommitSent { wire_hex } | Self::InitDoneAccepted { wire_hex } => hex(wire_hex, 128),
            Self::BrokerRetired { receipt } => broker(&receipt.status)
                && hex(&receipt.authority_generation, 32) && hex(&receipt.lease_generation, 32)
                && hex(&receipt.budget, 32) && receipt.registrations.len() <= 2
                && receipt.registrations.iter().all(|r| r.trigger.len() <= 64),
            _ => true,
        }
    }
    fn rank(&self) -> u8 {
        match self {
            Self::Prepared { .. } => 1, Self::OwnerAttached { .. } => 2,
            Self::InitHello { .. } => 3, Self::BrokerReady { .. } => 4,
            Self::InitProjectSent { .. } => 5, Self::InitProjectedAccepted { .. } => 6,
            Self::InitCommitSent { .. } => 7, Self::InitDoneAccepted { .. } => 8,
            Self::BrokerActive { .. } => 9, Self::Retiring => 10,
            Self::BrokerRetired { .. } => 11, Self::ProcessesDead => 12,
            Self::DomainEmpty => 13, Self::Retired => 14,
            Self::ResourcesRemoved => 15, Self::ClaimReleased => 16,
        }
    }
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
struct Record { sequence: u32, observed_monotonic_ns: u64, detail: Event }
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum FailureOrigin { Admission, Runtime, Retirement, Cleanup, Panic }
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
struct FailureRecord { origin: FailureOrigin, observed_monotonic_ns: u64, message: String }

/// The exact parent's wait result, not an inferred init exit or signal sender.
/// The process identity is the earlier live OwnerAttached observation. Missing
/// identity makes the journal incomplete but must not discard the wait result.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
struct NamespaceOwnerExit {
    host_pid: u32,
    process: Option<ProcessRecord>,
    observed_monotonic_ns: u64,
    raw_status: i32,
    exit_code: Option<i32>,
    signal: Option<i32>,
    core_dumped: bool,
    explicit_stop_requested_before_observation: bool,
    worker_retirement_started_before_observation: bool,
}

/// Data-only, bounded lifecycle observations. This is not an enrollment,
/// pressure, cleanup or production qualification by itself. Missing milestones
/// and `recording_incomplete` must never be inferred as successful operations.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct RelayLifecycleAudit {
    schema: u32,
    retained_after_exit: bool,
    nonce: String,
    canonical_spec_sha256: String,
    host_uid: u32,
    producer: Option<ProducerRecord>,
    memory_max_bytes: u64,
    memory_high_bytes: u64,
    memory_swap_max_bytes: u64,
    cpu_quota_us: u64,
    cpu_period_us: u64,
    tasks_max: u32,
    recording_incomplete: bool,
    recording_error: Option<String>,
    first_failure: Option<FailureRecord>,
    retirement_failure: Option<FailureRecord>,
    cleanup_failure: Option<FailureRecord>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    namespace_owner_exit: Option<NamespaceOwnerExit>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    init_log: Option<init_log::Observation>,
    records: Vec<Record>,
}
impl RelayLifecycleAudit {
    pub(crate) fn retained(mut self) -> Self { self.retained_after_exit = true; self }
}
struct Journal { snapshot: RelayLifecycleAudit, last_rank: u8 }
#[derive(Clone)]
pub(crate) struct Audit(Arc<Mutex<Journal>>);
fn monotonic_ns() -> io::Result<u64> {
    let mut value = libc::timespec { tv_sec: 0, tv_nsec: 0 };
    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut value) } != 0 {
        return Err(io::Error::last_os_error());
    }
    if value.tv_sec < 0 || value.tv_nsec < 0 || value.tv_nsec >= 1_000_000_000 {
        return Err(domain::error("audit monotonic clock invalid"));
    }
    (value.tv_sec as u64).checked_mul(1_000_000_000)
        .and_then(|n| n.checked_add(value.tv_nsec as u64))
        .ok_or_else(|| domain::error("audit monotonic clock overflow"))
}
fn bounded(message: &str) -> (String, bool) {
    let mut end = message.len().min(MAX_ERROR_BYTES);
    while !message.is_char_boundary(end) { end -= 1; }
    (message[..end].to_owned(), end != message.len())
}
impl Journal {
    fn gap(&mut self, message: &str) {
        self.snapshot.recording_incomplete = true;
        if self.snapshot.recording_error.is_none() { self.snapshot.recording_error = Some(bounded(message).0); }
    }
    fn append(&mut self, event: Event, now: u64) {
        if self.snapshot.records.len() >= MAX_RECORDS || !event.bounded() || event.rank() <= self.last_rank
            || now == 0 || self.snapshot.records.last().is_some_and(|r| r.observed_monotonic_ns > now) {
            self.gap("audit payload/order/capacity/clock violation");
            return;
        }
        self.last_rank = event.rank();
        self.snapshot.records.push(Record {
            sequence: self.snapshot.records.len() as u32 + 1, observed_monotonic_ns: now, detail: event,
        });
    }
    fn failure(&mut self, origin: FailureOrigin, message: &str, observed_monotonic_ns: u64) {
        let (message, truncated) = bounded(message);
        if truncated { self.gap("audit failure text truncated"); }
        let failure = FailureRecord { origin, observed_monotonic_ns, message };
        if self.snapshot.first_failure.is_none() { self.snapshot.first_failure = Some(failure.clone()); }
        if origin == FailureOrigin::Retirement && self.snapshot.retirement_failure.is_none() {
            self.snapshot.retirement_failure = Some(failure.clone());
        }
        if origin == FailureOrigin::Cleanup && self.snapshot.cleanup_failure.is_none() {
            self.snapshot.cleanup_failure = Some(failure);
        }
    }
}

#[cfg(test)]
fn fixture() -> Audit {
    // Data-only recording fixture; no HostContext, process authority or cell.
    Audit(Arc::new(Mutex::new(Journal {
        snapshot: RelayLifecycleAudit {
            schema: 1, retained_after_exit: false, nonce: "07".repeat(32),
            canonical_spec_sha256: "08".repeat(32), host_uid: 1001, producer: None,
            memory_max_bytes: 512 * 1024 * 1024, memory_high_bytes: 384 * 1024 * 1024,
            memory_swap_max_bytes: 0, cpu_quota_us: 100000, cpu_period_us: 100000, tasks_max: 64,
            recording_incomplete: false, recording_error: None, first_failure: None,
            retirement_failure: None, cleanup_failure: None, namespace_owner_exit: None, init_log: None,
            records: Vec::with_capacity(MAX_RECORDS),
        }, last_rank: 0,
    })))
}
#[cfg(test)]
pub(crate) fn test_snapshot() -> RelayLifecycleAudit {
    let audit = fixture();
    audit.lock().gap("synthetic data-only test snapshot; no lifecycle qualification");
    audit.snapshot()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use std::process::{Child, Command, Stdio};
    use std::time::{Duration, Instant};

    struct OwnedChild(Child);
    impl Drop for OwnedChild {
        fn drop(&mut self) {
            if self.0.try_wait().ok().flatten().is_none() { let _ = self.0.kill(); }
            let _ = self.0.wait();
        }
    }
    fn owned_wait(audit: &Audit, exit_code: u8, signal: Option<i32>, bind: bool) -> (u32, ExitStatus) {
        // An ordinary exact child, not a real Android namespace or an Owner
        // retirement certificate. The production Process pin and audit method
        // below observe the actual kernel identity and actual wait status.
        let mut child = OwnedChild(Command::new("/bin/sh")
            .args(["-c", &format!("read gate; exit {exit_code}")])
            .stdin(Stdio::piped()).stdout(Stdio::null()).stderr(Stdio::null())
            .spawn().unwrap());
        let process = Process::from_child(&mut child.0).unwrap();
        if bind { audit.record(process.observation().map(|process| Event::OwnerAttached { process })); }
        if let Some(signal) = signal { process.signal(signal).unwrap(); }
        else {
            child.0.stdin.as_mut().unwrap().write_all(b"exit\n").unwrap();
            drop(child.0.stdin.take());
        }
        let deadline = Instant::now() + Duration::from_secs(2);
        let status = loop {
            if let Some(status) = child.0.try_wait().unwrap() { break status; }
            assert!(Instant::now() < deadline, "owned audit child did not exit");
            std::thread::sleep(Duration::from_millis(2));
        };
        assert!(process.dead().unwrap());
        (child.0.id(), status)
    }

    #[test]
    fn unexpected_owned_hup_is_retained_before_later_stop_or_retirement() {
        let audit = fixture();
        let (pid, status) = owned_wait(&audit, 0, Some(libc::SIGHUP), true);
        assert_eq!(status.signal(), Some(libc::SIGHUP));
        audit.namespace_owner_exit(pid, status, false, false);
        let first = audit.snapshot();
        let exit = first.namespace_owner_exit.as_ref().unwrap();
        assert_eq!(exit.host_pid, pid);
        assert_eq!(exit.process.as_ref().unwrap().pid as u32, pid);
        assert_eq!(exit.raw_status, status.into_raw());
        assert_eq!(exit.signal, Some(libc::SIGHUP));
        assert_eq!(exit.exit_code, None);
        assert!(!exit.explicit_stop_requested_before_observation);
        let cause = first.first_failure.as_ref().unwrap();
        assert_eq!(cause.origin, FailureOrigin::Runtime);
        assert!(cause.message.contains("signal=Some(1)"));
        audit.namespace_owner_exit(pid, status, true, true);
        audit.record(Ok(Event::Retiring));
        audit.record(Ok(Event::Retired));
        audit.record(Ok(Event::ResourcesRemoved));
        audit.record(Ok(Event::ClaimReleased));
        let retired = audit.snapshot();
        assert_eq!(retired.namespace_owner_exit, first.namespace_owner_exit);
        assert_eq!(retired.first_failure, first.first_failure);
        assert_eq!(audit.first_failure_message().as_deref(), Some(cause.message.as_str()));
        assert!(!retired.recording_incomplete);
        assert_eq!(serde_json::from_slice::<RelayLifecycleAudit>(&serde_json::to_vec(&retired).unwrap()).unwrap(), retired);
    }

    #[test]
    fn owned_nonzero_code_retains_the_actual_raw_wait_status() {
        let audit = fixture();
        let (pid, status) = owned_wait(&audit, 17, None, true);
        assert_eq!(status.code(), Some(17));
        audit.namespace_owner_exit(pid, status, false, false);
        let result = audit.snapshot();
        let exit = result.namespace_owner_exit.unwrap();
        assert_eq!(exit.raw_status, status.into_raw());
        assert_eq!(exit.exit_code, Some(17));
        assert_eq!(exit.signal, None);
        assert!(result.first_failure.unwrap().message.contains("exit_code=Some(17)"));
    }

    #[test]
    fn explicit_stop_records_owned_term_without_inventing_runtime_failure() {
        let audit = fixture();
        let (pid, status) = owned_wait(&audit, 0, Some(libc::SIGTERM), true);
        audit.namespace_owner_exit(pid, status, true, false);
        let result = audit.snapshot();
        let exit = result.namespace_owner_exit.unwrap();
        assert_eq!(exit.signal, Some(libc::SIGTERM));
        assert!(exit.explicit_stop_requested_before_observation);
        assert!(result.first_failure.is_none());
        assert!(!result.recording_incomplete);
    }

    #[test]
    fn worker_retirement_keeps_the_earlier_failure_and_exact_child_status() {
        let audit = fixture();
        audit.failure(FailureOrigin::Runtime, "original enrollment failure");
        let (pid, status) = owned_wait(&audit, 0, Some(libc::SIGTERM), true);
        audit.namespace_owner_exit(pid, status, false, true);
        audit.failure(FailureOrigin::Cleanup, "later cleanup failure");
        let result = audit.snapshot();
        assert_eq!(result.first_failure.unwrap().message, "original enrollment failure");
        assert_eq!(result.cleanup_failure.unwrap().message, "later cleanup failure");
        assert!(result.namespace_owner_exit.unwrap().worker_retirement_started_before_observation);
    }

    #[test]
    fn successful_owned_exit_is_observed_without_reclassifying_android_shutdown() {
        let audit = fixture();
        let legacy = serde_json::to_vec(&audit.snapshot()).unwrap();
        assert!(!String::from_utf8(legacy.clone()).unwrap().contains("namespace_owner_exit"));
        let decoded: RelayLifecycleAudit = serde_json::from_slice(&legacy).unwrap();
        assert!(decoded.namespace_owner_exit.is_none());
        assert_eq!(serde_json::to_vec(&decoded).unwrap(), legacy);
        let (pid, status) = owned_wait(&audit, 0, None, true);
        assert!(status.success());
        audit.namespace_owner_exit(pid, status, false, false);
        let result = audit.snapshot();
        assert_eq!(result.namespace_owner_exit.unwrap().exit_code, Some(0));
        assert!(result.first_failure.is_none());
        assert!(!result.recording_incomplete);
    }

    #[test]
    fn missing_held_owner_identity_cannot_make_the_exit_record_complete() {
        let audit = fixture();
        let (pid, status) = owned_wait(&audit, 0, Some(libc::SIGHUP), false);
        audit.namespace_owner_exit(pid, status, false, false);
        let result = audit.snapshot();
        let exit = result.namespace_owner_exit.unwrap();
        assert_eq!(exit.raw_status, status.into_raw());
        assert!(exit.process.is_none());
        assert!(result.recording_incomplete);
        assert!(result.recording_error.unwrap().contains("earlier held identity"));
    }

    #[test]
    fn saturated_init_prefix_roundtrips_without_replacing_the_lifecycle_failure() {
        let audit = fixture();
        audit.failure(FailureOrigin::Runtime, "original init namespace failure");
        let first = audit.snapshot().first_failure;
        let capture = init_log::Capture::new([7; 32]).unwrap();
        // Real owned memfd plus synthetic longest bytes, not an Android log.
        (&*capture.writer().unwrap()).write_all(&vec![0xff; init_log::CAPACITY]).unwrap();
        let record = capture.finish(false);
        assert!(record.capacity_reached && record.held_fds_closed);
        assert_eq!(record.captured_hex.len(), 512 * 1024);
        audit.init_log(record.clone());
        let result = audit.snapshot();
        assert_eq!(result.first_failure, first);
        assert!(!result.recording_incomplete);
        let encoded = serde_json::to_vec(&result).unwrap();
        assert!(encoded.len() > 512 * 1024 && encoded.len() < 1024 * 1024);
        let decoded: RelayLifecycleAudit = serde_json::from_slice(&encoded).unwrap();
        assert_eq!(decoded, result);
        // A duplicate final observation is a recording gap, never a new
        // lifecycle success or an overwrite of the first capture/failure.
        audit.init_log(record);
        assert!(audit.snapshot().recording_incomplete);
        assert_eq!(audit.snapshot().first_failure, first);
        assert_eq!(audit.snapshot().init_log, result.init_log);
    }

    #[test]
    fn wrong_nonce_or_overbound_log_cannot_enter_the_retained_audit() {
        for foreign in [false, true] {
            let audit = fixture();
            audit.failure(FailureOrigin::Admission, "original attach failure");
            let mut record = init_log::Capture::new(if foreign { [8; 32] } else { [7; 32] })
                .unwrap().finish(false);
            if !foreign { record.captured_bytes = init_log::CAPACITY + 1; }
            audit.init_log(record);
            let result = audit.snapshot();
            assert!(result.init_log.is_none() && result.recording_incomplete);
            assert_eq!(result.first_failure.unwrap().message, "original attach failure");
        }
    }

    #[test]
    fn missing_observation_and_clock_or_order_failure_remain_incomplete() {
        let audit = fixture();
        audit.record(Err(domain::error("failed held-pidfd observation")));
        audit.record(Ok(Event::Retiring));
        audit.record(Ok(Event::Retired));
        let result = audit.snapshot();
        assert!(result.recording_incomplete);
        assert_eq!(result.recording_error.as_deref(), Some("failed held-pidfd observation"));
        assert_eq!(result.records.len(), 2);
        assert!(result.first_failure.is_none());
        for (first, second, now) in [
            (Event::Retiring, Event::Retiring, 2),
            (Event::Retired, Event::Retiring, 2),
            (Event::Retiring, Event::Retired, 0),
            (Event::Retiring, Event::Retired, 1),
        ] {
            let audit = fixture();
            audit.lock().append(first, 2);
            audit.lock().append(second, now);
            assert!(audit.snapshot().recording_incomplete);
            assert_eq!(audit.snapshot().records.len(), 1);
        }
    }
    #[test]
    fn successful_retirement_does_not_erase_run_or_cleanup_failure() {
        let audit = fixture();
        audit.failure(FailureOrigin::Runtime, "actual native enrollment deadline");
        audit.failure(FailureOrigin::Retirement, "broker receipt unavailable");
        audit.failure(FailureOrigin::Cleanup, "owned runtime could not be removed");
        audit.failure(FailureOrigin::Cleanup, "retry still blocked");
        audit.record(Ok(Event::Retiring));
        audit.record(Ok(Event::Retired));
        audit.record(Ok(Event::ResourcesRemoved));
        audit.record(Ok(Event::ClaimReleased));
        let result = audit.snapshot();
        assert_eq!(result.first_failure.as_ref().unwrap().origin, FailureOrigin::Runtime);
        assert_eq!(result.first_failure.as_ref().unwrap().message, "actual native enrollment deadline");
        assert_eq!(result.retirement_failure.as_ref().unwrap().message, "broker receipt unavailable");
        assert_eq!(result.cleanup_failure.as_ref().unwrap().message, "owned runtime could not be removed");
        assert!(!result.recording_incomplete);
        let encoded = serde_json::to_vec(&result).unwrap();
        assert_eq!(serde_json::from_slice::<RelayLifecycleAudit>(&encoded).unwrap(), result);
    }
    #[test]
    fn oversized_payload_and_utf8_truncation_cannot_be_silent() {
        let audit = fixture();
        audit.record(Ok(Event::InitCommitSent { wire_hex: "ff".repeat(129) }));
        assert!(audit.snapshot().records.is_empty());
        assert!(audit.snapshot().recording_incomplete);
        let audit = fixture();
        audit.failure(FailureOrigin::Runtime, &"界".repeat(600));
        let result = audit.snapshot();
        assert!(result.recording_incomplete);
        assert!(result.first_failure.as_ref().unwrap().message.len() <= MAX_ERROR_BYTES);
        let encoded = serde_json::to_vec(&result).unwrap();
        assert!(encoded.len() < 32768);
        assert!(serde_json::from_slice::<RelayLifecycleAudit>(&encoded).is_ok());
    }
    #[test]
    fn journal_poison_is_visible_and_never_panics_during_cleanup_recording() {
        let audit = fixture();
        let other = audit.clone();
        assert!(std::thread::spawn(move || {
            let _guard = other.0.lock().unwrap();
            panic!("owned audit mutex poison control");
        }).join().is_err());
        audit.failure(FailureOrigin::Cleanup, "original cleanup error");
        audit.record(Ok(Event::Retired));
        let result = audit.snapshot();
        assert!(result.recording_incomplete);
        assert_eq!(result.first_failure.unwrap().message, "original cleanup error");
        assert!(result.recording_error.unwrap().contains("mutex poisoned"));
    }
}
impl Audit {
    /// Called only after the original leader-only HostContext admission. Audit
    /// errors are sticky observations and do not replace its capability token.
    pub(crate) fn new(nonce: &[u8; 32], canonical_spec: &[u8; 32], host_uid: u32, policy: &PressureRelaySpec) -> Self {
        let producer = ProducerRecord::capture();
        let snapshot = RelayLifecycleAudit {
            schema: 1, retained_after_exit: false,
            nonce: policy::hex(nonce), canonical_spec_sha256: policy::hex(canonical_spec), host_uid,
            producer: producer.as_ref().ok().cloned(),
            memory_max_bytes: policy.memory_max_bytes, memory_high_bytes: policy.memory_high_bytes,
            memory_swap_max_bytes: policy.memory_swap_max_bytes, cpu_quota_us: policy.cpu_quota_us,
            cpu_period_us: policy.cpu_period_us, tasks_max: policy.tasks_max,
            recording_incomplete: producer.is_err(), recording_error: producer.err().map(|e| bounded(&e.to_string()).0),
            first_failure: None, retirement_failure: None, cleanup_failure: None, namespace_owner_exit: None, init_log: None,
            records: Vec::with_capacity(MAX_RECORDS),
        };
        Self(Arc::new(Mutex::new(Journal { snapshot, last_rank: 0 })))
    }
    fn lock(&self) -> MutexGuard<'_, Journal> {
        match self.0.lock() {
            Ok(guard) => guard,
            Err(poison) => {
                let mut guard = poison.into_inner();
                guard.gap("audit journal mutex poisoned");
                guard
            }
        }
    }
    pub(crate) fn record(&self, event: io::Result<Event>) {
        let mut journal = self.lock();
        match event.and_then(|event| Ok((event, monotonic_ns()?))) {
            Ok((event, now)) => journal.append(event, now),
            Err(error) => journal.gap(&error.to_string()),
        }
    }
    pub(crate) fn failure(&self, origin: FailureOrigin, message: &str) {
        let mut journal = self.lock();
        let observed_monotonic_ns = monotonic_ns().unwrap_or_else(|error| {
            journal.gap(&error.to_string()); 0
        });
        journal.failure(origin, message, observed_monotonic_ns);
    }
    /// Called only with the retained std::process::Child's actual wait result,
    /// before cleanup requests cancellation. A later Stop cannot reclassify an
    /// already observed failure. No serialized field is lifecycle authority.
    pub(crate) fn namespace_owner_exit(&self, host_pid: u32, status: ExitStatus,
        explicit_stop_requested: bool, worker_retirement_started: bool) {
        let mut journal = self.lock();
        if let Some(original) = &journal.snapshot.namespace_owner_exit {
            if original.host_pid != host_pid || original.raw_status != status.into_raw() {
                journal.gap("namespace owner Child wait result changed");
            }
            return;
        }
        let observed_monotonic_ns = monotonic_ns().unwrap_or_else(|error| {
            journal.gap(&error.to_string()); 0
        });
        let process = journal.snapshot.records.iter().find_map(|record| match &record.detail {
            Event::OwnerAttached { process } if process.pid as u32 == host_pid => Some(process.clone()),
            _ => None,
        });
        if process.is_none() { journal.gap("namespace owner exit lacks its earlier held identity"); }
        journal.snapshot.namespace_owner_exit = Some(NamespaceOwnerExit {
            host_pid, process, observed_monotonic_ns,
            raw_status: status.into_raw(), exit_code: status.code(), signal: status.signal(),
            core_dumped: status.core_dumped(),
            explicit_stop_requested_before_observation: explicit_stop_requested,
            worker_retirement_started_before_observation: worker_retirement_started,
        });
        // Successful Android shutdown is not reclassified as an error. For a
        // failed wait status, these flags describe observed prior intent only;
        // neither identifies the sender of a signal or the guest boot cause.
        if !status.success() && !explicit_stop_requested && !worker_retirement_started {
            journal.failure(FailureOrigin::Runtime, &format!(
                "namespace owner Child exited before explicit stop or worker retirement: pid={host_pid} raw_status={} exit_code={:?} signal={:?} core_dumped={}",
                status.into_raw(), status.code(), status.signal(), status.core_dumped()), observed_monotonic_ns);
        }
    }
    /// First observed run/cleanup cause for status propagation after retirement.
    /// This does not authorize retirement, resource removal or a new generation.
    pub(crate) fn first_failure_message(&self) -> Option<String> {
        self.lock().snapshot.first_failure.as_ref().map(|failure| failure.message.clone())
    }
    pub(crate) fn snapshot(&self) -> RelayLifecycleAudit { self.lock().snapshot.clone() }
    /// Diagnostic data only. Preserve lifecycle first_failure and every
    /// retirement gate even if logging was unavailable, full or incomplete.
    pub(crate) fn init_log(&self, value: init_log::Observation) {
        let mut journal = self.lock();
        if journal.snapshot.init_log.is_some() {
            journal.gap("init log final observation supplied twice");
            return;
        }
        if value.nonce != journal.snapshot.nonce
            || value.capacity_bytes != init_log::CAPACITY
            || value.captured_bytes > init_log::CAPACITY
            || value.captured_hex.len() != value.captured_bytes * 2
        {
            journal.gap("init log final observation binding/bound differs");
            return;
        }
        journal.snapshot.init_log = Some(value);
    }
}
