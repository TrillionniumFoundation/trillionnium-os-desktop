"""Source mutation checks for private persistence fault instrumentation.

These checks never substitute for the executable host corpus or disk power loss.
"""
from __future__ import annotations

import copy
import json
import re
import unittest

from tests.test_verify_receipt_journal import ROOT, VALIDATOR
from tests.test_agent_port_custody_workflow import trigger_paths


class PersistenceCutAuditTests(unittest.TestCase):
    def setUp(self):
        self.inputs = {
            key: (ROOT / path).read_text(encoding="utf-8")
            for key, path in VALIDATOR.MANAGED_INPUTS.items()
        }
        VALIDATOR.ERRORS.clear()

    def rejects(self, key, old, new):
        inputs = self.inputs.copy()
        self.assertIn(old, inputs[key])
        inputs[key] = inputs[key].replace(old, new, 1)
        VALIDATOR.ERRORS.clear()
        VALIDATOR.audit_managed_source(inputs)
        self.assertTrue(VALIDATOR.ERRORS, (key, old))

    def test_current_source_and_contract(self):
        VALIDATOR.audit_managed_source(self.inputs)
        VALIDATOR.audit_contract(json.loads((ROOT / "contracts/receipt-journal.v1.json").read_text()))
        self.assertEqual(VALIDATOR.ERRORS, [])

    def test_reopen_barrier_steps_cannot_be_omitted_or_errors_ignored(self):
        for old, new in [
            ("guard.stabilize_open(&mut next)?", "guard.verify_current()?"),
            ("next.file.sync_all().map_err(map_io_error)?", "Ok::<(), JournalError>(())?"),
            ("self.directory.sync_all().map_err(map_io_error)?", "Ok::<(), JournalError>(())?"),
            ("next.file.sync_all().map_err(map_io_error)?", "let _ = next.file.sync_all()"),
        ]:
            with self.subTest(old=old):
                self.rejects("managed", old, new)

    def test_reopen_revalidation_is_required_after_sync_not_just_elsewhere(self):
        raw = self.inputs["managed"]
        start = raw.index("fn stabilize_open(")
        end = raw.index("fn publish(", start)
        before, function, after = raw[:start], raw[start:end], raw[end:]
        for token in ["self.verify_current()?", "next.check_live_state()?"]:
            with self.subTest(token=token):
                self.assertEqual(function.count(token), 2)
                pos = function.rindex(token)
                inputs = self.inputs.copy()
                inputs["managed"] = before + function[:pos] + "Ok::<(), JournalError>(())?" + function[pos+len(token):] + after
                VALIDATOR.ERRORS.clear()
                VALIDATOR.audit_managed_source(inputs)
                self.assertTrue(VALIDATOR.ERRORS)

    def test_every_fault_call_requires_its_own_test_cfg(self):
        for key in ["source", "managed", "chain"]:
            matches = list(re.finditer(r'#\[cfg\(test\)\]\s*(?=persistence_tests::)', self.inputs[key]))
            self.assertTrue(matches)
            for match in matches:
                with self.subTest(key=key, offset=match.start()):
                    inputs = self.inputs.copy()
                    inputs[key] = inputs[key][:match.start()] + inputs[key][match.end():]
                    VALIDATOR.ERRORS.clear()
                    VALIDATOR.audit_managed_source(inputs)
                    self.assertTrue(VALIDATOR.ERRORS)

    def test_private_helper_cannot_become_unconditional_or_feature_enabled(self):
        old = "#[cfg(test)]\npub(crate) mod persistence_tests;"
        for new in ["pub(crate) mod persistence_tests;", '#[cfg(feature = "faults")]\npub(crate) mod persistence_tests;']:
            self.rejects("source", old, new)

    def test_custom_harness_registration_and_exact_source_cannot_drift(self):
        for old, new in [
            ("harness = false", "harness = true"),
            ('path = "tests/journal_persistence_process.rs"', 'path = "tests/replacement.rs"'),
            ("[lib]", "[lib]\ntest = false"),
        ]:
            self.rejects("cargo", old, new)
        self.rejects("persistence_process", '#[path = "../src/receipt_journal.rs"]', '#[path = "../copy.rs"]')

    def test_all_frozen_cutpoint_inventory_entries_are_required(self):
        for table in ["ROTATION_CUTS", "INITIALIZATION_CUTS", "REOPEN_CUTS", "APPEND_CUTS", "REPAIR_CUTS"]:
            start = self.inputs["persistence_tests"].index("const " + table)
            end = self.inputs["persistence_tests"].index("];", start)
            for match in re.finditer(r'"[^"\n]+"', self.inputs["persistence_tests"][start:end]):
                inputs = self.inputs.copy()
                pos = start + match.start()
                stop = start + match.end()
                inputs["persistence_tests"] = inputs["persistence_tests"][:pos] + '"removed"' + inputs["persistence_tests"][stop:]
                VALIDATOR.ERRORS.clear()
                VALIDATOR.audit_managed_source(inputs)
                self.assertTrue(VALIDATOR.ERRORS, (table, match.group()))

    def test_sigkill_must_be_observed_and_checkpoint_bounded(self):
        for old, new in [
            ("child.0.kill().unwrap()", "()"),
            ("child.0.wait().unwrap().signal()", "Some(9)"),
            ("Instant::now() < deadline", "true"),
            ("Duration::from_secs(10)", "Duration::from_secs(1000)"),
            ("        64,\n", "        1,\n"),
        ]:
            with self.subTest(old=old):
                self.rejects("persistence_process", old, new)

    def test_fault_corpus_cannot_promote_hardware_or_enable_replay(self):
        original = json.loads((ROOT / "contracts/receipt-journal.v1.json").read_text())
        for field, value in [
            ("process_cut_cases", True), ("injected_io_case_combinations", 0),
            ("physical_power_loss_qualified", True),
            ("in_kernel_syscall_interruption_qualified", True),
            ("automatic_replay_available", True),
        ]:
            contract = copy.deepcopy(original)
            contract["managed_store"]["persistence_fault_corpus"][field] = value
            VALIDATOR.ERRORS.clear()
            VALIDATOR.audit_contract(contract)
            self.assertTrue(any("managed receipt" in item for item in VALIDATOR.ERRORS))

    def test_workflow_runs_unit_and_process_matrices_without_filtering_process_target(self):
        workflow = (ROOT / ".github/workflows/receipt-journal.yml").read_text()
        commands = [line.strip() for line in workflow.splitlines() if line.strip().startswith("cargo test")]
        self.assertIn("cargo test --locked -p hepta-session-core --lib receipt_journal::persistence_tests:: -- --nocapture", commands)
        self.assertIn("cargo test --locked -p hepta-session-core --test journal_persistence_process", commands)
        for command in commands:
            if "receipt_journal::" in command:
                self.assertIn("--lib", command)
        gates = json.loads((ROOT / "manifests/gates.v1.json").read_text())
        inputs = set(next(g for g in gates["gates"] if g["id"] == "D0C-06")["invalidation_paths"])
        for path in ["docs/architecture/RECEIPT_PERSISTENCE_FAULT_MODEL.md", "tests/test_receipt_persistence_cuts.py"]:
            self.assertIn(path, inputs)
            for event in ["push", "pull_request"]:
                self.assertIn(path, trigger_paths(workflow, event))


if __name__ == "__main__":
    unittest.main()
