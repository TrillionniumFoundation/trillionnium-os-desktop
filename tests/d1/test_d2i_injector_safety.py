from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import inject_servo_content_process as injector  # noqa: E402


@unittest.skipUnless(hasattr(os, "symlink"), "symlink support is required")
class D2IInjectorSafetyTests(unittest.TestCase):
    def test_identity_parser_rejects_duplicate_unknown_and_coerced_values(self) -> None:
        cases = (
            '{"generation":1,"generation":1,"pid":123,"start_time":9}',
            '{"generation":1,"pid":123,"start_time":9,"extra":false}',
            '{"generation":true,"pid":123,"start_time":9}',
            '{"generation":1,"pid":"123","start_time":9}',
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, payload in enumerate(cases):
                path = root / f"identity-{index}.json"
                path.write_text(payload + "\n", encoding="utf-8")
                with self.subTest(index=index):
                    with self.assertRaisesRegex(ValueError, "identity"):
                        injector.read_identity(path)

    def test_identity_and_ready_readers_reject_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target"
            target.write_text('{"generation":1,"pid":123,"start_time":9}\n', encoding="utf-8")
            identity = root / "identity.json"
            identity.symlink_to(target)
            marker_target = root / "marker-target"
            marker_target.write_text("ready\n", encoding="utf-8")
            marker = root / "content-crash-ready"
            marker.symlink_to(marker_target)

            with self.assertRaisesRegex(ValueError, "identity"):
                injector.read_identity(identity)
            self.assertFalse(injector.ready_marker(marker))

    def test_receipt_writer_does_not_follow_destination_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.json"
            target.write_text("sentinel\n", encoding="utf-8")
            receipt = root / "content-sigkill-sent.json"
            receipt.symlink_to(target)
            with self.assertRaisesRegex(RuntimeError, "symlink"):
                injector.write_receipt(receipt, pid=123, start_time=9)
            self.assertEqual(target.read_text(encoding="utf-8"), "sentinel\n")

    def test_source_uses_strict_descriptor_backed_state_io(self) -> None:
        source = (ROOT / "tools/inject_servo_content_process.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("load_json_strict", source)
        self.assertIn("from qemu_safe_io import", source)
        self.assertNotIn("identity_path.read_text", source)
        self.assertNotIn("temporary.write_text", source)
        self.assertNotIn("os.replace(temporary, receipt)", source)

    def test_pre_kill_identity_recheck_fails_closed_on_exit_or_reuse(self) -> None:
        with mock.patch.object(injector, "proc_stat", return_value=None):
            self.assertFalse(injector.identity_matches(123, 9))
        # A procfs record with a different start time is a reused PID, not the
        # process selected by the runtime.
        fields = ["x"] * 22
        fields[19] = "9"
        record = "123 (runtime) " + " ".join(fields)
        with mock.patch.object(injector, "proc_stat", return_value=record):
            self.assertTrue(injector.identity_matches(123, 9))
            self.assertFalse(injector.identity_matches(123, 10))


if __name__ == "__main__":
    unittest.main()
