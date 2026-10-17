#!/usr/bin/env python3
"""Model the actual os-control transitions with a test-only Loom Mutex backend.

Run from any directory: python3 tests/control/loom/run-models.py OUTPUT_DIR
Optional --offline requires the pinned Cargo.lock dependencies to be cached.
No production source or Cargo dependency is edited. Every current src/**/*.rs
file is copied byte-for-byte into TemporaryDirectory; only src/sync.rs is then
replaced by the tracked Mutex shim. The temporary source and build artifacts are removed
on exit. Original source and harness hashes are checked again after validation.

Scope: lock-protected state transitions of the actual implementation, exercised
with Loom threads and harness atomics. Standard Arc/Weak ownership atomics,
allocator internals, kernel IRQ/preemption/SMP, real scheduler callbacks, crashes,
and executions exceeding the explicit model bounds remain outside this check.
Panic/unwind recovery is also excluded: Loom 0.7.2's Mutex::lock internally
unwraps its underlying std Mutex after poison before the adapter can recover.
The malformed-outcome model checks a pending post-effect path without unwind;
it must not be reported as verification of panic recovery.
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
    source_root = repo / "libs/os-control/src"
    source_paths = sorted(source_root.rglob("*.rs"))
    source_inventory = [str(path.relative_to(repo)) for path in source_paths]
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
        "source_inventory": source_inventory,
        "source_inventory_unchanged": False,
        "models": {},
        "bounds": {
            "max_threads": 4,
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
            "more than three concurrent workers or more than three preemptions",
            "panic/unwind recovery: Loom 0.7.2 Mutex::lock internally unwraps on poison",
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
        for path in source_paths:
            relative = path.relative_to(source_root)
            copied = src / relative
            copied.parent.mkdir(parents=True, exist_ok=True)
            data = inputs[str(path.relative_to(repo))]
            copied.write_bytes(data)
            assert copied.read_bytes() == data
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
            "retire_execute_loss_threeway",
            "two_deliveries_same_resource_cas",
            "malformed_callback_reconcile_and_retry",
            "management_revoke_and_native_commit_share_owner_lock",
            "reservation_loss_and_query_revalidate_admission",
            "overlapping_retirements_revalidate_smaller_prefix",
        }
        if not exit_code and (set(receipt["models"]) != expected_models
                              or any(count <= 0 for count in receipt["models"].values())):
            print("ERROR: expected twelve named models with positive schedule counts", file=sys.stderr)
            exit_code = 1
    after_inventory = [str(path.relative_to(repo)) for path in
                       sorted(source_root.rglob("*.rs"))]
    receipt["source_inventory_unchanged"] = after_inventory == source_inventory
    after = {name: digest((repo / name).read_bytes()) if (repo / name).is_file() else None
             for name in hashes}
    receipt["source_unchanged"] = after == hashes and receipt["source_inventory_unchanged"]
    if not receipt["source_unchanged"]:
        print("ERROR: input source or harness changed while modeling", file=sys.stderr)
        exit_code = 1
    receipt["exit_code"] = exit_code
    (output / "results.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Evidence: {output}; source_unchanged={receipt['source_unchanged']}; exit={exit_code}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
