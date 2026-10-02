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
        "signature_admission",
        "authority_ownership",
        "image_staging",
        "operator_recovery",
        "journal_reconciliation",
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
        "permits_bound_to_actual_coordinator_instance",
        "health_permits_invalidated_by_boot_failure_or_repeated_boot",
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
        if state.get("permits_bound_to_actual_coordinator_instance") is not True:
            fail("permit authority can cross coordinator instances")
        if state.get("health_permits_invalidated_by_boot_failure_or_repeated_boot") is not True:
            fail("health permits survive boot failure or repeated boot")

    durability = value.get("durability")
    durability_keys = {
        "state_directory_mode",
        "state_file_mode",
        "path_walk",
        "publication",
        "exclusive_coordinator_lease",
        "lease_release",
        "descriptor_lifecycle",
        "post_replace_failure",
        "replace_call_failure",
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
        if durability.get("lease_release") != "close_descriptor_copies_only_never_explicit_unlock_last_copy_releases":
            fail("fork child cleanup can release another coordinator's lease")
        if durability.get("descriptor_lifecycle") != "explicit_close_or_descriptor_only_gc_with_cleared_ownership_no_write_or_reconciliation":
            fail("descriptor cleanup acquired transaction authority")
        if durability.get("post_replace_failure") != (
            "publication_indeterminate_reconcile_before_retry"
        ):
            fail("post-replace uncertainty is no longer fail closed")
        if durability.get("replace_call_failure") != "publication_indeterminate_even_before_return":
            fail("replace-call interruption is no longer classified as indeterminate")

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

    expected_signature = {
        "default_admission_enabled": False,
        "trust_roots": "externally_approved_pinned_public_pem_not_manifest_or_repository",
        "signing_preimage_domain": "trillionnium.desktop.update-manifest-signature.v1\\u0000",
        "signing_preimage_encoding": "ascii_json_ensure_ascii_sorted_keys_compact_no_trailing_newline",
        "unsigned_envelope_fields": ["signature_sha256"],
        "detached_signature_digest_required": True,
        "verification": "system_openssl_dgst_sha256_verify_offline",
        "verification_input_custody": "three_sealed_linux_memfds_inherited_via_pass_fds_proc_self_fd_only",
        "verification_input_seals": ["write", "grow", "shrink", "seal"],
        "verification_environment": {"PATH": "/usr/bin:/bin", "OPENSSL_CONF": "/dev/null", "LC_ALL": "C"},
        "maximum_signature_bytes": 65536,
        "maximum_public_key_bytes": 65536,
        "maximum_trust_roots": 32,
        "verifier_timeout_seconds": 15,
        "unknown_revoked_or_expired_signer_refused": True,
        "protected_floor_and_root_minimum_required": True,
        "trusted_clock_and_revalidation_before_publication_and_boot": True,
        "trusted_clock_and_revalidation_before_commit": True,
        "external_monotonic_floor_persistence_implemented": False,
    }
    expected_ownership = {
        "configuration_types": "exact_UpdateTrustRoot_ExternalUpdateSignatureVerifier_DurableUpdateJournal_ImageSlotStore_no_subclass_callbacks",
        "scope": "creating_process_and_creating_thread",
        "guard_before_authority_use": True,
        "inherited_fork_authority": False,
        "fork_child_descriptor_cleanup_only": True,
        "thread_transfer_or_concurrent_use": False,
        "caller_verification_or_persistence_callbacks": False,
        "callbacks": "trusted_nonreentrant_in_process_configuration",
    }
    expected_staging = {
        "backend": "private_leased_regular_file_slots_only",
        "slot_names": ["slot-A.img", "slot-B.img"],
        "full_digest_and_length_verified_before_temp_write": True,
        "stream_chunk_bytes": 1048576,
        "active_slot_source_digest_verified": True,
        "retained_temp_and_named_inode_verified": True,
        "publication": "file_fsync_atomic_replace_directory_fsync",
        "post_replace_failure": "image_publication_indeterminate_recovery_required",
        "reconciliation": "verify_existing_complete_image_file_and_directory_fsync_no_rewrite",
        "production_activation_enabled": False,
        "replace_call_failure": "publication_indeterminate_even_before_return",
        "coordinator_intent_recorded_before_replace_call": True,
    }
    expected_operator = {
        "default_approved_operator_uids": [],
        "identity": "actual_local_effective_uid_from_external_approved_configuration",
        "action": "rollback_only_no_replay",
        "complete_source_digest_and_protected_floor_required": True,
        "possible_dispatch_latch_clear": "complete_private_durable_operation_record_verified_and_resynced_by_configured_authority",
        "bootloader_or_block_device_mutation": False,
    }
    expected_journal = {
        "default_authority_enabled": False,
        "schema": "trillionnium.desktop.update-dispatch-journal.v1",
        "exact_fields": ["schema", "manifest_sha256", "sequence", "operation_id", "operation", "target_slot", "image_sha256", "status"],
        "operation_identity": "coordinator_issued_random_256_bit_nonce",
        "caller_digest_or_status_assertion_accepted": False,
        "private_retained_root_lease_and_record_inode_required": True,
        "complete_bounded_record_required": True,
        "file_and_directory_fsync_before_fact_and_clear": True,
        "actual_issued_fact_and_current_record_identity_required": True,
        "clear_target_phase": "rollback_pending",
        "installed_journal_authority_provisioned": False,
    }
    for name, expected in (("signature_admission", expected_signature), ("authority_ownership", expected_ownership), ("image_staging", expected_staging),
                           ("operator_recovery", expected_operator), ("journal_reconciliation", expected_journal)):
        actual = value.get(name)
        if exact_keys(actual, set(expected), name):
            for key, expected_value in expected.items():
                if type(actual[key]) is not type(expected_value) or actual[key] != expected_value:
                    fail(f"{name}.{key} changed its closed admission/recovery contract")


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
        "UpdateTrustRoot",
        "ExternalUpdateSignatureVerifier",
        "SignatureAdmission",
        "ImageSlotStore",
        "ImageStageReceipt",
        "ImagePublicationIndeterminate",
        "RecoveryDecision",
        "DurableUpdateJournal",
        "DispatchBinding",
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
        "manifest_signing_bytes",
        "_image_digest",
        "_trusted_now",
        "_revalidate_admission",
        "stage_image_file",
        "reconcile_image_publication",
        "reconcile_image",
        "request_operator_rollback",
        "confirm_dispatch",
    }
    missing_functions = sorted(required_functions - functions)
    if missing_functions:
        fail(f"S11 source functions are missing: {missing_functions}")

    forbidden_imports = {"requests", "httpx", "aiohttp", "socket", "urllib"}
    offline_verifiers = []
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
            if name and name.startswith("subprocess."):
                if name != "subprocess.run":
                    fail(f"S11 subprocess API is outside the one bounded verifier: {name}")
                else:
                    offline_verifiers.append(node)

    if len(offline_verifiers) != 1:
        fail("S11 must have exactly one offline verification process boundary")
    else:
        call = offline_verifiers[0]
        keywords = {keyword.arg: ast.unparse(keyword.value) for keyword in call.keywords}
        if keywords != {"stdin": "subprocess.DEVNULL", "stdout": "subprocess.DEVNULL", "stderr": "subprocess.DEVNULL",
                        "env": "OPENSSL_ENV", "pass_fds": "tuple(snapshots)", "timeout": "15", "check": "False"}:
            fail("offline verifier sealed descriptor inheritance, fixed environment, timeout or redacted I/O changed")
        arguments = ast.unparse(call.args[0]) if len(call.args) == 1 else ""
        for token in ("str(executable)", "'dgst'", "'-sha256'", "'-verify'", "'-signature'", "/proc/self/fd/", "key_fd", "signature_fd", "manifest_fd"):
            if token not in arguments:
                fail(f"offline signature verifier command lost {token}")

    authority_classes = {"ExternalUpdateSignatureVerifier", "UpdateCoordinator", "AtomicStateStore", "ImageSlotStore", "DurableUpdateJournal"}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name not in authority_classes:
            continue
        expected_base = "AtomicStateStore" if node.name in {"ImageSlotStore", "DurableUpdateJournal"} else "_ProcessThreadOwner"
        if expected_base not in {ast.unparse(base) for base in node.bases}:
            fail(f"{node.name} lost its process/thread owner binding")
        for method in node.body:
            if not isinstance(method, ast.FunctionDef):
                continue
            decorators = {ast.unparse(item) for item in method.decorator_list}
            if method.name in {"__init__", "__exit__"} or "staticmethod" in decorators:
                continue
            if node.name == "AtomicStateStore" and method.name in {"close", "__del__", "_release_descriptors"}:
                continue  # A fork child and GC may close only descriptor copies.
            if "_owner_guard" not in decorators:
                fail(f"{node.name}.{method.name} lacks an authority ownership guard")
    if any(isinstance(node, ast.Attribute) and node.attr == "LOCK_UN" for node in ast.walk(tree)):
        fail("explicit flock unlock can release a live parent's inherited lease")

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
        'Path("/usr/bin/openssl")',
        "SIGNATURE_DOMAIN",
        'key != "signature_sha256"',
        "MAX_SIGNATURE_BYTES",
        "MAX_PUBLIC_KEY_BYTES",
        "root.revoked",
        "root.valid_until_unix",
        "protected_rollback_floor",
        "production_activation_enabled: bool = False",
        "os.pread(descriptor, min(1024 * 1024",
        "os.fsync(target_fd)",
        "except BaseException as error:",
        "self._health_permit is not permit",
        "self._reconciliation_fact is not fact",
        "secrets.token_hex(32)",
        "os.memfd_create(name, os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)",
        "fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL",
        "os.getpid() != self._owner_pid",
        "threading.current_thread() is not self._owner_thread",
        "type(root) is not UpdateTrustRoot",
        "type(signature_verifier) is not ExternalUpdateSignatureVerifier",
        "type(journal_authority) is not DurableUpdateJournal",
        "type(slot_store) is not ImageSlotStore",
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
            "test_real_signature_and_domain_separated_preimage",
            "test_unsigned_default_wrong_key_and_actual_signature_digest_refused",
            "test_every_authority_field_is_signed_even_with_valid_envelope_digest",
            "test_unapproved_revoked_expired_or_unpinned_roots_refused",
            "test_floor_and_clock_cannot_be_weakened",
            "test_expiry_clock_regression_and_policy_change_rechecked_before_stage_and_boot",
            "test_streamed_real_signed_publication_is_durable_and_inactive_only",
            "test_bad_complete_image_or_active_slot_refused_before_any_write",
            "test_temp_substitution_and_source_growth_cannot_publish",
            "test_post_replace_uncertainty_requires_fsync_reconciliation_without_rewrite",
            "test_approved_operator_rollback_binds_source_and_never_clears_dispatch_latch",
            "test_post_replace_interrupts_are_indeterminate_and_cannot_restaging",
            "test_atomic_state_post_replace_interrupts_preserve_uncertainty",
            "test_permits_and_tickets_cannot_cross_coordinator_instances",
            "test_caller_hash_and_status_cannot_mint_reconciliation",
            "test_complete_bound_durable_record_and_revalidation_clear_only_to_rollback",
            "test_missing_malformed_wrong_operation_manifest_and_sequence_records_refused",
            "test_sync_failure_copied_fact_and_replaced_record_cannot_clear_latch",
            "test_journal_fact_cannot_cross_coordinator_instances",
            "test_replace_effect_then_interrupt_before_return_is_indeterminate",
            "test_publication_return_interrupt_still_retains_recovery_intent",
            "test_health_permit_expires_on_boot_failure_and_cannot_commit_expired_admission",
            "test_sealed_inputs_refuse_actual_wrong_signer_key_substitution",
            "test_real_crypto_inputs_are_sealed_environment_fixed_and_fds_closed",
            "test_snapshot_write_failure_closes_fds_and_never_verifies",
            "test_child_close_cannot_release_parent_lease",
            "test_inherited_health_permit_cannot_commit_after_parent_boot_failure",
            "test_forked_verifier_store_staging_and_reconciliation_are_refused",
            "test_authority_requires_creating_thread_before_crypto_or_storage",
            "test_callback_verifier_and_root_subclasses_refused_before_authority",
            "test_callback_journal_and_slot_subclasses_refused_before_authority",
            "test_discarded_store_gc_on_foreign_thread_closes_fds_and_releases_lease",
            "test_failed_constructor_cleanup_cannot_close_reused_descriptor",
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
            "manifest_signing_bytes",
            "stage_image_file",
            "request_operator_rollback",
            "externally approved",
            "OpenSSL",
            "sealed memfds",
            "creating process and creating thread",
            "last descriptor copy",
        ):
            if phrase.lower() not in text.lower():
                fail(f"S11 document omits required phrase {phrase!r}")

    if WORKFLOW.is_file():
        text = WORKFLOW.read_text(encoding="utf-8")
        if "contents: write" in text or "pull-requests: write" in text:
            fail("S11 workflow is not read-only")
        if '  push:\n    branches:\n      - main\n      - "codex/**"\n' not in text:
            fail("S11 exact-head push checks must cover main and codex/**")
        for token in (
            "exact-head:",
            "prospective-merge:",
            "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
            "python3 -m py_compile platform/update_recovery.py",
            "python3 tools/validate_s11_update_recovery.py",
            "python3 -m unittest tests.test_s11_update_recovery -v",
            "test -x /usr/bin/openssl",
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
