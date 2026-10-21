#!/usr/bin/env python3
"""Qualify native HOS2 management in three actual initial guest processes.

The manager and independent recovery process keep their original CPU domain;
only the workload is bound to the controlled leaf. The two altered-image boots
must fail before any of the three images or grants is committed. This is an
in-memory kernel history qualification, not Hepta disk durability or hardware.
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
import subprocess
import sys
import time
import tomllib

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_g1c_guest as observation
import run_queryabi_candidate_guest as ordinary
import run_queryabi_guest as replay

ROOT = Path(__file__).resolve().parents[3]
require = replay.require
digest = replay.digest
save_json = ordinary.save_json
inspect_probe_elf = observation.inspect_probe_elf
CAP_NS = 50_000_000
PERIOD_NS = 100_000_000
LEASE_NS = 300_000_000_000
COMPLETE = "G1D_COMPLETE native_manage=true history=true hepta_durability=false hardware=false"
MARKERS = (
    "G1D_WORKLOAD_NO_AUTHORITY", "G1D_RECOVERY_READY",
    "G1D_QUERYABI_OK supported_ops=62 max_request=40 max_response=64 features=0",
    "G1D_SAME_VALUE_NEW_D_PRESERVES_USAGE",
    "G1D_STALE_REVISION_TERMINAL sequence=4 saved_status=5",
    "G1D_STATIC_AND_GAP_DO_NOT_RESERVE next=5",
    "G1D_CEILING_REFUSAL_TERMINAL sequence=6 saved_status=2",
    "G1D_FORK_CHILD_NO_AUTHORITY", "G1D_FORK_SCM_NO_AUTHORITY",
    "G1D_SUBMICROSECOND_CAPS_EXACT cases=3",
    "G1D_PREFIX_RETIRED through=512 next=1026 old_D=retired manager_ack=denied",
    "G1D_MANAGER_EXEC_BEGIN sequence=1025",
    "G1D_RECOVERY_RETIRED_AFTER_MANAGER_EXEC through=1025 next=1026",
    "G1D_RECOVERY_STOPPED",
    "G1D_CHILDREN_REAPED workload_signal=15 recovery_exit=0", COMPLETE,
)
COMMITTED = re.compile(r"^\[hepta-g1d\] trusted initial image committed: bytes=([0-9]+) entry=0x([0-9a-f]+)$")
ROLE_COMMITTED = re.compile(r"^\[hepta-g1d\] trusted role committed: role=([123]) pid=([0-9]+)$")
ACTIVATED = re.compile(
    r"^\[hepta-g1d\] initial control activated: manager=([0-9]+) workload=([0-9]+) recovery=([0-9]+) "
    r"cap_ns=50000000 period_ns=100000000 lease_ns=300000000000 hepta_durability=false$"
)
BOOT = re.compile(r"^G1D_BOOT role=([123]) pid=([0-9]+) manager=([0-9]+) workload=([0-9]+) "
                  r"recovery=([0-9]+) version=2 bytes=192$")
APPLY_KEYS = ("role", "sequence", "cap", "previous", "revision", "effective", "consumed",
              "before_sample", "before_total", "before_start", "before_used",
              "after_sample", "after_total", "after_start", "after_used")
APPLY = re.compile(r"^G1D_APPLY " + " ".join(key + r"=([0-9]+)" for key in APPLY_KEYS) + r"$")
APPLY_CASES = ((1, 1, 25_000_000, 0), (1, 2, 25_000_000, 1), (1, 5, CAP_NS, 3),
               (1, 7, 0, 4), (3, 1, CAP_NS, 5), (1, 8, 1, 6), (1, 9, 999, 7),
               (1, 10, 1001, 8), (1, 11, CAP_NS, 9), (1, 1025, CAP_NS, 1023))
COPYOUT = re.compile(r"^G1D_COPYOUT_REPLAY sequence=3 errno=14 revision=([0-9]+) exact_bytes=true conflicts=2$")
ALIAS_KINDS = ("cpu_max", "migrate_into", "migrate_out", "disable_controller")
ALIAS = re.compile(r"^G1D_LEGACY_ALIAS_DENIED kind=([a-z_]+) errno=13$")
ZERO = re.compile(r"^G1D_ZERO_CAP_STOPPED sample_a=([0-9]+) sample_b=([0-9]+) total_a=([0-9]+) "
                  r"total_b=([0-9]+) heartbeat_a=([0-9]+) heartbeat_b=([0-9]+) revision=([0-9]+)$")
RECOVERY = re.compile(r"^G1D_INDEPENDENT_RECOVERY resumed_total=([0-9]+) revision=([0-9]+) own_sequence=1$")
FULL = re.compile(r"^G1D_FULL_WINDOW capacity=1024 refused_sequence=1025 old_results=retained revision=([0-9]+)$")
EXEC = re.compile(r"^G1D_EXEC_REVOKED old_fd_errno=116 no_auxv=true own_history=denied "
                  r"recovery_history=terminal sequence=1025$")
DYNAMIC = (BOOT, APPLY, COPYOUT, ALIAS, ZERO, RECOVERY, FULL, EXEC)


def build_initramfs(original, probe):
    require(len(original) <= 8 * 1024 * 1024 and len(probe) <= 8 * 1024 * 1024,
            "initial-image inputs exceed their bounds")
    unpacked = gzip.decompress(original)
    require(len(unpacked) <= 64 * 1024 * 1024, "uncompressed initramfs exceeds its bound")
    entries = replay.unpack(unpacked)
    require(replay.unpack(replay.pack(entries)) == entries, "base cpio roundtrip failed")
    require(sum(name.lstrip("./") == "test" and stat.S_ISDIR(fields[1]) for name, fields, _ in entries) == 1,
            "base image must contain exactly one test directory")
    require(all(name.lstrip("./") != "test/g1d-init" for name, _, _ in entries), "probe already exists")
    name = "test/g1d-init"
    fields = [max(fields[0] for _, fields, _ in entries) + 1, 0o100755, 0, 0, 1, 0,
              len(probe), 0, 0, 0, 0, len(name.encode()) + 1, 0]
    modified = [*entries, (name, fields, probe)]
    require(replay.unpack(replay.pack(modified)) == modified, "probe cpio roundtrip failed")
    return gzip.compress(replay.pack(modified), mtime=0)


def records(lines, pattern):
    return [(index, match) for index, line in enumerate(lines) if (match := pattern.fullmatch(line))]


def evaluate_positive(raw, code, timed_out, probe_info):
    require(len(raw) <= replay.MAX_SERIAL_BYTES, "G1-d serial exceeds evidence bound")
    text = ordinary.boot_check.ANSI.sub("", raw.decode(errors="replace"))
    lines = text.splitlines()
    counts = {marker: lines.count(marker) for marker in MARKERS}
    exact = all(count == 1 for count in counts.values())
    images, roles, activation = records(lines, COMMITTED), records(lines, ROLE_COMMITTED), records(lines, ACTIVATED)
    boots = records(lines, BOOT)
    pids = tuple(map(int, activation[0][1].groups())) if len(activation) == 1 else ()
    manifest_ok = (len(images) == 3 and len(roles) == 3 and len(pids) == 3
                   and pids[0] == 1 and 1 < pids[1] < 1 << 31 and 1 < pids[2] < 1 << 31
                   and len(set(pids)) == 3
                   and all(int(m[1]) == probe_info["bytes"] and int(m[2], 16) == probe_info["entry"] for _, m in images)
                   and tuple(int(m[1]) for _, m in roles) == (1, 2, 3)
                   and tuple(int(m[2]) for _, m in roles) == pids)
    bootstrap_ok = (manifest_ok and len(boots) == 3 and {int(m[1]) for _, m in boots} == {1, 2, 3}
                    and all(tuple(map(int, m.groups()[2:])) == pids and int(m[2]) == pids[int(m[1]) - 1]
                            for _, m in boots))
    activation_before_resume = (bootstrap_ok
        and all(images[i][0] < roles[i][0] for i in range(3))
        and max(index for index, _ in images + roles) < activation[0][0] < min(index for index, _ in boots))
    applied_records = records(lines, APPLY)
    applied = [dict(zip(APPLY_KEYS, map(int, match.groups()))) for _, match in applied_records]
    accounting_ok = len(applied) == len(APPLY_CASES)
    initial = applied[0]["previous"] if applied else 0
    previous = None
    for item, (role, sequence, cap, offset) in zip(applied, APPLY_CASES):
        accounting_ok &= (all(0 <= value < 1 << 64 for value in item.values())
                          and initial > 0 and item["role"] == role and item["sequence"] == sequence
                          and item["cap"] == cap and item["previous"] == initial + offset
                          and item["revision"] == item["previous"] + 1
                          and 0 < item["before_sample"] <= item["effective"] <= item["after_sample"]
                          and item["consumed"] <= item["effective"] % PERIOD_NS
                          and item["after_total"] >= item["before_total"])
        for prefix in ("before", "after"):
            sample, total, start, used = (item[prefix + "_" + key] for key in ("sample", "total", "start", "used"))
            accounting_ok &= (start == sample // PERIOD_NS * PERIOD_NS
                              and 0 <= used <= total <= sample and used <= sample % PERIOD_NS
                              and total - used <= start)
        effective_window = item["effective"] // PERIOD_NS * PERIOD_NS
        if effective_window == item["before_start"]:
            accounting_ok &= item["consumed"] >= item["before_used"]
        if effective_window == item["after_start"]:
            accounting_ok &= item["after_used"] >= item["consumed"]
        if previous:
            accounting_ok &= (item["before_sample"] >= previous["after_sample"]
                              and item["before_total"] >= previous["after_total"])
            if item["before_start"] == previous["after_start"]:
                accounting_ok &= item["before_used"] >= previous["after_used"]
        previous = item
    copyout, aliases, zero = records(lines, COPYOUT), records(lines, ALIAS), records(lines, ZERO)
    recovery, full, executed = records(lines, RECOVERY), records(lines, FULL), records(lines, EXEC)
    retry_ok = len(copyout) == 1 and int(copyout[0][1][1]) == initial + 3
    aliases_ok = tuple(m[1] for _, m in aliases) == ALIAS_KINDS
    history_ok = len(full) == 1 and int(full[0][1][1]) == initial + 1023 and len(executed) == 1
    stopped = resumed = False
    if len(zero) == len(recovery) == 1 and accounting_ok:
        sample_a, sample_b, total_a, total_b, heart_a, heart_b, revision = map(int, zero[0][1].groups())
        total, recovery_revision = map(int, recovery[0][1].groups())
        stopped = (all(0 <= value < 1 << 64 for value in (sample_a, sample_b, total_a, total_b, heart_a, heart_b, revision))
                   and sample_b >= sample_a + 2 * PERIOD_NS and total_a == total_b <= sample_a
                   and heart_a == heart_b > 0 and revision == initial + 5
                   and sample_a >= applied[3]["after_sample"] and total_a >= applied[3]["after_total"]
                   and sample_b <= applied[4]["before_sample"] and total_b == applied[4]["before_total"])
        resumed = (0 < total < 1 << 64 and total > total_b and total >= applied[4]["after_total"]
                   and total <= applied[5]["before_total"] and recovery_revision == initial + 6)
    # Only actual manager actions are globally ordered. The three independently
    # scheduled initial processes may print their boot/readiness records in any order.
    ordered = False
    if exact and accounting_ok and retry_ok and aliases_ok and history_ok and len(zero) == len(recovery) == 1:
        marker = lambda index: lines.index(MARKERS[index])
        action = lambda index: applied_records[index][0]
        steps = [marker(2), action(0), action(1), marker(3), copyout[0][0], marker(4), marker(5),
                 action(2), marker(6), marker(7), marker(8), *[index for index, _ in aliases], action(3),
                 zero[0][0], action(4), recovery[0][0], action(5), action(6), action(7), action(8),
                 marker(9), full[0][0], action(9), marker(10), marker(11), executed[0][0], marker(12),
                 marker(13), marker(14), marker(15)]
        ordered = all(left < right for left, right in zip(steps, steps[1:]))
        if bootstrap_ok:
            boot_indices = {int(m[1]): index for index, m in boots}
            ordered &= (boot_indices[1] < marker(2) and boot_indices[2] < marker(0) < marker(2)
                        and boot_indices[3] < marker(1) < action(4))
    known = set(MARKERS)
    unexpected = [line for line in lines if line.startswith("G1D_") and line not in known
                  and not any(pattern.fullmatch(line) for pattern in DYNAMIC)]
    unknown_kernel = [line for line in lines if line.startswith("[hepta-g1d]")
                      and not any(pattern.fullmatch(line) for pattern in (COMMITTED, ROLE_COMMITTED, ACTIVATED))]
    no_failure = (not unexpected and not unknown_kernel and "rejected initial image" not in text
                  and not any(marker in text for marker in (*ordinary.boot_check.FATAL_PANICS, "Kernel panic"))
                  and not any(line.startswith("G1D_FAIL") for line in lines))
    passed = (type(code) is int and code == 33 and timed_out is False and exact and activation_before_resume
              and accounting_ok and retry_ok and aliases_ok and history_ok and stopped and resumed and ordered and no_failure)
    return {"passed": bool(passed), "marker_counts": counts, "three_private_bootstraps": bool(bootstrap_ok),
            "manifest_verified_before_any_resume": bool(activation_before_resume), "role_pids": list(pids),
            "apply_records": applied, "initial_revision": initial, "native_accounting_preserved": bool(accounting_ok),
            "copyout_replay_exact": bool(retry_ok), "legacy_aliases_denied": aliases_ok,
            "zero_budget_stops_real_workload": bool(stopped), "independent_recovery_resumes_workload": bool(resumed),
            "full_window_and_exec_history": bool(history_ok), "manager_actions_ordered": bool(ordered),
            "no_failure": no_failure, "unexpected_records": unexpected + unknown_kernel,
            "raw_serial_sha256": digest(raw), "raw_serial_size": len(raw)}


def evaluate_rejection(raw, code, timed_out, reason):
    require(reason in ("manifest-byte-mismatch", "truncated-snapshot"), "unknown negative control")
    require(len(raw) <= replay.MAX_SERIAL_BYTES, "G1-d rejection serial exceeds evidence bound")
    text = ordinary.boot_check.ANSI.sub("", raw.decode(errors="replace"))
    lines = text.splitlines()
    expected = f"[hepta-g1d] rejected initial image: {reason}"
    rejected = lines.count(expected) == 1 and sum("rejected initial image:" in line for line in lines) == 1
    no_resume = not any("trusted initial image committed:" in line or "trusted role committed:" in line
                        or "initial control activated:" in line or "initial observe activated:" in line
                        or line.startswith(("G1D_", "G1C_")) for line in lines)
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
                "INITRAMFS=on", "AUTO_TEST=none", "HEPTA_G1D_TRUSTED_CONTROL=1", "FEATURES=g1d-trusted-control",
                f"A01_INITRAMFS={directory / 'initramfs.cpio.gz'}",
                f"A01_QEMU_WRAPPER={ROOT / 'support/build/record-qemu.py'}"}
    require(command[:8] == expected and len(command) == 20 and command[8].startswith("CARGO_OSDK=")
            and set(command[9:]) == required, "unexpected G1-d product build arguments")
    require("--features=g1d-trusted-control" in (directory / "kernel.log").read_text(),
            "actual OSDK invocation did not include the explicit profile")
    source = subprocess.check_output([sys.executable, "-I", str(ROOT / "support/build/verify-source.py")], cwd=ROOT)
    require(json.loads(source) == json.loads((directory / "source-inputs.json").read_text()), "source-input gate differs")
    fixed = ROOT / "support/build/minimal/Cargo.lock"
    generated = target / "osdk/asterinas-run-base/Cargo.lock"
    require(generated.read_bytes() == fixed.read_bytes() and len(tomllib.loads(generated.read_text())["package"]) == 204,
            "G1-d generated package lock differs from the fixed 204-package product")
    embedded = directory / "trusted-initial.elf"
    require(embedded.read_bytes() == probe and stat.S_IMODE(embedded.stat().st_mode) == 0o444,
            "embedded trusted image differs from the frozen compiled probe")
    manifest = json.loads((directory / "trusted-initial-manifest.json").read_text())
    expected_manifest = {"schema": "hepta-g1d-trusted-initial-v1", "profile": "g1d-trusted-control",
                         "embedded_input": str(embedded), "bytes": len(probe), "sha256": digest(probe),
                         "supported_ops": 62, "features": 0, "bootstrap_version": 2, "bootstrap_bytes": 192,
                         "roles": ["manager", "workload", "recovery"],
                         "cap_ns": CAP_NS, "period_ns": PERIOD_NS, "lease_ns": LEASE_NS}
    require(set(manifest) == set(expected_manifest) | {"source"}
            and all(manifest.get(key) == value for key, value in expected_manifest.items()), "trusted build manifest differs")
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
            "-append", "earlycon console=ttyS0 loglevel=info rdinit=/test/g1d-init SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --",
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
    (output / "git-status-porcelain.txt").write_bytes(subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT))
    snapshot = ordinary.source_snapshot(ROOT, args.expected_source_head, args.expected_source_tree)
    for name in ("tests/kernel/control/g1d_init.c", "tests/kernel/control/run_g1d_guest.py",
                 "tests/kernel/control/run_g1c_guest.py", "support/build/prepare-trusted-image.py"):
        require(name in snapshot["files"], "untracked execution input")
    save_json(output / "source-before.json", snapshot)
    result.update(source_head=snapshot["head"], source_tree=snapshot["tree"], source_file_count=len(snapshot["files"]),
                  stage="compile_actual_initial_elf")
    compiler = [args.cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-static", "-no-pie",
                "-Wl,-z,noexecstack,-z,separate-code", str(ROOT / "tests/kernel/control/g1d_init.c"),
                "-o", str(output / "g1d-init")]
    built = subprocess.run(compiler, capture_output=True, timeout=90, check=False)
    (output / "compile.log").write_bytes(built.stdout + built.stderr)
    result.update(compiler_command=compiler, compile_exit=built.returncode)
    require(built.returncode == 0, "static trusted initial ELF compilation failed")
    probe = (output / "g1d-init").read_bytes()
    probe_info = inspect_probe_elf(probe)
    save_json(output / "probe.json", probe_info)
    target = args.target_dir.absolute()
    require(not target.exists() and not target.is_symlink(), "G1-d target must be fresh")
    require(not target.resolve().is_relative_to(ROOT.resolve()), "G1-d target must be outside source")
    build_dir = output / "kernel-build"
    env = dict(os.environ)
    for name in ("RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER",
                 "CARGO_TARGET_DIR", "HEPTA_TRUSTED_INITIAL_ELF", "HEPTA_G1C_TRUSTED_OBSERVE",
                 "HEPTA_G1D_TRUSTED_CONTROL", "FEATURES"):
        env.pop(name, None)
    env.update(A01_RUN_DIR=str(build_dir), A01_SMP="1", CARGO_TARGET_DIR=str(target),
               HEPTA_G1D_TRUSTED_CONTROL="1", HEPTA_TRUSTED_INITIAL_ELF=str(output / "g1d-init"))
    result.update(stage="build_explicit_profile", product_configuration="ActionChoice::Run; g1d-trusted-control; no --cfg ktest")
    save_json(output / "result.json", result)
    with (output / "build-wrapper.log").open("xb") as log:
        built = subprocess.run([str(ROOT / "support/build/kernel.sh"), "kernel"], env=env, cwd=ROOT,
                               stdout=log, stderr=subprocess.STDOUT, check=False)
    result["build_wrapper_exit"] = built.returncode
    after = ordinary.source_snapshot(ROOT, args.expected_source_head, args.expected_source_tree)
    save_json(output / "source-after-build.json", after)
    require(snapshot == after, "tracked source changed during G1-d build")
    require(built.returncode == 0, "G1-d kernel build failed; original logs retained")
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
    require(final == snapshot and (output / "g1d-init").read_bytes() == probe
            and (build_dir / "trusted-initial.elf").read_bytes() == probe, "source or embedded manifest changed between controls")
    require(digest(Path(binary).read_bytes()) == result["qemu_sha256"], "QEMU changed between profiles")
    result.update(stage="complete", source_inputs_unchanged=True, same_kernel_for_all_controls=True,
                  passed=all(guest["passed"] for guest in guests.values()))
    if result["passed"]:
        result.update(native_manage=True, native_history=True, three_initial_processes=True,
                      legacy_linux_management_isolated=True, history_retirement="original_memory_owner")


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
    result = {"schema": "a06.g1d-trusted-initial-control.v1", "stage": "source_admission", "passed": False,
              "profile": "g1d-trusted-control", "native_manage": False, "native_history": False,
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
