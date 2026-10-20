#!/usr/bin/env python3
"""Host-only regressions for the immutable upstream integration lock seed."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
SPEC = importlib.util.spec_from_file_location("a01_root_lock_runner", HERE / "run.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class RootLockSeedTests(unittest.TestCase):
    def test_extracts_original_git_bytes_despite_downstream_working_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            path, record = RUNNER.prepare_root_seed(PROJECT, output)
            original = subprocess.check_output(
                ["git", "show", RUNNER.UPSTREAM_COMMIT + ":Cargo.lock"], cwd=PROJECT)
            self.assertEqual(path.read_bytes(), original)
            self.assertNotEqual(path.read_bytes(), (PROJECT / "kernel/asterinas/Cargo.lock").read_bytes())
            self.assertEqual(hashlib.sha256(original).hexdigest(), RUNNER.ROOT_SEED_SHA256)
            self.assertEqual(record, json.loads((output / "root-lock-seed.json").read_text()))
            self.assertEqual(record["git_blob"], subprocess.check_output(
                ["git", "rev-parse", RUNNER.UPSTREAM_COMMIT + ":Cargo.lock"],
                cwd=PROJECT, text=True).strip())
            self.assertEqual(record["bytes"], len(original))

    def test_missing_fixed_git_object_never_falls_back_to_working_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, output = root / "empty-repository", root / "output"
            project.mkdir()
            output.mkdir()
            subprocess.run(["git", "init", "-q", str(project)], check=True)
            (project / "kernel/asterinas").mkdir(parents=True)
            (project / "kernel/asterinas/Cargo.lock").write_bytes(
                (PROJECT / "kernel/asterinas/Cargo.lock").read_bytes())
            with self.assertRaisesRegex(SystemExit, "cannot read fixed upstream root lock"):
                RUNNER.prepare_root_seed(project, output)
            self.assertEqual(list(output.iterdir()), [])

    def test_unexpected_git_blob_bytes_are_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            derived = (PROJECT / "kernel/asterinas/Cargo.lock").read_bytes()
            with mock.patch.object(RUNNER.subprocess, "check_output", return_value=derived):
                with self.assertRaisesRegex(SystemExit, "fixed upstream root lock seed hash mismatch"):
                    RUNNER.prepare_root_seed(PROJECT, output)
            self.assertEqual(list(output.iterdir()), [])

    def test_existing_seed_and_symlink_target_are_preserved(self):
        for symlink in (False, True):
            with self.subTest(symlink=symlink), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary)
                foreign = output / "foreign.lock"
                foreign.write_bytes(b"foreign input must survive\n")
                seed = output / "upstream-root.Cargo.lock"
                if symlink:
                    seed.symlink_to(foreign)
                else:
                    seed.write_bytes(foreign.read_bytes())
                with self.assertRaises(FileExistsError):
                    RUNNER.prepare_root_seed(PROJECT, output)
                self.assertEqual(seed.read_bytes(), b"foreign input must survive\n")
                self.assertEqual(foreign.read_bytes(), b"foreign input must survive\n")
                self.assertFalse((output / "root-lock-seed.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
