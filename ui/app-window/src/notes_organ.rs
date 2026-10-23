//! Notes' application side of an explicitly inherited private socketpair.
//! No listener, endpoint discovery, signing key, or ordinary Session request
//! can create this channel. The caller of the target must be the registered
//! original Hepta production owner; this child never verifies an invented grant.

use eframe::egui;
use std::io::{self, Read, Write};
use std::os::fd::BorrowedFd;
use std::os::unix::net::{UnixDatagram, UnixStream};
use std::sync::mpsc::{self, Receiver, SyncSender};
use std::time::{Duration, Instant};
use trill_ui_core::notes::{
    NotesDocument, NotesTargetIdentity, MAX_NOTES_REQUEST_BYTES, MAX_NOTES_RESPONSE_BYTES,
};

const APP_HANDOFF_DEADLINE: Duration = Duration::from_secs(1);

struct Pending {
    bytes: Vec<u8>,
    expires_at: Instant,
    recovery: bool,
    reply: SyncSender<Option<Vec<u8>>>,
}

pub struct NotesAppChannel {
    document: NotesDocument,
    requests: Receiver<Pending>,
}

impl NotesAppChannel {
    pub fn from_inherited_stdin(
        ctx: egui::Context,
        target: NotesTargetIdentity,
    ) -> io::Result<Self> {
        let document = NotesDocument::new(target.clone())
            .map_err(|_| io::Error::new(io::ErrorKind::InvalidInput, "notes target identity"))?;
        // stdin is a known, process-owned descriptor. Duplicate it before
        // constructing UnixStream; dropping this worker never closes stdin.
        // No caller-supplied descriptor integer or path is accepted.
        let fd = unsafe { BorrowedFd::borrow_raw(0) }.try_clone_to_owned()?;
        let bootstrap = UnixDatagram::from(fd);
        let (raw, effect, recovery) =
            trill_ui_core::notes_private_unix::receive_channels(&bootstrap, APP_HANDOFF_DEADLINE)?;
        let offered: NotesTargetIdentity =
            serde_json::from_slice(&raw).map_err(io::Error::other)?;
        if offered != target {
            return Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                "Notes app handoff identity mismatch",
            ));
        }
        let (sender, requests) = mpsc::sync_channel(2);
        let effect_sender = sender.clone();
        let effect_ctx = ctx.clone();
        std::thread::Builder::new()
            .name("notes-effect-channel".into())
            .spawn(move || serve(effect, effect_sender, effect_ctx, false))?;
        std::thread::Builder::new()
            .name("notes-recovery-channel".into())
            .spawn(move || serve_recovery(recovery, sender, ctx))?;
        Ok(Self { document, requests })
    }

    /// Called only on the same egui thread as local text edits. A stalled GUI
    /// cannot accumulate unbounded delayed mutations; expired handoffs are
    /// discarded before touching the document. Once applied, a lost reply
    /// remains an unknown outcome for the owner, never a rollback claim.
    pub fn poll(&mut self) -> bool {
        let before = self.document.revision();
        while let Ok(pending) = self.requests.try_recv() {
            if Instant::now() >= pending.expires_at {
                let _ = pending.reply.try_send(None);
                continue;
            }
            let result = if pending.recovery {
                self.document.recovery_exact(&pending.bytes)
            } else {
                self.document
                    .apply_exact(&pending.bytes)
                    .and_then(|response| {
                        serde_json::to_vec(&response)
                            .map_err(|_| trill_ui_core::notes::NotesProtocolError::Receipt)
                    })
            };
            let _ = pending.reply.try_send(result.ok());
        }
        self.document.revision() != before
    }

    pub fn text(&self) -> &str {
        self.document.text()
    }

    pub fn revision(&self) -> u64 {
        self.document.revision()
    }

    pub fn local_edit(&mut self, text: String) -> bool {
        self.document.local_edit(text).is_ok()
    }
}

fn serve(mut stream: UnixStream, sender: SyncSender<Pending>, ctx: egui::Context, recovery: bool) {
    // This thread handles a single serial private channel. Its only allocation
    // based on peer data follows the fixed length bound, and only one pending
    // GUI handoff may exist. Idle blocking does not occupy the egui thread.
    loop {
        let mut prefix = [0u8; 4];
        if stream.read_exact(&mut prefix).is_err() {
            return;
        }
        let length = u32::from_be_bytes(prefix) as usize;
        if length == 0 || length > MAX_NOTES_REQUEST_BYTES {
            return;
        }
        let mut bytes = vec![0u8; length];
        if stream.set_read_timeout(Some(APP_HANDOFF_DEADLINE)).is_err()
            || stream.read_exact(&mut bytes).is_err()
        {
            return;
        }
        let _ = stream.set_read_timeout(None);
        let (reply, receive) = mpsc::sync_channel(1);
        let expires_at = Instant::now() + APP_HANDOFF_DEADLINE;
        if sender
            .try_send(Pending {
                bytes,
                recovery,
                expires_at,
                reply,
            })
            .is_err()
        {
            return;
        }
        ctx.request_repaint();
        let Ok(Some(raw)) = receive.recv_timeout(APP_HANDOFF_DEADLINE) else {
            return;
        };
        if raw.is_empty() || raw.len() > MAX_NOTES_RESPONSE_BYTES {
            return;
        }
        if stream
            .set_write_timeout(Some(APP_HANDOFF_DEADLINE))
            .is_err()
            || stream.write_all(&(raw.len() as u32).to_be_bytes()).is_err()
            || stream.write_all(&raw).is_err()
        {
            return;
        }
    }
}

// Datagram boundaries survive a lost response. Retrying an exact retirement
// is safe because the model retains its last retirement identity. This lane
// never calls the mutation parser, even when the peer sends replace_note.
fn serve_recovery(channel: UnixDatagram, sender: SyncSender<Pending>, ctx: egui::Context) {
    let mut buffer = [0_u8; MAX_NOTES_REQUEST_BYTES + 1];
    loop {
        let Ok(length) = channel.recv(&mut buffer) else {
            return;
        };
        if length == 0 || length > MAX_NOTES_REQUEST_BYTES {
            continue;
        }
        let (reply, receive) = mpsc::sync_channel(1);
        if sender
            .try_send(Pending {
                bytes: buffer[..length].to_vec(),
                recovery: true,
                expires_at: Instant::now() + APP_HANDOFF_DEADLINE,
                reply,
            })
            .is_err()
        {
            continue;
        }
        ctx.request_repaint();
        let Ok(Some(raw)) = receive.recv_timeout(APP_HANDOFF_DEADLINE) else {
            continue;
        };
        if raw.is_empty() || raw.len() > MAX_NOTES_RESPONSE_BYTES {
            continue;
        }
        if channel
            .set_write_timeout(Some(APP_HANDOFF_DEADLINE))
            .is_err()
        {
            return;
        }
        // A lost acknowledgement does not close the observation lane or drop
        // the document's pending receipt. The exact request can be repeated.
        let _ = channel.send(&raw);
    }
}
