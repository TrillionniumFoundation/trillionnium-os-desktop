#!/usr/bin/env python3
"""Build/boot one reviewed G1 product candidate, then run the real QueryAbi probe.

The historical A05 pinned replay remains unchanged. This entry point requires a
clean reviewed Git head/tree, snapshots every tracked byte, invokes the existing
ordinary build wrapper, and binds both guests to that same product ELF. It does
not establish native grants, successful resource effects, Hepta or SMP support.
"""
import argparse
import hashlib
import importlib.util
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
import run_queryabi_guest as replay

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("product_boot_check", ROOT / "support/build/check-boot.py")
boot_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boot_check)
OP_MARKERS = (
    "HEPTA_DISABLED_READ_USAGE_OK", "HEPTA_DISABLED_INSTALL_BUDGET_OK",
    "HEPTA_DISABLED_QUERY_DELIVERY_OK", "HEPTA_DISABLED_RETIRE_THROUGH_OK",
)
CANDIDATE_MARKER = "HEPTA_QUERYABI_CANDIDATE_OK disabled_operations=4"
FINAL_BOOT_MARKER = "TRILLIONNIUM_A01_BOOT_OK"
MAX_KERNEL_BYTES = 256 * 1024 * 1024
require = replay.require


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def source_snapshot(root, head, tree):
    """Check actual bytes and Git modes, including symlinks, against the index."""
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root)
    require(re.fullmatch(r"[0-9a-f]{40}", head) is not None, "invalid reviewed source head")
    require(re.fullmatch(r"[0-9a-f]{40}", tree) is not None, "invalid reviewed source tree")
    require(git("rev-parse", "HEAD").decode().strip() == head, "reviewed source head mismatch")
    require(git("rev-parse", "HEAD^{tree}").decode().strip() == tree, "reviewed source tree mismatch")
    require(not git("status", "--porcelain", "--untracked-files=all"), "source checkout is dirty or has untracked inputs")
    files = {}
    for entry in filter(None, git("ls-files", "-s", "-z").split(b"\0")):
        meta, raw_name = entry.split(b"\t", 1)
        mode, blob, stage = meta.decode().split()
        name = os.fsdecode(raw_name)
        path = root / name
        require(stage == "0" and mode in ("100644", "100755", "120000"), "unsupported Git input")
        info = path.lstat()
        if mode == "120000":
            require(stat.S_ISLNK(info.st_mode), "source symlink mode mismatch")
            data = os.fsencode(os.readlink(path))
        else:
            require(stat.S_ISREG(info.st_mode), "source is not a regular file")
            actual_mode = "100755" if info.st_mode & 0o111 else "100644"
            require(actual_mode == mode, "source executable mode mismatch")
            data = path.read_bytes()
        actual_blob = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
        require(actual_blob == blob, f"tracked source byte mismatch: {name}")
        files[name] = {"mode": mode, "git_blob": blob, "size": len(data), "sha256": replay.digest(data)}
    return {"schema": "a06.g1-source-snapshot.v1", "root": str(root), "head": head, "tree": tree, "files": files}


def verify_n0_argv(argv):
    pairs, flags = {}, set()
    allowed = {"-kernel", "-initrd", "-append", "-machine", "-accel", "-cpu", "-bios",
               "-m", "-smp", "-display", "-monitor", "-chardev", "-serial", "-device"}
    allowed_flags = {"-nodefaults", "-no-user-config", "-no-reboot", "-nographic"}
    require(isinstance(argv, list) and argv and all(isinstance(a, str) for a in argv), "bad QEMU argv")
    index = 1
    while index < len(argv):
        option = argv[index]
        if option in allowed_flags:
            require(option not in flags, "duplicate QEMU flag")
            flags.add(option)
            index += 1
        else:
            require(option in allowed and option not in pairs and index + 1 < len(argv), "unexpected QEMU option")
            pairs[option] = argv[index + 1]
            index += 2
    require(set(pairs) == allowed and flags == allowed_flags, "incomplete N0 QEMU profile")
    expected = {"-machine": "q35", "-accel": "tcg", "-cpu": "max", "-m": "512M", "-smp": "1",
                "-display": "none", "-monitor": "none", "-serial": "chardev:serial",
                "-chardev": "stdio,id=serial,signal=off,logfile=qemu.log",
                "-device": "isa-debug-exit,iobase=0xf4,iosize=0x04"}
    require(all(pairs[k] == v for k, v in expected.items()), "N0 CPU/firmware/transport profile drift")
    return pairs


def verify_product_boot(directory, root, snapshot, target_dir):
    boot_check.check_boot(directory, live_artifacts=True)
    for name in ("make-exit-code.txt", "log-exit-code.txt", "run-exit-code.txt"):
        require((directory / name).read_text().strip() == "0", f"product stage failed: {name}")
    qemu = json.loads((directory / "qemu.json").read_text())
    pairs = verify_n0_argv(qemu["argv"])
    require((directory / "environment.log").read_text().splitlines().count(snapshot["head"]) == 1,
            "ordinary build environment did not record this source head")
    command = shlex.split((directory / "command.sh").read_text())
    expected_prefix = ["make", "-C", str(root / "kernel/asterinas"), "-f", "Makefile",
                       "-f", str(root / "support/build/minimal.mk"), "run_kernel"]
    require(command[:8] == expected_prefix, "not the ordinary product build entry point")
    required_make = {"TARGET_ARCH=x86_64", "SMP=1", "MEM=512M", "ENABLE_KVM=0",
                     "BOOT_PROTOCOL=multiboot", "INITRAMFS=on", "AUTO_TEST=none",
                     f"A01_INITRAMFS={directory / 'initramfs.cpio.gz'}",
                     f"A01_QEMU_WRAPPER={root / 'support/build/record-qemu.py'}"}
    require(set(command[9:]) == required_make and len(command) == 18
            and command[8].startswith("CARGO_OSDK="), "ordinary build arguments drifted")
    source_gate = subprocess.check_output([sys.executable, "-I", str(root / "support/build/verify-source.py")], cwd=root)
    require(json.loads(source_gate) == json.loads((directory / "source-inputs.json").read_text()),
            "ordinary boot source-input gate mismatch")
    generated = target_dir / "osdk/asterinas-run-base/Cargo.lock"
    require(generated.read_bytes() == (root / "support/build/minimal/Cargo.lock").read_bytes(),
            "ordinary generated lock differs from the fixed minimal lock")
    require(len(tomllib.loads(generated.read_text())["package"]) == 204, "ordinary G1 product lock is not 204 packages")
    artifacts = {}
    for option, limit in (("-kernel", MAX_KERNEL_BYTES), ("-initrd", 8 * 1024 * 1024), ("-bios", 2 * 1024 * 1024)):
        record = qemu["artifacts"][option]
        path = Path(record["path"])
        if not path.is_absolute():
            path = Path(qemu["cwd"]) / path
        require(path.resolve() == Path(pairs[option]).resolve(), "QEMU argv/artifact path mismatch")
        data = replay.read_pinned_file(path, record["sha256"], limit)
        require(len(data) == record["size"], "QEMU artifact size mismatch")
        artifacts[option] = data
    require(Path(pairs["-initrd"]).resolve() == (directory / "initramfs.cpio.gz").resolve(), "boot initramfs mismatch")
    require(replay.digest(artifacts["-bios"]) == replay.SEABIOS_SHA, "fixed SeaBIOS changed")
    kernel = artifacts["-kernel"]
    require(kernel[:6] == b"\x7fELF\x02\x01" and kernel[18:20] == b"\x03\x00",
            "not the x86_64 product's QEMU multiboot ELF with converted EM_386 header")
    return qemu, artifacts, replay.digest(generated.read_bytes())


def evaluate_guest(raw, code, timed_out):
    require(len(raw) <= replay.MAX_SERIAL_BYTES, "candidate serial exceeds evidence limit")
    text = boot_check.ANSI.sub("", raw.decode(errors="replace"))
    lines = text.splitlines()
    markers = (*replay.REQUIRED_SECURITY_MARKERS, *OP_MARKERS,
               replay.EXPECTED_SUCCESS, CANDIDATE_MARKER, FINAL_BOOT_MARKER)
    counts = {marker: lines.count(marker) for marker in markers}
    order = (replay.EXPECTED_SUCCESS, *OP_MARKERS, CANDIDATE_MARKER, FINAL_BOOT_MARKER)
    exact = all(value == 1 for value in counts.values())
    ordered = exact and [lines.index(m) for m in order] == sorted(lines.index(m) for m in order)
    no_fail = not any(marker in text for marker in (*boot_check.FATAL_PANICS, "Kernel panic", "HEPTA_QUERYABI_FAIL"))
    return {"marker_counts": counts, "exact_one_markers": exact, "ordered_root_completion": ordered,
            "no_guest_failure": no_fail, "raw_serial_sha256": replay.digest(raw), "raw_serial_size": len(raw),
            "passed": type(code) is int and code == 33 and timed_out is False and exact and ordered and no_fail}


def run_candidate(args, output, result):
    before = source_snapshot(ROOT, args.expected_source_head, args.expected_source_tree)
    for name in ("tests/kernel/control/run_queryabi_candidate_guest.py",
                 "tests/kernel/control/queryabi_candidate_guest.c",
                 "tests/kernel/control/queryabi_guest.c", "tests/kernel/control/run_queryabi_guest.py"):
        require(name in before["files"], "candidate execution input is not tracked by the reviewed commit")
    save_json(output / "source-before.json", before)
    result.update(source_head=before["head"], source_tree=before["tree"], source_file_count=len(before["files"]))
    boot_dir = output / "product-boot"
    target_dir = args.target_dir.absolute()
    env = dict(os.environ)
    # Clear ambient cfg/wrapper/target overrides for the ordinary product build.
    for name in ("RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "CARGO_TARGET_DIR"):
        env.pop(name, None)
    env.update(A01_RUN_DIR=str(boot_dir), A01_SMP="1", A01_QEMU_TIMEOUT=str(args.boot_timeout),
               CARGO_TARGET_DIR=str(target_dir))
    result.update(cargo_target_dir=str(target_dir), product_configuration="ActionChoice::Run; no --cfg ktest")
    result["stage"] = "ordinary_product_build_and_boot"
    with (output / "product-wrapper.log").open("xb") as log:
        built = subprocess.run([str(ROOT / "support/build/kernel.sh"), "run_kernel"], cwd=ROOT,
                               env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
    result["product_wrapper_exit"] = built.returncode
    after = source_snapshot(ROOT, args.expected_source_head, args.expected_source_tree)
    save_json(output / "source-after-boot.json", after)
    require(before == after, "tracked inputs changed during ordinary product build")
    require(built.returncode == 0, "ordinary product build/boot failed; retained original logs")
    qemu, artifacts, lock_hash = verify_product_boot(boot_dir, ROOT, before, target_dir)
    result.update(product_boot_raw_exit=qemu["raw_exit_code"], minimal_generated_lock_sha256=lock_hash,
                  minimal_generated_package_count=204,
                  product_qemu_record_sha256=replay.digest((boot_dir / "qemu.json").read_bytes()))
    result["stage"] = "compile_original_probe_wrapper"
    guest_source = Path(__file__).with_name("queryabi_candidate_guest.c")
    guest_elf = output / "hos2-queryabi"
    command = [args.cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-static", str(guest_source), "-o", str(guest_elf)]
    compiled = subprocess.run(command, capture_output=True, timeout=60)
    (output / "compile.log").write_bytes(compiled.stdout + compiled.stderr)
    result.update(compiler_command=command, compile_exit=compiled.returncode)
    require(compiled.returncode == 0, "static candidate probe compile failed")
    probe = guest_elf.read_bytes()
    initrd = replay.build_guest_initramfs(artifacts["-initrd"], probe)
    # Copy the exact reviewed boot bytes to fresh immutable-by-convention paths.
    for name, data in (("product-kernel.elf", artifacts["-kernel"]), ("bios.bin", artifacts["-bios"]), ("initramfs.cpio.gz", initrd)):
        (output / name).write_bytes(data)
    binary = shutil.which(args.qemu)
    require(binary is not None and replay.digest(Path(binary).read_bytes()) == qemu["qemu_sha256"],
            "candidate QEMU differs from the ordinary product boot")
    argv = [binary, "-kernel", str(output / "product-kernel.elf"), "-initrd", str(output / "initramfs.cpio.gz"),
            "-append", "earlycon console=ttyS0 loglevel=info SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --",
            "-machine", "q35", "-accel", "tcg", "-cpu", "max", "-bios", str(output / "bios.bin"), "-m", "512M", "-smp", "1",
            "-nodefaults", "-no-user-config", "-no-reboot", "-nographic", "-display", "none", "-monitor", "none",
            "-serial", "stdio", "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"]
    result.update(stage="queryabi_candidate_guest", qemu_argv=argv,
                  kernel_elf_sha256=replay.digest(artifacts["-kernel"]), original_initramfs_sha256=replay.digest(artifacts["-initrd"]),
                  bios_sha256=replay.digest(artifacts["-bios"]), probe_sha256=replay.digest(probe), injected_initramfs_sha256=replay.digest(initrd))
    save_json(output / "result.json", result)
    start = time.monotonic()
    code, timed_out = None, False
    with (output / "serial.log").open("xb") as log:
        try:
            code = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                  timeout=args.timeout, check=False).returncode
        except subprocess.TimeoutExpired:
            timed_out = True
    result.update(qemu_exit=code, timed_out=timed_out, elapsed_seconds=round(time.monotonic() - start, 3))
    result.update(evaluate_guest((output / "serial.log").read_bytes(), code, timed_out))
    final = source_snapshot(ROOT, args.expected_source_head, args.expected_source_tree)
    save_json(output / "source-after-guest.json", final)
    require(final == before, "tracked inputs changed during candidate guest")
    for name, data in (("product-kernel.elf", artifacts["-kernel"]), ("bios.bin", artifacts["-bios"]), ("initramfs.cpio.gz", initrd)):
        require((output / name).read_bytes() == data, "candidate boot input changed during guest")
    result.update(stage="complete", source_inputs_unchanged=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-source-head", required=True)
    parser.add_argument("--expected-source-tree", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-dir", type=Path, default=ROOT / "kernel/asterinas/target")
    parser.add_argument("--qemu", default="qemu-system-x86_64")
    parser.add_argument("--cc", default="cc")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--boot-timeout", type=int, default=300)
    args = parser.parse_args(argv)
    require(1 <= args.timeout <= 120 and 1 <= args.boot_timeout <= 600, "invalid bounded guest timeout")
    output = args.output.absolute()
    require(not output.exists() and not output.is_symlink(), "output must be a new directory")
    require(not output.resolve().is_relative_to(ROOT.resolve()), "candidate evidence must be outside the source checkout")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    result = {"schema": "a06.g1-queryabi-product-candidate.v1", "stage": "source_admission", "passed": False,
              "native_grants": False, "native_resource_effects": False, "hepta_durability": False,
              "smp_qualification": False, "production_ready": False}
    try:
        run_candidate(args, output, result)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        result.update(passed=False, error=f"{type(error).__name__}: {error}")
    save_json(output / "result.json", result)
    print(json.dumps({"passed": result["passed"], "stage": result["stage"], "output": str(output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
