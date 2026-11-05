// SPDX-License-Identifier: MPL-2.0

//! Bounded, read-only lifecycle samples for the exact original-owner experiment.
//!
//! This module is absent from legacy profiles. No allocator hot path, budget,
//! reserve, or recovery authority changes. Free/slab counters are approximate;
//! their minimum over these finite observations is not a continuous guest peak.

use core::sync::atomic::{AtomicUsize, Ordering};

use crate::{prelude::*, process::Process};

const MAX_SAMPLES: usize = 64;
static SAMPLES: AtomicUsize = AtomicUsize::new(0);
static MIN_FREE: AtomicUsize = AtomicUsize::new(usize::MAX);

pub(super) fn system(stage: &'static str, generation: u64) {
    emit(stage, generation, "none", 0, None);
}

pub(super) fn role(stage: &'static str, generation: u64, role: &'static str, process: &Process) {
    emit(stage, generation, role, process.pid(), Some(process));
}

fn emit(
    stage: &'static str,
    generation: u64,
    role: &'static str,
    pid: u32,
    process: Option<&Process>,
) {
    // Initial preparation precedes scheduling; subsequent calls are serialized
    // by the original launcher's sleeping gate. No CPU/image/VMAR spinlock is
    // acquired here, and these diagnostic atomics never govern admission.
    let Ok(previous) = SAMPLES.fetch_update(Ordering::Relaxed, Ordering::Relaxed, |count| {
        count.checked_add(1).filter(|next| *next <= MAX_SAMPLES)
    }) else {
        return;
    };
    let free = osdk_frame_allocator::load_total_free_size();
    let minimum = MIN_FREE.fetch_min(free, Ordering::Relaxed).min(free);
    let slab = crate::vm::mem_slab();
    let account = process.and_then(|process| process.user_memory_owner().as_ref());
    let (present, pages, limit) = match account {
        Some(account) => (true, account.current_pages(), account.limit_pages()),
        None => (false, 0, 0),
    };
    println!(
        "[hepta-g2-memory] schema=1 sample={} stage={} generation={} role={} pid={} ordinary_free_bytes={} sampled_min_free_bytes={} slab_backing_bytes={} account_present={} selected_user_pages={} selected_user_limit_pages={} complete_peak=false global_memory_reserve=false",
        previous + 1,
        stage,
        generation,
        role,
        pid,
        free,
        minimum,
        slab,
        present,
        pages,
        limit
    );
}
