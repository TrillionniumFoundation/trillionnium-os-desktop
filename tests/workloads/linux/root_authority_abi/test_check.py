# SPDX-License-Identifier: MPL-2.0
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("root_abi_checker", Path(__file__).with_name("check.py"))
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)
GOOD = b"\n".join(CHECKER.RECORDS + [CHECKER.SUMMARY]) + b"\n"
GUEST = b"kernel boot\n" + GOOD + CHECKER.EXIT + b"\n" + CHECKER.BOOT + b"\n"


class RootAbiOracleTests(unittest.TestCase):
    def test_complete_linux(self):
        result = CHECKER.check(GOOD, 0)
        self.assertTrue(result["passed"])
        self.assertEqual(result["checks"], 27)
        for key in ("original_writer_executed", "persistent_cpu_qualified", "recovery_qualified", "g2_complete"):
            self.assertIs(result[key], False)

    def test_complete_guest(self):
        self.assertTrue(CHECKER.check(GUEST, 33, guest=True)["passed"])

    def test_failed_actual_child(self):
        self.assertFalse(CHECKER.check(GOOD + b"ROOT_ABI_FAIL name=child_pidfd line=1 errno=38 child=1\n", 0)["passed"])

    def test_inner_alarm_not_accepted(self):
        self.assertFalse(CHECKER.check(GOOD + b"ROOT_ABI_TIMEOUT\n", 124)["passed"])

    def test_outer_timeout_not_accepted(self):
        self.assertFalse(CHECKER.check(GOOD, None, True)["passed"])

    def test_missing_or_duplicate_case(self):
        for modified in (GOOD.replace(CHECKER.RECORDS[0] + b"\n", b""), CHECKER.RECORDS[0] + b"\n" + GOOD):
            self.assertFalse(CHECKER.check(modified, 0)["passed"])

    def test_case_order(self):
        modified = b"\n".join(list(reversed(CHECKER.RECORDS)) + [CHECKER.SUMMARY]) + b"\n"
        self.assertFalse(CHECKER.check(modified, 0)["passed"])

    def test_missing_summary(self):
        self.assertFalse(CHECKER.check(GOOD.replace(CHECKER.SUMMARY, b""), 0)["passed"])

    def test_scope_cannot_be_upgraded(self):
        self.assertFalse(CHECKER.check(GOOD.replace(b"g2_complete=false", b"g2_complete=true"), 0)["passed"])

    def test_wrong_exit(self):
        self.assertFalse(CHECKER.check(GOOD, 1)["passed"])
        self.assertFalse(CHECKER.check(GUEST, 0, guest=True)["passed"])

    def test_marker_duplicates_and_order(self):
        for modified in (GUEST + CHECKER.EXIT + b"\n", GUEST + CHECKER.BOOT + b"\n",
                         CHECKER.BOOT + b"\n" + GOOD + CHECKER.EXIT + b"\n"):
            self.assertFalse(CHECKER.check(modified, 33, guest=True)["passed"])

    def test_trusted_profile_not_ordinary(self):
        for prefix in (b"[hepta-g1c]", b"[hepta-g1d]", b"[hepta-g2]"):
            self.assertFalse(CHECKER.check(prefix + b" initial control activated\n" + GUEST, 33, guest=True)["passed"])


if __name__ == "__main__":
    unittest.main()
