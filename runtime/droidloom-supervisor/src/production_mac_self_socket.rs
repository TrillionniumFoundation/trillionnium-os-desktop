//! A fixed broker/loader socket pair under an explicitly AA-first host route.
//! SO_PEERSEC is observed as AppArmor here. Typed SELinux CURRENT independently
//! proves the original creator; it is never substituted for an Android peer SID.
//! Both sockets and their actual kernel peer PIDFDs remain in this owner.
use super::*;

const PIDFS_MAGIC: u64 = 0x5049_4446;
const PIDFD_GET_INFO: libc::c_ulong = 0xc048_ff0b;
const SO_PEERPIDFD: i32 = 77;
#[repr(C)]
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct Info {
    mask: u64,
    cgroup: u64,
    pid: u32,
    tgid: u32,
    ppid: u32,
    ruid: u32,
    rgid: u32,
    euid: u32,
    egid: u32,
    suid: u32,
    sgid: u32,
    fsuid: u32,
    fsgid: u32,
    exit_code: i32,
    coredump: u32,
    spare: u32,
}
const _: () = assert!(std::mem::size_of::<Info>() == 72);
#[derive(Clone, Copy)]
enum Role {
    Broker,
    Loader,
}
impl Role {
    fn selinux(self) -> &'static str {
        match self {
            Self::Broker => BROKER,
            Self::Loader => LOADER,
        }
    }
    fn apparmor(self) -> &'static [u8] {
        match self {
            Self::Broker => AA_BROKER,
            Self::Loader => AA_LOADER,
        }
    }
}
fn check_creator(
    loaded: &LoadedPolicyWitness,
    selection: &ProductionSelection,
    role: Role,
) -> Result<()> {
    loaded.revalidate(selection)?;
    require(
        context_matches(&self_attr::selinux_current()?, role.selinux()),
        "typed original socket creator SELinux role differs",
    )?;
    require(
        proc_attr(&loaded.own_proc, true)? == role.apparmor(),
        "original socket creator AppArmor role differs",
    )?;
    require(
        unsafe { libc::syscall(libc::SYS_gettid) } == loaded.tid as libc::c_long,
        "socket creator original calling thread",
    )?;
    loaded.stable_epoch()
}
fn socket_int(fd: BorrowedFd<'_>, key: i32, expected: i32) -> Result<()> {
    let mut value = 0_i32;
    let mut length = std::mem::size_of_val(&value) as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            fd.as_raw_fd(),
            libc::SOL_SOCKET,
            key,
            (&mut value as *mut i32).cast(),
            &mut length,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    require(
        length as usize == std::mem::size_of_val(&value) && value == expected,
        "fixed actual self socket option",
    )
}
fn cookie(fd: BorrowedFd<'_>) -> Result<u64> {
    let mut value = 0_u64;
    let mut length = std::mem::size_of_val(&value) as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            fd.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_COOKIE,
            (&mut value as *mut u64).cast(),
            &mut length,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    require(
        length as usize == std::mem::size_of_val(&value) && value != 0,
        "actual self socket cookie",
    )?;
    Ok(value)
}
fn peer_pidfd(fd: BorrowedFd<'_>) -> Result<File> {
    let mut raw = -1_i32;
    let mut length = std::mem::size_of_val(&raw) as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            fd.as_raw_fd(),
            libc::SOL_SOCKET,
            SO_PEERPIDFD,
            (&mut raw as *mut i32).cast(),
            &mut length,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    require(raw >= 0, "actual self socket peer PIDFD is absent")?;
    let file = unsafe { File::from_raw_fd(raw) };
    require(
        length as usize == std::mem::size_of_val(&raw),
        "exact actual peer PIDFD result size",
    )?;
    let flags = unsafe { libc::fcntl(raw, libc::F_GETFD) };
    if flags < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        flags & libc::FD_CLOEXEC != 0,
        "actual peer PIDFD must be CLOEXEC",
    )?;
    Ok(file)
}
fn alive(fd: BorrowedFd<'_>) -> Result<()> {
    let mut p = libc::pollfd {
        fd: fd.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    let rc = unsafe { libc::poll(&mut p, 1, 0) };
    if rc < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        rc == 0 && p.revents == 0,
        "original self socket peer must remain live",
    )
}
fn info(fd: BorrowedFd<'_>, pid: u32) -> Result<Info> {
    alive(fd)?;
    let before = descriptor_identity(fd)?;
    let mut fs: libc::statfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstatfs(fd.as_raw_fd(), &mut fs) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        fs.f_type as u64 == PIDFS_MAGIC,
        "actual self peer must be a kernel PIDFD",
    )?;
    let mut value: Info = unsafe { std::mem::zeroed() };
    value.mask = 3;
    if unsafe { libc::ioctl(fd.as_raw_fd(), PIDFD_GET_INFO, &mut value) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        value.mask & 3 == 3
            && value.mask & !7 == 0
            && value.pid == pid
            && value.tgid == pid
            && value.ruid == 0
            && value.euid == 0
            && value.suid == 0
            && value.fsuid == 0
            && value.rgid == 0
            && value.egid == 0
            && value.sgid == 0
            && value.fsgid == 0
            && value.exit_code == 0
            && value.coredump == 0
            && value.spare == 0,
        "actual self socket peer is not the original root creator process",
    )?;
    require(
        descriptor_identity(fd)? == before,
        "self peer PIDFD identity changed",
    )?;
    alive(fd)?;
    Ok(value)
}
fn actual_peer(fd: BorrowedFd<'_>, held: &File, pid: u32, role: Role) -> Result<()> {
    let mut credentials: libc::ucred = unsafe { std::mem::zeroed() };
    let mut length = std::mem::size_of_val(&credentials) as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            fd.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERCRED,
            (&mut credentials as *mut libc::ucred).cast(),
            &mut length,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    require(
        length as usize == std::mem::size_of_val(&credentials)
            && credentials.pid > 0
            && credentials.pid as u32 == pid
            && credentials.uid == 0
            && credentials.gid == 0,
        "actual self socket peer credentials differ",
    )?;
    let fresh = peer_pidfd(fd)?;
    require(
        descriptor_identity(fresh.as_fd())? == descriptor_identity(held.as_fd())?,
        "self socket peer changed from its original PIDFD",
    )?;
    require(
        info(fresh.as_fd(), pid)? == info(held.as_fd(), pid)?,
        "self socket peer process changed",
    )?;
    // Final 6.18 AppArmor getpeersec_stream deliberately excludes NUL and LF.
    let expected = role
        .apparmor()
        .strip_suffix(b"\n")
        .ok_or(MacError::Rejected("fixed AppArmor context terminator"))?;
    require(
        actual_socket_security(fd)? == expected,
        "actual AA-first self socket peer label differs",
    )
}
pub(super) struct SelfSocketWitness {
    provider: ProviderBinding,
    role: Role,
    pid: u32,
    sockets: [File; 2],
    socket_nodes: [DescriptorIdentity; 2],
    cookies: [u64; 2],
    peers: [File; 2],
}
impl SelfSocketWitness {
    fn create(
        loaded: &LoadedPolicyWitness,
        selection: &ProductionSelection,
        role: Role,
    ) -> Result<Self> {
        require(
            loaded.declaration.scoped_contexts()?,
            "self socket route requires the explicit scoped-context contract",
        )?;
        check_creator(loaded, selection, role)?;
        let pid = unsafe { libc::getpid() };
        require(pid > 0, "original self socket process")?;
        let mut raw = [-1_i32; 2];
        if unsafe {
            libc::socketpair(
                libc::AF_UNIX,
                libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
                0,
                raw.as_mut_ptr(),
            )
        } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
        let sockets = unsafe { [File::from_raw_fd(raw[0]), File::from_raw_fd(raw[1])] };
        let peers = [
            peer_pidfd(sockets[0].as_fd())?,
            peer_pidfd(sockets[1].as_fd())?,
        ];
        let socket_nodes = [
            descriptor_identity(sockets[0].as_fd())?,
            descriptor_identity(sockets[1].as_fd())?,
        ];
        let cookies = [cookie(sockets[0].as_fd())?, cookie(sockets[1].as_fd())?];
        require(
            cookies[0] != cookies[1] && socket_nodes[0] != socket_nodes[1],
            "distinct original self socket endpoints",
        )?;
        let value = Self {
            provider: loaded.binding(),
            role,
            pid: pid as u32,
            sockets,
            socket_nodes,
            cookies,
            peers,
        };
        value.revalidate(loaded, selection)?;
        Ok(value)
    }
    pub(super) fn broker(
        loaded: &LoadedPolicyWitness,
        selection: &ProductionSelection,
    ) -> Result<Self> {
        Self::create(loaded, selection, Role::Broker)
    }
    pub(super) fn loader(
        loaded: &LoadedPolicyWitness,
        selection: &ProductionSelection,
    ) -> Result<Self> {
        Self::create(loaded, selection, Role::Loader)
    }
    pub(super) fn revalidate(
        &self,
        loaded: &LoadedPolicyWitness,
        selection: &ProductionSelection,
    ) -> Result<()> {
        check_creator(loaded, selection, self.role)?;
        require(
            loaded.binding() == self.provider && unsafe { libc::getpid() } as u32 == self.pid,
            "self socket belongs to another original MAC provider",
        )?;
        for i in 0..2 {
            let fd = self.sockets[i].as_fd();
            require(
                descriptor_identity(fd)? == self.socket_nodes[i]
                    && self.socket_nodes[i].kind == libc::S_IFSOCK
                    && cookie(fd)? == self.cookies[i],
                "original self socket identity changed",
            )?;
            for (key, value) in [
                (libc::SO_DOMAIN, libc::AF_UNIX),
                (libc::SO_TYPE, libc::SOCK_SEQPACKET),
                (libc::SO_PROTOCOL, 0),
                (libc::SO_ACCEPTCONN, 0),
            ] {
                socket_int(fd, key, value)?;
            }
            let flags = unsafe { libc::fcntl(fd.as_raw_fd(), libc::F_GETFD) };
            let status = unsafe { libc::fcntl(fd.as_raw_fd(), libc::F_GETFL) };
            if flags < 0 || status < 0 {
                return Err(io::Error::last_os_error().into());
            }
            require(
                flags & libc::FD_CLOEXEC != 0 && status & libc::O_NONBLOCK != 0,
                "original self socket descriptor flags",
            )?;
            actual_peer(fd, &self.peers[i], self.pid, self.role)?;
        }
        check_creator(loaded, selection, self.role)
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn a_regular_file_cannot_provide_peer_pidfd_or_socket_identity() {
        let file = tempfile::tempfile().unwrap();
        assert!(peer_pidfd(file.as_fd()).is_err());
        assert!(cookie(file.as_fd()).is_err());
        assert!(socket_int(file.as_fd(), libc::SO_DOMAIN, libc::AF_UNIX).is_err());
        assert!(info(file.as_fd(), unsafe { libc::getpid() } as u32).is_err());
    }
    #[test]
    fn actual_socket_pair_cookies_and_peer_pidfds_are_kernel_objects() {
        let mut raw = [-1_i32; 2];
        assert_eq!(
            unsafe {
                libc::socketpair(
                    libc::AF_UNIX,
                    libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC,
                    0,
                    raw.as_mut_ptr(),
                )
            },
            0
        );
        let pair = unsafe { [File::from_raw_fd(raw[0]), File::from_raw_fd(raw[1])] };
        assert_ne!(
            cookie(pair[0].as_fd()).unwrap(),
            cookie(pair[1].as_fd()).unwrap()
        );
        let first = peer_pidfd(pair[0].as_fd()).unwrap();
        let second = peer_pidfd(pair[1].as_fd()).unwrap();
        assert_eq!(
            descriptor_identity(first.as_fd()).unwrap(),
            descriptor_identity(second.as_fd()).unwrap()
        );
        let mut fs: libc::statfs = unsafe { std::mem::zeroed() };
        assert_eq!(unsafe { libc::fstatfs(first.as_raw_fd(), &mut fs) }, 0);
        assert_eq!(fs.f_type as u64, PIDFS_MAGIC);
        // No LoadedPolicyWitness or runtime role is fabricated by this real-UAPI control.
    }
}
