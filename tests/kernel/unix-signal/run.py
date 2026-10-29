#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Real owned Unix STREAM signal/partial-write QA; never an authority bypass."""
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
spec = importlib.util.spec_from_file_location("_unix_signal_safety_runner", HERE.parent / "safety/run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
runner.PROBES = ("unix_signal",)
runner.SOURCE_FILES = {"unix_signal": [HERE / "probe.c"]}
runner.PROBE_ARGS = {"unix_signal": " --asterinas-disposable-guest"}
base_initramfs = runner.initramfs


def initramfs(original, binaries, nonce, smp):
    entries = runner.unpack(gzip.decompress(base_initramfs(original, binaries, nonce, smp)))
    runner.require(not any(posixpath.normpath("/" + name.lstrip("/")) == "/.hepta-unix-signal-qa"
                           for name, _, _ in entries), "private Unix signal marker already exists")
    inode = max(fields[0] for _, fields, _ in entries) + 1
    entries.append((".hepta-unix-signal-qa", [inode, 0o100400, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0],
                    (nonce + "\n").encode()))
    return gzip.compress(runner.pack(entries), mtime=0)


runner.initramfs = initramfs
APIS = ("send", "sendto", "sendmsg", "sendmmsg", "write", "writev")


def expected_cases():
    return ({"setup.guest_guard", "nonblock.backpressure", "nonblock.partial", "nonblock.epipe",
             "zero_default.send", "zero_nosignal.send", "writev.partial_shutdown",
             "writev.invalid_after_progress", "writev.empty_vector", "writev.offset_boundary"}
            | {f"{mode}.{api}" for mode in ("default", "handler", "seqpacket", "healthy") for api in APIS}
            | {f"{mode}.{api}" for mode in ("nosignal", "per_call") for api in APIS[:4]})


def observations_agree(rows):
    for name, row in rows.items():
        mode = name.split(".")[0]
        if mode in ("default", "zero_default"):
            valid = row["received"] == 0 and row["child_signal"] == 13 and row["child_exit"] == -1
        elif mode == "nonblock":
            if name.endswith("backpressure"):
                valid = row["rc"] == -1 and row["errno"] == 11 and row["filled"] > 8192 and row["signals"] == 0
            elif name.endswith("partial"):
                filled = rows["nonblock.backpressure"]["filled"]
                valid = row["drained"] == filled // 2 and 0 < row["rc"] < filled and row["signals"] == 0
            else:
                valid = row["shutdown"] == 0 and row["rc"] == -1 and row["errno"] == 32 and row["signals"] == 1
        elif mode == "writev":
            if name.endswith("partial_shutdown"):
                valid = row["completed"] == 8 and row["partials"] > 0 and row["positive_signals"] == 0
            elif name.endswith("invalid_after_progress"):
                valid = row["rc"] == 4 and row["received"] == 4 and row["bytes_ok"] == 1 and row["signals"] == 0
            elif name.endswith("empty_vector"):
                valid = row["shutdown"] == 0 and row["rc"] == 0 and row["signals"] == 0
            else:
                valid = row["rc"] == -1 and row["errno"] == 29 and row["signals"] == 0
        else:
            valid = (row["received"] == 1 and row["child_signal"] == 0 and row["child_exit"] == 0
                     and row["setup"] == 1)
            if mode == "healthy":
                valid = valid and row["rc"] == 4 and row["signals"] == 0
            else:
                valid = valid and row["rc"] == -1 and row["errno"] == 32 and row["signals"] == (1 if mode == "handler" else 0)
            if mode == "per_call":
                valid = valid and row["rc2"] == -1 and row["errno2"] == 32 and row["signals2"] == 1
        if not valid:
            return False
    return True


def evaluate(raw, qemu_exit, timed_out, excessive_output, base_passed):
    text = re.sub(r"\x1b\[[0-9;]*m", "", raw.decode()).replace("\r", "")
    rows = [json.loads(line) for line in text.splitlines() if line.startswith("{")]
    cases = [row for row in rows if "case" in row]
    observed = [row for row in rows if "observation" in row]
    names = [row["case"] for row in cases]
    expected = expected_cases()
    runner.require(len(names) == len(set(names)) and set(names) == expected,
                   "Unix signal case inventory differs")
    observations = {row["observation"]: row for row in observed}
    runner.require(len(observed) == len(observations) and set(observations) == expected - {"setup.guest_guard"},
                   "Unix signal observation inventory differs")
    runner.require(all(type(row["passed"]) is bool for row in cases), "non-boolean case result")
    runner.require(all(type(value) is int for row in observed for key, value in row.items() if key != "observation"),
                   "non-integer Unix signal observation")
    failed = sorted(row["case"] for row in cases if not row["passed"])
    warning_count = len(re.findall(r"(?:unsupported flags:|sendmmsg flags)[^\n]*MSG_NOSIGNAL", text))
    agree = observations_agree(observations)
    return {"passed": base_passed is True and qemu_exit == 33 and not timed_out and not excessive_output
                      and not failed and agree and warning_count == 0,
            "actual_cases": len(cases), "expected_cases": len(expected), "failed_cases": failed,
            "actual_observations": len(observed), "observations_agree": agree,
            "NOSIGNAL_unsupported_warnings": warning_count, "observations": observations}


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--product-evidence", type=Path, required=True)
    args, _ = parser.parse_known_args()
    code = runner.main()
    output = args.output.resolve()
    try:
        base = json.loads((output / "result.json").read_text())
        raw = (output / "serial.log").read_bytes()
        runner.require(hashlib.sha256(raw).hexdigest() == base["serial_sha256"], "Unix signal serial digest differs")
        report = evaluate(raw, base["qemu_exit"], base["timed_out"], base["excessive_output"], base["passed"])
        report.update(schema="a06.unix-signal.v1", source_head=base["product_source_head"],
                      source_tree=base["product_source_tree"],
                      kernel_sha256=base["artifact_sha256"]["kernel.elf"], probe_sha256=base["probe_sha256"]["unix_signal"],
                      serial_sha256=base["serial_sha256"], qemu_exit=base["qemu_exit"], timed_out=base["timed_out"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        report = {"schema": "a06.unix-signal.v1", "passed": False, "error": str(error)}
    report.update(production_qualified=False, native_hepta_qualified=False)
    (output / "unix-signal.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, sort_keys=True))
    return 0 if code == 0 and report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
