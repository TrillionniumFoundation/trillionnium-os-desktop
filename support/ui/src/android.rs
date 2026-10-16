//! Contract model for an initial full-display Android surface.
//!
//! The model deliberately stops at the negotiated boundary described in
//! `INTEGRATION_CONTRACTS.md`.  It carries display and buffer metadata, fence
//! observations, coordinate transforms and input/lifecycle state, but it does
//! not contain file descriptors, binder objects, SurfaceFlinger calls or a
//! second Android protocol.

use std::collections::BTreeMap;

/// A non-zero identifier for a negotiated Android display instance.
#[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct DisplayInstanceId(u128);

impl DisplayInstanceId {
    pub const fn new(value: u128) -> Option<Self> {
        if value == 0 {
            None
        } else {
            Some(Self(value))
        }
    }

    pub const fn get(self) -> u128 {
        self.0
    }
}

/// A non-zero input-composition session identifier.
#[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct ImeSessionId(u64);

impl ImeSessionId {
    pub const fn new(value: u64) -> Option<Self> {
        if value == 0 {
            None
        } else {
            Some(Self(value))
        }
    }

    pub const fn get(self) -> u64 {
        self.0
    }
}

/// A non-zero identifier for a buffer tracked by this contract model.
#[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct BufferId(u64);

impl BufferId {
    pub const fn new(value: u64) -> Option<Self> {
        if value == 0 {
            None
        } else {
            Some(Self(value))
        }
    }

    pub const fn get(self) -> u64 {
        self.0
    }
}

/// A non-zero identifier for an acquire or release synchronization fence.
/// It is an observation token, not an owned OS file descriptor.
#[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct FenceId(u64);

impl FenceId {
    pub const fn new(value: u64) -> Option<Self> {
        if value == 0 {
            None
        } else {
            Some(Self(value))
        }
    }

    pub const fn get(self) -> u64 {
        self.0
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Extent {
    pub width: u32,
    pub height: u32,
}

impl Extent {
    pub const fn new(width: u32, height: u32) -> Option<Self> {
        if width == 0 || height == 0 {
            None
        } else {
            Some(Self { width, height })
        }
    }

    const fn valid(self) -> bool {
        self.width != 0 && self.height != 0
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PixelFormat {
    Rgba8888,
    Rgbx8888,
    Nv12,
    Yuv420,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum BufferTransport {
    /// The actual dma-buf import/export mechanism is chosen by the compositor.
    DmaBuf,
    /// CPU shared memory is a permitted fallback only when negotiated by A08.
    CpuSharedMemory,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ColorSpace {
    Srgb,
    DisplayP3,
    Bt2020,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Orientation {
    Portrait,
    Landscape,
    ReversePortrait,
    ReverseLandscape,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Rotation {
    Deg0,
    Deg90,
    Deg180,
    Deg270,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct InputPoint {
    pub x: u32,
    pub y: u32,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct SurfacePoint {
    pub x: u32,
    pub y: u32,
}

/// A deterministic integer coordinate transform for touch/pointer input.
///
/// The source extent is the coordinate space supplied by the input provider;
/// the target extent is the full-display surface.  Scaling uses floor
/// arithmetic so every point maps identically across implementations.  A
/// point outside the source extent is rejected instead of being clamped.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct CoordinateTransform {
    pub source: Extent,
    pub target: Extent,
    pub rotation: Rotation,
    pub mirror_x: bool,
    pub mirror_y: bool,
}

impl CoordinateTransform {
    pub const fn new(
        source: Extent,
        target: Extent,
        rotation: Rotation,
        mirror_x: bool,
        mirror_y: bool,
    ) -> Option<Self> {
        if !source.valid() || !target.valid() {
            None
        } else {
            Some(Self {
                source,
                target,
                rotation,
                mirror_x,
                mirror_y,
            })
        }
    }

    pub fn map(self, point: InputPoint) -> Option<SurfacePoint> {
        if point.x >= self.source.width || point.y >= self.source.height {
            return None;
        }

        // For a quarter turn the unrotated intermediate extent is the
        // transpose of the final target extent.
        let (base_width, base_height) = match self.rotation {
            Rotation::Deg90 | Rotation::Deg270 => (self.target.height, self.target.width),
            Rotation::Deg0 | Rotation::Deg180 => (self.target.width, self.target.height),
        };
        let mut x = ((point.x as u64 * base_width as u64) / self.source.width as u64) as u32;
        let mut y = ((point.y as u64 * base_height as u64) / self.source.height as u64) as u32;
        // The input is in range, so floor scaling remains below the target
        // extent.  Keep the guard for defensive robustness if this code is
        // later changed to accept another numeric representation.
        if x >= base_width || y >= base_height {
            return None;
        }
        if self.mirror_x {
            x = base_width - 1 - x;
        }
        if self.mirror_y {
            y = base_height - 1 - y;
        }

        let mapped = match self.rotation {
            Rotation::Deg0 => SurfacePoint { x, y },
            Rotation::Deg90 => SurfacePoint {
                x: self.target.width - 1 - y,
                y: x,
            },
            Rotation::Deg180 => SurfacePoint {
                x: self.target.width - 1 - x,
                y: self.target.height - 1 - y,
            },
            Rotation::Deg270 => SurfacePoint {
                x: y,
                y: self.target.height - 1 - x,
            },
        };
        Some(mapped)
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct DisplaySpec {
    pub extent: Extent,
    pub pixel_format: PixelFormat,
    /// Density expressed in thousandths of a logical density unit.
    pub density_milli: u32,
    pub orientation: Orientation,
    pub color_space: ColorSpace,
    pub input_transform: CoordinateTransform,
}

impl DisplaySpec {
    pub const fn new(
        extent: Extent,
        pixel_format: PixelFormat,
        density_milli: u32,
        orientation: Orientation,
        color_space: ColorSpace,
        input_transform: CoordinateTransform,
    ) -> Option<Self> {
        if !extent.valid() || density_milli == 0 || !input_transform.target.valid() {
            None
        } else {
            Some(Self {
                extent,
                pixel_format,
                density_milli,
                orientation,
                color_space,
                input_transform,
            })
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DisplayLifecycle {
    Negotiating,
    Active,
    Suspended { reason: SuspendReason },
    Resuming,
    Destroyed { reason: DestroyReason },
    Failed { reason: FailureReason },
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SuspendReason {
    AppPaused,
    DisplayPower,
    HostUnavailable,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DestroyReason {
    SurfaceFlingerLost,
    OwnerClosed,
    GenerationReplaced,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum FailureReason {
    InvalidBuffer,
    AcquireFenceFailed,
    ReleaseFenceFailed,
    ImportRejected,
    Unknown,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum FenceState {
    NotRequired,
    Pending(FenceId),
    Signaled,
    Failed(FenceId),
}

impl FenceState {
    const fn ready(self) -> bool {
        matches!(self, Self::NotRequired | Self::Signaled)
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum BufferOwner {
    AndroidProducer,
    Compositor,
    Retired,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum BufferLifecycle {
    Available,
    Queued,
    Displaying,
    Released,
    Retired { reason: BufferRetireReason },
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum BufferRetireReason {
    GenerationChanged,
    DisplayDestroyed,
    AcquireFenceFailed,
    ReleaseFenceFailed,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct BufferDescription {
    pub id: BufferId,
    pub generation: u64,
    pub extent: Extent,
    pub format: PixelFormat,
    pub transport: BufferTransport,
    pub stride: u32,
    pub planes: u8,
}

impl BufferDescription {
    fn valid(self) -> bool {
        self.generation != 0
            && self.extent.valid()
            && self.stride >= self.extent.width
            && self.planes != 0
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct BufferSnapshot {
    pub description: BufferDescription,
    pub owner: BufferOwner,
    pub lifecycle: BufferLifecycle,
    pub acquire_fence: FenceState,
    pub release_fence: FenceState,
}

#[derive(Clone, Debug)]
struct BufferRecord {
    description: BufferDescription,
    owner: BufferOwner,
    lifecycle: BufferLifecycle,
    acquire_fence: FenceState,
    release_fence: FenceState,
}

impl BufferRecord {
    fn snapshot(&self) -> BufferSnapshot {
        BufferSnapshot {
            description: self.description,
            owner: self.owner,
            lifecycle: self.lifecycle,
            acquire_fence: self.acquire_fence,
            release_fence: self.release_fence,
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum TouchPhase {
    Down,
    Move,
    Up,
    Cancel,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum KeyAction {
    Down,
    Up,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ImeEvent {
    Start { session: ImeSessionId },
    Preedit { session: ImeSessionId, text: String },
    Commit { session: ImeSessionId, text: String },
    Finish { session: ImeSessionId },
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum InputEvent {
    Touch {
        slot: u8,
        phase: TouchPhase,
        point: InputPoint,
    },
    Key {
        key_code: u32,
        action: KeyAction,
    },
    Ime(ImeEvent),
    Back,
    Home,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum RoutedInput {
    Touch {
        generation: u64,
        slot: u8,
        phase: TouchPhase,
        point: SurfacePoint,
    },
    Key {
        generation: u64,
        key_code: u32,
        action: KeyAction,
    },
    Ime {
        generation: u64,
        event: ImeEvent,
    },
    Navigation {
        generation: u64,
        action: NavigationAction,
    },
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum NavigationAction {
    Back,
    Home,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ImeState {
    Inactive,
    Composing {
        session: ImeSessionId,
        preedit: String,
    },
    Suspended {
        session: ImeSessionId,
        preedit: String,
    },
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AndroidDisplayError {
    InvalidSpec,
    InvalidTransition,
    GenerationExhausted,
    InvalidGeneration,
    BufferExists,
    BufferNotFound,
    InvalidBufferDescription,
    BufferBusy,
    BufferNotOwned,
    FenceNotReady,
    FenceMismatch,
    FenceAlreadyResolved,
    DisplaySuspended,
    DisplayDestroyed,
    DisplayFailed,
    InvalidInput,
    ImeSessionMismatch,
    ImeNotActive,
}

/// A pure host-side model of one Android full-display surface.
#[derive(Clone, Debug)]
pub struct AndroidDisplaySurface {
    instance: DisplayInstanceId,
    generation: u64,
    spec: DisplaySpec,
    lifecycle: DisplayLifecycle,
    buffers: BTreeMap<BufferId, BufferRecord>,
    ime: ImeState,
}

impl AndroidDisplaySurface {
    pub fn new(
        instance: DisplayInstanceId,
        spec: DisplaySpec,
    ) -> Result<Self, AndroidDisplayError> {
        if !spec.extent.valid()
            || spec.density_milli == 0
            || !spec.input_transform.source.valid()
            || !spec.input_transform.target.valid()
        {
            return Err(AndroidDisplayError::InvalidSpec);
        }
        Ok(Self {
            instance,
            generation: 1,
            spec,
            lifecycle: DisplayLifecycle::Negotiating,
            buffers: BTreeMap::new(),
            ime: ImeState::Inactive,
        })
    }

    pub const fn instance(&self) -> DisplayInstanceId {
        self.instance
    }

    pub const fn generation(&self) -> u64 {
        self.generation
    }

    pub const fn spec(&self) -> DisplaySpec {
        self.spec
    }

    pub const fn lifecycle(&self) -> DisplayLifecycle {
        self.lifecycle
    }

    pub fn ime(&self) -> &ImeState {
        &self.ime
    }

    pub fn buffer(&self, id: BufferId) -> Option<BufferSnapshot> {
        self.buffers.get(&id).map(BufferRecord::snapshot)
    }

    pub fn buffers(&self) -> impl Iterator<Item = BufferSnapshot> + '_ {
        self.buffers.values().map(BufferRecord::snapshot)
    }

    pub fn activate(&mut self) -> Result<(), AndroidDisplayError> {
        if self.lifecycle != DisplayLifecycle::Negotiating {
            return Err(AndroidDisplayError::InvalidTransition);
        }
        self.lifecycle = DisplayLifecycle::Active;
        Ok(())
    }

    pub fn suspend(&mut self, reason: SuspendReason) -> Result<(), AndroidDisplayError> {
        if self.lifecycle != DisplayLifecycle::Active {
            return Err(AndroidDisplayError::InvalidTransition);
        }
        if let ImeState::Composing { session, preedit } = &self.ime {
            self.ime = ImeState::Suspended {
                session: *session,
                preedit: preedit.clone(),
            };
        }
        self.lifecycle = DisplayLifecycle::Suspended { reason };
        Ok(())
    }

    pub fn begin_resume(&mut self) -> Result<(), AndroidDisplayError> {
        if !matches!(self.lifecycle, DisplayLifecycle::Suspended { .. }) {
            return Err(AndroidDisplayError::InvalidTransition);
        }
        self.lifecycle = DisplayLifecycle::Resuming;
        Ok(())
    }

    pub fn finish_resume(&mut self) -> Result<(), AndroidDisplayError> {
        if self.lifecycle != DisplayLifecycle::Resuming {
            return Err(AndroidDisplayError::InvalidTransition);
        }
        if let ImeState::Suspended { session, preedit } = &self.ime {
            self.ime = ImeState::Composing {
                session: *session,
                preedit: preedit.clone(),
            };
        }
        self.lifecycle = DisplayLifecycle::Active;
        Ok(())
    }

    /// Replace the negotiated display generation.  Existing buffers are
    /// retired before the new generation enters negotiation; no buffer is
    /// silently reused across generations.
    pub fn replace_generation(&mut self, spec: DisplaySpec) -> Result<u64, AndroidDisplayError> {
        if matches!(self.lifecycle, DisplayLifecycle::Destroyed { .. }) {
            return Err(AndroidDisplayError::DisplayDestroyed);
        }
        if !spec.extent.valid()
            || spec.density_milli == 0
            || !spec.input_transform.source.valid()
            || !spec.input_transform.target.valid()
        {
            return Err(AndroidDisplayError::InvalidSpec);
        }
        let generation = self
            .generation
            .checked_add(1)
            .ok_or(AndroidDisplayError::GenerationExhausted)?;
        self.retire_buffers(BufferRetireReason::GenerationChanged);
        self.generation = generation;
        self.spec = spec;
        self.lifecycle = DisplayLifecycle::Negotiating;
        self.ime = ImeState::Inactive;
        Ok(generation)
    }

    pub fn destroy(&mut self, reason: DestroyReason) -> Result<(), AndroidDisplayError> {
        if matches!(self.lifecycle, DisplayLifecycle::Destroyed { .. }) {
            return Err(AndroidDisplayError::InvalidTransition);
        }
        self.retire_buffers(BufferRetireReason::DisplayDestroyed);
        self.lifecycle = DisplayLifecycle::Destroyed { reason };
        self.ime = ImeState::Inactive;
        Ok(())
    }

    pub fn register_buffer(
        &mut self,
        description: BufferDescription,
    ) -> Result<(), AndroidDisplayError> {
        self.require_live()?;
        if description.id.get() == 0
            || !description.valid()
            || description.generation != self.generation
        {
            return Err(AndroidDisplayError::InvalidBufferDescription);
        }
        if self.buffers.contains_key(&description.id) {
            return Err(AndroidDisplayError::BufferExists);
        }
        self.buffers.insert(
            description.id,
            BufferRecord {
                description,
                owner: BufferOwner::AndroidProducer,
                lifecycle: BufferLifecycle::Available,
                acquire_fence: FenceState::NotRequired,
                release_fence: FenceState::NotRequired,
            },
        );
        Ok(())
    }

    /// Queue a producer-owned buffer for compositor import.  Reuse is only
    /// possible from Available or Released; a pending release fence keeps the
    /// buffer unavailable.
    pub fn queue_buffer(
        &mut self,
        id: BufferId,
        acquire_fence: FenceState,
    ) -> Result<(), AndroidDisplayError> {
        self.require_active()?;
        let Some(buffer) = self.buffers.get_mut(&id) else {
            return Err(AndroidDisplayError::BufferNotFound);
        };
        if buffer.description.generation != self.generation {
            return Err(AndroidDisplayError::InvalidGeneration);
        }
        if buffer.owner != BufferOwner::AndroidProducer
            || !matches!(
                buffer.lifecycle,
                BufferLifecycle::Available | BufferLifecycle::Released
            )
        {
            return Err(AndroidDisplayError::BufferBusy);
        }
        buffer.owner = BufferOwner::Compositor;
        buffer.lifecycle = BufferLifecycle::Queued;
        buffer.acquire_fence = acquire_fence;
        buffer.release_fence = FenceState::NotRequired;
        Ok(())
    }

    pub fn signal_acquire(
        &mut self,
        id: BufferId,
        fence: FenceId,
    ) -> Result<(), AndroidDisplayError> {
        let Some(buffer) = self.buffers.get_mut(&id) else {
            return Err(AndroidDisplayError::BufferNotFound);
        };
        match buffer.acquire_fence {
            FenceState::Pending(expected) if expected == fence => {
                buffer.acquire_fence = FenceState::Signaled;
                Ok(())
            }
            FenceState::Pending(_) => Err(AndroidDisplayError::FenceMismatch),
            FenceState::NotRequired | FenceState::Signaled | FenceState::Failed(_) => {
                Err(AndroidDisplayError::FenceAlreadyResolved)
            }
        }
    }

    pub fn fail_acquire(
        &mut self,
        id: BufferId,
        fence: FenceId,
    ) -> Result<(), AndroidDisplayError> {
        let Some(buffer) = self.buffers.get_mut(&id) else {
            return Err(AndroidDisplayError::BufferNotFound);
        };
        match buffer.acquire_fence {
            FenceState::Pending(expected) if expected == fence => {
                buffer.acquire_fence = FenceState::Failed(fence);
                buffer.owner = BufferOwner::Retired;
                buffer.lifecycle = BufferLifecycle::Retired {
                    reason: BufferRetireReason::AcquireFenceFailed,
                };
                Ok(())
            }
            FenceState::Pending(_) => Err(AndroidDisplayError::FenceMismatch),
            FenceState::NotRequired | FenceState::Signaled | FenceState::Failed(_) => {
                Err(AndroidDisplayError::FenceAlreadyResolved)
            }
        }
    }

    /// Promote a queued buffer to the display only after its acquire fence is
    /// observed ready.  A real compositor must perform the corresponding
    /// synchronization; this is only the explicit contract state.
    pub fn display_buffer(
        &mut self,
        id: BufferId,
        release_fence: FenceState,
    ) -> Result<(), AndroidDisplayError> {
        self.require_active()?;
        let Some(buffer) = self.buffers.get_mut(&id) else {
            return Err(AndroidDisplayError::BufferNotFound);
        };
        if buffer.owner != BufferOwner::Compositor || buffer.lifecycle != BufferLifecycle::Queued {
            return Err(AndroidDisplayError::BufferNotOwned);
        }
        if !buffer.acquire_fence.ready() {
            return Err(AndroidDisplayError::FenceNotReady);
        }
        buffer.lifecycle = BufferLifecycle::Displaying;
        buffer.release_fence = release_fence;
        Ok(())
    }

    pub fn signal_release(
        &mut self,
        id: BufferId,
        fence: FenceId,
    ) -> Result<(), AndroidDisplayError> {
        let Some(buffer) = self.buffers.get_mut(&id) else {
            return Err(AndroidDisplayError::BufferNotFound);
        };
        match buffer.release_fence {
            FenceState::Pending(expected) if expected == fence => {
                buffer.release_fence = FenceState::Signaled;
                Ok(())
            }
            FenceState::Pending(_) => Err(AndroidDisplayError::FenceMismatch),
            FenceState::NotRequired | FenceState::Signaled | FenceState::Failed(_) => {
                Err(AndroidDisplayError::FenceAlreadyResolved)
            }
        }
    }

    pub fn fail_release(
        &mut self,
        id: BufferId,
        fence: FenceId,
    ) -> Result<(), AndroidDisplayError> {
        let Some(buffer) = self.buffers.get_mut(&id) else {
            return Err(AndroidDisplayError::BufferNotFound);
        };
        match buffer.release_fence {
            FenceState::Pending(expected) if expected == fence => {
                buffer.release_fence = FenceState::Failed(fence);
                buffer.owner = BufferOwner::Retired;
                buffer.lifecycle = BufferLifecycle::Retired {
                    reason: BufferRetireReason::ReleaseFenceFailed,
                };
                Ok(())
            }
            FenceState::Pending(_) => Err(AndroidDisplayError::FenceMismatch),
            FenceState::NotRequired | FenceState::Signaled | FenceState::Failed(_) => {
                Err(AndroidDisplayError::FenceAlreadyResolved)
            }
        }
    }

    /// Return a displayed buffer to the producer.  A pending or failed
    /// release fence never becomes reusable by inference.
    pub fn release_buffer(&mut self, id: BufferId) -> Result<(), AndroidDisplayError> {
        let Some(buffer) = self.buffers.get_mut(&id) else {
            return Err(AndroidDisplayError::BufferNotFound);
        };
        if buffer.owner != BufferOwner::Compositor
            || buffer.lifecycle != BufferLifecycle::Displaying
        {
            return Err(AndroidDisplayError::BufferNotOwned);
        }
        if !buffer.release_fence.ready() {
            return Err(AndroidDisplayError::FenceNotReady);
        }
        buffer.owner = BufferOwner::AndroidProducer;
        buffer.lifecycle = BufferLifecycle::Released;
        buffer.acquire_fence = FenceState::NotRequired;
        buffer.release_fence = FenceState::NotRequired;
        Ok(())
    }

    pub fn route_input(&mut self, event: InputEvent) -> Result<RoutedInput, AndroidDisplayError> {
        self.require_active()?;
        match event {
            InputEvent::Touch { slot, phase, point } => {
                let point = self
                    .spec
                    .input_transform
                    .map(point)
                    .ok_or(AndroidDisplayError::InvalidInput)?;
                Ok(RoutedInput::Touch {
                    generation: self.generation,
                    slot,
                    phase,
                    point,
                })
            }
            InputEvent::Key { key_code, action } => Ok(RoutedInput::Key {
                generation: self.generation,
                key_code,
                action,
            }),
            InputEvent::Ime(event) => {
                self.apply_ime(&event)?;
                Ok(RoutedInput::Ime {
                    generation: self.generation,
                    event,
                })
            }
            InputEvent::Back => Ok(RoutedInput::Navigation {
                generation: self.generation,
                action: NavigationAction::Back,
            }),
            InputEvent::Home => Ok(RoutedInput::Navigation {
                generation: self.generation,
                action: NavigationAction::Home,
            }),
        }
    }

    fn apply_ime(&mut self, event: &ImeEvent) -> Result<(), AndroidDisplayError> {
        match event {
            ImeEvent::Start { session } => {
                if !matches!(self.ime, ImeState::Inactive) {
                    return Err(AndroidDisplayError::ImeNotActive);
                }
                self.ime = ImeState::Composing {
                    session: *session,
                    preedit: String::new(),
                };
                Ok(())
            }
            ImeEvent::Preedit { session, text } => match &mut self.ime {
                ImeState::Composing {
                    session: current,
                    preedit,
                } if current == session => {
                    *preedit = text.clone();
                    Ok(())
                }
                _ => Err(AndroidDisplayError::ImeSessionMismatch),
            },
            ImeEvent::Commit { session, .. } => match &mut self.ime {
                ImeState::Composing {
                    session: current,
                    preedit,
                } if current == session => {
                    preedit.clear();
                    Ok(())
                }
                _ => Err(AndroidDisplayError::ImeSessionMismatch),
            },
            ImeEvent::Finish { session } => match self.ime {
                ImeState::Composing {
                    session: current, ..
                } if current == *session => {
                    self.ime = ImeState::Inactive;
                    Ok(())
                }
                _ => Err(AndroidDisplayError::ImeSessionMismatch),
            },
        }
    }

    fn require_live(&self) -> Result<(), AndroidDisplayError> {
        match self.lifecycle {
            DisplayLifecycle::Destroyed { .. } => Err(AndroidDisplayError::DisplayDestroyed),
            DisplayLifecycle::Failed { .. } => Err(AndroidDisplayError::DisplayFailed),
            _ => Ok(()),
        }
    }

    fn require_active(&self) -> Result<(), AndroidDisplayError> {
        match self.lifecycle {
            DisplayLifecycle::Active => Ok(()),
            DisplayLifecycle::Suspended { .. } | DisplayLifecycle::Resuming => {
                Err(AndroidDisplayError::DisplaySuspended)
            }
            DisplayLifecycle::Destroyed { .. } => Err(AndroidDisplayError::DisplayDestroyed),
            DisplayLifecycle::Failed { .. } => Err(AndroidDisplayError::DisplayFailed),
            DisplayLifecycle::Negotiating => Err(AndroidDisplayError::InvalidTransition),
        }
    }

    fn retire_buffers(&mut self, reason: BufferRetireReason) {
        for buffer in self.buffers.values_mut() {
            buffer.owner = BufferOwner::Retired;
            buffer.lifecycle = BufferLifecycle::Retired { reason };
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn spec() -> DisplaySpec {
        let extent = Extent::new(1920, 1080).expect("valid extent");
        let input = CoordinateTransform::new(
            Extent::new(1920, 1080).expect("valid source"),
            extent,
            Rotation::Deg0,
            false,
            false,
        )
        .expect("valid transform");
        DisplaySpec::new(
            extent,
            PixelFormat::Rgba8888,
            160_000,
            Orientation::Landscape,
            ColorSpace::Srgb,
            input,
        )
        .expect("valid display spec")
    }

    fn surface() -> AndroidDisplaySurface {
        AndroidDisplaySurface::new(DisplayInstanceId::new(1).unwrap(), spec()).unwrap()
    }

    fn description(surface: &AndroidDisplaySurface, id: u64) -> BufferDescription {
        BufferDescription {
            id: BufferId::new(id).unwrap(),
            generation: surface.generation(),
            extent: surface.spec().extent,
            format: surface.spec().pixel_format,
            transport: BufferTransport::CpuSharedMemory,
            stride: surface.spec().extent.width,
            planes: 1,
        }
    }

    #[test]
    fn display_generation_retires_old_buffers_before_negotiation() {
        let mut display = surface();
        display.activate().unwrap();
        display.register_buffer(description(&display, 1)).unwrap();
        let old_generation = display.generation();
        let next = display.replace_generation(spec()).unwrap();
        assert!(next > old_generation);
        assert_eq!(display.lifecycle(), DisplayLifecycle::Negotiating);
        assert_eq!(
            display.buffer(BufferId::new(1).unwrap()).unwrap().lifecycle,
            BufferLifecycle::Retired {
                reason: BufferRetireReason::GenerationChanged
            }
        );
        assert_eq!(display.register_buffer(description(&display, 2)), Ok(()));
        assert_eq!(
            display.register_buffer(BufferDescription {
                generation: old_generation,
                ..description(&display, 3)
            }),
            Err(AndroidDisplayError::InvalidBufferDescription)
        );
    }

    #[test]
    fn buffer_cannot_be_reused_until_release_fence_signals() {
        let mut display = surface();
        display.activate().unwrap();
        let id = BufferId::new(1).unwrap();
        display.register_buffer(description(&display, 1)).unwrap();
        display
            .queue_buffer(id, FenceState::Pending(FenceId::new(10).unwrap()))
            .unwrap();
        assert_eq!(
            display.display_buffer(id, FenceState::Pending(FenceId::new(11).unwrap())),
            Err(AndroidDisplayError::FenceNotReady)
        );
        display
            .signal_acquire(id, FenceId::new(10).unwrap())
            .unwrap();
        display
            .display_buffer(id, FenceState::Pending(FenceId::new(11).unwrap()))
            .unwrap();
        assert_eq!(
            display.release_buffer(id),
            Err(AndroidDisplayError::FenceNotReady)
        );
        assert_eq!(
            display.queue_buffer(id, FenceState::NotRequired),
            Err(AndroidDisplayError::BufferBusy)
        );
        display
            .signal_release(id, FenceId::new(11).unwrap())
            .unwrap();
        display.release_buffer(id).unwrap();
        display.queue_buffer(id, FenceState::NotRequired).unwrap();
    }

    #[test]
    fn failed_fence_retires_buffer_without_inference() {
        let mut display = surface();
        display.activate().unwrap();
        let id = BufferId::new(1).unwrap();
        display.register_buffer(description(&display, 1)).unwrap();
        display
            .queue_buffer(id, FenceState::Pending(FenceId::new(12).unwrap()))
            .unwrap();
        display.fail_acquire(id, FenceId::new(12).unwrap()).unwrap();
        let buffer = display.buffer(id).unwrap();
        assert_eq!(buffer.owner, BufferOwner::Retired);
        assert_eq!(
            buffer.lifecycle,
            BufferLifecycle::Retired {
                reason: BufferRetireReason::AcquireFenceFailed
            }
        );
        assert_eq!(
            display.queue_buffer(id, FenceState::NotRequired),
            Err(AndroidDisplayError::BufferBusy)
        );
    }

    #[test]
    fn coordinate_transform_maps_rotation_and_rejects_out_of_bounds() {
        let transform = CoordinateTransform::new(
            Extent::new(2, 3).unwrap(),
            Extent::new(3, 2).unwrap(),
            Rotation::Deg90,
            false,
            false,
        )
        .unwrap();
        assert_eq!(
            transform.map(InputPoint { x: 0, y: 0 }),
            Some(SurfacePoint { x: 2, y: 0 })
        );
        assert_eq!(
            transform.map(InputPoint { x: 1, y: 2 }),
            Some(SurfacePoint { x: 0, y: 1 })
        );
        assert_eq!(transform.map(InputPoint { x: 2, y: 0 }), None);
    }

    #[test]
    fn ime_back_home_and_suspension_are_explicit() {
        let mut display = surface();
        display.activate().unwrap();
        let session = ImeSessionId::new(7).unwrap();
        display
            .route_input(InputEvent::Ime(ImeEvent::Start { session }))
            .unwrap();
        display
            .route_input(InputEvent::Ime(ImeEvent::Preedit {
                session,
                text: "ni".into(),
            }))
            .unwrap();
        assert_eq!(
            display.ime(),
            &ImeState::Composing {
                session,
                preedit: "ni".into()
            }
        );
        assert_eq!(
            display.route_input(InputEvent::Back).unwrap(),
            RoutedInput::Navigation {
                generation: 1,
                action: NavigationAction::Back
            }
        );
        assert_eq!(
            display.route_input(InputEvent::Home).unwrap(),
            RoutedInput::Navigation {
                generation: 1,
                action: NavigationAction::Home
            }
        );
        display.suspend(SuspendReason::AppPaused).unwrap();
        assert!(matches!(display.ime(), ImeState::Suspended { .. }));
        assert_eq!(
            display.route_input(InputEvent::Home),
            Err(AndroidDisplayError::DisplaySuspended)
        );
        display.begin_resume().unwrap();
        display.finish_resume().unwrap();
        assert!(matches!(display.ime(), ImeState::Composing { .. }));
        display.destroy(DestroyReason::OwnerClosed).unwrap();
        assert_eq!(display.ime(), &ImeState::Inactive);
        assert_eq!(
            display.route_input(InputEvent::Back),
            Err(AndroidDisplayError::DisplayDestroyed)
        );
    }

    #[test]
    fn display_destroy_retires_all_buffers_and_rejects_new_ones() {
        let mut display = surface();
        display.activate().unwrap();
        display.register_buffer(description(&display, 1)).unwrap();
        display.destroy(DestroyReason::SurfaceFlingerLost).unwrap();
        assert_eq!(
            display.buffer(BufferId::new(1).unwrap()).unwrap().lifecycle,
            BufferLifecycle::Retired {
                reason: BufferRetireReason::DisplayDestroyed
            }
        );
        assert_eq!(
            display.register_buffer(BufferDescription {
                id: BufferId::new(2).unwrap(),
                ..description(&display, 2)
            }),
            Err(AndroidDisplayError::DisplayDestroyed)
        );
    }
}
