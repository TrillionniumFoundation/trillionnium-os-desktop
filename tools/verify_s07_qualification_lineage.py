#!/usr/bin/env python3
"""Bind historical patch provenance and current event Git identity separately.

This verifier checks Git metadata and source contracts. Its result cannot prove
that S06 source tests, the complete patch, or actual Servo behavior executed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

try:
    from .artifact_evidence import load
except ImportError:
    from artifact_evidence import load

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "contracts/s07-qualification-lineage.v1.json"
MANIFEST = "manifests/lab-d3-servo-retained-node-action.v1.json"
HISTORICAL = {
    "repository_url": "https://github.com/TrillionniumFoundation/trillionnium-os-desktop.git",
    "commit": "f0e947e5e7267a3fcdd0a7d5437c0ae00c09ebfe",
    "tree": "b0b0304d70b209e26a08ed8a9d7e26f8a25cba02",
    "parents": ["648b204618328c2f9b9271ed6eb6db8aea7d8987"],
    "carrier_branch": "codex/s07-servo-retained-node-closure-v1",
    "meaning": "historical_extracted_patch_provenance_only",
}
PIN = "670ae8a70801b162e186f81cbb5bdd2d59c39108"
CURRENT = {
    "modes": ["exact-head", "prospective-merge"],
    "external_expected_event_sha_required": True,
    "current_checkout_clean_required": True,
    "prospective_parents": "exact_current_live_base_then_current_head",
    "historical_ancestor_required": False,
    "current_s06_source_tests_and_compile_fail_required": True,
    "current_public_export_guard_required": True,
    "complete_original_patch_and_actual_pin_required": True,
    "servo_commit": PIN,
    "runtime_evidence": "new_exact_event_run_never_inherited_historical_pass",
}
NON_CLAIMS = {
    "historical_git_metadata_is_current_s06_runtime": False,
    "metadata_verifier_is_servo_execution": False,
    "current_candidate_is_asserted_historical_descendant": False,
    "installed_product_or_hardware_qualified": False,
    "production_activation_or_release_authorized": False,
}
EXPECTED = {
    "schema": "trillionnium.desktop.s07-qualification-lineage.v1",
    "status": "SOURCE_METADATA_AND_CI_CONTRACT_ONLY",
    "historical_carrier": HISTORICAL,
    "current_qualification": CURRENT,
    "non_claims": NON_CLAIMS,
}
PARENT_BINDING = "historical_carrier_commit_tree_parent_exact_plus_current_pull_request_base_sha_head_sha_and_merge_parent_order"


def typed_equal(actual: object, expected: object) -> None:
    if type(actual) is not type(expected):
        raise ValueError("lineage contract has a different exact type")
    if isinstance(expected, dict):
        if set(actual) != set(expected):
            raise ValueError("lineage contract has missing or unknown fields")
        for name in expected:
            typed_equal(actual[name], expected[name])
    elif isinstance(expected, list):
        if len(actual) != len(expected):
            raise ValueError("lineage contract list changed")
        for left, right in zip(actual, expected):
            typed_equal(left, right)
    elif actual != expected:
        raise ValueError("lineage contract differs from its fixed source scope")


def git(root: Path, *arguments: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(root), *arguments], timeout=30)


def sha(value: str) -> str:
    if type(value) is not str or not re.fullmatch("[0-9a-f]{40}", value):
        raise ValueError("expected event identity must be one complete lowercase Git SHA")
    return value


def commit(root: Path, identity: str) -> dict:
    identity = sha(identity)
    if git(root, "cat-file", "-t", identity).strip() != b"commit":
        raise ValueError("Git identity is not a commit")
    size = int(git(root, "cat-file", "-s", identity).strip())
    if size > 65536:
        raise ValueError("Git commit metadata exceeds its bound")
    data = git(root, "cat-file", "commit", identity)
    if len(data) != size or hashlib.sha1(b"commit " + str(size).encode() + b"\0" + data).hexdigest() != identity:
        raise ValueError("Git commit bytes do not match their identity")
    headers = data.split(b"\n\n", 1)[0].splitlines()
    trees = [line[5:].decode("ascii") for line in headers if line.startswith(b"tree ")]
    parents = [line[7:].decode("ascii") for line in headers if line.startswith(b"parent ")]
    if len(trees) != 1:
        raise ValueError("Git commit has no unique tree")
    tree = sha(trees[0])
    for parent in parents:
        sha(parent)
    if git(root, "cat-file", "-t", tree).strip() != b"tree":
        raise ValueError("Git commit tree is absent")
    return {"commit": identity, "tree": tree, "parents": parents}


def verify(root: Path, mode: str, expected_sha: str, expected_base: str | None = None,
           expected_head: str | None = None) -> dict:
    if mode not in CURRENT["modes"]:
        raise ValueError("unknown current qualification mode")
    typed_equal(load(root / CONTRACT), EXPECTED)
    manifest = load(root / MANIFEST)
    typed_equal(manifest.get("qualification_lineage"), EXPECTED)
    if manifest.get("carrier_base_commit") != HISTORICAL["commit"] or manifest.get("carrier_branch") != HISTORICAL["carrier_branch"]:
        raise ValueError("original historical carrier identity changed")
    if manifest.get("carrier_parent_binding") != PARENT_BINDING or manifest.get("upstream", {}).get("commit") != PIN:
        raise ValueError("current lineage description or exact Servo PIN changed")
    actual_sha = git(root, "rev-parse", "HEAD").decode("ascii").strip()
    if actual_sha != sha(expected_sha):
        raise ValueError("current checkout differs from the exact expected event object")
    if git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("current qualification checkout is not clean")
    current = commit(root, actual_sha)
    if mode == "prospective-merge":
        if expected_base is None or expected_head is None or current["parents"] != [sha(expected_base), sha(expected_head)]:
            raise ValueError("prospective parents do not match current live base/head order")
    elif expected_base is not None or expected_head is not None:
        raise ValueError("exact head mode does not accept prospective parent assertions")
    historical = commit(root, HISTORICAL["commit"])
    if historical["tree"] != HISTORICAL["tree"] or historical["parents"] != HISTORICAL["parents"]:
        raise ValueError("historical commit/tree/parents differ from fixed provenance")
    return {
        "schema": "trillionnium.s07-source-lineage-result.v1",
        "status": "PASS_GIT_METADATA_AND_SOURCE_CONTRACT_ONLY",
        "mode": mode, "current": current, "historical_carrier": historical,
        "actual_s06_execution_observed": False,
        "actual_servo_execution_observed": False,
        "historical_ancestry_asserted": False,
        "installed_qualification": False, "production_activation": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--mode", choices=CURRENT["modes"], required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--expected-base")
    parser.add_argument("--expected-head")
    args = parser.parse_args()
    try:
        result = verify(args.root, args.mode, args.expected_sha, args.expected_base, args.expected_head)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"S07 source lineage verification failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
