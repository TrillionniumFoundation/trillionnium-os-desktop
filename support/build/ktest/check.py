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
        for name in sorted(PERMISSION_TESTS):
            if starts.count(name) != 1:
                raise ValueError(f"missing or repeated required permission test: {name}")
            block = section.split(f"test {name} ...", 1)[1].split("\ntest ", 1)[0]
            if "[skipped:" in block:
                raise ValueError(f"required permission test was soft-skipped: {name}")
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
