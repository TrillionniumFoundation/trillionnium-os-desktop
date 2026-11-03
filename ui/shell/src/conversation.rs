//! Local workspace interaction. Only complete Session snapshots feed live cards;
//! saved or imported quotes cannot create tasks, submit objectives or renew age.

use eframe::egui::{self, RichText};
use serde::{Deserialize, Serialize};
use std::time::Instant;
use trill_ui_core::conversation::{
    resolve_hepta_runtime, resolve_host_task, ContextRef, HostTaskKey, LocalDraft,
    MAX_DRAFT_CONTEXTS, MAX_LOCAL_DRAFTS,
};
use trill_ui_core::hepta::HeptaProjection;
use trill_ui_core::observation::{freshness_failure, FreshnessFailure};
use trill_ui_core::{TaskRecord, Workspace};

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum WorkspaceTab {
    #[default]
    Tasks,
    Context,
    Console,
}

impl WorkspaceTab {
    pub const ALL: [Self; 3] = [Self::Tasks, Self::Context, Self::Console];
    pub fn name(self) -> &'static str {
        match self {
            Self::Tasks => "Tasks",
            Self::Context => "Context",
            Self::Console => "Console",
        }
    }
}

fn workspace_index(workspace: Workspace) -> usize {
    match workspace {
        Workspace::Personal => 0,
        Workspace::Research => 1,
        Workspace::Build => 2,
    }
}

#[derive(Default)]
pub struct Composer {
    #[cfg(not(feature = "hepta-shared-presenter"))]
    text: String,
    // Under the candidate feature this replaces the String, rather than
    // shadowing it. The original Hepta ChatWorkspace is the sole draft owner.
    #[cfg(feature = "hepta-shared-presenter")]
    shared: trill_ui_core::shared_chat::SharedComposer,
    pub contexts: Vec<ContextRef>,
}

impl Composer {
    #[cfg(feature = "hepta-native-makepad")]
    pub(super) fn native_workspace(&self) -> &trill_ui_core::shared_chat::ChatWorkspace {
        self.shared.native_workspace()
    }

    #[cfg(feature = "hepta-native-makepad")]
    pub(super) fn native_workspace_mut(
        &mut self,
    ) -> &mut trill_ui_core::shared_chat::ChatWorkspace {
        self.shared.native_workspace_mut()
    }

    pub fn text(&self) -> &str {
        #[cfg(feature = "hepta-shared-presenter")]
        {
            self.shared.text()
        }
        #[cfg(not(feature = "hepta-shared-presenter"))]
        {
            &self.text
        }
    }

    #[cfg(test)]
    pub fn edit(&mut self, text: String) -> bool {
        #[cfg(feature = "hepta-shared-presenter")]
        {
            self.shared.edit(self.shared.source(), text)
                == trill_ui_core::shared_chat::ActionResult::Applied
        }
        #[cfg(not(feature = "hepta-shared-presenter"))]
        {
            self.text = text;
            true
        }
    }

    pub(super) fn can_save_local(&self) -> Result<(), &'static str> {
        #[cfg(feature = "hepta-shared-presenter")]
        self.shared.can_save_local()?;
        Ok(())
    }

    pub(super) fn clear(&mut self) -> bool {
        #[cfg(feature = "hepta-shared-presenter")]
        {
            self.shared.clear(self.shared.source())
                == trill_ui_core::shared_chat::ActionResult::Applied
        }
        #[cfg(not(feature = "hepta-shared-presenter"))]
        {
            self.text.clear();
            true
        }
    }
}

#[cfg(not(feature = "hepta-shared-presenter"))]
fn composer_editor(
    ui: &mut egui::Ui,
    composer: &mut Composer,
    workspace: Workspace,
    _ime_confirmation_fenced: bool,
) {
    let label = ui.label("Message / 消息");
    ui.add(
        egui::TextEdit::multiline(&mut composer.text)
            .id(egui::Id::new("hepta-local-composer").with(workspace.code()))
            .hint_text("输入想法、任务草稿……")
            .desired_rows(3)
            .desired_width(f32::INFINITY),
    )
    .labelled_by(label.id);
    if composer.text().len() > trill_ui_core::conversation::MAX_DRAFT_BYTES {
        ui.colored_label(
            super::warning(),
            "Draft exceeds 16 KiB; all text remains in the composer.",
        );
    }
}

#[cfg(feature = "hepta-shared-presenter")]
fn composer_editor(
    ui: &mut egui::Ui,
    composer: &mut Composer,
    workspace: Workspace,
    ime_confirmation_fenced: bool,
) {
    use trill_ui_core::shared_chat::{ActionResult, ComposeStatus};

    let id = egui::Id::new("hepta-local-composer").with(workspace.code());
    let source = composer.shared.source();
    // egui may delete a selection before inserting a paste or IME commit.
    // Keep that sequence transactional: this String exists for this GUI call
    // only, and the original ChatWorkspace owns every accepted draft value.
    let mut transaction = composer.text().to_owned();
    let previous =
        egui::TextEdit::load_state(ui.ctx(), id).map(|state| (state.cursor, state.undoer()));
    let mut editor = egui::TextEdit::multiline(&mut transaction)
        .id(id)
        .hint_text("输入想法、任务草稿……")
        .desired_rows(3)
        .desired_width(f32::INFINITY);
    if ime_confirmation_fenced {
        // egui otherwise handles Commit followed by Return as a line break,
        // including a confirming key delivered in a later frame. This reads
        // the same guard used for buttons; no second IME policy is created.
        editor = editor.return_key(None);
    }
    let label = ui.label("Message / 消息");
    let mut output = editor.show(ui);
    output.response = output.response.labelled_by(label.id);
    if output.response.changed()
        && composer.shared.edit(source, transaction) != ActionResult::Applied
    {
        // Preserve the native IME lifecycle from this callback. Restore only
        // cursor/selection and undo contents for the rejected transaction; a
        // rejected commit must not resurrect an earlier active IME session.
        if let Some((cursor, undoer)) = previous {
            output.state.cursor = cursor;
            output.state.set_undoer(undoer);
        } else {
            output
                .state
                .cursor
                .set_char_range(Some(egui::text::CCursorRange::one(
                    egui::text::CCursor::new(composer.text().chars().count()),
                )));
            output.state.clear_undoer();
        }
        output.state.store(ui.ctx(), id);
        ui.ctx().request_repaint();
    }
    let view = composer.shared.presentation(trill_ui_core::unix_ms());
    if *view.composer.status == ComposeStatus::InputLimit {
        ui.colored_label(
            super::warning(),
            "Edit rejected: 16 KiB limit or NUL input. Previous draft is kept; edit it before saving.",
        );
    }
    ui.small(view.composer.owner_status);
}

#[derive(Default)]
pub struct DraftBook {
    pub drafts: Vec<LocalDraft>,
    composers: [Composer; 3],
    tabs: [WorkspaceTab; 3],
}

/// Local UI recovery only. Context references retain their historical source
/// identities; this file cannot create a live task, owner, grant or delivery.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DraftCheckpoint {
    version: u32,
    drafts: Vec<LocalDraft>,
    workspaces: [WorkspaceCheckpoint; 3],
    active_workspace: Workspace,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct WorkspaceCheckpoint {
    workspace: Workspace,
    rooms: Vec<String>,
    active_room: usize,
    contexts: Vec<ContextRef>,
    tab: WorkspaceTab,
    #[cfg(feature = "hepta-shared-presenter")]
    #[serde(default, skip_serializing_if = "Option::is_none")]
    local_archive: Option<trill_ui_core::shared_chat::LocalDraftArchive>,
    #[cfg(not(feature = "hepta-shared-presenter"))]
    #[serde(default, skip_serializing_if = "Option::is_none")]
    local_archive: Option<serde_json::Value>,
}

impl DraftCheckpoint {
    pub fn validate(&self) -> Result<(), &'static str> {
        if !matches!(self.version, 3 | 4) || self.drafts.len() > MAX_LOCAL_DRAFTS {
            return Err("Unsupported or invalid local checkpoint");
        }
        for draft in &self.drafts {
            draft.validate()?;
        }
        for (workspace, entry) in Workspace::ALL.into_iter().zip(&self.workspaces) {
            if entry.workspace != workspace || entry.contexts.len() > MAX_DRAFT_CONTEXTS {
                return Err("Invalid workspace checkpoint");
            }
            if let Some(archive) = &entry.local_archive {
                if self.version != 4 || !entry.rooms.is_empty() || entry.active_room != 0 {
                    return Err("Checkpoint mixes legacy rooms with a partition archive");
                }
                #[cfg(feature = "hepta-shared-presenter")]
                archive.validate()?;
                #[cfg(not(feature = "hepta-shared-presenter"))]
                {
                    let _ = archive;
                    return Err(
                        "Checkpoint needs the original shared composer feature; file preserved",
                    );
                }
            } else {
                if entry.rooms.is_empty()
                    || entry.rooms.len() > 16
                    || entry.active_room >= entry.rooms.len()
                {
                    return Err("Invalid legacy room checkpoint");
                }
                #[cfg(not(feature = "hepta-shared-presenter"))]
                if entry.rooms.len() != 1 || entry.active_room != 0 {
                    return Err(
                        "Checkpoint needs the original shared composer feature; file preserved",
                    );
                }
                for text in &entry.rooms {
                    if text.len() > trill_ui_core::conversation::MAX_DRAFT_BYTES
                        || text.contains('\0')
                    {
                        return Err(
                            "Checkpoint text exceeds 16 KiB or contains NUL; previous file kept",
                        );
                    }
                }
            }
            for (index, reference) in entry.contexts.iter().enumerate() {
                reference.validate(workspace)?;
                if entry.contexts[..index]
                    .iter()
                    .any(|old| old.same_source(reference))
                {
                    return Err("Duplicate checkpoint context");
                }
            }
        }
        Ok(())
    }
}

impl DraftBook {
    pub fn checkpoint(&self, active_workspace: Workspace) -> Result<DraftCheckpoint, &'static str> {
        let mut entries = Vec::with_capacity(3);
        for workspace in Workspace::ALL {
            let composer = self.composer(workspace);
            #[cfg(feature = "hepta-shared-presenter")]
            let (rooms, active_room, local_archive) =
                (Vec::new(), 0, Some(composer.shared.export_local_archive()?));
            #[cfg(not(feature = "hepta-shared-presenter"))]
            let (rooms, active_room, local_archive) = (vec![composer.text().to_owned()], 0, None);
            entries.push(WorkspaceCheckpoint {
                workspace,
                rooms,
                active_room,
                contexts: composer.contexts.clone(),
                tab: self.tab(workspace),
                local_archive,
            });
        }
        let snapshot = DraftCheckpoint {
            version: 4,
            drafts: self.drafts.clone(),
            workspaces: entries.try_into().map_err(|_| "Missing workspace")?,
            active_workspace,
        };
        snapshot.validate()?;
        Ok(snapshot)
    }

    pub fn from_checkpoint(snapshot: DraftCheckpoint) -> Result<(Self, Workspace), &'static str> {
        snapshot.validate()?;
        let mut restored = Self::default();
        for entry in snapshot.workspaces {
            let composer = restored.composer_mut(entry.workspace);
            #[cfg(feature = "hepta-shared-presenter")]
            {
                if let Some(archive) = entry.local_archive {
                    composer.shared.restore_local_archive(archive)?;
                } else {
                    composer
                        .shared
                        .restore_local_rooms(&entry.rooms, entry.active_room)?;
                }
            }
            #[cfg(not(feature = "hepta-shared-presenter"))]
            {
                composer.text = entry.rooms[0].clone();
            }
            composer.contexts = entry.contexts;
            restored.tabs[workspace_index(entry.workspace)] = entry.tab;
        }
        restored.drafts = snapshot.drafts;
        Ok((restored, snapshot.active_workspace))
    }

    pub fn composer(&self, workspace: Workspace) -> &Composer {
        &self.composers[workspace_index(workspace)]
    }
    pub fn composer_mut(&mut self, workspace: Workspace) -> &mut Composer {
        &mut self.composers[workspace_index(workspace)]
    }
    pub fn tab(&self, workspace: Workspace) -> WorkspaceTab {
        self.tabs[workspace_index(workspace)]
    }
    pub fn set_tab(&mut self, workspace: Workspace, tab: WorkspaceTab) {
        #[cfg(feature = "hepta-shared-presenter")]
        if self
            .composer(workspace)
            .shared
            .presentation(0)
            .composer
            .composing
        {
            return;
        }
        self.tabs[workspace_index(workspace)] = tab;
    }

    #[cfg(feature = "hepta-shared-presenter")]
    pub fn observe_composition(&mut self, workspace: Workspace, composing: bool) {
        for (index, composer) in self.composers.iter_mut().enumerate() {
            composer
                .shared
                .set_composing(index == workspace_index(workspace) && composing);
        }
    }

    pub fn attach(
        &mut self,
        workspace: Workspace,
        reference: ContextRef,
    ) -> Result<(), &'static str> {
        reference.validate(workspace)?;
        let composer = self.composer_mut(workspace);
        if composer
            .contexts
            .iter()
            .any(|old| old.same_source(&reference))
        {
            return Err("This source is already quoted; its original capture was kept");
        }
        if composer.contexts.len() >= MAX_DRAFT_CONTEXTS {
            return Err("Context limit reached (8); earlier references were kept");
        }
        composer.contexts.push(reference);
        Ok(())
    }

    pub fn save(&mut self, workspace: Workspace) -> Result<(), &'static str> {
        let composer = self.composer(workspace);
        composer.can_save_local()?;
        let draft = LocalDraft {
            workspace,
            text: composer.text().to_owned(),
            contexts: composer.contexts.clone(),
        };
        draft.validate()?;
        if self.drafts.len() >= MAX_LOCAL_DRAFTS {
            return Err("Local draft history is full; older messages were NOT evicted");
        }
        // All rejection checks precede Clear, and Clear must succeed before
        // publishing the immutable local capture. Neither is a Hepta send.
        if !self.composer_mut(workspace).clear() {
            return Err("Composer is busy; draft and references were kept.");
        }
        self.composer_mut(workspace).contexts.clear();
        self.drafts.push(draft);
        Ok(())
    }

    fn has_unsaved_composer(&self) -> bool {
        self.composers
            .iter()
            .any(|composer| !composer.text().is_empty() || !composer.contexts.is_empty())
    }

    pub fn export(&self) -> Result<Vec<LocalDraft>, &'static str> {
        if self.has_unsaved_composer() {
            return Err(
                "Export refused: a workspace has unsaved text or context; prior export unchanged.",
            );
        }
        if self.drafts.is_empty() {
            return Err("No saved local drafts; prior export unchanged.");
        }
        Ok(self.drafts.clone())
    }

    pub fn may_restore(&self) -> bool {
        self.drafts.is_empty() && !self.has_unsaved_composer()
    }

    pub fn restore(&mut self, drafts: Vec<LocalDraft>) -> Result<(), &'static str> {
        if !self.may_restore() {
            return Err("Import refused: local chat/composer is not empty; nothing overwritten.");
        }
        if drafts.is_empty() || drafts.len() > MAX_LOCAL_DRAFTS {
            return Err("Invalid imported draft count");
        }
        for draft in &drafts {
            draft.validate()?;
        }
        self.drafts = drafts;
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum HostObservationProblem {
    Disconnected,
    SessionChanged,
    Age(FreshnessFailure),
}

/// This cache is deliberately separate from action-response task updates.
/// Its rows and clock always came from one complete actual Snapshot response.
#[derive(Default)]
pub struct HostObservation {
    pub session_instance: Option<String>,
    pub tasks: Vec<TaskRecord>,
    pub sampled_unix_ms: Option<u64>,
    received_at: Option<Instant>,
    problem: Option<HostObservationProblem>,
}

impl HostObservation {
    pub fn observe(
        &mut self,
        instance: &str,
        tasks: &[TaskRecord],
        sampled_unix_ms: u64,
        received_at: Instant,
    ) {
        *self = Self {
            session_instance: Some(instance.into()),
            tasks: tasks.to_vec(),
            sampled_unix_ms: Some(sampled_unix_ms),
            received_at: Some(received_at),
            problem: None,
        };
    }

    pub fn expire(&mut self, now: Instant, now_unix_ms: u64) {
        // Like the Hepta panel, only a later actual snapshot can restore live
        // status; a wall clock recovery or an action reply cannot do so.
        if self.problem.is_none() {
            self.problem = freshness_failure(
                self.sampled_unix_ms,
                self.received_at
                    .and_then(|received| now.checked_duration_since(received)),
                now_unix_ms,
            )
            .map(HostObservationProblem::Age);
        }
    }

    pub fn disconnect(&mut self, session_changed: bool) {
        self.problem = Some(if session_changed {
            HostObservationProblem::SessionChanged
        } else {
            HostObservationProblem::Disconnected
        });
    }

    pub fn is_current(&self) -> bool {
        self.session_instance.is_some()
            && self.received_at.is_some()
            && self.sampled_unix_ms.is_some()
            && self.problem.is_none()
    }

    pub fn label(&self) -> &'static str {
        if self.session_instance.is_none() {
            return "HOST TASKS · NOT OBSERVED";
        }
        match self.problem {
            None => "HOST TASKS · CURRENT SNAPSHOT",
            Some(HostObservationProblem::Disconnected) => {
                "HOST TASKS · OFFLINE · CURRENT STATE UNKNOWN"
            }
            Some(HostObservationProblem::SessionChanged) => {
                "HOST TASKS · SESSION CHANGED · CURRENT STATE UNKNOWN"
            }
            Some(HostObservationProblem::Age(
                FreshnessFailure::ReceiptExpired | FreshnessFailure::SampleExpired,
            )) => "HOST TASKS · STALE · CURRENT STATE UNKNOWN",
            Some(HostObservationProblem::Age(_)) => {
                "HOST TASKS · INVALID OBSERVATION TIME · CURRENT STATE UNKNOWN"
            }
        }
    }

    pub fn quote(&self, task_id: u64, workspace: Workspace) -> Result<ContextRef, &'static str> {
        if !self.is_current() {
            return Err("Cannot quote a current task: no fresh complete Session snapshot");
        }
        let task = self
            .tasks
            .iter()
            .find(|task| task.id == task_id && task.workspace == workspace)
            .ok_or("Task is absent from this workspace's current snapshot")?;
        Ok(ContextRef::host_task(
            self.session_instance
                .as_deref()
                .ok_or("Session not observed")?,
            task,
            self.sampled_unix_ms.ok_or("Sample time unavailable")?,
        ))
    }
}

/// Returns only a navigation reference. Rendering a card never queues IPC.
pub fn context_card(
    ui: &mut egui::Ui,
    reference: &ContextRef,
    host: &HostObservation,
    current_session: Option<&str>,
    hepta: &HeptaProjection,
) -> Option<HostTaskKey> {
    let mut open_task = None;
    ui.group(|ui| match reference {
        ContextRef::HostTask(quoted) => {
            ui.label(
                RichText::new(format!(
                    "HOST TASK #{} · {}",
                    quoted.key.task_id,
                    quoted.app.name()
                ))
                .strong(),
            );
            ui.small(format!(
                "Session {} · {}",
                quoted.key.session_instance,
                quoted.workspace.name()
            ));
            ui.small(format!(
                "Quoted capture: {} · PID {:?} · sample {}",
                quoted.quoted_state.label(),
                quoted.quoted_pid,
                quoted.sampled_unix_ms
            ));
            match resolve_host_task(
                quoted,
                current_session,
                &host.tasks,
                host.is_current() && host.session_instance.as_deref() == current_session,
            ) {
                Ok(task) => {
                    ui.colored_label(
                        super::success_color(),
                        format!("CURRENT HOST OBSERVATION · {}", task.state.label()),
                    );
                    ui.small(format!(
                        "PID {:?} · snapshot {} · last lifecycle change {}",
                        task.pid,
                        host.sampled_unix_ms.unwrap_or_default(),
                        task.updated_unix_ms
                    ));
                    if ui.small_button("Open task in workspace").clicked() {
                        open_task = Some(quoted.key.clone());
                    }
                }
                Err(reason) => {
                    ui.colored_label(super::warning(), reason.label());
                }
            }
        }
        ContextRef::HeptaRuntime(quoted) => {
            ui.label(RichText::new("HEPTA RUNTIME CONTEXT · READ ONLY").strong());
            ui.small(format!(
                "Agent {} · spawn {} · PID {}",
                quoted.agent_id, quoted.spawn_generation, quoted.process_id
            ));
            ui.small(format!("Observer Session {}", quoted.session_instance));
            ui.small(format!(
                "Quoted capture: {} · generation {} · sample {}",
                quoted.quoted_lifecycle, quoted.quoted_current_generation, quoted.sampled_unix_ms
            ));
            match resolve_hepta_runtime(quoted, current_session, hepta) {
                Ok(observed) => {
                    ui.colored_label(
                        super::success_color(),
                        format!(
                            "CURRENT RUNTIME OBSERVATION · {}",
                            observed.health.lifecycle
                        ),
                    );
                    ui.small(format!(
                        "Generation {} · sample {}",
                        observed.current_generation, observed.sampled_unix_ms
                    ));
                }
                Err(reason) => {
                    ui.colored_label(super::warning(), reason.label());
                }
            }
            ui.small("Runtime context does not associate a host task with an AI objective.");
        }
    });
    open_task
}

impl super::Desktop {
    pub(super) fn show_workspace_tab(&mut self, tab: WorkspaceTab) {
        self.page = super::Page::Conversation;
        self.drafts.set_tab(self.workspace, tab);
    }

    pub(super) fn quote_task(&mut self, id: u64) {
        let result = self
            .host_observation
            .quote(id, self.workspace)
            .and_then(|reference| self.drafts.attach(self.workspace, reference));
        match result {
            Ok(()) => self.notice(format!(
                "Task #{id} quoted in this workspace's draft; no request sent."
            )),
            Err(message) => self.notice(message),
        }
    }

    fn quote_hepta(&mut self) {
        use trill_ui_core::hepta::HeptaConnectionState;
        if self.hepta.connection != HeptaConnectionState::Observed {
            self.notice("No current Hepta observation to quote; draft unchanged");
            return;
        }
        let (Some(instance), Some(observation)) = (
            self.session_instance.as_deref(),
            self.hepta.last_observation.as_ref(),
        ) else {
            return;
        };
        let reference = ContextRef::hepta_runtime(instance, observation);
        match self.drafts.attach(self.workspace, reference) {
            Ok(()) => {
                self.notice("Read-only Hepta source quoted in draft; no objective submitted.")
            }
            Err(message) => self.notice(message),
        }
    }

    fn open_task_context(&mut self, key: HostTaskKey) {
        // Navigation from old/imported quotes cannot select a same-numbered
        // task in another Session or workspace, even after a panel refresh.
        if self.session_instance.as_deref() == Some(key.session_instance.as_str())
            && self.host_observation.is_current()
            && self.host_observation.session_instance.as_deref()
                == Some(key.session_instance.as_str())
            && self
                .host_observation
                .tasks
                .iter()
                .any(|task| task.id == key.task_id && task.workspace == self.workspace)
        {
            self.selected = Some(key.task_id);
            self.show_workspace_tab(WorkspaceTab::Context);
        } else {
            self.notice(
                "Historical task reference cannot select a current task; source not rebound.",
            );
        }
    }

    pub(super) fn conversation(&mut self, ui: &mut egui::Ui) {
        self.activation.begin_frame(ui.ctx());
        ui.horizontal_wrapped(|ui| {
            ui.heading(format!("{} / Chat", self.workspace.name()));
            ui.colored_label(super::warning(), "LOCAL DRAFT · NOT SUBMITTED");
        });
        ui.label("Connect your notes to observed host tasks and runtime context.");
        ui.small("General AI task execution is unavailable. Saving a draft stores it locally; the separate Hepta control writes Notes content only.");
        ui.horizontal_wrapped(|ui| {
            for app in [
                trill_ui_core::AppKind::Notes,
                trill_ui_core::AppKind::Calculator,
            ] {
                if self.activation.activated(&ui.add_enabled(
                    self.host_observation.is_current(),
                    egui::Button::new(format!("Open {}", app.name())),
                )) && self.launch_host_app(self.workspace, app)
                {
                    self.notice(format!(
                        "Queued host launch for {}; waiting for Session observation.",
                        app.name()
                    ));
                }
            }
            ui.colored_label(
                if self.host_observation.is_current() {
                    super::success_color()
                } else {
                    super::warning()
                },
                self.host_observation.label(),
            );
        });
        ui.separator();
        let width = ui.available_width();
        let height = ui.available_height();
        if width >= 900.0 {
            let chat_width = (width * 0.59).floor();
            ui.horizontal_top(|ui| {
                ui.allocate_ui_with_layout(
                    egui::vec2(chat_width, height),
                    egui::Layout::top_down(egui::Align::Min),
                    |ui| {
                        self.chat_thread(ui);
                    },
                );
                ui.separator();
                ui.allocate_ui_with_layout(
                    egui::vec2((width - chat_width - 20.0).max(280.0), height),
                    egui::Layout::top_down(egui::Align::Min),
                    |ui| {
                        self.workspace_context(ui);
                    },
                );
            });
        } else {
            // Narrow native windows keep the same chat/context model. This is
            // responsive host layout, not a claim of a qualified mobile port.
            egui::CollapsingHeader::new("Workspace tasks / context / console")
                .id_salt(("workspace-context", self.workspace.code()))
                .default_open(false)
                .show(ui, |ui| {
                    egui::ScrollArea::vertical()
                        .id_salt("narrow-workspace-context")
                        .max_height(300.0)
                        .show(ui, |ui| self.workspace_context(ui));
                });
            self.chat_thread(ui);
        }
    }

    fn chat_thread(&mut self, ui: &mut egui::Ui) {
        let height = ui.available_height().max(120.0);
        // Objective observations can grow after admission. Keep the complete
        // editor/control stack reachable in a short native window instead of
        // pushing cancellation or export below the viewport.
        egui::ScrollArea::vertical()
            .id_salt(("chat-pane", self.workspace.code()))
            .max_height(height)
            .auto_shrink([false, false])
            .show(ui, |ui| {
                self.chat_thread_content(ui, (height * 0.35).max(100.0))
            });
    }

    fn chat_thread_content(&mut self, ui: &mut egui::Ui, history_height: f32) {
        let mut open_task = None;
        egui::ScrollArea::vertical()
            .id_salt(("chat-thread", self.workspace.code()))
            .max_height(history_height)
            .show(ui, |ui| {
                let mut any = false;
                for draft in self.drafts.drafts.iter().filter(|draft| draft.workspace == self.workspace) {
                    any = true;
                    ui.group(|ui| {
                        ui.label(RichText::new("You · local draft · not submitted").strong().color(egui::Color32::LIGHT_BLUE));
                        ui.label(&draft.text);
                        for reference in &draft.contexts {
                            if let Some(key) = context_card(ui, reference, &self.host_observation, self.session_instance.as_deref(), &self.hepta) { open_task = Some(key); }
                        }
                    });
                    ui.add_space(8.0);
                }
                if !any {
                    ui.group(|ui| {
                        ui.label(RichText::new("Start with a thought or a task reference").strong());
                        ui.label("Use Tasks to quote an observed host app, or Context to quote the read-only Hepta runtime. Each workspace keeps its own unsent composer.");
                    });
                }
            });
        if let Some(key) = open_task {
            self.open_task_context(key);
        }
        ui.separator();
        let composer = self.drafts.composer_mut(self.workspace);
        composer_editor(
            ui,
            composer,
            self.workspace,
            self.activation.ime_confirmation_fenced(),
        );
        let mut remove = None;
        let mut open_task = None;
        let contexts = &self.drafts.composer(self.workspace).contexts;
        if !contexts.is_empty() {
            egui::ScrollArea::vertical()
                .id_salt(("composer-context", self.workspace.code()))
                .max_height(140.0)
                .show(ui, |ui| {
                    for (index, reference) in contexts.iter().enumerate() {
                        ui.push_id(index, |ui| {
                            if let Some(key) = context_card(
                                ui,
                                reference,
                                &self.host_observation,
                                self.session_instance.as_deref(),
                                &self.hepta,
                            ) {
                                open_task = Some(key);
                            }
                            if self
                                .activation
                                .activated(&ui.small_button("Remove from draft"))
                            {
                                remove = Some(index);
                            }
                        });
                    }
                });
        }
        if let Some(index) = remove {
            self.drafts
                .composer_mut(self.workspace)
                .contexts
                .remove(index);
        }
        if let Some(key) = open_task {
            self.open_task_context(key);
        }
        self.objective_controls(ui);
        ui.horizontal_wrapped(|ui| {
            if self.activation.activated(&ui.add_enabled(!self.drafts.composer(self.workspace).text().trim().is_empty(), egui::Button::new("Save local draft")))
            {
                match self.drafts.save(self.workspace) {
                    Ok(()) => self.notice("Local draft saved. Automatic recovery status is separate from Hepta submission."),
                    Err(message) => self.notice(message),
                }
            }
            ui.small(format!("{} / {} saved drafts", self.drafts.drafts.len(), MAX_LOCAL_DRAFTS));
        });
        ui.horizontal_wrapped(|ui| {
            if self
                .activation
                .activated(&ui.button("Export drafts to local file"))
            {
                self.export_drafts();
            }
            if self
                .activation
                .activated(&ui.button("Restore local export"))
            {
                self.restore_drafts();
            }
        });
        ui.small("Explicit export saves all workspaces as private plaintext, including references. Import requires every composer and draft history to be empty; legacy text is assigned to the selected workspace.");
        ui.small(
            "Automatic local recovery follows the configured recovery status. Explicit export remains a separate backup. App lifetimes belong to Session.",
        );
    }

    fn workspace_context(&mut self, ui: &mut egui::Ui) {
        ui.horizontal_wrapped(|ui| {
            for tab in WorkspaceTab::ALL {
                if self.navigation_activated(
                    &ui.selectable_label(self.drafts.tab(self.workspace) == tab, tab.name()),
                ) {
                    self.drafts.set_tab(self.workspace, tab);
                }
            }
        });
        ui.separator();
        ui.push_id(("workspace-tab", self.workspace.code()), |ui| {
            match self.drafts.tab(self.workspace) {
                WorkspaceTab::Tasks => self.task_list(ui),
                WorkspaceTab::Console => self.console(ui),
                WorkspaceTab::Context => {
                    egui::ScrollArea::vertical()
                        .id_salt("workspace-inspector")
                        .show(ui, |ui| {
                            if self.activation.activated(&ui.add_enabled(
                                self.hepta.connection
                                    == trill_ui_core::hepta::HeptaConnectionState::Observed,
                                egui::Button::new("Quote current Hepta context"),
                            )) {
                                self.quote_hepta();
                            }
                            self.inspector(ui);
                            egui::CollapsingHeader::new("Hepta runtime diagnostics")
                                .show(ui, |ui| super::hepta_panel::runtime(ui, &self.hepta));
                        });
                }
            }
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;
    use trill_ui_core::conversation::MAX_DRAFT_BYTES;
    use trill_ui_core::{AppKind, TaskState};
    const INSTANCE: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

    #[test]
    fn checkpoint_roundtrips_saved_and_unsaved_workspaces_with_historical_context() {
        let mut book = DraftBook::default();
        for workspace in Workspace::ALL {
            book.composer_mut(workspace)
                .edit(format!("saved {} 中文", workspace.code()));
            book.save(workspace).unwrap();
            book.composer_mut(workspace)
                .edit(format!("unsaved {} 📝", workspace.code()));
            let task = TaskRecord::new(7, workspace, AppKind::Notes);
            book.attach(workspace, ContextRef::host_task(INSTANCE, &task, 10_000))
                .unwrap();
        }
        book.set_tab(Workspace::Research, WorkspaceTab::Console);
        let expected = book.checkpoint(Workspace::Research).unwrap();
        let bytes = serde_json::to_vec(&expected).unwrap();
        let (restored, workspace) =
            DraftBook::from_checkpoint(serde_json::from_slice(&bytes).unwrap()).unwrap();
        assert_eq!(workspace, Workspace::Research);
        assert_eq!(restored.checkpoint(workspace).unwrap(), expected);
        assert_eq!(restored.drafts.len(), 3);
        assert_eq!(restored.composer(Workspace::Build).contexts.len(), 1);
    }

    #[test]
    fn invalid_checkpoint_is_rejected_as_a_whole() {
        let good = DraftBook::default()
            .checkpoint(Workspace::Personal)
            .unwrap();
        let mut bad = good.clone();
        bad.workspaces[1].rooms = vec!["x".repeat(MAX_DRAFT_BYTES + 1)];
        assert!(DraftBook::from_checkpoint(bad).is_err());
        let mut bad = good.clone();
        bad.workspaces[1].workspace = Workspace::Build;
        assert!(DraftBook::from_checkpoint(bad).is_err());
        let mut bad = good.clone();
        bad.version = 5;
        assert!(DraftBook::from_checkpoint(bad).is_err());
        let mut bad = good;
        bad.workspaces[0].rooms = vec!["bad\0text".into()];
        assert!(DraftBook::from_checkpoint(bad).is_err());
    }

    #[test]
    fn v3_checkpoint_migrates_all_workspace_text_and_selection() {
        let mut legacy = DraftBook::default().checkpoint(Workspace::Build).unwrap();
        legacy.version = 3;
        for entry in &mut legacy.workspaces {
            entry.local_archive = None;
            entry.rooms = vec![format!("legacy {} 中文", entry.workspace.code())];
            entry.active_room = 0;
            #[cfg(feature = "hepta-shared-presenter")]
            {
                entry
                    .rooms
                    .push(format!("selected {} 📝", entry.workspace.code()));
                entry.active_room = 1;
            }
        }
        legacy.workspaces[1].tab = WorkspaceTab::Console;
        let (restored, active) = DraftBook::from_checkpoint(legacy.clone()).unwrap();
        assert_eq!(active, Workspace::Build);
        for entry in &legacy.workspaces {
            assert_eq!(
                restored.composer(entry.workspace).text(),
                entry.rooms[entry.active_room]
            );
        }
        assert_eq!(restored.tab(Workspace::Research), WorkspaceTab::Console);
        let upgraded = restored.checkpoint(active).unwrap();
        assert_eq!(upgraded.version, 4);
        let (reopened, active) = DraftBook::from_checkpoint(upgraded.clone()).unwrap();
        assert_eq!(reopened.checkpoint(active).unwrap(), upgraded);
    }

    #[cfg(feature = "hepta-shared-presenter")]
    #[test]
    fn checkpoint_keeps_parked_local_text_without_activating_its_principal() {
        let mut snapshot = DraftBook::default()
            .checkpoint(Workspace::Research)
            .unwrap();
        snapshot.workspaces[1].local_archive = Some(
            serde_json::from_value(serde_json::json!({
                "version": 1,
                "partitions": [
                    {"principal": null, "rooms": ["anonymous"], "active": 0},
                    {"principal": "account-A", "rooms": ["first", "私人第二间"], "active": 1}
                ]
            }))
            .unwrap(),
        );
        let (restored, workspace) = DraftBook::from_checkpoint(snapshot.clone()).unwrap();
        let view = restored.composer(workspace).shared.presentation(100);
        assert_eq!(view.rooms.len(), 1);
        assert_eq!(view.composer.text, "anonymous");
        assert!(view.timeline.messages.is_empty());
        assert!(view.composer.delivery.is_none());
        assert_eq!(restored.checkpoint(workspace).unwrap(), snapshot);
    }

    #[cfg(feature = "hepta-shared-presenter")]
    #[test]
    fn original_shared_composer_recovers_every_local_room_without_history() {
        let mut book = DraftBook::default();
        book.composer_mut(Workspace::Personal)
            .shared
            .restore_local_rooms(&["first".into(), "第二间".into(), "third".into()], 1)
            .unwrap();
        let expected = book.checkpoint(Workspace::Personal).unwrap();
        let (restored, workspace) = DraftBook::from_checkpoint(expected.clone()).unwrap();
        let view = restored.composer(workspace).shared.presentation(100);
        assert_eq!(view.rooms.len(), 3);
        assert_eq!(view.composer.text, "第二间");
        assert!(view.timeline.messages.is_empty());
        assert!(view.composer.delivery.is_none());
        assert_eq!(restored.checkpoint(workspace).unwrap(), expected);
        book.observe_composition(Workspace::Personal, true);
        assert!(book.checkpoint(Workspace::Personal).is_err());
    }

    #[cfg(not(feature = "hepta-shared-presenter"))]
    #[test]
    fn plain_renderer_cannot_silently_truncate_a_shared_multiroom_checkpoint() {
        let mut snapshot = DraftBook::default()
            .checkpoint(Workspace::Personal)
            .unwrap();
        snapshot.workspaces[0].rooms.push("another room".into());
        assert!(DraftBook::from_checkpoint(snapshot).is_err());
    }

    #[cfg(not(feature = "hepta-shared-presenter"))]
    #[test]
    fn plain_renderer_refuses_partition_archives_without_losing_their_data() {
        let mut snapshot = DraftBook::default()
            .checkpoint(Workspace::Personal)
            .unwrap();
        snapshot.workspaces[0].rooms.clear();
        snapshot.workspaces[0].local_archive = Some(serde_json::json!({
            "version": 1,
            "partitions": [{"principal": null, "rooms": ["keep me"], "active": 0}]
        }));
        assert!(DraftBook::from_checkpoint(snapshot).is_err());
    }

    #[test]
    fn workspace_switch_keeps_unsent_text_and_context_separate() {
        let mut book = DraftBook::default();
        let task = TaskRecord::new(1, Workspace::Research, AppKind::Notes);
        assert!(book
            .composer_mut(Workspace::Research)
            .edit("研究草稿 📝".into()));
        book.attach(
            Workspace::Research,
            ContextRef::host_task(INSTANCE, &task, 10_000),
        )
        .unwrap();
        assert!(book.composer(Workspace::Build).text().is_empty());
        assert!(book.composer(Workspace::Build).contexts.is_empty());
        assert!(book.export().is_err());
        assert!(!book.may_restore());
        book.save(Workspace::Research).unwrap();
        let exported = book.export().unwrap();
        assert_eq!(exported[0].text, "研究草稿 📝");
        assert_eq!(exported[0].workspace, Workspace::Research);
        assert_eq!(exported[0].contexts.len(), 1);
        assert!(book.composer(Workspace::Research).text().is_empty());
    }

    #[test]
    fn full_or_oversized_draft_preserves_all_text_and_references() {
        let mut book = DraftBook {
            drafts: vec![
                LocalDraft {
                    workspace: Workspace::Personal,
                    text: "keep".into(),
                    contexts: vec![]
                };
                MAX_LOCAL_DRAFTS
            ],
            ..Default::default()
        };
        assert!(book
            .composer_mut(Workspace::Personal)
            .edit("valuable unsaved".into()));
        let task = TaskRecord::new(1, Workspace::Personal, AppKind::Notes);
        book.attach(
            Workspace::Personal,
            ContextRef::host_task(INSTANCE, &task, 10_000),
        )
        .unwrap();
        assert!(book.save(Workspace::Personal).is_err());
        assert_eq!(book.drafts.len(), MAX_LOCAL_DRAFTS);
        assert_eq!(book.drafts[0].text, "keep");
        assert_eq!(
            book.composer(Workspace::Personal).text(),
            "valuable unsaved"
        );
        assert_eq!(book.composer(Workspace::Personal).contexts.len(), 1);
        book.drafts.clear();
        let oversized = "中文".repeat(MAX_DRAFT_BYTES / 6 + 1);
        let accepted = book
            .composer_mut(Workspace::Personal)
            .edit(oversized.clone());
        assert_eq!(accepted, !cfg!(feature = "hepta-shared-presenter"));
        assert!(book.save(Workspace::Personal).is_err());
        let expected = if cfg!(feature = "hepta-shared-presenter") {
            "valuable unsaved"
        } else {
            oversized.as_str()
        };
        assert_eq!(book.composer(Workspace::Personal).text(), expected);
        assert_eq!(book.composer(Workspace::Personal).contexts.len(), 1);
        assert!(book.drafts.is_empty());
    }

    #[test]
    fn old_task_change_time_is_not_sample_age_and_expiry_is_sticky() {
        let now = Instant::now();
        let mut task = TaskRecord::new(1, Workspace::Personal, AppKind::Notes);
        task.state = TaskState::Running;
        task.updated_unix_ms = 1;
        let mut observation = HostObservation::default();
        observation.observe(INSTANCE, std::slice::from_ref(&task), 20_000, now);
        observation.expire(now, 20_000);
        assert!(observation.is_current());
        assert!(observation.quote(1, Workspace::Personal).is_ok());
        observation.expire(now, 27_001);
        assert!(!observation.is_current());
        observation.expire(now, 20_000);
        assert!(
            !observation.is_current(),
            "clock recovery cannot restore current status"
        );
        observation.observe(INSTANCE, &[task], 30_000, now);
        observation.expire(now + Duration::from_millis(7_000), 37_000);
        assert!(observation.is_current());
        observation.expire(now + Duration::from_millis(7_001), 37_000);
        assert!(!observation.is_current());
    }

    #[test]
    fn future_or_missing_clocks_stay_unknown_until_a_new_snapshot() {
        let now = Instant::now();
        let mut observation = HostObservation::default();
        observation.expire(now, 20_000);
        assert!(!observation.is_current());
        observation.observe(INSTANCE, &[], 20_001, now);
        observation.expire(now, 20_000);
        assert!(!observation.is_current());
        observation.expire(now, 20_001);
        assert!(!observation.is_current());
        observation.observe(INSTANCE, &[], 20_000, now + Duration::from_millis(1));
        observation.expire(now, 20_000);
        assert!(!observation.is_current());
        observation.observe(INSTANCE, &[], 20_000, now);
        observation.expire(now, 20_000);
        assert!(observation.is_current());
        observation.disconnect(false);
        observation.expire(now, 20_000);
        assert!(!observation.is_current());
    }

    #[test]
    fn context_limit_and_duplicate_source_preserve_the_first_capture() {
        let mut book = DraftBook::default();
        for id in 1..=MAX_DRAFT_CONTEXTS as u64 {
            let task = TaskRecord::new(id, Workspace::Personal, AppKind::Notes);
            book.attach(
                Workspace::Personal,
                ContextRef::host_task(INSTANCE, &task, 20_000),
            )
            .unwrap();
        }
        let first = book.composer(Workspace::Personal).contexts[0].clone();
        let mut repeated = TaskRecord::new(1, Workspace::Personal, AppKind::Notes);
        repeated.state = TaskState::Completed;
        assert!(book
            .attach(
                Workspace::Personal,
                ContextRef::host_task(INSTANCE, &repeated, 30_000)
            )
            .is_err());
        repeated.id = 9;
        assert!(book
            .attach(
                Workspace::Personal,
                ContextRef::host_task(INSTANCE, &repeated, 30_000)
            )
            .is_err());
        assert_eq!(
            book.composer(Workspace::Personal).contexts.len(),
            MAX_DRAFT_CONTEXTS
        );
        assert_eq!(book.composer(Workspace::Personal).contexts[0], first);
    }
}

#[cfg(all(test, feature = "hepta-shared-presenter"))]
mod shared_presenter_tests {
    use super::*;
    use crate::activation::ActivationGuard;
    use trill_ui_core::conversation::MAX_DRAFT_BYTES;
    use trill_ui_core::shared_chat::ComposeStatus;

    fn editor_id() -> egui::Id {
        egui::Id::new("hepta-local-composer").with(Workspace::Personal.code())
    }

    fn key(pressed: bool) -> egui::Event {
        egui::Event::Key {
            key: egui::Key::Enter,
            physical_key: None,
            pressed,
            repeat: false,
            modifiers: egui::Modifiers::default(),
        }
    }

    fn frame(
        ctx: &egui::Context,
        guard: &mut ActivationGuard,
        book: &mut DraftBook,
        events: Vec<egui::Event>,
    ) -> egui::Id {
        let mut save_id = None;
        let _ = ctx.run(
            egui::RawInput {
                focused: true,
                screen_rect: Some(egui::Rect::from_min_size(
                    egui::Pos2::ZERO,
                    egui::vec2(800.0, 600.0),
                )),
                events,
                ..Default::default()
            },
            |ctx| {
                guard.begin_frame(ctx);
                book.observe_composition(Workspace::Personal, guard.composing());
                egui::CentralPanel::default().show(ctx, |ui| {
                    composer_editor(
                        ui,
                        book.composer_mut(Workspace::Personal),
                        Workspace::Personal,
                        guard.ime_confirmation_fenced(),
                    );
                    let response = ui.button("Save local draft");
                    save_id = Some(response.id);
                    if guard.activated(&response) {
                        let _ = book.save(Workspace::Personal);
                    }
                });
            },
        );
        save_id.unwrap()
    }

    #[test]
    fn real_editor_rejects_oversized_selection_paste_atomically() {
        let ctx = egui::Context::default();
        let mut guard = ActivationGuard::default();
        let mut book = DraftBook::default();
        let original = "前缀 selected 中文 tail";
        assert!(book.composer_mut(Workspace::Personal).edit(original.into()));
        frame(&ctx, &mut guard, &mut book, vec![]);
        ctx.memory_mut(|memory| memory.request_focus(editor_id()));
        let selected = egui::text::CCursorRange::two(
            egui::text::CCursor::new(3),
            egui::text::CCursor::new(11),
        );
        let mut state = egui::TextEdit::load_state(&ctx, editor_id()).unwrap();
        state.cursor.set_char_range(Some(selected));
        state.store(&ctx, editor_id());
        frame(
            &ctx,
            &mut guard,
            &mut book,
            vec![egui::Event::Paste("界".repeat(MAX_DRAFT_BYTES))],
        );
        let composer = book.composer(Workspace::Personal);
        assert_eq!(composer.text(), original);
        assert_eq!(
            *composer.shared.presentation(0).composer.status,
            ComposeStatus::InputLimit
        );
        assert!(book.save(Workspace::Personal).is_err());
        assert!(book.drafts.is_empty());
        let restored = egui::TextEdit::load_state(&ctx, editor_id())
            .unwrap()
            .cursor
            .char_range()
            .unwrap();
        assert_eq!(restored.primary.index, selected.primary.index);
        assert_eq!(restored.secondary.index, selected.secondary.index);
        frame(&ctx, &mut guard, &mut book, vec![]);
        assert_eq!(book.composer(Workspace::Personal).text(), original);
    }

    #[test]
    fn real_ime_commit_and_fresh_keyboard_save_use_the_original_draft_once() {
        let ctx = egui::Context::default();
        let mut guard = ActivationGuard::default();
        let mut book = DraftBook::default();
        frame(&ctx, &mut guard, &mut book, vec![]);
        ctx.memory_mut(|memory| memory.request_focus(editor_id()));
        frame(
            &ctx,
            &mut guard,
            &mut book,
            vec![
                egui::Event::Ime(egui::ImeEvent::Enabled),
                egui::Event::Ime(egui::ImeEvent::Preedit("拼音".into())),
            ],
        );
        assert!(
            book.composer(Workspace::Personal)
                .shared
                .presentation(0)
                .composer
                .composing
        );
        assert!(book.save(Workspace::Personal).is_err());
        let save_id = frame(
            &ctx,
            &mut guard,
            &mut book,
            vec![
                egui::Event::Ime(egui::ImeEvent::Commit("中文".into())),
                key(true),
            ],
        );
        assert_eq!(book.composer(Workspace::Personal).text(), "中文");
        assert!(
            !book
                .composer(Workspace::Personal)
                .shared
                .presentation(0)
                .composer
                .composing
        );
        assert!(book.drafts.is_empty(), "IME confirmation is not Save");
        ctx.memory_mut(|memory| memory.request_focus(save_id));
        frame(&ctx, &mut guard, &mut book, vec![key(false)]);
        frame(&ctx, &mut guard, &mut book, vec![key(true)]);
        assert_eq!(book.drafts.len(), 1);
        assert_eq!(book.drafts[0].text, "中文");
        let view = book.composer(Workspace::Personal).shared.presentation(0);
        assert!(view.composer.text.is_empty());
        assert!(view.timeline.messages.is_empty());
        assert!(view.composer.delivery.is_none());
    }

    #[test]
    fn real_editor_ignores_delayed_ime_enter_then_accepts_a_fresh_linebreak() {
        for coalesced_release in [false, true] {
            let ctx = egui::Context::default();
            let mut guard = ActivationGuard::default();
            let mut book = DraftBook::default();
            frame(&ctx, &mut guard, &mut book, vec![]);
            ctx.memory_mut(|memory| memory.request_focus(editor_id()));
            frame(
                &ctx,
                &mut guard,
                &mut book,
                vec![
                    egui::Event::Ime(egui::ImeEvent::Enabled),
                    egui::Event::Ime(egui::ImeEvent::Preedit("候选".into())),
                ],
            );
            frame(
                &ctx,
                &mut guard,
                &mut book,
                vec![egui::Event::Ime(egui::ImeEvent::Commit("中文".into()))],
            );
            frame(&ctx, &mut guard, &mut book, vec![]);
            let mut confirmation = vec![key(true)];
            if coalesced_release {
                confirmation.push(key(false));
            }
            frame(&ctx, &mut guard, &mut book, confirmation);
            assert_eq!(book.composer(Workspace::Personal).text(), "中文");
            assert!(book.drafts.is_empty());
            if !coalesced_release {
                frame(&ctx, &mut guard, &mut book, vec![key(false)]);
            }
            frame(&ctx, &mut guard, &mut book, vec![key(true)]);
            assert_eq!(book.composer(Workspace::Personal).text(), "中文\n");
            assert!(
                book.drafts.is_empty(),
                "editing never creates a local archive"
            );
        }
    }

    #[test]
    fn session_task_quotes_and_local_archives_never_become_original_history() {
        let mut book = DraftBook::default();
        let task = TaskRecord::new(7, Workspace::Personal, trill_ui_core::AppKind::Notes);
        book.attach(
            Workspace::Personal,
            ContextRef::host_task("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", &task, 1000),
        )
        .unwrap();
        assert!(book
            .composer_mut(Workspace::Personal)
            .edit("请检查引用".into()));
        let before = book.composer(Workspace::Personal).shared.presentation(1000);
        assert_eq!(before.timeline.thread_id, None);
        assert!(before.timeline.messages.is_empty());
        assert!(before.composer.delivery.is_none());
        book.save(Workspace::Personal).unwrap();
        assert_eq!(book.drafts[0].contexts.len(), 1);
        let after = book.composer(Workspace::Personal).shared.presentation(1001);
        assert_eq!(after.timeline.thread_id, None);
        assert!(after.timeline.messages.is_empty());
        assert!(after.composer.delivery.is_none());
    }
}
