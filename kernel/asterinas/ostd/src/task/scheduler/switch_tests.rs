// SPDX-License-Identifier: MPL-2.0

use alloc::sync::Arc;
use core::sync::atomic::{AtomicBool, Ordering};

use crate::{
    prelude::*,
    sync::RcuOption,
    task::{Task, TaskOptions},
};

struct ReschedulingDrop {
    entered: Arc<AtomicBool>,
    finished: Arc<AtomicBool>,
}

impl Drop for ReschedulingDrop {
    fn drop(&mut self) {
        assert!(crate::arch::irq::is_local_enabled());
        let physical = Task::current().unwrap();
        super::scheduler_singleton().local_rq_with(&mut |rq| {
            assert!(core::ptr::eq(rq.current().unwrap().as_ref(), &*physical,));
        });
        self.entered.store(true, Ordering::Release);
        // A destructor is permitted to reschedule: it must run before the
        // outer invocation has selected, dequeued or reserved another task.
        Task::yield_now();
        self.finished.store(true, Ordering::Release);
    }
}

#[ktest]
fn rcu_callback_reschedules_before_outer_decision() {
    let entered = Arc::new(AtomicBool::new(false));
    let finished = Arc::new(AtomicBool::new(false));
    let helper_finished = Arc::new(AtomicBool::new(false));
    let helper = Arc::new(
        TaskOptions::new({
            let entered = entered.clone();
            let helper_finished = helper_finished.clone();
            move || {
                while !entered.load(Ordering::Acquire) {
                    Task::yield_now();
                }
                helper_finished.store(true, Ordering::Release);
            }
        })
        .build()
        .unwrap(),
    );
    helper.run();
    let protected = RcuOption::new(Some(Arc::new(ReschedulingDrop {
        entered: entered.clone(),
        finished: finished.clone(),
    })));
    protected.update(None);
    for _ in 0..8 {
        Task::yield_now();
        if finished.load(Ordering::Acquire) && helper_finished.load(Ordering::Acquire) {
            break;
        }
    }
    assert!(finished.load(Ordering::Acquire));
    assert!(helper_finished.load(Ordering::Acquire));
}

#[ktest]
fn live_reader_and_irq_guard_cannot_report_quiescence() {
    assert!(super::can_report_quiescent());
    let protected = RcuOption::new(Some(Arc::new(1u32)));
    let reader = protected.read();
    assert!(!super::can_report_quiescent());
    drop(reader);
    assert!(super::can_report_quiescent());
    let irq = crate::irq::disable_local();
    assert!(protected.read_with(&irq).is_some());
    assert!(!super::can_report_quiescent());
    drop(irq);
    assert!(super::can_report_quiescent());
}

#[ktest]
#[should_panic(expected = "This function might break atomic mode")]
fn reschedule_preparation_rejects_live_rcu_reader() {
    let protected = RcuOption::new(Some(Arc::new(1u32)));
    let reader = protected.read();
    super::prepare_reschedule();
    core::hint::black_box(reader);
}
