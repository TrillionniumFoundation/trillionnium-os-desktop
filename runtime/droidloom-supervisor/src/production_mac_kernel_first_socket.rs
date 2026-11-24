//! Direct public control transport for the original kernel-first generation.
//! The original runtime/package owner is retained before creating a socket.
//! No namespace switch, legacy provider selection or path-only proof is used.
use super::*;
use crate::production_execution::RuntimeMacOwner;

const CONTROL_DIRECTORY: &str = "u:object_r:droidloom_public_control_dir:s0";
const CONTROL_SOCKET: &str = "u:object_r:droidloom_public_control_socket:s0";

fn early(loaded: &LoadedPolicyWitness, selection: &ProductionSelection) -> Result<()> {
    loaded.revalidate(selection)?;
    require(
        selection.is_kernel_first()
            && loaded.declaration.early()
            && !loaded.declaration.scoped_contexts()?
            && loaded.early_media_held(),
        "direct control transport requires the original kernel-first selection and media",
    )?;
    self_attr::require_no_fscreate()?;
    loaded.stable_epoch()
}

fn initial_network(file: &File) -> Result<()> {
    require(
        kind(file)? == 0x6e736673,
        "direct control network must be nsfs",
    )?;
    let mut id = 0_u64;
    let ty = unsafe { libc::ioctl(file.as_raw_fd(), 0xb703, 0 as libc::c_ulong) };
    if ty < 0 || unsafe { libc::ioctl(file.as_raw_fd(), 0x8008_b70d, &mut id) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        ty == libc::CLONE_NEWNET && id == 7,
        "direct control requires the initial network namespace",
    )?;
    let current = File::open("/proc/thread-self/ns/net")?;
    require(
        descriptor_identity(current.as_fd())? == descriptor_identity(file.as_fd())?,
        "direct control creator left its original network namespace",
    )
}

fn listener_creation(loaded: &LoadedPolicyWitness, parent: &File) -> Result<Vec<u8>> {
    self_attr::require_no_fscreate()?;
    let label = held_label(parent)?;
    let context = object_context(&label)?;
    require(
        context == CONTROL_DIRECTORY,
        "direct public listener requires its fixed directory label",
    )?;
    let number = class_number(&loaded.root, "sock_file")?;
    let command = format!("{BROKER} {context} {number} control.sock");
    let actual = transaction(&loaded.root, "create", command.as_bytes())?;
    let target = object_context(&actual)?;
    require(
        target == CONTROL_SOCKET,
        "direct public listener requires its fixed named transition",
    )?;
    let mut sequence = Some(loaded.av_sequence);
    access(
        &loaded.root,
        BROKER,
        context,
        "dir",
        &["getattr", "search", "write", "add_name"],
        true,
        &mut sequence,
    )?;
    access(
        &loaded.root,
        BROKER,
        target,
        "sock_file",
        &["create", "getattr", "setattr", "write"],
        true,
        &mut sequence,
    )?;
    access(
        &loaded.root,
        BROKER,
        BROKER,
        "unix_stream_socket",
        &[
            "create", "bind", "listen", "accept", "getattr", "read", "write", "getopt", "setopt",
        ],
        true,
        &mut sequence,
    )?;
    require(
        held_label(parent)? == label,
        "direct listener parent label changed",
    )?;
    loaded.stable_epoch()?;
    Ok(actual)
}

fn actual_peer(fd: BorrowedFd<'_>) -> Result<ConnectedPeer> {
    let credentials = peer_credentials(fd)?;
    let pidfd = peer_pidfd(fd)?;
    let identity = descriptor_identity(pidfd.as_fd())?;
    let context = actual_socket_security(fd)?;
    let text = context.strip_suffix(&[0]).unwrap_or(&context);
    let text = std::str::from_utf8(text)
        .map_err(|_| MacError::Rejected("direct peer context encoding"))?;
    require(
        (text.starts_with("u:r:") || text.starts_with("u:system_r:"))
            && text.len() <= 512
            && text
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"_:,.-".contains(&b)),
        "direct socket returned no actual SELinux peer context",
    )?;
    let value = ConnectedPeer {
        credentials,
        pidfd,
        identity,
        context,
    };
    value.revalidate(fd)?;
    Ok(value)
}

pub(crate) struct KernelFirstBrokerListener {
    owner: RuntimeMacOwner,
    provider: ProviderBinding,
    network: File,
    parent: File,
    parent_node: Node,
    expected_label: Vec<u8>,
    end: Instant,
    attempted: bool,
    retired: bool,
    listener: Option<UnixListener>,
    socket: Option<(DescriptorIdentity, u64)>,
    server: Option<ListenerInode>,
}

impl KernelFirstBrokerListener {
    pub(crate) fn prepare(owner: RuntimeMacOwner, parent: &File, end: Instant) -> Result<Self> {
        deadline(end)?;
        let (mac, selection) = owner
            .objects()
            .map_err(|e| MacError::Owner(e.to_string()))?;
        early(mac.loaded_policy(), selection)?;
        let original = trusted_directory(parent)?;
        let fixed = fixed_parent(Purpose::Listener)?;
        let parent_node = trusted_directory(&fixed)?;
        require(
            same_inode(original, parent_node),
            "direct listener parent is not original /run/droidloom",
        )?;
        let network = File::open("/proc/thread-self/ns/net")?;
        initial_network(&network)?;
        policy::fixed_namespace_label(&network, &mac.loaded_policy().declaration)?;
        let expected_label = listener_creation(mac.loaded_policy(), &fixed)?;
        let provider = mac.loaded_policy().binding();
        deadline(end)?;
        Ok(Self {
            owner,
            provider,
            network,
            parent: fixed,
            parent_node,
            expected_label,
            end,
            attempted: false,
            retired: false,
            listener: None,
            socket: None,
            server: None,
        })
    }

    fn original(&self) -> Result<()> {
        require(!self.retired, "direct listener already retired")?;
        let (mac, selection) = self
            .owner
            .objects()
            .map_err(|e| MacError::Owner(e.to_string()))?;
        early(mac.loaded_policy(), selection)?;
        require(
            mac.loaded_policy().binding() == self.provider,
            "direct listener lost its original MAC provider",
        )?;
        initial_network(&self.network)?;
        policy::fixed_namespace_label(&self.network, &mac.loaded_policy().declaration)?;
        require(
            same_inode(trusted_directory(&self.parent)?, self.parent_node)
                && same_inode(
                    trusted_directory(&fixed_parent(Purpose::Listener)?)?,
                    self.parent_node,
                ),
            "direct listener original parent changed",
        )?;
        require(
            listener_creation(mac.loaded_policy(), &self.parent)? == self.expected_label,
            "direct listener original automatic create decision changed",
        )?;
        mac.loaded_policy().stable_epoch()
    }

    pub(crate) fn bind_and_listen(&mut self) -> Result<()> {
        require(
            !self.attempted,
            "direct listener creation cannot be replayed",
        )?;
        self.original()?;
        deadline(self.end)?;
        self.attempted = true;
        let mut stat: libc::stat = unsafe { std::mem::zeroed() };
        let rc = unsafe {
            libc::fstatat(
                self.parent.as_raw_fd(),
                c"control.sock".as_ptr(),
                &mut stat,
                libc::AT_SYMLINK_NOFOLLOW,
            )
        };
        require(
            rc < 0 && io::Error::last_os_error().raw_os_error() == Some(libc::ENOENT),
            "fixed control.sock must be absent; no implicit replacement",
        )?;
        let raw = unsafe {
            libc::socket(
                libc::AF_UNIX,
                libc::SOCK_STREAM | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
                0,
            )
        };
        if raw < 0 {
            return Err(io::Error::last_os_error().into());
        }
        self.listener = Some(unsafe { UnixListener::from_raw_fd(raw) });
        let socket = self.listener.as_ref().unwrap().as_fd();
        self.socket = Some((descriptor_identity(socket)?, socket_cookie(socket)?));
        require(
            context_matches(&super::super::listener::server_label(socket)?, BROKER),
            "direct listener socket was not created in the broker domain",
        )?;
        self.original()?;
        deadline(self.end)?;
        let (address, n) = address(&format!(
            "/proc/self/fd/{}/control.sock",
            self.parent.as_raw_fd()
        ))?;
        zero(unsafe { libc::bind(raw, (&address as *const libc::sockaddr_un).cast(), n) })?;
        let file = open_at(self.parent.as_raw_fd(), c"control.sock", libc::O_PATH)?;
        let node = Node::of(&file)?;
        self.server = Some(ListenerInode {
            file,
            node,
            label: Vec::new(),
        });
        let server = self.server.as_mut().unwrap();
        require(
            context_matches(
                &named_socket(&server.file, server.node)?,
                object_context(&self.expected_label)?,
            ),
            "direct control inode did not receive its automatic policy transition",
        )?;
        chmod_original(&server.file)?;
        server.node = Node::of(&server.file)?;
        server.label = named_socket(&server.file, server.node)?;
        require(
            context_matches(&server.label, object_context(&self.expected_label)?),
            "direct control inode label changed across exact chmod",
        )?;
        deadline(self.end)?;
        zero(unsafe { libc::listen(raw, 128) })?;
        self.revalidate()?;
        deadline(self.end)
    }

    fn revalidate(&self) -> Result<()> {
        self.original()?;
        let listener = self
            .listener
            .as_ref()
            .ok_or(MacError::Rejected("direct listener absent"))?;
        let (node, cookie) = self
            .socket
            .ok_or(MacError::Rejected("direct listener identity absent"))?;
        socket_identity(listener.as_fd(), node, cookie, true, true)?;
        require(
            context_matches(
                &super::super::listener::server_label(listener.as_fd())?,
                BROKER,
            ),
            "direct listener socket label changed",
        )?;
        let server = self
            .server
            .as_ref()
            .ok_or(MacError::Rejected("direct listener inode absent"))?;
        require(
            server.node.mode & 0o7777 == 0o666
                && named_socket(&server.file, server.node)? == server.label
                && context_matches(&server.label, object_context(&self.expected_label)?),
            "direct listener inode mode or label changed",
        )?;
        fixed_server(Purpose::Listener, &server.file, server.node)?;
        self.original()
    }

    pub(crate) fn server_inode(&self) -> Result<&File> {
        let server = self
            .server
            .as_ref()
            .ok_or(MacError::Rejected("direct bound server inode not captured"))?;
        let now = Node::of(&server.file)?;
        require(
            now.dev == server.node.dev
                && now.ino == server.node.ino
                && now.mode & libc::S_IFMT == libc::S_IFSOCK,
            "direct bound server inode changed",
        )?;
        Ok(&server.file)
    }
    pub(crate) fn listener(&self) -> Result<&UnixListener> {
        self.revalidate()?;
        self.listener
            .as_ref()
            .ok_or(MacError::Rejected("direct listener retired"))
    }
    pub(crate) fn accept(&self) -> Result<KernelFirstAcceptedStream<'_>> {
        self.revalidate()?;
        let raw = unsafe {
            libc::accept4(
                self.listener()?.as_raw_fd(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
            )
        };
        if raw < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let stream = unsafe { UnixStream::from_raw_fd(raw) };
        stream.set_nonblocking(false)?;
        let node = descriptor_identity(stream.as_fd())?;
        let cookie = socket_cookie(stream.as_fd())?;
        let peer = actual_peer(stream.as_fd())?;
        let value = KernelFirstAcceptedStream {
            listener: self,
            stream,
            node,
            cookie,
            peer,
        };
        value.revalidate()?;
        Ok(value)
    }
    pub(crate) fn retire(&mut self) -> Result<()> {
        // All accepted streams borrow this owner. Exclusive retirement closes
        // the only listener description before the outer exact-inode unlink.
        self.retired = true;
        self.listener.take();
        Ok(())
    }
}

pub(crate) struct KernelFirstAcceptedStream<'a> {
    listener: &'a KernelFirstBrokerListener,
    stream: UnixStream,
    node: DescriptorIdentity,
    cookie: u64,
    peer: ConnectedPeer,
}
impl KernelFirstAcceptedStream<'_> {
    fn revalidate(&self) -> Result<()> {
        self.listener.revalidate()?;
        socket_identity(self.stream.as_fd(), self.node, self.cookie, false, false)?;
        self.peer.revalidate(self.stream.as_fd())?;
        self.listener.revalidate()
    }
    pub(crate) fn stream(&self) -> Result<&UnixStream> {
        self.revalidate()?;
        Ok(&self.stream)
    }
    pub(crate) fn stream_mut(&mut self) -> Result<&mut UnixStream> {
        self.revalidate()?;
        Ok(&mut self.stream)
    }
}

pub(crate) struct KernelFirstPackageStream {
    owner: PackageMacOwner,
    provider: ProviderBinding,
    server: File,
    server_node: Node,
    label: Vec<u8>,
    network: File,
    end: Instant,
    attempted: bool,
    retired: bool,
    stream: Option<UnixStream>,
    socket: Option<(DescriptorIdentity, u64)>,
    peer: Option<ConnectedPeer>,
}
impl KernelFirstPackageStream {
    pub(crate) fn prepare(owner: &PackageMacOwner, server: &File, end: Instant) -> Result<Self> {
        deadline(end)?;
        owner.revalidate()?;
        require(
            owner.role() == PackageMacRole::Helper && end <= owner.deadline(),
            "direct package stream requires original helper and deadline",
        )?;
        let (loaded, selection) = owner.objects()?;
        early(loaded, selection)?;
        let server_node = Node::of(server)?;
        require(
            server_node.mode & 0o7777 == 0o666,
            "direct public transport mode differs",
        )?;
        let label = named_socket(server, server_node)?;
        require(
            context_matches(&label, CONTROL_SOCKET),
            "direct package endpoint requires its fixed public socket label",
        )?;
        fixed_server(Purpose::Package, server, server_node)?;
        let network = File::open("/proc/thread-self/ns/net")?;
        initial_network(&network)?;
        policy::fixed_namespace_label(&network, &loaded.declaration)?;
        let value = Self {
            owner: owner.retain_original()?,
            provider: loaded.binding(),
            server: server.try_clone()?,
            server_node,
            label,
            network,
            end,
            attempted: false,
            retired: false,
            stream: None,
            socket: None,
            peer: None,
        };
        value.original()?;
        deadline(end)?;
        Ok(value)
    }
    fn original(&self) -> Result<()> {
        require(!self.retired, "direct package stream retired")?;
        deadline(self.end)?;
        let (loaded, selection) = self.owner.objects()?;
        early(loaded, selection)?;
        require(
            loaded.binding() == self.provider,
            "direct package original MAC provider changed",
        )?;
        initial_network(&self.network)?;
        policy::fixed_namespace_label(&self.network, &loaded.declaration)?;
        fixed_server(Purpose::Package, &self.server, self.server_node)?;
        require(
            named_socket(&self.server, self.server_node)? == self.label,
            "direct package server label changed",
        )?;
        let source = self.owner.local_context();
        let mut sequence = Some(loaded.av_sequence);
        access(
            &loaded.root,
            source,
            source,
            "unix_stream_socket",
            &[
                "create", "connect", "getattr", "read", "write", "getopt", "setopt",
            ],
            true,
            &mut sequence,
        )?;
        access(
            &loaded.root,
            source,
            BROKER,
            "unix_stream_socket",
            &["connectto"],
            true,
            &mut sequence,
        )?;
        access(
            &loaded.root,
            source,
            object_context(&self.label)?,
            "sock_file",
            &["write"],
            true,
            &mut sequence,
        )?;
        loaded.stable_epoch()?;
        deadline(self.end)
    }
    pub(crate) fn connect(&mut self) -> Result<()> {
        require(!self.attempted, "direct package connect cannot be replayed")?;
        self.original()?;
        self.attempted = true;
        let raw = unsafe {
            libc::socket(
                libc::AF_UNIX,
                libc::SOCK_STREAM | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
                0,
            )
        };
        if raw < 0 {
            return Err(io::Error::last_os_error().into());
        }
        self.stream = Some(unsafe { UnixStream::from_raw_fd(raw) });
        self.original()?;
        connect_original(
            self.stream.as_ref().unwrap().as_fd(),
            &self.server,
            self.end,
        )?;
        let stream = self.stream.as_ref().unwrap();
        let peer = actual_peer(stream.as_fd())?;
        require(
            context_matches(&peer.context, BROKER)
                && peer.credentials.uid == 0
                && peer.credentials.gid == 0,
            "direct package socket is not connected to the actual root broker",
        )?;
        stream.set_nonblocking(false)?;
        self.socket = Some((
            descriptor_identity(stream.as_fd())?,
            socket_cookie(stream.as_fd())?,
        ));
        self.peer = Some(peer);
        self.revalidate()
    }
    fn revalidate(&self) -> Result<()> {
        self.original()?;
        let stream = self
            .stream
            .as_ref()
            .ok_or(MacError::Rejected("direct package socket absent"))?;
        let (node, cookie) = self
            .socket
            .ok_or(MacError::Rejected("direct package socket identity absent"))?;
        socket_identity(stream.as_fd(), node, cookie, false, false)?;
        self.peer
            .as_ref()
            .ok_or(MacError::Rejected("direct package peer absent"))?
            .revalidate(stream.as_fd())?;
        self.original()
    }
    pub(crate) fn stream(&self) -> Result<&UnixStream> {
        self.revalidate()?;
        Ok(self.stream.as_ref().unwrap())
    }
    pub(crate) fn stream_mut(&mut self) -> Result<&mut UnixStream> {
        self.revalidate()?;
        Ok(self.stream.as_mut().unwrap())
    }
    pub(crate) fn retire(&mut self) -> Result<()> {
        self.retired = true;
        self.stream.take();
        self.peer.take();
        Ok(())
    }
}

// Close the live descriptions while the original issuer and namespace custody
// are still retained, including preparation/connect failures.
impl Drop for KernelFirstBrokerListener {
    fn drop(&mut self) {
        if let Err(error) = self.retire() {
            eprintln!("direct broker socket retirement failed: {error}");
        }
    }
}
impl Drop for KernelFirstPackageStream {
    fn drop(&mut self) {
        if let Err(error) = self.retire() {
            eprintln!("direct package socket retirement failed: {error}");
        }
    }
}
