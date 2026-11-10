#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run unchanged Camera2 controls plus checked-disconnect source differential."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

REPAIR = Path(__file__).resolve().parents[1]
CAMERA = REPAIR.parent
ORIGINAL_CASES = [
    "healthy characteristics and selected facing",
    "enumerated device disappears before characteristics",
    "enumeration race preserves remaining connected device",
    "cached device removal selects replacement",
    "camera service checked failure retains cause",
    "unrelated runtime failure is not swallowed",
    "missing lens facing skipped",
    "null device list is unavailable",
    "null ID entry skipped",
    "null selected device becomes checked failure",
    "null characteristics becomes checked failure",
    "availability event invalidates same ID facing cache",
    "cached ID list failure reports unavailable",
    "external camera fallback retained",
    "callback registration and teardown retained",
]
NEW_CASES = [
    "checked disconnect retains following back camera",
    "checked disconnect retains following front camera",
    "checked disconnect retains external fallback",
    "all checked disconnects terminate within existing passes",
    "list service disconnect does not query metadata",
    "camera disabled preserves failure behavior",
    "camera error preserves failure behavior",
    "camera in use preserves failure behavior",
    "maximum cameras preserves failure behavior",
    "direct selected disconnect retains checked cause",
    "enumeration security exception is not swallowed",
]
MANAGER = "source/packages/apps/Camera2/src/com/android/camera/one/v2/Camera2OneCameraManagerImpl.java"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_inputs(lock):
    result = {}
    for root, key in ((CAMERA, "original_bundle_files"), (REPAIR, "repair_files")):
        for relative, expected in lock[key].items():
            path = root / relative
            if path.is_symlink() or digest(path) != expected:
                raise RuntimeError("input mismatch: " + key + "/" + relative)
            result[key + "/" + relative] = expected
    return result


def run(command, output, label, timeout):
    completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    (output / (label + ".stdout")).write_text(completed.stdout)
    (output / (label + ".stderr")).write_text(completed.stderr)
    return {
        "argv": command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def case_statuses(stdout):
    result = []
    for line in stdout.splitlines():
        if line.startswith("PASS "):
            result.append([line[5:], "PASS"])
        elif line.startswith("FAIL "):
            result.append([line[5:].split(":", 1)[0], "FAIL"])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java", default=shutil.which("java"))
    parser.add_argument("--javac", default=shutil.which("javac"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not args.java:
        raise SystemExit("A Java runtime and its compiler module are required")
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    lock_path = REPAIR / "source-lock.json"
    lock = json.loads(lock_path.read_text())
    lock_sha = digest(lock_path)
    before = verify_inputs(lock)
    java = str(Path(args.java).resolve())
    if args.javac:
        javac = str(Path(args.javac).resolve())
        compiler = [javac, "-J-XX:ActiveProcessorCount=2", "-J-Xmx256m"]
        compiler_identity = {"path": javac, "sha256": digest(Path(javac))}
    else:
        compiler = [java, "-XX:ActiveProcessorCount=2", "-Xmx256m",
                    "-m", "jdk.compiler/com.sun.tools.javac.Main"]
        compiler_identity = {"mode": "installed jdk.compiler module"}
    java_identity = {"path": java, "sha256": digest(Path(java))}
    modules = Path(java).parent.parent / "lib/modules"
    if modules.is_file():
        java_identity["modules_sha256"] = digest(modules)
    versions = {
        "java": run([java, "-version"], output, "java-version", 10),
        "compiler": run([*compiler, "-version"], output, "compiler-version", 10),
    }
    if any(row["exit_code"] != 0 for row in versions.values()):
        raise RuntimeError("Java/compiler version probe failed")
    original_lock = json.loads((CAMERA / "source-lock.json").read_text())
    bindings = []
    for relative in sorted(original_lock["host_test_bindings"]):
        replacement = REPAIR / relative
        bindings.append(str(replacement if replacement.is_file() else CAMERA / relative))
    bindings.append(str(REPAIR / "tests/bindings/CheckedDisconnectRegression.java"))
    result = {
        "schema": "pocket4-camera-checked-disconnect-host-v1",
        "scope": "Complete manager on host test bindings; not Android camera or APK qualification.",
        "production_ready": False,
        "source_lock_sha256": lock_sha,
        "java": java_identity,
        "compiler": compiler_identity,
        "versions": versions,
        "original_cases": len(ORIGINAL_CASES),
        "new_cases": len(NEW_CASES),
        "arms": {},
    }
    with tempfile.TemporaryDirectory(prefix="camera-disconnect-controls-") as temp:
        for label, source in (("release07_preimage", CAMERA / MANAGER),
                              ("checked_disconnect_candidate", REPAIR / MANAGER)):
            classes = Path(temp) / label
            classes.mkdir()
            compile_result = run(
                [*compiler, "-encoding", "UTF-8", "-source", "8", "-target", "8",
                 "-d", str(classes), *bindings, str(source)], output, label + "-compile", 60)
            row = {"source_sha256": digest(source), "compile": compile_result, "verified": False}
            result["arms"][label] = row
            if compile_result["exit_code"] != 0:
                continue
            manager_class = classes / "com/android/camera/one/v2/Camera2OneCameraManagerImpl.class"
            row["host_manager_class_sha256"] = digest(manager_class)
            row["host_manager_class_is_not_an_android_release"] = True
            old = run([java, "-XX:ActiveProcessorCount=2", "-Xmx256m", "-cp", str(classes),
                       "HotplugRegression"], output, label + "-original15", 30)
            new = run([java, "-XX:ActiveProcessorCount=2", "-Xmx256m", "-cp", str(classes),
                       "CheckedDisconnectRegression"], output, label + "-checked11", 30)
            row["original_regression"] = old
            row["checked_disconnect_regression"] = new
            row["original15_verified"] = (
                old["exit_code"] == 0 and not old["stderr"]
                and case_statuses(old["stdout"]) == [[name, "PASS"] for name in ORIGINAL_CASES]
                and old["stdout"].splitlines()[-1] == "TOTAL_PASS=15")
            expected = [[name, "FAIL" if label == "release07_preimage" and i < 3 else "PASS"]
                        for i, name in enumerate(NEW_CASES)]
            expected_summary = ("TOTAL_PASS=8 TOTAL_FAIL=3" if label == "release07_preimage"
                                else "TOTAL_PASS=11 TOTAL_FAIL=0")
            row["checked11_verified"] = (
                new["exit_code"] == (1 if label == "release07_preimage" else 0)
                and not new["stderr"] and case_statuses(new["stdout"]) == expected
                and new["stdout"].splitlines()[-1] == expected_summary)
            row["verified"] = row["original15_verified"] and row["checked11_verified"]
    result["inputs_unchanged"] = verify_inputs(lock) == before and digest(lock_path) == lock_sha
    result["test_runner_sha256"] = digest(Path(__file__))
    result["success"] = result["inputs_unchanged"] and all(row["verified"] for row in result["arms"].values())
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"success": result["success"], "result": str(output / "result.json"),
                      "arms": {name: {"verified": row["verified"],
                                       "original15_verified": row.get("original15_verified", False),
                                       "checked11_verified": row.get("checked11_verified", False)}
                               for name, row in result["arms"].items()}}, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
