//! Original default mount custody and the original init's later identity epoch.
//!
//! The initial baseline is the actual completed NEWNS round trip. A new live
//! identity is issued only while the same original init is stopped at the real
//! exit of its same-ID kernel-armed setns. This is separate from APEX activation:
//! a file publication never grants a payload mount or a running apexd identity.
use super::*;
use crate::production_runtime_assets::OriginalInitBootstrapBind;
use std::cell::{Ref, RefCell, RefMut};
use std::rc::Rc;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum InitNamespace {
    Bootstrap,
    Default,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct InitEpoch {
    namespace: InitNamespace,
    serial: u64,
    notification: u64,
    instruction_pointer: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum ChangePhase {
    Prepared,
    ExitObserved,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct PendingInit {
    notification: wire::Notification,
    before: InitEpoch,
    target: InitNamespace,
    phase: ChangePhase,
    actual_errno: Option<i32>,
    actual_after: Option<Node>,
}

fn projected_init_exit(
    before: InitEpoch,
    target: InitNamespace,
    notification: &wire::Notification,
    errno: i32,
    after: Node,
    bootstrap: Node,
    default: Node,
) -> Result<InitEpoch> {
    if bootstrap == default || !(0..=4095).contains(&errno) || [512, 513, 514, 516].contains(&errno)
    {
        return Err(NamespaceError::Rejected(
            "original init exit errno or namespace objects",
        ));
    }
    let namespace = if errno == 0 { target } else { before.namespace };
    let expected = match namespace {
        InitNamespace::Bootstrap => bootstrap,
        InitNamespace::Default => default,
    };
    if after != expected {
        return Err(NamespaceError::Rejected(
            "original init errno and current namespace disagree",
        ));
    }
    Ok(InitEpoch {
        namespace,
        serial: before
            .serial
            .checked_add(1)
            .ok_or(NamespaceError::Rejected(
                "original init epoch serial overflow",
            ))?,
        notification: notification.id,
        instruction_pointer: notification.data.instruction_pointer,
    })
}

impl PendingInit {
    fn expected_exit(
        &self,
        notification: &wire::Notification,
        errno: i32,
        after: Node,
        bootstrap: Node,
        default: Node,
    ) -> Result<InitEpoch> {
        if self.phase != ChangePhase::Prepared || notification != &self.notification {
            return Err(NamespaceError::Rejected(
                "original init actual exit replay or wrong notification",
            ));
        }
        projected_init_exit(
            self.before,
            self.target,
            notification,
            errno,
            after,
            bootstrap,
            default,
        )
    }

    fn recorded_epoch(
        &self,
        notification: &wire::Notification,
        bootstrap: Node,
        default: Node,
    ) -> Result<InitEpoch> {
        if self.phase != ChangePhase::ExitObserved || notification != &self.notification {
            return Err(NamespaceError::Rejected(
                "original init detach lacks the same actual exit",
            ));
        }
        projected_init_exit(
            self.before,
            self.target,
            notification,
            self.actual_errno
                .ok_or(NamespaceError::RetirementUnproven)?,
            self.actual_after
                .ok_or(NamespaceError::RetirementUnproven)?,
            bootstrap,
            default,
        )
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum BootstrapPhase {
    Prepared,
    Observed,
    ResponseSent,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct PendingBootstrap {
    notification: wire::Notification,
    revision: u64,
    phase: BootstrapPhase,
    errno: Option<i32>,
}

/// Created once by the original inherited listener after its real initial
/// round trip. No descriptor, path or caller-supplied epoch constructs it.
pub(in super::super) struct OriginalBootstrapBindChange {
    owner: Rc<DefaultMountOwner>,
    notification: wire::Notification,
    revision: u64,
}

/// This is a borrow of the original pending journal, not another owner or a
/// success receipt. Dropping it before a successful SEND leaves Observed.
pub(in super::super) struct OriginalBootstrapReply<'a> {
    pending: RefMut<'a, PendingBootstrap>,
}

impl OriginalBootstrapReply<'_> {
    /// Call immediately after the same SEND returns zero. No read, allocation,
    /// lookup, fallible borrow or live-task observation occurs here.
    pub(in super::super) fn sent(mut self) {
        self.pending.phase = BootstrapPhase::ResponseSent;
    }
}

struct Ledger {
    bootstrap: mount_epoch::SuccessorGraph,
    default: mount_epoch::SuccessorGraph,
    revision: u64,
    init: InitEpoch,
    pending_init: Option<PendingInit>,
    pending_bootstrap: Option<PendingBootstrap>,
    bootstrap_result: Option<i32>,
    bootstrap_history: Option<mount_epoch::SuccessorGraph>,
    retired: bool,
}

/// No public fields, decoding or independent authority constructor.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct DefaultMountBinding {
    original: Binding,
    namespace: Node,
    revision: u64,
    init_epoch: u64,
}

// Equality-test values only. This constructor does not exist in production,
// cannot create a DefaultMountOwner, and holds no live task or kernel handle.
#[cfg(test)]
impl DefaultMountBinding {
    pub(super) fn from_test_parts(
        original: Binding,
        namespace: Node,
        revision: u64,
        init_epoch: u64,
    ) -> Self {
        Self { original, namespace, revision, init_epoch }
    }
}

/// Shared only inside the original TreeChild and its one notification owner.
/// It is deliberately !Send/!Sync and is never recreated from a selection.
pub(in super::super) struct DefaultMountOwner {
    context: RuntimeMacOwner,
    original: Binding,
    pidfd: OwnedFd,
    proc: File,
    user: File,
    bootstrap: File,
    bootstrap_node: Node,
    default: File,
    default_node: Node,
    root: File,
    root_node: Node,
    ledger: RefCell<Ledger>,
    bootstrap_worker: RefCell<Option<OriginalInitBootstrapBind>>,
}

/// A borrow of the same owner, not an independently transferable FD grant.
pub(crate) struct DefaultMountAuthority<'a> {
    owner: &'a DefaultMountOwner,
    child: &'a TreeChild,
}

/// A failed or dropped transition cannot clear the owner's pending journal.
pub(super) struct OriginalInitChange {
    owner: Rc<DefaultMountOwner>,
    notification: wire::Notification,
    before: InitEpoch,
    target: InitNamespace,
}

impl DefaultMountOwner {
    pub(super) fn issue(r: &Resources, child: &TreeChild) -> Result<Rc<Self>> {
        if binding(child)? != r.binding || child.default_mounts.get().is_some() {
            return Err(NamespaceError::Rejected(
                "default mount owner generation or replay",
            ));
        }
        child.verify()?;
        let (bootstrap_graph, default_graph) = r
            .epoch
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?
            .completed_graphs()?;
        let default = r
            .default
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?
            .try_clone()?;
        let root = r
            .default_root
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?
            .try_clone()?;
        let value = Rc::new(Self {
            context: r.context.clone(),
            original: r.binding,
            pidfd: r.pidfd.try_clone()?,
            proc: r.proc.try_clone()?,
            user: r.user.try_clone()?,
            bootstrap: r.bootstrap.try_clone()?,
            bootstrap_node: Node::of(&r.bootstrap)?,
            default_node: Node::of(&default)?,
            default,
            root_node: Node::of(&root)?,
            root,
            ledger: RefCell::new(Ledger {
                bootstrap: bootstrap_graph,
                default: default_graph,
                revision: 0,
                init: InitEpoch {
                    namespace: InitNamespace::Bootstrap,
                    serial: 0,
                    notification: 0,
                    instruction_pointer: 0,
                },
                pending_init: None,
                pending_bootstrap: None,
                bootstrap_result: None,
                bootstrap_history: None,
                retired: false,
            }),
            bootstrap_worker: RefCell::new(None),
        });
        if value.bootstrap_node == value.default_node {
            return Err(NamespaceError::Rejected(
                "default owner lacks distinct original namespaces",
            ));
        }
        value.verify_custody()?;
        value.verify_original_mount(&child.pidfd, None)?;
        child
            .default_mounts
            .set(Rc::clone(&value))
            .map_err(|_| NamespaceError::Rejected("original default owner already issued"))?;
        // Custody is now in the original child even if a subsequent handoff
        // check fails. Its normal original PIDFD retirement remains required.
        Ok(value)
    }

    fn verify_custody(&self) -> Result<()> {
        if unsafe { libc::syscall(libc::SYS_gettid) } != self.original.creator_tid as libc::c_long
            || fd_node(self.pidfd.as_raw_fd())? != self.original.pidfd
            || Node::of(&self.proc)? != self.original.proc
            || Node::of(&self.user)? != self.original.user
            || Node::of(&self.bootstrap)? != self.bootstrap_node
            || Node::of(&self.default)? != self.default_node
            || Node::of(&self.root)? != self.root_node
        {
            return Err(NamespaceError::Rejected(
                "original default namespace custody changed",
            ));
        }
        self.context
            .objects()
            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        for file in [&self.bootstrap, &self.default] {
            if filesystem_kind(file)? != NSFS_MAGIC
                || unsafe { libc::ioctl(file.as_raw_fd(), NS_GET_NSTYPE) } != libc::CLONE_NEWNS
            {
                return Err(NamespaceError::Rejected(
                    "original default namespace type changed",
                ));
            }
            require_namespace_owner(file, self.original.user)?;
        }
        Ok(())
    }

    fn namespace_node(&self, namespace: InitNamespace) -> Node {
        match namespace {
            InitNamespace::Bootstrap => self.bootstrap_node,
            InitNamespace::Default => self.default_node,
        }
    }

    fn namespace_kind(&self, node: Node) -> Result<InitNamespace> {
        if node == self.bootstrap_node {
            Ok(InitNamespace::Bootstrap)
        } else if node == self.default_node {
            Ok(InitNamespace::Default)
        } else {
            Err(NamespaceError::Rejected(
                "init target is not its original namespace object",
            ))
        }
    }

    fn require_pending<'a>(
        &self,
        ledger: &'a Ledger,
        change: &OriginalInitChange,
    ) -> Result<&'a PendingInit> {
        if !std::ptr::eq(self, Rc::as_ptr(&change.owner)) || ledger.retired {
            return Err(NamespaceError::Rejected(
                "original init transition owner changed",
            ));
        }
        let pending = ledger
            .pending_init
            .as_ref()
            .ok_or(NamespaceError::Rejected(
                "original init transition journal absent",
            ))?;
        if pending.notification != change.notification
            || pending.before != change.before
            || pending.target != change.target
        {
            return Err(NamespaceError::Rejected(
                "original init transition journal differs",
            ));
        }
        Ok(pending)
    }

    pub(super) fn verify_original_mount(
        &self,
        pidfd: &OwnedFd,
        change: Option<&OriginalInitChange>,
    ) -> Result<()> {
        self.verify_custody()?;
        if fd_node(pidfd.as_raw_fd())? != self.original.pidfd
            || pidfd_exited(pidfd)?
            || read_identity(&self.proc, self.original.identity.pid)? != self.original.identity
        {
            return Err(NamespaceError::Rejected(
                "default epoch belongs to another original init",
            ));
        }
        let current = from_pidfd(pidfd, 0xff03, libc::CLONE_NEWNS)?;
        require_namespace_owner(&current, self.original.user)?;
        let actual = Node::of(&current)?;
        let ledger = self
            .ledger
            .try_borrow()
            .map_err(|_| NamespaceError::Rejected("default ledger is in mutation"))?;
        if ledger.retired {
            return Err(NamespaceError::Rejected("original default ledger retired"));
        }
        if let Some(change) = change {
            let pending = self.require_pending(&ledger, change)?;
            let before = self.namespace_node(pending.before.namespace);
            let target = self.namespace_node(pending.target);
            if actual != before && actual != target {
                return Err(NamespaceError::Rejected(
                    "in-flight original init left both held epochs",
                ));
            }
            if pending.phase == ChangePhase::ExitObserved && Some(actual) != pending.actual_after {
                return Err(NamespaceError::Rejected(
                    "observed original init exit epoch changed",
                ));
            }
        } else if ledger.pending_init.is_some()
            || actual != self.namespace_node(ledger.init.namespace)
        {
            return Err(NamespaceError::Rejected(
                "original init has no completed active mount epoch",
            ));
        }
        Ok(())
    }

    pub(in super::super) fn verify_child(&self, child: &TreeChild) -> Result<()> {
        if binding(child)? != self.original {
            return Err(NamespaceError::Rejected(
                "default identity epoch generation differs",
            ));
        }
        self.verify_original_mount(&child.pidfd, None)
    }

    pub(in super::super) fn current_namespace(&self, child: &TreeChild) -> Result<&File> {
        self.verify_child(child)?;
        let ledger = self
            .ledger
            .try_borrow()
            .map_err(|_| NamespaceError::Rejected("default ledger is in mutation"))?;
        Ok(match ledger.init.namespace {
            InitNamespace::Bootstrap => &self.bootstrap,
            InitNamespace::Default => &self.default,
        })
    }

    pub(in super::super) fn verify_current_layout(&self, child: &TreeChild) -> Result<()> {
        self.verify_child(child)?;
        let root = namespace_root(&child.proc_dir)?;
        let ledger = self
            .ledger
            .try_borrow()
            .map_err(|_| NamespaceError::Rejected("default ledger is in mutation"))?;
        if ledger.pending_bootstrap.is_some() {
            return Err(NamespaceError::Rejected(
                "bootstrap bind graph mutation is unfinished",
            ));
        }
        if let Some(history) = &ledger.bootstrap_history {
            history.revalidate_bootstrap_bind_history()?;
        }
        match ledger.init.namespace {
            InitNamespace::Bootstrap => ledger.bootstrap.matches(&child.proc_dir, &root)?,
            InitNamespace::Default => ledger.default.matches(&child.proc_dir, &root)?,
        }
        self.verify_child(child)
    }

    pub(in super::super) fn authority<'a>(
        &'a self,
        child: &'a TreeChild,
    ) -> Result<DefaultMountAuthority<'a>> {
        let value = DefaultMountAuthority { owner: self, child };
        value.revalidate()?;
        Ok(value)
    }

    pub(super) fn bootstrap_complete(&self) -> Result<()> {
        self.verify_custody()?;
        let ledger = self
            .ledger
            .try_borrow()
            .map_err(|_| NamespaceError::Rejected("bootstrap bind ledger is borrowed"))?;
        if ledger.retired
            || ledger.pending_bootstrap.is_some()
            || ledger.bootstrap_result != Some(0)
        {
            return Err(NamespaceError::Rejected(
                "original bootstrap bind has not completed",
            ));
        }
        Ok(())
    }

    pub(super) fn verify_target_graph(
        &self,
        namespace: Node,
        graph: &mount_epoch::SuccessorGraph,
    ) -> Result<()> {
        self.bootstrap_complete()?;
        let target = self.namespace_kind(namespace)?;
        let ledger = self
            .ledger
            .try_borrow()
            .map_err(|_| NamespaceError::Rejected("default target graph is borrowed"))?;
        if ledger.pending_init.is_some() {
            return Err(NamespaceError::Rejected(
                "default target has an unfinished original transition",
            ));
        }
        match target {
            InitNamespace::Bootstrap => ledger.bootstrap.same_observation(graph)?,
            InitNamespace::Default => ledger.default.same_observation(graph)?,
        }
        if let Some(history) = &ledger.bootstrap_history {
            history.revalidate_bootstrap_bind_history()?;
        }
        self.verify_custody()
    }

    /// A default apexd identity requires the original init's actual completed
    /// default epoch and this complete caller graph, never only held NS FDs.
    pub(super) fn apexd_binding(
        &self,
        namespace: Node,
        graph: &mount_epoch::SuccessorGraph,
    ) -> Result<DefaultMountBinding> {
        self.verify_original_mount(&self.pidfd, None)?;
        self.verify_target_graph(namespace, graph)?;
        let ledger = self
            .ledger
            .try_borrow()
            .map_err(|_| NamespaceError::Rejected("apexd default ledger is in mutation"))?;
        if ledger.retired
            || ledger.pending_init.is_some()
            || ledger.pending_bootstrap.is_some()
            || ledger.bootstrap_result != Some(0)
            || ledger.init.namespace != InitNamespace::Default
            || ledger.init.serial == 0
            || namespace != self.default_node
        {
            return Err(NamespaceError::Rejected(
                "actual original default apexd epoch has not completed",
            ));
        }
        ledger.default.same_observation(graph)?;
        Ok(DefaultMountBinding {
            original: self.original,
            namespace: self.default_node,
            revision: ledger.revision,
            init_epoch: ledger.init.serial,
        })
    }

    pub(super) fn begin_bootstrap_bind(
        self: &Rc<Self>,
        child: &TreeChild,
        notification: wire::Notification,
    ) -> Result<OriginalBootstrapBindChange> {
        self.verify_child(child)?;
        if notification.pid != self.original.identity.pid
            || notification.flags != 0
            || notification.data.arch != ARCH_X86_64
            || notification.data.nr != libc::SYS_mount as i32
            || notification.data.instruction_pointer == 0
            || notification.operation() != Some(wire::Operation::Mount)
        {
            return Err(NamespaceError::Rejected(
                "bootstrap bind is not the original native mount",
            ));
        }
        let mut ledger = self
            .ledger
            .try_borrow_mut()
            .map_err(|_| NamespaceError::Rejected("bootstrap bind ledger is borrowed"))?;
        if ledger.retired
            || ledger.pending_init.is_some()
            || ledger.pending_bootstrap.is_some()
            || ledger.bootstrap_result.is_some()
            || ledger.bootstrap_history.is_some()
            || ledger.revision != 0
            || ledger.init.namespace != InitNamespace::Bootstrap
            || ledger.init.serial != 0
            || self
                .bootstrap_worker
                .try_borrow()
                .map_err(|_| NamespaceError::Rejected("bootstrap helper is borrowed"))?
                .is_some()
        {
            return Err(NamespaceError::Rejected(
                "original bootstrap bind phase or replay",
            ));
        }
        ledger
            .bootstrap
            .matches(&child.proc_dir, &namespace_root(&child.proc_dir)?)?;
        ledger.default.revalidate_held()?;
        let revision = ledger.revision;
        ledger.pending_bootstrap = Some(PendingBootstrap {
            notification,
            revision,
            phase: BootstrapPhase::Prepared,
            errno: None,
        });
        Ok(OriginalBootstrapBindChange {
            owner: Rc::clone(self),
            notification,
            revision,
        })
    }

    pub(super) fn retire_bootstrap_helper(&self) -> Result<()> {
        let mut worker = self
            .bootstrap_worker
            .try_borrow_mut()
            .map_err(|_| NamespaceError::RetirementUnproven)?;
        if let Some(worker) = worker.as_mut() {
            worker
                .retire_helper()
                .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        }
        Ok(())
    }

    pub(super) fn begin_original(
        self: &Rc<Self>,
        notification: wire::Notification,
        before: Node,
        target: &File,
        graph: &mount_epoch::SuccessorGraph,
    ) -> Result<OriginalInitChange> {
        self.verify_original_mount(&self.pidfd, None)?;
        self.bootstrap_complete()?;
        if notification.pid != self.original.identity.pid
            || notification.operation() != Some(wire::Operation::SetNamespace)
            || notification.data.nr != libc::SYS_setns as i32
            || notification.data.arch != ARCH_X86_64
            || notification.flags != 0
            || notification.data.instruction_pointer == 0
            || notification.data.args[1] != libc::CLONE_NEWNS as u64
            || !(1..=i32::MAX as u64).contains(&notification.data.args[0])
        {
            return Err(NamespaceError::Rejected(
                "original init epoch requires its exact native setns",
            ));
        }
        require_namespace_owner(target, self.original.user)?;
        let target = self.namespace_kind(Node::of(target)?)?;
        let mut ledger = self
            .ledger
            .try_borrow_mut()
            .map_err(|_| NamespaceError::Rejected("default ledger is in mutation"))?;
        if ledger.pending_init.is_some()
            || ledger.retired
            || ledger.init.serial == u64::MAX
            || (ledger.init.serial != 0 && notification.id == ledger.init.notification)
            || before != self.namespace_node(ledger.init.namespace)
        {
            return Err(NamespaceError::Rejected(
                "original init epoch transition replay",
            ));
        }
        match ledger.init.namespace {
            InitNamespace::Bootstrap => ledger.bootstrap.same_observation(graph)?,
            InitNamespace::Default => ledger.default.same_observation(graph)?,
        }
        let change = OriginalInitChange {
            owner: Rc::clone(self),
            notification,
            before: ledger.init,
            target,
        };
        ledger.pending_init = Some(PendingInit {
            notification,
            before: ledger.init,
            target,
            phase: ChangePhase::Prepared,
            actual_errno: None,
            actual_after: None,
        });
        Ok(change)
    }

    pub(super) fn retire_after_original_reap(
        &self,
        child: &TreeChild,
        exit: &ChildExit,
    ) -> Result<()> {
        self.verify_custody()?;
        if binding(child)? != self.original
            || exit.pid != self.original.identity.pid
            || !pidfd_exited(&self.pidfd)?
        {
            return Err(NamespaceError::RetirementUnproven);
        }
        if let Some(worker) = self
            .bootstrap_worker
            .try_borrow_mut()
            .map_err(|_| NamespaceError::RetirementUnproven)?
            .as_mut()
        {
            worker
                .retire_views()
                .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        }
        let mut ledger = self
            .ledger
            .try_borrow_mut()
            .map_err(|_| NamespaceError::RetirementUnproven)?;
        ledger.retired = true;
        Ok(())
    }
}

impl OriginalBootstrapBindChange {
    pub(super) fn require_owner(&self, owner: &Rc<DefaultMountOwner>) -> Result<()> {
        if !Rc::ptr_eq(&self.owner, owner) {
            return Err(NamespaceError::Rejected(
                "bootstrap bind changed its unique original owner",
            ));
        }
        Ok(())
    }

    fn pending<'a>(&self, ledger: &'a Ledger) -> Result<&'a PendingBootstrap> {
        let pending = ledger
            .pending_bootstrap
            .as_ref()
            .ok_or(NamespaceError::Rejected("bootstrap bind journal absent"))?;
        if ledger.retired
            || pending.notification != self.notification
            || pending.revision != self.revision
            || ledger.pending_init.is_some()
            || ledger.init.namespace != InitNamespace::Bootstrap
            || ledger.init.serial != 0
            || ledger.bootstrap_result.is_some()
        {
            return Err(NamespaceError::Rejected(
                "bootstrap bind original journal changed",
            ));
        }
        Ok(pending)
    }

    pub(in super::super) fn revalidate(&self, child: &TreeChild) -> Result<()> {
        self.owner.verify_child(child)?;
        let ledger = self
            .owner
            .ledger
            .try_borrow()
            .map_err(|_| NamespaceError::Rejected("bootstrap ledger is borrowed"))?;
        self.pending(&ledger)?;
        ledger.default.revalidate_held()?;
        Ok(())
    }

    pub(in super::super) fn before_mount(
        &self,
        child: &TreeChild,
        source: &File,
        target: &File,
    ) -> Result<()> {
        self.revalidate(child)?;
        let ledger = self
            .owner
            .ledger
            .try_borrow()
            .map_err(|_| NamespaceError::Rejected("bootstrap ledger is borrowed"))?;
        if self.pending(&ledger)?.phase != BootstrapPhase::Prepared
            || ledger.revision != self.revision
            || ledger.bootstrap_history.is_some()
        {
            return Err(NamespaceError::Rejected(
                "bootstrap mount has already been observed",
            ));
        }
        ledger
            .bootstrap
            .before_original_bootstrap_bind(source, target)?;
        ledger
            .bootstrap
            .matches(&child.proc_dir, &namespace_root(&child.proc_dir)?)
    }

    pub(in super::super) fn install_worker(
        &self,
        child: &TreeChild,
        worker: OriginalInitBootstrapBind,
    ) -> Result<()> {
        self.revalidate(child)?;
        let mut slot = self
            .owner
            .bootstrap_worker
            .try_borrow_mut()
            .map_err(|_| NamespaceError::Rejected("bootstrap helper already borrowed"))?;
        if slot.is_some() {
            return Err(NamespaceError::Rejected("bootstrap helper already owned"));
        }
        *slot = Some(worker);
        Ok(())
    }

    pub(in super::super) fn worker(&self) -> Result<Ref<'_, OriginalInitBootstrapBind>> {
        Ref::filter_map(
            self.owner
                .bootstrap_worker
                .try_borrow()
                .map_err(|_| NamespaceError::Rejected("bootstrap helper already borrowed"))?,
            |x| x.as_ref(),
        )
        .map_err(|_| NamespaceError::RetirementUnproven)
    }

    pub(in super::super) fn worker_mut(&self) -> Result<RefMut<'_, OriginalInitBootstrapBind>> {
        RefMut::filter_map(
            self.owner
                .bootstrap_worker
                .try_borrow_mut()
                .map_err(|_| NamespaceError::Rejected("bootstrap helper already borrowed"))?,
            |x| x.as_mut(),
        )
        .map_err(|_| NamespaceError::RetirementUnproven)
    }

    pub(in super::super) fn observe_actual(
        &self,
        child: &TreeChild,
        source: &File,
        target: &File,
        errno: i32,
    ) -> Result<()> {
        self.revalidate(child)?;
        let root = namespace_root(&child.proc_dir)?;
        let after = mount_epoch::SuccessorGraph::observe(&child.proc_dir, &root)?;
        let mut ledger = self
            .owner
            .ledger
            .try_borrow_mut()
            .map_err(|_| NamespaceError::Rejected("bootstrap ledger is borrowed"))?;
        if self.pending(&ledger)?.phase != BootstrapPhase::Prepared
            || ledger.revision != self.revision
            || ledger.bootstrap_history.is_some()
        {
            return Err(NamespaceError::Rejected("bootstrap result replay"));
        }
        ledger
            .bootstrap
            .verify_original_bootstrap_bind(&after, source, target, errno)?;
        ledger.default.revalidate_held()?;
        if errno == 0 {
            let revision = ledger
                .revision
                .checked_add(1)
                .ok_or(NamespaceError::Rejected(
                    "bootstrap graph revision overflow",
                ))?;
            let before = std::mem::replace(&mut ledger.bootstrap, after);
            ledger.bootstrap_history = Some(before);
            ledger.revision = revision;
        }
        let pending = ledger.pending_bootstrap.as_mut().unwrap();
        pending.phase = BootstrapPhase::Observed;
        pending.errno = Some(errno);
        Ok(())
    }

    pub(in super::super) fn require_actual(&self, child: &TreeChild, errno: i32) -> Result<()> {
        self.revalidate(child)?;
        let ledger = self
            .owner
            .ledger
            .try_borrow()
            .map_err(|_| NamespaceError::Rejected("bootstrap ledger is borrowed"))?;
        let pending = self.pending(&ledger)?;
        if pending.phase != BootstrapPhase::Observed
            || pending.errno != Some(errno)
            || (errno == 0) != (ledger.bootstrap_history.is_some())
        {
            return Err(NamespaceError::Rejected(
                "bootstrap reply lacks the same actual result",
            ));
        }
        ledger
            .bootstrap
            .matches(&child.proc_dir, &namespace_root(&child.proc_dir)?)?;
        if let Some(history) = &ledger.bootstrap_history {
            history.revalidate_bootstrap_bind_history()?;
        }
        Ok(())
    }

    /// All fallible observation and the sole mutable journal borrow are
    /// obtained before SEND. The resulting guard cannot perform I/O.
    pub(in super::super) fn prepare_response(
        &self,
        child: &TreeChild,
        errno: i32,
    ) -> Result<OriginalBootstrapReply<'_>> {
        self.require_actual(child, errno)?;
        let ledger = self
            .owner
            .ledger
            .try_borrow_mut()
            .map_err(|_| NamespaceError::Rejected("bootstrap ledger is borrowed"))?;
        let pending = self.pending(&ledger)?;
        if pending.phase != BootstrapPhase::Observed || pending.errno != Some(errno) {
            return Err(NamespaceError::Rejected(
                "bootstrap reply preparation lost its observed result",
            ));
        }
        Ok(OriginalBootstrapReply {
            pending: RefMut::map(ledger, |ledger| {
                ledger
                    .pending_bootstrap
                    .as_mut()
                    .expect("checked pending bootstrap")
            }),
        })
    }

    pub(in super::super) fn complete_response(&self, child: &TreeChild, errno: i32) -> Result<()> {
        self.revalidate(child)?;
        let mut ledger = self
            .owner
            .ledger
            .try_borrow_mut()
            .map_err(|_| NamespaceError::Rejected("bootstrap ledger is borrowed"))?;
        let pending = self.pending(&ledger)?;
        if pending.phase != BootstrapPhase::ResponseSent || pending.errno != Some(errno) {
            return Err(NamespaceError::Rejected(
                "bootstrap response was not actually delivered",
            ));
        }
        ledger.bootstrap_result = Some(errno);
        ledger.pending_bootstrap = None;
        Ok(())
    }
}

impl OriginalInitChange {
    pub(super) fn verify(&self, owner: &Rc<DefaultMountOwner>) -> Result<()> {
        if !Rc::ptr_eq(owner, &self.owner) {
            return Err(NamespaceError::Rejected(
                "native original transition owner was substituted",
            ));
        }
        owner.verify_original_mount(&owner.pidfd, Some(self))
    }

    pub(super) fn observe_exit(
        &self,
        notification: &wire::Notification,
        errno: i32,
        after: Node,
        graph: &mount_epoch::SuccessorGraph,
    ) -> Result<()> {
        self.verify(&self.owner)?;
        let mut ledger = self
            .owner
            .ledger
            .try_borrow_mut()
            .map_err(|_| NamespaceError::Rejected("default ledger is in mutation"))?;
        let pending = *self.owner.require_pending(&ledger, self)?;
        let projected = pending.expected_exit(
            notification,
            errno,
            after,
            self.owner.bootstrap_node,
            self.owner.default_node,
        )?;
        let namespace = projected.namespace;
        // Exact approved target graph, never a new arbitrary snapshot baseline.
        match namespace {
            InitNamespace::Bootstrap => ledger.bootstrap.same_observation(graph)?,
            InitNamespace::Default => ledger.default.same_observation(graph)?,
        }
        let pending = ledger.pending_init.as_mut().unwrap();
        pending.phase = ChangePhase::ExitObserved;
        pending.actual_errno = Some(errno);
        pending.actual_after = Some(after);
        // Identity remains unavailable to ordinary witnesses until actual
        // stopped DETACH below. A failure retains the original pending owner.
        Ok(())
    }

    pub(super) fn detached(&self, notification: &wire::Notification) -> Result<()> {
        self.verify(&self.owner)?;
        if notification != &self.notification {
            return Err(NamespaceError::Rejected(
                "original init detach notification differs",
            ));
        }
        let mut ledger = self
            .owner
            .ledger
            .try_borrow_mut()
            .map_err(|_| NamespaceError::Rejected("default ledger is in mutation"))?;
        let pending = *self.owner.require_pending(&ledger, self)?;
        ledger.init = pending.recorded_epoch(
            notification,
            self.owner.bootstrap_node,
            self.owner.default_node,
        )?;
        ledger.pending_init = None;
        Ok(())
    }
}

impl DefaultMountAuthority<'_> {
    pub(crate) fn revalidate(&self) -> Result<()> {
        self.child.verify()?;
        self.owner.verify_child(self.child)?;
        let ledger = self.owner.ledger.try_borrow().map_err(|_| {
            NamespaceError::Rejected("default publication ledger is already borrowed")
        })?;
        if ledger.retired
            || ledger.pending_init.is_some()
            || ledger.pending_bootstrap.is_some()
            || ledger.bootstrap_result != Some(0)
        {
            return Err(NamespaceError::Rejected(
                "default namespace has an unfinished original actor",
            ));
        }
        ledger.bootstrap.revalidate_held()?;
        ledger.default.revalidate_held()?;
        self.owner.verify_child(self.child)
    }

    pub(crate) fn mount_namespace(&self) -> Result<&File> {
        self.revalidate()?;
        Ok(&self.owner.default)
    }

    pub(crate) fn root_directory(&self) -> Result<&File> {
        self.revalidate()?;
        Ok(&self.owner.root)
    }

    pub(crate) fn binding(&self) -> Result<DefaultMountBinding> {
        self.revalidate()?;
        let ledger = self
            .owner
            .ledger
            .try_borrow()
            .map_err(|_| NamespaceError::Rejected("default ledger is in mutation"))?;
        Ok(DefaultMountBinding {
            original: self.owner.original,
            namespace: self.owner.default_node,
            revision: ledger.revision,
            init_epoch: ledger.init.serial,
        })
    }

    pub(crate) fn require_owner(&self, context: &RuntimeMacOwner) -> Result<()> {
        self.revalidate()?;
        let (mac, selection) = context
            .objects()
            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        self.owner
            .context
            .require_pair(mac, selection)
            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        self.revalidate()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pending() -> PendingInit {
        PendingInit {
            notification: wire::Notification {
                id: 44,
                pid: 123,
                flags: 0,
                data: wire::Data {
                    nr: libc::SYS_setns as i32,
                    arch: ARCH_X86_64,
                    instruction_pointer: 0x1000,
                    args: [9, libc::CLONE_NEWNS as u64, 0, 0, 0, 0],
                },
            },
            before: InitEpoch {
                namespace: InitNamespace::Bootstrap,
                serial: 7,
                notification: 39,
                instruction_pointer: 0x2000,
            },
            target: InitNamespace::Default,
            phase: ChangePhase::Prepared,
            actual_errno: None,
            actual_after: None,
        }
    }

    #[test]
    fn original_default_epoch_projection_preserves_native_errno_and_rejects_wrong_namespace() {
        // This tests data projections only; no owner, File, PIDFD, MAC or
        // authority is created from these fixture records.
        let bootstrap = Node {
            device: 1,
            inode: 11,
        };
        let default = Node {
            device: 1,
            inode: 22,
        };
        let p = pending();
        let success = p
            .expected_exit(&p.notification, 0, default, bootstrap, default)
            .unwrap();
        assert_eq!(success.namespace, InitNamespace::Default);
        assert_eq!(success.serial, 8);
        let failed = p
            .expected_exit(&p.notification, libc::EPERM, bootstrap, bootstrap, default)
            .unwrap();
        assert_eq!(failed.namespace, InitNamespace::Bootstrap);
        assert_eq!(failed.serial, 8);
        assert!(
            p.expected_exit(&p.notification, 0, bootstrap, bootstrap, default)
                .is_err()
        );
        assert!(
            p.expected_exit(&p.notification, libc::EPERM, default, bootstrap, default)
                .is_err()
        );
        assert!(
            p.expected_exit(
                &p.notification,
                0,
                Node {
                    device: 1,
                    inode: 33
                },
                bootstrap,
                default
            )
            .is_err()
        );
        assert!(
            p.expected_exit(&p.notification, 0, default, default, default)
                .is_err()
        );
        for errno in [-1, 4096, 512, 513, 514, 516] {
            assert!(
                p.expected_exit(&p.notification, errno, bootstrap, bootstrap, default)
                    .is_err()
            );
        }
        let mut overflow = p;
        overflow.before.serial = u64::MAX;
        assert!(
            overflow
                .expected_exit(&p.notification, 0, default, bootstrap, default)
                .is_err()
        );
    }

    #[test]
    fn original_default_epoch_journal_rejects_changed_notification_replay_and_unobserved_detach() {
        let bootstrap = Node {
            device: 1,
            inode: 11,
        };
        let default = Node {
            device: 1,
            inode: 22,
        };
        let mut p = pending();
        assert!(
            p.recorded_epoch(&p.notification, bootstrap, default)
                .is_err()
        );
        let original = p.notification;
        let mut variants = Vec::new();
        let mut n = original;
        n.id += 1;
        variants.push(n);
        let mut n = original;
        n.pid += 1;
        variants.push(n);
        let mut n = original;
        n.data.instruction_pointer += 1;
        variants.push(n);
        let mut n = original;
        n.data.args[0] += 1;
        variants.push(n);
        let mut n = original;
        n.data.nr = libc::SYS_unshare as i32;
        variants.push(n);
        for n in variants {
            assert!(p.expected_exit(&n, 0, default, bootstrap, default).is_err());
        }
        p.phase = ChangePhase::ExitObserved;
        assert!(
            p.expected_exit(&original, 0, default, bootstrap, default)
                .is_err()
        );
        assert!(p.recorded_epoch(&original, bootstrap, default).is_err());
        p.actual_errno = Some(0);
        assert!(p.recorded_epoch(&original, bootstrap, default).is_err());
        p.actual_after = Some(default);
        assert_eq!(
            p.recorded_epoch(&original, bootstrap, default)
                .unwrap()
                .namespace,
            InitNamespace::Default
        );
        let mut n = original;
        n.id += 1;
        assert!(p.recorded_epoch(&n, bootstrap, default).is_err());
        p.actual_after = Some(bootstrap);
        assert!(p.recorded_epoch(&original, bootstrap, default).is_err());
    }
}
