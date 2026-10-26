#!/usr/bin/env python3
"""Package the original Desktop payload and its same-source Linux Root tools.

Installing a verified bundle does not initialize authority or start services.
The Desktop and Root supplement retain separate 512 MiB payload bounds and
the original 128 MiB per-file bound. One manifest binds both immutable parts.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tarfile
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
if (HERE / "desktop").is_dir():
    sys.path.insert(0, str(HERE / "desktop"))
import desktop

PROGRAMS = ("hepta-desktop-root", "codex-hepta-agentd", "hepta-authority-host", "codex-app-server")
EXTRA_FILES = {"build-receipt.json", "desktop-build-receipt.json", "root_bundle.py",
               "ROOT_PRODUCT.md", "libexec/native_human.py"}
PACKAGING_SOURCES = {"root_bundle.py": "support/ui/product/root_bundle.py",
                     "ROOT_PRODUCT.md": "support/ui/ROOT_PRODUCT.md",
                     "libexec/native_human.py": "support/ui/product/native_human.py"}
SCHEMA = "trill.linux-root-composition-package.v1"


def elf(data, name):
    desktop.require(len(data) >= 64 and data[:7] == b"\x7fELF\x02\x01\x01"
                    and int.from_bytes(data[18:20], "little") == 62,
                    f"Expected a real x86_64 Linux ELF: {name}")


def build_identity(receipt, desktop_manifest):
    desktop.require(receipt.get("schema") == "trill.linux-root-build-receipt.v1"
                    and receipt.get("status") == "passed"
                    and receipt.get("production_ready") is False
                    and receipt.get("source_clean_after") is True,
                    "Root build is not a completed clean-source build receipt")
    sources = receipt.get("sources", {})
    desktop.require(set(sources) == {"os", "hepta"}, "Both Root build sources are required")
    for name, commit in (("os", desktop_manifest["desktop_commit"]),
                         ("hepta", desktop_manifest["hepta_commit"])):
        identity = sources[name]
        desktop.require(set(identity) == {"commit", "tree"}
                        and identity["commit"] == commit
                        and desktop.SHA.fullmatch(identity["tree"]),
                        "Root and Desktop source combinations differ: " + name)
    commands = receipt.get("commands", [])
    desktop.require({"hepta-build", "desktop-root-build", "root-metadata"}
                    <= {entry.get("name") for entry in commands}
                    and all(entry.get("exit_code") == 0 for entry in commands),
                    "Root build receipt lacks successful original build commands")
    desktop.require(set(receipt.get("binaries", {})) == set(PROGRAMS),
                    "Root build must contain all four original executables")
    desktop.require(receipt.get("desktop_manifest_sha256") == desktop.digest(desktop.json_bytes(desktop_manifest)),
                    "Root build references a different Desktop payload")
    return sources


def ui_identity(receipt, manifest):
    desktop.require(receipt.get("schema") == "trill.linux-text-build-receipt.v1"
                    and receipt.get("status") == "passed" and receipt.get("exit_code") == 0
                    and receipt.get("source_commit") == manifest["desktop_commit"]
                    and receipt.get("hepta", {}).get("commit") == manifest["hepta_commit"],
                    "Desktop payload lacks its own completed native build")
    desktop.require(set(receipt.get("packaged_binaries", {})) == set(desktop.PROGRAMS),
                    "Desktop build lacks its final distribution ELF records")
    for name in desktop.PROGRAMS:
        record = manifest["files"]["bin/" + name]
        desktop.require(receipt["packaged_binaries"][name] == {
            "sha256": record["sha256"], "bytes": record["bytes"]},
            "Desktop distribution ELF differs from its actual build: " + name)
    return {"os": {"commit": receipt["source_commit"], "tree": receipt["source_tree"]},
            "hepta": {key: receipt["hepta"][key] for key in ("commit", "tree")}}


def inventory(package):
    files = set()
    for count, path in enumerate(Path(package).rglob("*"), 1):
        desktop.require(count <= 512 and len(path.relative_to(package).parts) <= 16,
                        "Package object count or depth exceeds its bound")
        info = path.lstat()
        desktop.require(stat.S_ISDIR(info.st_mode) or
                        (stat.S_ISREG(info.st_mode) and info.st_nlink == 1),
                        "Package contains a link or a special object: " + str(path))
        if stat.S_ISREG(info.st_mode):
            files.add(path.relative_to(package).as_posix())
    return files


def supplement_names():
    return EXTRA_FILES | {"bin/" + name for name in PROGRAMS}


def verify(package):
    package = Path(package)
    manifest = desktop.read_json(package / "root-manifest.json")
    desktop.require(set(manifest) == {"schema", "release_id", "sources", "desktop_manifest_sha256",
                                     "effects_authorized", "files"}
                    and manifest["schema"] == SCHEMA and manifest["effects_authorized"] is False,
                    "Unknown Root composition package schema")
    original = desktop.verify_package(package / "desktop")
    desktop.require("resources/NATIVE-SDK-SOURCE.json" in original["files"],
                    "Root native product requires its exact prepared SDK and resource payload")
    desktop.require(manifest["desktop_manifest_sha256"] == desktop.digest(
        desktop.regular_bytes(package / "desktop/manifest.json")), "Desktop payload identity changed")
    files = manifest["files"]
    desktop.require(set(files) == supplement_names(), "Unexpected or missing Root supplement file")
    desktop.require(manifest["release_id"] == original["desktop_commit"][:12] + "-"
                    + desktop.digest(desktop.json_bytes(files))[:12],
                    "Root release identifier does not bind its payload")
    total = 0
    for name, record in files.items():
        data = desktop.regular_bytes(package / name)
        total += len(data)
        mode = 0o755 if name.startswith("bin/") or name.endswith(".py") else 0o644
        desktop.require(set(record) == {"bytes", "sha256", "mode"}
                        and record["bytes"] == len(data) and record["sha256"] == desktop.digest(data)
                        and record["mode"] == mode and total <= desktop.MAX_BUNDLE,
                        "Root supplement checksum, mode or size differs: " + name)
        if name.startswith("bin/"):
            elf(data, name)
    receipt = desktop.read_json(package / "build-receipt.json")
    desktop.require(build_identity(receipt, original) == manifest["sources"], "Root build identity changed")
    ui_receipt = desktop.read_json(package / "desktop-build-receipt.json")
    desktop.require(ui_identity(ui_receipt, original) == manifest["sources"]
                    and receipt["desktop_build_receipt_sha256"] == files["desktop-build-receipt.json"]["sha256"],
                    "Native Desktop build identity differs from the Root supplement")
    desktop.require(set(receipt.get("packaging_sources", {})) == set(PACKAGING_SOURCES.values()),
                    "Root build omits reviewed packaging sources")
    for name, original_path in PACKAGING_SOURCES.items():
        source = receipt["packaging_sources"][original_path]
        desktop.require(source["sha256"] == files[name]["sha256"]
                        and source["bytes"] == files[name]["bytes"],
                        "Packaging source changed after its clean build: " + name)
    for name in PROGRAMS:
        expected = receipt["binaries"][name]
        record = files["bin/" + name]
        desktop.require(expected == {"path": "bin/" + name, "sha256": record["sha256"],
                                     "bytes": record["bytes"]}, "Original build ELF differs: " + name)
    expected = set(files) | {"root-manifest.json", "desktop/manifest.json"}
    expected.update("desktop/" + name for name in original["files"])
    desktop.require(inventory(package) == expected, "Unrecorded or missing package object")
    return manifest


def write_file(path, data, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        os.fchmod(stream.fileno(), mode)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def pack(desktop_package, build_directory, output):
    desktop_package, build_directory, output = map(Path, (desktop_package, build_directory, output))
    original = desktop.verify_package(desktop_package)
    receipt_bytes = desktop.regular_bytes(build_directory / "build-receipt.json")
    receipt = desktop.read_json(build_directory / "build-receipt.json")
    sources = build_identity(receipt, original)
    desktop.require(not output.exists(), "Choose a new Root package output")
    with tempfile.TemporaryDirectory(prefix=".trill-root-package-", dir=output.parent) as temp:
        package = Path(temp) / "trillionnium-desktop-root"
        package.mkdir()
        for name, record in original["files"].items():
            write_file(package / "desktop" / name, desktop.regular_bytes(desktop_package / name), record["mode"])
        write_file(package / "desktop/manifest.json", desktop.regular_bytes(desktop_package / "manifest.json"), 0o644)
        for name in PROGRAMS:
            write_file(package / "bin" / name, desktop.regular_bytes(build_directory / "bin" / name), 0o755)
        write_file(package / "build-receipt.json", receipt_bytes, 0o644)
        write_file(package / "desktop-build-receipt.json",
                   desktop.regular_bytes(build_directory / "desktop-build-receipt.json"), 0o644)
        for source, name in ((Path(__file__), "root_bundle.py"),
                             (HERE / "native_human.py", "libexec/native_human.py"),
                             (HERE.parent / "ROOT_PRODUCT.md", "ROOT_PRODUCT.md")):
            write_file(package / name, desktop.regular_bytes(source), 0o755 if name.endswith(".py") else 0o644)
        files = {}
        for name in sorted(supplement_names()):
            data = desktop.regular_bytes(package / name)
            files[name] = {"bytes": len(data), "sha256": desktop.digest(data),
                           "mode": stat.S_IMODE((package / name).stat().st_mode)}
        manifest = {"schema": SCHEMA, "sources": sources, "effects_authorized": False,
                    "desktop_manifest_sha256": desktop.digest(desktop.regular_bytes(package / "desktop/manifest.json")),
                    "files": files, "release_id": original["desktop_commit"][:12] + "-"
                    + desktop.digest(desktop.json_bytes(files))[:12]}
        write_file(package / "root-manifest.json", desktop.json_bytes(manifest), 0o644)
        verify(package)
        with tarfile.open(output, "x:gz") as archive:
            archive.add(package, arcname=package.name)
        desktop.require(output.stat().st_size <= desktop.MAX_BUNDLE, "Compressed Root archive exceeds bound")
    return {"package": str(output), "sha256": desktop.digest(desktop.regular_bytes(output, desktop.MAX_BUNDLE)),
            "release_id": manifest["release_id"], "production_ready": False}


def root_directory(path):
    path = Path(path)
    desktop.require(path.is_absolute() and path.resolve(strict=True) == path,
                    "Installation parent must be absolute and canonical")
    for parent in (path, *path.parents):
        info = parent.lstat()
        desktop.require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
                        "Installation ancestry must remain in Root custody")
    return path


def root_release(path):
    root_directory(path)
    for child in Path(path).rglob("*"):
        info = child.lstat()
        desktop.require(info.st_uid == 0 and not info.st_mode & 0o022
                        and (stat.S_ISDIR(info.st_mode) or
                             (stat.S_ISREG(info.st_mode) and info.st_nlink == 1)),
                        "Every installed product object must remain in Root custody")


def install(package, prefix):
    desktop.require(os.geteuid() == 0, "Root is required for the explicit product installation")
    manifest = verify(package)
    package, prefix = Path(package), Path(prefix)
    root_directory(prefix.parent)
    if not prefix.exists():
        prefix.mkdir(mode=0o755)
        desktop.fsync_dir(prefix.parent)
    root_directory(prefix)
    releases = prefix / "releases"
    if not releases.exists():
        releases.mkdir(mode=0o755)
    root_directory(releases)
    release = releases / manifest["release_id"]
    descriptor = os.open(prefix / ".install.lock", os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "r+b") as lock:
        info = os.fstat(lock.fileno())
        desktop.require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
                        and stat.S_IMODE(info.st_mode) == 0o600, "Invalid Root installation lock")
        import fcntl
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if release.exists():
            root_release(release)
            desktop.require(verify(release) == manifest, "Root release identifier collision")
        else:
            stage = Path(tempfile.mkdtemp(prefix=".install-", dir=releases))
            try:
                for name in sorted(inventory(package)):
                    data = desktop.regular_bytes(package / name)
                    mode = 0o755 if name.startswith(("bin/", "desktop/bin/")) or name.endswith(".py") else 0o644
                    write_file(stage / name, data, mode)
                desktop.require(verify(stage) == manifest, "Package changed while installing")
                for path in sorted(stage.rglob("*"), reverse=True):
                    if path.is_dir():
                        os.chmod(path, 0o755)
                        desktop.fsync_dir(path)
                os.chmod(stage, 0o755)
                desktop.fsync_dir(stage)
                root_release(stage)
                stage.rename(release)
                desktop.fsync_dir(releases)
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
        current = prefix / "current"
        if current.is_symlink():
            target = os.readlink(current)
            desktop.require(target.startswith("releases/") and len(Path(target).parts) == 2
                            and desktop.RELEASE.fullmatch(Path(target).name), "Unknown current product link")
        else:
            desktop.require(not current.exists(), "Existing current product object is not a release link")
        desktop.switch_release(prefix, manifest["release_id"])
    return {"installed": str(release), "release_id": manifest["release_id"],
            "services_started": False, "production_ready": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("pack")
    create.add_argument("--desktop-package", type=Path, required=True)
    create.add_argument("--root-build", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("verify")
    check.add_argument("package", type=Path)
    setup = commands.add_parser("install")
    setup.add_argument("package", type=Path)
    setup.add_argument("--prefix", type=Path, default=Path("/opt/trill-product"))
    args = parser.parse_args()
    try:
        if args.command == "pack":
            result = pack(args.desktop_package, args.root_build, args.output)
        elif args.command == "verify":
            result = verify(args.package)
        else:
            result = install(args.package, args.prefix)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    except (OSError, ValueError, desktop.ProductError) as error:
        parser.exit(1, f"Root package refused: {error}\n")


if __name__ == "__main__":
    main()
