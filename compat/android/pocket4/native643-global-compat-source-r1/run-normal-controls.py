#!/usr/bin/env python3
"""Rebuild the actual producer and execute the974 set; never start Android work."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("native643_capsule_verify", HERE / "verify.py")
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)
need = VERIFY.need


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cargo", default="cargo")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--inventory-sha256", required=True)
    args = parser.parse_args()
    root, output = args.workspace.absolute(), args.output.absolute()
    need(root.resolve() == root, "producer path or parent cannot be an alias")
    manifest, capsule_proof = VERIFY.verify_capsule(HERE, args.inventory_sha256)
    before_source = VERIFY.verify_producer(root, manifest)
    output = VERIFY.fresh_destination(output, [root, HERE])
    output.mkdir(parents=True, mode=0o700)
    target = output / "target"
    env = dict(os.environ, CARGO_TARGET_DIR=str(target), CARGO_BUILD_JOBS="1", CARGO_INCREMENTAL="0", CARGO_TERM_COLOR="never")
    records = []
    tests = {k: json.loads((HERE / "normal-test-names" / (k + "-control-test-names.json")).read_bytes()) for k in ("pair", "source", "permissions", "focused")}
    tests["journal"] = json.loads((HERE / "normal-test-names/journal-regression-test-names.json").read_bytes())
    before_lock = VERIFY.digest((root / "Cargo.lock").read_bytes())

    def run(name, argv, timeout=1800):
        begun = time.time_ns()
        child = subprocess.Popen(argv, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        timed_out = False
        try:
            stdout, stderr = child.communicate(timeout=timeout)
        except BaseException:
            timed_out = True
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                stdout, stderr = child.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                stdout, stderr = child.communicate(timeout=10)
        for side, raw in (("stdout", stdout), ("stderr", stderr)):
            (output / (name + "." + side)).write_bytes(raw)
        row = {"name": name, "argv": argv, "returncode": child.returncode, "pid": child.pid,
               "actual_child_reaped": True, "timed_out": timed_out, "begun_ns": begun,
               "finished_ns": time.time_ns(), "stdout": VERIFY.digest(stdout), "stderr": VERIFY.digest(stderr)}
        records.append(row)
        (output / (name + ".json")).write_text(json.dumps(row, indent=2, sort_keys=True) + "\n")
        need(not timed_out and child.returncode == 0, "ordinary command failed; raw output retained: " + name)
        return stdout.decode()

    def cargo(operation, packages, *rest):
        argv = [args.cargo, operation, "--locked"]
        if args.offline:
            argv.append("--offline")
        argv += ["-j", "1"]
        for package in packages:
            argv += ["-p", package]
        return argv + list(rest)

    def artifact(text, package, kind, is_test):
        messages = [json.loads(line) for line in text.splitlines() if line]
        finished = [row for row in messages if row.get("reason") == "build-finished"]
        need(len(finished) == 1 and messages[-1] == finished[0] and finished[0].get("success") is True,
             "one complete successful Cargo artifact terminal required")
        name = package.replace("-", "_") if kind == "lib" else package
        found = [r for r in messages if r.get("reason") == "compiler-artifact" and r["target"]["name"] == name and kind in r["target"]["kind"] and r["profile"]["test"] is is_test and r.get("executable")]
        need(len(found) == 1, "one actual ordinary Cargo executable required")
        row = found[0]
        need(row["target"]["src_path"] == str(root / "tools" / package / "src" / ("lib.rs" if kind == "lib" else "main.rs")), "Cargo must compile the captured real producer")
        path = Path(row["executable"]).absolute()
        need(path.resolve() == path and path.is_relative_to(target) and path.read_bytes()[:4] == b"\x7fELF", "actual Linux ELF in this new target directory required")
        return str(path)

    def execute_tests(name, binary, expected, *filters):
        text = run(name, [binary, *filters, "--test-threads=1", "--color", "never"])
        return VERIFY.test_terminal(text, expected)

    result = {"schema": "pocket4-native643-current-normal-controls-v1", "state": "STARTED", "errors": [], "AOSP_source_writes": 0, "AOSP_full_builds_started": 0, "runtime_qualified": False, "production_ready": False, "capsule": capsule_proof}
    try:
        update = artifact(run("compile-update-tests", cargo("test", ["droidloom-update"], "--no-run", "--message-format=json")), "droidloom-update", "bin", True)
        names = run("list-update-tests", [update, "--list"])
        listed = [line[:-6] for line in names.splitlines() if line.endswith(": test")]
        need(all(listed.count(n) == 1 for k in ("pair", "permissions", "journal", "focused") for n in tests[k]), "each pinned test is present exactly once in the real harness")
        executions = 0
        for index, test in enumerate(tests["focused"]):
            executions += execute_tests("focused-" + str(index), update, [test], test, "--exact")
        executions += execute_tests("all50-pair", update, tests["pair"], "native_generation_pair_build::")
        executions += execute_tests("all7-permissions", update, tests["permissions"], "android::tests::projection_v2_")
        for index, test in enumerate(tests["journal"]):
            executions += execute_tests("journal-" + str(index), update, [test], test, "--exact")
        source_tests = artifact(run("compile-source-tests", cargo("test", ["droidloom-source"], "--lib", "--no-run", "--message-format=json")), "droidloom-source", "lib", True)
        executions += execute_tests("all26-source", source_tests, tests["source"])
        clis = run("compile-both-normal-clis", cargo("build", ["droidloom-source", "droidloom-update"], "--message-format=json"))
        source = artifact(clis, "droidloom-source", "bin", False)
        update_cli = artifact(clis, "droidloom-update", "bin", False)
        run("source-help", [source, "--help"])
        run("update-help", [update_cli, "--help"])
        lock = str(root / "android/native-generation-pair/source-lock.json")
        run("source-verify-lock", [source, "verify-lock", "--lock", lock])
        plan = json.loads(run("source-plan", [source, "plan", "--lock", lock]))
        need(len(plan["projects"]) == 643 and len(plan["links"]) == 8 and plan["unrestricted_repo_sync"] is False and plan["superproject_commit"] == "28f0bbddc24d56c8ec5a8df5342ac7a292184039", "exact latest source plan required")
        need(executions == 95 and len(records) == 23, "complete ordinary source-only command/test set required")
        result.update(state="NORMAL_SOURCE_CONTROLS_PASSED", distinct_tests=89, test_executions=95, actual_commands=23, actual_source_projects=643, actual_root_links=8)
    except BaseException as error:
        result["state"] = "FAILED"
        result["errors"].append({"type": type(error).__name__, "message": str(error)})
    finally:
        try:
            need(VERIFY.verify_producer(root, manifest) == before_source, "all569 original source F9 changed during CI")
            need(before_lock == VERIFY.digest((root / "Cargo.lock").read_bytes()), "original Cargo lock changed")
            result["all569_source_inputs_unchanged"] = True
        except BaseException as error:
            result["state"] = "FAILED"
            result["errors"].append({"stage": "source_after", "type": type(error).__name__, "message": str(error)})
        result["commands"] = records
        (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: result[k] for k in ("state", "errors", "runtime_qualified", "production_ready")}, sort_keys=True))
    return 0 if result["state"] == "NORMAL_SOURCE_CONTROLS_PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
