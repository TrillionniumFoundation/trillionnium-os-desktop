#!/usr/bin/env python3
"""Generate a source-only Android compatibility snapshot for a Git commit.

The selected ref is resolved once. Every inspected byte is then read from its
immutable Git objects, never from the working tree. Source presence is evidence
for follow-up work, never runtime support.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import re
import subprocess
from pathlib import Path
from typing import Any


PIN = "c4b7ed575b7b32773475b194d2ad41fb6d03765b"
TAG = "v0.19.0"
CORE = "kernel/asterinas/kernel/core/src"
LOCK_PATH = "support/upstream-lock.json"
EXPECTED_LOCK = {"tag": TAG, "commit": PIN, "reuse": "full_kernel_derived"}
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


@dataclass(frozen=True)
class GitSource:
    blob: str
    mode: str
    data: bytes


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "--no-replace-objects", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def committed_sources(root: Path, commit: str) -> dict[str, GitSource]:
    """Read regular Rust sources and the upstream lock from one commit."""
    listing = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(root),
         "ls-tree", "-r", "-z", commit, "--", CORE, LOCK_PATH]
    )
    entries = []
    for entry in listing.split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, kind, blob = metadata.decode("ascii").split()
        relative = raw_path.decode("utf-8")
        if relative != LOCK_PATH and not (relative.startswith(CORE + "/") and relative.endswith(".rs")):
            continue
        if kind != "blob" or mode not in ("100644", "100755"):
            raise ValueError(f"committed source input is not a regular file: {relative}")
        entries.append((relative, mode, blob))
    if not entries:
        return {}
    # A single batch avoids one Git process per Rust source file. No archive
    # attributes, checkout filters, symlinks or dirty files affect the bytes.
    result = subprocess.run(
        ["git", "--no-replace-objects", "-C", str(root), "cat-file", "--batch"],
        input="".join(blob + "\n" for _, _, blob in entries).encode("ascii"),
        capture_output=True, check=True,
    )
    stream = io.BytesIO(result.stdout)
    sources = {}
    for relative, mode, expected_blob in entries:
        blob, kind, raw_size = stream.readline().decode("ascii").split()
        size = int(raw_size)
        data = stream.read(size)
        if (blob != expected_blob or kind != "blob" or len(data) != size
                or stream.read(1) != b"\n"):
            raise ValueError(f"incomplete or mismatched Git blob: {relative}")
        sources[relative] = GitSource(blob=blob, mode=mode, data=data)
    if stream.read():
        raise ValueError("unexpected trailing Git blob output")
    return sources


def source_metadata(source: GitSource) -> dict[str, Any]:
    return {
        "git_blob": source.blob,
        "git_mode": source.mode,
        "sha256": hashlib.sha256(source.data).hexdigest(),
        "bytes": len(source.data),
    }


def source_snapshot(sources: dict[str, GitSource]) -> tuple[dict[str, Any], list[str]]:
    files: dict[str, Any] = {}
    missing: list[str] = []
    for rel in REQUIRED:
        source = sources.get(rel)
        if source is None:
            missing.append(rel)
            continue
        files[rel] = source_metadata(source)
    if LOCK_PATH in sources:
        files[LOCK_PATH] = source_metadata(sources[LOCK_PATH])
    return files, missing


def verify_upstream_lock(source: GitSource | None) -> dict[str, Any]:
    result = {
        "source_path": LOCK_PATH,
        "expected": dict(EXPECTED_LOCK),
        "actual": None,
        "status": "missing",
    }
    if source is None:
        return result
    try:
        document = json.loads(source.data.decode("utf-8"))
        if not isinstance(document, dict) or not isinstance(document.get("kernel"), dict):
            raise ValueError("upstream lock must contain an object at kernel")
        actual = document["kernel"]
    except (UnicodeDecodeError, ValueError) as exc:
        result.update(status="invalid", error=str(exc))
        return result
    result["actual"] = actual
    result["status"] = "matched" if all(actual.get(key) == value for key, value in EXPECTED_LOCK.items()) else "mismatch"
    return result


def scan_source(sources: dict[str, GitSource]) -> dict[str, Any]:
    rust_sources = {relative: source for relative, source in sources.items()
                    if relative.startswith(CORE + "/") and relative.endswith(".rs")}
    text = {relative: source.data.decode("utf-8") for relative, source in rust_sources.items()}

    def matching(pattern: str, roots: tuple[str, ...]) -> list[str]:
        expression = re.compile(pattern)
        found: list[str] = []
        for relative, content in text.items():
            if any(relative.startswith(base + "/") for base in roots) and expression.search(content):
                found.append(relative)
        return sorted(found)

    binder = matching(
        r"\b(?:BINDER_WRITE_READ|BINDER_VERSION|binder_ioctl|BinderDevice|BinderDriver)\b",
        (CORE + "/device", CORE + "/fs", CORE + "/syscall"),
    )
    seccomp = matching(r"\b(?:PR_SET_SECCOMP|PR_GET_SECCOMP|sys_seccomp)\b", (CORE,))
    lsm_path = CORE + "/security/lsm/modules/mod.rs"
    lsm = text.get(lsm_path, "")
    selinux_path = CORE + "/security/lsm/modules/selinux.rs"
    # A mention in a comment or compatibility book is not a MAC module. Only
    # a registered module or an actual selinux implementation file counts as
    # a source candidate.
    selinux = []
    if selinux_path in rust_sources:
        selinux.append(selinux_path)
    if re.search(r"(?m)^\s*mod\s+selinux\s*;", lsm):
        selinux.append(lsm_path)
    inventory = b"".join(
        relative.encode("utf-8") + b"\0" + source.blob.encode("ascii") + b"\0"
        for relative, source in sorted(rust_sources.items())
    )
    return {
        "core_rust_file_count": len(rust_sources),
        "scanned_git_blobs_sha256": hashlib.sha256(inventory).hexdigest(),
        "binder_matches": binder,
        "seccomp_matches": seccomp,
        "selinux_matches": sorted(set(selinux)),
        "registered_lsm_modules": re.findall(r"(?m)^\s*mod\s+(\w+)\s*;", lsm),
    }


def build_report(root: Path, project_ref: str = "HEAD") -> dict[str, Any]:
    commit = git(root, "rev-parse", "--verify", "--end-of-options", f"{project_ref}^{{commit}}")
    tree = git(root, "rev-parse", f"{commit}^{{tree}}")
    sources = committed_sources(root, commit)
    files, missing = source_snapshot(sources)
    upstream_lock = verify_upstream_lock(sources.get(LOCK_PATH))
    scan = scan_source(sources)
    blockers: list[str] = []
    if not scan["binder_matches"]:
        blockers.append("binder")
    if not scan["seccomp_matches"]:
        blockers.append("seccomp")
    if not scan["selinux_matches"]:
        blockers.append("mac")
    if missing:
        blockers.append("source_paths")
    if upstream_lock["status"] != "matched":
        blockers.append("pinned_lock")
    observed_at = datetime.now(timezone.utc)
    return {
        "schema": 3,
        "observed_date": observed_at.date().isoformat(),
        "observed_at_utc": observed_at.isoformat(),
        "source_kind": "git_commit_objects",
        "requested_project_ref": project_ref,
        "project_commit": commit,
        "project_tree": tree,
        "kernel_upstream_lock": upstream_lock,
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
            "Only the selected immutable commit is inspected; working-tree changes are excluded.",
            "Expected upstream metadata is compared with the selected commit's hashed lock; matching metadata does not prove imported source equals the upstream tree.",
            "scanned_git_blobs_sha256 hashes sorted UTF-8 path, NUL, ASCII Git blob ID, NUL records.",
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
        help="Git ref to resolve once and inspect directly through immutable Git objects (default: HEAD)",
    )
    args = parser.parse_args()
    report = build_report(args.repo_root.resolve(), args.project_ref)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "blockers": report["blocking_requirements"], "commit": report["project_commit"]}, sort_keys=True))
    return 2 if report["blocking_requirements"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
