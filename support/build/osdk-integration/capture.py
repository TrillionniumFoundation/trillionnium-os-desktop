#!/usr/bin/env python3
"""Capture the live coverage bytes before the original ISA poweroff executes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time

PROFILE = "osdk-native-local-tcp-gdb-capture-v2"
SYMBOL = "ostd::arch::power::try_poweroff"


def file_record(path):
    path = Path(path).resolve()
    return {"path": str(path), "size": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def verify_symbol_elf(path):
    header = path.read_bytes()[:20]
    if len(header) != 20 or header[:6] != b"\x7fELF\x02\x01" or struct.unpack("<H", header[18:20])[0] != 62:
        raise ValueError("coverage symbols must be the original ELF64 little-endian EM_X86_64 artifact")


def resolved_address(text):
    addresses = set()
    for line in text.splitlines():
        fields = line.split(None, 2)
        if len(fields) == 3 and fields[2] == SYMBOL and re.fullmatch(r"[0-9a-fA-F]+", fields[0]):
            addresses.add(int(fields[0], 16))
    if len(addresses) != 1 or not next(iter(addresses), 0):
        raise ValueError("nm must resolve one nonzero exact poweroff symbol address")
    return next(iter(addresses))


def gdb_script(settings):
    payload = repr(json.dumps(settings))
    return '''set pagination off
set confirm off
set tcp auto-retry on
set tcp connect-timeout 15
set remotetimeout 10
set architecture i386:x86-64
python
import gdb, json, os, re, time
settings = json.loads(''' + payload + ''')
result = {"passed": False, "breakpoint": {"symbol": settings["symbol"], "resolved_address": settings["address"]}}
def persist():
    with open(settings["observations"], "w") as output:
        json.dump(result, output, indent=2)
        output.write("\\n")
persist()
try:
    gdb.execute("target remote " + settings["endpoint"])
    breakpoint = gdb.Breakpoint("*" + settings["address"], type=gdb.BP_HARDWARE_BREAKPOINT, internal=True)
    gdb.execute("continue")
    pc = int(gdb.parse_and_eval("$pc"))
    result["breakpoint"]["actual_pc"] = hex(pc)
    if pc != int(settings["address"], 16):
        raise gdb.GdbError("guest stopped at an unexpected instruction pointer")
    deadline = time.monotonic() + 5
    while True:
        try:
            with open(settings["serial"], "rb") as source:
                serial = source.read()
        except FileNotFoundError:
            serial = b""
        announcements = re.findall(rb"^#### Coverage: (0x[0-9a-fA-F]+) (\\d+)\\r?$", serial, re.MULTILINE)
        if len(announcements) == 1:
            break
        if len(announcements) > 1 or time.monotonic() >= deadline:
            raise gdb.GdbError("expected one complete live coverage announcement")
        time.sleep(.02)
    address, length = announcements[0]
    address, length = int(address, 16), int(length)
    if address == 0 or not 0 < length <= 512 * 1024 * 1024:
        raise gdb.GdbError("coverage pointer or size is invalid")
    result["announcement"] = {"address": hex(address), "size": length}
    if os.path.lexists(settings["raw"]):
        raise gdb.GdbError("refusing to overwrite an existing coverage profile")
    command = "monitor memsave 0x%x %d %s" % (address, length, json.dumps(settings["raw"]))
    result["memsave_command"] = command
    gdb.execute(command)
    deadline = time.monotonic() + 5
    while not os.path.isfile(settings["raw"]) or os.path.getsize(settings["raw"]) != length:
        if time.monotonic() >= deadline:
            raise gdb.GdbError("monitor dump did not produce the announced number of bytes")
        time.sleep(.02)
    with open(settings["prefix"], "wb") as prefix:
        prefix.write(serial)
    breakpoint.enabled = False
    breakpoint.delete()
    gdb.execute("detach")
    result["resumed_by_detach"] = True
    result["passed"] = True
    persist()
except Exception as error:
    result["error"] = str(error)
    persist()
    raise gdb.GdbError(str(error))
end
quit
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--symbol-elf", type=Path, required=True)
    parser.add_argument("--serial-log", type=Path, required=True)
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--sidecar", type=Path, required=True)
    parser.add_argument("--kernel-sha256", required=True)
    parser.add_argument("--guest-record", required=True)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    sidecar = args.sidecar.resolve()
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    record = {"schema": 1, "profile_id": PROFILE, "passed": False, "finalized": False,
              "endpoint": args.endpoint, "kernel_sha256": args.kernel_sha256,
              "guest_record": args.guest_record, "gdb_exit_code": None, "timed_out": False}
    started = time.monotonic()
    try:
        if not re.fullmatch(r"127\.0\.0\.1:([1-9][0-9]{0,4})", args.endpoint) \
                or int(args.endpoint.rsplit(":", 1)[1]) > 65535:
            raise ValueError("GDB capture requires an explicit allocated IPv4 loopback endpoint")
        if args.timeout <= 0 or not re.fullmatch(r"[0-9a-f]{64}", args.kernel_sha256):
            raise ValueError("invalid capture timeout or kernel digest")
        symbol = args.symbol_elf.resolve()
        raw = args.raw_output.resolve()
        if os.path.lexists(raw):
            raise ValueError("refusing to overwrite an existing raw coverage profile")
        verify_symbol_elf(symbol)
        record["symbol_elf"] = file_record(symbol)
        nm = shutil.which("nm")
        gdb = shutil.which("gdb")
        if not nm or not gdb:
            raise FileNotFoundError("native nm and GDB are required")
        nm_command = [nm, "-n", "-C", str(symbol)]
        with sidecar.with_name("capture-nm.log").open("wb") as output:
            checked = subprocess.run(nm_command, stdout=output, stderr=subprocess.STDOUT, timeout=30)
        record["nm_command"] = {"argv": nm_command, "raw_exit_code": checked.returncode}
        if checked.returncode:
            raise ValueError("nm failed to inspect the original symbol ELF")
        address = resolved_address(sidecar.with_name("capture-nm.log").read_text())
        observations = sidecar.with_name("capture-gdb-observations.json")
        prefix = sidecar.with_name("capture-serial-prefix.log")
        settings = {"endpoint": args.endpoint, "symbol": SYMBOL, "address": hex(address),
                    "serial": str(args.serial_log.resolve()), "raw": str(raw),
                    "observations": str(observations), "prefix": str(prefix)}
        script = sidecar.with_name("capture.gdb")
        script.write_text(gdb_script(settings))
        command = [gdb, "--batch", "-nx", "--quiet", "--se=" + str(symbol), "-x", str(script)]
        record["gdb_command"] = command
        record["gdb"] = file_record(Path(gdb))
        record["gdb_version"] = subprocess.check_output([gdb, "--version"], text=True, timeout=10)
        sidecar.write_text(json.dumps(record, indent=2) + "\n")
        with sidecar.with_name("capture-gdb.log").open("wb") as output:
            try:
                result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=args.timeout)
                record["gdb_exit_code"] = result.returncode
            except subprocess.TimeoutExpired:
                record["timed_out"] = True
                raise ValueError("GDB coverage capture timed out")
        if observations.is_file():
            observed = json.loads(observations.read_text())
            record.update(observed)
        if record["gdb_exit_code"] != 0 or not record.get("passed") \
                or record.get("timed_out") or not record.get("resumed_by_detach"):
            raise ValueError("GDB did not complete breakpoint, dump and detach")
        if file_record(symbol) != record["symbol_elf"]:
            raise ValueError("symbol ELF changed during capture")
        record["raw"] = file_record(raw)
        saved_prefix = prefix.read_bytes()
        record["serial_prefix"] = {"size": len(saved_prefix),
                                   "sha256": hashlib.sha256(saved_prefix).hexdigest()}
        if record["raw"]["size"] != record["announcement"]["size"]:
            raise ValueError("captured profile size differs from the guest announcement")
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        record["passed"] = False
        record["error"] = f"{type(error).__name__}: {error}"
    record["duration_seconds"] = round(time.monotonic() - started, 3)
    sidecar.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"passed": record["passed"], "sidecar": str(sidecar),
                      "gdb_exit_code": record["gdb_exit_code"]}))
    return int(not record["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
