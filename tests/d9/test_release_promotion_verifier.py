from __future__ import annotations

import base64
import copy
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from release_promotion_verifier import (  # noqa: E402
    ReleasePolicyError,
    artifact_record,
    create_fixture_release,
    load_json,
    release_payload,
    sha256,
    sign_document,
    signed_document_payload,
    verify_promotion_receipt,
    verify_release,
)
from trusted_app_bundle import ed25519_sign_fixture  # noqa: E402

SEEDS = {
    "artifact-signer": bytes.fromhex(
        "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
    ),
    "release-attestor": bytes.fromhex(
        "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb"
    ),
    "governance-auditor": __import__("hashlib").sha256(
        b"governance-auditor-seed"
    ).digest(),
    "custody-auditor": __import__("hashlib").sha256(
        b"custody-auditor-seed"
    ).digest(),
    "update-signer": __import__("hashlib").sha256(
        b"update-signer-seed"
    ).digest(),
    "recovery-signer": __import__("hashlib").sha256(
        b"recovery-signer-seed"
    ).digest(),
}

IDENTITY_MAP = {
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


class ReleasePromotionVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(
            (ROOT / "contracts/signed-release-promotion.v1.json").read_text()
        )

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.evidence, self.trust, self.previous = create_fixture_release(
            self.contract, self.root
        )
        self.now_epoch = 200

    def artifact(self, role: str) -> dict:
        return next(item for item in self.evidence["artifacts"] if item["role"] == role)

    def path(self, role: str) -> Path:
        return self.root / self.artifact(role)["path"]

    def resign_release(self) -> None:
        payload = release_payload(self.evidence)
        for record, seed_name in zip(
            self.evidence["release_signatures"],
            ["artifact-signer", "release-attestor"],
        ):
            record["value_base64"] = base64.b64encode(
                ed25519_sign_fixture(SEEDS[seed_name], payload)
            ).decode("ascii")

    def refresh(self, role: str) -> None:
        record = self.artifact(role)
        data = self.path(role).read_bytes()
        record["sha256"] = sha256(data)
        record["bytes"] = len(data)
        if role in IDENTITY_MAP:
            self.evidence["artifact_identity"][IDENTITY_MAP[role]] = record["sha256"]
        if role == "os_image":
            self.evidence["artifact_identity"]["image_bytes"] = record["bytes"]
        self.resign_release()

    def write_json_role(self, role: str, value: dict) -> None:
        self.path(role).write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.refresh(role)

    def read_json_role(self, role: str) -> dict:
        return load_json(self.path(role))

    def resign_document_role(
        self,
        role: str,
        value: dict,
        seed_name: str,
        signer_id: str,
        key_id: str,
    ) -> None:
        sign_document(value, SEEDS[seed_name], signer_id, key_id)
        self.write_json_role(role, value)

    def verify(self, *, require_production: bool = False) -> dict:
        return verify_release(
            self.evidence,
            self.root,
            self.trust,
            self.contract,
            previous_release=self.previous,
            now_epoch=self.now_epoch,
            require_production=require_production,
        )

    def assert_rejected(self, reason: str, callback) -> None:
        with self.assertRaises(ReleasePolicyError) as captured:
            callback()
        self.assertEqual(captured.exception.reason, reason)

    def productionize(self) -> None:
        self.evidence["environment_kind"] = "production_release"
        for group in (
            "release_signers",
            "governance_auditors",
            "custody_auditors",
            "update_signers",
            "recovery_signers",
        ):
            for actor in self.trust[group].values():
                for key in actor["keys"].values():
                    key["production_enrolled"] = True
        d8 = self.read_json_role("d8_hardware_evidence")
        d8.update(
            {
                "status": "PASS_PHYSICAL_POLICY_ELIGIBILITY",
                "duration_seconds": 259200,
                "policy_eligible": True,
                "lab_signer_role": "independent_hardware_lab",
            }
        )
        self.write_json_role("d8_hardware_evidence", d8)
        self.resign_release()

    def test_valid_fixture_is_format_only(self) -> None:
        result = self.verify()
        self.assertEqual(result["status"], "PASS_FIXTURE_FORMAT_ONLY")
        self.assertFalse(result["policy_eligible"])
        self.assertFalse(result["network_used"])
        self.assertFalse(result["source_gate_accessed_signing_keys"])
        self.assertFalse(result["source_gate_published_artifacts"])
        self.assertFalse(result["production_release_promoted"])
        verify_promotion_receipt(result)

    def test_fixture_cannot_become_production_evidence(self) -> None:
        self.assert_rejected(
            "PRODUCTION_RELEASE_EVIDENCE_REQUIRED",
            lambda: self.verify(require_production=True),
        )

    def test_complete_production_policy_shape_is_eligible_but_not_promoted(self) -> None:
        self.productionize()
        result = self.verify(require_production=True)
        self.assertEqual(result["status"], "PASS_PRODUCTION_POLICY_ELIGIBILITY")
        self.assertTrue(result["policy_eligible"])
        self.assertFalse(result["source_gate_protected_branch_or_tag"])
        self.assertFalse(result["source_gate_obtained_human_approvals"])
        self.assertFalse(result["source_gate_accessed_signing_keys"])
        self.assertFalse(result["source_gate_published_artifacts"])
        self.assertFalse(result["production_release_promoted"])
        verify_promotion_receipt(result)

    def test_unknown_top_level_field_is_rejected(self) -> None:
        self.evidence["ambient_release_authority"] = True
        self.assert_rejected("RELEASE_EVIDENCE_FIELD_SET_MISMATCH", self.verify)

    def test_release_signature_tamper_role_and_identity_rules(self) -> None:
        raw = bytearray(
            base64.b64decode(
                self.evidence["release_signatures"][0]["value_base64"]
            )
        )
        raw[0] ^= 1
        self.evidence["release_signatures"][0]["value_base64"] = base64.b64encode(
            raw
        ).decode()
        self.assert_rejected("RELEASE_SIGNATURE_REJECTED", self.verify)

        self.evidence, self.trust, self.previous = create_fixture_release(
            self.contract, self.root
        )
        self.evidence["release_signatures"][1]["role"] = "artifact_signer"
        self.assert_rejected("DUPLICATE_RELEASE_SIGNATURE_ROLE", self.verify)

        self.evidence, self.trust, self.previous = create_fixture_release(
            self.contract, self.root
        )
        self.evidence["release_signatures"][0]["signer_id"] = self.evidence[
            "source_identity"
        ]["source_author_id"]
        self.assert_rejected(
            "SOURCE_AUTHOR_OR_PROMOTER_CANNOT_SIGN_RELEASE", self.verify
        )

    def test_artifact_missing_extra_symlink_size_and_digest_rejected(self) -> None:
        self.path("kernel").unlink()
        self.assert_rejected("RELEASE_ARTIFACT_MISSING", self.verify)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence, trust, previous = create_fixture_release(self.contract, root)
            (root / "extra.txt").write_text("extra\n")
            self.assert_rejected(
                "RELEASE_ARTIFACT_SET_MISMATCH",
                lambda: verify_release(
                    evidence,
                    root,
                    trust,
                    self.contract,
                    previous_release=previous,
                    now_epoch=200,
                    require_production=False,
                ),
            )

        if hasattr(os, "symlink"):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                evidence, trust, previous = create_fixture_release(
                    self.contract, root
                )
                kernel_record = next(
                    item for item in evidence["artifacts"] if item["role"] == "kernel"
                )
                kernel = root / kernel_record["path"]
                real = root / "real-kernel.bin"
                real.write_bytes(kernel.read_bytes())
                kernel.unlink()
                os.symlink(real.name, kernel)
                self.assert_rejected(
                    "RELEASE_ARTIFACT_SYMLINK_REJECTED",
                    lambda: verify_release(
                        evidence,
                        root,
                        trust,
                        self.contract,
                        previous_release=previous,
                        now_epoch=200,
                        require_production=False,
                    ),
                )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence, trust, previous = create_fixture_release(self.contract, root)
            kernel_record = next(
                item for item in evidence["artifacts"] if item["role"] == "kernel"
            )
            kernel = root / kernel_record["path"]
            original = bytearray(kernel.read_bytes())
            original[0] ^= 1
            kernel.write_bytes(original)
            self.assert_rejected(
                "RELEASE_ARTIFACT_DIGEST_MISMATCH",
                lambda: verify_release(
                    evidence,
                    root,
                    trust,
                    self.contract,
                    previous_release=previous,
                    now_epoch=200,
                    require_production=False,
                ),
            )

    def test_exact_main_tag_and_source_archive_binding_required(self) -> None:
        self.evidence["source_identity"]["ref"] = "refs/heads/feature"
        self.resign_release()
        self.assert_rejected("RELEASE_SOURCE_REF_NOT_EXACT_MAIN", self.verify)

        self.evidence, self.trust, self.previous = create_fixture_release(
            self.contract, self.root
        )
        self.evidence["source_identity"]["tag"] = "desktop-v999"
        self.resign_release()
        self.assert_rejected("RELEASE_TAG_VERSION_MISMATCH", self.verify)

        self.evidence, self.trust, self.previous = create_fixture_release(
            self.contract, self.root
        )
        source = self.read_json_role("source_archive")
        source["tree"] = "0" * 40
        self.write_json_role("source_archive", source)
        self.assert_rejected("RELEASE_SOURCE_ARCHIVE_IDENTITY_MISMATCH", self.verify)

    def test_required_checks_are_exact_successful_and_sha_bound(self) -> None:
        self.evidence["checks"][0]["status"] = "failure"
        self.resign_release()
        self.assert_rejected("RELEASE_REQUIRED_CHECK_NOT_SUCCESS", self.verify)

        self.evidence, self.trust, self.previous = create_fixture_release(
            self.contract, self.root
        )
        self.evidence["checks"][0]["head_sha"] = "0" * 40
        self.resign_release()
        self.assert_rejected("RELEASE_CHECK_HEAD_SHA_MISMATCH", self.verify)

        self.evidence, self.trust, self.previous = create_fixture_release(
            self.contract, self.root
        )
        self.evidence["checks"].pop()
        self.resign_release()
        self.assert_rejected("RELEASE_REQUIRED_CHECK_SET_MISMATCH", self.verify)

    def test_source_and_environment_approvals_are_distinct_non_author_current(self) -> None:
        self.evidence["source_approvals"][0]["reviewer_id"] = self.evidence[
            "source_identity"
        ]["source_author_id"]
        self.resign_release()
        self.assert_rejected("DISALLOWED_SOURCE_APPROVER", self.verify)

        self.evidence, self.trust, self.previous = create_fixture_release(
            self.contract, self.root
        )
        self.evidence["source_approvals"][1]["reviewer_id"] = self.evidence[
            "source_approvals"
        ][0]["reviewer_id"]
        self.resign_release()
        self.assert_rejected("DUPLICATE_SOURCE_APPROVER", self.verify)

        self.evidence, self.trust, self.previous = create_fixture_release(
            self.contract, self.root
        )
        self.evidence["source_approvals"][0]["after_latest_push"] = False
        self.resign_release()
        self.assert_rejected("SOURCE_APPROVAL_NOT_CURRENT", self.verify)

        self.evidence, self.trust, self.previous = create_fixture_release(
            self.contract, self.root
        )
        self.evidence["environment_approvals"].pop()
        self.resign_release()
        self.assert_rejected(
            "INSUFFICIENT_DISTINCT_ENVIRONMENT_APPROVALS", self.verify
        )

    def test_source_author_and_promoter_cannot_bypass_or_self_approve(self) -> None:
        self.evidence["promoter"]["actor_id"] = self.evidence[
            "source_identity"
        ]["source_author_id"]
        self.resign_release()
        self.assert_rejected("SOURCE_AUTHOR_CANNOT_PROMOTE_RELEASE", self.verify)

        self.evidence, self.trust, self.previous = create_fixture_release(
            self.contract, self.root
        )
        promoter = self.evidence["promoter"]["actor_id"]
        self.evidence["environment_approvals"][0]["approver_id"] = promoter
        self.resign_release()
        self.assert_rejected("DISALLOWED_ENVIRONMENT_APPROVER", self.verify)

        self.evidence, self.trust, self.previous = create_fixture_release(
            self.contract, self.root
        )
        self.evidence["promoter"]["administrator_bypass"] = True
        self.resign_release()
        self.assert_rejected("RELEASE_ADMINISTRATOR_BYPASS_FORBIDDEN", self.verify)

    def test_release_signer_cannot_also_approve(self) -> None:
        self.evidence["source_approvals"][0][
            "reviewer_id"
        ] = "artifact-signer-fixture"
        self.resign_release()
        self.assert_rejected(
            "RELEASE_SIGNER_CANNOT_BE_SOURCE_OR_ENVIRONMENT_APPROVER",
            self.verify,
        )

    def test_governance_controls_and_auditor_signature_required(self) -> None:
        governance = self.read_json_role("governance_evidence")
        governance["administrator_bypass_allowed"] = True
        self.resign_document_role(
            "governance_evidence",
            governance,
            "governance-auditor",
            "governance-auditor-fixture",
            "governance-auditor-key-1",
        )
        self.assert_rejected("GOVERNANCE_FORBIDDEN_CONTROL_ACTIVE", self.verify)

        self.evidence, self.trust, self.previous = create_fixture_release(
            self.contract, self.root
        )
        governance = self.read_json_role("governance_evidence")
        raw = bytearray(base64.b64decode(governance["signature"]["value_base64"]))
        raw[-1] ^= 1
        governance["signature"]["value_base64"] = base64.b64encode(raw).decode()
        self.write_json_role("governance_evidence", governance)
        self.assert_rejected("SIGNED_DOCUMENT_SIGNATURE_REJECTED", self.verify)

    def test_offline_dual_control_custody_and_ci_exclusion_required(self) -> None:
        custody = self.read_json_role("custody_evidence")
        custody["pull_request_workflow_access"] = True
        self.resign_document_role(
            "custody_evidence",
            custody,
            "custody-auditor",
            "custody-auditor-fixture",
            "custody-auditor-key-1",
        )
        self.assert_rejected(
            "RELEASE_KEY_ONLINE_OR_CI_ACCESS_FORBIDDEN", self.verify
        )

        self.evidence, self.trust, self.previous = create_fixture_release(
            self.contract, self.root
        )
        custody = self.read_json_role("custody_evidence")
        custody["custodian_ids"] = ["custodian-fixture-1"]
        self.resign_document_role(
            "custody_evidence",
            custody,
            "custody-auditor",
            "custody-auditor-fixture",
            "custody-auditor-key-1",
        )
        self.assert_rejected("INSUFFICIENT_RELEASE_KEY_CUSTODIANS", self.verify)

        self.evidence, self.trust, self.previous = create_fixture_release(
            self.contract, self.root
        )
        custody = self.read_json_role("custody_evidence")
        custody["custodian_ids"][0] = self.evidence["source_identity"][
            "source_author_id"
        ]
        self.resign_document_role(
            "custody_evidence",
            custody,
            "custody-auditor",
            "custody-auditor-fixture",
            "custody-auditor-key-1",
        )
        self.assert_rejected(
            "SOURCE_AUTHOR_OR_PROMOTER_CANNOT_CUSTODY_RELEASE_KEY", self.verify
        )

    def test_d8_physical_eligibility_and_artifact_identity_required(self) -> None:
        self.productionize()
        d8 = self.read_json_role("d8_hardware_evidence")
        d8["policy_eligible"] = False
        self.write_json_role("d8_hardware_evidence", d8)
        self.assert_rejected(
            "D8_PHYSICAL_POLICY_ELIGIBILITY_REQUIRED",
            lambda: self.verify(require_production=True),
        )

        self.evidence, self.trust, self.previous = create_fixture_release(
            self.contract, self.root
        )
        d8 = self.read_json_role("d8_hardware_evidence")
        d8["image_sha256"] = "0" * 64
        self.write_json_role("d8_hardware_evidence", d8)
        self.assert_rejected("D8_RELEASE_ARTIFACT_IDENTITY_MISMATCH", self.verify)

    def test_update_and_recovery_metadata_signatures_and_bindings(self) -> None:
        update = self.read_json_role("update_metadata")
        update["version"] += 1
        self.resign_document_role(
            "update_metadata",
            update,
            "update-signer",
            "update-signer-fixture",
            "update-signer-key-1",
        )
        self.assert_rejected("RELEASE_UPDATE_VERSION_OR_INDEX_MISMATCH", self.verify)

        self.evidence, self.trust, self.previous = create_fixture_release(
            self.contract, self.root
        )
        recovery = self.read_json_role("recovery_metadata")
        recovery["automatic_destructive_recovery"] = True
        self.resign_document_role(
            "recovery_metadata",
            recovery,
            "recovery-signer",
            "recovery-signer-fixture",
            "recovery-signer-key-1",
        )
        self.assert_rejected(
            "RELEASE_RECOVERY_AUTOMATIC_DESTRUCTIVE_FORBIDDEN", self.verify
        )

        self.evidence, self.trust, self.previous = create_fixture_release(
            self.contract, self.root
        )
        recovery = self.read_json_role("recovery_metadata")
        raw = bytearray(base64.b64decode(recovery["signature"]["value_base64"]))
        raw[0] ^= 1
        recovery["signature"]["value_base64"] = base64.b64encode(raw).decode()
        self.write_json_role("recovery_metadata", recovery)
        self.assert_rejected("SIGNED_DOCUMENT_SIGNATURE_REJECTED", self.verify)

    def test_update_and_recovery_signer_separation_required(self) -> None:
        update = self.read_json_role("update_metadata")
        sign_document(
            update,
            SEEDS["recovery-signer"],
            "recovery-signer-fixture",
            "recovery-signer-key-1",
        )
        self.write_json_role("update_metadata", update)
        self.trust["update_signers"]["recovery-signer-fixture"] = copy.deepcopy(
            self.trust["recovery_signers"]["recovery-signer-fixture"]
        )
        self.trust["update_signers"]["recovery-signer-fixture"]["keys"][
            "recovery-signer-key-1"
        ]["role"] = "update_metadata_signer"
        self.resign_release()
        self.assert_rejected("UPDATE_AND_RECOVERY_SIGNERS_NOT_DISTINCT", self.verify)

    def test_previous_release_version_and_rollback_must_advance(self) -> None:
        self.previous["version"] = self.evidence["version"]
        self.assert_rejected("RELEASE_VERSION_DOWNGRADE_REJECTED", self.verify)
        self.previous["version"] = 0
        self.previous["rollback_index"] = self.evidence["rollback_index"]
        self.assert_rejected("RELEASE_ROLLBACK_INDEX_DOWNGRADE_REJECTED", self.verify)

    def test_sbom_provenance_support_cve_notes_limitations_and_nonclaims_bound(self) -> None:
        sbom = self.read_json_role("sbom")
        sbom["packages"] = []
        self.write_json_role("sbom", sbom)
        self.assert_rejected("RELEASE_SBOM_INVALID", self.verify)

        self.evidence, self.trust, self.previous = create_fixture_release(
            self.contract, self.root
        )
        provenance = self.read_json_role("provenance")
        provenance["source_commit"] = "0" * 40
        self.write_json_role("provenance", provenance)
        self.assert_rejected("RELEASE_PROVENANCE_SOURCE_IDENTITY_MISMATCH", self.verify)

        self.evidence, self.trust, self.previous = create_fixture_release(
            self.contract, self.root
        )
        support = self.read_json_role("support_policy")
        support["supported_until_epoch"] = 100
        self.write_json_role("support_policy", support)
        self.assert_rejected("RELEASE_SUPPORT_WINDOW_EXPIRED_OR_MISSING", self.verify)

        self.evidence, self.trust, self.previous = create_fixture_release(
            self.contract, self.root
        )
        cve = self.read_json_role("cve_process")
        cve["critical_response_hours"] = 25
        self.write_json_role("cve_process", cve)
        self.assert_rejected("RELEASE_CVE_CRITICAL_SLA_TOO_WEAK", self.verify)

        self.evidence, self.trust, self.previous = create_fixture_release(
            self.contract, self.root
        )
        notes = self.read_json_role("release_notes")
        notes["known_limitations_digest"] = "0" * 64
        self.write_json_role("release_notes", notes)
        self.assert_rejected("RELEASE_NOTES_LIMITATIONS_DIGEST_MISMATCH", self.verify)

        self.evidence, self.trust, self.previous = create_fixture_release(
            self.contract, self.root
        )
        limitations = self.read_json_role("known_limitations")
        limitations["limitations"] = []
        self.write_json_role("known_limitations", limitations)
        self.assert_rejected("RELEASE_KNOWN_LIMITATIONS_REVIEW_REQUIRED", self.verify)

        self.evidence, self.trust, self.previous = create_fixture_release(
            self.contract, self.root
        )
        self.evidence["machine_nonclaims"]["public_agent_listener"] = True
        self.resign_release()
        self.assert_rejected(
            "RELEASE_MACHINE_NONCLAIMS_CROSS_ARTIFACT_MISMATCH", self.verify
        )

    def test_promotion_receipt_tamper_is_rejected(self) -> None:
        result = self.verify()
        tampered = copy.deepcopy(result)
        tampered["required_check_count"] -= 1
        self.assert_rejected(
            "RELEASE_PROMOTION_RECEIPT_HASH_MISMATCH",
            lambda: verify_promotion_receipt(tampered),
        )


if __name__ == "__main__":
    unittest.main()
