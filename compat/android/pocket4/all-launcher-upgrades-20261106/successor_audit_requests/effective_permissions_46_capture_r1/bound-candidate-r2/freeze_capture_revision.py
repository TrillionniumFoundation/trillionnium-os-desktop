#!/usr/bin/env python3
"""Freeze the corrected capture-only source closure; no claim or device action."""
import sys
sys.dont_write_bytecode = True
import ast
import difflib
import hashlib
import json
import os
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "bound-candidate-r1"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, indent=2, allow_nan=False) + "\n").encode()


def pin(path):
    raw = path.read_bytes()
    return {"path": str(path.relative_to(HERE)), "bytes": len(raw), "sha256": sha(raw)}


def save(name, raw):
    raw = raw.encode() if isinstance(raw, str) else raw
    path = HERE / name
    with path.open("xb") as handle:
        handle.write(raw); handle.flush(); os.fsync(handle.fileno())
    assert path.read_bytes() == raw
    return pin(path)


def functions(raw):
    text = raw.decode()
    return {n.name: ast.get_source_segment(text, n) for n in ast.parse(text).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}


def main():
    old_manifest_raw = (PREVIOUS / "SOURCE_PINS.json").read_bytes()
    assert len(old_manifest_raw) == 28173 and sha(old_manifest_raw) == "97a7bb07ac2ddbf75144643d9154c3b8b3a3e8897615069a75013fd2c494d3a9"
    for row in json.loads(old_manifest_raw)["files"]:
        raw = (PREVIOUS / row["path"]).read_bytes()
        assert len(raw) == row["bytes"] and sha(raw) == row["sha256"]
    gate = types.ModuleType("new_capture_r2_final_local_gate")
    gate.__file__ = str(HERE / "permission_capture_gate.py")
    exec(compile(Path(gate.__file__).read_bytes(), gate.__file__, "exec"), gate.__dict__)
    g, plan, loaded = gate.load_closure()
    assert not gate.LEDGER.exists()
    rows = []
    for number, item in loaded.items():
        folder = "batch-%02d" % number
        worker = (HERE / folder / "observe_current_services.py").read_bytes()
        transport = (HERE / folder / "readonly_services_transport.py").read_bytes()
        old_transport = (PREVIOUS / folder / "readonly_services_transport.py").read_bytes()
        assert functions(worker) == functions((PREVIOUS / folder / "observe_current_services.py").read_bytes())
        assert functions(transport) == functions(old_transport)
        before, after = gate.constants(old_transport), gate.constants(transport)
        changed = sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))
        assert changed == ["EXPLICIT_SCOPE_SHA256"] and after["EXPLICIT_SCOPE_SHA256"] == plan["app_scope"]["sha256"]
        rows.append({"batch": number, "changed_transport_constants": changed,
            "all_original_transport_definitions_unchanged": True, "all_worker_definitions_unchanged": True,
            "actual49_scope": after["EXPLICIT_SCOPE_SHA256"], "framework_epoch": after["FRAMEWORK_EPOCH_SHA256"],
            "held_helper_sha256": after["HELD_HELPER_SHA256"]})
    control_names = ("controls-attempt1", "constructor-controls-attempt1")
    controls = []
    for name in control_names:
        raw = (HERE / (name + ".stdout.original.json")).read_bytes()
        result = json.loads(raw)
        assert result["ok"] is True and (HERE / (name + ".stderr.original.txt")).read_bytes() == b""
        controls.append(pin(HERE / (name + ".stdout.original.json")))
    assert json.loads((HERE / "closure-attempt1.stdout.original.json").read_bytes())["state"] == "SOURCE_CLOSURE_AND_ACTUAL49_INSTALL_READBACK_VERIFIED"
    assert (HERE / "closure-attempt1.stderr.original.txt").read_bytes() == b""
    proof = {"schema": "pocket4-fixed46-capture-r2-transport-binding-correction-v1",
        "previous_source_manifest": {"bytes": len(old_manifest_raw), "sha256": sha(old_manifest_raw)},
        "previous_revision_unsubmitted_and_preserved": True, "previous_constructor_rejection_reproduced": True,
        "actual49_scope": plan["app_scope"], "rows": rows,
        "constructor_controls_use_metadata_only_fixture": True, "no_live_process_or_namespace_opened_by_controls": True,
        "all14_actual49_parameters_accepted_by_original_constructor": True,
        "all14_old47_scope_parameters_rejected": True, "wrong_epoch_and_helper_rejected": True,
        "local_controls": controls, "new_runtime_results": 0, "claims_created": 0, "remote_jobs": 0,
        "production_ready": False, "old45_STOP3_modified": False}
    save("REVISION_PROOF.json", canonical(proof))
    diff = ""
    for name in ("assemble_bound.py", "gate_closure.py.inc", "permission_capture_gate.py", "batch-01/readonly_services_transport.py"):
        diff += "".join(difflib.unified_diff((PREVIOUS / name).read_text().splitlines(True),
            (HERE / name).read_text().splitlines(True), fromfile="preserved-unsubmitted-r1/" + name, tofile="corrected-r2/" + name))
    save("SOURCE_DIFF.patch", diff)
    files = []
    for path in sorted(HERE.rglob("*")):
        if not path.is_file():
            continue
        assert not path.is_symlink() and "__pycache__" not in path.parts and path.suffix != ".pyc"
        if path.name in ("SOURCE_PINS.json", "freeze.stdout.original.json", "freeze.stderr.original.txt"):
            continue
        files.append(pin(path))
    manifest = {"schema": "pocket4-fixed46-capture-r2-source-pins-v1", "files": files, "file_count": len(files),
        "total_bytes": sum(r["bytes"] for r in files), "scope": plan["app_scope"],
        "previous_r1_preserved": True, "source_only": True, "claims_created": 0, "remote_jobs_submitted": 0,
        "new_permission_observations": 0, "private_service_body_included": False, "production_ready": False}
    mp = save("SOURCE_PINS.json", canonical(manifest))
    for row in files:
        assert pin(HERE / row["path"]) == row
    print(json.dumps({"manifest": mp, "file_count": len(files), "total_bytes": manifest["total_bytes"],
        "plan": pin(HERE / "CAPTURE_PLAN.json"), "gate": pin(HERE / "permission_capture_gate.py"),
        "request_index": pin(HERE / "REQUEST_INDEX.json"), "claims_created": 0, "remote_jobs": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
