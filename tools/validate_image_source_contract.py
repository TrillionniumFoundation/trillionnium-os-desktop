#!/usr/bin/env python3
"""Audit current image-workflow references and invalidation scope, not image success."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ".github/workflows/s10-production-debian-qemu.yml"
REQUIRED_INPUTS = {"Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "apps/**", "crates/**",
                   "contracts/**", "runtime/**", "manifests/**", ".github/workflows/**",
                   "packaging/debian/**", "tests/d1/**", "tests/qemu/**", "tests/fixtures/**", "tools/**"}
CONSUMERS = (
    "tools/finalize_d1_evidence.py", "tools/finalize_d2i_evidence.py",
    "tools/run_d2i_integrated_image.sh", "tests/d1/test_d1_evidence_soundness.py",
    "tests/d1/test_d1_tool_binding.py", "tests/d1/test_d2i_contract.py",
)
OBSOLETE = (".github/workflows/d1-final-qualification.yml", ".github/workflows/d2i-integrated-image.yml")


def validate(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    try:
        path = root / WORKFLOW
        if path.is_symlink():
            return ["image workflow must not be a symlink"]
        workflow = path.read_text(encoding="utf-8")
        trigger = workflow.split("\npermissions:\n", 1)[0]
        if "paths:" in trigger or "paths-ignore:" in trigger:
            errors.append("image source gate cannot miss changed transitive inputs through path filters")
        for marker in ("pull_request:", "push:", "branches: [main]", "workflow_dispatch:"):
            if marker not in trigger:
                errors.append(f"missing image workflow trigger: {marker}")
        if "permissions:\n  contents: read" not in workflow or "contents: write" in workflow:
            errors.append("image workflow is not read-only")
        for forbidden in ("S10_BASE_REF", "git push", "gh workflow run"):
            if forbidden in workflow:
                errors.append(f"obsolete parent or mutation in image workflow: {forbidden}")
        for required in ("needs: source-contracts", "tools/image_workflow_identity.py",
                         "tools/validate_image_source_contract.py",
                         "python3 -m unittest discover -s tests/d1 -p 'test_*.py' -v",
                         "EXPECTED_BASE_REF:", "EXPECTED_MERGE:", "PR_NUMBER:",
                         "tools/run_d2i_integrated_image.sh boot-image",
                         "tools/run_d2i_integrated_image.sh finalize-evidence"):
            if required not in workflow:
                errors.append(f"required image execution or source boundary absent: {required}")
        for relative in CONSUMERS:
            text = (root / relative).read_text(encoding="utf-8")
            if WORKFLOW not in text or any(old in text for old in OBSOLETE):
                errors.append(f"stale image-workflow binding: {relative}")
        registry = json.loads((root / "manifests/gates.v1.json").read_text(encoding="utf-8"))
        for identifier in ("D1-01", "D2I-01"):
            gates = [gate for gate in registry["gates"] if gate["id"] == identifier]
            if len(gates) != 1:
                errors.append(f"missing or duplicate image gate: {identifier}")
                continue
            gate = gates[0]
            if not REQUIRED_INPUTS <= set(gate["invalidation_paths"]):
                errors.append(f"image gate omits transitive input domains: {identifier}")
            if any(old in json.dumps(gate) for old in OBSOLETE):
                errors.append(f"image gate references a retired workflow: {identifier}")
        finalizer = (root / "tools/finalize_d1_evidence.py").read_text(encoding="utf-8")
        if '"qualification_feature": "fixture"' not in finalizer:
            errors.append("D1 receipt target metadata differs from the actual Cargo example")
        combined = (root / "tools/finalize_d2i_evidence.py").read_text(encoding="utf-8")
        if 'assert d1_receipt["status"] == "PASS_D1_FINAL_QUALIFICATION"' in combined:
            errors.append("D2I expects a status never emitted by the D1 v3 producer")
        if "validate_embedded_d1_receipt(d1_receipt," not in combined:
            errors.append("D2I does not validate the embedded current-object D1 receipt")
    except (OSError, ValueError, TypeError, KeyError) as error:
        errors.append(f"image source contract input invalid: {type(error).__name__}: {error}")
    return errors


def main() -> int:
    errors = validate()
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        return 1
    print("image source contract passed; no installed-image or product-path claim")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
