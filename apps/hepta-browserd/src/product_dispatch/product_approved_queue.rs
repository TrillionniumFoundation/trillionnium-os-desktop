//! Opaque configured admission pairing. This is a queue/worker composition,
//! never evidence that a supplied endpoint executes native Servo.

use super::*;
use hepta_peer_attestation::{ApprovedAgentSelection, ControlRetainedAcceptedStream};
use std::sync::TryLockError;
use std::thread;

/// One original approved stream and its exact private terminal monitor.
/// No public extraction, reconstruction or Clone can separate these owners.
pub struct ApprovedRetainedAdmission {
    owner_pid: u32,
    original_deadline: Instant,
    connection: Option<ApprovedRetainedProductConnection>,
    monitor: Option<ProductControlMonitor>,
    queue: Option<Arc<QueueState>>,
}
impl ApprovedRetainedAdmission {
    /// Creator check only, before passing inherited native/channel arguments
    /// to composition. This does not attest a peer or approve an operation.
    pub fn ensure_creating_process(&self) -> Result<(), ProductDispatchError> {
        creating(self.owner_pid)
    }
    pub fn from_received(
        received: ControlRetainedAcceptedStream,
        selection: ApprovedAgentSelection,
    ) -> Result<Self, ProductDispatchError> {
        let (connection, monitor) =
            ApprovedRetainedProductConnection::from_received(received, selection)?;
        let original_deadline = connection.deadline()?;
        Ok(Self {
            owner_pid: std::process::id(),
            original_deadline,
            connection: Some(connection),
            monitor: Some(monitor),
            queue: None,
        })
    }
    pub fn deadline(&self) -> Result<Instant, ProductDispatchError> {
        creating(self.owner_pid)?;
        if let Some(queue) = &self.queue {
            queue.current()?;
        }
        let current = self
            .connection
            .as_ref()
            .ok_or(ProductDispatchError::Closed)?
            .deadline()?;
        if current != self.original_deadline {
            return Err(ProductDispatchError::PeerRefused);
        }
        product_time_remaining(self.original_deadline)?;
        Ok(self.original_deadline)
    }
    pub fn cancellation(&self) -> Result<ProductConnectionCancellation, ProductDispatchError> {
        self.deadline()?;
        self.connection
            .as_ref()
            .ok_or(ProductDispatchError::Closed)?
            .cancellation()
    }

    // This private observation is not complete executable attestation. It
    // rechecks the retained root/path, both original pidfds and cancellation
    // without extending either scope or changing the first Instant.
    fn original_scope(&self) -> Result<Instant, ProductDispatchError> {
        creating(self.owner_pid)?;
        if let Some(queue) = &self.queue {
            queue.current()?;
        }
        let current = self
            .connection
            .as_ref()
            .ok_or(ProductDispatchError::Closed)?
            .original_scope()?;
        if current != self.original_deadline {
            return Err(ProductDispatchError::PeerRefused);
        }
        product_time_remaining(self.original_deadline)?;
        Ok(self.original_deadline)
    }

    fn original_cancellation(&self) -> Result<ProductConnectionCancellation, ProductDispatchError> {
        self.original_scope()?;
        self.connection
            .as_ref()
            .ok_or(ProductDispatchError::Closed)?
            .original_cancellation()
    }
    /// Generic composition only. The concrete native driver supplies its
    /// privately constructed immutable endpoint; this method grants no native
    /// or effect-success claim to an arbitrary caller-supplied endpoint.
    pub fn coordinator(
        &self,
        endpoint: ServoRuntimeEndpoint,
        journal: ReceiptJournal,
        image_id: String,
    ) -> Result<ProductRequestCoordinator, ProductDispatchError> {
        self.original_scope()?;
        let value = ProductRequestCoordinator::from_approved_retained_connection(
            self.connection
                .as_ref()
                .ok_or(ProductDispatchError::Closed)?,
            endpoint,
            journal,
            image_id,
            RestartPolicy::new(1).map_err(|_| ProductDispatchError::InvalidConfiguration)?,
        )?;
        self.deadline()?;
        Ok(value)
    }
    /// Consume the same pair exactly once. Only the original coordinator's
    /// existing private own-journal seal can make a terminal control report.
    /// The returned observation is diagnostic data, never such a seal.
    pub fn serve(
        mut self,
        coordinator: &mut ProductRequestCoordinator,
    ) -> Result<ApprovedRetainedObservation, ProductDispatchError> {
        let deadline = self.deadline()?;
        coordinator.ensure_owner()?;
        let cancellation = self.original_cancellation()?;
        let active = match &self.queue {
            Some(queue) => Some(queue.activate(cancellation.clone())?),
            None => None,
        };
        self.original_scope()?;
        let monitor = self.monitor.take().ok_or(ProductDispatchError::Closed)?;
        let mut worker = ReportWorker {
            owner_pid: self.owner_pid,
            receiver: None,
            thread: None,
        };
        let (sender, receiver) = mpsc::sync_channel(1);
        worker.receiver = Some(receiver);
        // The complete admission checks precede allocation/spawn. Spawn failure
        // drops this same monitor, whose existing Drop revokes the original.
        self.deadline()?;
        worker.thread = Some(
            thread::Builder::new()
                .name("hepta-approved-report".into())
                .spawn(move || {
                    let result = monitor.run();
                    let _ = sender.try_send(result);
                })
                .map_err(|_| ProductDispatchError::DispatchFailed)?,
        );
        let service = match self.deadline() {
            Ok(_) => coordinator.serve_approved_retained_connection(
                self.connection.take().ok_or(ProductDispatchError::Closed)?,
            ),
            Err(error) => {
                let _ = try_cancel_original(&cancellation);
                Err(error)
            }
        };
        // No duration is restarted after serving or while waiting for a report.
        let report = loop {
            creating(self.owner_pid)?;
            let remaining = match product_time_remaining(deadline) {
                Ok(value) => value,
                Err(error) => {
                    let _ = try_cancel_original(&cancellation);
                    break Err(error);
                }
            };
            match worker.receive(remaining.min(Duration::from_millis(5)))? {
                Ok(value) => break value,
                Err(mpsc::RecvTimeoutError::Timeout) => (),
                Err(mpsc::RecvTimeoutError::Disconnected) => {
                    let _ = try_cancel_original(&cancellation);
                    break Err(ProductDispatchError::Closed);
                }
            }
        };
        // Dropping a JoinHandle detaches; Drop never joins an unbounded worker.
        // Its original monitor ceiling remains fixed, including after errors.
        drop(worker);
        drop(active);
        Ok(ApprovedRetainedObservation {
            original_deadline: deadline,
            service,
            report,
            runtime_state: coordinator.state(),
        })
    }
}

struct ReportWorker {
    owner_pid: u32,
    receiver: Option<mpsc::Receiver<Result<ProductControlMonitorOutcome, ProductDispatchError>>>,
    thread: Option<thread::JoinHandle<()>>,
}
impl ReportWorker {
    fn receive(
        &self,
        remaining: Duration,
    ) -> Result<
        Result<Result<ProductControlMonitorOutcome, ProductDispatchError>, mpsc::RecvTimeoutError>,
        ProductDispatchError,
    > {
        creating(self.owner_pid)?;
        Ok(self
            .receiver
            .as_ref()
            .ok_or(ProductDispatchError::Closed)?
            .recv_timeout(remaining))
    }
}
impl Drop for ReportWorker {
    fn drop(&mut self) {
        if creating(self.owner_pid).is_err() {
            std::mem::forget(self.receiver.take());
            std::mem::forget(self.thread.take());
        }
        // Local JoinHandle destruction detaches, never joins.
    }
}

/// Local diagnostics. No method admits work, clears uncertainty or mints a
/// durable terminal token. A report enqueue is not Agent delivery/effect success.
pub struct ApprovedRetainedObservation {
    original_deadline: Instant,
    service: Result<ServiceEvidence, ProductDispatchError>,
    report: Result<ProductControlMonitorOutcome, ProductDispatchError>,
    runtime_state: RuntimeState,
}
impl ApprovedRetainedObservation {
    pub fn original_deadline(&self) -> Instant {
        self.original_deadline
    }
    pub fn service(&self) -> &Result<ServiceEvidence, ProductDispatchError> {
        &self.service
    }
    pub fn report(&self) -> &Result<ProductControlMonitorOutcome, ProductDispatchError> {
        &self.report
    }
    pub fn runtime_state(&self) -> RuntimeState {
        self.runtime_state
    }
}

struct QueueState {
    owner_pid: u32,
    ceiling: Option<Instant>,
    retired: AtomicBool,
    active: Mutex<Option<ProductConnectionCancellation>>,
}
impl QueueState {
    fn current(&self) -> Result<(), ProductDispatchError> {
        creating(self.owner_pid)?;
        if let Some(ceiling) = self.ceiling {
            product_time_remaining(ceiling)?;
        }
        if self.retired.load(Ordering::SeqCst) {
            Err(ProductDispatchError::Closed)
        } else {
            Ok(())
        }
    }
    fn activate(
        self: &Arc<Self>,
        cancellation: ProductConnectionCancellation,
    ) -> Result<ActiveAdmission, ProductDispatchError> {
        self.current()?;
        let mut active = self
            .active
            .try_lock()
            .map_err(|_| ProductDispatchError::QueueFull)?;
        self.current()?;
        if active.is_some() {
            return Err(ProductDispatchError::QueueFull);
        }
        *active = Some(cancellation.clone());
        drop(active);
        let guard = ActiveAdmission {
            state: self.clone(),
            cancellation,
        };
        if let Err(error) = self.current() {
            let _ = try_cancel_original(&guard.cancellation);
            return Err(error);
        }
        Ok(guard)
    }
}
struct ActiveAdmission {
    state: Arc<QueueState>,
    cancellation: ProductConnectionCancellation,
}
impl Drop for ActiveAdmission {
    fn drop(&mut self) {
        if creating(self.state.owner_pid).is_err() {
            return;
        }
        match self.state.active.try_lock() {
            Ok(mut active) => {
                if active
                    .as_ref()
                    .is_some_and(|value| Arc::ptr_eq(&value.0, &self.cancellation.0))
                {
                    active.take();
                }
            }
            Err(_) => {
                // Cleanup uncertainty permanently closes this queue. No stale
                // registry entry can be silently treated as a fresh slot.
                self.state.retired.store(true, Ordering::SeqCst);
                let _ = try_cancel_original(&self.cancellation);
            }
        }
    }
}
fn creating(pid: u32) -> Result<(), ProductDispatchError> {
    if pid == std::process::id() {
        Ok(())
    } else {
        Err(ProductDispatchError::PeerRefused)
    }
}

// This additive path requests real denial without waiting for the old public
// cancellation method's mutexes. Requested is not a completed I/O barrier:
// already admitted native calls and old destructors remain non-preemptible.
fn try_cancel_original(
    cancellation: &ProductConnectionCancellation,
) -> Result<ApprovedQueueRetirementState, ProductDispatchError> {
    creating(cancellation.0.owner_pid)?;
    cancellation.0.cancelled.store(true, Ordering::SeqCst);
    if let Some(custodian) = &cancellation.0.custodian {
        custodian.revoke().map_err(control_error)?;
    }
    let mut pending = false;
    match cancellation.0.active.try_lock() {
        Ok(active) => {
            if let Some(token) = active.as_ref() {
                token.cancel();
            }
        }
        Err(_) => pending = true,
    }
    match cancellation.0.transport.try_lock() {
        Ok(transport) => {
            if let Some(stream) = transport.as_ref()
                && stream.shutdown(Shutdown::Both).is_err()
            {
                pending = true;
            }
        }
        Err(_) => pending = true,
    }
    Ok(if pending {
        ApprovedQueueRetirementState::Requested
    } else {
        ApprovedQueueRetirementState::ActiveCancellationIssued
    })
}

pub struct ApprovedRetainedIngress {
    state: Arc<QueueState>,
    sender: Option<mpsc::SyncSender<ApprovedRetainedAdmission>>,
}
pub struct ApprovedRetainedQueue {
    state: Arc<QueueState>,
    receiver: Option<mpsc::Receiver<ApprovedRetainedAdmission>>,
}
/// Denial only. This never resets its latch or provides dispatch/terminal data.
pub struct ApprovedQueueRetirement(Arc<QueueState>);
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ApprovedQueueRetirementState {
    Requested,
    ActiveCancellationIssued,
}
pub fn approved_retained_queue() -> (
    ApprovedRetainedIngress,
    ApprovedRetainedQueue,
    ApprovedQueueRetirement,
) {
    queue_with_ceiling(None)
}
/// A fixed outer ceiling cannot extend any packet's original custody deadline.
/// The concrete native driver uses its first admitted packet's exact ceiling.
pub fn approved_retained_queue_before(
    ceiling: Instant,
) -> Result<
    (
        ApprovedRetainedIngress,
        ApprovedRetainedQueue,
        ApprovedQueueRetirement,
    ),
    ProductDispatchError,
> {
    product_time_remaining(ceiling)?;
    Ok(queue_with_ceiling(Some(ceiling)))
}
fn queue_with_ceiling(
    ceiling: Option<Instant>,
) -> (
    ApprovedRetainedIngress,
    ApprovedRetainedQueue,
    ApprovedQueueRetirement,
) {
    let (sender, receiver) = mpsc::sync_channel(1);
    let state = Arc::new(QueueState {
        owner_pid: std::process::id(),
        ceiling,
        retired: AtomicBool::new(false),
        active: Mutex::new(None),
    });
    (
        ApprovedRetainedIngress {
            state: state.clone(),
            sender: Some(sender),
        },
        ApprovedRetainedQueue {
            state: state.clone(),
            receiver: Some(receiver),
        },
        ApprovedQueueRetirement(state),
    )
}
impl ApprovedRetainedIngress {
    pub fn try_submit(
        &self,
        mut admission: ApprovedRetainedAdmission,
    ) -> Result<ProductConnectionCancellation, ProductDispatchError> {
        self.state.current()?;
        let deadline = admission.deadline()?;
        if self.state.ceiling.is_some_and(|ceiling| deadline > ceiling) {
            return Err(ProductDispatchError::DeadlineExceeded);
        }
        if admission.queue.is_some() {
            return Err(ProductDispatchError::PeerRefused);
        }
        let cancellation = admission.original_cancellation()?;
        admission.queue = Some(self.state.clone());
        admission.deadline()?;
        match self
            .sender
            .as_ref()
            .ok_or(ProductDispatchError::Closed)?
            .try_send(admission)
        {
            Ok(()) => Ok(cancellation),
            Err(mpsc::TrySendError::Full(_)) => Err(ProductDispatchError::QueueFull),
            Err(mpsc::TrySendError::Disconnected(_)) => Err(ProductDispatchError::Closed),
        }
    }
}
impl ApprovedRetainedQueue {
    pub fn try_next(&mut self) -> Result<Option<ApprovedRetainedAdmission>, ProductDispatchError> {
        self.state.current()?;
        match self
            .receiver
            .as_ref()
            .ok_or(ProductDispatchError::Closed)?
            .try_recv()
        {
            Ok(admission) => {
                if !admission
                    .queue
                    .as_ref()
                    .is_some_and(|state| Arc::ptr_eq(state, &self.state))
                {
                    return Err(ProductDispatchError::PeerRefused);
                }
                admission.deadline()?;
                Ok(Some(admission))
            }
            Err(mpsc::TryRecvError::Empty) => Ok(None),
            Err(mpsc::TryRecvError::Disconnected) => Err(ProductDispatchError::Closed),
        }
    }
}
impl ApprovedQueueRetirement {
    pub fn is_requested(&self) -> Result<bool, ProductDispatchError> {
        creating(self.0.owner_pid)?;
        Ok(self.0.retired.load(Ordering::SeqCst))
    }
    pub fn request(&self) -> Result<ApprovedQueueRetirementState, ProductDispatchError> {
        creating(self.0.owner_pid)?;
        self.0.retired.store(true, Ordering::SeqCst);
        let cancellation = match self.0.active.try_lock() {
            Ok(active) => active.clone(),
            Err(TryLockError::WouldBlock) => return Ok(ApprovedQueueRetirementState::Requested),
            Err(TryLockError::Poisoned(_)) => return Err(ProductDispatchError::RecoveryRequired),
        };
        if let Some(cancellation) = cancellation {
            return try_cancel_original(&cancellation);
        }
        Ok(ApprovedQueueRetirementState::ActiveCancellationIssued)
    }
}
impl Drop for ApprovedRetainedIngress {
    fn drop(&mut self) {
        if creating(self.state.owner_pid).is_err() {
            std::mem::forget(self.sender.take());
        }
    }
}
impl Drop for ApprovedRetainedQueue {
    fn drop(&mut self) {
        if creating(self.state.owner_pid).is_err() {
            std::mem::forget(self.receiver.take());
        } else {
            self.state.retired.store(true, Ordering::SeqCst);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Read;

    fn cancellation() -> (ProductConnectionCancellation, UnixStream) {
        let (server, client) = UnixStream::pair().unwrap();
        let control = ConnectionControl {
            owner_pid: std::process::id(),
            transport: Mutex::new(Some(server)),
            ..ConnectionControl::default()
        };
        (ProductConnectionCancellation(Arc::new(control)), client)
    }
    #[test]
    fn contended_transport_is_requested_and_real_retry_retires_original_fd() {
        let (cancellation, mut client) = cancellation();
        let held = cancellation.0.transport.lock().unwrap();
        let before = Instant::now();
        assert_eq!(
            try_cancel_original(&cancellation),
            Ok(ApprovedQueueRetirementState::Requested)
        );
        assert!(before.elapsed() < Duration::from_millis(50));
        assert!(cancellation.0.cancelled.load(Ordering::SeqCst));
        drop(held);
        assert_eq!(
            try_cancel_original(&cancellation),
            Ok(ApprovedQueueRetirementState::ActiveCancellationIssued)
        );
        client
            .set_read_timeout(Some(Duration::from_millis(50)))
            .unwrap();
        assert_eq!(client.read(&mut [0]).unwrap(), 0);
    }
    #[test]
    fn contended_registry_requests_without_waiting_or_claiming_completion() {
        let (ingress, queue, retirement) = approved_retained_queue();
        let held = retirement.0.active.lock().unwrap();
        let before = Instant::now();
        assert_eq!(
            retirement.request(),
            Ok(ApprovedQueueRetirementState::Requested)
        );
        assert!(before.elapsed() < Duration::from_millis(50));
        assert!(retirement.is_requested().unwrap());
        drop(held);
        assert_eq!(
            retirement.request(),
            Ok(ApprovedQueueRetirementState::ActiveCancellationIssued)
        );
        assert_eq!(ingress.state.current(), Err(ProductDispatchError::Closed));
        drop(queue);
    }
}
