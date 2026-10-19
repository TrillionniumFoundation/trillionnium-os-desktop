#!/usr/bin/env python3
"""Adversarial tests for absent, skipped, divergent and matching guest evidence."""
import copy
import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[3] / "compat/linux/compare.py"
spec = importlib.util.spec_from_file_location("a04_diff", MODULE)
diff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diff)


def fixture():
    return {"binaries": {"dynamic": {"sha256": "a", "interpreter": "/lib/ld.so"}},
            "cases": {"threads": {"status": "pass", "exit_code": 0, "facts": {
                "threads_joined": 4, "futex_mismatch_errno": 11}},
                      "rust_tokio": {"status": "not_run", "reason": "toolchain missing"}}}


class Differential(unittest.TestCase):
    def test_missing_case_never_passes(self):
        ref = fixture()
        cand = copy.deepcopy(ref)
        cand["cases"].pop("threads")
        self.assertEqual(diff.compare(ref, cand)["verdict"], "incomplete")

    def test_linux_not_run_blocks_full_qualification(self):
        x = fixture()
        self.assertEqual(diff.compare(x, x)["verdict"], "incomplete")
        self.assertEqual(diff.compare(x, x, proven_only=True)["verdict"], "partial_match")

    def test_identical_facts_ignore_scheduler_order_not_observed(self):
        x = fixture()
        self.assertEqual(diff.compare(x, copy.deepcopy(x), proven_only=True)["matched"], ["threads"])

    def test_errno_change_is_failure(self):
        x = fixture()
        other = copy.deepcopy(x)
        other["cases"]["threads"]["facts"]["futex_mismatch_errno"] = 38
        self.assertEqual(diff.compare(x, other, proven_only=True)["verdict"], "fail")

    def test_binary_change_is_failure(self):
        x = fixture()
        other = copy.deepcopy(x)
        other["binaries"]["dynamic"]["sha256"] = "b"
        self.assertEqual(diff.compare(x, other, proven_only=True)["verdict"], "fail")

    def test_guest_failure_is_failure(self):
        x = fixture()
        other = copy.deepcopy(x)
        other["cases"]["threads"]["status"] = "fail"
        self.assertEqual(diff.compare(x, other, proven_only=True)["verdict"], "fail")

    def test_guest_evidence_required_even_if_cases_match(self):
        ref = {"binaries": fixture()["binaries"],
               "cases": {"threads": fixture()["cases"]["threads"]}}
        candidate = copy.deepcopy(ref)
        candidate["suite"] = "a04-linux-guest-differential"
        r = diff.compare(ref, candidate)
        self.assertEqual(r["verdict"], "incomplete")
        self.assertFalse(r["kernel_boot_verified"])
        self.assertEqual(r["blocked"][0]["case"], "kernel_boot")
        candidate["guest_execution_verified"] = True
        candidate["guest_compatibility_passed"] = True
        candidate["boot_evidence"] = {"a01_kernel_elf_sha256_matches": True,
                                      "a04_initramfs_sha256_matches": True,
                                      "qemu_exit_code": 33}
        verified = diff.compare(ref, candidate)
        self.assertEqual(verified["verdict"], "match")
        self.assertTrue(verified["kernel_boot_verified"])


if __name__ == "__main__":
    unittest.main()
