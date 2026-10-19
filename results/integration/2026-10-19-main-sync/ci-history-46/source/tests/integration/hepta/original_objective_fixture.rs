//! Independent test producer. The signing key never enters Agentd or the CLI.

use chrono::{DateTime, SecondsFormat, Utc};
use codex_hepta_agent_protocol::{AuthBusObjectiveBody, AuthBusObjectiveIngress};
use codex_hepta_authbus::SignedMessageClaims;
use codex_hepta_objective::{
    ObjectiveAdmissionContextV1, ObjectiveAdmissionReceiptV1, ObjectiveSourceAuthenticationV1,
    admit_and_compile_objective_v1, canonical_objective_intent_digest_v1,
    decode_admission_profile_json_v1, decode_source_envelope_json_v1, encode_objective_function_v1,
};
use codex_hepta_types::{Digest32, Generation, Revision, StableId};
use ed25519_dalek::{Signer, SigningKey};
use serde_json::{Value, json};

use crate::{AGENT, Result, require};

pub const ISSUER: &str = "issuer.desktop-isolated-objective.v1";
pub const PROFILE: &str = include_str!("original_objective_profile.json");

#[derive(Clone, Copy)]
pub enum ActionSet {
    Read,
    Abstain,
}

pub struct Fixture {
    pub request: AuthBusObjectiveIngress,
    pub admission: ObjectiveAdmissionReceiptV1,
    pub objective_digest: Digest32,
    pub hard_constraint_digest: Digest32,
    pub protocol_digest: Digest32,
    pub protocol_bytes: Vec<u8>,
}

pub fn digest(value: &str) -> Digest32 {
    Digest32::of_bytes(value.as_bytes())
}

pub fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

pub fn trust(key: &SigningKey, revoked: bool) -> Value {
    json!({"schema_version":1,"agent_id":AGENT,"issuer_id":ISSUER,
        "key_epoch":1,"public_key_hex":hex(key.verifying_key().as_bytes()),
        "revoked":revoked,"thread_ids":[]})
}

pub fn signed_fixture(
    key: &SigningKey,
    spawn: u64,
    sequence: u64,
    run_id: &str,
    actions: ActionSet,
) -> Result<Fixture> {
    let now_ms = Utc::now().timestamp_millis();
    require(now_ms > 0, "host clock must be positive")?;
    let now = DateTime::from_timestamp_millis(now_ms).ok_or("invalid host timestamp")?;
    let deadline =
        DateTime::from_timestamp_millis(now_ms + 240_000).ok_or("invalid objective deadline")?;
    let profile = decode_admission_profile_json_v1(PROFILE.as_bytes())?;
    let legal = match actions {
        ActionSet::Read => vec!["read"],
        ActionSet::Abstain => Vec::new(),
    };
    let mut source = json!({
        "requestId":format!("request.{run_id}"),
        "principalScopeDigest":profile.principal_scope_digest.to_string(),
        "intentDigest":"0".repeat(64),
        "structuredIntent":{
            "successPredicates":[{"predicateId":"task.success","unit":"ratio","comparator":"gte",
                "boundQ32":4294967296_i64,"evidenceSourceId":"observer.isolated-file","terminal":false}],
            "terminalConditions":[{"predicateId":"task.terminal","unit":"boolean","comparator":"eq",
                "boundQ32":4294967296_i64,"evidenceSourceId":"observer.isolated-file","terminal":true}],
            "legalActionClasses":legal,"forbiddenActionClasses":[],"confirmationActionClasses":[],
            "constraints":[{"constraintId":"latency.ceiling","unit":"micros","comparator":"lte",
                "boundQ32":10000000,"evidenceSourceId":"observer.clock","terminal":false}],
            "softDimensions":[],
            "evidenceRequirements":[{"requirementId":"evidence.quality","evidenceSourceId":"observer.isolated-file",
                "minimumConfidencePpm":1000000,"terminal":true}],
            "resources":{"timeMicros":10000000,"tokenCount":0,"computeMicros":1000000,
                "memoryBytes":1048576,"networkBytes":0,"externalEffectCount":0},
            "risk":{"riskClass":"low","abstentionRule":"ask","rollbackClass":"none","compensationRequired":false},
            "provenance":{"sourceDigest":digest("Read the isolated qualification marker file; no external device effects.").to_string(),
                "normalizationProfileDigest":profile.expected_normalization_profile_digest.to_string()}
        },
        "sourceTrustClass":"authorized_adapter","locale":"en-US",
        "observedAt":now.to_rfc3339_opts(SecondsFormat::Millis, true),
        "deadline":deadline.to_rfc3339_opts(SecondsFormat::Millis, true),
        "inputSchemaDigest":profile.expected_input_schema_digest.to_string()
    });
    let decoded = decode_source_envelope_json_v1(&serde_json::to_vec(&source)?)?;
    source["intentDigest"] = canonical_objective_intent_digest_v1(&decoded)?
        .to_string()
        .into();
    let source_json = serde_json::to_string(&source)?;
    let decoded = decode_source_envelope_json_v1(source_json.as_bytes())?;
    let context = ObjectiveAdmissionContextV1 {
        revision: Revision::new(1)?,
        now_unix_micros: u64::try_from(now_ms)?
            .checked_mul(1_000)
            .ok_or("clock overflow")?,
        selected_profile_digest: profile.digest()?,
        source_authentication: ObjectiveSourceAuthenticationV1::AuthorizedAdapter {
            source_identity: StableId::new(ISSUER)?,
            source_digest: decoded.structured_intent.provenance.source_digest,
        },
    };
    let compiled = admit_and_compile_objective_v1(&decoded, &profile, &context)?;
    require(
        !compiled.receipt.authority.grants_any(),
        "fixture unexpectedly granted authority",
    )?;
    let objective = compiled
        .compile_result
        .map_err(|_| "unexpected fixture conflict")?;
    let protocol = encode_objective_function_v1(&objective, &decoded, &profile, &compiled.receipt)?;
    let mut request = AuthBusObjectiveIngress {
        issuer_id: ISSUER.to_string(),
        key_epoch: 1,
        message_id: format!("message.desktop-isolated.{sequence}"),
        sequence,
        expires_at_ms: u64::try_from(now_ms)? + 240_000,
        signature_hex: String::new(),
        body: AuthBusObjectiveBody {
            spawn_generation: spawn,
            run_id: run_id.to_string(),
            objective_revision: 1,
            source_envelope_json: source_json,
            runtime_body_digest: digest("isolated-no-effect-runtime-body-v1").to_string(),
            preference_state_digest: digest("isolated-preference-state-v1").to_string(),
            model_tuple_digest: digest("isolated-no-model-tuple-v1").to_string(),
            prompt_registry_digest: digest("isolated-no-prompt-registry-v1").to_string(),
            artifact_set_digest: digest("isolated-empty-artifact-set-v1").to_string(),
            authority_epoch: 1,
        },
    };
    sign(key, &mut request)?;
    Ok(Fixture {
        request,
        admission: compiled.receipt,
        objective_digest: objective.objective.semantic_digest,
        hard_constraint_digest: objective.objective.hard_constraint_digest,
        protocol_digest: protocol.protocol_digest(),
        protocol_bytes: protocol.canonical_bytes().to_vec(),
    })
}

pub fn sign(key: &SigningKey, request: &mut AuthBusObjectiveIngress) -> Result<()> {
    request.signature_hex = hex(&key.sign(&claims(request)?.signing_bytes()).to_bytes());
    Ok(())
}

pub fn claims(request: &AuthBusObjectiveIngress) -> Result<SignedMessageClaims> {
    let mut scope = b"hepta:agentd:signed-objective:v1\0".to_vec();
    scope.extend_from_slice(AGENT.as_bytes());
    Ok(SignedMessageClaims {
        issuer_id: StableId::new(&request.issuer_id)?,
        key_epoch: Generation::new(request.key_epoch)?,
        message_id: StableId::new(&request.message_id)?,
        subject_id: StableId::new(AGENT)?,
        scope_digest: Digest32::of_bytes(&scope),
        payload_digest: Digest32::of_bytes(&serde_json::to_vec(&request.body)?),
        sequence: request.sequence,
        expires_at_ms: request.expires_at_ms,
    })
}
