#!/usr/bin/env python3
"""Write completed phase metadata without replacing historical evidence."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

scratch = Path(__file__).resolve().parent
project = scratch / "trillionnium-os-desktop"
root = project / "support/build/evidence/2026-10-16-ktest-lifecycle"
prefix = str(root.relative_to(project))
read = lambda path: json.loads(path.read_text())
lock_path = project / "support/upstream-lock.json"
lock = read(lock_path)
kernel = lock["kernel"]
boot = read(root / "kernel-public/artifact-bindings.json")
test_environment = read(root / "kernel-tests/environment.json")
test_result = read(root / "kernel-tests/result.json")
cancel = read(root / "real-ktest-cancel/result.json")
if not test_result["passed"] or not cancel["passed"] or cancel["boot_pass"]:
    raise SystemExit("completed result boundaries rejected")
old = copy.deepcopy(kernel["kernel_mode_regression"])
kernel.setdefault("kernel_mode_regression_history", []).append(old)
kernel["kernel_mode_regression"].update({
    "evidence": prefix + "/kernel-tests/result.json", "latest_phase": "2026-10-16-ktest-lifecycle",
    "code_commit": "efb02440ad6fff3b7a1a5d5019f660743d74ab32",
    "source_tree": "bfae38050e0b6473df7a46a6e02669166cf3055f",
    "osdk_code_commit": "efb02440ad6fff3b7a1a5d5019f660743d74ab32",
    "osdk_binary_sha256": test_environment["osdk_sha256"],
    "actual_tool_session": 96725, "actual_tool_exit": 0, "guests": 2,
    "raw_qemu_exits": [33, 33], "direct_command_leaders_reaped": 10,
    "target_cache_reused": True, "empty_target_rebuild": False,
})
old_boot = copy.deepcopy(kernel["latest_native_boot"])
kernel.setdefault("native_boot_history", []).append(old_boot)
kernel["latest_native_boot"] = {
    "code_commit": boot["source_commit"], "source_tree": boot["source_tree"],
    "actual_tool_session": 58936, "actual_tool_exit": 0, "source_build_invoked": True,
    "release_compilation_observed": b"Compiling " in (root / "kernel-public/run_kernel.log").read_bytes(),
    "target_cache_reused": True, "empty_target_rebuild": False, "passed": True,
    "qemu_raw_exit": 33, "supervisor_exit": 0, "worker_reaped": True,
    "boot_sha256": boot["artifacts"][0]["raw_sha256"], "boot_size": boot["artifacts"][0]["raw_size"],
    "initramfs_sha256": boot["artifacts"][1]["raw_sha256"],
    "serial_sha256": boot["serial_sha256"], "evidence": prefix + "/kernel-public/README.md",
    "profile": "x86_64-q35-tcg-max-1cpu-512MiB-SeaBIOS", "source_directory": "kernel/asterinas",
    "derived_tree": subprocess.check_output(["git", "rev-parse", "HEAD:kernel/asterinas"], cwd=project, text=True).strip(),
    "manifest_cleanup_outcome": "owned_removed", "manifest_cleanup_helper_sha256": boot["helper_sha256"],
    "later_foreign_manifest_observed": True, "foreign_manifest_writer_identified": False,
}
phase = {
    "evidence": prefix + "/report.json", "latest_main_merged": "ed7c9ef81388f89f1509e62f4d8d54322b23f496",
    "main_merge_commit": "84040737d2263368d254d4b16dabff7afb797ea4",
    "ktest_code_commit": "efb02440ad6fff3b7a1a5d5019f660743d74ab32",
    "manifest_code_commit": "a770f31a868d805524065c65a2bcfcbcf10ede2e",
    "host_ktest_per_python_mode": 15, "host_manifest_and_supervisor_per_python_mode": 31,
    "python_modes": ["-I", "-I -O"], "reported_kernel_passes": 362,
    "kernel_soft_skips": 3, "kernel_exercised_passed_lower_bound": 359,
    "actual_cancellation": {"tool_session": 50773, "controller_exit": 0, "cli_exit": 143,
        "actual_cargo_raw_exit": 13, "effective_cancellation_exit": 143,
        "native_qemu_paused_with_minus_S": True, "qemu_record_raw_exit": None,
        "guest_execution_or_boot_pass_claimed": False, "pidfds_exited": True,
        "stable_workspace_lock_released": True, "direct_command_leaders_reaped": 6},
    "no_tracked_kernel_source_changes_this_phase": True,
    "upstream_hardware_matrix_or_resource_control_accepted": False,
}
kernel["kernel_test_lifecycle_regression"] = phase
lock_path.write_text(json.dumps(lock, indent=2) + "\n")
report = {"schema": 1, "status": "completed", "generated_utc": datetime.now(timezone.utc).isoformat(),
          "upstream": {name: kernel[name] for name in ("tag", "commit", "tree", "toolchain", "source_directory")},
          "branch": "agents/A01-asterinas-boot", "pr": "https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/22",
          "phase": phase, "full_kernel_test_result": test_result,
          "latest_native_boot": kernel["latest_native_boot"],
          "actual_cancellation": phase["actual_cancellation"],
          "archive_directories": ["host-ktest", "host-manifest", "kernel-tests", "real-ktest-cancel", "kernel-public"],
          "remote_ci_snapshot": {"source_commit": "a770f31a868d805524065c65a2bcfcbcf10ede2e",
              "checks": [{"name": name, "status": "queued", "conclusion": None} for name in ("host-evidence", "Analyze (python)")],
              "final_evidence_commit_checks_not_yet_created": True},
          "limitations": ["unknown later manifest writer", "host AF_UNIX socket creation EPERM", "CI queued, main not merged",
              "A04 prior 24/28 result not rerun", "OSDK prior 22/22 not rerun", "no HOS2/quota/Hepta/SMP/persistence acceptance",
              "cache reuse is explicit; no bit reproducibility claim"],
          "root_readme_bytes": (project / "README.md").stat().st_size}
(root / "report.json").write_text(json.dumps(report, indent=2) + "\n")
shutil.copyfile(Path(__file__), root / "finalize-records.py")
print(json.dumps({"report": str(root / "report.json"), "lock_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
                  "boot_release_compilation_observed": kernel["latest_native_boot"]["release_compilation_observed"]}))
