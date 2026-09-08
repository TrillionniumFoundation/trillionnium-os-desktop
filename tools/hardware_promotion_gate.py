#!/usr/bin/env python3
"""Strict D8 promotion-policy wrapper over the hardware evidence verifier.

The lower-level verifier validates signatures, exact artifact custody, metrics,
cycles, subsystems, and policy thresholds. This wrapper additionally binds
cross-artifact semantics that must not be asserted independently:

- security `scenario_count` equals the sum of signed category case counts;
- the signed known-limitations artifact equals the top-level signed list;
- the outer decision is itself hash-bound.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from hardware_evidence_verifier import (  # noqa: E402
    HardwareEvidenceError,
    create_fixture_bundle,
    load_json,
    sha256,
    signed_payload,
    verify_evidence,
)
from hardware_verification_receipt import (  # noqa: E402
    verify_hardware_verification_receipt,
)
from trusted_app_bundle import ed25519_sign_fixture  # noqa: E402

CONTRACT_PATH = ROOT / "contracts" / "hardware-beta-qualification.v1.json"


class HardwarePromotionError(ValueError):
    def __init__(self, reason: str, detail: str | None = None) -> None:
        super().__init__(reason if detail is None else f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


def fail(reason: str, detail: str | None = None) -> None:
    raise HardwarePromotionError(reason, detail)


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def artifact_record(evidence: dict[str, Any], role: str) -> dict[str, Any]:
    artifacts = evidence.get("artifacts")
    if not isinstance(artifacts, list):
        fail("D8_ARTIFACT_LIST_REQUIRED")
    matches = [item for item in artifacts if isinstance(item, dict) and item.get("role") == role]
    if len(matches) != 1:
        fail("D8_ARTIFACT_ROLE_CARDINALITY_MISMATCH", role)
    return matches[0]


def artifact_path(evidence: dict[str, Any], evidence_dir: Path, role: str) -> Path:
    record = artifact_record(evidence, role)
    path_value = record.get("path")
    if not isinstance(path_value, str):
        fail("D8_ARTIFACT_PATH_REQUIRED", role)
    return evidence_dir / path_value


def verify_security_case_accounting(
    evidence: dict[str, Any], evidence_dir: Path
) -> dict[str, int]:
    path = artifact_path(evidence, evidence_dir, "security_results")
    value = load_json(path)
    categories = value.get("categories")
    scenario_count = value.get("scenario_count")
    if not isinstance(categories, dict) or not isinstance(scenario_count, int):
        fail("D8_SECURITY_ACCOUNTING_FIELDS_REQUIRED")
    total = 0
    for name, record in categories.items():
        if not isinstance(name, str) or not isinstance(record, dict):
            fail("D8_SECURITY_CATEGORY_INVALID")
        cases = record.get("cases")
        if not isinstance(cases, int) or cases < 1:
            fail("D8_SECURITY_CATEGORY_CASE_COUNT_INVALID", name)
        total += cases
    if scenario_count != total:
        fail(
            "D8_SECURITY_SCENARIO_COUNT_MISMATCH",
            json.dumps(
                {"declared_scenario_count": scenario_count, "category_case_sum": total},
                sort_keys=True,
            ),
        )
    return {"declared_scenario_count": scenario_count, "category_case_sum": total}


def verify_known_limitations_binding(
    evidence: dict[str, Any], evidence_dir: Path
) -> dict[str, Any]:
    path = artifact_path(evidence, evidence_dir, "known_limitations")
    value = load_json(path)
    if set(value) != {"schema", "limitations"}:
        fail("D8_KNOWN_LIMITATIONS_ARTIFACT_FIELD_SET_MISMATCH")
    if value.get("schema") != "trillionnium.desktop.known-limitations.v1":
        fail("D8_KNOWN_LIMITATIONS_ARTIFACT_SCHEMA_MISMATCH")
    limitations = value.get("limitations")
    if limitations != evidence.get("known_limitations"):
        fail("D8_KNOWN_LIMITATIONS_CROSS_ARTIFACT_MISMATCH")
    return {
        "limitation_count": len(limitations),
        "artifact_sha256": sha256(path.read_bytes()),
    }


def verify_gate(
    evidence: dict[str, Any],
    evidence_dir: Path,
    trust: dict[str, Any],
    contract: dict[str, Any],
    *,
    now_epoch: int,
    require_physical: bool,
) -> dict[str, Any]:
    try:
        base = verify_evidence(
            evidence,
            evidence_dir,
            trust,
            contract,
            now_epoch=now_epoch,
            require_physical=require_physical,
        )
    except HardwareEvidenceError:
        raise
    verify_hardware_verification_receipt(base)
    security = verify_security_case_accounting(evidence, evidence_dir)
    limitations = verify_known_limitations_binding(evidence, evidence_dir)
    result: dict[str, Any] = {
        "schema": "trillionnium.desktop.hardware-promotion-policy-result.v1",
        "status": (
            "PASS_PHYSICAL_POLICY_ELIGIBILITY"
            if require_physical
            else "PASS_FIXTURE_FORMAT_ONLY"
        ),
        "qualification_id": evidence["qualification_id"],
        "hardware_profile_id": evidence["hardware_profile_id"],
        "base_verification_receipt_sha256": base["verification_receipt_sha256"],
        "security_case_accounting": security,
        "known_limitations_binding": limitations,
        "policy_eligible": bool(require_physical and base["policy_eligible"]),
        "source_gate_generated_physical_evidence": False,
        "source_gate_enrolled_lab_key": False,
        "hardware_beta_promoted": False,
        "release_ready": False,
    }
    result["gate_receipt_sha256"] = hashlib.sha256(canonical(result)).hexdigest()
    return result


def verify_gate_receipt(result: dict[str, Any]) -> None:
    required = {
        "schema",
        "status",
        "qualification_id",
        "hardware_profile_id",
        "base_verification_receipt_sha256",
        "security_case_accounting",
        "known_limitations_binding",
        "policy_eligible",
        "source_gate_generated_physical_evidence",
        "source_gate_enrolled_lab_key",
        "hardware_beta_promoted",
        "release_ready",
        "gate_receipt_sha256",
    }
    if not isinstance(result, dict) or set(result) != required:
        fail("D8_GATE_RESULT_FIELD_SET_MISMATCH")
    value = copy.deepcopy(result)
    claimed = value.pop("gate_receipt_sha256")
    if claimed != hashlib.sha256(canonical(value)).hexdigest():
        fail("D8_GATE_RECEIPT_HASH_MISMATCH")
    if result["source_gate_generated_physical_evidence"] is not False:
        fail("D8_SOURCE_GATE_MUST_NOT_GENERATE_PHYSICAL_EVIDENCE")
    if result["source_gate_enrolled_lab_key"] is not False:
        fail("D8_SOURCE_GATE_MUST_NOT_ENROLL_LAB_KEY")
    if result["hardware_beta_promoted"] is not False or result["release_ready"] is not False:
        fail("D8_SOURCE_GATE_CLAIM_CEILING_WIDENED")


def prepare_strict_fixture(
    contract: dict[str, Any], root: Path, seed: bytes
) -> tuple[dict[str, Any], dict[str, Any]]:
    evidence, trust = create_fixture_bundle(contract, root, seed)
    limitations_path = artifact_path(evidence, root, "known_limitations")
    limitations_path.write_text(
        json.dumps(
            {
                "schema": "trillionnium.desktop.known-limitations.v1",
                "limitations": evidence["known_limitations"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    record = artifact_record(evidence, "known_limitations")
    data = limitations_path.read_bytes()
    record["sha256"] = sha256(data)
    record["bytes"] = len(data)
    evidence["artifact_identity"]["known_limitations_sha256"] = record["sha256"]
    evidence["signature"]["value_base64"] = base64.b64encode(
        ed25519_sign_fixture(seed, signed_payload(evidence))
    ).decode("ascii")
    return evidence, trust


def self_test(contract: dict[str, Any]) -> dict[str, Any]:
    seed = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        evidence, trust = prepare_strict_fixture(contract, root, seed)
        result = verify_gate(
            evidence,
            root,
            trust,
            contract,
            now_epoch=500,
            require_physical=False,
        )
        verify_gate_receipt(result)
    return {
        "schema": "trillionnium.desktop.hardware-promotion-policy-self-test.v1",
        "status": "PASS_SOURCE_REFERENCE_ONLY",
        "fixture_gate_status": result["status"],
        "fixture_policy_eligible": result["policy_eligible"],
        "security_case_accounting_bound": True,
        "known_limitations_cross_artifact_bound": True,
        "source_gate_generated_physical_evidence": False,
        "source_gate_enrolled_lab_key": False,
        "hardware_beta_promoted": False,
        "release_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--evidence", type=Path, required=True)
    verify_parser.add_argument("--evidence-dir", type=Path, required=True)
    verify_parser.add_argument("--trust", type=Path, required=True)
    verify_parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    verify_parser.add_argument("--now-epoch", type=int, required=True)
    verify_parser.add_argument("--require-physical", action="store_true")
    verify_parser.add_argument("--write-result", type=Path)
    self_parser = sub.add_parser("self-test")
    self_parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    self_parser.add_argument("--write-result", type=Path)
    args = parser.parse_args()
    try:
        contract = load_json(args.contract)
        if args.command == "verify":
            result = verify_gate(
                load_json(args.evidence),
                args.evidence_dir,
                load_json(args.trust),
                contract,
                now_epoch=args.now_epoch,
                require_physical=args.require_physical,
            )
        else:
            result = self_test(contract)
        payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.write_result:
            args.write_result.parent.mkdir(parents=True, exist_ok=True)
            args.write_result.write_text(payload, encoding="utf-8")
        print(payload, end="")
        return 0
    except (HardwareEvidenceError, HardwarePromotionError) as error:
        reason = getattr(error, "reason", error.__class__.__name__)
        detail = getattr(error, "detail", str(error))
        print(
            json.dumps(
                {"status": "REJECTED", "reason": reason, "detail": detail},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
