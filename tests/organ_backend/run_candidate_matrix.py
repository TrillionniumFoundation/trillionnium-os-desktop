#!/usr/bin/env python3
"""Replay a pinned Asterinas *candidate* in an isolated one-vCPU QEMU.

Unlike run_guest_probe.py's known-bad A01 reference, this intentionally
requires a caller-supplied, separately hashed kernel. No host cgroup writes,
no data disk, no networking, no system service changes. The guest initramfs
and probe are generated entirely inside the requested new output directory.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess

import sys

# Keep sibling imports stable if this runner is invoked from an isolated
# subprocess or a different working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_guest_probe import pack, unpack

REF_INITRD = "86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3"
REF_MARKER = "e884f5e50cf296833276016894a39337cd9ac13bc51f6b1f2dea3cc3a6904b63"
BIOS_SHA = "1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def checked_replace(src, old, new):
    if src.count(old) != 1:
        raise ValueError("expected exactly one source marker: " + repr(old[:90]))
    return src.replace(old, new)


def variant(source, mode, quota, duration_seconds=1):
    source = checked_replace(source, REF_MARKER, "__KERNEL_SHA__")
    source = checked_replace(source,
        "while (end - start < UINT64_C(1000000000))",
        "while (end - start < UINT64_C(" + str(duration_seconds * 1_000_000_000) + "))"
    )
    source = checked_replace(
        source, 'put(path,"1000 100000\\n");',
        'put(path,"' + str(quota) + ' 100000\\n");'
    )
    source = checked_replace(
        source, 'quota!=1000 || period!=100000',
        'quota!=' + str(quota) + ' || period!=100000'
    )
    if mode == "rt":
        source = checked_replace(source, "#include <errno.h>", "#include <errno.h>\n#include <sched.h>")
        key = '    snprintf(path,sizeof path,"%s/cpu.stat",group);read_text(path,buf,sizeof buf);'
        source = checked_replace(
            source, key,
            '    struct sched_param sp = {.sched_priority=1};\n'
            '    if (sched_setscheduler(0,SCHED_FIFO,&sp) != 0) fail("sched_setscheduler");\n'
            '    printf("ORGAN_POLICY=RT_FIFO\\n");\n' + key
        )
    elif mode == "parent":
        source = checked_replace(
            source, "char buf[4096], path[256], group[192], pid[32];",
            "char buf[4096], path[512], group[256], pid[32];",
        )
        key = (
            '    snprintf(group,sizeof group,"/sys/fs/cgroup/organ-audit-%ld",(long)getpid());\n'
            '    if (mkdir(group,0755) != 0) fail("mkdir-cgroup");\n'
            '    snprintf(path,sizeof path,"%s/cpu.max",group);'
            'put(path,"' + str(quota) + ' 100000\\n");'
        )
        source = checked_replace(
            source, key,
            '    char parent[192];\n'
            '    snprintf(parent,sizeof parent,"/sys/fs/cgroup/organ-parent-%ld",(long)getpid());\n'
            '    if (mkdir(parent,0755) != 0) fail("mkdir-parent");\n'
            '    snprintf(path,sizeof path,"%s/cpu.max",parent);put(path,"' + str(quota) + ' 100000\\n");\n'
            '    snprintf(path,sizeof path,"%s/cgroup.subtree_control",parent);put(path,"+cpu\\n");\n'
            '    snprintf(group,sizeof group,"%s/leaf",parent);\n'
            '    if (mkdir(group,0755) != 0) fail("mkdir-leaf");\n'
            '    snprintf(path,sizeof path,"%s/cpu.max",parent);'
        )
    return source


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--a01-tree", type=Path, required=True)
    ap.add_argument("--kernel", type=Path, required=True)
    ap.add_argument("--expected-sha256", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--quota-us", type=int, default=10000)
    ap.add_argument("--mode", choices=("leaf", "parent", "rt"), default="leaf")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--duration-seconds", type=int, default=1,
                    help="bounded CPU sample duration in the guest (1..10 seconds)")
    ap.add_argument("--max-cpu-percent", type=float, default=None,
                    help="optional explicit guest CPU percentage bound; report-only when absent")
    ap.add_argument("--bios", type=Path, default=Path("/usr/share/seabios/bios-256k.bin"))
    args = ap.parse_args()
    if not 1000 <= args.quota_us <= 100000 or not 1 <= args.repeat <= 10:
        ap.error("quota must be 1000..100000us, repeat 1..10")
    if args.max_cpu_percent is not None and not 0 < args.max_cpu_percent <= 100:
        ap.error("max CPU percentage must be within (0,100]")
    if not 1 <= args.duration_seconds <= 10:
        ap.error("duration seconds must be 1..10")
    if not re.fullmatch(r"[0-9a-f]{64}", args.expected_sha256):
        ap.error("expected SHA-256 must be exactly 64 lowercase hex digits")
    raw_kernel = args.kernel.read_bytes()
    if digest(raw_kernel) != args.expected_sha256:
        raise ValueError("candidate ELF SHA mismatch")
    if digest(args.bios.read_bytes()) != BIOS_SHA:
        raise ValueError("SeaBIOS SHA mismatch")
    initrd_ref = args.a01_tree / "support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz"
    initial = initrd_ref.read_bytes()
    if digest(initial) != REF_INITRD:
        raise ValueError("reference initramfs SHA mismatch")
    source = variant(Path(__file__).with_name("cpu_cap_probe.c").read_text(), args.mode,
                     args.quota_us, args.duration_seconds)
    source = checked_replace(source, "__KERNEL_SHA__", args.expected_sha256)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / "candidate_kernel.sha256").write_text(args.expected_sha256 + "\n")
    (out / "probe.c").write_text(source)
    binary = out / "probe"
    cmd = ["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
           "-static", str(out / "probe.c"), "-o", str(binary)]
    compile_run = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    (out / "compile.log").write_text(compile_run.stdout + compile_run.stderr)
    if compile_run.returncode:
        raise RuntimeError("probe compile failed; inspect compile.log")
    entries = unpack(gzip.decompress(initial))
    marker = b'echo "TRILLIONNIUM_A01_BOOT_OK"'
    changed = 0
    result_entries = []
    for name, fields, data in entries:
        if name.lstrip("./") == "init":
            if data.count(marker) != 1:
                raise ValueError("unexpected init script")
            data = data.replace(marker, b'/bin/cpu-cap-probe --asterinas-disposable-guest\n' + marker)
            changed += 1
        result_entries.append((name, fields, data))
    if changed != 1:
        raise ValueError("init script not found")
    inode = max(row[1][0] for row in result_entries)
    result_entries.append(("bin/cpu-cap-probe", [inode + 1, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0], binary.read_bytes()))
    result_entries.append((".hepta-disposable-guest", [inode + 2, 0o100400, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0], (args.expected_sha256 + "\n").encode()))
    archive = out / "initramfs.cpio.gz"
    archive.write_bytes(gzip.compress(pack(result_entries), mtime=0))
    qemu = [
        "qemu-system-x86_64", "-kernel", str(args.kernel.resolve()),
        "-initrd", str(archive), "-append",
        "earlycon console=ttyS0 loglevel=info SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --",
        "-machine", "q35", "-accel", "tcg", "-cpu", "max",
        "-bios", str(args.bios), "-m", "512M", "-smp", "1",
        "-nodefaults", "-no-user-config", "-no-reboot", "-nographic",
        "-display", "none", "-monitor", "none", "-serial", "stdio",
        "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04",
    ]
    runs = []
    for index in range(1, args.repeat + 1):
        try:
            p = subprocess.run(qemu, capture_output=True, text=True, timeout=45)
            output, code = p.stdout + p.stderr, p.returncode
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or b"").decode(errors="replace") + (exc.stderr or b"").decode(errors="replace")
            code = 124
        (out / f"serial-{index}.log").write_text(output)
        clean = re.sub(r"\x1b\[[0-9;]*m", "", output)
        matches = re.findall(
            r"ORGAN_CPU_SAMPLE label=(\S+) wall_ns=(\d+) cpu_ns=(\d+) iterations=(\d+)",
            clean,
        )
        samples = [
            {"label": a, "wall_ns": int(b), "cpu_ns": int(c), "iterations": int(d)}
            for a, b, c, d in matches
        ]
        percent = round(samples[-1]["cpu_ns"] * 100 / samples[-1]["wall_ns"], 3) if len(samples) == 2 else None
        run = {
            "index": index, "qemu_exit": code, "guest_complete": "ORGAN_PROBE_COMPLETE" in clean,
            "panic": "panicked at" in clean, "policy_rt": "ORGAN_POLICY=RT_FIFO" in clean,
            "cpu_percent": percent, "samples": samples,
        }
        runs.append(run)
        print(json.dumps({k: v for k, v in run.items() if k != "samples"}), flush=True)
        if code != 33 or not run["guest_complete"]:
            break
    report = {
        "mode": args.mode, "quota_us": args.quota_us, "period_us": 100000,
        "duration_seconds": args.duration_seconds,
        "max_cpu_percent": args.max_cpu_percent,
        "candidate_sha256": args.expected_sha256, "initramfs_sha256": digest(archive.read_bytes()),
        "source_pin": REF_INITRD, "host_cgroup_modified": False, "guest_only": True,
        "smp_qualified": False, "hepta_hos2_qualified": False, "runs": runs,
    }
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    # Guest completion is not resource qualification. Callers must explicitly
    # supply a bound when they intend to use exit 0 as a bandwidth guard.
    guest_ok = len(runs) == args.repeat and all(
        x["qemu_exit"] == 33 and x["guest_complete"] and not x["panic"] for x in runs
    )
    if args.max_cpu_percent is not None:
        guest_ok = guest_ok and all(
            x["cpu_percent"] is not None and x["cpu_percent"] <= args.max_cpu_percent
            for x in runs
        )
    return 0 if guest_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
