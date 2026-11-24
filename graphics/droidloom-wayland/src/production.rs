//! Presenter side of the original early owner's descriptor handoff.
//! No path, PID, UID or GID supplied by the desktop environment is authority.
#[path = "../../../runtime/droidloom-supervisor/src/production_frontend_protocol.rs"]
#[allow(dead_code)]
pub(crate) mod wire;
use std::fs::{self, File};
use std::io;
use std::os::fd::{AsRawFd, OwnedFd, RawFd};
use std::os::unix::fs::MetadataExt;
use std::sync::{
    Arc,
    atomic::{AtomicBool, Ordering},
};
use std::time::{Duration, Instant};
use wire::{Node, Role, check};

pub(crate) struct Registration {
    role: Role,
    socket_seal: SocketSeal,
    channel: OwnedFd,
    owner: wire::Peer,
    parent: File,
    parent_node: Node,
    socket_node: File,
    socket_identity: Node,
    composer_pidfd: OwnedFd,
    composer_node: Node,
    composer_socket: OwnedFd,
    pid: u32,
    uid: u32,
    gid: u32,
}
#[derive(Clone, PartialEq, Eq)]
struct SocketSeal {
    node: Node,
    values: [u64; 5],
    times: [i64; 4],
}
impl SocketSeal {
    fn of(file: &File) -> io::Result<Self> {
        let m = file.metadata()?;
        Ok(Self {
            node: Node(m.dev(), m.ino()),
            values: [
                m.mode() as u64,
                m.uid() as u64,
                m.gid() as u64,
                m.nlink(),
                m.len(),
            ],
            times: [m.mtime(), m.mtime_nsec(), m.ctime(), m.ctime_nsec()],
        })
    }
}
fn same_socket(
    parent: &File,
    node: &File,
    identity: Node,
    role: Role,
    seal: &SocketSeal,
) -> io::Result<()> {
    let current = wire::socket_node(parent, role.control(), 0, 0, 0o666)?;
    check(
        Node::of(node)? == identity
            && Node::of(&current)? == identity
            && SocketSeal::of(node)? == *seal
            && SocketSeal::of(&current)? == *seal,
        "the original owner socket inode was replaced",
    )
}
fn self_role() -> io::Result<()> {
    let bytes = fs::read("/proc/self/attr/selinux/current")?;
    check(
        bytes.strip_suffix(&[0]).unwrap_or(&bytes) == wire::PRESENTER_CONTEXT,
        "production presentation requires its dedicated current SELinux role",
    )?;
    check(
        unsafe { libc::getuid() } != 0 && unsafe { libc::getuid() } == unsafe { libc::geteuid() },
        "production presenter must be the ordinary desktop user",
    )
}
fn running(base: Option<&Registration>, stop: Option<&AtomicBool>) -> io::Result<()> {
    check(
        !stop.is_some_and(|s| s.load(Ordering::Acquire)),
        "frontend bridge stopped",
    )?;
    if let Some(base) = base {
        base.check()?;
    }
    Ok(())
}
fn connected(
    role: Role,
    until: Instant,
    base: Option<&Registration>,
    stop: Option<&AtomicBool>,
) -> io::Result<(OwnedFd, File, File)> {
    loop {
        check(
            Instant::now() < until,
            "original frontend owner did not become available",
        )?;
        running(base, stop)?;
        let attempt: io::Result<(OwnedFd, File, File)> = (|| {
            let parent = wire::trusted_directory(wire::CONTROL_PARENT)?;
            check(
                parent.metadata()?.mode() & 0o7777 == 0o711,
                "frontend control parent mode differs",
            )?;
            let node = wire::socket_node(&parent, role.control(), 0, 0, 0o666)?;
            let identity = Node::of(&node)?;
            let seal = SocketSeal::of(&node)?;
            let channel = wire::socket()?;
            let path = format!(
                "/proc/self/fd/{}/{}",
                parent.as_raw_fd(),
                role.control().to_str().unwrap()
            );
            let (address, size) = wire::address(&path)?;
            wire::cv(unsafe {
                libc::connect(
                    channel.as_raw_fd(),
                    (&address as *const libc::sockaddr_un).cast(),
                    size,
                )
            })?;
            same_socket(&parent, &node, identity, role, &seal)?;
            Ok((channel, parent, node))
        })();
        match attempt {
            Ok(value) => return Ok(value),
            Err(e)
                if matches!(
                    e.kind(),
                    io::ErrorKind::NotFound
                        | io::ErrorKind::ConnectionRefused
                        | io::ErrorKind::WouldBlock
                ) =>
            {
                std::thread::sleep(Duration::from_millis(50));
            }
            Err(e) => return Err(e),
        }
    }
}
impl Registration {
    pub(crate) fn connect() -> io::Result<Arc<Self>> {
        Self::connect_role(Role::Composer, None, None).map(Arc::new)
    }
    pub(crate) fn connect_role(
        role: Role,
        base: Option<&Registration>,
        stop: Option<&AtomicBool>,
    ) -> io::Result<Self> {
        check(
            (role == Role::Composer) == base.is_none(),
            "companion requires the original Composer authorization",
        )?;
        self_role()?;
        running(base, stop)?;
        let until = Instant::now() + Duration::from_secs(240);
        let (channel, parent, socket_node) = connected(role, until, base, stop)?;
        let owner = wire::Peer::acquire(&channel, wire::BROKER_CONTEXT)?;
        check(
            owner.uid == 0 && owner.gid == 0,
            "frontend owner is not the root broker",
        )?;
        wire::exact_ids(&wire::pid_info(&owner.pidfd)?, 0, 0)?;
        if let Some(base) = base {
            check(
                Node::of(&owner.pidfd)? == Node::of(&base.owner.pidfd)?,
                "companion owner is not the original Composer owner",
            )?;
        }
        let nonce = wire::fresh_nonce()?;
        let hello = wire::Record::control(wire::HELLO, nonce);
        loop {
            running(base, stop)?;
            owner.revalidate(&channel)?;
            match wire::send(&channel, &hello) {
                Ok(()) => break,
                Err(e)
                    if matches!(
                        e.kind(),
                        io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
                    ) =>
                {
                    wire::wait(&channel, libc::POLLOUT, until)?
                }
                Err(e) => return Err(e),
            }
        }
        let mut grant = loop {
            running(base, stop)?;
            owner.revalidate(&channel)?;
            match wire::receive(&channel)? {
                Some(r) => break r,
                None => wire::wait(&channel, libc::POLLIN, until)?,
            }
        };
        wire::reply(&grant, wire::GRANT, nonce)?;
        let composer_pidfd = grant.fds.pop().unwrap();
        let composer_socket = grant.fds.pop().unwrap();
        let value = Self {
            role,
            socket_seal: SocketSeal::of(&socket_node)?,
            parent_node: Node::of(&parent)?,
            socket_identity: Node::of(&socket_node)?,
            composer_node: Node::of(&composer_pidfd)?,
            channel,
            owner,
            parent,
            socket_node,
            composer_pidfd,
            composer_socket,
            pid: grant.pid,
            uid: grant.uid,
            gid: grant.gid,
        };
        value.validate_resources()?;
        let ack = wire::Record::control(wire::ACK, nonce);
        loop {
            running(base, stop)?;
            value.validate_resources()?;
            match wire::send(&value.channel, &ack) {
                Ok(()) => break,
                Err(e)
                    if matches!(
                        e.kind(),
                        io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
                    ) =>
                {
                    wire::wait(&value.channel, libc::POLLOUT, until)?
                }
                Err(e) => return Err(e),
            }
        }
        value.check()?;
        Ok(value)
    }
    fn validate_resources(&self) -> io::Result<()> {
        self.owner.revalidate(&self.channel)?;
        wire::exact_ids(&wire::pid_info(&self.owner.pidfd)?, 0, 0)?;
        check(
            Node::of(&self.parent)? == self.parent_node,
            "frontend control parent changed",
        )?;
        let named = wire::trusted_directory(wire::CONTROL_PARENT)?;
        check(
            Node::of(&named)? == self.parent_node,
            "frontend control directory was replaced",
        )?;
        same_socket(
            &self.parent,
            &self.socket_node,
            self.socket_identity,
            self.role,
            &self.socket_seal,
        )?;
        wire::socket_shape_as(&self.composer_socket, self.role.socket_type(), false)?;
        wire::endpoint_live(&self.composer_socket)?;
        let peer = wire::credentials(&self.composer_socket)?;
        let again = wire::peer_pidfd(&self.composer_socket)?;
        let info = wire::pid_info(&self.composer_pidfd)?;
        wire::exact_ids(&info, self.uid, self.gid)?;
        check(
            self.pid > 1
                && info.pid == self.pid
                && peer.pid as u32 == self.pid
                && peer.uid == self.uid
                && peer.gid == self.gid
                && Node::of(&self.composer_pidfd)? == self.composer_node
                && Node::of(&again)? == self.composer_node
                && wire::peer_security(&self.composer_socket)? == self.role.context(),
            "granted descriptors do not identify the same live Composer",
        )?;
        self_role()?;
        self.owner.revalidate(&self.channel)
    }
    pub(crate) fn check(&self) -> io::Result<()> {
        let result = self
            .validate_resources()
            .and_then(|()| wire::control_live(&self.channel));
        if result.is_err() {
            wire::shutdown(&self.composer_socket);
            wire::shutdown(&self.channel);
        }
        result
    }
    pub(crate) fn revoke(&self) {
        wire::shutdown(&self.composer_socket);
        wire::shutdown(&self.channel);
    }
    pub(crate) fn endpoint(&self) -> io::Result<OwnedFd> {
        self.check()?;
        self.composer_socket.try_clone()
    }
    pub(crate) fn credentials(&self) -> (u32, u32, u32) {
        (self.pid, self.uid, self.gid)
    }
    pub(crate) fn fds(&self) -> [RawFd; 3] {
        [
            self.channel.as_raw_fd(),
            self.owner.pidfd.as_raw_fd(),
            self.composer_pidfd.as_raw_fd(),
        ]
    }
}
impl Drop for Registration {
    fn drop(&mut self) {
        wire::shutdown(&self.composer_socket);
        wire::shutdown(&self.channel);
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn production_does_not_accept_environment_identity_as_authority() {
        // The fixed production constructor has no PID/path/descriptor input.
        // A normal test role must fail before connecting or reading a grant.
        assert!(self_role().is_err());
    }
}
