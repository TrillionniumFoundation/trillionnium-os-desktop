// SPDX-License-Identifier: MPL-2.0

//! Original Process allocations and the production first-run/image state.
//! These never schedule fixture user contexts. Native tests separately prove
//! actual pidfd events, consuming wait, frozen ELF startup and writer recovery.

use ostd::prelude::ktest;

use super::*;
use crate::process::test_util;

fn prepared() -> PreparedInitialProcess {
    let (process, task) = test_util::new_unstarted_process();
    let vmar = process.vmar.lock().as_ref().unwrap().clone();
    PreparedInitialProcess::new(process, vmar, task).unwrap()
}

#[ktest]
fn native_successor_claim_failure_closes_all_unpublished_images() {
    let first = prepared();
    let second = prepared();
    let first_process = first.process.clone();
    let second_process = second.process.clone();
    let keys = [first.key, second.key];
    let mut pending = PendingLaunch::new();
    pending.push(first);
    pending.push(second);
    // Inject failure at the second original claim, after the first claim
    // succeeds. Neither allocation has entered the parent or PID table.
    second_process.begin_hepta_image_close();
    assert_eq!(pending.claim_all().unwrap_err().error(), Errno::ESTALE);
    assert!(!pending.published);
    assert!(
        pid_table::pid_table_mut()
            .get_process(first_process.pid())
            .is_none()
    );
    assert!(
        pid_table::pid_table_mut()
            .get_process(second_process.pid())
            .is_none()
    );
    drop(pending);
    for (process, key) in [first_process, second_process].iter().zip(keys) {
        assert_eq!(
            process
                .check_hepta_capspace_session(key)
                .unwrap_err()
                .error(),
            Errno::ESTALE
        );
        assert_eq!(
            process.hepta_capspace_session().unwrap_err().error(),
            Errno::ESTALE
        );
    }
}

#[ktest]
fn native_successor_cancelled_token_cannot_close_a_newer_image() {
    let first = prepared();
    let process = first.process.clone();
    let key = first.key;
    let mut pending = PendingLaunch::new();
    pending.push(first);
    pending.claim_all().unwrap();
    process.begin_hepta_image_close();
    process.commit_hepta_exec_image().unwrap();
    let replacement = process.hepta_capspace_session().unwrap();
    assert_ne!(key, replacement);
    drop(pending);
    assert_eq!(process.hepta_capspace_session().unwrap(), replacement);
}

#[ktest]
fn native_successor_reap_gate_requires_release_of_the_actual_child_allocation() {
    let (child, child_task) = test_util::new_unstarted_process();
    let parent = test_util::UnstartedParent::new(&child);
    let children = [Some(Arc::downgrade(&child)), None];
    assert!(!children_reaped(&children));
    test_util::mark_zombie(&child);
    assert!(!children_reaped(&children));
    drop(child);
    drop(child_task);
    // Exit alone did not release the original parent's ownership. This is
    // the same strong pin removed by the original consuming wait path.
    assert!(!children_reaped(&children));
    parent.detach_zombie_child();
    assert!(children_reaped(&children));
}

#[ktest]
fn native_successor_generation_replays_only_the_last_successful_transaction() {
    let request = |expected| LaunchRequest {
        command: LaunchCommand::Advance,
        expected,
    };
    assert_eq!(request(0).next_generation(0).unwrap(), Some(1));
    assert_eq!(request(0).next_generation(1).unwrap(), None);
    assert_eq!(request(1).next_generation(1).unwrap(), Some(2));
    assert_eq!(request(1).next_generation(2).unwrap(), None);
    assert_eq!(
        request(0).next_generation(2).unwrap_err().error(),
        Errno::ESTALE
    );
    assert_eq!(
        request(3).next_generation(2).unwrap_err().error(),
        Errno::ESTALE
    );
    assert_eq!(
        request(u64::MAX)
            .next_generation(u64::MAX)
            .unwrap_err()
            .error(),
        Errno::EOVERFLOW
    );
    assert_eq!(
        request(u64::MAX - 1).next_generation(u64::MAX).unwrap(),
        None
    );
    let mut saved = SavedLaunchRetirement::policy(2, [[2; 16], [3; 16]], 0, None, None);
    let original = saved.read(2).unwrap();
    assert_eq!(saved.require_saved().unwrap_err().error(), Errno::EBUSY);
    assert_eq!(saved.acknowledge(1).unwrap_err().error(), Errno::ESTALE);
    assert_eq!(saved.acknowledge(3).unwrap_err().error(), Errno::ESTALE);
    assert_eq!(saved.require_saved().unwrap_err().error(), Errno::EBUSY);
    // Read/copyout retry is immutable and does not imply persistence/ACK.
    assert_eq!(saved.read(2).unwrap(), original);
    assert_eq!(saved.require_saved().unwrap_err().error(), Errno::EBUSY);
    saved.acknowledge(2).unwrap();
    saved.acknowledge(2).unwrap();
    saved.require_saved().unwrap();
    assert_eq!(saved.read(2).unwrap(), original);
    assert_eq!(saved.read(1).unwrap_err().error(), Errno::ESTALE);
    assert_eq!(
        u64::from_le_bytes(original[120..128].try_into().unwrap()),
        1
    );
    let no_cut = SavedLaunchRetirement::history_only(3, [[2; 16], [3; 16]])
        .read(3)
        .unwrap();
    assert_eq!(u64::from_le_bytes(no_cut[120..128].try_into().unwrap()), 0);
    // Some(0) and unavailable time are kept distinct without inventing time.
    let time_zero = SavedLaunchRetirement::policy(4, [[2; 16], [3; 16]], 2, Some(0), None)
        .read(4)
        .unwrap();
    assert_eq!(
        u64::from_le_bytes(time_zero[120..128].try_into().unwrap()),
        3
    );

    let mut bytes = [0u8; 128];
    bytes[..8].copy_from_slice(b"HOS2LAUN");
    bytes[8..16].copy_from_slice(&1u64.to_le_bytes());
    assert_eq!(
        LaunchRequest::decode(&bytes).unwrap().command,
        LaunchCommand::Query
    );
    bytes[32] = 1;
    assert_eq!(
        LaunchRequest::decode(&bytes).err().unwrap().error(),
        Errno::EINVAL
    );
    bytes[32] = 0;
    bytes[24] = 1;
    assert_eq!(
        LaunchRequest::decode(&bytes).err().unwrap().error(),
        Errno::EINVAL
    );
}

#[ktest]
fn native_successor_history_page_has_fresh_local_space_and_no_effect_handles() {
    let receipt = LaunchReceipt {
        generation: 9,
        root: 1,
        workload: 3,
        manager: 0,
        recovery: 0,
        history_only: 17,
        spaces: [[2; 16], [4; 16]],
    };
    let local = [9; 16];
    let page = successor_page(HISTORY_ROLE, receipt, 17, local);
    let word = |offset| u64::from_le_bytes(page[offset..offset + 8].try_into().unwrap());
    assert_eq!((word(8), word(16), word(24)), (4, 5, 240));
    for offset in [32, 40, 48, 56, 168, 184, 232] {
        assert_eq!(word(offset), 0);
    }
    assert_eq!((word(64), word(72), word(80), word(88)), (3, 1, 4, 1));
    assert_eq!(&page[112..128], &receipt.spaces[0]);
    assert_eq!(&page[128..144], &receipt.spaces[1]);
    assert_eq!(&page[208..224], &local);
    assert_eq!((word(192), word(200), word(224)), (1, 17, 9));
    assert!(page[240..].iter().all(|byte| *byte == 0));
    let reply = receipt.encode();
    assert_eq!(&reply[..8], b"HOS2LRES");
    assert_eq!(u64::from_le_bytes(reply[16..24].try_into().unwrap()), 2);
    assert_eq!(u64::from_le_bytes(reply[64..72].try_into().unwrap()), 17);
    assert!(reply[112..].iter().all(|byte| *byte == 0));
}

#[ktest]
fn native_successor_launcher_refuses_ordinary_marker_only_and_ended_images() {
    let (process, _task) = test_util::new_unstarted_process();
    let key = process.hepta_capspace_session().unwrap();
    let mut query = [0u8; 128];
    query[..8].copy_from_slice(b"HOS2LAUN");
    query[8..16].copy_from_slice(&1u64.to_le_bytes());
    assert_eq!(
        process
            .dispatch_hepta_launcher(key, &query)
            .unwrap_err()
            .error(),
        Errno::EPERM
    );
    process.hepta_image.lock().prepare_initial().unwrap();
    process
        .hepta_image
        .lock()
        .activate_initial_root(key)
        .unwrap();
    // The image-mutation protection marker is not itself launcher authority.
    assert_eq!(
        process
            .dispatch_hepta_launcher(key, &query)
            .unwrap_err()
            .error(),
        Errno::EPERM
    );
    process.begin_hepta_image_close();
    assert_eq!(
        process
            .dispatch_hepta_launcher(key, &query)
            .unwrap_err()
            .error(),
        Errno::ESTALE
    );
    process.commit_hepta_exec_image().unwrap();
    let fresh = process.hepta_capspace_session().unwrap();
    assert_ne!(key, fresh);
    assert_eq!(
        process
            .dispatch_hepta_launcher(fresh, &query)
            .unwrap_err()
            .error(),
        Errno::EPERM
    );
}

#[ktest]
fn native_successor_image_allocation_failure_never_publishes_a_process() {
    let (seed, seed_task) = test_util::new_unstarted_process();
    let path = seed
        .vmar
        .lock()
        .as_ref()
        .unwrap()
        .process_vm()
        .executable_path()
        .clone();
    drop(seed);
    drop(seed_task);
    let (process, vmar) = allocate_initial_process_with_owner(
        &path,
        new_resource_limits_for_init(),
        Some(crate::vm::user_memory::UserMemoryAccount::new(0)),
    );
    let weak = Arc::downgrade(&process);
    let snapshot = TrustedInitialSnapshot::frozen_manifest_for_ktest();
    let result = snapshot.load(
        vmar.clone_arc(),
        vec![CString::new("native-successor").unwrap()],
        Vec::new(),
        Box::new([0; PAGE_SIZE]),
    );
    assert_eq!(result.err().unwrap().error(), Errno::ENOMEM);
    assert_eq!(vmar.clone_arc().get_mappings_total_size(), 0);
    assert!(
        pid_table::pid_table_mut()
            .get_process(process.pid())
            .is_none()
    );
    drop(vmar);
    drop(process);
    assert!(weak.upgrade().is_none());
}
