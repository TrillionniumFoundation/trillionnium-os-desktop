#!/usr/bin/env python3
"""Exercise README navigation alongside real Git-pinned build input checks."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


VERIFIER = Path(__file__).resolve().parents[1] / "verify-source.py"


class SourceReadmeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="source-readme-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        spec = importlib.util.spec_from_file_location("source_readme_fixture", VERIFIER)
        self.verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.verifier)
        self.verifier.ROOT = self.root
        self.verifier.SOURCE = self.root / "kernel/asterinas"
        self.verifier.SOURCE.mkdir(parents=True)
        subprocess.run(["git", "init", "--quiet", str(self.root)], check=True,
                       capture_output=True, timeout=10)
        self.makefile = b"all:\n\t@echo fixture upstream build input\n"
        blob = self.git("hash-object", "-w", "--stdin", data=self.makefile)
        tree = self.git("mktree", data=f"100644 blob {blob}\tMakefile\n".encode())
        self.verifier.PINNED_TREE = tree
        (self.verifier.SOURCE / "Makefile").write_bytes(self.makefile)
        (self.root / "support").mkdir()
        (self.root / "support/upstream-lock.json").write_text(json.dumps({"kernel": {
            "commit": self.verifier.PINNED_COMMIT,
            "tree": tree,
            "toolchain": self.verifier.PINNED_TOOLCHAIN,
        }}))

    def git(self, *args, data=None):
        result = subprocess.run(["git", "-C", str(self.root), *args], input=data,
                                capture_output=True, check=True, timeout=10)
        return result.stdout.decode().strip()

    def verify(self):
        output = io.StringIO()
        with mock.patch.object(sys, "argv", [str(VERIFIER)]), contextlib.redirect_stdout(output):
            code = self.verifier.main()
        return code, json.loads(output.getvalue())

    def test_navigation_is_allowed_without_weakening_pinned_source_check(self):
        readme = self.root / "README.md"
        for content in (b"", b"# Project\n\n[Build](support/build/README.md)\n"):
            with self.subTest(content=content):
                readme.write_bytes(content)
                code, report = self.verify()
                self.assertEqual(code, 0)
                self.assertTrue(report["passed"])
                self.assertEqual(report["checked_files"], 1)
                self.assertEqual(readme.read_bytes(), content)
        (self.verifier.SOURCE / "Makefile").write_bytes(self.makefile + b"# changed\n")
        code, report = self.verify()
        self.assertEqual(code, 1)
        self.assertFalse(report["passed"])
        self.assertEqual(len(report["errors"]), 1)
        self.assertIn("Makefile: blob", report["errors"][0])

    def test_missing_directory_and_symlink_readme_are_rejected(self):
        readme = self.root / "README.md"
        with self.assertRaisesRegex(SystemExit, "root README must be a regular file"):
            self.verify()
        readme.mkdir()
        with self.assertRaisesRegex(SystemExit, "root README must be a regular file"):
            self.verify()
        readme.rmdir()
        target = self.root / "outside-readme"
        target.write_text("# Valid content behind a disallowed symlink\n")
        readme.symlink_to(target)
        with self.assertRaisesRegex(SystemExit, "root README must be a regular file"):
            self.verify()
        self.assertEqual(target.read_text(), "# Valid content behind a disallowed symlink\n")

    def test_navigation_does_not_allow_changing_the_upstream_pin(self):
        (self.root / "README.md").write_text("# Project navigation\n")
        lock = self.root / "support/upstream-lock.json"
        content = json.loads(lock.read_text())
        content["kernel"]["toolchain"] = "unreviewed-toolchain"
        lock.write_text(json.dumps(content))
        with self.assertRaisesRegex(SystemExit, "fixed upstream inputs changed"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
