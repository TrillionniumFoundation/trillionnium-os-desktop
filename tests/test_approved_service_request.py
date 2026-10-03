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
TRANSFER = "crates/hepta-agent-transport/src/root_control_path/service_control.rs"


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
        self.assertEqual(report["public_methods"], 18)
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

    def test_all_five_production_modules_are_mandatory_whole_objects(self):
        self.assertEqual(len(gate.EXPECTED["whole_production_source_sha256"]), 5)
        for path in gate.EXPECTED["whole_production_source_sha256"]:
            values = self.texts(); values[path] += "\n// candidate drift\n"
            with self.subTest(path=path), self.assertRaises(ValueError):
                gate.check(copy.deepcopy(gate.EXPECTED), values)

    def test_all_eighteen_signatures_and_seven_private_field_shapes_are_closed(self):
        self.assertEqual(len(gate.EXPECTED["public_api"]), 18)
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
        needle = "owner.current_for_service(session)"
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
                       '"--property=RuntimeMaxSec=120"', "const GROUPS: usize = 19;",
                       "assert!(accepted_at.elapsed() >= AFTER_FIRST);",
                       "if self.creator == std::process::id() && !self.done {"):
            values = self.texts(); self.assertIn(before, values[path]); values[path] = values[path].replace(before, "", 1)
            with self.subTest(before=before), self.assertRaises(ValueError): gate.check(copy.deepcopy(gate.EXPECTED), values)

    def test_root_transfer_checks_actual_admission_identity_not_only_held_clone(self):
        self.mutate_order(TRANSFER, "scope.socket_identity != Identity::from(&stat(fd)?)", "false")
        self.mutate_order(TRANSFER, "scope.cookie != option::<u64>(fd, libc::SO_COOKIE)?", "false")

    def test_root_transfer_original_creator_and_instant_precede_actual_fd_access(self):
        self.mutate_order(TRANSFER, "creator(scope.owner_pid)?;", "// omitted")
        self.mutate_order(TRANSFER, "remaining(scope.owner_pid, scope.deadline)?;", "// omitted")

    def test_root_transfer_requires_actual_peer_and_whole_held_scope(self):
        self.mutate_order(TRANSFER, "scope.identity\n            !=", "scope.identity\n            ==")
        values = self.texts(); values[TRANSFER] = values[TRANSFER].replace("scope.check()?;", "", 1)
        with self.assertRaises(ValueError): gate.inventory_and_orders(values)

    def test_root_transfer_keeps_original_legacy_delegate_and_full_post_proof(self):
        self.mutate_order(TRANSFER, "self.consume_before(consumer)?;", "caller_result;")
        text = self.texts()[TRANSFER]
        needle = "if let Err(error) = verify_moved(&guard.scope, fd)"
        self.assertEqual(text.count(needle), 1)
        values = self.texts(); offset = text.rfind(needle)
        values[TRANSFER] = text[:offset] + text[offset:].replace(needle, "if let Err(error) = caller_check()", 1)
        with self.assertRaises(ValueError): gate.inventory_and_orders(values)

    def test_post_failure_retires_before_callback_return_value_drop(self):
        self.mutate_order(TRANSFER, "guard.scope.current.store(false, Ordering::Release);", "// omitted")

    def test_uncompleted_unwind_guard_revokes_original_connection(self):
        self.mutate_order(TRANSFER, "if !self.completed", "if self.completed")
        self.mutate_order(TRANSFER, "self.scope.current.store(false, Ordering::Release);", "// omitted")
        values = self.texts(); values[TRANSFER] = values[TRANSFER].replace("completed: false", "completed: true", 1)
        with self.assertRaises(ValueError): gate.inventory_and_orders(values)

    def test_transfer_failure_does_not_add_service_or_shared_path_retirement(self):
        text = self.texts()[TRANSFER]
        self.assertNotIn("snapshot.current.store", text)
        self.assertNotIn("ServiceSessionState", text)
        self.assertNotIn("libc::shutdown", text)
        values = self.texts(); values[TRANSFER] += "\nimpl Default for OriginalTransferGuard {}\n"
        with self.assertRaises(ValueError): gate.check(copy.deepcopy(gate.EXPECTED), values)

    def test_product_service_factory_uses_only_explicit_root_transfer(self):
        self.mutate_order(ROOTED, ".consume_service_control_before(", ".consume_before(")

    def test_new_early_kernel_cases_preserve_denial_and_escape_observations(self):
        path = gate.EXPECTED["kernel_corpus"]["path"]
        self.assertEqual(gate.EXPECTED["kernel_corpus"]["early_root_transfer_groups"], [16, 17, 18, 19])
        for before in ("connection.deadline().unwrap();", "assert!(!callback_ran);",
                       "specific consumer-unwind stimulus", "guard.completed = true"):
            source = TRANSFER if before == "guard.completed = true" else path
            values = self.texts(); self.assertIn(before, values[source]); values[source] = values[source].replace(before, "", 1)
            with self.assertRaises(ValueError): gate.check(copy.deepcopy(gate.EXPECTED), values)


if __name__ == "__main__":
    unittest.main()


class ApprovedServicePrivateOwnerScopeTests(unittest.TestCase):
    """Actual source-token mutations, independently of complete-file hashes."""

    def texts(self):
        return gate.inputs(ROOT)

    def mutate_scope(self, before, after=""):
        values = self.texts()
        text = values[BRIDGE]
        start = text.index("    pub(crate) fn original_owner_root_scope(")
        end = text.index("    pub(crate) fn control_policy(", start)
        scope = text[start:end]
        self.assertIn(before, scope)
        values[BRIDGE] = text[:start] + scope.replace(before, after, 1) + text[end:]
        return values

    def refuse_after_rebinding_token_correspondence(self, values):
        # Rebind only the token correspondence, never route/orders/signatures.
        # Thus a real rejection must come from the independent finite semantics,
        # rather than the whole-file or whole-body digest alone.
        from unittest.mock import patch
        expected = copy.deepcopy(gate.EXPECTED)
        inventories = {path: gate.source_gate.rust_inventory(values[path])
                       for path in expected["whole_production_source_sha256"]}
        expected["all_function_body_tokens_sha256"] = {
            path: {name: hashlib.sha256(" ".join(body).encode()).hexdigest()
                   for name, body in inventory["functions"].items()}
            for path, inventory in inventories.items()}
        helpers = dict(expected["private_helper_inventory"])
        helpers.update(expected["denial_scope_helper_inventory"])
        helpers.update(expected["composed_service_helper_inventory"])
        for name, rule in helpers.items():
            path = rule["path"]
            header = gate._private_header(values[path], name)
            body = gate.source_gate.function(inventories[path], name)
            expected["private_helper_full_tokens_sha256"][name] = hashlib.sha256(
                " ".join(gate.source_gate.signature(header) + body).encode()).hexdigest()
        with patch.object(gate, "EXPECTED", expected), self.assertRaises(ValueError):
            gate.inventory_and_orders(values)

    def test_actual_closed_six_plus_one_helpers_cover_all_five_modules(self):
        values = self.texts()
        self.assertEqual(len(gate.EXPECTED["private_helper_inventory"]), 6)
        self.assertEqual(set(gate.EXPECTED["denial_scope_helper_inventory"]),
                         {"ServiceSessionState::original_owner_root_scope"})
        actual = {}
        for path in gate.EXPECTED["whole_production_source_sha256"]:
            for name, signature in gate._restricted_helpers(values[path]).items():
                self.assertNotIn(name, actual)
                actual[name] = (path, signature)
        self.assertEqual(set(gate.EXPECTED["composed_service_helper_inventory"]),
                         {"ControlPeerOwner::current_for_service", "AttestedHandoffReceiver::ensure_service_current"})
        self.assertEqual(len(actual), 9)
        self.assertEqual(set(actual), set(gate.EXPECTED["private_helper_full_tokens_sha256"]))
        gate.inventory_and_orders(values)

    def test_additional_restricted_free_function_and_method_are_not_hidden(self):
        for extra in ("\npub(crate) fn hidden_approval() {}\n",
                      "\nimpl ServiceSessionState { pub(crate) fn hidden_approval(&self) {} }\n"):
            values = self.texts(); values[BRIDGE] += extra
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                gate.inventory_and_orders(values)

    def test_duplicate_and_missing_scope_declarations_refuse(self):
        values = self.texts()
        text = values[BRIDGE]
        start = text.index("    pub(crate) fn original_owner_root_scope(")
        end = text.index("    pub(crate) fn control_policy(", start)
        for replacement in ("", text[start:end] * 2):
            changed = self.texts()
            changed[BRIDGE] = text[:start] + replacement + text[end:]
            with self.subTest(replacement=bool(replacement)), self.assertRaises(ValueError):
                gate.inventory_and_orders(changed)

    def test_scope_cannot_take_caller_boolean_fd_or_deadline(self):
        for argument in ("caller: bool", "fd: OwnedFd", "deadline: Instant"):
            values = self.mutate_scope("original_owner_root_scope(&self)",
                                       "original_owner_root_scope(&self, " + argument + ")")
            with self.subTest(argument=argument), self.assertRaises(ValueError):
                gate.inventory_and_orders(values)

    def test_old_and_new_helper_counts_are_fixed_not_configurable_capacity(self):
        from unittest.mock import patch
        for key in ("private_helper_inventory", "denial_scope_helper_inventory"):
            expected = copy.deepcopy(gate.EXPECTED)
            expected[key]["Caller::extra"] = {"path": BRIDGE, "signature": "pub(crate) fn extra()"}
            with patch.object(gate, "EXPECTED", expected), self.assertRaises(ValueError):
                gate.inventory_and_orders(self.texts())

    def test_scope_creator_is_required_before_any_shared_source_read(self):
        values = self.mutate_scope("self.source.creator_current()?;", "")
        self.refuse_after_rebinding_token_correspondence(values)

    def test_scope_same_owner_source_pointer_cannot_be_substituted(self):
        values = self.mutate_scope("Arc::ptr_eq(&self.source, &self.owner.state)", "true")
        self.refuse_after_rebinding_token_correspondence(values)

    def test_scope_original_owner_lease_is_required_at_both_sides(self):
        before = ("            self.owner\n                .original\n                .ensure_alive()\n"
                  "                .map_err(|_| ApprovedPolicyError::PeerRefused)?;\n")
        text = self.texts()[BRIDGE]
        start = text.index("    pub(crate) fn original_owner_root_scope(")
        end = text.index("    pub(crate) fn control_policy(", start)
        scope = text[start:end]
        self.assertEqual(scope.count(before), 2)
        for index in (0, 1):
            parts = scope.split(before)
            if index == 0:
                changed = parts[0] + parts[1] + before + parts[2]
            else:
                changed = parts[0] + before + parts[1] + parts[2]
            values = self.texts(); values[BRIDGE] = text[:start] + changed + text[end:]
            with self.subTest(index=index): self.refuse_after_rebinding_token_correspondence(values)

    def test_scope_root_source_inspection_is_required_at_both_sides(self):
        text = self.texts()[BRIDGE]
        start = text.index("    pub(crate) fn original_owner_root_scope(")
        end = text.index("    pub(crate) fn control_policy(", start)
        scope = text[start:end]
        before = "            self.source.inspect()?;\n"
        self.assertEqual(scope.count(before), 2)
        for index in (0, 1):
            parts = scope.split(before)
            changed = (parts[0] + parts[1] + before + parts[2] if index == 0
                       else parts[0] + before + parts[1] + parts[2])
            values = self.texts(); values[BRIDGE] = text[:start] + changed + text[end:]
            with self.subTest(index=index): self.refuse_after_rebinding_token_correspondence(values)

    def test_scope_original_default_proc_live_and_all_six_role_fields_are_required(self):
        markers = ["original.attestor.proc_root != Path::new(\"/proc\")",
                   "crate::ExecutableSource::Live", "snapshot.pid != self.source.creator.pid",
                   "snapshot.uid != entry.uid", "snapshot.gid != entry.gid",
                   "snapshot.systemd_unit.as_deref()", "snapshot.cgroup_v2_path != entry.cgroup",
                   "snapshot.executable_sha256 != entry.pin"]
        for marker in markers:
            values = self.mutate_scope(marker, "false")
            with self.subTest(marker=marker): self.refuse_after_rebinding_token_correspondence(values)

    def test_direct_owner_source_failure_stays_sticky_service_retirement(self):
        values = self.mutate_scope("self.source.retired.store(true, Ordering::SeqCst);", "")
        self.refuse_after_rebinding_token_correspondence(values)

    def test_challenge_full_control_boundaries_cannot_use_denial_scope(self):
        text = self.texts()[ROOTED]
        before = "owner.current_for_service(session)"
        self.assertEqual(text.count(before), 2)
        for index in (0, 1):
            offset = text.find(before) if index == 0 else text.rfind(before)
            values = self.texts()
            values[ROOTED] = text[:offset] + text[offset:].replace(
                before, "session.original_owner_root_scope()", 1)
            with self.subTest(index=index): self.refuse_after_rebinding_token_correspondence(values)

    def test_scope_is_limited_to_exact_three_immutable_composition_calls(self):
        self.assertEqual(gate.EXPECTED["denial_scope_call_inventory"], {
            "ServiceSessionState::control_policy": {"path": BRIDGE, "count": 2},
            "RootPathAttestedHandoffReceiver::from_service_control": {"path": ROOTED, "count": 1}})
        values = self.texts()
        values[BRIDGE] = values[BRIDGE].replace("self.owner.ensure_current()?;",
                                                "self.original_owner_root_scope()?;", 1)
        self.refuse_after_rebinding_token_correspondence(values)

    def test_scope_is_not_fresh_exec_and_does_not_mint_action_or_report_permits(self):
        inventory = gate.source_gate.rust_inventory(self.texts()[BRIDGE])
        body = " ".join(gate.source_gate.function(inventory, "ServiceSessionState::original_owner_root_scope"))
        for prohibited in (". refresh_snapshot (", ". attest (", "Instant : : now (", "ReportPermit", "RuntimePermit"):
            self.assertNotIn(prohibited, body)
        self.assertIs(gate.EXPECTED["private_owner_scope"]["fresh_current_owner_executable_observed"], False)
        self.assertIs(gate.EXPECTED["private_owner_scope"]["new_action_or_report_authority"], False)
        self.assertEqual(gate.EXPECTED["private_owner_scope"]["performance_improvement"],
                         "NOT_MEASURED_OR_QUALIFIED")

class ApprovedServiceControlCompositionTests(unittest.TestCase):
    """Actual finite mutants with whole/body/signature/order hashes rebound."""

    def texts(self):
        return gate.inputs(ROOT)

    def mutate_helper(self, path, method, before, after="", index=0):
        values = self.texts()
        text = values[path]
        start = text.index("    pub(in crate::control_owner) fn " + method + "(")
        end = text.index("\n    }", start) + len("\n    }")
        helper = text[start:end]
        self.assertIn(before, helper)
        offsets = []; cursor = 0
        while True:
            found = helper.find(before, cursor)
            if found < 0: break
            offsets.append(found); cursor = found + len(before)
        self.assertLess(index, len(offsets))
        offset = offsets[index]
        helper = helper[:offset] + helper[offset:].replace(before, after, 1)
        values[path] = text[:start] + helper + text[end:]
        return values

    def refuse_rebound(self, values, rebind_signatures=False, rebind_orders=False):
        from unittest.mock import patch
        expected = copy.deepcopy(gate.EXPECTED)
        inventories = {path: gate.source_gate.rust_inventory(values[path])
                       for path in expected["whole_production_source_sha256"]}
        expected["whole_production_source_sha256"] = {
            path: gate.sha256(values[path]) for path in inventories}
        expected["all_function_body_tokens_sha256"] = {
            path: {name: hashlib.sha256(" ".join(body).encode()).hexdigest()
                   for name, body in inventory["functions"].items()}
            for path, inventory in inventories.items()}
        for key in ("private_helper_inventory", "denial_scope_helper_inventory",
                    "composed_service_helper_inventory"):
            for name, rule in expected[key].items():
                header = gate._private_header(values[rule["path"]], name)
                body = gate.source_gate.function(inventories[rule["path"]], name)
                expected["private_helper_full_tokens_sha256"][name] = hashlib.sha256(
                    " ".join(gate.source_gate.signature(header) + body).encode()).hexdigest()
                if rebind_signatures: rule["signature"] = header
        if rebind_orders:
            for rule in expected["effect_orders"].values(): rule["markers"] = []
        with patch.object(gate, "EXPECTED", expected), self.assertRaises(ValueError):
            gate.inventory_and_orders(values)

    def test_complete_closed_nine_helpers_and_four_actual_full_boundary_calls(self):
        values = self.texts()
        self.assertEqual(gate.EXPECTED["private_owner_scope"]["total_restricted_helpers"], 9)
        self.assertEqual(set(gate.EXPECTED["composed_service_helper_inventory"]), {
            "ControlPeerOwner::current_for_service", "AttestedHandoffReceiver::ensure_service_current"})
        self.assertEqual(values[ROOTED].count("owner.current_for_service(session)?"), 2)
        self.assertEqual(values[PACKING].count("owner.current_for_service(session)?"), 1)
        self.assertEqual(values[PACKING].count("self.ensure_service_current(session)?"), 1)
        gate.inventory_and_orders(values)

    def test_composed_creator_cannot_be_removed_or_moved_after_source(self):
        for path, method in ((ROOTED, "current_for_service"), (PACKING, "ensure_service_current")):
            with self.subTest(method=method):
                self.refuse_rebound(self.mutate_helper(path, method, "creator(self.owner_pid)?;"), rebind_orders=True)
        values = self.mutate_helper(ROOTED, "current_for_service", "creator(self.owner_pid)?;")
        offset = values[ROOTED].rfind("        path.current()?;")
        self.assertGreaterEqual(offset, 0)
        values[ROOTED] = values[ROOTED][:offset] + values[ROOTED][offset:].replace(
            "        path.current()?;", "        creator(self.owner_pid)?;\n        path.current()?;", 1)
        self.refuse_rebound(values, rebind_orders=True)

    def test_both_original_deadline_checks_cannot_be_removed_or_extended(self):
        for before in ("remaining(self.owner_pid, self.deadline)?;", "remaining(self.owner_pid, self.deadline)\n"):
            for after in ("", "remaining(self.owner_pid, caller_future)\n"):
                with self.subTest(before=before, after=after):
                    self.refuse_rebound(self.mutate_helper(ROOTED, "current_for_service", before, after), rebind_orders=True)

    def test_each_original_root_path_check_surrounds_fresh_control(self):
        for index in (0, 1):
            with self.subTest(index=index):
                self.refuse_rebound(self.mutate_helper(ROOTED, "current_for_service", "path.current()?;", index=index), rebind_orders=True)
        self.refuse_rebound(self.mutate_helper(ROOTED, "current_for_service", ".ok_or(ControlOwnerError::PeerRefused)?", ".unwrap()"), rebind_orders=True)

    def test_default_proc_actual_literal_cannot_be_substituted_or_hidden_in_comment(self):
        values = self.mutate_helper(ROOTED, "current_for_service", 'Path::new("/proc")', 'Path::new("/tmp/proc")')
        # The existing lexer deliberately discards both literals identically.
        self.assertEqual(gate.source_gate.tokens(values[ROOTED]), gate.source_gate.tokens(self.texts()[ROOTED]))
        self.refuse_rebound(values, rebind_orders=True)
        values[ROOTED] += '\n// self.attestor.proc_root != Path::new("/proc")\n'
        self.refuse_rebound(values, rebind_orders=True)

    def test_default_proc_comparison_live_source_and_empty_legacy_state_are_mandatory(self):
        for before, after in (("self.attestor.proc_root !=", "self.attestor.proc_root =="),
                              ("crate::ExecutableSource::Live", "crate::ExecutableSource::Caller"),
                              ("!self.approved.is_empty()", "self.approved.is_empty()"),
                              ("return Err(ControlOwnerError::PeerRefused);", "return Ok(Duration::from_secs(20));")):
            with self.subTest(before=before):
                self.refuse_rebound(self.mutate_helper(ROOTED, "current_for_service", before, after), rebind_orders=True)

    def test_full_selected_control_cannot_be_replaced_by_denial_scope_or_idle(self):
        before = "session\n            .verify_control(&self.attested)\n            .map_err(service_error)?;"
        for after in ("", "session.original_owner_root_scope().map_err(service_error)?;",
                      "session.ensure_current().map_err(service_error)?;", "self.current()?;"):
            with self.subTest(after=after):
                self.refuse_rebound(self.mutate_helper(ROOTED, "current_for_service", before, after), rebind_orders=True)

    def test_composed_helpers_cannot_accept_caller_boolean_fd_or_future_instant(self):
        for path, method in ((ROOTED, "current_for_service"), (PACKING, "ensure_service_current")):
            for field in ("caller_approved: bool,", "caller_fd: RawFd,", "caller_deadline: Instant,"):
                with self.subTest(method=method, field=field):
                    values = self.mutate_helper(path, method, "        session: &ServiceSessionState,", "        session: &ServiceSessionState,\n        " + field)
                    self.refuse_rebound(values, rebind_signatures=True, rebind_orders=True)

    def test_composed_helpers_cannot_mint_new_authority_or_deadline(self):
        self.refuse_rebound(self.mutate_helper(ROOTED, "current_for_service", "Result<Duration, ControlOwnerError>", "Result<ApprovedActionPermit, ControlOwnerError>"), rebind_signatures=True, rebind_orders=True)
        self.refuse_rebound(self.mutate_helper(PACKING, "ensure_service_current", ".map(|_| self.deadline)", ".map(|_| Instant::now() + Duration::from_secs(20))"), rebind_orders=True)

    def test_cancelled_receiver_and_absent_original_owner_cannot_become_valid(self):
        for before, after in (("if self.cancelled", "if !self.cancelled"),
                              ("Err(ControlOwnerError::Cancelled)", "Ok(self.deadline)"),
                              (".ok_or(ControlOwnerError::ChannelRetired)", ".ok_or(ControlOwnerError::PeerRefused)"),
                              (".and_then(|owner| owner.current_for_service(session))", ".map(|_| Duration::from_secs(20))")):
            with self.subTest(before=before):
                self.refuse_rebound(self.mutate_helper(PACKING, "ensure_service_current", before, after), rebind_orders=True)

    def test_every_composed_error_still_retires_original_receiver(self):
        for before, after in (("if result.is_err()", "if result.is_ok()"),
                              ("self.retire()?;", ""), ("        result\n", "        Ok(self.deadline)\n")):
            with self.subTest(before=before):
                self.refuse_rebound(self.mutate_helper(PACKING, "ensure_service_current", before, after), rebind_orders=True)

    def test_before_and_after_challenge_cannot_use_weaker_or_missing_composition(self):
        before = "owner.current_for_service(session)?;"
        for index in (0, 1):
            for after in ("owner.current()?;", "session.original_owner_root_scope().map_err(service_error)?;", ""):
                text = self.texts()[ROOTED]; values = self.texts()
                offset = text.find(before) if index == 0 else text.rfind(before)
                self.assertGreaterEqual(offset, 0)
                values[ROOTED] = text[:offset] + text[offset:].replace(before, after, 1)
                with self.subTest(index=index, after=after): self.refuse_rebound(values, rebind_orders=True)

    def test_original_deadline_immediately_precedes_actual_single_challenge(self):
        values = self.texts()
        self.assertEqual(values[ROOTED].count("HandoffReceiver::from_control"), 1)
        values[ROOTED] = values[ROOTED].replace("                remaining(owner_pid, deadline)?;", "", 1)
        self.refuse_rebound(values, rebind_orders=True)

    def test_before_and_after_actual_scm_cannot_use_denial_or_idle_scope(self):
        for before in ("self.ensure_service_current(session)?;", "owner.current_for_service(session)?;"):
            for after in ("self.ensure_current()?;", "session.original_owner_root_scope().map_err(service_error)?;", ""):
                values = self.texts(); self.assertEqual(values[PACKING].count(before), 1)
                values[PACKING] = values[PACKING].replace(before, after, 1)
                with self.subTest(before=before, after=after): self.refuse_rebound(values, rebind_orders=True)

    def test_boundary_orders_cannot_move_full_check_after_its_effect(self):
        values = self.texts()
        before = "                owner.current_for_service(session)?;\n"
        values[ROOTED] = values[ROOTED].replace(before, "", 1)
        anchor = "                    .map_err(handoff)?;\n"
        self.assertEqual(values[ROOTED].count(anchor), 1)
        values[ROOTED] = values[ROOTED].replace(anchor, anchor + before, 1)
        self.refuse_rebound(values, rebind_orders=True)
        values = self.texts(); before = "            self.ensure_service_current(session)?;\n"
        values[PACKING] = values[PACKING].replace(before, "", 1)
        anchor = "            let (received, channel) = transferred.into_parts().map_err(handoff)?;\n"
        values[PACKING] = values[PACKING].replace(anchor, anchor + before, 1)
        self.refuse_rebound(values, rebind_orders=True)

    def test_unknown_additional_composition_route_is_refused_after_rebinding(self):
        values = self.texts()
        values[ROOTED] = values[ROOTED].replace("        Ok(received)", "        self.inner.ensure_service_current(session)?;\n        Ok(received)", 1)
        self.refuse_rebound(values, rebind_orders=True)

    def test_composed_helper_tables_are_closed_and_missing_extra_duplicate_refuse(self):
        from unittest.mock import patch
        for action in ("missing", "extra"):
            expected = copy.deepcopy(gate.EXPECTED)
            if action == "missing": expected["composed_service_helper_inventory"].pop("ControlPeerOwner::current_for_service")
            else: expected["composed_service_helper_inventory"]["Caller::extra"] = {"path": ROOTED, "signature": "pub(crate) fn extra()"}
            with patch.object(gate, "EXPECTED", expected), self.assertRaises(ValueError): gate.inventory_and_orders(self.texts())
        values = self.texts()
        start = values[ROOTED].index("impl ControlPeerOwner {")
        values[ROOTED] += "\n" + values[ROOTED][start:]
        with self.assertRaises(ValueError): gate.inventory_and_orders(values)

    def test_entire_original_full_session_control_guard_remains_required(self):
        # Rebind every correspondence/order digest; the composition still calls
        # the exact original full method, whose independent order is preserved.
        values = self.texts(); text = values[BRIDGE]
        start = text.index("    pub(crate) fn verify_control(")
        end = text.index("\n    }", start) + len("\n    }")
        method = text[start:end]
        for before in ("self.ensure_current()?;", ".refresh_snapshot(&ProcfsPeerAttestor::default())",
                       "snapshot.uid != entry.uid", "snapshot.gid != entry.gid",
                       "snapshot.systemd_unit.as_deref() != Some(entry.unit.as_str())",
                       "snapshot.cgroup_v2_path != entry.cgroup", "snapshot.executable_sha256 != entry.pin",
                       "        self.ensure_current()\n"):
            self.assertIn(before, method)
            changed = method.replace(before, "", 1)
            other = self.texts(); other[BRIDGE] = text[:start] + changed + text[end:]
            with self.subTest(before=before): self.refuse_rebound(other, rebind_orders=True)
        values = self.texts()
        values[BRIDGE] = text[:start] + method.replace('Path::new("/proc")', 'Path::new("/tmp/proc")', 1) + text[end:]
        self.refuse_rebound(values, rebind_orders=True)


class ApprovedServiceConsumeCompositionTests(unittest.TestCase):
    """Rebind contract hashes/API/opaque/orders; reviewed guards still refuse."""

    def texts(self):
        return gate.inputs(ROOT)

    def mutate(self, owner, method, before, after="", index=0):
        import re
        values = self.texts(); text = values[BRIDGE]
        start = text.index("impl " + owner + " {")
        match = re.compile(r"^    (?:pub(?:\([^\n]*\))? )?fn " + re.escape(method) + r"(?:<|\()", re.M).search(text, start)
        self.assertIsNotNone(match)
        start = match.start(); end = text.index("\n    }", start) + len("\n    }")
        body = text[start:end]; offsets = []; cursor = 0
        while True:
            found = body.find(before, cursor)
            if found < 0: break
            offsets.append(found); cursor = found + len(before)
        self.assertLess(index, len(offsets))
        offset = offsets[index]
        body = body[:offset] + body[offset:].replace(before, after, 1)
        values[BRIDGE] = text[:start] + body + text[end:]
        return values

    def refuse_rebound(self, values, rebind_guard_modules=False):
        from unittest.mock import patch
        expected = copy.deepcopy(gate.EXPECTED)
        inventories = {path: gate.source_gate.rust_inventory(values[path])
                       for path in expected["whole_production_source_sha256"]}
        for key in ("whole_production_source_sha256", "preserved_source_sha256", "kernel_source_sha256"):
            expected[key] = {path: gate.sha256(values[path]) for path in expected[key]}
        expected["all_function_body_tokens_sha256"] = {
            path: {name: hashlib.sha256(" ".join(body).encode()).hexdigest()
                   for name, body in inventory["functions"].items()}
            for path, inventory in inventories.items()}
        expected["public_api"] = {name: header for inventory in inventories.values()
                                   for name, header in inventory["public_api"].items()}
        expected["opaque_types"] = {name: "".join(value["body"])
                                    for inventory in inventories.values()
                                    for name, value in inventory["types"].items() if value["public"]}
        for key in ("private_helper_inventory", "denial_scope_helper_inventory", "composed_service_helper_inventory"):
            for name, rule in expected[key].items():
                header = gate._private_header(values[rule["path"]], name)
                body = gate.source_gate.function(inventories[rule["path"]], name)
                expected["private_helper_full_tokens_sha256"][name] = hashlib.sha256(
                    " ".join(gate.source_gate.signature(header) + body).encode()).hexdigest()
                rule["signature"] = header
        for rule in expected["effect_orders"].values(): rule["markers"] = []
        guards = {path: gate.sha256(values[path]) for path in gate._CONSUME_GUARD_MODULES}
        # Also bypass module hashes in selected cases so the hard-coded full
        # signature/body rule itself must reject the weak guard.
        with patch.object(gate, "EXPECTED", expected), patch.object(
                gate, "_CONSUME_GUARD_MODULES", guards if rebind_guard_modules else gate._CONSUME_GUARD_MODULES):
            with self.assertRaises(ValueError): gate.inventory_and_orders(values)

    def test_complete_seven_actual_modules_and_five_reviewed_guard_bodies(self):
        values = self.texts(); self.assertEqual(len(gate._CONSUME_GUARD_MODULES), 7)
        for path, wanted in gate._CONSUME_GUARD_MODULES.items():
            self.assertEqual(gate.sha256(values[path]), wanted)
        inventories = {path: gate.source_gate.rust_inventory(values[path])
                       for path in gate.EXPECTED["whole_production_source_sha256"]}
        gate._consume_service_semantics(values, inventories)

    def test_slot_must_precede_any_reporter_channel_check(self):
        self.refuse_rebound(self.mutate("ApprovedServiceReceivedRequest", "consume_with_request_binding", "self.binding.slot_current()?;"), True)

    def test_initial_original_clock_cannot_be_removed_renewed_or_delayed(self):
        before = "remaining(self.session.source.creator.pid, self.deadline)?;"
        for after in ("", "remaining(self.session.source.creator.pid, Instant::now())?;", "remaining(self.session.source.creator.pid, caller_deadline)?;"):
            with self.subTest(after=after):
                self.refuse_rebound(self.mutate("ApprovedServiceReceivedRequest", "consume_with_request_binding", before, after), True)
        values = self.mutate("ApprovedServiceReceivedRequest", "consume_with_request_binding", before)
        values[BRIDGE] = values[BRIDGE].replace("received.ensure_consume_current()?;", "received.ensure_consume_current()?;\n        " + before, 1)
        self.refuse_rebound(values, True)

    def test_slot_creator_identity_and_active_flag_cannot_be_rebound(self):
        for before, after in (("self.state.session.source.creator_current()?;", ""),
                              ("!Arc::ptr_eq(&self.slot.session, &self.state.session)", "false"),
                              ("!self.state.session.active.load(Ordering::SeqCst)", "false")):
            with self.subTest(before=before):
                self.refuse_rebound(self.mutate("ApprovedServiceRequestBinding", "slot_current", before, after), True)

    def test_full_independent_reporter_guard_must_precede_consumer(self):
        for after in ("", "self.session.original_owner_root_scope()?;", "caller_reporter_current()?;"):
            with self.subTest(after=after):
                self.refuse_rebound(self.mutate("ApprovedServiceReceivedRequest", "ensure_consume_current", "self.reporter.ensure_current()?;", after), True)
        values = self.mutate("ApprovedServiceReceivedRequest", "ensure_consume_current", "self.reporter.ensure_current()?;")
        values[BRIDGE] = values[BRIDGE].replace("        Ok(result)\n", "        reporter.ensure_current()?;\n        Ok(result)\n", 1)
        self.refuse_rebound(values, True)

    def test_final_pair_uses_same_original_agent_and_actual_control(self):
        before = "state\n                .control\n                .verify_pair_current(&self.binding.original.verifier())\n                .map_err(approval_error)?;"
        for after in ("", "state.control.verify_pair_current(&caller_original).map_err(approval_error)?;", "state.control.verify_current().map_err(approval_error)?;", "cached_pair_current()?;"):
            with self.subTest(after=after):
                self.refuse_rebound(self.mutate("ApprovedServiceReceivedRequest", "ensure_consume_current", before, after), True)

    def test_full_source_owner_envelopes_pair_before_and_after(self):
        for index in (0, 1):
            with self.subTest(index=index):
                self.refuse_rebound(self.mutate("ServiceRequestState", "current", "self.session.ensure_current()?;", index=index), True)
        self.refuse_rebound(self.mutate("ServiceSessionState", "ensure_current", "self.owner.ensure_current()?;", "self.original_owner_root_scope()?;"), True)
        self.refuse_rebound(self.mutate("ServiceSessionState", "ensure_current", "self.source.inspect()", "Ok(())"), True)

    def test_pair_original_clocks_and_sticky_retirement_remain_whole(self):
        for before, after in (("self.retired.load(Ordering::SeqCst)", "false"),
                              ("self.retired.store(true, Ordering::SeqCst);", ""),
                              ("remaining(self.session.source.creator.pid, self.deadline)?;", ""),
                              ("remaining(self.session.source.creator.pid, self.deadline)\n", "Ok(())\n"),
                              (".verify_pair_current(original)", ".verify_current()")):
            with self.subTest(before=before):
                self.refuse_rebound(self.mutate("ServiceRequestState", "current", before, after), True)

    def test_actual_consumer_cannot_precede_guard_repeat_or_be_caller_success(self):
        for after in ("let result = caller_value(", "let result = (consumer, consumer)("):
            with self.subTest(after=after):
                self.refuse_rebound(self.mutate("ApprovedServiceReceivedRequest", "consume_with_request_binding", "let result = consumer(", after), True)
        values = self.mutate("ApprovedServiceReceivedRequest", "consume_with_request_binding", "received.ensure_consume_current()?;")
        values[BRIDGE] = values[BRIDGE].replace("        Ok(result)\n", "        received.ensure_consume_current()?;\n        Ok(result)\n", 1)
        self.refuse_rebound(values, True)

    def test_post_callback_requires_full_source_owner_and_original_clock(self):
        for before, after in (("session.ensure_current()?;", ""),
                              ("remaining(session.source.creator.pid, deadline)?;", ""),
                              ("remaining(session.source.creator.pid, deadline)?;", "remaining(session.source.creator.pid, Instant::now())?;")):
            with self.subTest(before=before):
                self.refuse_rebound(self.mutate("ApprovedServiceReceivedRequest", "consume_with_request_binding", before, after), True)

    def test_reporter_full_source_control_channel_and_exact_deadline_remain_whole(self):
        for index in (0, 1):
            with self.subTest(index=index):
                self.refuse_rebound(self.mutate("ApprovedServiceRetainedReporter", "ensure_current", "self.session.ensure_current()?;", index=index), True)
        for before, after in (("self.session.source.creator_current()?;", ""),
                              ("!Arc::ptr_eq(&self.slot.session, &self.session)", "false"),
                              ("!self.session.active.load(Ordering::SeqCst)", "false"),
                              ("deadline != self.deadline", "false"),
                              (".ensure_current()", ".caller_channel_current()"),
                              ("self.retained.take();", "")):
            with self.subTest(before=before):
                self.refuse_rebound(self.mutate("ApprovedServiceRetainedReporter", "ensure_current", before, after), True)

    def test_all_seven_actual_guard_modules_refuse_complete_hash_api_rebinding(self):
        for path in gate._CONSUME_GUARD_MODULES:
            values = self.texts(); values[path] += "\n// rebound guard module drift\n"
            with self.subTest(path=path): self.refuse_rebound(values)

    def test_callback_signature_and_private_proof_fields_cannot_be_rebound(self):
        self.refuse_rebound(self.mutate("ApprovedServiceReceivedRequest", "consume_with_request_binding", "consumer: impl FnOnce(", "consumer: impl FnMut("), True)
        for before, after in (("original: PeerRequestCustody,", "original: PeerRequestVerifier,"),
                              ("deadline: Instant,\n    custody: ControlRequestCustody,", "deadline: Duration,\n    custody: ControlRequestCustody,")):
            values = self.texts(); self.assertIn(before, values[BRIDGE]); values[BRIDGE] = values[BRIDGE].replace(before, after, 1)
            with self.subTest(before=before): self.refuse_rebound(values)

    def test_public_original_deadline_still_performs_full_original_pair(self):
        self.refuse_rebound(self.mutate("ApprovedServiceReceivedRequest", "original_deadline", ".current(&self.binding.original.verifier())?;", ".caller_cached_current()?;"))

    def test_source_composition_does_not_claim_kernel_or_performance(self):
        scope = gate.EXPECTED["service_consume_guard_composition"]
        self.assertEqual(scope["kernel_on_current_source"], "NOT_EXECUTED")
        self.assertEqual(scope["performance_improvement"], "NOT_MEASURED_OR_QUALIFIED")
        self.assertIs(scope["production_ready"], False)
        self.assertIs(scope["cross_transaction_or_cross_stage_cached_approval"], False)


class ApprovedServiceReporterPairBoundaryTests(unittest.TestCase):
    """Rebind every correspondence field; fixed owned guards still refuse."""

    texts = ApprovedServiceConsumeCompositionTests.texts
    mutate = ApprovedServiceConsumeCompositionTests.mutate

    def refuse_rebound(self, values, rebind_guard_modules=True):
        from unittest.mock import patch
        expected = copy.deepcopy(gate.EXPECTED)
        inventories = {path: gate.source_gate.rust_inventory(values[path])
                       for path in expected["whole_production_source_sha256"]}
        for key in ("whole_production_source_sha256", "preserved_source_sha256", "kernel_source_sha256"):
            expected[key] = {path: gate.sha256(values[path]) for path in expected[key]}
        expected["all_function_body_tokens_sha256"] = {
            path: {name: hashlib.sha256(" ".join(body).encode()).hexdigest()
                   for name, body in inventory["functions"].items()}
            for path, inventory in inventories.items()}
        expected["public_api"] = {name: header for inventory in inventories.values()
                                  for name, header in inventory["public_api"].items()}
        expected["opaque_types"] = {name: "".join(value["body"])
                                   for inventory in inventories.values()
                                   for name, value in inventory["types"].items() if value["public"]}
        for key in ("private_helper_inventory", "denial_scope_helper_inventory", "composed_service_helper_inventory"):
            for name, rule in expected[key].items():
                header = gate._private_header(values[rule["path"]], name)
                body = gate.source_gate.function(inventories[rule["path"]], name)
                expected["private_helper_full_tokens_sha256"][name] = hashlib.sha256(
                    " ".join(gate.source_gate.signature(header) + body).encode()).hexdigest()
                rule["signature"] = header
        for name, rule in expected["consume_pair_boundary_helper_inventory"].items():
            header = gate._private_header(values[rule["path"]], name)
            body = gate.source_gate.function(inventories[rule["path"]], name)
            rule["signature"] = header
            rule["full_tokens_sha256"] = hashlib.sha256(
                " ".join(gate.source_gate.signature(header) + body).encode()).hexdigest()
        for rule in expected["effect_orders"].values(): rule["markers"] = []
        guards = {path: gate.sha256(values[path]) for path in gate._CONSUME_GUARD_MODULES}
        with patch.object(gate, "EXPECTED", expected), patch.object(
                gate, "_CONSUME_GUARD_MODULES", guards if rebind_guard_modules else gate._CONSUME_GUARD_MODULES):
            with self.assertRaises(ValueError): gate.inventory_and_orders(values)

    def helper_mutation(self, before, after="", index=0):
        return self.mutate("ApprovedServiceReceivedRequest", "ensure_consume_current", before, after, index)

    def test_complete_owned_helper_signature_body_inventory_and_sole_call(self):
        values = self.texts()
        gate.inventory_and_orders(values)
        rule = gate.EXPECTED["consume_pair_boundary_helper_inventory"]
        self.assertEqual(list(rule), ["ApprovedServiceReceivedRequest::ensure_consume_current"])
        self.assertEqual(rule[next(iter(rule))]["signature"],
                         "fn ensure_consume_current(&mut self) -> Result<(), ApprovedPolicyError>")
        self.assertEqual(len(gate.EXPECTED["private_helper_full_tokens_sha256"]), 9)
        self.assertEqual(len(gate._CONSUME_GUARD_MODULES), 7)

    def test_creator_precedes_own_identity_and_any_clock(self):
        self.refuse_rebound(self.helper_mutation("self.session.source.creator_current()?;"))
        self.refuse_rebound(self.helper_mutation("self.session.source.creator_current()?;",
                            "remaining(self.session.source.creator.pid, self.deadline)?;"))

    def test_all_three_same_Arc_denials_cannot_be_removed_or_caller_bound(self):
        for before in ("!Arc::ptr_eq(&self.session, &self.reporter.session)",
                       "!Arc::ptr_eq(&self.session, &self.binding.state.session)",
                       "!Arc::ptr_eq(&self.reporter.slot, &self.binding.slot)"):
            for after in ("false", "caller_same_identity"):
                with self.subTest(before=before, after=after):
                    self.refuse_rebound(self.helper_mutation(before, after))

    def test_original_reporter_and_pair_deadline_equality_cannot_be_rebound(self):
        for before in ("self.deadline != self.reporter.deadline", "self.deadline != self.binding.state.deadline"):
            for after in ("false", "self.deadline != Instant::now()"):
                with self.subTest(before=before, after=after):
                    self.refuse_rebound(self.helper_mutation(before, after))

    def test_reporter_complete_guard_cannot_be_cached_denial_only_or_after_pair(self):
        before = "self.reporter.ensure_current()?;"
        for after in ("", "self.session.original_owner_root_scope()?;", "caller_reporter_proof()?;"):
            with self.subTest(after=after): self.refuse_rebound(self.helper_mutation(before, after))
        values = self.helper_mutation(before)
        values[BRIDGE] = values[BRIDGE].replace("        let state = &self.binding.state;",
            "        let state = &self.binding.state;\n        caller_cached_reporter()?;", 1)
        self.refuse_rebound(values)

    def test_same_original_pair_cannot_be_removed_replaced_or_newly_attested(self):
        before = ".verify_pair_current(&self.binding.original.verifier())"
        for after in (".verify_current()", ".verify_pair_current(&caller_original)", ".verify_pair_current(&newly_attested.verifier())"):
            with self.subTest(after=after): self.refuse_rebound(self.helper_mutation(before, after))

    def test_pair_checked_tail_original_clocks_and_sticky_retire_are_whole(self):
        for before, after in (("remaining(state.session.source.creator.pid, state.deadline)?;", ""),
                              ("remaining(state.session.source.creator.pid, state.deadline)\n", "Ok(())\n"),
                              ("state.retired.load(Ordering::SeqCst)", "false"),
                              ("state.retired.store(true, Ordering::SeqCst);", ""),
                              (".map_err(approval_error)?;", ".map_err(|_| ApprovedPolicyError::Changed)?;")):
            with self.subTest(before=before): self.refuse_rebound(self.helper_mutation(before, after))

    def test_pair_post_requires_full_Source_Owner_not_scope_or_after_callback(self):
        for after in ("", "state.session.original_owner_root_scope()?;"):
            with self.subTest(after=after):
                self.refuse_rebound(self.helper_mutation("state.session.ensure_current()?;", after))

    def test_full_reporter_common_Source_Owner_boundary_remains_independent(self):
        for index in (0, 1):
            with self.subTest(index=index):
                self.refuse_rebound(self.mutate("ApprovedServiceRetainedReporter", "ensure_current", "self.session.ensure_current()?;", index=index))
        self.refuse_rebound(self.mutate("ServiceSessionState", "ensure_current", "self.owner.ensure_current()?;", "self.original_owner_root_scope()?;"))

    def test_sole_call_cannot_be_removed_repeated_moved_or_reused_by_other_operation(self):
        before = "received.ensure_consume_current()?;"
        for after in ("", before + "\n        " + before):
            with self.subTest(after=after):
                self.refuse_rebound(self.mutate("ApprovedServiceReceivedRequest", "consume_with_request_binding", before, after))
        values = self.texts()
        values[BRIDGE] = values[BRIDGE].replace("        self.binding.slot_current()?;",
            "        self.ensure_consume_current()?;\n        self.binding.slot_current()?;", 1)
        self.refuse_rebound(values)

    def test_helper_cannot_be_public_accept_caller_proof_or_return_authority(self):
        values = self.texts()
        values[BRIDGE] = values[BRIDGE].replace("    fn ensure_consume_current(", "    pub fn ensure_consume_current(", 1)
        self.refuse_rebound(values)
        for before, after in (("&mut self) -> Result<(), ApprovedPolicyError>", "&mut self, caller_proof: bool) -> Result<(), ApprovedPolicyError>"),
                              ("&mut self) -> Result<(), ApprovedPolicyError>", "&mut self) -> Result<ApprovalProof, ApprovedPolicyError>")):
            with self.subTest(after=after): self.refuse_rebound(self.helper_mutation(before, after))

    def test_private_opaque_fields_cannot_be_caller_replaced_or_cache_authority(self):
        for before, after in (("original: PeerRequestCustody,", "original: PeerRequestVerifier,"),
                              ("    binding: ApprovedServiceRequestBinding,", "    binding: ApprovedServiceRequestBinding,\n    cached_pair: bool,")):
            values = self.texts(); values[BRIDGE] = values[BRIDGE].replace(before, after, 1)
            with self.subTest(before=before): self.refuse_rebound(values)

    def test_actual_original_Agent_Control_retained_channel_guards_cannot_be_catalog_rebound(self):
        cases = [
            ("crates/hepta-peer-attestation/src/request_lease.rs", "self.state.peer.refresh_snapshot(&self.state.peer.attestor)", "caller_cached_snapshot()"),
            ("crates/hepta-peer-attestation/src/control_owner/control_request.rs", "self.original_peer_result(original.verify_current())?;", ""),
            ("crates/hepta-peer-attestation/src/control_owner/retained_request.rs", ".ensure_current()\n                .map_err(handoff)?;", ".caller_current()\n                .map_err(handoff)?;"),
            ("crates/hepta-peer-attestation/src/control_owner.rs", ".refresh_snapshot(&self.attestor)", ".ensure_alive()"),
            ("crates/hepta-agent-transport/src/accepted_handoff/retained_control.rs", "channel.original_identity.verify(fd)?;", ""),
        ]
        for path, before, after in cases:
            values = self.texts(); self.assertIn(before, values[path]); values[path] = values[path].replace(before, after, 1)
            with self.subTest(path=path): self.refuse_rebound(values, False)

    def test_post_callback_still_allows_action_retirement_without_new_pair_guard(self):
        values = self.mutate("ApprovedServiceReceivedRequest", "consume_with_request_binding",
                             "        session.ensure_current()?;", "        binding.state.current(&binding.original.verifier())?;\n        session.ensure_current()?;")
        self.refuse_rebound(values)

    def test_scope_is_Source_pending_without_runtime_or_sampling_equivalence_claim(self):
        scope = gate.EXPECTED["service_consume_reporter_pair_boundary"]
        self.assertEqual(scope["kernel_on_current_source"], "NOT_EXECUTED")
        self.assertIs(scope["temporary_drift_identical_sampling_time_claim"], False)
        self.assertIs(scope["runtime_snapshot_counts_or_latency_measured"], False)
        self.assertIs(scope["production_ready"], False)

