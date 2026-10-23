// SPDX-License-Identifier: MPL-2.0

use ostd::prelude::ktest;

use super::*;
use crate::{
    fs::{cgroupfs::CgroupMembership, pseudofs::SockFs},
    process::ProcessVm,
    thread::kernel_thread::ThreadOptions,
    vm::{
        perms::VmPerms,
        user_memory::{UserMemoryAccount, hierarchy},
        vmar::{Vmar, VmarHandle, VmarMapOffset},
    },
};

// Real associated VMAR, original current_owner lookup, and real user-copy fault
// handling. Completion prevents the kernel thread's panic catcher from passing
// an incomplete test. The final RCU witness also covers mapped test source pages.
fn with_sender(owner: Arc<UserMemoryAccount>, test: impl FnOnce(Arc<Vmar>) + Send + 'static) {
    crate::time::clocks::init_for_ktest();
    crate::util::random::init();
    let vmar = VmarHandle::new_with_owner(ProcessVm::new(SockFs::new_path()), Some(owner.clone()));
    let worker_vmar = vmar.clone_arc();
    let complete = Arc::new(AtomicBool::new(false));
    let worker_complete = complete.clone();
    let worker = ThreadOptions::new(move || {
        test(worker_vmar);
        worker_complete.store(true, Ordering::Release);
    })
    .vmar(vmar.clone_arc())
    .spawn();
    worker.join();
    assert!(complete.load(Ordering::Acquire));
    drop((worker, vmar));
    hierarchy::test_wait_for_rcu_refunds();
    assert_eq!(owner.current_pages(), 0);
}

fn send(target: &MessageReceiver, source: &MessageReceiver, data: &[u8]) -> Result<usize> {
    target.queue.try_send(
        &mut VmReader::from(data).to_fallible(),
        &mut AuxiliaryData::default(),
        source,
    )
}

#[ktest]
fn payload_peek_truncation_and_alias_keep_original_physical_charge() {
    let owner = UserMemoryAccount::new(2);
    let observed = owner.clone();
    with_sender(owner, move |_| {
        let (source, target) = (MessageReceiver::new(), MessageReceiver::new());
        let data = vec![0x5a; PAGE_SIZE + 37];
        assert_eq!(send(&target, &source, &data).unwrap(), data.len());
        assert_eq!(observed.current_pages(), 2);
        let alias = target.queue.inner.lock().as_ref().unwrap().messages[0]
            .bytes
            .frames
            .as_ref()
            .unwrap()
            .clone();
        let mut output = [0u8; 53];
        let (received, _, _) = target
            .try_recv(
                &mut VmWriter::from(&mut output[..]).to_fallible(),
                RecvFlags::MSG_PEEK,
            )
            .unwrap();
        assert_eq!(received.len(), output.len());
        assert!(received.flags().contains(RecvFlags::MSG_TRUNC));
        assert_eq!(output, [0x5a; 53]);
        assert_eq!(observed.current_pages(), 2);
        let (received, _, _) = target
            .try_recv(
                &mut VmWriter::from(&mut output[..]).to_fallible(),
                RecvFlags::MSG_TRUNC,
            )
            .unwrap();
        assert_eq!(received.len(), data.len());
        assert!(
            target
                .queue
                .inner
                .lock()
                .as_ref()
                .unwrap()
                .messages
                .is_empty()
        );
        assert_eq!(observed.current_pages(), 2);
        drop(alias);
        assert_eq!(observed.current_pages(), 0);
    });
}

#[ktest]
fn ancestor_quota_denial_does_not_consume_reader_or_publish_datagram() {
    let domain = hierarchy::test_leaf(1);
    domain.set_delegated(true);
    let leaf = hierarchy::MemoryDomain::child(domain.clone()).unwrap();
    let owner = UserMemoryAccount::new(usize::MAX);
    owner.move_to(leaf, &CgroupMembership::write_lock());
    let observed = owner.clone();
    with_sender(owner, move |_| {
        let (source, target) = (MessageReceiver::new(), MessageReceiver::new());
        send(&target, &source, &[1]).unwrap();
        let mut reader = VmReader::from(&[2u8][..]).to_fallible();
        let error = target
            .queue
            .try_send(&mut reader, &mut AuxiliaryData::default(), &source)
            .unwrap_err();
        assert!(error.is_cgroup_frame_limit());
        assert_eq!(reader.remain(), 1);
        assert_eq!(observed.current_pages(), 1);
        assert_eq!(domain.snapshot().pages, 1);
        assert_eq!(
            target.queue.inner.lock().as_ref().unwrap().messages.len(),
            1
        );
        drop(target);
        assert_eq!(domain.snapshot().pages, 0);
    });
}

#[ktest]
fn actual_user_copy_fault_refunds_unpublished_pages_and_preserves_receive() {
    let owner = UserMemoryAccount::new(3);
    let observed = owner.clone();
    with_sender(owner, move |vmar| {
        const BASE: usize = PAGE_SIZE * 16;
        vmar.new_map(PAGE_SIZE, VmPerms::READ | VmPerms::WRITE)
            .offset(VmarMapOffset::FixedNoReplace(BASE))
            .build()
            .unwrap();
        vmar.write_alien(BASE, &mut VmReader::from(&[0x44u8][..]).to_fallible())
            .unwrap();
        assert_eq!(observed.current_pages(), 1);
        let (source, target) = (MessageReceiver::new(), MessageReceiver::new());
        let mut reader = vmar.vm_space().reader(BASE, PAGE_SIZE + 17).unwrap();
        let error = target
            .queue
            .try_send(&mut reader, &mut AuxiliaryData::default(), &source)
            .unwrap_err();
        assert_eq!(error.error(), Errno::EFAULT);
        assert_eq!(reader.remain(), 17);
        assert_eq!(observed.current_pages(), 1);
        assert!(
            target
                .queue
                .inner
                .lock()
                .as_ref()
                .unwrap()
                .messages
                .is_empty()
        );
        assert_eq!(target.queue.inner.lock().as_ref().unwrap().total_length, 0);
        send(&target, &source, &[0x37]).unwrap();
        let mut writer = vmar.vm_space().writer(BASE + PAGE_SIZE, 1).unwrap();
        assert_eq!(
            target
                .try_recv(&mut writer, RecvFlags::empty())
                .unwrap_err()
                .error(),
            Errno::EFAULT
        );
        assert_eq!(observed.current_pages(), 2);
        let mut output = [0u8; 1];
        target
            .try_recv(
                &mut VmWriter::from(&mut output[..]).to_fallible(),
                RecvFlags::empty(),
            )
            .unwrap();
        assert_eq!(output, [0x37]);
        assert_eq!(observed.current_pages(), 1);
    });
}

#[ktest]
fn migration_and_receiver_close_refund_captured_domains_with_retained_queue() {
    let old = hierarchy::test_leaf(1);
    let new = hierarchy::test_leaf(1);
    let owner = UserMemoryAccount::new(2);
    owner.move_to(old.clone(), &CgroupMembership::write_lock());
    let observed = owner.clone();
    with_sender(owner, move |_| {
        let (source, target) = (MessageReceiver::new(), MessageReceiver::new());
        let queue = target.queue.clone();
        send(&target, &source, &[1]).unwrap();
        observed.move_to(new.clone(), &CgroupMembership::write_lock());
        send(&target, &source, &[2]).unwrap();
        assert_eq!(old.snapshot().pages, 1);
        assert_eq!(new.snapshot().pages, 1);
        assert_eq!(observed.current_pages(), 2);
        drop(target);
        assert!(queue.inner.lock().is_none());
        assert_eq!(old.snapshot().pages, 0);
        assert_eq!(new.snapshot().pages, 0);
        assert_eq!(observed.current_pages(), 0);
        let mut reader = VmReader::from(&[3u8][..]).to_fallible();
        assert_eq!(
            queue
                .try_send(&mut reader, &mut AuxiliaryData::default(), &source)
                .unwrap_err()
                .error(),
            Errno::ECONNREFUSED
        );
        assert_eq!(reader.remain(), 1);
    });
}

#[ktest]
fn empty_payload_and_original_byte_capacity_preserve_datagram_boundaries() {
    let owner = UserMemoryAccount::new(UNIX_DATAGRAM_DEFAULT_BUF_SIZE / PAGE_SIZE);
    let observed = owner.clone();
    with_sender(owner, move |_| {
        let (source, target) = (MessageReceiver::new(), MessageReceiver::new());
        send(&target, &source, &[]).unwrap();
        assert_eq!(observed.current_pages(), 0);
        let data = vec![0x77; UNIX_DATAGRAM_DEFAULT_BUF_SIZE];
        send(&target, &source, &data).unwrap();
        assert_eq!(observed.current_pages(), 16);
        assert_eq!(
            send(&target, &source, &[1]).unwrap_err().error(),
            Errno::EAGAIN
        );
        let oversized = vec![0; UNIX_DATAGRAM_DEFAULT_BUF_SIZE + 1];
        assert_eq!(
            send(&target, &source, &oversized).unwrap_err().error(),
            Errno::EMSGSIZE
        );
        assert_eq!(observed.current_pages(), 16);
        let mut output = vec![0xaa; UNIX_DATAGRAM_DEFAULT_BUF_SIZE + 17];
        let (received, _, _) = target
            .try_recv(
                &mut VmWriter::from(&mut output[..]).to_fallible(),
                RecvFlags::empty(),
            )
            .unwrap();
        assert_eq!(received.len(), 0);
        assert_eq!(observed.current_pages(), 16);
        let (received, _, _) = target
            .try_recv(
                &mut VmWriter::from(&mut output[..]).to_fallible(),
                RecvFlags::empty(),
            )
            .unwrap();
        assert_eq!(received.len(), data.len());
        assert_eq!(output[..data.len()], data[..]);
        assert_eq!(&output[data.len()..], &[0xaa; 17]);
        assert_eq!(observed.current_pages(), 0);
    });
}

#[ktest]
fn empty_message_slots_are_bounded_and_only_consumption_reopens_capacity() {
    let owner = UserMemoryAccount::new(0);
    with_sender(owner, move |_| {
        let (source, target) = (MessageReceiver::new(), MessageReceiver::new());
        for _ in 0..UNIX_DATAGRAM_MAX_QUEUED_MESSAGES {
            send(&target, &source, &[]).unwrap();
        }
        assert_eq!(target.queue.inner.lock().as_ref().unwrap().total_length, 0);
        assert_eq!(
            target.queue.inner.lock().as_ref().unwrap().messages.len(),
            UNIX_DATAGRAM_MAX_QUEUED_MESSAGES
        );
        assert_eq!(
            send(&target, &source, &[]).unwrap_err().error(),
            Errno::EAGAIN
        );
        let mut output = [];
        target
            .try_recv(
                &mut VmWriter::from(&mut output[..]).to_fallible(),
                RecvFlags::MSG_PEEK,
            )
            .unwrap();
        assert_eq!(
            send(&target, &source, &[]).unwrap_err().error(),
            Errno::EAGAIN
        );
        target
            .try_recv(
                &mut VmWriter::from(&mut output[..]).to_fallible(),
                RecvFlags::empty(),
            )
            .unwrap();
        send(&target, &source, &[]).unwrap();
        assert_eq!(
            target.queue.inner.lock().as_ref().unwrap().messages.len(),
            UNIX_DATAGRAM_MAX_QUEUED_MESSAGES
        );
    });
}

#[ktest]
fn message_slot_backpressure_precedes_new_payload_charge_and_reader_consumption() {
    let owner = UserMemoryAccount::new(usize::MAX);
    let domain = hierarchy::test_leaf(UNIX_DATAGRAM_MAX_QUEUED_MESSAGES + 1);
    owner.move_to(domain.clone(), &CgroupMembership::write_lock());
    let observed = owner.clone();
    with_sender(owner, move |_| {
        let (source, target) = (MessageReceiver::new(), MessageReceiver::new());
        for _ in 0..UNIX_DATAGRAM_MAX_QUEUED_MESSAGES {
            send(&target, &source, &[1]).unwrap();
        }
        assert_eq!(observed.current_pages(), UNIX_DATAGRAM_MAX_QUEUED_MESSAGES);
        assert_eq!(
            target.queue.inner.lock().as_ref().unwrap().total_length,
            UNIX_DATAGRAM_MAX_QUEUED_MESSAGES
        );
        let mut reader = VmReader::from(&[2u8][..]).to_fallible();
        assert_eq!(
            target
                .queue
                .try_send(&mut reader, &mut AuxiliaryData::default(), &source)
                .unwrap_err()
                .error(),
            Errno::EAGAIN
        );
        assert_eq!(reader.remain(), 1);
        assert_eq!(domain.snapshot().pages, UNIX_DATAGRAM_MAX_QUEUED_MESSAGES);
        assert_eq!(domain.snapshot().max_events, 0);
        drop(target);
        assert_eq!(domain.snapshot().pages, 0);
    });
}

#[ktest]
fn blocked_empty_sender_retries_after_consume_and_returns_refused_after_close() {
    use ostd::task::Task;

    let owner = UserMemoryAccount::new(0);
    with_sender(owner, move |vmar| {
        for close in [false, true] {
            let source = Arc::new(MessageReceiver::new());
            let target = MessageReceiver::new();
            for _ in 0..UNIX_DATAGRAM_MAX_QUEUED_MESSAGES {
                send(&target, &source, &[]).unwrap();
            }
            let queue = target.queue.clone();
            let source = source.clone();
            let attempted = Arc::new(AtomicBool::new(false));
            let done = Arc::new(AtomicBool::new(false));
            let worker_attempted = attempted.clone();
            let worker_done = done.clone();
            let worker = ThreadOptions::new(move || {
                let mut reader = VmReader::from(&[][..]).to_fallible();
                let mut aux = AuxiliaryData::default();
                let result = queue.block_send(Some(Duration::from_secs(1)), || {
                    let result = queue.try_send(&mut reader, &mut aux, &source);
                    if result
                        .as_ref()
                        .is_err_and(|err| err.error() == Errno::EAGAIN)
                    {
                        worker_attempted.store(true, Ordering::Release);
                    }
                    result
                });
                if close {
                    assert_eq!(result.unwrap_err().error(), Errno::ECONNREFUSED);
                } else {
                    assert_eq!(result.unwrap(), 0);
                }
                worker_done.store(true, Ordering::Release);
            })
            .vmar(vmar.clone())
            .spawn();
            for _ in 0..128 {
                Task::yield_now();
                if attempted.load(Ordering::Acquire) {
                    break;
                }
            }
            assert!(attempted.load(Ordering::Acquire));
            assert!(!done.load(Ordering::Acquire));
            if close {
                drop(target);
            } else {
                let mut output = [];
                target
                    .try_recv(
                        &mut VmWriter::from(&mut output[..]).to_fallible(),
                        RecvFlags::empty(),
                    )
                    .unwrap();
                worker.join();
                assert!(done.load(Ordering::Acquire));
                assert_eq!(
                    target.queue.inner.lock().as_ref().unwrap().messages.len(),
                    UNIX_DATAGRAM_MAX_QUEUED_MESSAGES
                );
                continue;
            }
            worker.join();
            assert!(done.load(Ordering::Acquire));
        }
    });
}
