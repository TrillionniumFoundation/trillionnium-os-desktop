#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Admission and rejection tests; these transcripts are explicitly synthetic."""
import copy
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import unix_stream_oracle as oracle

NONCE = "a1" * 16


def positive_records(selection):
    records = oracle.expected_records(selection, oracle.protocol())
    for index, row in enumerate(records, 1):
        row.update(nonce=NONCE, seq=index)
        for key, value in row.items():
            row[key] = str({"$pid": 17, "$uid": 60001, "$gid": 60002,
                            "$first_payload_read": 96}.get(value, value))
    return records


def encode(records, selection="all", exit_code=0, windows=(), aux=None):
    lines = [oracle.INIT, oracle.CPU]
    for row in records:
        lines.append(oracle.PREFIX + " " + " ".join(f"{k}={v}" for k, v in row.items()))
        if row.get("name") == "before_recv" and row.get("iteration") in windows:
            lines.append("[WARN] UNIX_STREAM_RACE_WINDOW old_len=0 queued=96 shutdown=1")
        if aux is not None and row.get("name") == "before_recv":
            lines.append(aux)
    lines.extend([f"{oracle.HARNESS} nonce={NONCE} selection={selection} exit={exit_code}", oracle.BOOT])
    return ("\n".join(lines) + "\n").encode()


def stale_records(iteration=0):
    records = positive_records("shutdown_race")[:3 + 2 * iteration]
    records[-1].update(observed_bytes="0", first_non_eagain="0", eof_read="0")
    records.extend([
        {"event": "case_fail", "case": "shutdown_race", "op": "race_eof", "expected": 96,
         "observed": 0, "errno": 0, "queued_bytes": 96, "iteration": iteration,
         "writer_bytes": 96, "shutdown_result": 0, "child_exit": 0,
         "first_non_eagain": 0, "eof_read": 0},
        {"event": "suite_fail", "case": "suite", "cases_passed": 0,
         "selection": "shutdown_race", "failed_case": "shutdown_race", "exit_code": 1},
    ])
    for index, row in enumerate(records, 1):
        row.update(nonce=NONCE, seq=index)
        records[index - 1] = {k: str(v) for k, v in row.items()}
    return records


def aux_records():
    records = positive_records("credential_only")[:-2]
    records.extend([
        {"event": "case_fail", "case": "credential_only", "op": "recv_credential_only",
         "expected": 13, "observed": -1, "errno": 40},
        {"event": "suite_fail", "case": "suite", "cases_passed": 0,
         "selection": "credential_only", "failed_case": "credential_only", "exit_code": 1},
    ])
    for index, row in enumerate(records, 1):
        row.update(nonce=NONCE, seq=index)
        records[index - 1] = {k: str(v) for k, v in row.items()}
    return records


AUX_MARKER = "[WARN] UNIX_STREAM_AUX_ZERO_PROGRESS count=3 read_bytes=13 remaining=0"


class TranscriptGate(unittest.TestCase):
    def evaluate(self, raw, **kwargs):
        arguments = dict(code=33, timed_out=False, excessive=False, nonce=NONCE,
                         selection="all", variant="positive")
        arguments.update(kwargs)
        result = oracle.evaluate(raw, **arguments)
        self.assertIs(result["native_execution_inferred_from_fixture"], False)
        return result

    def test_all_default_syscall_witnesses(self):
        result = self.evaluate(encode(positive_records("all")))
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["record_count"], 47)

    def test_named_cases_are_complete(self):
        for name in oracle.protocol()["cases"]:
            with self.subTest(name=name):
                result = self.evaluate(encode(positive_records(name), name), selection=name)
                self.assertTrue(result["passed"], result)

    def test_exact_scheduled_window_positive(self):
        raw = encode(positive_records("shutdown_race"), "shutdown_race", windows=("0", "63"))
        result = self.evaluate(raw, selection="shutdown_race", variant="race-fixed")
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["race_windows"], 2)

    def test_stale_snapshot_requires_reaped_real_writer_and_queued_bytes(self):
        for iteration in (0, 17, 63):
            raw = encode(stale_records(iteration), "shutdown_race", 1, (str(iteration),))
            result = self.evaluate(raw, selection="shutdown_race", variant="race-stale")
            self.assertTrue(result["passed"], result)
            self.assertEqual(result["failed_iteration"], iteration)

    def test_auxiliary_negative_is_specific_bounded_failure(self):
        raw = encode(aux_records(), "credential_only", 1, aux=AUX_MARKER)
        result = self.evaluate(raw, selection="credential_only", variant="aux-zero-progress")
        self.assertTrue(result["passed"], result)

    def test_guest_failure_never_substitutes_for_semantic_negative(self):
        raw = encode(aux_records(), "credential_only", 1, aux=AUX_MARKER)
        for overrides in ({"code": 65}, {"code": -9}, {"code": None}, {"timed_out": True},
                          {"excessive": True}, {"code": True}):
            with self.subTest(overrides=overrides):
                result = self.evaluate(raw, selection="credential_only", variant="aux-zero-progress", **overrides)
                self.assertFalse(result["passed"])

    def test_record_and_boot_integrity(self):
        raw = encode(positive_records("all"))
        changes = [
            raw.replace(NONCE.encode(), b"b2" * 16, 1),
            raw.replace(b"seq=1\n", b"seq=2\n", 1),
            raw.replace(b"pid=17", b"pid=18", 1),
            raw.replace(b"pid=17", b"pid=017", 1),
            raw.replace(b"pid=17", b"pid=17 pid=17", 1),
            raw.replace(b"pid=17", b"pid=17 extra=1", 1),
            raw.replace((oracle.INIT + "\n").encode(), b""),
            raw.replace((oracle.CPU + "\n").encode(), b"TRILLIONNIUM_A01_CPU_COUNT=2\n"),
            raw + (oracle.BOOT + "\n").encode(),
            raw[:-1], raw + b"Kernel panic\n",
            raw.replace(b"exit=0", b"exit=1"),
            raw.replace(b"selection=all exit=0", b"selection=queued_shutdown exit=0"),
        ]
        for index, changed in enumerate(changes):
            with self.subTest(index=index):
                self.assertFalse(self.evaluate(changed)["passed"])

    def test_missing_duplicate_reordered_or_invented_records(self):
        records = positive_records("all")
        for changed in (records[:-1], records + [records[-1]], records[1:],
                        [records[1], records[0], *records[2:]],
                        [{**records[0], "event": "case_pass"}, *records[1:]]):
            self.assertFalse(self.evaluate(encode(changed))["passed"])

    def test_wrong_auxiliary_evidence_and_false_probe_exit(self):
        raw = encode(aux_records(), "credential_only", 1, aux=AUX_MARKER)
        changes = [raw.replace(b"errno=40", b"errno=11"),
                   raw.replace(b"count=3", b"count=1"),
                   raw.replace(b"read_bytes=13", b"read_bytes=0"),
                   raw.replace(b"observed=-1", b"observed=0"),
                   raw.replace(b"exit=1", b"exit=124"),
                   raw.replace((AUX_MARKER + "\n").encode(), b""),
                   raw.replace((AUX_MARKER + "\n").encode(), ((AUX_MARKER + "\n") * 2).encode())]
        for changed in changes:
            result = self.evaluate(changed, selection="credential_only", variant="aux-zero-progress")
            self.assertFalse(result["passed"])

    def test_stale_negative_rejects_failed_writer_or_empty_queue(self):
        original = stale_records()
        for index, key, value in ((2, "writer_bytes", "0"), (2, "shutdown_result", "-1"),
                                  (2, "child_exit", "127"), (2, "observed_bytes", "1"),
                                  (3, "queued_bytes", "0"), (3, "observed", "1"),
                                  (3, "errno", "11"), (3, "iteration", "64")):
            changed = copy.deepcopy(original)
            changed[index][key] = value
            result = self.evaluate(encode(changed, "shutdown_race", 1, ("0",)),
                                   selection="shutdown_race", variant="race-stale")
            self.assertFalse(result["passed"], (index, key, value))

    def test_scheduled_window_must_belong_to_failed_iteration(self):
        records = stale_records(1)
        for windows in ((), ("0",)):
            result = self.evaluate(encode(records, "shutdown_race", 1, windows),
                                   selection="shutdown_race", variant="race-stale")
            self.assertFalse(result["passed"])

    def test_uninstrumented_positive_rejects_mutation_markers(self):
        raw = encode(positive_records("shutdown_race"), "shutdown_race", windows=("0",))
        self.assertFalse(self.evaluate(raw, selection="shutdown_race")["passed"])

    def test_instrumented_positive_requires_a_real_window(self):
        raw = encode(positive_records("shutdown_race"), "shutdown_race")
        self.assertFalse(self.evaluate(raw, selection="shutdown_race", variant="race-fixed")["passed"])

    def test_wrong_variant_selection_is_rejected(self):
        raw = encode(positive_records("all"))
        for variant in ("race-fixed", "race-stale", "aux-zero-progress", "invented"):
            self.assertFalse(self.evaluate(raw, variant=variant)["passed"])

    def test_wrong_read_bounds_are_rejected(self):
        for value in ("0", "97", "-1", "096"):
            rows = positive_records("shutdown_race")
            rows[2]["first_non_eagain"] = value
            self.assertFalse(self.evaluate(encode(rows, "shutdown_race"), selection="shutdown_race")["passed"])


if __name__ == "__main__":
    unittest.main()
