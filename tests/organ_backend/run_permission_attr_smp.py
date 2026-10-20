#!/usr/bin/env python3
"""Run fixed two-CPU permission races and two identified old-lock defects.

Run only after the original A06 full-suite and CPU negative gates. This runner
preserves their original green ELF, builds the separate default-off SMP test
feature, then proves genuine forbidden metadata outcomes under two frozen
production-only patches. All three executions use the source-built OSDK's
original checkout path and retain raw serial, ELF and before/after source proof.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
CONTROLS = {
    "ramfs-split-lock": (
        "permission_attr_ramfs_split_lock_negative.patch",
        "cbc08c3d97e97c6f02b2f663a55fc362302e1c884f2c1daa9a0deb4ae5f3e856",
        "kernel/asterinas/kernel/core/src/fs/fs_impls/ramfs/fs.rs",
    ),
    "memfd-release-seal": (
        "permission_attr_memfd_release_seal_negative.patch",
        "f9525f73657cd193bfa658e0f809781faa30f4a1ac0fd833dd550ff5caa8eac8",
        "kernel/asterinas/kernel/core/src/fs/fs_impls/ramfs/memfd.rs",
    ),
}
SAME_ENV = ("toolchain", "rustc", "cargo", "build_inputs_sha256", "osdk_sha256",
            "vdso_sha256", "test_name", "ktest_profile", "vcpus", "features")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root)


def gate_guest(directory):
    guests = sorted((directory / "aster-core/guests").glob("guest-*"))
    require(len(guests) == 1, "expected exactly one core guest")
    return guests[0]


def check_environment(directory, head):
    environment = json.loads((directory / "environment.json").read_text())
    require(environment["git_head"] == head and environment["git_status"] == "",
            "permission gate did not use the exact clean source")
    require(environment["toolchain"] == "nightly-2026-07-21"
            and environment["test_name"] == "permission_attr_smp"
            and environment["ktest_profile"] == "permission-attr-smp"
            and environment["vcpus"] == 2
            and environment["features"] == ["permission-attr-smp-ktest"],
            "permission gate build profile drifted")
    require((directory / "aster-core/generated.Cargo.lock").read_bytes() ==
            (ROOT / "support/build/ktest/locks/aster-core.Cargo.lock").read_bytes(),
            "permission gate generated Cargo lock differs")
    return environment


def run_gate(directory, receipt, head):
    env = os.environ.copy()
    env["VDSO_LIBRARY_DIR"] = str(ROOT / "support/build/out/linux-vdso")
    command = [sys.executable, "-I", "-B", str(ROOT / "support/build/ktest/run.py"),
               "--permission-attr-smp", "--skip-osdk-install", "--output", str(directory)]
    save(receipt / "command.json", {"argv": command, "cwd": str(ROOT), "execution_head": head,
                                   "vdso_library_dir": env["VDSO_LIBRARY_DIR"]})
    with (receipt / "gate-wrapper.log").open("wb") as log:
        completed = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    save(receipt / "gate-exit.json", {"exit_code": completed.returncode})
    return completed.returncode


def run(args, out, result):
    candidate = module("permission_candidate", ROOT / "tests/kernel/control/run_queryabi_candidate_guest.py")
    old_runner = module("permission_owner_control", ROOT / "tests/organ_backend/run_cpu_owner_negative.py")
    full_checker = module("permission_full_checker", ROOT / "support/build/ktest/check.py")
    checker = module("permission_smp_checker", ROOT / "support/build/ktest/check-permission-smp.py")
    head = git(ROOT, "rev-parse", "HEAD").decode().strip()
    tree = git(ROOT, "rev-parse", "HEAD^{tree}").decode().strip()
    before = candidate.source_snapshot(ROOT, head, tree)
    save(out / "candidate-source-before.json", before)
    result.update(candidate_head=head, candidate_tree=tree)

    full = args.full_evidence.resolve()
    full_env = json.loads((full / "environment.json").read_text())
    require(full_env["git_head"] == head and full_env["git_status"] == ""
            and full_env["test_name"] is None and full_env["ktest_profile"] == "default"
            and full_env["vcpus"] == 1 and full_env["features"] == [],
            "original full gate did not use the candidate and default one-CPU profile")
    require(json.loads((full / "result.json").read_text())["passed"] is True,
            "original full kernel gate did not pass")
    original = {}
    for crate in ("ostd", "aster-core"):
        guests = sorted((full / crate / "guests").glob("guest-*"))
        require(len(guests) == 1, "original full crate guest count differs")
        original[crate] = full_checker.check_guest(guests[0], crate)
        record = json.loads((guests[0] / "qemu.json").read_text())
        require(record["profile"]["vcpus"] == 1, "original full gate was changed to SMP")
    full_record = json.loads((gate_guest(full) / "qemu.json").read_text())
    original_elf = old_runner.checked_green_kernel(full_record, args.full_kernel)
    (out / "original-full-core-kernel.elf").write_bytes(original_elf)
    save(out / "original-full-validation.json", original)
    result["original_core_kernel_sha256"] = sha(original_elf)

    positive = out / "positive"
    positive.mkdir()
    require(run_gate(positive / "gate", positive, head) == 0, "positive permission SMP gate failed")
    positive_env = check_environment(positive / "gate", head)
    positive_guest = gate_guest(positive / "gate")
    positive_report = checker.check_guest(positive_guest)
    positive_record = json.loads((positive_guest / "qemu.json").read_text())
    positive_elf = old_runner.checked_green_kernel(positive_record)
    retained_positive = out / "positive-kernel.elf"
    retained_positive.write_bytes(positive_elf)
    save(positive / "validation.json", positive_report)
    result["positive"] = positive_report
    after_positive = candidate.source_snapshot(ROOT, head, tree)
    save(out / "candidate-source-after-positive.json", after_positive)
    require(before == after_positive, "source changed during the positive permission gate")

    worktrees = args.worktree_root.absolute()
    require(not worktrees.exists() and not worktrees.is_symlink(), "negative worktree root must be new")
    worktrees.mkdir(parents=True)
    result["controls"] = []
    for control, (patch_name, patch_sha, changed_path) in CONTROLS.items():
        # Keep failure-stage metadata even if compilation or QEMU fails later.
        negative = out / control
        negative.mkdir()
        control_result = {"control": control, "passed": False, "product_qualification": False,
                          "patch_sha256": patch_sha, "declared_changed_path": changed_path}
        result["controls"].append(control_result)
        save(out / "result.json", result)
        patch = ROOT / "tests/organ_backend" / patch_name
        require(sha(patch.read_bytes()) == patch_sha, "frozen production mutation differs: " + control)
        shutil.copyfile(patch, negative / "declared-negative-control.patch")
        # The first negative rebuild overwrites the shared OSDK target; every
        # later control verifies the separately archived positive ELF instead.
        checker.check_guest(positive_guest, kernel_path=retained_positive)
        worktree = worktrees / control
        git(ROOT, "worktree", "add", "--detach", str(worktree), head)
        git(worktree, "apply", "--index", str(patch))
        require(git(worktree, "diff", "--cached", "--name-only").decode().splitlines() == [changed_path],
                "negative patch changed an undeclared source or test")
        git(worktree, "-c", "user.name=A06 permission negative control",
            "-c", "user.email=a06-negative@example.invalid", "-c", "commit.gpgsign=false",
            "commit", "-m", "test: identified local permission " + control + " defect")
        negative_head = git(worktree, "rev-parse", "HEAD").decode().strip()
        negative_tree = git(worktree, "rev-parse", "HEAD^{tree}").decode().strip()
        control_result.update(negative_head=negative_head, negative_tree=negative_tree)
        archive = candidate.source_snapshot(worktree, negative_head, negative_tree)
        save(negative / "negative-archive-source.json", archive)
        require(archive["files"].keys() == before["files"].keys()
                and [name for name in before["files"] if archive["files"][name] != before["files"][name]] == [changed_path],
                "negative source differs beyond the frozen production mutation")
        (negative / "applied-negative-control.patch").write_bytes(git(worktree, "diff", head, negative_head))
        shutil.copyfile(worktree / changed_path, negative / "changed-production-source.rs")
        with old_runner.identified_checkout(ROOT, head, negative_head):
            running = candidate.source_snapshot(ROOT, negative_head, negative_tree)
            save(negative / "negative-source-before.json", running)
            require(running["files"] == archive["files"], "negative execution source differs from its archive")
            exit_code = run_gate(negative / "gate", negative, negative_head)
            after = candidate.source_snapshot(ROOT, negative_head, negative_tree)
            save(negative / "negative-source-after.json", after)
            require(running == after, "negative source changed during execution")
        restored = candidate.source_snapshot(ROOT, head, tree)
        save(negative / "candidate-source-restored.json", restored)
        require(before == restored, "candidate source was not exactly restored")
        require(exit_code != 0 and int((negative / "gate/aster-core/osdk-exit-code.txt").read_text()) != 0,
                "original gate accepted the frozen permission defect")
        negative_env = check_environment(negative / "gate", negative_head)
        for key in SAME_ENV:
            require(negative_env[key] == positive_env[key], "negative build input changed: " + key)
        guest = gate_guest(negative / "gate")
        report = checker.check_guest(guest, control)
        record = json.loads((guest / "qemu.json").read_text())
        require(report["declared"] == positive_report["declared"], "negative test denominator changed")
        for key in ("qemu_sha256", "qemu_version", "profile", "ktest_profile"):
            require(record[key] == positive_record[key], "negative QEMU input differs: " + key)
        require(record["artifacts"]["-bios"] == positive_record["artifacts"]["-bios"],
                "negative firmware differs")
        negative_elf = old_runner.checked_green_kernel(record)
        require(sha(negative_elf) != sha(positive_elf), "negative mutation did not change the loaded ELF")
        (negative / "negative-kernel.elf").write_bytes(negative_elf)
        save(negative / "validation.json", report)
        control_result.update(passed=True, negative_control_detected=True, observation=report,
                              same_osdk_binary_and_source_path=True, source_snapshots_unchanged=True)
        save(out / "result.json", result)
    save(out / "candidate-source-after.json", candidate.source_snapshot(ROOT, head, tree))
    result.update(passed=True, original_full_gate_preserved=True, original_tests_filtered=False,
                  permission_profile_vcpus=2, production_build_feature_default_off=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-evidence", type=Path, required=True)
    parser.add_argument("--full-kernel", type=Path, required=True,
                        help="original full core ELF saved before earlier CPU mutations rebuilt the target")
    parser.add_argument("--worktree-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    result = {"schema": "a06.permission-attr-smp.v1", "passed": False, "product_qualification": False}
    save(out / "result.json", result)
    try:
        run(args, out, result)
    except (KeyError, OSError, TypeError, ValueError, subprocess.SubprocessError) as error:
        result["error"] = str(error)
    save(out / "result.json", result)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
