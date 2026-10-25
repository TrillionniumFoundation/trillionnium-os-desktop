// SPDX-License-Identifier: MPL-2.0

//! Real pending-queue ownership and lifecycle regressions, without OOM injection.

use core::sync::atomic::{AtomicUsize, Ordering};

use ostd::{prelude::ktest, sync::Waiter};

use super::{
    HandlePendingSignal, PauseReason,
    c_types::siginfo_t,
    constants::*,
    sig_mask::SigMask,
    sig_num::SigNum,
    sig_queues::SigQueues,
    signals::{OwnedSignal, Signal, fault::FaultSignal, kernel::KernelSignal, user::UserSignal},
};
use crate::{
    prelude::*,
    process::{Uid, posix_thread::AsPosixThread, test_util},
};

#[ktest]
fn inline_fault_preserves_first_info_mask_and_original_priority() {
    let queue = SigQueues::new();
    let first = FaultSignal::new(SIGSEGV, 1, Some(0x1234));
    queue.enqueue_owned(OwnedSignal::new(first));
    queue.enqueue_owned(OwnedSignal::new(FaultSignal::new(SIGSEGV, 2, Some(0x5678))));
    assert!(queue.dequeue(&SigMask::from(SIGSEGV)).is_none());
    queue.enqueue_owned(OwnedSignal::new(KernelSignal::new(SIGKILL)));
    let kill = queue.dequeue(&SigMask::from(0)).unwrap();
    assert!(kill.is_inline());
    assert_eq!(kill.num(), SIGKILL);
    assert_eq!(kill.to_info().si_code, SI_KERNEL);
    let fault = queue.dequeue(&SigMask::from(0)).unwrap();
    assert!(fault.is_inline());
    assert_eq!(fault.num(), SIGSEGV);
    assert_eq!(fault.to_info().si_code, first.to_info().si_code);
    assert_eq!(fault.to_info().si_addr(), 0x1234);
    assert!(queue.is_empty());
}

#[derive(Debug)]
struct DropSignal {
    num: SigNum,
    tag: i32,
    drops: Arc<AtomicUsize>,
}

impl Signal for DropSignal {
    fn num(&self) -> SigNum {
        self.num
    }
    fn to_info(&self) -> siginfo_t {
        siginfo_t::new(self.num, self.tag)
    }
}

impl Drop for DropSignal {
    fn drop(&mut self) {
        self.drops.fetch_add(1, Ordering::Relaxed);
    }
}

#[ktest]
fn dynamic_realtime_keeps_original_fifo_and_drops_each_owner_once() {
    let queue = SigQueues::new();
    let drops = Arc::new(AtomicUsize::new(0));
    let rt = SigNum::try_from(MIN_RT_SIG_NUM).unwrap();
    for tag in [11, 12] {
        queue.enqueue_owned(OwnedSignal::from_box(Box::new(DropSignal {
            num: rt,
            tag,
            drops: drops.clone(),
        })));
    }
    queue.enqueue_owned(OwnedSignal::from_box(Box::new(DropSignal {
        num: SIGUSR1,
        tag: 21,
        drops: drops.clone(),
    })));
    queue.enqueue_owned(OwnedSignal::from_box(Box::new(DropSignal {
        num: SIGUSR1,
        tag: 22,
        drops: drops.clone(),
    })));
    assert_eq!(drops.load(Ordering::Relaxed), 1); // Coalesced standard owner.
    for tag in [21, 11, 12] {
        let signal = queue.dequeue(&SigMask::from(0)).unwrap();
        assert!(!signal.is_inline());
        assert_eq!(signal.to_info().si_code, tag);
        let before = drops.load(Ordering::Relaxed);
        drop(signal);
        assert_eq!(drops.load(Ordering::Relaxed), before + 1);
    }
    assert_eq!(drops.load(Ordering::Relaxed), 4);
    assert!(queue.is_empty());
    // A concrete FaultSignal carrying an RT number cannot enter inline storage.
    let rt_fault = OwnedSignal::new(FaultSignal::new(rt, 31, Some(0x4321)));
    assert!(!rt_fault.is_inline());
    queue.enqueue_owned(rt_fault);
    assert_eq!(
        queue
            .dequeue(&SigMask::from(0))
            .unwrap()
            .to_info()
            .si_addr(),
        0x4321
    );
}

#[ktest]
fn inline_user_kill_keeps_siginfo_and_irreversible_original_receipt() {
    use super::signals::user::UserSignalKind;
    for kind in [UserSignalKind::Kill, UserSignalKind::Tkill] {
        let queue = SigQueues::new();
        let signal = UserSignal::new(SIGKILL, kind, 73, Uid::new(501));
        let info = signal.to_info();
        let owner = OwnedSignal::new(signal);
        assert!(owner.is_inline());
        assert_eq!(owner.to_info().as_bytes(), info.as_bytes());
        queue.enqueue_owned(owner);
        assert!(queue.has_received_sigkill());
        let signal = queue.dequeue(&SigMask::from(0)).unwrap();
        assert_eq!(signal.to_info().as_bytes(), info.as_bytes());
        assert!(signal.is_inline());
        assert!(queue.is_empty());
        assert!(queue.has_received_sigkill());
        drop(signal);
        assert!(queue.has_received_sigkill());
        assert!(!SigQueues::new().has_received_sigkill());
    }
}

#[ktest]
fn inline_signal_wakes_original_thread_and_process_without_retaining_them() {
    let (process, tasks) = test_util::new_unstarted_process_with_threads(2);
    let parent = test_util::UnstartedParent::new(&process);
    let weak = Arc::downgrade(&process);
    let first = tasks[0].as_posix_thread().unwrap();
    let second = tasks[1].as_posix_thread().unwrap();
    let (waiter, waker) = Waiter::new_pair();
    first.set_signalled_waker(waker.clone(), PauseReason::Sleep);
    first.enqueue_owned_signal(OwnedSignal::new(FaultSignal::new(SIGSEGV, 1, Some(0x4321))));
    assert!(!waker.wake_up()); // The original enqueue already woke this real waiter.
    waiter.wait();
    first.clear_signalled_waker();
    assert_eq!(
        first
            .dequeue_signal(&SigMask::from(0))
            .unwrap()
            .unwrap()
            .to_info()
            .si_addr(),
        0x4321
    );
    drop((waiter, waker));

    let (waiter1, waker1) = Waiter::new_pair();
    let (waiter2, waker2) = Waiter::new_pair();
    first.set_signalled_waker(waker1.clone(), PauseReason::Sleep);
    second.set_signalled_waker(waker2.clone(), PauseReason::Sleep);
    process.enqueue_owned_signal(OwnedSignal::new(KernelSignal::new(SIGKILL)));
    assert!(!waker1.wake_up() && !waker2.wake_up());
    waiter1.wait();
    waiter2.wait();
    first.clear_signalled_waker();
    second.clear_signalled_waker();
    assert!(first.has_fatal_sigkill() && second.has_fatal_sigkill());
    assert!(
        second
            .dequeue_signal(&SigMask::from(0))
            .unwrap()
            .unwrap()
            .is_inline()
    );
    assert!(first.has_fatal_sigkill() && second.has_fatal_sigkill());
    drop((waiter1, waiter2, waker1, waker2));
    test_util::mark_zombie(&process);
    parent.detach_zombie_child();
    drop(tasks);
    drop(process);
    assert!(weak.upgrade().is_none());
}
