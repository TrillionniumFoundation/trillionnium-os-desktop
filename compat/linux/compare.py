#!/usr/bin/env python3
"""Compare identical ELF/input Linux-host and candidate-kernel JSON reports.

Concurrent scheduling is not compared. Each workload reports observable
invariants (row sets, join counts, locks, EOF, errno, release) instead.
Never turn absent, errored or not-run tests into passing cases.
"""
import argparse
import json
from pathlib import Path
import sys


def same_facts(expected, actual):
    """JSON observations must retain types, including nested bool/int values."""
    if type(expected) is not type(actual):
        return False
    if isinstance(expected, dict):
        return (expected.keys() == actual.keys()
                and all(same_facts(value, actual[key]) for key, value in expected.items()))
    if isinstance(expected, list):
        return (len(expected) == len(actual)
                and all(same_facts(left, right) for left, right in zip(expected, actual)))
    return expected == actual


def has_binary_identity(artifact):
    return (isinstance(artifact, dict) and isinstance(artifact.get('sha256'), str)
            and bool(artifact['sha256']) and 'interpreter' in artifact
            and (artifact['interpreter'] is None or isinstance(artifact['interpreter'], str)))


def has_observation(case):
    return type(case.get('exit_code')) is int and isinstance(case.get('facts'), dict)


def compare(reference, candidate, *, proven_only=False):
    differences = []
    blocked = []
    matched = []
    refs = reference.get("binaries", {})
    cands = candidate.get("binaries", {})
    if not refs:
        blocked.append({'case': 'binaries', 'reason': 'missing Linux reference ELF inventory'})
    if not any(case.get('status') == 'pass' for case in reference.get('cases', {}).values()):
        blocked.append({'case': 'reference', 'reason': 'no passed Linux reference cases'})
    for name, artifact in refs.items():
        other = cands.get(name)
        if not has_binary_identity(artifact):
            blocked.append({'case': name, 'reason': 'missing Linux reference ELF identity'})
        elif not has_binary_identity(other):
            blocked.append({"case": name, "reason": "missing ELF in candidate report"})
        elif artifact.get("sha256") != other.get("sha256"):
            differences.append({"case": name, "reason": "ELF bytes changed; not a differential test",
                                "expected_sha256": artifact.get("sha256"), "actual_sha256": other.get("sha256")})
        elif artifact.get("interpreter") != other.get("interpreter"):
            differences.append({"case": name, "reason": "loader path changed"})
    for name, baseline in reference.get("cases", {}).items():
        observed = candidate.get("cases", {}).get(name)
        if baseline.get("status") != "pass":
            if not proven_only:
                blocked.append({"case": name, "reason": "Linux reference did not run/pass"})
            continue
        if not has_observation(baseline):
            blocked.append({'case': name, 'reason': 'Linux reference lacks recorded exit code or facts'})
        elif observed is None or observed.get("status") == "not_run":
            blocked.append({"case": name, "reason": "candidate not run"})
        elif observed.get("status") != "pass":
            differences.append({"case": name, "reason": "candidate failed", "observed": observed})
        elif not has_observation(observed):
            differences.append({'case': name, 'reason': 'candidate lacks recorded exit code or facts'})
        elif baseline.get("exit_code") != observed.get("exit_code"):
            differences.append({"case": name, "reason": "exit code differs",
                                "expected": baseline.get("exit_code"), "actual": observed.get("exit_code")})
        elif not same_facts(baseline["facts"], observed["facts"]):
            differences.append({"case": name, "reason": "observable behavior differs",
                                "expected": baseline.get("facts"), "actual": observed.get("facts")})
        else:
            matched.append(name)
    unknown = sorted(set(candidate.get("cases", {})) - set(reference.get("cases", {})))
    for name in unknown:
        blocked.append({"case": name, "reason": "no pinned Linux reference"})
    guest_claim = candidate.get("suite") == "a04-linux-guest-differential"
    guest_evidence = candidate.get("boot_evidence", {})
    boot_verified = bool(guest_claim and candidate.get("guest_execution_verified") is True
                         and guest_evidence.get("a01_kernel_elf_sha256_matches") is True
                         and guest_evidence.get("a04_initramfs_sha256_matches") is True
                         and guest_evidence.get("qemu_exit_code") == 33)
    if guest_claim and not boot_verified:
        blocked.append({"case": "kernel_boot", "reason": "missing valid guest/QEMU boot evidence"})
    verdict = "fail" if differences else "incomplete" if blocked else (
        "partial_match" if proven_only else "match")
    return {"schema": 1, "verdict": verdict, "matched": matched,
            "matched_count": len(matched), "differences": differences,
            "blocked": blocked, "reference_case_count": len(reference.get("cases", {})),
            "candidate_case_count": len(candidate.get("cases", {})),
            "kernel_boot_verified": boot_verified,
            "guest_compatibility_passed": candidate.get("guest_compatibility_passed") is True}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reference", type=Path, required=True)
    ap.add_argument("--candidate", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--proven-only", action="store_true", help="compare only Linux-passed cases, mark partial_match")
    args = ap.parse_args()
    verdict = compare(json.loads(args.reference.read_text()),
                      json.loads(args.candidate.read_text()), proven_only=args.proven_only)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: verdict[k] for k in ("verdict", "matched_count", "reference_case_count",
                                               "candidate_case_count")}))
    return 1 if verdict["verdict"] == "fail" else 2 if verdict["verdict"] == "incomplete" else 0


if __name__ == "__main__":
    sys.exit(main())
