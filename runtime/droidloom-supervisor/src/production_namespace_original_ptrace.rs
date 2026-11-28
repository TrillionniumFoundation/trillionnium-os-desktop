//! Short, original-task ptrace custody for native mount-namespace observation.
//!
//! This owner is created from the already owned CLONE_PARENT/PIDFD child.
//! It has no attach/seize, numeric-PID adoption, register-writing, signal
//! rewriting, syscall emulation, seccomp-suspension, or Ready interface.
//! The namespace coordinator must validate its complete mount graph before
//! it resumes an observed native exit or detaches this temporary observer.

use super::runtime::NativeStorageSnapshot;
use super::*;
use crate::production_apex_seccomp as wire;
use crate::production_execution::RuntimeMacOwner;
#[path = "production_namespace_native_mount_epoch.rs"]
mod mount_epoch;
use mount_epoch::NativeMountEpoch;
#[path = "production_namespace_default_mounts.rs"]
mod default_mounts;
use default_mounts::OriginalInitChange;
pub(crate) use default_mounts::{DefaultMountAuthority, DefaultMountBinding};
pub(super) use default_mounts::{DefaultMountOwner, OriginalBootstrapBindChange};
#[path = "production_namespace_native_successor.rs"]
mod successor;
pub(super) use successor::NativeSuccessors;
pub(crate) use successor::{ActualApexdGeneration, ActualApexdTask, NativeSyscallOutcome};

const TRACE_OPTIONS: usize = 1 | (1 << 4) | (1 << 20);
const GET_SYSCALL_INFO: usize = 0x420e;
const ARCH_X86_64: u32 = 0xc000_003e;
const SYSCALL_STOP: i32 = libc::SIGTRAP | 0x80;
const EXEC_STOP: i32 = libc::SIGTRAP | (4 << 8);
const MAX_STOPS: u64 = 1_000_000;
// Bionic pthread creation uses this scalar legacy-clone set. No PTRACE_O_TRACECLONE
// or CLONE_PTRACE is present; new property-service threads inherit the fixed
// syscall filter, not this temporary original-main-thread observer.
const ORIGINAL_PTHREAD_FLAGS: u64 = (libc::CLONE_VM
    | libc::CLONE_FS
    | libc::CLONE_FILES
    | libc::CLONE_SIGHAND
    | libc::CLONE_THREAD
    | libc::CLONE_SYSVSEM
    | libc::CLONE_SETTLS
    | libc::CLONE_PARENT_SETTID
    | libc::CLONE_CHILD_CLEARTID) as u64;

fn original_thread_clone(entry: Entry) -> bool {
    entry.number == libc::SYS_clone as u64 && entry.arguments[0] == ORIGINAL_PTHREAD_FLAGS
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct Entry {
    number: u64,
    arguments: [u64; 6],
    instruction_pointer: u64,
    stack_pointer: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct Exit {
    value: i64,
    error: bool,
}

impl Exit {
    fn namespace_errno(self) -> Result<i32> {
        match (self.error, self.value) {
            (false, 0) => Ok(0),
            (true, -4095..=-1) if ![-512, -513, -514, -516].contains(&self.value) => {
                Ok((-self.value) as i32)
            }
            _ => Err(NamespaceError::Rejected(
                "native namespace syscall returned an invalid result",
            )),
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum SyscallStop {
    Entry(Entry),
    Exit(Exit),
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) enum NativeKind {
    Unshare,
    RestoreBootstrap,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Phase {
    Prepared,
    StartRequested,
    AwaitExec,
    ExecStopped,
    ExecExit,
    Running,
    NativeEntry,
    NativeDetaching,
    NativeNotifying,
    NativeArming,
    NativeArmed,
    NativeRunning,
    NativeExit,
    Detached,
    Retired,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct Binding {
    identity: ProcessIdentity,
    proc: Node,
    pidfd: Node,
    user: Node,
    pid_namespace: Node,
    creator_tid: libc::pid_t,
    nonce: [u8; 16],
}

struct NativeCall {
    kind: NativeKind,
    entry: Entry,
    before: Node,
    // A duplicate of the actual descriptor in the stopped original task,
    // never a caller-supplied namespace descriptor.
    target: Option<File>,
    notification: Option<wire::Notification>,
    // Actual ENTRY detach and fresh ARM have separate irreversible journals.
    detach_attempted: bool,
    detached: bool,
    arm_attempted: bool,
    armed: bool,
    release_attempted: bool,
    released: bool,
    result: Option<Exit>,
    after: Option<File>,
    root_after: Option<File>,
}

struct Resources {
    context: RuntimeMacOwner,
    parent_pid: u32,
    uid_start: u32,
    gid_start: u32,
    uid_map: Vec<u8>,
    gid_map: Vec<u8>,
    namespaces: Vec<(libc::c_int, libc::c_ulong, File, Node)>,
    user: File,
    pidfd: OwnedFd,
    thread_pidfd: OwnedFd,
    thread_pidfd_node: Node,
    proc: File,
    bootstrap: File,
    bootstrap_root: File,
    default: Option<File>,
    default_root: Option<File>,
    epoch: Option<NativeMountEpoch>,
    listener: Option<Node>,
    binding: Binding,
    coordinator_proc: File,
    coordinator_identity: ProcessIdentity,
    coordinator_node: Node,
}

/// The data here is an actual stopped native result, not permission to accept
/// a changed mount inventory. The coordinator still owes its exact graph and
/// namespace-epoch checks before calling a resume/detach method.
pub(super) struct NativeExitObservation<'a> {
    call: &'a NativeCall,
    resources: &'a Resources,
}

impl NativeExitObservation<'_> {
    pub(super) fn errno(&self) -> Result<i32> {
        self.call
            .result
            .ok_or(NamespaceError::Rejected("native exit result absent"))?
            .namespace_errno()
    }

    pub(super) fn is_unshare(&self) -> bool {
        self.call.kind == NativeKind::Unshare
    }

    pub(super) fn before_namespace(&self) -> &File {
        match self.call.kind {
            NativeKind::Unshare => &self.resources.bootstrap,
            NativeKind::RestoreBootstrap => self.resources.default.as_ref().unwrap(),
        }
    }

    pub(super) fn after_namespace(&self) -> &File {
        self.call.after.as_ref().unwrap()
    }

    pub(super) fn actual_root(&self) -> &File {
        self.call.root_after.as_ref().unwrap()
    }
}

/// Neither Send nor Sync: the original RuntimeMacOwner retains its one Rc pair.
/// No descriptor or task identity is accepted from outside the original tree.
pub(super) struct OriginalPtrace {
    resources: Option<Box<Resources>>,
    deadline: Instant,
    phase: Phase,
    stops: u64,
    ordinary_entry: Option<Entry>,
    native: Option<NativeCall>,
    completed_unshare: bool,
    completed_restore: bool,
    failed: bool,
    traceme_recorded: bool,
    successors_issued: bool,
}

fn fd_node(fd: RawFd) -> Result<Node> {
    let mut value: libc::stat = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstat(fd, &mut value) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(Node {
        device: value.st_dev,
        inode: value.st_ino,
    })
}

fn binding(child: &TreeChild) -> Result<Binding> {
    Ok(Binding {
        identity: child.identity,
        proc: child.proc_node,
        pidfd: fd_node(child.pidfd.as_raw_fd())?,
        user: child.namespaces.user_node,
        pid_namespace: Node::of(child.pid_namespace())?,
        creator_tid: child.creator_tid,
        nonce: child.nonce,
    })
}

fn canonical_status_value<'a>(raw: &'a [u8], key: &str) -> Result<&'a str> {
    if raw.is_empty() || raw.len() > 8192 || raw.last() != Some(&b'\n') || raw.contains(&0) {
        return Err(NamespaceError::Rejected("complete original trace status"));
    }
    let text = std::str::from_utf8(raw)
        .map_err(|_| NamespaceError::Rejected("original trace status encoding"))?;
    let mut matches = text.lines().filter_map(|line| {
        line.strip_prefix(key)
            .map(|value| value.trim_matches(|c| c == ' ' || c == '\t'))
    });
    let value = matches.next().ok_or(NamespaceError::Rejected(
        "original trace status field absent",
    ))?;
    if matches.next().is_some() {
        return Err(NamespaceError::Rejected(
            "duplicate original trace status field",
        ));
    }
    Ok(value)
}

fn tracer(proc: &File, identity: ProcessIdentity, expected: libc::pid_t) -> Result<()> {
    let raw = read_proc(proc, "status")?;
    for (key, value) in [
        ("Pid:", identity.pid),
        ("Tgid:", identity.pid),
        ("TracerPid:", expected as u32),
    ] {
        if canonical_status_value(&raw, key)? != value.to_string() {
            return Err(NamespaceError::Rejected(
                "original task/tracer identity changed",
            ));
        }
    }
    Ok(())
}

fn decode_syscall_info(raw: &[u8; 88], returned: usize) -> Result<SyscallStop> {
    if raw[1..4] != [0, 0, 0] || u32::from_ne_bytes(raw[4..8].try_into().unwrap()) != ARCH_X86_64 {
        return Err(NamespaceError::Rejected("native syscall observation ABI"));
    }
    let word = |offset| u64::from_ne_bytes(raw[offset..offset + 8].try_into().unwrap());
    match (raw[0], returned) {
        (1, 80) => {
            let number = word(24);
            if number > i32::MAX as u64 || number & 0x4000_0000 != 0 {
                return Err(NamespaceError::Rejected(
                    "native syscall observation number",
                ));
            }
            Ok(SyscallStop::Entry(Entry {
                number,
                arguments: std::array::from_fn(|i| word(32 + i * 8)),
                instruction_pointer: word(8),
                stack_pointer: word(16),
            }))
        }
        (2, 33) => {
            if raw[32] > 1 {
                return Err(NamespaceError::Rejected("native syscall error flag"));
            }
            let value = word(24) as i64;
            if raw[32] == 1 && !(-4095..=-1).contains(&value) {
                return Err(NamespaceError::Rejected("native syscall errno encoding"));
            }
            Ok(SyscallStop::Exit(Exit {
                value,
                error: raw[32] != 0,
            }))
        }
        _ => Err(NamespaceError::Rejected(
            "unexpected native syscall stop layout",
        )),
    }
}

fn syscall_info(pid: u32) -> Result<SyscallStop> {
    let mut raw = [0_u8; 88];
    let count = unsafe {
        libc::syscall(
            libc::SYS_ptrace,
            GET_SYSCALL_INFO,
            pid as libc::pid_t,
            raw.len(),
            raw.as_mut_ptr(),
        )
    };
    if count < 0 {
        return Err(io::Error::last_os_error().into());
    }
    decode_syscall_info(&raw, count as usize)
}

fn native_exit(pid: u32, instruction_pointer: u64) -> Result<Exit> {
    let mut raw = [0_u8; 88];
    let count = unsafe {
        libc::syscall(
            libc::SYS_ptrace,
            GET_SYSCALL_INFO,
            pid as libc::pid_t,
            raw.len(),
            raw.as_mut_ptr(),
        )
    };
    if count < 0 {
        return Err(io::Error::last_os_error().into());
    }
    match decode_syscall_info(&raw, count as usize)? {
        SyscallStop::Exit(exit)
            if u64::from_ne_bytes(raw[8..16].try_into().unwrap()) == instruction_pointer =>
        {
            Ok(exit)
        }
        _ => Err(NamespaceError::Rejected(
            "original native EXIT instruction differs from ENTRY",
        )),
    }
}

fn control(pid: u32, request: libc::c_uint, data: usize) -> Result<()> {
    // The only state-changing ptrace operations this implementation contains.
    // No generic caller-selected command reaches the syscall.
    if !matches!(
        request,
        libc::PTRACE_SETOPTIONS | libc::PTRACE_CONT | libc::PTRACE_SYSCALL | libc::PTRACE_DETACH
    ) || (request == libc::PTRACE_SETOPTIONS && data != TRACE_OPTIONS)
        || (request != libc::PTRACE_SETOPTIONS && data > 64)
    {
        return Err(NamespaceError::Rejected(
            "ptrace operation outside fixed observer",
        ));
    }
    if unsafe { libc::syscall(libc::SYS_ptrace, request, pid as libc::pid_t, 0_usize, data) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(())
}

fn namespace_root(proc: &File) -> Result<File> {
    // This intentional proc magic-link follow is bound to the original held
    // process directory and actual current namespace, not a caller pathname.
    let fd = unsafe {
        libc::openat(
            proc.as_raw_fd(),
            c"root".as_ptr(),
            libc::O_PATH | libc::O_DIRECTORY | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(unsafe { File::from_raw_fd(fd) })
}

impl OriginalPtrace {
    pub(super) fn prepare(
        child: &TreeChild,
        context: RuntimeMacOwner,
        deadline: Instant,
    ) -> Result<Self> {
        if !cfg!(target_arch = "x86_64") || Instant::now() >= deadline {
            return Err(NamespaceError::Rejected(
                "original trace architecture/deadline",
            ));
        }
        child.verify()?;
        let coordinator_pid = unsafe { libc::getpid() } as u32;
        if unsafe { libc::syscall(libc::SYS_gettid) } != coordinator_pid as libc::c_long {
            return Err(NamespaceError::Rejected(
                "original trace requires its single broker leader",
            ));
        }
        let coordinator_proc = open_proc_at(
            &child.proc_root,
            &coordinator_pid.to_string(),
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        let coordinator_identity = read_identity(&coordinator_proc, coordinator_pid)?;
        if canonical_status_value(&read_proc(&coordinator_proc, "status")?, "Threads:")? != "1" {
            return Err(NamespaceError::Rejected(
                "original trace broker wait ownership is not unique",
            ));
        }
        context
            .objects()
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        tracer(&child.proc_dir, child.identity, 0)?;
        let bootstrap = from_pidfd(&child.pidfd, 0xff03, libc::CLONE_NEWNS)?;
        let bootstrap_root = namespace_root(&child.proc_dir)?;
        let original = binding(child)?;
        require_namespace_owner(&bootstrap, original.user)?;
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, child.identity.pid, PIDFD_THREAD) };
        if raw < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let thread_pidfd = unsafe { OwnedFd::from_raw_fd(raw as i32) };
        let thread_info = pidfd_info(thread_pidfd.as_raw_fd())?;
        if thread_info.pid != child.identity.pid
            || thread_info.tgid != child.identity.pid
            || thread_info.ppid != child.parent_pid
        {
            return Err(NamespaceError::Rejected(
                "original thread PIDFD identity differs",
            ));
        }
        require_pidfd_creds(&thread_info, child.uids.start, child.gids.start)?;
        child.verify()?;
        let value = Self {
            resources: Some(Box::new(Resources {
                context,
                parent_pid: child.parent_pid,
                uid_start: child.uids.start,
                gid_start: child.gids.start,
                uid_map: read_proc(&child.proc_dir, "uid_map")?,
                gid_map: read_proc(&child.proc_dir, "gid_map")?,
                namespaces: child
                    .namespaces
                    .held
                    .iter()
                    .map(|(_, kind, command, file, node)| {
                        Ok((*kind, *command, file.try_clone()?, *node))
                    })
                    .collect::<Result<_>>()?,
                user: child.namespaces.userns.try_clone()?,
                pidfd: child.pidfd.try_clone()?,
                thread_pidfd_node: fd_node(thread_pidfd.as_raw_fd())?,
                thread_pidfd,
                proc: child.proc_dir.try_clone()?,
                bootstrap,
                bootstrap_root,
                default: None,
                default_root: None,
                epoch: None,
                listener: None,
                binding: original,
                coordinator_node: Node::of(&coordinator_proc)?,
                coordinator_proc,
                coordinator_identity,
            })),
            deadline,
            phase: Phase::Prepared,
            stops: 0,
            ordinary_entry: None,
            native: None,
            completed_unshare: false,
            completed_restore: false,
            failed: false,
            traceme_recorded: false,
            successors_issued: false,
        };
        value.check()?;
        tracer(&child.proc_dir, child.identity, 0)?;
        child.verify()?;
        Ok(value)
    }

    fn step<T>(&mut self, operation: impl FnOnce(&mut Self) -> Result<T>) -> Result<T> {
        self.before()?;
        let result = operation(self);
        if result.is_err() {
            // A consumed stop or partially performed ptrace operation is not
            // replayable. The original owner retains every descriptor until
            // actual tree retirement, including failures after a syscall ran.
            self.failed = true;
        }
        result
    }

    fn check_mount_phase(&self, actual: Node) -> Result<()> {
        let r = self.held()?;
        let bootstrap = Node::of(&r.bootstrap)?;
        let current = if self.completed_unshare && !self.completed_restore {
            Node::of(r.default.as_ref().ok_or(NamespaceError::Rejected(
                "completed unshare lost its actual default namespace",
            ))?)?
        } else {
            bootstrap
        };
        let expected = match self.phase {
            Phase::NativeEntry
            | Phase::NativeDetaching
            | Phase::NativeNotifying
            | Phase::NativeArming
            | Phase::NativeArmed => {
                let call = self
                    .native
                    .as_ref()
                    .ok_or(NamespaceError::Rejected("native call absent"))?;
                if call.before != current {
                    return Err(NamespaceError::Rejected(
                        "native entry belongs to another namespace epoch",
                    ));
                }
                Some(call.before)
            }
            Phase::NativeRunning => {
                // This state issues no namespace witness. The original syscall
                // alone is in flight; its mandatory exit-stop separately binds
                // the actual result and retained new namespace before use.
                let call = self
                    .native
                    .as_ref()
                    .ok_or(NamespaceError::Rejected("native call absent"))?;
                if call.before != current || call.result.is_some() || call.after.is_some() {
                    return Err(NamespaceError::Rejected("native in-flight journal differs"));
                }
                if call.kind == NativeKind::RestoreBootstrap
                    && actual != call.before
                    && actual != bootstrap
                {
                    return Err(NamespaceError::Rejected(
                        "in-flight restore entered a foreign namespace",
                    ));
                }
                None
            }
            Phase::NativeExit => Some(Node::of(
                self.native
                    .as_ref()
                    .and_then(|call| call.after.as_ref())
                    .ok_or(NamespaceError::Rejected(
                        "actual native exit namespace absent",
                    ))?,
            )?),
            Phase::Retired => return Err(NamespaceError::RetirementUnproven),
            _ => Some(current),
        };
        if expected.is_some_and(|node| node != actual) {
            return Err(NamespaceError::Rejected(
                "actual mount namespace differs from its precise trace phase",
            ));
        }
        Ok(())
    }

    pub(super) fn matches_original(&self, child: &TreeChild) -> Result<()> {
        self.check()?;
        if binding(child)? != self.held()?.binding {
            return Err(NamespaceError::Rejected(
                "trace belongs to another original tree",
            ));
        }
        self.before()
    }

    pub(super) fn mark_start_requested(&mut self) -> Result<()> {
        self.step(Self::mark_start_requested_inner)
    }

    pub(super) fn confirm_traceme_record(&mut self, child: &TreeChild) -> Result<()> {
        self.step(|this| {
            if this.phase != Phase::StartRequested || this.traceme_recorded {
                return Err(NamespaceError::Rejected(
                    "original TRACEME record phase or replay",
                ));
            }
            this.matches_original(child)?;
            // receive_phase validates the original nonce, exact SCM peer,
            // mapped identities and successful phase. The raw child emits
            // this record only after its own TRACEME syscall returned zero.
            child.receive_phase(super::Phase::OriginalTraceReady)?;
            this.check_traced()?;
            this.traceme_recorded = true;
            this.before()
        })
    }

    pub(super) fn accept_traceme(&mut self) -> Result<bool> {
        self.step(Self::accept_traceme_inner)
    }

    pub(super) fn accept_exec_stop(&mut self) -> Result<bool> {
        self.step(Self::accept_exec_stop_inner)
    }

    pub(super) fn start_syscalls(
        &mut self,
        runtime: &super::runtime::RuntimeObservation,
    ) -> Result<()> {
        self.step(|this| this.start_syscalls_inner(runtime))
    }

    pub(super) fn pump_ordinary(&mut self) -> Result<bool> {
        self.step(Self::pump_ordinary_inner)
    }

    pub(super) fn begin_unshare(&mut self, snapshot: NativeStorageSnapshot) -> Result<()> {
        self.step(|this| this.begin_unshare_inner(snapshot))
    }

    pub(super) fn begin_restore_bootstrap(&mut self) -> Result<()> {
        self.step(Self::begin_restore_bootstrap_inner)
    }

    pub(super) fn observe_native_exit(&mut self) -> Result<bool> {
        self.step(Self::observe_native_exit_inner)
    }

    pub(super) fn resume_after_unshare(&mut self) -> Result<()> {
        self.step(Self::resume_after_unshare_inner)
    }

    pub(super) fn detach_after_restore(&mut self) -> Result<()> {
        self.step(Self::detach_after_restore_inner)
    }

    pub(super) fn bind_listener(&mut self, listener: Node) -> Result<()> {
        self.step(|this| {
            this.check()?;
            if this.phase != Phase::Prepared || this.held()?.listener.is_some() {
                return Err(NamespaceError::Rejected(
                    "original trace listener cannot be rebound",
                ));
            }
            this.resources.as_mut().unwrap().listener = Some(listener);
            Ok(())
        })
    }

    pub(super) fn matches_listener(
        &self,
        identity: ProcessIdentity,
        nonce: [u8; 16],
        pidfd: Node,
        proc: Node,
        listener: Node,
    ) -> Result<()> {
        self.check()?;
        let r = self.held()?;
        if r.binding.identity != identity
            || r.binding.nonce != nonce
            || r.binding.pidfd != pidfd
            || r.binding.proc != proc
            || r.listener != Some(listener)
        {
            return Err(NamespaceError::Rejected(
                "native notification is not the original inherited listener",
            ));
        }
        self.before()
    }

    pub(super) fn matches_deadline(&self, end: Instant) -> Result<()> {
        self.before()?;
        if self.deadline != end {
            return Err(NamespaceError::Rejected(
                "native observer deadline was replaced",
            ));
        }
        Ok(())
    }

    pub(super) fn next_native_kind(&self) -> Result<Option<NativeKind>> {
        self.check_traced()?;
        Ok(if self.phase == Phase::NativeEntry {
            Some(
                self.native
                    .as_ref()
                    .ok_or(NamespaceError::RetirementUnproven)?
                    .kind,
            )
        } else {
            None
        })
    }

    pub(super) fn notification_pump(&mut self) -> Result<()> {
        self.step(|this| match this.phase {
            Phase::NativeNotifying => {
                // The exact resumed entry must reach its inherited NOTIFY.
                // It cannot execute or change namespace before this method's
                // separate, typed continuation is actually sent.
                this.check_untraced()
            }
            Phase::Detached => {
                this.check()?;
                let r = this.held()?;
                tracer(&r.proc, r.binding.identity, 0)
            }
            Phase::ExecExit | Phase::Running => {
                if this.pump_ordinary_inner()? {
                    return Err(NamespaceError::Rejected(
                        "native entry reached an unrelated notification dispatcher",
                    ));
                }
                Ok(())
            }
            _ => Err(NamespaceError::Rejected(
                "notification wait has no active original trace phase",
            )),
        })
    }

    pub(super) fn check_notification(&self, notification: &wire::Notification) -> Result<()> {
        match self.phase {
            Phase::NativeNotifying => self.check_untraced()?,
            Phase::NativeArmed | Phase::NativeRunning => self.check_traced()?,
            _ => {
                return Err(NamespaceError::Rejected(
                    "original native notification phase",
                ));
            }
        }
        let call = self
            .native
            .as_ref()
            .ok_or(NamespaceError::Rejected("native call absent"))?;
        if !call.detach_attempted
            || !call.detached
            || notification.pid != self.held()?.binding.identity.pid
            || notification.flags != 0
            || notification.data.arch != ARCH_X86_64
            || notification.data.nr as i64 != call.entry.number as i64
            || notification.data.instruction_pointer != call.entry.instruction_pointer
            || notification.data.args != call.entry.arguments
            || match call.kind {
                NativeKind::Unshare => {
                    notification.operation() != Some(wire::Operation::Unshare)
                        || notification.data.args[0] != libc::CLONE_NEWNS as u64
                }
                NativeKind::RestoreBootstrap => {
                    notification.operation() != Some(wire::Operation::SetNamespace)
                        || notification.data.args[0] == 0
                        || notification.data.args[0] > i32::MAX as u64
                        || notification.data.args[1] != libc::CLONE_NEWNS as u64
                }
            }
        {
            return Err(NamespaceError::Rejected(
                "real notification differs from the original fixed native entry",
            ));
        }
        self.before()
    }

    pub(super) fn original_mount_barrier(
        &self,
        child: &TreeChild,
        listener: Node,
        notification: &wire::Notification,
    ) -> Result<()> {
        self.matches_original(child)?;
        self.check_traced()?;
        let entry = self.ordinary_entry.ok_or(NamespaceError::Rejected(
            "original mount has no actual syscall entry",
        ))?;
        if self.phase != Phase::Running
            || self.native.is_some()
            || self.held()?.listener != Some(listener)
            || notification.pid != self.held()?.binding.identity.pid
            || notification.flags != 0
            || notification.data.arch != ARCH_X86_64
            || notification.operation() != Some(wire::Operation::Mount)
            || entry.number != libc::SYS_mount as u64
            || notification.data.nr as u64 != entry.number
            || notification.data.instruction_pointer != entry.instruction_pointer
            || notification.data.args != entry.arguments
        {
            return Err(NamespaceError::Rejected(
                "original mount notification lost its real entry",
            ));
        }
        self.before()
    }

    /// Reattach only through the fixed kernel operation on this exact pending
    /// notification. The prior entry observer has already detached normally;
    /// the kernel admits no pre-existing tracer and checks the held thread
    /// PIDFD against its successfully delivered notification task.
    pub(super) fn arm_native_notification(
        &mut self,
        listener: &File,
        notification: &wire::Notification,
    ) -> Result<()> {
        self.step(|this| {
            if this.phase != Phase::NativeNotifying
                || this.native.as_ref().is_none_or(|call| {
                    !call.detached
                        || call.arm_attempted
                        || call.armed
                        || call.notification.is_some()
                })
            {
                return Err(NamespaceError::Rejected(
                    "original native ARM phase or replay",
                ));
            }
            this.check_notification(notification)?;
            if Some(Node::of(listener)?) != this.held()?.listener {
                return Err(NamespaceError::Rejected(
                    "original native ARM listener differs",
                ));
            }
            let id = notification.id;
            if unsafe { libc::ioctl(listener.as_raw_fd(), wire::ID_VALID, &id) } != 0 {
                return Err(io::Error::last_os_error().into());
            }
            let call = this.native.as_ref().unwrap();
            let request = wire::ArmNativeExit {
                id,
                pidfd: this.held()?.thread_pidfd.as_raw_fd(),
                mntns_fd: call.target.as_ref().map_or(-1, AsRawFd::as_raw_fd),
                flags: 0,
                reserved: 0,
            };
            let call = this.native.as_mut().unwrap();
            call.notification = Some(*notification);
            call.arm_attempted = true;
            this.phase = Phase::NativeArming;
            let code =
                unsafe { libc::ioctl(listener.as_raw_fd(), wire::ARM_NATIVE_EXIT, &request) };
            let error = io::Error::last_os_error();
            if code != 0 {
                return Err(error.into());
            }
            // There is no fallible copyout after the kernel's attach commit.
            // Preserve that real ownership before any postcondition can fail.
            this.native.as_mut().unwrap().armed = true;
            this.phase = Phase::NativeArmed;
            this.check_notification(notification)?;
            if unsafe { libc::ioctl(listener.as_raw_fd(), wire::ID_VALID, &id) } != 0 {
                return Err(io::Error::last_os_error().into());
            }
            this.before()
        })
    }

    /// This journal is written before the actual SEND. It cannot be retried;
    /// the result remains unqualified until a private kernel-send receipt and
    /// the real syscall exit arrive. The original inherited filter is unchanged.
    pub(super) fn before_native_continue(
        &mut self,
        notification: &wire::Notification,
    ) -> Result<()> {
        self.step(|this| {
            if this.phase != Phase::NativeArmed
                || this.native.as_ref().is_none_or(|call| {
                    !call.armed
                        || !call.arm_attempted
                        || call.release_attempted
                        || call.released
                        || call.notification.as_ref() != Some(notification)
                })
            {
                return Err(NamespaceError::Rejected(
                    "native continuation phase or replay",
                ));
            }
            this.check_notification(notification)?;
            // Other original init threads are allowed. The fixed ARM/native
            // fdget guard binds the actual setns file; the one listener and
            // held broker actor ledger serialize every mount/root mutation.
            let call = this.native.as_ref().unwrap();
            if call.kind == NativeKind::RestoreBootstrap {
                let raw = unsafe {
                    libc::syscall(
                        libc::SYS_pidfd_getfd,
                        this.held()?.pidfd.as_raw_fd(),
                        call.entry.arguments[0] as i32,
                        0,
                    )
                };
                if raw < 0 {
                    return Err(io::Error::last_os_error().into());
                }
                let target = unsafe { File::from_raw_fd(raw as i32) };
                if Node::of(&target)?
                    != Node::of(call.target.as_ref().ok_or(NamespaceError::Rejected(
                        "actual native target custody absent",
                    ))?)?
                    || Node::of(&target)? != Node::of(&this.held()?.bootstrap)?
                    || filesystem_kind(&target)? != NSFS_MAGIC
                    || unsafe { libc::ioctl(target.as_raw_fd(), NS_GET_NSTYPE) }
                        != libc::CLONE_NEWNS
                {
                    return Err(NamespaceError::Rejected(
                        "original pending setns descriptor changed",
                    ));
                }
                require_namespace_owner(&target, this.held()?.binding.user)?;
            }
            this.check_notification(notification)?;
            let call = this.native.as_mut().unwrap();
            call.notification = Some(*notification);
            call.release_attempted = true;
            // Set the in-flight state BEFORE SEND: the original task can reach
            // its exit-stop immediately after the kernel accepts CONTINUE.
            this.phase = Phase::NativeRunning;
            Ok(())
        })
    }

    pub(super) fn native_continue_applied(
        &mut self,
        receipt: super::apex_notifications::NativeContinueReceipt,
    ) -> Result<()> {
        self.step(|this| {
            receipt.validate_original(this)?;
            if this.phase != Phase::NativeRunning {
                return Err(NamespaceError::Rejected(
                    "actual continuation receipt phase",
                ));
            }
            let call = this
                .native
                .as_mut()
                .ok_or(NamespaceError::RetirementUnproven)?;
            if !call.release_attempted
                || call.released
                || call.notification.as_ref() != Some(receipt.notification())
            {
                return Err(NamespaceError::Rejected(
                    "actual continuation receipt was replayed or changed",
                ));
            }
            call.released = true;
            this.check_traced()
        })
    }

    pub(super) fn continuation_failed(&mut self) {
        // The original tree remains the sole kill/reap owner.
        self.failed = true;
    }

    fn held(&self) -> Result<&Resources> {
        self.resources
            .as_deref()
            .ok_or(NamespaceError::RetirementUnproven)
    }

    fn before(&self) -> Result<()> {
        if Instant::now() >= self.deadline || self.phase == Phase::Retired || self.failed {
            return Err(NamespaceError::Rejected(
                "original ptrace deadline or retirement",
            ));
        }
        Ok(())
    }

    fn check(&self) -> Result<()> {
        self.before()?;
        let r = self.held()?;
        r.context
            .objects()
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        if Node::of(&r.coordinator_proc)? != r.coordinator_node
            || read_identity(&r.coordinator_proc, r.coordinator_identity.pid)?
                != r.coordinator_identity
            || canonical_status_value(&read_proc(&r.coordinator_proc, "status")?, "Threads:")?
                != "1"
        {
            return Err(NamespaceError::Rejected(
                "original broker wait ownership changed",
            ));
        }
        tracer(&r.coordinator_proc, r.coordinator_identity, 0)?;
        if unsafe { libc::syscall(libc::SYS_gettid) } != r.binding.creator_tid as libc::c_long
            || fd_node(r.pidfd.as_raw_fd())? != r.binding.pidfd
            || fd_node(r.thread_pidfd.as_raw_fd())? != r.thread_pidfd_node
            || pidfd_exited(&r.thread_pidfd)?
            || Node::of(&r.proc)? != r.binding.proc
            || read_identity(&r.proc, r.binding.identity.pid)? != r.binding.identity
            || pidfd_exited(&r.pidfd)?
        {
            return Err(NamespaceError::Rejected(
                "original traced task custody changed",
            ));
        }
        let info = pidfd_info(r.pidfd.as_raw_fd())?;
        if info.pid != r.binding.identity.pid
            || info.tgid != r.binding.identity.pid
            || info.ppid != r.parent_pid
        {
            return Err(NamespaceError::Rejected(
                "original traced PIDFD generation changed",
            ));
        }
        require_pidfd_creds(&info, r.uid_start, r.gid_start)?;
        let thread_info = pidfd_info(r.thread_pidfd.as_raw_fd())?;
        if thread_info.pid != info.pid
            || thread_info.tgid != info.tgid
            || thread_info.ppid != info.ppid
        {
            return Err(NamespaceError::Rejected(
                "original thread PIDFD generation changed",
            ));
        }
        require_pidfd_creds(&thread_info, r.uid_start, r.gid_start)?;
        let user = from_pidfd(&r.pidfd, 0xff09, libc::CLONE_NEWUSER)?;
        if Node::of(&user)? != r.binding.user || Node::of(&r.user)? != r.binding.user {
            return Err(NamespaceError::Rejected(
                "original traced user namespace changed",
            ));
        }
        for (kind, command, original, node) in &r.namespaces {
            let actual = from_pidfd(&r.pidfd, *command, *kind)?;
            require_namespace_owner(&actual, r.binding.user)?;
            if Node::of(original)? != *node {
                return Err(NamespaceError::Rejected("held original namespace changed"));
            }
            if *kind == libc::CLONE_NEWNS {
                self.check_mount_phase(Node::of(&actual)?)?;
            } else if Node::of(&actual)? != *node {
                return Err(NamespaceError::Rejected(
                    "unrelated traced namespace changed",
                ));
            }
        }
        if read_proc(&r.proc, "uid_map")? != r.uid_map
            || read_proc(&r.proc, "gid_map")? != r.gid_map
        {
            return Err(NamespaceError::Rejected(
                "original traced identity mappings changed",
            ));
        }
        if read_proc(&r.proc, "setgroups")? != b"allow\n" {
            return Err(NamespaceError::Rejected(
                "original traced setgroups policy changed",
            ));
        }
        self.before()
    }

    fn check_untraced(&self) -> Result<()> {
        self.check()?;
        let r = self.held()?;
        tracer(&r.proc, r.binding.identity, 0)?;
        self.before()
    }

    fn check_traced(&self) -> Result<()> {
        self.check()?;
        let r = self.held()?;
        tracer(&r.proc, r.binding.identity, r.binding.creator_tid)?;
        self.before()
    }

    fn stop(&mut self) -> Result<Option<i32>> {
        self.check_traced()?;
        let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
        // Only stopped events are consumed here. The tree's existing original
        // PIDFD retirement remains the sole consumer of WEXITED/reap.
        let options = libc::WSTOPPED | libc::WNOHANG | libc::__WALL | libc::__WNOTHREAD;
        if unsafe {
            libc::waitid(
                libc::P_PIDFD,
                self.held()?.pidfd.as_raw_fd() as u32,
                &mut info,
                options,
            )
        } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
        let pid = unsafe { info.si_pid() };
        if pid == 0 {
            self.before()?;
            return Ok(None);
        }
        if pid != self.held()?.binding.identity.pid as i32
            || info.si_signo != libc::SIGCHLD
            || info.si_errno != 0
            || info.si_code != libc::CLD_TRAPPED
        {
            return Err(NamespaceError::Rejected(
                "unexpected original PIDFD stop event",
            ));
        }
        self.stops = self
            .stops
            .checked_add(1)
            .ok_or(NamespaceError::Rejected("ptrace stop overflow"))?;
        if self.stops > MAX_STOPS {
            return Err(NamespaceError::Rejected(
                "original ptrace observation bound",
            ));
        }
        self.check_traced()?;
        Ok(Some(unsafe { info.si_status() }))
    }

    /// Called only after storing this owner, before releasing the original
    /// raw child into its fixed TRACEME/STOP handshake.
    fn mark_start_requested_inner(&mut self) -> Result<()> {
        self.check()?;
        if self.phase != Phase::Prepared {
            return Err(NamespaceError::Rejected("original ptrace start replay"));
        }
        tracer(&self.held()?.proc, self.held()?.binding.identity, 0)?;
        self.phase = Phase::StartRequested;
        Ok(())
    }

    fn accept_traceme_inner(&mut self) -> Result<bool> {
        if self.phase != Phase::StartRequested || !self.traceme_recorded {
            return Err(NamespaceError::Rejected("original TRACEME phase"));
        }
        let Some(status) = self.stop()? else {
            return Ok(false);
        };
        if status != libc::SIGSTOP {
            return Err(NamespaceError::Rejected(
                "original raw trace barrier differs",
            ));
        }
        control(
            self.held()?.binding.identity.pid,
            libc::PTRACE_SETOPTIONS,
            TRACE_OPTIONS,
        )?;
        self.check_traced()?;
        control(self.held()?.binding.identity.pid, libc::PTRACE_CONT, 0)?;
        self.phase = Phase::AwaitExec;
        self.before()?;
        Ok(true)
    }

    fn accept_exec_stop_inner(&mut self) -> Result<bool> {
        if self.phase != Phase::AwaitExec {
            return Err(NamespaceError::Rejected("original exec-stop phase"));
        }
        let Some(status) = self.stop()? else {
            return Ok(false);
        };
        if status != EXEC_STOP {
            return Err(NamespaceError::Rejected(
                "original trace did not reach exec event",
            ));
        }
        let mut old_tid = 0_usize;
        if unsafe {
            libc::syscall(
                libc::SYS_ptrace,
                libc::PTRACE_GETEVENTMSG,
                self.held()?.binding.identity.pid as libc::pid_t,
                0_usize,
                &mut old_tid,
            )
        } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
        if old_tid != self.held()?.binding.identity.pid as usize {
            return Err(NamespaceError::Rejected(
                "original exec changed task identity",
            ));
        }
        self.phase = Phase::ExecStopped;
        self.check_traced()?;
        Ok(true)
    }

    /// The caller must first use the normal ExecArmed/CLOEXEC/original ELF
    /// observation while the actual task remains in this exec-stop.
    fn start_syscalls_inner(&mut self, runtime: &super::runtime::RuntimeObservation) -> Result<()> {
        if self.phase != Phase::ExecStopped {
            return Err(NamespaceError::Rejected(
                "original syscall observation start phase",
            ));
        }
        self.check_traced()?;
        let fd = unsafe {
            libc::openat(
                self.held()?.proc.as_raw_fd(),
                c"exe".as_ptr(),
                libc::O_PATH | libc::O_CLOEXEC,
            )
        };
        if fd < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let executable = unsafe { File::from_raw_fd(fd) };
        runtime.verify_executable_target(&executable)?;
        self.check_traced()?;
        control(self.held()?.binding.identity.pid, libc::PTRACE_SYSCALL, 0)?;
        self.phase = Phase::ExecExit;
        self.before()
    }

    fn forward_signal(&mut self, signal: i32) -> Result<()> {
        if !(1..=64).contains(&signal)
            || matches!(
                signal,
                libc::SIGSTOP | libc::SIGTSTP | libc::SIGTTIN | libc::SIGTTOU
            )
        {
            // A short preparation cannot silently consume job-control stops.
            // Its caller retires the original tree on this unsupported event.
            return Err(NamespaceError::Rejected(
                "unsupported original trace signal stop",
            ));
        }
        let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
        if unsafe {
            libc::syscall(
                libc::SYS_ptrace,
                libc::PTRACE_GETSIGINFO,
                self.held()?.binding.identity.pid as libc::pid_t,
                0_usize,
                &mut info,
            )
        } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
        if info.si_signo != signal {
            return Err(NamespaceError::Rejected(
                "original signal-delivery stop differs",
            ));
        }
        self.check_traced()?;
        // Same signal number preserves the kernel's original siginfo. No
        // SETSIGINFO, handler execution, or result/register write occurs here.
        control(
            self.held()?.binding.identity.pid,
            libc::PTRACE_SYSCALL,
            signal as usize,
        )
    }

    /// Service ordinary entry/exit and genuine signal-delivery stops while an
    /// inherited USER_NOTIF receiver waits. Native namespace entries stay
    /// stopped for the separate finite coordinator, never auto-resumed.
    fn pump_ordinary_inner(&mut self) -> Result<bool> {
        if matches!(self.phase, Phase::NativeEntry | Phase::NativeExit) {
            self.check_traced()?;
            return Ok(true);
        }
        if !matches!(self.phase, Phase::ExecExit | Phase::Running) {
            return Err(NamespaceError::Rejected("ordinary trace pump phase"));
        }
        for _ in 0..128 {
            let Some(status) = self.stop()? else {
                return Ok(false);
            };
            if status != SYSCALL_STOP {
                if status & !0x7f != 0 {
                    return Err(NamespaceError::Rejected("unexpected original ptrace event"));
                }
                self.forward_signal(status)?;
                continue;
            }
            let observed = syscall_info(self.held()?.binding.identity.pid)?;
            match (self.phase, observed) {
                (Phase::ExecExit, SyscallStop::Exit(exit))
                    if exit
                        == (Exit {
                            value: 0,
                            error: false,
                        }) =>
                {
                    self.phase = Phase::Running;
                }
                (Phase::Running, SyscallStop::Entry(entry)) if self.ordinary_entry.is_none() => {
                    if matches!(
                        entry.number as libc::c_long,
                        libc::SYS_unshare | libc::SYS_setns
                    ) {
                        self.native = Some(NativeCall {
                            kind: if entry.number == libc::SYS_unshare as u64 {
                                NativeKind::Unshare
                            } else {
                                NativeKind::RestoreBootstrap
                            },
                            entry,
                            before: Node::of(&from_pidfd(
                                &self.held()?.pidfd,
                                0xff03,
                                libc::CLONE_NEWNS,
                            )?)?,
                            target: None,
                            notification: None,
                            detach_attempted: false,
                            detached: false,
                            arm_attempted: false,
                            armed: false,
                            release_attempted: false,
                            released: false,
                            result: None,
                            after: None,
                            root_after: None,
                        });
                        self.phase = Phase::NativeEntry;
                        self.check_traced()?;
                        return Ok(true);
                    }
                    // Original CP3A starts property-service pthreads before
                    // SetupMountNamespaces. Admit its exact scalar thread
                    // clone without tracing heirs. Their mount/root mutations
                    // still require the same original, nonreplaceable listener.
                    if (entry.number == libc::SYS_clone as u64 && !original_thread_clone(entry))
                        || matches!(
                            entry.number as libc::c_long,
                            libc::SYS_fork
                                | libc::SYS_vfork
                                | libc::SYS_execve
                                | libc::SYS_execveat
                                | libc::SYS_chroot
                                | libc::SYS_pivot_root
                                | libc::SYS_fsopen
                                | libc::SYS_fsconfig
                                | libc::SYS_fspick
                                | libc::SYS_fsmount
                                | libc::SYS_open_tree
                                | libc::SYS_move_mount
                                | libc::SYS_mount_setattr
                                | 467 // fixed open_tree_attr, pinned final x86-64 table
                        )
                    {
                        return Err(NamespaceError::Rejected(
                            "foreign task or mount mutation during original namespace trace",
                        ));
                    }
                    if self.completed_unshare
                        && matches!(
                            entry.number as libc::c_long,
                            libc::SYS_mount | libc::SYS_umount2
                        )
                    {
                        return Err(NamespaceError::Rejected(
                            "unexpected mount operation before original bootstrap restoration",
                        ));
                    }
                    self.ordinary_entry = Some(entry);
                }
                (Phase::Running, SyscallStop::Exit(exit)) if self.ordinary_entry.is_some() => {
                    if self.ordinary_entry.as_ref().unwrap().number == libc::SYS_clone3 as u64
                        && exit
                            != (Exit {
                                value: -(libc::ENOSYS as i64),
                                error: true,
                            })
                    {
                        return Err(NamespaceError::Rejected(
                            "original fixed clone3 filter changed",
                        ));
                    }
                    self.ordinary_entry.take();
                }
                _ => {
                    return Err(NamespaceError::Rejected(
                        "original syscall entry/exit sequence",
                    ));
                }
            }
            self.check_traced()?;
            control(self.held()?.binding.identity.pid, libc::PTRACE_SYSCALL, 0)?;
        }
        self.before()?;
        Ok(false)
    }

    fn original_native_entry(&self) -> Result<Entry> {
        self.check_traced()?;
        if self.phase != Phase::NativeEntry {
            return Err(NamespaceError::Rejected(
                "native entry is not actually stopped",
            ));
        }
        let entry = self.native.as_ref().unwrap().entry;
        if syscall_info(self.held()?.binding.identity.pid)? != SyscallStop::Entry(entry) {
            return Err(NamespaceError::Rejected(
                "original stopped native arguments changed",
            ));
        }
        // The original main thread is really syscall-stopped. Its siblings
        // inherit the same complete mount/root notification filter; the
        // coordinator separately holds the original broker actor ledger.
        self.check_traced()?;
        if syscall_info(self.held()?.binding.identity.pid)? != SyscallStop::Entry(entry) {
            return Err(NamespaceError::Rejected(
                "original native stop changed during actor check",
            ));
        }
        Ok(entry)
    }

    /// Finish the original entry observation with a normal stopped DETACH.
    /// The inherited USER_NOTIF still runs before the native syscall. A new
    /// ARM must establish the exit observer on that exact received request.
    fn detach_native_entry(&mut self, entry: Entry) -> Result<()> {
        if self.original_native_entry()? != entry
            || self.native.as_ref().is_none_or(|call| {
                call.detach_attempted || call.detached || call.arm_attempted || call.armed
            })
        {
            return Err(NamespaceError::Rejected(
                "original native entry detach replay",
            ));
        }
        self.native.as_mut().unwrap().detach_attempted = true;
        self.phase = Phase::NativeDetaching;
        control(self.held()?.binding.identity.pid, libc::PTRACE_DETACH, 0)?;
        // Normal DETACH removes the original ptrace options in the kernel.
        // Never accept its return as evidence that the syscall has executed.
        self.native.as_mut().unwrap().detached = true;
        self.phase = Phase::NativeNotifying;
        self.check_untraced()?;
        self.before()
    }

    /// Only the original task's exact NEWNS unshare is resumed. This method
    /// is not a general ptrace syscall continuation API.
    fn begin_unshare_inner(&mut self, snapshot: NativeStorageSnapshot) -> Result<()> {
        let entry = self.original_native_entry()?;
        if self.completed_unshare
            || self.completed_restore
            || self.held()?.default.is_some()
            || entry.number != libc::SYS_unshare as u64
            || entry.arguments[0] != libc::CLONE_NEWNS as u64
            || self.native.as_ref().unwrap().before != Node::of(&self.held()?.bootstrap)?
        {
            return Err(NamespaceError::Rejected(
                "original fixed mount unshare differs",
            ));
        }
        self.native.as_mut().unwrap().kind = NativeKind::Unshare;
        if self.held()?.epoch.is_some() {
            return Err(NamespaceError::Rejected("native epoch already attempted"));
        }
        let epoch = NativeMountEpoch::begin(snapshot, self.held()?)?;
        self.resources.as_mut().unwrap().epoch = Some(epoch);
        if self.original_native_entry()? != entry {
            return Err(NamespaceError::Rejected(
                "original unshare entry changed during epoch capture",
            ));
        }
        self.detach_native_entry(entry)
    }

    /// The FD number comes only from the real stopped syscall registers. It
    /// is duplicated through the original PIDFD and compared with bootstrap.
    fn begin_restore_bootstrap_inner(&mut self) -> Result<()> {
        let entry = self.original_native_entry()?;
        if !self.completed_unshare
            || self.completed_restore
            || entry.number != libc::SYS_setns as u64
            || entry.arguments[0] == 0
            || entry.arguments[0] > i32::MAX as u64
            || entry.arguments[1] != libc::CLONE_NEWNS as u64
            || self.native.as_ref().unwrap().before
                != Node::of(
                    self.held()?
                        .default
                        .as_ref()
                        .ok_or(NamespaceError::Rejected("owned default namespace absent"))?,
                )?
        {
            return Err(NamespaceError::Rejected("original bootstrap setns differs"));
        }
        let root = namespace_root(&self.held()?.proc)?;
        self.held()?
            .epoch
            .as_ref()
            .ok_or(NamespaceError::Rejected("native epoch absent"))?
            .verify_default(&self.held()?.proc, &root)?;
        let raw = unsafe {
            libc::syscall(
                libc::SYS_pidfd_getfd,
                self.held()?.pidfd.as_raw_fd(),
                entry.arguments[0] as i32,
                0,
            )
        };
        if raw < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let target = unsafe { File::from_raw_fd(raw as i32) };
        if filesystem_kind(&target)? != NSFS_MAGIC
            || unsafe { libc::ioctl(target.as_raw_fd(), NS_GET_NSTYPE) } != libc::CLONE_NEWNS
            || Node::of(&target)? != Node::of(&self.held()?.bootstrap)?
        {
            return Err(NamespaceError::Rejected(
                "original setns FD is not held bootstrap",
            ));
        }
        require_namespace_owner(&target, self.held()?.binding.user)?;
        // Retain the true target before releasing the original task.
        self.native.as_mut().unwrap().target = Some(target);
        if self.original_native_entry()? != entry {
            return Err(NamespaceError::Rejected("original setns entry changed"));
        }
        self.detach_native_entry(entry)
    }

    fn observe_native_exit_inner(&mut self) -> Result<bool> {
        if self.phase != Phase::NativeRunning
            || !self.native.as_ref().is_some_and(|call| {
                call.detached && call.armed && call.release_attempted && call.released
            })
        {
            return Err(NamespaceError::Rejected("original native exit phase"));
        }
        let Some(status) = self.stop()? else {
            return Ok(false);
        };
        if status != SYSCALL_STOP {
            return Err(NamespaceError::Rejected(
                "native call did not reach its syscall-exit stop",
            ));
        }
        let result = native_exit(
            self.held()?.binding.identity.pid,
            self.native.as_ref().unwrap().entry.instruction_pointer,
        )?;
        let errno = result.namespace_errno()?;
        let after = from_pidfd(&self.held()?.pidfd, 0xff03, libc::CLONE_NEWNS)?;
        require_namespace_owner(&after, self.held()?.binding.user)?;
        let after_node = Node::of(&after)?;
        let call = self.native.as_ref().unwrap();
        if (errno != 0 && after_node != call.before)
            || (errno == 0 && call.kind == NativeKind::Unshare && after_node == call.before)
            || (errno == 0
                && call.kind == NativeKind::RestoreBootstrap
                && after_node != Node::of(&self.held()?.bootstrap)?)
        {
            return Err(NamespaceError::Rejected(
                "native errno and actual namespace effect disagree",
            ));
        }
        let root_after = namespace_root(&self.held()?.proc)?;
        if Node::of(&root_after)? != Node::of(&self.held()?.bootstrap_root)? {
            return Err(NamespaceError::Rejected(
                "native namespace switch changed the original root inode",
            ));
        }
        let call = self.native.as_mut().unwrap();
        call.result = Some(result);
        call.after = Some(after);
        call.root_after = Some(root_after);
        self.phase = Phase::NativeExit;
        self.check_traced()?;
        if native_exit(
            self.held()?.binding.identity.pid,
            self.native.as_ref().unwrap().entry.instruction_pointer,
        )? != result
        {
            return Err(NamespaceError::Rejected(
                "original native result changed while stopped",
            ));
        }
        Ok(true)
    }

    pub(super) fn observed_exit(&self) -> Result<NativeExitObservation<'_>> {
        self.check_traced()?;
        if self.phase != Phase::NativeExit {
            return Err(NamespaceError::Rejected("no actual stopped native exit"));
        }
        Ok(NativeExitObservation {
            call: self.native.as_ref().unwrap(),
            resources: self.held()?,
        })
    }

    /// Only after the coordinator has validated the actual copied mount graph.
    /// The task remains stopped until this explicit, same-owner operation.
    fn resume_after_unshare_inner(&mut self) -> Result<()> {
        let view = self.observed_exit()?;
        if !view.is_unshare() || view.errno()? != 0 || self.completed_unshare {
            return Err(NamespaceError::Rejected(
                "original unshare cannot be accepted",
            ));
        }
        let default = view.after_namespace().try_clone()?;
        let default_root = view.actual_root().try_clone()?;
        let resources = self.resources.as_mut().unwrap();
        resources
            .epoch
            .as_mut()
            .ok_or(NamespaceError::Rejected("native epoch absent"))?
            .admit_clone(&resources.proc, &default_root)?;
        self.resources.as_mut().unwrap().default = Some(default);
        self.resources.as_mut().unwrap().default_root = Some(default_root);
        self.completed_unshare = true;
        self.check_traced()?;
        control(self.held()?.binding.identity.pid, libc::PTRACE_SYSCALL, 0)?;
        self.native.take();
        self.phase = Phase::Running;
        self.before()
    }

    /// Detach while the real successful restoration is still syscall-stopped.
    /// No child inherits a permanent TRACE-only or ptrace-owner requirement.
    fn detach_after_restore_inner(&mut self) -> Result<()> {
        let view = self.observed_exit()?;
        if view.is_unshare()
            || view.errno()? != 0
            || !self.completed_unshare
            || self.completed_restore
        {
            return Err(NamespaceError::Rejected(
                "original bootstrap restoration cannot be accepted",
            ));
        }
        let actual_root = view.actual_root().try_clone()?;
        let resources = self.resources.as_mut().unwrap();
        resources
            .epoch
            .as_mut()
            .ok_or(NamespaceError::Rejected("native epoch absent"))?
            .admit_restoration(&resources.proc, &actual_root)?;
        self.check()?;
        self.check_traced()?;
        control(self.held()?.binding.identity.pid, libc::PTRACE_DETACH, 0)?;
        self.completed_restore = true;
        self.native.take();
        self.phase = Phase::Detached;
        self.check()?;
        tracer(&self.held()?.proc, self.held()?.binding.identity, 0)?;
        self.check()?;
        self.before()
    }

    pub(super) fn observed_default_namespace(&self) -> Result<&File> {
        if self.phase != Phase::Detached || !self.completed_unshare || !self.completed_restore {
            return Err(NamespaceError::Rejected(
                "original namespace round trip incomplete",
            ));
        }
        self.check()?;
        tracer(&self.held()?.proc, self.held()?.binding.identity, 0)?;
        self.held()?
            .epoch
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?
            .verify_completed()?;
        self.held()?
            .default
            .as_ref()
            .ok_or(NamespaceError::Rejected("original default custody absent"))
    }

    pub(super) fn issue_successors(&mut self, child: &TreeChild) -> Result<NativeSuccessors> {
        self.step(|this| {
            if this.successors_issued {
                return Err(NamespaceError::Rejected(
                    "native successor owner already issued",
                ));
            }
            let owner = NativeSuccessors::issue(this, child)?;
            this.successors_issued = true;
            Ok(owner)
        })
    }

    pub(super) fn retire_after_tree(&mut self, retired: &RetiredTreeWitness<'_>) -> Result<()> {
        let r = self.held()?;
        let child = retired
            .tree
            .init
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?;
        let exit = retired
            .tree
            .reaped_init
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?;
        r.context
            .objects()
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        if unsafe { libc::syscall(libc::SYS_gettid) } != r.binding.creator_tid as libc::c_long
            || child.identity != r.binding.identity
            || fd_node(child.pidfd.as_raw_fd())? != r.binding.pidfd
            || fd_node(r.pidfd.as_raw_fd())? != r.binding.pidfd
            || exit.pid != r.binding.identity.pid
            || !pidfd_exited(&r.pidfd)?
        {
            return Err(NamespaceError::RetirementUnproven);
        }
        self.native.take();
        self.resources.take();
        self.phase = Phase::Retired;
        Ok(())
    }
}

impl Drop for OriginalPtrace {
    fn drop(&mut self) {
        if !matches!(self.phase, Phase::Prepared | Phase::Retired) {
            if let Some(call) = self.native.take() {
                std::mem::forget(call);
            }
            if let Some(resources) = self.resources.take() {
                std::mem::forget(resources);
            }
        }
    }
}

#[cfg(test)]
#[path = "production_namespace_native_controls.rs"]
mod controls;
