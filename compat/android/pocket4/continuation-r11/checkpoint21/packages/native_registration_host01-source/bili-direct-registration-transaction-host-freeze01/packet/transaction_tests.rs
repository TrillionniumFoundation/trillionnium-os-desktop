
#[cfg(test)]
mod transaction_regressions {
    use super::*;
    use crate::{Backend, Fault, Moment, Point};
    use std::sync::TryLockError;
    use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};

    const PACKAGE: &str = "org.example.player";
    const TASK: TaskId = TaskId(42);
    const ANDROID_DISPLAY: u32 = 0;

    struct Fixture { coordinator: Arc<TaskCoordinator>, io: Backend }
    impl Fixture {
        fn new() -> Self {
            let io = Backend::default();
            let coordinator = Arc::new(TaskCoordinator::new(
                DenialPresentationSink::fixture(io.clone()),
                ComposerLifecycle::fixture(io.clone()),
            ));
            let weak = Arc::downgrade(&coordinator);
            io.configure_with(Some(Arc::new(move |object| {
                weak.upgrade().unwrap().display_connected(object).unwrap();
            })));
            Self { coordinator, io }
        }
        fn register(&self) -> Result<(TaskObjectId, DisplayId), String> {
            self.coordinator.register_direct_task(TASK, PACKAGE.to_owned(), ANDROID_DISPLAY)
        }
        fn live(&self) -> TaskRegistration {
            let state = self.coordinator.state.0.lock().unwrap();
            let object = *state.direct_tasks.get(&TASK).expect("owned direct marker retained");
            state.registry.get(object).unwrap().clone()
        }
        fn assert_retired(&self, object: TaskObjectId, display: DisplayId) {
            let state = self.coordinator.state.0.lock().unwrap();
            assert!(state.retired.contains(&object));
            assert!(state.registry.get(object).is_err());
            assert!(!state.direct_tasks.values().any(|value| *value == object));
            assert!(!state.direct_android_displays.contains_key(&object));
            assert!(!state.input_scales.contains_key(&object));
            assert!(!state.removals.contains_key(&object));
            assert!(!state.endpoint_calls.contains_key(&object));
            drop(state);
            assert!(!self.io.has_channel(display));
            assert!(!self.io.has_window(display));
        }
        fn last_retired(&self) -> TaskObjectId {
            let state = self.coordinator.state.0.lock().unwrap();
            assert_eq!(state.retired.len(), 1);
            *state.retired.iter().next().unwrap()
        }
    }

    #[test]
    fn complete_direct_bind_commits_exact_registry_and_endpoints() {
        let f = Fixture::new();
        let (object, display) = f.register().unwrap();
        let current = f.live();
        assert_eq!(current.object, object);
        assert_eq!(current.phase, TaskRegistrationPhase::Bound);
        assert_eq!(current.task, Some(TASK));
        assert_eq!(current.android_display, Some(ANDROID_DISPLAY));
        assert_eq!(current.reservation.package, PACKAGE);
        assert_eq!(current.reservation.display, display);
        assert_eq!(f.io.bound_tasks(display), (Some(TASK), Some(TASK)));
        assert!(f.coordinator.is_direct_task(object));
        assert_eq!(f.coordinator.direct_task_display(TASK).unwrap(), display);
        assert_eq!(f.io.calls().iter().map(|(p, _)| *p).collect::<Vec<_>>(),
            vec![Point::Stage, Point::Register, Point::SinkBind, Point::ComposerBind]);
    }

    #[test]
    fn complete_bound_reuse_performs_no_new_backend_calls() {
        let f = Fixture::new();
        let first = f.register().unwrap();
        let before = f.io.calls();
        assert_eq!(f.register().unwrap(), first);
        assert_eq!(f.io.calls(), before);
    }

    #[test]
    fn bound_reuse_rejects_different_package_or_android_display() {
        let f = Fixture::new();
        f.register().unwrap();
        let before = f.io.calls();
        assert!(f.coordinator.register_direct_task(TASK, "org.example.foreign".into(), 0)
            .unwrap_err().contains("different ownership"));
        assert!(f.coordinator.register_direct_task(TASK, PACKAGE.into(), 7)
            .unwrap_err().contains("different ownership"));
        assert_eq!(f.io.calls(), before);
        assert_eq!(f.live().phase, TaskRegistrationPhase::Bound);
    }

    #[test]
    fn pending_direct_marker_is_visible_before_denial_register() {
        let f = Fixture::new();
        let weak = Arc::downgrade(&f.coordinator);
        let observed = Arc::new(AtomicBool::new(false));
        let copied = observed.clone();
        f.io.observe(Arc::new(move |point, moment, _| {
            if point == Point::Register && moment == Moment::Before {
                let coordinator = weak.upgrade().unwrap();
                let state = coordinator.state.0.lock().unwrap();
                let object = *state.direct_tasks.get(&TASK).unwrap();
                assert_eq!(state.registry.get(object).unwrap().phase, TaskRegistrationPhase::Staged);
                assert_eq!(state.direct_android_displays.get(&object), Some(&ANDROID_DISPLAY));
                drop(state);
                assert!(coordinator.is_direct_task(object));
                copied.store(true, Ordering::SeqCst);
            }
        }));
        f.register().unwrap();
        assert!(observed.load(Ordering::SeqCst));
    }

    #[test]
    fn sink_bind_after_effect_error_rolls_back_exact_owned_object() {
        let f = Fixture::new();
        f.io.fail(Point::SinkBind, Fault::After("sink-bind-after"));
        let error = f.register().unwrap_err();
        assert!(error.contains("sink-bind-after"));
        assert!(!error.contains("cleanup of"));
        let display = f.io.calls()[0].1;
        f.assert_retired(f.last_retired(), display);
        assert!(f.io.endpoints_empty());
        assert_eq!(f.io.count(Point::ComposerBind), 0);
        assert_eq!(f.io.count(Point::Destroy), 1);
        assert_eq!(f.io.count(Point::Remove), 1);
    }

    #[test]
    fn composer_bind_after_effect_error_rolls_back_both_endpoints() {
        let f = Fixture::new();
        f.io.fail(Point::ComposerBind, Fault::After("composer-bind-after"));
        let error = f.register().unwrap_err();
        assert!(error.contains("composer-bind-after"));
        let display = f.io.calls()[0].1;
        f.assert_retired(f.last_retired(), display);
        assert_eq!(f.io.count(Point::SinkBind), 1);
        assert_eq!(f.io.count(Point::ComposerBind), 1);
        assert!(f.io.endpoints_empty());
    }

    #[test]
    fn real_registry_duplicate_failure_preserves_foreign_registration() {
        let f = Fixture::new();
        let weak = Arc::downgrade(&f.coordinator);
        let foreign = Arc::new(Mutex::new(None));
        let copied = foreign.clone();
        f.io.observe(Arc::new(move |point, moment, _| {
            if point == Point::ComposerBind && moment == Moment::After {
                let coordinator = weak.upgrade().unwrap();
                let mut state = coordinator.state.0.lock().unwrap();
                let entry = state.registry.reserve("org.example.foreign".to_owned()).unwrap();
                state.registry.mark_staged(entry.object).unwrap();
                state.registry.mark_connected(entry.object).unwrap();
                state.registry.bind_task(entry.object, TASK, 9).unwrap();
                *copied.lock().unwrap() = Some(entry.object);
            }
        }));
        let error = f.register().unwrap_err();
        assert!(error.contains("already has a registration"));
        let display = f.io.calls()[0].1;
        f.assert_retired(f.last_retired(), display);
        let object = foreign.lock().unwrap().unwrap();
        let state = f.coordinator.state.0.lock().unwrap();
        let entry = state.registry.get(object).unwrap();
        assert_eq!(entry.phase, TaskRegistrationPhase::Bound);
        assert_eq!(entry.task, Some(TASK));
        assert_eq!(entry.android_display, Some(9));
        assert_eq!(entry.reservation.package, "org.example.foreign");
        assert!(!state.retired.contains(&object));
    }

    #[test]
    fn denial_cleanup_error_preserves_primary_and_pending_progress() {
        let f = Fixture::new();
        f.io.fail(Point::SinkBind, Fault::After("bind-primary"));
        f.io.fail(Point::Destroy, Fault::Before("destroy-secondary"));
        let error = f.register().unwrap_err();
        let a = error.find("bind-primary").unwrap();
        let b = error.find("destroy-secondary").unwrap();
        assert!(a < b);
        let current = f.live();
        assert_eq!(current.phase, TaskRegistrationPhase::Removing);
        let state = f.coordinator.state.0.lock().unwrap();
        let progress = state.removals.get(&current.object).unwrap();
        assert!(!progress.denial_complete && !progress.composer_complete);
        assert!(!state.retired.contains(&current.object));
        drop(state);
        assert!(f.io.has_channel(current.reservation.display));
        assert!(f.io.has_window(current.reservation.display));
        let count = f.io.calls().len();
        assert!(f.register().unwrap_err().contains("not fully Bound"));
        assert_eq!(f.io.calls().len(), count);
        f.coordinator.retire_direct_task(TASK).unwrap();
        f.assert_retired(current.object, current.reservation.display);
    }

    #[test]
    fn composer_cleanup_retry_skips_already_destroyed_denial_channel() {
        let f = Fixture::new();
        f.io.fail(Point::ComposerBind, Fault::After("bind-primary"));
        f.io.fail(Point::Remove, Fault::Before("remove-secondary"));
        let error = f.register().unwrap_err();
        assert!(error.contains("bind-primary") && error.contains("remove-secondary"));
        let current = f.live();
        assert_eq!(current.phase, TaskRegistrationPhase::Removing);
        {
            let state = f.coordinator.state.0.lock().unwrap();
            let progress = state.removals.get(&current.object).unwrap();
            assert!(progress.denial_complete && !progress.composer_complete);
        }
        assert!(!f.io.has_channel(current.reservation.display));
        assert!(f.io.has_window(current.reservation.display));
        f.coordinator.retire_direct_task(TASK).unwrap();
        assert_eq!(f.io.count(Point::Destroy), 1);
        assert_eq!(f.io.count(Point::Remove), 2);
        f.assert_retired(current.object, current.reservation.display);
    }

    #[test]
    fn repeated_composer_cleanup_error_keeps_success_checkpoint() {
        let f = Fixture::new();
        f.io.fail(Point::SinkBind, Fault::After("bind-primary"));
        f.io.fail(Point::Remove, Fault::Before("remove-first"));
        f.io.fail(Point::Remove, Fault::Before("remove-second"));
        f.register().unwrap_err();
        let current = f.live();
        assert!(f.coordinator.retire_direct_task(TASK).unwrap_err().contains("remove-second"));
        {
            let state = f.coordinator.state.0.lock().unwrap();
            assert!(state.removals.get(&current.object).unwrap().denial_complete);
            assert!(!state.removals.get(&current.object).unwrap().composer_complete);
            assert!(!state.retired.contains(&current.object));
        }
        f.coordinator.retire_direct_task(TASK).unwrap();
        assert_eq!(f.io.count(Point::Destroy), 1);
        assert_eq!(f.io.count(Point::Remove), 3);
        f.assert_retired(current.object, current.reservation.display);
    }

    #[test]
    fn activation_error_keeps_complete_bound_and_allows_reuse() {
        let f = Fixture::new();
        f.io.fail(Point::Activate, Fault::Before("activation-failed"));
        let error = f.coordinator.register_direct(11, PACKAGE.into(), TASK, ANDROID_DISPLAY).unwrap_err();
        assert!(error.1.contains("activation-failed"));
        let current = f.live();
        assert_eq!(current.phase, TaskRegistrationPhase::Bound);
        assert_eq!(f.io.count(Point::Destroy), 0);
        let response = f.coordinator.register_direct(12, PACKAGE.into(), TASK, ANDROID_DISPLAY).unwrap();
        assert!(matches!(response, ControlResponse::Bound { request_id: 12, object, .. } if object == current.object.0));
        assert_eq!(f.io.count(Point::Stage), 1);
        assert_eq!(f.io.count(Point::Activate), 2);
        assert_eq!(f.live().phase, TaskRegistrationPhase::Bound);
    }

    #[test]
    fn reserved_without_endpoint_calls_cancels_without_backend_cleanup() {
        let f = Fixture::new();
        let registration = {
            let mut state = f.coordinator.state.0.lock().unwrap();
            let registration = state.registry.reserve(PACKAGE.into()).unwrap();
            state.endpoint_calls.insert(registration.object, EndpointCalls {
                display: registration.reservation.display, composer: false, denial: false,
            });
            state.direct_tasks.insert(TASK, registration.object);
            state.direct_android_displays.insert(registration.object, ANDROID_DISPLAY);
            state.input_scales.insert(registration.object, (2, 1));
            registration
        };
        f.coordinator.retire_direct_task(TASK).unwrap();
        f.assert_retired(registration.object, registration.reservation.display);
        assert!(f.io.calls().is_empty());
    }

    #[test]
    fn composer_stage_after_effect_error_cleans_only_invoked_endpoint() {
        let f = Fixture::new();
        f.io.fail(Point::Stage, Fault::After("stage-after-effect"));
        let error = f.register().unwrap_err();
        assert!(error.contains("stage-after-effect"));
        assert!(!error.contains("cleanup failed"));
        assert_eq!(f.io.count(Point::Register), 0);
        assert_eq!(f.io.count(Point::Destroy), 0);
        assert_eq!(f.io.count(Point::Remove), 1);
        let display = f.io.calls()[0].1;
        f.assert_retired(f.last_retired(), display);
    }

    #[test]
    fn composer_stage_error_without_effect_does_not_infer_absence_from_error() {
        let f = Fixture::new();
        f.io.fail(Point::Stage, Fault::Before("stage-before-effect"));
        let error = f.register().unwrap_err();
        assert!(error.contains("stage-before-effect"));
        assert!(error.contains("cleanup failed") && error.contains("unknown-window"));
        let current = f.live();
        assert_eq!(current.phase, TaskRegistrationPhase::Reserved);
        let state = f.coordinator.state.0.lock().unwrap();
        assert!(!state.retired.contains(&current.object));
        let progress = state.removals.get(&current.object).unwrap();
        assert!(progress.denial_complete && !progress.composer_complete);
        drop(state);
        let before = f.io.calls();
        assert!(f.register().unwrap_err().contains("not fully Bound"));
        assert_eq!(f.io.calls(), before);
    }

    #[test]
    fn denial_register_after_effect_error_cleans_both_owned_endpoints() {
        let f = Fixture::new();
        f.io.fail(Point::Register, Fault::After("register-after-effect"));
        let error = f.register().unwrap_err();
        assert!(error.contains("register-after-effect"));
        assert!(!error.contains("cleanup failed"));
        assert_eq!(f.io.count(Point::Destroy), 1);
        assert_eq!(f.io.count(Point::Remove), 1);
        let display = f.io.calls()[0].1;
        f.assert_retired(f.last_retired(), display);
    }

    #[test]
    fn denial_register_error_missing_local_channel_stays_unresolved() {
        let f = Fixture::new();
        f.io.fail(Point::Register, Fault::Before("register-before-channel"));
        let error = f.register().unwrap_err();
        assert!(error.contains("register-before-channel") && error.contains("unknown-channel"));
        let current = f.live();
        assert_eq!(current.phase, TaskRegistrationPhase::Removing);
        let state = f.coordinator.state.0.lock().unwrap();
        assert!(!state.retired.contains(&current.object));
        assert!(!state.removals.get(&current.object).unwrap().denial_complete);
        drop(state);
        assert_eq!(f.io.count(Point::Remove), 0);
        assert!(f.io.has_window(current.reservation.display));
        let before = f.io.calls();
        assert!(f.register().unwrap_err().contains("not fully Bound"));
        assert_eq!(f.io.calls(), before);
    }

    #[test]
    fn configure_timeout_preserves_cleanup_error_and_explicit_retirement() {
        let f = Fixture::new();
        f.io.configure_with(None);
        f.io.fail(Point::Destroy, Fault::Before("timeout-destroy-failed"));
        let error = f.coordinator.reserve_with_kind(97, PACKAGE.into(), Some((TASK, 0))).unwrap_err();
        assert!(matches!(error.0, ControlErrorCode::ConfigureTimeout));
        assert!(error.1.contains("request 97") && error.1.contains("5000 ms"));
        assert!(error.1.contains("timeout-destroy-failed"));
        let current = f.live();
        assert_eq!(current.phase, TaskRegistrationPhase::Removing);
        f.coordinator.retire_direct_task(TASK).unwrap();
        f.assert_retired(current.object, current.reservation.display);
    }

    #[test]
    fn rollback_refuses_complete_bound_registration() {
        let f = Fixture::new();
        let (object, display) = f.register().unwrap();
        let reservation = DirectReservation {
            object, display, task: TASK, android_display: 0, package: PACKAGE.into(),
        };
        let before = f.io.calls();
        let operation = f.coordinator.operation_gate.lock().unwrap();
        let error = f.coordinator.rollback_direct_locked(&reservation, &operation).unwrap_err();
        assert!(error.1.contains("complete Bound"));
        drop(operation);
        assert_eq!(f.io.calls(), before);
        assert_eq!(f.live().phase, TaskRegistrationPhase::Bound);
    }

    #[test]
    fn rollback_refuses_changed_reservation_identity_before_backend_calls() {
        let f = Fixture::new();
        let (object, display) = f.register().unwrap();
        let reservation = DirectReservation {
            object, display, task: TASK, android_display: 0, package: "org.example.foreign".into(),
        };
        let before = f.io.calls();
        let operation = f.coordinator.operation_gate.lock().unwrap();
        let error = f.coordinator.rollback_direct_locked(&reservation, &operation).unwrap_err();
        assert!(error.1.contains("changed direct reservation"));
        drop(operation);
        assert_eq!(f.io.calls(), before);
    }

    #[test]
    fn retirement_rejects_progress_for_another_display() {
        let f = Fixture::new();
        let (object, display) = f.register().unwrap();
        f.coordinator.state.0.lock().unwrap().removals.insert(object, RemovalProgress {
            display: DisplayId(display.0 + 1), denial_complete: false, composer_complete: false,
        });
        let before = f.io.calls();
        assert!(f.coordinator.retire_direct_task(TASK).unwrap_err().contains("not for this display"));
        assert_eq!(f.io.calls(), before);
        assert!(!f.coordinator.is_retired(object));
    }

    #[test]
    fn retired_object_with_residual_mapping_is_not_accepted_as_clean() {
        let f = Fixture::new();
        let (object, display) = f.register().unwrap();
        f.coordinator.retire_direct_task(TASK).unwrap();
        f.assert_retired(object, display);
        f.coordinator.state.0.lock().unwrap().direct_tasks.insert(TASK, object);
        let before = f.io.calls();
        let error = f.coordinator.remove_internal(object).unwrap_err();
        assert!(error.1.contains("still has live coordinator state"));
        assert_eq!(f.io.calls(), before);
    }

    #[test]
    fn backend_calls_hold_operation_gate_but_never_state_mutex() {
        let f = Fixture::new();
        let weak = Arc::downgrade(&f.coordinator);
        let observed = Arc::new(AtomicUsize::new(0));
        let copied = observed.clone();
        f.io.observe(Arc::new(move |_, moment, _| {
            if moment == Moment::Before {
                let coordinator = weak.upgrade().unwrap();
                assert!(matches!(coordinator.operation_gate.try_lock(), Err(TryLockError::WouldBlock)));
                assert!(coordinator.state.0.try_lock().is_ok());
                assert!(matches!(coordinator.direct_registration_gate.try_lock(), Err(TryLockError::WouldBlock)));
                copied.fetch_add(1, Ordering::SeqCst);
            }
        }));
        f.io.fail(Point::ComposerBind, Fault::After("observe-cleanup"));
        assert!(f.register().unwrap_err().contains("observe-cleanup"));
        assert_eq!(observed.load(Ordering::SeqCst), 6);
    }

    #[test]
    fn invalid_task_identity_does_not_allocate_or_call_backends() {
        let f = Fixture::new();
        for task in [TaskId(0), TaskId(i32::MAX as u64 + 1)] {
            assert!(f.coordinator.register_direct_task(task, PACKAGE.into(), 0).unwrap_err()
                .contains("invalid Android task identity"));
        }
        assert!(f.io.calls().is_empty());
        let state = f.coordinator.state.0.lock().unwrap();
        assert!(state.direct_tasks.is_empty() && state.endpoint_calls.is_empty() && state.retired.is_empty());
    }

    #[test]
    fn completed_retirement_is_idempotent_without_repeating_backend_calls() {
        let f = Fixture::new();
        let (object, display) = f.register().unwrap();
        f.coordinator.set_input_scale(object, 3, 2).unwrap();
        f.coordinator.retire_direct_task(TASK).unwrap();
        f.assert_retired(object, display);
        let before = f.io.calls();
        f.coordinator.remove_internal(object).unwrap();
        assert_eq!(f.io.calls(), before);
    }

    #[test]
    fn after_destroy_error_is_not_promoted_to_a_success_checkpoint() {
        let f = Fixture::new();
        f.io.fail(Point::SinkBind, Fault::After("bind-primary"));
        f.io.fail(Point::Destroy, Fault::After("destroy-uncertain"));
        let error = f.register().unwrap_err();
        assert!(error.contains("destroy-uncertain"));
        let current = f.live();
        assert!(!f.io.has_channel(current.reservation.display));
        assert!(f.coordinator.retire_direct_task(TASK).unwrap_err().contains("unknown-channel"));
        let state = f.coordinator.state.0.lock().unwrap();
        assert!(!state.removals.get(&current.object).unwrap().denial_complete);
        assert!(!state.retired.contains(&current.object));
        drop(state);
        assert_eq!(f.io.count(Point::Remove), 0);
    }

    #[test]
    fn endpoint_call_record_is_required_for_bound_reuse() {
        let f = Fixture::new();
        let (object, _) = f.register().unwrap();
        f.coordinator.state.0.lock().unwrap().endpoint_calls.remove(&object);
        let before = f.io.calls();
        assert!(f.register().unwrap_err().contains("not fully Bound"));
        assert_eq!(f.io.calls(), before);
    }

    #[test]
    fn removal_checkpoint_cannot_be_reversed() {
        let f = Fixture::new();
        f.io.fail(Point::SinkBind, Fault::After("bind-primary"));
        f.io.fail(Point::Remove, Fault::Before("keep-composer"));
        f.register().unwrap_err();
        let current = f.live();
        let operation = f.coordinator.operation_gate.lock().unwrap();
        let error = f.coordinator.record_removal_locked(current.object, RemovalProgress {
            display: current.reservation.display,
            denial_complete: false,
            composer_complete: false,
        }, &operation).unwrap_err();
        assert!(error.1.contains("progress changed"));
        drop(operation);
        let state = f.coordinator.state.0.lock().unwrap();
        assert!(state.removals.get(&current.object).unwrap().denial_complete);
    }
}
