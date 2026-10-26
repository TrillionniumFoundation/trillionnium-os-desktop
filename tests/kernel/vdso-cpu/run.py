#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Real pinned libc/vDSO/SYS_getcpu agreement in owned ordinary QEMU guests."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("kernel_safety_runner", HERE.parent / "safety/run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
runner.PROBES = ("vdso_cpu",)
runner.SOURCE_FILES = {"vdso_cpu": [HERE / "probe.c"]}
base_initramfs = runner.initramfs


def initramfs(original, binaries, nonce, smp):
    entries = runner.unpack(gzip.decompress(base_initramfs(original, binaries, nonce, smp)))
    runner.require(not any(name.lstrip("./") == ".hepta-vdso-cpu-qa" for name, _, _ in entries),
                   "private CPU probe marker already exists")
    inode = max(fields[0] for _, fields, _ in entries) + 1
    entries.append((".hepta-vdso-cpu-qa", [inode, 0o100400, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0], (nonce + "\n").encode()))
    return gzip.compress(runner.pack(entries), mtime=0)


runner.initramfs = initramfs


def expected_cases(smp):
    fixed = {"setup.guest_guard", "setup.cpu_mask", "setup.vdso_entry", "main.mask_restored",
             "setup.thread_create", "thread.initial_tls", "thread.mask_restored",
             "setup.thread_join", "cleanup.main_state", "cleanup.monotonic"}
    return fixed | {f"{phase}.r{round}.cpu{cpu}.{key}"
                    for phase in ("main", "thread") for round in range(2) for cpu in range(smp)
                    for key in ("mask", "sys", "libc", "vdso", "lsl", "tls_selectors_tid")}


def validate(output, smp):
    base = json.loads((output / "result.json").read_text())
    raw = (output / "serial.log").read_bytes()
    runner.require(hashlib.sha256(raw).hexdigest() == base["serial_sha256"], "CPU serial digest differs")
    text = re.sub(r"\x1b\[[0-9;]*m", "", raw.decode()).replace("\r", "")
    rows = [json.loads(line) for line in text.splitlines() if line.startswith("{")]
    cases = [row for row in rows if "case" in row]
    samples = [row for row in rows if "sample" in row]
    names = [row["case"] for row in cases]
    expected = expected_cases(smp)
    runner.require(len(names) == len(set(names)) and set(names) == expected,
                   "CPU probe has missing, repeated or extra cases")
    sample_names = {f"{phase}.r{round}.cpu{cpu}" for phase in ("main", "thread")
                    for round in range(2) for cpu in range(smp)}
    runner.require(len(samples) == 4 * smp and {row["sample"] for row in samples} == sample_names,
                   "CPU sample inventory differs")
    failed = sorted(row["case"] for row in cases if row["passed"] is not True)
    observations_valid = True
    for phase in ("main", "thread"):
        selected = [row for row in samples if row["sample"].startswith(phase + ".")]
        runner.require(len({row["tid"] for row in selected}) == 1, "thread identity changed during CPU migration")
    runner.require(samples[0]["tid"] != next(row["tid"] for row in samples if row["sample"].startswith("thread.")),
                   "main and worker unexpectedly share a TID")
    for row in samples:
        target = int(row["sample"].split("cpu")[-1])
        observations_valid = observations_valid and row["target"] == target and row["sys_rc"] == 0 and row["sys_cpu"] == target and row["sys_node"] == 0 and row["libc_cpu"] == target and row["vdso_rc"] == 0 and row["vdso_cpu"] == target and row["vdso_node"] == 0 and row["lsl_valid"] == 1 and row["lsl_limit"] == target and row["cs"] == 0x33 and row["ss"] == 0x2b
    return {"schema": "a06.vdso-cpu-identity.v1", "passed": base["passed"] and not failed and observations_valid,
            "configured_vcpus": smp, "actual_cases": len(cases), "expected_cases": len(expected),
            "passed_cases": len(cases) - len(failed), "failed_cases": failed,
            "sample_inventory_complete": True, "pinned_samples": samples,
            "original_runner_passed": base["passed"], "qemu_exit": base["qemu_exit"],
            "timed_out": base["timed_out"], "probe_source_sha256": hashlib.sha256(runner.SOURCE_FILES["vdso_cpu"][0].read_bytes()).hexdigest(),
            "probe_sha256": base["probe_sha256"]["vdso_cpu"], "kernel_sha256": base["artifact_sha256"]["kernel.elf"],
            "serial_sha256": base["serial_sha256"], "production_qualified": False, "physical_hardware_qualified": False}


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--smp", type=int, choices=(1, 2, 4), default=1)
    parser.add_argument("--output", type=Path, required=True)
    known, _ = parser.parse_known_args()
    runner.PROBE_ARGS = {"vdso_cpu": f" --asterinas-disposable-guest --expected-cpus {known.smp}"}
    code = runner.main()
    output = known.output.resolve()
    try:
        report = validate(output, known.smp)
    except (OSError, ValueError, KeyError, TypeError) as error:
        report = {"schema": "a06.vdso-cpu-identity.v1", "passed": False, "error": str(error),
                  "production_qualified": False, "physical_hardware_qualified": False}
    (output / "cpu-identity.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, sort_keys=True))
    return 0 if code == 0 and report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
