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
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any
from urllib.parse import urlsplit

from gate_evidence_envelope import load_json_strict
from resolve_debian_snapshot import validate_archive_base_url
from resolve_debian_snapshot_with_pinned_keys import build_keyring

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]+$")
SNAPSHOT_HOST = "snapshot.debian.org"
SNAPSHOT_INRELEASE_PATH_RE = re.compile(r"^/file/[0-9a-f]{40}/InRelease$")
# ext4 superblock timestamp fields are unsigned 32-bit Unix seconds.  Keep
# the prepared manifest inside that representation so downstream D1/D2I image
# builders cannot silently truncate a seemingly bound source epoch.
EXT4_SUPERBLOCK_EPOCH_MIN = 1
EXT4_SUPERBLOCK_EPOCH_MAX = 0xFFFFFFFF
TRUST_ROOT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
ARCHIVE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", re.ASCII)
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)


def _has_symlink_component(path: Path) -> bool:
    """Check a raw CLI path before resolving it or following a symlink."""

    lexical = path if path.is_absolute() else Path.cwd() / path
    current = Path(lexical.anchor)
    for component in lexical.parts:
        if component in {lexical.anchor, "", "."}:
            continue
        if component == "..":
            current = current.parent
            continue
        current /= component
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            return False
        except OSError as error:
            raise ValueError(f"cannot inspect path component: {current}") from error
        if stat.S_ISLNK(mode):
            return True
    return False


def _reject_symlink_output(path: Path, label: str) -> None:
    """Reject an existing symlink anywhere in a generated output path."""

    if _has_symlink_component(path):
        raise RuntimeError(f"{label} path contains a symlink: {path}")


def _open_regular(path: Path, label: str, *, writable: bool = False) -> int:
    """Open one regular file without following a late symlink replacement."""

    if _has_symlink_component(path):
        raise RuntimeError(f"{label} path contains a symlink: {path}")
    flags = (os.O_WRONLY | os.O_CREAT | os.O_TRUNC) if writable else os.O_RDONLY
    flags |= _O_CLOEXEC | _O_NOFOLLOW | _O_NONBLOCK
    try:
        descriptor = os.open(path, flags, 0o644) if writable else os.open(path, flags)
    except OSError as error:
        raise RuntimeError(f"{label} is absent or unsafe: {path}") from error
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise RuntimeError(f"{label} is not a regular file: {path}")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _load_json_file(path: Path, label: str) -> dict[str, Any]:
    descriptor = _open_regular(path, label)
    try:
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=True) as stream:
            descriptor = -1
            value = load_json_strict(stream)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must be a JSON object: {path}")
    return value


def _write_text_file(path: Path, text: str, label: str) -> None:
    if _has_symlink_component(path):
        raise RuntimeError(f"{label} path contains a symlink: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = _open_regular(path, label, writable=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=True) as stream:
            descriptor = -1
            stream.write(text)
            stream.flush()
            try:
                os.fsync(stream.fileno())
            except OSError:
                pass
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    descriptor = _open_regular(path, "hashed D1 input")
    try:
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
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


def validate_archive_id(value: Any) -> str:
    require(
        isinstance(value, str) and ARCHIVE_ID_RE.fullmatch(value) is not None,
        f"unsafe archive identifier: {value!r}",
    )
    return value


def parse_snapshot_epoch(timestamp: str) -> int:
    try:
        parsed = datetime.strptime(timestamp, "%Y%m%dT%H%M%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as error:
        raise RuntimeError(f"invalid snapshot timestamp: {timestamp}") from error
    epoch = int(parsed.timestamp())
    if not EXT4_SUPERBLOCK_EPOCH_MIN <= epoch <= EXT4_SUPERBLOCK_EPOCH_MAX:
        raise RuntimeError(
            "snapshot timestamp epoch is outside the ext4 superblock range: "
            f"{timestamp} ({epoch})"
        )
    return epoch


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


def validate_inrelease_records(
    lock: dict[str, Any], requirements: dict[str, Any]
) -> None:
    """Validate the signed InRelease provenance carried by a committed lock.

    A committed lock bypasses the live resolver in the D1 pipeline, so this
    check must reject malformed or redirected provenance itself.  The resolver
    records the final Snapshot redirect (``/file/<sha1>/InRelease``); accepting
    arbitrary text here would make the lock's custody metadata meaningless.
    """

    archives = requirements.get("archives")
    records = lock.get("inrelease")
    require(isinstance(archives, list) and archives, "requirements have no archives")
    require(
        isinstance(records, list) and len(records) == len(archives),
        "lock InRelease record count does not match requirements",
    )
    by_id: dict[str, dict[str, Any]] = {}
    for raw in records:
        require(isinstance(raw, dict), "lock InRelease record must be an object")
        identifier = validate_archive_id(raw.get("id"))
        require(identifier not in by_id, f"duplicate lock InRelease id: {identifier}")
        by_id[identifier] = raw

    validated_archives: list[tuple[dict[str, Any], str]] = []
    seen_archive_ids: set[str] = set()
    for archive in archives:
        require(isinstance(archive, dict), "requirements archive must be an object")
        identifier = validate_archive_id(archive.get("id"))
        require(identifier not in seen_archive_ids, f"duplicate archive id: {identifier}")
        seen_archive_ids.add(identifier)
        validated_archives.append((archive, identifier))
    expected_ids = set(seen_archive_ids)
    require(
        expected_ids == set(by_id),
        "lock InRelease ids differ from requirements archives",
    )
    required_record_fields = {
        "id",
        "requested_url",
        "effective_url",
        "suite",
        "sha256",
        "bytes",
    }
    for archive, identifier in validated_archives:
        base_url = archive.get("base_url")
        suite = archive.get("suite")
        require(
            isinstance(identifier, str)
            and isinstance(base_url, str)
            and isinstance(suite, str),
            "requirements archive identity is malformed",
        )
        expected_timestamp = requirements.get("snapshot_timestamp")
        try:
            validated_base = validate_archive_base_url(
                base_url,
                expected_timestamp=(
                    expected_timestamp if isinstance(expected_timestamp, str) else None
                ),
                label=f"archive {identifier} base URL",
            )
        except RuntimeError as error:
            raise RuntimeError(str(error)) from error
        record = by_id[identifier]
        require(
            required_record_fields.issubset(record),
            f"lock InRelease record {identifier} omits required provenance fields",
        )
        requested = f"{validated_base.rstrip('/')}/dists/{suite}/InRelease"
        require(
            record["requested_url"] == requested,
            f"lock InRelease requested URL drifted for {identifier}",
        )
        effective = record["effective_url"]
        require(
            isinstance(effective, str)
            and effective == effective.strip()
            and not any(char.isspace() for char in effective),
            f"lock InRelease effective URL is contaminated for {identifier}",
        )
        parsed_effective = urlsplit(effective)
        require(
            parsed_effective.scheme == "https"
            and parsed_effective.hostname == SNAPSHOT_HOST
            and parsed_effective.netloc.lower() == SNAPSHOT_HOST
            and not parsed_effective.query
            and not parsed_effective.fragment
            and SNAPSHOT_INRELEASE_PATH_RE.fullmatch(parsed_effective.path)
            is not None,
            f"lock InRelease effective URL is not a Snapshot file for {identifier}",
        )
        require(
            record["id"] == identifier and record["suite"] == suite,
            f"lock InRelease identity drifted for {identifier}",
        )
        require(
            isinstance(record["sha256"], str)
            and SHA256_RE.fullmatch(record["sha256"]) is not None,
            f"lock InRelease digest is malformed for {identifier}",
        )
        require(
            isinstance(record["bytes"], int)
            and not isinstance(record["bytes"], bool)
            and record["bytes"] > 0,
            f"lock InRelease byte count is malformed for {identifier}",
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--baseline-lock", required=True, type=Path)
    parser.add_argument("--d1-lock", required=True, type=Path)
    parser.add_argument("--requirements", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    input_paths = (
        (args.selection, "selection"),
        (args.baseline_lock, "baseline lock"),
        (args.d1_lock, "D1 lock"),
        (args.requirements, "requirements"),
    )
    for path, label in input_paths:
        if _has_symlink_component(path):
            raise SystemExit(f"{label} path contains a symlink: {path}")
        if not path.is_file():
            raise SystemExit(f"{label} is missing or unsafe: {path}")
    if _has_symlink_component(args.output_dir):
        raise SystemExit(
            f"prepared-input output path contains a symlink: {args.output_dir}"
        )

    selection_path = args.selection.absolute()
    baseline_path = args.baseline_lock.absolute()
    d1_lock_path = args.d1_lock.absolute()
    requirements_path = args.requirements.absolute()
    output = args.output_dir.absolute()
    if output.exists() and not output.is_dir():
        raise SystemExit(f"prepared-input output is not a directory: {output}")
    output.mkdir(parents=True, exist_ok=True)

    selection = _load_json_file(selection_path, "D1 selection")
    baseline = _load_json_file(baseline_path, "D0R baseline lock")
    d1_lock = _load_json_file(d1_lock_path, "D1 package lock")
    requirements = _load_json_file(requirements_path, "D1 requirements")

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
    validate_inrelease_records(baseline, requirements)
    validate_inrelease_records(d1_lock, requirements)
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

    # build_keyring creates several files below this directory.  Check all
    # deterministic destinations before invoking it so a stale symlink cannot
    # redirect a key or GNUPG home write outside the prepared-input tree.
    trust_work = output / "trust"
    trust_roots = requirements.get("trust_roots")
    require(isinstance(trust_roots, list) and trust_roots, "requirements have no trust roots")
    generated_paths = [
        (trust_work, "trust workspace"),
        (trust_work / "trust-roots", "trust-root workspace"),
        (trust_work / "gnupg", "GNUPG workspace"),
        (trust_work / "debian-13-archive-keyring.gpg", "archive keyring"),
        (output / "sources.list", "sources list"),
        (output / "exact-packages.txt", "exact package list"),
        (output / "expected-package-lock.tsv", "expected package lock"),
        (output / "prepared-inputs.json", "prepared-input result"),
    ]
    for item in trust_roots:
        require(isinstance(item, dict), "trust root must be an object")
        identifier = item.get("id")
        require(
            isinstance(identifier, str) and TRUST_ROOT_ID_RE.fullmatch(identifier) is not None,
            f"unsafe trust root id: {identifier!r}",
        )
        generated_paths.append(
            (
                trust_work / "trust-roots" / f"{identifier}.asc",
                f"trust-root {identifier}",
            )
        )
    for generated_path, label in generated_paths:
        _reject_symlink_output(generated_path, label)

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
    _write_text_file(
        sources_path,
        "\n".join(source_lines) + "\n",
        "D1 sources list",
    )

    rows = sorted(
        (
            entry["package"],
            entry["version"],
            entry["architecture"],
        )
        for entry in d1_packages.values()
    )
    exact_specs_path = output / "exact-packages.txt"
    _write_text_file(
        exact_specs_path,
        "\n".join(f"{package}={version}" for package, version, _ in rows) + "\n",
        "D1 exact package list",
    )
    expected_tsv_path = output / "expected-package-lock.tsv"
    _write_text_file(
        expected_tsv_path,
        "".join(
            f"{package}\t{version}\t{architecture}\n"
            for package, version, architecture in rows
        ),
        "D1 expected package lock",
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
    _write_text_file(
        result_path,
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        "D1 prepared-input result",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001 - fail-closed CLI boundary
        print(f"D1 input preparation failed: {error}", file=sys.stderr)
        raise
