//! One empty APK transport born in its own fixed SELinux domain.
//! The child inherits only the preparation AppArmor profile. It receives no
//! APK, package, pathname or comparison descriptor, cannot write any file, and
//! must be reaped before the preparation owner fills its returned empty inode.
use super::{ApplicationError, Result, apk_io, external, query_io as helper, reject, require};
use crate::control::apk_payload;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{fs::File, io, mem, os::{fd::{AsRawFd, FromRawFd, RawFd}, unix::fs::MetadataExt},
    sync::atomic::{AtomicBool, Ordering}, time::{Duration, Instant}};

pub(crate) const MODE: &str = "--working-payload-birth";
const ARGUMENT: &std::ffi::CStr = c"--working-payload-birth";
const PARENT: &[u8] = b"u:system_r:p4_linux_working_privateprep_t:s0\0";
const CHILD: &[u8] = b"u:system_r:p4_linux_working_payload_birth_t:s0\0";
const PROFILE: &[u8] = b"droidloom-working-privateprep (enforce)\n";
const LIMIT: Duration = Duration::from_secs(10);
const RETIRE_RESERVE: Duration = Duration::from_secs(2);
static RETIREMENT_UNPROVEN: AtomicBool = AtomicBool::new(false);

pub(crate) fn retirement_failed() -> bool { RETIREMENT_UNPROVEN.load(Ordering::Acquire) }
pub(crate) fn require_retired() -> Result<()> {
    if retirement_failed() { Err(ApplicationError::RetirementUnproven) } else { Ok(()) }
}
fn before(end: Instant) -> Result<()> { require(Instant::now() < end, "empty payload original end expired") }
fn actor(context: &[u8]) -> Result<()> {
    helper::own_root_credentials()?;
    require(crate::production_mac::self_attr::selinux_current().map_err(external)? == context,
        "empty payload actor is not its fixed SELinux domain")?;
    let file = std::fs::OpenOptions::new().read(true)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open("/proc/thread-self/attr/apparmor/current")?;
    use std::io::Read;
    let mut kind: libc::statfs = unsafe { mem::zeroed() };
    require(unsafe { libc::fstatfs(file.as_raw_fd(), &mut kind) } == 0
        && kind.f_type == 0x9fa0 && file.metadata()?.is_file(), "empty payload AA observation is not procfs")?;
    let mut bytes = Vec::new(); file.take(257).read_to_end(&mut bytes)?;
    require(bytes == PROFILE, "empty payload must retain the exact enforcing preparation profile")
}
use std::os::unix::fs::OpenOptionsExt;

fn channel() -> Result<()> {
    for (option, expected) in [(libc::SO_TYPE, libc::SOCK_SEQPACKET),
        (libc::SO_DOMAIN, libc::AF_UNIX), (libc::SO_PASSCRED, 1)] {
        let mut actual = 0_i32; let mut size = mem::size_of_val(&actual) as libc::socklen_t;
        if unsafe { libc::getsockopt(3, libc::SOL_SOCKET, option,
            (&mut actual as *mut i32).cast(), &mut size) } != 0 { return Err(io::Error::last_os_error().into()); }
        require(size as usize == mem::size_of_val(&actual) && actual == expected,
            "empty payload requires the original credential-bearing anonymous seqpacket")?;
    }
    let mut label = [0_u8; 256]; let mut size = label.len() as libc::socklen_t;
    if unsafe { libc::getsockopt(3, libc::SOL_SOCKET, libc::SO_PEERSEC,
        label.as_mut_ptr().cast(), &mut size) } != 0 { return Err(io::Error::last_os_error().into()); }
    require(size as usize <= label.len(), "empty payload channel label exceeds its bound")?;
    channel_label(&label[..size as usize])
}
fn channel_label(actual: &[u8]) -> Result<()> {
    require(actual == b"droidloom-working-privateprep (enforce)",
        "empty payload anonymous channel is not the actual preparation AA origin")
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
enum Phase { Create, Created }
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Wire { phase: Phase, nonce: [u8; 16], deadline_ns: u64 }
fn remaining_end(wire: Wire) -> Result<Instant> {
    let start = Instant::now();
    let left = wire.deadline_ns.checked_sub(super::protocol::monotonic_ns()?)
        .ok_or_else(|| reject("empty payload original deadline expired"))?;
    require(wire.nonce != [0; 16] && left > 0 && u128::from(left) <= LIMIT.as_nanos(),
        "empty payload nonce or original window differs")?;
    Ok(start + Duration::from_nanos(left))
}

/// This object cannot be deserialized or reconstructed from a comparison.
/// Its PIDFD is retained only after actual waitid(P_PIDFD) returned exit zero.
pub(crate) struct Retirement {
    pid: u32, pidfd: File, node: (u64, u64), code: i32, status: i32,
    payload_node: (u64, u64),
}
impl Retirement {
    pub(crate) fn guard(&self) -> Result<()> {
        require_retired()?;
        let m = self.pidfd.metadata()?;
        require((m.dev(), m.ino()) == self.node && self.pid > 1
            && self.code == libc::CLD_EXITED && self.status == 0,
            "empty payload actual retirement custody changed")
    }
    pub(crate) fn require_payload(&self, file: &File) -> Result<()> {
        self.guard()?;
        let m = file.metadata()?;
        require((m.dev(), m.ino()) == self.payload_node,
            "prepared APK is not the original separately born payload inode")
    }
    pub(crate) fn comparison(&self) -> Result<Value> {
        self.guard()?;
        Ok(json!({"schema":"droidloom.working-empty-apk-payload-birth.v1",
            "pid":self.pid,"pidfd_device":self.node.0,"pidfd_inode":self.node.1,
            "waitid_code":self.code,"waitid_status":self.status,"actual_reaped":true,
            "payload_device":self.payload_node.0,"payload_inode":self.payload_node.1,
            "birth_context":"u:object_r:droidloom_apk_payload:s0",
            "creator_role":"u:system_r:p4_linux_working_payload_birth_t:s0",
            "creator_received_apk_descriptors":false,"creator_payload_bytes":0,
            "creation_limit_seconds":10,"original_sender_window_renewed":false}))
    }
}
fn poison(child: &mut helper::Child) -> ApplicationError {
    RETIREMENT_UNPROVEN.store(true, Ordering::Release);
    // The original PIDFD remains held; a renewed Drop cleanup timer cannot
    // turn a missed original retirement window into a successful operation.
    if let Some(fd) = child.pidfd.take() { mem::forget(fd); }
    ApplicationError::RetirementUnproven
}
fn retire_before(child: &mut helper::Child, end: Instant) -> Result<()> {
    if child.terminal.is_some() { return Ok(()); }
    match child.observe() { Ok(true) => return Ok(()), Err(_) => return Err(poison(child)), Ok(false) => {} }
    let raw = child.pidfd.as_ref().ok_or(ApplicationError::RetirementUnproven)?.as_raw_fd();
    if unsafe { libc::syscall(libc::SYS_pidfd_send_signal, raw, libc::SIGKILL,
        std::ptr::null::<libc::siginfo_t>(), 0_u32) } != 0
        && io::Error::last_os_error().raw_os_error() != Some(libc::ESRCH) { return Err(poison(child)); }
    loop {
        match child.observe() { Ok(true) => return Ok(()), Err(_) => return Err(poison(child)), Ok(false) => {} }
        if Instant::now() >= end { return Err(poison(child)); }
        let mut p = libc::pollfd { fd: raw, events: libc::POLLIN, revents: 0 };
        let n = unsafe { libc::poll(&mut p, 1, end.saturating_duration_since(Instant::now())
            .as_millis().clamp(1, 10) as i32) };
        if n < 0 && io::Error::last_os_error().kind() != io::ErrorKind::Interrupted { return Err(poison(child)); }
    }
}

pub(crate) fn create(original_end: Instant) -> Result<(File, Retirement)> {
    require_retired()?; actor(PARENT)?;
    let end = original_end.min(Instant::now() + LIMIT);
    let body_end = end.checked_sub(RETIRE_RESERVE).ok_or_else(|| reject("empty payload retirement reserve absent"))?;
    before(body_end)?; super::worker::require_wait_semantics()?;
    let executable = helper::above_reserved(&crate::production_host_admission::application_worker_executable().map_err(external)?)?;
    let image = executable.metadata()?;
    let (channel, child_channel) = apk_io::pair()?;
    let child_channel = helper::above_reserved(&File::from(std::os::fd::OwnedFd::from(child_channel)))?;
    let stdio = helper::fixed_stdio()?;
    let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, libc::getpid(), 0_u32) };
    if raw < 0 { return Err(io::Error::last_os_error().into()); }
    let owner = unsafe { File::from_raw_fd(raw as RawFd) }; helper::alive(&owner)?;
    let mut nonce = [0_u8; 16]; let mut offset = 0;
    while offset < nonce.len() {
        let n = unsafe { libc::getrandom(nonce[offset..].as_mut_ptr().cast(), nonce.len() - offset, 0) };
        if n < 0 { let e = io::Error::last_os_error(); if e.kind() == io::ErrorKind::Interrupted { continue; } return Err(e.into()); }
        require(n > 0, "empty payload original nonce unavailable")?; offset += n as usize;
    }
    require(nonce != [0; 16], "empty payload nonce cannot be zero")?;
    let wire = Wire { phase: Phase::Create, nonce, deadline_ns: super::protocol::monotonic_ns()?
        .checked_add(end.saturating_duration_since(Instant::now()).as_nanos() as u64)
        .ok_or_else(|| reject("empty payload deadline overflow"))? };
    let program = filter(Some(executable.as_raw_fd()));
    let fprog = libc::sock_fprog { len: program.len() as u16, filter: program.as_ptr().cast_mut() };
    let argv = [c"/usr/bin/droidloom-applications".as_ptr(), ARGUMENT.as_ptr(), std::ptr::null()];
    let environment = [c"LC_ALL=C".as_ptr(), std::ptr::null()];
    let parent = unsafe { libc::getpid() }; let mut raw_pidfd = -1_i32;
    let args = super::worker::CloneArgs { flags: libc::CLONE_PIDFD as u64,
        pidfd: (&mut raw_pidfd as *mut i32) as u64, exit_signal: libc::SIGCHLD as u64,
        ..super::worker::CloneArgs::default() };
    let mut mask = super::worker::SignalMask::block()?; before(body_end)?;
    let pid = unsafe { libc::syscall(libc::SYS_clone3, &args, mem::size_of_val(&args)) };
    if pid < 0 { return Err(io::Error::last_os_error().into()); }
    if pid == 0 { unsafe { helper::bootstrap(helper::HelperRole::WorkingOriginalPayloadBirth,
        parent, executable.as_raw_fd(), child_channel.as_raw_fd(), stdio.as_raw_fd(),
        argv.as_ptr(), environment.as_ptr(), &fprog) } }
    if raw_pidfd < 0 { RETIREMENT_UNPROVEN.store(true, Ordering::Release); return Err(ApplicationError::RetirementUnproven); }
    let mut child = helper::Child { pid: pid as u32,
        pidfd: Some(unsafe { File::from_raw_fd(raw_pidfd) }), terminal: None };
    drop(child_channel);
    let operation = (|| -> Result<(File, Retirement)> {
        mask.restore()?;
        let actual = helper::pidfd_info(child.pidfd.as_ref().unwrap())?;
        require(actual.pid == child.pid && actual.ppid == parent as u32,
            "empty payload child is not this original direct child")?;
        // Exactly one parent PIDFD is sent. All original APK descriptors were
        // CLOEXEC-closed by bootstrap and never enter this protocol.
        apk_io::send_before(channel.as_raw_fd(), &wire, &[owner.as_raw_fd()], body_end)?;
        let reply = apk_io::receive_before::<Wire>(channel.as_raw_fd(), body_end)?;
        require(reply.peer.pid == pid as i32 && reply.peer.uid == 0 && reply.peer.gid == 0
            && reply.value == Wire { phase: Phase::Created, ..wire } && reply.files.len() == 1,
            "empty payload response origin, phase, nonce or descriptor count differs")?;
        let file = reply.files.into_iter().next().ok_or_else(|| reject("empty payload descriptor absent"))?;
        apk_payload::validate_empty_born(&file).map_err(external)?;
        child.finish(end)?;
        actor(PARENT)?; before(end)?;
        let image_after = executable.metadata()?;
        require((image.dev(), image.ino(), image.len(), image.mtime(), image.mtime_nsec(), image.ctime(), image.ctime_nsec())
            == (image_after.dev(), image_after.ino(), image_after.len(), image_after.mtime(), image_after.mtime_nsec(), image_after.ctime(), image_after.ctime_nsec()),
            "empty payload installed executable changed")?;
        apk_payload::validate_empty_born(&file).map_err(external)?;
        let (code, status) = child.terminal.ok_or(ApplicationError::RetirementUnproven)?;
        let pidfd = child.pidfd.take().ok_or(ApplicationError::RetirementUnproven)?;
        let node = pidfd.metadata()?; let payload = file.metadata()?;
        let retired = Retirement { pid: child.pid, node: (node.dev(), node.ino()), pidfd, code, status,
            payload_node: (payload.dev(), payload.ino()) };
        retired.guard()?; Ok((file, retired))
    })();
    if operation.is_err() { retire_before(&mut child, end)?; }
    operation
}

fn restrict_dumpability() -> bool {
    // A normal exec can reset the pre-exec restriction. Only restrict this
    // fresh child, before checking the complete capability/privilege state.
    unsafe {
        libc::prctl(libc::PR_SET_DUMPABLE, 0, 0, 0, 0) == 0
            && libc::prctl(libc::PR_GET_DUMPABLE, 0, 0, 0, 0) == 0
    }
}

pub(super) fn entry() -> Result<()> {
    let args = std::env::args_os().collect::<Vec<_>>();
    require(fixed_arguments(&args),
        "empty payload entry accepts only the installed fixed argv")?;
    actor(CHILD)?; helper::verify_fixed_stdio()?;
    require(restrict_dumpability(), "empty payload fresh child could not restrict dumpability")?;
    helper::empty_capabilities()?;
    require(unsafe { libc::prctl(libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) } == 1,
        "empty payload child must retain no-new-privileges")?;
    drop(crate::production_host_admission::application_worker_executable().map_err(external)?);
    channel()?; helper::install_filter(&filter(None))?;
    let parent = unsafe { libc::getppid() }; require(parent > 1, "empty payload original parent absent")?;
    let packet = apk_io::receive_before::<Wire>(3, Instant::now() + Duration::from_secs(5))?;
    require(packet.value.phase == Phase::Create && packet.files.len() == 1,
        "empty payload creator accepts only one parent PIDFD")?;
    let owner = packet.files.into_iter().next().ok_or_else(|| reject("empty payload parent PIDFD absent"))?;
    helper::parent_identity(&owner, packet.peer, parent)?;
    let end = remaining_end(packet.value)?;
    let body_end = end.checked_sub(RETIRE_RESERVE).ok_or_else(|| reject("empty payload child retirement reserve absent"))?;
    before(body_end)?;
    let file = apk_payload::create_empty_born().map_err(external)?;
    helper::parent_identity(&owner, packet.peer, parent)?; actor(CHILD)?; helper::empty_capabilities()?;
    apk_io::send_before(3, &Wire { phase: Phase::Created, ..packet.value }, &[file.as_raw_fd()], body_end)?;
    helper::parent_identity(&owner, packet.peer, parent)?; before(body_end)
}
fn fixed_arguments(args: &[std::ffi::OsString]) -> bool {
    args.len() == 2 && args[0] == "/usr/bin/droidloom-applications" && args[1] == MODE
}

// No second exec, namespace/process/socket creation, writer open, filesystem
// mutation or payload write exists after fresh entry. Stdio writes only reach
// the three already-EOF read-only pipes and cannot modify the empty payload.
fn filter(executable: Option<RawFd>) -> Vec<libc::sock_filter> {
    let ins = |code, jt, jf, k| libc::sock_filter { code, jt, jf, k };
    let deny = 0x0005_0000 | libc::EPERM as u32; let allow = 0x7fff_0000;
    let mut f = vec![ins(0x20, 0, 0, 4), ins(0x15, 1, 0, 0xc000_003e), ins(0x06, 0, 0, 0x8000_0000),
        ins(0x20, 0, 0, 0), ins(0x35, 0, 1, 0x4000_0000), ins(0x06, 0, 0, deny)];
    let mut narrow = |syscall: libc::c_long, args: &[(u32, u64)]| {
        let mut body = Vec::new();
        for (index, value) in args {
            for (offset, part) in [(16 + index * 8, *value as u32), (20 + index * 8, (*value >> 32) as u32)] {
                body.extend([ins(0x20, 0, 0, offset), ins(0x15, 1, 0, part), ins(0x06, 0, 0, deny)]);
            }
        }
        body.push(ins(0x06, 0, 0, allow));
        f.push(ins(0x15, 0, body.len() as u8, syscall as u32)); f.extend(body); f.push(ins(0x20, 0, 0, 0));
    };
    narrow(459, &[(0, 100), (3, 1)]);
    narrow(libc::SYS_recvmsg, &[(0, 3)]); narrow(libc::SYS_sendmsg, &[(0, 3)]);
    narrow(libc::SYS_ioctl, &[(1, 0xc050_ff0b)]);
    narrow(libc::SYS_memfd_create, &[(1, (libc::MFD_CLOEXEC | libc::MFD_ALLOW_SEALING | 0x0008) as u64)]);
    if let Some(fd) = executable { narrow(libc::SYS_execveat, &[(0, fd as u64), (4, libc::AT_EMPTY_PATH as u64)]); }
    // openat accepts only a read-only description; no create/truncate/append.
    f.extend([ins(0x15, 0, 5, libc::SYS_openat as u32), ins(0x20, 0, 0, 32),
        ins(0x54, 0, 0, (libc::O_ACCMODE | libc::O_CREAT | libc::O_TRUNC | libc::O_APPEND | libc::O_TMPFILE) as u32),
        ins(0x15, 1, 0, 0), ins(0x06, 0, 0, deny), ins(0x06, 0, 0, allow), ins(0x20, 0, 0, 0)]);
    f.extend([ins(0x15, 0, 5, libc::SYS_write as u32), ins(0x20, 0, 0, 16),
        ins(0x35, 0, 1, 3), ins(0x06, 0, 0, deny), ins(0x06, 0, 0, allow),
        ins(0x06, 0, 0, deny), ins(0x20, 0, 0, 0)]);
    for syscall in [libc::SYS_read, libc::SYS_close, libc::SYS_fstat, libc::SYS_newfstatat,
        libc::SYS_statx, libc::SYS_fstatfs, libc::SYS_readlink, libc::SYS_readlinkat,
        libc::SYS_mmap, libc::SYS_mprotect, libc::SYS_munmap, libc::SYS_brk, libc::SYS_madvise,
        libc::SYS_rt_sigaction, libc::SYS_rt_sigprocmask, libc::SYS_rt_sigreturn, libc::SYS_arch_prctl,
        libc::SYS_prlimit64, libc::SYS_getrlimit, libc::SYS_getrandom, libc::SYS_set_tid_address,
        libc::SYS_set_robust_list, libc::SYS_rseq, libc::SYS_access, libc::SYS_faccessat, libc::SYS_faccessat2,
        libc::SYS_futex, libc::SYS_clock_gettime, libc::SYS_clock_nanosleep, libc::SYS_nanosleep,
        libc::SYS_poll, libc::SYS_ppoll, libc::SYS_fcntl, libc::SYS_getpid, libc::SYS_gettid, libc::SYS_getppid,
        libc::SYS_getuid, libc::SYS_geteuid, libc::SYS_getgid, libc::SYS_getegid, libc::SYS_getgroups,
        libc::SYS_capget, libc::SYS_prctl, libc::SYS_getsockopt, libc::SYS_fgetxattr,
        libc::SYS_lseek, libc::SYS_sched_getaffinity, libc::SYS_exit_group, libc::SYS_exit] {
        f.extend([ins(0x15, 0, 1, syscall as u32), ins(0x06, 0, 0, allow)]);
    }
    f.push(ins(0x06, 0, 0, deny)); f
}

#[cfg(test)]
mod tests {
    use super::*;
    fn decision(program: &[libc::sock_filter], nr: u32, args: [u64; 6]) -> u32 {
        let mut input = [0_u32; 16]; input[0] = nr; input[1] = 0xc000_003e;
        for (i, a) in args.iter().enumerate() { input[4 + 2 * i] = *a as u32; input[5 + 2 * i] = (*a >> 32) as u32; }
        let (mut pc, mut a) = (0_usize, 0_u32);
        for _ in 0..program.len() + 1 {
            let i = program.get(pc).expect("bounded BPF instruction");
            match i.code { 0x20 => { a = input[i.k as usize / 4]; pc += 1; },
                0x54 => { a &= i.k; pc += 1; },
                0x15 => pc += 1 + if a == i.k { i.jt } else { i.jf } as usize,
                0x35 => pc += 1 + if a >= i.k { i.jt } else { i.jf } as usize,
                0x06 => return i.k, _ => panic!("unexpected BPF opcode") }
        } panic!("BPF did not terminate")
    }
    #[test]
    fn working_payload_birth_protocol_has_no_apk_path_or_package_selector() {
        let wire = Wire { phase: Phase::Create, nonce: [1; 16], deadline_ns: 1 };
        let raw = serde_json::to_value(wire).unwrap();
        assert_eq!(serde_json::from_value::<Wire>(raw.clone()).unwrap(), wire);
        for field in ["path", "package", "fd", "context", "bytes", "kind"] {
            let mut wrong = raw.clone(); wrong[field] = json!("caller-selected");
            assert!(serde_json::from_value::<Wire>(wrong).is_err());
        }
        assert!(remaining_end(wire).is_err());
        let args: Vec<std::ffi::OsString> = ["/usr/bin/droidloom-applications", MODE].map(Into::into).into();
        assert!(fixed_arguments(&args));
        let mut wrong = args.clone(); wrong.push("/caller.apk".into());
        assert!(!fixed_arguments(&wrong));
        let mut wrong = args.clone(); wrong[0] = "/tmp/other-elf".into();
        assert!(!fixed_arguments(&wrong));
        let mut wrong = args; wrong[1] = "--working-qualification-prepare".into();
        assert!(!fixed_arguments(&wrong));
    }
    #[test]
    fn working_payload_birth_channel_never_substitutes_the_broker_profile() {
        assert!(channel_label(b"droidloom-working-privateprep (enforce)").is_ok());
        for wrong in [b"droidloom-production-broker (enforce)".as_slice(),
            b"droidloom-working-privateprep (complain)", b"unconfined",
            b"u:system_r:p4_linux_working_privateprep_t:s0",
            b"droidloom-working-privateprep (enforce)\0"] {
            assert!(channel_label(wrong).is_err());
        }
    }
    #[test]
    fn working_payload_birth_filter_forbids_writers_namespace_and_second_exec() {
        let p = filter(None); let allow = 0x7fff_0000; let deny = 0x0005_0000 | libc::EPERM as u32;
        assert_eq!(decision(&p, libc::SYS_memfd_create as u32, [0, 11, 0, 0, 0, 0]), allow);
        for flags in [0, 1, 3, 7, 15, 19, 0x1_0000_000b] {
            assert_eq!(decision(&p, libc::SYS_memfd_create as u32, [0, flags, 0, 0, 0, 0]), deny);
        }
        assert_eq!(decision(&p, libc::SYS_openat as u32, [0, 0, libc::O_CLOEXEC as u64, 0, 0, 0]), allow);
        for flags in [libc::O_WRONLY, libc::O_RDWR, libc::O_CREAT, libc::O_TRUNC, libc::O_APPEND, libc::O_TMPFILE] {
            assert_eq!(decision(&p, libc::SYS_openat as u32, [0, 0, flags as u64, 0, 0, 0]), deny);
        }
        for fd in 0..3 { assert_eq!(decision(&p, libc::SYS_write as u32, [fd, 0, 0, 0, 0, 0]), allow); }
        assert_eq!(decision(&p, libc::SYS_write as u32, [3, 0, 0, 0, 0, 0]), deny);
        for nr in [libc::SYS_execve, libc::SYS_execveat, libc::SYS_clone, libc::SYS_clone3,
            libc::SYS_fork, libc::SYS_vfork, libc::SYS_socket, libc::SYS_socketpair,
            libc::SYS_setns, libc::SYS_unshare, libc::SYS_mount, libc::SYS_setxattr,
            libc::SYS_fsetxattr, libc::SYS_pwrite64, libc::SYS_writev, libc::SYS_ftruncate, 460] {
            assert_eq!(decision(&p, nr as u32, [0; 6]), deny, "syscall {nr}");
        }
        let before = filter(Some(73));
        assert_eq!(decision(&before, libc::SYS_execveat as u32, [73, 0, 0, 0, libc::AT_EMPTY_PATH as u64, 0]), allow);
        assert_eq!(decision(&before, libc::SYS_execveat as u32, [74, 0, 0, 0, libc::AT_EMPTY_PATH as u64, 0]), deny);
    }
    #[test]
    fn working_payload_birth_fresh_exec_reseals_dumpability() {
        const MARKER: &str = "DROIDLOOM_TEST_WORKING_BIRTH_DUMPABILITY_CHILD";
        if std::env::var_os(MARKER).as_deref() == Some(std::ffi::OsStr::new("1")) {
            // A real fresh execution must demonstrate the reset; this test
            // never claims that it entered the production SELinux/AA role.
            assert_eq!(unsafe { libc::prctl(libc::PR_GET_DUMPABLE, 0, 0, 0, 0) }, 1);
            assert!(restrict_dumpability());
            assert_eq!(unsafe { libc::prctl(libc::PR_GET_DUMPABLE, 0, 0, 0, 0) }, 0);
            return;
        }
        use std::os::unix::process::CommandExt;
        let mut command = std::process::Command::new(std::env::current_exe().unwrap());
        let name = concat!(module_path!(), "::working_payload_birth_fresh_exec_reseals_dumpability");
        command.args(["--exact", name.split_once("::").unwrap().1, "--nocapture"])
            .env(MARKER, "1");
        unsafe {
            command.pre_exec(|| {
                if libc::prctl(libc::PR_SET_DUMPABLE, 0, 0, 0, 0) != 0 {
                    return Err(io::Error::last_os_error());
                }
                Ok(())
            });
        }
        assert!(command.status().unwrap().success());
    }
    #[test]
    fn working_payload_birth_filter_rejects_actual_kernel_write_and_growth() {
        // Byte/filter test only: this host need not carry the production LSM
        // policy. No fixture claims to have acquired a production birth role.
        let program = filter(None);
        let fprog = libc::sock_fprog { len: program.len() as u16, filter: program.as_ptr().cast_mut() };
        let pid = unsafe { libc::fork() }; assert!(pid >= 0);
        if pid == 0 { unsafe {
            // No allocation, lock or Rust destructor after fork.
            if libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0
                || libc::prctl(libc::PR_SET_SECCOMP, 2, &fprog as *const libc::sock_fprog) != 0 { libc::_exit(11); }
            if !restrict_dumpability() { libc::_exit(17); }
            let fd = libc::syscall(libc::SYS_memfd_create, c"droidloom-apk-payload".as_ptr(), 11_u32);
            if fd < 3 { libc::_exit(12); }
            let byte = 1_u8;
            if libc::syscall(libc::SYS_write, fd, &byte, 1_usize) != -1 || *libc::__errno_location() != libc::EPERM { libc::_exit(13); }
            if libc::syscall(libc::SYS_ftruncate, fd, 1_i64) != -1 || *libc::__errno_location() != libc::EPERM { libc::_exit(14); }
            if libc::syscall(libc::SYS_fcntl, fd, libc::F_GET_SEALS) != 0x20 { libc::_exit(15); }
            if libc::syscall(libc::SYS_lseek, fd, 0_i64, libc::SEEK_END) != 0 { libc::_exit(16); }
            libc::_exit(0);
        } }
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, pid, 0_u32) };
        assert!(raw >= 0);
        let pidfd = unsafe { File::from_raw_fd(raw as RawFd) };
        let mut status: libc::siginfo_t = unsafe { mem::zeroed() };
        assert_eq!(unsafe { libc::waitid(libc::P_PIDFD, pidfd.as_raw_fd() as u32, &mut status, libc::WEXITED) }, 0);
        assert_eq!(unsafe { status.si_pid() }, pid);
        assert_eq!(status.si_code, libc::CLD_EXITED);
        assert_eq!(unsafe { status.si_status() }, 0);
    }
}
