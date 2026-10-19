#!/usr/bin/env python3
"""Trace pinned *host Linux* A04 ELF cases using argument-free ptrace.

Unlike strace, the fallback records syscall number/errno (no paths/arguments).
The raw JSONL stays PRIVATE; the public aggregate retains counts, evidence
hashes and deterministic application observations. Neither means Hepta W1, A01
kernel testing, actual rootfs isolation or full dynamic dependency closure.
"""
import argparse
from collections import Counter
import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def imported(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = imported("a04_ptrace_runner", HERE / "run.py")
guest = imported("a04_ptrace_guest", HERE / "guest.py")
capture = imported("a04_ptrace_capture", ROOT / "support/rootfs/capture.py")


def syscall_numbers(header):
    pattern = re.compile(r"^#define\s+__NR_([A-Za-z0-9_]+)\s+(\d+)\s*$", re.M)
    names = {int(number): name for name, number in pattern.findall(header.read_text())}
    if not names or names.get(0) != "read":
        raise ValueError("incorrect Linux x86_64 syscall number table")
    return names


def inspect_trace(path):
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("trace log missing or empty")
    total = 0
    syscalls = Counter()
    errors = Counter()
    restarts = Counter()
    tids = set()
    exits = 0
    with path.open("rb") as trace:
        for blob in trace:
            row = json.loads(blob)
            if not isinstance(row, dict) or type(row.get("tid")) is not int or row["tid"] <= 0:
                raise ValueError("invalid trace event identity")
            tids.add(row["tid"])
            kind = row.get("kind")
            if kind == "syscall":
                nr, error = row.get("nr"), row.get("errno")
                internal_restart = row.get("internal_restart", 0)
                if type(internal_restart) is not int or internal_restart not in (0, 512, 513, 514, 515, 516):
                    raise ValueError("invalid kernel-internal restart")
                if error and internal_restart:
                    raise ValueError("internal restart cannot be reported as userspace errno")
                if type(nr) is not int or nr < 0 or type(error) is not int or error < 0 or error > 4095 or 512 <= error <= 516:
                    raise ValueError("invalid trace syscall number or errno")
                syscalls[nr] += 1
                if error:
                    errors[(nr, error)] += 1
                if internal_restart:
                    restarts[(nr, internal_restart)] += 1
                total += 1
            elif kind == "exit":
                if type(row.get("code")) is not int or row["code"] < 0 or row["code"] > 255:
                    raise ValueError("invalid process exit")
                exits += 1
            else:
                raise ValueError("unknown trace event")
    if total == 0 or exits == 0:
        raise ValueError("incomplete trace: no syscall completion or process exit")
    return {"syscall_events": total, "process_or_thread_exits": exits,
            "observed_threads": len(tids), "syscalls": syscalls,
            "syscall_errno": errors, "internal_restarts": restarts,
            "sha256": runner.digest(path), "bytes": path.stat().st_size}


def compile_tracer(output):
    command = ["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror",
               str(HERE / "ptrace_trace.c"), "-o", str(output)]
    p = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    if p.returncode:
        raise RuntimeError(f"ptrace tracer compile failed: {p.stderr[-1200:]}")
    return runner.digest(output)


def run(reference, rootfs, manifest_path, out, trace_dir, header):
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise ValueError("x86_64 Linux ptrace baseline required")
    if trace_dir.exists() or trace_dir.is_symlink():
        raise ValueError("private trace dir already exists: refusing overwrite")
    if out.exists():
        raise ValueError("aggregate output already exists: refusing overwrite")
    capture.verify(rootfs, manifest_path)
    fixed_manifest = json.loads(manifest_path.read_text())
    pinned = {x["name"]: x for x in fixed_manifest["elf"]}
    names = syscall_numbers(header)
    os.umask(0o077)
    trace_dir.mkdir(parents=True, mode=0o700)
    trace_dir.chmod(0o700)
    cases = {}
    errors = Counter()
    restarts = Counter()
    observed = Counter()
    with tempfile.TemporaryDirectory(prefix="a04-ptrace-work-") as scratch_dir:
        scratch = Path(scratch_dir)
        tracer = scratch / "a04-ptrace"
        tracer_sha = compile_tracer(tracer)
        env = os.environ.copy()
        for key in ("LD_PRELOAD", "LD_AUDIT", "LD_DEBUG", "LD_ORIGIN_PATH"):
            env.pop(key, None)
        env.update({"LC_ALL": "C", "TZ": "UTC", "LD_LIBRARY_PATH": str(rootfs / "lib/x86_64-linux-gnu")})
        for name, stem, case in guest.reference_elf_cases(reference):
            elf = pinned[guest.BINARY_FOR[stem]]
            binary = rootfs / elf["path"].lstrip("/")
            actual_sha = runner.digest(binary)
            if actual_sha != elf["sha256"] or actual_sha != reference["binaries"][stem]["sha256"]:
                raise ValueError("ELF changed: " + name)
            interp = reference["binaries"][stem]["interpreter"]
            command = [binary] if not interp else [rootfs / interp.lstrip("/"),
                          "--library-path", rootfs / "lib/x86_64-linux-gnu", binary]
            case_dir = scratch / name
            case_dir.mkdir()
            command += [case_dir] if stem.startswith("sqlite_") else [case, case_dir]
            raw_path = trace_dir / (name + ".jsonl")
            try:
                proc = subprocess.run([str(tracer), str(raw_path), "--", *map(str, command)],
                                      cwd=case_dir, env=env, capture_output=True,
                                      text=True, timeout=45, check=False)
                parsed = json.loads(proc.stdout.strip())
                traced = inspect_trace(raw_path)
                expected = reference["cases"][name]
                same = (proc.returncode == expected["exit_code"] == 0 and
                        isinstance(parsed, dict) and parsed == expected["facts"] and
                        parsed.get("ok") is True)
                cases[name] = {"status": "pass" if same else "fail",
                               "exit_code": proc.returncode,
                               "same_reference_facts": same,
                               "syscall_events": traced["syscall_events"],
                               "observed_threads": traced["observed_threads"],
                               "process_or_thread_exits": traced["process_or_thread_exits"],
                               "raw_trace_sha256": traced["sha256"],
                               "raw_trace_bytes": traced["bytes"],
                               "trace_private": True,
                               "error": None if same else "actual Linux case observations differ from pinned reference"}
                observed.update(traced["syscalls"])
                errors.update(traced["syscall_errno"])
                restarts.update(traced["internal_restarts"])
            except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                # Do not expose an absolute operator path or command in a
                # public aggregate: raw exception text stays local only.
                cases[name] = {"status": "blocked", "error_class": type(exc).__name__,
                               "trace_private": True}
    summary = {"schema": 1, "suite": "a04-linux-host-ptrace-syscall-observation",
               "kernel_guest_verified": False, "hepta_profile_verified": False,
               "trace_scope": "numeric_syscalls_and_errno_only; paths/NSS/TLS/services NOT captured",
               "source": "actual_ptrace_get_syscall_info_of_fixed_host_linux_ELF",
               "ptrace_tracer_sha256": tracer_sha, "source_sha256": runner.digest(HERE / "ptrace_trace.c"),
               "reference_sha256": runner.digest(HERE / "baselines/linux-debian13-x86_64.json"),
               "rootfs_manifest_sha256": runner.digest(manifest_path),
               "syscall_table_sha256": runner.digest(header),
               "arch": "x86_64", "trace_private": True,
               "cases": dict(sorted(cases.items())),
               "counts": {state: sum(c["status"] == state for c in cases.values())
                          for state in ("pass", "fail", "blocked")},
               "aggregate_syscalls": [{"number": nr, "name": names.get(nr, f"unknown_{nr}"),
                                       "count": count} for nr, count in sorted(observed.items())],
               "aggregate_internal_restarts": [{"number": nr, "name": names.get(nr, f"unknown_{nr}"),
                                                "internal_code": code, "count": count}
                                               for (nr, code), count in sorted(restarts.items())],
               "aggregate_syscall_errno": [{"number": nr, "name": names.get(nr, f"unknown_{nr}"),
                                              "errno": error, "errno_name": errno.errorcode.get(error, "UNKNOWN"),
                                              "count": count} for (nr, error), count in sorted(errors.items())]}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    out.chmod(0o600)
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reference", type=Path, required=True)
    ap.add_argument("--rootfs", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--private-trace-dir", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--syscall-header", type=Path,
                    default=Path("/usr/include/x86_64-linux-gnu/asm/unistd_64.h"))
    args = ap.parse_args()
    try:
        report = run(json.loads(args.reference.read_text()),args.rootfs.resolve(),args.manifest.resolve(),
                     args.output.resolve(),args.private_trace_dir.resolve(),args.syscall_header)
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        ap.exit(2, f"ptrace reference unavailable: {exc}\n")
    print(json.dumps({"counts": report["counts"], "syscall_kinds": len(report["aggregate_syscalls"]),
                      "kernel_guest_verified": False, "hepta_profile_verified": False}))
    expected_count = len(guest.reference_elf_cases(json.loads(args.reference.read_text())))
    return 0 if expected_count > 0 and report["counts"] == {"pass": expected_count, "fail": 0, "blocked": 0} else 2


if __name__ == "__main__":
    sys.exit(main())
