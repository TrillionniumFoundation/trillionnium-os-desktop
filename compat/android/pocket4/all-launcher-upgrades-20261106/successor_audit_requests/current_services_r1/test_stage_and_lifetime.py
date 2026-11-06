#!/usr/bin/env python3
"""Exact packet closure and actual precedent checks; no Main entry."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
AUDIT = ROOT.parent


def definitions(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class Controls(unittest.TestCase):
    def test_packet_exact_stager_and_four_bound_files(self):
        stage = definitions(ROOT / "stage_and_run_services.py", "closed_stage_definitions")
        packet = json.loads((ROOT / "process-request.review-only.json").read_bytes())
        self.assertEqual(packet["executable"], "/usr/bin/sudo")
        self.assertEqual(packet["args"], ["-n", "/usr/bin/python3", "-I", "-B", "-c", (ROOT / "stage_and_run_services.py").read_text()])
        self.assertEqual(packet["stdin"].encode(), (ROOT / "stage.stdin.original.json").read_bytes())
        payload = json.loads(packet["stdin"])
        self.assertEqual(payload["schema"], "pocket4-current-readonly-services-source-stage-v1")
        self.assertEqual(len(payload["files"]), 4)
        for pin, item in zip(stage.FILES, payload["files"]):
            raw = (ROOT / pin["name"]).read_bytes()
            self.assertEqual(item["name"], pin["name"])
            self.assertEqual(item["text"].encode(), raw)
            self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), (pin["bytes"], pin["sha256"]))

    def test_owned_child_lifetime_functions_identical_to_real_passed_precedent(self):
        actual = (AUDIT / "explicit47_scope_r2/owned_readonly_lifetime.py").read_text()
        current = (ROOT / "owned_readonly_lifetime.py").read_text()
        self.assertEqual(hashlib.sha256(actual.encode()).hexdigest(), "1b6bca427c4a01cd1a5a8ea2526f9223e884658ef3a1784f3a8fad885f004ecc")
        def part(text, name):
            node = next(node for node in ast.parse(text).body if isinstance(node, ast.FunctionDef) and node.name == name)
            return ast.get_source_segment(text, node)
        for name in ("child", "combined", "publish", "pin_bytes", "load", "retired"):
            self.assertEqual(part(actual, name), part(current, name))

    def test_real_explicit47_receipt_cannot_qualify_new_services_scope(self):
        module = definitions(ROOT / "owned_readonly_lifetime.py", "new_service_lifetime_definitions")
        raw = (AUDIT / "explicit47_scope_r2/actual/stdout.original.jsonl").read_bytes()
        actual = json.loads(raw.splitlines()[1])
        self.assertFalse(module.combined(actual["child_lifecycle"], actual["child_result"], b""))
        with self.assertRaises(RuntimeError):
            module.decode_worker(actual["child_result"]["worker_stdout_original"].encode())


if __name__ == "__main__":
    before = len(os.listdir("/proc/self/fd"))
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    after = len(os.listdir("/proc/self/fd"))
    print(json.dumps({"schema": "pocket4-readonly-services-stage-lifetime-local-controls-v1", "tests_run": result.testsRun,
                      "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
                      "process_FDs_before": before, "process_FDs_after": after, "Main_operations": 0,
                      "ok": result.wasSuccessful() and before == after}))
    raise SystemExit(0 if result.wasSuccessful() and before == after else 1)
