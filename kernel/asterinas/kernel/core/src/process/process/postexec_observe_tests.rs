// SPDX-License-Identifier: MPL-2.0

//! Real Process/pidfd lifecycle admission checks. These fixtures do not consume
//! a loader seal, schedule userspace, mint production authority, or claim an
//! observed CPU read. The protection checks use the actual installation helper
//! and real VMAR/TaskSet/ptrace objects. The separate native gate must cover
//! the sealed issuer and actual original-CPU observation boundaries.

use ostd::{prelude::ktest, task::Task};

use super::*;
use crate::{device::misc::test_control_session_recipient, process::test_util};

fn launcher() -> (LaunchBinding, Arc<Task>) {
    let (process, task) = test_util::new_unstarted_process();
    let key = {
        let mut image = process.hepta_image.lock();
        let key = image.prepare_initial().unwrap();
        image.arm_initial_observe_launcher(key).unwrap();
        image.consume_initial(key).unwrap();
        key
    };
    (LaunchBinding::new(process, key), task)
}

fn child_of(parent: &Arc<Process>) -> (Arc<Process>, Arc<Task>) {
    let (child, task) = test_util::new_unstarted_process();
    let mut children = parent.children.lock();
    child.parent.lock().set_process(parent);
    children
        .as_mut()
        .unwrap()
        .insert(child.pid(), child.clone());
    drop(children);
    child.hepta_image.lock().claim_unprepared_run().unwrap();
    (child, task)
}

fn complete_exec(child: &Process) -> ProcessImageKey {
    child.begin_hepta_image_close();
    child.commit_hepta_exec_image().unwrap();
    child.hepta_capspace_session().unwrap()
}

fn admit(
    binding: &LaunchBinding,
    child: &ChildImage,
    recipient: &ControlSessionRecipient,
) -> Result<()> {
    binding.with_recipient(child, binding.nonce, recipient, |_, _, _| Ok(()))
}

fn protect(
    binding: &LaunchBinding,
    child: &ChildImage,
    recipient: &ControlSessionRecipient,
) -> Result<()> {
    binding.with_recipient(child, binding.nonce, recipient, |_, vmar, tasks| {
        commit_external_fences(&child.process, vmar, tasks)
    })
}

#[track_caller]
fn assert_error(result: Result<()>, expected: Errno) {
    assert_eq!(result.unwrap_err().error(), expected);
}

#[ktest]
fn postexec_child_requires_its_original_pidfd_and_live_image() {
    let (binding, _parent_task) = launcher();
    let (child, _child_task) = child_of(&binding.supervisor);
    let key = complete_exec(&child);
    let pidfd = PidFile::new(child.clone(), false);
    let expected = binding.bind_child(&binding.supervisor, &pidfd).unwrap();
    let recipient = test_control_session_recipient(child.clone(), key).unwrap();
    assert!(admit(&binding, &expected, &recipient).is_ok());
    // Identity admission alone installs no slot and grants no usage access.
    assert!(!child.has_initial_observe_authority());
    assert_eq!(
        child.read_hepta_initial_usage(key, 1, 1).unwrap_err(),
        crate::hos2_os_abi::Status::PermissionDenied
    );
}

#[ktest]
fn foreign_caller_and_nonchild_pidfd_cannot_bind_a_launch() {
    let (binding, _parent_task) = launcher();
    let (stranger, _stranger_task) = test_util::new_unstarted_process();
    let (child, _child_task) = child_of(&binding.supervisor);
    complete_exec(&child);
    let pidfd = PidFile::new(child, false);
    assert_eq!(
        binding.bind_child(&stranger, &pidfd).err().unwrap().error(),
        Errno::EPERM
    );
    let foreign_pidfd = PidFile::new(stranger, false);
    assert_eq!(
        binding
            .bind_child(&binding.supervisor, &foreign_pidfd)
            .err()
            .unwrap()
            .error(),
        Errno::EPERM
    );
}

#[ktest]
fn fork_image_before_exec_cannot_receive_a_launch() {
    let (binding, _parent_task) = launcher();
    let (child, _child_task) = child_of(&binding.supervisor);
    let pidfd = PidFile::new(child, false);
    assert_eq!(
        binding
            .bind_child(&binding.supervisor, &pidfd)
            .err()
            .unwrap()
            .error(),
        Errno::ESTALE
    );
}

#[ktest]
fn sibling_control_fd_and_wrong_nonce_cannot_replace_bound_child() {
    let (binding, _parent_task) = launcher();
    let (child, _child_task) = child_of(&binding.supervisor);
    let key = complete_exec(&child);
    let expected = binding
        .bind_child(&binding.supervisor, &PidFile::new(child.clone(), false))
        .unwrap();
    let recipient = test_control_session_recipient(child, key).unwrap();
    let (sibling, _sibling_task) = child_of(&binding.supervisor);
    let sibling_key = complete_exec(&sibling);
    let sibling_fd = test_control_session_recipient(sibling, sibling_key).unwrap();
    assert_error(admit(&binding, &expected, &sibling_fd), Errno::EPERM);
    assert_error(
        binding.with_recipient(&expected, ObserveLaunchNonce(0), &recipient, |_, _, _| {
            Ok(())
        }),
        Errno::EPERM,
    );
}

#[ktest]
fn child_exec_between_pidfd_binding_and_fd_handoff_fences_both_sessions() {
    let (binding, _parent_task) = launcher();
    let (child, _child_task) = child_of(&binding.supervisor);
    let old_key = complete_exec(&child);
    let expected = binding
        .bind_child(&binding.supervisor, &PidFile::new(child.clone(), false))
        .unwrap();
    let old_fd = test_control_session_recipient(child.clone(), old_key).unwrap();
    let new_key = complete_exec(&child);
    let new_fd = test_control_session_recipient(child, new_key).unwrap();
    assert_error(admit(&binding, &expected, &old_fd), Errno::ESTALE);
    assert_error(admit(&binding, &expected, &new_fd), Errno::ESTALE);
}

#[ktest]
fn child_exit_and_supervisor_exec_fail_the_pending_handoff() {
    let (binding, _parent_task) = launcher();
    let (child, _child_task) = child_of(&binding.supervisor);
    let key = complete_exec(&child);
    let expected = binding
        .bind_child(&binding.supervisor, &PidFile::new(child.clone(), false))
        .unwrap();
    let recipient = test_control_session_recipient(child.clone(), key).unwrap();
    child.begin_hepta_image_close();
    assert_error(admit(&binding, &expected, &recipient), Errno::ESTALE);

    let (binding, _parent_task2) = launcher();
    let (child, _child_task2) = child_of(&binding.supervisor);
    let key = complete_exec(&child);
    let expected = binding
        .bind_child(&binding.supervisor, &PidFile::new(child.clone(), false))
        .unwrap();
    let recipient = test_control_session_recipient(child, key).unwrap();
    complete_exec(&binding.supervisor);
    assert_error(admit(&binding, &expected, &recipient), Errno::ESTALE);
}

#[ktest]
fn reparenting_and_a_second_issuer_claim_fail_closed() {
    let (binding, _parent_task) = launcher();
    let (child, _child_task) = child_of(&binding.supervisor);
    let key = complete_exec(&child);
    let expected = binding
        .bind_child(&binding.supervisor, &PidFile::new(child.clone(), false))
        .unwrap();
    let recipient = test_control_session_recipient(child.clone(), key).unwrap();
    let (other_parent, _other_task) = test_util::new_unstarted_process();
    child.parent.lock().set_process(&other_parent);
    assert_error(admit(&binding, &expected, &recipient), Errno::EPERM);
    assert_error(
        binding
            .supervisor
            .hepta_image
            .lock()
            .arm_initial_observe_launcher(binding.supervisor_key),
        Errno::ESTALE,
    );
}

#[ktest]
fn invalid_recipient_never_reaches_the_irreversible_protection_step() {
    let (binding, _parent_task) = launcher();
    let (child, _child_task) = child_of(&binding.supervisor);
    let key = complete_exec(&child);
    let expected = binding
        .bind_child(&binding.supervisor, &PidFile::new(child.clone(), false))
        .unwrap();
    let recipient = test_control_session_recipient(child.clone(), key).unwrap();
    let mut reached_protection = false;
    assert_error(
        binding.with_recipient(
            &expected,
            ObserveLaunchNonce(0),
            &recipient,
            |_, vmar, tasks| {
                reached_protection = true;
                commit_external_fences(&child, vmar, tasks)
            },
        ),
        Errno::EPERM,
    );
    assert!(!reached_protection);
    assert!(!child.external_control_fence().is_fenced());
    assert!(child.lock_vmar().unwrap().enter_external_mutation().is_ok());
}

#[ktest]
fn an_existing_real_tracer_is_rejected_before_either_fence_commits() {
    let (binding, parent_task) = launcher();
    let (child, child_task) = child_of(&binding.supervisor);
    let key = complete_exec(&child);
    let expected = binding
        .bind_child(&binding.supervisor, &PidFile::new(child.clone(), false))
        .unwrap();
    let recipient = test_control_session_recipient(child.clone(), key).unwrap();
    let tracer_thread = parent_task.as_thread().unwrap();
    let tracer = tracer_thread.as_posix_thread().unwrap();
    let tracee_thread = child_task.as_thread().unwrap().clone();
    tracer
        .attach_to(tracer_thread, tracee_thread.clone())
        .unwrap();
    assert_error(protect(&binding, &expected, &recipient), Errno::EPERM);
    assert!(!child.external_control_fence().is_fenced());
    assert!(child.lock_vmar().unwrap().enter_external_mutation().is_ok());
    tracer.clear_tracees();
    protect(&binding, &expected, &recipient).unwrap();
    // An already captured thread reference still reaches the real set_tracer
    // gate. Detaching the former tracer did not grant a replacement bypass.
    assert_eq!(
        tracer
            .attach_to(tracer_thread, tracee_thread)
            .unwrap_err()
            .error(),
        Errno::EPERM
    );
    // Protection alone grants no observer: no fake CPU pin is used by fixtures.
    assert_eq!(
        child.read_hepta_initial_usage(key, 1, 1).unwrap_err(),
        crate::hos2_os_abi::Status::PermissionDenied
    );
}

#[ktest]
fn either_inflight_owner_rejects_installation_without_fencing_the_other() {
    let (binding, _parent_task) = launcher();
    let (child, _child_task) = child_of(&binding.supervisor);
    let key = complete_exec(&child);
    let expected = binding
        .bind_child(&binding.supervisor, &PidFile::new(child.clone(), false))
        .unwrap();
    let recipient = test_control_session_recipient(child.clone(), key).unwrap();
    let vmar = child.vmar.lock().as_ref().unwrap().clone();
    let trace_access = child.external_control_fence().enter().unwrap();
    assert_error(protect(&binding, &expected, &recipient), Errno::EBUSY);
    assert!(!child.external_control_fence().is_fenced());
    assert!(vmar.enter_external_mutation().is_ok());
    drop(trace_access);
    let alien_write = vmar.enter_external_mutation().unwrap();
    assert_error(protect(&binding, &expected, &recipient), Errno::EBUSY);
    assert!(!child.external_control_fence().is_fenced());
    drop(alien_write);
    protect(&binding, &expected, &recipient).unwrap();
    assert!(child.external_control_fence().is_fenced());
    assert_eq!(
        vmar.enter_external_mutation().err().unwrap().error(),
        Errno::EPERM
    );
    // Repeating this exact protection transaction is idempotent. This does
    // not create or extend an observation lease, manage right, or history right.
    protect(&binding, &expected, &recipient).unwrap();
    complete_exec(&child);
    assert_error(protect(&binding, &expected, &recipient), Errno::ESTALE);
    assert!(child.external_control_fence().is_fenced());
}
