#!/usr/bin/env python3
"""Opt-in native original-owner lifecycle gate; never run Agentd on the host.

The unchanged original fixture creates the registry and launches Agentd through
its original Supervisor/UnixProcessDriver. A pass covers the no-turn lifecycle
only; it is not complete F1, production authority, native G2, or crash durability.
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ABI = HERE.parent / "hepta_agentd_abi"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ABI))
import cpio_codec
import run_agentd_abi as abi

require, sha, pinned, save = abi.require, abi.sha, abi.pinned, abi.save
AGENT = "22222222-2222-4222-8222-222222222222"
BINARIES = {"agentd": "codex-hepta-agentd", "fixture": "hepta-original-observer-probe", "observer": "hepta-observe"}
EXPECTED_CHECKS = [
    "original_starting", "original_running", "bounded_capabilities_events",
    "missing_run_read", "same_process_draining", "original_restart",
    "old_spawn_rejected", "controlled_stop",
]
STDOUT_LIMIT, STDERR_LIMIT = 512 * 1024, 64 * 1024
STATE_BYTES = 256 * 1024**2
ENVIRONMENT = {"PATH": "/bin:/sbin", "HOME": "/state/probe", "TMPDIR": "/state/tmp",
               "LANG": "C", "LC_ALL": "C", "RUST_BACKTRACE": "0"}


def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def json_value(raw):
    def invalid_constant(value):
        raise ValueError("non-finite JSON value: " + value)
    return json.loads(raw, object_pairs_hook=object_pairs, parse_constant=invalid_constant)


def read_source_review():
    pinned(SOURCE_REVIEW_PATH, SOURCE_REVIEW_SHA256, 1024 * 1024)
    if EXTERNAL_SOURCE_REVIEW:
        import current_source_review
        return current_source_review.load_external(SOURCE_REVIEW_PATH, SOURCE_REVIEW_SHA256,
                                                   ROOT, Path(os.environ["F1_HEPTA_SOURCE_ROOT"]))
    return json_value(SOURCE_REVIEW_PATH.read_bytes())


EXTERNAL_SOURCE_REVIEW = "F1_SOURCE_REVIEW_PATH" in os.environ
require(EXTERNAL_SOURCE_REVIEW == ("F1_SOURCE_REVIEW_SHA256" in os.environ)
        == ("F1_HEPTA_SOURCE_ROOT" in os.environ), "complete explicit current source review binding required")
SOURCE_REVIEW_PATH = Path(os.environ["F1_SOURCE_REVIEW_PATH"]) if EXTERNAL_SOURCE_REVIEW else HERE / "source-review.json"
SOURCE_REVIEW_SHA256 = os.environ["F1_SOURCE_REVIEW_SHA256"] if EXTERNAL_SOURCE_REVIEW else sha(SOURCE_REVIEW_PATH)
SOURCE_REVIEW = read_source_review()
DESKTOP, HEPTA = SOURCE_REVIEW["desktop"], SOURCE_REVIEW["hepta"]
SOURCES = {"desktop": DESKTOP, "hepta": HEPTA}


def input_file(directory, record, limit):
    require(isinstance(record, dict), "file identity must be an object")
    text = record.get("path", "")
    require(isinstance(text, str) and text and "\\" not in text, "invalid frozen path")
    relative = Path(text)
    require(not relative.is_absolute() and all(part not in ("", ".", "..") for part in text.split("/")),
            "frozen input path must be a normalized relative path")
    path = directory / relative
    require(path.resolve(strict=True).is_relative_to(directory.resolve(strict=True)), "input escapes frozen directory")
    pinned(path, record.get("sha256"), limit)
    require(type(record.get("bytes")) is int and path.stat().st_size == record["bytes"], "input byte count mismatch")
    return path


def validate_build_sources(receipt, kind):
    built = receipt.get("build_sources")
    required = {"desktop"} if kind == "kernel" else set(SOURCES)
    require(isinstance(built, dict) and set(built) == required, "actual build source identities missing")
    for name, identity in built.items():
        require(isinstance(identity, dict) and isinstance(identity.get("head"), str)
                and re.fullmatch("[0-9a-f]{40}", identity["head"])
                and identity.get("tree") == SOURCES[name]["tree"], "build source tree differs from reviewed content")


def frozen_inputs(path, digest):
    pinned(path, digest, 512 * 1024)
    value = json_value(path.read_bytes())
    require(isinstance(value, dict), "input manifest must be an object")
    require(value.get("schema") == "hepta.native-original-runtime-input.v1", "unknown input schema")
    require(value.get("sources") == SOURCES, "unreviewed Desktop/Hepta source pair")
    require(value.get("kernel_profile") == "ordinary-os", "ordinary OS kernel required; ktest is not runtime evidence")
    review = read_source_review()
    require(value.get("source_files") == review["source_files"], "reviewed original-owner source identities differ")
    records = value.get("binaries", {})
    require(isinstance(records, dict) and set(records) == set(BINARIES) | {"kernel"},
            "exactly kernel, Agentd, fixture and observer inputs required")
    files = {name: input_file(path.parent, record, 64 * 1024**2 if name == "kernel" else 1024**3)
             for name, record in records.items()}
    require(len({str(file.resolve()) for file in files.values()}) == 4, "distinct input binary paths required")
    receipts = value.get("build_receipts", {})
    require(isinstance(receipts, dict) and set(receipts) == {"kernel", "userspace"},
            "kernel and original userspace build receipts required")
    for name, record in receipts.items():
        receipt = json_value(input_file(path.parent, record, 4 * 1024**2).read_bytes())
        require(isinstance(receipt, dict), "build receipt must be an object")
        require(receipt.get("schema") == "hepta.native-original-runtime-build.v1", "unknown build receipt")
        require(receipt.get("sources") == SOURCES and receipt.get("built") is True,
                "build receipt has no reviewed successful build identity")
        validate_build_sources(receipt, name)
        expected = {key: records[key]["sha256"] for key in (["kernel"] if name == "kernel" else BINARIES)}
        require(receipt.get("binary_sha256") == expected, "build receipt does not bind these exact binaries")
        commands = receipt.get("commands")
        require(isinstance(commands, list) and commands
                and all(isinstance(command, list) and command and all(isinstance(arg, str) and arg for arg in command)
                        for command in commands), "build command evidence missing")
        require(receipt.get("source_clean") is True, "build receipt does not attest clean original sources")
        if name == "kernel":
            require(receipt.get("kernel_profile") == "ordinary-os", "kernel build receipt is not an ordinary OS build")
    return value, files


def stage_closure(binaries, payload, readelf, library_dirs):
    """Resolve data with readelf; do not use ldd or execute any input ELF."""
    infos, libraries, pending = {}, {}, []
    for name, binary in binaries.items():
        info = abi.elf_info(binary, readelf)
        require(info["interpreter"] == "/lib64/ld-linux-x86-64.so.2", "unexpected " + name + " interpreter")
        infos[name] = info
        pending.extend(info["needed"])
    pending.append("ld-linux-x86-64.so.2")
    while pending:
        name = pending.pop(0)
        if name in libraries:
            continue
        require(len(libraries) < 64, "runtime library closure too large")
        paths = [(directory / name).resolve(strict=True) for directory in library_dirs if (directory / name).exists()]
        require(paths, "unresolved runtime library: " + name)
        source = paths[0]
        require(source.is_file() and 0 < source.stat().st_size <= 64 * 1024**2, "invalid library input")
        digest = sha(source)
        require(all(candidate.is_file() and sha(candidate) == digest for candidate in paths),
                "ambiguous differing runtime library: " + name)
        target = payload / "lib/x86_64-linux-gnu" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(0o555)
        pinned(target, digest, 64 * 1024**2)
        info = abi.elf_info(target, readelf)
        require(info["interpreter"] in (None, "/lib64/ld-linux-x86-64.so.2"), "library names unexpected interpreter")
        libraries[name] = {"host_path": str(source), "guest_path": "/lib/x86_64-linux-gnu/" + name,
                           "bytes": target.stat().st_size, "sha256": digest, "elf": info}
        pending.extend(info["needed"])
    (payload / "lib64").mkdir()
    shutil.copyfile(payload / "lib/x86_64-linux-gnu/ld-linux-x86-64.so.2", payload / "lib64/ld-linux-x86-64.so.2")
    (payload / "lib64/ld-linux-x86-64.so.2").chmod(0o555)
    return {"binaries": infos, "libraries": libraries}


def build_initramfs(original, probe, nonce):
    require(re.fullmatch("[0-9a-f]{64}", nonce) is not None, "invalid nonce")
    entries = cpio_codec.unpack(gzip.decompress(original))
    require(cpio_codec.unpack(cpio_codec.pack(entries)) == entries, "original cpio roundtrip mismatch")
    reserved = ("lib", "lib64", "payload", "state", "bin/agentd-runtime-probe")
    require(all(name.lstrip("./") not in reserved for name, _, _ in entries), "unexpected original runtime path")
    script = (
        '/bin/busybox mkdir -p /payload /state\n'
        '/bin/busybox mount -t ext2 -o ro /dev/vda /payload\n'
        '/bin/busybox mount -t ext2 -o rw /dev/vdb /state\n'
        '/bin/busybox ln -s /payload/lib /lib\n'
        '/bin/busybox ln -s /payload/lib64 /lib64\n'
        f'if /bin/agentd-runtime-probe {nonce}; then runtime_code=0; else runtime_code=$?; fi\n'
        '/bin/busybox sync\n'
        f'echo "HEPTA_RUNTIME_HARNESS nonce={nonce} exit=$runtime_code"\n'
    ).encode()
    changed, found = [], 0
    for name, fields, content in entries:
        if name.lstrip("./") == "init":
            require(content.count(abi.BOOT) == 1 and b"set -eu" in content, "ambiguous original init")
            content = content.replace(abi.BOOT, script + abi.BOOT)
            found += 1
        changed.append((name, fields, content))
    require(found == 1, "missing original init")
    fields = [max(item[1][0] for item in entries) + 1, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
    changed.append(("bin/agentd-runtime-probe", fields, probe))
    packed = cpio_codec.pack(changed)
    require(len(cpio_codec.unpack(packed)) == len(entries) + 1, "changed initramfs entry set")
    return gzip.compress(packed, mtime=0)


def positive_integer(value):
    return type(value) is int and 0 < value < 2**64


def validate_records(stdout):
    require(0 < len(stdout) <= STDOUT_LIMIT and stdout.endswith(b"\n"), "incomplete or excessive fixture stdout")
    raw_lines = stdout.decode("utf-8", "strict").splitlines()
    require(0 < len(raw_lines) <= 256, "fixture record count outside bound")
    records = [json_value(line) for line in raw_lines]
    require(all(isinstance(record, dict) for record in records), "fixture record must be an object")
    first, final = records[0], records[-1]
    require(first.get("event") == "trusted_endpoint" and first.get("agent_id") == AGENT
            and first.get("evidence_class") == "original_agentd_probe_in_progress_not_pass"
            and first.get("peer_uid") == 0 and type(first.get("peer_uid")) is int,
            "missing original registered endpoint")
    socket = first.get("socket_path")
    require(isinstance(socket, str) and socket.startswith("/state/probe/fleet/")
            and ".." not in socket.split("/") and "//" not in socket, "endpoint outside private guest fleet")
    old, new = final.get("old_spawn"), final.get("new_spawn")
    require(positive_integer(old) and positive_integer(new) and new > old and first.get("spawn_generation") == old,
            "invalid original/replacement spawn generations")
    require(final.get("event") == "acceptance_pass"
            and final.get("evidence_class") == "original_agentd_process_readonly_observer"
            and final.get("checks") == EXPECTED_CHECKS, "original lifecycle acceptance checks missing")
    require(all(final.get(flag) is False for flag in ("objective_submission", "model_turn", "device_effect")),
            "no-turn fixture scope changed")
    middle = records[1:-1]
    require([record.get("event") for record in middle] == ["phase_observed", "phase_observed", "ready_window",
                                                            "phase_observed", "phase_observed", "phase_observed"],
            "original fixture lifecycle record order changed")
    require(middle[2].get("hold_seconds") == 0 and type(middle[2].get("hold_seconds")) is int,
            "native fixture must use bounded zero hold")
    phases = [middle[index]["observation"] for index in (0, 1, 3, 4, 5)]
    expected = [(old, "starting", 0), (old, "running", 1), (old, "draining", 2),
                (new, "running", 1), (new, "running", 1)]
    pids = []
    for observation, (spawn, phase, offset) in zip(phases, expected):
        require(isinstance(observation, dict), "observation must be an object")
        health = observation.get("health", {})
        require(isinstance(health, dict), "health projection must be an object")
        require(observation.get("agent_id") == AGENT and type(observation.get("spawn_generation")) is int
                and observation["spawn_generation"] == spawn and type(observation.get("current_generation")) is int
                and observation["current_generation"] == spawn + offset, "observed generation mismatch")
        require(health.get("lifecycle") == phase and positive_integer(health.get("process_id"))
                and health.get("fenced") is False and health.get("ready") is (phase == "running"),
                "observed lifecycle, readiness or PID mismatch")
        capabilities, events = observation.get("capabilities"), observation.get("events")
        require(isinstance(capabilities, list) and len(capabilities) <= 256
                and all(isinstance(item, dict) and item.get("id") not in
                        ("objective.start", "automation.external_effect", "intelligence.canonical_v1") for item in capabilities),
                "unexpected production capability or unbounded projection")
        require(isinstance(events, list) and len(events) <= 256 and all(isinstance(event, dict) for event in events)
                and any(event.get("lifecycle") == "starting" and type(event.get("generation")) is int
                        and event["generation"] == spawn for event in events), "original starting history missing")
        pids.append(health["process_id"])
    require(pids[0] == pids[1] == pids[2] and pids[3] == pids[4] and pids[3] != pids[0],
            "PID changed within a spawn or restart did not replace original process")
    return {"old_spawn": old, "new_spawn": new, "old_pid": pids[0], "new_pid": pids[3],
            "checks": EXPECTED_CHECKS, "record_count": len(records)}


def captured_streams(raw, nonce):
    """Decode bounded diagnostics on failure too; this never grants a pass."""
    lines = raw.replace(b"\r\n", b"\n").split(b"\n")
    streams = {}
    for name, limit in (("STDOUT", STDOUT_LIMIT), ("STDERR", STDERR_LIMIT)):
        prefix = f"HEPTA_RUNTIME_{name} nonce={nonce} hex=".encode()
        matches = [line[len(prefix):] for line in lines if line.startswith(prefix)]
        require(len(matches) == 1, "missing or repeated fixture stream")
        encoded = matches[0]
        require(len(encoded) <= limit * 2 and len(encoded) % 2 == 0 and re.fullmatch(b"[0-9a-f]*", encoded),
                "invalid or excessive fixture stream encoding")
        streams[name.lower()] = bytes.fromhex(encoded.decode("ascii"))
    return streams


def observe(raw, code, timed_out, excessive, nonce):
    require(code == 33 and not timed_out and not excessive, "QEMU did not finish a bounded ordinary boot")
    lines = raw.replace(b"\r\n", b"\n").split(b"\n")
    require(lines.count(b"TRILLIONNIUM_A01_INIT_BEGIN") == 1 and lines.count(b"TRILLIONNIUM_A01_BOOT_OK") == 1,
            "ordinary init/boot markers missing or repeated")
    require(b"kernel panic" not in raw.lower(), "kernel panic in runtime boot")
    markers = [line for line in lines if line.startswith(b"HEPTA_RUNTIME_")]
    require(len(markers) == 5, "unexpected runtime marker count")
    require(markers[0] == f"HEPTA_RUNTIME_BEGIN nonce={nonce}".encode()
            and markers[3] == f"HEPTA_RUNTIME_CHILD nonce={nonce} kind=exit code=0".encode()
            and markers[4] == f"HEPTA_RUNTIME_HARNESS nonce={nonce} exit=0".encode(),
            "runtime nonce, child exit, or launcher exit mismatch")
    for index, name in enumerate(("STDOUT", "STDERR"), 1):
        prefix = f"HEPTA_RUNTIME_{name} nonce={nonce} hex=".encode()
        require(markers[index].startswith(prefix), "missing or reordered fixture stream")
    streams = captured_streams(raw, nonce)
    require(streams["stderr"] == b"", "successful original fixture wrote unexpected stderr")
    observation = validate_records(streams["stdout"])
    return observation, streams


def qemu_argv(qemu, out, memory_mib):
    return [qemu, "-kernel", str(out / "kernel.elf"), "-initrd", str(out / "initramfs.cpio.gz"),
            "-machine", "q35", "-accel", "tcg", "-cpu", "max", "-bios", str(out / "bios.bin"),
            "-m", str(memory_mib) + "M", "-smp", "1", "-nodefaults", "-no-user-config",
            "-no-reboot", "-nographic", "-display", "none", "-monitor", "none", "-serial", "stdio", "-nic", "none",
            "-append", "earlycon console=ttyS0 loglevel=warn SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --",
            "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04",
            "-drive", "if=none,format=raw,id=runtime_payload,readonly=on,file=" + str(out / "payload.raw"),
            "-device", "virtio-blk-pci,bus=pcie.0,addr=0x7,drive=runtime_payload,disable-legacy=on,disable-modern=off",
            "-drive", "if=none,format=raw,id=runtime_state,file=" + str(out / "state.raw"),
            "-device", "virtio-blk-pci,bus=pcie.0,addr=0x8,drive=runtime_state,disable-legacy=on,disable-modern=off"]


def execute(args, out, report):
    require(120 <= args.timeout <= 900, "guest deadline must be 120..900 seconds")
    require(2048 <= args.memory_mib <= 8192, "guest memory must be 2048..8192 MiB")
    manifest, files = frozen_inputs(args.input_manifest, args.expected_input_manifest_sha256)
    pinned(args.initramfs, abi.INITRAMFS_SHA, abi.LIMIT)
    pinned(args.bios, abi.BIOS_SHA, 2 * 1024**2)
    require(not out.exists() and not out.is_symlink() and "," not in str(out), "output must be new and comma-free")
    require(not out.resolve().is_relative_to(args.input_manifest.parent.resolve()), "output must be outside frozen input")
    tools = {name: abi.tool(getattr(args, name)) for name in ("qemu", "mkfs", "readelf", "cc")}
    pinned(Path(tools["qemu"]), args.expected_qemu_sha256, 1024**3)
    out.mkdir(parents=True, mode=0o700)
    report["evidence_directory_created"] = True
    save(out / "frozen-input-manifest.json", manifest)
    for name, record in manifest["build_receipts"].items():
        source = input_file(args.input_manifest.parent, record, 4 * 1024**2)
        shutil.copyfile(source, out / (name + "-build-receipt.json"))
        pinned(out / (name + "-build-receipt.json"), record["sha256"], 4 * 1024**2)
    report.update(input_manifest_sha256=args.expected_input_manifest_sha256,
                  input_source_attestation="caller-retained build receipts; fixed reviewed source identities checked; not remote attestation",
                  tool_identities={name: {"path": path, "sha256": sha(Path(path))} for name, path in tools.items()})
    payload = out / "payload-root"
    (payload / "bin").mkdir(parents=True)
    copies = {}
    for name, filename in BINARIES.items():
        copies[name] = payload / "bin" / filename
        shutil.copyfile(files[name], copies[name])
        copies[name].chmod(0o555)
        pinned(copies[name], manifest["binaries"][name]["sha256"], 1024**3)
    save(out / "runtime-inputs.json", stage_closure(copies, payload, tools["readelf"], args.library_dir))
    for filename, source, digest in (("kernel.elf", files["kernel"], manifest["binaries"]["kernel"]["sha256"]),
                                     ("bios.bin", args.bios, abi.BIOS_SHA)):
        shutil.copyfile(source, out / filename)
        pinned(out / filename, digest, 64 * 1024**2)
    compiler = [tools["cc"], "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror", "-static",
                str(HERE / "agentd_runtime_probe.c"), "-o", str(out / "agentd-runtime-probe")]
    abi.command(compiler, out, "compile-guest-probe", 120)
    require(abi.elf_info(out / "agentd-runtime-probe", tools["readelf"])["interpreter"] is None, "guest launcher must be static")
    nonce = os.urandom(32).hex()
    (out / "initramfs.cpio.gz").write_bytes(build_initramfs(args.initramfs.read_bytes(),
                                                         (out / "agentd-runtime-probe").read_bytes(), nonce))
    total = sum(path.stat().st_size for path in payload.rglob("*") if path.is_file())
    payload_bytes = max(1024**3, (total * 2 + 256 * 1024**2 + 4095) // 4096 * 4096)
    require(shutil.disk_usage(out).free >= payload_bytes + STATE_BYTES + 256 * 1024**2, "insufficient free disk")
    formatters = []
    for name, size in (("payload", payload_bytes), ("state", STATE_BYTES)):
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
    save(out / "invocation.json", {"argv": argv, "formatters": formatters, "compiler": compiler, "nonce": nonce,
                                  "fixture_argv": ["/payload/bin/hepta-original-observer-probe", "/payload/bin/codex-hepta-agentd",
                                                   "/payload/bin/hepta-observe", "/state/probe", "0"],
                                  "fixture_environment": ENVIRONMENT, "state_before_sha256": state_before,
                                  "read_only_payload_sha256": payload_sha, "timeout_seconds": args.timeout})
    report.update(nonce=nonce, kernel_sha256=sha(out / "kernel.elf"), initramfs_sha256=sha(out / "initramfs.cpio.gz"),
                  launcher_sha256=sha(out / "agentd-runtime-probe"), payload_sha256=payload_sha,
                  state_before_sha256=state_before, state_bytes=STATE_BYTES)
    pinned(Path(tools["qemu"]), args.expected_qemu_sha256, 1024**3)
    report["execution_attempted"] = True
    raw, code, timed_out, excessive = abi.run_qemu(argv, out, args.timeout, report)
    unchanged = (sha(out / "payload.raw") == payload_sha
                 and all(sha(path) == manifest["binaries"][name]["sha256"] for name, path in files.items())
                 and sha(args.input_manifest) == args.expected_input_manifest_sha256
                 and sha(args.initramfs) == abi.INITRAMFS_SHA and sha(args.bios) == abi.BIOS_SHA
                 and all(sha(args.input_manifest.parent / record["path"]) == record["sha256"]
                         for record in manifest["build_receipts"].values()))
    report.update(qemu_exit=code, timed_out=timed_out, serial_excessive=excessive, inputs_unchanged=unchanged,
                  serial_sha256=hashlib.sha256(raw).hexdigest(), state_after_sha256=sha(out / "state.raw"))
    try:
        for name, content in captured_streams(raw, nonce).items():
            (out / ("fixture." + name)).write_bytes(content)
    except ValueError as error:
        report["diagnostic_decode_error"] = str(error)
    observation, _ = observe(raw, code, timed_out, excessive, nonce)
    require(unchanged, "frozen input or read-only payload changed")
    require(report["state_after_sha256"] != state_before, "original runtime did not write its fresh state image")
    report.update(passed=True, original_owner_runtime_lifecycle_verified=True, observed_lifecycle=observation)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--input-manifest", type=Path)
    parser.add_argument("--expected-input-manifest-sha256")
    parser.add_argument("--initramfs", type=Path)
    parser.add_argument("--bios", type=Path, default=Path("/usr/share/seabios/bios-256k.bin"))
    parser.add_argument("--qemu", default="qemu-system-x86_64")
    parser.add_argument("--expected-qemu-sha256")
    parser.add_argument("--mkfs", default="mkfs.ext2")
    parser.add_argument("--readelf", default="readelf")
    parser.add_argument("--cc", default="gcc")
    parser.add_argument("--library-dir", type=Path, action="append")
    parser.add_argument("--memory-mib", type=int, default=4096)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = {"schema": "hepta.native-original-runtime-result.v1", "passed": False, "executed": False,
              "original_owner_runtime_lifecycle_verified": False, "production": False,
              "f1_completed": False, "g2_completed": False, "f_completed": False,
              "crash_durability_verified": False, "hardware_verified": False, "sources": SOURCES,
              "scope": "unchanged original registry/supervisor -> Agentd runtime -> original read-only lifecycle fixture",
              "started_at_utc": datetime.now(timezone.utc).isoformat()}
    if not args.execute:
        report["status"] = "disabled; explicit --execute and frozen real build inputs required"
        print(json.dumps(report, sort_keys=True))
        return 0
    for name in ("input_manifest", "expected_input_manifest_sha256", "initramfs", "expected_qemu_sha256", "output"):
        if getattr(args, name) is None:
            parser.error("--execute requires --" + name.replace("_", "-"))
    out = args.output.absolute()
    args.library_dir = args.library_dir or [Path("/lib/x86_64-linux-gnu"), Path("/usr/lib/x86_64-linux-gnu"), Path("/lib64")]
    try:
        execute(args, out, report)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report["error"] = f"{type(error).__name__}: {error}"
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["runner_sha256"] = sha(Path(__file__))
    report["candidate_source_sha256"] = {str(path.relative_to(ROOT)): sha(path) for path in
        (HERE / "agentd_runtime_probe.c", HERE / "source-review.json", ABI / "run_agentd_abi.py", ABI / "cpio_codec.py")}
    if report.get("evidence_directory_created") is True:
        save(out / "result.json", report)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
