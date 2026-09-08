use trillionnium_contract_core::Sha256Hex;

use super::*;

fn digest(byte: char) -> Sha256Hex {
    Sha256Hex::parse(byte.to_string().repeat(64)).expect("fixture digest")
}

fn surface() -> ContentSurfaceId {
    ContentSurfaceId::new(7).expect("fixture surface")
}

fn state() -> WorkspaceState {
    let config = WorkspaceConfig::new(
        PixelSize::new(1280, 720).expect("fixture viewport"),
        64,
        surface(),
    )
    .expect("fixture config");
    WorkspaceState::new(config).expect("fixture state")
}

fn attach(state: &mut WorkspaceState) {
    state
        .apply(WorkspaceEvent::AttachContent {
            surface_id: surface(),
        })
        .expect("attach content");
}

#[test]
fn viewport_and_chrome_geometry_are_bounded() {
    assert!(PixelSize::new(0, 720).is_err());
    assert!(PixelSize::new(1280, 0).is_err());
    assert!(PixelSize::new(40_000, 720).is_err());
    let viewport = PixelSize::new(1280, 720).unwrap();
    assert!(WorkspaceConfig::new(viewport, 0, surface()).is_err());
    assert!(WorkspaceConfig::new(viewport, 720, surface()).is_err());
}

#[test]
fn trusted_chrome_is_always_visible_and_has_a_fixed_origin() {
    let state = state();
    let snapshot = state.snapshot();
    assert!(snapshot.trusted_chrome_visible);
    assert_eq!(snapshot.trusted_chrome_origin, TRUSTED_CHROME_ORIGIN);
    assert_eq!(
        snapshot.config.trusted_chrome_rect(),
        Rect::new(0, 0, 1280, 64)
    );
    assert_eq!(snapshot.config.content_rect(), Rect::new(0, 64, 1280, 656));
}

#[test]
fn exactly_one_configured_content_surface_can_attach() {
    let mut state = state();
    attach(&mut state);
    let error = state
        .apply(WorkspaceEvent::AttachContent {
            surface_id: surface(),
        })
        .unwrap_err();
    assert_eq!(error, CompositionError::ContentAlreadyAttached);

    let other = ContentSurfaceId::new(8).unwrap();
    let error = state
        .apply(WorkspaceEvent::ContentCrashed { surface_id: other })
        .unwrap_err();
    assert_eq!(
        error,
        CompositionError::WrongContentSurface {
            expected: surface(),
            actual: other,
        }
    );
}

#[test]
fn failed_events_roll_back_the_event_sequence_and_state() {
    let mut state = state();
    let before = state.snapshot();
    assert!(state.apply(WorkspaceEvent::ImeStarted).is_err());
    assert_eq!(state.snapshot(), before);
}

#[test]
fn committed_content_frame_becomes_presentable_without_replacing_chrome() {
    let mut state = state();
    attach(&mut state);
    let effects = state
        .apply(WorkspaceEvent::ContentFrameCommitted {
            surface_id: surface(),
            document_generation: 1,
            frame_sha256: digest('a'),
        })
        .unwrap();
    assert!(
        effects
            .iter()
            .any(|effect| matches!(effect, WorkspaceEffect::Compose(_)))
    );
    let frame = state.composition_frame();
    assert!(frame.content_presentable);
    assert!(!frame.crash_placeholder_visible);
    assert_eq!(frame.trusted_chrome_origin, TRUSTED_CHROME_ORIGIN);
}

#[test]
fn zero_document_generation_is_refused_atomically() {
    let mut state = state();
    attach(&mut state);
    let before = state.snapshot();
    assert_eq!(
        state
            .apply(WorkspaceEvent::ContentFrameCommitted {
                surface_id: surface(),
                document_generation: 0,
                frame_sha256: digest('b'),
            })
            .unwrap_err(),
        CompositionError::InvalidDocumentGeneration
    );
    assert_eq!(state.snapshot(), before);
}

#[test]
fn pointer_routing_respects_the_trusted_chrome_boundary() {
    let mut state = state();
    let chrome = state
        .apply(WorkspaceEvent::PointerMoved { x: 10, y: 10 })
        .unwrap();
    assert_eq!(chrome, vec![WorkspaceEffect::RoutePointerToTrustedChrome]);
    assert_eq!(state.snapshot().pointer_owner, InputOwner::TrustedChrome);

    let content = state
        .apply(WorkspaceEvent::PointerMoved { x: 10, y: 100 })
        .unwrap();
    assert_eq!(content, vec![WorkspaceEffect::RoutePointerToContent]);
    assert_eq!(state.snapshot().pointer_owner, InputOwner::Content);

    let outside = state
        .apply(WorkspaceEvent::PointerMoved { x: -1, y: 0 })
        .unwrap();
    assert_eq!(outside, vec![WorkspaceEffect::DropPointerOutsideWorkspace]);
    assert_eq!(state.snapshot().pointer_owner, InputOwner::None);
}

#[test]
fn content_keyboard_focus_requires_a_live_content_surface() {
    let mut state = state();
    assert_eq!(
        state
            .apply(WorkspaceEvent::KeyboardFocusRequested {
                target: SurfaceTarget::Content,
            })
            .unwrap_err(),
        CompositionError::ContentNotAttached
    );
    attach(&mut state);
    let effects = state
        .apply(WorkspaceEvent::KeyboardFocusRequested {
            target: SurfaceTarget::Content,
        })
        .unwrap();
    assert_eq!(effects, vec![WorkspaceEffect::RouteKeyboardToContent]);
}

#[test]
fn recovering_content_rejects_focus_and_navigation() {
    let mut state = state();
    attach(&mut state);
    state
        .apply(WorkspaceEvent::ContentCrashed {
            surface_id: surface(),
        })
        .unwrap();
    state
        .apply(WorkspaceEvent::BeginContentRecovery {
            requested_session_generation: 2,
        })
        .unwrap();

    let before_focus = state.snapshot();
    assert_eq!(
        state
            .apply(WorkspaceEvent::KeyboardFocusRequested {
                target: SurfaceTarget::Content,
            })
            .unwrap_err(),
        CompositionError::ContentCrashed
    );
    assert_eq!(state.snapshot(), before_focus);

    let before_navigation = state.snapshot();
    assert_eq!(
        state
            .apply(WorkspaceEvent::ExistingContentNavigationRequested)
            .unwrap_err(),
        CompositionError::ContentCrashed
    );
    assert_eq!(state.snapshot(), before_navigation);
}

#[test]
fn recovering_content_drops_pointer_input_until_replacement_frame() {
    let mut state = state();
    attach(&mut state);
    state
        .apply(WorkspaceEvent::ContentCrashed {
            surface_id: surface(),
        })
        .unwrap();
    state
        .apply(WorkspaceEvent::BeginContentRecovery {
            requested_session_generation: 2,
        })
        .unwrap();

    let dropped = state
        .apply(WorkspaceEvent::PointerMoved { x: 10, y: 100 })
        .unwrap();
    assert_eq!(dropped, vec![WorkspaceEffect::DropPointerOutsideWorkspace]);
    assert_eq!(state.snapshot().pointer_owner, InputOwner::None);

    // Trusted chrome remains interactive while content is recovering.
    let chrome = state
        .apply(WorkspaceEvent::PointerMoved { x: 10, y: 10 })
        .unwrap();
    assert_eq!(chrome, vec![WorkspaceEffect::RoutePointerToTrustedChrome]);
    assert_eq!(state.snapshot().pointer_owner, InputOwner::TrustedChrome);
}

#[test]
fn ime_is_owned_only_by_content_keyboard_focus() {
    let mut state = state();
    attach(&mut state);
    assert_eq!(
        state.apply(WorkspaceEvent::ImeStarted).unwrap_err(),
        CompositionError::ImeRequiresContentKeyboardFocus
    );
    state
        .apply(WorkspaceEvent::KeyboardFocusRequested {
            target: SurfaceTarget::Content,
        })
        .unwrap();
    assert_eq!(
        state.apply(WorkspaceEvent::ImeStarted).unwrap(),
        vec![WorkspaceEffect::BeginContentIme]
    );
    assert!(state.snapshot().ime_active);
    assert_eq!(
        state.apply(WorkspaceEvent::ImeEnded).unwrap(),
        vec![WorkspaceEffect::EndContentIme]
    );
    assert!(!state.snapshot().ime_active);
}

#[test]
fn moving_keyboard_focus_to_chrome_ends_content_ime() {
    let mut state = state();
    attach(&mut state);
    state
        .apply(WorkspaceEvent::KeyboardFocusRequested {
            target: SurfaceTarget::Content,
        })
        .unwrap();
    state.apply(WorkspaceEvent::ImeStarted).unwrap();
    let effects = state
        .apply(WorkspaceEvent::KeyboardFocusRequested {
            target: SurfaceTarget::TrustedChrome,
        })
        .unwrap();
    assert_eq!(
        effects,
        vec![
            WorkspaceEffect::EndContentIme,
            WorkspaceEffect::RouteKeyboardToTrustedChrome,
        ]
    );
    assert!(!state.snapshot().ime_active);
}

#[test]
fn every_popup_request_is_denied_without_creating_a_surface() {
    let mut state = state();
    attach(&mut state);
    for expected in 1..=3 {
        assert_eq!(
            state.apply(WorkspaceEvent::PopupRequested).unwrap(),
            vec![WorkspaceEffect::DenyPopup]
        );
        assert_eq!(state.snapshot().rejected_popup_count, expected);
        assert_eq!(state.snapshot().config.content_surface_id, surface());
    }
}

#[test]
fn navigation_is_reduced_to_the_existing_content_surface() {
    let mut state = state();
    assert_eq!(
        state
            .apply(WorkspaceEvent::ExistingContentNavigationRequested)
            .unwrap_err(),
        CompositionError::ContentNotAttached
    );
    attach(&mut state);
    assert_eq!(
        state
            .apply(WorkspaceEvent::ExistingContentNavigationRequested)
            .unwrap(),
        vec![WorkspaceEffect::NavigateExistingContent]
    );
}

#[test]
fn content_crash_preserves_trusted_chrome_and_shows_placeholder() {
    let mut state = state();
    attach(&mut state);
    state
        .apply(WorkspaceEvent::KeyboardFocusRequested {
            target: SurfaceTarget::Content,
        })
        .unwrap();
    state.apply(WorkspaceEvent::ImeStarted).unwrap();
    let effects = state
        .apply(WorkspaceEvent::ContentCrashed {
            surface_id: surface(),
        })
        .unwrap();
    assert!(effects.contains(&WorkspaceEffect::EndContentIme));
    assert!(effects.contains(&WorkspaceEffect::ShowCrashPlaceholder));
    let snapshot = state.snapshot();
    assert!(snapshot.trusted_chrome_visible);
    assert_eq!(snapshot.trusted_chrome_origin, TRUSTED_CHROME_ORIGIN);
    assert_eq!(snapshot.keyboard_owner, InputOwner::TrustedChrome);
    assert!(!snapshot.ime_active);
    assert!(state.composition_frame().crash_placeholder_visible);
}

#[test]
fn a_crashed_surface_cannot_publish_a_frame() {
    let mut state = state();
    attach(&mut state);
    state
        .apply(WorkspaceEvent::ContentCrashed {
            surface_id: surface(),
        })
        .unwrap();
    assert_eq!(
        state
            .apply(WorkspaceEvent::ContentFrameCommitted {
                surface_id: surface(),
                document_generation: 2,
                frame_sha256: digest('c'),
            })
            .unwrap_err(),
        CompositionError::ContentCrashed
    );
}

#[test]
fn recovery_requires_a_crash_and_matching_session_generation() {
    let mut state = state();
    attach(&mut state);
    assert_eq!(
        state
            .apply(WorkspaceEvent::BeginContentRecovery {
                requested_session_generation: 2,
            })
            .unwrap_err(),
        CompositionError::RecoveryRequiresCrash
    );
    state
        .apply(WorkspaceEvent::ContentCrashed {
            surface_id: surface(),
        })
        .unwrap();
    state
        .apply(WorkspaceEvent::BeginContentRecovery {
            requested_session_generation: 2,
        })
        .unwrap();
    assert_eq!(
        state
            .apply(WorkspaceEvent::ContentRecovered {
                surface_id: surface(),
                session_generation: 3,
            })
            .unwrap_err(),
        CompositionError::InvalidSessionGeneration
    );
    let effects = state
        .apply(WorkspaceEvent::ContentRecovered {
            surface_id: surface(),
            session_generation: 2,
        })
        .unwrap();
    assert!(effects.contains(&WorkspaceEffect::AwaitContentFrame));
    assert!(matches!(
        state.snapshot().content,
        ContentLifecycle::Attached
    ));
}

#[test]
fn recovery_does_not_reuse_the_old_presentable_frame() {
    let mut state = state();
    attach(&mut state);
    state
        .apply(WorkspaceEvent::ContentFrameCommitted {
            surface_id: surface(),
            document_generation: 1,
            frame_sha256: digest('d'),
        })
        .unwrap();
    state
        .apply(WorkspaceEvent::ContentCrashed {
            surface_id: surface(),
        })
        .unwrap();
    state
        .apply(WorkspaceEvent::BeginContentRecovery {
            requested_session_generation: 2,
        })
        .unwrap();
    state
        .apply(WorkspaceEvent::ContentRecovered {
            surface_id: surface(),
            session_generation: 2,
        })
        .unwrap();
    assert!(!state.composition_frame().content_presentable);
}

#[test]
fn recovering_surface_cannot_publish_a_frame_before_recovered() {
    let mut state = state();
    attach(&mut state);
    state
        .apply(WorkspaceEvent::ContentCrashed {
            surface_id: surface(),
        })
        .unwrap();
    state
        .apply(WorkspaceEvent::BeginContentRecovery {
            requested_session_generation: 2,
        })
        .unwrap();

    assert_eq!(
        state
            .apply(WorkspaceEvent::ContentFrameCommitted {
                surface_id: surface(),
                document_generation: 2,
                frame_sha256: digest('e'),
            })
            .unwrap_err(),
        CompositionError::ContentCrashed
    );
    assert!(matches!(
        state.snapshot().content,
        ContentLifecycle::Recovering {
            requested_session_generation: 2
        }
    ));
    assert!(!state.composition_frame().content_presentable);
}

#[test]
fn resize_preserves_single_surface_and_recomputes_both_rectangles() {
    let mut state = state();
    attach(&mut state);
    let effects = state
        .apply(WorkspaceEvent::Resize {
            viewport: PixelSize::new(1920, 1080).unwrap(),
            chrome_height: 72,
        })
        .unwrap();
    assert!(
        effects
            .iter()
            .any(|effect| matches!(effect, WorkspaceEffect::Compose(_)))
    );
    let frame = state.composition_frame();
    assert_eq!(frame.content_surface_id, surface());
    assert_eq!(frame.trusted_chrome_rect, Rect::new(0, 0, 1920, 72));
    assert_eq!(frame.content_rect, Rect::new(0, 72, 1920, 1008));
}

#[test]
fn invalid_resize_rolls_back_the_old_geometry() {
    let mut state = state();
    let before = state.snapshot();
    assert!(
        state
            .apply(WorkspaceEvent::Resize {
                viewport: PixelSize::new(640, 480).unwrap(),
                chrome_height: 480,
            })
            .is_err()
    );
    assert_eq!(state.snapshot(), before);
}

#[test]
fn frame_revision_advances_only_for_composition_changes() {
    let mut state = state();
    let initial = state.snapshot().frame_revision;
    state
        .apply(WorkspaceEvent::PointerMoved { x: 1, y: 1 })
        .unwrap();
    assert_eq!(state.snapshot().frame_revision, initial);
    attach(&mut state);
    assert_eq!(state.snapshot().frame_revision, initial + 1);
    state
        .apply(WorkspaceEvent::ContentFrameCommitted {
            surface_id: surface(),
            document_generation: 1,
            frame_sha256: digest('e'),
        })
        .unwrap();
    assert_eq!(state.snapshot().frame_revision, initial + 2);
}

#[test]
fn event_sequence_is_monotonic_for_committed_events() {
    let mut state = state();
    assert_eq!(state.snapshot().event_sequence, 0);
    state
        .apply(WorkspaceEvent::PointerMoved { x: 1, y: 1 })
        .unwrap();
    assert_eq!(state.snapshot().event_sequence, 1);
    state.apply(WorkspaceEvent::PopupRequested).unwrap();
    assert_eq!(state.snapshot().event_sequence, 2);
}

#[test]
fn content_surface_id_zero_is_never_constructible() {
    assert_eq!(
        ContentSurfaceId::new(0).unwrap_err(),
        CompositionError::InvalidContentSurfaceId
    );
}
