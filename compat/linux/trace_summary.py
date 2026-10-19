#!/usr/bin/env python3
"""Summarize completed strace calls; private arguments never enter public output.

`-ff -ttt` prints one file per PID but may split an interrupted system call
into `<unfinished ...>` and `<... syscall resumed>` lines. A half-call is
NOT a completed syscall, and the errno belongs to the resumed half. Treat
orphan/unfinished events as incomplete trace evidence rather than success.

Do not equate syscall count/loader closure with authenticated Hepta tool effect.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re

PREFIX = r"(?:\d+(?:\.\d+)?\s+)?"
CALL = re.compile(r"^" + PREFIX + r"([a-zA-Z_][a-zA-Z0-9_]*)\(")
RESUME = re.compile(r"^" + PREFIX + r"<\.\.\. ([a-zA-Z_][a-zA-Z0-9_]*) resumed>(.*)$")
UNFINISHED = re.compile(r"\s+<unfinished \.\.\.>\s*$")
RETURN = re.compile(r"\)\s+=\s+")
ERR = re.compile(r"\)\s+=\s+-1\s+([A-Z][A-Z0-9_]+)(?:\s|$)")
INTERNAL_RESTART = re.compile(r"\)\s+=\s+\?\s+(ERESTART[A-Z_]+)(?:\s|$)")
QUOTED = re.compile(r'"((?:\\.|[^"\\])*)"')
PROCESS_EXIT = re.compile(r"^" + PREFIX + r"\+\+\+ exited with (\d+) \+\+\+$")
PROCESS_SIGNAL = re.compile(r"^" + PREFIX + r"\+\+\+ killed by (SIG[A-Z0-9]+)(?: \([^)]*\))? \+\+\+$")
SHA_LINE = re.compile(r"^([0-9a-f]{64})  (.+)$")
SIGNAL_NOTICE = re.compile(r"^" + PREFIX + r"--- SIG[A-Z0-9]+(?: .*?)? ---$")
FILESYSTEM_CALLS = frozenset(("open", "openat", "openat2", "access", "faccessat",
                              "faccessat2", "stat", "lstat", "newfstatat", "statx",
                              "readlink", "readlinkat", "execve", "execveat"))


def summarize(trace_dir, *, include_paths=False):
    traces = sorted(p for p in trace_dir.glob("trace.*") if p.is_file() and
                    re.fullmatch(r"trace\.\d+", p.name))
    if not traces:
        raise ValueError("zero real trace.PID logs; cannot report trace captured")
    syscalls, errors, calls_by_error, paths, raw_files = Counter(), Counter(), Counter(), set(), []
    restarts = Counter()
    resumed_pairs = incomplete = orphan_resumptions = 0
    terminated, missing_terminal, terminated_by_signal, unknown_lines = 0, 0, Counter(), 0
    process_exit_codes = Counter()
    observed_hashes = {}
    for trace in traces:
        sha = hashlib.sha256()
        pending, terminal = None, False
        with trace.open("rb") as stream:
            for blob in stream:
                sha.update(blob)
                line = blob.decode("utf-8", "replace").rstrip("\r\n")
                if not line:
                    continue
                if terminal:
                    # Anything after +++ exited +++ means the trace is not a
                    # trustworthy single-process lifecycle transcript.
                    unknown_lines += 1
                    continue
                if (exited := PROCESS_EXIT.match(line)) is not None:
                    process_exit_codes[exited.group(1)] += 1
                    terminal = True
                    terminated += 1
                    continue
                if (signaled := PROCESS_SIGNAL.match(line)) is not None:
                    terminated_by_signal[signaled.group(1)] += 1
                    terminal = True
                    terminated += 1
                    continue
                if SIGNAL_NOTICE.match(line) or line.startswith("strace: Process "):
                    continue
                resumed = RESUME.match(line)
                if resumed:
                    syscall, tail = resumed.groups()
                    if pending is None or pending[0] != syscall:
                        orphan_resumptions += 1
                        if pending is not None:
                            incomplete += 1
                        pending = None
                        continue
                    name, original = pending
                    pending = None
                    line = original + tail
                    resumed_pairs += 1
                else:
                    match = CALL.match(line)
                    if match is None:
                        unknown_lines += 1
                        continue
                    syscall = match.group(1)
                    if UNFINISHED.search(line):
                        if pending is not None:
                            incomplete += 1
                        pending = (syscall, UNFINISHED.sub("", line))
                        continue
                    if pending is not None:
                        # Trace may have been lost/truncated across the gap.
                        incomplete += 1
                        pending = None
                match = CALL.match(line)
                if not match or not RETURN.search(line):
                    incomplete += 1
                    continue
                syscall = match.group(1)
                if (restart := INTERNAL_RESTART.search(line)) is not None:
                    # ERESTARTSYS and friends are kernel-internal; they are not
                    # errno observed by user code, and completion is uncertain.
                    restarts[f"{syscall}:{restart.group(1)}"] += 1
                    incomplete += 1  # not yet a userspace-visible return
                    continue
                syscalls[syscall] += 1
                if (error := ERR.search(line)) is not None:
                    errors[error.group(1)] += 1
                    calls_by_error[f"{syscall}:{error.group(1)}"] += 1
                if include_paths and syscall in FILESYSTEM_CALLS:
                    quoted = QUOTED.search(line[match.end():])
                    if quoted:
                        path = quoted.group(1)
                        # Relative paths are not generally resolvable from a
                        # strace log without a trustworthy per-process cwd.
                        if path.startswith("/") and "\\" not in path and "\x00" not in path:
                            paths.add(path)
        if pending is not None:
            incomplete += 1
        if not terminal:
            missing_terminal += 1
        observed_hashes[trace.name] = sha.hexdigest()
        raw_files.append({"sha256": sha.hexdigest(), "bytes": trace.stat().st_size})

    # A completed syscall fragment is NOT evidence of a completed Agentd
    # process tree. Require the actual strace -ff PID file manifest and the
    # wrapper's exit status, in addition to every PID's terminal marker.
    manifest_path = trace_dir / "trace-files.sha256"
    integrity = "missing"
    if manifest_path.is_file():
        declared = {}
        valid = True
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            match = SHA_LINE.fullmatch(line)
            if match is None:
                valid = False
                break
            digest, filename = match.groups()
            name = Path(filename).name
            if (not re.fullmatch(r"trace\.\d+", name) or
                    name in declared):
                valid = False
                break
            declared[name] = digest
        integrity = "verified" if valid and declared == observed_hashes else "mismatch"

    tracer_status = None
    tracer_exit_file = trace_dir / "exit-status.txt"
    if tracer_exit_file.is_file():
        contents = tracer_exit_file.read_text(encoding="ascii").strip()
        if re.fullmatch(r"(?:0|[1-9]\d{0,2})", contents) and int(contents) <= 255:
            tracer_status = int(contents)
    finished = sum(syscalls.values())
    if finished == 0:
        raise ValueError("zero completed syscalls; no dependency closure was observed")
    lifecycle_complete = (incomplete == orphan_resumptions == unknown_lines == missing_terminal == 0
                          and not terminated_by_signal and terminated == len(traces)
                          and integrity == "verified" and tracer_status == 0)
    report = {"schema": 4, "kind": "aggregate_trace_only", "raw_trace_private": True,
              "trace_file_count": len(raw_files), "raw_trace_hashes": raw_files,
              "completed_syscalls": finished, "resumed_pairs": resumed_pairs,
              "incomplete_syscalls": incomplete, "orphan_resumptions": orphan_resumptions,
              "trace_completeness": "complete" if lifecycle_complete else "incomplete",
              "trace_files_integrity": integrity, "strace_wrapper_exit_code": tracer_status,
              "processes_with_terminal_marker": terminated,
              "processes_missing_terminal_marker": missing_terminal,
              "process_exit_status_counts": dict(sorted(process_exit_codes.items())),
              "process_signal_termination_counts": dict(sorted(terminated_by_signal.items())),
              "unrecognized_trace_lines": unknown_lines,
              "kernel_internal_restarts": dict(sorted(restarts.items())),
              "syscalls": dict(sorted(syscalls.items())), "errors": dict(sorted(errors.items())),
              "syscall_errno": dict(sorted(calls_by_error.items())),
              "path_values_excluded": True, "tool_execution_verified": False,
              "hepta_e2e_verified": False,
              "note": "Lifecycle completeness requires every PID exit, verified PID-log hashes and zero wrapper exit. Completed calls or successful ELF loading alone never prove W1 execution."}
    return report, sorted(paths)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("trace_dir", type=Path)
    ap.add_argument("--output", type=Path, required=True, help="safe aggregate counts only")
    ap.add_argument("--private-path-output", type=Path,
                    help="NEW local private candidate runtime-path inventory; NEVER commit")
    args = ap.parse_args()
    if args.output.exists() or (args.private_path_output and args.private_path_output.exists()):
        ap.error("refusing to overwrite an existing trace report")
    if args.private_path_output and args.output.resolve() == args.private_path_output.resolve():
        ap.error("private paths must not share the public output file")
    try:
        report, paths = summarize(args.trace_dir, include_paths=args.private_path_output is not None)
    except (ValueError, OSError) as e:
        ap.exit(2, f"trace not obtained: {e}\n")
    os.umask(0o077)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    os.chmod(args.output, 0o600)
    if args.private_path_output:
        args.private_path_output.parent.mkdir(parents=True, exist_ok=True)
        private = {"schema": 1, "kind": "PRIVATE_trace_paths_DO_NOT_COMMIT",
                   "warning": "Paths may identify operators, user accounts or configuration; do not commit",
                   "files": [{"path": p} for p in paths], "status": "candidate_only_unverified"}
        args.private_path_output.write_text(json.dumps(private, indent=2, sort_keys=True) + "\n")
        os.chmod(args.private_path_output, 0o600)
    print(f"{report['trace_file_count']} trace files; {report['completed_syscalls']} completed calls; "
          f"lifecycle={report['trace_completeness']}; "
          f"PID-log integrity={report['trace_files_integrity']}; "
          f"private paths={len(paths)} (not in aggregate report); NO Hepta E2E claim")
    # Do not let a truncated/timeout strace report turn a CI job green. The
    # aggregate is still retained so the exact failure can be inspected.
    return 0 if report['trace_completeness'] == 'complete' else 3


if __name__ == "__main__":
    raise SystemExit(main())
