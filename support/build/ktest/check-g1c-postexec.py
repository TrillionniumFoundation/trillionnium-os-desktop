#!/usr/bin/env python3
"""Add the g1c post-exec object tests to the complete original core oracle.

This is kernel-object qualification. It does not establish a sealed native
Supervisor launch, a production issuer, or a successful original-CPU grant/read.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import stat


def load_original_checker():
    path = Path(__file__).with_name("check.py")
    spec = importlib.util.spec_from_file_location("original_core_ktest_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


original = load_original_checker()
PROFILE = "g1c-postexec-observe"
FEATURES = ["g1c-trusted-observe"]
FENCE_TESTS = (
    "aster_core::util::external_mutation::tests::in_flight_admission_rejects_fence_without_closing_the_owner",
    "aster_core::fs::fs_impls::procfs::pid::task::mem::tests::an_already_open_mem_handle_cannot_write_after_its_vmar_is_fenced",
    "aster_core::process::posix_thread::ptrace::external_fence_tests::a_captured_tracee_reference_cannot_mutate_after_process_fencing_or_exec",
    "aster_core::vm::vmar::vmar_impls::access_alien::external_fence_tests::actual_alien_write_admission_blocks_fencing_until_the_copy_finishes",
    "aster_core::process::clone::external_share_tests::shared_clone_and_vfork_admission_cannot_race_the_single_handle_fence",
)
RECIPIENT_TESTS = tuple(
    "aster_core::process::process::postexec_observe::tests::" + name for name in (
        "postexec_child_requires_its_original_pidfd_and_live_image",
        "foreign_caller_and_nonchild_pidfd_cannot_bind_a_launch",
        "fork_image_before_exec_cannot_receive_a_launch",
        "sibling_control_fd_and_wrong_nonce_cannot_replace_bound_child",
        "child_exec_between_pidfd_binding_and_fd_handoff_fences_both_sessions",
        "child_exit_and_supervisor_exec_fail_the_pending_handoff",
        "reparenting_and_a_second_issuer_claim_fail_closed",
        "invalid_recipient_never_reaches_the_irreversible_protection_step",
        "an_existing_real_tracer_is_rejected_before_either_fence_commits",
        "either_inflight_owner_rejects_installation_without_fencing_the_other",
    )
) + ("aster_core::device::misc::hepta_control::recipient_tests::actual_control_file_rejects_a_foreign_caller_and_an_ended_recipient",)
REQUIRED_ADDITIONAL_TESTS = FENCE_TESTS + RECIPIENT_TESTS


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_environment(environment_path, commands_path):
    environment = json.loads(environment_path.read_text())
    commands = json.loads(commands_path.read_text())
    require(environment.get("ktest_profile") == PROFILE and environment.get("vcpus") == 1,
            "wrong fixed g1c kernel-test profile")
    require(environment.get("features") == FEATURES and environment.get("test_name") is None,
            "g1c kernel tests require the exact feature and no test filter")
    require(environment.get("toolchain") == "nightly-2026-07-21" and environment.get("git_status") == "",
            "g1c source/toolchain identity is not a clean fixed candidate")
    source = environment.get("source_identity", {})
    require(source.get("head") == environment.get("git_head")
            and all(re.fullmatch(r"[0-9a-f]{40}", source.get(key, "")) for key in ("head", "tree")),
            "missing complete committed source identity")
    require(environment.get("qualification") == "kernel-object-tests-only"
            and environment.get("native_sealed_launch_qualified") is False
            and environment.get("g2_qualified") is False,
            "kernel-object evidence must not claim native/production G2")
    tests = [entry for entry in commands if entry.get("argv", [])[2:4] == ["osdk", "test"]]
    require(len(tests) == 1, "expected exactly one complete aster-core invocation")
    argv = tests[0]["argv"]
    require(argv[:4] == ["cargo", "+nightly-2026-07-21", "osdk", "test"]
            and Path(tests[0]["cwd"]).parts[-2:] == ("kernel", "core")
            and argv[4:] == ["--release", "--boot-method=vmm-direct", "--grub-boot-protocol=multiboot",
                             "--qemu-exe=" + str(Path(__file__).resolve().with_name("record-qemu.py")),
                             "--kcmd-args=loglevel=error", "--kcmd-args=earlycon",
                             "--kcmd-args=console=ttyS0", "--features=g1c-trusted-observe"],
            "complete core command differs from the fixed unfiltered feature invocation")
    manifest = environment.get("trusted_initial", {})
    embedded = environment_path.resolve().parent / "trusted-initial.elf"
    require(manifest.get("profile") == FEATURES[0] and manifest.get("embedded_input") == str(embedded),
            "trusted ELF manifest is not bound to this output directory")
    require(embedded.is_file() and not embedded.is_symlink()
            and stat.S_IMODE(embedded.stat().st_mode) == 0o444,
            "trusted ELF is not the frozen read-only regular input")
    data = embedded.read_bytes()
    require(20 <= len(data) <= 8 * 1024 * 1024 and len(data) == manifest.get("bytes")
            and hashlib.sha256(data).hexdigest() == manifest.get("sha256")
            and data[:7] == b"\x7fELF\x02\x01\x01" and data[16:20] == b"\x02\x00\x3e\x00",
            "frozen trusted ELF identity changed")
    return {"source_identity": source, "trusted_initial_sha256": manifest["sha256"]}


def check_guest(guest):
    # Preserve every current and future retained default-core assertion.
    result = original.check_guest(guest, "aster-core", allow_filtered=False)
    qemu = json.loads((guest / "qemu.json").read_text())
    require(qemu.get("ktest_profile") == PROFILE
            and qemu.get("profile") == {"arch": "x86_64", "machine": "q35", "accel": "tcg", "cpu": "max",
                                        "vcpus": 1, "memory_mib": 512, "network": False, "data_disks": False},
            "guest was not run under the fixed one-CPU g1c profile")
    serial = original.ANSI.sub("", (guest / "serial.log").read_text(errors="replace")).replace("\r", "")
    headers = list(original.HEAD.finditer(serial))
    header = next(item for item in headers if item[2] == "aster-core")
    end = next((other.start() for other in headers if other.start() > header.start()), len(serial))
    section = serial[header.end():end]
    starts = re.findall(r"^test ([\w:]+) \.\.\.", section, re.MULTILINE)
    for name in REQUIRED_ADDITIONAL_TESTS:
        require(starts.count(name) == 1, "missing or repeated additional g1c test: " + name)
        block = section.split(f"test {name} ...", 1)[1].split("\ntest ", 1)[0]
        require("[skipped:" not in block, "additional g1c test was soft-skipped: " + name)
    require(result["passed"] >= original.MINIMUM_CORE_TESTS + len(REQUIRED_ADDITIONAL_TESTS),
            "g1c complete gate shrank below the original core minimum plus all additions")
    return {**result, "required_additional_tests": list(REQUIRED_ADDITIONAL_TESTS),
            "ktest_profile": PROFILE, "qualification": "kernel-object-tests-only",
            "native_sealed_launch_qualified": False, "g2_qualified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--environment", type=Path, required=True)
    parser.add_argument("--commands", type=Path, required=True)
    args = parser.parse_args()
    identity = check_environment(args.environment, args.commands)
    guests = sorted(args.directory.glob("guest-*"))
    require(bool(guests), "no real QEMU guest records found")
    results = [check_guest(guest) for guest in guests]
    print(json.dumps({"passed": True, **identity, "guests": results,
                      "qualification": "kernel-object-tests-only", "native_sealed_launch_qualified": False,
                      "g2_qualified": False}, indent=2))


if __name__ == "__main__":
    main()
