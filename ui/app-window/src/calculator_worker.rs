//! One owner serializes Calculator state, local CAS edits and durable receipts.
//! Filesystem synchronization never runs in the renderer event loop.
use super::Pending;
use eframe::egui;
use std::io;
use std::path::PathBuf;
use std::sync::{mpsc, Arc, Mutex};
use std::time::Duration;
use trill_ui_core::calculator::{
    CalculatorDocument, CalculatorTargetIdentity, CalculatorValueState,
};
use trill_ui_core::calculator_lifetime::{SessionLifetime, StorageRequirement};
use trill_ui_core::calculator_store::CalculatorStore;

pub(super) enum Command {
    Protocol(Pending),
    LocalEdit {
        id: u64,
        revision: u64,
        state: CalculatorValueState,
    },
}
#[derive(Clone, Default)]
pub(super) struct Projection {
    pub version: u64,
    pub state: CalculatorValueState,
    pub revision: u64,
    pub receipt_pending: bool,
    pub local_result: Option<(u64, bool)>,
    pub storage_failed: bool,
}
enum Document {
    Memory(CalculatorDocument),
    Durable(CalculatorStore),
}
impl Document {
    fn state(&self) -> &CalculatorValueState {
        match self {
            Self::Memory(v) => v.state(),
            Self::Durable(v) => v.state(),
        }
    }
    fn revision(&self) -> u64 {
        match self {
            Self::Memory(v) => v.revision(),
            Self::Durable(v) => v.revision(),
        }
    }
    fn receipt_pending(&self) -> bool {
        match self {
            Self::Memory(v) => v.receipt_pending(),
            Self::Durable(v) => v.receipt_pending(),
        }
    }
    fn frozen(&self) -> bool {
        matches!(self, Self::Durable(v) if v.is_frozen())
    }
    fn protocol(&mut self, pending: &Pending) -> Option<Vec<u8>> {
        if pending.deadline.remaining().is_err() {
            return if pending.recovery {
                None
            } else {
                let response = match self {
                    Self::Memory(v) => v.deadline_refusal(&pending.bytes).ok()?,
                    Self::Durable(v) => v.deadline_refusal(&pending.bytes).ok()?,
                };
                serde_json::to_vec(&response).ok()
            };
        }
        match (self, pending.recovery) {
            (Self::Memory(v), true) => v.recovery_exact(&pending.bytes).ok(),
            (Self::Durable(v), true) => v.recovery_exact(&pending.bytes).ok(),
            (Self::Memory(v), false) => {
                serde_json::to_vec(&v.apply_exact(&pending.bytes).ok()?).ok()
            }
            (Self::Durable(v), false) => {
                serde_json::to_vec(&v.apply_exact(&pending.bytes).ok()?).ok()
            }
        }
    }
    fn edit(&mut self, state: CalculatorValueState) -> bool {
        match self {
            Self::Memory(v) => v.local_edit(state).is_ok(),
            Self::Durable(v) => v.local_edit(state).is_ok(),
        }
    }
}
pub(super) struct Connection {
    pub sender: mpsc::SyncSender<Command>,
    pub projection: Arc<Mutex<Projection>>,
    pub durable: bool,
}
pub(super) fn start(
    ctx: egui::Context,
    target: CalculatorTargetIdentity,
    lifetime: Option<SessionLifetime>,
) -> io::Result<Connection> {
    if let Some(lifetime) = &lifetime {
        lifetime.check_alive()?;
    }
    let root = std::env::var_os("TRILL_CALCULATOR_STATE_DIR").map(PathBuf::from);
    if lifetime
        .as_ref()
        .is_some_and(|l| l.storage_requirement() == StorageRequirement::DurableRequired)
    {
        CalculatorStore::validate_existing_storage_root(root.as_deref().ok_or_else(|| {
            io::Error::other("Root Calculator lifetime requires durable storage")
        })?)?;
    }
    let document = if let Some(root) = root {
        Document::Durable(CalculatorStore::create(&root, target)?)
    } else {
        Document::Memory(CalculatorDocument::new(target).map_err(io::Error::other)?)
    };
    let durable = matches!(document, Document::Durable(_));
    let projection = Arc::new(Mutex::new(Projection::default()));
    let output = projection.clone();
    let (sender, receiver) = mpsc::sync_channel(4);
    std::thread::Builder::new()
        .name("calculator-document-owner".into())
        .spawn(move || run(document, receiver, output, ctx, lifetime))?;
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
    lifetime: Option<SessionLifetime>,
) {
    let mut projection = Projection::default();
    loop {
        if lifetime.as_ref().is_some_and(SessionLifetime::has_ended) {
            ctx.request_repaint();
            return;
        }
        let command = match receiver.recv_timeout(Duration::from_millis(50)) {
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
                let result = document.protocol(&pending);
                Some((pending.reply, result))
            }
            Command::LocalEdit {
                id,
                revision,
                state,
            } => {
                let accepted = revision == document.revision() && document.edit(state);
                projection.local_result = Some((id, accepted));
                None
            }
        };
        if lifetime.as_ref().is_some_and(SessionLifetime::has_ended) {
            ctx.request_repaint();
            return;
        }
        projection.version = projection.version.saturating_add(1);
        projection.state = document.state().clone();
        projection.revision = document.revision();
        projection.receipt_pending = document.receipt_pending();
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
