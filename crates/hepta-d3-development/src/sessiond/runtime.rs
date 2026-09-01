//! Caller-bound atomic semantic action runtime for the isolated D3 fixture.
//!
//! This adapter deliberately remains local-fixture-only. It proves that the
//! BrowserActor's dedicated `dispatch_page_act` hook can retain one observed
//! target, revalidate every available revision and structural coordinate at
//! the action boundary, and apply the typed action exactly once without a
//! resolve/act split. It does not claim a Servo adapter or product authority.

use hepta_browser_actor::{
    BrowserActorMessage, DeterministicLocalRuntime, PageOwnerSnapshot, PageRuntime,
    RequestControl, RuntimeFailure, RuntimeReply,
};
use hepta_browser_codec::{ElementReference, JsonObject, JsonValue, PageAction};

const FRAME_ID: &str = "frame-main";
const BACKEND_NODE_KEY: &str = "submit-primary";
const ROLE: &str = "button";
const ACCESSIBLE_NAME_SHA256: &str =
    "155f816c0407310c0dab222493370773e045ee7fe04e6c9a951b07f495531264";
const STRUCTURAL_FINGERPRINT: &str =
    "1111111111111111111111111111111111111111111111111111111111111111";

#[derive(Debug, Clone)]
pub(crate) struct AtomicFixtureRuntime {
    inner: DeterministicLocalRuntime,
    semantic_snapshot: Option<SemanticSnapshot>,
    applied_action_count: u64,
}

impl Default for AtomicFixtureRuntime {
    fn default() -> Self {
        Self {
            inner: DeterministicLocalRuntime::default(),
            semantic_snapshot: None,
            applied_action_count: 0,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct RuntimeCoordinates {
    session_id: String,
    webview_token: String,
    current_url: String,
    session_generation: u64,
    document_generation: u64,
    semantic_snapshot_revision: u64,
    mutation_epoch: u64,
}

impl RuntimeCoordinates {
    fn from_owner(owner: &PageOwnerSnapshot) -> Self {
        let revisions = owner.session.revisions;
        Self {
            session_id: owner.session_id.clone(),
            webview_token: owner.webview_token.clone(),
            current_url: owner.current_url.clone(),
            session_generation: revisions.session_generation,
            document_generation: revisions.document_generation,
            semantic_snapshot_revision: revisions.semantic_snapshot_revision,
            mutation_epoch: revisions.mutation_epoch,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct SemanticSnapshot {
    coordinates: RuntimeCoordinates,
    target: ElementReference,
}

impl PageRuntime for AtomicFixtureRuntime {
    fn dispatch(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        message: BrowserActorMessage,
        control: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure> {
        let captures_semantic_snapshot = matches!(&message, BrowserActorMessage::Observe { .. });
        let invalidates_semantic_snapshot = matches!(
            &message,
            BrowserActorMessage::CreateSession { .. }
                | BrowserActorMessage::Navigate { .. }
                | BrowserActorMessage::Close
        );
        let reports_health = matches!(&message, BrowserActorMessage::Health);
        let reports_extract = matches!(&message, BrowserActorMessage::Extract { .. });

        if captures_semantic_snapshot || invalidates_semantic_snapshot {
            self.semantic_snapshot = None;
        }

        let mut reply = self.inner.dispatch(owner, message, control)?;
        control.ensure_active()?;

        if reports_health {
            reply.result.insert(
                "atomic_fixture_page_act_ready".to_owned(),
                JsonValue::Bool(true),
            );
            reply.result.insert(
                "caller_bound_target_revalidation".to_owned(),
                JsonValue::Bool(true),
            );
            reply.result.insert(
                "servo_adapter_exercised".to_owned(),
                JsonValue::Bool(false),
            );
        }

        if captures_semantic_snapshot {
            let owner = owner.ok_or_else(|| {
                RuntimeFailure::Internal("PageObserve has no PageOwner".to_owned())
            })?;
            if !owner.local_fixture_only {
                return Err(RuntimeFailure::PolicyDenied(
                    "atomic fixture resolver requires a local-only PageOwner",
                ));
            }
            let mut coordinates = RuntimeCoordinates::from_owner(owner);
            coordinates.semantic_snapshot_revision = coordinates
                .semantic_snapshot_revision
                .checked_add(1)
                .ok_or_else(|| {
                    RuntimeFailure::Internal(
                        "semantic snapshot revision exhausted before publication".to_owned(),
                    )
                })?;
            let target = semantic_target(&coordinates);
            self.semantic_snapshot = Some(SemanticSnapshot {
                coordinates: coordinates.clone(),
                target: target.clone(),
            });
            reply.result.insert(
                "semantic_target".to_owned(),
                JsonValue::Object(reference_json(&target)?),
            );
            reply.result.insert(
                "semantic_snapshot_mutation_epoch".to_owned(),
                json_u64(coordinates.mutation_epoch)?,
            );
            reply.result.insert(
                "caller_bound_snapshot".to_owned(),
                JsonValue::Bool(true),
            );
            reply.result.insert(
                "atomic_page_act_available".to_owned(),
                JsonValue::Bool(true),
            );
            reply.result.insert(
                "servo_adapter_exercised".to_owned(),
                JsonValue::Bool(false),
            );
        }

        if reports_extract
            && let Some(JsonValue::Object(value)) = reply.result.get_mut("value")
        {
            value.insert(
                "action_count".to_owned(),
                json_u64(self.applied_action_count)?,
            );
        }

        Ok(reply)
    }

    fn dispatch_page_act(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        target: ElementReference,
        action: PageAction,
        control: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure> {
        control.ensure_active()?;
        let owner = owner.ok_or_else(|| {
            RuntimeFailure::Internal("PageAct has no PageOwner".to_owned())
        })?;
        if !owner.local_fixture_only {
            return Err(RuntimeFailure::PolicyDenied(
                "atomic fixture action requires a local-only PageOwner",
            ));
        }
        let current = RuntimeCoordinates::from_owner(owner);
        let snapshot = self.semantic_snapshot.clone().ok_or(
            RuntimeFailure::PolicyDenied(
                "PageAct requires a caller-bound semantic observation",
            ),
        )?;
        validate_binding(&snapshot, &current, &target, &action)?;

        let next_action_count = self.applied_action_count.checked_add(1).ok_or_else(|| {
            RuntimeFailure::Internal("atomic fixture action counter exhausted".to_owned())
        })?;
        let mutation_epoch_after = current.mutation_epoch.checked_add(1).ok_or_else(|| {
            RuntimeFailure::Internal("mutation epoch exhausted before atomic action".to_owned())
        })?;

        // This second control check is intentionally adjacent to the commit.
        // No target lookup, await point, callback, or externally visible effect
        // occurs between it and the exactly-once state mutation below.
        control.ensure_active()?;
        self.applied_action_count = next_action_count;
        self.semantic_snapshot = None;

        let mut result = JsonObject::new();
        result.insert(
            "action".to_owned(),
            JsonValue::String(action_name(&action).to_owned()),
        );
        result.insert(
            "action_count".to_owned(),
            json_u64(self.applied_action_count)?,
        );
        result.insert(
            "atomic_semantic_resolver_exercised".to_owned(),
            JsonValue::Bool(true),
        );
        result.insert(
            "caller_bound_target_revalidated".to_owned(),
            JsonValue::Bool(true),
        );
        result.insert(
            "resolved_frame_id".to_owned(),
            JsonValue::String(target.frame_id),
        );
        result.insert(
            "resolved_backend_node_key".to_owned(),
            JsonValue::String(BACKEND_NODE_KEY.to_owned()),
        );
        result.insert(
            "mutation_epoch_before".to_owned(),
            json_u64(current.mutation_epoch)?,
        );
        result.insert(
            "mutation_epoch_after".to_owned(),
            json_u64(mutation_epoch_after)?,
        );
        result.insert(
            "effect_applied_exactly_once".to_owned(),
            JsonValue::Bool(true),
        );
        result.insert(
            "local_fixture_only".to_owned(),
            JsonValue::Bool(true),
        );
        result.insert(
            "external_effect_authority".to_owned(),
            JsonValue::Bool(false),
        );
        result.insert(
            "servo_adapter_exercised".to_owned(),
            JsonValue::Bool(false),
        );

        Ok(RuntimeReply {
            result,
            current_url: Some(current.current_url),
        })
    }
}

fn semantic_target(coordinates: &RuntimeCoordinates) -> ElementReference {
    ElementReference {
        session_generation: coordinates.session_generation,
        document_generation: coordinates.document_generation,
        semantic_snapshot_revision: coordinates.semantic_snapshot_revision,
        frame_id: FRAME_ID.to_owned(),
        backend_node_key: Some(BACKEND_NODE_KEY.to_owned()),
        role: Some(ROLE.to_owned()),
        accessible_name_sha256: Some(ACCESSIBLE_NAME_SHA256.to_owned()),
        structural_fingerprint: STRUCTURAL_FINGERPRINT.to_owned(),
    }
}

fn validate_binding(
    snapshot: &SemanticSnapshot,
    current: &RuntimeCoordinates,
    target: &ElementReference,
    action: &PageAction,
) -> Result<(), RuntimeFailure> {
    if snapshot.coordinates != *current {
        return Err(RuntimeFailure::PolicyDenied(
            "semantic snapshot no longer matches the current PageOwner",
        ));
    }
    if snapshot.target != *target {
        return Err(RuntimeFailure::PolicyDenied(
            "semantic target changed between observation and action",
        ));
    }
    if !matches!(action, PageAction::Click) {
        return Err(RuntimeFailure::Unsupported(
            "the local atomic fixture exposes only a click action",
        ));
    }
    Ok(())
}

fn reference_json(reference: &ElementReference) -> Result<JsonObject, RuntimeFailure> {
    let mut object = JsonObject::new();
    object.insert(
        "session_generation".to_owned(),
        json_u64(reference.session_generation)?,
    );
    object.insert(
        "document_generation".to_owned(),
        json_u64(reference.document_generation)?,
    );
    object.insert(
        "semantic_snapshot_revision".to_owned(),
        json_u64(reference.semantic_snapshot_revision)?,
    );
    object.insert(
        "frame_id".to_owned(),
        JsonValue::String(reference.frame_id.clone()),
    );
    if let Some(value) = &reference.backend_node_key {
        object.insert(
            "backend_node_key".to_owned(),
            JsonValue::String(value.clone()),
        );
    }
    if let Some(value) = &reference.role {
        object.insert("role".to_owned(), JsonValue::String(value.clone()));
    }
    if let Some(value) = &reference.accessible_name_sha256 {
        object.insert(
            "accessible_name_sha256".to_owned(),
            JsonValue::String(value.clone()),
        );
    }
    object.insert(
        "structural_fingerprint".to_owned(),
        JsonValue::String(reference.structural_fingerprint.clone()),
    );
    Ok(object)
}

fn json_u64(value: u64) -> Result<JsonValue, RuntimeFailure> {
    i64::try_from(value)
        .map(JsonValue::Integer)
        .map_err(|_| RuntimeFailure::Internal("runtime integer exceeds wire range".to_owned()))
}

fn action_name(action: &PageAction) -> &'static str {
    match action {
        PageAction::Click => "click",
        PageAction::Type { .. } => "type",
        PageAction::Press { .. } => "press",
        PageAction::Scroll { .. } => "scroll",
        PageAction::Select { .. } => "select",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn coordinates() -> RuntimeCoordinates {
        RuntimeCoordinates {
            session_id: "session-1".to_owned(),
            webview_token: "webview-1".to_owned(),
            current_url: "http://127.0.0.1/d3-local-fixture".to_owned(),
            session_generation: 1,
            document_generation: 2,
            semantic_snapshot_revision: 2,
            mutation_epoch: 1,
        }
    }

    fn snapshot() -> SemanticSnapshot {
        let coordinates = coordinates();
        SemanticSnapshot {
            target: semantic_target(&coordinates),
            coordinates,
        }
    }

    #[test]
    fn exact_observed_binding_admits_one_click() {
        let snapshot = snapshot();
        assert!(
            validate_binding(
                &snapshot,
                &snapshot.coordinates,
                &snapshot.target,
                &PageAction::Click,
            )
            .is_ok()
        );
    }

    #[test]
    fn mutation_epoch_drift_is_rejected_before_action() {
        let snapshot = snapshot();
        let mut current = snapshot.coordinates.clone();
        current.mutation_epoch += 1;
        assert!(matches!(
            validate_binding(&snapshot, &current, &snapshot.target, &PageAction::Click),
            Err(RuntimeFailure::PolicyDenied(_))
        ));
    }

    #[test]
    fn structural_retargeting_is_rejected_before_action() {
        let snapshot = snapshot();
        let mut target = snapshot.target.clone();
        target.structural_fingerprint = "22".repeat(32);
        assert!(matches!(
            validate_binding(
                &snapshot,
                &snapshot.coordinates,
                &target,
                &PageAction::Click,
            ),
            Err(RuntimeFailure::PolicyDenied(_))
        ));
    }

    #[test]
    fn unsupported_typed_action_is_rejected_before_action() {
        let snapshot = snapshot();
        assert!(matches!(
            validate_binding(
                &snapshot,
                &snapshot.coordinates,
                &snapshot.target,
                &PageAction::Type {
                    text: "forbidden".to_owned(),
                },
            ),
            Err(RuntimeFailure::Unsupported(_))
        ));
    }
}
