from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import compare_d1_builds  # noqa: E402
import prepare_d1_inputs  # noqa: E402


@contextmanager
def argv(*values: str):
    original = sys.argv
    sys.argv = [original[0], *values]
    try:
        yield
    finally:
        sys.argv = original


class PrepareD1InputsTests(unittest.TestCase):
    def test_snapshot_timestamp_becomes_utc_epoch(self) -> None:
        self.assertEqual(
            prepare_d1_inputs.parse_snapshot_epoch("20260828T000000Z"),
            1787875200,
        )

    def test_invalid_snapshot_timestamp_is_rejected(self) -> None:
        for value in ["2026-08-28", "20260828", "20261328T000000Z", ""]:
            with self.subTest(value=value):
                with self.assertRaises(RuntimeError):
                    prepare_d1_inputs.parse_snapshot_epoch(value)

    def package(self, name: str, *, version: str = "1", arch: str = "amd64"):
        return {
            "package": name,
            "requested_name": name,
            "version": version,
            "architecture": arch,
            "filename": f"pool/main/{name[0]}/{name}/{name}_{version}_{arch}.deb",
            "size": 1,
            "sha256": "a" * 64,
        }

    def lock(self, packages: list[dict[str, object]]) -> dict[str, object]:
        return {
            "packages": packages,
            "resolved_package_count": len(packages),
            "package_set_sha256": prepare_d1_inputs.sha256_bytes(
                prepare_d1_inputs.canonical_json(packages)
            ),
        }

    def test_package_map_rejects_digest_drift(self) -> None:
        value = self.lock([self.package("alpha")])
        value["package_set_sha256"] = "0" * 64
        with self.assertRaises(RuntimeError):
            prepare_d1_inputs.package_map(value)

    def test_package_map_rejects_duplicate_identity(self) -> None:
        value = self.lock([self.package("alpha"), self.package("alpha")])
        with self.assertRaises(RuntimeError):
            prepare_d1_inputs.package_map(value)


class CompareD1BuildsTests(unittest.TestCase):
    def build_result(self) -> dict[str, object]:
        return {
            "schema": "trillionnium.desktop.d1-build-result.v2",
            "status": "PASS_BUILD_ONLY",
            "build_name": "candidate",
            "image_id": "fixture-image",
            "source_date_epoch": 1787875200,
            "selection_sha256": "a" * 64,
            "prepared_manifest_sha256": "b" * 64,
            "signed_package_set_sha256": "c" * 64,
            "package_lock": {
                "path": "package-lock.tsv",
                "entries": 1,
                "sha256": "d" * 64,
            },
            "rootfs_tar": {"path": "rootfs.tar", "sha256": "e" * 64},
            "image": {
                "path": "trillionnium-d1.ext4",
                "bytes": 16,
                "sha256": "f" * 64,
                "format": "ext4",
                "label": "TOSD1",
                "uuid": "7f453284-a1e5-4f17-9c30-7c5bde910001",
            },
            "kernel": {
                "source_name": "vmlinuz-fixture",
                "path": "vmlinuz",
                "sha256": "0" * 64,
            },
            "initrd": {
                "source_name": "initrd.img-fixture",
                "path": "initrd.img",
                "sha256": "1" * 64,
            },
            "release_marker_present": False,
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
            json.dumps(self.build_result(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return root

    def prepared_input(self, path: Path) -> Path:
        path.write_text(
            json.dumps(
                {
                    "schema": "trillionnium.desktop.d1-prepared-inputs.v2",
                    "status": "PASS_GENERATED_SIGNED_D1_PACKAGE_LOCK",
                    "package_count": 1,
                    "package_set_sha256": "c" * 64,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def test_identical_independent_builds_are_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = self.create_artifacts(root / "first")
            second = self.create_artifacts(root / "second")
            prepared = self.prepared_input(root / "prepared.json")
            result = root / "result.json"
            with argv(
                "--first",
                str(first),
                "--second",
                str(second),
                "--prepared-inputs",
                str(prepared),
                "--result",
                str(result),
            ):
                self.assertEqual(compare_d1_builds.main(), 0)
            result_data = json.loads(result.read_text(encoding="utf-8"))
            self.assertEqual(
                result_data["status"], "PASS_TWO_INDEPENDENT_BUILDS"
            )
            self.assertTrue(result_data["reproducible"])

    def test_one_byte_image_difference_blocks_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = self.create_artifacts(root / "first")
            second = self.create_artifacts(root / "second", mutate_image=True)
            prepared = self.prepared_input(root / "prepared.json")
            result = root / "result.json"
            with argv(
                "--first",
                str(first),
                "--second",
                str(second),
                "--prepared-inputs",
                str(prepared),
                "--result",
                str(result),
            ):
                with self.assertRaises(RuntimeError):
                    compare_d1_builds.main()
            result_data = json.loads(result.read_text(encoding="utf-8"))
            self.assertEqual(result_data["status"], "FAIL_BUILD_MISMATCH")
            self.assertFalse(
                result_data["artifact_comparisons"][
                    "trillionnium-d1.ext4"
                ]["equal"]
            )


if __name__ == "__main__":
    unittest.main()
