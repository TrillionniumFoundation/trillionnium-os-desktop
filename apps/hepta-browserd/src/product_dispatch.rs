//! Product request composition over the original accepted AF_UNIX stream.
//!
//! This source API connects the concrete Servo actor and managed receipts. A
//! native embedder must own/pump the matching ServoRuntimeOwner. It introduces
//! no listener, fixture backend, mailbox, startup activation or release claim.

use std::cell::RefCell;
use std::fmt;
use std::net::Shutdown;
use std::os::unix::net::UnixStream;
use std::rc::Rc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, mpsc};
use std::time::{Duration, Instant};

use hepta_agent_port::{
    AgentPortError, BrowserRequestHandler, DispatchContext, HandlerOutcome,
    OperationLifecycleObserver, ServiceEvidence, serve_one_before_with_observer,
};
#[cfg(target_os = "linux")]
use hepta_agent_transport::{HandoffError, ReceivedAcceptedStream};
use hepta_agent_transport::{PeerIdentity, PeerPolicy};
use hepta_browser_actor::{
    CancellationToken, ReceiptLifecycleObserver, ServoBrowserActor, ServoRuntimeEndpoint,
    TaskFlowPrincipal,
};
use hepta_browser_codec::{BrowserErrorCode, BrowserRequest, BrowserResponse, BrowserWireError};
use hepta_peer_attestation::{AttestedPeer, PeerRuntimePolicy, ProcfsPeerAttestor};
#[cfg(target_os = "linux")]
use hepta_peer_attestation::{
    ControlOwnerError, ControlReceivedAcceptedStream, ControlRequestCustody, ControlRequestVerifier,
};
use hepta_session_core::{Digest, DurableReceiptFact, ReceiptJournal, ReceiptLifecycleState};

use crate::{RestartPolicy, RuntimeGeneration, RuntimeState};

#[cfg(target_os = "linux")]
mod product_approved_policy;
#[cfg(target_os = "linux")]
pub use product_approved_policy::ApprovedRetainedProductConnection;
#[cfg(target_os = "linux")]
mod product_control_wait;
#[cfg(target_os = "linux")]
pub use product_control_wait::{
    ProductControlMonitor, ProductControlMonitorOutcome, RetainedProductConnection,
};

pub const MAX_PRODUCT_PENDING_CONNECTIONS: usize = 8;
pub const MAX_PRODUCT_CONNECTION_BUDGET: Duration = Duration::from_secs(20);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ProductDispatchError {
    InvalidConfiguration,
    PeerRefused,
    QueueFull,
    Closed,
    DeadlineExceeded,
    Cancelled,
    RecoveryRequired,
    StorageUnavailable,
    DispatchFailed,
    CrashLoopOpen,
}

impl fmt::Display for ProductDispatchError {
    fn fmt(&self, output: &mut fmt::Formatter<'_>) -> fmt::Result {
        output.write_str(match self {
            Self::InvalidConfiguration => "invalid product dispatch configuration",
            Self::PeerRefused => "product peer custody refused",
            Self::QueueFull => "product connection queue is full",
            Self::Closed => "product connection queue is closed",
            Self::DeadlineExceeded => "product connection deadline exceeded",
            Self::Cancelled => "product connection cancelled",
            Self::RecoveryRequired => "product request requires durable reconciliation",
            Self::StorageUnavailable => "product receipt storage requires recovery",
            Self::DispatchFailed => "product transport or dispatch failed",
            Self::CrashLoopOpen => "product runtime crash loop is locked",
        })
    }
}
impl std::error::Error for ProductDispatchError {}

#[derive(Default)]
struct ConnectionControl {
    owner_pid: u32,
    cancelled: AtomicBool,
    active: Mutex<Option<CancellationToken>>,
    transport: Mutex<Option<UnixStream>>,
    #[cfg(target_os = "linux")]
    custodian: Option<ControlRequestCustody>,
}

/// Revocation only: this handle cannot dispatch, release human control, or
/// clear recovery. It applies to one queued or active connection lifetime.
#[derive(Clone)]
pub struct ProductConnectionCancellation(Arc<ConnectionControl>);
impl ProductConnectionCancellation {
    pub fn cancel(&self) {
        if self.0.owner_pid != std::process::id() {
            return;
        }
        self.0.cancelled.store(true, Ordering::SeqCst);
        #[cfg(target_os = "linux")]
        if let Some(custodian) = &self.0.custodian {
            let _ = custodian.revoke();
        }
        if let Ok(active) = self.0.active.lock()
            && let Some(token) = active.as_ref()
        {
            token.cancel();
        }
        // Interrupt a transport challenge/read as well as an active engine
        // token. This is the same accepted socket, never a replacement peer.
        if let Ok(transport) = self.0.transport.lock()
            && let Some(stream) = transport.as_ref()
        {
            let _ = stream.shutdown(Shutdown::Both);
        }
    }
}

/// Holds the original stream and original opaque pidfd-backed attestation.
/// Mechanism facts are never copied into a second request/JSON IPC protocol.
pub struct AcceptedProductConnection {
    stream: Option<UnixStream>,
    peer: PeerIdentity,
    attestor: ProcfsPeerAttestor,
    attested: AttestedPeer,
    deadline: Instant,
    control: Arc<ConnectionControl>,
}

impl AcceptedProductConnection {
    pub fn attest(
        stream: UnixStream,
        attestor: ProcfsPeerAttestor,
        policy: &PeerRuntimePolicy,
        budget: Duration,
    ) -> Result<Self, ProductDispatchError> {
        if budget.is_zero() || budget > MAX_PRODUCT_CONNECTION_BUDGET {
            return Err(ProductDispatchError::InvalidConfiguration);
        }
        // Queue residence and identity admission consume the same budget.
        let deadline = Instant::now()
            .checked_add(budget)
            .ok_or(ProductDispatchError::InvalidConfiguration)?;
        Self::attest_before(stream, attestor, policy, deadline)
    }

    /// Consume the received original descriptor and its original absolute
    /// deadline together. Transfer and receiver queue residence are never
    /// converted into a fresh product admission budget. This still requires
    /// independently configured live identity policy; it grants no principal.
    #[cfg(target_os = "linux")]
    pub fn from_received(
        received: ReceivedAcceptedStream,
        attestor: ProcfsPeerAttestor,
        policy: &PeerRuntimePolicy,
    ) -> Result<Self, ProductDispatchError> {
        received
            .consume_before(|stream, deadline| {
                Self::attest_before(stream, attestor, policy, deadline)
            })
            .map_err(|error| match error {
                HandoffError::DeadlineExceeded => ProductDispatchError::DeadlineExceeded,
                _ => ProductDispatchError::PeerRefused,
            })?
    }

    /// Consume an opaque actual control handoff and retain its original
    /// custodian through this connection's response lifetime. Original Agent
    /// admission always uses default live `/proc`, never an injected source.
    #[cfg(target_os = "linux")]
    pub fn from_control_received(
        received: ControlReceivedAcceptedStream,
        policy: &PeerRuntimePolicy,
        approved_executable_sha256: &str,
    ) -> Result<Self, ProductDispatchError> {
        received.deadline().map_err(control_error)?;
        if approved_executable_sha256.len() != 64
            || !approved_executable_sha256
                .bytes()
                .all(|value| value.is_ascii_digit() || (b'a'..=b'f').contains(&value))
        {
            return Err(ProductDispatchError::InvalidConfiguration);
        }
        received
            .consume_before(|stream, deadline, custody| {
                let verifier = custody.verifier().map_err(control_error)?;
                verifier.verify_current().map_err(control_error)?;
                let mut connection =
                    Self::attest_before(stream, ProcfsPeerAttestor::default(), policy, deadline)?;
                if connection.attested.snapshot().executable_sha256 != approved_executable_sha256 {
                    return Err(ProductDispatchError::PeerRefused);
                }
                let control = Arc::get_mut(&mut connection.control)
                    .ok_or(ProductDispatchError::PeerRefused)?;
                control.custodian = Some(custody);
                connection.ensure_control_current()?;
                Ok(connection)
            })
            .map_err(control_error)?
    }

    #[cfg(target_os = "linux")]
    fn control_verifier(&self) -> Result<Option<ControlRequestVerifier>, ProductDispatchError> {
        if self.control.owner_pid != std::process::id() {
            return Err(ProductDispatchError::PeerRefused);
        }
        self.control
            .custodian
            .as_ref()
            .map(|custody| custody.verifier().map_err(control_error))
            .transpose()
    }

    fn ensure_control_current(&self) -> Result<(), ProductDispatchError> {
        #[cfg(target_os = "linux")]
        if let Some(verifier) = self.control_verifier()? {
            let checked = (|| {
                self.deadline()?;
                self.attested
                    .refresh_snapshot(&self.attestor)
                    .map_err(|_| ProductDispatchError::PeerRefused)?;
                self.deadline()?;
                verifier.verify_current().map_err(control_error)?;
                self.deadline()?;
                Ok(())
            })();
            if checked.is_err()
                && let Some(custody) = &self.control.custodian
            {
                let _ = custody.revoke();
            }
            checked?;
        }
        Ok(())
    }

    fn attest_before(
        stream: UnixStream,
        attestor: ProcfsPeerAttestor,
        policy: &PeerRuntimePolicy,
        deadline: Instant,
    ) -> Result<Self, ProductDispatchError> {
        let remaining = product_time_remaining(deadline)?;
        if remaining > MAX_PRODUCT_CONNECTION_BUDGET {
            return Err(ProductDispatchError::InvalidConfiguration);
        }
        let peer = PeerIdentity::from_stream(&stream);
        product_time_remaining(deadline)?;
        let peer = peer.map_err(|_| ProductDispatchError::PeerRefused)?;
        let attested = attestor.attest(peer, policy);
        product_time_remaining(deadline)?;
        let attested = attested.map_err(|_| ProductDispatchError::PeerRefused)?;
        let interrupt = stream.try_clone();
        product_time_remaining(deadline)?;
        let interrupt = interrupt.map_err(|_| ProductDispatchError::PeerRefused)?;
        attested
            .ensure_alive()
            .map_err(|_| ProductDispatchError::PeerRefused)?;
        product_time_remaining(deadline)?;
        let connection = Self {
            stream: Some(stream),
            peer,
            attestor,
            attested,
            deadline,
            control: Arc::new(ConnectionControl {
                owner_pid: std::process::id(),
                transport: Mutex::new(Some(interrupt)),
                ..ConnectionControl::default()
            }),
        };
        // Allocation/setup also consume the original ceiling. A late local
        // result closes its owned descriptors instead of issuing admission.
        product_time_remaining(deadline)?;
        Ok(connection)
    }

    /// Inspect the unchanged ingress ceiling, never renew it. This local
    /// observation is neither identity refresh nor dispatch authority.
    pub fn deadline(&self) -> Result<Instant, ProductDispatchError> {
        if self.control.owner_pid != std::process::id() {
            return Err(ProductDispatchError::PeerRefused);
        }
        if self.control.cancelled.load(Ordering::SeqCst) {
            return Err(ProductDispatchError::Cancelled);
        }
        product_time_remaining(self.deadline)?;
        Ok(self.deadline)
    }

    pub fn cancellation(&self) -> ProductConnectionCancellation {
        ProductConnectionCancellation(self.control.clone())
    }
}

fn product_time_remaining(deadline: Instant) -> Result<Duration, ProductDispatchError> {
    deadline
        .checked_duration_since(Instant::now())
        .filter(|remaining| !remaining.is_zero())
        .ok_or(ProductDispatchError::DeadlineExceeded)
}

#[cfg(target_os = "linux")]
fn control_error(error: ControlOwnerError) -> ProductDispatchError {
    match error {
        ControlOwnerError::DeadlineExceeded => ProductDispatchError::DeadlineExceeded,
        ControlOwnerError::Cancelled => ProductDispatchError::Cancelled,
        _ => ProductDispatchError::PeerRefused,
    }
}

impl Drop for AcceptedProductConnection {
    fn drop(&mut self) {
        if self.control.owner_pid != std::process::id() {
            return;
        }
        #[cfg(target_os = "linux")]
        if let Some(custodian) = &self.control.custodian {
            let _ = custodian.revoke();
        }
        if let Ok(mut active) = self.control.active.lock() {
            active.take();
        }
        if let Ok(mut transport) = self.control.transport.lock() {
            transport.take();
        }
    }
}

pub struct ProductConnectionIngress(u32, mpsc::SyncSender<AcceptedProductConnection>);
pub struct ProductConnectionQueue(u32, mpsc::Receiver<AcceptedProductConnection>);

pub fn product_connection_queue(
    capacity: usize,
) -> Result<(ProductConnectionIngress, ProductConnectionQueue), ProductDispatchError> {
    if capacity == 0 || capacity > MAX_PRODUCT_PENDING_CONNECTIONS {
        return Err(ProductDispatchError::InvalidConfiguration);
    }
    let (sender, receiver) = mpsc::sync_channel(capacity);
    let owner_pid = std::process::id();
    Ok((
        ProductConnectionIngress(owner_pid, sender),
        ProductConnectionQueue(owner_pid, receiver),
    ))
}

impl ProductConnectionIngress {
    /// Nonblocking admission. A full/closed queue drops and closes this stream.
    pub fn try_submit(
        &self,
        connection: AcceptedProductConnection,
    ) -> Result<ProductConnectionCancellation, ProductDispatchError> {
        if self.0 != std::process::id() || connection.control.owner_pid != self.0 {
            return Err(ProductDispatchError::PeerRefused);
        }
        connection.ensure_control_current()?;
        let cancellation = connection.cancellation();
        match self.1.try_send(connection) {
            Ok(()) => Ok(cancellation),
            Err(mpsc::TrySendError::Full(_)) => Err(ProductDispatchError::QueueFull),
            Err(mpsc::TrySendError::Disconnected(_)) => Err(ProductDispatchError::Closed),
        }
    }
}
impl ProductConnectionQueue {
    pub fn try_next(&self) -> Result<Option<AcceptedProductConnection>, ProductDispatchError> {
        if self.0 != std::process::id() {
            return Err(ProductDispatchError::PeerRefused);
        }
        match self.1.try_recv() {
            Ok(connection) => {
                connection.ensure_control_current()?;
                Ok(Some(connection))
            }
            Err(mpsc::TryRecvError::Empty) => Ok(None),
            Err(mpsc::TryRecvError::Disconnected) => Err(ProductDispatchError::Closed),
        }
    }
}

#[derive(Clone)]
struct RequestIdentity {
    id: String,
    digest: Digest,
}
#[derive(Default)]
struct OperationTrace {
    request: Option<RequestIdentity>,
    requested: bool,
    dispatched: bool,
    terminal: Option<ReceiptLifecycleState>,
    terminal_record: Option<Digest>,
    storage_failed: bool,
    uncertain: bool,
}

/// Co-own the actor and its receipt observer on one actor worker thread.
/// Rc state deliberately prevents moving a constructed coordinator to another
/// thread. Move the concrete endpoint first, then construct on that worker.
pub struct ProductRequestCoordinator {
    owner_pid: u32,
    actor: Option<ServoBrowserActor>,
    observer: Rc<RefCell<Option<ReceiptLifecycleObserver>>>,
    state: RuntimeState,
    generation: RuntimeGeneration,
    restart_policy: RestartPolicy,
    crashes: u32,
    pending_reconciliation: Option<RequestIdentity>,
    storage_failed: bool,
    image_id: String,
    principal: TaskFlowPrincipal,
    // Private coordinates from this invocation only; never supplied by a
    // caller's ServiceEvidence or a fact from another journal instance.
    #[cfg(target_os = "linux")]
    last_retirement: Option<(RequestIdentity, ReceiptLifecycleState, Digest)>,
}

impl ProductRequestCoordinator {
    pub fn from_connection(
        principal: TaskFlowPrincipal,
        bootstrap: &AcceptedProductConnection,
        endpoint: ServoRuntimeEndpoint,
        journal: ReceiptJournal,
        image_id: String,
        restart_policy: RestartPolicy,
    ) -> Result<Self, ProductDispatchError> {
        Self::from_connection_after_reconciliation(
            principal,
            bootstrap,
            endpoint,
            journal,
            image_id,
            restart_policy,
            &[],
        )
    }

    /// The trusted recovery caller must explicitly acknowledge every terminal
    /// uncertain request by its original identity and canonical digest. Each
    /// acknowledgment is checked against the live complete journal. It does
    /// not authorize replay, alter a receipt, or synthesize a known outcome.
    /// Nonterminal history and storage damage still require storage recovery.
    pub fn from_connection_after_reconciliation(
        principal: TaskFlowPrincipal,
        bootstrap: &AcceptedProductConnection,
        endpoint: ServoRuntimeEndpoint,
        mut journal: ReceiptJournal,
        image_id: String,
        restart_policy: RestartPolicy,
        acknowledged_requests: &[(&str, Digest)],
    ) -> Result<Self, ProductDispatchError> {
        if bootstrap.control.owner_pid != std::process::id() {
            return Err(ProductDispatchError::PeerRefused);
        }
        bootstrap.ensure_control_current()?;
        if !journal.is_managed()
            || image_id.is_empty()
            || image_id.len() > 128
            || image_id
                .chars()
                .any(|value| value.is_control() || value.is_whitespace())
        {
            return Err(ProductDispatchError::InvalidConfiguration);
        }
        // Opening existing history never resets a namespace or guesses a head.
        if journal
            .has_unresolved_receipts()
            .map_err(|_| ProductDispatchError::StorageUnavailable)?
        {
            return Err(ProductDispatchError::RecoveryRequired);
        }
        let uncertain = journal
            .execution_reconciliation_facts()
            .map_err(|_| ProductDispatchError::StorageUnavailable)?;
        if uncertain.len() != acknowledged_requests.len() {
            return Err(ProductDispatchError::RecoveryRequired);
        }
        for fact in &uncertain {
            let fact_id = fact
                .receipt_id()
                .map_err(|_| ProductDispatchError::StorageUnavailable)?;
            let fact_digest = fact
                .request_sha256()
                .map_err(|_| ProductDispatchError::StorageUnavailable)?;
            if acknowledged_requests
                .iter()
                .filter(|(id, digest)| *id == fact_id && *digest == fact_digest)
                .count()
                != 1
            {
                return Err(ProductDispatchError::RecoveryRequired);
            }
        }
        let actor = ServoBrowserActor::from_attested(
            principal.clone(),
            bootstrap.peer,
            &bootstrap.attestor,
            &bootstrap.attested,
            endpoint,
        )
        .map_err(|_| ProductDispatchError::PeerRefused)?;
        let observer = actor.receipt_observer(journal, image_id.clone());
        bootstrap.ensure_control_current()?;
        Ok(Self {
            owner_pid: std::process::id(),
            actor: Some(actor),
            observer: Rc::new(RefCell::new(Some(observer))),
            state: RuntimeState::Ready,
            generation: RuntimeGeneration::INITIAL,
            restart_policy,
            crashes: 0,
            pending_reconciliation: None,
            storage_failed: false,
            image_id,
            principal,
            #[cfg(target_os = "linux")]
            last_retirement: None,
        })
    }

    pub const fn state(&self) -> RuntimeState {
        self.state
    }
    pub const fn generation(&self) -> RuntimeGeneration {
        self.generation
    }

    fn ensure_owner(&self) -> Result<(), ProductDispatchError> {
        if self.owner_pid != std::process::id() {
            return Err(ProductDispatchError::PeerRefused);
        }
        Ok(())
    }

    pub fn serve_connection(
        &mut self,
        mut connection: AcceptedProductConnection,
    ) -> Result<ServiceEvidence, ProductDispatchError> {
        self.ensure_owner()?;
        #[cfg(target_os = "linux")]
        {
            self.last_retirement = None;
        }
        if connection.control.owner_pid != self.owner_pid {
            return Err(ProductDispatchError::PeerRefused);
        }
        if connection.control.cancelled.load(Ordering::SeqCst) {
            return Err(ProductDispatchError::Cancelled);
        }
        connection.ensure_control_current()?;
        if self.storage_failed {
            return Err(ProductDispatchError::StorageUnavailable);
        }
        if self.state == RuntimeState::CrashLoopOpen {
            return Err(ProductDispatchError::CrashLoopOpen);
        }
        if self.state != RuntimeState::Ready {
            return Err(ProductDispatchError::RecoveryRequired);
        }
        connection
            .deadline
            .checked_duration_since(Instant::now())
            .filter(|remaining| !remaining.is_zero())
            .ok_or(ProductDispatchError::DeadlineExceeded)?;
        let actor = self
            .actor
            .as_mut()
            .ok_or(ProductDispatchError::RecoveryRequired)?;
        let trace = Rc::new(RefCell::new(OperationTrace::default()));
        let stream = connection
            .stream
            .take()
            .ok_or(ProductDispatchError::Closed)?;
        let control = connection.control.clone();
        let mut handler = AttestedProductHandler {
            owner_pid: self.owner_pid,
            actor,
            attestor: &connection.attestor,
            attested: &connection.attested,
            observer: self.observer.clone(),
            trace: trace.clone(),
            control: control.clone(),
            prepared_request: None,
        };
        let mut lifecycle = DurableProductLifecycle {
            owner_pid: self.owner_pid,
            observer: self.observer.clone(),
            trace: trace.clone(),
        };
        // A panic or return after possible dispatch cannot clear uncertainty.
        self.state = RuntimeState::ReplayReconciliationRequired;
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            serve_one_before_with_observer(
                stream,
                PeerPolicy::exact(connection.peer),
                connection.deadline,
                &mut handler,
                &mut lifecycle,
            )
        }));
        // Lifecycle/deadline errors can skip handle after successful preflight.
        // Retire its request preparation before examining the durable outcome.
        drop(handler);
        self.ensure_owner()?;
        if let Ok(mut active) = control.active.lock() {
            active.take();
        }
        let trace = trace.borrow();
        #[cfg(target_os = "linux")]
        if !trace.storage_failed
            && trace.requested
            && let (Some(request), Some(lifecycle), Some(record)) =
                (&trace.request, trace.terminal, trace.terminal_record)
            && lifecycle.is_terminal()
        {
            self.last_retirement = Some((request.clone(), lifecycle, record));
        }
        self.storage_failed |= trace.storage_failed;
        let unresolved = trace.requested
            && (trace.uncertain
                || trace.terminal.is_none()
                || trace.terminal == Some(ReceiptLifecycleState::Indeterminate)
                || (trace.dispatched
                    && trace.terminal == Some(ReceiptLifecycleState::Interrupted)));
        if self.storage_failed || unresolved || result.is_err() {
            self.pending_reconciliation = trace.request.clone();
        } else {
            self.state = RuntimeState::Ready;
        }
        drop(trace);
        match result {
            Ok(result) => result.map_err(|_| {
                if self.storage_failed {
                    ProductDispatchError::StorageUnavailable
                } else {
                    ProductDispatchError::DispatchFailed
                }
            }),
            Err(panic) => std::panic::resume_unwind(panic),
        }
    }

    /// Explicitly inspect the exact blocked request in the live complete
    /// journal. Caller-created reports or generic supervisor latches are not
    /// accepted. Clearing uncertainty never reconstructs or repeats work.
    pub fn reconcile_request(
        &mut self,
        request_id: &str,
        request_digest: Digest,
    ) -> Result<DurableReceiptFact, ProductDispatchError> {
        self.ensure_owner()?;
        if self.storage_failed {
            return Err(ProductDispatchError::StorageUnavailable);
        }
        let pending = self
            .pending_reconciliation
            .as_ref()
            .ok_or(ProductDispatchError::RecoveryRequired)?;
        if pending.id != request_id || pending.digest != request_digest {
            return Err(ProductDispatchError::RecoveryRequired);
        }
        let fact = self
            .observer
            .borrow_mut()
            .as_mut()
            .ok_or(ProductDispatchError::StorageUnavailable)?
            .receipt_fact(request_id, request_digest)
            .map_err(|_| ProductDispatchError::StorageUnavailable)?;
        if !fact
            .lifecycle()
            .map_err(|_| ProductDispatchError::StorageUnavailable)?
            .is_terminal()
        {
            return Err(ProductDispatchError::RecoveryRequired);
        }
        self.pending_reconciliation = None;
        if self.state != RuntimeState::CrashLoopOpen {
            self.state = if self.actor.is_some() {
                RuntimeState::Ready
            } else {
                RuntimeState::NeedsReconstruction
            };
        }
        Ok(fact)
    }

    /// The native owner must withdraw content pixels/input and retire its
    /// bridge before calling this notification. No factory or replay runs here.
    pub fn content_process_crashed(&mut self) -> Result<(), ProductDispatchError> {
        self.ensure_owner()?;
        if self.state == RuntimeState::CrashLoopOpen {
            return Err(ProductDispatchError::CrashLoopOpen);
        }
        if self.actor.is_none() {
            return Err(ProductDispatchError::RecoveryRequired);
        }
        self.actor.take();
        self.state = RuntimeState::CrashLoopOpen;
        self.generation = self
            .generation
            .checked_next()
            .map_err(|_| ProductDispatchError::CrashLoopOpen)?;
        self.crashes = self
            .crashes
            .checked_add(1)
            .ok_or(ProductDispatchError::CrashLoopOpen)?;
        if self.crashes >= self.restart_policy.max_consecutive_crashes() {
            return Ok(());
        }
        self.state = if self.storage_failed || self.pending_reconciliation.is_some() {
            RuntimeState::ReplayReconciliationRequired
        } else {
            RuntimeState::NeedsReconstruction
        };
        Ok(())
    }

    pub fn acknowledge_stable_cycle(&mut self) {
        if self.ensure_owner().is_ok()
            && self.state == RuntimeState::Ready
            && !self.storage_failed
            && self.pending_reconciliation.is_none()
            && self.actor.is_some()
        {
            self.crashes = 0;
        }
    }

    /// Bind a fresh native owner endpoint after explicit recovery. The actor's
    /// fresh OS incarnation makes previous session/WebView references stale.
    pub fn reconstruct(
        &mut self,
        bootstrap: &AcceptedProductConnection,
        endpoint: ServoRuntimeEndpoint,
    ) -> Result<(), ProductDispatchError> {
        self.ensure_owner()?;
        if bootstrap.control.owner_pid != self.owner_pid {
            return Err(ProductDispatchError::PeerRefused);
        }
        bootstrap.ensure_control_current()?;
        if self.state == RuntimeState::CrashLoopOpen {
            return Err(ProductDispatchError::CrashLoopOpen);
        }
        if self.storage_failed
            || self.pending_reconciliation.is_some()
            || self.state != RuntimeState::NeedsReconstruction
        {
            return Err(ProductDispatchError::RecoveryRequired);
        }
        let actor = ServoBrowserActor::from_attested(
            self.principal.clone(),
            bootstrap.peer,
            &bootstrap.attestor,
            &bootstrap.attested,
            endpoint,
        )
        .map_err(|_| ProductDispatchError::PeerRefused)?;
        bootstrap.ensure_control_current()?;
        let observer = self
            .observer
            .borrow_mut()
            .take()
            .ok_or(ProductDispatchError::StorageUnavailable)?;
        let journal = match observer.into_journal() {
            Ok(journal) => journal,
            Err(_) => {
                self.storage_failed = true;
                return Err(ProductDispatchError::StorageUnavailable);
            }
        };
        *self.observer.borrow_mut() = Some(actor.receipt_observer(journal, self.image_id.clone()));
        self.actor = Some(actor);
        self.state = RuntimeState::Ready;
        Ok(())
    }
}

struct AttestedProductHandler<'a> {
    owner_pid: u32,
    actor: &'a mut ServoBrowserActor,
    attestor: &'a ProcfsPeerAttestor,
    attested: &'a AttestedPeer,
    observer: Rc<RefCell<Option<ReceiptLifecycleObserver>>>,
    trace: Rc<RefCell<OperationTrace>>,
    control: Arc<ConnectionControl>,
    prepared_request: Option<String>,
}
impl Drop for AttestedProductHandler<'_> {
    fn drop(&mut self) {
        if self.owner_pid != std::process::id() {
            return;
        }
        if let Some(request_id) = self.prepared_request.take() {
            let _ = self.actor.retire_prepared_request(&request_id);
            #[cfg(target_os = "linux")]
            if let Some(custody) = &self.control.custodian {
                let _ = custody.revoke();
            }
        }
    }
}
impl BrowserRequestHandler for AttestedProductHandler<'_> {
    fn preflight(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
    ) -> Result<Option<BrowserWireError>, AgentPortError> {
        product_owner(self.owner_pid)?;
        self.prepared_request = Some(request.request_id.clone());
        let cancellation = self.actor.active_cancellation_token(&request.request_id);
        let result = (|| {
            if self.control.cancelled.load(Ordering::SeqCst) {
                return Ok(Some(refusal(
                    BrowserErrorCode::Cancelled,
                    "connection cancelled before admission",
                )));
            }
            #[cfg(target_os = "linux")]
            if let Some(custody) = &self.control.custodian {
                context.remaining()?;
                if self.attested.refresh_snapshot(self.attestor).is_err() {
                    let _ = custody.revoke();
                    return Ok(Some(refusal(
                        BrowserErrorCode::PolicyDenied,
                        "original Agent refused",
                    )));
                }
                context.remaining()?;
            }
            #[cfg(target_os = "linux")]
            let custodian = self
                .control
                .custodian
                .as_ref()
                .map(|value| value.verifier())
                .transpose()
                .map_err(|_| AgentPortError::Handler("control custodian refused".into()))?;
            #[cfg(target_os = "linux")]
            let admission = if let Some(verifier) = &custodian {
                self.actor.preflight_attested_controlled(
                    context,
                    request,
                    self.attestor,
                    self.attested,
                    verifier,
                )?
            } else {
                self.actor
                    .preflight_attested(context, request, self.attestor, self.attested)?
            };
            #[cfg(not(target_os = "linux"))]
            let admission =
                self.actor
                    .preflight_attested(context, request, self.attestor, self.attested)?;
            if let Some(error) = admission {
                return Ok(Some(error));
            }
            let mut observer = self.observer.borrow_mut();
            let observer = observer.as_mut().ok_or_else(storage_error)?;
            match observer.contains_receipt(&request.request_id) {
                Ok(true) => {
                    return Ok(Some(refusal(
                        BrowserErrorCode::PolicyDenied,
                        "request identity already exists in durable history; replay refused",
                    )));
                }
                Ok(false) => (),
                Err(_) => {
                    self.trace.borrow_mut().storage_failed = true;
                    return Err(storage_error());
                }
            }
            self.trace.borrow_mut().request = Some(RequestIdentity {
                id: request.request_id.clone(),
                digest: request_digest(context)?,
            });
            Ok(None)
        })();
        if !matches!(result, Ok(None)) {
            self.actor.retire_prepared_request(&request.request_id)?;
            self.prepared_request.take();
            if let Some(token) = cancellation {
                token.cancel();
            }
            #[cfg(target_os = "linux")]
            if let Some(custody) = &self.control.custodian {
                let _ = custody.revoke();
            }
        }
        result
    }

    fn handle(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
    ) -> Result<HandlerOutcome, AgentPortError> {
        product_owner(self.owner_pid)?;
        self.prepared_request = Some(request.request_id.clone());
        let cancellation = self.actor.cancellation_token(request.request_id.clone());
        let result = (|| {
            let mut active = self.control.active.lock().map_err(|_| {
                AgentPortError::Handler("connection cancellation state unavailable".into())
            })?;
            if self.control.cancelled.load(Ordering::SeqCst) {
                cancellation.cancel();
            }
            *active = Some(cancellation.clone());
            drop(active);
            #[cfg(target_os = "linux")]
            if let Some(custody) = &self.control.custodian {
                context.remaining()?;
                if self.attested.refresh_snapshot(self.attestor).is_err() {
                    let _ = custody.revoke();
                    return Ok(HandlerOutcome::Failure(refusal(
                        BrowserErrorCode::PolicyDenied,
                        "original Agent refused before controlled dispatch",
                    )));
                }
                context.remaining()?;
                let verifier = custody
                    .verifier()
                    .map_err(|_| AgentPortError::Handler("control custodian refused".into()))?;
                return self.actor.handle_attested_controlled(
                    context,
                    request,
                    self.attestor,
                    self.attested,
                    &verifier,
                );
            }
            self.actor
                .handle_attested(context, request, self.attestor, self.attested)
        })();
        self.actor.retire_prepared_request(&request.request_id)?;
        self.prepared_request.take();
        cancellation.cancel();
        #[cfg(target_os = "linux")]
        if !matches!(&result, Ok(HandlerOutcome::Success(_)))
            && let Some(custody) = &self.control.custodian
        {
            let _ = custody.revoke();
        }
        result
    }
}

struct DurableProductLifecycle {
    owner_pid: u32,
    observer: Rc<RefCell<Option<ReceiptLifecycleObserver>>>,
    trace: Rc<RefCell<OperationTrace>>,
}
impl DurableProductLifecycle {
    fn apply(
        &mut self,
        operation: impl FnOnce(&mut ReceiptLifecycleObserver) -> Result<(), AgentPortError>,
    ) -> Result<(), AgentPortError> {
        product_owner(self.owner_pid)?;
        let mut observer = self.observer.borrow_mut();
        let result = operation(observer.as_mut().ok_or_else(storage_error)?);
        if result.is_err() {
            self.trace.borrow_mut().storage_failed = true;
        }
        result
    }
    fn terminal(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
    ) -> Result<(), AgentPortError> {
        product_owner(self.owner_pid)?;
        let digest = request_digest(context)?;
        let mut observer = self.observer.borrow_mut();
        let fact = observer
            .as_mut()
            .ok_or_else(storage_error)?
            .receipt_fact(&request.request_id, digest);
        match fact.and_then(|fact| Ok((fact.lifecycle()?, fact.record_sha256()?))) {
            Ok((lifecycle, record)) => {
                self.trace.borrow_mut().terminal = Some(lifecycle);
                self.trace.borrow_mut().terminal_record = Some(record);
                Ok(())
            }
            Err(_) => {
                self.trace.borrow_mut().storage_failed = true;
                Err(storage_error())
            }
        }
    }
}
impl OperationLifecycleObserver for DurableProductLifecycle {
    fn requested(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
    ) -> Result<(), AgentPortError> {
        product_owner(self.owner_pid)?;
        self.apply(|observer| observer.requested(context, request))?;
        self.trace.borrow_mut().requested = true;
        Ok(())
    }
    fn dispatched(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
    ) -> Result<(), AgentPortError> {
        self.apply(|observer| observer.dispatched(context, request))?;
        self.trace.borrow_mut().dispatched = true;
        Ok(())
    }
    fn completed(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
        response: &BrowserResponse,
        digest: &str,
    ) -> Result<(), AgentPortError> {
        product_owner(self.owner_pid)?;
        if response.outcome.as_ref().err().is_some_and(|error| {
            matches!(
                error.code,
                BrowserErrorCode::Indeterminate | BrowserErrorCode::BrowserCrashed
            )
        }) {
            self.trace.borrow_mut().uncertain = true;
        }
        self.apply(|observer| observer.completed(context, request, response, digest))?;
        self.terminal(context, request)
    }
    fn interrupted(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
        error: &AgentPortError,
    ) -> Result<(), AgentPortError> {
        self.apply(|observer| observer.interrupted(context, request, error))?;
        self.terminal(context, request)
    }
}

fn refusal(code: BrowserErrorCode, message: &str) -> BrowserWireError {
    BrowserWireError {
        code,
        message: message.into(),
        details: None,
    }
}
fn storage_error() -> AgentPortError {
    AgentPortError::Handler("product receipt storage requires recovery".into())
}
fn product_owner(owner_pid: u32) -> Result<(), AgentPortError> {
    if std::process::id() != owner_pid {
        return Err(AgentPortError::Handler(
            "product owner process changed".into(),
        ));
    }
    Ok(())
}
fn request_digest(context: &DispatchContext) -> Result<Digest, AgentPortError> {
    let text = context.canonical_request_sha256.as_bytes();
    if text.len() != 64 {
        return Err(AgentPortError::Handler(
            "invalid canonical request digest".into(),
        ));
    }
    let mut digest = [0; 32];
    for (byte, pair) in digest.iter_mut().zip(text.chunks_exact(2)) {
        let nibble = |value| match value {
            b'0'..=b'9' => Some(value - b'0'),
            b'a'..=b'f' => Some(value - b'a' + 10),
            _ => None,
        };
        *byte = nibble(pair[0])
            .zip(nibble(pair[1]))
            .map(|(high, low)| high * 16 + low)
            .ok_or_else(|| AgentPortError::Handler("invalid canonical request digest".into()))?;
    }
    Ok(digest)
}

#[cfg(test)]
#[path = "product_dispatch/tests.rs"]
mod tests;
