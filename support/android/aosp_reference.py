#!/usr/bin/env python3
"""Reproducible AOSP reference checks for the A08 host/guest model.

This tool never reports native Rust-kernel Android support.  It either records
host facts, verifies an already checked-out AOSP tree, or runs the exact AOSP
commands from the locked profile when the caller explicitly asks it to.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = ROOT / "compat" / "android" / "aosp-profile.json"


def load_profile() -> dict[str, Any]:
    with PROFILE_PATH.open(encoding="utf-8") as stream:
        return json.load(stream)


def command_version(command: str) -> str | None:
    path = shutil.which(command)
    if path is None:
        return None
    try:
        completed = subprocess.run(
            [command, "--version"], capture_output=True, text=True, check=False
        )
    except OSError:
        return path
    line = (completed.stdout or completed.stderr).splitlines()
    return f"{path}: {line[0] if line else 'present'}"


def host_probe(profile: dict[str, Any]) -> dict[str, Any]:
    required = profile["toolchain"]["required_host_tools"]
    page_size = os.sysconf("SC_PAGE_SIZE")
    physical_memory = os.sysconf("SC_PHYS_PAGES") * page_size
    disk = shutil.disk_usage(ROOT)
    requirements = profile["toolchain"]["official_host_requirements"]
    return {
        "execution_class": "host-model",
        "native_android_claim": False,
        "kernel_compatibility_status": "not_tested",
        "uname": platform.uname()._asdict(),
        "page_size_bytes": page_size,
        "page_size_matches_profile": page_size == profile["target"]["page_size_bytes"],
        "physical_memory_bytes": physical_memory,
        "free_disk_bytes": disk.free,
        "official_requirement_check": {
            "ram_gib_min": requirements["ram_gib_min"],
            "free_disk_gib_min": requirements["free_disk_gib_min"],
            "ram_meets_requirement": physical_memory >= requirements["ram_gib_min"] * 1024**3,
            "disk_meets_requirement": disk.free >= requirements["free_disk_gib_min"] * 1024**3,
        },
        "commands": {name: command_version(name) for name in required},
        "profile_id": profile["profile_id"],
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_head(path: Path) -> str | None:
    if not (path / ".git").exists() and not (path / "HEAD").exists():
        return None
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def verify_checkout(source: Path, profile: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Verify facts that can be checked without network access.

    AOSP's repo manifest stores projects in paths such as build/make while
    their git repositories live below .repo/projects.  We check the ordinary
    checkout paths first and report missing projects rather than guessing.
    """

    checks: dict[str, Any] = {
        "execution_class": "android-guest-reference",
        "native_android_claim": False,
        "kernel_compatibility_status": "not_tested",
        "source": str(source),
        "profile_id": profile["profile_id"],
        "checks": [],
    }
    failures = 0

    def check(name: str, ok: bool, detail: Any) -> None:
        nonlocal failures
        checks["checks"].append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            failures += 1

    if not source.is_dir():
        check("source_directory", False, "directory does not exist")
        return checks, failures

    target = profile["target"]
    product = source / target["product_makefile"]
    board = source / target["board_config"]
    check("product_makefile", product.is_file(), str(product))
    check("board_config", board.is_file(), str(board))
    if product.is_file():
        contents = product.read_text(encoding="utf-8", errors="replace")
        expected_product = f"PRODUCT_NAME := {target['product']}"
        check("product_name", expected_product in contents, expected_product)
    if board.is_file():
        contents = board.read_text(encoding="utf-8", errors="replace")
        check("target_arch", "TARGET_ARCH := x86_64" in contents, "TARGET_ARCH")
        check("target_cpu_abi", "TARGET_CPU_ABI := x86_64" in contents, "TARGET_CPU_ABI")
    shared_board = source / "device" / "google" / "cuttlefish" / "shared" / "BoardConfig.mk"
    check("shared_board_config", shared_board.is_file(), str(shared_board))
    if shared_board.is_file():
        shared_contents = shared_board.read_text(encoding="utf-8", errors="replace")
        groups = profile["partitions"]["dynamic_groups"]
        check(
            "dynamic_partitions",
            "BOARD_SUPER_PARTITION_GROUPS :=" in shared_contents
            and all(group in shared_contents for group in groups)
            and f"BOARD_SUPER_PARTITION_SIZE := {profile['partitions']['super_partition_size_bytes']}" in shared_contents,
            {"groups": groups, "super_partition_size_bytes": profile["partitions"]["super_partition_size_bytes"]},
        )

    expected_projects = profile["aosp"]["source_projects"]
    project_heads: dict[str, str | None] = {}
    for path, expected in expected_projects.items():
        project = source / path
        head = git_head(project)
        project_heads[path] = head
        check(f"project:{path}", head == expected, {"expected": expected, "actual": head})
    checks["project_heads"] = project_heads

    manifest = source / ".repo" / "manifests" / "default.xml"
    manifest_repo = source / ".repo" / "manifests"
    manifest_head = git_head(manifest_repo)
    check(
        "manifest_commit",
        manifest_head == profile["aosp"]["manifest_commit"],
        {"expected": profile["aosp"]["manifest_commit"], "actual": manifest_head},
    )
    if manifest.is_file():
        check(
            "default_xml_sha256",
            sha256(manifest) == profile["aosp"]["default_xml_sha256"],
            {"expected": profile["aosp"]["default_xml_sha256"], "actual": sha256(manifest)},
        )
    else:
        check("default_xml_sha256", False, "repo manifest checkout not found")

    return checks, failures


def build_command(profile: dict[str, Any]) -> list[str]:
    return profile["toolchain"]["build_commands"]


def run_build(source: Path, profile: dict[str, Any]) -> int:
    if not source.is_dir():
        print(json.dumps({"status": "blocked", "reason": "source directory does not exist"}))
        return 2
    lock_report, lock_failures = verify_checkout(source, profile)
    if lock_failures:
        print(json.dumps({"status": "blocked", "reason": "AOSP checkout does not match locked profile", "checkout": lock_report}, sort_keys=True))
        return 3
    missing = [name for name in profile["toolchain"]["required_host_tools"] if shutil.which(name) is None]
    if missing:
        print(json.dumps({"status": "blocked", "reason": "missing host tools", "missing": missing}))
        return 2
    env = os.environ.copy()
    env["ANDROID_BUILD_TOP"] = str(source)
    lunch = profile["target"]["lunch"]
    commands = [
        ["bash", "-lc", f"source build/envsetup.sh && lunch {lunch}"],
        ["bash", "-lc", f"source build/envsetup.sh && lunch {lunch} && m -j$(nproc)"],
    ]
    for command in commands:
        completed = subprocess.run(command, cwd=source, env=env, check=False)
        if completed.returncode:
            return completed.returncode
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("probe", help="record this host; this is never native Android evidence")
    verify = sub.add_parser("verify-checkout", help="verify a complete local repo checkout")
    verify.add_argument("--source", type=Path, required=True)
    command = sub.add_parser("build-command", help="print the locked commands")
    command.add_argument("--shell", action="store_true", help="print a shell script")
    build = sub.add_parser("build", help="run the real AOSP build in an existing checkout")
    build.add_argument("--source", type=Path, required=True)
    args = parser.parse_args(argv)
    profile = load_profile()

    if args.action == "probe":
        print(json.dumps(host_probe(profile), indent=2, sort_keys=True))
        return 0
    if args.action == "verify-checkout":
        result, failures = verify_checkout(args.source, profile)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1 if failures else 0
    if args.action == "build-command":
        if args.shell:
            print("set -eu")
            for command_line in build_command(profile):
                print(command_line)
        else:
            print(json.dumps(build_command(profile), indent=2))
        return 0
    if args.action == "build":
        return run_build(args.source, profile)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
