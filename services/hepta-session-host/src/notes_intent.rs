//! Deterministic adapter for the named “Write note” action. Text is literal
//! document content, never instructions to a model or additional capabilities.
use codex_hepta_memory::{NotesTargetIdentity, notes_operation_intent};
use codex_hepta_objective::{
    LiteralNotesSourceContext, literal_notes_admission_profile_json_v1,
    literal_notes_source_json_v1,
};
use codex_hepta_operations::OperationIntentV1;
use codex_hepta_types::{Digest32, Generation, StableId};
use serde_json::json;
use trill_ui_core::objective::{ObjectiveCommand, ObjectiveHostIssue, ObjectiveIntent};

/// All destination and subject fields come from trusted deployment, never UI.
pub struct NotesIntentContext<'a> {
    pub target: &'a NotesTargetIdentity,
    pub expected_revision: u64,
    pub operation_id: &'a str,
    pub subject: StableId,
    pub policy_generation: Generation,
    pub principal_scope_digest: Digest32,
    pub locale: &'a str,
    pub observed_at: &'a str,
    pub deadline: &'a str,
}

/// Keep these bytes private. The original operation owner must retain this
/// exact payload and intent before any final-use dispatch. Compilation alone
/// provides no grant and performs no document write.
pub struct CompiledNotesIntent {
    pub source_envelope_json: String,
    pub payload_json: String,
    pub operation: OperationIntentV1,
}

pub fn compile_notes_intent(
    intent: &ObjectiveIntent,
    context: NotesIntentContext<'_>,
) -> Result<CompiledNotesIntent, ObjectiveHostIssue> {
    ObjectiveCommand::Submit {
        intent: intent.clone(),
    }
    .validate()?;
    let payload_json = serde_json::to_string(&json!({
        "schema_version":1,"action":"replace_note","operation_id":context.operation_id,
        "destination_id":context.target.destination_id(),"target":context.target,
        "expected_revision":context.expected_revision,"text":intent.text,
    }))
    .map_err(|_| ObjectiveHostIssue::InvalidIntent)?;
    // The original Notes owner enforces 4096 text bytes, its exact 8192-byte
    // wire bound, destination incarnation and predecessor semantics.
    let operation = notes_operation_intent(
        context.target,
        &payload_json,
        context.subject,
        context.policy_generation,
    )
    .map_err(|_| ObjectiveHostIssue::InvalidIntent)?;
    let source_envelope_json = literal_notes_source_json_v1(LiteralNotesSourceContext {
        client_intent_id: &intent.client_intent_id,
        source_digest: operation.semantic_digest(),
        principal_scope_digest: context.principal_scope_digest,
        locale: context.locale,
        observed_at: context.observed_at,
        deadline: context.deadline,
    })
    .map_err(|_| ObjectiveHostIssue::InvalidIntent)?;
    Ok(CompiledNotesIntent {
        source_envelope_json,
        payload_json,
        operation,
    })
}

/// A frozen profile for one persistent principal and registered signing adapter.
/// Its scope is independent of a Notes process incarnation; each operation
/// separately binds the exact current target and predecessor in its payload.
pub fn notes_admission_profile_json(
    principal_scope: &str,
    principal_scope_digest: Digest32,
    issuer_id: &str,
) -> Result<String, ObjectiveHostIssue> {
    literal_notes_admission_profile_json_v1(principal_scope, principal_scope_digest, issuer_id)
        .map_err(|_| ObjectiveHostIssue::InvalidIntent)
}
