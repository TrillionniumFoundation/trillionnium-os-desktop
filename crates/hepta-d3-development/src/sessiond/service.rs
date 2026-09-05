use crate::runtime::AtomicFixtureRuntime;
use crate::storage;
use crate::{AnyError, PEER_EXECUTABLE, PEER_GROUP, PEER_UNIT, PEER_USER, REQUEST_BUDGET, invalid};
use crate::{activation, engine};
use hepta_agent_port::{
    AgentPortError, BrowserRequestHandler, DispatchContext, HandlerOutcome, ServiceEvidence,
    serve_one_with_observer,
};
use hepta_agent_transport::{PeerIdentity, PeerPolicy};
use hepta_browser_actor::engine_dispatch::EngineThreadRuntime;
use hepta_browser_actor::{
    BrowserActor, PrincipalBinding, ReceiptLifecycleObserver, TaskFlowPrincipal,
};
use hepta_browser_codec::BrowserRequest;
use hepta_peer_attestation::{
    AttestedPeer, PeerRuntimePolicy, PeerRuntimeSnapshot, ProcfsPeerAttestor,
    TrustedExecutableDigest, hash_trusted_executable, resolve_group_id, resolve_user_id,
};
use hepta_session_core::ReceiptJournal;
use std::os::unix::net::{UnixListener, UnixStream};

// Only the endpoint moves to this worker; the fixture stays on the main thread.
type D3Actor = BrowserActor<EngineThreadRuntime>;

struct AttestedHandler<'a> {
    actor: &'a mut D3Actor,
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
    peer_snapshot: PeerRuntimeSnapshot,
    actor: D3Actor,
    observer: ReceiptLifecycleObserver,
}

pub(crate) fn run_service(arguments: &[String]) -> Result<(), AnyError> {
    activation::require_profile(arguments)?;
    let _marker = activation::require_marker()?;
    let listener = activation::inherited_listener()?;
    listener.set_nonblocking(true)?;
    let expected_uid = resolve_user_id(PEER_USER)?;
    let expected_gid = resolve_group_id(PEER_GROUP)?;
    let policy = PeerRuntimePolicy::for_system_service(expected_uid, expected_gid, PEER_UNIT)?;
    let executable = hash_trusted_executable(PEER_EXECUTABLE)?;
    if activation::required_env("HEPTA_D3_EXPECTED_EXECUTABLE_SHA256")? != executable.as_str() {
        return Err(invalid("configured executable digest does not match trusted path").into());
    }

    let mut persistent_journal = storage::open_configured()?;
    let reconciled = storage::reconcile_unresolved(&mut persistent_journal)?;
    let principal_id = std::env::var("HEPTA_D3_PRINCIPAL_ID")
        .unwrap_or_else(|_| "taskflow-development-local".to_owned());
    let image_id = std::env::var("HEPTA_D3_IMAGE_ID")
        .unwrap_or_else(|_| "trillionnium-development-local".to_owned());

    // Construct and destroy the fixture on main; all actor/observer state is
    // constructed inside the one worker, so its Rc state never crosses threads.
    engine::run_on_owner(AtomicFixtureRuntime::default(), move |runtime, stop| {
        run_connections(
            listener,
            stop,
            runtime,
            persistent_journal,
            policy,
            executable,
            expected_uid,
            expected_gid,
            principal_id,
            image_id,
            reconciled,
        )
    })
}

#[allow(clippy::too_many_arguments)]
fn run_connections(
    listener: UnixListener,
    stop: &engine::ServiceStop,
    runtime: EngineThreadRuntime,
    persistent_journal: ReceiptJournal,
    policy: PeerRuntimePolicy,
    executable: TrustedExecutableDigest,
    expected_uid: u32,
    expected_gid: u32,
    principal_id: String,
    image_id: String,
    reconciled: usize,
) -> Result<(), AnyError> {
    let mut runtime = Some(runtime);
    let mut journal = Some(persistent_journal);
    let mut state = None;
    let attestor = ProcfsPeerAttestor::default();
    println!(
        concat!(
            "{{\"schema\":\"trillionnium.desktop.d3-sessiond-ready.v1\",",
            "\"status\":\"READY\",\"listener_owner\":\"systemd\",",
            "\"accept_mode\":\"accept_no\",\"persistent_actor\":true,",
            "\"one_request_per_connection\":true,\"reconciled_receipts\":{},",
            "\"atomic_semantic_page_act\":true,",
            "\"engine_thread_dispatch_wired\":true,",
            "\"callback_service_runner_wired\":true,",
            "\"callback_service_runner_exercised\":false,",
            "\"same_peer_process_birth_required\":true,",
            "\"servo_adapter_exercised\":false,",
            "\"product_agent_port_enabled\":false,",
            "\"external_effect_authority\":false}}"
        ),
        reconciled
    );

    loop {
        let stream = engine::accept_next(&listener, stop)?;
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
            &mut runtime,
            &mut state,
        ) {
            Ok(evidence) => println!("{}", evidence_json(&evidence)),
            Err(error) => eprintln!("d3 connection rejected: {error}"),
        }
        stop.ensure_active()?;
        // Rotation errors exit the service. A consumed/uncertain writer must
        // not be retried against a guessed old segment or a replacement log.
        rotate_quiescent_store(&mut state)?;
    }
}

fn rotate_quiescent_store(state: &mut Option<SessionState>) -> Result<(), AnyError> {
    if state
        .as_ref()
        .is_some_and(|current| current.observer.managed_rotation_due())
    {
        let now = storage::wall_clock_unix_ms()?;
        let current = state
            .take()
            .ok_or_else(|| invalid("session state disappeared during rotation"))?;
        let observer = current.observer.rotate_managed(now)?;
        *state = Some(SessionState {
            observer,
            ..current
        });
    }
    Ok(())
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
    runtime: &mut Option<EngineThreadRuntime>,
    state: &mut Option<SessionState>,
) -> Result<ServiceEvidence, AnyError> {
    activation::verify_stream_path(&stream)?;
    let peer = PeerIdentity::from_stream(&stream)?;
    let attested = attestor.attest_with_static_executable_digest(peer, policy, executable)?;
    if let Some(current) = state.as_ref() {
        verify_continuity(current, peer, attested.snapshot())?;
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
        *state = Some(attach_session(
            peer,
            attested.snapshot().clone(),
            binding,
            runtime
                .take()
                .ok_or_else(|| invalid("engine endpoint is already attached"))?,
            journal
                .take()
                .ok_or_else(|| invalid("receipt journal is already attached"))?,
            image_id.to_owned(),
        ));
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

fn attach_session(
    peer: PeerIdentity,
    peer_snapshot: PeerRuntimeSnapshot,
    binding: PrincipalBinding,
    runtime: EngineThreadRuntime,
    journal: ReceiptJournal,
    image_id: String,
) -> SessionState {
    let actor = BrowserActor::new(binding, runtime);
    let observer = actor.receipt_observer(journal, image_id);
    SessionState {
        peer,
        peer_snapshot,
        actor,
        observer,
    }
}

// The first attested process birth is retained across connections, while each
// connection retains and refreshes its own pidfd. PID reuse cannot resume a
// previous actor merely because UID/GID/unit/executable still match.
fn verify_continuity(
    current: &SessionState,
    peer: PeerIdentity,
    snapshot: &PeerRuntimeSnapshot,
) -> Result<(), AnyError> {
    if !same_peer(current.peer, peer) || current.peer_snapshot != *snapshot {
        return Err(invalid("persistent TaskFlow process identity changed").into());
    }
    Ok(())
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

#[cfg(test)]
#[path = "service_managed_tests.rs"]
mod managed_tests;

#[cfg(test)]
#[path = "service_threaded_tests.rs"]
mod threaded_tests;
