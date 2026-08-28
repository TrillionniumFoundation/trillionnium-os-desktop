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
import subprocess
import sys
import time
from typing import Any

HEX_FINGERPRINT = re.compile(r"^[0-9A-F]{40,64}$")
HEX_KEY_ID = re.compile(r"^[0-9A-F]{16,64}$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
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
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        f"$ {' '.join(command)}\n"
        f"exit={completed.returncode} elapsed_ms={round((time.monotonic() - started) * 1000)}\n\n"
        f"{output}",
        encoding="utf-8",
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
    for path in [lists / "partial", archives / "partial"]:
        path.mkdir(parents=True, exist_ok=True)
    status = state / "status"
    status.touch()
    extended = state / "extended_states"
    extended.touch()
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
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        f"$ {' '.join(command)}\n"
        f"exit={completed.returncode} elapsed_ms={round((time.monotonic() - started) * 1000)}\n\n"
        f"{output}",
        encoding="utf-8",
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
    archive_id = archive["id"]
    url = f"{archive['base_url'].rstrip('/')}/dists/{archive['suite']}/InRelease"
    destination = work / "inrelease" / f"{archive_id}.InRelease"
    destination.parent.mkdir(parents=True, exist_ok=True)
    curl = run(
        [
            "curl",
            "--fail",
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
    signature = verify_gpgv_signatures(
        archive_id=archive_id,
        accepted_primary_fingerprints=archive["accepted_primary_fingerprints"],
        keyring=keyring,
        destination=destination,
        work=work,
        log=logs / f"gpgv-{archive_id}.log",
    )
    text = destination.read_text(encoding="utf-8")
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
        "bytes": destination.stat().st_size,
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
    package_dir.mkdir(parents=True, exist_ok=True)
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
    actual_size = deb.stat().st_size
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

    requirements = json.loads(args.requirements.read_text(encoding="utf-8"))
    work = args.work_dir.resolve()
    logs = args.logs.resolve()
    work.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    keyring = Path(requirements["archive_keyring_path"])
    if not keyring.is_file() or keyring.is_symlink():
        raise RuntimeError(f"archive keyring is missing or unsafe: {keyring}")

    sources = work / "sources.list"
    source_lines = []
    for archive in requirements["archives"]:
        components = " ".join(archive["components"])
        source_lines.append(
            f"deb [check-valid-until=no signed-by={keyring}] "
            f"{archive['base_url']} {archive['suite']} {components}"
        )
    sources.write_text("\n".join(source_lines) + "\n", encoding="utf-8")
    apt = apt_options(work, sources, requirements["architecture"])

    inrelease = [
        verify_inrelease(archive, keyring, work, logs)
        for archive in requirements["archives"]
    ]
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
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001 - single fail-closed CLI boundary
        print(f"Debian snapshot resolution failed: {error}", file=sys.stderr)
        raise
