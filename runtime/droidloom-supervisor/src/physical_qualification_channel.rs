//! Owned physical qualification channel. It carries current execution facts,
//! never a saved report or a caller-supplied permission to qualify.
//!
//! The installed applications ELF owns both endpoints. The child still mints
//! Complete only inside its normal application factory; the parent retains a
//! different capture object, conditional on exact child exit and retirement.
use super::{BoundProcess, bounded_text, current_cgroup_parent, open_at, same_file};
use crate::control::application_probe::RuntimeEpoch;
use crate::main_custody::RuntimeMainCustody;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::fs::{self, File, OpenOptions};
use std::io;
use std::os::fd::AsRawFd;
use std::os::unix::fs::{FileExt, MetadataExt, OpenOptionsExt};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

#[path = "physical_qualification_capture.rs"]
mod capture;
#[path = "physical_qualification_socket.rs"]
mod socket;
use super::application_leaf_unit::qualification::{ChildPeer, KernelProfile};
pub use capture::{CapturedCompleteApplicationRun, capture_installed_physical_run};

pub const SUITE_SECONDS: u64 = 33_440;
pub const CASE_COUNT: usize = 14;
pub const SUMMARY_LIMIT: usize = 16 * 1024 * 1024;
pub const BINDING_LIMIT: usize = 128 * 1024;
pub(super) const EXE: &str = "/usr/bin/droidloom-applications";
pub(super) const TEMPLATE_NAME: &str = "droidloom-physical-qualification@.service";
pub(super) const TEMPLATE: &str =
    include_str!("../../../packaging/systemd/system/droidloom-physical-qualification@.service");

fn error(why: &str) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, why)
}
pub(super) fn sha(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
pub(super) fn digest_ok(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
pub(super) fn monotonic_ns() -> io::Result<u64> {
    let mut time = std::mem::MaybeUninit::<libc::timespec>::uninit();
    // SAFETY: time points to correctly sized writable timespec storage.
    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, time.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    let time = unsafe { time.assume_init() };
    u64::try_from(i128::from(time.tv_sec) * 1_000_000_000 + i128::from(time.tv_nsec))
        .map_err(|_| error("monotonic time is outside its normal range"))
}
fn end_ns(end: Instant) -> io::Result<u64> {
    let clock = monotonic_ns()?;
    let remaining = end
        .checked_duration_since(Instant::now())
        .ok_or_else(|| error("original qualification deadline exhausted"))?;
    clock
        .checked_add(
            u64::try_from(remaining.as_nanos())
                .map_err(|_| error("qualification deadline overflow"))?,
        )
        .ok_or_else(|| error("qualification deadline overflow"))
}
pub(super) fn instant_until(ns: u64, ceiling: Instant) -> io::Result<Instant> {
    let instant = Instant::now();
    let now = monotonic_ns()?;
    let remaining = ns
        .checked_sub(now)
        .filter(|v| *v > 0)
        .ok_or_else(|| error("original monotonic qualification deadline exhausted"))?;
    instant
        .checked_add(Duration::from_nanos(remaining))
        .map(|end| end.min(ceiling))
        .ok_or_else(|| error("qualification instant overflow"))
}
pub(super) fn plan_path(digest: &str) -> io::Result<PathBuf> {
    if !digest_ok(digest) {
        return Err(error("exact physical plan digest required"));
    }
    Ok(PathBuf::from(format!(
        "/var/lib/droidloom-qualification/physical-{digest}/PLAN.json"
    )))
}
pub(super) fn unit_name(digest: &str) -> io::Result<String> {
    plan_path(digest)?;
    Ok(format!("droidloom-physical-qualification@{digest}.service"))
}
pub(super) fn parent_argv(digest: &str) -> Vec<String> {
    vec![
        EXE.into(),
        "--owned-physical-plan-sha256".into(),
        digest.into(),
    ]
}
pub(super) fn child_argv(digest: &str) -> io::Result<Vec<String>> {
    Ok(vec![
        EXE.into(),
        "--physical-application-plan".into(),
        plan_path(digest)?.to_string_lossy().into_owned(),
        "--expect-physical-plan-sha256".into(),
        digest.into(),
    ])
}

/// Source-owned case order. This is not parsed from an external action string.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum QualificationCase {
    CalendarCore,
    CalendarReminder,
    CameraPhoto,
    ContactsSearch,
    ClockTimerPair,
    ClockAlarm,
    DocumentsSaf,
    DocumentsSearchSort,
    GalleryRotation,
    GalleryVideo,
    GallerySeek,
    GalleryAlbum,
    SettingsSupportedPages,
    IhgLondon,
}
impl QualificationCase {
    pub(super) fn ordinal(self) -> u8 {
        self as u8
    }
    pub(super) fn from_ordinal(value: u8) -> io::Result<Self> {
        const ALL: [QualificationCase; CASE_COUNT] = [
            QualificationCase::CalendarCore,
            QualificationCase::CalendarReminder,
            QualificationCase::CameraPhoto,
            QualificationCase::ContactsSearch,
            QualificationCase::ClockTimerPair,
            QualificationCase::ClockAlarm,
            QualificationCase::DocumentsSaf,
            QualificationCase::DocumentsSearchSort,
            QualificationCase::GalleryRotation,
            QualificationCase::GalleryVideo,
            QualificationCase::GallerySeek,
            QualificationCase::GalleryAlbum,
            QualificationCase::SettingsSupportedPages,
            QualificationCase::IhgLondon,
        ];
        ALL.get(value as usize)
            .copied()
            .ok_or_else(|| error("unknown qualification case"))
    }
    /// Complete original case budget; resource acknowledgements consume this window.
    pub fn window_seconds(self) -> u64 {
        [
            1690, 1450, 1260, 1180, 2100, 1570, 1960, 1960, 2290, 2290, 2290, 2290, 1660, 1440,
        ][self as usize]
    }
    pub(super) fn profile(self) -> KernelProfile {
        if self == Self::CalendarReminder {
            KernelProfile::Calendar
        } else {
            KernelProfile::Standard
        }
    }
}

fn f9(file: &File) -> io::Result<[u64; 9]> {
    let m = file.metadata()?;
    let ns = |s: i64, n: i64| {
        u64::try_from(i128::from(s) * 1_000_000_000 + i128::from(n))
            .map_err(|_| error("negative qualification input timestamp"))
    };
    Ok([
        m.dev(),
        m.ino(),
        m.mode() as u64,
        m.uid() as u64,
        m.gid() as u64,
        m.nlink(),
        m.len(),
        ns(m.mtime(), m.mtime_nsec())?,
        ns(m.ctime(), m.ctime_nsec())?,
    ])
}

pub(super) struct Plan {
    pub path: PathBuf,
    pub file: File,
    pub pin: [u64; 9],
    pub digest: String,
    parents: Vec<(PathBuf, File, [u64; 9])>,
}
impl Plan {
    pub fn open(digest: &str) -> io::Result<Self> {
        let path = plan_path(digest)?;
        if path.canonicalize()? != path {
            return Err(error("physical plan path has an alias"));
        }
        let mut parents = Vec::new();
        for p in path
            .parent()
            .ok_or_else(|| error("physical plan parent absent"))?
            .ancestors()
        {
            let file = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(p)?;
            let pin = f9(&file)?;
            if pin[3..5] != [0, 0]
                || pin[2] & 0o022 != 0
                || (Some(p) == path.parent() && pin[2] & 0o7777 != 0o700)
            {
                return Err(error("root protected physical stage parent required"));
            }
            parents.push((p.into(), file, pin));
        }
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&path)?;
        let pin = f9(&file)?;
        if pin[2] != u64::from(libc::S_IFREG | 0o400)
            || pin[3..6] != [0, 0, 1]
            || pin[6] == 0
            || pin[6] > 4 * 1024 * 1024
        {
            return Err(error("root immutable regular physical plan required"));
        }
        let result = Self {
            path,
            file,
            pin,
            digest: digest.into(),
            parents,
        };
        result.guard()?;
        Ok(result)
    }
    pub fn bytes(&self) -> io::Result<Vec<u8>> {
        let mut raw = vec![0; self.pin[6] as usize];
        self.file.read_exact_at(&mut raw, 0)?;
        if self.file.read_at(&mut [0; 1], self.pin[6])? != 0 || sha(&raw) != self.digest {
            return Err(error("actual whole physical plan differs"));
        }
        Ok(raw)
    }
    pub fn guard(&self) -> io::Result<()> {
        for (p, file, pin) in &self.parents {
            let named = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(p)?;
            if f9(file)?[..5] != pin[..5] || f9(&named)?[..5] != pin[..5] {
                return Err(error("held physical stage parent changed"));
            }
        }
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&self.path)?;
        if f9(&self.file)? != self.pin || f9(&named)? != self.pin {
            return Err(error("held physical plan changed"));
        }
        self.bytes()?;
        if f9(&self.file)? != self.pin || f9(&named)? != self.pin {
            return Err(error("physical plan changed during whole read"));
        }
        Ok(())
    }
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Hello {
    pub plan_bytes: u64,
    pub plan_sha256: String,
    pub epoch: RuntimeEpoch,
    pub suite_seconds: u64,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct CompleteHeader {
    pub summary_bytes: u64,
    pub summary_sha256: String,
    pub binding_bytes: u64,
    pub binding_sha256: String,
    pub selected_applications: u32,
    pub required_gates: u32,
}

/// The child-side private connection. It cannot be made from a saved receipt.
pub struct ChildChannel {
    socket: Option<socket::Socket>,
    peer: ChildPeer,
    plan: Plan,
    epoch: RuntimeEpoch,
    end: Instant,
    wire_end: u64,
    next_case: u8,
    sequence: u32,
    complete: bool,
}
impl ChildChannel {
    /// Called only by the normal physical factory after it reads its whole plan.
    pub fn acquire(
        path: &Path,
        bytes: u64,
        digest: &str,
        epoch: &RuntimeEpoch,
        original_end: Instant,
    ) -> io::Result<Self> {
        let plan = Plan::open(digest)?;
        if path != plan.path || bytes != plan.pin[6] {
            return Err(error(
                "child physical plan is not the exact parent-selected input",
            ));
        }
        let peer = ChildPeer::capture(digest)?;
        let socket = socket::Socket::inherited()?;
        let wire_end = end_ns(original_end)?;
        let hello = Hello {
            plan_bytes: bytes,
            plan_sha256: digest.into(),
            epoch: epoch.clone(),
            suite_seconds: SUITE_SECONDS,
        };
        let mut result = Self {
            socket: Some(socket),
            peer,
            plan,
            epoch: epoch.clone(),
            end: original_end,
            wire_end,
            next_case: 0,
            sequence: 0,
            complete: false,
        };
        let ack = result.exchange(1, 255, wire_end, serde_json::to_vec(&hello)?, original_end)?;
        if ack.end_ns > wire_end {
            return Err(error("parent attempted to extend the suite window"));
        }
        result.wire_end = ack.end_ns;
        result.end = instant_until(ack.end_ns, original_end)?;
        Ok(result)
    }
    pub fn deadline(&self) -> Instant {
        self.end
    }
    fn exchange(
        &mut self,
        kind: u8,
        case: u8,
        wire_end: u64,
        payload: Vec<u8>,
        end: Instant,
    ) -> io::Result<socket::Packet> {
        self.peer.guard()?;
        self.plan.guard()?;
        if self.complete || end > self.end {
            return Err(error("qualification channel is closed or extended"));
        }
        let socket = self
            .socket
            .as_ref()
            .ok_or_else(|| error("qualification channel was cancelled"))?;
        let packet = socket::Packet {
            sequence: self.sequence,
            kind,
            case,
            end_ns: wire_end,
            payload,
        };
        socket.send(&packet, end)?;
        let ack = socket.receive(self.peer.parent_pid(), end)?;
        if ack.kind != 5
            || ack.sequence != self.sequence
            || ack.case != case
            || !ack.payload.is_empty()
        {
            self.socket.take();
            return Err(error(
                "qualification acknowledgement differs from this exact request",
            ));
        }
        self.peer.guard()?;
        self.plan.guard()?;
        if Instant::now() >= end {
            return Err(error(
                "qualification acknowledgement exceeded original deadline",
            ));
        }
        self.sequence += 1;
        Ok(ack)
    }
    /// Begin exactly the next compiled case after the original case_end exists.
    pub fn begin_case(
        &mut self,
        case: QualificationCase,
        case_end: Instant,
    ) -> io::Result<CaseGuard<'_>> {
        if case.ordinal() != self.next_case
            || case_end > self.end
            || case_end
                .checked_duration_since(Instant::now())
                .is_none_or(|d| d > Duration::from_secs(case.window_seconds()))
        {
            return Err(error("qualification case order or original window differs"));
        }
        let wire = end_ns(case_end)?.min(self.wire_end);
        let ack = self.exchange(2, case.ordinal(), wire, Vec::new(), case_end)?;
        if ack.end_ns != wire {
            return Err(error("case resource ACK changed its original deadline"));
        }
        Ok(CaseGuard {
            channel: self,
            case,
            end: case_end,
            wire_end: wire,
            finished: false,
        })
    }
    /// The caller retains its actual Complete/source/results until this ACK.
    /// This method never reconstructs Complete from the serialized comparison.
    pub fn complete(
        &mut self,
        summary: &[u8],
        binding: &RuntimeMainCustody,
        end: Instant,
    ) -> io::Result<()> {
        if self.next_case as usize != CASE_COUNT
            || summary.is_empty()
            || summary.len() > SUMMARY_LIMIT
            || end > self.end
            || binding.epoch != self.epoch
        {
            return Err(error(
                "complete qualification requires all exact case boundaries and same Main",
            ));
        }
        binding.validate(&self.epoch).map_err(|e| error(&e))?;
        let body = serde_json::to_vec(binding)?;
        if body.len() > BINDING_LIMIT {
            return Err(error("complete Main comparison body exceeds bound"));
        }
        let header = CompleteHeader {
            summary_bytes: summary.len() as u64,
            summary_sha256: sha(summary),
            binding_bytes: body.len() as u64,
            binding_sha256: sha(&body),
            selected_applications: 39,
            required_gates: 377,
        };
        let mut payload = serde_json::to_vec(&header)?;
        payload.push(b'\n');
        payload.extend_from_slice(&body);
        let ack = self.exchange(4, 255, self.wire_end, payload, end)?;
        if ack.end_ns != self.wire_end {
            return Err(error("Complete ACK changed the suite deadline"));
        }
        self.complete = true;
        self.socket.take();
        Ok(())
    }
}

/// Drop cancels the private connection. It never fabricates a completed case.
pub struct CaseGuard<'a> {
    channel: &'a mut ChildChannel,
    case: QualificationCase,
    end: Instant,
    wire_end: u64,
    finished: bool,
}
impl CaseGuard<'_> {
    /// Call only after consuming the original case's successful historical seal.
    pub fn finish_after_history(mut self, original_case_end: Instant) -> io::Result<()> {
        if original_case_end != self.end {
            return Err(error("case end cannot be replaced"));
        }
        let ack =
            self.channel
                .exchange(3, self.case.ordinal(), self.wire_end, Vec::new(), self.end)?;
        if ack.end_ns != self.wire_end {
            return Err(error("case retirement ACK changed its end"));
        }
        self.channel.next_case += 1;
        self.finished = true;
        Ok(())
    }
}
impl Drop for CaseGuard<'_> {
    fn drop(&mut self) {
        if !self.finished {
            self.channel.socket.take();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn fixed_case_order_and_window_preserve_all_original_budgets() {
        let mut total = 0;
        for n in 0..14 {
            let c = QualificationCase::from_ordinal(n).unwrap();
            assert_eq!(c.ordinal(), n);
            total += c.window_seconds();
            assert_eq!(
                c.profile(),
                if n == 1 {
                    KernelProfile::Calendar
                } else {
                    KernelProfile::Standard
                }
            );
        }
        assert_eq!(total, 25_430);
        assert_eq!(total + 31 * 250 + 140 + 120, SUITE_SECONDS);
        assert!(QualificationCase::from_ordinal(14).is_err());
        assert!(plan_path("../caller").is_err());
    }
}
