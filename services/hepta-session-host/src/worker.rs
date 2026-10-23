//! One bounded blocking worker. Cached views carry no signing or replay rights.
use crate::{ObjectiveHostAuthority, TypedObjectiveHost};
use std::collections::BTreeMap;
use std::sync::{Arc, Mutex, mpsc};
use trill_ui_core::objective::*;

struct Views {
    availability: ObjectiveObservation,
    intents: BTreeMap<String, ObjectiveObservation>,
}

/// A deployment's socket listener calls `request` and immediately returns the
/// current view. It must authenticate its fixed Session peer before this call.
/// The original host performs all retention and I/O on this one bounded worker.
pub struct ObjectiveWorker {
    commands: mpsc::SyncSender<ObjectiveCommand>,
    views: Arc<Mutex<Views>>,
}

impl ObjectiveWorker {
    pub fn spawn<A: ObjectiveHostAuthority + 'static>(
        mut host: TypedObjectiveHost<A>,
    ) -> std::io::Result<Self> {
        let (commands, incoming) = mpsc::sync_channel(8);
        let views = Arc::new(Mutex::new(Views {
            availability: ObjectiveObservation::new(None, ObjectiveStage::Unavailable),
            intents: BTreeMap::new(),
        }));
        let updated = Arc::clone(&views);
        std::thread::Builder::new()
            .name("original-objective-host".into())
            .spawn(move || {
                while let Ok(command) = incoming.recv() {
                    let result = host.handle(command);
                    let Ok(mut views) = updated.lock() else {
                        break;
                    };
                    if let Some(id) = &result.client_intent_id {
                        views.intents.insert(id.clone(), result);
                    } else {
                        views.availability = result;
                    }
                }
            })?;
        Ok(Self { commands, views })
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
        let Ok(mut views) = self.views.lock() else {
            fallback.issue = Some(ObjectiveHostIssue::Unavailable);
            return fallback;
        };
        let result = if let Some(id) = command.client_intent_id() {
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
        // A full queue never starts an unrecorded fallback operation. The caller
        // may repeat Status; repeating Submit is fenced by the original owner.
        if self.commands.try_send(command).is_err() {
            let mut result = result;
            result.issue = Some(ObjectiveHostIssue::Capacity);
            result
        } else {
            result
        }
    }
}
