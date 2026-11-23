//! Observations of two different kernel objects in an already owned session.
//!
//! A pathname socket inode's security.selinux value is not SO_PEERSEC, and
//! neither observation identifies the process sending a particular message.
//! These bytes are retained and rechecked, never converted into an allow rule,
//! a selected-policy witness, or Ready. Selected socket creation and the full
//! Composer policy/provider closure remain separately required.
use super::*;
use std::ffi::CString;

const CONTEXT_LIMIT: usize = 1024;

fn bounded_observation(raw: Vec<u8>) -> Result<Vec<u8>> {
    check(
        !raw.is_empty() && raw.len() <= CONTEXT_LIMIT,
        "task-control kernel security observation is empty or unbounded",
    )?;
    // This is opaque observation storage, not a SELinux-context parser. In
    // particular, SO_PEERSEC may describe another active LSM. Preserve every
    // byte, including spaces, non-UTF-8 bytes and terminator representation;
    // neither syntax nor successful storage grants selected-policy authority.
    Ok(raw)
}

fn original_socket_alias(file: &File, deadline: Instant) -> Result<CString> {
    before(deadline)?;
    let mode = file.metadata()?.mode();
    let flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
    if flags < 0 {
        return Err(io::Error::last_os_error().into());
    }
    check(
        mode & libc::S_IFMT == libc::S_IFSOCK && flags & libc::O_PATH != 0,
        "task-control inode context requires the original O_PATH socket inode",
    )?;
    // Like the existing systemd server-inode observer, follow only the held
    // descriptor's own proc alias. fgetxattr on O_PATH is not a supported
    // substitute on the selected kernel. No pathname comes from a request.
    CString::new(format!("/proc/self/fd/{}", file.as_raw_fd()))
        .map_err(|_| NamespaceError::Rejected("invalid held task-control FD alias"))
}

fn read_inode_context(alias: &CStr) -> Result<Vec<u8>> {
    let mut bytes = [0_u8; CONTEXT_LIMIT];
    let count = unsafe {
        libc::getxattr(
            alias.as_ptr(),
            c"security.selinux".as_ptr(),
            bytes.as_mut_ptr().cast(),
            bytes.len(),
        )
    };
    if count < 0 {
        return Err(io::Error::last_os_error().into());
    }
    check(
        count > 0 && count as usize <= bytes.len(),
        "task-control inode security context length differs",
    )?;
    Ok(bytes[..count as usize].to_vec())
}

fn connection_node(socket: &File, deadline: Instant) -> Result<Node> {
    before(deadline)?;
    check(
        socket.metadata()?.mode() & libc::S_IFMT == libc::S_IFSOCK,
        "task-control peer context requires the connected socket",
    )?;
    for (option, expected) in [
        (libc::SO_DOMAIN, libc::AF_UNIX),
        (libc::SO_TYPE, libc::SOCK_SEQPACKET),
        (libc::SO_ACCEPTCONN, 0),
    ] {
        let mut value = -1_i32;
        let mut size = std::mem::size_of_val(&value) as libc::socklen_t;
        if unsafe {
            libc::getsockopt(
                socket.as_raw_fd(),
                libc::SOL_SOCKET,
                option,
                (&mut value as *mut i32).cast(),
                &mut size,
            )
        } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
        check(
            size as usize == std::mem::size_of_val(&value) && value == expected,
            "task-control peer context socket role differs",
        )?;
    }
    Ok(Node::of(socket)?)
}

fn read_peer_security(socket: &File) -> Result<Vec<u8>> {
    let mut bytes = [0_u8; CONTEXT_LIMIT];
    let mut length = bytes.len() as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            socket.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERSEC,
            bytes.as_mut_ptr().cast(),
            &mut length,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    check(
        length > 0 && length as usize <= bytes.len(),
        "task-control peer security context length differs",
    )?;
    Ok(bytes[..length as usize].to_vec())
}

pub(super) struct InodeSelinuxContext {
    seal: Seal,
    selinux_xattr: Vec<u8>,
}

impl InodeSelinuxContext {
    fn observe(
        file: &File,
        deadline: Instant,
        read: impl FnOnce(&CStr) -> Result<Vec<u8>>,
    ) -> Result<Self> {
        let alias = original_socket_alias(file, deadline)?;
        let seal = Seal::of(file)?;
        let bytes = bounded_observation(read(&alias)?)?;
        check(
            Seal::of(file)? == seal,
            "task-control inode changed during security context read",
        )?;
        before(deadline)?;
        Ok(Self {
            seal,
            selinux_xattr: bytes,
        })
    }

    pub(super) fn acquire(file: &File, deadline: Instant) -> Result<Self> {
        Self::observe(file, deadline, read_inode_context)
    }

    pub(super) fn revalidate(&self, file: &File, deadline: Instant) -> Result<()> {
        let current = Self::acquire(file, deadline)?;
        check(
            self.seal == current.seal && self.selinux_xattr == current.selinux_xattr,
            "original task-control socket inode or security context changed",
        )
    }
}

// SO_PEERSEC is supplied by the active LSM. A successful query does not
// establish that its bytes are a SELinux process domain or the creator's
// current process label. Preserve this observation independently.
pub(super) struct ConnectionPeerSecurity {
    node: Node,
    peer_security: Vec<u8>,
}

impl ConnectionPeerSecurity {
    fn observe(
        socket: &File,
        deadline: Instant,
        read: impl FnOnce(&File) -> Result<Vec<u8>>,
    ) -> Result<Self> {
        let node = connection_node(socket, deadline)?;
        let bytes = bounded_observation(read(socket)?)?;
        check(
            connection_node(socket, deadline)? == node,
            "task-control connected socket changed during peer context read",
        )?;
        Ok(Self {
            node,
            peer_security: bytes,
        })
    }

    pub(super) fn acquire(socket: &File, deadline: Instant) -> Result<Self> {
        Self::observe(socket, deadline, read_peer_security)
    }

    fn check_observation(&self, current: &Self) -> Result<()> {
        check(
            self.node == current.node && self.peer_security == current.peer_security,
            "original task-control connection or SO_PEERSEC changed",
        )
    }

    pub(super) fn revalidate(&self, socket: &File, deadline: Instant) -> Result<()> {
        self.check_observation(&Self::acquire(socket, deadline)?)
    }
}

#[cfg(test)]
#[path = "production_namespace_task_control_mac_tests.rs"]
mod tests;
