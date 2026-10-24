#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Strict Linux/native oracle for the original Root's required process ABI."""

CASES = (
    "root_actual_ids", "boot_identity", "proc_start_identity", "proc_exe_inode",
    "proc_mountinfo", "memfd_create_metadata", "memfd_seal_metadata", "memfd_readback",
    "memfd_write_denied", "memfd_resize_denied", "memfd_shared_write_denied",
    "private_socket_directory", "child_peer_credentials", "child_exec_close_range",
    "child_restricted_credentials", "child_root_peer_credentials", "child_rights_cloexec",
    "child_sealed_memfd", "child_root_pidfd", "child_root_pidfd_alive",
    "child_pidfd_identity", "child_pidfd_alive", "child_pidfd_zero_signal",
    "child_pidfd_exit_ready", "child_reap_sigkill", "child_pidfd_reaped_esrch",
    "all_resources_released",
)
RECORDS = [f"ROOT_ABI_CASE name={name} passed=1".encode() for name in CASES]
SUMMARY = f"ROOT_ABI_SUMMARY passed={len(CASES)} failed=0 g2_complete=false".encode()
EXIT = b"ROOT_AUTHORITY_ABI_PROBE_EXIT=0"
BOOT = b"TRILLIONNIUM_A01_BOOT_OK"


def check(data, exit_code, timed_out=False, *, guest=False):
    errors = []
    lines = data.splitlines()
    records = [line for line in lines if b"ROOT_ABI_" in line]
    if records != RECORDS + [SUMMARY]:
        errors.append("complete ordered 27-case inventory and exact summary required")
    if b"ROOT_ABI_FAIL" in data or b"ROOT_ABI_TIMEOUT" in data:
        errors.append("actual child/parent failure or alarm is never a pass")
    if timed_out:
        errors.append("outer timeout is never a pass")
    if guest:
        markers = [line for line in lines if b"ROOT_AUTHORITY_ABI_PROBE_EXIT=" in line]
        if markers != [EXIT]:
            errors.append("unique zero probe exit marker required")
        if lines.count(BOOT) != 1:
            errors.append("unique ordinary boot marker required")
        if records == RECORDS + [SUMMARY] and markers == [EXIT] and lines.count(BOOT) == 1:
            if not (lines.index(SUMMARY) < lines.index(EXIT) < lines.index(BOOT)):
                errors.append("probe/exit/boot ordering changed")
        if b"[hepta-g2]" in data or b"[hepta-g1d] initial roles activated" in data:
            errors.append("ordinary kernel required for this ABI preflight")
        if exit_code != 33:
            errors.append("ordinary QEMU must exit 33")
    else:
        if [line for line in lines if line] != RECORDS + [SUMMARY]:
            errors.append("unexpected Linux output")
        if exit_code != 0:
            errors.append("Linux process must exit zero")
    return {"passed": not errors, "checks": sum(line in RECORDS for line in records),
            "errors": errors, "runtime_scope": "native_abi" if guest else "linux_reference",
            "original_writer_executed": False, "persistent_cpu_qualified": False,
            "recovery_qualified": False, "g2_complete": False}
