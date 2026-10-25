#!/usr/bin/env python3
"""Exercise exact manifest admission using real upstream Git objects."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("reserve_source_inputs", ROOT / "support/build/verify-source.py")
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


class ReserveSourceInputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="reserve-source-inputs-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "kernel/asterinas"
        self.source.mkdir(parents=True)
        (self.root / "support").mkdir()
        shutil.copy2(ROOT / "README.md", self.root / "README.md", follow_symlinks=False)
        shutil.copyfile(ROOT / "support/upstream-lock.json", self.root / "support/upstream-lock.json")
        self.git_dir = subprocess.check_output(["git", "rev-parse", "--absolute-git-dir"], cwd=ROOT, text=True).strip()
        entries = subprocess.check_output(["git", "ls-tree", "-rz", verify.PINNED_TREE], cwd=ROOT).split(b"\0")
        for entry in filter(None, entries):
            _, name = entry.split(b"\t", 1)
            name = os.fsdecode(name)
            if name not in verify.BUILD_INPUTS and not name.endswith("Cargo.toml"):
                continue
            destination = self.source / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / "kernel/asterinas" / name, destination, follow_symlinks=False)

    def check(self):
        output = io.StringIO()
        with patch.object(verify, "ROOT", self.root), patch.object(verify, "SOURCE", self.source), \
                patch.dict(os.environ, {"GIT_DIR": self.git_dir}), \
                patch.object(sys, "argv", ["verify-source.py"]), redirect_stdout(output):
            code = verify.main()
        return code, json.loads(output.getvalue())

    def test_exact_reserve_features_are_admitted_without_changing_dependencies(self):
        code, report = self.check()
        self.assertEqual(code, 0, report["errors"])
        self.assertTrue(report["passed"])
        manifests = report["downstream_manifests"]
        for name in verify.PHYSICAL_RESERVE_FEATURE_ADDITIONS:
            self.assertIn("physical-reserve", manifests[name]["optional_profiles"])
        allocator = manifests["osdk/deps/frame-allocator/Cargo.toml"]
        self.assertIsNone(allocator["local_dependency"])

    def test_unreviewed_default_or_dependency_changes_fail_the_real_verifier(self):
        path = self.source / "osdk/deps/frame-allocator/Cargo.toml"
        original = path.read_text()
        for text in (original.replace('physical-reserve = []', 'physical-reserve = []\ndefault = ["physical-reserve"]'),
                     original.replace('paste.workspace = true', 'paste = "2"')):
            path.write_text(text)
            code, report = self.check()
            self.assertEqual(code, 1)
            self.assertFalse(report["passed"])
            self.assertEqual(len(report["errors"]), 1)
            self.assertIn("osdk/deps/frame-allocator/Cargo.toml: blob", report["errors"][0])

    def test_removing_the_opt_in_forwarding_is_not_silently_admitted(self):
        path = self.source / "kernel/core/Cargo.toml"
        path.write_text(path.read_text().replace(', "osdk-frame-allocator/physical-reserve"', ''))
        code, report = self.check()
        self.assertEqual(code, 1)
        self.assertEqual(len(report["errors"]), 1)
        self.assertIn("kernel/core/Cargo.toml: blob", report["errors"][0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
