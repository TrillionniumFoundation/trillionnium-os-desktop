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

CAPTURE_PROFILE = "osdk-native-local-tcp-gdb-capture-v2"
UNIX_CAPTURE_PROFILE = "osdk-native-unix-gdb-capture-v3"
CAPTURE_PROFILES = (CAPTURE_PROFILE, UNIX_CAPTURE_PROFILE)
CAPTURE_SYMBOL = "ostd::arch::power::try_poweroff"
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
FATAL_PANICS = (
    "panicked at", "An uncaught panic occurred:", "Uncaught panic:",
    "unknown panic payload! (fatal panic handling error",
    "Non-resettable panic!", "The panic handler panicked",
    "Panicked in `PanicGuard`, aborting the system",
)


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
            if environment.get("A01_OSDK_PROFILE") == CAPTURE_PROFILE:
                actual.append("--gdb-server=wait-client,addr=127.0.0.1:0")
    return actual


def coverage_binding(case_directory, raw_path, profile_id, source_path=None):
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
        if profile_id in CAPTURE_PROFILES and any(
                marker in ANSI.sub("", data.decode(errors="replace")) for marker in FATAL_PANICS):
            raise ValueError("fatal guest panic in GDB coverage capture serial stream")
        announcements = re.findall(rb"^#### Coverage: (0x[0-9a-fA-F]+) (\d+)\r?$", data, re.MULTILINE)
        if len(announcements) != 1:
            raise ValueError("coverage requires exactly one guest announcement")
        address, size = announcements[0]
        length = int(size)
        if int(address, 16) == 0 or length <= 0:
            raise ValueError("coverage announcement has a null pointer or empty size")
        if not raw_path.is_file() or raw_path.stat().st_size != length:
            raise ValueError("raw coverage size differs from the guest announcement")
        raw_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        if profile_id in CAPTURE_PROFILES:
            capture = record.get("capture", {})
            if capture.get("raw_exit_code") != 0 or capture.get("timed_out") or capture.get("error"):
                raise ValueError("GDB capture process failed or timed out")
            sidecar = path.with_name("coverage-capture.json")
            sidecar_record = capture.get("sidecar", {})
            if not sidecar.is_file() or Path(sidecar_record.get("path", "")).resolve() != sidecar.resolve() \
                    or sidecar_record.get("size") != sidecar.stat().st_size \
                    or sidecar_record.get("sha256") != hashlib.sha256(sidecar.read_bytes()).hexdigest():
                raise ValueError("GDB capture sidecar is missing or does not match its recorded bytes")
            saved = json.loads(sidecar.read_text())
            if saved.get("profile_id") != profile_id or saved.get("passed") is not True \
                    or saved.get("finalized") is not True or saved.get("gdb_exit_code") != 0 \
                    or saved.get("timed_out") or saved.get("error"):
                raise ValueError("GDB capture sidecar did not finalize successfully")
            if saved.get("kernel_sha256") != kernel or saved.get("serial_sha256") != serial_hash \
                    or saved.get("guest_record") != str(path.relative_to(case_directory)):
                raise ValueError("GDB capture does not identify this exact guest and serial stream")
            if profile_id == UNIX_CAPTURE_PROFILE:
                endpoint = record.get("unix_gdb_endpoint", {})
                identity = endpoint.get("identity", {})
                endpoint_file = path.with_name("unix-gdb-endpoint.json")
                endpoint_bytes = endpoint_file.read_bytes()
                if record.get("raw_exit_code") != 33 or record.get("wrapper_exit_code") != 33:
                    raise ValueError("UNIX coverage requires the guest's actual ISA success exit33")
                if saved.get("transport") != "unix" or saved.get("unix_endpoint_identity") != identity \
                        or identity.get("qemu_pid") != record.get("qemu_pid") \
                        or identity.get("transport") != "unix" \
                        or not saved.get("unix_endpoint_verified_before_connect") \
                        or not saved.get("unix_endpoint_verified_after_connect") \
                        or not saved.get("unix_endpoint_verified_after_detach"):
                    raise ValueError("UNIX coverage endpoint is not bound to this actual guest")
                expected_endpoint = {"path": str(endpoint_file.resolve()), "size": len(endpoint_bytes),
                                     "sha256": hashlib.sha256(endpoint_bytes).hexdigest()}
                if endpoint.get("record") != expected_endpoint \
                        or saved.get("unix_endpoint_record") != expected_endpoint \
                        or json.loads(endpoint_bytes) != identity:
                    raise ValueError("UNIX endpoint identity receipt changed")
                if record.get("snapshot_verification") != {"before_qemu": True, "after_qemu": True}:
                    raise ValueError("UNIX coverage requires frozen input verification before/after QEMU")
                loaded = record["artifacts"]["-kernel"]
                loaded_path = Path(loaded["path"])
                loaded_bytes = loaded_path.read_bytes()
                argv = record.get("argv", [])
                if argv.count("-kernel") != 1 or argv[argv.index("-kernel") + 1] != str(loaded_path) \
                        or loaded_path.resolve() != loaded_path or loaded_path.is_symlink() \
                        or loaded_path.stat().st_mode & 0o222 \
                        or len(loaded_bytes) != loaded["size"] \
                        or hashlib.sha256(loaded_bytes).hexdigest() != kernel \
                        or loaded_bytes[:6] != b"\x7fELF\x02\x01" \
                        or int.from_bytes(loaded_bytes[18:20], "little") != 3:
                    raise ValueError("UNIX coverage loaded ELF bytes/argv do not match the frozen QEMU input")
                original = record.get("artifact_snapshots", {}).get("coverage-symbol", {})
                if any(original.get(key) != saved.get("symbol_elf", {}).get(key)
                       for key in ("path", "size", "sha256")):
                    raise ValueError("UNIX coverage symbols differ from this guest's private frozen symbols")
            point = saved.get("breakpoint", {})
            resolved = int(point.get("resolved_address", "0"), 16)
            actual_pc = int(point.get("actual_pc", "0"), 16)
            if point.get("symbol") != CAPTURE_SYMBOL or resolved <= 0 or actual_pc != resolved:
                raise ValueError("GDB did not stop at the resolved original poweroff instruction")
            expected_source = (source_path if source_path is not None else raw_path).resolve()
            saved_raw = saved.get("raw", {})
            if Path(saved_raw.get("path", "")).resolve() != expected_source \
                    or saved_raw.get("size") != length or saved_raw.get("sha256") != raw_hash \
                    or not expected_source.is_file() \
                    or hashlib.sha256(expected_source.read_bytes()).hexdigest() != raw_hash:
                raise ValueError("GDB raw dump path, size or bytes differ from the validated profile")
            announcement = saved.get("announcement", {})
            if int(announcement.get("address", "0"), 16) != int(address, 16) \
                    or announcement.get("size") != length:
                raise ValueError("GDB dump announcement differs from this guest's serial announcement")
            prefix = saved.get("serial_prefix", {})
            prefix_size = prefix.get("size", 0)
            if not isinstance(prefix_size, int) or not 0 < prefix_size <= len(data) \
                    or prefix.get("sha256") != hashlib.sha256(data[:prefix_size]).hexdigest() \
                    or re.findall(rb"^#### Coverage: (0x[0-9a-fA-F]+) (\d+)\r?$", data[:prefix_size], re.MULTILINE) != announcements:
                raise ValueError("GDB stopped-guest serial prefix differs from the final recorded stream")
            symbol_record = saved.get("symbol_elf", {})
            symbol_file = Path(symbol_record.get("path", ""))
            symbol_bytes = symbol_file.read_bytes()
            if len(symbol_bytes) < 20 or symbol_bytes[:6] != b"\x7fELF\x02\x01" \
                    or int.from_bytes(symbol_bytes[18:20], "little") != 62 \
                    or symbol_record.get("size") != len(symbol_bytes) \
                    or symbol_record.get("sha256") != hashlib.sha256(symbol_bytes).hexdigest():
                raise ValueError("GDB original ELF64 symbol artifact identity is invalid")
            validation.update({"capture_sidecar": str(sidecar.relative_to(case_directory)),
                               "capture_sidecar_sha256": sidecar_record["sha256"],
                               "symbol_elf_sha256": symbol_record["sha256"]})
        validation.update({"passed": True, "guest_record": str(path.relative_to(case_directory)),
                           "kernel_sha256": kernel, "serial_sha256": serial_hash,
                           "raw_sha256": raw_hash,
                           "announcement": {"address": address.decode(), "size": length}})
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
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
    command_env = os.environ.copy()
    capture_requested = os.environ.get("A01_OSDK_PROFILE") in CAPTURE_PROFILES \
        and len(args) >= 2 and args[:2] == ["osdk", "run"] and "--coverage" in args
    command_env["A01_OSDK_COVERAGE_GDB"] = "1" if capture_requested else "0"
    if capture_requested:
        command_env["A01_OSDK_COVERAGE_SYMBOL_ELF"] = str(
            Path(os.environ["CARGO_TARGET_DIR"]) / "x86_64-unknown-none/debug/basic_coverage-osdk-bin")
    result = subprocess.run(actual, env=command_env)
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
            if os.environ.get("A01_OSDK_LOCAL_TCP") == "1" or capture_requested:
                binding = coverage_binding(Path(os.environ["A01_OSDK_CASE_OUTPUT"]), raw,
                                           os.environ["A01_OSDK_PROFILE"], source_path=source)
                validation["guest_binding"] = binding
                validation["passed"] = validation["passed"] and binding["passed"] \
                    and not coverage_preexisted
        (coverage / "result.json").write_text(json.dumps(validation, indent=2) + "\n")
        report["coverage"] = validation
    destination.write_text(json.dumps(report, indent=2) + "\n")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
