#!/usr/bin/env python3
"""Resolve and verify the signed Debian input closure for D0R-02.

The resolver uses an isolated empty dpkg status database, verifies every
InRelease against an archive-specific accepted signer set, resolves the complete
--no-install-recommends dependency closure, downloads every selected .deb and
checks its size and SHA-256 against apt metadata. It never creates an image.
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
import time
from typing import Any
from urllib.parse import urlsplit

from gate_evidence_envelope import load_json_strict

HEX_FINGERPRINT = re.compile(r"^[0-9A-F]{40,64}$")
HEX_KEY_ID = re.compile(r"^[0-9A-F]{16,64}$")
SNAPSHOT_HOST = "snapshot.debian.org"
SNAPSHOT_INRELEASE_PATH_RE = re.compile(r"^/file/[0-9a-f]{40}/InRelease$")
SNAPSHOT_ARCHIVE_BASE_RE = re.compile(
    r"^/archive/[A-Za-z0-9][A-Za-z0-9._+-]*/([0-9]{8}T[0-9]{6}Z)$",
    re.ASCII,
)
# Archive identifiers become filenames for downloaded metadata and resolver
# logs.  Keep them deliberately narrower than a general label so a malformed
# requirements file cannot escape the resolver work tree through ``../`` or
# inject control characters into shell/log output.
ARCHIVE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", re.ASCII)
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)


def _has_symlink_component(path: Path) -> bool:
    """Check a lexical path without resolving away symlink components."""

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
            raise RuntimeError(f"cannot inspect path component: {current}") from error
        if stat.S_ISLNK(mode):
            return True
    return False


def _reject_symlink_path(path: Path, label: str) -> None:
    if _has_symlink_component(path):
        raise RuntimeError(f"{label} path contains a symlink: {path}")


def _open_regular(path: Path, label: str, *, writable: bool = False) -> int:
    """Open a regular file with a no-follow final-component check."""

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


def _read_text_file(path: Path, label: str) -> str:
    descriptor = _open_regular(path, label)
    try:
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=True) as stream:
            descriptor = -1
            return stream.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


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


def _touch_regular(path: Path, label: str) -> None:
    """Create an empty regular file without following a preseeded link."""

    _reject_symlink_path(path, label)
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | _O_CLOEXEC | _O_NOFOLLOW | _O_NONBLOCK
    try:
        descriptor = os.open(path, flags, 0o644)
    except OSError as error:
        raise RuntimeError(f"{label} is absent or unsafe: {path}") from error
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise RuntimeError(f"{label} is not a regular file: {path}")
    finally:
        os.close(descriptor)


def validate_archive_id(value: Any) -> str:
    if not isinstance(value, str) or ARCHIVE_ID_RE.fullmatch(value) is None:
        raise RuntimeError(f"unsafe archive identifier: {value!r}")
    return value


def validate_archive_base_url(
    value: Any,
    *,
    expected_timestamp: str | None = None,
    label: str = "archive base URL",
) -> str:
    """Require a canonical, timestamped Debian snapshot archive URL.

    This check runs before ``curl`` is invoked.  Effective-URL validation
    after a download is necessary but too late to prevent a malicious
    requirements file from making an arbitrary outbound request.  Restrict
    the authority and path here so only the official snapshot service can be
    contacted, with no credentials, alternate ports, query strings, or path
    traversal.
    """

    if not isinstance(value, str) or not value or value != value.strip():
        raise RuntimeError(f"{label} is not a clean URL")
    if any(ord(char) < 0x21 or ord(char) == 0x7F for char in value):
        raise RuntimeError(f"{label} contains whitespace or control characters")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
    except ValueError as error:
        raise RuntimeError(f"{label} is malformed: {value!r}") from error
    match = SNAPSHOT_ARCHIVE_BASE_RE.fullmatch(parsed.path)
    if (
        parsed.scheme != "https"
        or hostname != SNAPSHOT_HOST
        or parsed.netloc.lower() != SNAPSHOT_HOST
        or parsed.query
        or parsed.fragment
        or match is None
    ):
        raise RuntimeError(
            f"{label} is not an official timestamped Debian snapshot URL: {value!r}"
        )
    timestamp = match.group(1)
    if expected_timestamp is not None and timestamp != expected_timestamp:
        raise RuntimeError(
            f"{label} timestamp {timestamp!r} does not match expected "
            f"snapshot {expected_timestamp!r}"
        )
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


def run(
    command: list[str],
    *,
    cwd: Path,
    log: Path,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        check=False,
    )
    output = completed.stdout or ""
    _write_text_file(
        log,
        f"$ {' '.join(command)}\n"
        f"exit={completed.returncode} elapsed_ms={round((time.monotonic() - started) * 1000)}\n\n"
        f"{output}",
        "resolver command log",
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}; see {log}"
        )
    return completed


def parse_control(text: str) -> list[dict[str, str]]:
    paragraphs: list[dict[str, str]] = []
    current: dict[str, str] = {}
    last_key: str | None = None
    for line in text.splitlines():
        if not line:
            if current:
                paragraphs.append(current)
                current = {}
                last_key = None
            continue
        if line[0].isspace() and last_key is not None:
            current[last_key] += "\n" + line[1:]
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        last_key = key
        current[key] = value.lstrip()
    if current:
        paragraphs.append(current)
    return paragraphs


def inrelease_payload(text: str) -> str:
    signature_marker = "-----BEGIN PGP SIGNATURE-----"
    if not text.startswith("-----BEGIN PGP SIGNED MESSAGE-----"):
        raise RuntimeError("InRelease is not an OpenPGP clearsigned message")
    try:
        header_end = text.index("\n\n") + 2
        signature_start = text.index(signature_marker)
    except ValueError as error:
        raise RuntimeError("malformed InRelease clearsign envelope") from error
    payload = text[header_end:signature_start]
    return "\n".join(
        line[2:] if line.startswith("- ") else line for line in payload.splitlines()
    ).rstrip() + "\n"


def apt_options(work: Path, sources: Path, architecture: str) -> list[str]:
    state = work / "apt-state"
    cache = work / "apt-cache"
    lists = state / "lists"
    archives = cache / "archives"
    for path, label in (
        (state, "APT state directory"),
        (cache, "APT cache directory"),
        (lists, "APT lists directory"),
        (archives, "APT archives directory"),
        (lists / "partial", "APT lists partial directory"),
        (archives / "partial", "APT archives partial directory"),
    ):
        _reject_symlink_path(path, label)
        path.mkdir(parents=True, exist_ok=True)
        _reject_symlink_path(path, label)
    status = state / "status"
    _touch_regular(status, "APT status database")
    extended = state / "extended_states"
    _touch_regular(extended, "APT extended state database")
    return [
        "-o",
        f"Dir::Etc::sourcelist={sources}",
        "-o",
        "Dir::Etc::sourceparts=-",
        "-o",
        f"Dir::State={state}",
        "-o",
        f"Dir::State::status={status}",
        "-o",
        f"Dir::State::extended_states={extended}",
        "-o",
        f"Dir::State::lists={lists}",
        "-o",
        f"Dir::Cache={cache}",
        "-o",
        f"Dir::Cache::archives={archives}",
        "-o",
        f"APT::Architecture={architecture}",
        "-o",
        f"APT::Architectures::={architecture}",
        "-o",
        "Acquire::Check-Valid-Until=false",
        "-o",
        "Acquire::AllowInsecureRepositories=false",
        "-o",
        "Acquire::AllowDowngradeToInsecureRepositories=false",
        "-o",
        "APT::Get::AllowUnauthenticated=false",
        "-o",
        "APT::Install-Recommends=false",
        "-o",
        "APT::Sandbox::User=root",
        "-o",
        "Debug::NoLocking=true",
    ]


def verify_gpgv_signatures(
    *,
    archive_id: str,
    accepted_primary_fingerprints: list[str],
    keyring: Path,
    destination: Path,
    work: Path,
    log: Path,
) -> dict[str, Any]:
    accepted = {value.upper() for value in accepted_primary_fingerprints}
    if not accepted or any(HEX_FINGERPRINT.fullmatch(value) is None for value in accepted):
        raise RuntimeError(f"{archive_id} has an invalid or empty accepted signer set")

    command = [
        "gpgv",
        "--status-fd=1",
        "--keyring",
        str(keyring),
        str(destination),
    ]
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=work,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = completed.stdout or ""
    _write_text_file(
        log,
        f"$ {' '.join(command)}\n"
        f"exit={completed.returncode} elapsed_ms={round((time.monotonic() - started) * 1000)}\n\n"
        f"{output}",
        "resolver signature log",
    )

    signing: set[str] = set()
    primary: set[str] = set()
    for line in output.splitlines():
        marker = "[GNUPG:] VALIDSIG "
        if marker not in line:
            continue
        fields = line.split(marker, 1)[1].split()
        if not fields:
            continue
        signer = fields[0].upper()
        if HEX_FINGERPRINT.fullmatch(signer):
            signing.add(signer)
        candidate = fields[-1].upper()
        primary.add(candidate if HEX_FINGERPRINT.fullmatch(candidate) else signer)

    unknown = {
        match.group(1).upper()
        for match in re.finditer(
            r"^\[GNUPG:\] NO_PUBKEY ([0-9A-F]{16,64})$",
            output,
            flags=re.MULTILINE,
        )
    }
    error_signers = {
        match.group(1).upper()
        for match in re.finditer(
            r"^\[GNUPG:\] ERRSIG ([0-9A-F]{16,64}) ",
            output,
            flags=re.MULTILINE,
        )
    }
    forbidden_statuses = [
        "BADSIG",
        "EXPSIG",
        "EXPKEYSIG",
        "REVKEYSIG",
        "KEYEXPIRED",
        "SIGEXPIRED",
        "NODATA",
        "FAILURE",
    ]
    observed_forbidden = [
        status
        for status in forbidden_statuses
        if f"[GNUPG:] {status}" in output
    ]
    if observed_forbidden:
        raise RuntimeError(
            f"{archive_id} gpgv reported forbidden signature states "
            f"{observed_forbidden}; see {log}"
        )
    if not signing or not primary or not accepted.intersection(primary):
        raise RuntimeError(
            f"{archive_id} has no valid signature from accepted primary keys "
            f"{sorted(accepted)}; observed={sorted(primary)}; see {log}"
        )
    if completed.returncode != 0:
        if not unknown or not error_signers or not error_signers.issubset(unknown):
            raise RuntimeError(
                f"{archive_id} gpgv failed for a reason other than additional unknown "
                f"co-signers (exit={completed.returncode}); see {log}"
            )

    return {
        "gpgv_exit_code": completed.returncode,
        "valid_signature_fingerprints": sorted(signing),
        "valid_primary_fingerprints": sorted(primary),
        "accepted_primary_fingerprints": sorted(accepted),
        "unknown_signature_key_ids": sorted(unknown),
    }


def verify_inrelease(
    archive: dict[str, Any],
    keyring: Path,
    work: Path,
    logs: Path,
) -> dict[str, Any]:
    archive_id = validate_archive_id(archive.get("id"))
    base_url = validate_archive_base_url(archive.get("base_url"))
    url = f"{base_url}/dists/{archive['suite']}/InRelease"
    destination = work / "inrelease" / f"{archive_id}.InRelease"
    _reject_symlink_path(destination.parent, "InRelease directory")
    _reject_symlink_path(destination, "InRelease destination")
    destination.parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink_path(destination.parent, "InRelease directory")
    curl = run(
        [
            "curl",
            "--fail",
            # Keep --write-out isolated from curl's progress meter.  run()
            # intentionally merges stderr into stdout for one complete log;
            # without --silent the progress UI becomes part of effective_url
            # and poisons the committed provenance field.
            "--silent",
            "--show-error",
            "--location",
            "--retry",
            "5",
            "--retry-all-errors",
            "--user-agent",
            "TrillionniumOS-D0R02/4",
            "--output",
            str(destination),
            "--write-out",
            "%{url_effective}",
            url,
        ],
        cwd=work,
        log=logs / f"curl-{archive_id}.log",
    )
    effective_url = curl.stdout.strip()
    parsed_effective = urlsplit(effective_url)
    if (
        parsed_effective.scheme != "https"
        or parsed_effective.hostname != SNAPSHOT_HOST
        or parsed_effective.netloc.lower() != SNAPSHOT_HOST
        or not SNAPSHOT_INRELEASE_PATH_RE.fullmatch(parsed_effective.path)
    ):
        raise RuntimeError(
            f"{archive_id} curl redirected to an unexpected effective URL: "
            f"{effective_url!r}"
        )
    signature = verify_gpgv_signatures(
        archive_id=archive_id,
        accepted_primary_fingerprints=archive["accepted_primary_fingerprints"],
        keyring=keyring,
        destination=destination,
        work=work,
        log=logs / f"gpgv-{archive_id}.log",
    )
    text = _read_text_file(destination, "downloaded InRelease")
    paragraphs = parse_control(inrelease_payload(text))
    if not paragraphs:
        raise RuntimeError(f"InRelease metadata is empty for {archive_id}")
    fields = paragraphs[0]
    if fields.get("Codename") != archive["suite"] and fields.get("Suite") != archive["suite"]:
        raise RuntimeError(
            f"{archive_id} signed suite mismatch: Suite={fields.get('Suite')} "
            f"Codename={fields.get('Codename')} expected={archive['suite']}"
        )
    return {
        "id": archive_id,
        "requested_url": url,
        "effective_url": effective_url,
        "suite": archive["suite"],
        "origin": fields.get("Origin"),
        "label": fields.get("Label"),
        "date": fields.get("Date"),
        "valid_until": fields.get("Valid-Until"),
        "sha256": sha256(destination),
        "bytes": _file_size(destination, "downloaded InRelease"),
        **signature,
    }


def parse_simulation(output: str) -> dict[str, str]:
    resolved: dict[str, str] = {}
    pattern = re.compile(r"^Inst\s+(\S+)\s+\((\S+)")
    for line in output.splitlines():
        match = pattern.match(line)
        if match is None:
            continue
        package, version = match.groups()
        existing = resolved.get(package)
        if existing is not None and existing != version:
            raise RuntimeError(
                f"apt simulation selected conflicting versions for {package}: "
                f"{existing} and {version}"
            )
        resolved[package] = version
    if not resolved:
        raise RuntimeError("apt simulation produced an empty dependency closure")
    return resolved


def package_metadata(
    package: str,
    version: str,
    *,
    apt: list[str],
    work: Path,
    logs: Path,
) -> dict[str, str]:
    completed = run(
        ["apt-cache", *apt, "show", "--no-all-versions", f"{package}={version}"],
        cwd=work,
        log=logs / "package-metadata" / f"{package.replace(':', '_')}.log",
    )
    paragraphs = parse_control(completed.stdout)
    matching = [item for item in paragraphs if item.get("Version") == version]
    if len(matching) != 1:
        raise RuntimeError(
            f"expected exactly one metadata paragraph for {package}={version}, got {len(matching)}"
        )
    fields = matching[0]
    required = ["Package", "Version", "Architecture", "Filename", "Size", "SHA256"]
    missing = [key for key in required if key not in fields]
    if missing:
        raise RuntimeError(f"metadata missing {missing} for {package}={version}")
    return {key: fields[key] for key in required}


def download_and_verify_package(
    package: str,
    version: str,
    metadata: dict[str, str],
    *,
    apt: list[str],
    work: Path,
    logs: Path,
) -> dict[str, Any]:
    package_dir = work / "downloads" / re.sub(r"[^A-Za-z0-9_.-]", "_", package)
    _reject_symlink_path(package_dir, f"download directory for {package}")
    package_dir.mkdir(parents=True, exist_ok=True)
    _reject_symlink_path(package_dir, f"download directory for {package}")
    run(
        ["apt-get", *apt, "download", f"{package}={version}"],
        cwd=package_dir,
        log=logs / "package-download" / f"{package.replace(':', '_')}.log",
    )
    debs = list(package_dir.glob("*.deb"))
    if len(debs) != 1:
        raise RuntimeError(
            f"expected exactly one downloaded .deb for {package}={version}, got {len(debs)}"
        )
    deb = debs[0]
    actual_size = _file_size(deb, f"downloaded package {package}")
    expected_size = int(metadata["Size"])
    if actual_size != expected_size:
        raise RuntimeError(
            f"size mismatch for {package}={version}: {actual_size} != {expected_size}"
        )
    actual_sha256 = sha256(deb)
    if actual_sha256 != metadata["SHA256"]:
        raise RuntimeError(
            f"SHA-256 mismatch for {package}={version}: "
            f"{actual_sha256} != {metadata['SHA256']}"
        )
    return {
        "package": metadata["Package"],
        "requested_name": package,
        "version": version,
        "architecture": metadata["Architecture"],
        "filename": metadata["Filename"],
        "size": actual_size,
        "sha256": actual_sha256,
    }


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
    expected_timestamp = requirements.get("snapshot_timestamp")
    if not isinstance(expected_timestamp, str) or not re.fullmatch(
        r"[0-9]{8}T[0-9]{6}Z", expected_timestamp
    ):
        raise RuntimeError("requirements snapshot_timestamp is malformed")
    archives = requirements.get("archives")
    if not isinstance(archives, list) or not archives:
        raise RuntimeError("requirements archives must be a non-empty list")
    # Validate every requested archive before creating apt sources or making
    # any network request.  The per-archive check in verify_inrelease remains
    # as a defense-in-depth guard for direct callers.
    for archive in archives:
        if not isinstance(archive, dict):
            raise RuntimeError("requirements archive must be an object")
        validate_archive_base_url(
            archive.get("base_url"), expected_timestamp=expected_timestamp
        )
    work = args.work_dir.absolute()
    logs = args.logs.absolute()
    work.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    keyring = Path(requirements["archive_keyring_path"])
    _reject_symlink_path(keyring, "archive keyring")
    if not keyring.is_file():
        raise RuntimeError(f"archive keyring is missing or unsafe: {keyring}")

    sources = work / "sources.list"
    source_lines = []
    seen_archive_ids: set[str] = set()
    for archive in archives:
        if not isinstance(archive, dict):
            raise RuntimeError("requirements archive must be an object")
        archive_id = validate_archive_id(archive.get("id"))
        if archive_id in seen_archive_ids:
            raise RuntimeError(f"duplicate archive identifier: {archive_id}")
        seen_archive_ids.add(archive_id)
        base_url = validate_archive_base_url(
            archive.get("base_url"), expected_timestamp=expected_timestamp
        )
        components = " ".join(archive["components"])
        source_lines.append(
            f"deb [check-valid-until=no signed-by={keyring}] "
            f"{base_url} {archive['suite']} {components}"
        )
    _write_text_file(
        sources,
        "\n".join(source_lines) + "\n",
        "APT sources list",
    )
    apt = apt_options(work, sources, requirements["architecture"])

    inrelease = [verify_inrelease(archive, keyring, work, logs) for archive in archives]
    run(
        ["apt-get", *apt, "update"],
        cwd=work,
        log=logs / "apt-update.log",
    )
    simulation = run(
        [
            "apt-get",
            *apt,
            "--simulate",
            "--no-install-recommends",
            "install",
            *requirements["seed_packages"],
        ],
        cwd=work,
        log=logs / "apt-simulate-install.log",
    )
    resolved = parse_simulation(simulation.stdout)

    packages = []
    for package, version in sorted(resolved.items()):
        metadata = package_metadata(
            package,
            version,
            apt=apt,
            work=work,
            logs=logs,
        )
        packages.append(
            download_and_verify_package(
                package,
                version,
                metadata,
                apt=apt,
                work=work,
                logs=logs,
            )
        )

    canonical_packages = json.dumps(
        packages, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    package_set_sha256 = hashlib.sha256(canonical_packages).hexdigest()
    keyring_version = subprocess.check_output(
        ["dpkg-query", "-W", "-f=${Version}", "debian-archive-keyring"],
        text=True,
    ).strip()
    fingerprints = sorted(
        {
            fingerprint
            for item in inrelease
            for fingerprint in item["valid_signature_fingerprints"]
        }
    )
    report = {
        "schema": "trillionnium.desktop.debian-snapshot-lock.v1",
        "status": "PASS_SIGNED_INPUT_AND_PACKAGE_CLOSURE_ONLY",
        "distribution": requirements["distribution"],
        "architecture": requirements["architecture"],
        "snapshot_timestamp": requirements["snapshot_timestamp"],
        "sources": source_lines,
        "inrelease": inrelease,
        "archive_keyring": {
            "path": str(keyring),
            "package_version": keyring_version,
            "sha256": sha256(keyring),
            "valid_signature_fingerprints": fingerprints,
        },
        "seed_packages": sorted(requirements["seed_packages"]),
        "resolved_package_count": len(packages),
        "packages": packages,
        "package_set_sha256": package_set_sha256,
        "resolver_policy": requirements["resolver_policy"],
        "claims": {
            "rootfs_created": False,
            "disk_image_created": False,
            "qemu_booted": False,
            "wayland_started": False,
            "secure_boot_enabled": False,
            "product_ready": False,
        },
        "next_gate": "D1-01 reproducible Debian rootfs and QEMU boot",
    }
    _write_text_file(
        args.output,
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        "resolver output",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001 - single fail-closed CLI boundary
        print(f"Debian snapshot resolution failed: {error}", file=sys.stderr)
        raise
