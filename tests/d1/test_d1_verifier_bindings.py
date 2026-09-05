from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import verify_d1_artifact  # noqa: E402


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class D1VerifierBindingTests(unittest.TestCase):
    """Mutation tests for the portable verifier's cross-file bindings."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for relative in (
            "inputs",
            "evidence",
            "builds/build-a",
            "builds/build-b",
        ):
            (self.root / relative).mkdir(parents=True, exist_ok=True)

        self.package_lock = b"bash\t1\tamd64\n"
        (self.root / "inputs/expected-package-lock.tsv").write_bytes(
            self.package_lock
        )
        prepared = {
            "schema": "trillionnium.desktop.d1-prepared-inputs.v2",
            "expected_package_lock_sha256": digest(self.package_lock),
            "package_count": 1,
            "package_set_sha256": "a" * 64,
            "selection_sha256": "b" * 64,
            "source_date_epoch": 1787875200,
        }
        (self.root / "inputs/prepared-inputs.json").write_text(
            json.dumps(prepared, sort_keys=True), encoding="utf-8"
        )
        self.prepared_sha = digest(
            (self.root / "inputs/prepared-inputs.json").read_bytes()
        )

        self.binary_digests = {
            "schema": "trillionnium.desktop.d1-binary-digests.v1",
            "product": {
                "path": "target/release/hepta-agent-portd",
                "sha256": "c" * 64,
                "bytes": 3,
            },
            "qualification": {
                "path": "target/release/hepta-agent-d1-fixture",
                "sha256": "d" * 64,
                "bytes": 4,
            },
        }
        self._write_binary_digests()

        self.results: dict[str, dict[str, object]] = {
            "inputs/prepared-inputs.json": prepared,
        }
        for build_name in ("build-a", "build-b"):
            build_root = self.root / "builds" / build_name
            (build_root / "package-lock.tsv").write_bytes(self.package_lock)
            entries = [
                {"path": ".", "type": "directory"},
                {
                    "path": "./usr/libexec/hepta-agent-portd",
                    "type": "file",
                    "size": 3,
                    "sha256": self.binary_digests["product"]["sha256"],
                },
                {
                    "path": "./usr/libexec/hepta-agent-d1-fixture",
                    "type": "file",
                    "size": 4,
                    "sha256": self.binary_digests["qualification"]["sha256"],
                },
            ]
            self._write_manifest(build_name, entries)
            self.results[f"builds/{build_name}/build-result.json"] = {
                "status": "PASS_BUILD_ONLY",
                "build_name": "candidate",
                "prepared_manifest_sha256": self.prepared_sha,
                "network_during_acceptance": False,
                "qemu_booted": False,
                "release_marker_present": False,
                "package_lock": {
                    "path": "package-lock.tsv",
                    "entries": 1,
                    "sha256": digest(self.package_lock),
                },
                "rootfs_manifest": {
                    "path": "rootfs-content-manifest.json",
                    "entries_sha256": self.manifest_entries_sha,
                    "sha256": digest(
                        (build_root / "rootfs-content-manifest.json").read_bytes()
                    ),
                },
                "image": {
                    "path": "trillionnium-d1.ext4",
                    "sha256": "e" * 64,
                    "format": "ext4",
                },
                "kernel": {"sha256": "f" * 64},
                "initrd": {"sha256": "1" * 64},
                "rootfs_tar": {"sha256": "2" * 64},
            }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_binary_digests(self) -> None:
        (self.root / "evidence/binary-digests.json").write_text(
            json.dumps(self.binary_digests, sort_keys=True), encoding="utf-8"
        )

    def _write_manifest(
        self, build_name: str, entries: list[dict[str, object]]
    ) -> None:
        encoded = json.dumps(
            entries,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        self.manifest_entries_sha = digest(encoded)
        document = {
            "schema": "trillionnium.desktop.d1-rootfs-manifest.v1",
            "entry_count": len(entries),
            "entries_sha256": self.manifest_entries_sha,
            "entries": entries,
        }
        (self.root / "builds" / build_name / "rootfs-content-manifest.json").write_text(
            json.dumps(document, sort_keys=True), encoding="utf-8"
        )

    def _refresh_build_manifest_metadata(self, build_name: str) -> None:
        path = self.root / "builds" / build_name / "rootfs-content-manifest.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        self.results[f"builds/{build_name}/build-result.json"]["rootfs_manifest"] = {
            "path": "rootfs-content-manifest.json",
            "entries_sha256": document["entries_sha256"],
            "sha256": digest(path.read_bytes()),
        }

    def test_package_lock_mutation_is_rejected(self) -> None:
        (self.root / "builds/build-b/package-lock.tsv").write_bytes(
            b"dash\t2\tamd64\n"
        )
        with self.assertRaises(ValueError):
            verify_d1_artifact.validate_build_bindings(self.root, self.results)

    def test_binary_digest_detachment_from_rootfs_is_rejected(self) -> None:
        path = self.root / "builds/build-a/rootfs-content-manifest.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["entries"][1]["sha256"] = "3" * 64
        document["entries_sha256"] = digest(
            json.dumps(
                document["entries"],
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
        self._refresh_build_manifest_metadata("build-a")
        with self.assertRaises(ValueError):
            verify_d1_artifact.validate_build_bindings(self.root, self.results)

    def test_rootfs_manifest_extra_field_is_rejected(self) -> None:
        path = self.root / "builds/build-b/rootfs-content-manifest.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["unexpected"] = True
        path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
        self._refresh_build_manifest_metadata("build-b")
        with self.assertRaises(ValueError):
            verify_d1_artifact.validate_build_bindings(self.root, self.results)


if __name__ == "__main__":
    unittest.main()
