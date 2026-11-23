//! The system manager owns the public socket and notification. The OCI producer
//! owns creation and retirement of the cell; this process observes its fixed
//! instance and accepts progress only from the bound, live kernel peer.
use droidloom_supervisor::control::{PreparedContainerSelection, check_installed_mac_platform};
use serde::Deserialize;
use std::fs;
use std::io::{self, Read, Write};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::fs::{FileTypeExt, MetadataExt, PermissionsExt};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread;
use std::time::{Duration, Instant};

#[path = "container_status_protocol.rs"]
mod protocol;

const START_LIMIT: Duration = Duration::from_secs(240);
const CHANNEL: &str = "/run/droidloom-container/guest.sock";
const OCI_ROOT: &str = "/run/droidloom-container-oci";
const BUNDLE: &str = "/etc/droidloom/production/oci-bundle";
const INSTANCE: &str = "android";
const PROGRAM: &str = "/usr/lib/droidloom/production/current/droidloom-container-entry";

fn error(text: &str) -> io::Error {
    io::Error::other(text)
}

#[derive(Deserialize)]
struct OciState {
    id: String,
    status: String,
    pid: i32,
    bundle: PathBuf,
    annotations: std::collections::BTreeMap<String, String>,
}

fn state() -> io::Result<OciState> {
    let mut command = Command::new("/usr/bin/runc");
    command
        .env_clear()
        .env("PATH", "/usr/sbin:/usr/bin")
        .args(["--root", OCI_ROOT, "state", INSTANCE])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    let mut child = command.spawn()?;
    let end = Instant::now() + Duration::from_secs(2);
    loop {
        if let Some(exit) = child.try_wait()? {
            if !exit.success() {
                return Err(error("the prepared OCI instance has no live runtime state"));
            }
            let mut bytes = Vec::new();
            child
                .stdout
                .take()
                .unwrap()
                .take(65537)
                .read_to_end(&mut bytes)?;
            if bytes.len() > 65536 {
                return Err(error("oversized OCI state"));
            }
            return serde_json::from_slice(&bytes).map_err(io::Error::other);
        }
        if Instant::now() >= end {
            child.kill()?;
            child.wait()?;
            return Err(error("OCI state query timed out"));
        }
        thread::sleep(Duration::from_millis(10));
    }
}

fn bind_named(path: &str) -> io::Result<(UnixListener, (u64, u64))> {
    let parent = fs::symlink_metadata(Path::new(path).parent().unwrap())?;
    if !parent.is_dir() || parent.uid() != unsafe { libc::geteuid() } || parent.mode() & 0o022 != 0
    {
        return Err(error("the service runtime directory has invalid ownership"));
    }
    let listener = UnixListener::bind(path)?;
    let m = fs::symlink_metadata(path)?;
    fs::set_permissions(path, fs::Permissions::from_mode(0o666))?;
    listener.set_nonblocking(true)?;
    Ok((listener, (m.dev(), m.ino())))
}

struct Channel {
    listener: UnixListener,
    node: (u64, u64),
}
impl Drop for Channel {
    fn drop(&mut self) {
        if let Ok(meta) = fs::symlink_metadata(CHANNEL)
            && meta.file_type().is_socket()
            && (meta.dev(), meta.ino()) == self.node
        {
            let _ = fs::remove_file(CHANNEL);
        }
    }
}

fn socket_value<T: Copy>(stream: &UnixStream, option: i32) -> io::Result<T> {
    let mut value = std::mem::MaybeUninit::<T>::uninit();
    let mut length = std::mem::size_of::<T>() as libc::socklen_t;
    let result = unsafe {
        libc::getsockopt(
            stream.as_raw_fd(),
            libc::SOL_SOCKET,
            option,
            value.as_mut_ptr().cast(),
            &mut length,
        )
    };
    if result != 0 {
        return Err(io::Error::last_os_error());
    }
    if length as usize != std::mem::size_of::<T>() {
        return Err(error("unexpected kernel socket credential size"));
    }
    Ok(unsafe { value.assume_init() })
}

fn live(pidfd: &OwnedFd) -> io::Result<bool> {
    let mut poll = libc::pollfd {
        fd: pidfd.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    let n = unsafe { libc::poll(&mut poll, 1, 0) };
    if n < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(n == 0)
}

struct Guest {
    socket: UnixStream,
    pidfd: OwnedFd,
    binder: bool,
    android: bool,
    last: Instant,
}
impl Guest {
    fn admit(socket: UnixStream, choice: &PreparedContainerSelection) -> io::Result<Self> {
        let cred: libc::ucred = socket_value(&socket, libc::SO_PEERCRED)?;
        // SO_PEERPIDFD returns a descriptor for the actual connecting task.
        // Opening a fresh pidfd by its numeric PID would allow PID reuse.
        const SO_PEERPIDFD: libc::c_int = 77;
        let fd: i32 = socket_value(&socket, SO_PEERPIDFD)?;
        if fd < 0 {
            return Err(error("missing guest pidfd"));
        }
        let pidfd = unsafe { OwnedFd::from_raw_fd(fd) };
        if cred.pid <= 1 || !live(&pidfd)? {
            return Err(error("guest peer is absent"));
        }
        let original = choice.entry_program()?;
        let actual = fs::metadata(format!("/proc/{}/exe", cred.pid))?;
        let selected = fs::metadata(PROGRAM)?;
        if (actual.dev(), actual.ino()) != (selected.dev(), selected.ino()) {
            return Err(error(
                "peer does not execute the published guest entry inode",
            ));
        }
        let current = state()?;
        if current.id != INSTANCE
            || current.status != "running"
            || current.pid != cred.pid
            || current.bundle != Path::new(BUNDLE)
            || current
                .annotations
                .get("org.droidloom.selection.sha256")
                .map(String::as_str)
                != Some(choice.selection_digest())
        {
            return Err(error(
                "OCI generation does not match the connected guest and selected release",
            ));
        }
        original.revalidate()?;
        choice.revalidate()?;
        if !live(&pidfd)? {
            return Err(error("guest exited while binding its generation"));
        }
        socket.set_nonblocking(true)?;
        Ok(Self {
            socket,
            pidfd,
            binder: false,
            android: false,
            last: Instant::now(),
        })
    }
    fn update(&mut self) -> io::Result<()> {
        if !live(&self.pidfd)? {
            return Err(error("bound OCI PID 1 exited"));
        }
        let mut bytes = [0u8; 64];
        match self.socket.read(&mut bytes) {
            Ok(0) => return Err(error("guest liveness channel closed")),
            Ok(n) => {
                for &stage in &bytes[..n] {
                    if stage > 2 || self.binder && stage == 0 {
                        return Err(error("guest Binder readiness was lost or invalid"));
                    }
                    self.binder = stage >= 1;
                    self.android = stage == 2;
                }
                self.last = Instant::now();
            }
            Err(e)
                if matches!(
                    e.kind(),
                    io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
                ) => {}
            Err(e) => return Err(e),
        }
        if self.last.elapsed() > Duration::from_secs(15) {
            return Err(error("guest readiness observations expired"));
        }
        Ok(())
    }
}

pub(super) fn run(stop: &AtomicBool) -> io::Result<()> {
    let choice = PreparedContainerSelection::acquire()?;
    check_installed_mac_platform()?;
    let program = choice.entry_program()?;
    let (listener, node) = bind_named(CHANNEL)?;
    let channel = Channel { listener, node };
    let mut clients = protocol::Clients::bind()?;
    let mut guest: Option<Guest> = None;
    let mut notified = false;
    let end = Instant::now() + START_LIMIT;
    let mut last_issue = None;
    let mut revalidate = Instant::now();
    while !stop.load(Ordering::Relaxed) {
        if guest.is_none() {
            match channel.listener.accept() {
                Ok((socket, _)) => match Guest::admit(socket, &choice) {
                    Ok(peer) => guest = Some(peer),
                    Err(e) => last_issue = Some(e),
                },
                Err(e)
                    if matches!(
                        e.kind(),
                        io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
                    ) => {}
                Err(e) => return Err(e),
            }
        }
        if let Some(peer) = guest.as_mut() {
            peer.update()?;
            if peer.binder && !notified {
                choice.revalidate()?;
                program.revalidate()?;
                protocol::notify_main()?;
                notified = true;
            }
        }
        if !notified && Instant::now() >= end {
            return Err(last_issue.unwrap_or_else(|| {
                error("selected OCI guest did not establish Android Binder before startup deadline")
            }));
        }
        if Instant::now() >= revalidate {
            choice.revalidate()?;
            revalidate = Instant::now() + Duration::from_secs(5);
        }
        clients.poll(guest.as_ref().is_some_and(|v| v.android))?;
        thread::sleep(Duration::from_millis(30));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn socket_peer_pidfd_is_kernel_bound_and_tracked_after_peer_exit() {
        use std::os::unix::process::CommandExt;
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("ch");
        let server = UnixListener::bind(&path).unwrap();
        let mut child=Command::new("/usr/bin/python3").arg0("python3").args(["-c","import socket,sys,time; s=socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); s.sendall(bytes([1,2])); time.sleep(5)"]).arg(&path).spawn().unwrap();
        let (stream, _) = server.accept().unwrap();
        let cred: libc::ucred = socket_value(&stream, libc::SO_PEERCRED).unwrap();
        assert_eq!(cred.pid as u32, child.id());
        let fd: i32 = socket_value(&stream, 77).unwrap();
        let pidfd = unsafe { OwnedFd::from_raw_fd(fd) };
        stream.set_nonblocking(true).unwrap();
        let mut peer = Guest {
            socket: stream,
            pidfd,
            binder: false,
            android: false,
            last: Instant::now(),
        };
        for _ in 0..20 {
            peer.update().unwrap();
            if peer.android {
                break;
            }
            thread::sleep(Duration::from_millis(15));
        }
        assert!(peer.binder && peer.android);
        child.kill().unwrap();
        child.wait().unwrap();
        assert!(!live(&peer.pidfd).unwrap());
        assert!(peer.update().is_err());
    }
}
