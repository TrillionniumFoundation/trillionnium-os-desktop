//! Proof emitted only by the authenticated boot-born factory query client.
//! Field visibility deliberately prevents a caller or deserializer from
//! constructing an observed TRACEEXEC event. The factory remains the actual
//! creating thread, ptracer and final waitid owner of every query child.

/// The same direct child at its actual factory-owned PTRACE_EVENT_EXEC stop.
pub(crate) struct FactoryExecStop {
    pid: u32,
    tracer_tid: u32,
    waitid_code: i32,
    waitid_status: i32,
    event_previous_tid: u64,
}
impl FactoryExecStop {
    pub(crate) fn pid(&self) -> u32 {
        self.pid
    }
    pub(crate) fn tracer_tid(&self) -> u32 {
        self.tracer_tid
    }
    pub(crate) fn waitid_code(&self) -> i32 {
        self.waitid_code
    }
    pub(crate) fn waitid_status(&self) -> i32 {
        self.waitid_status
    }
    pub(crate) fn event_previous_tid(&self) -> u64 {
        self.event_previous_tid
    }
}

use super::protocol::{self, Message};
use super::*;
use std::mem;
use std::os::fd::{AsRawFd, FromRawFd, RawFd};
use std::os::unix::fs::OpenOptionsExt;
use std::time::{Duration, Instant};

pub(crate) const QUERY_SELINUX: &str = "u:r:droidloom_query:s0";
pub(crate) const QUERY_APPARMOR: &str = "droidloom-production-android (enforce)";
const STDIN: usize = 12;
const STDOUT: usize = 13;
const STDERR: usize = 14;
const EXEC_EVENT: i32 = libc::SIGTRAP | (libc::PTRACE_EVENT_EXEC << 8);
const CGROUP_PATH: &str =
    "/sys/fs/cgroup/system.slice/droidloom-production.service/cell-u1000/application-read";

/// Source-owned original generation, supplied only by the authenticated
/// factory service loop. None of these capabilities comes from a wire receipt.
pub(crate) struct FactoryAuthority<'a> {
    pub(crate) init: &'a File,
    pub(crate) owner: &'a File,
    pub(crate) pid_namespace: &'a File,
    pub(crate) mount_namespace: &'a File,
    pub(crate) user_namespace: &'a File,
    pub(crate) root_uid: u32,
    pub(crate) root_gid: u32,
    pub(crate) validate: &'a dyn Fn() -> io::Result<()>,
}
impl FactoryAuthority<'_> {
    fn check(&self) -> Result<()> {
        (self.validate)()?;
        require(
            live(self.init)? && live(self.owner)?,
            "original factory generation exited",
        )
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
pub(super) struct Terminal {
    pub(super) code: i32,
    pub(super) status: i32,
}
impl Terminal {
    fn valid(self) -> bool {
        match self.code {
            libc::CLD_EXITED => (0..=255).contains(&self.status),
            libc::CLD_KILLED | libc::CLD_DUMPED => (1..=64).contains(&self.status),
            _ => false,
        }
    }
    pub(super) fn success(self) -> bool {
        self == Self {
            code: libc::CLD_EXITED,
            status: 0,
        }
    }
}
#[repr(C)]
#[derive(Default)]
struct PidInfo {
    mask: u64,
    cgroupid: u64,
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
    coredump_mask: u32,
    coredump_signal: u32,
    supported_mask: u64,
}
const _: () = assert!(mem::size_of::<PidInfo>() == 80);
fn info(file: &File) -> Result<PidInfo> {
    let mut value = PidInfo {
        mask: 3,
        ..PidInfo::default()
    };
    if unsafe { libc::ioctl(file.as_raw_fd(), 0xc050_ff0b_u64, &mut value) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        value.mask & 3 == 3 && value.pid > 1 && value.pid == value.tgid,
        "factory query pidfd identity is incomplete",
    )?;
    Ok(value)
}
fn identity(file: &File) -> Result<(u64, u64)> {
    let m = file.metadata()?;
    Ok((m.dev(), m.ino()))
}
fn fs(file: &File, expected: libc::c_long) -> Result<()> {
    let mut value: libc::statfs = unsafe { mem::zeroed() };
    if unsafe { libc::fstatfs(file.as_raw_fd(), &mut value) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        value.f_type == expected,
        "factory query kernel object filesystem differs",
    )
}
fn live(file: &File) -> Result<bool> {
    fs(file, 0x50494446)?;
    let mut p = libc::pollfd {
        fd: file.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    loop {
        let n = unsafe { libc::poll(&mut p, 1, 0) };
        if n < 0 {
            let error = io::Error::last_os_error();
            if error.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(error.into());
        }
        require(
            p.revents & (libc::POLLERR | libc::POLLNVAL) == 0,
            "factory query PIDFD is invalid",
        )?;
        return Ok(n == 0);
    }
}
fn pidfd(pid: u32) -> Result<File> {
    require(pid > 1, "factory authenticated process number is invalid")?;
    let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, pid, 0) };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let result = unsafe { File::from_raw_fd(raw as i32) };
    fs(&result, 0x50494446)?;
    Ok(result)
}
fn mount_id(file: &File) -> Result<u64> {
    let mut st: libc::statx = unsafe { mem::zeroed() };
    if unsafe {
        libc::statx(
            file.as_raw_fd(),
            c"".as_ptr(),
            libc::AT_EMPTY_PATH | libc::AT_SYMLINK_NOFOLLOW,
            libc::STATX_MNT_ID,
            &mut st,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    require(
        st.stx_mask & libc::STATX_MNT_ID != 0 && st.stx_mnt_id > 0,
        "factory borrowed file mount identity is absent",
    )?;
    Ok(st.stx_mnt_id)
}
fn reopen(file: &File, path_only: bool) -> Result<File> {
    let before = identity(file)?;
    let mount = mount_id(file)?;
    let result = std::fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_CLOEXEC | if path_only { libc::O_PATH } else { 0 })
        .open(format!("/proc/self/fd/{}", file.as_raw_fd()))?;
    require(
        identity(&result)? == before && mount_id(&result)? == mount,
        "factory reopen changed borrowed kernel object identity",
    )?;
    Ok(result)
}
fn credentials(socket: &File) -> Result<libc::ucred> {
    let mut value: libc::ucred = unsafe { mem::zeroed() };
    let mut size = mem::size_of_val(&value) as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            socket.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERCRED,
            (&mut value as *mut libc::ucred).cast(),
            &mut size,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    require(
        size as usize == mem::size_of_val(&value)
            && value.pid > 1
            && value.uid == 0
            && value.gid == 0,
        "factory query channel peer is not original host-root",
    )?;
    Ok(value)
}
fn pass_credentials(socket: &File) -> Result<()> {
    let enabled = 1_i32;
    if unsafe {
        libc::setsockopt(
            socket.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PASSCRED,
            (&enabled as *const i32).cast(),
            mem::size_of_val(&enabled) as libc::socklen_t,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    Ok(())
}
fn readable(fd: RawFd, deadline: Instant) -> Result<bool> {
    require(Instant::now() < deadline, "factory query absolute deadline")?;
    let mut p = libc::pollfd {
        fd,
        events: libc::POLLIN,
        revents: 0,
    };
    let n = unsafe { libc::poll(&mut p, 1, 0) };
    if n < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        p.revents & libc::POLLNVAL == 0,
        "factory query channel is invalid",
    )?;
    Ok(n > 0)
}
fn pause(fds: &[RawFd], deadline: Instant) -> Result<()> {
    let left = deadline.saturating_duration_since(Instant::now());
    require(!left.is_zero(), "factory query absolute deadline")?;
    let mut values: Vec<_> = fds
        .iter()
        .map(|fd| libc::pollfd {
            fd: *fd,
            events: libc::POLLIN,
            revents: 0,
        })
        .collect();
    let n = unsafe {
        libc::poll(
            values.as_mut_ptr(),
            values.len() as libc::nfds_t,
            left.as_millis().clamp(1, 20) as i32,
        )
    };
    if n < 0 && io::Error::last_os_error().kind() != io::ErrorKind::Interrupted {
        return Err(io::Error::last_os_error().into());
    }
    require(
        values.iter().all(|p| p.revents & libc::POLLNVAL == 0),
        "factory query descriptor became invalid",
    )
}
fn pipe_label(file: &File) -> Result<()> {
    let mut label = [0u8; 128];
    let n = unsafe {
        libc::fgetxattr(
            file.as_raw_fd(),
            c"security.selinux".as_ptr(),
            label.as_mut_ptr().cast(),
            label.len(),
        )
    };
    if n < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let actual = &label[..n as usize];
    require(
        actual.strip_suffix(&[0]).unwrap_or(actual) == b"u:r:droidloom_query_io:s0",
        "query stream inode did not come from the isolated I/O role",
    )
}
struct Prepared {
    files: Vec<File>,
    cgroup: File,
}
fn prepare(
    files: Vec<File>,
    query: &ApplicationOperation,
    authority: &FactoryAuthority<'_>,
    deadline: Instant,
) -> Result<Prepared> {
    query.validate()?;
    require(
        files.len() == query.descriptor_count() + 1,
        "factory query descriptor layout differs",
    )?;
    authority.check()?;
    let original = info(authority.init)?;
    let owner = info(authority.owner)?;
    require(
        identity(&files[0])? == identity(authority.init)?
            && identity(&files[1])? == identity(authority.owner)?
            && original.ppid == unsafe { libc::getpid() } as u32
            && original.ruid == authority.root_uid
            && original.rgid == authority.root_gid
            && owner.ruid == 0
            && owner.rgid == 0,
        "factory query does not belong to its original Android/resource owner",
    )?;
    require(
        identity(&files[3])? == identity(authority.user_namespace)?
            && identity(&files[5])? == identity(authority.pid_namespace)?,
        "query changed the original Android user/PID namespace",
    )?;
    // Android init may legitimately create its final mount/cgroup namespace.
    // The authenticated fixed owner supplied the current seven metadata pins;
    // all remain in the immutable original user namespace. The broker repeats
    // exact final root+seven-namespace equality at the actual exec stop.
    let _original_mount = identity(authority.mount_namespace)?;
    for (index, kind) in [
        (3, libc::CLONE_NEWUSER),
        (4, libc::CLONE_NEWNS),
        (5, libc::CLONE_NEWPID),
        (6, libc::CLONE_NEWIPC),
        (7, libc::CLONE_NEWUTS),
        (8, libc::CLONE_NEWNET),
        (9, libc::CLONE_NEWCGROUP),
    ] {
        fs(&files[index], 0x6e736673)?;
        require(
            unsafe { libc::ioctl(files[index].as_raw_fd(), 0xb703_u64) } == kind,
            "factory query namespace type differs",
        )?;
        if index != 3 {
            let raw = unsafe { libc::ioctl(files[index].as_raw_fd(), 0xb701_u64) };
            if raw < 0 {
                return Err(io::Error::last_os_error().into());
            }
            let user = unsafe { File::from_raw_fd(raw) };
            require(
                identity(&user)? == identity(authority.user_namespace)?,
                "query namespace has another user namespace owner",
            )?;
        }
    }
    require(
        files[2].metadata()?.is_dir(),
        "query root is not a directory",
    )?;
    for index in [STDOUT, STDERR] {
        let m = files[index].metadata()?;
        require(
            m.mode() & libc::S_IFMT == libc::S_IFIFO,
            "query output is not a pipe",
        )?;
        require(
            unsafe { libc::fcntl(files[index].as_raw_fd(), libc::F_GETFL) } & libc::O_ACCMODE
                == libc::O_WRONLY,
            "query output pipe is not write-only",
        )?;
        pipe_label(&files[index])?;
    }
    require(
        identity(&files[STDOUT])? != identity(&files[STDERR])?,
        "query stdout and stderr alias",
    )?;
    let input = files[STDIN].metadata()?;
    let flags = unsafe { libc::fcntl(files[STDIN].as_raw_fd(), libc::F_GETFL) };
    require(
        flags >= 0 && flags & (libc::O_ACCMODE | libc::O_NONBLOCK | libc::O_PATH) == libc::O_RDONLY,
        "query stdin is not a blocking readonly stream",
    )?;
    if query.install_input_bytes().is_some() {
        fs(&files[STDIN], 0x5049_5045)?;
        require(
            input.mode() & libc::S_IFMT == libc::S_IFIFO
                && identity(&files[STDIN])? != identity(&files[STDOUT])?
                && identity(&files[STDIN])? != identity(&files[STDERR])?,
            "install stdin is not its distinct creator-origin pipe",
        )?;
        pipe_label(&files[STDIN])?;
    } else {
        require(
            input.mode() & libc::S_IFMT == libc::S_IFCHR && input.rdev() == libc::makedev(1, 3),
            "query stdin is not the held guest null stream",
        )?;
    }
    // Null's inode label is not evidence of file-description origin. Its
    // QueryIo provenance is retained through the original SCM file description;
    // the unchanged Android->broker/metadata FD-use guards still apply.
    let cgroup = std::fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW)
        .open(CGROUP_PATH)?;
    fs(&cgroup, 0x63677270)?;
    let meta = cgroup.metadata()?;
    require(
        identity(&files[query.descriptor_count()])? == identity(&cgroup)?
            && meta.uid() == 0
            && meta.gid() == 0
            && meta.mode() & 0o7777 == 0o700,
        "query cgroup is not the fixed original broker leaf",
    )?;
    for (name, expected) in [
        ("cgroup.type", "domain"),
        ("cgroup.subtree_control", ""),
        ("cgroup.procs", ""),
        ("memory.max", "536870912"),
        ("memory.high", "402653184"),
        ("memory.swap.max", "0"),
        ("pids.max", "64"),
        ("cpu.max", "100000 100000"),
    ] {
        let path = CString::new(name).map_err(external)?;
        let fd = unsafe {
            libc::openat(
                cgroup.as_raw_fd(),
                path.as_ptr(),
                libc::O_RDONLY | libc::O_CLOEXEC | libc::O_NOFOLLOW,
            )
        };
        if fd < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let mut body = String::new();
        use std::io::Read;
        unsafe { File::from_raw_fd(fd) }
            .take(4096)
            .read_to_string(&mut body)?;
        require(
            body.trim_end_matches('\n') == expected,
            "query cgroup limit or occupancy differs",
        )?;
    }
    // Reopen root and namespace descriptions in kernel context. Dup would
    // preserve a broker/metadata f_sid and is deliberately insufficient.
    let mut owned = Vec::with_capacity(query.descriptor_count());
    owned.push(authority.init.try_clone()?);
    owned.push(authority.owner.try_clone()?);
    owned.push(reopen(&files[2], true)?);
    for file in &files[3..10] {
        owned.push(reopen(file, false)?);
    }
    owned.push(reopen(&files[10], false)?);
    owned.push(reopen(&files[11], false)?);
    owned.push(files[STDIN].try_clone()?);
    owned.push(files[STDOUT].try_clone()?);
    owned.push(files[STDERR].try_clone()?);
    if query.needs_content_jar() {
        for index in [protocol::CONTENT_JAR, protocol::ORIGINAL_CONTENT_JAR] {
            owned.push(reopen(&files[index], false)?);
        }
    }
    require(
        owned.len() == query.descriptor_count(),
        "fixed operation input shape differs",
    )?;
    // Reopen only the source-owned executable and optional Contacts JAR paths;
    // compare both complete immutable bodies with their original system inputs.
    super::worker::executable::verify(
        &owned,
        query,
        QueryProjection::EarlyDev,
        authority.root_uid,
        authority.root_gid,
        deadline,
    )?;
    authority.check()?;
    Ok(Prepared {
        files: owned,
        cgroup,
    })
}

#[repr(C)]
struct NativeQuery {
    files: [i32; 15],
    pid_namespace: i32,
    cgroup: i32,
    domain: u32,
    deadline_ns: u64,
    argv: *const *const libc::c_char,
    envp: *const *const libc::c_char,
    filter: *const libc::sock_fprog,
}
// This number never comes from the request wire. The validated closed operation
// selects the native stub's literal SELinux exec context.
fn native_domain(domain: OperationDomain) -> u32 {
    match domain {
        OperationDomain::Query => 0,
        OperationDomain::Browser => 1,
        OperationDomain::ContactsRead => 2,
        OperationDomain::LaunchRead => 3,
        OperationDomain::LaunchStart => 4,
        OperationDomain::Install => 5,
        OperationDomain::CatalogRead => 6,
    }
}
unsafe extern "C" {
    fn droidloom_factory_spawn_query(
        query: *const NativeQuery,
        pid: *mut i32,
        pidfd: *mut i32,
    ) -> i32;
}
/// This is the only query wait owner. Construction consumes the atomic clone3
/// PIDFD produced by this exact factory thread; no wire data constructs it.
struct OwnedQuery {
    pid: u32,
    pidfd: File,
    creator: libc::pid_t,
    terminal: Option<Terminal>,
    stopped: bool,
    released: bool,
}
impl OwnedQuery {
    fn thread(&self) -> Result<()> {
        require(
            unsafe { libc::syscall(libc::SYS_gettid) } == self.creator as libc::c_long,
            "query wait owner changed its original single factory thread",
        )
    }
    fn original(&self) -> Result<()> {
        self.thread()?;
        require(self.terminal.is_none(), "query already has a terminal wait")?;
        let info = info(&self.pidfd)?;
        require(
            info.pid == self.pid && info.ppid == unsafe { libc::getpid() } as u32,
            "factory query is no longer the original direct child",
        )
    }
    fn wait(&self, flags: i32) -> Result<Option<(i32, i32)>> {
        self.thread()?;
        let mut value: libc::siginfo_t = unsafe { mem::zeroed() };
        if unsafe {
            libc::waitid(
                libc::P_PIDFD,
                self.pidfd.as_raw_fd() as u32,
                &mut value,
                flags | libc::WNOHANG,
            )
        } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
        let pid = unsafe { value.si_pid() };
        if pid == 0 {
            return Ok(None);
        }
        require(
            pid == self.pid as i32,
            "factory waitid returned a different child",
        )?;
        Ok(Some((value.si_code, unsafe { value.si_status() })))
    }
    fn terminal(&mut self) -> Result<Option<Terminal>> {
        if let Some(value) = self.terminal {
            return Ok(Some(value));
        }
        if let Some((code, status)) = self.wait(libc::WEXITED | libc::WNOWAIT)? {
            let value = Terminal { code, status };
            require(value.valid(), "factory query terminal state is invalid")?;
            require(
                self.wait(libc::WEXITED)? == Some((code, status)),
                "query terminal changed during actual factory reap",
            )?;
            self.terminal = Some(value);
        }
        Ok(self.terminal)
    }
    fn seize(&self) -> Result<()> {
        self.original()?;
        let options = libc::PTRACE_O_TRACEEXEC | libc::PTRACE_O_EXITKILL;
        if unsafe {
            libc::ptrace(
                libc::PTRACE_SEIZE,
                self.pid as i32,
                std::ptr::null_mut::<libc::c_void>(),
                options as usize as *mut libc::c_void,
            )
        } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
        Ok(())
    }
    fn exec_stop(&mut self, authority: &FactoryAuthority<'_>, deadline: Instant) -> Result<u64> {
        require(!self.stopped, "factory exec stop was already consumed")?;
        loop {
            authority.check()?;
            self.original()?;
            if let Some(event) = self.wait(libc::WSTOPPED | libc::WNOWAIT)? {
                require(
                    event == (libc::CLD_TRAPPED, EXEC_EVENT)
                        && self.wait(libc::WSTOPPED)? == Some(event),
                    "query did not reach the actual kernel TRACEEXEC event",
                )?;
                let mut previous: libc::c_ulong = 0;
                if unsafe {
                    libc::ptrace(
                        libc::PTRACE_GETEVENTMSG,
                        self.pid as i32,
                        std::ptr::null_mut::<libc::c_void>(),
                        (&mut previous as *mut libc::c_ulong).cast::<libc::c_void>(),
                    )
                } != 0
                {
                    return Err(io::Error::last_os_error().into());
                }
                require(
                    previous == self.pid as u64,
                    "query exec changed the original task",
                )?;
                self.stopped = true;
                require(
                    self.terminal()?.is_none(),
                    "query already exited at exec stop",
                )?;
                return Ok(previous);
            }
            require(
                self.terminal()?.is_none(),
                "query exited before its exec stop",
            )?;
            pause(&[self.pidfd.as_raw_fd()], deadline)?;
        }
    }
    fn release(&mut self) -> Result<()> {
        self.original()?;
        require(
            self.stopped && !self.released,
            "query is not at its unreleased original exec stop",
        )?;
        if unsafe {
            libc::ptrace(
                libc::PTRACE_CONT,
                self.pid as i32,
                std::ptr::null_mut::<libc::c_void>(),
                std::ptr::null_mut::<libc::c_void>(),
            )
        } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
        self.released = true;
        Ok(())
    }
    fn retire(&mut self, deadline: Instant) -> Result<Terminal> {
        if let Some(value) = self.terminal()? {
            return Ok(value);
        }
        self.original()?;
        if unsafe {
            libc::syscall(
                libc::SYS_pidfd_send_signal,
                self.pidfd.as_raw_fd(),
                libc::SIGKILL,
                std::ptr::null::<libc::siginfo_t>(),
                0_u32,
            )
        } != 0
            && io::Error::last_os_error().raw_os_error() != Some(libc::ESRCH)
        {
            return Err(ApplicationError::RetirementUnproven);
        }
        loop {
            if let Some(value) = self.terminal()? {
                return Ok(value);
            }
            pause(&[self.pidfd.as_raw_fd()], deadline)?;
        }
    }
}
impl Drop for OwnedQuery {
    fn drop(&mut self) {
        if self.terminal.is_none() {
            // Successful dispatch never reaches this fallback. A failed query
            // is killed and genuinely reaped; it never becomes a success.
            if self.retire(Instant::now() + RETIRE_LIMIT).is_err() {
                if let Ok(held) = self.pidfd.try_clone() {
                    mem::forget(held);
                }
            }
        }
    }
}
fn spawn(
    prepared: &Prepared,
    query: &ApplicationOperation,
    deadline_ns: u64,
) -> Result<(OwnedQuery, File)> {
    super::worker::require_wait_semantics()?;
    let arguments = query.arguments()?;
    let mut argv: Vec<_> = arguments.iter().map(|a| a.as_ptr()).collect();
    argv.push(std::ptr::null());
    let environment = query.environment(QueryProjection::EarlyDev);
    let mut envp: Vec<_> = environment.iter().map(|a| a.as_ptr()).collect();
    envp.push(std::ptr::null());
    let mut filter = super::worker::query_filter();
    let program = libc::sock_fprog {
        len: filter.len() as u16,
        filter: filter.as_mut_ptr(),
    };
    let (parent_gate, child_gate) = protocol::socketpair()?;
    let parent_gate = File::from(parent_gate);
    let child_gate = File::from(child_gate);
    let factory = pidfd(unsafe { libc::getpid() } as u32)?;
    let f = &prepared.files;
    let native = NativeQuery {
        files: [
            f[STDIN].as_raw_fd(),
            f[STDOUT].as_raw_fd(),
            f[STDERR].as_raw_fd(),
            child_gate.as_raw_fd(),
            f[0].as_raw_fd(),
            f[1].as_raw_fd(),
            factory.as_raw_fd(),
            f[2].as_raw_fd(),
            f[3].as_raw_fd(),
            f[4].as_raw_fd(),
            f[6].as_raw_fd(),
            f[7].as_raw_fd(),
            f[8].as_raw_fd(),
            f[9].as_raw_fd(),
            f[10].as_raw_fd(),
        ],
        pid_namespace: f[5].as_raw_fd(),
        cgroup: prepared.cgroup.as_raw_fd(),
        domain: native_domain(query.domain()),
        deadline_ns,
        argv: argv.as_ptr(),
        envp: envp.as_ptr(),
        filter: &program,
    };
    let mut pid = -1;
    let mut raw = -1;
    let status = unsafe { droidloom_factory_spawn_query(&native, &mut pid, &mut raw) };
    let error = io::Error::last_os_error();
    if raw < 0 {
        return if pid > 0 {
            Err(ApplicationError::RetirementUnproven)
        } else {
            Err(error.into())
        };
    }
    let mut child = OwnedQuery {
        pid: pid as u32,
        pidfd: unsafe { File::from_raw_fd(raw) },
        creator: unsafe { libc::syscall(libc::SYS_gettid) } as i32,
        terminal: None,
        stopped: false,
        released: false,
    };
    if status != 0 || pid <= 1 {
        child
            .retire(Instant::now() + RETIRE_LIMIT)
            .map_err(|_| ApplicationError::RetirementUnproven)?;
        return Err(ApplicationError::RetirementUnproven);
    }
    if child.original().is_err() {
        child
            .retire(Instant::now() + RETIRE_LIMIT)
            .map_err(|_| ApplicationError::RetirementUnproven)?;
        return Err(ApplicationError::RetirementUnproven);
    }
    Ok((child, parent_gate))
}
fn gate_ready(
    child: &mut OwnedQuery,
    gate: &File,
    authority: &FactoryAuthority<'_>,
    deadline: Instant,
) -> Result<()> {
    loop {
        authority.check()?;
        require(
            child.terminal()?.is_none(),
            "query exited before its birth gate",
        )?;
        if readable(gate.as_raw_fd(), deadline)? {
            let mut bytes = [0u8; 2];
            let n = unsafe {
                libc::recv(
                    gate.as_raw_fd(),
                    bytes.as_mut_ptr().cast(),
                    bytes.len(),
                    libc::MSG_DONTWAIT,
                )
            };
            require(n == 1 && bytes[0] == b'R', "fixed query birth gate differs")?;
            // Birth has left kernel SID, but retains the original host userns,
            // UID/GID, dumpability and capability subset needed for attach.
            let value = info(&child.pidfd)?;
            require(
                value.ruid == 0
                    && value.euid == 0
                    && value.suid == 0
                    && value.rgid == 0
                    && value.egid == 0
                    && value.sgid == 0,
                "query changed credentials before original factory attach",
            )?;
            child.seize()?;
            if unsafe {
                libc::send(
                    gate.as_raw_fd(),
                    b"G".as_ptr().cast(),
                    1,
                    libc::MSG_NOSIGNAL,
                )
            } != 1
            {
                return Err(io::Error::last_os_error().into());
            }
            return Ok(());
        }
        pause(&[gate.as_raw_fd(), child.pidfd.as_raw_fd()], deadline)?;
    }
}
fn peer(received: &protocol::Received, pid: u32) -> Result<()> {
    require(
        received.peer.pid == pid as i32
            && received.peer.uid == 0
            && received.peer.gid == 0
            && received.files.is_empty(),
        "factory query response authority differs",
    )
}
/// Handle one closed query only while the same authenticated production
/// resource owner and original Android generation remain alive.
pub(crate) fn serve(channel: &File, authority: FactoryAuthority<'_>) -> Result<()> {
    pass_credentials(channel)?;
    let expected = info(authority.owner)?.pid;
    let credentials = credentials(channel)?;
    require(
        credentials.pid == expected as i32,
        "factory query is not from the original owner",
    )?;
    let received = protocol::receive(channel.as_raw_fd(), Instant::now() + QUERY_LIMIT)?;
    require(
        received.peer.pid == expected as i32 && received.peer.uid == 0 && received.peer.gid == 0,
        "factory request sender differs",
    )?;
    let (nonce, query, deadline_ns) = match received.message {
        Message::FactoryRequest {
            nonce,
            query,
            deadline_ns,
        } => (nonce, query, deadline_ns),
        _ => return Err(reject("factory first query phase differs")),
    };
    let remaining = deadline_ns
        .checked_sub(protocol::monotonic_ns()?)
        .ok_or_else(|| reject("factory query deadline expired"))?;
    require(
        remaining > 0 && remaining <= QUERY_LIMIT.as_nanos() as u64,
        "factory query requested a different time budget",
    )?;
    let deadline = Instant::now() + Duration::from_nanos(remaining);
    let prepared = match prepare(
        received.files.into_iter().map(File::from).collect(),
        &query,
        &authority,
        deadline,
    ) {
        Ok(value) => value,
        Err(error) => {
            let message = error.to_string().chars().take(2048).collect();
            protocol::send(
                channel.as_raw_fd(),
                &Message::FactoryRejected { nonce, message },
                &[],
                deadline,
            )?;
            return Ok(());
        }
    };
    let (mut child, gate) = match spawn(&prepared, &query, deadline_ns) {
        Ok(value) => value,
        Err(ApplicationError::RetirementUnproven) => {
            return Err(ApplicationError::RetirementUnproven);
        }
        Err(error) => {
            let message = error.to_string().chars().take(2048).collect();
            protocol::send(
                channel.as_raw_fd(),
                &Message::FactoryRejected { nonce, message },
                &[],
                deadline,
            )?;
            return Ok(());
        }
    };
    let node = match identity(&child.pidfd) {
        Ok(value) => value,
        Err(error) => {
            child
                .retire(Instant::now() + RETIRE_LIMIT)
                .map_err(|_| ApplicationError::RetirementUnproven)?;
            return Err(error);
        }
    };
    // Only the child may retain its I/O write descriptions. Parent ownership
    // is limited to atomic PIDFD, authenticated control and lifecycle evidence.
    drop(prepared);
    let operation = (|| -> Result<()> {
        // Bind the observation handle before the wait owner may reap anything.
        // Only this source-owned authenticated response can select the PID;
        // the broker must match its new PIDFD to this atomic PIDFS inode.
        protocol::send(
            channel.as_raw_fd(),
            &Message::FactoryBorn {
                nonce,
                pid: child.pid,
                pidfd_device: node.0,
                pidfd_inode: node.1,
            },
            &[],
            deadline,
        )?;
        let bound = protocol::receive(channel.as_raw_fd(), deadline)?;
        peer(&bound, expected)?;
        require(
            matches!(bound.message,Message::FactoryBound {nonce:actual} if actual==nonce),
            "broker did not bind the original factory child observation",
        )?;
        gate_ready(&mut child, &gate, &authority, deadline)?;
        let previous = child.exec_stop(&authority, deadline)?;
        authority.check()?;
        protocol::send(
            channel.as_raw_fd(),
            &Message::FactoryExecStopped {
                nonce,
                pid: child.pid,
                pidfd_device: node.0,
                pidfd_inode: node.1,
                tracer_tid: child.creator as u32,
                waitid_code: libc::CLD_TRAPPED,
                waitid_status: EXEC_EVENT,
                event_previous_tid: previous,
            },
            &[],
            deadline,
        )?;
        let response = protocol::receive(channel.as_raw_fd(), deadline)?;
        peer(&response, expected)?;
        match response.message {
            Message::FactoryRelease { nonce: actual } if actual == nonce => {
                authority.check()?;
                child.release()?;
                protocol::send(
                    channel.as_raw_fd(),
                    &Message::FactoryReleased { nonce },
                    &[],
                    deadline,
                )?;
            }
            Message::FactoryCancel { nonce: actual } if actual == nonce => {
                return Err(reject("query cancelled"));
            }
            _ => return Err(reject("factory query release phase differs")),
        }
        loop {
            authority.check()?;
            if child.terminal()?.is_some() {
                return Ok(());
            }
            if readable(channel.as_raw_fd(), deadline)? {
                let response = protocol::receive(channel.as_raw_fd(), deadline)?;
                peer(&response, expected)?;
                match response.message {
                    Message::FactoryCancel { nonce: actual } if actual == nonce => {
                        return Err(reject("query cancelled after release"));
                    }
                    _ => return Err(reject("unexpected factory query running phase")),
                }
            }
            pause(&[channel.as_raw_fd(), child.pidfd.as_raw_fd()], deadline)?;
        }
    })();
    let terminal = if operation.is_ok() {
        child
            .terminal()?
            .ok_or(ApplicationError::RetirementUnproven)?
    } else {
        child
            .retire(Instant::now() + RETIRE_LIMIT)
            .map_err(|_| ApplicationError::RetirementUnproven)?
    };
    require(
        !live(&child.pidfd)?,
        "factory query remained alive after actual waitid",
    )?;
    let _ = protocol::send(
        channel.as_raw_fd(),
        &Message::FactoryTerminated {
            nonce,
            pid: child.pid,
            pidfd_device: node.0,
            pidfd_inode: node.1,
            waitid_code: terminal.code,
            waitid_status: terminal.status,
            released: child.released,
        },
        &[],
        Instant::now() + RETIRE_LIMIT,
    );
    // Even a lost response cannot change the actual original query retirement.
    // The client separately fails closed if it did not receive that evidence.
    Ok(())
}

struct ObservedQuery {
    pid: u32,
    pidfd: File,
    node: (u64, u64),
}
impl ObservedQuery {
    fn bind(pid: u32, node: (u64, u64), factory: u32) -> Result<Self> {
        let pidfd = pidfd(pid)?;
        require(
            identity(&pidfd)? == node,
            "authenticated query PID was reused before observation",
        )?;
        let value = Self { pid, pidfd, node };
        let observed = info(&value.pidfd)?;
        require(
            observed.pid == pid && observed.ppid == factory,
            "new observation is not the factory's original direct child",
        )?;
        Ok(value)
    }
    fn revalidate(&self, factory: u32) -> Result<()> {
        require(
            identity(&self.pidfd)? == self.node && live(&self.pidfd)?,
            "same observed factory query is no longer live",
        )?;
        let value = info(&self.pidfd)?;
        require(
            value.pid == self.pid && value.ppid == factory,
            "query observation no longer belongs to its original factory",
        )?;
        Ok(())
    }
}

/// Remote lifecycle evidence retains the original authenticated factory
/// channel. It never implements Child, sends a signal, or calls waitid.
struct Client {
    endpoint: crate::production_selection::FactoryQueryEndpoint,
    nonce: [u8; 16],
    sent: bool,
    no_child: bool,
    query: Option<ObservedQuery>,
    terminal: Option<Terminal>,
    released: bool,
}
impl Client {
    fn connect() -> Result<Self> {
        let endpoint = crate::production_selection::FactoryQueryEndpoint::connect()?;
        pass_credentials(endpoint.channel())?;
        let mut nonce = [0u8; 16];
        require(
            unsafe { libc::syscall(libc::SYS_getrandom, nonce.as_mut_ptr(), nonce.len(), 0u32) }
                == nonce.len() as libc::c_long,
            "factory query nonce generation failed",
        )?;
        Ok(Self {
            endpoint,
            nonce,
            sent: false,
            no_child: false,
            query: None,
            terminal: None,
            released: false,
        })
    }
    fn revalidate(&self) -> Result<()> {
        self.endpoint.revalidate()?;
        if self.terminal.is_none() {
            if let Some(query) = &self.query {
                query.revalidate(self.endpoint.pid())?;
            }
        }
        Ok(())
    }
    fn receive(
        &self,
        deadline: Instant,
        progress: &mut dyn FnMut() -> Result<()>,
    ) -> Result<protocol::Received> {
        loop {
            self.endpoint.revalidate()?;
            if readable(self.endpoint.channel().as_raw_fd(), deadline)? {
                let message = protocol::receive(self.endpoint.channel().as_raw_fd(), deadline)?;
                peer(&message, self.endpoint.pid())?;
                return Ok(message);
            }
            progress()?;
            pause(
                &[
                    self.endpoint.channel().as_raw_fd(),
                    self.endpoint.pidfd().as_raw_fd(),
                ],
                deadline,
            )?;
        }
    }
    fn request(
        &mut self,
        query: &ApplicationOperation,
        files: &[File],
        deadline: Instant,
        progress: &mut dyn FnMut() -> Result<()>,
    ) -> Result<FactoryExecStop> {
        require(
            !self.sent && files.len() == query.descriptor_count() + 1,
            "factory client request is not one-shot",
        )?;
        let anchor = protocol::monotonic_ns()?;
        let left = deadline.saturating_duration_since(Instant::now());
        require(!left.is_zero(), "factory client request deadline")?;
        let deadline_ns = anchor
            .checked_add(left.as_nanos() as u64)
            .ok_or_else(|| reject("factory request deadline overflow"))?;
        let raw: Vec<_> = files.iter().map(AsRawFd::as_raw_fd).collect();
        self.sent = true;
        protocol::send(
            self.endpoint.channel().as_raw_fd(),
            &Message::FactoryRequest {
                nonce: self.nonce,
                query: query.clone(),
                deadline_ns,
            },
            &raw,
            deadline,
        )?;
        let first = self.receive(deadline, progress)?;
        match first.message {
            Message::FactoryRejected { nonce, message } => {
                require(
                    nonce == self.nonce && message.len() <= 2048,
                    "factory rejection identity differs",
                )?;
                self.no_child = true;
                return Err(reject(message));
            }
            Message::FactoryBorn {
                nonce,
                pid,
                pidfd_device,
                pidfd_inode,
            } => {
                require(
                    nonce == self.nonce
                        && pid > 1
                        && pidfd_device > 0
                        && pidfd_inode > 0
                        && pid != self.endpoint.pid(),
                    "factory birth identity differs",
                )?;
                let observed =
                    ObservedQuery::bind(pid, (pidfd_device, pidfd_inode), self.endpoint.pid())?;
                self.query = Some(observed);
            }
            _ => return Err(reject("factory first response phase differs")),
        }
        self.revalidate()?;
        protocol::send(
            self.endpoint.channel().as_raw_fd(),
            &Message::FactoryBound { nonce: self.nonce },
            &[],
            deadline,
        )?;
        let stopped = self.receive(deadline, progress)?;
        match stopped.message {
            Message::FactoryExecStopped {
                nonce,
                pid,
                pidfd_device,
                pidfd_inode,
                tracer_tid,
                waitid_code,
                waitid_status,
                event_previous_tid,
            } => {
                let query = self
                    .query
                    .as_ref()
                    .ok_or(ApplicationError::RetirementUnproven)?;
                require(
                    nonce == self.nonce
                        && pid == query.pid
                        && (pidfd_device, pidfd_inode) == query.node
                        && tracer_tid == self.endpoint.pid()
                        && waitid_code == libc::CLD_TRAPPED
                        && waitid_status == EXEC_EVENT
                        && event_previous_tid == pid as u64,
                    "factory exec stop differs from the original bound query",
                )?;
                self.revalidate()?;
                Ok(FactoryExecStop {
                    pid,
                    tracer_tid,
                    waitid_code,
                    waitid_status,
                    event_previous_tid,
                })
            }
            message @ Message::FactoryTerminated { .. } => {
                self.accept_terminal(message)?;
                Err(reject("query terminated before a verified factory exec"))
            }
            _ => Err(reject(
                "factory query did not report its original exec stop",
            )),
        }
    }
    fn accept_terminal(&mut self, message: Message) -> Result<()> {
        self.endpoint.revalidate()?;
        let Message::FactoryTerminated {
            nonce,
            pid,
            pidfd_device,
            pidfd_inode,
            waitid_code,
            waitid_status,
            released,
        } = message
        else {
            return Err(reject("factory terminal message phase differs"));
        };
        let query = self
            .query
            .as_ref()
            .ok_or(ApplicationError::RetirementUnproven)?;
        let terminal = Terminal {
            code: waitid_code,
            status: waitid_status,
        };
        require(
            nonce == self.nonce
                && pid == query.pid
                && (pidfd_device, pidfd_inode) == query.node
                && identity(&query.pidfd)? == query.node
                && !live(&query.pidfd)?
                && terminal.valid()
                && released == self.released,
            "authenticated terminal does not retire the same original factory query",
        )?;
        require(
            self.terminal.is_none(),
            "factory query terminal was already consumed",
        )?;
        self.terminal = Some(terminal);
        Ok(())
    }
    fn release(
        &mut self,
        stop: &FactoryExecStop,
        deadline: Instant,
        progress: &mut dyn FnMut() -> Result<()>,
    ) -> Result<()> {
        self.revalidate()?;
        let query = self
            .query
            .as_ref()
            .ok_or(ApplicationError::RetirementUnproven)?;
        require(
            stop.pid == query.pid
                && stop.tracer_tid == self.endpoint.pid()
                && !self.released
                && self.terminal.is_none(),
            "factory release is not the verified exec stop",
        )?;
        protocol::send(
            self.endpoint.channel().as_raw_fd(),
            &Message::FactoryRelease { nonce: self.nonce },
            &[],
            deadline,
        )?;
        let response = self.receive(deadline, progress)?;
        require(
            matches!(response.message,Message::FactoryReleased {nonce} if nonce==self.nonce),
            "factory did not acknowledge actual original PTRACE_CONT",
        )?;
        self.released = true;
        Ok(())
    }
    fn poll_terminal(&mut self, deadline: Instant) -> Result<Option<Terminal>> {
        if let Some(value) = self.terminal {
            return Ok(Some(value));
        }
        self.endpoint.revalidate()?;
        if readable(self.endpoint.channel().as_raw_fd(), deadline)? {
            let response = protocol::receive(self.endpoint.channel().as_raw_fd(), deadline)?;
            peer(&response, self.endpoint.pid())?;
            self.accept_terminal(response.message)?;
        }
        Ok(self.terminal)
    }
    fn retire(&mut self) -> Result<()> {
        if !self.sent || self.no_child || self.terminal.is_some() {
            return Ok(());
        }
        let deadline = Instant::now() + RETIRE_LIMIT;
        // Cancellation grants no new authority: only the original factory can
        // signal and reap this one child. The broker never substitutes waitpid.
        protocol::send(
            self.endpoint.channel().as_raw_fd(),
            &Message::FactoryCancel { nonce: self.nonce },
            &[],
            deadline,
        )?;
        loop {
            let response = protocol::receive(self.endpoint.channel().as_raw_fd(), deadline)?;
            peer(&response, self.endpoint.pid())?;
            match response.message {
                Message::FactoryRejected { nonce, message }
                    if nonce == self.nonce && message.len() <= 2048 =>
                {
                    self.no_child = true;
                    return Ok(());
                }
                Message::FactoryBorn {
                    nonce,
                    pid,
                    pidfd_device,
                    pidfd_inode,
                } if nonce == self.nonce => {
                    if self.query.is_none() {
                        self.query = Some(ObservedQuery::bind(
                            pid,
                            (pidfd_device, pidfd_inode),
                            self.endpoint.pid(),
                        )?);
                    }
                }
                Message::FactoryExecStopped { nonce, .. } if nonce == self.nonce => {}
                Message::FactoryReleased { nonce } if nonce == self.nonce => {
                    self.released = true;
                }
                message @ Message::FactoryTerminated { .. } => {
                    self.accept_terminal(message)?;
                    return Ok(());
                }
                _ => return Err(ApplicationError::RetirementUnproven),
            }
        }
    }
    fn verify_retirement(&self) -> Result<()> {
        require(
            !self.sent || self.no_child || self.terminal.is_some(),
            "factory query retirement has not been authenticated",
        )?;
        if let Some(query) = &self.query {
            require(
                self.terminal.is_some()
                    && identity(&query.pidfd)? == query.node
                    && !live(&query.pidfd)?,
                "factory query PIDFD has not actually exited",
            )?;
        }
        self.endpoint.revalidate()?;
        Ok(())
    }
}
impl Drop for Client {
    fn drop(&mut self) {
        if self.sent && !self.no_child && self.terminal.is_none() {
            let _ = self.retire();
        }
    }
}

/// Borrowed only after the authenticated original owner reported real waitid.
/// It can prove cleanup after a failure; success requires the separate strict
/// lifecycle/stdio/normal-exit checks on ReadReceipt.
pub(crate) struct RetiredQuery<'a> {
    client: &'a Client,
    cgroup_identity: (u64, u64),
}
impl RetiredQuery<'_> {
    pub(crate) fn verify_cgroup(&self, file: &File) -> Result<()> {
        self.client.verify_retirement()?;
        require(
            identity(file)? == self.cgroup_identity,
            "factory retirement belongs to another cgroup leaf",
        )
    }
}

fn drain(
    file: &mut File,
    body: &mut Vec<u8>,
    total: &mut usize,
    eof: &mut bool,
    limit: usize,
) -> Result<()> {
    use std::io::Read;
    if *eof {
        return Ok(());
    }
    loop {
        let mut bytes = [0u8; 4096];
        match file.read(&mut bytes) {
            Ok(0) => {
                *eof = true;
                return Ok(());
            }
            Ok(n) => {
                *total = total
                    .checked_add(n)
                    .ok_or_else(|| reject("query output overflow"))?;
                require(
                    *total <= limit,
                    "factory query combined output exceeded bound",
                )?;
                body.extend_from_slice(&bytes[..n]);
            }
            Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
            Err(e) if e.kind() == io::ErrorKind::WouldBlock => return Ok(()),
            Err(e) => return Err(e.into()),
        }
    }
}
fn capture(
    client: &mut Client,
    stdout: &mut File,
    stderr: &mut File,
    input: &mut Option<super::install_input::InputPump>,
    output_limit: usize,
    deadline: Instant,
    progress: &mut dyn FnMut() -> Result<()>,
) -> Result<(Vec<u8>, Vec<u8>)> {
    let mut output = Vec::new();
    let mut error = Vec::new();
    let mut total = 0;
    let mut output_eof = false;
    let mut error_eof = false;
    let mut progress_after = Instant::now();
    loop {
        if input.is_none() || Instant::now() >= progress_after {
            progress()?;
            progress_after = Instant::now() + Duration::from_millis(20);
        }
        require(Instant::now() < deadline, "factory query output deadline")?;
        drain(
            stdout,
            &mut output,
            &mut total,
            &mut output_eof,
            output_limit,
        )?;
        drain(stderr, &mut error, &mut total, &mut error_eof, output_limit)?;
        if client.poll_terminal(deadline)?.is_some() {
            if let Some(input) = input {
                input.close();
            }
            if output_eof && error_eof {
                return Ok((output, error));
            }
        } else if let Some(input) = input {
            input.advance(deadline)?;
        }
        let query = client
            .query
            .as_ref()
            .ok_or(ApplicationError::RetirementUnproven)?;
        let mut watches = vec![
            libc::pollfd {
                fd: client.endpoint.channel().as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            },
            libc::pollfd {
                fd: query.pidfd.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            },
            libc::pollfd {
                fd: stdout.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            },
            libc::pollfd {
                fd: stderr.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            },
        ];
        if let Some(fd) = input.as_ref().and_then(|input| input.descriptor()) {
            watches.push(libc::pollfd {
                fd,
                events: libc::POLLOUT,
                revents: 0,
            });
        }
        let left = deadline.saturating_duration_since(Instant::now());
        require(!left.is_zero(), "factory stream absolute deadline")?;
        let count = unsafe {
            libc::poll(
                watches.as_mut_ptr(),
                watches.len() as libc::nfds_t,
                left.as_millis().clamp(1, 20) as i32,
            )
        };
        if count < 0 && io::Error::last_os_error().kind() != io::ErrorKind::Interrupted {
            return Err(io::Error::last_os_error().into());
        }
        require(
            watches.iter().all(|p| p.revents & libc::POLLNVAL == 0),
            "factory stream descriptor became invalid",
        )?;
    }
}
pub(super) fn run(
    authority: &dyn ApplicationWorkerAuthority,
    request: &ApplicationOperation,
    workflow_deadline: Instant,
) -> Result<LaunchCommandResult> {
    run_with_input(authority, request, None, workflow_deadline)
}
pub(super) fn run_with_input(
    authority: &dyn ApplicationWorkerAuthority,
    request: &ApplicationOperation,
    input: Option<super::install_input::SegmentInput>,
    workflow_deadline: Instant,
) -> Result<LaunchCommandResult> {
    use sha2::{Digest, Sha256};
    use std::os::unix::process::ExitStatusExt;
    let started = Instant::now();
    let deadline = (started + QUERY_LIMIT).min(workflow_deadline);
    require(Instant::now() < deadline, "factory query workflow deadline")?;
    request.validate()?;
    require(
        authority.query_projection() == QueryProjection::EarlyDev,
        "factory operation requires the original early projection",
    )?;
    authority.revalidate().map_err(external)?;
    let mut files = authority.descriptors(request.binary()).map_err(external)?;
    require(
        files.len() == 12,
        "factory query original descriptor prefix differs",
    )?;
    let namespaces = super::process::NamespaceBinding::from_original_owner(&files)?;
    let (root_uid, root_gid) = authority.mapped_root().map_err(external)?;
    let classpath = if request.needs_content_jar() {
        Some(authority.contacts_content_descriptors().map_err(external)?)
    } else {
        None
    };
    let binding = if request.uses_app_process() {
        super::process::ExecutableBinding::from_contacts_role(
            &files[10], root_uid, root_gid, deadline,
        )?
    } else {
        super::process::ExecutableBinding::from_held_role(&files[10], root_uid, root_gid, deadline)?
    };
    let shell_uid = root_uid
        .checked_add(2000)
        .ok_or_else(|| reject("query shell UID overflow"))?;
    let shell_gid = root_gid
        .checked_add(2000)
        .ok_or_else(|| reject("query shell GID overflow"))?;
    // The stdio creator is an independent real broker child, with its own
    // normal PIDFD wait. It is never presented as the query's creator.
    require(
        input.as_ref().map(|input| input.bytes()) == request.install_input_bytes(),
        "installation input is absent or outside its fixed write operation",
    )?;
    let io = if input.is_some() {
        super::query_io::create_apk_pipe(&files[2], deadline)?
    } else {
        super::query_io::create(&files[2], deadline)?
    };
    let stdio_creator = io.creator_receipt()?;
    let mut input = match (input, io.stdin_write) {
        (Some(input), Some(writer)) => Some(super::install_input::InputPump::new(input, writer)?),
        (None, None) => None,
        _ => return Err(reject("query I/O creator returned another stdin role")),
    };
    let mut stdout = io.stdout_read;
    let mut stderr = io.stderr_read;
    let mut client = Client::connect()?;
    let mut leaf = authority.leaf().map_err(external)?;
    let cgroup_identity = leaf.identity().map_err(external)?;
    let cgroup = leaf
        .clone_target()
        .map_err(external)?
        .try_clone_to_owned()?;
    files.extend([io.stdin, io.stdout_write, io.stderr_write]);
    if let Some(classpath) = classpath {
        files.extend(classpath);
    }
    files.push(File::from(cgroup));
    let mut progress = || {
        authority
            .progress_inherited_native(deadline)
            .map_err(external)
    };
    let operation = (|| -> Result<(Vec<u8>, Vec<u8>, super::process::ExecReceipt)> {
        let stop = client.request(request, &files, deadline, &mut progress)?;
        drop(files);
        authority.revalidate().map_err(external)?;
        let query = client
            .query
            .as_ref()
            .ok_or(ApplicationError::RetirementUnproven)?;
        // Only the fixed metadata helper opens Android proc. Its authenticated
        // host cgroup and namespace observations are checked by the pure verifier
        // against the original application leaf and held query PIDFD.
        let exec = super::process::verify_factory_exec(
            &binding,
            &namespaces,
            &query.pidfd,
            client.endpoint.pidfd(),
            &stop,
            shell_uid,
            shell_gid,
            request.domain(),
            deadline,
        )?;
        client.release(&stop, deadline, &mut progress)?;
        let (output, error) = capture(
            &mut client,
            &mut stdout,
            &mut stderr,
            &mut input,
            request.output_limit(),
            deadline,
            &mut progress,
        )?;
        Ok((output, error, exec))
    })();
    // Close the creator-origin writer on every path before actual retirement.
    if let Some(input) = &mut input {
        input.close();
    }
    // Every return passes actual factory wait ownership and same-leaf empty
    // retirement. The broker never calls waitid or sends a signal via its query
    // observation handle. A lost/unverifiable response retains the lease.
    if client.retire().is_err() {
        let _ = leaf.kill();
        let _ = leaf.wait_empty(Instant::now() + RETIRE_LIMIT);
        return Err(ApplicationError::RetirementUnproven);
    }
    client
        .verify_retirement()
        .map_err(|_| ApplicationError::RetirementUnproven)?;
    leaf.wait_empty(Instant::now() + RETIRE_LIMIT)
        .map_err(|_| ApplicationError::RetirementUnproven)?;
    let proof = RetiredQuery {
        client: &client,
        cgroup_identity,
    };
    leaf.retire(&ApplicationRetired::Factory { query: &proof })
        .map_err(|_| ApplicationError::RetirementUnproven)?;
    let (output, error, exec) = operation?;
    let query = client
        .query
        .as_ref()
        .ok_or(ApplicationError::RetirementUnproven)?;
    let terminal = client
        .terminal
        .ok_or(ApplicationError::RetirementUnproven)?;
    let factory_node = identity(client.endpoint.pidfd())?;
    require(
        client.released,
        "query output has no actual factory release acknowledgement",
    )?;
    let receipt = ReadReceipt {
        schema: 2,
        lifecycle: ReadLifecycle::InstanceFactory {
            factory_pid: client.endpoint.pid(),
            factory_tid: client.endpoint.pid(),
            factory_pidfd_device: factory_node.0,
            factory_pidfd_inode: factory_node.1,
            query_pidfd_device: query.node.0,
            query_pidfd_inode: query.node.1,
            stdio_creator,
            release_acknowledged: client.released,
        },
        query_pid: query.pid,
        query_waitid_code: terminal.code,
        query_waitid_status: terminal.status,
        exec,
        output_bytes: output.len(),
        output_sha256: format!("{:x}", Sha256::digest(&output)),
        elapsed_millis: started
            .elapsed()
            .as_millis()
            .try_into()
            .map_err(|_| reject("query timing overflow"))?,
        cgroup_removed: true,
    };
    let raw = match terminal {
        Terminal {
            code: libc::CLD_EXITED,
            status,
        } => status << 8,
        Terminal {
            code: libc::CLD_KILLED,
            status,
        } => status,
        Terminal {
            code: libc::CLD_DUMPED,
            status,
        } => status | 0x80,
        _ => return Err(reject("query terminal cannot form an exit status")),
    };
    if terminal.code == libc::CLD_EXITED && terminal.status == 0 {
        if let Some(input) = &input {
            input.finish()?;
        }
    }
    let stderr_bytes = error.len();
    let stderr_sha256 = format!("{:x}", Sha256::digest(&error));
    require(
        Instant::now() < deadline,
        "factory query completed after its workflow deadline",
    )?;
    Ok(LaunchCommandResult {
        output: std::process::Output {
            status: std::process::ExitStatus::from_raw(raw),
            stdout: output,
            stderr: error,
        },
        receipt,
        stderr_bytes,
        stderr_sha256,
        operation_deadline: deadline,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn ordinary_child(exec: bool) -> (OwnedQuery, File) {
        super::super::worker::require_wait_semantics().unwrap();
        let (a, b) = protocol::socketpair().unwrap();
        let a = File::from(a);
        let b = File::from(b);
        let executable = File::open("/usr/bin/true").unwrap();
        let mut raw = -1;
        let args = super::super::worker::CloneArgs {
            flags: libc::CLONE_PIDFD as u64,
            pidfd: (&mut raw as *mut i32) as u64,
            exit_signal: libc::SIGCHLD as u64,
            ..Default::default()
        };
        let mut mask = super::super::worker::SignalMask::block().unwrap();
        let pid = unsafe { libc::syscall(libc::SYS_clone3, &args, mem::size_of_val(&args)) };
        assert!(
            pid >= 0,
            "ordinary query ownership fixture: {}",
            io::Error::last_os_error()
        );
        if pid == 0 {
            unsafe {
                let mut signal = 0u8;
                loop {
                    let n = libc::recv(b.as_raw_fd(), (&mut signal as *mut u8).cast(), 1, 0);
                    if n == 1 {
                        break;
                    }
                    let mut p = libc::pollfd {
                        fd: b.as_raw_fd(),
                        events: libc::POLLIN,
                        revents: 0,
                    };
                    if libc::poll(&mut p, 1, 1000) < 0 && *libc::__errno_location() != libc::EINTR {
                        libc::_exit(125);
                    }
                }
                if !exec {
                    libc::_exit(7);
                }
                let argv = [c"true".as_ptr(), std::ptr::null()];
                let envp = [std::ptr::null::<libc::c_char>()];
                libc::syscall(
                    libc::SYS_execveat,
                    executable.as_raw_fd(),
                    c"".as_ptr(),
                    argv.as_ptr(),
                    envp.as_ptr(),
                    libc::AT_EMPTY_PATH,
                );
                libc::_exit(125);
            }
        }
        assert!(raw >= 0);
        mask.restore().unwrap();
        let child = OwnedQuery {
            pid: pid as u32,
            pidfd: unsafe { File::from_raw_fd(raw) },
            creator: unsafe { libc::syscall(libc::SYS_gettid) } as i32,
            terminal: None,
            stopped: false,
            released: false,
        };
        (child, a)
    }
    fn go(gate: &File) {
        assert_eq!(
            unsafe {
                libc::send(
                    gate.as_raw_fd(),
                    b"G".as_ptr().cast(),
                    1,
                    libc::MSG_NOSIGNAL,
                )
            },
            1
        );
    }
    fn completed(child: &mut OwnedQuery) -> Terminal {
        let end = Instant::now() + Duration::from_secs(3);
        loop {
            if let Some(value) = child.terminal().unwrap() {
                return value;
            }
            pause(&[child.pidfd.as_raw_fd()], end).unwrap();
        }
    }
    #[test]
    fn actual_factory_owner_reaps_its_original_pidfd_once() {
        let (mut child, gate) = ordinary_child(false);
        go(&gate);
        assert_eq!(
            completed(&mut child),
            Terminal {
                code: libc::CLD_EXITED,
                status: 7
            }
        );
        assert!(!child.terminal.unwrap().success());
        let mut status: libc::siginfo_t = unsafe { mem::zeroed() };
        assert_eq!(
            unsafe {
                libc::waitid(
                    libc::P_PIDFD,
                    child.pidfd.as_raw_fd() as u32,
                    &mut status,
                    libc::WEXITED | libc::WNOHANG,
                )
            },
            -1
        );
        assert_eq!(
            io::Error::last_os_error().raw_os_error(),
            Some(libc::ECHILD)
        );
    }
    #[test]
    fn observation_binding_rejects_other_pidfs_inode_and_parent() {
        let (mut child, _gate) = ordinary_child(false);
        let node = identity(&child.pidfd).unwrap();
        assert!(ObservedQuery::bind(child.pid, (node.0, node.1 + 1), std::process::id()).is_err());
        assert!(ObservedQuery::bind(child.pid, node, std::process::id() + 1).is_err());
        let bound = ObservedQuery::bind(child.pid, node, std::process::id()).unwrap();
        bound.revalidate(std::process::id()).unwrap();
        let terminal = child
            .retire(Instant::now() + Duration::from_secs(3))
            .unwrap();
        assert_eq!(terminal.code, libc::CLD_KILLED);
        assert!(!terminal.success());
        assert!(!live(&bound.pidfd).unwrap());
    }
    #[test]
    fn actual_exec_event_and_continue_belong_to_the_original_wait_thread() {
        let (mut child, gate) = ordinary_child(true);
        child.seize().unwrap();
        let current = pidfd(std::process::id()).unwrap();
        let user = File::open("/proc/self/ns/user").unwrap();
        let pid = File::open("/proc/self/ns/pid").unwrap();
        let mount = File::open("/proc/self/ns/mnt").unwrap();
        let validate = || Ok(());
        let authority = FactoryAuthority {
            init: &current,
            owner: &current,
            pid_namespace: &pid,
            mount_namespace: &mount,
            user_namespace: &user,
            root_uid: 0,
            root_gid: 0,
            validate: &validate,
        };
        go(&gate);
        let previous = child
            .exec_stop(&authority, Instant::now() + Duration::from_secs(3))
            .unwrap();
        assert_eq!(previous, child.pid as u64);
        assert!(!child.released);
        assert!(child.terminal().unwrap().is_none());
        child.release().unwrap();
        assert!(child.released);
        assert!(completed(&mut child).success());
    }
    #[test]
    fn native_creator_rejects_an_ordinary_host_before_any_clone() {
        let ns = File::open("/proc/self/ns/pid").unwrap();
        let group = File::open("/sys/fs/cgroup").unwrap();
        let original = identity(&ns).unwrap();
        let argv = [c"true".as_ptr(), std::ptr::null()];
        let envp = [std::ptr::null()];
        let mut instruction = libc::sock_filter {
            code: 6,
            jt: 0,
            jf: 0,
            k: 0x7fff0000,
        };
        let filter = libc::sock_fprog {
            len: 1,
            filter: &mut instruction,
        };
        let native = NativeQuery {
            files: [-1; 15],
            pid_namespace: ns.as_raw_fd(),
            cgroup: group.as_raw_fd(),
            domain: native_domain(OperationDomain::Query),
            deadline_ns: u64::MAX,
            argv: argv.as_ptr(),
            envp: envp.as_ptr(),
            filter: &filter,
        };
        let mut pid = -1;
        let mut raw = -1;
        assert_ne!(
            unsafe { droidloom_factory_spawn_query(&native, &mut pid, &mut raw) },
            0
        );
        assert_eq!((pid, raw), (-1, -1));
        assert_eq!(
            identity(&File::open("/proc/self/ns/pid").unwrap()).unwrap(),
            original
        );
    }
}
