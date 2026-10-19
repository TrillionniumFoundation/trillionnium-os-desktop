"""Adversarial serial parsing tests: SYNTHETIC, never a QEMU guest pass."""
import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("a04_strict_serial_guest", HERE / "guest.py")
guest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guest)


class StrictSerial(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = json.loads((HERE / "baselines/linux-debian13-x86_64.json").read_text())
        cls.cases = [n for n, _, _ in guest.reference_elf_cases(cls.reference)]
        cls.manifest = {"cases": cls.cases, "a04_initramfs_sha256": "synthetic"}

    def lines(self):
        result = ["TRILLIONNIUM_A01_INIT_BEGIN", "TRILLIONNIUM_A01_BOOT_OK",
                  "TRILLIONNIUM_A04_WORKLOAD_BEGIN"]
        for name in self.cases:
            result.extend(("A04_CASE_BEGIN=" + name,
                           json.dumps(self.reference["cases"][name]["facts"], sort_keys=True),
                           "A04_CASE_END=" + name + ":0"))
        return result + ["TRILLIONNIUM_A04_RUNNER_STATUS=0",
                         "TRILLIONNIUM_A04_WORKLOAD_END"]

    def parse(self, lines):
        return guest.parse_serial("\n".join(lines) + "\n", self.reference, self.manifest,
                                  qemu_exit=33, kernel_sha=guest.A01_KERNEL_SHA,
                                  image_sha="synthetic")

    def test_synthetic_valid_reference_has_no_anomalies(self):
        result = self.parse(self.lines())
        self.assertTrue(result["guest_compatibility_passed"])
        self.assertEqual(result["counts"]["pass"], len(self.cases))
        self.assertFalse(result["boot_evidence"]["anomalies"])

    def test_marker_order_replay_panic_and_unexpected_lines_are_rejected(self):
        base = self.lines()
        poisoned = (
            base[:1] + [base[0]] + base[1:],                 # repeated A01 marker
            [base[1], base[0], *base[2:]],                  # out of order
            base[:3] + ["TRILLIONNIUM_A04_RUNNER_STATUS=0"] + base[3:],
            base + ["TRILLIONNIUM_A04_RUNNER_STATUS=0"],     # duplicate status
            base + ["Uncaught panic: post-smoke crash"],
            base[:3] + ["A04_CASE_BEGIN=unknown.fake"] + base[3:],
            base + ["A04_CASE_BEGIN=dynamic.smoke"],       # post-workload case
        )
        for index, lines in enumerate(poisoned):
            with self.subTest(index=index):
                result = self.parse(lines)
                self.assertFalse(result["guest_execution_verified"])
                self.assertFalse(result["guest_compatibility_passed"])
                self.assertTrue(result["boot_evidence"]["anomalies"])

    def test_duplicate_json_key_and_nonfinite_numbers_are_not_accepted(self):
        base = self.lines()
        marker = "A04_CASE_BEGIN=dynamic.smoke"
        offset = base.index(marker) + 1
        for payload in ('{"ok":false,"ok":true}', '{"ok":true,"value":NaN}'):
            with self.subTest(payload=payload):
                corrupted = list(base)
                corrupted[offset] = payload
                result = self.parse(corrupted)
                self.assertFalse(result["guest_compatibility_passed"])
                self.assertEqual(result["cases"]["dynamic.smoke"]["status"], "fail")
                self.assertTrue(result["boot_evidence"]["anomalies"])


    def test_warning_or_loader_error_mixed_with_correct_json_cannot_pass(self):
        lines = self.lines()
        start = lines.index("A04_CASE_BEGIN=dynamic.smoke")
        for extra in ("error: unexpected loader fault", "{not valid json}"):
            with self.subTest(extra=extra):
                altered = list(lines)
                altered.insert(start + 1, extra)
                result = self.parse(altered)
                self.assertFalse(result["guest_execution_verified"])
                self.assertFalse(result["guest_compatibility_passed"])
                self.assertIn("unexpected or ambiguous guest case output",
                              result["boot_evidence"]["anomalies"])

if __name__ == "__main__":
    unittest.main()
