//! Trusted startup only. No public IPC request can open/export a display.
use super::notes_bootstrap::{receive_ack, require_socket_type, send_descriptors};
use std::fs::File;
use std::io::{self, Read};
use std::net::Shutdown;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::net::{UnixDatagram, UnixStream};
use std::time::{Duration, Instant};
use trill_ui_broker::desktop::{DesktopService, NativeX11};
use trill_ui_core::desktop::{
    encode_hex, DesktopBootstrapAck, DesktopBootstrapStatus, DesktopTargetIdentity,
};

#[derive(Default)]
pub struct DesktopStartup {
    pub enabled: bool,
    pub x11_fd: Option<i32>,
    pub cookie_fd: Option<i32>,
    pub server_pid: Option<u32>,
    pub window: Option<u32>,
}
impl DesktopStartup {
    pub fn validate(&self) -> io::Result<()> {
        let any = self.x11_fd.is_some()
            || self.cookie_fd.is_some()
            || self.server_pid.is_some()
            || self.window.is_some();
        if (!self.enabled && any)
            || (self.enabled
                && (self.x11_fd.is_none_or(|fd| fd < 3)
                    || self
                        .server_pid
                        .is_none_or(|pid| pid == 0 || pid > i32::MAX as u32)
                    || self.window.is_none_or(|id| id == 0)))
            || self
                .cookie_fd
                .is_some_and(|fd| fd < 3 || Some(fd) == self.x11_fd)
        {
            return Err(io::Error::other(
                "incomplete or invalid private desktop startup",
            ));
        }
        Ok(())
    }
}
fn take_fd(fd: i32) -> io::Result<OwnedFd> {
    // Explicit trusted startup transfers ownership. Verify existence and mark
    // CLOEXEC before any child can launch; do not retain a hidden alias.
    if unsafe { libc::fcntl(fd, libc::F_GETFD) } < 0 {
        return Err(io::Error::last_os_error());
    }
    let owned = unsafe { OwnedFd::from_raw_fd(fd) };
    if unsafe { libc::fcntl(owned.as_raw_fd(), libc::F_SETFD, libc::FD_CLOEXEC) } < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(owned)
}
fn random_hex() -> io::Result<String> {
    let mut bytes = [0; 16];
    File::open("/dev/urandom")?.read_exact(&mut bytes)?;
    Ok(encode_hex(&bytes))
}
pub fn start(startup: DesktopStartup, session_instance: &str) -> io::Result<DesktopService> {
    startup.validate()?;
    require_socket_type(0, libc::SOCK_DGRAM)?;
    let channel = UnixDatagram::from(take_fd(0)?);
    if !channel.local_addr()?.is_unnamed() || !channel.peer_addr()?.is_unnamed() {
        return Err(io::Error::other(
            "desktop bootstrap requires private unnamed pair",
        ));
    }
    let fd = startup
        .x11_fd
        .ok_or_else(|| io::Error::other("X11 descriptor missing"))?;
    require_socket_type(fd, libc::SOCK_STREAM)?;
    let stream = UnixStream::from(take_fd(fd)?);
    let cookie = if let Some(fd) = startup.cookie_fd {
        let mut file = File::from(take_fd(fd)?);
        let metadata = file.metadata()?;
        if !metadata.is_file() || metadata.len() != 16 {
            return Err(io::Error::other(
                "X11 cookie requires exact 16-byte regular file",
            ));
        }
        let mut bytes = vec![0; 16];
        file.read_exact(&mut bytes)?;
        Some(bytes)
    } else {
        None
    };
    let native = NativeX11::from_stream(
        stream,
        startup.server_pid.unwrap(),
        startup.window.unwrap(),
        cookie,
    )?;
    let identity = DesktopTargetIdentity {
        session_instance: session_instance.into(),
        incarnation: random_hex()?,
        display_epoch: random_hex()?,
    };
    let (service, effect, observe, offer) = DesktopService::start(native, identity)?;
    let result = (|| -> io::Result<()> {
        let raw = serde_json::to_vec(&offer).map_err(io::Error::other)?;
        let deadline = Instant::now() + Duration::from_secs(2);
        send_descriptors(
            &channel,
            &raw,
            &[effect.as_raw_fd(), observe.as_raw_fd()],
            deadline,
        )?;
        let raw = receive_ack(&channel, deadline)?;
        let ack = DesktopBootstrapAck::parse_exact(&raw).map_err(io::Error::other)?;
        if ack.target != offer.target || ack.status != DesktopBootstrapStatus::Attached {
            return Err(io::Error::other("original owner rejected desktop target"));
        }
        Ok(())
    })();
    if let Err(error) = result {
        let _ = effect.shutdown(Shutdown::Both);
        let _ = observe.shutdown(Shutdown::Both);
        return Err(error);
    }
    Ok(service)
}
