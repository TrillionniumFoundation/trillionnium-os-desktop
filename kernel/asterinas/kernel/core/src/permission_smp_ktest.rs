// SPDX-License-Identifier: MPL-2.0

//! Bootstrap for the dedicated two-CPU permission kernel tests.
//!
//! OSDK's ordinary runner uses bare tasks and a BSP-only FIFO scheduler. This
//! entry runs before its first task and supplies the production class scheduler
//! and real kernel threads, while retaining OSDK's test selection and verdicts.

use ostd::{
    cpu::{CpuId, num_cpus},
    task::{self, Task},
};

use crate::{
    sched::{self, SchedPolicy},
    thread::{self, Thread, kernel_thread::ThreadOptions},
    time::clocks,
};

/// Boots the fixed SMP test profile before any task is created.
///
/// `run_tests_fn` must be the original OSDK test-suite and power-off entry.
pub fn boot(run_tests_fn: fn() -> !) {
    assert!(Task::current().is_none(), "SMP test boot requires bootstrap context");
    assert_eq!(num_cpus(), 2, "permission SMP tests require exactly two CPUs");
    assert_eq!(CpuId::current_racy(), CpuId::bsp());

    thread::init();
    clocks::init_for_ktest();
    sched::init();
    sched::init_on_each_cpu();
    ostd::boot::smp::register_ap_entry(ap_entry);

    // Enqueuing the first class-scheduled task can leave bootstrap immediately.
    // As in the production boot path, start the non-idle task from the BSP idle
    // thread instead of relying on code after the first spawn to run.
    ThreadOptions::new(move || {
        ThreadOptions::new(move || {
            assert!(Thread::current().is_some());
            assert_eq!(CpuId::current_racy(), CpuId::bsp());
            ostd::early_println!(
                "\nPERMISSION_SMP_BOOTSTRAP scheduler=class runner_cpu=0 runner_thread=true"
            );
            run_tests_fn();
        })
        .cpu_affinity(CpuId::bsp().into())
        .spawn();

        idle_loop();
    })
    .cpu_affinity(CpuId::bsp().into())
    .sched_policy(SchedPolicy::Idle)
    .spawn();
}

fn ap_entry() {
    assert_eq!(CpuId::current_racy(), CpuId::new(1));
    // The coarse metadata clock is CPU-local; initialize the AP's slot too.
    clocks::init_for_ktest();
    sched::init_on_each_cpu();
    ThreadOptions::new(idle_loop)
        .cpu_affinity(CpuId::current_racy().into())
        .sched_policy(SchedPolicy::Idle)
        .spawn();
}

fn idle_loop() {
    assert!(Thread::current().is_some());
    loop {
        task::halt_cpu();
    }
}
