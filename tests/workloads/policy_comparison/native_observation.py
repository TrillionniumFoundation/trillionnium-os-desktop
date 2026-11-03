#!/usr/bin/env python3
"""Read-only import of original native-owner cycle evidence, never a policy trial.

Reuses the existing strict raw-event oracle. Its bounded usage windows are
useful prerequisites, but lack three controllers, task metrics and whole-arm
energy/cost observations. They must remain ineligible for a policy ranking.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import comparison as contract

ORACLE_PATH = Path(__file__).resolve().parents[1] / "hepta_cpu_control/native_owner_evidence.py"
spec = importlib.util.spec_from_file_location("original_native_owner_evidence", ORACLE_PATH)
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)


def retained(directory, relative, expected_sha, maximum=contract.MAX_JSON):
    path = directory / relative
    contract.artifact(directory, {"path": relative, "bytes": path.stat().st_size,
                                 "sha256": expected_sha}, relative, maximum)
    return path.read_bytes()


def import_cycle(directory, expected_receipt_sha256, expected_sources):
    directory = Path(directory).resolve(strict=True)
    raw_result = retained(directory, "result.json", expected_receipt_sha256)
    report = oracle.json_value(raw_result)
    contract.require(report.get("schema") == "hepta.native-original-owner-result.v1"
                     and report.get("stage") == "complete" and report.get("passed") is True
                     and report.get("original_native_owner_cycle_verified") is True,
                     "a successful original native-owner receipt is required")
    for repository in ("desktop", "hepta"):
        expected = expected_sources[repository]
        contract.source(expected, repository)
        contract.require(all(report["sources"][repository].get(key) == expected[key] for key in ("head", "tree")),
                         "original owner used another " + repository + " source")
    contract.require(all(report["harness_source"].get(key) == expected_sources["desktop"][key]
                         for key in ("head", "tree")), "native harness source differs from the selected Desktop")
    contract.require(report.get("source_inputs_unchanged") is True, "original source after-check missing")
    contract.require(report.get("g2_complete") is False and report.get("production_ready") is False,
                     "this finite-cycle adapter cannot inherit broader qualification")
    imported = {}
    scenarios = report.get("scenarios")
    contract.require(type(scenarios) is dict and scenarios and set(scenarios) <= set(oracle.SCENARIOS),
                     "known finite owner scenarios required")
    for name, case in scenarios.items():
        local_case = contract.read_json(directory / name / "result.json")
        contract.require(local_case == case, "retained scenario receipt changed")
        raw = retained(directory, name + "/serial.log", case["raw_serial_sha256"], oracle.MAX_SERIAL_BYTES)
        raw_qemu = retained(directory, name + "/qemu.json", case["actual_qemu_record_sha256"])
        qemu = oracle.json_value(raw_qemu)
        contract.require(qemu["serial_sha256"] == hashlib.sha256(raw).hexdigest()
                         and qemu["serial_bytes"] == len(raw), "QEMU record belongs to another serial stream")
        observed = oracle.evaluate(raw, qemu["raw_exit_code"], qemu["timed_out"], qemu["serial_excessive"],
                                   name, case["nonce"], report["original_elf_shape"])
        contract.require(all(case.get(key) == value for key, value in observed.items()),
                         "original oracle replay differs from the retained receipt")
        _, events = oracle.parse(raw, name, case["nonce"])
        windows = []
        for _, event in events:
            if event["event"] == "usage_window":
                payload = event["payload"]
                first, second = payload["first"], payload["second"]
                windows.append({"operation": payload["operation"],
                                "elapsed_boottime_ns": second["sample_boottime_ns"] - first["sample_boottime_ns"],
                                "workload_cpu_ns": second["cumulative_cpu_ns"] - first["cumulative_cpu_ns"],
                                "heartbeat_delta": second["heartbeat"] - first["heartbeat"],
                                "scope": "original one-workload native counters; excludes controller/inference/host costs"})
        imported[name] = {"original_oracle_replayed": True, "raw_serial_sha256": case["raw_serial_sha256"],
                          "event_count": observed["event_count"], "usage_windows": windows}
    return {"schema": "hepta.cpu-policy-native-prerequisite.v1", "source_receipt_sha256": expected_receipt_sha256,
            "sources": report["sources"], "oracle_source_sha256": hashlib.sha256(ORACLE_PATH.read_bytes()).hexdigest(),
            "scenarios": imported, "scope": "finite original-owner protocol prerequisite only",
            "policy_arm": None, "whole_arm_costs": None, "task_success_latency": None, "energy": None,
            "comparison_complete": False, "ranking_allowed": False, "production_ready": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-result-directory", type=Path, required=True)
    parser.add_argument("--expected-receipt-sha256", required=True)
    parser.add_argument("--source-inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        inventory = contract.read_json(args.source_inventory)
        result = import_cycle(args.native_result_directory, args.expected_receipt_sha256, inventory["sources"])
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 2
    with args.output.open("x", encoding="utf-8") as output:
        output.write(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"original_oracle_replayed": True, "ranking_allowed": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
