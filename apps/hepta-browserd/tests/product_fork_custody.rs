//! Actual fork from single-thread main. The AF_UNIX streams/pidfds are real;
//! procfs facts and the native completion owner are source fixtures only.
use hepta_agent_transport::PeerIdentity;
use hepta_browser_actor::{TaskFlowPrincipal, servo_runtime_pair};
use hepta_browserd::{
    AcceptedProductConnection, BrowserdRuntimeSupervisor, DispatchCompletion, ProductDispatchError,
    ProductRequestCoordinator, ProductRuntimeError, RestartPolicy, RuntimeState,
    product_connection_queue,
};
use hepta_peer_attestation::{PeerRuntimePolicy, ProcfsPeerAttestor};
use hepta_session_core::{JournalId, ManagedOpenPolicy, ReceiptJournal};
use std::fs;
use std::io::{Read, Write};
use std::os::unix::fs::DirBuilderExt;
use std::os::unix::net::UnixStream;
use std::sync::Arc;
use std::time::Duration;

fn main() {
    let root = std::env::temp_dir().join(format!("hepta-product-fork-{}", std::process::id()));
    fs::DirBuilder::new().mode(0o700).create(&root).unwrap();
    let proc_root = root.join("proc");
    fs::create_dir(&proc_root).unwrap();
    let (server, mut client) = UnixStream::pair().unwrap();
    let peer = PeerIdentity::from_stream(&server).unwrap();
    let process = proc_root.join(peer.pid.unwrap().to_string());
    fs::create_dir(&process).unwrap();
    fs::write(
        process.join("status"),
        format!(
            "Uid:\t{0}\t{0}\t{0}\t{0}\nGid:\t{1}\t{1}\t{1}\t{1}\n",
            peer.uid, peer.gid
        ),
    )
    .unwrap();
    let mut stat = vec!["S"; 20];
    stat[19] = "987654";
    fs::write(
        process.join("stat"),
        format!(
            "{} (source-fork-fixture) {}\n",
            peer.pid.unwrap(),
            stat.join(" ")
        ),
    )
    .unwrap();
    fs::write(
        process.join("cgroup"),
        "0::/system.slice/source-fork.service\n",
    )
    .unwrap();
    fs::write(process.join("exe"), b"source-only-fork-executable").unwrap();
    let attestor = ProcfsPeerAttestor::new(proc_root);
    let snapshot = attestor.read_snapshot(peer.pid.unwrap()).unwrap();
    let principal = TaskFlowPrincipal {
        principal_id: "fork-test".into(),
        expected_uid: peer.uid,
        expected_gid: peer.gid,
        expected_systemd_unit: snapshot.systemd_unit.clone().unwrap(),
        expected_cgroup_v2_path: snapshot.cgroup_v2_path.clone(),
        expected_executable_sha256: snapshot.executable_sha256.clone(),
    };
    let connection = AcceptedProductConnection::attest(
        server,
        attestor.clone(),
        &PeerRuntimePolicy::exact(&snapshot),
        Duration::from_secs(5),
    )
    .unwrap();
    let (queued_server, queued_client) = UnixStream::pair().unwrap();
    let queued = AcceptedProductConnection::attest(
        queued_server,
        attestor,
        &PeerRuntimePolicy::exact(&snapshot),
        Duration::from_secs(5),
    )
    .unwrap();
    let (ingress, queue) = product_connection_queue(1).unwrap();
    let cancellation = connection.cancellation();
    let (endpoint, mut native_owner) = servo_runtime_pair(Arc::new(|| {}));
    let id = JournalId([0x61; 16]);
    let store = root.join("receipts");
    let journal = ReceiptJournal::create_managed(&store, id, 1).unwrap();
    let mut coordinator = ProductRequestCoordinator::from_connection(
        principal,
        &connection,
        endpoint,
        journal,
        "source-test-image".into(),
        RestartPolicy::new(3).unwrap(),
    )
    .unwrap();
    let mut supervisor =
        BrowserdRuntimeSupervisor::start(|_| Ok(0usize), RestartPolicy::new(3).unwrap()).unwrap();
    let reference = supervisor.semantic_reference(1);
    let _: Result<(), _> = supervisor.dispatch(reference, |_| {
        DispatchCompletion::IndeterminateAfterDispatch
    });
    let before = fs::read(store.join("segment-0000000000000001.journal")).unwrap();
    let (mut receiver, mut sender) = UnixStream::pair().unwrap();
    // SAFETY: this test main has started no other thread.
    let pid = unsafe { libc::fork() };
    assert!(pid >= 0, "actual fork required");
    if pid == 0 {
        drop(receiver);
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            // Foreign revocation must not shutdown the parent's original socket.
            cancellation.cancel();
            assert_eq!(
                queue.try_next().err(),
                Some(ProductDispatchError::PeerRefused)
            );
            assert_eq!(
                ingress.try_submit(queued).err(),
                Some(ProductDispatchError::PeerRefused)
            );
            assert_eq!(
                coordinator.reconcile_request("made-up", [0; 32]).err(),
                Some(ProductDispatchError::PeerRefused)
            );
            assert_eq!(
                coordinator.content_process_crashed(),
                Err(ProductDispatchError::PeerRefused)
            );
            let (fresh, _owner) = servo_runtime_pair(Arc::new(|| {}));
            assert_eq!(
                coordinator.reconstruct(&connection, fresh),
                Err(ProductDispatchError::PeerRefused)
            );
            coordinator.acknowledge_stable_cycle();
            assert_eq!(
                coordinator.serve_connection(connection).err(),
                Some(ProductDispatchError::PeerRefused)
            );
            assert_eq!(
                supervisor.validate_reference(reference),
                Err(ProductRuntimeError::RuntimeUnavailable)
            );
            assert_eq!(
                supervisor.content_process_crashed().err(),
                Some(ProductRuntimeError::RuntimeUnavailable)
            );
            assert_eq!(
                supervisor.reconstruct(),
                Err(ProductRuntimeError::RuntimeUnavailable)
            );
            supervisor.reconcile_indeterminate();
            assert!(supervisor.replay_blocked());
            assert_eq!(
                supervisor.dispatch(reference, |_| -> DispatchCompletion<()> {
                    panic!("child dispatch executed")
                }),
                Err(ProductRuntimeError::RuntimeUnavailable)
            );
            drop(coordinator);
            assert!(ReceiptJournal::open_managed(&store, id, ManagedOpenPolicy::STRICT).is_err());
        }))
        .is_ok();
        let _ = sender.write_all(&[u8::from(result)]);
        // SAFETY: avoid inherited parent cleanup after explicit handle Drop.
        unsafe {
            libc::_exit(if result { 0 } else { 1 });
        }
    }
    drop(sender);
    receiver
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    let mut result = [0];
    receiver.read_exact(&mut result).unwrap();
    let mut status = 0;
    // SAFETY: reap only the child just created by this test.
    assert_eq!(unsafe { libc::waitpid(pid, &mut status, 0) }, pid);
    assert_eq!(status, 0);
    assert_eq!(result, [1]);
    assert!(queue.try_next().unwrap().is_none());
    ingress.try_submit(queued).unwrap();
    drop(queue.try_next().unwrap().unwrap());
    drop(queued_client);
    assert_eq!(coordinator.state(), RuntimeState::Ready);
    assert_eq!(
        fs::read(store.join("segment-0000000000000001.journal")).unwrap(),
        before
    );
    assert!(ReceiptJournal::open_managed(&store, id, ManagedOpenPolicy::STRICT).is_err());
    native_owner.pump_one();
    assert!(
        native_owner.take_command().is_none(),
        "child must not dispatch native work"
    );
    client.set_nonblocking(true).unwrap();
    let mut bytes = [0];
    assert_eq!(
        client.read(&mut bytes).unwrap_err().kind(),
        std::io::ErrorKind::WouldBlock,
        "child cancellation/Drop must not close the parent's original transport"
    );
    drop(connection);
    drop(coordinator);
    let reopened = ReceiptJournal::open_managed(&store, id, ManagedOpenPolicy::STRICT).unwrap();
    assert!(reopened.is_managed());
    drop(reopened);
    fs::remove_dir_all(&root).unwrap();
    println!(
        "actual fork: inherited product dispatch/recovery/cancellation refused; parent lease and socket preserved"
    );
}
