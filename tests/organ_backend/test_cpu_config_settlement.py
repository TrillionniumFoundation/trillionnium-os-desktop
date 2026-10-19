#!/usr/bin/env python3
"""Reject misleading CPU-config receipts; these are host verifier tests."""
import json
from pathlib import Path
import tempfile
import unittest

import run_cpu_config_settlement as runner


def transcript(period=100000, mode="same-value", cpu_ns=40_000_000):
    return (
        "ordinary kernel boot log\n"
        "CPU_CONFIG_SAMPLE label=unlimited wall_ns=250000000 cpu_ns=245000000 operations=500 checksum=1\n"
        f"CPU_CONFIG_PARAMETERS quota_us=1000 period_us={period} mode={mode} seconds=4\n"
        f"CPU_CONFIG_SAMPLE label={mode} wall_ns=4000000000 cpu_ns={cpu_ns} operations=100 checksum=2\n"
        "CPU_CONFIG_STAT\nusage_usec 40000\n"
        "CPU_CONFIG_COMPLETE\n"
        "CPU_CONFIG_PROCESS_EXIT status=0\n"
        "TRILLIONNIUM_A01_BOOT_OK\n"
    ).encode()


class GuestReceiptTests(unittest.TestCase):
    def evaluate(self, data, code=33, timed_out=False, period=100000, mode="same-value"):
        return runner.evaluate_serial(data, code, timed_out, period, mode)

    def test_four_declared_cases_accept_one_complete_execution(self):
        for period in (2000, 100000):
            for mode in ("read-only", "same-value"):
                with self.subTest(period=period, mode=mode):
                    cpu = 2_000_000_000 if period == 2000 else 40_000_000
                    result = self.evaluate(transcript(period, mode, cpu), period=period, mode=mode)
                    self.assertTrue(result["passed"])
                    self.assertEqual(result["probe_process_exit"], 0)

    def test_missing_or_nonzero_process_exit_is_not_inferred_from_boot(self):
        for replacement in (b"", b"CPU_CONFIG_PROCESS_EXIT status=2\n", b"CPU_CONFIG_PROCESS_EXIT status=137\n"):
            with self.subTest(replacement=replacement):
                data = transcript().replace(b"CPU_CONFIG_PROCESS_EXIT status=0\n", replacement)
                self.assertFalse(self.evaluate(data)["passed"])

    def test_prefixed_suffixed_or_duplicate_markers_are_rejected(self):
        markers = [line for line in transcript().splitlines() if line.startswith((b"CPU_CONFIG_", b"TRILLIONNIUM_"))]
        for marker in markers:
            for bad in (b"prefix " + marker, marker + b" suffix", marker + b"\n" + marker):
                with self.subTest(marker=marker, bad=bad):
                    self.assertFalse(self.evaluate(transcript().replace(marker, bad))["passed"])

    def test_completion_and_boot_must_follow_the_samples_and_exit(self):
        lines = transcript().splitlines()
        marker_positions = [i for i, line in enumerate(lines) if line.startswith((b"CPU_CONFIG_", b"TRILLIONNIUM_"))]
        for first, second in zip(marker_positions, marker_positions[1:]):
            changed = lines[:]
            changed[first], changed[second] = changed[second], changed[first]
            with self.subTest(first=first, second=second):
                self.assertFalse(self.evaluate(b"\n".join(changed))["passed"])

    def test_parameters_must_equal_the_selected_case(self):
        for old, new in ((b"quota_us=1000", b"quota_us=2000"),
                         (b"period_us=100000", b"period_us=2000"),
                         (b"mode=same-value", b"mode=read-only"), (b"seconds=4", b"seconds=1")):
            with self.subTest(old=old):
                self.assertFalse(self.evaluate(transcript().replace(old, new))["passed"])

    def test_zero_truncated_or_out_of_range_samples_are_rejected(self):
        for old, new in ((b"wall_ns=4000000000", b"wall_ns=0"),
                         (b"wall_ns=4000000000", b"wall_ns=3999999999"),
                         (b"wall_ns=250000000", b"wall_ns=249999999"),
                         (b"cpu_ns=40000000", b"cpu_ns=0"),
                         (b"operations=100", b"operations=0"),
                         (b"checksum=2", b"checksum=18446744073709551616"),
                         (b"checksum=2", b"checksum=2 trailing")):
            with self.subTest(old=old, new=new):
                self.assertFalse(self.evaluate(transcript().replace(old, new))["passed"])

    def test_low_unlimited_use_is_inconclusive_and_overquota_use_fails(self):
        low = transcript().replace(b"cpu_ns=245000000", b"cpu_ns=100000000")
        result = self.evaluate(low)
        self.assertTrue(result["guest_complete"])
        self.assertFalse(result["timing_valid"])
        self.assertFalse(result["passed"])
        self.assertFalse(self.evaluate(transcript(cpu_ns=49_000_000))["passed"])
        self.assertFalse(self.evaluate(transcript(2000, cpu_ns=2_100_000_000), period=2000)["passed"])

    def test_qemu_failure_timeout_or_panic_cannot_pass(self):
        for code in (0, 65, 124, None, True):
            with self.subTest(code=code):
                self.assertFalse(self.evaluate(transcript(), code=code)["passed"])
        self.assertFalse(self.evaluate(transcript(), timed_out=True)["passed"])
        for failure in (b"CPU_CONFIG_BLOCKED where=write errno=1", b"panicked at source.rs", b"Kernel panic"):
            with self.subTest(failure=failure):
                self.assertFalse(self.evaluate(transcript() + failure)["passed"])

    def test_excessive_serial_is_rejected(self):
        self.assertFalse(self.evaluate(transcript() + b"x" * runner.MAX_SERIAL_BYTES)["passed"])


class InputReceiptTests(unittest.TestCase):
    def test_each_recorded_input_is_checked_for_mutation_and_disappearance(self):
        names = ("kernel", "original_initramfs", "bios", "qemu", "compiler", "probe_source",
                 "runner", "archive_helper", "compiled_source", "probe", "injected_initramfs", "input_receipt")
        with tempfile.TemporaryDirectory() as directory:
            records = {}
            for name in names:
                path = Path(directory) / name
                data = name.encode()
                path.write_bytes(data)
                records[name] = {"path": str(path), "size": len(data), "sha256": runner.sha(data)}
            self.assertTrue(runner.verify_input_records(records)["inputs_unchanged"])
            for name in names:
                path = Path(records[name]["path"])
                original = path.read_bytes()
                for mutation in ("same-size", "missing"):
                    with self.subTest(name=name, mutation=mutation):
                        if mutation == "same-size":
                            path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
                        else:
                            path.unlink()
                        result = runner.verify_input_records(records)
                        self.assertFalse(result["inputs_unchanged"])
                        self.assertEqual(set(result["changed_inputs"]), {name})
                        json.dumps(result)
                        path.write_bytes(original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
