#!/usr/bin/python3 -I
"""Offline state/fd-scope controls only. Never accesses real host sysfs."""
from pathlib import Path
import importlib.util
import os
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("pm_trial", Path(__file__).with_name("pm_control_trial.py"))
pm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm)


class FakeClock:
    value = 0.0

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class FakeDevice:
    def __init__(self, control="auto"):
        self.control = control
        self.writes = []
        self.snapshots = 0
        self.on_snapshot = None
        self.fail_on_after_apply = False
        self.disappeared = False
        self.replacement_control = "auto"
        self.fail_power_reads_after_on = False
        self.delay_ms = "2000"

    def snapshot(self):
        self.snapshots += 1
        if self.on_snapshot:
            self.on_snapshot(self)
        if self.disappeared:
            raise pm.Refused("DEVICE_OR_CONTROL_GENERATION_CHANGED")
        if self.fail_power_reads_after_on and self.writes:
            raise OSError("unrelated PM diagnostic counter unavailable")
        return {"control": self.control, "power": {"runtime_status": "active",
                "runtime_suspended_time": "0", "autosuspend_delay_ms": self.delay_ms}}

    def control_value(self):
        if self.disappeared:
            raise pm.Refused("DEVICE_OR_CONTROL_GENERATION_CHANGED")
        return self.control

    def store(self, value):
        if self.disappeared:
            raise pm.Refused("DEVICE_OR_CONTROL_GENERATION_CHANGED")
        self.writes.append(value)
        self.control = value
        if value == "on" and self.fail_on_after_apply:
            raise InterruptedError("write outcome unknown after applying on")
        return len(value) + 1


class TrialTests(unittest.TestCase):
    def run_fake(self, device, emit=lambda kind, data: None, sleep=None):
        clock = FakeClock()
        return pm.run_trial(device, emit, pm.SignalState(), clock=clock.now,
                            sleep=clock.sleep if sleep is None else sleep,
                            bootclock=clock.now)

    def test_complete_30_second_observation_restores_once(self):
        d = FakeDevice()
        r = self.run_fake(d)
        self.assertEqual(d.writes, ["on", "auto"])
        self.assertEqual(r["observed_seconds"], 30.0)
        self.assertTrue(r["observation_complete"] and r["original_value_verified"])
        self.assertEqual(r["state"], "ON_WINDOW_OBSERVED_ORIGINAL_VALUE_VERIFIED")
        self.assertFalse(r["causality_established"] or r["production_ready"])

    def test_target_already_on_does_not_write(self):
        d = FakeDevice("on")
        r = self.run_fake(d)
        self.assertEqual(d.writes, [])
        self.assertEqual(r["state"], "STOPPED_WITHOUT_POWER_WRITE")

    def test_delay_outside_observation_window_is_zero_write(self):
        for delay in ("30000", "60000"):
            with self.subTest(delay=delay):
                d = FakeDevice()
                d.delay_ms = delay
                r = self.run_fake(d)
                self.assertEqual(d.writes, [])
                self.assertIn("NO_WRITE_OUTSIDE_OBSERVATION_WINDOW", r["error"])
                self.assertEqual(r["state"], "STOPPED_WITHOUT_POWER_WRITE")

    def test_generation_replacement_never_receives_restore(self):
        d = FakeDevice()
        def disappear(d):
            if d.snapshots >= 4:
                d.disappeared = True
        d.on_snapshot = disappear
        r = self.run_fake(d)
        self.assertEqual(d.writes, ["on"])
        self.assertEqual(d.replacement_control, "auto")
        self.assertEqual(r["restore_write_attempts"], 0)
        self.assertFalse(r["original_value_verified"])
        self.assertTrue(r["outcome_unknown"])

    def test_uncertain_on_write_is_not_repeated_and_restore_runs(self):
        d = FakeDevice()
        d.fail_on_after_apply = True
        r = self.run_fake(d)
        self.assertEqual(d.writes, ["on", "auto"])
        self.assertTrue(r["original_value_verified"])
        self.assertTrue(r["outcome_unknown"])
        self.assertFalse(r["observation_complete"])

    def test_interrupt_and_cleanup_journal_failure_still_restore(self):
        d = FakeDevice()
        def interrupt(seconds):
            raise InterruptedError("cancel during observation")
        def fail_cleanup_log(kind, data):
            if kind.startswith("restore-"):
                raise OSError("disk full")
        r = self.run_fake(d, fail_cleanup_log, interrupt)
        self.assertEqual(d.writes, ["on", "auto"])
        self.assertTrue(r["original_value_verified"])
        self.assertEqual(len(r["cleanup_evidence_errors"]), 2)
        self.assertEqual(r["state"], "CONTRAST_INCOMPLETE_RESTORED")

    def test_external_return_to_auto_is_not_overwritten_or_passed(self):
        d = FakeDevice()
        def change(d):
            if d.snapshots >= 4:
                d.control = "auto"
        d.on_snapshot = change
        r = self.run_fake(d)
        self.assertEqual(d.writes, ["on"])
        self.assertTrue(r["original_value_verified"])
        self.assertFalse(r["observation_complete"])
        self.assertEqual(r["restore_write_attempts"], 0)

    def test_diagnostic_counter_failure_does_not_block_restoration(self):
        d = FakeDevice()
        d.fail_power_reads_after_on = True
        r = self.run_fake(d)
        self.assertEqual(d.writes, ["on", "auto"])
        self.assertTrue(r["original_value_verified"])
        self.assertFalse(r["observation_complete"])

    def test_retained_fd_write_cannot_retarget_replaced_path(self):
        # This checks ordinary Linux FD scope in a disposable regular file,
        # not kernfs callback behavior or the real camera's PM implementation.
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            root = Path(tmp)
            current = root / "control"
            current.write_bytes(b"auto\n")
            fd = os.open(current, os.O_RDWR | os.O_NOFOLLOW)
            try:
                current.rename(root / "old-control")
                current.write_bytes(b"auto\n")
                self.assertEqual(pm.single_store(fd, "on"), 3)
                self.assertEqual(current.read_bytes(), b"auto\n")
                self.assertEqual((root / "old-control").read_bytes()[:3], b"on\n")
            finally:
                os.close(fd)


if __name__ == "__main__":
    unittest.main(verbosity=2)
