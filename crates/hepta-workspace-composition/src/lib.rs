#![forbid(unsafe_code)]

//! Deterministic trusted-chrome/untrusted-content composition contract.
//!
//! The model owns no native window and no Servo object. A future runtime
//! adapter must translate native/compositor and Servo events into this state
//! machine while preserving its single-content-surface and trust invariants.

mod model;

pub use model::{
    CompositionError, CompositionFrame, ContentLifecycle, ContentSurfaceId, InputOwner, PixelSize,
    Rect, SurfaceTarget, TRUSTED_CHROME_ORIGIN, WorkspaceConfig, WorkspaceEffect, WorkspaceEvent,
    WorkspaceSnapshot, WorkspaceState,
};

#[cfg(test)]
mod tests;
