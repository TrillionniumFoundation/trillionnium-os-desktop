//! Raw, allocation-free child side. It never calls caller-provided code.
//!
//! Everything after clone3 in the child uses fixed stack values and libc's
//! direct syscall entry only. No allocator, mutex, std I/O, unwinding, external
//! executable or inherited Rust destructor is used.

use std::io;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};

use super::{NamespaceError, Result};

const MAGIC: u64 = 0x444c_4e53_4252_4b31;
const CHILD_FD: RawFd = 3;

#[path = "production_namespace_mount_child.rs"]
mod empty_root;
#[path = "production_namespace_device_child.rs"]
mod private_dev;

#[derive(Clone, Copy)]
#[repr(u32)]
pub(super) enum Phase {
    Created = 1,
    Enter = 2,
    Ready = 3,
    Go = 4,
    Mapped = 5,
    Stop = 6,
    PrepareTree = 13,
    TreeSpawned = 14,
    TreeReady = 15,
    MountEmptyBase = 16,
    EmptyRootReady = 17,
    MountPrivateDev = 20,
    PrivateDevReady = 21,
    #[cfg(test)]
    ProbePrivateDev = 22,
    #[cfg(test)]
    PrivateDevChecked = 23,
    #[cfg(test)]
    ProbeEmptyRoot = 18,
    #[cfg(test)]
    EmptyRootChecked = 19,
    Failed = 7,
    #[cfg(test)]
    Parked = 8,
    #[cfg(test)]
    ProbeGroups = 9,
    #[cfg(test)]
    GroupsSet = 10,
    #[cfg(test)]
    ClearGroups = 11,
    #[cfg(test)]
    GroupsCleared = 12,
}

#[derive(Clone, Copy)]
#[repr(u32)]
pub(super) enum Mode {
    UserNamespace = 0,
    #[cfg(test)]
    ParkOnly = 1,
    #[cfg(test)]
    ExitBeforeCreated = 2,
    #[cfg(test)]
    WrongNonce = 3,
    #[cfg(test)]
    WithholdReady = 4,
    #[cfg(test)]
    GroupControl = 5,
    #[cfg(test)]
    TreeWrongReady = 6,
    #[cfg(test)]
    EmptyRootControl = 7,
    #[cfg(test)]
    DeviceRootControl = 8,
}

#[derive(Clone, Copy)]
#[repr(C)]
pub(super) struct Packet {
    magic: u64,
    nonce: [u8; 16],
    pub(super) phase: u32,
    pub(super) errno: i32,
    pid: u32,
    reserved: u32,
}

const _: () = assert!(std::mem::size_of::<Packet>() == 40);

impl Packet {
    pub(super) const fn new(nonce: [u8; 16], phase: Phase, errno: i32, pid: u32) -> Self {
        Self {
            magic: MAGIC,
            nonce,
            phase: phase as u32,
            errno,
            pid,
            reserved: 0,
        }
    }
    pub(super) const fn zeroed() -> Self {
        Self {
            magic: 0,
            nonce: [0; 16],
            phase: 0,
            errno: 0,
            pid: 0,
            reserved: 0,
        }
    }
    pub(super) fn matches(&self, nonce: [u8; 16], pid: u32) -> bool {
        self.magic == MAGIC && self.nonce == nonce && self.pid == pid && self.reserved == 0
    }
}

#[repr(C)]
#[derive(Default)]
struct CloneArgs {
    flags: u64,
    pidfd: u64,
    child_tid: u64,
    parent_tid: u64,
    exit_signal: u64,
    stack: u64,
    stack_size: u64,
    tls: u64,
    set_tid: u64,
    set_tid_size: u64,
    cgroup: u64,
}

type Spawned = (u32, OwnedFd, OwnedFd, u32, libc::pid_t, [u8; 16]);

pub(super) fn spawn(mode: Mode) -> Result<Spawned> {
    // Do not permit inherited SIGCHLD auto-reaping: exit must be observed and
    // reaped through the exact held pidfd, not inferred from missing proc paths.
    let mut action: libc::sigaction = unsafe { std::mem::zeroed() };
    // SAFETY: read-only query, writable initialized action.
    if unsafe { libc::sigaction(libc::SIGCHLD, std::ptr::null(), &mut action) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    if action.sa_sigaction != libc::SIG_DFL || action.sa_flags & libc::SA_NOCLDWAIT != 0 {
        return Err(NamespaceError::Rejected(
            "SIGCHLD auto-reaping prevents owned exit proof",
        ));
    }
    let mut sockets = [-1_i32; 2];
    // SAFETY: two writable fd slots; no external socket/address is contacted.
    if unsafe {
        libc::socketpair(
            libc::AF_UNIX,
            libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC,
            0,
            sockets.as_mut_ptr(),
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    // SAFETY: successful socketpair transfers both newly owned descriptors.
    let parent = unsafe { OwnedFd::from_raw_fd(sockets[0]) };
    let child = unsafe { OwnedFd::from_raw_fd(sockets[1]) };
    let passcred: libc::c_int = 1;
    // SAFETY: a scalar SO_PASSCRED value on the private parent endpoint.
    if unsafe {
        libc::setsockopt(
            parent.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PASSCRED,
            (&passcred as *const libc::c_int).cast(),
            std::mem::size_of_val(&passcred) as libc::socklen_t,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    let mut nonce = [0_u8; 16];
    let mut got = 0;
    while got < nonce.len() {
        // SAFETY: remaining writable nonce slice; no user-provided pointer.
        let rc = unsafe {
            libc::syscall(
                libc::SYS_getrandom,
                nonce.as_mut_ptr().add(got),
                nonce.len() - got,
                0,
            )
        };
        if rc < 0 {
            let e = io::Error::last_os_error();
            if e.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(e.into());
        }
        if rc == 0 {
            return Err(NamespaceError::Rejected(
                "getrandom returned no nonce bytes",
            ));
        }
        got += rc as usize;
    }
    // SAFETY: read-only identity syscalls.
    let parent_pid = unsafe { libc::getpid() };
    let creator_tid = unsafe { libc::syscall(libc::SYS_gettid) } as libc::pid_t;
    if parent_pid <= 1 || creator_tid <= 1 {
        return Err(NamespaceError::Rejected(
            "namespace broker cannot be host PID 1",
        ));
    }
    let mask = SignalMask::block()?;
    let mut pidfd = -1_i32;
    let args = CloneArgs {
        flags: libc::CLONE_PIDFD as u64,
        pidfd: (&mut pidfd as *mut i32) as u64,
        exit_signal: libc::SIGCHLD as u64,
        ..CloneArgs::default()
    };
    // SAFETY: clone3 copies the process without CLONE_VM/FILES/THREAD. The
    // child branches immediately into a fixed ! function with no destructors.
    // CLONE_PIDFD returns ownership atomically; there is no pidfd_open fallback.
    let pid = unsafe { libc::syscall(libc::SYS_clone3, &args, std::mem::size_of::<CloneArgs>()) };
    if pid == 0 {
        // SAFETY: only the newly cloned child reaches this no-return function.
        unsafe {
            child_main(child.as_raw_fd(), parent_pid as u32, nonce, mode);
        }
    }
    if pid < 0 {
        return Err(io::Error::last_os_error().into());
    }
    // Successful CLONE_PIDFD guarantees this descriptor. No separate PID
    // lookup is ever used to acquire lifecycle authority.
    if pidfd < 0 || pid > i32::MAX as libc::c_long {
        // Closing both socket endpoints makes the fixed child exit. Do not
        // signal an unbound numeric PID, even on a broken syscall contract.
        return Err(NamespaceError::Rejected(
            "clone3 did not return its promised pidfd",
        ));
    }
    // SAFETY: newly acquired atomic clone3 pidfd.
    let owned_pidfd = unsafe { OwnedFd::from_raw_fd(pidfd) };
    drop(child);
    drop(mask); // restore only this parent thread's original signal mask
    Ok((
        pid as u32,
        owned_pidfd,
        parent,
        parent_pid as u32,
        creator_tid,
        nonce,
    ))
}

struct SignalMask {
    previous: u64,
}

impl SignalMask {
    fn block() -> Result<Self> {
        // Linux's kernel rt_sigprocmask ABI has 64 signal bits. This is the
        // raw kernel mask, not libc's larger userspace sigset_t.
        let all = u64::MAX;
        let mut previous = 0_u64;
        // SAFETY: fixed 8-byte kernel masks; only the calling thread changes.
        if unsafe {
            libc::syscall(
                libc::SYS_rt_sigprocmask,
                libc::SIG_SETMASK,
                &all,
                &mut previous,
                8,
            )
        } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
        Ok(Self { previous })
    }
}
impl Drop for SignalMask {
    fn drop(&mut self) {
        // SAFETY: same valid fixed ABI and saved mask as the successful block.
        let rc = unsafe {
            libc::syscall(
                libc::SYS_rt_sigprocmask,
                libc::SIG_SETMASK,
                &self.previous,
                std::ptr::null::<u64>(),
                8,
            )
        };
        debug_assert_eq!(rc, 0, "restoring the creating thread signal mask failed");
    }
}

// These functions are child-only. Their unsafe bodies contain no heap-backed
// state, formatting, libstd, callback, lock, panic path or Rust unwinding.
unsafe fn finish(status: i32) -> ! {
    unsafe {
        libc::syscall(libc::SYS_exit_group, status);
        // SYS_exit_group cannot return. Keep a syscall-only terminal fallback.
        loop {
            libc::syscall(libc::SYS_exit, status);
        }
    }
}

unsafe fn send(nonce: [u8; 16], phase: Phase, errno: i32, pid: u32) {
    let packet = Packet::new(nonce, phase, errno, pid);
    let rc = unsafe {
        libc::syscall(
            libc::SYS_sendto,
            CHILD_FD,
            &packet,
            std::mem::size_of::<Packet>(),
            libc::MSG_NOSIGNAL | libc::MSG_DONTWAIT,
            std::ptr::null::<libc::sockaddr>(),
            0,
        )
    };
    if rc != std::mem::size_of::<Packet>() as libc::c_long {
        unsafe {
            finish(121);
        }
    }
}

unsafe fn fail(nonce: [u8; 16], pid: u32) -> ! {
    // The errno TLS belongs to this cloned child; no allocation/lock is used.
    let errno = unsafe { *libc::__errno_location() };
    unsafe {
        send(
            nonce,
            Phase::Failed,
            if errno > 0 { errno } else { libc::EIO },
            pid,
        );
    }
    unsafe {
        finish(122);
    }
}

unsafe fn receive(nonce: [u8; 16], parent_pid: u32, wanted: Phase) {
    let mut packet = Packet::zeroed();
    let rc = unsafe {
        libc::syscall(
            libc::SYS_recvfrom,
            CHILD_FD,
            &mut packet,
            std::mem::size_of::<Packet>(),
            libc::MSG_TRUNC,
            std::ptr::null_mut::<libc::sockaddr>(),
            std::ptr::null_mut::<libc::socklen_t>(),
        )
    };
    if rc == 0 {
        unsafe {
            finish(0);
        }
    }
    if rc != std::mem::size_of::<Packet>() as libc::c_long
        || !packet.matches(nonce, parent_pid)
        || packet.errno != 0
    {
        unsafe {
            finish(123);
        }
    }
    if packet.phase == Phase::Stop as u32 {
        unsafe {
            finish(0);
        }
    }
    if packet.phase != wanted as u32 {
        unsafe {
            finish(124);
        }
    }
}

unsafe fn parent_death(parent_pid: u32, nonce: [u8; 16], pid: u32) {
    if unsafe {
        libc::syscall(
            libc::SYS_prctl,
            libc::PR_SET_PDEATHSIG,
            libc::SIGKILL,
            0,
            0,
            0,
        )
    } != 0
    {
        unsafe {
            fail(nonce, pid);
        }
    }
    if unsafe { libc::syscall(libc::SYS_getppid) } != libc::c_long::from(parent_pid) {
        unsafe {
            finish(125);
        }
    }
}

unsafe fn child_main(fd: RawFd, parent_pid: u32, nonce: [u8; 16], _mode: Mode) -> ! {
    unsafe {
        // Only the private control FD survives. Inherited reservation/data/
        // service descriptors cannot leak into the parked namespace child.
        if fd != CHILD_FD
            && libc::syscall(libc::SYS_dup3, fd, CHILD_FD, libc::O_CLOEXEC)
                != libc::c_long::from(CHILD_FD)
        {
            finish(120);
        }
        if libc::syscall(libc::SYS_close_range, 4_u32, u32::MAX, 0) != 0 {
            finish(120);
        }
        libc::syscall(libc::SYS_close, 0);
        libc::syscall(libc::SYS_close, 1);
        libc::syscall(libc::SYS_close, 2);
        if libc::syscall(libc::SYS_chdir, c"/".as_ptr()) != 0 {
            finish(120);
        }
        let pid = libc::syscall(libc::SYS_getpid) as u32;
        parent_death(parent_pid, nonce, pid);
        #[cfg(test)]
        if matches!(_mode, Mode::ExitBeforeCreated) {
            finish(42);
        }
        #[cfg(test)]
        if matches!(_mode, Mode::WrongNonce) {
            let mut wrong = nonce;
            wrong[0] ^= 1;
            send(wrong, Phase::Created, 0, pid);
            receive(nonce, parent_pid, Phase::Stop);
            finish(0);
        }
        send(nonce, Phase::Created, 0, pid);
        receive(nonce, parent_pid, Phase::Enter);
        #[cfg(test)]
        if matches!(_mode, Mode::WithholdReady) {
            loop {
                libc::syscall(libc::SYS_pause);
            }
        }
        #[cfg(test)]
        if matches!(_mode, Mode::ParkOnly) {
            send(nonce, Phase::Parked, 0, pid);
            receive(nonce, parent_pid, Phase::Stop);
            finish(0);
        }
        // Clear supplementary host groups before unshare. Afterwards gid_map
        // is empty, so setgroups would fail until the privileged parent writes it.
        // Preserve allow: Android must subsequently set its mapped groups.
        if libc::syscall(libc::SYS_getgroups, 0, std::ptr::null::<libc::gid_t>()) != 0
            && libc::syscall(libc::SYS_setgroups, 0, std::ptr::null::<libc::gid_t>()) != 0
        {
            fail(nonce, pid);
        }
        if libc::syscall(libc::SYS_getgroups, 0, std::ptr::null::<libc::gid_t>()) != 0 {
            fail(nonce, pid);
        }
        if libc::syscall(libc::SYS_unshare, libc::CLONE_NEWUSER) != 0 {
            fail(nonce, pid);
        }
        send(nonce, Phase::Ready, 0, pid);
        receive(nonce, parent_pid, Phase::Go);
        if libc::syscall(libc::SYS_setresgid, 0, 0, 0) != 0 {
            fail(nonce, pid);
        }
        if libc::syscall(libc::SYS_setresuid, 0, 0, 0) != 0 {
            fail(nonce, pid);
        }
        // Linux clears PDEATHSIG on credential changes; re-arm and re-check.
        parent_death(parent_pid, nonce, pid);
        if libc::syscall(libc::SYS_prctl, libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0 {
            fail(nonce, pid);
        }
        if libc::syscall(libc::SYS_getuid) != 0
            || libc::syscall(libc::SYS_geteuid) != 0
            || libc::syscall(libc::SYS_getgid) != 0
            || libc::syscall(libc::SYS_getegid) != 0
            || libc::syscall(libc::SYS_getgroups, 0, std::ptr::null::<libc::gid_t>()) != 0
        {
            finish(126);
        }
        send(nonce, Phase::Mapped, 0, pid);
        #[cfg(test)]
        if matches!(_mode, Mode::GroupControl) {
            receive(nonce, parent_pid, Phase::ProbeGroups);
            let groups: [libc::gid_t; 2] = [1, 99999];
            let mut observed: [libc::gid_t; 2] = [0, 0];
            if libc::syscall(libc::SYS_setgroups, 2, groups.as_ptr()) != 0
                || libc::syscall(libc::SYS_getgroups, 2, observed.as_mut_ptr()) != 2
                || observed != groups
            {
                fail(nonce, pid);
            }
            send(nonce, Phase::GroupsSet, 0, pid);
            receive(nonce, parent_pid, Phase::ClearGroups);
            if libc::syscall(libc::SYS_setgroups, 0, std::ptr::null::<libc::gid_t>()) != 0
                || libc::syscall(libc::SYS_getgroups, 0, std::ptr::null::<libc::gid_t>()) != 0
            {
                fail(nonce, pid);
            }
            send(nonce, Phase::GroupsCleared, 0, pid);
        }
        let parent_thread = receive_tree_request(nonce, parent_pid);
        create_isolated_child(parent_pid, nonce, pid, parent_thread, _mode);
        finish(0);
    }
}

// Fixed namespace-tree branch. The request is possible only over the already
// nonce-bound private socket. The sole supplied FD is the broker's actual
// creating-thread pidfd, used read-only for the parent-death race.
unsafe fn receive_tree_request(nonce: [u8; 16], parent_pid: u32) -> RawFd {
    let mut packet = Packet::zeroed();
    let mut iov = libc::iovec {
        iov_base: (&mut packet as *mut Packet).cast(),
        iov_len: std::mem::size_of::<Packet>(),
    };
    let mut ancillary = [0_usize; 16];
    let mut message: libc::msghdr = unsafe { std::mem::zeroed() };
    message.msg_iov = &mut iov;
    message.msg_iovlen = 1;
    message.msg_control = ancillary.as_mut_ptr().cast();
    message.msg_controllen = std::mem::size_of_val(&ancillary);
    let rc = unsafe {
        libc::syscall(
            libc::SYS_recvmsg,
            CHILD_FD,
            &mut message,
            libc::MSG_CMSG_CLOEXEC,
        )
    };
    if rc == 0 {
        unsafe {
            finish(0);
        }
    }
    if rc != std::mem::size_of::<Packet>() as libc::c_long
        || message.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) != 0
        || !packet.matches(nonce, parent_pid)
        || packet.errno != 0
    {
        unsafe {
            finish(123);
        }
    }
    let first = unsafe { libc::CMSG_FIRSTHDR(&message) };
    if packet.phase == Phase::Stop as u32 {
        if !first.is_null() {
            unsafe {
                finish(123);
            }
        }
        unsafe {
            finish(0);
        }
    }
    if packet.phase != Phase::PrepareTree as u32 || first.is_null() {
        unsafe {
            finish(124);
        }
    }
    let header = unsafe { &*first };
    if header.cmsg_level != libc::SOL_SOCKET
        || header.cmsg_type != libc::SCM_RIGHTS
        || header.cmsg_len != unsafe { libc::CMSG_LEN(std::mem::size_of::<i32>() as u32) } as usize
        || !unsafe { libc::CMSG_NXTHDR(&message, first) }.is_null()
    {
        unsafe {
            finish(123);
        }
    }
    let parent = unsafe { std::ptr::read_unaligned(libc::CMSG_DATA(first).cast::<i32>()) };
    if parent < 0 || parent == CHILD_FD {
        unsafe {
            finish(123);
        }
    }
    let mut kind: libc::statfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::syscall(libc::SYS_fstatfs, parent, &mut kind) } != 0
        || kind.f_type != 0x5049_4446
    // Linux PID_FS_MAGIC, not a pathname
    {
        unsafe {
            finish(123);
        }
    }
    // FD 3 remains the old creator-control socket, FD 4 is a read-only pidfd.
    if parent != 4 && unsafe { libc::syscall(libc::SYS_dup3, parent, 4, libc::O_CLOEXEC) } != 4 {
        unsafe {
            finish(120);
        }
    }
    if parent != 4 {
        unsafe {
            libc::syscall(libc::SYS_close, parent);
        }
    }
    4
}

unsafe fn check_parent_thread(pidfd: RawFd) {
    let mut event = libc::pollfd {
        fd: pidfd,
        events: libc::POLLIN,
        revents: 0,
    };
    if unsafe { libc::syscall(libc::SYS_poll, &mut event, 1, 0) } != 0 || event.revents != 0 {
        unsafe {
            finish(125);
        }
    }
}

unsafe fn send_created_fds(nonce: [u8; 16], creator_pid: u32, pidfd: RawFd, control: RawFd) {
    let packet = Packet::new(nonce, Phase::TreeSpawned, 0, creator_pid);
    let mut iov = libc::iovec {
        iov_base: (&packet as *const Packet).cast_mut().cast(),
        iov_len: std::mem::size_of::<Packet>(),
    };
    let mut ancillary = [0_usize; 8];
    let mut message: libc::msghdr = unsafe { std::mem::zeroed() };
    message.msg_iov = &mut iov;
    message.msg_iovlen = 1;
    message.msg_control = ancillary.as_mut_ptr().cast();
    message.msg_controllen =
        unsafe { libc::CMSG_SPACE(2 * std::mem::size_of::<i32>() as u32) } as usize;
    let header = unsafe { libc::CMSG_FIRSTHDR(&message) };
    unsafe {
        (*header).cmsg_level = libc::SOL_SOCKET;
        (*header).cmsg_type = libc::SCM_RIGHTS;
        (*header).cmsg_len = libc::CMSG_LEN(2 * std::mem::size_of::<i32>() as u32) as usize;
        let values = libc::CMSG_DATA(header).cast::<i32>();
        std::ptr::write_unaligned(values, pidfd);
        std::ptr::write_unaligned(values.add(1), control);
    }
    if unsafe {
        libc::syscall(
            libc::SYS_sendmsg,
            CHILD_FD,
            &message,
            libc::MSG_DONTWAIT | libc::MSG_NOSIGNAL,
        )
    } != std::mem::size_of::<Packet>() as libc::c_long
    {
        // Closing the untransferred control endpoint makes the fixed PID 1
        // exit. The broker still quarantines the reservation unless it has a
        // bound pidfd and proves that exact reap.
        unsafe {
            finish(121);
        }
    }
}

unsafe fn create_isolated_child(
    parent_pid: u32,
    nonce: [u8; 16],
    creator_pid: u32,
    parent_thread: RawFd,
    mode: Mode,
) {
    unsafe {
        check_parent_thread(parent_thread);
    }
    let mut sockets = [-1_i32; 2];
    if unsafe {
        libc::syscall(
            libc::SYS_socketpair,
            libc::AF_UNIX,
            libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC,
            0,
            sockets.as_mut_ptr(),
        )
    } != 0
    {
        unsafe {
            fail(nonce, creator_pid);
        }
    }
    let one = 1_i32;
    if unsafe {
        libc::syscall(
            libc::SYS_setsockopt,
            sockets[0],
            libc::SOL_SOCKET,
            libc::SO_PASSCRED,
            &one,
            std::mem::size_of::<i32>(),
        )
    } != 0
    {
        unsafe {
            fail(nonce, creator_pid);
        }
    }
    let mut inner_pidfd = -1_i32;
    // No NEWUSER here: all six namespaces are owned by the already-admitted
    // mapped userns. CLONE_PARENT inherits this creator's SIGCHLD parent
    // relationship. clone3 explicitly requires exit_signal=0 with that flag.
    let args = CloneArgs {
        flags: (libc::CLONE_PARENT
            | libc::CLONE_PIDFD
            | libc::CLONE_NEWPID
            | libc::CLONE_NEWNS
            | libc::CLONE_NEWIPC
            | libc::CLONE_NEWUTS
            | libc::CLONE_NEWNET
            | libc::CLONE_NEWCGROUP) as u64,
        pidfd: (&mut inner_pidfd as *mut i32) as u64,
        exit_signal: 0,
        ..CloneArgs::default()
    };
    let pid = unsafe { libc::syscall(libc::SYS_clone3, &args, std::mem::size_of::<CloneArgs>()) };
    if pid == 0 {
        unsafe {
            isolated_child_main(sockets[1], parent_thread, parent_pid, nonce, mode);
        }
    }
    if pid < 0 {
        unsafe {
            fail(nonce, creator_pid);
        }
    }
    if inner_pidfd < 0 || pid > i32::MAX as libc::c_long {
        unsafe {
            finish(127);
        }
    }
    unsafe {
        send_created_fds(nonce, creator_pid, inner_pidfd, sockets[0]);
        libc::syscall(libc::SYS_close, inner_pidfd);
        libc::syscall(libc::SYS_close, sockets[0]);
        libc::syscall(libc::SYS_close, sockets[1]);
        libc::syscall(libc::SYS_close, parent_thread);
        // The creator keeps only FD 3 and can never create a second child.
        receive(nonce, parent_pid, Phase::Stop);
        finish(0);
    }
}

unsafe fn isolated_child_main(
    control: RawFd,
    parent_thread: RawFd,
    parent_pid: u32,
    nonce: [u8; 16],
    _mode: Mode,
) -> ! {
    unsafe {
        if control != CHILD_FD
            && libc::syscall(libc::SYS_dup3, control, CHILD_FD, libc::O_CLOEXEC)
                != libc::c_long::from(CHILD_FD)
        {
            finish(120);
        }
        // The creator supplied only these two descriptors. No reservation,
        // host service, namespace-administration or data FD crosses this barrier.
        if parent_thread != 4 || libc::syscall(libc::SYS_close_range, 5_u32, u32::MAX, 0) != 0 {
            finish(120);
        }
        libc::syscall(libc::SYS_close, 0);
        libc::syscall(libc::SYS_close, 1);
        libc::syscall(libc::SYS_close, 2);
        if libc::syscall(libc::SYS_getpid) != 1 || libc::syscall(libc::SYS_getppid) != 0 {
            finish(126);
        }
        // Its actual parent is the broker thread in the ancestor PID ns, so
        // getppid() is legitimately 0. The inherited, actual thread pidfd closes
        // the race after setting PDEATHSIG without inventing a numeric parent.
        if libc::syscall(
            libc::SYS_prctl,
            libc::PR_SET_PDEATHSIG,
            libc::SIGKILL,
            0,
            0,
            0,
        ) != 0
        {
            fail(nonce, 1);
        }
        check_parent_thread(parent_thread);
        libc::syscall(libc::SYS_close, parent_thread);
        if libc::syscall(libc::SYS_getuid) != 0
            || libc::syscall(libc::SYS_geteuid) != 0
            || libc::syscall(libc::SYS_getgid) != 0
            || libc::syscall(libc::SYS_getegid) != 0
            || libc::syscall(libc::SYS_getgroups, 0, std::ptr::null::<libc::gid_t>()) != 0
            || libc::syscall(libc::SYS_prctl, libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) != 1
        {
            finish(126);
        }
        // Change only this new namespace's propagation, before any image mount.
        if libc::syscall(
            libc::SYS_mount,
            std::ptr::null::<u8>(),
            c"/".as_ptr(),
            std::ptr::null::<u8>(),
            libc::MS_REC | libc::MS_PRIVATE,
            std::ptr::null::<u8>(),
        ) != 0
        {
            fail(nonce, 1);
        }
        if libc::syscall(libc::SYS_sethostname, c"droidloom".as_ptr(), 9) != 0 {
            fail(nonce, 1);
        }
        #[cfg(test)]
        if matches!(_mode, Mode::TreeWrongReady) {
            let mut wrong = nonce;
            wrong[0] ^= 1;
            send(wrong, Phase::TreeReady, 0, 1);
            receive(nonce, parent_pid, Phase::Stop);
            finish(0);
        }
        send(nonce, Phase::TreeReady, 0, 1);
        // Only a fixed, admitted pair of base mount descriptors can enter the
        // empty-data assembler. It has no runtime/dev/APEX or exec authority.
        empty_root::run(nonce, parent_pid, _mode);
    }
}
