#!/usr/bin/env python3
"""Resolve and verify the signed Debian snapshot inputs for D1.

The resolver downloads only InRelease metadata, verifies every signature with
the Debian archive keyring, emits an exact apt sources list, and records the
source epoch and metadata digests. Package and image locks are added by the
build stage after mmdebstrap resolves the signed snapshot.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

TIMESTAMP_PATTERN = re.compile(r"^[0-9]{8}T[0-9]{6}Z$")
SUITE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9+.-]{0,63}$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], *, log: Path) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(completed.stdout)
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}; see {log}"
        )
    return completed


def parse_source_epoch(timestamp: str) -> int:
    if not TIMESTAMP_PATTERN.fullmatch(timestamp):
        raise ValueError(f"invalid snapshot timestamp: {timestamp}")
    moment = datetime.strptime(timestamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    return int(moment.timestamp())


def parse_valid_signers(status_output: str) -> list[str]:
    signers: list[str] = []
    for line in status_output.splitlines():
        marker = "[GNUPG:] VALIDSIG "
        if line.startswith(marker):
            fields = line[len(marker) :].split()
            if not fields or not re.fullmatch(r"[0-9A-F]{40,64}", fields[0]):
                raise RuntimeError(f"malformed VALIDSIG status: {line}")
            signers.append(fields[0])
    if not signers:
        raise RuntimeError("gpgv succeeded without a VALIDSIG fingerprint")
    return sorted(set(signers))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resolved-manifest", type=Path, required=True)
    parser.add_argument("--sources-list", type=Path, required=True)
    args = parser.parse_args()

    selection = json.loads(args.selection.read_text())
    if selection.get("schema") != "trillionnium.desktop.debian-d1-selection.v1":
        raise ValueError("unexpected Debian D1 selection schema")
    timestamp = selection["preferred_snapshot_timestamp"]
    source_epoch = parse_source_epoch(timestamp)
    architecture = selection["architecture"]
    if architecture != "amd64":
        raise ValueError(f"D1 currently supports amd64 only, received {architecture}")

    keyring = Path(selection["signature_keyring"])
    if not keyring.is_file():
        raise FileNotFoundError(f"Debian archive keyring is missing: {keyring}")

    output_dir = args.output_dir.resolve()
    inrelease_dir = output_dir / "inrelease"
    logs_dir = output_dir / "logs"
    inrelease_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, object]] = []
    source_lines: list[str] = []
    seen_suites: set[str] = set()

    for repository in selection["repositories"]:
        name = repository["name"]
        base_url = repository["base_url"].rstrip("/") + "/"
        if timestamp not in base_url:
            raise ValueError(f"repository {name} is not bound to timestamp {timestamp}")
        components = repository["components"]
        if components != ["main"]:
            raise ValueError(f"D1 repository {name} must use only main")
        for suite in repository["suites"]:
            if not SUITE_PATTERN.fullmatch(suite):
                raise ValueError(f"invalid suite name: {suite}")
            if suite in seen_suites:
                raise ValueError(f"duplicate suite: {suite}")
            seen_suites.add(suite)
            url = f"{base_url}dists/{suite}/InRelease"
            destination = inrelease_dir / f"{name}-{suite}-InRelease"
            run(
                [
                    "curl",
                    "--fail",
                    "--location",
                    "--silent",
                    "--show-error",
                    "--proto",
                    "=https",
                    "--tlsv1.2",
                    "--user-agent",
                    "TrillionniumOS-D1-Snapshot-Resolver/1",
                    url,
                    "--output",
                    str(destination),
                ],
                log=logs_dir / f"download-{name}-{suite}.log",
            )
            verification = run(
                [
                    "gpgv",
                    "--status-fd=1",
                    "--keyring",
                    str(keyring),
                    str(destination),
                ],
                log=logs_dir / f"gpgv-{name}-{suite}.log",
            )
            signers = parse_valid_signers(verification.stdout)
            records.append(
                {
                    "repository": name,
                    "suite": suite,
                    "url": url,
                    "sha256": sha256(destination),
                    "bytes": destination.stat().st_size,
                    "valid_signer_fingerprints": signers,
                }
            )
            options = f"check-valid-until=no signed-by={keyring}"
            source_lines.append(
                f"deb [{options}] {base_url} {suite} {' '.join(components)}"
            )

    if not records:
        raise RuntimeError("no signed Debian snapshot inputs were resolved")

    args.sources_list.parent.mkdir(parents=True, exist_ok=True)
    args.sources_list.write_text("\n".join(source_lines) + "\n")
    resolved = {
        "schema": "trillionnium.desktop.debian-d1-resolved.v1",
        "status": "PASS_SIGNED_INRELEASE",
        "suite": selection["suite"],
        "architecture": architecture,
        "snapshot_timestamp": timestamp,
        "source_date_epoch": source_epoch,
        "signature_keyring": str(keyring),
        "signature_keyring_sha256": sha256(keyring),
        "inrelease": sorted(records, key=lambda item: (item["repository"], item["suite"])),
        "sources_list_sha256": sha256(args.sources_list),
        "network_during_qemu_acceptance": False,
        "package_lock": None,
        "image": None,
    }
    args.resolved_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.resolved_manifest.write_text(json.dumps(resolved, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
