"""Adversarial inert no-head transcripts; never original/native receipts."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

import native_owner_evidence as original
import native_owner_genesis_evidence as oracle
import native_owner_genesis_types as t
import native_owner_genesis_witness as witness
from native_owner_genesis_test_records import GenesisRecords, pair
from test_native_owner_evidence import ELF, NONCE


class OriginalGenesisTranscriptTests(unittest.TestCase):
    def test_three_complete_shapes_remain_unqualified_until_actual_disk_and_vm_gates(self):
        for scenario, epoch in zip(t.SCENARIOS, (1, 2, 2)):
            with self.subTest(scenario=scenario):
                first, second = pair(scenario)
                cut, result = first.evaluate(), second.evaluate()
                self.assertEqual(cut["event_count"], 1)
                self.assertEqual(result["event_count"], 14)
                self.assertEqual(result["original_authority"]["proof"]["claims"]["sequence"], epoch)
                self.assertEqual(result["original_authority"]["writer"]["owner_epoch"], epoch)
                self.assertEqual(result["first_checkpoint"]["head"]["counter"], 1)
                self.assertEqual(result["first_checkpoint"]["head"]["writer_binding"]["generation"], 1)
                self.assertEqual(len(result["genesis_activations_expected"]), epoch)
                for report in (cut, result):
                    for key in ("passed", "same_physical_disk_reboot_verified", "original_no_head_recovery_verified",
                                "writer_reservation_recovery_verified", "proof_before_head_recovery_verified",
                                "kill_within_guest_wait_window_proven", "original_native_owner_cycle_verified",
                                "power_loss_verified", "g2_complete", "production_ready"):
                        self.assertFalse(report[key], key)

    def test_first_cut_is_one_selected_actual_sigkill_not_a_poweroff_or_later_owner(self):
        for scenario in t.SCENARIOS:
            for code in (0, 33, -15):
                records = GenesisRecords(scenario=scenario)
                with self.subTest(scenario=scenario, code=code), self.assertRaises(ValueError):
                    oracle.evaluate(records.raw(), {"raw_exit_code": code, "timed_out": False, "serial_excessive": False},
                                    NONCE, ELF, "fresh", scenario=scenario)
            records = GenesisRecords(scenario=scenario)
            records.add("owner_ready", {"untrusted_late_event": True})
            with self.subTest(scenario=scenario, late=True), self.assertRaises(ValueError):
                records.evaluate()

    def test_no_head_cuts_do_not_accept_an_invented_current_or_changed_mode(self):
        for scenario in t.SCENARIOS:
            for kind in ("head0", "mode"):
                records = GenesisRecords(scenario=scenario)
                cut = records.event("genesis_cut")
                state = cut["before"]["before_admission"] if scenario == t.SCENARIOS[1] else cut["cut"]
                if kind == "head0": state["current"] = {"counter": 0}
                else: records.records[0]["payload"]["phase"] = "other"
                with self.subTest(scenario=scenario, kind=kind), self.assertRaises(ValueError):
                    records.evaluate()

    def test_pending_original_preimage_full_claims_key_and_domain_are_mandatory(self):
        for kind in ("preimage", "signing-domain", "key", "purpose", "sequence", "claims", "premature-signature", "time"):
            records = GenesisRecords(scenario=t.SCENARIOS[1])
            actual = records.event("genesis_cut")["reserved_issuer"]
            pending = actual["writer_reservation"]
            if kind == "preimage": pending["expected_state_sha256"] = "ab" * 32
            elif kind == "signing-domain": pending["signing_bytes_sha256"] = "ab" * 32
            elif kind == "key": pending["verifying_key"][0] ^= 1
            elif kind == "purpose": pending["purpose"] = {"kind": "unactivated_genesis_replacement"}
            elif kind == "sequence": actual["sequence"] = 2
            elif kind == "claims": pending["claims"]["spawn_generation"] = 2
            elif kind == "premature-signature": actual["writer_authorization"] = {"claims": pending["claims"], "signature_hex": "ab" * 64}
            else: pending["admitted_at_unix_ms"] = pending["claims"]["authority_lease"]["expires_at_unix_ms"]
            with self.subTest(kind=kind), self.assertRaises(ValueError): records.evaluate()

    def test_exact_initial_witness_rejects_legacy_cut_digest_and_changed_preparing_process(self):
        for scenario in t.SCENARIOS[1:]:
            for kind in ("legacy", "root", "peer", "extra"):
                records = GenesisRecords(scenario=scenario)
                value = records.event("genesis_cut")
                candidate = value["before"]["candidate"] if scenario == t.SCENARIOS[1] else value["candidate"]
                if kind == "legacy":
                    candidate["writer"]["authority_lease"]["binding"]["payload_sha256"] = [1] * 32
                elif kind == "root":
                    state = value["before"]["before_admission"] if scenario == t.SCENARIOS[1] else value["cut"]
                    state["root"]["process_start_ticks"] += 1
                elif kind == "peer": candidate["peer"]["process_start_ticks"] += 1
                else: candidate["activation"]["unverified"] = True
                with self.subTest(scenario=scenario, kind=kind), self.assertRaises(ValueError): records.evaluate()

    def test_cold_open_preserves_all_original_immutable_inputs_and_clock_highwater(self):
        for kind in ("material", "inode", "intent", "pin", "clock", "boot"):
            _, second = pair(t.SCENARIOS[0])
            state = second.event("genesis_reopened")
            if kind == "material": state["initial_material"]["sha256"] = "ab" * 32
            elif kind == "inode": state["source_database"]["inode"] += 1
            elif kind == "intent": state["intent"]["record_sha256"] = "ab" * 32
            elif kind == "pin": state["installation"]["inode"] += 1
            elif kind == "clock": state["clock"]["projection"]["anchor_unix_ms"] -= 3000
            else: state["kernel_boot"] = second.previous["native_boot_id"]
            with self.subTest(kind=kind), self.assertRaises(ValueError): second.evaluate()

    def test_reserved_completion_keeps_the_old_sequence_claims_and_signature_chain(self):
        for kind in ("claims", "completed", "reservation", "predecessor", "new-sequence"):
            _, second = pair(t.SCENARIOS[1])
            first = second.event("genesis_first_owner")
            old = first["resumed"]["unactivated_writer"]
            if kind == "claims": old["proof"]["claims"]["authority_lease"]["expires_at_unix_ms"] += 1
            elif kind == "completed": old["completed_reserved_proof"] = None
            elif kind == "reservation": old["reservation"] = None
            elif kind == "predecessor": old["peer"]["boot_id"] = second.linux_boot
            else: first["writer_proof"]["claims"]["sequence"] += 1
            with self.subTest(kind=kind), self.assertRaises(ValueError): second.evaluate()

    def test_already_signed_cut_cannot_be_reported_as_a_new_reservation(self):
        _, second = pair(t.SCENARIOS[2])
        old = second.event("genesis_first_owner")["resumed"]["unactivated_writer"]
        old["completed_reserved_proof"] = copy.deepcopy(old["proof"])
        with self.assertRaises(ValueError): second.evaluate()

    def test_complete_original_selected_lease_retirement_is_revision_and_reason_bound(self):
        for kind in ("missing", "reason", "revision", "after", "retained-row"):
            _, second = pair(t.SCENARIOS[2])
            retired = second.event("genesis_first_owner")["resumed"]["unactivated_writer"]["retirement"]
            if kind == "missing": retired["revocations_applied"].pop()
            elif kind == "reason": retired["revocations_applied"][0]["reason_sha256"][0] ^= 1
            elif kind == "revision": retired["revocations_applied"][0]["store_revision"] += 1
            elif kind == "after": retired["registry_after"]["leases"] = retired["registry_before"]["leases"]
            else: second.stopped["root_authority"]["registry"]["leases"].pop("native-cpu-root-installation")
            with self.subTest(kind=kind), self.assertRaises(ValueError): second.evaluate()

    def test_first_checkpoint_is_counter_one_without_a_replacement_local_generation(self):
        for kind in ("counter", "epoch", "cut", "generation", "spawn"):
            _, second = pair(t.SCENARIOS[2])
            first = second.event("genesis_first_owner")
            if kind in ("counter", "epoch"):
                key = "counter" if kind == "counter" else "publisher_epoch"
                first["first_checkpoint"]["head"][key] = first["first_checkpoint"]["token"][key] = 0
            elif kind == "cut": first["first_checkpoint"]["head"]["last_current"]["state_digest"] = "ab" * 32
            elif kind == "generation": first["writer"]["local_lease_generation"] = 2
            else: second.event("owner_ready")["spawn_generation"] = 1
            with self.subTest(kind=kind), self.assertRaises(ValueError): second.evaluate()

    def test_actual_effect_ack_window_release_and_successful_reap_cannot_be_omitted(self):
        for name in ("native_result", "source_terminal", "history_ack", "usage_window", "owner_released", "owner_stopped"):
            _, second = pair()
            second.records = [value for value in second.records if value["event"] != name]
            # Preserve envelope positions so the required event-order oracle,
            # rather than an unrelated sequence gap, rejects each omission.
            for index, value in enumerate(second.records, 1): value["sequence"] = index
            with self.subTest(event=name), self.assertRaises(ValueError): second.evaluate()
        _, second = pair()
        window = second.event("usage_window")
        window["second"]["sample_boottime_ns"] = window["first"]["sample_boottime_ns"] + original.PERIOD_NS
        with self.assertRaises(ValueError): second.evaluate()

    def test_new_boot_cannot_redispatch_under_the_old_namespace(self):
        _, second = pair(t.SCENARIOS[1])
        op = second.event("prepared")
        request = original.json_value(op["request_json"])
        request["delivery"]["boot_id"] = second.previous["native_boot_id"]
        op["request_json"] = original.canonical(request)
        with self.assertRaises(ValueError): second.evaluate()

    def test_public_six_case_and_other_cold_oracles_do_not_implicitly_accept_genesis(self):
        for scenario in t.SCENARIOS:
            records = GenesisRecords(scenario=scenario)
            with self.subTest(scenario=scenario), self.assertRaises(ValueError):
                original.evaluate(records.raw(), -9, False, False, scenario, NONCE, ELF)
        records = GenesisRecords(scenario=t.SCENARIOS[1])
        reader = oracle.cut_line_reader(NONCE, t.SCENARIOS[0])
        line = records.raw().splitlines()[-1]
        with self.assertRaises(ValueError): reader(line)

    def test_runner_is_disabled_and_requires_explicit_case_and_actual_builds(self):
        script = Path(__file__).with_name("run_native_owner_genesis.py")
        result = subprocess.run([sys.executable, "-B", str(script)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertIsNone(report["scenario"])
        self.assertFalse(report["passed"])
        self.assertFalse(report["native_execution_attempted"])
        attempted = subprocess.run([sys.executable, "-B", str(script), "--execute", "--scenario", t.SCENARIOS[1]],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(attempted.returncode, 2)
        self.assertIn(b"requires --desktop-source", attempted.stderr)


if __name__ == "__main__":
    unittest.main()
