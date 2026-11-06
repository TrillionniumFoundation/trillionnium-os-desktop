#!/usr/bin/env python3
"""Local exact-source and real-receipt checks; never enters Pocket4."""
import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
AUDIT = ROOT.parents[2]
PROJECT = AUDIT.parent


def definitions(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


M = definitions(ROOT / "owned_readonly_lifetime.py", "calendar_owned_definitions")


class Controls(unittest.TestCase):
    def test_original_worker_only_new_private_paths(self):
        before = (ROOT.parent / "candidate-r2/diagnose_calendar_and_fcitx.py").read_text()
        expected = before.replace("calendar-aapt2-comparison-r2-", "calendar-aapt2-comparison-r3-")
        expected = expected.replace("pocket4-calendar-aapt2-diagnostic-source-20261106-r2", "pocket4-calendar-aapt2-diagnostic-source-20261106-r3")
        self.assertEqual(expected, (ROOT / "diagnose_calendar_and_fcitx.py").read_text())

    def test_adapter_only_config_differs_from_actual_passed_explicit47_source(self):
        prior = (AUDIT / "explicit47_scope_r2/owned_readonly_lifetime.py").read_bytes()
        self.assertEqual(len(prior), 16637)
        self.assertEqual(hashlib.sha256(prior).hexdigest(), "1b6bca427c4a01cd1a5a8ea2526f9223e884658ef3a1784f3a8fad885f004ecc")
        def without_config(raw):
            tree = ast.parse(raw)
            tree.body = [node for node in tree.body if not isinstance(node, ast.Assign) or
                         not any(isinstance(t, ast.Name) and t.id == "CONFIG" for t in node.targets)]
            return ast.dump(tree, include_attributes=False)
        self.assertEqual(without_config(prior), without_config((ROOT / "owned_readonly_lifetime.py").read_bytes()))

    def test_packet_contains_exact_stage_and_six_source_inputs(self):
        stage = definitions(ROOT / "stage_and_run_comparison_r3.py", "calendar_stage_definitions")
        packet = json.loads((ROOT / "process-request.review-only.json").read_bytes())
        self.assertEqual(packet["executable"], "/usr/bin/sudo")
        self.assertEqual(packet["args"], ["-n", "/usr/bin/python3", "-I", "-B", "-c", (ROOT / "stage_and_run_comparison_r3.py").read_text()])
        payload_raw = (ROOT / "stage.stdin.original.json").read_bytes()
        self.assertEqual(packet["stdin"].encode(), payload_raw)
        payload = json.loads(payload_raw)
        self.assertEqual(len(payload["files"]), 6)
        for pin, supplied in zip(stage.FILES, payload["files"]):
            raw = (ROOT / pin["name"]).read_bytes()
            self.assertEqual(supplied["name"], pin["name"])
            self.assertEqual(supplied["text"].encode(), raw)
            self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), (pin["bytes"], pin["sha256"]))

    def test_original_host_probe_and_current_real_joint_receipt(self):
        support = PROJECT / "successor_qa/ffi_owned_generation_r2/candidate-r1/prepare_beike_owned_lifetime.py"
        raw = support.read_bytes()
        self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), (M.SUPPORT["bytes"], M.SUPPORT["sha256"]))
        S = definitions(support, "original_proven_bootstrap_definitions")
        probe = (PROJECT / "successor_qa/actual/ffi-bootstrap-probe-r1/stdout.raw.jsonl").read_bytes()
        terminal = json.loads((PROJECT / "successor_qa/actual/ffi-bootstrap-probe-r1/terminal.raw.json").read_bytes())
        S.validate_probe_proof(probe, terminal, "1a1b16bbf10-fc05-7891")
        actual = json.loads((AUDIT / "explicit47_scope_r2/actual/stdout.original.jsonl").read_bytes().splitlines()[1])
        config = M.CONFIG
        try:
            M.CONFIG = dict(config, kind="explicit47")
            self.assertTrue(M.combined(actual["child_lifecycle"], actual["child_result"], b""))
            broken = copy.deepcopy(actual["child_lifecycle"])
            broken["pidfd_exit_observed"] = False
            self.assertFalse(M.combined(broken, actual["child_result"], b""))
            broken = copy.deepcopy(actual["child_lifecycle"])
            broken["owned_child_sigkill_count"] = 1
            self.assertFalse(M.combined(broken, actual["child_result"], b""))
        finally:
            M.CONFIG = config
        self.assertFalse(M.combined(actual["child_lifecycle"], actual["child_result"], b""))

    def test_prior_failed_help_cannot_satisfy_calendar_worker_gate(self):
        actual = json.loads((ROOT / "inputs/aapt2-proof.outer.original.json").read_bytes())
        with self.assertRaisesRegex(RuntimeError, "ORIGINAL_WORKER_DID_NOT_PASS"):
            M.worker_gate(actual, 1)


if __name__ == "__main__":
    before = len(os.listdir("/proc/self/fd"))
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    after = len(os.listdir("/proc/self/fd"))
    print(json.dumps({"schema": "pocket4-owned-calendar-local-controls-v1", "tests_run": result.testsRun,
                      "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
                      "process_FDs_before": before, "process_FDs_after": after, "Pocket4_bootstrap_reexecuted": False,
                      "root_or_Main_operations": 0, "ok": result.wasSuccessful() and before == after}))
    raise SystemExit(0 if result.wasSuccessful() and before == after else 1)
