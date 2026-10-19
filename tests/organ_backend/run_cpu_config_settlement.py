#!/usr/bin/env python3
"""Compare ordinary cpu.max reads and same-value writes in a disposable QEMU.

The 100 ms case uses a predeclared 1.2% CPU bound over four seconds. The
ordinary 2 ms case uses 52%, to expose cross-window accounting separately.
Both bounds include startup and 1 ms rusage quantization. A complete boot
with insufficient unlimited CPU use is inconclusive, never a timing pass.
No host network, data disks, cgroup files, or external system are used.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
from run_guest_probe import BIOS_SHA, INITRD_SHA, pack, unpack

MAX_SERIAL_BYTES = 8 * 1024 * 1024
BOOT_MARKER = "TRILLIONNIUM_A01_BOOT_OK"
SAMPLE = re.compile(
    r"CPU_CONFIG_SAMPLE label=(unlimited|read-only|same-value) "
    r"wall_ns=([0-9]{1,20}) cpu_ns=([0-9]{1,20}) operations=([0-9]{1,20}) "
    r"checksum=([0-9]{1,20})"
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def evaluate_serial(raw, code, timed_out, period_us, mode):
    """Accept one ordered guest execution, including the shell-observed exit."""
    if period_us not in (2000, 100000) or mode not in ("read-only", "same-value"):
        raise ValueError("unsupported declared case")
    bound = 1.2 if period_us == 100000 else 52.0
    clean = re.sub(r"\x1b\[[0-9;]*m", "", raw.decode(errors="replace"))
    parameters = f"CPU_CONFIG_PARAMETERS quota_us=1000 period_us={period_us} mode={mode} seconds=4"
    exact = {parameters: "parameters", "CPU_CONFIG_STAT": "stat",
             "CPU_CONFIG_COMPLETE": "complete", "CPU_CONFIG_PROCESS_EXIT status=0": "exit0",
             BOOT_MARKER: "boot"}
    events, samples, malformed = [], [], []
    for line in clean.splitlines():
        match = SAMPLE.fullmatch(line)
        if match:
            label, wall, cpu, operations, checksum = match.groups()
            wall, cpu, operations, checksum = map(int, (wall, cpu, operations, checksum))
            samples.append({"label": label, "wall_ns": wall, "cpu_ns": cpu,
                            "operations": operations, "checksum": checksum,
                            "cpu_percent": 100 * cpu / wall if wall else None})
            events.append("sample:" + label)
        elif line in exact:
            events.append(exact[line])
        elif "CPU_CONFIG_" in line or BOOT_MARKER in line:
            malformed.append(line)
    ordered = events == ["sample:unlimited", "parameters", "sample:" + mode,
                         "stat", "complete", "exit0", "boot"] and not malformed
    measurements_valid = ordered and all(
        0 < sample[key] < 2**64 for sample in samples for key in ("wall_ns", "cpu_ns", "operations")
    ) and all(sample["checksum"] < 2**64 for sample in samples)
    if measurements_valid:
        measurements_valid = samples[0]["wall_ns"] >= 250_000_000 and samples[1]["wall_ns"] >= 4_000_000_000
    no_failure = not any(text in clean for text in ("CPU_CONFIG_BLOCKED", "panicked at", "Kernel panic", "[PANIC]"))
    complete = (type(code) is int and code == 33 and timed_out is False and len(raw) <= MAX_SERIAL_BYTES
                and ordered and measurements_valid and no_failure)
    timing_valid = complete and samples[0]["cpu_percent"] >= 70.0
    return {"samples": samples, "events": events, "malformed_marker_lines": malformed,
            "ordered_exact_markers": ordered, "measurements_valid": measurements_valid,
            "probe_process_exit": 0 if ordered else None, "guest_complete": complete,
            "timing_valid": timing_valid, "passed": timing_valid and samples[1]["cpu_percent"] <= bound}


def verify_input_records(records):
    """Check every recorded input again, retaining missing/mutated input details."""
    changed = {}
    for name, record in records.items():
        try:
            data = Path(record["path"]).read_bytes()
            actual = {"sha256": sha(data), "size": len(data)}
            if actual != {key: record[key] for key in ("sha256", "size")}:
                changed[name] = actual
        except OSError as error:
            changed[name] = {"error": str(error)}
    return {"inputs_unchanged": not changed, "changed_inputs": changed}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kernel", type=Path, required=True)
    ap.add_argument("--expected-sha256", required=True)
    ap.add_argument("--initramfs", type=Path, required=True)
    ap.add_argument("--bios", type=Path, required=True)
    ap.add_argument("--qemu", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--period-us", type=int, choices=(2000, 100000), required=True)
    ap.add_argument("--mode", choices=("read-only", "same-value"), required=True)
    args = ap.parse_args()
    if not re.fullmatch(r"[0-9a-f]{64}", args.expected_sha256):
        ap.error("expected SHA-256 must be 64 lowercase hex digits")
    runner_path = Path(__file__)
    helper_path = runner_path.with_name("run_guest_probe.py")
    runner_bytes, helper_bytes = runner_path.read_bytes(), helper_path.read_bytes()
    kernel = args.kernel.read_bytes()
    original = args.initramfs.read_bytes()
    bios = args.bios.read_bytes()
    qemu_path = args.qemu.resolve(strict=True)
    qemu = qemu_path.read_bytes()
    if not qemu.startswith(b"\x7fELF"):
        raise ValueError("QEMU must be the actual ELF executable, not a wrapper")
    qemu_version = subprocess.check_output([str(qemu_path), "--version"], text=True, timeout=10).strip()
    if not qemu_version.startswith("QEMU emulator version "):
        raise ValueError("QEMU executable did not identify itself")
    if sha(kernel) != args.expected_sha256 or sha(original) != INITRD_SHA or sha(bios) != BIOS_SHA:
        raise ValueError("pinned kernel/initramfs/BIOS input mismatch")
    source_path = Path(__file__).with_name("cpu_config_settlement_probe.c")
    original_source_bytes = source_path.read_bytes()
    original_source = original_source_bytes.decode()
    if original_source.count("__KERNEL_SHA__") != 1:
        raise ValueError("missing or duplicate guest identity placeholder")
    source = original_source.replace("__KERNEL_SHA__", args.expected_sha256)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / "probe.c").write_text(source)
    binary = out / "probe"
    compiler = shutil.which("cc")
    if compiler is None:
        raise ValueError("static C compiler is missing")
    compiler_path = Path(compiler).resolve(strict=True)
    compiler_bytes = compiler_path.read_bytes()
    compile_argv = [str(compiler_path), "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-static",
                    str(out / "probe.c"), "-o", str(binary)]
    compiled = subprocess.run(compile_argv, capture_output=True, text=True, timeout=60)
    (out / "compile.log").write_text(compiled.stdout + compiled.stderr)
    if compiled.returncode:
        raise RuntimeError("probe compile failed; inspect compile.log")
    probe = binary.read_bytes()
    entries = unpack(gzip.decompress(original))
    marker = b'echo "TRILLIONNIUM_A01_BOOT_OK"'
    # `if` preserves the real child status even though the fixed init uses -e.
    # Only a zero child exit may proceed to the original boot completion.
    invocation = (f"if /bin/cpu-config-settlement --asterinas-disposable-guest {args.period_us} {args.mode} 4; then\n"
                  '  echo "CPU_CONFIG_PROCESS_EXIT status=0"\n'
                  'else\n  probe_status=$?\n'
                  '  echo "CPU_CONFIG_PROCESS_EXIT status=$probe_status"\n'
                  '  exit "$probe_status"\nfi\n').encode()
    injected = []
    changed = 0
    for name, fields, content in entries:
        if name.lstrip("./") == "init":
            if content.count(marker) != 1:
                raise ValueError("unexpected init completion marker")
            content = content.replace(marker, invocation + marker)
            changed += 1
        injected.append((name, fields, content))
    if changed != 1:
        raise ValueError("missing init script")
    inode = max(row[1][0] for row in entries)
    for offset, name, mode, data in [
        (1, "bin/cpu-config-settlement", 0o100755, probe),
        (2, ".hepta-disposable-guest", 0o100400, (args.expected_sha256 + "\n").encode()),
    ]:
        injected.append((name, [inode + offset, mode, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0], data))
    archive = out / "initramfs.cpio.gz"
    archive_bytes = gzip.compress(pack(injected), mtime=0)
    archive.write_bytes(archive_bytes)
    argv = [str(qemu_path), "-kernel", str(args.kernel.resolve()), "-initrd", str(archive),
            "-append", "earlycon console=ttyS0 loglevel=info SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --",
            "-machine", "q35", "-accel", "tcg", "-cpu", "max", "-bios", str(args.bios.resolve()),
            "-m", "512M", "-smp", "1", "-nodefaults", "-no-user-config", "-no-reboot", "-nographic",
            "-display", "none", "-monitor", "none", "-serial", "stdio", "-nic", "none",
            "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"]
    bound = 1.2 if args.period_us == 100000 else 52.0
    paths = {"kernel": args.kernel, "original_initramfs": args.initramfs, "bios": args.bios,
             "qemu": qemu_path, "compiler": compiler_path, "probe_source": source_path,
             "runner": runner_path, "archive_helper": helper_path,
             "compiled_source": out / "probe.c", "probe": binary, "injected_initramfs": archive}
    expected = {"kernel": kernel, "original_initramfs": original, "bios": bios, "qemu": qemu,
                "compiler": compiler_bytes, "probe_source": original_source_bytes,
                "runner": runner_bytes, "archive_helper": helper_bytes,
                "compiled_source": source.encode(), "probe": probe, "injected_initramfs": archive_bytes}
    records = {}
    for name, path in paths.items():
        path = path.resolve(strict=True)
        data = path.read_bytes()
        if name in expected and data != expected[name]:
            raise ValueError(f"input changed before guest: {name}")
        records[name] = {"path": str(path), "size": len(data), "sha256": sha(data)}
    inputs = {"schema": "a06.cpu-config-settlement.v2", "kernel_sha256": sha(kernel),
              "original_initramfs_sha256": sha(original), "bios_sha256": sha(bios),
              "probe_source_sha256": sha(original_source_bytes), "input_files": records,
              "compiled_source_sha256": sha(source.encode()), "probe_sha256": sha(probe),
              "initramfs_sha256": sha(archive_bytes), "argv": argv,
              "qemu_sha256": sha(qemu), "qemu_version": qemu_version, "compiler_argv": compile_argv,
              "period_us": args.period_us, "quota_us": 1000, "mode": args.mode,
              "duration_seconds": 4, "max_cpu_percent": bound,
              "minimum_unlimited_percent": 70.0, "max_serial_bytes": MAX_SERIAL_BYTES, "single_vcpu": True,
              "network": False, "data_disks": False, "hos2_qualification": False}
    # Write the inputs and numerical acceptance criteria before booting.
    input_receipt = (json.dumps(inputs, indent=2) + "\n").encode()
    (out / "inputs.json").write_bytes(input_receipt)
    receipt_record = {"path": str(out / "inputs.json"), "size": len(input_receipt), "sha256": sha(input_receipt)}
    timed_out = False
    try:
        run = subprocess.run(argv, capture_output=True, timeout=45)
        raw, code = run.stdout + run.stderr, run.returncode
    except subprocess.TimeoutExpired as exc:
        raw, code = (exc.stdout or b"") + (exc.stderr or b""), None
        timed_out = True
    (out / "serial.log").write_bytes(raw)
    report = {"inputs": inputs, "qemu_exit": code, "timed_out": timed_out,
              "input_receipt": receipt_record, "serial_sha256": sha(raw), "serial_bytes": len(raw)}
    report.update(evaluate_serial(raw, code, timed_out, args.period_us, args.mode))
    report.update(verify_input_records({**records, "input_receipt": receipt_record}))
    report["passed"] = report["passed"] and report["inputs_unchanged"]
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "inputs"}, indent=2))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
