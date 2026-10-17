#!/usr/bin/env python3
"""Restore signed snapshot packages into a private root, without package scripts."""
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
import lzma
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time

BASE = "https://snapshot.ubuntu.com/ubuntu/20260828T000000Z/"
HERE = Path(__file__).resolve().parent
PREFIX = HERE.parent / "native-tools/root"
KEYRING = Path("/usr/share/keyrings/ubuntu-archive-keyring.gpg")
REQUESTED = ["clang", "lld", "qemu-system-x86", "busybox-static", "gdb", "seabios",
             "pkg-config", "libssl-dev", "cpio"]
LOCK = threading.Lock()


def sha256(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1048576), b""):
            result.update(block)
    return result.hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def execute(argv, log, **kwargs):
    started = time.time()
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("wb") as output:
        result = subprocess.run(argv, stdout=output, stderr=subprocess.STDOUT, **kwargs)
    record = {"argv": argv, "cwd": str(kwargs.get("cwd", Path.cwd())), "log": str(log.relative_to(HERE)),
              "raw_exit_code": result.returncode, "started_unix": started,
              "duration_seconds": time.time() - started}
    with LOCK, (HERE / "controller.jsonl").open("a") as output:
        output.write(json.dumps(record) + "\n")
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {log}")
    return record


def fetch(relative, destination, expected=None):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        execute(["/usr/bin/curl", "-q", "--fail", "--location", "--show-error", "--retry", "2",
                 "--max-time", "180", BASE + relative, "--output", str(destination)],
                HERE / "logs" / (destination.name + ".curl.log"), timeout=200)
    if expected and (destination.stat().st_size != expected["bytes"] or
                     sha256(destination) != expected["sha256"]):
        raise ValueError("signed metadata mismatch: " + str(destination))
    return {"url": BASE + relative, "retained": str(destination.relative_to(HERE)),
            "bytes": destination.stat().st_size, "sha256": sha256(destination)}


def paragraphs(source):
    current = {}
    previous = None
    for line in source:
        if not line.strip():
            if current:
                yield current
            current = {}
            previous = None
        elif line[:1].isspace() and previous:
            current[previous] += " " + line.strip()
        elif ":" in line:
            previous, value = line.split(":", 1)
            current[previous] = value.strip()
    if current:
        yield current


def prepare():
    for name in ("signed", "indexes", "apt-lists/partial", "debs", "logs", "cache"):
        (HERE / name).mkdir(parents=True, exist_ok=True)
    write_json(HERE / "controller-environment.json", {
        "snapshot": BASE, "private_prefix": str(PREFIX), "requested": REQUESTED,
        "keyring": str(KEYRING), "keyring_sha256": sha256(KEYRING),
        "policy": "Signature/hash/size verification; curl only; private extraction only. No APT sandbox changes, package scripts, account/service/library installation or privilege/namespace changes."})
    releases = {}
    for suite in ("noble", "noble-updates", "noble-security"):
        inrelease = HERE / "signed" / (suite + "-InRelease")
        fetched = fetch("dists/" + suite + "/InRelease", inrelease)
        release = HERE / "signed" / (suite + "-Release")
        if not release.exists():
            execute(["/usr/bin/gpgv", "--keyring", str(KEYRING), "--status-fd", "1",
                     "--output", str(release), str(inrelease)],
                    HERE / "logs" / (suite + ".gpgv.log"), timeout=30)
        lines = release.read_text().splitlines()
        hashes = {}
        active = False
        for line in lines:
            if line == "SHA256:":
                active = True
            elif line and not line[0].isspace():
                active = False
            elif active:
                value, size, path = line.split()
                hashes[path] = {"sha256": value, "bytes": int(size)}
        releases[suite] = {"inrelease": fetched, "release_sha256": sha256(release),
                           "headers": {line.split(":", 1)[0]: line.split(":", 1)[1].strip()
                                       for line in lines if line.startswith(("Date:", "Valid-Until:", "Suite:", "Codename:"))},
                           "indexes": {}}
        for component in ("main", "universe"):
            path = component + "/binary-amd64/Packages.xz"
            releases[suite]["indexes"][component] = {"relative": "dists/" + suite + "/" + path,
                                                        "expected": hashes[path]}
    jobs = [(suite, component, value) for suite, data in releases.items()
            for component, value in data["indexes"].items()]

    def get_index(job):
        suite, component, value = job
        path = HERE / "indexes" / (suite + "-" + component + "-Packages.xz")
        value["download"] = fetch(value["relative"], path, value["expected"])
        return suite, component, path

    with ThreadPoolExecutor(max_workers=3) as pool:
        indexes = list(pool.map(get_index, jobs))
    write_json(HERE / "signed-indexes.json", releases)
    packages = {}
    for suite, component, compressed in indexes:
        apt_name = "snapshot.ubuntu.com_ubuntu_20260828T000000Z_dists_" + suite + "_" + component + "_binary-amd64_Packages"
        plain = HERE / "apt-lists" / apt_name
        with lzma.open(compressed, "rb") as source, plain.open("wb") as target:
            shutil.copyfileobj(source, target)
        with plain.open() as source:
            for package in paragraphs(source):
                if package.get("Architecture") not in ("amd64", "all"):
                    continue
                key = (package["Package"], package["Version"])
                packages[key] = {field: package.get(field) for field in
                                 ("Package", "Version", "Architecture", "Filename", "Size", "SHA256", "Depends", "Pre-Depends")}
                packages[key]["suite"] = suite
                packages[key]["component"] = component
    sources = HERE / "sources.list"
    sources.write_text("".join("deb [signed-by=" + str(KEYRING) + "] " + BASE + " " + suite +
                              " main universe\n" for suite in releases))
    solver = ["/usr/bin/apt-get", "--simulate", "--no-install-recommends",
              "-o", "Dir::State::lists=" + str(HERE / "apt-lists"),
              "-o", "Dir::Cache::pkgcache=" + str(HERE / "cache/pkgcache.bin"),
              "-o", "Dir::Cache::srcpkgcache=" + str(HERE / "cache/srcpkgcache.bin"),
              "-o", "Dir::Etc::sourcelist=" + str(sources), "-o", "Dir::Etc::sourceparts=-",
              "install", *REQUESTED]
    execute(solver, HERE / "logs/apt-solver.log", timeout=120)
    chosen = []
    for line in (HERE / "logs/apt-solver.log").read_text().splitlines():
        match = re.match(r"Inst (\S+)(?: \[[^]]+\])? \((\S+) ", line)
        if match:
            name, version = match.groups()
            package = packages[(name.removesuffix(":amd64"), version)]
            package["Size"] = int(package["Size"])
            chosen.append(package)
    if not chosen:
        raise ValueError("APT solver produced no missing-package plan")
    if any(package["Package"] in ("libc6", "libc-bin") for package in chosen):
        raise ValueError("private plan unexpectedly selects host libc; review before extraction")
    write_json(HERE / "package-plan.json", chosen)
    print(json.dumps({"signature_verified_suites": list(releases), "signed_indexes": len(indexes),
                      "selected_packages": len(chosen), "download_bytes": sum(p["Size"] for p in chosen)}, indent=2))


def extract():
    plan = json.loads((HERE / "package-plan.json").read_text())

    def download(package):
        path = HERE / "debs" / Path(package["Filename"]).name
        observed = fetch(package["Filename"], path,
                         {"bytes": package["Size"], "sha256": package["SHA256"]})
        return package, path, observed

    with ThreadPoolExecutor(max_workers=4) as pool:
        downloaded = list(pool.map(download, plan))
    write_json(HERE / "verified-downloads.json", [
        {"package": package["Package"], "version": package["Version"],
         "architecture": package["Architecture"], "signed_index_suite": package["suite"],
         "signed_index_component": package["component"], **observed}
        for package, path, observed in downloaded])
    PREFIX.mkdir(parents=True, exist_ok=True)
    completed = []
    for package, path, observed in downloaded:
        identity = subprocess.check_output(["/usr/bin/dpkg-deb", "--show",
                                           "--showformat=${Package} ${Version} ${Architecture}\n", str(path)],
                                          text=True).strip()
        if identity != " ".join(package[field] for field in ("Package", "Version", "Architecture")):
            raise ValueError("downloaded package identity differs: " + str(path))
        record = execute(["/usr/bin/dpkg-deb", "--extract", str(path), str(PREFIX)],
                         HERE / "logs" / (package["Package"] + ".extract.log"), timeout=120)
        completed.append({"package": package["Package"], "version": package["Version"],
                          "deb_sha256": observed["sha256"], "deb_bytes": observed["bytes"],
                          "prefix": str(PREFIX), "identity_verified": identity,
                          "extraction_exit": record["raw_exit_code"],
                          "maintainer_scripts_executed": False})
        write_json(HERE / "extractions.json", completed)
    print(json.dumps({"private_prefix": str(PREFIX), "verified_downloads": len(downloaded),
                      "extracted_packages": len(completed), "system_install_performed": False,
                      "maintainer_scripts_executed": False}, indent=2))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract", action="store_true")
    arguments = parser.parse_args()
    extract() if arguments.extract else prepare()
