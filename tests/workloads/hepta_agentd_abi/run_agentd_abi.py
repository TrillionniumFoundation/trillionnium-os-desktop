#!/usr/bin/env python3
"""Disabled by default: original Agentd's earliest config rejection in QEMU.

Only --execute creates a fresh payload disk, compiles the small guest launcher,
and starts QEMU. Agentd and the dynamic loader are never executed on the host.
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import stat
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cpio_codec

HERE = Path(__file__).resolve().parent
KERNEL_SHA = "8170402aaa7408eb2c4ab1ade2cd1d9641ef03ccbd37631aaec775528df2ede7"
KERNEL_HEAD = "85d394f99c73ad3194d57c876712ac01b59d90ca"
KERNEL_TREE = "7389c0a3f982983087953f75de7042fc058be088"
INITRAMFS_SHA = "86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3"
BIOS_SHA = "1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735"
EXPECTED_ERROR = b"Error: invalid agentd configuration: HEPTA_FLEET_ROOT is required\n"
BOOT = b'echo "TRILLIONNIUM_A01_BOOT_OK"'
ENV = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C"}
LIMIT = 8 * 1024 * 1024


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def pinned(path, expected, limit):
    require(re.fullmatch("[0-9a-f]{64}", expected or "") is not None, "invalid expected SHA256")
    require(path.is_file() and not path.is_symlink(), "expected regular non-symlink input: " + str(path))
    require(0 < path.stat().st_size <= limit, "input size outside bound: " + str(path))
    require(sha(path) == expected, "input SHA256 mismatch: " + str(path))
    return path


def frozen_input(path, expected):
    pinned(path, expected, 256 * 1024)
    value = json.loads(path.read_text())
    require(value.get("schema") == "hepta.agentd-frozen-input.v1", "unknown frozen-input schema")
    built = value.get("build_source", {})
    for key in ("head", "tree"):
        require(re.fullmatch("[0-9a-f]{40}", built.get(key, "")) is not None, "missing build source " + key)
    published = value.get("published_source")
    if published is not None:
        require(re.fullmatch("[0-9a-f]{40}", published.get("head", "")) is not None,
                "invalid published source head")
        require(published.get("tree") == built["tree"], "build/published source trees differ")
    reviewed = json.loads((HERE / "source-review.json").read_text())
    expected_files = {v["path"]: v for v in reviewed["source_files"] if v["path"].endswith(".rs")}
    records = value.get("source_files", [])
    require(isinstance(records, list), "source_files must be a list")
    files = {v["path"]: v for v in records}
    require(len(files) == len(records), "duplicate source identity")
    for name, reference in expected_files.items():
        actual = files.get(name, {})
        require(all(actual.get(k) == reference[k] for k in ("git_blob", "sha256")),
                "unreviewed startup source: " + name)
    binary = value.get("binary", {})
    relative = Path(binary.get("path", ""))
    require(not relative.is_absolute() and relative.parts and
            all(p not in ("", ".", "..") for p in relative.parts), "binary path must remain in frozen input directory")
    input_path = path.parent / relative
    require(input_path.resolve().is_relative_to(path.parent.resolve()), "binary escapes frozen input directory")
    pinned(input_path, binary.get("sha256"), 1024**3)
    require(type(binary.get("bytes")) is int and input_path.stat().st_size == binary["bytes"], "binary size mismatch")
    return value, input_path


def tool(name):
    located = shutil.which(name, path=ENV["PATH"])
    require(located is not None, "missing tool: " + name)
    p = Path(located).resolve(strict=True)
    require(p.is_file(), "tool must be a regular file: " + name)
    with p.open("rb") as stream:
        require(stream.read(4) == b"\x7fELF", "tool must be actual native ELF: " + name)
    return str(p)


def command(argv, out, name, timeout=60):
    with (out / (name + ".log")).open("xb") as f:
        cp = subprocess.run(argv, env=ENV, stdin=subprocess.DEVNULL, stdout=f,
                            stderr=subprocess.STDOUT, timeout=timeout, check=False)
    require(cp.returncode == 0, name + " failed; see its log")
    return (out / (name + ".log")).read_bytes()


def elf_info(path, readelf):
    with path.open("rb") as f:
        header = f.read(64)
        require(len(header) == 64 and header[:7] == b"\x7fELF\x02\x01\x01", "ELF64 little-endian required")
        kind, machine = struct.unpack_from("<HH", header, 16)
        require(machine == 62 and kind in (2, 3), "ELF must be x86_64 executable/shared object")
        offset = struct.unpack_from("<Q", header, 32)[0]
        size, count = struct.unpack_from("<HH", header, 54)
        require(size == 56 and 0 < count <= 128 and offset + size * count <= path.stat().st_size,
                "invalid ELF program headers")
        f.seek(offset)
        table = f.read(size * count)
        loads, interpreter = [], None
        for index in range(count):
            ptype, flags, off, va, _, filesz, memsz, align = struct.unpack_from("<IIQQQQQQ", table, index * size)
            if ptype == 1:
                loads.append({"offset": off, "virtual_address": va, "file_bytes": filesz,
                              "memory_bytes": memsz, "flags": flags, "alignment": align})
            if ptype == 3:
                require(interpreter is None and 0 < filesz <= 4096, "ambiguous ELF interpreter")
                f.seek(off)
                raw = f.read(filesz)
                require(raw.endswith(b"\0") and b"\0" not in raw[:-1], "invalid interpreter path")
                interpreter = raw[:-1].decode("ascii")
    cp = subprocess.run([readelf, "-d", str(path)], env=ENV, capture_output=True, timeout=15, check=False)
    require(cp.returncode == 0, "readelf dynamic inspection failed")
    text = cp.stdout.decode("utf-8", "strict")
    require("(RPATH)" not in text and "(RUNPATH)" not in text, "review RPATH/RUNPATH before staging")
    needed = re.findall(r"\(NEEDED\).*Shared library: \[([^\]]+)\]", text)
    require(all(re.fullmatch("[A-Za-z0-9_.+-]+", n) for n in needed), "unsafe DT_NEEDED name")
    return {"type": kind, "machine": machine, "interpreter": interpreter, "needed": needed,
            "load_segments": loads, "load_memory_bytes": sum(v["memory_bytes"] for v in loads)}


def stage_closure(binary, payload, readelf, library_dirs):
    binary_info = elf_info(binary, readelf)
    require(binary_info["interpreter"] == "/lib64/ld-linux-x86-64.so.2", "unexpected Agentd interpreter")
    pending = list(binary_info["needed"])
    if "ld-linux-x86-64.so.2" not in pending:
        pending.append("ld-linux-x86-64.so.2")
    libraries = {}
    while pending:
        name = pending.pop(0)
        if name in libraries:
            continue
        require(len(libraries) < 32, "runtime library closure too large")
        paths = [(directory / name).resolve() for directory in library_dirs if (directory / name).exists()]
        require(paths, "unresolved runtime library: " + name)
        source = paths[0]
        require(source.is_file() and source.stat().st_size <= 64 * 1024 * 1024, "invalid library input")
        digest = sha(source)
        require(all(sha(p) == digest for p in paths), "ambiguous differing runtime library: " + name)
        destination = payload / "lib/x86_64-linux-gnu" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        destination.chmod(0o555)
        require(sha(destination) == digest, "runtime library changed during copy")
        info = elf_info(destination, readelf)
        require(info["interpreter"] in (None, binary_info["interpreter"]),
                "shared library names a different interpreter")
        libraries[name] = {"host_path": str(source), "guest_path": "/lib/x86_64-linux-gnu/" + name,
                           "bytes": destination.stat().st_size, "sha256": digest, "elf": info}
        pending.extend(info["needed"])
    (payload / "lib64").mkdir()
    shutil.copyfile(payload / "lib/x86_64-linux-gnu/ld-linux-x86-64.so.2",
                    payload / "lib64/ld-linux-x86-64.so.2")
    (payload / "lib64/ld-linux-x86-64.so.2").chmod(0o555)
    return binary_info, libraries


def build_initramfs(original, probe, nonce):
    entries = cpio_codec.unpack(gzip.decompress(original))
    require(cpio_codec.unpack(cpio_codec.pack(entries)) == entries, "original cpio roundtrip mismatch")
    require(all(name.lstrip("./") not in ("lib", "lib64", "payload", "bin/agentd-abi-probe")
                for name, _, _ in entries), "unexpected original runtime paths")
    script = (
        '/bin/busybox mkdir -p /payload\n'
        '/bin/busybox mount -t ext2 -o ro /dev/vda /payload\n'
        '/bin/busybox ln -s /payload/lib /lib\n'
        '/bin/busybox ln -s /payload/lib64 /lib64\n'
        f'if /bin/agentd-abi-probe {nonce}; then abi_code=0; else abi_code=$?; fi\n'
        f'echo "HEPTA_ABI_HARNESS nonce={nonce} exit=$abi_code"\n'
    ).encode()
    changed, found = [], 0
    for name, fields, content in entries:
        if name.lstrip("./") == "init":
            require(content.count(BOOT) == 1 and b"set -eu" in content, "ambiguous original init")
            content = content.replace(BOOT, script + BOOT)
            found += 1
        changed.append((name, fields, content))
    require(found == 1, "missing original init")
    fields = [max(item[1][0] for item in entries) + 1, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
    changed.append(("bin/agentd-abi-probe", fields, probe))
    packed = cpio_codec.pack(changed)
    require(len(cpio_codec.unpack(packed)) == len(entries) + 1, "changed initramfs entry set")
    return gzip.compress(packed, mtime=0)


def oracle(raw, code, timed_out, nonce):
    lines = raw.replace(b"\r\n", b"\n").split(b"\n")
    expected = [
        f"HEPTA_ABI_BEGIN nonce={nonce}".encode(),
        f"HEPTA_ABI_STDOUT nonce={nonce} hex=".encode(),
        f"HEPTA_ABI_STDERR nonce={nonce} hex={EXPECTED_ERROR.hex()}".encode(),
        f"HEPTA_ABI_CHILD nonce={nonce} kind=exit code=1".encode(),
        f"HEPTA_ABI_HARNESS nonce={nonce} exit=0".encode(),
    ]
    markers = [line for line in lines if line.startswith(b"HEPTA_ABI_")]
    return (code == 33 and not timed_out and markers == expected
            and lines.count(b"TRILLIONNIUM_A01_INIT_BEGIN") == 1
            and lines.count(b"TRILLIONNIUM_A01_BOOT_OK") == 1
            and b"Kernel panic" not in raw)


def child_observation(raw, nonce):
    lines = raw.replace(b"\r\n", b"\n").split(b"\n")
    observed = {}
    for stream in ("STDOUT", "STDERR"):
        prefix = f"HEPTA_ABI_{stream} nonce={nonce} hex=".encode()
        matches = [line[len(prefix):] for line in lines if line.startswith(prefix)]
        if len(matches) == 1 and re.fullmatch(b"[0-9a-f]{0,8192}", matches[0]):
            try:
                observed[stream.lower()] = bytes.fromhex(matches[0].decode()).decode("utf-8", "replace")
            except ValueError:
                pass
    prefix = f"HEPTA_ABI_CHILD nonce={nonce} ".encode()
    matches = [line[len(prefix):] for line in lines if line.startswith(prefix)]
    if len(matches) == 1:
        observed["termination"] = matches[0].decode("ascii", "replace")
    return observed


def run_qemu(argv, out, timeout, report):
    timed_out, excessive = False, False
    started = time.monotonic()
    data = bytearray()
    with (out / "serial.log").open("xb") as log, subprocess.Popen(
        argv, env=ENV, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, start_new_session=True,
    ) as process:
        report["executed"] = True
        report["qemu_started_at_utc"] = datetime.now(timezone.utc).isoformat()
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
                    block = os.read(process.stdout.fileno(), 16384)
                    if not block:
                        break
                    log.write(block)
                    data.extend(block)
                    if len(data) > LIMIT:
                        excessive = True
                        break
            if timed_out or excessive:
                process.kill()
            code = process.wait(timeout=10)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
    return bytes(data), code, timed_out, excessive


def execute(args, out, report):
    require(args.expected_kernel_sha256 == KERNEL_SHA, "ordinary kernel is not the reviewed 85d artifact")
    require(30 <= args.timeout <= 600, "guest timeout must be 30..600 seconds")
    require(1024 <= args.memory_mib <= 4096, "guest memory must be 1024..4096 MiB")
    manifest, binary = frozen_input(args.input_manifest, args.expected_input_manifest_sha256)
    pinned(args.kernel, KERNEL_SHA, 64 * 1024 * 1024)
    pinned(args.initramfs, INITRAMFS_SHA, LIMIT)
    pinned(args.bios, BIOS_SHA, 2 * 1024 * 1024)
    require(not out.exists() and not out.is_symlink() and "," not in str(out), "output must be new and comma-free")
    require(not out.resolve().is_relative_to(args.input_manifest.parent.resolve()), "output must be outside frozen input")
    tools = {name: tool(getattr(args, name)) for name in ("qemu", "mkfs", "readelf", "cc")}
    require(re.fullmatch("[0-9a-f]{64}", args.expected_qemu_sha256 or "") is not None,
            "explicit actual QEMU executable digest is required")
    require(sha(Path(tools["qemu"])) == args.expected_qemu_sha256, "QEMU executable digest mismatch")
    out.mkdir(parents=True, mode=0o700)
    report["evidence_directory_created"] = True
    save(out / "frozen-input-manifest.json", manifest)
    report.update(frozen_input_manifest_sha256=args.expected_input_manifest_sha256,
                  build_source=manifest["build_source"], published_source=manifest.get("published_source"),
                  binary=manifest["binary"], input_source_attestation="caller-retained frozen manifest; reviewed startup blobs checked",
                  tool_identities={n: {"path": p, "sha256": sha(Path(p))} for n, p in tools.items()})
    payload = out / "payload-root"
    (payload / "bin").mkdir(parents=True)
    frozen_copy = payload / "bin/codex-hepta-agentd"
    shutil.copyfile(binary, frozen_copy)
    frozen_copy.chmod(0o555)
    pinned(frozen_copy, manifest["binary"]["sha256"], 1024**3)
    runtime_info, libraries = stage_closure(frozen_copy, payload, tools["readelf"], args.library_dir)
    save(out / "runtime-inputs.json", {"binary_elf": runtime_info, "libraries": libraries,
                                      "interpreter_duplicate_path": "/lib64/ld-linux-x86-64.so.2"})
    command([tools["readelf"], "-W", "-V", str(frozen_copy)], out, "agentd-symbol-versions")
    for name, original in (("kernel.elf", args.kernel), ("bios.bin", args.bios)):
        shutil.copyfile(original, out / name)
    pinned(out / "kernel.elf", KERNEL_SHA, 64 * 1024 * 1024)
    pinned(out / "bios.bin", BIOS_SHA, 2 * 1024 * 1024)
    compiler = [tools["cc"], "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror", "-static",
                str(HERE / "agentd_abi_probe.c"), "-o", str(out / "agentd-abi-probe")]
    command(compiler, out, "compile-guest-probe", 120)
    require(elf_info(out / "agentd-abi-probe", tools["readelf"])["interpreter"] is None,
            "guest launcher must be static")
    nonce = os.urandom(32).hex()
    (out / "initramfs.cpio.gz").write_bytes(build_initramfs(
        args.initramfs.read_bytes(), (out / "agentd-abi-probe").read_bytes(), nonce))
    image = out / "payload.raw"
    size = max(1024**3, (manifest["binary"]["bytes"] * 2 + 256 * 1024**2 + 4095) // 4096 * 4096)
    require(shutil.disk_usage(out).free >= size + 256 * 1024**2, "insufficient free space for fresh payload")
    with image.open("xb") as f:
        f.truncate(size)
    formatter = [tools["mkfs"], "-F", "-q", "-b", "4096", "-I", "256", "-m", "0",
                 "-O", "none,filetype", "-d", str(payload), str(image)]
    command(formatter, out, "format-payload", 120)
    image_sha = sha(image)
    argv = [tools["qemu"], "-kernel", str(out / "kernel.elf"), "-initrd", str(out / "initramfs.cpio.gz"),
            "-machine", "q35", "-accel", "tcg", "-cpu", "max", "-bios", str(out / "bios.bin"),
            "-m", str(args.memory_mib) + "M", "-smp", "1", "-nodefaults", "-no-user-config",
            "-no-reboot", "-nographic", "-display", "none", "-monitor", "none", "-serial", "stdio", "-nic", "none",
            "-append", "earlycon console=ttyS0 loglevel=info SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --",
            "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04",
            "-drive", "if=none,format=raw,id=abi,readonly=on,file=" + str(image),
            "-device", "virtio-blk-pci,bus=pcie.0,addr=0x7,drive=abi,disable-legacy=on,disable-modern=off"]
    save(out / "invocation.json", {"argv": argv, "formatter": formatter, "compiler": compiler,
                                  "nonce": nonce, "child_argv": ["/payload/bin/codex-hepta-agentd"],
                                  "child_environment": {}, "read_only_payload_sha256": image_sha,
                                  "timeout_seconds": args.timeout})
    report.update(kernel_sha256=KERNEL_SHA, initramfs_sha256=sha(out / "initramfs.cpio.gz"),
                  probe_sha256=sha(out / "agentd-abi-probe"), payload_sha256=image_sha,
                  runtime_inputs_sha256=sha(out / "runtime-inputs.json"), nonce=nonce)
    require(sha(Path(tools["qemu"])) == args.expected_qemu_sha256, "QEMU executable changed")
    report["execution_attempted"] = True
    raw, code, timed_out, excessive = run_qemu(argv, out, args.timeout, report)
    unchanged = (sha(image) == image_sha and sha(binary) == manifest["binary"]["sha256"]
                 and sha(args.input_manifest) == args.expected_input_manifest_sha256)
    passed = oracle(raw, code, timed_out, nonce) and not excessive and unchanged
    report.update(executed=True, qemu_exit=code, timed_out=timed_out, serial_excessive=excessive,
                  serial_sha256=hashlib.sha256(raw).hexdigest(), inputs_unchanged=unchanged,
                  observed_child=child_observation(raw, nonce),
                  passed=passed, earliest_config_rejection_verified=passed)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--input-manifest", type=Path)
    parser.add_argument("--expected-input-manifest-sha256")
    parser.add_argument("--kernel", type=Path)
    parser.add_argument("--expected-kernel-sha256")
    parser.add_argument("--initramfs", type=Path)
    parser.add_argument("--bios", type=Path, default=Path("/usr/share/seabios/bios-256k.bin"))
    parser.add_argument("--qemu", default="qemu-system-x86_64")
    parser.add_argument("--expected-qemu-sha256")
    parser.add_argument("--mkfs", default="mkfs.ext2")
    parser.add_argument("--readelf", default="readelf")
    parser.add_argument("--cc", default="gcc")
    parser.add_argument("--library-dir", type=Path, action="append")
    parser.add_argument("--memory-mib", type=int, default=2048)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = {"schema": "hepta.agentd-ordinary-abi-preflight.v1", "passed": False, "executed": False,
              "production": False, "daemon_started": False, "original_owner_runtime": False,
              "g2_completed": False, "f_completed": False, "ordinary_os_source": {"head": KERNEL_HEAD, "tree": KERNEL_TREE},
              "scope": "original ELF loader -> Rust main -> expected missing HEPTA_FLEET_ROOT rejection",
              "expected_child_exit": 1, "expected_child_stderr": EXPECTED_ERROR.decode(),
              "started_at_utc": datetime.now(timezone.utc).isoformat()}
    if not args.execute:
        report["status"] = "disabled; explicit --execute required"
        print(json.dumps(report, sort_keys=True))
        return 0
    required = ("input_manifest", "expected_input_manifest_sha256", "kernel", "expected_kernel_sha256",
                "initramfs", "expected_qemu_sha256", "output")
    for key in required:
        if getattr(args, key) is None:
            parser.error("--execute requires --" + key.replace("_", "-"))
    out = args.output.absolute()
    args.library_dir = args.library_dir or [Path("/lib/x86_64-linux-gnu"), Path("/usr/lib/x86_64-linux-gnu"), Path("/lib64")]
    try:
        execute(args, out, report)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report["error"] = f"{type(error).__name__}: {error}"
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["runner_sha256"] = sha(Path(__file__))
    report["candidate_input_sha256"] = {name: sha(HERE / name) for name in
        ("agentd_abi_probe.c", "cpio_codec.py", "source-review.json")}
    if report.get("evidence_directory_created") is True:
        save(out / "result.json", report)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
