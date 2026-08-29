#!/usr/bin/env python3
"""Verify bounded D2I evidence for an actual Servo child-process crash.

This verifier deliberately requires OS-process identity before and after SIGKILL.
A logical WebView rebuild, a callback injected by the test harness, or a main
service restart is not accepted as a content-process crash proof.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

HEX64 = re.compile(r"^[0-9a-f]{64}$")
PASS = "PASS_ACTUAL_CONTENT_PROCESS_CRASH_AND_RECOVERY"


class VerificationError(RuntimeError):
    pass


def load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"{label} is unreadable or invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"{label} must be a JSON object")
    return value


def require(value: bool, message: str) -> None:
    if not value:
        raise VerificationError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(proof_path: Path, runtime_path: Path, qemu_command_path: Path) -> dict[str, Any]:
    proof = load_object(proof_path, "content crash proof")
    runtime = load_object(runtime_path, "runtime evidence")
    qemu_command = qemu_command_path.read_text()

    require(proof.get("schema") == "trillionnium.desktop.d2i-content-process-crash-proof.v1", "unexpected proof schema")
    require(proof.get("status") == PASS, "content crash proof did not pass")
    require(proof.get("runtime_main_survived") is True, "runtime main process did not survive")
    require(proof.get("sigkill_delivered") is True, "SIGKILL delivery is not proven")
    require(proof.get("killed_pid_disappeared") is True, "killed PID disappearance is not proven")
    require(proof.get("replacement_pid_distinct") is True, "replacement PID is not distinct")
    require(proof.get("crash_callback_observed") is True, "Servo crash callback is not observed")
    require(proof.get("trusted_chrome_visible_after_crash") is True, "trusted chrome survival is not proven")

    main_pid = proof.get("runtime_main_pid")
    killed_pid = proof.get("killed_content_pid")
    replacement_pid = proof.get("replacement_content_pid")
    for label, value in (("runtime main PID", main_pid), ("killed content PID", killed_pid), ("replacement content PID", replacement_pid)):
        require(isinstance(value, int) and value > 1, f"{label} must be a positive non-init PID")
    require(main_pid != killed_pid, "main process was mislabeled as content")
    require(main_pid != replacement_pid, "replacement process was mislabeled as main")
    require(killed_pid != replacement_pid, "killed and replacement PIDs are identical")

    for key in ("killed_content_start_time_ticks", "replacement_content_start_time_ticks"):
        require(isinstance(proof.get(key), int) and proof[key] > 0, f"{key} is invalid")
    for key in ("killed_content_cmdline_sha256", "replacement_content_cmdline_sha256"):
        require(isinstance(proof.get(key), str) and HEX64.fullmatch(proof[key]) is not None, f"{key} is invalid")

    generation = proof.get("runtime_generation_after_recovery")
    require(isinstance(generation, int) and generation >= 2, "recovery did not advance runtime generation")
    runtime_generation = runtime.get("generation", runtime.get("session_generation", 0))
    require(isinstance(runtime_generation, int) and runtime_generation >= generation, "runtime evidence regressed below crash proof generation")
    require(runtime.get("trusted_chrome_visible") is True, "runtime evidence does not preserve trusted chrome")
    require(runtime.get("crash_callback_observed", runtime.get("content_crash_observed")) is True, "runtime evidence lacks crash callback")

    forbidden_network = ("-netdev", "-nic", "-device e1000", "-device virtio-net", "user,id=")
    for token in forbidden_network:
        require(token not in qemu_command, f"QEMU command enables a network path: {token}")
    require("-nodefaults" in qemu_command or "-nic none" in qemu_command, "QEMU network-closed intent is not explicit")

    return {
        "schema": "trillionnium.desktop.d2i-content-process-crash-verification.v1",
        "status": PASS,
        "proof_sha256": sha256(proof_path),
        "runtime_evidence_sha256": sha256(runtime_path),
        "qemu_command_sha256": sha256(qemu_command_path),
        "runtime_main_pid": main_pid,
        "killed_content_pid": killed_pid,
        "replacement_content_pid": replacement_pid,
        "runtime_generation_after_recovery": generation,
        "claim": {
            "actual_content_process_crash_proven": True,
            "main_runtime_survived": True,
            "trusted_chrome_survived": True,
            "replacement_content_process_observed": True,
            "network_device_present": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proof", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--qemu-command", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify(args.proof, args.runtime, args.qemu_command)
    except (OSError, VerificationError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(PASS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
