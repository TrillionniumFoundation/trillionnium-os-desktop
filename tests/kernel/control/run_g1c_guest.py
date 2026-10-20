#!/usr/bin/env python3
"""Build the opt-in G1-c kernel and boot its actual trusted initial image.

Keep the ordinary QueryAbi product gate separate. Three boots use one frozen
kernel: the exact initial ELF, a byte-modified initramfs, and a truncated input.
Only the real initial Process may observe its original CPU owner. This profile
does not qualify native management/history, Hepta durability, SMP or hardware.
"""
import argparse
import gzip
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import struct
import subprocess
import sys
import time
import tomllib

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_queryabi_candidate_guest as ordinary
import run_queryabi_guest as replay

ROOT = Path(__file__).resolve().parents[3]
require = replay.require
digest = replay.digest
save_json = ordinary.save_json
CAP_NS = 50_000_000
PERIOD_NS = 100_000_000
LEASE_NS = 300_000_000_000
ACTIVATED = ("[hepta-g1c] initial observe activated: slot=1 generation=1 "
             "cap_ns=50000000 period_ns=100000000 lease_ns=300000000000")
COMMITTED = re.compile(r"^\[hepta-g1c\] trusted initial image committed: bytes=([0-9]+) entry=0x([0-9a-f]+)$")
COMPLETE = "G1C_COMPLETE initial_manifest=exact observe=real_owner manage=disabled exec_grant=revoked"
MARKERS = (
    "G1C_INIT_STARTED pid=1",
    "G1C_BOOT_PAGE_OK version=1 slot=1 generation=1",
    "G1C_QUERYABI_OK supported_ops=6 max_request=0 max_response=64 features=0",
    "G1C_READ_USAGE_OK", "G1C_WRONG_SLOT_DENIED", "G1C_WRONG_GENERATION_DENIED",
    "G1C_DISABLED_OPERATIONS_OK count=3", "G1C_INVALID_TRANSPORT_DENIED",
    "G1C_MAPPINGS_SEALED cases=9", "G1C_SELF_MEM_WRITE_DENIED", "G1C_THREAD_SHARE_OK",
    "G1C_DUP_SESSION_OK", "G1C_FORK_FD_DENIED", "G1C_FORK_CAPSPACE_DISTINCT",
    "G1C_FORGED_BOOT_PAGE_DENIED", "G1C_SCM_FD_DENIED", "G1C_TRANSFERRED_MEM_WRITE_DENIED",
    "G1C_ALIEN_MEM_OPEN_DENIED", "G1C_NONROOT_OPEN_DENIED", "G1C_FORK_CHILD_OK",
    "G1C_FORK_PARENT_AUTHORITY_STABLE", "G1C_FAILED_EXEC_GRANT_STABLE", "G1C_PRE_EXEC_USAGE_OK",
    "G1C_EXEC_OLD_FD_DENIED", "G1C_EXEC_CAPSPACE_ROTATED", "G1C_EXEC_AUXV_ABSENT",
    "G1C_EXEC_NO_GRANT_OK", COMPLETE,
)
SEAL_CASES = (
    "boot_add_write", "code_add_write", "boot_add_exec", "new_exec_mapping",
    "boot_fixed_replace", "boot_unmap", "boot_discard", "remap_alias", "cross_process_clone_vm",
)
USAGE_LABELS = (
    "initial", "thread", "after_thread", "dup", "after_fork", "before_work",
    "before_stat", "after_stat", "same_linux_budget", "changed_linux_budget",
    "restored_linux_budget", "after_failed_exec", "pre_exec",
)
USAGE = re.compile(
    r"^G1C_USAGE label=([a-z_]+) sample=([0-9]+) cumulative=([0-9]+) "
    r"window_start=([0-9]+) window_consumed=([0-9]+) cap=([0-9]+) period=([0-9]+) "
    r"events=([0-9]+) dropped=([0-9]+) revision=([0-9]+)$"
)
OWNER = re.compile(r"^G1C_REAL_CPU_OWNER_MATCH same_revision=([0-9]+) changed_revision=([0-9]+) restored_revision=([0-9]+)$")
STAT = re.compile(r"^G1C_CPU_STAT_OBSERVATION usage_usec=([0-9]+) before_ns=([0-9]+) after_ns=([0-9]+)$")


def inspect_probe_elf(data):
    """Independent static-profile check; kernel still owns runtime validation."""
    require(64 <= len(data) <= 8 * 1024 * 1024, "static initial ELF size out of bounds")
    require(data[:7] == b"\x7fELF\x02\x01\x01" and data[16:20] == b"\x02\x00\x3e\x00",
            "initial probe is not little-endian x86_64 ET_EXEC")
    entry, phoff = struct.unpack_from("<QQ", data, 24)
    phsize, phcount = struct.unpack_from("<HH", data, 54)
    require(phsize == 56 and 1 <= phcount <= 64 and phoff + phsize * phcount <= len(data),
            "invalid bounded ELF program-header table")
    loads = []
    for index in range(phcount):
        kind, flags, offset, address, _, filesz, memsz, align = struct.unpack_from("<IIQQQQQQ", data, phoff + index * phsize)
        require(kind != 3, "initial probe must not contain PT_INTERP")
        if kind == 0x6474E551:
            require(flags & 1 == 0, "initial probe requests an executable stack")
        if kind != 1:
            continue
        require(filesz <= memsz and offset + filesz <= len(data) and memsz > 0,
                "invalid LOAD file/memory bounds")
        require(address >= 4096 and address + memsz <= (1 << 47) and flags & 4 and flags & 3 != 3,
                "invalid LOAD permissions/address")
        require(offset % 4096 == address % 4096 and align >= 4096 and align & (align - 1) == 0,
                "invalid LOAD alignment")
        start, end = address // 4096 * 4096, (address + memsz + 4095) // 4096 * 4096
        require(not any(start < old["end"] and old["start"] < end for old in loads),
                "initial LOAD pages overlap")
        loads.append({"start": start, "end": end, "file_end": offset + filesz,
                      "entry_inside": bool(flags & 1 and address <= entry < address + memsz)})
    require(1 <= len(loads) <= 16 and any(item["entry_inside"] for item in loads),
            "initial entry is not in an executable LOAD segment")
    require(sum(item["end"] - item["start"] for item in loads) <= 16 * 1024 * 1024,
            "initial mapped bytes exceed kernel profile")
    require(max(item["file_end"] for item in loads) < len(data),
            "probe has no non-LOAD tail byte for the byte-mismatch control")
    return {"entry": entry, "bytes": len(data), "loads": loads, "sha256": digest(data)}


def build_initramfs(original, probe):
    require(len(original) <= 8 * 1024 * 1024, "original initramfs is too large")
    require(len(probe) <= 8 * 1024 * 1024, "initial probe is too large")
    unpacked = gzip.decompress(original)
    require(len(unpacked) <= 64 * 1024 * 1024, "uncompressed initramfs is too large")
    entries = replay.unpack(unpacked)
    require(replay.unpack(replay.pack(entries)) == entries, "original initramfs roundtrip failed")
    require(sum(name.lstrip("./") == "test" and stat.S_ISDIR(fields[1]) for name, fields, _ in entries) == 1,
            "original image must contain exactly one test directory")
    require(all(name.lstrip("./") != "test/g1c-init" for name, _, _ in entries),
            "initial probe already exists in the base image")
    inode = max(fields[0] for _, fields, _ in entries) + 1
    fields = [inode, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
    modified = [*entries, ("test/g1c-init", fields, probe)]
    require(replay.unpack(replay.pack(modified)) == modified, "initial-image cpio roundtrip failed")
    # /init remains byte-identical. QEMU rdinit selects the C ELF directly.
    return gzip.compress(replay.pack(modified), mtime=0)


def evaluate_positive(raw, code, timed_out, probe_info):
    require(len(raw) <= replay.MAX_SERIAL_BYTES, "G1-c serial exceeds evidence bound")
    text = ordinary.boot_check.ANSI.sub("", raw.decode(errors="replace"))
    lines = text.splitlines()
    counts = {marker: lines.count(marker) for marker in MARKERS}
    exact = all(count == 1 for count in counts.values())
    ordered = exact and [lines.index(marker) for marker in MARKERS] == sorted(lines.index(marker) for marker in MARKERS)
    seals = [f"G1C_SEAL_CASE name={name} result=PASS errno=1" for name in SEAL_CASES]
    seal_lines = [line for line in lines if line.startswith("G1C_SEAL_CASE ")]
    seals_ok = seal_lines == seals
    committed = [match for line in lines if (match := COMMITTED.fullmatch(line))]
    manifest_ok = (len(committed) == 1 and int(committed[0][1]) == probe_info["bytes"]
                   and int(committed[0][2], 16) == probe_info["entry"] and lines.count(ACTIVATED) == 1)
    activation_before_run = (manifest_ok and exact and lines.index(committed[0][0]) <
                             lines.index(ACTIVATED) < lines.index(MARKERS[0]))
    readings = []
    for line in lines:
        if match := USAGE.fullmatch(line):
            keys = ("sample", "cumulative", "window_start", "window_consumed", "cap", "period", "events", "dropped", "revision")
            readings.append({"label": match[1], **dict(zip(keys, map(int, match.groups()[1:])))})
    usage_ok = tuple(item["label"] for item in readings) == USAGE_LABELS
    previous = None
    for item in readings:
        expected_cap = 25_000_000 if item["label"] == "changed_linux_budget" else CAP_NS
        usage_ok &= (0 < item["sample"] < 1 << 64 and item["cap"] == expected_cap and item["period"] == PERIOD_NS
                     and item["window_start"] == item["sample"] // PERIOD_NS * PERIOD_NS
                     and 0 <= item["window_consumed"] <= item["cumulative"] <= item["sample"]
                     and item["cumulative"] - item["window_consumed"] <= item["window_start"]
                     and 0 <= item["dropped"] <= item["events"] < 1 << 64 and 0 < item["revision"] < 1 << 64)
        if previous:
            usage_ok &= item["sample"] >= previous["sample"] and item["cumulative"] >= previous["cumulative"]
            if item["window_start"] == previous["window_start"]:
                usage_ok &= item["window_consumed"] >= previous["window_consumed"]
        previous = item
    by_label = {item["label"]: item for item in readings}
    owner_records = [match for line in lines if (match := OWNER.fullmatch(line))]
    stat_records = [match for line in lines if (match := STAT.fullmatch(line))]
    owner_ok = usage_ok and len(owner_records) == 1 and len(stat_records) == 1
    if owner_ok:
        base = by_label["initial"]["revision"]
        for label in USAGE_LABELS:
            delta = (1 if label == "same_linux_budget" else 2 if label == "changed_linux_budget"
                     else 3 if USAGE_LABELS.index(label) >= USAGE_LABELS.index("restored_linux_budget") else 0)
            owner_ok &= by_label[label]["revision"] == base + delta
        owner_ok &= (tuple(map(int, owner_records[0].groups())) == (base + 1, base + 2, base + 3)
                     and by_label["before_stat"]["cumulative"] > by_label["before_work"]["cumulative"]
                     and int(stat_records[0][2]) == by_label["before_stat"]["cumulative"]
                     and int(stat_records[0][3]) == by_label["after_stat"]["cumulative"])
    known = set(MARKERS) | set(seals)
    unexpected = [line for line in lines if line.startswith("G1C_") and line not in known
                  and not USAGE.fullmatch(line) and not OWNER.fullmatch(line) and not STAT.fullmatch(line)]
    no_failure = (not unexpected and "rejected initial image" not in text
                  and not any(marker in text for marker in (*ordinary.boot_check.FATAL_PANICS, "Kernel panic"))
                  and not any(line.startswith("G1C_FAIL ") for line in lines))
    passed = (type(code) is int and code == 33 and timed_out is False and exact and ordered and seals_ok
              and manifest_ok and activation_before_run and usage_ok and owner_ok and no_failure)
    return {"passed": bool(passed), "marker_counts": counts, "ordered_markers": ordered,
            "seal_cases_exact": seals_ok, "manifest_verified_before_resume": activation_before_run,
            "read_usage_records": readings, "read_usage_invariants": bool(usage_ok),
            "original_linux_cpu_owner_revision_agrees": bool(owner_ok), "no_failure": no_failure,
            "unexpected_records": unexpected, "raw_serial_sha256": digest(raw), "raw_serial_size": len(raw)}


def evaluate_rejection(raw, code, timed_out, reason):
    require(reason in ("manifest-byte-mismatch", "truncated-snapshot"), "unknown negative control")
    require(len(raw) <= replay.MAX_SERIAL_BYTES, "G1-c rejection serial exceeds evidence bound")
    text = ordinary.boot_check.ANSI.sub("", raw.decode(errors="replace"))
    lines = text.splitlines()
    expected = f"[hepta-g1c] rejected initial image: {reason}"
    rejected = lines.count(expected) == 1 and sum("rejected initial image:" in line for line in lines) == 1
    no_resume = not any("trusted initial image committed:" in line or "initial observe activated:" in line
                        or line.startswith("G1C_") for line in lines)
    # Require the specific loader refusal plus the existing init-failure panic.
    # A panic elsewhere, timeout, or a boot which ran userspace is never a pass.
    exact_failure = text.count("failed to run the init process") == 1
    return {"passed": type(code) is int and code == 65 and timed_out is False and rejected and no_resume and exact_failure,
            "reason": reason, "exact_rejection": rejected, "no_commit_activation_or_guest": no_resume,
            "initial_loader_failure": exact_failure, "raw_serial_sha256": digest(raw), "raw_serial_size": len(raw)}


def verify_build(directory, snapshot, target, probe):
    for name in ("make-exit-code.txt", "log-exit-code.txt", "run-exit-code.txt"):
        require((directory / name).read_text().strip() == "0", f"kernel stage failed: {name}")
    require((directory / "environment.log").read_text().splitlines().count(snapshot["head"]) == 1,
            "build did not record the exact reviewed source head")
    command = shlex.split((directory / "command.sh").read_text())
    expected = ["make", "-C", str(ROOT / "kernel/asterinas"), "-f", "Makefile", "-f",
                str(ROOT / "support/build/minimal.mk"), "kernel"]
    required = {"TARGET_ARCH=x86_64", "SMP=1", "MEM=512M", "ENABLE_KVM=0", "BOOT_PROTOCOL=multiboot",
                "INITRAMFS=on", "AUTO_TEST=none", "HEPTA_G1C_TRUSTED_OBSERVE=1", "FEATURES=g1c-trusted-observe",
                f"A01_INITRAMFS={directory / 'initramfs.cpio.gz'}",
                f"A01_QEMU_WRAPPER={ROOT / 'support/build/record-qemu.py'}"}
    require(command[:8] == expected and len(command) == 20 and command[8].startswith("CARGO_OSDK=")
            and set(command[9:]) == required, "unexpected G1-c product build arguments")
    require("--features=g1c-trusted-observe" in (directory / "kernel.log").read_text(),
            "actual OSDK invocation did not include the explicit profile")
    source = subprocess.check_output([sys.executable, "-I", str(ROOT / "support/build/verify-source.py")], cwd=ROOT)
    require(json.loads(source) == json.loads((directory / "source-inputs.json").read_text()), "source-input gate differs")
    fixed = ROOT / "support/build/minimal/Cargo.lock"
    generated = target / "osdk/asterinas-run-base/Cargo.lock"
    require(generated.read_bytes() == fixed.read_bytes() and len(tomllib.loads(generated.read_text())["package"]) == 204,
            "G1-c generated package lock differs from the fixed 204-package product")
    embedded = directory / "trusted-initial.elf"
    require(embedded.read_bytes() == probe and stat.S_IMODE(embedded.stat().st_mode) == 0o444,
            "embedded trusted image differs from the frozen compiled probe")
    manifest = json.loads((directory / "trusted-initial-manifest.json").read_text())
    expected_manifest = {"schema": "hepta-g1c-trusted-initial-v1", "profile": "g1c-trusted-observe",
                         "embedded_input": str(embedded), "bytes": len(probe), "sha256": digest(probe),
                         "supported_ops": 6, "features": 0, "slot": 1, "generation": 1,
                         "cap_ns": CAP_NS, "period_ns": PERIOD_NS, "lease_ns": LEASE_NS}
    require(all(manifest.get(key) == value for key, value in expected_manifest.items()), "trusted build manifest differs")
    require(Path(manifest["source"]).read_bytes() == probe, "input changed after the build snapshot")
    kernel_path = target / "osdk/asterinas/asterinas-osdk-bin.elf"
    require(kernel_path.is_file() and not kernel_path.is_symlink()
            and kernel_path.stat().st_size <= ordinary.MAX_KERNEL_BYTES, "invalid bounded product kernel")
    kernel = kernel_path.read_bytes()
    require(kernel[:6] == b"\x7fELF\x02\x01" and kernel[18:20] == b"\x03\x00",
            "kernel is not the original OSDK multiboot EM_386 conversion")
    original = directory / "initramfs.cpio.gz"
    image_manifest = json.loads((directory / "initramfs-manifest.json").read_text())
    initramfs = replay.read_pinned_file(original, image_manifest["image_sha256"], 8 * 1024 * 1024)
    return kernel, initramfs, digest(generated.read_bytes()), manifest


def boot(args, output, kernel, bios, initramfs, name, binary):
    directory = output / name
    directory.mkdir(mode=0o700)
    (directory / "initramfs.cpio.gz").write_bytes(initramfs)
    argv = [binary, "-kernel", str(output / "product-kernel.elf"), "-initrd", str(directory / "initramfs.cpio.gz"),
            "-append", "earlycon console=ttyS0 loglevel=info rdinit=/test/g1c-init SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --",
            "-machine", "q35", "-accel", "tcg", "-cpu", "max", "-bios", str(output / "bios.bin"),
            "-m", "512M", "-smp", "1", "-nodefaults", "-no-user-config", "-no-reboot", "-nographic",
            "-display", "none", "-monitor", "none", "-serial", "stdio", "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"]
    evidence = {"argv": argv, "kernel_sha256": digest(kernel), "bios_sha256": digest(bios),
                "initramfs_sha256": digest(initramfs), "qemu_sha256": digest(Path(binary).read_bytes()),
                "qemu_exit": None, "timed_out": False}
    save_json(directory / "qemu.json", evidence)
    started = time.monotonic()
    with (directory / "serial.log").open("xb") as serial:
        try:
            evidence["qemu_exit"] = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=serial,
                                                   stderr=subprocess.STDOUT, timeout=args.timeout, check=False).returncode
        except subprocess.TimeoutExpired:
            evidence["timed_out"] = True
    evidence["elapsed_seconds"] = round(time.monotonic() - started, 3)
    raw = (directory / "serial.log").read_bytes()
    save_json(directory / "qemu.json", evidence)
    require((output / "product-kernel.elf").read_bytes() == kernel and (output / "bios.bin").read_bytes() == bios
            and (directory / "initramfs.cpio.gz").read_bytes() == initramfs, "boot inputs changed during execution")
    return raw, evidence


def run(args, output, result):
    snapshot = ordinary.source_snapshot(ROOT, args.expected_source_head, args.expected_source_tree)
    for name in ("tests/kernel/control/g1c_init.c", "tests/kernel/control/run_g1c_guest.py",
                 "support/build/prepare-trusted-image.py"):
        require(name in snapshot["files"], "untracked execution input")
    save_json(output / "source-before.json", snapshot)
    result.update(source_head=snapshot["head"], source_tree=snapshot["tree"], source_file_count=len(snapshot["files"]),
                  stage="compile_actual_initial_elf")
    compiler = [args.cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread", "-static", "-no-pie",
                "-Wl,-z,noexecstack,-z,separate-code", str(ROOT / "tests/kernel/control/g1c_init.c"),
                "-o", str(output / "g1c-init")]
    built = subprocess.run(compiler, capture_output=True, timeout=90, check=False)
    (output / "compile.log").write_bytes(built.stdout + built.stderr)
    result.update(compiler_command=compiler, compile_exit=built.returncode)
    require(built.returncode == 0, "static trusted initial ELF compilation failed")
    probe = (output / "g1c-init").read_bytes()
    probe_info = inspect_probe_elf(probe)
    save_json(output / "probe.json", probe_info)
    target = args.target_dir.absolute()
    require(not target.exists() and not target.is_symlink(), "G1-c target must be fresh")
    require(not target.resolve().is_relative_to(ROOT.resolve()), "G1-c target must be outside source")
    build_dir = output / "kernel-build"
    env = dict(os.environ)
    for name in ("RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER",
                 "CARGO_TARGET_DIR", "HEPTA_TRUSTED_INITIAL_ELF", "HEPTA_G1C_TRUSTED_OBSERVE", "FEATURES"):
        env.pop(name, None)
    env.update(A01_RUN_DIR=str(build_dir), A01_SMP="1", CARGO_TARGET_DIR=str(target),
               HEPTA_G1C_TRUSTED_OBSERVE="1", HEPTA_TRUSTED_INITIAL_ELF=str(output / "g1c-init"))
    result.update(stage="build_explicit_profile", product_configuration="ActionChoice::Run; g1c-trusted-observe; no --cfg ktest")
    save_json(output / "result.json", result)
    with (output / "build-wrapper.log").open("xb") as log:
        built = subprocess.run([str(ROOT / "support/build/kernel.sh"), "kernel"], env=env, cwd=ROOT,
                               stdout=log, stderr=subprocess.STDOUT, check=False)
    result["build_wrapper_exit"] = built.returncode
    after = ordinary.source_snapshot(ROOT, args.expected_source_head, args.expected_source_tree)
    save_json(output / "source-after-build.json", after)
    require(snapshot == after, "tracked source changed during G1-c build")
    require(built.returncode == 0, "G1-c kernel build failed; original logs retained")
    kernel, original, lock_hash, manifest = verify_build(build_dir, snapshot, target, probe)
    bios = replay.read_pinned_file(args.bios, replay.SEABIOS_SHA, 2 * 1024 * 1024)
    binary = shutil.which(args.qemu)
    require(binary is not None, "QEMU unavailable")
    result.update(stage="guest_profiles", kernel_elf_sha256=digest(kernel), probe_sha256=digest(probe),
                  original_initramfs_sha256=digest(original), bios_sha256=digest(bios),
                  generated_lock_sha256=lock_hash, generated_package_count=204, trusted_manifest=manifest,
                  qemu_version=subprocess.check_output([binary, "--version"], text=True).strip(),
                  qemu_sha256=digest(Path(binary).read_bytes()))
    (output / "product-kernel.elf").write_bytes(kernel)
    (output / "bios.bin").write_bytes(bios)
    changed = bytearray(probe)
    changed[-1] ^= 1
    controls = (("exact", probe, None), ("byte-mismatch", bytes(changed), "manifest-byte-mismatch"),
                ("truncated", probe[:-1], "truncated-snapshot"))
    guests = {}
    for name, actual_probe, reason in controls:
        initramfs = build_initramfs(original, actual_probe)
        raw, evidence = boot(args, output, kernel, bios, initramfs, name, binary)
        verdict = (evaluate_positive(raw, evidence["qemu_exit"], evidence["timed_out"], probe_info) if reason is None
                   else evaluate_rejection(raw, evidence["qemu_exit"], evidence["timed_out"], reason))
        guests[name] = {**evidence, **verdict, "actual_initial_elf_sha256": digest(actual_probe)}
        save_json(output / name / "result.json", guests[name])
        result["guests"] = guests
        save_json(output / "result.json", result)
    final = ordinary.source_snapshot(ROOT, args.expected_source_head, args.expected_source_tree)
    save_json(output / "source-after-guests.json", final)
    require(final == snapshot and (output / "g1c-init").read_bytes() == probe
            and (build_dir / "trusted-initial.elf").read_bytes() == probe, "source or embedded manifest changed between controls")
    require(digest(Path(binary).read_bytes()) == result["qemu_sha256"], "QEMU changed between profiles")
    result.update(stage="complete", source_inputs_unchanged=True, same_kernel_for_all_controls=True,
                  passed=all(guest["passed"] for guest in guests.values()))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-source-head", required=True)
    parser.add_argument("--expected-source-tree", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-dir", type=Path, required=True)
    parser.add_argument("--bios", type=Path, default=Path("/usr/share/seabios/bios-256k.bin"))
    parser.add_argument("--qemu", default="qemu-system-x86_64")
    parser.add_argument("--cc", default="cc")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args(argv)
    require(1 <= args.timeout <= 120, "guest timeout must be 1..120 seconds")
    output = args.output.absolute()
    require(not output.exists() and not output.is_symlink(), "output must be a new directory")
    require(not output.resolve().is_relative_to(ROOT.resolve()), "evidence must be outside the source checkout")
    output.mkdir(mode=0o700, parents=True)
    result = {"schema": "a06.g1c-trusted-initial-observe.v1", "stage": "source_admission", "passed": False,
              "profile": "g1c-trusted-observe", "native_manage": False, "native_history": False,
              "hepta_durability": False, "smp_qualification": False, "hardware_qualification": False,
              "legacy_linux_management_isolated": False, "production_ready": False}
    try:
        run(args, output, result)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        result.update(passed=False, error=f"{type(error).__name__}: {error}")
    save_json(output / "result.json", result)
    print(json.dumps({"passed": result["passed"], "stage": result["stage"], "output": str(output)}, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
