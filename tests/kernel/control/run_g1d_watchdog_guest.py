#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Qualify the fixed watchdog with actual sealed images and hardware timer ticks.

Six separate boots use one exact ELF manifest. None of the successful recovery
checks call a test-only kernel hook. Fault-cut ktests cover late/unknown clocks;
this gate does not claim those synthetic cuts as physical-clock fault evidence.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_g1d_guest as control

ROOT = Path(__file__).resolve().parents[3]
ordinary, replay = control.ordinary, control.replay
require, digest, save_json = control.require, control.digest, control.save_json
CASES = ("restore", "healthy", "zero", "zerothread", "stopped", "recovered")
RESULT = re.compile(r"^G1DW_RESULT case=([a-z]+) status=([0-9]+) cap=([0-9]+) revision=([0-9]+) "
                    r"due=([0-9]+) expires=([0-9]+) evaluated=([0-9]+) stopped=([01]) user_pause_intent_available=0$")
RECEIPT = re.compile(r"^G1DW_RECEIPT previous=([0-9]+) revision=([0-9]+) effective=([0-9]+) "
                     r"consumed=([0-9]+) stable_low=([0-9]+) stable_high=([0-9]+)$")
CLOSE = re.compile(r"^G1DW_MANAGER_CLOSE case=([a-z]+) original_revision=([0-9]+) failure=exec_revoke$")
REPEAT = re.compile(r"^G1DW_REPEAT before_ticks=([0-9]+) after_ticks=([0-9]+) unchanged_receipt=1 unchanged_revision=1$")
REAP = re.compile(r"^G1DW_REAP case=([a-z]+) workload_signal=9 recovery_exit=0$")
FATAL_EXIT = re.compile(r"^G1DW_FATAL_EXIT case=([a-z]+) signal=9 reaped=1 heartbeat_before=([0-9]+) "
                        r"heartbeat_after=([0-9]+) cap_before=0 cap_after=0 period_usec=100000$")
ZERO_CASES = ("zero", "zerothread")
INIT_IMMUNITY = "G1DW_INIT_SIGKILL_IGNORED original_policy=1"
ONE_USE = "G1DW_ONE_USE denied=2 exact_replay=1 manager_next_D=not_seen"
CONTINUE = "G1DW_EXPLICIT_CONTINUE signal=18 original_jobstop_cleared=1 budget_unchanged=1"


def evaluate(raw, code, timed_out, probe_info, kind):
    require(kind in CASES and len(raw) <= replay.MAX_SERIAL_BYTES, "invalid or oversized guest evidence")
    text = ordinary.boot_check.ANSI.sub("", raw.decode(errors="replace"))
    lines = text.splitlines()
    records = lambda pattern: control.records(lines, pattern)
    complete = f"G1DW_COMPLETE case={kind} timer=true original_owner=true durable=false reserve=false"
    allowed = (ONE_USE, CONTINUE, complete, INIT_IMMUNITY)
    patterns = (RESULT, RECEIPT, CLOSE, REPEAT, REAP, FATAL_EXIT, control.BOOT, control.APPLY, control.COMMITTED,
                control.ROLE_COMMITTED, control.ACTIVATED)
    unknown = [line for line in lines if any(tag in line for tag in ("G1D_", "G1DW_", "[hepta-g1d]"))
               and line not in allowed and not any(pattern.fullmatch(line) for pattern in patterns)]
    clean = not unknown and not any(marker in text for marker in
        (*ordinary.boot_check.FATAL_PANICS, "Kernel panic", "rejected initial image"))
    images, roles, activation, boots = (records(pattern) for pattern in
        (control.COMMITTED, control.ROLE_COMMITTED, control.ACTIVATED, control.BOOT))
    pids = tuple(map(int, activation[0][1].groups())) if len(activation) == 1 else ()
    manifest = (len(images) == len(roles) == len(boots) == 3 and len(pids) == 3 and pids[0] == 1
                and len(set(pids)) == 3 and all(1 < pid < 1 << 31 for pid in pids[1:])
                and all(int(match[1]) == probe_info["bytes"] and int(match[2], 16) == probe_info["entry"]
                        for _, match in images)
                and [tuple(map(int, match.groups())) for _, match in roles] == list(zip((1, 2, 3), pids))
                and {int(match[1]) for _, match in boots} == {1, 2, 3}
                and all(int(match[2]) == pids[int(match[1]) - 1] and tuple(map(int, match.groups()[2:])) == pids
                        for _, match in boots))
    if manifest:
        manifest = (all(images[i][0] < roles[i][0] for i in range(3))
                    and max(index for index, _ in images + roles) < activation[0][0]
                    < min(index for index, _ in boots))
    results, receipts, closes, applications = (records(pattern) for pattern in (RESULT, RECEIPT, CLOSE, control.APPLY))
    expected = {"restore": (1, 50_000_000, 2, 0), "healthy": (0, 25_000_000, 1, 0),
                "zero": (2, 0, 1, 0), "zerothread": (2, 0, 1, 0), "stopped": (3, 25_000_000, 1, 1), "recovered": (2, 50_000_000, 2, 0)}[kind]
    effect = False
    if manifest and len(results) == 1 and len(applications) == (2 if kind == "recovered" else 1):
        result = results[0][1]
        status, cap, revision, due, expires, evaluated, stopped = map(int, result.groups()[1:])
        applied = [dict(zip(control.APPLY_KEYS, map(int, match.groups()))) for _, match in applications]
        original = applied[0]["previous"]
        effect = (result[1] == kind and (status, cap, revision - original, stopped) == expected
                  and original > 0 and due > 0 and expires == due + 25_000_000_000)
        effect &= evaluated == 0 if kind == "healthy" else due <= evaluated < expires
        effect &= (applied[0]["role"] == 1 and applied[0]["sequence"] == 1
                   and applied[0]["cap"] == (0 if kind in ZERO_CASES else 25_000_000)
                   and applied[0]["revision"] == original + 1)
        for item in applied:
            effect &= (all(0 <= value < 1 << 64 for value in item.values())
                       and 0 < item["before_sample"] <= item["effective"] <= item["after_sample"]
                       and item["before_total"] <= item["after_total"]
                       and item["consumed"] <= item["effective"] % control.PERIOD_NS)
        if kind == "recovered":
            effect &= (applied[1]["role"], applied[1]["sequence"], applied[1]["cap"],
                       applied[1]["previous"], applied[1]["revision"]) == (3, 1, 50_000_000, original + 1, original + 2)
        if kind == "restore":
            effect &= len(receipts) == 1
            if receipts:
                previous, saved, effective, consumed, low, high = map(int, receipts[0][1].groups())
                effect &= (previous == original + 1 and saved == revision and effective == evaluated
                           and consumed <= effective % control.PERIOD_NS and (low != 0 or high != 0)
                           and applications[0][0] < closes[0][0] < receipts[0][0] < results[0][0]) if len(closes) == 1 else False
        else:
            effect &= not receipts
        effect &= (not closes if kind == "healthy" else len(closes) == 1 and closes[0][1][1] == kind
                   and int(closes[0][1][2]) == original + 1 and applications[0][0] < closes[0][0] < results[0][0])
    repeats = records(REPEAT)
    markers = (lines.count(INIT_IMMUNITY) == 1 and lines.count(complete) == 1 and len(repeats) == (0 if kind == "healthy" else 1)
               and lines.count(ONE_USE) == (1 if kind == "restore" else 0)
               and lines.count(CONTINUE) == (1 if kind == "stopped" else 0))
    if repeats:
        markers &= len(repeats) == 1 and 0 < int(repeats[0][1][1]) < int(repeats[0][1][2]) < 1 << 64
    if len(results) == 1 and lines.count(complete) == 1:
        markers &= results[0][0] < lines.index(complete)
    reaps, fatal_exits = records(REAP), records(FATAL_EXIT)
    cleanup = len(reaps) == (0 if kind == "healthy" else 1) and len(fatal_exits) == (1 if kind in ZERO_CASES else 0)
    if reaps:
        cleanup &= (len(reaps) == 1 and reaps[0][1][1] == kind and lines.count(complete) == 1
                    and lines.index(complete) < reaps[0][0])
    if fatal_exits:
        cleanup &= (len(fatal_exits) == 1 and fatal_exits[0][1][1] == kind
                    and 0 < int(fatal_exits[0][1][2]) == int(fatal_exits[0][1][3]) < 1 << 64
                    and len(reaps) == 1 and lines.count(complete) == 1
                    and lines.index(complete) < fatal_exits[0][0] < reaps[0][0])
    return {"passed": bool(type(code) is int and code == 33 and timed_out is False and clean and manifest and effect and markers and cleanup),
            "case": kind, "manifest_verified_before_any_resume": bool(manifest),
            "original_owner_effect_and_deadline": bool(effect), "required_markers": bool(markers), "fatal_cleanup_and_reap": bool(cleanup),
            "unknown_records": unknown, "raw_serial_sha256": digest(raw), "raw_serial_size": len(raw),
            "qemu_exit": code, "timed_out": timed_out}


def boot(args, output, kind, kernel, bios, initramfs, binary):
    directory = output / kind
    directory.mkdir(mode=0o700)
    (directory / "initramfs.cpio.gz").write_bytes(initramfs)
    argv = [binary, "-kernel", str(output / "product-kernel.elf"), "-initrd", str(directory / "initramfs.cpio.gz"),
            "-append", "earlycon console=ttyS0 loglevel=warn rdinit=/test/g1d-init SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin -- " + kind,
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
    require((output / "product-kernel.elf").read_bytes() == kernel and (output / "bios.bin").read_bytes() == bios
            and (directory / "initramfs.cpio.gz").read_bytes() == initramfs, "boot inputs changed")
    save_json(directory / "qemu.json", evidence)
    return raw, evidence


def run(args, output, result):
    snapshot = ordinary.source_snapshot(ROOT, args.expected_source_head, args.expected_source_tree)
    for name in ("tests/kernel/control/g1d_watchdog.c", "tests/kernel/control/run_g1d_watchdog_guest.py",
                 "tests/kernel/control/g1d_init.c", "tests/kernel/control/g1d_pids.c", "tests/kernel/control/run_g1d_guest.py"):
        require(name in snapshot["files"], "untracked execution input")
    save_json(output / "source-before.json", snapshot)
    result.update(source_head=snapshot["head"], source_tree=snapshot["tree"], stage="compile_initial_elf")
    compiler = [args.cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-static", "-no-pie", "-pthread",
                "-Wl,-z,noexecstack,-z,separate-code", str(ROOT / "tests/kernel/control/g1d_watchdog.c"),
                "-o", str(output / "g1d-init")]
    built = subprocess.run(compiler, capture_output=True, timeout=90, check=False)
    (output / "compile.log").write_bytes(built.stdout + built.stderr)
    result.update(compiler_command=compiler, compile_exit=built.returncode)
    require(built.returncode == 0, "native probe compilation failed")
    probe = (output / "g1d-init").read_bytes()
    probe_info = control.inspect_probe_elf(probe)
    save_json(output / "probe.json", probe_info)
    target = args.target_dir.absolute()
    require(not target.resolve().is_relative_to(ROOT.resolve()), "target must be outside source")
    build_dir = args.prepared_build.absolute() if args.prepared_build else output / "kernel-build"
    if not args.prepared_build:
        require(not target.exists() and not target.is_symlink(), "new build target must be fresh")
        env = dict(os.environ)
        for name in ("RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER",
                     "CARGO_TARGET_DIR", "HEPTA_TRUSTED_INITIAL_ELF", "HEPTA_G1C_TRUSTED_OBSERVE",
                     "HEPTA_G1D_TRUSTED_CONTROL", "FEATURES"):
            env.pop(name, None)
        env.update(A01_RUN_DIR=str(build_dir), A01_SMP="1", CARGO_TARGET_DIR=str(target),
                   HEPTA_G1D_TRUSTED_CONTROL="1", HEPTA_TRUSTED_INITIAL_ELF=str(output / "g1d-init"))
        result.update(stage="build_profile")
        save_json(output / "result.json", result)
        with (output / "build-wrapper.log").open("xb") as log:
            built = subprocess.run([str(ROOT / "support/build/kernel.sh"), "kernel"], cwd=ROOT, env=env,
                                   stdout=log, stderr=subprocess.STDOUT, timeout=1800, check=False)
        require(built.returncode == 0, "kernel build failed")
    require(ordinary.source_snapshot(ROOT, args.expected_source_head, args.expected_source_tree) == snapshot,
            "source changed during build")
    # A prepared build is accepted only through the identical source, manifest,
    # package-lock, exact probe and kernel extraction checks used by a new build.
    kernel, original, lock_hash, manifest = control.verify_build(build_dir, snapshot, target, probe)
    bios = replay.read_pinned_file(args.bios, replay.SEABIOS_SHA, 2 * 1024 * 1024)
    binary = shutil.which(args.qemu)
    require(binary is not None, "QEMU unavailable")
    result.update(stage="guest", kernel_elf_sha256=digest(kernel), probe_sha256=digest(probe),
                  original_initramfs_sha256=digest(original), bios_sha256=digest(bios), generated_lock_sha256=lock_hash,
                  trusted_manifest=manifest, qemu_sha256=digest(Path(binary).read_bytes()),
                  qemu_version=subprocess.check_output([binary, "--version"], text=True).strip())
    (output / "product-kernel.elf").write_bytes(kernel)
    (output / "bios.bin").write_bytes(bios)
    result["guests"] = {}
    initramfs = control.build_initramfs(original, probe)
    for kind in CASES:
        raw, evidence = boot(args, output, kind, kernel, bios, initramfs, binary)
        verdict = evaluate(raw, evidence["qemu_exit"], evidence["timed_out"], probe_info, kind)
        result["guests"][kind] = {**evidence, **verdict}
        save_json(output / kind / "result.json", result["guests"][kind])
        save_json(output / "result.json", result)
    final = ordinary.source_snapshot(ROOT, args.expected_source_head, args.expected_source_tree)
    save_json(output / "source-after-guest.json", final)
    require(final == snapshot and (output / "g1d-init").read_bytes() == probe
            and (build_dir / "trusted-initial.elf").read_bytes() == probe
            and digest(Path(binary).read_bytes()) == result["qemu_sha256"], "execution inputs changed")
    passed = all(verdict["passed"] for verdict in result["guests"].values())
    result.update(stage="complete", passed=passed, source_inputs_unchanged=True, independent_timer_qualified=passed)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-source-head", required=True)
    parser.add_argument("--expected-source-tree", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-dir", type=Path, required=True)
    parser.add_argument("--prepared-build", type=Path)
    parser.add_argument("--bios", type=Path, default=Path("/usr/share/seabios/bios-256k.bin"))
    parser.add_argument("--qemu", default="qemu-system-x86_64")
    parser.add_argument("--cc", default="cc")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args(argv)
    require(1 <= args.timeout <= 600, "guest timeout must be 1..600 seconds")
    output = args.output.absolute()
    require(not output.exists() and not output.is_symlink(), "output must be new")
    require(not output.resolve().is_relative_to(ROOT.resolve()), "evidence must be outside source")
    output.mkdir(mode=0o700, parents=True)
    result = {"schema": "g1d.owner-watchdog.v1", "stage": "source_admission", "passed": False,
              "independent_timer_qualified": False, "trusted_user_pause_intent": False,
              "global_physical_reserve": False, "smp_qualification": False,
              "physical_clock_fault_injection": False, "hardware_qualification": False,
              "hepta_durability": False, "production_ready": False}
    try:
        run(args, output, result)
    except (OSError, ValueError, KeyError, TypeError, IndexError, subprocess.SubprocessError) as error:
        result.update(passed=False, error=f"{type(error).__name__}: {error}")
    save_json(output / "result.json", result)
    print(json.dumps({"passed": result["passed"], "stage": result["stage"], "output": str(output)}, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
