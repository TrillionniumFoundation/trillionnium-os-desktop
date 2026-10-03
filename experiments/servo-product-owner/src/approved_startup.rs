//! Concrete same-process startup for the closed immutable native owner.
//! No listener, policy loader, observed self-approval or installed activation.
use crate::native_owner::{ClosedImmutableNativeOwner, NativeDrive, NativeOwnerError};
use hepta_browser_actor::ServoEventLoopWaker;
use hepta_browserd::{
    ApprovedQueueRetirement, ApprovedQueueRetirementState, ApprovedRetainedAdmission,
    ApprovedRetainedIngress, ApprovedRetainedObservation, ProductDispatchError, RuntimeState,
    approved_retained_queue_before,
};
use hepta_session_core::ReceiptJournal;
use paint_api::rendering_context::RenderingContext;
use servo::Servo;
use std::rc::Rc;
use std::sync::{Arc, mpsc};
use std::thread::{self, ThreadId};
use std::time::{Duration, Instant};

/// Native state stays on its creator thread. The actor worker consumes complete
/// opaque admissions; neither caller nor worker can replace this native endpoint.
pub struct ApprovedImmutableNativeStartup {
    creator_pid: u32,
    creator_thread: ThreadId,
    original_deadline: Instant,
    native: Option<ClosedImmutableNativeOwner>,
    retirement: Option<ApprovedQueueRetirement>,
    observations: Option<mpsc::Receiver<Result<ApprovedRetainedObservation, ProductDispatchError>>>,
    worker: Option<thread::JoinHandle<()>>,
}
impl ApprovedImmutableNativeStartup {
    pub fn start(
        admission: ApprovedRetainedAdmission,
        servo: Servo,
        context: Rc<dyn RenderingContext>,
        waker: Arc<dyn ServoEventLoopWaker>,
        journal: ReceiptJournal,
        image_id: String,
    ) -> Result<(Self, ApprovedRetainedIngress), ProductDispatchError> {
        let creator_pid = std::process::id();
        if let Err(error) = admission.ensure_creating_process() {
            // Servo/context/waker are already caller-created engine objects.
            // Do not run copied engine/channel destructors on fork refusal.
            std::mem::forget(servo);
            std::mem::forget(context);
            std::mem::forget(waker);
            return Err(error);
        }
        // Actual default-proc/policy/path admission precedes constructor/spawn.
        // The queue and packet retain this same opaque original Instant.
        let original_deadline = admission.deadline()?;
        let (ingress, mut queue, retirement) = approved_retained_queue_before(original_deadline)?;
        ingress.try_submit(admission)?;
        let first = queue.try_next()?.ok_or(ProductDispatchError::Closed)?;
        first.deadline()?;
        let (endpoint, native) = ClosedImmutableNativeOwner::new(servo, context, waker);
        first.deadline()?;
        let (sender, observations) = mpsc::sync_channel(1);
        let sender = ResultSender {
            creator_pid,
            channel: Some(sender),
        };
        // The non-Send coordinator is constructed on its actual actor worker.
        let worker = thread::Builder::new()
            .name("hepta-approved-actor".into())
            .spawn(move || {
                let mut coordinator = match first.coordinator(endpoint, journal, image_id) {
                    Ok(value) => value,
                    Err(error) => {
                        let _ = sender.try_send(Err(error));
                        return;
                    },
                };
                let mut next = Some(first);
                loop {
                    if std::process::id() != creator_pid {
                        std::mem::forget(coordinator);
                        std::mem::forget(next);
                        std::mem::forget(queue);
                        return;
                    }
                    let admission = match next.take() {
                        Some(value) => value,
                        None => loop {
                            match queue.try_next() {
                                Ok(Some(value)) => break value,
                                Ok(None) => thread::sleep(Duration::from_millis(2)),
                                Err(_) => return,
                            }
                        },
                    };
                    let result = admission.serve(&mut coordinator);
                    if std::process::id() != creator_pid {
                        std::mem::forget(coordinator);
                        std::mem::forget(queue);
                        return;
                    }
                    let stop = match &result {
                        Err(_) => true,
                        Ok(value) => {
                            value.service().is_err()
                                || value.report().is_err()
                                || value.runtime_state() != RuntimeState::Ready
                        },
                    };
                    if sender.try_send(result).is_err() || stop {
                        return;
                    }
                }
            })
            .map_err(|_| ProductDispatchError::DispatchFailed)?;
        if creator_pid != std::process::id() {
            std::mem::forget(native);
            std::mem::forget(observations);
            std::mem::forget(worker);
            return Err(ProductDispatchError::PeerRefused);
        }
        if Instant::now() >= original_deadline {
            let _ = retirement.request();
            drop(worker);
            return Err(ProductDispatchError::DeadlineExceeded);
        }
        Ok((
            Self {
                creator_pid,
                creator_thread: thread::current().id(),
                original_deadline,
                native: Some(native),
                retirement: Some(retirement),
                observations: Some(observations),
                worker: Some(worker),
            },
            ingress,
        ))
    }
    fn current_owner(&self) -> Result<(), ProductDispatchError> {
        if self.creator_pid != std::process::id() || self.creator_thread != thread::current().id() {
            Err(ProductDispatchError::PeerRefused)
        } else {
            Ok(())
        }
    }
    fn current(&self) -> Result<(), ProductDispatchError> {
        self.current_owner()?;
        if self
            .retirement
            .as_ref()
            .ok_or(ProductDispatchError::Closed)?
            .is_requested()?
        {
            return Err(ProductDispatchError::Closed);
        }
        if Instant::now() >= self.original_deadline {
            return Err(ProductDispatchError::DeadlineExceeded);
        }
        Ok(())
    }
    pub fn original_deadline(&self) -> Result<Instant, ProductDispatchError> {
        self.current_owner()?;
        Ok(self.original_deadline)
    }
    pub fn next_wake_deadline(&self) -> Result<Instant, ProductDispatchError> {
        self.current()?;
        let native = self
            .native
            .as_ref()
            .ok_or(ProductDispatchError::Closed)?
            .next_wake_deadline()
            .map_err(native_error)?;
        Ok(native.map_or(self.original_deadline, |value| {
            value.min(self.original_deadline)
        }))
    }
    pub fn drive(&mut self) -> Result<NativeDrive, ProductDispatchError> {
        if let Err(error) = self.current() {
            if self.current_owner().is_ok() {
                let _ = self.retire();
            }
            return Err(error);
        }
        let result = self
            .native
            .as_mut()
            .ok_or(ProductDispatchError::Closed)?
            .drive()
            .map_err(native_error);
        if result.is_err() {
            let _ = self.retire();
        }
        result
    }
    pub fn try_observation(
        &mut self,
    ) -> Result<
        Option<Result<ApprovedRetainedObservation, ProductDispatchError>>,
        ProductDispatchError,
    > {
        self.current_owner()?;
        match self
            .observations
            .as_ref()
            .ok_or(ProductDispatchError::Closed)?
            .try_recv()
        {
            Ok(value) => Ok(Some(value)),
            Err(mpsc::TryRecvError::Empty) => Ok(None),
            Err(mpsc::TryRecvError::Disconnected) => Err(ProductDispatchError::Closed),
        }
    }
    /// Requested can mean contended cancellation, never a completed native
    /// barrier. No joins, automatic reconstruction, reconciliation or replay.
    pub fn retire(&mut self) -> Result<ApprovedQueueRetirementState, ProductDispatchError> {
        self.current_owner()?;
        self.retirement
            .as_ref()
            .ok_or(ProductDispatchError::Closed)?
            .request()
    }
}
struct ResultSender {
    creator_pid: u32,
    channel: Option<mpsc::SyncSender<Result<ApprovedRetainedObservation, ProductDispatchError>>>,
}
impl ResultSender {
    fn try_send(
        &self,
        result: Result<ApprovedRetainedObservation, ProductDispatchError>,
    ) -> Result<(), ProductDispatchError> {
        if self.creator_pid != std::process::id() {
            return Err(ProductDispatchError::PeerRefused);
        }
        self.channel
            .as_ref()
            .ok_or(ProductDispatchError::Closed)?
            .try_send(result)
            .map_err(|_| ProductDispatchError::QueueFull)
    }
}
impl Drop for ResultSender {
    fn drop(&mut self) {
        if self.creator_pid != std::process::id() {
            std::mem::forget(self.channel.take());
        }
    }
}
impl Drop for ApprovedImmutableNativeStartup {
    fn drop(&mut self) {
        if self.current_owner().is_err() {
            // No copied Servo/mpsc/worker destructor runs in a foreign process.
            std::mem::forget(self.native.take());
            std::mem::forget(self.retirement.take());
            std::mem::forget(self.observations.take());
            std::mem::forget(self.worker.take());
            return;
        }
        let _ = self.retire();
        // JoinHandle drop detaches. Old connection/monitor/journal destructors
        // and synchronous native/proc/filesystem calls remain non-preemptible.
        self.worker.take();
    }
}
fn native_error(error: NativeOwnerError) -> ProductDispatchError {
    match error {
        NativeOwnerError::WrongOwner => ProductDispatchError::PeerRefused,
        NativeOwnerError::Deadline => ProductDispatchError::DeadlineExceeded,
        _ => ProductDispatchError::RecoveryRequired,
    }
}
