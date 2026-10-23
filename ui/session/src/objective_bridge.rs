//! Fixed trusted-host transport. Renderer messages never select a peer or carry authority.
use std::os::unix::fs::{FileTypeExt, MetadataExt};
use std::path::PathBuf;
use std::time::Duration;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::runtime::{Builder, Runtime};
use trill_ui_core::objective::*;

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

    pub(super) fn request(&self, command: ObjectiveCommand) -> ObjectiveObservation {
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
        let result = runtime.block_on(async {
            tokio::time::timeout(Duration::from_millis(150), async {
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
