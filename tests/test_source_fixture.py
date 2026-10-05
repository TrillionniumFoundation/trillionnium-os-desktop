"""Regression for fixtures that previously copied live Cargo output."""

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("source_fixture", ROOT / "tests/_source_fixture.py")
assert SPEC is not None and SPEC.loader is not None
FIXTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURE)


class SourceFixtureTests(unittest.TestCase):
    def test_generated_special_file_is_ignored_and_authority_inputs_retained(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            source, destination = parent / "source", parent / "copy"
            for path in ("target/debug/incremental", ".git/objects", "docs/evidence/generated",
                         ".github/workflows", "crates/sample/src", "crates/sample/target"):
                (source / path).mkdir(parents=True)
            # Copying a live generated special inode previously failed (and large
            # output trees were copied once per hostile test).
            os.mkfifo(source / "target/debug/incremental/live-fifo")
            evidence = source / "docs/evidence/generated/result.json"
            evidence.write_text("{}\n")
            (source / ".github/workflows/ci.yml").write_text("jobs: {}\n")
            (source / "crates/sample/target/tracked.txt").write_text("source fixture\n")
            (source / "crates/sample/src/link.rs").symlink_to("missing.rs")
            FIXTURE.copy_source_tree(source, destination)
            self.assertFalse((destination / "target").exists())
            self.assertFalse((destination / ".git").exists())
            self.assertEqual("{}\n", (destination / "docs/evidence/generated/result.json").read_text())
            self.assertTrue((destination / ".github/workflows/ci.yml").is_file())
            self.assertTrue((destination / "crates/sample/target/tracked.txt").is_file())
            self.assertTrue((destination / "crates/sample/src/link.rs").is_symlink())


if __name__ == "__main__":
    unittest.main()
