// Copyright 2026 Droidloom contributors
// SPDX-License-Identifier: Apache-2.0
use super::*;
use std::sync::atomic::{AtomicU32, AtomicU64};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PressureLevel { Medium, Critical }
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct PressureConfig { pub level: PressureLevel, pub window_us: u64, pub stall_us: u64 }
impl PressureConfig {
    fn validate(self) -> Result<()> {
        if !(500_000..=10_000_000).contains(&self.window_us) || self.stall_us == 0 || self.stall_us > self.window_us {
            return Err(Error::Reject("invalid existing PSI monitor parameters"));
        }
        Ok(())
    }
    pub fn exact_trigger(self) -> Result<String> {
        self.validate()?;
        Ok(format!("{} {} {}", match self.level { PressureLevel::Medium => "some", PressureLevel::Critical => "full" }, self.stall_us, self.window_us))
    }
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ScopeRequest { pub cgroup: FileId, pub budget: [u8; 32], pub authority_generation: [u8; 32] }
impl CellAuthority {
    pub fn scope_request(&self) -> ScopeRequest {
        ScopeRequest { cgroup: self.root_id, budget: self.budget.canonical(), authority_generation: self.generation }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct WorkerDiagnostics { pub observations: u64, pub packets_queued: u64, pub stop_reason: u32 }
#[derive(Default)]
pub(super) struct Counters { observations: AtomicU64, queued: AtomicU64, reason: AtomicU32 }
impl Counters {
    pub(super) fn snapshot(&self) -> WorkerDiagnostics {
        WorkerDiagnostics { observations: self.observations.load(Ordering::Acquire), packets_queued: self.queued.load(Ordering::Acquire), stop_reason: self.reason.load(Ordering::Acquire) }
    }
    fn stop(&self, reason: u32) { let _ = self.reason.compare_exchange(0, reason, Ordering::AcqRel, Ordering::Acquire); }
}
pub(super) struct WorkerMonitor { pressure: File, sender: OwnedFd, config: PressureConfig, sequence: u64 }
pub struct RegisteredLease { pub owner: LeaseOwner, pub recipients: Vec<OwnedFd>, pub configs: Vec<PressureConfig> }

fn notification_pair() -> Result<(OwnedFd, OwnedFd)> {
    let mut pair = [-1; 2];
    if unsafe { libc::socketpair(libc::AF_UNIX, libc::SOCK_SEQPACKET | libc::SOCK_NONBLOCK | libc::SOCK_CLOEXEC, 0, pair.as_mut_ptr()) } < 0 { return Err(err("PSI notification pair")); }
    let sender = unsafe { OwnedFd::from_raw_fd(pair[0]) };
    let recipient = unsafe { OwnedFd::from_raw_fd(pair[1]) };
    let size: libc::c_int = 4096;
    if unsafe { libc::setsockopt(sender.as_raw_fd(), libc::SOL_SOCKET, libc::SO_SNDBUF, (&size as *const libc::c_int).cast(), size_of::<libc::c_int>() as libc::socklen_t) } < 0 ||
        socket_integer(sender.as_raw_fd(), libc::SO_SNDBUF)? > 8192 ||
        unsafe { libc::shutdown(sender.as_raw_fd(), libc::SHUT_RD) } < 0 ||
        unsafe { libc::shutdown(recipient.as_raw_fd(), libc::SHUT_WR) } < 0 {
        return Err(Error::Reject("PSI notification capability setup failed"));
    }
    Ok((sender, recipient))
}
fn register_exact(authority: &CellAuthority, config: PressureConfig) -> Result<File> {
    config.validate()?;
    authority.validate()?;
    let file = open_at(&authority.root, "memory.pressure", libc::O_RDWR | libc::O_NONBLOCK | libc::O_NOFOLLOW)?;
    require_fs(&file, CGROUP2_MAGIC)?;
    let id = FileId::of(&file)?;
    if id.device != authority.root_id.device { return Err(Error::Reject("pressure file filesystem differs")); }
    let trigger = config.exact_trigger()?;
    let count = unsafe { libc::write(file.as_raw_fd(), trigger.as_ptr().cast(), trigger.len()) };
    if count < 0 { return Err(err("register exact held cgroup PSI trigger")); }
    if count as usize != trigger.len() { return Err(Error::Reject("short PSI registration write")); }
    if FileId::of(&file)? != id { return Err(Error::Reject("pressure file identity changed")); }
    authority.validate()?;
    Ok(file)
}
impl LeaseOwner {
    /// Scope and configuration fields may be echoed from a request, but none
    /// supplies authority. Only the exact held authority can be registered.
    /// Every partial resource is RAII-owned before the next fallible operation.
    pub fn register(peer: VerifiedPeer, host: Arc<HostContext>, authority: Arc<CellAuthority>,
        request: ScopeRequest, configs: &[PressureConfig]) -> Result<RegisteredLease> {
        peer.revalidate(&host, &authority)?;
        if request != authority.scope_request() { return Err(Error::Reject("requested scope is not the held cell generation")); }
        if configs.is_empty() || configs.len() > 2 { return Err(Error::Reject("PSI monitor count outside bound")); }
        for config in configs { config.validate()?; }
        if configs.len() == 2 && configs[0].level == configs[1].level { return Err(Error::Reject("duplicate PSI level")); }
        let mut generation = [0u8; 32];
        let got = unsafe { libc::getrandom(generation.as_mut_ptr().cast(), generation.len(), 0) };
        if got != generation.len() as isize || generation.iter().all(|b| *b == 0) { return Err(err("fresh registered lease nonce")); }
        let mut monitors = Vec::with_capacity(configs.len());
        let mut revokers = Vec::with_capacity(configs.len());
        let mut recipients = Vec::with_capacity(configs.len());
        for config in configs {
            let pressure = register_exact(&authority, *config)?;
            let (sender, recipient) = notification_pair()?;
            revokers.push(duplicate(sender.as_raw_fd())?);
            recipients.push(recipient);
            monitors.push(WorkerMonitor { pressure, sender, config: *config, sequence: 0 });
            peer.revalidate(&host, &authority)?;
        }
        let owner = Self::start_with_monitors(peer, host, authority, generation, monitors, revokers)?;
        Ok(RegisteredLease { owner, recipients, configs: configs.to_vec() })
    }
}

fn now_ns() -> Result<u64> {
    let mut t: libc::timespec = unsafe { zeroed() };
    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut t) } != 0 || t.tv_sec < 0 || !(0..1_000_000_000).contains(&t.tv_nsec) {
        return Err(Error::Reject("invalid monotonic clock"));
    }
    let value = (t.tv_sec as u64).checked_mul(1_000_000_000).and_then(|s| s.checked_add(t.tv_nsec as u64)).ok_or(Error::Reject("monotonic overflow"))?;
    if value == 0 { return Err(Error::Reject("zero monotonic clock")); }
    Ok(value)
}
fn put(frame: &mut [u8; 128], offset: usize, value: u64, bytes: usize) {
    frame[offset..offset + bytes].copy_from_slice(&value.to_le_bytes()[..bytes]);
}
fn frame(authority: &CellAuthority, generation: [u8; 32], config: PressureConfig, sequence: u64, observed: u64) -> [u8; 128] {
    let mut frame = [0u8; 128];
    frame[..8].copy_from_slice(b"P4PSI01!"); put(&mut frame, 8, 1, 4);
    put(&mut frame, 12, match config.level { PressureLevel::Medium => 1, PressureLevel::Critical => 2 }, 4);
    frame[16..48].copy_from_slice(&generation);
    put(&mut frame, 48, authority.root_id.device, 8); put(&mut frame, 56, authority.root_id.inode, 8);
    frame[64..96].copy_from_slice(&authority.budget.canonical());
    put(&mut frame, 96, config.window_us, 8); put(&mut frame, 104, config.stall_us, 8);
    put(&mut frame, 112, sequence, 8); put(&mut frame, 120, observed, 8);
    frame
}
fn elapsed_valid(now: u64, before: u64, window: Option<u64>) -> bool {
    now >= before && window.is_none_or(|w| now - before < w)
}

pub(super) fn run_worker(peer: &VerifiedPeer, host: &HostContext, authority: &CellAuthority,
    generation: [u8; 32], cancel: &OwnedFd, state: &LeaseState, counters: &Counters,
    mut monitors: Vec<WorkerMonitor>) {
    struct RevokeBeforeMonitorsDrop<'a>(&'a LeaseState);
    impl Drop for RevokeBeforeMonitorsDrop<'_> { fn drop(&mut self) { self.0.revoke(); } }
    // A local guard is dropped before function parameters, including monitors,
    // on every return/unwind. Invalidate/shutdown before PSI release can stall.
    let _revoke = RevokeBeforeMonitorsDrop(state);
    // Stop reasons are bounded metadata: 1 cancellation, 2 process/control,
    // 3 identity/budget, 4 clock/progress, 5 monitor error, 6 send/sequence.
    let minimum_window = monitors.iter().map(|m| m.config.window_us * 1000).min();
    let timeout_ms = minimum_window.map(|n| (n / 4 / 1_000_000).min(100) as libc::c_int).unwrap_or(100);
    let mut poll = Vec::with_capacity(5 + monitors.len());
    poll.extend([
        libc::pollfd { fd: cancel.as_raw_fd(), events: libc::POLLIN, revents: 0 },
        libc::pollfd { fd: peer.pin.pidfd.as_raw_fd(), events: libc::POLLIN, revents: 0 },
        libc::pollfd { fd: authority.owner.pidfd.as_raw_fd(), events: libc::POLLIN, revents: 0 },
        libc::pollfd { fd: authority.init.pidfd.as_raw_fd(), events: libc::POLLIN, revents: 0 },
        libc::pollfd { fd: peer.connection.socket.as_raw_fd(), events: libc::POLLIN | libc::POLLRDHUP, revents: 0 },
    ]);
    for m in &monitors { poll.push(libc::pollfd { fd: m.pressure.as_raw_fd(), events: libc::POLLPRI, revents: 0 }); }
    let mut progress = match now_ns() { Ok(t) => t, Err(_) => { counters.stop(4); return; } };
    loop {
        if !state.active.load(Ordering::Acquire) { counters.stop(1); break; }
        if peer.revalidate(host, authority).is_err() { counters.stop(3); break; }
        let pre_poll = match now_ns() { Ok(t) if elapsed_valid(t, progress, minimum_window) => t, _ => { counters.stop(4); break; } };
        for p in &mut poll { p.revents = 0; }
        let n = unsafe { libc::poll(poll.as_mut_ptr(), poll.len() as libc::nfds_t, timeout_ms) };
        let observed = match now_ns() { Ok(t) if elapsed_valid(t, progress, minimum_window) && t >= pre_poll => t, _ => { counters.stop(4); break; } };
        if n < 0 { counters.stop(5); break; }
        if poll[..5].iter().any(|p| p.revents != 0) { counters.stop(if poll[0].revents != 0 { 1 } else { 2 }); break; }
        if poll[5..].iter().any(|p| p.revents & (libc::POLLERR | libc::POLLHUP | libc::POLLNVAL) != 0 || p.revents & !libc::POLLPRI != 0) { counters.stop(5); break; }
        // PSI poll consumes an event bit. Never confirm it with another poll.
        if poll[5..].iter().any(|p| p.revents & libc::POLLPRI != 0) {
            if peer.revalidate(host, authority).is_err() { counters.stop(3); break; }
            let mut failed = false;
            for (i, monitor) in monitors.iter_mut().enumerate() {
                if poll[i + 5].revents & libc::POLLPRI == 0 { continue; }
                counters.observations.fetch_add(1, Ordering::AcqRel);
                let before_send = match now_ns() {
                    Ok(t) if elapsed_valid(t, progress, minimum_window) && elapsed_valid(t, observed, Some(monitor.config.window_us * 1000)) => t,
                    _ => { counters.stop(4); failed = true; break; }
                };
                if !state.active.load(Ordering::Acquire) { counters.stop(1); failed = true; break; }
                monitor.sequence = match monitor.sequence.checked_add(1) {
                    Some(s) if s != u64::MAX => s,
                    _ => { counters.stop(6); failed = true; break; }
                };
                let packet = frame(authority, generation, monitor.config, monitor.sequence, observed);
                if unsafe { libc::send(monitor.sender.as_raw_fd(), packet.as_ptr().cast(), packet.len(), libc::MSG_DONTWAIT | libc::MSG_NOSIGNAL) } != packet.len() as isize {
                    counters.stop(6); failed = true; break;
                }
                counters.queued.fetch_add(1, Ordering::AcqRel);
                match now_ns() {
                    Ok(t) if t >= before_send && elapsed_valid(t, progress, minimum_window) && elapsed_valid(t, observed, Some(monitor.config.window_us * 1000)) => {},
                    _ => { counters.stop(4); failed = true; break; }
                }
            }
            if failed { break; }
        }
        progress = match now_ns() { Ok(t) if elapsed_valid(t, progress, minimum_window) && t >= observed => t, _ => { counters.stop(4); break; } };
    }
    // The caller revokes every host sender alias. Dropping this vector also
    // closes all real PSI descriptions before thread completion is observable.
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn exact_thresholds_and_bounded_progress_are_not_relaxed() {
        let c = PressureConfig { level: PressureLevel::Critical, window_us: 1_000_000, stall_us: 70_000 };
        assert_eq!(c.exact_trigger().unwrap(), "full 70000 1000000");
        assert!(PressureConfig { window_us: 499_999, ..c }.validate().is_err());
        assert!(PressureConfig { window_us: 10_000_001, ..c }.validate().is_err());
        assert!(PressureConfig { stall_us: 0, ..c }.validate().is_err());
        assert!(PressureConfig { stall_us: 1_000_001, ..c }.validate().is_err());
        assert!(elapsed_valid(1_999_999_999, 1_000_000_000, Some(1_000_000_000)));
        assert!(!elapsed_valid(2_000_000_000, 1_000_000_000, Some(1_000_000_000)));
        assert!(!elapsed_valid(999_999_999, 1_000_000_000, Some(1_000_000_000)));
    }
}
