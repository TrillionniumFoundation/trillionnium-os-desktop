//! Deterministic adapter for the named “Write note” action. Text is literal
//! document content, never instructions to a model or additional capabilities.
use codex_hepta_memory::{NotesTargetIdentity, notes_operation_intent};
use codex_hepta_objective::{
    canonical_objective_intent_digest_v1, decode_admission_profile_json_v1,
    decode_source_envelope_json_v1,
};
use codex_hepta_operations::OperationIntentV1;
use codex_hepta_types::{Digest32, Generation, StableId};
use serde_json::{Value, json};
use trill_ui_core::objective::{ObjectiveCommand, ObjectiveHostIssue, ObjectiveIntent};

const SCHEMA: &[u8] = b"organ.notes.literal.v1:client_intent_id,text;private:target,expected_revision,operation_id,subject,policy_generation";
const NORMALIZATION: &[u8] = b"organ.notes.literal.v1:preserve-utf8-exactly;json-encode-notes-replace-v1;original-operation-semantic-digest;one-note-no-model-no-network";

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
    let source_digest = operation.semantic_digest();
    let mut source = json!({
        "requestId":intent.client_intent_id,"principalScopeDigest":context.principal_scope_digest.to_string(),
        "intentDigest":Digest32::ZERO.to_string(),
        "structuredIntent":{
            "successPredicates":[{"predicateId":"notes.document.matches","unit":"boolean","comparator":"eq","boundQ32":4294967296_i64,"evidenceSourceId":"notes.original.readback","terminal":false}],
            "terminalConditions":[{"predicateId":"notes.operation.committed","unit":"boolean","comparator":"eq","boundQ32":4294967296_i64,"evidenceSourceId":"notes.original.owner","terminal":true}],
            "legalActionClasses":["notes.replace"],"forbiddenActionClasses":["network","process.execute"],"confirmationActionClasses":[],
            "constraints":[{"constraintId":"notes.exact.destination","unit":"boolean","comparator":"eq","boundQ32":4294967296_i64,"evidenceSourceId":"notes.literal.profile","terminal":false}],"softDimensions":[],
            "evidenceRequirements":[{"requirementId":"notes.exact.receipt","evidenceSourceId":"notes.original.owner","minimumConfidencePpm":1000000,"terminal":true}],
            "resources":{"timeMicros":5000000,"tokenCount":0,"computeMicros":1000000,"memoryBytes":8192,"networkBytes":0,"externalEffectCount":1},
            "risk":{"riskClass":"low","abstentionRule":"refuse_if_unbound","rollbackClass":"none","compensationRequired":false},
            "provenance":{"sourceDigest":source_digest.to_string(),"normalizationProfileDigest":Digest32::of_bytes(NORMALIZATION).to_string()}
        },
        "sourceTrustClass":"authorized_adapter","locale":context.locale,"observedAt":context.observed_at,
        "deadline":context.deadline,"inputSchemaDigest":Digest32::of_bytes(SCHEMA).to_string(),
    });
    let decoded = decode_source_envelope_json_v1(
        &serde_json::to_vec(&source).map_err(|_| ObjectiveHostIssue::InvalidIntent)?,
    )
    .map_err(|_| ObjectiveHostIssue::InvalidIntent)?;
    source["intentDigest"] = json!(
        canonical_objective_intent_digest_v1(&decoded)
            .map_err(|_| ObjectiveHostIssue::InvalidIntent)?
            .to_string()
    );
    Ok(CompiledNotesIntent {
        source_envelope_json: serde_json::to_string(&source)
            .map_err(|_| ObjectiveHostIssue::InvalidIntent)?,
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
    let resource = |name: &str| json!({"constraintId":format!("notes.resource.{name}.ceiling"),"axis":format!("notes.resource.{name}"),"class":"principal","q32PerSourceUnit":1,"evidenceSource":"notes.literal.profile"});
    let profile: Value = json!({
        "profileId":"organ.notes.literal.v1","profileRevision":1,
        "expectedInputSchemaDigest":Digest32::of_bytes(SCHEMA).to_string(),
        "expectedNormalizationProfileDigest":Digest32::of_bytes(NORMALIZATION).to_string(),
        "principalScopeDigest":principal_scope_digest.to_string(),"principalScope":principal_scope,
        "allowedLocales":["en-US","zh-CN"],"maximumSourceAgeMicros":60000000,"maximumFutureSkewMicros":1000000,
        "deadlineRequired":true,"allowedTrustedSourceIdentities":[issuer_id],
        "constraints":[{"sourceConstraintId":"notes.exact.destination","expectedUnit":"boolean","class":"principal","axis":"notes.exact.destination"}],
        "predicates":[
            {"sourcePredicateId":"notes.document.matches","expectedUnit":"boolean","axis":"notes.document.matches"},
            {"sourcePredicateId":"notes.operation.committed","expectedUnit":"boolean","axis":"notes.operation.committed"}
        ],
        "actions":[
            {"sourceActionClass":"notes.replace","actionId":"notes.replace"},
            {"sourceActionClass":"network","actionId":"network"},
            {"sourceActionClass":"process.execute","actionId":"process.execute"}
        ],
        "softDimensions":[],"evidenceRequirements":[{"sourceRequirementId":"notes.exact.receipt","axis":"notes.receipt.confidence"}],
        "resources":{"timeMicros":resource("time"),"tokenCount":resource("tokens"),"computeMicros":resource("compute"),"memoryBytes":resource("memory"),"networkBytes":resource("network"),"externalEffectCount":resource("effects")},
        "risk":{"evidenceSource":"notes.literal.profile","class":"principal",
            "riskConstraintId":"notes.risk.class","riskAxis":"notes.risk.class.value","lowValueQ32":0,"mediumValueQ32":1,"highValueQ32":2,"criticalValueQ32":3,
            "rollbackConstraintId":"notes.risk.rollback","rollbackAxis":"notes.risk.rollback.value","rollbackNoneValueQ32":0,"rollbackReversibleValueQ32":1,"rollbackCompensatableValueQ32":2,"rollbackIrreversibleValueQ32":3,
            "compensationConstraintId":"notes.risk.compensation","compensationAxis":"notes.risk.compensation.value","compensationFalseValueQ32":0,"compensationTrueValueQ32":1,
            "abstentionConstraintId":"notes.risk.abstention","abstentionAxis":"notes.risk.abstention.value","abstentionRules":[{"sourceRule":"refuse_if_unbound","valueQ32":1}]
        }
    });
    let bytes = serde_json::to_vec(&profile).map_err(|_| ObjectiveHostIssue::InvalidIntent)?;
    decode_admission_profile_json_v1(&bytes).map_err(|_| ObjectiveHostIssue::InvalidIntent)?;
    String::from_utf8(bytes).map_err(|_| ObjectiveHostIssue::InvalidIntent)
}
