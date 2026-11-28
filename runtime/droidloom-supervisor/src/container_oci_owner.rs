//! The system manager owns the public socket and notification. The OCI producer
//! owns creation and retirement of the cell; this process observes its fixed
//! instance and accepts progress only from the bound, live kernel peer.
use droidloom_supervisor::control::{
    ContainerLibraryMount, ContainerManagerMac, PreparedContainerSelection,
};
use serde::Deserialize;
use std::fs::{self, File};
use std::io::{self, Read, Write};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::fs::{FileTypeExt, MetadataExt, PermissionsExt};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread;
use std::time::{Duration, Instant};

#[path = "container_early_observer.rs"]
pub(super) mod early;
#[path = "container_status_protocol.rs"]
mod protocol;

const START_LIMIT: Duration = Duration::from_secs(240);
const CHANNEL: &str = "/run/droidloom-container-link/guest.sock";
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

fn fixed_output(executable: &str, args: &[&str]) -> io::Result<Vec<u8>> {
    let mut child = Command::new(executable)
        .env_clear()
        .env("PATH", "/usr/sbin:/usr/bin")
        .env("LC_ALL", "C")
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()?;
    let end = Instant::now() + Duration::from_secs(2);
    loop {
        if let Some(exit) = child.try_wait()? {
            if !exit.success() {
                return Err(error("the prepared OCI service has no live runtime state"));
            }
            let mut bytes = Vec::new();
            child
                .stdout
                .take()
                .unwrap()
                .take(65537)
                .read_to_end(&mut bytes)?;
            if bytes.len() > 65536 {
                return Err(error("oversized OCI service response"));
            }
            return Ok(bytes);
        }
        if Instant::now() >= end {
            child.kill()?;
            child.wait()?;
            return Err(error("OCI service query timed out"));
        }
        thread::sleep(Duration::from_millis(10));
    }
}
fn state() -> io::Result<OciState> {
    serde_json::from_slice(&fixed_output(
        "/usr/bin/runc",
        &["--root", OCI_ROOT, "state", INSTANCE],
    )?)
    .map_err(io::Error::other)
}

#[derive(Debug, Eq, PartialEq)]
struct OciOwner {
    pid: i32,
    invocation: String,
}
impl OciOwner {
    fn current() -> io::Result<Self> {
        let bytes = fixed_output(
            "/usr/bin/systemctl",
            &[
                "--system",
                "--no-pager",
                "show",
                "--property=MainPID,InvocationID,ActiveState",
                "droidloom-container-oci.service",
            ],
        )?;
        let text = std::str::from_utf8(&bytes).map_err(io::Error::other)?;
        let field = |k: &str| {
            text.lines()
                .filter_map(|line| line.split_once('='))
                .find_map(|(key, value)| (key == k).then_some(value))
        };
        let pid = field("MainPID")
            .and_then(|v| v.parse::<i32>().ok())
            .filter(|n| *n > 1)
            .ok_or_else(|| error("OCI system service lacks live MainPID"))?;
        let invocation = field("InvocationID")
            .filter(|s| {
                s.len() == 32
                    && s.bytes().all(|b| b.is_ascii_hexdigit())
                    && s.bytes().any(|b| b != b'0')
            })
            .ok_or_else(|| error("OCI system service lacks a valid invocation"))?;
        if !matches!(field("ActiveState"), Some("active" | "activating")) {
            return Err(error("OCI system service is inactive"));
        }
        Ok(Self {
            pid,
            invocation: invocation.to_string(),
        })
    }
    fn pidfd(&self) -> io::Result<OwnedFd> {
        let fd = unsafe { libc::syscall(libc::SYS_pidfd_open, self.pid, 0u32) };
        if fd < 0 {
            return Err(io::Error::last_os_error());
        }
        Ok(unsafe { OwnedFd::from_raw_fd(fd as i32) })
    }
}

fn inherited_guest_listener() -> io::Result<UnixListener> {
    if std::env::var("LISTEN_PID")
        .ok()
        .and_then(|s| s.parse::<u32>().ok())
        != Some(std::process::id())
        || std::env::var("LISTEN_FDS").as_deref() != Ok("1")
        || std::env::var("LISTEN_FDNAMES").as_deref() != Ok("android_guest")
    {
        return Err(error(
            "systemd must pass the dedicated guest socket to its current MainPID",
        ));
    }
    let listener = unsafe { UnixListener::from_raw_fd(3) };
    if listener.local_addr()?.as_pathname() != Some(Path::new(CHANNEL)) {
        return Err(error("unexpected systemd guest socket"));
    }
    let dir = fs::symlink_metadata(Path::new(CHANNEL).parent().unwrap())?;
    if !dir.is_dir() || dir.uid() != 0 || dir.mode() & 0o7777 != 0o700 {
        return Err(error(
            "guest socket requires its private root-owned host directory",
        ));
    }
    if unsafe { libc::fcntl(listener.as_raw_fd(), libc::F_SETFD, libc::FD_CLOEXEC) } < 0 {
        return Err(io::Error::last_os_error());
    }
    listener.set_nonblocking(true)?;
    Ok(listener)
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

enum GuestLibraryMount {
    Selected(ContainerLibraryMount),
    #[cfg(test)]
    ProtocolFixture,
}
impl GuestLibraryMount {
    fn revalidate(&self) -> io::Result<()> {
        match self {
            Self::Selected(held) => held.revalidate(),
            #[cfg(test)]
            Self::ProtocolFixture => Err(error("protocol fixture has no admitted library mount")),
        }
    }
}

struct Guest {
    mount: GuestLibraryMount,
    socket: UnixStream,
    pid: i32,
    pidfd: OwnedFd,
    controller: OwnedFd,
    binder: bool,
    android: bool,
    last: Instant,
}
impl Guest {
    fn matches_oci(pid: i32, selection: &str) -> io::Result<()> {
        let current = state()?;
        if current.id != INSTANCE
            || current.status != "running"
            || current.pid != pid
            || current.bundle != Path::new(BUNDLE)
            || current
                .annotations
                .get("org.droidloom.selection.sha256")
                .map(String::as_str)
                != Some(selection)
        {
            return Err(error(
                "OCI generation does not match the connected guest and selected release",
            ));
        }
        Ok(())
    }
    fn admit(mut socket: UnixStream, choice: &PreparedContainerSelection, mac: &ContainerManagerMac) -> io::Result<Self> {
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
        let owner = OciOwner::current()?;
        let controller = owner.pidfd()?;
        let guest_proc = File::open(format!("/proc/{}", cred.pid))?;
        let owner_proc = File::open(format!("/proc/{}", owner.pid))?;
        choice.verify_oci_identities(&guest_proc, &owner_proc)?;
        let original = choice.entry_program()?;
        let actual = fs::metadata(format!("/proc/{}/exe", cred.pid))?;
        let selected = fs::metadata(PROGRAM)?;
        if (actual.dev(), actual.ino()) != (selected.dev(), selected.ino()) {
            return Err(error(
                "peer does not execute the published guest entry inode",
            ));
        }
        Self::matches_oci(cred.pid, choice.selection_digest())?;
        original.revalidate()?;
        choice.revalidate()?;
        if !live(&pidfd)? || !live(&controller)? || owner != OciOwner::current()? {
            return Err(error(
                "OCI owner or guest exited while binding its generation",
            ));
        }
        let mount = choice.observe_library_mount(&guest_proc, &owner_proc)?;
        if !live(&pidfd)? || !live(&controller)? || owner != OciOwner::current()? {
            return Err(error("OCI generation changed during image validation"));
        }
        socket.set_write_timeout(Some(Duration::from_millis(200)))?;
        mac.revalidate()?;
        socket.write_all(&[1])?;
        socket.set_nonblocking(true)?;
        Ok(Self {
            mount: GuestLibraryMount::Selected(mount),
            socket,
            pid: cred.pid,
            pidfd,
            controller,
            binder: false,
            android: false,
            last: Instant::now(),
        })
    }
    fn shutdown(&mut self) -> io::Result<()> {
        self.socket.set_nonblocking(false)?;
        self.socket
            .set_write_timeout(Some(Duration::from_secs(2)))?;
        self.socket.write_all(&[0x53])?;
        self.socket
            .set_read_timeout(Some(Duration::from_millis(100)))?;
        let end = Instant::now() + Duration::from_secs(85);
        let mut retired = false;
        loop {
            let mut states = [0u8; 64];
            match self.socket.read(&mut states) {
                Ok(0) if !retired => {
                    return Err(error("guest exited without persistent mount retirement"));
                }
                Ok(n) => {
                    for &stage in &states[..n] {
                        if stage == 3 && !retired {
                            retired = true;
                        } else if stage > 2 || retired {
                            return Err(error("invalid shutdown progress from guest"));
                        }
                    }
                }
                Err(e)
                    if matches!(
                        e.kind(),
                        io::ErrorKind::TimedOut
                            | io::ErrorKind::WouldBlock
                            | io::ErrorKind::Interrupted
                    ) => {}
                Err(e) => return Err(e),
            }
            if !live(&self.pidfd)? {
                return if retired {
                    Ok(())
                } else {
                    Err(error("guest PID 1 exited before orderly shutdown"))
                };
            }
            if !live(&self.controller)? {
                return Err(error("OCI owner exited before retirement was proven"));
            }
            if Instant::now() >= end {
                return Err(error("guest orderly shutdown exceeded its deadline"));
            }
            thread::sleep(Duration::from_millis(20));
        }
    }
    fn update(&mut self) -> io::Result<()> {
        if !live(&self.pidfd)? || !live(&self.controller)? {
            return Err(error("bound OCI PID 1 or its system service owner exited"));
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
    let mac = ContainerManagerMac::acquire()?;
    let program = choice.entry_program()?;
    let channel = inherited_guest_listener()?;
    let mut clients = protocol::Clients::bind()?;
    let mut guest: Option<Guest> = None;
    let mut notified = false;
    let end = Instant::now() + START_LIMIT;
    let mut last_issue = None;
    let mut revalidate = Instant::now();
    let observation = (|| -> io::Result<()> {
        while !stop.load(Ordering::Relaxed) {
            mac.check_epoch()?;
            if guest.is_none() {
                match channel.accept() {
                    Ok((socket, _)) => match Guest::admit(socket, &choice, &mac) {
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
                    peer.mount.revalidate()?;
                    mac.revalidate()?;
                    protocol::notify_main()?;
                    notified = true;
                }
            }
            if !notified && Instant::now() >= end {
                return Err(last_issue.unwrap_or_else(||error("selected OCI guest did not establish Android Binder before startup deadline")));
            }
            if Instant::now() >= revalidate {
                if let Some(peer) = guest.as_ref() {
                    peer.mount.revalidate()?;
                    Guest::matches_oci(peer.pid, choice.selection_digest())?;
                }
                choice.revalidate()?;
                mac.revalidate()?;
                revalidate = Instant::now() + Duration::from_secs(5);
            }
            clients.poll(guest.as_ref().is_some_and(|v| v.android), || mac.revalidate())?;
            thread::sleep(Duration::from_millis(30));
        }
        Ok(())
    })();
    drop(clients);
    let stopping = if notified { protocol::notify_stopping() } else { Ok(()) };
    let shutdown = match guest {
        Some(mut peer) => peer.shutdown(),
        None => Ok(()),
    };
    observation.and(stopping).and(shutdown)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn orderly_host_stop_requires_the_same_peer_acknowledgement_and_exit() {
        for ack in [false, true] {
            let tmp = tempfile::tempdir().unwrap();
            let path = tmp.path().join("peer");
            let listener = UnixListener::bind(&path).unwrap();
            let script = r#"import socket,sys
s=socket.socket(socket.AF_UNIX);s.connect(sys.argv[1]);assert s.recv(1)==b"S"
if sys.argv[2]=="yes": s.send(bytes([3]))"#;
            let mut child = Command::new("/usr/bin/python3")
                .args(["-c", script])
                .arg(&path)
                .arg(if ack { "yes" } else { "no" })
                .spawn()
                .unwrap();
            let (socket, _) = listener.accept().unwrap();
            let fd: i32 = socket_value(&socket, 77).unwrap();
            let controller = OciOwner {
                pid: std::process::id() as i32,
                invocation: String::new(),
            }
            .pidfd()
            .unwrap();
            let mut peer = Guest {
                mount: GuestLibraryMount::ProtocolFixture,
                socket,
                pid: child.id() as i32,
                pidfd: unsafe { OwnedFd::from_raw_fd(fd) },
                controller,
                binder: true,
                android: true,
                last: Instant::now(),
            };
            let result = peer.shutdown();
            assert_eq!(result.is_ok(), ack, "{result:?}");
            assert!(child.wait().unwrap().success());
        }
    }

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
        let controller = pidfd.try_clone().unwrap();
        let mut peer = Guest {
            mount: GuestLibraryMount::ProtocolFixture,
            socket: stream,
            pid: cred.pid,
            pidfd,
            controller,
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
