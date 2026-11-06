#!/usr/bin/env python3
"""Local source/actual-receipt controls; no runtime or tool invocation."""
import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("candidate_definition_only", ROOT / "diagnose_calendar_and_fcitx.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
PROOF = json.loads((ROOT / "inputs/aapt2-proof.outer.original.json").read_bytes())
TERMINAL = json.loads((ROOT / "inputs/aapt2-proof.terminal.original.json").read_bytes())
REQUEST = json.loads((ROOT / "request.review-only.json").read_bytes())


class Controls(unittest.TestCase):
    def test_actual_failed_help_receipt_is_preserved_not_promoted(self):
        result = M.verify_actual_proof(PROOF, TERMINAL, REQUEST["candidate_aapt2"])
        self.assertEqual(result["prior_job_state"], "failed")
        self.assertEqual(result["help_returncode"], 1)
        self.assertIs(result["prior_job_reclassified"], False)
        inventory = json.loads((ROOT / "inputs/inventory.original.json").read_bytes())
        M.verify_candidate_inventory(REQUEST["candidate_aapt2"], inventory)
        M.validate_request(REQUEST)

    def test_cannot_rewrite_prior_help_failure_as_pass(self):
        changed = copy.deepcopy(TERMINAL)
        changed.update(state="succeeded", exit_code=0)
        with self.assertRaisesRegex(RuntimeError, "PRESERVE_ACTUAL_FAILED_HELP_JOB"):
            M.verify_actual_proof(PROOF, changed, REQUEST["candidate_aapt2"])

    def test_unknown_or_incomplete_terminal_is_rejected(self):
        for key, value in (("output_durable", False), ("terminal_publication_confirmed", False), ("timed_out", True)):
            changed = copy.deepcopy(TERMINAL)
            changed[key] = value
            with self.assertRaises(RuntimeError):
                M.verify_actual_proof(PROOF, changed, REQUEST["candidate_aapt2"])

    def test_unjoined_child_and_foreign_action_are_rejected(self):
        changed = copy.deepcopy(PROOF)
        changed["commands"][1]["joined"] = False
        with self.assertRaisesRegex(RuntimeError, "PROOF_CHILD_NOT_SETTLED"):
            M.verify_actual_proof(changed, TERMINAL, REQUEST["candidate_aapt2"])
        changed = copy.deepcopy(PROOF)
        changed["permission_changes"] = 1
        with self.assertRaisesRegex(RuntimeError, "PROOF_ACTION_BOUNDARY_CHANGED"):
            M.verify_actual_proof(changed, TERMINAL, REQUEST["candidate_aapt2"])

    def test_real_unsafe_integer_stat_roundtrip_is_rejected(self):
        changed = copy.deepcopy(REQUEST["candidate_aapt2"])
        value = changed["file"]["st_ctime_ns"]
        changed["file"]["st_ctime_ns"] = int(float(value))
        self.assertNotEqual(value, changed["file"]["st_ctime_ns"])
        with self.assertRaisesRegex(RuntimeError, "EXACT_ACTUAL_CANDIDATE"):
            M.validate_candidate(changed)

    def test_extra_application_and_unsupported_tool_are_rejected(self):
        changed = copy.deepcopy(REQUEST)
        changed["packages"].append("com.sankuai.meituan.takeoutnew")
        with self.assertRaisesRegex(RuntimeError, "EXACT_CALENDAR"):
            M.validate_request(changed)
        changed = copy.deepcopy(REQUEST)
        changed["candidate_aapt2"]["path"] = "/usr/bin/aapt2"
        with self.assertRaisesRegex(RuntimeError, "EXACT_ACTUAL_CANDIDATE"):
            M.validate_request(changed)

    def test_real_owned_symlink_retarget_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="aapt2-static-alias-control-") as tmp:
            root = Path(tmp)
            (root / "first").write_bytes(b"first")
            (root / "second").write_bytes(b"second")
            link = root / "dependency"
            link.symlink_to(root / "first")
            aliases = [{"declared_path": str(link), "resolved_path": str(root / "first")}]
            M.recheck_static_aliases(aliases, time.monotonic() + 5)
            link.unlink()
            link.symlink_to(root / "second")
            with self.assertRaisesRegex(RuntimeError, "ACTUAL_LOADER_ALIAS_CHANGED"):
                M.recheck_static_aliases(aliases, time.monotonic() + 5)

    def test_original_faff_child_runner_is_byte_identical(self):
        original = ROOT.parents[3] / "reference/audit_successor_apks.py"
        raw = original.read_bytes()
        self.assertEqual(len(raw), 29242)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), "faff199c1f6218b3c01d87e44be610d6fa211de396b5e8c862c188dec59d284a")
        def function_text(text):
            node = next(n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name == "run_tool")
            return ast.get_source_segment(text, node)
        self.assertEqual(function_text(raw.decode()), function_text((ROOT / "diagnose_calendar_and_fcitx.py").read_text()))


if __name__ == "__main__":
    before = len(os.listdir("/proc/self/fd"))
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Controls)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    after = len(os.listdir("/proc/self/fd"))
    print(json.dumps({"schema": "pocket4-calendar-aapt2-comparison-local-controls-v1", "tests_run": result.testsRun,
                      "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
                      "process_FDs_before": before, "process_FDs_after": after,
                      "root_authority_tested": False, "Main_or_remote_reads": 0, "tool_executions": 0,
                      "ok": result.wasSuccessful() and before == after}))
    raise SystemExit(0 if result.wasSuccessful() and before == after else 1)
