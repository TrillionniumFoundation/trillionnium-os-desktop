// SPDX-License-Identifier: MPL-2.0

//! Connections to OSDK's managed QEMU monitor.

use std::{
    io::{self, Read, Write},
    net::{Ipv4Addr, TcpListener, TcpStream},
    os::{
        fd::AsRawFd,
        unix::{net::UnixStream, process::CommandExt},
    },
    process::{Child, Command},
    time::{Duration, Instant},
};

use rustix::io::{FdFlags, fcntl_dupfd_cloexec, fcntl_setfd};
use tempfile::TempPath;

use crate::config::scheme::MonitorTransport;

const TCP_SETUP_TIMEOUT: Duration = Duration::from_secs(2);
const MONITOR_CHARDEV_ID: &str = "osdk-managed-monitor";
// Leave standard descriptors and launcher bookkeeping undisturbed.
const MIN_CHILD_MONITOR_FD: i32 = 64;

pub(super) enum MonitorEndpoint {
    Unix(TempPath),
    Tcp(TcpStream),
}

impl MonitorEndpoint {
    /// Spawns QEMU with only its end of a private, already connected monitor.
    pub(super) fn spawn(
        transport: MonitorTransport,
        mut command: Command,
    ) -> io::Result<(Child, Self)> {
        match transport {
            MonitorTransport::Unix => {
                let path = tempfile::NamedTempFile::new()?.into_temp_path();
                command
                    .arg("-monitor")
                    .arg(format!("unix:{},server,nowait", path.to_string_lossy()));
                info!("Running QEMU: {command:#?}");
                let child = command.spawn()?;
                Ok((child, Self::Unix(path)))
            }
            MonitorTransport::Tcp => {
                let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0))?;
                Self::spawn_tcp(TcpPair::connect(listener)?, command)
            }
        }
    }

    fn spawn_tcp(pair: TcpPair, mut command: Command) -> io::Result<(Child, Self)> {
        // TcpPair::connect has already closed the listener. There is no
        // listening control endpoint while QEMU is running.
        let fd = pair.qemu.as_raw_fd();
        let local = pair.qemu.local_addr()?;
        let peer = pair.qemu.peer_addr()?;
        command
            .arg("-chardev")
            .arg(format!("socket,id={MONITOR_CHARDEV_ID},fd={fd},server=off"))
            .arg("-monitor")
            .arg(format!("chardev:{MONITOR_CHARDEV_ID}"));
        let qemu = pair.qemu;
        // SAFETY: the owned stream keeps this descriptor valid until Command
        // is dropped after spawn. The child hook performs only async-signal-
        // safe fcntl; it does not allocate or take locks. CLOEXEC remains set
        // in the parent and unrelated children.
        unsafe {
            command.pre_exec(move || fcntl_setfd(&qemu, FdFlags::empty()).map_err(io::Error::from));
        }
        info!(
            "QEMU monitor preconnected fd={fd} local={local} peer={peer}; listener closed; rejected peers={}",
            pair.rejected_peers
        );
        info!("Running QEMU: {command:#?}");
        let child = command.spawn()?;
        // Command owns the parent copy of QEMU's stream, so all return paths
        // close it, including spawn failure.
        drop(command);
        info!(
            "QEMU monitor inherited by child pid={}; parent child-end closed",
            child.id()
        );
        Ok((child, Self::Tcp(pair.monitor)))
    }

    pub(super) fn try_connect(&self) -> io::Result<MonitorStream> {
        match self {
            Self::Unix(path) => UnixStream::connect(path).map(MonitorStream::Unix),
            Self::Tcp(stream) => stream.try_clone().map(MonitorStream::Tcp),
        }
    }
}

/// The two ends are created by OSDK, before either is handed to a child.
struct TcpPair {
    monitor: TcpStream,
    qemu: TcpStream,
    rejected_peers: usize,
}

impl TcpPair {
    fn connect(listener: TcpListener) -> io::Result<Self> {
        let qemu = TcpStream::connect_timeout(&listener.local_addr()?, TCP_SETUP_TIMEOUT)?;
        let owned_peer = qemu.local_addr()?;
        let qemu = TcpStream::from(fcntl_dupfd_cloexec(&qemu, MIN_CHILD_MONITOR_FD)?);
        listener.set_nonblocking(true)?;
        let deadline = Instant::now() + TCP_SETUP_TIMEOUT;
        let mut rejected_peers = 0;
        loop {
            match listener.accept() {
                Ok((monitor, peer)) if peer == owned_peer => {
                    // qemu still owns this exact connected TCP tuple, so an
                    // unrelated client cannot be selected by arriving first.
                    // listener is dropped before the pair leaves this method.
                    return Ok(Self {
                        monitor,
                        qemu,
                        rejected_peers,
                    });
                }
                Ok(_) => rejected_peers += 1,
                Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                    std::thread::sleep(Duration::from_millis(1));
                }
                Err(error) => return Err(error),
            }
            if Instant::now() >= deadline {
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "private QEMU monitor setup timed out",
                ));
            }
        }
    }
}

pub(super) enum MonitorStream {
    Unix(UnixStream),
    Tcp(TcpStream),
}

impl MonitorStream {
    pub(super) fn set_read_timeout(&self, timeout: Option<Duration>) -> io::Result<()> {
        match self {
            Self::Unix(stream) => stream.set_read_timeout(timeout),
            Self::Tcp(stream) => stream.set_read_timeout(timeout),
        }
    }

    pub(super) fn set_write_timeout(&self, timeout: Option<Duration>) -> io::Result<()> {
        match self {
            Self::Unix(stream) => stream.set_write_timeout(timeout),
            Self::Tcp(stream) => stream.set_write_timeout(timeout),
        }
    }
}

impl Read for MonitorStream {
    fn read(&mut self, buffer: &mut [u8]) -> io::Result<usize> {
        match self {
            Self::Unix(stream) => stream.read(buffer),
            Self::Tcp(stream) => stream.read(buffer),
        }
    }
}

impl Write for MonitorStream {
    fn write(&mut self, buffer: &[u8]) -> io::Result<usize> {
        match self {
            Self::Unix(stream) => stream.write(buffer),
            Self::Tcp(stream) => stream.write(buffer),
        }
    }

    fn flush(&mut self) -> io::Result<()> {
        match self {
            Self::Unix(stream) => stream.flush(),
            Self::Tcp(stream) => stream.flush(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rustix::io::fcntl_getfd;
    use std::process::Stdio;

    #[test]
    fn client_arriving_first_cannot_become_the_monitor() {
        let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
        let address = listener.local_addr().unwrap();
        let mut attacker = TcpStream::connect(address).unwrap();
        attacker.write_all(b"attacker\n").unwrap();
        let mut pair = TcpPair::connect(listener).unwrap();
        assert_eq!(pair.rejected_peers, 1);
        assert_eq!(
            pair.monitor.peer_addr().unwrap(),
            pair.qemu.local_addr().unwrap()
        );
        assert!(fcntl_getfd(&pair.qemu).unwrap().contains(FdFlags::CLOEXEC));
        // A new outsider cannot connect once the private pair is prepared.
        let deadline = Instant::now() + TCP_SETUP_TIMEOUT;
        while TcpStream::connect_timeout(&address, TCP_SETUP_TIMEOUT).is_ok() {
            // Concurrent host tests may fork while the close-on-exec listener
            // exists; an unrelated child releases that copy on exec.
            assert!(
                Instant::now() < deadline,
                "private setup listener remained open"
            );
            std::thread::sleep(Duration::from_millis(1));
        }
        pair.qemu.write_all(b"owned\n").unwrap();
        pair.monitor
            .set_read_timeout(Some(TCP_SETUP_TIMEOUT))
            .unwrap();
        let mut buffer = [0u8; 6];
        pair.monitor.read_exact(&mut buffer).unwrap();
        assert_eq!(&buffer, b"owned\n");
        attacker.set_read_timeout(Some(TCP_SETUP_TIMEOUT)).unwrap();
        assert!(matches!(attacker.read(&mut buffer), Ok(0) | Err(_)));
    }

    #[test]
    fn spawn_failure_closes_the_private_child_endpoint() {
        let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
        let pair = TcpPair::connect(listener).unwrap();
        let mut retained_monitor = pair.monitor.try_clone().unwrap();
        let command = Command::new("/nonexistent/osdk-monitor-spawn-test");
        assert!(MonitorEndpoint::spawn_tcp(pair, command).is_err());
        retained_monitor
            .set_read_timeout(Some(TCP_SETUP_TIMEOUT))
            .unwrap();
        assert_eq!(retained_monitor.read(&mut [0; 1]).unwrap(), 0);
    }

    #[test]
    fn qemu_child_endpoint_is_not_retained_by_parent_after_spawn() {
        let mut command = Command::new("/bin/true");
        command.stdout(Stdio::null()).stderr(Stdio::null());
        let (mut child, endpoint) = MonitorEndpoint::spawn(MonitorTransport::Tcp, command).unwrap();
        assert!(child.wait().unwrap().success());
        let mut stream = endpoint.try_connect().unwrap();
        stream.set_read_timeout(Some(TCP_SETUP_TIMEOUT)).unwrap();
        assert_eq!(stream.read(&mut [0; 1]).unwrap(), 0);
    }

    #[test]
    fn unix_monitor_keeps_the_existing_qemu_server_argument() {
        let output = tempfile::NamedTempFile::new().unwrap();
        let mut command = Command::new("/usr/bin/printf");
        command.arg("%s\n").stdout(output.reopen().unwrap());
        let (mut child, endpoint) =
            MonitorEndpoint::spawn(MonitorTransport::Unix, command).unwrap();
        assert!(child.wait().unwrap().success());
        let MonitorEndpoint::Unix(path) = endpoint else {
            panic!("expected original UNIX monitor endpoint");
        };
        assert_eq!(
            std::fs::read_to_string(output.path()).unwrap(),
            format!("-monitor\nunix:{},server,nowait\n", path.to_string_lossy())
        );
    }

    #[test]
    #[ignore = "requires QEMU and A01_MONITOR_PROBE_OUT; transport probe only, no kernel"]
    fn real_qemu_uses_preconnected_fd_after_rejecting_client_first() {
        use std::{fs, path::PathBuf};
        let _ = env_logger::builder().is_test(true).try_init();
        let output =
            PathBuf::from(std::env::var_os("A01_MONITOR_PROBE_OUT").expect("new output path"));
        fs::create_dir(&output).unwrap();
        let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
        let listener_address = listener.local_addr().unwrap();
        let mut attacker = TcpStream::connect(listener_address).unwrap();
        attacker.write_all(b"quit\n").unwrap();
        let pair = TcpPair::connect(listener).unwrap();
        let child_fd = pair.qemu.as_raw_fd();
        let child_address = pair.qemu.local_addr().unwrap();
        let parent_address = pair.monitor.local_addr().unwrap();
        assert_eq!(pair.rejected_peers, 1);
        assert!(fcntl_getfd(&pair.qemu).unwrap().contains(FdFlags::CLOEXEC));
        let listener_closed =
            TcpStream::connect_timeout(&listener_address, TCP_SETUP_TIMEOUT).is_err();
        assert!(listener_closed);
        let mut command = Command::new("qemu-system-x86_64");
        command
            .args([
                "-machine",
                "q35,accel=tcg",
                "-cpu",
                "max",
                "-smp",
                "1",
                "-m",
                "64M",
                "-nodefaults",
                "-display",
                "none",
                "-serial",
                "none",
                "-S",
                "-no-reboot",
            ])
            .stdout(fs::File::create(output.join("qemu-stdout.log")).unwrap())
            .stderr(fs::File::create(output.join("qemu-stderr.log")).unwrap());
        struct OwnedChild(Child);
        impl Drop for OwnedChild {
            fn drop(&mut self) {
                let _ = self.0.kill();
                let _ = self.0.wait();
            }
        }
        let (child, endpoint) = MonitorEndpoint::spawn_tcp(pair, command).unwrap();
        let mut child = OwnedChild(child);
        let mut monitor = endpoint.try_connect().unwrap();
        monitor.set_read_timeout(Some(TCP_SETUP_TIMEOUT)).unwrap();
        monitor.set_write_timeout(Some(TCP_SETUP_TIMEOUT)).unwrap();
        let mut received = Vec::new();
        fn read_prompt(stream: &mut MonitorStream, transcript: &mut Vec<u8>) {
            let deadline = Instant::now() + Duration::from_secs(5);
            let start = transcript.len();
            loop {
                assert!(Instant::now() < deadline, "QEMU monitor prompt timeout");
                let mut buffer = [0u8; 4096];
                let count = stream.read(&mut buffer).expect("QEMU monitor read");
                assert_ne!(count, 0, "QEMU monitor closed before prompt");
                transcript.extend_from_slice(&buffer[..count]);
                if transcript[start..]
                    .windows(6)
                    .any(|bytes| bytes == b"(qemu)")
                {
                    break;
                }
            }
        }
        read_prompt(&mut monitor, &mut received);
        monitor.write_all(b"info status\n").unwrap();
        read_prompt(&mut monitor, &mut received);
        assert!(String::from_utf8_lossy(&received).contains("VM status: paused"));
        assert!(
            child.0.try_wait().unwrap().is_none(),
            "attacker quit reached QEMU"
        );
        monitor.write_all(b"quit\n").unwrap();
        let deadline = Instant::now() + Duration::from_secs(5);
        let status = loop {
            if let Some(status) = child.0.try_wait().unwrap() {
                break status;
            }
            if Instant::now() >= deadline {
                let _ = child.0.kill();
                let _ = child.0.wait();
                panic!("QEMU quit timed out");
            }
            std::thread::sleep(Duration::from_millis(10));
        };
        fs::write(output.join("monitor.log"), &received).unwrap();
        fs::write(output.join("result.json"), serde_json::to_vec_pretty(&serde_json::json!({
            "kind": "host_qemu_transport_probe_no_kernel", "qemu_pid": child.0.id(),
            "child_fd": child_fd, "qemu_endpoint": child_address.to_string(),
            "osdk_endpoint": parent_address.to_string(), "listener_closed_before_spawn": listener_closed,
            "attacker_connected_first": true, "attacker_quit_rejected": true,
            "parent_fd_was_cloexec": true, "qemu_monitor_info_status": "paused", "qemu_raw_exit": status.code(),
            "machine": "q35", "accel": "tcg", "cpu": "max", "vcpus": 1, "memory_mib": 64,
            "project_kernel_boot": false
        })).unwrap()).unwrap();
        assert!(status.success());
    }
}
