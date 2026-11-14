//! Fixed activation socket on the original fresh private DEV.
//!
//! Create before idmap while the new filesystem belongs to initial root;
//! map that same inode to the admitted guest. No chown, caller pathname,
//! existing-file replacement or guest descriptor import is permitted.

use super::*;
use std::os::fd::OwnedFd;
use std::time::Instant;

const BASENAME: &CStr = c"droidloom-linkerconfig";

fn socket_option(fd: BorrowedFd<'_>, key: i32, expected: i32) -> Result<()> {
    let mut value = 0_i32;
    let mut bytes = std::mem::size_of_val(&value) as libc::socklen_t;
    zero(unsafe {
        libc::getsockopt(
            fd.as_raw_fd(),
            libc::SOL_SOCKET,
            key,
            (&mut value as *mut i32).cast(),
            &mut bytes,
        )
    } as _)?;
    need(
        bytes as usize == std::mem::size_of_val(&value) && value == expected,
        "actual activation socket option differs",
    )
}

fn socket_cookie(fd: BorrowedFd<'_>) -> Result<u64> {
    let mut value = 0_u64;
    let mut bytes = std::mem::size_of_val(&value) as libc::socklen_t;
    zero(unsafe {
        libc::getsockopt(
            fd.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_COOKIE,
            (&mut value as *mut u64).cast(),
            &mut bytes,
        )
    } as _)?;
    need(
        bytes as usize == std::mem::size_of_val(&value) && value != 0,
        "actual listener kernel cookie is absent",
    )?;
    Ok(value)
}

fn private_flags(fd: BorrowedFd<'_>) -> Result<()> {
    let fdflags = unsafe { libc::fcntl(fd.as_raw_fd(), libc::F_GETFD) };
    if fdflags < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let flags = unsafe { libc::fcntl(fd.as_raw_fd(), libc::F_GETFL) };
    if flags < 0 {
        return Err(io::Error::last_os_error().into());
    }
    need(
        fdflags & libc::FD_CLOEXEC != 0 && flags & libc::O_NONBLOCK != 0,
        "activation control must be CLOEXEC and nonblocking",
    )
}

fn pass_credentials(fd: BorrowedFd<'_>) -> Result<()> {
    let one = 1_i32;
    zero(unsafe {
        libc::setsockopt(
            fd.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PASSCRED,
            (&one as *const i32).cast(),
            std::mem::size_of_val(&one) as _,
        )
    } as _)
}

/// Retained with the original detached tmpfs in DeviceResources.
#[derive(Debug)]
pub(super) struct ActivationListener {
    root: (u64, u64),
    directory: File,
    directory_node: (u64, u64),
    node: File,
    node_identity: DeviceIdentity,
    server: OwnedFd,
    cookie: u64,
}

impl ActivationListener {
    pub(super) fn bind_new(root: &File) -> Result<Self> {
        require_initial_broker()?;
        require_detached(root)?;
        verify_root(root, 0, 0)?;
        let root_node = node(root)?;
        let mut expected: Vec<_> = DEVICES
            .iter()
            .map(|item| item.name.to_bytes().to_vec())
            .collect();
        expected.sort();
        need(
            directory_names(root)? == expected,
            "activation listener requires the original fresh seven-node DEV",
        )?;
        zero(unsafe { libc::mkdirat(root.as_raw_fd(), c"socket".as_ptr(), 0o700) } as _)?;
        let directory = open_at(root, c"socket", libc::O_RDONLY | libc::O_DIRECTORY)?;
        let dir_node = node(&directory)?;
        let m = directory.metadata()?;
        need(
            m.dev() == root_node.0 && m.is_dir() && m.uid() == 0 && m.gid() == 0,
            "new private socket directory identity",
        )?;
        zero(unsafe { libc::fchmod(directory.as_raw_fd(), 0o755) } as _)?;
        need(
            directory_names_bounded(&directory, 1)?.is_empty(),
            "new socket directory must be empty",
        )?;
        let (server, named) = bind_socket(&directory)?;
        let cookie = socket_cookie(server.as_fd())?;
        let value = Self {
            root: root_node,
            directory_node: dir_node,
            directory,
            node_identity: identity(&named.metadata()?),
            node: named,
            server,
            cookie,
        };
        value.verify_inode(root, 0, 0)?;
        Ok(value)
    }

    fn verify_inode(&self, root: &File, uid: u32, gid: u32) -> Result<()> {
        need(
            node(root)? == self.root && node(&self.directory)? == self.directory_node,
            "activation listener private directory changed",
        )?;
        let named_dir = open_at(root, c"socket", libc::O_RDONLY | libc::O_DIRECTORY)?;
        need(
            node(&named_dir)? == self.directory_node,
            "activation socket directory was replaced",
        )?;
        let d = self.directory.metadata()?;
        need(
            d.dev() == self.root.0
                && d.mode() == libc::S_IFDIR | 0o755
                && d.uid() == uid
                && d.gid() == gid,
            "actual mapped socket directory credentials or mode differ",
        )?;
        let named = open_at(&self.directory, BASENAME, libc::O_PATH)?;
        for file in [&self.node, &named] {
            let m = file.metadata()?;
            need(
                identity(&m) == self.node_identity
                    && m.dev() == self.root.0
                    && m.mode() == libc::S_IFSOCK | 0o600
                    && m.nlink() == 1
                    && m.uid() == uid
                    && m.gid() == gid,
                "original mapped listener inode changed or was replaced",
            )?;
        }
        private_flags(self.server.as_fd())?;
        for (key, expected) in [
            (libc::SO_DOMAIN, libc::AF_UNIX),
            (libc::SO_TYPE, libc::SOCK_SEQPACKET),
            (libc::SO_PASSCRED, 1),
            (libc::SO_ACCEPTCONN, 1),
        ] {
            socket_option(self.server.as_fd(), key, expected)?;
        }
        need(
            socket_cookie(self.server.as_fd())? == self.cookie,
            "original listening socket kernel identity changed",
        )
    }

    pub(super) fn verify_complete(
        &self,
        root: &File,
        uid: u32,
        gid: u32,
        devices: &[DeviceIdentity],
    ) -> Result<()> {
        verify_root(root, uid, gid)?;
        verify_device_nodes(root, uid, gid, devices)?;
        let mut expected: Vec<_> = DEVICES
            .iter()
            .map(|item| item.name.to_bytes().to_vec())
            .collect();
        expected.push(b"socket".to_vec());
        expected.sort();
        need(
            directory_names_bounded(root, DEVICES.len() + 1)? == expected,
            "only the declared eight prepared DEV entries are allowed",
        )?;
        need(
            directory_names_bounded(&self.directory, 1)? == [BASENAME.to_bytes().to_vec()],
            "only the fixed prepared activation socket is allowed",
        )?;
        self.verify_inode(root, uid, gid)
    }
}

/// Kernel transport primitive only. Production calls it solely after the
/// fresh private-DEV checks above; it cannot issue a device or MAC witness.
fn bind_socket(directory: &File) -> Result<(OwnedFd, File)> {
    let raw = unsafe {
        libc::socket(
            libc::AF_UNIX,
            libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
            0,
        )
    };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let server = unsafe { OwnedFd::from_raw_fd(raw) };
    pass_credentials(server.as_fd())?;
    // Only this process's actually held directory FD is used as an alias.
    let path = format!(
        "/proc/self/fd/{}/droidloom-linkerconfig",
        directory.as_raw_fd()
    );
    let mut address: libc::sockaddr_un = unsafe { std::mem::zeroed() };
    need(
        path.len() < address.sun_path.len(),
        "fixed listener address bound",
    )?;
    address.sun_family = libc::AF_UNIX as _;
    for (slot, byte) in address.sun_path.iter_mut().zip(path.bytes()) {
        *slot = byte as _;
    }
    let length = std::mem::offset_of!(libc::sockaddr_un, sun_path) + path.len() + 1;
    zero(unsafe {
        libc::bind(
            server.as_raw_fd(),
            (&address as *const libc::sockaddr_un).cast(),
            length as _,
        )
    } as _)?;
    let named = open_at(directory, BASENAME, libc::O_PATH)?;
    let m = named.metadata()?;
    need(
        m.dev() == directory.metadata()?.dev()
            && m.mode() & libc::S_IFMT == libc::S_IFSOCK
            && m.nlink() == 1
            && m.uid() == unsafe { libc::geteuid() }
            && m.gid() == unsafe { libc::getegid() },
        "new fixed filesystem socket inode",
    )?;
    zero(unsafe {
        libc::syscall(
            libc::SYS_fchmodat2,
            named.as_raw_fd(),
            c"".as_ptr(),
            0o600_u32,
            AT_EMPTY_PATH,
        )
    })?;
    zero(unsafe { libc::listen(server.as_raw_fd(), 1) } as _)?;
    Ok((server, named))
}

/// A distinct production constructor. The original ordinary/private seven
/// devices type cannot be converted into this capability after transfer.
pub(crate) struct PreparedActivationDevices {
    devices: PreparedDevices,
}

impl PreparedActivationDevices {
    pub(crate) fn prepare(
        owner: &OwnedNamespaceWitness<'_>,
        selection: &ProductionSelection,
        mac: &MacPreflight,
    ) -> Result<Self> {
        owner.revalidate_live_admission()?;
        mac.revalidate(selection)?;
        let lease = owner.identity_lease()?;
        need(
            selection.spec().host_uid == lease.host_uid()
                && selection.base_cohort() == lease.broker_cohort(),
            "activation DEV and actual selected owner differ",
        )?;
        let devices =
            PreparedDevices::prepare_bound_with_activation(owner, Some((selection, mac)))?;
        let value = Self { devices };
        let listener = value.listener(owner, selection)?;
        let actual = mac.observe_linkerconfig_listener(&listener)?;
        actual.revalidate(mac, &listener)?;
        Ok(value)
    }

    pub(crate) fn listener<'a>(
        &'a self,
        owner: &'a OwnedNamespaceWitness<'a>,
        selection: &'a ProductionSelection,
    ) -> Result<OwnedActivationListener<'a>> {
        let value = OwnedActivationListener {
            devices: &self.devices,
            owner,
            selection,
        };
        value.revalidate()?;
        Ok(value)
    }

    pub(crate) fn descriptor_for_transfer<'a>(
        &'a mut self,
        owner: &OwnedNamespaceWitness<'_>,
        selection: &ProductionSelection,
        mac: &MacPreflight,
    ) -> Result<BorrowedFd<'a>> {
        {
            let listener = self.listener(owner, selection)?;
            let actual = mac.observe_linkerconfig_listener(&listener)?;
            actual.revalidate(mac, &listener)?;
        }
        self.devices.descriptor_for_transfer(owner)
    }

    pub(crate) fn retire_untransferred(self) -> Result<DeviceRetirement> {
        self.devices.retire_untransferred()
    }

    pub(crate) fn retire_after_tree(
        self,
        retired: &RetiredTreeWitness<'_>,
    ) -> Result<DeviceRetirement> {
        self.devices.retire_after_tree(retired)
    }
}

/// Read-only borrow of the actual original listener, private DEV and owner.
/// No PID, saved inode number, label string or supplied FD constructs it.
pub(crate) struct OwnedActivationListener<'a> {
    devices: &'a PreparedDevices,
    owner: &'a OwnedNamespaceWitness<'a>,
    selection: &'a ProductionSelection,
}

impl OwnedActivationListener<'_> {
    fn actual(&self) -> &ActivationListener {
        self.devices
            .resources
            .as_ref()
            .and_then(|r| r.activation.as_ref())
            .expect("typed activation devices retain the original listener")
    }

    /// Full original prepared-DEV validation is intentionally retained. Stock
    /// init's later sockets/mounts need the separately reviewed runtime stage
    /// adapter; this witness does not silently accept an arbitrary new tree.
    /// This function performs no MAC observation, so MAC cannot recurse here.
    pub(crate) fn revalidate(&self) -> Result<()> {
        self.selection
            .revalidate()
            .map_err(|error| DeviceError::Selection(error.to_string()))?;
        self.owner.revalidate_live_admission()?;
        let resources = self
            .devices
            .resources
            .as_ref()
            .ok_or(DeviceError::Rejected("activation DEV has retired"))?;
        need(
            resources.activation.is_some(),
            "original typed listener is absent",
        )?;
        resources.matches(self.owner)?;
        let lease = self.owner.identity_lease()?;
        need(
            self.selection.spec().host_uid == lease.host_uid()
                && self.selection.base_cohort() == lease.broker_cohort(),
            "listener and selected original owner differ",
        )?;
        resources.verify_for_transfer()?;
        self.owner
            .revalidate_live_admission()
            .map_err(DeviceError::from)
    }

    pub(crate) fn selection(&self) -> &ProductionSelection {
        self.selection
    }
    pub(crate) fn sock_file(&self) -> &File {
        &self.actual().node
    }
    pub(crate) fn server(&self) -> BorrowedFd<'_> {
        self.actual().server.as_fd()
    }

    /// Accept from this original listener only. The next stage authenticates
    /// the new connection's actual peer PIDFD; accept alone grants no command.
    pub(crate) fn accept(&self, mac: &MacPreflight, deadline: Instant) -> Result<OwnedFd> {
        self.revalidate()?;
        let policy = mac.observe_linkerconfig_listener(self)?;
        let init = self.owner.descendant_pidfd().ok_or(DeviceError::Rejected(
            "actual original init PIDFD is absent",
        ))?;
        loop {
            let now = Instant::now();
            if now >= deadline {
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "activation accept absolute deadline",
                )
                .into());
            }
            self.revalidate()?;
            policy.revalidate(mac, self)?;
            let remaining = deadline
                .checked_duration_since(Instant::now())
                .ok_or_else(|| {
                    io::Error::new(
                        io::ErrorKind::TimedOut,
                        "activation accept absolute deadline",
                    )
                })?;
            let millis = remaining
                .as_nanos()
                .div_ceil(1_000_000)
                .min(i32::MAX as u128) as i32;
            let mut events = [
                libc::pollfd {
                    fd: self.server().as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
                libc::pollfd {
                    fd: init.as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
                libc::pollfd {
                    fd: self.owner.pidfd().as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
            ];
            let count = unsafe { libc::poll(events.as_mut_ptr(), events.len() as _, millis) };
            if count < 0 {
                let error = io::Error::last_os_error();
                if error.kind() == io::ErrorKind::Interrupted {
                    continue;
                }
                return Err(error.into());
            }
            if Instant::now() >= deadline {
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "activation accept absolute deadline",
                )
                .into());
            }
            need(
                events.iter().all(|event| {
                    event.revents & (libc::POLLERR | libc::POLLNVAL | libc::POLLHUP) == 0
                }) && events[1].revents == 0
                    && events[2].revents == 0,
                "original owner exited or activation listener failed",
            )?;
            if count == 0 || events[0].revents & libc::POLLIN == 0 {
                continue;
            }
            let raw = unsafe {
                libc::accept4(
                    self.server().as_raw_fd(),
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    libc::SOCK_NONBLOCK | libc::SOCK_CLOEXEC,
                )
            };
            if raw < 0 {
                let error = io::Error::last_os_error();
                if matches!(
                    error.kind(),
                    io::ErrorKind::Interrupted | io::ErrorKind::WouldBlock
                ) {
                    continue;
                }
                return Err(error.into());
            }
            let accepted = unsafe { OwnedFd::from_raw_fd(raw) };
            pass_credentials(accepted.as_fd())?;
            private_flags(accepted.as_fd())?;
            socket_option(accepted.as_fd(), libc::SO_TYPE, libc::SOCK_SEQPACKET)?;
            socket_option(accepted.as_fd(), libc::SO_DOMAIN, libc::AF_UNIX)?;
            socket_option(accepted.as_fd(), libc::SO_PASSCRED, 1)?;
            policy.revalidate(mac, self)?;
            self.revalidate()?;
            if Instant::now() >= deadline {
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "activation accept absolute deadline",
                )
                .into());
            }
            return Ok(accepted);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::ffi::OsStrExt;

    #[test]
    fn fixed_socket_alias_reaches_same_inode_and_never_replaces_existing_entry() {
        let temp = tempfile::tempdir().unwrap();
        let directory = File::open(temp.path()).unwrap();
        let (server, inode) = bind_socket(&directory).unwrap();
        let original = identity(&inode.metadata().unwrap());
        assert_eq!(inode.metadata().unwrap().mode(), libc::S_IFSOCK | 0o600);
        private_flags(server.as_fd()).unwrap();
        socket_option(server.as_fd(), libc::SO_ACCEPTCONN, 1).unwrap();
        socket_option(server.as_fd(), libc::SO_PASSCRED, 1).unwrap();
        let cookie = socket_cookie(server.as_fd()).unwrap();
        let raw = unsafe {
            libc::socket(
                libc::AF_UNIX,
                libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
                0,
            )
        };
        assert!(raw >= 0);
        let client = unsafe { OwnedFd::from_raw_fd(raw) };
        let path = temp.path().join(BASENAME.to_str().unwrap());
        let bytes = path.as_os_str().as_bytes();
        let mut address: libc::sockaddr_un = unsafe { std::mem::zeroed() };
        assert!(bytes.len() < address.sun_path.len());
        address.sun_family = libc::AF_UNIX as _;
        for (slot, byte) in address.sun_path.iter_mut().zip(bytes) {
            *slot = *byte as _;
        }
        let length = std::mem::offset_of!(libc::sockaddr_un, sun_path) + bytes.len() + 1;
        assert_eq!(
            unsafe {
                libc::connect(
                    client.as_raw_fd(),
                    (&address as *const libc::sockaddr_un).cast(),
                    length as _,
                )
            },
            0
        );
        let raw = unsafe {
            libc::accept4(
                server.as_raw_fd(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
            )
        };
        assert!(raw >= 0);
        let accepted = unsafe { OwnedFd::from_raw_fd(raw) };
        private_flags(accepted.as_fd()).unwrap();
        assert_eq!(
            identity(
                &open_at(&directory, BASENAME, libc::O_PATH)
                    .unwrap()
                    .metadata()
                    .unwrap()
            ),
            original
        );
        assert_eq!(socket_cookie(server.as_fd()).unwrap(), cookie);
        for attempt in 0..2 {
            match bind_socket(&directory) {
                Err(DeviceError::Io(error)) => {
                    assert_eq!(error.raw_os_error(), Some(libc::EADDRINUSE))
                }
                _ => panic!("attempt {attempt} did not reject the existing fixed inode"),
            }
        }
        drop(accepted);
        drop(client);
        drop(server);
        // A retired server still does not authorize reusing its old directory.
        match bind_socket(&directory) {
            Err(DeviceError::Io(error)) => assert_eq!(error.raw_os_error(), Some(libc::EADDRINUSE)),
            _ => panic!("retired listener inode was silently replaced"),
        }
        assert_eq!(identity(&inode.metadata().unwrap()), original);
    }
}
