//! Actual original host manager endpoint, independent of unit RPC or MAC authority.
//!
//! Capture has no caller-supplied PID, path, file descriptor or role. The kernel
//! peer PIDFD must identify initial-namespace root PID1; this same process holds
//! the original manager, observer, namespace, directory and server inode owners.
//! A loaded-policy observer must separately authenticate their current labels.
//! No endpoint or generation value admits Android. The distinct consumed label
//! operation also requires the actual fixed loader role and installed inputs.
use super::*;
use crate::production_mac::{
    HostPeerIssuer, LoaderHostPeerOwner, ManagerSelectedStream, PackageMacOwner,
};
use std::ops::Deref;
use std::time::Instant;

#[path = "production_systemd_label.rs"]
mod label;
pub(crate) use label::ManagerLabelReport;

const SO_PEERPIDFD: i32 = 77;
const PROC_MAGIC: libc::c_long = 0x9fa0;

fn alive(pidfd: &File) -> Result<()> {
    let mut event = libc::pollfd {
        fd: pidfd.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    let value = unsafe { libc::poll(&mut event, 1, 0) };
    if value < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        value == 0 && event.revents == 0,
        "original service owner PIDFD is no longer live",
    )
}
pub(super) fn before(deadline: Instant) -> Result<()> {
    if Instant::now() >= deadline {
        return Err(io::Error::from_raw_os_error(libc::ETIMEDOUT).into());
    }
    Ok(())
}
pub(super) fn proc_read(directory: &File, name: &CStr) -> Result<String> {
    let file = open_at(directory, name, libc::O_RDONLY)?;
    let mut fs: libc::statfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstatfs(file.as_raw_fd(), &mut fs) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        fs.f_type == PROC_MAGIC,
        "held service owner proc filesystem changed",
    )?;
    let mut bytes = Vec::new();
    (&file).take(65537).read_to_end(&mut bytes)?;
    require(bytes.len() <= 65536, "service owner proc observation bound")?;
    String::from_utf8(bytes).map_err(|_| CgroupError::Rejected("non-UTF8 service owner proc value"))
}
pub(super) fn pidfd_pid(file: &File) -> Result<u32> {
    let name = CString::new(format!("/proc/self/fdinfo/{}", file.as_raw_fd()))
        .map_err(|_| CgroupError::Rejected("invalid own PIDFD alias"))?;
    let text = read_absolute(&name)?;
    let pid: Vec<_> = text
        .lines()
        .filter_map(|l| l.strip_prefix("Pid:\t"))
        .collect();
    let nspid: Vec<_> = text
        .lines()
        .filter_map(|l| l.strip_prefix("NSpid:\t"))
        .collect();
    require(
        pid.len() == 1 && nspid.len() == 1 && pid[0] == nspid[0],
        "service owner PIDFD is not bound in the initial PID namespace",
    )?;
    pid[0]
        .parse()
        .map_err(|_| CgroupError::Rejected("invalid live kernel PIDFD identity"))
}
pub(super) fn proc_start(text: &str, expected: u32) -> Result<u64> {
    let split = text
        .rfind(')')
        .ok_or(CgroupError::Rejected("invalid held process stat"))?;
    let prefix = text
        .split_once(' ')
        .ok_or(CgroupError::Rejected("invalid held process PID"))?
        .0;
    require(prefix == expected.to_string(), "held process PID changed")?;
    let fields: Vec<_> = text[split + 1..].split_whitespace().collect();
    require(fields.len() >= 20, "short held process stat")?;
    fields[19]
        .parse()
        .map_err(|_| CgroupError::Rejected("invalid original process start time"))
}

fn initial_namespaces() -> Result<Vec<File>> {
    require(
        unsafe { libc::getuid() == 0 && libc::geteuid() == 0 },
        "initial-root service observer required",
    )?;
    let mut values = Vec::new();
    for (name, kind, expected) in [
        (c"/proc/self/ns/user", libc::CLONE_NEWUSER, 3_u64),
        (c"/proc/self/ns/pid", libc::CLONE_NEWPID, 4_u64),
    ] {
        let descriptor = unsafe { libc::open(name.as_ptr(), libc::O_RDONLY | libc::O_CLOEXEC) };
        if descriptor < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let file = unsafe { File::from_raw_fd(descriptor) };
        let mut id = 0_u64;
        require(
            unsafe { libc::ioctl(file.as_raw_fd(), NS_GET_NSTYPE, 0 as libc::c_ulong) } == kind
                && unsafe { libc::ioctl(file.as_raw_fd(), NS_GET_ID, &mut id as *mut u64) } == 0
                && id == expected,
            "initial user/PID namespace required for manager custody",
        )?;
        values.push(file);
    }
    Ok(values)
}

struct Task {
    pidfd: File,
    pid: u32,
    proc: File,
    proc_node: NodeIdentity,
    start: u64,
    executable: File,
    executable_seal: Metadata,
}
impl Task {
    fn executable(proc: &File) -> Result<File> {
        // Follow only this held real proc inode's fixed kernel magic link.
        let fd = unsafe {
            libc::openat(
                proc.as_raw_fd(),
                c"exe".as_ptr(),
                libc::O_PATH | libc::O_CLOEXEC,
            )
        };
        if fd < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let file = unsafe { File::from_raw_fd(fd) };
        let meta = file.metadata()?;
        require(
            meta.is_file()
                && meta.uid() == 0
                && meta.gid() == 0
                && meta.nlink() == 1
                && meta.mode() & 0o6022 == 0
                && meta.mode() & 0o111 != 0,
            "service owner executable is not root controlled",
        )?;
        Ok(file)
    }
    fn capture(pidfd: File, pid: u32) -> Result<Self> {
        alive(&pidfd)?;
        require(
            pid > 0 && pidfd_pid(&pidfd)? == pid,
            "original PIDFD does not name expected owner",
        )?;
        let path = CString::new(format!("/proc/{pid}"))
            .map_err(|_| CgroupError::Rejected("invalid observed owner proc name"))?;
        let proc = open_absolute(&path, libc::O_RDONLY | libc::O_DIRECTORY)?;
        let start = proc_start(&proc_read(&proc, c"stat")?, pid)?;
        let executable = Self::executable(&proc)?;
        let value = Self {
            pidfd,
            pid,
            proc_node: NodeIdentity::of(&proc)?,
            proc,
            start,
            executable_seal: executable.metadata()?,
            executable,
        };
        value.check()?;
        Ok(value)
    }
    fn check(&self) -> Result<()> {
        alive(&self.pidfd)?;
        require(
            pidfd_pid(&self.pidfd)? == self.pid
                && NodeIdentity::of(&self.proc)? == self.proc_node
                && proc_start(&proc_read(&self.proc, c"stat")?, self.pid)? == self.start,
            "original service owner process generation changed",
        )?;
        let current = Self::executable(&self.proc)?;
        require(
            file_seal(&current.metadata()?) == file_seal(&self.executable_seal)
                && file_seal(&self.executable.metadata()?) == file_seal(&self.executable_seal),
            "original service owner executable changed",
        )?;
        let status = proc_read(&self.proc, c"status")?;
        for key in ["Uid:", "Gid:"] {
            let rows: Vec<_> = status
                .lines()
                .filter_map(|line| line.strip_prefix(key))
                .collect();
            require(
                rows.len() == 1
                    && rows[0].split_whitespace().collect::<Vec<_>>() == ["0", "0", "0", "0"],
                "service owner credentials changed",
            )?;
        }
        alive(&self.pidfd)
    }
}

/// Own the selected connection and every local duplicate in an explicit order.
/// The endpoint never reconstructs its original MAC/namespace authority.
#[path = "production_systemd_early_socket.rs"]
mod early_socket;
use crate::production_mac::EarlyManagerClient;

enum ManagerOrigin {
    Selected(HostPeerIssuer),
    KernelFirst(EarlyManagerClient),
}

enum ManagerSocket {
    Selected(SelectedManagerSocket),
    KernelFirst(early_socket::EarlyManagerSocket),
}
impl Deref for ManagerSocket {
    type Target = File;
    fn deref(&self) -> &File {
        match self {
            Self::Selected(value) => value,
            Self::KernelFirst(value) => value.connection(),
        }
    }
}

struct SelectedManagerSocket {
    duplicate: Option<File>,
    selected: ManagerSelectedStream,
}
impl SelectedManagerSocket {
    fn connect(issuer: HostPeerIssuer, server: &File, deadline: Instant) -> Result<Self> {
        before(deadline)?;
        let selected = ManagerSelectedStream::prepare(issuer, server, deadline)
            .map_err(|error| io::Error::other(error.to_string()))?;
        // This outer owner exists before the first namespace/selector/socket
        // mutation; its selected child's Drop preserves failed retirement.
        let mut value = Self {
            duplicate: None,
            selected,
        };
        value
            .selected
            .connect()
            .map_err(|error| io::Error::other(error.to_string()))?;
        value.duplicate = Some(
            value
                .selected
                .connection()
                .map_err(|error| io::Error::other(error.to_string()))?
                .try_clone()?,
        );
        value.revalidate()?;
        before(deadline)?;
        Ok(value)
    }
    fn revalidate(&self) -> Result<()> {
        let duplicate = self.duplicate.as_ref().ok_or(CgroupError::Rejected(
            "original selected manager duplicate absent",
        ))?;
        self.selected
            .check_duplicate(duplicate)
            .map_err(|error| io::Error::other(error.to_string()))?;
        Ok(())
    }
}
impl Deref for SelectedManagerSocket {
    type Target = File;
    fn deref(&self) -> &File {
        // Only the completed private constructor can issue SelectedManagerSocket.
        self.duplicate
            .as_ref()
            .expect("completed original manager socket")
    }
}
impl Drop for SelectedManagerSocket {
    fn drop(&mut self) {
        self.duplicate.take();
        // All our duplicates close before the original selected owner. Its
        // own Drop retains custody if original PIDFD retirement is unproven.
        let _ = self.selected.retire();
    }
}

struct EndpointCustody {
    socket: ManagerSocket,
    socket_node: NodeIdentity,
    file: File,
    server_node: NodeIdentity,
    directories: Vec<File>,
    directory_nodes: Vec<NodeIdentity>,
    manager: Task,
    observer: Task,
    namespaces: Vec<File>,
    thread: libc::pid_t,
    _same_thread: PhantomData<Rc<()>>,
}

/// Equality binds observations to this original endpoint. This value neither
/// owns descriptors nor proves that the endpoint or its MAC policy is live.
#[derive(Clone, Eq, PartialEq)]
pub(crate) struct ManagerEndpointGeneration {
    manager_start: u64,
    observer_start: u64,
    observer_pid: u32,
    manager_executable: NodeIdentity,
    observer_executable: NodeIdentity,
    connection: NodeIdentity,
}

fn peer_credentials(socket: &File) -> Result<libc::ucred> {
    let mut credentials: libc::ucred = unsafe { std::mem::zeroed() };
    let mut size = std::mem::size_of::<libc::ucred>() as libc::socklen_t;
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
        size as usize == std::mem::size_of::<libc::ucred>()
            && credentials.pid == 1
            && credentials.uid == 0
            && credentials.gid == 0,
        "private manager peer is not actual host PID1",
    )?;
    Ok(credentials)
}
fn peer_pidfd(socket: &File) -> Result<File> {
    let mut descriptor: i32 = -1;
    let mut size = std::mem::size_of::<i32>() as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            socket.as_raw_fd(),
            libc::SOL_SOCKET,
            SO_PEERPIDFD,
            (&mut descriptor as *mut i32).cast(),
            &mut size,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    require(descriptor >= 0, "kernel manager PIDFD absent")?;
    let value = unsafe { File::from_raw_fd(descriptor) };
    let flags = unsafe { libc::fcntl(descriptor, libc::F_GETFD) };
    if flags < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        size as usize == std::mem::size_of::<i32>() && flags & libc::FD_CLOEXEC != 0,
        "kernel manager PIDFD size or CLOEXEC differs",
    )?;
    Ok(value)
}

impl Task {
    fn namespaces(&self, expected: &[File]) -> Result<()> {
        require(
            expected.len() == 2,
            "complete manager namespace custody required",
        )?;
        for (name, original) in [c"ns/user", c"ns/pid"].iter().zip(expected) {
            let fd = unsafe {
                libc::openat(
                    self.proc.as_raw_fd(),
                    name.as_ptr(),
                    libc::O_RDONLY | libc::O_CLOEXEC,
                )
            };
            if fd < 0 {
                return Err(io::Error::last_os_error().into());
            }
            let observed = unsafe { File::from_raw_fd(fd) };
            require(
                NodeIdentity::of(&observed)? == NodeIdentity::of(original)?,
                "manager/broker left the original initial namespaces",
            )?;
        }
        Ok(())
    }
}

impl EndpointCustody {
    fn capture(origin: ManagerOrigin, deadline: Instant) -> Result<(Self, Metadata)> {
        before(deadline)?;
        let namespaces = initial_namespaces()?;
        let mut directories = vec![open_absolute(c"/", libc::O_RDONLY | libc::O_DIRECTORY)?];
        for name in [c"run", c"systemd"] {
            trusted_directory(directories.last().unwrap())?;
            directories.push(open_at(
                directories.last().unwrap(),
                name,
                libc::O_RDONLY | libc::O_DIRECTORY,
            )?);
        }
        trusted_directory(directories.last().unwrap())?;
        let file = open_at(directories.last().unwrap(), c"private", libc::O_PATH)?;
        let file_seal = file.metadata()?;
        require(
            file_seal.mode() & libc::S_IFMT == libc::S_IFSOCK
                && file_seal.uid() == 0
                && file_seal.gid() == 0
                && file_seal.nlink() == 1
                && file_seal.mode() & 0o022 == 0,
            "fixed manager sock_file is not root controlled",
        )?;
        let socket = match origin {
            ManagerOrigin::Selected(issuer) => {
                ManagerSocket::Selected(SelectedManagerSocket::connect(issuer, &file, deadline)?)
            }
            ManagerOrigin::KernelFirst(issuer) => ManagerSocket::KernelFirst(
                early_socket::EarlyManagerSocket::connect(issuer, &file, deadline)?,
            ),
        };
        let manager = Task::capture(peer_pidfd(&socket)?, 1)?;
        let pid = unsafe { libc::getpid() };
        let descriptor = unsafe { libc::syscall(libc::SYS_pidfd_open, pid, 0) };
        if descriptor < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let observer = Task::capture(unsafe { File::from_raw_fd(descriptor as i32) }, pid as u32)?;
        manager.namespaces(&namespaces)?;
        observer.namespaces(&namespaces)?;
        let value = Self {
            socket_node: NodeIdentity::of(&socket)?,
            socket,
            server_node: NodeIdentity::of(&file)?,
            file,
            directory_nodes: directories
                .iter()
                .map(NodeIdentity::of)
                .collect::<Result<_>>()?,
            directories,
            manager,
            observer,
            namespaces,
            thread: unsafe { libc::syscall(libc::SYS_gettid) } as libc::pid_t,
            _same_thread: PhantomData,
        };
        value.check_until(deadline)?;
        Ok((value, file_seal))
    }
    fn check_until(&self, deadline: Instant) -> Result<()> {
        before(deadline)?;
        match &self.socket {
            ManagerSocket::Selected(value) => value.revalidate()?,
            ManagerSocket::KernelFirst(value) => {
                value.check(&self.file, &self.manager.proc, &self.observer.proc)?
            }
        }
        require(
            unsafe { libc::syscall(libc::SYS_gettid) } as libc::pid_t == self.thread
                && unsafe { libc::getpid() } as u32 == self.observer.pid,
            "manager owner used outside its original process/thread",
        )?;
        let current = initial_namespaces()?;
        require(
            current.len() == self.namespaces.len(),
            "complete original manager namespaces required",
        )?;
        for (observed, original) in current.iter().zip(&self.namespaces) {
            require(
                NodeIdentity::of(observed)? == NodeIdentity::of(original)?,
                "current manager namespace changed",
            )?;
        }
        let root = open_absolute(c"/", libc::O_RDONLY | libc::O_DIRECTORY)?;
        require(
            NodeIdentity::of(&root)? == self.directory_nodes[0],
            "manager host root changed",
        )?;
        for (index, directory) in self.directories.iter().enumerate() {
            trusted_directory(directory)?;
            require(
                NodeIdentity::of(directory)? == self.directory_nodes[index],
                "held manager directory changed",
            )?;
            if index > 0 {
                let name = [c"run", c"systemd"][index - 1];
                let named = open_at(
                    &self.directories[index - 1],
                    name,
                    libc::O_RDONLY | libc::O_DIRECTORY,
                )?;
                require(
                    NodeIdentity::of(&named)? == self.directory_nodes[index],
                    "named manager directory changed",
                )?;
            }
        }
        let named = open_at(self.directories.last().unwrap(), c"private", libc::O_PATH)?;
        require(
            NodeIdentity::of(&self.file)? == self.server_node
                && NodeIdentity::of(&named)? == self.server_node
                && NodeIdentity::of(&self.socket)? == self.socket_node,
            "fixed manager socket inode changed",
        )?;
        peer_credentials(&self.socket)?;
        self.manager.check()?;
        self.observer.check()?;
        self.manager.namespaces(&self.namespaces)?;
        self.observer.namespaces(&self.namespaces)?;
        before(deadline)
    }

    pub(crate) fn manager_pidfd(&self) -> BorrowedFd<'_> {
        self.manager.pidfd.as_fd()
    }
    pub(crate) fn manager_proc(&self) -> &File {
        &self.manager.proc
    }
    pub(crate) fn observer_pidfd(&self) -> BorrowedFd<'_> {
        self.observer.pidfd.as_fd()
    }
    pub(crate) fn observer_proc(&self) -> &File {
        &self.observer.proc
    }
    pub(super) fn observer_pid(&self) -> u32 {
        self.observer.pid
    }
    /// The connected client FD is for actual SO_PEERSEC and fixed unit RPC.
    /// Its own inode label cannot stand in for the server's sock_file label.
    pub(crate) fn connection(&self) -> &File {
        &self.socket
    }
    /// The original O_PATH sock_file, independently of the connected client FD.
    /// Revalidation retains the full immutable seal, including ctime. Labeling
    /// needs a separate consumed mutation stage; no such stage is issued here.
    pub(crate) fn server_inode(&self) -> &File {
        &self.file
    }
    pub(crate) fn generation(&self) -> Result<ManagerEndpointGeneration> {
        Ok(ManagerEndpointGeneration {
            manager_start: self.manager.start,
            observer_start: self.observer.start,
            observer_pid: self.observer.pid,
            manager_executable: NodeIdentity::of(&self.manager.executable)?,
            observer_executable: NodeIdentity::of(&self.observer.executable)?,
            connection: self.socket_node,
        })
    }
}

/// Ordinary manager observations always retain the complete immutable server
/// seal. The label operation consumes this type; it never manufactures a new
/// ordinary endpoint with a changed ctime.
pub(crate) struct AuthenticatedManagerEndpoint {
    custody: EndpointCustody,
    file_seal: Metadata,
}

impl EndpointCustody {
    fn check_seal_until(&self, seal: &Metadata, deadline: Instant) -> Result<()> {
        self.check_until(deadline)?;
        let named = open_at(self.directories.last().unwrap(), c"private", libc::O_PATH)?;
        require(
            file_seal(&self.file.metadata()?) == file_seal(seal)
                && file_seal(&named.metadata()?) == file_seal(seal),
            "immutable manager server inode changed",
        )?;
        before(deadline)
    }
}

impl AuthenticatedManagerEndpoint {
    pub(crate) fn capture(issuer: HostPeerIssuer, deadline: Instant) -> Result<Self> {
        Self::from_origin(ManagerOrigin::Selected(issuer), deadline)
    }
    fn from_origin(origin: ManagerOrigin, deadline: Instant) -> Result<Self> {
        let (custody, file_seal) = EndpointCustody::capture(origin, deadline)?;
        let value = Self { custody, file_seal };
        value.revalidate_until(deadline)?;
        Ok(value)
    }
    pub(crate) fn capture_runtime(
        owner: crate::production_execution::RuntimeMacOwner,
        deadline: Instant,
    ) -> Result<Self> {
        if owner.selection().is_kernel_first() {
            let client =
                EarlyManagerClient::broker(owner).map_err(|e| CgroupError::Owner(e.to_string()))?;
            Self::from_origin(ManagerOrigin::KernelFirst(client), deadline)
        } else {
            let issuer =
                HostPeerIssuer::broker(owner).map_err(|e| CgroupError::Owner(e.to_string()))?;
            Self::capture(issuer, deadline)
        }
    }
    pub(crate) fn capture_package(owner: PackageMacOwner, deadline: Instant) -> Result<Self> {
        if owner.selection().is_kernel_first() {
            let client = EarlyManagerClient::package(owner).map_err(|error| io::Error::other(error.to_string()))?;
            return Self::from_origin(ManagerOrigin::KernelFirst(client), deadline);
        }
        let issuer =
            HostPeerIssuer::package(owner).map_err(|error| io::Error::other(error.to_string()))?;
        Self::capture(issuer, deadline)
    }
    pub(crate) fn capture_loader(owner: LoaderHostPeerOwner, deadline: Instant) -> Result<Self> {
        if owner
            .objects()
            .map_err(|e| CgroupError::Owner(e.to_string()))?
            .1
            .is_kernel_first()
        {
            let client =
                EarlyManagerClient::loader(owner).map_err(|e| CgroupError::Owner(e.to_string()))?;
            return Self::from_origin(ManagerOrigin::KernelFirst(client), deadline);
        }
        let issuer =
            HostPeerIssuer::loader(owner).map_err(|error| io::Error::other(error.to_string()))?;
        Self::capture(issuer, deadline)
    }
    pub(crate) fn revalidate_until(&self, deadline: Instant) -> Result<()> {
        self.custody.check_seal_until(&self.file_seal, deadline)
    }
    pub(crate) fn manager_pidfd(&self) -> BorrowedFd<'_> {
        self.custody.manager_pidfd()
    }
    pub(crate) fn manager_proc(&self) -> &File {
        self.custody.manager_proc()
    }
    pub(crate) fn observer_pidfd(&self) -> BorrowedFd<'_> {
        self.custody.observer_pidfd()
    }
    pub(crate) fn observer_proc(&self) -> &File {
        self.custody.observer_proc()
    }
    pub(super) fn observer_pid(&self) -> u32 {
        self.custody.observer_pid()
    }
    pub(crate) fn connection(&self) -> &File {
        self.custody.connection()
    }
    pub(crate) fn server_inode(&self) -> &File {
        self.custody.server_inode()
    }
    pub(crate) fn generation(&self) -> Result<ManagerEndpointGeneration> {
        self.custody.generation()
    }
}

/// Read-only borrow for the fixed labeler's actual MAC observation. Its only
/// constructors are the original immutable owner and the consumed label stage.
/// Neither this borrow nor a label report is accepted by the unit RPC owner.
pub(crate) struct ManagerLabelObservation<'a> {
    custody: &'a EndpointCustody,
    seal: &'a Metadata,
}
impl ManagerLabelObservation<'_> {
    pub(crate) fn manager_pidfd(&self) -> BorrowedFd<'_> {
        self.custody.manager_pidfd()
    }
    pub(crate) fn observer_pidfd(&self) -> BorrowedFd<'_> {
        self.custody.observer_pidfd()
    }

    pub(crate) fn revalidate_until(&self, deadline: Instant) -> Result<()> {
        self.custody.check_seal_until(self.seal, deadline)
    }
    pub(crate) fn manager_proc(&self) -> &File {
        &self.custody.manager.proc
    }
    pub(crate) fn observer_proc(&self) -> &File {
        &self.custody.observer.proc
    }
    pub(crate) fn manager_executable(&self) -> &File {
        &self.custody.manager.executable
    }
    pub(crate) fn observer_executable(&self) -> &File {
        &self.custody.observer.executable
    }
    pub(crate) fn connection(&self) -> &File {
        &self.custody.socket
    }
    pub(crate) fn server_inode(&self) -> &File {
        &self.custody.file
    }
    pub(crate) fn generation(&self) -> Result<ManagerEndpointGeneration> {
        self.custody.generation()
    }
}
