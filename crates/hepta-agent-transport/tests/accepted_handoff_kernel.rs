//! Actual Linux kernel corpus. No synthetic procfs, injected kernel identity,
//! product daemon activation, Servo callback or installed-runtime claim.
#![cfg(target_os = "linux")]
#![deny(unsafe_op_in_unsafe_fn)]

use hepta_agent_transport::{
    AcceptedStreamCustody, HandoffError, HandoffReceiver, HandoffSender, MAX_HANDOFF_BUDGET,
    MAX_HANDOFFS_PER_CHANNEL, PeerIdentity, PeerPolicy,
};
use std::fs;
use std::io::{Read, Write};
use std::mem::{size_of, size_of_val, zeroed};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::os::unix::fs::{DirBuilderExt, MetadataExt};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, Instant};

const WAIT: Duration = Duration::from_secs(2);
static NEXT: AtomicU64 = AtomicU64::new(0);
struct Directory(PathBuf);
impl Directory {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "g2fd-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::DirBuilder::new().mode(0o700).create(&path).unwrap();
        assert_eq!(fs::metadata(&path).unwrap().mode() & 0o777, 0o700);
        Self(path)
    }
}
impl Drop for Directory {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.0).unwrap();
    }
}
fn original(path: &Path) -> (UnixStream, UnixStream) {
    let listener = UnixListener::bind(path).unwrap();
    let client = UnixStream::connect(path).unwrap();
    let (accepted, _) = listener.accept().unwrap();
    (accepted, client)
}
fn controls() -> (OwnedFd, OwnedFd) {
    let mut descriptors = [-1; 2];
    // SAFETY: socketpair initializes two fresh descriptors in live storage.
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
    // SAFETY: each fresh integer is transferred into exactly one owned object.
    unsafe {
        (
            OwnedFd::from_raw_fd(descriptors[0]),
            OwnedFd::from_raw_fd(descriptors[1]),
        )
    }
}
fn policy() -> PeerPolicy {
    // Expected configuration for this explicitly same-process host fixture;
    // the implementation independently reads actual kernel credentials.
    PeerPolicy {
        expected_pid: Some(std::process::id()),
        expected_uid: unsafe { libc::getuid() },
        expected_gid: Some(unsafe { libc::getgid() }),
    }
}
fn channels(path: &Path) -> (HandoffSender, HandoffReceiver) {
    let (sender, receiver) = controls();
    let receiver = HandoffReceiver::from_control(receiver, policy(), path).unwrap();
    let sender = HandoffSender::from_control(sender, policy(), WAIT).unwrap();
    (sender, receiver)
}
fn raw_receiver(path: &Path) -> (UnixStream, HandoffReceiver, [u8; 32]) {
    let (sender, receiver) = controls();
    let receiver = HandoffReceiver::from_control(receiver, policy(), path).unwrap();
    let mut sender = UnixStream::from(sender);
    let mut challenge = [0; 40];
    assert_eq!(sender.read(&mut challenge).unwrap(), 40);
    assert_eq!(&challenge[..8], b"HPTAFDC1");
    let mut nonce = [0; 32];
    nonce.copy_from_slice(&challenge[8..]);
    (sender, receiver, nonce)
}
fn socket_identity(fd: RawFd) -> (u64, u64, u64) {
    let mut cookie = 0u64;
    let mut length = size_of::<u64>() as libc::socklen_t;
    // SAFETY: getsockopt/fstat write live bounded integer/metadata storage.
    assert_eq!(
        unsafe {
            libc::getsockopt(
                fd,
                libc::SOL_SOCKET,
                libc::SO_COOKIE,
                std::ptr::addr_of_mut!(cookie).cast(),
                &mut length,
            )
        },
        0
    );
    let mut stat: libc::stat = unsafe { zeroed() };
    assert_eq!(unsafe { libc::fstat(fd, &mut stat) }, 0);
    (cookie, stat.st_dev, stat.st_ino)
}
fn nanos() -> u64 {
    let mut value: libc::timespec = unsafe { zeroed() };
    assert_eq!(
        unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut value) },
        0
    );
    value.tv_sec as u64 * 1_000_000_000 + value.tv_nsec as u64
}
fn raw_packet(fd: RawFd, nonce: &[u8; 32], sequence: u64, budget: Duration) -> [u8; 128] {
    // Independent fixture encoder for this separate closed handoff contract.
    // All identity/clock values come from the actual kernel/boot namespace.
    let mut data = [0; 128];
    data[..8].copy_from_slice(b"HPTAFD01");
    data[8..10].copy_from_slice(&1u16.to_be_bytes());
    data[16..24].copy_from_slice(&sequence.to_be_bytes());
    let boot = fs::read_to_string("/proc/sys/kernel/random/boot_id")
        .unwrap()
        .trim()
        .replace('-', "");
    for index in 0..16 {
        data[24 + index] = u8::from_str_radix(&boot[index * 2..index * 2 + 2], 16).unwrap();
    }
    let started = nanos();
    let identity = socket_identity(fd);
    let namespace = fs::File::open("/proc/thread-self/ns/time")
        .unwrap()
        .metadata()
        .unwrap();
    for (offset, value) in [
        (40, started),
        (48, started + budget.as_nanos() as u64),
        (56, identity.0),
        (64, identity.1),
        (72, identity.2),
        (80, namespace.dev()),
        (88, namespace.ino()),
    ] {
        data[offset..offset + 8].copy_from_slice(&value.to_be_bytes());
    }
    data[96..].copy_from_slice(nonce);
    data
}
fn raw_send(control: &UnixStream, data: &[u8], descriptors: &[RawFd]) {
    let mut storage = [0usize; 160];
    let mut vector = libc::iovec {
        iov_base: data.as_ptr().cast_mut().cast(),
        iov_len: data.len(),
    };
    let mut message: libc::msghdr = unsafe { zeroed() };
    message.msg_iov = &mut vector;
    message.msg_iovlen = 1;
    if !descriptors.is_empty() {
        message.msg_control = storage.as_mut_ptr().cast();
        unsafe {
            message.msg_controllen = libc::CMSG_SPACE(size_of_val(descriptors) as u32) as usize;
            let header = libc::CMSG_FIRSTHDR(&message);
            (*header).cmsg_level = libc::SOL_SOCKET;
            (*header).cmsg_type = libc::SCM_RIGHTS;
            (*header).cmsg_len = libc::CMSG_LEN(size_of_val(descriptors) as u32) as usize;
            std::ptr::copy_nonoverlapping(
                descriptors.as_ptr().cast::<u8>(),
                libc::CMSG_DATA(header),
                size_of_val(descriptors),
            );
        }
    }
    assert_eq!(
        unsafe { libc::sendmsg(control.as_raw_fd(), &message, libc::MSG_NOSIGNAL) },
        data.len() as isize
    );
}
fn inventory() -> Vec<u32> {
    let mut descriptors: Vec<u32> = fs::read_dir("/proc/self/fd")
        .unwrap()
        .map(|entry| {
            entry
                .unwrap()
                .file_name()
                .to_str()
                .unwrap()
                .parse()
                .unwrap()
        })
        .collect();
    descriptors.sort_unstable();
    descriptors
}
fn eof(client: &mut UnixStream) {
    client.set_read_timeout(Some(WAIT)).unwrap();
    let mut byte = [0];
    assert_eq!(client.read(&mut byte).unwrap(), 0);
}

fn original_kernel_identity_and_bytes_survive_handoff() {
    let directory = Directory::new();
    let path = directory.0.join("original.sock");
    let (accepted, mut client) = original(&path);
    let identity = socket_identity(accepted.as_raw_fd());
    let peer = PeerIdentity::from_stream(&accepted).unwrap();
    let (mut sender, mut receiver) = channels(&path);
    let custody = AcceptedStreamCustody::capture(accepted, &path, WAIT).unwrap();
    sender.send(custody).unwrap();
    let received = receiver.receive(WAIT).unwrap();
    client.write_all(b"original opaque bytes").unwrap();
    let fixed_deadline = received.deadline().unwrap();
    received
        .consume_before(|mut stream, deadline| {
            assert_eq!(deadline, fixed_deadline);
            assert_eq!(socket_identity(stream.as_raw_fd()), identity);
            assert_eq!(PeerIdentity::from_stream(&stream).unwrap(), peer);
            assert!(
                unsafe { libc::fcntl(stream.as_raw_fd(), libc::F_GETFD) } & libc::FD_CLOEXEC != 0
            );
            let mut bytes = [0; 21];
            stream.read_exact(&mut bytes).unwrap();
            assert_eq!(&bytes, b"original opaque bytes");
            stream.write_all(b"same connection response").unwrap();
        })
        .unwrap();
    let mut response = [0; 24];
    client.read_exact(&mut response).unwrap();
    assert_eq!(&response, b"same connection response");
}
fn sender_and_receiver_waits_do_not_renew_original_budget() {
    let directory = Directory::new();
    let path = directory.0.join("original.sock");
    let (accepted, _client) = original(&path);
    let custody =
        AcceptedStreamCustody::capture(accepted, &path, Duration::from_millis(500)).unwrap();
    std::thread::sleep(Duration::from_millis(120));
    let (mut sender, mut receiver) = channels(&path);
    sender.send(custody).unwrap();
    std::thread::sleep(Duration::from_millis(80));
    let received = receiver.receive(WAIT).unwrap();
    assert!(
        received
            .deadline()
            .unwrap()
            .saturating_duration_since(Instant::now())
            <= Duration::from_millis(300)
    );
    let deadline = received.deadline().unwrap();
    std::thread::sleep(Duration::from_millis(20));
    assert_eq!(received.deadline().unwrap(), deadline);
}
fn queued_expiry_closes_original_without_consumer_call() {
    let directory = Directory::new();
    let path = directory.0.join("original.sock");
    let (accepted, mut client) = original(&path);
    let (mut sender, mut receiver) = channels(&path);
    let custody =
        AcceptedStreamCustody::capture(accepted, &path, Duration::from_millis(60)).unwrap();
    sender.send(custody).unwrap();
    let received = receiver.receive(WAIT).unwrap();
    std::thread::sleep(Duration::from_millis(80));
    let mut called = false;
    assert_eq!(
        received.consume_before(|_, _| called = true),
        Err(HandoffError::DeadlineExceeded)
    );
    assert!(!called);
    eof(&mut client);
}
fn expired_sender_consumes_custody_and_retires_without_publication() {
    let directory = Directory::new();
    let path = directory.0.join("original.sock");
    let (accepted, mut client) = original(&path);
    let (mut sender, mut receiver) = channels(&path);
    let custody =
        AcceptedStreamCustody::capture(accepted, &path, Duration::from_millis(30)).unwrap();
    std::thread::sleep(Duration::from_millis(50));
    assert_eq!(sender.send(custody), Err(HandoffError::DeadlineExceeded));
    assert!(matches!(
        receiver.receive(WAIT),
        Err(HandoffError::ConnectionClosed)
    ));
    eof(&mut client);
    let (accepted, _client) = original(&directory.0.join("other.sock"));
    let custody =
        AcceptedStreamCustody::capture(accepted, &directory.0.join("other.sock"), WAIT).unwrap();
    assert_eq!(sender.send(custody), Err(HandoffError::ChannelRetired));
}
fn capture_refuses_pipe_listener_socketpair_and_wrong_path() {
    let directory = Directory::new();
    let path = directory.0.join("original.sock");
    let listener = UnixListener::bind(&path).unwrap();
    assert!(matches!(
        AcceptedStreamCustody::capture(UnixStream::from(OwnedFd::from(listener)), &path, WAIT),
        Err(HandoffError::WrongDescriptor)
    ));
    let (left, _right) = UnixStream::pair().unwrap();
    assert!(matches!(
        AcceptedStreamCustody::capture(left, &path, WAIT),
        Err(HandoffError::WrongDescriptor)
    ));
    let mut pipe = [-1; 2];
    assert_eq!(
        unsafe { libc::pipe2(pipe.as_mut_ptr(), libc::O_CLOEXEC) },
        0
    );
    let (read, _write) = unsafe { (OwnedFd::from_raw_fd(pipe[0]), OwnedFd::from_raw_fd(pipe[1])) };
    assert!(matches!(
        AcceptedStreamCustody::capture(UnixStream::from(read), &path, WAIT),
        Err(HandoffError::WrongDescriptor)
    ));
    let actual = directory.0.join("other.sock");
    let (accepted, _client) = original(&actual);
    assert!(matches!(
        AcceptedStreamCustody::capture(accepted, &path, WAIT),
        Err(HandoffError::WrongDescriptor)
    ));
}
fn control_refuses_stream_and_actual_wrong_kernel_peer() {
    let directory = Directory::new();
    let path = directory.0.join("original.sock");
    let (left, _right) = UnixStream::pair().unwrap();
    assert!(matches!(
        HandoffReceiver::from_control(left.into(), policy(), &path),
        Err(HandoffError::WrongDescriptor)
    ));
    let (_left, right) = controls();
    let mut wrong = policy();
    wrong.expected_uid ^= 1;
    assert!(matches!(
        HandoffReceiver::from_control(right, wrong, &path),
        Err(HandoffError::PeerRefused)
    ));
    let (left, _right) = controls();
    let mut wrong = policy();
    wrong.expected_pid = Some(std::process::id() + 1);
    assert!(matches!(
        HandoffSender::from_control(left, wrong, WAIT),
        Err(HandoffError::PeerRefused)
    ));
}
fn actual_extra_rights_and_ctrunc_close_all_received_descriptors() {
    for amount in [0, 2, 17, 100] {
        let directory = Directory::new();
        let path = directory.0.join("original.sock");
        let (accepted, _client) = original(&path);
        let (control, mut receiver, nonce) = raw_receiver(&path);
        let data = raw_packet(accepted.as_raw_fd(), &nonce, 1, WAIT);
        let before = inventory();
        raw_send(&control, &data, &vec![accepted.as_raw_fd(); amount]);
        assert!(matches!(
            receiver.receive(WAIT),
            Err(HandoffError::ProtocolRefused)
        ));
        // One channel receiver descriptor was permanently retired. Every
        // kernel-delivered duplicate (including truncation) is gone.
        let after = inventory();
        assert_eq!(after.len() + 1, before.len());
        assert!(matches!(
            receiver.receive(WAIT),
            Err(HandoffError::ChannelRetired)
        ));
    }
}
fn receiver_refuses_substituted_pipe_listener_socketpair_and_path() {
    for kind in 0..4 {
        let directory = Directory::new();
        let path = directory.0.join("original.sock");
        let (accepted, _client) = original(&path);
        let (control, mut receiver, nonce) = raw_receiver(&path);
        let data = raw_packet(accepted.as_raw_fd(), &nonce, 1, WAIT);
        let mut retained = Vec::new();
        let descriptor = match kind {
            0 => {
                let mut values = [-1; 2];
                assert_eq!(
                    unsafe { libc::pipe2(values.as_mut_ptr(), libc::O_CLOEXEC) },
                    0
                );
                retained.push(unsafe { OwnedFd::from_raw_fd(values[1]) });
                unsafe { OwnedFd::from_raw_fd(values[0]) }
            }
            1 => UnixListener::bind(directory.0.join("listener.sock"))
                .unwrap()
                .into(),
            2 => {
                let (left, right) = UnixStream::pair().unwrap();
                retained.push(right.into());
                left.into()
            }
            _ => {
                let (left, right) = original(&directory.0.join("wrong.sock"));
                retained.push(right.into());
                left.into()
            }
        };
        let before = inventory();
        raw_send(&control, &data, &[descriptor.as_raw_fd()]);
        assert!(matches!(
            receiver.receive(WAIT),
            Err(HandoffError::WrongDescriptor)
        ));
        assert_eq!(inventory().len() + 1, before.len());
    }
}
fn exact_packet_mutations_boot_namespace_clock_and_identity_refuse() {
    for offset in [0, 8, 10, 16, 24, 40, 48, 56, 64, 72, 80, 88, 96] {
        let directory = Directory::new();
        let path = directory.0.join("original.sock");
        let (accepted, _client) = original(&path);
        let (control, mut receiver, nonce) = raw_receiver(&path);
        let mut data = raw_packet(accepted.as_raw_fd(), &nonce, 1, WAIT);
        data[offset] ^= 0xff;
        let before = inventory();
        raw_send(&control, &data, &[accepted.as_raw_fd()]);
        assert!(
            receiver.receive(WAIT).is_err(),
            "accepted mutation at {offset}"
        );
        assert_eq!(inventory().len() + 1, before.len());
    }
}
fn short_long_and_eof_packets_retire_without_fd_leak() {
    for size in [0, 1, 127, 129, 8192] {
        let directory = Directory::new();
        let path = directory.0.join("original.sock");
        let (accepted, _client) = original(&path);
        let (control, mut receiver, nonce) = raw_receiver(&path);
        let data = raw_packet(accepted.as_raw_fd(), &nonce, 1, WAIT);
        let mut malformed = vec![0; size];
        let copy = size.min(data.len());
        malformed[..copy].copy_from_slice(&data[..copy]);
        let before = inventory();
        raw_send(&control, &malformed, &[accepted.as_raw_fd()]);
        assert!(receiver.receive(WAIT).is_err());
        assert_eq!(inventory().len() + 1, before.len());
    }
    let directory = Directory::new();
    let path = directory.0.join("original.sock");
    let (control, mut receiver, _) = raw_receiver(&path);
    drop(control);
    assert!(matches!(
        receiver.receive(WAIT),
        Err(HandoffError::ConnectionClosed)
    ));
    assert!(matches!(
        receiver.receive(WAIT),
        Err(HandoffError::ChannelRetired)
    ));
}
fn same_and_cross_channel_replay_refuse_real_duplicate_original() {
    let directory = Directory::new();
    let path = directory.0.join("original.sock");
    let (accepted, _client) = original(&path);
    let (control, mut receiver, nonce) = raw_receiver(&path);
    let data = raw_packet(accepted.as_raw_fd(), &nonce, 1, WAIT);
    raw_send(&control, &data, &[accepted.as_raw_fd()]);
    drop(receiver.receive(WAIT).unwrap());
    let before = inventory();
    raw_send(&control, &data, &[accepted.as_raw_fd()]);
    assert!(matches!(
        receiver.receive(WAIT),
        Err(HandoffError::ProtocolRefused)
    ));
    assert_eq!(inventory().len() + 1, before.len());
    let (other, mut fresh, fresh_nonce) = raw_receiver(&path);
    assert_ne!(nonce, fresh_nonce);
    raw_send(&other, &data, &[accepted.as_raw_fd()]);
    assert!(matches!(
        fresh.receive(WAIT),
        Err(HandoffError::ProtocolRefused)
    ));
    let (other, mut fresh, nonce) = raw_receiver(&path);
    let first = raw_packet(accepted.as_raw_fd(), &nonce, 1, WAIT);
    raw_send(&other, &first, &[accepted.as_raw_fd()]);
    drop(fresh.receive(WAIT).unwrap());
    let second = raw_packet(accepted.as_raw_fd(), &nonce, 2, WAIT);
    raw_send(&other, &second, &[accepted.as_raw_fd()]);
    assert!(matches!(
        fresh.receive(WAIT),
        Err(HandoffError::ProtocolRefused)
    ));
}
fn sender_duplicate_cookie_refuses_and_consumes_second_custody() {
    let directory = Directory::new();
    let path = directory.0.join("original.sock");
    let (accepted, _client) = original(&path);
    let duplicate = accepted.try_clone().unwrap();
    let (mut sender, mut receiver) = channels(&path);
    sender
        .send(AcceptedStreamCustody::capture(accepted, &path, WAIT).unwrap())
        .unwrap();
    drop(receiver.receive(WAIT).unwrap());
    assert_eq!(
        sender.send(AcceptedStreamCustody::capture(duplicate, &path, WAIT).unwrap()),
        Err(HandoffError::ProtocolRefused)
    );
}
fn incoming_expiry_and_timeout_close_rights_and_channel() {
    let directory = Directory::new();
    let path = directory.0.join("original.sock");
    let (accepted, _client) = original(&path);
    let (control, mut receiver, nonce) = raw_receiver(&path);
    let data = raw_packet(accepted.as_raw_fd(), &nonce, 1, Duration::from_millis(20));
    raw_send(&control, &data, &[accepted.as_raw_fd()]);
    std::thread::sleep(Duration::from_millis(40));
    let before = inventory();
    assert!(matches!(
        receiver.receive(WAIT),
        Err(HandoffError::DeadlineExceeded)
    ));
    assert_eq!(inventory().len() + 1, before.len());
    let (_control, mut receiver, _) = raw_receiver(&path);
    assert!(matches!(
        receiver.receive(Duration::from_millis(20)),
        Err(HandoffError::DeadlineExceeded)
    ));
    assert!(matches!(
        receiver.receive(WAIT),
        Err(HandoffError::ChannelRetired)
    ));
}
fn malformed_challenge_rights_are_owned_and_closed_on_sender_refusal() {
    let (sender, receiver) = controls();
    let control = UnixStream::from(receiver);
    let file = fs::File::open("/dev/null").unwrap();
    let before = inventory();
    raw_send(&control, &[0; 40], &[file.as_raw_fd()]);
    assert!(matches!(
        HandoffSender::from_control(sender, policy(), WAIT),
        Err(HandoffError::ProtocolRefused)
    ));
    assert_eq!(inventory().len() + 1, before.len());
}
fn actual_passpidfd_refuses_and_closes_pidfds_and_remaining_rights() {
    fn enable(descriptor: RawFd) {
        let enabled: libc::c_int = 1;
        // Required actual kernel capability, never a mock or skipped case.
        // SAFETY: the integer option storage and owned descriptor are live.
        let result = unsafe {
            libc::setsockopt(
                descriptor,
                libc::SOL_SOCKET,
                libc::SO_PASSPIDFD,
                std::ptr::addr_of!(enabled).cast(),
                size_of_val(&enabled) as libc::socklen_t,
            )
        };
        assert_eq!(
            result,
            0,
            "actual SO_PASSPIDFD is required; unsupported kernel refuses this test: {}",
            std::io::Error::last_os_error()
        );
    }
    {
        let directory = Directory::new();
        let path = directory.0.join("original.sock");
        let (accepted, mut client) = original(&path);
        let (sender, receiver) = controls();
        enable(receiver.as_raw_fd());
        let mut receiver = HandoffReceiver::from_control(receiver, policy(), &path).unwrap();
        let mut sender = HandoffSender::from_control(sender, policy(), WAIT).unwrap();
        sender
            .send(AcceptedStreamCustody::capture(accepted, &path, WAIT).unwrap())
            .unwrap();
        let before = inventory();
        assert!(matches!(
            receiver.receive(WAIT),
            Err(HandoffError::ProtocolRefused)
        ));
        // The original right and kernel-created pidfd are both gone; only the
        // failed receiver's owned control descriptor disappears from inventory.
        assert_eq!(inventory().len() + 1, before.len());
        eof(&mut client);
        assert!(matches!(
            receiver.receive(WAIT),
            Err(HandoffError::ChannelRetired)
        ));
    }
    {
        // A valid, rights-free challenge must refuse solely because the kernel
        // additionally delivered SCM_PIDFD, without retaining that pidfd.
        let directory = Directory::new();
        let path = directory.0.join("original.sock");
        let (sender, receiver) = controls();
        enable(sender.as_raw_fd());
        let _receiver = HandoffReceiver::from_control(receiver, policy(), &path).unwrap();
        let before = inventory();
        assert!(matches!(
            HandoffSender::from_control(sender, policy(), WAIT),
            Err(HandoffError::ProtocolRefused)
        ));
        assert_eq!(inventory().len() + 1, before.len());
    }
    {
        // The shared challenge parser also closes an extra original right and
        // the actual kernel pidfd, even though that challenge is already invalid.
        let directory = Directory::new();
        let path = directory.0.join("original.sock");
        let (accepted, mut client) = original(&path);
        let (sender, receiver) = controls();
        enable(sender.as_raw_fd());
        let control = UnixStream::from(receiver);
        let mut challenge = [1; 40];
        challenge[..8].copy_from_slice(b"HPTAFDC1");
        raw_send(&control, &challenge, &[accepted.as_raw_fd()]);
        drop(accepted);
        let before = inventory();
        assert!(matches!(
            HandoffSender::from_control(sender, policy(), WAIT),
            Err(HandoffError::ProtocolRefused)
        ));
        assert_eq!(inventory().len() + 1, before.len());
        eof(&mut client);
    }
}
fn strict_budget_configuration_and_no_inherited_process_use() {
    for budget in [Duration::ZERO, MAX_HANDOFF_BUDGET + Duration::from_nanos(1)] {
        let directory = Directory::new();
        let path = directory.0.join("original.sock");
        let (accepted, _client) = original(&path);
        assert!(matches!(
            AcceptedStreamCustody::capture(accepted, &path, budget),
            Err(HandoffError::InvalidConfiguration)
        ));
    }
    let directory = Directory::new();
    let path = directory.0.join("original.sock");
    let (accepted, _client) = original(&path);
    let (mut sender, mut receiver) = channels(&path);
    sender
        .send(AcceptedStreamCustody::capture(accepted, &path, WAIT).unwrap())
        .unwrap();
    let received = receiver.receive(WAIT).unwrap();
    // This executable has one thread and no borrowed mutex/thread state.
    let pid = unsafe { libc::fork() };
    assert!(pid >= 0);
    if pid == 0 {
        let denied = received.deadline() == Err(HandoffError::ProcessChanged)
            && matches!(receiver.receive(WAIT), Err(HandoffError::ProcessChanged));
        // SAFETY: child exits without touching parent runtime or dropping
        // copied synchronization state. Kernel closes only child FD copies.
        unsafe { libc::_exit(if denied { 0 } else { 1 }) }
    }
    let mut status = 0;
    assert_eq!(unsafe { libc::waitpid(pid, &mut status, 0) }, pid);
    assert_eq!(status, 0);
    received.consume_before(|_, _| ()).unwrap();
}
fn kernel_message_credentials_refuse_foreign_fork_writer() {
    let directory = Directory::new();
    let path = directory.0.join("original.sock");
    let (accepted, _client) = original(&path);
    let (control, mut receiver, nonce) = raw_receiver(&path);
    let data = raw_packet(accepted.as_raw_fd(), &nonce, 1, WAIT);
    let before = inventory();
    let pid = unsafe { libc::fork() };
    assert!(pid >= 0);
    if pid == 0 {
        // SO_PEERCRED still names the parent that created this control socket.
        // Actual SCM_CREDENTIALS names the child writer, so receiver must refuse.
        raw_send(&control, &data, &[accepted.as_raw_fd()]);
        unsafe { libc::_exit(0) }
    }
    assert!(matches!(
        receiver.receive(WAIT),
        Err(HandoffError::ProtocolRefused)
    ));
    let mut status = 0;
    assert_eq!(unsafe { libc::waitpid(pid, &mut status, 0) }, pid);
    assert_eq!(status, 0);
    assert_eq!(inventory().len() + 1, before.len());
}
fn control_listener(path: &Path) -> OwnedFd {
    let raw = unsafe { libc::socket(libc::AF_UNIX, libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC, 0) };
    assert!(raw >= 0);
    let fd = unsafe { OwnedFd::from_raw_fd(raw) };
    let (address, length) = control_address(path);
    assert_eq!(
        unsafe { libc::bind(raw, std::ptr::addr_of!(address).cast(), length) },
        0
    );
    assert_eq!(unsafe { libc::listen(raw, 1) }, 0);
    fd
}
fn control_address(path: &Path) -> (libc::sockaddr_un, libc::socklen_t) {
    let bytes = path.as_os_str().as_encoded_bytes();
    let mut address: libc::sockaddr_un = unsafe { zeroed() };
    assert!(bytes.len() < address.sun_path.len());
    address.sun_family = libc::AF_UNIX as libc::sa_family_t;
    for (destination, value) in address.sun_path.iter_mut().zip(bytes) {
        *destination = *value as libc::c_char;
    }
    (
        address,
        (std::mem::offset_of!(libc::sockaddr_un, sun_path) + bytes.len() + 1) as libc::socklen_t,
    )
}
fn control_connect(path: &Path) -> OwnedFd {
    let raw = unsafe { libc::socket(libc::AF_UNIX, libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC, 0) };
    assert!(raw >= 0);
    let fd = unsafe { OwnedFd::from_raw_fd(raw) };
    let (address, length) = control_address(path);
    assert_eq!(
        unsafe { libc::connect(raw, std::ptr::addr_of!(address).cast(), length) },
        0
    );
    fd
}
fn wait_fd(fd: RawFd) {
    let mut value = libc::pollfd {
        fd,
        events: libc::POLLIN,
        revents: 0,
    };
    assert_eq!(
        unsafe { libc::poll(&mut value, 1, WAIT.as_millis() as i32) },
        1
    );
}
fn actual_distinct_process_same_uid_original_stream_handoff() {
    let directory = Directory::new();
    let path = directory.0.join("original.sock");
    let control_path = directory.0.join("control.sock");
    let listener = UnixListener::bind(&path).unwrap();
    let controls = control_listener(&control_path);
    let parent_pid = std::process::id();
    let child = unsafe { libc::fork() };
    assert!(child >= 0);
    if child == 0 {
        wait_fd(listener.as_raw_fd());
        let (accepted, _) = listener.accept().unwrap();
        let custody = AcceptedStreamCustody::capture(accepted, &path, WAIT).unwrap();
        let mut expected = policy();
        expected.expected_pid = Some(parent_pid);
        let control = control_connect(&control_path);
        let mut sender = HandoffSender::from_control(control, expected, WAIT).unwrap();
        sender.send(custody).unwrap();
        unsafe { libc::_exit(0) }
    }
    let mut client = UnixStream::connect(&path).unwrap();
    wait_fd(controls.as_raw_fd());
    let raw = unsafe {
        libc::accept4(
            controls.as_raw_fd(),
            std::ptr::null_mut(),
            std::ptr::null_mut(),
            libc::SOCK_CLOEXEC,
        )
    };
    assert!(raw >= 0);
    let control = unsafe { OwnedFd::from_raw_fd(raw) };
    let mut expected = policy();
    expected.expected_pid = Some(child as u32);
    let mut receiver = HandoffReceiver::from_control(control, expected, &path).unwrap();
    let received = receiver.receive(WAIT).unwrap();
    let mut status = 0;
    assert_eq!(unsafe { libc::waitpid(child, &mut status, 0) }, child);
    assert_eq!(status, 0);
    // The source connection service exited. The handed original is still the
    // connected socket, whose real peer is this original client process.
    client.write_all(b"actual cross-process custody").unwrap();
    received
        .consume_before(|mut original, _| {
            assert_eq!(
                PeerIdentity::from_stream(&original).unwrap().pid,
                Some(parent_pid)
            );
            let mut bytes = [0; 28];
            original.read_exact(&mut bytes).unwrap();
            assert_eq!(&bytes, b"actual cross-process custody");
            original.write_all(b"retained original").unwrap();
        })
        .unwrap();
    let mut response = [0; 17];
    client.read_exact(&mut response).unwrap();
    assert_eq!(&response, b"retained original");
}
fn bounded_channel_history_refuses_capacity_without_original_leak() {
    let directory = Directory::new();
    // All connections share the actual listener path; every accepted socket
    // has a distinct cookie. No protocol or nonce test injection is exposed.
    let path = directory.0.join("original.sock");
    let listener = UnixListener::bind(&path).unwrap();
    let (mut sender, mut receiver) = channels(&path);
    for _ in 0..MAX_HANDOFFS_PER_CHANNEL {
        let client = UnixStream::connect(&path).unwrap();
        let (accepted, _) = listener.accept().unwrap();
        sender
            .send(AcceptedStreamCustody::capture(accepted, &path, WAIT).unwrap())
            .unwrap();
        drop(receiver.receive(WAIT).unwrap());
        drop(client);
    }
    let mut client = UnixStream::connect(&path).unwrap();
    let (accepted, _) = listener.accept().unwrap();
    assert_eq!(
        sender.send(AcceptedStreamCustody::capture(accepted, &path, WAIT).unwrap()),
        Err(HandoffError::CapacityExceeded)
    );
    eof(&mut client);

    // Exercise receiver exhaustion independently of the honest sender's cap.
    // The final original exists only as an actual queued SCM_RIGHTS reference;
    // retiring the receiver must release that reference without installing it.
    let (raw_sender, mut raw_receiver, nonce) = raw_receiver(&path);
    for sequence in 1..=MAX_HANDOFFS_PER_CHANNEL as u64 {
        let client = UnixStream::connect(&path).unwrap();
        let (accepted, _) = listener.accept().unwrap();
        let packet = raw_packet(accepted.as_raw_fd(), &nonce, sequence, WAIT);
        raw_send(&raw_sender, &packet, &[accepted.as_raw_fd()]);
        drop(accepted);
        drop(raw_receiver.receive(WAIT).unwrap());
        drop(client);
    }
    let mut client = UnixStream::connect(&path).unwrap();
    let (accepted, _) = listener.accept().unwrap();
    let packet = raw_packet(
        accepted.as_raw_fd(),
        &nonce,
        MAX_HANDOFFS_PER_CHANNEL as u64 + 1,
        WAIT,
    );
    raw_send(&raw_sender, &packet, &[accepted.as_raw_fd()]);
    drop(accepted);
    assert!(matches!(
        raw_receiver.receive(WAIT),
        Err(HandoffError::CapacityExceeded)
    ));
    eof(&mut client);
}
fn main() {
    let tests: &[(&str, fn())] = &[
        (
            "original kernel identity and bytes",
            original_kernel_identity_and_bytes_survive_handoff,
        ),
        (
            "handoff waits preserve original deadline",
            sender_and_receiver_waits_do_not_renew_original_budget,
        ),
        (
            "queued expiry closes without consumer",
            queued_expiry_closes_original_without_consumer_call,
        ),
        (
            "expired sender consumes without publication",
            expired_sender_consumes_custody_and_retires_without_publication,
        ),
        (
            "capture descriptor and path refusals",
            capture_refuses_pipe_listener_socketpair_and_wrong_path,
        ),
        (
            "actual control shape and peer refusals",
            control_refuses_stream_and_actual_wrong_kernel_peer,
        ),
        (
            "extra rights and real CTRUNC cleanup",
            actual_extra_rights_and_ctrunc_close_all_received_descriptors,
        ),
        (
            "received descriptor and path substitutions",
            receiver_refuses_substituted_pipe_listener_socketpair_and_path,
        ),
        (
            "exact clock namespace identity mutations",
            exact_packet_mutations_boot_namespace_clock_and_identity_refuse,
        ),
        (
            "short long and EOF actual packets",
            short_long_and_eof_packets_retire_without_fd_leak,
        ),
        (
            "same and cross channel replay",
            same_and_cross_channel_replay_refuse_real_duplicate_original,
        ),
        (
            "sender duplicate cookie consumed",
            sender_duplicate_cookie_refuses_and_consumes_second_custody,
        ),
        (
            "incoming expiry and timeout",
            incoming_expiry_and_timeout_close_rights_and_channel,
        ),
        (
            "malformed challenge FD cleanup",
            malformed_challenge_rights_are_owned_and_closed_on_sender_refusal,
        ),
        (
            "actual SCM_PIDFD challenge and original right cleanup",
            actual_passpidfd_refuses_and_closes_pidfds_and_remaining_rights,
        ),
        (
            "strict budgets and actual inherited fork refusal",
            strict_budget_configuration_and_no_inherited_process_use,
        ),
        (
            "actual foreign writer credential refusal",
            kernel_message_credentials_refuse_foreign_fork_writer,
        ),
        (
            "actual distinct-process same-UID handoff",
            actual_distinct_process_same_uid_original_stream_handoff,
        ),
        (
            "bounded channel capacity",
            bounded_channel_history_refuses_capacity_without_original_leak,
        ),
    ];
    for (name, test) in tests {
        let before = inventory();
        test();
        assert_eq!(inventory(), before, "descriptor leak in {name}");
        println!("PASS: {name}");
    }
    println!(
        "{} actual kernel handoff cases PASS; same-UID source only, no installed/native/broker qualification",
        tests.len()
    );
}
