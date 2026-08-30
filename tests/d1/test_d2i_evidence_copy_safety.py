from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class D2IEvidenceCopySafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = (ROOT / ".github/workflows/d2i-integrated-image.yml").read_text(
            encoding="utf-8"
        )
        start = self.workflow.index("- name: Enforce evidence, candidate ceiling, and promotion blocker")
        end = self.workflow.index("- name: Collect bounded D2I failure diagnostics")
        self.enforce = self.workflow[start:end]

    def test_servo_lock_is_loaded_with_duplicate_rejecting_nofollow_reader(self) -> None:
        self.assertIn("_open_artifact(Path('.'), 'manifests/servo.lock.json')", self.workflow)
        self.assertIn("load_json_strict(io.TextIOWrapper(stream, encoding='utf-8'))", self.workflow)

    def test_digest_bound_assembly_has_nofollow_regular_file_helpers(self) -> None:
        for marker in (
            "_has_symlink_component",
            "_open_artifact",
            "_O_NOFOLLOW = getattr(os, 'O_NOFOLLOW', 0)",
            "def open_regular(path, label):",
            "def copy_regular(source, destination",
            "def copy_regular_tree(source_root, destination_root, label):",
            "def artifact_records(root_dir):",
            "def write_json(path, value",
        ):
            self.assertIn(marker, self.enforce)

        # Every copied source and every advertised artifact must pass through
        # the descriptor-backed helpers; these direct operations would follow
        # a symlink introduced after the lexical check.
        for forbidden in (
            "source.read_bytes()",
            "target.write_bytes(",
            "shutil.copytree(",
            "path.read_bytes()",
            "path.stat().st_size",
        ):
            self.assertNotIn(forbidden, self.enforce)

    def test_d1_diagnostic_copy_guard_remains_separate(self) -> None:
        diagnostics = self.workflow[
            self.workflow.index("- name: Collect bounded D2I failure diagnostics") :
        ]
        for marker in (
            "copy_diagnostic_tree()",
            "find -P \"$source_root\"",
            'require_regular_path "$source"',
            'require_regular_path "$destination"',
        ):
            self.assertIn(marker, diagnostics)
        self.assertNotIn("destination_root=\"/tmp/trillionnium-d2i/evidence\"", diagnostics)


if __name__ == "__main__":
    unittest.main()
