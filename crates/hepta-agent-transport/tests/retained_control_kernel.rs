//! Actual retained control kernel corpus. No synthetic procfs, injected identity,
//! product daemon activation, Servo callback or installed-runtime claim.
#![cfg(target_os = "linux")]
#![deny(unsafe_op_in_unsafe_fn)]

use hepta_agent_transport::{
    AcceptedStreamCustody, HandoffError, HandoffReceiver, HandoffSender, PeerIdentity, PeerPolicy,
    PendingHandoffReceiver, PendingHandoffSender, RemoteRetirementReport, RemoteTerminalState,
};
use std::fs;
use std::io::{Read, Write};
use std::mem::{size_of, size_of_val, zeroed};
use std::os::fd::{AsFd, AsRawFd, FromRawFd, OwnedFd, RawFd};
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
            "g2ret-{}-{}",
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

fn report(state: RemoteTerminalState) -> RemoteRetirementReport {
    RemoteRetirementReport::new(state, [4; 32], [5; 32]).unwrap()
}
fn retained(
    path: &Path,
    budget: Duration,
) -> (
    PendingHandoffSender,
    PendingHandoffReceiver,
    hepta_agent_transport::ReceivedAcceptedStream,
    UnixStream,
) {
    let (accepted, client) = original(path);
    let (sender, receiver) = channels(path);
    let custody = AcceptedStreamCustody::capture(accepted, path, budget).unwrap();
    let sender = sender.send_retained(custody).unwrap();
    let (received, receiver) = receiver
        .receive_retained(WAIT)
        .unwrap()
        .into_parts()
        .unwrap();
    (sender, receiver, received, client)
}
fn identity_deadline_original_stream_and_report() {
    for state in [
        RemoteTerminalState::Completed,
        RemoteTerminalState::Interrupted,
        RemoteTerminalState::Indeterminate,
    ] {
        let directory = Directory::new();
        let path = directory.0.join("original.sock");
        let (accepted, mut client) = original(&path);
        let identity = socket_identity(accepted.as_raw_fd());
        let peer = PeerIdentity::from_stream(&accepted).unwrap();
        let (sender, receiver) = channels(&path);
        let original_deadline = Instant::now() + WAIT;
        let custody =
            AcceptedStreamCustody::capture_before(accepted, &path, original_deadline).unwrap();
        let mut sender = sender.send_retained(custody).unwrap();
        let (received, mut receiver) = receiver
            .receive_retained(WAIT)
            .unwrap()
            .into_parts()
            .unwrap();
        assert!(sender.deadline().unwrap() <= original_deadline);
        let deadline = received.deadline().unwrap();
        assert_eq!(receiver.deadline().unwrap(), deadline);
        assert!(deadline <= original_deadline);
        assert!(!receiver.poll_cancel().unwrap());
        client.write_all(b"original").unwrap();
        received
            .consume_before(|mut stream, actual| {
                assert_eq!(actual, deadline);
                assert_eq!(socket_identity(stream.as_raw_fd()), identity);
                assert_eq!(PeerIdentity::from_stream(&stream).unwrap(), peer);
                let mut data = [0; 8];
                stream.read_exact(&mut data).unwrap();
                assert_eq!(&data, b"original");
                stream.write_all(b"same").unwrap();
            })
            .unwrap();
        let mut bytes = [0; 4];
        client.read_exact(&mut bytes).unwrap();
        assert_eq!(&bytes, b"same");
        let expected = report(state);
        receiver.send_report(expected).unwrap();
        assert_eq!(
            receiver.send_report(expected),
            Err(HandoffError::ChannelRetired)
        );
        assert_eq!(sender.wait_report().unwrap(), expected);
        assert_eq!(sender.wait_report(), Err(HandoffError::ChannelRetired));
        eof(&mut client);
    }
}
fn cancellation_once_no_synthetic_application_bytes() {
    let directory = Directory::new();
    let path = directory.0.join("original.sock");
    let (mut sender, mut receiver, received, mut client) = retained(&path, WAIT);
    let deadline = receiver.deadline().unwrap();
    assert!(!receiver.poll_cancel().unwrap());
    sender.request_cancel().unwrap();
    assert!(receiver.poll_cancel().unwrap());
    assert!(!receiver.poll_cancel().unwrap());
    assert_eq!(receiver.deadline().unwrap(), deadline);
    client.set_nonblocking(true).unwrap();
    assert_eq!(
        client.read(&mut [0]).unwrap_err().kind(),
        std::io::ErrorKind::WouldBlock
    );
    client.set_nonblocking(false).unwrap();
    receiver
        .send_report(report(RemoteTerminalState::Interrupted))
        .unwrap();
    assert_eq!(
        sender.wait_report().unwrap().state(),
        RemoteTerminalState::Interrupted
    );
    drop(received);
    eof(&mut client);
}
fn nonblocking_report_then_same_channel_cancel_and_one_terminal() {
    let directory = Directory::new();
    let path = directory.0.join("original.sock");
    let (mut sender, mut receiver, _received, _client) = retained(&path, WAIT);
    let deadline = sender.deadline().unwrap();
    let started = Instant::now();
    assert_eq!(sender.poll_report(), Ok(None));
    assert!(started.elapsed() < Duration::from_millis(250));
    assert_eq!(sender.deadline().unwrap(), deadline);
    sender.request_cancel().unwrap();
    assert!(receiver.poll_cancel().unwrap());
    assert_eq!(sender.poll_report(), Ok(None));
    receiver
        .send_report(report(RemoteTerminalState::Interrupted))
        .unwrap();
    assert_eq!(
        sender.poll_report(),
        Ok(Some(report(RemoteTerminalState::Interrupted)))
    );
    assert_eq!(sender.poll_report(), Err(HandoffError::ChannelRetired));
    assert_eq!(sender.request_cancel(), Err(HandoffError::ChannelRetired));
    let path = directory.0.join("eof.sock");
    let (mut sender, receiver, _received, _client) = retained(&path, WAIT);
    drop(receiver);
    assert_eq!(sender.poll_report(), Err(HandoffError::ConnectionClosed));
    assert_eq!(sender.wait_report(), Err(HandoffError::ChannelRetired));
    let path = directory.0.join("malformed.sock");
    let (raw, mut sender, _client, packet) = raw_retained_sender(&path);
    let mut malformed = sideband(&packet, 2);
    malformed[12] = 1;
    raw_send(&raw, &malformed, &[]);
    assert_eq!(sender.poll_report(), Err(HandoffError::ProtocolRefused));
    assert_eq!(sender.poll_report(), Err(HandoffError::ChannelRetired));
}
fn sender_duplicate_cancellation_consumes_endpoint() {
    let directory = Directory::new();
    let path = directory.0.join("original.sock");
    let (mut sender, mut receiver, _received, _client) = retained(&path, WAIT);
    sender.request_cancel().unwrap();
    assert_eq!(sender.request_cancel(), Err(HandoffError::ProtocolRefused));
    assert_eq!(sender.wait_report(), Err(HandoffError::ChannelRetired));
    assert!(receiver.poll_cancel().unwrap());
    assert_eq!(receiver.poll_cancel(), Err(HandoffError::ConnectionClosed));
}
fn original_budget_expiry_wait_and_queue_no_renewal() {
    let directory = Directory::new();
    let path = directory.0.join("original.sock");
    let (mut sender, mut receiver, received, mut client) =
        retained(&path, Duration::from_millis(35));
    let started = Instant::now();
    assert_eq!(sender.wait_report(), Err(HandoffError::DeadlineExceeded));
    assert!(started.elapsed() < Duration::from_millis(300));
    assert_eq!(sender.ensure_current(), Err(HandoffError::ChannelRetired));
    assert_eq!(receiver.poll_cancel(), Err(HandoffError::DeadlineExceeded));
    assert!(matches!(
        received.consume_before(|_, _| panic!("expired custody dispatched")),
        Err(HandoffError::DeadlineExceeded)
    ));
    eof(&mut client);
    let path = directory.0.join("queue.sock");
    let (accepted, mut client) = original(&path);
    let (sender, receiver) = channels(&path);
    let mut sender = sender
        .send_retained(
            AcceptedStreamCustody::capture(accepted, &path, Duration::from_millis(35)).unwrap(),
        )
        .unwrap();
    let received = receiver.receive_retained(WAIT).unwrap();
    std::thread::sleep(Duration::from_millis(60));
    assert!(matches!(
        received.into_parts(),
        Err(HandoffError::DeadlineExceeded)
    ));
    assert_eq!(sender.request_cancel(), Err(HandoffError::DeadlineExceeded));
    eof(&mut client);
}
fn eof_and_ambiguous_report_publication_no_retry() {
    let directory = Directory::new();
    let path = directory.0.join("sender.sock");
    let (mut sender, receiver, received, mut client) = retained(&path, WAIT);
    drop(receiver);
    assert_eq!(sender.wait_report(), Err(HandoffError::ConnectionClosed));
    assert_eq!(sender.request_cancel(), Err(HandoffError::ChannelRetired));
    drop(received);
    eof(&mut client);
    let path = directory.0.join("receiver.sock");
    let (sender, mut receiver, received, mut client) = retained(&path, WAIT);
    drop(sender);
    assert_eq!(
        receiver.send_report(report(RemoteTerminalState::Completed)),
        Err(HandoffError::Io)
    );
    assert_eq!(
        receiver.send_report(report(RemoteTerminalState::Completed)),
        Err(HandoffError::ChannelRetired)
    );
    drop(received);
    eof(&mut client);
}
fn raw_retained_receiver(
    path: &Path,
) -> (
    UnixStream,
    PendingHandoffReceiver,
    hepta_agent_transport::ReceivedAcceptedStream,
    UnixStream,
    [u8; 128],
) {
    let (control, receiver, nonce) = raw_receiver(path);
    let (accepted, client) = original(path);
    let packet = raw_packet(accepted.as_raw_fd(), &nonce, 1, WAIT);
    raw_send(&control, &packet, &[accepted.as_raw_fd()]);
    drop(accepted);
    let (received, pending) = receiver
        .receive_retained(WAIT)
        .unwrap()
        .into_parts()
        .unwrap();
    (control, pending, received, client, packet)
}
fn sideband(packet: &[u8; 128], kind: u8) -> [u8; 192] {
    let mut data = [0; 192];
    data[..128].copy_from_slice(packet);
    data[..8].copy_from_slice(b"HPTAFDS1");
    data[10] = kind;
    if kind == 2 {
        data[11] = 1;
        data[128..160].fill(4);
        data[160..].fill(5);
    }
    data
}
fn raw_receive_handoff(control: &UnixStream) -> [u8; 128] {
    let mut data = [0; 128];
    let mut ancillary = [0usize; 32];
    let mut vector = libc::iovec {
        iov_base: data.as_mut_ptr().cast(),
        iov_len: data.len(),
    };
    let mut message: libc::msghdr = unsafe { zeroed() };
    message.msg_iov = &mut vector;
    message.msg_iovlen = 1;
    message.msg_control = ancillary.as_mut_ptr().cast();
    message.msg_controllen = size_of_val(&ancillary);
    assert_eq!(
        unsafe { libc::recvmsg(control.as_raw_fd(), &mut message, libc::MSG_CMSG_CLOEXEC) },
        128
    );
    assert_eq!(message.msg_flags & (libc::MSG_CTRUNC | libc::MSG_TRUNC), 0);
    let mut count = 0;
    unsafe {
        let mut header = libc::CMSG_FIRSTHDR(&message);
        while !header.is_null() {
            if (*header).cmsg_level == libc::SOL_SOCKET && (*header).cmsg_type == libc::SCM_RIGHTS {
                let n = ((*header).cmsg_len - libc::CMSG_LEN(0) as usize) / size_of::<RawFd>();
                for i in 0..n {
                    drop(OwnedFd::from_raw_fd(std::ptr::read_unaligned(
                        libc::CMSG_DATA(header).cast::<RawFd>().add(i),
                    )));
                    count += 1;
                }
            }
            header = libc::CMSG_NXTHDR(&message, header);
        }
    }
    assert_eq!(count, 1);
    data
}
fn raw_retained_sender(path: &Path) -> (UnixStream, PendingHandoffSender, UnixStream, [u8; 128]) {
    let (sender, receiver) = controls();
    let raw = UnixStream::from(receiver);
    let typed =
        HandoffReceiver::from_control(raw.try_clone().unwrap().into(), policy(), path).unwrap();
    let sender = HandoffSender::from_control(sender, policy(), WAIT).unwrap();
    let (accepted, client) = original(path);
    let sender = sender
        .send_retained(AcceptedStreamCustody::capture(accepted, path, WAIT).unwrap())
        .unwrap();
    let packet = raw_receive_handoff(&raw);
    drop(typed);
    (raw, sender, client, packet)
}
fn exact_frame_mutations_refuse_cancel_and_report() {
    for kind in [1, 2] {
        for offset in [
            0, 8, 9, 10, 11, 12, 15, 16, 23, 24, 39, 40, 47, 48, 55, 56, 63, 64, 71, 72, 79, 80,
            87, 88, 95, 96, 127,
        ] {
            let directory = Directory::new();
            let path = directory.0.join("original.sock");
            if kind == 1 {
                let (raw, mut receiver, received, mut client, packet) =
                    raw_retained_receiver(&path);
                let mut data = sideband(&packet, kind);
                data[offset] ^= 0x80;
                raw_send(&raw, &data, &[]);
                assert_eq!(
                    receiver.poll_cancel(),
                    Err(HandoffError::ProtocolRefused),
                    "offset {offset}"
                );
                assert_eq!(receiver.poll_cancel(), Err(HandoffError::ChannelRetired));
                drop(received);
                eof(&mut client);
            } else {
                let (raw, mut sender, mut client, packet) = raw_retained_sender(&path);
                let mut data = sideband(&packet, kind);
                data[offset] ^= 0x80;
                raw_send(&raw, &data, &[]);
                assert_eq!(
                    sender.wait_report(),
                    Err(HandoffError::ProtocolRefused),
                    "offset {offset}"
                );
                assert_eq!(sender.wait_report(), Err(HandoffError::ChannelRetired));
                eof(&mut client);
            }
        }
    }
}
fn closed_digest_fields_and_zero_report_refusals() {
    for state in [
        RemoteTerminalState::Completed,
        RemoteTerminalState::Interrupted,
        RemoteTerminalState::Indeterminate,
    ] {
        assert_eq!(
            RemoteRetirementReport::new(state, [0; 32], [1; 32]),
            Err(HandoffError::ProtocolRefused)
        );
        assert_eq!(
            RemoteRetirementReport::new(state, [1; 32], [0; 32]),
            Err(HandoffError::ProtocolRefused)
        );
    }
    for kind in [1, 2] {
        for which in [0, 1] {
            let directory = Directory::new();
            let path = directory.0.join("original.sock");
            if kind == 1 {
                let (raw, mut receiver, _received, _client, packet) = raw_retained_receiver(&path);
                let mut data = sideband(&packet, 1);
                data[128 + which * 32] = 1;
                raw_send(&raw, &data, &[]);
                assert_eq!(receiver.poll_cancel(), Err(HandoffError::ProtocolRefused));
            } else {
                let (raw, mut sender, _client, packet) = raw_retained_sender(&path);
                let mut data = sideband(&packet, 2);
                data[128 + which * 32..160 + which * 32].fill(0);
                raw_send(&raw, &data, &[]);
                assert_eq!(sender.wait_report(), Err(HandoffError::ProtocolRefused));
            }
        }
    }
}
fn malformed_length_and_rights_all_closed() {
    for kind in [1, 2] {
        for variant in 0..5 {
            let directory = Directory::new();
            let path = directory.0.join("original.sock");
            let (extra, mut extra_client) = original(&directory.0.join("extra.sock"));
            let originals = std::iter::repeat_n(extra.as_raw_fd(), 100).collect::<Vec<_>>();
            let run = |raw: &UnixStream, packet: &[u8; 128]| {
                let data = sideband(packet, kind);
                match variant {
                    0 => raw_send(raw, &data[..191], &[]),
                    1 => raw_send(raw, &[0; 193], &[]),
                    2 => raw_send(raw, &data, &originals[..1]),
                    3 => raw_send(raw, &data, &originals[..2]),
                    _ => raw_send(raw, &data, &originals),
                }
            };
            if kind == 1 {
                let (raw, mut receiver, received, mut client, packet) =
                    raw_retained_receiver(&path);
                run(&raw, &packet);
                drop(extra);
                let before = inventory();
                assert_eq!(receiver.poll_cancel(), Err(HandoffError::ProtocolRefused));
                assert_eq!(inventory().len() + 1, before.len());
                drop(received);
                eof(&mut client);
            } else {
                let (raw, mut sender, mut client, packet) = raw_retained_sender(&path);
                run(&raw, &packet);
                drop(extra);
                let before = inventory();
                assert_eq!(sender.wait_report(), Err(HandoffError::ProtocolRefused));
                assert_eq!(inventory().len() + 1, before.len());
                eof(&mut client);
            }
            eof(&mut extra_client);
        }
    }
}
fn duplicate_cancel_packet_refuses_and_cross_transaction_replay() {
    let directory = Directory::new();
    let path = directory.0.join("first.sock");
    let (raw, mut receiver, _received, _client, packet) = raw_retained_receiver(&path);
    let data = sideband(&packet, 1);
    raw_send(&raw, &data, &[]);
    assert!(receiver.poll_cancel().unwrap());
    raw_send(&raw, &data, &[]);
    assert_eq!(receiver.poll_cancel(), Err(HandoffError::ProtocolRefused));
    let path = directory.0.join("second.sock");
    let (other, mut fresh, _received, _client, _) = raw_retained_receiver(&path);
    raw_send(&other, &data, &[]);
    assert_eq!(fresh.poll_cancel(), Err(HandoffError::ProtocolRefused));
    let path = directory.0.join("report.sock");
    let (other, mut fresh, _client, _) = raw_retained_sender(&path);
    raw_send(&other, &sideband(&packet, 2), &[]);
    assert_eq!(fresh.wait_report(), Err(HandoffError::ProtocolRefused));
}
fn enable_pidfd(raw: RawFd) {
    let enabled: libc::c_int = 1;
    assert_eq!(
        unsafe {
            libc::setsockopt(
                raw,
                libc::SOL_SOCKET,
                libc::SO_PASSPIDFD,
                std::ptr::addr_of!(enabled).cast(),
                size_of_val(&enabled) as libc::socklen_t,
            )
        },
        0,
        "SO_PASSPIDFD actual capability required: {}",
        std::io::Error::last_os_error()
    );
}
fn actual_sideband_pidfds_and_rights_cleanup() {
    for kind in [1, 2] {
        let directory = Directory::new();
        let path = directory.0.join("original.sock");
        if kind == 1 {
            let (sender, receiver) = controls();
            let receiver_fd = receiver.as_raw_fd();
            let receiver = HandoffReceiver::from_control(receiver, policy(), &path).unwrap();
            let sender = HandoffSender::from_control(sender, policy(), WAIT).unwrap();
            let (accepted, _client) = original(&path);
            let mut sender = sender
                .send_retained(AcceptedStreamCustody::capture(accepted, &path, WAIT).unwrap())
                .unwrap();
            let (_received, mut receiver) = receiver
                .receive_retained(WAIT)
                .unwrap()
                .into_parts()
                .unwrap();
            enable_pidfd(receiver_fd);
            sender.request_cancel().unwrap();
            let before = inventory();
            assert_eq!(receiver.poll_cancel(), Err(HandoffError::ProtocolRefused));
            assert_eq!(inventory().len() + 1, before.len());
        } else {
            let (sender, receiver) = controls();
            let sender_fd = sender.as_raw_fd();
            let receiver = HandoffReceiver::from_control(receiver, policy(), &path).unwrap();
            let sender = HandoffSender::from_control(sender, policy(), WAIT).unwrap();
            let (accepted, _client) = original(&path);
            let mut sender = sender
                .send_retained(AcceptedStreamCustody::capture(accepted, &path, WAIT).unwrap())
                .unwrap();
            let (_received, mut receiver) = receiver
                .receive_retained(WAIT)
                .unwrap()
                .into_parts()
                .unwrap();
            enable_pidfd(sender_fd);
            receiver
                .send_report(report(RemoteTerminalState::Completed))
                .unwrap();
            let before = inventory();
            assert_eq!(sender.wait_report(), Err(HandoffError::ProtocolRefused));
            assert_eq!(inventory().len() + 1, before.len());
        }
    }
}
fn inherited_child_api_refusal_drop_preserves_parent_channel() {
    let directory = Directory::new();
    let path = directory.0.join("original.sock");
    let (mut sender, mut receiver, received, _client) = retained(&path, WAIT);
    let child = unsafe { libc::fork() };
    assert!(child >= 0);
    if child == 0 {
        assert_eq!(sender.ensure_current(), Err(HandoffError::ProcessChanged));
        assert_eq!(sender.deadline(), Err(HandoffError::ProcessChanged));
        assert_eq!(sender.request_cancel(), Err(HandoffError::ProcessChanged));
        assert_eq!(sender.wait_report(), Err(HandoffError::ProcessChanged));
        assert_eq!(sender.poll_report(), Err(HandoffError::ProcessChanged));
        assert_eq!(receiver.ensure_current(), Err(HandoffError::ProcessChanged));
        assert_eq!(receiver.deadline(), Err(HandoffError::ProcessChanged));
        assert_eq!(receiver.poll_cancel(), Err(HandoffError::ProcessChanged));
        assert_eq!(
            receiver.send_report(report(RemoteTerminalState::Completed)),
            Err(HandoffError::ProcessChanged)
        );
        drop(sender);
        drop(receiver);
        drop(received);
        unsafe { libc::_exit(0) }
    }
    let mut status = 0;
    assert_eq!(unsafe { libc::waitpid(child, &mut status, 0) }, child);
    assert_eq!(status, 0);
    sender.request_cancel().unwrap();
    assert!(receiver.poll_cancel().unwrap());
    receiver
        .send_report(report(RemoteTerminalState::Interrupted))
        .unwrap();
    assert_eq!(
        sender.wait_report().unwrap().state(),
        RemoteTerminalState::Interrupted
    );
}
fn actual_foreign_writer_credentials_refused() {
    for kind in [1, 2] {
        let directory = Directory::new();
        let path = directory.0.join("original.sock");
        if kind == 1 {
            let (raw, mut receiver, _received, _client, packet) = raw_retained_receiver(&path);
            let child = unsafe { libc::fork() };
            assert!(child >= 0);
            if child == 0 {
                raw_send(&raw, &sideband(&packet, 1), &[]);
                unsafe { libc::_exit(0) }
            }
            let mut status = 0;
            assert_eq!(unsafe { libc::waitpid(child, &mut status, 0) }, child);
            assert_eq!(status, 0);
            assert_eq!(receiver.poll_cancel(), Err(HandoffError::ProtocolRefused));
        } else {
            let (raw, mut sender, _client, packet) = raw_retained_sender(&path);
            let child = unsafe { libc::fork() };
            assert!(child >= 0);
            if child == 0 {
                raw_send(&raw, &sideband(&packet, 2), &[]);
                unsafe { libc::_exit(0) }
            }
            let mut status = 0;
            assert_eq!(unsafe { libc::waitpid(child, &mut status, 0) }, child);
            assert_eq!(status, 0);
            assert_eq!(sender.wait_report(), Err(HandoffError::ProtocolRefused));
        }
    }
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

fn actual_distinct_process_retained_cancel_and_report() {
    let directory = Directory::new();
    let path = directory.0.join("original.sock");
    let control_path = directory.0.join("control.sock");
    let controls = control_listener(&control_path);
    let (accepted, mut client) = original(&path);
    let parent_pid = std::process::id();
    let child = unsafe { libc::fork() };
    assert!(child >= 0);
    if child == 0 {
        drop(accepted);
        drop(client);
        drop(controls);
        let mut expected = policy();
        expected.expected_pid = Some(parent_pid);
        let receiver =
            HandoffReceiver::from_control(control_connect(&control_path), expected, &path).unwrap();
        let (received, mut pending) = receiver
            .receive_retained(WAIT)
            .unwrap()
            .into_parts()
            .unwrap();
        received
            .consume_before(|mut stream, _| {
                assert_eq!(
                    PeerIdentity::from_stream(&stream).unwrap().pid,
                    Some(parent_pid)
                );
                stream.set_read_timeout(Some(WAIT)).unwrap();
                let mut data = [0; 4];
                stream.read_exact(&mut data).unwrap();
                assert_eq!(&data, b"live");
                stream.write_all(b"same").unwrap();
            })
            .unwrap();
        let stop = Instant::now() + WAIT;
        while !pending.poll_cancel().unwrap() {
            assert!(Instant::now() < stop);
            std::thread::yield_now();
        }
        pending
            .send_report(report(RemoteTerminalState::Interrupted))
            .unwrap();
        unsafe { libc::_exit(0) }
    }
    wait_fd(controls.as_raw_fd());
    let fd = unsafe {
        libc::accept4(
            controls.as_raw_fd(),
            std::ptr::null_mut(),
            std::ptr::null_mut(),
            libc::SOCK_CLOEXEC,
        )
    };
    assert!(fd >= 0);
    let mut expected = policy();
    expected.expected_pid = Some(child as u32);
    let sender =
        HandoffSender::from_control(unsafe { OwnedFd::from_raw_fd(fd) }, expected, WAIT).unwrap();
    let mut sender = sender
        .send_retained(AcceptedStreamCustody::capture(accepted, &path, WAIT).unwrap())
        .unwrap();
    client.set_read_timeout(Some(WAIT)).unwrap();
    client.write_all(b"live").unwrap();
    let mut bytes = [0; 4];
    client.read_exact(&mut bytes).unwrap();
    assert_eq!(&bytes, b"same");
    sender.request_cancel().unwrap();
    assert_eq!(
        sender.wait_report().unwrap(),
        report(RemoteTerminalState::Interrupted)
    );
    let mut status = 0;
    assert_eq!(unsafe { libc::waitpid(child, &mut status, 0) }, child);
    assert_eq!(status, 0);
    eof(&mut client);
}
fn fill_send_buffer(control: &UnixStream) {
    let size: libc::c_int = 4096;
    assert_eq!(
        unsafe {
            libc::setsockopt(
                control.as_raw_fd(),
                libc::SOL_SOCKET,
                libc::SO_SNDBUF,
                std::ptr::addr_of!(size).cast(),
                size_of_val(&size) as libc::socklen_t,
            )
        },
        0
    );
    let data = [0u8; 192];
    for _ in 0..4096 {
        let result = unsafe {
            libc::send(
                control.as_raw_fd(),
                data.as_ptr().cast(),
                data.len(),
                libc::MSG_DONTWAIT | libc::MSG_NOSIGNAL,
            )
        };
        if result < 0 {
            assert_eq!(
                std::io::Error::last_os_error().kind(),
                std::io::ErrorKind::WouldBlock
            );
            return;
        }
        assert_eq!(result, 192);
    }
    panic!("bounded actual send buffer did not fill");
}
fn real_send_backpressure_consumes_cancel_and_report() {
    for kind in [1, 2] {
        let directory = Directory::new();
        let path = directory.0.join("original.sock");
        let (sender_control, receiver_control) = controls();
        let raw = UnixStream::from(if kind == 1 {
            sender_control.as_fd().try_clone_to_owned().unwrap()
        } else {
            receiver_control.as_fd().try_clone_to_owned().unwrap()
        });
        let receiver = HandoffReceiver::from_control(receiver_control, policy(), &path).unwrap();
        let sender = HandoffSender::from_control(sender_control, policy(), WAIT).unwrap();
        let (accepted, _client) = original(&path);
        let mut sender = sender
            .send_retained(AcceptedStreamCustody::capture(accepted, &path, WAIT).unwrap())
            .unwrap();
        let (_received, mut receiver) = receiver
            .receive_retained(WAIT)
            .unwrap()
            .into_parts()
            .unwrap();
        fill_send_buffer(&raw);
        let start = Instant::now();
        if kind == 1 {
            assert_eq!(sender.request_cancel(), Err(HandoffError::Io));
            assert_eq!(sender.request_cancel(), Err(HandoffError::ChannelRetired));
        } else {
            assert_eq!(
                receiver.send_report(report(RemoteTerminalState::Completed)),
                Err(HandoffError::Io)
            );
            assert_eq!(
                receiver.send_report(report(RemoteTerminalState::Completed)),
                Err(HandoffError::ChannelRetired)
            );
        }
        assert!(start.elapsed() < Duration::from_millis(250));
    }
}
fn main() {
    let cases: &[(&str, fn())] = &[
        (
            "original socket identity/deadline/three remote states",
            identity_deadline_original_stream_and_report,
        ),
        (
            "single cancellation no application bytes",
            cancellation_once_no_synthetic_application_bytes,
        ),
        (
            "nonblocking report/cancel/terminal/EOF fail-stop",
            nonblocking_report_then_same_channel_cancel_and_one_terminal,
        ),
        (
            "duplicate sender cancellation fail-stop",
            sender_duplicate_cancellation_consumes_endpoint,
        ),
        (
            "original expiry and queued custody cannot renew",
            original_budget_expiry_wait_and_queue_no_renewal,
        ),
        (
            "EOF and ambiguous report no retry",
            eof_and_ambiguous_report_publication_no_retry,
        ),
        (
            "all fixed frame binding mutations",
            exact_frame_mutations_refuse_cancel_and_report,
        ),
        (
            "closed digest fields and zero report refusal",
            closed_digest_fields_and_zero_report_refusals,
        ),
        (
            "short long rights CTRUNC actual cleanup",
            malformed_length_and_rights_all_closed,
        ),
        (
            "cancel duplicate and cross transaction replay",
            duplicate_cancel_packet_refuses_and_cross_transaction_replay,
        ),
        (
            "real SCM_PIDFD both sideband directions",
            actual_sideband_pidfds_and_rights_cleanup,
        ),
        (
            "creator PID and child Drop preserve parent",
            inherited_child_api_refusal_drop_preserves_parent_channel,
        ),
        (
            "real foreign writer credentials both directions",
            actual_foreign_writer_credentials_refused,
        ),
        (
            "actual distinct process retained cancellation and report",
            actual_distinct_process_retained_cancel_and_report,
        ),
        (
            "actual send backpressure consumes cancel/report",
            real_send_backpressure_consumes_cancel_and_report,
        ),
    ];
    for (name, test) in cases {
        let before = inventory();
        test();
        assert_eq!(inventory(), before, "FD leak: {name}");
        println!("PASS: {name}");
    }
    println!(
        "{} actual retained-control kernel groups PASS; remote assertions, source only; no journal/native/installed authority",
        cases.len()
    );
}
