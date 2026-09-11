#!/usr/bin/env python3
"""Validate the closed S11 update/recovery source candidate.

This validator proves source shape and hostile-test coverage only.  It never
claims an installed update, QEMU execution, raw-power interruption, hardware,
signing-key custody, publication, or release authority.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts/s11-update-recovery.v1.json"
SOURCE = ROOT / "platform/update_recovery.py"
TEST = ROOT / "tests/test_s11_update_recovery.py"
DOC = ROOT / "docs/architecture/S11_UPDATE_RECOVERY.md"
WORKFLOW = ROOT / ".github/workflows/s11-update-recovery.yml"
ERRORS: list[str] = []


def fail(message: str) -> None:
    ERRORS.append(message)


def strict_json(path: Path) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    def constant(value: str) -> None:
        raise ValueError(f"non-JSON numeric constant {value!r}")

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=pairs,
            parse_constant=constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        fail(f"cannot decode {path.relative_to(ROOT)} strictly: {error}")
        return {}
    if not isinstance(value, dict):
        fail(f"{path.relative_to(ROOT)} must contain one object")
        return {}
    return value


def exact_keys(value: object, expected: set[str], label: str) -> bool:
    if not isinstance(value, dict):
        fail(f"{label} must be an object")
        return False
    actual = set(value)
    if actual != expected:
        fail(
            f"{label} keys differ: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )
        return False
    return True


def check_contract() -> None:
    value = strict_json(CONTRACT)
    expected_top = {
        "schema",
        "stage",
        "claim_ceiling",
        "manifest",
        "state_machine",
        "durability",
        "fault_model",
        "non_claims",
    }
    if not exact_keys(value, expected_top, "contract"):
        return
    if value.get("schema") != "trillionnium.desktop.s11-update-recovery.v1":
        fail("S11 contract schema identity is invalid")
    if value.get("stage") != "S11":
        fail("S11 contract stage is invalid")
    if value.get("claim_ceiling") != (
        "source_and_host_mechanism_candidate_only_no_installed_update_"
        "no_hardware_no_signing_no_release"
    ):
        fail("S11 contract claim ceiling widened or changed")

    manifest = value.get("manifest")
    manifest_keys = {
        "schema",
        "repository",
        "exact_fields",
        "whole_image_digest_required",
        "whole_image_length_required",
        "inactive_slot_required",
        "source_identity_required",
        "downgrade_refused",
        "rollback_floor_enforced",
        "expiry_enforced",
    }
    if exact_keys(manifest, manifest_keys, "manifest"):
        assert isinstance(manifest, dict)
        if manifest.get("schema") != "trillionnium.desktop.update-manifest.v1":
            fail("update manifest schema changed")
        if manifest.get("repository") != ROOT.parent.name + "/trillionnium-os-desktop":
            # Keep the repository identity explicit; this branch is not portable authority.
            if manifest.get("repository") != "TrillionniumFoundation/trillionnium-os-desktop":
                fail("update manifest repository identity changed")
        expected_fields = {
            "schema",
            "repository",
            "source_version",
            "source_image_sha256",
            "target_version",
            "target_slot",
            "target_image_sha256",
            "target_image_bytes",
            "rollback_floor",
            "expires_unix",
            "signer_id",
            "signature_sha256",
        }
        fields = manifest.get("exact_fields")
        if not isinstance(fields, list) or set(fields) != expected_fields or len(fields) != len(expected_fields):
            fail("update manifest field inventory is not exact")
        for key in (
            "whole_image_digest_required",
            "whole_image_length_required",
            "inactive_slot_required",
            "source_identity_required",
            "downgrade_refused",
            "rollback_floor_enforced",
            "expiry_enforced",
        ):
            if manifest.get(key) is not True:
                fail(f"manifest control {key} is not true")

    state = value.get("state_machine")
    state_keys = {
        "states",
        "commit_requires_health_receipt",
        "minimum_stable_health_seconds",
        "maximum_boot_failures",
        "automatic_effect_replay",
        "reconciliation_required_after_possible_dispatch",
    }
    if exact_keys(state, state_keys, "state_machine"):
        assert isinstance(state, dict)
        expected_states = [
            "idle",
            "verified",
            "staged",
            "boot_pending",
            "health_pending",
            "committed",
            "rollback_pending",
            "recovery_required",
        ]
        if state.get("states") != expected_states:
            fail("S11 state inventory or order changed")
        if state.get("commit_requires_health_receipt") is not True:
            fail("commit no longer requires a health receipt")
        if state.get("minimum_stable_health_seconds") != 60:
            fail("stable-health duration changed")
        if state.get("maximum_boot_failures") != 2:
            fail("boot failure bound changed")
        if state.get("automatic_effect_replay") is not False:
            fail("automatic effect replay was enabled")
        if state.get("reconciliation_required_after_possible_dispatch") is not True:
            fail("possible dispatch no longer requires reconciliation")

    durability = value.get("durability")
    durability_keys = {
        "state_directory_mode",
        "state_file_mode",
        "path_walk",
        "publication",
        "exclusive_coordinator_lease",
        "post_replace_failure",
    }
    if exact_keys(durability, durability_keys, "durability"):
        assert isinstance(durability, dict)
        if durability.get("state_directory_mode") != "0700":
            fail("state directory is not private")
        if durability.get("state_file_mode") != "0600":
            fail("state file is not private")
        if durability.get("path_walk") != "descriptor_pinned_no_follow":
            fail("state path walk is not descriptor pinned and no-follow")
        if durability.get("publication") != [
            "exclusive_temp_create",
            "complete_write",
            "file_fsync",
            "atomic_replace",
            "directory_fsync",
        ]:
            fail("state publication order changed")
        if durability.get("exclusive_coordinator_lease") is not True:
            fail("exclusive coordinator lease was removed")
        if durability.get("post_replace_failure") != (
            "publication_indeterminate_reconcile_before_retry"
        ):
            fail("post-replace uncertainty is no longer fail closed")

    fault = value.get("fault_model")
    fault_keys = {
        "cutpoints",
        "missing_or_mismatched_slot",
        "torn_or_malformed_state",
    }
    if exact_keys(fault, fault_keys, "fault_model"):
        assert isinstance(fault, dict)
        expected = {
            "before_temp_create",
            "after_temp_create",
            "after_complete_write",
            "after_file_fsync",
            "after_atomic_replace",
            "after_directory_fsync",
            "during_first_boot_health",
            "during_rollback",
        }
        observed = fault.get("cutpoints")
        if not isinstance(observed, list) or set(observed) != expected or len(observed) != len(expected):
            fail("fault cutpoint inventory is incomplete or duplicated")
        for key in ("missing_or_mismatched_slot", "torn_or_malformed_state"):
            if fault.get(key) != "recovery_required":
                fail(f"fault handling {key} is not recovery_required")

    non_claims = value.get("non_claims")
    expected_nonclaims = {
        "installed_qemu_update_executed",
        "raw_power_loss_executed",
        "physical_hardware_qualified",
        "production_signature_verified",
        "release_published",
    }
    if exact_keys(non_claims, expected_nonclaims, "non_claims"):
        assert isinstance(non_claims, dict)
        if any(item is not False for item in non_claims.values()):
            fail("an S11 non-claim was promoted by source")


def check_source() -> None:
    try:
        text = SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(SOURCE))
    except (OSError, UnicodeError, SyntaxError) as error:
        fail(f"cannot parse S11 source: {error}")
        return

    classes = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
    required_classes = {
        "UpdateManifest",
        "ManifestTicket",
        "HealthPermit",
        "JournalReconciliation",
        "UpdateCoordinator",
        "AtomicStateStore",
        "PublicationIndeterminate",
        "RecoveryRequired",
    }
    missing = sorted(required_classes - classes)
    if missing:
        fail(f"S11 source classes are missing: {missing}")

    functions = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    required_functions = {
        "parse",
        "verify_manifest",
        "stage_image",
        "arm_first_boot",
        "record_booted_image",
        "record_health",
        "commit",
        "record_boot_failure",
        "rollback",
        "mark_possible_dispatch",
        "verify_journal_reconciliation",
        "reconcile_possible_dispatch",
        "reconcile_startup",
        "acquire",
        "write",
        "read",
    }
    missing_functions = sorted(required_functions - functions)
    if missing_functions:
        fail(f"S11 source functions are missing: {missing_functions}")

    forbidden_imports = {"requests", "httpx", "aiohttp", "socket", "subprocess", "urllib"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".", 1)[0] in forbidden_imports:
                    fail(f"S11 source imports forbidden external-I/O module {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".", 1)[0] in forbidden_imports:
                fail(f"S11 source imports forbidden external-I/O module {node.module}")
        elif isinstance(node, ast.Call):
            name = None
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                name = f"{node.func.value.id}.{node.func.attr}"
            if name in {"eval", "exec", "compile", "os.system", "os.popen"}:
                fail(f"S11 source contains forbidden call {name}")

    markers = (
        "parse_constant=constant",
        "source_image_sha256",
        "target_image_bytes",
        "target_slot == active_slot",
        "MIN_STABLE_HEALTH_SECONDS",
        "MAX_BOOT_FAILURES",
        "_effect_reconciliation_required",
        "PublicationIndeterminate",
        "os.O_NOFOLLOW",
        "fcntl.LOCK_EX | fcntl.LOCK_NB",
        "os.O_EXCL",
        "os.fsync(temp_fd)",
        "os.replace(",
        "os.fsync(root_fd)",
    )
    for marker in markers:
        if marker not in text:
            fail(f"required S11 implementation marker absent: {marker}")


def check_docs_tests_workflow() -> None:
    for path in (CONTRACT, SOURCE, TEST, DOC, WORKFLOW):
        if path.is_symlink() or not path.is_file():
            fail(f"required S11 path missing or symlinked: {path.relative_to(ROOT)}")

    if TEST.is_file():
        text = TEST.read_text(encoding="utf-8")
        for name in (
            "test_strict_manifest_and_source_binding",
            "test_whole_image_substitution_is_refused",
            "test_health_gated_commit_and_exact_boot_identity",
            "test_boot_failures_open_rollback_and_require_exact_source",
            "test_possible_dispatch_never_replays_automatically",
            "test_startup_reconciliation_refuses_missing_or_substituted_slots",
            "test_atomic_state_store_is_private_locked_and_durable",
            "test_state_store_refuses_symlink_root_and_post_replace_uncertainty",
            "test_pre_replace_fault_leaves_no_promoted_state",
        ):
            if f"def {name}(" not in text:
                fail(f"S11 hostile corpus is missing {name}")

    if DOC.is_file():
        text = DOC.read_text(encoding="utf-8")
        expected_headings = (
            "## Scope and claim ceiling",
            "## Threat and authority boundary",
            "## Manifest admission",
            "## Durable A/B state",
            "## Failure and replay semantics",
            "## Installed-image qualification",
            "## Evidence invalidation",
            "## Non-claims",
        )
        positions = [text.find(heading) for heading in expected_headings]
        if any(position < 0 for position in positions) or positions != sorted(positions):
            fail("S11 document headings are missing or out of order")
        for phrase in (
            "whole-image digest",
            "inactive slot",
            "durable reconciliation",
            "no automatic replay",
            "raw power loss",
            "installed QEMU",
        ):
            if phrase.lower() not in text.lower():
                fail(f"S11 document omits required phrase {phrase!r}")

    if WORKFLOW.is_file():
        text = WORKFLOW.read_text(encoding="utf-8")
        if "contents: write" in text or "pull-requests: write" in text:
            fail("S11 workflow is not read-only")
        for token in (
            "exact-head:",
            "prospective-merge:",
            "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
            "python3 -m py_compile platform/update_recovery.py",
            "python3 tools/validate_s11_update_recovery.py",
            "python3 -m unittest tests.test_s11_update_recovery -v",
            "python3 tools/validate_repository.py",
            "python3 tools/validate_project_truth.py",
            "git diff --check",
        ):
            if token not in text:
                fail(f"S11 workflow omits executable gate token: {token}")


def main() -> int:
    check_contract()
    check_source()
    check_docs_tests_workflow()
    for error in ERRORS:
        print(f"S11-UPDATE-RECOVERY: {error}", file=sys.stderr)
    if ERRORS:
        print(f"S11 validation failed ({len(ERRORS)} errors)", file=sys.stderr)
        return 1
    print("S11 update/recovery source validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
