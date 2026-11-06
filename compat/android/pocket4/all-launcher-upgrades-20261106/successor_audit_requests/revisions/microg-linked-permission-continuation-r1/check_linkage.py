#!/usr/bin/env python3
"""Local evidence/temporary-ledger controls; never claim the actual ledger."""
import sys
sys.dont_write_bytecode = True
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import types
import unittest

HERE = Path(__file__).resolve().parent
source = (HERE / "linked_permission_gate.py").read_bytes()
gate = types.ModuleType("reviewed_local_microg_linkage_controls")
gate.__file__ = str(HERE / "linked_permission_gate.py")
exec(compile(source, gate.__file__, "exec"), gate.__dict__)


def snapshot(folder):
    return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob("*") if p.is_file()}


class Controls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = gate.load_linkage()
        cls.original, cls.g = cls.context["original"], cls.context["g"]
        cls.plan = cls.g.parse((gate.CORRECTION / "REPAIR_PLAN.json").read_bytes())
        cls.request = cls.g.parse((gate.CORRECTION / "request.review-only.json").read_bytes())
        cls.wrapper = gate.module((gate.CORRECTION / "owned_readonly_lifetime.py").read_bytes(),
                                 gate.CORRECTION / "owned_readonly_lifetime.py", "actual_corrective_owned_controls")

    def test_actual_full_joint_and_original_failure_remain(self):
        state = gate.inspect(self.context)
        self.assertEqual(state["state"], gate.READY)
        self.assertEqual(state["next"]["batch"], 3)
        self.assertEqual([x["batch"] for x in state["completed"]], [1, 2])
        corrected = self.context["correction"][1]
        self.assertEqual(corrected["android_commands"][1]["stdout_bytes"], 1478016)
        self.assertEqual(corrected["android_commands"][2]["stdout_bytes"], 1478)
        self.assertEqual(state["original_ledger_gate_state"], "STOP_FAILED_OR_UNVERIFIED_BATCH")
        self.assertFalse(state["linkage"]["original_failed_capture_reclassified"])
        old = self.original.inspect(self.g, self.context["plan"], self.context["loaded"])
        self.assertEqual((old["state"], old["batch"]), ("STOP_FAILED_OR_UNVERIFIED_BATCH", 2))

    def test_original_failed_terminal_and_false_owned_exit_rejected(self):
        raw = (gate.LEDGER / "batch-02/stdout.original.jsonl").read_bytes()
        terminal = self.g.parse((gate.LEDGER / "batch-02/terminal.original.json").read_bytes())
        with self.assertRaisesRegex(RuntimeError, "EXACT_SUCCESSFUL_DURABLE_TERMINAL_REQUIRED"):
            self.original.owned_gate(self.g, raw, terminal, gate.OLD_JOB, self.wrapper,
                self.plan["stage_files"], self.plan["source_root"], "pocket4-microg-permission-correction-source-stage-result-v1")
        raw = (gate.CORRECTION / "actual/stdout.original.jsonl").read_bytes()
        rows = [self.g.parse(line) for line in raw.splitlines()]
        rows[1]["child_lifecycle"]["pidfd_closed"] = False
        changed = b"\n".join(self.g.canonical(r) for r in rows) + b"\n"
        terminal = self.g.parse((gate.CORRECTION / "actual/terminal.original.json").read_bytes())
        terminal["log_bytes"]["stdout"] = {"seen": len(changed), "stored": len(changed)}
        with self.assertRaisesRegex(RuntimeError, "ORIGINAL_CHILD_PIDFD_RETIREMENT_REQUIRED"):
            self.original.owned_gate(self.g, changed, terminal, gate.CORRECTION_JOB, self.wrapper,
                self.plan["stage_files"], self.plan["source_root"], "pocket4-microg-permission-correction-source-stage-result-v1")

    def test_partial_scope_mismatch_and_other_stream_expansion_rejected(self):
        item = self.context["loaded"][2]
        original = self.context["correction"][1]
        def check(value):
            gate.corrective_service_gate(value, self.request, item["row"]["Android_commands"],
                item["row"]["target_identities"], item["expected_guard"])
        for field in ("complete", "joined", "stdout_eof"):
            altered = copy.deepcopy(original)
            altered["android_commands"][1][field] = False
            with self.assertRaisesRegex(RuntimeError, "EVERY_COMMAND_MUST_COMPLETE_NORMALLY"):
                check(altered)
        altered = copy.deepcopy(original)
        altered["scope_guard_after"]["current_apk_paths_and_file_identities_match"] = False
        with self.assertRaisesRegex(RuntimeError, "FULL_47_CURRENT_IDENTITY_GUARDS_REQUIRED"):
            check(altered)
        for prefix, index, stream in (("android-01", 0, "stdout"), ("android-02", 1, "stderr"), ("android-03", 2, "stdout")):
            row = copy.deepcopy(original["android_commands"][index])
            row[stream + "_bytes"] = row[stream]["bytes"] = 262145
            row[stream + "_sha256"] = row[stream]["sha256"] = "a" * 64
            with self.assertRaisesRegex(RuntimeError, "RAW_STREAM_PIN_MUST_MATCH_ACTUAL_COMMAND_CAPTURE"):
                gate.corrective_stream_pair(row, row, gate.ROOT, prefix)

    def test_real_temporary_claim_is_one_shot_and_never_changes_old_batches(self):
        with tempfile.TemporaryDirectory(prefix="p4-local-permission-linkage-") as tmp:
            ledger = Path(tmp) / "ledger"
            ledger.mkdir(mode=0o700)
            for name in ("batch-01", "batch-02"):
                shutil.copytree(gate.LEDGER / name, ledger / name)
            before = {n: snapshot(ledger / n) for n in ("batch-01", "batch-02")}
            context = gate.load_linkage(ledger)
            decision = gate.claim(context)
            self.assertEqual(decision["state"], "CLAIMED_WITH_VERIFIED_MICROG_CORRECTION_NOT_SUBMITTED")
            self.assertEqual(decision["batch"], 3)
            self.assertEqual(gate.inspect(context)["state"], "STOP_UNSETTLED_BATCH")
            with self.assertRaisesRegex(RuntimeError, "NO_CLAIM_AFTER_FAILED_UNKNOWN_OR_COMPLETE"):
                gate.claim(context)
            self.assertFalse((ledger / "batch-04").exists())
            self.assertEqual(before, {n: snapshot(ledger / n) for n in before})
            (ledger / "batch-03/correction-link.json").write_bytes(b"{}\n")
            self.assertEqual(gate.inspect(context)["state"], "STOP_FAILED_OR_UNVERIFIED_BATCH")


if __name__ == "__main__":
    before_fds = len(os.listdir("/proc/self/fd"))
    original_ledger = snapshot(gate.LEDGER)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    after_fds = len(os.listdir("/proc/self/fd"))
    unchanged = snapshot(gate.LEDGER) == original_ledger
    ok = result.wasSuccessful() and before_fds == after_fds and unchanged
    print(json.dumps({"schema": "pocket4-microg-linked-permission-local-controls-v1", "ok": ok,
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
        "FDs_before": before_fds, "FDs_after": after_fds, "actual_original_ledger_unchanged": unchanged,
        "temporary_original_batch03_claims_created": 1, "temporary_unknown_second_claim_rejected": True,
        "actual_claims": 0, "remote_jobs": 0, "private_service_bodies_read": 0,
        "original_failure_reclassified": False, "production_ready": False}, sort_keys=True))
    raise SystemExit(0 if ok else 1)
