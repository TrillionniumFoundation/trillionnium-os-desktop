//! A single bounded kernel NOTIF_RECV, with actual atomic PIDFD custody.
//!
//! Linux 6.18 NOTIF_RECV can wait after a poll wakeup is invalidated; setting
//! O_NONBLOCK does not change that ioctl. Only this disposable raw child may
//! block. Its original owner keeps the PIDFD and kills/reaps it at deadline.
//! No mount/device operation or notification response runs in this child.
use crate::production_apex_seccomp::{Notification, RECV};
use std::fs::File;
use std::io;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::time::{Duration, Instant};

const READY: u32 = 0x504e_5230;
const RESULT: u32 = 0x504e_5231;
const RETIREMENT: Duration = Duration::from_secs(2);

#[repr(C)]
#[derive(Clone, Copy, Default)]
struct Header {
    magic: u32,
    error: i32,
    reserved: [u32; 2],
}
#[repr(C)]
#[derive(Clone, Copy, Default)]
struct Reply {
    header: Header,
    notification: Notification,
}
const _: [(); 96] = [(); std::mem::size_of::<Reply>()];

fn require(value: bool, reason: &'static str) -> io::Result<()> {
    if value {
        Ok(())
    } else {
        Err(io::Error::other(reason))
    }
}
fn rc(value: i32) -> io::Result<()> {
    if value == 0 {
        Ok(())
    } else {
        Err(io::Error::last_os_error())
    }
}
unsafe fn alive(fd: RawFd) -> bool {
    let mut p = libc::pollfd {
        fd,
        events: libc::POLLIN,
        revents: 0,
    };
    unsafe { libc::syscall(libc::SYS_poll, &mut p, 1, 0) == 0 && p.revents == 0 }
}

/// This is an owned child, never a worker adopted from an external PID.
pub(super) struct Receiver {
    pidfd: Option<OwnedFd>,
    creator_pidfd: OwnedFd,
    socket: OwnedFd,
    pid: i32,
    creator: i64,
    end: Instant,
    released: bool,
    preparation_error: Option<i32>,
    reply: Option<Reply>,
    exit: Option<(i32, i32)>,
}

impl Receiver {
    /// Caller stores the result in the same original resource before start.
    pub(super) fn spawn(listener: &File, end: Instant) -> io::Result<Self> {
        require(Instant::now() < end, "notification receive deadline")?;
        let mut clock: libc::timespec = unsafe { std::mem::zeroed() };
        rc(unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut clock) })?;
        let deadline = u64::try_from(clock.tv_sec)
            .ok()
            .and_then(|s| s.checked_mul(1_000_000_000))
            .and_then(|s| s.checked_add(u64::try_from(clock.tv_nsec).ok()?))
            .and_then(|s| {
                s.checked_add(
                    u64::try_from(end.saturating_duration_since(Instant::now()).as_nanos()).ok()?,
                )
            })
            .ok_or_else(|| io::Error::other("notification clock overflow"))?;
        let creator = unsafe { libc::syscall(libc::SYS_gettid) };
        let parent = unsafe { libc::getpid() };
        require(creator > 1 && parent > 1, "notification receiver host PID1")?;
        let mut action: libc::sigaction = unsafe { std::mem::zeroed() };
        rc(unsafe { libc::sigaction(libc::SIGCHLD, std::ptr::null(), &mut action) })?;
        require(
            action.sa_sigaction == libc::SIG_DFL && action.sa_flags & libc::SA_NOCLDWAIT == 0,
            "notification receiver requires original parent reaping",
        )?;
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, creator, libc::O_EXCL) };
        if raw < 0 {
            return Err(io::Error::last_os_error());
        }
        let creator_pidfd = unsafe { OwnedFd::from_raw_fd(raw as i32) };
        let mut info = crate::production_activation_protocol::PidfdInfo::request_exit();
        info.mask = 3;
        rc(unsafe {
            libc::ioctl(
                creator_pidfd.as_raw_fd(),
                crate::production_activation_protocol::PIDFD_GET_INFO as libc::c_ulong,
                &mut info,
            )
        })?;
        require(
            info.mask & 3 == 3 && info.pid == creator as u32 && info.tgid == parent as u32,
            "notification receiver original creator PIDFD",
        )?;
        require(
            unsafe { alive(creator_pidfd.as_raw_fd()) },
            "notification creator exited",
        )?;
        let mut pair = [-1; 2];
        rc(unsafe {
            libc::socketpair(
                libc::AF_UNIX,
                libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
                0,
                pair.as_mut_ptr(),
            )
        })?;
        let socket = unsafe { OwnedFd::from_raw_fd(pair[0]) };
        let child = unsafe { OwnedFd::from_raw_fd(pair[1]) };
        let all = u64::MAX;
        let mut previous = 0_u64;
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
            return Err(io::Error::last_os_error());
        }
        let mut pidfd = -1;
        let mut args = [0_u64; 11];
        args[0] = libc::CLONE_PIDFD as u64;
        args[1] = (&mut pidfd as *mut i32) as u64;
        args[4] = libc::SIGCHLD as u64;
        let pid = unsafe {
            libc::syscall(
                libc::SYS_clone3,
                args.as_ptr(),
                std::mem::size_of_val(&args),
            )
        };
        if pid == 0 {
            unsafe {
                child_receive(
                    listener.as_raw_fd(),
                    creator_pidfd.as_raw_fd(),
                    child.as_raw_fd(),
                    parent,
                    deadline,
                )
            }
        }
        let error = if pid < 0 {
            Some(io::Error::last_os_error())
        } else {
            None
        };
        let restored = unsafe {
            libc::syscall(
                libc::SYS_rt_sigprocmask,
                libc::SIG_SETMASK,
                &previous,
                std::ptr::null::<u64>(),
                8,
            )
        };
        let preparation_error = if restored != 0 {
            Some(
                io::Error::last_os_error()
                    .raw_os_error()
                    .unwrap_or(libc::EIO),
            )
        } else {
            None
        };
        drop(child);
        if let Some(error) = error {
            return Err(error);
        }
        require(
            pidfd >= 0 && pid <= i32::MAX as i64,
            "notification clone3 atomic PIDFD missing",
        )?;
        Ok(Self {
            pidfd: Some(unsafe { OwnedFd::from_raw_fd(pidfd) }),
            creator_pidfd,
            socket,
            pid: pid as i32,
            creator,
            end,
            released: false,
            preparation_error,
            reply: None,
            exit: None,
        })
    }

    fn same_thread(&self) -> io::Result<()> {
        require(
            unsafe { libc::syscall(libc::SYS_gettid) } == self.creator
                && unsafe { alive(self.creator_pidfd.as_raw_fd()) },
            "notification receiver owner thread changed",
        )
    }

    fn wait(&self, end: Instant) -> io::Result<()> {
        self.wait_for(end, 50)
    }

    fn wait_for(&self, end: Instant, maximum_ms: u128) -> io::Result<()> {
        self.same_thread()?;
        let left = end.saturating_duration_since(Instant::now());
        require(!left.is_zero(), "notification receive deadline exceeded")?;
        let mut p = [
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
                p.as_mut_ptr(),
                p.len() as _,
                left.as_millis().clamp(1, maximum_ms) as i32,
            )
        };
        if count < 0 && io::Error::last_os_error().kind() != io::ErrorKind::Interrupted {
            return Err(io::Error::last_os_error());
        }
        require(
            !p.iter().any(|p| p.revents & libc::POLLNVAL != 0),
            "notification receiver descriptor invalid",
        )
    }

    pub(super) fn start(&mut self) -> io::Result<()> {
        self.same_thread()?;
        require(
            !self.released && self.exit.is_none(),
            "notification receiver already released/reaped",
        )?;
        if let Some(error) = self.preparation_error {
            return Err(io::Error::from_raw_os_error(error));
        }
        loop {
            require(Instant::now() < self.end, "notification READY deadline")?;
            let mut header = Header::default();
            let count = unsafe {
                libc::recv(
                    self.socket.as_raw_fd(),
                    (&mut header as *mut Header).cast(),
                    std::mem::size_of::<Header>(),
                    libc::MSG_DONTWAIT | libc::MSG_TRUNC,
                )
            };
            if count >= 0 {
                require(
                    count == std::mem::size_of::<Header>() as isize
                        && header.magic == READY
                        && header.error == 0
                        && header.reserved == [0; 2],
                    "notification child did not reach post-PDEATHSIG READY",
                )?;
                break;
            }
            let error = io::Error::last_os_error();
            if ![Some(libc::EAGAIN), Some(libc::EINTR)].contains(&error.raw_os_error()) {
                return Err(error);
            }
            self.wait(self.end)?;
        }
        // Same still-executing creator must cross the child's PDEATHSIG
        // barrier, including Linux 6.18's delayed leader-PIDFD exit window.
        self.same_thread()?;
        require(Instant::now() < self.end, "notification release deadline")?;
        let release = 1_u8;
        let count = unsafe {
            libc::send(
                self.socket.as_raw_fd(),
                (&release as *const u8).cast(),
                1,
                libc::MSG_NOSIGNAL | libc::MSG_DONTWAIT,
            )
        };
        if count < 0 {
            return Err(io::Error::last_os_error());
        }
        require(count == 1, "notification receiver release packet")?;
        self.released = true;
        Ok(())
    }

    fn reap(&mut self) -> io::Result<bool> {
        self.same_thread()?;
        if self.exit.is_some() {
            return Ok(true);
        }
        let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
        rc(unsafe {
            libc::waitid(
                libc::P_PIDFD,
                self.pidfd.as_ref().unwrap().as_raw_fd() as u32,
                &mut info,
                libc::WEXITED | libc::WNOHANG,
            )
        })?;
        if unsafe { info.si_pid() } == 0 {
            return Ok(false);
        }
        require(
            unsafe { info.si_pid() } == self.pid
                && [libc::CLD_EXITED, libc::CLD_KILLED, libc::CLD_DUMPED].contains(&info.si_code),
            "notification original PIDFD reap differs",
        )?;
        self.exit = Some((info.si_code, unsafe { info.si_status() }));
        Ok(true)
    }

    fn receive_reply(&mut self) -> io::Result<()> {
        if self.reply.is_some() {
            return Ok(());
        }
        let mut reply = Reply::default();
        let n = unsafe {
            libc::recv(
                self.socket.as_raw_fd(),
                (&mut reply as *mut Reply).cast(),
                std::mem::size_of::<Reply>(),
                libc::MSG_DONTWAIT | libc::MSG_TRUNC,
            )
        };
        if n < 0 {
            let e = io::Error::last_os_error();
            if [Some(libc::EAGAIN), Some(libc::EINTR)].contains(&e.raw_os_error()) {
                return Ok(());
            }
            return Err(e);
        }
        require(
            n == std::mem::size_of::<Reply>() as isize
                && reply.header.magic == RESULT
                && reply.header.reserved == [0; 2]
                && (0..=4095).contains(&reply.header.error),
            "notification receiver result packet",
        )?;
        self.reply = Some(reply);
        Ok(())
    }

    pub(super) fn complete(&mut self) -> io::Result<Notification> {
        self.complete_with_progress(None)
    }

    // The original init may be stopped at an actual syscall entry/exit while
    // this separate bounded worker waits in NOTIF_RECV. Pump only the already
    // owned tracer; the receiver's real result, exit and deadline stay required.
    pub(super) fn complete_with_progress(
        &mut self,
        mut progress: Option<&mut dyn FnMut() -> io::Result<()>>,
    ) -> io::Result<Notification> {
        self.same_thread()?;
        require(
            Instant::now() < self.end,
            "notification result arrived after its absolute deadline",
        )?;
        require(self.released, "notification receiver barrier not released")?;
        loop {
            if let Some(progress) = progress.as_mut() {
                progress()?;
            }
            self.receive_reply()?;
            if self.reap()? {
                self.receive_reply()?;
                let reply = self.reply.ok_or_else(|| {
                    io::Error::other("notification receiver reaped without result")
                })?;
                require(
                    self.exit
                        == Some((
                            libc::CLD_EXITED,
                            if reply.header.error == 0 { 0 } else { 125 },
                        )),
                    "notification result differs from actual original PIDFD exit",
                )?;
                if reply.header.error != 0 {
                    return Err(io::Error::from_raw_os_error(reply.header.error));
                }
                require(
                    reply.notification.operation().is_some(),
                    "notification kernel ABI/operation differs",
                )?;
                require(
                    Instant::now() < self.end,
                    "notification result acceptance exceeded its absolute deadline",
                )?;
                return Ok(reply.notification);
            }
            self.wait_for(self.end, if progress.is_some() { 1 } else { 50 })?;
        }
    }

    pub(super) fn retire(&mut self) -> io::Result<()> {
        self.same_thread()?;
        if self.reap()? {
            return Ok(());
        }
        if unsafe {
            libc::syscall(
                libc::SYS_pidfd_send_signal,
                self.pidfd.as_ref().unwrap().as_raw_fd(),
                libc::SIGKILL,
                std::ptr::null::<libc::siginfo_t>(),
                0,
            )
        } != 0
            && io::Error::last_os_error().raw_os_error() != Some(libc::ESRCH)
        {
            return Err(io::Error::last_os_error());
        }
        let end = Instant::now() + RETIREMENT;
        while !self.reap()? {
            self.wait(end)?;
        }
        Ok(())
    }
}

impl Drop for Receiver {
    fn drop(&mut self) {
        if self.exit.is_none() {
            if let Some(fd) = self.pidfd.take() {
                std::mem::forget(fd);
            }
        }
    }
}

unsafe fn finish(socket: RawFd, error: i32, notification: Notification) -> ! {
    let reply = Reply {
        header: Header {
            magic: RESULT,
            error,
            reserved: [0; 2],
        },
        notification,
    };
    unsafe {
        libc::syscall(
            libc::SYS_sendto,
            socket,
            &reply,
            std::mem::size_of::<Reply>(),
            libc::MSG_DONTWAIT | libc::MSG_NOSIGNAL,
            std::ptr::null::<libc::sockaddr>(),
            0,
        );
        libc::syscall(libc::SYS_exit_group, if error == 0 { 0 } else { 125 });
        std::hint::unreachable_unchecked()
    }
}
unsafe fn fail(socket: RawFd) -> ! {
    let error = unsafe { *libc::__errno_location() };
    unsafe {
        finish(
            socket,
            if (1..=4095).contains(&error) {
                error
            } else {
                libc::EIO
            },
            Notification::default(),
        )
    }
}

unsafe fn restrict_receive(listener: RawFd, channel: RawFd) -> i32 {
    const fn i(code: u16, jt: u8, jf: u8, k: u32) -> libc::sock_filter {
        libc::sock_filter { code, jt, jf, k }
    }
    const ALLOW: u32 = 0x7fff_0000;
    const KILL: u32 = 0x8000_0000;
    let filter = [
        i(0x20, 0, 0, 4),
        i(0x15, 1, 0, 0xc000_003e),
        i(0x06, 0, 0, KILL),
        i(0x20, 0, 0, 0),
        i(0x15, 0, 1, libc::SYS_exit_group as u32),
        i(0x06, 0, 0, ALLOW),
        i(0x15, 0, 8, libc::SYS_ioctl as u32),
        i(0x20, 0, 0, 16),
        i(0x15, 0, 4, listener as u32),
        i(0x20, 0, 0, 24),
        i(0x15, 0, 2, RECV as u32),
        i(0x20, 0, 0, 28),
        i(0x15, 1, 0, 0),
        i(0x06, 0, 0, KILL),
        i(0x06, 0, 0, ALLOW),
        i(0x15, 0, 4, libc::SYS_sendto as u32),
        i(0x20, 0, 0, 16),
        i(0x15, 0, 2, channel as u32),
        i(0x06, 0, 0, ALLOW),
        i(0x06, 0, 0, KILL),
        i(0x06, 0, 0, KILL),
    ];
    let program = libc::sock_fprog {
        len: filter.len() as u16,
        filter: filter.as_ptr().cast_mut(),
    };
    unsafe {
        if libc::syscall(libc::SYS_prctl, libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0 {
            return *libc::__errno_location();
        }
        if libc::syscall(libc::SYS_seccomp, 1, 0, &program) != 0 {
            return *libc::__errno_location();
        }
    }
    0
}

unsafe fn before_deadline(channel: RawFd, creator: RawFd, deadline: u64) {
    unsafe {
        if !alive(creator) {
            finish(channel, libc::ESRCH, Notification::default());
        }
        let mut clock: libc::timespec = std::mem::zeroed();
        if libc::syscall(libc::SYS_clock_gettime, libc::CLOCK_MONOTONIC, &mut clock) != 0 {
            fail(channel);
        }
        let value = u64::try_from(clock.tv_sec)
            .ok()
            .and_then(|s| s.checked_mul(1_000_000_000))
            .and_then(|s| s.checked_add(u64::try_from(clock.tv_nsec).ok()?));
        if !(0..1_000_000_000).contains(&clock.tv_nsec) || value.is_none_or(|v| v >= deadline) {
            finish(channel, libc::ETIMEDOUT, Notification::default());
        }
    }
}

unsafe fn child_receive(
    listener: RawFd,
    creator: RawFd,
    socket: RawFd,
    parent: i32,
    deadline: u64,
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
            || !alive(creator)
        {
            fail(socket);
        }
        let mut keep = [-1; 3];
        for (index, fd) in [listener, creator, socket].into_iter().enumerate() {
            let copy = libc::syscall(libc::SYS_fcntl, fd, libc::F_DUPFD_CLOEXEC, 128);
            if copy < 128 || copy > i32::MAX as i64 {
                fail(socket);
            }
            keep[index] = copy as i32;
        }
        let channel = keep[2];
        let mut low = 0_u32;
        for fd in keep {
            if low < fd as u32 && libc::syscall(libc::SYS_close_range, low, fd as u32 - 1, 0) != 0 {
                fail(channel);
            }
            low = fd as u32 + 1;
        }
        if libc::syscall(libc::SYS_close_range, low, u32::MAX, 0) != 0 || !alive(keep[1]) {
            fail(channel);
        }
        before_deadline(channel, keep[1], deadline);
        let ready = Header {
            magic: READY,
            error: 0,
            reserved: [0; 2],
        };
        if libc::syscall(
            libc::SYS_sendto,
            channel,
            &ready,
            std::mem::size_of::<Header>(),
            libc::MSG_DONTWAIT | libc::MSG_NOSIGNAL,
            std::ptr::null::<libc::sockaddr>(),
            0,
        ) != std::mem::size_of::<Header>() as i64
        {
            fail(channel);
        }
        loop {
            before_deadline(channel, keep[1], deadline);
            let mut release = [0_u8; 2];
            let count = libc::syscall(
                libc::SYS_recvfrom,
                channel,
                release.as_mut_ptr(),
                release.len(),
                libc::MSG_DONTWAIT | libc::MSG_TRUNC,
                std::ptr::null::<libc::sockaddr>(),
                std::ptr::null::<libc::socklen_t>(),
            );
            if count == 1 && release[0] == 1 {
                break;
            }
            if count >= 0 {
                finish(channel, libc::EPROTO, Notification::default());
            }
            if *libc::__errno_location() != libc::EAGAIN && *libc::__errno_location() != libc::EINTR
            {
                fail(channel);
            }
            let mut p = libc::pollfd {
                fd: channel,
                events: libc::POLLIN,
                revents: 0,
            };
            libc::syscall(libc::SYS_poll, &mut p, 1, 20);
        }
        let policy = restrict_receive(keep[0], channel);
        if policy != 0 {
            finish(channel, policy, Notification::default());
        }
        let mut notification = Notification::default();
        if libc::syscall(libc::SYS_ioctl, keep[0], RECV, &mut notification) != 0 {
            fail(channel);
        }
        finish(channel, 0, notification)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::process::ExitStatusExt;

    #[test]
    fn apex_notification_receiver_rejects_actual_completed_reply_after_its_original_deadline() {
        let (listener, release, task) = super::super::tests::actual_listener();
        let end = Instant::now() + Duration::from_secs(3);
        let mut receiver = Receiver::spawn(&listener, end).unwrap();
        release.send(true).unwrap();
        receiver.start().unwrap();
        while receiver.reply.is_none() {
            receiver.receive_reply().unwrap();
            if receiver.reply.is_none() {
                receiver.wait(end).unwrap();
            }
        }
        while !receiver.reap().unwrap() {
            receiver.wait(end).unwrap();
        }
        assert_eq!(receiver.exit, Some((libc::CLD_EXITED, 0)));
        let notification = receiver.reply.unwrap().notification;
        std::thread::sleep(
            end.saturating_duration_since(Instant::now()) + Duration::from_millis(1),
        );
        assert!(receiver.complete().is_err());
        receiver.retire().unwrap();
        // Actual negative response only for retiring the controlled task;
        // the late result above is never accepted as a production request.
        let response = crate::production_apex_seccomp::Response {
            id: notification.id,
            value: 0,
            error: -libc::EACCES,
            flags: 0,
        };
        assert_eq!(
            unsafe {
                libc::ioctl(
                    listener.as_raw_fd(),
                    crate::production_apex_seccomp::SEND,
                    &response,
                )
            },
            0
        );
        assert_eq!(task.join().unwrap(), (-1, libc::EACCES));
    }

    #[test]
    fn apex_notification_receiver_actual_filter_kills_an_unrelated_syscall() {
        const MARKER: &str = "DROIDLOOM_APEX_RECEIVE_FILTER_CONTROL";
        if std::env::var_os(MARKER).is_some() {
            let limit = libc::rlimit {
                rlim_cur: 0,
                rlim_max: 0,
            };
            assert_eq!(unsafe { libc::setrlimit(libc::RLIMIT_CORE, &limit) }, 0);
            let file = File::open("/dev/null").unwrap();
            let error = unsafe { restrict_receive(file.as_raw_fd(), file.as_raw_fd()) };
            if error != 0 {
                unsafe {
                    libc::syscall(libc::SYS_exit_group, 124);
                }
            }
            // This is a real syscall after installing the actual receiver's
            // filter. A wrong BPF branch must not silently allow it.
            unsafe {
                libc::syscall(libc::SYS_getpid);
                libc::syscall(libc::SYS_exit_group, 123);
            }
            unreachable!();
        }
        let output = std::process::Command::new(std::env::current_exe().unwrap())
            .args(["--exact", "production_namespace::tree::apex_notifications::receiver::tests::apex_notification_receiver_actual_filter_kills_an_unrelated_syscall", "--test-threads=1"])
            .env(MARKER, "1")
            .output().unwrap();
        assert_eq!(output.status.signal(), Some(libc::SIGSYS));
    }
}
