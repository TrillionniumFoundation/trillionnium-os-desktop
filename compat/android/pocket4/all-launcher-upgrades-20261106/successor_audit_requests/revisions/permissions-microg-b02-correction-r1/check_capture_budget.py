#!/usr/bin/env python3
"""Offline original-failure checks and real owned HOST child budget controls.

The synthetic writer is Python in this local executor. Its trailing arguments
exercise the fixed budget selector only; it never enters an Android namespace.
"""
import sys
sys.dont_write_bytecode = True
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import types
import unittest

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
OLD = PROJECT / "successor_audit_requests/effective_permissions_45_capture_r1/batch-02"
W = types.ModuleType("independent_microg_local_control")
W.__file__ = str(HERE / "observe_current_services.py")
exec(compile((HERE / "observe_current_services.py").read_bytes(), W.__file__, "exec"), W.__dict__)


def defs(raw):
    source = raw.decode()
    return {n.name: ast.get_source_segment(source, n) for n in ast.parse(source).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}


class Controls(unittest.TestCase):
    def test_01_actual_failed_prefix_is_preserved_and_not_whole_service_output(self):
        raw = {key: (HERE / ("inputs/original-b02-" + key.replace("_", "-") + ".json")).read_bytes() for key in W.FAILURE_INPUTS}
        observed = W.verify_original_failure(raw)
        self.assertEqual(observed["job_id"], "1a1b2be17ec-fc05-7f8b")
        self.assertEqual(observed["inner_first_cause"], "CHILD_OUTPUT_BOUND")
        self.assertEqual(observed["original_worker_error_label"], "HOST_COMMAND_TIMEOUT")
        self.assertFalse(observed["service_capture_complete"])
        changed = dict(raw)
        value = json.loads(raw["artifact"])
        value["android_commands"][1]["complete"] = True
        changed["artifact"] = W.canonical(value)
        with self.assertRaisesRegex(RuntimeError, "ORIGINAL_FAILURE_INPUT_PIN_CHANGED"):
            W.verify_original_failure(changed)

    def owned_writer(self, stream, size, *, expanded, suffix=None):
        suffix = W.CORRECTION_COMMANDS[1] if suffix is None else suffix
        source = "import os; data=memoryview(b'x'*%d);\nwhile data:\n n=os.write(%d,data);data=data[n:]\n" % (size, 1 if stream == "stdout" else 2)
        argv = [sys.executable, "-I", "-B", "-c", source, *suffix]
        return W.held_bounded_child(argv, 5, 262144, (), {"PATH": "/usr/bin:/bin", "LANG": "C"},
                                    stdout_limit=2097152 if expanded else None)

    def test_02_actual_owned_300KiB_stdout_is_complete_only_under_fixed_new_budget(self):
        raw, stderr, row = self.owned_writer("stdout", 307200, expanded=True)
        self.assertEqual(len(raw), 307200)
        self.assertEqual(stderr, b"")
        self.assertTrue(row["complete"])
        self.assertTrue(row["joined"])
        self.assertEqual(row["returncode"], 0)
        self.assertFalse(row["termination_attempted"])
        self.assertEqual(row["capture_limits"], {"stdout": 2097152, "stderr": 262144})
        raw, stderr, row = self.owned_writer("stdout", 307200, expanded=False, suffix=W.CORRECTION_COMMANDS[0])
        self.assertEqual(len(raw), 262145)
        self.assertFalse(row["complete"])
        self.assertTrue(row["joined"])
        self.assertEqual(row["errors"], [{"type": "RuntimeError", "code": "CHILD_OUTPUT_BOUND"}])

    def test_03_new_stdout_ceiling_and_original_stderr_ceiling_still_fail_closed(self):
        for stream, size in (("stdout", 2097153), ("stderr", 262145)):
            with self.subTest(stream=stream):
                raw, stderr, row = self.owned_writer(stream, size, expanded=True)
                self.assertEqual(len(raw if stream == "stdout" else stderr), size)
                self.assertFalse(row["complete"])
                self.assertTrue(row["joined"])
                self.assertEqual(row["errors"], [{"type": "RuntimeError", "code": "CHILD_OUTPUT_BOUND"}])
        with self.assertRaisesRegex(RuntimeError, "ONLY_EXACT_MICROG_DUMP_STDOUT_MAY_USE_TWO_MIB"):
            self.owned_writer("stdout", 1, expanded=True, suffix=("/system/bin/cmd", "package", "dump-package", "local.other"))
        self.assertEqual([W.capture_limits_for(i+1, command) for i, command in enumerate(W.CORRECTION_COMMANDS)],
                         [{"stdout": 262144, "stderr": 262144}, {"stdout": 2097152, "stderr": 262144}, {"stdout": 262144, "stderr": 262144}])
        with self.assertRaisesRegex(RuntimeError, "EXACT_READ_COMMAND_SUFFIX_REQUIRED"):
            W.capture_limits_for(2, W.CORRECTION_COMMANDS[2])

    def test_04_exact_transport_lifetime_guards_and_source_packet_closure(self):
        old = defs((OLD / "observe_current_services.py").read_bytes())
        new = defs((HERE / "observe_current_services.py").read_bytes())
        changed = {"held_bounded_child", "validate_request", "run", "main"}
        self.assertEqual({name for name in old if old[name] != new[name]}, changed)
        self.assertEqual(set(new) - set(old), {"verify_original_failure", "capture_limits_for"})
        old_owned = defs((OLD / "owned_readonly_lifetime.py").read_bytes())
        new_owned = defs((HERE / "owned_readonly_lifetime.py").read_bytes())
        self.assertEqual({name for name in old_owned if old_owned[name] != new_owned[name]}, {"worker_gate"})
        self.assertEqual((OLD / "readonly_services_transport.py").read_bytes(), (HERE / "readonly_services_transport.py").read_bytes())
        request = json.loads((HERE / "request.review-only.json").read_bytes())
        self.assertEqual(request["capture_policy"], W.CAPTURE_POLICY)
        self.assertEqual(request["target_packages"], ["com.google.android.gms"])
        plan = json.loads((HERE / "REPAIR_PLAN.json").read_bytes())
        packet = json.loads((HERE / "process-request.review-only.json").read_bytes())
        self.assertEqual(packet["args"][-1].encode(), (HERE / "stage_and_run_services.py").read_bytes())
        self.assertEqual(packet["stdin"].encode(), (HERE / "stage.stdin.original.json").read_bytes())
        for item, pin in zip(json.loads(packet["stdin"])["files"], plan["stage_files"]):
            raw = item["text"].encode()
            self.assertEqual(raw, (HERE / pin["name"]).read_bytes())
            self.assertEqual((item["name"], len(raw), hashlib.sha256(raw).hexdigest()), (pin["name"], pin["bytes"], pin["sha256"]))
        self.assertEqual((packet["timeout_seconds"], packet["memory_max_bytes"], packet["cpu_quota_percent"], packet["nice"]),
                         (1100, 1073741824, 100, 10))


def main():
    before = len(os.listdir("/proc/self/fd"))
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    after = len(os.listdir("/proc/self/fd"))
    value = {"schema": "pocket4-microg-fixed-stdout-budget-local-controls-v1", "ok": result.wasSuccessful() and before == after,
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
        "FDs_before": before, "FDs_after": after, "real_owned_local_writer_children": 4,
        "original_error_name_preserved": True, "old_ledger_writes": 0, "remote_jobs": 0,
        "Main_reads": 0, "Android_commands": 0, "permission_changes": 0,
        "new_microG_capture_completed": False, "production_ready": False}
    print(json.dumps(value, sort_keys=True), flush=True)
    return 0 if value["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
