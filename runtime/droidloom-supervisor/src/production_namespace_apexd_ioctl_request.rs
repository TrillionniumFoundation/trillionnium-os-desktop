//! Original normal-service apexd request custody in the approved default epoch.
//!
//! The listener has already received this exact request. This owner retains the
//! original dispatch RefMut and mount-actor ledger borrow until dropped. It
//! issues only observations and a single matched-source binding: no guest loop
//! handle, ioctl result, notification response, AVB, dm or mount success.
use super::super::original_ptrace::{ActualApexdGeneration, ActualApexdTask, DefaultMountBinding};
use super::*;
use crate::production_execution::RuntimeMacOwner;
use crate::production_mac::MacApexdTaskWitness;
use crate::production_private_loop_owner::compressed::MatchedDecompressedCapex;
use std::cell::Cell;
use std::os::unix::fs::FileTypeExt;

const CONFIGURE: u64 = 0x4c0a;
const CONFIG_BYTES: usize = 304;
const F_DUPFD_QUERY: libc::c_int = 1027;

fn before(end: Instant) -> Result<()> {
    if Instant::now() >= end {
        return Err(NamespaceError::Rejected(
            "original apexd request deadline expired",
        ));
    }
    Ok(())
}

fn error(error: impl std::fmt::Display) -> NamespaceError {
    NamespaceError::RuntimeResource(error.to_string())
}

fn configure_address(notification: &wire::Notification) -> Result<(i32, u64)> {
    if notification.id == 0
        || notification.pid <= 1
        || notification.flags != 0
        || notification.data.arch != 0xc000_003e
        || notification.data.nr != libc::SYS_ioctl as i32
        || notification.data.instruction_pointer == 0
        || notification.data.args[0] > i32::MAX as u64
        || notification.data.args[1] != CONFIGURE
        || notification.operation() != Some(wire::Operation::LoopIoctl)
    {
        return Err(NamespaceError::Rejected(
            "original apexd LOOP_CONFIGURE ABI differs",
        ));
    }
    let address = notification.data.args[2];
    if address == 0 || address > (i64::MAX as u64).saturating_sub(CONFIG_BYTES as u64) {
        return Err(NamespaceError::Rejected(
            "original apexd configuration address is unbounded",
        ));
    }
    Ok((notification.data.args[0] as i32, address))
}

fn read_configuration(memory: &File, address: u64, end: Instant) -> Result<[u8; CONFIG_BYTES]> {
    if address == 0 || address > (i64::MAX as u64).saturating_sub(CONFIG_BYTES as u64) {
        return Err(NamespaceError::Rejected(
            "original apexd configuration address is unbounded",
        ));
    }
    let mut bytes = [0_u8; CONFIG_BYTES];
    let mut done = 0;
    while done < bytes.len() {
        before(end)?;
        match memory.read_at(&mut bytes[done..], address + done as u64) {
            Ok(0) => {
                return Err(NamespaceError::Rejected(
                    "original apexd configuration is short",
                ));
            }
            Ok(count) => {
                before(end)?;
                done += count;
            }
            Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
            Err(e) => return Err(e.into()),
        }
    }
    before(end)?;
    Ok(bytes)
}

fn source_number(bytes: &[u8; CONFIG_BYTES]) -> Result<i32> {
    let number = u32::from_le_bytes(bytes[0..4].try_into().unwrap());
    if number > i32::MAX as u32 {
        // The actual fd=-1 support probe is a different kernel operation.
        // A failed PIDFD_GETFD is never translated into the probe's EBADF.
        return Err(NamespaceError::Rejected(
            "original apexd invalid-fd probe requires its actual loop provider",
        ));
    }
    Ok(number as i32)
}

/// The original support probe has no backing source descriptor. Parsing its
/// exact bytes is only classification: it grants no task, target or reply
/// authority and cannot supply a normal configuration or a live target lease.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct SupportProbeBody {
    bytes: [u8; CONFIG_BYTES],
}
impl SupportProbeBody {
    fn parse(bytes: [u8; CONFIG_BYTES]) -> Result<Self> {
        if u32::from_le_bytes(bytes[..4].try_into().unwrap()) != u32::MAX
            || bytes[4..].iter().any(|byte| *byte != 0)
        {
            return Err(NamespaceError::Rejected(
                "original apexd support probe is not exact fd=-1 with a zero body",
            ));
        }
        Ok(Self { bytes })
    }
}

/// A unique fixed size only selects the candidate to be fully hashed below.
/// It is not byte, caller, role or device authority.
fn compressed_role_for_length(bytes: u64) -> Result<usize> {
    let rows = crate::production_execution_profile::apex_inputs::original_inputs()
        .map_err(NamespaceError::Rejected)?;
    let mut selected = None;
    for (index, row) in rows.iter().enumerate() {
        if row.input.container_file.ends_with(".capex") && row.input.original_apex_bytes == bytes {
            if selected.replace(index).is_some() {
                return Err(NamespaceError::Rejected(
                    "original requested CAPEX size has multiple fixed candidates",
                ));
            }
        }
    }
    selected.ok_or(NamespaceError::Rejected(
        "original requested file has no fixed compressed APEX candidate",
    ))
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct FileIdentity {
    node: Node,
    mode: u32,
    uid: u32,
    gid: u32,
    links: u64,
    bytes: u64,
    mtime: (i64, i64),
    ctime: (i64, i64),
    rdev: u64,
    flags: i32,
}
impl FileIdentity {
    fn observe(file: &File) -> Result<Self> {
        let m = file.metadata()?;
        let flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
        let descriptor_flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFD) };
        if flags < 0 || descriptor_flags < 0 {
            return Err(io::Error::last_os_error().into());
        }
        if descriptor_flags & libc::FD_CLOEXEC == 0 || flags & libc::O_PATH != 0 {
            return Err(NamespaceError::Rejected(
                "original apexd duplicated descriptor shape differs",
            ));
        }
        Ok(Self {
            node: Node::of(file)?,
            mode: m.mode(),
            uid: m.uid(),
            gid: m.gid(),
            links: m.nlink(),
            bytes: m.len(),
            mtime: (m.mtime(), m.mtime_nsec()),
            ctime: (m.ctime(), m.ctime_nsec()),
            rdev: m.rdev(),
            flags,
        })
    }
}

fn same_open_file(original: &File, other: &File) -> Result<()> {
    let observed = unsafe { libc::fcntl(original.as_raw_fd(), F_DUPFD_QUERY, other.as_raw_fd()) };
    if observed < 0 {
        return Err(io::Error::last_os_error().into());
    }
    if observed != 1 {
        return Err(NamespaceError::Rejected(
            "original apexd descriptor is a different open file description",
        ));
    }
    Ok(())
}

fn copy_task_fd(task: &ActualApexdTask, number: i32, end: Instant) -> Result<File> {
    before(end)?;
    if number < 0 {
        return Err(NamespaceError::Rejected(
            "negative original apexd descriptor",
        ));
    }
    // PIDFD_GETFD targets the original thread object, never a numeric PID.
    let raw = unsafe { libc::syscall(libc::SYS_pidfd_getfd, task.pidfd().as_raw_fd(), number, 0) };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let result = unsafe { File::from_raw_fd(raw as i32) };
    before(end)?;
    FileIdentity::observe(&result)?;
    Ok(result)
}

fn readonly_source_identity(source: &File) -> Result<FileIdentity> {
    let identity = FileIdentity::observe(source)?;
    // Original CP3A first opens O_RDONLY|O_DIRECT and may fall back to
    // O_RDONLY. Preserve whichever complete flags the original OFD has.
    // Do not reopen it or toggle O_DIRECT while reading or matching it.
    if !source.metadata()?.is_file() || identity.flags & libc::O_ACCMODE != libc::O_RDONLY {
        return Err(NamespaceError::Rejected(
            "actual apexd backing is not an original readonly regular file",
        ));
    }
    Ok(identity)
}

fn require_input_shapes(source: &File, target: &File) -> Result<()> {
    readonly_source_identity(source)?;
    let target_identity = FileIdentity::observe(target)?;
    if !target.metadata()?.file_type().is_block_device()
        || target_identity.flags & libc::O_ACCMODE != libc::O_RDWR
    {
        return Err(NamespaceError::Rejected(
            "original apexd source or actual opened block descriptor differs",
        ));
    }
    Ok(())
}

fn support_probe_target_identity(target: &File) -> Result<FileIdentity> {
    let identity = FileIdentity::observe(target)?;
    if !target.metadata()?.file_type().is_block_device()
        || identity.flags & libc::O_ACCMODE != libc::O_RDWR
    {
        return Err(NamespaceError::Rejected(
            "original apexd support probe target is not its real opened read-write block descriptor",
        ));
    }
    Ok(identity)
}

struct ConfigurationCustody {
    notification: wire::Notification,
    generation: ActualApexdGeneration,
    default: DefaultMountBinding,
    deadline: Instant,
    bytes: [u8; CONFIG_BYTES],
    source: File,
    source_identity: FileIdentity,
    source_fd: i32,
    target: File,
    target_identity: FileIdentity,
    target_fd: i32,
}

/// Actual original request bytes and duplicated original open-file descriptions.
/// The target block FD is private observation custody; it is not exported and
/// does not by itself authorize any device operation.
pub(crate) struct ObservedApexdLoopConfigure {
    custody: Rc<ConfigurationCustody>,
}
impl ObservedApexdLoopConfigure {
    pub(crate) fn bytes(&self) -> &[u8; CONFIG_BYTES] {
        &self.custody.bytes
    }
    pub(crate) fn source(&self) -> &File {
        &self.custody.source
    }
    pub(crate) fn revalidate(&self, request: &OriginalApexdIoctlRequest<'_>) -> Result<()> {
        request.revalidate()?;
        request.require_configuration(&self.custody)?;
        request.revalidate()
    }
}

struct SupportProbeCustody {
    notification: wire::Notification,
    generation: ActualApexdGeneration,
    default: DefaultMountBinding,
    deadline: Instant,
    body: SupportProbeBody,
    target: File,
    target_identity: FileIdentity,
    target_fd: i32,
}

/// Original pending support-probe custody only. This type has no source FD,
/// target accessor, issuer, native ioctl or notification-response operation.
/// Keeping this observation after its request ends cannot extend that request
/// or authorize a later configuration. A private target provider is still absent.
pub(crate) struct ObservedApexdLoopSupportProbe {
    custody: Rc<SupportProbeCustody>,
}
impl ObservedApexdLoopSupportProbe {
    pub(crate) fn bytes(&self) -> &[u8; CONFIG_BYTES] {
        &self.custody.body.bytes
    }

    pub(crate) fn revalidate(&self, request: &OriginalApexdIoctlRequest<'_>) -> Result<()> {
        request.revalidate()?;
        request.require_support_probe(&self.custody)?;
        request.revalidate()
    }
}

struct BoundCustody {
    observation: Rc<ConfigurationCustody>,
    matched: Rc<MatchedDecompressedCapex>,
    index: usize,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum JournalPhase {
    Fresh,
    Entered,
    Complete,
}

fn begin_support_probe_observation(phase: &Cell<JournalPhase>) -> Result<()> {
    if phase.get() != JournalPhase::Fresh {
        return Err(NamespaceError::Rejected(
            "original apexd support probe observation replay",
        ));
    }
    // The same journal gates normal configure. A failed body/FD observation
    // remains Entered and cannot be retried as either request class.
    phase.set(JournalPhase::Entered);
    Ok(())
}

/// Private trait erases only the tree-borrow lifetime. Its sole implementation
/// is the original request; external values cannot construct a bound request.
trait BoundOwner {
    fn require_bound(&self, bound: &Rc<BoundCustody>) -> Result<()>;
}

pub(crate) struct BoundApexdCapexRequest<'request> {
    request: &'request dyn BoundOwner,
    custody: Rc<BoundCustody>,
}
impl BoundApexdCapexRequest<'_> {
    pub(crate) fn revalidate(&self) -> Result<()> {
        self.request.require_bound(&self.custody)
    }

    /// Match this exact original matched journal, not a copied numeric stamp.
    /// All observations occur outside any inner ledger or pending-slot borrow.
    pub(crate) fn require_request(&self, request: &OriginalApexdIoctlRequest<'_>) -> Result<()> {
        self.revalidate()?;
        request.require_bound(&self.custody)?;
        self.revalidate()
    }
}

/// Immutable equality stamp for custody registered by this original request.
/// It contains no public fields, constructor or independent operation authority.
/// A holder must still validate the original request and its same ledger borrow.
#[derive(Clone, Copy, Eq, PartialEq)]
pub(crate) struct ActualApexdRequestBinding {
    notification: wire::Notification,
    generation: ActualApexdGeneration,
    default: DefaultMountBinding,
    deadline: Instant,
}

/// This type is the dispatch borrow, not a second actor identity. In particular
/// the same original ApexLoops RefMut cannot be replaced by a later fresh borrow.
/// A future mutation lane must transfer this original ledger explicitly.
pub(crate) struct OriginalApexdIoctlRequest<'task> {
    transport: RefMut<'task, Transport>,
    child: &'task TreeChild,
    mount_owner: OwnedNamespaceWitness<'task>,
    original_bases: &'task crate::production_mounts::PreparedMounts,
    mount_actors: crate::production_runtime_assets::NativeMountActorGuard<'task>,
    task: ActualApexdTask,
    mac: MacApexdTaskWitness,
    owner: RuntimeMacOwner,
    notification: wire::Notification,
    generation: ActualApexdGeneration,
    default: DefaultMountBinding,
    deadline: Instant,
    memory: File,
    memory_node: Node,
    observation_phase: Cell<JournalPhase>,
    observation: RefCell<Option<Rc<ConfigurationCustody>>>,
    support_probe: RefCell<Option<Rc<SupportProbeCustody>>>,
    binding_phase: Cell<JournalPhase>,
    bound: RefCell<Option<Rc<BoundCustody>>>,
}

impl InheritedNotifications {
    /// Consume only an already received device request from this same owner.
    /// This does not poll again or reset the existing successor deadline.
    pub(in super::super) fn original_apexd_ioctl<'task>(
        &'task self,
        child: &'task TreeChild,
        mount_owner: OwnedNamespaceWitness<'task>,
        original_bases: &'task crate::production_mounts::PreparedMounts,
        mount_actors: crate::production_runtime_assets::NativeMountActorGuard<'task>,
        maximum_end: Instant,
    ) -> Result<OriginalApexdIoctlRequest<'task>> {
        self.revalidate(child)?;
        mount_actors.require_exclusive().map_err(error)?;
        mount_owner.revalidate()?;
        mount_actors.revalidate(&mount_owner).map_err(error)?;
        let mut transport = self
            .transport
            .try_borrow_mut()
            .map_err(|_| NamespaceError::Rejected("original apexd listener is already borrowed"))?;
        if transport.failed || transport.receiving.is_some() || transport.original_trace.is_some() {
            return Err(NamespaceError::Rejected(
                "original apexd request lacks completed native handoff",
            ));
        }
        let notification = transport.pending.ok_or(NamespaceError::Rejected(
            "no original apexd pending request",
        ))?;
        let deadline = transport
            .successor_deadline
            .ok_or(NamespaceError::Rejected(
                "original apexd pending deadline is absent",
            ))?;
        if deadline > maximum_end {
            return Err(NamespaceError::Rejected(
                "original apexd request exceeds prepared execution deadline",
            ));
        }
        before(deadline)?;
        transport.valid(&notification)?;
        // From this point, every failed construction preserves this exact
        // pending ID in a failed lane for the owning tree's normal retirement.
        transport.failed = true;
        let successors = transport
            .successors
            .as_ref()
            .ok_or(NamespaceError::Rejected(
                "original apexd successor owner absent",
            ))?;
        successors.matches_listener(
            self.identity,
            self.nonce,
            self.pidfd,
            self.proc,
            transport.node,
        )?;
        let task = successors.issue_apexd_task(
            &transport.file,
            notification,
            deadline,
            &mount_owner,
            &mount_actors,
        )?;
        let owner = task.original_context()?;
        task.require_owner(&owner)?;
        let mac = MacApexdTaskWitness::observe(&owner, &task).map_err(error)?;
        let generation = task.generation()?;
        let default = task.default_binding()?;
        let memory = open_proc_at(task.proc_directory(), "mem", libc::O_RDONLY)?;
        let memory_node = Node::of(&memory)?;
        transport.valid(&notification)?;
        mount_actors.revalidate(&mount_owner).map_err(error)?;
        before(deadline)?;
        transport.failed = false;
        let value = OriginalApexdIoctlRequest {
            transport,
            child,
            mount_owner,
            original_bases,
            mount_actors,
            task,
            mac,
            owner,
            notification,
            generation,
            default,
            deadline,
            memory,
            memory_node,
            observation_phase: Cell::new(JournalPhase::Fresh),
            observation: RefCell::new(None),
            support_probe: RefCell::new(None),
            binding_phase: Cell::new(JournalPhase::Fresh),
            bound: RefCell::new(None),
        };
        value.revalidate()?;
        Ok(value)
    }
}

impl<'task> OriginalApexdIoctlRequest<'task> {
    /// Call outside the inner ledger borrow; revalidation uses the already held
    /// exclusive ledger and never replaces or reacquires its outer RefMut.
    pub(crate) fn custody_binding(&self) -> Result<ActualApexdRequestBinding> {
        self.revalidate()?;
        let binding = ActualApexdRequestBinding {
            notification: self.notification,
            generation: self.generation,
            default: self.default,
            deadline: self.deadline,
        };
        self.revalidate()?;
        Ok(binding)
    }

    pub(crate) fn notification(&self) -> wire::Notification {
        self.notification
    }
    pub(crate) fn deadline(&self) -> Instant {
        self.deadline
    }
    pub(crate) fn default_binding(&self) -> DefaultMountBinding {
        self.default
    }

    fn revalidate_base(&self) -> Result<()> {
        before(self.deadline)?;
        if self.transport.failed
            || self.transport.receiving.is_some()
            || self.transport.original_trace.is_some()
            || self.transport.pending != Some(self.notification)
            || self.transport.successor_deadline != Some(self.deadline)
            || Node::of(&self.memory)? != self.memory_node
            || filesystem_kind(&self.memory)? != PROC_MAGIC
        {
            return Err(NamespaceError::Rejected(
                "original apexd dispatch or memory custody changed",
            ));
        }
        self.transport.valid(&self.notification)?;
        self.transport
            .successors
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?
            .idle()?;
        self.child.verify()?;
        self.mount_owner.revalidate()?;
        self.mount_actors.require_exclusive().map_err(error)?;
        self.mount_actors
            .revalidate(&self.mount_owner)
            .map_err(error)?;
        self.task
            .require_request(&self.notification, self.deadline)?;
        self.task.require_owner(&self.owner)?;
        if self.task.generation()? != self.generation
            || self.task.default_binding()? != self.default
        {
            return Err(NamespaceError::Rejected(
                "original apexd task/default generation changed",
            ));
        }
        // Kept outside the kernel-only task method: this observer calls back
        // into that kernel-only method, and never recursively into itself.
        self.mac.revalidate(&self.task).map_err(error)?;
        self.transport.valid(&self.notification)?;
        self.mount_actors
            .revalidate(&self.mount_owner)
            .map_err(error)?;
        before(self.deadline)
    }

    pub(crate) fn revalidate(&self) -> Result<()> {
        if self.observation_phase.get() == JournalPhase::Entered
            || self.binding_phase.get() == JournalPhase::Entered
        {
            return Err(NamespaceError::Rejected(
                "original apexd observation or role binding is incomplete",
            ));
        }
        self.revalidate_base()
    }

    pub(crate) fn require_owner(&self, owner: &RuntimeMacOwner) -> Result<()> {
        self.revalidate()?;
        self.task.require_owner(owner)?;
        let (mac, selection) = owner.objects().map_err(error)?;
        self.owner.require_pair(mac, selection).map_err(error)?;
        self.revalidate()
    }

    /// Borrow the already held exclusive ledger, never obtain a new one.
    pub(crate) fn actor_ledger(
        &self,
    ) -> Result<&crate::production_runtime_assets::NativeMountActorGuard<'task>> {
        self.revalidate()?;
        self.mount_actors.require_exclusive().map_err(error)?;
        Ok(&self.mount_actors)
    }

    pub(crate) fn require_actor_ledger(
        &self,
        ledger: &crate::production_runtime_assets::NativeMountActorGuard<'task>,
    ) -> Result<()> {
        self.revalidate()?;
        if !std::ptr::eq(&self.mount_actors, ledger) {
            return Err(NamespaceError::Rejected(
                "apexd transaction replaced its original ledger borrow",
            ));
        }
        ledger.require_exclusive().map_err(error)?;
        ledger.revalidate(&self.mount_owner).map_err(error)?;
        self.revalidate()
    }

    fn configuration_body(&self) -> Result<[u8; CONFIG_BYTES]> {
        let (_, address) = configure_address(&self.notification)?;
        read_configuration(&self.memory, address, self.deadline)
    }

    fn check_configuration(&self, c: &ConfigurationCustody) -> Result<()> {
        self.revalidate_base()?;
        if c.notification != self.notification
            || c.generation != self.generation
            || c.default != self.default
            || c.deadline != self.deadline
            || FileIdentity::observe(&c.source)? != c.source_identity
            || FileIdentity::observe(&c.target)? != c.target_identity
            || self.configuration_body()? != c.bytes
        {
            return Err(NamespaceError::Rejected(
                "original apexd configure observation changed",
            ));
        }
        let (target_fd, _) = configure_address(&self.notification)?;
        if c.target_fd != target_fd || c.source_fd != source_number(&c.bytes)? {
            return Err(NamespaceError::Rejected(
                "original apexd descriptor registers changed",
            ));
        }
        let source = copy_task_fd(&self.task, c.source_fd, self.deadline)?;
        let target = copy_task_fd(&self.task, c.target_fd, self.deadline)?;
        same_open_file(&c.source, &source)?;
        same_open_file(&c.target, &target)?;
        if FileIdentity::observe(&source)? != c.source_identity
            || FileIdentity::observe(&target)? != c.target_identity
        {
            return Err(NamespaceError::Rejected(
                "original apexd copied descriptor identity changed",
            ));
        }
        require_input_shapes(&c.source, &c.target)?;
        self.transport.valid(&self.notification)?;
        if self.configuration_body()? != c.bytes
            || FileIdentity::observe(&c.source)? != c.source_identity
            || FileIdentity::observe(&c.target)? != c.target_identity
        {
            return Err(NamespaceError::Rejected(
                "original apexd configure final bookend changed",
            ));
        }
        self.revalidate_base()
    }

    fn require_configuration(&self, c: &Rc<ConfigurationCustody>) -> Result<()> {
        let slot = self
            .observation
            .try_borrow()
            .map_err(|_| NamespaceError::Rejected("original apexd observation journal borrowed"))?;
        if self.observation_phase.get() != JournalPhase::Complete
            || !slot
                .as_ref()
                .is_some_and(|original| Rc::ptr_eq(original, c))
        {
            return Err(NamespaceError::Rejected(
                "configuration belongs to another original request",
            ));
        }
        self.check_configuration(c)
    }

    fn check_support_probe(&self, custody: &SupportProbeCustody) -> Result<()> {
        self.revalidate_base()?;
        if custody.notification != self.notification
            || custody.generation != self.generation
            || custody.default != self.default
            || custody.deadline != self.deadline
            || support_probe_target_identity(&custody.target)? != custody.target_identity
            || self.configuration_body()? != custody.body.bytes
        {
            return Err(NamespaceError::Rejected(
                "original apexd support probe observation changed",
            ));
        }
        let (target_fd, _) = configure_address(&self.notification)?;
        if target_fd != custody.target_fd {
            return Err(NamespaceError::Rejected(
                "original apexd support probe target register changed",
            ));
        }
        // Only the original ioctl target is duplicated. In particular the
        // body's -1 is never passed to PIDFD_GETFD or interpreted as errno.
        let target = copy_task_fd(&self.task, custody.target_fd, self.deadline)?;
        same_open_file(&custody.target, &target)?;
        if support_probe_target_identity(&target)? != custody.target_identity {
            return Err(NamespaceError::Rejected(
                "original apexd support probe copied target identity changed",
            ));
        }
        self.transport.valid(&self.notification)?;
        if self.configuration_body()? != custody.body.bytes
            || support_probe_target_identity(&custody.target)? != custody.target_identity
        {
            return Err(NamespaceError::Rejected(
                "original apexd support probe final bookend changed",
            ));
        }
        self.revalidate_base()
    }

    fn require_support_probe(&self, custody: &Rc<SupportProbeCustody>) -> Result<()> {
        let slot = self
            .support_probe
            .try_borrow()
            .map_err(|_| NamespaceError::Rejected("original apexd support probe journal borrowed"))?;
        if self.observation_phase.get() != JournalPhase::Complete
            || self.binding_phase.get() != JournalPhase::Fresh
            || !slot
                .as_ref()
                .is_some_and(|original| Rc::ptr_eq(original, custody))
        {
            return Err(NamespaceError::Rejected(
                "support probe belongs to another original request",
            ));
        }
        self.check_support_probe(custody)
    }

    /// Observe the exact support probe from this already received request.
    /// This performs no ioctl or reply, never opens a host loop node, and does
    /// not make the currently unconstructible original-target issuer available.
    pub(crate) fn original_loop_support_probe(&self) -> Result<ObservedApexdLoopSupportProbe> {
        self.revalidate()?;
        begin_support_probe_observation(&self.observation_phase)?;
        let (target_fd, _) = configure_address(&self.notification)?;
        let body = SupportProbeBody::parse(self.configuration_body()?)?;
        let target = copy_task_fd(&self.task, target_fd, self.deadline)?;
        let custody = Rc::new(SupportProbeCustody {
            notification: self.notification,
            generation: self.generation,
            default: self.default,
            deadline: self.deadline,
            body,
            target_identity: support_probe_target_identity(&target)?,
            target,
            target_fd,
        });
        // Retain the real target OFD before the remaining fallible bookends.
        *self.support_probe.try_borrow_mut().map_err(|_| {
            NamespaceError::Rejected("original apexd support probe journal borrowed")
        })? = Some(Rc::clone(&custody));
        self.check_support_probe(&custody)?;
        self.observation_phase.set(JournalPhase::Complete);
        Ok(ObservedApexdLoopSupportProbe { custody })
    }

    pub(crate) fn original_loop_configure(&self) -> Result<ObservedApexdLoopConfigure> {
        self.revalidate()?;
        if self.observation_phase.get() != JournalPhase::Fresh {
            return Err(NamespaceError::Rejected(
                "original apexd configure observation replay",
            ));
        }
        self.observation_phase.set(JournalPhase::Entered);
        let (target_fd, _) = configure_address(&self.notification)?;
        let bytes = self.configuration_body()?;
        let source_fd = source_number(&bytes)?;
        let source = copy_task_fd(&self.task, source_fd, self.deadline)?;
        let target = copy_task_fd(&self.task, target_fd, self.deadline)?;
        require_input_shapes(&source, &target)?;
        let custody = Rc::new(ConfigurationCustody {
            notification: self.notification,
            generation: self.generation,
            default: self.default,
            deadline: self.deadline,
            bytes,
            source_identity: FileIdentity::observe(&source)?,
            target_identity: FileIdentity::observe(&target)?,
            source,
            target,
            source_fd,
            target_fd,
        });
        // Custody is retained before any remaining live read can fail.
        *self.observation.try_borrow_mut().map_err(|_| {
            NamespaceError::Rejected("original apexd observation journal borrowed")
        })? = Some(Rc::clone(&custody));
        self.check_configuration(&custody)?;
        self.observation_phase.set(JournalPhase::Complete);
        Ok(ObservedApexdLoopConfigure { custody })
    }

    /// Obtain the source only from this request's original admitted system,
    /// actual default root and actual duplicated readonly backing descriptor.
    /// No caller path/index or init execution witness enters this route.
    pub(crate) fn match_original_compressed(
        &self,
        observed: &ObservedApexdLoopConfigure,
    ) -> Result<Rc<MatchedDecompressedCapex>> {
        self.revalidate()?;
        observed.revalidate(self)?;
        if self.binding_phase.get() != JournalPhase::Fresh {
            return Err(NamespaceError::Rejected(
                "original apexd CAPEX binding has already started",
            ));
        }
        let bytes = observed.custody.source_identity.bytes;
        let index = compressed_role_for_length(bytes)?;
        let container =
            self.task
                .original_compressed_apex(self.original_bases, &self.mount_owner, index)?;
        observed.revalidate(self)?;
        let requested = observed.source().try_clone()?;
        same_open_file(observed.source(), &requested)?;
        before(self.deadline)?;
        let matched = Rc::new(
            MatchedDecompressedCapex::copy_requested(container, requested, index, self.deadline)
                .map_err(error)?,
        );
        matched
            .require_requested(observed.source())
            .map_err(error)?;
        observed.revalidate(self)?;
        self.revalidate()?;
        before(self.deadline)?;
        Ok(matched)
    }

    /// The registered CAPEX lane receives this request's own original pair.
    /// A caller cannot substitute a role, source, pool or separately acquired
    /// owner. A successful return records custody only, never a syscall reply.
    pub(crate) fn prepare_registered_capex(
        &self,
    ) -> Result<crate::production_capex_loop_request::PreparedApexdCapexLoop<'_>> {
        self.revalidate()?;
        let prepared =
            crate::production_capex_loop_request::PreparedApexdCapexLoop::prepare_registered(
                self,
                &self.owner,
            )
            .map_err(error)?;
        self.revalidate()?;
        Ok(prepared)
    }

    pub(crate) fn bind_matched_capex<'request>(
        &'request self,
        observed: &ObservedApexdLoopConfigure,
        matched: &Rc<MatchedDecompressedCapex>,
    ) -> Result<BoundApexdCapexRequest<'request>> {
        self.revalidate()?;
        observed.revalidate(self)?;
        if self.binding_phase.get() != JournalPhase::Fresh {
            return Err(NamespaceError::Rejected(
                "original apexd CAPEX role binding replay",
            ));
        }
        self.binding_phase.set(JournalPhase::Entered);
        matched
            .require_requested(observed.source())
            .map_err(error)?;
        let index = matched.index();
        let custody = Rc::new(BoundCustody {
            observation: Rc::clone(&observed.custody),
            matched: Rc::clone(matched),
            index,
        });
        *self
            .bound
            .try_borrow_mut()
            .map_err(|_| NamespaceError::Rejected("original apexd matched journal borrowed"))? =
            Some(Rc::clone(&custody));
        self.require_configuration(&custody.observation)?;
        custody
            .matched
            .require_requested(&custody.observation.source)
            .map_err(error)?;
        if custody.matched.index() != custody.index {
            return Err(NamespaceError::Rejected(
                "original matched CAPEX role changed",
            ));
        }
        self.revalidate_base()?;
        self.binding_phase.set(JournalPhase::Complete);
        Ok(BoundApexdCapexRequest {
            request: self,
            custody,
        })
    }
}

impl BoundOwner for OriginalApexdIoctlRequest<'_> {
    fn require_bound(&self, bound: &Rc<BoundCustody>) -> Result<()> {
        self.revalidate()?;
        let slot = self
            .bound
            .try_borrow()
            .map_err(|_| NamespaceError::Rejected("original apexd matched journal borrowed"))?;
        if self.binding_phase.get() != JournalPhase::Complete
            || !slot
                .as_ref()
                .is_some_and(|original| Rc::ptr_eq(original, bound))
        {
            return Err(NamespaceError::Rejected(
                "CAPEX binding belongs to another original request",
            ));
        }
        self.require_configuration(&bound.observation)?;
        bound
            .matched
            .require_requested(&bound.observation.source)
            .map_err(error)?;
        if bound.matched.index() != bound.index {
            return Err(NamespaceError::Rejected(
                "actual matched CAPEX index changed",
            ));
        }
        self.revalidate()
    }
}

impl Drop for OriginalApexdIoctlRequest<'_> {
    fn drop(&mut self) {
        // No reply path is provided by this observation-only increment. Keep
        // the exact pending ID/deadline for the original tree's retirement.
        // The dispatcher cannot silently abandon this request and receive anew.
        self.transport.failed = true;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn notification() -> wire::Notification {
        wire::Notification {
            id: 71,
            pid: 42,
            flags: 0,
            data: wire::Data {
                nr: libc::SYS_ioctl as i32,
                arch: 0xc000_003e,
                instruction_pointer: 0x1000,
                args: [7, CONFIGURE, 128, 0, 0, 0],
            },
        }
    }

    fn support_probe_body() -> [u8; CONFIG_BYTES] {
        let mut body = [0_u8; CONFIG_BYTES];
        body[..4].copy_from_slice(&u32::MAX.to_le_bytes());
        body
    }

    #[test]
    fn actual_apexd_support_probe_accepts_only_all_exact_304_bytes() {
        let original = support_probe_body();
        assert_eq!(SupportProbeBody::parse(original).unwrap().bytes, original);
        // Every bit belongs to the original ABI, including all reserved bytes.
        for offset in 0..CONFIG_BYTES {
            for bit in 0..8 {
                let mut changed = original;
                changed[offset] ^= 1_u8 << bit;
                assert!(SupportProbeBody::parse(changed).is_err(), "{offset}:{bit}");
            }
        }
    }

    #[test]
    fn actual_apexd_support_probe_never_becomes_a_normal_source_descriptor() {
        let probe = support_probe_body();
        assert!(SupportProbeBody::parse(probe).is_ok());
        assert!(source_number(&probe).is_err());
        for number in [0, 1, 19, i32::MAX as u32] {
            let mut normal = [0_u8; CONFIG_BYTES];
            normal[..4].copy_from_slice(&number.to_le_bytes());
            assert_eq!(source_number(&normal).unwrap(), number as i32);
            assert!(SupportProbeBody::parse(normal).is_err());
        }
        for number in [i32::MAX as u32 + 1, u32::MAX - 1] {
            let mut invalid = [0_u8; CONFIG_BYTES];
            invalid[..4].copy_from_slice(&number.to_le_bytes());
            assert!(source_number(&invalid).is_err());
            assert!(SupportProbeBody::parse(invalid).is_err());
        }
    }

    #[test]
    fn actual_apexd_support_probe_keeps_original_exact_notification_abi() {
        let original = notification();
        assert_eq!(configure_address(&original).unwrap(), (7, 128));
        let changes: [fn(&mut wire::Notification); 11] = [
            |request| request.id = 0,
            |request| request.pid = 1,
            |request| request.flags = 1,
            |request| request.data.arch = 0x4000_0003,
            |request| request.data.nr = libc::SYS_mount as i32,
            |request| request.data.instruction_pointer = 0,
            |request| request.data.args[0] = i32::MAX as u64 + 1,
            |request| request.data.args[1] = 0x4c05,
            |request| request.data.args[2] = 0,
            |request| request.data.args[2] = i64::MAX as u64,
            |request| request.data.args[2] = u64::MAX,
        ];
        for change in changes {
            let mut invalid = original;
            change(&mut invalid);
            assert!(configure_address(&invalid).is_err());
        }
        // These are ABI controls only. A nonzero ID still needs the unchanged
        // actual pending-ID, PIDFD_THREAD, original owner and deadline checks.
    }

    #[test]
    fn actual_apexd_support_probe_rejects_changed_short_or_expired_memory() {
        let memory = tempfile::tempfile().unwrap();
        let original = support_probe_body();
        memory.write_all_at(&original, 128).unwrap();
        let deadline = Instant::now() + Duration::from_secs(2);
        let observed = SupportProbeBody::parse(read_configuration(&memory, 128, deadline).unwrap())
            .unwrap();
        assert_eq!(observed.bytes, original);
        memory.write_all_at(&[1], 128 + 12).unwrap();
        let changed = read_configuration(&memory, 128, deadline).unwrap();
        assert_ne!(changed, observed.bytes);
        assert!(SupportProbeBody::parse(changed).is_err());
        memory.write_all_at(&original, 128).unwrap();
        assert!(read_configuration(&memory, 128, Instant::now()).is_err());
        memory.set_len(128 + CONFIG_BYTES as u64 - 1).unwrap();
        assert!(read_configuration(&memory, 128, deadline).is_err());
    }

    #[test]
    fn actual_apexd_support_probe_journal_cannot_replay_or_reset_a_failed_observation() {
        let phase = Cell::new(JournalPhase::Fresh);
        begin_support_probe_observation(&phase).unwrap();
        assert_eq!(phase.get(), JournalPhase::Entered);
        assert!(SupportProbeBody::parse([0_u8; CONFIG_BYTES]).is_err());
        assert!(begin_support_probe_observation(&phase).is_err());
        assert_eq!(phase.get(), JournalPhase::Entered);
        // Normal configuration uses this same journal. Neither a completed
        // normal observation nor a completed probe can be observed again.
        phase.set(JournalPhase::Complete);
        assert!(begin_support_probe_observation(&phase).is_err());
        assert_eq!(phase.get(), JournalPhase::Complete);
    }

    #[test]
    fn actual_apexd_support_probe_rejects_reopened_ofds_and_nonblock_targets() {
        use std::fs::OpenOptions;
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("probe-identity-only");
        let original = OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .open(&path)
            .unwrap();
        let copy = original.try_clone().unwrap();
        same_open_file(&original, &copy).unwrap();
        let reopened = OpenOptions::new().read(true).write(true).open(&path).unwrap();
        assert_eq!(Node::of(&original).unwrap(), Node::of(&reopened).unwrap());
        assert!(same_open_file(&original, &reopened).is_err());
        for target in [&original, &copy, &reopened] {
            assert!(support_probe_target_identity(target).is_err());
        }
        let readonly = OpenOptions::new().read(true).open(&path).unwrap();
        assert!(support_probe_target_identity(&readonly).is_err());
        let path_only = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_PATH)
            .open(&path)
            .unwrap();
        assert!(FileIdentity::observe(&path_only).is_err());
        assert!(support_probe_target_identity(&path_only).is_err());
        // No block node, loop control, ioctl or privileged fixture is opened.
    }

    #[test]
    fn actual_apexd_requested_size_selects_only_fixed_compressed_candidates() {
        let rows = crate::production_execution_profile::apex_inputs::original_inputs().unwrap();
        let mut selected = 0;
        for (index, row) in rows.iter().enumerate() {
            if row.input.container_file.ends_with(".capex") {
                assert_eq!(
                    compressed_role_for_length(row.input.original_apex_bytes).unwrap(),
                    index
                );
                assert!(compressed_role_for_length(row.input.original_apex_bytes - 1).is_err());
                assert!(compressed_role_for_length(row.input.original_apex_bytes + 1).is_err());
                selected += 1;
            }
        }
        assert_eq!(selected, 28);
        assert!(compressed_role_for_length(0).is_err());
        assert!(compressed_role_for_length(u64::MAX).is_err());
    }

    #[test]
    fn actual_apexd_configure_observation_rejects_other_calls_and_unbounded_memory() {
        let good = notification();
        assert_eq!(configure_address(&good).unwrap(), (7, 128));
        for index in [0, 1, 2] {
            let mut bad = good;
            bad.data.args[index] = u64::MAX;
            assert!(configure_address(&bad).is_err());
        }
        let mut bad = good;
        bad.data.args[1] = 0x4c05;
        assert!(configure_address(&bad).is_err());
        bad = good;
        bad.data.args[2] = 0;
        assert!(configure_address(&bad).is_err());
        bad = good;
        bad.data.arch = 0x4000_0003;
        assert!(configure_address(&bad).is_err());
        bad = good;
        bad.data.nr = libc::SYS_mount as i32;
        assert!(configure_address(&bad).is_err());
        bad = good;
        bad.flags = 1;
        assert!(configure_address(&bad).is_err());
    }

    #[test]
    fn actual_apexd_configure_bytes_keep_full_memory_and_real_probe_separate() {
        let memory = tempfile::tempfile().unwrap();
        let mut raw = [0_u8; CONFIG_BYTES];
        raw[..4].copy_from_slice(&19_u32.to_le_bytes());
        raw[4..].fill(0x65);
        memory.write_all_at(&raw, 128).unwrap();
        let end = Instant::now() + Duration::from_secs(2);
        assert_eq!(read_configuration(&memory, 128, end).unwrap(), raw);
        assert_eq!(source_number(&raw).unwrap(), 19);
        let mut probe = [0_u8; CONFIG_BYTES];
        probe[..4].copy_from_slice(&u32::MAX.to_le_bytes());
        assert!(source_number(&probe).is_err());
        memory.set_len(128 + CONFIG_BYTES as u64 - 1).unwrap();
        assert!(read_configuration(&memory, 128, end).is_err());
        assert!(read_configuration(&memory, 128, Instant::now()).is_err());
        for address in [0, i64::MAX as u64, u64::MAX] {
            assert!(read_configuration(&memory, address, end).is_err());
        }
    }

    #[test]
    fn actual_apexd_observation_requires_same_ofd_and_preserves_original_file_changes() {
        use std::fs::OpenOptions;
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("original");
        let original = OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .open(&path)
            .unwrap();
        original.write_all_at(b"actual", 0).unwrap();
        let copy = original.try_clone().unwrap();
        same_open_file(&original, &copy).unwrap();
        let reopened = OpenOptions::new()
            .read(true)
            .write(true)
            .open(&path)
            .unwrap();
        assert_eq!(Node::of(&original).unwrap(), Node::of(&reopened).unwrap());
        assert!(same_open_file(&original, &reopened).is_err());
        let before = FileIdentity::observe(&original).unwrap();
        copy.write_all_at(b"new bytes", 0).unwrap();
        assert_ne!(FileIdentity::observe(&original).unwrap(), before);
        assert!(require_input_shapes(&original, &copy).is_err());
    }
    #[test]
    fn actual_apexd_source_keeps_real_direct_and_buffered_readonly_open_modes() {
        use std::fs::OpenOptions;
        #[repr(align(4096))]
        struct Aligned([u8; 4096]);
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("original-archive-input");
        let write = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&path)
            .unwrap();
        write.write_all_at(&[0x5a_u8; 4096], 0).unwrap();
        write.sync_all().unwrap();
        drop(write);
        for flags in [0, libc::O_DIRECT] {
            let original = OpenOptions::new()
                .read(true)
                .custom_flags(flags)
                .open(&path)
                .unwrap();
            let before = readonly_source_identity(&original).unwrap();
            assert_eq!(before.flags & libc::O_DIRECT, flags);
            let mut data = Aligned([0_u8; 4096]);
            assert_eq!(original.read_at(&mut data.0, 0).unwrap(), 4096);
            assert_eq!(data.0, [0x5a_u8; 4096]);
            assert_eq!(readonly_source_identity(&original).unwrap(), before);
            let copy = original.try_clone().unwrap();
            same_open_file(&original, &copy).unwrap();
            assert_eq!(readonly_source_identity(&copy).unwrap(), before);
        }
        let writable = OpenOptions::new()
            .read(true)
            .write(true)
            .open(&path)
            .unwrap();
        assert!(readonly_source_identity(&writable).is_err());
    }
}
