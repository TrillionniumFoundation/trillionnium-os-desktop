#!/usr/bin/env python3
"""Materialize D1 builder inputs from the committed D0R-02 lock.

The script does not resolve packages. It validates the committed signed lock,
reconstructs only the pinned Debian trust roots, and emits exact package specs,
an expected installed-package TSV, a signed apt source list, and a compact
builder manifest. Any difference from the committed 319-package closure fails
closed before a root filesystem is created.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from resolve_debian_snapshot_with_pinned_keys import build_keyring

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]+$")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def parse_snapshot_epoch(timestamp: str) -> int:
    try:
        parsed = datetime.strptime(timestamp, "%Y%m%dT%H%M%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as error:
        raise RuntimeError(f"invalid snapshot timestamp: {timestamp}") from error
    return int(parsed.timestamp())


def validate_package(entry: dict[str, Any]) -> tuple[str, str, str]:
    required = {
        "package",
        "requested_name",
        "version",
        "architecture",
        "filename",
        "size",
        "sha256",
    }
    require(set(entry) == required, f"unexpected package fields: {sorted(entry)}")
    package = entry["package"]
    version = entry["version"]
    architecture = entry["architecture"]
    require(isinstance(package, str) and PACKAGE_RE.fullmatch(package) is not None,
            f"invalid package name: {package!r}")
    require(entry["requested_name"] == package,
            f"requested/package mismatch for {package}")
    require(isinstance(version, str) and version and "\n" not in version,
            f"invalid version for {package}")
    require(architecture in {"amd64", "all"},
            f"unexpected architecture for {package}: {architecture}")
    require(isinstance(entry["filename"], str)
            and entry["filename"].startswith("pool/")
            and ".." not in entry["filename"].split("/"),
            f"unsafe pool filename for {package}")
    require(isinstance(entry["size"], int) and entry["size"] > 0,
            f"invalid package size for {package}")
    require(isinstance(entry["sha256"], str)
            and SHA256_RE.fullmatch(entry["sha256"]) is not None,
            f"invalid package digest for {package}")
    return package, version, architecture


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--snapshot-lock", required=True, type=Path)
    parser.add_argument("--requirements", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    selection_path = args.selection.resolve()
    lock_path = args.snapshot_lock.resolve()
    requirements_path = args.requirements.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    requirements = json.loads(requirements_path.read_text(encoding="utf-8"))

    require(selection["status"] == "COMMITTED_SIGNED_INPUT_LOCK_REQUIRED",
            "D1 selection is not bound to a committed signed input lock")
    require(lock["status"] == "PASS_SIGNED_INPUT_AND_PACKAGE_CLOSURE_ONLY",
            f"unexpected D0R lock status: {lock.get('status')}")
    require(lock["next_gate"].startswith("D1-01"),
            "committed lock does not designate D1-01 as its next gate")
    require(selection["architecture"] == lock["architecture"] == requirements["architecture"],
            "architecture mismatch across D1 inputs")
    require(selection["snapshot_timestamp"] == lock["snapshot_timestamp"]
            == requirements["snapshot_timestamp"],
            "snapshot timestamp mismatch across D1 inputs")
    require(selection["expected_package_set_sha256"] == lock["package_set_sha256"],
            "D1 selection package-set digest does not match committed lock")
    require(all(value is False for value in lock["claims"].values()),
            "D0R lock contains a promoted runtime claim")

    packages = lock["packages"]
    require(isinstance(packages, list), "lock packages must be a list")
    require(len(packages) == selection["expected_package_count"],
            "locked package count does not match D1 selection")
    require(len(packages) == lock["resolved_package_count"],
            "locked package count does not match resolver result")

    canonical_package_digest = sha256_bytes(canonical_json(packages))
    require(canonical_package_digest == lock["package_set_sha256"],
            "committed package-set digest is not reproducible")

    seen: set[tuple[str, str]] = set()
    package_rows: list[tuple[str, str, str]] = []
    for entry in packages:
        require(isinstance(entry, dict), "package entry must be an object")
        package, version, architecture = validate_package(entry)
        identity = (package, architecture)
        require(identity not in seen, f"duplicate package identity: {identity}")
        seen.add(identity)
        package_rows.append((package, version, architecture))
    package_rows.sort()

    trust_work = output / "trust"
    keyring, trust_records, _expected = build_keyring(requirements, trust_work)
    committed_roots = {
        item["id"]: item for item in lock["archive_keyring"]["trust_roots"]
    }
    require(len(trust_records) == len(committed_roots),
            "trust-root count differs from committed lock")
    for item in trust_records:
        committed = committed_roots.get(item["id"])
        require(committed is not None, f"unexpected trust root: {item['id']}")
        require(item["primary_fingerprint"] == committed["primary_fingerprint"],
                f"trust-root fingerprint drift: {item['id']}")
        require(item["armored_sha256"] == committed["armored_sha256"],
                f"trust-root bytes drift: {item['id']}")

    sources_path = output / "sources.list"
    source_lines: list[str] = []
    for archive in requirements["archives"]:
        components = " ".join(archive["components"])
        source_lines.append(
            f"deb [check-valid-until=no signed-by={keyring}] "
            f"{archive['base_url']} {archive['suite']} {components}"
        )
    sources_path.write_text("\n".join(source_lines) + "\n", encoding="utf-8")

    exact_specs_path = output / "exact-packages.txt"
    exact_specs_path.write_text(
        "\n".join(f"{package}={version}" for package, version, _ in package_rows)
        + "\n",
        encoding="utf-8",
    )
    expected_tsv_path = output / "expected-package-lock.tsv"
    expected_tsv_path.write_text(
        "".join(
            f"{package}\t{version}\t{architecture}\n"
            for package, version, architecture in package_rows
        ),
        encoding="utf-8",
    )

    source_epoch = parse_snapshot_epoch(lock["snapshot_timestamp"])
    result = {
        "schema": "trillionnium.desktop.d1-prepared-inputs.v1",
        "status": "PASS_COMMITTED_SIGNED_INPUT_LOCK",
        "architecture": lock["architecture"],
        "suite": selection["suite"],
        "snapshot_timestamp": lock["snapshot_timestamp"],
        "source_date_epoch": source_epoch,
        "package_count": len(package_rows),
        "package_set_sha256": lock["package_set_sha256"],
        "snapshot_lock_sha256": sha256_file(lock_path),
        "snapshot_requirements_sha256": sha256_file(requirements_path),
        "selection_sha256": sha256_file(selection_path),
        "sources_list": str(sources_path),
        "sources_list_sha256": sha256_file(sources_path),
        "exact_packages": str(exact_specs_path),
        "exact_packages_sha256": sha256_file(exact_specs_path),
        "expected_package_lock": str(expected_tsv_path),
        "expected_package_lock_sha256": sha256_file(expected_tsv_path),
        "archive_keyring": {
            "path": str(keyring),
            "sha256": sha256_file(keyring),
            "trust_roots": trust_records,
        },
        "claims": {
            "rootfs_created": False,
            "disk_image_created": False,
            "qemu_booted": False,
            "wayland_started": False,
            "agent_port_activated": False,
            "servo_started": False,
            "product_ready": False,
        },
        "next_gate": "D1-01 two-build rootfs/image reproducibility and QEMU acceptance",
    }
    result_path = output / "prepared-inputs.json"
    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001 - fail-closed CLI boundary
        print(f"D1 input preparation failed: {error}", file=sys.stderr)
        raise
