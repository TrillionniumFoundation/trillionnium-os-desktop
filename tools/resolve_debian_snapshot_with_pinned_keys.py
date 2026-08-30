#!/usr/bin/env python3
"""Run the Debian snapshot resolver with explicit Debian 13 trust roots.

The Ubuntu runner's debian-archive-keyring can predate trixie. This wrapper
downloads Debian's official release-13 keys over HTTPS, verifies each primary
fingerprint against the repository contract, imports the keys into an isolated
GNUPG home, exports a deterministic OpenPGP public-key ring for gpgv/apt, runs
the package resolver, and binds every InRelease signature to an accepted
primary fingerprint. No unauthenticated apt mode is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any
from urllib.parse import urlsplit

from gate_evidence_envelope import load_json_strict

HEX_FINGERPRINT = re.compile(r"^[0-9A-F]{40,64}$")
TRUST_ROOT_HOST = "ftp-master.debian.org"
TRUST_ROOT_PATH_RE = re.compile(r"^/keys/[A-Za-z0-9][A-Za-z0-9._+-]*\.asc$")
TRUST_ROOT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
ARCHIVE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", re.ASCII)
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)


def validate_archive_id(value: Any) -> str:
    if not isinstance(value, str) or ARCHIVE_ID_RE.fullmatch(value) is None:
        raise RuntimeError(f"unsafe archive identifier: {value!r}")
    return value


def _has_symlink_component(path: Path) -> bool:
    """Check a raw CLI/path component without resolving symlinks first."""

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


def _reject_symlink_path(path: Path, label: str) -> None:
    if _has_symlink_component(path):
        raise RuntimeError(f"{label} path contains a symlink: {path}")


def _open_regular(path: Path, label: str, *, writable: bool = False) -> int:
    """Open a regular file without following a late symlink replacement."""

    _reject_symlink_path(path, label)
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
    _reject_symlink_path(path, label)
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


def _file_size(path: Path, label: str) -> int:
    descriptor = _open_regular(path, label)
    try:
        return os.fstat(descriptor).st_size
    finally:
        os.close(descriptor)


def validate_trust_root_url(value: Any, label: str) -> str:
    """Require one canonical Debian archive-key URL.

    Fingerprint pinning protects the bytes, while this check protects the
    custody metadata and redirect boundary.  In particular, a URL with
    userinfo, an alternate port, query/fragment data, or a path outside the
    official ``/keys/*.asc`` namespace must never be recorded as an official
    Debian trust root.
    """

    if not isinstance(value, str) or not value or value != value.strip():
        raise RuntimeError(f"{label} is not a clean URL")
    if any(ord(char) < 0x21 or ord(char) == 0x7f for char in value):
        raise RuntimeError(f"{label} contains whitespace or control characters")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
    except ValueError as error:
        raise RuntimeError(f"{label} is malformed: {value!r}") from error
    if (
        parsed.scheme != "https"
        or hostname != TRUST_ROOT_HOST
        or parsed.netloc.lower() != TRUST_ROOT_HOST
        or parsed.query
        or parsed.fragment
        or TRUST_ROOT_PATH_RE.fullmatch(parsed.path) is None
    ):
        raise RuntimeError(f"{label} is not an official Debian trust-root URL: {value!r}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    descriptor = _open_regular(path, "hashed resolver input")
    try:
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return digest.hexdigest()


def run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            f"{completed.stdout}"
        )
    return completed.stdout


def primary_fingerprints(colons: str) -> list[str]:
    fingerprints: list[str] = []
    expect_primary = False
    for line in colons.splitlines():
        fields = line.split(":")
        record = fields[0] if fields else ""
        if record == "pub":
            expect_primary = True
        elif record == "fpr" and expect_primary:
            value = fields[9].upper() if len(fields) > 9 else ""
            if not HEX_FINGERPRINT.fullmatch(value):
                raise RuntimeError(f"invalid OpenPGP primary fingerprint: {value!r}")
            fingerprints.append(value)
            expect_primary = False
        elif record in {"sub", "sec", "ssb"}:
            expect_primary = False
    return fingerprints


def export_public_keyring(
    *,
    keyring: Path,
    fingerprints: list[str],
    cwd: Path,
    env: dict[str, str],
) -> None:
    """Export a classic OpenPGP packet stream that gpgv and apt both accept."""
    command = ["gpg", "--batch", "--export", *fingerprints]
    descriptor = _open_regular(keyring, "exported archive keyring", writable=True)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as output:
            descriptor = -1
            completed = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                stdout=output,
                stderr=subprocess.PIPE,
                check=False,
            )
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n{stderr}"
        )
    if _file_size(keyring, "exported archive keyring") == 0:
        raise RuntimeError("exported Debian archive keyring is missing, empty, or unsafe")
    os.chmod(keyring, 0o644)


def build_keyring(
    requirements: dict[str, Any], work: Path
) -> tuple[Path, list[dict[str, Any]], dict[str, str]]:
    _reject_symlink_path(work, "trust-root work directory")
    work = work.absolute()
    if work.exists() and not work.is_dir():
        raise RuntimeError(f"trust-root work path is not a directory: {work}")
    root = work / "trust-roots"
    gnupg = work / "gnupg"
    for path, label in (
        (root, "trust-root directory"),
        (gnupg, "GNUPG directory"),
        (work / "debian-13-archive-keyring.gpg", "archive keyring"),
    ):
        _reject_symlink_path(path, label)
    root.mkdir(parents=True, exist_ok=True)
    gnupg.mkdir(parents=True, exist_ok=True, mode=0o700)
    _reject_symlink_path(root, "trust-root directory")
    _reject_symlink_path(gnupg, "GNUPG directory")
    os.chmod(gnupg, 0o700)
    env = os.environ.copy()
    env["GNUPGHOME"] = str(gnupg)
    keyring = work / "debian-13-archive-keyring.gpg"
    records: list[dict[str, Any]] = []
    expected_by_id: dict[str, str] = {}

    for item in requirements["trust_roots"]:
        identifier = item["id"]
        if not isinstance(identifier, str) or TRUST_ROOT_ID_RE.fullmatch(identifier) is None:
            raise RuntimeError(f"unsafe trust-root identifier: {identifier!r}")
        expected = item["primary_fingerprint"].upper()
        if not HEX_FINGERPRINT.fullmatch(expected):
            raise RuntimeError(f"invalid pinned fingerprint for {identifier}: {expected}")
        requested_url = validate_trust_root_url(item.get("url"), f"{identifier} URL")
        destination = root / f"{identifier}.asc"
        _reject_symlink_path(destination, f"trust-root {identifier}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        _reject_symlink_path(destination.parent, "trust-root directory")
        effective = run(
            [
                "curl",
                "--silent",
                "--fail",
                "--show-error",
                "--location",
                "--proto",
                "=https",
                "--tlsv1.2",
                "--retry",
                "5",
                "--retry-all-errors",
                "--user-agent",
                "TrillionniumOS-D0R02/3",
                "--output",
                str(destination),
                "--write-out",
                "%{url_effective}",
                requested_url,
            ],
            cwd=work,
        ).strip()
        validate_trust_root_url(effective, f"{identifier} effective URL")
        if urlsplit(effective).path != urlsplit(requested_url).path:
            raise RuntimeError(
                f"{identifier} effective URL path differs from requested path: "
                f"{effective!r}"
            )
        shown = run(
            [
                "gpg",
                "--batch",
                "--show-keys",
                "--with-colons",
                "--fingerprint",
                str(destination),
            ],
            cwd=work,
            env=env,
        )
        actual = primary_fingerprints(shown)
        if actual != [expected]:
            raise RuntimeError(
                f"trust-root fingerprint mismatch for {identifier}: {actual} != {[expected]}"
            )
        run(
            ["gpg", "--batch", "--import", str(destination)],
            cwd=work,
            env=env,
        )
        records.append(
            {
                "id": identifier,
                "requested_url": requested_url,
                "effective_url": effective,
                "primary_fingerprint": expected,
                "armored_sha256": sha256(destination),
                "armored_bytes": _file_size(
                    destination, f"trust-root {identifier}"
                ),
            }
        )
        expected_by_id[identifier] = expected

    listed = run(
        [
            "gpg",
            "--batch",
            "--with-colons",
            "--fingerprint",
            "--list-keys",
        ],
        cwd=work,
        env=env,
    )
    imported = sorted(primary_fingerprints(listed))
    expected = sorted(expected_by_id.values())
    if imported != expected:
        raise RuntimeError(f"isolated GNUPG key set mismatch: {imported} != {expected}")

    export_public_keyring(
        keyring=keyring,
        fingerprints=expected,
        cwd=work,
        env=env,
    )
    exported = run(
        [
            "gpg",
            "--batch",
            "--no-default-keyring",
            "--keyring",
            str(keyring),
            "--with-colons",
            "--fingerprint",
            "--list-keys",
        ],
        cwd=work,
        env=env,
    )
    exported_fingerprints = sorted(primary_fingerprints(exported))
    if exported_fingerprints != expected:
        raise RuntimeError(
            f"exported gpgv keyring mismatch: {exported_fingerprints} != {expected}"
        )
    return keyring, records, expected_by_id


def bind_inrelease_signers(
    requirements: dict[str, Any], report: dict[str, Any]
) -> None:
    """Normalize the signer evidence already verified by the base resolver.

    Debian InRelease files can carry additional co-signatures whose keys are not
    part of the deliberately minimal pinned trust set. The base resolver has
    already required at least one accepted valid primary signature and rejected
    every bad, expired or revoked signature state. Re-running strict gpgv here
    would incorrectly turn a recorded unknown co-signer into a gate failure.
    """
    by_id: dict[str, dict[str, Any]] = {}
    for item in requirements["archives"]:
        identifier = validate_archive_id(item.get("id"))
        if identifier in by_id:
            raise RuntimeError(f"duplicate archive identifier: {identifier}")
        by_id[identifier] = item
    for item in report["inrelease"]:
        archive = by_id[validate_archive_id(item.get("id"))]
        signing = sorted(set(item["valid_signature_fingerprints"]))
        primary = sorted(set(item["valid_primary_fingerprints"]))
        accepted = {value.upper() for value in archive["accepted_primary_fingerprints"]}
        if not accepted.intersection(primary):
            raise RuntimeError(
                f"{item['id']} signer primary fingerprints {primary} are not accepted "
                f"{sorted(accepted)}"
            )
        item["signing_fingerprints"] = signing
        item["primary_key_fingerprints"] = primary
        item["accepted_primary_fingerprints"] = sorted(accepted)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--logs", required=True, type=Path)
    args = parser.parse_args()

    for path, label in (
        (args.requirements, "requirements"),
        (args.output, "resolver output"),
        (args.work_dir, "resolver work directory"),
        (args.logs, "resolver logs"),
    ):
        _reject_symlink_path(path, label)
    if not args.requirements.is_file():
        raise SystemExit(f"requirements are missing or unsafe: {args.requirements}")

    requirements = _load_json_file(args.requirements, "requirements")
    archives = requirements.get("archives")
    if not isinstance(archives, list) or not archives:
        raise SystemExit("requirements archives must be a non-empty list")
    seen_archive_ids: set[str] = set()
    for item in archives:
        if not isinstance(item, dict):
            raise SystemExit("requirements archive must be an object")
        identifier = validate_archive_id(item.get("id"))
        if identifier in seen_archive_ids:
            raise SystemExit(f"duplicate archive identifier: {identifier}")
        seen_archive_ids.add(identifier)
    work = args.work_dir.absolute()
    output = args.output.absolute()
    logs = args.logs.absolute()
    if work.exists() and not work.is_dir():
        raise SystemExit(f"resolver work path is not a directory: {work}")
    if logs.exists() and not logs.is_dir():
        raise SystemExit(f"resolver logs path is not a directory: {logs}")
    work.mkdir(parents=True, exist_ok=True)
    keyring, trust_roots, _expected = build_keyring(requirements, work)

    delegated_requirements = dict(requirements)
    delegated_requirements["archive_keyring_path"] = str(keyring)
    delegated_path = work / "requirements.with-keyring.json"
    _reject_symlink_path(delegated_path, "delegated requirements")
    _write_text_file(
        delegated_path,
        json.dumps(delegated_requirements, indent=2, sort_keys=True) + "\n",
        "delegated requirements",
    )
    intermediate = work / "intermediate-lock.json"
    _reject_symlink_path(intermediate, "intermediate lock")
    resolver = Path(__file__).with_name("resolve_debian_snapshot.py")
    run(
        [
            sys.executable,
            str(resolver),
            "--requirements",
            str(delegated_path),
            "--output",
            str(intermediate),
            "--work-dir",
            str(work),
            "--logs",
            str(logs),
        ],
        cwd=Path.cwd(),
    )
    report = _load_json_file(intermediate, "intermediate lock")
    bind_inrelease_signers(requirements, report)
    report["archive_keyring"] = {
        "path_in_builder": str(keyring),
        "sha256": sha256(keyring),
        "bytes": _file_size(keyring, "archive keyring"),
        "bootstrap": "official_debian_https_plus_pinned_primary_fingerprints",
        "trust_roots": trust_roots,
    }
    report["resolver_policy"] = requirements["resolver_policy"]
    _write_text_file(
        output,
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        "resolver output",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001 - one fail-closed CLI boundary
        print(f"Pinned Debian snapshot resolution failed: {error}", file=sys.stderr)
        raise
