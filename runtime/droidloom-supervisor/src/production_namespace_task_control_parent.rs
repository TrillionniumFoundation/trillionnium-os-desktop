//! Endpoint and message-sender custody borrowed from the original Ready tree.
//! Init owns the listening socket; the Composer reply is authenticated separately
//! with the kernel's per-message PIDFD. A listener PID is never called Composer.
use super::*;
use sha2::{Digest, Sha256};
use std::os::unix::fs::FileExt;

#[path = "production_namespace_task_control_mac.rs"]
mod mac_observation;

const COMPOSER: &CStr = c"android.hardware.graphics.composer3-service.droidloom";
// An explicit required policy role, not a report that a selected runtime has
// installed it. Missing/different policy is a hard rejection, with no fallback.
const COMPOSER_CONTEXT: &[u8] = b"u:r:hal_graphics_composer_default:s0";

fn check(value: bool, message: &'static str) -> Result<()> {
    if value {
        Ok(())
    } else {
        Err(NamespaceError::Rejected(message))
    }
}
fn before(deadline: Instant) -> Result<()> {
    check(Instant::now() < deadline, "task-control absolute deadline")
}

#[derive(Clone, Eq, PartialEq)]
struct Seal {
    integers: [u64; 7],
    times: [i64; 4],
}
impl Seal {
    fn of(file: &File) -> Result<Self> {
        let m = file.metadata()?;
        Ok(Self {
            integers: [
                m.dev(),
                m.ino(),
                u64::from(m.mode()),
                u64::from(m.uid()),
                u64::from(m.gid()),
                m.nlink(),
                m.len(),
            ],
            times: [m.mtime(), m.mtime_nsec(), m.ctime(), m.ctime_nsec()],
        })
    }
}

pub(crate) struct TaskControlEndpoint {
    owner: ProcessIdentity,
    root: Node,
    socket: File,
    socket_seal: Seal,
    socket_inode_selinux_context: mac_observation::InodeSelinuxContext,
    composer: File,
    composer_seal: Seal,
    composer_sha256: String,
    listener_pidfd: Option<OwnedFd>,
    connection_peer_security: Option<mac_observation::ConnectionPeerSecurity>,
}

pub(crate) struct TaskControlPeer {
    pidfd: OwnedFd,
    directory: File,
    node: Node,
    identity: ProcessIdentity,
    process_selinux_context: Vec<u8>,
}

fn endpoint_socket(root: &File) -> Result<File> {
    let dev = fixed_at(root, c"dev", true, false)?;
    let sockets = fixed_at(&dev, c"socket", true, false)?;
    fixed_at(&sockets, c"droidloom-task-control", false, false)
}
fn composer_file(root: &File) -> Result<File> {
    let vendor = fixed_at(root, c"vendor", true, false)?;
    let bin = fixed_at(&vendor, c"bin", true, false)?;
    let hw = fixed_at(&bin, c"hw", true, false)?;
    fixed_at(&hw, COMPOSER, false, true)
}
fn readonly_image(file: &File) -> Result<()> {
    let mut fs: libc::statfs = unsafe { std::mem::zeroed() };
    let mut flags: libc::statvfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstatfs(file.as_raw_fd(), &mut fs) } != 0
        || unsafe { libc::fstatvfs(file.as_raw_fd(), &mut flags) } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    check(
        [0xef53, 0xe0f5_e1e2_u32 as libc::c_long].contains(&fs.f_type)
            && flags.f_flag & libc::ST_RDONLY != 0,
        "Composer must remain in the original readonly image mount",
    )
}
fn context(directory: &File) -> Result<Vec<u8>> {
    let attrs = fixed_at(directory, c"attr", true, false)?;
    let current = fixed_at(&attrs, c"current", false, true)?;
    check_fs(current.as_raw_fd(), PROC_MAGIC)?;
    let mut bytes = Vec::new();
    current.take(257).read_to_end(&mut bytes)?;
    check(bytes.len() <= 256, "Composer context bound")?;
    if bytes.last() == Some(&0) {
        bytes.pop();
    }
    check(
        bytes == COMPOSER_CONTEXT,
        "Composer actual SELinux domain differs",
    )?;
    Ok(bytes)
}
fn process_executable(directory: &File) -> Result<File> {
    // Only the exe magic link of an already kernel-message-PIDFD-bound proc
    // inode is followed; neither a caller PID nor an executable path is used.
    let fd = unsafe {
        libc::openat(
            directory.as_raw_fd(),
            c"exe".as_ptr(),
            libc::O_PATH | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        Err(io::Error::last_os_error().into())
    } else {
        Ok(unsafe { File::from_raw_fd(fd) })
    }
}

fn listener_pidfd(socket: &OwnedFd) -> Result<OwnedFd> {
    super::super::activation_peer::require_activation_socket(socket)?;
    let mut raw = -1_i32;
    let mut size = std::mem::size_of::<i32>() as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            socket.as_raw_fd(),
            libc::SOL_SOCKET,
            77,
            (&mut raw as *mut i32).cast(),
            &mut size,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    check(raw >= 0, "kernel task-control listener PIDFD absent")?;
    let owned = unsafe { OwnedFd::from_raw_fd(raw) };
    let flags = unsafe { libc::fcntl(owned.as_raw_fd(), libc::F_GETFD) };
    check(
        size as usize == std::mem::size_of::<i32>() && flags >= 0 && flags & libc::FD_CLOEXEC != 0,
        "kernel task-control listener PIDFD shape differs",
    )?;
    Ok(owned)
}

impl ApplicationAuthority<'_> {
    pub(crate) fn task_control_endpoint(&self, deadline: Instant) -> Result<TaskControlEndpoint> {
        before(deadline)?;
        self.revalidate()?;
        let child = self.child()?;
        let root = held_child_root(child)?;
        let socket = endpoint_socket(&root)?;
        let m = socket.metadata()?;
        check(
            m.mode() == libc::S_IFSOCK | 0o660
                && m.nlink() == 1
                && m.uid()
                    == child
                        .uids
                        .start
                        .checked_add(1000)
                        .ok_or(NamespaceError::Rejected("socket UID overflow"))?
                && m.gid()
                    == child
                        .gids
                        .start
                        .checked_add(1000)
                        .ok_or(NamespaceError::Rejected("socket GID overflow"))?,
            "fixed init task-control socket identity differs",
        )?;
        let composer = composer_file(&root)?;
        let original = Seal::of(&composer)?;
        let m = composer.metadata()?;
        check(
            m.is_file()
                && m.nlink() == 1
                && (64..=64 * 1024 * 1024).contains(&m.len())
                && m.uid() == child.uids.start
                && m.gid() == child.gids.start
                && m.mode() & 0o6022 == 0
                && m.mode() & 0o111 != 0,
            "fixed Composer executable metadata differs",
        )?;
        readonly_image(&composer)?;
        let mut header = [0_u8; 64];
        composer.read_exact_at(&mut header, 0)?;
        check(
            &header[..7] == b"\x7fELF\x02\x01\x01"
                && u16::from_le_bytes([header[18], header[19]]) == 62,
            "fixed Composer is not the selected x86_64 ELF",
        )?;
        let mut hash = Sha256::new();
        let mut buffer = [0_u8; 65536];
        let mut offset = 0_u64;
        while offset < m.len() {
            before(deadline)?;
            let count = (m.len() - offset).min(buffer.len() as u64) as usize;
            composer.read_exact_at(&mut buffer[..count], offset)?;
            hash.update(&buffer[..count]);
            offset += count as u64;
        }
        check(
            Seal::of(&composer)? == original,
            "Composer changed while binding full body",
        )?;
        let value = TaskControlEndpoint {
            owner: child.identity,
            root: Node::of(&root)?,
            socket_seal: Seal::of(&socket)?,
            socket_inode_selinux_context: mac_observation::InodeSelinuxContext::acquire(
                &socket, deadline,
            )?,
            socket,
            composer,
            composer_seal: original,
            composer_sha256: format!("{:x}", hash.finalize()),
            listener_pidfd: None,
            connection_peer_security: None,
        };
        value.revalidate(self, deadline)?;
        Ok(value)
    }
}

impl TaskControlEndpoint {
    pub(crate) fn socket_inode(&self) -> &File {
        &self.socket
    }

    pub(crate) fn revalidate(
        &self,
        authority: &ApplicationAuthority<'_>,
        deadline: Instant,
    ) -> Result<()> {
        before(deadline)?;
        authority.revalidate()?;
        let child = authority.child()?;
        let root = held_child_root(child)?;
        check(
            child.identity == self.owner
                && Node::of(&root)? == self.root
                && Seal::of(&self.socket)? == self.socket_seal
                && Seal::of(&endpoint_socket(&root)?)? == self.socket_seal
                && Seal::of(&self.composer)? == self.composer_seal
                && Seal::of(&composer_file(&root)?)? == self.composer_seal,
            "task-control original endpoint or Composer inode changed",
        )?;
        readonly_image(&self.composer)?;
        self.socket_inode_selinux_context
            .revalidate(&self.socket, deadline)?;
        if let Some(pidfd) = &self.listener_pidfd {
            check(
                !pidfd_exited(pidfd)?,
                "task-control original listener exited",
            )?;
            let info = pidfd_info(pidfd.as_raw_fd())?;
            check(
                info.pid == child.identity.pid && info.tgid == info.pid,
                "task-control listener generation changed",
            )?;
            child.namespaces.verify(pidfd)?;
        }
        before(deadline)
    }

    pub(crate) fn bind_listener(
        &mut self,
        authority: &ApplicationAuthority<'_>,
        socket: &File,
        deadline: Instant,
    ) -> Result<()> {
        self.revalidate(authority, deadline)?;
        check(
            self.listener_pidfd.is_none() && self.connection_peer_security.is_none(),
            "task-control connection cannot be rebound",
        )?;
        let owned: OwnedFd = socket.try_clone()?.into();
        let pidfd = listener_pidfd(&owned)?;
        let credentials = super::super::activation_peer::peer_credentials(&owned)?;
        let info = pidfd_info(pidfd.as_raw_fd())?;
        let child = authority.child()?;
        check(
            credentials.pid == child.identity.pid as libc::pid_t
                && info.pid == child.identity.pid
                && info.tgid == info.pid
                && !pidfd_exited(&pidfd)?,
            "task-control listener is not this owned init",
        )?;
        require_pidfd_creds(&info, child.uids.start, child.gids.start)?;
        check(
            credentials.uid == child.uids.start && credentials.gid == child.gids.start,
            "task-control listener credentials differ",
        )?;
        child.namespaces.verify(&pidfd)?;
        // SO_PEERSEC belongs to this connection. Do not infer it from the
        // init listener PID, the pathname label, or a later Composer message.
        let connection_peer_security =
            mac_observation::ConnectionPeerSecurity::acquire(socket, deadline)?;
        self.listener_pidfd = Some(pidfd);
        self.connection_peer_security = Some(connection_peer_security);
        self.revalidate_connection(authority, socket, deadline)
    }

    pub(crate) fn revalidate_connection(
        &self,
        authority: &ApplicationAuthority<'_>,
        socket: &File,
        deadline: Instant,
    ) -> Result<()> {
        self.revalidate(authority, deadline)?;
        check(
            self.listener_pidfd.is_some(),
            "task-control original listener binding absent",
        )?;
        self.connection_peer_security
            .as_ref()
            .ok_or(NamespaceError::Rejected(
                "task-control peer security observation absent",
            ))?
            .revalidate(socket, deadline)?;
        authority.revalidate()?;
        before(deadline)
    }

    pub(crate) fn bind_sender(
        &self,
        authority: &ApplicationAuthority<'_>,
        pidfd: OwnedFd,
        credentials: libc::ucred,
        deadline: Instant,
    ) -> Result<TaskControlPeer> {
        self.revalidate(authority, deadline)?;
        check(
            self.listener_pidfd.is_some() && !pidfd_exited(&pidfd)?,
            "task-control sender is not live",
        )?;
        let child = authority.child()?;
        let info = pidfd_info(pidfd.as_raw_fd())?;
        check(
            credentials.pid > 1
                && info.pid == credentials.pid as u32
                && info.pid == info.tgid
                && info.pid != child.identity.pid,
            "task-control message PIDFD and credentials differ",
        )?;
        let uid = child
            .uids
            .start
            .checked_add(1000)
            .ok_or(NamespaceError::Rejected("Composer UID overflow"))?;
        let gid = child
            .gids
            .start
            .checked_add(1000)
            .ok_or(NamespaceError::Rejected("Composer GID overflow"))?;
        check(
            credentials.uid == uid && credentials.gid == gid,
            "Composer message credentials differ",
        )?;
        require_pidfd_creds(&info, uid, gid)?;
        child.namespaces.verify(&pidfd)?;
        let directory = open_proc_at(
            &child.proc_root,
            &info.pid.to_string(),
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        let identity = read_identity(&directory, info.pid)?;
        check(
            identity.parent == info.ppid
                && framework_namespace(&directory, child)?
                && Seal::of(&process_executable(&directory)?)? == self.composer_seal,
            "task-control sender is not the same-tree selected Composer",
        )?;
        let value = TaskControlPeer {
            pidfd,
            node: Node::of(&directory)?,
            identity,
            process_selinux_context: context(&directory)?,
            directory,
        };
        value.revalidate(authority, self, deadline)?;
        Ok(value)
    }

    pub(crate) fn composer_sha256(&self) -> &str {
        &self.composer_sha256
    }
}

impl TaskControlPeer {
    pub(crate) fn revalidate(
        &self,
        authority: &ApplicationAuthority<'_>,
        endpoint: &TaskControlEndpoint,
        deadline: Instant,
    ) -> Result<()> {
        endpoint.revalidate(authority, deadline)?;
        let child = authority.child()?;
        check(
            !pidfd_exited(&self.pidfd)?,
            "original task-control Composer exited",
        )?;
        let info = pidfd_info(self.pidfd.as_raw_fd())?;
        let uid = child
            .uids
            .start
            .checked_add(1000)
            .ok_or(NamespaceError::Rejected("Composer UID overflow"))?;
        let gid = child
            .gids
            .start
            .checked_add(1000)
            .ok_or(NamespaceError::Rejected("Composer GID overflow"))?;
        require_pidfd_creds(&info, uid, gid)?;
        check(
            info.pid == self.identity.pid
                && info.pid == info.tgid
                && info.ppid == self.identity.parent
                && Node::of(&self.directory)? == self.node
                && read_identity(&self.directory, info.pid)? == self.identity
                && Node::of(&open_proc_at(
                    &child.proc_root,
                    &info.pid.to_string(),
                    libc::O_RDONLY | libc::O_DIRECTORY,
                )?)? == self.node
                && framework_namespace(&self.directory, child)?
                && Seal::of(&process_executable(&self.directory)?)? == endpoint.composer_seal
                && context(&self.directory)? == self.process_selinux_context,
            "original task-control Composer changed",
        )?;
        child.namespaces.verify(&self.pidfd)?;
        before(deadline)
    }

    pub(crate) fn same_generation(&self, other: &Self) -> bool {
        self.identity == other.identity
            && self.node == other.node
            && self.process_selinux_context == other.process_selinux_context
    }
}
