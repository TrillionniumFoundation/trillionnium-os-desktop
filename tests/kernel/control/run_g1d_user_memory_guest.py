#!/usr/bin/env python3
"""Bounded native G1-d family user-frame admission and separate-role recovery.

This gate does not qualify memory.max, global physical reserves, OOM killing,
SMP, hardware or durable Hepta delivery. --expect-no-limit is a counterfactual
negative only; its passing receipt never sets product qualification fields.
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
LIMIT_PAGES = 16384
HOLDER_PAGES = 4608
COMPLETE = ("G1DM_COMPLETE aggregate_user_frames=true fork_exec=true recovery=true "
            "memory_max=false physical_reserve=false hardware=false")
REFUND = "G1DM_REFUND family_children_reaped=3 parent_cow_unchanged=1 file_truncated=1"
HOLDER = re.compile(r"^G1DM_HOLDER kind=(fork|exec) pid=([0-9]+) parent=([0-9]+) pages=4608$")
EXEC = re.compile(r"^G1DM_EXEC_CHILD pid=([0-9]+) parent=([0-9]+) uid=60001 no_boot=1$")
DENIALS = re.compile(r"^G1DM_DENIALS pid=([0-9]+) address=([0-9]+) pages=([0-9]+) "
                    r"shared_address=([0-9]+) cow_address=([0-9]+) file_address=([0-9]+) "
                    r"direct_errno=14 shared_errno=14 cow_errno=14 file_errno=14 write_errno=12$")
SATURATED = re.compile(r"^G1DM_SATURATED pid=([0-9]+) fork_pid=([0-9]+) exec_pid=([0-9]+) "
                      r"saturator_pid=([0-9]+) holder_pages=4608 saturator_pages=([0-9]+) limit_pages=16384$")
FAULT = re.compile(r"^\[hepta-user-memory\] denied pid=([0-9]+) address=([0-9]+) "
                   r"current_pages=16384 limit_pages=16384$")
ALLOC = re.compile(r"^G1DM_RECOVERY_ALLOC role=3 pid=([0-9]+) pages=16 workload_at_limit=1 physical_reserve=false$")
READBACK = re.compile(r"^G1DM_RECOVERY_READBACK initial=([0-9]+) stopped=([0-9]+) recovered=([0-9]+) "
                      r"stopped_total=([0-9]+) paused_total=([0-9]+) "
                      r"cap=50000000 manager_history_terminal=1$")
RETRY = re.compile(r"^G1DM_RETRY pid=([0-9]+) address=([0-9]+) same_mappings=1 "
                   r"anonymous=1 shared=1 cow=1 file_fault=1 file_write=1$")
NO_LIMIT = re.compile(r"^G1DM_NO_LIMIT pid=([0-9]+) pages=16384 held_pages=9216$")
FAILURE = re.compile(r"^G1D_FAIL at=([a-z_]+) line=([0-9]+) errno=([0-9]+) pid=([0-9]+) role=([123])$")
PATTERNS = (HOLDER, EXEC, DENIALS, SATURATED, FAULT, ALLOC, READBACK, RETRY, NO_LIMIT,
            FAILURE, control.BOOT, control.APPLY, control.COMMITTED, control.ROLE_COMMITTED, control.ACTIVATED)


def evaluate(raw, code, timed_out, probe_info, expect_no_limit=False):
    require(len(raw) <= replay.MAX_SERIAL_BYTES, "memory serial exceeds evidence bound")
    text = ordinary.boot_check.ANSI.sub("", raw.decode(errors="replace"))
    lines = text.splitlines()
    records = lambda pattern: control.records(lines, pattern)
    unknown = [line for line in lines
               if any(token in line for token in ("G1DM_", "G1D_", "[hepta-g1d]", "[hepta-user-memory]"))
               and line not in (COMPLETE, REFUND)
               and not any(pattern.fullmatch(line) for pattern in PATTERNS)]
    clean = not unknown and not any(marker in text for marker in
        (*ordinary.boot_check.FATAL_PANICS, "Kernel panic", "rejected initial image"))
    images, roles, activation, boots = (records(pattern) for pattern in
        (control.COMMITTED, control.ROLE_COMMITTED, control.ACTIVATED, control.BOOT))
    pids = tuple(map(int, activation[0][1].groups())) if len(activation) == 1 else ()
    manifest = (len(images) == len(roles) == len(boots) == 3 and len(pids) == 3
                and pids[0] == 1 and len(set(pids)) == 3 and all(1 < pid < 1 << 31 for pid in pids[1:])
                and all(int(match[1]) == probe_info["bytes"] and int(match[2], 16) == probe_info["entry"]
                        for _, match in images)
                and [tuple(map(int, match.groups())) for _, match in roles] == list(zip((1, 2, 3), pids))
                and {int(match[1]) for _, match in boots} == {1, 2, 3}
                and all(int(match[2]) == pids[int(match[1]) - 1]
                        and tuple(map(int, match.groups()[2:])) == pids for _, match in boots))
    if manifest:
        manifest = (all(images[i][0] < roles[i][0] for i in range(3))
                    and max(index for index, _ in images + roles) < activation[0][0]
                    < min(index for index, _ in boots))
    boot_indices = {int(match[1]): index for index, match in boots}
    holders, executed, denied, saturation, faults, allocated, readback, retry, failures, no_limit = (
        records(pattern) for pattern in (HOLDER, EXEC, DENIALS, SATURATED, FAULT, ALLOC, READBACK,
                                        RETRY, FAILURE, NO_LIMIT))
    holder_ok = (manifest and len(holders) == 2 and [match[1] for _, match in holders] == ["fork", "exec"]
                 and all(int(match[3]) == pids[1] and 1 < int(match[2]) < 1 << 31
                         and int(match[2]) not in pids for _, match in holders)
                 and len(executed) == 1 and int(executed[0][1][1]) == int(holders[1][1][2])
                 and int(executed[0][1][2]) == pids[1]
                 and int(holders[0][1][2]) != int(holders[1][1][2])
                 and boot_indices[2] < holders[0][0]
                 and holders[0][0] < executed[0][0] < holders[1][0])
    aggregate = False
    path_admission = False
    if holder_ok and len(denied) == len(saturation) == 1:
        d, s = denied[0][1], saturation[0][1]
        sat_pid, address, pages, shared, cow, file_address = map(int, d.groups())
        children = (int(holders[0][1][2]), int(holders[1][1][2]), sat_pid)
        aggregate = (int(s[1]) == pids[1] and tuple(map(int, s.groups()[1:4])) == children
                     and len(set((*pids, *children))) == 6 and 1 < sat_pid < 1 << 31
                     and int(s[5]) == pages and 4096 <= pages < LIMIT_PAGES - 2 * HOLDER_PAGES
                     and holders[1][0] < denied[0][0] < saturation[0][0])
        addresses = (address, shared, cow, file_address)
        path_admission = (aggregate and len(set(addresses)) == 4
                          and all(4096 <= value < 1 << 47 and value % 4096 == 0 for value in addresses)
                          and len(faults) == 4
                          and [(int(match[1]), int(match[2])) for _, match in faults]
                          == [(sat_pid, value) for value in addresses]
                          and holders[1][0] < faults[0][0] < faults[-1][0] < denied[0][0])
    applications = [dict(zip(control.APPLY_KEYS, map(int, match.groups())))
                    for _, match in records(control.APPLY)]
    control_ok = False
    if path_admission and len(allocated) == len(readback) == 1 and len(applications) == 2:
        before, stopped, recovered, stopped_total, paused_total = map(int, readback[0][1].groups())
        control_ok = (int(allocated[0][1][1]) == pids[2] and before > 0
                      and stopped == before + 1 and recovered == before + 2
                      and [(item["role"], item["sequence"], item["cap"], item["previous"], item["revision"])
                           for item in applications]
                      == [(1, 1, 0, before, stopped), (3, 1, 50_000_000, stopped, recovered)])
        for item in applications:
            control_ok &= (all(0 <= value < 1 << 64 for value in item.values())
                           and 0 < item["before_sample"] <= item["effective"] <= item["after_sample"]
                           and item["before_total"] <= item["after_total"]
                           and item["consumed"] <= item["effective"] % control.PERIOD_NS)
            for prefix in ("before", "after"):
                sample, total, start, used = (item[prefix + "_" + key]
                                              for key in ("sample", "total", "start", "used"))
                control_ok &= (start == sample // control.PERIOD_NS * control.PERIOD_NS
                               and used <= total <= sample and used <= sample % control.PERIOD_NS
                               and total - used <= start)
            if item["effective"] // control.PERIOD_NS * control.PERIOD_NS == item["before_start"]:
                control_ok &= item["consumed"] >= item["before_used"]
            if item["effective"] // control.PERIOD_NS * control.PERIOD_NS == item["after_start"]:
                control_ok &= item["after_used"] >= item["consumed"]
        control_ok &= (0 < stopped_total == paused_total == applications[0]["after_total"]
                       == applications[1]["before_total"]
                       and applications[1]["before_sample"] >= applications[0]["after_sample"])
    refund_ok = (control_ok and len(retry) == 1 and retry[0][1].groups() == denied[0][1].groups()[:2]
                 and lines.count(REFUND) == lines.count(COMPLETE) == 1)
    ordered = False
    if refund_ok:
        apply_indices = [index for index, _ in records(control.APPLY)]
        indices = [saturation[0][0], apply_indices[0], allocated[0][0], apply_indices[1],
                   readback[0][0], retry[0][0], lines.index(REFUND), lines.index(COMPLETE)]
        ordered = all(left < right for left, right in zip(indices, indices[1:]))
        ordered &= boot_indices[1] < apply_indices[0] and boot_indices[3] < allocated[0][0]
    exited = type(code) is int and code == 33 and timed_out is False
    positive = bool(exited and clean and manifest and path_admission and control_ok and refund_ok and ordered
                    and not failures and not no_limit)
    negative = (exited and clean and holder_ok and len(no_limit) == len(failures) == 1
                and not denied and not saturation and not faults and not allocated and not readback
                and not retry and not applications and REFUND not in lines and COMPLETE not in lines)
    if negative:
        failure = failures[0][1]
        negative = (failure[1] == "memory_aggregate_limit" and int(failure[2]) > 0
                    and (int(failure[4]), int(failure[5])) == (pids[0], 1)
                    and 1 < int(no_limit[0][1][1]) < 1 << 31
                    and int(no_limit[0][1][1]) not in (*pids, int(holders[0][1][2]), int(holders[1][1][2]))
                    and holders[1][0] < no_limit[0][0] < failures[0][0]
                    and boot_indices[1] < failures[0][0] and boot_indices[3] < failures[0][0]
                    and not positive)
    return {"passed": bool(negative if expect_no_limit else positive),
            "counterfactual_only": bool(expect_no_limit), "positive_oracle_passed": positive,
            "exact_no_limit_negative": bool(negative), "manifest_verified_before_any_resume": bool(manifest),
            "family_aggregate_observed": bool(aggregate), "four_fault_causes_and_file_write_bound": bool(path_admission),
            "independent_recovery_effect_and_readback": bool(control_ok), "same_mapping_retry_after_refund": bool(refund_ok),
            "observations_ordered": bool(ordered), "unknown_records": unknown,
            "failure_records": [match.group(0) for _, match in failures],
            "qemu_exit": code, "timed_out": timed_out, "raw_serial_sha256": digest(raw), "raw_serial_size": len(raw)}


def boot(args, output, kernel, bios, initramfs, binary):
    directory = output / "exact"
    directory.mkdir(mode=0o700)
    (directory / "initramfs.cpio.gz").write_bytes(initramfs)
    argv = [binary, "-kernel", str(output / "product-kernel.elf"), "-initrd", str(directory / "initramfs.cpio.gz"),
            "-append", "earlycon console=ttyS0 loglevel=warn rdinit=/test/g1d-init SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --",
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
            and (directory / "initramfs.cpio.gz").read_bytes() == initramfs, "boot inputs changed")
    return raw, evidence


def run(args, output, result):
    (output / "git-status-porcelain.txt").write_bytes(subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT))
    snapshot = ordinary.source_snapshot(ROOT, args.expected_source_head, args.expected_source_tree)
    for name in ("tests/kernel/control/g1d_user_memory.c", "tests/kernel/control/run_g1d_user_memory_guest.py",
                 "tests/kernel/control/g1d_init.c", "tests/kernel/control/g1d_pids.c", "tests/kernel/control/run_g1d_guest.py",
                 "tests/kernel/control/run_g1c_guest.py", "support/build/prepare-trusted-image.py"):
        require(name in snapshot["files"], "untracked execution input")
    save_json(output / "source-before.json", snapshot)
    result.update(source_head=snapshot["head"], source_tree=snapshot["tree"], stage="compile_initial_elf")
    compiler = [args.cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-static", "-no-pie", "-pthread",
                "-Wl,-z,noexecstack,-z,separate-code", str(ROOT / "tests/kernel/control/g1d_user_memory.c"),
                "-o", str(output / "g1d-init")]
    built = subprocess.run(compiler, capture_output=True, timeout=90, check=False)
    (output / "compile.log").write_bytes(built.stdout + built.stderr)
    result.update(compiler_command=compiler, compile_exit=built.returncode)
    require(built.returncode == 0, "native probe compilation failed")
    probe = (output / "g1d-init").read_bytes()
    probe_info = control.inspect_probe_elf(probe)
    save_json(output / "probe.json", probe_info)
    target = args.target_dir.absolute()
    require(not target.exists() and not target.is_symlink(), "target must be fresh")
    require(not target.resolve().is_relative_to(ROOT.resolve()), "target must be outside source")
    build_dir = output / "kernel-build"
    env = dict(os.environ)
    for name in ("RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER",
                 "CARGO_TARGET_DIR", "HEPTA_TRUSTED_INITIAL_ELF", "HEPTA_G1C_TRUSTED_OBSERVE",
                 "HEPTA_G1D_TRUSTED_CONTROL", "FEATURES"):
        env.pop(name, None)
    env.update(A01_RUN_DIR=str(build_dir), A01_SMP="1", CARGO_TARGET_DIR=str(target),
               HEPTA_G1D_TRUSTED_CONTROL="1", HEPTA_TRUSTED_INITIAL_ELF=str(output / "g1d-init"))
    result.update(stage="build_profile", product_configuration="ActionChoice::Run; g1d-trusted-control; no --cfg ktest")
    save_json(output / "result.json", result)
    with (output / "build-wrapper.log").open("xb") as log:
        built = subprocess.run([str(ROOT / "support/build/kernel.sh"), "kernel"], cwd=ROOT, env=env,
                               stdout=log, stderr=subprocess.STDOUT, timeout=1800, check=False)
    result["build_wrapper_exit"] = built.returncode
    after = ordinary.source_snapshot(ROOT, args.expected_source_head, args.expected_source_tree)
    save_json(output / "source-after-build.json", after)
    require(after == snapshot and built.returncode == 0, "kernel build failed or source changed")
    kernel, original, lock_hash, manifest = control.verify_build(build_dir, snapshot, target, probe)
    bios = replay.read_pinned_file(args.bios, replay.SEABIOS_SHA, 2 * 1024 * 1024)
    binary = shutil.which(args.qemu)
    require(binary is not None, "QEMU unavailable")
    result.update(stage="guest", kernel_elf_sha256=digest(kernel), probe_sha256=digest(probe),
                  original_initramfs_sha256=digest(original), bios_sha256=digest(bios),
                  generated_lock_sha256=lock_hash, generated_package_count=204, trusted_manifest=manifest,
                  qemu_version=subprocess.check_output([binary, "--version"], text=True).strip(),
                  qemu_sha256=digest(Path(binary).read_bytes()))
    (output / "product-kernel.elf").write_bytes(kernel)
    (output / "bios.bin").write_bytes(bios)
    save_json(output / "result.json", result)
    raw, evidence = boot(args, output, kernel, bios, control.build_initramfs(original, probe), binary)
    verdict = evaluate(raw, evidence["qemu_exit"], evidence["timed_out"], probe_info, args.expect_no_limit)
    result["guest"] = {**evidence, **verdict}
    save_json(output / "exact/result.json", result["guest"])
    final = ordinary.source_snapshot(ROOT, args.expected_source_head, args.expected_source_tree)
    save_json(output / "source-after-guest.json", final)
    require(final == snapshot and (output / "g1d-init").read_bytes() == probe
            and (build_dir / "trusted-initial.elf").read_bytes() == probe
            and digest(Path(binary).read_bytes()) == result["qemu_sha256"], "execution inputs changed")
    result.update(stage="complete", passed=verdict["passed"], source_inputs_unchanged=True,
                  aggregate_user_frames=verdict["passed"] and not args.expect_no_limit,
                  native_recovery_under_capped_user_pressure=verdict["passed"] and not args.expect_no_limit)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-source-head", required=True)
    parser.add_argument("--expected-source-tree", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-dir", type=Path, required=True)
    parser.add_argument("--bios", type=Path, default=Path("/usr/share/seabios/bios-256k.bin"))
    parser.add_argument("--qemu", default="qemu-system-x86_64")
    parser.add_argument("--cc", default="cc")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--expect-no-limit", action="store_true")
    args = parser.parse_args(argv)
    require(1 <= args.timeout <= 600, "guest timeout must be 1..600 seconds")
    output = args.output.absolute()
    require(not output.exists() and not output.is_symlink(), "output must be new")
    require(not output.resolve().is_relative_to(ROOT.resolve()), "evidence must be outside source")
    output.mkdir(mode=0o700, parents=True)
    result = {"schema": "g1d.family-user-frames.v1", "stage": "source_admission", "passed": False,
              "counterfactual_only": args.expect_no_limit, "aggregate_user_frames": False,
              "native_recovery_under_capped_user_pressure": False, "memory_max": False,
              "global_physical_reserve": False, "oom_killer": False, "smp_qualification": False,
              "hardware_qualification": False, "hepta_durability": False, "production_ready": False}
    try:
        run(args, output, result)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        result.update(passed=False, error=f"{type(error).__name__}: {error}")
    save_json(output / "result.json", result)
    print(json.dumps({"passed": result["passed"], "stage": result["stage"], "output": str(output)}, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
