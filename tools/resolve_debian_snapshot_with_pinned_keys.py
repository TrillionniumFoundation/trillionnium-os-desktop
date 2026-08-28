#!/usr/bin/env python3
"""Run the Debian snapshot resolver with explicit Debian 13 trust roots.

The Ubuntu runner's debian-archive-keyring can predate trixie. This wrapper
downloads Debian's official release-13 keys over HTTPS, verifies each primary
fingerprint against the repository contract, builds an isolated keyring, runs
the package resolver, and then binds every InRelease signature to an accepted
primary fingerprint. No unauthenticated apt mode is used.
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
from typing import Any

HEX_FINGERPRINT = re.compile(r"^[0-9A-F]{40,64}$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
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


def build_keyring(
    requirements: dict[str, Any], work: Path
) -> tuple[Path, list[dict[str, Any]], dict[str, str]]:
    root = work / "trust-roots"
    gnupg = work / "gnupg"
    root.mkdir(parents=True, exist_ok=True)
    gnupg.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(gnupg, 0o700)
    env = os.environ.copy()
    env["GNUPGHOME"] = str(gnupg)
    keyring = work / "debian-13-archive-keyring.gpg"
    records: list[dict[str, Any]] = []
    expected_by_id: dict[str, str] = {}

    for item in requirements["trust_roots"]:
        identifier = item["id"]
        expected = item["primary_fingerprint"].upper()
        if not HEX_FINGERPRINT.fullmatch(expected):
            raise RuntimeError(f"invalid pinned fingerprint for {identifier}: {expected}")
        destination = root / f"{identifier}.asc"
        effective = run(
            [
                "curl",
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
                "TrillionniumOS-D0R02/2",
                "--output",
                str(destination),
                "--write-out",
                "%{url_effective}",
                item["url"],
            ],
            cwd=work,
        ).strip()
        if not effective.startswith("https://ftp-master.debian.org/keys/"):
            raise RuntimeError(
                f"unexpected effective trust-root URL for {identifier}: {effective}"
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
            [
                "gpg",
                "--batch",
                "--no-default-keyring",
                "--keyring",
                str(keyring),
                "--import",
                str(destination),
            ],
            cwd=work,
            env=env,
        )
        records.append(
            {
                "id": identifier,
                "requested_url": item["url"],
                "effective_url": effective,
                "primary_fingerprint": expected,
                "armored_sha256": sha256(destination),
                "armored_bytes": destination.stat().st_size,
            }
        )
        expected_by_id[identifier] = expected

    listed = run(
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
    imported = sorted(primary_fingerprints(listed))
    expected = sorted(expected_by_id.values())
    if imported != expected:
        raise RuntimeError(f"built keyring mismatch: {imported} != {expected}")
    return keyring, records, expected_by_id


def parse_validsig(status: str) -> tuple[list[str], list[str]]:
    signing: set[str] = set()
    primary: set[str] = set()
    for line in status.splitlines():
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
        if HEX_FINGERPRINT.fullmatch(candidate):
            primary.add(candidate)
        else:
            primary.add(signer)
    if not signing or not primary:
        raise RuntimeError("gpgv did not publish a valid signature fingerprint")
    return sorted(signing), sorted(primary)


def bind_inrelease_signers(
    requirements: dict[str, Any], report: dict[str, Any], keyring: Path, work: Path
) -> None:
    by_id = {item["id"]: item for item in requirements["archives"]}
    for item in report["inrelease"]:
        archive = by_id[item["id"]]
        inrelease = work / "inrelease" / f"{item['id']}.InRelease"
        status = run(
            [
                "gpgv",
                "--status-fd=1",
                "--keyring",
                str(keyring),
                str(inrelease),
            ],
            cwd=work,
        )
        signing, primary = parse_validsig(status)
        accepted = {value.upper() for value in archive["accepted_primary_fingerprints"]}
        if not accepted.intersection(primary):
            raise RuntimeError(
                f"{item['id']} signer primary fingerprints {primary} are not accepted {sorted(accepted)}"
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

    requirements = json.loads(args.requirements.read_text(encoding="utf-8"))
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    keyring, trust_roots, _expected = build_keyring(requirements, work)

    delegated_requirements = dict(requirements)
    delegated_requirements["archive_keyring_path"] = str(keyring)
    delegated_path = work / "requirements.with-keyring.json"
    delegated_path.write_text(
        json.dumps(delegated_requirements, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    intermediate = work / "intermediate-lock.json"
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
            str(args.logs.resolve()),
        ],
        cwd=Path.cwd(),
    )
    report = json.loads(intermediate.read_text(encoding="utf-8"))
    bind_inrelease_signers(requirements, report, keyring, work)
    report["archive_keyring"] = {
        "path_in_builder": str(keyring),
        "sha256": sha256(keyring),
        "bytes": keyring.stat().st_size,
        "bootstrap": "official_debian_https_plus_pinned_primary_fingerprints",
        "trust_roots": trust_roots,
    }
    report["resolver_policy"] = requirements["resolver_policy"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001 - one fail-closed CLI boundary
        print(f"Pinned Debian snapshot resolution failed: {error}", file=sys.stderr)
        raise
