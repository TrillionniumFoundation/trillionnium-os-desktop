//! Same-source negative oracle for the generic native execution boundary.
//!
//! On old A03 86663ea the generic callback can mix a reservation with another
//! native owner or freshly resolved ancestry, despite checking all binding
//! fields it receives. The hardened API must reject this path before callback
//! admission. This models mistakes inside a trusted adapter; it is not an
//! unauthenticated HOS2 exploit or evidence of actual kernel integration.

use os_control::{
    BootId, CapSpaceId, ControlCore, DeliveryError, DeliveryState, DeliveryStatus,
    NativeDeliveryRequest, NativeGrant, NativeTarget, PublishOutcome, PublisherId, RequestBinding,
    ReserveToken, ResourceDomainId, StableObjectId,
};
use std::sync::{Arc, Mutex};

struct OracleOwner {
    id: ResourceDomainId,
    object: StableObjectId,
    mutation: Mutex<OracleState>,
}

struct OracleState {
    revision: u64,
    epoch: u64,
    ancestor: u64,
    effects: usize,
}

impl OracleOwner {
    fn new() -> Arc<Self> {
        Arc::new(Self {
            id: ResourceDomainId::from_u128(1),
            object: StableObjectId::from_u128(1),
            mutation: Mutex::new(OracleState {
                revision: 1,
                epoch: 1,
                ancestor: 1,
                effects: 0,
            }),
        })
    }

    fn apply(&self, binding: RequestBinding, expected_ancestors: &[u64]) -> PublishOutcome {
        let mut state = self.mutation.lock().unwrap();
        // These checks use the owner's original lock and every target and
        // authorization field the old callback receives. They cannot verify
        // a missing owner pointer or recover the reservation's saved ancestry.
        assert_eq!(binding.target, self.id);
        assert_eq!(binding.stable_object_id, self.object);
        assert_eq!(binding.publisher, publisher());
        assert_eq!(binding.grant_epoch, state.epoch);
        assert_eq!(binding.expected_revision, state.revision);
        if expected_ancestors != [state.ancestor] {
            return PublishOutcome::Failure {
                status: DeliveryStatus::Revoked,
            };
        }
        let previous = state.revision;
        state.revision += 1;
        state.effects += 1;
        PublishOutcome::Success {
            stable_object_id: self.object,
            previous_revision: previous,
            saved_revision: state.revision,
            effective_ns: 1,
            consumed_ns: 0,
        }
    }
}

fn publisher() -> PublisherId {
    PublisherId::from_u128(2)
}

fn reserve(owner: &Arc<OracleOwner>) -> (ControlCore, ReserveToken) {
    let core = ControlCore::new(BootId::from_u128(3), CapSpaceId::from_u128(4));
    let target = NativeTarget::from_owner(Arc::clone(owner), owner.id, owner.object).unwrap();
    let grant = NativeGrant::from_owner(target, publisher(), 1, vec![1]).unwrap();
    let request = NativeDeliveryRequest::from_wire(1, grant, 1, 17, 5, 6).unwrap();
    let token = core.reserve_native(request, publisher()).unwrap();
    (core, token)
}

#[test]
fn generic_native_callback_cannot_apply_a_different_owner_with_the_same_public_ids() {
    let original = OracleOwner::new();
    let other_instance = OracleOwner::new();
    let (core, token) = reserve(&original);
    let result = core.execute_reserved(&token, publisher(), |binding| {
        other_instance.apply(binding, &[1])
    });
    assert_eq!(
        other_instance.mutation.lock().unwrap().effects,
        0,
        "generic callback applied the wrong native Arc instance"
    );
    assert_eq!(original.mutation.lock().unwrap().effects, 0);
    assert_eq!(result, Err(DeliveryError::InvalidRequest));
    assert_eq!(
        core.query_delivery(&core.delivery_view(), 1).unwrap().state,
        DeliveryState::Reserved
    );
}

#[test]
fn generic_native_callback_cannot_replace_reserved_ancestry_with_fresh_context() {
    let original = OracleOwner::new();
    let (core, token) = reserve(&original);
    original.mutation.lock().unwrap().ancestor = 2; // Ancestor revoke/reactivate.
    let fresh_ancestry = [original.mutation.lock().unwrap().ancestor];
    let result = core.execute_reserved(&token, publisher(), |binding| {
        original.apply(binding, &fresh_ancestry)
    });
    assert_eq!(
        original.mutation.lock().unwrap().effects,
        0,
        "generic callback let fresh out-of-band ancestry authorize the old D"
    );
    assert_eq!(result, Err(DeliveryError::InvalidRequest));
    assert_eq!(
        core.query_delivery(&core.delivery_view(), 1).unwrap().state,
        DeliveryState::Reserved
    );
}
