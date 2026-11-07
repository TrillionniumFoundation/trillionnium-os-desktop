#!/usr/bin/env python3
"""Freeze only this new local source/metadata candidate; never submit or claim."""
import sys
sys.dont_write_bytecode = True
import hashlib
import json
import os
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(path):
    raw = path.read_bytes()
    return {"path": str(path.relative_to(HERE)), "bytes": len(raw), "sha256": sha(raw)}


def save(name, value):
    raw = (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    path = HERE / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        view = memoryview(raw)
        while view:
            count = os.write(fd, view)
            assert count > 0
            view = view[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    assert path.read_bytes() == raw
    return pin(path)


def main():
    path = HERE / "permission_capture_gate.py"
    gate = types.ModuleType("frozen_candidate_final_local_check")
    gate.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), "exec"), gate.__dict__)
    g, plan, loaded = gate.load_closure()
    assert not gate.LEDGER.exists() and not (HERE / "readbacks").exists()
    checks = json.loads((HERE / "controls-attempt1.stdout.original.json").read_bytes())
    readback = json.loads((HERE / "readback-controls-attempt2.stdout.original.json").read_bytes())
    assert checks["ok"] is True and len(checks["cases"]) == 7 and all(row["pass"] is True for row in checks["cases"])
    assert readback["ok"] is True and len(readback["cases"]) == 3 and all(row["pass"] is True for row in readback["cases"])
    assert checks["whole_process_descriptors_before"] == checks["whole_process_descriptors_after"]
    assert readback["FDs_before"] == readback["FDs_after"]
    for name in ("controls-attempt1.stderr.original.txt", "readback-controls-attempt2.stderr.original.txt",
                 "closure-attempt1.stderr.original.txt", "assembly-attempt3.stderr.original.txt"):
        assert (HERE / name).read_bytes() == b""
    review = {"schema": "pocket4-fixed46-permission-candidate-source-review-v1",
        "actual_scope49": plan["app_scope"], "source_plan": pin(HERE / "CAPTURE_PLAN.json"),
        "serial_gate": pin(path), "request_index": pin(HERE / "REQUEST_INDEX.json"),
        "partitions": 14, "Launcher_targets": 46, "protected_packages": 49, "protected_APKs": 89,
        "Android_readonly_commands": 106, "original13_partitions_preserved": True, "new_batch14": "com.example.ndk_tests",
        "old45_STOP3_preserved": plan["preserved_old45_stop"], "default_stream_limit": 262144,
        "exception": "Only exact batch02 command02 microG PM stdout:2097152; all stderr/native/other streams remain262144",
        "worker_definitions_unchanged_from_frozen_templates": True,
        "all_transport_definitions_unchanged": True, "original_owned_lifetime_definitions_unchanged": 11,
        "changed_owned_definition": "worker_gate", "original_stage_functions_unchanged": True,
        "complete_actual_installer_scope_transition_validator_reused": True,
        "independent_actual_raw_scope_readback_required": True,
        "raw_capture_does_not_interpret_permission_grants": True, "semantic_interpretation_is_separate_after_readback": True,
        "subsequent_readback_pins_from_actual_completed_batch_only": True, "original_private_reader_functions_unchanged": 5,
        "original_decoder_helper_functions_unchanged": 7, "original_literal_parser_core_functions_unchanged": 8,
        "shared_UID_or_unprefixed_AppOps_scope_inferred": False, "permission_whitespace_normalized": False,
        "grant_changes": 0, "UI_actions": 0, "installs": 0, "remote_jobs_submitted": 0, "actual_claims_created": 0,
        "new_capture_results": 0, "new_private_bodies_read": 0, "new_semantic_permission_results": 0,
        "role_status": "UNKNOWN_NOT_QUERIED", "production_ready": False, "cleanup_actions": 0,
        "local_controls": [pin(HERE / "controls-attempt1.stdout.original.json"),
                           pin(HERE / "readback-controls-attempt2.stdout.original.json")],
        "assembly_failures_retained": [pin(HERE / "assembly-attempt1.stderr.original.txt"),
                                      pin(HERE / "assembly-attempt2.stderr.original.txt")],
        "privacy": "No APK, key, service raw body, private UI or business contents in this candidate; future raw readback stays outside repository."}
    review_pin = save("SOURCE_REVIEW.json", review)
    files = []
    for candidate in sorted(HERE.rglob("*")):
        if not candidate.is_file():
            continue
        assert not candidate.is_symlink() and "__pycache__" not in candidate.parts and candidate.suffix != ".pyc"
        if candidate.name in ("SOURCE_PINS.json", "freeze.stdout.original.json", "freeze.stderr.original.txt"):
            continue
        files.append(pin(candidate))
    manifest = {"schema": "pocket4-fixed46-permission-source-pins-v1", "files": files, "file_count": len(files),
        "total_bytes": sum(row["bytes"] for row in files), "source_review": review_pin,
        "actual_scope49": plan["app_scope"], "source_only": True, "remote_jobs_submitted": 0,
        "actual_claims_created": 0, "new_capture_results": 0, "private_service_bodies_included": False,
        "old_revisions_modified": False, "production_ready": False}
    result = save("SOURCE_PINS.json", manifest)
    for row in files:
        assert pin(HERE / row["path"]) == row
    print(json.dumps({"manifest": result, "file_count": len(files), "total_bytes": manifest["total_bytes"],
        "review": review_pin, "new_observations": 0, "Main_or_remote_actions": 0, "claims_created": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
