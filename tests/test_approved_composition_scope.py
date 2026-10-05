"""Mutation checks for the finite private-scope source profile, not native execution."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools import verify_approved_composition_scope as verifier

ROOT = Path(__file__).resolve().parents[1]


class ApprovedCompositionScopeTests(unittest.TestCase):
    def texts(self):
        paths = set(verifier.EXPECTED["function_token_sha256"]) | set(verifier.EXPECTED["retained_source_sha256"])
        return {path: (ROOT / path).read_text(encoding="utf-8") for path in paths}

    def refuse(self, path, before, after):
        values = self.texts()
        self.assertIn(before, values[path])
        values[path] = values[path].replace(before, after, 1)
        with self.assertRaises(ValueError):
            verifier.check(copy.deepcopy(verifier.EXPECTED), values)

    def test_actual_contract_cli_and_source_correspondence(self):
        verifier.validate(ROOT)
        result = subprocess.run([sys.executable, str(ROOT / "tools/verify_approved_composition_scope.py")],
                                cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["public_cheap_api"])
        self.assertEqual(json.loads(result.stdout)["actual_native_execution"], "PENDING")

    def test_exact_types_unknown_fields_and_source_hash_rebinding_refuse(self):
        mutations = []
        for group, key, values in [
            ("authority", "full_executable_readback_in_scope", [0, True]),
            ("authority", "cross_transaction_executable_cache", [0, True]),
            ("lifetime", "accepted_seconds_maximum", [True, 20.0, 21]),
            ("qualification", "production_ready", [0, True]),
        ]:
            for value in values:
                changed = copy.deepcopy(verifier.EXPECTED)
                changed[group][key] = value
                mutations.append(changed)
        changed = copy.deepcopy(verifier.EXPECTED)
        changed["authority"]["caller_bool_approved"] = False
        mutations.append(changed)
        changed = copy.deepcopy(verifier.EXPECTED)
        changed["function_token_sha256"][verifier.POLICY]["ApprovedRetainedProductConnection::original_scope"] = "0" * 64
        mutations.append(changed)
        for changed in mutations:
            with self.subTest(changed=changed):
                with self.assertRaises(ValueError): verifier.check(changed, self.texts())

    def test_json_duplicate_fields_refuse(self):
        with tempfile.TemporaryDirectory(prefix="approved-composition-contract-") as temporary:
            path = Path(temporary) / "contract.json"
            value = json.dumps(verifier.EXPECTED)
            path.write_text(value.replace('"public_cheap_api": false',
                                          '"public_cheap_api": false, "public_cheap_api": false', 1))
            with self.assertRaises(ValueError): verifier.composition.load(path)

    def test_scope_creator_and_original_root_pair_gate_cannot_be_removed_or_literal_decoyed(self):
        for before, after in [
            ("self.binding.start_session().map_err(approved_error)?;", ""),
            ("self.binding.start_session().map_err(approved_error)?;",
             'let _decoy = "self.binding.start_session().map_err(approved_error)?;";'),
            ("self.binding.start_session().map_err(approved_error)?;",
             "// self.binding.start_session().map_err(approved_error)?;"),
            ("pub(super) fn original_scope", "pub fn original_scope"),
        ]:
            with self.subTest(before=before, after=after): self.refuse(verifier.POLICY, before, after)
        self.refuse(verifier.QUEUE, "    fn original_scope(&self)", "    pub fn original_scope(&self)")
        self.refuse(verifier.QUEUE, "creating(self.owner_pid)?;\n        if let Some(queue)",
                    "if let Some(queue)")

    def test_private_helper_cannot_accept_caller_authority_or_change_borrow(self):
        self.refuse(verifier.POLICY, "pub(super) fn original_scope(&self)",
                    "pub(super) fn original_scope(&self, caller_approved: bool)")
        self.refuse(verifier.QUEUE, "fn original_cancellation(&self)",
                    "fn original_cancellation(&mut self)")

    def test_denial_scope_cannot_gain_action_authority(self):
        self.refuse(verifier.POLICY, "self.binding.start_session().map_err(approved_error)?;",
                    "self.binding.start_session().map_err(approved_error)?; mint_runtime_permit();")
        self.refuse(verifier.QUEUE, "self.original_scope()?;\n        self.connection",
                    "mint_report_permit();\n        self.connection")

    def test_original_scope_still_refuses_queue_retirement_and_clock_drift(self):
        self.refuse(verifier.QUEUE, "queue.current()?;\n        }\n        let current", "}\n        let current")
        # Both public and private paths must retain the same captured Instant.
        self.refuse(verifier.QUEUE, "current != self.original_deadline", "false")
        values = self.texts()
        marker = "    fn original_scope(&self)"
        prefix, body = values[verifier.QUEUE].split(marker, 1)
        body = body.replace("current != self.original_deadline", "false", 1)
        values[verifier.QUEUE] = prefix + marker + body
        with self.assertRaises(ValueError): verifier.check(verifier.EXPECTED, values)

    def test_pre_spawn_full_boundary_cannot_be_dropped(self):
        self.refuse(verifier.QUEUE, "self.deadline()?;\n        worker.thread = Some(", "worker.thread = Some(")

    def test_post_spawn_full_boundary_cannot_be_dropped_or_comment_decoyed(self):
        self.refuse(verifier.QUEUE, "let service = match self.deadline()", "let service = match Ok(())")
        self.refuse(verifier.QUEUE, "let service = match self.deadline()",
                    "// self.deadline()\n        let service = match Ok(())")

    def test_final_constructor_and_queue_full_boundaries_cannot_be_dropped(self):
        self.refuse(verifier.QUEUE, "        self.deadline()?;\n        Ok(value)", "        Ok(value)")
        self.refuse(verifier.QUEUE, "admission.queue = Some(self.state.clone());\n        admission.deadline()?;",
                    "admission.queue = Some(self.state.clone());")

    def test_public_full_getter_and_cancellation_contract_cannot_be_weakened(self):
        self.refuse(verifier.POLICY, ".ensure_control_current()?;\n        self.inner.deadline()",
                    ".ensure_alive()?;\n        self.inner.deadline()")
        self.refuse(verifier.QUEUE, "pub fn cancellation(&self) -> Result<ProductConnectionCancellation, ProductDispatchError> {\n        self.deadline()?;",
                    "pub fn cancellation(&self) -> Result<ProductConnectionCancellation, ProductDispatchError> {\n        self.original_scope()?;")

    def test_real_root_pidfd_and_full_poll_sources_cannot_be_substituted(self):
        for path in verifier.EXPECTED["retained_source_sha256"]:
            with self.subTest(path=path):
                values = self.texts()
                values[path] += "\n// substituted retained custody source\n"
                with self.assertRaises(ValueError): verifier.check(verifier.EXPECTED, values)

    def test_whitespace_and_comments_do_not_mint_missing_helper_or_boundary(self):
        values = self.texts()
        values[verifier.POLICY] += "\n// mint_runtime_permit() has no source authority\n"
        verifier.check(verifier.EXPECTED, values)


if __name__ == "__main__":
    unittest.main()
