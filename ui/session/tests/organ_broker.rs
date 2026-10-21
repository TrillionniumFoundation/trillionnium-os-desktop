#![cfg(target_os = "linux")]

//! The actual Session executable consumes the existing Broker over a real
//! private Unix socket. This grants no production owner or graphics status.
use socket2::{Domain, SockAddr, Socket, Type};
use std::fs::{self, DirBuilder};
use std::io::{self, Read, Write};
use std::net::Shutdown;
use std::os::fd::OwnedFd;
use std::os::unix::fs::{DirBuilderExt, MetadataExt, PermissionsExt};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::thread;
use std::time::Duration;
use trill_ui_broker::host::{exchange_at, ExchangeRequest};
use trill_ui_broker::{
    BootDelivery, Capability, ClientHello, DenialCode, DraftDurability, DurableIntent,
    GenerationFence, OfflineDraft, OperationKey, OperationState, Request, Response, SafetyMode,
};
use trill_ui_core::{request_at, unix_ms};

struct SessionProcess {
    child: Child,
    runtime: PathBuf,
}

impl Drop for SessionProcess {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
        let _ = fs::remove_dir_all(&self.runtime);
    }
}

fn command(runtime: &PathBuf) -> Command {
    let mut command = Command::new(env!("CARGO_BIN_EXE_trill-session"));
    command
        .env("XDG_RUNTIME_DIR", runtime)
        .env_remove("TRILL_HEPTA_AGENTD_SOCKET")
        .env_remove("TRILL_HEPTA_AGENT_ID")
        .env_remove("TRILL_HEPTA_SPAWN_GENERATION")
        .env_remove("TRILL_HEPTA_PEER_UID")
        .env_remove("TRILL_HEPTA_RUN_ID")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    command
}

fn hello() -> ClientHello {
    ClientHello {
        protocol_version: 1,
        client_id: "desktop-test".into(),
        session_nonce: "nonce-0123456789abcdef".into(),
        requested_capabilities: vec![
            Capability::Observe,
            Capability::OfflineDraft,
            Capability::Reconcile,
            Capability::SubmitEffect,
            Capability::CancelEffect,
        ],
    }
}

fn intent() -> DurableIntent {
    DurableIntent {
        key: OperationKey {
            scope_id: "scope-a".into(),
            operation_id: "operation-a".into(),
            payload_digest: "a".repeat(64),
        },
        destination: "cpu:test".into(),
    }
}

fn delivery() -> BootDelivery {
    BootDelivery {
        boot_id: "boot-a".into(),
        delivery_id: "delivery-a".into(),
        capspace_epoch: 1,
        sequence: 1,
    }
}

fn fence() -> GenerationFence {
    GenerationFence {
        authority_generation: 1,
        body_generation: 1,
        resource_generation: 1,
        bridge_generation: 1,
        owner_generation: 1,
    }
}

#[test]
fn actual_session_exposes_one_default_deny_broker_beside_the_existing_host_protocol() {
    let runtime = std::env::temp_dir().join(format!(
        "trill-organ-test-{}-{}",
        std::process::id(),
        unix_ms()
    ));
    DirBuilder::new().mode(0o700).create(&runtime).unwrap();
    let mut process = SessionProcess {
        child: command(&runtime).spawn().unwrap(),
        runtime: runtime.clone(),
    };
    let host_socket = runtime.join("trillionnium-ui/session.sock");
    let broker_socket = runtime.join("trillionnium-ui/organ.sock");
    let mut ready = false;
    for _ in 0..100 {
        if host_socket.exists() && broker_socket.exists() {
            ready = true;
            break;
        }
        assert!(process.child.try_wait().unwrap().is_none());
        thread::sleep(Duration::from_millis(20));
    }
    assert!(ready, "Session must bind both original-owner listeners");
    let before = fs::metadata(&broker_socket).unwrap();
    assert_eq!(before.permissions().mode() & 0o777, 0o600);
    let original_instance =
        match request_at(&host_socket, &trill_ui_core::Request::Snapshot).unwrap() {
            trill_ui_core::Response::Snapshot {
                session_instance,
                tasks,
                ..
            } => {
                assert!(tasks.is_empty());
                session_instance
            }
            response => panic!("unexpected original host reply: {response:?}"),
        };
    // The first accepted Host peer continuously makes sub-timeout progress.
    // Its original per-read timeout could otherwise starve both listeners.
    let mut slow_peer = UnixStream::connect(&host_socket).unwrap();
    slow_peer.write_all(b" ").unwrap();
    let slow_interrupter = slow_peer.try_clone().unwrap();
    let slow_writer = thread::spawn(move || {
        for _ in 0..250 {
            if slow_peer.write_all(b" ").is_err() {
                return;
            }
            thread::sleep(Duration::from_millis(20));
        }
    });
    let following_snapshot = request_at(&host_socket, &trill_ui_core::Request::Snapshot);
    let _ = slow_interrupter.shutdown(Shutdown::Both);
    slow_writer.join().unwrap();
    assert!(matches!(
        following_snapshot.expect("slow Host peer must not starve the next real client"),
        trill_ui_core::Response::Snapshot { .. }
    ));
    for request in [
        Request::Submit {
            request_id: "submit-a".into(),
            intent: intent(),
            delivery: delivery(),
            fence: fence(),
        },
        Request::Cancel {
            request_id: "cancel-a".into(),
            intent: intent(),
            delivery: delivery(),
            fence: fence(),
        },
    ] {
        let reply = exchange_at(
            &broker_socket,
            &ExchangeRequest {
                hello: hello(),
                request,
            },
        )
        .unwrap();
        assert_eq!(reply.session.safety_mode, SafetyMode::DefaultDenyNoEffects);
        assert_eq!(
            reply.session.denied_capabilities,
            vec![Capability::SubmitEffect, Capability::CancelEffect]
        );
        assert!(matches!(
            reply.response,
            Response::Denied {
                code: DenialCode::CapabilityNotGranted,
                ..
            }
        ));
    }
    let draft = exchange_at(
        &broker_socket,
        &ExchangeRequest {
            hello: hello(),
            request: Request::Draft {
                draft: OfflineDraft {
                    draft_id: "draft-a".into(),
                    scope_id: "scope-a".into(),
                    text_digest: "b".repeat(64),
                    created_unix_ms: 1,
                },
            },
        },
    )
    .unwrap();
    assert!(matches!(
        draft.response,
        Response::DraftAccepted {
            durability: DraftDurability::LocalOnly,
            ..
        }
    ));
    let query = exchange_at(
        &broker_socket,
        &ExchangeRequest {
            hello: hello(),
            request: Request::Reconcile {
                intent: intent(),
                delivery: delivery(),
                fence: fence(),
            },
        },
    )
    .unwrap();
    assert!(matches!(
        query.response,
        Response::Operation { reply } if reply.state == OperationState::Unknown
    ));

    // Numeric IDs from replies are never credentials in the new endpoint.
    let mut connection = UnixStream::connect(&broker_socket).unwrap();
    connection
        .set_read_timeout(Some(Duration::from_secs(2)))
        .unwrap();
    connection
        .write_all(b"{\"session_id\":1,\"request\":{\"pull_notifications\":{\"after_sequence\":0,\"max_items\":1}}}\n")
        .unwrap();
    connection.shutdown(Shutdown::Write).unwrap();
    let mut rejected = Vec::new();
    connection.read_to_end(&mut rejected).unwrap();
    assert!(rejected.is_empty());

    let after = fs::metadata(&broker_socket).unwrap();
    assert_eq!((after.dev(), after.ino()), (before.dev(), before.ino()));
    match request_at(&host_socket, &trill_ui_core::Request::Snapshot).unwrap() {
        trill_ui_core::Response::Snapshot {
            session_instance,
            tasks,
            ..
        } => {
            assert_eq!(session_instance, original_instance);
            assert!(tasks.is_empty(), "Organ IPC must not launch a host child");
        }
        response => panic!("unexpected original host reply: {response:?}"),
    }
}

#[test]
fn busy_existing_listener_is_never_unlinked_or_allowed_to_block_session_startup() {
    for name in ["session.sock", "organ.sock"] {
        let runtime = std::env::temp_dir().join(format!(
            "trill-organ-busy-{}-{}-{name}",
            std::process::id(),
            unix_ms()
        ));
        DirBuilder::new().mode(0o700).create(&runtime).unwrap();
        let directory = runtime.join("trillionnium-ui");
        DirBuilder::new().mode(0o700).create(&directory).unwrap();
        let path = directory.join(name);
        let socket = Socket::new(Domain::UNIX, Type::STREAM, None).unwrap();
        socket.bind(&SockAddr::unix(&path).unwrap()).unwrap();
        socket.listen(0).unwrap();
        let listener = UnixListener::from(OwnedFd::from(socket));
        let occupying_peer = UnixStream::connect(&path).unwrap();
        let probe = Socket::new(Domain::UNIX, Type::STREAM, None).unwrap();
        probe.set_nonblocking(true).unwrap();
        assert_eq!(
            probe
                .connect(&SockAddr::unix(&path).unwrap())
                .unwrap_err()
                .kind(),
            io::ErrorKind::WouldBlock,
            "the actual fixture backlog must be full"
        );
        drop(probe);
        let before = fs::metadata(&path).unwrap();
        let mut process = SessionProcess {
            child: command(&runtime).spawn().unwrap(),
            runtime,
        };
        let mut exit = None;
        for _ in 0..100 {
            if let Some(status) = process.child.try_wait().unwrap() {
                exit = Some(status);
                break;
            }
            thread::sleep(Duration::from_millis(20));
        }
        assert!(
            !exit
                .expect("busy stale probe must fail within its deadline")
                .success(),
            "Session must not claim ownership of the occupied endpoint"
        );
        let after = fs::metadata(&path).unwrap();
        assert_eq!((after.dev(), after.ino()), (before.dev(), before.ino()));
        drop(occupying_peer);
        drop(listener);
    }
}
