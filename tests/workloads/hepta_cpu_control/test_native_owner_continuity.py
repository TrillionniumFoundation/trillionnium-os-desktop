"""Inert transcript rejection tests; these never execute or qualify Hepta."""
import copy
import hashlib
import json
import struct
import unittest

import native_owner_evidence as evidence
import native_owner_continuity_types as types
import native_owner_state_observations as disk
from native_owner_continuity_test_records import ContinuityRecords
from native_owner_successor_wire import initial_expiry_upper_bound, retirement_receipt
from test_native_owner_evidence import NONCE


class OriginalContinuityOracleTests(unittest.TestCase):
    def test_complete_inert_shapes_still_require_actual_retained_disk(self):
        for scenario in evidence.CONTINUITY_SCENARIOS:
            with self.subTest(scenario=scenario):
                result = ContinuityRecords(scenario).evaluate()
                self.assertTrue(result["continuity_transcript_verified"])
                self.assertFalse(result["passed"])
                for name in ("original_native_owner_cycle_verified", "root_launch_files_verified", "grant_renewal_verified",
                             "unbounded_persistent_cpu_verified", "cross_boot_unknown_preservation_verified",
                             "power_loss_verified", "production_ready", "g2_complete"):
                    self.assertFalse(result[name], name)
                self.assertEqual(len(result["root_launch_observations_expected"]), 2)
                with self.assertRaises(ValueError):
                    disk.accept_retained_observations(result, {"passed": True, "readonly_extraction": True, "actual_files": []})

    def test_real_effect_endpoint_and_two_new_generations_are_required(self):
        for case in ("threshold", "initial-time", "fresh-count", "delivery", "terminal"):
            records = ContinuityRecords("successor-renewal-v1")
            endpoint = records.event("renewal_endpoint")
            if case == "threshold": endpoint["after_boottime_ns"] -= 30_000_000_000
            if case == "initial-time": endpoint["initial_sample_boottime_ns"] = 0
            if case == "fresh-count": endpoint["fresh_kernel_generations"] = [2]
            if case == "delivery": endpoint["delivery"]["sequence"] = "0000000000000002"
            if case == "terminal": endpoint["actual_terminal_json"] = records.event("native_result")["terminal_json"]
            with self.subTest(case=case), self.assertRaises(ValueError):
                records.evaluate()
        with self.assertRaises(ValueError):
            initial_expiry_upper_bound((1 << 64) - 300_000_000_000, include_recovery=True)

    def test_every_new_manager_needs_two_periods_of_actual_progress_after_ack(self):
        for scenario in evidence.CONTINUITY_SCENARIOS:
            for case in ("missing", "short", "no-cpu", "no-heartbeat", "before-ack"):
                records = ContinuityRecords(scenario)
                window = records.event("usage_window")
                if case == "missing":
                    next(record for record in records.records if record["event"] == "usage_window")["event"] = "missing-window"
                elif case == "short": window["second"] = copy.deepcopy(window["first"])
                elif case == "no-cpu": window["second"]["cumulative_cpu_ns"] = window["first"]["cumulative_cpu_ns"]
                elif case == "no-heartbeat": window["second"]["heartbeat"] = window["first"]["heartbeat"]
                else:
                    index = next(index for index, record in enumerate(records.records) if record["event"] == "usage_window")
                    records.records[index - 1]["event"], records.records[index]["event"] = "usage_window", "history_ack"
                with self.subTest(scenario=scenario, case=case), self.assertRaises(ValueError):
                    records.evaluate()

    def test_original_leases_proofs_release_and_consuming_reap_are_bound(self):
        for case in ("root-lifetime", "writer-lifetime", "proof", "scope", "release", "reap", "successor-generation"):
            records = ContinuityRecords("successor-renewal-v1")
            owner = records.event("continuity_owner", 2)
            if case == "root-lifetime": owner["root_lease"]["expires_at_unix_ms"] += 1
            if case == "writer-lifetime": owner["writer"]["authority_lease"]["expires_at_unix_ms"] += 1
            if case == "proof": owner["writer_proof"]["signature_hex"] = "cd" * 64
            if case == "scope": owner["root_lease"]["binding"]["scope_sha256"][0] ^= 1
            if case == "release": records.event("owner_released")["receipt"]["state"] = "active"
            if case == "reap": records.event("owner_stopped")["supervisor"]["events"][-1]["details"]["code"] = None
            if case == "successor-generation": owner["supervisor"]["spawn_generation"] += 1
            with self.subTest(case=case), self.assertRaises(ValueError):
                records.evaluate()

    def test_kernel_generation_namespace_raw_bytes_and_saved_payload_cannot_be_replaced(self):
        for case in ("reserved", "history", "payload", "duplicate-generation", "missing-image"):
            records = ContinuityRecords("successor-renewal-v1")
            saved = records.event("kernel_launch_saved")
            if case == "reserved": saved["launch_receipt"][-1] = 1
            if case == "history": saved["retirement_receipt"][88] ^= 1
            if case == "payload": saved["durable_payload_json"] += " "
            if case == "duplicate-generation": records.event("kernel_launch_saved", 2)["launch_generation"] = 1
            if case == "missing-image": next(iter(records.kernel_before.values())).pop(0)
            with self.subTest(case=case), self.assertRaises(ValueError):
                records.evaluate()

    def test_original_root_lease_id_requires_actual_boot_and_supervisor_spawn(self):
        for case in ("legacy", "another-boot", "local-generation", "initial-replaced"):
            records = ContinuityRecords("successor-renewal-v1")
            owner = records.event("continuity_owner", 2 if case != "initial-replaced" else 0)
            if case == "legacy":
                selected = "native-cpu-root-writer-" + str(owner["writer"]["local_lease_generation"])
            elif case == "another-boot":
                selected = "native-cpu.root.00000000-0000-0000-0000-000000000001." + str(owner["writer"]["spawn_generation"])
            elif case == "local-generation":
                self.assertNotEqual(owner["writer"]["local_lease_generation"], owner["writer"]["spawn_generation"])
                selected = "native-cpu.root." + records.linux_boot + "." + str(owner["writer"]["local_lease_generation"])
            else:
                selected = "native-cpu.root." + records.linux_boot + "." + str(owner["writer"]["spawn_generation"])
            owner["root_lease"]["lease_id"] = selected
            with self.subTest(case=case), self.assertRaisesRegex(ValueError, "lease was reused or silently extended"):
                records.evaluate()

    def test_consistently_bound_old_writer_lease_id_is_still_rejected(self):
        class LegacyWriterRecords(ContinuityRecords):
            def authority(self, previous):
                value = super().authority(previous)
                lease = value["writer"]["authority_lease"]
                lease["lease_id"] = "native-cpu-writer-" + str(self.local_generation)
                # Keep all inert proof/Current digests self-consistent, so the
                # rejection specifically exercises the actual lease identity.
                proof = value["proof"]
                proof["claims"]["authority_lease_sha256"] = types.sha(lease)
                proof_hash = types.sha(proof)
                value["binding"]["authority_grant_digest"] = proof_hash
                value["binding"]["fencing_token_digest"] = hashlib.sha256(hashlib.sha256(
                    b"hepta:production-authority-token-grant:v2\0"
                    + proof_hash.encode() + proof["signature_hex"].encode()).digest()).hexdigest()
                return value

        with self.assertRaisesRegex(ValueError, "lease was reused or silently extended"):
            LegacyWriterRecords("successor-renewal-v1").evaluate()

    def test_history_only_has_no_usage_or_effect_and_preserves_the_old_delivery(self):
        for case in ("usage", "handle", "old-terminal", "no-expiry", "live", "unreaped", "wrong-fault", "watchdog-cut"):
            records = ContinuityRecords("history-only-after-both-owner-exit-v1")
            if case == "usage": records.event("continuity_owner")["usage"] = {"revision": 3}
            if case == "handle": records.event("continuity_owner")["kernel_bootstrap"][32] = 1
            if case == "old-terminal": records.event("reconciled")["terminal_json"] = records.event("native_result", 1)["terminal_json"]
            if case == "no-expiry": records.event("local_lease_retired")["observed_unix_seconds"] -= 1
            if case == "live": records.event("launch_refused")["errno"] = 1
            if case == "unreaped": records.event("launch_refused", 1)["launch_receipt"][24] = 1
            if case == "wrong-fault": records.event("initial_recovery_reaped")["driver_fault"] = "some unrelated failure"
            if case == "watchdog-cut": records.event("kernel_launch_saved", 1)["retirement_receipt"][72] ^= 1
            with self.subTest(case=case), self.assertRaises(ValueError):
                records.evaluate()

    def test_only_renewal_has_1024_event_limit_and_old_single_event_bound_remains(self):
        template = {"schema_version": 1, "scenario": "successor-renewal-v1", "nonce": NONCE,
                    "event": "inert-limit-record", "sequence": 1, "payload": {}}
        def raw(scenario, count):
            return ("\n".join(evidence.PREFIX + json.dumps({**template, "scenario": scenario, "sequence": index + 1})
                              for index in range(count)) + "\n").encode()
        self.assertEqual(len(evidence.parse(raw("successor-renewal-v1", 1024), "successor-renewal-v1", NONCE)[1]), 1024)
        for scenario, count in [("successor-renewal-v1", 1025)] + [(name, 129) for name in evidence.SUPPORTED_SCENARIOS if name != "successor-renewal-v1"]:
            with self.subTest(scenario=scenario), self.assertRaises(ValueError):
                evidence.parse(raw(scenario, count), scenario, NONCE)
        template["payload"] = {"inert": "x" * evidence.MAX_EVENT_BYTES}
        with self.assertRaises(ValueError):
            evidence.parse(raw("successor-renewal-v1", 1), "successor-renewal-v1", NONCE)

    def test_final_cut_keeps_some_zero_separate_from_an_absent_time(self):
        records = ContinuityRecords("successor-renewal-v1")
        raw = bytearray(records.event("kernel_launch_saved")["retirement_receipt"])
        struct.pack_into("<Q", raw, 24, 7)
        struct.pack_into("<Q", raw, 120, 3)
        present = retirement_receipt(list(raw), records.boot)
        self.assertEqual(present["evaluated_ns"], 0)
        struct.pack_into("<Q", raw, 120, 1)
        absent = retirement_receipt(list(raw), records.boot)
        self.assertIsNone(absent["evaluated_ns"])
        self.assertNotEqual(present["raw"], absent["raw"])


if __name__ == "__main__":
    unittest.main()
