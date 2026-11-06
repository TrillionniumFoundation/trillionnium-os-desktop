#!/usr/bin/env python3
"""Local actual-pin and bounded-codec controls; no private actual bodies read."""
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


def load(name):
    path = HERE / (name + ".py")
    value = types.ModuleType("local_" + name)
    value.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), "exec"), value.__dict__)
    return value


prepare = load("prepare_compressed_readback")
decode = load("decode_private_readback")


class Controls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.link, cls.context, cls.state = prepare.load_link()

    def test_actual_microg_closure_exact_limits_and_five_reader_functions(self):
        pins, limits, binding = prepare.select_complete_batch(2, self.link, self.context, self.state)
        self.assertEqual([p["bytes"] for p in pins], [1478016, 1478])
        self.assertEqual(limits, [2097152, 262144])
        self.assertEqual(binding["source_capture_job"], "1a1b2d790f2-fc05-7ffb")
        source, original = prepare.render_reader(pins, limits, binding)
        self.assertEqual(source.encode(), (HERE / "batch-02/read_fixed_batch_private_logs.py").read_bytes())
        a, b = prepare.definitions(original), prepare.definitions(source)
        for name in ("need", "sha", "canonical", "read_file", "read_host_pin"):
            self.assertEqual(a[name], b[name])
        packet = json.loads((HERE / "batch-02/process-request.review-only.json").read_bytes())
        self.assertEqual(packet["args"][-1], source)
        self.assertEqual(packet["timeout_seconds"], 60)
        self.assertEqual(packet["memory_max_bytes"], 268435456)

    def test_synthetic_large_codec_complete_hash_and_truncation_rejection(self):
        # A transport fixture of the actual byte lengths; never service evidence.
        plan = copy.deepcopy(json.loads((HERE / "batch-02/READBACK_PLAN.json").read_bytes()))
        rows = []
        bodies = []
        for index, pin in enumerate(plan["fixed_files"]):
            body = (b"SYNTHETIC_CODEC_FIXTURE_" + bytes([65 + index])) * (pin["bytes"] // 24 + 1)
            body = (body + b"x" * pin["bytes"])[:pin["bytes"]]
            pin["sha256"] = hashlib.sha256(body).hexdigest()
            bodies.append(body)
            rows.append({**pin, "encoding": "hex", "bytes_hex": body.hex(), "held_file_and_path_rechecked": True})
        value = {"schema": "pocket4-fixed-batch-private-service-log-readback-v2", "ok": True,
            "capture_binding": plan["capture_binding"], "files": rows, "process_FDs_before": 4, "process_FDs_after": 4,
            "existing_files_modified": False, "Main_reads": 0, "native_commands": 0, "Android_commands": 0, "aapt_commands": 0,
            "UI_actions": 0, "installs": 0, "namespace_entries": 0, "permission_changes": 0, "action_lock_acquired": False,
            "automatic_retry": False, "original_failed_audit_reclassified": False,
            "raw_output_may_contain_private_state": True, "raw_output_repository_publication_admitted": False}
        inner = decode.canonical(value)
        compressed = zlib.compress(inner, 9)
        envelope = {"encoding": "zlib-base64", "artifact_bytes": len(inner), "artifact_sha256": decode.sha(inner),
                    "data": base64.b64encode(compressed).decode()}
        raw = decode.canonical(envelope) + b"\n"
        _, actual_inner, decoded = decode.decode_envelope(raw, plan)
        self.assertEqual(actual_inner, inner)
        self.assertEqual([body for _, body in decoded], bodies)
        for bad in (compressed[:-1], compressed + b"trailing"):
            changed = dict(envelope, data=base64.b64encode(bad).decode())
            with self.assertRaisesRegex(RuntimeError, "COMPLETE_DECOMPRESSED_ORIGINAL_BYTES_REQUIRED"):
                decode.decode_envelope(decode.canonical(changed) + b"\n", plan)
        changed = dict(envelope, artifact_sha256="0" * 64)
        with self.assertRaisesRegex(RuntimeError, "COMPLETE_DECOMPRESSED_ORIGINAL_BYTES_REQUIRED"):
            decode.decode_envelope(decode.canonical(changed) + b"\n", plan)
        altered_plan = copy.deepcopy(plan)
        altered_plan["fixed_files"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "FIXED_FULL_FILE_PIN_AND_PATH_RECHECK_REQUIRED"):
            decode.decode_envelope(raw, altered_plan)

    def test_no_unknown_or_old_failed_batch_and_no_arbitrary_path(self):
        unknown_state = copy.deepcopy(self.state)
        unknown_state["completed"] = [row for row in unknown_state["completed"] if row["batch"] != 3]
        with self.assertRaisesRegex(RuntimeError, "NO_READER_FOR_FAILED_UNKNOWN_OR_UNOBSERVED_BATCH"):
            prepare.select_complete_batch(3, self.link, self.context, unknown_state)
        changed = copy.deepcopy(self.state)
        changed["completed"][1]["job_id"] = self.link.OLD_JOB
        with self.assertRaisesRegex(RuntimeError, "ONLY_EXACT_CORRECTED_MICROG_CAPTURE"):
            prepare.select_complete_batch(2, self.link, self.context, changed)
        changed = copy.deepcopy(self.state)
        changed["completed"][1]["service_reports"][0]["stdout"]["path"] = "/etc/shadow"
        with self.assertRaisesRegex(RuntimeError, "ONLY_FIXED_SUCCESSFUL_LOG_PATHS_AND_BUDGETS"):
            prepare.select_complete_batch(2, self.link, self.context, changed)
        changed = copy.deepcopy(self.state)
        changed["completed"][1]["service_reports"][1]["stdout"]["bytes"] = 262145
        with self.assertRaisesRegex(RuntimeError, "ONLY_FIXED_SUCCESSFUL_LOG_PATHS_AND_BUDGETS"):
            prepare.select_complete_batch(2, self.link, self.context, changed)


if __name__ == "__main__":
    before = len(os.listdir("/proc/self/fd"))
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    after = len(os.listdir("/proc/self/fd"))
    ok = result.wasSuccessful() and before == after
    print(json.dumps({"schema": "pocket4-fixed-batch-private-compression-local-controls-v2", "ok": ok,
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
        "FDs_before": before, "FDs_after": after, "synthetic_codec_is_service_evidence": False,
        "actual_private_bodies_read": 0, "remote_jobs": 0, "actual_claims": 0, "production_ready": False}, sort_keys=True))
    raise SystemExit(0 if ok else 1)
