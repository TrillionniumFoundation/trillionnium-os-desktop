#!/usr/bin/env python3
"""Local protocol/source checks; actual bootstrap proof remains the prior host job."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]


def definitions(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


M = definitions(ROOT / "owned_readonly_lifetime.py", "owned47_candidate_definitions")
SUPPORT_PATH = PROJECT / "successor_qa/ffi_owned_generation_r2/candidate-r1/prepare_beike_owned_lifetime.py"
S = definitions(SUPPORT_PATH, "original_bootstrap_definitions")
PROBE_RAW = (PROJECT / "successor_qa/actual/ffi-bootstrap-probe-r1/stdout.raw.jsonl").read_bytes()
TERM = json.loads((PROJECT / "successor_qa/actual/ffi-bootstrap-probe-r1/terminal.raw.json").read_bytes())


class Controls(unittest.TestCase):
    def test_actual_prior_host_probe_and_fixed_support_bytes(self):
        raw = SUPPORT_PATH.read_bytes()
        self.assertEqual(len(raw), M.SUPPORT["bytes"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), M.SUPPORT["sha256"])
        observed = S.validate_probe_proof(PROBE_RAW, TERM, "1a1b16bbf10-fc05-7891")
        self.assertEqual(observed["python"]["version_info"][:2], [3, 14])
        self.assertEqual(observed["library"]["sha256"], "1a0dc86f787f73e025a6e521056360afcbe70f2a82cd808132fefc2b4ee95daa")

    def test_prior_probe_without_durable_terminal_or_pidfd_death_is_rejected(self):
        terminal = copy.deepcopy(TERM)
        terminal["output_durable"] = False
        with self.assertRaises(RuntimeError):
            S.validate_probe_proof(PROBE_RAW, terminal, "1a1b16bbf10-fc05-7891")
        lines = PROBE_RAW.splitlines()
        result = json.loads(lines[1])
        result["child_lifecycle"]["pidfd_exit_observed"] = False
        damaged = lines[0] + b"\n" + json.dumps(result).encode() + b"\n"
        # Match stream length only to isolate the original held-pidfd gate.
        terminal = copy.deepcopy(TERM)
        terminal["log_bytes"]["stdout"] = {"seen": len(damaged), "stored": len(damaged)}
        with self.assertRaisesRegex(RuntimeError, "ACTUAL_PROBE_AND_OWNED_EXIT_REQUIRED"):
            S.validate_probe_proof(damaged, terminal, "1a1b16bbf10-fc05-7891")

    def test_worker_diff_only_new_private_stage_and_output_paths(self):
        before = (ROOT.parent / "explicit47_scope_r1/observe_explicit_47.py").read_text()
        expected = before.replace("pocket4-explicit-47-scope-source-20261106-r1", "pocket4-explicit-47-scope-source-20261106-r2")
        expected = expected.replace("pocket4-current-explicit-47-app-observation-20261106-r1", "pocket4-current-explicit-47-app-observation-20261106-r2")
        self.assertEqual(expected, (ROOT / "observe_explicit_47.py").read_text())

    def test_exact_config_pins_and_original_worker_request_validator(self):
        for key in ("worker", "request"):
            pin = M.CONFIG[key]
            raw = (ROOT / Path(pin["path"]).name).read_bytes()
            self.assertEqual(len(raw), pin["bytes"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), pin["sha256"])
        worker = definitions(ROOT / "observe_explicit_47.py", "explicit47_worker_definitions")
        worker.validate_request(json.loads((ROOT / "request.review-only.json").read_bytes()))

    def test_unsealed_template_rejects_before_any_runtime_source(self):
        template = ROOT.parent / "owned_readonly_lifetime_template.py"
        result = subprocess.run([sys.executable, "-I", "-B", str(template)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertEqual(result.returncode, 1)
        value = json.loads(result.stdout)
        self.assertIs(value["ok"], False)
        self.assertEqual(value["errors"][0]["reason"], "UNSEALED_NO_RUNTIME")
        self.assertEqual(result.stderr, b"")

    def test_current_helper_receipt_cannot_be_misused_as_full_scope_success(self):
        raw = (ROOT / "inputs/helper-install.stdout.original.jsonl").read_bytes()
        with self.assertRaises(RuntimeError):
            M.worker_gate(M.decode_worker(raw), 0)


if __name__ == "__main__":
    before = len(os.listdir("/proc/self/fd"))
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    after = len(os.listdir("/proc/self/fd"))
    print(json.dumps({"schema": "pocket4-owned-explicit47-local-controls-v1", "tests_run": result.testsRun,
                      "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
                      "process_FDs_before": before, "process_FDs_after": after, "Pocket4_bootstrap_reexecuted": False,
                      "root_or_Main_operations": 0, "ok": result.wasSuccessful() and before == after}))
    raise SystemExit(0 if result.wasSuccessful() and before == after else 1)
