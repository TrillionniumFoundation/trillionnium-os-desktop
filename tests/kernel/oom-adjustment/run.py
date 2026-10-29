#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Owned OOM authority syscalls in one disposable, exact-product guest only."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import posixpath
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("_oom_owned_safety", HERE.parent / "safety/run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
runner.PROBES = ("oom_adjustment",)
runner.SOURCE_FILES = {"oom_adjustment": [HERE / "probe.c"]}
runner.PROBE_ARGS = {"oom_adjustment": " --asterinas-disposable-guest"}
base_initramfs = runner.initramfs


def initramfs(original, binaries, nonce, smp):
    entries = runner.unpack(gzip.decompress(base_initramfs(original, binaries, nonce, smp)))
    runner.require(not any(posixpath.normpath("/" + name.lstrip("/")) == "/.hepta-oom-adjustment-qa"
                           for name, _, _ in entries), "OOM QA marker already exists")
    inode = max(fields[0] for _, fields, _ in entries) + 1
    # Read-only to every guest UID so the nonprivileged replacement image can
    # revalidate its disposable-guest guard after a real exec.
    entries.append((".hepta-oom-adjustment-qa", [inode, 0o100444, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0],
                    (nonce + "\n").encode()))
    return gzip.compress(runner.pack(entries), mtime=0)


runner.initramfs = initramfs
# Ordered (requested value, expected errno) inventory. It describes the public
# syscall contract, not a relaxation of the historical native oracle.
WRITES = {
    "uid_floor": [(500, 0), (0, 0), (-1, 13), (-1001, 22), (1001, 22)],
    "privileged_floor": [(200, 0), (500, 0), (200, 0), (199, 13), (199, 13),
                         (-100, 0), (400, 0), (-100, 0), (-101, 13)],
    "fork": [(-100, 0), (500, 0), (-100, 0), (-101, 13), (200, 0), (0, 0)],
    "clone_vm_exit": [(200, 0), (199, 13), (500, 0), (-100, 0), (-100, 0),
                      (-101, 13), (0, 3), (0, 0)],
    "vfork": [(200, 0), (300, 0), (500, 0), (300, 0), (299, 13)],
    "threads": [(-100, 0), (500, 0), (-100, 0), (-101, 13),
                (200, 0), (500, 0), (200, 0), (199, 13)],
    "exec": [(-100, 0), (500, 0), (-100, 0), (-101, 13)],
    "clone_vm_exec": [(-100, 0), (500, 0), (200, 0), (-100, 0), (-101, 13)],
    "fd_credential": [(0, 0), (500, 0), (0, 0), (-1, 13)],
    "fd_transfer": [(0, 0), (500, 0), (0, 0), (-1, 13)],
    "owned_dac": [(500, 0), (0, 0), (-1, 13)],
}


def evaluate(raw, base):
    serial = re.sub(r"\x1b\[[0-9;]*m", "", raw.decode()).replace("\r", "")
    rows = [json.loads(line) for line in serial.splitlines() if line.startswith("{")]
    cases = [row for row in rows if "case" in row]
    names = [row["case"] for row in cases]
    expected = {"oom.setup", *("oom." + name for name in WRITES)}
    runner.require(len(names) == len(set(names)) and set(names) == expected,
                   "OOM case inventory differs")
    runner.require(all(type(row["passed"]) is bool for row in cases), "nonboolean OOM verdict")
    observed = [row for row in rows if "observation" in row]
    by_stage = {name: [] for name in WRITES}
    for row in observed:
        runner.require(set(row) == {"observation", "stage", "pid", "value", "rc", "errno", "expected_errno"}
                       and row["observation"] == "write" and row["stage"] in WRITES,
                       "unexpected OOM observation")
        runner.require(all(type(row[key]) is int for key in ("pid", "value", "rc", "errno", "expected_errno"))
                       and row["pid"] > 1, "malformed OOM observation")
        by_stage[row["stage"]].append((row["value"], row["expected_errno"]))
    inventory = all(by_stage[name] == expected_rows for name, expected_rows in WRITES.items())
    agree = all((row["rc"] == -1 and row["errno"] == row["expected_errno"])
                if row["expected_errno"] else
                (row["rc"] == len(str(row["value"])) + 1 and row["errno"] == 0)
                for row in observed)
    failed = sorted(row["case"] for row in cases if not row["passed"])
    return {"passed": base["passed"] is True and base["qemu_exit"] == 33
                      and not base["timed_out"] and not base["excessive_output"]
                      and not failed and inventory and agree,
            "expected_cases": len(expected), "actual_cases": len(cases),
            "failed_cases": failed, "observation_inventory_agrees": inventory,
            "syscall_observations_agree": agree, "actual_observations": len(observed),
            "expected_observations": sum(map(len, WRITES.values())), "observations": observed}


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--output", type=Path, required=True)
    # A matching clean source product is mandatory. The inherited runner's
    # optional dirty-development build route is deliberately unreachable here.
    parser.add_argument("--product-evidence", type=Path, required=True)
    args, _ = parser.parse_known_args()
    code = runner.main()
    output = args.output.resolve()
    try:
        base = json.loads((output / "result.json").read_text())
        raw = (output / "serial.log").read_bytes()
        runner.require(hashlib.sha256(raw).hexdigest() == base["serial_sha256"], "OOM serial digest differs")
        report = evaluate(raw, base)
        report.update(schema="a06.owned-oom-adjustment.v1", production_qualified=False,
                      source_head=base["product_source_head"], source_tree=base["product_source_tree"],
                      probe_sha256=base["probe_sha256"]["oom_adjustment"],
                      kernel_sha256=base["artifact_sha256"]["kernel.elf"],
                      serial_sha256=base["serial_sha256"],
                      clone_thread_vfork_combination_qualified=False,
                      initial_user_namespace="fixed ordinary guest; new user namespaces unsupported")
    except (ValueError, KeyError, UnicodeError, OSError) as error:
        report = {"passed": False, "error": str(error), "production_qualified": False}
    runner.save(output / "oom-adjustment.json", report)
    print(json.dumps(report, indent=2))
    return 0 if code == 0 and report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
