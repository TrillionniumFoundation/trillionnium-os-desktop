//! Notes' application side of an explicitly inherited private socketpair.
//! No listener, endpoint discovery, signing key, or ordinary Session request
//! can create this channel. The caller of the target must be the registered
//! original Hepta production owner; this child never verifies an invented grant.

use eframe::egui;
use std::io::{self, Read, Write};
use std::os::fd::BorrowedFd;
use std::os::unix::net::{UnixDatagram, UnixStream};
use std::sync::mpsc::{self, SyncSender};
use std::sync::Arc;
use std::time::{Duration, Instant};
use trill_ui_core::notes::{
    NotesTargetIdentity, MAX_NOTES_REQUEST_BYTES, MAX_NOTES_RESPONSE_BYTES,
};
use trill_ui_core::notes_store::{SavedNote, SavedNotes};

#[path = "notes_worker.rs"]
mod worker;

const APP_HANDOFF_DEADLINE: Duration = Duration::from_secs(1);

struct Pending {
    bytes: Vec<u8>,
    expires_at: Instant,
    recovery: bool,
    reply: SyncSender<Option<Vec<u8>>>,
}

pub struct NotesAppChannel {
    worker: worker::Connection,
    version: u64,
    text: String,
    saved_text: String,
    revision: u64,
    next_edit: u64,
    pending_edit: Option<u64>,
    deferred_edit: Option<(u64, String)>,
    notice: Option<&'static str>,
    conflicted: bool,
    frozen: bool,
    saved: Arc<SavedNotes>,
    saved_request: Option<u64>,
    reopen_request: Option<u64>,
    saved_notice: Option<String>,
}

impl NotesAppChannel {
    pub fn from_inherited_stdin(
        ctx: egui::Context,
        target: NotesTargetIdentity,
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
        let worker = worker::start(ctx.clone(), target)?;
        let sender = worker.sender.clone();
        let effect_sender = sender.clone();
        let effect_ctx = ctx.clone();
        std::thread::Builder::new()
            .name("notes-effect-channel".into())
            .spawn(move || serve(effect, effect_sender, effect_ctx, false))?;
        std::thread::Builder::new()
            .name("notes-recovery-channel".into())
            .spawn(move || serve_recovery(recovery, sender, ctx))?;
        Ok(Self {
            worker,
            version: 0,
            text: String::new(),
            saved_text: String::new(),
            revision: 0,
            next_edit: 1,
            pending_edit: None,
            deferred_edit: None,
            notice: None,
            conflicted: false,
            frozen: false,
            saved: Arc::new(SavedNotes::default()),
            saved_request: None,
            reopen_request: None,
            saved_notice: None,
        })
    }

    /// Copy the bounded document projection without waiting for storage or
    /// transport. Local typing is coalesced while one revision-CAS edit is in
    /// flight; an intervening external effect retains the unsaved draft and
    /// reports a conflict instead of automatically overwriting that effect.
    pub fn poll(&mut self) -> bool {
        let before = self.text.clone();
        let revision_before = self.revision;
        let projection = self
            .worker
            .projection
            .try_lock()
            .ok()
            .map(|value| value.clone());
        if let Some(value) = projection.filter(|value| value.version != self.version) {
            self.version = value.version;
            self.revision = value.revision;
            self.saved_text = value.text.clone();
            self.frozen = value.storage_failed;
            if let Some((_, result)) = value
                .saved_result
                .filter(|(id, _)| self.saved_request == Some(*id))
            {
                self.saved_request = None;
                match result {
                    Ok(saved) => {
                        self.saved = saved;
                        self.saved_notice = None;
                    }
                    Err(error) => {
                        self.saved_notice = Some(format!("无法读取已保存的笔记：{error}"))
                    }
                }
            }
            if let Some((_, result)) = value
                .reopen_result
                .filter(|(id, _)| self.reopen_request == Some(*id))
            {
                self.reopen_request = None;
                match result {
                    Ok(()) => {
                        self.text = value.text.clone();
                        self.saved_notice = None;
                    }
                    Err(error) => {
                        self.saved_notice =
                            Some(format!("未打开旧笔记；原文保留，请刷新后重试：{error}"))
                    }
                }
            }
            if self.frozen {
                self.notice = Some("保存结果未知；保留当前编辑，需要独立恢复。");
                self.deferred_edit = None;
            } else if let Some((_, accepted, revision)) = value
                .local_result
                .filter(|(id, _, _)| self.pending_edit == Some(*id))
            {
                self.pending_edit = None;
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

    /// IME commits retain the revision observed before composition. An effect
    /// received while the editor was composing cannot silently become its base.
    pub fn local_edit_at(&mut self, revision: u64, text: String) -> bool {
        if !self.can_edit() || text.len() > trill_ui_core::notes::MAX_NOTES_TEXT_BYTES {
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

    pub fn storage_status(&self) -> &'static str {
        if let Some(notice) = self.notice {
            return notice;
        }
        if self.pending_edit.is_some() || self.deferred_edit.is_some() {
            return "正在保存编辑……";
        }
        if self.reopen_request.is_some() {
            return "正在打开已保存的笔记……";
        }
        if self.worker.durable {
            "已保存到本机；旧操作可独立回读。"
        } else {
            "临时笔记：关闭窗口后不会保存。"
        }
    }

    pub fn is_durable(&self) -> bool {
        self.worker.durable
    }

    pub fn can_edit(&self) -> bool {
        !self.frozen && self.reopen_request.is_none()
    }

    pub fn has_conflict(&self) -> bool {
        self.conflicted && !self.frozen
    }

    /// Only an explicit user choice can rebase an unsaved conflicting draft.
    /// The worker still compares this observed revision before committing it.
    pub fn keep_local_after_conflict(&mut self) {
        if !self.has_conflict() || !self.can_edit() || self.pending_edit.is_some() {
            return;
        }
        self.conflicted = false;
        self.notice = None;
        self.local_edit_at(self.revision, self.text.clone());
    }

    pub fn discard_local_after_conflict(&mut self) {
        if !self.has_conflict() || !self.can_edit() || self.pending_edit.is_some() {
            return;
        }
        self.text = self.saved_text.clone();
        self.conflicted = false;
        self.notice = None;
        self.deferred_edit = None;
    }

    pub fn can_reopen(&self) -> bool {
        self.worker.durable
            && self.can_edit()
            && self.revision == 0
            && self.text.is_empty()
            && self.pending_edit.is_none()
            && self.deferred_edit.is_none()
            && self.notice.is_none()
    }

    pub fn saved_notes(&self) -> &[SavedNote] {
        &self.saved.entries
    }

    pub fn unavailable_saved_notes(&self) -> usize {
        self.saved.unavailable
    }

    pub fn saved_notice(&self) -> Option<&str> {
        self.saved_notice.as_deref()
    }

    pub fn saved_notes_loading(&self) -> bool {
        self.saved_request.is_some()
    }

    pub fn refresh_saved_notes(&mut self) {
        if !self.worker.durable || self.frozen || self.saved_request.is_some() {
            return;
        }
        let Some(next) = self.next_edit.checked_add(1) else {
            return;
        };
        let id = self.next_edit;
        match self
            .worker
            .sender
            .try_send(worker::Command::ListSaved { id })
        {
            Ok(()) => {
                self.next_edit = next;
                self.saved_request = Some(id);
            }
            Err(_) => self.saved_notice = Some("笔记正在处理其他操作，请稍后刷新。".into()),
        }
    }

    pub fn reopen_saved_note(&mut self, index: usize) -> bool {
        if !self.can_reopen() {
            return false;
        }
        let Some(source) = self.saved.entries.get(index).cloned() else {
            return false;
        };
        let Some(next) = self.next_edit.checked_add(1) else {
            return false;
        };
        let id = self.next_edit;
        match self.worker.sender.try_send(worker::Command::ReopenSaved {
            id,
            revision: self.revision,
            source,
        }) {
            Ok(()) => {
                self.next_edit = next;
                self.reopen_request = Some(id);
                true
            }
            Err(_) => {
                self.saved_notice = Some("笔记正在处理其他操作，请稍后重试。".into());
                false
            }
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
mod editor_tests {
    use super::*;
    use std::sync::Mutex;

    #[test]
    fn commit_from_an_older_composition_retains_unsaved_text_without_queueing_an_overwrite() {
        let (sender, receiver) = mpsc::sync_channel(4);
        let projection = Arc::new(Mutex::new(worker::Projection::default()));
        let mut channel = NotesAppChannel {
            worker: worker::Connection {
                sender,
                projection: projection.clone(),
                durable: true,
            },
            version: 0,
            text: "external effect".into(),
            saved_text: "external effect".into(),
            revision: 5,
            next_edit: 1,
            pending_edit: None,
            deferred_edit: None,
            notice: None,
            conflicted: false,
            frozen: false,
            saved: Arc::new(SavedNotes::default()),
            saved_request: None,
            reopen_request: None,
            saved_notice: None,
        };
        assert!(channel.local_edit_at(4, "我的输入".into()));
        assert_eq!(channel.text(), "我的输入");
        assert_eq!(channel.revision(), 5);
        assert!(channel.storage_status().contains("尚未保存"));
        assert!(receiver.try_recv().is_err());
        *projection.lock().unwrap() = worker::Projection {
            version: 1,
            text: "another external observation".into(),
            revision: 6,
            ..Default::default()
        };
        channel.poll();
        assert_eq!(channel.text(), "我的输入");
        assert_eq!(channel.revision(), 6);
        assert!(!channel.can_reopen());
        assert!(receiver.try_recv().is_err());
        assert!(channel.local_edit_at(6, "我的输入继续编辑".into()));
        assert!(channel.has_conflict());
        assert!(receiver.try_recv().is_err());
        channel.keep_local_after_conflict();
        assert!(!channel.has_conflict());
        match receiver.try_recv().unwrap() {
            worker::Command::LocalEdit { revision, text, .. } => {
                assert_eq!(revision, 6);
                assert_eq!(text, "我的输入继续编辑");
            }
            _ => panic!("explicit conflict resolution must use the existing local CAS worker"),
        }
    }
}
