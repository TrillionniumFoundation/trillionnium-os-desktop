"""New two-boot continuation parser checks; no native qualification here."""
import copy
import json
import unittest

import native_owner_evidence as e
import native_owner_prior_renewal_evidence as oracle
from native_owner_continuity_test_records import ContinuityRecords
from native_owner_prior_renewal_test_records import pair
from test_native_owner_evidence import ELF, NONCE


class PriorUnknownRenewalEvidenceTests(unittest.TestCase):
    def test_complete_new_inert_stream_keeps_native_acceptance_false(self):
        first, second = pair()
        a, b = first.evaluate(), second.evaluate()
        self.assertEqual((a["phase"], b["phase"]), ("fresh", "retained"))
        self.assertEqual(b["manager_cycles"], 3)
        self.assertEqual(len(b["original_releases"]), 5)
        self.assertEqual(len(b["retained_old_observations"]), 10)
        self.assertEqual(b["fresh_kernel_generations"], [1, 2])
        self.assertEqual(b["unresolved_old_drain_blockers"], 1)
        self.assertNotEqual(b["terminal_current"]["token"], b["final_current"]["token"])
        for key in ("passed", "original_native_owner_cycle_verified", "cross_boot_unknown_preservation_verified",
                    "graceful_owner_release_verified", "activation_witness_files_verified", "root_launch_files_verified",
                    "kill_within_guest_callback_window_proven", "power_loss_verified", "g2_complete", "production_ready"):
            self.assertFalse(b[key], key)

    def test_every_start_and_stop_requires_the_actual_unchanged_old_observation(self):
        for event in ("continuity_owner", "owner_released"):
            for change in ("missing", "phase", "old-state", "old-payload", "old-ioctl", "drain", "terminal-error"):
                _, records = pair()
                value = records.event(event, 2)
                retained = value["retained_prior_boot"]
                if change == "missing": value.pop("retained_prior_boot")
                elif change == "phase": retained["phase"] = "after_stop"
                elif change == "old-state": retained["observation"]["after"]["state"] = "committed"
                elif change == "old-payload": retained["observation"]["request_json"] += " "
                elif change == "old-ioctl": retained["observation"]["calls_after"]["query_ioctl_count"] += 1
                elif change == "drain": retained["observation"]["drain_blockers"] = 0
                else: retained["terminal_lookup"]["reason"] = "unrelated failure"
                with self.subTest(event=event, change=change), self.assertRaises(ValueError):
                    records.evaluate()

    def test_new_real_effect_namespace_and_each_private_owner_database_are_required(self):
        for case in ("reuse-inode", "change-path", "startup", "manager-count", "recovery-install"):
            _, records = pair()
            owner = records.event("continuity_owner", 2)["retained_prior_boot"]
            if case == "reuse-inode":
                owner["transport"]["database_inode"] = records.event("continuity_owner")["retained_prior_boot"]["transport"]["database_inode"]
            elif case == "change-path":
                records.event("owner_released", 2)["retained_prior_boot"]["transport"]["database_path"] += "changed.sqlite3"
            elif case == "startup": owner["transport"]["startup_retained"] = []
            elif case == "manager-count":
                records.event("owner_released", 2)["retained_prior_boot"]["transport"]["ioctl_counts"]["install_ioctl_count"] = 0
            else:
                records.event("owner_released", 1)["retained_prior_boot"]["transport"]["ioctl_counts"]["install_ioctl_count"] = 1
            with self.subTest(case=case), self.assertRaises(ValueError):
                records.evaluate()

    def test_cold_root_lease_has_new_lifetime_but_preserves_original_installation_scope(self):
        _, records = pair()
        initial = records.event("continuity_owner")
        self.assertTrue(initial["root_lease"]["lease_id"].startswith("native-cpu.root." + records.linux_boot))
        _, changed = pair()
        changed.event("continuity_owner")["root_lease"]["lease_id"] = "native-cpu-root-installation"
        with self.assertRaises(ValueError):
            changed.evaluate()
        _, changed = pair()
        changed.event("continuity_owner")["root_lease"]["binding"]["scope_sha256"][0] ^= 1
        with self.assertRaises(ValueError):
            changed.evaluate()

    def test_final_observation_and_actual_release_reap_cannot_be_replaced_by_poweroff(self):
        for case in ("authority-missing", "old-sequence", "final-query", "no-release", "no-reap", "final-token", "root-dirty"):
            _, records = pair()
            final = records.event("prior_boot_observed", 1)
            if case == "authority-missing": final.pop("authority")
            elif case == "old-sequence": final["authority"]["issuer_sequence"] -= 1
            elif case == "final-query": final["observation"]["calls_after"]["query_ioctl_count"] += 1
            elif case == "no-release": records.event("owner_released", 4)["receipt"]["state"] = "active"
            elif case == "no-reap": records.event("owner_stopped", 4)["supervisor"]["events"][-1]["details"] = {"success": False, "code": None}
            elif case == "final-token": records.event("complete")["final_current_token"] = records.event("owner_released", 4)["current"]["token"]
            else: records.event("owner_released", 4)["current"]["head"]["phase"] = "dirty"
            with self.subTest(case=case), self.assertRaises(ValueError):
                records.evaluate()

    def test_new_case_still_requires_330_seconds_two_fresh_pairs_and_each_ack_window(self):
        for case in ("threshold", "generation", "ack", "window"):
            _, records = pair()
            if case == "threshold": records.event("renewal_endpoint")["after_boottime_ns"] -= 30_000_000_000
            elif case == "generation": records.event("renewal_endpoint")["fresh_kernel_generations"] = [2]
            elif case == "ack": records.event("history_ack", 1)["retired_through"] = 0
            else: records.event("usage_window", 1)["second"] = copy.deepcopy(records.event("usage_window", 1)["first"])
            with self.subTest(case=case), self.assertRaises(ValueError):
                records.evaluate()

    def test_new_private_parser_admission_does_not_extend_old_scenario_schemas(self):
        first, _ = pair()
        with self.assertRaises(ValueError):
            e.evaluate(first.raw(), -9, False, False, oracle.SCENARIO, NONCE, ELF)
        with self.assertRaises(ValueError):
            e.parse(first.raw(), oracle.SCENARIO, NONCE)
        records = ContinuityRecords("successor-renewal-v1")
        records.event("continuity_owner")["retained_prior_boot"] = {}
        with self.assertRaises(ValueError):
            records.evaluate()
        records = ContinuityRecords("successor-renewal-v1")
        records.event("owner_released")["retained_prior_boot"] = {}
        with self.assertRaises(ValueError):
            records.evaluate()

    def test_only_private_new_case_gets_1024_events_and_original_byte_bounds(self):
        def raw(count, payload=None):
            return ("\n".join(e.PREFIX + json.dumps({"schema_version": 1, "scenario": oracle.SCENARIO,
                "nonce": NONCE, "event": "inert-limit-test", "sequence": index + 1, "payload": payload or {}})
                for index in range(count)) + "\n").encode()
        self.assertEqual(len(e._parse(raw(1024), oracle.SCENARIO, NONCE, True, prior_renewal=True)[1]), 1024)
        for value in (raw(1025), raw(1, {"oversized": "x" * e.MAX_EVENT_BYTES})):
            with self.assertRaises(ValueError):
                e._parse(value, oracle.SCENARIO, NONCE, True, prior_renewal=True)


if __name__ == "__main__":
    unittest.main()
