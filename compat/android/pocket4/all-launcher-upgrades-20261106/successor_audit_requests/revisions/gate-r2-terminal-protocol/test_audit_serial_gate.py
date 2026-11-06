#!/usr/bin/env python3
"""Synthetic local receipt/claim controls. They are never actual audit evidence."""
import sys
sys.dont_write_bytecode = True
import base64
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zlib

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("serial_gate", HERE / "audit_serial_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
PLAN_PATH = HERE / "initial-reference-r2/REQUEST_MANIFEST.json"
PLAN_SHA = "8dbdbd2b3f5de9d0141a6c92a3cc5bb2fbaf12b9931c55fa59d85a45d9962b9b"
NANOSECOND = 1793958953453465022
ACTUAL_FAILED_TERMINAL_SHA = '5ddb9fed6cba3ebb3ccea59ca09d12bdc527c51e0284183aa5d5759a5409eab9'


def actual_failed_terminal():
    raw = (HERE / "reference/actual-failed-sourcegen-terminal.original.json").read_bytes()
    if gate.sha(raw) != ACTUAL_FAILED_TERMINAL_SHA:
        raise RuntimeError("ACTUAL_SCHEMA_FIXTURE_CHANGED")
    return gate.parse(raw)


def fixture():
    plan, requests = gate.load_plan(PLAN_PATH, PLAN_SHA)
    plan = copy.deepcopy(plan)
    plan["phase"] = "post-upgrades"  # In-memory fixture only; no real plan is rewritten.
    return plan, requests


def published(result):
    value = copy.deepcopy(result)
    value.pop("final_receipt", None)
    final = value.pop("owned_descriptors_final", {"acquired": 11, "closed": 11, "remaining": 0, "errors": []})
    raw = gate.canonical(value) + b"\n"
    value["final_receipt"] = {"path": value["request"]["output_root"] + "/result.json", "bytes": len(raw), "sha256": gate.sha(raw)}
    value["owned_descriptors_final"] = final
    return value


def encoded(value):
    raw = gate.canonical(value)
    return gate.canonical({"encoding": "zlib-base64", "artifact_bytes": len(raw), "artifact_sha256": gate.sha(raw),
                           "data": base64.b64encode(zlib.compress(raw)).decode()}) + b"\n"


def success(plan, row, request):
    apps = []
    fields = ("complete_APK_set_observed", "one_base_manifest_observed", "all_APKs_signature_verified",
              "all_current_signers_equal_PM_records", "all_manifests_match_PM_identity", "all_permission_names_decoded")
    for number, package in enumerate(row["packages"]):
        count = row["APK_count"] - len(row["packages"]) + 1 if number == 0 else 1
        apps.append({"package": package, "apks": [{"synthetic_fixture": True} for _ in range(count)],
                     **{key: True for key in fields}})
    guard = {"schema": "pocket4-successor-main-guard-v1", "runtime_epoch_sha256": plan["runtime_epoch_sha256"]}
    result = {"schema": "pocket4-successor-installed-apk-audit-v1", "status": "ACTUAL_APK_AUDIT_VERIFIED",
              "synthetic_fixture_only": True, "request": request, "packages": row["packages"], "apps": apps,
              "snapshot_consistent": True, "all_commands_succeeded": True, "all_manifests_and_signatures_verified": True,
              "all_tool_children_joined": True, "action_lock_released": True, "unjoined_tool_pids": [], "errors": [],
              "guard_before": guard, "guard_after": guard,
              "commands": [{"synthetic_fixture": True} for _ in range(3*row["APK_count"])],
              "automatic_retry": False, "production_ready": False, "effective_permission_grants": "UNKNOWN_NOT_QUERIED",
              "collector_source": {"path": request["output_root"] + "/collector-source.py", "bytes": 29242,
                                   "sha256": gate.COLLECTOR_SHA},
              "owned_descriptors_before_final_receipt": {"acquired": 10, "closed": 9, "remaining": 1, "errors": []},
              "precision_fixture_mtime_ns": NANOSECOND}
    result.update({key: 0 for key in ("UI_actions", "App_launches", "permission_changes", "installs",
                   "Android_namespace_commands", "ADB_commands", "business_data_content_reads")})
    terminal = {"job_id": "synthetic-audit-job-%02d" % row["batch"], "state": "succeeded", "exit_code": 0,
                "output_complete": True, "output_durable": True, "terminal_publication_confirmed": True,
                "timed_out": False, "automatic_retry": False, "cancelled": False,
                "log_truncated": actual_failed_terminal()["log_truncated"],
                "log_errors": actual_failed_terminal()["log_errors"]}
    submitted = {"job_id": terminal["job_id"], "idempotency_key": row["suggested_new_idempotency_key"],
                 "request_sha256": row["request"]["sha256"], "plan_sha256": PLAN_SHA}
    return published(result), terminal, submitted


def complete_fixture(folder, result, terminal, submitted):
    for name, raw in (("stdout.original.json", encoded(result)),
                      ("terminal.original.json", gate.canonical(terminal)),
                      ("submitted-job.json", gate.canonical(submitted))):
        with (folder / name).open("xb") as handle:
            handle.write(raw)


class Controls(unittest.TestCase):
    def test_actual_initial_plan_has_45_packages_and_86_apks(self):
        plan, requests = gate.load_plan(PLAN_PATH, PLAN_SHA)
        self.assertEqual(len(requests), 13)
        self.assertEqual(sum(row["APK_count"] for row in plan["batches"]), 86)
        self.assertEqual(sum(row["logical_APK_bytes"] for row in plan["batches"]), 5172118818)

    def test_claim_blocks_resubmission_until_actual_evidence_exists(self):
        plan, requests = fixture()
        with tempfile.TemporaryDirectory(prefix="p4-serial-claim-fixture-") as root:
            state = Path(root) / "state"
            ready = gate.inspect(plan, requests, PLAN_SHA, state)
            self.assertEqual(ready["next"]["batch"], 1)
            gate.claim(state, ready, PLAN_SHA)
            stopped = gate.inspect(plan, requests, PLAN_SHA, state)
            self.assertEqual(stopped["state"], "STOP_UNSETTLED_BATCH")
            with self.assertRaises(RuntimeError):
                gate.claim(state, stopped, PLAN_SHA)

    def test_out_of_order_folder_prevents_advance(self):
        plan, requests = fixture()
        with tempfile.TemporaryDirectory(prefix="p4-serial-order-fixture-") as root:
            state = Path(root); (state / "batch-02").mkdir()
            with self.assertRaises(RuntimeError):
                gate.inspect(plan, requests, PLAN_SHA, state)

    def test_failed_or_incomplete_terminal_stops(self):
        plan, requests = fixture(); row = plan["batches"][0]
        result, terminal, submitted = success(plan, row, requests[1])
        for key, value in (("state", "failed"), ("exit_code", 1), ("output_durable", False),
                           ("terminal_publication_confirmed", False), ("timed_out", True),
                           ("automatic_retry", True), ("log_truncated", True)):
            changed = {**terminal, key: value}
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                gate.check_success(plan, row, requests[1], changed, submitted, encoded(result))

    def test_actual_failed_terminal_proves_stream_shape_but_cannot_pass(self):
        terminal = actual_failed_terminal()
        self.assertEqual(terminal["job_id"], "1a1b13a09dc-fc05-7718")
        self.assertEqual(terminal["state"], "failed")
        self.assertTrue(gate.exact_stream_values(terminal["log_truncated"], False))
        self.assertTrue(gate.exact_stream_values(terminal["log_errors"], None))
        plan, requests = fixture(); row = plan["batches"][0]
        result, _, submitted = success(plan, row, requests[1])
        # The actual failed receipt is not rewritten into a success fixture.
        with self.assertRaisesRegex(RuntimeError, "AUTHORITATIVE_SUCCESSFUL_DURABLE_TERMINAL_REQUIRED"):
            gate.check_success(plan, row, requests[1], terminal, submitted, encoded(result))

    def test_both_stream_flags_are_closed_and_typed(self):
        plan, requests = fixture(); row = plan["batches"][0]
        result, terminal, submitted = success(plan, row, requests[1])
        invalid = {
            "log_truncated": [None, False, True, [], {}, {"stdout": False}, {"stderr": False},
                {"stdout": False, "stderr": False, "unknown": False},
                {"stdout": True, "stderr": False}, {"stdout": False, "stderr": True},
                {"stdout": 0, "stderr": False}, {"stdout": False, "stderr": None},
                {"stdout": "false", "stderr": False}],
            "log_errors": [None, False, [], {}, {"stdout": None}, {"stderr": None},
                {"stdout": None, "stderr": None, "unknown": None},
                {"stdout": "read error", "stderr": None}, {"stdout": None, "stderr": "error"},
                {"stdout": False, "stderr": None}, {"stdout": None, "stderr": []},
                {"stdout": None, "stderr": ""}]
        }
        for key, values in invalid.items():
            for value in values:
                changed = {**terminal, key: value}
                with self.subTest(key=key, value=value), self.assertRaisesRegex(RuntimeError,
                        "AUTHORITATIVE_SUCCESSFUL_DURABLE_TERMINAL_REQUIRED"):
                    gate.check_success(plan, row, requests[1], changed, submitted, encoded(result))
            missing = dict(terminal); del missing[key]
            with self.subTest(key=key, missing=True), self.assertRaises(RuntimeError):
                gate.check_success(plan, row, requests[1], missing, submitted, encoded(result))

    def test_signer_mismatch_child_or_fd_leak_blocks_even_success_status(self):
        plan, requests = fixture(); row = plan["batches"][0]
        result, terminal, submitted = success(plan, row, requests[1])
        cases = []
        value = copy.deepcopy(result); value["apps"][0]["all_current_signers_equal_PM_records"] = False; cases.append(value)
        value = copy.deepcopy(result); value["all_tool_children_joined"] = False; cases.append(value)
        value = copy.deepcopy(result); value["owned_descriptors_final"]["remaining"] = 1; cases.append(value)
        value = copy.deepcopy(result); value["action_lock_released"] = False; cases.append(value)
        for value in cases:
            with self.assertRaises(RuntimeError):
                gate.check_success(plan, row, requests[1], terminal, submitted, encoded(published(value)))

    def test_exact_integer_retained_and_unsafe_roundtrip_rejected(self):
        plan, requests = fixture(); row = plan["batches"][0]
        result, terminal, submitted = success(plan, row, requests[1])
        gate.check_success(plan, row, requests[1], terminal, submitted, encoded(result))
        parsed, raw = gate.decode_artifact(encoded(result))
        self.assertEqual(parsed["precision_fixture_mtime_ns"], NANOSECOND)
        changed = copy.deepcopy(result)
        changed["precision_fixture_mtime_ns"] = int(float(NANOSECOND))
        self.assertNotEqual(changed["precision_fixture_mtime_ns"], NANOSECOND)
        # Outer artifact SHA can be re-encoded, but the original durable result pin is unchanged.
        with self.assertRaisesRegex(RuntimeError, "DURABLE_RESULT_PUBLICATION_PIN_REQUIRED"):
            gate.check_success(plan, row, requests[1], terminal, submitted, encoded(changed))

    def test_hash_change_and_bounded_decompression(self):
        plan, requests = fixture(); row = plan["batches"][0]
        result, _, _ = success(plan, row, requests[1])
        envelope = gate.parse(encoded(result)); envelope["artifact_sha256"] = "0"*64
        with self.assertRaises(RuntimeError):
            gate.decode_artifact(gate.canonical(envelope))
        bomb = b"a" * (gate.MAX_RESULT + 1)
        envelope = {"encoding": "zlib-base64", "artifact_bytes": gate.MAX_RESULT,
                    "artifact_sha256": gate.sha(bomb), "data": base64.b64encode(zlib.compress(bomb)).decode()}
        with self.assertRaises(RuntimeError):
            gate.decode_artifact(gate.canonical(envelope))

    def test_all_thirteen_serial_settlements_do_not_imply_production_ready(self):
        plan, requests = fixture()
        with tempfile.TemporaryDirectory(prefix="p4-serial-all-fixture-") as root:
            state = Path(root) / "state"
            for number in range(1, 14):
                ready = gate.inspect(plan, requests, PLAN_SHA, state)
                self.assertEqual(ready["next"]["batch"], number)
                gate.claim(state, ready, PLAN_SHA)
                row = plan["batches"][number-1]
                result, terminal, submitted = success(plan, row, requests[number])
                complete_fixture(state / ("batch-%02d" % number), result, terminal, submitted)
            final = gate.inspect(plan, requests, PLAN_SHA, state)
            self.assertEqual(final["state"], "ALL_13_APK_AUDITS_SETTLED")
            self.assertEqual(len(final["completed"]), 13)
            self.assertFalse(final["production_ready"])
            self.assertEqual(final["effective_permission_grants"], "UNKNOWN_NOT_QUERIED")


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    print(json.dumps({"schema": "pocket4-audit-serial-gate-offline-controls-v1", "ok": result.wasSuccessful(),
                      "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
                      "skipped": len(result.skipped), "runtime_jobs_submitted": 0, "Main_reads": 0,
                      "fixtures_are_not_actual_audit_receipts": True}, sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() else 1)
