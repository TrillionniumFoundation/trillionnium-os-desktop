// SPDX-License-Identifier: MPL-2.0

use core::sync::atomic::{AtomicU16, Ordering};

use ostd::{
    cpu::{CpuId, num_cpus},
    prelude::ktest,
};

use super::*;
use crate::{
    fs::vfs::permission_attrs::{
        PermissionAttrOp,
        smp_support::{CheckpointStage, PermissionCheckpoint},
    },
    process::credentials::capabilities::CapSet,
    thread::kernel_thread::ThreadOptions,
    time::clocks,
};

#[ktest]
fn permission_attr_smp() {
    assert_eq!(
        num_cpus(),
        2,
        "permission SMP tests require exactly two CPUs"
    );
    crate::thread::init();
    clocks::init_for_ktest();
    let file = Arc::new(
        InodeHandle::new_memfd("permission-smp".to_string(), MemfdFlags::MFD_ALLOW_SEALING)
            .unwrap(),
    );
    assert!(memfd_inode_or_err(&file).is_ok());
    let path = file.path();
    let inode = path.inode();
    inode
        .set_mode(path.dentry(), InodeMode::from_bits_truncate(0o666))
        .unwrap();
    assert!(!file.get_seals().unwrap().contains(FileSeals::F_SEAL_EXEC));
    let metadata = inode.metadata().unwrap();
    let checkpoint = Arc::new(PermissionCheckpoint::new(CheckpointStage::MemfdSealDecision));
    let sealed_mode = Arc::new(AtomicU16::new(0));
    let request = PermissionAttrRequest::for_test(
        PermissionAttrOp::Chmod(InodeMode::from_bits_truncate(0o777)),
        metadata.uid,
        metadata.gid,
        BTreeSet::new(),
        CapSet::empty(),
    )
    .with_checkpoint(checkpoint.clone());

    let second_file = file.clone();
    let second_checkpoint = checkpoint.clone();
    let second_sealed_mode = sealed_mode.clone();
    let second = ThreadOptions::new(move || {
        let worker = second_checkpoint.second_worker();
        second_checkpoint.wait_checked();
        let inode = memfd_inode_or_err(&second_file).unwrap();
        let lock_busy = match inode.seals.try_lock() {
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
            second_checkpoint.resume();
        }
        let result = second_file.add_seals(FileSeals::F_SEAL_EXEC);
        second_sealed_mode.store(inode.mode().unwrap().bits(), Ordering::Release);
        worker.finish(Some(result));
    })
    .cpu_affinity(CpuId::new(1).into())
    .spawn();

    let first_file = file.clone();
    let first_checkpoint = checkpoint.clone();
    let first = ThreadOptions::new(move || {
        let worker = first_checkpoint.first_worker();
        let dentry = first_file.path().dentry();
        let result = dentry
            .inode()
            .try_permission_attr_transaction(dentry, &request);
        worker.finish(result);
    })
    .cpu_affinity(CpuId::new(0).into())
    .spawn();
    first.join();
    second.join();

    let after = file.path().inode().metadata().unwrap();
    let sealed_mode = sealed_mode.load(Ordering::Acquire);
    let seals = file.get_seals().unwrap();
    ostd::early_println!(
        "\nPERMISSION_SMP_OBSERVATION case=memfd_seal cpu_a={} cpu_b={} entered={} lock_busy={} a_rc={} b_rc={} mode={:o} sealed_mode={:o} seal_exec={}",
        checkpoint.checking_cpu.load(Ordering::Acquire),
        checkpoint.other_cpu.load(Ordering::Acquire),
        checkpoint.entered.load(Ordering::Acquire),
        checkpoint.lock_busy.load(Ordering::Acquire),
        checkpoint.first_result.load(Ordering::Acquire),
        checkpoint.second_result.load(Ordering::Acquire),
        after.mode.bits(),
        sealed_mode,
        seals.contains(FileSeals::F_SEAL_EXEC),
    );
    assert_eq!(
        after.mode.bits(),
        sealed_mode,
        "executable bits changed after sealing"
    );
    assert_eq!(after.mode.bits(), 0o777);
    assert!(seals.contains(FileSeals::F_SEAL_EXEC));
    checkpoint.assert_completed();
}
