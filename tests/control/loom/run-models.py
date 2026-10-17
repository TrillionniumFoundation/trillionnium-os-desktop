#!/usr/bin/env python3
"""Model the actual os-control transitions with a test-only Loom Mutex backend.

Run from any directory: python3 tests/control/loom/run-models.py OUTPUT_DIR
Optional --offline requires the pinned Cargo.lock dependencies to be cached.
No production source or Cargo dependency is edited. The exact current lib.rs
and native.rs bytes are copied into TemporaryDirectory; only sync.rs is replaced
by the tracked Mutex shim. The temporary source and build artifacts are removed
on exit. Original source and harness hashes are checked again after validation.

Scope: lock-protected state transitions of the actual implementation, exercised
with Loom threads and harness atomics. Standard Arc/Weak ownership atomics,
allocator internals, kernel IRQ/preemption/SMP, real scheduler callbacks, crashes,
and executions exceeding the explicit model bounds remain outside this check.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    harness = Path(__file__).resolve().parent
    repo = harness.parents[2]
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source_paths = [
        repo / "libs/os-control/src/lib.rs",
        repo / "libs/os-control/src/native.rs",
        repo / "libs/os-control/src/sync.rs",
    ]
    harness_paths = [harness / name for name in
                     ("Cargo.toml", "Cargo.lock", "models.rs", "sync.rs", "run-models.py")]
    inputs = {str(path.relative_to(repo)): path.read_bytes()
              for path in source_paths + harness_paths}
    hashes = {name: digest(data) for name, data in inputs.items()}
    (output / "source-manifest.sha256").write_text(
        "".join(f"{value}  {name}\n" for name, value in sorted(hashes.items())))
    receipt = {
        "kind": "bounded host model; actual state transitions with Loom Mutex shim",
        "loom_version": "0.7.2",
        "source_hashes": hashes,
        "source_unchanged": False,
        "models": {},
        "bounds": {
            "max_threads": 3,
            "preemption_bound": 3,
            "max_branches": 10000,
            "max_permutations": None,
            "max_duration": None,
        },
        "excluded": [
            "std/alloc Arc and Weak reference-count atomics and finalization ordering",
            "allocator internals and allocation failure",
            "real kernel IRQ, preemption, SMP, lock adapters and scheduler mutation",
            "real credentials and Hepta durable acknowledgement/crash recovery",
            "more than two concurrent workers or more than three preemptions",
            "arbitrary request values and long sequence histories beyond each fixture",
        ],
        "commands": [],
    }
    cargo = os.environ.get("CARGO", "cargo")
    versions = {}
    for program in (cargo, "rustc"):
        command = [program, "--version"]
        proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, check=False)
        versions[program] = proc.stdout.strip()
        receipt["commands"].append({"argv": command, "exit_code": proc.returncode})
        if proc.returncode:
            (output / "results.json").write_text(json.dumps(receipt, indent=2) + "\n")
            sys.stdout.write(proc.stdout)
            return proc.returncode
    receipt["versions"] = versions
    exit_code = 0
    with tempfile.TemporaryDirectory(prefix="os-control-loom-") as temporary:
        root = Path(temporary)
        src = root / "src"
        src.mkdir()
        for name in ("lib.rs", "native.rs"):
            data = inputs[f"libs/os-control/src/{name}"]
            (src / name).write_bytes(data)
            assert (src / name).read_bytes() == data
        for name in ("Cargo.toml", "Cargo.lock", "models.rs"):
            (root / name).write_bytes(inputs[f"tests/control/loom/{name}"])
        (src / "sync.rs").write_bytes(inputs["tests/control/loom/sync.rs"])
        environment = os.environ.copy()
        # Never resume a checkpoint or inherit scheduling bounds from the shell.
        for key in list(environment):
            if key.startswith("LOOM_"):
                del environment[key]
        environment["CARGO_TARGET_DIR"] = str(root / "target")
        common = ["--locked", "--manifest-path", str(root / "Cargo.toml")]
        if args.offline:
            common.append("--offline")
        commands = [
            [cargo, "fmt", "--manifest-path", str(root / "Cargo.toml"), "--", "--check"],
            [cargo, "test", *common, "--test", "models", "--", "--nocapture", "--test-threads=1"],
            [cargo, "clippy", *common, "--test", "models", "--", "-D", "warnings"],
        ]
        log = []
        for command in commands:
            print("RUN " + " ".join(command), flush=True)
            proc = subprocess.run(command, cwd=root, env=environment,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, check=False)
            sys.stdout.write(proc.stdout)
            sys.stdout.flush()
            receipt["commands"].append({"argv": command, "exit_code": proc.returncode})
            log.append("$ " + " ".join(command) + "\n" + proc.stdout)
            if proc.returncode:
                exit_code = proc.returncode
                break
        combined = "\n".join(log)
        (output / "models.log").write_text(combined)
        receipt["models"] = {
            name: int(count) for name, count in
            re.findall(r"MODEL (\w+): schedules=(\d+)", combined)
        }
        expected_models = {
            "same_d_reservation_and_effect_once",
            "revoke_and_commit_linearize",
            "retire_and_query_linearize",
            "publish_and_observe_never_tear",
            "history_loss_and_callback_fence",
            "native_typed_owner_same_token_effect_once",
        }
        if not exit_code and (set(receipt["models"]) != expected_models
                              or any(count <= 0 for count in receipt["models"].values())):
            print("ERROR: expected six named models with positive schedule counts", file=sys.stderr)
            exit_code = 1
    after = {name: digest((repo / name).read_bytes()) for name in hashes}
    receipt["source_unchanged"] = after == hashes
    if not receipt["source_unchanged"]:
        print("ERROR: input source or harness changed while modeling", file=sys.stderr)
        exit_code = 1
    receipt["exit_code"] = exit_code
    (output / "results.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Evidence: {output}; source_unchanged={receipt['source_unchanged']}; exit={exit_code}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
