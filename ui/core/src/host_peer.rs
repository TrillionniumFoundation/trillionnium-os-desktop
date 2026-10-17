//! Linux-host Unix socket peer identity, shared by Session AND its clients.
//! SO_PEERCRED enforces only same-effective-UID IPC. It cannot authenticate
//! two processes under the same UID, nor provide an A05 CapSpace/Hepta grant.
use std::io;
use std::os::unix::net::UnixStream;

#[cfg(target_os = "linux")]
use std::os::fd::AsRawFd;

#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct LinuxPeerCred {
    pub pid: i32,
    pub uid: u32,
    pub gid: u32,
}

#[cfg(target_os = "linux")]
unsafe extern "C" {
    fn getsockopt(
        fd: i32,
        level: i32,
        optname: i32,
        value: *mut std::ffi::c_void,
        length: *mut u32,
    ) -> i32;
    fn geteuid() -> u32;
}

#[cfg(target_os = "linux")]
pub fn current_effective_uid() -> u32 {
    unsafe { geteuid() }
}

#[cfg(target_os = "linux")]
pub fn linux_socket_peer_credentials(stream: &UnixStream) -> io::Result<LinuxPeerCred> {
    // Linux SOL_SOCKET=1, SO_PEERCRED=17, socklen_t=u32. The 12-byte
    // repr(C) ucred is populated by the kernel, not a peer-supplied header.
    const SOL_SOCKET: i32 = 1;
    const SO_PEERCRED: i32 = 17;
    let mut cred = LinuxPeerCred {
        pid: 0,
        uid: u32::MAX,
        gid: u32::MAX,
    };
    let mut length = std::mem::size_of::<LinuxPeerCred>() as u32;
    let status = unsafe {
        getsockopt(
            stream.as_raw_fd(),
            SOL_SOCKET,
            SO_PEERCRED,
            std::ptr::addr_of_mut!(cred).cast(),
            &mut length,
        )
    };
    if status != 0 {
        return Err(io::Error::last_os_error());
    }
    if length != std::mem::size_of::<LinuxPeerCred>() as u32 || cred.pid <= 0 {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "Invalid Linux IPC peer credentials",
        ));
    }
    Ok(cred)
}

#[cfg(not(target_os = "linux"))]
pub fn linux_socket_peer_credentials(_stream: &UnixStream) -> io::Result<LinuxPeerCred> {
    Err(io::Error::new(
        io::ErrorKind::Unsupported,
        "SO_PEERCRED requires Linux",
    ))
}

pub fn validate_same_uid(cred: LinuxPeerCred, expected_uid: u32) -> io::Result<()> {
    if cred.uid != expected_uid {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "Cross-UID host UI IPC request refused",
        ));
    }
    Ok(())
}

#[cfg(target_os = "linux")]
pub fn require_same_uid_peer(stream: &UnixStream) -> io::Result<()> {
    validate_same_uid(
        linux_socket_peer_credentials(stream)?,
        current_effective_uid(),
    )
}

#[cfg(not(target_os = "linux"))]
pub fn require_same_uid_peer(_stream: &UnixStream) -> io::Result<()> {
    Err(io::Error::new(
        io::ErrorKind::Unsupported,
        "A10 host UI IPC requires Linux SO_PEERCRED",
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    #[cfg(target_os = "linux")]
    fn both_ends_read_the_kernel_credentials_and_reject_foreign_uid() {
        let (server, client) = UnixStream::pair().unwrap();
        let current_uid = current_effective_uid();
        for socket in [&server, &client] {
            let cred = linux_socket_peer_credentials(socket).unwrap();
            assert_eq!(cred.pid, std::process::id() as i32);
            assert_eq!(cred.uid, current_uid);
            assert!(require_same_uid_peer(socket).is_ok());
            assert_eq!(
                validate_same_uid(cred, current_uid.wrapping_add(1))
                    .unwrap_err()
                    .kind(),
                io::ErrorKind::PermissionDenied
            );
        }
    }
}
