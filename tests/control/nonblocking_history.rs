//! Host-only regressions for history availability during a paused external
//! callback. Every timeout is recorded before the callback is unconditionally
//! released and all worker threads are joined; a failing assertion never
//! leaves a callback blocked forever.

use os_control::{
    BootId, CapSpaceId, ControlCore, DeliveryError, DeliveryRequest, DeliveryState, DeliveryStatus,
    HistoryAck, OriginalOwnerAuthority, OwnerId, PublishOutcome, PublisherId, RequestBinding,
    ResourceDomain, ResourceDomainId, StableObjectId, CPU_PERIOD_NS,
};
use std::sync::{mpsc, Arc, Barrier};
use std::thread;
use std::time::Duration;

const DEADLINE: Duration = Duration::from_secs(1);

fn publisher() -> PublisherId {
    PublisherId::from_u128(910_001)
}

fn owner() -> OwnerId {
    OwnerId::from_u128(910_002)
}

fn fixture(n: u128) -> (ControlCore, OriginalOwnerAuthority, ResourceDomain) {
    let (core, authority) =
        ControlCore::with_original_owner(BootId::from_u128(n), CapSpaceId::from_u128(n), owner())
            .unwrap();
    let resource = ResourceDomain::new(
        ResourceDomainId::from_u128(n),
        StableObjectId::from_u128(n),
        None,
        CPU_PERIOD_NS,
    )
    .unwrap();
    (core, authority, resource)
}

fn request(resource: &ResourceDomain, sequence: u64) -> DeliveryRequest {
    DeliveryRequest::from_wire(sequence, resource.grant(publisher()).unwrap(), 1, 17, 9, 11)
        .unwrap()
}

fn success(binding: RequestBinding) -> PublishOutcome {
    PublishOutcome::Success {
        stable_object_id: binding.stable_object_id,
        previous_revision: binding.expected_revision,
        saved_revision: binding.expected_revision + 1,
        effective_ns: 1,
        consumed_ns: 0,
    }
}

fn ack(authority: &OriginalOwnerAuthority, through: u64) -> HistoryAck {
    authority.history_ack(through, [0x61; 32]).unwrap()
}

/// Release on both normal completion and assertion unwinding. This guard is
/// always created *inside* the thread::scope body, so it drops before scope
/// cleanup joins an outstanding executor.
struct ReleaseCallback(Option<mpsc::Sender<()>>);

impl ReleaseCallback {
    fn release(&mut self) {
        if let Some(sender) = self.0.take() {
            let _ = sender.send(());
        }
    }
}

impl Drop for ReleaseCallback {
    fn drop(&mut self) {
        self.release();
    }
}

#[test]
fn paused_callback_query_returns_reserved_and_does_not_hold_namespace() {
    let (core, _, resource) = fixture(920_001);
    let token = core.reserve(request(&resource, 1), publisher()).unwrap();
    let view = core.delivery_view();
    thread::scope(|scope| {
        let (entered_send, entered_recv) = mpsc::channel();
        let (release_send, release_recv) = mpsc::channel();
        let mut release = ReleaseCallback(Some(release_send));
        let core_ref = &core;
        let execute = scope.spawn(move || {
            core_ref.execute_reserved(&token, publisher(), |binding| {
                entered_send.send(()).unwrap();
                release_recv.recv().unwrap();
                success(binding)
            })
        });
        entered_recv.recv_timeout(DEADLINE).unwrap();

        let (query_send, query_recv) = mpsc::channel();
        let query = scope.spawn(move || {
            query_send.send(core_ref.query_delivery(&view, 1)).unwrap();
        });
        // On the old implementation this query waits for the callback while
        // owning the namespace lock. Keep its timeout result for assertion
        // only after the executor has been released and every worker joined.
        let pending = query_recv.recv_timeout(DEADLINE);

        let (read_send, read_recv) = mpsc::channel();
        let read = scope.spawn(move || {
            read_send.send(core_ref.next_sequence()).unwrap();
        });
        let (reserve_send, reserve_recv) = mpsc::channel();
        let next_request = request(&resource, 2);
        let reserve = scope.spawn(move || {
            reserve_send
                .send(core_ref.reserve(next_request, publisher()))
                .unwrap();
        });
        let next_sequence = read_recv.recv_timeout(DEADLINE);
        let next_reservation = reserve_recv.recv_timeout(DEADLINE);
        release.release();
        let terminal = execute.join().unwrap().unwrap();
        query.join().unwrap();
        read.join().unwrap();
        reserve.join().unwrap();

        assert_eq!(terminal.status, Some(DeliveryStatus::Ok));
        assert_eq!(
            pending
                .expect("query must finish while callback remains paused")
                .unwrap()
                .state,
            DeliveryState::Reserved
        );
        assert!(matches!(
            next_sequence.expect("namespace read must not wait for callback"),
            2 | 3
        ));
        assert!(next_reservation
            .expect("unrelated reservation must not wait for callback")
            .is_ok());
    });
    core.validate_invariants_for_host_model().unwrap();
}

#[test]
fn retire_of_paused_callback_returns_pending_prefix_without_waiting() {
    let (core, authority, resource) = fixture(930_001);
    let token = core.reserve(request(&resource, 1), publisher()).unwrap();
    let view = core.delivery_view_for(owner()).unwrap();
    let acknowledgement = ack(&authority, 1);
    thread::scope(|scope| {
        let (entered_send, entered_recv) = mpsc::channel();
        let (release_send, release_recv) = mpsc::channel();
        let mut release = ReleaseCallback(Some(release_send));
        let core_ref = &core;
        let execute = scope.spawn(move || {
            core_ref.execute_reserved(&token, publisher(), |binding| {
                entered_send.send(()).unwrap();
                release_recv.recv().unwrap();
                success(binding)
            })
        });
        entered_recv.recv_timeout(DEADLINE).unwrap();
        let (retire_send, retire_recv) = mpsc::channel();
        let retire = scope.spawn(move || {
            retire_send
                .send(core_ref.retire_through(&view, acknowledgement, &authority))
                .unwrap();
        });
        let pending_prefix = retire_recv.recv_timeout(DEADLINE);
        release.release();
        execute.join().unwrap().unwrap();
        retire.join().unwrap();
        assert_eq!(
            pending_prefix.expect("retirement must inspect pending state without waiting"),
            Err(DeliveryError::PendingPrefix)
        );
    });
    assert_eq!(core.retired_through(), 0);
    core.validate_invariants_for_host_model().unwrap();
}

#[test]
fn invariant_audit_can_observe_paused_callback_without_waiting() {
    let (core, _, resource) = fixture(940_001);
    let token = core.reserve(request(&resource, 1), publisher()).unwrap();
    thread::scope(|scope| {
        let (entered_send, entered_recv) = mpsc::channel();
        let (release_send, release_recv) = mpsc::channel();
        let mut release = ReleaseCallback(Some(release_send));
        let core_ref = &core;
        let execute = scope.spawn(move || {
            core_ref.execute_reserved(&token, publisher(), |binding| {
                entered_send.send(()).unwrap();
                release_recv.recv().unwrap();
                success(binding)
            })
        });
        entered_recv.recv_timeout(DEADLINE).unwrap();
        let (audit_send, audit_recv) = mpsc::channel();
        let audit = scope.spawn(move || {
            audit_send
                .send(core_ref.validate_invariants_for_host_model())
                .unwrap();
        });
        let audited = audit_recv.recv_timeout(DEADLINE);
        release.release();
        execute.join().unwrap().unwrap();
        audit.join().unwrap();
        assert_eq!(
            audited.expect("invariant audit must not wait for external callback"),
            Ok(())
        );
    });
}

#[test]
fn closing_namespace_fences_writes_while_queries_and_reads_remain_available() {
    let (core, authority, resource) = fixture(950_001);
    let retired_request = request(&resource, 1);
    let first = core.reserve(retired_request.clone(), publisher()).unwrap();
    core.publish(&first, publisher(), success(first.binding()))
        .unwrap();
    let view = core.delivery_view_for(owner()).unwrap();
    core.retire_through(&view, ack(&authority, 1), &authority)
        .unwrap();
    let token = core.reserve(request(&resource, 2), publisher()).unwrap();
    let acknowledgement = ack(&authority, 2);

    thread::scope(|scope| {
        let (entered_send, entered_recv) = mpsc::channel();
        let (release_send, release_recv) = mpsc::channel();
        let mut release = ReleaseCallback(Some(release_send));
        let core_ref = &core;
        let execute = scope.spawn(move || {
            core_ref.execute_reserved(&token, publisher(), |binding| {
                entered_send.send(()).unwrap();
                release_recv.recv().unwrap();
                success(binding)
            })
        });
        entered_recv.recv_timeout(DEADLINE).unwrap();
        let (loss_started_send, loss_started_recv) = mpsc::channel();
        let loss = scope.spawn(move || {
            loss_started_send.send(()).unwrap();
            core_ref.lose_history();
        });
        loss_started_recv.recv_timeout(DEADLINE).unwrap();

        let (closing_send, closing_recv) = mpsc::channel();
        let probe = scope.spawn(move || {
            // An already-retired D never allocates a result or advances a
            // sequence. Its admission changes Retired -> HistoryLost only
            // when namespace closure has started, so this is a read-only
            // public-API synchronization point, not a scheduling sleep.
            loop {
                match core_ref.reserve(retired_request.clone(), publisher()) {
                    Err(DeliveryError::Retired) => thread::yield_now(),
                    result => {
                        closing_send.send(result.err()).unwrap();
                        break;
                    }
                }
            }
        });
        let closing = closing_recv.recv_timeout(DEADLINE);
        let mut during_closing = None;
        let mut inspect = None;
        let inspect_recv;
        if closing.is_ok() {
            let (inspect_send, receiver) = mpsc::channel();
            inspect_recv = Some(receiver);
            let view_ref = &view;
            let authority_ref = &authority;
            let fresh = request(&resource, 3);
            inspect = Some(scope.spawn(move || {
                let snapshot = (
                    core_ref.query_delivery(view_ref, 2),
                    core_ref.next_sequence(),
                    core_ref.reserve(fresh, publisher()).err(),
                    core_ref.retire_through(view_ref, acknowledgement, authority_ref),
                    core_ref.validate_invariants_for_host_model(),
                );
                inspect_send.send(snapshot).unwrap();
            }));
        } else {
            inspect_recv = None;
        }
        if let Some(receiver) = &inspect_recv {
            during_closing = Some(receiver.recv_timeout(DEADLINE));
        }

        release.release();
        let terminal = execute.join().unwrap().unwrap();
        probe.join().unwrap();
        if let Some(inspect) = inspect {
            inspect.join().unwrap();
        }
        loss.join().unwrap();

        assert_eq!(terminal.status, Some(DeliveryStatus::Ok));
        assert_eq!(
            closing.expect("closure must fence admission before waiting for callback"),
            Some(DeliveryError::HistoryLost)
        );
        let (pending, next, new_write, retire, audit) = during_closing
            .expect("closing namespace should have been inspected")
            .expect("closing must release the namespace mutex while waiting for callback");
        assert_eq!(pending.unwrap().state, DeliveryState::Reserved);
        assert_eq!(next, 3);
        assert_eq!(new_write, Some(DeliveryError::HistoryLost));
        assert_eq!(retire, Err(DeliveryError::HistoryLost));
        assert_eq!(audit, Ok(()));
    });
    assert_eq!(
        core.query_delivery(&view, 2).unwrap().state,
        DeliveryState::HistoryLost
    );
    assert_eq!(core.next_sequence(), 3);
    assert_eq!(core.window_len(), 0);
    core.validate_invariants_for_host_model().unwrap();
}

#[test]
fn terminal_observations_never_regress_during_concurrent_read_and_publication_retries() {
    let (core, _, resource) = fixture(960_001);
    let core = Arc::new(core);
    let token = Arc::new(core.reserve(request(&resource, 1), publisher()).unwrap());
    let terminal = core
        .publish(&token, publisher(), success(token.binding()))
        .unwrap();
    let start = Arc::new(Barrier::new(9));
    let mut workers = Vec::new();
    for worker in 0..8 {
        let core = Arc::clone(&core);
        let token = Arc::clone(&token);
        let start = Arc::clone(&start);
        let view = core.delivery_view();
        workers.push(thread::spawn(move || {
            start.wait();
            for _ in 0..2_000 {
                let observed = if worker % 2 == 0 {
                    core.query_delivery(&view, 1).unwrap()
                } else {
                    core.publish(&token, publisher(), success(token.binding()))
                        .unwrap()
                };
                assert_eq!(
                    observed, terminal,
                    "terminal history must never become Reserved"
                );
            }
        }));
    }
    start.wait();
    for worker in workers {
        worker.join().unwrap();
    }
    core.validate_invariants_for_host_model().unwrap();
}

#[test]
fn two_concurrent_losses_wait_for_every_callback_without_blocking_history_reads() {
    let (core, authority, first_resource) = fixture(970_001);
    let second_resource = ResourceDomain::new(
        ResourceDomainId::from_u128(970_002),
        StableObjectId::from_u128(970_002),
        None,
        CPU_PERIOD_NS,
    )
    .unwrap();
    let retired_request = request(&first_resource, 1);
    let retired = core.reserve(retired_request.clone(), publisher()).unwrap();
    core.publish(&retired, publisher(), success(retired.binding()))
        .unwrap();
    let view = core.delivery_view_for(owner()).unwrap();
    core.retire_through(&view, ack(&authority, 1), &authority)
        .unwrap();
    let first = core
        .reserve(request(&first_resource, 2), publisher())
        .unwrap();
    let second = core
        .reserve(request(&second_resource, 3), publisher())
        .unwrap();

    thread::scope(|scope| {
        let core_ref = &core;
        let (first_entered_send, first_entered_recv) = mpsc::channel();
        let (first_release_send, first_release_recv) = mpsc::channel();
        let mut first_release = ReleaseCallback(Some(first_release_send));
        let first_execute = scope.spawn(move || {
            core_ref.execute_reserved(&first, publisher(), |binding| {
                first_entered_send.send(()).unwrap();
                first_release_recv.recv().unwrap();
                success(binding)
            })
        });
        let (second_entered_send, second_entered_recv) = mpsc::channel();
        let (second_release_send, second_release_recv) = mpsc::channel();
        let mut second_release = ReleaseCallback(Some(second_release_send));
        let second_execute = scope.spawn(move || {
            core_ref.execute_reserved(&second, publisher(), |binding| {
                second_entered_send.send(()).unwrap();
                second_release_recv.recv().unwrap();
                success(binding)
            })
        });
        first_entered_recv.recv_timeout(DEADLINE).unwrap();
        second_entered_recv.recv_timeout(DEADLINE).unwrap();

        let loss_start = Arc::new(Barrier::new(3));
        let (loss_done_send, loss_done_recv) = mpsc::channel();
        let mut losses = Vec::new();
        for index in 0..2 {
            let start = Arc::clone(&loss_start);
            let done = loss_done_send.clone();
            losses.push(scope.spawn(move || {
                start.wait();
                core_ref.lose_history();
                done.send(index).unwrap();
            }));
        }
        loss_start.wait();

        let (closing_send, closing_recv) = mpsc::channel();
        let probe = scope.spawn(move || loop {
            match core_ref.reserve(retired_request.clone(), publisher()) {
                Err(DeliveryError::Retired) => thread::yield_now(),
                result => {
                    closing_send.send(result.err()).unwrap();
                    break;
                }
            }
        });
        let closing = closing_recv.recv_timeout(DEADLINE);
        let early_loss = loss_done_recv.try_recv();

        first_release.release();
        let first_terminal = first_execute.join().unwrap().unwrap();
        // The higher-sequence executor is still paused. Neither the first
        // loss nor the serialized second loss may have returned yet.
        let loss_after_first = loss_done_recv.recv_timeout(Duration::from_millis(100));

        let (inspect_send, inspect_recv) = mpsc::channel();
        let view_ref = &view;
        let inspect = scope.spawn(move || {
            inspect_send
                .send((
                    core_ref.query_delivery(view_ref, 2),
                    core_ref.query_delivery(view_ref, 3),
                    core_ref.next_sequence(),
                    core_ref.validate_invariants_for_host_model(),
                ))
                .unwrap();
        });
        let between_callbacks = inspect_recv.recv_timeout(DEADLINE);

        second_release.release();
        let second_terminal = second_execute.join().unwrap().unwrap();
        probe.join().unwrap();
        inspect.join().unwrap();
        for loss in losses {
            loss.join().unwrap();
        }
        let mut completed = Vec::new();
        if let Ok(index) = &early_loss {
            completed.push(*index);
        }
        if let Ok(index) = &loss_after_first {
            completed.push(*index);
        }
        while completed.len() < 2 {
            completed.push(loss_done_recv.recv_timeout(DEADLINE).unwrap());
        }
        completed.sort_unstable();

        assert_eq!(
            closing.expect("loss admission fence must remain observable"),
            Some(DeliveryError::HistoryLost)
        );
        assert!(matches!(early_loss, Err(mpsc::TryRecvError::Empty)));
        assert!(matches!(
            loss_after_first,
            Err(mpsc::RecvTimeoutError::Timeout)
        ));
        assert_eq!(completed, [0, 1]);
        assert_eq!(first_terminal.status, Some(DeliveryStatus::Ok));
        assert_eq!(second_terminal.status, Some(DeliveryStatus::Ok));
        let (finished, pending, next, audit) =
            between_callbacks.expect("readers must not wait for either loss or paused executor");
        assert_eq!(finished.unwrap(), first_terminal);
        assert_eq!(pending.unwrap().state, DeliveryState::Reserved);
        assert_eq!(next, 4);
        assert_eq!(audit, Ok(()));
    });
    for sequence in 1..=3 {
        assert_eq!(
            core.query_delivery(&view, sequence).unwrap().state,
            DeliveryState::HistoryLost
        );
    }
    assert_eq!(core.window_len(), 0);
    assert_eq!(core.next_sequence(), 4);
    core.validate_invariants_for_host_model().unwrap();
}
