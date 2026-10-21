#!/usr/bin/python3 -I
"""Preserve Cargo/OSDK flags and enforce the canonical compiler path map."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("a01_repro_profile", HERE / "profile.py")
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)
env = os.environ.copy()
policy = json.loads(profile.regular(Path(env["A01_REPRO_POLICY"]))[0])
incoming = {name: env.get(name) for name in
            ("CARGO", "CARGO_MANIFEST_DIR", "OSDK_BUILD_USERNAME", "OSDK_BUILD_HOSTNAME")}
incoming_argv = sys.argv[1:]
effective_argv = profile.compiler_argv(incoming_argv, policy)
units_path = Path(policy["output"]) / "compiler-units.jsonl"
units_fd = os.open(units_path, os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
if not stat.S_ISREG(os.fstat(units_fd).st_mode) or os.fstat(units_fd).st_nlink != 1:
    os.close(units_fd)
    raise ValueError("unsafe compiler producer ledger")


def append_unit(record):
    with os.fdopen(units_fd, "wb", closefd=False) as ledger:
        ledger.write((json.dumps(record, sort_keys=True) + "\n").encode())
        ledger.flush()


try:
    fcntl.flock(units_fd, fcntl.LOCK_EX)
    os.lseek(units_fd, 0, os.SEEK_SET)
    with os.fdopen(units_fd, "rb", closefd=False) as ledger:
        history = [json.loads(line) for line in ledger]
    effective_argv, unit = profile.canonical_compiler_metadata(
        effective_argv, env, os.getcwd(), policy, history)
    append_unit({"state": "started", "pid": os.getpid(), "unit": unit})
finally:
    fcntl.flock(units_fd, fcntl.LOCK_UN)
env["CARGO"] = str(HERE / "cargo-metadata-wrapper.py")
env["OSDK_BUILD_USERNAME"] = policy["embedded_builder"]["username"]
env["OSDK_BUILD_HOSTNAME"] = policy["embedded_builder"]["hostname"]
path = Path(policy["output"]) / "rustc.jsonl"
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
try:
    if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_nlink != 1:
        raise ValueError("unsafe compiler log")
    fcntl.flock(fd, fcntl.LOCK_EX)
    payload = {"pid": os.getpid(), "cwd": os.getcwd(), "argv": effective_argv,
               "incoming_argv": incoming_argv, "effective_argv": effective_argv,
               "incoming": incoming, "effective": {name: env.get(name) for name in incoming},
               "compiler_unit": unit}
    raw = (json.dumps(payload, sort_keys=True) + "\n").encode()
    with os.fdopen(fd, "wb", closefd=False) as stream:
        stream.write(raw)
        stream.flush()
finally:
    os.close(fd)
# Supervise the actual compiler so only successful, unchanged producers can
# satisfy later --extern bindings. Preserve Cargo's inherited jobserver FDs.
returncode = 127
try:
    returncode = subprocess.run(effective_argv, env=env, close_fds=False).returncode
finally:
    fcntl.flock(units_fd, fcntl.LOCK_EX)
    try:
        append_unit({"state": "completed", "pid": os.getpid(), "unit": unit,
                     "returncode": returncode,
                     "artifacts": profile.completed_artifacts(unit) if returncode == 0 else {}})
    finally:
        os.close(units_fd)
if returncode < 0:
    import signal
    signal.signal(-returncode, signal.SIG_DFL)
    os.kill(os.getpid(), -returncode)
raise SystemExit(returncode)
