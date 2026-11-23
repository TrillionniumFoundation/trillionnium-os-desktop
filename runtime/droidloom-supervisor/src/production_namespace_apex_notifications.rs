//! Listener custody acquired only from the original PID-1 pre-exec barrier.
use super::original_ptrace::{NativeSuccessors, NativeSyscallOutcome, OriginalPtrace};
use super::*;
use crate::production_apex_seccomp as wire;
use crate::production_runtime_assets::OriginalInitCleanup;
use std::cell::{RefCell, RefMut};
use std::os::unix::fs::FileExt;
use std::rc::Rc;

#[path = "production_namespace_apexd_ioctl_request.rs"]
mod apexd_ioctl;
pub(crate) use apexd_ioctl::{
    ActualApexdRequestBinding, BoundApexdCapexRequest, ObservedApexdLoopConfigure,
    OriginalApexdIoctlRequest,
};

#[path = "production_namespace_init_mount_requests.rs"]
mod initial_mount_requests;
#[path = "production_apex_notify_receive.rs"]
mod receiver;
pub(crate) use initial_mount_requests::OriginalInitTmpfsRequest;
#[path = "production_namespace_init_propagation_requests.rs"]
mod initial_propagation_requests;
pub(crate) use initial_propagation_requests::OriginalInitPropagationRequest;
#[path = "production_namespace_init_bootstrap_bind_request.rs"]
mod initial_bootstrap_bind_request;
pub(crate) use initial_bootstrap_bind_request::OriginalInitBootstrapBindRequest;
#[path = "production_namespace_init_storage_bind_requests.rs"]
mod initial_storage_bind_requests;
pub(crate) use initial_storage_bind_requests::OriginalInitStorageBindRequest;

struct Transport {
    file: File,
    node: Node,
    creator: i64,
    receiving: Option<receiver::Receiver>,
    original_trace: Option<Rc<RefCell<OriginalPtrace>>>,
    successors: Option<NativeSuccessors>,
    successor_deadline: Option<Instant>,
    pending: Option<wire::Notification>,
    failed: bool,
}

impl Transport {
    fn new(file: File) -> Result<Self> {
        let flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
        let fd_flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFD) };
        if flags < 0 || fd_flags < 0 {
            return Err(io::Error::last_os_error().into());
        }
        if filesystem_kind(&file)? != 0x0904_1934
            || flags & libc::O_ACCMODE != libc::O_RDWR
            || fd_flags & libc::FD_CLOEXEC == 0
        {
            return Err(NamespaceError::Rejected(
                "notification listener kernel descriptor shape",
            ));
        }
        // No notified syscall can run before this authenticated exec barrier.
        // This kernel ioctl probes the actual seccomp file operations, not a
        // caller's filename or an anon-inode-looking regular file.
        let absent = 0_u64;
        let check = unsafe { libc::ioctl(file.as_raw_fd(), wire::ID_VALID, &absent) };
        if check != -1 || io::Error::last_os_error().raw_os_error() != Some(libc::ENOENT) {
            return Err(NamespaceError::Rejected(
                "notification listener kernel operations differ",
            ));
        }
        let node = Node::of(&file)?;
        Ok(Self {
            file,
            node,
            creator: unsafe { libc::syscall(libc::SYS_gettid) },
            receiving: None,
            original_trace: None,
            successors: None,
            successor_deadline: None,
            pending: None,
            failed: false,
        })
    }

    fn revalidate(&self) -> Result<()> {
        if self.creator != unsafe { libc::syscall(libc::SYS_gettid) }
            || Node::of(&self.file)? != self.node
        {
            return Err(NamespaceError::Rejected(
                "notification listener original owner changed",
            ));
        }
        Ok(())
    }

    fn valid(&self, notification: &wire::Notification) -> Result<()> {
        self.revalidate()?;
        if notification.operation().is_none() {
            return Err(NamespaceError::Rejected(
                "notification operation outside fixed filter",
            ));
        }
        if unsafe { libc::ioctl(self.file.as_raw_fd(), wire::ID_VALID, &notification.id) } != 0 {
            return Err(io::Error::last_os_error().into());
        }
        Ok(())
    }

    fn receive(&mut self, end: Instant) -> Result<wire::Notification> {
        self.revalidate()?;
        if self.failed || self.pending.is_some() || self.receiving.is_some() {
            return Err(NamespaceError::Rejected(
                "notification previous request/receiver still owned",
            ));
        }
        // A deadline can expire after the kernel consumed a notification but
        // before its packet reached this owner. Do not retry on a new budget
        // and silently abandon that unknown pending request. Only retirement
        // remains available unless this exact receive completes admission.
        self.failed = true;
        self.receiving = Some(receiver::Receiver::spawn(&self.file, end)?);
        // Store actual child custody before releasing its private READY barrier.
        let result = (|| -> io::Result<wire::Notification> {
            let receiver = self.receiving.as_mut().unwrap();
            receiver.start()?;
            if let Some(trace) = self.original_trace.as_ref() {
                let mut progress = || -> io::Result<()> {
                    trace
                        .try_borrow_mut()
                        .map_err(|_| io::Error::other("original trace already borrowed"))?
                        .notification_pump()
                        .map_err(|error| io::Error::other(error.to_string()))
                };
                receiver.complete_with_progress(Some(&mut progress))
            } else {
                receiver.complete()
            }
        })();
        self.stop_receiver()?;
        let notification = result?;
        self.valid(&notification)?;
        if Instant::now() >= end {
            return Err(NamespaceError::Rejected(
                "notification pending admission exceeded its original deadline",
            ));
        }
        self.pending = Some(notification);
        self.failed = false;
        Ok(notification)
    }

    fn original_mount_barrier(
        &self,
        child: &TreeChild,
        notification: &wire::Notification,
    ) -> Result<()> {
        if self.failed || self.receiving.is_some() || self.pending.as_ref() != Some(notification) {
            return Err(NamespaceError::Rejected(
                "original mount receiver/response ownership changed",
            ));
        }
        self.valid(notification)?;
        let trace = self
            .original_trace
            .as_ref()
            .ok_or(NamespaceError::Rejected(
                "original mount lost its authenticated entry observer",
            ))?;
        trace
            .try_borrow()
            .map_err(|_| NamespaceError::Rejected("original mount trace already borrowed"))?
            .original_mount_barrier(child, self.node, notification)?;
        self.valid(notification)
    }

    fn stop_receiver(&mut self) -> Result<()> {
        self.revalidate()?;
        if let Some(receiver) = self.receiving.as_mut() {
            receiver.retire()?;
        }
        self.receiving.take();
        Ok(())
    }

    fn reject(&mut self, errno: i32) -> Result<()> {
        if self.failed {
            return Err(NamespaceError::Rejected(
                "notification transport requires original tree retirement",
            ));
        }
        if !(1..=4095).contains(&errno) {
            return Err(NamespaceError::Rejected(
                "notification error must be a real positive errno",
            ));
        }
        let notification = self
            .pending
            .as_ref()
            .ok_or(NamespaceError::Rejected("no original pending notification"))?;
        self.valid(notification)?;
        let response = wire::Response {
            id: notification.id,
            value: 0,
            error: -errno,
            flags: 0,
        };
        self.failed = true;
        if unsafe { libc::ioctl(self.file.as_raw_fd(), wire::SEND, &response) } != 0 {
            return Err(io::Error::last_os_error().into());
        }
        self.pending.take();
        self.failed = false;
        Ok(())
    }

    fn retire_after_tree(&mut self) -> Result<()> {
        self.stop_receiver()?;
        let end = Instant::now() + Duration::from_secs(2);
        loop {
            self.revalidate()?;
            let left = end.saturating_duration_since(Instant::now());
            if left.is_zero() {
                return Err(NamespaceError::RetirementUnproven);
            }
            let mut p = libc::pollfd {
                fd: self.file.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            let count = unsafe { libc::poll(&mut p, 1, left.as_millis().clamp(1, 50) as i32) };
            if count < 0 {
                let error = io::Error::last_os_error();
                if error.kind() == io::ErrorKind::Interrupted {
                    continue;
                }
                return Err(error.into());
            }
            if p.revents & libc::POLLNVAL != 0 {
                return Err(NamespaceError::RetirementUnproven);
            }
            // HUP means this real filter has no task users left. Closing its
            // fd alone would only turn blocked operations into ENOSYS.
            if p.revents & libc::POLLHUP != 0 {
                self.pending.take();
                return Ok(());
            }
        }
    }
}

/// A pending non-native call remains owned by the same listener and original
/// deadline. Its own fixed operation handler must consume it; this enum never
/// turns it into a success or an unlimited wait.
pub(crate) enum InheritedNativePoll {
    Idle,
    Completed(NativeSyscallOutcome),
    PendingOther(wire::Operation),
}

pub(super) struct InheritedNotifications {
    transport: RefCell<Transport>,
    identity: ProcessIdentity,
    nonce: [u8; 16],
    pidfd: Node,
    proc: Node,
}

impl InheritedNotifications {
    pub(super) fn receive_from_child(child: &TreeChild) -> Result<Self> {
        child.verify()?;
        wait_readable(&child.control, &child.pidfd)?;
        let (packet, credentials, file) =
            receive_child_descriptor_record(child.control.as_raw_fd(), Phase::ApexNotifyReady)?;
        if !packet.matches(child.nonce, 1)
            || credentials.pid != child.identity.pid as i32
            || credentials.uid != child.uids.start
            || credentials.gid != child.gids.start
        {
            return Err(NamespaceError::Rejected(
                "notification pre-exec original child peer/nonce differs",
            ));
        }
        if packet.phase == Phase::Failed as u32 && packet.errno > 0 {
            return Err(io::Error::from_raw_os_error(packet.errno).into());
        }
        let transport =
            Transport::new(file.ok_or(NamespaceError::Rejected("notification listener absent"))?)?;
        let value = Self {
            transport: RefCell::new(transport),
            identity: child.identity,
            nonce: child.nonce,
            pidfd: descriptor_node(child.pidfd.as_fd())?,
            proc: child.proc_node,
        };
        value.revalidate(child)?;
        Ok(value)
    }

    fn revalidate(&self, child: &TreeChild) -> Result<()> {
        child.verify()?;
        if self.identity != child.identity
            || self.nonce != child.nonce
            || self.proc != child.proc_node
            || self.pidfd != descriptor_node(child.pidfd.as_fd())?
        {
            return Err(NamespaceError::Rejected(
                "notification listener belongs to another original tree",
            ));
        }
        self.transport
            .try_borrow()
            .map_err(|_| NamespaceError::Rejected("notification request already borrowed"))?
            .revalidate()
    }

    pub(super) fn bind_original_trace(
        &self,
        child: &TreeChild,
        trace: Rc<RefCell<OriginalPtrace>>,
    ) -> Result<()> {
        self.revalidate(child)?;
        let mut transport = self
            .transport
            .try_borrow_mut()
            .map_err(|_| NamespaceError::Rejected("notification request already borrowed"))?;
        if transport.original_trace.is_some()
            || transport.failed
            || transport.receiving.is_some()
            || transport.pending.is_some()
        {
            return Err(NamespaceError::Rejected(
                "original trace binding must precede every receive",
            ));
        }
        {
            let mut original = trace
                .try_borrow_mut()
                .map_err(|_| NamespaceError::Rejected("original trace already borrowed"))?;
            original.matches_original(child)?;
            original.bind_listener(transport.node)?;
            original.matches_listener(
                self.identity,
                self.nonce,
                self.pidfd,
                self.proc,
                transport.node,
            )?;
        }
        // This is the same Rc already stored in the original tree. It is not
        // an independently reconstructed tracer or a numeric PID constructor.
        transport.original_trace = Some(trace);
        transport.revalidate()
    }

    pub(super) fn handoff_successors(&self, child: &TreeChild) -> Result<()> {
        self.revalidate(child)?;
        let mut transport = self
            .transport
            .try_borrow_mut()
            .map_err(|_| NamespaceError::Rejected("notification request already borrowed"))?;
        if transport.successors.is_some()
            || transport.successor_deadline.is_some()
            || transport.failed
            || transport.pending.is_some()
            || transport.receiving.is_some()
        {
            return Err(NamespaceError::Rejected(
                "native successor handoff phase or replay",
            ));
        }
        let trace = transport
            .original_trace
            .as_ref()
            .ok_or(NamespaceError::Rejected(
                "native successor handoff has no original trace",
            ))?
            .clone();
        let owner = trace
            .try_borrow_mut()
            .map_err(|_| NamespaceError::Rejected("original trace already borrowed"))?
            .issue_successors(child)?;
        // Keep this exact owner before any later request can attach a task.
        transport.successors = Some(owner);
        transport.successors.as_ref().unwrap().matches_listener(
            self.identity,
            self.nonce,
            self.pidfd,
            self.proc,
            transport.node,
        )?;
        // The completed initial observer and its deadline remain in the tree.
        // Later requests have their own finite deadlines; they do not extend
        // the original boot attempt or run its detached progress callback.
        transport.original_trace.take();
        transport.revalidate()
    }

    pub(super) fn poll_inherited_native(&self, end: Instant) -> Result<InheritedNativePoll> {
        let mut transport = self
            .transport
            .try_borrow_mut()
            .map_err(|_| NamespaceError::Rejected("notification request already borrowed"))?;
        let result = (|| -> Result<InheritedNativePoll> {
            transport.revalidate()?;
            if transport.failed || transport.receiving.is_some() {
                return Err(NamespaceError::Rejected(
                    "inherited request requires retirement",
                ));
            }
            transport
                .successors
                .as_ref()
                .ok_or(NamespaceError::Rejected(
                    "original native handoff is absent",
                ))?
                .matches_listener(
                    self.identity,
                    self.nonce,
                    self.pidfd,
                    self.proc,
                    transport.node,
                )?;
            if transport.pending.is_none() {
                if transport.successor_deadline.is_some() {
                    return Err(NamespaceError::Rejected(
                        "inherited request lost its original notification",
                    ));
                }
                transport.successors.as_ref().unwrap().idle()?;
                let now = Instant::now();
                if now >= end || end.duration_since(now) > Duration::from_secs(10) {
                    return Err(NamespaceError::Rejected(
                        "inherited native bounded poll deadline",
                    ));
                }
                let mut ready = libc::pollfd {
                    fd: transport.file.as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                };
                let count = unsafe { libc::poll(&mut ready, 1, 0) };
                if count < 0 {
                    return Err(io::Error::last_os_error().into());
                }
                if ready.revents & (libc::POLLHUP | libc::POLLERR | libc::POLLNVAL) != 0 {
                    return Err(NamespaceError::Rejected(
                        "inherited listener is no longer live",
                    ));
                }
                if count == 0 || ready.revents & libc::POLLIN == 0 {
                    return Ok(InheritedNativePoll::Idle);
                }
                // Store the first budget before RECV can consume a request.
                transport.successor_deadline = Some(end);
                transport.receive(end)?;
            }
            let deadline = transport
                .successor_deadline
                .ok_or(NamespaceError::Rejected(
                    "inherited pending deadline absent",
                ))?;
            if Instant::now() >= deadline {
                return Err(NamespaceError::Rejected(
                    "inherited pending operation exceeded original deadline",
                ));
            }
            let notification = *transport
                .pending
                .as_ref()
                .ok_or(NamespaceError::RetirementUnproven)?;
            transport.valid(&notification)?;
            let operation = notification.operation().ok_or(NamespaceError::Rejected(
                "inherited pending operation differs",
            ))?;
            if !matches!(
                operation,
                wire::Operation::Unshare | wire::Operation::SetNamespace
            ) {
                return Ok(InheritedNativePoll::PendingOther(operation));
            }
            {
                let held = &mut *transport;
                let owner = held
                    .successors
                    .as_mut()
                    .ok_or(NamespaceError::RetirementUnproven)?;
                owner.prepare(&held.file, notification, deadline)?;
                owner.arm(&held.file)?;
            }
            transport.valid(&notification)?;
            {
                let held = &mut *transport;
                held.successors
                    .as_mut()
                    .unwrap()
                    .before_continue(&held.file, &notification)?;
            }
            transport.failed = true;
            let response = wire::Response {
                id: notification.id,
                value: 0,
                error: 0,
                flags: 1,
            };
            if unsafe { libc::ioctl(transport.file.as_raw_fd(), wire::SEND, &response) } != 0 {
                return Err(io::Error::last_os_error().into());
            }
            {
                let held = &mut *transport;
                held.successors
                    .as_mut()
                    .unwrap()
                    .continued(&held.file, &notification)?;
            }
            // Keep the same pending journal and unique borrow through the real
            // exit and stopped DETACH. Nothing else can dispatch a mount here.
            let outcome = loop {
                let complete = transport.successors.as_mut().unwrap().complete()?;
                if let Some(outcome) = complete {
                    break outcome;
                }
                std::thread::sleep(Duration::from_millis(1));
            };
            if Instant::now() >= deadline {
                return Err(NamespaceError::Rejected(
                    "inherited native completion exceeded original deadline",
                ));
            }
            transport.pending.take();
            transport.successor_deadline.take();
            transport.failed = false;
            Ok(InheritedNativePoll::Completed(outcome))
        })();
        if result.is_err() {
            transport.failed = true;
            if let Some(owner) = transport.successors.as_mut() {
                owner.failed();
            }
        }
        result
    }

    pub(super) fn retire_before_init_wait(&self, child: &TreeChild) -> Result<()> {
        let mut transport = self
            .transport
            .try_borrow_mut()
            .map_err(|_| NamespaceError::RetirementUnproven)?;
        transport.stop_receiver()?;
        if let Some(owner) = transport.successors.as_mut() {
            owner.retire_before_init_wait(child)?;
        }
        Ok(())
    }

    pub(super) fn original_native_namespace(
        &self,
        end: Instant,
    ) -> Result<OriginalNativeRequest<'_>> {
        let mut transport = self
            .transport
            .try_borrow_mut()
            .map_err(|_| NamespaceError::Rejected("notification request already borrowed"))?;
        let trace = transport
            .original_trace
            .as_ref()
            .ok_or(NamespaceError::Rejected(
                "native request has no original trace owner",
            ))?
            .clone();
        {
            let owner = trace
                .try_borrow()
                .map_err(|_| NamespaceError::Rejected("original trace already borrowed"))?;
            owner.matches_listener(
                self.identity,
                self.nonce,
                self.pidfd,
                self.proc,
                transport.node,
            )?;
            owner.matches_deadline(end)?;
        }
        let notification = transport.receive(end)?;
        {
            let owner = trace
                .try_borrow()
                .map_err(|_| NamespaceError::Rejected("original trace already borrowed"))?;
            owner.matches_listener(
                self.identity,
                self.nonce,
                self.pidfd,
                self.proc,
                transport.node,
            )?;
            owner.check_notification(&notification)?;
        }
        Ok(OriginalNativeRequest {
            transport,
            trace,
            notification,
            identity: self.identity,
            nonce: self.nonce,
            pidfd: self.pidfd,
            proc: self.proc,
            deadline: end,
        })
    }

    pub(super) fn receive(
        &mut self,
        child: &TreeChild,
        end: Instant,
    ) -> Result<wire::Notification> {
        self.revalidate(child)?;
        let notification = self
            .transport
            .try_borrow_mut()
            .map_err(|_| NamespaceError::Rejected("notification request already borrowed"))?
            .receive(end)?;
        self.revalidate(child)?;
        Ok(notification)
    }

    pub(super) fn reject(&mut self, child: &TreeChild, errno: i32) -> Result<()> {
        self.revalidate(child)?;
        self.transport
            .try_borrow_mut()
            .map_err(|_| NamespaceError::Rejected("notification request already borrowed"))?
            .reject(errno)
    }

    pub(super) fn original_init_unmount<'a>(
        &'a self,
        child: &'a TreeChild,
        init: &ExecutedInitWitness<'_>,
        end: Instant,
    ) -> Result<OriginalInitUnmountRequest<'a>> {
        self.revalidate(child)?;
        init.revalidate_capability_contract()?;
        if init.host_pid() != child.identity.pid || Instant::now() >= end {
            return Err(NamespaceError::Rejected(
                "original init notification owner/deadline",
            ));
        }
        let mut transport = self
            .transport
            .try_borrow_mut()
            .map_err(|_| NamespaceError::Rejected("notification request already borrowed"))?;
        let notification = transport.receive(end)?;
        if notification.pid != child.identity.pid
            || notification.operation() != Some(wire::Operation::Unmount)
            || notification.data.args[1] != 0
        {
            return Err(NamespaceError::Rejected(
                "only the original init fixed umount2 request",
            ));
        }
        let raw = unsafe {
            libc::openat(
                child.proc_dir.as_raw_fd(),
                c"mem".as_ptr(),
                libc::O_RDONLY | libc::O_CLOEXEC | libc::O_NOFOLLOW,
            )
        };
        if raw < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let memory = unsafe { File::from_raw_fd(raw) };
        if filesystem_kind(&memory)? != PROC_MAGIC {
            return Err(NamespaceError::Rejected(
                "original init memory is not held procfs",
            ));
        }
        let memory_node = Node::of(&memory)?;
        transport.valid(&notification)?;
        let kind = original_cleanup_target(&memory, notification.data.args[0])?;
        let value = OriginalInitUnmountRequest {
            transport,
            child,
            notification,
            memory,
            memory_node,
            generation: init.generation()?,
            kind,
            deadline: end,
        };
        value.revalidate(init)?;
        Ok(value)
    }

    pub(super) fn retire_after_tree(
        &mut self,
        child: &TreeChild,
        actual_exit: &ChildExit,
    ) -> Result<()> {
        let transport = self.transport.get_mut();
        transport.retire_after_tree()?;
        if let Some(owner) = transport.successors.as_mut() {
            owner.retire_after_tree(child, actual_exit)?;
        }
        transport.successors.take();
        transport.successor_deadline.take();
        Ok(())
    }
    pub(super) fn stop_receiver(&mut self) -> Result<()> {
        self.transport.get_mut().stop_receiver()
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd)]
pub(crate) enum OriginalInitUnmountKind {
    DebugRamdisk,
    SecondStageResources,
}

impl OriginalInitUnmountKind {
    pub(crate) fn name(self) -> &'static std::ffi::CStr {
        match self {
            Self::DebugRamdisk => c"debug_ramdisk",
            Self::SecondStageResources => c"second_stage_resources",
        }
    }
    pub(crate) fn target(self) -> &'static str {
        match self {
            Self::DebugRamdisk => "/debug_ramdisk",
            Self::SecondStageResources => "/second_stage_resources",
        }
    }
}

/// Read only the finite longest original target plus its terminator. Partial
/// preads are allowed only until that same bound; no caller pathname escapes.
fn original_cleanup_target(memory: &File, address: u64) -> Result<OriginalInitUnmountKind> {
    const MAX: usize = b"/second_stage_resources\0".len();
    if address == 0 || address > (i64::MAX as u64).saturating_sub(MAX as u64) {
        return Err(NamespaceError::Rejected(
            "original init pointer outside native user range",
        ));
    }
    let mut bytes = [0_u8; MAX];
    let mut at = 0;
    while at < bytes.len() {
        let count = memory.read_at(&mut bytes[at..], address + at as u64)?;
        if count == 0 {
            return Err(NamespaceError::Rejected("incomplete original init target"));
        }
        at += count;
        if let Some(end) = bytes[..at].iter().position(|byte| *byte == 0) {
            return match &bytes[..end] {
                b"/debug_ramdisk" => Ok(OriginalInitUnmountKind::DebugRamdisk),
                b"/second_stage_resources" => Ok(OriginalInitUnmountKind::SecondStageResources),
                _ => Err(NamespaceError::Rejected(
                    "original init target is outside fixed cleanup",
                )),
            };
        }
    }
    Err(NamespaceError::Rejected(
        "unterminated original init target",
    ))
}

// The received WAIT_KILLABLE_RECV request keeps the original main thread
// asleep until its reply or fatal exit. Once the kernel reports one thread,
// and that sole thread has no children, no guest task can fork a new mount
// actor. This is an actual proc observation of the original held process,
// not a caller's process count or a status receipt.
fn single_process_status(raw: &[u8], pid: u32) -> Result<()> {
    if pid <= 1 || raw.is_empty() || raw.len() > 8192 || !raw.ends_with(b"\n") {
        return Err(NamespaceError::Rejected(
            "complete original single-task status",
        ));
    }
    let text = std::str::from_utf8(raw)
        .map_err(|_| NamespaceError::Rejected("original task status encoding"))?;
    let mut seen = [false; 3];
    for line in text.lines() {
        let Some((key, value)) = line.split_once(':') else {
            continue;
        };
        let index = match key {
            "Pid" => 0,
            "Tgid" => 1,
            "Threads" => 2,
            _ => continue,
        };
        let value = value.trim_matches(|c| c == ' ' || c == '\t');
        let expected = if index == 2 { 1 } else { pid };
        if seen[index] || value != expected.to_string() {
            return Err(NamespaceError::Rejected(
                "original init is not its one main thread",
            ));
        }
        seen[index] = true;
    }
    if seen != [true; 3] {
        return Err(NamespaceError::Rejected(
            "original single-task identity fields absent",
        ));
    }
    Ok(())
}

fn task_leaf(parent: &File, name: &std::ffi::CStr, directory: bool) -> Result<File> {
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
    if filesystem_kind(&file)? != PROC_MAGIC {
        return Err(NamespaceError::Rejected(
            "original task observation is not procfs",
        ));
    }
    Ok(file)
}

fn task_bytes(parent: &File, name: &std::ffi::CStr, bound: u64) -> Result<Vec<u8>> {
    use std::io::Read;
    let file = task_leaf(parent, name, false)?;
    let node = Node::of(&file)?;
    let mut bytes = Vec::new();
    (&file).take(bound + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > bound || Node::of(&file)? != node {
        return Err(NamespaceError::Rejected(
            "original task observation bound or inode changed",
        ));
    }
    Ok(bytes)
}

pub(super) fn original_single_process(proc: &File, pid: u32) -> Result<()> {
    if filesystem_kind(proc)? != PROC_MAGIC {
        return Err(NamespaceError::Rejected(
            "original main process custody is not procfs",
        ));
    }
    let proc_node = Node::of(proc)?;
    single_process_status(&task_bytes(proc, c"status", 8192)?, pid)?;
    let task = task_leaf(proc, c"task", true)?;
    let name = std::ffi::CString::new(pid.to_string())
        .map_err(|_| NamespaceError::Rejected("original main thread name"))?;
    let main = task_leaf(&task, &name, true)?;
    let main_node = Node::of(&main)?;
    single_process_status(&task_bytes(&main, c"status", 8192)?, pid)?;
    if !task_bytes(&main, c"children", 0)?.is_empty() {
        return Err(NamespaceError::Rejected(
            "original init already has another guest process",
        ));
    }
    single_process_status(&task_bytes(&main, c"status", 8192)?, pid)?;
    single_process_status(&task_bytes(proc, c"status", 8192)?, pid)?;
    if Node::of(proc)? != proc_node || Node::of(&main)? != main_node {
        return Err(NamespaceError::Rejected(
            "original single task proc identity changed",
        ));
    }
    Ok(())
}

/// Delivery receipt only. This type cannot assert native success, errno, a
/// new namespace, a mount graph or readiness. Its sole constructor follows
/// an actual successful SEND on the already held inherited listener.
pub(super) struct NativeContinueReceipt {
    identity: ProcessIdentity,
    nonce: [u8; 16],
    pidfd: Node,
    proc: Node,
    listener: Node,
    notification: wire::Notification,
    deadline: Instant,
}

impl NativeContinueReceipt {
    pub(super) fn notification(&self) -> &wire::Notification {
        &self.notification
    }

    pub(super) fn validate_original(&self, original: &OriginalPtrace) -> Result<()> {
        original.matches_listener(
            self.identity,
            self.nonce,
            self.pidfd,
            self.proc,
            self.listener,
        )?;
        original.matches_deadline(self.deadline)?;
        if Instant::now() >= self.deadline {
            return Err(NamespaceError::Rejected(
                "native continuation delivery exceeded deadline",
            ));
        }
        Ok(())
    }
}

/// A unique borrow of the exact kernel request that followed the original
/// task's observed entry-stop. The inherited filter remains installed.
pub(super) struct OriginalNativeRequest<'a> {
    transport: RefMut<'a, Transport>,
    trace: Rc<RefCell<OriginalPtrace>>,
    notification: wire::Notification,
    identity: ProcessIdentity,
    nonce: [u8; 16],
    pidfd: Node,
    proc: Node,
    deadline: Instant,
}

impl OriginalNativeRequest<'_> {
    pub(super) fn execute_original(mut self) -> Result<()> {
        let result = (|| -> Result<()> {
            if self.transport.failed
                || self.transport.pending.as_ref() != Some(&self.notification)
                || self.transport.receiving.is_some()
                || Instant::now() >= self.deadline
            {
                return Err(NamespaceError::Rejected(
                    "native pending request, receiver or deadline changed",
                ));
            }
            self.transport.valid(&self.notification)?;
            let mut original = self
                .trace
                .try_borrow_mut()
                .map_err(|_| NamespaceError::Rejected("original trace already borrowed"))?;
            original.matches_listener(
                self.identity,
                self.nonce,
                self.pidfd,
                self.proc,
                self.transport.node,
            )?;
            original.matches_deadline(self.deadline)?;
            original.arm_native_notification(&self.transport.file, &self.notification)?;
            original.before_native_continue(&self.notification)?;
            // The fixed kernel ARM binds the original successfully received
            // request and exact thread PIDFD. Its one-shot native fdget guard
            // retains the setns file even with legitimate shared file tables.
            // No existing tracer, register write or ADDFD is accepted.
            self.transport.valid(&self.notification)?;
            if Instant::now() >= self.deadline {
                return Err(NamespaceError::Rejected("native SEND deadline"));
            }
            let response = wire::Response {
                id: self.notification.id,
                value: 0,
                error: 0,
                flags: 1,
            };
            self.transport.failed = true;
            if unsafe { libc::ioctl(self.transport.file.as_raw_fd(), wire::SEND, &response) } != 0 {
                return Err(io::Error::last_os_error().into());
            }
            // The task can already be at its actual exit-stop. Neither this
            // zero response nor the ioctl return is a syscall result witness.
            let receipt = NativeContinueReceipt {
                identity: self.identity,
                nonce: self.nonce,
                pidfd: self.pidfd,
                proc: self.proc,
                listener: self.transport.node,
                notification: self.notification,
                deadline: self.deadline,
            };
            original.native_continue_applied(receipt)?;
            self.transport.pending.take();
            self.transport.failed = false;
            Ok(())
        })();
        if result.is_err() {
            self.transport.failed = true;
            if let Ok(mut original) = self.trace.try_borrow_mut() {
                original.continuation_failed();
            }
        }
        result
    }
}

/// A real pending kernel notification borrowed from this original listener.
/// It owns no independent response authority; its complete method requires the
/// actual fixed helper outcome and revalidates the original init generation.
pub(crate) struct OriginalInitUnmountRequest<'a> {
    transport: RefMut<'a, Transport>,
    child: &'a TreeChild,
    notification: wire::Notification,
    memory: File,
    memory_node: Node,
    generation: ExecutedInitGeneration,
    kind: OriginalInitUnmountKind,
    deadline: Instant,
}

impl OriginalInitUnmountRequest<'_> {
    pub(crate) fn kind(&self) -> OriginalInitUnmountKind {
        self.kind
    }
    pub(crate) fn notification(&self) -> wire::Notification {
        self.notification
    }
    pub(crate) fn generation(&self) -> ExecutedInitGeneration {
        self.generation
    }
    pub(crate) fn deadline(&self) -> Instant {
        self.deadline
    }

    pub(crate) fn revalidate(&self, init: &ExecutedInitWitness<'_>) -> Result<()> {
        if Instant::now() >= self.deadline {
            return Err(NamespaceError::Rejected("original init request deadline"));
        }
        init.revalidate_capability_contract()?;
        self.child.verify()?;
        if init.host_pid() != self.child.identity.pid
            || init.generation()? != self.generation
            || self.notification.pid != self.child.identity.pid
            || self.transport.pending != Some(self.notification)
            || self.transport.failed
            || Node::of(&self.memory)? != self.memory_node
        {
            return Err(NamespaceError::Rejected(
                "original pending init request identity changed",
            ));
        }
        self.transport.valid(&self.notification)?;
        original_single_process(&self.child.proc_dir, self.child.identity.pid)?;
        self.transport.valid(&self.notification)?;
        if original_cleanup_target(&self.memory, self.notification.data.args[0])? != self.kind {
            return Err(NamespaceError::Rejected(
                "original init fixed target changed",
            ));
        }
        self.transport.valid(&self.notification)?;
        if Instant::now() >= self.deadline {
            return Err(NamespaceError::Rejected(
                "original init request observation deadline",
            ));
        }
        init.revalidate()?;
        if Instant::now() >= self.deadline {
            return Err(NamespaceError::Rejected(
                "original init final request observation exceeded its deadline",
            ));
        }
        Ok(())
    }

    pub(super) fn complete(
        mut self,
        init: &ExecutedInitWitness<'_>,
        completed: &OriginalInitCleanup,
    ) -> Result<()> {
        self.revalidate(init)?;
        let errno = completed
            .actual_errno(init, &self)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        self.revalidate(init)?;
        let response = wire::Response {
            id: self.notification.id,
            value: 0,
            error: -errno,
            flags: 0,
        };
        self.transport.failed = true;
        if unsafe { libc::ioctl(self.transport.file.as_raw_fd(), wire::SEND, &response) } != 0 {
            return Err(io::Error::last_os_error().into());
        }
        self.transport.pending.take();
        if Instant::now() >= self.deadline {
            // The actual syscall reply has already resumed this task. Do not
            // admit a completed activation phase on an expired observation;
            // the caller must retire the same original tree.
            return Err(NamespaceError::Rejected(
                "original init syscall reply exceeded its original deadline",
            ));
        }
        self.transport.failed = false;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    pub(super) fn actual_listener() -> (
        File,
        std::sync::mpsc::SyncSender<bool>,
        std::thread::JoinHandle<(i64, i32)>,
    ) {
        let (send, receive) = std::sync::mpsc::sync_channel(1);
        let (release, wait) = std::sync::mpsc::sync_channel(1);
        let task = std::thread::spawn(move || {
            assert_eq!(
                unsafe { libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) },
                0
            );
            let raw = unsafe { wire::install() }.unwrap();
            let file = unsafe { File::from_raw_fd(raw) };
            send.send(file).unwrap();
            if wait.recv().unwrap() {
                let result = unsafe { libc::syscall(libc::SYS_ioctl, -1, 0x4c82_u64, 0) };
                (result, io::Error::last_os_error().raw_os_error().unwrap())
            } else {
                (0, 0)
            }
        });
        (receive.recv().unwrap(), release, task)
    }

    #[test]
    fn original_init_single_task_parser_rejects_missing_duplicate_and_ambiguous_identity() {
        let good = b"Name:\tinit\nTgid:\t123\nPid:\t123\nThreads:\t1\n";
        single_process_status(good, 123).unwrap();
        for bad in [
            b"Pid:\t123\nThreads:\t1\n".as_slice(),
            b"Pid:\t123\nTgid:\t123\nThreads:\t2\n",
            b"Pid:\t123\nTgid:\t123\nThreads:\t1\nThreads:\t1\n",
            b"Pid:\t123\nTgid:\t124\nThreads:\t1\n",
            b"Pid:\t0123\nTgid:\t123\nThreads:\t1\n",
            b"Pid:\t123\nTgid:\t123\nThreads:\t1",
        ] {
            assert!(single_process_status(bad, 123).is_err());
        }
        let directory = tempfile::tempdir().unwrap();
        let ordinary = File::open(directory.path()).unwrap();
        assert!(original_single_process(&ordinary, 123).is_err());
    }

    #[test]
    fn original_init_single_task_observation_reads_real_proc_and_rejects_a_live_child() {
        use std::io::Read;
        use std::process::{Child, Command, Stdio};
        struct Owned {
            child: Child,
            pidfd: std::os::fd::OwnedFd,
        }
        impl Drop for Owned {
            fn drop(&mut self) {
                self.child.stdin.take();
                let end = Instant::now() + Duration::from_secs(2);
                loop {
                    match self.child.try_wait() {
                        Ok(Some(_)) => return,
                        Ok(None) if Instant::now() < end => std::thread::yield_now(),
                        _ => break,
                    }
                }
                unsafe {
                    libc::syscall(
                        libc::SYS_pidfd_send_signal,
                        self.pidfd.as_raw_fd(),
                        libc::SIGKILL,
                        std::ptr::null::<libc::siginfo_t>(),
                        0,
                    );
                }
                let _ = self.child.wait();
            }
        }
        let shell = std::fs::canonicalize("/bin/sh").unwrap();
        let sleep = std::fs::canonicalize("/bin/sleep").unwrap();
        for has_child in [false, true] {
            let script = if has_child {
                "\"$1\" 30 & kid=$!; printf ready; read x; kill \"$kid\"; wait \"$kid\" || :"
            } else {
                "printf ready; read x || :"
            };
            let mut child = Command::new(&shell)
                .args(["-c", script, "owned-proc-control"])
                .arg(&sleep)
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::null())
                .spawn()
                .unwrap();
            // This unreaped Child is the only source of the PID. It cannot be
            // reused while this parent acquires and retains its actual PIDFD.
            let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, child.id(), 0) };
            if raw < 0 {
                let error = io::Error::last_os_error();
                child.stdin.take();
                let _ = child.kill();
                let _ = child.wait();
                panic!("original test child PIDFD could not be acquired: {error}");
            }
            let mut owned = Owned {
                child,
                pidfd: unsafe { std::os::fd::OwnedFd::from_raw_fd(raw as i32) },
            };
            let mut ready = [0_u8; 5];
            owned
                .child
                .stdout
                .as_mut()
                .unwrap()
                .read_exact(&mut ready)
                .unwrap();
            assert_eq!(&ready, b"ready");
            let proc = File::open(format!("/proc/{}", owned.child.id())).unwrap();
            assert_eq!(
                original_single_process(&proc, owned.child.id()).is_ok(),
                !has_child
            );
            owned.child.stdin.take();
            let end = Instant::now() + Duration::from_secs(2);
            loop {
                if let Some(exit) = owned.child.try_wait().unwrap() {
                    assert!(exit.success());
                    break;
                }
                assert!(
                    Instant::now() < end,
                    "actual owned proc control must exit and reap its child"
                );
                std::thread::yield_now();
            }
        }
    }

    #[test]
    fn original_init_cleanup_targets_read_actual_memory_and_reject_escape_or_unbounded_pointers() {
        let memory = File::open("/proc/self/mem").unwrap();
        for (path, kind) in [
            (c"/debug_ramdisk", OriginalInitUnmountKind::DebugRamdisk),
            (
                c"/second_stage_resources",
                OriginalInitUnmountKind::SecondStageResources,
            ),
        ] {
            assert_eq!(
                original_cleanup_target(&memory, path.as_ptr() as u64).unwrap(),
                kind
            );
        }
        for path in [c"/", c"/debug_ramdisk/child", c"/second_stage_resourcesx"] {
            assert!(original_cleanup_target(&memory, path.as_ptr() as u64).is_err());
        }
        let unterminated = [b'x'; 32];
        assert!(original_cleanup_target(&memory, unterminated.as_ptr() as u64).is_err());
        for address in [0, i64::MAX as u64, u64::MAX] {
            assert!(original_cleanup_target(&memory, address).is_err());
        }
    }

    #[test]
    fn apex_notification_actual_ioctl_is_received_once_and_denial_reaches_original_task() {
        let (file, release, task) = actual_listener();
        let mut transport = Transport::new(file).unwrap();
        release.send(true).unwrap();
        let notification = transport
            .receive(Instant::now() + Duration::from_secs(3))
            .unwrap();
        assert_eq!(notification.operation(), Some(wire::Operation::LoopIoctl));
        assert_eq!(notification.data.args[1], 0x4c82);
        assert!(
            transport
                .receive(Instant::now() + Duration::from_secs(1))
                .is_err()
        );
        assert!(transport.reject(0).is_err());
        transport.valid(&notification).unwrap();
        transport.reject(libc::EACCES).unwrap();
        assert_eq!(task.join().unwrap(), (-1, libc::EACCES));
        assert!(transport.valid(&notification).is_err());
        assert!(transport.reject(libc::EPERM).is_err());
        transport.retire_after_tree().unwrap();
    }

    #[test]
    fn apex_notification_idle_kernel_recv_expires_and_actual_worker_is_reaped() {
        let (file, release, task) = actual_listener();
        let mut transport = Transport::new(file).unwrap();
        let now = Instant::now();
        assert!(transport.receive(now + Duration::from_millis(80)).is_err());
        assert!(now.elapsed() < Duration::from_secs(3));
        assert!(transport.receiving.is_none() && transport.pending.is_none());
        assert!(transport.failed);
        assert!(
            transport
                .receive(Instant::now() + Duration::from_secs(3))
                .is_err()
        );
        release.send(false).unwrap();
        assert_eq!(task.join().unwrap(), (0, 0));
        transport.retire_after_tree().unwrap();
    }

    #[test]
    fn apex_notification_listener_rejects_regular_and_other_anonymous_descriptors() {
        assert!(Transport::new(tempfile::tempfile().unwrap()).is_err());
        let raw = unsafe { libc::eventfd(0, libc::EFD_CLOEXEC | libc::EFD_NONBLOCK) };
        assert!(raw >= 0);
        assert!(Transport::new(unsafe { File::from_raw_fd(raw) }).is_err());
    }
}

#[cfg(test)]
pub(super) fn receive_native_control(
    listener: &File,
    deadline: Instant,
) -> Result<wire::Notification> {
    let mut receiver = receiver::Receiver::spawn(listener, deadline)?;
    let result = (|| -> io::Result<wire::Notification> {
        receiver.start()?;
        receiver.complete()
    })();
    let retired = receiver.retire();
    if retired.is_err() {
        std::mem::forget(receiver);
        return Err(NamespaceError::RetirementUnproven);
    }
    Ok(result?)
}
