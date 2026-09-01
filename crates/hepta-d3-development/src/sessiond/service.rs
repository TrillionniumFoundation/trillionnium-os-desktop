use crate::activation;
use crate::storage;
use crate::{AnyError, PEER_EXECUTABLE, PEER_GROUP, PEER_UNIT, PEER_USER, REQUEST_BUDGET, invalid};
use hepta_agent_port::{
    AgentPortError, BrowserRequestHandler, DispatchContext, HandlerOutcome, ServiceEvidence,
    serve_one_with_observer,
};
use hepta_agent_transport::{PeerIdentity, PeerPolicy};
use hepta_browser_actor::{
    BrowserActor, DeterministicLocalRuntime, PrincipalBinding, ReceiptLifecycleObserver,
    TaskFlowPrincipal,
};
use hepta_browser_codec::BrowserRequest;
use hepta_peer_attestation::{
    AttestedPeer, PeerRuntimePolicy, ProcfsPeerAttestor, TrustedExecutableDigest,
    hash_trusted_executable, resolve_group_id, resolve_user_id,
};
use hepta_session_core::ReceiptJournal;
use std::os::unix::net::UnixStream;

struct AttestedHandler<'a> {
    actor: &'a mut BrowserActor<DeterministicLocalRuntime>,
    attestor: &'a ProcfsPeerAttestor,
    attested: &'a AttestedPeer,
}

impl BrowserRequestHandler for AttestedHandler<'_> {
    fn handle(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
    ) -> Result<HandlerOutcome, AgentPortError> {
        self.actor
            .handle_attested(context, request, self.attestor, self.attested)
    }
}

struct SessionState {
    peer: PeerIdentity,
    actor: BrowserActor<DeterministicLocalRuntime>,
    observer: ReceiptLifecycleObserver,
}

pub(crate) fn run_service(arguments: &[String]) -> Result<(), AnyError> {
    activation::require_profile(arguments)?;
    let _marker = activation::require_marker()?;
    let listener = activation::inherited_listener()?;
    let expected_uid = resolve_user_id(PEER_USER)?;
    let expected_gid = resolve_group_id(PEER_GROUP)?;
    let policy = PeerRuntimePolicy::for_system_service(expected_uid, expected_gid, PEER_UNIT)?;
    let executable = hash_trusted_executable(PEER_EXECUTABLE)?;
    if activation::required_env("HEPTA_D3_EXPECTED_EXECUTABLE_SHA256")? != executable.as_str() {
        return Err(invalid("configured executable digest does not match trusted path").into());
    }

    let path = storage::configured_path()?;
    let mut persistent_journal = storage::open_or_create(&path)?;
    let reconciled = storage::reconcile_unresolved(&mut persistent_journal)?;
    let mut journal = Some(persistent_journal);
    let mut state = None;
    let attestor = ProcfsPeerAttestor::default();
    let principal_id = std::env::var("HEPTA_D3_PRINCIPAL_ID")
        .unwrap_or_else(|_| "taskflow-development-local".to_owned());
    let image_id = std::env::var("HEPTA_D3_IMAGE_ID")
        .unwrap_or_else(|_| "trillionnium-development-local".to_owned());

    println!(
        concat!(
            "{{\"schema\":\"trillionnium.desktop.d3-sessiond-ready.v1\",",
            "\"status\":\"READY\",\"listener_owner\":\"systemd\",",
            "\"accept_mode\":\"accept_no\",\"persistent_actor\":true,",
            "\"one_request_per_connection\":true,\"reconciled_receipts\":{},",
            "\"product_agent_port_enabled\":false,",
            "\"external_effect_authority\":false}}"
        ),
        reconciled
    );

    loop {
        let (stream, _) = listener.accept()?;
        match serve_connection(
            stream,
            &attestor,
            &policy,
            &executable,
            expected_uid,
            expected_gid,
            &principal_id,
            &image_id,
            &mut journal,
            &mut state,
        ) {
            Ok(evidence) => println!("{}", evidence_json(&evidence)),
            Err(error) => eprintln!("d3 connection rejected: {error}"),
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn serve_connection(
    stream: UnixStream,
    attestor: &ProcfsPeerAttestor,
    policy: &PeerRuntimePolicy,
    executable: &TrustedExecutableDigest,
    expected_uid: u32,
    expected_gid: u32,
    principal_id: &str,
    image_id: &str,
    journal: &mut Option<ReceiptJournal>,
    state: &mut Option<SessionState>,
) -> Result<ServiceEvidence, AnyError> {
    activation::verify_stream_path(&stream)?;
    let peer = PeerIdentity::from_stream(&stream)?;
    let attested = attestor.attest_with_static_executable_digest(peer, policy, executable)?;
    if let Some(current) = state.as_ref()
        && !same_peer(current.peer, peer)
    {
        return Err(invalid("persistent TaskFlow PID/UID/GID changed").into());
    }

    if state.is_none() {
        let binding = PrincipalBinding::bind_attested(
            TaskFlowPrincipal {
                principal_id: principal_id.to_owned(),
                expected_uid,
                expected_gid,
                expected_systemd_unit: PEER_UNIT.to_owned(),
                expected_cgroup_v2_path: format!("/system.slice/{PEER_UNIT}"),
                expected_executable_sha256: executable.as_str().to_owned(),
            },
            peer,
            attested.snapshot(),
        )?;
        let actor = BrowserActor::new(binding, DeterministicLocalRuntime::default());
        let observer = actor.receipt_observer(
            journal
                .take()
                .ok_or_else(|| invalid("receipt journal is already attached"))?,
            image_id.to_owned(),
        );
        *state = Some(SessionState {
            peer,
            actor,
            observer,
        });
    }

    let current = state
        .as_mut()
        .ok_or_else(|| invalid("persistent session state is missing"))?;
    let mut handler = AttestedHandler {
        actor: &mut current.actor,
        attestor,
        attested: &attested,
    };
    let evidence = serve_one_with_observer(
        stream,
        PeerPolicy {
            expected_pid: peer.pid,
            expected_uid,
            expected_gid: Some(expected_gid),
        },
        REQUEST_BUDGET,
        &mut handler,
        &mut current.observer,
    )?;
    attested.ensure_alive()?;
    Ok(evidence)
}

fn same_peer(left: PeerIdentity, right: PeerIdentity) -> bool {
    left.pid == right.pid && left.uid == right.uid && left.gid == right.gid
}

fn evidence_json(evidence: &ServiceEvidence) -> String {
    format!(
        concat!(
            "{{\"schema\":\"trillionnium.desktop.d3-sessiond-request.v1\",",
            "\"peer_pid\":{},\"peer_uid\":{},\"peer_gid\":{},",
            "\"transport_sequence\":{},\"request_id\":\"{}\",",
            "\"request_sha256\":\"{}\",\"response_sha256\":\"{}\",",
            "\"response_ok\":{},\"response_committed\":{},",
            "\"persistent_actor\":true}}"
        ),
        evidence.peer.pid.unwrap_or_default(),
        evidence.peer.uid,
        evidence.peer.gid,
        evidence.transport_sequence,
        escape_json(&evidence.request_id),
        evidence.request_sha256,
        evidence.response_sha256,
        evidence.response_ok,
        evidence.response_committed,
    )
}

fn escape_json(value: &str) -> String {
    value
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
        .replace('\r', "\\r")
        .replace('\t', "\\t")
}

#[cfg(test)]
mod tests {
    use super::*;
    use hepta_session_core::ReceiptLifecycleState;

    #[test]
    fn peer_identity_comparison_includes_pid_uid_and_gid() {
        let base = PeerIdentity {
            pid: Some(7),
            uid: 8,
            gid: 9,
        };
        assert!(same_peer(base, base));
        assert!(!same_peer(
            base,
            PeerIdentity {
                pid: Some(10),
                ..base
            }
        ));
    }

    #[test]
    fn receipt_recovery_terminal_vocabulary_is_available() {
        assert!(ReceiptLifecycleState::Indeterminate.is_terminal());
        assert!(ReceiptLifecycleState::Interrupted.is_terminal());
    }
}
