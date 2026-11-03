# SPDX-License-Identifier: MPL-2.0
"""Reject incomplete runs and unrelated failures; these are host oracle tests."""
import errno
import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("unix_dontwait_check", Path(__file__).with_name("check.py"))
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def observations(old=False):
    result = []
    for kind, case in checker.EXPECTED:
        item = dict(suite="unix_dontwait", socket=kind, case=case, passed=True,
                    **{"return": 1, "errno": 0, "elapsed_us": 0})
        if case in ("empty_recv_dontwait", "full_send_dontwait", "ordinary_recv_timeout"):
            item.update({"return": -1, "errno": errno.EAGAIN,
                         "elapsed_us": 750000 if case == "ordinary_recv_timeout" else 100})
        if case in ("ordinary_recv_wakeup", "ordinary_send_wakeup"):
            item["elapsed_us"] = 50000
            item["return"] = 1 if case == "ordinary_recv_wakeup" else 1024
        if case == "wakeup_payload_readback":
            item["return"] = 1024
        if "shared_flags" in case:
            item.update({"return": 2, "errno": 2})
        if "child_reaped" in case:
            item["return"] = 123
        if old and (kind, case) in checker.OLD_BLOCKING:
            item.update(passed=False, elapsed_us=750000)
        result.append(item)
    result.append(dict(suite="unix_dontwait", summary=True, checks=33, failures=4 if old else 0))
    return result


def serial(items, old=False):
    lines = [json.dumps(item, separators=(",", ":")) for item in items]
    lines += [f"UNIX_DONTWAIT_PROBE_EXIT={1 if old else 0}", "TRILLIONNIUM_A01_BOOT_OK"]
    return ("\n".join(lines) + "\n").encode()


class OracleTests(unittest.TestCase):
    def check(self, items, old=False, **kwargs):
        return checker.check(serial(items, old), 33, guest=True, expect_old_blocking=old, **kwargs)

    def test_complete_positive(self):
        self.assertTrue(self.check(observations())["product_passed"])

    def test_precise_old_blocking_is_counterexample_only(self):
        result = self.check(observations(True), True)
        self.assertTrue(result["counterexample_accepted"])
        self.assertFalse(result["product_passed"])
        self.assertFalse(checker.check(serial(observations(True), True), 33, guest=True)["passed"])

    def test_partial_or_duplicate_inventory_rejected(self):
        for items in (observations()[1:], observations() + [observations()[0]]):
            self.assertFalse(self.check(items)["passed"])

    def test_timeout_is_not_counterexample(self):
        self.assertFalse(self.check(observations(True), True, timed_out=True)["passed"])
        self.assertFalse(checker.check(serial(observations(True), True), 65,
                                      guest=True, expect_old_blocking=True)["passed"])

    def test_wrong_error_is_not_counterexample(self):
        items = observations(True)
        items[5]["errno"] = errno.EINVAL
        self.assertFalse(self.check(items, True)["passed"])

    def test_failed_flag_without_measured_delay_rejected(self):
        items = observations(True)
        items[5]["elapsed_us"] = 100
        self.assertFalse(self.check(items, True)["passed"])

    def test_shared_nonblocking_or_unreaped_child_rejected(self):
        for index, change in ((1, {"return": 2050, "errno": 2050}), (4, {"errno": 9})):
            items = observations()
            items[index].update(change)
            self.assertFalse(self.check(items)["passed"])

    def test_unrelated_failure_cannot_hide_in_negative_summary(self):
        items = observations(True)
        items[8]["passed"] = False
        items[-1]["failures"] = 5
        self.assertFalse(self.check(items, True)["passed"])

    def test_wrong_exit_and_repeated_boot_rejected(self):
        data = serial(observations())
        for changed in (data.replace(b"PROBE_EXIT=0", b"PROBE_EXIT=1"),
                        data + b"TRILLIONNIUM_A01_BOOT_OK\n"):
            self.assertFalse(checker.check(changed, 33, guest=True)["passed"])

    def test_incomplete_alarm_not_accepted(self):
        data = serial(observations(True)[:5], True).replace(b"PROBE_EXIT=1", b"PROBE_EXIT=142")
        self.assertFalse(checker.check(data, 33, guest=True, expect_old_blocking=True)["passed"])

    def test_interleaved_record_rejected(self):
        data = serial(observations()).replace(b'{"suite":', b'kernel warning {"suite":', 1)
        self.assertFalse(checker.check(data, 33, guest=True)["passed"])

    def test_boolean_numeric_fields_rejected(self):
        items = observations()
        items[0]["elapsed_us"] = True
        self.assertFalse(self.check(items)["passed"])


if __name__ == "__main__":
    unittest.main()
