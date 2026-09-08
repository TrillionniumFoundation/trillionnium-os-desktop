use hepta_workspace_composition::{
    ContentSurfaceId, InputOwner, PixelSize, WorkspaceConfig, WorkspaceEffect, WorkspaceEvent,
    WorkspaceState,
};

fn fixture() -> (WorkspaceState, ContentSurfaceId) {
    let surface = ContentSurfaceId::new(1).unwrap();
    let config = WorkspaceConfig::new(PixelSize::new(800, 600).unwrap(), 80, surface).unwrap();
    (WorkspaceState::new(config).unwrap(), surface)
}

fn pointer_to_content(state: &mut WorkspaceState) -> Vec<WorkspaceEffect> {
    state
        .apply(WorkspaceEvent::PointerMoved { x: 10, y: 100 })
        .unwrap()
}

#[test]
fn detached_content_never_acquires_pointer_authority() {
    let (mut state, _) = fixture();
    assert_eq!(
        pointer_to_content(&mut state),
        vec![WorkspaceEffect::DropPointerOutsideWorkspace]
    );
    assert_eq!(state.snapshot().pointer_owner, InputOwner::None);

    assert_eq!(
        state
            .apply(WorkspaceEvent::PointerMoved { x: 10, y: 20 })
            .unwrap(),
        vec![WorkspaceEffect::RoutePointerToTrustedChrome]
    );
    assert_eq!(state.snapshot().pointer_owner, InputOwner::TrustedChrome);
}

#[test]
fn crashed_content_cannot_reacquire_pointer_before_recovery() {
    let (mut state, surface) = fixture();
    state
        .apply(WorkspaceEvent::AttachContent { surface_id: surface })
        .unwrap();
    assert_eq!(
        pointer_to_content(&mut state),
        vec![WorkspaceEffect::RoutePointerToContent]
    );
    assert_eq!(state.snapshot().pointer_owner, InputOwner::Content);

    state
        .apply(WorkspaceEvent::ContentCrashed { surface_id: surface })
        .unwrap();
    assert_eq!(state.snapshot().pointer_owner, InputOwner::None);
    assert_eq!(
        pointer_to_content(&mut state),
        vec![WorkspaceEffect::DropPointerOutsideWorkspace]
    );
    assert_eq!(state.snapshot().pointer_owner, InputOwner::None);
}

#[test]
fn recovering_content_drops_pointer_but_trusted_chrome_remains_live() {
    let (mut state, surface) = fixture();
    state
        .apply(WorkspaceEvent::AttachContent { surface_id: surface })
        .unwrap();
    state
        .apply(WorkspaceEvent::ContentCrashed { surface_id: surface })
        .unwrap();
    state
        .apply(WorkspaceEvent::BeginContentRecovery {
            requested_session_generation: 7,
        })
        .unwrap();

    assert_eq!(
        pointer_to_content(&mut state),
        vec![WorkspaceEffect::DropPointerOutsideWorkspace]
    );
    assert_eq!(state.snapshot().pointer_owner, InputOwner::None);
    assert_eq!(
        state
            .apply(WorkspaceEvent::PointerMoved { x: 10, y: 20 })
            .unwrap(),
        vec![WorkspaceEffect::RoutePointerToTrustedChrome]
    );
    assert_eq!(state.snapshot().pointer_owner, InputOwner::TrustedChrome);
}

#[test]
fn successfully_recovered_attached_content_can_route_pointer_again() {
    let (mut state, surface) = fixture();
    state
        .apply(WorkspaceEvent::AttachContent { surface_id: surface })
        .unwrap();
    state
        .apply(WorkspaceEvent::ContentCrashed { surface_id: surface })
        .unwrap();
    state
        .apply(WorkspaceEvent::BeginContentRecovery {
            requested_session_generation: 9,
        })
        .unwrap();
    state
        .apply(WorkspaceEvent::ContentRecovered {
            surface_id: surface,
            session_generation: 9,
        })
        .unwrap();

    assert_eq!(
        pointer_to_content(&mut state),
        vec![WorkspaceEffect::RoutePointerToContent]
    );
    assert_eq!(state.snapshot().pointer_owner, InputOwner::Content);
}
