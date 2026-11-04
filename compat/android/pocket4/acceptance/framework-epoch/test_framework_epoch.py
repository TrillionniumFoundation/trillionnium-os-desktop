#!/usr/bin/env python3
"""Real Linux process tests: no fabricated /proc trees or mocked identities."""
import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from framework_epoch import (EpochError, capture_processes, execute_bound,
                             process_identity, require_unchanged)


class EpochTests(unittest.TestCase):
    def setUp(self):
        self.children = []

    def tearDown(self):
        for child in self.children:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=5)
            if child.stdin:
                child.stdin.close()
            if child.stdout:
                child.stdout.close()

    def child(self, source="import time; print('ready',flush=True); time.sleep(60)"):
        proc = subprocess.Popen([sys.executable, "-u", "-c", source], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, text=True)
        self.children.append(proc)
        self.assertEqual(proc.stdout.readline().strip(), "ready")
        return proc

    def freeze(self, proc):
        return capture_processes({"retained_parent": os.getpid(), "framework_child": proc.pid})

    def test_stable_epoch_runs_exactly_once(self):
        snapshot = self.freeze(self.child())
        calls = []
        self.assertEqual(execute_bound(snapshot, lambda: calls.append(1) or 42), 42)
        self.assertEqual(calls, [1])

    def test_retained_parent_does_not_hide_child_restart(self):
        child = self.child()
        before = self.freeze(child)
        child.terminate(); child.wait(timeout=5)
        after = self.freeze(self.child())
        self.assertEqual(before["binding"]["processes"]["retained_parent"],
                         after["binding"]["processes"]["retained_parent"])
        self.assertNotEqual(before["sha256"], after["sha256"])
        calls = []
        with self.assertRaises(EpochError) as failure:
            execute_bound(before, lambda: calls.append(1))
        self.assertEqual(calls, [])
        self.assertFalse(failure.exception.action_attempted)
        self.assertFalse(failure.exception.automatic_retry)

    def test_disappeared_process_rejects_before_action(self):
        child = self.child(); snapshot = self.freeze(child)
        child.terminate(); child.wait(timeout=5)
        with self.assertRaises(EpochError) as failure:
            require_unchanged(snapshot)
        self.assertFalse(failure.exception.outcome_unknown)

    def test_exec_in_same_pid_and_start_time_changes_identity(self):
        child = self.child("import os,sys; print('ready',flush=True); sys.stdin.readline(); os.execv('/usr/bin/sleep',['sleep','60'])")
        snapshot = self.freeze(child)
        previous = process_identity(child.pid)
        child.stdin.write("exec\n"); child.stdin.flush()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            current = process_identity(child.pid)
            if current["executable"] != previous["executable"]:
                break
            time.sleep(0.01)
        self.assertEqual(current["host_pid"], previous["host_pid"])
        self.assertEqual(current["start_ticks"], previous["start_ticks"])
        self.assertNotEqual(current["executable"], previous["executable"])
        with self.assertRaises(EpochError):
            require_unchanged(snapshot)

    def test_comm_main_and_parentheses_do_not_break_stat_parsing(self):
        child = self.child("import ctypes,time; ctypes.CDLL(None).prctl(15,b'main ) ( test',0,0,0); print('ready',flush=True); time.sleep(60)")
        snapshot = self.freeze(child)
        require_unchanged(snapshot)
        self.assertEqual(snapshot["binding"]["processes"]["framework_child"]["parent_host_pid"], os.getpid())

    def test_restart_during_action_is_unknown_and_not_replayed(self):
        child = self.child(); snapshot = self.freeze(child); calls = []
        def action():
            calls.append(1); child.terminate(); child.wait(timeout=5)
            self.child()
            return "transport-acknowledged"
        with self.assertRaises(EpochError) as failure:
            execute_bound(snapshot, action)
        self.assertEqual(calls, [1])
        self.assertTrue(failure.exception.action_attempted)
        self.assertTrue(failure.exception.outcome_unknown)
        self.assertFalse(failure.exception.automatic_retry)

    def test_timeout_preserved_without_retry_when_epoch_stable(self):
        snapshot = self.freeze(self.child()); calls = []
        def action():
            calls.append(1)
            subprocess.run(["/usr/bin/sleep", "2"], timeout=0.05, check=True)
        with self.assertRaises(subprocess.TimeoutExpired):
            execute_bound(snapshot, action)
        self.assertEqual(calls, [1])
        require_unchanged(snapshot)

    def test_timeout_with_restart_keeps_original_error_chain(self):
        child = self.child(); snapshot = self.freeze(child); calls = []
        def action():
            calls.append(1); child.terminate(); child.wait(timeout=5)
            subprocess.run(["/usr/bin/sleep", "2"], timeout=0.05, check=True)
        with self.assertRaises(EpochError) as failure:
            execute_bound(snapshot, action)
        self.assertTrue(failure.exception.outcome_unknown)
        self.assertIsInstance(failure.exception.__cause__, subprocess.TimeoutExpired)
        self.assertEqual(calls, [1])

    def test_modified_document_is_rejected(self):
        snapshot = self.freeze(self.child())
        snapshot["binding"]["processes"]["framework_child"]["start_ticks"] += 1
        with self.assertRaises(EpochError) as failure:
            require_unchanged(snapshot)
        self.assertEqual(failure.exception.code, "INVALID_EPOCH_DOCUMENT")

    def test_serialized_epoch_retains_binding(self):
        snapshot = self.freeze(self.child())
        restored = json.loads(json.dumps(snapshot))
        require_unchanged(restored)
        self.assertEqual(execute_bound(restored, lambda: "same"), "same")


if __name__ == "__main__":
    unittest.main(verbosity=2)
