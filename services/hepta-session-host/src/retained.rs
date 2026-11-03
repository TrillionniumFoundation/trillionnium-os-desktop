//! Bounded navigation recovery from the original owner; never a send path.
use crate::ObjectiveHostAuthority;
use codex_hepta_memory::{
    ObjectiveSenderOrigin, ObjectiveSenderRetainedPosition, ProductionObjectiveSender,
};
use std::{collections::BTreeSet, time::Duration};
use tokio::runtime::Handle;
use trill_ui_core::objective::*;

pub(crate) fn collect<A: ObjectiveHostAuthority>(
    authority: &A,
    sender: &ProductionObjectiveSender<A::Checkpoint>,
    origin: &ObjectiveSenderOrigin,
    runtime: &Handle,
    deadline: Duration,
) -> Result<ObjectiveRetainedIntents, ObjectiveHostIssue> {
    runtime.block_on(async {
        tokio::time::timeout(deadline, async {
            let mut ids = BTreeSet::new();
            let mut position = ObjectiveSenderRetainedPosition::Beginning;
            // Limit both renderer-visible IDs and unrelated retained records.
            // A partial traversal never advertises complete recovery/readiness.
            for _ in 0..64 {
                let page = sender
                    .retained_page(position)
                    .await
                    .map_err(|_| ObjectiveHostIssue::PersistenceUnknown)?;
                for request in page.requests {
                    if request.origin().agent_id != origin.agent_id
                        || request.origin().spawn_generation > origin.spawn_generation
                    {
                        return Err(ObjectiveHostIssue::IdentityMismatch);
                    }
                    let Some(id) = authority.retained_client_intent_id(&request)? else {
                        continue;
                    };
                    ObjectiveCommand::Status {
                        client_intent_id: id.clone(),
                    }
                    .validate()?;
                    if authority.run_id(&id)? != request.identity().run_id || ids.contains(&id) {
                        return Err(ObjectiveHostIssue::IdentityMismatch);
                    }
                    if ids.len() == MAX_OBJECTIVE_VIEWS {
                        return Ok(ObjectiveRetainedIntents {
                            client_intent_ids: ids.into_iter().collect(),
                            complete: false,
                        });
                    }
                    ids.insert(id);
                }
                match page.next {
                    Some(cursor) => position = ObjectiveSenderRetainedPosition::After(cursor),
                    None => {
                        return Ok(ObjectiveRetainedIntents {
                            client_intent_ids: ids.into_iter().collect(),
                            complete: true,
                        });
                    }
                }
            }
            Ok(ObjectiveRetainedIntents {
                client_intent_ids: ids.into_iter().collect(),
                complete: false,
            })
        })
        .await
        .map_err(|_| ObjectiveHostIssue::PersistenceUnknown)?
    })
}
