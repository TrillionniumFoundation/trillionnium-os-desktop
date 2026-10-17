//! Host-model token lifetime regressions. An opaque old token can retain its
//! cached delivery identity without retaining retired results or resources.
//! No test implements native kernel ownership or a durable Hepta ledger.

use os_control::{
    with_parent, BootId, CapSpaceId, ControlCore, DeliveryError, DeliveryRequest, DeliveryState,
    DeliveryStatus, HistoryAck, OwnerId, OwnerReceipt, PublishOutcome, PublisherId, ResourceDomain,
    ResourceDomainId, ResourceError, StableObjectId, CPU_PERIOD_NS,
};
use std::sync::atomic::{AtomicUsize, Ordering};

fn publisher() -> PublisherId {
    PublisherId::from_u128(1_100_001)
}

fn owner() -> OwnerId {
    OwnerId::from_u128(1_100_002)
}

fn parent(n: u128) -> ResourceDomain {
    ResourceDomain::new(
        ResourceDomainId::from_u128(n),
        StableObjectId::from_u128(n),
        None,
        CPU_PERIOD_NS,
    )
    .unwrap()
}

fn ack(authority: &OriginalOwnerAuthority, through: u64) -> HistoryAck {
    authority.history_ack(through, [0x73; 32]).unwrap()
}

fn denied_without_replay(result: Result<os_control::DeliveryObservation, DeliveryError>) {
    assert!(matches!(
        result,
        Err(DeliveryError::Retired | DeliveryError::HistoryLost)
    ));
}

#[test]
fn ten_thousand_retained_tokens_do_not_reexecute_in_a_one_slot_namespace() {
    let (core, authority) = ControlCore::with_capacity_for_owner(
        BootId::from_u128(1_110_001),
        CapSpaceId::from_u128(1_110_001),
        1,
        owner(),
    )
    .unwrap();
    let target = parent(1_110_001);
    let grant = target.grant(publisher()).unwrap();
    let view = core.delivery_view_for(owner()).unwrap();
    let mut old_tokens = Vec::with_capacity(10_000);
    for sequence in 1..=10_000 {
        let token = core
            .reserve(
                DeliveryRequest::from_wire(sequence, grant.clone(), target.revision(), 17, 9, 11)
                    .unwrap(),
                publisher(),
            )
            .unwrap();
        let binding = token.binding();
        assert_eq!(
            core.commit(&token, publisher(), sequence).unwrap().status,
            Some(DeliveryStatus::Ok)
        );
        core.retire_through(&view, ack(&authority, sequence), &authority)
            .unwrap();
        assert_eq!(core.window_len(), 0);
        assert_eq!(token.binding(), binding);
        old_tokens.push(token);
    }
    assert_eq!(old_tokens.len(), 10_000);
    assert_eq!(core.next_sequence(), 10_001);
    assert_eq!(core.retired_through(), 10_000);
    assert_eq!(target.revision(), 10_001);
    let effects = AtomicUsize::new(0);
    for token in &old_tokens {
        denied_without_replay(core.commit(token, publisher(), 10_001));
        denied_without_replay(core.publish(
            token,
            publisher(),
            PublishOutcome::Failure {
                status: DeliveryStatus::Revoked,
            },
        ));
        denied_without_replay(core.execute_reserved(token, publisher(), |_| {
            effects.fetch_add(1, Ordering::SeqCst);
            PublishOutcome::Failure {
                status: DeliveryStatus::Revoked,
            }
        }));
        assert_eq!(token.publisher(), publisher());
        assert_eq!(token.id().namespace(), core.identity());
        assert_eq!(token.binding().sequence, token.id().sequence());
    }
    assert_eq!(effects.load(Ordering::SeqCst), 0);
    assert_eq!(target.revision(), 10_001);
    assert_eq!(target.budget().cap_ns, 17);
    core.validate_invariants_for_host_model().unwrap();
}

#[test]
fn retained_retired_token_no_longer_keeps_a_child_cap_constraint_alive() {
    let root = parent(1_120_001);
    let root_grant = root.grant(publisher()).unwrap();
    let (core, authority) = ControlCore::with_original_owner(
        BootId::from_u128(1_120_001),
        CapSpaceId::from_u128(1_120_001),
        owner(),
    )
    .unwrap();
    let token = {
        let child = with_parent(
            ResourceDomainId::from_u128(1_120_002),
            StableObjectId::from_u128(1_120_002),
            &root,
            60,
        )
        .unwrap();
        let token = core
            .reserve(
                DeliveryRequest::new(1, child.grant(publisher()).unwrap(), 1, 40),
                publisher(),
            )
            .unwrap();
        core.commit(&token, publisher(), 1).unwrap();
        token
    };
    let binding = token.binding();
    let view = core.delivery_view_for(owner()).unwrap();
    core.retire_through(&view, ack(&authority, 1), &authority)
        .unwrap();

    // Only the obsolete token remains outside the namespace. Its cached
    // identity is useful for diagnostics, but its old grant must be released.
    root.install_budget_for_host_model(&root_grant, 1, CPU_PERIOD_NS, 20, 2)
        .expect("retiring the result must release its last child reference");
    assert_eq!(token.binding(), binding);
    assert_eq!(
        core.query_delivery(&view, 1).unwrap().state,
        DeliveryState::Retired
    );
    denied_without_replay(core.commit(&token, publisher(), 2));
    assert_eq!(root.budget().cap_ns, 20);
}

#[test]
fn unretired_namespace_slot_protects_a_child_after_token_and_user_handles_drop() {
    let root = parent(1_130_001);
    let root_grant = root.grant(publisher()).unwrap();
    let (core, authority) = ControlCore::with_original_owner(
        BootId::from_u128(1_130_001),
        CapSpaceId::from_u128(1_130_001),
        owner(),
    )
    .unwrap();
    {
        let child = with_parent(
            ResourceDomainId::from_u128(1_130_002),
            StableObjectId::from_u128(1_130_002),
            &root,
            60,
        )
        .unwrap();
        let token = core
            .reserve(
                DeliveryRequest::new(1, child.grant(publisher()).unwrap(), 1, 40),
                publisher(),
            )
            .unwrap();
        core.commit(&token, publisher(), 1).unwrap();
    }
    let view = core.delivery_view_for(owner()).unwrap();
    assert_eq!(core.window_len(), 1);
    assert_eq!(
        core.query_delivery(&view, 1).unwrap().status,
        Some(DeliveryStatus::Ok)
    );
    assert_eq!(
        root.install_budget_for_host_model(&root_grant, 1, CPU_PERIOD_NS, 20, 2),
        Err(ResourceError::ParentConstraint)
    );
    core.retire_through(&view, ack(&authority, 1), &authority)
        .unwrap();
    root.install_budget_for_host_model(&root_grant, 1, CPU_PERIOD_NS, 20, 2)
        .unwrap();
    assert_eq!(root.budget().cap_ns, 20);
}

#[test]
fn lost_history_releases_result_resources_even_when_the_old_token_is_retained() {
    let root = parent(1_140_001);
    let root_grant = root.grant(publisher()).unwrap();
    let core = ControlCore::new(
        BootId::from_u128(1_140_001),
        CapSpaceId::from_u128(1_140_001),
    );
    let token = {
        let child = with_parent(
            ResourceDomainId::from_u128(1_140_002),
            StableObjectId::from_u128(1_140_002),
            &root,
            60,
        )
        .unwrap();
        core.reserve(
            DeliveryRequest::new(1, child.grant(publisher()).unwrap(), 1, 40),
            publisher(),
        )
        .unwrap()
    };
    let binding = token.binding();
    core.lose_history();
    root.install_budget_for_host_model(&root_grant, 1, CPU_PERIOD_NS, 20, 1)
        .expect("lost results must not retain resources through obsolete tokens");
    let effects = AtomicUsize::new(0);
    denied_without_replay(core.commit(&token, publisher(), 1));
    denied_without_replay(core.publish(
        &token,
        publisher(),
        PublishOutcome::Failure {
            status: DeliveryStatus::Revoked,
        },
    ));
    denied_without_replay(core.execute_reserved(&token, publisher(), |_| {
        effects.fetch_add(1, Ordering::SeqCst);
        PublishOutcome::Failure {
            status: DeliveryStatus::Revoked,
        }
    }));
    assert_eq!(effects.load(Ordering::SeqCst), 0);
    assert_eq!(token.binding(), binding);
    assert_eq!(core.window_len(), 0);
    core.validate_invariants_for_host_model().unwrap();
}

#[test]
fn obsolete_token_does_not_keep_an_otherwise_unreferenced_namespace_alive() {
    let root = parent(1_150_001);
    let root_grant = root.grant(publisher()).unwrap();
    let token = {
        // No DeliveryView or OriginalOwnerAuthority is retained here: either
        // of those would deliberately keep the history namespace alive.
        let core = ControlCore::new(
            BootId::from_u128(1_150_001),
            CapSpaceId::from_u128(1_150_001),
        );
        let child = with_parent(
            ResourceDomainId::from_u128(1_150_002),
            StableObjectId::from_u128(1_150_002),
            &root,
            60,
        )
        .unwrap();
        core.reserve(
            DeliveryRequest::new(1, child.grant(publisher()).unwrap(), 1, 40),
            publisher(),
        )
        .unwrap()
    };
    root.install_budget_for_host_model(&root_grant, 1, CPU_PERIOD_NS, 20, 1)
        .expect("an obsolete token must not preserve an entire namespace");
    assert_eq!(token.id().sequence(), 1);
    assert_eq!(token.binding().cap_ns, 40);
    assert_eq!(token.publisher(), publisher());
    assert_eq!(root.budget().cap_ns, 20);
}
