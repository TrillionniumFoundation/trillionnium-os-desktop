#!/usr/bin/env python3
"""Validate canonical project truth, gate identities, and immutable CI inputs."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []
ACTION_REF = re.compile(r"^\s*uses:\s*([^#\s]+)\s*$")
IMMUTABLE_ACTION = re.compile(r"^[^@]+@[0-9a-f]{40}$")
PLAN_REVISION = "2026-08-29-d6"
PLAN_PATH = "docs/DESKTOP_PLAN-2026-08-29-d6.md"
INTEGRATED_STAGE = "D0R_D0C06_D0A01_COMPILE_VALIDATED"


def fail(message: str) -> None:
    ERRORS.append(message)


def load_json(relative: str) -> dict[str, Any]:
    path = ROOT / relative
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"invalid JSON {relative}: {error}")
        return {}
    if not isinstance(value, dict):
        fail(f"expected object in {relative}")
        return {}
    return value


def require_text(relative: str, needles: list[str]) -> str:
    path = ROOT / relative
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        fail(f"cannot read {relative}: {error}")
        return ""
    for needle in needles:
        if needle not in text:
            fail(f"{relative} is missing canonical marker {needle!r}")
    return text


def check_truth_alignment() -> None:
    project = load_json("manifests/project-state.v1.json")
    gates = load_json("manifests/gates.v1.json")
    docs = load_json("docs/MANIFEST.json")
    repository = load_json("manifests/repository-state.json")

    expected = {
        "active_plan": PLAN_PATH,
        "active_plan_revision": PLAN_REVISION,
        "integrated_implementation_stage": INTEGRATED_STAGE,
    }
    for key, value in expected.items():
        if project.get(key) != value:
            fail(f"project-state {key} must be {value!r}")

    if docs.get("active_plan") != Path(PLAN_PATH).name:
        fail("docs manifest active_plan disagrees with project-state")
    if docs.get("active_plan_revision") != PLAN_REVISION:
        fail("docs manifest revision disagrees with project-state")
    if docs.get("implementation_stage") != INTEGRATED_STAGE:
        fail("docs manifest implementation_stage disagrees with project-state")
    if docs.get("project_state") != "../manifests/project-state.v1.json":
        fail("docs manifest does not point to project-state")
    if docs.get("gate_registry") != "../manifests/gates.v1.json":
        fail("docs manifest does not point to gate registry")

    if repository.get("active_plan") != PLAN_PATH:
        fail("repository-state active_plan disagrees with project-state")
    if repository.get("active_plan_revision") != PLAN_REVISION:
        fail("repository-state revision disagrees with project-state")
    if repository.get("implementation_stage") != INTEGRATED_STAGE:
        fail("repository-state implementation_stage disagrees with project-state")
    if repository.get("project_state") != "manifests/project-state.v1.json":
        fail("repository-state does not point to project-state")
    if repository.get("gate_registry") != "manifests/gates.v1.json":
        fail("repository-state does not point to gate registry")

    completed = project.get("integrated_completed_work_packages")
    if not isinstance(completed, list) or any(not isinstance(item, str) for item in completed):
        fail("project-state completed package set is invalid")
        completed = []
    if len(completed) != len(set(completed)):
        fail("project-state completed package set has duplicates")
    if set(repository.get("completed_work_packages", [])) != set(completed):
        fail("repository-state completed package set disagrees with project-state")

    if gates.get("plan_revision") != PLAN_REVISION:
        fail("gate registry revision disagrees with project-state")
    vocabulary = set(gates.get("status_vocabulary", []))
    gate_list = gates.get("gates", [])
    if not isinstance(gate_list, list):
        fail("gate registry gates is not a list")
        gate_list = []
    gate_ids: list[str] = []
    for entry in gate_list:
        if not isinstance(entry, dict):
            fail("gate registry contains a non-object gate")
            continue
        gate_id = entry.get("id")
        status = entry.get("status")
        if not isinstance(gate_id, str):
            fail("gate registry entry has no string id")
            continue
        gate_ids.append(gate_id)
        if status not in vocabulary:
            fail(f"gate {gate_id} has unknown status {status!r}")
        for key in (
            "evidence_tier",
            "prerequisites",
            "invalidation_paths",
            "claim_ceiling",
            "review_class",
        ):
            if key not in entry:
                fail(f"gate {gate_id} is missing {key}")
    if len(gate_ids) != len(set(gate_ids)):
        fail("gate registry contains duplicate ids")

    gate_id_set = set(gate_ids)
    for package in completed:
        if package not in gate_id_set:
            fail(f"completed package {package} is absent from gate registry")
    gate_status_by_id = {
        entry["id"]: entry.get("status")
        for entry in gate_list
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    }
    for package in completed:
        if gate_status_by_id.get(package) != "INTEGRATED_AND_EXACT_MAIN_VALIDATED":
            fail(f"completed package {package} is not integrated-and-main-validated in gate registry")

    candidates = project.get("source_candidate_work_packages", [])
    if not isinstance(candidates, list):
        fail("project-state source candidates is not a list")
        candidates = []
    candidate_view: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            fail("project-state contains a non-object source candidate")
            continue
        package = candidate.get("id")
        status = candidate.get("status")
        if package not in gate_id_set:
            fail(f"candidate package {package!r} is absent from gate registry")
        if status not in vocabulary:
            fail(f"candidate package {package!r} has unknown status {status!r}")
        if gate_status_by_id.get(package) != status:
            fail(f"candidate package {package!r} status disagrees with gate registry")
        if package in completed:
            fail(f"candidate package {package} is also listed as integrated complete")
        candidate_view.append({
            "id": package,
            "branch": candidate.get("branch"),
            "pr": candidate.get("pr"),
            "status": status,
        })

    repository_candidates = repository.get("source_candidate_work_packages", [])
    if repository_candidates != candidates:
        fail("repository-state source candidates disagree with project-state")
    docs_candidates = docs.get("active_candidates", [])
    if docs_candidates != candidate_view:
        fail("docs manifest active candidates disagree with project-state")

    required_nonclaims = {
        "headed_servo_integrated",
        "debian_image_built",
        "qemu_pid1_wayland_boot",
        "browser_actor_dispatch",
        "external_navigation_or_effects",
        "production_release",
    }
    nonclaims = set(project.get("not_claimed", []))
    missing = sorted(required_nonclaims - nonclaims)
    if missing:
        fail(f"project-state is missing required non-claims: {missing}")
    if set(repository.get("not_claimed", [])) != nonclaims:
        fail("repository-state non-claims disagree with project-state")

    policy = project.get("evidence_binding_policy", {})
    if not isinstance(policy, dict) or not policy or any(value is not True for value in policy.values()):
        fail("project-state evidence binding policy is not fully fail-closed")

    require_text(PLAN_PATH, [PLAN_REVISION, INTEGRATED_STAGE, "D1", "D0A-02", "D9"])
    require_text("docs/DESKTOP_PLAN.md", [Path(PLAN_PATH).name, PLAN_REVISION, INTEGRATED_STAGE])
    require_text("docs/CURRENT_STATE.md", [PLAN_REVISION, INTEGRATED_STAGE, "PR #23", "PR #27"])
    require_text("README.md", [PLAN_REVISION, INTEGRATED_STAGE, "project-state.v1.json"])
    require_text("apps/hepta-browserd/src/lib.rs", [PLAN_REVISION, INTEGRATED_STAGE])


def check_upstream_boundary() -> None:
    boundary = load_json("manifests/product-boundary.json")
    review = load_json("manifests/upstream-reference-review.v1.json")
    mobile = boundary.get("mobile_reference", {})
    if not isinstance(mobile, dict):
        fail("product boundary mobile_reference is invalid")
        return
    if mobile.get("repository") != "TrillionniumFoundation/trillionnium-os":
        fail("product boundary points to the wrong sibling repository")
    if mobile.get("commit") != review.get("reviewed_company_main_sha"):
        fail("product boundary sibling commit disagrees with upstream review")
    if mobile.get("relationship") != "company_sibling_reference_not_build_dependency":
        fail("product boundary weakens the sibling/build boundary")
    if review.get("mobile_authority_imported") is not False:
        fail("upstream review imports mobile authority")
    rejected = set(review.get("explicitly_rejected_default_authorities", []))
    for authority in ("adb", "root_linux", "direct_shell", "owner_open_root_execution"):
        if authority not in rejected:
            fail(f"upstream review does not reject {authority}")


def check_workflow_action_pins() -> None:
    pins = load_json("manifests/ci-action-pins.v1.json").get("actions", {})
    if not isinstance(pins, dict):
        fail("CI action pin manifest is invalid")
        pins = {}
    workflows = sorted((ROOT / ".github/workflows").glob("*.yml"))
    if not workflows:
        fail("no GitHub workflows found")
        return
    for path in workflows:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = ACTION_REF.match(line)
            if not match:
                continue
            action = match.group(1).strip("\"'")
            if action.startswith("./"):
                continue
            if not IMMUTABLE_ACTION.fullmatch(action):
                fail(
                    f"{path.relative_to(ROOT)}:{line_number} uses mutable action ref {action!r}"
                )
                continue
            name, sha = action.rsplit("@", 1)
            expected = pins.get(name)
            if expected != sha:
                fail(
                    f"{path.relative_to(ROOT)}:{line_number} action {name!r} "
                    f"is not bound to the reviewed pin manifest"
                )


def check_command_baseline() -> None:
    makefile = require_text(
        "Makefile",
        [
            "python3 tools/validate_project_truth.py",
            "cargo check --workspace --all-targets --locked",
            "cargo clippy --workspace --all-targets --locked -- -D warnings",
            "cargo test --workspace --all-targets --locked",
            "cargo run --locked -p hepta-browserd -- --self-check",
        ],
    )
    ci = require_text(
        ".github/workflows/ci.yml",
        [
            "runs-on: ubuntu-24.04",
            "python3 tools/validate_project_truth.py",
            "cargo check --workspace --all-targets --locked",
            "cargo clippy --workspace --all-targets --locked -- -D warnings",
            "cargo test --workspace --all-targets --locked",
            "cargo run --locked -p hepta-browserd -- --self-check",
        ],
    )
    for text, label in ((makefile, "Makefile"), (ci, "CI")):
        if "cargo test --workspace\n" in text:
            fail(f"{label} contains an unlocked/non-all-targets workspace test")


def main() -> int:
    required = [
        "manifests/project-state.v1.json",
        "manifests/gates.v1.json",
        "manifests/upstream-reference-review.v1.json",
        "contracts/project-state.v1.schema.json",
        "contracts/gate-evidence-envelope.v1.schema.json",
        "manifests/ci-action-pins.v1.json",
        PLAN_PATH,
        "docs/plan/PROJECT_TRUTH_AND_EVIDENCE.md",
        "docs/plan/GATE_CONTRACTS_AND_INVALIDATION.md",
        "docs/architecture/RUNTIME_TOPOLOGY_AND_FAILURE_MODEL.md",
        "docs/security/THREAT_MODEL_V2.md",
        "docs/security/SECURITY_CONTROL_MATRIX.md",
        "docs/release/RELEASE_SECURITY_AND_QUALIFICATION.md",
    ]
    for relative in required:
        if not (ROOT / relative).is_file():
            fail(f"required d6 path is missing: {relative}")

    check_truth_alignment()
    check_upstream_boundary()
    check_workflow_action_pins()
    check_command_baseline()

    if ERRORS:
        for error in ERRORS:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"project truth validation failed with {len(ERRORS)} error(s)", file=sys.stderr)
        return 1
    print("project truth validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
