//! Pure Rust acceptance model for the A10 desktop boundaries.
//!
//! The production shell/session is deliberately not pulled into this crate:
//! these invariants must remain runnable on a headless host and must not be
//! confused with a Wayland, GPU, or target-kernel pass.  Integration tests use
//! the model as an oracle for lifecycle, focus, notification, and task-state
//! contracts that the executable UI must preserve.

use std::collections::{BTreeMap, BTreeSet, VecDeque};

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum TaskState {
    Pending,
    Running,
    Completed,
    Failed,
    Partial,
    Unknown,
    CancelRequested,
    Cancelled,
}

impl TaskState {
    pub fn is_terminal(self) -> bool {
        matches!(self, Self::Completed | Self::Failed | Self::Cancelled)
    }

    pub fn transition_allowed(self, next: Self) -> bool {
        use TaskState::*;
        matches!(
            (self, next),
            (Pending, Running | Failed)
                | (Running, Completed | Failed | Partial | Unknown | CancelRequested)
                | (Partial, Completed | Failed | Unknown | CancelRequested)
                | (Unknown, Completed | Failed | Partial | CancelRequested)
                // A kill request can race with an observed natural exit.
                | (CancelRequested, Cancelled | Completed | Failed | Unknown)
        )
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Task {
    pub id: u64,
    pub state: TaskState,
    pub observed_detail: String,
}

impl Task {
    pub fn new(id: u64) -> Self {
        Self {
            id,
            state: TaskState::Pending,
            observed_detail: "waiting for process observation".into(),
        }
    }

    /// A state change is valid only when it came from an independent owner
    /// observation.  Assistant text is never represented by this API.
    pub fn observe(&mut self, next: TaskState, detail: impl Into<String>) -> bool {
        if !self.state.transition_allowed(next) {
            return false;
        }
        self.state = next;
        self.observed_detail = detail.into();
        true
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FocusOwner {
    None,
    ShellComposer,
    App(u64),
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FocusController {
    owner: FocusOwner,
    preedit: String,
    shell_text: String,
    app_text: BTreeMap<u64, String>,
}

impl Default for FocusController {
    fn default() -> Self {
        Self {
            owner: FocusOwner::None,
            preedit: String::new(),
            shell_text: String::new(),
            app_text: BTreeMap::new(),
        }
    }
}

impl FocusController {
    pub fn owner(&self) -> FocusOwner {
        self.owner
    }

    pub fn preedit(&self) -> &str {
        &self.preedit
    }

    pub fn shell_text(&self) -> &str {
        &self.shell_text
    }

    pub fn app_text(&self, id: u64) -> &str {
        self.app_text.get(&id).map(String::as_str).unwrap_or("")
    }

    /// Changing focus abandons an uncommitted composition.  It must never
    /// leak the composition into the next window or commit it twice.
    pub fn focus(&mut self, owner: FocusOwner) {
        if owner != self.owner {
            self.preedit.clear();
        }
        self.owner = owner;
    }

    pub fn update_preedit(&mut self, text: impl Into<String>) -> bool {
        if self.owner == FocusOwner::None {
            return false;
        }
        self.preedit = text.into();
        true
    }

    /// `text` is the committed IME result.  The preedit is cleared exactly
    /// once, so a later focus or redraw cannot duplicate the committed text.
    pub fn commit(&mut self, text: &str) -> bool {
        match self.owner {
            FocusOwner::None => false,
            FocusOwner::ShellComposer => {
                self.shell_text.push_str(text);
                self.preedit.clear();
                true
            }
            FocusOwner::App(id) => {
                self.app_text.entry(id).or_default().push_str(text);
                self.preedit.clear();
                true
            }
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct NotificationId(pub u64);

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Notification {
    pub id: NotificationId,
    pub task_id: Option<u64>,
    pub message: String,
}

#[derive(Clone, Debug)]
pub struct NotificationCenter {
    capacity: usize,
    seen: BTreeSet<NotificationId>,
    items: VecDeque<Notification>,
}

impl NotificationCenter {
    pub fn new(capacity: usize) -> Self {
        assert!(capacity > 0, "a notification center needs bounded storage");
        Self {
            capacity,
            seen: BTreeSet::new(),
            items: VecDeque::new(),
        }
    }

    /// Returns false for a duplicate event.  Replayed snapshots therefore do
    /// not create duplicate toasts; storage remains bounded by `capacity`.
    pub fn push(&mut self, item: Notification) -> bool {
        if !self.seen.insert(item.id) {
            return false;
        }
        if self.items.len() == self.capacity {
            if let Some(expired) = self.items.pop_front() {
                self.seen.remove(&expired.id);
            }
        }
        self.items.push_back(item);
        true
    }

    pub fn items(&self) -> impl Iterator<Item = &Notification> {
        self.items.iter()
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ShellState {
    Running,
    Crashed,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CompositorState {
    Running,
    Crashed,
    GpuReset,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum WindowState {
    Attached { compositor_generation: u64 },
    Disconnected,
    Closed,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct AppWindow {
    pub id: u64,
    pub workspace: u8,
    pub state: WindowState,
}

/// Model the process boundary explicitly: shell restart is independent from
/// compositor and app lifetime; compositor recovery never claims a client was
/// losslessly reattached without an explicit client handshake.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DesktopBoundary {
    pub shell: ShellState,
    pub compositor: CompositorState,
    pub shell_generation: u64,
    pub compositor_generation: u64,
    pub apps: BTreeMap<u64, AppWindow>,
}

impl Default for DesktopBoundary {
    fn default() -> Self {
        Self {
            shell: ShellState::Running,
            compositor: CompositorState::Running,
            shell_generation: 1,
            compositor_generation: 1,
            apps: BTreeMap::new(),
        }
    }
}

impl DesktopBoundary {
    pub fn launch_app(&mut self, id: u64, workspace: u8) -> bool {
        if self.compositor != CompositorState::Running || self.apps.contains_key(&id) {
            return false;
        }
        self.apps.insert(
            id,
            AppWindow {
                id,
                workspace,
                state: WindowState::Attached {
                    compositor_generation: self.compositor_generation,
                },
            },
        );
        true
    }

    pub fn restart_shell(&mut self) {
        self.shell_generation += 1;
        self.shell = ShellState::Running;
    }

    pub fn crash_shell(&mut self) {
        self.shell = ShellState::Crashed;
    }

    pub fn crash_compositor(&mut self) {
        self.compositor = CompositorState::Crashed;
        for app in self.apps.values_mut() {
            if !matches!(app.state, WindowState::Closed) {
                app.state = WindowState::Disconnected;
            }
        }
    }

    pub fn restart_compositor(&mut self) {
        self.compositor_generation += 1;
        self.compositor = CompositorState::Running;
        // Existing clients remain disconnected until they perform their own
        // reconnect handshake.
    }

    pub fn gpu_reset(&mut self) {
        self.compositor = CompositorState::GpuReset;
        for app in self.apps.values_mut() {
            if !matches!(app.state, WindowState::Closed) {
                app.state = WindowState::Disconnected;
            }
        }
    }

    pub fn recover_gpu(&mut self) {
        if self.compositor == CompositorState::GpuReset {
            self.compositor_generation += 1;
            self.compositor = CompositorState::Running;
        }
    }

    pub fn reconnect_app(&mut self, id: u64) -> bool {
        if self.compositor != CompositorState::Running {
            return false;
        }
        let Some(app) = self.apps.get_mut(&id) else {
            return false;
        };
        if app.state == WindowState::Closed {
            return false;
        }
        app.state = WindowState::Attached {
            compositor_generation: self.compositor_generation,
        };
        true
    }

    pub fn close_app(&mut self, id: u64) -> bool {
        let Some(app) = self.apps.get_mut(&id) else {
            return false;
        };
        if app.state == WindowState::Closed {
            return false;
        }
        app.state = WindowState::Closed;
        true
    }
}
