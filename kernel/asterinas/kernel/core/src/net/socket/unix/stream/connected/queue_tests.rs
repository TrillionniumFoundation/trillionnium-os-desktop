// SPDX-License-Identifier: MPL-2.0

use ostd::prelude::ktest;

use super::*;
use crate::{
    events::{EventFile, EventFileFlags},
    net::socket::{
        Socket,
        unix::{UnixStreamSocket, ctrl_msg::UnixControlMessage},
        util::{MessageHeader, SendFlags},
    },
    process::{posix_thread::AsPosixThread, signal::Pollable, test_util},
    thread::kernel_thread::ThreadOptions,
    util::net::SockType,
    vm::user_memory::UserMemoryAccount,
};

fn pair() -> (Connected, Connected, Arc<UserMemoryAccount>) {
    crate::time::clocks::init_for_ktest();
    crate::util::random::init();
    let (process, task) = test_util::new_unstarted_process();
    let cred = || SocketCred::from_posix_thread_for_test(task.as_posix_thread().unwrap());
    let owner = UserMemoryAccount::new(32);
    let buffers = Buffers::new(&Some(owner.clone())).unwrap();
    let pair = Connected::new_pair(
        buffers,
        None,
        None,
        EndpointState::default(),
        EndpointState::default(),
        cred(),
        cred(),
    );
    drop((task, process));
    (pair.0, pair.1, owner)
}

fn empty_send(sender: &Connected) -> Result<usize> {
    sender.try_write(
        &mut VmReader::from(&[][..]).to_fallible(),
        &mut AuxiliaryData::default(),
        true,
    )
}

#[ktest]
fn empty_seqpackets_bound_original_aux_queue_and_peek_keeps_slot() {
    let (sender, receiver, owner) = pair();
    assert!(!receiver.check_io_events(true).contains(IoEvents::IN));
    for _ in 0..UNIX_SEQPACKET_MAX_QUEUED_MESSAGES {
        assert_eq!(empty_send(&sender).unwrap(), 0);
    }
    assert!(receiver.check_io_events(true).contains(IoEvents::IN));
    assert_eq!(sender.inner.this_end().writer.lock().len(), 0);
    assert_eq!(sender.inner.this_end().all_aux.lock().len(), 128);
    assert_eq!(empty_send(&sender).unwrap_err().error(), Errno::EAGAIN);
    receiver
        .try_read(
            &mut VmWriter::from(&mut [][..]).to_fallible(),
            true,
            RecvFlags::MSG_PEEK,
        )
        .unwrap();
    assert_eq!(empty_send(&sender).unwrap_err().error(), Errno::EAGAIN);
    receiver
        .try_read(
            &mut VmWriter::from(&mut [][..]).to_fallible(),
            true,
            RecvFlags::empty(),
        )
        .unwrap();
    assert_eq!(empty_send(&sender).unwrap(), 0);
    assert_eq!(owner.current_pages(), 32);
    drop((sender, receiver));
    assert_eq!(owner.current_pages(), 0);
}

#[ktest]
fn full_aux_queue_rejects_before_reader_or_control_consumption() {
    let (sender, receiver, owner) = pair();
    for _ in 0..UNIX_SEQPACKET_MAX_QUEUED_MESSAGES {
        empty_send(&sender).unwrap();
    }
    let mut reader = VmReader::from(&[0x71][..]).to_fallible();
    let event = Arc::new(EventFile::new(7, EventFileFlags::empty()));
    let weak = Arc::downgrade(&event);
    let mut aux = AuxiliaryData::from_control(vec![ControlMessage::Unix(
        UnixControlMessage::from_files_for_test(vec![event]),
    )])
    .unwrap();
    assert_eq!(
        sender
            .try_write(&mut reader, &mut aux, true)
            .unwrap_err()
            .error(),
        Errno::EAGAIN
    );
    assert_eq!(reader.remain(), 1);
    assert!(!aux.is_empty());
    assert!(weak.upgrade().is_some());
    assert_eq!(sender.inner.this_end().writer.lock().len(), 0);
    assert_eq!(sender.inner.this_end().all_aux.lock().len(), 128);
    receiver
        .try_read(
            &mut VmWriter::from(&mut [][..]).to_fallible(),
            true,
            RecvFlags::empty(),
        )
        .unwrap();
    assert_eq!(sender.try_write(&mut reader, &mut aux, true).unwrap(), 1);
    assert_eq!(reader.remain(), 0);
    assert!(aux.is_empty());
    assert!(weak.upgrade().is_some());
    drop((sender, receiver));
    assert!(weak.upgrade().is_none());
    assert_eq!(owner.current_pages(), 0);
}

#[ktest]
fn blocked_seqpacket_sender_wakes_on_empty_receive_and_peer_close() {
    for close in [false, true] {
        let (sender, receiver, owner) = pair();
        for _ in 0..UNIX_SEQPACKET_MAX_QUEUED_MESSAGES {
            empty_send(&sender).unwrap();
        }
        let sender = UnixStreamSocket::new_connected(
            sender,
            super::super::socket::OptionSet::new_accepted(false),
            false,
            SockType::SOCK_SEQPACKET,
        );
        assert!(!sender.poll(IoEvents::OUT, None).contains(IoEvents::OUT));
        let done = Arc::new(AtomicBool::new(false));
        let started = Arc::new(AtomicBool::new(false));
        let worker_done = done.clone();
        let worker_started = started.clone();
        let worker = ThreadOptions::new(move || {
            worker_started.store(true, Ordering::Release);
            let result = sender.sendmsg(
                &mut VmReader::from(&[][..]).to_fallible(),
                MessageHeader::new(None, Vec::new()),
                SendFlags::empty(),
            );
            if close {
                assert_eq!(result.unwrap_err().error(), Errno::EPIPE);
            } else {
                assert_eq!(result.unwrap(), 0);
            }
            worker_done.store(true, Ordering::Release);
        })
        .spawn();
        for _ in 0..128 {
            ostd::task::Task::yield_now();
            if started.load(Ordering::Acquire) {
                break;
            }
        }
        assert!(started.load(Ordering::Acquire));
        assert!(!done.load(Ordering::Acquire));
        if close {
            drop(receiver);
        } else {
            receiver
                .try_read(
                    &mut VmWriter::from(&mut [][..]).to_fallible(),
                    true,
                    RecvFlags::empty(),
                )
                .unwrap();
            worker.join();
            assert!(done.load(Ordering::Acquire));
            drop(receiver);
        }
        worker.join();
        assert!(done.load(Ordering::Acquire));
        drop(worker);
        assert_eq!(owner.current_pages(), 0);
    }
}
