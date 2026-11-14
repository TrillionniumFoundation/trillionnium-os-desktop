//! Actual original host manager endpoint, independent of unit RPC or MAC authority.
//!
//! Capture has no caller-supplied PID, path, file descriptor or role. The kernel
//! peer PIDFD must identify initial-namespace root PID1; this same process holds
//! the original manager, observer, namespace, directory and server inode owners.
//! A loaded-policy observer must separately authenticate their current labels.
//! No endpoint or generation value admits Android or permits a label mutation.
use super::*;
use std::time::Instant;

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

pub(crate) struct AuthenticatedManagerEndpoint {
    socket: File,
    socket_node: NodeIdentity,
    file: File,
    file_seal: Metadata,
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
fn connect_private(directory: &File, deadline: Instant) -> Result<File> {
    let alias = format!("/proc/self/fd/{}/private", directory.as_raw_fd());
    let mut address: libc::sockaddr_un = unsafe { std::mem::zeroed() };
    require(
        alias.len() < address.sun_path.len(),
        "fixed manager socket alias too long",
    )?;
    address.sun_family = libc::AF_UNIX as libc::sa_family_t;
    for (out, byte) in address.sun_path.iter_mut().zip(alias.bytes()) {
        *out = byte as libc::c_char;
    }
    before(deadline)?;
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
    let length = (std::mem::size_of::<libc::sa_family_t>() + alias.len() + 1) as libc::socklen_t;
    if unsafe { libc::connect(fd, (&address as *const libc::sockaddr_un).cast(), length) } != 0 {
        let error = io::Error::last_os_error();
        if error.raw_os_error() != Some(libc::EINPROGRESS) {
            return Err(error.into());
        }
        loop {
            before(deadline)?;
            let left = deadline.saturating_duration_since(Instant::now());
            let millis = i32::try_from(left.as_millis().saturating_add(1))
                .map_err(|_| CgroupError::Rejected("manager connect deadline overflow"))?;
            let mut event = libc::pollfd {
                fd,
                events: libc::POLLOUT,
                revents: 0,
            };
            let rc = unsafe { libc::poll(&mut event, 1, millis) };
            if rc < 0 {
                let error = io::Error::last_os_error();
                if error.raw_os_error() == Some(libc::EINTR) {
                    continue;
                }
                return Err(error.into());
            }
            before(deadline)?;
            if rc == 0 {
                continue;
            }
            let mut error: i32 = 0;
            let mut bytes = 4 as libc::socklen_t;
            if unsafe {
                libc::getsockopt(
                    fd,
                    libc::SOL_SOCKET,
                    libc::SO_ERROR,
                    (&mut error as *mut i32).cast(),
                    &mut bytes,
                )
            } != 0
            {
                return Err(io::Error::last_os_error().into());
            }
            if error != 0 {
                return Err(io::Error::from_raw_os_error(error).into());
            }
            require(
                bytes == 4
                    && event.revents & libc::POLLOUT != 0
                    && event.revents & (libc::POLLERR | libc::POLLHUP | libc::POLLNVAL) == 0,
                "manager connection did not complete",
            )?;
            break;
        }
    }
    before(deadline)?;
    peer_credentials(&socket)?;
    Ok(socket)
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

impl AuthenticatedManagerEndpoint {
    pub(crate) fn capture(deadline: Instant) -> Result<Self> {
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
        let socket = connect_private(directories.last().unwrap(), deadline)?;
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
            file,
            file_seal,
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
        value.revalidate_until(deadline)?;
        Ok(value)
    }
    pub(crate) fn revalidate_until(&self, deadline: Instant) -> Result<()> {
        before(deadline)?;
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
            file_seal(&self.file.metadata()?) == file_seal(&self.file_seal)
                && file_seal(&named.metadata()?) == file_seal(&self.file_seal)
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
