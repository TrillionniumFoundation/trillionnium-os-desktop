//! The host systemd MainPID owns the public, read-only readiness socket.
use super::*;
use std::os::linux::net::SocketAddrExt;
use std::os::unix::net::{SocketAddr, UnixDatagram};
const CONTROL: &str = "/run/droidloom-container/readiness.sock";
pub(super) fn notify_main() -> io::Result<()> {
    notify(b"READY=1")
}
pub(super) fn notify_stopping() -> io::Result<()> {
    notify(b"STOPPING=1")
}
fn notify(message: &[u8]) -> io::Result<()> {
    let dest = std::env::var_os("NOTIFY_SOCKET")
        .ok_or_else(|| error("missing system manager notification socket"))?;
    use std::os::unix::ffi::OsStrExt;
    let buf = dest.as_bytes();
    let addr = if let Some(name) = buf.strip_prefix(b"@") {
        SocketAddr::from_abstract_name(name)?
    } else {
        SocketAddr::from_pathname(PathBuf::from(dest))?
    };
    UnixDatagram::unbound()?.send_to_addr(message, &addr)?;
    Ok(())
}

struct Control {
    listener: UnixListener,
    identity: (u64, u64),
}
impl Control {
    fn bind() -> io::Result<Self> {
        let parent = Path::new(CONTROL).parent().unwrap();
        let dir = fs::symlink_metadata(parent)?;
        if !dir.is_dir() || dir.uid() != unsafe { libc::geteuid() } || dir.mode() & 0o022 != 0 {
            return Err(error("fixed control socket directory lacks cell ownership"));
        }
        let listener = UnixListener::bind(CONTROL)?;
        let node = fs::symlink_metadata(CONTROL)?;
        let owner = Self {
            listener,
            identity: (node.dev(), node.ino()),
        };
        fs::set_permissions(CONTROL, fs::Permissions::from_mode(0o666))?;
        owner.listener.set_nonblocking(true)?;
        Ok(owner)
    }
}
impl Drop for Control {
    fn drop(&mut self) {
        if let Ok(n) = fs::symlink_metadata(CONTROL) {
            if n.file_type().is_socket() && (n.dev(), n.ino()) == self.identity {
                let _ = fs::remove_file(CONTROL);
            }
        }
    }
}

fn reply(stream: &mut UnixStream, ok: bool, ready: bool, message: &str) -> io::Result<()> {
    let frame =
        serde_json::json!({"ok":ok,"state":if ready{"running"}else{"starting"},"message":message});
    serde_json::to_writer(&mut *stream, &frame).map_err(io::Error::other)?;
    stream.write_all(b"\n")
}

#[derive(Deserialize)]
#[serde(rename_all = "snake_case")]
enum Query {
    Status,
    Readiness,
    WaitReady,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    command: Query,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Progress {
    request: Request,
}
#[derive(Deserialize)]
#[serde(untagged)]
enum Incoming {
    Direct(Request),
    Progress(Progress),
}

fn request(stream: &mut UnixStream) -> io::Result<Query> {
    stream.set_write_timeout(Some(Duration::from_millis(200)))?;
    let end = Instant::now() + Duration::from_millis(200);
    let mut bytes = Vec::new();
    let mut chunk = [0; 256];
    loop {
        let remaining = end
            .checked_duration_since(Instant::now())
            .filter(|v| !v.is_zero())
            .ok_or_else(|| error("readiness request deadline"))?;
        stream.set_read_timeout(Some(remaining))?;
        let n = stream.read(&mut chunk)?;
        if n == 0 {
            break;
        }
        bytes.extend_from_slice(&chunk[..n]);
        if bytes.len() > 1024 {
            return Err(error("oversized readiness request"));
        }
    }
    let frame: Incoming = serde_json::from_slice(&bytes).map_err(io::Error::other)?;
    Ok(match frame {
        Incoming::Direct(req) => req.command,
        Incoming::Progress(msg) => msg.request.command,
    })
}

fn checked_ready_reply(
    stream: &mut UnixStream,
    check: &impl Fn() -> io::Result<()>,
) -> io::Result<()> {
    check()?;
    // A disconnected client does not revoke a healthy Android generation.
    let _ = reply(
        stream,
        true,
        true,
        "Android boot completed and ActivityManager answers Binder",
    );
    Ok(())
}

pub(super) struct Clients {
    control: Control,
    pending: Vec<(UnixStream, Instant)>,
}
impl Clients {
    pub(super) fn bind() -> io::Result<Self> {
        Ok(Self {
            control: Control::bind()?,
            pending: Vec::new(),
        })
    }
    pub(super) fn poll(
        &mut self,
        android: bool,
        check: impl Fn() -> io::Result<()>,
    ) -> io::Result<()> {
        if android {
            for (mut socket, _) in self.pending.drain(..) {
                checked_ready_reply(&mut socket, &check)?;
            }
        } else {
            self.pending.retain_mut(|(socket, deadline)| {
                if Instant::now() < *deadline {
                    return true;
                }
                let _ = reply(socket, false, false, "Android readiness deadline expired");
                false
            });
        }
        match self.control.listener.accept() {
            Ok((mut socket, _)) => match request(&mut socket) {
                Ok(Query::WaitReady) if !android && self.pending.len() < 8 => {
                    self.pending.push((socket, Instant::now() + START_LIMIT))
                }
                Ok(Query::WaitReady) if !android => {
                    let _ = reply(&mut socket, false, false, "Readiness request queue is full");
                }
                Ok(_) if android => checked_ready_reply(&mut socket, &check)?,
                Ok(_) => {
                    let _ = reply(&mut socket, true, false, "Waiting for Android boot");
                }
                Err(_) => {
                    let _ = reply(&mut socket, false, false, "Unsupported readiness request");
                }
            },
            Err(e)
                if matches!(
                    e.kind(),
                    io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
                ) => {}
            Err(e) => return Err(e),
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejected_enforcement_writes_no_positive_frame() {
        let (mut service, mut client) = UnixStream::pair().unwrap();
        assert!(checked_ready_reply(&mut service, &|| Err(error("changed kernel epoch"))).is_err());
        client.set_nonblocking(true).unwrap();
        let mut b = [0; 256];
        assert_eq!(
            client.read(&mut b).unwrap_err().kind(),
            io::ErrorKind::WouldBlock
        );
        checked_ready_reply(&mut service, &|| Ok(())).unwrap();
        let n = client.read(&mut b).unwrap();
        let observed: serde_json::Value = serde_json::from_slice(&b[..n]).unwrap();
        assert_eq!(observed["state"], "running");
    }

    #[test]
    fn only_fixed_readonly_requests_are_accepted() {
        for (body, allowed) in [
            (r#"{"request":{"command":"wait_ready"}}"#, true),
            (r#"{"command":"readiness"}"#, true),
            (r#"{"command":"launch"}"#, false),
            (r#"{"command":"status","path":"/other"}"#, false),
        ] {
            let (mut client, mut server) = UnixStream::pair().unwrap();
            client.write_all(body.as_bytes()).unwrap();
            client.shutdown(std::net::Shutdown::Write).unwrap();
            assert_eq!(request(&mut server).is_ok(), allowed);
        }
    }
}
