#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Closed-inventory parser counterexamples; no guest or process is started."""
import copy
import gzip
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("_unix_signal_test_runner", Path(__file__).with_name("run.py"))
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)


class UnixSignalOracle(unittest.TestCase):
    def fixture(self):
        rows = []
        for name in sorted(qa.expected_cases()):
            if name != "setup.guest_guard":
                mode = name.split(".")[0]
                row = dict(observation=name, received=1, child_signal=0, child_exit=0,
                           rc=-1, errno=32, signals=0, rc2=-2, errno2=0, signals2=0, setup=1)
                if mode in ("default", "zero_default"):
                    row.update(received=0, child_signal=13, child_exit=-1, rc=-2, errno=0, setup=0)
                elif mode == "handler":
                    row.update(signals=1)
                elif mode == "healthy":
                    row.update(rc=4, errno=0)
                elif mode == "per_call":
                    row.update(rc2=-1, errno2=32, signals2=1)
                elif mode == "nonblock":
                    if name.endswith("backpressure"):
                        row = dict(observation=name, rc=-1, errno=11, filled=65536, signals=0)
                    elif name.endswith("partial"):
                        row = dict(observation=name, rc=32768, errno=0, drained=32768, signals=0)
                    else:
                        row = dict(observation=name, rc=-1, errno=32, shutdown=0, signals=1)
                elif mode == "writev":
                    if name.endswith("partial_shutdown"):
                        row = dict(observation=name, completed=8, partials=8, positive_signals=0)
                    elif name.endswith("invalid_after_progress"):
                        row = dict(observation=name, rc=4, errno=0, received=4, bytes_ok=1, signals=0)
                    elif name.endswith("empty_vector"):
                        row = dict(observation=name, rc=0, errno=0, shutdown=0, signals=0)
                    else:
                        row = dict(observation=name, rc=-1, errno=29, signals=0)
                rows.append(row)
            rows.append(dict(case=name, passed=True))
        return rows

    def evaluate(self, rows, suffix=b"", **overrides):
        args = dict(qemu_exit=33, timed_out=False, excessive_output=False, base_passed=True)
        args.update(overrides)
        raw = b"\n".join(json.dumps(r).encode() for r in rows) + b"\n" + suffix
        return qa.evaluate(raw, **args)

    def test_complete_fixed_inventory_and_observations(self):
        self.assertEqual(len(qa.expected_cases()), 42)
        report = self.evaluate(self.fixture())
        self.assertTrue(report["passed"])
        self.assertEqual(report["actual_cases"], 42)
        self.assertEqual(report["actual_observations"], 41)

    def test_missing_duplicate_extra_case_and_observation_are_refused(self):
        rows = self.fixture()
        variants = [rows[1:], rows + [rows[0]], rows + [rows[1]], rows + [dict(case="extra", passed=True)],
                    rows + [dict(observation="extra", rc=0)]]
        for changed in variants:
            with self.subTest(size=len(changed)), self.assertRaises(ValueError):
                self.evaluate(changed)

    def test_fake_pass_cannot_hide_missing_signal_or_partial_write_signal(self):
        for name, key, value in [("handler.send", "signals", 0), ("per_call.sendmsg", "signals2", 0),
                                 ("default.write", "child_signal", 0), ("seqpacket.send", "child_signal", 13),
                                 ("writev.partial_shutdown", "positive_signals", 1),
                                 ("writev.invalid_after_progress", "rc", -1),
                                 ("writev.offset_boundary", "errno", 32),
                                 ("nonblock.partial", "rc", 65536)]:
            changed = copy.deepcopy(self.fixture())
            next(row for row in changed if row.get("observation") == name)[key] = value
            with self.subTest(name=name):
                self.assertFalse(self.evaluate(changed)["passed"])

    def test_invalid_observation_types_are_refused(self):
        for invalid in (True, "1", 1.0):
            changed = copy.deepcopy(self.fixture())
            next(row for row in changed if row.get("observation") == "handler.send")["signals"] = invalid
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                self.evaluate(changed)

    def test_base_failure_timeout_exit_and_excessive_output_are_not_accepted(self):
        for changes in (dict(base_passed=False), dict(qemu_exit=65), dict(timed_out=True), dict(excessive_output=True)):
            with self.subTest(changes=changes):
                self.assertFalse(self.evaluate(self.fixture(), **changes)["passed"])

    def test_both_misleading_nosignal_warning_paths_are_refused(self):
        for text in (b"WARN: unsupported flags: MSG_NOSIGNAL\n",
                     b"WARN: sendmmsg flags MSG_NOSIGNAL are not supported\n"):
            with self.subTest(text=text):
                report = self.evaluate(self.fixture(), text)
                self.assertFalse(report["passed"])
                self.assertEqual(report["NOSIGNAL_unsupported_warnings"], 1)

    def test_old_marker_aliases_are_refused(self):
        for name in (".hepta-unix-signal-qa", "./.hepta-unix-signal-qa", "/.hepta-unix-signal-qa"):
            fields = [1, 0o100400, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
            archive = gzip.compress(qa.runner.pack([(name, fields, b"old-fixture-only\n")]), mtime=0)
            with self.subTest(name=name), patch.object(qa, "base_initramfs", return_value=archive):
                with self.assertRaisesRegex(ValueError, "private Unix signal marker already exists"):
                    qa.initramfs(b"synthetic-only", {}, "f" * 32, 1)

    def test_marker_admission_preserves_original_entries(self):
        fields = [1, 0o100644, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
        archive = gzip.compress(qa.runner.pack([("note", fields, b"synthetic-only\n")]), mtime=0)
        original = qa.runner.unpack(gzip.decompress(archive))
        with patch.object(qa, "base_initramfs", return_value=archive):
            result = qa.runner.unpack(gzip.decompress(qa.initramfs(b"synthetic-only", {}, "f" * 32, 1)))
        self.assertEqual(result[:-1], original)
        self.assertEqual(len(result), len(original) + 1)
        self.assertEqual(result[-1][0], ".hepta-unix-signal-qa")
        self.assertEqual(result[-1][1][1], 0o100400)
        self.assertEqual(result[-1][2], b"f" * 32 + b"\n")


if __name__ == "__main__":
    unittest.main()
