use crate::model;
use crate::{
    CompositionError, CompositionFrame, ContentLifecycle, InputOwner, WorkspaceConfig,
    WorkspaceEffect, WorkspaceEvent, WorkspaceSnapshot,
};

/// Public workspace state with lifecycle-aware input admission.
///
/// The lower deterministic model remains private. This wrapper prevents a
/// pointer from being routed to a content rectangle unless the content surface
/// is explicitly live (`Attached` or `FrameReady`), and it rechecks ownership
/// invariants after every transition.
#[derive(Debug, Clone)]
pub struct WorkspaceState {
    inner: model::WorkspaceState,
}

impl WorkspaceState {
    pub fn new(config: WorkspaceConfig) -> Result<Self, CompositionError> {
        let state = Self {
            inner: model::WorkspaceState::new(config)?,
        };
        state.assert_input_authority()?;
        Ok(state)
    }

    pub fn snapshot(&self) -> WorkspaceSnapshot {
        self.inner.snapshot()
    }

    pub fn composition_frame(&self) -> CompositionFrame {
        self.inner.composition_frame()
    }

    pub fn apply(
        &mut self,
        event: WorkspaceEvent,
    ) -> Result<Vec<WorkspaceEffect>, CompositionError> {
        let previous = self.inner.clone();
        let admitted = match event {
            WorkspaceEvent::PointerMoved { x, y } => {
                let snapshot = self.inner.snapshot();
                if content_unavailable(&snapshot.content)
                    && snapshot.config.content_rect().contains(x, y)
                {
                    // Preserve one accepted event transition and the model's
                    // canonical drop effect without exposing stale content
                    // coordinates to the lower routing branch.
                    WorkspaceEvent::PointerMoved { x: -1, y: -1 }
                } else {
                    WorkspaceEvent::PointerMoved { x, y }
                }
            }
            other => other,
        };

        match self.inner.apply(admitted) {
            Ok(effects) => {
                if let Err(error) = self.assert_input_authority() {
                    self.inner = previous;
                    Err(error)
                } else {
                    Ok(effects)
                }
            }
            Err(error) => {
                self.inner = previous;
                Err(error)
            }
        }
    }

    fn assert_input_authority(&self) -> Result<(), CompositionError> {
        let snapshot = self.inner.snapshot();
        if content_unavailable(&snapshot.content) {
            if snapshot.pointer_owner == InputOwner::Content {
                return Err(CompositionError::InvariantViolation(
                    "unavailable content retains pointer ownership",
                ));
            }
            if snapshot.keyboard_owner == InputOwner::Content {
                return Err(CompositionError::InvariantViolation(
                    "unavailable content retains keyboard ownership",
                ));
            }
            if snapshot.ime_active {
                return Err(CompositionError::InvariantViolation(
                    "unavailable content retains IME authority",
                ));
            }
        }
        Ok(())
    }
}

const fn content_unavailable(content: &ContentLifecycle) -> bool {
    matches!(
        content,
        ContentLifecycle::Detached
            | ContentLifecycle::Crashed { .. }
            | ContentLifecycle::Recovering { .. }
    )
}
