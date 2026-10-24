#!/usr/bin/env python3
"""Build and package one explicit original Makepad/text source combination."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "support/release"))
sys.path.insert(0, str(HERE / "product"))
import organ_release_profile as source_profile
import desktop


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_graph(metadata, hepta_commit, profile):
    """The metadata must describe the exact native feature's actual resolution."""
    nodes = {item["id"]: item for item in (metadata.get("resolve") or {}).get("nodes", [])}
    packages = metadata["packages"]
    selected = {}
    for name in ("trill-shell", "hepta-session-host", "hepta-robrix-ui",
                 "hepta-control-core", "codex-hepta-agentd", "codex-hepta-memory",
                 "makepad-widgets"):
        candidates = [item for item in packages if item["name"] == name and item["id"] in nodes]
        require(len(candidates) == 1, "Native text graph requires one resolved package: " + name)
        selected[name] = candidates[0]
    for name, feature in (("trill-shell", "hepta-native-makepad"),
                          ("hepta-session-host", "native-text"),
                          ("hepta-robrix-ui", "native-presentation")):
        require(feature in nodes[selected[name]["id"]]["features"], "Missing native feature: " + name + "/" + feature)
    require("hepta-native-clipboard-sdk" not in nodes[selected["trill-shell"]["id"]]["features"]
            and "native-clipboard-sdk" not in nodes[selected["hepta-robrix-ui"]["id"]]["features"],
            "This baseline profile does not select the independent patched SDK candidate")
    expected = "git+https://github.com/TrillionniumFoundation/hepta-private-ci?rev=" + hepta_commit + "#" + hepta_commit
    for package in packages:
        source = package.get("source") or ""
        if "TrillionniumFoundation/hepta-private-ci" in source:
            require(source == expected, "Mixed original Hepta revisions in the resolved graph")
    for name in ("hepta-robrix-ui", "hepta-control-core", "codex-hepta-agentd", "codex-hepta-memory"):
        require(selected[name].get("source") == expected, "Original Hepta package was substituted: " + name)
    sdk = selected["makepad-widgets"].get("source") or ""
    require(sdk == "git+" + profile["makepad_repository"] + "?rev=" + profile["makepad_commit"]
            + "#" + profile["makepad_commit"], "Original Makepad SDK differs from this profile")
    return {name: {"id": value["id"], "source": value.get("source"),
                   "features": nodes[value["id"]]["features"]} for name, value in selected.items()}


def build(args):
    require(sys.version_info >= (3, 11), "Python 3.11 or later is required")
    require(platform.system() == "Linux" and platform.machine() == "x86_64", "This profile requires an x86_64 Linux host")
    profile_path = HERE / "linux-text-profile.json"
    profile = source_profile.load_json(profile_path)
    require(profile["schema"] == "trill.linux-text-build-profile.v1", "Unknown text build profile")
    os_repo = source_profile.Repository(REPO, "os")
    hepta_repo = source_profile.Repository(args.hepta_repo, "hepta")
    identity = os_repo.check(args.desktop_commit, args.desktop_tree)
    hepta_identity = hepta_repo.check(args.hepta_commit, args.hepta_tree)
    mapping = source_profile.load_json(REPO / "support/release/organ_source_map.json")
    manifest, source_receipt = source_profile.create_manifest(
        os_repo, hepta_repo, args.desktop_commit, args.desktop_tree,
        args.hepta_commit, args.hepta_tree, mapping)
    output = Path(args.output).absolute()
    require(output == output.resolve(), "Build output must have a canonical absolute path")
    require(not any(output.is_relative_to(repo.path) for repo in (os_repo, hepta_repo)), "Build output must be outside both source checkouts")
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    logs = output / "logs"
    logs.mkdir(mode=0o700)
    target = output / "target"
    env = dict(os.environ, RUSTUP_TOOLCHAIN=profile["toolchain"],
               CARGO_TARGET_DIR=str(target), CARGO_BUILD_JOBS=str(args.jobs),
               CARGO_PROFILE_DEV_DEBUG="0", CARGO_PROFILE_DEV_INCREMENTAL="false",
               GIT_TERMINAL_PROMPT="0")
    receipt = {"schema": "trill.linux-text-build-receipt.v1", "status": "running",
               "source_commit": identity["commit"], "source_tree": identity["tree"],
               "hepta": hepta_identity, "profile": profile,
               "profile_sha256": digest(profile_path), "cargo_profile": args.build_profile,
               "commands": [], "locks": {}, "binaries": {},
               "production_authority_qualified": False, "window_qualified": False,
               "environment": {key: env[key] for key in ("RUSTUP_TOOLCHAIN", "CARGO_TARGET_DIR",
                   "CARGO_BUILD_JOBS", "CARGO_PROFILE_DEV_DEBUG", "CARGO_PROFILE_DEV_INCREMENTAL")}}

    def save():
        desktop.atomic_write(output / "build-receipt.json", source_profile.canonical(receipt))

    def run(name, command, machine_output=False):
        start = time.monotonic()
        stdout, stderr = logs / (name + (".json" if machine_output else ".log")), logs / (name + ".stderr.log")
        entry = {"name": name, "command": command, "stdout": stdout.name, "stderr": stderr.name}
        receipt["commands"].append(entry)
        save()
        print("Running " + name, flush=True)
        with stdout.open("xb") as out, stderr.open("xb") as err:
            result = subprocess.run(command, cwd=REPO, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
        entry.update(exit_code=result.returncode, seconds=round(time.monotonic() - start, 3),
                     stdout_sha256=digest(stdout), stderr_sha256=digest(stderr))
        save()
        require(result.returncode == 0, f"{name} failed with exit {result.returncode}; retain {stderr} and {stdout}")
        return stdout

    try:
        save()
        manifest_bytes = source_profile.canonical(manifest)
        (output / "source-profile.json").write_bytes(manifest_bytes)
        source_receipt["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
        (output / "source-verification.json").write_bytes(source_profile.canonical(source_receipt))
        for relative in ("ui/Cargo.lock", "services/hepta-session-host/Cargo.lock",
                         "services/hepta-os/Cargo.lock", "support/ui/Cargo.lock", "tests/ui/Cargo.lock"):
            receipt["locks"][relative] = digest(REPO / relative)
        compiler = run("compiler", ["rustc", "--version", "--verbose"])
        require(compiler.read_text().splitlines()[0].startswith("rustc " + profile["toolchain"] + " "), "Unexpected Rust compiler")
        require("host: " + profile["target"] in compiler.read_text(), "Unexpected Rust host target")
        run("cargo", ["cargo", "--version"])
        common = ["--locked"] + (["--offline"] if args.offline else [])
        feature = ["--features", profile["cargo_feature"]]
        metadata = run("native-metadata", ["cargo", "metadata", "--manifest-path", "ui/Cargo.toml",
            "--format-version", "1", *common, *feature], machine_output=True)
        receipt["resolved_packages"] = validate_graph(json.loads(metadata.read_bytes()), args.hepta_commit, profile)
        run("rustfmt", ["cargo", "fmt", "--manifest-path", "ui/Cargo.toml", "--all", "--", "--check"])
        for name, path, features in (
            ("native-ui-tests", "ui/Cargo.toml", ["--workspace", *feature]),
            ("native-text-tests", "services/hepta-session-host/Cargo.toml", ["--features", "native-text", "--lib"]),
            ("observer-tests", "services/hepta-os/Cargo.toml", []),
            ("support-tests", "support/ui/Cargo.toml", []),
            ("host-contract-tests", "tests/ui/Cargo.toml", []),
        ):
            run(name, ["cargo", "test", "--manifest-path", path, *common, *features])
        command = ["cargo", "build", "--manifest-path", "ui/Cargo.toml", "--workspace", "--bins", *common, *feature]
        if args.build_profile == "release":
            command.append("--release")
        run("native-build", command)
        resources = output / "resources"
        command = [sys.executable, "-B", str(HERE / "prepare_native_makepad.py"),
                   "--metadata", str(metadata), "--output", str(resources)]
        if args.offline:
            command.append("--offline")
        if args.liberation_source:
            command.extend(["--liberation-source", str(Path(args.liberation_source).resolve(strict=True))])
        if args.asset_cache:
            command.extend(["--asset-cache", str(Path(args.asset_cache).resolve(strict=True))])
        run("native-resources", command)
        resource_files = desktop.native_resource_files(resources, args.hepta_commit)
        require(len(resource_files) == profile["resource_files"], "Resource inventory differs from this exact profile")
        receipt["resources"] = {name: digest(resources / name) for name in resource_files}
        os_repo.check(args.desktop_commit, args.desktop_tree)
        hepta_repo.check(args.hepta_commit, args.hepta_tree)
        for path, checksum in receipt["locks"].items():
            require(digest(REPO / path) == checksum, "Cargo lock changed while building: " + path)
        for name in desktop.PROGRAMS:
            binary = target / args.build_profile / name
            require(binary.is_file() and not binary.is_symlink(), "Missing native binary: " + name)
            receipt["binaries"][name] = {"sha256": digest(binary), "bytes": binary.stat().st_size}
        env["TRILL_UI_BUILD_PROFILE"] = args.build_profile
        run("host-archive", ["bash", str(HERE / "package-host-binaries.sh"), str(output / "host-archive")])
        package = output / "trillionnium-desktop-linux-text.tar.gz"
        receipt["package"] = desktop.pack(output / "host-archive/a10-linux-host-binaries.tar.gz",
            args.desktop_commit, output / "source-profile.json", package, resources)
        receipt["package"]["sha256"] = digest(package)
        receipt["packaged_binaries"] = receipt["package"]["binaries"]
        receipt["distribution_transform"] = "GNU strip --strip-unneeded"
        config = desktop.default_config()
        config["renderer"] = profile["renderer"]
        desktop.atomic_write(output / "linux-text-config.json", desktop.json_bytes(config))
        receipt.update(status="passed", exit_code=0)
        save()
        print(str(output / "build-receipt.json"))
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, source_profile.ProfileError, desktop.ProductError) as error:
        receipt.update(status="failed", exit_code=1, error=str(error))
        save()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("desktop-commit", "desktop-tree", "hepta-repo", "hepta-commit", "hepta-tree", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--jobs", type=int, choices=range(1, 9), default=2)
    parser.add_argument("--build-profile", choices=("debug", "release"), default="release")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--liberation-source")
    parser.add_argument("--asset-cache")
    try:
        return build(parser.parse_args())
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, source_profile.ProfileError, desktop.ProductError) as error:
        print("Linux text product: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
