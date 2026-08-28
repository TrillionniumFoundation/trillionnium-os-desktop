#!/usr/bin/env python3
"""Offline, fail-closed consistency checks for the committed D0R-02 lock."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "manifests/debian-snapshot.lock.v1.json"
SELECTION_PATH = ROOT / "manifests/debian-base.selection.json"
REQUIREMENTS_PATH = ROOT / "manifests/debian-snapshot.requirements.v1.json"
DOCS_MANIFEST_PATH = ROOT / "docs/MANIFEST.json"
REPOSITORY_STATE_PATH = ROOT / "manifests/repository-state.json"
HEX40 = re.compile(r"^[0-9A-F]{40}$")
HEX64_LOWER = re.compile(r"^[0-9a-f]{64}$")
ERRORS: list[str] = []


def fail(message: str) -> None:
    ERRORS.append(message)


def load(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"cannot load {path.relative_to(ROOT)}: {error}")
        return {}
    if not isinstance(document, dict):
        fail(f"{path.relative_to(ROOT)} must contain a JSON object")
        return {}
    return document


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        fail(f"cannot hash {path.relative_to(ROOT)}: {error}")
        return ""
    return digest.hexdigest()


def check_lock() -> None:
    lock = load(LOCK_PATH)
    selection = load(SELECTION_PATH)
    requirements = load(REQUIREMENTS_PATH)
    docs = load(DOCS_MANIFEST_PATH)
    state = load(REPOSITORY_STATE_PATH)

    if lock.get("schema") != "trillionnium.desktop.debian-snapshot-lock.v1":
        fail("unexpected Debian lock schema")
    if lock.get("status") != "PASS_SIGNED_INPUT_AND_PACKAGE_CLOSURE_ONLY":
        fail("Debian lock status is not the D0R-02 pass status")
    if lock.get("distribution") != requirements.get("distribution"):
        fail("Debian lock distribution disagrees with requirements")
    if lock.get("architecture") != requirements.get("architecture"):
        fail("Debian lock architecture disagrees with requirements")
    if lock.get("snapshot_timestamp") != requirements.get("snapshot_timestamp"):
        fail("Debian lock timestamp disagrees with requirements")
    if lock.get("seed_packages") != sorted(requirements.get("seed_packages", [])):
        fail("Debian lock seed packages disagree with requirements")
    if lock.get("resolver_policy") != requirements.get("resolver_policy"):
        fail("Debian lock resolver policy disagrees with requirements")

    claims = lock.get("claims")
    expected_claims = {
        "rootfs_created",
        "disk_image_created",
        "qemu_booted",
        "wayland_started",
        "secure_boot_enabled",
        "product_ready",
    }
    if not isinstance(claims, dict) or set(claims) != expected_claims:
        fail("Debian lock claim ceiling fields changed")
    elif any(value is not False for value in claims.values()):
        fail("D0R-02 lock exceeds the signed-input-only claim ceiling")

    required_archives = {
        item.get("id"): item
        for item in requirements.get("archives", [])
        if isinstance(item, dict)
    }
    locked_archives = {
        item.get("id"): item
        for item in lock.get("inrelease", [])
        if isinstance(item, dict)
    }
    if set(required_archives) != {"debian", "debian-updates", "debian-security"}:
        fail("requirements do not contain the exact three frozen archives")
    if set(locked_archives) != set(required_archives):
        fail("Debian lock InRelease set disagrees with requirements")
    for archive_id, requirement in required_archives.items():
        record = locked_archives.get(archive_id, {})
        if record.get("suite") != requirement.get("suite"):
            fail(f"{archive_id} suite disagrees with requirements")
        accepted = set(requirement.get("accepted_primary_fingerprints", []))
        locked_accepted = set(record.get("accepted_primary_fingerprints", []))
        valid_primary = set(record.get("valid_primary_fingerprints", []))
        if locked_accepted != accepted:
            fail(f"{archive_id} accepted primary signer set changed")
        if not accepted.intersection(valid_primary):
            fail(f"{archive_id} lacks a valid signature from an accepted primary key")
        if any(HEX40.fullmatch(value) is None for value in accepted | valid_primary):
            fail(f"{archive_id} contains an invalid primary fingerprint")
        if HEX64_LOWER.fullmatch(str(record.get("sha256", ""))) is None:
            fail(f"{archive_id} lacks a valid InRelease SHA-256")
        exit_code = record.get("gpgv_exit_code")
        unknown = record.get("unknown_signature_key_ids", [])
        if exit_code not in {0, 2}:
            fail(f"{archive_id} has an unexpected gpgv exit code {exit_code!r}")
        if exit_code == 2 and not unknown:
            fail(f"{archive_id} nonzero gpgv exit lacks recorded unknown co-signers")

    required_roots = {
        item.get("id"): item.get("primary_fingerprint")
        for item in requirements.get("trust_roots", [])
        if isinstance(item, dict)
    }
    locked_roots = {
        item.get("id"): item.get("primary_fingerprint")
        for item in lock.get("archive_keyring", {}).get("trust_roots", [])
        if isinstance(item, dict)
    }
    if locked_roots != required_roots:
        fail("committed Debian trust roots disagree with requirements")
    if lock.get("archive_keyring", {}).get("bootstrap") != (
        "official_debian_https_plus_pinned_primary_fingerprints"
    ):
        fail("Debian keyring bootstrap policy changed")

    packages = lock.get("packages")
    if not isinstance(packages, list) or not packages:
        fail("Debian lock package closure is empty")
        packages = []
    keys: list[tuple[str, str, str]] = []
    for index, package in enumerate(packages):
        if not isinstance(package, dict):
            fail(f"package entry {index} is not an object")
            continue
        name = package.get("package")
        version = package.get("version")
        architecture = package.get("architecture")
        filename = package.get("filename")
        size = package.get("size")
        digest = package.get("sha256")
        if not all(isinstance(value, str) and value for value in (name, version, filename)):
            fail(f"package entry {index} has incomplete identity")
            continue
        if architecture not in {"amd64", "all"}:
            fail(f"package {name} has unexpected architecture {architecture!r}")
        if not isinstance(size, int) or size <= 0:
            fail(f"package {name} has invalid byte size")
        if HEX64_LOWER.fullmatch(str(digest)) is None:
            fail(f"package {name} has invalid SHA-256")
        keys.append((name, str(architecture), version))
    if keys != sorted(keys):
        fail("Debian package closure is not canonically sorted")
    if len(keys) != len(set(keys)):
        fail("Debian package closure contains duplicate package identities")
    if lock.get("resolved_package_count") != len(packages):
        fail("resolved package count disagrees with package entries")

    canonical = json.dumps(
        packages, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    recomputed_package_set = hashlib.sha256(canonical).hexdigest()
    if recomputed_package_set != lock.get("package_set_sha256"):
        fail("package-set SHA-256 does not match canonical package entries")

    snapshot = selection.get("snapshot_lock", {})
    if snapshot.get("resolved") is not True:
        fail("Debian base selection does not mark the snapshot resolved")
    if snapshot.get("lock_file") != "manifests/debian-snapshot.lock.v1.json":
        fail("Debian base selection points at the wrong lock")
    if snapshot.get("canonical_lock_file_sha256") != sha256_file(LOCK_PATH):
        fail("Debian base selection lock-file SHA-256 is stale")
    if snapshot.get("snapshot_timestamp") != lock.get("snapshot_timestamp"):
        fail("Debian base selection timestamp disagrees with lock")
    if snapshot.get("resolved_package_count") != len(packages):
        fail("Debian base selection package count disagrees with lock")
    if snapshot.get("package_set_sha256") != recomputed_package_set:
        fail("Debian base selection package-set SHA-256 disagrees with lock")

    if docs.get("debian_signed_snapshot_resolved") is not True:
        fail("docs manifest does not record the resolved Debian snapshot")
    if docs.get("debian_snapshot_lock") != "../manifests/debian-snapshot.lock.v1.json":
        fail("docs manifest points at the wrong Debian lock")
    if docs.get("debian_image_built") is not False:
        fail("docs manifest exceeds the D0R-02 no-image claim")
    if "D0R-02" not in state.get("completed_work_packages", []):
        fail("repository state does not mark D0R-02 complete")
    if "D0R-02" in state.get("partial_work_packages", []):
        fail("repository state still marks D0R-02 partial")
    if "debian_image_built" not in state.get("not_claimed", []):
        fail("repository state dropped the no-image claim")


def main() -> int:
    check_lock()
    if ERRORS:
        for error in ERRORS:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"Debian snapshot lock validation failed with {len(ERRORS)} error(s)", file=sys.stderr)
        return 1
    lock = load(LOCK_PATH)
    print(
        "Debian snapshot lock validation passed: "
        f"snapshot={lock['snapshot_timestamp']} "
        f"packages={lock['resolved_package_count']} "
        f"package_set_sha256={lock['package_set_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
