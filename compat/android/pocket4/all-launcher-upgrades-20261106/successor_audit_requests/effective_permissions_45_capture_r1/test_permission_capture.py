#!/usr/bin/env python3
"""Local controls only: actual pilot evidence, conservative parsing, and STOP.

No real ledger claim and no remote/Android process is created. Temporary ledger
entries are explicit synthetic fixtures. Private inputs are exact pinned Beike
service logs; only aggregate test results are printed.
"""
import sys
sys.dont_write_bytecode = True
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


G = load("permission_capture_gate_controls", "permission_capture_gate.py")
P = load("permission_literal_parser_controls", "interpret_permission_raw.py")


class Controls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g, cls.plan, cls.loaded = G.load_closure()
        cls.base = G.PROJECT / "successor_audit_requests/beike_permission_pilot_r1"
        cls.outer_raw = (cls.base / "actual/stdout.original.jsonl").read_bytes()
        cls.terminal = cls.g.parse((cls.base / "actual/status-01.original.txt").read_bytes())
        cls.pilot = cls.g.parse((cls.base / "actual/worker.stdout.original.json").read_bytes())
        cls.request = cls.g.parse((cls.base / "request.review-only.json").read_bytes())
        cls.wrapper = G.module((cls.base / "owned_readonly_lifetime.py").read_bytes(), cls.base / "owned_readonly_lifetime.py", "pilot_fixture_wrapper")
        cls.stage = cls.g.parse(cls.outer_raw.splitlines()[0])
        cls.commands = [["/system/bin/cmd", "package", "help"], ["/system/bin/cmd", "package", "dump-package", "com.lianjia.beike"],
                        ["/system/bin/cmd", "appops", "get", "--user", "0", "com.lianjia.beike"]]

    def owned(self, raw=None, terminal=None):
        return G.owned_gate(self.g, self.outer_raw if raw is None else raw, self.terminal if terminal is None else terminal,
            self.plan["baseline_pilot_job"], self.wrapper, self.stage["files"], self.wrapper.CONFIG["stage_root"],
            "pocket4-beike-permission-pilot-source-stage-result-v1")

    def test_01_exact_actual_pilot_and_all_13_source_closures(self):
        actual, raw, outer = self.owned()
        self.assertEqual(raw, (self.base / "actual/worker.stdout.original.json").read_bytes())
        self.assertEqual(actual["current_scope_47_unchanged"], True)
        self.assertEqual(len(self.loaded), 13)
        self.assertEqual(sum(len(row["row"]["Android_commands"]) for row in self.loaded.values()), 103)
        self.assertEqual(len({p for row in self.loaded.values() for p in row["row"]["targets"]}), 45)

    def test_02_actual_terminal_two_stream_protocol_is_strict(self):
        for field, wrong in (("log_truncated", False), ("log_truncated", {"stdout": False}),
                             ("log_truncated", {"stdout": True, "stderr": False}),
                             ("log_errors", {"stdout": None, "stderr": "lost"}),
                             ("automatic_retry", True), ("exit_code", 1), ("output_durable", False)):
            with self.subTest(field=field, wrong=wrong):
                terminal = copy.deepcopy(self.terminal); terminal[field] = wrong
                with self.assertRaises(RuntimeError):
                    self.owned(terminal=terminal)

    def test_03_original_pidfd_retirement_cannot_be_replaced_by_worker_success(self):
        stage, outer = map(self.g.parse, self.outer_raw.splitlines())
        self.assertTrue(outer["child_result"]["ok"])
        outer["child_lifecycle"]["pidfd_closed"] = False
        synthetic = self.g.canonical(stage) + b"\n" + self.g.canonical(outer) + b"\n"
        terminal = copy.deepcopy(self.terminal)
        terminal["log_bytes"]["stdout"] = {"seen": len(synthetic), "stored": len(synthetic)}
        with self.assertRaisesRegex(RuntimeError, "ORIGINAL_CHILD_PIDFD_RETIREMENT_REQUIRED"):
            self.owned(synthetic, terminal)

    def test_04_scope_or_command_change_rejected_and_pilot_not_new_batch_result(self):
        for field in ("argv", "scope"):
            value = copy.deepcopy(self.pilot)
            if field == "argv":
                value["android_commands"][1]["argv"][-2] = "grant"
            else:
                value["scope_guard_after"]["packages"] = value["scope_guard_after"]["packages"][:-1]
            with self.assertRaises(RuntimeError):
                G.service_gate(value, self.request, self.commands, [], self.pilot["guard_before"], True)
        with self.assertRaises(RuntimeError):
            self.loaded[3]["wrapper"].worker_gate(self.pilot, 0)

    def test_05_temporary_unsettled_batch_stops_without_real_claim(self):
        before = G.LEDGER.exists()
        with tempfile.TemporaryDirectory(prefix="p4-permission-gate-fixture-") as path:
            ledger = Path(path)
            state = G.inspect(self.g, self.plan, self.loaded, ledger)
            self.assertEqual(state["state"], "NEXT_READY")
            row = self.loaded[1]["row"]
            folder = ledger / "batch-01"; folder.mkdir()
            intent = {"schema": "pocket4-permission-capture-intent-v1", "plan_sha256": G.PLAN_SHA, "batch": 1,
                      "request": row["request"], "process_request": row["process_request"], "idempotency_key": row["idempotency_key"],
                      "automatic_retry": False}
            (folder / "intent.json").write_bytes(self.g.canonical(intent) + b"\n")
            self.assertEqual(G.inspect(self.g, self.plan, self.loaded, ledger)["state"], "STOP_UNSETTLED_BATCH")
            self.assertFalse((ledger / "batch-02").exists())
        self.assertEqual(G.LEDGER.exists(), before)

    def test_06_actual_pinned_private_pilot_matches_prior_public_literals(self):
        private = P.PRIVATE_ROOT / "beike-permission-pilot-r1"
        pm = P.read_private(private / "android-02.stdout", {"bytes": 50525, "sha256": "001c37aab9fe84def6d2e9d87c1e6a81d34baf74e62e2f50643c45c1077b5487"})
        ops = P.read_private(private / "android-03.stdout", {"bytes": 1720, "sha256": "f839074801868c1196b0df62916df5c31b40ef894649c522495668cfcbeb3b6d"})
        old_raw = (self.base / "EFFECTIVE_PERMISSION_OBSERVATION.derived.json").read_bytes()
        self.assertEqual(hashlib.sha256(old_raw).hexdigest(), "aec1bf7e8df82e73f87f7392bf42321a70633980798a7f2b370cd4fdb9dce47a")
        old = self.g.parse(old_raw)
        new = P.derive(pm, ops, self.pilot["target_identity_from_pinned_scope"], {"existing_actual_pilot_verification_only": True})
        body = new["permission_service"]
        self.assertEqual([r["permission"] for r in body["requested"]["rows"]], old["requested_permissions_verbatim_after_exact_six_space_format_prefix"])
        for key, oldkey in (("install", "install_permission_observations"), ("runtime_user0", "user0_runtime_permission_observations")):
            self.assertEqual([{k: v for k, v in row.items() if k != "canonical_name_without_normalization"} for row in body[key]["rows"]], old[oldkey])
        self.assertEqual([{k: v for k, v in row.items() if k != "reported_scope"} for row in new["AppOps_service"]["rows"]], old["AppOps_reported_modes"])
        self.assertEqual(new["role_status"], "UNKNOWN_NOT_QUERIED")
        self.assertFalse(new["private_raw_bodies_published"])

    def test_07_user0_and_package_boundaries_do_not_borrow_other_user_state(self):
        raw = ("Packages:\n  Package [local.test] (aa):\n    appId=1000\n    requested permissions:\n"
               "      android.permission.CAMERA\n    install permissions:\n    User 10: ceDataInode=1\n"
               "      runtime permissions:\n        android.permission.CAMERA: granted=true, flags=[]\n"
               "    User 0: ceDataInode=2\n      runtime permissions:\n"
               "        android.permission.CAMERA: granted=false, flags=[ USER_SET ]\n"
               "Other service:\n    User 0: ceDataInode=3\n      runtime permissions:\n"
               "        android.permission.CAMERA: granted=true, flags=[]\n").encode()
        value = P.parse_package(raw, "local.test", 1000)
        self.assertEqual(value["runtime_user0"]["rows"][0]["granted"], False)
        self.assertEqual(value["requested_permission_states"][0]["state"], "PM_SERVICE_REPORTED_NOT_GRANTED")
        self.assertEqual(P.parse_package(raw.replace(b"    User 10:", b"    User 0:"), "local.test", 1000)["runtime_user0"]["status"], "UNKNOWN")
        self.assertEqual(P.parse_package(raw + b"  Package [local.test] (bb):\n    appId=1000\n", "local.test", 1000)["status"], "UNKNOWN")
        self.assertEqual(P.parse_package(raw, "local.test", 1001)["status"], "UNKNOWN")

    def test_08_whitespace_missing_and_conflicting_rows_remain_unknown(self):
        raw = ("Packages:\n  Package [local.test] (aa):\n    appId=10100\n    requested permissions:\n"
               "             android.permission.VIBRATE\n      android.permission.CAMERA\n"
               "    install permissions:\n    User 0: ceDataInode=2\n      runtime permissions:\n").encode()
        value = P.parse_package(raw, "local.test", 10100)
        self.assertEqual(value["requested"]["rows"][0]["permission"], "       android.permission.VIBRATE")
        self.assertEqual([r["state"] for r in value["requested_permission_states"]], ["UNKNOWN", "UNKNOWN"])
        bad = raw + b"        android.permission.CAMERA: granted=true, flags=[]\n        android.permission.CAMERA: granted=false, flags=[]\n"
        self.assertEqual(P.parse_package(bad, "local.test", 10100)["runtime_user0"]["status"], "UNKNOWN")
        malformed = raw + b"        android.permission.CAMERA: granted=maybe, flags=[]\n"
        self.assertEqual(P.parse_package(malformed, "local.test", 10100)["runtime_user0"]["status"], "UNKNOWN")

    def test_09_appops_scope_and_modes_never_become_permission_grants(self):
        value = P.parse_appops(b"Uid mode: CAMERA: foreground\nCOARSE_LOCATION: default; time=private\nFUTURE FORMAT\n")
        self.assertEqual(value["status"], "PARTIAL_UNKNOWN")
        self.assertEqual([r["reported_scope"] for r in value["rows"]], ["UID_EXPLICIT_ON_THIS_LINE", "UNKNOWN_UNPREFIXED_LINE"])
        self.assertFalse(value["mode_is_permission_grant"])
        self.assertNotIn("private", json.dumps(value))
        self.assertEqual(P.parse_appops(b"CAMERA: allow\nCAMERA: deny\n")["status"], "PARTIAL_UNKNOWN")
        self.assertEqual(P.parse_appops(b"")["status"], "UNKNOWN")


def main():
    before = len(os.listdir("/proc/self/fd"))
    actual_ledger_existed = G.LEDGER.exists()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Controls)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    after = len(os.listdir("/proc/self/fd"))
    unchanged = G.LEDGER.exists() == actual_ledger_existed
    print(json.dumps({"schema": "pocket4-fixed45-permission-local-controls-v1", "ok": result.wasSuccessful() and before == after and unchanged,
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
        "FDs_before": before, "FDs_after": after, "actual_permission_ledger_unchanged": unchanged,
        "actual_claims_created": 0, "remote_jobs": 0, "Android_commands": 0, "private_raw_bodies_exported": False,
        "actual_new_target_observations": 0, "pilot_literal_parser_comparison_only": True}, sort_keys=True))
    return 0 if result.wasSuccessful() and before == after and unchanged else 1


if __name__ == "__main__":
    raise SystemExit(main())
