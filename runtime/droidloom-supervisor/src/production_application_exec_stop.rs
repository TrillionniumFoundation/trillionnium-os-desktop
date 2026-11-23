//! Actual TRACEEXEC supervision of the already acquired original query.
//!
//! Ptrace's numeric ABI is used only after PIDFD_GET_INFO and the held proc
//! directory prove the unreaped direct child. No external PID, attach target,
//! command, signal or executable can enter this interface. The original
//! Child remains the sole wait owner; failures use its whole-leaf retirement.
use super::*;
use std::ffi::c_void;
use std::os::unix::fs::FileExt;

const QUERY_EXEC: &[u8] = b"u:object_r:droidloom_query_exec:s0";
const PROVIDER_EXEC: &[u8] = b"u:object_r:droidloom_provider_exec:s0";
const AA_STACK: &[u8] = b"droidloom-production-android//&droidloom-production-broker (enforce)\n";
const EXEC_EVENT: i32 = libc::SIGTRAP | (libc::PTRACE_EVENT_EXEC << 8);
const MAX_EXECUTABLE: u64 = 128 * 1024 * 1024;

#[cfg(test)]
#[path = "production_application_exec_stop_tests.rs"]
mod tests;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
struct Node {
    dev: u64,
    ino: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    nlink: u64,
    bytes: u64,
    mtime: i64,
    mtime_nsec: i64,
    ctime: i64,
    ctime_nsec: i64,
}
impl Node {
    fn of(file: &File) -> Result<Self> {
        let m = file.metadata()?;
        Ok(Self {
            dev: m.dev(),
            ino: m.ino(),
            mode: m.mode(),
            uid: m.uid(),
            gid: m.gid(),
            nlink: m.nlink(),
            bytes: m.size(),
            mtime: m.mtime(),
            mtime_nsec: m.mtime_nsec(),
            ctime: m.ctime(),
            ctime_nsec: m.ctime_nsec(),
        })
    }
}

fn kind(file: &File) -> Result<libc::c_long> {
    let mut value: libc::statfs = unsafe { mem::zeroed() };
    if unsafe { libc::fstatfs(file.as_raw_fd(), &mut value) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(value.f_type)
}

fn mount_id(file: &File) -> Result<u64> {
    let mut value: libc::statx = unsafe { mem::zeroed() };
    const STATX_MNT_ID: u32 = 0x1000;
    if unsafe {
        libc::statx(
            file.as_raw_fd(),
            c"".as_ptr(),
            libc::AT_EMPTY_PATH | libc::AT_NO_AUTOMOUNT,
            STATX_MNT_ID,
            &mut value,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    require(
        value.stx_mask & STATX_MNT_ID != 0 && value.stx_mnt_id != 0,
        "query executable mount identity is unavailable",
    )?;
    Ok(value.stx_mnt_id)
}

fn label_matches(actual: &[u8], expected: &[u8]) -> bool {
    actual == expected || actual.strip_suffix(b"\0") == Some(expected)
}

fn query_executable_security(file: &File, expected_label: &[u8]) -> Result<()> {
    require(
        kind(file)? == 0x0102_1994,
        "query executable is not the owned private tmpfs inode",
    )?;
    let mut flags: libc::statvfs = unsafe { mem::zeroed() };
    if unsafe { libc::fstatvfs(file.as_raw_fd(), &mut flags) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        flags.f_flag & 7 == 7 && flags.f_flag & 8 == 0,
        "query executable mount is not readonly nosuid nodev and executable",
    )?;
    let access = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
    if access < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        access & (libc::O_ACCMODE | libc::O_PATH) == libc::O_RDONLY,
        "query executable descriptor is not a readonly body view",
    )?;
    let mut label = [0_u8; 128];
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
    require(
        label_matches(&label[..n as usize], expected_label),
        "actual private query executable label differs",
    )?;
    let n = unsafe {
        libc::fgetxattr(
            file.as_raw_fd(),
            c"security.capability".as_ptr(),
            label.as_mut_ptr().cast(),
            label.len(),
        )
    };
    require(
        n == -1 && io::Error::last_os_error().raw_os_error() == Some(libc::ENODATA),
        "private query executable has a capability xattr or lacks xattr support",
    )
}

fn digest(file: &File, expected: Node, deadline: Instant) -> Result<[u8; 32]> {
    require(
        Node::of(file)? == expected && expected.bytes <= MAX_EXECUTABLE,
        "query executable changed before hashing",
    )?;
    let mut hash = Sha256::new();
    let mut at = 0_u64;
    let mut buffer = [0_u8; 32 * 1024];
    while at < expected.bytes {
        require(Instant::now() < deadline, "query executable hash deadline")?;
        let length = (expected.bytes - at).min(buffer.len() as u64) as usize;
        let n = match file.read_at(&mut buffer[..length], at) {
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            result => result?,
        };
        require(n != 0, "query executable ended before its declared length")?;
        hash.update(&buffer[..n]);
        at += n as u64;
    }
    require(
        file.read_at(&mut buffer[..1], at)? == 0 && Node::of(file)? == expected,
        "query executable changed during complete hashing",
    )?;
    Ok(hash.finalize().into())
}

/// This is a local binding of the descriptor lent by the already revalidated
/// PreparedRuntime query role. It is not a constructor for runtime authority.
pub(super) struct ExecutableBinding {
    file: File,
    node: Node,
    mount_id: u64,
    sha256: [u8; 32],
    label: &'static [u8],
}
impl ExecutableBinding {
    pub(super) fn from_held_role(
        file: &File,
        root_uid: u32,
        root_gid: u32,
        deadline: Instant,
    ) -> Result<Self> {
        Self::from_role(file, root_uid, root_gid, QUERY_EXEC, deadline)
    }
    pub(super) fn from_contacts_role(
        file: &File,
        root_uid: u32,
        root_gid: u32,
        deadline: Instant,
    ) -> Result<Self> {
        Self::from_role(file, root_uid, root_gid, PROVIDER_EXEC, deadline)
    }
    fn from_role(
        file: &File,
        root_uid: u32,
        root_gid: u32,
        label: &'static [u8],
        deadline: Instant,
    ) -> Result<Self> {
        let node = Node::of(file)?;
        require(
            node.mode == libc::S_IFREG | 0o555
                && node.uid == root_uid
                && node.gid == root_gid
                && node.nlink == 1
                && (64..=MAX_EXECUTABLE).contains(&node.bytes),
            "fixed private query executable custody differs",
        )?;
        query_executable_security(file, label)?;
        let sha256 = digest(file, node, deadline)?;
        let value = Self {
            file: file.try_clone()?,
            node,
            mount_id: mount_id(file)?,
            sha256,
            label,
        };
        value.verify(file, deadline)?;
        Ok(value)
    }
    fn verify(&self, file: &File, deadline: Instant) -> Result<()> {
        require(
            Node::of(&self.file)? == self.node
                && Node::of(file)? == self.node
                && mount_id(&self.file)? == self.mount_id
                && mount_id(file)? == self.mount_id,
            "actual stopped executable is not the original private query inode",
        )?;
        query_executable_security(&self.file, self.label)?;
        query_executable_security(file, self.label)?;
        require(
            digest(file, self.node, deadline)? == self.sha256,
            "actual stopped executable bytes differ from the held query role",
        )
    }
}

fn proc_open(parent: &File, name: &CStr, directory: bool) -> Result<File> {
    require(
        kind(parent)? == 0x9fa0,
        "query observation parent is not held procfs",
    )?;
    let raw = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            name.as_ptr(),
            libc::O_RDONLY
                | libc::O_CLOEXEC
                | libc::O_NOFOLLOW
                | libc::O_NONBLOCK
                | if directory { libc::O_DIRECTORY } else { 0 },
        )
    };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let file = unsafe { File::from_raw_fd(raw) };
    require(
        kind(&file)? == 0x9fa0
            && file.metadata()?.mode() & libc::S_IFMT
                == if directory {
                    libc::S_IFDIR
                } else {
                    libc::S_IFREG
                },
        "query observation changed procfs node type",
    )?;
    Ok(file)
}
fn proc_bytes(parent: &File, name: &CStr, limit: u64) -> Result<Vec<u8>> {
    let file = proc_open(parent, name, false)?;
    let mut bytes = Vec::new();
    file.take(limit + 1).read_to_end(&mut bytes)?;
    require(bytes.len() as u64 <= limit, "query proc observation bound")?;
    Ok(bytes)
}
fn generation(proc: &File, pid: u32) -> Result<(u32, u64)> {
    let bytes = proc_bytes(proc, c"stat", 8192)?;
    let text = std::str::from_utf8(&bytes).map_err(external)?;
    require(
        text.starts_with(&format!("{pid} (")),
        "held query proc PID differs",
    )?;
    let (_, tail) = text
        .rsplit_once(") ")
        .ok_or_else(|| reject("query proc stat shape"))?;
    let fields: Vec<_> = tail.split_ascii_whitespace().collect();
    require(fields.len() >= 20, "query proc stat field count")?;
    Ok((
        fields[1].parse().map_err(external)?,
        fields[19].parse().map_err(external)?,
    ))
}
fn status(proc: &File) -> Result<String> {
    String::from_utf8(proc_bytes(proc, c"status", 16384)?).map_err(external)
}
fn status_field<'a>(status: &'a str, field: &str) -> Result<&'a str> {
    let mut found = status.lines().filter_map(|line| line.strip_prefix(field));
    let value = found
        .next()
        .ok_or_else(|| reject("query proc status field absent"))?;
    require(found.next().is_none(), "duplicate query proc status field")?;
    Ok(value.trim())
}
enum ProcLabel {
    Selinux,
    AppArmor,
}
fn current_label(proc: &File, label: ProcLabel) -> Result<Vec<u8>> {
    let attr = proc_open(proc, c"attr", true)?;
    // This query requires the SELinux-first MAC provider contract.
    // This target has no attr/selinux directory; no failed read is retried.
    let parent = match label {
        ProcLabel::Selinux => attr,
        ProcLabel::AppArmor => proc_open(&attr, c"apparmor", true)?,
    };
    proc_bytes(&parent, c"current", 256)
}

/// Source-derived values become evidence only after the actual stopped task
/// and original held executable have all been checked. No deserializer exists.
#[derive(Debug, Serialize)]
pub(crate) struct ExecReceipt {
    query_start_ticks: u64,
    original_parent_pid: u32,
    tracer_tid: u32,
    waitid_code: i32,
    waitid_status: i32,
    event_previous_tid: u64,
    executable: Node,
    executable_mount_id: u64,
    executable_sha256: String,
    executable_selinux: &'static str,
    process_selinux: &'static str,
    process_apparmor: &'static str,
    uid: u32,
    gid: u32,
    no_new_privileges: bool,
    seccomp_filter_mode: u32,
}

pub(super) struct ExecTrace<'a> {
    child: &'a mut Child,
    proc: File,
    original: (u32, u64),
    stopped: bool,
}
impl<'a> ExecTrace<'a> {
    pub(super) fn seize(child: &'a mut Child, proc: &File) -> Result<Self> {
        child.check_thread()?;
        require(
            child.terminal.is_none()
                && child.peek()?.is_none()
                && worker::created_query_pid(&child.pidfd)? == child.pid,
            "query is not the unreaped original direct child",
        )?;
        let original = generation(proc, child.pid)?;
        require(
            original.0 == unsafe { libc::getpid() } as u32,
            "query no longer has the original broker wait owner",
        )?;
        require(
            status_field(&status(proc)?, "TracerPid:")? == "0",
            "query already has another ptrace owner",
        )?;
        let options = libc::PTRACE_O_TRACEEXEC | libc::PTRACE_O_EXITKILL;
        if unsafe {
            libc::ptrace(
                libc::PTRACE_SEIZE,
                child.pid as libc::pid_t,
                std::ptr::null_mut::<c_void>(),
                options as usize as *mut c_void,
            )
        } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
        let value = Self {
            child,
            proc: proc.try_clone()?,
            original,
            stopped: false,
        };
        value.original_owner()?;
        Ok(value)
    }

    fn original_owner(&self) -> Result<()> {
        self.child.check_thread()?;
        require(
            self.child.terminal.is_none()
                && worker::created_query_pid(&self.child.pidfd)? == self.child.pid
                && generation(&self.proc, self.child.pid)? == self.original
                && self.original.0 == unsafe { libc::getpid() } as u32,
            "original traced query identity or wait ownership changed",
        )?;
        let observed = status(&self.proc)?;
        // TracerPid names the actual tracer task (TID), not necessarily its
        // process TGID when the original owner is a broker thread.
        require(
            status_field(&observed, "TracerPid:")?
                .parse::<u32>()
                .map_err(external)?
                == self.child.creator as u32,
            "original broker thread is not the actual query tracer",
        )
    }

    fn wait_stop(&self, consume: bool) -> Result<Option<(i32, i32)>> {
        let mut info: libc::siginfo_t = unsafe { mem::zeroed() };
        if unsafe {
            libc::waitid(
                libc::P_PIDFD,
                self.child.pidfd.as_raw_fd() as libc::id_t,
                &mut info,
                libc::WSTOPPED | libc::WNOHANG | if consume { 0 } else { libc::WNOWAIT },
            )
        } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
        let pid = unsafe { info.si_pid() };
        if pid == 0 {
            return Ok(None);
        }
        require(
            pid == self.child.pid as libc::pid_t,
            "exec stop belongs to another task",
        )?;
        Ok(Some((info.si_code, unsafe { info.si_status() })))
    }

    fn actual_exec_stop(&mut self, deadline: Instant) -> Result<u64> {
        require(!self.stopped, "query exec stop was already consumed")?;
        loop {
            if let Some(event) = self.wait_stop(false)? {
                require(
                    event == (libc::CLD_TRAPPED, EXEC_EVENT)
                        && self.wait_stop(true)? == Some(event),
                    "query did not reach its actual kernel TRACEEXEC stop",
                )?;
                let mut previous_tid: libc::c_ulong = 0;
                if unsafe {
                    libc::ptrace(
                        libc::PTRACE_GETEVENTMSG,
                        self.child.pid as libc::pid_t,
                        std::ptr::null_mut::<c_void>(),
                        (&mut previous_tid as *mut libc::c_ulong).cast::<c_void>(),
                    )
                } != 0
                {
                    return Err(io::Error::last_os_error().into());
                }
                require(
                    previous_tid == u64::from(self.child.pid),
                    "query exec changed the original single-thread PID",
                )?;
                self.stopped = true;
                self.original_owner()?;
                require(
                    self.child.peek()?.is_none(),
                    "query was already terminal at exec stop",
                )?;
                return Ok(previous_tid);
            }
            require(
                self.child.peek()?.is_none(),
                "query exited without a verified exec stop",
            )?;
            poll_once(&[self.child.pidfd.as_raw_fd()], deadline)?;
        }
    }

    fn continue_original(&self, deadline: Instant) -> Result<()> {
        require(
            self.stopped && Instant::now() < deadline,
            "query must remain at its verified exec stop before continuation",
        )?;
        self.original_owner()?;
        if unsafe {
            libc::ptrace(
                libc::PTRACE_CONT,
                self.child.pid as libc::pid_t,
                std::ptr::null_mut::<c_void>(),
                std::ptr::null_mut::<c_void>(),
            )
        } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
        Ok(())
    }

    pub(super) fn verify_and_continue(
        mut self,
        binding: &ExecutableBinding,
        shell_uid: u32,
        shell_gid: u32,
        domain: OperationDomain,
        deadline: Instant,
    ) -> Result<ExecReceipt> {
        require(
            binding.label
                == if domain == OperationDomain::ContactsRead {
                    PROVIDER_EXEC
                } else {
                    QUERY_EXEC
                },
            "operation domain does not match its private executable role",
        )?;
        let previous_tid = self.actual_exec_stop(deadline)?;
        // This is the held process's kernel exe link, not a task lookup or a
        // caller pathname. The already stopped original task cannot race exec.
        let raw = unsafe {
            libc::openat(
                self.proc.as_raw_fd(),
                c"exe".as_ptr(),
                libc::O_RDONLY | libc::O_CLOEXEC | libc::O_NONBLOCK,
            )
        };
        if raw < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let actual = unsafe { File::from_raw_fd(raw) };
        binding.verify(&actual, deadline)?;
        require(
            label_matches(
                &current_label(&self.proc, ProcLabel::Selinux)?,
                domain.context().as_bytes(),
            ),
            "actual stopped query SELinux domain differs",
        )?;
        require(
            current_label(&self.proc, ProcLabel::AppArmor)? == AA_STACK,
            "actual stopped query lost the required AppArmor stack",
        )?;
        let observed = status(&self.proc)?;
        for (field, value) in [("Uid:", shell_uid), ("Gid:", shell_gid)] {
            let values = status_field(&observed, field)?
                .split_ascii_whitespace()
                .map(str::parse::<u32>)
                .collect::<std::result::Result<Vec<_>, _>>()
                .map_err(external)?;
            require(values == vec![value; 4], "stopped query credentials differ")?;
        }
        for field in ["CapInh:", "CapPrm:", "CapEff:", "CapAmb:"] {
            require(
                u64::from_str_radix(status_field(&observed, field)?, 16).map_err(external)? == 0,
                "stopped query retained process capabilities",
            )?;
        }
        require(
            status_field(&observed, "NoNewPrivs:")? == "1"
                && status_field(&observed, "Seccomp:")? == "2"
                && status_field(&observed, "Threads:")? == "1"
                && status_field(&observed, "Groups:")?.is_empty(),
            "actual stopped query privilege, filter or thread state differs",
        )?;
        self.original_owner()?;
        binding.verify(&actual, deadline)?;
        self.continue_original(deadline)?;
        Ok(ExecReceipt {
            query_start_ticks: self.original.1,
            original_parent_pid: self.original.0,
            tracer_tid: self.child.creator as u32,
            waitid_code: libc::CLD_TRAPPED,
            waitid_status: EXEC_EVENT,
            event_previous_tid: previous_tid,
            executable: binding.node,
            executable_mount_id: binding.mount_id,
            executable_sha256: binding
                .sha256
                .iter()
                .map(|byte| format!("{byte:02x}"))
                .collect(),
            executable_selinux: std::str::from_utf8(binding.label).expect("fixed ASCII role"),
            process_selinux: domain.context(),
            process_apparmor: "droidloom-production-android//&droidloom-production-broker (enforce)",
            uid: shell_uid,
            gid: shell_gid,
            no_new_privileges: true,
            seccomp_filter_mode: 2,
        })
    }
}
