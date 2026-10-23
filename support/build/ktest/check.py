#!/usr/bin/env python3
"""Verify target-crate ktest summaries and raw guest exit evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
HEAD = re.compile(r'^running (\d+) tests in crate "([^"]+)"$', re.MULTILINE)
SUMMARY = re.compile(r'test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) filtered out\.')
PERMISSION_TESTS = {
    "aster_core::fs::fs_impls::ramfs::fs::permission_tests::permission_rejection_has_no_partial_update",
    "aster_core::fs::fs_impls::ramfs::fs::permission_tests::permission_noop_chown_updates_ctime",
    "aster_core::fs::fs_impls::ramfs::fs::permission_tests::permission_alias_observes_new_owner",
    "aster_core::fs::fs_impls::ext2::inode::attrs::permission_tests::permission_ext2_reject_then_commit",
    "aster_core::fs::fs_impls::ramfs::memfd::permission_tests::permission_memfd_exec_seal_preserves_attributes_on_error",
}

# The default core gate keeps its 239-test baseline, five permission tests,
# all twenty-one G1-c/G1-d regressions, two ExFAT tests and three ext2
# durability regressions, five initial-readonly atime/sync regressions, six
# physical user-frame regressions, two stopped-stack, three timestamp and six
# independent watchdog owner/lifecycle regressions, plus three fatal-cleanup
# regressions. Existing required names are never replaced by these additions.
# Filtered runs retain explicit opt-in; they cannot stand in for a complete
# core qualification.
MINIMUM_CORE_TESTS = 316  # Retained 303 plus ten memory and three boot-identity regressions.
TRUSTED_PROFILE_CORE_TESTS = (
    "aster_core::vm::vmar::vmar_impls::initial_image::tests::initial_image_seal_preserves_bytes_across_mapping_replacement_attempts",
    "aster_core::vm::vmar::vmar_impls::initial_image::tests::initial_image_seal_allows_relro_but_never_readds_permissions",
    "aster_core::vm::vmar::vmar_impls::initial_image::tests::initial_image_seal_rechecks_alien_write_using_an_earlier_vmar_pin",
    "aster_core::vm::vmar::vmar_impls::initial_image::tests::initial_image_seal_does_not_turn_fork_into_a_shared_writable_alias",
    "aster_core::process::process::image::tests::initial_observe_lease_includes_issue_and_excludes_expiry",
    "aster_core::process::process::image::tests::initial_observe_lease_does_not_accept_a_pre_issue_clock_cut",
    "aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::usage_tests::initial_observer_pin_rejects_a_replaced_real_cpu_owner",
    "aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::usage_tests::initial_observer_pin_does_not_keep_a_deleted_resource_authorized",
    "aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::usage_tests::initial_owner_lease_check_rejects_before_sampling",
    "aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::trusted_control::tests::native_budget_enforces_sub_microsecond_caps_on_the_original_owner",
    "aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::trusted_control::tests::native_budget_update_and_replay_preserve_consumption_and_positive_debt",
    "aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::trusted_control::tests::native_manager_revocation_preserves_recovery_and_saved_history",
    "aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::trusted_control::tests::native_recovery_expiry_is_finite_single_use_and_replays_original_receipt",
    "aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::trusted_control::tests::native_recovery_never_infers_resume_from_zero_or_unowned_budget",
    "aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::trusted_control::tests::native_recovery_first_close_cut_is_not_renewed_and_missing_clock_fences",
    "aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::trusted_control::tests::native_recovery_refuses_expired_final_cut_and_preserves_accounting_fault",
    "aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::trusted_control::tests::native_management_lease_edges_and_clock_absence_do_not_change_budget",
    "aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::trusted_control::tests::native_ceiling_and_revision_rejections_are_immutable_without_effect",
    "aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::trusted_control::tests::native_accounting_fault_cannot_publish_a_successful_budget_receipt",
    "aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::trusted_control::tests::native_controlled_leaf_refuses_linux_configuration_and_membership_aliases",
    "aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::trusted_control::tests::native_bounded_history_retirement_never_reexecutes_an_old_cpu_delivery",
)
EXFAT_CORE_TESTS = (
    "aster_core::fs::fs_impls::exfat::inode::permission_mode_tests::exfat_modes_never_invent_setid_or_sticky",
    "aster_core::fs::fs_impls::exfat::inode::permission_mode_tests::exfat_modes_keep_file_directory_masks_and_readonly",
)
EXT2_DURABILITY_TESTS = (
    "aster_core::fs::fs_impls::ext2::fs::test::inode_sync_preserves_allocation_and_data_across_remount",
    "aster_core::fs::fs_impls::ext2::fs::test::allocation_sync_rechecks_an_earlier_snapshot_under_the_same_owner",
    "aster_core::fs::fs_impls::ext2::fs::test::allocation_sync_retries_all_dirty_metadata_after_write_failure",
)
EXT2_READONLY_ATIME_TESTS = (
    "aster_core::fs::fs_impls::ext2::inode::attrs::readonly_atime_tests::readonly_buffered_read_keeps_atime_without_writes",
    "aster_core::fs::fs_impls::ext2::inode::attrs::readonly_atime_tests::readonly_direct_read_keeps_atime_without_writes",
    "aster_core::fs::fs_impls::ext2::inode::attrs::readonly_atime_tests::readonly_readdir_keeps_atime_without_writes",
    "aster_core::fs::fs_impls::ext2::inode::attrs::readonly_atime_tests::writable_reads_persist_atime",
    "aster_core::fs::fs_impls::ext2::inode::attrs::readonly_atime_tests::readonly_flag_does_not_discard_preexisting_dirty_data",
)
USER_MEMORY_CORE_TESTS = (
    "aster_core::vm::user_memory::tests::exact_limit_and_unconsumed_reservation_refund",
    "aster_core::vm::user_memory::tests::shared_frame_charges_once_until_last_reference",
    "aster_core::vm::user_memory::tests::independent_owners_do_not_consume_each_others_allowance",
    "aster_core::vm::page_cache::vmo::options::test::contiguous_limit_is_admitted_before_any_page",
    "aster_core::vm::page_cache::vmo::options::test::shared_vmo_aliases_keep_one_physical_charge",
    "aster_core::vm::vmar::vm_mapping::user_memory_tests::cow_charges_the_copy_and_refunds_each_physical_page",
    "aster_core::process::process_vm::init_stack::tests::stopped_initial_stack_charges_its_destination_without_a_current_process",
    "aster_core::process::process_vm::init_stack::tests::rejected_stopped_initial_stack_refunds_its_pages_when_the_image_is_dropped",
)
WATCHDOG_CORE_TESTS = (
    "aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::trusted_control::tests::native_watchdog_first_close_deadline_restores_once_with_original_receipt",
    "aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::trusted_control::tests::native_watchdog_preserves_zero_job_stop_and_recovery_owned_budgets",
    "aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::trusted_control::tests::native_watchdog_expiry_clock_fault_and_late_tick_fail_closed",
    "aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::trusted_control::tests::native_watchdog_fenced_or_bad_accounting_never_restores",
    "aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::trusted_control::tests::native_watchdog_observes_original_status_without_retaining_process",
    "aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::trusted_control::tests::native_watchdog_poll_admission_never_settles_or_changes_budget",
)
TIMESTAMP_CORE_TESTS = (
    "aster_core::fs::fs_impls::ramfs::fs::permission_tests::utimes_checks_current_owner_through_alias_without_partial_update",
    "aster_core::fs::fs_impls::ramfs::fs::permission_tests::utimes_omit_preserves_newer_alias_timestamp",
    "aster_core::fs::fs_impls::ext2::inode::attrs::permission_tests::utimes_ext2_denial_is_unchanged_and_success_is_persistent",
)
FATAL_CLEANUP_CORE_TESTS = tuple(
    "aster_core::fs::fs_impls::cgroupfs::controller::cpu::scheduler_handoff_regressions::" + suffix
    for suffix in (
        "zero_quota_thread_sigkill_resumes_only_fatal_cleanup_with_original_debit",
        "zero_quota_process_sigkill_resumes_only_fatal_cleanup_with_original_debit",
        "fatal_receipts_follow_original_signal_queues_without_constructor_inheritance",
    )
)
IPC_FRAME_CORE_TESTS = (
    "aster_core::util::ring_buffer::test::ipc_buffer_charges_original_pages_until_last_segment_alias",
    "aster_core::util::ring_buffer::test::ipc_buffer_rejected_layout_and_allocator_failure_refund_owner",
    "aster_core::fs::pipe::common::test::pipe_production_capacity_uses_current_family_and_refunds_last_endpoint",
    "aster_core::fs::pipe::common::test::fifo_shared_opens_keep_first_owner_without_double_charge",
    "aster_core::fs::pipe::common::test::pipe_denial_publishes_no_object_or_open_counts",
    "aster_core::net::socket::unix::stream::connected::memory_tests::unix_pair_admits_both_directions_or_refunds_the_first",
    "aster_core::net::socket::unix::stream::init::memory_tests::denied_connection_keeps_original_bound_and_shutdown_state",
    "aster_core::net::socket::unix::stream::socket::memory_tests::unix_socketpair_denial_preserves_current_family_without_endpoints",
)
HIERARCHICAL_MEMORY_CORE_TESTS = (
    "aster_core::fs::pipe::common::test::pipe_and_fifo_backing_obey_hierarchical_limit_with_unlimited_family",
    *tuple("aster_core::vm::user_memory::hierarchy::tests::" + suffix for suffix in (
        "hierarchical_frame_admission_refunds_family_and_every_ancestor_once",
        "disabled_domains_keep_live_charges_and_deleted_identity_cannot_escape",
        "physical_allocator_error_rolls_back_complete_hierarchical_precharge",
        "concurrent_sibling_allocators_cannot_both_cross_ancestor_limit",
        "explicit_vmar_fault_owner_overrides_loader_fallback_without_recharging_shared_pages",
        "unix_stream_and_seqpacket_partial_buffer_admission_refund_ancestor",
    )),
    *tuple("aster_core::fs::fs_impls::cgroupfs::controller::memory::tests::" + suffix for suffix in (
        "memory_files_round_bytes_reject_lowering_and_bound_depth_before_publication",
        "migration_changes_only_future_allocations_and_failed_target_preserves_membership",
        "fork_has_independent_binding_and_clone_vm_processes_cannot_split_membership",
    )),
)
BOOT_ID_CORE_TESTS = (
    "aster_core::util::boot_identity::tests::boot_identity_is_stable_and_has_uuid_v4_layout",
    "aster_core::fs::fs_impls::procfs::sys::kernel::random::tests::proc_boot_id_partial_reads_preserve_the_same_uuid",
    "aster_core::fs::fs_impls::procfs::sys::kernel::random::tests::proc_boot_id_rejects_mutation",
)
REQUIRED_CORE_TESTS = (*HIERARCHICAL_MEMORY_CORE_TESTS, *BOOT_ID_CORE_TESTS, *IPC_FRAME_CORE_TESTS, *FATAL_CLEANUP_CORE_TESTS, *sorted(PERMISSION_TESTS), *TRUSTED_PROFILE_CORE_TESTS, *EXFAT_CORE_TESTS,
                       *EXT2_DURABILITY_TESTS, *EXT2_READONLY_ATIME_TESTS,
                       *USER_MEMORY_CORE_TESTS, *TIMESTAMP_CORE_TESTS, *WATCHDOG_CORE_TESTS)
RECOVERY_PAGE_TABLE_TESTS = tuple("ostd::mm::vm_space::recovery_tests::" + suffix for suffix in (
    "recovery_root_uses_explicit_reserve_and_closed_root_fails",
    "recovery_mapping_failure_at_each_missing_level_preserves_input_and_tree",
    "recovery_mapping_uses_only_selected_token_and_refunds_last_vm_owner",
    "recovery_mapping_does_not_authorize_ordinary_or_closed_growth",
    "recovery_mapping_rejects_conflict_without_replacing_original_frame",
))
REQUIRED_OSTD_TESTS = (
    "ostd::mm::frame::allocator::allocation_claim_rejects_busy_page_without_refunding_its_owner",
    "ostd::user::fatal_pre_entry_returns_kernel_event_before_unmapped_user_code",
    *RECOVERY_PAGE_TABLE_TESTS,
)
MINIMUM_OSTD_TESTS = 229  # Retained 224 plus five explicit-reserve page-table regressions.

# A separate third crate preserves all nine original allocator tests. Changes
# to this exact inventory require review, not a smaller denominator at runtime.
BASELINE_ALLOCATOR_TESTS = tuple("osdk_frame_allocator::" + suffix for suffix in (
    "chunk::test::greater_order_of_works",
    "chunk::test::lesser_order_of_works",
    "chunk::test::max_order_from_works",
    "chunk::test::split_to_chunks_works",
    "chunk::test::split_to_order_works",
    "chunk::test::free_chunk_ops",
    "set::test::buddy_set_insert_alloc",
    "smp_counter::test::per_cpu_counter",
    "test::frame_allocator_alloc_layout_match",
))
RESERVE_ALLOCATOR_TESTS = tuple("osdk_frame_allocator::reserve::tests::" + suffix for suffix in (
    "reserve_admission_and_stale_authority",
    "reserve_refunds_original_owner_after_aliases_and_repurpose",
    "reserve_fragmentation_alignment_and_failed_allocation_refund",
    "reserve_metadata_construction_unwind_refunds_prefix_and_raw_tail",
    "reserve_metadata_callback_cannot_retain_current_or_future_raw_frames",
    "reserve_metadata_callback_cannot_claim_then_drop_raw_frame",
    "reserve_metadata_unwind_preserves_published_prefix_alias_until_final_drop",
    "reserve_raw_subranges_and_typed_frames_share_original_refund",
    "reserve_concurrent_holders_close_and_final_refund",
    "reserve_concurrent_creation_publishes_only_one_extent",
    "reserve_survives_actual_ordinary_allocator_exhaustion_n0",
))
REQUIRED_ALLOCATOR_TESTS = (*BASELINE_ALLOCATOR_TESTS, *RESERVE_ALLOCATOR_TESTS)
EXHAUSTION_MARKER = re.compile(
    r"PHYSICAL_RESERVE_EXHAUSTION ordinary_frames=([0-9]+) reserve_start=(0x[0-9a-f]+) "
    r"reserve_pages=64 ordinary_denied=true reserved_succeeded=true "
    r"returned_to_original_owner=true global_recovery_guarantee=false"
)


def check_fixed_n0_profile(qemu, suite):
    """Require the recorder's actual default N0 invocation, not a profile label."""
    if type(qemu.get("raw_exit_code")) is not int or qemu.get("timed_out") is not False:
        raise ValueError(f"{suite} requires an explicit raw QEMU exit and no timeout")
    expected = {"arch": "x86_64", "machine": "q35", "accel": "tcg", "cpu": "max",
                "vcpus": 1, "memory_mib": 512, "network": False, "data_disks": False}
    if (qemu.get("ktest_profile") != "default" or qemu.get("profile") != expected
            or "test_name" not in qemu or qemu["test_name"] is not None):
        raise ValueError(f"{suite} requires the complete unfiltered default N0 profile")
    argv = qemu.get("argv", [])
    artifacts = qemu.get("artifacts", {})
    if not isinstance(argv, list) or not argv:
        raise ValueError(f"{suite} QEMU invocation is missing")
    expected_argv = [argv[0]]
    for option in ("-kernel", "-initrd", "-append"):
        if option == "-initrd" and option not in argv:
            continue
        if argv.count(option) != 1 or argv.index(option) + 1 >= len(argv):
            raise ValueError(f"{suite} QEMU invocation has missing or repeated boot arguments")
        value = argv[argv.index(option) + 1]
        expected_argv.extend((option, value))
        if option != "-append" and artifacts.get(option, {}).get("path") != value:
            raise ValueError(f"{suite} QEMU boot artifact path does not match the invocation")
    firmware = artifacts.get("-bios", {}).get("path")
    if firmware != "/usr/share/seabios/bios-256k.bin" or argv.count("-chardev") != 1:
        raise ValueError(f"{suite} QEMU firmware or serial record is missing")
    serial_index = argv.index("-chardev") + 1
    if serial_index >= len(argv) or not re.fullmatch(r"stdio,id=serial,signal=off,logfile=.+/serial\.log", argv[serial_index]):
        raise ValueError(f"{suite} QEMU serial capture differs from the fixed profile")
    expected_argv.extend(("-machine", "q35", "-accel", "tcg", "-cpu", "max", "-bios", firmware,
                          "-m", "512M", "-smp", "1", "-nodefaults", "-no-user-config", "-no-reboot",
                          "-nographic", "-display", "none", "-monitor", "none", "-serial", "chardev:serial",
                          "-chardev", argv[serial_index], "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"))
    if argv != expected_argv:
        raise ValueError(f"{suite} actual QEMU invocation differs from the fixed N0 profile")
    for option in ("-kernel", "-bios", *(("-initrd",) if "-initrd" in argv else ())):
        artifact = artifacts.get(option, {})
        if (not re.fullmatch(r"[0-9a-f]{64}", artifact.get("sha256", ""))
                or type(artifact.get("size")) is not int or artifact["size"] <= 0):
            raise ValueError(f"{suite} boot artifact hash/size evidence is missing")


def check_allocator_tests(qemu, serial, section, summary, starts, declared, allow_filtered):
    if allow_filtered:
        raise ValueError("allocator gate never permits filtered qualification")
    check_fixed_n0_profile(qemu, "allocator")
    if len(HEAD.findall(serial)) != 1 or section.find("[ktest runner] All crates tested.") < summary.end():
        raise ValueError("allocator target sequence must finish before the runner completion marker")
    if declared != len(REQUIRED_ALLOCATOR_TESTS) or sorted(starts) != sorted(REQUIRED_ALLOCATOR_TESTS):
        raise ValueError("allocator requires every retained and reserve test exactly once (20 total)")
    if "[skipped:" in serial.lower():
        raise ValueError("allocator suite cannot pass with any soft-skipped test")
    records = list(re.finditer(r"^test ([\w:]+) \.\.\.", section, re.MULTILINE))
    blocks = {}
    for index, record in enumerate(records):
        end = records[index + 1].start() if index + 1 < len(records) else summary.start()
        if record.end() >= end or end > summary.start():
            raise ValueError("allocator per-test result appears outside the target test sequence")
        block = section[record.end():end].rstrip("\n")
        if not re.search(r"(?:\A|\n)[ \t]+ok[ \t]*\Z", block):
            raise ValueError("allocator named test lacks its own terminal ok result")
        blocks[record[1]] = block
    exhaustion = blocks[RESERVE_ALLOCATOR_TESTS[-1]]
    markers = list(EXHAUSTION_MARKER.finditer(exhaustion))
    if serial.count("PHYSICAL_RESERVE_EXHAUSTION") != 1 or len(markers) != 1:
        raise ValueError("allocator exhaustion marker must occur once inside its successful named test")
    marker = markers[0]
    if (exhaustion[:marker.start()].strip() or exhaustion[marker.end():].strip() != "ok"
            or int(marker[1]) <= 64 or int(marker[2], 16) == 0 or int(marker[2], 16) % 4096):
        raise ValueError("allocator exhaustion receipt has inconsistent counts, extent or completion")
    return {"ordinary_frames": int(marker[1]), "reserve_start": marker[2], "reserve_pages": 64,
            "ordinary_denied": True, "reserved_succeeded": True,
            "returned_to_original_owner": True, "global_recovery_guarantee": False}


REQUIRED_MLSDISK_TESTS = tuple("aster_mlsdisk::test::" + name for name in (
    "write_sync_read",
    "raw_disk_flush_submits_and_reports_terminal_failure",
    "mlsdisk_sync_returns_device_flush_error",
    "mlsdisk_flush_bio_completes_with_io_error",
    "entropy_failure_prevents_blob_and_chain_publication",
    "entropy_failure_keeps_buffered_disk_data_for_retry",
    "entropy_failure_aborts_original_log_transaction",
    "entropy_failure_does_not_apply_current_journal_edit",
    "delayed_bio_completes_after_original_task_parks",
    "transaction_callbacks_sleep_and_defer_reentrant_registration",
    "final_store_owner_releases_real_disk_between_full_runs",
    "frame_backed_disk_handles_noncontiguous_cross_page_bios",
)) + (
    "aster_mlsdisk::os::entropy_test::entropy_fill_reports_partial_failure_and_exact_word_count",
    "aster_mlsdisk::os::entropy_test::entropy_cut_is_task_scoped_and_restored_on_drop",
    "aster_mlsdisk::layers::log::tx_log::entropy_tests::journal_entropy_failure_aborts_before_log_publication",
)


def check_mlsdisk_tests(qemu, serial, section, summary, starts, declared, allow_filtered):
    if allow_filtered:
        raise ValueError("mlsdisk gate never permits filtered qualification")
    check_fixed_n0_profile(qemu, "mlsdisk")
    if len(HEAD.findall(serial)) != 1 or section.find("[ktest runner] All crates tested.") < summary.end():
        raise ValueError("mlsdisk target sequence must finish before the runner completion marker")
    if declared != len(REQUIRED_MLSDISK_TESTS) or sorted(starts) != sorted(REQUIRED_MLSDISK_TESTS):
        raise ValueError("mlsdisk requires every original, flush, entropy and async-owner test exactly once (15 total)")
    if "[skipped:" in serial.lower():
        raise ValueError("mlsdisk suite cannot pass with any soft-skipped test")
    records = list(re.finditer(r"^test ([\w:]+) \.\.\.", section, re.MULTILINE))
    for index, record in enumerate(records):
        end = records[index + 1].start() if index + 1 < len(records) else summary.start()
        if record.end() >= end or end > summary.start():
            raise ValueError("mlsdisk per-test result appears outside the target test sequence")
        block = section[record.end():end].rstrip("\n")
        if not re.search(r"(?:\A|\n)[ \t]+ok[ \t]*\Z", block):
            raise ValueError("mlsdisk named test lacks its own terminal ok result")


def check_guest(guest, crate, allow_filtered=False):
    qemu = json.loads((guest / "qemu.json").read_text())
    raw_serial = (guest / "serial.log").read_bytes()
    if qemu.get("serial_sha256") != hashlib.sha256(raw_serial).hexdigest():
        raise ValueError("serial log does not match the recorded SHA256")
    serial = ANSI.sub("", raw_serial.decode(errors="replace")).replace("\r", "")
    if qemu["raw_exit_code"] != 33 or qemu["timed_out"]:
        raise ValueError("guest did not exit with raw successful status 33")
    if qemu.get("crate") != crate:
        raise ValueError("QEMU evidence belongs to a different crate")
    if serial.count("[ktest runner] All crates tested.") != 1:
        raise ValueError("ktest runner did not complete")
    if len(re.findall(r"\[ktest runner\] running \d+ tests in \d+ crates", serial)) != 1:
        raise ValueError("missing or repeated kernel test runner start")
    headers = list(HEAD.finditer(serial))
    targets = [header for header in headers if header[2] == crate]
    if len(targets) != 1:
        raise ValueError("missing or repeated target-crate test header")
    header = targets[0]
    end = next((other.start() for other in headers if other.start() > header.start()), len(serial))
    section = serial[header.end():end]
    summaries = list(SUMMARY.finditer(section))
    if len(summaries) != 1:
        raise ValueError("missing or repeated target-crate result summary")
    summary = summaries[0]
    status, passed, failed, filtered = summary[1], int(summary[2]), int(summary[3]), int(summary[4])
    declared = int(header[1])
    if status != "ok" or failed != 0 or passed == 0 or passed + failed + filtered != declared:
        raise ValueError("failed, empty, or inconsistent target-crate test result")
    if filtered and not allow_filtered:
        raise ValueError("unexpected filtered tests in a full-crate run")
    starts = re.findall(r"^test ([\w:]+) \.\.\.", section, re.MULTILINE)
    if len(starts) != passed + failed or any(not name.startswith(crate.replace('-', '_') + '::') for name in starts):
        raise ValueError("per-test starts do not match the target summary")
    allocator_exhaustion = None
    if crate == "osdk-frame-allocator":
        allocator_exhaustion = check_allocator_tests(
            qemu, serial, section, summary, starts, declared, allow_filtered)
    if crate == "aster-mlsdisk":
        check_mlsdisk_tests(qemu, serial, section, summary, starts, declared, allow_filtered)
    if crate == "aster-core" and not allow_filtered:
        missing = [name for name in REQUIRED_CORE_TESTS if starts.count(name) != 1]
        if missing:
            raise ValueError("missing or repeated required core tests: " + ", ".join(missing))
        for name in REQUIRED_CORE_TESTS:
            block = section.split(f"test {name} ...", 1)[1].split("\ntest ", 1)[0]
            if "[skipped:" in block:
                raise ValueError("required core test was soft-skipped: " + name)
        if passed < MINIMUM_CORE_TESTS:
            raise ValueError("complete core gate shrank below the retained baseline plus regressions")
        for name in REQUIRED_CORE_TESTS:
            block = section.split(f"test {name} ...", 1)[1].split("\ntest ", 1)[0]
            if "[skipped:" in block:
                raise ValueError(f"required core test was soft-skipped: {name}")
    if any(result[1] == "FAILED" or int(result[3]) for result in SUMMARY.finditer(serial)):
        raise ValueError("a tested crate reported failure")
    # Expected-panic tests are valid kernel tests. Do not apply boot's broad
    # panic-string filter; reject explicit uncaught/fatal test-runner messages.
    if any(marker in serial for marker in ("An uncaught panic occurred:", "Uncaught panic:",
                                           "unknown panic payload! (fatal panic handling error",
                                           "Non-resettable panic!", "The panic handler panicked",
                                           "Panicked in `PanicGuard`, aborting the system")):
        raise ValueError("uncaught or fatal kernel-test panic")
    skips = re.findall(r"\[skipped: ([^\]]+)\]", section)
    if len(skips) >= passed:
        raise ValueError("no target test exercised beyond reported soft skips")
    if crate == "ostd" and not allow_filtered:
        for name in REQUIRED_OSTD_TESTS:
            if starts.count(name) != 1:
                raise ValueError("missing or repeated required OSTD test: " + name)
            block = section.split(f"test {name} ...", 1)[1].split("\ntest ", 1)[0]
            if "[skipped:" in block:
                raise ValueError("required OSTD test was soft-skipped: " + name)
        if passed < MINIMUM_OSTD_TESTS:
            raise ValueError("complete OSTD gate shrank below the retained 224 tests plus five recovery page-table regressions")
    return {"crate": crate, "declared": declared, "passed": passed, "failed": failed,
            "filtered": filtered, "soft_skipped": len(skips), "soft_skip_reasons": skips,
            "exercised_passed_lower_bound": passed - len(skips),
            "observed_test_starts": len(starts),
            "required_permission_tests": sorted(PERMISSION_TESTS) if crate == "aster-core" and not allow_filtered else [],
            "required_core_tests": list(REQUIRED_CORE_TESTS) if crate == "aster-core" and not allow_filtered else [],
            "required_allocator_tests": list(REQUIRED_ALLOCATOR_TESTS) if crate == "osdk-frame-allocator" else [],
            "allocator_exhaustion": allocator_exhaustion,
            "required_mlsdisk_tests": list(REQUIRED_MLSDISK_TESTS) if crate == "aster-mlsdisk" else [],
            "mlsdisk_media_durability_qualified": False if crate == "aster-mlsdisk" else None,
            "required_ostd_tests": list(REQUIRED_OSTD_TESTS) if crate == "ostd" and not allow_filtered else [],
            "raw_qemu_exit": 33, "guest": guest.name}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--crate", required=True)
    parser.add_argument("--allow-filtered", action="store_true")
    args = parser.parse_args()
    guests = sorted(args.directory.glob("guest-*"))
    if not guests:
        raise SystemExit("no real QEMU guest records found")
    results = []
    for guest in guests:
        try:
            results.append(check_guest(guest, args.crate, args.allow_filtered))
        except (ValueError, KeyError, OSError) as error:
            raise SystemExit(f"{guest.name}: {error}") from error
    print(json.dumps({"passed": True, "guests": results}, indent=2))


if __name__ == "__main__":
    main()
