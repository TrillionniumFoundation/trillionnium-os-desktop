#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Build the current reviewed working bytes, boot, then run owned safety probes.

Development evidence only: a dirty worktree is explicitly recorded, never
represented as a committed or production-qualified artifact. CI may reuse an
existing exact-source ordinary product receipt without another kernel build. The guest has no
host disks or network. No probe is executed on the host.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / "network"))
sys.path.insert(0, str(HERE.parent / "control"))
from run_unix_stream_guest import run_qemu
from run_queryabi_guest import unpack, pack, BOOT_MARKER, require
import run_queryabi_candidate_guest as candidate

PROBES = ("commoncap", "socket_snapshot", "anon_budget", "dumpable_lifecycle", "ptrace_dumpable")
SOURCE_FILES = {name: [HERE / f"{name}_probe.c"] for name in PROBES}
SOURCE_FILES["dumpable_lifecycle"] = sorted((HERE / "lifecycle").glob("*.c"))
PROBE_ARGS = {"dumpable_lifecycle": " --reset-policy 0"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def snapshot():
    prefixes = ("kernel/asterinas/", "libs/", "support/build/", "tests/kernel/", "support/upstream-lock.json")
    names = subprocess.check_output(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT).split(b"\0")
    hashes = {}
    for raw in sorted(set(filter(None, names))):
        name = os.fsdecode(raw)
        if not name.startswith(prefixes):
            continue
        path = ROOT / name
        if path.is_symlink():
            hashes[name] = {"symlink": os.readlink(path)}
        elif path.is_file():
            hashes[name] = {"sha256": digest(path.read_bytes()), "executable": bool(path.stat().st_mode & 0o111)}
    return {"head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "kind": "development-working-bytes", "files": hashes}


def load_product(directory, head, tree):
    """Reuse only a successful ordinary build from this exact clean checkout."""
    receipt_bytes = (directory / "result.json").read_bytes()
    receipt = json.loads(receipt_bytes)
    require(receipt.get("schema") == "a06.g1-queryabi-product-candidate.v1", "unknown product receipt")
    require(receipt.get("passed") is True and receipt.get("source_inputs_unchanged") is True
            and receipt.get("stage") == "complete", "product build/guest receipt did not pass")
    require((receipt.get("source_head"), receipt.get("source_tree")) == (head, tree),
            "product source identity differs from this checkout")
    current = candidate.source_snapshot(ROOT, head, tree)
    for name in ("source-before.json", "source-after-boot.json", "source-after-guest.json"):
        require(json.loads((directory / name).read_text()) == current, "product source bytes differ")
    require(receipt.get("source_file_count") == len(current["files"]), "product source file count differs")
    boot = directory / "product-boot"
    qemu, artifacts, _ = candidate.verify_product_boot(boot, ROOT, current, Path(receipt["cargo_target_dir"]))
    require(digest((boot / "qemu.json").read_bytes()) == receipt["product_qemu_record_sha256"],
            "product boot receipt changed")
    for key, field in (("-kernel", "kernel_elf_sha256"), ("-initrd", "original_initramfs_sha256"),
                       ("-bios", "bios_sha256")):
        require(digest(artifacts[key]) == receipt[field], "product artifact digest differs")
    require((directory / "product-kernel.elf").read_bytes() == artifacts["-kernel"],
            "retained product ELF differs from the booted ELF")
    raw = (directory / "serial.log").read_bytes()
    verdict = candidate.evaluate_guest(raw, receipt["qemu_exit"], receipt["timed_out"])
    require(verdict["passed"] and digest(raw) == receipt["raw_serial_sha256"],
            "product QueryAbi guest evidence failed or changed")
    return artifacts, qemu["qemu_sha256"], {
        "source_kind": "committed-exact-source-product-reuse", "kernel_rebuilt": False,
        "product_evidence": str(directory), "product_receipt_sha256": digest(receipt_bytes),
        "product_source_head": head, "product_source_tree": tree,
        "original_initramfs_sha256": digest(artifacts["-initrd"]),
    }


def initramfs(original, binaries, nonce, smp):
    entries = unpack(gzip.decompress(original))
    script = b""
    for name in PROBES:
        script += (f"if /bin/safety-{name}{PROBE_ARGS.get(name, '')}; then safety_rc=0; else safety_rc=$?; fi\n"
                   f'echo "HEPTA_SAFETY nonce={nonce} probe={name} exit=$safety_rc"\n').encode()
    changed = 0
    for index, (name, fields, content) in enumerate(entries):
        if name.lstrip("./") == "init":
            require(content.count(BOOT_MARKER) == 1, "missing or ambiguous boot marker")
            require(content.count(b'test "$cpu_count" -eq 1') == 1, "missing original single-CPU check")
            entries[index] = (name, fields, content.replace(b'test "$cpu_count" -eq 1', f'test "$cpu_count" -eq {smp}'.encode()).replace(BOOT_MARKER, script + BOOT_MARKER))
            changed += 1
    require(changed == 1, "missing or ambiguous init")
    inode = max(entry[1][0] for entry in entries) + 1
    for name in PROBES:
        fields = [inode, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
        entries.append((f"bin/safety-{name}", fields, binaries[name]))
        inode += 1
    encoded = pack(entries)
    require([(name, data) for name, _, data in unpack(encoded)] == [(name, data) for name, _, data in entries],
            "initramfs roundtrip mismatch")
    return gzip.compress(encoded, mtime=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="new evidence directory")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--smp", type=int, choices=(1, 2, 4), default=1)
    parser.add_argument("--product-evidence", type=Path, help="reuse a verified exact-source ordinary product; no rebuild")
    parser.add_argument("--cc", default="gcc")
    parser.add_argument("--qemu", default="qemu-system-x86_64")
    parser.add_argument("--cpu", choices=("max", "max,-rdrand"), default="max",
                        help="fixed CPU profiles; the latter tests missing secure entropy")
    args = parser.parse_args()
    require(1 <= args.timeout <= 300, "guest timeout must be 1..300 seconds")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    before = snapshot()
    save(output / "source-before.json", before)
    result = {"passed": False, "production_qualified": False, "source_kind": before["kind"]}
    save(output / "result.json", result)
    binaries = {}
    for name in PROBES:
        argv = [args.cc, "-static", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread", *map(str, SOURCE_FILES[name]), "-o", str(output / name)]
        compiled = subprocess.run(argv, capture_output=True, timeout=60)
        (output / f"{name}-compile.log").write_bytes(compiled.stdout + compiled.stderr)
        if compiled.returncode:
            raise SystemExit(f"probe compile failed: {name}")
        binaries[name] = (output / name).read_bytes()
    expected_qemu_sha = None
    if args.product_evidence:
        tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip()
        artifacts, expected_qemu_sha, provenance = load_product(args.product_evidence.resolve(), before["head"], tree)
        result.update(provenance)
        save(output / "source-after-product-validation.json", snapshot())
    else:
        env = dict(os.environ)
        env.update(A01_RUN_DIR=str(output / "boot"), A01_QEMU_TIMEOUT="120", A01_SMP="1")
        for key in ("HEPTA_G1C_TRUSTED_OBSERVE", "HEPTA_G1D_TRUSTED_CONTROL", "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS"):
            env.pop(key, None)
        with (output / "build.log").open("w") as log:
            built = subprocess.run([str(ROOT / "support/build/kernel.sh"), "run_kernel"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        result["build_exit"] = built.returncode
        save(output / "result.json", result)
        if built.returncode:
            raise SystemExit("ordinary kernel build/boot failed; inspect build.log")
        after = snapshot()
        save(output / "source-after-build.json", after)
        if before != after:
            raise SystemExit("relevant source bytes changed during build")
        qemu = json.loads((output / "boot/qemu.json").read_text())
        original_argv = qemu["argv"]
        values = {key: original_argv[original_argv.index(key) + 1] for key in ("-kernel", "-initrd", "-bios")}
        cwd = Path(qemu["cwd"])
        artifacts = {key: (cwd / value).read_bytes() for key, value in values.items()}
        result["kernel_rebuilt"] = True
    nonce = secrets.token_hex(16)
    retained = {"kernel.elf": artifacts["-kernel"], "bios.bin": artifacts["-bios"],
                "initramfs.cpio.gz": initramfs(artifacts["-initrd"], binaries, nonce, args.smp)}
    for name, data in retained.items():
        (output / name).write_bytes(data)
    binary = shutil.which(args.qemu)
    require(binary is not None, "QEMU unavailable")
    qemu_sha = digest(Path(binary).read_bytes())
    require(expected_qemu_sha is None or qemu_sha == expected_qemu_sha, "QEMU differs from ordinary product boot")
    argv = [binary, "-kernel", str(output / "kernel.elf"), "-initrd", str(output / "initramfs.cpio.gz"),
            "-append", "earlycon console=ttyS0 loglevel=warn SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --",
            "-machine", "q35", "-accel", "tcg", "-cpu", args.cpu, "-bios", str(output / "bios.bin"),
            "-m", "512M", "-smp", str(args.smp), "-nodefaults", "-no-user-config", "-no-reboot", "-nographic",
            "-display", "none", "-monitor", "none", "-serial", "stdio", "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"]
    result.update(nonce=nonce, qemu_argv=argv, qemu_sha256=qemu_sha, artifact_sha256={name: digest(data) for name, data in retained.items()},
                  probe_sha256={name: digest(data) for name, data in binaries.items()})
    save(output / "result.json", result)
    raw, code, timeout, excessive, elapsed = run_qemu(argv, output, args.timeout)
    serial = raw.decode(errors="replace").replace("\r", "")
    markers = {name: serial.count(f"HEPTA_SAFETY nonce={nonce} probe={name} exit=0") == 1 for name in PROBES}
    final = snapshot()
    save(output / "source-after-guest.json", final)
    artifacts_unchanged = all((output / name).read_bytes() == data for name, data in retained.items())
    passed = artifacts_unchanged and code == 33 and not timeout and not excessive and all(markers.values()) and '"passed":false' not in serial and before == final
    result.update(passed=passed, qemu_exit=code, timed_out=timeout, excessive_output=excessive,
                  elapsed_seconds=elapsed, probe_passed=markers, serial_sha256=digest(raw), source_unchanged=before == final,
                  artifacts_unchanged=artifacts_unchanged)
    save(output / "result.json", result)
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
