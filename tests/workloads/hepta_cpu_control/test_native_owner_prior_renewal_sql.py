"""Host-only SQLite/WAL negatives for the new read-only forensic checker.

The deliberately inert rows are not Hepta owner output. No test here is a
guest receipt, an original factory run, or native/persistent qualification.
"""
import copy
import hashlib
from pathlib import Path
import sqlite3
import struct
import tempfile
import unittest

import native_owner_evidence as e
import native_owner_inputs as inputs
import native_owner_prior_boot_store as old
import native_owner_prior_renewal_sql as checker
from test_native_owner_prior_boot_store import KEY, LEASE, OWNER, fixture


class PriorRenewalSQLTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="inert-prior-renewal-")
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name).resolve() / "inert.sqlite3"
        self.connection = sqlite3.connect(self.database)
        self.addCleanup(self.connection.close)
        raw, _, self.insert = fixture(self.connection)
        self.previous = old.observe_extracted_database(self.database, inputs.sha(self.database), None, OWNER, KEY, raw)
        self.connection.row_factory = sqlite3.Row
        self.previous["lease_rows"] = checker.observe_initial_lease(self.connection, self.previous, [])
        original = self.previous["lease_rows"][0]
        expired = {**original, "lease_sequence": 2, "state": "rolled_back",
                   "previous_sha256": original["lease_sha256"], "recorded_at_unix_seconds": 20}
        expired["lease_sha256"] = old.row_digest(expired, "lease")
        self.insert("cognitive_local_leases", expired)
        self.operations, self.releases = [], []
        for generation in range(2, 7):
            binding = {"lease_id": LEASE, "generation": generation, "authority_epoch": 1, "owner_epoch": generation,
                       "authority_grant_digest": hashlib.sha256(f"inert-proof-{generation}".encode()).hexdigest(),
                       "fencing_token_digest": hashlib.sha256(f"inert-fence-{generation}".encode()).hexdigest(),
                       "expires_at_unix_seconds": 20 + generation}
            active = self.append_lease(binding, "active")
            if generation % 2 == 0:
                self.operations.append(self.append_operation(binding, len(self.operations)))
            released = self.append_lease(binding, "released")
            self.releases.append({"binding": binding, "receipt": {
                "schema_version": 1, "namespace": "production_durable_writer", "lease_id": LEASE,
                "owner_agent_id": OWNER, "generation": generation, "authority_epoch": 1,
                "owner_epoch": generation, "authority_grant_digest": binding["authority_grant_digest"],
                "state": "released", "lease_head_digest": released["lease_sha256"], "external_effect": False}})
            self.assertEqual(active["generation"], released["generation"])
        self.connection.commit()

    def last(self, table, ordering):
        return dict(self.connection.execute("SELECT * FROM " + table + " ORDER BY " + ordering + " DESC LIMIT 1").fetchone())

    def append_lease(self, binding, state):
        previous = self.last("cognitive_local_leases", "lease_sequence")
        row = {"lease_id": LEASE, "lease_sequence": previous["lease_sequence"] + 1,
               "owner_agent_id": OWNER, "generation": binding["generation"],
               "fencing_token": binding["fencing_token_digest"], "state": state,
               "previous_sha256": previous["lease_sha256"], "recorded_at_unix_seconds": binding["generation"],
               "authority_epoch": 1, "owner_epoch": binding["owner_epoch"],
               "lease_expires_at_unix_seconds": binding["expires_at_unix_seconds"]}
        row["lease_sha256"] = old.row_digest(row, "lease")
        self.insert("cognitive_local_leases", row)
        return row

    def append_event(self, base, key, kind, payload):
        previous = self.last("cognitive_local_events", "event_sequence")
        sequence = previous["event_sequence"] + 1
        row = {**base, "event_sequence": sequence, "event_id": f"inert-event-{sequence}",
               "occurrence_key": key, "event_kind": kind, "payload_json": payload,
               "payload_sha256": hashlib.sha256(payload.encode()).hexdigest(),
               "previous_sha256": previous["event_sha256"], "recorded_at_unix_seconds": base["generation"]}
        row["event_sha256"] = old.row_digest(row, "event")
        self.insert("cognitive_local_events", row)
        return row

    def append_operation(self, binding, index):
        key = f"inert-renewal-operation-{index}"
        request = {"schema_version": 1, "delivery": {"boot_id": [4] * 16, "space_id": [10 + index] * 16,
                   "sequence": "0000000000000001"}, "manage_slot": 2, "manage_generation": 1,
                   "expected_revision": index + 1, "period_ns": e.PERIOD_NS, "cap_ns": 25_000_000}
        raw = e.canonical(request)
        base = {"lease_id": LEASE, "owner_agent_id": OWNER, "generation": binding["generation"],
                "fencing_token": binding["fencing_token_digest"]}
        admitted = self.append_event(base, key, "admitted", raw)
        self.append_event(base, key, "indeterminate", "dispatch_started_pending_ack:" + "a" * 64)
        prior_outbox = self.last("cognitive_local_outbox", "outbox_sequence")
        outbox = {**base, "outbox_sequence": prior_outbox["outbox_sequence"] + 1,
                  "outbox_id": f"inert-outbox-{index}", "event_id": admitted["event_id"], "occurrence_key": key,
                  "topic": "hepta.hos2.install-budget.v1", "payload_json": raw,
                  "payload_sha256": admitted["payload_sha256"], "dispatch_state": "queued",
                  "recorded_at_unix_seconds": binding["generation"], "previous_sha256": prior_outbox["outbox_sha256"]}
        outbox["outbox_sha256"] = old.row_digest(outbox, "outbox")
        self.insert("cognitive_local_outbox", outbox)
        operation = {**base, "operation_id": key, "subject_id": OWNER, "destination_id": "hos2.cpu-budget.v1",
                     "payload_sha256": outbox["payload_sha256"], "policy_generation": 1,
                     "scope_sha256": hashlib.sha256(b"hepta.hos2.cpu-budget.scope.v1\0" + bytes([4] * 16)
                        + bytes([10 + index] * 16) + struct.pack("<QQ", 2, 1)).hexdigest(),
                     "expected_predecessor_sha256": None, "event_id": admitted["event_id"],
                     "outbox_id": outbox["outbox_id"], "authority_epoch": 1,
                     "owner_epoch": binding["owner_epoch"], "prepared_at_unix_seconds": binding["generation"]}
        operation["semantic_sha256"] = old.operation_semantic_digest(operation)
        self.insert("cognitive_operation_ledger", operation)
        prior = hashlib.sha256(b"hepta:kernel.operations:dispatch-claim:genesis:v1").hexdigest()
        for sequence, state in ((1, "claimed"), (2, "entered")):
            claim = {"operation_id": key, "claim_sequence": sequence, "attempt": 1,
                     "owner_generation": binding["generation"], "fencing_token": base["fencing_token"],
                     "claim_state": state, "lease_expires_at_unix_ms": 1000, "next_eligible_at_unix_ms": 2000,
                     "previous_sha256": prior, "recorded_at_unix_ms": binding["generation"]}
            claim["claim_sha256"] = self.claim_digest(claim)
            prior = claim["claim_sha256"]
            self.insert("cognitive_operation_dispatch_claims", claim)
        observation = {"state": "applied", "stable_object_id": [9] * 16, "previous_revision": index + 1,
                       "revision": index + 2, "effective_ns": 101 + index, "consumed_ns": 1}
        terminal_json = e.canonical({"schema_version": 1, "request": request, "observation": observation})
        terminal = self.append_event(base, key, "reconcile_committed", terminal_json)
        return {"key": key, "request_json": raw, "request": request, "observation": observation,
                "source_event": terminal["event_id"], "terminal": terminal_json}

    @staticmethod
    def claim_digest(row):
        parts = [old.utf8(row["operation_id"]), old.u64(row["claim_sequence"]), struct.pack(">I", row["attempt"]),
                 old.u64(row["owner_generation"]), old.utf8(row["fencing_token"]), old.utf8(row["claim_state"]),
                 old.u64(row["lease_expires_at_unix_ms"]), old.u64(row["next_eligible_at_unix_ms"]),
                 old.utf8(row["previous_sha256"])]
        return old.framed(b"hepta:kernel.operations:dispatch-claim:v1", parts)

    def read(self):
        wal = self.database.with_name(self.database.name + "-wal")
        before = {path: inputs.sha(path) for path in (self.database, wal) if path.exists()}
        connection = sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True)
        try:
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.enable_load_extension(False)
            connection.execute("BEGIN")
            queries = []
            result = checker.observe(connection, self.previous, self.operations, self.releases, queries)
            self.assertEqual(len(queries), 5)
            connection.rollback()
        finally:
            connection.close()
            self.assertEqual(before, {path: inputs.sha(path) for path in before})
        return result

    def test_complete_unknown_and_three_effects_survive_five_actual_readonly_release_observations(self):
        result = self.read()
        self.assertEqual(result["old_unknown"]["events"], self.previous["events"])
        self.assertEqual(result["released_generations"], [2, 3, 4, 5, 6])
        self.assertEqual(len(result["new_committed_operations"]), 3)
        self.assertEqual(result["original_expired_lease"]["state"], "rolled_back")
        self.assertIs(result["native_execution_verified"], False)
        self.assertIs(result["old_terminal_absent"], True)

    def test_missing_middle_recovery_release_cannot_be_hidden_by_final_manager_release(self):
        self.connection.execute("DELETE FROM cognitive_local_leases WHERE generation=3 AND state='released'")
        self.connection.commit()
        with self.assertRaises(ValueError):
            self.read()

    def test_original_expiry_cannot_be_reported_as_an_old_operation_terminal_or_graceful_release(self):
        rows = [dict(row) for row in self.connection.execute("SELECT * FROM cognitive_local_leases ORDER BY lease_sequence")]
        rows[1]["state"] = "released"
        self.rewrite_leases(rows)
        with self.assertRaisesRegex(ValueError, "expire the exact old lease"):
            self.read()

    def rewrite_leases(self, rows):
        self.connection.execute("DELETE FROM cognitive_local_leases")
        previous = hashlib.sha256(b"hepta-memory:local-lease:genesis:v1").hexdigest()
        for sequence, row in enumerate(rows, 1):
            row.update(lease_sequence=sequence, previous_sha256=previous)
            row["lease_sha256"] = old.row_digest(row, "lease")
            previous = row["lease_sha256"]
            self.insert("cognitive_local_leases", row)
        self.connection.commit()

    def test_two_consecutive_active_rows_cannot_masquerade_as_a_successful_new_owner(self):
        rows = [dict(row) for row in self.connection.execute("SELECT * FROM cognitive_local_leases ORDER BY lease_sequence")]
        rows.insert(3, dict(rows[2]))
        self.rewrite_leases(rows)
        with self.assertRaisesRegex(ValueError, "terminal-to-next-generation CAS"):
            self.read()

    def test_first_physical_lease_preimage_cannot_be_replaced_by_a_later_inference(self):
        self.previous["lease_rows"][0]["recorded_at_unix_seconds"] += 1
        with self.assertRaisesRegex(ValueError, "expire the exact old lease"):
            self.read()

    def test_effectless_recovery_cannot_reuse_a_previous_active_fence(self):
        rows = [dict(row) for row in self.connection.execute("SELECT * FROM cognitive_local_leases ORDER BY lease_sequence")]
        token = rows[2]["fencing_token"]
        for row in rows:
            if row["generation"] == 3:
                row["fencing_token"] = token
        self.rewrite_leases(rows)
        with self.assertRaisesRegex(ValueError, "reused a prior active fencing token"):
            self.read()

    def test_real_wal_only_old_terminal_is_not_ignored(self):
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA wal_autocheckpoint=0")
        prior = self.previous["operation"]
        self.append_event({key: prior[key] for key in ("lease_id", "owner_agent_id", "generation", "fencing_token")},
                          KEY, "reconcile_committed", self.operations[0]["terminal"])
        self.connection.commit()
        self.assertGreater(self.database.with_name(self.database.name + "-wal").stat().st_size, 0)
        with self.assertRaisesRegex(ValueError, "missing, duplicated or unobserved"):
            self.read()

    def test_hidden_or_duplicated_new_operation_is_rejected(self):
        self.connection.execute("INSERT INTO cognitive_operation_ledger SELECT * FROM cognitive_operation_ledger LIMIT 1")
        self.connection.commit()
        with self.assertRaisesRegex(ValueError, "missing, duplicated or unobserved"):
            self.read()

    def test_original_terminal_event_and_every_release_head_must_match_actual_observations(self):
        original_operations, original_releases = copy.deepcopy(self.operations), copy.deepcopy(self.releases)
        for changed in ("event", "terminal", "middle-release", "future-generation", "owner-epoch"):
            self.operations, self.releases = copy.deepcopy(original_operations), copy.deepcopy(original_releases)
            if changed == "event":
                self.operations[1]["source_event"] += "-changed"
            elif changed == "terminal":
                self.operations[1]["terminal"] = self.operations[0]["terminal"]
            elif changed == "middle-release":
                self.releases[1]["receipt"]["lease_head_digest"] = "ab" * 32
            elif changed == "future-generation":
                self.releases[1]["receipt"]["generation"] = 99
            else:
                self.releases[1]["binding"]["owner_epoch"] += 1
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.read()

    def test_same_effect_cannot_be_relabelled_as_a_recovery_owner_operation(self):
        self.operations[0], self.operations[1] = self.operations[1], self.operations[0]
        with self.assertRaisesRegex(ValueError, "owner generation or fence"):
            self.read()

    def test_original_secondary_settlement_is_checked_without_requiring_it(self):
        key = self.operations[1]["key"]
        prior = dict(self.connection.execute("SELECT * FROM cognitive_operation_dispatch_claims "
                                            "WHERE operation_id=? ORDER BY claim_sequence DESC LIMIT 1", (key,)).fetchone())
        settled = {**prior, "claim_sequence": prior["claim_sequence"] + 1, "claim_state": "settled",
                   "previous_sha256": prior["claim_sha256"]}
        settled["claim_sha256"] = self.claim_digest(settled)
        self.insert("cognitive_operation_dispatch_claims", settled)
        self.connection.commit()
        self.assertTrue(self.read()["new_committed_operations"][1]["secondary_settled_claim_present"])
        self.connection.execute("UPDATE cognitive_operation_dispatch_claims SET claim_sha256=? "
                                "WHERE operation_id=? AND claim_state='settled'", ("aa" * 32, key))
        self.connection.commit()
        with self.assertRaisesRegex(ValueError, "secondary settlement digest"):
            self.read()

    def test_intermediate_material_prefixes_cannot_be_used_as_a_complete_campaign(self):
        complete = checker.read_rows(self.connection, [])
        for count in (1, 2):
            rows = copy.deepcopy(complete)
            allowed = {KEY, self.operations[0]["key"]}
            for table in ("cognitive_local_events", "cognitive_local_outbox"):
                rows[table] = [row for row in rows[table] if row["occurrence_key"] in allowed]
            for table in ("cognitive_operation_ledger", "cognitive_operation_dispatch_claims"):
                rows[table] = [row for row in rows[table] if row["operation_id"] in allowed]
            rows["cognitive_local_leases"] = [row for row in rows["cognitive_local_leases"] if row["generation"] <= count + 1]
            with self.subTest(releases=count):
                result = checker.verify_rows(rows, self.previous, self.operations[:1], self.releases[:count], partial=True)
                self.assertEqual(len(result["released_generations"]), count)
                self.assertFalse(result["native_execution_verified"])
                with self.assertRaisesRegex(ValueError, "bounded actual Manager effects"):
                    checker.verify_rows(rows, self.previous, self.operations[:1], self.releases[:count])


if __name__ == "__main__":
    unittest.main()
