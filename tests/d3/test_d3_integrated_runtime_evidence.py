from __future__ import annotations

import base64
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
SPEC = importlib.util.spec_from_file_location(
    "d3_integrated_runtime_verifier",
    ROOT / "tools" / "verify_d3_integrated_runtime_evidence.py",
)
assert SPEC is not None and SPEC.loader is not None
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)
from trusted_app_bundle import (  # noqa: E402
    canonical_json,
    ed25519_public_from_seed,
    ed25519_sign_fixture,
)


class D3IntegratedRuntimeEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.contract_path = ROOT / "contracts" / "d3-integrated-runtime-evidence.v1.json"
        self.contract = VERIFIER.load_json(self.contract_path)
        self.evidence_path, self.artifact_root = VERIFIER.build_source_fixture(
            self.root, self.contract
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def read_evidence(self) -> dict:
        return json.loads(self.evidence_path.read_text(encoding="utf-8"))

    def write_evidence(self, evidence: dict) -> None:
        self.evidence_path.write_bytes(canonical_json(evidence))

    def verify(self, **kwargs: object) -> dict:
        return VERIFIER.verify_evidence(
            self.evidence_path,
            self.artifact_root,
            contract_path=self.contract_path,
            **kwargs,
        )

    def assert_reason(self, reason: str, **kwargs: object) -> None:
        with self.assertRaises(VERIFIER.EvidenceError) as captured:
            self.verify(**kwargs)
        self.assertEqual(captured.exception.reason, reason)

    def test_source_fixture_proves_verifier_only(self) -> None:
        result = self.verify()
        self.assertEqual(result["status"], "PASS_SOURCE_VERIFIER_ONLY")
        self.assertEqual(result["artifact_count"], 3)
        self.assertGreaterEqual(result["runtime_case_count"], 25)
        self.assertEqual(result["receipt_chain_count"], 2)
        self.assertEqual(result["verified_attestation_count"], 0)
        self.assertFalse(result["promotion_eligible"])
        self.assertFalse(result["promotion_authoritative"])

    def test_duplicate_json_members_fail_closed(self) -> None:
        self.evidence_path.write_text('{"schema":"a","schema":"b"}\n', encoding="utf-8")
        with self.assertRaises(VERIFIER.EvidenceError) as captured:
            VERIFIER.load_json(self.evidence_path)
        self.assertEqual(captured.exception.reason, "DUPLICATE_JSON_MEMBER")

    def test_artifact_tamper_and_extra_file_are_rejected(self) -> None:
        target = self.artifact_root / "browser-runtime.json"
        target.write_text('{"tampered":true}\n', encoding="utf-8")
        self.assert_reason("ARTIFACT_DIGEST_OR_SIZE_MISMATCH")
        target.write_bytes(b'{"fixture":true,"servo_owned":true}\n')
        (self.artifact_root / "undeclared.txt").write_text("extra", encoding="utf-8")
        self.assert_reason("ARTIFACT_DIRECTORY_SET_MISMATCH")

    def test_principal_dispatch_drift_and_dead_pidfd_are_rejected(self) -> None:
        evidence = self.read_evidence()
        evidence["principal"]["dispatch"]["start_time_ticks"] += 1
        self.write_evidence(evidence)
        self.assert_reason("PRINCIPAL_DISPATCH_DRIFT")

        evidence = self.read_evidence()
        evidence["principal"]["dispatch"] = copy.deepcopy(
            evidence["principal"]["admission"]
        )
        evidence["principal"]["admission"]["pidfd_alive"] = False
        evidence["principal"]["dispatch"]["pidfd_alive"] = False
        self.write_evidence(evidence)
        self.assert_reason("PIDFD_LIVENESS_REQUIRED")

    def test_semantic_fallback_action_count_and_epoch_are_rejected(self) -> None:
        for field, value, reason in (
            ("coordinate_fallback", True, "SEMANTIC_ACTION_COORDINATE_FALLBACK_FORBIDDEN"),
            ("action_count", 2, "EXACTLY_ONE_ACTION_REQUIRED"),
            ("mutation_epoch_after", 9, "MUTATION_EPOCH_MUST_ADVANCE_ONCE"),
            ("servo_owned_adapter", False, "SEMANTIC_ACTION_SERVO_OWNED_ADAPTER_REQUIRED"),
        ):
            with self.subTest(field=field):
                evidence = self.read_evidence()
                evidence["semantic_action"][field] = value
                self.write_evidence(evidence)
                self.assert_reason(reason)
                self.evidence_path, self.artifact_root = VERIFIER.build_source_fixture(
                    self.root, self.contract
                )

    def test_runtime_case_omission_and_wrong_outcome_are_rejected(self) -> None:
        evidence = self.read_evidence()
        evidence["cases"].pop("ambiguous_target")
        self.write_evidence(evidence)
        self.assert_reason("RUNTIME_CASE_SET_MISMATCH")

        self.evidence_path, self.artifact_root = VERIFIER.build_source_fixture(
            self.root, self.contract
        )
        evidence = self.read_evidence()
        evidence["cases"]["wrong_uid"] = "admitted"
        self.write_evidence(evidence)
        self.assert_reason("RUNTIME_CASE_OUTCOME_MISMATCH")

    def test_receipt_mutation_and_automatic_replay_are_rejected(self) -> None:
        evidence = self.read_evidence()
        evidence["receipts"]["chains"][0]["records"][1]["record_hash"] = "f" * 64
        self.write_evidence(evidence)
        self.assert_reason("RECEIPT_HASH_MISMATCH")

        self.evidence_path, self.artifact_root = VERIFIER.build_source_fixture(
            self.root, self.contract
        )
        evidence = self.read_evidence()
        evidence["receipts"]["automatic_replay"] = True
        self.write_evidence(evidence)
        self.assert_reason("AUTOMATIC_REPLAY_FORBIDDEN")

    def test_product_authority_widening_is_rejected(self) -> None:
        for field in (
            "production_agent_port_enabled",
            "external_effect_authority",
            "external_network_enabled",
            "hardware_qualified",
            "signing_key_custody",
            "release_ready",
        ):
            with self.subTest(field=field):
                evidence = self.read_evidence()
                evidence["product_boundaries"][field] = True
                self.write_evidence(evidence)
                self.assert_reason(f"BOUNDARY_{field.upper()}_MUST_BE_FALSE")
                self.evidence_path, self.artifact_root = VERIFIER.build_source_fixture(
                    self.root, self.contract
                )

    def test_exact_main_requires_identity_and_keyring(self) -> None:
        self.assert_reason("EXACT_MAIN_REF_REQUIRED", require_exact_main=True)
        evidence = self.read_evidence()
        evidence["source"].update(
            {
                "ref": "refs/heads/main",
                "head_sha": "1" * 40,
                "tested_sha": "1" * 40,
                "integrated_main_sha": "1" * 40,
                "fixture_evidence": False,
            }
        )
        self.write_evidence(evidence)
        self.assert_reason("KEYRING_REQUIRED_FOR_EXACT_MAIN", require_exact_main=True)

    def test_two_distinct_ed25519_roles_validate_exact_main(self) -> None:
        evidence = self.read_evidence()
        evidence["source"].update(
            {
                "ref": "refs/heads/main",
                "head_sha": "1" * 40,
                "tested_sha": "1" * 40,
                "integrated_main_sha": "1" * 40,
                "fixture_evidence": False,
            }
        )
        roles = list(self.contract["required_operator_roles"])
        seeds = [bytes(range(32)), bytes(reversed(range(32)))]
        key_records = []
        attestations = []
        evidence["attestations"] = []
        payload = VERIFIER.attestation_payload(evidence)
        for index, (role, seed) in enumerate(zip(roles, seeds, strict=True), 1):
            key_id = f"d3-key-{index}"
            identity = f"independent-person-{index}"
            public_key = ed25519_public_from_seed(seed)
            signature = ed25519_sign_fixture(seed, payload)
            key_records.append(
                {
                    "key_id": key_id,
                    "identity": identity,
                    "role": role,
                    "public_key_base64": base64.b64encode(public_key).decode("ascii"),
                    "production_enrolled": True,
                }
            )
            attestations.append(
                {
                    "key_id": key_id,
                    "identity": identity,
                    "role": role,
                    "signature_base64": base64.b64encode(signature).decode("ascii"),
                }
            )
        evidence["attestations"] = attestations
        self.write_evidence(evidence)
        keyring_path = self.root / "keyring.json"
        keyring_path.write_bytes(
            canonical_json(
                {
                    "schema": "trillionnium.desktop.d3-attestation-keyring.v1",
                    "keys": key_records,
                }
            )
        )
        result = self.verify(keyring_path=keyring_path, require_exact_main=True)
        self.assertEqual(result["status"], "PASS_D3_EXACT_MAIN_EVIDENCE")
        self.assertEqual(result["verified_attestation_count"], 2)
        self.assertTrue(result["promotion_eligible"])
        self.assertFalse(result["promotion_authoritative"])

        evidence = self.read_evidence()
        signature = base64.b64decode(evidence["attestations"][0]["signature_base64"])
        evidence["attestations"][0]["signature_base64"] = base64.b64encode(
            bytes([signature[0] ^ 1]) + signature[1:]
        ).decode("ascii")
        self.write_evidence(evidence)
        self.assert_reason(
            "ATTESTATION_SIGNATURE_INVALID",
            keyring_path=keyring_path,
            require_exact_main=True,
        )

    def test_artifact_symlink_is_rejected(self) -> None:
        target = self.artifact_root / "browser-runtime.json"
        backup = self.root / "outside.json"
        backup.write_bytes(target.read_bytes())
        target.unlink()
        try:
            target.symlink_to(backup)
        except OSError:
            self.skipTest("symlinks unavailable")
        self.assert_reason("UNSAFE_FILE_TYPE")


if __name__ == "__main__":
    unittest.main()
