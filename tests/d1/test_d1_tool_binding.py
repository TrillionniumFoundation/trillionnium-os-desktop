from __future__ import annotations

from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class D1FilesystemToolBindingTests(unittest.TestCase):
    def test_pipeline_passes_canonical_exact_tool_bindings_to_root_builder(self) -> None:
        pipeline = (REPOSITORY_ROOT / "tests/qemu/run-d1-pipeline.sh").read_text(
            encoding="utf-8"
        )
        for variable, command in [
            ("mke2fs_binary", "mke2fs"),
            ("e2fsck_binary", "e2fsck"),
            ("dumpe2fs_binary", "dumpe2fs"),
        ]:
            self.assertIn(
                f'{variable}=$(readlink -f "$(command -v {command})")', pipeline
            )
        self.assertEqual(pipeline.count("D1_MKE2FS_BINARY=\"$mke2fs_binary\""), 2)
        self.assertEqual(pipeline.count("D1_E2FSCK_BINARY=\"$e2fsck_binary\""), 2)
        self.assertEqual(
            pipeline.count("D1_DUMPE2FS_BINARY=\"$dumpe2fs_binary\""), 2
        )
        self.assertEqual(pipeline.count('PATH="$d1_root_path"'), 2)

    def test_root_builder_fails_closed_and_executes_bound_binaries(self) -> None:
        builder = (
            REPOSITORY_ROOT / "packaging/debian/image/build-d1-image.sh"
        ).read_text(encoding="utf-8")
        for binding in [
            "D1_MKE2FS_BINARY",
            "D1_E2FSCK_BINARY",
            "D1_DUMPE2FS_BINARY",
        ]:
            self.assertIn(binding, builder)
        self.assertIn(
            "D1 filesystem tool PATH does not resolve to the explicit reviewed bindings",
            builder,
        )
        self.assertIn('mke2fs_version=$("$mke2fs_binary" -V', builder)
        self.assertIn('"$mke2fs_binary" \\', builder)
        self.assertIn('"$e2fsck_binary" -fn "$image"', builder)
        self.assertIn('"$dumpe2fs_binary" -h "$image"', builder)
        self.assertNotIn("mke2fs_version=$(mke2fs -V", builder)
        self.assertNotIn("\nmke2fs \\", builder)
        self.assertNotIn("\ne2fsck -fn", builder)
        self.assertNotIn("\ndumpe2fs -h", builder)


if __name__ == "__main__":
    unittest.main()
