#!/usr/bin/env python3
"""Run the two original partial-activation recovery cases independently.

Only actual source-bound original owner/product-kernel builds may execute.
This entry does not extend the six-case or two-boot runner's accepted plans.
No failure, authority, Current, Process or successful result is supplied by
the host. Each case requires its actual original failure and physical files.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

import native_owner_activation_evidence as activation
import native_owner_evidence as e
import native_owner_inputs as inputs
import native_owner_state_observations as observations
import native_owner_activation_witness_disk as witness_files
import run_native_owner as original


def accept_actual_observations(transcript, physical, activation_files=None):
    e.require(transcript.get("scenario") in activation.SCENARIOS
              and transcript.get("partial_activation_transcript_verified") is True
              and transcript.get("partial_activation_recovery_verified") is False,
              "only a complete original failed-activation transcript can enter physical verification")
    e.require(activation_files is not None, "both exact original activation preparations require actual saved-file verification")
    witness_files.accept_expected(transcript, activation_files)
    observations.accept_retained_observations(transcript, physical)
    transcript["partial_activation_recovery_verified"] = True


def execute(args, report):
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
    selected = args.scenario or list(activation.SCENARIOS)
    e.require(len(selected) == len(set(selected)) and selected
              and all(name in activation.SCENARIOS for name in selected), "unique fixed failure cases required")
    output = args.output
    e.require(output.is_absolute() and output.parent.is_dir() and output.parent.resolve(strict=True) == output.parent
              and not output.exists() and not output.is_symlink() and "," not in str(output), "new canonical comma-free output required")
    for protected in (*roots.values(), original.ROOT, args.owner_build_receipt.parent, args.kernel_pipeline):
        e.require(not output.is_relative_to(protected) and not protected.is_relative_to(output),
                  "actual native evidence must not overlap original sources or build inputs")
    e.require(type(args.timeout) is int and 1 <= args.timeout <= 120, "unchanged finite 1..120 second case deadline required")
    output.mkdir(mode=0o700)
    report["output_created"] = True
    original.freeze_bytes(output / "source-review.json",
                          inputs.read(args.source_review, 1024**2, args.expected_source_review_sha256))
    original.save(output / "source-before.json", snapshots)
    original.save(output / "harness-source-before.json", harness)
    report.update(stage="inputs_frozen", selected_scenarios=selected,
                  sources={key: review[key] for key in roots}, original_entry=review["entry"],
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
    report["controls"], report["scenarios"] = {}, {}
    original.save(output / "result.json", report)
    changed = bytearray(owner)
    changed[-1] ^= 1
    controls = [("manifest-byte-mismatch", bytes(changed)), ("truncated-snapshot", owner[:-1])]
    for name, actual_owner in controls + [(name, owner) for name in selected]:
        is_control = name not in activation.SCENARIOS
        directory = output / name
        directory.mkdir(mode=0o700)
        nonce = os.urandom(32).hex()
        plan = {"schema_version": 1, "scenario": selected[0] if is_control else name, "nonce": nonce}
        original.save(directory / "run-plan.json", plan)
        original.freeze_bytes(directory / "initramfs.cpio.gz", original.build_initramfs(base, actual_owner, plan, replay))
        result = {"passed": False, "scenario": name, "nonce": nonce,
                  "actual_initial_elf_sha256": hashlib.sha256(actual_owner).hexdigest(), "g2_complete": False}
        if not is_control:
            result["state"] = original.format_state(directory, mkfs, mkfs_identity)
            report["native_execution_attempted"] = True
        report["stage"] = "actual-original-case:" + name
        original.save(directory / "result.json", result)
        original.save(output / "result.json", report)
        raw, record = original.run_qemu(original.qemu_argv(qemu, output, directory, not is_control),
                                         directory, args.timeout, qemu_identity)
        try:
            if is_control:
                result.update(original.rejection(raw, record, name))
            else:
                state = directory / "state.raw"
                result["state"].update(after_sha256=inputs.sha(state), after_bytes=state.stat().st_size)
                e.require(inputs.sha(directory / "state-before.raw") == result["state"]["before_sha256"]
                          and result["state"]["after_bytes"] == original.STATE_BYTES
                          and result["state"]["after_sha256"] != result["state"]["before_sha256"],
                          "actual original state did not persist or its retained preimage changed")
                observed = activation.evaluate(raw, record["raw_exit_code"], record["timed_out"],
                                                record["serial_excessive"], name, nonce, elf_info)
                physical = observations.verify(state, debugfs, debugfs_identity, result["state"]["after_sha256"],
                    observed["root_launch_observations_expected"], directory / "root-launch-observations")
                result["retained_root_observations"] = physical
                activation_files = witness_files.verify(state, debugfs, debugfs_identity, result["state"]["after_sha256"],
                    observed["activation_witnesses_expected"], directory / "checkpoint-activation-witnesses")
                result["retained_activation_witnesses"] = activation_files
                accept_actual_observations(observed, physical, activation_files)
                result.update(observed)
        except (OSError, ValueError, TypeError, KeyError, UnicodeError, subprocess.SubprocessError) as error:
            result.update(passed=False, error=f"{type(error).__name__}: {error}")
        result["actual_qemu_record_sha256"] = inputs.sha(directory / "qemu.json")
        result["raw_serial_sha256"] = inputs.sha(directory / "serial.log")
        original.save(directory / "result.json", result)
        report["controls" if is_control else "scenarios"][name] = result
        original.save(output / "result.json", report)
        for tool, identity in ((qemu, qemu_identity), (mkfs, mkfs_identity), (debugfs, debugfs_identity)):
            e.require(inputs.sha(tool) == identity["sha256"], "actual execution or extraction tool changed")
        if is_control:
            e.require(result["passed"] is True, "actual original immutable-loader negative control failed")
    after = inputs.source_snapshots(roots, review, builder)
    final_harness = builder.source_snapshot(original.ROOT, harness_head, harness_tree)
    original.save(output / "source-after.json", after)
    original.save(output / "harness-source-after.json", final_harness)
    e.require(after == snapshots and final_harness == harness, "original source or oracle changed during actual execution")
    inputs.review_inputs(args.source_review, args.expected_source_review_sha256)
    inputs.owner_build(args.owner_build_receipt, args.expected_owner_build_receipt_sha256, args.owner_elf,
                       review, snapshots, shape, roots["hepta"])
    inputs.kernel_build(args.kernel_pipeline, args.expected_kernel_pipeline_sha256, review, owner, ordinary)
    for artifact in report["artifacts"].values():
        e.require(inputs.sha(Path(artifact["path"])) == artifact["sha256"], "retained actual input artifact changed")
    for name, result in report["scenarios"].items():
        e.require(inputs.sha(output / name / "state-before.raw") == result["state"]["before_sha256"]
                  and inputs.sha(output / name / "state.raw") == result["state"]["after_sha256"],
                  "actual stopped original state or pristine preimage changed after inspection")
    passed = (len(report["controls"]) == 2 and len(report["scenarios"]) == len(selected)
              and all(value["passed"] is True for group in (report["controls"], report["scenarios"]) for value in group.values()))
    report.update(passed=passed, stage="complete", source_inputs_unchanged=True, same_product_kernel_all_boots=True,
                  original_native_owner_cycle_verified=passed,
                  same_boot_authenticated_successor_verified=passed,
                  selected_partial_activations_verified=passed,
                  activation_witness_files_verified=passed,
                  both_partial_activations_verified=passed and set(selected) == set(activation.SCENARIOS),
                  activation_after_proof_verified=passed and activation.SCENARIOS[0] in selected,
                  activation_after_material_verified=passed and activation.SCENARIOS[1] in selected)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
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
    parser.add_argument("--scenario", choices=activation.SCENARIOS, action="append")
    args = parser.parse_args(argv)
    report = {"schema": "hepta.native-partial-activation-result.v1", "passed": False, "stage": "source_admission",
              "native_execution_attempted": False, "original_native_owner_cycle_verified": False,
              "same_boot_authenticated_successor_verified": False, "selected_partial_activations_verified": False,
              "both_partial_activations_verified": False, "activation_after_proof_verified": False,
              "activation_witness_files_verified": False,
              "activation_after_material_verified": False, "cross_boot_unknown_preservation_verified": False,
              "grant_renewal_verified": False, "repeated_recovery_verified": False,
              "unbounded_persistent_cpu_verified": False, "power_loss_verified": False, "hardware_qualification": False,
              "g2_complete": False, "production_ready": False, "started_at_utc": datetime.now(timezone.utc).isoformat()}
    if not args.execute:
        print(json.dumps({**report, "status": "disabled; explicit actual original builds and --execute required"}, sort_keys=True))
        return 0
    for name in (*paths, *hashes):
        if getattr(args, name.replace("-", "_")) is None:
            parser.error("--execute requires --" + name)
    try:
        e.require(all(getattr(args, name.replace("-", "_")).is_absolute() for name in (*paths, "bios")),
                  "absolute original inputs and new evidence output required")
        execute(args, report)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, AssertionError, subprocess.SubprocessError) as error:
        report.update(passed=False, error=f"{type(error).__name__}: {error}")
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    if report.get("output_created"):
        original.save(args.output / "result.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
