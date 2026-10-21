use trill_ui_broker::{
    AuthError, Broker, Capability, ClientHello, DenialCode, OfflineDraft, PeerCredentials, Request,
    Response, SameUidAuthenticator, SessionHandle,
};

// Keep these acceptance bounds independent of the implementation constants.
const PEER_LIMIT: usize = 16;
const GLOBAL_LIMIT: usize = 128;

fn peer(pid: i32, uid: u32) -> PeerCredentials {
    PeerCredentials { pid, uid, gid: uid }
}

fn hello(sequence: usize) -> ClientHello {
    ClientHello {
        protocol_version: 1,
        client_id: format!("client-{sequence}"),
        session_nonce: format!("session-nonce-{sequence:016}"),
        requested_capabilities: vec![
            Capability::OfflineDraft,
            Capability::SubmitEffect,
            Capability::CancelEffect,
        ],
    }
}

fn open(
    broker: &mut Broker,
    credentials: PeerCredentials,
    sequence: usize,
) -> Result<SessionHandle, AuthError> {
    let (handle, info) = broker.open_session(
        &SameUidAuthenticator {
            expected_uid: credentials.uid,
        },
        hello(sequence),
        credentials,
    )?;
    assert_eq!(info.granted_capabilities, vec![Capability::OfflineDraft]);
    assert_eq!(
        info.denied_capabilities,
        vec![Capability::SubmitEffect, Capability::CancelEffect]
    );
    Ok(handle)
}

fn draft() -> Request {
    Request::Draft {
        draft: OfflineDraft {
            draft_id: "draft-a".into(),
            scope_id: "scope-a".into(),
            text_digest: "a".repeat(64),
            created_unix_ms: 1,
        },
    }
}

#[test]
fn per_peer_capacity_cannot_be_bypassed_by_client_nonce_or_group() {
    let mut broker = Broker::new();
    let credentials = peer(42, 1000);
    let handles: Vec<_> = (0..PEER_LIMIT)
        .map(|i| open(&mut broker, credentials, i).unwrap())
        .collect();

    for sequence in PEER_LIMIT..PEER_LIMIT + 3 {
        let mut changed_group = credentials;
        changed_group.gid = sequence as u32;
        assert!(
            open(&mut broker, changed_group, sequence).is_err(),
            "a kernel peer must remain bounded when client-controlled labels change"
        );
    }

    // An independent kernel peer retains its own quota. Rejections above must
    // not consume local IDs or revoke admitted clients.
    let other_process = open(&mut broker, peer(43, 1000), 100).unwrap();
    let other_user = open(&mut broker, peer(42, 1001), 101).unwrap();
    assert_eq!(other_process.id(), PEER_LIMIT as u64 + 1);
    assert_eq!(other_user.id(), PEER_LIMIT as u64 + 2);
    for handle in handles {
        assert!(matches!(
            broker.handle(&handle, draft()),
            Response::DraftAccepted { .. }
        ));
    }
}

#[test]
fn global_capacity_is_shared_across_peers_and_close_releases_one_slot() {
    let mut broker = Broker::new();
    let handles: Vec<_> = (0..GLOBAL_LIMIT)
        .map(|i| open(&mut broker, peer(i as i32 + 1, 1000), i).unwrap())
        .collect();
    for sequence in GLOBAL_LIMIT..GLOBAL_LIMIT + 3 {
        assert!(open(&mut broker, peer(1000, 2000), sequence).is_err());
    }

    broker.close_session(&handles[0]);
    let replacement = open(&mut broker, peer(1000, 2000), 200).unwrap();
    assert_eq!(replacement.id(), GLOBAL_LIMIT as u64 + 1);
    assert!(open(&mut broker, peer(1001, 2000), 201).is_err());
    assert!(matches!(
        broker.handle(&handles[0], draft()),
        Response::Denied {
            code: DenialCode::UnauthenticatedSession,
            ..
        }
    ));
}

#[test]
fn close_reclaims_peer_quota_even_while_clones_remain() {
    let mut broker = Broker::new();
    let credentials = peer(42, 1000);
    let handles: Vec<_> = (0..PEER_LIMIT)
        .map(|i| open(&mut broker, credentials, i).unwrap())
        .collect();
    let clone = handles[0].clone();
    assert!(open(&mut broker, credentials, 100).is_err());
    broker.close_session(&clone);
    let replacement = open(&mut broker, credentials, 101).unwrap();
    assert_eq!(replacement.id(), PEER_LIMIT as u64 + 1);
    for stale in [&handles[0], &clone] {
        assert!(matches!(
            broker.handle(stale, draft()),
            Response::Denied {
                code: DenialCode::UnauthenticatedSession,
                ..
            }
        ));
    }
}

#[test]
fn only_dropping_the_last_clone_reclaims_admission_capacity() {
    let mut broker = Broker::new();
    let credentials = peer(42, 1000);
    let mut handles: Vec<_> = (0..PEER_LIMIT)
        .map(|i| open(&mut broker, credentials, i).unwrap())
        .collect();
    let last = handles.pop().unwrap();
    let clone = last.clone();
    drop(last);
    assert!(open(&mut broker, credentials, 100).is_err());
    assert!(matches!(
        broker.handle(&clone, draft()),
        Response::DraftAccepted { .. }
    ));
    drop(clone);
    let replacement = open(&mut broker, credentials, 101).unwrap();
    assert_eq!(replacement.id(), PEER_LIMIT as u64 + 1);
    assert!(open(&mut broker, credentials, 102).is_err());
}

#[test]
fn foreign_close_cannot_release_a_local_peer_slot() {
    let mut broker = Broker::new();
    let credentials = peer(42, 1000);
    let handles: Vec<_> = (0..PEER_LIMIT)
        .map(|i| open(&mut broker, credentials, i).unwrap())
        .collect();
    let mut foreign_broker = Broker::new();
    let foreign = open(&mut foreign_broker, credentials, 0).unwrap();
    assert_eq!(foreign.id(), handles[0].id());
    broker.close_session(&foreign);
    assert!(open(&mut broker, credentials, 100).is_err());
    assert!(matches!(
        broker.handle(&handles[0], draft()),
        Response::DraftAccepted { .. }
    ));
}

#[test]
fn authentication_rejection_never_consumes_an_admission_id() {
    let mut broker = Broker::new();
    let authenticator = SameUidAuthenticator { expected_uid: 1000 };
    assert!(broker
        .open_session(&authenticator, hello(0), peer(42, 2000))
        .is_err());
    assert!(broker
        .open_session(&authenticator, hello(1), peer(0, 1000))
        .is_err());
    let mut invalid = hello(2);
    invalid.session_nonce.clear();
    assert!(broker
        .open_session(&authenticator, invalid, peer(42, 1000))
        .is_err());
    assert_eq!(open(&mut broker, peer(42, 1000), 3).unwrap().id(), 1);
}
