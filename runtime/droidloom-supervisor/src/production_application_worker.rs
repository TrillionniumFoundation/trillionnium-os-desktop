//! Fresh image and fixed query child. After each raw clone3 child branch only
//! preallocated storage and async-signal-safe syscalls are used before exec.
use super::protocol::{self, Message};
use super::*;
use std::mem;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::time::{Duration, Instant};

#[path = "production_application_bridge_worker.rs"]
mod bridge;
#[path = "production_application_executable.rs"]
pub(super) mod executable;
#[path = "production_application_mac_child.rs"]
mod mac_child;

#[repr(C)]
#[derive(Default)]
pub(crate) struct CloneArgs {
    pub(crate) flags: u64,
    pub(crate) pidfd: u64,
    pub(crate) child_tid: u64,
    pub(crate) parent_tid: u64,
    pub(crate) exit_signal: u64,
    pub(crate) stack: u64,
    pub(crate) stack_size: u64,
    pub(crate) tls: u64,
    pub(crate) set_tid: u64,
    pub(crate) set_tid_size: u64,
    pub(crate) cgroup: u64,
}

pub(crate) struct SignalMask {
    original: u64,
    active: bool,
}
impl SignalMask {
    pub(crate) fn block() -> Result<Self> {
        let all = u64::MAX;
        let mut original = 0_u64;
        if unsafe {
            libc::syscall(
                libc::SYS_rt_sigprocmask,
                libc::SIG_SETMASK,
                &all,
                &mut original,
                mem::size_of::<u64>(),
            )
        } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
        Ok(Self {
            original,
            active: true,
        })
    }
    pub(crate) fn restore(&mut self) -> Result<()> {
        if self.active {
            if unsafe {
                libc::syscall(
                    libc::SYS_rt_sigprocmask,
                    libc::SIG_SETMASK,
                    &self.original,
                    std::ptr::null_mut::<u64>(),
                    mem::size_of::<u64>(),
                )
            } != 0
            {
                return Err(io::Error::last_os_error().into());
            }
            self.active = false;
        }
        Ok(())
    }
}
impl Drop for SignalMask {
    fn drop(&mut self) {
        let _ = self.restore();
    }
}

pub(super) fn require_wait_semantics() -> Result<()> {
    let mut action: libc::sigaction = unsafe { mem::zeroed() };
    if unsafe { libc::sigaction(libc::SIGCHLD, std::ptr::null(), &mut action) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        action.sa_sigaction == libc::SIG_DFL && action.sa_flags & libc::SA_NOCLDWAIT == 0,
        "application worker requires default waitable SIGCHLD",
    )
}

fn fresh_signals() -> Result<()> {
    for signal in 1..=64 {
        if matches!(signal, libc::SIGKILL | libc::SIGSTOP | 32 | 33) {
            continue;
        }
        let mut action: libc::sigaction = unsafe { mem::zeroed() };
        action.sa_sigaction = libc::SIG_DFL;
        if unsafe { libc::sigemptyset(&mut action.sa_mask) } != 0
            || unsafe { libc::sigaction(signal, &action, std::ptr::null_mut()) } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
    }
    let empty = 0_u64;
    if unsafe {
        libc::syscall(
            libc::SYS_rt_sigprocmask,
            libc::SIG_SETMASK,
            &empty,
            std::ptr::null_mut::<u64>(),
            mem::size_of::<u64>(),
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    Ok(())
}

pub(super) unsafe fn bootstrap(
    parent: libc::pid_t,
    executable: RawFd,
    socket: RawFd,
    null: RawFd,
    argv: *const *const libc::c_char,
    envp: *const *const libc::c_char,
) -> ! {
    unsafe {
        if libc::getppid() != parent
            || libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) != 0
            || libc::getppid() != parent
        {
            libc::_exit(125);
        }
        if libc::dup2(null, 0) != 0
            || libc::dup2(null, 1) != 1
            || libc::dup2(null, 2) != 2
            || libc::dup2(socket, 3) != 3
        {
            libc::_exit(125);
        }
        if libc::syscall(libc::SYS_close_range, 3_u32, u32::MAX, 4_u32) != 0
            || libc::fcntl(3, libc::F_SETFD, 0) != 0
        {
            libc::_exit(125);
        }
        let zero = libc::rlimit {
            rlim_cur: 0,
            rlim_max: 0,
        };
        let memory = libc::rlimit {
            rlim_cur: 512 * 1024 * 1024,
            rlim_max: 512 * 1024 * 1024,
        };
        let cpu = libc::rlimit {
            rlim_cur: 15,
            rlim_max: 15,
        };
        if libc::setrlimit(libc::RLIMIT_CORE, &zero) != 0
            || libc::setrlimit(libc::RLIMIT_FSIZE, &zero) != 0
            || libc::setrlimit(libc::RLIMIT_AS, &memory) != 0
            || libc::setrlimit(libc::RLIMIT_CPU, &cpu) != 0
        {
            libc::_exit(125);
        }
        libc::syscall(
            libc::SYS_execveat,
            executable,
            c"".as_ptr(),
            argv,
            envp,
            libc::AT_EMPTY_PATH,
        );
        libc::_exit(125);
    }
}

#[repr(C)]
#[derive(Default)]
struct PidfdInfo {
    mask: u64,
    cgroup_id: u64,
    pid: u32,
    tgid: u32,
    ppid: u32,
    ruid: u32,
    rgid: u32,
    euid: u32,
    egid: u32,
    suid: u32,
    sgid: u32,
    fsuid: u32,
    fsgid: u32,
    exit_code: i32,
    coredump_mask: u32,
    coredump_signal: u32,
    supported_mask: u64,
}
const _: () = assert!(mem::size_of::<PidfdInfo>() == 80);
fn pidfd_info(file: &File) -> Result<PidfdInfo> {
    let mut value = PidfdInfo {
        mask: 3,
        ..PidfdInfo::default()
    };
    if unsafe { libc::ioctl(file.as_raw_fd(), 0xc050_ff0b_u64, &mut value) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        value.mask & 3 == 3 && value.pid > 1 && value.tgid == value.pid,
        "incomplete application pidfd identity",
    )?;
    Ok(value)
}
pub(super) fn created_query_pid(pidfd: &OwnedFd) -> Result<u32> {
    let file = File::from(pidfd.try_clone()?);
    let info = pidfd_info(&file)?;
    require(
        info.ppid == unsafe { libc::getpid() } as u32,
        "transferred query pidfd is not a direct child of this broker",
    )?;
    Ok(info.pid)
}
fn alive(file: &File) -> Result<()> {
    let mut poll = libc::pollfd {
        fd: file.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    let count = unsafe { libc::poll(&mut poll, 1, 0) };
    if count < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(count == 0, "original application owner has exited")
}
fn node(file: &File) -> Result<(u64, u64)> {
    let m = file.metadata()?;
    Ok((m.dev(), m.ino()))
}

fn validate_owner_descriptors(
    files: &[File],
    parent: libc::pid_t,
    projection: QueryProjection,
) -> Result<PidfdInfo> {
    require(files.len() >= 10, "original owner descriptor prefix absent")?;
    let init = pidfd_info(&files[0])?;
    let broker = pidfd_info(&files[1])?;
    require(
        (projection == QueryProjection::EarlyDev || init.ppid == parent as u32)
            && broker.pid == parent as u32
            && init.ruid == init.euid
            && init.ruid == init.suid
            && init.ruid != 0,
        "original init/broker pidfd identity differs",
    )?;
    alive(&files[0])?;
    alive(&files[1])?;
    for (index, kind, command) in [
        (3, libc::CLONE_NEWUSER, 0xff09),
        (4, libc::CLONE_NEWNS, 0xff03),
        (5, libc::CLONE_NEWPID, 0xff05),
        (6, libc::CLONE_NEWIPC, 0xff02),
        (7, libc::CLONE_NEWUTS, 0xff0a),
        (8, libc::CLONE_NEWNET, 0xff04),
        (9, libc::CLONE_NEWCGROUP, 0xff01),
    ] {
        let mut stat: libc::statfs = unsafe { mem::zeroed() };
        if unsafe { libc::fstatfs(files[index].as_raw_fd(), &mut stat) } != 0 {
            return Err(io::Error::last_os_error().into());
        }
        require(
            stat.f_type == 0x6e736673
                && unsafe { libc::ioctl(files[index].as_raw_fd(), 0xb703_u64) } == kind,
            "application namespace descriptor has wrong type",
        )?;
        if projection == QueryProjection::LegacyRoot {
            let current = unsafe {
                libc::ioctl(
                    files[0].as_raw_fd(),
                    command as libc::c_ulong,
                    0 as libc::c_ulong,
                )
            };
            if current < 0 {
                return Err(io::Error::last_os_error().into());
            }
            let current = unsafe { File::from_raw_fd(current) };
            require(
                node(&current)? == node(&files[index])?,
                "namespace is not from the original held init",
            )?;
        } else if index != 3 {
            // The early owner lends the already retained original namespace
            // capabilities. Reopening through a differently mapped init would
            // require forbidden SYS_PTRACE. Verify their actual kernel owner.
            let raw = unsafe { libc::ioctl(files[index].as_raw_fd(), 0xb701 as libc::c_ulong) };
            if raw < 0 {
                return Err(io::Error::last_os_error().into());
            }
            let owner = unsafe { File::from_raw_fd(raw) };
            require(
                node(&owner)? == node(&files[3])?,
                "early query namespace does not belong to the borrowed user namespace",
            )?;
        }
    }
    require(
        files[2].metadata()?.is_dir(),
        "application root descriptor is not a directory",
    )?;
    Ok(init)
}

fn validate_descriptors(
    files: &[File],
    parent: libc::pid_t,
    query: &ApplicationOperation,
    projection: QueryProjection,
    deadline: Instant,
) -> Result<()> {
    require(
        files.len() == query.descriptor_count(),
        "application descriptor count differs",
    )?;
    let init = validate_owner_descriptors(files, parent, projection)?;
    executable::verify(files, query, projection, init.ruid, init.rgid, deadline)?;
    for index in [protocol::STDOUT, protocol::STDERR] {
        require(
            files[index].metadata()?.mode() & libc::S_IFMT == libc::S_IFIFO,
            "query output is not a pipe",
        )?;
    }
    require(
        files[protocol::GATE].metadata()?.mode() & libc::S_IFMT == libc::S_IFSOCK,
        "query gate is not a socket",
    )?;
    Ok(())
}

pub(super) fn entry() -> Result<()> {
    #[cfg(not(target_arch = "x86_64"))]
    return Err(reject(
        "application worker requires reviewed x86_64 host ABI",
    ));
    require(
        unsafe { libc::getuid() } == 0
            && unsafe { libc::geteuid() } == 0
            && unsafe { libc::getgid() } == 0
            && unsafe { libc::getegid() } == 0,
        "application worker requires the original initial-root broker child",
    )?;
    // Verify the same sealed running image after the fresh exec boundary.
    drop(crate::production_host_admission::application_worker_executable().map_err(external)?);
    fresh_signals()?;
    require_wait_semantics()?;
    let parent = unsafe { libc::getppid() };
    require(parent > 1, "application worker has no live broker parent")?;
    let received = protocol::receive(3, Instant::now() + QUERY_LIMIT)?;
    require(
        received.peer.pid == parent && received.peer.uid == 0 && received.peer.gid == 0,
        "application worker sender is not its actual broker parent",
    )?;
    if let Message::BridgeRequest { nonce, deadline_ns } = &received.message {
        let nonce = *nonce;
        let deadline_ns = *deadline_ns;
        let anchor = Instant::now();
        let remaining = deadline_ns
            .checked_sub(protocol::monotonic_ns()?)
            .ok_or_else(|| reject("expired bridge connector deadline"))?;
        require(
            remaining > 0 && remaining <= QUERY_LIMIT.as_nanos() as u64,
            "invalid bridge connector absolute deadline",
        )?;
        let deadline = anchor + Duration::from_nanos(remaining);
        let files: Vec<File> = received.files.into_iter().map(File::from).collect();
        let result = bridge::connect(parent, &files, nonce, deadline);
        if let Err(error) = &result {
            let message: String = error.to_string().chars().take(2048).collect();
            let _ = protocol::send(
                3,
                &Message::BridgeRejected { nonce, message },
                &[],
                deadline,
            );
        }
        return result;
    }
    let (nonce, query, projection, deadline_ns) = match received.message {
        Message::Request {
            nonce,
            query,
            projection,
            deadline_ns,
        } => (nonce, query, projection, deadline_ns),
        _ => return Err(reject("application worker received the wrong first phase")),
    };
    let remaining = deadline_ns
        .checked_sub(protocol::monotonic_ns()?)
        .ok_or_else(|| reject("expired application worker deadline"))?;
    require(
        remaining > 0 && remaining <= QUERY_LIMIT.as_nanos() as u64,
        "invalid application worker absolute deadline",
    )?;
    let deadline = Instant::now() + Duration::from_nanos(remaining);
    let files: Vec<File> = received.files.into_iter().map(File::from).collect();
    let mut child_created = false;
    let result = prepare_query(
        parent,
        &files,
        &query,
        projection,
        nonce,
        deadline_ns,
        deadline,
        &mut child_created,
    );
    if let Err(error) = &result {
        if !child_created {
            let message = error.to_string();
            let message: String = message.chars().take(2048).collect();
            let _ = protocol::send(
                3,
                &Message::RejectedBeforeClone { nonce, message },
                &[],
                deadline,
            );
        }
    }
    result
}

fn prepare_query(
    parent: libc::pid_t,
    files: &[File],
    query: &ApplicationOperation,
    projection: QueryProjection,
    nonce: [u8; 16],
    deadline_ns: u64,
    deadline: Instant,
    child_created: &mut bool,
) -> Result<()> {
    query.validate()?;
    validate_descriptors(files, parent, query, projection, deadline)?;
    let arguments = query.arguments()?;
    let domain = query.domain();
    let mut argv: Vec<_> = arguments.iter().map(|arg| arg.as_ptr()).collect();
    argv.push(std::ptr::null());
    let environment = query.environment(projection);
    let mut envp: Vec<_> = environment.iter().map(|entry| entry.as_ptr()).collect();
    envp.push(std::ptr::null());
    let go = protocol::encoded(&Message::Go { nonce })?;
    let armed = protocol::encoded(&Message::Armed { nonce })?;
    let mut filter = query_filter();
    let program = libc::sock_fprog {
        len: filter.len() as u16,
        filter: filter.as_mut_ptr(),
    };
    // The early query is born in the selected PID namespace while it still
    // has the original host-root credentials/user namespace. Its actual broker
    // wait owner seizes that parked direct child before any credential change.
    // Joining USER and the remaining namespaces happens only after the gate.
    // This avoids granting the broker SYS_PTRACE across mapped credentials.
    let enter_late = projection == QueryProjection::EarlyDev;
    for (index, kind) in [
        (3, libc::CLONE_NEWUSER),
        (6, libc::CLONE_NEWIPC),
        (7, libc::CLONE_NEWUTS),
        (8, libc::CLONE_NEWNET),
        (9, libc::CLONE_NEWCGROUP),
        (4, libc::CLONE_NEWNS),
        (5, libc::CLONE_NEWPID),
    ] {
        if (!enter_late || kind == libc::CLONE_NEWPID)
            && unsafe { libc::setns(files[index].as_raw_fd(), kind) } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
    }
    if !enter_late && unsafe { query_root_credentials() } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    alive(&files[0])?;
    alive(&files[1])?;
    let mut pidfd = -1_i32;
    let args = CloneArgs {
        flags: (libc::CLONE_PIDFD | libc::CLONE_PARENT) as u64,
        pidfd: (&mut pidfd as *mut i32) as u64,
        exit_signal: 0,
        ..CloneArgs::default()
    };
    let mut mask = SignalMask::block()?;
    let pid = unsafe { libc::syscall(libc::SYS_clone3, &args, mem::size_of_val(&args)) };
    if pid < 0 {
        return Err(io::Error::last_os_error().into());
    }
    if pid == 0 {
        unsafe {
            query_child(
                files,
                &go,
                &armed,
                deadline_ns,
                domain,
                enter_late,
                argv.as_ptr(),
                envp.as_ptr(),
                &program,
            );
        }
    }
    *child_created = true;
    if pidfd < 0 {
        return Err(ApplicationError::RetirementUnproven);
    }
    let pidfd = unsafe { OwnedFd::from_raw_fd(pidfd) };
    mask.restore()?;
    // Broker is the actual CLONE_PARENT wait owner. The command remains parked
    // until it has bound this atomic pidfd and all original namespaces.
    protocol::send(
        3,
        &Message::Spawned { nonce },
        &[pidfd.as_raw_fd()],
        deadline,
    )
}

unsafe fn query_root_credentials() -> i32 {
    unsafe {
        if libc::syscall(
            libc::SYS_setgroups,
            0_usize,
            std::ptr::null::<libc::gid_t>(),
        ) != 0
            || libc::syscall(libc::SYS_setresgid, 0_u32, 0_u32, 0_u32) != 0
            || libc::syscall(libc::SYS_setresuid, 0_u32, 0_u32, 0_u32) != 0
            || libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) != 0
        {
            -1
        } else {
            0
        }
    }
}

unsafe fn query_child(
    files: &[File],
    expected_go: &[u8],
    armed: &[u8],
    deadline_ns: u64,
    domain: OperationDomain,
    enter_late: bool,
    argv: *const *const libc::c_char,
    envp: *const *const libc::c_char,
    filter: &libc::sock_fprog,
) -> ! {
    unsafe {
        if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) != 0 {
            libc::_exit(125);
        }
        let mut buffer = [0_u8; 8192];
        loop {
            let mut now = libc::timespec {
                tv_sec: 0,
                tv_nsec: 0,
            };
            if libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut now) != 0 {
                libc::_exit(125);
            }
            let ns = (now.tv_sec as u64)
                .saturating_mul(1_000_000_000)
                .saturating_add(now.tv_nsec as u64);
            if ns >= deadline_ns {
                libc::_exit(125);
            }
            let mut poll = [
                libc::pollfd {
                    fd: files[protocol::GATE].as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
                libc::pollfd {
                    fd: files[0].as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
                libc::pollfd {
                    fd: files[1].as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
            ];
            let ready = libc::poll(
                poll.as_mut_ptr(),
                3,
                ((deadline_ns - ns) / 1_000_000).clamp(1, 20) as i32,
            );
            if ready < 0 {
                if *libc::__errno_location() == libc::EINTR {
                    continue;
                }
                libc::_exit(125);
            }
            if poll[1].revents != 0
                || poll[2].revents != 0
                || poll[0].revents & (libc::POLLNVAL | libc::POLLERR | libc::POLLHUP) != 0
            {
                libc::_exit(125);
            }
            if poll[0].revents & libc::POLLIN != 0 {
                let count = libc::recv(
                    files[protocol::GATE].as_raw_fd(),
                    buffer.as_mut_ptr().cast(),
                    buffer.len(),
                    libc::MSG_DONTWAIT,
                );
                if count < 0 && matches!(*libc::__errno_location(), libc::EINTR | libc::EAGAIN) {
                    continue;
                }
                if count != expected_go.len() as isize {
                    libc::_exit(125);
                }
                let mut index = 0;
                while index < expected_go.len() {
                    if buffer[index] != expected_go[index] {
                        libc::_exit(125);
                    }
                    index += 1;
                }
                break;
            }
        }
        if enter_late {
            // All descriptors were authenticated before clone; no path or PID
            // is accepted at this gate. CLONE_FS/THREAD/VM are never used.
            for (index, kind) in [
                (3, libc::CLONE_NEWUSER),
                (6, libc::CLONE_NEWIPC),
                (7, libc::CLONE_NEWUTS),
                (8, libc::CLONE_NEWNET),
                (9, libc::CLONE_NEWCGROUP),
                (4, libc::CLONE_NEWNS),
            ] {
                if libc::setns(files[index].as_raw_fd(), kind) != 0 {
                    libc::_exit(125);
                }
            }
            if query_root_credentials() != 0 {
                libc::_exit(125);
            }
        }
        if libc::fchdir(files[2].as_raw_fd()) != 0
            || libc::chroot(c".".as_ptr()) != 0
            || libc::chdir(c"/".as_ptr()) != 0
            || libc::dup2(files[protocol::STDOUT].as_raw_fd(), 1) != 1
            || libc::dup2(files[protocol::STDERR].as_raw_fd(), 2) != 2
        {
            libc::_exit(125);
        }
        // Only the already traced, original parked query reaches this point.
        // Arm both explicit LSM exec attributes while mapped root still has
        // its required capabilities. UID/capability drop follows immediately.
        // A pending label is not accepted as evidence of a completed exec.
        if mac_child::guest_stdin(files[2].as_raw_fd(), deadline_ns) != 0
            || libc::prctl(libc::PR_SET_DUMPABLE, 0, 0, 0, 0) != 0
            || match domain {
                OperationDomain::Query => mac_child::arm_query_mac(deadline_ns),
                OperationDomain::Browser => mac_child::arm_browser_mac(deadline_ns),
                OperationDomain::ContactsRead => mac_child::arm_contacts_read_mac(deadline_ns),
                OperationDomain::LaunchRead => mac_child::arm_launch_read_mac(deadline_ns),
                OperationDomain::LaunchStart => mac_child::arm_launch_start_mac(deadline_ns),
            } != 0
        {
            libc::_exit(125);
        }
        #[repr(C)]
        struct CapHeader {
            version: u32,
            pid: i32,
        }
        #[repr(C)]
        #[derive(Clone, Copy)]
        struct CapData {
            effective: u32,
            permitted: u32,
            inheritable: u32,
        }
        let mut cap_header = CapHeader {
            version: 0x2008_0522,
            pid: 0,
        };
        let caps = [CapData {
            effective: 0,
            permitted: 0,
            inheritable: 0,
        }; 2];
        if libc::syscall(
            libc::SYS_setgroups,
            0_usize,
            std::ptr::null::<libc::gid_t>(),
        ) != 0
            || libc::syscall(libc::SYS_setresgid, 2000_u32, 2000_u32, 2000_u32) != 0
            || libc::syscall(libc::SYS_setresuid, 2000_u32, 2000_u32, 2000_u32) != 0
            || libc::syscall(libc::SYS_capset, &mut cap_header, caps.as_ptr()) != 0
            || libc::prctl(
                libc::PR_CAP_AMBIENT,
                libc::PR_CAP_AMBIENT_CLEAR_ALL,
                0,
                0,
                0,
            ) != 0
            || libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) != 0
            || libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0
        {
            libc::_exit(125);
        }
        let mut poll = [
            libc::pollfd {
                fd: files[0].as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            },
            libc::pollfd {
                fd: files[1].as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            },
        ];
        if libc::poll(poll.as_mut_ptr(), 2, 0) != 0 {
            libc::_exit(125);
        }
        if libc::send(
            files[protocol::GATE].as_raw_fd(),
            armed.as_ptr().cast(),
            armed.len(),
            libc::MSG_NOSIGNAL,
        ) != armed.len() as isize
        {
            libc::_exit(125);
        }
        if libc::syscall(libc::SYS_close_range, 3_u32, u32::MAX, 4_u32) != 0
            || libc::prctl(libc::PR_SET_SECCOMP, 2, filter as *const libc::sock_fprog) != 0
        {
            libc::_exit(125);
        }
        let empty = 0_u64;
        if libc::syscall(
            libc::SYS_rt_sigprocmask,
            libc::SIG_SETMASK,
            &empty,
            std::ptr::null_mut::<u64>(),
            mem::size_of::<u64>(),
        ) != 0
        {
            libc::_exit(125);
        }
        libc::syscall(
            libc::SYS_execveat,
            files[protocol::EXECUTABLE].as_raw_fd(),
            c"".as_ptr(),
            argv,
            envp,
            libc::AT_EMPTY_PATH,
        );
        libc::_exit(125);
    }
}

pub(super) fn query_filter() -> Vec<libc::sock_filter> {
    let ins = |code, jt, jf, k| libc::sock_filter { code, jt, jf, k };
    let deny = 0x0005_0000 | libc::EPERM as u32;
    let mut f = vec![
        ins(0x20, 0, 0, 4),
        ins(0x15, 1, 0, 0xc000_003e),
        ins(0x06, 0, 0, 0x8000_0000),
        ins(0x20, 0, 0, 0),
        ins(0x35, 0, 1, 0x4000_0000),
        ins(0x06, 0, 0, deny),
    ];
    // Binder clients may create native threads. A thread must share VM and
    // handlers and cannot create namespaces or a separately reparented child.
    let required = (libc::CLONE_THREAD | libc::CLONE_VM | libc::CLONE_SIGHAND) as u32;
    let forbidden = (libc::CLONE_NEWUSER
        | libc::CLONE_NEWPID
        | libc::CLONE_NEWNS
        | libc::CLONE_NEWNET
        | libc::CLONE_NEWIPC
        | libc::CLONE_NEWUTS
        | libc::CLONE_NEWCGROUP
        | libc::CLONE_PARENT
        | libc::CLONE_VFORK
        | 0xff) as u32;
    f.extend([
        ins(0x15, 0, 6, libc::SYS_clone as u32),
        ins(0x20, 0, 0, 16),
        ins(0x45, 3, 0, forbidden),
        ins(0x54, 0, 0, required),
        ins(0x15, 0, 1, required),
        ins(0x06, 0, 0, 0x7fff_0000),
        ins(0x06, 0, 0, deny),
    ]);
    // ENOSYS permits libc's normal pthread clone fallback; process creation
    // never falls back because clone without CLONE_THREAD is denied above.
    f.extend([
        ins(0x15, 0, 1, libc::SYS_clone3 as u32),
        ins(0x06, 0, 0, 0x0005_0000 | libc::ENOSYS as u32),
    ]);
    for syscall in [
        libc::SYS_fork,
        libc::SYS_vfork,
        libc::SYS_setns,
        libc::SYS_unshare,
        libc::SYS_mount,
        libc::SYS_umount2,
        libc::SYS_pivot_root,
        libc::SYS_ptrace,
    ] {
        f.extend([ins(0x15, 0, 1, syscall as u32), ins(0x06, 0, 0, deny)]);
    }
    f.push(ins(0x06, 0, 0, 0x7fff_0000));
    f
}
