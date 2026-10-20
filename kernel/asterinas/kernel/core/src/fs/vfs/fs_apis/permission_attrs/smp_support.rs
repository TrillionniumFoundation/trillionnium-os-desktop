// SPDX-License-Identifier: MPL-2.0

//! Test-only rendezvous for the dedicated two-CPU permission profile.
//!
//! The checked thread may hold a spin lock. Its hook performs only atomic
//! operations and spin_loop: no allocation, logging, blocking wait or scheduler
//! call. A second, separately pinned CPU observes the actual lock with try_lock,
//! then releases this rendezvous before any operation that could wait on it.

use core::sync::atomic::{AtomicBool, AtomicI32, AtomicUsize, Ordering};

use ostd::cpu::CpuId;

use crate::prelude::*;

#[derive(Clone, Copy, PartialEq, Eq)]
pub(in crate::fs) enum CheckpointStage {
    InodeDecision,
    MemfdSealDecision,
}

pub(in crate::fs) struct PermissionCheckpoint {
    stage: CheckpointStage,
    checked: AtomicBool,
    resume: AtomicBool,
    pub entered: AtomicUsize,
    pub checking_cpu: AtomicUsize,
    pub other_cpu: AtomicUsize,
    pub lock_busy: AtomicBool,
    pub first_result: AtomicI32,
    pub second_result: AtomicI32,
}

impl PermissionCheckpoint {
    pub(in crate::fs) fn new(stage: CheckpointStage) -> Self {
        Self {
            stage,
            checked: AtomicBool::new(false),
            resume: AtomicBool::new(false),
            entered: AtomicUsize::new(0),
            checking_cpu: AtomicUsize::new(usize::MAX),
            other_cpu: AtomicUsize::new(usize::MAX),
            lock_busy: AtomicBool::new(false),
            first_result: AtomicI32::new(-999),
            second_result: AtomicI32::new(-999),
        }
    }

    pub(in crate::fs) fn after_check(&self, stage: CheckpointStage) {
        if stage != self.stage {
            return;
        }
        self.checking_cpu
            .store(CpuId::current_racy().as_usize(), Ordering::Release);
        self.entered.fetch_add(1, Ordering::AcqRel);
        self.checked.store(true, Ordering::Release);
        while !self.resume.load(Ordering::Acquire) {
            core::hint::spin_loop();
        }
    }

    pub(in crate::fs) fn wait_checked(&self) {
        while !self.checked.load(Ordering::Acquire) {
            core::hint::spin_loop();
        }
        self.other_cpu
            .store(CpuId::current_racy().as_usize(), Ordering::Release);
    }

    pub(in crate::fs) fn resume(&self) {
        self.resume.store(true, Ordering::Release);
    }

    pub(in crate::fs) fn first_worker(self: &Arc<Self>) -> PermissionWorkerGuard {
        PermissionWorkerGuard {
            checkpoint: self.clone(),
            first: true,
            finished: false,
        }
    }

    pub(in crate::fs) fn second_worker(self: &Arc<Self>) -> PermissionWorkerGuard {
        PermissionWorkerGuard {
            checkpoint: self.clone(),
            first: false,
            finished: false,
        }
    }

    fn finish_first(&self, result: Option<Result<()>>) {
        self.first_result
            .store(result_code(result), Ordering::Release);
        // An unexpected permission error must fail assertions instead of leaving
        // CPU 1 waiting forever. The mandatory entered/CPU checks still reject
        // removal of the real checkpoint or a return before reaching it.
        self.checked.store(true, Ordering::Release);
    }

    fn finish_second(&self, result: Option<Result<()>>) {
        self.second_result
            .store(result_code(result), Ordering::Release);
        self.resume();
    }

    pub(in crate::fs) fn assert_completed(&self) {
        assert_eq!(self.entered.load(Ordering::Acquire), 1);
        assert_eq!(self.checking_cpu.load(Ordering::Acquire), 0);
        assert_eq!(self.other_cpu.load(Ordering::Acquire), 1);
        assert_eq!(self.first_result.load(Ordering::Acquire), 0);
        assert_eq!(self.second_result.load(Ordering::Acquire), 0);
        assert!(self.lock_busy.load(Ordering::Acquire));
    }
}

/// A kernel worker catches an oops before it exits. Ensure unwinding or an
/// unexpected early return cannot strand the other CPU inside its rendezvous.
/// The sentinel remains a hard failure; this never manufactures a successful rc.
pub(in crate::fs) struct PermissionWorkerGuard {
    checkpoint: Arc<PermissionCheckpoint>,
    first: bool,
    finished: bool,
}

impl PermissionWorkerGuard {
    pub(in crate::fs) fn finish(mut self, result: Option<Result<()>>) {
        if self.first {
            self.checkpoint.finish_first(result);
        } else {
            self.checkpoint.finish_second(result);
        }
        self.finished = true;
    }
}

impl Drop for PermissionWorkerGuard {
    fn drop(&mut self) {
        if self.finished {
            return;
        }
        let result = if self.first {
            &self.checkpoint.first_result
        } else {
            &self.checkpoint.second_result
        };
        result.store(-998, Ordering::Release);
        self.checkpoint.checked.store(true, Ordering::Release);
        self.checkpoint.resume();
    }
}

fn result_code(result: Option<Result<()>>) -> i32 {
    match result {
        Some(Ok(())) => 0,
        Some(Err(error)) => error.error() as i32,
        None => -1,
    }
}
