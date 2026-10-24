//! One application-state worker serializes effects, local CAS edits and
//! receipt retirement. Filesystem sync never runs in the renderer event loop.

use super::Pending;
use eframe::egui;
use std::io;
use std::path::PathBuf;
use std::sync::{mpsc, Arc, Mutex};
use std::time::Instant;
use trill_ui_core::notes::{NotesDocument, NotesTargetIdentity};
use trill_ui_core::notes_store::NotesStore;

pub(super) enum Command {
    Protocol(Pending),
    LocalEdit {
        id: u64,
        revision: u64,
        text: String,
    },
}

#[derive(Clone, Default)]
pub(super) struct Projection {
    pub version: u64,
    pub text: String,
    pub revision: u64,
    pub local_result: Option<(u64, bool, u64)>,
    pub storage_failed: bool,
}

enum Document {
    Memory(NotesDocument),
    Durable(NotesStore),
}

impl Document {
    fn text(&self) -> &str {
        match self {
            Self::Memory(value) => value.text(),
            Self::Durable(value) => value.text(),
        }
    }

    fn revision(&self) -> u64 {
        match self {
            Self::Memory(value) => value.revision(),
            Self::Durable(value) => value.revision(),
        }
    }

    fn frozen(&self) -> bool {
        matches!(self, Self::Durable(value) if value.is_frozen())
    }

    fn protocol(&mut self, pending: &Pending) -> Option<Vec<u8>> {
        match (self, pending.recovery) {
            (Self::Memory(value), true) => value.recovery_exact(&pending.bytes).ok(),
            (Self::Durable(value), true) => value.recovery_exact(&pending.bytes).ok(),
            (Self::Memory(value), false) => {
                serde_json::to_vec(&value.apply_exact(&pending.bytes).ok()?).ok()
            }
            (Self::Durable(value), false) => {
                serde_json::to_vec(&value.apply_exact(&pending.bytes).ok()?).ok()
            }
        }
    }

    fn local_edit(&mut self, text: String) -> bool {
        match self {
            Self::Memory(value) => value.local_edit(text).is_ok(),
            Self::Durable(value) => value.local_edit(text).is_ok(),
        }
    }
}

pub(super) struct Connection {
    pub sender: mpsc::SyncSender<Command>,
    pub projection: Arc<Mutex<Projection>>,
    pub durable: bool,
}

pub(super) fn start(ctx: egui::Context, target: NotesTargetIdentity) -> io::Result<Connection> {
    let document = if let Some(root) = std::env::var_os("TRILL_NOTES_STATE_DIR") {
        Document::Durable(NotesStore::create(&PathBuf::from(root), target)?)
    } else {
        Document::Memory(NotesDocument::new(target).map_err(|_| io::Error::other("Notes target"))?)
    };
    let durable = matches!(document, Document::Durable(_));
    let projection = Arc::new(Mutex::new(Projection::default()));
    let output = projection.clone();
    let (sender, receiver) = mpsc::sync_channel(4);
    std::thread::Builder::new()
        .name("notes-document-owner".into())
        .spawn(move || {
            run(document, receiver, output, ctx);
        })?;
    Ok(Connection {
        sender,
        projection,
        durable,
    })
}

fn run(
    mut document: Document,
    receiver: mpsc::Receiver<Command>,
    output: Arc<Mutex<Projection>>,
    ctx: egui::Context,
) {
    let mut projection = Projection::default();
    while let Ok(command) = receiver.recv() {
        let reply = match command {
            Command::Protocol(pending) => {
                let result = if Instant::now() < pending.expires_at {
                    document.protocol(&pending)
                } else {
                    None
                };
                Some((pending.reply, result))
            }
            Command::LocalEdit { id, revision, text } => {
                let accepted = revision == document.revision() && document.local_edit(text);
                projection.local_result = Some((id, accepted, document.revision()));
                None
            }
        };
        projection.version = projection.version.saturating_add(1);
        projection.text = document.text().to_owned();
        projection.revision = document.revision();
        projection.storage_failed = document.frozen();
        if let Ok(mut current) = output.lock() {
            *current = projection.clone();
        } else {
            return;
        }
        ctx.request_repaint();
        if let Some((sender, result)) = reply {
            let _ = sender.try_send(result);
        }
    }
}

#[cfg(test)]
#[path = "notes_worker_tests.rs"]
mod tests;
