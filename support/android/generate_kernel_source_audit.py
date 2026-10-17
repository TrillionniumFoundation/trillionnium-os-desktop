#!/usr/bin/env python3
"""Generate a source-only Android compatibility snapshot for the current tree.

The snapshot binds every finding to the checked-out project commit and the
imported Asterinas file hashes. It is deliberately conservative: source
presence is recorded as evidence for follow-up work, never as runtime support.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


PIN = "c4b7ed575b7b32773475b194d2ad41fb6d03765b"
TAG = "v0.19.0"
REQUIRED = (
    "kernel/asterinas/kernel/core/src/syscall/mod.rs",
    "kernel/asterinas/kernel/core/src/syscall/prctl.rs",
    "kernel/asterinas/kernel/core/src/syscall/futex.rs",
    "kernel/asterinas/kernel/core/src/syscall/mmap.rs",
    "kernel/asterinas/kernel/core/src/syscall/mprotect.rs",
    "kernel/asterinas/kernel/core/src/syscall/munmap.rs",
    "kernel/asterinas/kernel/core/src/syscall/mremap.rs",
    "kernel/asterinas/kernel/core/src/syscall/memfd_create.rs",
    "kernel/asterinas/kernel/core/src/syscall/sendmsg.rs",
    "kernel/asterinas/kernel/core/src/syscall/recvmsg.rs",
    "kernel/asterinas/kernel/core/src/syscall/clone.rs",
    "kernel/asterinas/kernel/core/src/syscall/execve.rs",
    "kernel/asterinas/kernel/core/src/syscall/rt_sigaction.rs",
    "kernel/asterinas/kernel/core/src/security/lsm/modules/mod.rs",
    "kernel/asterinas/kernel/core/src/device/mod.rs",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def source_snapshot(root: Path) -> tuple[dict[str, Any], list[str]]:
    files: dict[str, Any] = {}
    missing: list[str] = []
    for rel in REQUIRED:
        path = root / rel
        if not path.is_file():
            missing.append(rel)
            continue
        files[rel] = {
            "git_blob": git(root, "hash-object", rel),
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }
    return files, missing


def scan_source(root: Path) -> dict[str, Any]:
    core = root / "kernel/asterinas/kernel/core/src"
    rust_files = sorted(core.rglob("*.rs")) if core.is_dir() else []

    def matching(pattern: str, roots: tuple[Path, ...]) -> list[str]:
        expression = re.compile(pattern)
        found: list[str] = []
        for base in roots:
            if not base.is_dir():
                continue
            for path in sorted(base.rglob("*.rs")):
                text = path.read_text(encoding="utf-8", errors="replace")
                if expression.search(text):
                    found.append(str(path.relative_to(root)))
        return sorted(set(found))

    binder = matching(
        r"\b(?:BINDER_WRITE_READ|BINDER_VERSION|binder_ioctl|BinderDevice|BinderDriver)\b",
        (core / "device", core / "fs", core / "syscall"),
    )
    seccomp = matching(r"\b(?:PR_SET_SECCOMP|PR_GET_SECCOMP|sys_seccomp)\b", (core,))
    lsm = (core / "security/lsm/modules/mod.rs").read_text(
        encoding="utf-8", errors="replace"
    ) if (core / "security/lsm/modules/mod.rs").is_file() else ""
    selinux_path = core / "security/lsm/modules/selinux.rs"
    # A mention in a comment or compatibility book is not a MAC module. Only
    # a registered module or an actual selinux implementation file counts as
    # a source candidate.
    selinux = []
    if selinux_path.is_file():
        selinux.append(str(selinux_path.relative_to(root)))
    if re.search(r"(?m)^\s*mod\s+selinux\s*;", lsm):
        selinux.append(str((core / "security/lsm/modules/mod.rs").relative_to(root)))
    return {
        "core_rust_file_count": len(rust_files),
        "binder_matches": binder,
        "seccomp_matches": seccomp,
        "selinux_matches": sorted(set(selinux)),
        "registered_lsm_modules": re.findall(r"(?m)^\s*mod\s+(\w+)\s*;", lsm),
    }


def build_report(root: Path, project_ref: str = "HEAD") -> dict[str, Any]:
    files, missing = source_snapshot(root)
    scan = scan_source(root)
    blockers: list[str] = []
    if not scan["binder_matches"]:
        blockers.append("binder")
    if not scan["seccomp_matches"]:
        blockers.append("seccomp")
    if not scan["selinux_matches"]:
        blockers.append("mac")
    if missing:
        blockers.append("source_paths")
    return {
        "schema": 2,
        "observed_date": "2026-10-16",
        "project_commit": git(root, "rev-parse", project_ref),
        "project_tree": git(root, "rev-parse", f"{project_ref}^{{tree}}"),
        "kernel_upstream_lock": {"tag": TAG, "commit": PIN},
        "source_files": files,
        "missing_source_paths": missing,
        "source_scan": scan,
        "checks": {
            "binder": {
                "status": "driver_not_evidenced" if not scan["binder_matches"] else "candidate_source_requires_ioctl_review",
                "transactions_verified": False,
                "owner": "A05/A08",
            },
            "seccomp": {
                "status": "missing_install_entrypoint" if not scan["seccomp_matches"] else "candidate_source_requires_runtime_review",
                "negative_filter_test_passed": False,
                "owner": "A05",
            },
            "android_mac": {
                "status": "selinux_equivalent_not_evidenced" if not scan["selinux_matches"] else "candidate_policy_requires_runtime_review",
                "negative_mac_tests_passed": False,
                "owner": "A05",
            },
        },
        "blocking_requirements": blockers,
        "runtime_android_verified": False,
        "booted_android_on_asterinas": False,
        "build_tested_this_agent": False,
        "status": "source_review_blocked" if blockers else "source_candidates_unverified",
        "limitations": [
            "This is a source snapshot, not a kernel build or guest run.",
            "A syscall entrypoint or source match does not establish Android semantics.",
            "The Cuttlefish Linux reference and any host probes remain separate from Asterinas qualification.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--project-ref",
        default="HEAD",
        help="Git ref whose commit/tree identify the source snapshot (default: HEAD)",
    )
    args = parser.parse_args()
    report = build_report(args.repo_root.resolve(), args.project_ref)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "blockers": report["blocking_requirements"], "commit": report["project_commit"]}, sort_keys=True))
    return 2 if report["blocking_requirements"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
