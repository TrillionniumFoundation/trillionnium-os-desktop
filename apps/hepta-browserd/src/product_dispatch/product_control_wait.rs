//! A private journal seal connects one retained control channel to one actual
//! coordinator invocation. No public boolean, hash, response status or external
//! DurableReceiptFact can enter the seal path.

use super::*;
use hepta_agent_transport::{RemoteRetirementReport, RemoteTerminalState};
use hepta_peer_attestation::{AttestedRetainedReceiver, ControlRetainedAcceptedStream};

// Neither a public constructor nor a public sending interface is exposed.
struct SealedTerminal {
    owner_pid: u32,
    deadline: Instant,
    request: RequestIdentity,
    lifecycle: ReceiptLifecycleState,
    record_sha256: Digest,
}
enum MonitorMessage {
    Terminal(SealedTerminal),
    NoTerminal,
}

/// One original accepted connection and a private single-use terminal link.
/// Only actual default-live retained handoff admission constructs this value.
///
/// ```compile_fail,E0432
/// use hepta_browserd::SealedTerminal;
/// ```
///
/// ```compile_fail
/// use hepta_browserd::RetainedProductConnection;
/// fn clone_required<T: Clone>() {}
/// clone_required::<RetainedProductConnection>();
/// ```
pub struct RetainedProductConnection {
    owner_pid: u32,
    connection: Option<AcceptedProductConnection>,
    terminal: Option<mpsc::SyncSender<MonitorMessage>>,
    deadline: Instant,
    report_deadline: Instant,
}
impl RetainedProductConnection {
    pub fn from_control_retained_received(
        received: ControlRetainedAcceptedStream,
        policy: &PeerRuntimePolicy,
        approved_executable_sha256: &str,
    ) -> Result<(Self, ProductControlMonitor), ProductDispatchError> {
        received.deadline().map_err(control_error)?;
        if approved_executable_sha256.len() != 64
            || !approved_executable_sha256
                .bytes()
                .all(|value| value.is_ascii_digit() || (b'a'..=b'f').contains(&value))
        {
            return Err(ProductDispatchError::InvalidConfiguration);
        }
        received
            .consume_before(|stream, deadline, custody, mut retained| {
                let report_deadline = retained.ensure_current().map_err(control_error)?;
                let verifier = custody.verifier().map_err(control_error)?;
                verifier.verify_current().map_err(control_error)?;
                let mut connection = AcceptedProductConnection::attest_before(
                    stream,
                    ProcfsPeerAttestor::default(),
                    policy,
                    deadline,
                )?;
                if connection.attested.snapshot().executable_sha256 != approved_executable_sha256 {
                    return Err(ProductDispatchError::PeerRefused);
                }
                Arc::get_mut(&mut connection.control)
                    .ok_or(ProductDispatchError::PeerRefused)?
                    .custodian = Some(custody);
                connection.ensure_control_current()?;
                retained.ensure_current().map_err(control_error)?;
                let cancellation = connection.cancellation();
                let (sender, receiver) = mpsc::sync_channel(1);
                let owner_pid = std::process::id();
                Ok((
                    Self {
                        owner_pid,
                        connection: Some(connection),
                        terminal: Some(sender),
                        deadline,
                        report_deadline: deadline.min(report_deadline),
                    },
                    ProductControlMonitor {
                        owner_pid,
                        deadline: deadline.min(report_deadline),
                        retained: Some(retained),
                        cancellation,
                        receiver: Some(receiver),
                        finished: false,
                    },
                ))
            })
            .map_err(control_error)?
    }
    pub fn deadline(&self) -> Result<Instant, ProductDispatchError> {
        if self.owner_pid != std::process::id() {
            return Err(ProductDispatchError::PeerRefused);
        }
        self.connection
            .as_ref()
            .ok_or(ProductDispatchError::Closed)?
            .deadline()
    }
    pub fn cancellation(&self) -> Result<ProductConnectionCancellation, ProductDispatchError> {
        self.deadline()?;
        Ok(self
            .connection
            .as_ref()
            .ok_or(ProductDispatchError::Closed)?
            .cancellation())
    }
}
impl Drop for RetainedProductConnection {
    fn drop(&mut self) {
        if self.owner_pid != std::process::id() {
            // Do not run a std channel destructor against an inherited mutex.
            // This child-only heap reference is left to process retirement;
            // the accepted/socket owners still close only their FD copies.
            std::mem::forget(self.terminal.take());
        }
    }
}

/// This outcome concerns control packet enqueue only. It asserts neither
/// application-response delivery nor known effect success.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProductControlMonitorOutcome {
    ReportEnqueued,
    NoTerminal,
}

/// Move to one same-process I/O worker and run while the actor worker serves
/// the connection. No thread is started or unbounded join performed by Drop.
pub struct ProductControlMonitor {
    owner_pid: u32,
    deadline: Instant,
    retained: Option<AttestedRetainedReceiver>,
    cancellation: ProductConnectionCancellation,
    receiver: Option<mpsc::Receiver<MonitorMessage>>,
    finished: bool,
}
impl ProductControlMonitor {
    pub fn run(mut self) -> Result<ProductControlMonitorOutcome, ProductDispatchError> {
        if self.owner_pid != std::process::id() {
            return Err(ProductDispatchError::PeerRefused);
        }
        loop {
            product_time_remaining(self.deadline)?;
            let retained = self.retained.as_mut().ok_or(ProductDispatchError::Closed)?;
            retained.ensure_current().map_err(control_error)?;
            if retained.poll_cancel().map_err(control_error)? {
                self.cancellation.cancel();
            }
            let wait = product_time_remaining(self.deadline)?.min(Duration::from_millis(5));
            if self.owner_pid != std::process::id() {
                return Err(ProductDispatchError::PeerRefused);
            }
            match self
                .receiver
                .as_ref()
                .ok_or(ProductDispatchError::Closed)?
                .recv_timeout(wait)
            {
                Ok(MonitorMessage::Terminal(seal)) => {
                    if self.owner_pid != std::process::id()
                        || seal.owner_pid != self.owner_pid
                        || seal.deadline != self.deadline
                    {
                        return Err(ProductDispatchError::PeerRefused);
                    }
                    product_time_remaining(self.deadline)?;
                    let state = match seal.lifecycle {
                        ReceiptLifecycleState::Completed => RemoteTerminalState::Completed,
                        ReceiptLifecycleState::Interrupted => RemoteTerminalState::Interrupted,
                        ReceiptLifecycleState::Indeterminate => RemoteTerminalState::Indeterminate,
                        _ => return Err(ProductDispatchError::StorageUnavailable),
                    };
                    let report =
                        RemoteRetirementReport::new(state, seal.request.digest, seal.record_sha256)
                            .map_err(|_| ProductDispatchError::StorageUnavailable)?;
                    retained.send_remote_report(report).map_err(control_error)?;
                    self.finished = true;
                    return Ok(ProductControlMonitorOutcome::ReportEnqueued);
                }
                Ok(MonitorMessage::NoTerminal) => {
                    self.cancellation.cancel();
                    self.finished = true;
                    return Ok(ProductControlMonitorOutcome::NoTerminal);
                }
                Err(mpsc::RecvTimeoutError::Timeout) => (),
                Err(mpsc::RecvTimeoutError::Disconnected) => {
                    return Err(ProductDispatchError::Closed);
                }
            }
        }
    }
}
impl Drop for ProductControlMonitor {
    fn drop(&mut self) {
        if self.owner_pid != std::process::id() {
            std::mem::forget(self.receiver.take());
        } else if !self.finished {
            self.cancellation.cancel();
        }
        // Dropping the retained peer owner revokes action verifiers and closes
        // only this process's control descriptor copies. No join or shutdown
        // of a parent's control channel is attempted after fork.
    }
}

impl ProductRequestCoordinator {
    pub fn from_retained_connection(
        principal: TaskFlowPrincipal,
        bootstrap: &RetainedProductConnection,
        endpoint: ServoRuntimeEndpoint,
        journal: ReceiptJournal,
        image_id: String,
        restart_policy: RestartPolicy,
    ) -> Result<Self, ProductDispatchError> {
        bootstrap.deadline()?;
        Self::from_connection(
            principal,
            bootstrap
                .connection
                .as_ref()
                .ok_or(ProductDispatchError::Closed)?,
            endpoint,
            journal,
            image_id,
            restart_policy,
        )
    }

    /// Only this coordinator's current invocation can produce the private
    /// terminal token. Public ServiceEvidence remains diagnostic data.
    pub fn serve_retained_connection(
        &mut self,
        mut connection: RetainedProductConnection,
    ) -> Result<ServiceEvidence, ProductDispatchError> {
        self.ensure_owner()?;
        if connection.owner_pid != self.owner_pid {
            return Err(ProductDispatchError::PeerRefused);
        }
        connection.deadline()?;
        let sender = connection
            .terminal
            .take()
            .ok_or(ProductDispatchError::Closed)?;
        let accepted = connection
            .connection
            .take()
            .ok_or(ProductDispatchError::Closed)?;
        // The report wait can conservatively expire before the original
        // accepted ceiling; neither ceiling is renewed here.
        let deadline = connection.report_deadline;
        product_time_remaining(connection.deadline)?;
        self.last_retirement = None;
        let result = self.serve_connection(accepted);
        // serve_connection has retired preparation and the original accepted
        // owner's action custody before this new reporting-only phase.
        if let Some((request, lifecycle, record)) = self.last_retirement.take() {
            self.ensure_owner()?;
            product_time_remaining(deadline)?;
            let fact = self
                .observer
                .borrow_mut()
                .as_mut()
                .ok_or(ProductDispatchError::StorageUnavailable)?
                .receipt_fact(&request.id, request.digest);
            let fact = match fact {
                Ok(fact) => fact,
                Err(_) => {
                    self.storage_failed = true;
                    self.state = RuntimeState::ReplayReconciliationRequired;
                    self.pending_reconciliation = Some(request);
                    return Err(ProductDispatchError::StorageUnavailable);
                }
            };
            if !lifecycle.is_terminal()
                || fact
                    .lifecycle()
                    .map_err(|_| ProductDispatchError::StorageUnavailable)?
                    != lifecycle
                || fact
                    .request_sha256()
                    .map_err(|_| ProductDispatchError::StorageUnavailable)?
                    != request.digest
                || fact
                    .receipt_id()
                    .map_err(|_| ProductDispatchError::StorageUnavailable)?
                    != request.id
                || fact
                    .record_sha256()
                    .map_err(|_| ProductDispatchError::StorageUnavailable)?
                    != record
            {
                self.storage_failed = true;
                self.state = RuntimeState::ReplayReconciliationRequired;
                self.pending_reconciliation = Some(request);
                return Err(ProductDispatchError::StorageUnavailable);
            }
            product_time_remaining(deadline)?;
            sender
                .try_send(MonitorMessage::Terminal(SealedTerminal {
                    owner_pid: self.owner_pid,
                    deadline,
                    request,
                    lifecycle,
                    record_sha256: record,
                }))
                .map_err(|_| ProductDispatchError::Closed)?;
        } else {
            sender
                .try_send(MonitorMessage::NoTerminal)
                .map_err(|_| ProductDispatchError::Closed)?;
        }
        result
    }
}
