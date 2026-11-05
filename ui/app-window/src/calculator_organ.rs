//! Private Calculator channels. One state worker persists causal receipts;
//! rendering and transport threads cannot issue grants, mutate or replay effects.

use eframe::egui;
use std::io::{self, Read, Write};
use std::net::Shutdown;
use std::os::fd::BorrowedFd;
use std::os::unix::net::{UnixDatagram, UnixStream};
use std::sync::mpsc::{self, SyncSender};
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;
use std::time::Duration;
use trill_ui_core::calculator::{
    CalculatorTargetIdentity, CalculatorValueState, MAX_CALCULATOR_REQUEST_BYTES,
    MAX_CALCULATOR_RESPONSE_BYTES,
};
use trill_ui_core::calculator_lifetime::{boottime_nanos, SessionLifetime};

#[path = "calculator_worker.rs"]
mod worker;

const HANDOFF_BUDGET: Duration = Duration::from_secs(1);

#[derive(Clone, Copy)]
struct Deadline(u64);
impl Deadline {
    fn new() -> io::Result<Self> {
        boottime_nanos()?
            .checked_add(HANDOFF_BUDGET.as_nanos() as u64)
            .map(Self)
            .ok_or_else(|| io::Error::other("Calculator deadline overflow"))
    }
    fn remaining(self) -> io::Result<Duration> {
        self.0
            .checked_sub(boottime_nanos()?)
            .filter(|n| *n > 0)
            .map(Duration::from_nanos)
            .ok_or_else(|| {
                io::Error::new(io::ErrorKind::TimedOut, "Calculator total handoff deadline")
            })
    }
}

struct Pending {
    bytes: Vec<u8>,
    deadline: Deadline,
    recovery: bool,
    reply: SyncSender<Option<Vec<u8>>>,
}

pub struct CalculatorAppChannel {
    projection: worker::Projection,
    snapshot: Arc<Mutex<worker::Projection>>,
    sender: Option<SyncSender<worker::Command>>,
    durable: bool,
    pending_edit: Option<(u64, CalculatorValueState)>,
    next_edit: u64,
    edit_refused: bool,
    deferred_close: bool,
    lifetime: Option<SessionLifetime>,
    effect: UnixStream,
    recovery: UnixDatagram,
    workers: Vec<JoinHandle<()>>,
}

impl CalculatorAppChannel {
    pub fn from_inherited_stdin(
        ctx: egui::Context,
        target: CalculatorTargetIdentity,
        lifetime: SessionLifetime,
    ) -> io::Result<Self> {
        target.validate().map_err(io::Error::other)?;
        // The trusted Session selected stdin; no endpoint path or caller FD is accepted.
        let fd = unsafe { BorrowedFd::borrow_raw(0) }.try_clone_to_owned()?;
        let channel = UnixDatagram::from(fd);
        let (raw, effect, recovery) =
            trill_ui_core::notes_private_unix::receive_channels(&channel, HANDOFF_BUDGET)?;
        let offered: CalculatorTargetIdentity =
            serde_json::from_slice(&raw).map_err(io::Error::other)?;
        if offered != target {
            return Err(io::Error::other("Calculator app identity mismatch"));
        }
        lifetime.check_alive()?;
        Self::from_channels(ctx, target, effect, recovery, Some(lifetime))
    }

    fn from_channels(
        ctx: egui::Context,
        target: CalculatorTargetIdentity,
        effect: UnixStream,
        recovery: UnixDatagram,
        lifetime: Option<SessionLifetime>,
    ) -> io::Result<Self> {
        let effect_worker = effect.try_clone()?;
        let recovery_worker = recovery.try_clone()?;
        let connection = worker::start(ctx.clone(), target, lifetime.clone())?;
        let sender = connection.sender.clone();
        // Construct the shutdown guard before the first spawn; a later spawn
        // failure cannot strand an open private effect reader.
        let mut channel = Self {
            projection: worker::Projection::default(),
            snapshot: connection.projection,
            sender: Some(connection.sender),
            durable: connection.durable,
            pending_edit: None,
            next_edit: 0,
            edit_refused: false,
            deferred_close: false,
            lifetime,
            effect,
            recovery,
            workers: Vec::new(),
        };
        let effect_sender = sender.clone();
        let effect_ctx = ctx.clone();
        channel.workers.push(
            std::thread::Builder::new()
                .name("calculator-effect-channel".into())
                .spawn(move || serve_effect(effect_worker, effect_sender, effect_ctx))?,
        );
        channel.workers.push(
            std::thread::Builder::new()
                .name("calculator-readback-channel".into())
                .spawn(move || serve_recovery(recovery_worker, sender, ctx))?,
        );
        Ok(channel)
    }

    pub fn close_if_session_ended(&self, ctx: &egui::Context) -> bool {
        let ended = self
            .lifetime
            .as_ref()
            .is_some_and(SessionLifetime::has_ended);
        if ended {
            ctx.send_viewport_cmd(egui::ViewportCommand::Close);
        } else {
            // Idle windows still observe their real Session pidfd. This is a
            // bounded read-only repaint timer, cancelled with the egui window.
            ctx.request_repaint_after(Duration::from_millis(100));
        }
        ended
    }

    /// Read-only projection: a worker publishes only after the checkpoint sync.
    pub fn poll(&mut self) -> bool {
        let Ok(snapshot) = self.snapshot.lock() else {
            return false;
        };
        if snapshot.version == self.projection.version {
            return false;
        }
        self.projection = snapshot.clone();
        if let Some((id, _)) = &self.pending_edit {
            if let Some((completed, accepted)) = self.projection.local_result {
                if completed == *id {
                    self.pending_edit = None;
                    self.edit_refused = !accepted;
                }
            }
        }
        true
    }
    pub fn state(&self) -> &CalculatorValueState {
        &self.projection.state
    }
    pub fn revision(&self) -> u64 {
        self.projection.revision
    }
    pub fn receipt_pending(&self) -> bool {
        self.projection.receipt_pending
    }
    pub fn edit_pending(&self) -> bool {
        self.pending_edit.is_some()
    }
    pub fn editable(&self) -> bool {
        !self.edit_pending() && !self.projection.storage_failed
    }
    pub fn storage_status(&self) -> &'static str {
        if self.projection.storage_failed {
            "保存失败；当前结果需要恢复核对"
        } else if self.edit_pending() {
            "正在保存计算内容…"
        } else if self.durable {
            "计算内容已保存到此设备"
        } else {
            "临时计算内容；关闭窗口后不会保存"
        }
    }
    pub fn edit_notice(&self) -> Option<&'static str> {
        if self.projection.storage_failed {
            Some("保存失败，已保留最后确认的状态")
        } else if self.edit_refused {
            Some("计算内容已变化，当前编辑未覆盖新状态")
        } else {
            None
        }
    }
    pub fn defer_close_while_saving(&mut self, ctx: &egui::Context) {
        if ctx.input(|input| input.viewport().close_requested()) && self.edit_pending() {
            self.deferred_close = true;
            ctx.send_viewport_cmd(egui::ViewportCommand::CancelClose);
        }
        if self.deferred_close && !self.edit_pending() {
            self.deferred_close = false;
            if !self.projection.storage_failed && !self.edit_refused {
                ctx.send_viewport_cmd(egui::ViewportCommand::Close);
            }
        }
    }
    pub fn local_edit(&mut self, state: CalculatorValueState) -> io::Result<()> {
        if let Some(lifetime) = &self.lifetime {
            lifetime.check_alive()?;
        }
        state.validate().map_err(io::Error::other)?;
        if let Some((_, pending)) = &self.pending_edit {
            return if pending == &state {
                Ok(())
            } else {
                Err(io::Error::new(
                    io::ErrorKind::WouldBlock,
                    "Calculator edit is saving",
                ))
            };
        }
        if state == self.projection.state {
            return Ok(());
        }
        if !self.editable() {
            return Err(io::Error::other("Calculator storage requires recovery"));
        }
        let id = self
            .next_edit
            .checked_add(1)
            .ok_or_else(|| io::Error::other("Calculator edit IDs exhausted"))?;
        self.sender
            .as_ref()
            .ok_or_else(|| io::Error::other("Calculator state worker ended"))?
            .try_send(worker::Command::LocalEdit {
                id,
                revision: self.revision(),
                state: state.clone(),
            })
            .map_err(|_| io::Error::other("Calculator edit queue unavailable"))?;
        self.next_edit = id;
        self.pending_edit = Some((id, state));
        self.edit_refused = false;
        Ok(())
    }
}

impl Drop for CalculatorAppChannel {
    fn drop(&mut self) {
        let _ = self.effect.shutdown(Shutdown::Both);
        let _ = self.recovery.shutdown(Shutdown::Both);
        // Active work has a one-second budget; shutdown wakes idle readers.
        // Drop the final sender after transport exit. The state worker then exits;
        // an in-progress sync keeps the old incarnation locked until it finishes.
        for worker in self.workers.drain(..) {
            let _ = worker.join();
        }
        self.sender.take();
    }
}

fn read_until(stream: &mut UnixStream, mut bytes: &mut [u8], deadline: Deadline) -> io::Result<()> {
    while !bytes.is_empty() {
        stream.set_read_timeout(Some(deadline.remaining()?))?;
        match stream.read(bytes) {
            Ok(0) => {
                return Err(io::Error::new(
                    io::ErrorKind::UnexpectedEof,
                    "Calculator channel closed",
                ))
            }
            Ok(length) => bytes = &mut bytes[length..],
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            Err(error) => return Err(error),
        }
    }
    deadline.remaining()?;
    Ok(())
}

fn write_until(stream: &mut UnixStream, mut bytes: &[u8], deadline: Deadline) -> io::Result<()> {
    while !bytes.is_empty() {
        stream.set_write_timeout(Some(deadline.remaining()?))?;
        match stream.write(bytes) {
            Ok(0) => {
                return Err(io::Error::new(
                    io::ErrorKind::WriteZero,
                    "Calculator channel closed",
                ))
            }
            Ok(length) => bytes = &bytes[length..],
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            Err(error) => return Err(error),
        }
    }
    deadline.remaining()?;
    Ok(())
}

fn serve_effect(mut stream: UnixStream, sender: SyncSender<worker::Command>, ctx: egui::Context) {
    let _ = (|| -> io::Result<()> {
        loop {
            let mut prefix = [0_u8; 4];
            // Waiting for an idle channel starts no operation. From the first
            // byte onward all remaining work shares one BOOTTIME deadline.
            stream.set_read_timeout(None)?;
            stream.read_exact(&mut prefix[..1])?;
            let deadline = Deadline::new()?;
            read_until(&mut stream, &mut prefix[1..], deadline)?;
            let length = u32::from_be_bytes(prefix) as usize;
            if length == 0 || length > MAX_CALCULATOR_REQUEST_BYTES {
                return Err(io::Error::other("Calculator frame bound"));
            }
            let mut bytes = vec![0_u8; length];
            read_until(&mut stream, &mut bytes, deadline)?;
            let (reply, receive) = mpsc::sync_channel(1);
            sender
                .try_send(worker::Command::Protocol(Pending {
                    bytes,
                    deadline,
                    recovery: false,
                    reply,
                }))
                .map_err(|_| io::Error::other("Calculator app queue unavailable"))?;
            ctx.request_repaint();
            let raw = receive
                .recv_timeout(deadline.remaining()?)
                .ok()
                .flatten()
                .ok_or_else(|| io::Error::other("Calculator app outcome unavailable"))?;
            if raw.is_empty() || raw.len() > MAX_CALCULATOR_RESPONSE_BYTES {
                return Err(io::Error::other("Calculator response bound"));
            }
            write_until(&mut stream, &(raw.len() as u32).to_be_bytes(), deadline)?;
            write_until(&mut stream, &raw, deadline)?;
        }
    })();
    // Invalidate every local alias after ambiguity. No subsequent frame can be
    // treated as a fresh operation on this stream, even if a late reply exists.
    let _ = stream.shutdown(Shutdown::Both);
}

fn serve_recovery(channel: UnixDatagram, sender: SyncSender<worker::Command>, ctx: egui::Context) {
    let mut buffer = [0_u8; MAX_CALCULATOR_REQUEST_BYTES + 1];
    loop {
        let Ok(length) = channel.recv(&mut buffer) else {
            return;
        };
        if length == 0 {
            return;
        }
        if length > MAX_CALCULATOR_REQUEST_BYTES {
            continue;
        }
        let Ok(deadline) = Deadline::new() else {
            return;
        };
        let (reply, receive) = mpsc::sync_channel(1);
        if sender
            .try_send(worker::Command::Protocol(Pending {
                bytes: buffer[..length].to_vec(),
                deadline,
                recovery: true,
                reply,
            }))
            .is_err()
        {
            continue;
        }
        ctx.request_repaint();
        let Ok(remaining) = deadline.remaining() else {
            continue;
        };
        let Ok(Some(raw)) = receive.recv_timeout(remaining) else {
            continue;
        };
        if raw.is_empty() || raw.len() > MAX_CALCULATOR_RESPONSE_BYTES {
            continue;
        }
        let Ok(remaining) = deadline.remaining() else {
            continue;
        };
        if channel.set_write_timeout(Some(remaining)).is_err() {
            return;
        }
        // Datagram boundaries preserve the observation/retirement identity.
        // This readback lane has no call to the effect parser.
        let _ = channel.send(&raw);
    }
}

#[cfg(test)]
#[path = "calculator_organ_tests.rs"]
mod tests;

#[cfg(all(test, target_os = "linux"))]
#[path = "calculator_lifetime_tests.rs"]
mod lifetime_tests;
