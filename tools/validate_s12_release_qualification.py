#!/usr/bin/env python3
"""Validate the closed S12 release-qualification source boundary."""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts/s12-release-qualification.v1.json"
VERIFIER = ROOT / "tools/verify_s12_release_qualification.py"
TEST = ROOT / "tests/test_s12_release_qualification.py"
DOC = ROOT / "docs/architecture/S12_RELEASE_QUALIFICATION.md"
WORKFLOW = ROOT / ".github/workflows/s12-release-qualification.yml"
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
        raise ValueError(f"non-JSON constant {value!r}")

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
    top = {
        "schema",
        "stage",
        "claim_ceiling",
        "evidence_packet",
        "source_and_image",
        "independent_rebuild",
        "fixed_hardware",
        "endurance",
        "raw_power_loss",
        "key_custody",
        "role_separation",
        "publication",
        "verifier_output",
        "non_claims",
    }
    if not exact_keys(value, top, "S12 contract"):
        return
    if value.get("schema") != "trillionnium.desktop.s12-release-qualification.v1":
        fail("S12 contract schema identity is invalid")
    if value.get("stage") != "S12":
        fail("S12 contract stage is invalid")
    if value.get("claim_ceiling") != (
        "source_verifier_only_no_external_fact_creation_no_signing_no_publication"
    ):
        fail("S12 claim ceiling widened or changed")

    packet = value.get("evidence_packet")
    packet_keys = {
        "schema",
        "strict_json",
        "detached_signature_required",
        "external_public_key_digest_required",
        "external_attestor_identity_required",
        "current_main_binding_required",
        "maximum_packet_age_seconds",
    }
    if exact_keys(packet, packet_keys, "evidence_packet"):
        assert isinstance(packet, dict)
        if packet.get("schema") != "trillionnium.release-evidence.v1":
            fail("release evidence schema changed")
        for key in (
            "strict_json",
            "detached_signature_required",
            "external_public_key_digest_required",
            "external_attestor_identity_required",
            "current_main_binding_required",
        ):
            if packet.get(key) is not True:
                fail(f"release evidence control {key} is not true")
        if packet.get("maximum_packet_age_seconds") != 86400:
            fail("release evidence freshness bound changed")

    subject = value.get("source_and_image")
    subject_keys = {
        "plan_revision",
        "repository",
        "source_sha_required",
        "source_tree_required",
        "locked_inputs_digest_required",
        "whole_image_digest_and_length_required",
        "s10_installed_product_receipt_required",
        "s11_installed_update_recovery_receipt_required",
        "sbom_license_vulnerability_digests_required",
    }
    if exact_keys(subject, subject_keys, "source_and_image"):
        assert isinstance(subject, dict)
        if subject.get("plan_revision") != "2026-08-29-d6":
            fail("source plan revision is not d6")
        if subject.get("repository") != "TrillionniumFoundation/trillionnium-os-desktop":
            fail("source repository identity changed")
        for key in subject_keys - {"plan_revision", "repository"}:
            if subject.get(key) is not True:
                fail(f"source/image binding {key} is not true")

    rebuild = value.get("independent_rebuild")
    rebuild_keys = {
        "builder_count",
        "distinct_actor_ids",
        "distinct_runner_ids",
        "distinct_administrative_domains",
        "same_source_tree",
        "same_locked_inputs",
        "same_normalized_image_digest",
    }
    if exact_keys(rebuild, rebuild_keys, "independent_rebuild"):
        assert isinstance(rebuild, dict)
        if rebuild.get("builder_count") != 2:
            fail("independent rebuild does not require exactly two builders")
        for key in rebuild_keys - {"builder_count"}:
            if rebuild.get(key) is not True:
                fail(f"independent rebuild control {key} is not true")

    hardware = value.get("fixed_hardware")
    hardware_keys = {
        "exact_bom_required",
        "secure_boot_observed",
        "tpm_or_equivalent_observed",
        "required_results",
    }
    if exact_keys(hardware, hardware_keys, "fixed_hardware"):
        assert isinstance(hardware, dict)
        for key in hardware_keys - {"required_results"}:
            if hardware.get(key) is not True:
                fail(f"fixed-hardware control {key} is not true")
        required_results = {
            "firmware",
            "cpu",
            "memory",
            "storage",
            "gpu",
            "display",
            "input",
            "audio",
            "network",
            "suspend_resume",
            "recovery",
        }
        results = hardware.get("required_results")
        if not isinstance(results, list) or set(results) != required_results or len(results) != len(required_results):
            fail("fixed-hardware result inventory is not exact")

    endurance = value.get("endurance")
    endurance_keys = {
        "required_hours",
        "same_image_and_bom_required",
        "monotonic_checkpoints_required",
        "maximum_checkpoint_gap_seconds",
        "terminal_pass_required",
    }
    if exact_keys(endurance, endurance_keys, "endurance"):
        assert isinstance(endurance, dict)
        if endurance.get("required_hours") != [24, 72]:
            fail("endurance duration inventory changed")
        if endurance.get("maximum_checkpoint_gap_seconds") != 900:
            fail("endurance checkpoint gap changed")
        for key in (
            "same_image_and_bom_required",
            "monotonic_checkpoints_required",
            "terminal_pass_required",
        ):
            if endurance.get(key) is not True:
                fail(f"endurance control {key} is not true")

    power = value.get("raw_power_loss")
    power_keys = {
        "method",
        "required_cutpoints",
        "post_boot_filesystem_pass_required",
        "post_boot_journal_pass_required",
        "post_boot_update_reconciliation_pass_required",
    }
    if exact_keys(power, power_keys, "raw_power_loss"):
        assert isinstance(power, dict)
        if power.get("method") != "non_graceful_power_removal":
            fail("raw-power method changed")
        expected = {
            "update_staging",
            "first_boot_before_health_commit",
            "rollback_or_recovery",
        }
        cutpoints = power.get("required_cutpoints")
        if not isinstance(cutpoints, list) or set(cutpoints) != expected or len(cutpoints) != len(expected):
            fail("raw-power cutpoint inventory is not exact")
        for key in power_keys - {"method", "required_cutpoints"}:
            if power.get(key) is not True:
                fail(f"raw-power control {key} is not true")

    custody = value.get("key_custody")
    custody_keys = {
        "allowed_modes",
        "controller_count",
        "distinct_controllers_required",
        "rotation_drill_required",
        "revocation_drill_required",
        "compromised_builder_drill_required",
    }
    if exact_keys(custody, custody_keys, "key_custody"):
        assert isinstance(custody, dict)
        if custody.get("allowed_modes") != ["offline", "hsm"]:
            fail("production key custody modes changed")
        if custody.get("controller_count") != 2:
            fail("production key custody does not require two controllers")
        for key in custody_keys - {"allowed_modes", "controller_count"}:
            if custody.get(key) is not True:
                fail(f"key custody control {key} is not true")

    roles = value.get("role_separation")
    role_keys = {"roles", "all_actor_ids_distinct"}
    expected_roles = [
        "author",
        "reviewer",
        "builder_a",
        "builder_b",
        "hardware_attestor",
        "endurance_attestor",
        "power_attestor",
        "key_controller_a",
        "key_controller_b",
        "signer",
        "promoter",
        "publisher",
        "release_attestor",
    ]
    if exact_keys(roles, role_keys, "role_separation"):
        assert isinstance(roles, dict)
        if roles.get("roles") != expected_roles:
            fail("release role inventory or order changed")
        if roles.get("all_actor_ids_distinct") is not True:
            fail("release roles are no longer all identity-separated")

    publication = value.get("publication")
    publication_keys = {
        "protected_environment",
        "protected_environment_readback_required",
        "current_main_subject_required",
        "promoter_publisher_separation_required",
        "verifier_may_publish",
    }
    if exact_keys(publication, publication_keys, "publication"):
        assert isinstance(publication, dict)
        if publication.get("protected_environment") != "production-publication":
            fail("production publication environment identity changed")
        for key in (
            "protected_environment_readback_required",
            "current_main_subject_required",
            "promoter_publisher_separation_required",
        ):
            if publication.get(key) is not True:
                fail(f"publication control {key} is not true")
        if publication.get("verifier_may_publish") is not False:
            fail("source verifier was granted publication authority")

    output = value.get("verifier_output")
    output_keys = {
        "eligible_for_independent_promotion_review",
        "release_published_by_this_verifier",
        "external_facts_created_by_this_verifier",
    }
    if exact_keys(output, output_keys, "verifier_output"):
        assert isinstance(output, dict)
        if output.get("eligible_for_independent_promotion_review") != (
            "derived_only_after_all_checks"
        ):
            fail("qualification eligibility derivation changed")
        if output.get("release_published_by_this_verifier") is not False:
            fail("verifier claims publication")
        if output.get("external_facts_created_by_this_verifier") is not False:
            fail("verifier claims to create external facts")

    non_claims = value.get("non_claims")
    expected_nonclaims = {
        "second_builder_executed_by_source_ci",
        "physical_hardware_executed_by_source_ci",
        "endurance_time_elapsed_by_source_ci",
        "raw_power_loss_executed_by_source_ci",
        "production_key_accessed_by_verifier",
        "release_signed_by_verifier",
        "release_published_by_verifier",
    }
    if exact_keys(non_claims, expected_nonclaims, "non_claims"):
        assert isinstance(non_claims, dict)
        if any(item is not False for item in non_claims.values()):
            fail("an S12 non-claim was promoted by source")


def check_verifier() -> None:
    try:
        text = VERIFIER.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(VERIFIER))
    except (OSError, UnicodeError, SyntaxError) as error:
        fail(f"cannot parse S12 verifier: {error}")
        return
    functions = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    required = {
        "strict_json_bytes",
        "canonical_json",
        "verify_packet",
        "verify_detached_signature",
        "qualification_result",
        "main",
    }
    missing = sorted(required - functions)
    if missing:
        fail(f"S12 verifier functions are missing: {missing}")

    forbidden_imports = {"requests", "httpx", "aiohttp", "socket", "urllib"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".", 1)[0] in forbidden_imports:
                    fail(f"S12 verifier imports network module {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".", 1)[0] in forbidden_imports:
                fail(f"S12 verifier imports network module {node.module}")

    for token in (
        "object_pairs_hook=pairs",
        "parse_constant=constant",
        "exactly two independent builder records are required",
        "builder administrative domains are not independent",
        "REQUIRED_ENDURANCE_HOURS = {24, 72}",
        "MAX_CHECKPOINT_GAP_SECONDS = 15 * 60",
        "non_graceful_power_removal",
        "production-publication",
        '"release_published_by_this_verifier": False',
        '"external_facts_created_by_this_verifier": False',
        '"openssl",',
        '"dgst",',
        '"-verify",',
    ):
        if token not in text:
            fail(f"required S12 verifier marker absent: {token}")
    for forbidden in ("curl ", "wget ", "gh api", "git push", "release create"):
        if forbidden in text:
            fail(f"S12 verifier contains forbidden network/publication token {forbidden!r}")


def check_docs_tests_workflow() -> None:
    for path in (CONTRACT, VERIFIER, TEST, DOC, WORKFLOW):
        if path.is_symlink() or not path.is_file():
            fail(f"required S12 path missing or symlinked: {path.relative_to(ROOT)}")

    if TEST.is_file():
        text = TEST.read_text(encoding="utf-8")
        for name in (
            "test_valid_packet_is_only_eligible_for_independent_review",
            "test_strict_json_rejects_duplicates_bom_non_json_and_non_object",
            "test_two_builders_must_be_independent_and_byte_identical",
            "test_all_release_roles_are_identity_separated_and_bound",
            "test_hardware_requires_exact_bom_roots_and_complete_results",
            "test_endurance_requires_real_24_and_72_hour_monotonic_records",
            "test_raw_power_loss_requires_all_three_non_graceful_cutpoints",
            "test_key_custody_requires_two_controllers_and_all_drills",
            "test_s10_s11_current_main_and_publication_bindings_are_closed",
            "test_packet_freshness_signature_and_external_trust_root_are_required",
            "test_detached_signature_verifier_is_exact_and_offline",
        ):
            if f"def {name}(" not in text:
                fail(f"S12 hostile corpus is missing {name}")

    if DOC.is_file():
        text = DOC.read_text(encoding="utf-8")
        headings = (
            "## Scope and claim ceiling",
            "## Externally rooted evidence",
            "## Independent rebuild",
            "## Fixed hardware and endurance",
            "## Raw power-loss qualification",
            "## Key custody and role separation",
            "## Protected promotion and publication",
            "## Evidence invalidation",
            "## Non-claims",
        )
        positions = [text.find(heading) for heading in headings]
        if any(position < 0 for position in positions) or positions != sorted(positions):
            fail("S12 document headings are missing or out of order")
        for phrase in (
            "two independent builders",
            "24-hour",
            "72-hour",
            "non-graceful power removal",
            "offline or HSM",
            "production-publication",
            "does not create external facts",
        ):
            if phrase.lower() not in text.lower():
                fail(f"S12 document omits required phrase {phrase!r}")

    if WORKFLOW.is_file():
        text = WORKFLOW.read_text(encoding="utf-8")
        if "contents: write" in text or "pull-requests: write" in text:
            fail("S12 workflow is not read-only")
        for token in (
            "exact-head:",
            "prospective-merge:",
            "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
            "python3 -m py_compile tools/verify_s12_release_qualification.py",
            "python3 tools/validate_s12_release_qualification.py",
            "python3 -m unittest tests.test_s12_release_qualification -v",
            "python3 tools/validate_s11_update_recovery.py",
            "python3 tools/validate_repository.py",
            "python3 tools/validate_project_truth.py",
            "git diff --check",
        ):
            if token not in text:
                fail(f"S12 workflow omits executable gate token: {token}")


def main() -> int:
    check_contract()
    check_verifier()
    check_docs_tests_workflow()
    for error in ERRORS:
        print(f"S12-RELEASE-QUALIFICATION: {error}", file=sys.stderr)
    if ERRORS:
        print(f"S12 validation failed ({len(ERRORS)} errors)", file=sys.stderr)
        return 1
    print("S12 release-qualification source validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
