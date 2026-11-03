//! Private Calculator channels. Only the egui main thread mutates app state;
//! transport threads submit bounded work and cannot issue grants or replay.

use eframe::egui;
use std::io::{self, Read, Write};
use std::net::Shutdown;
use std::os::fd::BorrowedFd;
use std::os::unix::net::{UnixDatagram, UnixStream};
use std::sync::mpsc::{self, Receiver, SyncSender};
use std::thread::JoinHandle;
use std::time::Duration;
use trill_ui_core::calculator::{
    CalculatorDocument, CalculatorTargetIdentity, CalculatorValueState,
    MAX_CALCULATOR_REQUEST_BYTES, MAX_CALCULATOR_RESPONSE_BYTES,
};
use trill_ui_core::calculator_lifetime::{boottime_nanos, SessionLifetime};

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
    document: CalculatorDocument,
    receiver: Receiver<Pending>,
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
        let document = CalculatorDocument::new(target).map_err(io::Error::other)?;
        let (sender, receiver) = mpsc::sync_channel(2);
        let effect_worker = effect.try_clone()?;
        let recovery_worker = recovery.try_clone()?;
        // Construct the shutdown guard before the first spawn; a later spawn
        // failure cannot strand an open private effect reader.
        let mut channel = Self {
            document,
            receiver,
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

    /// Called from the same egui update which consumes these values for layout.
    pub fn poll(&mut self) -> bool {
        let mut updated = false;
        for _ in 0..2 {
            let Ok(pending) = self.receiver.try_recv() else {
                break;
            };
            if self
                .lifetime
                .as_ref()
                .is_some_and(SessionLifetime::has_ended)
            {
                let _ = pending.reply.try_send(None);
                continue;
            }
            let response = if pending.deadline.remaining().is_err() {
                if pending.recovery {
                    None
                } else {
                    self.document
                        .deadline_refusal(&pending.bytes)
                        .ok()
                        .and_then(|r| serde_json::to_vec(&r).ok())
                }
            } else if pending.recovery {
                self.document.recovery_exact(&pending.bytes).ok()
            } else {
                self.document
                    .apply_exact(&pending.bytes)
                    .ok()
                    .and_then(|r| serde_json::to_vec(&r).ok())
            };
            updated = true;
            let _ = pending.reply.try_send(
                response.filter(|v| !v.is_empty() && v.len() <= MAX_CALCULATOR_RESPONSE_BYTES),
            );
        }
        updated
    }
    pub fn state(&self) -> &CalculatorValueState {
        self.document.state()
    }
    pub fn revision(&self) -> u64 {
        self.document.revision()
    }
    pub fn receipt_pending(&self) -> bool {
        self.document.receipt_pending()
    }
    pub fn local_edit(&mut self, state: CalculatorValueState) -> io::Result<()> {
        if let Some(lifetime) = &self.lifetime {
            lifetime.check_alive()?;
        }
        self.document.local_edit(state).map_err(io::Error::other)
    }
}

impl Drop for CalculatorAppChannel {
    fn drop(&mut self) {
        let _ = self.effect.shutdown(Shutdown::Both);
        let _ = self.recovery.shutdown(Shutdown::Both);
        // Active work has a one-second budget; shutdown wakes idle readers.
        // Neither worker can access or mutate the GUI-owned model.
        for worker in self.workers.drain(..) {
            let _ = worker.join();
        }
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

fn serve_effect(mut stream: UnixStream, sender: SyncSender<Pending>, ctx: egui::Context) {
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
                .try_send(Pending {
                    bytes,
                    deadline,
                    recovery: false,
                    reply,
                })
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

fn serve_recovery(channel: UnixDatagram, sender: SyncSender<Pending>, ctx: egui::Context) {
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
            .try_send(Pending {
                bytes: buffer[..length].to_vec(),
                deadline,
                recovery: true,
                reply,
            })
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
