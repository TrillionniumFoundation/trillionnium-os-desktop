#!/usr/bin/env python3
"""Observe tasks once through the unchanged, pinned current R5 Bili Flow.

Run as root with python3 -B -I and no arguments. The only Android calls are
Flow.admission() and Flow.stacks(); both use the original held transport.
Only a new private evidence step is written. No launch, UI, install, task
removal, reconciliation, permission change, or automatic retry is requested.
An observation does not settle the original unknown native launch.
"""
import sys
sys.dont_write_bytecode = True

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import types


RECORDER_ROOT = Path("/home/alex/work/pocket4-owned-bili-qa-r9-install-state-01/source/recorder-r5")
RECORDER_SHA = "7101d2ab2cd4b73bf96cab1117c8d0177c2b290255c6946af52ec834115a7f44"
MANIFEST_SHA = "6d99374e1580083fd0f30b7f9b3c520306680760c97ad0d5400798fda427fb6e"
FLOW = Path("/home/alex/work/pocket4-bilibili-owned-qa-r9-flow-474d7477074ea01fbc986e0d867924c1")
STEP = "eight-apps-r9-tasks-20261106-01"
PACKAGE = "tv.danmaku.bili"
UID = 10117
EPOCH = "734fab42fa57e7289a5a88c24d3d4e00e9326d74fefbe523d1c280e0e6d38bc2"
BASELINE = Path("/home/alex/work/pocket4-main-current-baseline-01/baseline.private.json")
BASELINE_SHA = "163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266"
QUALIFICATION_SHA = "f37b2eb00db80c398c9a4f9fd895628b6c7ecc827ccf9699c2242fa5ba862ed6"
PRIOR_PINS = {
    "scope.json": (1006, "ac6dea24873125a8ac322306786f9f5760fd20b0f1c8d06bc80a498e33eddc50"),
    "steps/launch-01/result.json": (5202, "037076b15c27611f83815ad243280a1ec8eae82416616c928c9106e17f7a12ca"),
    "steps/launch-01/command-004.stdout": (495, "2957db51935e4687990181acd1e9a395fb24326c4289725b67d2d48724024fc8"),
    "steps/launch-01/prelaunch-stacks.txt": (665, "4828128d5f155cfcbdd15b713ae6430eef36735163ca5ed53dd59a7409670e76"),
}
STAT_KEYS = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_uid", "st_gid",
             "st_size", "st_mtime_ns", "st_ctime_ns")


def require(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pinned(path, size, expected):
    """Read pinned bytes, rejecting a symlink at the final path component.

    Frozen recorder directory links, if present, are resolved and verified by
    its original SourceContract; this loader adds no alternative source path.
    """
    require(path.is_absolute() and ".." not in path.parts, "FIXED_ABSOLUTE_PATH_REQUIRED")
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
                before.st_uid == 0 and not before.st_mode & 0o022 and
                before.st_size == size and 0 < size <= 65536, "PINNED_FILE_METADATA_DIFFERS")
        chunks, count = [], 0
        while count <= size:
            part = os.read(fd, min(65536, size + 1 - count))
            if not part:
                break
            chunks.append(part)
            count += len(part)
        after = os.fstat(fd)
        raw = b"".join(chunks)
        require(count == size and all(getattr(before, k) == getattr(after, k)
                                     for k in STAT_KEYS), "PINNED_FILE_CHANGED_DURING_READ")
        require(sha(raw) == expected, "PINNED_FILE_SHA256_DIFFERS")
        return raw
    finally:
        os.close(fd)


def prior_unknown_launch():
    rows = {name: pinned(FLOW / name, size, digest)
            for name, (size, digest) in PRIOR_PINS.items()}
    scope = json.loads(rows["scope.json"])
    old = json.loads(rows["steps/launch-01/result.json"])
    native = json.loads(rows["steps/launch-01/command-004.stdout"])
    require(scope.get("package") == PACKAGE and scope.get("uid") == UID and
            scope.get("epoch_sha256") == EPOCH and
            scope.get("current_baseline_sha256") == BASELINE_SHA and
            scope.get("current_baseline_qualification_sha256") == QUALIFICATION_SHA,
            "ORIGINAL_SCOPE_DIFFERS")
    require(old.get("ok") is False and old.get("phase") == "launch" and
            old.get("action_attempted") is True and old.get("outcome_unknown") is True and
            old.get("final_Main_guard_passed") is True and
            old.get("held_binding_released") is True and old.get("action_lock_released") is True,
            "ORIGINAL_UNKNOWN_LAUNCH_RECEIPT_DIFFERS")
    require(native.get("ok") is False and
            "Android task 873 is already registered with different ownership" in native.get("message", ""),
            "ORIGINAL_NATIVE_OWNERSHIP_FAILURE_DIFFERS")
    require(not os.path.lexists(FLOW / "launch-scope.json") and
            not os.path.lexists(FLOW / "reconciliations/launch-01.json"),
            "ORIGINAL_LAUNCH_SCOPE_OR_RECONCILIATION_CHANGED")
    return {name: {"bytes": size, "sha256": digest}
            for name, (size, digest) in PRIOR_PINS.items()}


def load_recorder():
    manifest_raw = pinned(RECORDER_ROOT / "source-manifest.json", 3605, MANIFEST_SHA)
    manifest = json.loads(manifest_raw)
    require(manifest["files"]["recorder.py"] == {"bytes": 41689, "sha256": RECORDER_SHA},
            "RECORDER_MANIFEST_ENTRY_DIFFERS")
    raw = pinned(RECORDER_ROOT / "recorder.py", 41689, RECORDER_SHA)
    module = types.ModuleType("pocket4_r5_readonly_task_observer")
    module.__file__ = str(RECORDER_ROOT / "recorder.py")
    exec(compile(raw, module.__file__, "exec"), module.__dict__)
    return module


def arguments():
    return argparse.Namespace(
        operation="admission", adapter_manifest_sha256=MANIFEST_SHA,
        flow_dir=FLOW, step=STEP, current_baseline=BASELINE, baseline_sha256=BASELINE_SHA,
        package=PACKAGE, component=PACKAGE + "/tv.danmaku.bili.MainActivityV2",
        epoch_module=RECORDER_ROOT / "references/framework_epoch.py",
        task_source=RECORDER_ROOT / "references/task_scope_baseline.py",
        request={"collector": "pocket4-r9-readonly-task-observation-v1",
                 "calls": ["Flow.admission", "Flow.stacks"],
                 "original_unknown_step": "launch-01", "mutation": False},
        unknown_step=None, observation_step=None, postcondition=None)


def remember(result, phase, error):
    row = {"phase": phase, "type": type(error).__name__, "message": str(error)[:1024]}
    if "error" not in result:
        result.update(error_type=row["type"], error=row["message"], error_phase=phase)
        for key in ("command_observation", "details"):
            if hasattr(error, key):
                result["command_observation" if key == "command_observation" else "transport_failure"] = getattr(error, key)
    else:
        result["secondary_errors"].append(row)
    result["ok"] = False


def observe(recorder):
    result = {"schema": "pocket4-r9-readonly-task-observation-v1", "ok": False,
              "automatic_retry": False, "action_attempted": False, "outcome_unknown": False,
              "business_success_verified": False, "whole_app_production_ready": False,
              "source_manifest_sha256": MANIFEST_SHA, "recorder_sha256": RECORDER_SHA,
              "flow": str(FLOW), "step": STEP, "package": PACKAGE, "uid": UID,
              "epoch_sha256": EPOCH, "original_launch_outcome": "unknown_retained",
              "launch_reconciliation_completed": False, "cleanup_authority_established": False,
              "native_ownership_evidence_collected": False, "secondary_errors": []}
    flow = None
    try:
        result["original_launch_evidence"] = prior_unknown_launch()
        flow = recorder.Flow(arguments())
        require(flow.scope["epoch_sha256"] == EPOCH and flow.scope["package"] == PACKAGE and
                flow.scope["uid"] == UID, "CURRENT_FLOW_SCOPE_DIFFERS")
        flow.begin(arguments(), mutation=False)
        result.update(flow.admission())
        raw, roots, tasks = flow.stacks()
        data = raw.encode("utf-8", "strict")
        require(len(data) <= 1024 * 1024 and isinstance(roots, dict) and
                all(type(value) is int for value in tasks), "TASK_OBSERVATION_BOUND_OR_TYPE")
        recorder.write_new(flow.step / "task-stacks.txt", data)
        recorder.write_new(flow.step / "parsed-task-stacks.json",
                           {"roots": roots, "task_ids": sorted(tasks)})
        bili = [child for root in roots.values() for child in root["children"]
                if child["component"].split("/", 1)[0] == PACKAGE]
        result["task_observation"] = {
            "raw": {"path": str(flow.step / "task-stacks.txt"), "bytes": len(data), "sha256": sha(data)},
            "parsed_path": str(flow.step / "parsed-task-stacks.json"),
            "root_task_ids": sorted(roots), "task_ids": sorted(tasks),
            "task_873_in_task_ids": 873 in tasks, "task_873_in_root_ids": 873 in roots,
            "bilibili_tasks": bili, "bilibili_present_in_task_stacks": bool(bili),
            "ownership_inferred_from_task_presence": False}
        require(flow.action_attempted is False, "UNEXPECTED_MUTATION_FLAG")
        result["ok"] = True
    except BaseException as error:
        remember(result, "read_only_observation", error)
    finally:
        if flow is not None:
            try:
                flow.guard(attempted=flow.action_attempted)
                result["final_Main_guard_passed"] = True
            except BaseException as error:
                remember(result, "final_Main_guard", error)
        try:
            prior_unknown_launch()
            result["original_launch_evidence_unchanged"] = True
        except BaseException as error:
            remember(result, "original_launch_evidence", error)
        if flow is not None:
            try:
                flow.close()
                result["held_binding_released"] = True
            except BaseException as error:
                remember(result, "held_binding_release", error)
            result["action_attempted"] = bool(flow.action_attempted)
            result["outcome_unknown"] = bool(flow.action_attempted)
        result["ended_utc"] = recorder.now()
    if flow is not None and flow.step is not None:
        try:
            recorder.write_new(flow.step / "result.json", result)
        except BaseException as error:
            remember(result, "durable_result_write", error)
    return result


def main():
    require(len(sys.argv) == 1, "NO_ARGUMENTS_ACCEPTED")
    require(os.getuid() == os.geteuid() == 0, "ROOT_REQUIRED")
    os.umask(0o077)
    try:
        result = observe(load_recorder())
    except BaseException as error:
        result = {"ok": False, "error_type": type(error).__name__, "error": str(error)[:1024],
                  "action_attempted": False, "outcome_unknown": False, "automatic_retry": False,
                  "business_success_verified": False, "whole_app_production_ready": False}
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
