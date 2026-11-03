//! Persist committed native editor transactions, never egui's transient IME
//! buffer. egui 0.31 mutates that buffer on Preedit as well as Commit.

use eframe::egui::{self, text_edit::TextEditState};
use std::collections::VecDeque;
use trill_ui_core::notes::MAX_NOTES_TEXT_BYTES;

type TextEditUndoer = egui::util::undoer::Undoer<(egui::text::CCursorRange, String)>;

pub(super) const EDITOR_ID: &str = "notes-editor";
const MAX_QUEUED_FRAMES: usize = 64;
const MAX_QUEUED_EVENTS: usize = 1024;
const MAX_QUEUED_TEXT_BYTES: usize = 64 * 1024;

fn frame_number(ctx: &egui::Context) -> u64 {
    ctx.cumulative_pass_nr()
        .saturating_sub(ctx.output(|output| output.num_completed_passes as u64))
}

fn event_text_bytes(event: &egui::Event) -> usize {
    match event {
        egui::Event::Text(value)
        | egui::Event::Paste(value)
        | egui::Event::Ime(egui::ImeEvent::Preedit(value) | egui::ImeEvent::Commit(value)) => {
            value.len()
        }
        _ => 0,
    }
}

struct BeforeEdit {
    text: String,
    revision: u64,
    state: Option<TextEditState>,
    undo: Option<TextEditUndoer>,
}

impl BeforeEdit {
    fn capture(ctx: &egui::Context, text: &str, revision: u64) -> Self {
        let state = TextEditState::load(ctx, egui::Id::new(EDITOR_ID));
        let undo = state.as_ref().map(TextEditState::undoer);
        Self {
            text: text.to_owned(),
            revision,
            state,
            undo,
        }
    }

    fn restore(self, ctx: &egui::Context, text: &mut String) {
        *text = self.text;
        if let Some(previous) = self.state {
            // A snapshot may follow Enabled. Reusing that whole state would
            // restore egui's private IME-enabled flag after cancellation.
            let mut state = TextEditState::default();
            state.cursor = previous.cursor;
            if let Some(undo) = self.undo {
                state.set_undoer(undo);
            }
            state.store(ctx, egui::Id::new(EDITOR_ID));
        }
    }
}

#[derive(Default)]
pub(super) struct NotesInput {
    raw_frames: VecDeque<egui::RawInput>,
    pending_pointer_commit: Option<String>,
    activation_commit: Option<String>,
    composition: Option<BeforeEdit>,
    before_frame: Option<BeforeEdit>,
    empty_preedit: bool,
    commit: bool,
    cancel: bool,
    pointer_cancelled_ime: bool,
    notice: Option<&'static str>,
    queue_notice: Option<&'static str>,
    begun_frame: Option<u64>,
    prepared_frame: Option<u64>,
    finished_frame: Option<u64>,
}

impl NotesInput {
    /// Called by eframe before egui derives pointer/key/focus state. A frame
    /// must not contain a new preedit after an earlier IME terminal event:
    /// TextEdit exposes only its final text, not each intermediate commit.
    /// Keep complete ordered RawInput fragments until that next transaction.
    pub fn raw_input_hook(&mut self, ctx: &egui::Context, raw: &mut egui::RawInput) {
        // A pointer fragment is always pushed to the very front, so the next
        // raw frame is exactly the gesture associated with this real Commit.
        self.activation_commit = self.pending_pointer_commit.take();
        let mut incoming = std::mem::take(raw);
        if self.raw_frames.is_empty() && !incoming.events.is_empty() {
            self.queue_notice = None;
        }
        let events = self
            .raw_frames
            .iter()
            .map(|frame| frame.events.len())
            .sum::<usize>();
        let bytes = self
            .raw_frames
            .iter()
            .flat_map(|frame| &frame.events)
            .map(event_text_bytes)
            .sum::<usize>();
        if !incoming.events.is_empty()
            && (self.raw_frames.len() >= MAX_QUEUED_FRAMES
                || events.saturating_add(incoming.events.len()) > MAX_QUEUED_EVENTS
                || bytes
                    .saturating_add(incoming.events.iter().map(event_text_bytes).sum::<usize>())
                    > MAX_QUEUED_TEXT_BYTES)
        {
            // Already accepted transactions remain queued. Refuse this new
            // batch as a whole, never clear previously committed document text.
            incoming.events.clear();
            incoming.dropped_files.clear();
            incoming.hovered_files.clear();
            self.queue_notice =
                Some("输入队列已满；本次新输入未接收，已有文字和待处理输入保留。请稍后重试。");
        }
        // Idle repaints must not build up behind a deferred transaction. There
        // is at most one extra empty metadata frame beyond the queue bound.
        if self.raw_frames.back().is_some_and(|frame| {
            frame.events.is_empty()
                && frame.dropped_files.is_empty()
                && frame
                    .viewports
                    .values()
                    .all(|viewport| viewport.events.is_empty())
        }) {
            *self.raw_frames.back_mut().expect("checked back frame") = incoming;
        } else {
            self.raw_frames.push_back(incoming);
        }
        let mut current = self.raw_frames.pop_front().expect("incoming frame");
        let mut terminal = false;
        let split = current.events.iter().position(|event| {
            if terminal
                && matches!(
                    event,
                    egui::Event::Ime(
                        egui::ImeEvent::Enabled
                            | egui::ImeEvent::Preedit(_)
                            | egui::ImeEvent::Commit(_)
                    )
                )
            {
                return true;
            }
            terminal |= matches!(
                event,
                egui::Event::Ime(egui::ImeEvent::Commit(_) | egui::ImeEvent::Disabled)
                    | egui::Event::WindowFocused(false)
                    | egui::Event::Key {
                        key: egui::Key::Escape,
                        pressed: true,
                        ..
                    }
            );
            false
        });
        if let Some(index) = split {
            let tail = current.events.split_off(index);
            let mut deferred = current.clone();
            deferred.events = tail;
            deferred.dropped_files.clear();
            for viewport in deferred.viewports.values_mut() {
                viewport.events.clear();
            }
            // A later focus event belongs to the deferred frame, not this
            // earlier commit. Keyboard/pointer events retain their modifiers.
            current.focused = ctx.input(|input| input.focused);
            current.modifiers = ctx.input(|input| input.modifiers);
            for event in &current.events {
                match event {
                    egui::Event::WindowFocused(focused) => current.focused = *focused,
                    egui::Event::Key { modifiers, .. }
                    | egui::Event::PointerButton { modifiers, .. } => {
                        current.modifiers = *modifiers
                    }
                    _ => {}
                }
            }
            if let Some(viewport) = current.viewports.get_mut(&current.viewport_id) {
                viewport.focused = Some(current.focused);
            }
            self.raw_frames.push_front(deferred);
        }
        let native_commit = current.events.iter().find_map(|event| match event {
            egui::Event::Ime(egui::ImeEvent::Commit(value))
                if !value.is_empty() && value != "\n" && value != "\r" =>
            {
                Some(value.clone())
            }
            _ => None,
        });
        if self.composition.is_some() && native_commit.is_some() {
            // TextEdit handles pointer positioning before its IME events. A
            // pointer delivered with Commit would move the private IME anchor
            // and make egui report changed without inserting the confirmation.
            // Commit at that original anchor first; retain the complete mouse
            // gesture for the next ordered frame, ahead of any next preedit.
            let mut pointer = current.clone();
            pointer.events.retain(|event| {
                matches!(
                    event,
                    egui::Event::PointerMoved(_)
                        | egui::Event::PointerButton { .. }
                        | egui::Event::PointerGone
                )
            });
            if !pointer.events.is_empty() {
                current.events.retain(|event| {
                    !matches!(
                        event,
                        egui::Event::PointerMoved(_)
                            | egui::Event::PointerButton { .. }
                            | egui::Event::PointerGone
                    )
                });
                pointer.dropped_files.clear();
                for viewport in pointer.viewports.values_mut() {
                    viewport.events.clear();
                }
                self.raw_frames.push_front(pointer);
                self.pending_pointer_commit = native_commit;
            }
        } else if self.composition.is_some()
            && current
                .events
                .iter()
                .any(|event| matches!(event, egui::Event::PointerButton { pressed: true, .. }))
        {
            // Share this explicit cancellation with ActivationGuard before
            // either consumer sees the frame. Otherwise Notes would cancel
            // while the guard kept blocking subsequent controls as composing.
            current
                .events
                .push(egui::Event::Ime(egui::ImeEvent::Disabled));
        }
        *raw = current;
        if !self.raw_frames.is_empty() {
            ctx.request_repaint();
        }
    }

    /// Preserve the original guard's IME fence for a pointer deferred from a
    /// Commit frame. Only the guard observes this retained Commit; TextEdit
    /// receives the original pointer once and never replays the text effect.
    pub fn begin_activation(
        &self,
        ctx: &egui::Context,
        guard: &mut crate::activation::ActivationGuard,
    ) {
        if let Some(commit) = &self.activation_commit {
            ctx.input_mut(|input| {
                input
                    .events
                    .insert(0, egui::Event::Ime(egui::ImeEvent::Commit(commit.clone())))
            });
        }
        guard.begin_frame(ctx);
        if self.activation_commit.is_some() {
            ctx.input_mut(|input| {
                input.events.remove(0);
            });
        }
    }

    /// Called before polling the worker and before TextEdit consumes events.
    /// Returns true while the visible buffer must survive external projections.
    pub fn begin(&mut self, ctx: &egui::Context, text: &mut String, revision: u64) -> bool {
        let frame = frame_number(ctx);
        if self.begun_frame == Some(frame) {
            return self.composition.is_some();
        }
        self.begun_frame = Some(frame);
        self.commit = false;
        self.cancel = false;
        let (focused, mut events) = ctx.input(|input| (input.focused, input.events.clone()));
        if self.pointer_cancelled_ime
            && events.iter().any(|event| {
                matches!(
                    event,
                    egui::Event::Ime(
                        egui::ImeEvent::Enabled
                            | egui::ImeEvent::Preedit(_)
                            | egui::ImeEvent::Commit(_)
                    )
                )
            })
        {
            // A pointer-only frame explicitly cancelled our old composition.
            // The OS may keep its IME enabled, so establish egui's new anchor
            // before accepting a later real confirmation at the current caret.
            if !events
                .iter()
                .any(|event| matches!(event, egui::Event::Ime(egui::ImeEvent::Enabled)))
            {
                events.insert(0, egui::Event::Ime(egui::ImeEvent::Enabled));
                ctx.input_mut(|input| {
                    input
                        .events
                        .insert(0, egui::Event::Ime(egui::ImeEvent::Enabled))
                });
            }
            self.pointer_cancelled_ime = false;
        }
        let pointer_cancels = self.composition.is_some()
            && events
                .iter()
                .any(|event| matches!(event, egui::Event::PointerButton { pressed: true, .. }));
        let mut saw_preedit = false;
        let mut disabled = !focused;
        let mut ordinary_edit = false;
        for event in &events {
            match event {
                egui::Event::Ime(egui::ImeEvent::Preedit(value)) => {
                    saw_preedit = true;
                    self.empty_preedit = value.is_empty();
                }
                egui::Event::Ime(egui::ImeEvent::Commit(value)) => {
                    // egui ignores newline predictions; an empty commit is a
                    // cancellation, not permission to persist residual preedit.
                    self.commit = !value.is_empty() && value != "\n" && value != "\r";
                    disabled |= !self.commit;
                }
                egui::Event::Ime(egui::ImeEvent::Disabled) => disabled = true,
                egui::Event::Key {
                    key: egui::Key::Escape,
                    pressed: true,
                    ..
                } => disabled = true,
                egui::Event::Text(_) | egui::Event::Paste(_) | egui::Event::Cut => {
                    ordinary_edit = true
                }
                egui::Event::Key { pressed: true, .. }
                | egui::Event::PointerButton { pressed: true, .. } => ordinary_edit = true,
                _ => {}
            }
        }
        if self.composition.is_none() && (saw_preedit || self.commit) {
            self.composition = Some(BeforeEdit::capture(ctx, text, revision));
        }
        // Empty Preedit often precedes Commit in a later frame. Keep the old
        // revision until Commit, explicit cancellation, or ordinary new input.
        if !self.commit
            && (disabled
                || pointer_cancels
                || (self.empty_preedit && !saw_preedit && ordinary_edit))
        {
            if let Some(before) = self.composition.take() {
                before.restore(ctx, text);
                self.cancel = true;
                self.pointer_cancelled_ime |= pointer_cancels;
                // The same raw frame can contain Preedit then Disabled. The
                // original TextEdit would otherwise reinsert that cancelled
                // prediction after this restoration and report it as changed.
                ctx.input_mut(|input| {
                    input
                        .events
                        .retain(|event| !matches!(event, egui::Event::Ime(_)))
                });
            }
            self.empty_preedit = false;
        }
        self.composition.is_some()
    }

    /// Ordinary edits start after the latest worker projection is copied to
    /// the editor. An acknowledgement of our own last edit is not a conflict.
    /// An active IME composition keeps its original pre-poll revision instead.
    pub fn prepare_editor(&mut self, ctx: &egui::Context, text: &str, revision: u64) {
        let frame = frame_number(ctx);
        if self.prepared_frame == Some(frame) {
            return;
        }
        self.prepared_frame = Some(frame);
        self.before_frame = (self.composition.is_none()
            && ctx.input(|input| !input.events.is_empty()))
        .then(|| BeforeEdit::capture(ctx, text, revision));
    }

    /// Only the channel's exact accepted local operation may advance an IME
    /// base. A later external revision is deliberately not part of this ACK.
    pub fn accept_local_revision(&mut self, from: u64, to: u64) {
        if let Some(before) = &mut self.composition {
            if before.revision == from {
                before.revision = to;
            }
        }
    }

    pub fn cancelled(&self) -> bool {
        self.cancel
    }

    pub fn composing(&self) -> bool {
        self.composition.is_some()
    }

    pub fn queued_input(&self) -> bool {
        !self.raw_frames.is_empty()
    }

    pub fn notice(&self) -> Option<&'static str> {
        self.queue_notice.or(self.notice)
    }

    /// Called after the actual TextEdit. A failed size check restores the full
    /// prior text, selection and undo history instead of accepting a prefix.
    pub fn finish(
        &mut self,
        ctx: &egui::Context,
        text: &mut String,
        changed: bool,
        lost_focus: bool,
    ) -> Option<(u64, String)> {
        let frame = frame_number(ctx);
        if self.finished_frame == Some(frame) {
            return None;
        }
        self.finished_frame = Some(frame);
        if lost_focus && (!self.commit || !changed) && self.composition.is_some() {
            if let Some(before) = self.composition.take() {
                before.restore(ctx, text);
                self.empty_preedit = false;
                self.cancel = true;
            }
            return None;
        }
        if self.composition.is_some() && !self.commit {
            return None;
        }
        let before = if self.commit {
            self.empty_preedit = false;
            self.composition.take()
        } else {
            self.before_frame.take()
        }?;
        if text.len() > MAX_NOTES_TEXT_BYTES {
            before.restore(ctx, text);
            self.notice = Some("输入超过4096字节，已保留原文和撤销记录。");
            return None;
        }
        if (changed || self.commit) && *text != before.text {
            self.notice = None;
            Some((before.revision, text.clone()))
        } else {
            None
        }
    }
}

#[cfg(test)]
#[path = "notes_input_tests.rs"]
mod tests;
