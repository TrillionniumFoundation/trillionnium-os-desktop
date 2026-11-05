#!/usr/bin/env python3
"""One local exact-source transport/held-task control; no service or role grant."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "local03"
INPUTS = (
    "source/role_authorization.h", "source/role_authorization.cc",
    "source/factory_context.h", "source/factory_context.cc",
    "controls/protocol_controls.cc",
)


def pin(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-once", action="store_true")
    args = parser.parse_args()
    if not args.execute_once:
        print(json.dumps({"state": "PLAN_ONLY", "output": str(OUTPUT),
                          "service_started": False, "registry_positive": False}))
        return 0
    OUTPUT.mkdir(mode=0o700, exist_ok=False)
    result = {"schema": 1, "state": "FAIL", "commands": [],
              "scope": "Local exact-source protocol and held caller task controls",
              "main_actions": 0, "factory_service_started": False,
              "registry_positive_authorization_executed": False,
              "platform_filter_executed": False,
              "forced_numeric_tid_reuse": False,
              "source_pins": {}, "source_unchanged_after": False,
              "tool_unchanged_after": False}
    error = None
    sources = {}
    compiler = Path(shutil.which("g++") or "/nonexistent").resolve(strict=True)
    compiler_data = compiler.read_bytes()
    result["compiler"] = {"path": str(compiler), **pin(compiler_data)}

    def run(argv, name, timeout):
        start = time.monotonic_ns()
        try:
            completed = subprocess.run(argv, cwd=OUTPUT, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       timeout=timeout, check=False)
            out, err = completed.stdout, completed.stderr
            row = {"argv": argv, "returncode": completed.returncode, "timed_out": False}
        except subprocess.TimeoutExpired as exception:
            out, err = exception.stdout or b"", exception.stderr or b""
            row = {"argv": argv, "returncode": None, "timed_out": True}
        (OUTPUT / (name + ".stdout")).write_bytes(out)
        (OUTPUT / (name + ".stderr")).write_bytes(err)
        row.update(stdout=pin(out), stderr=pin(err), elapsed_ns=time.monotonic_ns()-start)
        result["commands"].append(row)
        if row["timed_out"] or row["returncode"] != 0:
            raise RuntimeError(name + " did not complete successfully")
        return out

    try:
        for relative in INPUTS:
            data = (ROOT / relative).read_bytes()
            sources[relative] = data
            path = OUTPUT / "inputs" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            result["source_pins"][relative] = pin(data)
        source = OUTPUT / "inputs" / "source"
        binary = OUTPUT / "protocol_controls"
        argv = [str(compiler), "-std=c++17", "-Wall", "-Wextra", "-Werror", "-O2",
                "-pthread", "-I" + str(source), str(source / "role_authorization.cc"),
                str(source / "factory_context.cc"),
                str(OUTPUT / "inputs" / "controls" / "protocol_controls.cc"), "-o", str(binary)]
        run(argv, "compile", 60)
        result["binary"] = pin(binary.read_bytes())
        records = [json.loads(line) for line in run([str(binary)], "run", 15).splitlines()]
        if len(records) != 2:
            raise RuntimeError("expected held-caller record and single protocol summary")
        held, summary = records
        if (held.get("control") != "held_caller_exit" or
                held.get("owned_thread_joined") is not True or
                held.get("same_held_inode") is not True or
                held.get("numeric_tid_reuse_forced") is not False or
                summary.get("state") != "PASS_PROTOCOL_SCOPE" or
                summary.get("real_receive_cases") != 14 or
                summary.get("registry_authorization_positive_executed") is not False or
                summary.get("platform_filter_executed") is not False):
            raise RuntimeError("actual control contract differed")
        result["actual_control_records"] = records
        result["state"] = "PASS_PROTOCOL_SCOPE"
    except Exception as exception:
        error = {"type": type(exception).__name__, "message": str(exception)}
    finally:
        result["source_unchanged_after"] = all(
            (ROOT / relative).read_bytes() == data and
            (OUTPUT / "inputs" / relative).read_bytes() == data
            for relative, data in sources.items()) and len(sources) == len(INPUTS)
        result["tool_unchanged_after"] = compiler.read_bytes() == compiler_data
        if not result["source_unchanged_after"] or not result["tool_unchanged_after"]:
            error = {"type": "InputChange", "message": "exact source or compiler changed"}
        if error:
            result["state"] = "FAIL"
        result["error"] = error
        encoded = (json.dumps(result, sort_keys=True, indent=2) + "\n").encode()
        (OUTPUT / "result.json").write_bytes(encoded)
        print(json.dumps({"state": result["state"], "result": str(OUTPUT / "result.json"),
                          **pin(encoded), "error": error}))
    return 0 if result["state"] == "PASS_PROTOCOL_SCOPE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
