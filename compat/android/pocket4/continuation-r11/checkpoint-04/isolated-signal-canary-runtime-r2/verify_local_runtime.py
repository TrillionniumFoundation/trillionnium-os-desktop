#!/usr/bin/env python3
"""Pure/runtime-loader controls. No actual preparation, test binary or service."""
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types

sys.dont_write_bytecode = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-input-reference", type=Path, required=True)
    parser.add_argument("--preparation-source", type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("owned_runtime_under_control", Path(__file__).with_name("run.py"))
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    template = json.loads((args.preparation_source / "inputs-template.json").read_text())
    template["engine"] = {"path": "/declared-synthetic-engine-not-opened", "sha256": "a" * 64}
    base = json.loads((args.device_input_reference / "0-cell.json").read_text())
    manifest = json.loads((args.device_input_reference / "1-media-canary-manifest.json").read_text())
    layout = {key: Path(template["attempt"][key]) for key in ("stage", "data", "runtime", "user_runtime", "evidence")}
    layout["cell_runtime"] = Path("/run/droidloom/cells/u" + str(template["attempt"]["host_uid"]))
    probes = {key: {"package": "org.droidloom.signalprobe" + (".r3" if key == "r3" else ""),
                    "path": "/declared-synthetic-APK-not-opened", "sha256": key * 32,
                    "version": 1 if key == "r2" else 3, "bytes": 123, "instrumentation": "fixture"}
              for key in ("r2", "r3")}
    records = [{"relative": r["relative"], "sha256": r["sha256"], "bytes": r["bytes"]} for r in manifest["records"]]
    for row in records:
        if row["relative"] == "payload/39/libberberis_arm64.so":
            row.update(sha256="a" * 64, bytes=20)
    prepared = {"schema": 1, "kind": "isolated-owned-signal-canary-r1", "arm": "signal-mask-r1", "production_ready": False,
                "name": template["attempt"]["name"], "engine_sha256": "a" * 64,
                "presenter": template["presenter"]["path"], "presenter_sha256": template["presenter"]["sha256"],
                "framework_guard": template["framework_guard"]["path"], "framework_guard_sha256": template["framework_guard"]["sha256"],
                "copied_records": records, "apks": {key: dict(value, path=str(layout["stage"] / "tests" / ("signal-" + key + ".apk"))) for key, value in probes.items()},
                "data_images": [{"name": "data.img", "bytes": 8 * 1024**3, "fresh_O_EXCL_created": True},
                                {"name": "metadata.img", "bytes": 128 * 1024**2, "fresh_O_EXCL_created": True}],
                "nonce": "0" * 32, "nonces": {revision + "-" + case: str(i + 1) * 32 for i, (revision, case) in enumerate(runtime.CASES)},
                **{key: str(value) for key, value in layout.items()}}
    controls = []

    def test(name, value, reject=False):
        error = None
        try:
            runtime.verify_prepared_sets(template, value, base, manifest, probes, 20, layout)
        except (RuntimeError, KeyError, TypeError) as failure:
            error = str(failure)
        passed = (error is not None) == reject
        controls.append({"name": name, "passed": passed, "expected_rejection": reject, "error": error})
        if not passed:
            raise RuntimeError(name)

    test("synthetic-complete-admission-sets-only", prepared)
    for key, value in (("copied_records", []), ("apks", {}), ("data_images", []), ("nonces", {})):
        changed = copy.deepcopy(prepared); changed[key] = value
        test("reject-empty-" + key, changed, True)
    changed = copy.deepcopy(prepared); changed["copied_records"].pop()
    test("reject-one-missing-runtime-record", changed, True)
    changed = copy.deepcopy(prepared); changed["apks"].pop("r3")
    test("reject-missing-r3", changed, True)
    changed = copy.deepcopy(prepared); changed["data_images"][1] = dict(changed["data_images"][0])
    test("reject-duplicate-data-instead-of-metadata", changed, True)
    changed = copy.deepcopy(prepared); changed["nonces"]["r3-smc-mask-edit"] = changed["nonce"]
    test("reject-reused-nonce", changed, True)
    changed = copy.deepcopy(prepared); changed["presenter"] = "/usr/bin/unreviewed-presenter"
    test("reject-changed-action-target", changed, True)
    changed = copy.deepcopy(prepared); changed["engine_sha256"] = "b" * 64
    test("reject-changed-engine-identity", changed, True)
    cell = runtime.expected_cell_spec(base, template, layout)
    if (cell["data_dir"] != str(layout["data"]) or cell["shared_storage_directories"] != [] or
        cell["denial_socket"] != str(layout["user_runtime"] / "droidloom/native-bridge.sock") or
        any(not Path(row["source"]).is_relative_to(layout["stage"]) for key in
            ("android_file_overrides", "android_runtime_directories") for row in cell[key])):
        raise RuntimeError("fresh spec derivation differs")
    controls.append({"name": "exact-spec-derivation-uses-only-owned-data-and-sources", "passed": True})

    # The loader gets read-only fixtures. Any accidental use of a real Main
    # observation or process operation is a failure, even before run().
    def forbidden(*args, **kwargs):
        raise RuntimeError("runtime action accidentally executed by the original-source loader")

    fixture_prep = types.SimpleNamespace(read_json=lambda *a: json.loads((args.device_input_reference / "4-cpu-inventory-v2.json").read_text()),
        CPU_INVENTORY_SHA="fixture", load_guard=lambda *a: {"require_unchanged": forbidden, "capture_android": forbidden}, main_snapshot=forbidden)
    saved_run = runtime.subprocess.run
    try:
        runtime.subprocess.run = forbidden
        scope = runtime.original_runtime(fixture_prep, template, prepared, args.preparation_source)
    finally:
        runtime.subprocess.run = saved_run
    forbidden_legacy = {"PKG", "PARSER", "ONCE_PARSER", "BASE", "install_probe", "normal_probe", "default_alarm_probe"}
    if forbidden_legacy.intersection(scope):
        raise RuntimeError("legacy Activity/control code entered runtime scope")
    original = (args.preparation_source / "v5_original.py").read_text()
    tree = ast.parse(original)
    functions = {node.name: {"source_sha256": hashlib.sha256(ast.get_source_segment(original, node).encode()).hexdigest(),
                             "first_line": node.lineno}
                 for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in runtime.RETAINED_FUNCTIONS}
    if set(functions) != set(runtime.RETAINED_FUNCTIONS):
        raise RuntimeError("retained function set differs")
    controls.append({"name": "18-original-v5-function-definitions-loaded-with-no-side-effects", "passed": True})
    print(json.dumps({"schema": 1, "state": "LOCAL_RUNTIME_CONTROLS_PASS", "controls": controls,
        "retained_original_functions": functions, "device_operations": 0, "native_execution": False,
        "actual_isolated_Android_qualification": "NOT_RUN", "synthetic_scope": "complete-set admission and loader only"}, indent=2))


if __name__ == "__main__":
    main()
