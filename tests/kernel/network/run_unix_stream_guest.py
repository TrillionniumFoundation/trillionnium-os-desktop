#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Build an ordinary reviewed kernel and exercise real AF_UNIX system calls.

Every invocation requires a clean source head/tree, builds through the existing
ordinary product wrapper, and runs one bounded guest without host disks/network.
Qualification-only source mutations are pinned separately from production.
"""
import argparse
import gzip
import json
import os
from pathlib import Path
import re
import secrets
import selectors
import shutil
import stat
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "control"))
import unix_stream_oracle as oracle
import run_queryabi_candidate_guest as ordinary
import run_queryabi_guest as replay

require, digest, save = replay.require, replay.digest, ordinary.save_json
ENDPOINT = "kernel/asterinas/kernel/core/src/fs/utils/endpoint.rs"
CONNECTED = "kernel/asterinas/kernel/core/src/net/socket/unix/stream/connected.rs"
SOCKET = "kernel/asterinas/kernel/core/src/net/socket/unix/stream/socket.rs"
SOCKET_SHA = "3458b0b5a9023c26b396d73e61c13c69affcf98fe23c46fc4ca5793b75db1933"
ENDPOINT_SHA = "07e67a10fad1eb4cf84f56d37834e677da1ca03354cf22fb208e0d91ecb308ba"
CONNECTED_SHA = {
    "positive": "a331c8596416d56127eccd7beaa232dcb25bec5763648d322f6be5d697a904d3",
    "race-fixed": "aac591b80a071aeb14d7ad337f538c7906b7a03bd64fe9ba44e26d92c9891348",
    "race-stale": "b80f1157bb9cbcb513ff6231fa72693268741b34e2fd1763df34a627a5736b0e",
    "aux-zero-progress": "c578aa3d6d2a05bc78c8100b24b39343eb8c21d9cda580e1092e6114983581e4",
}
PROBE_SHA = "bb7e334a76c4e201b3ef33842be7f87a235a6940d783c8c741d63839519ab747"
ENV = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LANG": "C"}


def selection_valid(selection, variant):
    require(selection == "all" or selection in oracle.protocol()["cases"], "unknown case")
    require(variant in oracle.VARIANTS, "unknown source variant")
    if variant in ("race-fixed", "race-stale"):
        require(selection == "shutdown_race", "race control requires shutdown_race")
    if variant == "aux-zero-progress":
        require(selection == "credential_only", "auxiliary control requires credential_only")


def build_initramfs(original, probe, nonce, selection):
    require(re.fullmatch(r"[0-9a-f]{32}", nonce) is not None, "invalid nonce")
    require(selection == "all" or selection in oracle.protocol()["cases"], "unknown case")
    require(len(original) <= 8 * 1024 * 1024 and len(probe) <= 8 * 1024 * 1024,
            "initramfs or probe exceeds bound")
    unpacked = gzip.decompress(original)
    require(len(unpacked) <= 64 * 1024 * 1024, "uncompressed initramfs exceeds bound")
    entries = replay.unpack(unpacked)
    require(replay.unpack(replay.pack(entries)) == entries, "original cpio roundtrip mismatch")
    require(all(name.lstrip("./") != "bin/unix-stream-probe" for name, _, _ in entries),
            "probe already exists")
    case_arg = "" if selection == "all" else " " + selection
    script = (f"if /bin/unix-stream-probe {nonce}{case_arg}; then us_code=0; else us_code=$?; fi\n"
              f'echo "UNIX_STREAM_HARNESS nonce={nonce} selection={selection} exit=$us_code"\n').encode()
    modified, found = [], 0
    for name, fields, content in entries:
        if name.lstrip("./") == "init":
            require(stat.S_ISREG(fields[1]) and content.count(replay.BOOT_MARKER) == 1
                    and b"set -eu" in content, "ambiguous original init")
            content = content.replace(replay.BOOT_MARKER, script + replay.BOOT_MARKER)
            found += 1
        modified.append((name, fields, content))
    require(found == 1, "missing original init")
    fields = [max(item[1][0] for item in entries) + 1, 0o100755, 0, 0, 1, 0,
              0, 0, 0, 0, 0, 0, 0]
    modified.append(("bin/unix-stream-probe", fields, probe))
    packed = replay.pack(modified)
    decoded = replay.unpack(packed)
    require(len(decoded) == len(entries) + 1, "initramfs entry set changed")
    require([(name, data) for name, _, data in decoded] ==
            [(name, data) for name, _, data in modified], "initramfs contents changed")
    return gzip.compress(packed, mtime=0)


def run_qemu(argv, output, timeout):
    started, data = time.monotonic(), bytearray()
    timed_out, excessive = False, False
    with (output / "serial.log").open("xb") as log, subprocess.Popen(
        argv, env=ENV, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, start_new_session=True,
    ) as process:
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = timeout - (time.monotonic() - started)
                    if remaining <= 0:
                        timed_out = True
                        break
                    if not selector.select(min(0.2, remaining)):
                        continue
                    block = os.read(process.stdout.fileno(),
                                    min(16384, oracle.MAX_SERIAL_BYTES - len(data) + 1))
                    if not block:
                        break
                    log.write(block)
                    data.extend(block)
                    if len(data) > oracle.MAX_SERIAL_BYTES:
                        excessive = True
                        break
            if timed_out or excessive:
                process.kill()
            code = process.wait(timeout=10)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
    return bytes(data), code, timed_out, excessive, round(time.monotonic() - started, 3)


def execute(args, output, result):
    selection_valid(args.selection, args.variant)
    before = ordinary.source_snapshot(ROOT, args.expected_source_head, args.expected_source_tree)
    required = {ENDPOINT: ENDPOINT_SHA, CONNECTED: CONNECTED_SHA[args.variant],
                SOCKET: SOCKET_SHA,
                "tests/kernel/network/unix_stream_probe.c": PROBE_SHA,
                "tests/kernel/network/unix_stream_protocol.json": oracle.PROTOCOL_SHA256}
    for name, sha in required.items():
        require(before["files"].get(name, {}).get("sha256") == sha,
                "reviewed variant input mismatch: " + name)
    for name in ("run_unix_stream_guest.py", "unix_stream_oracle.py", "test_unix_stream_guest.py"):
        require("tests/kernel/network/" + name in before["files"], "untracked execution input")
    save(output / "source-before.json", before)
    result.update(source_head=before["head"], source_tree=before["tree"],
                  source_file_count=len(before["files"]), source_variant=args.variant,
                  source_variant_sha256=required, stage="ordinary_product_build_and_boot")
    boot = output / "product-boot"
    target = args.target_dir.absolute()
    require(not target.resolve().is_relative_to(ROOT.resolve()), "target must be outside source")
    env = dict(os.environ)
    for name in ("RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTC_WRAPPER",
                 "RUSTC_WORKSPACE_WRAPPER", "CARGO_TARGET_DIR"):
        env.pop(name, None)
    env.update(A01_RUN_DIR=str(boot), A01_SMP="1", A01_QEMU_TIMEOUT=str(args.boot_timeout),
               CARGO_TARGET_DIR=str(target))
    result.update(cargo_target_dir=str(target), product_configuration="ordinary ActionChoice::Run")
    save(output / "result.json", result)
    with (output / "product-wrapper.log").open("xb") as log:
        built = subprocess.run([str(ROOT / "support/build/kernel.sh"), "run_kernel"],
                               cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
    result["product_wrapper_exit"] = built.returncode
    after = ordinary.source_snapshot(ROOT, args.expected_source_head, args.expected_source_tree)
    save(output / "source-after-boot.json", after)
    require(before == after, "source changed during ordinary build")
    require(built.returncode == 0, "ordinary build/boot failed; original logs retained")
    qemu, artifacts, lock_hash = ordinary.verify_product_boot(boot, ROOT, before, target)
    result.update(product_boot_raw_exit=qemu["raw_exit_code"],
                  minimal_generated_lock_sha256=lock_hash, stage="compile_probe")
    cc = shutil.which(args.cc)
    require(cc is not None, "C compiler missing")
    command = [cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-static",
               str(HERE / "unix_stream_probe.c"), "-o", str(output / "unix-stream-probe")]
    compiled = subprocess.run(command, env=ENV, capture_output=True, timeout=60)
    (output / "compile.log").write_bytes(compiled.stdout + compiled.stderr)
    result.update(compiler_command=command, compiler_sha256=digest(Path(cc).read_bytes()),
                  compile_exit=compiled.returncode)
    require(compiled.returncode == 0, "static probe compile failed")
    probe = (output / "unix-stream-probe").read_bytes()
    require(probe[:6] == b"\x7fELF\x02\x01" and probe[18:20] == b"\x3e\x00", "wrong probe architecture")
    nonce = secrets.token_hex(16)
    initrd = build_initramfs(artifacts["-initrd"], probe, nonce, args.selection)
    inputs = {"product-kernel.elf": artifacts["-kernel"], "bios.bin": artifacts["-bios"],
              "initramfs.cpio.gz": initrd}
    for name, data in inputs.items():
        (output / name).write_bytes(data)
        (output / name).chmod(0o400)
    binary = shutil.which(args.qemu)
    require(binary is not None and digest(Path(binary).read_bytes()) == qemu["qemu_sha256"],
            "QEMU differs from ordinary build boot")
    argv = [binary, "-kernel", str(output / "product-kernel.elf"),
            "-initrd", str(output / "initramfs.cpio.gz"),
            "-append", "earlycon console=ttyS0 loglevel=warn SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --",
            "-machine", "q35", "-accel", "tcg", "-cpu", "max", "-bios", str(output / "bios.bin"),
            "-m", "512M", "-smp", "1", "-nodefaults", "-no-user-config", "-no-reboot",
            "-nographic", "-display", "none", "-monitor", "none", "-serial", "stdio",
            "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"]
    result.update(stage="unix_stream_guest", nonce=nonce, qemu_argv=argv,
                  qemu_sha256=qemu["qemu_sha256"], probe_sha256=digest(probe),
                  original_initramfs_sha256=digest(artifacts["-initrd"]),
                  boot_input_sha256={name: digest(data) for name, data in inputs.items()})
    save(output / "result.json", result)
    raw, code, timed_out, excessive, elapsed = run_qemu(argv, output, args.timeout)
    result.update(qemu_exit=code, timed_out=timed_out, excessive_output=excessive, elapsed_seconds=elapsed)
    evaluated = oracle.evaluate(raw, code, timed_out, excessive, nonce, args.selection, args.variant)
    result.update(oracle=evaluated, passed=evaluated["passed"])
    final = ordinary.source_snapshot(ROOT, args.expected_source_head, args.expected_source_tree)
    save(output / "source-after-guest.json", final)
    require(before == final, "source changed during syscall guest")
    require(all((output / name).read_bytes() == data for name, data in inputs.items()), "boot input changed")
    require((output / "unix-stream-probe").read_bytes() == probe, "compiled probe changed")
    result.update(stage="complete", source_inputs_unchanged=True, boot_inputs_unchanged=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-source-head", required=True)
    parser.add_argument("--expected-source-tree", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-dir", type=Path, required=True)
    parser.add_argument("--selection", default="all")
    parser.add_argument("--variant", choices=oracle.VARIANTS, default="positive")
    parser.add_argument("--cc", default="cc")
    parser.add_argument("--qemu", default="qemu-system-x86_64")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--boot-timeout", type=int, default=300)
    args = parser.parse_args(argv)
    require(1 <= args.timeout <= 120 and 1 <= args.boot_timeout <= 600, "invalid bounded timeout")
    output = args.output.absolute()
    require(not output.exists() and not output.is_symlink(), "output must be new")
    require(not output.resolve().is_relative_to(ROOT.resolve()), "evidence must be outside source")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    result = {"schema": "asterinas.unix-stream-qualification.v1", "stage": "source_admission",
              "passed": False, "native_authority_qualified": False, "hepta_lifecycle_qualified": False,
              "host_disks_or_network_attached": False}
    try:
        execute(args, output, result)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        result.update(passed=False, error=f"{type(error).__name__}: {error}")
    save(output / "result.json", result)
    print(json.dumps({"passed": result["passed"], "stage": result["stage"], "output": str(output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
