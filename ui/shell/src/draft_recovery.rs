//! Renderer-independent lifecycle for the existing bounded recovery writer.
use crate::conversation::DraftBook;
use crate::local_drafts::Recovery;
use std::time::{Duration, Instant};
use trill_ui_core::Workspace;

pub(super) struct DraftRecovery {
    writer: Option<Recovery>,
    last_check: Instant,
    pub(super) warning: Option<String>,
}

impl Default for DraftRecovery {
    fn default() -> Self {
        Self {
            writer: None,
            last_check: Instant::now(),
            warning: None,
        }
    }
}

impl DraftRecovery {
    /// Startup I/O occurs before either renderer opens its event loop. A file
    /// that cannot be safely restored never gains a replacement writer.
    pub(super) fn open() -> (Self, DraftBook, Workspace) {
        let mut state = Self::default();
        let mut book = DraftBook::default();
        let mut workspace = Workspace::Personal;
        if Recovery::enabled() {
            match Recovery::open() {
                Ok((writer, snapshot)) => {
                    let restored = snapshot.map(DraftBook::from_checkpoint).transpose();
                    match restored {
                        Ok(restored) => {
                            if let Some((saved, active)) = restored {
                                book = saved;
                                workspace = active;
                            }
                            state.writer = Some(writer);
                        }
                        Err(error) => state.warning = Some(format!("Draft recovery disabled: {error}. The previous checkpoint is preserved.")),
                    }
                }
                Err(error) => {
                    state.warning = Some(format!(
                    "Draft recovery unavailable: {error}. The previous checkpoint is preserved."
                ))
                }
            }
        }
        (state, book, workspace)
    }

    pub(super) fn tick(&mut self, book: &DraftBook, workspace: Workspace) {
        if let Some(result) = self.writer.as_mut().and_then(Recovery::poll) {
            self.warning = result
                .err()
                .map(|error| format!("Local drafts were not saved: {error}"));
        }
        if self.last_check.elapsed() >= Duration::from_millis(500) {
            self.last_check = Instant::now();
            self.queue_current(book, workspace);
        }
    }

    /// Only serialization and a bounded mailbox write occur on the UI thread.
    /// Active preedit is not a committed draft and retains the previous file.
    pub(super) fn queue_current(&mut self, book: &DraftBook, workspace: Workspace) {
        let Some(writer) = self.writer.as_mut() else {
            return;
        };
        match book.checkpoint(workspace) {
            Ok(checkpoint) => {
                if let Err(error) = writer.queue(&checkpoint) {
                    self.warning = Some(format!("Local drafts were not queued: {error}"));
                }
            }
            Err(error) if error.contains("IME composition") => {}
            Err(error) => self.warning = Some(format!("Local drafts were not saved: {error}")),
        }
    }

    /// Drain only during owner destruction, after the event loop has released
    /// the App. This never blocks a Makepad callback or an egui Draw/update.
    pub(super) fn finish(&mut self, book: &DraftBook, workspace: Workspace) {
        self.queue_current(book, workspace);
        if let Some(mut writer) = self.writer.take() {
            if let Err(error) = writer.finish() {
                eprintln!("trill-shell: local draft recovery failed during close: {error}");
            }
        }
    }
}
