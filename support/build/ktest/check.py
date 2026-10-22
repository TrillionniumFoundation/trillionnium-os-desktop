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

# The default core gate keeps its 238-test baseline, five permission tests,
# all twenty-one G1-c/G1-d regressions, two ExFAT tests and three ext2
# durability regressions, plus five initial-readonly atime/sync regressions.
# Filtered runs retain explicit opt-in; they cannot stand in for a complete
# core qualification.
MINIMUM_CORE_TESTS = 274
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
REQUIRED_CORE_TESTS = (*sorted(PERMISSION_TESTS), *TRUSTED_PROFILE_CORE_TESTS, *EXFAT_CORE_TESTS,
                       *EXT2_DURABILITY_TESTS, *EXT2_READONLY_ATIME_TESTS)


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
    return {"crate": crate, "declared": declared, "passed": passed, "failed": failed,
            "filtered": filtered, "soft_skipped": len(skips), "soft_skip_reasons": skips,
            "exercised_passed_lower_bound": passed - len(skips),
            "observed_test_starts": len(starts),
            "required_permission_tests": sorted(PERMISSION_TESTS) if crate == "aster-core" and not allow_filtered else [],
            "required_core_tests": list(REQUIRED_CORE_TESTS) if crate == "aster-core" and not allow_filtered else [],
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
