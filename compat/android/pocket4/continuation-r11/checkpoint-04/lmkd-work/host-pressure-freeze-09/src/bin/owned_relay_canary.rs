// Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
//! Owned real-broker bootstrap/protocol/pressure/stale canary. No installation,
//! Main process discovery, automatic retry, or global cleanup is implemented.
#![deny(unsafe_op_in_unsafe_fn)]
use droidloom_pressure_relay_owner_candidate::*;
use std::collections::BTreeMap;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Write};
use std::mem::{size_of, zeroed};
use std::os::fd::{AsRawFd, BorrowedFd, FromRawFd, OwnedFd, RawFd};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};

type Check<T> = std::result::Result<T, Box<dyn std::error::Error>>;
const LMKD_SHA: &str = "bd794b7b59d1047523cea6174bcd230c75aa2eececd1900b23f3f33a86061dde";
const NS: [&str; 6] = ["pid", "mnt", "cgroup", "ipc", "uts", "net"];
const LIBRARIES: &str = include_str!("../../owned-relay/minimal-root-libraries.tsv");
fn require(value: bool, text: &'static str) -> Check<()> { if value { Ok(()) } else { Err(text.into()) } }
fn open(path: &Path, directory: bool) -> Check<File> {
    Ok(OpenOptions::new().read(true).custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC |
        if directory { libc::O_DIRECTORY } else { 0 }).open(path)?)
}
fn pin(value: &str) -> Check<[u8; 32]> {
    require(value.len() == 64 && value.bytes().all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c)), "canonical SHA/nonce required")?;
    let mut out = [0; 32];
    for (index, byte) in out.iter_mut().enumerate() { *byte = u8::from_str_radix(&value[2 * index..2 * index + 2], 16)?; }
    Ok(out)
}
fn hex(value: &[u8]) -> String { value.iter().map(|byte| format!("{byte:02x}")).collect() }
fn save(state: &Path, name: &str, data: &str) -> Check<()> {
    let mut file = OpenOptions::new().write(true).create_new(true).mode(0o600)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW).open(state.join("evidence").join(name))?;
    file.write_all(data.as_bytes())?; file.write_all(b"\n")?; file.sync_all()?; Ok(())
}
fn status_record(state: &Path, name: &str, status: &BootstrapStatus) -> Check<()> {
    save(state, name, &format!("{{\"state\":\"{:?}\",\"nonce\":\"{}\",\"generation\":\"{}\",\"endpoint_device\":{},\"endpoint_inode\":{},\"cgroup_device\":{},\"cgroup_inode\":{},\"budget_hex\":\"{}\",\"granted\":{},\"faulted\":{}}}",
        status.state, hex(&status.nonce), hex(&status.generation), status.endpoint.device, status.endpoint.inode,
        status.cgroup.device, status.cgroup.inode, hex(&status.budget), status.granted, status.faulted))
}
fn kernel_counters(text: &str) -> Check<BTreeMap<String, u64>> {
    let mut counters = BTreeMap::new();
    for line in text.lines() {
        let fields: Vec<_> = line.split_whitespace().collect();
        require(fields.len() == 2 && !fields[0].is_empty() &&
            fields[0].bytes().all(|c| c.is_ascii_lowercase() || c == b'_') &&
            !fields[1].is_empty() && fields[1].bytes().all(|c| c.is_ascii_digit()),
            "bounded kernel counter row")?;
        require(counters.insert(fields[0].to_owned(), fields[1].parse()?).is_none(),
            "duplicate kernel counter")?;
    }
    Ok(counters)
}
fn counters_json(counters: &BTreeMap<String, u64>) -> String {
    format!("{{{}}}", counters.iter().map(|(key, value)| format!("\"{key}\":{value}"))
        .collect::<Vec<_>>().join(","))
}
fn process_list(path: &Path) -> Check<Vec<u32>> {
    fs::read_to_string(path)?.split_whitespace().map(|value| {
        let pid: u32 = value.parse()?;
        require(pid > 0, "positive owned cgroup member PID")?;
        Ok(pid)
    }).collect()
}
fn outer_retirement_record(state: &Path, cgroup: &Path, unit: &str, phase: &str,
                           nonce: &[u8; 32], domain: &File) -> Check<()> {
    // This runs only after the broker, owner and init are joined/reaped. The
    // driver still occupies host/, so systemd cannot remove the empty outer
    // cgroup before its final resource counters have been retained.
    let held = open(cgroup, true)?;
    let path = PathBuf::from(format!("/proc/self/fd/{}", held.as_raw_fd()));
    let identity = held.metadata()?;
    let domain_identity = domain.metadata()?;
    let pid = unsafe { libc::getpid() } as u32;
    let membership = format!("0::/system.slice/{unit}/host\n");
    require(fs::read_to_string("/proc/self/cgroup")? == membership,
        "retiring driver must remain in its exact owned host subgroup")?;
    let root_members = process_list(&path.join("cgroup.procs"))?;
    let host_members = process_list(&path.join("host/cgroup.procs"))?;
    require(root_members.is_empty() && host_members == [pid],
        "only the exact retiring driver may remain outside the empty domain")?;
    let scoped = PathBuf::from(format!("/proc/self/fd/{}", domain.as_raw_fd()));
    let domain_events = kernel_counters(&fs::read_to_string(scoped.join("cgroup.events"))?)?;
    let cgroup_events = kernel_counters(&fs::read_to_string(path.join("cgroup.events"))?)?;
    require(domain_events.get("populated") == Some(&0) && domain_events.get("frozen") == Some(&0) &&
        cgroup_events.get("populated") == Some(&1) && cgroup_events.get("frozen") == Some(&0),
        "joined domain and live retiring driver state")?;
    let mut limits = Vec::new();
    for (name, expected) in [("memory.max", "536870912"), ("memory.high", "max"),
        ("memory.swap.max", "0"), ("pids.max", "64"), ("cpu.max", "100000 100000")] {
        require(fs::read_to_string(path.join(name))?.trim() == expected,
            "outer budget changed before joined retirement")?;
        limits.push(format!("\"{name}\":\"{expected}\""));
    }
    let events = kernel_counters(&fs::read_to_string(path.join("memory.events"))?)?;
    for name in ["max", "oom", "oom_kill", "oom_group_kill"] {
        require(events.get(name) == Some(&0), "outer memory max/OOM counter is nonzero")?;
    }
    let number = |name: &str| -> Check<u64> { Ok(fs::read_to_string(path.join(name))?.trim().parse()?) };
    let current = number("memory.current")?;
    let peak = number("memory.peak")?;
    let pids_current = number("pids.current")?;
    let swap_current = number("memory.swap.current")?;
    let swap_peak = number("memory.swap.peak")?;
    require(current <= peak && peak < 536870912 && swap_current == 0 && swap_peak == 0,
        "outer final peak/current/swap exceeds fixed admission bounds")?;
    require(pids_current == 1,
        "only the single-threaded exact driver may remain across every outer descendant")?;
    let mut now: libc::timespec = unsafe { zeroed() };
    require(unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut now) } == 0 &&
        now.tv_sec >= 0 && now.tv_nsec >= 0 && now.tv_nsec < 1_000_000_000,
        "actual monotonic outer retirement observation")?;
    let observed_ns = (now.tv_sec as u64).checked_mul(1_000_000_000)
        .and_then(|seconds| seconds.checked_add(now.tv_nsec as u64)).ok_or("monotonic overflow")?;
    save(state, "outer-final.json", &format!(concat!(
        "{{\"schema\":1,\"source\":\"owned-driver-after-all-child-retirement-before-exit\",",
        "\"unit\":\"{}\",\"phase\":\"{}\",\"nonce\":\"{}\",\"driver_pid\":{},",
        "\"cgroup_device\":{},\"cgroup_inode\":{},\"domain_device\":{},\"domain_inode\":{},",
        "\"observed_monotonic_ns\":{},\"limits\":{{{}}},\"memory_events\":{},",
        "\"memory_current\":{},\"memory_peak\":{},\"pids_current\":{},\"swap_current\":{},\"swap_peak\":{},",
        "\"root_members\":[],\"host_members\":[{}],\"cgroup_events\":{},\"domain_events\":{}}}"),
        unit, phase, hex(nonce), pid, identity.dev(), identity.ino(), domain_identity.dev(), domain_identity.ino(),
        observed_ns, limits.join(","), counters_json(&events), current, peak, pids_current, swap_current, swap_peak,
        pid, counters_json(&cgroup_events), counters_json(&domain_events)))
}
fn private_directory(path: &Path, mode: u32) -> Check<()> {
    let m = fs::symlink_metadata(path)?;
    require(m.is_dir() && m.uid() == 0 && m.gid() == 0 && m.mode() & 0o777 == mode, "exact private directory ownership/mode")
}
fn wait_packet(fd: RawFd, timeout: Duration) -> Check<()> {
    let deadline = Instant::now() + timeout;
    loop {
        require(Instant::now() < deadline, "owned actor control deadline")?;
        let mut p = libc::pollfd { fd, events: libc::POLLIN | libc::POLLRDHUP, revents: 0 };
        if unsafe { libc::poll(&mut p, 1, 100) } < 0 {
            if io::Error::last_os_error().kind() == io::ErrorKind::Interrupted { continue; }
            return Err(io::Error::last_os_error().into());
        }
        require(p.revents & (libc::POLLERR | libc::POLLHUP | libc::POLLRDHUP | libc::POLLNVAL) == 0,
            "owned actor control failed")?;
        if p.revents & libc::POLLIN != 0 { return Ok(()); }
    }
}
fn send_byte(fd: RawFd, byte: u8) -> Check<()> {
    require(unsafe { libc::send(fd, (&byte as *const u8).cast(), 1, libc::MSG_NOSIGNAL | libc::MSG_DONTWAIT) } == 1,
        "owned actor command send")
}
fn receive_byte(fd: RawFd, expected: u8) -> Check<()> {
    let mut byte = 0u8; let mut ancillary = [0 as libc::c_long; 64];
    let mut iov = libc::iovec { iov_base: (&mut byte as *mut u8).cast(), iov_len: 1 };
    let mut message: libc::msghdr = unsafe { zeroed() };
    message.msg_iov = &mut iov; message.msg_iovlen = 1;
    message.msg_control = ancillary.as_mut_ptr().cast(); message.msg_controllen = std::mem::size_of_val(&ancillary);
    let got = unsafe { libc::recvmsg(fd, &mut message, libc::MSG_CMSG_CLOEXEC | libc::MSG_TRUNC | libc::MSG_DONTWAIT) };
    let mut extra = false;
    if got >= 0 {
        let mut header = unsafe { libc::CMSG_FIRSTHDR(&message) };
        while !header.is_null() {
            extra = true; let h = unsafe { &*header }; let base = unsafe { libc::CMSG_LEN(0) } as usize;
            if h.cmsg_level == libc::SOL_SOCKET && h.cmsg_type == libc::SCM_RIGHTS && h.cmsg_len >= base {
                for index in 0..(h.cmsg_len - base) / size_of::<RawFd>() {
                    let raw = unsafe { std::ptr::read_unaligned(libc::CMSG_DATA(header).add(index * size_of::<RawFd>()).cast::<RawFd>()) };
                    unsafe { libc::close(raw) };
                }
            }
            header = unsafe { libc::CMSG_NXTHDR(&message, header) };
        }
    }
    require(got == 1 && byte == expected && !extra && message.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) == 0,
        "owned actor reply/ancillary mismatch")
}
fn pidfd_pid(fd: RawFd) -> Check<u32> {
    require(unsafe { libc::syscall(libc::SYS_pidfd_send_signal, fd, 0, std::ptr::null::<libc::siginfo_t>(), 0) } == 0,
        "actual live owned pidfd required")?;
    let text = fs::read_to_string(format!("/proc/self/fdinfo/{fd}"))?;
    let values: Vec<_> = text.lines().filter_map(|line| line.strip_prefix("Pid:")).collect();
    require(values.len() == 1, "unique kernel pidfd PID")?;
    let pid = values[0].trim().parse::<u32>()?; require(pid > 0, "live kernel pidfd PID")?; Ok(pid)
}
fn pidfd_dead(fd: RawFd) -> Check<bool> {
    let mut p = libc::pollfd { fd, events: libc::POLLIN, revents: 0 };
    require(unsafe { libc::poll(&mut p, 1, 0) } >= 0 && p.revents & (libc::POLLERR | libc::POLLNVAL) == 0,
        "owned pidfd exit poll")?;
    Ok(p.revents & libc::POLLIN != 0)
}
fn write_limit(path: &Path, content: &str) -> Check<()> {
    let mut file = OpenOptions::new().write(true).custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC).open(path)?;
    file.write_all(content.as_bytes())?; Ok(())
}
fn spawn_actor(file: &File, child_fd: RawFd, args: &[String]) -> Check<Child> {
    let raw = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_DUPFD_CLOEXEC, 64) };
    require(raw >= 0, "pin exact owned actor executable")?;
    let executable = unsafe { OwnedFd::from_raw_fd(raw) };
    let parent = unsafe { libc::getpid() };
    let mut command = Command::new(format!("/proc/self/fd/{}", executable.as_raw_fd()));
    command.args(args).stdin(Stdio::null());
    unsafe {
        command.pre_exec(move || {
            if child_fd != 3 && libc::dup2(child_fd, 3) < 0 { return Err(io::Error::last_os_error()); }
            if libc::fcntl(3, libc::F_SETFD, 0) < 0 || libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) < 0 {
                return Err(io::Error::last_os_error());
            }
            if libc::getppid() != parent { return Err(io::Error::other("owned actor parent changed")); }
            Ok(())
        });
    }
    Ok(command.spawn()?)
}
fn fresh_dir(path: &Path, mode: u32) -> Check<()> {
    fs::create_dir(path)?; fs::set_permissions(path, fs::Permissions::from_mode(mode))?;
    private_directory(path, mode)
}
fn stage_file(root: &Path, source: &Path, relative: &str, expected: [u8; 32], mode: u32) -> Check<()> {
    require(source.is_absolute() && fs::canonicalize(source)? == source, "staging source must be a canonical pinned regular path")?;
    require(!relative.starts_with('/') && !relative.split('/').any(|p| p == ".." || p.is_empty()), "fixed staging relative destination")?;
    let mut input = open(source, false)?; let before = input.metadata()?;
    require(before.is_file() && before.len() > 0 && before.len() <= 64 * 1024 * 1024, "bounded regular staging input")?;
    require(ExecutablePin::hash_file_for_receipt(&input)? == expected, "staging input hash differs from frozen receipt")?;
    let destination = root.join(relative);
    let mut output = OpenOptions::new().read(true).write(true).create_new(true).mode(0o600)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW).open(&destination)?;
    require(io::copy(&mut input, &mut output)? == before.len(), "staging input length changed")?;
    output.sync_all()?;
    require(ExecutablePin::hash_file_for_receipt(&output)? == expected, "copied staging bytes mismatch")?;
    let after = input.metadata()?;
    require((before.dev(),before.ino(),before.len(),before.mtime(),before.mtime_nsec(),before.ctime(),before.ctime_nsec()) ==
        (after.dev(),after.ino(),after.len(),after.mtime(),after.mtime_nsec(),after.ctime(),after.ctime_nsec()), "staging input generation changed")?;
    output.set_permissions(fs::Permissions::from_mode(mode))?; Ok(())
}
fn prepare(args: &[String]) -> Check<()> {
    require(args.len() == 9, "usage: owned-relay-canary prepare ROOT STATE UNIT ACTOR_PATH ACTOR_SHA LMKD_PATH LMKD_SHA")?;
    require(unsafe { libc::geteuid() } == 0 && unsafe { libc::getegid() } == 0, "owned fresh staging requires root")?;
    let root = PathBuf::from(&args[2]); let state = PathBuf::from(&args[3]); let unit = &args[4];
    require(unit.starts_with("p4-lmkd-relay-") && unit.ends_with(".service") &&
        unit.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'-' || c == b'.') && !unit.contains(".."), "exact fresh canary unit name")?;
    let stem = unit.strip_suffix(".service").expect("checked suffix");
    require(root == Path::new(&format!("/opt/{stem}/root")) && state == Path::new(&format!("/run/{stem}")), "fresh owned staging paths")?;
    require(args[7] == "/home/alex/work/pocket4-lmkd-enrollment-r6-android-build-01/link/lmkd-cgroup" && args[8] == LMKD_SHA,
        "only actual matching r6 build path/hash may be staged")?;
    let actor_hash = pin(&args[6])?; let lmkd_hash = pin(&args[8])?;
    for (path, executable) in [(Path::new("/opt"), true),(Path::new("/run"), false)] {
        let m = fs::symlink_metadata(path)?;
        require(m.is_dir() && m.uid() == 0 && m.gid() == 0 && m.mode() & 0o022 == 0, "root-owned staging parents")?;
        let file = open(path, true)?; let mut v: libc::statvfs = unsafe { zeroed() };
        require(unsafe { libc::fstatvfs(file.as_raw_fd(), &mut v) } == 0, "staging filesystem flags")?;
        require(v.f_flag & libc::ST_RDONLY == 0 && ((v.f_flag & libc::ST_NOEXEC == 0) == executable), "executable payload/noexec state boundary")?;
    }
    require(!root.parent().expect("fixed root parent").try_exists()? && !state.try_exists()?, "fresh staging directories only; no reuse or overwrite")?;
    fresh_dir(root.parent().expect("fixed root parent"), 0o755)?;
    fresh_dir(&root, 0o755)?; fresh_dir(&state, 0o700)?;
    for path in ["evidence", "relay"] { fresh_dir(&state.join(path), 0o700)?; }
    fresh_dir(&state.join("socket"), 0o755)?;
    for path in ["system", "system/bin", "system/lib64", "proc", "sys", "sys/fs", "sys/fs/cgroup", "dev", "dev/socket"] {
        fresh_dir(&root.join(path), 0o755)?;
    }
    fresh_dir(&root.join("evidence"), 0o700)?;
    let rows: Vec<_> = LIBRARIES.lines().map(|line| line.split('\t').collect::<Vec<_>>()).collect();
    require(rows.len() == 15 && rows.iter().all(|row| row.len() == 4), "frozen minimal-root library table")?;
    for row in rows {
        let mode = u32::from_str_radix(row[1], 8)?;
        require(mode == 0o444 || mode == 0o555, "frozen minimal-root library mode")?;
        stage_file(&root, Path::new(row[2]), row[3], pin(row[0])?, mode)?;
    }
    stage_file(&root, Path::new(&args[5]), "fixture-init", actor_hash, 0o555)?;
    stage_file(&root, Path::new(&args[7]), "system/bin/lmkd", lmkd_hash, 0o555)?;
    let null = std::ffi::CString::new(root.join("dev/null").as_os_str().as_encoded_bytes())?;
    require(unsafe { libc::mknod(null.as_ptr(), libc::S_IFCHR | 0o666, libc::makedev(1,3)) } == 0, "owned fixture dev/null")?;
    fs::set_permissions(root.join("dev/null"), fs::Permissions::from_mode(0o666))?;
    save(&state, "staging-result.json", &format!("{{\"ok\":true,\"actor_sha256\":\"{}\",\"lmkd_sha256\":\"{}\",\"pinned_library_files\":15,\"all_source_and_copied_hashes_matched\":true,\"processes_started\":false,\"namespaces_created\":false,\"pressure\":false}}",hex(&actor_hash),hex(&lmkd_hash)))?;
    println!("{{\"ok\":true,\"prepared\":true,\"processes_started\":false}}");
    Ok(())
}
fn run(args: &[String]) -> Check<()> {
    require(args.len() == 15, "usage: owned-relay-canary bootstrap|protocol|pressure|stale ROOT STATE UNIT ACTOR_SHA LMKD_SHA BROKER_PATH BROKER_SHA SIX_MAIN_NAMESPACE_INODES")?;
    let phase = &args[1];
    require(matches!(phase.as_str(), "bootstrap" | "protocol" | "pressure" | "stale"), "only fixed owned relay phases")?;
    let android = phase != "bootstrap";
    let pressure = phase == "pressure" || phase == "stale";
    let root = PathBuf::from(&args[2]); let state = PathBuf::from(&args[3]); let unit = &args[4];
    require(unsafe { libc::geteuid() } == 0 && unsafe { libc::getegid() } == 0, "owned bootstrap needs lifecycle root")?;
    require(unit.starts_with("p4-lmkd-relay-") && unit.ends_with(".service") &&
        unit.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'-' || c == b'.') && !unit.contains(".."), "exact owned canary unit name")?;
    let stem = unit.strip_suffix(".service").expect("checked suffix");
    require(root == Path::new(&format!("/opt/{stem}/root")) && state == Path::new(&format!("/run/{stem}")), "exact canary staging roots")?;
    private_directory(&state, 0o700)?; private_directory(&state.join("evidence"), 0o700)?;
    private_directory(&state.join("relay"), 0o700)?;
    require(args[6] == LMKD_SHA, "only matching frozen Android r6 binary is accepted")?;
    let actor_hash = pin(&args[5])?; let lmkd_hash = pin(&args[6])?; let broker_hash = pin(&args[8])?;
    let actor_file = open(&root.join("fixture-init"), false)?;
    require(ExecutablePin::hash_file_for_receipt(&actor_file)? == actor_hash, "owned actor source/build hash changed")?;
    let lmkd_file = open(&root.join("system/bin/lmkd"), false)?;
    require(ExecutablePin::hash_file_for_receipt(&lmkd_file)? == lmkd_hash, "matching Android LMKD bytes changed")?;
    let broker_path = PathBuf::from(&args[7]);
    let broker_executable = ExecutablePin::from_lifecycle(open(&broker_path, false)?, broker_hash)?;
    let main_namespaces: Vec<u64> = args[9..15].iter().map(|s| s.parse()).collect::<std::result::Result<_, _>>()?;
    require(main_namespaces.iter().all(|id| *id > 0), "Main namespace fence required")?;
    for name in NS {
        let own = fs::metadata(format!("/proc/self/ns/{name}"))?;
        let initial = fs::metadata(format!("/proc/1/ns/{name}"))?;
        require(own.dev() == initial.dev() && own.ino() == initial.ino(),
            "driver must stay in initial host namespaces")?;
    }
    let membership = format!("0::/system.slice/{unit}\n");
    require(fs::read_to_string("/proc/self/cgroup")? == membership, "driver must own the exact private unit root")?;
    let cgroup = PathBuf::from(format!("/sys/fs/cgroup/system.slice/{unit}"));
    for (name, expected) in [("memory.max", "536870912\n"), ("memory.high", "max\n"),
        ("memory.swap.max", "0\n"), ("pids.max", "64\n"), ("cpu.max", "100000 100000\n")] {
        require(fs::read_to_string(cgroup.join(name))? == expected, "fixed owned systemd budget/quota mismatch")?;
    }
    require(unsafe { libc::getpriority(libc::PRIO_PROCESS, 0) } >= 5, "owned canary requires nice >=5")?;
    let host = HostContext::open()?;
    let mut nonce = [0u8; 32];
    require(unsafe { libc::getrandom(nonce.as_mut_ptr().cast(), nonce.len(), 0) } == nonce.len() as isize && nonce != [0; 32], "fresh lifecycle nonce")?;
    let spec = BootstrapSpec { nonce, uid: 1069, gid: 1069, lmkd_sha256: lmkd_hash, init_sha256: actor_hash };
    let mut pair = [-1; 2];
    require(unsafe { libc::socketpair(libc::AF_UNIX, libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
        0, pair.as_mut_ptr()) } == 0, "owned actor bootstrap socketpair")?;
    let parent_channel = unsafe { OwnedFd::from_raw_fd(pair[0]) };
    let actor_channel = unsafe { OwnedFd::from_raw_fd(pair[1]) };
    let mut actor_args = vec![args[2].clone(), args[3].clone(), phase.clone(), unit.clone(), hex(&nonce)];
    actor_args.extend(args[9..15].iter().cloned()); actor_args.extend([args[6].clone(), args[5].clone()]);
    // The actor starts in the unit root and waits at H. Move only this driver
    // to its fresh host-control subgroup before allowing the actor to empty
    // the root, enable controllers and configure its independent domain.
    let mut actor = spawn_actor(&actor_file, actor_channel.as_raw_fd(), &actor_args)?;
    drop(actor_channel);
    let actor_pin = host.pin_owned_child(&mut actor)?;
    fs::create_dir(cgroup.join("host"))?;
    write_limit(&cgroup.join("host/cgroup.procs"), &unsafe { libc::getpid() }.to_string())?;
    send_byte(parent_channel.as_raw_fd(), b'H')?;
    wait_packet(parent_channel.as_raw_fd(), Duration::from_secs(15))?;
    let handles = spec.receive_from_owned_child(unsafe { BorrowedFd::borrow_raw(parent_channel.as_raw_fd()) }, Duration::from_secs(2))?;
    actor_pin.live()?;
    require(pidfd_pid(handles[1].as_raw_fd())? == actor.id(), "exported owner differs from exact held actor Child")?;
    let init_pid = pidfd_pid(handles[2].as_raw_fd())?;
    let scope = File::from(handles[0].try_clone()?);
    let scope_meta = scope.metadata()?;
    let borrowed: [BorrowedFd<'_>; 16] = std::array::from_fn(|index| unsafe { BorrowedFd::borrow_raw(handles[index].as_raw_fd()) });
    let mut broker = LifecycleBroker::spawn(broker_executable, spec.clone(), &borrowed)?;
    let ready = broker.initialize()?.clone();
    require(ready.cgroup.device == scope_meta.dev() && ready.cgroup.inode == scope_meta.ino(), "READY scope equals exact exported cell FD")?;
    status_record(&state, "broker-ready.json", &ready)?;
    ready.permit_projection(unsafe { BorrowedFd::borrow_raw(parent_channel.as_raw_fd()) }, Duration::from_secs(1))?;
    if android {
        let active = broker.receive_progress(Duration::from_secs(2))?.clone();
        require(active.state == BootstrapState::Active && active.granted && !active.faulted, "actual Android authenticated grant required")?;
        status_record(&state, "broker-active.json", &active)?;
    }
    wait_packet(parent_channel.as_raw_fd(), Duration::from_secs(if pressure { 35 } else { 20 }))?;
    receive_byte(parent_channel.as_raw_fd(), b'D')?;
    let finished = broker.retire(Duration::from_secs(2))?;
    require(finished && broker.retirement_complete(), "broker joined retirement did not complete")?;
    let retired = broker.latest_status().ok_or("missing actual broker retirement record")?;
    require(retired.state == BootstrapState::Retired && !retired.faulted && retired.granted == android,
        "actual broker retirement scope/phase mismatch")?;
    status_record(&state, "broker-retired.json", retired)?;
    let audit = broker.pressure_audit().ok_or("missing joined worker pressure audit")?;
    if android { audit.require_minimal_root_defaults()?; }
    save(&state, "broker-pressure-audit.json", &audit.to_json()?)?;
    // An independently created executable pin may NOT create a second broker
    // while either old lifecycle process lives, even after clean retirement.
    let replacement = ExecutablePin::from_lifecycle(open(&broker_path, false)?, broker_hash)?;
    match LifecycleBroker::spawn(replacement, spec, &borrowed) {
        Err(Error::Reject("previous cell has not retired and exited")) => {}
        Ok(mut unexpected) => { unexpected.abort_before_initialize()?; return Err("same living cell incorrectly admitted a replacement".into()); }
        Err(error) => return Err(format!("same-cell refusal had an unrelated cause: {error}").into()),
    }
    actor_pin.live()?;
    require(!pidfd_dead(handles[2].as_raw_fd())?, "private init must stay held until broker receipt")?;
    send_byte(parent_channel.as_raw_fd(), b'R')?;
    let end = Instant::now() + Duration::from_secs(10);
    let actor_exit = loop {
        if let Some(exit) = actor.try_wait()? { break exit; }
        require(Instant::now() < end, "exact owned actor exit deadline")?;
        thread::sleep(Duration::from_millis(10));
    };
    require(actor_exit.success() && pidfd_dead(handles[1].as_raw_fd())? && pidfd_dead(handles[2].as_raw_fd())?,
        "exact owner/init did not both exit cleanly")?;
    let scoped = format!("/proc/self/fd/{}", scope.as_raw_fd());
    require(fs::read_to_string(format!("{scoped}/cgroup.events"))?.lines().any(|line| line == "populated 0"),
        "owned domain still populated")?;
    require(fs::read_to_string(format!("{scoped}/memory.max"))? == "536870912\n" &&
        fs::read_to_string(format!("{scoped}/memory.high"))? == (if pressure { "402653184\n" } else { "max\n" }) &&
        fs::read_to_string(format!("{scoped}/memory.swap.max"))? == "0\n", "fixed budget changed during canary")?;
    outer_retirement_record(&state, &cgroup, unit, phase, &nonce, &scope)?;
    save(&state, "driver-result.json", &format!("{{\"ok\":true,\"phase\":\"{phase}\",\"nonce\":\"{}\",\"driver_pid\":{},\"actual_broker\":true,\"broker_pid\":{},\"owner_pid\":{},\"init_pid\":{init_pid},\"bootstrap_rights\":16,\"same_cell_retry_denied\":true,\"broker_retired_and_reaped\":true,\"owner_and_init_exited\":true,\"domain_populated\":false,\"android_enrollment\":{},\"joined_host_audit_present\":true,\"pressure_workload_requested\":{},\"real_pressure_verified\":false,\"installed_supervisor_changed\":false}}",
        hex(&nonce), unsafe { libc::getpid() }, broker.pid(), actor.id(), android, pressure))?;
    println!("{{\"ok\":true,\"phase\":\"{phase}\",\"real_pressure_verified\":false}}");
    Ok(())
}
fn main() {
    let args: Vec<String> = std::env::args().collect();
    let outcome = if args.get(1).map(String::as_str) == Some("prepare") { prepare(&args) } else { run(&args) };
    if let Err(error) = outcome {
        eprintln!("owned-relay-canary: {error}");
        // Exact broker/actor children are tied to this driver by PDEATHSIG;
        // actor ties its exact PID 1 similarly. No success receipt is written
        // on error. Preserve the owned unit/files for independent inspection.
        std::process::exit(1);
    }
}
