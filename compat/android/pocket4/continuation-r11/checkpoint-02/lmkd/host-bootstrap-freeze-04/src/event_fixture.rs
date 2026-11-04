// Copyright 2026 Droidloom contributors
// SPDX-License-Identifier: Apache-2.0
//! One explicitly armed owned-host PSI event. No LMKD and no victim selection.
//! The independently persisted Python guard owns admission and cancellation.
use super::*;
use std::collections::BTreeMap;
use std::fs::File;

const MIB: u64 = 1024 * 1024;
const HIGH: u64 = 24 * MIB;
const MAXIMUM: u64 = 64 * MIB;
const ALLOCATION: usize = 32 * 1024 * 1024;
const WINDOW_NS: u64 = 1_000_000_000;
const NS_NAMES: [&str; 10] = ["pid", "pid_for_children", "mnt", "cgroup", "user", "net", "ipc", "uts", "time", "time_for_children"];

fn monotonic() -> TestResult<u64> {
    let mut t: libc::timespec = unsafe { zeroed() };
    checked(unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut t) } == 0 && t.tv_sec >= 0 && (0..1_000_000_000).contains(&t.tv_nsec), "event clock unavailable")?;
    (t.tv_sec as u64).checked_mul(1_000_000_000).and_then(|s| s.checked_add(t.tv_nsec as u64)).ok_or_else(|| "event clock overflow".into())
}
fn input(timeout_ms: i32) -> TestResult<Option<u8>> {
    let mut poll = libc::pollfd { fd: libc::STDIN_FILENO, events: libc::POLLIN, revents: 0 };
    let n = unsafe { libc::poll(&mut poll, 1, timeout_ms) };
    if n < 0 { return Err(io::Error::last_os_error().into()); }
    if n == 0 { return Ok(None); }
    checked(poll.revents & (libc::POLLERR | libc::POLLNVAL) == 0, "owned command channel error")?;
    let mut value = [0u8; 1];
    let count = unsafe { libc::read(libc::STDIN_FILENO, value.as_mut_ptr().cast(), 1) };
    checked(count == 1, "owned command channel closed")?;
    Ok(Some(value[0]))
}
fn verify_target(target: &Path) -> TestResult<()> {
    checked(unsafe { libc::geteuid() } == 0, "event fixture requires owned root job")?;
    let wanted = std::env::var("P4_EVENT_TARGET")?;
    checked(target.as_os_str() == std::ffi::OsStr::new(&wanted), "event target argument differs from lifecycle")?;
    let id = fs::metadata(target)?;
    checked(std::env::var("P4_EVENT_TARGET_ID")? == format!("{}:{}", id.dev(), id.ino()), "owned event target generation changed")?;
    checked(fs::read_to_string(target.join("memory.max"))?.trim() == MAXIMUM.to_string() &&
            fs::read_to_string(target.join("memory.high"))?.trim() == HIGH.to_string() &&
            fs::read_to_string(target.join("memory.swap.max"))?.trim() == "0", "event target budget differs from frozen contract")?;
    Ok(())
}
struct Mapping { address: *mut u8, bytes: usize }
impl Mapping {
    fn new(bytes: usize) -> TestResult<Self> {
        let raw = unsafe { libc::mmap(std::ptr::null_mut(), bytes, libc::PROT_READ | libc::PROT_WRITE, libc::MAP_PRIVATE | libc::MAP_ANONYMOUS, -1, 0) };
        checked(raw != libc::MAP_FAILED, "bounded anonymous mapping failed")?;
        let mapping = Self { address: raw.cast(), bytes };
        checked(unsafe { libc::madvise(raw, bytes, libc::MADV_NOHUGEPAGE) } == 0, "bounded pages require NOHUGEPAGE")?;
        Ok(mapping)
    }
    fn touch(&mut self, offset: usize) { unsafe { std::ptr::write_volatile(self.address.add(offset), 0x5a) }; }
}
impl Drop for Mapping { fn drop(&mut self) { unsafe { libc::munmap(self.address.cast(), self.bytes) }; } }

pub(super) fn workload(target: &Path, role: &str) -> TestResult<()> {
    let started = monotonic()?;
    verify_target(target)?;
    let parent = unsafe { libc::getppid() };
    checked(parent > 1, "owned workload parent absent")?;
    checked(unsafe { libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) } == 0 && unsafe { libc::getppid() } == parent, "owned workload parent generation changed")?;
    // This last-resort lifetime guard is not a successful cooperative exit.
    // A SIGALRM, parent-death signal, forced cancellation, or timeout is FAIL.
    unsafe { libc::alarm(6) };
    checked(fs::read_to_string("/proc/self/cgroup")? == std::env::var("P4_EVENT_CONTROL_MEMBERSHIP")?, "workload did not inherit the exact owned control leaf")?;
    let (score, length) = match role {
        "foreground" => (0, MIB as usize), "protected" => (-1000, MIB as usize),
        "allocator" => (900, ALLOCATION), _ => return Err("unknown owned workload role".into()),
    };
    fs::write(target.join("cgroup.procs"), format!("{}\n", std::process::id()))?;
    fs::write("/proc/self/oom_score_adj", format!("{score}\n"))?;
    checked(fs::read_to_string("/proc/self/oom_score_adj")?.trim() == score.to_string(), "owned score assignment failed")?;
    let mut allocation = Mapping::new(length)?;
    let mut touched = 0usize;
    if role != "allocator" {
        for offset in (0..length).step_by(4096) { allocation.touch(offset); }
        touched = length;
    }
    println!("READY"); io::stdout().flush()?;
    let mut armed_at = None;
    loop {
        match input(if armed_at.is_some() && touched < length { 0 } else { 5 })? {
            Some(b'q') => {
                let stopped = monotonic()?;
                checked(stopped >= started && stopped - started < 6_000_000_000, "owned stop arrived after lifetime limit")?;
                if let Some(armed) = armed_at {
                    checked(stopped >= armed && stopped - armed < 3_000_000_000, "owned stop arrived after pressure phase")?;
                }
                break;
            },
            Some(b'a') if role == "allocator" && armed_at.is_none() => { armed_at = Some(monotonic()?); },
            Some(_) => return Err("invalid owned workload command".into()),
            None => {},
        }
        let now = monotonic()?;
        checked(now >= started && now - started < 6_000_000_000, "owned workload lifetime exhausted")?;
        if let Some(armed) = armed_at {
            checked(now >= armed && now - armed < 3_000_000_000, "allocator phase exceeded three seconds")?;
            // Sixteen base pages per batch, with a command/deadline check
            // between batches. There is no retry, extra allocation or swap.
            let end = (touched + 64 * 1024).min(length);
            while touched < end { allocation.touch(touched); touched += 4096; }
        }
    }
    drop(allocation);
    let completed = monotonic()?;
    checked(completed >= started && completed - started < 6_000_000_000, "owned normal release exceeded lifetime limit")?;
    let pressure_ns = if let Some(armed) = armed_at {
        checked(completed >= armed && completed - armed < 3_000_000_000, "owned normal release exceeded pressure phase")?;
        completed - armed
    } else { 0 };
    unsafe { libc::alarm(0) };
    println!("WORKLOAD_EXIT role={role} bytes_touched={touched} lifetime_ns={} pressure_ns={pressure_ns} cooperative=true", completed - started);
    io::stdout().flush()?;
    Ok(())
}

fn proc_text(dir: &File, name: &str) -> TestResult<String> {
    let name = CString::new(name)?;
    let raw = unsafe { libc::openat(dir.as_raw_fd(), name.as_ptr(), libc::O_RDONLY | libc::O_NOFOLLOW | libc::O_CLOEXEC) };
    if raw < 0 { return Err(io::Error::last_os_error().into()); }
    let file = unsafe { File::from_raw_fd(raw) };
    let mut value = String::new(); file.take(65537).read_to_string(&mut value)?;
    checked(value.len() <= 65536, "owned process metadata bound")?;
    Ok(value)
}
struct Workload {
    child: PeerChild, pin: ProcessPin, proc: File, namespaces: NamespacePins,
    status: Vec<String>, membership: String, score: i32, role: &'static str,
}
impl Workload {
    fn spawn(host: &HostContext, target: &Path, role: &'static str, score: i32) -> TestResult<Self> {
        let mut command = Command::new(std::env::current_exe()?);
        command.arg("--owned-workload").arg(target).arg(role);
        let mut child = PeerChild::spawn_command(command)?;
        let pin = host.pin_owned_child(&mut child.process)?;
        let proc = OpenOptions::new().read(true).custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC).open(format!("/proc/{}", pin.pid()))?;
        let status: Vec<_> = proc_text(&proc, "status")?.lines().filter(|s| s.starts_with("Uid:") || s.starts_with("Gid:") || s.starts_with("NSpid:")).map(str::to_owned).collect();
        checked(status.len() == 3 && status.iter().filter(|s| s.starts_with("Uid:") || s.starts_with("Gid:")).all(|s| s.split_whitespace().skip(1).eq(["0", "0", "0", "0"])), "owned workload credentials differ from fixed root role")?;
        let membership = format!("0::/{}\n", target.strip_prefix("/sys/fs/cgroup")?.display());
        let namespaces = host.pin_self()?.namespace_pins()?;
        let value = Self { child, pin, proc, namespaces, status, membership, score, role };
        value.verify()?;
        Ok(value)
    }
    fn verify(&self) -> TestResult<()> {
        self.pin.live()?;
        checked(proc_text(&self.proc, "cgroup")? == self.membership && proc_text(&self.proc, "oom_score_adj")?.trim() == self.score.to_string(), "owned witness membership or score changed")?;
        let actual: Vec<_> = proc_text(&self.proc, "status")?.lines().filter(|s| s.starts_with("Uid:") || s.starts_with("Gid:") || s.starts_with("NSpid:")).map(str::to_owned).collect();
        checked(actual == self.status, "owned witness credentials/PID view changed")?;
        let namespaces = self.pin.namespace_pins()?;
        checked(NS_NAMES.iter().all(|name| namespaces.identity(name) == self.namespaces.identity(name)), "owned witness namespace changed")?;
        let exe = fs::metadata(format!("/proc/{}/exe", self.pin.pid()))?;
        let expected = fs::metadata(std::env::current_exe()?)?;
        checked(exe.dev() == expected.dev() && exe.ino() == expected.ino(), "owned witness executable changed")?;
        self.pin.live()?;
        Ok(())
    }
    fn finish(&mut self) -> TestResult<()> {
        self.verify()?;
        self.child.finish()?;
        let mut remaining = String::new(); self.child.output.read_to_string(&mut remaining)?;
        checked(remaining.lines().any(|s| s.starts_with(&format!("WORKLOAD_EXIT role={} ", self.role)) && s.ends_with("cooperative=true")), "owned workload lacks normal release receipt")?;
        print!("{remaining}"); io::stdout().flush()?;
        Ok(())
    }
}

#[derive(Clone, Debug)]
struct Stats { current: u64, events: BTreeMap<String, u64>, full_total: u64 }
fn stats(target: &Path) -> TestResult<Stats> {
    let current = fs::read_to_string(target.join("memory.current"))?.trim().parse()?;
    let mut events = BTreeMap::new();
    for line in fs::read_to_string(target.join("memory.events"))?.lines() {
        let fields: Vec<_> = line.split_whitespace().collect();
        checked(fields.len() == 2 && !events.contains_key(fields[0]), "target event counter parse")?;
        events.insert(fields[0].to_owned(), fields[1].parse()?);
    }
    let pressure = fs::read_to_string(target.join("memory.pressure"))?;
    let full: Vec<_> = pressure.lines().filter(|s| s.starts_with("full ")).collect();
    checked(full.len() == 1, "target full pressure counter missing")?;
    let totals: Vec<_> = full[0].split_whitespace().filter_map(|s| s.strip_prefix("total=")).collect();
    checked(totals.len() == 1, "target full total parse")?;
    Ok(Stats { current, events, full_total: totals[0].parse()? })
}
fn resource_guard(now: &Stats, before: &Stats) -> TestResult<()> {
    checked(now.current < 48 * MIB, "owned target reached 48 MiB abort bound")?;
    for name in ["max", "oom", "oom_kill", "oom_group_kill"] {
        checked(now.events.get(name).is_some() && now.events.get(name) == before.events.get(name), "owned target max/OOM counter changed")?;
    }
    checked(now.full_total >= before.full_total, "target pressure accounting rolled back")?;
    Ok(())
}
fn number(bytes: &[u8], at: usize, length: usize) -> u64 {
    let mut value = [0u8; 8]; value[..length].copy_from_slice(&bytes[at..at + length]); u64::from_le_bytes(value)
}
fn validate_frame(packet: &[u8], generation: &[u8; 32], scope: ScopeRequest, now: u64) -> TestResult<u64> {
    checked(packet.len() == 128, "event packet size")?;
    checked(&packet[..8] == b"P4PSI01!" && number(packet, 8, 4) == 1 && number(packet, 12, 4) == 2, "event wire version or real critical level")?;
    checked(&packet[16..48] == generation && generation != &[0; 32], "event lease generation")?;
    checked(number(packet, 48, 8) == scope.cgroup.device && number(packet, 56, 8) == scope.cgroup.inode && packet[64..96] == scope.budget, "event scope or budget")?;
    checked(number(packet, 96, 8) == 1_000_000 && number(packet, 104, 8) == 70_000 && number(packet, 112, 8) == 1, "event exact thresholds/first sequence")?;
    let observed = number(packet, 120, 8);
    checked(observed != 0 && now >= observed && now - observed < WINDOW_NS, "event future/expired observation")?;
    Ok(observed)
}
fn validate_correlation(now: &Stats, before: &Stats) -> TestResult<()> {
    resource_guard(now, before)?;
    checked(now.current > HIGH && now.events.get("high").zip(before.events.get("high")).is_some_and(|(a, b)| a > b) && now.full_total > before.full_total, "actual event lacks current target pressure evidence")
}
fn take_packet(fd: &OwnedFd) -> TestResult<Option<[u8; 128]>> {
    let mut p = libc::pollfd { fd: fd.as_raw_fd(), events: libc::POLLIN | libc::POLLRDHUP, revents: 0 };
    checked(unsafe { libc::poll(&mut p, 1, 0) } >= 0, "event recipient poll failed")?;
    checked(p.revents & (libc::POLLERR | libc::POLLHUP | libc::POLLRDHUP | libc::POLLNVAL) == 0, "event capability revoked")?;
    if p.revents & libc::POLLIN == 0 { return Ok(None); }
    let mut packet = [0u8; 128];
    let n = unsafe { libc::recv(fd.as_raw_fd(), packet.as_mut_ptr().cast(), packet.len(), libc::MSG_DONTWAIT | libc::MSG_TRUNC) };
    checked(n == 128, "event notification truncated or unavailable")?;
    Ok(Some(packet))
}

pub(super) fn run(target: &Path) -> TestResult<()> {
    verify_target(target)?;
    let host = Arc::new(HostContext::open()?);
    checked(fs::read_to_string("/proc/self/cgroup")? == std::env::var("P4_EVENT_CONTROL_MEMBERSHIP")?, "event owner left its control leaf")?;
    let baseline_fds = fd_count()?;
    let tmp = std::env::temp_dir().join(format!("p4-psi-event-{}", std::process::id()));
    fs::create_dir(&tmp)?; fs::set_permissions(&tmp, fs::Permissions::from_mode(0o700))?;
    let path = tmp.join("enroll.sock");
    let result = (|| -> TestResult<()> {
        let listener = Listener::bind(&path)?;
        let mut peer = PeerChild::spawn_psi(&path, target)?;
        let mut foreground = Workload::spawn(&host, target, "foreground", 0)?;
        let mut protected = Workload::spawn(&host, target, "protected", -1000)?;
        let root = OpenOptions::new().read(true).custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC).open(target)?;
        let authority = Arc::new(authority_with_root(&host, &mut peer, 0, 0, false, false, root)?);
        let verified = host.authenticate(accept(&listener)?, &authority)?;
        let scope = authority.scope_request();
        let config = PressureConfig { level: PressureLevel::Critical, window_us: 1_000_000, stall_us: 70_000 };
        let mut lease = LeaseOwner::register(verified, Arc::clone(&host), Arc::clone(&authority), scope, &[config])?;
        let alias = duplicate(&lease.recipients[0])?;
        let generation = lease.owner.generation();
        let mut allocator = Workload::spawn(&host, target, "allocator", 900)?;
        let trial = (|| -> TestResult<()> {
            let before = stats(target)?;
            checked(before.current <= 8 * MIB && pressure_fd_count(target)? == 1, "event target not quiet or monitor count differs")?;
            foreground.verify()?; protected.verify()?; allocator.verify()?;
            let d = lease.owner.diagnostics();
            checked(!lease.owner.is_retired() && d.observations == 0 && d.packets_queued == 0 && d.stop_reason == 0 && take_packet(&lease.recipients[0])?.is_none(), "event registration not initially quiet")?;
            println!("EVENT_READY current={} high={} max={} full_total={} high_events={}", before.current, HIGH, MAXIMUM, before.full_total, before.events.get("high").ok_or("missing high counter")?);
            io::stdout().flush()?;
            let until = Instant::now() + Duration::from_secs(1);
            loop {
                match input(10)? { Some(b'a') => break, Some(_) => return Err("event not armed or cancelled by health owner".into()), None => {} }
                checked(Instant::now() < until, "health owner did not arm within one second")?;
            }
            verify_target(target)?; authority.validate()?;
            foreground.verify()?; protected.verify()?; allocator.verify()?;
            let started = monotonic()?;
            allocator.child.command(b'a')?;
            println!("EVENT_ARMED monotonic_ns={started}"); io::stdout().flush()?;
            loop {
                if input(0)?.is_some() { return Err("pressure owner cancelled the one event trial".into()); }
                let now = monotonic()?;
                checked(now >= started && now - started < 3_000_000_000, "no qualifying event within three seconds")?;
                foreground.verify()?; protected.verify()?; allocator.verify()?;
                // The Python owner persists periodic target/Main health before
                // threshold judgment. This loop only checks owned identity
                // and the notification; it does not create unsaved health
                // decisions between the authoritative health frames.
                if let Some(packet) = take_packet(&lease.recipients[0])? {
                    let received = monotonic()?;
                    let observed = validate_frame(&packet, &generation, scope, received)?;
                    let at_event = stats(target)?;
                    foreground.verify()?; protected.verify()?; allocator.verify()?;
                    checked(!endpoint_hup(&lease.recipients[0])? && !lease.owner.is_retired(), "event retired during final observation")?;
                    let completed = monotonic()?;
                    // Persist this full numeric decision input through the
                    // parent's flushed stdout journal before calling it PASS.
                    println!("EVENT_SAMPLE {{\"observed_monotonic_ns\":{observed},\"received_monotonic_ns\":{received},\"completed_monotonic_ns\":{completed},\"current\":{},\"high\":{HIGH},\"full_total_before\":{},\"full_total_after\":{},\"high_before\":{},\"high_after\":{},\"max\":{},\"oom\":{},\"oom_kill\":{},\"oom_group_kill\":{},\"foreground_live\":true,\"protected_live\":true,\"allocator_live\":true,\"first_sequence\":1,\"critical_window_us\":1000000,\"critical_stall_us\":70000}}", at_event.current, before.full_total, at_event.full_total, before.events["high"], at_event.events["high"], at_event.events["max"], at_event.events["oom"], at_event.events["oom_kill"], at_event.events["oom_group_kill"]);
                    io::stdout().flush()?;
                    validate_frame(&packet, &generation, scope, completed)?;
                    validate_correlation(&at_event, &before)?;
                    let d = lease.owner.diagnostics();
                    checked(d.observations >= 1 && d.packets_queued >= 1 && d.stop_reason == 0, "worker event diagnostic mismatch")?;
                    break;
                }
                std::thread::sleep(Duration::from_millis(5));
            }
            Ok(())
        })();
        // Cancellation and normal completion follow the same owned cleanup.
        // Any failed cleanup retains FAIL even if a valid event was observed.
        let allocator_done = allocator.finish();
        let witnesses_alive = foreground.verify().and_then(|_| protected.verify());
        lease.owner.retire();
        let worker_done = lease.owner.finish_retirement(Duration::from_secs(2));
        let aliases_done = endpoint_hup(&lease.recipients[0]).and_then(|a| checked(a && endpoint_hup(&alias)?, "event aliases did not revoke"));
        let monitors_closed = pressure_fd_count(target).and_then(|n| checked(n == 0, "event pressure fd remained"));
        let foreground_done = foreground.finish(); let protected_done = protected.finish(); let peer_done = peer.finish();
        println!("EVENT_CLEANUP allocator_normal={} witnesses_live_before_stop={} worker_joined={} aliases_hup={} monitors_closed={} foreground_normal={} protected_normal={} peer_normal={}", allocator_done.is_ok(), witnesses_alive.is_ok(), matches!(worker_done.as_ref(), Ok(true)), aliases_done.is_ok(), monitors_closed.is_ok(), foreground_done.is_ok(), protected_done.is_ok(), peer_done.is_ok());
        io::stdout().flush()?;
        allocator_done?; witnesses_alive?; checked(worker_done? , "event worker join incomplete")?; aliases_done?; monitors_closed?; foreground_done?; protected_done?; peer_done?;
        trial
    })();
    let fd_clean = checked(fd_count()? == baseline_fds && pressure_fd_count(target)? == 0, "event descriptors leaked");
    let socket_clean = checked(!path.exists(), "event listener socket remained");
    let directory_clean = fs::remove_dir(&tmp);
    fd_clean?; socket_clean?; directory_clean?; result?;
    emit("one genuine owned-cgroup PSI event, exact packet and current statistics, both witnesses survived, normal allocation release, complete retirement");
    println!("RESULT PASS mode=owned-host-real-psi-event-only no_android=true no_lmkd_killgate=true");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn packet() -> ([u8; 128], ScopeRequest) {
        let scope = ScopeRequest { cgroup: FileId { device: 13, inode: 17 }, budget: [29; 32], authority_generation: [41; 32] };
        let mut p = [0; 128]; p[..8].copy_from_slice(b"P4PSI01!"); p[8..12].copy_from_slice(&1u32.to_le_bytes()); p[12..16].copy_from_slice(&2u32.to_le_bytes()); p[16..48].fill(31);
        for (at, value) in [(48, 13u64), (56, 17), (96, 1_000_000), (104, 70_000), (112, 1), (120, 2_000_000_000)] { p[at..at + 8].copy_from_slice(&value.to_le_bytes()); }
        p[64..96].copy_from_slice(&scope.budget); (p, scope)
    }
    #[test]
    fn event_gate_rejects_wrong_generation_scope_threshold_sequence_future_and_exact_expiry() {
        let (p, scope) = packet(); assert!(validate_frame(&p, &[31; 32], scope, 2_000_000_001).is_ok());
        for offset in [0usize, 8, 12, 16, 48, 56, 64, 96, 104, 112] { let mut bad = p; bad[offset] ^= 1; assert!(validate_frame(&bad, &[31; 32], scope, 2_000_000_001).is_err(), "offset {offset}"); }
        assert!(validate_frame(&p, &[31; 32], scope, 1_999_999_999).is_err());
        assert!(validate_frame(&p, &[31; 32], scope, 3_000_000_000).is_err());
        assert!(validate_frame(&p[..127], &[31; 32], scope, 2_000_000_001).is_err());
    }
    #[test]
    fn notification_alone_or_historical_high_cannot_certify_real_target_pressure() {
        let before = Stats { current: MIB, events: [("high", 3), ("max", 0), ("oom", 0), ("oom_kill", 0), ("oom_group_kill", 0)].into_iter().map(|(k, v)| (k.to_owned(), v)).collect(), full_total: 100 };
        let mut now = before.clone(); now.current = HIGH + MIB; now.events.insert("high".into(), 4); now.full_total += 1;
        assert!(validate_correlation(&now, &before).is_ok());
        for kind in 0..5 { let mut bad = now.clone(); match kind { 0 => bad.current = HIGH, 1 => { bad.events.insert("high".into(), 3); }, 2 => bad.full_total = 100, 3 => { bad.events.insert("oom_kill".into(), 1); }, _ => bad.current = 48 * MIB }; assert!(validate_correlation(&bad, &before).is_err()); }
    }
}
