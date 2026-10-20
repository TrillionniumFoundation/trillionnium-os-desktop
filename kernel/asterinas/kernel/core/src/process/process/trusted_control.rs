// SPDX-License-Identifier: MPL-2.0

//! Native capabilities in the original Process image, with the original D core.
//!
//! The operation gate serializes final use and image closure; it is not an
//! authority record. Lock order: operation gate -> brief image check (released)
//! -> os-control execution gate -> local runqueue -> original CPU owner.
//! Lifecycle marks Closing under TaskSet -> image, releases both, then waits
//! for this gate and revokes the owner's canonical grant. No image/table lock
//! spans the CPU mutation. Recovery views retain the same D namespace on exec.

use os_control::{
    BootId, CapSpaceId, ControlCoreWith, DeliveryError, DeliveryObservation,
    DeliveryState, DeliveryViewWith, NativeDeliveryRequest,
    OriginalOwnerAuthorityWith, OwnerId, ReserveAttemptWith,
};
use ostd::sync::Mutex;

use super::{KernelControlBackend, Process, ProcessImageKey};
use crate::{
    device::misc::{hepta_boot_id, hepta_image_space_id},
    fs::cgroupfs::{CpuUsageError, NativeCpuManager},
    hos2_os_abi::{self as wire, ResponsePayload, Status},
    prelude::*,
};

type KernelCore = ControlCoreWith<KernelControlBackend>;
type KernelHistoryView = DeliveryViewWith<KernelControlBackend>;
type KernelHistoryOwner = OriginalOwnerAuthorityWith<KernelControlBackend>;
pub(crate) type NativeResult = core::result::Result<(u64, ResponsePayload), Status>;

struct HistorySlot {
    core: KernelCore,
    view: KernelHistoryView,
    ack: Option<KernelHistoryOwner>,
}

/// The only G1-d slots. Constructors are reachable only from the sealed,
/// stopped bootstrap transaction; later exec/fork allocate none of them.
pub(super) struct TrustedControlSlots {
    key: ProcessImageKey,
    operation_gate: Mutex<()>,
    manager: Arc<NativeCpuManager>,
    core: KernelCore,
    manager_history: Arc<HistorySlot>,
    recovery_history: Option<Arc<HistorySlot>>,
}

impl TrustedControlSlots {
    pub(super) fn prepare_pair(
        managers: [Arc<NativeCpuManager>; 2],
        keys: [ProcessImageKey; 2],
    ) -> Result<[Arc<Self>; 2]> {
        let boot = BootId::new(hepta_boot_id());
        let manager_space = CapSpaceId::new(hepta_image_space_id(keys[0]));
        let recovery_space = CapSpaceId::new(hepta_image_space_id(keys[1]));
        let owner = OwnerId::new(recovery_space.bytes());
        let make_error = |_| Error::with_message(Errno::ENOMEM, "cannot create bounded native namespace");
        let (manager_core, manager_ack) = KernelCore::with_original_owner(boot, manager_space, owner)
            .map_err(make_error)?;
        let (recovery_core, recovery_ack) = KernelCore::with_original_owner(boot, recovery_space, owner)
            .map_err(make_error)?;
        let readonly = Arc::new(HistorySlot {
            view: manager_core.delivery_view(), core: manager_core.clone(), ack: None,
        });
        let retained = Arc::new(HistorySlot {
            view: manager_core.delivery_view_for(owner).map_err(make_error)?,
            core: manager_core.clone(), ack: Some(manager_ack),
        });
        let own = Arc::new(HistorySlot {
            view: recovery_core.delivery_view_for(owner).map_err(make_error)?,
            core: recovery_core.clone(), ack: Some(recovery_ack),
        });
        let [manager, recovery] = managers;
        Ok([
            Arc::new(Self { key: keys[0], operation_gate: Mutex::new(()), manager,
                core: manager_core, manager_history: readonly, recovery_history: None }),
            Arc::new(Self { key: keys[1], operation_gate: Mutex::new(()), manager: recovery,
                core: recovery_core, manager_history: retained, recovery_history: Some(own) }),
        ])
    }

    pub(super) fn belongs_to(&self, key: ProcessImageKey) -> bool { self.key == key }

    pub(super) fn revoke_after_image_close(&self) {
        let _gate = self.operation_gate.lock();
        self.manager.revoke();
    }

    fn install(&self, request: &wire::Request, payload: wire::InstallBudgetRequest) -> NativeResult {
        if request.target_slot != 2 || request.target_generation != 1 {
            return Err(Status::StaleHandle);
        }
        let sequence = u64::from_le_bytes(request.request_id[..8].try_into().unwrap());
        let native = NativeDeliveryRequest::from_wire(
            sequence, self.manager.grant(), payload.expected_revision, payload.cap_ns,
            request.target_slot, request.target_generation,
        ).map_err(delivery_error)?;
        let observation = match self.core.reserve_native_or_get(native, self.manager.publisher())
            .map_err(delivery_error)?
        {
            ReserveAttemptWith::Existing(observation) => observation,
            ReserveAttemptWith::Reserved(token) => {
                self.manager.execute(&self.core, &token).map_err(delivery_error)?
            }
        };
        install_observation(observation)
    }

    fn history(&self, slot: u64, generation: u64, payload: wire::DeliveryRequest)
        -> core::result::Result<&HistorySlot, Status>
    {
        if generation != 1 { return Err(Status::StaleHandle); }
        let history = match slot {
            3 => self.manager_history.as_ref(),
            4 => self.recovery_history.as_deref().ok_or(Status::StaleHandle)?,
            _ => return Err(Status::StaleHandle),
        };
        let identity = history.core.identity();
        if identity.boot_id().bytes() != payload.history_boot
            || identity.cap_space_id().bytes() != payload.history_space
        {
            return Err(Status::PermissionDenied);
        }
        Ok(history)
    }

    fn dispatch(&self, request: &wire::Request) -> NativeResult {
        match request.payload {
            wire::RequestPayload::ReadUsage => {
                if request.target_slot != 1 || request.target_generation != 1 {
                    return Err(Status::StaleHandle);
                }
                let usage = self.manager.read_usage().map_err(|error| match error {
                    CpuUsageError::Unbound | CpuUsageError::Closed | CpuUsageError::Expired => Status::Revoked,
                    _ => Status::Indeterminate,
                })?;
                Ok((usage.revision, ResponsePayload::ReadUsage(wire::ReadUsageResponse {
                    sample_boottime_ns: usage.sample_boottime_ns,
                    cumulative_cpu_ns: usage.cumulative_cpu_ns,
                    window_start_ns: usage.window_start_ns,
                    window_consumed_ns: usage.window_consumed_ns,
                    active_cap_ns: usage.active_cap_ns,
                    active_period_ns: usage.active_period_ns,
                    event_sequence: usage.event_sequence,
                    dropped_events: usage.dropped_events,
                })))
            }
            wire::RequestPayload::InstallBudget(payload) => self.install(request, payload),
            wire::RequestPayload::QueryDelivery(payload) => {
                let history = self.history(request.target_slot, request.target_generation, payload)?;
                let observation = history.core.query_delivery(&history.view, payload.sequence)
                    .map_err(delivery_error)?;
                query_observation(observation)
            }
            wire::RequestPayload::RetireThrough(payload) => {
                let history = self.history(request.target_slot, request.target_generation, payload)?;
                let authority = history.ack.as_ref().ok_or(Status::PermissionDenied)?;
                // This opt-in qualification image is the trusted ack holder.
                // The tag records this exact namespace/frontier claim; it is
                // explicitly NOT a Hepta SQLite durability or fsync receipt.
                let mut claim = [0u8; 32];
                claim[..16].copy_from_slice(&payload.history_space);
                claim[16..24].copy_from_slice(&payload.sequence.to_le_bytes());
                claim[24..].copy_from_slice(b"G1DQUAL1");
                let ack = authority.history_ack(payload.sequence, claim).map_err(delivery_error)?;
                let receipt = history.core.retire_through(&history.view, ack, authority)
                    .map_err(delivery_error)?;
                Ok((0, ResponsePayload::RetireThrough(wire::RetireThroughResponse {
                    retired_through: receipt.retired_through, next_sequence: receipt.next_sequence,
                })))
            }
            wire::RequestPayload::QueryAbi => Err(Status::InvalidInput),
        }
    }
}

impl Process {
    /// Resolve a real image slot, acquire its final-use gate, then recheck the
    /// image. Never keep the image lock while entering another owner.
    pub(crate) fn dispatch_hepta_control(&self, key: ProcessImageKey, request: &wire::Request)
        -> NativeResult
    {
        let slots = self.hepta_image.lock().initial_control(key)?.clone();
        let _gate = slots.operation_gate.lock();
        self.hepta_image.lock().initial_control(key)?;
        slots.dispatch(request)
    }

    /// Called only outside TaskSet/image/VMAR locks after Closing admission.
    /// The gate waits for synchronous admitted effects and their saved result,
    /// then the canonical owner lock fences future uses of this delegation.
    pub(in crate::process) fn revoke_closing_hepta_control(&self) {
        let slots = self.hepta_image.lock().closing_control();
        if let Some(slots) = slots { slots.revoke_after_image_close(); }
    }
}

fn delivery_error(error: DeliveryError) -> Status {
    match error {
        DeliveryError::InvalidSequence | DeliveryError::InvalidRequest
            | DeliveryError::InvalidIdentity | DeliveryError::InvalidCapacity
            | DeliveryError::InvalidAck => Status::InvalidInput,
        DeliveryError::PermissionDenied => Status::PermissionDenied,
        DeliveryError::Conflict => Status::Conflict,
        DeliveryError::ResourceExhausted => Status::ResourceExhausted,
        DeliveryError::Busy | DeliveryError::PendingPrefix => Status::Busy,
        DeliveryError::OutOfOrder { .. } | DeliveryError::NotSeen => Status::OutOfOrder,
        DeliveryError::Retired => Status::Retired,
        DeliveryError::HistoryLost | DeliveryError::TerminalImmutable
            | DeliveryError::InvalidPublish => Status::Indeterminate,
    }
}

fn install_observation(observation: DeliveryObservation) -> NativeResult {
    if observation.hos2_saved_status_code().is_none() { return Err(Status::Indeterminate); }
    if observation.state != DeliveryState::Terminal {
        return Err(match observation.state {
            DeliveryState::Reserved => Status::Busy,
            DeliveryState::Retired => Status::Retired,
            _ => Status::Indeterminate,
        });
    }
    let status = Status::from_u16(observation.status.ok_or(Status::Indeterminate)?.hos2_code())
        .map_err(|_| Status::Indeterminate)?;
    if status != Status::Ok { return Err(status); }
    Ok((observation.saved_revision.ok_or(Status::Indeterminate)?,
        ResponsePayload::InstallBudget(wire::InstallBudgetResponse {
            previous_revision: observation.previous_revision.ok_or(Status::Indeterminate)?,
            effective_boottime_ns: observation.effective_ns.ok_or(Status::Indeterminate)?,
            consumed_at_apply_ns: observation.consumed_ns.ok_or(Status::Indeterminate)?,
        })))
}

fn query_observation(observation: DeliveryObservation) -> NativeResult {
    let saved_status = Status::from_u16(observation.hos2_saved_status_code()
        .ok_or(Status::Indeterminate)?).map_err(|_| Status::Indeterminate)?;
    let state = wire::DeliveryState::from_u16(observation.state.hos2_code())
        .map_err(|_| Status::Indeterminate)?;
    Ok((0, ResponsePayload::QueryDelivery(wire::QueryDeliveryResponse {
        state, saved_status, sequence: observation.id.sequence,
        stable_object_id: observation.stable_object_id.map_or([0; 16], |id| id.bytes()),
        saved_revision: observation.saved_revision.unwrap_or(0),
        previous_revision: observation.previous_revision.unwrap_or(0),
        effective_ns: observation.effective_ns.unwrap_or(0),
        consumed_ns: observation.consumed_ns.unwrap_or(0),
    })))
}
