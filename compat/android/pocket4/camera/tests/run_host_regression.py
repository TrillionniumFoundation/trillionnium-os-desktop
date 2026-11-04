#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compile the complete reviewed manager with test-only bindings and a negative control."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = [
    "healthy characteristics and selected facing",
    "enumerated device disappears before characteristics",
    "enumeration race preserves remaining connected device",
    "cached device removal selects replacement",
    "camera service checked failure retains cause",
    "unrelated runtime failure is not swallowed",
    "missing lens facing skipped",
    "null device list is unavailable",
    "null ID entry skipped",
    "null selected device becomes checked failure",
    "null characteristics becomes checked failure",
    "availability event invalidates same ID facing cache",
    "cached ID list failure reports unavailable",
    "external camera fallback retained",
    "callback registration and teardown retained",
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--javac", default="javac")
    parser.add_argument("--java", default="java")
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    lock = json.loads((ROOT / "source-lock.json").read_text())
    sources = {
        "candidate": lock["reviewed_source"],
        "negative_control": lock["negative_control"],
    }
    for record in sources.values():
        if sha(ROOT / record["path"]) != record["sha256"]:
            raise SystemExit("Manager source does not match source-lock.json")
    bindings = []
    for path, expected in sorted(lock["host_test_bindings"].items()):
        file = ROOT / path
        if sha(file) != expected:
            raise SystemExit("Test binding does not match source-lock.json: " + path)
        bindings.append(str(file))

    result = {
        "schema": "pocket4-camera-host-regression-v1",
        "scope": "Host Java logic only; bindings are not Android runtime code.",
        "production_ready": False,
        "cases_expected": len(EXPECTED),
        "results": {},
    }
    with tempfile.TemporaryDirectory(prefix="p4-camera-regression-") as temp:
        for label, record in sources.items():
            out = Path(temp) / label
            out.mkdir()
            compile_run = subprocess.run(
                [args.javac, "-J-XX:ActiveProcessorCount=2", "-J-Xmx256m",
                 "-encoding", "UTF-8", "-source", "8", "-target", "8",
                 "-d", str(out), *bindings, str(ROOT / record["path"])],
                capture_output=True, text=True, timeout=60)
            row = {"source_sha256": record["sha256"], "compile_exit": compile_run.returncode}
            if compile_run.returncode == 0:
                test = subprocess.run(
                    [args.java, "-XX:ActiveProcessorCount=2", "-Xmx256m",
                     "-cp", str(out), "HotplugRegression"],
                    capture_output=True, text=True, timeout=30)
                passed = [line[5:] for line in test.stdout.splitlines() if line.startswith("PASS ")]
                row.update(test_exit=test.returncode, passed_cases=passed)
                if label == "candidate":
                    row["verified"] = (test.returncode == 0 and passed == EXPECTED
                                       and "TOTAL_PASS=15" in test.stdout.splitlines()
                                       and not test.stderr)
                else:
                    row["expected_failure_observed"] = (
                        test.returncode == 1
                        and passed == EXPECTED[:1]
                        and "java.lang.IllegalArgumentException: unknown device gone" in test.stderr)
                    row["verified"] = row["expected_failure_observed"]
            else:
                row["verified"] = False
                row["compile_error"] = compile_run.stderr.replace(str(ROOT), "<camera-source>")[-4000:]
            result["results"][label] = row
    result["success"] = all(row["verified"] for row in result["results"].values())
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output_json:
        args.output_json.write_text(rendered)
    print(rendered, end="")
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
