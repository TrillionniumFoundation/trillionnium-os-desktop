#!/usr/bin/env python3
"""Actual kernel boot identity: two fresh boots and a missing-entropy refusal."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent


def single(negative, argv):
    spec = importlib.util.spec_from_file_location("safety_boot_id", HERE.parent / "safety/run.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    runner.PROBES = ("boot_id",)
    runner.SOURCE_FILES = {"boot_id": [HERE / "probe.c"]}
    runner.PROBE_ARGS = {"boot_id": " --expect-unavailable"} if negative else {}
    sys.argv = [str(__file__), *argv, *(["--cpu", "max,-rdrand"] if negative else [])]
    return runner.main()


def collect_profile(output, name, code):
    """Missing or malformed child evidence is a failed profile, never a pass."""
    entry = {"profile": name, "exit": code, "passed": False}
    try:
        directory = output / name
        result = json.loads((directory / "result.json").read_text())
        records = [json.loads(line) for line in (directory / "serial.log").read_text().splitlines()
                   if line.startswith('{')]
        source = json.loads((directory / "source-before.json").read_text())
        source_digest = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
        cpu = result["qemu_argv"][result["qemu_argv"].index("-cpu") + 1]
        expected_cpu = "max,-rdrand" if name == "no-secure-seed" else "max"
        entry.update(passed=code == 0 and result["passed"] and cpu == expected_cpu,
                     boot_ids=[record["boot_id"] for record in records if "boot_id" in record],
                     kernel_sha256=result["artifact_sha256"]["kernel.elf"],
                     source_sha256=source_digest, cpu=cpu,
                     serial_sha256=result["serial_sha256"],
                     source_unchanged=result["source_unchanged"],
                     artifacts_unchanged=result["artifacts_unchanged"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        entry["evidence_error"] = str(error)
    return entry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect-unavailable", action="store_true")
    parser.add_argument("--cross-boot", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args, rest = parser.parse_known_args()
    if not args.cross_boot:
        return single(args.expect_unavailable, ["--output", str(args.output), *rest])
    if args.expect_unavailable or rest:
        parser.error("cross-boot fixes all three profiles")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    results = []
    report = {"schema": "hepta.boot-id.v1", "passed": False, "profiles": results,
              "scope": "same-kernel fresh-boot identity and missing-entropy refusal, not full Root qualification"}
    for name in ("first", "second", "no-secure-seed"):
        report["stage"] = name
        (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        command = [sys.executable, "-I", "-B", str(__file__), "--output", str(output / name)]
        if name == "no-secure-seed":
            command.append("--expect-unavailable")
        with (output / f"{name}.log").open("w") as log:
            code = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT).returncode
        results.append(collect_profile(output, name, code))
    passed = (all(r["passed"] and r["source_unchanged"] and r["artifacts_unchanged"] for r in results)
              and all(len(r["boot_ids"]) == 1 for r in results[:2]) and not results[2]["boot_ids"]
              and results[0]["boot_ids"] != results[1]["boot_ids"]
              and len({r["source_sha256"] for r in results}) == 1
              and len({r["kernel_sha256"] for r in results}) == 1)
    report.update(passed=passed, stage="complete")
    (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
