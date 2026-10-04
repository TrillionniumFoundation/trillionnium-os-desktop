//! Actual kernel objects; private malformed-packet/cookie mutations are named
//! separately. This same-process transport corpus asserts no procfs approval.
use super::*;
use std::io::Write;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::fs::DirBuilderExt;
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

static NEXT: AtomicU64 = AtomicU64::new(0);
struct Fixture {
    sender: PendingHandoffSender,
    receiver: PendingHandoffReceiver,
    _received: ReceivedAcceptedStream,
    client: UnixStream,
    directory: PathBuf,
}
impl Fixture {
    fn new(budget: Duration) -> Self {
        let directory = std::env::temp_dir().join(format!(
            "hepta-ready-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::DirBuilder::new()
            .mode(0o700)
            .create(&directory)
            .unwrap();
        let path = directory.join("agent.sock");
        let listener = UnixListener::bind(&path).unwrap();
        let client = UnixStream::connect(&path).unwrap();
        let (accepted, _) = listener.accept().unwrap();
        let (sender, receiver) = controls();
        let policy = super::super::PeerPolicy {
            expected_pid: Some(std::process::id()),
            expected_uid: unsafe { libc::getuid() },
            expected_gid: Some(unsafe { libc::getgid() }),
        };
        let receiver = HandoffReceiver::from_control(receiver, policy, &path).unwrap();
        let sender = HandoffSender::from_control(sender, policy, Duration::from_secs(2)).unwrap();
        let accepted = AcceptedStreamCustody::capture(accepted, &path, budget).unwrap();
        let sender = sender.send_retained(accepted).unwrap();
        let (received, receiver) = receiver
            .receive_retained(Duration::from_secs(2))
            .unwrap()
            .into_parts()
            .unwrap();
        Self {
            sender,
            receiver,
            _received: received,
            client,
            directory,
        }
    }
    fn control_fd(&self) -> RawFd {
        self.receiver
            .transaction
            .channel
            .stream
            .as_ref()
            .unwrap()
            .as_raw_fd()
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.directory).unwrap();
    }
}
fn controls() -> (OwnedFd, OwnedFd) {
    let mut fds = [-1; 2];
    assert_eq!(
        unsafe {
            libc::socketpair(
                libc::AF_UNIX,
                libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC,
                0,
                fds.as_mut_ptr(),
            )
        },
        0
    );
    unsafe { (OwnedFd::from_raw_fd(fds[0]), OwnedFd::from_raw_fd(fds[1])) }
}
fn report() -> RemoteRetirementReport {
    RemoteRetirementReport::new(RemoteTerminalState::Completed, [4; 32], [5; 32]).unwrap()
}
fn fixture() -> Fixture {
    Fixture::new(Duration::from_secs(2))
}

#[test]
fn readiness_idle_nonconsuming_original_clock_and_report() {
    let mut f = fixture();
    let deadline = f.receiver.deadline().unwrap();
    let captured = f.receiver.transaction.channel.original_identity;
    for _ in 0..50 {
        assert!(!f.receiver.cancel_readable_now().unwrap());
        assert_eq!(f.receiver.deadline().unwrap(), deadline);
        assert!(f.receiver.transaction.channel.original_identity == captured);
    }
    f.receiver.send_report(report()).unwrap();
    assert_eq!(f.sender.wait_report().unwrap(), report());
    assert!(f.receiver.send_report(report()).is_err());
}
#[test]
fn readiness_is_control_not_agent_stream() {
    let mut f = fixture();
    f.client.write_all(b"agent payload").unwrap();
    assert!(!f.receiver.cancel_readable_now().unwrap());
    f.sender.request_cancel().unwrap();
    assert!(f.receiver.cancel_readable_now().unwrap());
    assert!(f.receiver.poll_cancel().unwrap());
    assert!(!f.receiver.cancel_readable_now().unwrap());
}
#[test]
fn readiness_before_first_call_same_credentials_substitution_refuses() {
    let mut f = fixture();
    let fd = f.control_fd();
    let (replacement, _remote) = controls();
    assert_eq!(unsafe { libc::dup2(replacement.as_raw_fd(), fd) }, fd);
    assert_eq!(
        f.receiver.cancel_readable_now(),
        Err(HandoffError::WrongDescriptor)
    );
    assert!(f.receiver.poll_cancel().is_err());
    assert!(unsafe { libc::fcntl(replacement.as_raw_fd(), libc::F_GETFD) } >= 0);
}
#[test]
fn readiness_full_report_gate_detects_same_credentials_later_substitution() {
    let mut f = fixture();
    assert!(!f.receiver.cancel_readable_now().unwrap());
    let fd = f.control_fd();
    let (replacement, _remote) = controls();
    assert_eq!(unsafe { libc::dup2(replacement.as_raw_fd(), fd) }, fd);
    assert_eq!(
        f.receiver.send_report(report()),
        Err(HandoffError::WrongDescriptor)
    );
    assert!(f.receiver.send_report(report()).is_err());
    assert!(unsafe { libc::fcntl(replacement.as_raw_fd(), libc::F_GETFD) } >= 0);
}
#[test]
fn readiness_closed_original_fd_reused_by_same_credentials_refuses() {
    const CASE: &str = "accepted_handoff::retained_control::readiness_tests::readiness_closed_original_fd_reused_by_same_credentials_refuses";
    const CHILD: &str = "HEPTA_CONTROL_READINESS_CLOSE_REUSE_CHILD";
    if std::env::var_os(CHILD).as_deref() != Some(std::ffi::OsStr::new("1")) {
        let result = std::process::Command::new(std::env::current_exe().unwrap())
            .args(["--exact", CASE, "--test-threads=1", "--nocapture"])
            .env(CHILD, "1")
            .output()
            .unwrap();
        assert!(
            result.status.success(),
            "isolated close/reuse child: {:?}\n{}\n{}",
            result.status,
            String::from_utf8_lossy(&result.stdout),
            String::from_utf8_lossy(&result.stderr)
        );
        assert!(String::from_utf8_lossy(&result.stdout).contains("1 passed; 0 failed"));
        return;
    }
    let args: Vec<_> = std::env::args().skip(1).collect();
    assert_eq!(args, ["--exact", CASE, "--test-threads=1", "--nocapture"]);
    let mut f = fixture();
    let fd = f.control_fd();
    let (replacement, _remote) = controls();
    assert_eq!(unsafe { libc::close(fd) }, 0);
    assert_eq!(unsafe { libc::dup2(replacement.as_raw_fd(), fd) }, fd);
    assert_eq!(
        f.receiver.cancel_readable_now(),
        Err(HandoffError::WrongDescriptor)
    );
}
#[test]
fn readiness_private_wrong_agent_cookie_mutation_refuses() {
    let mut f = fixture();
    f.receiver.transaction.channel.original_identity =
        super::super::OriginalControlIdentity(f.receiver.transaction.identity);
    assert_eq!(
        f.receiver.cancel_readable_now(),
        Err(HandoffError::WrongDescriptor)
    );
}
#[test]
fn readiness_repeated_cancel_real_packet_permanently_retires() {
    let mut f = fixture();
    f.sender.request_cancel().unwrap();
    assert!(f.receiver.cancel_readable_now().unwrap());
    assert!(f.receiver.poll_cancel().unwrap());
    // Deliberate private packet fault; public sender forbids this second send.
    let data = f.sender.transaction.encode(CANCEL, None);
    send_packet(f.sender.transaction.verify().unwrap(), &data, None).unwrap();
    assert!(f.receiver.cancel_readable_now().unwrap());
    assert_eq!(f.receiver.poll_cancel(), Err(HandoffError::ProtocolRefused));
    assert!(f.receiver.cancel_readable_now().is_err());
}
#[test]
fn readiness_bad_nonce_and_ancillary_real_packets_refuse() {
    for rights in [false, true] {
        let mut f = fixture();
        let mut data = f.sender.transaction.encode(CANCEL, None);
        if !rights {
            data[96] ^= 1;
        }
        let fd = f.sender.transaction.verify().unwrap();
        send_packet(fd, &data, rights.then_some(fd)).unwrap();
        assert!(f.receiver.cancel_readable_now().unwrap());
        assert_eq!(f.receiver.poll_cancel(), Err(HandoffError::ProtocolRefused));
        assert!(f.receiver.cancel_readable_now().is_err());
    }
}
#[test]
fn readiness_hup_requires_original_raw_full_path() {
    let mut f = fixture();
    let original_ceiling = f.receiver.deadline().unwrap();
    f.sender.transaction.channel.retire();
    // A readiness snapshot is nonblocking; wait for actual HUP under the same
    // original ceiling while the stock parallel harness may spawn children.
    while !f.receiver.cancel_readable_now().unwrap() {
        assert!(Instant::now() < original_ceiling);
        std::thread::sleep(Duration::from_millis(1));
    }
    assert_eq!(
        f.receiver.poll_cancel(),
        Err(HandoffError::ConnectionClosed)
    );
    assert!(f.receiver.cancel_readable_now().is_err());
}
#[test]
fn readiness_private_foreign_creator_fault_refuses_before_fd() {
    let mut f = fixture();
    // Private creator-field mutation is a fault case. The real fork corpus is
    // the single-thread harness=false browserd target, never this unit harness.
    let creator = f.receiver.transaction.channel.owner_pid;
    f.receiver.transaction.channel.owner_pid = 0;
    assert_eq!(
        f.receiver.cancel_readable_now(),
        Err(HandoffError::ProcessChanged)
    );
    f.receiver.transaction.channel.owner_pid = creator;
    assert!(!f.receiver.cancel_readable_now().unwrap());
    f.receiver.send_report(report()).unwrap();
    assert_eq!(f.sender.wait_report().unwrap(), report());
}
#[test]
fn readiness_original_expiry_not_restarted() {
    let mut f = Fixture::new(Duration::from_millis(80));
    let deadline = f.receiver.deadline().unwrap();
    assert!(!f.receiver.cancel_readable_now().unwrap());
    std::thread::sleep(
        deadline.saturating_duration_since(Instant::now()) + Duration::from_millis(2),
    );
    assert_eq!(
        f.receiver.cancel_readable_now(),
        Err(HandoffError::DeadlineExceeded)
    );
    assert!(f.receiver.send_report(report()).is_err());
}
