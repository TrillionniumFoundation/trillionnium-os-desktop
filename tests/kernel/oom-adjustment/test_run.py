#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Parser-only rejection tests; never executes the C binary or a guest."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("_owned_oom_test_runner", HERE / "run.py")
post = importlib.util.module_from_spec(spec)
spec.loader.exec_module(post)


class OomGuestOracle(unittest.TestCase):
    def sample(self):
        rows = [{"case": "oom.setup", "passed": True}]
        for stage, values in post.WRITES.items():
            for value, error in values:
                rows.append({"observation": "write", "stage": stage, "pid": 2,
                             "value": value, "rc": -1 if error else len(str(value)) + 1,
                             "errno": error, "expected_errno": error})
            rows.append({"case": "oom." + stage, "passed": True})
        return rows

    def evaluate(self, rows, **updates):
        base = {"passed": True, "qemu_exit": 33, "timed_out": False, "excessive_output": False}
        base.update(updates)
        raw = ("\n".join(map(json.dumps, rows)) + "\n").encode()
        return post.evaluate(raw, base)

    def test_exact_fixture_facts_pass(self):
        result = self.evaluate(self.sample())
        self.assertTrue(result["passed"])
        self.assertEqual(result["actual_cases"], 12)
        self.assertEqual(result["actual_observations"], result["expected_observations"])

    def test_each_missing_or_duplicate_case_is_refused(self):
        sample = self.sample()
        for index, row in enumerate(sample):
            if "case" in row:
                for changed in (sample[:index] + sample[index + 1:], sample + [row]):
                    with self.assertRaisesRegex(ValueError, "case inventory"):
                        self.evaluate(changed)

    def test_case_claiming_success_cannot_hide_wrong_errno_or_byte_count(self):
        for error in (True, False):
            changed = self.sample()
            row = next(r for r in changed if "observation" in r and bool(r["expected_errno"]) == error)
            row["errno" if error else "rc"] += 1
            self.assertFalse(self.evaluate(changed)["passed"])

    def test_each_missing_or_duplicate_syscall_fact_is_rejected(self):
        sample = self.sample()
        for index, row in enumerate(sample):
            if "observation" in row:
                for changed in (sample[:index] + sample[index + 1:], sample + [row]):
                    self.assertFalse(self.evaluate(changed)["passed"])

    def test_swapped_stage_order_and_forged_expected_errno_are_rejected(self):
        for action in ("swap", "forge"):
            changed = self.sample()
            observations = [r for r in changed if r.get("stage") == "uid_floor"]
            if action == "swap":
                observations[0]["value"], observations[1]["value"] = observations[1]["value"], observations[0]["value"]
            else:
                observations[2].update(expected_errno=0, errno=0, rc=3)
            self.assertFalse(self.evaluate(changed)["passed"])

    def test_failed_case_or_base_result_cannot_pass(self):
        changed = self.sample()
        changed[0]["passed"] = False
        self.assertFalse(self.evaluate(changed)["passed"])
        for update in ({"passed": False}, {"qemu_exit": 65}, {"timed_out": True}, {"excessive_output": True}):
            self.assertFalse(self.evaluate(self.sample(), **update)["passed"])

    def test_malformed_rows_are_refused(self):
        for key, value in (("pid", True), ("pid", 1), ("rc", "3"), ("observation", "other"), ("stage", "foreign")):
            changed = self.sample()
            next(r for r in changed if "observation" in r)[key] = value
            with self.assertRaises(ValueError):
                self.evaluate(changed)
        changed = copy.deepcopy(self.sample())
        changed[0]["passed"] = 1
        with self.assertRaisesRegex(ValueError, "nonboolean"):
            self.evaluate(changed)


if __name__ == "__main__":
    unittest.main()
