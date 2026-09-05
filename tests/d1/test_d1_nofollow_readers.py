from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import compare_d1_builds  # noqa: E402
import d1_rootfs_manifest  # noqa: E402
import finalize_d1_evidence  # noqa: E402
import verify_d1_artifact  # noqa: E402


@unittest.skipUnless(hasattr(os, "symlink"), "symlink support is required")
class D1NoFollowReaderTests(unittest.TestCase):
    """Every D1 evidence reader rejects a final symlink and duplicate JSON."""

    def test_final_symlink_is_rejected_by_all_hash_readers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target"
            target.write_text("{}\n", encoding="utf-8")
            alias = root / "alias"
            alias.symlink_to(target)

            readers = (
                (compare_d1_builds, lambda path: compare_d1_builds.sha256(path)),
                (d1_rootfs_manifest, lambda path: d1_rootfs_manifest.sha256_file(path)),
                (finalize_d1_evidence, lambda path: finalize_d1_evidence.sha256(path)),
                (verify_d1_artifact, lambda path: verify_d1_artifact.sha256(path)),
            )
            for module, reader in readers:
                with self.subTest(module=module.__name__):
                    with self.assertRaisesRegex(
                        (ValueError, FileNotFoundError), "symlink|unsafe"
                    ):
                        reader(alias)

    def test_final_symlink_is_rejected_by_json_readers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.json"
            target.write_text('{"status":"PASS"}\n', encoding="utf-8")
            alias = root / "alias.json"
            alias.symlink_to(target)

            readers = (
                (compare_d1_builds, lambda path: compare_d1_builds.load_json(path)),
                (finalize_d1_evidence, lambda path: finalize_d1_evidence.load_json(path)),
                (
                    verify_d1_artifact,
                    lambda path: verify_d1_artifact.load_json(path, "evidence"),
                ),
            )
            for module, reader in readers:
                with self.subTest(module=module.__name__):
                    with self.assertRaisesRegex(
                        (ValueError, FileNotFoundError), "symlink|unsafe"
                    ):
                        reader(alias)

    def test_compare_json_reader_rejects_duplicate_members(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicate.json"
            path.write_text('{"status":"PASS","status":"FORGED"}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
                compare_d1_builds.load_json(path)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO support is required")
    def test_fifo_inputs_are_rejected_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fifo = Path(temporary) / "input.fifo"
            os.mkfifo(fifo)
            readers = (
                (compare_d1_builds, lambda path: compare_d1_builds.sha256(path)),
                (d1_rootfs_manifest, lambda path: d1_rootfs_manifest.sha256_file(path)),
                (finalize_d1_evidence, lambda path: finalize_d1_evidence.sha256(path)),
                (verify_d1_artifact, lambda path: verify_d1_artifact.sha256(path)),
            )
            for module, reader in readers:
                with self.subTest(module=module.__name__):
                    with self.assertRaisesRegex(ValueError, "regular"):
                        reader(fifo)


if __name__ == "__main__":
    unittest.main()
