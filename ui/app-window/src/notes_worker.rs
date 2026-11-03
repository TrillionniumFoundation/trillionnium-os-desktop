//! One application-state worker serializes effects, local CAS edits and
//! receipt retirement. Filesystem sync never runs in the renderer event loop.

use super::Pending;
use eframe::egui;
use std::io;
use std::path::PathBuf;
use std::sync::{mpsc, Arc, Mutex};
use std::time::Instant;
use trill_ui_core::notes::{NotesDocument, NotesTargetIdentity};
use trill_ui_core::notes_lifetime::{SessionLifetime, StorageRequirement};
use trill_ui_core::notes_store::{NotesStore, SavedNotesDocument, SavedNotesListing};

#[cfg(all(test, target_os = "linux"))]
#[path = "notes_lifetime_tests.rs"]
mod lifetime_tests;

pub(super) enum Command {
    Protocol(Pending),
    LocalEdit {
        id: u64,
        revision: u64,
        text: String,
    },
    ListSaved {
        id: u64,
    },
    RestoreSaved {
        id: u64,
        revision: u64,
        source: SavedNotesDocument,
    },
}

#[derive(Clone, Default)]
pub(super) struct Projection {
    pub version: u64,
    pub text: String,
    pub revision: u64,
    pub local_result: Option<(u64, bool, u64)>,
    pub storage_failed: bool,
    pub saved_documents: Option<(u64, Result<SavedNotesListing, String>)>,
    pub restore_result: Option<(u64, Result<(), String>)>,
}

enum Document {
    Memory(NotesDocument),
    Durable(NotesStore),
}

impl Document {
    fn target(&self) -> &NotesTargetIdentity {
        match self {
            Self::Memory(value) => value.target(),
            Self::Durable(value) => value.target(),
        }
    }

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
    pub lifetime: Option<SessionLifetime>,
}

pub(super) fn start(
    ctx: egui::Context,
    target: NotesTargetIdentity,
    lifetime: Option<SessionLifetime>,
) -> io::Result<Connection> {
    if let Some(lifetime) = &lifetime {
        lifetime.check_alive()?;
    }
    let root = std::env::var_os("TRILL_NOTES_STATE_DIR").map(PathBuf::from);
    if lifetime
        .as_ref()
        .is_some_and(|l| l.storage_requirement() == StorageRequirement::DurableRequired)
    {
        NotesStore::validate_existing_storage_root(
            root.as_ref()
                .ok_or_else(|| io::Error::other("Root Notes lifetime requires durable storage"))?,
        )?;
    }
    let document = if let Some(root) = &root {
        Document::Durable(NotesStore::create(root, target)?)
    } else {
        Document::Memory(NotesDocument::new(target).map_err(|_| io::Error::other("Notes target"))?)
    };
    let durable = matches!(document, Document::Durable(_));
    let projection = Arc::new(Mutex::new(Projection::default()));
    let output = projection.clone();
    let (sender, receiver) = mpsc::sync_channel(4);
    let worker_lifetime = lifetime.clone();
    std::thread::Builder::new()
        .name("notes-document-owner".into())
        .spawn(move || {
            run(document, root, receiver, output, ctx, worker_lifetime);
        })?;
    Ok(Connection {
        sender,
        projection,
        durable,
        lifetime,
    })
}

fn run(
    mut document: Document,
    root: Option<PathBuf>,
    receiver: mpsc::Receiver<Command>,
    output: Arc<Mutex<Projection>>,
    ctx: egui::Context,
    lifetime: Option<SessionLifetime>,
) {
    let mut projection = Projection::default();
    loop {
        if lifetime.as_ref().is_some_and(SessionLifetime::has_ended) {
            ctx.request_repaint();
            return;
        }
        let command = match receiver.recv_timeout(std::time::Duration::from_millis(50)) {
            Ok(command) => command,
            Err(mpsc::RecvTimeoutError::Timeout) => continue,
            Err(mpsc::RecvTimeoutError::Disconnected) => return,
        };
        if lifetime.as_ref().is_some_and(SessionLifetime::has_ended) {
            ctx.request_repaint();
            return;
        }
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
            Command::ListSaved { id } => {
                let result = root
                    .as_ref()
                    .ok_or_else(|| "Temporary Notes have no saved document directory".to_owned())
                    .and_then(|root| {
                        NotesStore::saved_documents(root, document.target())
                            .map_err(|error| error.to_string())
                    });
                projection.saved_documents = Some((id, result));
                None
            }
            Command::RestoreSaved {
                id,
                revision,
                source,
            } => {
                let result = match (&mut document, root.as_ref()) {
                    (Document::Durable(store), Some(root)) => store
                        .restore_saved_text(root, &source, revision)
                        .map_err(|error| error.to_string()),
                    _ => Err("Temporary Notes cannot restore saved documents".to_owned()),
                };
                projection.restore_result = Some((id, result));
                None
            }
        };
        if lifetime.as_ref().is_some_and(SessionLifetime::has_ended) {
            ctx.request_repaint();
            return;
        }
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
