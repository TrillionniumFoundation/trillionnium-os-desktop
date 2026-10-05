#!/usr/bin/env python3
"""Signed G6a closure with bounded parallel exact-byte downloads.

Reuse the existing Debian signature/apt metadata validators. Only transfer is
parallel: curl downloads the exact HTTPS URI selected by authenticated apt;
every completed package is checked against the signed index's size and SHA256.
No host apt configuration, installation or D1/D2I resolver is changed.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

import resolve_debian_snapshot as base
from resolve_debian_snapshot_with_pinned_keys import build_keyring, bind_inrelease_signers


def transfer(uri, partial, size, directory, logs, safe):
    options = ["curl", "--silent", "--fail", "--show-error", "--location", "--proto", "=https", "--proto-redir", "=https", "--retry", "2", "--retry-all-errors", "--connect-timeout", "30", "--max-time", "1800"]
    if size < 16 * 1024**2:
        base.run([*options, "--output", str(partial), uri], cwd=directory, log=logs / "package-download" / (safe + ".log"))
        return
    # One large signed kernel package would otherwise serialize the transfer.
    # Require exact 206 Content-Range and chunk length; only the final complete
    # signed-index SHA256 admits the assembled file. Keep all failed chunks.
    chunk_bytes = (size + 7) // 8
    def segment(index):
        start, end = index * chunk_bytes, min((index + 1) * chunk_bytes, size) - 1
        destination = directory / ("segment-%02d" % index)
        headers = destination.with_suffix(".headers")
        if destination.exists() or headers.exists():
            raise RuntimeError("unconfirmed interrupted segments retained; use a new resolution directory")
        base.run([*options, "--range", f"{start}-{end}", "--dump-header", str(headers), "--output", str(destination), uri], cwd=directory, log=logs / "package-download" / (safe + "-segment-%02d.log" % index))
        if headers.stat().st_size > 65536:
            raise RuntimeError("bounded HTTP range header required")
        header_bytes = headers.read_bytes()
        statuses = re.findall(rb"(?im)^HTTP/(?:1\.[01]|2|3)\s+(\d{3})(?:\s|$)", header_bytes)
        ranges = re.findall(rb"(?im)^content-range:\s*bytes (\d+)-(\d+)/(\d+)\s*$", header_bytes)
        if not statuses or statuses[-1] != b"206" or not ranges or tuple(map(int, ranges[-1])) != (start, end, size) or destination.stat().st_size != end - start + 1:
            raise RuntimeError("exact actual HTTP range required")
        return destination
    with ThreadPoolExecutor(max_workers=8) as pool:
        segments = list(pool.map(segment, range(8)))
    with partial.open("xb") as output:
        for path in segments:
            with path.open("rb") as stream:
                while chunk := stream.read(1024**2):
                    output.write(chunk)


def download(item, apt, work, logs, archives):
    package, version, metadata = item
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", package)
    directory = work / "downloads" / safe
    directory.mkdir(parents=True, exist_ok=True)
    filename = metadata["Filename"]
    if not 0 < int(metadata["Size"]) <= 512 * 1024**2:
        raise RuntimeError("bounded package size required")
    if not filename.startswith("pool/") or not re.fullmatch(r"[A-Za-z0-9_+./:~%-]+", filename) or ".." in filename.split("/"):
        raise RuntimeError("unsafe authenticated pool filename")
    existing = list(directory.glob("*.deb"))
    if existing:
        if len(existing) != 1 or existing[0].is_symlink() or existing[0].stat().st_size != int(metadata["Size"]) or base.sha256(existing[0]) != metadata["SHA256"]:
            raise RuntimeError("existing package download is unconfirmed; retain and refuse")
        return {"package": metadata["Package"], "requested_name": package, "version": version,
                "architecture": metadata["Architecture"], "filename": filename,
                "size": existing[0].stat().st_size, "sha256": base.sha256(existing[0])}
    completed = base.run(["apt-get", *apt, "--print-uris", "download", f"{package}={version}"], cwd=directory, log=logs / "package-uri" / (safe + ".log"))
    lines = [shlex.split(line) for line in completed.stdout.splitlines() if line.startswith("'https://")]
    if len(lines) != 1:
        raise RuntimeError("exact authenticated apt package URI required")
    uri = lines[0][0]
    if not any(uri.startswith(archive["base_url"] + "/pool/") for archive in archives):
        raise RuntimeError("package URI outside fixed HTTPS snapshot")
    destination = directory / Path(filename).name
    if not existing:
        partial = destination.with_suffix(".partial")
        if partial.exists():
            raise RuntimeError("interrupted partial input retained; use a new resolution directory")
        transfer(uri, partial, int(metadata["Size"]), directory, logs, safe)
        if partial.stat().st_size != int(metadata["Size"]) or base.sha256(partial) != metadata["SHA256"]:
            raise RuntimeError("actual package bytes differ from signed index")
        partial.replace(destination)
    else:
        destination = existing[0]
    return {"package": metadata["Package"], "requested_name": package, "version": version,
            "architecture": metadata["Architecture"], "filename": filename,
            "size": destination.stat().st_size, "sha256": base.sha256(destination)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--logs", type=Path, required=True)
    args = parser.parse_args()
    requirements = json.loads(args.requirements.read_bytes())
    if requirements["schema"] != "trillionnium.desktop.debian-g6a-requirements.v1" or requirements["architecture"] != "amd64" or requirements["snapshot_timestamp"] != "20260828T000000Z":
        raise RuntimeError("independent fixed G6a requirements required")
    expected_roots = {"debian-13-archive": "04B54C3CDCA79751B16BC6B5225629DF75B188BD", "debian-13-security": "5E04A1E3223A19A20706E20F9904613D4CCE68C6", "debian-13-release": "41587F7DB8C774BCCF131416762F67A0B2C39DE4"}
    if {item["id"]: item["primary_fingerprint"] for item in requirements["trust_roots"]} != expected_roots:
        raise RuntimeError("fixed independently pinned Debian roots required")
    if {item["id"]: item["base_url"] for item in requirements["archives"]} != {"debian": "https://snapshot.debian.org/archive/debian/20260828T000000Z", "debian-updates": "https://snapshot.debian.org/archive/debian/20260828T000000Z", "debian-security": "https://snapshot.debian.org/archive/debian-security/20260828T000000Z"}:
        raise RuntimeError("fixed authenticated snapshot archives required")
    work, logs = args.work_dir.resolve(), args.logs.resolve()
    work.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    keyring, roots, _ = build_keyring(requirements, work)
    sources = work / "sources.list"
    source_lines = [f"deb [check-valid-until=no signed-by={keyring}] {archive['base_url']} {archive['suite']} {' '.join(archive['components'])}" for archive in requirements["archives"]]
    sources.write_text("\n".join(source_lines) + "\n")
    apt = base.apt_options(work, sources, "amd64")
    # Explicit command arguments disable only irrelevant translation/appstream
    # transfers, including desktop-host apt overrides. Signature checks remain.
    for key, value in (("Acquire::Languages", "none"), ("Acquire::Retries", "2"), ("Acquire::https::Timeout", "30")):
        apt += ["-o", key + "=" + value]
    for target in ("DEP-11", "DEP-11-icons-small", "DEP-11-icons", "DEP-11-icons-hidpi", "DEP-11-icons-large", "DEP-11-icons-large-hidpi"):
        apt += ["-o", "Acquire::IndexTargets::deb::" + target + "::DefaultEnabled=false"]
    inrelease = [base.verify_inrelease(archive, keyring, work, logs) for archive in requirements["archives"]]
    base.run(["apt-get", *apt, "update"], cwd=work, log=logs / "apt-update.log")
    simulation = base.run(["apt-get", *apt, "--simulate", "--no-install-recommends", "install", *requirements["seed_packages"]], cwd=work, log=logs / "apt-simulate-install.log")
    resolved = base.parse_simulation(simulation.stdout)
    items = [(package, version, base.package_metadata(package, version, apt=apt, work=work, logs=logs)) for package, version in sorted(resolved.items())]
    with ThreadPoolExecutor(max_workers=8) as pool:
        packages = list(pool.map(lambda item: download(item, apt, work, logs, requirements["archives"]), items))
    canonical = json.dumps(packages, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    report = {"schema": "trillionnium.desktop.debian-snapshot-lock.v1", "status": "PASS_SIGNED_INPUT_AND_PACKAGE_CLOSURE_ONLY", "distribution": requirements["distribution"], "architecture": "amd64", "snapshot_timestamp": requirements["snapshot_timestamp"], "sources": source_lines, "inrelease": inrelease,
              "archive_keyring": {"path_in_builder": str(keyring), "sha256": base.sha256(keyring), "bytes": keyring.stat().st_size, "bootstrap": "official_debian_https_plus_pinned_primary_fingerprints", "trust_roots": roots},
              "seed_packages": sorted(requirements["seed_packages"]), "resolved_package_count": len(packages), "packages": packages, "package_set_sha256": hashlib.sha256(canonical).hexdigest(), "resolver_policy": requirements["resolver_policy"],
              "claims": {"rootfs_created": False, "disk_image_created": False, "qemu_booted": False, "wayland_started": False, "secure_boot_enabled": False, "product_ready": False}, "next_gate": "test-only G6a installed immutable root and attempt matrix"}
    bind_inrelease_signers(requirements, report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "actual_packages": len(packages), "package_set_sha256": report["package_set_sha256"], "production_activation_enabled": False}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print("signed G6a input resolution refused: " + str(error), file=sys.stderr)
        raise SystemExit(1)
