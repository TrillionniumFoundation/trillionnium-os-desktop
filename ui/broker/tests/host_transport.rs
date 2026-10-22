#![cfg(target_os = "linux")]

use socket2::{Domain, SockAddr, Socket, Type};
use std::fs;
use std::io::{self, Read, Write};
use std::net::Shutdown;
use std::os::fd::OwnedFd;
use std::os::unix::net::{UnixListener, UnixStream};
use std::sync::mpsc;
use std::thread;
use std::time::Duration;
use trill_ui_broker::host::{exchange_at, serve_exchange, ExchangeReply, ExchangeRequest};
use trill_ui_broker::{
    peer_credentials_from_unix, Broker, Capability, ClientHello, DenialCode, DraftDurability,
    OfflineDraft, Request, Response, SameUidAuthenticator,
};
use trill_ui_core::{read_frame, unix_ms, write_frame, MAX_FRAME};

fn exchange() -> ExchangeRequest {
    ExchangeRequest {
        hello: ClientHello {
            protocol_version: 1,
            client_id: "real-host-peer".into(),
            session_nonce: "host-nonce-0123456789".into(),
            requested_capabilities: vec![
                Capability::OfflineDraft,
                Capability::SubmitEffect,
                Capability::CancelEffect,
            ],
        },
        request: Request::Draft {
            draft: OfflineDraft {
                draft_id: "local-draft".into(),
                scope_id: "scope-a".into(),
                text_digest: "a".repeat(64),
                created_unix_ms: 1,
            },
        },
    }
}

fn encoded() -> Vec<u8> {
    let mut bytes = Vec::new();
    write_frame(&mut bytes, &exchange()).unwrap();
    bytes
}

fn next_id(broker: &mut Broker) -> u64 {
    let (server, _client) = UnixStream::pair().unwrap();
    let peer = peer_credentials_from_unix(&server).unwrap();
    let (session, _) = broker
        .open_session(
            &SameUidAuthenticator {
                expected_uid: peer.uid,
            },
            exchange().hello,
            peer,
        )
        .unwrap();
    let id = session.id();
    broker.close_session(&session);
    id
}

#[test]
fn real_connections_close_every_session_and_never_grant_effects() {
    let mut broker = Broker::new();
    for expected_id in 1..=40 {
        let (server, mut client) = UnixStream::pair().unwrap();
        let observed = peer_credentials_from_unix(&server).unwrap();
        assert_eq!(observed.pid, std::process::id() as i32);
        client.write_all(&encoded()).unwrap();
        client.shutdown(Shutdown::Write).unwrap();
        serve_exchange(server, &mut broker).unwrap();
        let reply: ExchangeReply =
            serde_json::from_slice(&read_frame(&mut client).unwrap()).unwrap();
        assert_eq!(reply.session.session_id, expected_id);
        assert_eq!(
            reply.session.granted_capabilities,
            vec![Capability::OfflineDraft]
        );
        assert_eq!(
            reply.session.denied_capabilities,
            vec![Capability::SubmitEffect, Capability::CancelEffect]
        );
        assert!(matches!(
            reply.response,
            Response::DraftAccepted {
                durability: DraftDurability::LocalOnly,
                ..
            }
        ));
        // Explicit close, rather than a lingering strong handle or lazy sweep.
        assert_eq!(broker.reap_sessions(), 0);
    }
    assert_eq!(next_id(&mut broker), 41);
}

#[test]
fn strict_raw_frames_reject_nested_duplicates_and_claimed_credentials_before_admission() {
    let good = String::from_utf8(encoded()).unwrap();
    let invalid = vec![
        good.replacen("{", "{\"uid\":0,", 1),
        good.replacen("{", "{\"session_id\":1,", 1),
        good.replacen("\"hello\":{", "\"hello\":{\"role\":\"owner\",", 1),
        good.replacen(
            "\"protocol_version\":1",
            "\"protocol_version\":1,\"protocol_version\":1",
            1,
        ),
        good.replacen(
            "\"draft_id\":\"local-draft\"",
            "\"draft_id\":\"local-draft\",\"draft_id\":\"other\"",
            1,
        ),
        format!("{}{}", good, good),
        format!("{}trailing", good),
        good.trim_end().to_string(),
        "x".repeat(MAX_FRAME + 1),
    ];
    for frame in invalid {
        let mut broker = Broker::new();
        let (server, mut client) = UnixStream::pair().unwrap();
        client.write_all(frame.as_bytes()).unwrap();
        client.shutdown(Shutdown::Write).unwrap();
        assert_eq!(
            serve_exchange(server, &mut broker).unwrap_err().kind(),
            io::ErrorKind::InvalidData
        );
        assert_eq!(next_id(&mut broker), 1);
    }
}

#[test]
fn invalid_version_and_unsupported_capabilities_still_follow_original_broker_policy() {
    let mut broker = Broker::new();
    let mut request = exchange();
    request.hello.protocol_version = 2;
    let (server, mut client) = UnixStream::pair().unwrap();
    write_frame(&mut client, &request).unwrap();
    client.shutdown(Shutdown::Write).unwrap();
    assert_eq!(
        serve_exchange(server, &mut broker).unwrap_err().kind(),
        io::ErrorKind::PermissionDenied
    );
    assert_eq!(next_id(&mut broker), 1);

    request = exchange();
    request.hello.requested_capabilities = vec![Capability::SubmitEffect];
    let (server, mut client) = UnixStream::pair().unwrap();
    write_frame(&mut client, &request).unwrap();
    client.shutdown(Shutdown::Write).unwrap();
    serve_exchange(server, &mut broker).unwrap();
    let reply: ExchangeReply = serde_json::from_slice(&read_frame(&mut client).unwrap()).unwrap();
    assert!(reply.session.granted_capabilities.is_empty());
    assert!(matches!(
        reply.response,
        Response::Denied {
            code: DenialCode::CapabilityNotGranted,
            ..
        }
    ));
}

#[test]
fn valid_line_without_eof_is_not_executed_and_does_not_allocate_an_id() {
    let mut broker = Broker::new();
    let (server, mut client) = UnixStream::pair().unwrap();
    client.write_all(&encoded()).unwrap();
    let error = serve_exchange(server, &mut broker).unwrap_err();
    assert!(matches!(
        error.kind(),
        io::ErrorKind::TimedOut | io::ErrorKind::WouldBlock
    ));
    assert_eq!(next_id(&mut broker), 1);
}

#[test]
fn slow_progress_cannot_reset_the_complete_exchange_deadline() {
    let (server, mut client) = UnixStream::pair().unwrap();
    let interrupter = client.try_clone().unwrap();
    let (finished, completion) = mpsc::channel();
    let server_thread = thread::spawn(move || {
        let mut broker = Broker::new();
        let result = serve_exchange(server, &mut broker);
        finished.send((result, next_id(&mut broker))).unwrap();
    });
    let writer_thread = thread::spawn(move || {
        for _ in 0..100 {
            if client.write_all(b" ").is_err() {
                return;
            }
            thread::sleep(Duration::from_millis(20));
        }
    });
    // The watchdog also releases a regressed implementation, keeping this
    // real socket negative control finite rather than stranding the suite.
    let completed = completion.recv_timeout(Duration::from_millis(1500));
    let _ = interrupter.shutdown(Shutdown::Both);
    writer_thread.join().unwrap();
    server_thread.join().unwrap();
    let (result, next) = completed.expect("slow peer exceeded the complete-frame budget");
    assert!(matches!(
        result.unwrap_err().kind(),
        io::ErrorKind::TimedOut | io::ErrorKind::WouldBlock
    ));
    assert_eq!(next, 1);
}

#[test]
fn disconnected_reply_closes_the_admitted_handle_without_retry() {
    let mut broker = Broker::new();
    let (server, mut client) = UnixStream::pair().unwrap();
    client.write_all(&encoded()).unwrap();
    client.shutdown(Shutdown::Write).unwrap();
    client.shutdown(Shutdown::Read).unwrap();
    assert!(serve_exchange(server, &mut broker).is_err());
    assert_eq!(broker.reap_sessions(), 0);
    assert_eq!(next_id(&mut broker), 2);
    let mut reply = Vec::new();
    client.read_to_end(&mut reply).unwrap();
    assert!(reply.is_empty());
}

#[test]
fn a_full_listener_backlog_cannot_block_client_connection_without_a_deadline() {
    let path = std::env::temp_dir().join(format!(
        "trill-broker-backlog-{}-{}.sock",
        std::process::id(),
        unix_ms()
    ));
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
        "the actual Linux listener backlog must be full before testing the client"
    );
    drop(probe);
    let (finished, completion) = mpsc::channel();
    let endpoint = path.clone();
    let client_thread = thread::spawn(move || {
        finished.send(exchange_at(&endpoint, &exchange())).unwrap();
    });
    let completed = completion.recv_timeout(Duration::from_secs(3));
    // Closing the owned fixture listener also releases a regressed blocking
    // connect, so a failed control cannot strand a thread or another test.
    drop(listener);
    drop(occupying_peer);
    client_thread.join().unwrap();
    fs::remove_file(path).unwrap();
    assert!(completed
        .expect("client remained blocked on a full backlog")
        .is_err());
}
