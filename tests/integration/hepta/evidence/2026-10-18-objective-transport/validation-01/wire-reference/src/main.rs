use serde::{Deserialize, Serialize};
mod agent_id;
use agent_id::AgentId;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AuthBusObjectiveBody {
    pub spawn_generation: u64,
    pub run_id: String,
    pub objective_revision: u64,
    pub source_envelope_json: String,
    pub runtime_body_digest: String,
    pub preference_state_digest: String,
    pub model_tuple_digest: String,
    pub prompt_registry_digest: String,
    pub artifact_set_digest: String,
    pub authority_epoch: u64,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AuthBusObjectiveIngress {
    pub issuer_id: String,
    pub key_epoch: u64,
    pub message_id: String,
    pub sequence: u64,
    pub expires_at_ms: u64,
    pub signature_hex: String,
    pub body: AuthBusObjectiveBody,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ObjectiveRunAdmission {
    pub run_id: String,
    pub objective_digest: String,
    pub hard_constraint_digest: String,
    pub publication_digest: String,
    pub chain_digest: String,
    pub disposition: String,
    pub idempotent: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum ObjectiveStartOutcome {
    Admitted {
        receipt: ObjectiveRunAdmission,
    },
    Conflict {
        run_id: String,
        conflict_digest: String,
    },
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AgentdRequest {
    pub schema_version: u32,
    pub request_id: u64,
    pub spawn_generation: u64,
    pub method: AgentdMethod,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AgentdResponse {
    pub schema_version: u32,
    pub request_id: u64,
    pub agent_id: AgentId,
    pub spawn_generation: u64,
    pub current_generation: u64,
    pub payload: AgentdPayload,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum AgentdMethod {
    ObjectiveStart {
        request: AuthBusObjectiveIngress,
    },
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum AgentdPayload {
    ObjectiveRun(ObjectiveRunAdmission),
    ObjectiveConflict {
        run_id: String,
        conflict_digest: String,
    },
    Error {
        code: String,
        message: String,
    },
}

fn digest(byte: char) -> String {
    byte.to_string().repeat(64)
}

fn ingress() -> AuthBusObjectiveIngress {
    AuthBusObjectiveIngress {
        issuer_id: "issuer.objective".to_string(),
        key_epoch: 1,
        message_id: "objective.message.1".to_string(),
        sequence: 1,
        expires_at_ms: 9_999_999,
        signature_hex: "00".repeat(64),
        body: AuthBusObjectiveBody {
            spawn_generation: 3,
            run_id: "run.objective.1".to_string(),
            objective_revision: 1,
            source_envelope_json: "{\"requestId\":\"request.1\"}".to_string(),
            runtime_body_digest: digest('1'),
            preference_state_digest: digest('2'),
            model_tuple_digest: digest('3'),
            prompt_registry_digest: digest('4'),
            artifact_set_digest: digest('5'),
            authority_epoch: 7,
        },
    }
}


fn main() {
    let raw = include_str!("../fixture.json");
    let provided: AuthBusObjectiveIngress = serde_json::from_str(raw).unwrap();
    assert_eq!(provided, ingress(), "fixture must equal the unchanged original wire-only factory");
    let supplied: serde_json::Value = serde_json::from_str(raw).unwrap();
    let request_json = serde_json::json!({
        "schema_version":2, "request_id":41, "spawn_generation":3,
        "method":{"type":"objective_start", "request":supplied}
    });
    let request: AgentdRequest = serde_json::from_value(request_json.clone()).unwrap();
    assert_eq!(request.method, AgentdMethod::ObjectiveStart { request: provided });
    assert_eq!(serde_json::to_value(&request).unwrap(), request_json);
    let mut frame = serde_json::to_vec(&request).unwrap();
    frame.push(b'\n');
    assert!(frame.len() <= 65_536);

    let admission = ObjectiveRunAdmission {
        run_id:"run.objective.1".to_owned(), objective_digest:digest('1'),
        hard_constraint_digest:digest('2'), publication_digest:digest('3'),
        chain_digest:digest('4'), disposition:"compiled".to_owned(), idempotent:false
    };
    let payload = serde_json::to_value(AgentdPayload::ObjectiveRun(admission.clone())).unwrap();
    let expected = serde_json::json!({
        "type":"objective_run", "run_id":"run.objective.1", "objective_digest":digest('1'),
        "hard_constraint_digest":digest('2'), "publication_digest":digest('3'),
        "chain_digest":digest('4'), "disposition":"compiled", "idempotent":false
    });
    assert_eq!(payload, expected);
    let _: AgentdPayload = serde_json::from_value(payload.clone()).unwrap();
    let outcome = serde_json::to_value(ObjectiveStartOutcome::Admitted { receipt:admission }).unwrap();
    assert_eq!(outcome["type"], "admitted");
    assert!(outcome.get("receipt").is_some());
    assert!(serde_json::from_value::<AgentdPayload>(outcome).is_err());

    let response = AgentdResponse {
        schema_version:2, request_id:41,
        agent_id:AgentId::parse("11111111-1111-4111-8111-111111111111").unwrap(),
        spawn_generation:3, current_generation:4,
        payload:serde_json::from_value(payload.clone()).unwrap()
    };
    let response_json = serde_json::json!({
        "schema_version":2, "request_id":41, "agent_id":"11111111-1111-4111-8111-111111111111",
        "spawn_generation":3, "current_generation":4, "payload":payload
    });
    assert_eq!(serde_json::to_value(&response).unwrap(), response_json);
    assert_eq!(serde_json::from_value::<AgentdResponse>(response_json).unwrap(), response);
    for value in [
        serde_json::json!({"type":"objective_conflict", "run_id":"run.objective.1", "conflict_digest":digest('6')}),
        serde_json::json!({"type":"error", "code":"request_rejected", "message":"wire-only fixture"})
    ] {
        let payload: AgentdPayload = serde_json::from_value(value.clone()).unwrap();
        assert_eq!(serde_json::to_value(payload).unwrap(), value);
    }
    let duplicate = raw.replacen("\"issuer_id\":", "\"issuer_id\":\"duplicate\",\"issuer_id\":", 1);
    assert!(serde_json::from_str::<AuthBusObjectiveIngress>(&duplicate).is_err());
    let mut unknown: serde_json::Value = serde_json::from_str(raw).unwrap();
    unknown["body"]["unexpected"] = serde_json::json!(true);
    assert!(serde_json::from_value::<AuthBusObjectiveIngress>(unknown).is_err());
    println!("{}", serde_json::json!({
        "status":"passed", "qualification":"original serde declarations and wire-only fixture; no original runtime/authentication",
        "checks":["original_fixture", "objective_start_request", "flat_objective_run_payload", "client_outcome_is_distinct", "response_envelope", "conflict_and_error_payloads", "strict_fields"],
        "original_agentd_started":false, "signature_created":false, "objective_submitted":false
    }));
}

