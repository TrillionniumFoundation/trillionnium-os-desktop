#!/usr/bin/env python3
"""Execute the source-bound original Hepta owner in the G2 initial-role guest.

No C owner, replacement writer, signer or FinalUse consumer is generated. The
actual original build receipt and complete retained product-kernel pipeline are
required. Each finite scenario uses a fresh retained ext2 disk. Native grants,
Root installation and writer creation remain entirely inside the original entry.
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import stat
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import native_owner_evidence as oracle
import native_owner_inputs as inputs

ROOT = HERE.parents[2]
STATE_BYTES = 256 * 1024**2
ENV = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
require = oracle.require


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def freeze_bytes(path, content, mode=0o444):
    require(not path.exists() and not path.is_symlink(), "retained artifact must be new")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(content)
    path.chmod(mode)
    digest = hashlib.sha256(content).hexdigest()
    require(inputs.sha(path) == digest, "input changed during evidence freezing")
    return {"path": str(path), "bytes": len(content), "sha256": digest}


def retain_files(directory, files):
    result = {}
    for relative, source in files.items():
        require(not Path(relative).is_absolute() and ".." not in Path(relative).parts, "retained relative path escaped")
        result[relative] = freeze_bytes(directory / relative, inputs.read(source, 512 * 1024**2))
    return result


def tool(path, expected=None):
    selected = shutil.which(str(path))
    require(selected is not None, "required native runner tool is unavailable: " + str(path))
    selected = Path(selected).resolve(strict=True)
    content = inputs.read(selected, 1024**3, expected)
    require(os.access(selected, os.X_OK), "runner tool is not executable")
    return selected, {"path": str(selected), "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}


def build_initramfs(original, owner, plan, replay):
    require(len(original) <= 8 * 1024**2 and 0 < len(owner) <= inputs.MAX_OWNER_BYTES,
            "original base or owner exceeds the unchanged input bounds")
    raw = gzip.decompress(original)
    require(len(raw) <= 64 * 1024**2, "original initramfs exceeds its uncompressed bound")
    entries = replay.unpack(raw)
    require(replay.unpack(replay.pack(entries)) == entries, "original cpio does not roundtrip")
    require(sum(name.lstrip("./") == "test" and stat.S_ISDIR(fields[1]) for name, fields, _ in entries) == 1,
            "original base initramfs must contain one test directory")
    additions = (("test/hepta-g2-owner", 0o100555, owner),
                 ("test/hepta-g2-run.json", 0o100400, (json.dumps(plan, sort_keys=True, separators=(",", ":")) + "\n").encode()))
    names = {name.lstrip("./") for name, _, _ in entries}
    inode = max(fields[0] for _, fields, _ in entries)
    modified = list(entries)
    for name, mode, content in additions:
        require(name not in names, "original image already contains an owner or run plan")
        inode += 1
        fields = [inode, mode, 0, 0, 1, 0, len(content), 0, 0, 0, 0, len(name.encode()) + 1, 0]
        modified.append((name, fields, content))
    packed = replay.pack(modified)
    require(len(packed) <= 64 * 1024**2 and replay.unpack(packed) == modified,
            "original owner/plan image exceeds the unchanged cpio bound or changed bytes")
    return gzip.compress(packed, mtime=0)


def format_state(directory, mkfs, identity):
    image = directory / "state.raw"
    require(shutil.disk_usage(directory).free >= 2 * STATE_BYTES + 256 * 1024**2, "insufficient disk for original state and retained preimage")
    with image.open("xb") as stream:
        stream.truncate(STATE_BYTES)
    argv = [str(mkfs), "-F", "-q", "-b", "4096", "-I", "256", "-m", "0", "-O", "none,filetype", str(image)]
    record = {"argv": argv, "tool": identity, "exit_code": None, "timed_out": False}
    save(directory / "format-state.json", record)
    started = time.monotonic()
    with (directory / "format-state.log").open("xb") as log:
        try:
            process = subprocess.run(argv, env=ENV, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                     timeout=120, check=False)
            record["exit_code"] = process.returncode
        except subprocess.TimeoutExpired:
            record["timed_out"] = True
    record["elapsed_seconds"] = round(time.monotonic() - started, 3)
    save(directory / "format-state.json", record)
    require(record["exit_code"] == 0 and record["timed_out"] is False, "actual ext2 state formatting failed")
    with image.open("rb") as stream:
        stream.seek(1024)
        superblock = stream.read(1024)
    require(len(superblock) == 1024 and struct.unpack_from("<H", superblock, 56)[0] == 0xEF53
            and struct.unpack_from("<I", superblock, 24)[0] == 2
            and struct.unpack_from("<H", superblock, 88)[0] == 256
            and struct.unpack_from("<I", superblock, 92)[0] == 0
            and struct.unpack_from("<I", superblock, 96)[0] == 2
            and struct.unpack_from("<I", superblock, 100)[0] == 0,
            "actual state filesystem differs from original 4096-byte ext2/no-journal profile")
    before = inputs.sha(image)
    prior = directory / "state-before.raw"
    shutil.copyfile(image, prior)
    prior.chmod(0o444)
    require(inputs.sha(prior) == inputs.sha(image) == before and image.stat().st_size == STATE_BYTES,
            "fresh ext2 state changed before execution")
    return {"path": str(image), "bytes": STATE_BYTES, "before_sha256": before,
            "retained_preimage": str(prior), "ext2_uuid": superblock[104:120].hex(),
            "failure_layer": "guest process lifecycle on a retained QEMU raw ext2 disk; not host power loss"}


def qemu_argv(binary, output, directory, with_state):
    argv = [str(binary), "-kernel", str(output / "product-kernel.elf"), "-initrd", str(directory / "initramfs.cpio.gz"),
            "-append", "earlycon console=ttyS0 loglevel=info rdinit=/test/hepta-g2-owner SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --",
            "-machine", "q35", "-accel", "tcg", "-cpu", "max", "-bios", str(output / "bios.bin"),
            "-m", "512M", "-smp", "1", "-nodefaults", "-no-user-config", "-no-reboot", "-nographic",
            "-display", "none", "-monitor", "none", "-serial", "stdio", "-nic", "none",
            "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"]
    if with_state:
        argv += ["-drive", "if=none,format=raw,id=hepta_g2_state,file=" + str(directory / "state.raw"),
                 "-device", "virtio-blk-pci,bus=pcie.0,addr=0x8,drive=hepta_g2_state,disable-legacy=on,disable-modern=off"]
    return argv


def run_qemu(argv, directory, timeout, identity):
    """Bound both wall time and serial bytes without a blocking stdout reader."""
    record = {"argv": argv, "qemu": identity, "timeout_seconds": timeout, "raw_exit_code": None,
              "timed_out": False, "serial_excessive": False, "profile": {"machine": "q35", "accel": "tcg", "cpu": "max",
              "memory_mib": 512, "vcpus": 1, "network": False}, "artifacts": {}}
    for option in ("-kernel", "-initrd", "-bios"):
        path = Path(argv[argv.index(option) + 1])
        record["artifacts"][option] = {"path": str(path), "bytes": path.stat().st_size, "sha256": inputs.sha(path)}
    save(directory / "qemu.json", record)
    started = time.monotonic()
    process = subprocess.Popen(argv, env=ENV, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               start_new_session=True)
    selector = selectors.DefaultSelector()
    total, eof = 0, False
    try:
        selector.register(process.stdout, selectors.EVENT_READ)
        with (directory / "serial.log").open("xb") as log:
            while True:
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    record["timed_out"] = True
                    break
                for key, _ in selector.select(min(remaining, 0.5)):
                    content = os.read(key.fd, 65536)
                    if not content:
                        selector.unregister(key.fd)
                        eof = True
                        continue
                    allowed = min(len(content), oracle.MAX_SERIAL_BYTES - total)
                    log.write(content[:allowed])
                    total += allowed
                    if allowed != len(content):
                        record["serial_excessive"] = True
                        break
                if record["serial_excessive"] or (eof and process.poll() is not None):
                    break
    finally:
        selector.close()
        if record["timed_out"] or record["serial_excessive"] or process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=10)
        process.stdout.close()
        record.update(raw_exit_code=process.returncode, elapsed_seconds=round(time.monotonic() - started, 3))
        raw = (directory / "serial.log").read_bytes()
        record.update(serial_sha256=hashlib.sha256(raw).hexdigest(), serial_bytes=len(raw))
        save(directory / "qemu.json", record)
    for artifact in record["artifacts"].values():
        path = Path(artifact["path"])
        require(path.stat().st_size == artifact["bytes"] and inputs.sha(path) == artifact["sha256"],
                "actual boot input changed during native execution")
    return raw, record


def rejection(raw, record, reason):
    require(reason in ("manifest-byte-mismatch", "truncated-snapshot"), "unrecognized loader negative control")
    text = oracle.ANSI.sub("", raw.decode("utf-8", errors="replace")).replace("\r", "")
    lines = text.splitlines()
    marker = "[hepta-g2] rejected initial image: " + reason
    require(type(record["raw_exit_code"]) is int and record["raw_exit_code"] == 65 and record["timed_out"] is False
            and record["serial_excessive"] is False and lines.count(marker) == 1
            and sum("rejected initial image:" in line for line in lines) == 1
            and text.count("failed to run the init process") == 1
            and not any("trusted initial image committed:" in line or "initial roles activated:" in line
                        or line.startswith(("HEPTA_G2_", "G1D_", "G1C_")) for line in lines),
            "altered original ELF did not fail exactly before any image commit, role or owner execution")
    require(all(line == marker for line in lines if line.startswith("[hepta-g2]")), "unknown G2 negative-control kernel record")
    return {"passed": True, "reason": reason, "rejected_before_any_role_resume": True,
            "native_owner_verified": False, "g2_complete": False}


def execute(args, report):
    review = inputs.review_inputs(args.source_review, args.expected_source_review_sha256)
    roots = {"desktop": args.desktop_source, "hepta": args.hepta_source}
    builder = inputs.load_module("original_native_entry_builder", HERE / "build_original_entry.py")
    snapshots = inputs.source_snapshots(roots, review, builder)
    harness_head = builder.git(ROOT, "rev-parse", "HEAD").decode().strip()
    harness_tree = builder.git(ROOT, "rev-parse", "HEAD^{tree}").decode().strip()
    harness = builder.source_snapshot(ROOT, harness_head, harness_tree)
    shape, ordinary, replay = inputs.original_helpers(roots["desktop"])
    owner_receipt, owner, info, owner_files = inputs.owner_build(args.owner_build_receipt,
        args.expected_owner_build_receipt_sha256, args.owner_elf, review, snapshots, shape, roots["hepta"])
    pipeline, kernel, base, kernel_files = inputs.kernel_build(args.kernel_pipeline,
        args.expected_kernel_pipeline_sha256, review, owner, ordinary)
    bios = inputs.read(args.bios, 2 * 1024**2, replay.SEABIOS_SHA)
    qemu, qemu_identity = tool(args.qemu, args.expected_qemu_sha256)
    mkfs, mkfs_identity = tool(args.mkfs)
    selected = args.scenario or list(oracle.SUPPORTED_SCENARIOS)
    require(len(set(selected)) == len(selected), "scenario selection repeats a boot")
    debugfs, debugfs_identity = None, None
    if any(name in oracle.CONTINUITY_SCENARIOS for name in selected):
        debugfs, debugfs_identity = tool(args.debugfs)
    output = args.output
    require(output.is_absolute() and output.parent.is_dir() and output.parent.resolve(strict=True) == output.parent
            and not output.exists() and not output.is_symlink() and "," not in str(output), "new canonical comma-free output required")
    for protected in (*roots.values(), ROOT, args.owner_build_receipt.parent, args.kernel_pipeline):
        require(not output.is_relative_to(protected) and not protected.is_relative_to(output),
                "native evidence must not overlap frozen sources or build inputs")
    require(1 <= args.timeout <= 120, "unchanged G1d guest deadline must remain 1..120 seconds")
    output.mkdir(mode=0o700)
    report["output_created"] = True
    freeze_bytes(output / "source-review.json",
                 inputs.read(args.source_review, 1024**2, args.expected_source_review_sha256))
    save(output / "source-before.json", snapshots)
    save(output / "harness-source-before.json", harness)
    report.update(stage="inputs_frozen", sources={name: review[name] for name in roots},
                  harness_source={"head": harness_head, "tree": harness_tree}, original_entry=review["entry"],
                  original_elf_shape=info, source_review_sha256=args.expected_source_review_sha256,
                  owner_build_receipt_sha256=args.expected_owner_build_receipt_sha256,
                  kernel_pipeline_sha256=args.expected_kernel_pipeline_sha256,
                  input_attestation="caller-retained actual local build records and complete checked sources; not remote attestation",
                  tool_identities={"qemu": qemu_identity, "mkfs": mkfs_identity})
    if debugfs_identity is not None:
        report["tool_identities"]["debugfs"] = debugfs_identity
    report["retained_owner_build"] = retain_files(output / "owner-build", owner_files)
    report["retained_kernel_build"] = retain_files(output / "kernel-build-evidence", kernel_files)
    report["artifacts"] = {"owner": freeze_bytes(output / "original-owner.elf", owner),
                           "kernel": freeze_bytes(output / "product-kernel.elf", kernel),
                           "base_initramfs": freeze_bytes(output / "base-initramfs.cpio.gz", base),
                           "bios": freeze_bytes(output / "bios.bin", bios),
                           "qemu_binary": freeze_bytes(output / "source-qemu-binary", qemu.read_bytes())}
    if debugfs is not None:
        report["artifacts"]["debugfs_binary"] = freeze_bytes(output / "source-debugfs-binary", debugfs.read_bytes())
    save(output / "result.json", report)
    changed = bytearray(owner)
    changed[-1] ^= 1
    controls = [("manifest-byte-mismatch", bytes(changed)), ("truncated-snapshot", owner[:-1])]
    report["controls"], report["scenarios"] = {}, {}
    for name, actual_owner in controls + [(name, owner) for name in selected]:
        is_control = name not in oracle.SUPPORTED_SCENARIOS
        directory = output / name
        directory.mkdir(mode=0o700)
        nonce = os.urandom(32).hex()
        plan = {"schema_version": 1, "scenario": selected[0] if is_control else name, "nonce": nonce}
        # This root-only file is an acceptance plan, never Root installation,
        # registration, a writer lease, Current, a signer or a FinalUse grant.
        save(directory / "run-plan.json", plan)
        initramfs = build_initramfs(base, actual_owner, plan, replay)
        freeze_bytes(directory / "initramfs.cpio.gz", initramfs)
        result = {"passed": False, "scenario": name, "nonce": nonce,
                  "actual_initial_elf_sha256": hashlib.sha256(actual_owner).hexdigest(), "g2_complete": False}
        if not is_control:
            result["state"] = format_state(directory, mkfs, mkfs_identity)
        report["stage"] = "guest:" + name
        save(directory / "result.json", result)
        save(output / "result.json", report)
        argv = qemu_argv(qemu, output, directory, not is_control)
        report["native_execution_attempted"] = report["native_execution_attempted"] or not is_control
        # This one campaign's wall deadline never changes a finite Root/Host,
        # writer, native grant, watchdog or original four-case deadline.
        deadline = 600 if name == "successor-renewal-v1" else args.timeout
        raw, record = run_qemu(argv, directory, deadline, qemu_identity)
        if not is_control:
            state = directory / "state.raw"
            result["state"]["after_sha256"] = inputs.sha(state)
            result["state"]["after_bytes"] = state.stat().st_size
            require(inputs.sha(directory / "state-before.raw") == result["state"]["before_sha256"],
                    "retained pristine state image changed during guest execution")
        try:
            observed = (rejection(raw, record, name) if is_control else oracle.evaluate(raw, record["raw_exit_code"],
                        record["timed_out"], record["serial_excessive"], name, nonce, info))
            if not is_control:
                require(result["state"]["after_bytes"] == STATE_BYTES
                        and result["state"]["after_sha256"] != result["state"]["before_sha256"],
                        "the original native writer did not change its actual retained ext2 state")
            if name in oracle.CONTINUITY_SCENARIOS:
                import native_owner_state_observations
                physical = native_owner_state_observations.verify(
                    directory / "state.raw", debugfs, debugfs_identity, result["state"]["after_sha256"],
                    observed["root_launch_observations_expected"], directory / "root-launch-observations")
                result["retained_root_observations"] = physical
                native_owner_state_observations.accept_retained_observations(observed, physical)
            result.update(observed)
        except (OSError, ValueError, TypeError, KeyError, UnicodeError, subprocess.SubprocessError) as error:
            result.update(passed=False, error=f"{type(error).__name__}: {error}")
        result["actual_qemu_record_sha256"] = inputs.sha(directory / "qemu.json")
        result["raw_serial_sha256"] = inputs.sha(directory / "serial.log")
        save(directory / "result.json", result)
        report["controls" if is_control else "scenarios"][name] = result
        save(output / "result.json", report)
        require(inputs.sha(qemu) == qemu_identity["sha256"] and inputs.sha(mkfs) == mkfs_identity["sha256"],
                "actual native runner tools changed between boots")
        if debugfs is not None:
            require(inputs.sha(debugfs) == debugfs_identity["sha256"], "actual read-only state tool changed between boots")
    after = inputs.source_snapshots(roots, review, builder)
    final_harness = builder.source_snapshot(ROOT, harness_head, harness_tree)
    save(output / "source-after.json", after)
    save(output / "harness-source-after.json", final_harness)
    require(after == snapshots and final_harness == harness, "source or original evidence oracle changed during native execution")
    inputs.review_inputs(args.source_review, args.expected_source_review_sha256)
    inputs.owner_build(args.owner_build_receipt, args.expected_owner_build_receipt_sha256, args.owner_elf,
                       review, snapshots, shape, roots["hepta"])
    inputs.kernel_build(args.kernel_pipeline, args.expected_kernel_pipeline_sha256, review, owner, ordinary)
    for artifact in report["artifacts"].values():
        require(inputs.sha(Path(artifact["path"])) == artifact["sha256"], "retained actual artifact changed")
    passed = all(value["passed"] is True for group in (report["controls"], report["scenarios"]) for value in group.values())
    report.update(passed=passed, stage="complete", source_inputs_unchanged=True, same_product_kernel_all_boots=True,
                  original_native_owner_cycle_verified=passed,
                  bounded_steady_state_verified=passed and "steady-state-v1" in selected,
                  same_boot_authenticated_successor_verified=passed and any(
                      value.get("same_boot_authenticated_successor_verified") is True
                      for value in report["scenarios"].values()),
                  lost_copyout_live_verified=passed and report["scenarios"].get(
                      "lost-copyout-live-v1", {}).get("lost_copyout_live_verified") is True,
                  after_effect_crash_verified=passed and report["scenarios"].get(
                      "manager-exit-before-terminal-v1", {}).get("after_effect_crash_verified") is True,
                  recovered_unknown_without_install_verified=passed and report["scenarios"].get(
                      "manager-exit-before-terminal-v1", {}).get("recovered_unknown_without_install_verified") is True,
                  grant_renewal_verified=passed and report["scenarios"].get(
                      "successor-renewal-v1", {}).get("grant_renewal_verified") is True,
                  history_only_recovery_verified=passed and report["scenarios"].get(
                      "history-only-after-both-owner-exit-v1", {}).get("history_only_recovery_verified") is True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    for name in ("desktop-source", "hepta-source", "source-review", "owner-elf", "owner-build-receipt", "kernel-pipeline", "output"):
        parser.add_argument("--" + name, type=Path)
    for name in ("expected-source-review-sha256", "expected-owner-build-receipt-sha256", "expected-kernel-pipeline-sha256", "expected-qemu-sha256"):
        parser.add_argument("--" + name)
    parser.add_argument("--qemu", default="qemu-system-x86_64")
    parser.add_argument("--mkfs", default="mkfs.ext2")
    parser.add_argument("--debugfs", default="debugfs")
    parser.add_argument("--bios", type=Path, default=Path("/usr/share/seabios/bios-256k.bin"))
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--scenario", choices=oracle.SUPPORTED_SCENARIOS, action="append")
    args = parser.parse_args(argv)
    report = {"schema": "hepta.native-original-owner-result.v1", "passed": False, "stage": "source_admission",
              "native_execution_attempted": False, "original_native_owner_cycle_verified": False,
              "bounded_steady_state_verified": False, "same_boot_authenticated_successor_verified": False,
              "after_effect_crash_verified": False, "lost_copyout_live_verified": False,
              "recovered_unknown_without_install_verified": False, "cross_boot_unknown_preservation_verified": False,
              "grant_renewal_verified": False, "history_only_recovery_verified": False, "repeated_recovery_verified": False,
              "unbounded_persistent_cpu_verified": False, "power_loss_verified": False,
              "hardware_qualification": False, "production_ready": False, "g2_complete": False,
              "started_at_utc": datetime.now(timezone.utc).isoformat()}
    if not args.execute:
        print(json.dumps({**report, "status": "disabled; explicit --execute and original source-bound owner/kernel inputs required"}, sort_keys=True))
        return 0
    for name in ("desktop_source", "hepta_source", "source_review", "owner_elf", "owner_build_receipt", "kernel_pipeline", "output",
                 "expected_source_review_sha256", "expected_owner_build_receipt_sha256", "expected_kernel_pipeline_sha256", "expected_qemu_sha256"):
        if getattr(args, name) is None:
            parser.error("--execute requires --" + name.replace("_", "-"))
    try:
        require(all(getattr(args, name).is_absolute() for name in ("desktop_source", "hepta_source", "source_review", "owner_elf",
                                                                 "owner_build_receipt", "kernel_pipeline", "output", "bios")),
                "absolute original input and output paths required")
        execute(args, report)
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError, AssertionError) as error:
        report.update(passed=False, error=f"{type(error).__name__}: {error}")
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    if report.get("output_created"):
        save(args.output / "result.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
