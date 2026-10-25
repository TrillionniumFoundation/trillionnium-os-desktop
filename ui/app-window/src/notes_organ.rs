//! Private application channels. The GUI thread owns the document and its
//! durable state; neither socket is reachable through public Session IPC.
use eframe::egui;
use std::io::{self, Read, Write};
use std::net::Shutdown;
use std::os::fd::{BorrowedFd, FromRawFd, OwnedFd};
use std::os::unix::net::{UnixDatagram, UnixStream};
use std::path::Path;
use std::sync::mpsc::{self, Receiver, SyncSender};
use std::time::{Duration, Instant};
use trill_ui_core::notes::{
    persistence::{ensure_private_directory, DurableNotes},
    NotesDocument, NotesObserve, NotesTargetIdentity, MAX_NOTES_REQUEST_BYTES,
    MAX_NOTES_RESPONSE_BYTES,
};

const APP_HANDOFF_DEADLINE: Duration = Duration::from_secs(1);
#[derive(Clone, Copy)]
enum ChannelKind {
    Effect,
    Recovery,
}
struct Pending {
    bytes: Vec<u8>,
    kind: ChannelKind,
    expires_at: Instant,
    reply: SyncSender<Option<Vec<u8>>>,
}

enum Document {
    Volatile(NotesDocument),
    Durable(DurableNotes),
}
impl Document {
    fn text(&self) -> &str {
        match self {
            Self::Volatile(d) => d.text(),
            Self::Durable(d) => d.text(),
        }
    }
    fn revision(&self) -> u64 {
        match self {
            Self::Volatile(d) => d.revision(),
            Self::Durable(d) => d.revision(),
        }
    }
    fn apply(&mut self, bytes: &[u8], kind: ChannelKind) -> Option<Vec<u8>> {
        match self {
            Self::Durable(d) => match kind {
                ChannelKind::Effect => d
                    .apply_exact_bytes(bytes)
                    .or_else(|_| d.observe_exact_bytes(bytes))
                    .ok(),
                ChannelKind::Recovery => d
                    .observe_exact_bytes(bytes)
                    .or_else(|_| d.acknowledge_exact_bytes(bytes))
                    .or_else(|_| d.read_document_state(bytes))
                    .ok(),
            },
            Self::Volatile(d) => {
                if matches!(kind, ChannelKind::Recovery) {
                    return None;
                }
                let response = d
                    .apply_exact(bytes)
                    .or_else(|_| NotesObserve::parse_exact(bytes).and_then(|q| d.observe(&q)))
                    .ok()?;
                serde_json::to_vec(&response).ok()
            }
        }
    }
}

pub struct NotesAppChannel {
    document: Document,
    requests: Receiver<Pending>,
    storage_error: bool,
}
impl NotesAppChannel {
    pub fn from_inherited_stdin(
        ctx: egui::Context,
        target: NotesTargetIdentity,
    ) -> io::Result<Self> {
        let document = match (
            std::env::var_os("TRILL_NOTES_STORE_DIR"),
            std::env::var("TRILL_NOTES_STORE_MODE").ok(),
        ) {
            (Some(path), Some(mode)) => {
                let path = Path::new(&path);
                let store = match mode.as_str() {
                    "create" => {
                        ensure_private_directory(
                            path.parent()
                                .ok_or_else(|| io::Error::other("Notes storage parent"))?,
                        )?;
                        DurableNotes::create(path, target)?
                    }
                    "reopen" => DurableNotes::reopen(path, target)?,
                    _ => return Err(io::Error::other("invalid trusted Notes storage mode")),
                };
                Document::Durable(store)
            }
            (None, None) => Document::Volatile(
                NotesDocument::new(target)
                    .map_err(|_| io::Error::other("notes target identity"))?,
            ),
            _ => {
                return Err(io::Error::other(
                    "partial trusted Notes storage configuration",
                ))
            }
        };
        let fd = unsafe { BorrowedFd::borrow_raw(0) }.try_clone_to_owned()?;
        let stream = UnixStream::from(fd);
        if !stream.local_addr()?.is_unnamed() || !stream.peer_addr()?.is_unnamed() {
            return Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                "notes requires inherited socketpair",
            ));
        }
        let (sender, requests) = mpsc::sync_channel(8);
        if let Some(fd) = std::env::var_os("TRILL_NOTES_RECOVERY_FD") {
            if !matches!(document, Document::Durable(_)) {
                return Err(io::Error::other("recovery requires durable Notes"));
            }
            let fd: i32 = fd
                .to_str()
                .and_then(|s| s.parse().ok())
                .filter(|fd| *fd >= 3)
                .ok_or_else(|| io::Error::other("invalid private Notes recovery descriptor"))?;
            let mut socket_type: libc::c_int = 0;
            let mut length = std::mem::size_of_val(&socket_type) as libc::socklen_t;
            if unsafe {
                libc::getsockopt(
                    fd,
                    libc::SOL_SOCKET,
                    libc::SO_TYPE,
                    (&mut socket_type as *mut libc::c_int).cast(),
                    &mut length,
                )
            } != 0
                || socket_type != libc::SOCK_DGRAM
            {
                return Err(io::Error::other(
                    "private recovery descriptor is not a datagram socket",
                ));
            }
            // The trusted launcher transferred this descriptor to this child;
            // take its ownership exactly once and restore close-on-exec.
            if unsafe { libc::fcntl(fd, libc::F_SETFD, libc::FD_CLOEXEC) } < 0 {
                return Err(io::Error::last_os_error());
            }
            let recovery = UnixDatagram::from(unsafe { OwnedFd::from_raw_fd(fd) });
            if !recovery.local_addr()?.is_unnamed() || !recovery.peer_addr()?.is_unnamed() {
                return Err(io::Error::other("recovery requires private datagram pair"));
            }
            let recovery_sender = sender.clone();
            let recovery_ctx = ctx.clone();
            std::thread::Builder::new()
                .name("notes-private-recovery".into())
                .spawn(move || serve_recovery(recovery, recovery_sender, recovery_ctx))?;
        }
        std::thread::Builder::new()
            .name("notes-private-channel".into())
            .spawn(move || serve(stream, sender, ctx))?;
        Ok(Self {
            document,
            requests,
            storage_error: false,
        })
    }

    pub fn poll(&mut self) -> bool {
        let before = self.document.revision();
        // No unbounded queue; every accepted request has a total GUI handoff expiry.
        for _ in 0..8 {
            let Ok(pending) = self.requests.try_recv() else {
                break;
            };
            if Instant::now() >= pending.expires_at {
                let _ = pending.reply.try_send(None);
                continue;
            }
            let response = self.document.apply(&pending.bytes, pending.kind);
            if let Document::Durable(d) = &self.document {
                self.storage_error |= d.is_poisoned();
            }
            let _ = pending.reply.try_send(response);
        }
        self.document.revision() != before
    }
    pub fn text(&self) -> &str {
        self.document.text()
    }
    pub fn revision(&self) -> u64 {
        self.document.revision()
    }
    pub fn is_durable(&self) -> bool {
        matches!(self.document, Document::Durable(_))
    }
    pub fn storage_error(&self) -> bool {
        self.storage_error
    }
    pub fn local_edit(&mut self, text: String) -> bool {
        let result = match &mut self.document {
            Document::Volatile(d) => d.local_edit(text).is_ok(),
            Document::Durable(d) => d.local_edit(text).is_ok(),
        };
        if let Document::Durable(d) = &self.document {
            self.storage_error |= d.is_poisoned();
        }
        result
    }
}

fn handoff(
    bytes: Vec<u8>,
    kind: ChannelKind,
    sender: &SyncSender<Pending>,
    ctx: &egui::Context,
) -> Option<Vec<u8>> {
    let (reply, receive) = mpsc::sync_channel(1);
    sender
        .try_send(Pending {
            bytes,
            kind,
            expires_at: Instant::now() + APP_HANDOFF_DEADLINE,
            reply,
        })
        .ok()?;
    ctx.request_repaint();
    receive.recv_timeout(APP_HANDOFF_DEADLINE).ok().flatten()
}
fn remaining(deadline: Instant) -> io::Result<Duration> {
    deadline
        .checked_duration_since(Instant::now())
        .filter(|d| !d.is_zero())
        .ok_or_else(|| io::Error::new(io::ErrorKind::TimedOut, "Notes total frame deadline"))
}
fn read_until(stream: &mut UnixStream, mut bytes: &mut [u8], deadline: Instant) -> io::Result<()> {
    while !bytes.is_empty() {
        stream.set_read_timeout(Some(remaining(deadline)?))?;
        match stream.read(bytes) {
            Ok(0) => return Err(io::ErrorKind::UnexpectedEof.into()),
            Ok(n) => bytes = &mut bytes[n..],
            Err(e) if e.kind() == io::ErrorKind::Interrupted => {}
            Err(e) => return Err(e),
        }
    }
    Ok(())
}
struct EffectConnection(UnixStream);

impl Drop for EffectConnection {
    fn drop(&mut self) {
        // stdin still owns an alias of the inherited socket. Closing only the
        // worker's cloned fd would hide its exit from the owner. Shut down the
        // socket itself on every return path; recovery has its own endpoint.
        let _ = self.0.shutdown(Shutdown::Both);
    }
}

fn serve(stream: UnixStream, sender: SyncSender<Pending>, ctx: egui::Context) {
    let mut connection = EffectConnection(stream);
    serve_effect(&mut connection.0, sender, ctx);
}

fn serve_effect(stream: &mut UnixStream, sender: SyncSender<Pending>, ctx: egui::Context) {
    loop {
        let mut prefix = [0u8; 4];
        // Idle wait owns only this channel's dedicated thread. Once the first
        // byte arrives, prefix plus body share one nonrenewable deadline.
        let _ = stream.set_read_timeout(None);
        if stream.read_exact(&mut prefix[..1]).is_err() {
            return;
        }
        let deadline = Instant::now() + APP_HANDOFF_DEADLINE;
        if read_until(stream, &mut prefix[1..], deadline).is_err() {
            return;
        }
        let length = u32::from_be_bytes(prefix) as usize;
        if length == 0 || length > MAX_NOTES_REQUEST_BYTES {
            return;
        }
        let mut bytes = vec![0u8; length];
        if read_until(stream, &mut bytes, deadline).is_err() {
            return;
        }
        let Some(raw) = handoff(bytes, ChannelKind::Effect, &sender, &ctx) else {
            return;
        };
        if raw.is_empty() || raw.len() > MAX_NOTES_RESPONSE_BYTES {
            return;
        }
        let mut frame = (raw.len() as u32).to_be_bytes().to_vec();
        frame.extend_from_slice(&raw);
        let mut bytes = frame.as_slice();
        let deadline = Instant::now() + APP_HANDOFF_DEADLINE;
        while !bytes.is_empty() {
            let Ok(left) = remaining(deadline) else {
                return;
            };
            if stream.set_write_timeout(Some(left)).is_err() {
                return;
            }
            match stream.write(bytes) {
                Ok(0) => return,
                Ok(n) => bytes = &bytes[n..],
                Err(e) if e.kind() == io::ErrorKind::Interrupted => {}
                Err(_) => return,
            }
        }
    }
}
fn serve_recovery(channel: UnixDatagram, sender: SyncSender<Pending>, ctx: egui::Context) {
    loop {
        let mut bytes = [0u8; MAX_NOTES_REQUEST_BYTES + 1];
        let Ok(count) = channel.recv(&mut bytes) else {
            return;
        };
        if count == 0 || count > MAX_NOTES_REQUEST_BYTES {
            continue;
        }
        let Some(raw) = handoff(
            bytes[..count].to_vec(),
            ChannelKind::Recovery,
            &sender,
            &ctx,
        ) else {
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
        if channel.send(&raw).is_err() {
            return;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn assert_effect_exit_disconnects_alias(frame: &[u8]) {
        let (mut owner, child) = UnixStream::pair().unwrap();
        // Reproduce the original stdin alias that outlives the effect worker.
        let inherited_stdin = child.try_clone().unwrap();
        let (sender, _requests) = mpsc::sync_channel(8);
        let worker = std::thread::spawn(move || serve(child, sender, egui::Context::default()));
        owner
            .set_read_timeout(Some(Duration::from_secs(3)))
            .unwrap();
        owner.write_all(frame).unwrap();
        let mut reply = [0u8; 1];
        assert_eq!(owner.read(&mut reply).unwrap(), 0);
        worker.join().unwrap();
        // The alias is deliberately still open when EOF must be visible.
        assert!(inherited_stdin.peer_addr().unwrap().is_unnamed());
    }

    #[test]
    fn effect_worker_exit_disconnects_stdin_alias_on_handoff_timeout() {
        // No GUI polls the accepted request. The bounded handoff expires.
        assert_effect_exit_disconnects_alias(&[0, 0, 0, 1, b'x']);
    }

    #[test]
    fn effect_worker_exit_disconnects_stdin_alias_on_invalid_frame() {
        assert_effect_exit_disconnects_alias(&0u32.to_be_bytes());
    }
}
