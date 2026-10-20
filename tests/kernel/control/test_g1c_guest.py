#!/usr/bin/env python3
"""Negative controls for the host evidence verdict; these are not guest runs."""
import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name("run_g1c_guest.py")
SPEC = importlib.util.spec_from_file_location("g1c_guest", SOURCE)
g1c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(g1c)
INFO = {"bytes": 8192, "entry": 0x401000}


def valid_serial():
    lines = ["[hepta-g1c] trusted initial image committed: bytes=8192 entry=0x401000", g1c.ACTIVATED]
    lines.extend(g1c.MARKERS)
    lines.extend(f"G1C_SEAL_CASE name={name} result=PASS errno=1" for name in g1c.SEAL_CASES)
    for index, label in enumerate(g1c.USAGE_LABELS):
        revision = (2 if label == "same_linux_budget" else 3 if label == "changed_linux_budget"
                    else 4 if index >= g1c.USAGE_LABELS.index("restored_linux_budget") else 1)
        cap = 25_000_000 if label == "changed_linux_budget" else g1c.CAP_NS
        lines.append(f"G1C_USAGE label={label} sample={1000000 + index * 1000} cumulative={1000 + index * 100} "
                     f"window_start=0 window_consumed={1000 + index * 100} cap={cap} period=100000000 "
                     f"events=1 dropped=0 revision={revision}")
    lines.extend(("G1C_CPU_STAT_OBSERVATION usage_usec=1 before_ns=1600 after_ns=1700",
                  "G1C_REAL_CPU_OWNER_MATCH same_revision=2 changed_revision=3 restored_revision=4"))
    return ("\n".join(lines) + "\n").encode()


class VerdictTests(unittest.TestCase):
    def verdict(self, raw, code=33, timed_out=False):
        return g1c.evaluate_positive(raw, code, timed_out, INFO)["passed"]

    def test_complete_fixture_describes_the_oracle(self):
        self.assertTrue(self.verdict(valid_serial()))

    def test_transport_success_cannot_replace_guest_exit(self):
        for code in (None, 0, 1, 65, True):
            with self.subTest(code=code):
                self.assertFalse(self.verdict(valid_serial(), code))
        self.assertFalse(self.verdict(valid_serial(), 33, True))

    def test_every_security_marker_is_required_exactly_once(self):
        for marker in g1c.MARKERS:
            with self.subTest(marker=marker):
                raw = valid_serial()
                self.assertFalse(self.verdict(raw.replace((marker + "\n").encode(), b"", 1)))
                self.assertFalse(self.verdict(raw + (marker + "\n").encode()))

    def test_pid1_must_start_after_both_loader_checks(self):
        raw = valid_serial().replace((g1c.ACTIVATED + "\n").encode(), b"", 1)
        self.assertFalse(self.verdict(raw + (g1c.ACTIVATED + "\n").encode()))
        self.assertFalse(self.verdict(valid_serial().replace(b"bytes=8192", b"bytes=8193")))

    def test_no_missing_or_forged_vm_denial(self):
        for name in g1c.SEAL_CASES:
            original = f"G1C_SEAL_CASE name={name} result=PASS errno=1".encode()
            self.assertFalse(self.verdict(valid_serial().replace(original, original.replace(b"errno=1", b"errno=5"))))
        self.assertFalse(self.verdict(valid_serial().replace(b"G1C_SEAL_CASE name=boot_unmap", b"FAKE_SEAL_CASE name=boot_unmap")))

    def test_missing_duplicate_or_wrong_usage_payload_is_red(self):
        for label in g1c.USAGE_LABELS:
            original = next(line for line in valid_serial().splitlines() if line.startswith(f"G1C_USAGE label={label} ".encode()))
            self.assertFalse(self.verdict(valid_serial().replace(original + b"\n", b"")))
            self.assertFalse(self.verdict(valid_serial() + original + b"\n"))
        self.assertFalse(self.verdict(valid_serial().replace(b"cap=25000000", b"cap=50000000")))
        self.assertFalse(self.verdict(valid_serial().replace(b"events=1 dropped=0", b"events=1 dropped=2", 1)))

    def test_linux_budget_cannot_be_reported_by_an_unrelated_revision(self):
        self.assertFalse(self.verdict(valid_serial().replace(b"same_revision=2", b"same_revision=1")))
        self.assertFalse(self.verdict(valid_serial().replace(b"restored_revision=4", b"restored_revision=3")))
        self.assertFalse(self.verdict(valid_serial().replace(b"before_ns=1600", b"before_ns=1601")))

    def test_guest_failure_and_unexpected_records_are_red(self):
        for extra in (b"G1C_FAIL at=assertion\n", b"G1C_FORGED_SUCCESS\n", b"Kernel panic\n"):
            self.assertFalse(self.verdict(valid_serial() + extra))

    def test_rejection_requires_specific_loader_failure_and_no_resume(self):
        for reason in ("manifest-byte-mismatch", "truncated-snapshot"):
            raw = (f"[hepta-g1c] rejected initial image: {reason}\n"
                   "panicked at init: failed to run the init process\n").encode()
            self.assertTrue(g1c.evaluate_rejection(raw, 65, False, reason)["passed"])
            for changed in (b"Kernel panic\n", raw + b"G1C_INIT_STARTED pid=1\n",
                            raw + (g1c.ACTIVATED + "\n").encode(), raw * 2):
                self.assertFalse(g1c.evaluate_rejection(changed, 65, False, reason)["passed"])
            self.assertFalse(g1c.evaluate_rejection(raw, 33, False, reason)["passed"])
            self.assertFalse(g1c.evaluate_rejection(raw, 65, True, reason)["passed"])


if __name__ == "__main__":
    unittest.main()
