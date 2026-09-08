"""Repository invariants that do not interpret or render status documents.

The integrated-status contract lives exclusively in ``structured_status_model.py``
and ``structured_status.py``. This module is an import-only library: it has no
CLI entry point and contains no competing status projection implementation.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ACTION_REF = re.compile(r"^\s*uses:\s*([^#\s]+)\s*$")
IMMUTABLE_ACTION = re.compile(r"^[^@]+@[0-9a-f]{40}$")
PLAN_REVISION = "2026-08-29-d6"
PLAN_PATH = "docs/DESKTOP_PLAN-2026-08-29-d6.md"
INTEGRATED_STAGE = "D0R_D0C06_D0A01_COMPILE_VALIDATED"


class _Validator:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.errors: list[str] = []

    def fail(self, message: str) -> None:
        self.errors.append(message)

    @staticmethod
    def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    def load_json(self, relative: str) -> dict[str, Any]:
        path = self.root / relative
        try:
            value = json.loads(
                path.read_text(encoding="utf-8"),
                object_pairs_hook=self._reject_duplicate_keys,
            )
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            self.fail(f"invalid JSON {relative}: {error}")
            return {}
        if not isinstance(value, dict):
            self.fail(f"expected object in {relative}")
            return {}
        return value

    def require_text(self, relative: str, needles: list[str]) -> str:
        path = self.root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            self.fail(f"cannot read {relative}: {error}")
            return ""
        for needle in needles:
            if needle not in text:
                self.fail(f"{relative} is missing canonical marker {needle!r}")
        return text

    def check_truth_alignment(self) -> None:
        project = self.load_json("manifests/project-state.v1.json")
        gates = self.load_json("manifests/gates.v1.json")
        docs = self.load_json("docs/MANIFEST.json")
        repository = self.load_json("manifests/repository-state.json")

        expected = {
            "active_plan": PLAN_PATH,
            "active_plan_revision": PLAN_REVISION,
            "integrated_implementation_stage": INTEGRATED_STAGE,
        }
        for key, value in expected.items():
            if project.get(key) != value:
                self.fail(f"project-state {key} must be {value!r}")

        if docs.get("active_plan") != Path(PLAN_PATH).name:
            self.fail("docs manifest active_plan disagrees with project-state")
        if docs.get("active_plan_revision") != PLAN_REVISION:
            self.fail("docs manifest revision disagrees with project-state")
        if docs.get("implementation_stage") != INTEGRATED_STAGE:
            self.fail("docs manifest implementation_stage disagrees with project-state")
        if docs.get("project_state") != "../manifests/project-state.v1.json":
            self.fail("docs manifest does not point to project-state")
        if docs.get("gate_registry") != "../manifests/gates.v1.json":
            self.fail("docs manifest does not point to gate registry")

        if repository.get("active_plan") != PLAN_PATH:
            self.fail("repository-state active_plan disagrees with project-state")
        if repository.get("active_plan_revision") != PLAN_REVISION:
            self.fail("repository-state revision disagrees with project-state")
        if repository.get("implementation_stage") != INTEGRATED_STAGE:
            self.fail("repository-state implementation_stage disagrees with project-state")
        if repository.get("project_state") != "manifests/project-state.v1.json":
            self.fail("repository-state does not point to project-state")
        if repository.get("gate_registry") != "manifests/gates.v1.json":
            self.fail("repository-state does not point to gate registry")

        completed = project.get("integrated_completed_work_packages")
        if not isinstance(completed, list) or any(
            not isinstance(item, str) for item in completed
        ):
            self.fail("project-state completed package set is invalid")
            completed = []
        if len(completed) != len(set(completed)):
            self.fail("project-state completed package set has duplicates")
        if set(repository.get("completed_work_packages", [])) != set(completed):
            self.fail("repository-state completed package set disagrees with project-state")

        if gates.get("plan_revision") != PLAN_REVISION:
            self.fail("gate registry revision disagrees with project-state")
        vocabulary = set(gates.get("status_vocabulary", []))
        gate_list = gates.get("gates", [])
        if not isinstance(gate_list, list):
            self.fail("gate registry gates is not a list")
            gate_list = []
        gate_ids: list[str] = []
        for entry in gate_list:
            if not isinstance(entry, dict):
                self.fail("gate registry contains a non-object gate")
                continue
            gate_id = entry.get("id")
            status = entry.get("status")
            if not isinstance(gate_id, str):
                self.fail("gate registry entry has no string id")
                continue
            gate_ids.append(gate_id)
            if status not in vocabulary:
                self.fail(f"gate {gate_id} has unknown status {status!r}")
            for key in (
                "evidence_tier",
                "prerequisites",
                "invalidation_paths",
                "claim_ceiling",
                "review_class",
            ):
                if key not in entry:
                    self.fail(f"gate {gate_id} is missing {key}")
        if len(gate_ids) != len(set(gate_ids)):
            self.fail("gate registry contains duplicate ids")

        gate_id_set = set(gate_ids)
        for package in completed:
            if package not in gate_id_set:
                self.fail(f"completed package {package} is absent from gate registry")
        gate_status_by_id = {
            entry["id"]: entry.get("status")
            for entry in gate_list
            if isinstance(entry, dict) and isinstance(entry.get("id"), str)
        }
        for package in completed:
            if gate_status_by_id.get(package) != "INTEGRATED_AND_EXACT_MAIN_VALIDATED":
                self.fail(
                    f"completed package {package} is not "
                    "integrated-and-main-validated in gate registry"
                )

        candidates = project.get("source_candidate_work_packages", [])
        if not isinstance(candidates, list):
            self.fail("project-state source candidates is not a list")
            candidates = []
        candidate_view: list[dict[str, Any]] = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                self.fail("project-state contains a non-object source candidate")
                continue
            package = candidate.get("id")
            status = candidate.get("status")
            if package not in gate_id_set:
                self.fail(f"candidate package {package!r} is absent from gate registry")
            if status not in vocabulary:
                self.fail(f"candidate package {package!r} has unknown status {status!r}")
            if gate_status_by_id.get(package) != status:
                self.fail(
                    f"candidate package {package!r} status disagrees with gate registry"
                )
            if package in completed:
                self.fail(f"candidate package {package} is also listed as integrated complete")
            candidate_view.append(
                {
                    "id": package,
                    "branch": candidate.get("branch"),
                    "pr": candidate.get("pr"),
                    "status": status,
                }
            )

        if repository.get("source_candidate_work_packages", []) != candidates:
            self.fail("repository-state source candidates disagree with project-state")
        if docs.get("active_candidates", []) != candidate_view:
            self.fail("docs manifest active candidates disagree with project-state")

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
            self.fail(f"project-state is missing required non-claims: {missing}")
        if set(repository.get("not_claimed", [])) != nonclaims:
            self.fail("repository-state non-claims disagree with project-state")

        policy = project.get("evidence_binding_policy", {})
        if (
            not isinstance(policy, dict)
            or not policy
            or any(value is not True for value in policy.values())
        ):
            self.fail("project-state evidence binding policy is not fully fail-closed")

        self.require_text(
            PLAN_PATH,
            [PLAN_REVISION, INTEGRATED_STAGE, "D1", "D0A-02", "D9"],
        )
        self.require_text(
            "docs/DESKTOP_PLAN.md",
            [Path(PLAN_PATH).name, PLAN_REVISION, INTEGRATED_STAGE],
        )
        self.require_text(
            "apps/hepta-browserd/src/lib.rs",
            [PLAN_REVISION, INTEGRATED_STAGE],
        )

    def check_upstream_boundary(self) -> None:
        boundary = self.load_json("manifests/product-boundary.json")
        review = self.load_json("manifests/upstream-reference-review.v1.json")
        mobile = boundary.get("mobile_reference", {})
        if not isinstance(mobile, dict):
            self.fail("product boundary mobile_reference is invalid")
            return
        if mobile.get("repository") != "TrillionniumFoundation/trillionnium-os":
            self.fail("product boundary points to the wrong sibling repository")
        if mobile.get("commit") != review.get("reviewed_company_main_sha"):
            self.fail("product boundary sibling commit disagrees with upstream review")
        if (
            mobile.get("relationship")
            != "company_sibling_reference_not_build_dependency"
        ):
            self.fail("product boundary weakens the sibling/build boundary")
        if review.get("mobile_authority_imported") is not False:
            self.fail("upstream review imports mobile authority")
        rejected = set(review.get("explicitly_rejected_default_authorities", []))
        for authority in (
            "adb",
            "root_linux",
            "direct_shell",
            "owner_open_root_execution",
        ):
            if authority not in rejected:
                self.fail(f"upstream review does not reject {authority}")

    def check_workflow_action_pins(self) -> None:
        pins = self.load_json("manifests/ci-action-pins.v1.json").get("actions", {})
        if not isinstance(pins, dict):
            self.fail("CI action pin manifest is invalid")
            pins = {}
        workflows = sorted((self.root / ".github/workflows").glob("*.yml"))
        if not workflows:
            self.fail("no GitHub workflows found")
            return
        for path in workflows:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeError) as error:
                self.fail(f"cannot read {path.relative_to(self.root)}: {error}")
                continue
            for line_number, line in enumerate(lines, 1):
                match = ACTION_REF.match(line)
                if not match:
                    continue
                action = match.group(1).strip("\"'")
                if action.startswith("./"):
                    continue
                if not IMMUTABLE_ACTION.fullmatch(action):
                    self.fail(
                        f"{path.relative_to(self.root)}:{line_number} uses mutable "
                        f"action ref {action!r}"
                    )
                    continue
                name, sha = action.rsplit("@", 1)
                expected = pins.get(name)
                if expected != sha:
                    self.fail(
                        f"{path.relative_to(self.root)}:{line_number} action {name!r} "
                        "is not bound to the reviewed pin manifest"
                    )

    def check_command_baseline(self) -> None:
        makefile = self.require_text(
            "Makefile",
            [
                "python3 tools/validate_project_truth.py",
                "python3 -m unittest discover -s tests "
                "-p 'test_project_truth_status_documents.py'",
                "cargo check --workspace --all-targets --locked",
                "cargo clippy --workspace --all-targets --locked -- -D warnings",
                "cargo test --workspace --all-targets --locked",
                "cargo run --locked -p hepta-browserd -- --self-check",
            ],
        )
        ci = self.require_text(
            ".github/workflows/ci.yml",
            [
                "runs-on: ubuntu-24.04",
                "python3 tools/validate_project_truth.py",
                "python3 -m unittest discover -s tests "
                "-p 'test_project_truth_status_documents.py'",
                "cargo check --workspace --all-targets --locked",
                "cargo clippy --workspace --all-targets --locked -- -D warnings",
                "cargo test --workspace --all-targets --locked",
                "cargo run --locked -p hepta-browserd -- --self-check",
            ],
        )
        for text, label in ((makefile, "Makefile"), (ci, "CI")):
            if "cargo test --workspace\n" in text:
                self.fail(f"{label} contains an unlocked/non-all-targets workspace test")

    def run(self) -> list[str]:
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
            path = self.root / relative
            if path.is_symlink() or not path.is_file():
                self.fail(f"required d6 path is missing or not regular: {relative}")

        self.check_truth_alignment()
        self.check_upstream_boundary()
        self.check_workflow_action_pins()
        self.check_command_baseline()
        return self.errors


def validate_non_status_repository(root: Path = ROOT) -> list[str]:
    """Return every non-status repository invariant failure."""

    return _Validator(root).run()
