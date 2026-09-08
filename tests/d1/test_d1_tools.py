from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import compare_d1_builds  # noqa: E402
import prepare_d1_inputs  # noqa: E402
import resolve_debian_snapshot  # noqa: E402
import resolve_debian_snapshot_with_pinned_keys  # noqa: E402


@contextmanager
def argv(*values: str):
    original = sys.argv
    sys.argv = [original[0], *values]
    try:
        yield
    finally:
        sys.argv = original


class PrepareD1InputsTests(unittest.TestCase):
    def test_archive_identifier_is_filename_safe(self) -> None:
        for value in ["debian", "debian-updates", "archive.v1_2"]:
            with self.subTest(value=value):
                self.assertEqual(
                    resolve_debian_snapshot.validate_archive_id(value), value
                )
        for value in [
            "",
            "../escape",
            "/absolute",
            "-leading",
            "debian updates",
            "debian\nupdates",
            "x" * 129,
        ]:
            with self.subTest(value=value):
                with self.assertRaises(RuntimeError):
                    resolve_debian_snapshot.validate_archive_id(value)
                with self.assertRaises(RuntimeError):
                    prepare_d1_inputs.validate_archive_id(value)

    def test_snapshot_timestamp_becomes_utc_epoch(self) -> None:
        self.assertEqual(
            prepare_d1_inputs.parse_snapshot_epoch("20260828T000000Z"),
            1787875200,
        )

    def test_snapshot_epoch_stays_within_ext4_superblock_range(self) -> None:
        self.assertEqual(
            prepare_d1_inputs.parse_snapshot_epoch("19700101T000001Z"),
            1,
        )
        self.assertEqual(
            prepare_d1_inputs.parse_snapshot_epoch("21060207T062815Z"),
            4294967295,
        )
        for value in ("19691231T235959Z", "21060207T062816Z"):
            with self.subTest(value=value):
                with self.assertRaises(RuntimeError):
                    prepare_d1_inputs.parse_snapshot_epoch(value)

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

    def inrelease_inputs(self, *, effective_url: str) -> tuple[dict, dict]:
        archive = {
            "id": "debian",
            "base_url": "https://snapshot.debian.org/archive/debian/20260828T000000Z",
            "suite": "trixie",
        }
        record = {
            "id": "debian",
            "requested_url": (
                "https://snapshot.debian.org/archive/debian/20260828T000000Z/"
                "dists/trixie/InRelease"
            ),
            "effective_url": effective_url,
            "suite": "trixie",
            "sha256": "a" * 64,
            "bytes": 1,
        }
        return {"inrelease": [record]}, {"archives": [archive]}

    def test_inrelease_provenance_rejects_curl_progress_contamination(self) -> None:
        lock, requirements = self.inrelease_inputs(
            effective_url=(
                "% Total ...\nhttps://snapshot.debian.org/file/"
                "0123456789abcdef0123456789abcdef01234567/InRelease"
            )
        )
        with self.assertRaises(RuntimeError):
            prepare_d1_inputs.validate_inrelease_records(lock, requirements)

    def test_inrelease_provenance_requires_snapshot_file_redirect(self) -> None:
        lock, requirements = self.inrelease_inputs(
            effective_url="https://example.invalid/file/0123456789abcdef0123456789abcdef01234567/InRelease"
        )
        with self.assertRaises(RuntimeError):
            prepare_d1_inputs.validate_inrelease_records(lock, requirements)

    def test_committed_lock_rejects_snapshot_base_path_escape(self) -> None:
        lock, requirements = self.inrelease_inputs(
            effective_url=(
                "https://snapshot.debian.org/file/"
                "0123456789abcdef0123456789abcdef01234567/InRelease"
            )
        )
        requirements["archives"][0]["base_url"] = (
            "https://snapshot.debian.org/archive/debian/../20260828T000000Z"
        )
        with self.assertRaises(RuntimeError):
            prepare_d1_inputs.validate_inrelease_records(lock, requirements)

        lock, requirements = self.inrelease_inputs(
            effective_url="https://user@snapshot.debian.org/file/0123456789abcdef0123456789abcdef01234567/InRelease"
        )
        with self.assertRaises(RuntimeError):
            prepare_d1_inputs.validate_inrelease_records(lock, requirements)

    def test_inrelease_provenance_accepts_clean_snapshot_file_redirect(self) -> None:
        lock, requirements = self.inrelease_inputs(
            effective_url=(
                "https://snapshot.debian.org/file/"
                "0123456789abcdef0123456789abcdef01234567/InRelease"
            )
        )
        prepare_d1_inputs.validate_inrelease_records(lock, requirements)


class ArchiveBaseUrlTests(unittest.TestCase):
    TIMESTAMP = "20260828T000000Z"

    def test_official_timestamped_snapshot_url_is_accepted(self) -> None:
        value = (
            "https://snapshot.debian.org/archive/debian/" + self.TIMESTAMP
        )
        self.assertEqual(
            resolve_debian_snapshot.validate_archive_base_url(
                value, expected_timestamp=self.TIMESTAMP
            ),
            value,
        )

    def test_archive_url_rejects_non_snapshot_authorities_and_ambiguous_forms(self) -> None:
        values = [
            "http://snapshot.debian.org/archive/debian/20260828T000000Z",
            "https://evil.example/archive/debian/20260828T000000Z",
            "https://user@snapshot.debian.org/archive/debian/20260828T000000Z",
            "https://snapshot.debian.org:443/archive/debian/20260828T000000Z",
            "https://snapshot.debian.org/archive/debian/20260828T000000Z?x=1",
            "https://snapshot.debian.org/archive/debian/20260828T000000Z#frag",
            "https://snapshot.debian.org/archive/debian/../20260828T000000Z",
            "https://snapshot.debian.org/archive/debian/latest",
            "https://snapshot.debian.org/archive/debian/20260828T000000Z/",
        ]
        for value in values:
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                resolve_debian_snapshot.validate_archive_base_url(
                    value, expected_timestamp=self.TIMESTAMP
                )

    def test_archive_url_rejects_timestamp_mismatch_before_network(self) -> None:
        value = "https://snapshot.debian.org/archive/debian/20260827T000000Z"
        with self.assertRaisesRegex(RuntimeError, "does not match expected"):
            resolve_debian_snapshot.validate_archive_base_url(
                value, expected_timestamp=self.TIMESTAMP
            )

    def test_verify_inrelease_validates_base_before_run(self) -> None:
        archive = {
            "id": "debian",
            "base_url": "https://evil.example/archive/debian/20260828T000000Z",
            "suite": "trixie",
            "accepted_primary_fingerprints": ["A" * 40],
        }
        with mock.patch.object(
            resolve_debian_snapshot, "run", side_effect=AssertionError("network")
        ):
            with self.assertRaises(RuntimeError):
                resolve_debian_snapshot.verify_inrelease(
                    archive,
                    Path("/tmp/nonexistent-keyring"),
                    Path("/tmp/nonexistent-work"),
                    Path("/tmp/nonexistent-logs"),
                )


class TrustRootUrlTests(unittest.TestCase):
    def test_official_trust_root_url_is_accepted(self) -> None:
        value = "https://ftp-master.debian.org/keys/archive-key-13.asc"
        self.assertEqual(
            resolve_debian_snapshot_with_pinned_keys.validate_trust_root_url(
                value, "test"
            ),
            value,
        )

    def test_trust_root_url_rejects_authority_and_path_variants(self) -> None:
        variants = [
            "https://user@ftp-master.debian.org/keys/archive-key-13.asc",
            "https://ftp-master.debian.org:443/keys/archive-key-13.asc",
            "https://ftp-master.debian.org/keys/archive-key-13.asc?download=1",
            "https://ftp-master.debian.org/keys/archive-key-13.asc#fragment",
            "https://ftp-master.debian.org/keys/archive-key-13.asc/extra",
            "https://evil.example/keys/archive-key-13.asc",
            "http://ftp-master.debian.org/keys/archive-key-13.asc",
            "https://ftp-master.debian.org/other/archive-key-13.asc",
        ]
        for value in variants:
            with self.subTest(value=value):
                with self.assertRaises(RuntimeError):
                    resolve_debian_snapshot_with_pinned_keys.validate_trust_root_url(
                        value, "test"
                    )


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
            "rootfs_manifest": {
                "path": "rootfs-content-manifest.json",
                "entries": 1,
                "sha256": "2" * 64,
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
        rootfs_manifest = {
            "schema": "trillionnium.desktop.d1-rootfs-manifest.v1",
            "entry_count": 1,
            "entries": [
                {
                    "path": "usr/libexec/hepta-agent-portd",
                    "kind": "file",
                    "mode": "0755",
                    "uid": 0,
                    "gid": 0,
                    "bytes": 16,
                    "sha256": "2" * 64,
                }
            ],
        }
        contents = {
            "package-lock.tsv": b"bash\t1\tamd64\n",
            "rootfs-content-manifest.json": (
                json.dumps(rootfs_manifest, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8"),
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
