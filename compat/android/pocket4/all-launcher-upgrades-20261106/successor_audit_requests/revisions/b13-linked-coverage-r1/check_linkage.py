#!/usr/bin/env python3
"""Small offline controls over real immutable failed/successful receipts only."""
import sys
sys.dont_write_bytecode = True
import ast
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import types
import unittest
import zlib

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "verify_linked_coverage.py"
V = types.ModuleType("local_b13_linkage_controls")
V.__file__ = str(SOURCE)
exec(compile(SOURCE.read_bytes(), str(SOURCE), "exec"), V.__dict__)


class Controls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.closure = V.input_closure()
        cls.ctx = V.load_context()
        cls.raw = V.read_pin(V.REPAIR / "actual/stdout.original.jsonl", *V.NEW_STDOUT)
        cls.terminal = cls.ctx["g"].parse(V.read_pin(V.REPAIR / "actual/terminal.original.json", *V.NEW_TERMINAL))
        cls.result = cls.ctx["g"].parse(V.read_pin(V.REPAIR / "actual/artifact.original.json", *V.NEW_ARTIFACT))
        _, cls.failure = V.failed_original_b13(cls.ctx)

    def test_01_full_actual_history_and_correction_link_to_45_without_rewrite(self):
        value = V.linked_coverage(self.ctx)
        self.assertEqual((value["observed_packages"], value["observed_APKs"], value["successful_tool_commands"]), (45, 85, 255))
        self.assertEqual(value["original_ledger_final_gate_state"], "STOP_NO_RETRY")
        self.assertEqual(value["original_b13_failure_preserved"]["state"], "failed")
        fixture = next(a for a in value["packages"] if a["package"] == "local.pocket4.fixture")
        self.assertIsNone(fixture["declared_version_code"])
        self.assertIsNone(fixture["declared_version_name"])
        self.assertEqual(fixture["PM_version_code"], 0)
        self.assertFalse(value["original_ledger_written"])
        self.assertFalse(value["production_ready"])
        self.assertEqual(V.input_closure(), self.closure)

    def test_02_actual_failed_b13_is_never_accepted_as_a_success(self):
        folder = V.LEDGER / "batch-13"
        raw = self.ctx["g"].read(folder / "stdout.original.jsonl", 1048576)
        terminal = self.ctx["g"].parse(self.ctx["g"].read(folder / "terminal.original.json", 65536))
        row = self.ctx["plan"]["batches"][-1]
        with self.assertRaisesRegex(RuntimeError, "EXACT_DURABLE_TERMINAL_REQUIRED"):
            self.ctx["old"].owned_gate(self.ctx["g"], raw, terminal, V.FAILED_JOB, self.ctx["wrappers"][13], V.stage_files(row), row["source_root"])
        with self.assertRaisesRegex(RuntimeError, "EXACT_DURABLE_TERMINAL_REQUIRED"):
            V.correction_gate(self.ctx, raw, terminal, self.failure)

    def test_03_original_pidfd_and_complete_descriptor_identity_are_required(self):
        for mutation, code in (("pidfd", "HELD_ORIGINAL_CHILD_RETIREMENT_REQUIRED"),
                               ("descriptor", "FULL_DESCRIPTOR_IDENTITIES_AND_NO_MANUAL_CLOSE_REQUIRED")):
            stage, outer = [self.ctx["g"].parse(line) for line in self.raw.splitlines()]
            if mutation == "pidfd":
                outer["child_lifecycle"]["pidfd_closed"] = False
            else:
                outer["child_result"]["final_descriptors"]["1"]["target"] = "synthetic_replaced_descriptor"
                child_raw = self.ctx["g"].canonical(outer["child_result"]) + b"\n"
                outer["child_stdout"]["bytes"] = len(child_raw)
                outer["child_stdout"]["sha256"] = V.sha(child_raw)
            raw = self.ctx["g"].canonical(stage) + b"\n" + self.ctx["g"].canonical(outer) + b"\n"
            terminal = copy.deepcopy(self.terminal)
            terminal["log_bytes"]["stdout"] = {"seen": len(raw), "stored": len(raw)}
            with self.subTest(mutation=mutation), self.assertRaisesRegex(RuntimeError, code):
                V.correction_gate(self.ctx, raw, terminal, self.failure)

    def test_04_missing_command_signature_stat_and_layout_evidence_reject(self):
        cases = (("command", "THREE_COMMANDS_PER_APK"), ("signature", "FULL_ORIGINAL_SIGNATURE_AND_HELD_APK_PROOF"),
                 ("stat", "EVERY_COVERED_APK_UID_DATA_MATCHES_CURRENT_REFERENCE"))
        for mutation, code in cases:
            value = copy.deepcopy(self.result)
            apk = value["apps"][0]["apks"][0]
            if mutation == "command":
                apk["commands"].pop()
            elif mutation == "signature":
                apk["signature"]["verified"] = False
            else:
                apk["file"]["st_mtime_ns"] += 1
            with self.subTest(mutation=mutation), self.assertRaisesRegex(RuntimeError, code):
                V.basic_apk_checks(self.ctx, value)
        value = copy.deepcopy(self.result)
        layout = value["official_private_layout"]
        full = json.loads(zlib.decompress(base64.b64decode(layout["data"])))
        full["observations"][0]["complete"] = False
        raw = self.ctx["g"].canonical(full) + b"\n"
        layout["artifact"]["bytes"], layout["artifact"]["sha256"] = len(raw), V.sha(raw)
        layout["data"] = base64.b64encode(zlib.compress(raw)).decode()
        with self.assertRaisesRegex(RuntimeError, "INCOMPLETE_OFFICIAL_LAYOUT_OBSERVATION"):
            self.ctx["old"].layout_gate(self.ctx["g"], value, 3, True)


def main():
    before = len(os.listdir("/proc/self/fd"))
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    after = len(os.listdir("/proc/self/fd"))
    original = (V.OLD / "linked_audit_gate.py").read_text()
    new = SOURCE.read_text()
    def definition(source, name):
        return ast.get_source_segment(source, next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name))
    same_terminal = definition(original, "terminal_gate") == definition(new, "terminal_gate")
    exact_owned_delta = definition(original, "owned_gate").replace("def owned_gate(", "def repair_owned_gate(", 1).replace(
        "pocket4-calendar-official-comparison-source-stage-result-v1", "pocket4-b13-version-repair-source-stage-result-v1") == definition(new, "repair_owned_gate")
    value = {"schema": "pocket4-b13-linked-coverage-local-controls-v1", "ok": result.wasSuccessful() and before == after and same_terminal and exact_owned_delta,
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
        "local_FDs_before": before, "local_FDs_after": after, "terminal_gate_exact_original_definition": same_terminal,
        "owned_gate_only_function_name_and_stage_schema_changed": exact_owned_delta, "actual_receipts_checked_locally": True,
        "negative_mutations_are_memory_only_not_authoritative_receipts": True, "ledger_writes": 0, "ledger_claims": 0,
        "remote_jobs": 0, "Main_reads": 0, "Android_commands": 0, "APK_tool_executions": 0, "production_ready": False}
    print(json.dumps(value, sort_keys=True), flush=True)
    return 0 if value["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
