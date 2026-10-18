//! Local workspace interaction. Only complete Session snapshots feed live cards;
//! saved or imported quotes cannot create tasks, submit objectives or renew age.

use eframe::egui::{self, RichText};
use std::time::Instant;
use trill_ui_core::conversation::{
    resolve_hepta_runtime, resolve_host_task, ContextRef, HostTaskKey, LocalDraft,
    MAX_DRAFT_CONTEXTS, MAX_LOCAL_DRAFTS,
};
use trill_ui_core::hepta::HeptaProjection;
use trill_ui_core::observation::{freshness_failure, FreshnessFailure};
use trill_ui_core::{TaskRecord, Workspace};

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
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
    pub text: String,
    pub contexts: Vec<ContextRef>,
}

#[derive(Default)]
pub struct DraftBook {
    pub drafts: Vec<LocalDraft>,
    composers: [Composer; 3],
    tabs: [WorkspaceTab; 3],
}

impl DraftBook {
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
        self.tabs[workspace_index(workspace)] = tab;
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
        let draft = LocalDraft {
            workspace,
            text: composer.text.clone(),
            contexts: composer.contexts.clone(),
        };
        draft.validate()?;
        if self.drafts.len() >= MAX_LOCAL_DRAFTS {
            return Err("Local draft history is full; older messages were NOT evicted");
        }
        self.drafts.push(draft);
        *self.composer_mut(workspace) = Composer::default();
        Ok(())
    }

    fn has_unsaved_composer(&self) -> bool {
        self.composers
            .iter()
            .any(|composer| !composer.text.is_empty() || !composer.contexts.is_empty())
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
        ui.horizontal_wrapped(|ui| {
            ui.heading(format!("{} / Chat", self.workspace.name()));
            ui.colored_label(super::warning(), "LOCAL DRAFT · NOT SUBMITTED");
        });
        ui.label("Connect your notes to observed host tasks and runtime context.");
        ui.small("AI objective submission is unavailable. Saving a draft stores it locally.");
        ui.horizontal_wrapped(|ui| {
            for app in [
                trill_ui_core::AppKind::Notes,
                trill_ui_core::AppKind::Calculator,
            ] {
                if ui
                    .add_enabled(
                        self.host_observation.is_current(),
                        egui::Button::new(format!("Open {}", app.name())),
                    )
                    .clicked_by(egui::PointerButton::Primary)
                    && self.launch_host_app(self.workspace, app)
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
        let mut open_task = None;
        egui::ScrollArea::vertical()
            .id_salt(("chat-thread", self.workspace.code()))
            .max_height((ui.available_height() - 285.0).max(120.0))
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
        ui.label("Message / 消息");
        let composer = self.drafts.composer_mut(self.workspace);
        ui.add(
            egui::TextEdit::multiline(&mut composer.text)
                .id(egui::Id::new("hepta-local-composer").with(self.workspace.code()))
                .hint_text("输入想法、任务草稿……")
                .desired_rows(3)
                .desired_width(f32::INFINITY),
        );
        if composer.text.len() > trill_ui_core::conversation::MAX_DRAFT_BYTES {
            ui.colored_label(
                super::warning(),
                "Draft exceeds 16 KiB; all text remains in the composer.",
            );
        }
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
                            if ui
                                .small_button("Remove from draft")
                                .clicked_by(egui::PointerButton::Primary)
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
        ui.horizontal_wrapped(|ui| {
            if ui.add_enabled(!self.drafts.composer(self.workspace).text.trim().is_empty(), egui::Button::new("Save local draft"))
                .clicked_by(egui::PointerButton::Primary)
            {
                match self.drafts.save(self.workspace) {
                    Ok(()) => self.notice("Draft and context references stored in Shell memory. Not executed or sent to Hepta."),
                    Err(message) => self.notice(message),
                }
            }
            ui.small(format!("{} / {} saved drafts", self.drafts.drafts.len(), MAX_LOCAL_DRAFTS));
        });
        ui.horizontal_wrapped(|ui| {
            if ui
                .button("Export drafts to local file")
                .clicked_by(egui::PointerButton::Primary)
            {
                self.export_drafts();
            }
            if ui
                .button("Restore local export")
                .clicked_by(egui::PointerButton::Primary)
            {
                self.restore_drafts();
            }
        });
        ui.small("Explicit export saves all workspaces as private plaintext, including references. Import requires every composer and draft history to be empty; legacy text is assigned to the selected workspace.");
        ui.small(
            "Without export, closing Shell discards local drafts. App lifetimes belong to Session.",
        );
    }

    fn workspace_context(&mut self, ui: &mut egui::Ui) {
        ui.horizontal_wrapped(|ui| {
            for tab in WorkspaceTab::ALL {
                if ui
                    .selectable_label(self.drafts.tab(self.workspace) == tab, tab.name())
                    .clicked()
                {
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
                            if ui
                                .add_enabled(
                                    self.hepta.connection
                                        == trill_ui_core::hepta::HeptaConnectionState::Observed,
                                    egui::Button::new("Quote current Hepta context"),
                                )
                                .clicked_by(egui::PointerButton::Primary)
                            {
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
    fn workspace_switch_keeps_unsent_text_and_context_separate() {
        let mut book = DraftBook::default();
        let task = TaskRecord::new(1, Workspace::Research, AppKind::Notes);
        book.composer_mut(Workspace::Research).text = "研究草稿 📝".into();
        book.attach(
            Workspace::Research,
            ContextRef::host_task(INSTANCE, &task, 10_000),
        )
        .unwrap();
        assert!(book.composer(Workspace::Build).text.is_empty());
        assert!(book.composer(Workspace::Build).contexts.is_empty());
        assert!(book.export().is_err());
        assert!(!book.may_restore());
        book.save(Workspace::Research).unwrap();
        let exported = book.export().unwrap();
        assert_eq!(exported[0].text, "研究草稿 📝");
        assert_eq!(exported[0].workspace, Workspace::Research);
        assert_eq!(exported[0].contexts.len(), 1);
        assert!(book.composer(Workspace::Research).text.is_empty());
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
        book.composer_mut(Workspace::Personal).text = "valuable unsaved".into();
        let task = TaskRecord::new(1, Workspace::Personal, AppKind::Notes);
        book.attach(
            Workspace::Personal,
            ContextRef::host_task(INSTANCE, &task, 10_000),
        )
        .unwrap();
        assert!(book.save(Workspace::Personal).is_err());
        assert_eq!(book.drafts.len(), MAX_LOCAL_DRAFTS);
        assert_eq!(book.drafts[0].text, "keep");
        assert_eq!(book.composer(Workspace::Personal).text, "valuable unsaved");
        assert_eq!(book.composer(Workspace::Personal).contexts.len(), 1);
        book.drafts.clear();
        let oversized = "中文".repeat(MAX_DRAFT_BYTES / 6 + 1);
        book.composer_mut(Workspace::Personal).text = oversized.clone();
        assert!(book.save(Workspace::Personal).is_err());
        assert_eq!(book.composer(Workspace::Personal).text, oversized);
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
        observation.observe(INSTANCE, &[task.clone()], 20_000, now);
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
