#!/usr/bin/env python3
"""Check and curate existing results; this script does not execute the tests."""

import ast
from collections import Counter
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


HERE = Path(__file__).resolve().parent
REPO = Path("/workspace/scratch/98f315e377b2/recovery-r7/r9-main-sync-20261019")
BASE = "5060ac6976b56b32647c728991e489cdee1cce9d"
GUARD = "tests/integration/hepta/run_original_agentd.py"
TEST = "tests/integration/hepta/test_original_process_guard.py"
ATTEMPTS = ["red-01", "red-02", "green-01", "related-01"]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def load(path):
    return json.loads(path.read_text())


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def proof(attempt):
    text = (HERE / attempt / "stdout.log").read_text()
    prefix = "owned successful-leader writer proof: "
    lines = [line for line in text.splitlines() if line.startswith(prefix)]
    need(len(lines) == 1, "exactly one writer proof required")
    return json.loads(lines[0].removeprefix(prefix))


def main():
    stage = HERE / "archive-stage"
    stage.mkdir()
    executions = {}
    for name in ATTEMPTS:
        directory = HERE / name
        receipt = load(directory / "receipt.json")
        before = load(directory / "source-before.json")
        after = load(directory / "source-after.json")
        need(before["input_files"] == after["input_files"], "execution input changed")
        need(receipt["input_files_unchanged"] and receipt["head_unchanged"], "execution source guard failed")
        for path, metadata in before["input_files"].items():
            data = (directory / "source" / path).read_bytes()
            need(metadata == {"bytes": len(data), "sha256": sha(data)}, "source snapshot mismatch")
        for path, metadata in receipt["logs"].items():
            data = (directory / path).read_bytes()
            need(metadata == {"bytes": len(data), "sha256": sha(data)}, "raw log mismatch")
        for moment in ["before", "after"]:
            need(sha((directory / f"source-{moment}.json").read_bytes()) == receipt[f"source_{moment}_sha256"],
                 "source catalog hash mismatch")
        need(sha((directory / "run_checks.py").read_bytes()) == receipt["helper_sha256"], "helper snapshot mismatch")
        shutil.copytree(directory, stage / name)
        executions[name] = {"receipt_sha256": sha((directory / "receipt.json").read_bytes()),
                            "started_at": receipt["started_at"], "finished_at": receipt["finished_at"],
                            "actual_exit_code": receipt["exit_code"], "scope": receipt["scope"]}

    red = proof("red-02")
    green = proof("green-01")
    related = proof("related-01")
    for item in [red, green, related]:
        need(all(item[key] for key in ["command_returned_success", "fixture_children_all_reaped",
                                      "leader_reaped", "leader_waitable_at_reap_boundary",
                                      "writer_group_matches_leader", "writer_reaped"]), "owned cleanup proof incomplete")
        need(item["leader_exit_code"] == 0, "leader business status changed")
    need(red["signals"] == [] and red["writer_wrote_after_leader_exit"]
         and not red["writer_exited_before_leader_reap"]
         and red["writer_wait_status"] == {"code": 2, "status": 9}, "RED is not the intended live writer defect")
    for item in [green, related]:
        need(item["signals"] == [15, 9] and not item["writer_wrote_after_leader_exit"]
             and item["writer_exited_before_leader_reap"]
             and item["writer_wait_status"] == {"code": 2, "status": 15}, "GREEN writer did not exit before leader reap")
    blocked = (HERE / "red-01/stderr.log").read_text()
    need("PermissionError: [Errno 1] Operation not permitted" in blocked
         and "listener.bind" in blocked, "first attempt not the recorded sandbox failure")
    executions["red-01"]["classification"] = "one intended failure plus fixture blocked by sandbox AF_UNIX bind EPERM; not a complete RED"
    for name, ending in [("red-02", "FAILED (failures=2)"), ("green-01", "OK")]:
        log = (HERE / name / "stderr.log").read_text()
        need(re.search(r"Ran 2 tests in [0-9.]+s", log) is not None and log.rstrip().endswith(ending),
             "focused actual result count mismatch")
    executions["red-02"]["classification"] = "two intended assertion failures, real live writer and write proven"
    executions["green-01"]["classification"] = "two focused tests passed"
    log = (HERE / "related-01/stderr.log").read_text()
    counts = dict(Counter(re.findall(r"^test_[^\n]+ \((test_[^.]+)\.[^\n]+\) \.\.\. ok$", log, re.MULTILINE)))
    expected = {"test_original_process_guard": 7, "test_original_session_receipts": 6,
                "test_original_objective_receipts": 12, "test_objective_history_contracts": 22}
    need(counts == expected and re.search(r"Ran 47 tests in [0-9.]+s", log) is not None
         and log.rstrip().endswith("OK") and "skipped" not in log, "related suite counts mismatch")
    executions["related-01"].update({"classification": "47 related tests passed; no skips", "counts": counts})

    red_guard = (HERE / "red-02/source" / GUARD).read_bytes()
    green_guard = (HERE / "green-01/source" / GUARD).read_bytes()
    original = subprocess.check_output(["git", "-C", str(REPO), "show", f"{BASE}:{GUARD}"], timeout=20)
    need(red_guard == original, "RED guard was not the failed CI source")
    test = (HERE / "red-02/source" / TEST).read_bytes()
    need(all((HERE / name / "source" / TEST).read_bytes() == test for name in ATTEMPTS), "RED/GREEN tests differ")
    need((HERE / "related-01/source" / GUARD).read_bytes() == green_guard, "related suite changed GREEN guard")
    need((REPO / GUARD).read_bytes() == green_guard and (REPO / TEST).read_bytes() == test, "current guard/test no longer match GREEN")

    def definitions(data):
        return {node.name: ast.dump(node, include_attributes=False) for node in ast.parse(data).body
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))}
    old_nodes, new_nodes = definitions(red_guard), definitions(green_guard)
    changed = sorted(key for key in old_nodes.keys() | new_nodes.keys() if old_nodes.get(key) != new_nodes.get(key))
    need(changed == ["bounded_command"], "production change exceeds bounded_command")
    (stage / "red-to-green-production.patch").write_text("".join(difflib.unified_diff(
        red_guard.decode().splitlines(keepends=True), green_guard.decode().splitlines(keepends=True),
        fromfile="red/" + GUARD, tofile="green/" + GUARD)))
    report = {
        "schema": "r9-anchored-success-cleanup-review-v1",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "status": "local_python_fix_verified_new_exact_head_ci_still_required",
        "failed_ci_head": BASE,
        "failed_ci_run": 39182491155,
        "failed_ci_overall_conclusion": "failure",
        "ci_failure": {
            "outer_error": "[Errno 39] Directory not empty: 'plugins'",
            "readonly_original_eight_and_session_eight_plus_five_elf_package": "passed on old head only",
            "objective_raw_runtime_acceptance_does_not_override_outer_failure": True,
            "actual_ci_writer_identity_captured": False,
            "link_to_success_path_defect": "source inference supported by a separate deterministic real-process reproduction",
        },
        "production_change": "Every observed leader completion uses the existing anchored TERM/grace/KILL then sole-reap path; actual leader business exit status is retained.",
        "unchanged_production_definitions": ["ChildGroup", "terminate_group", "child_anchor_available"],
        "changed_production_definitions": changed,
        "source_binding": {
            "execution_base_head": load(HERE / "related-01/source-before.json")["head"],
            "dirty_integration_worktree_patch_is_the_executed_source": True,
            "red_guard_sha256": sha(red_guard), "green_guard_sha256": sha(green_guard),
            "identical_test_sha256": sha(test),
            "red_guard_bytes_equal_exact_failed_ci_git_blob": True,
            "production_test_pre_post_bytes_verified": True,
        },
        "executions": executions,
        "real_process_proofs": {"red-02": red, "green-01": green, "related-01": related},
        "fixture": {
            "isolated_subreaper_process": True,
            "unittest_parent_subreaper_state_changed": False,
            "readiness": "bounded AF_UNIX handshake with actual SO_PEERCRED and same-PGID checks, never sleep timing",
            "signals": "WNOWAIT anchor checked before every real owned process-group signal",
            "writer_exit": "pidfd observation before leader reap; actual adopted child wait status and final reap",
            "postcondition": "all fixture children reaped, then actual P_ALL ECHILD",
            "numeric_pid_reuse_attempted": False,
        },
        "qualification_limits": [
            "No new original Hepta daemon, Rust build, ARM run, target OS or device execution occurred here.",
            "The five fixed-original build-manifest tests were not executed locally because their full unchanged original checkout is absent; they were not silently skipped.",
            "Receipt and history contract tests use synthetic records or disposable Git fixtures and do not qualify original-owner runtime.",
            "The new production path reuses the existing bounded owned-group cleanup contract. It is not a new proof for arbitrary daemonized descendants that escape the group.",
            "New exact integrated HEAD CI is required before replacing the failed old-head qualification.",
            "Execution receipts classify expected process exit codes; this report separately identifies the red-01 sandbox fixture failure.",
        ],
    }
    write_json(stage / "review.json", report)
    shutil.copyfile(__file__, stage / "finalize_evidence.py")
    shutil.copyfile(HERE / "README.md", stage / "README.md")
    files = sorted(path for path in stage.rglob("*") if path.is_file())
    manifest = "".join(f"{sha(path.read_bytes())}  {path.relative_to(stage)}\n" for path in files)
    (stage / "SHA256SUMS").write_text(manifest)
    for line in manifest.splitlines():
        digest, relative = line.split("  ", 1)
        need(sha((stage / relative).read_bytes()) == digest, "archive final hash mismatch")
    print(json.dumps({"stage": str(stage), "files_including_manifest": len(files) + 1,
                      "bytes": sum(path.stat().st_size for path in stage.rglob("*") if path.is_file()),
                      "sha256sums_sha256": sha((stage / "SHA256SUMS").read_bytes()),
                      "review_sha256": sha((stage / "review.json").read_bytes())}, sort_keys=True))


if __name__ == "__main__":
    main()
