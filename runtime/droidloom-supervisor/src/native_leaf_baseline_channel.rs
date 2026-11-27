//! One private, check-only channel for the source-owned native leaf invocation.
//! Only a live NativeLeafBaselineObservation can create the production payload.
//! No pathname listener, command/PID/UID input or deserializable authority exists.
use crate::native_leaf_baseline::NativeLeafBaselineObservation;
use std::fs::File;
use std::io::{self, Read, Write};
use std::os::fd::{AsRawFd, FromRawFd, RawFd};
use std::os::unix::net::UnixDatagram;
use std::process::Command;
use std::time::Instant;

pub(crate) const FACTS_ENV: &str = "DROIDLOOM_NATIVE_LEAF_FACTS_FD";
pub(crate) const GUARD_ENV: &str = "DROIDLOOM_NATIVE_LEAF_GUARD_FD";
const MAX_FACTS: usize = 262144;
const MAX_CHECKS: usize = 4096;

pub(crate) struct NativeLeafChannel {
    facts: File,
    server: UnixDatagram,
    child: UnixDatagram,
    deadline: Instant,
    checks: usize,
}
fn invalid(why: &'static str) -> io::Error {
    io::Error::other(why)
}
fn sealed(bytes: &[u8]) -> io::Result<File> {
    if bytes.is_empty() || bytes.len() > MAX_FACTS {
        return Err(invalid("native leaf facts bound"));
    }
    let raw = unsafe {
        libc::memfd_create(
            c"droidloom-native-leaf-facts".as_ptr(),
            libc::MFD_CLOEXEC | libc::MFD_ALLOW_SEALING,
        )
    };
    if raw < 0 {
        return Err(io::Error::last_os_error());
    }
    let mut f = unsafe { File::from_raw_fd(raw) };
    f.write_all(bytes)?;
    let seals = libc::F_SEAL_SEAL | libc::F_SEAL_SHRINK | libc::F_SEAL_GROW | libc::F_SEAL_WRITE;
    if unsafe { libc::fcntl(f.as_raw_fd(), libc::F_ADD_SEALS, seals) } < 0 {
        return Err(io::Error::last_os_error());
    }
    // The pathname is the just-created descriptor, not an input name.
    let readonly = File::open(format!("/proc/self/fd/{}", f.as_raw_fd()))?;
    use std::os::unix::fs::MetadataExt;
    if readonly.metadata()?.ino() != f.metadata()?.ino()
        || readonly.metadata()?.dev() != f.metadata()?.dev()
        || unsafe { libc::fcntl(readonly.as_raw_fd(), libc::F_GET_SEALS) } != seals
    {
        return Err(invalid("native leaf sealed facts identity changed"));
    }
    Ok(readonly)
}
impl NativeLeafChannel {
    pub(crate) fn new(
        observation: &NativeLeafBaselineObservation<'_>,
        inspector: &crate::control::NativeApplicationInspector,
        deadline: Instant,
    ) -> Result<Self, String> {
        observation
            .verify_local(inspector, deadline)
            .map_err(|e| e.to_string())?;
        let bytes = serde_json::to_vec(&observation.facts()).map_err(|e| e.to_string())?;
        Self::from_bytes(&bytes, deadline).map_err(|e| e.to_string())
    }
    fn from_bytes(bytes: &[u8], deadline: Instant) -> io::Result<Self> {
        if Instant::now() >= deadline {
            return Err(invalid("native leaf channel deadline expired"));
        }
        let facts = sealed(bytes)?;
        let (server, child) = UnixDatagram::pair()?;
        server.set_nonblocking(true)?;
        // Socketpair has no filesystem address; only these two held endpoints
        // exist. Parent retains the server, fixed exec inherits only child.
        Ok(Self {
            facts,
            server,
            child,
            deadline,
            checks: 0,
        })
    }
    pub(crate) fn prepare(&self, command: &mut Command) -> [RawFd; 2] {
        let f = self.facts.as_raw_fd();
        let g = self.child.as_raw_fd();
        command
            .env(FACTS_ENV, f.to_string())
            .env(GUARD_ENV, g.to_string());
        [f, g]
    }
    fn serve_with(&mut self, mut check: impl FnMut() -> Result<(), String>) -> Result<(), String> {
        let mut request = [0u8; 2];
        match self.server.recv(&mut request) {
            Err(e) if e.kind() == io::ErrorKind::WouldBlock => return Ok(()),
            Err(e) => return Err(format!("native leaf guard channel failed: {e}")),
            Ok(n) => {
                if n != 1
                    || request[0] != b'G'
                    || self.checks >= MAX_CHECKS
                    || Instant::now() >= self.deadline
                {
                    let _ = self.server.send(b"1");
                    return Err(
                        "native leaf guard accepts only bounded current-custody checks".into(),
                    );
                }
            }
        }
        let result = check();
        if result.is_err() || Instant::now() >= self.deadline {
            let _ = self.server.send(b"1");
            return result.and(Err(
                "native leaf custody check finished after its actual invocation budget".into(),
            ));
        }
        self.server
            .send(b"0")
            .map_err(|e| format!("native leaf guard reply failed: {e}"))?;
        self.checks += 1;
        Ok(())
    }
    pub(crate) fn serve(
        &mut self,
        observation: &NativeLeafBaselineObservation<'_>,
        inspector: &crate::control::NativeApplicationInspector,
    ) -> Result<(), String> {
        let deadline = self.deadline;
        self.serve_with(|| {
            observation
                .verify_local(inspector, deadline)
                .map_err(|e| e.to_string())
        })
    }
    pub(crate) fn finish(&self) -> Result<(), String> {
        if self.checks == 0 {
            return Err("native leaf never checked the actual retained owner".into());
        }
        if Instant::now() >= self.deadline {
            return Err("native leaf channel retirement exceeded invocation budget".into());
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;
    #[test]
    fn native_leaf_channel_seals_real_payload_and_has_no_path_listener() {
        let mut ch = NativeLeafChannel::from_bytes(
            b"{\"comparison_only\":true}",
            Instant::now() + Duration::from_secs(3),
        )
        .unwrap();
        let mut value = String::new();
        ch.facts.read_to_string(&mut value).unwrap();
        assert_eq!(value, "{\"comparison_only\":true}");
        assert_eq!(
            unsafe { libc::fcntl(ch.facts.as_raw_fd(), libc::F_GETFL) } & libc::O_ACCMODE,
            libc::O_RDONLY
        );
        assert!(ch.facts.write_all(b"x").is_err());
        assert!(ch.server.local_addr().unwrap().is_unnamed());
        ch.child.send(b"G").unwrap();
        let mut called = 0;
        ch.serve_with(|| {
            called += 1;
            Ok(())
        })
        .unwrap();
        let mut reply = [0u8; 1];
        assert_eq!(ch.child.recv(&mut reply).unwrap(), 1);
        assert_eq!(reply[0], b'0');
        assert_eq!(called, 1);
        ch.finish().unwrap();
    }
    #[test]
    fn native_leaf_channel_rejects_foreign_requests_expiry_and_failed_actual_guard() {
        for request in [b"P".as_slice(), b"GG", b""] {
            let mut ch =
                NativeLeafChannel::from_bytes(b"{}", Instant::now() + Duration::from_secs(3))
                    .unwrap();
            ch.child.send(request).unwrap();
            assert!(
                ch.serve_with(|| panic!("unvalidated request must not query owner"))
                    .is_err()
            );
            assert!(ch.finish().is_err());
        }
        let mut ch =
            NativeLeafChannel::from_bytes(b"{}", Instant::now() + Duration::from_secs(3)).unwrap();
        ch.child.send(b"G").unwrap();
        assert!(
            ch.serve_with(|| Err("actual original owner changed".into()))
                .unwrap_err()
                .contains("owner changed")
        );
        let mut reply = [0u8; 1];
        ch.child.recv(&mut reply).unwrap();
        assert_eq!(reply[0], b'1');
        assert!(ch.finish().is_err());
        let mut expired =
            NativeLeafChannel::from_bytes(b"{}", Instant::now() + Duration::from_secs(3)).unwrap();
        expired.deadline = Instant::now() - Duration::from_millis(1);
        expired.child.send(b"G").unwrap();
        assert!(
            expired
                .serve_with(|| panic!("expired channel must not query owner"))
                .is_err()
        );
    }
}
