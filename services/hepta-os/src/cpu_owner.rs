//! Bounded decoder for the pinned production owner's immutable outbox payload.
//! The schema and digest framing are pinned in CPU_UPSTREAM_CONTRACT.json.
//! Recomputing them checks correlation, never authority or durable provenance.

use hos2_os_abi::{
    install_budget_request_id, InstallBudgetRequest, Opcode, Request, RequestPayload,
};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use super::{BindingError, CpuDeliveryId, CpuDeliveryIdentity};

const MAX_PAYLOAD_BYTES: usize = 1024;
const DESTINATION: &str = "hos2.cpu-budget.v1";

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Delivery {
    boot_id: [u8; 16],
    space_id: [u8; 16],
    sequence: String,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Install {
    schema_version: u32,
    delivery: Delivery,
    manage_slot: u64,
    manage_generation: u64,
    expected_revision: u64,
    period_ns: u64,
    cap_ns: u64,
}

pub(super) fn decode_owner_payload(
    identity: &CpuDeliveryIdentity,
    payload_json: &str,
) -> Result<(CpuDeliveryId, Request), BindingError> {
    if !valid_id(&identity.operation_id)
        || !valid_id(&identity.subject_id)
        || identity.policy_generation == 0
        || identity.owner_generation == 0
    {
        return Err(BindingError::InvalidOwnerIdentity);
    }
    if payload_json.len() > MAX_PAYLOAD_BYTES {
        return Err(BindingError::InvalidOwnerPayload);
    }
    let payload: Install =
        serde_json::from_str(payload_json).map_err(|_| BindingError::InvalidOwnerPayload)?;
    if payload.schema_version != 1
        || serde_json::to_string(&payload).map_err(|_| BindingError::InvalidOwnerPayload)?
            != payload_json
    {
        return Err(BindingError::InvalidOwnerPayload);
    }
    let sequence = u64::from_str_radix(&payload.delivery.sequence, 16)
        .map_err(|_| BindingError::InvalidDeliveryIdentity)?;
    if payload.delivery.boot_id == [0; 16]
        || payload.delivery.space_id == [0; 16]
        || sequence == 0
        || sequence == u64::MAX
        || payload.delivery.sequence != format!("{sequence:016x}")
    {
        return Err(BindingError::InvalidDeliveryIdentity);
    }
    let request = Request {
        opcode: Opcode::InstallBudget,
        request_id: install_budget_request_id(sequence)
            .map_err(|_| BindingError::MalformedInstall)?,
        target_slot: payload.manage_slot,
        target_generation: payload.manage_generation,
        payload: RequestPayload::InstallBudget(InstallBudgetRequest {
            expected_revision: payload.expected_revision,
            period_ns: payload.period_ns,
            cap_ns: payload.cap_ns,
            reserved: 0,
        }),
    };
    let payload_digest: [u8; 32] = Sha256::digest(payload_json.as_bytes()).into();
    if identity.payload_digest != payload_digest {
        return Err(BindingError::PayloadDigestMismatch);
    }
    let mut scope = Sha256::new();
    scope.update(b"hepta.hos2.cpu-budget.scope.v1\0");
    scope.update(payload.delivery.boot_id);
    scope.update(payload.delivery.space_id);
    scope.update(payload.manage_slot.to_le_bytes());
    scope.update(payload.manage_generation.to_le_bytes());
    let scope_digest: [u8; 32] = scope.finalize().into();
    if identity.scope_digest != scope_digest {
        return Err(BindingError::ScopeDigestMismatch);
    }
    let mut semantic = Sha256::new();
    semantic.update(b"hepta.kernel.operations.operation-intent.v1\0");
    for value in [
        identity.operation_id.as_str(),
        identity.subject_id.as_str(),
        DESTINATION,
    ] {
        semantic.update((value.len() as u32).to_be_bytes());
        semantic.update(value.as_bytes());
    }
    semantic.update(payload_digest);
    semantic.update(scope_digest);
    semantic.update(identity.policy_generation.to_be_bytes());
    // The existing HOS2 destination rejects an expected-predecessor CAS value.
    semantic.update([0]);
    let semantic_digest: [u8; 32] = semantic.finalize().into();
    if identity.semantic_digest != semantic_digest {
        return Err(BindingError::SemanticDigestMismatch);
    }
    Ok((
        CpuDeliveryId {
            boot_id: payload.delivery.boot_id,
            capspace_id: payload.delivery.space_id,
            sequence,
        },
        request,
    ))
}

fn valid_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b':' | b'-'))
}
