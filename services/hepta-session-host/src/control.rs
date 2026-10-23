//! Original protocol calls with the same pinned kernel peer as Objective ingress.
use codex_hepta_agent_protocol::{
    AGENTD_CONTROL_SCHEMA_VERSION, AgentdPayload, AgentdRequest, AgentdResponse,
    MAX_CONTROL_FRAME_BYTES,
};
use codex_hepta_memory::ObjectiveSenderOrigin;
use std::os::unix::fs::{FileTypeExt, MetadataExt};
use std::time::Duration;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::UnixStream;
use tokio::runtime::Handle;
use trill_ui_core::objective::ObjectiveHostIssue;

pub(super) fn call(
    runtime: &Handle,
    origin: &ObjectiveSenderOrigin,
    request: AgentdRequest,
) -> Result<AgentdPayload, ObjectiveHostIssue> {
    if Handle::try_current().is_ok() {
        return Err(ObjectiveHostIssue::Unavailable);
    }
    runtime.block_on(async {
        tokio::time::timeout(Duration::from_secs(5), async {
            let metadata = tokio::fs::symlink_metadata(&origin.endpoint_identity)
                .await
                .map_err(|_| ObjectiveHostIssue::Unavailable)?;
            if !metadata.file_type().is_socket()
                || metadata.uid() != origin.expected_peer_uid
                || metadata.mode() & 0o077 != 0
            {
                return Err(ObjectiveHostIssue::IdentityMismatch);
            }
            let mut stream = UnixStream::connect(&origin.endpoint_identity)
                .await
                .map_err(|_| ObjectiveHostIssue::Unavailable)?;
            let peer = stream
                .peer_cred()
                .map_err(|_| ObjectiveHostIssue::IdentityMismatch)?;
            if peer.uid() != origin.expected_peer_uid
                || peer.pid().and_then(|p| u32::try_from(p).ok()) != Some(origin.expected_peer_pid)
            {
                return Err(ObjectiveHostIssue::IdentityMismatch);
            }
            let mut frame =
                serde_json::to_vec(&request).map_err(|_| ObjectiveHostIssue::InvalidIntent)?;
            frame.push(b'\n');
            if frame.len() as u64 > MAX_CONTROL_FRAME_BYTES {
                return Err(ObjectiveHostIssue::InvalidIntent);
            }
            stream
                .write_all(&frame)
                .await
                .map_err(|_| ObjectiveHostIssue::TransportUnknown)?;
            let mut bytes = Vec::new();
            stream
                .take(MAX_CONTROL_FRAME_BYTES + 1)
                .read_to_end(&mut bytes)
                .await
                .map_err(|_| ObjectiveHostIssue::TransportUnknown)?;
            if bytes.is_empty()
                || bytes.len() as u64 > MAX_CONTROL_FRAME_BYTES
                || !bytes.ends_with(b"\n")
                || bytes[..bytes.len() - 1].contains(&b'\n')
            {
                return Err(ObjectiveHostIssue::TransportUnknown);
            }
            let response: AgentdResponse =
                serde_json::from_slice(&bytes).map_err(|_| ObjectiveHostIssue::TransportUnknown)?;
            if response.schema_version != AGENTD_CONTROL_SCHEMA_VERSION
                || response.request_id != request.request_id
                || response.agent_id != origin.agent_id
                || response.spawn_generation != origin.spawn_generation
                || response.current_generation < origin.spawn_generation
            {
                return Err(ObjectiveHostIssue::IdentityMismatch);
            }
            let receipt = match &response.payload {
                AgentdPayload::RunStatus { run } => run.as_ref(),
                AgentdPayload::RunCancellation(cancellation) => Some(&cancellation.receipt),
                _ => None,
            };
            if receipt.is_some_and(|run| {
                run.generation < origin.spawn_generation
                    || run.generation > response.current_generation
            }) {
                return Err(ObjectiveHostIssue::IdentityMismatch);
            }
            Ok(response.payload)
        })
        .await
        .map_err(|_| ObjectiveHostIssue::TransportUnknown)?
    })
}
