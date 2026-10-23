// SPDX-License-Identifier: MPL-2.0

use ostd::prelude::ktest;

use super::*;
use crate::{
    events::{EventFile, EventFileFlags},
    fs::{
        file::{AccessMode, InodeHandle, InodeType, StatusFlags, mkmod},
        pipe,
        ramfs::RamFs,
        vfs::{
            path::{Mount, Path, PerMountFlags},
            registry::FsAndRoot,
        },
    },
    net::socket::{
        Socket,
        unix::UnixSocketAddr,
        util::{MessageHeader, SendFlags},
    },
    util::net::SockType,
};

fn init() {
    crate::time::clocks::init_for_ktest();
    crate::util::random::init();
}

fn bound(name: &[u8]) -> Arc<UnixDatagramSocket> {
    let socket = UnixDatagramSocket::new(true).unwrap();
    socket
        .bind(UnixSocketAddr::Abstract(Arc::from(name)).into())
        .unwrap();
    socket
}

fn header(destination: &UnixDatagramSocket, files: Vec<Arc<dyn FileLike>>) -> MessageHeader {
    MessageHeader::new(
        Some(destination.addr().unwrap()),
        vec![ControlMessage::Unix(
            UnixControlMessage::from_files_for_test(files),
        )],
    )
}

fn received_files(header: MessageHeader) -> Vec<Arc<dyn FileLike>> {
    assert_eq!(header.control_messages.len(), 1);
    let ControlMessage::Unix(UnixControlMessage(Message::Files(message))) =
        header.control_messages.into_iter().next().unwrap()
    else {
        panic!("not a descriptor control message");
    };
    message.files
}

#[ktest]
fn regular_pipe_eventfd_rights_preserve_real_owners_through_peek_and_receive() {
    init();
    let sender = bound(b"rights-positive-sender");
    let receiver = bound(b"rights-positive-target");
    let mount = Mount::new_detached(
        FsAndRoot::new(RamFs::new()),
        PerMountFlags::empty(),
        Weak::new(),
        None,
    )
    .unwrap();
    let path = Path::new_root(mount)
        .new_child("file", InodeType::File, mkmod!(u+rw))
        .unwrap();
    let regular = Arc::new(
        InodeHandle::new_unchecked_access(path, AccessMode::O_RDWR, StatusFlags::empty()).unwrap(),
    ) as Arc<dyn FileLike>;
    let (pipe_reader, pipe_writer) = pipe::new_file_pair(StatusFlags::O_NONBLOCK).unwrap();
    let pipe_reader = pipe_reader as Arc<dyn FileLike>;
    let event = Arc::new(EventFile::new(7, EventFileFlags::empty())) as Arc<dyn FileLike>;
    let weak = [
        Arc::downgrade(&regular),
        Arc::downgrade(&pipe_reader),
        Arc::downgrade(&event),
    ];
    assert_eq!(
        sender
            .sendmsg(
                &mut VmReader::from(&[][..]).to_fallible(),
                header(&receiver, vec![regular, pipe_reader, event]),
                SendFlags::empty()
            )
            .unwrap(),
        0
    );
    assert!(weak.iter().all(|file| file.upgrade().is_some()));
    let (_, peek_header) = receiver
        .recvmsg(
            &mut VmWriter::from(&mut [][..]).to_fallible(),
            RecvFlags::MSG_PEEK,
        )
        .unwrap();
    let peeked = received_files(peek_header);
    let (_, recv_header) = receiver
        .recvmsg(
            &mut VmWriter::from(&mut [][..]).to_fallible(),
            RecvFlags::empty(),
        )
        .unwrap();
    let received = received_files(recv_header);
    assert_eq!(received.len(), 3);
    for (peek, recv) in peeked.iter().zip(&received) {
        assert!(Arc::ptr_eq(peek, recv));
    }
    drop(peeked);
    assert!(weak.iter().all(|file| file.upgrade().is_some()));
    assert_eq!(
        received[0]
            .write_at(0, &mut VmReader::from(&[0x55][..]).to_fallible())
            .unwrap(),
        1
    );
    let mut byte = [0u8];
    assert_eq!(
        received[0]
            .read_at(0, &mut VmWriter::from(&mut byte[..]).to_fallible())
            .unwrap(),
        1
    );
    assert_eq!(byte, [0x55]);
    assert_eq!(
        pipe_writer
            .write(&mut VmReader::from(&[0x66][..]).to_fallible())
            .unwrap(),
        1
    );
    assert_eq!(
        received[1]
            .read(&mut VmWriter::from(&mut byte[..]).to_fallible())
            .unwrap(),
        1
    );
    assert_eq!(byte, [0x66]);
    let mut count = [0u8; 8];
    assert_eq!(
        received[2]
            .read(&mut VmWriter::from(&mut count[..]).to_fallible())
            .unwrap(),
        8
    );
    assert_eq!(u64::from_ne_bytes(count), 7);
    drop((received, pipe_writer));
    assert!(weak.iter().all(|file| file.upgrade().is_none()));
}

#[ktest]
fn self_cross_and_future_datagram_connection_cycles_reject_before_copy() {
    init();
    let a = bound(b"rights-graph-cycle-a");
    let b = bound(b"rights-graph-cycle-b");
    let weak_a = Arc::downgrade(&a);
    let weak_b = Arc::downgrade(&b);
    let mut reader = VmReader::from(&[7][..]).to_fallible();
    assert_eq!(
        a.sendmsg(&mut reader, header(&a, vec![a.clone()]), SendFlags::empty())
            .unwrap_err()
            .error(),
        Errno::ELOOP
    );
    assert_eq!(reader.remain(), 1);
    a.sendmsg(
        &mut VmReader::from(&[][..]).to_fallible(),
        header(&a, vec![b.clone()]),
        SendFlags::empty(),
    )
    .unwrap();
    assert_eq!(
        b.sendmsg(&mut reader, header(&b, vec![a.clone()]), SendFlags::empty())
            .unwrap_err()
            .error(),
        Errno::ELOOP
    );
    assert_eq!(reader.remain(), 1);
    assert_eq!(
        b.connect(a.addr().unwrap()).unwrap_err().error(),
        Errno::ELOOP
    );
    assert_eq!(b.peer_addr().unwrap_err().error(), Errno::ENOTCONN);
    drop((a, b));
    assert!(weak_a.upgrade().is_none());
    assert!(weak_b.upgrade().is_none());
}

#[ktest]
fn real_peek_and_received_control_aliases_keep_original_owner_admission() {
    init();
    let a = bound(b"rights-graph-alias-a");
    let b = bound(b"rights-graph-alias-b");
    let weak_a = Arc::downgrade(&a);
    let weak_b = Arc::downgrade(&b);
    a.sendmsg(
        &mut VmReader::from(&[][..]).to_fallible(),
        header(&a, vec![b.clone()]),
        SendFlags::empty(),
    )
    .unwrap();
    let (_, peek) = a
        .recvmsg(
            &mut VmWriter::from(&mut [][..]).to_fallible(),
            RecvFlags::MSG_PEEK,
        )
        .unwrap();
    let (_, received) = a
        .recvmsg(
            &mut VmWriter::from(&mut [][..]).to_fallible(),
            RecvFlags::empty(),
        )
        .unwrap();
    let reverse = || {
        b.sendmsg(
            &mut VmReader::from(&[][..]).to_fallible(),
            header(&b, vec![a.clone()]),
            SendFlags::empty(),
        )
    };
    assert_eq!(reverse().unwrap_err().error(), Errno::ELOOP);
    drop(received);
    assert_eq!(reverse().unwrap_err().error(), Errno::ELOOP);
    drop(peek);
    assert_eq!(reverse().unwrap(), 0);
    drop((a, b));
    assert!(weak_a.upgrade().is_none());
    assert!(weak_b.upgrade().is_none());
}

#[ktest]
fn original_notes_socket_types_transfer_acyclically_on_stream_and_seqpacket() {
    init();
    for kind in [SockType::SOCK_STREAM, SockType::SOCK_SEQPACKET] {
        let (sender, receiver) = UnixStreamSocket::pair_for_ownership_test(kind);
        let (effect, effect_peer) =
            UnixStreamSocket::pair_for_ownership_test(SockType::SOCK_STREAM);
        let recovery = UnixDatagramSocket::new(true).unwrap();
        let weak_effect = Arc::downgrade(&effect);
        let weak_recovery = Arc::downgrade(&recovery);
        let header = MessageHeader::new(
            None,
            vec![ControlMessage::Unix(
                UnixControlMessage::from_files_for_test(vec![effect, recovery]),
            )],
        );
        assert_eq!(
            sender
                .sendmsg(
                    &mut VmReader::from(&[0x48][..]).to_fallible(),
                    header,
                    SendFlags::empty()
                )
                .unwrap(),
            1
        );
        let mut output = [0u8];
        let (len, header) = receiver
            .recvmsg(
                &mut VmWriter::from(&mut output[..]).to_fallible(),
                RecvFlags::empty(),
            )
            .unwrap();
        assert_eq!(len.len(), 1);
        assert_eq!(output, [0x48]);
        let files = received_files(header);
        assert_eq!(files.len(), 2);
        let effect = (&*files[0] as &dyn Any)
            .downcast_ref::<UnixStreamSocket>()
            .unwrap();
        let recovery = (&*files[1] as &dyn Any)
            .downcast_ref::<UnixDatagramSocket>()
            .unwrap();
        assert_eq!(
            effect
                .sendmsg(
                    &mut VmReader::from(&[0x49][..]).to_fallible(),
                    MessageHeader::new(None, Vec::new()),
                    SendFlags::empty()
                )
                .unwrap(),
            1
        );
        effect_peer
            .recvmsg(
                &mut VmWriter::from(&mut output[..]).to_fallible(),
                RecvFlags::empty(),
            )
            .unwrap();
        assert_eq!(output, [0x49]);
        assert!(recovery.addr().is_ok());
        drop((files, sender, receiver, effect_peer));
        assert!(weak_effect.upgrade().is_none());
        assert!(weak_recovery.upgrade().is_none());
    }
}

#[ktest]
fn shared_stream_pair_rejects_either_endpoint_and_cross_transport_back_edge() {
    init();
    for kind in [SockType::SOCK_STREAM, SockType::SOCK_SEQPACKET] {
        let (sender, receiver) = UnixStreamSocket::pair_for_ownership_test(kind);
        let weak_sender = Arc::downgrade(&sender);
        let weak_receiver = Arc::downgrade(&receiver);
        for file in [sender.clone(), receiver.clone()] {
            let mut input = VmReader::from(&[0x11][..]).to_fallible();
            let message = MessageHeader::new(
                None,
                vec![ControlMessage::Unix(
                    UnixControlMessage::from_files_for_test(vec![file]),
                )],
            );
            assert_eq!(
                sender
                    .sendmsg(&mut input, message, SendFlags::empty())
                    .unwrap_err()
                    .error(),
                Errno::ELOOP
            );
            assert_eq!(input.remain(), 1);
        }
        let datagram = bound(if kind == SockType::SOCK_STREAM {
            b"rights-mixed-stream"
        } else {
            b"rights-mixed-seqpacket"
        });
        let message = MessageHeader::new(
            None,
            vec![ControlMessage::Unix(
                UnixControlMessage::from_files_for_test(vec![datagram.clone()]),
            )],
        );
        sender
            .sendmsg(
                &mut VmReader::from(&[0x12][..]).to_fallible(),
                message,
                SendFlags::empty(),
            )
            .unwrap();
        assert_eq!(
            datagram
                .sendmsg(
                    &mut VmReader::from(&[][..]).to_fallible(),
                    header(&datagram, vec![receiver.clone()]),
                    SendFlags::empty()
                )
                .unwrap_err()
                .error(),
            Errno::ELOOP
        );
        drop((sender, receiver, datagram));
        assert!(weak_sender.upgrade().is_none());
        assert!(weak_receiver.upgrade().is_none());
    }
}

#[ktest]
fn concurrent_opposite_real_socket_sends_admit_only_one_edge() {
    use core::sync::atomic::{AtomicBool, AtomicUsize, Ordering};

    use crate::thread::kernel_thread::ThreadOptions;
    init();
    let a = bound(b"rights-concurrent-a");
    let b = bound(b"rights-concurrent-b");
    let weak_a = Arc::downgrade(&a);
    let weak_b = Arc::downgrade(&b);
    let start = Arc::new(AtomicBool::new(false));
    let accepted = Arc::new(AtomicUsize::new(0));
    let rejected = Arc::new(AtomicUsize::new(0));
    let mut workers = Vec::new();
    for (destination, file) in [(a.clone(), b.clone()), (b.clone(), a.clone())] {
        let (start, accepted, rejected) = (start.clone(), accepted.clone(), rejected.clone());
        workers.push(
            ThreadOptions::new(move || {
                while !start.load(Ordering::Acquire) {
                    Task::yield_now();
                }
                match destination.sendmsg(
                    &mut VmReader::from(&[][..]).to_fallible(),
                    header(&destination, vec![file]),
                    SendFlags::empty(),
                ) {
                    Ok(0) => {
                        accepted.fetch_add(1, Ordering::Release);
                    }
                    Err(error) if error.error() == Errno::ELOOP => {
                        rejected.fetch_add(1, Ordering::Release);
                    }
                    result => panic!("unexpected graph send result: {:?}", result),
                }
            })
            .spawn(),
        );
    }
    start.store(true, Ordering::Release);
    for worker in &workers {
        worker.join();
    }
    assert_eq!(accepted.load(Ordering::Acquire), 1);
    assert_eq!(rejected.load(Ordering::Acquire), 1);
    drop((workers, a, b));
    assert!(weak_a.upgrade().is_none());
    assert!(weak_b.upgrade().is_none());
}

#[ktest]
fn stream_full_failure_refunds_edge_and_partial_write_keeps_real_prefix_owner() {
    init();
    for full in [true, false] {
        let (sender, receiver) = UnixStreamSocket::pair_for_ownership_test(SockType::SOCK_STREAM);
        let datagram = bound(if full {
            b"rights-stream-full"
        } else {
            b"rights-stream-partial"
        });
        let fill = vec![0x55; if full { 65536 } else { 65530 }];
        assert_eq!(
            sender
                .sendmsg(
                    &mut VmReader::from(&fill[..]).to_fallible(),
                    MessageHeader::new(None, Vec::new()),
                    SendFlags::empty()
                )
                .unwrap(),
            fill.len()
        );
        let mut reader = VmReader::from(&[0x56; 16][..]).to_fallible();
        let control = MessageHeader::new(
            None,
            vec![ControlMessage::Unix(
                UnixControlMessage::from_files_for_test(vec![datagram.clone()]),
            )],
        );
        let result = sender.sendmsg(&mut reader, control, SendFlags::empty());
        let reverse = || {
            datagram.sendmsg(
                &mut VmReader::from(&[][..]).to_fallible(),
                header(&datagram, vec![receiver.clone()]),
                SendFlags::empty(),
            )
        };
        if full {
            assert_eq!(result.unwrap_err().error(), Errno::EAGAIN);
            assert_eq!(reader.remain(), 16);
            assert_eq!(reverse().unwrap(), 0);
        } else {
            assert_eq!(result.unwrap(), 6);
            assert_eq!(reader.remain(), 10);
            assert_eq!(reverse().unwrap_err().error(), Errno::ELOOP);
            let mut bytes = vec![0u8; 65536];
            let (read, first) = receiver
                .recvmsg(
                    &mut VmWriter::from(&mut bytes[..]).to_fallible(),
                    RecvFlags::empty(),
                )
                .unwrap();
            assert_eq!(read.len(), fill.len());
            assert!(first.control_messages.is_empty());
            let (read, second) = receiver
                .recvmsg(
                    &mut VmWriter::from(&mut bytes[..]).to_fallible(),
                    RecvFlags::empty(),
                )
                .unwrap();
            assert_eq!(read.len(), 6);
            assert_eq!(&bytes[..6], &[0x56; 6]);
            assert_eq!(second.control_messages.len(), 1);
            assert_eq!(reverse().unwrap_err().error(), Errno::ELOOP);
            drop(second);
            assert_eq!(reverse().unwrap(), 0);
        }
        let weak_sender = Arc::downgrade(&sender);
        let weak_receiver = Arc::downgrade(&receiver);
        let weak_datagram = Arc::downgrade(&datagram);
        drop((sender, receiver, datagram));
        assert!(weak_sender.upgrade().is_none());
        assert!(weak_receiver.upgrade().is_none());
        assert!(weak_datagram.upgrade().is_none());
    }
}
