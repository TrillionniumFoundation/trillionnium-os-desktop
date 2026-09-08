"""Policy verification for independently produced D3 integrated-runtime evidence."""

from __future__ import annotations

import base64
import copy
import hashlib
from pathlib import Path
from typing import Any

from trusted_app_bundle import canonical_json, ed25519_verify
from d3_integrated_runtime_common import (
    DEFAULT_CONTRACT,
    EvidenceError,
    load_json,
    require_bool,
    require_dict,
    require_list,
    require_sha40,
    require_sha256,
    require_token,
    verify_artifacts,
    verify_receipt_chain,
)

def verify_receipts(evidence: dict[str, Any], contract: dict[str, Any]) -> int:
    receipts = require_dict(evidence.get("receipts"), "RECEIPTS_REQUIRED")
    require_bool(
        receipts.get("requested_fsync_before_dispatch"),
        True,
        "REQUESTED_NOT_DURABLE_BEFORE_DISPATCH",
    )
    require_bool(
        receipts.get("terminal_fsync_before_response"),
        True,
        "TERMINAL_NOT_DURABLE_BEFORE_RESPONSE",
    )
    require_bool(receipts.get("automatic_replay"), False, "AUTOMATIC_REPLAY_FORBIDDEN")
    require_bool(
        receipts.get("indeterminate_requires_reconciliation"),
        True,
        "INDETERMINATE_RECONCILIATION_REQUIRED",
    )
    chains = require_list(receipts.get("chains"), "RECEIPT_CHAINS_REQUIRED")
    terminals = require_list(
        contract.get("required_receipt_terminals"), "CONTRACT_TERMINALS_REQUIRED"
    )
    if len(chains) != len(terminals):
        raise EvidenceError("RECEIPT_CHAIN_COUNT_MISMATCH")
    by_terminal: dict[str, Any] = {}
    for chain in chains:
        value = require_dict(chain, "INVALID_RECEIPT_CHAIN")
        records = require_list(value.get("records"), "RECEIPT_RECORDS_REQUIRED")
        if len(records) != 3 or not isinstance(records[-1], dict):
            raise EvidenceError("INVALID_RECEIPT_CHAIN")
        terminal = records[-1].get("event")
        if not isinstance(terminal, str) or terminal in by_terminal:
            raise EvidenceError("DUPLICATE_OR_INVALID_RECEIPT_TERMINAL")
        by_terminal[terminal] = chain
    if set(by_terminal) != set(terminals):
        raise EvidenceError("RECEIPT_TERMINAL_SET_MISMATCH")
    for terminal in terminals:
        verify_receipt_chain(by_terminal[terminal], terminal)
    return len(chains)


def verify_source_and_image(
    evidence: dict[str, Any], contract: dict[str, Any], *, require_exact_main: bool
) -> None:
    if evidence.get("schema") != contract.get("evidence_schema"):
        raise EvidenceError("EVIDENCE_SCHEMA_MISMATCH")
    if evidence.get("status") != "PASS_D3_EXACT_IMAGE_RUNTIME_CANDIDATE":
        raise EvidenceError("EVIDENCE_STATUS_MISMATCH")
    source = require_dict(evidence.get("source"), "SOURCE_IDENTITY_REQUIRED")
    if source.get("repository") != contract.get("repository"):
        raise EvidenceError("REPOSITORY_IDENTITY_MISMATCH")
    reference = source.get("ref")
    if not isinstance(reference, str) or not reference.startswith("refs/"):
        raise EvidenceError("INVALID_SOURCE_REF")
    head = require_sha40(source.get("head_sha"), "INVALID_HEAD_SHA")
    require_sha40(source.get("tree_sha"), "INVALID_TREE_SHA")
    tested = require_sha40(source.get("tested_sha"), "INVALID_TESTED_SHA")
    require_sha40(source.get("base_sha"), "INVALID_BASE_SHA")
    integrated = source.get("integrated_main_sha")
    if integrated is not None:
        integrated = require_sha40(integrated, "INVALID_INTEGRATED_MAIN_SHA")
    fixture_evidence = source.get("fixture_evidence")
    if not isinstance(fixture_evidence, bool):
        raise EvidenceError("FIXTURE_EVIDENCE_FLAG_REQUIRED")
    if require_exact_main:
        policy = require_dict(contract.get("exact_main_policy"), "EXACT_MAIN_POLICY_REQUIRED")
        if reference != policy.get("ref"):
            raise EvidenceError("EXACT_MAIN_REF_REQUIRED")
        if integrated is None or head != tested or head != integrated:
            raise EvidenceError("EXACT_MAIN_IDENTITY_MISMATCH")
        if fixture_evidence:
            raise EvidenceError("FIXTURE_EVIDENCE_FORBIDDEN_FOR_EXACT_MAIN")

    image = require_dict(evidence.get("image"), "IMAGE_IDENTITY_REQUIRED")
    require_sha256(image.get("sha256"), "INVALID_IMAGE_SHA256")
    if image.get("qemu_machine") != "q35":
        raise EvidenceError("Q35_REQUIRED")
    require_bool(image.get("tcg"), True, "TCG_REQUIRED")
    require_bool(image.get("network_device_present"), False, "NETWORK_DEVICE_FORBIDDEN")
    require_bool(image.get("systemd_pid1"), True, "SYSTEMD_PID1_REQUIRED")
    require_bool(image.get("wayland_ready"), True, "WAYLAND_REQUIRED")
    require_bool(image.get("servo_runtime_ready"), True, "SERVO_RUNTIME_REQUIRED")
    if image.get("servo_commit") != contract.get("servo_commit"):
        raise EvidenceError("SERVO_COMMIT_MISMATCH")


def verify_principal(evidence: dict[str, Any]) -> None:
    principal = require_dict(evidence.get("principal"), "PRINCIPAL_EVIDENCE_REQUIRED")
    admission = require_dict(principal.get("admission"), "ADMISSION_SNAPSHOT_REQUIRED")
    dispatch = require_dict(principal.get("dispatch"), "DISPATCH_SNAPSHOT_REQUIRED")
    required_keys = {
        "pid",
        "uid",
        "gid",
        "start_time_ticks",
        "systemd_unit",
        "cgroup_v2_path",
        "executable_sha256",
        "pidfd_alive",
    }
    if set(admission) != required_keys or set(dispatch) != required_keys:
        raise EvidenceError("PRINCIPAL_SNAPSHOT_SHAPE_MISMATCH")
    if admission != dispatch:
        raise EvidenceError("PRINCIPAL_DISPATCH_DRIFT")
    for key in ("pid", "start_time_ticks"):
        value = admission.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise EvidenceError("INVALID_PRINCIPAL_NUMERIC_IDENTITY", key)
    for key in ("uid", "gid"):
        value = admission.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise EvidenceError("INVALID_PRINCIPAL_NUMERIC_IDENTITY", key)
    require_token(admission.get("systemd_unit"), "INVALID_SYSTEMD_UNIT")
    require_token(admission.get("cgroup_v2_path"), "INVALID_CGROUP_PATH")
    require_sha256(admission.get("executable_sha256"), "INVALID_EXECUTABLE_SHA256")
    require_bool(admission.get("pidfd_alive"), True, "PIDFD_LIVENESS_REQUIRED")
    require_bool(principal.get("dispatch_time_revalidated"), True, "DISPATCH_REVALIDATION_REQUIRED")


def verify_semantic_action(evidence: dict[str, Any]) -> None:
    action = require_dict(evidence.get("semantic_action"), "SEMANTIC_ACTION_EVIDENCE_REQUIRED")
    for field in (
        "servo_owned_adapter",
        "engine_retained_node",
        "same_engine_critical_section",
        "current_frame_only",
        "role_match",
        "accessible_name_digest_match",
        "structural_fingerprint_match",
        "revalidated_immediately_before_action",
    ):
        require_bool(action.get(field), True, f"SEMANTIC_ACTION_{field.upper()}_REQUIRED")
    for field in (
        "coordinate_fallback",
        "dom_order_fallback",
        "accessible_name_only_fallback",
        "cross_frame_fallback",
    ):
        require_bool(action.get(field), False, f"SEMANTIC_ACTION_{field.upper()}_FORBIDDEN")
    if action.get("unique_match_count") != 1:
        raise EvidenceError("UNIQUE_CURRENT_TARGET_REQUIRED")
    if action.get("action_count") != 1:
        raise EvidenceError("EXACTLY_ONE_ACTION_REQUIRED")
    before = action.get("mutation_epoch_before")
    after = action.get("mutation_epoch_after")
    if (
        isinstance(before, bool)
        or not isinstance(before, int)
        or isinstance(after, bool)
        or not isinstance(after, int)
        or after != before + 1
    ):
        raise EvidenceError("MUTATION_EPOCH_MUST_ADVANCE_ONCE")


def verify_cases(evidence: dict[str, Any], contract: dict[str, Any]) -> int:
    cases = require_dict(evidence.get("cases"), "RUNTIME_CASES_REQUIRED")
    expected = require_dict(contract.get("required_cases"), "CONTRACT_CASES_REQUIRED")
    if set(cases) != set(expected):
        raise EvidenceError("RUNTIME_CASE_SET_MISMATCH")
    for name, outcome in expected.items():
        if cases.get(name) != outcome:
            raise EvidenceError("RUNTIME_CASE_OUTCOME_MISMATCH", name)
    return len(cases)


def verify_product_boundaries(evidence: dict[str, Any]) -> None:
    boundaries = require_dict(evidence.get("product_boundaries"), "PRODUCT_BOUNDARIES_REQUIRED")
    for field in (
        "production_agent_port_enabled",
        "external_effect_authority",
        "external_network_enabled",
        "ambient_filesystem_authority",
        "hardware_qualified",
        "signing_key_custody",
        "release_ready",
    ):
        require_bool(boundaries.get(field), False, f"BOUNDARY_{field.upper()}_MUST_BE_FALSE")
    require_bool(
        boundaries.get("development_profile_explicit"),
        True,
        "EXPLICIT_DEVELOPMENT_PROFILE_REQUIRED",
    )


def attestation_payload(evidence: dict[str, Any]) -> bytes:
    unsigned = copy.deepcopy(evidence)
    unsigned["attestations"] = []
    return canonical_json(unsigned)


def _decode_base64(value: Any, expected_bytes: int, reason: str) -> bytes:
    if not isinstance(value, str):
        raise EvidenceError(reason)
    try:
        result = base64.b64decode(value, validate=True)
    except (ValueError, base64.binascii.Error) as error:
        raise EvidenceError(reason) from error
    if len(result) != expected_bytes:
        raise EvidenceError(reason)
    return result


def verify_attestations(
    evidence: dict[str, Any],
    contract: dict[str, Any],
    keyring: dict[str, Any] | None,
    *,
    require_exact_main: bool,
) -> int:
    attestations = require_list(evidence.get("attestations"), "ATTESTATION_LIST_REQUIRED")
    if keyring is None:
        if require_exact_main:
            raise EvidenceError("KEYRING_REQUIRED_FOR_EXACT_MAIN")
        if attestations:
            raise EvidenceError("UNVERIFIED_ATTESTATIONS_FORBIDDEN")
        return 0

    if keyring.get("schema") != "trillionnium.desktop.d3-attestation-keyring.v1":
        raise EvidenceError("KEYRING_SCHEMA_MISMATCH")
    key_entries = require_list(keyring.get("keys"), "KEYRING_KEYS_REQUIRED")
    keys: dict[str, dict[str, Any]] = {}
    for item in key_entries:
        record = require_dict(item, "INVALID_KEYRING_RECORD")
        key_id = require_token(record.get("key_id"), "INVALID_KEY_ID")
        if key_id in keys:
            raise EvidenceError("DUPLICATE_KEY_ID", key_id)
        require_token(record.get("identity"), "INVALID_KEY_IDENTITY")
        require_token(record.get("role"), "INVALID_KEY_ROLE")
        _decode_base64(record.get("public_key_base64"), 32, "INVALID_PUBLIC_KEY")
        if not isinstance(record.get("production_enrolled"), bool):
            raise EvidenceError("PRODUCTION_ENROLLMENT_FLAG_REQUIRED")
        keys[key_id] = record

    required_roles = set(
        require_list(contract.get("required_operator_roles"), "CONTRACT_ROLES_REQUIRED")
    )
    seen_roles: set[str] = set()
    seen_identities: set[str] = set()
    seen_keys: set[str] = set()
    payload = attestation_payload(evidence)
    for item in attestations:
        record = require_dict(item, "INVALID_ATTESTATION_RECORD")
        if set(record) != {"key_id", "identity", "role", "signature_base64"}:
            raise EvidenceError("INVALID_ATTESTATION_RECORD_SHAPE")
        key_id = require_token(record.get("key_id"), "INVALID_ATTESTATION_KEY_ID")
        identity = require_token(record.get("identity"), "INVALID_ATTESTATION_IDENTITY")
        role = require_token(record.get("role"), "INVALID_ATTESTATION_ROLE")
        if key_id in seen_keys or identity in seen_identities or role in seen_roles:
            raise EvidenceError("ATTESTATION_ROLE_IDENTITY_OR_KEY_NOT_DISTINCT")
        key = keys.get(key_id)
        if key is None:
            raise EvidenceError("UNKNOWN_ATTESTATION_KEY", key_id)
        if key.get("identity") != identity or key.get("role") != role:
            raise EvidenceError("ATTESTATION_KEY_BINDING_MISMATCH", key_id)
        if require_exact_main and key.get("production_enrolled") is not True:
            raise EvidenceError("PRODUCTION_ENROLLED_KEY_REQUIRED", key_id)
        public_key = _decode_base64(key.get("public_key_base64"), 32, "INVALID_PUBLIC_KEY")
        signature = _decode_base64(
            record.get("signature_base64"), 64, "INVALID_ATTESTATION_SIGNATURE"
        )
        if not ed25519_verify(public_key, payload, signature):
            raise EvidenceError("ATTESTATION_SIGNATURE_INVALID", key_id)
        seen_keys.add(key_id)
        seen_identities.add(identity)
        seen_roles.add(role)
    if seen_roles != required_roles:
        raise EvidenceError("ATTESTATION_ROLE_SET_MISMATCH")
    return len(attestations)


def verify_evidence(
    evidence_path: Path,
    artifact_root: Path,
    *,
    contract_path: Path = DEFAULT_CONTRACT,
    keyring_path: Path | None = None,
    require_exact_main: bool = False,
) -> dict[str, Any]:
    contract = load_json(contract_path)
    evidence = load_json(evidence_path)
    keyring = load_json(keyring_path) if keyring_path is not None else None
    verify_source_and_image(evidence, contract, require_exact_main=require_exact_main)
    artifact_count = verify_artifacts(evidence, contract, artifact_root)
    verify_principal(evidence)
    verify_semantic_action(evidence)
    case_count = verify_cases(evidence, contract)
    receipt_chain_count = verify_receipts(evidence, contract)
    verify_product_boundaries(evidence)
    attestation_count = verify_attestations(
        evidence,
        contract,
        keyring,
        require_exact_main=require_exact_main,
    )
    evidence_digest = hashlib.sha256(canonical_json(evidence)).hexdigest()
    exact_main = require_exact_main
    return {
        "schema": "trillionnium.desktop.d3-integrated-runtime-verification-result.v1",
        "status": (
            "PASS_D3_EXACT_MAIN_EVIDENCE"
            if exact_main
            else "PASS_SOURCE_VERIFIER_ONLY"
        ),
        "evidence_sha256": evidence_digest,
        "artifact_count": artifact_count,
        "runtime_case_count": case_count,
        "receipt_chain_count": receipt_chain_count,
        "verified_attestation_count": attestation_count,
        "exact_main_identity_verified": exact_main,
        "promotion_eligible": exact_main and attestation_count == 2,
        "promotion_authoritative": False,
        "product_agent_port_enabled": False,
        "external_effect_authority": False,
        "hardware_qualified": False,
        "release_ready": False,
    }

