#!/usr/bin/python3 -I
"""Only the pinned component macro's exact metadata command is projected."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("a01_repro_profile", HERE / "profile.py")
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)
policy = json.loads(profile.regular(Path(os.environ["A01_REPRO_POLICY"]))[0])
real_cargo = policy["real_cargo"]
env = os.environ.copy()
env["CARGO"] = real_cargo
args = sys.argv[1:]
if args != ["metadata", "--format-version", "1"]:
    os.execve(real_cargo, [real_cargo, *args], env)
result = subprocess.run([real_cargo, *args], env=env,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
prefix = Path(policy["output"]) / "metadata" / f"{os.getpid()}-{time.monotonic_ns()}"


def retain_refusal(kind, value, traceback):
    try:
        profile.exclusive(prefix.with_suffix(".refusal.json"),
                          (json.dumps({"error_type": kind.__name__, "message": str(value)}) + "\n").encode())
    except OSError:
        pass
    sys.__excepthook__(kind, value, traceback)


sys.excepthook = retain_refusal
profile.exclusive(prefix.with_suffix(".original.json"), result.stdout)
profile.exclusive(prefix.with_suffix(".stderr.log"), result.stderr)
if result.returncode:
    sys.stderr.buffer.write(result.stderr)
    sys.exit(result.returncode)
root = Path(policy["profile_root"])
before = profile.snapshot(root)
if before != policy["profile_snapshot"]:
    raise ValueError("profile input custody changed")
source, source_identity = profile.regular(Path(policy["real_root"]) / "Components.toml")
mirror, mirror_identity = profile.regular(Path(policy["virtual_root"]) / "Components.toml")
if source != mirror or profile.digest(source) != policy["components_sha256"]:
    raise ValueError("virtual Components.toml differs from the actual source input")
profile.verify_project_inputs(policy)
mapped, checks = profile.project_metadata(json.loads(result.stdout), policy["real_root"],
                                         policy["virtual_root"], source, policy)
encoded = (json.dumps(mapped, separators=(",", ":")) + "\n").encode()
profile.exclusive(prefix.with_suffix(".mapped.json"), encoded)
receipt = {"original_sha256": profile.digest(result.stdout),
           "mapped_sha256": profile.digest(encoded), "component_membership": checks,
           "source_identity": source_identity, "mirror_identity": mirror_identity}
profile.exclusive(prefix.with_suffix(".binding.json"),
                  (json.dumps(receipt, indent=2) + "\n").encode())
profile.verify_project_inputs(policy)
if profile.snapshot(root) != before:
    raise ValueError("profile input changed during metadata projection")
sys.stderr.buffer.write(result.stderr)
sys.stdout.buffer.write(encoded)
