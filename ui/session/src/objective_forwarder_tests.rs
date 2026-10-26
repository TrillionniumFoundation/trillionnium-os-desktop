use super::*;
use std::io::{self, BufRead, BufReader, Write};
use std::os::unix::fs::{DirBuilderExt, PermissionsExt};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::PathBuf;
use std::sync::atomic::AtomicUsize;
use std::time::Duration;

static NEXT: AtomicUsize = AtomicUsize::new(1);

struct Endpoint {
    directory: PathBuf,
    listener: UnixListener,
}

impl Endpoint {
    fn new() -> Self {
        let directory = std::env::temp_dir().join(format!(
            "trill-forwarder-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        std::fs::DirBuilder::new()
            .mode(0o700)
            .create(&directory)
            .unwrap();
        let path = directory.join("host.sock");
        let listener = UnixListener::bind(&path).unwrap();
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
        listener.set_nonblocking(true).unwrap();
        Self {
            directory,
            listener,
        }
    }

    fn forwarder(&self) -> ObjectiveForwarder {
        ObjectiveForwarder::from_bridge(ObjectiveBridge::at_endpoint(
            self.directory.join("host.sock"),
            std::process::id(),
        ))
    }

    fn no_more_connections(&self) {
        assert_eq!(
            self.listener.accept().unwrap_err().kind(),
            io::ErrorKind::WouldBlock
        );
    }
}

impl Drop for Endpoint {
    fn drop(&mut self) {
        std::fs::remove_dir_all(&self.directory).unwrap();
    }
}

fn accept(listener: &UnixListener) -> (UnixStream, ObjectiveCommand) {
    let until = Instant::now() + Duration::from_secs(3);
    let mut stream = loop {
        match listener.accept() {
            Ok((stream, _)) => break stream,
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                assert!(Instant::now() < until, "transport did not connect");
                std::thread::sleep(Duration::from_millis(1));
            }
            Err(error) => panic!("endpoint accept: {error}"),
        }
    };
    stream
        .set_read_timeout(Some(Duration::from_secs(2)))
        .unwrap();
    let mut frame = String::new();
    BufReader::new(&mut stream).read_line(&mut frame).unwrap();
    (stream, serde_json::from_str(&frame).unwrap())
}

fn reply(mut stream: UnixStream, observation: &ObjectiveObservation) {
    let mut bytes = serde_json::to_vec(observation).unwrap();
    bytes.push(b'\n');
    stream.write_all(&bytes).unwrap();
}

fn receive_reply(pending: &mut PendingReply) -> ObjectiveReply {
    let until = Instant::now() + Duration::from_secs(3);
    loop {
        if let Some(view) = pending.poll() {
            assert!(pending.poll().is_none(), "a response must be consumed once");
            return view;
        }
        assert!(Instant::now() < until, "transport worker did not complete");
        std::thread::sleep(Duration::from_millis(1));
    }
}

fn receive(pending: &mut PendingReply) -> ObjectiveObservation {
    let ObjectiveReply::Observation(view) = receive_reply(pending) else {
        panic!("expected original observation or conservative uncertainty");
    };
    view
}

fn submit(id: &str) -> ObjectiveCommand {
    ObjectiveCommand::Submit {
        intent: ObjectiveIntent {
            client_intent_id: id.into(),
            text: "transport fixture only; no original owner or effect".into(),
        },
    }
}

#[test]
fn forwards_mutations_once_in_fifo_order_and_refuses_full_queue() {
    let endpoint = Endpoint::new();
    let forwarder = endpoint.forwarder();
    let listener = endpoint.listener.try_clone().unwrap();
    let first = submit("original-intent");
    let second = ObjectiveCommand::Cancel {
        client_intent_id: "original-intent".into(),
    };
    let first_view: ObjectiveObservation = serde_json::from_str(include_str!(
        "../../../tests/ui/notes-document-observation-v1.json"
    ))
    .unwrap();
    let mut second_view = first_view.clone();
    second_view.cancellation = ObjectiveCancellation::Unknown;
    let expected = [first_view.clone(), second_view.clone()];
    let (seen, observed) = mpsc::channel();
    let (release, released) = mpsc::channel();
    let server = std::thread::spawn(move || {
        for (index, view) in expected.iter().enumerate() {
            let (stream, command) = accept(&listener);
            seen.send(command).unwrap();
            if index == 0 {
                released.recv_timeout(Duration::from_secs(2)).unwrap();
            }
            reply(stream, view);
        }
    });
    let deadline = Instant::now() + Duration::from_secs(2);
    let mut active = forwarder.request(first.clone(), deadline);
    assert_eq!(
        observed.recv_timeout(Duration::from_secs(2)).unwrap(),
        first
    );
    let mut waiting = forwarder.request(second.clone(), deadline);
    let mut overflow = forwarder.request(submit("overflow"), deadline);
    let ObjectiveReply::Rejected(refused) = receive_reply(&mut overflow) else {
        panic!("queue overflow must have a distinct local transport receipt");
    };
    assert_eq!(refused.reason, ObjectiveTransportRejectionReason::Capacity);
    assert_eq!(refused.request, submit("overflow").transport_request());
    release.send(()).unwrap();
    assert_eq!(receive(&mut active), first_view);
    assert_eq!(receive(&mut waiting), second_view);
    assert_eq!(
        observed.recv_timeout(Duration::from_secs(2)).unwrap(),
        second
    );
    server.join().unwrap();
    endpoint.no_more_connections();
}

#[test]
fn abandoned_and_expired_queued_mutations_never_reach_the_endpoint() {
    for expired in [false, true] {
        let endpoint = Endpoint::new();
        let forwarder = endpoint.forwarder();
        let listener = endpoint.listener.try_clone().unwrap();
        let (seen, observed) = mpsc::channel();
        let (release, released) = mpsc::channel();
        let server = std::thread::spawn(move || {
            let (stream, command) = accept(&listener);
            assert_eq!(command, ObjectiveCommand::Availability {});
            seen.send(()).unwrap();
            released.recv_timeout(Duration::from_secs(2)).unwrap();
            // A timed-out requester may have closed; do not turn the fixture's
            // deliberate hold into a secondary BrokenPipe panic.
            drop(stream);
        });
        let mut active = forwarder.request(
            ObjectiveCommand::Availability {},
            Instant::now() + Duration::from_secs(2),
        );
        observed.recv_timeout(Duration::from_secs(2)).unwrap();
        let mut queued = forwarder.request(
            submit("never-forwarded"),
            Instant::now()
                + if expired {
                    Duration::from_millis(5)
                } else {
                    Duration::from_secs(2)
                },
        );
        if expired {
            std::thread::sleep(Duration::from_millis(10));
        } else {
            // The same atomic transition used by PendingReply::drop. Retain
            // the receiver here so the worker's completed skip is observable.
            queued.permit.abandon();
        }
        release.send(()).unwrap();
        receive(&mut active);
        let skipped = receive(&mut queued);
        assert_eq!(skipped.issue, Some(ObjectiveHostIssue::TransportUnknown));
        assert_eq!(skipped.stage, ObjectiveStage::SubmitUnknown);
        assert!(skipped.run.is_none());
        server.join().unwrap();
        endpoint.no_more_connections();
    }
}

#[test]
fn dropped_forwarder_stops_queued_transport_without_claiming_owner_cancellation() {
    let endpoint = Endpoint::new();
    let forwarder = endpoint.forwarder();
    let listener = endpoint.listener.try_clone().unwrap();
    let (seen, observed) = mpsc::channel();
    let (release, released) = mpsc::channel();
    let server = std::thread::spawn(move || {
        let (stream, _) = accept(&listener);
        seen.send(()).unwrap();
        released.recv_timeout(Duration::from_secs(2)).unwrap();
        drop(stream);
    });
    let deadline = Instant::now() + Duration::from_secs(2);
    let mut active = forwarder.request(submit("already-forwarded"), deadline);
    observed.recv_timeout(Duration::from_secs(2)).unwrap();
    let mut waiting = forwarder.request(
        ObjectiveCommand::Cancel {
            client_intent_id: "already-forwarded".into(),
        },
        deadline,
    );
    drop(forwarder);
    release.send(()).unwrap();
    let active = receive(&mut active);
    assert_eq!(active.stage, ObjectiveStage::SubmitUnknown);
    assert!(active.run.is_none());
    let cancelled = receive(&mut waiting);
    assert_eq!(cancelled.cancellation, ObjectiveCancellation::Unknown);
    assert!(cancelled.run.is_none());
    server.join().unwrap();
    endpoint.no_more_connections();
}

#[test]
fn dropping_a_pending_reply_abandons_its_unsent_ticket() {
    let forwarder = ObjectiveForwarder {
        sender: None,
        stopped: Arc::new(AtomicBool::new(false)),
    };
    let pending = forwarder.request(
        ObjectiveCommand::Availability {},
        Instant::now() + Duration::from_secs(1),
    );
    let permit = pending.permit.clone();
    drop(pending);
    // Check through the real bridge: an abandoned ticket must receive an
    // unknown observation without even opening a trusted endpoint socket.
    let endpoint = Endpoint::new();
    let bridge =
        ObjectiveBridge::at_endpoint(endpoint.directory.join("host.sock"), std::process::id());
    let observation = bridge.request_until(submit("dropped"), &permit);
    assert_eq!(observation.stage, ObjectiveStage::SubmitUnknown);
    endpoint.no_more_connections();
}
