// SPDX-License-Identifier: MPL-2.0

//! Connections to OSDK's managed QEMU monitor.

use std::{
    io::{self, Read, Write},
    net::{Ipv4Addr, TcpListener, TcpStream},
    os::unix::net::UnixStream,
    time::Duration,
};

use tempfile::TempPath;

use crate::config::scheme::MonitorTransport;

pub(super) enum MonitorEndpoint {
    Unix(TempPath),
    Tcp(TcpListener),
}

impl MonitorEndpoint {
    pub(super) fn new(transport: MonitorTransport) -> io::Result<Self> {
        match transport {
            MonitorTransport::Unix => {
                Ok(Self::Unix(tempfile::NamedTempFile::new()?.into_temp_path()))
            }
            MonitorTransport::Tcp => {
                // Keep ownership of the ephemeral port until QEMU connects,
                // rather than selecting a free port and asking QEMU to rebind it.
                let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0))?;
                listener.set_nonblocking(true)?;
                Ok(Self::Tcp(listener))
            }
        }
    }

    pub(super) fn qemu_argument(&self) -> io::Result<String> {
        match self {
            Self::Unix(path) => Ok(format!("unix:{},server,nowait", path.to_string_lossy())),
            Self::Tcp(listener) => Ok(format!("tcp:{},server=off", listener.local_addr()?)),
        }
    }

    pub(super) fn try_connect(&self) -> io::Result<MonitorStream> {
        match self {
            Self::Unix(path) => UnixStream::connect(path).map(MonitorStream::Unix),
            Self::Tcp(listener) => listener
                .accept()
                .map(|(stream, _)| MonitorStream::Tcp(stream)),
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

    const IO_TIMEOUT: Duration = Duration::from_secs(2);

    #[test]
    fn tcp_listener_owns_only_an_ephemeral_loopback_port() {
        let endpoint = MonitorEndpoint::new(MonitorTransport::Tcp).unwrap();
        let MonitorEndpoint::Tcp(listener) = &endpoint else {
            panic!("expected a TCP monitor listener");
        };
        let address = listener.local_addr().unwrap();
        assert_eq!(address.ip(), Ipv4Addr::LOCALHOST);
        assert_ne!(address.port(), 0);
        assert_eq!(
            endpoint.qemu_argument().unwrap(),
            format!("tcp:{address},server=off")
        );
        assert!(
            matches!(TcpListener::bind(address), Err(error) if error.kind() == io::ErrorKind::AddrInUse)
        );
        assert!(
            matches!(endpoint.try_connect(), Err(error) if error.kind() == io::ErrorKind::WouldBlock)
        );
        drop(endpoint);
        // Other host tests spawn processes concurrently. A child between fork
        // and exec may briefly retain the close-on-exec listener descriptor.
        let deadline = std::time::Instant::now() + IO_TIMEOUT;
        loop {
            match TcpListener::bind(address) {
                Ok(_) => break,
                Err(error)
                    if error.kind() == io::ErrorKind::AddrInUse
                        && std::time::Instant::now() < deadline =>
                {
                    std::thread::sleep(Duration::from_millis(10));
                }
                Err(error) => panic!("monitor listener was not released: {error}"),
            }
        }
    }

    #[test]
    fn tcp_monitor_exchanges_bytes_with_a_connecting_client() {
        let endpoint = MonitorEndpoint::new(MonitorTransport::Tcp).unwrap();
        let MonitorEndpoint::Tcp(listener) = &endpoint else {
            panic!("expected a TCP monitor listener");
        };
        let mut client =
            TcpStream::connect_timeout(&listener.local_addr().unwrap(), IO_TIMEOUT).unwrap();
        client.set_read_timeout(Some(IO_TIMEOUT)).unwrap();
        client.set_write_timeout(Some(IO_TIMEOUT)).unwrap();
        let mut monitor = endpoint.try_connect().unwrap();
        monitor.set_read_timeout(Some(IO_TIMEOUT)).unwrap();
        monitor.set_write_timeout(Some(IO_TIMEOUT)).unwrap();
        client.write_all(b"info status\n").unwrap();
        let mut command = [0u8; 12];
        monitor.read_exact(&mut command).unwrap();
        assert_eq!(&command, b"info status\n");
        monitor.write_all(b"running\n").unwrap();
        monitor.flush().unwrap();
        let mut response = [0u8; 8];
        client.read_exact(&mut response).unwrap();
        assert_eq!(&response, b"running\n");
    }

    #[test]
    fn unix_monitor_keeps_the_existing_qemu_server_argument() {
        let endpoint = MonitorEndpoint::new(MonitorTransport::Unix).unwrap();
        let MonitorEndpoint::Unix(path) = &endpoint else {
            panic!("expected a UNIX monitor path");
        };
        assert_eq!(
            endpoint.qemu_argument().unwrap(),
            format!("unix:{},server,nowait", path.to_string_lossy())
        );
    }
}
