#!/usr/bin/env python3
"""Offline D9 signed-release promotion policy verifier.

This source package verifies evidence only. It cannot protect a branch or tag,
approve a pull request or environment, access release keys, sign or publish
artifacts, update metadata, or promote a release.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from trusted_app_bundle import (  # noqa: E402
    canonical_json,
    ed25519_public_from_seed,
    ed25519_sign_fixture,
    ed25519_verify,
)

CONTRACT_PATH = ROOT / "contracts" / "signed-release-promotion.v1.json"
HEX_40 = re.compile(r"^[0-9a-f]{40}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
EVIDENCE_FIELDS = {
    "schema",
    "release_id",
    "environment_kind",
    "channel",
    "version",
    "rollback_index",
    "hardware_profile_id",
    "d8_qualification_id",
    "created_at_epoch",
    "source_identity",
    "artifact_identity",
    "artifacts",
    "checks",
    "source_approvals",
    "environment_approvals",
    "promoter",
    "machine_nonclaims",
    "release_signatures",
}
ARTIFACT_FIELDS = {"role", "path", "sha256", "bytes"}
CHECK_FIELDS = {"context", "head_sha", "status", "completed_at_epoch"}
SOURCE_APPROVAL_FIELDS = {
    "reviewer_id",
    "reviewed_sha",
    "decision",
    "submitted_at_epoch",
    "after_latest_push",
}
ENVIRONMENT_APPROVAL_FIELDS = {
    "approver_id",
    "environment",
    "release_id",
    "decision",
    "approved_at_epoch",
}
PROMOTER_FIELDS = {
    "actor_id",
    "environment",
    "method",
    "administrator_bypass",
    "promoted_at_epoch",
}
RELEASE_SIGNATURE_FIELDS = {
    "role",
    "signer_id",
    "key_id",
    "algorithm",
    "value_base64",
}
SIGNED_DOCUMENT_SIGNATURE_FIELDS = {
    "algorithm",
    "signer_id",
    "key_id",
    "value_base64",
}
GOVERNANCE_FIELDS = {
    "schema",
    "repository",
    "main_ref",
    "main_sha",
    "main_tree",
    "branch_protected",
    "strict_required_checks",
    "required_checks",
    "source_approval_ids",
    "dismiss_stale_approvals",
    "approval_after_latest_push_required",
    "code_owner_review_required",
    "all_conversations_resolved",
    "administrator_bypass_allowed",
    "force_push_allowed",
    "branch_deletion_allowed",
    "protected_environment",
    "environment_approval_ids",
    "protected_tag",
    "tag",
    "signature",
}
CUSTODY_FIELDS = {
    "schema",
    "release_key_ids",
    "custodian_ids",
    "storage",
    "dual_control",
    "pull_request_workflow_access",
    "repository_secret_access",
    "source_author_excluded",
    "rotation_procedure_sha256",
    "revocation_procedure_sha256",
    "disaster_recovery_procedure_sha256",
    "signature",
}
UPDATE_FIELDS = {
    "schema",
    "release_id",
    "version",
    "rollback_index",
    "hardware_profile_id",
    "image_sha256",
    "image_bytes",
    "recovery_metadata_sha256",
    "support_policy_sha256",
    "signature",
}
RECOVERY_FIELDS = {
    "schema",
    "release_id",
    "hardware_profile_id",
    "minimum_rollback_index",
    "recovery_image_sha256",
    "support_policy_sha256",
    "automatic_destructive_recovery",
    "signature",
}
D8_FIELDS = {
    "schema",
    "status",
    "qualification_id",
    "hardware_profile_id",
    "duration_seconds",
    "policy_eligible",
    "lab_signer_role",
    "image_sha256",
    "kernel_sha256",
    "initrd_sha256",
    "package_lock_sha256",
    "sbom_sha256",
    "provenance_sha256",
    "critical_failures",
    "uncorrected_data_corruption",
    "unexpected_external_effects",
    "network_policy_bypasses",
    "hardware_beta_promoted",
    "release_ready",
    "verification_receipt_sha256",
}
PREVIOUS_FIELDS = {
    "schema",
    "repository",
    "channel",
    "release_id",
    "version",
    "rollback_index",
    "release_manifest_sha256",
}


class ReleasePolicyError(ValueError):
    def __init__(self, reason: str, detail: str | None = None) -> None:
        super().__init__(reason if detail is None else f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


def fail(reason: str, detail: str | None = None) -> None:
    raise ReleasePolicyError(reason, detail)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReleasePolicyError("INVALID_JSON", str(path)) from error
    if not isinstance(value, dict):
        fail("JSON_OBJECT_REQUIRED", str(path))
    return value


def require_identifier(value: Any, reason: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        fail(reason)
    return value


def require_hex(value: Any, pattern: re.Pattern[str], reason: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        fail(reason)
    return value


def normalize_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        fail("RELEASE_ARTIFACT_PATH_INVALID")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        fail("RELEASE_ARTIFACT_PATH_TRAVERSAL", value)
    normalized = "/".join(path.parts)
    if normalized != value or len(value.encode("utf-8")) > 512:
        fail("RELEASE_ARTIFACT_PATH_NON_CANONICAL", value)
    return normalized


def release_payload(evidence: dict[str, Any]) -> bytes:
    value = copy.deepcopy(evidence)
    value.pop("release_signatures", None)
    return canonical_json(value)


def signed_document_payload(value: dict[str, Any]) -> bytes:
    result = copy.deepcopy(value)
    result.pop("signature", None)
    return canonical_json(result)


def decode_signature(value: Any, reason: str) -> bytes:
    if not isinstance(value, str):
        fail(reason)
    try:
        decoded = base64.b64decode(value, validate=True)
    except (TypeError, ValueError) as error:
        raise ReleasePolicyError(reason, "invalid base64") from error
    if len(decoded) != 64:
        fail(reason, "expected 64 bytes")
    return decoded


def trust_key(
    trust: dict[str, Any],
    group: str,
    actor_id: str,
    key_id: str,
    role: str,
    *,
    now_epoch: int,
    require_production: bool,
) -> bytes:
    if trust.get("schema") != "trillionnium.desktop.release-trust.v1":
        fail("RELEASE_TRUST_SCHEMA_MISMATCH")
    group_value = trust.get(group)
    actor = group_value.get(actor_id) if isinstance(group_value, dict) else None
    keys = actor.get("keys") if isinstance(actor, dict) else None
    record = keys.get(key_id) if isinstance(keys, dict) else None
    required = {
        "status",
        "role",
        "public_key_base64",
        "not_before_epoch",
        "expires_at_epoch",
        "production_enrolled",
    }
    if not isinstance(record, dict) or set(record) != required:
        fail("RELEASE_TRUST_KEY_UNKNOWN_OR_INVALID", f"{group}:{actor_id}:{key_id}")
    if record["status"] != "active":
        fail("RELEASE_TRUST_KEY_NOT_ACTIVE", key_id)
    if record["role"] != role:
        fail("RELEASE_TRUST_ROLE_MISMATCH", role)
    if not isinstance(record["not_before_epoch"], int) or not isinstance(record["expires_at_epoch"], int):
        fail("RELEASE_TRUST_KEY_TIME_INVALID")
    if not record["not_before_epoch"] <= now_epoch <= record["expires_at_epoch"]:
        fail("RELEASE_TRUST_KEY_OUTSIDE_VALIDITY")
    if require_production and record["production_enrolled"] is not True:
        fail("PRODUCTION_RELEASE_TRUST_KEY_REQUIRED", f"{group}:{key_id}")
    revoked = trust.get("revoked_key_ids")
    if not isinstance(revoked, list) or not all(isinstance(item, str) for item in revoked):
        fail("REVOKED_RELEASE_KEY_SET_INVALID")
    if key_id in revoked:
        fail("RELEASE_KEY_REVOKED", key_id)
    try:
        public = base64.b64decode(record["public_key_base64"], validate=True)
    except (TypeError, ValueError) as error:
        raise ReleasePolicyError("RELEASE_PUBLIC_KEY_INVALID", key_id) from error
    if len(public) != 32:
        fail("RELEASE_PUBLIC_KEY_LENGTH_INVALID", key_id)
    return public


def verify_signature_record(
    value: dict[str, Any],
    payload: bytes,
    trust: dict[str, Any],
    *,
    group: str,
    expected_role: str,
    now_epoch: int,
    require_production: bool,
) -> tuple[str, str]:
    if not isinstance(value, dict) or set(value) != SIGNED_DOCUMENT_SIGNATURE_FIELDS:
        fail("SIGNED_DOCUMENT_SIGNATURE_FIELD_SET_MISMATCH")
    if value["algorithm"] != "Ed25519":
        fail("SIGNED_DOCUMENT_SIGNATURE_ALGORITHM_UNSUPPORTED")
    signer_id = require_identifier(value["signer_id"], "SIGNED_DOCUMENT_SIGNER_ID_INVALID")
    key_id = require_identifier(value["key_id"], "SIGNED_DOCUMENT_KEY_ID_INVALID")
    public = trust_key(
        trust,
        group,
        signer_id,
        key_id,
        expected_role,
        now_epoch=now_epoch,
        require_production=require_production,
    )
    if not ed25519_verify(
        public,
        payload,
        decode_signature(value["value_base64"], "SIGNED_DOCUMENT_SIGNATURE_INVALID"),
    ):
        fail("SIGNED_DOCUMENT_SIGNATURE_REJECTED", expected_role)
    return signer_id, key_id


def verify_artifacts(
    evidence: dict[str, Any], release_dir: Path, contract: dict[str, Any]
) -> dict[str, tuple[dict[str, Any], Path]]:
    if not release_dir.is_dir() or release_dir.is_symlink():
        fail("RELEASE_DIRECTORY_UNSAFE")
    artifacts = evidence.get("artifacts")
    if not isinstance(artifacts, list):
        fail("RELEASE_ARTIFACT_LIST_REQUIRED")
    by_role: dict[str, tuple[dict[str, Any], Path]] = {}
    declared_paths: set[str] = set()
    for record in artifacts:
        if not isinstance(record, dict) or set(record) != ARTIFACT_FIELDS:
            fail("RELEASE_ARTIFACT_FIELD_SET_MISMATCH")
        role = require_identifier(record["role"], "RELEASE_ARTIFACT_ROLE_INVALID")
        path_value = normalize_path(record["path"])
        if role in by_role:
            fail("DUPLICATE_RELEASE_ARTIFACT_ROLE", role)
        if path_value in declared_paths:
            fail("DUPLICATE_RELEASE_ARTIFACT_PATH", path_value)
        declared_paths.add(path_value)
        path = release_dir / path_value
        try:
            metadata = path.lstat()
        except FileNotFoundError as error:
            raise ReleasePolicyError("RELEASE_ARTIFACT_MISSING", path_value) from error
        if stat.S_ISLNK(metadata.st_mode):
            fail("RELEASE_ARTIFACT_SYMLINK_REJECTED", path_value)
        if not stat.S_ISREG(metadata.st_mode):
            fail("RELEASE_ARTIFACT_NOT_REGULAR", path_value)
        if not isinstance(record["bytes"], int) or record["bytes"] != metadata.st_size:
            fail("RELEASE_ARTIFACT_SIZE_MISMATCH", path_value)
        require_hex(record["sha256"], HEX_64, "RELEASE_ARTIFACT_DIGEST_INVALID")
        if sha256(path.read_bytes()) != record["sha256"]:
            fail("RELEASE_ARTIFACT_DIGEST_MISMATCH", path_value)
        by_role[role] = (record, path)
    required_roles = set(contract["artifact_roles"])
    if set(by_role) != required_roles:
        fail(
            "RELEASE_ARTIFACT_ROLE_SET_MISMATCH",
            json.dumps(
                {
                    "missing": sorted(required_roles - set(by_role)),
                    "extra": sorted(set(by_role) - required_roles),
                },
                sort_keys=True,
            ),
        )
    actual: set[str] = set()
    for root, dirs, files in os.walk(release_dir, followlinks=False):
        root_path = Path(root)
        for directory in dirs:
            if (root_path / directory).is_symlink():
                fail("RELEASE_DIRECTORY_SYMLINK_REJECTED")
        for name in files:
            path = root_path / name
            if path.is_symlink():
                fail("RELEASE_ARTIFACT_SYMLINK_REJECTED")
            actual.add(path.relative_to(release_dir).as_posix())
    if actual != declared_paths:
        fail(
            "RELEASE_ARTIFACT_SET_MISMATCH",
            json.dumps(
                {
                    "missing": sorted(declared_paths - actual),
                    "extra": sorted(actual - declared_paths),
                },
                sort_keys=True,
            ),
        )
    return by_role


def verify_source_identity(value: Any, contract: dict[str, Any], trust: dict[str, Any]) -> dict[str, Any]:
    required = set(contract["source_identity_fields"])
    if not isinstance(value, dict) or set(value) != required:
        fail("RELEASE_SOURCE_IDENTITY_FIELD_SET_MISMATCH")
    repository = value["repository"]
    if repository != trust.get("repository"):
        fail("RELEASE_REPOSITORY_MISMATCH")
    if value["ref"] != contract["release"]["source_ref"]:
        fail("RELEASE_SOURCE_REF_NOT_EXACT_MAIN")
    require_hex(value["commit"], HEX_40, "RELEASE_SOURCE_COMMIT_INVALID")
    require_hex(value["tree"], HEX_40, "RELEASE_SOURCE_TREE_INVALID")
    require_hex(value["tag_object_sha256"], HEX_64, "RELEASE_TAG_OBJECT_DIGEST_INVALID")
    require_identifier(value["source_author_id"], "RELEASE_SOURCE_AUTHOR_ID_INVALID")
    expected_tag = f"{contract['release']['tag_prefix']}{value.get('version', '')}"
    # Version is validated by the top-level object; only prefix is checked here.
    if not isinstance(value["tag"], str) or not value["tag"].startswith(
        contract["release"]["tag_prefix"]
    ):
        fail("RELEASE_TAG_PREFIX_MISMATCH")
    return copy.deepcopy(value)


def verify_artifact_identity(
    value: Any,
    artifacts: dict[str, tuple[dict[str, Any], Path]],
    contract: dict[str, Any],
) -> dict[str, Any]:
    required = set(contract["artifact_identity_fields"])
    if not isinstance(value, dict) or set(value) != required:
        fail("RELEASE_ARTIFACT_IDENTITY_FIELD_SET_MISMATCH")
    for key, item in value.items():
        if key == "image_bytes":
            if not isinstance(item, int) or item < 1:
                fail("RELEASE_IMAGE_BYTES_INVALID")
        else:
            require_hex(item, HEX_64, "RELEASE_ARTIFACT_IDENTITY_DIGEST_INVALID")
    mapping = {
        "os_image": "image_sha256",
        "kernel": "kernel_sha256",
        "initrd": "initrd_sha256",
        "package_lock": "package_lock_sha256",
        "sbom": "sbom_sha256",
        "licenses": "licenses_sha256",
        "provenance": "provenance_sha256",
        "update_metadata": "update_metadata_sha256",
        "recovery_metadata": "recovery_metadata_sha256",
        "d8_hardware_evidence": "d8_hardware_evidence_sha256",
        "governance_evidence": "governance_evidence_sha256",
        "custody_evidence": "custody_evidence_sha256",
        "release_notes": "release_notes_sha256",
        "machine_nonclaims": "machine_nonclaims_sha256",
        "support_policy": "support_policy_sha256",
        "cve_process": "cve_process_sha256",
        "known_limitations": "known_limitations_sha256",
    }
    for role, identity_key in mapping.items():
        if artifacts[role][0]["sha256"] != value[identity_key]:
            fail("RELEASE_ARTIFACT_IDENTITY_MISMATCH", role)
    if artifacts["os_image"][0]["bytes"] != value["image_bytes"]:
        fail("RELEASE_IMAGE_BYTES_MISMATCH")
    return copy.deepcopy(value)


def verify_checks(checks: Any, contract: dict[str, Any], commit: str, created_at: int) -> list[str]:
    if not isinstance(checks, list):
        fail("RELEASE_CHECK_LIST_REQUIRED")
    contexts: list[str] = []
    for check in checks:
        if not isinstance(check, dict) or set(check) != CHECK_FIELDS:
            fail("RELEASE_CHECK_FIELD_SET_MISMATCH")
        context = check["context"]
        if not isinstance(context, str) or not context:
            fail("RELEASE_CHECK_CONTEXT_INVALID")
        if context in contexts:
            fail("DUPLICATE_RELEASE_CHECK_CONTEXT", context)
        contexts.append(context)
        if check["head_sha"] != commit:
            fail("RELEASE_CHECK_HEAD_SHA_MISMATCH", context)
        if check["status"] != "success":
            fail("RELEASE_REQUIRED_CHECK_NOT_SUCCESS", context)
        if not isinstance(check["completed_at_epoch"], int) or check["completed_at_epoch"] > created_at:
            fail("RELEASE_CHECK_TIME_INVALID", context)
    if set(contexts) != set(contract["required_checks"]):
        fail(
            "RELEASE_REQUIRED_CHECK_SET_MISMATCH",
            json.dumps(
                {
                    "missing": sorted(set(contract["required_checks"]) - set(contexts)),
                    "extra": sorted(set(contexts) - set(contract["required_checks"])),
                },
                sort_keys=True,
            ),
        )
    return contexts


def verify_source_approvals(
    approvals: Any,
    *,
    commit: str,
    created_at: int,
    disallowed: set[str],
    minimum: int,
) -> list[str]:
    if not isinstance(approvals, list):
        fail("SOURCE_APPROVAL_LIST_REQUIRED")
    identities: list[str] = []
    for approval in approvals:
        if not isinstance(approval, dict) or set(approval) != SOURCE_APPROVAL_FIELDS:
            fail("SOURCE_APPROVAL_FIELD_SET_MISMATCH")
        reviewer = require_identifier(approval["reviewer_id"], "SOURCE_REVIEWER_ID_INVALID")
        if reviewer in identities:
            fail("DUPLICATE_SOURCE_APPROVER", reviewer)
        identities.append(reviewer)
        if reviewer in disallowed:
            fail("DISALLOWED_SOURCE_APPROVER", reviewer)
        if approval["reviewed_sha"] != commit:
            fail("SOURCE_APPROVAL_SHA_MISMATCH", reviewer)
        if approval["decision"] != "APPROVED" or approval["after_latest_push"] is not True:
            fail("SOURCE_APPROVAL_NOT_CURRENT", reviewer)
        if not isinstance(approval["submitted_at_epoch"], int) or approval["submitted_at_epoch"] > created_at:
            fail("SOURCE_APPROVAL_TIME_INVALID", reviewer)
    if len(identities) < minimum:
        fail("INSUFFICIENT_DISTINCT_SOURCE_APPROVALS")
    return identities


def verify_environment_approvals(
    approvals: Any,
    *,
    release_id: str,
    created_at: int,
    disallowed: set[str],
    minimum: int,
) -> list[str]:
    if not isinstance(approvals, list):
        fail("ENVIRONMENT_APPROVAL_LIST_REQUIRED")
    identities: list[str] = []
    for approval in approvals:
        if not isinstance(approval, dict) or set(approval) != ENVIRONMENT_APPROVAL_FIELDS:
            fail("ENVIRONMENT_APPROVAL_FIELD_SET_MISMATCH")
        approver = require_identifier(
            approval["approver_id"], "ENVIRONMENT_APPROVER_ID_INVALID"
        )
        if approver in identities:
            fail("DUPLICATE_ENVIRONMENT_APPROVER", approver)
        identities.append(approver)
        if approver in disallowed:
            fail("DISALLOWED_ENVIRONMENT_APPROVER", approver)
        if approval["environment"] != "production" or approval["release_id"] != release_id:
            fail("ENVIRONMENT_APPROVAL_SCOPE_MISMATCH", approver)
        if approval["decision"] != "APPROVED":
            fail("ENVIRONMENT_APPROVAL_NOT_APPROVED", approver)
        if not isinstance(approval["approved_at_epoch"], int) or approval["approved_at_epoch"] > created_at:
            fail("ENVIRONMENT_APPROVAL_TIME_INVALID", approver)
    if len(identities) < minimum:
        fail("INSUFFICIENT_DISTINCT_ENVIRONMENT_APPROVALS")
    return identities


def verify_release_signatures(
    evidence: dict[str, Any],
    trust: dict[str, Any],
    *,
    source_author: str,
    promoter: str,
    now_epoch: int,
    require_production: bool,
    contract: dict[str, Any],
) -> tuple[list[str], list[str]]:
    signatures = evidence.get("release_signatures")
    if not isinstance(signatures, list):
        fail("RELEASE_SIGNATURE_LIST_REQUIRED")
    roles: list[str] = []
    signer_ids: list[str] = []
    key_ids: list[str] = []
    payload = release_payload(evidence)
    for signature in signatures:
        if not isinstance(signature, dict) or set(signature) != RELEASE_SIGNATURE_FIELDS:
            fail("RELEASE_SIGNATURE_FIELD_SET_MISMATCH")
        role = signature["role"]
        if role in roles:
            fail("DUPLICATE_RELEASE_SIGNATURE_ROLE", str(role))
        roles.append(role)
        signer_id = require_identifier(signature["signer_id"], "RELEASE_SIGNER_ID_INVALID")
        key_id = require_identifier(signature["key_id"], "RELEASE_SIGNER_KEY_ID_INVALID")
        if signer_id in signer_ids or key_id in key_ids:
            fail("RELEASE_SIGNATURE_IDENTITY_NOT_DISTINCT")
        signer_ids.append(signer_id)
        key_ids.append(key_id)
        if signer_id in {source_author, promoter}:
            fail("SOURCE_AUTHOR_OR_PROMOTER_CANNOT_SIGN_RELEASE", signer_id)
        if signature["algorithm"] != "Ed25519":
            fail("RELEASE_SIGNATURE_ALGORITHM_UNSUPPORTED")
        public = trust_key(
            trust,
            "release_signers",
            signer_id,
            key_id,
            str(role),
            now_epoch=now_epoch,
            require_production=require_production,
        )
        if not ed25519_verify(
            public,
            payload,
            decode_signature(signature["value_base64"], "RELEASE_SIGNATURE_INVALID"),
        ):
            fail("RELEASE_SIGNATURE_REJECTED", str(role))
    required_roles = set(contract["release"]["required_release_signature_roles"])
    if set(roles) != required_roles or len(roles) < contract["release"]["minimum_release_signatures"]:
        fail("RELEASE_SIGNATURE_ROLE_SET_MISMATCH")
    return signer_ids, key_ids


def verify_governance(
    value: dict[str, Any],
    evidence: dict[str, Any],
    trust: dict[str, Any],
    contract: dict[str, Any],
    *,
    source_approvers: list[str],
    environment_approvers: list[str],
    now_epoch: int,
    require_production: bool,
) -> tuple[str, str]:
    if set(value) != GOVERNANCE_FIELDS:
        fail("GOVERNANCE_EVIDENCE_FIELD_SET_MISMATCH")
    if value["schema"] != contract["governance_evidence"]["schema"]:
        fail("GOVERNANCE_EVIDENCE_SCHEMA_MISMATCH")
    source = evidence["source_identity"]
    if value["repository"] != source["repository"]:
        fail("GOVERNANCE_REPOSITORY_MISMATCH")
    if value["main_ref"] != source["ref"] or value["main_sha"] != source["commit"] or value["main_tree"] != source["tree"]:
        fail("GOVERNANCE_EXACT_MAIN_IDENTITY_MISMATCH")
    if value["required_checks"] != contract["required_checks"]:
        fail("GOVERNANCE_REQUIRED_CHECK_SET_MISMATCH")
    if sorted(value["source_approval_ids"]) != sorted(source_approvers):
        fail("GOVERNANCE_SOURCE_APPROVER_SET_MISMATCH")
    if sorted(value["environment_approval_ids"]) != sorted(environment_approvers):
        fail("GOVERNANCE_ENVIRONMENT_APPROVER_SET_MISMATCH")
    required_true = [
        "branch_protected",
        "strict_required_checks",
        "dismiss_stale_approvals",
        "approval_after_latest_push_required",
        "code_owner_review_required",
        "all_conversations_resolved",
        "protected_tag",
    ]
    for key in required_true:
        if value[key] is not True:
            fail("GOVERNANCE_REQUIRED_CONTROL_NOT_ACTIVE", key)
    for key in ["administrator_bypass_allowed", "force_push_allowed", "branch_deletion_allowed"]:
        if value[key] is not False:
            fail("GOVERNANCE_FORBIDDEN_CONTROL_ACTIVE", key)
    if value["protected_environment"] != "production" or value["tag"] != source["tag"]:
        fail("GOVERNANCE_RELEASE_SCOPE_MISMATCH")
    signature = value["signature"]
    return verify_signature_record(
        signature,
        signed_document_payload(value),
        trust,
        group="governance_auditors",
        expected_role="independent_governance_auditor",
        now_epoch=now_epoch,
        require_production=require_production,
    )


def verify_custody(
    value: dict[str, Any],
    evidence: dict[str, Any],
    release_key_ids: list[str],
    trust: dict[str, Any],
    *,
    source_author: str,
    promoter: str,
    now_epoch: int,
    require_production: bool,
    contract: dict[str, Any],
) -> tuple[list[str], tuple[str, str]]:
    if set(value) != CUSTODY_FIELDS:
        fail("CUSTODY_EVIDENCE_FIELD_SET_MISMATCH")
    if value["schema"] != contract["custody_evidence"]["schema"]:
        fail("CUSTODY_EVIDENCE_SCHEMA_MISMATCH")
    if sorted(value["release_key_ids"]) != sorted(release_key_ids):
        fail("CUSTODY_RELEASE_KEY_SET_MISMATCH")
    custodians = value["custodian_ids"]
    if not isinstance(custodians, list) or len(custodians) < contract["custody_evidence"]["minimum_distinct_custodians"]:
        fail("INSUFFICIENT_RELEASE_KEY_CUSTODIANS")
    if len(custodians) != len(set(custodians)) or not all(
        isinstance(item, str) and IDENTIFIER.fullmatch(item) for item in custodians
    ):
        fail("CUSTODIAN_IDENTITY_SET_INVALID")
    if source_author in custodians or promoter in custodians:
        fail("SOURCE_AUTHOR_OR_PROMOTER_CANNOT_CUSTODY_RELEASE_KEY")
    if value["storage"] != "offline_hardware_security_module" or value["dual_control"] is not True:
        fail("OFFLINE_DUAL_CONTROL_CUSTODY_REQUIRED")
    if value["pull_request_workflow_access"] is not False or value["repository_secret_access"] is not False:
        fail("RELEASE_KEY_ONLINE_OR_CI_ACCESS_FORBIDDEN")
    if value["source_author_excluded"] is not True:
        fail("SOURCE_AUTHOR_CUSTODY_EXCLUSION_REQUIRED")
    for key in (
        "rotation_procedure_sha256",
        "revocation_procedure_sha256",
        "disaster_recovery_procedure_sha256",
    ):
        require_hex(value[key], HEX_64, "CUSTODY_PROCEDURE_DIGEST_INVALID")
    auditor = verify_signature_record(
        value["signature"],
        signed_document_payload(value),
        trust,
        group="custody_auditors",
        expected_role="independent_custody_auditor",
        now_epoch=now_epoch,
        require_production=require_production,
    )
    if auditor[0] in {source_author, promoter, *custodians}:
        fail("CUSTODY_AUDITOR_NOT_INDEPENDENT")
    return list(custodians), auditor


def verify_update_metadata(
    value: dict[str, Any],
    evidence: dict[str, Any],
    trust: dict[str, Any],
    *,
    recovery_sha256: str,
    support_sha256: str,
    now_epoch: int,
    require_production: bool,
) -> tuple[str, str]:
    if set(value) != UPDATE_FIELDS or value["schema"] != "trillionnium.desktop.release-update-metadata.v1":
        fail("RELEASE_UPDATE_METADATA_FIELD_SET_OR_SCHEMA_MISMATCH")
    identity = evidence["artifact_identity"]
    if value["release_id"] != evidence["release_id"] or value["version"] != evidence["version"] or value["rollback_index"] != evidence["rollback_index"]:
        fail("RELEASE_UPDATE_VERSION_OR_INDEX_MISMATCH")
    if value["hardware_profile_id"] != evidence["hardware_profile_id"]:
        fail("RELEASE_UPDATE_HARDWARE_PROFILE_MISMATCH")
    if value["image_sha256"] != identity["image_sha256"] or value["image_bytes"] != identity["image_bytes"]:
        fail("RELEASE_UPDATE_IMAGE_IDENTITY_MISMATCH")
    if value["recovery_metadata_sha256"] != recovery_sha256:
        fail("RELEASE_UPDATE_RECOVERY_METADATA_DIGEST_MISMATCH")
    if value["support_policy_sha256"] != support_sha256:
        fail("RELEASE_UPDATE_SUPPORT_POLICY_DIGEST_MISMATCH")
    return verify_signature_record(
        value["signature"],
        signed_document_payload(value),
        trust,
        group="update_signers",
        expected_role="update_metadata_signer",
        now_epoch=now_epoch,
        require_production=require_production,
    )


def verify_recovery_metadata(
    value: dict[str, Any],
    evidence: dict[str, Any],
    trust: dict[str, Any],
    *,
    support_sha256: str,
    now_epoch: int,
    require_production: bool,
) -> tuple[str, str]:
    if set(value) != RECOVERY_FIELDS or value["schema"] != "trillionnium.desktop.release-recovery-metadata.v1":
        fail("RELEASE_RECOVERY_METADATA_FIELD_SET_OR_SCHEMA_MISMATCH")
    if value["release_id"] != evidence["release_id"]:
        fail("RELEASE_RECOVERY_ID_MISMATCH")
    if value["hardware_profile_id"] != evidence["hardware_profile_id"]:
        fail("RELEASE_RECOVERY_HARDWARE_PROFILE_MISMATCH")
    if value["minimum_rollback_index"] != evidence["rollback_index"]:
        fail("RELEASE_RECOVERY_ROLLBACK_INDEX_MISMATCH")
    require_hex(value["recovery_image_sha256"], HEX_64, "RELEASE_RECOVERY_IMAGE_DIGEST_INVALID")
    if value["support_policy_sha256"] != support_sha256:
        fail("RELEASE_RECOVERY_SUPPORT_POLICY_DIGEST_MISMATCH")
    if value["automatic_destructive_recovery"] is not False:
        fail("RELEASE_RECOVERY_AUTOMATIC_DESTRUCTIVE_FORBIDDEN")
    return verify_signature_record(
        value["signature"],
        signed_document_payload(value),
        trust,
        group="recovery_signers",
        expected_role="recovery_metadata_signer",
        now_epoch=now_epoch,
        require_production=require_production,
    )


def verify_d8_binding(value: dict[str, Any], evidence: dict[str, Any], contract: dict[str, Any], require_production: bool) -> None:
    if set(value) != D8_FIELDS or value["schema"] != "trillionnium.desktop.release-d8-binding.v1":
        fail("D8_RELEASE_BINDING_FIELD_SET_OR_SCHEMA_MISMATCH")
    identity = evidence["artifact_identity"]
    if value["qualification_id"] != evidence["d8_qualification_id"]:
        fail("D8_QUALIFICATION_ID_MISMATCH")
    if value["hardware_profile_id"] != evidence["hardware_profile_id"]:
        fail("D8_HARDWARE_PROFILE_MISMATCH")
    mapping = {
        "image_sha256": "image_sha256",
        "kernel_sha256": "kernel_sha256",
        "initrd_sha256": "initrd_sha256",
        "package_lock_sha256": "package_lock_sha256",
        "sbom_sha256": "sbom_sha256",
        "provenance_sha256": "provenance_sha256",
    }
    for d8_key, release_key in mapping.items():
        if value[d8_key] != identity[release_key]:
            fail("D8_RELEASE_ARTIFACT_IDENTITY_MISMATCH", d8_key)
    require_hex(value["verification_receipt_sha256"], HEX_64, "D8_VERIFICATION_RECEIPT_INVALID")
    for key in (
        "critical_failures",
        "uncorrected_data_corruption",
        "unexpected_external_effects",
        "network_policy_bypasses",
    ):
        if value[key] != 0:
            fail("D8_ZERO_TOLERANCE_OUTCOME_VIOLATION", key)
    if value["hardware_beta_promoted"] is not False or value["release_ready"] is not False:
        fail("D8_BINDING_CLAIM_CEILING_WIDENED")
    if require_production:
        if value["status"] != contract["d8_evidence"]["required_status"] or value["policy_eligible"] is not True:
            fail("D8_PHYSICAL_POLICY_ELIGIBILITY_REQUIRED")
        if value["lab_signer_role"] != "independent_hardware_lab":
            fail("D8_INDEPENDENT_LAB_ROLE_REQUIRED")
        if not isinstance(value["duration_seconds"], int) or value["duration_seconds"] < contract["d8_evidence"]["minimum_duration_seconds"]:
            fail("D8_FINAL_STABILITY_DURATION_REQUIRED")
    else:
        if value["status"] not in {"PASS_FIXTURE_FORMAT_ONLY", "PASS_PHYSICAL_POLICY_ELIGIBILITY"}:
            fail("D8_BINDING_STATUS_INVALID")


def verify_document_artifacts(
    evidence: dict[str, Any],
    artifacts: dict[str, tuple[dict[str, Any], Path]],
    contract: dict[str, Any],
    *,
    now_epoch: int,
) -> None:
    sbom = load_json(artifacts["sbom"][1])
    if sbom.get("schema") not in {"spdx-2.3", "cyclonedx-1.6"} or not isinstance(sbom.get("packages"), list) or not sbom["packages"]:
        fail("RELEASE_SBOM_INVALID")
    licenses = load_json(artifacts["licenses"][1])
    if licenses.get("schema") != "trillionnium.desktop.license-report.v1" or not isinstance(licenses.get("packages"), list) or not licenses["packages"]:
        fail("RELEASE_LICENSE_REPORT_INVALID")
    provenance = load_json(artifacts["provenance"][1])
    expected_provenance = {
        "schema",
        "repository",
        "source_commit",
        "source_tree",
        "image_sha256",
        "kernel_sha256",
        "initrd_sha256",
        "package_lock_sha256",
        "sbom_sha256",
        "builder_identity",
        "build_started_at_epoch",
        "build_ended_at_epoch",
    }
    if set(provenance) != expected_provenance or provenance["schema"] != "trillionnium.desktop.release-provenance.v1":
        fail("RELEASE_PROVENANCE_FIELD_SET_OR_SCHEMA_MISMATCH")
    source = evidence["source_identity"]
    identity = evidence["artifact_identity"]
    if provenance["repository"] != source["repository"] or provenance["source_commit"] != source["commit"] or provenance["source_tree"] != source["tree"]:
        fail("RELEASE_PROVENANCE_SOURCE_IDENTITY_MISMATCH")
    for key in ("image_sha256", "kernel_sha256", "initrd_sha256", "package_lock_sha256", "sbom_sha256"):
        if provenance[key] != identity[key]:
            fail("RELEASE_PROVENANCE_ARTIFACT_IDENTITY_MISMATCH", key)
    if not isinstance(provenance["builder_identity"], str) or not provenance["builder_identity"]:
        fail("RELEASE_PROVENANCE_BUILDER_IDENTITY_REQUIRED")
    if not isinstance(provenance["build_started_at_epoch"], int) or not isinstance(provenance["build_ended_at_epoch"], int) or not provenance["build_started_at_epoch"] < provenance["build_ended_at_epoch"] <= now_epoch:
        fail("RELEASE_PROVENANCE_TIME_INVALID")

    support = load_json(artifacts["support_policy"][1])
    required_support = {
        "schema",
        "release_id",
        "supported_until_epoch",
        "security_contact",
        "update_channel",
        "recovery_documentation",
        "minimum_supported_rollback_index",
    }
    if set(support) != required_support or support["schema"] != "trillionnium.desktop.support-policy.v1":
        fail("RELEASE_SUPPORT_POLICY_FIELD_SET_OR_SCHEMA_MISMATCH")
    if support["release_id"] != evidence["release_id"] or support["update_channel"] != evidence["channel"]:
        fail("RELEASE_SUPPORT_POLICY_SCOPE_MISMATCH")
    if not isinstance(support["supported_until_epoch"], int) or support["supported_until_epoch"] <= now_epoch:
        fail("RELEASE_SUPPORT_WINDOW_EXPIRED_OR_MISSING")
    if support["minimum_supported_rollback_index"] != evidence["rollback_index"]:
        fail("RELEASE_SUPPORT_ROLLBACK_INDEX_MISMATCH")
    for key in ("security_contact", "recovery_documentation"):
        if not isinstance(support[key], str) or not support[key]:
            fail("RELEASE_SUPPORT_POLICY_VALUE_MISSING", key)

    cve = load_json(artifacts["cve_process"][1])
    required_cve = {
        "schema",
        "owner_role",
        "advisory_sources",
        "critical_response_hours",
        "high_response_hours",
        "exception_requires_independent_approval",
        "last_reviewed_at_epoch",
        "reviewer_id",
    }
    if set(cve) != required_cve or cve["schema"] != "trillionnium.desktop.cve-process.v1":
        fail("RELEASE_CVE_PROCESS_FIELD_SET_OR_SCHEMA_MISMATCH")
    if cve["owner_role"] != "security_response" or not isinstance(cve["advisory_sources"], list) or not cve["advisory_sources"]:
        fail("RELEASE_CVE_PROCESS_OWNER_OR_SOURCES_INVALID")
    if not isinstance(cve["critical_response_hours"], int) or cve["critical_response_hours"] > 24:
        fail("RELEASE_CVE_CRITICAL_SLA_TOO_WEAK")
    if not isinstance(cve["high_response_hours"], int) or cve["high_response_hours"] > 72:
        fail("RELEASE_CVE_HIGH_SLA_TOO_WEAK")
    if cve["exception_requires_independent_approval"] is not True:
        fail("RELEASE_CVE_EXCEPTION_REVIEW_REQUIRED")
    if not isinstance(cve["last_reviewed_at_epoch"], int) or cve["last_reviewed_at_epoch"] > now_epoch:
        fail("RELEASE_CVE_REVIEW_TIME_INVALID")
    require_identifier(cve["reviewer_id"], "RELEASE_CVE_REVIEWER_ID_INVALID")

    limitations = load_json(artifacts["known_limitations"][1])
    if set(limitations) != {"schema", "limitations"} or limitations["schema"] != "trillionnium.desktop.known-limitations.v1":
        fail("RELEASE_KNOWN_LIMITATIONS_FIELD_SET_OR_SCHEMA_MISMATCH")
    if not isinstance(limitations["limitations"], list) or not limitations["limitations"]:
        fail("RELEASE_KNOWN_LIMITATIONS_REVIEW_REQUIRED")
    for item in limitations["limitations"]:
        if not isinstance(item, dict) or set(item) != {
            "id",
            "severity",
            "description",
            "mitigation",
            "status",
            "reviewer_id",
        }:
            fail("RELEASE_KNOWN_LIMITATION_FIELD_SET_MISMATCH")
        if not all(isinstance(item[key], str) and item[key] for key in item):
            fail("RELEASE_KNOWN_LIMITATION_VALUE_INVALID")


    notes = load_json(artifacts["release_notes"][1])
    required_notes = {
        "schema",
        "release_id",
        "version",
        "summary",
        "security_changes",
        "known_limitations_digest",
        "upgrade_notes",
        "rollback_notes",
    }
    if set(notes) != required_notes or notes["schema"] != "trillionnium.desktop.release-notes.v1":
        fail("RELEASE_NOTES_FIELD_SET_OR_SCHEMA_MISMATCH")
    if notes["release_id"] != evidence["release_id"] or notes["version"] != evidence["version"]:
        fail("RELEASE_NOTES_IDENTITY_MISMATCH")
    if notes["known_limitations_digest"] != evidence["artifact_identity"]["known_limitations_sha256"]:
        fail("RELEASE_NOTES_LIMITATIONS_DIGEST_MISMATCH")
    for key in ("summary", "upgrade_notes", "rollback_notes"):
        if not isinstance(notes[key], str) or not notes[key]:
            fail("RELEASE_NOTES_VALUE_MISSING", key)
    if not isinstance(notes["security_changes"], list):
        fail("RELEASE_NOTES_SECURITY_CHANGES_INVALID")

    nonclaims = load_json(artifacts["machine_nonclaims"][1])
    if nonclaims != {
        "schema": "trillionnium.desktop.release-nonclaims.v1",
        "claims": evidence["machine_nonclaims"],
    }:
        fail("RELEASE_MACHINE_NONCLAIMS_CROSS_ARTIFACT_MISMATCH")
    expected_nonclaims = contract["machine_nonclaims_required"]
    if evidence["machine_nonclaims"] != expected_nonclaims:
        fail("RELEASE_MACHINE_NONCLAIMS_NOT_EXACT_FALSE_SET")


def verify_previous_release(
    previous: dict[str, Any] | None,
    evidence: dict[str, Any],
    trust: dict[str, Any],
    *,
    require_production: bool,
) -> None:
    if previous is None:
        if require_production:
            fail("PREVIOUS_RELEASE_STATE_REQUIRED")
        return
    if set(previous) != PREVIOUS_FIELDS or previous["schema"] != "trillionnium.desktop.previous-release-state.v1":
        fail("PREVIOUS_RELEASE_STATE_FIELD_SET_OR_SCHEMA_MISMATCH")
    if previous["repository"] != trust.get("repository") or previous["channel"] != evidence["channel"]:
        fail("PREVIOUS_RELEASE_STATE_SCOPE_MISMATCH")
    if not isinstance(previous["version"], int) or not isinstance(previous["rollback_index"], int):
        fail("PREVIOUS_RELEASE_VERSION_OR_INDEX_INVALID")
    if evidence["version"] <= previous["version"]:
        fail("RELEASE_VERSION_DOWNGRADE_REJECTED")
    if evidence["rollback_index"] <= previous["rollback_index"]:
        fail("RELEASE_ROLLBACK_INDEX_DOWNGRADE_REJECTED")
    require_hex(previous["release_manifest_sha256"], HEX_64, "PREVIOUS_RELEASE_MANIFEST_DIGEST_INVALID")


def verify_release(
    evidence: dict[str, Any],
    release_dir: Path,
    trust: dict[str, Any],
    contract: dict[str, Any],
    *,
    previous_release: dict[str, Any] | None,
    now_epoch: int,
    require_production: bool,
) -> dict[str, Any]:
    if not isinstance(evidence, dict) or set(evidence) != EVIDENCE_FIELDS:
        fail("RELEASE_EVIDENCE_FIELD_SET_MISMATCH")
    if evidence["schema"] != contract["release"]["evidence_schema"]:
        fail("RELEASE_EVIDENCE_SCHEMA_MISMATCH")
    release_id = require_identifier(evidence["release_id"], "RELEASE_ID_INVALID")
    if evidence["environment_kind"] not in {"fixture", "production_release"}:
        fail("RELEASE_ENVIRONMENT_KIND_INVALID")
    if require_production and evidence["environment_kind"] != "production_release":
        fail("PRODUCTION_RELEASE_EVIDENCE_REQUIRED")
    if evidence["channel"] != contract["release"]["channel"]:
        fail("RELEASE_CHANNEL_MISMATCH")
    if not isinstance(evidence["version"], int) or evidence["version"] < 1:
        fail("RELEASE_VERSION_INVALID")
    if not isinstance(evidence["rollback_index"], int) or evidence["rollback_index"] < 1:
        fail("RELEASE_ROLLBACK_INDEX_INVALID")
    require_identifier(evidence["hardware_profile_id"], "RELEASE_HARDWARE_PROFILE_ID_INVALID")
    require_identifier(evidence["d8_qualification_id"], "RELEASE_D8_QUALIFICATION_ID_INVALID")
    created_at = evidence["created_at_epoch"]
    if not isinstance(created_at, int) or created_at > now_epoch:
        fail("RELEASE_CREATED_AT_INVALID")
    revoked = trust.get("revoked_release_ids")
    if not isinstance(revoked, list) or not all(isinstance(item, str) for item in revoked):
        fail("REVOKED_RELEASE_SET_INVALID")
    if release_id in revoked:
        fail("RELEASE_ID_REVOKED")

    source = verify_source_identity(evidence["source_identity"], contract, trust)
    expected_tag = f"{contract['release']['tag_prefix']}{evidence['version']}"
    if source["tag"] != expected_tag:
        fail("RELEASE_TAG_VERSION_MISMATCH")
    artifacts = verify_artifacts(evidence, release_dir, contract)
    identity = verify_artifact_identity(evidence["artifact_identity"], artifacts, contract)
    source_archive_binding = load_json(artifacts["source_archive"][1])
    if source_archive_binding != {
        "schema": "trillionnium.desktop.release-source-binding.v1",
        "repository": source["repository"],
        "ref": source["ref"],
        "commit": source["commit"],
        "tree": source["tree"],
        "tag": source["tag"],
    }:
        fail("RELEASE_SOURCE_ARCHIVE_IDENTITY_MISMATCH")

    # Validate each local release document before any downstream document
    # consumes its digest. This preserves fail-closed verification while
    # reporting the narrowest corrupt artifact instead of a secondary
    # cross-artifact mismatch.
    verify_document_artifacts(evidence, artifacts, contract, now_epoch=now_epoch)

    promoter = evidence["promoter"]
    if not isinstance(promoter, dict) or set(promoter) != PROMOTER_FIELDS:
        fail("RELEASE_PROMOTER_FIELD_SET_MISMATCH")
    promoter_id = require_identifier(promoter["actor_id"], "RELEASE_PROMOTER_ID_INVALID")
    if promoter["environment"] != "production" or promoter["method"] != "protected_environment":
        fail("RELEASE_PROMOTION_METHOD_OR_ENVIRONMENT_INVALID")
    if promoter["administrator_bypass"] is not False:
        fail("RELEASE_ADMINISTRATOR_BYPASS_FORBIDDEN")
    if not isinstance(promoter["promoted_at_epoch"], int) or not created_at <= promoter["promoted_at_epoch"] <= now_epoch:
        fail("RELEASE_PROMOTER_TIME_INVALID")
    source_author = source["source_author_id"]
    if promoter_id == source_author:
        fail("SOURCE_AUTHOR_CANNOT_PROMOTE_RELEASE")

    checks = verify_checks(evidence["checks"], contract, source["commit"], created_at)
    provisional_disallowed = {source_author, promoter_id}
    source_approvers = verify_source_approvals(
        evidence["source_approvals"],
        commit=source["commit"],
        created_at=created_at,
        disallowed=provisional_disallowed,
        minimum=contract["release"]["minimum_distinct_source_approvers"],
    )
    environment_approvers = verify_environment_approvals(
        evidence["environment_approvals"],
        release_id=release_id,
        created_at=created_at,
        disallowed=provisional_disallowed,
        minimum=contract["release"]["minimum_distinct_environment_approvers"],
    )
    if promoter_id in set(source_approvers) | set(environment_approvers):
        fail("PROMOTER_CANNOT_APPROVE_OWN_RELEASE")

    signer_ids, release_key_ids = verify_release_signatures(
        evidence,
        trust,
        source_author=source_author,
        promoter=promoter_id,
        now_epoch=now_epoch,
        require_production=require_production,
        contract=contract,
    )
    if set(signer_ids) & (set(source_approvers) | set(environment_approvers)):
        fail("RELEASE_SIGNER_CANNOT_BE_SOURCE_OR_ENVIRONMENT_APPROVER")

    governance = load_json(artifacts["governance_evidence"][1])
    governance_auditor = verify_governance(
        governance,
        evidence,
        trust,
        contract,
        source_approvers=source_approvers,
        environment_approvers=environment_approvers,
        now_epoch=now_epoch,
        require_production=require_production,
    )
    custody = load_json(artifacts["custody_evidence"][1])
    custodians, custody_auditor = verify_custody(
        custody,
        evidence,
        release_key_ids,
        trust,
        source_author=source_author,
        promoter=promoter_id,
        now_epoch=now_epoch,
        require_production=require_production,
        contract=contract,
    )
    if governance_auditor[0] in {
        source_author,
        promoter_id,
        *signer_ids,
        *source_approvers,
        *environment_approvers,
        *custodians,
        custody_auditor[0],
    }:
        fail("GOVERNANCE_AUDITOR_NOT_INDEPENDENT")

    support_sha = artifacts["support_policy"][0]["sha256"]
    recovery_sha = artifacts["recovery_metadata"][0]["sha256"]
    recovery = load_json(artifacts["recovery_metadata"][1])
    recovery_signer = verify_recovery_metadata(
        recovery,
        evidence,
        trust,
        support_sha256=support_sha,
        now_epoch=now_epoch,
        require_production=require_production,
    )
    update = load_json(artifacts["update_metadata"][1])
    update_signer = verify_update_metadata(
        update,
        evidence,
        trust,
        recovery_sha256=recovery_sha,
        support_sha256=support_sha,
        now_epoch=now_epoch,
        require_production=require_production,
    )
    disallowed_operators = {
        source_author,
        promoter_id,
        *source_approvers,
        *environment_approvers,
        *signer_ids,
        *custodians,
        governance_auditor[0],
        custody_auditor[0],
    }
    if recovery_signer[0] in disallowed_operators or update_signer[0] in disallowed_operators:
        fail("UPDATE_OR_RECOVERY_SIGNER_NOT_SEPARATED")
    if recovery_signer[0] == update_signer[0] or recovery_signer[1] == update_signer[1]:
        fail("UPDATE_AND_RECOVERY_SIGNERS_NOT_DISTINCT")

    d8 = load_json(artifacts["d8_hardware_evidence"][1])
    verify_d8_binding(d8, evidence, contract, require_production)
    verify_previous_release(
        previous_release, evidence, trust, require_production=require_production
    )

    result: dict[str, Any] = {
        "schema": "trillionnium.desktop.release-promotion-verification-result.v1",
        "status": (
            "PASS_PRODUCTION_POLICY_ELIGIBILITY"
            if require_production
            else "PASS_FIXTURE_FORMAT_ONLY"
        ),
        "release_id": release_id,
        "version": evidence["version"],
        "rollback_index": evidence["rollback_index"],
        "source_commit": source["commit"],
        "source_tree": source["tree"],
        "tag": source["tag"],
        "image_sha256": identity["image_sha256"],
        "required_check_count": len(checks),
        "source_approver_count": len(source_approvers),
        "environment_approver_count": len(environment_approvers),
        "release_signature_roles": contract["release"]["required_release_signature_roles"],
        "policy_eligible": require_production,
        "network_used": False,
        "source_gate_protected_branch_or_tag": False,
        "source_gate_obtained_human_approvals": False,
        "source_gate_accessed_signing_keys": False,
        "source_gate_published_artifacts": False,
        "production_release_promoted": False,
    }
    result["promotion_receipt_sha256"] = sha256(canonical_json(result))
    return result


def verify_promotion_receipt(result: dict[str, Any]) -> None:
    required = {
        "schema",
        "status",
        "release_id",
        "version",
        "rollback_index",
        "source_commit",
        "source_tree",
        "tag",
        "image_sha256",
        "required_check_count",
        "source_approver_count",
        "environment_approver_count",
        "release_signature_roles",
        "policy_eligible",
        "network_used",
        "source_gate_protected_branch_or_tag",
        "source_gate_obtained_human_approvals",
        "source_gate_accessed_signing_keys",
        "source_gate_published_artifacts",
        "production_release_promoted",
        "promotion_receipt_sha256",
    }
    if not isinstance(result, dict) or set(result) != required:
        fail("RELEASE_PROMOTION_RESULT_FIELD_SET_MISMATCH")
    value = copy.deepcopy(result)
    claimed = value.pop("promotion_receipt_sha256")
    if claimed != sha256(canonical_json(value)):
        fail("RELEASE_PROMOTION_RECEIPT_HASH_MISMATCH")
    for key in (
        "network_used",
        "source_gate_protected_branch_or_tag",
        "source_gate_obtained_human_approvals",
        "source_gate_accessed_signing_keys",
        "source_gate_published_artifacts",
        "production_release_promoted",
    ):
        if result[key] is not False:
            fail("RELEASE_SOURCE_GATE_CLAIM_CEILING_WIDENED", key)


def make_key_record(seed: bytes, role: str, production: bool = False) -> tuple[dict[str, Any], bytes]:
    public = ed25519_public_from_seed(seed)
    return (
        {
            "status": "active",
            "role": role,
            "public_key_base64": base64.b64encode(public).decode("ascii"),
            "not_before_epoch": 1,
            "expires_at_epoch": 10**9,
            "production_enrolled": production,
        },
        public,
    )


def sign_document(
    value: dict[str, Any], seed: bytes, signer_id: str, key_id: str
) -> None:
    value["signature"] = {
        "algorithm": "Ed25519",
        "signer_id": signer_id,
        "key_id": key_id,
        "value_base64": base64.b64encode(
            ed25519_sign_fixture(seed, signed_document_payload(value))
        ).decode("ascii"),
    }


def artifact_record(role: str, path: Path, root: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "role": role,
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256(data),
        "bytes": len(data),
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def create_fixture_release(
    contract: dict[str, Any], root: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    root.mkdir(parents=True, exist_ok=True)
    seeds = {
        "artifact-signer": bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"),
        "release-attestor": bytes.fromhex("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb"),
        "governance-auditor": hashlib.sha256(b"governance-auditor-seed").digest(),
        "custody-auditor": hashlib.sha256(b"custody-auditor-seed").digest(),
        "update-signer": hashlib.sha256(b"update-signer-seed").digest(),
        "recovery-signer": hashlib.sha256(b"recovery-signer-seed").digest(),
    }
    key_ids = {
        name: f"{name}-key-1" for name in seeds
    }
    source_commit = hashlib.sha1(b"fixture release commit").hexdigest()
    source_tree = hashlib.sha1(b"fixture release tree").hexdigest()
    release_id = "desktop-release-fixture-1"
    version = 1
    rollback_index = 1
    hardware_profile = "trillionnium-x86_64-reference-appliance-v1"
    image = b"fixture immutable OS image"
    kernel = b"fixture kernel"
    initrd = b"fixture initrd"
    package_lock = b"fixture package lock\n"

    paths: dict[str, Path] = {}
    for role, data in {
        "os_image": image,
        "kernel": kernel,
        "initrd": initrd,
        "package_lock": package_lock,
    }.items():
        path = root / f"{role}.bin"
        path.write_bytes(data)
        paths[role] = path

    source_binding = {
        "schema": "trillionnium.desktop.release-source-binding.v1",
        "repository": "TrillionniumFoundation/trillionnium-os-desktop",
        "ref": "refs/heads/main",
        "commit": source_commit,
        "tree": source_tree,
        "tag": "desktop-v1",
    }
    paths["source_archive"] = root / "source_archive.json"
    write_json(paths["source_archive"], source_binding)

    paths["sbom"] = root / "sbom.json"
    write_json(paths["sbom"], {"schema": "spdx-2.3", "packages": [{"name": "fixture", "version": "1"}]})
    paths["licenses"] = root / "licenses.json"
    write_json(paths["licenses"], {"schema": "trillionnium.desktop.license-report.v1", "packages": [{"name": "fixture", "license": "MIT"}]})
    paths["provenance"] = root / "provenance.json"
    write_json(
        paths["provenance"],
        {
            "schema": "trillionnium.desktop.release-provenance.v1",
            "repository": source_binding["repository"],
            "source_commit": source_commit,
            "source_tree": source_tree,
            "image_sha256": sha256(image),
            "kernel_sha256": sha256(kernel),
            "initrd_sha256": sha256(initrd),
            "package_lock_sha256": sha256(package_lock),
            "sbom_sha256": sha256(paths["sbom"].read_bytes()),
            "builder_identity": "fixture-builder-no-production-authority",
            "build_started_at_epoch": 10,
            "build_ended_at_epoch": 20,
        },
    )
    paths["support_policy"] = root / "support_policy.json"
    write_json(
        paths["support_policy"],
        {
            "schema": "trillionnium.desktop.support-policy.v1",
            "release_id": release_id,
            "supported_until_epoch": 10**9,
            "security_contact": "security@example.invalid",
            "update_channel": "stable",
            "recovery_documentation": "offline fixture documentation",
            "minimum_supported_rollback_index": rollback_index,
        },
    )
    paths["cve_process"] = root / "cve_process.json"
    write_json(
        paths["cve_process"],
        {
            "schema": "trillionnium.desktop.cve-process.v1",
            "owner_role": "security_response",
            "advisory_sources": ["rustsec", "debian-security"],
            "critical_response_hours": 24,
            "high_response_hours": 72,
            "exception_requires_independent_approval": True,
            "last_reviewed_at_epoch": 30,
            "reviewer_id": "security-reviewer-fixture",
        },
    )
    limitations_value = {
        "schema": "trillionnium.desktop.known-limitations.v1",
        "limitations": [
            {
                "id": "fixture-not-production",
                "severity": "blocking",
                "description": "This deterministic fixture is not release evidence.",
                "mitigation": "Run the governed hardware and release process.",
                "status": "open",
                "reviewer_id": "security-reviewer-fixture",
            }
        ],
    }
    paths["known_limitations"] = root / "known_limitations.json"
    write_json(paths["known_limitations"], limitations_value)
    paths["release_notes"] = root / "release_notes.json"
    write_json(
        paths["release_notes"],
        {
            "schema": "trillionnium.desktop.release-notes.v1",
            "release_id": release_id,
            "version": version,
            "summary": "Fixture release-verifier self-test only.",
            "security_changes": [],
            "known_limitations_digest": sha256(paths["known_limitations"].read_bytes()),
            "upgrade_notes": "No production upgrade exists.",
            "rollback_notes": "No production rollback exists.",
        },
    )
    nonclaims = copy.deepcopy(contract["machine_nonclaims_required"])
    paths["machine_nonclaims"] = root / "machine_nonclaims.json"
    write_json(
        paths["machine_nonclaims"],
        {"schema": "trillionnium.desktop.release-nonclaims.v1", "claims": nonclaims},
    )

    recovery = {
        "schema": "trillionnium.desktop.release-recovery-metadata.v1",
        "release_id": release_id,
        "hardware_profile_id": hardware_profile,
        "minimum_rollback_index": rollback_index,
        "recovery_image_sha256": sha256(b"fixture recovery image"),
        "support_policy_sha256": sha256(paths["support_policy"].read_bytes()),
        "automatic_destructive_recovery": False,
        "signature": {},
    }
    sign_document(
        recovery,
        seeds["recovery-signer"],
        "recovery-signer-fixture",
        key_ids["recovery-signer"],
    )
    paths["recovery_metadata"] = root / "recovery_metadata.json"
    write_json(paths["recovery_metadata"], recovery)

    update = {
        "schema": "trillionnium.desktop.release-update-metadata.v1",
        "release_id": release_id,
        "version": version,
        "rollback_index": rollback_index,
        "hardware_profile_id": hardware_profile,
        "image_sha256": sha256(image),
        "image_bytes": len(image),
        "recovery_metadata_sha256": sha256(paths["recovery_metadata"].read_bytes()),
        "support_policy_sha256": sha256(paths["support_policy"].read_bytes()),
        "signature": {},
    }
    sign_document(
        update,
        seeds["update-signer"],
        "update-signer-fixture",
        key_ids["update-signer"],
    )
    paths["update_metadata"] = root / "update_metadata.json"
    write_json(paths["update_metadata"], update)

    d8 = {
        "schema": "trillionnium.desktop.release-d8-binding.v1",
        "status": "PASS_FIXTURE_FORMAT_ONLY",
        "qualification_id": "d8-fixture-qualification",
        "hardware_profile_id": hardware_profile,
        "duration_seconds": 240,
        "policy_eligible": False,
        "lab_signer_role": "fixture_only",
        "image_sha256": sha256(image),
        "kernel_sha256": sha256(kernel),
        "initrd_sha256": sha256(initrd),
        "package_lock_sha256": sha256(package_lock),
        "sbom_sha256": sha256(paths["sbom"].read_bytes()),
        "provenance_sha256": sha256(paths["provenance"].read_bytes()),
        "critical_failures": 0,
        "uncorrected_data_corruption": 0,
        "unexpected_external_effects": 0,
        "network_policy_bypasses": 0,
        "hardware_beta_promoted": False,
        "release_ready": False,
        "verification_receipt_sha256": sha256(b"fixture d8 verification receipt"),
    }
    paths["d8_hardware_evidence"] = root / "d8_hardware_evidence.json"
    write_json(paths["d8_hardware_evidence"], d8)

    source_approvers = ["source-reviewer-1", "source-reviewer-2"]
    environment_approvers = ["environment-reviewer-1", "environment-reviewer-2"]
    governance = {
        "schema": "trillionnium.desktop.release-governance-evidence.v1",
        "repository": source_binding["repository"],
        "main_ref": source_binding["ref"],
        "main_sha": source_commit,
        "main_tree": source_tree,
        "branch_protected": True,
        "strict_required_checks": True,
        "required_checks": contract["required_checks"],
        "source_approval_ids": source_approvers,
        "dismiss_stale_approvals": True,
        "approval_after_latest_push_required": True,
        "code_owner_review_required": True,
        "all_conversations_resolved": True,
        "administrator_bypass_allowed": False,
        "force_push_allowed": False,
        "branch_deletion_allowed": False,
        "protected_environment": "production",
        "environment_approval_ids": environment_approvers,
        "protected_tag": True,
        "tag": source_binding["tag"],
        "signature": {},
    }
    sign_document(
        governance,
        seeds["governance-auditor"],
        "governance-auditor-fixture",
        key_ids["governance-auditor"],
    )
    paths["governance_evidence"] = root / "governance_evidence.json"
    write_json(paths["governance_evidence"], governance)

    custody = {
        "schema": "trillionnium.desktop.release-key-custody.v1",
        "release_key_ids": [key_ids["artifact-signer"], key_ids["release-attestor"]],
        "custodian_ids": ["custodian-fixture-1", "custodian-fixture-2"],
        "storage": "offline_hardware_security_module",
        "dual_control": True,
        "pull_request_workflow_access": False,
        "repository_secret_access": False,
        "source_author_excluded": True,
        "rotation_procedure_sha256": sha256(b"fixture rotation procedure"),
        "revocation_procedure_sha256": sha256(b"fixture revocation procedure"),
        "disaster_recovery_procedure_sha256": sha256(b"fixture disaster recovery procedure"),
        "signature": {},
    }
    sign_document(
        custody,
        seeds["custody-auditor"],
        "custody-auditor-fixture",
        key_ids["custody-auditor"],
    )
    paths["custody_evidence"] = root / "custody_evidence.json"
    write_json(paths["custody_evidence"], custody)

    artifacts = [artifact_record(role, paths[role], root) for role in contract["artifact_roles"]]
    by_role = {item["role"]: item for item in artifacts}
    artifact_identity = {
        "image_sha256": by_role["os_image"]["sha256"],
        "image_bytes": by_role["os_image"]["bytes"],
        "kernel_sha256": by_role["kernel"]["sha256"],
        "initrd_sha256": by_role["initrd"]["sha256"],
        "package_lock_sha256": by_role["package_lock"]["sha256"],
        "sbom_sha256": by_role["sbom"]["sha256"],
        "licenses_sha256": by_role["licenses"]["sha256"],
        "provenance_sha256": by_role["provenance"]["sha256"],
        "update_metadata_sha256": by_role["update_metadata"]["sha256"],
        "recovery_metadata_sha256": by_role["recovery_metadata"]["sha256"],
        "d8_hardware_evidence_sha256": by_role["d8_hardware_evidence"]["sha256"],
        "governance_evidence_sha256": by_role["governance_evidence"]["sha256"],
        "custody_evidence_sha256": by_role["custody_evidence"]["sha256"],
        "release_notes_sha256": by_role["release_notes"]["sha256"],
        "machine_nonclaims_sha256": by_role["machine_nonclaims"]["sha256"],
        "support_policy_sha256": by_role["support_policy"]["sha256"],
        "cve_process_sha256": by_role["cve_process"]["sha256"],
        "known_limitations_sha256": by_role["known_limitations"]["sha256"],
    }
    evidence: dict[str, Any] = {
        "schema": "trillionnium.desktop.release-evidence.v1",
        "release_id": release_id,
        "environment_kind": "fixture",
        "channel": "stable",
        "version": version,
        "rollback_index": rollback_index,
        "hardware_profile_id": hardware_profile,
        "d8_qualification_id": d8["qualification_id"],
        "created_at_epoch": 100,
        "source_identity": {
            "repository": source_binding["repository"],
            "ref": source_binding["ref"],
            "commit": source_commit,
            "tree": source_tree,
            "tag": source_binding["tag"],
            "tag_object_sha256": sha256(b"fixture signed tag object"),
            "source_author_id": "source-author-fixture",
        },
        "artifact_identity": artifact_identity,
        "artifacts": artifacts,
        "checks": [
            {
                "context": context,
                "head_sha": source_commit,
                "status": "success",
                "completed_at_epoch": 90,
            }
            for context in contract["required_checks"]
        ],
        "source_approvals": [
            {
                "reviewer_id": reviewer,
                "reviewed_sha": source_commit,
                "decision": "APPROVED",
                "submitted_at_epoch": 91 + index,
                "after_latest_push": True,
            }
            for index, reviewer in enumerate(source_approvers)
        ],
        "environment_approvals": [
            {
                "approver_id": reviewer,
                "environment": "production",
                "release_id": release_id,
                "decision": "APPROVED",
                "approved_at_epoch": 95 + index,
            }
            for index, reviewer in enumerate(environment_approvers)
        ],
        "promoter": {
            "actor_id": "release-promoter-fixture",
            "environment": "production",
            "method": "protected_environment",
            "administrator_bypass": False,
            "promoted_at_epoch": 110,
        },
        "machine_nonclaims": nonclaims,
        "release_signatures": [],
    }
    for role, name, signer_id in (
        ("artifact_signer", "artifact-signer", "artifact-signer-fixture"),
        ("release_attestor", "release-attestor", "release-attestor-fixture"),
    ):
        evidence["release_signatures"].append(
            {
                "role": role,
                "signer_id": signer_id,
                "key_id": key_ids[name],
                "algorithm": "Ed25519",
                "value_base64": "",
            }
        )
    payload = release_payload(evidence)
    for record, name in zip(
        evidence["release_signatures"], ["artifact-signer", "release-attestor"]
    ):
        record["value_base64"] = base64.b64encode(
            ed25519_sign_fixture(seeds[name], payload)
        ).decode("ascii")

    trust: dict[str, Any] = {
        "schema": "trillionnium.desktop.release-trust.v1",
        "repository": source_binding["repository"],
        "release_signers": {},
        "governance_auditors": {},
        "custody_auditors": {},
        "update_signers": {},
        "recovery_signers": {},
        "revoked_key_ids": [],
        "revoked_release_ids": [],
    }
    group_definitions = [
        ("release_signers", "artifact-signer-fixture", "artifact-signer", "artifact_signer"),
        ("release_signers", "release-attestor-fixture", "release-attestor", "release_attestor"),
        ("governance_auditors", "governance-auditor-fixture", "governance-auditor", "independent_governance_auditor"),
        ("custody_auditors", "custody-auditor-fixture", "custody-auditor", "independent_custody_auditor"),
        ("update_signers", "update-signer-fixture", "update-signer", "update_metadata_signer"),
        ("recovery_signers", "recovery-signer-fixture", "recovery-signer", "recovery_metadata_signer"),
    ]
    for group, actor, seed_name, role in group_definitions:
        record, _public = make_key_record(seeds[seed_name], role, production=False)
        trust[group][actor] = {"keys": {key_ids[seed_name]: record}}

    previous = {
        "schema": "trillionnium.desktop.previous-release-state.v1",
        "repository": source_binding["repository"],
        "channel": "stable",
        "release_id": "desktop-release-fixture-0",
        "version": 0,
        "rollback_index": 0,
        "release_manifest_sha256": sha256(b"fixture previous release"),
    }
    return evidence, trust, previous


def self_test(contract: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        evidence, trust, previous = create_fixture_release(contract, root)
        result = verify_release(
            evidence,
            root,
            trust,
            contract,
            previous_release=previous,
            now_epoch=200,
            require_production=False,
        )
        verify_promotion_receipt(result)
        try:
            verify_release(
                evidence,
                root,
                trust,
                contract,
                previous_release=previous,
                now_epoch=200,
                require_production=True,
            )
        except ReleasePolicyError as error:
            if error.reason != "PRODUCTION_RELEASE_EVIDENCE_REQUIRED":
                raise
        else:
            raise AssertionError("fixture release became production eligible")
    return {
        "schema": "trillionnium.desktop.release-promotion-self-test.v1",
        "status": "PASS_SOURCE_REFERENCE_ONLY",
        "fixture_verification_status": result["status"],
        "fixture_policy_eligible": result["policy_eligible"],
        "source_gate_protected_branch_or_tag": False,
        "source_gate_obtained_human_approvals": False,
        "source_gate_accessed_signing_keys": False,
        "source_gate_published_artifacts": False,
        "production_release_promoted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--evidence", type=Path, required=True)
    verify_parser.add_argument("--release-dir", type=Path, required=True)
    verify_parser.add_argument("--trust", type=Path, required=True)
    verify_parser.add_argument("--previous-release", type=Path)
    verify_parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    verify_parser.add_argument("--now-epoch", type=int, required=True)
    verify_parser.add_argument("--require-production", action="store_true")
    verify_parser.add_argument("--write-result", type=Path)
    self_parser = sub.add_parser("self-test")
    self_parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    self_parser.add_argument("--write-result", type=Path)
    args = parser.parse_args()
    try:
        contract = load_json(args.contract)
        if contract.get("status") != "SOURCE_CANDIDATE_BLOCKED_UPSTREAM_D8":
            fail("D9_CONTRACT_STATUS_WIDENED")
        if args.command == "verify":
            result = verify_release(
                load_json(args.evidence),
                args.release_dir,
                load_json(args.trust),
                contract,
                previous_release=(
                    load_json(args.previous_release)
                    if args.previous_release
                    else None
                ),
                now_epoch=args.now_epoch,
                require_production=args.require_production,
            )
        else:
            result = self_test(contract)
        payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.write_result:
            args.write_result.parent.mkdir(parents=True, exist_ok=True)
            args.write_result.write_text(payload, encoding="utf-8")
        print(payload, end="")
        return 0
    except ReleasePolicyError as error:
        print(
            json.dumps(
                {"status": "REJECTED", "reason": error.reason, "detail": error.detail},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
