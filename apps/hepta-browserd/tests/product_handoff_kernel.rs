//! Real Linux descriptor transfer and live /proc/pidfd admission. The peer is
//! an explicitly same-UID Python child, not an approved product principal or
//! installed service. No synthetic identity or Servo completion is used here.
#![cfg(target_os = "linux")]
#![deny(unsafe_op_in_unsafe_fn)]
use hepta_agent_transport::{AcceptedStreamCustody, HandoffReceiver, HandoffSender};
use hepta_agent_transport::{PeerIdentity, PeerPolicy, ReceivedAcceptedStream};
use hepta_browserd::{AcceptedProductConnection, ProductDispatchError, product_connection_queue};
use hepta_peer_attestation::{PeerRuntimePolicy, ProcfsPeerAttestor};
use std::fs;
use std::io::Read;
use std::os::fd::{FromRawFd, OwnedFd};
use std::os::unix::fs::DirBuilderExt;
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::AtomicU64;
use std::sync::atomic::Ordering;
use std::thread;
use std::time::{Duration, Instant};

const WAIT: Duration = Duration::from_secs(5);
static NEXT: AtomicU64 = AtomicU64::new(0);

struct LivePeer {
    root: PathBuf,
    child: Child,
    accepted: Option<UnixStream>,
    attestor: ProcfsPeerAttestor,
    policy: PeerRuntimePolicy,
}
impl LivePeer {
    fn new() -> Self {
        let root = std::env::temp_dir().join(format!(
            "g2-product-received-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::SeqCst)
        ));
        fs::DirBuilder::new().mode(0o700).create(&root).unwrap();
        let path = root.join("original.sock");
        let listener = UnixListener::bind(&path).unwrap();
        let child = Command::new("python3")
            .args([
                "-I", "-c",
                "import socket,sys; s=socket.socket(socket.AF_UNIX); s.settimeout(15); s.connect(sys.argv[1]); s.sendall(b'original-peer'); data=s.recv(1); print('EOF' if data==b'' else 'unexpected-data'); sys.exit(0 if data==b'' else 1)",
            ])
            .arg(&path)
            .stdout(Stdio::piped())
            .spawn().unwrap();
        let (mut accepted, _) = listener.accept().unwrap();
        accepted.set_read_timeout(Some(WAIT)).unwrap();
        let mut bytes = [0; 13];
        accepted.read_exact(&mut bytes).unwrap();
        assert_eq!(&bytes, b"original-peer");
        let peer = PeerIdentity::from_stream(&accepted).unwrap();
        assert_eq!(peer.pid, Some(child.id()));
        let attestor = ProcfsPeerAttestor::default();
        let snapshot = attestor.read_snapshot(child.id()).unwrap();
        assert_eq!(snapshot.pid, child.id());
        assert!(snapshot.start_time_ticks > 0);
        assert_eq!(snapshot.executable_sha256.len(), 64);
        let policy = PeerRuntimePolicy::exact(&snapshot);
        Self {
            root,
            child,
            accepted: Some(accepted),
            attestor,
            policy,
        }
    }
    fn received(&mut self, budget: Duration) -> ReceivedAcceptedStream {
        let path = self.root.join("original.sock");
        let (sending, receiving) = controls();
        // Explicit host fixture policy; both endpoints read actual SO_PEERCRED.
        let control_policy = PeerPolicy::exact(
            PeerIdentity::from_stream(&UnixStream::from(sending.try_clone().unwrap())).unwrap(),
        );
        let mut receiver = HandoffReceiver::from_control(receiving, control_policy, &path).unwrap();
        let mut sender = HandoffSender::from_control(sending, control_policy, WAIT).unwrap();
        let custody =
            AcceptedStreamCustody::capture(self.accepted.take().unwrap(), &path, budget).unwrap();
        sender.send(custody).unwrap();
        receiver.receive(WAIT).unwrap()
    }
    fn assert_eof(&mut self) {
        assert!(self.child.wait().unwrap().success());
        let mut output = String::new();
        self.child
            .stdout
            .take()
            .unwrap()
            .read_to_string(&mut output)
            .unwrap();
        assert_eq!(output.trim(), "EOF");
    }
}
impl Drop for LivePeer {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
        let _ = fs::remove_dir_all(&self.root);
    }
}
fn controls() -> (OwnedFd, OwnedFd) {
    let mut descriptors = [-1; 2];
    // SAFETY: socketpair fills initialized storage with two fresh descriptors.
    assert_eq!(
        unsafe {
            libc::socketpair(
                libc::AF_UNIX,
                libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC,
                0,
                descriptors.as_mut_ptr(),
            )
        },
        0
    );
    // SAFETY: each fresh descriptor is owned by one OwnedFd exactly once.
    unsafe {
        (
            OwnedFd::from_raw_fd(descriptors[0]),
            OwnedFd::from_raw_fd(descriptors[1]),
        )
    }
}
fn real_rights_live_pidfd_and_absolute_deadline_survive_consumption() {
    let mut live = LivePeer::new();
    let received = live.received(WAIT);
    let deadline = received.deadline().unwrap();
    let connection =
        AcceptedProductConnection::from_received(received, live.attestor.clone(), &live.policy)
            .unwrap();
    assert_eq!(connection.deadline().unwrap(), deadline);
    connection.cancellation().cancel();
    live.assert_eof();
}

fn delayed_receiver_and_product_queue_never_restart_the_captured_budget() {
    let mut live = LivePeer::new();
    let received = live.received(Duration::from_secs(4));
    let deadline = received.deadline().unwrap();
    thread::sleep(Duration::from_millis(500));
    let connection =
        AcceptedProductConnection::from_received(received, live.attestor.clone(), &live.policy)
            .unwrap();
    assert_eq!(
        connection.deadline().unwrap(),
        deadline,
        "no new Duration-based admission clock"
    );
    assert!(
        connection
            .deadline()
            .unwrap()
            .saturating_duration_since(Instant::now())
            < Duration::from_millis(3500)
    );
    let (ingress, queue) = product_connection_queue(1).unwrap();
    ingress.try_submit(connection).unwrap();
    thread::sleep(deadline.saturating_duration_since(Instant::now()) + Duration::from_millis(20));
    let queued = queue.try_next().unwrap().unwrap();
    assert_eq!(
        queued.deadline().err(),
        Some(ProductDispatchError::DeadlineExceeded)
    );
    drop(queued);
    live.assert_eof();
}

fn expired_received_custody_refuses_before_live_attestor_and_closes_original() {
    let mut live = LivePeer::new();
    let received = live.received(Duration::from_millis(100));
    thread::sleep(Duration::from_millis(150));
    assert_eq!(
        AcceptedProductConnection::from_received(
            received,
            ProcfsPeerAttestor::new(live.root.join("absent-proc")),
            &live.policy
        )
        .err(),
        Some(ProductDispatchError::DeadlineExceeded)
    );
    live.assert_eof();
}

fn live_policy_refusal_consumes_received_stream_and_never_queues_it() {
    let mut live = LivePeer::new();
    let received = live.received(WAIT);
    let mut wrong = live.policy.clone();
    wrong.expected_uid = wrong.expected_uid.checked_add(1).unwrap();
    assert_eq!(
        AcceptedProductConnection::from_received(received, live.attestor.clone(), &wrong).err(),
        Some(ProductDispatchError::PeerRefused)
    );
    live.assert_eof();
}

fn actual_peer_death_after_transfer_refuses_live_pidfd_admission() {
    let mut live = LivePeer::new();
    let received = live.received(WAIT);
    live.child.kill().unwrap();
    live.child.wait().unwrap();
    assert_eq!(
        AcceptedProductConnection::from_received(received, live.attestor.clone(), &live.policy)
            .err(),
        Some(ProductDispatchError::PeerRefused)
    );
}

fn original_cancellation_survives_received_stream_queue_handoff() {
    let mut live = LivePeer::new();
    let received = live.received(WAIT);
    let connection =
        AcceptedProductConnection::from_received(received, live.attestor.clone(), &live.policy)
            .unwrap();
    let (ingress, queue) = product_connection_queue(1).unwrap();
    let cancellation = ingress.try_submit(connection).unwrap();
    cancellation.cancel();
    let queued = queue.try_next().unwrap().unwrap();
    assert_eq!(
        queued.deadline().err(),
        Some(ProductDispatchError::Cancelled)
    );
    live.assert_eof();
    drop(queued);
}

fn inherited_consumer_observation_and_cancellation_refuse_before_locks() {
    let mut live = LivePeer::new();
    let received = live.received(WAIT);
    let connection =
        AcceptedProductConnection::from_received(received, live.attestor.clone(), &live.policy)
            .unwrap();
    let deadline = connection.deadline().unwrap();
    // SAFETY: this harness has a single-thread main; child uses only the
    // creator-PID refusal paths, owned descriptor teardown and then _exit.
    let child = unsafe { libc::fork() };
    assert!(child >= 0);
    if child == 0 {
        assert_eq!(
            connection.deadline().err(),
            Some(ProductDispatchError::PeerRefused)
        );
        connection.cancellation().cancel();
        drop(connection);
        unsafe { libc::_exit(0) }
    }
    let mut status = 0;
    assert_eq!(unsafe { libc::waitpid(child, &mut status, 0) }, child);
    assert!(libc::WIFEXITED(status));
    assert_eq!(libc::WEXITSTATUS(status), 0);
    assert_eq!(connection.deadline().unwrap(), deadline);
    connection.cancellation().cancel();
    live.assert_eof();
}

fn main() {
    let cases: [(&str, fn()); 7] = [
        (
            "real_rights_live_pidfd_and_absolute_deadline_survive_consumption",
            real_rights_live_pidfd_and_absolute_deadline_survive_consumption,
        ),
        (
            "delayed_receiver_and_product_queue_never_restart_the_captured_budget",
            delayed_receiver_and_product_queue_never_restart_the_captured_budget,
        ),
        (
            "expired_received_custody_refuses_before_live_attestor_and_closes_original",
            expired_received_custody_refuses_before_live_attestor_and_closes_original,
        ),
        (
            "live_policy_refusal_consumes_received_stream_and_never_queues_it",
            live_policy_refusal_consumes_received_stream_and_never_queues_it,
        ),
        (
            "actual_peer_death_after_transfer_refuses_live_pidfd_admission",
            actual_peer_death_after_transfer_refuses_live_pidfd_admission,
        ),
        (
            "original_cancellation_survives_received_stream_queue_handoff",
            original_cancellation_survives_received_stream_queue_handoff,
        ),
        (
            "inherited_consumer_observation_and_cancellation_refuse_before_locks",
            inherited_consumer_observation_and_cancellation_refuse_before_locks,
        ),
    ];
    for (name, case) in cases {
        case();
        println!("PASS {name}");
    }
    println!("7 actual Linux handoff-consumer cases; source mechanism only");
}
