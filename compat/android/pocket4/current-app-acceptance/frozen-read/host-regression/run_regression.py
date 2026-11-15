#!/usr/bin/env python3
"""Compile pinned real release modules and reproduce the open-time FIFO race.

This Linux host regression never contacts Android or grants runtime readiness.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tempfile

from run_race import race


ORIGINAL_SHA256 = "df7eeb8d4b8e808a5273847eb61d28d986d02787c61755d5b674e5305192aa2b"
CANDIDATE_SHA256 = "786383bce459c120cd7bf978d6ad313743ef8a66b6ca002e422cbb234d2b55f9"
LOCK_SHA256 = "70f9e24fa3214a9acdd8944b9ab13939391a598353276671c11a026e7def0883"


def pinned(path, expected):
    path = path.resolve(strict=True)
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size < 1048576:
            raise RuntimeError("test input must be a bounded regular file")
        with os.fdopen(os.dup(fd), "rb") as stream:
            data = stream.read(1048576)
        after = os.fstat(fd)
        fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
                  "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, f) != getattr(after, f) for f in fields):
            raise RuntimeError("test input changed")
        if len(data) != before.st_size or hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError("test input SHA-256 differs")
        return data
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-registry-fetch", action="store_true")
    args = parser.parse_args()
    if not sys.platform.startswith("linux") or not hasattr(os, "pidfd_open"):
        raise RuntimeError("Linux with pidfd_open is required")
    allowed_cpus = sorted(os.sched_getaffinity(0))
    if len(allowed_cpus) <= 2:
        raise RuntimeError("compiler budget must leave two logical CPUs free")
    compiler_cpus = allowed_cpus[:min(2, len(allowed_cpus) - 2)]
    here = Path(__file__).resolve().parent
    original = pinned(args.original, ORIGINAL_SHA256)
    candidate = pinned(args.candidate, CANDIDATE_SHA256)
    lock = pinned(here / "Cargo.lock", LOCK_SHA256)
    report = {"schema": "p4-native-app-frozen-open-regression-v1",
              "original_source_sha256": ORIGINAL_SHA256,
              "candidate_source_sha256": CANDIDATE_SHA256,
              "cargo_lock_sha256": LOCK_SHA256,
              "host_affinity_cpu_count": len(allowed_cpus),
              "compiler_cpus": compiler_cpus,
              "Android_actions": 0, "runtime_qualified": False,
              "production_ready": False, "commands": [], "races": [],
              "status": "failed", "temporary_build_removed": False}
    build_root = None
    try:
        with tempfile.TemporaryDirectory(prefix="p4-app-frozen-regression-") as directory:
            root = Path(directory)
            build_root = root
            (root / "native-original-release.rs").write_bytes(original)
            (root / "native-candidate-release.rs").write_bytes(candidate)
            (root / "Cargo.lock").write_bytes(lock)
            shutil.copyfile(here / "Cargo.toml", root / "Cargo.toml")
            for which in ("original", "candidate"):
                driver = ('#[path = "native-' + which + '-release.rs"]\nmod release;\n'
                          'fn main() {\n'
                          ' let path = std::env::args_os().nth(1).expect("path");\n'
                          ' match release::read_frozen(std::path::Path::new(&path), 8 * 1024 * 1024) {\n'
                          '  Ok(raw) => println!("READ {}", raw.len()),\n'
                          '  Err(error) => { eprintln!("REJECT {error}"); std::process::exit(2); }\n'
                          ' }\n}\n')
                (root / ("native-" + which + "-main.rs")).write_text(driver)
            env = dict(os.environ, CARGO_BUILD_JOBS=str(len(compiler_cpus)),
                       CARGO_TARGET_DIR=str(root / "target"), RUSTFLAGS="-Dunused_imports")

            def command(argv, timeout=120):
                child = subprocess.Popen(argv, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         start_new_session=True,
                                         preexec_fn=lambda: os.sched_setaffinity(0, compiler_cpus))
                try:
                    stdout, stderr = child.communicate(timeout=timeout)
                except BaseException:
                    # This group was created exclusively for this command.
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    child.communicate(timeout=10)
                    raise
                entry = {"argv": [str(x).replace(str(root), "<owned-build>") for x in argv],
                         "returncode": child.returncode,
                         "stdout": stdout.decode("utf-8", "strict"),
                         "stderr": stderr.decode("utf-8", "strict").replace(str(root), "<owned-build>")}
                report["commands"].append(entry)
                if child.returncode:
                    raise RuntimeError("command failed: " + str(argv[0]))
                return entry

            version = command(["rustc", "+1.93.0", "--version"])
            if not version["stdout"].startswith("rustc 1.93.0 "):
                raise RuntimeError("fixed Rust 1.93.0 required")
            command(["cc", "-shared", "-fPIC", "-O2", "-o", str(root / "open_gate.so"),
                     str(here / "open_gate.c"), "-ldl"])
            cargo = ["cargo", "+1.93.0"]
            options = ["--locked"] + ([] if args.allow_registry_fetch else ["--offline"])
            command(cargo + ["build"] + options + ["--bins"])
            tests = command(cargo + ["test"] + options + ["--bin", "native-candidate-reader"])
            if "test result: ok. 10 passed; 0 failed; 0 ignored" not in tests["stdout"]:
                raise RuntimeError("complete ten native release tests required")
            for which, replacement, should_block in (("original", "fifo", True),
                                                      ("candidate", "fifo", False),
                                                      ("candidate", "symlink", False)):
                binary = root / ("target/debug/native-" + which + "-reader")
                result = race(binary, root / "open_gate.so", replacement)
                result.update(source=which, replacement=replacement,
                              binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
                report["races"].append(result)
                if result["timed_out_blocked_in_real_open"] != should_block:
                    raise RuntimeError("original/candidate blocking behavior differs")
                if not should_block and result["exit_code"] != 2:
                    raise RuntimeError("replacement must be rejected")
            positive = root / "ordinary-evidence.json"
            binary = root / "target/debug/native-candidate-reader"
            for content in (b"ordinary exact bytes\n", b""):
                positive.write_bytes(content)
                result = command([str(binary), str(positive)])
                if result["stdout"] != "READ " + str(len(content)) + "\n":
                    raise RuntimeError("normal/empty input changed")
            report["status"] = "passed"
    except Exception as error:
        report["error"] = type(error).__name__ + ": " + str(error)
    finally:
        report["temporary_build_removed"] = build_root is not None and not build_root.exists()
        with args.output.open("x") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
    print(json.dumps({"status": report["status"], "output": str(args.output),
                      "temporary_build_removed": report["temporary_build_removed"],
                      "Android_actions": 0}))
    return 0 if report["status"] == "passed" and report["temporary_build_removed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
