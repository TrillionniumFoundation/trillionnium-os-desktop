#!/usr/bin/env python3
"""Verify r5's external qualifications before fresh preparation; never start services."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import traceback

sys.dont_write_bytecode = True
HERE = Path(__file__).parent

def need(value, message):
    if not value:
        raise RuntimeError(message)

def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def manifest(path, expected):
    path = Path(path)
    need(path.is_absolute() and re.fullmatch(r"[0-9a-f]{64}", expected or ""), "explicit source manifest pin required")
    need(sha(path) == expected, "source manifest changed")
    result = json.loads(path.read_text())
    for name, row in result["files"].items():
        rel = Path(name)
        need(not rel.is_absolute() and ".." not in rel.parts, "bad source manifest path")
        source = path.parent / rel
        info = source.lstat()
        need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size == row["bytes"]
             and sha(source) == row["sha256"], "source payload changed: " + name)
    return result

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

def qualify(args):
    current = manifest(args.source_manifest, args.source_manifest_sha256)
    need(Path(args.source_manifest).parent.resolve() == HERE.resolve()
         and current["artifact"] == "isolated-signal-canary-runtime-r5"
         and {"run.py", "prepare_runtime.py", "held_runtime.py", "failure_evidence.py",
              "held_namespace_entry.rs", "cleanup_owned.py"}.issubset(current["files"]),
         "wrong or incomplete preparation coordinator source")
    runtime = load(HERE / "run.py", "qualified_private_runtime_r5")
    source = Path(args.preparation_source).resolve(strict=True)
    manifest(source / "source-manifest.json", runtime.PREPARATION_MANIFEST_SHA)
    prep = load(source / "prepare.py", "qualified_original_preparation_r1")
    host = runtime.qualified_host_wrapper(current, args.host_wrapper_source_manifest)
    helper = runtime.verify_helper_qualification(args.namespace_helper_qualification,
                                                args.namespace_helper_qualification_sha256)
    need(args.namespace_helper_sha256 == runtime.HELPER_BINARY_SHA
         and args.namespace_helper_source_sha256 == runtime.HELPER_SOURCE_SHA,
         "namespace helper pin differs")
    for path, digest, executable in ((args.namespace_helper, args.namespace_helper_sha256, True),
                                    (args.namespace_helper_source, args.namespace_helper_source_sha256, False)):
        prep.pinned_file({"path": path, "sha256": digest}, executable=executable)
        info = Path(path).lstat()
        need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_mode & 0o022 == 0,
             "namespace helper input is aliased or writable by others")
    config = prep.load_inputs(Path(args.inputs), args.inputs_sha256)
    need(Path(config["runner_manifest"]["path"]).resolve() == source / "source-manifest.json"
         and config["runner_manifest"]["sha256"] == runtime.PREPARATION_MANIFEST_SHA,
         "input selects a different preparation source")
    suite = host.verify_report(Path(args.host_suite_receipt), args.host_suite_sha256,
                               config["candidate_build_receipt"], config["engine"],
                               runtime.HOST_WRAPPER_MANIFEST_SHA)
    helper_inputs = prep.read_json({"path": args.host_launch_inputs,
                                   "sha256": args.host_launch_inputs_sha256})
    need(helper_inputs["schema"] == 1 and set(helper_inputs["tools"]) == {
        "/usr/local/libexec/droidloom-compat/unshare", "/usr/bin/unshare", "/usr/bin/ip", "/usr/bin/python3"},
        "complete host launch input set required")
    for path, digest in helper_inputs["tools"].items():
        prep.pinned_file({"path": path, "sha256": digest}, executable=True)
    base = prep.read_json(config["base"]["manifest"], prep.BASE_MANIFEST_SHA)
    need(helper_inputs["tools"]["/usr/local/libexec/droidloom-compat/unshare"] == base["host_compat_wrapper_sha256"]
         and helper_inputs["tools"]["/usr/bin/unshare"] == base["host_unshare_sha256"],
         "original launch tool binding changed")
    contract = {"schema": 1, "runtime_manifest_sha256": args.source_manifest_sha256,
                "input_sha256": args.inputs_sha256, "host_suite_sha256": args.host_suite_sha256,
                "host_wrapper_manifest_sha256": runtime.HOST_WRAPPER_MANIFEST_SHA,
                "preparation_manifest_sha256": runtime.PREPARATION_MANIFEST_SHA,
                "namespace_entry_qualification": helper,
                "namespace_helper_sha256": runtime.HELPER_BINARY_SHA,
                "namespace_helper_source_sha256": runtime.HELPER_SOURCE_SHA,
                "host_launch_inputs_sha256": args.host_launch_inputs_sha256,
                "services_started": False, "old_data_read": False}
    return prep, config, contract

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("check-inputs", "prepare"))
    for name in ("inputs", "inputs-sha256", "preparation-source", "source-manifest",
                 "source-manifest-sha256", "host-wrapper-source-manifest", "host-suite-receipt",
                 "host-suite-sha256", "host-launch-inputs", "host-launch-inputs-sha256",
                 "namespace-helper", "namespace-helper-sha256", "namespace-helper-source",
                 "namespace-helper-source-sha256", "namespace-helper-qualification",
                 "namespace-helper-qualification-sha256"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    need(sys.flags.optimize == 0, "optimized Python is prohibited")
    prep, config, contract = qualify(args)
    if args.phase == "check-inputs":
        validated = prep.validate_inputs(config)
        print(json.dumps({"state": "QUALIFIED_INPUTS_CHECKED_NO_ACTIONS",
                          "main_epoch_sha256": validated["main"]["framework_sha256"], **contract}))
        return 0
    # All qualifications above are read-only. Only the original, exact
    # preparation implementation creates the fresh stage/data/nonce set.
    status = prep.prepare(config, Path(args.inputs), args.inputs_sha256)
    need(status["status"] == "PREPARED_NOT_STARTED", "original preparation did not finish")
    contract["prepared_sha256"] = status["prepared_sha256"]
    contract["state"] = "QUALIFIED_PREPARED_NOT_STARTED"
    evidence = prep.paths(config)["evidence"]
    prep.write_new(evidence / "preparation-entry-contract-r4.json", contract)
    print(json.dumps(contract))
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"state": "PREPARATION_GATE_OR_STAGE_FAILED_NO_RETRY",
                          "error": repr(error), "traceback": traceback.format_exc(),
                          "services_started": False, "automatic_retry": False}))
        raise SystemExit(1)
