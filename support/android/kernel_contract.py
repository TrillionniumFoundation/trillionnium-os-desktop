#!/usr/bin/env python3
"""Source-only Android ABI gate against the actual imported Asterinas kernel.

This tool cannot certify a syscall, Binder, ART or Android execution. It reads
only Rust sources and a pinned metadata lock; missing critical Android kernel
requirements return a nonzero status. No kernel files are modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

PIN = "c4b7ed575b7b32773475b194d2ad41fb6d03765b"
TAG = "v0.19.0"
BASE = Path("kernel/core/src")
ENTRYPOINTS = {
    "futex": "syscall/futex.rs",
    "mmap": "syscall/mmap.rs",
    "mprotect": "syscall/mprotect.rs",
    "clone": "syscall/clone.rs",
    "execve": "syscall/execve.rs",
    "rt_sigaction": "syscall/rt_sigaction.rs",
    "sendmsg": "syscall/sendmsg.rs",
    "recvmsg": "syscall/recvmsg.rs",
    "memfd_create": "syscall/memfd_create.rs",
    "prctl": "syscall/prctl.rs",
    "ioctl": "syscall/ioctl.rs",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_file(root: Path, rel: str, files: dict, missing: list, *, optional: bool = False) -> str:
    path = root / BASE / rel
    if not path.is_file():
        if not optional:
            missing.append(str(BASE / rel))
        return ""
    data = path.read_bytes()
    files[str(BASE / rel)] = {"sha256": digest(data), "bytes": len(data)}
    return data.decode("utf-8", errors="replace")


def implementation_body_present(source: str, name: str) -> bool:
    # Ignore Rust single-line comments. A comment containing a method name
    # cannot certify it is implemented; no guarantee of semantic correctness.
    code = "\n".join(line.split("//", 1)[0] for line in source.splitlines())
    return bool(re.search(r"\bfn\s+sys_" + re.escape(name) + r"\s*\(", code))


def scan(kernel: Path, lock_path: Path) -> dict:
    result = {
        "schema": 1,
        "kernel_source": str(kernel.resolve()),
        "lock": str(lock_path.resolve()),
        "upstream_pin": PIN,
        "status": "not_scanned",
        "runtime_verified": False,
        "android_compatible": False,
        "source_checkout_tree_verified": False,
        "source_files": {},
        "missing_source_paths": [],
        "checks": {},
        "blocking_requirements": [],
        "notes": [
            "Source entrypoint presence never equals a passing syscall/Android runtime test.",
            "The Asterinas upstream Git tree SHA cannot be proven solely from imported file copies.",
            "Binder, seccomp and MAC still require real negative/runtime tests.",
        ],
    }
    try:
        lock = json.loads(lock_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        result["status"] = "lock_unavailable"
        result["blocking_requirements"].append("pinned_lock")
        result["error"] = str(exc)
        return result
    info = lock.get("kernel", {})
    if (info.get("commit") != PIN or info.get("tag") != TAG or
            info.get("reuse") != "full_kernel_derived"):
        result["status"] = "lock_mismatch"
        result["blocking_requirements"].append("pinned_lock")
        return result
    results = result["checks"]
    files = result["source_files"]
    missing = result["missing_source_paths"]
    dispatch = source_file(kernel, "syscall/mod.rs", files, missing)
    for syscall, rel in ENTRYPOINTS.items():
        source = source_file(kernel, rel, files, missing)
        entry = implementation_body_present(source, syscall)
        registered = bool(re.search(r"(?m)^\s*mod\s+" + re.escape(syscall) + r"\s*;", dispatch))
        results[syscall] = {
            "status": "source_entrypoint_only" if entry and registered else "missing_or_unregistered",
            "implementation_present": entry,
            "module_registered": registered,
            "runtime_verified": False,
            "owner": "A04/A05",
        }
    prctl = source_file(kernel, "syscall/prctl.rs", files, missing)
    seccomp = source_file(kernel, "syscall/seccomp.rs", files, missing, optional=True)
    syscall_seccomp = bool(re.search(r"\bfn\s+sys_seccomp\s*\(", seccomp)) and bool(
        re.search(r"(?m)^\s*mod\s+seccomp\s*;", dispatch))
    prctl_filter = bool(re.search(r"\bPR_SET_SECCOMP\b", prctl))
    results["seccomp"] = {
        "status": "source_entrypoint_only" if syscall_seccomp or prctl_filter else "missing_install_entrypoint",
        "syscall_entrypoint": syscall_seccomp,
        "prctl_entrypoint": prctl_filter,
        "tsync_verified": False,
        "negative_filter_test_passed": False,
        "owner": "A05",
    }
    # Only actual core device code and the core ioctl handler are inspected;
    # docs/test names mentioning Binder do not count as a driver.
    binder_re = re.compile(r"\b(?:BINDER_WRITE_READ|BINDER_VERSION|binder_ioctl|BinderDevice|BinderDriver)\b")
    binder_matches = []
    for directory in (kernel / BASE / "device", kernel / BASE / "fs", kernel / BASE / "syscall"):
        if directory.is_dir():
            for path in directory.rglob("*.rs"):
                data = path.read_bytes()
                if binder_re.search(data.decode("utf-8", errors="replace")):
                    relative = path.relative_to(kernel)
                    files[str(relative)] = {"sha256": digest(data), "bytes": len(data)}
                    binder_matches.append(str(relative))
    results["binder"] = {
        "status": "candidate_source_requires_ioctl_review" if binder_matches else "driver_not_evidenced",
        "candidates": sorted(binder_matches),
        "transactions_verified": False,
        "death_fd_identity_verified": False,
        "owner": "A05/A08",
    }
    registry = source_file(kernel, "security/lsm/modules/mod.rs", files, missing)
    mac_registered = bool(re.search(r"\bselinux::[A-Z_]+\b", registry))
    mac_file = kernel / BASE / "security/lsm/modules/selinux.rs"
    mac_file_exists = mac_file.is_file()
    if mac_file_exists:
        data = mac_file.read_bytes()
        files[str(mac_file.relative_to(kernel))] = {"sha256": digest(data), "bytes": len(data)}
    results["mac"] = {
        "status": "candidate_module_requires_policy_tests" if mac_registered and mac_file_exists else "selinux_equivalent_not_evidenced",
        "selinux_module_registered": mac_registered,
        "selinux_source_present": mac_file_exists,
        "negative_mac_tests_passed": False,
        "owner": "A05",
    }
    # cgroup and procfs presence does not mean lmkd gets actual PSI events.
    psi = (kernel / BASE / "fs/fs_impls/procfs/pressure").exists()
    cgroup_mem = (kernel / BASE / "fs/fs_impls/cgroupfs/controller/memory.rs").exists()
    results["lmkd_pressure"] = {
        "status": "source_candidates_only" if psi or cgroup_mem else "source_not_evidenced",
        "procfs_pressure_source_dir_present": psi,
        "cgroup_memory_source_present": cgroup_mem,
        "psi_event_behavior_verified": False,
        "app_freezer_verified": False,
        "owner": "A06/A08",
    }
    for req in ("binder", "seccomp", "mac"):
        if results[req]["status"] in (
            "driver_not_evidenced", "missing_install_entrypoint", "selinux_equivalent_not_evidenced"
        ):
            result["blocking_requirements"].append(req)
    if missing or any(v["status"] == "missing_or_unregistered" for v in
                      (results[x] for x in ENTRYPOINTS)):
        result["blocking_requirements"].append("source_syscall_coverage")
        result["status"] = "missing_core_sources"
    elif result["blocking_requirements"]:
        result["status"] = "source_review_blocked"
    else:
        result["status"] = "source_candidates_unverified"
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kernel-root", type=Path, required=True,
                        help="path to imported kernel/asterinas; no files are written here")
    parser.add_argument("--lock", type=Path, required=True,
                        help="project support/upstream-lock.json")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    result = scan(args.kernel_root, args.lock)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"status": result["status"],
                      "blockers": result["blocking_requirements"],
                      "runtime_verified": False}, sort_keys=True))
    # This scanner *never* makes an Android qualification claim. Known missing
    # features are a red gate even if host/Linux probes pass.
    return 3 if result["status"] in ("lock_unavailable", "lock_mismatch", "missing_core_sources") else 2 if result["blocking_requirements"] else 0


if __name__ == "__main__":
    sys.exit(main())
