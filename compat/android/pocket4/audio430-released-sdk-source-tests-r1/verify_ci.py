#!/usr/bin/env python3
"""Verify complete source inputs, replay the fixes, and check actual CI output.

This helper never invokes Cargo or Rust.  The documented A08 shell step invokes
the normal tools and saves their actual output before the result subcommand.
"""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tempfile
import tomllib


ROOT = Path(__file__).resolve().parent
SOURCE_NAMES = (
    "tools/droidloom-source/src/lib.rs",
    "android/manifest/audio-bridge-source-lock.json",
    "tools/droidloom-source/tests/fixtures/audio-source321-before-allgraph.json",
)
DIRECT = {
    "hex": "0.4.3", "serde": "1.0.229", "serde_json": "1.0.151",
    "sha2": "0.10.9", "tempfile": "3.27.0", "thiserror": "2.0.19",
}
SUMMARY = "test result: ok. 26 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;"


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def read_regular(path):
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
            "Expected a single-link regular input: " + str(path))
    raw = path.read_bytes()
    after = path.lstat()
    fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
              "st_size", "st_mtime_ns", "st_ctime_ns")
    require(tuple(getattr(before, k) for k in fields) ==
            tuple(getattr(after, k) for k in fields), "Input changed while reading")
    return raw


def pin(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def inventory():
    raw = read_regular(ROOT / "FILES.json")
    expected = json.loads(raw)
    require(type(expected) is dict and expected, "Expected exact input inventory")
    observed = set()
    for path in ROOT.rglob("*"):
        info = path.lstat()
        require(not stat.S_ISLNK(info.st_mode), "Symlink in source capsule")
        if stat.S_ISDIR(info.st_mode):
            continue
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                "Unexpected source member type")
        observed.add(path.relative_to(ROOT).as_posix())
    require(observed == set(expected) | {"FILES.json"}, "Source inventory differs")
    for name, want in expected.items():
        relative = PurePosixPath(name)
        require(not relative.is_absolute() and ".." not in relative.parts
                and str(relative) == name, "Non-canonical source path")
        require(pin(read_regular(ROOT / name)) == want, "Source pin differs: " + name)
    return {"manifest": pin(raw), "files": expected}


def expected_tests():
    data = json.loads(read_regular(ROOT / "EXPECTED-TESTS.json"))
    names = data["tests"]
    require(type(names) is list and len(names) == len(set(names)) == 26,
            "Exactly 26 unique source library tests are required")
    return names


def check_complete_source():
    source = read_regular(ROOT / "harness" / SOURCE_NAMES[0]).decode("utf-8")
    original = read_regular(ROOT / "preimages" / SOURCE_NAMES[0]).decode("utf-8")
    names = re.findall(r"#\[test\]\s*fn\s+(\w+)", source)
    require(names == expected_tests(), "Complete source test inventory differs")
    require(not re.search(r"#\[ignore(?:\]|\s*=)", source), "Ignored source test")
    marker = "#[cfg(test)]\nmod tests {"
    require(source.count(marker) == original.count(marker) == 1,
            "Expected one original source test module")
    require(source.split(marker)[0] == original.split(marker)[0],
            "The followup must preserve the complete production library prefix")
    require(set(re.findall(r'include_(?:str|bytes)!\("([^\"]+)"\)', source)) == {
        "../../../android/manifest/audio-bridge-source-lock.json",
        "../tests/fixtures/audio-source321-before-allgraph.json",
    }, "Unexpected compile-time source input")
    manifest = tomllib.loads(read_regular(ROOT / "harness/Cargo.toml").decode())
    deps = manifest["dependencies"]
    require(set(deps) == set(DIRECT), "Source library dependency inventory differs")
    for name, version in DIRECT.items():
        item = deps[name]
        observed = item["version"] if isinstance(item, dict) else item
        require(observed == "=" + version, "Direct dependency is not exact: " + name)
    require(deps["serde"] == {"version": "=1.0.229", "features": ["derive"]},
            "Original serde derive support is required")
    require(manifest["lib"]["path"] == SOURCE_NAMES[0], "Complete library path differs")


def replay(parent):
    with tempfile.TemporaryDirectory(prefix="audio-source-replay-", dir=parent) as tmp:
        work = Path(tmp)
        for name in SOURCE_NAMES[:2]:
            target = work / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(read_regular(ROOT / "preimages" / name))
        commands = [
            ["git", "apply", "--include=android/manifest/audio-bridge-source-lock.json",
             str(ROOT / "patches/published-sdk-inputs.patch")],
            ["git", "apply", str(ROOT / "patches/source-lib-history-followup.patch")],
        ]
        for command in commands:
            check = command[:2] + ["--check"] + command[2:]
            subprocess.run(check, cwd=work, check=True, capture_output=True, timeout=30)
            subprocess.run(command, cwd=work, check=True, capture_output=True, timeout=30)
        for name in SOURCE_NAMES[:2]:
            require(read_regular(work / name) == read_regular(ROOT / "harness" / name),
                    "Exact source replay differs: " + name)


def write_json_new(path, data):
    with path.open("x", encoding="utf-8") as output:
        json.dump(data, output, indent=2, sort_keys=True)
        output.write("\n")


def prepare(args):
    before = inventory()
    check_complete_source()
    work = Path(args.work).absolute()
    require(not work.is_relative_to(ROOT), "CI work must be outside the source capsule")
    require(not work.exists(), "CI work must be a fresh directory")
    work.parent.mkdir(parents=True, exist_ok=True)
    replay(work.parent)
    work.mkdir()
    for name in SOURCE_NAMES:
        target = work / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(read_regular(ROOT / "harness" / name))
    (work / "Cargo.toml").write_bytes(read_regular(ROOT / "harness/Cargo.toml"))
    if args.mode == "bootstrap":
        require(not args.lock_file, "Bootstrap must use the disclosed original seed")
        lock = read_regular(ROOT / "provenance/broker-harness-Cargo.lock")
        lock_role = "existing_public_broker_seed_requires_normal_cargo_resolution"
    else:
        require(args.lock_file, "Locked mode requires a separately frozen source lock")
        lock = read_regular(Path(args.lock_file))
        lock_role = "caller_supplied_frozen_source_harness_lock"
    (work / "Cargo.lock").write_bytes(lock)
    require(inventory() == before, "Capsule changed during preparation")
    report = {
        "schema": "audio430-source-library-ci-preparation-v1",
        "mode": args.mode, "capsule": before["manifest"],
        "source_inputs": {name: pin(read_regular(work / name)) for name in SOURCE_NAMES},
        "harness_manifest": pin(read_regular(work / "Cargo.toml")),
        "lock_input": pin(lock), "lock_input_role": lock_role,
        "complete_source_replay_verified": True, "expected_tests": 26,
        "rust_executed": False, "source_materialized": False,
        "complete_apex_qualified": False, "runtime_qualified": False,
    }
    write_json_new(Path(args.report), report)
    print(json.dumps(report, sort_keys=True))


def result(args):
    capsule = inventory()
    check_complete_source()
    work = Path(args.work)
    for name in SOURCE_NAMES:
        require(read_regular(work / name) == read_regular(ROOT / "harness" / name),
                "Source changed during actual Cargo execution: " + name)
    require(read_regular(work / "Cargo.toml") == read_regular(ROOT / "harness/Cargo.toml"),
            "Harness manifest changed during Cargo execution")
    lock_raw = read_regular(work / "Cargo.lock")
    require(lock_raw == read_regular(Path(args.resolved_lock)),
            "Resolved Cargo lock changed during actual tests")
    lock = tomllib.loads(lock_raw.decode())
    packages = lock["package"]
    for name, version in DIRECT.items():
        selected = [p for p in packages if p["name"] == name]
        require(len(selected) == 1 and selected[0]["version"] == version,
                "Resolved direct dependency differs: " + name)
    log_raw = read_regular(Path(args.log))
    log = log_raw.decode("utf-8")
    require(log.count(SUMMARY) == 1, "All 26 tests must pass without filtering or ignoring")
    actual = re.findall(r"^test tests::(\w+) \.\.\. ok$", log, re.MULTILINE)
    require(len(actual) == 26 and len(set(actual)) == 26
            and set(actual) == set(expected_tests()), "Executed test inventory differs")
    rustc = read_regular(Path(args.rustc_version)).decode("utf-8").strip()
    require(rustc.startswith("rustc 1.93.0 "), "Expected the existing pinned Rust 1.93.0")
    report = {
        "schema": "audio430-complete-source-library-ci-result-v1",
        "capsule": capsule["manifest"], "rustc_version": rustc,
        "resolved_source_harness_lock": pin(lock_raw), "actual_test_log": pin(log_raw),
        "tests_passed": 26, "failed": 0, "ignored": 0, "filtered_out": 0,
        "actual_tests": actual, "source_bytes_unchanged": True,
        "normal_recipe_tools_qualified": False, "original_sdk_blob_bytes_qualified": False,
        "source_materialized": False, "strict_soong_graph_qualified": False,
        "complete_apex_qualified": False, "runtime_qualified": False,
    }
    write_json_new(Path(args.report), report)
    print(json.dumps(report, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    first = commands.add_parser("prepare")
    first.add_argument("--mode", choices=("bootstrap", "locked"), required=True)
    first.add_argument("--work", required=True)
    first.add_argument("--report", required=True)
    first.add_argument("--lock-file")
    first.set_defaults(function=prepare)
    finish = commands.add_parser("result")
    finish.add_argument("--work", required=True)
    finish.add_argument("--log", required=True)
    finish.add_argument("--rustc-version", required=True)
    finish.add_argument("--resolved-lock", required=True)
    finish.add_argument("--report", required=True)
    finish.set_defaults(function=result)
    args = parser.parse_args()
    args.function(args)


if __name__ == "__main__":
    main()
