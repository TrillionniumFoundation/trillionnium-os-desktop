"""Real private SQLite reads over inert rows; no owner/native qualification."""
import copy
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

import native_owner_evidence as e
import native_owner_genesis_sql as sql
import native_owner_inputs as inputs
import native_owner_prior_boot_store as old
from test_native_owner_prior_boot_store import KEY, fixture


class OriginalFirstWriterSQLTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="inert-first-writer-sql-")
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name).resolve() / "original.sqlite3"
        self.connection = sqlite3.connect(self.database)
        self.addCleanup(self.connection.close)
        raw, events, insert = fixture(self.connection)
        self.connection.row_factory = sqlite3.Row
        request = e.request(raw)
        observation = {"state": "applied", "stable_object_id": [9] * 16, "previous_revision": 1,
                       "revision": 2, "effective_ns": 101, "consumed_ns": 1}
        terminal_json = e.canonical({"schema_version": 1, "request": request, "observation": observation})
        terminal = {**events[-1], "event_sequence": 3, "event_id": "inert-first-terminal", "event_kind": "reconcile_committed",
                    "payload_json": terminal_json, "payload_sha256": hashlib.sha256(terminal_json.encode()).hexdigest(),
                    "previous_sha256": events[-1]["event_sha256"]}
        terminal["event_sha256"] = old.row_digest(terminal, "event")
        insert("cognitive_local_events", terminal)
        lease = dict(self.connection.execute("SELECT * FROM cognitive_local_leases").fetchone())
        released = {**lease, "lease_sequence": 2, "state": "released", "recorded_at_unix_seconds": 2,
                    "previous_sha256": lease["lease_sha256"]}
        released["lease_sha256"] = old.row_digest(released, "lease")
        insert("cognitive_local_leases", released)
        self.connection.commit()
        self.operation = {"key": KEY, "request_json": raw, "request": request, "observation": observation,
                          "source_event": terminal["event_id"], "terminal": terminal_json}
        self.release = {"generation": 1, "authority_epoch": 1, "owner_epoch": 1, "lease_head_digest": released["lease_sha256"]}

    def read(self):
        before = inputs.sha(self.database)
        connection = sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True)
        try:
            connection.execute("PRAGMA query_only=ON")
            connection.execute("BEGIN")
            counts = {name: connection.execute("SELECT COUNT(*) FROM " + name).fetchone()[0] for name in sql.TABLES}
            queries = []
            result = sql.committed(connection, counts, self.operation, self.release, queries)
            self.assertEqual(len(queries), 5)
            connection.rollback()
        finally:
            connection.close()
        self.assertEqual(inputs.sha(self.database), before)
        return result

    def test_actual_readonly_original_admission_terminal_and_release_are_complete(self):
        result = self.read()
        self.assertEqual(result["observed_state"], "committed")
        self.assertEqual(result["terminal_event_count"], 1)
        self.assertFalse(result["secondary_settled_claim_present"])
        self.assertFalse(result["native_execution_verified"])

    def test_replacement_owner_epoch_two_uses_same_first_local_generation(self):
        leases = [dict(row) for row in self.connection.execute("SELECT * FROM cognitive_local_leases ORDER BY lease_sequence")]
        previous = leases[0]["previous_sha256"]
        for lease in leases:
            lease.update(owner_epoch=2, previous_sha256=previous)
            previous = old.row_digest(lease, "lease")
            self.connection.execute("UPDATE cognitive_local_leases SET owner_epoch=2,previous_sha256=?,lease_sha256=? WHERE lease_sequence=?",
                                    (lease["previous_sha256"], previous, lease["lease_sequence"]))
        operation = dict(self.connection.execute("SELECT * FROM cognitive_operation_ledger").fetchone())
        operation["owner_epoch"] = 2
        self.connection.execute("UPDATE cognitive_operation_ledger SET owner_epoch=2,semantic_sha256=?",
                                (old.operation_semantic_digest(operation),))
        self.connection.commit()
        self.release.update(owner_epoch=2, lease_head_digest=previous)
        result = self.read()
        self.assertEqual(result["operation"]["owner_epoch"], 2)
        self.assertTrue(all(value["generation"] == 1 for value in result["leases"]))

    def test_terminal_and_release_receipts_cannot_be_inferred_from_current_cap(self):
        for kind in ("event-id", "terminal", "lease-head", "owner-epoch"):
            before_op, before_release = copy.deepcopy(self.operation), copy.deepcopy(self.release)
            if kind == "event-id": self.operation["source_event"] += "changed"
            elif kind == "terminal": self.operation["terminal"] = self.operation["terminal"].replace('"revision":2', '"revision":3')
            elif kind == "lease-head": self.release["lease_head_digest"] = "ab" * 32
            else: self.release["owner_epoch"] = 2
            with self.subTest(kind=kind), self.assertRaises(ValueError): self.read()
            self.operation, self.release = before_op, before_release

    def test_hidden_operation_row_and_missing_original_table_are_not_ignored(self):
        self.connection.execute("INSERT INTO cognitive_operation_ledger SELECT * FROM cognitive_operation_ledger")
        self.connection.commit()
        with self.assertRaisesRegex(ValueError, "missing/extra"):
            self.read()
        for counts in ({name: 0 for name in sql.TABLES},):
            self.assertFalse(sql.empty(counts)["original_writer_present"])
            for name in sql.TABLES:
                changed = dict(counts)
                changed[name] = 1
                with self.subTest(table=name), self.assertRaises(ValueError): sql.empty(changed)
                changed.pop(name)
                with self.subTest(missing=name), self.assertRaises(ValueError): sql.empty(changed)


if __name__ == "__main__":
    unittest.main()
