//! Actual host systemd custody for the original production broker.
//!
//! AA label transitions clear PDEATHSIG. This provider binds the live host
//! manager, original broker PIDFD, Invocation and effective loaded unit to the
//! held production cgroup. It observes ownership; it does not authorize a MAC
//! transition, execute Android, restart a service or replace whole-tree reap.
use super::*;
use crate::production_selection::ProductionSelection;
use std::time::{Duration, Instant};

#[path = "production_unit_bus.rs"]
mod bus;
use bus::{Interface, Invocation, PrivateBus, Properties, Value};

const SO_PEERPIDFD: i32 = 77;
const PROC_MAGIC: libc::c_long = 0x9fa0;
const DEADLINE: Duration = Duration::from_secs(3);
const UNIT_OBJECT: &str = "/org/freedesktop/systemd1/unit/droidloom_2dproduction_2eservice";
const BROKER_EXECUTABLE: &str = "/usr/lib/droidloom/production/current/droidloomd";
const CAP_SETUID: u32 = 7;

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
fn before(deadline: Instant) -> Result<()> {
    if Instant::now() >= deadline {
        return Err(io::Error::from_raw_os_error(libc::ETIMEDOUT).into());
    }
    Ok(())
}
fn proc_read(directory: &File, name: &CStr) -> Result<String> {
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
fn pidfd_pid(file: &File) -> Result<u32> {
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
fn proc_start(text: &str, expected: u32) -> Result<u64> {
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

struct ManagerChannel {
    // Drop the sd-bus duplicate before the kernel identity and socket owners.
    bus: PrivateBus,
    socket: File,
    socket_node: NodeIdentity,
    file: File,
    file_seal: Metadata,
    directories: Vec<File>,
    directory_nodes: Vec<NodeIdentity>,
    manager: Task,
    broker: Task,
    namespaces: Vec<File>,
    thread: libc::pid_t,
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

impl ManagerChannel {
    fn open(deadline: Instant) -> Result<Self> {
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
        let broker = Task::capture(unsafe { File::from_raw_fd(descriptor as i32) }, pid as u32)?;
        manager.namespaces(&namespaces)?;
        broker.namespaces(&namespaces)?;
        let bus = PrivateBus::from_authenticated_socket(&socket, deadline)?;
        let value = Self {
            bus,
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
            broker,
            namespaces,
            thread: unsafe { libc::syscall(libc::SYS_gettid) } as libc::pid_t,
        };
        value.check()?;
        before(deadline)?;
        Ok(value)
    }
    fn check(&self) -> Result<()> {
        require(
            unsafe { libc::syscall(libc::SYS_gettid) } as libc::pid_t == self.thread
                && unsafe { libc::getpid() } as u32 == self.broker.pid,
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
        self.broker.check()?;
        self.manager.namespaces(&self.namespaces)?;
        self.broker.namespaces(&self.namespaces)
    }
}

fn property<'a>(properties: &'a Properties, name: &str) -> Result<&'a Value> {
    properties.get(name).ok_or(CgroupError::Rejected(
        "required effective unit property is absent",
    ))
}
fn equal(properties: &Properties, name: &str, expected: Value) -> Result<()> {
    require(
        property(properties, name)? == &expected,
        "effective loaded unit differs from fixed contract",
    )
}
fn nonzero_time(properties: &Properties, name: &str) -> Result<()> {
    require(
        matches!(property(properties, name)?, Value::U64(value) if *value > 0),
        "actual running unit generation timestamp required",
    )
}

fn validate_configuration(
    invocation: &Invocation,
    unit: &Properties,
    service: &Properties,
    broker: u32,
    cgroup: u64,
) -> Result<()> {
    require(
        invocation.unit == UNIT && invocation.path == UNIT_OBJECT,
        "original broker belongs to another systemd unit",
    )?;
    for (name, value) in [
        ("Id", UNIT),
        ("LoadState", "loaded"),
        ("ActiveState", "active"),
        ("SubState", "running"),
        (
            "FragmentPath",
            "/etc/systemd/system/droidloom-production.service",
        ),
        ("SourcePath", ""),
    ] {
        equal(unit, name, Value::Text(value.into()))?;
    }
    for name in ["Transient", "NeedDaemonReload"] {
        equal(unit, name, Value::Boolean(false))?;
    }
    equal(unit, "DropInPaths", Value::Strings(Vec::new()))?;
    equal(unit, "Job", Value::Job(0, "/".into()))?;
    equal(unit, "InvocationID", Value::Bytes(invocation.id.to_vec()))?;
    nonzero_time(unit, "StateChangeTimestampMonotonic")?;
    for (name, value) in [
        ("Type", "exec"),
        ("ExitType", "main"),
        ("Restart", "no"),
        ("KillMode", "control-group"),
        ("TimeoutStopFailureMode", "terminate"),
        ("User", "root"),
        ("Group", "root"),
        ("DelegateSubgroup", "broker"),
        ("ControlGroup", UNIT_CGROUP),
        ("Slice", "system.slice"),
        ("RootDirectory", ""),
        ("RootImage", ""),
        ("WorkingDirectory", "/"),
    ] {
        equal(service, name, Value::Text(value.into()))?;
    }
    for (name, value) in [
        ("RemainAfterExit", false),
        ("SendSIGKILL", true),
        ("SendSIGHUP", false),
        ("NoNewPrivileges", true),
        ("PrivateMounts", true),
        ("Delegate", true),
        ("DynamicUser", false),
    ] {
        equal(service, name, Value::Boolean(value))?;
    }
    for (name, value) in [
        ("MainPID", broker),
        ("ExecMainPID", broker),
        ("ControlPID", 0),
        ("NRestarts", 0),
        ("UMask", 0o077),
    ] {
        equal(service, name, Value::U32(value))?;
    }
    for (name, value) in [
        ("KillSignal", libc::SIGTERM),
        ("RestartKillSignal", libc::SIGTERM),
        ("FinalKillSignal", libc::SIGKILL),
        ("ExecMainCode", 0),
        ("ExecMainStatus", 0),
    ] {
        equal(service, name, Value::I32(value))?;
    }
    for (name, value) in [
        ("TimeoutStopUSec", 30_000_000),
        ("ExecMainExitTimestampMonotonic", 0),
        ("ControlGroupId", cgroup),
        ("MemoryMax", MEMORY_MAX),
        ("MemoryHigh", MEMORY_HIGH),
        ("MemorySwapMax", 0),
        ("TasksMax", PIDS_MAX),
        ("CPUQuotaPerSecUSec", 6_000_000),
        ("CPUQuotaPeriodUSec", 100_000),
        ("AmbientCapabilities", 1 << CAP_SETUID),
    ] {
        equal(service, name, Value::U64(value))?;
    }
    nonzero_time(service, "ExecMainStartTimestampMonotonic")?;
    equal(
        service,
        "AppArmorProfile",
        Value::Profile(false, "droidloom-production-broker".into()),
    )?;
    match property(service, "DelegateControllers")? {
        Value::Strings(values) => {
            let actual: BTreeSet<_> = values.iter().map(String::as_str).collect();
            require(
                values.len() == 4 && actual == REQUIRED_CONTROLLERS.into_iter().collect(),
                "effective manager delegation differs from fixed four controllers",
            )?;
        }
        _ => {
            return Err(CgroupError::Rejected(
                "effective manager delegation is not a string array",
            ));
        }
    }
    for name in [
        "ExecConditionEx",
        "ExecStartPreEx",
        "ExecStartPostEx",
        "ExecReloadEx",
        "ExecStopEx",
        "ExecStopPostEx",
    ] {
        equal(service, name, Value::Commands(Vec::new()))?;
    }
    match property(service, "ExecStartEx")? {
        Value::Commands(commands) if commands.len() == 1 => {
            let command = &commands[0];
            require(
                command.path == BROKER_EXECUTABLE
                    && command.arguments
                        == [BROKER_EXECUTABLE, "--socket", "/run/droidloom/control.sock"]
                    && command.flags.is_empty()
                    && command.pid == broker
                    && command.started.iter().all(|value| *value > 0)
                    && command.exited == [0, 0]
                    && command.code == 0
                    && command.status == 0,
                "actual original broker ExecStart differs",
            )?;
        }
        _ => {
            return Err(CgroupError::Rejected(
                "exactly one original broker ExecStart is required",
            ));
        }
    }
    Ok(())
}

#[derive(Eq, PartialEq)]
struct Snapshot {
    invocation: Invocation,
    unit: Properties,
    service: Properties,
}

/// The actual manager, original broker and held fixed cgroup issue this
/// observation. It is not a MAC, signal or Android readiness capability.
pub(super) struct EffectiveUnit {
    channel: ManagerChannel,
    cgroup: File,
    cgroup_node: NodeIdentity,
    original: Snapshot,
}

impl EffectiveUnit {
    fn snapshot(channel: &ManagerChannel, cgroup: &File, deadline: Instant) -> Result<Snapshot> {
        before(deadline)?;
        channel.check()?;
        trusted_directory(cgroup)?;
        cgroup_filesystem(cgroup)?;
        require(
            parse_unified_cgroup(&proc_read(&channel.broker.proc, c"cgroup")?)?
                == format!("{UNIT_CGROUP}/broker"),
            "original broker left the fixed manager subgroup",
        )?;
        let invocation = channel
            .bus
            .invocation(channel.broker.pidfd.as_fd(), deadline)?;
        require(
            invocation.unit == UNIT && invocation.path == UNIT_OBJECT,
            "original broker manager owner is not the fixed production unit",
        )?;
        let unit = channel
            .bus
            .properties(&invocation, Interface::Unit, deadline)?;
        let service = channel
            .bus
            .properties(&invocation, Interface::Service, deadline)?;
        validate_configuration(
            &invocation,
            &unit,
            &service,
            channel.broker.pid,
            cgroup.metadata()?.ino(),
        )?;
        require(
            channel
                .bus
                .invocation(channel.broker.pidfd.as_fd(), deadline)?
                == invocation,
            "manager invocation changed during effective unit observation",
        )?;
        channel.check()?;
        before(deadline)?;
        Ok(Snapshot {
            invocation,
            unit,
            service,
        })
    }

    pub(super) fn open(cgroup: &File) -> Result<Self> {
        let deadline = Instant::now() + DEADLINE;
        let channel = ManagerChannel::open(deadline)?;
        let original = Self::snapshot(&channel, cgroup, deadline)?;
        let value = Self {
            channel,
            cgroup: cgroup.try_clone()?,
            cgroup_node: NodeIdentity::of(cgroup)?,
            original,
        };
        value.check_until(cgroup, deadline)?;
        Ok(value)
    }

    fn check_until(&self, cgroup: &File, deadline: Instant) -> Result<()> {
        before(deadline)?;
        require(
            NodeIdentity::of(cgroup)? == self.cgroup_node
                && NodeIdentity::of(&self.cgroup)? == self.cgroup_node,
            "effective manager cgroup custody changed",
        )?;
        let current = Self::snapshot(&self.channel, &self.cgroup, deadline)?;
        require(
            current == self.original,
            "original manager generation or effective unit changed",
        )?;
        before(deadline)
    }

    pub(super) fn check(&self, cgroup: &File) -> Result<()> {
        self.check_until(cgroup, Instant::now() + DEADLINE)
    }
}

/// Identity is copied only from the live provider; fields have no public
/// constructor and cannot be restored from a report or configuration file.
#[derive(Clone, Eq, PartialEq)]
pub(crate) struct SystemdOwnerGeneration {
    invocation: [u8; 16],
    manager_start: u64,
    broker_start: u64,
    broker_pid: u32,
    manager_executable: NodeIdentity,
    broker_executable: NodeIdentity,
    connection: NodeIdentity,
    cgroup: NodeIdentity,
}

/// Read-only borrow of an already admitted owned hierarchy. The MAC provider
/// still has to observe actual manager and broker domains, socket labels and
/// precise signal/FD permissions under its current loaded policy epoch.
pub(crate) struct SystemdOwnerWitness<'a> {
    owner: &'a PreparedCgroup,
    selection: &'a ProductionSelection,
}

impl PreparedCgroup {
    pub(crate) fn systemd_owner<'a>(
        &'a self,
        selection: &'a ProductionSelection,
    ) -> Result<SystemdOwnerWitness<'a>> {
        let witness = SystemdOwnerWitness {
            owner: self,
            selection,
        };
        witness.revalidate()?;
        Ok(witness)
    }
}

impl SystemdOwnerWitness<'_> {
    fn effective(&self) -> &EffectiveUnit {
        &self.owner.get().unit_authority.effective
    }
    pub(crate) fn revalidate(&self) -> Result<()> {
        self.owner.revalidate()?;
        self.selection
            .revalidate()
            .map_err(|e| CgroupError::Owner(e.to_string()))?;
        let lease = self.owner.admission().lease();
        require(
            lease.host_uid() == self.selection.spec().host_uid
                && lease.broker_cohort() == self.selection.base_cohort(),
            "systemd owner belongs to another production selection",
        )
    }
    pub(crate) fn selection(&self) -> &ProductionSelection {
        self.selection
    }
    pub(crate) fn manager_pidfd(&self) -> BorrowedFd<'_> {
        self.effective().channel.manager.pidfd.as_fd()
    }
    pub(crate) fn manager_proc(&self) -> &File {
        &self.effective().channel.manager.proc
    }
    pub(crate) fn broker_pidfd(&self) -> BorrowedFd<'_> {
        self.effective().channel.broker.pidfd.as_fd()
    }
    pub(crate) fn broker_proc(&self) -> &File {
        &self.effective().channel.broker.proc
    }
    /// This is the client end. Use SO_PEERSEC to observe the actual manager;
    /// its own fgetxattr is not evidence for the server's socket domain.
    pub(crate) fn manager_connection(&self) -> &File {
        &self.effective().channel.socket
    }
    pub(crate) fn manager_socket_file(&self) -> &File {
        &self.effective().channel.file
    }
    pub(crate) fn generation(&self) -> Result<SystemdOwnerGeneration> {
        self.revalidate()?;
        let effective = self.effective();
        Ok(SystemdOwnerGeneration {
            invocation: effective.original.invocation.id,
            manager_start: effective.channel.manager.start,
            broker_start: effective.channel.broker.start,
            broker_pid: effective.channel.broker.pid,
            manager_executable: NodeIdentity::of(&effective.channel.manager.executable)?,
            broker_executable: NodeIdentity::of(&effective.channel.broker.executable)?,
            connection: effective.channel.socket_node,
            cgroup: effective.cgroup_node,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn kernel_process_generation_is_not_a_numeric_pid_claim() {
        let actual = std::fs::read_to_string("/proc/self/stat").unwrap();
        let pid = unsafe { libc::getpid() } as u32;
        assert!(proc_start(&actual, pid).unwrap() > 0);
        assert!(matches!(
            proc_start(&actual, pid + 1),
            Err(CgroupError::Rejected("held process PID changed"))
        ));
        assert!(matches!(
            proc_start(&format!("{pid} (a name with ) parens) S 1"), pid),
            Err(CgroupError::Rejected("short held process stat"))
        ));
        let regular = tempfile::tempfile().unwrap();
        assert!(matches!(
            pidfd_pid(&regular),
            Err(CgroupError::Rejected(
                "service owner PIDFD is not bound in the initial PID namespace"
            ))
        ));
    }

    #[test]
    #[ignore = "requires an initial-root sealed ELF in its own native systemd fixture unit"]
    fn actual_private_manager_original_pidfd_observation() {
        let deadline = Instant::now() + DEADLINE;
        let channel = ManagerChannel::open(deadline).expect("actual authenticated host manager");
        let invocation = channel
            .bus
            .invocation(channel.broker.pidfd.as_fd(), deadline)
            .unwrap();
        assert_eq!(
            invocation.unit,
            std::env::var("DROIDLOOM_SYSTEMD_FIXTURE_UNIT").unwrap()
        );
        let hex: String = invocation.id.iter().map(|b| format!("{b:02x}")).collect();
        assert_eq!(hex, std::env::var("INVOCATION_ID").unwrap());
        let unit = channel
            .bus
            .properties(&invocation, Interface::Unit, deadline)
            .unwrap();
        let service = channel
            .bus
            .properties(&invocation, Interface::Service, deadline)
            .unwrap();
        assert_eq!(
            property(&unit, "Id").unwrap(),
            &Value::Text(invocation.unit.clone())
        );
        assert_eq!(
            property(&unit, "InvocationID").unwrap(),
            &Value::Bytes(invocation.id.to_vec())
        );
        assert_eq!(
            property(&service, "MainPID").unwrap(),
            &Value::U32(channel.broker.pid)
        );
        assert_eq!(
            property(&service, "ExecMainPID").unwrap(),
            &Value::U32(channel.broker.pid)
        );
        let own =
            parse_unified_cgroup(&proc_read(&channel.broker.proc, c"cgroup").unwrap()).unwrap();
        assert_eq!(
            property(&service, "ControlGroup").unwrap(),
            &Value::Text(own)
        );
        assert_eq!(
            channel
                .bus
                .invocation(channel.broker.pidfd.as_fd(), deadline)
                .unwrap(),
            invocation
        );
        channel.check().unwrap();
        before(deadline).unwrap();
        // A real transient fixture must never issue the fixed production
        // observation, even though its original manager and PIDFD are valid.
        assert!(matches!(
            validate_configuration(&invocation, &unit, &service, channel.broker.pid, 0),
            Err(CgroupError::Rejected(
                "original broker belongs to another systemd unit"
            ))
        ));
        eprintln!(
            "actual private manager: invocation={invocation:?}; unit={unit:?}; service={service:?}"
        );
    }
}
