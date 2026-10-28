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
    def test_empty_reference_cannot_match_even_in_proven_only_mode(self):
        for proven_only in (False, True):
            self.assertEqual(diff.compare({}, {}, proven_only=proven_only)['verdict'],
                             'incomplete')

    def test_no_passed_reference_cannot_report_partial_match(self):
        report = {'cases': {'threads': {'status': 'not_run'}}}
        self.assertEqual(diff.compare(report, report, proven_only=True)['verdict'],
                         'incomplete')

    def test_missing_or_empty_binary_inventory_cannot_match(self):
        for side in ('reference', 'candidate', 'both'):
            for missing in (False, True):
                for proven_only in (False, True):
                    with self.subTest(side=side, missing=missing, proven_only=proven_only):
                        reference, candidate = fixture(), fixture()
                        for report in (reference, candidate):
                            del report['cases']['rust_tokio']
                        selected = ([reference, candidate] if side == 'both' else
                                    [reference] if side == 'reference' else [candidate])
                        for report in selected:
                            if missing:
                                del report['binaries']
                            else:
                                report['binaries'] = {}
                        self.assertEqual(diff.compare(reference, candidate,
                                                      proven_only=proven_only)['verdict'],
                                         'incomplete')

    def test_pass_requires_recorded_exit_and_facts_on_both_sides(self):
        for field in ('exit_code', 'facts'):
            for side in ('reference', 'candidate', 'both'):
                with self.subTest(field=field, side=side):
                    reference, candidate = fixture(), fixture()
                    if side in ('reference', 'both'):
                        del reference['cases']['threads'][field]
                    if side in ('candidate', 'both'):
                        del candidate['cases']['threads'][field]
                    self.assertNotIn(diff.compare(reference, candidate, proven_only=True)['verdict'],
                                     ('match', 'partial_match'))

    def test_facts_compare_json_types_recursively(self):
        for original, changed in ((True, 1), (1, True), (1, 1.0),
                                  ([{'ok': True}], [{'ok': 1}])):
            with self.subTest(original=original, changed=changed):
                reference, candidate = fixture(), fixture()
                reference['cases']['threads']['facts'] = {'value': original}
                candidate['cases']['threads']['facts'] = {'value': changed}
                self.assertEqual(diff.compare(reference, candidate, proven_only=True)['verdict'],
                                 'fail')

    def test_boolean_exit_code_is_not_integer_exit_code(self):
        reference, candidate = fixture(), fixture()
        candidate['cases']['threads']['exit_code'] = False
        self.assertEqual(diff.compare(reference, candidate, proven_only=True)['verdict'], 'fail')

    def test_recorded_static_elf_and_nested_facts_still_match(self):
        reference = fixture()
        reference['binaries']['dynamic']['interpreter'] = None
        reference['cases']['threads']['facts'] = {'nested': [False, 0, None, {'count': 4}]}
        candidate = copy.deepcopy(reference)
        self.assertEqual(diff.compare(reference, candidate, proven_only=True)['verdict'],
                         'partial_match')

    def test_binary_identity_fields_cannot_be_absent_on_both_sides(self):
        for field in ('sha256', 'interpreter'):
            with self.subTest(field=field):
                report = fixture()
                del report['binaries']['dynamic'][field]
                self.assertNotIn(diff.compare(report, report, proven_only=True)['verdict'],
                                 ('match', 'partial_match'))

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
