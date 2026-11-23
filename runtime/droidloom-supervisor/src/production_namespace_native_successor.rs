//! Finite late observation of one inherited native mount-namespace syscall.
//!
//! A numeric notification PID is only a candidate lookup. The fixed kernel ARM
//! ioctl is the first operation that can attach: it binds the original listener,
//! successfully delivered request ID and PIDFD_THREAD to the same kernel task.
//! No PTRACE_ATTACH/SEIZE, register write, synthetic return value or RET_TRACE
//! fallback exists here. The task is detached while stopped at its real exit.
use super::*;
#[path = "production_namespace_apexd_execution_identity.rs"]
mod apexd_identity;
pub(crate) use apexd_identity::{ActualApexdGeneration, ActualApexdTask};

const ARM_NATIVE_EXIT: libc::c_ulong = wire::ARM_NATIVE_EXIT;
const REQUEST_BUDGET: Duration = Duration::from_secs(10);
const PIDFS_MAGIC: libc::c_long = 0x5049_4446;
use wire::ArmNativeExit as Arm;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Kind {
    Unshare,
    SetNamespace,
}

fn fixed_kind(n: &wire::Notification) -> Result<Kind> {
    if n.pid <= 1
        || n.flags != 0
        || n.data.arch != ARCH_X86_64
        || n.data.nr < 0
        || n.data.nr as u32 & 0x4000_0000 != 0
        || n.data.instruction_pointer == 0
    {
        return Err(NamespaceError::Rejected(
            "inherited native notification ABI",
        ));
    }
    match n.operation() {
        Some(wire::Operation::Unshare) if n.data.args[0] == libc::CLONE_NEWNS as u64 => {
            Ok(Kind::Unshare)
        }
        Some(wire::Operation::SetNamespace)
            if (1..=i32::MAX as u64).contains(&n.data.args[0])
                && n.data.args[1] == libc::CLONE_NEWNS as u64 =>
        {
            Ok(Kind::SetNamespace)
        }
        _ => Err(NamespaceError::Rejected(
            "inherited native call is outside fixed NEWNS ABI",
        )),
    }
}

fn range(raw: &[u8], expected_start: u32) -> Result<(u32, u32)> {
    let text = std::str::from_utf8(raw)
        .map_err(|_| NamespaceError::Rejected("native owner map encoding"))?;
    if text.lines().count() != 1 || !text.ends_with('\n') {
        return Err(NamespaceError::Rejected(
            "native owner must have one subordinate map",
        ));
    }
    let fields: Vec<_> = text.split_ascii_whitespace().collect();
    if fields.len() != 3 {
        return Err(NamespaceError::Rejected("native owner map fields"));
    }
    let values = fields
        .iter()
        .map(|x| {
            x.parse::<u32>()
                .map_err(|_| NamespaceError::Rejected("native owner map number"))
        })
        .collect::<Result<Vec<_>>>()?;
    if values[0] != 0 || values[1] != expected_start || values[2] == 0 {
        return Err(NamespaceError::Rejected(
            "native owner subordinate map differs",
        ));
    }
    let end = values[1]
        .checked_add(values[2])
        .ok_or(NamespaceError::Rejected("native owner map overflow"))?;
    Ok((values[1], end))
}

fn inside(value: u32, bounds: (u32, u32)) -> bool {
    (bounds.0..bounds.1).contains(&value)
}

fn payload_prefix(raw: &[u8]) -> Result<Vec<u8>> {
    if !raw.starts_with(b"0::/")
        || !raw.ends_with(b"/payload/init\n")
        || raw.iter().filter(|&&x| x == b'\n').count() != 1
        || raw.contains(&0)
    {
        return Err(NamespaceError::Rejected("original native payload cgroup"));
    }
    let prefix = raw[..raw.len() - b"init\n".len()].to_vec();
    if prefix.len() > 4096 {
        return Err(NamespaceError::Rejected(
            "original native payload cgroup bound",
        ));
    }
    Ok(prefix)
}

fn payload_member(raw: &[u8], prefix: &[u8]) -> Result<()> {
    if raw.len() > 8192
        || !raw.starts_with(prefix)
        || !raw.ends_with(b"\n")
        || raw.iter().filter(|&&x| x == b'\n').count() != 1
        || raw.contains(&0)
    {
        return Err(NamespaceError::Rejected(
            "native caller is outside original payload cgroup",
        ));
    }
    let suffix = &raw[prefix.len()..raw.len() - 1];
    if suffix.is_empty()
        || suffix.split(|&x| x == b'/').any(|x| {
            x.is_empty() || x == b"." || x == b".." || x.iter().any(|&c| c < b' ' || c == 0x7f)
        })
    {
        return Err(NamespaceError::Rejected(
            "native caller cgroup is not canonical",
        ));
    }
    Ok(())
}

fn sole(proc: &File, identity: ProcessIdentity, expected_tracer: libc::pid_t) -> Result<()> {
    tracer(proc, identity, expected_tracer)?;
    let raw = read_proc(proc, "status")?;
    if canonical_status_value(&raw, "Threads:")? != "1" {
        return Err(NamespaceError::Rejected(
            "native syscall requires one original task thread",
        ));
    }
    Ok(())
}

fn native_thread_status(
    proc: &File,
    identity: ProcessIdentity,
    tgid: u32,
    expected_tracer: libc::pid_t,
) -> Result<()> {
    let raw = read_proc(proc, "status")?;
    for (key, value) in [
        ("Pid:", identity.pid),
        ("Tgid:", tgid),
        ("TracerPid:", expected_tracer as u32),
    ] {
        if value == 0 && key != "TracerPid:" {
            return Err(NamespaceError::Rejected("native thread identity is zero"));
        }
        if canonical_status_value(&raw, key)? != value.to_string() {
            return Err(NamespaceError::Rejected(
                "native thread/group/tracer identity changed",
            ));
        }
    }
    let threads = canonical_status_value(&raw, "Threads:")?
        .parse::<u32>()
        .map_err(|_| NamespaceError::Rejected("native thread count encoding"))?;
    if threads == 0 {
        return Err(NamespaceError::Rejected(
            "native thread group is no longer live",
        ));
    }
    Ok(())
}

struct Scope {
    context: RuntimeMacOwner,
    defaults: std::rc::Rc<DefaultMountOwner>,
    binding: Binding,
    proc_root: File,
    proc_root_node: Node,
    proc: File,
    pidfd: OwnedFd,
    parent_pid: u32,
    user: File,
    namespaces: Vec<(libc::c_int, libc::c_ulong, File, Node)>,
    uid_map: Vec<u8>,
    gid_map: Vec<u8>,
    uids: (u32, u32),
    gids: (u32, u32),
    payload: Vec<u8>,
    bootstrap: File,
    bootstrap_root: File,
    default: File,
    default_root: File,
    listener: Node,
    coordinator_proc: File,
    coordinator_identity: ProcessIdentity,
    coordinator_node: Node,
}

impl Scope {
    fn check_custody(&self) -> Result<()> {
        if unsafe { libc::syscall(libc::SYS_gettid) } != self.binding.creator_tid as libc::c_long
            || fd_node(self.pidfd.as_raw_fd())? != self.binding.pidfd
            || Node::of(&self.proc)? != self.binding.proc
            || Node::of(&self.user)? != self.binding.user
            || Node::of(&self.proc_root)? != self.proc_root_node
            || Node::of(&self.coordinator_proc)? != self.coordinator_node
            || read_identity(&self.coordinator_proc, self.coordinator_identity.pid)?
                != self.coordinator_identity
        {
            return Err(NamespaceError::Rejected(
                "inherited native original owner changed",
            ));
        }
        Ok(())
    }

    fn check(&self) -> Result<()> {
        self.check_for_original(None)
    }

    fn check_for_original(&self, change: Option<&OriginalInitChange>) -> Result<()> {
        self.check_custody()?;
        self.context
            .objects()
            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        // The receiver is already reaped before ARM. This synchronous owner
        // creates no other thread or worker while a native syscall is armed.
        sole(&self.coordinator_proc, self.coordinator_identity, 0)?;
        if pidfd_exited(&self.pidfd)?
            || read_identity(&self.proc, self.binding.identity.pid)? != self.binding.identity
        {
            return Err(NamespaceError::Rejected(
                "inherited native original init exited",
            ));
        }
        let info = pidfd_info(self.pidfd.as_raw_fd())?;
        if info.pid != self.binding.identity.pid
            || info.tgid != info.pid
            || info.ppid != self.parent_pid
        {
            return Err(NamespaceError::Rejected(
                "inherited native original init PIDFD changed",
            ));
        }
        require_pidfd_creds(&info, self.uids.0, self.gids.0)?;
        let user = from_pidfd(&self.pidfd, 0xff09, libc::CLONE_NEWUSER)?;
        if Node::of(&user)? != self.binding.user
            || read_proc(&self.proc, "uid_map")? != self.uid_map
            || read_proc(&self.proc, "gid_map")? != self.gid_map
            || payload_prefix(&read_proc(&self.proc, "cgroup")?)? != self.payload
        {
            return Err(NamespaceError::Rejected(
                "inherited native original namespace or lease changed",
            ));
        }
        for (kind, command, held, node) in &self.namespaces {
            if Node::of(held)? != *node {
                return Err(NamespaceError::Rejected(
                    "inherited native held namespace changed",
                ));
            }
            let actual = from_pidfd(&self.pidfd, *command, *kind)?;
            require_namespace_owner(&actual, self.binding.user)?;
            if *kind == libc::CLONE_NEWNS {
                // Only the same owned original attempt may inspect its pending
                // transition. Ordinary witnesses require a completed epoch.
                self.defaults.verify_original_mount(&self.pidfd, change)?;
            } else if Node::of(&actual)? != *node {
                return Err(NamespaceError::Rejected(
                    "original init changed an unrelated namespace",
                ));
            }
        }
        for target in [&self.bootstrap, &self.default] {
            if filesystem_kind(target)? != NSFS_MAGIC
                || unsafe { libc::ioctl(target.as_raw_fd(), NS_GET_NSTYPE) } != libc::CLONE_NEWNS
            {
                return Err(NamespaceError::Rejected(
                    "inherited native fixed namespace type",
                ));
            }
            require_namespace_owner(target, self.binding.user)?;
        }
        Ok(())
    }

    fn listener(&self, file: &File) -> Result<()> {
        self.check_custody()?;
        if Node::of(file)? != self.listener {
            return Err(NamespaceError::Rejected(
                "inherited native listener was substituted",
            ));
        }
        Ok(())
    }

    fn pending(&self, file: &File, n: &wire::Notification) -> Result<()> {
        self.listener(file)?;
        if unsafe { libc::ioctl(file.as_raw_fd(), wire::ID_VALID, &n.id) } != 0 {
            return Err(io::Error::last_os_error().into());
        }
        Ok(())
    }

    fn target_root(&self, namespace: Node) -> Result<&File> {
        if namespace == Node::of(&self.bootstrap)? {
            Ok(&self.bootstrap_root)
        } else if namespace == Node::of(&self.default)? {
            Ok(&self.default_root)
        } else {
            Err(NamespaceError::Rejected(
                "setns target is not original bootstrap or default",
            ))
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum AttemptPhase {
    Prepared,
    ArmEntered,
    Armed,
    SendEntered,
    Running,
    ExitStopped,
    Detached,
    TraceExitReleased,
    OriginalInitRetiring,
}

struct Attempt {
    notification: wire::Notification,
    kind: Kind,
    deadline: Instant,
    identity: ProcessIdentity,
    tgid: u32,
    pidfd: OwnedFd,
    pidfd_node: Node,
    proc: File,
    proc_node: Node,
    credentials: [u32; 8],
    cgroup: Vec<u8>,
    before_namespace: File,
    before_node: Node,
    before_root: File,
    graph: mount_epoch::SuccessorGraph,
    target: Option<File>,
    target_node: Option<Node>,
    phase: AttemptPhase,
    armed: bool,
    continued: bool,
    exit: Option<Exit>,
    after_namespace: Option<File>,
    after_root: Option<File>,
    after_graph: Option<mount_epoch::SuccessorGraph>,
    original_change: Option<OriginalInitChange>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) enum RetirementWait {
    OriginalTree,
    DescendantTraceReport,
}

pub(super) fn retirement_wait_route(
    task: ProcessIdentity,
    tgid: u32,
    original: ProcessIdentity,
    original_change: bool,
) -> Result<RetirementWait> {
    if original_change {
        if task != original || tgid != task.pid {
            return Err(NamespaceError::RetirementUnproven);
        }
        Ok(RetirementWait::OriginalTree)
    } else if task.pid == original.pid {
        Err(NamespaceError::RetirementUnproven)
    } else {
        Ok(RetirementWait::DescendantTraceReport)
    }
}

fn credentials(info: &PidfdInfo) -> [u32; 8] {
    [
        info.ruid, info.euid, info.suid, info.fsuid, info.rgid, info.egid, info.sgid, info.fsgid,
    ]
}

impl Attempt {
    fn before(&self) -> Result<()> {
        if Instant::now() >= self.deadline {
            return Err(NamespaceError::Rejected(
                "inherited native original request deadline",
            ));
        }
        Ok(())
    }

    fn check(&self, scope: &Scope, traced: bool, current_namespace: Option<Node>) -> Result<()> {
        self.before()?;
        scope.check_for_original(self.original_change.as_ref())?;
        if let Some(change) = self.original_change.as_ref() {
            change.verify(&scope.defaults)?;
            if self.identity != scope.binding.identity || self.tgid != self.identity.pid {
                return Err(NamespaceError::Rejected(
                    "original native epoch task was substituted",
                ));
            }
        }
        if fd_node(self.pidfd.as_raw_fd())? != self.pidfd_node
            || Node::of(&self.before_namespace)? != self.before_node
            || self.target.as_ref().map(Node::of).transpose()? != self.target_node
            || Node::of(&self.proc)? != self.proc_node
            || pidfd_exited(&self.pidfd)?
            || read_identity(&self.proc, self.identity.pid)? != self.identity
        {
            return Err(NamespaceError::Rejected(
                "inherited native task generation changed",
            ));
        }
        let info = pidfd_info(self.pidfd.as_raw_fd())?;
        if info.pid != self.identity.pid
            || info.tgid != self.tgid
            || info.ppid != self.identity.parent
            || credentials(&info) != self.credentials
            || read_proc(&self.proc, "cgroup")? != self.cgroup
            || read_proc(&self.proc, "uid_map")? != scope.uid_map
            || read_proc(&self.proc, "gid_map")? != scope.gid_map
        {
            return Err(NamespaceError::Rejected(
                "inherited native task identity or cgroup changed",
            ));
        }
        payload_member(&self.cgroup, &scope.payload)?;
        let user = from_pidfd(&self.pidfd, 0xff09, libc::CLONE_NEWUSER)?;
        if Node::of(&user)? != scope.binding.user {
            return Err(NamespaceError::Rejected(
                "inherited native caller changed user namespace",
            ));
        }
        for (kind, command, _, node) in &scope.namespaces {
            let actual = from_pidfd(&self.pidfd, *command, *kind)?;
            require_namespace_owner(&actual, scope.binding.user)?;
            if *kind == libc::CLONE_NEWNS {
                if current_namespace.is_some_and(|n| Node::of(&actual).ok() != Some(n)) {
                    return Err(NamespaceError::Rejected(
                        "inherited native syscall namespace phase",
                    ));
                }
            } else if Node::of(&actual)? != *node {
                return Err(NamespaceError::Rejected(
                    "inherited native unrelated namespace differs",
                ));
            }
        }
        native_thread_status(
            &self.proc,
            self.identity,
            self.tgid,
            if traced { scope.binding.creator_tid } else { 0 },
        )?;
        self.before()
    }
}

/// An actual historical syscall result. It does not issue a live task,
// activation, mount policy, Ready or production witness.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct NativeSyscallOutcome {
    task: ProcessIdentity,
    operation: wire::Operation,
    errno: i32,
    before: Node,
    after: Node,
    ordinal: u64,
}
impl NativeSyscallOutcome {
    pub(crate) fn errno(&self) -> i32 {
        self.errno
    }
    pub(crate) fn operation(&self) -> wire::Operation {
        self.operation
    }
}

pub(in super::super) struct NativeSuccessors {
    scope: Option<std::rc::Rc<Scope>>,
    attempt: Option<Attempt>,
    ordinal: u64,
    failed: bool,
    retired: bool,
}

impl NativeSuccessors {
    // Only the parent OriginalPtrace can issue this from its completed actual
    // two-call observation and the same opaque original TreeChild.
    pub(super) fn issue(original: &OriginalPtrace, child: &TreeChild) -> Result<Self> {
        original.matches_original(child)?;
        original.observed_default_namespace()?;
        let r = original.held()?;
        let proc_root = child.proc_root.try_clone()?;
        check_fs(proc_root.as_raw_fd(), PROC_MAGIC)?;
        let self_pid = unsafe { libc::getpid() as u32 };
        if self_pid != r.binding.creator_tid as u32 {
            return Err(NamespaceError::Rejected(
                "native coordinator must be its sole group leader",
            ));
        }
        let coordinator_proc = open_proc_at(
            &proc_root,
            &self_pid.to_string(),
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        let coordinator_identity = read_identity(&coordinator_proc, self_pid)?;
        sole(&coordinator_proc, coordinator_identity, 0)?;
        let defaults = DefaultMountOwner::issue(r, child)?;
        let scope = Scope {
            context: r.context.clone(),
            defaults,
            binding: r.binding,
            proc_root_node: Node::of(&proc_root)?,
            proc_root,
            proc: r.proc.try_clone()?,
            pidfd: r.pidfd.try_clone()?,
            parent_pid: r.parent_pid,
            user: r.user.try_clone()?,
            namespaces: r
                .namespaces
                .iter()
                .map(|(kind, command, file, node)| Ok((*kind, *command, file.try_clone()?, *node)))
                .collect::<Result<_>>()?,
            uid_map: r.uid_map.clone(),
            gid_map: r.gid_map.clone(),
            uids: range(&r.uid_map, r.uid_start)?,
            gids: range(&r.gid_map, r.gid_start)?,
            payload: payload_prefix(&read_proc(&r.proc, "cgroup")?)?,
            bootstrap: r.bootstrap.try_clone()?,
            bootstrap_root: r.bootstrap_root.try_clone()?,
            default: r
                .default
                .as_ref()
                .ok_or(NamespaceError::RetirementUnproven)?
                .try_clone()?,
            default_root: r
                .default_root
                .as_ref()
                .ok_or(NamespaceError::RetirementUnproven)?
                .try_clone()?,
            listener: r.listener.ok_or(NamespaceError::RetirementUnproven)?,
            coordinator_node: Node::of(&coordinator_proc)?,
            coordinator_proc,
            coordinator_identity,
        };
        scope.check()?;
        Ok(Self {
            scope: Some(std::rc::Rc::new(scope)),
            attempt: None,
            ordinal: 0,
            failed: false,
            retired: false,
        })
    }

    fn scope(&self) -> Result<&Scope> {
        self.scope
            .as_deref()
            .ok_or(NamespaceError::RetirementUnproven)
    }

    pub(in super::super) fn matches_listener(
        &self,
        identity: ProcessIdentity,
        nonce: [u8; 16],
        pidfd: Node,
        proc: Node,
        listener: Node,
    ) -> Result<()> {
        let s = self.scope()?;
        s.check()?;
        if s.binding.identity != identity
            || s.binding.nonce != nonce
            || s.binding.pidfd != pidfd
            || s.binding.proc != proc
            || s.listener != listener
            || self.failed
            || self.retired
        {
            return Err(NamespaceError::Rejected(
                "inherited native owner or listener changed",
            ));
        }
        Ok(())
    }

    pub(in super::super) fn idle(&self) -> Result<()> {
        if self.failed || self.retired || self.attempt.is_some() {
            return Err(NamespaceError::Rejected(
                "inherited native attempt remains owned",
            ));
        }
        self.scope()?.check()
    }

    pub(in super::super) fn begin_original_bootstrap_bind(
        &self,
        child: &TreeChild,
        listener: Node,
        notification: wire::Notification,
    ) -> Result<OriginalBootstrapBindChange> {
        self.idle()?;
        let s = self.scope()?;
        if self.ordinal != 0
            || binding(child)? != s.binding
            || s.listener != listener
            || notification.pid != s.binding.identity.pid
        {
            return Err(NamespaceError::Rejected(
                "bootstrap bind lost its original listener or phase",
            ));
        }
        s.defaults.begin_bootstrap_bind(child, notification)
    }

    pub(in super::super) fn original_bootstrap_bind_barrier(
        &self,
        child: &TreeChild,
        listener: Node,
        notification: &wire::Notification,
        change: &OriginalBootstrapBindChange,
    ) -> Result<()> {
        self.idle()?;
        let s = self.scope()?;
        if self.ordinal != 0
            || binding(child)? != s.binding
            || s.listener != listener
            || notification.pid != s.binding.identity.pid
            || notification.operation() != Some(wire::Operation::Mount)
        {
            return Err(NamespaceError::Rejected(
                "bootstrap bind has another native actor",
            ));
        }
        change.require_owner(&s.defaults)?;
        change.revalidate(child)
    }

    /// Read-only issuer used only by the same inherited pending request owner.
    /// The original broker actor ledger remains borrowed through the request.
    pub(in super::super) fn issue_apexd_task(
        &self,
        listener: &File,
        notification: wire::Notification,
        deadline: Instant,
        mount_owner: &OwnedNamespaceWitness<'_>,
        actors: &crate::production_runtime_assets::NativeMountActorGuard<'_>,
    ) -> Result<ActualApexdTask> {
        self.idle()?;
        actors
            .require_exclusive()
            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        mount_owner.revalidate()?;
        let scope = self
            .scope
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?;
        if Node::of(mount_owner.user_namespace())? != scope.binding.user
            || mount_owner
                .descendant_pidfd()
                .map(|fd| fd_node(fd.as_raw_fd()))
                .transpose()?
                != Some(scope.binding.pidfd)
        {
            return Err(NamespaceError::Rejected(
                "apexd actor ledger belongs to another original tree",
            ));
        }
        actors
            .revalidate(mount_owner)
            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        let value =
            ActualApexdTask::capture(std::rc::Rc::clone(scope), listener, notification, deadline)?;
        actors
            .revalidate(mount_owner)
            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        value.revalidate_kernel()?;
        Ok(value)
    }

    pub(in super::super) fn prepare(
        &mut self,
        listener: &File,
        notification: wire::Notification,
        deadline: Instant,
    ) -> Result<()> {
        self.idle()?;
        // All failures retain a failed lane. An unarmed candidate is never
        // killed independently; only the original tree can be retired.
        self.failed = true;
        self.scope()?.defaults.bootstrap_complete()?;
        let kind = fixed_kind(&notification)?;
        let now = Instant::now();
        if now >= deadline
            || deadline.duration_since(now) > REQUEST_BUDGET
            || self.ordinal == u64::MAX
        {
            return Err(NamespaceError::Rejected(
                "inherited native finite request budget",
            ));
        }
        let s = self.scope()?;
        s.pending(listener, &notification)?;
        let is_original = notification.pid == s.binding.identity.pid;
        if is_original && kind != Kind::SetNamespace {
            return Err(NamespaceError::Rejected(
                "later original init requires its fixed setns epoch",
            ));
        }
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, notification.pid, PIDFD_THREAD) };
        if raw < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let pidfd = unsafe { OwnedFd::from_raw_fd(raw as i32) };
        if filesystem_kind_fd(pidfd.as_raw_fd())? != PIDFS_MAGIC {
            return Err(NamespaceError::Rejected(
                "native candidate is not a kernel PIDFD",
            ));
        }
        let info = pidfd_info(pidfd.as_raw_fd())?;
        if info.pid != notification.pid
            || info.tgid == 0
            || ![info.ruid, info.euid, info.suid, info.fsuid]
                .into_iter()
                .all(|x| inside(x, s.uids))
            || ![info.rgid, info.egid, info.sgid, info.fsgid]
                .into_iter()
                .all(|x| inside(x, s.gids))
        {
            return Err(NamespaceError::Rejected(
                "native candidate is not an original mapped process",
            ));
        }
        let proc = open_proc_at(
            &s.proc_root,
            &info.pid.to_string(),
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        let identity = read_identity(&proc, info.pid)?;
        if identity.parent != info.ppid {
            return Err(NamespaceError::Rejected("native candidate parent changed"));
        }
        let cgroup = read_proc(&proc, "cgroup")?;
        payload_member(&cgroup, &s.payload)?;
        let before_namespace = from_pidfd(&pidfd, 0xff03, libc::CLONE_NEWNS)?;
        require_namespace_owner(&before_namespace, s.binding.user)?;
        let before_node = Node::of(&before_namespace)?;
        let before_root = namespace_root(&proc)?;
        if Node::of(&before_root)? != Node::of(&s.bootstrap_root)? {
            return Err(NamespaceError::Rejected(
                "native candidate root is not original Android root",
            ));
        }
        let graph = mount_epoch::SuccessorGraph::observe(&proc, &before_root)?;
        let target = if kind == Kind::SetNamespace {
            let raw = unsafe {
                libc::syscall(
                    libc::SYS_pidfd_getfd,
                    pidfd.as_raw_fd(),
                    notification.data.args[0] as i32,
                    0,
                )
            };
            if raw < 0 {
                return Err(io::Error::last_os_error().into());
            }
            let target = unsafe { File::from_raw_fd(raw as i32) };
            if filesystem_kind(&target)? != NSFS_MAGIC
                || unsafe { libc::ioctl(target.as_raw_fd(), NS_GET_NSTYPE) } != libc::CLONE_NEWNS
            {
                return Err(NamespaceError::Rejected(
                    "native setns register does not name a mount namespace",
                ));
            }
            require_namespace_owner(&target, s.binding.user)?;
            s.target_root(Node::of(&target)?)?;
            Some(target)
        } else {
            None
        };
        let original_change = if is_original {
            if identity != s.binding.identity
                || info.tgid != identity.pid
                || Node::of(&proc)? != s.binding.proc
            {
                return Err(NamespaceError::Rejected(
                    "later original init generation differs",
                ));
            }
            Some(s.defaults.begin_original(
                notification,
                before_node,
                target.as_ref().ok_or(NamespaceError::RetirementUnproven)?,
                &graph,
            )?)
        } else {
            None
        };
        let attempt = Attempt {
            notification,
            kind,
            deadline,
            identity,
            tgid: info.tgid,
            pidfd_node: fd_node(pidfd.as_raw_fd())?,
            pidfd,
            proc_node: Node::of(&proc)?,
            proc,
            credentials: credentials(&info),
            cgroup,
            before_namespace,
            before_node,
            before_root,
            graph,
            target_node: target.as_ref().map(Node::of).transpose()?,
            target,
            phase: AttemptPhase::Prepared,
            armed: false,
            continued: false,
            exit: None,
            after_namespace: None,
            after_root: None,
            after_graph: None,
            original_change,
        };
        attempt.check(s, false, Some(before_node))?;
        s.pending(listener, &notification)?;
        // Store all candidate resources before the first mutation/attach.
        self.attempt = Some(attempt);
        self.failed = false;
        Ok(())
    }

    pub(in super::super) fn arm(&mut self, listener: &File) -> Result<()> {
        if self.failed || self.retired {
            return Err(NamespaceError::Rejected("native ARM lane already failed"));
        }
        self.failed = true;
        let s = self
            .scope
            .as_deref()
            .ok_or(NamespaceError::RetirementUnproven)?;
        let a = self
            .attempt
            .as_mut()
            .ok_or(NamespaceError::RetirementUnproven)?;
        if a.phase != AttemptPhase::Prepared || a.armed || a.continued {
            return Err(NamespaceError::Rejected("native ARM replay"));
        }
        a.check(s, false, Some(a.before_node))?;
        s.pending(listener, &a.notification)?;
        a.graph.matches(&a.proc, &a.before_root)?;
        let request = Arm {
            id: a.notification.id,
            pidfd: a.pidfd.as_raw_fd(),
            mntns_fd: a.target.as_ref().map_or(-1, AsRawFd::as_raw_fd),
            flags: 0,
            reserved: 0,
        };
        a.phase = AttemptPhase::ArmEntered;
        let code = unsafe { libc::ioctl(listener.as_raw_fd(), ARM_NATIVE_EXIT, &request) };
        let error = io::Error::last_os_error();
        // The fixed kernel contract has no fallible copyout after commit.
        // Record that successful commit before any other observation can fail.
        if code == 0 {
            a.armed = true;
            a.phase = AttemptPhase::Armed;
        } else {
            return Err(error.into());
        }
        a.check(s, true, Some(a.before_node))?;
        s.pending(listener, &a.notification)?;
        self.failed = false;
        Ok(())
    }

    pub(in super::super) fn before_continue(
        &mut self,
        listener: &File,
        notification: &wire::Notification,
    ) -> Result<()> {
        if self.failed || self.retired {
            return Err(NamespaceError::Rejected("native continuation lane failed"));
        }
        self.failed = true;
        let s = self
            .scope
            .as_deref()
            .ok_or(NamespaceError::RetirementUnproven)?;
        let a = self
            .attempt
            .as_mut()
            .ok_or(NamespaceError::RetirementUnproven)?;
        if !a.armed
            || a.phase != AttemptPhase::Armed
            || a.continued
            || &a.notification != notification
        {
            return Err(NamespaceError::Rejected(
                "native continuation request or phase changed",
            ));
        }
        a.check(s, true, Some(a.before_node))?;
        a.graph.matches(&a.proc, &a.before_root)?;
        s.pending(listener, notification)?;
        // The kernel SEND repeats exact task and original tracer+cred checks.
        // Its one-shot setns guard checks the file returned by native fdget;
        // valid shared tables/threads do not become a replacement authority.
        // ADDFD remains rejected for this exact armed request.
        a.phase = AttemptPhase::SendEntered;
        Ok(())
    }

    pub(in super::super) fn continued(
        &mut self,
        listener: &File,
        notification: &wire::Notification,
    ) -> Result<()> {
        let s = self
            .scope
            .as_deref()
            .ok_or(NamespaceError::RetirementUnproven)?;
        let a = self
            .attempt
            .as_mut()
            .ok_or(NamespaceError::RetirementUnproven)?;
        if !self.failed
            || a.phase != AttemptPhase::SendEntered
            || !a.armed
            || a.continued
            || &a.notification != notification
        {
            return Err(NamespaceError::Rejected(
                "native actual SEND receipt differs",
            ));
        }
        // This method is reachable only after the same listener's actual
        // CONTINUE ioctl returned zero. It still grants zero syscall credit.
        a.continued = true;
        a.phase = AttemptPhase::Running;
        s.listener(listener)?;
        a.check(s, true, None)?;
        self.failed = false;
        Ok(())
    }

    pub(in super::super) fn failed(&mut self) {
        self.failed = true;
    }

    pub(in super::super) fn complete(&mut self) -> Result<Option<NativeSyscallOutcome>> {
        if self.failed || self.retired {
            return Err(NamespaceError::Rejected("native exit lane failed"));
        }
        self.failed = true;
        let s = self
            .scope
            .as_deref()
            .ok_or(NamespaceError::RetirementUnproven)?;
        let a = self
            .attempt
            .as_mut()
            .ok_or(NamespaceError::RetirementUnproven)?;
        if a.phase != AttemptPhase::Running || !a.armed || !a.continued {
            return Err(NamespaceError::Rejected(
                "native result lacks actual ARM and SEND",
            ));
        }
        a.check(s, true, None)?;
        let mut event: libc::siginfo_t = unsafe { std::mem::zeroed() };
        if unsafe {
            libc::waitid(
                libc::P_PIDFD,
                a.pidfd.as_raw_fd() as u32,
                &mut event,
                libc::WSTOPPED | libc::WNOHANG | libc::__WALL | libc::__WNOTHREAD,
            )
        } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
        let pid = unsafe { event.si_pid() };
        if pid == 0 {
            a.before()?;
            self.failed = false;
            return Ok(None);
        }
        if pid != a.identity.pid as i32
            || event.si_code != libc::CLD_TRAPPED
            || unsafe { event.si_status() } != SYSCALL_STOP
        {
            return Err(NamespaceError::Rejected(
                "native syscall did not stop at its real exit",
            ));
        }
        a.phase = AttemptPhase::ExitStopped;
        let mut raw = [0_u8; 88];
        let count = unsafe {
            libc::syscall(
                libc::SYS_ptrace,
                GET_SYSCALL_INFO,
                a.identity.pid as libc::pid_t,
                raw.len(),
                raw.as_mut_ptr(),
            )
        };
        if count < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let exit = match decode_syscall_info(&raw, count as usize)? {
            SyscallStop::Exit(value)
                if u64::from_ne_bytes(raw[8..16].try_into().unwrap())
                    == a.notification.data.instruction_pointer =>
            {
                value
            }
            _ => {
                return Err(NamespaceError::Rejected(
                    "native EXIT does not match original syscall instruction",
                ));
            }
        };
        let errno = exit.namespace_errno()?;
        a.exit = Some(exit);
        let namespace = from_pidfd(&a.pidfd, 0xff03, libc::CLONE_NEWNS)?;
        require_namespace_owner(&namespace, s.binding.user)?;
        let after_node = Node::of(&namespace)?;
        let root = namespace_root(&a.proc)?;
        let graph = mount_epoch::SuccessorGraph::observe(&a.proc, &root)?;
        if errno != 0 {
            if after_node != a.before_node {
                return Err(NamespaceError::Rejected(
                    "failed native syscall changed mount namespace",
                ));
            }
            a.graph.same_observation(&graph)?;
        } else {
            match a.kind {
                Kind::Unshare => {
                    if after_node == a.before_node {
                        return Err(NamespaceError::Rejected(
                            "successful unshare kept the old namespace",
                        ));
                    }
                    a.graph.exact_clone(&graph)?;
                }
                Kind::SetNamespace => {
                    if Some(after_node) != a.target_node
                        || a.target.as_ref().map(Node::of).transpose()? != a.target_node
                        || Node::of(&root)? != Node::of(s.target_root(after_node)?)?
                    {
                        return Err(NamespaceError::Rejected(
                            "successful setns is not its exact held target",
                        ));
                    }
                    // The target must match this owner's approved complete
                    // epoch. A fresh self-consistent snapshot is not authority.
                    if a.original_change.is_none() {
                        s.defaults.verify_target_graph(after_node, &graph)?;
                    }
                    graph.matches(&a.proc, &root)?;
                }
            }
        }
        if let Some(change) = a.original_change.as_ref() {
            change.observe_exit(&a.notification, errno, after_node, &graph)?;
        }
        a.after_namespace = Some(namespace);
        a.after_root = Some(root);
        a.after_graph = Some(graph);
        a.check(s, true, Some(after_node))?;
        // No successful graph check is followed by a resume/re-stop window.
        // Detach is done at this very exit-stop with unchanged signal/result.
        let mut final_raw = [0_u8; 88];
        let final_count = unsafe {
            libc::syscall(
                libc::SYS_ptrace,
                GET_SYSCALL_INFO,
                a.identity.pid as libc::pid_t,
                final_raw.len(),
                final_raw.as_mut_ptr(),
            )
        };
        if final_count != count || final_raw != raw {
            return Err(NamespaceError::Rejected(
                "native syscall exit changed before detach",
            ));
        }
        a.after_graph
            .as_ref()
            .unwrap()
            .matches(&a.proc, a.after_root.as_ref().unwrap())?;
        a.before()?;
        control(a.identity.pid, libc::PTRACE_DETACH, 0)?;
        // A successful DETACH releases the kernel relationship. A process
        // exiting immediately afterwards is an ordinary descendant exit.
        a.phase = AttemptPhase::Detached;
        if let Some(change) = a.original_change.as_ref() {
            // This call is reachable only after actual stopped DETACH returned
            // success; an error preserves the uncompleted original epoch.
            change.detached(&a.notification)?;
        }
        a.before()?;
        let ordinal = self
            .ordinal
            .checked_add(1)
            .ok_or(NamespaceError::Rejected("native outcome ordinal overflow"))?;
        let outcome = NativeSyscallOutcome {
            task: a.identity,
            operation: match a.kind {
                Kind::Unshare => wire::Operation::Unshare,
                Kind::SetNamespace => wire::Operation::SetNamespace,
            },
            errno,
            before: a.before_node,
            after: after_node,
            ordinal,
        };
        self.ordinal = ordinal;
        self.attempt.take();
        self.failed = false;
        Ok(Some(outcome))
    }

    pub(in super::super) fn retire_before_init_wait(&mut self, child: &TreeChild) -> Result<()> {
        let s = self
            .scope
            .as_deref()
            .ok_or(NamespaceError::RetirementUnproven)?;
        s.check_custody()?;
        if binding(child)? != s.binding {
            return Err(NamespaceError::RetirementUnproven);
        }
        self.failed = true;
        s.defaults.retire_bootstrap_helper()?;
        let Some(a) = self.attempt.as_mut() else {
            return Ok(());
        };
        if !a.armed
            || a.phase == AttemptPhase::Detached
            || a.phase == AttemptPhase::TraceExitReleased
            || a.phase == AttemptPhase::OriginalInitRetiring
        {
            return Ok(());
        }
        // zap_pid_ns_processes can wait for a child held by this tracer.
        // Signal the original PID 1, then release this exact tracee's exit
        // report, BEFORE the tree's existing wait/reap of its original PID 1.
        if !pidfd_exited(&s.pidfd)? {
            signal_owned(&s.pidfd, libc::SIGKILL)?;
        }
        if fd_node(a.pidfd.as_raw_fd())? != a.pidfd_node {
            return Err(NamespaceError::RetirementUnproven);
        }
        if !pidfd_exited(&a.pidfd)? {
            signal_owned(&a.pidfd, libc::SIGKILL)?;
        }
        if retirement_wait_route(
            a.identity,
            a.tgid,
            s.binding.identity,
            a.original_change.is_some(),
        )? == RetirementWait::OriginalTree
        {
            // This tracer is also the real parent of original PID 1.
            // Consuming WEXITED here would steal its only parent report.
            // Fixed ARM has no TRACEEXIT stop; SIGKILL proceeds to the one
            // original TreeChild waitid/reap. This phase alone proves no exit.
            a.phase = AttemptPhase::OriginalInitRetiring;
            return Ok(());
        }
        let end = Instant::now() + RETIRE_TIMEOUT;
        loop {
            if Instant::now() >= end {
                return Err(NamespaceError::RetirementUnproven);
            }
            s.check_custody()?;
            let mut event: libc::siginfo_t = unsafe { std::mem::zeroed() };
            if unsafe {
                libc::waitid(
                    libc::P_PIDFD,
                    a.pidfd.as_raw_fd() as u32,
                    &mut event,
                    libc::WEXITED | libc::WNOHANG | libc::__WALL | libc::__WNOTHREAD,
                )
            } != 0
            {
                return Err(NamespaceError::RetirementUnproven);
            }
            let pid = unsafe { event.si_pid() };
            if pid == 0 {
                std::thread::sleep(Duration::from_millis(1));
                continue;
            }
            if pid != a.identity.pid as i32
                || !matches!(
                    event.si_code,
                    libc::CLD_EXITED | libc::CLD_KILLED | libc::CLD_DUMPED
                )
            {
                return Err(NamespaceError::RetirementUnproven);
            }
            // This releases the tracer's report, not a claim that the real
            // parent has reaped the descendant or that the namespace is gone.
            a.phase = AttemptPhase::TraceExitReleased;
            return Ok(());
        }
    }

    pub(in super::super) fn retire_after_tree(
        &mut self,
        child: &TreeChild,
        actual_exit: &ChildExit,
    ) -> Result<()> {
        let s = self
            .scope
            .as_deref()
            .ok_or(NamespaceError::RetirementUnproven)?;
        s.check_custody()?;
        if binding(child)? != s.binding
            || actual_exit.pid != s.binding.identity.pid
            || !pidfd_exited(&s.pidfd)?
            || self.attempt.as_ref().is_some_and(|a| {
                a.armed
                    && !matches!(
                        a.phase,
                        AttemptPhase::Detached
                            | AttemptPhase::TraceExitReleased
                            | AttemptPhase::OriginalInitRetiring
                    )
            })
        {
            return Err(NamespaceError::RetirementUnproven);
        }
        s.defaults.retire_after_original_reap(child, actual_exit)?;
        self.attempt.take();
        self.scope.take();
        self.retired = true;
        Ok(())
    }
}

fn filesystem_kind_fd(fd: RawFd) -> Result<libc::c_long> {
    let mut value: libc::statfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstatfs(fd, &mut value) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(value.f_type as libc::c_long)
}

impl Drop for NativeSuccessors {
    fn drop(&mut self) {
        if !self.retired {
            if let Some(a) = self.attempt.take() {
                std::mem::forget(a);
            }
            if let Some(s) = self.scope.take() {
                std::mem::forget(s);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn inherited_native_arm_layout_and_fixed_scalar_calls_match_kernel_contract() {
        assert_eq!(std::mem::size_of::<Arm>(), 24);
        assert_eq!(std::mem::align_of::<Arm>(), 8);
        assert_eq!(std::mem::offset_of!(Arm, id), 0);
        assert_eq!(std::mem::offset_of!(Arm, pidfd), 8);
        assert_eq!(std::mem::offset_of!(Arm, mntns_fd), 12);
        assert_eq!(std::mem::offset_of!(Arm, flags), 16);
        assert_eq!(std::mem::offset_of!(Arm, reserved), 20);
        assert_eq!(ARM_NATIVE_EXIT, 0x40182150);
        let mut n = wire::Notification {
            id: 1,
            pid: 2,
            flags: 0,
            data: wire::Data {
                nr: libc::SYS_unshare as i32,
                arch: ARCH_X86_64,
                instruction_pointer: 0x1000,
                args: [libc::CLONE_NEWNS as u64, 0, 0, 0, 0, 0],
            },
        };
        assert_eq!(fixed_kind(&n).unwrap(), Kind::Unshare);
        for bad in [
            0,
            libc::CLONE_NEWUSER as u64,
            (libc::CLONE_NEWNS | libc::CLONE_FS) as u64,
            1_u64 << 32 | libc::CLONE_NEWNS as u64,
        ] {
            let mut altered = n;
            altered.data.args[0] = bad;
            assert!(fixed_kind(&altered).is_err());
        }
        n.data.nr = libc::SYS_setns as i32;
        n.data.args[0] = 3;
        n.data.args[1] = libc::CLONE_NEWNS as u64;
        assert_eq!(fixed_kind(&n).unwrap(), Kind::SetNamespace);
        for bad in [0, i32::MAX as u64 + 1, u64::MAX] {
            let mut altered = n;
            altered.data.args[0] = bad;
            assert!(fixed_kind(&altered).is_err());
        }
        for bad in [
            0,
            libc::CLONE_NEWUSER as u64,
            1_u64 << 32 | libc::CLONE_NEWNS as u64,
        ] {
            let mut altered = n;
            altered.data.args[1] = bad;
            assert!(fixed_kind(&altered).is_err());
        }
        for bad in [
            libc::SYS_clone as i32,
            libc::SYS_unshare as i32 | 0x40000000,
            -1,
        ] {
            let mut altered = n;
            altered.data.nr = bad;
            assert!(fixed_kind(&altered).is_err());
        }
    }

    #[test]
    fn inherited_native_payload_and_mapping_reject_foreign_and_noncanonical_members() {
        let raw = b"0::/system.slice/droidloom-production.service/cell-u1000/payload/init\n";
        let prefix = payload_prefix(raw).unwrap();
        for good in [
            raw.as_slice(),
            b"0::/system.slice/droidloom-production.service/cell-u1000/payload/uid_10000/pid_22\n",
        ] {
            payload_member(good, &prefix).unwrap();
        }
        for bad in [
            b"0::/system.slice/droidloom-production.service/cell-u1001/payload/init\n".as_slice(),
            b"0::/system.slice/droidloom-production.service/cell-u1000/payload/../outside\n",
            b"0::/system.slice/droidloom-production.service/cell-u1000/payload/a//b\n",
            b"0::/system.slice/droidloom-production.service/cell-u1000/payload/\n",
            b"0::/system.slice/droidloom-production.service/cell-u1000/payload/init\n0::/\n",
        ] {
            assert!(payload_member(bad, &prefix).is_err());
        }
        assert_eq!(
            range(b"         0     200000      65536\n", 200000).unwrap(),
            (200000, 265536)
        );
        for bad in [
            b"0 200000 0\n".as_slice(),
            b"0 200001 65536\n",
            b"1 200000 65536\n",
            b"0 200000 65536\n1 300000 1\n",
            b"0 4294967295 2\n",
        ] {
            assert!(range(bad, 200000).is_err());
        }
    }

    #[test]
    fn inherited_native_thread_observation_binds_a_real_nonleader_without_requiring_one_thread() {
        let (identity_tx, identity_rx) = std::sync::mpsc::sync_channel(1);
        let (done_tx, done_rx) = std::sync::mpsc::sync_channel::<()>(0);
        std::thread::scope(|scope| {
            scope.spawn(move || {
                let tid = unsafe { libc::syscall(libc::SYS_gettid) } as u32;
                identity_tx.send(tid).unwrap();
                // The sender's drop also releases this thread on assertion failure.
                let _ = done_rx.recv_timeout(Duration::from_secs(5));
            });
            let tid = identity_rx.recv_timeout(Duration::from_secs(2)).unwrap();
            let tgid = unsafe { libc::getpid() } as u32;
            assert_ne!(tid, tgid);
            let proc = File::open(format!("/proc/{tid}")).unwrap();
            let identity = read_identity(&proc, tid).unwrap();
            assert_ne!(
                canonical_status_value(&read_proc(&proc, "status").unwrap(), "Threads:").unwrap(),
                "1"
            );
            native_thread_status(&proc, identity, tgid, 0).unwrap();
            assert!(native_thread_status(&proc, identity, tid, 0).is_err());
            assert!(native_thread_status(&proc, identity, tgid, 1).is_err());
            drop(done_tx);
        });
    }

    #[test]
    fn inherited_native_real_pidfd_rejects_arm_on_non_listener_without_attaching() {
        // An actual PIDFD is insufficient. A regular descriptor has no ARM
        // authority and the original process remains untraced.
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, libc::getpid(), PIDFD_THREAD) };
        assert!(raw >= 0);
        let pidfd = unsafe { OwnedFd::from_raw_fd(raw as i32) };
        assert_eq!(filesystem_kind_fd(pidfd.as_raw_fd()).unwrap(), PIDFS_MAGIC);
        let f = tempfile::tempfile().unwrap();
        let request = Arm {
            id: 1,
            pidfd: pidfd.as_raw_fd(),
            mntns_fd: -1,
            flags: 0,
            reserved: 0,
        };
        assert_eq!(
            unsafe { libc::ioctl(f.as_raw_fd(), ARM_NATIVE_EXIT, &request) },
            -1
        );
        assert_eq!(
            io::Error::last_os_error().raw_os_error(),
            Some(libc::ENOTTY)
        );
        let proc = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(format!("/proc/{}", unsafe { libc::getpid() }))
            .unwrap();
        let raw = read_proc(&proc, "status").unwrap();
        assert_eq!(canonical_status_value(&raw, "TracerPid:").unwrap(), "0");
    }
}
