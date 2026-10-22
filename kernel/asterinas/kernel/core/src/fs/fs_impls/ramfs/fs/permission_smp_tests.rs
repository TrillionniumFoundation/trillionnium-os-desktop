// SPDX-License-Identifier: MPL-2.0

use core::sync::atomic::Ordering;

use ostd::{
    cpu::{CpuId, num_cpus},
    prelude::ktest,
};

use super::{
    permission_tests::{new_aliases, request},
    *,
};
use crate::{
    fs::vfs::permission_attrs::{
        PermissionAttrOp,
        smp_support::{CheckpointStage, PermissionCheckpoint},
    },
    process::credentials::capabilities::CapSet,
    thread::kernel_thread::ThreadOptions,
};

fn run_alias_race(
    name: &str,
    initial_mode: u16,
    first_op: PermissionAttrOp,
    second_op: PermissionAttrOp,
    expected_uid: u32,
    expected_mode: u16,
) {
    // This function is absent from the normal 1-CPU suite. The dedicated gate
    // must fail, without entering a rendezvous, if its actual profile is wrong.
    assert_eq!(
        num_cpus(),
        2,
        "permission SMP tests require exactly two CPUs"
    );
    crate::thread::init();
    let (_fs, original, alias) = new_aliases(InodeMode::from_bits_truncate(initial_mode));
    assert!(original.inode().downcast_ref::<RamInode>().is_some());
    assert!(alias.inode().downcast_ref::<RamInode>().is_some());
    let checkpoint = Arc::new(PermissionCheckpoint::new(CheckpointStage::InodeDecision));
    let first_request =
        request(first_op, 1000, CapSet::empty()).with_checkpoint(checkpoint.clone());
    let second_request = request(second_op, 1000, CapSet::CHOWN | CapSet::FOWNER);

    let second_checkpoint = checkpoint.clone();
    let other_alias = alias.clone();
    let second = ThreadOptions::new(move || {
        let worker = second_checkpoint.second_worker();
        second_checkpoint.wait_checked();
        let inode = other_alias.inode().downcast_ref::<RamInode>().unwrap();
        let lock_busy = match inode.metadata.try_lock() {
            Some(guard) => {
                drop(guard);
                false
            }
            None => true,
        };
        second_checkpoint
            .lock_busy
            .store(lock_busy, Ordering::Release);
        if lock_busy {
            // The real owner lock is held: let CPU 0 commit before blocking on it.
            second_checkpoint.resume();
        }
        let result = other_alias
            .inode()
            .try_permission_attr_transaction(&other_alias, &second_request);
        // Under the frozen split-lock defect, the real second operation commits
        // before CPU 0 resumes and tries to apply its now-stale decision.
        worker.finish(result);
    })
    .cpu_affinity(CpuId::new(1).into())
    .spawn();

    let first_checkpoint = checkpoint.clone();
    let first_alias = original.clone();
    let first = ThreadOptions::new(move || {
        let worker = first_checkpoint.first_worker();
        let result = first_alias
            .inode()
            .try_permission_attr_transaction(&first_alias, &first_request);
        worker.finish(result);
    })
    .cpu_affinity(CpuId::new(0).into())
    .spawn();
    first.join();
    second.join();

    let after = original.inode().metadata().unwrap();
    let through_alias = alias.inode().metadata().unwrap();
    ostd::early_println!(
        "\nPERMISSION_SMP_OBSERVATION case={} cpu_a={} cpu_b={} entered={} lock_busy={} a_rc={} b_rc={} uid={} mode={:o} alias_uid={} alias_mode={:o}",
        name,
        checkpoint.checking_cpu.load(Ordering::Acquire),
        checkpoint.other_cpu.load(Ordering::Acquire),
        checkpoint.entered.load(Ordering::Acquire),
        checkpoint.lock_busy.load(Ordering::Acquire),
        checkpoint.first_result.load(Ordering::Acquire),
        checkpoint.second_result.load(Ordering::Acquire),
        u32::from(after.uid),
        after.mode.bits(),
        u32::from(through_alias.uid),
        through_alias.mode.bits(),
    );
    // Check the forbidden outcome before lock-observation assertions so the old
    // behavior is rejected for an actual incorrect metadata result.
    assert_eq!(
        after.mode.bits(),
        expected_mode,
        "stale permission decision changed final mode"
    );
    assert_eq!(after.uid, Uid::new(expected_uid));
    assert_eq!(through_alias.mode, after.mode);
    assert_eq!(through_alias.uid, after.uid);
    checkpoint.assert_completed();
}

mod owner_alias {
    use super::*;

    #[ktest]
    fn permission_attr_smp() {
        run_alias_race(
            "owner_alias",
            0o755,
            PermissionAttrOp::Chmod(InodeMode::from_bits_truncate(0o4755)),
            PermissionAttrOp::Chown {
                uid: Some(Uid::new(1002)),
                gid: None,
            },
            1002,
            0o755,
        );
    }
}

mod clear_setid_alias {
    use super::*;

    #[ktest]
    fn permission_attr_smp() {
        run_alias_race(
            "clear_setid_alias",
            0o4755,
            PermissionAttrOp::ClearSetIdBits,
            PermissionAttrOp::Chmod(InodeMode::from_bits_truncate(0o600)),
            1000,
            0o600,
        );
    }
}
