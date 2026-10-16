#!/usr/bin/env python3
"""Adapt only the OSDK integration test's boot profile to native TCG."""
import json
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def main():
    args = sys.argv[1:]
    actual = [os.environ["A01_REAL_OSDK"], *args]
    actual = [re.sub(r"(^|,)addr=:(\d+)(?=,|$)", r"\1addr=127.0.0.1:\2", arg)
              for arg in actual]
    if len(args) >= 2 and args[0] == "osdk" and args[1] in ("build", "run", "test") \
            and not any(arg in ("-h", "--help") for arg in args):
        actual += ["--boot-method=vmm-direct", "--grub-boot-protocol=multiboot",
                   "--qemu-exe=" + str(Path(__file__).with_name("record-qemu.py"))]
    directory = Path(os.environ["A01_OSDK_CASE_OUTPUT"]) / "osdk"
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, path = tempfile.mkstemp(prefix="request-", suffix=".json", dir=directory)
    os.close(descriptor)
    report = {"cwd": os.getcwd(), "requested_argv": args, "actual_argv": actual,
              "raw_exit_code": None}
    destination = Path(path)
    destination.write_text(json.dumps(report, indent=2) + "\n")
    result = subprocess.run(actual)
    report["raw_exit_code"] = result.returncode
    if "--coverage" in args:
        coverage = Path(os.environ["A01_OSDK_CASE_OUTPUT"]) / "coverage"
        coverage.mkdir(exist_ok=False)
        source = Path.cwd() / "coverage.profraw"
        validation = {"passed": False, "source": str(source)}
        if source.is_file():
            raw = coverage / "coverage.profraw"
            shutil.copyfile(source, raw)
            validation.update({"size": raw.stat().st_size,
                               "sha256": hashlib.sha256(raw.read_bytes()).hexdigest()})
            toolchain = Path(os.environ["A01_REAL_CARGO"]).parent.parent
            llvm = toolchain / "lib/rustlib/x86_64-unknown-linux-gnu/bin/llvm-profdata"
            validation["llvm_profdata"] = str(llvm)
            steps = [[str(llvm), "merge", "--sparse", str(raw), "-o", str(coverage / "coverage.profdata")],
                     [str(llvm), "show", "--all-functions", "--counts", str(coverage / "coverage.profdata")]]
            validation["commands"] = []
            for index, step in enumerate(steps):
                with (coverage / f"llvm-profdata-{index}.log").open("wb") as output:
                    checked = subprocess.run(step, stdout=output, stderr=subprocess.STDOUT, timeout=30)
                validation["commands"].append({"argv": step, "raw_exit_code": checked.returncode})
                if checked.returncode:
                    break
            validation["passed"] = raw.stat().st_size > 0 \
                and len(validation["commands"]) == 2 \
                and all(step["raw_exit_code"] == 0 for step in validation["commands"])
            summary = coverage / "llvm-profdata-1.log"
            text = summary.read_text() if summary.is_file() else ""
            for key, label in (("total_functions", "Total functions"),
                               ("maximum_function_count", "Maximum function count")):
                matched = re.search(label + r":\s*(\d+)", text)
                validation[key] = int(matched.group(1)) if matched else 0
            validation["passed"] = validation["passed"] \
                and validation["total_functions"] > 0 and validation["maximum_function_count"] > 0
        (coverage / "result.json").write_text(json.dumps(validation, indent=2) + "\n")
        report["coverage"] = validation
    destination.write_text(json.dumps(report, indent=2) + "\n")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
