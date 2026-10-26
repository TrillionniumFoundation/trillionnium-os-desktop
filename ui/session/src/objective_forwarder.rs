//! One bounded FIFO transport worker; it owns no effect, task, ledger or grant.

use super::objective_bridge::{transport_unknown, ObjectiveBridge, RequestPermit};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{self, Receiver, SyncSender, TryRecvError, TrySendError};
use std::sync::Arc;
use std::time::Instant;
use trill_ui_core::objective::*;

struct Call {
    command: ObjectiveCommand,
    permit: Arc<RequestPermit>,
    response: SyncSender<ObjectiveReply>,
}

pub(super) enum ObjectiveReply {
    Observation(ObjectiveObservation),
    Rejected(ObjectiveTransportRejection),
}

pub(super) struct PendingReply {
    response: Receiver<ObjectiveReply>,
    permit: Arc<RequestPermit>,
    unknown: ObjectiveObservation,
    completed: bool,
}

impl PendingReply {
    pub(super) fn poll(&mut self) -> Option<ObjectiveReply> {
        if self.completed {
            return None;
        }
        let response = match self.response.try_recv() {
            Ok(response) => response,
            Err(TryRecvError::Empty) => return None,
            // A dead worker is not evidence of the original owner's outcome.
            Err(TryRecvError::Disconnected) => ObjectiveReply::Observation(self.unknown.clone()),
        };
        self.completed = true;
        Some(response)
    }
}

impl Drop for PendingReply {
    fn drop(&mut self) {
        self.permit.abandon();
    }
}

pub(super) struct ObjectiveForwarder {
    sender: Option<SyncSender<Call>>,
    stopped: Arc<AtomicBool>,
}

impl ObjectiveForwarder {
    pub(super) fn from_environment() -> Self {
        Self::from_bridge(ObjectiveBridge::from_environment())
    }

    pub(super) fn from_bridge(bridge: ObjectiveBridge) -> Self {
        let stopped = Arc::new(AtomicBool::new(false));
        if !bridge.configured() {
            return Self {
                sender: None,
                stopped,
            };
        }
        // At most one active exchange and one waiting command. A FIFO worker
        // preserves forwarding order; no per-peer thread may dispatch in parallel.
        let (sender, receiver) = mpsc::sync_channel::<Call>(1);
        let worker = std::thread::Builder::new()
            .name("trill-objective-transport".into())
            .spawn(move || {
                while let Ok(call) = receiver.recv() {
                    let response = bridge.request_until(call.command, &call.permit);
                    // Exactly one response slot exists. Losing its reader is
                    // not permission to repeat a command or invent a terminal.
                    let _ = call.response.send(ObjectiveReply::Observation(response));
                }
            });
        Self {
            sender: worker.ok().map(|_| sender),
            stopped,
        }
    }

    pub(super) fn request(&self, command: ObjectiveCommand, deadline: Instant) -> PendingReply {
        let (response, receive) = mpsc::sync_channel(1);
        let permit = Arc::new(RequestPermit::new(deadline, self.stopped.clone()));
        let pending = PendingReply {
            response: receive,
            permit: permit.clone(),
            unknown: transport_unknown(&command),
            completed: false,
        };
        let request = command.transport_request();
        let issue = command
            .validate()
            .err()
            .map(|_| ObjectiveTransportRejectionReason::InvalidIntent)
            .or_else(|| {
                (self.sender.is_none() || self.stopped.load(Ordering::Acquire))
                    .then_some(ObjectiveTransportRejectionReason::Unavailable)
            });
        if let Some(reason) = issue {
            let _ = response.send(ObjectiveReply::Rejected(ObjectiveTransportRejection {
                request,
                reason,
            }));
            return pending;
        }
        let call = Call {
            command,
            permit,
            response,
        };
        match self
            .sender
            .as_ref()
            .expect("configured worker")
            .try_send(call)
        {
            Ok(()) => {}
            Err(error) => {
                let (call, reason) = match error {
                    TrySendError::Full(call) => (call, ObjectiveTransportRejectionReason::Capacity),
                    TrySendError::Disconnected(call) => {
                        (call, ObjectiveTransportRejectionReason::Unavailable)
                    }
                };
                call.permit.abandon();
                let _ = call
                    .response
                    .send(ObjectiveReply::Rejected(ObjectiveTransportRejection {
                        request,
                        reason,
                    }));
            }
        }
        pending
    }
}

impl Drop for ObjectiveForwarder {
    fn drop(&mut self) {
        self.stopped.store(true, Ordering::SeqCst);
        drop(self.sender.take());
        // Do not join a slow transport from the lifecycle owner. The worker
        // rejects queued sends, finishes its bounded in-flight exchange and
        // exits when its only sender closes. No original-owner cancellation
        // or rollback is asserted for a write that may already have happened.
    }
}

#[cfg(test)]
#[path = "objective_forwarder_tests.rs"]
mod tests;
