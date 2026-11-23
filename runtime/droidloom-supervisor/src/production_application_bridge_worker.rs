//! Fixed connection in the original broker-owned fresh worker; no Android
//! exec, query fork, caller path or Ready construction occurs in this branch.
use super::*;
use std::io::Read;
use std::os::unix::fs::OpenOptionsExt;

const SO_PASSPIDFD: i32 = 76; // selected Linux UAPI

fn before(files: &[File], deadline: Instant) -> Result<()> {
    require(
        Instant::now() < deadline,
        "bridge connector absolute deadline",
    )?;
    alive(&files[0])?;
    alive(&files[1])
}

fn label(path: &str, expected: &[u8]) -> Result<()> {
    let file = std::fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(path)?;
    let mut fs: libc::statfs = unsafe { mem::zeroed() };
    if unsafe { libc::fstatfs(file.as_raw_fd(), &mut fs) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        fs.f_type == 0x9fa0,
        "bridge worker attributes are not procfs",
    )?;
    let mut body = Vec::new();
    file.take(257).read_to_end(&mut body)?;
    require(
        body.len() <= 256 && (body == expected || body.strip_suffix(b"\0") == Some(expected)),
        "bridge worker must retain its original broker MAC context",
    )
}

fn broker_labels() -> Result<()> {
    // Fixed own-task attributes, never pending labels or a requested transition.
    label("/proc/self/attr/current", b"u:r:droidloom_broker:s0")?;
    label(
        "/proc/self/attr/apparmor/current",
        b"droidloom-production-broker (enforce)\n",
    )
}

fn drop_to_system() -> Result<()> {
    #[repr(C)]
    struct Header {
        version: u32,
        pid: i32,
    }
    #[repr(C)]
    #[derive(Clone, Copy)]
    struct Data {
        effective: u32,
        permitted: u32,
        inheritable: u32,
    }
    let mut header = Header {
        version: 0x2008_0522,
        pid: 0,
    };
    let caps = [Data {
        effective: 0,
        permitted: 0,
        inheritable: 0,
    }; 2];
    if unsafe {
        libc::syscall(
            libc::SYS_setgroups,
            0_usize,
            std::ptr::null::<libc::gid_t>(),
        )
    } != 0
        || unsafe { libc::syscall(libc::SYS_setresgid, 1000_u32, 1000_u32, 1000_u32) } != 0
        || unsafe { libc::syscall(libc::SYS_setresuid, 1000_u32, 1000_u32, 1000_u32) } != 0
        || unsafe { libc::syscall(libc::SYS_capset, &mut header, caps.as_ptr()) } != 0
        || unsafe {
            libc::prctl(
                libc::PR_CAP_AMBIENT,
                libc::PR_CAP_AMBIENT_CLEAR_ALL,
                0,
                0,
                0,
            )
        } != 0
        || unsafe { libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) } != 0
        || unsafe { libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) } != 0
        || unsafe { libc::prctl(libc::PR_SET_DUMPABLE, 0, 0, 0, 0) } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    require(
        unsafe { libc::getuid() } == 1000
            && unsafe { libc::geteuid() } == 1000
            && unsafe { libc::getgid() } == 1000
            && unsafe { libc::getegid() } == 1000
            && unsafe { libc::getgroups(0, std::ptr::null_mut()) } == 0,
        "bridge connector credentials differ",
    )
}

fn fixed_filter() -> Vec<libc::sock_filter> {
    let ins = |code, jt, jf, k| libc::sock_filter { code, jt, jf, k };
    let deny = 0x0005_0000 | libc::EPERM as u32;
    let mut filter = vec![
        ins(0x20, 0, 0, 4),
        ins(0x15, 1, 0, 0xc000_003e),
        ins(0x06, 0, 0, 0x8000_0000),
        ins(0x20, 0, 0, 0),
        ins(0x35, 0, 1, 0x4000_0000),
        ins(0x06, 0, 0, deny),
    ];
    // Unlike cmd's Binder thread allowance, this one-shot connector cannot
    // create even a thread. There is no execution or path-open continuation.
    for call in [
        libc::SYS_clone,
        libc::SYS_clone3,
        libc::SYS_fork,
        libc::SYS_vfork,
        libc::SYS_execve,
        libc::SYS_execveat,
        libc::SYS_setns,
        libc::SYS_unshare,
        libc::SYS_mount,
        libc::SYS_umount2,
        libc::SYS_pivot_root,
        libc::SYS_ptrace,
        libc::SYS_open,
        libc::SYS_openat,
        libc::SYS_openat2,
        libc::SYS_creat,
    ] {
        filter.extend([ins(0x15, 0, 1, call as u32), ins(0x06, 0, 0, deny)]);
    }
    filter.push(ins(0x06, 0, 0, 0x7fff_0000));
    filter
}

pub(super) fn connect(
    parent: libc::pid_t,
    files: &[File],
    nonce: [u8; 16],
    deadline: Instant,
) -> Result<()> {
    require(files.len() == 11, "fixed bridge descriptor count differs")?;
    let init = validate_owner_descriptors(files, parent)?;
    before(files, deadline)?;
    let endpoint = files[10].metadata()?;
    require(
        endpoint.mode() == libc::S_IFSOCK | 0o660
            && endpoint.nlink() == 1
            && endpoint.uid()
                == init
                    .ruid
                    .checked_add(1000)
                    .ok_or_else(|| reject("bridge UID overflow"))?
            && endpoint.gid()
                == init
                    .rgid
                    .checked_add(1000)
                    .ok_or_else(|| reject("bridge GID overflow"))?,
        "fixed task-control socket metadata differs",
    )?;
    let flags = unsafe { libc::fcntl(files[10].as_raw_fd(), libc::F_GETFL) };
    require(
        flags >= 0 && flags & libc::O_PATH != 0,
        "bridge endpoint is not the held socket inode",
    )?;
    broker_labels()?;
    // The proc magic link resolves the received O_PATH inode itself. Its FD
    // number is private custody, not a pathname supplied in a request. The
    // fresh worker retains its host root solely for this proc lookup; it does
    // not chroot, execute a program, or export that root to the parent/client.
    let path =
        CString::new(format!("/proc/self/fd/{}", files[10].as_raw_fd())).map_err(external)?;
    let mut address: libc::sockaddr_un = unsafe { mem::zeroed() };
    address.sun_family = libc::AF_UNIX as libc::sa_family_t;
    require(
        path.as_bytes_with_nul().len() <= address.sun_path.len(),
        "bridge socket address bound",
    )?;
    for (out, byte) in address.sun_path.iter_mut().zip(path.as_bytes_with_nul()) {
        *out = *byte as libc::c_char;
    }
    for (index, kind) in [
        (3, libc::CLONE_NEWUSER),
        (6, libc::CLONE_NEWIPC),
        (7, libc::CLONE_NEWUTS),
        (8, libc::CLONE_NEWNET),
        (9, libc::CLONE_NEWCGROUP),
        (4, libc::CLONE_NEWNS),
    ] {
        if unsafe { libc::setns(files[index].as_raw_fd(), kind) } != 0 {
            return Err(io::Error::last_os_error().into());
        }
    }
    // PID setns would affect only a future child. This branch creates none;
    // the original host broker remains the actual PIDFD wait owner.
    drop_to_system()?;
    before(files, deadline)?;
    broker_labels()?;
    let current = files[10].metadata()?;
    require(
        current.dev() == endpoint.dev()
            && current.ino() == endpoint.ino()
            && current.mode() == endpoint.mode()
            && current.nlink() == 1
            && current.uid() == 1000
            && current.gid() == 1000,
        "bridge endpoint changed during namespace entry",
    )?;
    let raw = unsafe {
        libc::socket(
            libc::AF_UNIX,
            libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
            0,
        )
    };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let socket = unsafe { OwnedFd::from_raw_fd(raw) };
    for option in [libc::SO_PASSCRED, SO_PASSPIDFD] {
        let enabled = 1_i32;
        if unsafe {
            libc::setsockopt(
                socket.as_raw_fd(),
                libc::SOL_SOCKET,
                option,
                (&enabled as *const i32).cast(),
                mem::size_of::<i32>() as libc::socklen_t,
            )
        } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
    }
    let mut instructions = fixed_filter();
    let program = libc::sock_fprog {
        len: instructions.len() as u16,
        filter: instructions.as_mut_ptr(),
    };
    if unsafe { libc::prctl(libc::PR_SET_SECCOMP, 2, &program as *const libc::sock_fprog) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    before(files, deadline)?;
    let result = unsafe {
        libc::connect(
            socket.as_raw_fd(),
            (&address as *const libc::sockaddr_un).cast(),
            (mem::offset_of!(libc::sockaddr_un, sun_path) + path.as_bytes_with_nul().len())
                as libc::socklen_t,
        )
    };
    if result != 0 {
        let error = io::Error::last_os_error();
        // A full backlog is a failure, not a new connection attempt.
        if error.raw_os_error() != Some(libc::EINPROGRESS) {
            return Err(error.into());
        }
        loop {
            before(files, deadline)?;
            let mut poll = [
                libc::pollfd {
                    fd: socket.as_raw_fd(),
                    events: libc::POLLOUT,
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
            let count = unsafe {
                libc::poll(
                    poll.as_mut_ptr(),
                    3,
                    deadline
                        .saturating_duration_since(Instant::now())
                        .as_millis()
                        .clamp(1, 20) as i32,
                )
            };
            if count < 0 {
                let error = io::Error::last_os_error();
                if error.kind() == io::ErrorKind::Interrupted {
                    continue;
                }
                return Err(error.into());
            }
            before(files, deadline)?;
            require(
                poll[1].revents == 0 && poll[2].revents == 0,
                "bridge original owner exited",
            )?;
            if poll[0].revents != 0 {
                let mut error = 0_i32;
                let mut len = mem::size_of::<i32>() as libc::socklen_t;
                if unsafe {
                    libc::getsockopt(
                        socket.as_raw_fd(),
                        libc::SOL_SOCKET,
                        libc::SO_ERROR,
                        (&mut error as *mut i32).cast(),
                        &mut len,
                    )
                } != 0
                {
                    return Err(io::Error::last_os_error().into());
                }
                require(
                    len as usize == mem::size_of::<i32>()
                        && error == 0
                        && poll[0].revents & (libc::POLLNVAL | libc::POLLERR | libc::POLLHUP) == 0,
                    "bridge connection did not complete",
                )?;
                break;
            }
        }
    }
    before(files, deadline)?;
    protocol::send(
        3,
        &Message::BridgeConnected { nonce },
        &[socket.as_raw_fd()],
        deadline,
    )?;
    before(files, deadline)
}
