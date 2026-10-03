"""Finite source mutation tests, not actual compilation, kernel or health."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools import verify_approved_service_request as gate

ROOT = Path(__file__).resolve().parents[1]
TRANSPORT = "crates/hepta-agent-transport/src/accepted_handoff/retained_control/service_control.rs"
BRIDGE = "crates/hepta-peer-attestation/src/approved_policy/service_policy/request_bridge.rs"
ROOTED = "crates/hepta-peer-attestation/src/control_owner/root_path/service_request.rs"
PACKING = "crates/hepta-peer-attestation/src/control_owner/retained_request/service_request.rs"


class ApprovedServiceRequestTests(unittest.TestCase):
    def texts(self):
        return gate.inputs(ROOT)

    def mutate_order(self, path, before, after=""):
        values = self.texts()
        self.assertIn(before, values[path])
        values[path] = values[path].replace(before, after, 1)
        # Test the complete finite body/order inventory independently of hashes.
        with self.assertRaises(ValueError):
            gate.inventory_and_orders(values)
        with self.assertRaises(ValueError):
            gate.check(copy.deepcopy(gate.EXPECTED), values)

    def test_current_complete_source_contract_and_payload_free_cli(self):
        gate.check(copy.deepcopy(gate.EXPECTED), self.texts())
        result = subprocess.run([sys.executable, "tools/verify_approved_service_request.py"],
                                cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["scope"], "P1_SOURCE_ONLY")
        self.assertEqual(report["public_methods"], 17)
        for key in ("actual_kernel", "native_health", "installed", "production_ready"):
            self.assertIs(report[key], False)

    def test_duplicate_json_fields_and_unknown_fields_refuse(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            path.write_text('{"status":"x","status":"x"}')
            with self.assertRaises(ValueError): gate.source_gate.load(path)
        value = copy.deepcopy(gate.EXPECTED); value["caller_approval"] = True
        with self.assertRaises(ValueError): gate.check(value, self.texts())

    def test_typed_flags_cannot_be_rebound_into_runtime_claims(self):
        for group, key, replacement in [("execution", "kernel", True),
                ("non_claims", "production_ready", True),
                ("kernel_corpus", "groups", True),
                ("kernel_corpus", "request_seconds_maximum", 21)]:
            value = copy.deepcopy(gate.EXPECTED)
            if key not in value[group]:
                # All arbitrary fields are closed as well as existing flags.
                value[group][key] = replacement
            else: value[group][key] = replacement
            with self.subTest(group=group, key=key), self.assertRaises(ValueError):
                gate.check(value, self.texts())

    def test_every_current_parent_insertion_restores_exact_whole_bytes(self):
        for path, rule in gate.EXPECTED["original_source_inverse"].items():
            current = self.texts()[path]
            parent = gate.parent_source(path, current)
            self.assertEqual(len(parent.encode()), rule["parent_bytes"])
            self.assertEqual(hashlib.sha256(parent.encode()).hexdigest(), rule["parent_sha256"])
            self.assertEqual(gate.parent_source(path, parent), parent)
            with self.subTest(path=path), self.assertRaises(ValueError):
                gate.parent_source(path, current + "\n")

    def test_detached_normalized_old_input_cannot_qualify_current_profile(self):
        for path in gate.EXPECTED["original_source_inverse"]:
            values = self.texts(); values[path] = gate.parent_source(path, values[path])
            with self.subTest(path=path), self.assertRaises(ValueError):
                gate.check(copy.deepcopy(gate.EXPECTED), values)

    def test_wrong_position_duplicate_and_rewritten_insertions_refuse(self):
        for path, rule in gate.EXPECTED["original_source_inverse"].items():
            if rule.get("kind") == "exact_plumbing": continue
            current = self.texts()[path]; block = rule["block"]
            parent = gate.parent_source(path, current)
            for value in (block + parent, current + block, current.replace(block, block + " ", 1)):
                with self.subTest(path=path), self.assertRaises(ValueError): gate.parent_source(path, value)

    def test_original_foundation_checker_four_reader_steps_are_closed(self):
        path = "tools/verify_approved_service_owner.py"
        rule = gate.EXPECTED["original_source_inverse"][path]
        self.assertEqual(len(rule["steps"]), 4)
        current = self.texts()[path]
        for step in rule["steps"]:
            for value in (current.replace(step["actual"], step["parent"], 1), current + step["actual"]):
                with self.assertRaises(ValueError): gate.parent_source(path, value)

    def test_unknown_legacy_objects_and_non_string_magic_refuse(self):
        class Magic(str):
            def encode(self, *args, **kwargs):
                raise AssertionError("subclass operation must not run")
        path = BRIDGE.replace("/request_bridge.rs", ".rs")
        current = self.texts()[path]
        for value in (None, Magic(current), current[:-1], "//" + current):
            with self.assertRaises(ValueError): gate.parent_source(path, value)

    def test_known_whole_object_table_is_normalization_only(self):
        for rows in gate.EXPECTED["known_legacy_inputs"].values():
            for row in rows:
                self.assertEqual(row["scope"], "DENIAL_ONLY_NORMALIZATION_NOT_CURRENT_P1")
                self.assertEqual(len(row["blob"]), 40)
                self.assertEqual(len(row["sha256"]), 64)
        value = copy.deepcopy(gate.EXPECTED)
        path = next(iter(value["known_legacy_inputs"]))
        value["known_legacy_inputs"][path][0]["sha256"] = "0" * 64
        with self.assertRaises(ValueError): gate.check(value, self.texts())

    def test_all_four_production_modules_are_mandatory_whole_objects(self):
        self.assertEqual(len(gate.EXPECTED["whole_production_source_sha256"]), 4)
        for path in gate.EXPECTED["whole_production_source_sha256"]:
            values = self.texts(); values[path] += "\n// candidate drift\n"
            with self.subTest(path=path), self.assertRaises(ValueError):
                gate.check(copy.deepcopy(gate.EXPECTED), values)

    def test_all_seventeen_signatures_and_seven_private_field_shapes_are_closed(self):
        self.assertEqual(len(gate.EXPECTED["public_api"]), 17)
        self.assertEqual(len(gate.EXPECTED["opaque_types"]), 7)
        values = self.texts(); values[BRIDGE] += "\npub fn caller_approval() {}\n"
        with self.assertRaises(ValueError): gate.inventory_and_orders(values)
        values = self.texts(); values[BRIDGE] = values[BRIDGE].replace(
            "original_owner: Option<ApprovedServiceOwnerBinding>",
            "pub original_owner: Option<ApprovedServiceOwnerBinding>", 1)
        with self.assertRaises(ValueError): gate.inventory_and_orders(values)

    def test_six_private_helpers_cannot_accept_caller_process_proof(self):
        self.assertEqual(len(gate.EXPECTED["private_helper_inventory"]), 6)
        values = self.texts(); values[ROOTED] = values[ROOTED].replace(
            "session: &ServiceSessionState", "session: &ServiceSessionState, caller: bool", 1)
        with self.assertRaises(ValueError): gate.inventory_and_orders(values)

    def test_original_control_identity_stays_before_first_scm_receive(self):
        self.mutate_order(TRANSPORT, "self.channel.original_identity.verify(fd)?;", "// omitted")

    def test_actual_returned_pending_cookie_and_enabled_transaction_stay_after_scm(self):
        self.mutate_order(TRANSPORT, "pending.transaction.channel.original_identity.verify(fd)?;", "// omitted")
        self.mutate_order(TRANSPORT, "pending.transaction.readiness_enabled = true;", "// omitted")

    def test_creator_precedes_transport_fd_access(self):
        self.mutate_order(TRANSPORT, "self.channel.owner()?;", "// omitted")

    def test_original_control_clock_is_checked_immediately_before_challenge(self):
        self.mutate_order(ROOTED, "remaining(owner_pid, deadline)?;", "// omitted")

    def test_source_owner_control_full_checks_surround_challenge(self):
        values = self.texts(); text = values[ROOTED]
        needle = "session\n                    .verify_control(&owner.attested)"
        self.assertEqual(text.count(needle), 2)
        for index in (0, 1):
            changed = text.split(needle)
            changed[index + 1] = "// removed selected boundary\n" + changed[index + 1]
            # Remove exactly one full call by replacing its receiver with a decoy.
            values2 = self.texts(); values2[ROOTED] = needle.join(changed)
            start = values2[ROOTED].find(needle) if index == 0 else values2[ROOTED].rfind(needle)
            values2[ROOTED] = values2[ROOTED][:start] + values2[ROOTED][start:].replace(needle, "caller.check_control()", 1)
            with self.assertRaises(ValueError): gate.inventory_and_orders(values2)

    def test_source_role_and_original_scope_surround_actual_scm(self):
        self.mutate_order(PACKING, "creator(self.owner_pid)?;", "// omitted")
        self.mutate_order(PACKING, "let wait = remaining(self.owner_pid, self.deadline)?;", "// omitted")
        self.mutate_order(PACKING, "retained.ensure_current()?;", "// omitted")

    def test_root_selected_default_proc_agent_and_nonclone_custody_are_required(self):
        self.mutate_order(BRIDGE, "ProcfsPeerAttestor::default()\n                    .attest", "caller_attestor.attest")
        self.mutate_order(BRIDGE, "attested\n                    .request_custody()", "caller_snapshot.custody()")

    def test_same_source_session_requires_pointer_identity(self):
        self.mutate_order(BRIDGE, "Arc::ptr_eq(&self.session, &session.session)", "true")

    def test_effective_deadline_cannot_exceed_original_control(self):
        self.mutate_order(BRIDGE, "deadline > original_control_deadline", "false")

    def test_original_pair_before_callback_and_final_service_clock_are_required(self):
        self.mutate_order(BRIDGE, "reporter.ensure_current()?;", "// omitted")
        self.mutate_order(BRIDGE, "let result = consumer(", "let result = caller_value(")

    def test_retained_reporting_remains_independent_of_action_permission(self):
        inventory = gate.source_gate.rust_inventory(self.texts()[BRIDGE])
        body = gate.source_gate.function(inventory, "ApprovedServiceRetainedReporter::ensure_current")
        self.assertNotIn("verify_pair_current", " ".join(body))
        self.mutate_order(BRIDGE, ".send_remote_report(report)", ".caller_report_success()")

    def test_current_source_cannot_drop_final_reporting_check_or_rebind_hash(self):
        values = self.texts(); values[BRIDGE] = values[BRIDGE].replace(
            "remaining(self.session.source.creator.pid, self.deadline)", "Ok(())")
        with self.assertRaises(ValueError): gate.inventory_and_orders(values)
        value = copy.deepcopy(gate.EXPECTED)
        value["whole_production_source_sha256"][BRIDGE] = gate.sha256(values[BRIDGE])
        with self.assertRaises(ValueError): gate.check(value, values)

    def test_original_tests_pins_and_raw_methods_are_whole_preserved(self):
        self.assertIn("tests/test_retained_control_readiness.py", gate.EXPECTED["preserved_source_sha256"])
        self.assertIn("experiments/servo-product-owner/src/approved_connected_tests.rs", gate.EXPECTED["preserved_source_sha256"])
        for path in gate.EXPECTED["preserved_source_sha256"]:
            values = self.texts(); values[path] += " "
            with self.subTest(path=path), self.assertRaises(ValueError): gate.check(copy.deepcopy(gate.EXPECTED), values)

    def test_new_cargo_entry_is_only_exact_suffix_and_not_old_budget_change(self):
        path = "crates/hepta-peer-attestation/Cargo.toml"
        rule = gate.EXPECTED["original_source_inverse"][path]
        self.assertIn("harness = false", rule["block"])
        self.assertEqual(rule["offset"], rule["parent_bytes"])
        self.assertEqual(gate.EXPECTED["kernel_corpus"]["execution"], "NOT_EXECUTED")

    def test_actual_process_corpus_source_and_limits_cannot_be_weakened(self):
        path = gate.EXPECTED["kernel_corpus"]["path"]
        for before in ("assert_ne!(control.child.id(), agent.child.id());",
                       '"--property=RuntimeMaxSec=120"', "const GROUPS: usize = 15;",
                       "assert!(accepted_at.elapsed() >= AFTER_FIRST);",
                       "if self.creator == std::process::id() && !self.done {"):
            values = self.texts(); self.assertIn(before, values[path]); values[path] = values[path].replace(before, "", 1)
            with self.subTest(before=before), self.assertRaises(ValueError): gate.check(copy.deepcopy(gate.EXPECTED), values)


if __name__ == "__main__":
    unittest.main()
