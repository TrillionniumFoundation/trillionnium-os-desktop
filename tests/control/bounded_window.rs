//! Native-window wrap and partial-retirement regressions on a host only.
//!
//! The synthetic owner counts committed effects under one host mutex. No
//! ResourceDomain, kernel scheduler, allocator proof, usercopy or durable
//! Hepta state is implemented by these tests.

use os_control::{
    BootId, CapSpaceId, ControlCore, DeliveryError, DeliveryObservation, DeliveryState,
    DeliveryStatus, HistoryAck, NativeDeliveryRequest, NativeGrant, NativeTarget,
    OriginalOwnerAuthority, OwnerId, PublishOutcome, PublisherId, RequestBinding,
    ReserveAttempt, ReserveToken, ResourceDomainId, StableObjectId,
};
use std::collections::VecDeque;
use std::sync::{Arc, Mutex};

const WRITES: u64 = 10_000;

fn publisher() -> PublisherId {
    PublisherId::from_u128(1_700_001)
}

fn history_owner() -> OwnerId {
    OwnerId::from_u128(1_700_002)
}

struct Owner {
    id: ResourceDomainId,
    object: StableObjectId,
    mutation: Mutex<EffectState>,
}

struct EffectState {
    revision: u64,
    effects: u64,
}

impl Owner {
    fn new(id: u128) -> Arc<Self> {
        Arc::new(Self {
            id: ResourceDomainId::from_u128(id),
            object: StableObjectId::from_u128(id + 1),
            mutation: Mutex::new(EffectState {
                revision: 1,
                effects: 0,
            }),
        })
    }

    fn request(self: &Arc<Self>, sequence: u64) -> NativeDeliveryRequest {
        let revision = self.mutation.lock().unwrap().revision;
        let target = NativeTarget::from_owner(Arc::clone(self), self.id, self.object).unwrap();
        let grant = NativeGrant::from_owner(target, publisher(), 1, Vec::new()).unwrap();
        NativeDeliveryRequest::from_wire(sequence, grant, revision, sequence % 97, 7, 13)
            .unwrap()
            .with_payload_digest([0x8d; 32])
    }

    fn apply(&self, binding: RequestBinding, ancestors: &[u64]) -> PublishOutcome {
        let mut state = self.mutation.lock().unwrap();
        assert_eq!(binding.target, self.id);
        assert_eq!(binding.stable_object_id, self.object);
        assert_eq!(binding.publisher, publisher());
        assert_eq!(binding.grant_epoch, 1);
        assert!(ancestors.is_empty());
        assert_eq!(binding.expected_revision, state.revision);
        let previous = state.revision;
        state.revision += 1;
        state.effects += 1;
        PublishOutcome::Success {
            stable_object_id: self.object,
            previous_revision: previous,
            saved_revision: state.revision,
            effective_ns: previous,
            consumed_ns: 0,
        }
    }

    fn effects(&self) -> u64 {
        self.mutation.lock().unwrap().effects
    }
}

fn namespace(id: u128, capacity: usize) -> (ControlCore, OriginalOwnerAuthority) {
    ControlCore::with_capacity_for_owner(
        BootId::from_u128(id),
        CapSpaceId::from_u128(id + 1),
        capacity,
        history_owner(),
    )
    .unwrap()
}

fn ack(authority: &OriginalOwnerAuthority, through: u64) -> HistoryAck {
    authority.history_ack(through, [0x8d; 32]).unwrap()
}

fn execute(core: &ControlCore, token: &ReserveToken) -> DeliveryObservation {
    core.execute_native_reserved::<Owner, _>(token, publisher(), |context| {
        context
            .owner()
            .apply(context.binding(), context.ancestor_epochs())
    })
    .unwrap()
}

#[test]
fn odd_windows_survive_ten_thousand_writes_with_only_partial_prefix_retirement() {
    for capacity in [3, 17] {
        let (core, authority) = namespace(1_710_000 + capacity as u128, capacity);
        let owner = Owner::new(1_710_100 + capacity as u128);
        let view = core.delivery_view_for(history_owner()).unwrap();
        let mut live = VecDeque::new();
        let mut retired = 0;
        let mut first_request = None;
        for sequence in 1..=WRITES {
            if live.len() == capacity {
                let count = if capacity == 3 { 1 } else { 5 };
                let through = live[count - 1];
                let before_next = core.next_sequence();
                let receipt = core
                    .retire_through(&view, ack(&authority, through), &authority)
                    .unwrap();
                for _ in 0..count {
                    live.pop_front();
                }
                retired = through;
                assert!(
                    !live.is_empty(),
                    "exercise repeated partial retirement, not flushes"
                );
                assert_eq!(receipt.retired_through, retired);
                assert_eq!(receipt.next_sequence, before_next);
                assert_eq!(core.retired_through(), retired);
                assert_eq!(core.window_len(), capacity - count);
                assert_eq!(
                    core.retire_through(&view, ack(&authority, 1), &authority)
                        .unwrap(),
                    receipt
                );
                assert_eq!(
                    core.query_delivery(&view, retired).unwrap().state,
                    DeliveryState::Retired
                );
                assert_eq!(
                    core.query_delivery(&view, *live.front().unwrap())
                        .unwrap()
                        .state,
                    DeliveryState::Terminal
                );
            }
            let request = owner.request(sequence);
            if first_request.is_none() {
                first_request = Some(request.clone());
            }
            let token = core.reserve_native(request.clone(), publisher()).unwrap();
            let terminal = execute(&core, &token);
            assert_eq!(terminal.status, Some(DeliveryStatus::Ok));
            assert_eq!(terminal.saved_revision, Some(sequence + 1));
            assert_eq!(
                core.execute_native_reserved::<Owner, _>(&token, publisher(), |_| {
                    panic!("one native D produced a second effect")
                })
                .unwrap(),
                terminal
            );
            match core.reserve_native_or_get(request, publisher()).unwrap() {
                ReserveAttempt::Existing(result) => assert_eq!(result, terminal),
                ReserveAttempt::Reserved(_) => panic!("same D reserved a second slot"),
            }
            live.push_back(sequence);
            assert_eq!(core.next_sequence(), sequence + 1);
            assert_eq!(core.retired_through(), retired);
            assert_eq!(core.window_len(), live.len());
            assert_eq!(owner.effects(), sequence);
            if retired > 0 && sequence % 131 == 0 {
                assert_eq!(
                    core.reserve_native(first_request.as_ref().unwrap().clone(), publisher())
                        .err(),
                    Some(DeliveryError::Retired)
                );
                core.validate_invariants_for_host_model().unwrap();
            }
        }
        let receipt = core
            .retire_through(&view, ack(&authority, WRITES), &authority)
            .unwrap();
        assert_eq!(receipt.retired_through, WRITES);
        assert_eq!(receipt.next_sequence, WRITES + 1);
        assert_eq!(core.window_len(), 0);
        assert_eq!(core.retired_through(), WRITES);
        assert_eq!(
            core.reserve_native(first_request.unwrap(), publisher())
                .err(),
            Some(DeliveryError::Retired)
        );
        assert_eq!(owner.effects(), WRITES);
        core.validate_invariants_for_host_model().unwrap();
    }
}

#[test]
fn pending_head_blocks_full_odd_window_until_no_effect_resolution_then_partial_wrap_continues() {
    let capacity = 17;
    let (core, authority) = namespace(1_720_000, capacity);
    let owner = Owner::new(1_720_100);
    let view = core.delivery_view_for(history_owner()).unwrap();
    let pending_request = owner.request(1);
    let pending = core
        .reserve_native(pending_request.clone(), publisher())
        .unwrap();
    let mut live = VecDeque::from([1_u64]);
    let mut last_terminal_request = None;
    let mut last_terminal_result = None;
    for sequence in 2..=capacity as u64 {
        let request = owner.request(sequence);
        let token = core.reserve_native(request.clone(), publisher()).unwrap();
        let terminal = execute(&core, &token);
        live.push_back(sequence);
        last_terminal_request = Some(request);
        last_terminal_result = Some(terminal);
    }
    assert_eq!(owner.effects(), capacity as u64 - 1);
    assert_eq!(core.window_len(), capacity);
    assert_eq!(core.next_sequence(), capacity as u64 + 1);
    assert_eq!(
        core.reserve_native(owner.request(capacity as u64 + 1), publisher())
            .err(),
        Some(DeliveryError::ResourceExhausted)
    );
    assert_eq!(
        core.reserve_native(pending_request.clone(), publisher())
            .err(),
        Some(DeliveryError::Busy)
    );
    match core
        .reserve_native_or_get(last_terminal_request.unwrap(), publisher())
        .unwrap()
    {
        ReserveAttempt::Existing(result) => assert_eq!(Some(result), last_terminal_result),
        ReserveAttempt::Reserved(_) => panic!("full-window terminal retry allocated another slot"),
    }
    assert_eq!(
        core.query_delivery(&view, 1).unwrap().state,
        DeliveryState::Reserved
    );
    for sequence in 2..=capacity as u64 {
        assert_eq!(
            core.query_delivery(&view, sequence).unwrap().state,
            DeliveryState::Terminal
        );
    }
    assert_eq!(
        core.retire_through(&view, ack(&authority, capacity as u64), &authority),
        Err(DeliveryError::PendingPrefix)
    );
    assert_eq!(core.retired_through(), 0);
    assert_eq!(core.window_len(), capacity);
    assert_eq!(core.next_sequence(), capacity as u64 + 1);

    // This synthetic executor never entered the head callback; publishing a
    // known no-effect refusal resolves it without inventing a CPU effect.
    let refusal = core
        .publish(
            &pending,
            publisher(),
            PublishOutcome::Failure {
                status: DeliveryStatus::Revoked,
            },
        )
        .unwrap();
    assert_eq!(refusal.status, Some(DeliveryStatus::Revoked));
    assert_eq!(owner.effects(), capacity as u64 - 1);
    assert_eq!(
        core.execute_native_reserved::<Owner, _>(&pending, publisher(), |_| {
            panic!("resolved refusal became executable")
        })
        .unwrap(),
        refusal
    );
    core.retire_through(&view, ack(&authority, 4), &authority)
        .unwrap();
    for _ in 0..4 {
        live.pop_front();
    }
    let mut retired = 4;
    assert_eq!(core.window_len(), capacity - 4);
    for sequence in capacity as u64 + 1..=WRITES {
        if live.len() == capacity {
            let through = live[2];
            let receipt = core
                .retire_through(&view, ack(&authority, through), &authority)
                .unwrap();
            for _ in 0..3 {
                live.pop_front();
            }
            retired = through;
            assert_eq!(receipt.retired_through, retired);
            assert_eq!(receipt.next_sequence, sequence);
            assert_eq!(core.window_len(), capacity - 3);
        }
        let token = core
            .reserve_native(owner.request(sequence), publisher())
            .unwrap();
        assert_eq!(execute(&core, &token).status, Some(DeliveryStatus::Ok));
        live.push_back(sequence);
        assert_eq!(core.window_len(), live.len());
        assert_eq!(core.retired_through(), retired);
        assert_eq!(core.next_sequence(), sequence + 1);
        assert_eq!(owner.effects(), sequence - 1);
        if sequence % 127 == 0 {
            assert_eq!(
                core.reserve_native(pending_request.clone(), publisher())
                    .err(),
                Some(DeliveryError::Retired)
            );
            core.validate_invariants_for_host_model().unwrap();
        }
    }
    let receipt = core
        .retire_through(&view, ack(&authority, WRITES), &authority)
        .unwrap();
    assert_eq!(receipt.retired_through, WRITES);
    assert_eq!(receipt.next_sequence, WRITES + 1);
    assert_eq!(core.window_len(), 0);
    assert_eq!(
        core.query_delivery(&view, 1).unwrap().state,
        DeliveryState::Retired
    );
    assert_eq!(
        core.reserve_native(pending_request, publisher()).err(),
        Some(DeliveryError::Retired)
    );
    assert_eq!(owner.effects(), WRITES - 1);
    core.validate_invariants_for_host_model().unwrap();
}
