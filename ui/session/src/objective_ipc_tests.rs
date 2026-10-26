use super::*;
use crate::objective_bridge::ObjectiveBridge;
use crate::objective_forwarder::ObjectiveForwarder;
use std::io::{BufRead, BufReader};
use std::os::fd::AsRawFd;
use std::os::unix::fs::{DirBuilderExt, PermissionsExt};
use std::path::PathBuf;
use std::sync::mpsc;
use std::time::Duration;
use trill_ui_core::objective::*;
use trill_ui_core::{read_frame, AppKind, Request, TaskState, Workspace};

#[test]
fn pending_objective_allows_snapshot_reap_and_keeps_one_response_under_backpressure() {
    let directory =
        std::env::temp_dir().join(format!("trill-objective-ipc-{}", std::process::id()));
    std::fs::DirBuilder::new()
        .mode(0o700)
        .create(&directory)
        .unwrap();
    struct Cleanup(PathBuf);
    impl Drop for Cleanup {
        fn drop(&mut self) {
            std::fs::remove_dir_all(&self.0).unwrap();
        }
    }
    let _cleanup = Cleanup(directory.clone());
    let path = directory.join("host.sock");
    let listener = UnixListener::bind(&path).unwrap();
    listener.set_nonblocking(true).unwrap();
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
    let backend = listener.try_clone().unwrap();
    let mut observation = ObjectiveObservation::new(None, ObjectiveStage::Ready);
    observation.retained_intents = Some(ObjectiveRetainedIntents {
        client_intent_ids: (0..128)
            .map(|index| format!("{index:03}{}", "x".repeat(90)))
            .collect(),
        complete: true,
    });
    let original_view = observation.clone();
    let (read, was_read) = mpsc::channel();
    let (release, released) = mpsc::channel();
    let owner = std::thread::spawn(move || {
        let until = Instant::now() + Duration::from_secs(3);
        let mut stream = loop {
            match backend.accept() {
                Ok((stream, _)) => break stream,
                Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                    assert!(Instant::now() < until);
                    std::thread::sleep(Duration::from_millis(1));
                }
                Err(error) => panic!("fixed endpoint accept: {error}"),
            }
        };
        stream
            .set_read_timeout(Some(Duration::from_secs(2)))
            .unwrap();
        let mut frame = String::new();
        BufReader::new(&mut stream).read_line(&mut frame).unwrap();
        assert_eq!(
            serde_json::from_str::<ObjectiveCommand>(&frame).unwrap(),
            ObjectiveCommand::Availability {}
        );
        read.send(()).unwrap();
        released.recv_timeout(Duration::from_secs(2)).unwrap();
        write_frame(&mut stream, &original_view).unwrap();
    });
    let mut session = Session::new(PathBuf::from("/bin/true")).unwrap();
    session.objective =
        ObjectiveForwarder::from_bridge(ObjectiveBridge::at_endpoint(path, std::process::id()));
    assert!(matches!(
        session.handle(
            Request::ObjectiveAvailability {
                expected_instance: "stale-generation".into(),
            },
            Instant::now() + EXCHANGE_BUDGET,
        ),
        SessionReply::Ready(Response::Error { .. })
    ));
    let Response::Task { task, .. } = session.launch(Workspace::Build, AppKind::Calculator) else {
        panic!("expected the owned /bin/true child");
    };
    session.children.get_mut(&task.id).unwrap().wait().unwrap();
    let (mut waiting, waiting_stream) = UnixStream::pair().unwrap();
    let buffer_bytes: libc::c_int = 4096;
    assert_eq!(
        unsafe {
            libc::setsockopt(
                waiting_stream.as_raw_fd(),
                libc::SOL_SOCKET,
                libc::SO_SNDBUF,
                (&buffer_bytes as *const libc::c_int).cast(),
                std::mem::size_of_val(&buffer_bytes) as libc::socklen_t,
            )
        },
        0
    );
    write_frame(
        &mut waiting,
        &Request::ObjectiveAvailability {
            expected_instance: session.instance.clone(),
        },
    )
    .unwrap();
    // A second buffered frame cannot turn response backpressure into another
    // forwarding attempt, including a mutation sent after the first query.
    write_frame(
        &mut waiting,
        &Request::ObjectiveCancel {
            client_intent_id: "not-forwarded".into(),
            expected_instance: session.instance.clone(),
        },
    )
    .unwrap();
    let (mut fast, fast_stream) = UnixStream::pair().unwrap();
    fast.set_read_timeout(Some(Duration::from_secs(1))).unwrap();
    write_frame(&mut fast, &Request::Snapshot).unwrap();
    let deadline = Instant::now() + Duration::from_secs(3);
    let mut server = Server {
        connections: [waiting_stream, fast_stream]
            .into_iter()
            .map(|stream| Connection::new(stream, deadline).unwrap())
            .collect(),
    };
    server.advance(&mut session);
    was_read.recv_timeout(Duration::from_secs(2)).unwrap();
    let Response::Snapshot { tasks, .. } =
        serde_json::from_slice(&read_frame(&mut fast).unwrap()).unwrap()
    else {
        panic!("unrelated snapshot was blocked by Objective transport");
    };
    assert_eq!(tasks[0].id, task.id);
    assert_eq!(tasks[0].state, TaskState::Completed);
    assert!(session.children.is_empty());
    assert_eq!(server.connections.len(), 1);
    assert!(server.connections[0].pending.is_some());
    assert!(server.connections[0].output.is_none());
    release.send(()).unwrap();
    while server.connections[0].output.is_none() {
        assert!(Instant::now() < deadline);
        server.advance(&mut session);
        std::thread::sleep(Duration::from_millis(1));
    }
    owner.join().unwrap();
    let retained = server.connections[0].output.clone().unwrap();
    for _ in 0..8 {
        server.advance(&mut session);
    }
    assert_eq!(server.connections.len(), 1);
    assert_eq!(server.connections[0].output.as_ref().unwrap(), &retained);
    assert!(server.connections[0].pending.is_none());
    waiting.set_nonblocking(true).unwrap();
    let mut delivered = Vec::new();
    while !delivered.ends_with(b"\n") {
        assert!(Instant::now() < deadline);
        let mut bytes = [0; 4096];
        match waiting.read(&mut bytes) {
            Ok(0) => panic!("response was truncated"),
            Ok(count) => delivered.extend_from_slice(&bytes[..count]),
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => {}
            Err(error) => panic!("reading retained response: {error}"),
        }
        server.advance(&mut session);
    }
    assert_eq!(delivered, retained);
    let Response::Objective {
        observation: received,
        ..
    } = serde_json::from_slice(&delivered).unwrap()
    else {
        panic!("typed observation was not preserved");
    };
    assert_eq!(received, observation);
    assert!(server.connections.is_empty());
    assert_eq!(
        listener.accept().unwrap_err().kind(),
        io::ErrorKind::WouldBlock
    );
}
