//! Rust AI-workspace shell for a Linux/Wayland host, not for the target kernel.
mod conversation;
mod hepta_panel;
#[path = "../../host_fonts.rs"]
mod host_fonts;
mod local_drafts;

use conversation::{DraftBook, HostObservation, WorkspaceTab};
use eframe::egui::{self, Color32, RichText};
use std::cmp::Reverse;
use std::collections::VecDeque;
use std::io::{self, Write};
use std::sync::mpsc::{self, Receiver, SyncSender, TryRecvError};
use std::time::{Duration, Instant};
#[cfg(test)]
use trill_ui_core::conversation::{LocalDraft, MAX_DRAFT_BYTES, MAX_LOCAL_DRAFTS};
use trill_ui_core::hepta::HeptaProjection;
use trill_ui_core::{
    request, AppKind, HostResources, HostWaylandObservation, HostWindowObservation, Request,
    Response, TaskRecord, TaskState, WaylandSocketStatus, Workspace,
};

#[derive(Clone, Copy, PartialEq, Eq)]
enum Page {
    Conversation,
    Hepta,
    Tasks,
    Apps,
    Workspaces,
    Console,
    Settings,
}

impl Page {
    fn name(self) -> &'static str {
        match self {
            Self::Conversation => "Workspace / Chat",
            Self::Hepta => "Hepta / Runtime",
            Self::Tasks => "Tasks",
            Self::Apps => "Applications",
            Self::Workspaces => "Workspaces",
            Self::Console => "Console / Logs",
            Self::Settings => "Settings",
        }
    }
}

#[derive(Clone, Copy)]
struct StartupOptions {
    page: Page,
    hepta_layout_probe: bool,
}

fn parse_startup_options(
    args: impl IntoIterator<Item = String>,
) -> Result<StartupOptions, &'static str> {
    let mut options = StartupOptions {
        page: Page::Conversation,
        hepta_layout_probe: false,
    };
    let mut page_selected = false;
    let mut args = args.into_iter();
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--page" if !page_selected => {
                options.page = match args.next().as_deref() {
                    Some("conversation") => Page::Conversation,
                    Some("hepta") => Page::Hepta,
                    Some("tasks") => Page::Tasks,
                    Some("apps") => Page::Apps,
                    Some("workspaces") => Page::Workspaces,
                    Some("console") => Page::Console,
                    Some("settings") => Page::Settings,
                    _ => return Err("--page requires a known page name"),
                };
                page_selected = true;
            }
            "--hepta-layout-probe" if !options.hepta_layout_probe => {
                options.hepta_layout_probe = true;
            }
            _ => return Err("unknown or duplicate Shell option"),
        }
    }
    if options.hepta_layout_probe && options.page != Page::Hepta {
        return Err("--hepta-layout-probe requires --page hepta");
    }
    Ok(options)
}

/// User actions and passive status polling are intentionally independent.
/// A slow/disconnected session must not fill the user-action queue with polls.
struct Bridge {
    actions: SyncSender<Request>,
    polls: SyncSender<()>,
    rx: Receiver<(bool, Result<Response, String>)>,
}
impl Bridge {
    fn new() -> Self {
        Self::with_transport(|message| request(message).map_err(|err| err.to_string()))
    }

    fn with_transport(
        transport: impl Fn(&Request) -> Result<Response, String> + Send + 'static,
    ) -> Self {
        let (actions, incoming_actions) = mpsc::sync_channel::<Request>(8);
        let (polls, incoming_polls) = mpsc::sync_channel::<()>(1);
        let (outgoing, rx) = mpsc::sync_channel(16);
        // The worker, not egui, waits for the Unix socket. After each IPC,
        // prioritized actions are handled before the coalesced next poll.
        std::thread::spawn(move || loop {
            let (message, is_action) = match incoming_actions.try_recv() {
                Ok(action) => (action, true),
                Err(TryRecvError::Disconnected) => break,
                Err(TryRecvError::Empty) => match incoming_polls.try_recv() {
                    Ok(()) => (Request::Snapshot, false),
                    Err(TryRecvError::Disconnected) => break,
                    Err(TryRecvError::Empty) => {
                        match incoming_actions.recv_timeout(Duration::from_millis(40)) {
                            Ok(action) => (action, true),
                            Err(mpsc::RecvTimeoutError::Disconnected) => break,
                            Err(mpsc::RecvTimeoutError::Timeout) => continue,
                        }
                    }
                },
            };
            let result = transport(&message);
            if outgoing.send((is_action, result)).is_err() {
                break;
            }
        });
        Self { actions, polls, rx }
    }

    fn send_action(&self, request: Request) -> bool {
        self.actions.try_send(request).is_ok()
    }

    fn poll(&self) {
        // A pending snapshot is sufficient: never accumulate stale samples.
        let _ = self.polls.try_send(());
    }
}

/// An independently emitted Shell-side egui layout marker. This proves only
/// that the Rust widget tree completed an update, not compositor presentation.
const SHELL_FIRST_LAYOUT_MARKER: &[u8] = b"TRILL_SHELL_FIRST_FRAME_V1\n";

fn emit_shell_first_layout<W: Write>(emitted: &mut bool, output: &mut W) -> io::Result<()> {
    if *emitted {
        return Ok(());
    }
    // A broken stdout pipe must not turn a still-usable desktop into a
    // recurring I/O retry loop or a fatal process exit.
    *emitted = true;
    output.write_all(SHELL_FIRST_LAYOUT_MARKER)?;
    output.flush()
}

/// Offer only an explicit *new* host process, never silent reattachment.
/// UNKNOWN, PARTIAL, CANCEL REQUESTED and PENDING are nonterminal, but none
/// proves a still-running previously rendered client. Refuse to duplicate an
/// uncertain or cancelling process from this recovery shortcut.
fn can_offer_fresh_window(
    task: &TaskRecord,
    display: Option<&HostWaylandObservation>,
    connected: bool,
) -> bool {
    connected
        && task.state == TaskState::Running
        && task.pid.is_some_and(|pid| pid != 0)
        && task.ui_first_frame_unix_ms.is_some()
        && display.is_some_and(|sample| {
            task.wayland_socket_epoch_at_launch
                .is_some_and(|launch_epoch| {
                    sample.socket_observation_epoch > launch_epoch
                        && task.host_window_observation(sample)
                            == HostWindowObservation::SocketChanged
                })
        })
}

/// A plain process observation, NOT Hepta operation success or a security log.
/// Stable formatting keeps the console useful when the session is offline.
fn observed_host_line(task: &TaskRecord) -> String {
    let first_layout = task
        .ui_first_frame_unix_ms
        .map_or("UNOBSERVED".to_owned(), |time| time.to_string());
    let launch_socket_epoch = task
        .wayland_socket_epoch_at_launch
        .map_or("UNOBSERVED".to_owned(), |epoch| epoch.to_string());
    format!(
        "{} | {} | #{} {} | HOST_PROCESS={} | PID={} | FIRST_EGUI_LAYOUT={} | WAYLAND_AT_LAUNCH={} | {}",
        task.updated_unix_ms,
        task.workspace.name(),
        task.id,
        task.app.name(),
        task.state.label(),
        task.pid.map_or("-".into(), |pid| pid.to_string()),
        first_layout,
        launch_socket_epoch,
        task.detail,
    )
}

struct Desktop {
    page: Page,
    workspace: Workspace,
    drafts: DraftBook,
    host_observation: HostObservation,
    tasks: Vec<TaskRecord>,
    selected: Option<u64>,
    resources: Option<HostResources>,
    hepta: HeptaProjection,
    hepta_last_snapshot: Option<Instant>,
    connected: bool,
    session_instance: Option<String>,
    session_error: String,
    last_poll: Instant,
    bridge: Bridge,
    zoom: f32,
    show_notifications: bool,
    notices: VecDeque<String>,
    first_frame_emitted: bool,
    hepta_layout_probe: hepta_panel::LayoutProbe,
}

impl Desktop {
    fn new(ctx: &egui::Context, options: StartupOptions) -> Self {
        let mut visuals = egui::Visuals::dark();
        visuals.panel_fill = Color32::from_rgb(13, 20, 30);
        visuals.window_fill = Color32::from_rgb(18, 28, 40);
        visuals.faint_bg_color = Color32::from_rgb(21, 34, 47);
        visuals.selection.bg_fill = Color32::from_rgb(25, 91, 110);
        visuals.widgets.active.bg_fill = Color32::from_rgb(27, 102, 123);
        ctx.set_visuals(visuals);
        host_fonts::install(ctx);
        let bridge = Bridge::new();
        bridge.poll();
        let mut drafts = DraftBook::default();
        let page = match options.page {
            Page::Tasks | Page::Workspaces => Page::Conversation,
            Page::Console => {
                drafts.set_tab(Workspace::Personal, WorkspaceTab::Console);
                Page::Conversation
            }
            page => page,
        };
        Self {
            page,
            workspace: Workspace::Personal,
            drafts,
            host_observation: HostObservation::default(),
            tasks: Vec::new(),
            selected: None,
            resources: None,
            hepta: HeptaProjection::default(),
            hepta_last_snapshot: None,
            connected: false,
            session_instance: None,
            session_error: "Waiting for host session".into(),
            last_poll: Instant::now(),
            bridge,
            zoom: 1.0,
            show_notifications: false,
            notices: VecDeque::new(),
            first_frame_emitted: false,
            hepta_layout_probe: hepta_panel::LayoutProbe::new(options.hepta_layout_probe),
        }
    }

    fn notice(&mut self, message: impl Into<String>) {
        if self.notices.len() >= 30 {
            self.notices.pop_front();
        }
        self.notices.push_back(message.into());
    }

    /// A queue admission is NOT a successful OS operation. Report false
    /// immediately if the IPC worker has not accepted the action for delivery.
    fn submit(&mut self, request: Request) -> bool {
        if self.bridge.send_action(request) {
            true
        } else {
            self.notice(
                "IPC busy: command NOT queued. No operation was performed by this request.",
            );
            false
        }
    }

    fn launch_host_app(&mut self, workspace: Workspace, app: AppKind) -> bool {
        let Some(expected_instance) = self.session_instance.clone() else {
            self.notice("No session generation observed; no app launch attempted");
            return false;
        };
        self.submit(Request::Launch {
            workspace,
            app,
            expected_instance,
        })
    }

    fn store_task(&mut self, task: TaskRecord) {
        let old_state = self
            .tasks
            .iter()
            .find(|old| old.id == task.id)
            .map(|old| old.state);
        if old_state != Some(task.state) {
            self.notice(format!("Task #{}: {}", task.id, task.state.label()));
        }
        if let Some(old) = self.tasks.iter_mut().find(|old| old.id == task.id) {
            *old = task;
        } else {
            self.selected = Some(task.id);
            self.tasks.push(task);
        }
        self.tasks.sort_by_key(|task| Reverse(task.id));
    }

    fn receive(&mut self) {
        while let Ok((is_action, result)) = self.bridge.rx.try_recv() {
            match result {
                Ok(Response::Snapshot {
                    tasks,
                    resources,
                    session_instance,
                    hepta,
                }) => {
                    if self
                        .session_instance
                        .as_ref()
                        .is_some_and(|id| id != &session_instance)
                    {
                        self.tasks.clear();
                        self.selected = None;
                        self.notice("Host session restarted: previous child history cannot be reattached or trusted.");
                    }
                    if self.session_instance.as_deref() == Some(session_instance.as_str()) {
                        if let Some(previous) = &self.resources {
                            let old_epoch = previous.wayland.socket_observation_epoch;
                            let observed_epoch = resources.wayland.socket_observation_epoch;
                            if old_epoch != observed_epoch {
                                self.notice("Wayland socket identity changed or disappeared: older application surfaces NOT verified; process states remain separate.");
                            }
                        }
                    }
                    let received_at = Instant::now();
                    self.host_observation.observe(
                        &session_instance,
                        &tasks,
                        resources.sampled_unix_ms,
                        received_at,
                    );
                    self.session_instance = Some(session_instance);
                    self.connected = true;
                    self.session_error.clear();
                    self.resources = Some(resources);
                    self.hepta = hepta;
                    self.hepta_last_snapshot = Some(received_at);
                    for item in &tasks {
                        if let Some(previous) = self.tasks.iter().find(|old| old.id == item.id) {
                            if previous.state != item.state {
                                self.notice(format!("Task #{}: {}", item.id, item.state.label()));
                            }
                        }
                    }
                    self.tasks = tasks;
                }
                Ok(Response::Task {
                    task,
                    session_instance,
                }) => {
                    if self.session_instance.as_deref() == Some(session_instance.as_str()) {
                        self.connected = true;
                        self.store_task(task);
                    } else {
                        self.connected = false;
                        self.host_observation.disconnect(true);
                        self.hepta.mark_unavailable("host_session_changed");
                        self.notice("Task from changed/unobserved session ignored; refreshing before any status claim");
                        self.bridge.poll();
                    }
                }
                Ok(Response::Error {
                    message,
                    session_instance,
                }) => {
                    if self.session_instance.as_deref() != Some(session_instance.as_str()) {
                        self.connected = false;
                        self.host_observation.disconnect(true);
                        self.hepta.mark_unavailable("host_session_changed");
                        self.notice("Session generation changed; refreshing before new commands");
                        self.bridge.poll();
                    }
                    self.notice(format!("Session rejected operation: {message}"));
                }
                Err(err) => {
                    if self.connected || is_action {
                        self.notice(format!("Session unavailable: {err}; no success inferred"));
                    }
                    self.connected = false;
                    self.host_observation.disconnect(false);
                    self.resources = None;
                    self.hepta.mark_unavailable("host_session_unavailable");
                    self.session_error = err;
                }
            }
        }
    }

    /// Consume queued host responses and refresh state before any page draws.
    /// The clock is sampled after receive, so an arriving response does not
    /// get a local timestamp later than the frame's freshness evaluation.
    fn receive_and_refresh_hepta(&mut self, clock: impl FnOnce() -> (Instant, u64)) {
        self.receive();
        let (now, now_unix_ms) = clock();
        self.host_observation.expire(now, now_unix_ms);
        hepta_panel::expire_unfresh_observation(
            &mut self.hepta,
            self.hepta_last_snapshot,
            now,
            now_unix_ms,
        );
    }

    /// Explicit user-requested export. Never autosave chat or feed Hepta.
    fn export_drafts(&mut self) {
        let drafts = match self.drafts.export() {
            Ok(drafts) => drafts,
            Err(message) => {
                self.notice(message);
                return;
            }
        };
        match local_drafts::state_dir().and_then(|dir| local_drafts::save_context_at(&dir, &drafts))
        {
            Ok(path) => self.notice(format!(
                "Exported {} local drafts to {} (PRIVATE PLAINTEXT; no Hepta upload)",
                drafts.len(),
                path.display()
            )),
            Err(error) => self.notice(format!(
                "Draft export FAILED; chat remains unchanged: {error}"
            )),
        }
    }

    fn restore_drafts(&mut self) {
        self.restore_drafts_from(local_drafts::state_dir());
    }

    fn restore_drafts_from(&mut self, directory: io::Result<std::path::PathBuf>) {
        // Import is deliberately non-destructive: never clear existing unsent
        // composer text or replace in-memory drafts without a fresh session.
        if !self.drafts.may_restore() {
            self.notice("Import refused: local chat/composer is not empty; nothing overwritten.");
            return;
        }
        match directory.and_then(|dir| local_drafts::load_context_at(&dir, self.workspace)) {
            Ok(drafts) => {
                let count = drafts.len();
                if let Err(message) = self.drafts.restore(drafts) {
                    self.notice(message);
                    return;
                }
                self.notice(format!(
                    "Restored {count} LOCAL ONLY drafts. Saved quotes are historical; only current Session snapshots can resolve them."
                ));
            }
            Err(error) => self.notice(format!(
                "Draft import FAILED; chat remains unchanged: {error}"
            )),
        }
    }

    fn task_list(&mut self, ui: &mut egui::Ui) {
        ui.heading("Tasks / Host applications");
        ui.colored_label(
            if self.host_observation.is_current() {
                success_color()
            } else {
                warning()
            },
            self.host_observation.label(),
        );
        ui.small("Quote an observed task in your draft, or inspect it in this workspace.");
        ui.separator();
        let visible: Vec<_> = self
            .host_observation
            .tasks
            .iter()
            .filter(|task| task.workspace == self.workspace)
            .cloned()
            .collect();
        if visible.is_empty() {
            ui.label("No host application tasks in this workspace.");
        }
        egui::ScrollArea::vertical().show(ui, |ui| {
            for task in visible {
                ui.horizontal(|ui| {
                    let clicked = ui
                        .selectable_label(
                            self.selected == Some(task.id),
                            format!("#{}  {}", task.id, task.app.name()),
                        )
                        .clicked();
                    if clicked {
                        self.selected = Some(task.id);
                    }
                    ui.label(RichText::new(format!("HOST {}", task.state.label())).color(
                        if self.host_observation.is_current() {
                            state_color(task.state)
                        } else {
                            warning()
                        },
                    ));
                });
                ui.small(format!("PID {:?} · {}", task.pid, task.execution_mode));
                ui.horizontal_wrapped(|ui| {
                    if ui
                        .add_enabled(
                            self.host_observation.is_current(),
                            egui::Button::new("Quote in draft"),
                        )
                        .clicked_by(egui::PointerButton::Primary)
                    {
                        self.quote_task(task.id);
                    }
                    if ui.small_button("Details").clicked() {
                        self.selected = Some(task.id);
                        self.show_workspace_tab(WorkspaceTab::Context);
                    }
                });
                let window_status = self
                    .resources
                    .as_ref()
                    .map_or("UNVERIFIED: NO CURRENT DISPLAY OBSERVATION", |sample| {
                        task.host_window_observation(&sample.wayland).label()
                    });
                if !task.state.is_terminal() {
                    ui.colored_label(warning(), window_status);
                }
                ui.separator();
            }
        });
    }

    fn apps(&mut self, ui: &mut egui::Ui) {
        ui.heading("App launcher / 应用");
        ui.label(format!("Target workspace: {}", self.workspace.name()));
        ui.colored_label(
            warning(),
            "Host-local processes; workspace labels do NOT isolate OS permissions.",
        );
        ui.separator();
        for kind in [AppKind::Notes, AppKind::Calculator] {
            ui.group(|ui| {
                ui.horizontal(|ui| {
                    ui.vertical(|ui| {
                        ui.heading(kind.name());
                        ui.label("Separate Rust GUI process · independent Wayland/X11 window");
                    });
                    if ui
                        .add_enabled(
                            self.host_observation.is_current(),
                            egui::Button::new("Launch"),
                        )
                        .clicked_by(egui::PointerButton::Primary)
                        && self.launch_host_app(self.workspace, kind)
                    {
                        self.show_workspace_tab(WorkspaceTab::Tasks);
                    }
                });
            });
            ui.add_space(12.0);
        }
        ui.label("Full shell and third-party Wayland apps: adapter not implemented.");
        ui.small("The read-only Console is a tab in each chat workspace.");
        if !self.connected {
            ui.colored_label(warning(), "Start trill-session to enable launching.");
        }
    }

    fn workspaces(&mut self, ui: &mut egui::Ui) {
        ui.heading("Workspaces / 工作区");
        ui.label("Switch task filters and launch context. This preview does not create security boundaries.");
        ui.separator();
        for workspace in Workspace::ALL {
            let count = self
                .tasks
                .iter()
                .filter(|task| task.workspace == workspace)
                .count();
            if ui
                .selectable_label(
                    self.workspace == workspace,
                    format!("{}    ·    {} host tasks", workspace.name(), count),
                )
                .clicked()
            {
                self.workspace = workspace;
                self.selected = None;
                self.show_workspace_tab(WorkspaceTab::Tasks);
            }
        }
        ui.add_space(12.0);
        ui.colored_label(warning(), "Separate Xwayland, per-workspace clipboard/drag-and-drop and portals are pending compositor integration.");
    }

    fn console(&self, ui: &mut egui::Ui) {
        ui.heading("Console / Host observations");
        ui.colored_label(
            warning(),
            "READ ONLY · Not an executable terminal, Hepta log or security audit ledger",
        );
        ui.label(format!("Workspace: {}", self.workspace.name()));
        if self.host_observation.is_current() {
            ui.label(format!(
                "Host session generation: {}",
                self.session_instance.as_deref().unwrap_or("not observed"),
            ));
        } else {
            ui.colored_label(warning(), self.host_observation.label());
        }
        ui.separator();
        ui.label(RichText::new("Observed host process lifecycle").strong());
        let observed: Vec<_> = self
            .host_observation
            .tasks
            .iter()
            .filter(|task| task.workspace == self.workspace)
            .map(observed_host_line)
            .collect();
        egui::ScrollArea::vertical()
            .max_height(340.0)
            .show(ui, |ui| {
                if observed.is_empty() {
                    ui.monospace("No host process events observed for this workspace");
                }
                for line in observed {
                    ui.monospace(line);
                    ui.separator();
                }
            });
        ui.separator();
        ui.label(RichText::new("Local Shell notices (latest 30, volatile)").strong());
        egui::ScrollArea::vertical()
            .max_height(240.0)
            .show(ui, |ui| {
                if self.notices.is_empty() {
                    ui.monospace("No local notices");
                }
                for notice in self.notices.iter().rev() {
                    ui.monospace(notice);
                    ui.separator();
                }
            });
        ui.small("Process exit 0 ≠ Hepta effect completion. No privileged shell, screen capture or global input access.");
    }

    fn settings(&mut self, ui: &mut egui::Ui, ctx: &egui::Context) {
        ui.heading("Settings / 设置");
        if ui
            .add(egui::Slider::new(&mut self.zoom, 0.8..=2.0).text("UI scale"))
            .changed()
        {
            ctx.set_zoom_factor(self.zoom);
        }
        ui.separator();
        ui.label("Platform: Linux host Rust/egui desktop prototype");
        ui.label("Graphics: eframe/glow; actual GPU/driver not attested");
        ui.label(host_fonts::status_label(ctx));
        ui.small("Set TRILL_UI_CJK_FONT to an absolute host font path; font coverage does not verify an input method.");
        hepta_panel::status(ui, &self.hepta);
        ui.label("Hepta objective submission: unavailable; local drafts only");
        ui.label("Native HOS2 resource revision: unavailable");
        ui.label("Compositor: external Wayland/X11 host, not bundled");
        ui.separator();
        ui.heading("Permission access");
        for item in [
            "File picker / portal",
            "Clipboard isolation",
            "Drag & drop",
            "Screenshot",
            "Screen share",
            "Microphone",
            "Camera",
            "System notification grant",
        ] {
            ui.label(format!("{item}: not implemented (no grant)"));
        }
        ui.label("No global keyboard/screen/microphone stream is sent to Hepta.");
    }

    fn inspector(&mut self, ui: &mut egui::Ui) {
        ui.heading("Context / Inspector");
        if self.host_observation.is_current() {
            ui.colored_label(success_color(), self.host_observation.label());
        } else {
            ui.colored_label(warning(), self.host_observation.label());
            ui.small(&self.session_error);
        }
        hepta_panel::status(ui, &self.hepta);
        ui.small("Objective submission: unavailable");
        ui.label("HOS2: NOT OBSERVED");
        ui.separator();
        ui.label(RichText::new("Host resource sample").strong());
        if let Some(sample) = &self.resources {
            ui.small(&sample.source);
            if let (Some(total), Some(available)) = (sample.mem_total_kib, sample.mem_available_kib)
            {
                ui.label(format!(
                    "RAM available: {:.1} / {:.1} GiB",
                    available as f64 / 1_048_576.0,
                    total as f64 / 1_048_576.0
                ));
            } else {
                ui.label("Host RAM: unknown");
            }
            if let Some(load) = sample.load_average_1m {
                ui.label(format!("Host 1m load: {load:.2}"));
            } else {
                ui.label("Host load: unknown");
            }
            ui.small(format!("Observed unix ms: {}", sample.sampled_unix_ms));
            ui.separator();
            ui.label(RichText::new("Wayland socket (host-only)").strong());
            ui.label(format!(
                "{} · observation epoch {}",
                sample.wayland.status.label(),
                sample.wayland.socket_observation_epoch
            ));
            ui.small(format!(
                "Socket observed unix ms: {}",
                sample.wayland.sampled_unix_ms
            ));
            if sample.wayland.status != WaylandSocketStatus::SocketObserved {
                ui.colored_label(
                    warning(),
                    "No observed Wayland socket: RUNNING means host process only",
                );
            }
            ui.small("Socket presence does NOT prove protocol readiness, compositor health, window attachment or GPU presentation.");
        } else {
            ui.label("Resource snapshot unavailable");
        }
        ui.separator();
        if let Some(task) = self
            .host_observation
            .tasks
            .iter()
            .find(|task| Some(task.id) == self.selected)
            .cloned()
        {
            ui.label(RichText::new(format!("Task #{}", task.id)).strong());
            ui.label(task.app.name());
            ui.label(RichText::new(format!("HOST {}", task.state.label())).color(
                if self.host_observation.is_current() {
                    state_color(task.state)
                } else {
                    warning()
                },
            ));
            ui.small(format!("Workspace: {}", task.workspace.name()));
            ui.small(format!("Execution: {}", task.execution_mode));
            ui.small(format!(
                "PID: {:?}; exit code: {:?}",
                task.pid, task.exit_code
            ));
            ui.small(format!("HOS2 revision: {:?}", task.hos2_revision));
            ui.small(format!(
                "Wayland socket epoch at launch: {:?}",
                task.wayland_socket_epoch_at_launch
            ));
            if let Some(resources) = &self.resources {
                ui.colored_label(
                    warning(),
                    task.host_window_observation(&resources.wayland).label(),
                );
                ui.small("This is host socket metadata only; client surfaces and reattachment are not attested.");
            } else {
                ui.colored_label(warning(), "UNVERIFIED: NO CURRENT DISPLAY OBSERVATION");
            }
            if let Some(time) = task.ui_first_frame_unix_ms {
                ui.colored_label(
                    success_color(),
                    format!("Native egui first frame observed at {time} ms"),
                );
                ui.small("Does NOT prove Wayland compositor mapping or rendered GPU buffer");
            } else {
                ui.colored_label(warning(), "Native UI first frame: unobserved");
            }
            ui.small(format!("Last lifecycle change: {}", task.updated_unix_ms));
            if ui
                .add_enabled(
                    self.host_observation.is_current(),
                    egui::Button::new("Quote selected task in draft"),
                )
                .clicked_by(egui::PointerButton::Primary)
            {
                self.quote_task(task.id);
            }
            ui.separator();
            ui.label(&task.detail);
            if task.app != AppKind::Terminal
                && can_offer_fresh_window(
                    &task,
                    self.resources.as_ref().map(|sample| &sample.wayland),
                    self.host_observation.is_current(),
                )
            {
                ui.colored_label(
                    warning(),
                    "Old client window unverified after compositor restart. A fresh process cannot restore unsaved app state.",
                );
                if ui
                    .button("Launch NEW window (not reattach)")
                    .clicked_by(egui::PointerButton::Primary)
                    && self.launch_host_app(task.workspace, task.app)
                {
                    self.notice(format!(
                        "Queued NEW {} process; old task #{} is neither reattached nor cancelled",
                        task.app.name(),
                        task.id
                    ));
                }
            }
            if self.host_observation.is_current()
                && !task.state.is_terminal()
                && ui
                    .button("Request termination")
                    .clicked_by(egui::PointerButton::Primary)
            {
                if let Some(expected_instance) = self.session_instance.clone() {
                    self.submit(Request::Cancel {
                        id: task.id,
                        expected_instance,
                    });
                } else {
                    self.notice("No authenticated session generation; cancellation not attempted");
                }
            }
            if !self.host_observation.is_current() {
                ui.small("Task controls require a fresh complete Session snapshot.");
            }
        } else {
            ui.label("Select a task to inspect.");
        }
        ui.separator();
        if ui
            .button(format!("Notifications ({})", self.notices.len()))
            .clicked()
        {
            self.show_notifications = !self.show_notifications;
        }
        if self.show_notifications {
            egui::ScrollArea::vertical()
                .max_height(260.0)
                .show(ui, |ui| {
                    for notice in self.notices.iter().rev().take(12) {
                        ui.small(notice);
                        ui.separator();
                    }
                });
        }
    }
}

impl eframe::App for Desktop {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.receive_and_refresh_hepta(|| (Instant::now(), trill_ui_core::unix_ms()));
        if self.last_poll.elapsed() >= Duration::from_millis(800) {
            self.last_poll = Instant::now();
            self.bridge.poll();
        }
        egui::TopBottomPanel::top("top").show(ctx, |ui| {
            ui.horizontal(|ui| {
                ui.label(RichText::new("TRILLIONNIUM").size(22.0).strong());
                ui.separator();
                ui.label("AI-native workspace · Linux host prototype");
                ui.separator();
                ui.colored_label(
                    if self.host_observation.is_current() {
                        success_color()
                    } else {
                        warning()
                    },
                    self.host_observation.label(),
                );
            });
        });
        egui::SidePanel::left("nav")
            .default_width(190.0)
            .resizable(false)
            .show(ctx, |ui| {
                ui.heading("Workspace");
                for workspace in Workspace::ALL {
                    if ui
                        .selectable_label(self.workspace == workspace, workspace.name())
                        .clicked()
                    {
                        self.workspace = workspace;
                        self.selected = None;
                        self.page = Page::Conversation;
                    }
                }
                ui.separator();
                for page in [Page::Conversation, Page::Apps, Page::Settings] {
                    if ui
                        .selectable_label(self.page == page, page.name())
                        .clicked()
                    {
                        self.page = page;
                    }
                }
                ui.separator();
                ui.small("Tasks, context and Console stay in your chat workspace.");
                ui.small("Linux host · Rust native UI");
            });
        if self.page != Page::Conversation {
            egui::SidePanel::right("inspector")
                .default_width(270.0)
                .resizable(true)
                .show(ctx, |ui| self.inspector(ui));
        }
        egui::CentralPanel::default().show(ctx, |ui| match self.page {
            Page::Conversation => self.conversation(ui),
            Page::Hepta => hepta_panel::runtime(ui, &self.hepta),
            Page::Tasks => self.task_list(ui),
            Page::Apps => self.apps(ui),
            Page::Workspaces => self.workspaces(ui),
            Page::Console => self.console(ui),
            Page::Settings => self.settings(ui, ctx),
        });
        if self.page == Page::Hepta && self.connected {
            // This optional diagnostic belongs to the completed Hepta page,
            // never the default Conversation first-layout marker. It reports
            // only bounded runtime metadata, not a presented compositor frame.
            let _ = self.hepta_layout_probe.emit_after_runtime_layout(
                &self.hepta,
                self.hepta_last_snapshot,
                Instant::now(),
                trill_ui_core::unix_ms(),
                &mut io::stdout(),
            );
        }
        // Report only after a full egui widget update, never merely because
        // the shell PID exists. Failure to write a diagnostic marker does not
        // stop independent session-owned clients.
        let _ = emit_shell_first_layout(&mut self.first_frame_emitted, &mut io::stdout());
        ctx.request_repaint_after(Duration::from_millis(100));
    }
}

fn warning() -> Color32 {
    Color32::from_rgb(248, 190, 100)
}
fn success_color() -> Color32 {
    Color32::from_rgb(112, 210, 170)
}
fn state_color(state: TaskState) -> Color32 {
    match state {
        TaskState::Completed => success_color(),
        TaskState::Running => Color32::from_rgb(112, 189, 245),
        TaskState::Failed => Color32::from_rgb(255, 112, 112),
        TaskState::Unknown | TaskState::Partial | TaskState::CancelRequested => warning(),
        _ => Color32::from_gray(185),
    }
}

fn main() -> eframe::Result {
    let startup = match parse_startup_options(std::env::args().skip(1)) {
        Ok(options) => options,
        Err(message) => {
            eprintln!("trill-shell: {message}");
            eprintln!("Usage: trill-shell [--page conversation|hepta|tasks|apps|workspaces|console|settings] [--hepta-layout-probe]");
            std::process::exit(2);
        }
    };
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default().with_inner_size([1360.0, 840.0]),
        ..Default::default()
    };
    eframe::run_native(
        "Trillionnium · AI workspace",
        options,
        Box::new(move |cc| Ok(Box::new(Desktop::new(&cc.egui_ctx, startup)))),
    )
}

#[cfg(test)]
mod observation_freshness_tests {
    use super::*;
    use trill_ui_core::hepta::{
        HeptaConnectionState, HeptaHealthObservation, HeptaRuntimeObservation,
    };

    type ResponseSender = SyncSender<(bool, Result<Response, String>)>;

    fn observed(sampled_unix_ms: u64) -> HeptaProjection {
        HeptaProjection {
            connection: HeptaConnectionState::Observed,
            last_attempt_unix_ms: Some(sampled_unix_ms),
            error_code: None,
            last_observation: Some(HeptaRuntimeObservation {
                sampled_unix_ms,
                agent_id: "11111111-1111-4111-8111-111111111111".into(),
                spawn_generation: 7,
                current_generation: 8,
                health: HeptaHealthObservation {
                    ready: true,
                    promotion_ready: true,
                    fenced: false,
                    lifecycle: "running".into(),
                    process_id: 42,
                },
                capabilities: Vec::new(),
                capabilities_truncated: false,
                events: Vec::new(),
                events_omitted_from_view: 0,
                next_cursor: 9,
                latest_cursor: 9,
                history_gap: true,
                source_changed: false,
            }),
        }
    }

    // Only the in-process response queue is synthetic here. The test consumes
    // it through Desktop's real receive and pre-draw state path; no Agentd,
    // compositor, device effect or physical display is claimed.
    pub(super) fn queued_desktop() -> (Desktop, ResponseSender) {
        let (actions, _incoming_actions) = mpsc::sync_channel(8);
        let (polls, _incoming_polls) = mpsc::sync_channel(1);
        let (outgoing, rx) = mpsc::sync_channel(16);
        let desktop = Desktop {
            page: Page::Hepta,
            workspace: Workspace::Personal,
            drafts: DraftBook::default(),
            host_observation: HostObservation::default(),
            tasks: Vec::new(),
            selected: None,
            resources: None,
            hepta: HeptaProjection::default(),
            hepta_last_snapshot: None,
            connected: false,
            session_instance: None,
            session_error: String::new(),
            last_poll: Instant::now(),
            bridge: Bridge { actions, polls, rx },
            zoom: 1.0,
            show_notifications: false,
            notices: VecDeque::new(),
            first_frame_emitted: false,
            hepta_layout_probe: hepta_panel::LayoutProbe::new(false),
        };
        (desktop, outgoing)
    }

    fn enqueue(sender: &ResponseSender, hepta: HeptaProjection) {
        sender
            .send((
                false,
                Ok(Response::Snapshot {
                    tasks: Vec::new(),
                    resources: HostResources {
                        sampled_unix_ms: 10_000,
                        mem_total_kib: None,
                        mem_available_kib: None,
                        load_average_1m: None,
                        source: "synthetic response queue only".into(),
                        wayland: HostWaylandObservation::default(),
                    },
                    session_instance: "held-session-instance".into(),
                    hepta,
                }),
            ))
            .unwrap();
    }

    fn actual_status_text(projection: &HeptaProjection) -> String {
        let ctx = egui::Context::default();
        let output = ctx.run(
            egui::RawInput {
                screen_rect: Some(egui::Rect::from_min_size(
                    egui::Pos2::ZERO,
                    egui::vec2(900.0, 600.0),
                )),
                ..Default::default()
            },
            |ctx| {
                egui::CentralPanel::default().show(ctx, |ui| hepta_panel::status(ui, projection));
            },
        );
        output
            .shapes
            .iter()
            .filter_map(|shape| match &shape.shape {
                egui::Shape::Text(text) => Some(text.galley.job.text.as_str()),
                _ => None,
            })
            .collect::<Vec<_>>()
            .join("\n")
    }

    #[test]
    fn a_queued_old_observed_response_is_visibly_stale_before_drawing() {
        let (mut desktop, outgoing) = queued_desktop();
        let old = observed(10_000);
        enqueue(&outgoing, old.clone());
        // No sleep: the old response has just arrived locally, while its
        // actual sample already exceeds the seven-second runtime deadline.
        desktop.receive_and_refresh_hepta(|| (Instant::now(), 18_001));
        let text = actual_status_text(&desktop.hepta);
        assert!(
            text.contains("STALE · CURRENT STATE UNKNOWN"),
            "actual status text was {text:?}"
        );
        assert!(!text.contains("OBSERVED · READ ONLY"));
        assert_eq!(desktop.hepta.last_observation, old.last_observation);
        assert_eq!(desktop.hepta.last_attempt_unix_ms, old.last_attempt_unix_ms);
        assert!(
            desktop.connected,
            "runtime staleness must not invent host IPC loss"
        );
        assert_eq!(
            desktop.session_instance.as_deref(),
            Some("held-session-instance")
        );
    }

    #[test]
    fn runtime_sample_and_local_receipt_both_have_exact_seven_second_limits() {
        for (now_unix_ms, expected) in [
            (17_000, HeptaConnectionState::Observed),
            (17_001, HeptaConnectionState::Stale),
        ] {
            let (mut desktop, outgoing) = queued_desktop();
            enqueue(&outgoing, observed(10_000));
            desktop.receive_and_refresh_hepta(|| (Instant::now(), now_unix_ms));
            assert_eq!(desktop.hepta.connection, expected, "sample age boundary");
        }
        for (age_ms, expected) in [
            (7000, HeptaConnectionState::Observed),
            (7001, HeptaConnectionState::Stale),
        ] {
            let (mut desktop, outgoing) = queued_desktop();
            enqueue(&outgoing, observed(10_000));
            desktop.receive();
            let now = Instant::now();
            desktop.hepta_last_snapshot = Some(now - Duration::from_millis(age_ms));
            desktop.receive_and_refresh_hepta(|| (now, 10_000));
            assert_eq!(
                desktop.hepta.connection, expected,
                "local receipt age boundary"
            );
        }
    }

    #[test]
    fn future_or_missing_observation_cannot_appear_current() {
        for view in [
            observed(18_002),
            HeptaProjection {
                connection: HeptaConnectionState::Observed,
                ..Default::default()
            },
        ] {
            let (mut desktop, outgoing) = queued_desktop();
            let historical = view.last_observation.clone();
            enqueue(&outgoing, view);
            desktop.receive_and_refresh_hepta(|| (Instant::now(), 18_001));
            assert_eq!(
                desktop.hepta.connection,
                if historical.is_some() {
                    HeptaConnectionState::Stale
                } else {
                    HeptaConnectionState::Unavailable
                }
            );
            assert_eq!(desktop.hepta.last_observation, historical);
        }
    }

    #[test]
    fn missing_or_future_local_receipt_is_unknown_without_rewriting_history() {
        for future in [false, true] {
            let (mut desktop, outgoing) = queued_desktop();
            let old = observed(10_000);
            enqueue(&outgoing, old.clone());
            desktop.receive();
            let now = Instant::now();
            desktop.hepta_last_snapshot = future.then_some(now + Duration::from_millis(1));
            desktop.receive_and_refresh_hepta(|| (now, 10_000));
            assert_eq!(desktop.hepta.connection, HeptaConnectionState::Stale);
            assert_eq!(desktop.hepta.last_observation, old.last_observation);
        }
    }

    #[test]
    fn a_later_fresh_session_snapshot_can_restore_the_visible_observation() {
        let (mut desktop, outgoing) = queued_desktop();
        enqueue(&outgoing, observed(10_000));
        desktop.receive_and_refresh_hepta(|| (Instant::now(), 18_001));
        assert_eq!(desktop.hepta.connection, HeptaConnectionState::Stale);
        let fresh = observed(18_001);
        enqueue(&outgoing, fresh.clone());
        desktop.receive_and_refresh_hepta(|| (Instant::now(), 18_001));
        assert_eq!(desktop.hepta, fresh);
        assert!(actual_status_text(&desktop.hepta).contains("OBSERVED · READ ONLY"));
    }

    #[test]
    fn existing_unknown_states_keep_their_original_diagnostic_and_history() {
        for connection in [
            HeptaConnectionState::NotObserved,
            HeptaConnectionState::NotConfigured,
            HeptaConnectionState::Connecting,
            HeptaConnectionState::Stale,
            HeptaConnectionState::Unavailable,
        ] {
            let (mut desktop, outgoing) = queued_desktop();
            let mut old = observed(10_000);
            old.connection = connection;
            old.error_code = Some("existing_owner_diagnostic".into());
            enqueue(&outgoing, old.clone());
            desktop.receive_and_refresh_hepta(|| (Instant::now(), 18_001));
            assert_eq!(desktop.hepta, old);
        }
    }
}

#[cfg(test)]
mod startup_tests {
    use super::*;

    #[test]
    fn runtime_probe_requires_explicit_hepta_navigation() {
        let parse = |args: &[&str]| parse_startup_options(args.iter().map(|arg| (*arg).to_owned()));
        let ordinary = parse(&[]).unwrap();
        assert!(ordinary.page == Page::Conversation);
        assert!(!ordinary.hepta_layout_probe);
        let runtime = parse(&["--page", "hepta", "--hepta-layout-probe"]).unwrap();
        assert!(runtime.page == Page::Hepta);
        assert!(runtime.hepta_layout_probe);
        assert!(parse(&["--hepta-layout-probe"]).is_err());
        assert!(parse(&["--page", "conversation", "--hepta-layout-probe"]).is_err());
        assert!(parse(&["--page", "unknown"]).is_err());
        assert!(parse(&["--page"]).is_err());
        assert!(parse(&["--page", "hepta", "--page", "conversation"]).is_err());
    }
}

/// A synthetic egui input test, not proof that Wayland IME candidates render.
#[cfg(test)]
mod input_tests {
    use super::*;

    fn draw(ctx: &egui::Context, first: &mut String, second: &mut String) {
        egui::CentralPanel::default().show(ctx, |ui| {
            ui.add(egui::TextEdit::singleline(first).id(egui::Id::new("first-input")));
            ui.add(egui::TextEdit::singleline(second).id(egui::Id::new("second-input")));
        });
    }

    fn raw(events: Vec<egui::Event>) -> egui::RawInput {
        egui::RawInput {
            screen_rect: Some(egui::Rect::from_min_size(
                egui::Pos2::ZERO,
                egui::vec2(900.0, 600.0),
            )),
            events,
            ..Default::default()
        }
    }

    #[test]
    fn synthetic_chinese_ime_commit_uses_focused_text_edit() {
        let ctx = egui::Context::default();
        let mut first = String::new();
        let mut second = String::new();

        let _ = ctx.run(raw(vec![]), |ctx| draw(ctx, &mut first, &mut second));
        ctx.memory_mut(|m| m.request_focus(egui::Id::new("first-input")));

        let _ = ctx.run(
            raw(vec![
                egui::Event::Ime(egui::ImeEvent::Enabled),
                egui::Event::Ime(egui::ImeEvent::Preedit("nihao".into())),
            ]),
            |ctx| draw(ctx, &mut first, &mut second),
        );
        let _ = ctx.run(
            raw(vec![
                egui::Event::Ime(egui::ImeEvent::Commit("你好".into())),
                egui::Event::Ime(egui::ImeEvent::Disabled),
            ]),
            |ctx| draw(ctx, &mut first, &mut second),
        );

        assert_eq!(
            first, "你好",
            "preedit must be replaced by confirmed candidate"
        );
        assert_eq!(second, "", "unfocused field must not receive candidate");

        ctx.memory_mut(|m| m.request_focus(egui::Id::new("second-input")));
        let _ = ctx.run(raw(vec![egui::Event::Text("中文".into())]), |ctx| {
            draw(ctx, &mut first, &mut second)
        });
        assert_eq!(first, "你好");
        assert_eq!(second, "中文");
    }
}

#[cfg(test)]
mod bridge_tests {
    use super::*;
    use std::sync::{Arc, Mutex};

    #[test]
    fn full_action_queue_rejects_new_command_instead_of_claiming_it_was_sent() {
        let (entered_tx, entered_rx) = mpsc::channel();
        let (release_tx, release_rx) = mpsc::channel();
        let bridge = Bridge::with_transport(move |_command| {
            entered_tx.send(()).unwrap();
            release_rx.recv_timeout(Duration::from_secs(3)).unwrap();
            Ok(Response::Error {
                message: "synthetic IPC transport".into(),
                session_instance: "test".into(),
            })
        });
        let action = || Request::Cancel {
            id: 1,
            expected_instance: "test".into(),
        };
        // Hold the worker inside its first request. Its action queue has
        // EXACTLY eight waiting slots; a ninth may not be silently enqueued.
        assert!(bridge.send_action(action()));
        entered_rx.recv_timeout(Duration::from_secs(2)).unwrap();
        for _ in 0..8 {
            assert!(bridge.send_action(action()));
        }
        assert!(
            !bridge.send_action(action()),
            "queued != executed; refuse over-capacity action"
        );
        for _ in 0..9 {
            release_tx.send(()).unwrap();
        }
    }

    #[test]
    fn coalesced_poll_does_not_fill_action_queue_or_freeze_gui() {
        use std::sync::atomic::{AtomicBool, Ordering};
        let observed = Arc::new(Mutex::new(Vec::<String>::new()));
        let observed_in_worker = observed.clone();
        let (release_tx, release_rx) = mpsc::channel::<()>();
        let first_poll = AtomicBool::new(true);
        let bridge = Bridge::with_transport(move |req| {
            let label = match req {
                Request::Snapshot => "snapshot",
                Request::Launch { .. } => "launch",
                Request::Cancel { .. } => "cancel",
            };
            observed_in_worker.lock().unwrap().push(label.to_owned());
            if label == "snapshot" && first_poll.swap(false, Ordering::SeqCst) {
                // Hold the one in-flight snapshot so queue coalescing is
                // deterministic regardless of thread scheduling.
                release_rx.recv_timeout(Duration::from_secs(3)).unwrap();
            }
            Ok(Response::Error {
                message: "synthetic only; no host effect".into(),
                session_instance: "test-generation".into(),
            })
        });
        bridge.poll();
        let start = Instant::now();
        while !observed
            .lock()
            .unwrap()
            .iter()
            .any(|event| event == "snapshot")
        {
            assert!(
                start.elapsed() < Duration::from_secs(2),
                "snapshot worker never started"
            );
            std::thread::sleep(Duration::from_millis(2));
        }
        for _ in 0..500 {
            bridge.poll();
        }
        assert!(bridge.send_action(Request::Cancel {
            id: 41,
            expected_instance: "test-generation".into(),
        }));
        release_tx.send(()).unwrap();
        let start = Instant::now();
        while !observed
            .lock()
            .unwrap()
            .iter()
            .any(|event| event == "cancel")
        {
            assert!(
                start.elapsed() < Duration::from_secs(2),
                "action starved behind poll backlog"
            );
            std::thread::sleep(Duration::from_millis(2));
        }
        assert!(
            observed
                .lock()
                .unwrap()
                .iter()
                .filter(|event| event.as_str() == "snapshot")
                .count()
                <= 2,
            "passive polling must be coalesced"
        );
    }
}

#[cfg(test)]
mod workspace_context_tests {
    use super::*;
    use trill_ui_core::conversation::ContextRef;
    const A: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    const B: &str = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    type QueuedResponses = SyncSender<(bool, Result<Response, String>)>;

    fn setup() -> (Desktop, QueuedResponses, Receiver<Request>) {
        let (mut desktop, outgoing) = observation_freshness_tests::queued_desktop();
        let (actions, incoming) = mpsc::sync_channel(8);
        desktop.bridge.actions = actions;
        desktop.page = Page::Conversation;
        (desktop, outgoing, incoming)
    }

    fn snapshot(instance: &str, sample: u64, task: TaskRecord) -> Response {
        Response::Snapshot {
            tasks: vec![task],
            resources: HostResources {
                sampled_unix_ms: sample,
                mem_total_kib: None,
                mem_available_kib: None,
                load_average_1m: None,
                source: "response-queue regression fixture".into(),
                wayland: HostWaylandObservation::default(),
            },
            session_instance: instance.into(),
            hepta: HeptaProjection::default(),
        }
    }

    fn draw(
        desktop: &mut Desktop,
        ctx: &egui::Context,
        events: Vec<egui::Event>,
    ) -> egui::FullOutput {
        ctx.run(
            egui::RawInput {
                screen_rect: Some(egui::Rect::from_min_size(
                    egui::Pos2::ZERO,
                    egui::vec2(1500.0, 1100.0),
                )),
                events,
                ..Default::default()
            },
            |ctx| {
                egui::CentralPanel::default().show(ctx, |ui| desktop.conversation(ui));
            },
        )
    }

    fn visible_text(output: &egui::FullOutput) -> String {
        output
            .shapes
            .iter()
            .filter_map(|shape| match &shape.shape {
                egui::Shape::Text(text) => Some(text.galley.job.text.as_str()),
                _ => None,
            })
            .collect::<Vec<_>>()
            .join("\n")
    }

    fn click(desktop: &mut Desktop, ctx: &egui::Context, label: &str) {
        let output = draw(desktop, ctx, vec![]);
        let pos = output
            .shapes
            .iter()
            .find_map(|shape| match &shape.shape {
                egui::Shape::Text(text) if text.galley.job.text == label => {
                    Some(text.pos + text.galley.size() * 0.5)
                }
                _ => None,
            })
            .unwrap_or_else(|| panic!("button {label:?} missing: {}", visible_text(&output)));
        for pressed in [true, false] {
            draw(
                desktop,
                ctx,
                vec![
                    egui::Event::PointerMoved(pos),
                    egui::Event::PointerButton {
                        pos,
                        button: egui::PointerButton::Primary,
                        pressed,
                        modifiers: egui::Modifiers::NONE,
                    },
                ],
            );
        }
    }

    #[test]
    fn actual_workspace_clicks_quote_save_navigate_and_console_without_ipc() {
        let (mut desktop, outgoing, requests) = setup();
        let mut task = TaskRecord::new(1, Workspace::Personal, AppKind::Notes);
        task.state = TaskState::Running;
        task.pid = Some(42);
        task.updated_unix_ms = 1;
        outgoing
            .send((false, Ok(snapshot(A, 20_000, task.clone()))))
            .unwrap();
        desktop.receive_and_refresh_hepta(|| (Instant::now(), 20_000));
        desktop.drafts.composer_mut(Workspace::Personal).text = "检查这份笔记 📝".into();
        let ctx = egui::Context::default();
        click(&mut desktop, &ctx, "Quote in draft");
        assert_eq!(
            desktop.drafts.composer(Workspace::Personal).contexts.len(),
            1
        );
        click(&mut desktop, &ctx, "Save local draft");
        assert_eq!(desktop.drafts.drafts[0].text, "检查这份笔记 📝");
        assert_eq!(desktop.drafts.drafts[0].contexts.len(), 1);
        click(&mut desktop, &ctx, "Open task in workspace");
        assert_eq!(desktop.selected, Some(1));
        assert!(desktop.page == Page::Conversation);
        assert_eq!(
            desktop.drafts.tab(Workspace::Personal),
            WorkspaceTab::Context
        );
        click(&mut desktop, &ctx, "Console");
        let text = visible_text(&draw(&mut desktop, &ctx, vec![]));
        assert!(text.contains("Console / Host observations"));
        assert!(text.contains("HOST_PROCESS=RUNNING"));
        assert!(text.contains("You · local draft · not submitted"));
        assert!(
            matches!(requests.try_recv(), Err(TryRecvError::Empty)),
            "local interaction queued an operation"
        );
        outgoing
            .send((false, Ok(snapshot(B, 21_000, task))))
            .unwrap();
        desktop.receive_and_refresh_hepta(|| (Instant::now(), 21_000));
        assert_eq!(desktop.selected, None);
        let text = visible_text(&draw(&mut desktop, &ctx, vec![]));
        assert!(text.contains("Session changed; reference not rebound"));
        assert!(!text.contains("Open task in workspace"));
        let ContextRef::HostTask(reference) = &desktop.drafts.drafts[0].contexts[0] else {
            unreachable!()
        };
        assert_eq!(reference.key.session_instance, A);
        assert!(matches!(requests.try_recv(), Err(TryRecvError::Empty)));
    }

    #[test]
    fn delayed_snapshot_is_visibly_stale_and_action_reply_cannot_refresh_it() {
        let (mut desktop, outgoing, requests) = setup();
        let mut task = TaskRecord::new(1, Workspace::Personal, AppKind::Notes);
        task.state = TaskState::Running;
        task.updated_unix_ms = 1;
        outgoing
            .send((false, Ok(snapshot(A, 10_000, task.clone()))))
            .unwrap();
        desktop.receive_and_refresh_hepta(|| (Instant::now(), 18_001));
        assert!(!desktop.host_observation.is_current());
        let ctx = egui::Context::default();
        let text = visible_text(&draw(&mut desktop, &ctx, vec![]));
        assert!(text.contains("HOST TASKS · STALE · CURRENT STATE UNKNOWN"));
        task.state = TaskState::Completed;
        outgoing
            .send((
                true,
                Ok(Response::Task {
                    task: task.clone(),
                    session_instance: A.into(),
                }),
            ))
            .unwrap();
        desktop.receive_and_refresh_hepta(|| (Instant::now(), 18_002));
        assert!(!desktop.host_observation.is_current());
        assert_eq!(desktop.host_observation.tasks[0].state, TaskState::Running);
        assert_eq!(desktop.host_observation.sampled_unix_ms, Some(10_000));
        outgoing
            .send((false, Ok(snapshot(A, 20_000, task))))
            .unwrap();
        desktop.receive_and_refresh_hepta(|| (Instant::now(), 20_000));
        assert!(desktop.host_observation.is_current());
        assert_eq!(
            desktop.host_observation.tasks[0].state,
            TaskState::Completed
        );
        assert!(matches!(requests.try_recv(), Err(TryRecvError::Empty)));
    }

    #[test]
    #[cfg(target_os = "linux")]
    fn actual_import_refuses_fifo_without_writer_and_never_restores_legacy() {
        use std::ffi::CString;
        use std::fs::{self, DirBuilder, OpenOptions};
        use std::os::unix::ffi::OsStrExt;
        use std::os::unix::fs::{DirBuilderExt, OpenOptionsExt};
        use std::path::PathBuf;
        unsafe extern "C" {
            fn mkfifo(path: *const std::os::raw::c_char, mode: u32) -> i32;
        }
        struct PrivateDir(PathBuf);
        impl Drop for PrivateDir {
            fn drop(&mut self) {
                let _ = fs::remove_dir_all(&self.0);
            }
        }
        let dir = PrivateDir(std::env::temp_dir().join(format!(
            "trill-fifo-import-{}-{}",
            std::process::id(),
            trill_ui_core::unix_ms()
        )));
        DirBuilder::new().mode(0o700).create(&dir.0).unwrap();
        let legacy = dir.0.join("local-drafts-v1.json");
        let original = br#"{"version":1,"drafts":["legacy must not be silently restored"]}"#;
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&legacy)
            .unwrap()
            .write_all(original)
            .unwrap();
        let fifo = dir.0.join("local-context-drafts-v2.json");
        let name = CString::new(fifo.as_os_str().as_bytes()).unwrap();
        // Only this test-owned path is created, with no writer during the
        // complete acceptance window. No global environment is changed.
        assert_eq!(unsafe { mkfifo(name.as_ptr(), 0o600) }, 0);
        let (mut desktop, _outgoing, requests) = setup();
        let (finished, receive) = mpsc::sync_channel(1);
        let import_dir = dir.0.clone();
        let worker = std::thread::spawn(move || {
            desktop.restore_drafts_from(Ok(import_dir));
            finished.send(desktop).unwrap();
        });
        let first = receive.recv_timeout(Duration::from_secs(2));
        let refused_without_writer = first.is_ok();
        let mut cleanup_writer = None;
        let returned = match first {
            Ok(desktop) => desktop,
            Err(mpsc::RecvTimeoutError::Timeout) => {
                // RED-only cleanup: open our FIFO after the failed deadline
                // to release a blocked reader, then join it. This writer
                // cannot turn the no-writer acceptance predicate into PASS.
                cleanup_writer = Some(
                    OpenOptions::new()
                        .write(true)
                        .custom_flags(0o4000)
                        .open(&fifo)
                        .unwrap(),
                );
                receive
                    .recv_timeout(Duration::from_secs(2))
                    .expect("blocked FIFO reader did not finish after owned cleanup writer")
            }
            Err(error) => panic!("import worker ended without a result: {error}"),
        };
        worker.join().unwrap();
        drop(cleanup_writer);
        assert!(
            returned.drafts.may_restore(),
            "FIFO import changed the empty draft book"
        );
        assert!(returned
            .notices
            .back()
            .unwrap()
            .contains("Draft import FAILED"));
        assert_eq!(fs::read(legacy).unwrap(), original);
        assert!(matches!(requests.try_recv(), Err(TryRecvError::Empty)));
        assert!(refused_without_writer, "FIFO import blocked for 2 seconds with no writer; only the later cleanup writer released it");
    }
}

#[cfg(test)]
mod draft_safety_tests {
    use super::*;

    #[test]
    fn full_chat_never_evicts_earlier_user_text_or_clears_composer() {
        let mut book = DraftBook::default();
        for i in 0..MAX_LOCAL_DRAFTS {
            book.composer_mut(Workspace::Personal).text = format!("draft-{i}");
            book.save(Workspace::Personal).unwrap();
        }
        book.composer_mut(Workspace::Personal).text = "a valuable unsaved draft".into();
        assert!(book.save(Workspace::Personal).is_err());
        assert_eq!(book.drafts.len(), MAX_LOCAL_DRAFTS);
        assert_eq!(book.drafts[0].text, "draft-0");
        assert_eq!(
            book.composer(Workspace::Personal).text,
            "a valuable unsaved draft"
        );
    }

    #[test]
    fn oversized_utf8_draft_is_not_truncated_or_saved() {
        let mut book = DraftBook::default();
        let original = "中文".repeat(MAX_DRAFT_BYTES / 6 + 1);
        book.composer_mut(Workspace::Personal).text = original.clone();
        assert!(book.save(Workspace::Personal).is_err());
        assert!(book.drafts.is_empty());
        assert_eq!(book.composer(Workspace::Personal).text, original);
    }

    #[test]
    fn import_refuses_to_overwrite_chat_or_unsubmitted_composer() {
        let mut book = DraftBook::default();
        let imported = vec![LocalDraft {
            workspace: Workspace::Personal,
            text: "imported".into(),
            contexts: vec![],
        }];
        assert!(book.may_restore());
        book.composer_mut(Workspace::Build).text = "unfinished".into();
        assert!(!book.may_restore());
        assert!(book.restore(imported.clone()).is_err());
        book.save(Workspace::Build).unwrap();
        assert!(!book.may_restore());
        assert!(book.restore(imported).is_err());
        assert_eq!(book.drafts[0].text, "unfinished");
    }

    #[test]
    fn export_collection_never_omits_unsent_text_or_overwrites_old_backup() {
        let mut book = DraftBook::default();
        assert!(book.export().is_err());
        book.composer_mut(Workspace::Personal).text = "prior saved 中文".into();
        book.save(Workspace::Personal).unwrap();
        book.composer_mut(Workspace::Research).text = "unfinished composer".into();
        assert!(book.export().is_err());
        book.composer_mut(Workspace::Research).text.clear();
        assert_eq!(book.export().unwrap()[0].text, "prior saved 中文");
    }

    #[test]
    fn accepted_chinese_draft_is_stored_exactly_once() {
        let mut book = DraftBook::default();
        book.composer_mut(Workspace::Personal).text = "测试输入法：你好 📝".into();
        assert!(book.save(Workspace::Personal).is_ok());
        assert_eq!(book.drafts.len(), 1);
        assert_eq!(book.drafts[0].text, "测试输入法：你好 📝");
        assert!(book.composer(Workspace::Personal).text.is_empty());
        assert!(book.save(Workspace::Personal).is_err());
        assert_eq!(book.drafts.len(), 1);
    }
}

#[cfg(test)]
mod console_tests {
    use super::*;

    #[test]
    fn process_observations_never_claim_hepta_success() {
        let mut task = TaskRecord::new(42, Workspace::Research, AppKind::Calculator);
        task.pid = Some(1234);
        task.state = TaskState::Completed;
        task.exit_code = Some(0);
        task.detail = "Observed host process exit code 0, not Hepta task completion".into();
        let line = observed_host_line(&task);
        assert!(line.contains("HOST_PROCESS=COMPLETED"));
        assert!(line.contains("PID=1234"));
        assert!(line.contains("FIRST_EGUI_LAYOUT=UNOBSERVED"));
        assert!(line.contains("not Hepta task completion"));
    }

    #[test]
    fn unknown_host_effect_remains_visibly_unknown() {
        let mut task = TaskRecord::new(43, Workspace::Build, AppKind::Notes);
        task.state = TaskState::Unknown;
        task.detail = "Child exit could not be observed".into();
        let line = observed_host_line(&task);
        assert!(line.contains("HOST_PROCESS=UNKNOWN"));
        assert!(line.contains("Child exit could not be observed"));
        assert!(line.contains("WAYLAND_AT_LAUNCH=UNOBSERVED"));
    }
}

#[cfg(test)]
mod shell_lifecycle_tests {
    use super::*;

    #[test]
    fn new_window_offer_requires_observed_running_client_and_changed_live_socket() {
        let mut task = TaskRecord::new(12, Workspace::Build, AppKind::Notes);
        task.wayland_socket_epoch_at_launch = Some(3);
        let mut display = HostWaylandObservation {
            status: WaylandSocketStatus::SocketObserved,
            socket_observation_epoch: 4,
            sampled_unix_ms: 1,
        };
        assert!(!can_offer_fresh_window(&task, Some(&display), true));
        assert!(task.transition(TaskState::Running));
        assert!(!can_offer_fresh_window(&task, Some(&display), true));
        task.pid = Some(1234);
        assert!(!can_offer_fresh_window(&task, Some(&display), true));
        task.ui_first_frame_unix_ms = Some(10);
        assert!(can_offer_fresh_window(&task, Some(&display), true));
        assert!(!can_offer_fresh_window(&task, Some(&display), false));
        assert!(!can_offer_fresh_window(&task, None, true));
        display.status = WaylandSocketStatus::Missing;
        assert!(!can_offer_fresh_window(&task, Some(&display), true));
        display.status = WaylandSocketStatus::SocketObserved;
        display.socket_observation_epoch = 3;
        assert!(!can_offer_fresh_window(&task, Some(&display), true));
        // An out-of-order older socket sample is not evidence that the
        // compositor advanced and must never offer a second process.
        display.socket_observation_epoch = 2;
        assert!(!can_offer_fresh_window(&task, Some(&display), true));
        display.socket_observation_epoch = 4;
        let mut unknown = task.clone();
        assert!(unknown.transition(TaskState::Unknown));
        assert!(!can_offer_fresh_window(&unknown, Some(&display), true));
        let mut partial = task.clone();
        assert!(partial.transition(TaskState::Partial));
        assert!(!can_offer_fresh_window(&partial, Some(&display), true));
        let mut cancelling = task.clone();
        assert!(cancelling.transition(TaskState::CancelRequested));
        assert!(!can_offer_fresh_window(&cancelling, Some(&display), true));
        let mut completed = task.clone();
        assert!(completed.transition(TaskState::Completed));
        assert!(!can_offer_fresh_window(&completed, Some(&display), true));
        task.pid = None;
        assert!(!can_offer_fresh_window(&task, Some(&display), true));
    }

    #[test]
    fn keyboard_focused_host_action_cannot_fake_a_primary_pointer_click() {
        let ctx = egui::Context::default();
        let raw = |events| egui::RawInput {
            focused: true,
            screen_rect: Some(egui::Rect::from_min_size(
                egui::Pos2::ZERO,
                egui::vec2(900.0, 600.0),
            )),
            events,
            ..Default::default()
        };
        let mut button_id = None;
        let _ = ctx.run(raw(vec![]), |ctx| {
            egui::CentralPanel::default().show(ctx, |ui| {
                button_id = Some(ui.button("Request termination").id);
            });
        });
        ctx.memory_mut(|memory| memory.request_focus(button_id.unwrap()));
        for key in [egui::Key::Enter, egui::Key::Space] {
            let mut focused = false;
            let mut effect_clicked = false;
            let _ = ctx.run(
                raw(vec![egui::Event::Key {
                    key,
                    physical_key: None,
                    pressed: true,
                    repeat: false,
                    modifiers: egui::Modifiers::default(),
                }]),
                |ctx| {
                    egui::CentralPanel::default().show(ctx, |ui| {
                        let response = ui.button("Request termination");
                        focused = response.has_focus();
                        effect_clicked = response.clicked_by(egui::PointerButton::Primary);
                    });
                },
            );
            assert!(focused, "test must keep the process-effect control focused");
            assert!(
                !effect_clicked,
                "Enter/Space, including an IME candidate key, must not request a host effect"
            );
        }
    }

    #[test]
    fn focused_draft_file_buttons_ignore_keyboard_candidate_confirmation() {
        for label in [
            "Save local draft",
            "Export drafts to local file",
            "Restore local export",
        ] {
            let ctx = egui::Context::default();
            let input = |events| egui::RawInput {
                focused: true,
                screen_rect: Some(egui::Rect::from_min_size(
                    egui::Pos2::ZERO,
                    egui::vec2(900.0, 600.0),
                )),
                events,
                ..Default::default()
            };
            let mut id = None;
            let _ = ctx.run(input(vec![]), |ctx| {
                egui::CentralPanel::default().show(ctx, |ui| {
                    id = Some(ui.button(label).id);
                });
            });
            ctx.memory_mut(|memory| memory.request_focus(id.unwrap()));
            for key in [egui::Key::Enter, egui::Key::Space] {
                let mut activated_by_pointer = false;
                let _ = ctx.run(
                    input(vec![egui::Event::Key {
                        key,
                        physical_key: None,
                        pressed: true,
                        repeat: false,
                        modifiers: egui::Modifiers::default(),
                    }]),
                    |ctx| {
                        egui::CentralPanel::default().show(ctx, |ui| {
                            activated_by_pointer =
                                ui.button(label).clicked_by(egui::PointerButton::Primary);
                        });
                    },
                );
                assert!(
                    !activated_by_pointer,
                    "{label}: candidate-confirming keyboard action is not an explicit file action"
                );
            }
        }
    }

    #[test]
    fn shell_first_layout_marker_is_exact_and_emitted_once() {
        let mut emitted = false;
        let mut output = Vec::new();
        emit_shell_first_layout(&mut emitted, &mut output).unwrap();
        emit_shell_first_layout(&mut emitted, &mut output).unwrap();
        assert!(emitted);
        assert_eq!(output, SHELL_FIRST_LAYOUT_MARKER);
    }

    #[test]
    fn broken_shell_stdout_never_crashes_or_retries_layout_marker() {
        struct BrokenPipe;
        impl Write for BrokenPipe {
            fn write(&mut self, _bytes: &[u8]) -> io::Result<usize> {
                Err(io::Error::new(io::ErrorKind::BrokenPipe, "closed stdout"))
            }
            fn flush(&mut self) -> io::Result<()> {
                Ok(())
            }
        }
        let mut emitted = false;
        let error = emit_shell_first_layout(&mut emitted, &mut BrokenPipe).unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::BrokenPipe);
        assert!(
            emitted,
            "a closed logging pipe must not trigger a retry loop"
        );
        let mut output = Vec::new();
        emit_shell_first_layout(&mut emitted, &mut output).unwrap();
        assert!(output.is_empty(), "layout marker is one-shot");
    }
}
