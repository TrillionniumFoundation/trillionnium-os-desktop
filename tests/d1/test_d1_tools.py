from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import compare_d1_builds  # noqa: E402
import resolve_debian_d1_lock  # noqa: E402


@contextmanager
def argv(*values: str):
    original = sys.argv
    sys.argv = [original[0], *values]
    try:
        yield
    finally:
        sys.argv = original


class ResolveDebianD1LockTests(unittest.TestCase):
    def test_snapshot_timestamp_becomes_utc_epoch(self) -> None:
        expected = int(
            datetime(2026, 8, 27, 0, 0, 0, tzinfo=timezone.utc).timestamp()
        )
        self.assertEqual(
            resolve_debian_d1_lock.parse_source_epoch("20260827T000000Z"),
            expected,
        )

    def test_invalid_snapshot_timestamp_is_rejected(self) -> None:
        for value in ["2026-08-27", "20260827", "20261327T000000Z", ""]:
            with self.subTest(value=value):
                with self.assertRaises((ValueError, OverflowError)):
                    resolve_debian_d1_lock.parse_source_epoch(value)

    def test_validsig_fingerprints_are_required_and_deduplicated(self) -> None:
        first = "A" * 40
        second = "B" * 40
        output = "\n".join(
            [
                f"[GNUPG:] VALIDSIG {second} 2026-08-27 1787788800 0 4 0 1 10 01 {second}",
                f"[GNUPG:] VALIDSIG {first} 2026-08-27 1787788800 0 4 0 1 10 01 {first}",
                f"[GNUPG:] VALIDSIG {second} 2026-08-27 1787788800 0 4 0 1 10 01 {second}",
            ]
        )
        self.assertEqual(
            resolve_debian_d1_lock.parse_valid_signers(output),
            [first, second],
        )
        with self.assertRaises(RuntimeError):
            resolve_debian_d1_lock.parse_valid_signers("[GNUPG:] GOODSIG fixture")


class CompareD1BuildsTests(unittest.TestCase):
    def build_result(self) -> dict[str, object]:
        return {
            "schema": "trillionnium.desktop.d1-build-result.v1",
            "status": "PASS_BUILD_ONLY",
            "build_name": "candidate",
            "image_id": "fixture-image",
            "source_date_epoch": 1787788800,
            "selection_sha256": "a" * 64,
            "resolved_manifest_sha256": "b" * 64,
            "package_lock": {"path": "package-lock.tsv", "sha256": "c" * 64},
            "rootfs_tar": {"path": "rootfs.tar", "sha256": "d" * 64},
            "image": {
                "path": "trillionnium-d1.ext4",
                "bytes": 16,
                "sha256": "e" * 64,
                "format": "ext4",
                "label": "TOSD1",
                "uuid": "7f453284-a1e5-4f17-9c30-7c5bde910001",
            },
            "kernel": {
                "source_name": "vmlinuz-fixture",
                "path": "vmlinuz",
                "sha256": "f" * 64,
            },
            "initrd": {
                "source_name": "initrd.img-fixture",
                "path": "initrd.img",
                "sha256": "0" * 64,
            },
            "qemu_booted": False,
            "network_during_acceptance": False,
        }

    def create_artifacts(self, root: Path, *, mutate_image: bool = False) -> Path:
        root.mkdir(parents=True)
        contents = {
            "package-lock.tsv": b"bash\t1\tamd64\n",
            "rootfs.tar": b"rootfs-fixture",
            "trillionnium-d1.ext4": b"image-fixture-00",
            "vmlinuz": b"kernel-fixture",
            "initrd.img": b"initrd-fixture",
        }
        if mutate_image:
            contents["trillionnium-d1.ext4"] = b"image-fixture-01"
        for name, content in contents.items():
            (root / name).write_bytes(content)
        (root / "build-result.json").write_text(
            json.dumps(self.build_result(), indent=2, sort_keys=True) + "\n"
        )
        return root

    def resolved_input(self, path: Path) -> Path:
        path.write_text(
            json.dumps(
                {
                    "schema": "trillionnium.desktop.debian-d1-resolved.v1",
                    "status": "PASS_SIGNED_INRELEASE",
                    "suite": "trixie",
                    "architecture": "amd64",
                }
            )
            + "\n"
        )
        return path

    def test_identical_independent_builds_are_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = self.create_artifacts(root / "first")
            second = self.create_artifacts(root / "second")
            resolved_input = self.resolved_input(root / "resolved-input.json")
            resolved_output = root / "resolved-output.json"
            result = root / "result.json"
            with argv(
                "--first",
                str(first),
                "--second",
                str(second),
                "--resolved-input",
                str(resolved_input),
                "--resolved-output",
                str(resolved_output),
                "--result",
                str(result),
            ):
                self.assertEqual(compare_d1_builds.main(), 0)
            result_data = json.loads(result.read_text())
            resolved_data = json.loads(resolved_output.read_text())
            self.assertEqual(result_data["status"], "PASS_TWO_INDEPENDENT_BUILDS")
            self.assertTrue(result_data["reproducible"])
            self.assertEqual(
                resolved_data["status"],
                "PASS_SIGNED_SNAPSHOT_AND_REPRODUCIBLE_BUILD",
            )

    def test_one_byte_image_difference_blocks_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = self.create_artifacts(root / "first")
            second = self.create_artifacts(root / "second", mutate_image=True)
            resolved_input = self.resolved_input(root / "resolved-input.json")
            result = root / "result.json"
            with argv(
                "--first",
                str(first),
                "--second",
                str(second),
                "--resolved-input",
                str(resolved_input),
                "--resolved-output",
                str(root / "resolved-output.json"),
                "--result",
                str(result),
            ):
                with self.assertRaises(RuntimeError):
                    compare_d1_builds.main()
            result_data = json.loads(result.read_text())
            self.assertEqual(result_data["status"], "FAIL_BUILD_MISMATCH")
            self.assertFalse(
                result_data["artifact_comparisons"]["trillionnium-d1.ext4"]["equal"]
            )


if __name__ == "__main__":
    unittest.main()
