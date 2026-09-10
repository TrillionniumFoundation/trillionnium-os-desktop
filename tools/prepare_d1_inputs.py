#!/usr/bin/env python3
"""Validate and materialize exact D1 builder inputs.

The D0R-02 lock fixes the snapshot, trust roots, and baseline package closure.
A D1-specific lock may add only packages resolved from that same signed
snapshot. This tool verifies both locks, requires the complete D0R closure to
remain present byte-for-byte, rebuilds the pinned keyring, and emits exact
package/version inputs for an offline-equivalent rootfs transaction.
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
    require(
        isinstance(package, str) and PACKAGE_RE.fullmatch(package) is not None,
        f"invalid package name: {package!r}",
    )
    require(
        entry["requested_name"] == package,
        f"requested/package mismatch for {package}",
    )
    require(
        isinstance(version, str) and version and "\n" not in version,
        f"invalid version for {package}",
    )
    require(
        architecture in {"amd64", "all"},
        f"unexpected architecture for {package}: {architecture}",
    )
    require(
        isinstance(entry["filename"], str)
        and entry["filename"].startswith("pool/")
        and ".." not in entry["filename"].split("/"),
        f"unsafe pool filename for {package}",
    )
    require(
        isinstance(entry["size"], int) and entry["size"] > 0,
        f"invalid package size for {package}",
    )
    require(
        isinstance(entry["sha256"], str)
        and SHA256_RE.fullmatch(entry["sha256"]) is not None,
        f"invalid package digest for {package}",
    )
    return package, version, architecture


def package_map(lock: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    packages = lock.get("packages")
    require(isinstance(packages, list), "lock packages must be a list")
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in packages:
        require(isinstance(raw, dict), "package entry must be an object")
        package, _version, architecture = validate_package(raw)
        identity = (package, architecture)
        require(identity not in result, f"duplicate package identity: {identity}")
        result[identity] = raw
    require(
        len(result) == lock.get("resolved_package_count"),
        "lock package count does not match resolver result",
    )
    require(
        sha256_bytes(canonical_json(packages)) == lock.get("package_set_sha256"),
        "lock package-set digest is not reproducible",
    )
    return result


def trust_root_map(lock: dict[str, Any]) -> dict[str, dict[str, Any]]:
    roots = lock.get("archive_keyring", {}).get("trust_roots")
    require(isinstance(roots, list) and roots, "lock has no pinned trust roots")
    result: dict[str, dict[str, Any]] = {}
    for root in roots:
        require(isinstance(root, dict), "trust root must be an object")
        identifier = root.get("id")
        require(isinstance(identifier, str), "trust root id is missing")
        require(identifier not in result, f"duplicate trust root {identifier}")
        result[identifier] = root
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--baseline-lock", required=True, type=Path)
    parser.add_argument("--d1-lock", required=True, type=Path)
    parser.add_argument("--requirements", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    selection_path = args.selection.resolve()
    baseline_path = args.baseline_lock.resolve()
    d1_lock_path = args.d1_lock.resolve()
    requirements_path = args.requirements.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    d1_lock = json.loads(d1_lock_path.read_text(encoding="utf-8"))
    requirements = json.loads(requirements_path.read_text(encoding="utf-8"))

    require(
        selection.get("schema") == "trillionnium.desktop.debian-d1-selection.v3",
        "unexpected D1 selection schema",
    )
    require(
        selection.get("status")
        in {
            "SIGNED_D1_CLOSURE_RESOLUTION_REQUIRED",
            "COMMITTED_SIGNED_D1_PACKAGE_LOCK",
        },
        "D1 selection is not in a lock-qualified state",
    )
    require(
        baseline.get("status") == "PASS_SIGNED_INPUT_AND_PACKAGE_CLOSURE_ONLY",
        f"unexpected D0R baseline status: {baseline.get('status')}",
    )
    require(
        d1_lock.get("status") == "PASS_SIGNED_INPUT_AND_PACKAGE_CLOSURE_ONLY",
        f"unexpected D1 lock status: {d1_lock.get('status')}",
    )

    architecture = selection.get("architecture")
    timestamp = selection.get("snapshot_timestamp")
    require(
        architecture
        == baseline.get("architecture")
        == d1_lock.get("architecture")
        == requirements.get("architecture"),
        "architecture mismatch across D1 inputs",
    )
    require(
        timestamp
        == baseline.get("snapshot_timestamp")
        == d1_lock.get("snapshot_timestamp")
        == requirements.get("snapshot_timestamp"),
        "snapshot timestamp mismatch across D1 inputs",
    )
    require(
        selection.get("baseline_package_count")
        == baseline.get("resolved_package_count"),
        "selection baseline package count drifted",
    )
    require(
        selection.get("baseline_package_set_sha256")
        == baseline.get("package_set_sha256"),
        "selection baseline package digest drifted",
    )
    require(
        sorted(requirements.get("seed_packages", []))
        == sorted(d1_lock.get("seed_packages", [])),
        "D1 lock seed package set differs from requirements",
    )
    require(
        all(value is False for value in baseline.get("claims", {}).values()),
        "D0R baseline contains a promoted runtime claim",
    )
    require(
        all(value is False for value in d1_lock.get("claims", {}).values()),
        "D1 package lock contains a promoted runtime claim",
    )

    baseline_packages = package_map(baseline)
    d1_packages = package_map(d1_lock)
    for identity, expected in baseline_packages.items():
        actual = d1_packages.get(identity)
        require(actual is not None, f"D1 closure dropped baseline package {identity}")
        require(
            actual == expected,
            f"D1 closure changed baseline package bytes or metadata: {identity}",
        )

    committed_lock = selection.get("committed_d1_lock")
    if selection["status"] == "COMMITTED_SIGNED_D1_PACKAGE_LOCK":
        require(
            committed_lock == "manifests/debian-d1.lock.v1.json",
            "selection committed D1 lock path is not canonical",
        )
        require(
            d1_lock_path == (selection_path.parents[1] / committed_lock).resolve(),
            "prepared D1 lock is not the committed canonical lock",
        )
        require(
            selection.get("expected_d1_package_count")
            == d1_lock.get("resolved_package_count"),
            "committed D1 package count drifted",
        )
        require(
            selection.get("expected_d1_package_set_sha256")
            == d1_lock.get("package_set_sha256"),
            "committed D1 package digest drifted",
        )

    baseline_roots = trust_root_map(baseline)
    d1_roots = trust_root_map(d1_lock)
    require(set(baseline_roots) == set(d1_roots), "D1 trust-root set changed")
    for identifier, expected in baseline_roots.items():
        actual = d1_roots[identifier]
        for field in ("primary_fingerprint", "armored_sha256"):
            require(
                actual.get(field) == expected.get(field),
                f"D1 trust root {identifier} changed {field}",
            )

    trust_work = output / "trust"
    keyring, trust_records, _expected = build_keyring(requirements, trust_work)
    reconstructed = {item["id"]: item for item in trust_records}
    require(
        set(reconstructed) == set(d1_roots),
        "reconstructed trust-root set differs from D1 lock",
    )
    for identifier, item in reconstructed.items():
        locked = d1_roots[identifier]
        require(
            item["primary_fingerprint"] == locked["primary_fingerprint"],
            f"trust-root fingerprint drift: {identifier}",
        )
        require(
            item["armored_sha256"] == locked["armored_sha256"],
            f"trust-root bytes drift: {identifier}",
        )

    sources_path = output / "sources.list"
    source_lines: list[str] = []
    for archive in requirements["archives"]:
        components = " ".join(archive["components"])
        source_lines.append(
            f"deb [check-valid-until=no signed-by={keyring}] "
            f"{archive['base_url']} {archive['suite']} {components}"
        )
    sources_path.write_text("\n".join(source_lines) + "\n", encoding="utf-8")

    rows = sorted(
        (
            entry["package"],
            entry["version"],
            entry["architecture"],
        )
        for entry in d1_packages.values()
    )
    exact_specs_path = output / "exact-packages.txt"
    exact_specs_path.write_text(
        "\n".join(f"{package}={version}" for package, version, _ in rows) + "\n",
        encoding="utf-8",
    )
    expected_tsv_path = output / "expected-package-lock.tsv"
    expected_tsv_path.write_text(
        "".join(
            f"{package}\t{version}\t{architecture}\n"
            for package, version, architecture in rows
        ),
        encoding="utf-8",
    )

    source_epoch = parse_snapshot_epoch(timestamp)
    result = {
        "schema": "trillionnium.desktop.d1-prepared-inputs.v2",
        "status": (
            "PASS_COMMITTED_SIGNED_D1_PACKAGE_LOCK"
            if selection["status"] == "COMMITTED_SIGNED_D1_PACKAGE_LOCK"
            else "PASS_GENERATED_SIGNED_D1_PACKAGE_LOCK"
        ),
        "architecture": architecture,
        "suite": selection["suite"],
        "snapshot_timestamp": timestamp,
        "source_date_epoch": source_epoch,
        "baseline_package_count": len(baseline_packages),
        "baseline_package_set_sha256": baseline["package_set_sha256"],
        "package_count": len(rows),
        "package_set_sha256": d1_lock["package_set_sha256"],
        "baseline_lock_sha256": sha256_file(baseline_path),
        "d1_lock_sha256": sha256_file(d1_lock_path),
        "requirements_sha256": sha256_file(requirements_path),
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
        "next_gate": "D1-01 two-build image reproducibility and PID1 acceptance",
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
