#!/usr/bin/env python3
"""Preserve exact local Python guard inputs, commands and raw execution logs."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path("/workspace/scratch/98f315e377b2/recovery-r7/r9-main-sync-20261019")
OUT = Path(__file__).resolve().parent
TEST_DIR = ROOT / "tests/integration/hepta"
FOCUSED = [
    "test_original_process_guard.OriginalProcessGuardTests."
    "test_success_cleans_group_only_while_actual_exit_zero_leader_is_waitable",
    "test_original_process_guard.OriginalProcessGuardTests."
    "test_successful_leader_cannot_leave_a_same_group_plugin_writer",
]


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def git(*args):
    return subprocess.check_output(
        ["git", "-C", str(ROOT), *args],
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1"}, timeout=20,
    ).decode()


def source_identity():
    inputs = sorted(TEST_DIR.glob("test_original*.py")) + [TEST_DIR / name for name in [
        "test_objective_history_contracts.py", "run_original_agentd.py",
        "run_original_objective.py", "run_objective_history.py",
    ]]
    return {
        "head": git("rev-parse", "HEAD").strip(),
        "head_tree": git("rev-parse", "HEAD^{tree}").strip(),
        "status": git("status", "--porcelain=v1", "--untracked-files=all"),
        "input_files": {
            str(path.relative_to(ROOT)): {"bytes": path.stat().st_size, "sha256": sha(path.read_bytes())}
            for path in sorted(inputs)
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("attempt")
    parser.add_argument("--scope", choices=["focused", "guard", "related"], required=True)
    parser.add_argument("--expected-exit", type=int, required=True)
    parser.add_argument("--optimized", action="store_true")
    args = parser.parse_args()
    destination = OUT / args.attempt
    destination.mkdir()
    source = source_identity()
    write_json(destination / "source-before.json", source)
    for relative in source["input_files"]:
        target = destination / "source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    shutil.copyfile(__file__, destination / "run_checks.py")
    (destination / "changes.patch").write_text(git("diff", "HEAD", "--", *source["input_files"]))
    command = [sys.executable, "-B"] + (["-O"] if args.optimized else []) + ["-m", "unittest"]
    if args.scope == "focused":
        command += ["-v", *FOCUSED]
    elif args.scope == "guard":
        command += ["-v", "test_original_process_guard"]
    else:
        # The fixed-original manifest suite needs the full unchanged upstream
        # checkout; it is not restored locally and is not silently skipped.
        command += ["-v", "test_original_process_guard", "test_original_session_receipts",
                    "test_original_objective_receipts", "test_objective_history_contracts"]
    receipt = {
        "schema": "r9-anchored-success-cleanup-execution-v1",
        "status": "running", "scope": args.scope,
        "command": command, "cwd": str(TEST_DIR),
        "expected_exit": args.expected_exit, "started_at": utc(),
        "python": {"executable": sys.executable, "version": sys.version},
        "source_is_dirty_integration_worktree": True,
        "source_head_is_not_execution_commit": True,
        "runtime_scope": "real disposable Linux children and Python gate contracts only",
        "fixed_original_build_manifest_suite_executed": False,
        "original_hepta_started": False, "rust_build": False,
        "timeout_seconds": 90,
    }
    write_json(destination / "execution-plan.json", receipt)
    with (destination / "stdout.log").open("xb") as stdout, (destination / "stderr.log").open("xb") as stderr:
        result = subprocess.run(command, cwd=TEST_DIR, stdout=stdout, stderr=stderr, timeout=90, check=False)
    after = source_identity()
    write_json(destination / "source-after.json", after)
    receipt.update({
        "finished_at": utc(), "exit_code": result.returncode,
        "input_files_unchanged": source["input_files"] == after["input_files"],
        "head_unchanged": source["head"] == after["head"],
        "source_before_sha256": sha((destination / "source-before.json").read_bytes()),
        "source_after_sha256": sha((destination / "source-after.json").read_bytes()),
        "helper_sha256": sha(Path(__file__).read_bytes()),
        "logs": {name: {"bytes": (destination / name).stat().st_size,
                         "sha256": sha((destination / name).read_bytes())}
                 for name in ["stdout.log", "stderr.log"]},
    })
    receipt["status"] = "expected_result" if (
        result.returncode == args.expected_exit and receipt["input_files_unchanged"] and receipt["head_unchanged"]
    ) else "unexpected_result"
    write_json(destination / "receipt.json", receipt)
    print(json.dumps({"attempt": args.attempt, **receipt}, sort_keys=True), flush=True)
    return 0 if receipt["status"] == "expected_result" else 1


if __name__ == "__main__":
    raise SystemExit(main())
