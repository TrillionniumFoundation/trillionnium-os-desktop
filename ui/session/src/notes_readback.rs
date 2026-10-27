//! Root-reserved App-only receipt continuation on the original recovery peer.
//! The effect endpoint is never retained. Only an actually reaped owned App
//! permits the one sealed helper to inherit that App's same recovery socket.

use std::fs::{File, OpenOptions};
use std::io::{self, Read, Write};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::os::unix::net::UnixDatagram;
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdout, Command, Stdio};
use std::time::{Duration, Instant};
use trill_ui_core::notes::{sha256_hex, NotesTargetIdentity};

pub(super) const HELPER_SHA_ENV: &str = "TRILL_NOTES_READBACK_HELPER_SHA256";
const MAX_HELPER_BYTES: u64 = 128 * 1024 * 1024;
const READY: &[u8] = b"TRILL_NOTES_RECOVERY_READY_V1\n";

pub(super) struct Standby {
    executable: File,
    root: PathBuf,
    binding: Option<Binding>,
    original_app: Option<(u32, OwnedFd)>,
    consumed: bool,
    running: Option<Running>,
}

struct Binding {
    target: NotesTargetIdentity,
    channel: UnixDatagram,
}

struct Running {
    child: Child,
    ready: ChildStdout,
    filled: usize,
    deadline: Instant,
    confirmed: bool,
}

impl Standby {
    /// Only Root-reserved startup calls this with the package's fixed sibling
    /// helper and the original Root launch's actual artifact digest.
    pub(super) fn prepare(helper: &Path, expected: &str, root: PathBuf) -> io::Result<Self> {
        trill_ui_core::notes_store::NotesStore::validate_existing_storage_root(&root)?;
        if !helper.is_absolute()
            || helper.canonicalize()? != helper
            || expected.len() != 64
            || !expected
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
            || expected.bytes().all(|byte| byte == b'0')
        {
            return Err(invalid("original fixed Notes readback artifact required"));
        }
        let mut source = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK | libc::O_CLOEXEC)
            .open(helper)?;
        let before = source.metadata()?;
        // SAFETY: reads the actual process identity.
        let uid = unsafe { libc::geteuid() };
        if !before.is_file()
            || before.nlink() != 1
            || (before.uid() != uid && before.uid() != 0)
            || before.mode() & 0o022 != 0
            || before.mode() & 0o111 == 0
            || before.len() > MAX_HELPER_BYTES
        {
            return Err(invalid("Notes readback executable custody"));
        }
        let mut bytes = Vec::new();
        Read::by_ref(&mut source)
            .take(MAX_HELPER_BYTES + 1)
            .read_to_end(&mut bytes)?;
        let after = source.metadata()?;
        if bytes.len() as u64 > MAX_HELPER_BYTES
            || !bytes.starts_with(b"\x7fELF")
            || sha256_hex(&bytes) != expected
            || (
                before.dev(),
                before.ino(),
                before.len(),
                before.uid(),
                before.mode(),
            ) != (
                after.dev(),
                after.ino(),
                after.len(),
                after.uid(),
                after.mode(),
            )
        {
            return Err(invalid("Notes readback executable identity mismatch"));
        }
        // SAFETY: returns one new private descriptor for immutable ELF bytes.
        let descriptor = unsafe {
            libc::memfd_create(
                c"trill-session-readback".as_ptr(),
                libc::MFD_CLOEXEC | libc::MFD_ALLOW_SEALING,
            )
        };
        if descriptor < 0 {
            return Err(io::Error::last_os_error());
        }
        // SAFETY: owns exactly the newly created descriptor.
        let mut executable = unsafe { File::from_raw_fd(descriptor) };
        executable.write_all(&bytes)?;
        // SAFETY: executable owns this descriptor throughout both calls.
        if unsafe { libc::fchmod(descriptor, 0o500) } != 0
            || unsafe {
                libc::fcntl(
                    descriptor,
                    libc::F_ADD_SEALS,
                    libc::F_SEAL_WRITE
                        | libc::F_SEAL_GROW
                        | libc::F_SEAL_SHRINK
                        | libc::F_SEAL_SEAL,
                )
            } != 0
        {
            return Err(io::Error::last_os_error());
        }
        Ok(Self {
            executable,
            root,
            binding: None,
            original_app: None,
            consumed: false,
            running: None,
        })
    }

    /// The sole initial private bootstrap supplies the App-side recovery peer;
    /// no public request, arbitrary FD number or effect stream reaches here.
    pub(super) fn bind(
        &mut self,
        target: NotesTargetIdentity,
        peer: &UnixDatagram,
    ) -> io::Result<()> {
        target
            .validate()
            .map_err(|_| invalid("original Notes target identity"))?;
        if target.task_id != 1
            || self.binding.is_some()
            || self.consumed
            || !peer.local_addr()?.is_unnamed()
            || !peer.peer_addr()?.is_unnamed()
        {
            return Err(invalid(
                "initial original Notes recovery peer required exactly once",
            ));
        }
        self.binding = Some(Binding {
            target,
            channel: peer.try_clone()?,
        });
        Ok(())
    }

    /// Pin only the actual owned child immediately after the original spawn.
    /// The kernel handle is retained across exit; no later PID lookup adopts it.
    pub(super) fn pin_original(&mut self, app: &mut Child) -> io::Result<()> {
        if self.binding.is_none()
            || self.original_app.is_some()
            || self.consumed
            || app.try_wait()?.is_some()
        {
            return Err(invalid("live original Notes App must be pinned once"));
        }
        // SAFETY: pid comes from the original owned Child, never an IPC field.
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, app.id(), 0_u32) };
        if raw < 0 {
            return Err(io::Error::last_os_error());
        }
        // SAFETY: owns precisely the returned kernel process descriptor.
        let pidfd = unsafe { OwnedFd::from_raw_fd(raw as i32) };
        let mut poll = libc::pollfd {
            fd: pidfd.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        // SAFETY: one initialized poll descriptor, no waiting or PID adoption.
        if unsafe { libc::poll(&mut poll, 1, 0) } != 0 || app.try_wait()?.is_some() {
            return Err(invalid("original Notes App exited before pinning"));
        }
        self.original_app = Some((app.id(), pidfd));
        Ok(())
    }

    /// Called with the original Session-owned Child, never a disk PID. Waiting
    /// is observed here before the recovery peer can leave its standby slot.
    /// A failed start consumes the slot; there is no effect or helper retry.
    pub(super) fn after_reap(&mut self, app: &mut Child) -> io::Result<()> {
        let (pid, pidfd) = self
            .original_app
            .as_ref()
            .ok_or_else(|| invalid("original Notes App was not pinned"))?;
        if app.id() != *pid {
            return Err(invalid("reaped process differs from original Notes App"));
        }
        if app.try_wait()?.is_none() {
            return Err(invalid("original Notes App has not been reaped"));
        }
        let mut poll = libc::pollfd {
            fd: pidfd.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        // SAFETY: the exact original pidfd is held, with a nonblocking poll.
        if unsafe { libc::poll(&mut poll, 1, 0) } != 1 || poll.revents & libc::POLLIN == 0 {
            return Err(invalid("original Notes App lifetime has not ended"));
        }
        if self.consumed {
            return Err(invalid("original Notes readback already consumed"));
        }
        self.consumed = true;
        let binding = self
            .binding
            .take()
            .ok_or_else(|| invalid("original Notes readback peer missing"))?;
        let mut command = Command::new(format!("/proc/self/fd/{}", self.executable.as_raw_fd()));
        command
            .arg("--state-dir")
            .arg(&self.root)
            .args([
                "--notes-session",
                &binding.target.session_instance,
                "--task-id",
                &binding.target.task_id.to_string(),
                "--notes-incarnation",
                &binding.target.incarnation,
            ])
            .env_clear()
            .stdin(Stdio::from(OwnedFd::from(binding.channel)))
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit());
        // SAFETY: reads the actual original parent process identity.
        let parent = unsafe { libc::getpid() };
        // SAFETY: only async-signal-safe process/descriptor operations occur
        // after fork. The same recovery peer is stdin; no effect FD is copied.
        unsafe {
            command.pre_exec(move || {
                if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) != 0 {
                    return Err(io::Error::last_os_error());
                }
                if libc::getppid() != parent {
                    return Err(io::Error::from_raw_os_error(libc::ESRCH));
                }
                if libc::syscall(
                    libc::SYS_close_range,
                    3_u32,
                    u32::MAX,
                    libc::CLOSE_RANGE_CLOEXEC,
                ) != 0
                {
                    return Err(io::Error::last_os_error());
                }
                Ok(())
            });
        }
        let deadline = Instant::now() + Duration::from_secs(2);
        let mut child = command.spawn()?;
        let setup = (|| {
            let ready = child
                .stdout
                .take()
                .ok_or_else(|| invalid("original Notes helper ready pipe missing"))?;
            // SAFETY: the owned pipe remains live. Set only nonblocking I/O.
            let flags = unsafe { libc::fcntl(ready.as_raw_fd(), libc::F_GETFL) };
            if flags < 0
                || unsafe {
                    libc::fcntl(ready.as_raw_fd(), libc::F_SETFL, flags | libc::O_NONBLOCK)
                } < 0
            {
                return Err(io::Error::last_os_error());
            }
            Ok(ready)
        })();
        let ready = match setup {
            Ok(ready) => ready,
            Err(error) => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(error);
            }
        };
        self.running = Some(Running {
            child,
            ready,
            filled: 0,
            deadline,
            confirmed: false,
        });
        Ok(())
    }

    /// Polling is nonblocking and never renews the original two-second ready
    /// budget. Ready only means the same store lock opened, never an effect.
    pub(super) fn refresh(&mut self) -> io::Result<()> {
        let Some(running) = &mut self.running else {
            return Ok(());
        };
        if running.child.try_wait()?.is_some() {
            return Err(invalid("original Notes readback helper exited"));
        }
        if running.confirmed {
            return Ok(());
        }
        if Instant::now() >= running.deadline {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "original Notes readback readiness deadline",
            ));
        }
        let mut bytes = [0_u8; READY.len()];
        match running.ready.read(&mut bytes[running.filled..]) {
            Ok(0) => return Err(invalid("original Notes readback ready EOF")),
            Ok(count) => {
                if bytes[running.filled..running.filled + count]
                    != READY[running.filled..running.filled + count]
                {
                    return Err(invalid("original Notes readback ready mismatch"));
                }
                running.filled += count;
                if Instant::now() >= running.deadline {
                    return Err(io::Error::new(
                        io::ErrorKind::TimedOut,
                        "original Notes readback readiness deadline",
                    ));
                }
                running.confirmed = running.filled == READY.len();
            }
            Err(error)
                if error.kind() == io::ErrorKind::WouldBlock
                    || error.kind() == io::ErrorKind::Interrupted => {}
            Err(error) => return Err(error),
        }
        Ok(())
    }
}

impl Drop for Standby {
    fn drop(&mut self) {
        if let Some(running) = &mut self.running {
            if matches!(running.child.try_wait(), Ok(None)) {
                let _ = running.child.kill();
            }
            let _ = running.child.wait();
        }
    }
}

fn invalid(message: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message)
}

#[cfg(test)]
#[path = "notes_readback_tests.rs"]
mod tests;
