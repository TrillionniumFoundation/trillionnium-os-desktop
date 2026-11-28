//! Fixed cgroup activation by the same owned PID 1, before Android exec.
//!
//! The inputs are the broker's held, already delegated payload and init FDs.
//! No path, PID, controller list or policy is accepted from the packet. The
//! child moves only itself into `init`, verifies both memberships, and only
//! then enables the five controllers below the unchanged outer hard budget.
use super::{CHILD_FD, Packet, Phase, finish, send};
use std::ffi::CStr;
use std::os::fd::RawFd;

const CGROUP2_MAGIC: libc::c_long = 0x6367_7270;
const CONTROLLERS: u8 = 31;
const CONTROLS: [&CStr; 3] = [
    c"cgroup.procs",
    c"cgroup.threads",
    c"cgroup.subtree_control",
];

/// Kernel controller records have arbitrary order, but no duplicates or extras.
fn controller_mask(bytes: &[u8]) -> Option<u8> {
    let mut mask = 0;
    for word in bytes
        .split(|b| b.is_ascii_whitespace())
        .filter(|s| !s.is_empty())
    {
        let bit = match word {
            b"cpu" => 1,
            b"cpuset" => 2,
            b"memory" => 4,
            b"pids" => 8,
            b"io" => 16,
            _ => return None,
        };
        if mask & bit != 0 {
            return None;
        }
        mask |= bit;
    }
    Some(mask)
}

unsafe fn errno() -> i32 {
    unsafe { *libc::__errno_location() }
}
unsafe fn close(fd: RawFd) {
    unsafe {
        libc::syscall(libc::SYS_close, fd);
    }
}

unsafe fn opened(parent: RawFd, name: &CStr, flags: i32) -> Result<RawFd, i32> {
    let fd = unsafe {
        libc::syscall(
            libc::SYS_openat,
            parent,
            name.as_ptr(),
            flags | libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK,
            0,
        )
    };
    if fd < 0 {
        return Err(unsafe { errno() });
    }
    if fd > i32::MAX as libc::c_long {
        return Err(libc::EPROTO);
    }
    Ok(fd as RawFd)
}

unsafe fn metadata(fd: RawFd) -> Result<libc::stat, i32> {
    let mut st: libc::stat = unsafe { std::mem::zeroed() };
    if unsafe { libc::syscall(libc::SYS_fstat, fd, &mut st) } != 0 {
        return Err(unsafe { errno() });
    }
    Ok(st)
}

unsafe fn filesystem(fd: RawFd) -> Result<(), i32> {
    let mut st: super::empty_root::KernelStatfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::syscall(libc::SYS_fstatfs, fd, &mut st) } != 0 {
        return Err(unsafe { errno() });
    }
    if st.f_type != CGROUP2_MAGIC || st.f_flags as u64 & 15 != 14 {
        return Err(libc::EPROTO);
    }
    Ok(())
}

unsafe fn read_control<'a>(parent: RawFd, name: &CStr, buf: &'a mut [u8]) -> Result<&'a [u8], i32> {
    let fd = unsafe { opened(parent, name, libc::O_RDONLY)? };
    let result = (|| {
        unsafe {
            filesystem(fd)?;
        }
        let st = unsafe { metadata(fd)? };
        if st.st_mode & libc::S_IFMT != libc::S_IFREG {
            return Err(libc::EPROTO);
        }
        let mut used = 0;
        loop {
            if used == buf.len() {
                return Err(libc::E2BIG);
            }
            let n = unsafe {
                libc::syscall(
                    libc::SYS_read,
                    fd,
                    buf[used..].as_mut_ptr(),
                    buf.len() - used,
                )
            };
            if n < 0 {
                return Err(unsafe { errno() });
            }
            if n == 0 {
                break;
            }
            if n as usize > buf.len() - used {
                return Err(libc::EPROTO);
            }
            used += n as usize;
        }
        Ok(used)
    })();
    unsafe {
        close(fd);
    }
    result.map(|used| &buf[..used])
}

unsafe fn exact(parent: RawFd, name: &CStr, wanted: &[u8]) -> Result<(), i32> {
    let mut buf = [0u8; 512];
    if unsafe { read_control(parent, name, &mut buf)? } != wanted {
        return Err(libc::EPROTO);
    }
    Ok(())
}

unsafe fn controllers(parent: RawFd, name: &CStr, wanted: u8) -> Result<(), i32> {
    let mut buf = [0u8; 512];
    if controller_mask(unsafe { read_control(parent, name, &mut buf)? }) != Some(wanted) {
        return Err(libc::EPROTO);
    }
    Ok(())
}

unsafe fn write_control(parent: RawFd, name: &CStr, bytes: &[u8]) -> Result<(), i32> {
    let fd = unsafe { opened(parent, name, libc::O_WRONLY)? };
    let result = (|| {
        unsafe {
            filesystem(fd)?;
        }
        let st = unsafe { metadata(fd)? };
        if st.st_mode & libc::S_IFMT != libc::S_IFREG {
            return Err(libc::EPROTO);
        }
        let n = unsafe { libc::syscall(libc::SYS_write, fd, bytes.as_ptr(), bytes.len()) };
        if n < 0 {
            return Err(unsafe { errno() });
        }
        if n as usize != bytes.len() {
            return Err(libc::EIO);
        }
        Ok(())
    })();
    unsafe {
        close(fd);
    }
    result
}

unsafe fn owner_mode(fd: RawFd, directory: bool) -> Result<(), i32> {
    let st = unsafe { metadata(fd)? };
    let mode = if directory {
        libc::S_IFDIR | 0o775
    } else {
        libc::S_IFREG | 0o664
    };
    if st.st_mode != mode || st.st_uid != 0 || st.st_gid != 1000 {
        return Err(libc::EPROTO);
    }
    unsafe { filesystem(fd) }
}

unsafe fn current_path(wanted: &[u8]) -> Result<(), i32> {
    let fd = unsafe { opened(libc::AT_FDCWD, c"/proc/1/cgroup", libc::O_RDONLY)? };
    let mut buf = [0u8; 64];
    let n = unsafe { libc::syscall(libc::SYS_read, fd, buf.as_mut_ptr(), buf.len()) };
    let result = if n < 0 {
        Err(unsafe { errno() })
    } else if n as usize != wanted.len() || &buf[..n as usize] != wanted {
        Err(libc::EPROTO)
    } else {
        let end = unsafe { libc::syscall(libc::SYS_read, fd, buf.as_mut_ptr(), buf.len()) };
        if end < 0 {
            Err(unsafe { errno() })
        } else if end != 0 {
            Err(libc::EPROTO)
        } else {
            Ok(())
        }
    };
    unsafe {
        close(fd);
    }
    result
}

/// The same owned PID1 carries this private, descriptor-derived value across
/// setup phases. Construction is restricted to successful cgroup activation.
pub(super) struct ActivatedPayload {
    device: libc::dev_t,
    inode: libc::ino_t,
}

/// Rights are confined to an anonymous mount of the already activated payload.
/// No path, mount option, or namespace descriptor comes from a caller.
pub(super) struct DetachedPayloadMount {
    fd: ProjectionFd,
}

impl DetachedPayloadMount {
    pub(super) fn descriptor(&self) -> RawFd {
        self.fd.0
    }
}

struct ProjectionFd(RawFd);

impl Drop for ProjectionFd {
    fn drop(&mut self) {
        unsafe { close(self.0) };
    }
}

fn held_projection_fd(raw: libc::c_long) -> Result<ProjectionFd, i32> {
    if raw < 0 {
        return Err(unsafe { errno() });
    }
    let fd = RawFd::try_from(raw).map_err(|_| libc::EPROTO)?;
    Ok(ProjectionFd(fd))
}

impl ActivatedPayload {
    /// The kernel roots a new cgroup2 view at the caller's cgroup namespace
    /// root. Check the same actual PID1 path again before CREATE could run.
    /// No input calls for a new/reconfigured initial-namespace mount.
    pub(super) unsafe fn stage_detached(&self) -> Result<DetachedPayloadMount, i32> {
        if unsafe { libc::syscall(libc::SYS_getpid) } != 1
            || unsafe { libc::syscall(libc::SYS_getppid) } != 0
            || unsafe { libc::syscall(libc::SYS_geteuid) } != 0
        {
            return Err(libc::EPERM);
        }
        unsafe { current_path(b"0::/init\n")? };
        const FSOPEN_CLOEXEC: u32 = 1;
        const FSCONFIG_CMD_CREATE: u32 = 6;
        const FSMOUNT_CLOEXEC: u32 = 1;
        const RESTRICTED_MOUNT: u32 = 2 | 4 | 8; // nosuid, nodev, noexec
        let context = held_projection_fd(unsafe {
            libc::syscall(libc::SYS_fsopen, c"cgroup2".as_ptr(), FSOPEN_CLOEXEC)
        })?;
        if unsafe {
            libc::syscall(
                libc::SYS_fsconfig,
                context.0,
                FSCONFIG_CMD_CREATE,
                std::ptr::null::<libc::c_char>(),
                std::ptr::null::<libc::c_void>(),
                0_i32,
            )
        } != 0
        {
            return Err(unsafe { errno() });
        }
        let mount = held_projection_fd(unsafe {
            libc::syscall(libc::SYS_fsmount, context.0, FSMOUNT_CLOEXEC, RESTRICTED_MOUNT)
        })?;
        drop(context);
        unsafe { self.verify_projection(mount.0)? };
        Ok(DetachedPayloadMount { fd: mount })
    }

    pub(super) unsafe fn verify_projection(&self, mounted: RawFd) -> Result<(), i32> {
        unsafe { owner_mode(mounted, true)? };
        let identity = unsafe { metadata(mounted)? };
        if identity.st_dev != self.device || identity.st_ino != self.inode {
            return Err(libc::EPROTO);
        }
        unsafe { current_path(b"0::/init\n") }
    }
}

/// The descriptor is consumed only by this fixed raw path; errors leave all
/// existing objects for the original parent owner to retire after PIDFD reap.
unsafe fn activate(payload: RawFd, init: RawFd) -> Result<ActivatedPayload, i32> {
    if unsafe { libc::syscall(libc::SYS_getpid) } != 1
        || unsafe { libc::syscall(libc::SYS_getppid) } != 0
        || unsafe { libc::syscall(libc::SYS_geteuid) } != 0
        || unsafe { libc::syscall(libc::SYS_getegid) } != 0
    {
        return Err(libc::EPERM);
    }
    unsafe {
        owner_mode(payload, true)?;
        current_path(b"0::/\n")?;
        exact(payload, c"cgroup.type", b"domain\n")?;
        exact(payload, c"cgroup.procs", b"1\n")?;
        exact(payload, c"cgroup.threads", b"1\n")?;
        controllers(payload, c"cgroup.controllers", CONTROLLERS)?;
        controllers(payload, c"cgroup.subtree_control", 0)?;
    }
    // The initial-namespace broker creates and delegates this exact leaf.
    // Guest capabilities never authorize chown on the initial-owned cgroupfs.
    let named = unsafe { opened(payload, c"init", libc::O_RDONLY | libc::O_DIRECTORY)? };
    let named_stat = unsafe { metadata(named) };
    unsafe {
        close(named);
    }
    let named_stat = named_stat?;
    let root_stat = unsafe { metadata(payload)? };
    let init_stat = unsafe { metadata(init)? };
    if named_stat.st_dev != init_stat.st_dev
        || named_stat.st_ino != init_stat.st_ino
        || root_stat.st_dev != init_stat.st_dev
        || root_stat.st_ino == init_stat.st_ino
    {
        return Err(libc::EPROTO);
    }
    let result = (|| {
        unsafe {
            owner_mode(init, true)?;
            exact(init, c"cgroup.type", b"domain\n")?;
            exact(init, c"cgroup.procs", b"")?;
            controllers(init, c"cgroup.subtree_control", 0)?;
        }
        for dir in [payload, init] {
            for name in CONTROLS {
                let fd = unsafe { opened(dir, name, libc::O_RDONLY)? };
                let result = unsafe { owner_mode(fd, false) };
                unsafe {
                    close(fd);
                }
                result?;
            }
        }
        unsafe {
            write_control(init, c"cgroup.procs", b"1\n")?;
            // A successful write alone is insufficient. Both actual task
            // lists and the PID1's cgroup-namespace view precede activation.
            exact(payload, c"cgroup.procs", b"")?;
            exact(payload, c"cgroup.threads", b"")?;
            exact(init, c"cgroup.procs", b"1\n")?;
            exact(init, c"cgroup.threads", b"1\n")?;
            current_path(b"0::/init\n")?;
            write_control(
                payload,
                c"cgroup.subtree_control",
                b"+cpu +cpuset +io +memory +pids\n",
            )?;
            controllers(payload, c"cgroup.subtree_control", CONTROLLERS)?;
            controllers(init, c"cgroup.controllers", CONTROLLERS)?;
            controllers(init, c"cgroup.subtree_control", 0)?;
            exact(payload, c"cgroup.procs", b"")?;
            exact(init, c"cgroup.procs", b"1\n")?;
            current_path(b"0::/init\n")?;
            owner_mode(payload, true)?;
            owner_mode(init, true)?;
        }
        Ok(ActivatedPayload {
            device: root_stat.st_dev,
            inode: root_stat.st_ino,
        })
    })();
    result
}

unsafe fn discard_rights(message: &libc::msghdr) {
    let mut header = unsafe { libc::CMSG_FIRSTHDR(message) };
    while !header.is_null() {
        let h = unsafe { &*header };
        let base = unsafe { libc::CMSG_LEN(0) } as usize;
        if h.cmsg_level == libc::SOL_SOCKET && h.cmsg_type == libc::SCM_RIGHTS && h.cmsg_len >= base
        {
            let count = (h.cmsg_len - base) / std::mem::size_of::<RawFd>();
            for index in 0..count {
                let fd = unsafe {
                    std::ptr::read_unaligned(libc::CMSG_DATA(header).cast::<RawFd>().add(index))
                };
                unsafe {
                    close(fd);
                }
            }
        }
        header = unsafe { libc::CMSG_NXTHDR(message, header) };
    }
}

/// The production caller always supplies the fixed control FD 3. The local
/// argument also permits real SCM_RIGHTS rejection tests without closing the
/// test runner's unrelated descriptors or creating a test-only packet parser.
unsafe fn receive_from(socket: RawFd, nonce: [u8; 16], parent_pid: u32) -> Result<[RawFd; 2], i32> {
    let mut packet = Packet::zeroed();
    let mut iov = libc::iovec {
        iov_base: (&mut packet as *mut Packet).cast(),
        iov_len: std::mem::size_of::<Packet>(),
    };
    let mut control = [0_usize; 16];
    let mut msg: libc::msghdr = unsafe { std::mem::zeroed() };
    msg.msg_iov = &mut iov;
    msg.msg_iovlen = 1;
    msg.msg_control = control.as_mut_ptr().cast();
    msg.msg_controllen = std::mem::size_of_val(&control);
    let n = unsafe { libc::syscall(libc::SYS_recvmsg, socket, &mut msg, libc::MSG_CMSG_CLOEXEC) };
    if n == 0 {
        unsafe { finish(0) }
    }
    if n < 0 {
        return Err(unsafe { errno() });
    }
    let parsed = (|| {
        if n != std::mem::size_of::<Packet>() as libc::c_long
            || msg.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) != 0
            || !packet.matches(nonce, parent_pid)
            || packet.errno != 0
        {
            return Err(libc::EPROTO);
        }
        let header = unsafe { libc::CMSG_FIRSTHDR(&msg) };
        if packet.phase == Phase::Stop as u32 && header.is_null() {
            unsafe { finish(0) }
        }
        if packet.phase != Phase::PrepareCgroup as u32 || header.is_null() {
            return Err(libc::EPROTO);
        }
        let h = unsafe { &*header };
        if h.cmsg_level != libc::SOL_SOCKET
            || h.cmsg_type != libc::SCM_RIGHTS
            || h.cmsg_len != unsafe { libc::CMSG_LEN(8) } as usize
            || !unsafe { libc::CMSG_NXTHDR(&msg, header) }.is_null()
        {
            return Err(libc::EPROTO);
        }
        let data = unsafe { libc::CMSG_DATA(header).cast::<i32>() };
        let fds = unsafe {
            [
                std::ptr::read_unaligned(data),
                std::ptr::read_unaligned(data.add(1)),
            ]
        };
        if fds.iter().any(|fd| *fd < 0 || *fd == socket) || fds[0] == fds[1] {
            return Err(libc::EPROTO);
        }
        Ok(fds)
    })();
    if parsed.is_err() {
        unsafe {
            discard_rights(&msg);
        }
    }
    parsed
}

pub(super) unsafe fn run(nonce: [u8; 16], parent_pid: u32) -> ActivatedPayload {
    let result = (|| {
        let [payload, init] = unsafe { receive_from(CHILD_FD, nonce, parent_pid)? };
        let result = unsafe { activate(payload, init) };
        unsafe {
            close(payload);
            close(init);
        }
        let activated = result?;
        // No ancestor cgroup descriptor reaches init or a subsequent phase.
        if unsafe { libc::syscall(libc::SYS_close_range, 4_u32, u32::MAX, 0) } != 0 {
            return Err(unsafe { errno() });
        }
        for fd in 0..3 {
            unsafe {
                close(fd);
            }
        }
        Ok(activated)
    })();
    match result {
        Ok(activated) => unsafe {
            send(nonce, Phase::CgroupReady, 0, 1);
            activated
        },
        Err(error) => unsafe {
            // recvmsg may have installed descriptors even in a malformed or
            // truncated control record. Close the entire fixed range before
            // reporting failure, including descriptors not parsed above.
            if libc::syscall(libc::SYS_close_range, 4_u32, u32::MAX, 0) != 0 {
                finish(127);
            }
            for fd in 0..3 {
                close(fd);
            }
            send(nonce, Phase::Failed, error, 1);
            finish(127)
        },
    }
}

#[cfg(test)]
pub(super) unsafe fn private_control(nonce: [u8; 16], parent_pid: u32) -> ! {
    // This test-only branch needs no Android image or Binder fixture. Its proc
    // mount belongs to the same new PID/user/mount namespaces as production.
    // The host's proc mount is unchanged; no execution admission can use this.
    if unsafe {
        libc::syscall(
            libc::SYS_mount,
            c"proc".as_ptr(),
            c"/proc".as_ptr(),
            c"proc".as_ptr(),
            libc::MS_NOSUID | libc::MS_NODEV | libc::MS_NOEXEC,
            std::ptr::null::<u8>(),
        )
    } != 0
    {
        unsafe {
            send(nonce, Phase::Failed, errno(), 1);
            finish(127)
        }
    }
    unsafe {
        run(nonce, parent_pid);
        super::receive(nonce, parent_pid, Phase::Stop);
        finish(0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};

    fn send_record(socket: RawFd, packet: &Packet, rights: &[RawFd]) {
        let mut iov = libc::iovec {
            iov_base: (packet as *const Packet).cast_mut().cast(),
            iov_len: std::mem::size_of::<Packet>(),
        };
        let mut ancillary = [0_usize; 128];
        let mut msg: libc::msghdr = unsafe { std::mem::zeroed() };
        msg.msg_iov = &mut iov;
        msg.msg_iovlen = 1;
        if !rights.is_empty() {
            msg.msg_control = ancillary.as_mut_ptr().cast();
            msg.msg_controllen =
                unsafe { libc::CMSG_SPACE(std::mem::size_of_val(rights) as u32) } as usize;
            assert!(msg.msg_controllen <= std::mem::size_of_val(&ancillary));
            let h = unsafe { libc::CMSG_FIRSTHDR(&msg) };
            unsafe {
                (*h).cmsg_level = libc::SOL_SOCKET;
                (*h).cmsg_type = libc::SCM_RIGHTS;
                (*h).cmsg_len = libc::CMSG_LEN(std::mem::size_of_val(rights) as u32) as usize;
                for (index, fd) in rights.iter().enumerate() {
                    std::ptr::write_unaligned(libc::CMSG_DATA(h).cast::<RawFd>().add(index), *fd);
                }
            }
        }
        assert_eq!(
            unsafe { libc::sendmsg(socket, &msg, libc::MSG_NOSIGNAL | libc::MSG_DONTWAIT) },
            std::mem::size_of::<Packet>() as isize
        );
    }

    #[test]
    fn cgroup_activation_protocol_rejects_nonce_phase_and_fd_counts_without_leaks() {
        let mut raw = [-1_i32; 2];
        assert_eq!(
            unsafe {
                libc::socketpair(
                    libc::AF_UNIX,
                    libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC,
                    0,
                    raw.as_mut_ptr(),
                )
            },
            0
        );
        let receiver = unsafe { OwnedFd::from_raw_fd(raw[0]) };
        let sender = unsafe { OwnedFd::from_raw_fd(raw[1]) };
        let input = std::fs::File::open("/dev/null").unwrap();
        let nonce = [0x44; 16];
        let parent = unsafe { libc::getpid() } as u32;
        let packet = Packet::new(nonce, Phase::PrepareCgroup, 0, parent);
        let count = || std::fs::read_dir("/proc/self/fd").unwrap().count();
        let before = count();
        send_record(sender.as_raw_fd(), &packet, &[input.as_raw_fd(); 2]);
        let received = unsafe { receive_from(receiver.as_raw_fd(), nonce, parent) }.unwrap();
        assert_ne!(received[0], received[1]);
        for fd in received {
            assert_ne!(
                unsafe { libc::fcntl(fd, libc::F_GETFD) } & libc::FD_CLOEXEC,
                0
            );
            unsafe {
                close(fd);
            }
        }
        assert_eq!(count(), before);
        for fd_count in [0, 1, 3, 96] {
            send_record(
                sender.as_raw_fd(),
                &packet,
                &vec![input.as_raw_fd(); fd_count],
            );
            assert_eq!(
                unsafe { receive_from(receiver.as_raw_fd(), nonce, parent) },
                Err(libc::EPROTO)
            );
            assert_eq!(count(), before, "rights count {fd_count}");
        }
        for rejected in [
            Packet::new([0x45; 16], Phase::PrepareCgroup, 0, parent),
            Packet::new(nonce, Phase::MountRuntime, 0, parent),
            Packet::new(nonce, Phase::PrepareCgroup, 0, parent + 1),
            Packet::new(nonce, Phase::PrepareCgroup, libc::EPERM, parent),
            Packet::new(nonce, Phase::Stop, 0, parent),
        ] {
            send_record(sender.as_raw_fd(), &rejected, &[input.as_raw_fd(); 2]);
            assert_eq!(
                unsafe { receive_from(receiver.as_raw_fd(), nonce, parent) },
                Err(libc::EPROTO)
            );
            assert_eq!(count(), before);
        }
    }

    #[test]
    fn cgroup_activation_controller_inventory_rejects_missing_duplicate_and_unknown() {
        assert_eq!(
            controller_mask(b"cpuset cpu io memory pids\n"),
            Some(CONTROLLERS)
        );
        assert_eq!(
            controller_mask(b"pids io memory cpu cpuset\n"),
            Some(CONTROLLERS)
        );
        assert_eq!(controller_mask(b"cpu cpuset memory pids\n"), Some(15));
        assert_eq!(controller_mask(b"cpu memory pids\n"), Some(13));
        assert_eq!(controller_mask(b"cpu cpu memory pids\n"), None);
        assert_eq!(
            controller_mask(b"cpu cpuset io memory pids hugetlb\n"),
            None
        );
        assert_eq!(controller_mask(b"cpu\0 cpuset memory pids\n"), None);
        assert_eq!(controller_mask(b"\n"), Some(0));
    }

    #[test]
    fn cgroup_activation_refuses_ordinary_process_before_descriptor_use() {
        assert_ne!(unsafe { libc::getpid() }, 1);
        assert_eq!(unsafe { activate(-1, -1) }.err(), Some(libc::EPERM));
        let anchor = ActivatedPayload { device: 0, inode: 0 };
        assert_eq!(unsafe { anchor.stage_detached() }.err(), Some(libc::EPERM));
    }

    #[test]
    fn cgroup_activation_rejects_regular_directory_as_kernel_cgroup() {
        let dir = tempfile::tempdir().unwrap();
        let held = std::fs::File::open(dir.path()).unwrap();
        assert_eq!(unsafe { filesystem(held.as_raw_fd()) }, Err(libc::EPROTO));
    }
}
