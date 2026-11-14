"""Ordinary host controls for exact consumer function bodies; no Android calls."""
import ast
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent
BINDING = json.loads((ROOT / "source-binding.json").read_text())
MARKER = "droidloom-settings-observation.pending.json"
SELECT = {
    "ControlError", "require", "_check_pending_settings_at",
    "require_no_pending_settings", "arun", "ui", "dispatch",
}


def exact_namespace(record):
    path = ROOT / "source" / record["file"]
    raw = path.read_bytes()
    assert len(raw) == record["postimage_bytes"]
    assert hashlib.sha256(raw).hexdigest() == record["postimage_sha256"]
    tree = ast.parse(raw, filename=str(path))
    # The full consumer must parse; only these exact bodies are evaluated so
    # the controls do not import PIL or acquire any Android/system resource.
    nodes = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))
             and n.name in SELECT]
    assert {n.name for n in nodes} == SELECT
    ns = {"os": os}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), ns)
    return ns


class PendingMarkerControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.uid = self.directory.stat().st_uid
        self.marker = self.directory / MARKER

    def tearDown(self):
        self.temp.cleanup()

    def each(self):
        for record in BINDING["files"]:
            yield record["file"], exact_namespace(record)

    def assert_blocked(self, ns, fn):
        with self.assertRaises(ns["ControlError"]) as caught:
            fn()
        self.assertIs(caught.exception.details["action_taken"], False)
        self.assertIs(caught.exception.details["outcome_unknown"], True)
        self.assertIs(caught.exception.details["automatic_retry"], False)

    def test_clear_directory_does_not_create_marker_or_lock(self):
        for name, ns in self.each():
            with self.subTest(consumer=name):
                ns["_check_pending_settings_at"](str(self.directory), self.uid)
                self.assertEqual(list(self.directory.iterdir()), [])

    def test_regular_marker_is_preserved_without_reading_its_payload(self):
        self.marker.write_bytes(b"untrusted and incomplete intent\x00")
        self.marker.chmod(0)
        inode = self.marker.lstat().st_ino
        for name, ns in self.each():
            with self.subTest(consumer=name):
                self.assert_blocked(ns, lambda: ns["_check_pending_settings_at"](str(self.directory), self.uid))
                self.assertEqual(self.marker.lstat().st_ino, inode)
                self.assertEqual(self.marker.lstat().st_mode & 0o777, 0)
        self.marker.chmod(0o600)
        self.assertEqual(self.marker.read_bytes(), b"untrusted and incomplete intent\x00")

    def test_dangling_symlink_and_directory_markers_block(self):
        self.marker.symlink_to("missing-target")
        for name, ns in self.each():
            with self.subTest(consumer=name, inode="symlink"):
                self.assert_blocked(ns, lambda: ns["_check_pending_settings_at"](str(self.directory), self.uid))
                self.assertEqual(os.readlink(self.marker), "missing-target")
        self.marker.unlink()
        self.marker.mkdir()
        for name, ns in self.each():
            with self.subTest(consumer=name, inode="directory"):
                self.assert_blocked(ns, lambda: ns["_check_pending_settings_at"](str(self.directory), self.uid))
                self.assertTrue(self.marker.is_dir())

    def test_untrusted_or_missing_directory_fails_closed(self):
        alias = self.directory / "alias"
        alias.symlink_to(self.directory, target_is_directory=True)
        for name, ns in self.each():
            for path, uid in ((self.directory, self.uid + 1),
                              (self.directory / "missing", self.uid), (alias, self.uid)):
                with self.subTest(consumer=name, path=str(path), owner=uid):
                    self.assert_blocked(ns, lambda: ns["_check_pending_settings_at"](str(path), uid))

    def test_production_wrapper_uses_fixed_system_directory_and_owner(self):
        for name, ns in self.each():
            calls = []
            ns["_check_pending_settings_at"] = lambda *args: calls.append(args)
            with self.subTest(consumer=name):
                ns["require_no_pending_settings"]()
                self.assertEqual(calls, [("/run/lock", 0)])

    def test_pending_blocks_entry_before_any_command_or_input_processing(self):
        self.marker.write_text("unknown previous outcome")
        for name, ns in self.each():
            ns["require_no_pending_settings"] = lambda: ns["_check_pending_settings_at"](str(self.directory), self.uid)
            # These malformed inputs would fail differently if any original
            # body, dispatch, discover, instrumentation, or command were reached.
            for entry, args in (("arun", (None,)), ("ui", (None,)), ("dispatch", (None,))):
                with self.subTest(consumer=name, entry=entry):
                    self.assert_blocked(ns, lambda: ns[entry](*args))
            self.assertEqual(self.marker.read_text(), "unknown previous outcome")


if __name__ == "__main__":
    unittest.main(verbosity=2)
