#!/usr/bin/python3 -I
"""Pass argv unchanged; select explicitly recorded embedded build metadata."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import stat
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
env["CARGO"] = str(HERE / "cargo-metadata-wrapper.py")
env["OSDK_BUILD_USERNAME"] = policy["embedded_builder"]["username"]
env["OSDK_BUILD_HOSTNAME"] = policy["embedded_builder"]["hostname"]
path = Path(policy["output"]) / "rustc.jsonl"
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
try:
    if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_nlink != 1:
        raise ValueError("unsafe compiler log")
    fcntl.flock(fd, fcntl.LOCK_EX)
    payload = {"pid": os.getpid(), "cwd": os.getcwd(), "argv": sys.argv[1:],
               "incoming": incoming, "effective": {name: env.get(name) for name in incoming}}
    raw = (json.dumps(payload, sort_keys=True) + "\n").encode()
    with os.fdopen(fd, "wb", closefd=False) as stream:
        stream.write(raw)
        stream.flush()
finally:
    os.close(fd)
os.execvpe(sys.argv[1], sys.argv[1:], env)
