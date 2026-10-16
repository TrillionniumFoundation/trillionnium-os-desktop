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


def adapt_command(args, environment, here):
    actual = [environment["A01_REAL_OSDK"], *args]
    actual = [re.sub(r"(^|,)addr=:(\d+)(?=,|$)", r"\1addr=127.0.0.1:\2", arg)
              for arg in actual]
    if len(args) >= 2 and args[0] == "osdk" and args[1] in ("build", "run", "test") \
            and not any(arg in ("-h", "--help") for arg in args):
        actual += ["--boot-method=vmm-direct", "--grub-boot-protocol=multiboot",
                   "--qemu-exe=" + str(here / "record-qemu.py")]
        if environment.get("A01_OSDK_LOCAL_TCP") == "1" and args[1] == "run" and "--coverage" in args:
            actual.append("--qemu-monitor-transport=tcp")
    return actual


def coverage_binding(case_directory, raw_path, profile_id):
    """Bind a fresh dump to the exact guest's announced bytes and artifacts."""
    validation = {"passed": False}
    try:
        records = list((case_directory / "guests").glob("guest-*/qemu.json"))
        if len(records) != 1:
            raise ValueError("coverage requires exactly one recorded guest")
        path = records[0]
        record = json.loads(path.read_text())
        if record.get("profile_id") != profile_id:
            raise ValueError("coverage guest profile differs from the requested profile")
        if record.get("timed_out") or record.get("error") or record.get("stream_errors"):
            raise ValueError("coverage guest timed out or recording failed")
        kernel = record.get("artifacts", {}).get("-kernel", {}).get("sha256", "")
        if not re.fullmatch(r"[0-9a-f]{64}", kernel):
            raise ValueError("coverage guest has no valid kernel artifact hash")
        serial = path.with_name("serial.log")
        data = serial.read_bytes()
        serial_hash = hashlib.sha256(data).hexdigest()
        serial_records = record.get("serial_logs", [])
        if not data or len(serial_records) != 1 \
                or serial_records[0].get("sha256") != serial_hash \
                or serial_records[0].get("size") != len(data):
            raise ValueError("coverage serial bytes do not match the guest record")
        announcements = re.findall(rb"^#### Coverage: (0x[0-9a-fA-F]+) (\d+)\r?$", data, re.MULTILINE)
        if len(announcements) != 1:
            raise ValueError("coverage requires exactly one guest announcement")
        address, size = announcements[0]
        length = int(size)
        if int(address, 16) == 0 or length <= 0:
            raise ValueError("coverage announcement has a null pointer or empty size")
        if not raw_path.is_file() or raw_path.stat().st_size != length:
            raise ValueError("raw coverage size differs from the guest announcement")
        validation.update({"passed": True, "guest_record": str(path.relative_to(case_directory)),
                           "kernel_sha256": kernel, "serial_sha256": serial_hash,
                           "raw_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                           "announcement": {"address": address.decode(), "size": length}})
    except (OSError, ValueError, TypeError, KeyError) as error:
        validation["error"] = str(error)
    return validation


def main():
    args = sys.argv[1:]
    actual = adapt_command(args, os.environ, Path(__file__).resolve().parent)
    directory = Path(os.environ["A01_OSDK_CASE_OUTPUT"]) / "osdk"
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, path = tempfile.mkstemp(prefix="request-", suffix=".json", dir=directory)
    os.close(descriptor)
    report = {"cwd": os.getcwd(), "requested_argv": args, "actual_argv": actual,
              "profile_id": os.environ.get("A01_OSDK_PROFILE", "osdk-native-unix-v1"),
              "raw_exit_code": None}
    destination = Path(path)
    destination.write_text(json.dumps(report, indent=2) + "\n")
    source = Path.cwd() / "coverage.profraw"
    coverage_preexisted = "--coverage" in args and source.exists()
    result = subprocess.run(actual)
    report["raw_exit_code"] = result.returncode
    if "--coverage" in args:
        coverage = Path(os.environ["A01_OSDK_CASE_OUTPUT"]) / "coverage"
        coverage.mkdir(exist_ok=False)
        validation = {"passed": False, "source": str(source),
                      "source_preexisted": coverage_preexisted,
                      "source_osdk_exit_code": result.returncode}
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
                and result.returncode == 0 \
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
            if os.environ.get("A01_OSDK_LOCAL_TCP") == "1":
                binding = coverage_binding(Path(os.environ["A01_OSDK_CASE_OUTPUT"]), raw,
                                           os.environ["A01_OSDK_PROFILE"])
                validation["guest_binding"] = binding
                validation["passed"] = validation["passed"] and binding["passed"] \
                    and not coverage_preexisted
        (coverage / "result.json").write_text(json.dumps(validation, indent=2) + "\n")
        report["coverage"] = validation
    destination.write_text(json.dumps(report, indent=2) + "\n")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
