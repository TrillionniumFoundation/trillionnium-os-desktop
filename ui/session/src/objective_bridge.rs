//! Fixed trusted-host transport. Renderer messages never select a peer or carry authority.
use std::os::unix::fs::{FileTypeExt, MetadataExt};
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, AtomicU8, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::runtime::{Builder, Runtime};
use trill_ui_core::objective::*;

const WAITING: u8 = 0;
const ABANDONED: u8 = 1;
const SENDING: u8 = 2;

/// A local transport admission race, never original-owner cancellation.
pub(super) struct RequestPermit {
    deadline: Instant,
    state: AtomicU8,
    stopped: Arc<AtomicBool>,
}

impl RequestPermit {
    pub(super) fn new(deadline: Instant, stopped: Arc<AtomicBool>) -> Self {
        Self {
            deadline,
            state: AtomicU8::new(WAITING),
            stopped,
        }
    }

    pub(super) fn abandon(&self) {
        // Once first-write admission wins, an effect may already have reached
        // the original owner. Closing a client cannot revoke that possibility.
        let _ =
            self.state
                .compare_exchange(WAITING, ABANDONED, Ordering::AcqRel, Ordering::Acquire);
    }

    fn waiting(&self) -> bool {
        Instant::now() < self.deadline
            && !self.stopped.load(Ordering::Acquire)
            && self.state.load(Ordering::Acquire) == WAITING
    }

    fn begin_send(&self) -> Result<(), ObjectiveHostIssue> {
        if !self.waiting() {
            return Err(ObjectiveHostIssue::TransportUnknown);
        }
        self.state
            .compare_exchange(WAITING, SENDING, Ordering::AcqRel, Ordering::Acquire)
            .map_err(|_| ObjectiveHostIssue::TransportUnknown)?;
        if Instant::now() >= self.deadline || self.stopped.load(Ordering::SeqCst) {
            return Err(ObjectiveHostIssue::TransportUnknown);
        }
        Ok(())
    }
}

pub(super) fn transport_unknown(command: &ObjectiveCommand) -> ObjectiveObservation {
    let mut view = ObjectiveObservation::new(
        command.client_intent_id().map(str::to_owned),
        ObjectiveStage::Unavailable,
    );
    if matches!(command, ObjectiveCommand::Submit { .. }) {
        view.stage = ObjectiveStage::SubmitUnknown;
    }
    if matches!(command, ObjectiveCommand::Cancel { .. }) {
        view.cancellation = ObjectiveCancellation::Unknown;
    }
    view.issue = Some(ObjectiveHostIssue::TransportUnknown);
    view
}

pub(super) struct ObjectiveBridge {
    endpoint: Option<(PathBuf, u32)>,
    runtime: Option<Runtime>,
}

impl ObjectiveBridge {
    pub(super) fn from_environment() -> Self {
        let endpoint = std::env::var_os("TRILL_OBJECTIVE_HOST_SOCKET")
            .map(PathBuf::from)
            .zip(
                std::env::var("TRILL_OBJECTIVE_HOST_PID")
                    .ok()
                    .and_then(|s| s.parse::<u32>().ok()),
            )
            .filter(|(path, pid)| path.is_absolute() && *pid > 0 && *pid <= i32::MAX as u32);
        let runtime = endpoint.as_ref().and_then(|_| {
            Builder::new_current_thread()
                .enable_io()
                .enable_time()
                .max_blocking_threads(1)
                .build()
                .ok()
        });
        Self { endpoint, runtime }
    }

    pub(super) fn configured(&self) -> bool {
        self.endpoint.is_some() && self.runtime.is_some()
    }

    pub(super) fn request_until(
        &self,
        command: ObjectiveCommand,
        permit: &RequestPermit,
    ) -> ObjectiveObservation {
        let mut unknown = ObjectiveObservation::new(
            command.client_intent_id().map(str::to_owned),
            ObjectiveStage::Unavailable,
        );
        if let Err(issue) = command.validate() {
            unknown.issue = Some(issue);
            return unknown;
        }
        let (Some((path, pid)), Some(runtime)) = (&self.endpoint, &self.runtime) else {
            unknown.issue = Some(ObjectiveHostIssue::Unavailable);
            return unknown;
        };
        if !permit.waiting() {
            return transport_unknown(&command);
        }
        let deadline = permit
            .deadline
            .min(Instant::now() + Duration::from_millis(150));
        let result = runtime.block_on(async {
            tokio::time::timeout_at(tokio::time::Instant::from_std(deadline), async {
                let metadata = tokio::fs::symlink_metadata(path)
                    .await
                    .map_err(|_| ObjectiveHostIssue::Unavailable)?;
                let uid = trill_ui_core::host_peer::current_effective_uid();
                if !metadata.file_type().is_socket()
                    || metadata.uid() != uid
                    || metadata.mode() & 0o077 != 0
                {
                    return Err(ObjectiveHostIssue::IdentityMismatch);
                }
                let mut stream = tokio::net::UnixStream::connect(path)
                    .await
                    .map_err(|_| ObjectiveHostIssue::Unavailable)?;
                let peer = stream
                    .peer_cred()
                    .map_err(|_| ObjectiveHostIssue::IdentityMismatch)?;
                if peer.uid() != uid || peer.pid().and_then(|p| u32::try_from(p).ok()) != Some(*pid)
                {
                    return Err(ObjectiveHostIssue::IdentityMismatch);
                }
                let mut frame =
                    serde_json::to_vec(&command).map_err(|_| ObjectiveHostIssue::InvalidIntent)?;
                frame.push(b'\n');
                // Validation and peer authentication may have yielded. Check
                // the original exchange budget and abandonment again before
                // the only first-write attempt; no retry follows uncertainty.
                permit.begin_send()?;
                stream
                    .write_all(&frame)
                    .await
                    .map_err(|_| ObjectiveHostIssue::TransportUnknown)?;
                let mut bytes = Vec::new();
                stream
                    .take(trill_ui_core::MAX_FRAME as u64 + 1)
                    .read_to_end(&mut bytes)
                    .await
                    .map_err(|_| ObjectiveHostIssue::TransportUnknown)?;
                if bytes.is_empty()
                    || bytes.len() > trill_ui_core::MAX_FRAME
                    || !bytes.ends_with(b"\n")
                    || bytes[..bytes.len() - 1].contains(&b'\n')
                {
                    return Err(ObjectiveHostIssue::TransportUnknown);
                }
                let view: ObjectiveObservation = serde_json::from_slice(&bytes)
                    .map_err(|_| ObjectiveHostIssue::TransportUnknown)?;
                if view.client_intent_id.as_deref() != command.client_intent_id() {
                    return Err(ObjectiveHostIssue::IdentityMismatch);
                }
                if let Some(document) = &view.notes_document {
                    document.validate()?;
                }
                if let Some(retained) = &view.retained_intents {
                    retained.validate()?;
                    if !matches!(command, ObjectiveCommand::Availability {}) {
                        return Err(ObjectiveHostIssue::IdentityMismatch);
                    }
                }
                Ok(view)
            })
            .await
        });
        match result {
            Ok(Ok(view)) => view,
            error => {
                let issue = match error {
                    Ok(Err(issue)) => issue,
                    Err(_) => ObjectiveHostIssue::TransportUnknown,
                    Ok(Ok(_)) => unreachable!(),
                };
                if matches!(command, ObjectiveCommand::Submit { .. }) {
                    unknown.stage = ObjectiveStage::SubmitUnknown;
                }
                if matches!(command, ObjectiveCommand::Cancel { .. }) {
                    unknown.cancellation = ObjectiveCancellation::Unknown;
                }
                unknown.issue = Some(issue);
                unknown
            }
        }
    }

    #[cfg(test)]
    pub(super) fn at_endpoint(path: PathBuf, pid: u32) -> Self {
        Self {
            endpoint: Some((path, pid)),
            runtime: Some(Builder::new_current_thread().enable_all().build().unwrap()),
        }
    }

    #[cfg(test)]
    fn request(&self, command: ObjectiveCommand) -> ObjectiveObservation {
        self.request_until(
            command,
            &RequestPermit::new(
                Instant::now() + Duration::from_millis(150),
                Arc::new(AtomicBool::new(false)),
            ),
        )
    }
}

impl Drop for ObjectiveBridge {
    fn drop(&mut self) {
        if let Some(runtime) = self.runtime.take() {
            runtime.shutdown_background();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{BufRead, BufReader, Write};
    use std::os::unix::fs::PermissionsExt;
    use std::os::unix::net::UnixListener;
    use std::sync::atomic::{AtomicUsize, Ordering};
    static NEXT: AtomicUsize = AtomicUsize::new(1);

    #[test]
    fn bridge_preserves_readback_and_refuses_malformed_document_identity() {
        let path = std::env::temp_dir().join(format!(
            "trill-objective-readback-{}-{}.sock",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        let listener = UnixListener::bind(&path).unwrap();
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
        let bridge = ObjectiveBridge {
            endpoint: Some((path.clone(), std::process::id())),
            runtime: Some(Builder::new_current_thread().enable_all().build().unwrap()),
        };
        let expected: ObjectiveObservation = serde_json::from_str(include_str!(
            "../../../tests/ui/notes-document-observation-v1.json"
        ))
        .unwrap();
        let mut invalid = expected.clone();
        invalid.notes_document.as_mut().unwrap().target.task_id = 0;
        let replies = [expected.clone(), invalid];
        let server = std::thread::spawn(move || {
            for response in replies {
                let (mut stream, _) = listener.accept().unwrap();
                let mut frame = String::new();
                BufReader::new(stream.try_clone().unwrap())
                    .read_line(&mut frame)
                    .unwrap();
                assert!(matches!(
                    serde_json::from_str::<ObjectiveCommand>(&frame).unwrap(),
                    ObjectiveCommand::Status { .. }
                ));
                let mut bytes = serde_json::to_vec(&response).unwrap();
                bytes.push(b'\n');
                stream.write_all(&bytes).unwrap();
            }
        });
        let command = ObjectiveCommand::Status {
            client_intent_id: "original-intent".into(),
        };
        assert_eq!(bridge.request(command.clone()), expected);
        let refused = bridge.request(command);
        assert_eq!(refused.issue, Some(ObjectiveHostIssue::IdentityMismatch));
        assert!(refused.notes_document.is_none());
        assert!(refused.run.is_none());
        server.join().unwrap();
        std::fs::remove_file(path).unwrap();
    }

    #[test]
    fn bridge_checks_fixed_peer_before_forwarding_and_preserves_typed_reply() {
        let path = std::env::temp_dir().join(format!(
            "trill-objective-{}-{}.sock",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        let listener = UnixListener::bind(&path).unwrap();
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
        let runtime = Builder::new_current_thread().enable_all().build().unwrap();
        let mut bridge = ObjectiveBridge {
            endpoint: Some((path.clone(), std::process::id() + 1)),
            runtime: Some(runtime),
        };
        let denied = bridge.request(ObjectiveCommand::Availability {});
        assert_eq!(denied.issue, Some(ObjectiveHostIssue::IdentityMismatch));
        // The refused connection receives no request bytes.
        let (mut denied_peer, _) = listener.accept().unwrap();
        let mut bytes = Vec::new();
        std::io::Read::read_to_end(&mut denied_peer, &mut bytes).unwrap();
        assert!(bytes.is_empty());
        bridge.endpoint = Some((path.clone(), std::process::id()));
        let expected = ObjectiveObservation::new(None, ObjectiveStage::Ready);
        let response = expected.clone();
        let server = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let mut frame = String::new();
            BufReader::new(stream.try_clone().unwrap())
                .read_line(&mut frame)
                .unwrap();
            assert_eq!(
                serde_json::from_str::<ObjectiveCommand>(&frame).unwrap(),
                ObjectiveCommand::Availability {}
            );
            let mut bytes = serde_json::to_vec(&response).unwrap();
            bytes.push(b'\n');
            stream.write_all(&bytes).unwrap();
        });
        assert_eq!(bridge.request(ObjectiveCommand::Availability {}), expected);
        server.join().unwrap();
        std::fs::remove_file(path).unwrap();
    }
}
