#!/usr/bin/env python3
"""Build original Root/Agentd/Core tools for one already built native Desktop.

All source checkouts and Cargo locks are checked before and after compilation.
Existing target caches may be reused; no dependency path override is accepted.
This builder starts no Root, human session, inference turn or application.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE / "product"))
sys.path.insert(0, str(REPO / "support/release"))
import desktop
import root_bundle
import organ_release_profile as source_profile
import build_text_product
import verify_product_dependencies


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def original_cache(metadata, identity):
    repository = "https://github.com/TrillionniumFoundation/hepta-private-ci"
    expected = f"git+{repository}?rev={identity['commit']}#{identity['commit']}"
    roots = set()
    packages = []
    for package in metadata["packages"]:
        if repository not in (package.get("source") or ""):
            continue
        desktop.require(package["source"] == expected, "Root graph selects a different original Hepta source")
        manifest = Path(package["manifest_path"]).resolve(strict=True)
        root = Path(build_text_product.cache_git(manifest.parent, "rev-parse", "--show-toplevel").decode().strip())
        roots.add(root)
        build_text_product.cache_git(root, "ls-files", "--error-unmatch", "--", manifest.relative_to(root).as_posix())
        packages.append(package["name"])
    desktop.require(len(roots) == 1 and {"codex-hepta-agentd", "codex-hepta-supervisor", "codex-hepta-fleet"}
                    <= set(packages), "Root graph omits original owners or substitutes their source")
    root = next(iter(roots))
    for ref, value in (("HEAD", identity["commit"]), ("HEAD^{tree}", identity["tree"])):
        desktop.require(build_text_product.cache_git(root, "rev-parse", ref).decode().strip() == value,
                        "Resolved original Root source identity differs")
    flags = build_text_product.cache_git(root, "ls-files", "-v", "-z").split(b"\0")
    desktop.require(not any(item and (item[:1].islower() or item[:1] == b"S") for item in flags)
                    and not build_text_product.cache_git(root, "status", "--porcelain=v1", "--untracked-files=no"),
                    "Resolved original Root source is dirty or hidden")
    return {"root": str(root), "identity": identity, "packages": sorted(packages)}


def build(args):
    original = desktop.verify_package(args.desktop_package)
    ui_receipt_path = args.desktop_build / "build-receipt.json"
    ui_receipt = desktop.read_json(ui_receipt_path)
    identities = root_bundle.ui_identity(ui_receipt, original)
    os_repo = source_profile.Repository(REPO, "os")
    hepta_repo = source_profile.Repository(args.hepta_repo, "hepta")
    for repo, name in ((os_repo, "os"), (hepta_repo, "hepta")):
        repo.check(identities[name]["commit"], identities[name]["tree"])
    verify_product_dependencies.verify(REPO, hepta_repo.path)
    output = args.output.absolute()
    targets = {"hepta": args.hepta_target.absolute(), "desktop": args.root_target.absolute()}
    for path in (output, *targets.values()):
        desktop.require(path.resolve() == path and not any(path.is_relative_to(repo.path) for repo in (os_repo, hepta_repo)),
                        "Build outputs and caches must be canonical and outside the source checkouts")
    desktop.require(targets["hepta"] != targets["desktop"], "The two Cargo roots need distinct target directories")
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    logs = output / "logs"; logs.mkdir()
    binaries = output / "bin"; binaries.mkdir()
    tools = {name: str(Path(subprocess.check_output(
        ["rustup", "which", "--toolchain", "1.96.0", name], text=True).strip()).resolve(strict=True))
        for name in ("cargo", "rustc", "rustdoc")}
    tool_records = {name: {"path": path, "sha256": digest(path)} for name, path in tools.items()}
    profile = {"toolchain": "1.96.0"}
    env, removed = build_text_product.controlled_environment(profile, targets["hepta"], 1, tools)
    env["CARGO_INCREMENTAL"] = "0"
    locks = {"hepta": (hepta_repo.path / "codex-rs/Cargo.lock"),
             "desktop": (REPO / "services/hepta-session-host/Cargo.lock")}
    lock_hashes = {name: digest(path) for name, path in locks.items()}
    packaging = {path: os_repo.file(path)[1] for path in root_bundle.PACKAGING_SOURCES.values()}
    receipt = {"schema": "trill.linux-root-build-receipt.v1", "status": "running", "sources": identities,
               "source_clean_after": False, "production_ready": False, "commands": [], "binaries": {},
               "desktop_manifest_sha256": desktop.digest(desktop.json_bytes(original)),
               "desktop_build_receipt_sha256": digest(ui_receipt_path), "packaging_sources": packaging,
               "targets": {key: str(value) for key, value in targets.items()}, "locks": lock_hashes,
               "compiler_tools": tool_records, "ambient_overrides_removed": removed,
               "cargo_profile": "dev-small", "distribution_transform": "GNU strip --strip-unneeded"}

    def save():
        desktop.atomic_write(output / "build-receipt.json", desktop.json_bytes(receipt))

    def run(name, command, cwd, target):
        current_env = dict(env, CARGO_TARGET_DIR=str(target))
        command = [tools[command[0]], *command[1:]] if command[0] in tools else command
        entry = {"name": name, "command": command, "cwd": str(cwd)}
        receipt["commands"].append(entry); save()
        start = time.monotonic()
        stdout, stderr = logs / (name + ".stdout.log"), logs / (name + ".stderr.log")
        print("Running " + name, flush=True)
        with stdout.open("xb") as out, stderr.open("xb") as err:
            result = subprocess.run(command, cwd=cwd, env=current_env, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
        entry.update(exit_code=result.returncode, seconds=round(time.monotonic() - start, 3),
                     stdout_sha256=digest(stdout), stderr_sha256=digest(stderr))
        save()
        desktop.require(result.returncode == 0, f"{name} failed; retain {stderr}")
        return stdout

    try:
        save()
        common = ["--locked"] + (["--offline"] if args.offline else [])
        compiler = run("compiler", ["rustc", "--version", "--verbose"], hepta_repo.path, targets["hepta"])
        desktop.require(compiler.read_text().startswith("rustc 1.96.0 ")
                        and "host: x86_64-unknown-linux-gnu" in compiler.read_text(), "Unsupported compiler or host")
        metadata = run("root-metadata", ["cargo", "metadata", "--manifest-path", "services/hepta-session-host/Cargo.toml",
                       "--format-version", "1", "--features", "product-root", *common], REPO, targets["desktop"])
        graph = json.loads(metadata.read_bytes())
        receipt["original_source_cache"] = original_cache(graph, identities["hepta"])
        run("hepta-build", ["cargo", "build", *common, "--profile", "dev-small", "--jobs", "1",
                            "-p", "codex-hepta-agentd", "-p", "codex-app-server", "--bin", "codex-hepta-agentd",
                            "--bin", "hepta-authority-host", "--bin", "codex-app-server"],
            hepta_repo.path / "codex-rs", targets["hepta"])
        run("desktop-root-build", ["cargo", "build", "--manifest-path", "services/hepta-session-host/Cargo.toml",
                                   *common, "--features", "product-root", "--profile", "dev-small",
                                   "--bin", "hepta-desktop-root", "--jobs", "1"], REPO, targets["desktop"])
        strip = Path(shutil.which("strip")).resolve(strict=True)
        receipt["strip"] = {"path": str(strip), "sha256": digest(strip)}
        for name in root_bundle.PROGRAMS:
            target = targets["desktop" if name == "hepta-desktop-root" else "hepta"]
            source = target / "dev-small" / name
            destination = binaries / name
            shutil.copyfile(source, destination)
            run("strip-" + name, [str(strip), "--strip-unneeded", str(destination)], REPO, target)
            data = desktop.regular_bytes(destination)
            root_bundle.elf(data, name)
            os.chmod(destination, 0o755)
            receipt["binaries"][name] = {"path": "bin/" + name, "sha256": desktop.digest(data), "bytes": len(data)}
        for repo, name in ((os_repo, "os"), (hepta_repo, "hepta")):
            repo.check(identities[name]["commit"], identities[name]["tree"])
        desktop.require({name: digest(path) for name, path in locks.items()} == lock_hashes,
                        "Cargo changed a committed product lock")
        desktop.require(original_cache(graph, identities["hepta"]) == receipt["original_source_cache"],
                        "Original Cargo source cache changed during the build")
        desktop.require(all(digest(record["path"]) == record["sha256"] for record in tool_records.values())
                        and digest(strip) == receipt["strip"]["sha256"], "A build tool changed during compilation")
        desktop.require(digest(ui_receipt_path) == receipt["desktop_build_receipt_sha256"]
                        and desktop.verify_package(args.desktop_package) == original,
                        "Native Desktop build or payload changed during Root compilation")
        (output / "desktop-build-receipt.json").write_bytes(desktop.regular_bytes(ui_receipt_path))
        receipt.update(status="passed", source_clean_after=True); save()
        print(str(output / "build-receipt.json")); return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, desktop.ProductError,
            source_profile.ProfileError) as error:
        receipt.update(status="failed", error=str(error)); save(); raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("desktop-package", "desktop-build", "hepta-repo", "hepta-target", "root-target", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    try:
        return build(parser.parse_args())
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, desktop.ProductError,
            source_profile.ProfileError) as error:
        parser.exit(1, f"Root product build refused: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
