"""Finite constructor mutation corpus; no measured native performance claim."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools import verify_approved_constructor_route as verifier

ROOT = Path(__file__).resolve().parents[1]


class ApprovedConstructorRouteTests(unittest.TestCase):
    def texts(self):
        return {path: (ROOT / path).read_text(encoding="utf-8")
                for path in verifier.EXPECTED["whole_source_sha256"]}

    def refuse(self, path, before, after):
        values = self.texts()
        self.assertIn(before, values[path])
        values[path] = values[path].replace(before, after, 1)
        with self.assertRaises(ValueError):
            verifier.check(copy.deepcopy(verifier.EXPECTED), values)

    def test_actual_source_contract_and_cli(self):
        verifier.validate(ROOT)
        result = subprocess.run([sys.executable, str(ROOT / "tools/verify_approved_constructor_route.py")],
                                cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output["public_cheap_api"])
        self.assertFalse(output["installed_activation"])
        self.assertEqual(output["actual_native_execution"], "PENDING")

    def test_unknown_fields_typed_flags_and_hash_rebinding_refuse(self):
        mutations = []
        for group, key, changes in [
            ("authority", "caller_snapshot_or_boolean_authority", [0, True]),
            ("authority", "cross_call_executable_cache", [0, True]),
            ("lifetime", "accepted_seconds_maximum", [True, 20.0, 21]),
            ("qualification", "production_ready", [0, True]),
        ]:
            for value in changes:
                changed = copy.deepcopy(verifier.EXPECTED)
                changed[group][key] = value
                mutations.append(changed)
        changed = copy.deepcopy(verifier.EXPECTED)
        changed["authority"]["caller_prechecked"] = True
        mutations.append(changed)
        changed = copy.deepcopy(verifier.EXPECTED)
        changed["whole_source_sha256"][verifier.MAIN] = "0" * 64
        mutations.append(changed)
        for changed in mutations:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                verifier.check(changed, self.texts())

    def test_duplicate_json_fields_refuse(self):
        with tempfile.TemporaryDirectory(prefix="approved-constructor-contract-") as directory:
            path = Path(directory) / "contract.json"
            text = json.dumps(verifier.EXPECTED)
            path.write_text(text.replace('"default_activation": false',
                                         '"default_activation": false, "default_activation": false', 1))
            with self.assertRaises(ValueError):
                verifier.composition.load(path)

    def test_creator_precedes_original_pair_and_fd_access(self):
        self.refuse(verifier.MAIN,
                    "fn ensure_approved_constructor_scope(\n        &self,",
                    "fn ensure_approved_constructor_scope(\n        &mut self,")
        values = self.texts()
        start = values[verifier.MAIN].index("    fn ensure_approved_constructor_scope(")
        prefix, body = values[verifier.MAIN][:start], values[verifier.MAIN][start:]
        body = body.replace("if self.control.owner_pid != std::process::id()", "if false", 1)
        values[verifier.MAIN] = prefix + body
        with self.assertRaises(ValueError): verifier.check(verifier.EXPECTED, values)

    def test_original_instant_and_cancel_gate_cannot_be_replaced(self):
        self.refuse(verifier.MAIN, "let deadline = self.deadline()?;",
                    "let deadline = Instant::now() + Duration::from_secs(20);")
        self.refuse(verifier.MAIN, "if control.deadline().map_err(control_error)? != deadline",
                    "if false")

    def test_original_control_custody_must_be_present_and_alive(self):
        self.refuse(verifier.MAIN, ".control_verifier()?\n                .ok_or(ProductDispatchError::PeerRefused)?;",
                    ".control_verifier()?.unwrap();")
        self.refuse(verifier.MAIN, "control.ensure_alive().map_err(control_error)?;", "")
        self.refuse(verifier.MAIN, "custodian.ensure_alive().map_err(control_error)?;", "")

    def test_original_agent_pidfd_must_be_alive(self):
        self.refuse(verifier.MAIN, "let deadline = self.deadline()?;\n            self.attested\n                .ensure_alive()",
                    "let deadline = self.deadline()?;\n            self.attested\n                .snapshot()")

    def test_root_thirteen_fields_and_opaque_pair_cannot_be_decoyed(self):
        for after in ["", 'let _decoy = "approved.start_session().map_err(approved_error)?;";',
                      "// approved.start_session().map_err(approved_error)?;"]:
            with self.subTest(after=after):
                self.refuse(verifier.MAIN, "let session = approved.start_session().map_err(approved_error)?;", after)
        self.refuse(verifier.MAIN, ".with_original_pair(&session, |_, attested, custodian, ceiling|",
                    ".with_caller_pair(&session, |_, attested, custodian, ceiling|")

    def test_same_private_factory_binding_cross_checks_both_peer_and_ceiling(self):
        self.refuse(verifier.MAIN, "ceiling != deadline || attested.snapshot() != self.attested.snapshot()",
                    "false")
        self.refuse(verifier.POLICY, "approved: Some(&bootstrap.binding)", "approved: None")

    def test_failed_gate_retires_original_custody(self):
        values = self.texts()
        start = values[verifier.MAIN].index("    fn ensure_approved_constructor_scope(")
        prefix, body = values[verifier.MAIN][:start], values[verifier.MAIN][start:]
        body = body.replace("let _ = custody.revoke();", "let _ = custody;", 1)
        values[verifier.MAIN] = prefix + body
        with self.assertRaises(ValueError): verifier.check(verifier.EXPECTED, values)

    def test_private_gate_cannot_expose_caller_or_mint_effect_permission(self):
        self.refuse(verifier.MAIN, "    fn ensure_approved_constructor_scope(",
                    "    pub fn ensure_approved_constructor_scope(")
        self.refuse(verifier.MAIN, "approved: &hepta_peer_attestation::ApprovedAgentRequestBinding,\n    )",
                    "approved: &hepta_peer_attestation::ApprovedAgentRequestBinding, caller_prechecked: bool,\n    )")
        self.refuse(verifier.MAIN, "let session = approved.start_session().map_err(approved_error)?;",
                    "mint_runtime_permit(); mint_report_permission();\n            let session = approved.start_session().map_err(approved_error)?;")

    def test_legacy_none_full_and_actual_final_full_cannot_be_dropped(self):
        self.refuse(verifier.MAIN,
                    "bootstrap.ensure_approved_constructor_scope(approved)?;\n        } else {\n            bootstrap.ensure_control_current()?;",
                    "bootstrap.ensure_approved_constructor_scope(approved)?;\n        } else {")
        self.refuse(verifier.MAIN, "let observer = actor.receipt_observer(journal, image_id.clone());\n        bootstrap.ensure_control_current()?;",
                    "let observer = actor.receipt_observer(journal, image_id.clone());")
        self.refuse(verifier.MAIN, "actor.principal() != &principal", "false")

    def test_public_wrapper_full_factory_and_other_live_sources_are_preserved(self):
        self.refuse(verifier.POLICY, "bootstrap.deadline()?;\n        let connection", "let connection")
        self.refuse(verifier.POLICY, "attestor: ProcfsPeerAttestor::default()", "attestor: caller_attestor")
        self.refuse("crates/hepta-peer-attestation/src/approved_policy/request_binding.rs",
                    "self.control\n            .ensure_pair_alive(&self.original.verifier())", "self.control\n            .ensure_alive()")


if __name__ == "__main__":
    unittest.main()
