//! Task-control custody from the real early owner. Only the authenticated
//! metadata helper reads Android procfs. Listener init and per-message Composer
//! retain separate kernel PIDFDs; neither PID nor a saved receipt selects a target.
use super::*;
use sha2::{Digest, Sha256};
use std::os::unix::fs::FileExt;
#[path = "production_namespace_task_control_mac.rs"]
mod mac_observation;

const COMPOSER: &CStr = c"android.hardware.graphics.composer3-service.droidloom";
#[derive(Clone, Copy, Eq, PartialEq, Debug)]
struct Node {
    device: u64,
    inode: u64,
}
impl Node {
    fn of(file: &File) -> Result<Self> {
        let (d, i) = identity(file)?;
        Ok(Self {
            device: d,
            inode: i,
        })
    }
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
fn check(value: bool, why: &'static str) -> Result<()> {
    require(value, why)
}
fn before(deadline: Instant) -> Result<()> {
    retirement_checked(Ok(()))?;
    require(
        Instant::now() < deadline,
        "early task-control absolute deadline",
    )
}
fn socket_file(root: &File) -> Result<File> {
    let dev = open(root, c"dev", true)?;
    let sockets = open(&dev, c"socket", true)?;
    let raw = unsafe {
        libc::openat(
            sockets.as_raw_fd(),
            c"droidloom-task-control".as_ptr(),
            libc::O_PATH | libc::O_NOFOLLOW | libc::O_CLOEXEC,
        )
    };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(unsafe { File::from_raw_fd(raw) })
}
fn composer_file(root: &File) -> Result<File> {
    let vendor = open(root, c"vendor", true)?;
    let bin = open(&vendor, c"bin", true)?;
    let hw = open(&bin, c"hw", true)?;
    Ok(open(&hw, COMPOSER, false)?)
}
fn readonly_image(file: &File) -> Result<()> {
    let mut fs: libc::statfs = unsafe { std::mem::zeroed() };
    let mut flags: libc::statvfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstatfs(file.as_raw_fd(), &mut fs) } != 0
        || unsafe { libc::fstatvfs(file.as_raw_fd(), &mut flags) } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    require(
        [0xef53, 0xe0f5_e1e2_u32 as libc::c_long].contains(&fs.f_type)
            && flags.f_flag & libc::ST_RDONLY != 0,
        "early Composer is not in the original readonly image",
    )
}
fn listener(socket: &File) -> Result<(OwnedFd, libc::ucred)> {
    let mut raw = -1_i32;
    let mut size = std::mem::size_of_val(&raw) as libc::socklen_t;
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
    require(raw >= 0, "kernel early listener PIDFD absent")?;
    let fd = unsafe { OwnedFd::from_raw_fd(raw) };
    let flags = unsafe { libc::fcntl(fd.as_raw_fd(), libc::F_GETFD) };
    require(
        size as usize == std::mem::size_of_val(&raw) && flags >= 0 && flags & libc::FD_CLOEXEC != 0,
        "early listener PIDFD shape differs",
    )?;
    let mut credentials: libc::ucred = unsafe { std::mem::zeroed() };
    size = std::mem::size_of_val(&credentials) as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            socket.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERCRED,
            (&mut credentials as *mut libc::ucred).cast(),
            &mut size,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    require(
        size as usize == std::mem::size_of_val(&credentials),
        "early listener credentials size differs",
    )?;
    Ok((fd, credentials))
}

pub(crate) struct EarlyTaskControlEndpoint {
    owner: Process,
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
pub(crate) struct EarlyTaskControlPeer {
    pidfd: OwnedFd,
    observed: MetadataObservation,
    process: Process,
}
impl EarlyApplicationAuthority<'_> {
    pub(crate) fn task_control_endpoint(
        &self,
        deadline: Instant,
    ) -> Result<EarlyTaskControlEndpoint> {
        before(deadline)?;
        self.ready()?;
        let (uid, gid) = self.mapped_root()?;
        let socket = socket_file(self.root)?;
        let m = socket.metadata()?;
        let (_, system_uid, system_gid) = role_ids(&self.base, MetadataRole::Composer)?;
        require(
            m.mode() == libc::S_IFSOCK | 0o660
                && m.nlink() == 1
                && m.uid() == system_uid
                && m.gid() == system_gid,
            "early fixed init task-control socket identity differs",
        )?;
        let composer = composer_file(self.root)?;
        let seal = Seal::of(&composer)?;
        let m = composer.metadata()?;
        require(
            m.is_file()
                && m.nlink() == 1
                && (64..=64 * 1024 * 1024).contains(&m.len())
                && m.uid() == uid
                && m.gid() == gid
                && m.mode() & 0o6022 == 0
                && m.mode() & 0o111 != 0,
            "early selected Composer executable differs",
        )?;
        readonly_image(&composer)?;
        let mut header = [0_u8; 64];
        composer.read_exact_at(&mut header, 0)?;
        require(
            &header[..7] == b"\x7fELF\x02\x01\x01"
                && u16::from_le_bytes([header[18], header[19]]) == 62,
            "early Composer is not the selected x86_64 ELF",
        )?;
        let mut hash = Sha256::new();
        let mut buffer = [0_u8; 65536];
        let mut offset = 0;
        while offset < m.len() {
            before(deadline)?;
            let count = (m.len() - offset).min(buffer.len() as u64) as usize;
            composer.read_exact_at(&mut buffer[..count], offset)?;
            hash.update(&buffer[..count]);
            offset += count as u64;
        }
        require(
            Seal::of(&composer)? == seal,
            "early Composer changed during body binding",
        )?;
        let value = EarlyTaskControlEndpoint {
            owner: self.init,
            root: Node::of(self.root)?,
            socket_seal: Seal::of(&socket)?,
            socket_inode_selinux_context: mac_observation::InodeSelinuxContext::acquire(
                &socket, deadline,
            )?,
            socket,
            composer,
            composer_seal: seal,
            composer_sha256: format!("{:x}", hash.finalize()),
            listener_pidfd: None,
            connection_peer_security: None,
        };
        value.revalidate(self, deadline)?;
        Ok(value)
    }
}
impl EarlyTaskControlEndpoint {
    pub(crate) fn socket_inode(&self) -> &File {
        &self.socket
    }
    pub(crate) fn composer_sha256(&self) -> &str {
        &self.composer_sha256
    }
    fn revalidate(
        &self,
        authority: &EarlyApplicationAuthority<'_>,
        deadline: Instant,
    ) -> Result<()> {
        before(deadline)?;
        authority.ready()?;
        require(
            authority.init == self.owner
                && Node::of(authority.root)? == self.root
                && Seal::of(&self.socket)? == self.socket_seal
                && Seal::of(&socket_file(authority.root)?)? == self.socket_seal
                && Seal::of(&self.composer)? == self.composer_seal
                && Seal::of(&composer_file(authority.root)?)? == self.composer_seal,
            "early task-control original endpoint or Composer inode changed",
        )?;
        readonly_image(&self.composer)?;
        self.socket_inode_selinux_context
            .revalidate(&self.socket, deadline)?;
        if let Some(fd) = &self.listener_pidfd {
            let file = File::from(fd.try_clone()?);
            require(
                identity(&file)? == identity(authority.base.board().pidfd())?,
                "early task-control listener is another init lifetime",
            )?;
            let (uid, gid) = authority.mapped_root()?;
            native_process(&file, self.owner, uid, gid)?;
        }
        before(deadline)
    }
    pub(crate) fn bind_listener(
        &mut self,
        authority: &EarlyApplicationAuthority<'_>,
        socket: &File,
        deadline: Instant,
    ) -> Result<()> {
        self.revalidate(authority, deadline)?;
        require(
            self.listener_pidfd.is_none() && self.connection_peer_security.is_none(),
            "early task-control connection cannot be rebound",
        )?;
        let (fd, credentials) = listener(socket)?;
        let file = File::from(fd.try_clone()?);
        let (uid, gid) = authority.mapped_root()?;
        native_process(&file, self.owner, uid, gid)?;
        require(
            identity(&file)? == identity(authority.base.board().pidfd())?
                && credentials.pid == self.owner.pid as i32
                && credentials.uid == uid
                && credentials.gid == gid,
            "early task-control listener is not the original init PIDFD",
        )?;
        let security = mac_observation::ConnectionPeerSecurity::acquire(socket, deadline)?;
        self.listener_pidfd = Some(fd);
        self.connection_peer_security = Some(security);
        self.revalidate_connection(authority, socket, deadline)
    }
    pub(crate) fn revalidate_connection(
        &self,
        authority: &EarlyApplicationAuthority<'_>,
        socket: &File,
        deadline: Instant,
    ) -> Result<()> {
        self.revalidate(authority, deadline)?;
        let held = self
            .listener_pidfd
            .as_ref()
            .ok_or(NamespaceError::Rejected("early listener custody absent"))?;
        let (current, credentials) = listener(socket)?;
        require(
            identity(&File::from(current))? == identity(&File::from(held.try_clone()?))?
                && credentials.pid == self.owner.pid as i32,
            "early connected socket changed its original listener",
        )?;
        self.connection_peer_security
            .as_ref()
            .ok_or(NamespaceError::Rejected(
                "early peer security observation absent",
            ))?
            .revalidate(socket, deadline)?;
        before(deadline)
    }
    fn sample_composer(
        &self,
        authority: &EarlyApplicationAuthority<'_>,
        target: &File,
        deadline: Instant,
    ) -> Result<(MetadataObservation, Process)> {
        before(deadline)?;
        let native = info(target.as_fd(), true)?;
        let (_, uid, gid) = role_ids(&authority.base, MetadataRole::Composer)?;
        require(
            native.pid > 1
                && native.tgid == native.pid
                && native.pid != self.owner.pid
                && native.ppid == self.owner.pid,
            "early Composer PIDFD is not the original init's direct child",
        )?;
        let observed = crate::production_application::observe_metadata(
            &authority.base.board().observer_proc().map_err(external)?,
            MetadataRole::Composer,
            target,
            authority.base.user_namespace(),
            deadline,
        )
        .map_err(external)?;
        let process = verify_sample(
            &authority.base,
            authority.root,
            &observed,
            target,
            MetadataRole::Composer,
            native.pid,
        )?;
        require(
            process.parent == self.owner.pid
                && process.start > self.owner.start
                && Seal::of(&observed.executable)? == self.composer_seal,
            "early reply sender is not the original selected Composer ELF",
        )?;
        native_process(target, process, uid, gid)?;
        before(deadline)?;
        Ok((observed, process))
    }
    pub(crate) fn bind_sender(
        &self,
        authority: &EarlyApplicationAuthority<'_>,
        pidfd: OwnedFd,
        credentials: libc::ucred,
        deadline: Instant,
    ) -> Result<EarlyTaskControlPeer> {
        self.revalidate(authority, deadline)?;
        require(
            self.listener_pidfd.is_some(),
            "early sender has no bound listener",
        )?;
        let target = File::from(pidfd.try_clone()?);
        let native = info(target.as_fd(), true)?;
        let (_, uid, gid) = role_ids(&authority.base, MetadataRole::Composer)?;
        require(
            credentials.pid > 1
                && native.pid == credentials.pid as u32
                && credentials.uid == uid
                && credentials.gid == gid,
            "early Composer message PIDFD and credentials differ",
        )?;
        let (observed, process) = self.sample_composer(authority, &target, deadline)?;
        let value = EarlyTaskControlPeer {
            pidfd,
            observed,
            process,
        };
        value.revalidate(authority, self, deadline)?;
        Ok(value)
    }
}
impl EarlyTaskControlPeer {
    pub(crate) fn revalidate(
        &self,
        authority: &EarlyApplicationAuthority<'_>,
        endpoint: &EarlyTaskControlEndpoint,
        deadline: Instant,
    ) -> Result<()> {
        endpoint.revalidate(authority, deadline)?;
        let target = File::from(self.pidfd.try_clone()?);
        let (observed, process) = endpoint.sample_composer(authority, &target, deadline)?;
        require(
            process == self.process,
            "early Composer process birth changed",
        )?;
        same_sample(&self.observed, &observed)?;
        before(deadline)
    }
    pub(crate) fn same_generation(&self, other: &Self) -> bool {
        self.process == other.process
            && self.observed.host.proc_identity() == other.observed.host.proc_identity()
            && self.observed.selinux == other.observed.selinux
            && self.observed.apparmor == other.observed.apparmor
            && self
                .pidfd
                .try_clone()
                .ok()
                .and_then(|fd| File::from(fd).metadata().ok())
                .zip(
                    other
                        .pidfd
                        .try_clone()
                        .ok()
                        .and_then(|fd| File::from(fd).metadata().ok()),
                )
                .is_some_and(|(a, b)| a.dev() == b.dev() && a.ino() == b.ino())
    }
}
