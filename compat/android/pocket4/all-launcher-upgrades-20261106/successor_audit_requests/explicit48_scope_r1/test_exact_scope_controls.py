#!/usr/bin/env python3
"""Local pure-contract controls against actual discovery and the prior scope bytes."""
import copy
import hashlib
import json
import os
from pathlib import Path
import types

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent.parent


def load(path):
    module = types.ModuleType(path.stem)
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


def census():
    result = {}
    for name in os.listdir("/proc/self/fd"):
        try:
            value = os.fstat(int(name))
            result[name] = [os.readlink("/proc/self/fd/" + name), value.st_dev, value.st_ino,
                            value.st_mode, value.st_uid, value.st_gid, value.st_rdev]
        except FileNotFoundError:
            pass
        except OSError as error:
            if error.errno != 9:
                raise
    return result


def main():
    before = census()
    worker = load(ROOT / "observe_explicit_48.py")
    validator = load(PROJECT / "successor_audit_requests/native46_discovery_r1/owned_readonly_lifetime.py")
    artifact_raw = (ROOT / "inputs/discovery-artifact.original.json").read_bytes()
    outer_raw = (ROOT / "inputs/discovery-stdout.original.jsonl").read_bytes()
    terminal_raw = (ROOT / "inputs/discovery-terminal.original.json").read_bytes()
    actual, identity = worker.validate_inputs(artifact_raw, outer_raw, terminal_raw, validator)
    cases = [{"name": "actual_native46_full_joint_and_terminal_accepted", "status": "PASS"}]
    parent = json.loads((PROJECT / "successor_audit_requests/explicit47_scope_r2/actual-readback/app-scope.private.json").read_bytes())
    # This is only a local future-observation test value, never a remote scope or a PASS receipt.
    model = copy.deepcopy(parent)
    model["parent_app_scope"] = worker.PARENT
    model["apps"][worker.NEW_PACKAGE] = copy.deepcopy(identity)
    worker.validate_projection(model, parent, identity)
    cases.append({"name": "actual_47_plus_exact_discovered_identity_test_model_accepted", "status": "PASS",
                  "not_a_fresh_device_scope": True})

    def rejects(name, operation, expected):
        try:
            operation()
        except RuntimeError as error:
            if str(error) != expected:
                raise RuntimeError("UNEXPECTED_REJECTION:" + name + ":" + str(error))
            cases.append({"name": name, "status": "PASS", "rejection": str(error)})
        else:
            raise RuntimeError("REQUIRED_REJECTION_MISSING:" + name)

    bad = copy.deepcopy(model)
    del bad["apps"][worker.ORIGINAL_PACKAGES[0]]
    rejects("omitted_original_package_rejected", lambda: worker.validate_projection(bad, parent, identity),
            "ACTUAL_SCOPE_NOT_EXACT_48")
    bad = copy.deepcopy(model)
    bad["apps"]["com.example.unreviewed"] = copy.deepcopy(identity)
    rejects("additional_unreviewed_package_rejected", lambda: worker.validate_projection(bad, parent, identity),
            "ACTUAL_SCOPE_NOT_EXACT_48")
    bad = copy.deepcopy(model)
    bad["apps"][worker.NEW_PACKAGE]["uid"] += 1
    rejects("new_package_uid_change_rejected", lambda: worker.validate_projection(bad, parent, identity),
            "NDK_UID_APK_SIGNER_PM_DATA_OR_FILE_IDENTITY_CHANGED")
    bad = copy.deepcopy(model)
    bad["apps"][worker.NEW_PACKAGE]["apks"][0]["file"]["st_ino"] += 1
    rejects("new_package_apk_inode_change_rejected", lambda: worker.validate_projection(bad, parent, identity),
            "NDK_UID_APK_SIGNER_PM_DATA_OR_FILE_IDENTITY_CHANGED")
    bad = copy.deepcopy(model)
    bad["apps"][worker.ORIGINAL_PACKAGES[0]]["apks"][0]["file"]["st_mtime_ns"] += 1
    rejects("ordinary_original_apk_mtime_change_rejected", lambda: worker.validate_projection(bad, parent, identity),
            "ORIGINAL_47_APP_IDENTITY_CHANGED")
    bad = copy.deepcopy(model)
    bad["fresh_signature_verification_performed"] = True
    rejects("identity_scope_cannot_claim_fresh_signature", lambda: worker.validate_projection(bad, parent, identity),
            "IDENTITY_SCOPE_MUST_NOT_PROMOTE_SIGNATURE_OR_RUNTIME_AUTHORITY")
    bad_terminal = json.loads(terminal_raw)
    bad_terminal["timed_out"] = True
    rejects("timed_out_historical_discovery_rejected", lambda: worker.validate_inputs(
        artifact_raw, outer_raw, worker.canonical(bad_terminal), validator), "DISCOVERY_NOT_DURABLY_SETTLED")
    lines = [json.loads(line) for line in outer_raw.splitlines()]
    lines[1]["child_lifecycle"]["owned_child_sigkill_count"] = 1
    bad_outer = b"\n".join(worker.canonical(line) for line in lines) + b"\n"
    bad_terminal = json.loads(terminal_raw)
    bad_terminal["log_bytes"]["stdout"] = {"seen": len(bad_outer), "stored": len(bad_outer)}
    rejects("forced_historical_child_exit_rejected", lambda: worker.validate_inputs(
        artifact_raw, bad_outer, worker.canonical(bad_terminal), validator), "DISCOVERY_OWNED_CHILD_DID_NOT_RETIRE_NORMALLY")
    historical = json.loads((PROJECT / "successor_audit_requests/explicit47_scope_r2/actual/worker.stdout.original.jsonl").read_bytes())
    required = {"app_scope", "qa_build_input", "app_scope_guard", "observation_fds"}
    if not required <= historical["observation"].keys():
        raise RuntimeError("ACTUAL_READER_RETURN_INTERFACE_CHANGED")
    cases.append({"name": "actual_frozen_reader_return_interface_verified", "status": "PASS"})
    after = census()
    if before != after:
        raise RuntimeError("LOCAL_WHOLE_FD_IDENTITY_CHANGED")
    print(json.dumps({"schema": "pocket4-explicit48-local-controls-v1", "ok": True, "cases": cases,
                      "actual_discovery_sha256": hashlib.sha256(artifact_raw).hexdigest(),
                      "runtime_or_namespace_invoked": False, "root_identity_simulated": False,
                      "uid": os.getuid(), "euid": os.geteuid(), "scope_created": False,
                      "FDs_before": before, "FDs_after": after}, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
