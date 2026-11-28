//! Direct connection to the held Ubuntu PID 1 socket for a kernel-first release.
use super::*;
use crate::production_mac::EarlyManagerClient;

pub(super) struct EarlyManagerSocket {
    principal: EarlyManagerClient,
    network: File,
    connection: File,
}

fn mac<T>(result: std::result::Result<T, crate::production_mac::MacError>) -> Result<T> {
    result.map_err(|e| CgroupError::Owner(e.to_string()))
}

fn task_network(proc: &File) -> Result<File> {
    let fd = unsafe {
        libc::openat(
            proc.as_raw_fd(),
            c"ns/net".as_ptr(),
            libc::O_RDONLY | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(unsafe { File::from_raw_fd(fd) })
}

fn connect_held(server: &File) -> Result<File> {
    // An fd alias addresses the held sock_file even if the name changes.
    let alias = format!("/proc/self/fd/{}", server.as_raw_fd());
    let mut addr: libc::sockaddr_un = unsafe { std::mem::zeroed() };
    addr.sun_family = libc::AF_UNIX as _;
    require(
        alias.len() < addr.sun_path.len(),
        "bounded held manager descriptor alias",
    )?;
    for (dst, ch) in addr.sun_path.iter_mut().zip(alias.bytes()) {
        *dst = ch as _;
    }
    let fd = unsafe {
        libc::socket(
            libc::AF_UNIX,
            libc::SOCK_STREAM | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
            0,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let socket = unsafe { File::from_raw_fd(fd) };
    let length = std::mem::offset_of!(libc::sockaddr_un, sun_path) + alias.len() + 1;
    if unsafe { libc::connect(fd, (&raw const addr).cast(), length as _) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(socket)
}

impl EarlyManagerSocket {
    pub(super) fn connect(
        principal: EarlyManagerClient,
        server: &File,
        deadline: Instant,
    ) -> Result<Self> {
        before(deadline)?;
        mac(principal.check_server(server))?;
        let network = File::open("/proc/thread-self/ns/net")?;
        mac(principal.network(&network))?;
        let connection = connect_held(server)?;
        peer_credentials(&connection)?;
        before(deadline)?;
        Ok(Self {
            principal,
            network,
            connection,
        })
    }

    pub(super) fn check(&self, server: &File, manager: &File, observer: &File) -> Result<()> {
        mac(self.principal.check_server(server))?;
        mac(self.principal.check_peer(&self.connection, manager))?;
        mac(self.principal.network(&self.network))?;
        let original = NodeIdentity::of(&self.network)?;
        for current in [
            File::open("/proc/thread-self/ns/net")?,
            task_network(manager)?,
            task_network(observer)?,
        ] {
            require(
                NodeIdentity::of(&current)? == original,
                "manager or observer left the original host network namespace",
            )?;
        }
        Ok(())
    }

    pub(super) fn connection(&self) -> &File {
        &self.connection
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::net::UnixListener;
    #[test]
    fn connected_held_server_cannot_be_replaced_by_renaming_another_listener() {
        let temporary = tempfile::tempdir().unwrap();
        let path = temporary.path().join("private");
        let displaced = temporary.path().join("old");
        let listener = UnixListener::bind(&path).unwrap();
        let alias = CString::new(path.as_os_str().as_encoded_bytes()).unwrap();
        let fd = unsafe {
            libc::open(
                alias.as_ptr(),
                libc::O_PATH | libc::O_CLOEXEC | libc::O_NOFOLLOW,
            )
        };
        assert!(fd >= 0);
        let server = unsafe { File::from_raw_fd(fd) };
        std::fs::rename(&path, &displaced).unwrap();
        let replacement = UnixListener::bind(&path).unwrap();
        replacement.set_nonblocking(true).unwrap();
        let client = connect_held(&server).unwrap();
        listener.set_nonblocking(true).unwrap();
        let _original = listener.accept().unwrap();
        assert_eq!(
            replacement.accept().unwrap_err().kind(),
            io::ErrorKind::WouldBlock
        );
        assert!(peer_credentials(&client).is_err());
    }
}
