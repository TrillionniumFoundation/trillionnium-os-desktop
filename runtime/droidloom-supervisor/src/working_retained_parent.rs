//! Actual parent-owned retained-original helper lifetime.
//! Only this private spawn/SCM-credential handshake constructs a usable lease.
use super::*;
use crate::control::working_retained_peer::{self, RetainedHelperPeer};
use crate::native_working_contract::retained_data as c;
use crate::working_retained_wire::{self as wire, Frame};
use std::os::unix::net::UnixStream;
fn io(why: impl Into<String>) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, why.into())
}
/// Live original-pair retention. It cannot be serialized, cloned or reconstructed
/// from an evidence record, a PID number or the cold comparison manifest.
pub struct WorkingRetainedOriginals<'a> {
    owner: &'a WorkingQualificationOwner,
    child: Child,
    peer: Rc<RetainedHelperPeer>,
    socket: UnixStream,
    end: Instant,
    complete: bool,
}
fn reap(child: &mut Child, end: Instant) -> io::Result<ExitStatus> {
    loop {
        if let Some(status) = child.try_wait()? {
            return Ok(status);
        }
        if Instant::now() >= end {
            return Err(io("retained helper actual retirement is unproven"));
        }
        let ms = end
            .saturating_duration_since(Instant::now())
            .as_millis()
            .min(20)
            .max(1) as i32;
        // Finite same-thread retirement; no detached feeder or renewed window.
        if unsafe { libc::poll(std::ptr::null_mut(), 0, ms) } < 0 {
            let e = io::Error::last_os_error();
            if e.kind() != io::ErrorKind::Interrupted {
                return Err(e);
            }
        }
    }
}
impl<'a> WorkingRetainedOriginals<'a> {
    pub(super) fn start(
        owner: &'a WorkingQualificationOwner,
        main: &MainCustodyObservation,
    ) -> Result<Self, String> {
        owner.compare_preparation_main(main)?;
        if unsafe { libc::prctl(libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) } != 0 {
            return Err(
                "retained helper normal transition requires the actual parent NNP=0".into(),
            );
        }
        if owner
            .preparation_end
            .saturating_duration_since(Instant::now())
            < Duration::from_secs(c::RETAINED_INSTALL_PREPARATION_SECONDS)
        {
            return Err(
                "original preparation cannot fit the full retained-original mechanical window"
                    .into(),
            );
        }
        let now_ns = wire::clock().map_err(|e| e.to_string())?;
        let end_ns = now_ns
            .checked_add(c::RETAINED_HELPER_SECONDS * 1_000_000_000)
            .ok_or("retained helper monotonic deadline overflow")?
            .min(owner.preparation_end_ns);
        let end = wire::until(end_ns)
            .map_err(|e| e.to_string())?
            .min(owner.preparation_end);
        let boot = owner.pulse.retained_boot();
        boot.compare_main(main).map_err(|e| e.to_string())?;
        let candidate = boot.config().candidate_id.clone();
        let executable = boot.retained_executable().map_err(|e| e.to_string())?;
        let (socket, child_socket) = UnixStream::pair().map_err(|e| e.to_string())?;
        wire::prepare(&socket)
            .and_then(|_| wire::prepare(&child_socket))
            .map_err(|e| e.to_string())?;
        let raw = unsafe { libc::fcntl(child_socket.as_raw_fd(), libc::F_DUPFD_CLOEXEC, 64) };
        if raw < 0 {
            return Err(io::Error::last_os_error().to_string());
        }
        let inherited = unsafe { OwnedFd::from_raw_fd(raw) };
        let mut command = Command::new(format!("/proc/self/fd/{}", executable.as_raw_fd()));
        command
            .arg0(c::HELPER_PATH)
            .arg(working_retained_peer::ARG)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::inherit())
            .env_clear()
            .env("PATH", "/usr/sbin:/usr/bin:/sbin:/bin")
            .env("LANG", "C.UTF-8")
            .current_dir("/");
        let parent = std::process::id();
        let watchdog = owner.pulse.child_close_fd().map_err(|e| e.to_string())?;
        let fd = inherited.as_raw_fd();
        unsafe {
            command.pre_exec(move || {
                if libc::close(watchdog) != 0
                    || libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) != 0
                {
                    return Err(io::Error::last_os_error());
                }
                if libc::getppid() as u32 != parent {
                    return Err(io("retained parent died before normal exec"));
                }
                if libc::dup2(fd, 3) < 0 || libc::fcntl(3, libc::F_SETFD, 0) < 0 {
                    return Err(io::Error::last_os_error());
                }
                // Only the fixed private channel survives; the executable may be
                // referenced by exec through its CLOEXEC descriptor.
                if libc::syscall(
                    libc::SYS_close_range,
                    4u32,
                    u32::MAX,
                    libc::CLOSE_RANGE_CLOEXEC,
                ) != 0
                {
                    return Err(io::Error::last_os_error());
                }
                Ok(())
            });
        }
        owner.compare_preparation_main(main)?;
        let mut child = command.spawn().map_err(|e| e.to_string())?;
        drop(inherited);
        drop(child_socket);
        let admit = (|| {
            let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, child.id(), 0u32) };
            if raw < 0 {
                return Err(io::Error::last_os_error().to_string());
            }
            let pidfd = unsafe { File::from_raw_fd(raw as i32) };
            let peer = Rc::new(
                RetainedHelperPeer::capture(&pidfd, parent, end).map_err(|e| e.to_string())?,
            );
            owner.pulse.bind_retained(peer.clone())?;
            Ok(peer)
        })();
        let peer = match admit {
            Ok(v) => v,
            Err(e) => {
                owner.pulse.poison();
                let _ = child.kill();
                let retired = reap(
                    &mut child,
                    (Instant::now() + Duration::from_secs(c::RETAINED_HELPER_RETIRE_SECONDS))
                        .min(end),
                );
                return Err(format!("{e}; actual retained child cleanup: {retired:?}"));
            }
        };
        let value = Self {
            owner,
            child,
            peer,
            socket,
            end,
            complete: false,
        };
        let mut guard = || value.guard(main).map_err(io);
        wire::send(
            &value.socket,
            &Frame::Begin {
                schema: wire::SCHEMA.into(),
                candidate_id: candidate,
                preparation_end_ns: owner.preparation_end_ns,
                helper_end_ns: end_ns,
                main: main.facts().clone(),
            },
            end,
            &mut guard,
        )
        .map_err(|e| e.to_string())?;
        match wire::receive(&value.socket, value.peer.pid(), end, &mut guard)
            .map_err(|e| e.to_string())?
        {
            Frame::Ready {
                schema,
                main: actual,
            } if schema == wire::SCHEMA && actual == *main.facts() => {}
            _ => {
                return Err(
                    "retained helper did not independently bind the same complete actual Main"
                        .into(),
                );
            }
        }
        value.guard(main)?;
        Ok(value)
    }
    /// The same actual preparation owner, child PIDFD, ELF, roles and Main.
    pub fn guard(&self, main: &MainCustodyObservation) -> Result<(), String> {
        if self.complete || Instant::now() >= self.end {
            return Err("retained helper lease is complete or expired".into());
        }
        self.peer.guard().map_err(|e| e.to_string())?;
        self.owner.compare_preparation_main(main)
    }
    pub(crate) fn pidfd(&self) -> &File {
        self.peer.pidfd()
    }
    pub(crate) fn helper_pid(&self) -> u32 {
        self.peer.pid()
    }
    pub(crate) fn deadline(&self) -> Instant {
        self.end
    }
    /// Finish the second full original-pair hash and fresh complete Main check,
    /// then reap the exact helper before releasing the parent membership guard.
    pub fn finish(mut self, main: &MainCustodyObservation) -> Result<Value, String> {
        self.guard(main)?;
        let mut guard = || self.guard(main).map_err(io);
        wire::send(&self.socket, &Frame::Finish {}, self.end, &mut guard)
            .map_err(|e| e.to_string())?;
        match wire::receive(&self.socket, self.peer.pid(), self.end, &mut guard)
            .map_err(|e| e.to_string())?
        {
            Frame::Finished {
                schema,
                main: actual,
            } if schema == wire::SCHEMA && actual == *main.facts() => {}
            _ => return Err("retained final full Main/hash acknowledgement differs".into()),
        }
        wire::send_retire(&self.socket, self.end, &mut guard).map_err(|e| e.to_string())?;
        drop(guard);
        let status = reap(
            &mut self.child,
            (Instant::now() + Duration::from_secs(c::RETAINED_HELPER_RETIRE_SECONDS)).min(self.end),
        )
        .map_err(|e| e.to_string())?;
        if !status.success() {
            return Err(format!("normal retained helper exited {status}"));
        }
        self.owner.pulse.retired_retained()?;
        self.owner.compare_preparation_main(main)?;
        self.complete = true;
        Ok(
            json!({"schema":"droidloom.retained-original-mechanical-window.v1",
            "actual_helper_pid":self.peer.pid(),"initial_and_final_full_original_pair_hashes_verified":true,
            "same_complete_actual_working_main":true,"readonly_original_ofds_held_through_window":true,
            "direct_helper_reaped":true,"original_data_migration_accepted":false,
            "account_login_accepted":false,"application_accepted":false,"production_ready":false}),
        )
    }
}
impl Drop for WorkingRetainedOriginals<'_> {
    fn drop(&mut self) {
        if self.complete {
            return;
        }
        self.owner.pulse.poison();
        let _ = self.child.kill();
        let end =
            (Instant::now() + Duration::from_secs(c::RETAINED_HELPER_RETIRE_SECONDS)).min(self.end);
        if let Err(error) = reap(&mut self.child, end) {
            eprintln!("retained original helper retirement unproven: {error}");
        }
    }
}
