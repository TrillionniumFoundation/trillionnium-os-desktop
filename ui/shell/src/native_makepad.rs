//! Moves the existing Desktop state into the original Hepta Makepad App.
//! No task/health observation can create chat authority or a transcript.
use super::{Desktop, Page, StartupOptions, WorkspaceTab};
use hepta_session_host::text::TextChatAdapter;
use std::fmt::Write;
use std::sync::Arc;
use std::time::{Duration, Instant};
use trill_ui_core::shared_chat::native_presentation::{
    run_native_presentation, NativeApprovalDecision, NativeApprovalView, NativeChatAvailability,
    NativeChatComposition, NativeConsoleObservation, NativeNotesView,
};
use trill_ui_core::shared_chat::{ChatWorkspace, NativeWorkspaceTab, RoomKey};

struct DesktopComposition {
    desktop: Desktop,
    refresh_pending: bool,
    closed: bool,
    displayed_recovery_warning: Option<String>,
    chat_config: Result<Option<super::native_text_config::TextLaunchEndpoint>, String>,
    chat: Option<TextChatAdapter>,
    chat_started: bool,
    last_native_tab: NativeWorkspaceTab,
}

impl DesktopComposition {
    fn sync_tab_for_recovery(&mut self) {
        let tab = self.workspace().tab;
        if tab != self.last_native_tab {
            self.desktop.drafts.set_tab(
                self.desktop.workspace,
                match tab {
                    NativeWorkspaceTab::Console => WorkspaceTab::Console,
                    NativeWorkspaceTab::Conversations => WorkspaceTab::Tasks,
                },
            );
            self.last_native_tab = tab;
        }
    }

    fn validate_source(&self, source: RoomKey) -> Result<(), String> {
        if self.closed
            || source.epoch != self.workspace().presentation_epoch()
            || source.local_id != self.workspace().active_id()
            || self.workspace().composing
        {
            return Err("Conversation changed or input is composing; action was not queued".into());
        }
        Ok(())
    }

    fn validate_notes_source(&self, source: RoomKey) -> Result<(), String> {
        self.validate_source(source)?;
        if self.workspace().tab != NativeWorkspaceTab::Conversations
            || self.workspace().navigation_open
        {
            return Err(
                "Notes action is unavailable outside the current conversation; draft retained"
                    .into(),
            );
        }
        Ok(())
    }
}

impl NativeChatComposition for DesktopComposition {
    fn workspace(&self) -> &ChatWorkspace {
        self.desktop
            .drafts
            .composer(self.desktop.workspace)
            .native_workspace()
    }

    fn workspace_mut(&mut self) -> &mut ChatWorkspace {
        self.desktop
            .drafts
            .composer_mut(self.desktop.workspace)
            .native_workspace_mut()
    }

    fn set_waker(&mut self, waker: Arc<dyn Fn() + Send + Sync>) {
        self.desktop.bridge.set_waker(waker.clone());
        if self.chat_started || self.closed {
            return;
        }
        self.chat_started = true;
        if let Ok(Some(endpoint)) = &self.chat_config {
            match TextChatAdapter::start(endpoint.socket_path.clone(), endpoint.root_pid, waker) {
                Ok(chat) => self.chat = Some(chat),
                Err(error) => self.chat_config = Err(error),
            }
        }
    }

    fn poll_chat(&mut self) -> NativeChatAvailability {
        if self.closed {
            return NativeChatAvailability::default();
        }
        let Some(chat) = self.chat.as_mut() else {
            return NativeChatAvailability::default();
        };
        let workspace = self
            .desktop
            .drafts
            .composer_mut(self.desktop.workspace)
            .native_workspace_mut();
        let availability = chat.poll(workspace, trill_ui_core::unix_ms());
        NativeChatAvailability {
            can_submit: availability.can_submit,
            can_interrupt: availability.can_interrupt,
            can_load_earlier: availability.can_load_earlier,
            can_load_latest: availability.can_load_latest,
        }
    }

    fn request_send(&mut self, source: RoomKey) -> Result<(), String> {
        self.validate_source(source)?;
        let chat = self
            .chat
            .as_mut()
            .ok_or("Authenticated Root chat lane is unavailable; draft retained")?;
        let workspace = self
            .desktop
            .drafts
            .composer_mut(self.desktop.workspace)
            .native_workspace_mut();
        chat.request_send(workspace, source.local_id, trill_ui_core::unix_ms())
    }

    fn request_interrupt(&mut self, source: RoomKey) -> Result<(), String> {
        self.validate_source(source)?;
        let chat = self
            .chat
            .as_mut()
            .ok_or("Authenticated Root chat lane is unavailable")?;
        let workspace = self
            .desktop
            .drafts
            .composer_mut(self.desktop.workspace)
            .native_workspace_mut();
        chat.request_interrupt(workspace, source.local_id, trill_ui_core::unix_ms())
    }

    fn request_earlier_history(&mut self, source: RoomKey) -> Result<(), String> {
        self.validate_source(source)?;
        let chat = self
            .chat
            .as_mut()
            .ok_or("Authenticated Root chat lane is unavailable")?;
        let workspace = self
            .desktop
            .drafts
            .composer_mut(self.desktop.workspace)
            .native_workspace_mut();
        chat.request_earlier_history(workspace, source.local_id, trill_ui_core::unix_ms())
    }

    fn request_latest_history(&mut self, source: RoomKey) -> Result<(), String> {
        self.validate_source(source)?;
        let chat = self
            .chat
            .as_mut()
            .ok_or("Authenticated Root chat lane is unavailable")?;
        let workspace = self
            .desktop
            .drafts
            .composer_mut(self.desktop.workspace)
            .native_workspace_mut();
        chat.request_latest_history(workspace, source.local_id, trill_ui_core::unix_ms())
    }

    fn notes_view(&self) -> Option<NativeNotesView> {
        if self.closed {
            return None;
        }
        let view = self.desktop.notes_controls_view();
        let current = self.workspace().tab == NativeWorkspaceTab::Conversations
            && !self.workspace().navigation_open
            && !self.workspace().composing;
        Some(NativeNotesView {
            status: view.status,
            can_write: current && view.can_write,
            can_refresh: current && view.can_refresh,
            can_cancel: current && view.can_cancel,
        })
    }

    fn request_write_note(&mut self, source: RoomKey) -> Result<(), String> {
        self.validate_notes_source(source)?;
        self.desktop.write_note_from_draft()
    }

    fn request_notes_refresh(&mut self, source: RoomKey) -> Result<(), String> {
        self.validate_notes_source(source)?;
        self.desktop.refresh_notes_controls()
    }

    fn request_notes_cancel(&mut self, source: RoomKey) -> Result<(), String> {
        self.validate_notes_source(source)?;
        self.desktop.cancel_note_request()
    }

    fn pending_approval(&self) -> Option<NativeApprovalView> {
        let view = self
            .chat
            .as_ref()?
            .pending_approval(self.workspace(), trill_ui_core::unix_ms())?;
        Some(NativeApprovalView {
            id: view.id,
            title: view.title,
            details: view.details,
            can_accept: view.can_accept,
            can_decline: view.can_decline,
            busy: view.busy,
        })
    }

    fn request_approval(
        &mut self,
        source: RoomKey,
        id: &str,
        decision: NativeApprovalDecision,
    ) -> Result<(), String> {
        self.validate_source(source)?;
        let chat = self
            .chat
            .as_mut()
            .ok_or("Authenticated Root chat lane is unavailable")?;
        let workspace = self
            .desktop
            .drafts
            .composer_mut(self.desktop.workspace)
            .native_workspace_mut();
        let decision = match decision {
            NativeApprovalDecision::AcceptOnce => {
                hepta_session_host::text::TextApprovalDecision::AcceptOnce
            }
            NativeApprovalDecision::Decline => {
                hepta_session_host::text::TextApprovalDecision::Decline
            }
        };
        chat.request_approval(
            workspace,
            source.local_id,
            id,
            decision,
            trill_ui_core::unix_ms(),
        )
    }

    fn poll_console(&mut self) -> NativeConsoleObservation {
        if self.closed {
            return NativeConsoleObservation {
                text: "Desktop window closed".into(),
                refresh_pending: false,
            };
        }
        if self
            .desktop
            .receive_and_refresh_hepta(|| (Instant::now(), trill_ui_core::unix_ms()))
        {
            self.refresh_pending = false;
        }
        self.desktop.poll_notes_controls();
        self.sync_tab_for_recovery();
        self.desktop
            .recovery
            .tick(&self.desktop.drafts, self.desktop.workspace);
        let warning = self.desktop.recovery.warning.clone();
        if warning != self.displayed_recovery_warning {
            if warning.is_some()
                || self.workspace().presentation_note == self.displayed_recovery_warning
            {
                self.workspace_mut().presentation_note = warning.clone();
            }
            self.displayed_recovery_warning = warning;
        }
        if self.desktop.last_poll.elapsed() >= Duration::from_millis(800) {
            self.desktop.bridge.poll();
            self.desktop.last_poll = Instant::now();
        }
        // Connection/status below comes only from the existing receive reducer.
        // A locally queued refresh has no success or readiness meaning.
        let mut text = format!(
            "Trillionnium · {} workspace\nOriginal Hepta Makepad renderer\n\n",
            self.desktop.workspace.name()
        );
        let _ = writeln!(
            text,
            "Chat: {}",
            self.workspace().owner_status(trill_ui_core::unix_ms())
        );
        match &self.chat_config {
            Ok(None) => {
                let _ = writeln!(
                    text,
                    "Authenticated Root UI lane is not configured; local drafts remain available."
                );
            }
            Err(error) => {
                let _ = writeln!(text, "Chat launch configuration: {error}");
            }
            Ok(Some(_)) => {}
        }
        if self.desktop.connected {
            let _ = writeln!(
                text,
                "Session observed: {}",
                self.desktop
                    .session_instance
                    .as_deref()
                    .unwrap_or("unobserved")
            );
        } else {
            let _ = writeln!(text, "Session unavailable: {}", self.desktop.session_error);
        }
        let _ = writeln!(
            text,
            "Hepta connection: {:?}",
            self.desktop.hepta.connection
        );
        if let Some(error) = &self.desktop.hepta.error_code {
            let _ = writeln!(text, "Hepta observation: {error}");
        }
        for task in &self.desktop.tasks {
            let _ = writeln!(text, "{}", super::observed_host_line(task));
        }
        for notice in self.desktop.notices.iter().rev().take(8) {
            let _ = writeln!(text, "{notice}");
        }
        NativeConsoleObservation {
            text,
            refresh_pending: self.refresh_pending,
        }
    }

    fn request_refresh(&mut self) {
        if !self.closed {
            self.desktop.bridge.poll();
            self.refresh_pending = true;
            if let Some(chat) = self.chat.as_mut() {
                if let Err(error) = chat.reconnect() {
                    self.workspace_mut().presentation_note = Some(error);
                }
            }
        }
    }

    fn on_ui_exit(&mut self) {
        self.sync_tab_for_recovery();
        self.desktop
            .recovery
            .queue_current(&self.desktop.drafts, self.desktop.workspace);
        self.closed = true;
        // Closing a client is separate from requesting an original turn stop.
        self.chat = None;
        self.desktop.bridge.close();
    }
}

pub(super) fn run(options: StartupOptions) -> Result<(), String> {
    let root = super::native_resources::verified_root()?;
    let mut composition = DesktopComposition {
        desktop: Desktop::from_options(options),
        refresh_pending: true,
        closed: false,
        displayed_recovery_warning: None,
        chat_config: super::native_text_config::from_environment(),
        chat: None,
        chat_started: false,
        last_native_tab: NativeWorkspaceTab::Conversations,
    };
    // Explicit CLI navigation wins; otherwise restore the actual original App
    // tab. The desktop workspace stays fixed while the App owns its borrows.
    let tab = if options.page_explicit {
        if options.page == Page::Console {
            NativeWorkspaceTab::Console
        } else {
            NativeWorkspaceTab::Conversations
        }
    } else if composition
        .desktop
        .drafts
        .tab(composition.desktop.workspace)
        == WorkspaceTab::Console
    {
        NativeWorkspaceTab::Console
    } else {
        NativeWorkspaceTab::Conversations
    };
    composition.workspace_mut().tab = tab;
    composition.last_native_tab = tab;
    run_native_presentation(
        Box::new(composition),
        Box::new(move |cx| {
            cx.package_root = Some(root);
        }),
    )
}

#[cfg(test)]
#[path = "native_notes_tests.rs"]
mod notes_tests;
