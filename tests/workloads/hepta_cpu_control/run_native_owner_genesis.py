#!/usr/bin/env python3
"""Execute one explicit original no-head cut and recovery over one raw FD.

This separately enabled campaign preserves all six earlier cases, the two
partial activations and the separate old-boot Unknown campaign. Each of the
three cuts requires its own actual two-VM run and independent evidence output.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess

import native_owner_evidence as e
import native_owner_inputs as inputs
import native_owner_genesis_disk as physical
import native_owner_genesis_evidence as genesis_oracle
import native_owner_genesis_store as material
import native_owner_prior_boot_io as transport
import native_owner_genesis_types as t
import run_native_owner as original


def verify_actual_kill(raw, record, first):
    e.require(type(record["raw_exit_code"]) is int and record["raw_exit_code"] == -signal.SIGKILL
              and record["timed_out"] is False and record["serial_excessive"] is False,
              "actual first no-head VM did not exit from the requested SIGKILL")
    cut = e.obj(record["host_cut"], ("signal", "process_group", "line_offset", "line_bytes", "line_sha256", "original_cut",
                "clock", "observed_at_ns", "kill_call_before_ns", "kill_call_after_ns", "guest_time_inferred"),
                "actual host no-head signal observation")
    e.integer(cut["signal"], "actual host terminating signal", signal.SIGKILL, signal.SIGKILL)
    e.integer(cut["process_group"], "actual VM process group", 1, (1 << 31) - 1)
    start = e.integer(cut["line_offset"], "actual cut byte offset", 0, len(raw))
    size = e.integer(cut["line_bytes"], "actual cut line bytes", 1, e.MAX_EVENT_BYTES + 2)
    e.require(start + size <= len(raw) and hashlib.sha256(raw[start:start + size]).hexdigest() == cut["line_sha256"]
              and cut["original_cut"]["payload"] == first["cut_event"] and cut["original_cut"]["event"] == "genesis_cut"
              and cut["original_cut"]["sequence"] == 1 and cut["guest_time_inferred"] is False
              and cut["clock"] == "host time.monotonic_ns", "actual SIGKILL is detached from the original no-head cut line")
    observed = e.integer(cut["observed_at_ns"], "actual host cut reception", 1)
    before = e.integer(cut["kill_call_before_ns"], "actual host kill entry", observed)
    after = e.integer(cut["kill_call_after_ns"], "actual host kill return", before)
    return {"signal": signal.SIGKILL, "raw_exit_code": -signal.SIGKILL,
            "host_receive_to_kill_ns": after - observed, "host_kill_syscall_ns": after - before,
            "guest_original_cut_boottime_ns": first["cut_event"].get("observed_boottime_ns",
                first["observed_installation"]["observed_boottime_ns"]),
            "guest_original_wait_until_boottime_ns": first["cut_event"]["wait_until_boottime_ns"],
            "kill_within_guest_wait_window_proven": False,
            "clock_mapping": "unverified; actual host durations are never relabeled as guest BOOTTIME"}


def execute(args, report):
    # Same complete original-source/build admissions as the six-case runner.
    review = inputs.review_inputs(args.source_review, args.expected_source_review_sha256)
    roots = {"desktop": args.desktop_source, "hepta": args.hepta_source}
    builder = inputs.load_module("original_native_entry_builder", original.HERE / "build_original_entry.py")
    snapshots = inputs.source_snapshots(roots, review, builder)
    harness_head = builder.git(original.ROOT, "rev-parse", "HEAD").decode().strip()
    harness_tree = builder.git(original.ROOT, "rev-parse", "HEAD^{tree}").decode().strip()
    harness = builder.source_snapshot(original.ROOT, harness_head, harness_tree)
    shape, ordinary, replay = inputs.original_helpers(roots["desktop"])
    _, owner, elf_info, owner_files = inputs.owner_build(args.owner_build_receipt,
        args.expected_owner_build_receipt_sha256, args.owner_elf, review, snapshots, shape, roots["hepta"])
    _, kernel, base, kernel_files = inputs.kernel_build(args.kernel_pipeline,
        args.expected_kernel_pipeline_sha256, review, owner, ordinary)
    bios = inputs.read(args.bios, 2 * 1024**2, replay.SEABIOS_SHA)
    qemu, qemu_identity = original.tool(args.qemu, args.expected_qemu_sha256)
    mkfs, mkfs_identity = original.tool(args.mkfs)
    debugfs, debugfs_identity = original.tool(args.debugfs)
    output = args.output
    e.require(output.is_absolute() and output.parent.is_dir() and output.parent.resolve(strict=True) == output.parent
              and not output.exists() and not output.is_symlink() and "," not in str(output), "new canonical comma-free output required")
    for protected in (*roots.values(), original.ROOT, args.owner_build_receipt.parent, args.kernel_pipeline):
        e.require(not output.is_relative_to(protected) and not protected.is_relative_to(output),
                  "actual native evidence must not overlap original sources/build inputs")
    e.require(type(args.timeout) is int and 1 <= args.timeout <= 120, "original finite per-boot deadline required")
    e.require(shutil.disk_usage(output.parent).free >= 6 * original.STATE_BYTES + 256 * 1024**2,
              "insufficient space for one original state inode and independent stopped forensic copies")
    output.mkdir(mode=0o700)
    report["output_created"] = True
    original.freeze_bytes(output / "source-review.json",
                          inputs.read(args.source_review, 1024**2, args.expected_source_review_sha256))
    original.save(output / "source-before.json", snapshots)
    original.save(output / "harness-source-before.json", harness)
    original_schema_path = roots["hepta"] / "codex-rs/hepta-memory/src/cognitive_store.rs"
    original_schema_bytes = inputs.read(original_schema_path, 1024**2)
    schema = material.inventory(original_schema_bytes)
    original.freeze_bytes(output / "reviewed-cognitive-store.rs", original_schema_bytes)
    original.save(output / "original-schema-inventory.json", schema)
    report["original_material_schema"] = schema
    report.update(stage="inputs_frozen", sources={key: review[key] for key in roots}, original_entry=review["entry"],
                  harness_source={"head": harness_head, "tree": harness_tree}, original_elf_shape=elf_info,
                  source_review_sha256=args.expected_source_review_sha256,
                  owner_build_receipt_sha256=args.expected_owner_build_receipt_sha256,
                  kernel_pipeline_sha256=args.expected_kernel_pipeline_sha256,
                  input_attestation="caller-retained actual local original builds and complete checked sources; not remote attestation",
                  tool_identities={"qemu": qemu_identity, "mkfs": mkfs_identity, "debugfs": debugfs_identity})
    report["retained_owner_build"] = original.retain_files(output / "owner-build", owner_files)
    report["retained_kernel_build"] = original.retain_files(output / "kernel-build-evidence", kernel_files)
    report["artifacts"] = {
        "owner": original.freeze_bytes(output / "original-owner.elf", owner),
        "kernel": original.freeze_bytes(output / "product-kernel.elf", kernel),
        "base_initramfs": original.freeze_bytes(output / "base-initramfs.cpio.gz", base),
        "bios": original.freeze_bytes(output / "bios.bin", bios),
        "qemu_binary": original.freeze_bytes(output / "source-qemu-binary", qemu.read_bytes()),
        "debugfs_binary": original.freeze_bytes(output / "source-debugfs-binary", debugfs.read_bytes()),
    }
    report["controls"], report["boots"] = {}, {}
    original.save(output / "result.json", report)
    changed = bytearray(owner)
    changed[-1] ^= 1
    for name, actual in (("manifest-byte-mismatch", bytes(changed)), ("truncated-snapshot", owner[:-1])):
        directory = output / name
        directory.mkdir(mode=0o700)
        plan = {"schema_version": 1, "scenario": args.scenario, "nonce": os.urandom(32).hex()}
        original.save(directory / "run-plan.json", plan)
        original.freeze_bytes(directory / "initramfs.cpio.gz", original.build_initramfs(base, actual, plan, replay))
        report["stage"] = "original-loader-control:" + name
        original.save(output / "result.json", report)
        raw, record = original.run_qemu(original.qemu_argv(qemu, output, directory, False), directory, args.timeout, qemu_identity)
        result = original.rejection(raw, record, name)
        result.update(actual_initial_elf_sha256=hashlib.sha256(actual).hexdigest(),
                      actual_qemu_record_sha256=inputs.sha(directory / "qemu.json"),
                      raw_serial_sha256=inputs.sha(directory / "serial.log"))
        original.save(directory / "result.json", result)
        report["controls"][name] = result
        e.require(result["passed"] is True, "actual original immutable-loader negative control failed")
    campaign = output / "campaign"
    campaign.mkdir(mode=0o700)
    formatted = original.format_state(campaign, mkfs, mkfs_identity)
    nonce = os.urandom(32).hex()
    plan = {"schema_version": 1, "scenario": args.scenario, "nonce": nonce}
    original.save(campaign / "run-plan.json", plan)
    initramfs = original.build_initramfs(base, owner, plan, replay)
    report.update(nonce=nonce, format_state=formatted, native_execution_attempted=True)
    first_directory, second_directory = output / "boot-1", output / "boot-2"
    for directory in (first_directory, second_directory):
        directory.mkdir(mode=0o700)
        original.freeze_bytes(directory / "initramfs.cpio.gz", initramfs)
    with transport.SameStateDisk(campaign / "state.raw", formatted["before_sha256"]) as disk:
        report["original_state_inode"] = disk.initial
        report["stage"] = "actual-first-boot"
        original.save(output / "result.json", report)
        first_argv = transport.qemu_argv(qemu, output, first_directory, disk)
        raw, record = transport.run_until_actual_cut(first_argv, first_directory, args.timeout, qemu_identity,
                                                    disk, genesis_oracle.cut_line_reader(nonce, args.scenario))
        first = genesis_oracle.evaluate(raw, record, nonce, elf_info, "fresh", scenario=args.scenario)
        first["actual_kill"] = verify_actual_kill(raw, record, first)
        first_state = disk.observe()
        e.require(first_state["sha256"] != disk.initial["sha256"], "original initialization did not persist its actual input/material/state")
        first_copy = disk.retain_stopped_copy(first_directory / "stopped-state.raw", first_state["sha256"])
        first_physical = physical.verify(Path(first_copy["path"]), first_copy["sha256"], debugfs, debugfs_identity,
                                          first, schema, first_directory / "physical")
        first.update(actual_qemu_record_sha256=inputs.sha(first_directory / "qemu.json"),
                     original_stopped_state=first_state, forensic_stopped_copy=first_copy,
                     stopped_physical_evidence=first_physical)
        original.save(first_directory / "result.json", first)
        report["boots"]["fresh"] = first
        report["stage"] = "actual-retained-boot"
        original.save(output / "result.json", report)
        # Inspectors only read the retained copy. The original descriptor is
        # checked before it is inherited again; no copy/format is a boot input.
        e.require(disk.observe(first_state["sha256"]) == first_state,
                  "original stopped disk changed between actual VMs")
        second_argv = transport.qemu_argv(qemu, output, second_directory, disk)
        raw2, record2 = transport.run_until_actual_poweroff(second_argv, second_directory, args.timeout, qemu_identity, disk)
        second = genesis_oracle.evaluate(raw2, record2, nonce, elf_info, "retained", first, first_physical,
                                         scenario=args.scenario)
        second_state = disk.observe()
        e.require(second_state["sha256"] != first_state["sha256"], "actual cold first writer did not persist its effect/release")
        second_copy = disk.retain_stopped_copy(second_directory / "stopped-state.raw", second_state["sha256"])
        second_physical = physical.verify(Path(second_copy["path"]), second_copy["sha256"], debugfs, debugfs_identity,
                                           second, schema, second_directory / "physical", first_physical)
        e.require(record["state_descriptor"] == record2["state_descriptor"]
                  and record["pass_fds"] == record2["pass_fds"] == [disk.fd]
                  and first_state["host_device"] == second_state["host_device"]
                  and first_state["host_inode"] == second_state["host_inode"]
                  and first_state["ext2_uuid"] == second_state["ext2_uuid"],
                  "the actual two QEMU processes did not inherit the same original physical descriptor/inode")
        second.update(actual_qemu_record_sha256=inputs.sha(second_directory / "qemu.json"),
                      original_stopped_state=second_state, forensic_stopped_copy=second_copy,
                      stopped_physical_evidence=second_physical)
        original.save(second_directory / "result.json", second)
        report["boots"]["retained"] = second
        report["same_original_disk_descriptor_verified"] = True
    after = inputs.source_snapshots(roots, review, builder)
    final_harness = builder.source_snapshot(original.ROOT, harness_head, harness_tree)
    original.save(output / "source-after.json", after)
    original.save(output / "harness-source-after.json", final_harness)
    e.require(after == snapshots and final_harness == harness, "original source or oracle changed during the actual two-boot campaign")
    inputs.review_inputs(args.source_review, args.expected_source_review_sha256)
    inputs.owner_build(args.owner_build_receipt, args.expected_owner_build_receipt_sha256, args.owner_elf,
                       review, snapshots, shape, roots["hepta"])
    inputs.kernel_build(args.kernel_pipeline, args.expected_kernel_pipeline_sha256, review, owner, ordinary)
    for artifact in report["artifacts"].values():
        e.require(inputs.sha(Path(artifact["path"])) == artifact["sha256"], "actual retained input artifact changed")
    for selected, identity in ((qemu, qemu_identity), (mkfs, mkfs_identity), (debugfs, debugfs_identity)):
        e.require(inputs.sha(selected) == identity["sha256"], "actual execution/inspection tool changed")
    for copy in (first_copy, second_copy):
        e.require(inputs.sha(Path(copy["path"])) == copy["sha256"] and copy["execution_input"] is False,
                  "stopped forensic copy was changed or used as a second boot input")
    e.require(inputs.sha(campaign / "state-before.raw") == formatted["before_sha256"], "retained pristine ext2 preimage changed")
    e.require(first_physical["original_no_head_initial_material_physically_verified"] is True
              and second_physical["original_first_writer_released_physically_verified"] is True,
              "actual finite no-head recovery is missing either independent physical boundary")
    report.update(passed=True, stage="complete", source_inputs_unchanged=True, same_product_kernel_all_boots=True,
                  actual_first_vm_sigkill_verified=True, same_physical_disk_reboot_verified=True,
                  original_no_head_initial_material_physically_verified=True, actual_checkpoint_absence_verified=True,
                  original_initial_material_preserved=True, original_first_writer_factory_verified=True,
                  original_first_writer_released_physically_verified=True,
                  new_boot_original_effect_window_verified=True, graceful_owner_release_verified=True,
                  original_no_head_recovery_verified=True,
                  writer_reservation_recovery_verified=args.scenario == t.SCENARIOS[1],
                  proof_before_head_recovery_verified=args.scenario == t.SCENARIOS[2],
                  kill_within_guest_wait_window_proven=False,
                  cross_boot_unknown_preservation_verified=False, power_loss_verified=False,
                  unbounded_persistent_cpu_verified=False, original_native_owner_cycle_verified=True,
                  g2_complete=False, production_ready=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--scenario", choices=t.SCENARIOS)
    paths = ("desktop-source", "hepta-source", "source-review", "owner-elf", "owner-build-receipt", "kernel-pipeline", "output")
    hashes = ("expected-source-review-sha256", "expected-owner-build-receipt-sha256", "expected-kernel-pipeline-sha256", "expected-qemu-sha256")
    for name in paths:
        parser.add_argument("--" + name, type=Path)
    for name in hashes:
        parser.add_argument("--" + name)
    parser.add_argument("--qemu", default="qemu-system-x86_64")
    parser.add_argument("--mkfs", default="mkfs.ext2")
    parser.add_argument("--debugfs", default="debugfs")
    parser.add_argument("--bios", type=Path, default=Path("/usr/share/seabios/bios-256k.bin"))
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args(argv)
    report = {"schema": "hepta.native-genesis-recovery-result.v1", "scenario": args.scenario, "passed": False,
              "stage": "source_admission", "native_execution_attempted": False,
              "same_original_disk_descriptor_verified": False, "same_physical_disk_reboot_verified": False,
              "original_no_head_initial_material_physically_verified": False, "actual_checkpoint_absence_verified": False,
              "original_first_writer_factory_verified": False, "original_no_head_recovery_verified": False,
              "original_first_writer_released_physically_verified": False,
              "new_boot_original_effect_window_verified": False, "graceful_owner_release_verified": False,
              "writer_reservation_recovery_verified": False, "proof_before_head_recovery_verified": False,
              "cross_boot_unknown_preservation_verified": False, "kill_within_guest_wait_window_proven": False,
              "power_loss_verified": False, "unbounded_persistent_cpu_verified": False,
              "original_native_owner_cycle_verified": False, "hardware_qualification": False,
              "g2_complete": False, "production_ready": False, "started_at_utc": datetime.now(timezone.utc).isoformat()}
    if not args.execute:
        print(json.dumps({**report, "status": "disabled; explicit actual original builds and --execute required"}, sort_keys=True))
        return 0
    for name in (*paths, *hashes, "scenario"):
        if getattr(args, name.replace("-", "_")) is None:
            parser.error("--execute requires --" + name)
    try:
        e.require(all(getattr(args, name.replace("-", "_")).is_absolute() for name in (*paths, "bios")),
                  "absolute original inputs and new evidence output required")
        execute(args, report)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, AssertionError,
            sqlite3.Error, subprocess.SubprocessError) as error:
        report.update(passed=False, error=f"{type(error).__name__}: {error}")
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    if report.get("output_created"):
        original.save(args.output / "result.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
