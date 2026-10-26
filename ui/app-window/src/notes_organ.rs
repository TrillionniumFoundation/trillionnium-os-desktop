//! Notes' application side of an explicitly inherited private socketpair.
//! No listener, endpoint discovery, signing key, or ordinary Session request
//! can create this channel. The caller of the target must be the registered
//! original Hepta production owner; this child never verifies an invented grant.

use eframe::egui;
use std::io::{self, Read, Write};
use std::os::fd::BorrowedFd;
use std::os::unix::net::{UnixDatagram, UnixStream};
use std::sync::mpsc::{self, SyncSender};
use std::time::{Duration, Instant};
use trill_ui_core::notes::{
    NotesTargetIdentity, MAX_NOTES_REQUEST_BYTES, MAX_NOTES_RESPONSE_BYTES,
};
use trill_ui_core::notes_store::{SavedNotesDocument, SavedNotesListing};

#[path = "notes_worker.rs"]
mod worker;

const APP_HANDOFF_DEADLINE: Duration = Duration::from_secs(1);

struct Pending {
    bytes: Vec<u8>,
    expires_at: Instant,
    recovery: bool,
    reply: SyncSender<Option<Vec<u8>>>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum NotesCloseState {
    Ready,
    Saving,
    Unsaved,
}

pub struct NotesAppChannel {
    worker: worker::Connection,
    version: u64,
    text: String,
    saved_text: String,
    revision: u64,
    accepted_local_revision: Option<(u64, u64)>,
    next_edit: u64,
    pending_edit: Option<u64>,
    deferred_edit: Option<(u64, String)>,
    notice: Option<&'static str>,
    conflicted: bool,
    frozen: bool,
    saved_documents: SavedNotesListing,
    pending_list: Option<u64>,
    pending_restore: Option<u64>,
    list_error: Option<&'static str>,
    close_requested: bool,
    discard_on_close: bool,
    input_queued: bool,
}

impl NotesAppChannel {
    /// A retired Session cannot keep a document owner alive through the
    /// ordinary unsaved-draft close cancellation path.
    pub fn close_if_session_ended(&self, ctx: &egui::Context) -> bool {
        let ended = self
            .worker
            .lifetime
            .as_ref()
            .is_some_and(trill_ui_core::notes_lifetime::SessionLifetime::has_ended);
        if ended {
            ctx.send_viewport_cmd(egui::ViewportCommand::Close);
        }
        ended
    }

    pub fn from_inherited_stdin(
        ctx: egui::Context,
        target: NotesTargetIdentity,
        lifetime: Option<trill_ui_core::notes_lifetime::SessionLifetime>,
    ) -> io::Result<Self> {
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
        let worker = worker::start(ctx.clone(), target, lifetime)?;
        let sender = worker.sender.clone();
        let effect_sender = sender.clone();
        let effect_ctx = ctx.clone();
        std::thread::Builder::new()
            .name("notes-effect-channel".into())
            .spawn(move || serve(effect, effect_sender, effect_ctx, false))?;
        std::thread::Builder::new()
            .name("notes-recovery-channel".into())
            .spawn(move || serve_recovery(recovery, sender, ctx))?;
        Ok(Self::from_worker(worker))
    }

    fn from_worker(worker: worker::Connection) -> Self {
        Self {
            worker,
            version: 0,
            text: String::new(),
            saved_text: String::new(),
            revision: 0,
            accepted_local_revision: None,
            next_edit: 1,
            pending_edit: None,
            deferred_edit: None,
            notice: None,
            conflicted: false,
            frozen: false,
            saved_documents: SavedNotesListing::default(),
            pending_list: None,
            pending_restore: None,
            list_error: None,
            close_requested: false,
            discard_on_close: false,
            input_queued: false,
        }
    }

    /// Copy the bounded document projection without waiting for storage or
    /// transport. Local typing is coalesced while one revision-CAS edit is in
    /// flight; an intervening external effect retains the unsaved draft and
    /// reports a conflict instead of automatically overwriting that effect.
    pub fn poll(&mut self) -> bool {
        let before = self.text.clone();
        let revision_before = self.revision;
        self.accepted_local_revision = None;
        let projection = self
            .worker
            .projection
            .try_lock()
            .ok()
            .map(|value| value.clone());
        if let Some(value) = projection.filter(|value| value.version != self.version) {
            self.version = value.version;
            self.saved_text = value.text.clone();
            self.revision = value.revision;
            self.frozen = value.storage_failed;
            if let Some((_, result)) = value
                .saved_documents
                .as_ref()
                .filter(|(id, _)| self.pending_list == Some(*id))
            {
                self.pending_list = None;
                match result {
                    Ok(listing) => {
                        self.saved_documents = listing.clone();
                        self.list_error = None;
                    }
                    Err(_) => self.list_error = Some("无法读取已保存笔记；原文件保持不变。"),
                }
            }
            let restored = value
                .restore_result
                .as_ref()
                .filter(|(id, _)| self.pending_restore == Some(*id))
                .map(|(_, result)| result.is_ok());
            if restored.is_some() {
                self.pending_restore = None;
            }
            if self.frozen {
                self.notice = Some("保存结果未知；保留当前编辑，需要独立恢复。");
                self.deferred_edit = None;
            } else if let Some(accepted) = restored {
                self.text = value.text;
                self.notice = if accepted {
                    None
                } else {
                    Some("未恢复：文档已变化、仍在使用或无法读取。请刷新后选择，或新建笔记。")
                };
            } else if let Some((_, accepted, revision)) = value
                .local_result
                .filter(|(id, _, _)| self.pending_edit == Some(*id))
            {
                self.pending_edit = None;
                if accepted {
                    self.accepted_local_revision = Some((revision_before, revision));
                }
                if !accepted || (self.deferred_edit.is_some() && value.revision != revision) {
                    self.conflicted = true;
                    self.notice = Some("文档已被其他操作修改；当前编辑尚未保存。");
                    self.deferred_edit = None;
                } else if let Some((base, _)) = &mut self.deferred_edit {
                    *base = revision;
                } else {
                    self.text = value.text;
                }
            } else if self.pending_edit.is_none()
                && self.deferred_edit.is_none()
                && self.notice.is_none()
            {
                self.text = value.text;
            }
        }
        self.flush_edit();
        self.text != before || self.revision != revision_before
    }

    pub fn text(&self) -> &str {
        &self.text
    }

    pub fn revision(&self) -> u64 {
        self.revision
    }

    pub fn accepted_local_revision(&self) -> Option<(u64, u64)> {
        self.accepted_local_revision
    }

    /// Keep the revision observed before IME composition. A concurrent external
    /// effect must never silently become the composition's new CAS base.
    pub fn local_edit_at(&mut self, revision: u64, text: String) -> bool {
        if self.frozen
            || self.pending_restore.is_some()
            || text.len() > trill_ui_core::notes::MAX_NOTES_TEXT_BYTES
        {
            return false;
        }
        self.text = text.clone();
        if self.conflicted || revision != self.revision {
            self.conflicted = true;
            self.notice = Some("文档已被其他操作修改；当前编辑尚未保存。");
            self.deferred_edit = None;
            return true;
        }
        self.notice = None;
        self.deferred_edit = Some((revision, text));
        self.flush_edit();
        true
    }

    pub fn has_conflict(&self) -> bool {
        self.conflicted && !self.frozen
    }

    pub fn keep_local_after_conflict(&mut self) {
        if self.has_conflict() && self.pending_edit.is_none() && self.pending_restore.is_none() {
            self.conflicted = false;
            self.notice = None;
            self.local_edit_at(self.revision, self.text.clone());
        }
    }

    pub fn discard_local_after_conflict(&mut self) {
        if self.has_conflict() && self.pending_edit.is_none() && self.pending_restore.is_none() {
            self.text = self.saved_text.clone();
            self.conflicted = false;
            self.notice = None;
            self.deferred_edit = None;
        }
    }

    pub fn has_document_storage(&self) -> bool {
        self.worker.durable
    }

    pub fn restore_pending(&self) -> bool {
        self.pending_restore.is_some()
    }

    pub fn can_restore_saved(&self) -> bool {
        self.worker.durable
            && !self.frozen
            && self.revision == 0
            && self.text.is_empty()
            && self.pending_edit.is_none()
            && self.deferred_edit.is_none()
            && self.pending_restore.is_none()
    }

    pub fn saved_documents(&self) -> &SavedNotesListing {
        &self.saved_documents
    }

    pub fn saved_list_pending(&self) -> bool {
        self.pending_list.is_some()
    }

    pub fn saved_list_error(&self) -> Option<&'static str> {
        self.list_error
    }

    pub fn refresh_saved_documents(&mut self) {
        if !self.worker.durable || self.pending_list.is_some() {
            return;
        }
        let Some(id) = self.next_request_id() else {
            return;
        };
        match self
            .worker
            .sender
            .try_send(worker::Command::ListSaved { id })
        {
            Ok(()) => {
                self.pending_list = Some(id);
                self.list_error = None;
            }
            Err(_) => self.list_error = Some("笔记读取暂不可用，请稍后刷新。"),
        }
    }

    pub fn restore_saved_document(&mut self, source: SavedNotesDocument) -> bool {
        if !self.can_restore_saved() {
            return false;
        }
        let Some(id) = self.next_request_id() else {
            return false;
        };
        match self.worker.sender.try_send(worker::Command::RestoreSaved {
            id,
            revision: self.revision,
            source,
        }) {
            Ok(()) => {
                self.pending_restore = Some(id);
                self.notice = None;
                true
            }
            Err(_) => {
                self.notice = Some("保存通道暂不可用；尚未开始恢复，请稍后重试。");
                false
            }
        }
    }

    fn next_request_id(&mut self) -> Option<u64> {
        let next = self.next_edit.checked_add(1)?;
        let id = self.next_edit;
        self.next_edit = next;
        Some(id)
    }

    /// A native close request is held until the worker confirms the last
    /// accepted local edit was synced. Storage uncertainty or a CAS conflict
    /// keeps the draft visible until the user explicitly discards it.
    pub fn close_state(&self) -> NotesCloseState {
        if !self.worker.durable || self.discard_on_close {
            NotesCloseState::Ready
        } else if self.frozen {
            NotesCloseState::Unsaved
        } else if self.input_queued
            || self.pending_edit.is_some()
            || self.deferred_edit.is_some()
            || self.pending_restore.is_some()
        {
            NotesCloseState::Saving
        } else if self.text != self.saved_text {
            NotesCloseState::Unsaved
        } else {
            NotesCloseState::Ready
        }
    }

    pub fn input_queue_changed(&mut self, queued: bool) {
        self.input_queued = queued;
    }

    pub fn close_requested(&self) -> bool {
        self.close_requested
    }

    pub fn keep_open(&mut self) {
        self.close_requested = false;
        self.discard_on_close = false;
    }

    pub fn discard_and_close(&mut self) {
        self.discard_on_close = true;
        self.close_requested = true;
    }

    /// Called after editor events are submitted, including a final edit and
    /// close in the same frame. It never waits on transport or filesystem I/O.
    pub fn handle_close(&mut self, ctx: &egui::Context) {
        self.close_requested |= ctx.input(|input| input.viewport().close_requested());
        if self.close_requested {
            if self.close_state() == NotesCloseState::Ready {
                ctx.send_viewport_cmd(egui::ViewportCommand::Close);
            } else {
                ctx.send_viewport_cmd(egui::ViewportCommand::CancelClose);
                ctx.request_repaint_after(Duration::from_millis(25));
            }
        }
    }

    pub fn storage_status(&self) -> &'static str {
        if let Some(notice) = self.notice {
            return notice;
        }
        if self.pending_edit.is_some() || self.deferred_edit.is_some() {
            return "正在保存编辑……";
        }
        if self.pending_restore.is_some() {
            return "正在打开已保存笔记的副本……";
        }
        if self.worker.durable {
            "已保存到本机；旧操作可独立回读。"
        } else {
            "临时笔记：关闭窗口后不会保存。"
        }
    }

    fn flush_edit(&mut self) {
        if self.frozen || self.pending_edit.is_some() {
            return;
        }
        let Some((revision, text)) = self.deferred_edit.take() else {
            return;
        };
        if revision != self.revision {
            self.conflicted = true;
            self.notice = Some("文档已被其他操作修改；当前编辑尚未保存。");
            return;
        }
        let Some(next) = self.next_edit.checked_add(1) else {
            self.frozen = true;
            return;
        };
        let id = self.next_edit;
        match self
            .worker
            .sender
            .try_send(worker::Command::LocalEdit { id, revision, text })
        {
            Ok(()) => {
                self.pending_edit = Some(id);
                self.next_edit = next;
            }
            Err(mpsc::TrySendError::Full(worker::Command::LocalEdit {
                revision, text, ..
            })) => {
                self.deferred_edit = Some((revision, text));
            }
            Err(_) => {
                self.frozen = true;
                self.notice = Some("笔记进程连接中断；编辑尚未保存。");
            }
        }
    }
}

fn serve(
    mut stream: UnixStream,
    sender: SyncSender<worker::Command>,
    ctx: egui::Context,
    recovery: bool,
) {
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
            .try_send(worker::Command::Protocol(Pending {
                bytes,
                recovery,
                expires_at,
                reply,
            }))
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
fn serve_recovery(channel: UnixDatagram, sender: SyncSender<worker::Command>, ctx: egui::Context) {
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
            .try_send(worker::Command::Protocol(Pending {
                bytes: buffer[..length].to_vec(),
                recovery: true,
                expires_at: Instant::now() + APP_HANDOFF_DEADLINE,
                reply,
            }))
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

#[cfg(test)]
#[path = "notes_close_tests.rs"]
mod close_tests;
