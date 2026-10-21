//! Read one retained CPU delivery through the existing HOS2 history operation.
//!
//! The production writer supplies its original canonical outbox payload and
//! operation binding, plus an authenticated history transport. Validation
//! here is structural and correlational; it does not authenticate that owner,
//! create a durable binding, grant authority, or confirm a durable result.
//! No install, retry, ID allocation, acknowledgement, or retirement API exists.

use hos2_os_abi::{
    DeliveryRequest, DeliveryState, Opcode, Request, RequestPayload, Response, ResponsePayload,
    Status, HEADER_LEN,
};

#[path = "cpu_owner.rs"]
mod owner;
use owner::decode_owner_payload;

pub const INSTALL_FRAME_BYTES: usize = HEADER_LEN + 32;
pub const HISTORY_REQUEST_BYTES: usize = HEADER_LEN + 40;
pub const HISTORY_RESPONSE_BYTES: usize = HEADER_LEN + 64;

/// Values from the existing ProductionDurableWriter/LocalLeaseOutbox owner.
/// K is operation_id. Scope is a digest constraint, never a fabricated scope_id.
/// Owner generation is a fence, distinct from the semantic policy generation.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CpuDeliveryIdentity {
    pub operation_id: String,
    pub subject_id: String,
    pub payload_digest: [u8; 32],
    pub scope_digest: [u8; 32],
    pub semantic_digest: [u8; 32],
    pub policy_generation: u64,
    pub owner_generation: u64,
}

/// Original native namespace and sequence decoded from the immutable payload.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct CpuDeliveryId {
    pub boot_id: [u8; 16],
    pub capspace_id: [u8; 16],
    pub sequence: u64,
}

/// The *current* history-view handle supplied by the trusted native host. It
/// need not equal the management handle recorded in the old InstallBudget.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct HistoryView {
    pub slot: u64,
    pub generation: u64,
}

/// A narrow host transport. Implementations must authenticate their actual
/// kernel endpoint and bound their I/O lifetime; a codec cannot prove origin.
/// Entry must remain inside the original writer's dispatch/observer exclusion
/// gate, after it refuses disabled or contradictory original operations.
pub trait CpuHistoryTransport {
    type Error;

    fn query_delivery(
        &mut self,
        request: &[u8; HISTORY_REQUEST_BYTES],
        response: &mut [u8; HISTORY_RESPONSE_BYTES],
    ) -> Result<usize, Self::Error>;
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BindingError {
    InvalidOwnerIdentity,
    InvalidDeliveryIdentity,
    InvalidOwnerPayload,
    PayloadDigestMismatch,
    ScopeDigestMismatch,
    SemanticDigestMismatch,
    MalformedInstall,
}

#[derive(Debug, PartialEq, Eq)]
pub enum HistoryError<E> {
    InvalidQuery,
    Transport(E),
    MalformedResponse,
    BootChanged,
    RevisionChanged,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum UnknownReason {
    Reserved,
    Retired,
    NotSeen,
    HistoryLost,
    OuterStatus(Status),
    SavedStatus(Status),
}

/// A correlated native observation, still requiring the original owner to
/// authenticate its origin and persist the result before any retirement.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CpuHistoryObservation {
    Installed {
        stable_object_id: [u8; 16],
        revision: u64,
        previous_revision: u64,
        effective_ns: u64,
        consumed_ns: u64,
    },
    TerminalRejection(Status),
    Unknown(UnknownReason),
}

/// Immutable snapshot of an existing owner record. No new K or D is minted.
/// Missing original-owner persistence is an assembly blocker, not a reason to
/// reconstruct this snapshot from a renderer draft or current resource state.
#[derive(Debug)]
pub struct RecordedCpuDelivery {
    identity: CpuDeliveryIdentity,
    delivery: CpuDeliveryId,
    payload_json: String,
    install_frame: [u8; INSTALL_FRAME_BYTES],
    expected_revision: u64,
}

impl RecordedCpuDelivery {
    /// Decode an existing production owner record. The host must first verify
    /// that the original K is eligible for observation under its live owner
    /// fence and use gate. This structural constructor supplies no such proof.
    pub fn from_owner_record(
        identity: CpuDeliveryIdentity,
        payload_json: &str,
    ) -> Result<Self, BindingError> {
        let (delivery, request) = decode_owner_payload(&identity, payload_json)?;
        let RequestPayload::InstallBudget(budget) = request.payload else {
            return Err(BindingError::MalformedInstall);
        };
        let mut install_frame = [0; INSTALL_FRAME_BYTES];
        request
            .encode(&mut install_frame)
            .map_err(|_| BindingError::MalformedInstall)?;
        Ok(Self {
            identity,
            delivery,
            payload_json: payload_json.to_owned(),
            install_frame,
            expected_revision: budget.expected_revision,
        })
    }

    pub fn identity(&self) -> &CpuDeliveryIdentity {
        &self.identity
    }

    pub fn delivery_id(&self) -> CpuDeliveryId {
        self.delivery
    }

    pub fn recorded_payload_json(&self) -> &str {
        &self.payload_json
    }

    pub fn recorded_install_bytes(&self) -> &[u8; INSTALL_FRAME_BYTES] {
        &self.install_frame
    }

    /// One QueryDelivery for the retained D. Transport/validation errors keep
    /// the old operation unresolved. This method never reconnects, writes an
    /// InstallBudget, allocates a new delivery, or treats missing history as
    /// proof of no effect. The read request ID is supplied by the host.
    pub fn query_once<T: CpuHistoryTransport>(
        &self,
        transport: &mut T,
        view: HistoryView,
        request_id: [u8; 16],
    ) -> Result<CpuHistoryObservation, HistoryError<T::Error>> {
        let request = Request {
            opcode: Opcode::QueryDelivery,
            request_id,
            target_slot: view.slot,
            target_generation: view.generation,
            payload: RequestPayload::QueryDelivery(DeliveryRequest {
                history_boot: self.delivery.boot_id,
                history_space: self.delivery.capspace_id,
                sequence: self.delivery.sequence,
            }),
        };
        let mut request_frame = [0; HISTORY_REQUEST_BYTES];
        request
            .encode(&mut request_frame)
            .map_err(|_| HistoryError::InvalidQuery)?;
        let mut response_frame = [0; HISTORY_RESPONSE_BYTES];
        let length = transport
            .query_delivery(&request_frame, &mut response_frame)
            .map_err(HistoryError::Transport)?;
        let bytes = response_frame
            .get(..length)
            .ok_or(HistoryError::MalformedResponse)?;
        let response = Response::decode(bytes).map_err(|_| HistoryError::MalformedResponse)?;
        response
            .validate_for(&request)
            .map_err(|_| HistoryError::MalformedResponse)?;
        if response.boot_id != self.delivery.boot_id {
            return Err(HistoryError::BootChanged);
        }
        if response.status != Status::Ok {
            return Ok(CpuHistoryObservation::Unknown(UnknownReason::OuterStatus(
                response.status,
            )));
        }
        let ResponsePayload::QueryDelivery(saved) = response.payload else {
            return Err(HistoryError::MalformedResponse);
        };
        let unknown = match saved.state {
            DeliveryState::Reserved => Some(UnknownReason::Reserved),
            DeliveryState::Retired => Some(UnknownReason::Retired),
            DeliveryState::NotSeen => Some(UnknownReason::NotSeen),
            DeliveryState::HistoryLost => Some(UnknownReason::HistoryLost),
            DeliveryState::Terminal => None,
        };
        if let Some(reason) = unknown {
            return Ok(CpuHistoryObservation::Unknown(reason));
        }
        if matches!(saved.saved_status, Status::Indeterminate | Status::Busy) {
            return Ok(CpuHistoryObservation::Unknown(UnknownReason::SavedStatus(
                saved.saved_status,
            )));
        }
        if saved.saved_status != Status::Ok {
            return Ok(CpuHistoryObservation::TerminalRejection(saved.saved_status));
        }
        if saved.previous_revision != self.expected_revision {
            return Err(HistoryError::RevisionChanged);
        }
        Ok(CpuHistoryObservation::Installed {
            stable_object_id: saved.stable_object_id,
            revision: saved.saved_revision,
            previous_revision: saved.previous_revision,
            effective_ns: saved.effective_ns,
            consumed_ns: saved.consumed_ns,
        })
    }
}
