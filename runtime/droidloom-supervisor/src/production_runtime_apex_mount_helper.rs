//! Fixed original-init/APEX operations in an already pinned guest mount namespace.
//!
//! The child never enters a user namespace, executes guest code, opens a
//! caller pathname or exports a privileged descriptor. The same runtime
//! guard retains its atomic PIDFD before releasing the one-operation barrier.
use super::*;
use std::os::fd::{OwnedFd, RawFd};
use std::time::Duration;

const REPLY_MAGIC: u32 = 0x5041_4d31;
const READY_MAGIC: u32 = 0x5041_4d30;
const RETIRE_BOUND: Duration = Duration::from_secs(2);

// Native 64-bit Linux fstatfs UAPI; libc's statfs keeps f_flags private on
// this target. The child uses only raw syscalls after clone, never fstatvfs's
// possible libc work. Production CP3A execution is fixed to x86_64.
#[repr(C)]
struct KernelStatfs {
    kind: i64,
    block_size: i64,
    blocks: u64,
    free_blocks: u64,
    available_blocks: u64,
    files: u64,
    free_files: u64,
    fsid: [i32; 2],
    name_length: i64,
    fragment_size: i64,
    flags: i64,
    spare: [i64; 4],
}
const _: [(); 120] = [(); std::mem::size_of::<KernelStatfs>()];

#[derive(Clone, Copy, Debug)]
#[repr(C)]
struct Reply {
    magic: u32,
    stage: u32,
    errno: i32,
    reserved: u32,
}

#[derive(Clone, Copy, Debug)]
#[repr(C)]
pub(super) struct ExpectedNode {
    device: u64,
    inode: u64,
    mount: u64,
    mode: u32,
    uid: u32,
    gid: u32,
}

impl ExpectedNode {
    pub(super) fn of(file: &File) -> Result<Self> {
        let meta = file.metadata()?;
        Ok(Self {
            device: meta.dev(),
            inode: meta.ino(),
            mount: mount_id(file)?,
            mode: meta.mode(),
            uid: meta.uid(),
            gid: meta.gid(),
        })
    }
}

/// Only these compiled operations cover the pinned CP3A second-stage calls.
/// The operation selects every pathname and tmpfs limit in compiled code.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) enum InitialOperation {
    DebugRamdisk,
    SecondStageResources,
    Apex,
    BootstrapApex,
    Linkerconfig,
    RootShared,
    ApexPrivate,
    LinkerconfigPrivate,
    Storage,
    BindInstaller,
    BindAndroidWritable,
    SlaveInstaller,
    SlaveAndroidWritable,
    SharedInstaller,
    SharedAndroidWritable,
    BindBootstrapApex,
}

impl InitialOperation {
    pub(super) const ALL: [Self; 16] = [
        Self::DebugRamdisk,
        Self::SecondStageResources,
        Self::Apex,
        Self::BootstrapApex,
        Self::Linkerconfig,
        Self::RootShared,
        Self::ApexPrivate,
        Self::LinkerconfigPrivate,
        Self::Storage,
        Self::BindInstaller,
        Self::BindAndroidWritable,
        Self::SlaveInstaller,
        Self::SlaveAndroidWritable,
        Self::SharedInstaller,
        Self::SharedAndroidWritable,
        Self::BindBootstrapApex,
    ];

    pub(super) fn target(self) -> &'static CStr {
        match self {
            Self::DebugRamdisk => c"/debug_ramdisk",
            Self::SecondStageResources => c"/second_stage_resources",
            Self::Apex | Self::BindBootstrapApex => c"/apex",
            Self::BootstrapApex => c"/bootstrap-apex",
            Self::Linkerconfig | Self::LinkerconfigPrivate => c"/linkerconfig",
            Self::RootShared => c"/",
            Self::ApexPrivate => c"/apex",
            Self::Storage => c"/mnt",
            Self::BindInstaller | Self::SlaveInstaller | Self::SharedInstaller => c"/mnt/installer",
            Self::BindAndroidWritable
            | Self::SlaveAndroidWritable
            | Self::SharedAndroidWritable => c"/mnt/androidwritable",
        }
    }

    fn propagation_flags(self) -> Option<libc::c_ulong> {
        match self {
            Self::RootShared => Some(0x10_4000),
            Self::ApexPrivate | Self::LinkerconfigPrivate => Some(0x4_0000),
            Self::SlaveInstaller | Self::SlaveAndroidWritable => Some(0x8_0000),
            Self::SharedInstaller | Self::SharedAndroidWritable => Some(0x10_0000),
            _ => None,
        }
    }

    fn bind_source(self) -> Option<&'static CStr> {
        match self {
            Self::BindInstaller | Self::BindAndroidWritable => Some(c"/mnt/user"),
            Self::BindBootstrapApex => Some(c"/bootstrap-apex"),
            _ => None,
        }
    }

    fn storage_branch(self) -> bool {
        matches!(
            self,
            Self::BindInstaller
                | Self::BindAndroidWritable
                | Self::SlaveInstaller
                | Self::SlaveAndroidWritable
                | Self::SharedInstaller
                | Self::SharedAndroidWritable
        )
    }

    pub(super) fn role(self) -> Option<ActivationRootRole> {
        match self {
            Self::DebugRamdisk
            | Self::SecondStageResources
            | Self::RootShared
            | Self::ApexPrivate
            | Self::LinkerconfigPrivate
            | Self::Storage
            | Self::BindInstaller
            | Self::BindAndroidWritable
            | Self::SlaveInstaller
            | Self::SlaveAndroidWritable
            | Self::SharedInstaller
            | Self::SharedAndroidWritable => None,
            Self::Apex => Some(ActivationRootRole::Apex),
            Self::BootstrapApex | Self::BindBootstrapApex => {
                Some(ActivationRootRole::BootstrapApex)
            }
            Self::Linkerconfig => Some(ActivationRootRole::Linkerconfig),
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Operation {
    ReadonlyApex,
    Initial(InitialOperation),
}

/// Issued once, only after the real fixed operation, packet and PIDFD exit
/// agree within the original deadline. Earlier helper/setup errors never
/// become an emulated result for a syscall that did not execute.
#[derive(Debug)]
pub(super) struct InitialResult {
    operation: InitialOperation,
    errno: i32,
}

impl InitialResult {
    pub(super) fn operation(&self) -> InitialOperation {
        self.operation
    }

    pub(super) fn errno(&self) -> i32 {
        self.errno
    }
}

#[derive(Debug)]
pub(super) struct Helper {
    pidfd: Option<OwnedFd>,
    socket: OwnedFd,
    pid: i32,
    creator: i64,
    creator_pidfd: OwnedFd,
    deadline: Instant,
    operation: Operation,
    result_taken: bool,
    ready: bool,
    started: bool,
    preparation_error: Option<i32>,
    reply: Option<Reply>,
    exit: Option<(i32, i32)>,
}

fn current_thread_handle() -> Result<(OwnedFd, i64, i32)> {
    let creator = unsafe { libc::syscall(libc::SYS_gettid) };
    let parent = unsafe { libc::getpid() };
    require(
        creator > 1 && parent > 1,
        "mount helper cannot be host PID1",
    )?;
    // The currently executing thread cannot be reaped/reused during this
    // call. This is not a lookup of an external PID or child authority.
    let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, creator, libc::O_EXCL) };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let held = unsafe { OwnedFd::from_raw_fd(raw as i32) };
    let mut info = crate::production_activation_protocol::PidfdInfo::request_exit();
    info.mask = 3;
    zero_rc(unsafe {
        libc::ioctl(
            held.as_raw_fd(),
            crate::production_activation_protocol::PIDFD_GET_INFO as libc::c_ulong,
            &mut info,
        )
    })?;
    require(
        info.mask & 3 == 3 && info.pid == creator as u32 && info.tgid == parent as u32,
        "mount helper creator thread PIDFD identity differs",
    )?;
    require(
        unsafe { creator_alive(held.as_raw_fd()) },
        "mount helper creator thread already exited",
    )?;
    Ok((held, creator, parent))
}

fn monotonic() -> io::Result<u64> {
    let mut now: libc::timespec = unsafe { std::mem::zeroed() };
    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut now) } != 0 {
        return Err(io::Error::last_os_error());
    }
    u64::try_from(now.tv_sec)
        .ok()
        .and_then(|s| s.checked_mul(1_000_000_000))
        .and_then(|n| n.checked_add(u64::try_from(now.tv_nsec).ok()?))
        .ok_or_else(|| io::Error::other("mount helper clock overflow"))
}

fn validate_reply_identity(reply: Reply, exit: (i32, i32)) -> Result<()> {
    require(
        reply.magic == REPLY_MAGIC
            && reply.reserved == 0
            && (1..=9).contains(&reply.stage)
            && (0..=4095).contains(&reply.errno),
        "fixed mount helper result encoding",
    )?;
    require(
        exit.0 == libc::CLD_EXITED && exit.1 == if reply.errno == 0 { 0 } else { 125 },
        "mount helper reply differs from actual PIDFD exit",
    )?;
    Ok(())
}

fn validate_outcome(reply: Reply, exit: (i32, i32)) -> Result<()> {
    validate_reply_identity(reply, exit)?;
    if reply.errno != 0 {
        return Err(io::Error::from_raw_os_error(reply.errno).into());
    }
    require(
        reply.stage == 9,
        "only completed move_mount can report success",
    )
}

impl Helper {
    /// The four input descriptors are held in the parent runtime resource
    /// before this call. No namespace or mount operation occurs until start.
    pub(super) fn spawn(
        files: [&File; 4],
        expected: [ExpectedNode; 3],
        end: Instant,
    ) -> Result<Self> {
        Self::spawn_operation(files, expected, Operation::ReadonlyApex, end)
    }

    pub(super) fn spawn_initial(
        files: [&File; 4],
        expected: [ExpectedNode; 3],
        operation: InitialOperation,
        end: Instant,
    ) -> Result<Self> {
        Self::spawn_operation(files, expected, Operation::Initial(operation), end)
    }

    fn spawn_operation(
        files: [&File; 4],
        expected: [ExpectedNode; 3],
        operation: Operation,
        end: Instant,
    ) -> Result<Self> {
        let now_ns = monotonic()?;
        let left = end
            .checked_duration_since(Instant::now())
            .filter(|left| !left.is_zero())
            .ok_or(MountError::Rejected("mount helper deadline"))?;
        let deadline = now_ns
            .checked_add(
                u64::try_from(left.as_nanos())
                    .map_err(|_| MountError::Rejected("mount helper deadline overflow"))?,
            )
            .ok_or(MountError::Rejected("mount helper deadline overflow"))?;
        let mut action: libc::sigaction = unsafe { std::mem::zeroed() };
        zero_rc(unsafe { libc::sigaction(libc::SIGCHLD, std::ptr::null(), &mut action) })?;
        require(
            action.sa_sigaction == libc::SIG_DFL && action.sa_flags & libc::SA_NOCLDWAIT == 0,
            "mount helper requires actual original-parent PIDFD reaping",
        )?;
        let mut pair = [-1_i32; 2];
        zero_rc(unsafe {
            libc::socketpair(
                libc::AF_UNIX,
                libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
                0,
                pair.as_mut_ptr(),
            )
        })?;
        let parent = unsafe { OwnedFd::from_raw_fd(pair[0]) };
        let child = unsafe { OwnedFd::from_raw_fd(pair[1]) };
        let (creator_pidfd, creator, parent_pid) = current_thread_handle()?;
        let mut full: libc::sigset_t = unsafe { std::mem::zeroed() };
        let mut old: libc::sigset_t = unsafe { std::mem::zeroed() };
        zero_rc(unsafe { libc::sigfillset(&mut full) })?;
        let mask = unsafe { libc::pthread_sigmask(libc::SIG_SETMASK, &full, &mut old) };
        if mask != 0 {
            return Err(io::Error::from_raw_os_error(mask).into());
        }
        let mut pidfd = -1_i32;
        // struct clone_args through cgroup, no shared VM/files/fs/sighand and
        // no namespace creation. CLONE_PIDFD is acquired atomically at birth.
        let mut args = [0_u64; 11];
        args[0] = libc::CLONE_PIDFD as u64;
        args[1] = (&mut pidfd as *mut i32) as u64;
        args[4] = libc::SIGCHLD as u64;
        let raw = files.map(AsRawFd::as_raw_fd);
        let pid = unsafe {
            libc::syscall(
                libc::SYS_clone3,
                args.as_ptr(),
                std::mem::size_of_val(&args),
            )
        };
        if pid == 0 {
            unsafe {
                child_run(
                    raw,
                    expected,
                    child.as_raw_fd(),
                    creator_pidfd.as_raw_fd(),
                    parent_pid,
                    deadline,
                    operation,
                )
            }
        }
        let clone_error = if pid < 0 {
            Some(io::Error::last_os_error())
        } else {
            None
        };
        let restored =
            unsafe { libc::pthread_sigmask(libc::SIG_SETMASK, &old, std::ptr::null_mut()) };
        drop(child);
        if let Some(error) = clone_error {
            return Err(error.into());
        }
        require(
            pidfd >= 0 && pid <= i32::MAX as i64,
            "mount helper clone3 did not return its atomic PIDFD",
        )?;
        let value = Self {
            pidfd: Some(unsafe { OwnedFd::from_raw_fd(pidfd) }),
            socket: parent,
            pid: pid as i32,
            creator,
            creator_pidfd,
            deadline: end,
            operation,
            result_taken: false,
            ready: false,
            started: false,
            preparation_error: (restored != 0).then_some(restored),
            reply: None,
            exit: None,
        };
        // A post-clone setup error is retained in this owner. start() will
        // reject it after the caller has placed the actual PIDFD in custody.
        Ok(value)
    }

    fn same_thread(&self) -> Result<()> {
        require(
            unsafe { libc::syscall(libc::SYS_gettid) } == self.creator
                && unsafe { creator_alive(self.creator_pidfd.as_raw_fd()) },
            "mount helper owner moved away from its creating thread",
        )
    }

    pub(super) fn start(&mut self) -> Result<()> {
        self.same_thread()?;
        if let Some(error) = self.preparation_error {
            return Err(io::Error::from_raw_os_error(error).into());
        }
        require(
            !self.started && self.exit.is_none(),
            "mount helper already released or reaped",
        )?;
        // A queued release before PR_SET_PDEATHSIG would miss death of a
        // nonleader creator that is reparented inside its still-live TGID.
        // Linux 6.18 can also delay leader-thread PIDFD readability until
        // the group exits. Require this same still-executing creator to
        // receive the child's post-PDEATHSIG READY before sending release.
        while !self.ready {
            self.same_thread()?;
            let left = self.deadline.saturating_duration_since(Instant::now());
            require(!left.is_zero(), "mount helper READY deadline")?;
            let mut packet = Reply {
                magic: 0,
                stage: 0,
                errno: 0,
                reserved: 0,
            };
            let count = unsafe {
                libc::recv(
                    self.socket.as_raw_fd(),
                    (&mut packet as *mut Reply).cast(),
                    std::mem::size_of::<Reply>(),
                    libc::MSG_DONTWAIT | libc::MSG_TRUNC,
                )
            };
            if count == std::mem::size_of::<Reply>() as isize {
                if packet.magic == REPLY_MAGIC {
                    self.reply = Some(packet);
                }
                require(
                    packet.magic == READY_MAGIC
                        && packet.stage == 3
                        && packet.errno == 0
                        && packet.reserved == 0,
                    "mount helper did not complete its actual PDEATHSIG/descriptor READY barrier",
                )?;
                self.ready = true;
                break;
            }
            if count >= 0 {
                return Err(MountError::Rejected(
                    "mount helper READY packet size or closed peer",
                ));
            }
            let error = io::Error::last_os_error();
            if ![Some(libc::EAGAIN), Some(libc::EINTR)].contains(&error.raw_os_error()) {
                return Err(error.into());
            }
            let mut poll = [
                libc::pollfd {
                    fd: self.socket.as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
                libc::pollfd {
                    fd: self.pidfd.as_ref().unwrap().as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
            ];
            let count = unsafe {
                libc::poll(
                    poll.as_mut_ptr(),
                    poll.len() as _,
                    left.as_millis().clamp(1, 50) as i32,
                )
            };
            if count < 0 && io::Error::last_os_error().kind() != io::ErrorKind::Interrupted {
                return Err(io::Error::last_os_error().into());
            }
            require(
                !poll.iter().any(|row| row.revents & libc::POLLNVAL != 0),
                "mount helper READY descriptor changed",
            )?;
        }
        self.same_thread()?;
        require(
            Instant::now() < self.deadline,
            "mount helper release deadline",
        )?;
        let start = 1_u8;
        let sent = unsafe {
            libc::send(
                self.socket.as_raw_fd(),
                (&start as *const u8).cast(),
                1,
                libc::MSG_NOSIGNAL | libc::MSG_DONTWAIT,
            )
        };
        if sent < 0 {
            return Err(io::Error::last_os_error().into());
        }
        require(sent == 1, "mount helper barrier send")?;
        self.started = true;
        Ok(())
    }

    fn reap_if_exited(&mut self) -> Result<bool> {
        self.same_thread()?;
        if self.exit.is_some() {
            return Ok(true);
        }
        let fd = self
            .pidfd
            .as_ref()
            .ok_or(MountError::Rejected("mount helper PIDFD absent"))?;
        let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
        zero_rc(unsafe {
            libc::waitid(
                libc::P_PIDFD,
                fd.as_raw_fd() as u32,
                &mut info,
                libc::WEXITED | libc::WNOHANG,
            )
        })?;
        let pid = unsafe { info.si_pid() };
        if pid == 0 {
            return Ok(false);
        }
        require(
            pid == self.pid
                && [libc::CLD_EXITED, libc::CLD_KILLED, libc::CLD_DUMPED].contains(&info.si_code),
            "mount helper actual PIDFD reap identity",
        )?;
        self.exit = Some((info.si_code, unsafe { info.si_status() }));
        Ok(true)
    }

    fn receive(&mut self) -> Result<()> {
        if self.reply.is_some() {
            return Ok(());
        }
        let mut reply = Reply {
            magic: 0,
            stage: 0,
            errno: 0,
            reserved: 0,
        };
        let count = unsafe {
            libc::recv(
                self.socket.as_raw_fd(),
                (&mut reply as *mut Reply).cast(),
                std::mem::size_of::<Reply>(),
                libc::MSG_DONTWAIT | libc::MSG_TRUNC,
            )
        };
        if count < 0 {
            let error = io::Error::last_os_error();
            if [Some(libc::EAGAIN), Some(libc::EINTR)].contains(&error.raw_os_error()) {
                return Ok(());
            }
            return Err(error.into());
        }
        if count == 0 {
            return Err(MountError::Rejected("mount helper closed without a result"));
        }
        require(
            count as usize == std::mem::size_of::<Reply>(),
            "mount helper result packet size",
        )?;
        self.reply = Some(reply);
        Ok(())
    }

    pub(super) fn complete(&mut self, end: Instant) -> Result<()> {
        require(
            self.operation == Operation::ReadonlyApex,
            "readonly helper operation differs",
        )?;
        let (reply, exit) = self.complete_packet(end)?;
        validate_outcome(reply, exit)
    }

    pub(super) fn complete_initial(&mut self, end: Instant) -> Result<InitialResult> {
        let Operation::Initial(operation) = self.operation else {
            return Err(MountError::Rejected(
                "original-init helper operation absent",
            ));
        };
        require(
            !self.result_taken,
            "original-init syscall result was already consumed",
        )?;
        let (reply, exit) = self.complete_packet(end)?;
        validate_reply_identity(reply, exit)?;
        if reply.stage != 9 {
            if reply.errno != 0 {
                return Err(io::Error::from_raw_os_error(reply.errno).into());
            }
            return Err(MountError::Rejected("original-init syscall did not run"));
        }
        require(
            Instant::now() < end,
            "original-init syscall result deadline",
        )?;
        self.result_taken = true;
        Ok(InitialResult {
            operation,
            errno: reply.errno,
        })
    }

    fn complete_packet(&mut self, end: Instant) -> Result<(Reply, (i32, i32))> {
        self.same_thread()?;
        require(self.started, "mount helper barrier was not released")?;
        require(
            end <= self.deadline,
            "mount helper cannot extend its original deadline",
        )?;
        loop {
            require(
                Instant::now() < end,
                "actual mount helper completion deadline",
            )?;
            self.receive()?;
            if self.reap_if_exited()? {
                self.receive()?;
                let reply = self.reply.ok_or(MountError::Rejected(
                    "mount helper exited without its result",
                ))?;
                let exit = self.exit.unwrap();
                require(
                    Instant::now() < end,
                    "actual mount helper completion deadline",
                )?;
                return Ok((reply, exit));
            }
            let left = end.saturating_duration_since(Instant::now());
            require(!left.is_zero(), "actual mount helper completion deadline")?;
            let mut poll = [
                libc::pollfd {
                    fd: self.socket.as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
                libc::pollfd {
                    fd: self.pidfd.as_ref().unwrap().as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
            ];
            let rc = unsafe {
                libc::poll(
                    poll.as_mut_ptr(),
                    poll.len() as _,
                    left.as_millis().clamp(1, 50) as i32,
                )
            };
            if rc < 0 && io::Error::last_os_error().kind() != io::ErrorKind::Interrupted {
                return Err(io::Error::last_os_error().into());
            }
            require(
                !poll.iter().any(|row| row.revents & libc::POLLNVAL != 0),
                "mount helper lost held descriptor",
            )?;
        }
    }

    pub(super) fn retire(&mut self) -> Result<()> {
        self.same_thread()?;
        if self.reap_if_exited()? {
            return Ok(());
        }
        let pidfd = self.pidfd.as_ref().unwrap().as_raw_fd();
        let rc = unsafe {
            libc::syscall(
                libc::SYS_pidfd_send_signal,
                pidfd,
                libc::SIGKILL,
                std::ptr::null::<libc::siginfo_t>(),
                0,
            )
        };
        if rc != 0 && io::Error::last_os_error().raw_os_error() != Some(libc::ESRCH) {
            return Err(io::Error::last_os_error().into());
        }
        let end = Instant::now() + RETIRE_BOUND;
        while !self.reap_if_exited()? {
            let left = end.saturating_duration_since(Instant::now());
            require(
                !left.is_zero(),
                "mount helper retirement unproven; original resource retained",
            )?;
            let mut poll = libc::pollfd {
                fd: pidfd,
                events: libc::POLLIN,
                revents: 0,
            };
            let rc = unsafe { libc::poll(&mut poll, 1, left.as_millis().clamp(1, 50) as i32) };
            if rc < 0 && io::Error::last_os_error().kind() != io::ErrorKind::Interrupted {
                return Err(io::Error::last_os_error().into());
            }
        }
        Ok(())
    }
}

impl Drop for Helper {
    fn drop(&mut self) {
        if self.exit.is_none() {
            // The outer runtime guard also retains the original reservation.
            // Never turn an unproven helper lifetime into a released PIDFD.
            if let Some(fd) = self.pidfd.take() {
                std::mem::forget(fd);
            }
        }
    }
}

unsafe fn child_result(socket: RawFd, stage: u32, errno: i32) -> ! {
    let reply = Reply {
        magic: REPLY_MAGIC,
        stage,
        errno,
        reserved: 0,
    };
    unsafe {
        libc::syscall(
            libc::SYS_sendto,
            socket,
            &reply,
            std::mem::size_of::<Reply>(),
            libc::MSG_NOSIGNAL | libc::MSG_DONTWAIT,
            std::ptr::null::<libc::sockaddr>(),
            0,
        );
        libc::syscall(libc::SYS_exit_group, if errno == 0 { 0 } else { 125 });
        std::hint::unreachable_unchecked()
    }
}

unsafe fn child_error(socket: RawFd, stage: u32) -> ! {
    let errno = unsafe { *libc::__errno_location() };
    unsafe {
        child_result(
            socket,
            stage,
            if (1..=4095).contains(&errno) {
                errno
            } else {
                libc::EIO
            },
        )
    }
}

unsafe fn child_node(fd: RawFd, expected: ExpectedNode) -> bool {
    let mut stat: libc::stat = unsafe { std::mem::zeroed() };
    let mut sx: libc::statx = unsafe { std::mem::zeroed() };
    unsafe {
        libc::syscall(libc::SYS_fstat, fd, &mut stat) == 0
            && libc::syscall(
                libc::SYS_statx,
                fd,
                c"".as_ptr(),
                AT_EMPTY_PATH,
                0x1000_u32,
                &mut sx,
            ) == 0
            && sx.stx_mask & 0x1000 != 0
            && sx.stx_mnt_id == expected.mount
            && (
                stat.st_dev,
                stat.st_ino,
                stat.st_mode,
                stat.st_uid,
                stat.st_gid,
            ) == (
                expected.device,
                expected.inode,
                expected.mode,
                expected.uid,
                expected.gid,
            )
    }
}

unsafe fn creator_alive(fd: RawFd) -> bool {
    let mut poll = libc::pollfd {
        fd,
        events: libc::POLLIN,
        revents: 0,
    };
    unsafe { libc::syscall(libc::SYS_poll, &mut poll, 1, 0) == 0 && poll.revents == 0 }
}

unsafe fn child_before_deadline(socket: RawFd, creator: RawFd, stage: u32, deadline: u64) {
    if !unsafe { creator_alive(creator) } {
        unsafe {
            child_result(socket, stage, libc::ESRCH);
        }
    }
    let mut now: libc::timespec = unsafe { std::mem::zeroed() };
    if unsafe { libc::syscall(libc::SYS_clock_gettime, libc::CLOCK_MONOTONIC, &mut now) } != 0 {
        unsafe {
            child_error(socket, stage);
        }
    }
    let value = u64::try_from(now.tv_sec)
        .ok()
        .and_then(|s| s.checked_mul(1_000_000_000))
        .and_then(|s| s.checked_add(u64::try_from(now.tv_nsec).ok()?));
    if !(0..1_000_000_000).contains(&now.tv_nsec) || value.is_none_or(|value| value >= deadline) {
        unsafe {
            child_result(socket, stage, libc::ETIMEDOUT);
        }
    }
}

unsafe fn child_run(
    raw: [RawFd; 4],
    expected: [ExpectedNode; 3],
    socket: RawFd,
    creator: RawFd,
    parent: i32,
    deadline: u64,
    operation: Operation,
) -> ! {
    unsafe {
        if libc::syscall(
            libc::SYS_prctl,
            libc::PR_SET_PDEATHSIG,
            libc::SIGKILL,
            0,
            0,
            0,
        ) != 0
            || libc::syscall(libc::SYS_getppid) != parent as i64
        {
            child_error(socket, 1);
        }
        if !creator_alive(creator) {
            child_result(socket, 1, libc::ESRCH);
        }
        // Duplicate every input before closing anything. Original descriptors
        // may overlap our eventual retained range; no live FD is overwritten.
        let mut keep = [-1_i32; 6];
        for (i, fd) in raw.into_iter().chain([creator, socket]).enumerate() {
            let n = libc::syscall(libc::SYS_fcntl, fd, libc::F_DUPFD_CLOEXEC, 128);
            if n < 128 || n > i32::MAX as i64 {
                child_error(socket, 2);
            }
            keep[i] = n as i32;
        }
        let creator = keep[4];
        let channel = keep[5];
        let mut next = 0_u32;
        for fd in keep {
            if next < fd as u32 && libc::syscall(libc::SYS_close_range, next, fd as u32 - 1, 0) != 0
            {
                child_error(channel, 2);
            }
            next = fd as u32 + 1;
        }
        if libc::syscall(libc::SYS_close_range, next, u32::MAX, 0) != 0 {
            child_error(channel, 2);
        }
        child_before_deadline(channel, creator, 3, deadline);
        let ready = Reply {
            magic: READY_MAGIC,
            stage: 3,
            errno: 0,
            reserved: 0,
        };
        if libc::syscall(
            libc::SYS_sendto,
            channel,
            &ready,
            std::mem::size_of::<Reply>(),
            libc::MSG_NOSIGNAL | libc::MSG_DONTWAIT,
            std::ptr::null::<libc::sockaddr>(),
            0,
        ) != std::mem::size_of::<Reply>() as i64
        {
            child_error(channel, 3);
        }
        loop {
            child_before_deadline(channel, creator, 3, deadline);
            let mut start = [0_u8; 2];
            let count = libc::syscall(
                libc::SYS_recvfrom,
                channel,
                start.as_mut_ptr(),
                start.len(),
                libc::MSG_DONTWAIT | libc::MSG_TRUNC,
                std::ptr::null::<libc::sockaddr>(),
                std::ptr::null::<libc::socklen_t>(),
            );
            if count == 1 && start[0] == 1 {
                break;
            }
            if count >= 0 {
                child_result(channel, 3, libc::EPROTO);
            }
            if *libc::__errno_location() != libc::EAGAIN && *libc::__errno_location() != libc::EINTR
            {
                child_error(channel, 3);
            }
            let mut p = libc::pollfd {
                fd: channel,
                events: libc::POLLIN,
                revents: 0,
            };
            libc::syscall(libc::SYS_poll, &mut p, 1, 20);
        }
        for i in 0..3 {
            if !child_node(keep[i], expected[i]) {
                child_result(channel, 4, libc::ESTALE);
            }
        }
        let mut fs: KernelStatfs = std::mem::zeroed();
        if libc::syscall(libc::SYS_fstatfs, keep[0], &mut fs) != 0 {
            child_error(channel, 4);
        }
        let source_valid = match operation {
            Operation::ReadonlyApex => {
                [0xef53, 0xe0f5_e1e2_u32 as libc::c_long].contains(&fs.kind)
                    && fs.flags as u64 & (READONLY_FLAGS | 8 | 1024) == READONLY_FLAGS | 1024
            }
            Operation::Initial(initial)
                if initial == InitialOperation::Storage || initial.storage_branch() =>
            {
                fs.kind == 0x0102_1994
                    && fs.flags as u64 & 15 == ACTIVATION_FLAGS
                    && fs.blocks.checked_mul(fs.fragment_size as u64)
                        == Some(super::init_storage::STORAGE_BYTES)
                    && fs.files == super::init_storage::STORAGE_INODES
                    && expected[0].mode == libc::S_IFDIR | 0o755
            }
            Operation::Initial(initial) => match initial.role() {
                Some(role) => {
                    fs.kind == 0x0102_1994
                        && fs.flags as u64 & 15 == ACTIVATION_FLAGS
                        && fs.blocks.checked_mul(fs.fragment_size as u64) == Some(role.bytes())
                        && fs.files == role.inodes()
                        && expected[0].mode == libc::S_IFDIR | 0o755
                }
                None => {
                    expected[0].mode & libc::S_IFMT == libc::S_IFDIR
                        && expected[1].mode & libc::S_IFMT == libc::S_IFDIR
                }
            },
        };
        if !source_valid {
            child_result(channel, 4, libc::EPERM);
        }
        if libc::syscall(libc::SYS_prctl, libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0 {
            child_error(channel, 5);
        }
        // Only mntns, never userns; normal setns/move_mount MAC hooks remain.
        child_before_deadline(channel, creator, 6, deadline);
        if libc::syscall(libc::SYS_setns, keep[3], libc::CLONE_NEWNS) != 0 {
            child_error(channel, 6);
        }
        if libc::syscall(libc::SYS_fchdir, keep[2]) != 0
            || libc::syscall(libc::SYS_chroot, c".".as_ptr()) != 0
            || libc::syscall(libc::SYS_chdir, c"/".as_ptr()) != 0
        {
            child_error(channel, 7);
        }
        for i in 0..3 {
            if !child_node(keep[i], expected[i]) {
                child_result(channel, 8, libc::ESTALE);
            }
        }
        if let Operation::Initial(initial) = operation {
            // Only a compiled, absolute name below the held guest root is
            // opened. Its actual inode/mount must still be the pinned target.
            let visible = libc::syscall(
                libc::SYS_openat,
                libc::AT_FDCWD,
                initial.target().as_ptr(),
                libc::O_PATH | libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW,
            );
            if visible < 0 {
                child_error(channel, 8);
            }
            if visible > i32::MAX as i64 || !child_node(visible as i32, expected[1]) {
                child_result(channel, 8, libc::ESTALE);
            }
            if libc::syscall(libc::SYS_close, visible) != 0 {
                child_error(channel, 8);
            }
            if let Some(source) = initial.bind_source() {
                let actual_source = libc::syscall(
                    libc::SYS_openat,
                    libc::AT_FDCWD,
                    source.as_ptr(),
                    libc::O_PATH | libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW,
                );
                if actual_source < 0 {
                    child_error(channel, 8);
                }
                if actual_source > i32::MAX as i64 || !child_node(actual_source as i32, expected[0])
                {
                    child_result(channel, 8, libc::ESTALE);
                }
                if libc::syscall(libc::SYS_close, actual_source) != 0 {
                    child_error(channel, 8);
                }
            }
        }
        child_before_deadline(channel, creator, 9, deadline);
        let rc = match operation {
            Operation::Initial(initial) if initial.bind_source().is_some() => {
                // Original recursive bind, including the normal propagation
                // and LSM path. Both fixed names were matched to held inodes.
                libc::syscall(
                    libc::SYS_mount,
                    initial.bind_source().unwrap().as_ptr(),
                    initial.target().as_ptr(),
                    std::ptr::null::<libc::c_char>(),
                    0x5000 as libc::c_ulong,
                    std::ptr::null::<libc::c_char>(),
                )
            }
            Operation::Initial(initial) if initial.propagation_flags().is_some() => {
                // Normal mount syscall and all actual LSM hooks. Only the
                // compiled original target and flags enter the held guest
                // mount namespace; there is no caller-selected propagation.
                libc::syscall(
                    libc::SYS_mount,
                    std::ptr::null::<libc::c_char>(),
                    initial.target().as_ptr(),
                    std::ptr::null::<libc::c_char>(),
                    initial.propagation_flags().unwrap(),
                    std::ptr::null::<libc::c_char>(),
                )
            }
            Operation::Initial(initial)
                if matches!(
                    initial,
                    InitialOperation::DebugRamdisk | InitialOperation::SecondStageResources
                ) =>
            {
                libc::syscall(libc::SYS_umount2, initial.target().as_ptr(), 0)
            }
            _ => libc::syscall(
                libc::SYS_move_mount,
                keep[0],
                c"".as_ptr(),
                keep[1],
                c"".as_ptr(),
                0x4_u32 | 0x40_u32,
            ),
        };
        if rc != 0 {
            child_error(channel, 9);
        }
        child_result(channel, 9, 0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn peek_actual_ready(helper: &Helper) {
        let end = Instant::now() + Duration::from_secs(3);
        loop {
            let mut reply: Reply = unsafe { std::mem::zeroed() };
            let count = unsafe {
                libc::recv(
                    helper.socket.as_raw_fd(),
                    (&mut reply as *mut Reply).cast(),
                    std::mem::size_of::<Reply>(),
                    libc::MSG_DONTWAIT | libc::MSG_TRUNC | libc::MSG_PEEK,
                )
            };
            if count >= 0 {
                assert_eq!(count, std::mem::size_of::<Reply>() as isize);
                assert_eq!(
                    (reply.magic, reply.stage, reply.errno, reply.reserved),
                    (READY_MAGIC, 3, 0, 0)
                );
                return;
            }
            assert!(
                [Some(libc::EAGAIN), Some(libc::EINTR)]
                    .contains(&io::Error::last_os_error().raw_os_error())
            );
            assert!(Instant::now() < end, "actual helper did not reach READY");
            let mut poll = libc::pollfd {
                fd: helper.socket.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            assert!(unsafe { libc::poll(&mut poll, 1, 20) } >= 0);
        }
    }

    #[test]
    fn original_init_helper_setup_failure_never_issues_a_completed_syscall_result() {
        let before = std::fs::read("/proc/self/mountinfo").unwrap();
        let directory = tempfile::tempdir().unwrap();
        let file = File::open(directory.path()).unwrap();
        let expected = ExpectedNode::of(&file).unwrap();
        for operation in InitialOperation::ALL {
            let end = Instant::now() + Duration::from_secs(3);
            let mut helper =
                Helper::spawn_initial([&file; 4], [expected; 3], operation, end).unwrap();
            helper.start().unwrap();
            assert!(helper.complete_initial(end).is_err());
            let reply = helper.reply.expect("actual setup reply");
            assert!(reply.stage < 9 && reply.errno > 0);
            assert_eq!(helper.exit, Some((libc::CLD_EXITED, 125)));
            assert!(!helper.result_taken);
            helper.retire().unwrap();
            let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
            assert_eq!(
                unsafe {
                    libc::waitid(
                        libc::P_PIDFD,
                        helper.pidfd.as_ref().unwrap().as_raw_fd() as _,
                        &mut info,
                        libc::WEXITED | libc::WNOHANG,
                    )
                },
                -1
            );
            assert_eq!(
                io::Error::last_os_error().raw_os_error(),
                Some(libc::ECHILD)
            );
        }
        assert_eq!(std::fs::read("/proc/self/mountinfo").unwrap(), before);
    }

    #[test]
    fn apex_mount_helper_creator_thread_exit_kills_ready_child_while_group_lives() {
        let (send, receive) = std::sync::mpsc::sync_channel(1);
        let (finish, until_finish) = std::sync::mpsc::sync_channel(1);
        let thread = std::thread::spawn(move || {
            let directory = tempfile::tempdir().unwrap();
            let file = File::open(directory.path()).unwrap();
            let expected = ExpectedNode::of(&file).unwrap();
            let helper = Helper::spawn(
                [&file; 4],
                [expected; 3],
                Instant::now() + Duration::from_secs(5),
            )
            .unwrap();
            send.send(helper).unwrap();
            until_finish.recv().unwrap();
        });
        let mut helper = receive.recv().unwrap();
        assert_ne!(helper.creator, unsafe { libc::getpid() } as i64);
        assert!(unsafe { creator_alive(helper.creator_pidfd.as_raw_fd()) });
        assert!(helper.same_thread().is_err());
        peek_actual_ready(&helper);
        assert!(!helper.started && !helper.ready);
        finish.send(()).unwrap();
        thread.join().unwrap();
        // clear_child_tid wakes pthread_join from exit_mm_release, before
        // exit_notify publishes exit_state and wakes the PIDFD. Require the
        // actual readable PIDFD within the same short retirement bound.
        let end = Instant::now() + Duration::from_secs(3);
        loop {
            let left = end.saturating_duration_since(Instant::now());
            assert!(
                !left.is_zero(),
                "creator thread PIDFD exit was not observed"
            );
            let mut poll = libc::pollfd {
                fd: helper.creator_pidfd.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            let count = unsafe { libc::poll(&mut poll, 1, left.as_millis().clamp(1, 50) as i32) };
            if count < 0 && io::Error::last_os_error().kind() == io::ErrorKind::Interrupted {
                continue;
            }
            assert!(count >= 0 && poll.revents & (libc::POLLNVAL | libc::POLLERR) == 0);
            if poll.revents & libc::POLLIN != 0 {
                break;
            }
        }
        assert!(!unsafe { creator_alive(helper.creator_pidfd.as_raw_fd()) });
        // This test deliberately observes from another still-live group
        // thread. Production never transfers the helper's owner to it.
        loop {
            let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
            assert_eq!(
                unsafe {
                    libc::waitid(
                        libc::P_PIDFD,
                        helper.pidfd.as_ref().unwrap().as_raw_fd() as u32,
                        &mut info,
                        libc::WEXITED | libc::WNOHANG,
                    )
                },
                0
            );
            if unsafe { info.si_pid() } != 0 {
                assert_eq!(unsafe { info.si_pid() }, helper.pid);
                assert_eq!(
                    (info.si_code, unsafe { info.si_status() }),
                    (libc::CLD_KILLED, libc::SIGKILL)
                );
                helper.exit = Some((info.si_code, unsafe { info.si_status() }));
                break;
            }
            assert!(
                Instant::now() < end,
                "original creator death did not kill its child"
            );
            let mut poll = libc::pollfd {
                fd: helper.pidfd.as_ref().unwrap().as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            assert!(unsafe { libc::poll(&mut poll, 1, 20) } >= 0);
        }
        assert!(unsafe { libc::getpid() } > 1);
        assert!(!helper.started);
    }

    #[test]
    fn apex_mount_helper_native_statfs_matches_the_actual_kernel_descriptor() {
        let file = tempfile::tempfile().unwrap();
        let mut raw: KernelStatfs = unsafe { std::mem::zeroed() };
        assert_eq!(
            unsafe { libc::syscall(libc::SYS_fstatfs, file.as_raw_fd(), &mut raw) },
            0
        );
        let mut vfs: libc::statvfs = unsafe { std::mem::zeroed() };
        assert_eq!(unsafe { libc::fstatvfs(file.as_raw_fd(), &mut vfs) }, 0);
        assert_eq!(raw.kind, fs_type(&file).unwrap());
        assert_eq!(raw.blocks, vfs.f_blocks as u64);
        assert_eq!(raw.files, vfs.f_files as u64);
        assert_eq!(
            raw.flags as u64 & (READONLY_FLAGS | 8 | 1024),
            vfs.f_flag as u64 & (READONLY_FLAGS | 8 | 1024)
        );
    }

    #[test]
    fn apex_mount_helper_unreleased_child_is_reaped_before_custody_release() {
        let directory = tempfile::tempdir().unwrap();
        let file = File::open(directory.path()).unwrap();
        let expected = ExpectedNode::of(&file).unwrap();
        let mut helper = Helper::spawn(
            [&file; 4],
            [expected; 3],
            Instant::now() + Duration::from_secs(3),
        )
        .unwrap();
        assert!(!helper.started && !helper.ready && !helper.reap_if_exited().unwrap());
        helper.retire().unwrap();
        assert_eq!(helper.exit, Some((libc::CLD_KILLED, libc::SIGKILL)));
        helper.retire().unwrap();
        assert!(helper.start().is_err());
    }

    #[test]
    fn apex_mount_helper_success_requires_exact_reply_and_real_exit_agreement() {
        let good = Reply {
            magic: REPLY_MAGIC,
            stage: 9,
            errno: 0,
            reserved: 0,
        };
        validate_outcome(good, (libc::CLD_EXITED, 0)).unwrap();
        for exit in [
            (libc::CLD_EXITED, 125),
            (libc::CLD_KILLED, 0),
            (libc::CLD_KILLED, 9),
            (libc::CLD_DUMPED, 11),
        ] {
            assert!(validate_outcome(good, exit).is_err());
        }
        for row in [
            Reply { magic: 0, ..good },
            Reply { stage: 8, ..good },
            Reply {
                reserved: 1,
                ..good
            },
            Reply { errno: -1, ..good },
            Reply {
                errno: 4096,
                ..good
            },
        ] {
            assert!(validate_outcome(row, (libc::CLD_EXITED, 0)).is_err());
        }
        assert!(
            matches!(validate_outcome(Reply { errno: libc::EPERM, ..good }, (libc::CLD_EXITED, 125)),
            Err(MountError::Io(error)) if error.raw_os_error() == Some(libc::EPERM))
        );
    }

    #[test]
    fn apex_mount_helper_rejects_actual_completed_reply_after_original_deadline() {
        let directory = tempfile::tempdir().unwrap();
        let file = File::open(directory.path()).unwrap();
        let expected = ExpectedNode::of(&file).unwrap();
        let end = Instant::now() + Duration::from_secs(3);
        let mut helper = Helper::spawn([&file; 4], [expected; 3], end).unwrap();
        helper.start().unwrap();
        loop {
            helper.receive().unwrap();
            if helper.reap_if_exited().unwrap() {
                helper.receive().unwrap();
                break;
            }
            assert!(Instant::now() < end, "actual helper exit did not arrive");
            std::thread::yield_now();
        }
        assert_eq!(helper.reply.unwrap().stage, 4);
        assert_eq!(helper.reply.unwrap().errno, libc::EPERM);
        assert_eq!(helper.exit, Some((libc::CLD_EXITED, 125)));
        assert!(matches!(
            helper.complete(end + Duration::from_secs(1)),
            Err(MountError::Rejected(
                "mount helper cannot extend its original deadline"
            ))
        ));
        std::thread::sleep(
            end.saturating_duration_since(Instant::now()) + Duration::from_millis(2),
        );
        assert!(matches!(
            helper.complete(end),
            Err(MountError::Rejected(
                "actual mount helper completion deadline"
            ))
        ));
        helper.retire().unwrap();
        assert_eq!(helper.exit, Some((libc::CLD_EXITED, 125)));
    }

    #[test]
    fn apex_mount_helper_rejects_real_ordinary_directory_and_reaps_its_original_pidfd() {
        let directory = tempfile::tempdir().unwrap();
        let file = File::open(directory.path()).unwrap();
        let expected = ExpectedNode::of(&file).unwrap();
        let end = Instant::now() + Duration::from_secs(3);
        let mut helper = Helper::spawn([&file; 4], [expected; 3], end).unwrap();
        assert!(!helper.started && helper.exit.is_none());
        peek_actual_ready(&helper);
        assert!(!helper.started && !helper.ready && !helper.reap_if_exited().unwrap());
        helper.start().unwrap();
        assert!(helper.ready && helper.started);
        assert!(helper.complete(end).is_err());
        assert_eq!(helper.reply.unwrap().stage, 4);
        assert_eq!(helper.reply.unwrap().errno, libc::EPERM);
        assert_eq!(helper.exit, Some((libc::CLD_EXITED, 125)));
        helper.retire().unwrap();
        assert!(helper.start().is_err());
    }
}
