//! Persist committed native editor transactions, never egui's transient IME
//! buffer. egui 0.31 mutates that buffer on Preedit as well as Commit.

use eframe::egui::{self, text_edit::TextEditState};
use trill_ui_core::notes::MAX_NOTES_TEXT_BYTES;

type TextEditUndoer = egui::util::undoer::Undoer<(egui::text::CCursorRange, String)>;

pub(super) const EDITOR_ID: &str = "notes-editor";

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
    composition: Option<BeforeEdit>,
    before_frame: Option<BeforeEdit>,
    empty_preedit: bool,
    commit: bool,
    cancel: bool,
    notice: Option<&'static str>,
}

impl NotesInput {
    /// Called before polling the worker and before TextEdit consumes events.
    /// Returns true while the visible buffer must survive external projections.
    pub fn begin(&mut self, ctx: &egui::Context, text: &mut String, revision: u64) -> bool {
        self.commit = false;
        self.cancel = false;
        let (focused, events) = ctx.input(|input| (input.focused, input.events.clone()));
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
        if !self.commit && (disabled || (self.empty_preedit && !saw_preedit && ordinary_edit)) {
            if let Some(before) = self.composition.take() {
                before.restore(ctx, text);
                self.cancel = true;
            }
            self.empty_preedit = false;
        }
        self.before_frame = (self.composition.is_none() && !events.is_empty())
            .then(|| BeforeEdit::capture(ctx, text, revision));
        self.composition.is_some()
    }

    pub fn cancelled(&self) -> bool {
        self.cancel
    }

    pub fn composing(&self) -> bool {
        self.composition.is_some()
    }

    pub fn notice(&self) -> Option<&'static str> {
        self.notice
    }

    /// Called after the actual TextEdit. A failed size check restores the full
    /// prior text, selection and undo history instead of accepting a prefix.
    pub fn finish(
        &mut self,
        ctx: &egui::Context,
        text: &mut String,
        changed: bool,
    ) -> Option<(u64, String)> {
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
