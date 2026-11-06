#!/usr/bin/env python3
"""Definition-only checks against actual original install/catalog receipts."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("explicit47_definitions_only", ROOT / "observe_explicit_47.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
CATALOG = json.loads((ROOT / "inputs/native45.original.json").read_bytes())
INSTALL = json.loads((ROOT / "inputs/helper-install.stdout.original.jsonl").read_bytes())
TERMINAL = json.loads((ROOT / "inputs/helper-install.terminal.original.json").read_bytes())
REQUEST = json.loads((ROOT / "request.review-only.json").read_bytes())


class Controls(unittest.TestCase):
    def test_actual_native45_and_installed_helper_form_exact_47(self):
        M.validate_request(REQUEST)
        result = M.validate_inputs(CATALOG, INSTALL, TERMINAL)
        self.assertEqual(result["uid"], 10157)
        self.assertEqual(len(REQUEST["packages"]), 47)
        self.assertEqual(set(REQUEST["packages"]), {x["package"] for x in CATALOG["applications"]} | {M.ACTIONS, M.HELPER})

    def test_unknown_install_cannot_authorize_helper_scope(self):
        value = copy.deepcopy(INSTALL)
        value["outcome_unknown"] = True
        with self.assertRaisesRegex(RuntimeError, "ACTUAL_SUCCESSFUL_HELPER_INSTALL"):
            M.validate_inputs(CATALOG, value, TERMINAL)

    def test_wrong_helper_uid_or_apk_is_rejected(self):
        value = copy.deepcopy(INSTALL)
        value["helper_uid"] = 10156
        with self.assertRaisesRegex(RuntimeError, "HELPER_PACKAGE_OR_ACTION_BOUNDARY"):
            M.validate_inputs(CATALOG, value, TERMINAL)
        value = copy.deepcopy(INSTALL)
        value["installed_after_state"]["apk_sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "HELPER_ACTUAL_INSTALLED_BYTES"):
            M.validate_inputs(CATALOG, value, TERMINAL)

    def test_missing_or_duplicate_launcher_is_rejected(self):
        value = copy.deepcopy(CATALOG)
        value["applications"][-1] = copy.deepcopy(value["applications"][0])
        with self.assertRaisesRegex(RuntimeError, "EXACT_CAPTURED_NATIVE_45"):
            M.validate_inputs(value, INSTALL, TERMINAL)

    def test_new_unreviewed_package_or_old_guard_is_rejected(self):
        value = copy.deepcopy(REQUEST)
        value["packages"].append("com.example.unreviewed")
        with self.assertRaisesRegex(RuntimeError, "EXACT_EXPLICIT_47"):
            M.validate_request(value)
        value = copy.deepcopy(REQUEST)
        value["guard"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "EXACT_EXPLICIT_47"):
            M.validate_request(value)

    def test_incomplete_terminal_stream_is_rejected(self):
        value = copy.deepcopy(TERMINAL)
        value["log_truncated"]["stdout"] = True
        with self.assertRaisesRegex(RuntimeError, "HELPER_INSTALL_LOGS_INCOMPLETE"):
            M.validate_inputs(CATALOG, INSTALL, value)

    def test_frozen_original_observer_source_and_three_raw_inputs_match(self):
        original = ROOT.parents[1] / "recovery/observe_successor_scope.py"
        raw = original.read_bytes()
        self.assertEqual(len(raw), M.READER["bytes"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), M.READER["sha256"])
        for name, pin in (("native45.original.json", M.CATALOG), ("helper-install.stdout.original.jsonl", M.INSTALL),
                          ("helper-install.terminal.original.json", M.TERMINAL)):
            raw = (ROOT / "inputs" / name).read_bytes()
            self.assertEqual(len(raw), pin["bytes"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), pin["sha256"])


if __name__ == "__main__":
    before = len(os.listdir("/proc/self/fd"))
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    after = len(os.listdir("/proc/self/fd"))
    print(json.dumps({"schema": "pocket4-explicit47-source-local-controls-v1", "tests_run": result.testsRun,
                      "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
                      "process_FDs_before": before, "process_FDs_after": after,
                      "actual_root_lock_tested": False, "remote_or_Main_operations": 0,
                      "ok": result.wasSuccessful() and before == after}))
    raise SystemExit(0 if result.wasSuccessful() and before == after else 1)
