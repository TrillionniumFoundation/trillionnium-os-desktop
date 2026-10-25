#!/usr/bin/env python3
"""Freeze actual available policy/interface sources and report missing execution inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import comparison as contract

POLICY = "codex-rs/hepta-agentd/src/cpu_policy.rs"
HEPTA_FILES = (
    POLICY,
    "codex-rs/hepta-agentd/src/hos2_device.rs",
    "codex-rs/hepta-agentd/src/production_writer_host.rs",
    "codex-rs/hepta-memory/src/production_hos2.rs",
)
DESKTOP_FILES = (
    "docs/VALIDATION.md", "docs/HEPTA_INTEGRATION.md",
    "tests/workloads/hepta_cpu_control/run_native_owner.py",
    "tests/workloads/hepta_cpu_control/native_owner_evidence.py",
    "tests/organ_backend/smp2/run_parallel_candidate.py",
    "tests/workloads/policy_comparison/comparison.py",
    "tests/workloads/policy_comparison/freeze_inputs.py",
    "tests/workloads/policy_comparison/native_observation.py",
)


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE)


def snapshot(root, paths):
    root = Path(root).resolve(strict=True)
    contract.require(git(root, "rev-parse", "--show-toplevel").decode().strip() == str(root),
                     "an exact repository worktree root is required")
    flags = git(root, "ls-files", "-v", "-z").split(b"\0")
    contract.require(all(not line or line.startswith(b"H ") for line in flags),
                     "tracked skip-worktree/assume-unchanged or unresolved files are forbidden")
    contract.require(not git(root, "status", "--porcelain=v1", "--untracked-files=no", "--ignore-submodules=none"),
                     "tracked source files must be clean before freezing")
    files = {}
    for relative in paths:
        git(root, "ls-files", "--error-unmatch", "--", relative)
        path = root / relative
        contract.require(path.is_file() and not path.is_symlink(), "required original source missing: " + relative)
        raw = path.read_bytes()
        files[relative] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    return {"head": git(root, "rev-parse", "HEAD").decode().strip(),
            "tree": git(root, "rev-parse", "HEAD^{tree}").decode().strip(),
            "files": files, "verification": "tracked clean tree and selected actual bytes; not remote attestation"}


def inventory(desktop, hepta):
    before = {"desktop": snapshot(desktop, DESKTOP_FILES), "hepta": snapshot(hepta, HEPTA_FILES)}
    after = {"desktop": snapshot(desktop, DESKTOP_FILES), "hepta": snapshot(hepta, HEPTA_FILES)}
    contract.require(before == after, "sources changed while freezing experiment inputs")
    return {"schema": "hepta.cpu-policy-source-inventory.v1", "sources": before,
            "policy_rules": contract.POLICY_RULES,
            "implemented": {
                "fixed": {"source_sha256": before["hepta"]["files"][POLICY]["sha256"],
                          "entry": "CpuPolicyKind::Fixed", "target_cap_ns": "explicit plan input"},
                "feedback": {"source_sha256": before["hepta"]["files"][POLICY]["sha256"],
                             "entry": "CpuPolicyKind::Feedback", "demand": "real CpuDemandSample required"},
                "request_adapter": "CpuBudgetProposal::original_request -> AgentdHos2Device::install_request",
                "effect_path": "original-writer/grant-provider/ProductionHos2Target"},
            "existing_scope_only": {
                "native_owner": "finite original-owner effects/recovery prerequisite; no three-policy metrics",
                "smp2": "separate two-vCPU quota diagnostic, not this N0 policy comparison",
                "synthetic_cart": "not a native CPU or actual Hepta policy arm"},
            "missing_execution_inputs": [
                "common workload ELF/source/data and complete task IDs",
                "common kernel/rootfs and whole-arm local/external resource ceilings",
                "frozen initial budget, warmup, fault schedule, randomized repeats and environment",
                "actual trusted wait-cause collector and final-consumer freshness integration",
                "source-bound original-owner controller entries for all three arms",
                "actual Hepta model/provider configuration",
                "all-cost collector including external inference and attributable energy"],
            "runtime_blockers": list(contract.RUNTIME_BLOCKERS),
            "runnable": False, "comparison_complete": False, "ranking_allowed": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desktop-source", type=Path, required=True)
    parser.add_argument("--hepta-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = inventory(args.desktop_source, args.hepta_source)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 2
    with args.output.open("x", encoding="utf-8") as output:
        output.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"sources": {name: {key: item[key] for key in ("head", "tree")}
                                   for name, item in result["sources"].items()},
                      "runnable": False, "missing_execution_inputs": result["missing_execution_inputs"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
