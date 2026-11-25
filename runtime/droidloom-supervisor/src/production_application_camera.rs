//! The original production MainPID owns and reaps one fixed capture image.
use super::{ApplicationError, Result, external, query_io, reject, require};
#[path = "production_camera_device.rs"]
mod device;
#[path = "production_camera_filter.rs"]
mod filter;
#[path = "production_camera_mac.rs"]
mod mac;
#[path = "production_camera_runtime.rs"]
mod runtime;
#[path = "production_camera_wire.rs"]
mod wire;
use std::fs::File;
use std::io;
use std::mem;
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::MetadataExt;
use std::time::{Duration, Instant};
const ARGUMENT: &std::ffi::CStr = c"__production-camera-capture";
const INITIALIZE: Duration = Duration::from_secs(5);
pub(crate) struct CameraOwner {
    child: query_io::Child,
    channel: File,
    proof: File,
    owner: File,
    init: File,
    retired: bool,
}
fn same_pidfd(a: &File, b: &File) -> Result<()> {
    let a = a.metadata()?;
    let b = b.metadata()?;
    require(
        a.dev() == b.dev() && a.ino() == b.ino(),
        "camera original PIDFD identity differs",
    )
}
impl CameraOwner {
    pub(crate) fn start(listener: &File, init: &File, uid: u32, gid: u32) -> Result<Self> {
        query_io::own_root_credentials()?;
        query_io::mac_context(mac::BROKER)?;
        require(
            uid >= 65536 && gid >= 65536,
            "camera selected mapped root identities differ",
        )?;
        super::worker::require_wait_semantics()?;
        let original = query_io::pidfd_info(init)?;
        query_io::alive(init)?;
        mac::exact_ids(&original, uid, gid)?;
        // The new handle is only an observer of the original owner's PIDFS
        // object, never a replacement namespace/reaper authority.
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, original.pid, 0u32) };
        if raw < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let init_observer = unsafe { File::from_raw_fd(raw as i32) };
        same_pidfd(init, &init_observer)?;
        query_io::alive(init)?;
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, libc::getpid(), 0u32) };
        if raw < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let owner = unsafe { File::from_raw_fd(raw as i32) };
        let executable =
            crate::production_host_admission::application_worker_executable().map_err(external)?;
        let executable = query_io::above_reserved(&executable)?;
        let (channel, child_channel) = super::protocol::socketpair()?;
        let channel = File::from(channel);
        let child_channel = query_io::above_reserved(&File::from(child_channel))?;
        let stdio = query_io::fixed_stdio()?;
        let mut nonce = [0u8; 16];
        let mut offset = 0;
        while offset < nonce.len() {
            let n = unsafe {
                libc::getrandom(nonce[offset..].as_mut_ptr().cast(), nonce.len() - offset, 0)
            };
            if n < 0 {
                if io::Error::last_os_error().kind() == io::ErrorKind::Interrupted {
                    continue;
                }
                return Err(io::Error::last_os_error().into());
            }
            require(n > 0, "camera nonce unavailable")?;
            offset += n as usize;
        }
        require(nonce != [0; 16], "camera nonce is zero")?;
        let deadline = Instant::now() + INITIALIZE;
        let request = wire::Wire {
            phase: wire::INITIALIZE,
            uid,
            gid,
            error: 0,
            nonce,
            deadline_ns: super::protocol::monotonic_ns()?
                .checked_add(INITIALIZE.as_nanos() as u64)
                .ok_or_else(|| reject("camera initialization deadline overflow"))?,
        };
        let program = filter::program(Some(executable.as_raw_fd()));
        let fprog = libc::sock_fprog {
            len: program.len() as u16,
            filter: program.as_ptr().cast_mut(),
        };
        let argv = [
            c"droidloom-owned-camera".as_ptr(),
            ARGUMENT.as_ptr(),
            std::ptr::null(),
        ];
        let env = [c"LC_ALL=C".as_ptr(), std::ptr::null()];
        let parent = unsafe { libc::getpid() };
        let mut raw_pidfd = -1i32;
        let args = super::worker::CloneArgs {
            flags: libc::CLONE_PIDFD as u64,
            pidfd: (&mut raw_pidfd as *mut i32) as u64,
            exit_signal: libc::SIGCHLD as u64,
            ..super::worker::CloneArgs::default()
        };
        let mut mask = super::worker::SignalMask::block()?;
        let pid = unsafe { libc::syscall(libc::SYS_clone3, &args, mem::size_of_val(&args)) };
        if pid < 0 {
            return Err(io::Error::last_os_error().into());
        }
        if pid == 0 {
            unsafe {
                query_io::bootstrap(
                    query_io::HelperRole::NativeCamera,
                    parent,
                    executable.as_raw_fd(),
                    child_channel.as_raw_fd(),
                    stdio.as_raw_fd(),
                    argv.as_ptr(),
                    env.as_ptr(),
                    &fprog,
                )
            }
        }
        if raw_pidfd < 0 {
            return Err(ApplicationError::RetirementUnproven);
        }
        let child = query_io::Child {
            pid: pid as u32,
            pidfd: Some(unsafe { File::from_raw_fd(raw_pidfd) }),
            terminal: None,
        };
        drop(child_channel);
        mask.restore()?;
        let info = query_io::pidfd_info(child.pidfd.as_ref().unwrap())?;
        require(
            info.pid == child.pid && info.ppid == parent as u32,
            "camera atomic child identity differs",
        )?;
        wire::send(
            channel.as_raw_fd(),
            request,
            &[
                owner.as_raw_fd(),
                init_observer.as_raw_fd(),
                listener.as_raw_fd(),
            ],
            deadline,
        )?;
        let ready = wire::receive(channel.as_raw_fd(), 1, deadline)?;
        require(
            ready.peer.pid == pid as i32
                && ready.peer.uid == 0
                && ready.peer.gid == 0
                && ready.wire
                    == wire::Wire {
                        phase: wire::READY,
                        ..request
                    },
            "camera authenticated child initialization differs",
        )?;
        let proof = ready.files.into_iter().next().unwrap();
        let result = Self {
            child,
            channel,
            proof,
            owner,
            init: init_observer,
            retired: false,
        };
        result.verify()?;
        Ok(result)
    }
    fn verify(&self) -> Result<()> {
        require(!self.retired, "camera original owner was already retired")?;
        query_io::mac_context(mac::BROKER)?;
        query_io::alive(&self.owner)?;
        query_io::alive(&self.init)?;
        let original = self
            .child
            .pidfd
            .as_ref()
            .ok_or_else(|| reject("camera PIDFD custody lost"))?;
        query_io::alive(original)?;
        let (observed, credential) = mac::peer_pidfd(self.proof.as_raw_fd())?;
        same_pidfd(original, &observed)?;
        let info = query_io::pidfd_info(&observed)?;
        mac::exact_ids(&info, 0, 0)?;
        require(
            credential.pid as u32 == self.child.pid
                && credential.uid == 0
                && credential.gid == 0
                && info.ppid == unsafe { libc::getpid() } as u32
                && mac::peer(self.proof.as_raw_fd(), mac::SELINUX)? == mac::CAPTURE
                && mac::capture_stack(&mac::peer(self.proof.as_raw_fd(), mac::APPARMOR)?),
            "camera proof is not the actual fixed child and enforced MAC intersection",
        )?;
        query_io::alive(original)
    }
    pub(crate) fn progress(&mut self) -> Result<()> {
        require(
            !self.child.observe()?,
            "camera original child exited outside normal retirement",
        )?;
        self.verify()
    }
    pub(crate) fn retire(&mut self) -> Result<()> {
        if self.retired {
            return Ok(());
        }
        self.verify()?;
        let deadline = Instant::now() + Duration::from_secs(5);
        loop {
            let n = unsafe {
                libc::send(
                    self.channel.as_raw_fd(),
                    wire::STOP.as_ptr().cast(),
                    wire::STOP.len(),
                    libc::MSG_DONTWAIT | libc::MSG_NOSIGNAL,
                )
            };
            if n == wire::STOP.len() as isize {
                break;
            }
            if n < 0
                && matches!(
                    io::Error::last_os_error().kind(),
                    io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
                )
            {
                wire::wait(self.channel.as_raw_fd(), libc::POLLOUT, deadline)?;
                continue;
            }
            return Err(reject(
                "camera owner stop was not delivered to its original child",
            ));
        }
        self.child.finish(deadline)?;
        require(
            self.child.terminal == Some((libc::CLD_EXITED, 0)),
            "camera did not actually retire normally",
        )?;
        self.retired = true;
        Ok(())
    }
}
impl Drop for CameraOwner {
    fn drop(&mut self) {
        if !self.retired {
            let _ = self.retire();
        }
    }
}
pub(super) fn entry() -> Result<()> {
    runtime::entry()
}

/// No command-line device, PID, profile, UID or frame is an authority.
pub(super) fn dispatch(arguments: &[std::ffi::OsString]) -> Result<bool> {
    let selected = arguments
        .first()
        .is_some_and(|a| a == "__production-camera-capture");
    if selected {
        require(arguments.len() == 1, "camera capture accepts no parameters")?;
        entry()?;
        return Ok(true);
    }
    match mac::current(mac::SELINUX) {
        Ok(role) => {
            require(
                role != mac::CAPTURE,
                "the capture role cannot select another daemon entry",
            )?;
            Ok(false)
        }
        // The private entry above always requires the real provider. Ordinary
        // nonproduction CLI use is still possible on a host without SELinux.
        Err(ApplicationError::Io(error))
            if matches!(error.raw_os_error(), Some(libc::ENOSYS | libc::EOPNOTSUPP)) =>
        {
            Ok(false)
        }
        Err(error) => Err(error),
    }
}
