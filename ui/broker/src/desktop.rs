//! Private display-domain adapter. Original Hepta owns grants and its durable
//! operation ledger. This process keeps only bounded, live-instance receipts;
//! lost history is Unknown, and screenshot pixels never prove an input result.
mod x11;
use std::collections::BTreeMap;
use std::io::{self, Read, Write};
use std::net::Shutdown;
use std::os::unix::net::UnixStream;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use trill_ui_core::desktop::*;
use trill_ui_core::notes::sha256_hex;
use x11::NativeInput;
pub use x11::NativeX11;

const FRAME_DEADLINE: Duration = Duration::from_secs(2);
struct Adapter {
    native: NativeX11,
    identity: DesktopTargetIdentity,
    sequence: u64,
    receipts: BTreeMap<String, (String, Vec<u8>)>,
    uncertain: bool,
}
impl Adapter {
    fn reply(
        &self,
        operation_id: String,
        payload_sha256: String,
        result: InputResult,
    ) -> io::Result<Vec<u8>> {
        serde_json::to_vec(&DesktopReceipt {
            schema_version: 1,
            target: self.identity.clone(),
            operation_id,
            payload_sha256,
            result,
        })
        .map_err(io::Error::other)
    }
    fn input(&mut self, raw: &[u8]) -> io::Result<Vec<u8>> {
        let request = DesktopInput::parse_exact(raw).map_err(io::Error::other)?;
        let digest = sha256_hex(raw);
        if let Some((prior, reply)) = self.receipts.get(&request.operation_id) {
            if *prior == digest {
                return Ok(reply.clone());
            }
            return self.reply(
                request.operation_id,
                digest,
                InputResult::NotInjected {
                    reason: NotInjectedReason::OperationConflict,
                    current_sequence: self.sequence,
                },
            );
        }
        let reason =
            if request.target != self.identity || request.expected_window != self.native.window() {
                Some(NotInjectedReason::TargetMismatch)
            } else if self.receipts.len() >= MAX_RECEIPTS {
                Some(NotInjectedReason::ReceiptCapacity)
            } else if request.expected_sequence != self.sequence {
                Some(NotInjectedReason::SequenceConflict)
            } else if self.sequence == u64::MAX {
                Some(NotInjectedReason::SequenceExhausted)
            } else {
                None
            };
        if let Some(reason) = reason {
            return self.reply(
                request.operation_id,
                digest,
                InputResult::NotInjected {
                    reason,
                    current_sequence: self.sequence,
                },
            );
        }
        let result = if self.uncertain {
            InputResult::Unknown {
                current_sequence: self.sequence,
            }
        } else {
            match self.native.inject(&request.events) {
                NativeInput::Injected => {
                    let previous = self.sequence;
                    self.sequence += 1;
                    InputResult::Injected {
                        effect_semantics: InputSemantics::X11ServerInjected,
                        previous_sequence: previous,
                        sequence: self.sequence,
                    }
                }
                NativeInput::NotInjected(reason) => InputResult::NotInjected {
                    reason,
                    current_sequence: self.sequence,
                },
                NativeInput::Unknown => {
                    self.uncertain = true;
                    InputResult::Unknown {
                        current_sequence: self.sequence,
                    }
                }
            }
        };
        let reply = self.reply(request.operation_id.clone(), digest.clone(), result)?;
        // Store the exact reply before returning it. This is an ephemeral
        // deduplication cache; crash/restart cannot claim persistence.
        self.receipts
            .insert(request.operation_id, (digest, reply.clone()));
        Ok(reply)
    }
    fn observe(&mut self, raw: &[u8]) -> io::Result<Vec<u8>> {
        match DesktopObservationRequest::parse_exact(raw).map_err(io::Error::other)? {
            DesktopObservationRequest::Observe {
                target,
                operation_id,
                payload_sha256,
                ..
            } => {
                if target == self.identity {
                    if let Some((digest, reply)) = self.receipts.get(&operation_id) {
                        if *digest == payload_sha256 {
                            return Ok(reply.clone());
                        }
                    }
                }
                // Return the queried identity, including an old incarnation,
                // and never confuse cache absence with proven non-injection.
                serde_json::to_vec(&DesktopReceipt {
                    schema_version: 1,
                    target,
                    operation_id,
                    payload_sha256,
                    result: InputResult::Unknown {
                        current_sequence: self.sequence,
                    },
                })
                .map_err(io::Error::other)
            }
            DesktopObservationRequest::Capture {
                target, request_id, ..
            } => {
                if target != self.identity {
                    return Err(io::Error::other("capture identity mismatch"));
                }
                let image = self.native.capture()?;
                serde_json::to_vec(&DesktopCapture {
                    schema_version: 1,
                    action: "capture".into(),
                    target,
                    request_id,
                    input_sequence: self.sequence,
                    window_id: self.native.window(),
                    width: image.width,
                    height: image.height,
                    pixel_format: "rgb8".into(),
                    pixels_hex: encode_hex(&image.rgb),
                    sha256: sha256_hex(&image.rgb),
                })
                .map_err(io::Error::other)
            }
        }
    }
}

/// Worker ownership handle. Dropping it shuts down both capabilities even if
/// workers retain duplicates; Session never joins a peer-blocked worker.
pub struct DesktopService {
    effect: UnixStream,
    observe: UnixStream,
}
impl Drop for DesktopService {
    fn drop(&mut self) {
        let _ = self.effect.shutdown(Shutdown::Both);
        let _ = self.observe.shutdown(Shutdown::Both);
    }
}
impl DesktopService {
    /// Only an explicit trusted-parent bootstrap can call this constructor.
    /// Neither Broker nor public Session IPC has a route to these descriptors.
    pub fn start(
        native: NativeX11,
        identity: DesktopTargetIdentity,
    ) -> io::Result<(Self, UnixStream, UnixStream, DesktopBootstrapOffer)> {
        identity.validate().map_err(io::Error::other)?;
        let (width, height) = native.dimensions();
        let offer = DesktopBootstrapOffer {
            schema_version: 1,
            profile: PROFILE.into(),
            destination_id: identity.destination_id(),
            scope_sha256: identity.scope_sha256(),
            expected_window: native.window(),
            screen_width: width,
            screen_height: height,
            target: identity.clone(),
        };
        let shared = Arc::new(Mutex::new(Adapter {
            native,
            identity,
            sequence: 0,
            receipts: BTreeMap::new(),
            uncertain: false,
        }));
        let (effect, owner_effect) = UnixStream::pair()?;
        let (observe, owner_observe) = UnixStream::pair()?;
        let guard = Self {
            effect: effect.try_clone()?,
            observe: observe.try_clone()?,
        };
        for (mut stream, is_effect) in [(effect, true), (observe, false)] {
            let state = Arc::clone(&shared);
            std::thread::Builder::new()
                .name(
                    if is_effect {
                        "desktop-effect"
                    } else {
                        "desktop-observe"
                    }
                    .into(),
                )
                .spawn(move || {
                    let result = (|| -> io::Result<()> {
                        loop {
                            // Idle is not a failed request. The total frame deadline
                            // starts only once its first byte arrives.
                            stream.set_read_timeout(None)?;
                            let mut first = [0];
                            stream.read_exact(&mut first)?;
                            let deadline = Instant::now() + FRAME_DEADLINE;
                            let raw = read_frame(&mut stream, first[0], deadline)?;
                            let reply = {
                                let mut state = state
                                    .lock()
                                    .map_err(|_| io::Error::other("desktop adapter poisoned"))?;
                                if is_effect {
                                    state.input(&raw)?
                                } else {
                                    state.observe(&raw)?
                                }
                            };
                            if reply.len() > if is_effect { RESPONSE_MAX } else { CAPTURE_MAX } {
                                return Err(io::Error::other("desktop reply bound"));
                            }
                            write_frame(&mut stream, &reply, deadline)?;
                        }
                    })();
                    if let Err(e) = result {
                        eprintln!(
                            "desktop {} channel closed: {e}",
                            if is_effect { "effect" } else { "observe" }
                        );
                    }
                    let _ = stream.shutdown(Shutdown::Both);
                })?;
        }
        Ok((guard, owner_effect, owner_observe, offer))
    }
}
fn remaining(deadline: Instant) -> io::Result<Duration> {
    deadline
        .checked_duration_since(Instant::now())
        .filter(|d| !d.is_zero())
        .ok_or_else(|| io::Error::new(io::ErrorKind::TimedOut, "desktop total frame deadline"))
}
fn read_frame(stream: &mut UnixStream, first: u8, deadline: Instant) -> io::Result<Vec<u8>> {
    let mut prefix = [0; 4];
    prefix[0] = first;
    for byte in &mut prefix[1..] {
        stream.set_read_timeout(Some(remaining(deadline)?))?;
        stream.read_exact(std::slice::from_mut(byte))?;
    }
    let length = u32::from_be_bytes(prefix) as usize;
    if length == 0 || length > REQUEST_MAX {
        return Err(io::Error::other("desktop request bound"));
    }
    let mut raw = vec![0; length];
    let mut done = 0;
    while done < length {
        stream.set_read_timeout(Some(remaining(deadline)?))?;
        let count = stream.read(&mut raw[done..])?;
        if count == 0 {
            return Err(io::Error::new(
                io::ErrorKind::UnexpectedEof,
                "desktop frame",
            ));
        }
        done += count;
    }
    remaining(deadline)?;
    Ok(raw)
}
fn write_frame(stream: &mut UnixStream, raw: &[u8], deadline: Instant) -> io::Result<()> {
    let mut output = (raw.len() as u32).to_be_bytes().to_vec();
    output.extend_from_slice(raw);
    let mut done = 0;
    while done < output.len() {
        stream.set_write_timeout(Some(remaining(deadline)?))?;
        let count = stream.write(&output[done..])?;
        if count == 0 {
            return Err(io::Error::new(io::ErrorKind::WriteZero, "desktop frame"));
        }
        done += count;
    }
    remaining(deadline)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn frame_deadline_is_total_and_shutdown_reaches_duplicates() {
        let (mut server, mut client) = UnixStream::pair().unwrap();
        let alias = server.try_clone().unwrap();
        let worker = std::thread::spawn(move || {
            let result = read_frame(&mut server, 0, Instant::now() + Duration::from_millis(100));
            assert!(result.is_err());
            let _ = server.shutdown(Shutdown::Both);
        });
        let started = Instant::now();
        for byte in [0, 0, 32, b' '] {
            let _ = client.write_all(&[byte]);
            std::thread::sleep(Duration::from_millis(35));
        }
        client
            .set_read_timeout(Some(Duration::from_millis(300)))
            .unwrap();
        assert_eq!(client.read(&mut [0]).unwrap(), 0);
        worker.join().unwrap();
        assert!(started.elapsed() < Duration::from_millis(400));
        drop(alias);
    }
}
