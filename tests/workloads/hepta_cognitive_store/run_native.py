#!/usr/bin/env python3
"""Opt-in ordinary Asterinas guest gate for original legacy CognitiveStore.

This does not build a kernel. Supply a real ordinary-kernel build receipt and
its reviewed Desktop tree explicitly. No lifecycle profile pins are rewritten.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_host as host
sys.path.insert(0, str(HERE.parent / "hepta_agentd_runtime"))
import run_agentd_runtime as runtime

require, sha, save, abi = host.require, host.sha, host.save, runtime.abi


def kernel_input(kernel, receipt_path, expected_receipt, expected_tree):
    abi.pinned(receipt_path, expected_receipt, 4 * 1024**2)
    value = host.json_value(receipt_path.read_bytes())
    require(isinstance(value, dict) and value.get("schema") == "hepta.native-original-runtime-build.v1"
            and value.get("built") is True and value.get("source_clean") is True
            and value.get("kernel_profile") == "ordinary-os", "successful clean ordinary kernel build receipt required")
    sources = value.get("build_sources", {})
    require(isinstance(sources, dict) and set(sources) == {"desktop"}, "actual kernel build source required")
    identity = sources["desktop"]
    require(isinstance(identity, dict) and re.fullmatch("[0-9a-f]{40}", identity.get("head", ""))
            and re.fullmatch("[0-9a-f]{40}", expected_tree or "")
            and identity.get("tree") == expected_tree, "kernel source tree differs from caller-reviewed tree")
    hashes = value.get("binary_sha256", {})
    require(isinstance(hashes, dict) and set(hashes) == {"kernel"}, "one kernel binary identity required")
    abi.pinned(kernel, hashes["kernel"], 64 * 1024**2)
    commands = value.get("commands")
    require(isinstance(commands, list) and commands
            and all(isinstance(command, list) and command and all(isinstance(arg, str) and arg for arg in command)
                    for command in commands), "ordinary kernel build commands missing")
    return value


def observe(raw, code, timed_out, excessive, nonce):
    require(code == 33 and not timed_out and not excessive, "QEMU did not finish a bounded ordinary boot")
    lines = raw.replace(b"\r\n", b"\n").split(b"\n")
    require(lines.count(b"TRILLIONNIUM_A01_INIT_BEGIN") == 1 and lines.count(b"TRILLIONNIUM_A01_BOOT_OK") == 1,
            "ordinary boot markers missing or repeated")
    require(b"kernel panic" not in raw.lower(), "kernel panic in store boot")
    markers = [line for line in lines if line.startswith(b"HEPTA_RUNTIME_")]
    require(len(markers) == 5 and markers[0] == f"HEPTA_RUNTIME_BEGIN nonce={nonce}".encode()
            and markers[3] == f"HEPTA_RUNTIME_CHILD nonce={nonce} kind=exit code=0".encode()
            and markers[4] == f"HEPTA_RUNTIME_HARNESS nonce={nonce} exit=0".encode(), "store nonce/child/launcher markers mismatch")
    for index, name in enumerate(("STDOUT", "STDERR"), 1):
        require(markers[index].startswith(f"HEPTA_RUNTIME_{name} nonce={nonce} hex=".encode()), "store streams reordered")
    streams = runtime.captured_streams(raw, nonce)
    require(streams["stderr"] == b"", "successful original store fixture wrote stderr")
    return host.validate_record(streams["stdout"]), streams


def qemu_argv(qemu, out, memory_mib):
    argv = runtime.qemu_argv(qemu, out, memory_mib)
    index = argv.index("-append") + 1
    require(argv[index].count("loglevel=info") == 1, "unexpected original boot log filter")
    # Keep WARN/ERROR diagnostics, without INFO syscall traces splitting serial
    # receipt records or consuming the bounded serial budget.
    argv[index] = argv[index].replace("loglevel=info", "loglevel=warn")
    return argv


def execute(args, out, report):
    require(120 <= args.timeout <= 900 and 2048 <= args.memory_mib <= 8192, "bounded guest timeout/memory required")
    receipt, fixture = host.frozen_build(args.build_receipt, args.expected_build_receipt_sha256)
    kernel_receipt = kernel_input(args.kernel, args.kernel_receipt, args.expected_kernel_receipt_sha256,
                                  args.expected_desktop_tree)
    abi.pinned(args.initramfs, abi.INITRAMFS_SHA, abi.LIMIT)
    abi.pinned(args.bios, abi.BIOS_SHA, 2 * 1024**2)
    require(not out.exists() and not out.is_symlink() and "," not in str(out), "new comma-free output required")
    require(not out.resolve().is_relative_to(args.build_receipt.parent.resolve()), "output must be outside frozen fixture inputs")
    require(not out.resolve().is_relative_to(args.kernel.parent.resolve()), "output must be outside retained kernel inputs")
    tools = {name: abi.tool(getattr(args, name)) for name in ("qemu", "mkfs", "readelf", "cc")}
    abi.pinned(Path(tools["qemu"]), args.expected_qemu_sha256, 1024**3)
    out.mkdir(mode=0o700)
    report["output_created"] = True
    save(out / "frozen-build.json", receipt)
    save(out / "frozen-kernel-build.json", kernel_receipt)
    report.update(hepta_source=receipt["source"], kernel_build_source=kernel_receipt["build_sources"]["desktop"],
                  input_attestation="caller-retained local build receipts and explicit reviewed Desktop tree; not remote attestation",
                  tool_identities={name: {"path": path, "sha256": sha(Path(path))} for name, path in tools.items()})
    payload = out / "payload-root"
    (payload / "bin").mkdir(parents=True)
    copy = payload / "bin" / host.build.NAME
    shutil.copyfile(fixture, copy)
    copy.chmod(0o555)
    abi.pinned(copy, receipt["binary"]["sha256"], 1024**3)
    save(out / "runtime-inputs.json", runtime.stage_closure({"fixture": copy}, payload, tools["readelf"], args.library_dir))
    for filename, source, digest in (("kernel.elf", args.kernel, kernel_receipt["binary_sha256"]["kernel"]),
                                     ("bios.bin", args.bios, abi.BIOS_SHA)):
        shutil.copyfile(source, out / filename)
        abi.pinned(out / filename, digest, 64 * 1024**2)
    compiler = [tools["cc"], "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror", "-static",
                str(HERE / "store_runtime_probe.c"), "-o", str(out / "store-runtime-probe")]
    abi.command(compiler, out, "compile-guest-probe", 120)
    require(abi.elf_info(out / "store-runtime-probe", tools["readelf"])["interpreter"] is None, "static guest launcher required")
    nonce = os.urandom(32).hex()
    (out / "initramfs.cpio.gz").write_bytes(runtime.build_initramfs(args.initramfs.read_bytes(),
                                                                 (out / "store-runtime-probe").read_bytes(), nonce))
    total = sum(path.stat().st_size for path in payload.rglob("*") if path.is_file())
    payload_bytes = max(512 * 1024**2, (total * 2 + 128 * 1024**2 + 4095) // 4096 * 4096)
    require(shutil.disk_usage(out).free >= payload_bytes + runtime.STATE_BYTES + 256 * 1024**2, "insufficient free disk")
    formatters = []
    for name, size in (("payload", payload_bytes), ("state", runtime.STATE_BYTES)):
        image = out / (name + ".raw")
        with image.open("xb") as stream:
            stream.truncate(size)
        command = [tools["mkfs"], "-F", "-q", "-b", "4096", "-I", "256", "-m", "0", "-O", "none,filetype"]
        if name == "payload":
            command.extend(["-d", str(payload)])
        command.append(str(image))
        abi.command(command, out, "format-" + name, 120)
        formatters.append(command)
    payload_sha, state_before = sha(out / "payload.raw"), sha(out / "state.raw")
    argv = qemu_argv(tools["qemu"], out, args.memory_mib)
    save(out / "invocation.json", {"argv": argv, "compiler": compiler, "formatters": formatters, "nonce": nonce,
                                  "fixture_argv": ["/payload/bin/" + host.build.NAME, "probe", "/state/probe/store"],
                                  "fixture_environment": runtime.ENVIRONMENT, "timeout_seconds": args.timeout,
                                  "build_receipt_sha256": args.expected_build_receipt_sha256,
                                  "kernel_receipt_sha256": args.expected_kernel_receipt_sha256})
    report.update(nonce=nonce, kernel_sha256=sha(out / "kernel.elf"), initramfs_sha256=sha(out / "initramfs.cpio.gz"),
                  launcher_sha256=sha(out / "store-runtime-probe"), payload_sha256=payload_sha,
                  state_before_sha256=state_before, state_bytes=runtime.STATE_BYTES, execution_attempted=True)
    raw, code, timed_out, excessive = abi.run_qemu(argv, out, args.timeout, report)
    report.update(qemu_exit=code, timed_out=timed_out, serial_excessive=excessive,
                  state_after_sha256=sha(out / "state.raw"))
    # Preserve failure diagnostics too. A decode failure cannot grant a pass.
    try:
        for name, content in runtime.captured_streams(raw, nonce).items():
            (out / ("fixture." + name)).write_bytes(content)
    except ValueError as error:
        report["diagnostic_decode_error"] = str(error)
    observed, _ = observe(raw, code, timed_out, excessive, nonce)
    host.frozen_build(args.build_receipt, args.expected_build_receipt_sha256)
    kernel_input(args.kernel, args.kernel_receipt, args.expected_kernel_receipt_sha256, args.expected_desktop_tree)
    abi.pinned(args.initramfs, abi.INITRAMFS_SHA, abi.LIMIT)
    abi.pinned(args.bios, abi.BIOS_SHA, 2 * 1024**2)
    abi.pinned(Path(tools["qemu"]), args.expected_qemu_sha256, 1024**3)
    require(sha(out / "payload.raw") == payload_sha, "read-only payload changed")
    require(report["state_after_sha256"] != state_before, "original store did not write fresh ext2 state disk")
    report.update(passed=True, native_guest_verified=True, original_store_process_crash_reopen_verified=True,
                  observation=observed)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    for name in ("build-receipt", "kernel", "kernel-receipt", "initramfs", "output"):
        parser.add_argument("--" + name, type=Path)
    for name in ("expected-build-receipt-sha256", "expected-kernel-receipt-sha256", "expected-desktop-tree", "expected-qemu-sha256"):
        parser.add_argument("--" + name)
    parser.add_argument("--bios", type=Path, default=Path("/usr/share/seabios/bios-256k.bin"))
    for name, default in (("qemu", "qemu-system-x86_64"), ("mkfs", "mkfs.ext2"), ("readelf", "readelf"), ("cc", "gcc")):
        parser.add_argument("--" + name, default=default)
    parser.add_argument("--library-dir", type=Path, action="append")
    parser.add_argument("--memory-mib", type=int, default=4096)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args(argv)
    report = {"schema": "hepta.original-cognitive-store-native-result.v1", "passed": False, "executed": False,
              "native_guest_verified": False, **dict.fromkeys(host.FALSE_FLAGS, False),
              "started_at_utc": datetime.now(timezone.utc).isoformat()}
    if not args.execute:
        report["status"] = "disabled; explicit --execute and real frozen ordinary-kernel and fixture inputs required"
        print(json.dumps(report, sort_keys=True))
        return 0
    for name in ("build_receipt", "expected_build_receipt_sha256", "kernel", "kernel_receipt", "expected_kernel_receipt_sha256",
                 "expected_desktop_tree", "initramfs", "expected_qemu_sha256", "output"):
        if getattr(args, name) is None:
            parser.error("--execute requires --" + name.replace("_", "-"))
    args.library_dir = args.library_dir or [Path("/lib/x86_64-linux-gnu"), Path("/usr/lib/x86_64-linux-gnu"), Path("/lib64")]
    out = args.output.absolute()
    try:
        execute(args, out, report)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report["error"] = f"{type(error).__name__}: {error}"
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["candidate_source_sha256"] = {path.name: sha(path) for path in
        (Path(__file__), HERE / "store_runtime_probe.c", HERE / "store_probe.rs", HERE / "source-review.json")}
    if report.get("output_created"):
        save(out / "result.json", report)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
