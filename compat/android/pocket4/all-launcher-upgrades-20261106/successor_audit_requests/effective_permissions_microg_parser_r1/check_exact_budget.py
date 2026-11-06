#!/usr/bin/env python3
"""One local real-file budget control; never read actual private service logs."""
import sys
sys.dont_write_bytecode = True
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import types
import unittest

HERE = Path(__file__).resolve().parent
path = HERE / "interpret_microg_exact.py"
raw = path.read_bytes()
adapter = types.ModuleType("local_exact_microg_budget_control")
adapter.__file__ = str(path)
exec(compile(raw, str(path), "exec"), adapter.__dict__)


class Budget(unittest.TestCase):
    def test_exact_pin_only_and_real_other_files_keep_256KiB(self):
        old = (adapter.PROJECT / "successor_audit_requests/effective_permissions_45_capture_r1/interpret_permission_raw.py").read_text()
        new = raw.decode()
        def defs(source):
            return {n.name: ast.get_source_segment(source, n) for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)}
        a, b = defs(old), defs(new)
        for name in ("need", "sha", "unknown", "lines", "section", "parse_package", "parse_appops", "derive"):
            self.assertEqual(a[name], b[name])
        self.assertEqual(adapter.private_input_limit(adapter.MICROG_PM_PRIVATE, adapter.MICROG_PM_PIN), 2097152)
        for key, value in (("path", "/arbitrary/root/file"), ("bytes", 1478017), ("sha256", "0" * 64)):
            changed = dict(adapter.MICROG_PM_PIN, **{key: value})
            self.assertEqual(adapter.private_input_limit(adapter.MICROG_PM_PRIVATE, changed), 262144)
        self.assertEqual(adapter.private_input_limit(adapter.MICROG_APPOPS_PRIVATE, adapter.MICROG_PM_PIN), 262144)
        self.assertEqual(adapter.private_input_limit(adapter.MICROG_APPOPS_PRIVATE, adapter.MICROG_APPOPS_PIN), 262144)
        with tempfile.TemporaryDirectory(prefix="microg-parser-own-budget-", dir=adapter.PRIVATE_ROOT) as tmp:
            own = Path(tmp) / "synthetic.txt"
            body = b"x" * 262144
            own.write_bytes(body)
            pin = {"path": "/synthetic/nonservice", "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
            self.assertEqual(adapter.read_private(own, pin), body)
            own.write_bytes(body + b"x")
            pin.update(bytes=262145, sha256=hashlib.sha256(body + b"x").hexdigest())
            with self.assertRaisesRegex(RuntimeError, "BOUNDED_PINNED_PRIVATE_INPUT_REQUIRED"):
                adapter.read_private(own, pin)


if __name__ == "__main__":
    before = len(os.listdir("/proc/self/fd"))
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Budget))
    after = len(os.listdir("/proc/self/fd"))
    ok = result.wasSuccessful() and before == after
    print(json.dumps({"schema": "pocket4-exact-microg-parser-budget-local-control-v1", "ok": ok,
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
        "FDs_before": before, "FDs_after": after, "core_parser_functions_byte_identical": 8,
        "actual_private_service_bodies_read": 0, "own_synthetic_files_only": True,
        "runtime_queries": 0, "permission_changes": 0}, sort_keys=True))
    raise SystemExit(0 if ok else 1)
