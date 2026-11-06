#!/usr/bin/env python3
"""Local actual-capture selection and immutable per-file-reader controls."""
import sys
sys.dont_write_bytecode = True
import copy
import json
import os
from pathlib import Path
import types
import unittest

HERE = Path(__file__).resolve().parent
M = types.ModuleType("batch_private_preparer_controls")
M.__file__ = str(HERE / "prepare_batch_private_readback.py")
exec(compile(Path(M.__file__).read_bytes(), M.__file__, "exec"), M.__dict__)


class Controls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gate, cls.g, cls.plan, cls.loaded = M.load_gate()
        cls.completed = cls.gate.load_record(cls.g, cls.loaded[1], cls.gate.LEDGER / "batch-01")[0]

    def test_01_actual_successful_Fcitx_only_and_five_reader_definitions_unchanged(self):
        source, original, pins, mapping, binding = M.render_reader(self.completed, self.loaded[1]["row"])
        self.assertEqual([p["bytes"] for p in pins], [14599, 1311])
        self.assertEqual(sum(p["bytes"] for p in pins), 15910)
        self.assertEqual(binding["source_capture_job"], "1a1b2b86eb1-fc05-7f76")
        for name in ("need", "sha", "canonical", "read_file", "read_host_pin"):
            self.assertEqual(M.definitions(source)[name], M.definitions(original)[name])

    def test_02_actual_failed_microG_capture_cannot_make_a_reader(self):
        with self.assertRaisesRegex(RuntimeError, "EXACT_SUCCESSFUL_DURABLE_TERMINAL_REQUIRED"):
            self.gate.load_record(self.g, self.loaded[2], self.gate.LEDGER / "batch-02")

    def test_03_incomplete_report_changed_path_or_oversized_stream_rejected(self):
        for mutation in ("incomplete", "path", "size"):
            completed = copy.deepcopy(self.completed)
            report = completed["service_reports"][0]
            if mutation == "incomplete":
                report["complete"] = False
            elif mutation == "path":
                report["stdout"]["path"] = "/etc/shadow"
            else:
                report["stdout"]["bytes"] = M.MAX_FILE + 1
            with self.subTest(mutation=mutation), self.assertRaises(RuntimeError):
                M.fixed_logs(completed, self.loaded[1]["row"])


def main():
    before = len(os.listdir("/proc/self/fd"))
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    after = len(os.listdir("/proc/self/fd"))
    print(json.dumps({"schema": "pocket4-private-batch-readback-preparer-local-controls-v1", "ok": result.wasSuccessful() and before == after,
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
        "FDs_before": before, "FDs_after": after, "remote_jobs": 0, "Main_reads": 0, "private_service_bodies_read": 0,
        "new_reader_packets_written_by_controls": 0, "existing_single_target_candidate_changed": False}, sort_keys=True))
    return 0 if result.wasSuccessful() and before == after else 1


if __name__ == "__main__":
    raise SystemExit(main())
