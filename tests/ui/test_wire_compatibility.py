#!/usr/bin/env python3
"""Refusal boundaries for the narrowly reviewed actual-output exception."""
import importlib.util
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
DIRECTORY = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("wire_gate", DIRECTORY / "verify_wire_compatibility.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class WireCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = (DIRECTORY / "wire-compatibility-v1.json").read_bytes()
        cls.aligned = (DIRECTORY / "wire-compatibility-aligned-v1.json").read_bytes()

    def test_actual_original_and_aligned_execution_outputs(self):
        report = gate.compare(self.original, self.aligned)
        self.assertTrue(report["passed"])
        self.assertFalse(report["exact_stdout_bytes_equal"])
        self.assertEqual(report["exact_case_values"], 51)
        self.assertEqual(len(report["allowed_observer_exponent_changes"]), 1)

    def test_byte_identical_output_is_also_compatible(self):
        self.assertTrue(gate.compare(self.original, self.original)["exact_stdout_bytes_equal"])

    def test_changing_the_finite_value_is_refused(self):
        changed = self.aligned.replace(b"3.4028235e+38", b"3.4028234e+38", 1)
        self.assertNotEqual(changed, self.aligned)
        with self.assertRaises(ValueError):
            gate.compare(self.original, changed)

    def test_the_observed_rounding_regression_is_refused(self):
        old = b'"response/parse-f32/above-half-ulp-at-one": "3f800000"'
        changed = self.aligned.replace(old, old.replace(b"3f800000", b"3f800001"), 1)
        self.assertNotEqual(changed, self.aligned)
        with self.assertRaises(ValueError):
            gate.compare(self.original, changed)

    def test_the_observed_overflow_regression_is_refused(self):
        old = b'"response/parse-f32/f32-overflow": "7f800000"'
        changed = self.aligned.replace(old, old.replace(b"7f800000", b"rejected"), 1)
        self.assertNotEqual(changed, self.aligned)
        with self.assertRaises(ValueError):
            gate.compare(self.original, changed)

    def test_unrelated_whitespace_is_not_canonicalized(self):
        with self.assertRaises(ValueError):
            gate.compare(self.original, self.aligned.replace(b"  ", b" ", 1))

    def test_duplicate_or_extra_outer_cases_are_refused(self):
        for extra in (b'"unexpected":"new",', b'"request/snapshot":"duplicate",'):
            with self.assertRaises(ValueError):
                gate.compare(self.original, self.aligned.replace(b"{", b"{" + extra, 1))

    def test_modified_original_cannot_redefine_the_exception(self):
        changed = self.original.replace(b"3.4028235e38", b"3.4028234e38", 1)
        with self.assertRaises(ValueError):
            gate.compare(changed, self.aligned)


if __name__ == "__main__":
    unittest.main()
