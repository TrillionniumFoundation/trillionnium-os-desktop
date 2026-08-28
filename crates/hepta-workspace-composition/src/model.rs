use std::error::Error;
use std::fmt;

use trillionnium_contract_core::Sha256Hex;

pub const TRUSTED_CHROME_ORIGIN: &str = "https://shell.system.hepta.invalid";
const MAX_VIEWPORT_DIMENSION: u32 = 32_768;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PixelSize {
    pub width: u32,
    pub height: u32,
}

impl PixelSize {
    pub fn new(width: u32, height: u32) -> Result<Self, CompositionError> {
        if width == 0 || height == 0 {
            return Err(CompositionError::ZeroViewport);
        }
        if width > MAX_VIEWPORT_DIMENSION || height > MAX_VIEWPORT_DIMENSION {
            return Err(CompositionError::ViewportTooLarge { width, height });
        }
        Ok(Self { width, height })
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Rect {
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
}

impl Rect {
    pub const fn new(x: i32, y: i32, width: u32, height: u32) -> Self {
        Self {
            x,
            y,
            width,
            height,
        }
    }

    pub fn contains(&self, x: i32, y: i32) -> bool {
        let right = i64::from(self.x) + i64::from(self.width);
        let bottom = i64::from(self.y) + i64::from(self.height);
        i64::from(x) >= i64::from(self.x)
            && i64::from(x) < right
            && i64::from(y) >= i64::from(self.y)
            && i64::from(y) < bottom
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct ContentSurfaceId(u64);

impl ContentSurfaceId {
    pub fn new(value: u64) -> Result<Self, CompositionError> {
        if value == 0 {
            Err(CompositionError::InvalidContentSurfaceId)
        } else {
            Ok(Self(value))
        }
    }

    pub const fn get(self) -> u64 {
        self.0
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SurfaceTarget {
    TrustedChrome,
    Content,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InputOwner {
    None,
    TrustedChrome,
    Content,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ContentLifecycle {
    Detached,
    Attached,
    FrameReady {
        document_generation: u64,
        frame_sha256: Sha256Hex,
    },
    Crashed {
        crash_generation: u64,
    },
    Recovering {
        requested_session_generation: u64,
    },
}

impl ContentLifecycle {
    pub const fn has_live_surface(&self) -> bool {
        matches!(
            self,
            Self::Attached | Self::FrameReady { .. } | Self::Recovering { .. }
        )
    }

    pub const fn has_presentable_frame(&self) -> bool {
        matches!(self, Self::FrameReady { .. })
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct WorkspaceConfig {
    pub viewport: PixelSize,
    pub chrome_height: u32,
    pub content_surface_id: ContentSurfaceId,
}

impl WorkspaceConfig {
    pub fn new(
        viewport: PixelSize,
        chrome_height: u32,
        content_surface_id: ContentSurfaceId,
    ) -> Result<Self, CompositionError> {
        if chrome_height == 0 || chrome_height >= viewport.height {
            return Err(CompositionError::InvalidChromeHeight {
                chrome_height,
                viewport_height: viewport.height,
            });
        }
        Ok(Self {
            viewport,
            chrome_height,
            content_surface_id,
        })
    }

    pub const fn trusted_chrome_rect(self) -> Rect {
        Rect::new(0, 0, self.viewport.width, self.chrome_height)
    }

    pub fn content_rect(self) -> Rect {
        Rect::new(
            0,
            i32::try_from(self.chrome_height).unwrap_or(i32::MAX),
            self.viewport.width,
            self.viewport.height - self.chrome_height,
        )
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CompositionFrame {
    pub frame_revision: u64,
    pub trusted_chrome_origin: &'static str,
    pub trusted_chrome_rect: Rect,
    pub content_surface_id: ContentSurfaceId,
    pub content_rect: Rect,
    pub content_presentable: bool,
    pub crash_placeholder_visible: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WorkspaceSnapshot {
    pub event_sequence: u64,
    pub frame_revision: u64,
    pub config: WorkspaceConfig,
    pub content: ContentLifecycle,
    pub pointer_owner: InputOwner,
    pub keyboard_owner: InputOwner,
    pub ime_active: bool,
    pub rejected_popup_count: u64,
    pub trusted_chrome_visible: bool,
    pub trusted_chrome_origin: &'static str,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum WorkspaceEvent {
    AttachContent {
        surface_id: ContentSurfaceId,
    },
    ContentFrameCommitted {
        surface_id: ContentSurfaceId,
        document_generation: u64,
        frame_sha256: Sha256Hex,
    },
    PointerMoved {
        x: i32,
        y: i32,
    },
    KeyboardFocusRequested {
        target: SurfaceTarget,
    },
    ImeStarted,
    ImeEnded,
    ExistingContentNavigationRequested,
    PopupRequested,
    ContentCrashed {
        surface_id: ContentSurfaceId,
    },
    BeginContentRecovery {
        requested_session_generation: u64,
    },
    ContentRecovered {
        surface_id: ContentSurfaceId,
        session_generation: u64,
    },
    Resize {
        viewport: PixelSize,
        chrome_height: u32,
    },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum WorkspaceEffect {
    Compose(CompositionFrame),
    RoutePointerToTrustedChrome,
    RoutePointerToContent,
    DropPointerOutsideWorkspace,
    RouteKeyboardToTrustedChrome,
    RouteKeyboardToContent,
    BeginContentIme,
    EndContentIme,
    NavigateExistingContent,
    DenyPopup,
    ShowCrashPlaceholder,
    AwaitContentFrame,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CompositionError {
    ZeroViewport,
    ViewportTooLarge {
        width: u32,
        height: u32,
    },
    InvalidChromeHeight {
        chrome_height: u32,
        viewport_height: u32,
    },
    InvalidContentSurfaceId,
    WrongContentSurface {
        expected: ContentSurfaceId,
        actual: ContentSurfaceId,
    },
    ContentAlreadyAttached,
    ContentNotAttached,
    ContentCrashed,
    InvalidDocumentGeneration,
    InvalidSessionGeneration,
    ImeRequiresContentKeyboardFocus,
    ImeAlreadyActive,
    ImeNotActive,
    RecoveryRequiresCrash,
    EventSequenceExhausted,
    FrameRevisionExhausted,
    PopupCounterExhausted,
    InvariantViolation(&'static str),
}

impl fmt::Display for CompositionError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::ZeroViewport => formatter.write_str("workspace viewport must be non-zero"),
            Self::ViewportTooLarge { width, height } => write!(
                formatter,
                "workspace viewport {width}x{height} exceeds the product bound"
            ),
            Self::InvalidChromeHeight {
                chrome_height,
                viewport_height,
            } => write!(
                formatter,
                "trusted chrome height {chrome_height} is invalid for viewport height {viewport_height}"
            ),
            Self::InvalidContentSurfaceId => {
                formatter.write_str("content surface id must be non-zero")
            }
            Self::WrongContentSurface { expected, actual } => write!(
                formatter,
                "content event targeted surface {}, expected {}",
                actual.get(),
                expected.get()
            ),
            Self::ContentAlreadyAttached => {
                formatter.write_str("the single content surface is already attached")
            }
            Self::ContentNotAttached => formatter.write_str("content surface is not attached"),
            Self::ContentCrashed => formatter.write_str("content surface is crashed"),
            Self::InvalidDocumentGeneration => {
                formatter.write_str("document generation must be non-zero")
            }
            Self::InvalidSessionGeneration => {
                formatter.write_str("session generation must be non-zero")
            }
            Self::ImeRequiresContentKeyboardFocus => {
                formatter.write_str("IME requires content keyboard ownership")
            }
            Self::ImeAlreadyActive => formatter.write_str("IME is already active"),
            Self::ImeNotActive => formatter.write_str("IME is not active"),
            Self::RecoveryRequiresCrash => {
                formatter.write_str("content recovery requires a crashed content surface")
            }
            Self::EventSequenceExhausted => formatter.write_str("event sequence exhausted"),
            Self::FrameRevisionExhausted => formatter.write_str("frame revision exhausted"),
            Self::PopupCounterExhausted => formatter.write_str("popup counter exhausted"),
            Self::InvariantViolation(reason) => {
                write!(formatter, "workspace invariant failed: {reason}")
            }
        }
    }
}

impl Error for CompositionError {}

#[derive(Debug, Clone)]
pub struct WorkspaceState {
    config: WorkspaceConfig,
    content: ContentLifecycle,
    pointer_owner: InputOwner,
    keyboard_owner: InputOwner,
    ime_active: bool,
    event_sequence: u64,
    frame_revision: u64,
    rejected_popup_count: u64,
}

impl WorkspaceState {
    pub fn new(config: WorkspaceConfig) -> Result<Self, CompositionError> {
        let state = Self {
            config,
            content: ContentLifecycle::Detached,
            pointer_owner: InputOwner::None,
            keyboard_owner: InputOwner::None,
            ime_active: false,
            event_sequence: 0,
            frame_revision: 0,
            rejected_popup_count: 0,
        };
        state.assert_invariants()?;
        Ok(state)
    }

    pub fn snapshot(&self) -> WorkspaceSnapshot {
        WorkspaceSnapshot {
            event_sequence: self.event_sequence,
            frame_revision: self.frame_revision,
            config: self.config,
            content: self.content.clone(),
            pointer_owner: self.pointer_owner,
            keyboard_owner: self.keyboard_owner,
            ime_active: self.ime_active,
            rejected_popup_count: self.rejected_popup_count,
            trusted_chrome_visible: true,
            trusted_chrome_origin: TRUSTED_CHROME_ORIGIN,
        }
    }

    pub fn composition_frame(&self) -> CompositionFrame {
        CompositionFrame {
            frame_revision: self.frame_revision,
            trusted_chrome_origin: TRUSTED_CHROME_ORIGIN,
            trusted_chrome_rect: self.config.trusted_chrome_rect(),
            content_surface_id: self.config.content_surface_id,
            content_rect: self.config.content_rect(),
            content_presentable: self.content.has_presentable_frame(),
            crash_placeholder_visible: matches!(self.content, ContentLifecycle::Crashed { .. }),
        }
    }

    pub fn apply(
        &mut self,
        event: WorkspaceEvent,
    ) -> Result<Vec<WorkspaceEffect>, CompositionError> {
        let previous = self.clone();
        let result = self.apply_inner(event);
        match result {
            Ok(effects) => {
                if let Err(error) = self.assert_invariants() {
                    *self = previous;
                    return Err(error);
                }
                Ok(effects)
            }
            Err(error) => {
                *self = previous;
                Err(error)
            }
        }
    }

    fn apply_inner(
        &mut self,
        event: WorkspaceEvent,
    ) -> Result<Vec<WorkspaceEffect>, CompositionError> {
        self.event_sequence = self
            .event_sequence
            .checked_add(1)
            .ok_or(CompositionError::EventSequenceExhausted)?;

        let mut effects = Vec::new();
        match event {
            WorkspaceEvent::AttachContent { surface_id } => {
                self.require_surface(surface_id)?;
                if !matches!(self.content, ContentLifecycle::Detached) {
                    return Err(CompositionError::ContentAlreadyAttached);
                }
                self.content = ContentLifecycle::Attached;
                self.advance_frame()?;
                effects.push(WorkspaceEffect::AwaitContentFrame);
                effects.push(WorkspaceEffect::Compose(self.composition_frame()));
            }
            WorkspaceEvent::ContentFrameCommitted {
                surface_id,
                document_generation,
                frame_sha256,
            } => {
                self.require_surface(surface_id)?;
                if document_generation == 0 {
                    return Err(CompositionError::InvalidDocumentGeneration);
                }
                match self.content {
                    ContentLifecycle::Detached => {
                        return Err(CompositionError::ContentNotAttached);
                    }
                    ContentLifecycle::Crashed { .. } => {
                        return Err(CompositionError::ContentCrashed);
                    }
                    ContentLifecycle::Attached
                    | ContentLifecycle::FrameReady { .. }
                    | ContentLifecycle::Recovering { .. } => {}
                }
                self.content = ContentLifecycle::FrameReady {
                    document_generation,
                    frame_sha256,
                };
                self.advance_frame()?;
                effects.push(WorkspaceEffect::Compose(self.composition_frame()));
            }
            WorkspaceEvent::PointerMoved { x, y } => {
                if self.config.trusted_chrome_rect().contains(x, y) {
                    self.pointer_owner = InputOwner::TrustedChrome;
                    effects.push(WorkspaceEffect::RoutePointerToTrustedChrome);
                } else if self.config.content_rect().contains(x, y) {
                    self.pointer_owner = InputOwner::Content;
                    effects.push(WorkspaceEffect::RoutePointerToContent);
                } else {
                    self.pointer_owner = InputOwner::None;
                    effects.push(WorkspaceEffect::DropPointerOutsideWorkspace);
                }
            }
            WorkspaceEvent::KeyboardFocusRequested { target } => match target {
                SurfaceTarget::TrustedChrome => {
                    if self.ime_active {
                        self.ime_active = false;
                        effects.push(WorkspaceEffect::EndContentIme);
                    }
                    self.keyboard_owner = InputOwner::TrustedChrome;
                    effects.push(WorkspaceEffect::RouteKeyboardToTrustedChrome);
                }
                SurfaceTarget::Content => {
                    if !self.content.has_live_surface()
                        || matches!(self.content, ContentLifecycle::Crashed { .. })
                    {
                        return Err(CompositionError::ContentNotAttached);
                    }
                    self.keyboard_owner = InputOwner::Content;
                    effects.push(WorkspaceEffect::RouteKeyboardToContent);
                }
            },
            WorkspaceEvent::ImeStarted => {
                if self.ime_active {
                    return Err(CompositionError::ImeAlreadyActive);
                }
                if self.keyboard_owner != InputOwner::Content {
                    return Err(CompositionError::ImeRequiresContentKeyboardFocus);
                }
                self.ime_active = true;
                effects.push(WorkspaceEffect::BeginContentIme);
            }
            WorkspaceEvent::ImeEnded => {
                if !self.ime_active {
                    return Err(CompositionError::ImeNotActive);
                }
                self.ime_active = false;
                effects.push(WorkspaceEffect::EndContentIme);
            }
            WorkspaceEvent::ExistingContentNavigationRequested => {
                if !self.content.has_live_surface() {
                    return Err(CompositionError::ContentNotAttached);
                }
                effects.push(WorkspaceEffect::NavigateExistingContent);
            }
            WorkspaceEvent::PopupRequested => {
                self.rejected_popup_count = self
                    .rejected_popup_count
                    .checked_add(1)
                    .ok_or(CompositionError::PopupCounterExhausted)?;
                effects.push(WorkspaceEffect::DenyPopup);
            }
            WorkspaceEvent::ContentCrashed { surface_id } => {
                self.require_surface(surface_id)?;
                if matches!(self.content, ContentLifecycle::Detached) {
                    return Err(CompositionError::ContentNotAttached);
                }
                let crash_generation = match self.content {
                    ContentLifecycle::Crashed { crash_generation } => crash_generation,
                    _ => self.event_sequence,
                };
                self.content = ContentLifecycle::Crashed { crash_generation };
                self.keyboard_owner = InputOwner::TrustedChrome;
                if self.pointer_owner == InputOwner::Content {
                    self.pointer_owner = InputOwner::None;
                }
                if self.ime_active {
                    self.ime_active = false;
                    effects.push(WorkspaceEffect::EndContentIme);
                }
                self.advance_frame()?;
                effects.push(WorkspaceEffect::ShowCrashPlaceholder);
                effects.push(WorkspaceEffect::Compose(self.composition_frame()));
            }
            WorkspaceEvent::BeginContentRecovery {
                requested_session_generation,
            } => {
                if requested_session_generation == 0 {
                    return Err(CompositionError::InvalidSessionGeneration);
                }
                if !matches!(self.content, ContentLifecycle::Crashed { .. }) {
                    return Err(CompositionError::RecoveryRequiresCrash);
                }
                self.content = ContentLifecycle::Recovering {
                    requested_session_generation,
                };
                self.advance_frame()?;
                effects.push(WorkspaceEffect::AwaitContentFrame);
                effects.push(WorkspaceEffect::Compose(self.composition_frame()));
            }
            WorkspaceEvent::ContentRecovered {
                surface_id,
                session_generation,
            } => {
                self.require_surface(surface_id)?;
                if session_generation == 0 {
                    return Err(CompositionError::InvalidSessionGeneration);
                }
                match self.content {
                    ContentLifecycle::Recovering {
                        requested_session_generation,
                    } if requested_session_generation == session_generation => {}
                    ContentLifecycle::Recovering { .. } => {
                        return Err(CompositionError::InvalidSessionGeneration);
                    }
                    _ => return Err(CompositionError::RecoveryRequiresCrash),
                }
                self.content = ContentLifecycle::Attached;
                self.advance_frame()?;
                effects.push(WorkspaceEffect::AwaitContentFrame);
                effects.push(WorkspaceEffect::Compose(self.composition_frame()));
            }
            WorkspaceEvent::Resize {
                viewport,
                chrome_height,
            } => {
                self.config =
                    WorkspaceConfig::new(viewport, chrome_height, self.config.content_surface_id)?;
                self.advance_frame()?;
                effects.push(WorkspaceEffect::Compose(self.composition_frame()));
            }
        }
        Ok(effects)
    }

    fn require_surface(&self, actual: ContentSurfaceId) -> Result<(), CompositionError> {
        if actual == self.config.content_surface_id {
            Ok(())
        } else {
            Err(CompositionError::WrongContentSurface {
                expected: self.config.content_surface_id,
                actual,
            })
        }
    }

    fn advance_frame(&mut self) -> Result<(), CompositionError> {
        self.frame_revision = self
            .frame_revision
            .checked_add(1)
            .ok_or(CompositionError::FrameRevisionExhausted)?;
        Ok(())
    }

    fn assert_invariants(&self) -> Result<(), CompositionError> {
        if TRUSTED_CHROME_ORIGIN != "https://shell.system.hepta.invalid" {
            return Err(CompositionError::InvariantViolation(
                "trusted chrome origin changed",
            ));
        }
        let chrome = self.config.trusted_chrome_rect();
        let content = self.config.content_rect();
        if chrome.x != 0 || chrome.y != 0 || chrome.width != self.config.viewport.width {
            return Err(CompositionError::InvariantViolation(
                "trusted chrome is not anchored to the workspace top edge",
            ));
        }
        if content.x != 0
            || content.y != i32::try_from(self.config.chrome_height).unwrap_or(i32::MAX)
            || content.width != self.config.viewport.width
            || content.height + chrome.height != self.config.viewport.height
        {
            return Err(CompositionError::InvariantViolation(
                "content surface does not occupy the remaining workspace",
            ));
        }
        if self.ime_active && self.keyboard_owner != InputOwner::Content {
            return Err(CompositionError::InvariantViolation(
                "IME is active without content keyboard ownership",
            ));
        }
        if matches!(self.content, ContentLifecycle::Crashed { .. })
            && self.keyboard_owner == InputOwner::Content
        {
            return Err(CompositionError::InvariantViolation(
                "crashed content retains keyboard ownership",
            ));
        }
        Ok(())
    }
}
