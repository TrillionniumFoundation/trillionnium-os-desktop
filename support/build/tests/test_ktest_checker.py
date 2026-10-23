#!/usr/bin/env python3
"""Mutate synthetic ktest evidence; never compile or execute a kernel."""

import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest


CHECKER = Path(__file__).resolve().parents[1] / "ktest/check.py"
CHECKER_MODULE = runpy.run_path(str(CHECKER))
check_guest = CHECKER_MODULE["check_guest"]
REQUIRED_CORE_TESTS = CHECKER_MODULE["REQUIRED_CORE_TESTS"]
MINIMUM_CORE_TESTS = CHECKER_MODULE["MINIMUM_CORE_TESTS"]
REQUIRED_OSTD_TESTS = CHECKER_MODULE["REQUIRED_OSTD_TESTS"]
MINIMUM_OSTD_TESTS = CHECKER_MODULE["MINIMUM_OSTD_TESTS"]


def serial_log(passed=MINIMUM_OSTD_TESTS, failed=0, filtered=0, skips=0):
    declared = passed + failed + filtered
    lines = [
        f"[ktest runner] running {declared} tests in 1 crates",
        f'running {declared} tests in crate "ostd"',
    ]
    for index in range(passed + failed):
        skip = " [skipped: VMX unavailable]" if index < skips else ""
        status = "ok" if index < passed else "FAILED"
        offset = index - (passed + failed - len(REQUIRED_OSTD_TESTS))
        name = REQUIRED_OSTD_TESTS[offset] if 0 <= offset < len(REQUIRED_OSTD_TESTS) else f"ostd::fixture::case_{index}"
        lines.append(f"test {name} ...{skip} \x1b[32m{status}\x1b[0m")
    status = "ok" if not failed else "FAILED"
    lines.extend((
        f"test result: {status}. {passed} passed; {failed} failed; {filtered} filtered out.",
        "[ktest runner] All crates tested.",
    ))
    return ("\r\n".join(lines) + "\r\n").encode()


def core_serial(names):
    lines = [f"[ktest runner] running {len(names)} tests in 1 crates",
             f'running {len(names)} tests in crate "aster-core"']
    lines.extend(f"test {name} ... ok" for name in names)
    lines.extend((f"test result: ok. {len(names)} passed; 0 failed; 0 filtered out.",
                  "[ktest runner] All crates tested."))
    return ("\r\n".join(lines) + "\r\n").encode()


class KtestCheckerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="a01-ktest-checker-")
        self.addCleanup(self.temporary.cleanup)
        self.guests = Path(self.temporary.name)
        self.guest = self.guests / "guest-001"
        self.guest.mkdir()

    def evidence(self, serial=None, **metadata):
        serial = serial_log() if serial is None else serial
        record = {
            "schema": 1, "crate": "ostd", "raw_exit_code": 33,
            "timed_out": False,
            "serial_sha256": hashlib.sha256(serial).hexdigest(),
        }
        record.update(metadata)
        (self.guest / "serial.log").write_bytes(serial)
        (self.guest / "qemu.json").write_text(json.dumps(record))

    def test_valid_guest_requires_nonempty_own_crate_results(self):
        self.evidence()
        result = check_guest(self.guest, "ostd")
        self.assertEqual(result["declared"], MINIMUM_OSTD_TESTS)
        self.assertEqual(result["passed"], MINIMUM_OSTD_TESTS)
        self.assertEqual(result["soft_skipped"], 0)
        self.assertEqual(result["exercised_passed_lower_bound"], MINIMUM_OSTD_TESTS)

    def test_complete_ostd_requires_owner_fatal_and_page_table_regressions_without_soft_skip(self):
        self.assertEqual(len(REQUIRED_OSTD_TESTS), 8)
        for required in REQUIRED_OSTD_TESTS:
            name = required.encode()
            for serial in (serial_log().replace(name, b"ostd::fixture::unrelated"),
                           serial_log().replace(name + b" ...", name + b" ... [skipped: fixture]")):
                with self.subTest(required=required, serial=serial):
                    self.evidence(serial)
                    with self.assertRaisesRegex(ValueError, "required OSTD test"):
                        check_guest(self.guest, "ostd")

    def test_ostd_owner_regression_cannot_replace_the_retained_baseline(self):
        self.assertEqual(MINIMUM_OSTD_TESTS, 230)
        for count in (7, 8, 224, 228, 229):
            self.evidence(serial_log(passed=count))
            with self.assertRaisesRegex(ValueError, "required OSTD test" if count == 7 else "OSTD gate shrank"):
                check_guest(self.guest, "ostd")

    def test_serial_tampering_is_rejected_before_parsing(self):
        self.evidence()
        # The extra text leaves all test counts and success markers valid.
        with (self.guest / "serial.log").open("ab") as output:
            output.write(b"different run's trailing output\n")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            check_guest(self.guest, "ostd")

    def test_missing_and_wrong_serial_hash_are_rejected(self):
        for mode in ("missing", "wrong"):
            with self.subTest(mode=mode):
                self.evidence()
                record_path = self.guest / "qemu.json"
                record = json.loads(record_path.read_text())
                if mode == "missing":
                    record.pop("serial_sha256")
                else:
                    record["serial_sha256"] = "0" * 64
                record_path.write_text(json.dumps(record))
                with self.assertRaisesRegex(ValueError, "SHA256"):
                    check_guest(self.guest, "ostd")

    def test_zero_tests_and_all_filtered_are_rejected_even_when_filtering_allowed(self):
        for filtered in (0, 2):
            with self.subTest(filtered=filtered):
                self.evidence(serial_log(passed=0, filtered=filtered))
                with self.assertRaisesRegex(ValueError, "empty"):
                    check_guest(self.guest, "ostd", allow_filtered=True)

    def test_non_successful_raw_qemu_status_is_rejected(self):
        for code in (0, 1, 65, 124, -9):
            with self.subTest(raw_exit_code=code):
                self.evidence(raw_exit_code=code)
                with self.assertRaisesRegex(ValueError, "status 33"):
                    check_guest(self.guest, "ostd")

    def test_timeout_is_rejected_even_with_successful_status_and_log(self):
        self.evidence(timed_out=True)
        with self.assertRaisesRegex(ValueError, "status 33"):
            check_guest(self.guest, "ostd")

    def test_filter_requires_explicit_permission_and_exercised_test(self):
        self.evidence(serial_log(passed=1, filtered=1))
        with self.assertRaisesRegex(ValueError, "unexpected filtered"):
            check_guest(self.guest, "ostd")
        result = check_guest(self.guest, "ostd", allow_filtered=True)
        self.assertEqual((result["passed"], result["filtered"]), (1, 1))

    def test_soft_skip_counts_preserve_exercised_lower_bound(self):
        self.evidence(serial_log(passed=MINIMUM_OSTD_TESTS, skips=2))
        result = check_guest(self.guest, "ostd")
        self.assertEqual(result["soft_skipped"], 2)
        self.assertEqual(result["soft_skip_reasons"], ["VMX unavailable"] * 2)
        self.assertEqual(result["exercised_passed_lower_bound"], MINIMUM_OSTD_TESTS - 2)

    def test_all_soft_skipped_is_not_exercised_success(self):
        self.evidence(serial_log(passed=2, skips=2))
        with self.assertRaisesRegex(ValueError, "no target test exercised"):
            check_guest(self.guest, "ostd")

    def test_summary_without_per_test_execution_is_rejected(self):
        lines = serial_log().splitlines(keepends=True)
        serial = b"".join(line for line in lines if not line.startswith(b"test ostd::"))
        self.evidence(serial)
        with self.assertRaisesRegex(ValueError, "per-test starts"):
            check_guest(self.guest, "ostd")

    def test_other_crate_success_cannot_replace_target_success(self):
        self.evidence(serial_log().replace(b'crate "ostd"', b'crate "other"'))
        with self.assertRaisesRegex(ValueError, "target-crate test header"):
            check_guest(self.guest, "ostd")

    def test_empty_guest_directory_is_rejected_by_entry_point(self):
        empty = self.guests / "empty"
        empty.mkdir()
        result = subprocess.run(
            [sys.executable, "-I", str(CHECKER), str(empty), "--crate", "ostd"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=5,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("no real QEMU guest records", result.stdout)

    def test_complete_core_requires_all_named_regressions_exactly_once(self):
        self.assertEqual(len(REQUIRED_CORE_TESTS), 108)
        self.assertEqual(MINIMUM_CORE_TESTS, 347)
        baseline = tuple(f"aster_core::fixture::retained_{index}" for index in range(239))
        names = (*baseline, *REQUIRED_CORE_TESTS)
        self.evidence(core_serial(names), crate="aster-core")
        self.assertEqual(check_guest(self.guest, "aster-core")["passed"], MINIMUM_CORE_TESTS)
        for name in REQUIRED_CORE_TESTS:
            with self.subTest(missing=name):
                replaced = tuple("aster_core::fixture::unrelated" if item == name else item for item in names)
                self.evidence(core_serial(replaced), crate="aster-core")
                with self.assertRaisesRegex(ValueError, "required core tests"):
                    check_guest(self.guest, "aster-core")
            with self.subTest(soft_skipped=name):
                skipped = core_serial(names).replace(
                    f"test {name} ... ok".encode(),
                    f"test {name} ... [skipped: synthetic fixture] ok".encode())
                self.evidence(skipped, crate="aster-core")
                with self.assertRaisesRegex(ValueError, "soft-skipped"):
                    check_guest(self.guest, "aster-core")
        self.evidence(core_serial((*names, REQUIRED_CORE_TESTS[0])), crate="aster-core")
        with self.assertRaisesRegex(ValueError, "required core tests"):
            check_guest(self.guest, "aster-core")

    def test_required_core_tests_cannot_pass_as_soft_skips(self):
        baseline = tuple(f"aster_core::fixture::retained_{index}" for index in range(239))
        names = (*baseline, *REQUIRED_CORE_TESTS)
        for name in REQUIRED_CORE_TESTS:
            with self.subTest(soft_skipped=name):
                serial = core_serial(names).replace(
                    f"test {name} ... ok".encode(),
                    f"test {name} ... [skipped: unavailable] ok".encode(),
                )
                self.evidence(serial, crate="aster-core")
                with self.assertRaisesRegex(ValueError, "required core test was soft-skipped"):
                    check_guest(self.guest, "aster-core")

    def test_pre_extension_238_test_success_cannot_pass_current_core_gate(self):
        names = tuple(f"aster_core::fixture::old_{index}" for index in range(239))
        self.evidence(core_serial(names), crate="aster-core")
        with self.assertRaisesRegex(ValueError, "required core tests"):
            check_guest(self.guest, "aster-core")

    def test_new_regressions_do_not_replace_the_retained_core_baseline(self):
        self.evidence(core_serial(REQUIRED_CORE_TESTS), crate="aster-core")
        with self.assertRaisesRegex(ValueError, "shrank"):
            check_guest(self.guest, "aster-core")


if __name__ == "__main__":
    unittest.main(verbosity=2)
