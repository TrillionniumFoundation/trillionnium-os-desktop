"""Inert parser adversaries, never source/build/guest qualification records."""
import copy
import hashlib
import json
import unittest

import native_owner_evidence as e
import native_owner_prior_boot_evidence as oracle
import native_owner_prior_boot_types as t
from native_owner_prior_boot_test_records import PriorRecords, pair
from run_native_owner_prior_boot import verify_actual_kill
from test_native_owner_evidence import ELF, NONCE


class PriorBootEvidenceTests(unittest.TestCase):
    def reject(self, records):
        with self.assertRaises(ValueError):
            records.evaluate()

    def test_complete_schema_branches_are_only_transcripts_and_not_native_qualification(self):
        first, second = pair()
        for records, count in ((first, 7), (second, 14)):
            result = records.evaluate()
            self.assertTrue(result["prior_boot_transcript_verified"])
            self.assertEqual(result["event_count"], count)
            for key in ("passed", "cross_boot_unknown_preservation_verified", "power_loss_verified",
                        "kill_within_guest_callback_window_proven", "original_native_owner_cycle_verified",
                        "g2_complete", "production_ready"):
                self.assertIs(result[key], False)
        self.assertTrue(second.evaluate()["new_source_terminal_observed"])
        self.assertEqual(second.evaluate()["unresolved_old_drain_blockers"], 1)

    def test_existing_public_six_case_gate_and_wrong_vm_exit_cannot_accept_the_new_case(self):
        first = PriorRecords()
        self.assertNotIn(t.SCENARIO, e.SUPPORTED_SCENARIOS)
        with self.assertRaises(ValueError):
            e.evaluate(first.raw(), 33, False, False, t.SCENARIO, NONCE, ELF)
        with self.assertRaises(ValueError):
            e.parse(first.raw(), t.SCENARIO, NONCE)
        with self.assertRaises(ValueError):
            oracle.evaluate(first.raw(), {"raw_exit_code": 33, "timed_out": False, "serial_excessive": False},
                            NONCE, ELF, "fresh")
        with self.assertRaises(ValueError):
            oracle.PriorBootTranscript("retained", NONCE, first.evaluate(), {"old_unknown_physically_verified": False})

    def test_fault_cut_binds_original_wire_claim_current_and_unchanged_callback_budget(self):
        for wrong in ("errno", "frame", "late", "extended", "key", "token", "issuer", "device-frontier"):
            records = PriorRecords()
            event = records.event("prior_boot_cut")
            cut = json.loads(event["durable_payload_json"])
            if wrong == "errno": cut["boundary"]["diagnostic"]["errno"] = 5
            elif wrong == "frame": cut["boundary"]["diagnostic"]["request_sha256"][0] ^= 1
            elif wrong == "late": event["emitted_boottime_ns"] = cut["boundary"]["pending_until_boottime_ns"]
            elif wrong == "extended": cut["boundary"]["pending_until_boottime_ns"] += 1
            elif wrong == "key": cut["occurrence_key"] += ".different"
            elif wrong == "token": cut["current_token"]["counter"] += 1
            elif wrong == "issuer": cut["issuer_sequence_at_cut"] = event["authority_before_dispatch"]["issuer_sequence"]
            elif wrong == "device-frontier": cut["frontiers"][0] = records.event("owner_ready")["device_frontier"]
            event["durable_payload_json"] = e.canonical(cut)
            event["durable_payload_sha256"] = hashlib.sha256(event["durable_payload_json"].encode()).hexdigest()
            with self.subTest(wrong=wrong): self.reject(records)

    def test_any_owner_event_after_cut_is_rejected_even_if_the_cut_itself_is_valid(self):
        records = PriorRecords()
        records.add("source_terminal", {"late_untrusted_terminal": True})
        self.reject(records)
        records = PriorRecords()
        records.records[-1]["event"] = "complete"
        self.reject(records)

    def test_cold_open_requires_original_pin_highwater_revocations_and_exact_cut(self):
        for wrong in ("pin", "highwater", "previous", "revoke", "selected", "expiry", "frontier", "writer-proof"):
            _, records = pair()
            event = records.event("prior_boot_adopted")
            cold = event["cold_open"]
            if wrong == "pin": records.event("boot_phase")["installation"]["inode"] += 1
            elif wrong == "highwater": cold["issuer_sequence"] -= 1
            elif wrong == "previous": cold["previous"]["token"]["head_sha256"] = "a" * 64
            elif wrong == "revoke": cold["revocations_applied"][0]["lease_revision"] += 1
            elif wrong == "selected": cold["registry_after"]["leases"] = cold["registry_before"]["leases"]
            elif wrong == "expiry": cold["clock"]["observed_unix_ms"] = 1
            elif wrong == "frontier": cold["notes_frontier"]["state_sha256"][0] ^= 1
            elif wrong == "writer-proof": records.event("owner_ready")["writer_proof_sha256"] = records.previous["original_owner"]["writer_proof_sha256"]
            with self.subTest(wrong=wrong): self.reject(records)

    def test_old_unknown_must_be_original_observer_refusal_without_either_ioctl(self):
        for wrong in ("generic-error", "query", "install", "committed", "operation", "startup", "blocker"):
            _, records = pair()
            event = records.event("prior_boot_observed")
            observed = event["observation"]
            if wrong == "generic-error": observed["refusal"] = "device unavailable"
            elif wrong == "query": observed["calls_after"]["query_ioctl_count"] = 1
            elif wrong == "install": event["transport"]["ioctl_counts"]["install_ioctl_count"] = 1
            elif wrong == "committed": observed["before"]["state"] = observed["after"]["state"] = "committed"
            elif wrong == "operation": observed["after"]["operation"]["payload_digest"][0] ^= 1
            elif wrong == "startup": event["transport"]["startup_retained"] = []
            elif wrong == "blocker": observed["drain_blockers"] = 0
            with self.subTest(wrong=wrong): self.reject(records)

    def test_fresh_effect_requires_new_native_scope_terminal_ack_and_workload_window(self):
        for wrong in ("short", "old-boot", "ack", "terminal", "extra-install", "notes"):
            _, records = pair()
            if wrong == "short":
                window = records.event("usage_window")
                window["second"]["sample_boottime_ns"] = window["first"]["sample_boottime_ns"] + e.PERIOD_NS
            elif wrong == "old-boot":
                event = records.event("prepared")
                request = json.loads(event["request_json"])
                request["delivery"]["boot_id"] = records.previous["native_boot_id"]
                event["request_json"] = e.canonical(request)
                event["payload_sha256"] = hashlib.sha256(event["request_json"].encode()).hexdigest()
            elif wrong in ("ack", "terminal"):
                name = "history_ack" if wrong == "ack" else "source_terminal"
                record = next(record for record in records.records if record["event"] == name)
                record["event"] = "fabricated-observation"
            elif wrong == "extra-install":
                records.event("prior_boot_observed", 1)["transport"]["ioctl_counts"]["install_ioctl_count"] = 2
            elif wrong == "notes":
                records.event("source_terminal")["notes_frontier"]["state_sha256"][0] ^= 1
            with self.subTest(wrong=wrong): self.reject(records)

    def test_forced_shutdown_cannot_claim_release_or_hide_a_later_current(self):
        for key, value in (("drain_blockers", 0), ("shutdown", "graceful-release"),
                           ("material_sha256", "a" * 64), ("unresolved_occurrence_key", "different")):
            _, records = pair()
            records.event("prior_boot_complete")[key] = value
            with self.subTest(key=key): self.reject(records)
        _, records = pair()
        records.event("prior_boot_complete")["current"]["head"]["counter"] += 1
        self.reject(records)

    def test_host_signal_observation_never_becomes_a_guest_clock_claim(self):
        first = PriorRecords()
        raw, checked = first.raw(), first.evaluate()
        line = raw.splitlines(keepends=True)[-1]
        cut = oracle.cut_line_reader(NONCE)(line)
        record = {"raw_exit_code": -9, "timed_out": False, "serial_excessive": False,
                  "host_cut": {"signal": 9, "process_group": 123, "line_offset": len(raw) - len(line),
                      "line_bytes": len(line), "line_sha256": hashlib.sha256(line).hexdigest(), "original_cut": cut,
                      "clock": "host time.monotonic_ns", "observed_at_ns": 10,
                      "kill_call_before_ns": 20, "kill_call_after_ns": 30, "guest_time_inferred": False}}
        value = verify_actual_kill(raw, record, checked)
        self.assertIs(value["kill_within_guest_callback_window_proven"], False)
        self.assertEqual(value["host_receive_to_kill_ns"], 20)
        changed = copy.deepcopy(record)
        changed["host_cut"]["guest_time_inferred"] = True
        with self.assertRaises(ValueError): verify_actual_kill(raw, changed, checked)


if __name__ == "__main__":
    unittest.main()
