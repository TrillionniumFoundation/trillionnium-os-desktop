#!/usr/bin/env python3
"""Preserve the whole original core gate and all G2 Process regressions.

This qualifies kernel Process-state tests only. The embedded ELF is a bounded
compilation input; these ktests neither boot it nor qualify a Hepta owner.
The original three Root tests and eleven successor/launcher tests are mandatory.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import stat
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("original_core_ktest_check", HERE / "check.py")
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)

G2_TESTS = tuple("aster_core::process::process::image::tests::" + name for name in (
    "frozen_root_requires_its_prepared_image_and_has_no_control_slot",
    "frozen_root_exec_fences_old_image_without_reactivating_the_role",
    "cancelled_frozen_root_does_not_leave_live_process_protection",
))
CONTINUITY_TESTS = tuple("aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::trusted_control::tests::" + name for name in (
    "native_late_image_close_cannot_revoke_replacement_delegations",
    "native_delayed_watchdog_cut_cannot_mutate_a_replacement_policy",
    "native_watchdog_registration_is_bounded_across_owner_policy_replacements",
))
CPU_SUCCESSOR_TESTS = tuple("aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::trusted_control::tests::" + name for name in (
    "native_successor_preparation_and_drop_do_not_publish_authority",
    "native_successor_requires_both_exact_predecessor_delegations_closed",
    "native_successor_preserves_cpu_debt_revision_and_original_delivery_history",
    "native_successor_failed_or_stale_commit_leaves_current_policy_intact",
    "native_successor_generations_keep_one_watchdog_registration_and_bounded_origins",
))
G2_SUCCESSOR_TESTS = (
    *("aster_core::process::process::init_proc::trusted_launcher::tests::" + name for name in (
        "native_successor_claim_failure_closes_all_unpublished_images",
        "native_successor_cancelled_token_cannot_close_a_newer_image",
        "native_successor_reap_gate_requires_release_of_the_actual_child_allocation",
        "native_successor_generation_replays_only_the_last_successful_transaction",
        "native_successor_history_page_has_fresh_local_space_and_no_effect_handles",
        "native_successor_launcher_refuses_ordinary_marker_only_and_ended_images",
        "native_successor_image_allocation_failure_never_publishes_a_process",
    )),
    *("aster_core::process::process::trusted_control::successor_tests::" + name for name in (
        "native_successor_requires_retirement_of_both_original_history_frontiers",
        "native_successor_empty_lost_history_is_not_a_retirement_proof",
        "native_history_only_image_retains_original_owners_without_effect_namespace",
    )),
    "aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::trusted_control::tests::native_successor_commit_retains_the_watchdog_receipt_from_its_final_owner_cut",
)
G2_REQUIRED_TESTS = (*G2_TESTS, *G2_SUCCESSOR_TESTS)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_build(directory):
    output = directory.parent.parent
    environment = json.loads((output / "environment.json").read_text())
    require(environment.get("g2_initial_root") is True and environment.get("features") == ["g2-trusted-daemon"]
            and environment.get("ktest_profile") == "default" and environment.get("test_name") is None
            and type(environment.get("vcpus")) is int and environment["vcpus"] == 1
            and environment.get("toolchain") == "nightly-2026-07-21",
            "G2 core requires the explicit feature and unchanged unfiltered one-CPU N0 profile")
    require(re.fullmatch(r"[0-9a-f]{40}", environment.get("git_head", "")) is not None
            and environment.get("git_status") == "", "clean exact original kernel source required")
    trusted = environment.get("ktest_trusted_initial", {})
    require(set(trusted) == {"source_path", "path", "sha256", "bytes", "compilation_input_only", "native_entry_execution_claimed"}
            and trusted["compilation_input_only"] is True and trusted["native_entry_execution_claimed"] is False
            and trusted["path"] == str(output / "ktest-trusted-initial.elf")
            and type(trusted["bytes"]) is int and 0 < trusted["bytes"] <= 8 * 1024**2
            and re.fullmatch(r"[0-9a-f]{64}", trusted["sha256"]) is not None,
            "G2 ktest compilation input provenance missing")
    image = output / "ktest-trusted-initial.elf"
    require(image.is_file() and not image.is_symlink() and image.stat().st_size == trusted["bytes"]
            and stat.S_IMODE(image.stat().st_mode) == 0o444 and digest(image) == trusted["sha256"],
            "frozen G2 ktest compilation bytes changed")
    commands = json.loads((output / "commands.json").read_text())
    require(type(commands) is list and 1 <= len(commands) <= 2, "one actual G2 OSDK test command required")
    tests = [item for item in commands if type(item) is dict and "test" in item.get("argv", [])]
    require(len(tests) == 1, "missing or repeated G2 test command")
    command = tests[0]
    cwd = Path(command.get("cwd", ""))
    require(cwd.is_absolute() and tuple(cwd.parts[-4:]) == ("kernel", "asterinas", "kernel", "core"),
            "G2 test must execute the original aster-core crate")
    project = cwd.parents[3]
    expected = ["cargo", "+nightly-2026-07-21", "osdk", "test", "--release", "--boot-method=vmm-direct",
                "--grub-boot-protocol=multiboot", "--qemu-exe=" + str(project / "support/build/ktest/record-qemu.py"),
                "--kcmd-args=loglevel=error", "--kcmd-args=earlycon", "--kcmd-args=console=ttyS0",
                "--features=g2-trusted-daemon"]
    require(command.get("argv") == expected, "G2 actual OSDK command differs or filters the original core suite")
    lock = directory.parent / "generated.Cargo.lock"
    expected_lock = environment.get("build_inputs_sha256", {}).get("support/build/ktest/locks/aster-core.Cargo.lock")
    require(type(expected_lock) is str and re.fullmatch(r"[0-9a-f]{64}", expected_lock) is not None
            and command.get("lock_sha256") == expected_lock and digest(lock) == expected_lock,
            "G2 core generated lock differs from the original fixed lock")
    require((directory.parent / "osdk-exit-code.txt").read_text().strip() == "0", "original G2 OSDK test failed")
    return {"source_head": environment["git_head"], "features": environment["features"],
            "generated_lock_sha256": expected_lock, "ktest_trusted_initial": trusted,
            "osdk_sha256": environment.get("osdk_sha256")}


def check_guest(guest):
    # The original checker owns the complete baseline and its required CPU
    # continuity/successor tests. A stale checker must not qualify a newer G2
    # product; the old 365/368-test gates cannot be paired with this extension.
    required = original.REQUIRED_CORE_TESTS
    require(type(original.MINIMUM_CORE_TESTS) is int and original.MINIMUM_CORE_TESTS >= 373
            and len(required) >= 134 and len(set(required)) == len(required)
            and all(required.count(name) == 1 for name in (*CONTINUITY_TESTS, *CPU_SUCCESSOR_TESTS)),
            "G2 requires the original 373-test core gate with at least 134 required names, CPU continuity3 and successor5")
    result = original.check_guest(guest, "aster-core", False)
    qemu = json.loads((guest / "qemu.json").read_text())
    original.check_fixed_n0_profile(qemu, "G2 original Process-state tests")
    serial = original.ANSI.sub("", (guest / "serial.log").read_text()).replace("\r", "")
    headers = list(original.HEAD.finditer(serial))
    header = next(item for item in headers if item[2] == "aster-core")
    end = next((item.start() for item in headers if item.start() > header.start()), len(serial))
    section = serial[header.end():end]
    summary = next(original.SUMMARY.finditer(section))
    records = list(re.finditer(r"^test ([\w:]+) \.\.\.", section, re.MULTILINE))
    for name in G2_REQUIRED_TESTS:
        matches = [(index, item) for index, item in enumerate(records) if item[1] == name]
        require(len(matches) == 1, "missing or repeated actual G2 Process test: " + name)
        index, record = matches[0]
        boundary = records[index + 1].start() if index + 1 < len(records) else summary.start()
        require(record.start() < record.end() <= boundary <= summary.start(), "G2 test appears after its summary")
        block = section[record.end():boundary].rstrip("\n")
        require("[skipped:" not in block and re.search(r"(?:\A|\n)[ \t]+ok[ \t]*\Z", block) is not None,
                "G2 Process test lacks its own exercised terminal ok: " + name)
    require(result["passed"] >= original.MINIMUM_CORE_TESTS + len(G2_REQUIRED_TESTS),
            "G2 core shrank the preserved whole-core baseline plus Root3 and successor11 tests")
    return {**result, "required_g2_process_tests": list(G2_TESTS), "g2_process_tests_exercised": len(G2_TESTS),
            "required_g2_successor_tests": list(G2_SUCCESSOR_TESTS),
            "g2_successor_tests_exercised": len(G2_SUCCESSOR_TESTS),
            "g2_total_additional_tests_exercised": len(G2_REQUIRED_TESTS),
            "original_core_inventory_preserved": True, "actual_native_owner_verified": False, "g2_complete": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        build = check_build(args.directory)
        guests = sorted(args.directory.glob("guest-*"))
        require(bool(guests), "no actual G2 QEMU guests retained")
        results = [check_guest(guest) for guest in guests]
        value = {"passed": True, "build": build, "guests": results,
                 "actual_native_owner_verified": False, "g2_complete": False}
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
        value = {"passed": False, "error": f"{type(error).__name__}: {error}",
                 "actual_native_owner_verified": False, "g2_complete": False}
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0 if value["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
