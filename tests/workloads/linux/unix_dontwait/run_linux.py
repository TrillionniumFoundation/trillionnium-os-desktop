#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Compile and execute the static reference probe on an ordinary Linux host."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import subprocess
import time

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        parser.error("output must be new")
    out.mkdir(parents=True)
    compiler = Path(shutil.which("gcc")).resolve()
    command = [str(compiler), "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror", "-static",
               str(HERE / "probe.c"), "-o", str(out / "probe.elf")]
    report = {"schema": "trillionnium.unix-dontwait-linux.v1", "passed": False,
              "source_sha256": sha(HERE / "probe.c"), "compiler_sha256": sha(compiler),
              "compiler_command": command, "host_kernel": platform.release(),
              "runtime_scope": "linux_reference", "native_guest_qualified": False}
    start = time.monotonic()
    try:
        with (out / "compile.log").open("wb") as log:
            report["compile_exit"] = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                                    timeout=60).returncode
        if report["compile_exit"] != 0:
            return 1
        report["binary_sha256"] = sha(out / "probe.elf")
        timed_out = False
        with (out / "stdout.jsonl").open("wb") as stdout, (out / "stderr.log").open("wb") as stderr:
            try:
                code = subprocess.run([str(out / "probe.elf")], stdin=subprocess.DEVNULL,
                                      stdout=stdout, stderr=stderr, timeout=25).returncode
            except subprocess.TimeoutExpired:
                code, timed_out = None, True
        spec = importlib.util.spec_from_file_location("unix_dontwait_check", HERE / "check.py")
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        report.update(exit_code=code, timed_out=timed_out,
                      oracle=checker.check((out / "stdout.jsonl").read_bytes(), code, timed_out),
                      stdout_sha256=sha(out / "stdout.jsonl"), stderr_sha256=sha(out / "stderr.log"),
                      checker_sha256=sha(HERE / "check.py"))
        report["source_unchanged"] = report["source_sha256"] == sha(HERE / "probe.c")
        report["passed"] = (report["oracle"]["passed"] and not (out / "stderr.log").read_bytes()
                            and report["source_unchanged"])
        return 0 if report["passed"] else 1
    finally:
        report["elapsed_seconds"] = time.monotonic() - start
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
