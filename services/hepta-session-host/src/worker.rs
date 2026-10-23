//! One bounded blocking worker; passive refresh cannot occupy action slots.
use crate::{ObjectiveHostAuthority, TypedObjectiveHost};
use std::collections::{BTreeMap, VecDeque};
use std::sync::{Arc, Condvar, Mutex};
use trill_ui_core::objective::*;

const ACTION_CAPACITY: usize = 8;

struct Views {
    availability: ObjectiveObservation,
    intents: BTreeMap<String, ObjectiveObservation>,
}

#[derive(Default)]
struct Pending {
    actions: VecDeque<ObjectiveCommand>,
    passive: VecDeque<ObjectiveCommand>,
    closed: bool,
}

struct Queue {
    pending: Mutex<Pending>,
    wake: Condvar,
}

/// The listener authenticates its fixed Session peer, calls `request`, and
/// immediately returns the last observation. Only the worker enters the original
/// owner. Actions retain FIFO order (a Cancel cannot overtake its queued Submit).
/// Availability and Status refreshes coalesce independently and never consume
/// the eight action slots. No queue entry grants authority or sending rights.
pub struct ObjectiveWorker {
    queue: Arc<Queue>,
    views: Arc<Mutex<Views>>,
}

impl ObjectiveWorker {
    pub fn spawn<A: ObjectiveHostAuthority + 'static>(
        mut host: TypedObjectiveHost<A>,
    ) -> std::io::Result<Self> {
        Self::spawn_handler(move |command| host.handle(command))
    }

    fn spawn_handler(
        mut handle: impl FnMut(ObjectiveCommand) -> ObjectiveObservation + Send + 'static,
    ) -> std::io::Result<Self> {
        let queue = Arc::new(Queue {
            pending: Mutex::new(Pending::default()),
            wake: Condvar::new(),
        });
        let views = Arc::new(Mutex::new(Views {
            availability: ObjectiveObservation::new(None, ObjectiveStage::Unavailable),
            intents: BTreeMap::new(),
        }));
        let incoming = Arc::clone(&queue);
        let updated = Arc::clone(&views);
        std::thread::Builder::new()
            .name("original-objective-host".into())
            .spawn(move || {
                loop {
                    let command = {
                        let Ok(mut pending) = incoming.pending.lock() else {
                            break;
                        };
                        while !pending.closed
                            && pending.actions.is_empty()
                            && pending.passive.is_empty()
                        {
                            let Ok(next) = incoming.wake.wait(pending) else {
                                return;
                            };
                            pending = next;
                        }
                        if pending.closed {
                            break;
                        }
                        pending
                            .actions
                            .pop_front()
                            .or_else(|| pending.passive.pop_front())
                    };
                    let Some(command) = command else { continue };
                    let result = handle(command);
                    let Ok(mut views) = updated.lock() else { break };
                    if let Some(id) = &result.client_intent_id {
                        views.intents.insert(id.clone(), result);
                    } else {
                        views.availability = result;
                    }
                }
            })?;
        Ok(Self { queue, views })
    }

    pub fn request(&self, command: ObjectiveCommand) -> ObjectiveObservation {
        let mut fallback = ObjectiveObservation::new(
            command.client_intent_id().map(str::to_owned),
            ObjectiveStage::Unavailable,
        );
        if let Err(issue) = command.validate() {
            fallback.issue = Some(issue);
            return fallback;
        }
        let Ok(mut views) = self.views.try_lock() else {
            fallback.issue = Some(ObjectiveHostIssue::Unavailable);
            return fallback;
        };
        let mut result = if let Some(id) = command.client_intent_id() {
            if !views.intents.contains_key(id) && views.intents.len() >= MAX_OBJECTIVE_VIEWS {
                fallback.issue = Some(ObjectiveHostIssue::Capacity);
                return fallback;
            }
            views
                .intents
                .entry(id.to_owned())
                .or_insert_with(|| {
                    ObjectiveObservation::new(Some(id.to_owned()), ObjectiveStage::Queued)
                })
                .clone()
        } else {
            views.availability.clone()
        };
        drop(views);
        let Ok(mut pending) = self.queue.pending.try_lock() else {
            result.issue = Some(ObjectiveHostIssue::Capacity);
            return result;
        };
        if pending.closed {
            result.issue = Some(ObjectiveHostIssue::Unavailable);
            return result;
        }
        match &command {
            ObjectiveCommand::Submit { .. } | ObjectiveCommand::Cancel { .. } => {
                if pending.actions.len() >= ACTION_CAPACITY {
                    result.issue = Some(ObjectiveHostIssue::Capacity);
                    return result;
                }
                pending.actions.push_back(command);
            }
            ObjectiveCommand::Availability {} | ObjectiveCommand::Status { .. } => {
                if let Some(existing) = pending
                    .passive
                    .iter_mut()
                    .find(|existing| existing.client_intent_id() == command.client_intent_id())
                {
                    *existing = command;
                } else if pending.passive.len() < MAX_OBJECTIVE_VIEWS + 1 {
                    pending.passive.push_back(command);
                } else {
                    result.issue = Some(ObjectiveHostIssue::Capacity);
                    return result;
                }
            }
        }
        self.queue.wake.notify_one();
        result
    }
}

impl Drop for ObjectiveWorker {
    fn drop(&mut self) {
        if let Ok(mut pending) = self.queue.pending.lock() {
            // A discarded host must not start a queued submission afterward.
            // An already-running original call keeps its original uncertainty
            // and cancellation rules; this drop does not fabricate a receipt.
            pending.closed = true;
            pending.actions.clear();
            pending.passive.clear();
            self.queue.wake.notify_one();
        }
    }
}

#[cfg(test)]
#[path = "worker_tests.rs"]
mod tests;
