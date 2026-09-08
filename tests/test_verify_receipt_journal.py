from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_receipt_journal_under_test",
    ROOT / "tools/verify_receipt_journal.py",
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class ReceiptJournalAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        VALIDATOR.ERRORS.clear()

    def test_contract_requires_exact_false_claim_ceiling(self) -> None:
        contract = json.loads(
            (ROOT / "contracts/receipt-journal.v1.json").read_text(encoding="utf-8")
        )
        VALIDATOR.audit_contract(contract)
        self.assertEqual(VALIDATOR.ERRORS, [])

        malformed = json.loads(json.dumps(contract))
        del malformed["claim_ceiling"]["product_ready"]
        VALIDATOR.ERRORS.clear()
        VALIDATOR.audit_contract(malformed)
        self.assertTrue(any("claim_ceiling keys" in error for error in VALIDATOR.ERRORS))

    def test_receipt_schema_accepts_d6_and_historical_d5_only(self) -> None:
        schema = json.loads(
            (ROOT / "contracts/receipt.v1.schema.json").read_text(encoding="utf-8")
        )
        pattern = schema["properties"]["plan_revision"]["pattern"]
        self.assertEqual(pattern, VALIDATOR.RECEIPT_PLAN_REVISION_PATTERN)
        self.assertRegex("2026-08-29-d6", pattern)
        self.assertRegex("2026-08-28-d5", pattern)
        for unsupported in ("2026-08-28-d6", "2026-08-29-d5", "2026-08-27-d4"):
            self.assertIsNone(re.fullmatch(pattern, unsupported))

    def test_receipt_schema_digest_binding_is_current(self) -> None:
        contract = json.loads(
            (ROOT / "contracts/receipt-journal.v1.json").read_text(encoding="utf-8")
        )
        binding = contract["receipt_envelope_schema"]
        self.assertEqual(binding["path"], VALIDATOR.RECEIPT_SCHEMA_RELATIVE)
        self.assertEqual(binding["sha256"], VALIDATOR.RECEIPT_SCHEMA_SHA256)
        VALIDATOR.ERRORS.clear()
        VALIDATOR.audit_contract(contract)
        self.assertEqual(VALIDATOR.ERRORS, [])

    def test_contract_binds_canonical_and_forensic_exports(self) -> None:
        contract = json.loads(
            (ROOT / "contracts/receipt-journal.v1.json").read_text(encoding="utf-8")
        )
        exports = contract["exports"]
        self.assertEqual(exports["public_receipt_envelope"], "export_redacted_jsonl")
        self.assertEqual(
            exports["public_receipt_envelope_schema"],
            "contracts/receipt.v1.schema.json",
        )
        self.assertEqual(
            exports["forensic_lifecycle_export"], "export_journal_redacted_jsonl"
        )
        VALIDATOR.ERRORS.clear()
        malformed = json.loads(json.dumps(contract))
        malformed["exports"]["public_receipt_envelope"] = "export_journal_redacted_jsonl"
        VALIDATOR.audit_contract(malformed)
        self.assertTrue(any("public receipt export" in error for error in VALIDATOR.ERRORS))

    def test_structural_chain_api_and_regressions_are_required(self) -> None:
        source = (ROOT / "crates/hepta-session-core/src/receipt_journal.rs").read_text(
            encoding="utf-8"
        )
        public_api = (ROOT / "crates/hepta-session-core/src/lib.rs").read_text(
            encoding="utf-8"
        )
        chain_source = VALIDATOR.CHAIN_SOURCE.read_text(encoding="utf-8")
        VALIDATOR.audit_source(source, public_api, chain_source, VALIDATOR.BINDING_SOURCE.read_text(encoding="utf-8"), VALIDATOR.BINDING_TESTS.read_text(encoding="utf-8"))
        self.assertEqual(VALIDATOR.ERRORS, [])

        VALIDATOR.ERRORS.clear()
        VALIDATOR.audit_source(source.replace("pub fn inspect_chain", "// pub fn inspect_chain", 1), public_api, chain_source, VALIDATOR.BINDING_SOURCE.read_text(encoding="utf-8"), VALIDATOR.BINDING_TESTS.read_text(encoding="utf-8"))
        self.assertTrue(any("inspect_chain API" in error for error in VALIDATOR.ERRORS))

    def test_chain_helper_must_be_wired_into_both_read_and_write_paths(self) -> None:
        source = VALIDATOR.SOURCE.read_text(encoding="utf-8")
        api = VALIDATOR.PUBLIC_API.read_text(encoding="utf-8")
        chain = VALIDATOR.CHAIN_SOURCE.read_text(encoding="utf-8")
        for token in ("mod chain;", "chain::inspect(paths)", "Self::open_chain_impl([path], None, policy, true)"):
            with self.subTest(token=token):
                self.assertIn(token, source)
                VALIDATOR.ERRORS.clear()
                VALIDATOR.audit_source(source.replace(token, "/* removed */", 1), api, chain, VALIDATOR.BINDING_SOURCE.read_text(encoding="utf-8"), VALIDATOR.BINDING_TESTS.read_text(encoding="utf-8"))
                self.assertTrue(VALIDATOR.ERRORS)

    def test_chain_helper_comparisons_cannot_be_replaced_by_comments(self) -> None:
        source = VALIDATOR.SOURCE.read_text(encoding="utf-8")
        api = VALIDATOR.PUBLIC_API.read_text(encoding="utf-8")
        chain = VALIDATOR.CHAIN_SOURCE.read_text(encoding="utf-8")
        for token in ("previous_segment_sha256 != *previous_digest",
                      "previous_record_sha256 != previous.last_record_sha256",
                      "report.header.journal_id != expected"):
            with self.subTest(token=token):
                self.assertIn(token, chain)
                VALIDATOR.ERRORS.clear()
                VALIDATOR.audit_source(source, api, chain.replace(token, "/* " + token + " */ true"), VALIDATOR.BINDING_SOURCE.read_text(encoding="utf-8"), VALIDATOR.BINDING_TESTS.read_text(encoding="utf-8"))
                self.assertTrue(VALIDATOR.ERRORS)

    def test_chain_helper_must_restore_progress_and_keep_all_bounds(self) -> None:
        source = VALIDATOR.SOURCE.read_text(encoding="utf-8")
        api = VALIDATOR.PUBLIC_API.read_text(encoding="utf-8")
        chain = VALIDATOR.CHAIN_SOURCE.read_text(encoding="utf-8")
        for token in ("validate_reports(&inspected, policy.repair_torn_tail)",
                      "MAX_CHAIN_SEGMENTS", "MAX_CHAIN_BYTES", "MAX_CHAIN_RECORDS", "lock_file(&file)"):
            with self.subTest(token=token):
                self.assertIn(token, chain)
                VALIDATOR.ERRORS.clear()
                VALIDATOR.audit_source(source, api, chain.replace(token, "removed_invariant"), VALIDATOR.BINDING_SOURCE.read_text(encoding="utf-8"), VALIDATOR.BINDING_TESTS.read_text(encoding="utf-8"))
                self.assertTrue(VALIDATOR.ERRORS)

    def test_comments_and_literals_cannot_satisfy_forbidden_authority_check(self) -> None:
        masked = VALIDATOR.mask_rust_non_code(
            '// TcpListener WebDriver std::process::Command\n'
            'let text = "TcpListener WebDriver";\n'
            'fn safe() {}\n'
        )
        self.assertNotIn("TcpListener", masked)
        self.assertNotIn("WebDriver", masked)

    def test_d0c06_generated_artifact_is_historical_and_fail_closed(self) -> None:
        artifact = json.loads(
            (ROOT / VALIDATOR.D0C06_GENERATED_EVIDENCE_RELATIVE).read_text(
                encoding="utf-8"
            )
        )
        VALIDATOR.audit_generated_evidence(artifact)
        self.assertEqual(VALIDATOR.ERRORS, [])
        self.assertEqual(
            artifact["validated_source_head"], VALIDATOR.D0C06_HISTORICAL_SOURCE_HEAD
        )
        self.assertEqual(
            artifact["validated_tree_sha"], VALIDATOR.D0C06_HISTORICAL_TREE_SHA
        )
        self.assertEqual(
            artifact["evidence_lifecycle"], VALIDATOR.D0C06_EVIDENCE_LIFECYCLE
        )
        self.assertIs(artifact["merge_ready"], False)
        self.assertEqual(
            set(artifact["claim_ceiling"]), VALIDATOR.EXPECTED_CLAIM_CEILING
        )
        self.assertTrue(all(value is False for value in artifact["claim_ceiling"].values()))

    def test_d0c06_generated_artifact_rejects_claim_or_hash_drift(self) -> None:
        artifact = json.loads(
            (ROOT / VALIDATOR.D0C06_GENERATED_EVIDENCE_RELATIVE).read_text(
                encoding="utf-8"
            )
        )
        artifact["claim_ceiling"]["product_ready"] = True
        artifact["input_hashes"]["Cargo.lock"] = "0" * 64
        VALIDATOR.audit_generated_evidence(artifact)
        self.assertTrue(
            any("claim_ceiling.product_ready" in error for error in VALIDATOR.ERRORS)
        )
        self.assertTrue(
            any("input_hashes.Cargo.lock" in error for error in VALIDATOR.ERRORS)
        )


    def audit_binding_inputs(self, source=None, chain=None, binding=None, tests=None):
        VALIDATOR.audit_source(
            VALIDATOR.SOURCE.read_text(encoding="utf-8") if source is None else source,
            VALIDATOR.PUBLIC_API.read_text(encoding="utf-8"),
            VALIDATOR.CHAIN_SOURCE.read_text(encoding="utf-8") if chain is None else chain,
            VALIDATOR.BINDING_SOURCE.read_text(encoding="utf-8") if binding is None else binding,
            VALIDATOR.BINDING_TESTS.read_text(encoding="utf-8") if tests is None else tests,
        )

    def test_binding_contract_cannot_omit_fields_or_promote_authenticity(self):
        contract = json.loads(VALIDATOR.CONTRACT.read_text(encoding="utf-8"))
        policy = contract["lifecycle"]["admission_binding"]
        for field in policy["immutable_fields"]:
            with self.subTest(field=field):
                changed = json.loads(json.dumps(contract))
                changed["lifecycle"]["admission_binding"]["immutable_fields"].remove(field)
                VALIDATOR.ERRORS.clear()
                VALIDATOR.audit_contract(changed)
                self.assertIn("receipt immutable admission binding contract drift", VALIDATOR.ERRORS)
        policy["cryptographic_authentication_claim"] = True
        VALIDATOR.ERRORS.clear()
        VALIDATOR.audit_contract(contract)
        self.assertIn("receipt immutable admission binding contract drift", VALIDATOR.ERRORS)

    def test_every_admission_digest_field_must_remain_executable(self):
        original = VALIDATOR.BINDING_SOURCE.read_text(encoding="utf-8")
        for field in VALIDATOR.EXPECTED_ADMISSION_BINDING["immutable_fields"]:
            with self.subTest(field=field):
                token = "event." + field
                self.assertIn(token, original)
                VALIDATOR.ERRORS.clear()
                self.audit_binding_inputs(binding=original.replace(token, "/* " + token + " */ omitted"))
                self.assertIn("admission binding omits immutable " + field, VALIDATOR.ERRORS)

    def test_all_four_parent_paths_require_the_shared_binding(self):
        original = VALIDATOR.SOURCE.read_text(encoding="utf-8")
        positions = [m.start() for m in re.finditer(r"ReceiptProgress::advance", original)]
        self.assertEqual(len(positions), 4)
        for pos in positions:
            with self.subTest(offset=pos):
                changed = original[:pos] + original[pos:].replace("ReceiptProgress::advance", "Unchecked::advance", 1)
                VALIDATOR.ERRORS.clear()
                self.audit_binding_inputs(source=changed)
                self.assertTrue(any("bypasses immutable admission binding" in e for e in VALIDATOR.ERRORS))
        chain = VALIDATOR.CHAIN_SOURCE.read_text(encoding="utf-8")
        VALIDATOR.ERRORS.clear()
        self.audit_binding_inputs(chain=chain.replace("ReceiptProgress::advance", "Unchecked::advance"))
        self.assertTrue(any("chain validation bypasses" in e for e in VALIDATOR.ERRORS))

    def test_binding_equality_and_module_wiring_cannot_be_comments(self):
        binding = VALIDATOR.BINDING_SOURCE.read_text(encoding="utf-8")
        token = "previous.admission_sha256 != admission_sha256"
        self.assertIn(token, binding)
        self.audit_binding_inputs(binding=binding.replace(token, "/* " + token + " */ false"))
        self.assertTrue(any("lost executable validation" in e for e in VALIDATOR.ERRORS))
        for token in ("mod binding;", "mod binding_tests;"):
            VALIDATOR.ERRORS.clear()
            source = VALIDATOR.SOURCE.read_text(encoding="utf-8")
            self.assertIn(token, source)
            self.audit_binding_inputs(source=source.replace(token, "/* " + token + " */"))
            self.assertTrue(VALIDATOR.ERRORS)

    def test_binding_module_cannot_gain_hidden_execution_authority(self):
        binding = VALIDATOR.BINDING_SOURCE.read_text(encoding="utf-8")
        self.audit_binding_inputs(binding=binding + "\nfn hidden() { std::process::Command::new(\"x\"); }\n")
        self.assertIn("receipt journal contains process execution authority", VALIDATOR.ERRORS)

    def test_binding_regressions_cannot_be_removed_or_commented(self):
        tests = VALIDATOR.BINDING_TESTS.read_text(encoding="utf-8")
        token = "fn lifecycle_binding_checks_identity_again_after_reopen"
        self.assertIn(token, tests)
        self.audit_binding_inputs(tests=tests.replace(token, "// " + token))
        self.assertTrue(any("lacks executable" in e for e in VALIDATOR.ERRORS))

    def test_json_inputs_reject_duplicate_keys_and_non_finite_constants(self):
        for text in ('{"a":1,"a":2}', '{"x":{"privacy":true,"privacy":false}}',
                     '{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                VALIDATOR.strict_json(text)
        self.assertEqual(VALIDATOR.strict_json('{"a":{"b":0},"x":[false]}'),
                         {"a":{"b":0},"x":[False]})

    def test_admission_contract_rejects_boolean_integer_aliases(self):
        for key, value in (("disk_format_version", True),
                           ("cryptographic_authentication_claim", 0)):
            contract = json.loads(VALIDATOR.CONTRACT.read_text(encoding="utf-8"))
            contract["lifecycle"]["admission_binding"][key] = value
            VALIDATOR.ERRORS.clear()
            VALIDATOR.audit_contract(contract)
            self.assertIn("receipt immutable admission binding contract drift", VALIDATOR.ERRORS)

if __name__ == "__main__":
    unittest.main()
