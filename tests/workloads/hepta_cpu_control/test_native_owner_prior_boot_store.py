"""Actual host SQLite/WAL I/O regressions; no original writer or native claim.

The inert rows below exercise the forensic reader only. They are deliberately
not accepted as a guest transcript, retained production database or receipt.
"""
import hashlib
import copy
from pathlib import Path
import shutil
import sqlite3
import struct
import tempfile
import unittest

import native_owner_evidence as e
import native_owner_inputs as inputs
import native_owner_prior_boot_store as s


OWNER = "018f4f72-5f8f-7cc1-8f55-df9fb3aa2c13"
KEY = "offline-forensic-test-only"
LEASE = "offline-lease"


def fixture(connection):
    # Small host schema for SQL transport tests, not the Hepta schema/factory.
    sets = (("cognitive_local_leases", s.LEASE_COLUMNS), ("cognitive_local_events", s.EVENT_COLUMNS),
            ("cognitive_local_outbox", s.OUTBOX_COLUMNS), ("cognitive_operation_ledger", s.OPERATION_COLUMNS),
            ("cognitive_operation_dispatch_claims", s.CLAIM_COLUMNS))
    integers = {"lease_sequence", "event_sequence", "outbox_sequence", "generation", "authority_epoch", "owner_epoch",
                "lease_expires_at_unix_seconds", "recorded_at_unix_seconds", "policy_generation", "prepared_at_unix_seconds",
                "claim_sequence", "attempt", "owner_generation", "lease_expires_at_unix_ms", "next_eligible_at_unix_ms",
                "recorded_at_unix_ms"}
    for name, columns in sets:
        connection.execute("CREATE TABLE " + name + " (" + ", ".join(key + (" INTEGER" if key in integers else " TEXT")
                                                                           for key in columns) + ") STRICT")
    def insert(table, value):
        connection.execute("INSERT INTO " + table + " (" + ", ".join(value) + ") VALUES ("
                           + ",".join("?" for _ in value) + ")", tuple(value.values()))
    raw = e.canonical({"schema_version": 1, "delivery": {"boot_id": [1] * 16, "space_id": [2] * 16,
                         "sequence": "0000000000000001"}, "manage_slot": 2, "manage_generation": 1,
                       "expected_revision": 1, "period_ns": e.PERIOD_NS, "cap_ns": 25_000_000})
    base = {"lease_id": LEASE, "owner_agent_id": OWNER, "generation": 1, "fencing_token": "offline-fence"}
    lease = {**base, "lease_sequence": 1, "state": "active", "authority_epoch": 1, "owner_epoch": 1,
             "lease_expires_at_unix_seconds": 20, "recorded_at_unix_seconds": 1,
             "previous_sha256": hashlib.sha256(b"hepta-memory:local-lease:genesis:v1").hexdigest()}
    lease["lease_sha256"] = s.row_digest(lease, "lease")
    insert("cognitive_local_leases", lease)
    previous = hashlib.sha256(b"hepta-memory:local-event:genesis:v1").hexdigest()
    events = []
    for seq, kind, payload in ((1, "admitted", raw), (2, "indeterminate", "dispatch_started_pending_ack:" + "a" * 64)):
        event = {**base, "event_sequence": seq, "event_id": "offline-event-" + str(seq), "occurrence_key": KEY,
                 "event_kind": kind, "payload_json": payload, "payload_sha256": hashlib.sha256(payload.encode()).hexdigest(),
                 "previous_sha256": previous, "recorded_at_unix_seconds": 1}
        event["event_sha256"] = s.row_digest(event, "event")
        previous = event["event_sha256"]
        events.append(event)
        insert("cognitive_local_events", event)
    outbox = {**base, "outbox_sequence": 1, "outbox_id": "offline-outbox", "event_id": events[0]["event_id"],
              "occurrence_key": KEY, "topic": "hepta.hos2.install-budget.v1", "payload_json": raw,
              "payload_sha256": events[0]["payload_sha256"], "dispatch_state": "queued", "recorded_at_unix_seconds": 1,
              "previous_sha256": hashlib.sha256(b"hepta-memory:local-outbox:genesis:v1").hexdigest()}
    outbox["outbox_sha256"] = s.row_digest(outbox, "outbox")
    insert("cognitive_local_outbox", outbox)
    op = {**base, "operation_id": KEY, "subject_id": OWNER, "destination_id": "hos2.cpu-budget.v1",
          "payload_sha256": outbox["payload_sha256"],
          "scope_sha256": hashlib.sha256(b"hepta.hos2.cpu-budget.scope.v1\0" + bytes([1] * 16) + bytes([2] * 16)
                                         + struct.pack("<QQ", 2, 1)).hexdigest(),
          "policy_generation": 1, "expected_predecessor_sha256": None, "event_id": outbox["event_id"],
          "outbox_id": outbox["outbox_id"], "authority_epoch": 1, "owner_epoch": 1, "prepared_at_unix_seconds": 1}
    op["semantic_sha256"] = s.operation_semantic_digest(op)
    insert("cognitive_operation_ledger", op)
    previous = hashlib.sha256(b"hepta:kernel.operations:dispatch-claim:genesis:v1").hexdigest()
    for seq, kind in ((1, "claimed"), (2, "entered")):
        claim = {"operation_id": KEY, "claim_sequence": seq, "attempt": 1, "owner_generation": 1,
                 "fencing_token": base["fencing_token"], "claim_state": kind, "lease_expires_at_unix_ms": 1000,
                 "next_eligible_at_unix_ms": 2000, "previous_sha256": previous, "recorded_at_unix_ms": 1}
        parts = [KEY.encode(), struct.pack(">Q", seq), struct.pack(">I", 1), struct.pack(">Q", 1),
                 base["fencing_token"].encode(), kind.encode(), struct.pack(">Q", 1000), struct.pack(">Q", 2000), previous.encode()]
        claim["claim_sha256"] = s.framed(b"hepta:kernel.operations:dispatch-claim:v1", parts)
        previous = claim["claim_sha256"]
        insert("cognitive_operation_dispatch_claims", claim)
    connection.commit()
    return raw, events, insert


class ActualSQLiteForensicTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()

    def tearDown(self):
        self.temp.cleanup()

    def observe(self, database, raw):
        wal = database.with_name(database.name + "-wal")
        return s.observe_extracted_database(database, inputs.sha(database), inputs.sha(wal) if wal.exists() else None,
                                            OWNER, KEY, raw)

    def test_empty_existing_wal_is_preserved_and_never_claims_native_execution(self):
        database = self.root / "fixture.sqlite3"
        connection = sqlite3.connect(database)
        raw, _, _ = fixture(connection)
        connection.close()
        wal = database.with_name(database.name + "-wal")
        wal.write_bytes(b"")
        result = self.observe(database, raw)
        self.assertEqual(result["observed_state"], "indeterminate")
        self.assertEqual(result["terminal_event_count"], 0)
        self.assertIs(result["native_execution_verified"], False)
        self.assertEqual(wal.read_bytes(), b"")

    def test_terminal_committed_only_to_wal_is_not_hidden_by_an_old_main_database(self):
        database = self.root / "active.sqlite3"
        connection = sqlite3.connect(database)
        raw, events, insert = fixture(connection)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA wal_autocheckpoint=0")
        terminal = {**events[-1], "event_sequence": 3, "event_id": "offline-late-terminal",
                    "event_kind": "reconcile_committed", "payload_json": "offline late terminal only",
                    "previous_sha256": events[-1]["event_sha256"]}
        terminal["payload_sha256"] = hashlib.sha256(terminal["payload_json"].encode()).hexdigest()
        terminal["event_sha256"] = s.row_digest(terminal, "event")
        insert("cognitive_local_events", terminal)
        connection.commit()
        try:
            omitted = self.root / "omitted.sqlite3"
            actual = self.root / "actual.sqlite3"
            shutil.copyfile(database, omitted)
            shutil.copyfile(database, actual)
            shutil.copyfile(database.with_name(database.name + "-wal"), actual.with_name(actual.name + "-wal"))
            self.assertEqual(self.observe(omitted, raw)["observed_state"], "indeterminate")
            with self.assertRaisesRegex(ValueError, "terminal, rollback"):
                self.observe(actual, raw)
        finally:
            connection.close()

    def test_operation_semantics_and_another_lease_outbox_cannot_be_substituted(self):
        database = self.root / "fixture.sqlite3"
        connection = sqlite3.connect(database)
        raw, _, _ = fixture(connection)
        connection.execute("UPDATE cognitive_operation_ledger SET semantic_sha256=?", ("f" * 64,))
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(ValueError, "semantic digest"):
            self.observe(database, raw)
        connection = sqlite3.connect(database)
        original = dict(zip(s.OPERATION_COLUMNS, connection.execute("SELECT " + ",".join(s.OPERATION_COLUMNS)
                            + " FROM cognitive_operation_ledger").fetchone()))
        connection.execute("UPDATE cognitive_operation_ledger SET semantic_sha256=?", (s.operation_semantic_digest(original),))
        row = connection.execute("SELECT " + ",".join(s.OUTBOX_COLUMNS) + " FROM cognitive_local_outbox").fetchone()
        hidden = dict(zip(s.OUTBOX_COLUMNS, row))
        hidden["lease_id"] = "different-hidden-lease"
        connection.execute("INSERT INTO cognitive_local_outbox (" + ",".join(hidden) + ") VALUES ("
                           + ",".join("?" for _ in hidden) + ")", tuple(hidden.values()))
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(ValueError, "hidden outbox"):
            self.observe(database, raw)

    def test_boot_mismatch_unavailable_cannot_append_a_new_unknown_event(self):
        database = self.root / "fixture.sqlite3"
        connection = sqlite3.connect(database)
        raw, _, _ = fixture(connection)
        connection.close()
        first = self.observe(database, raw)
        self.assertEqual(s.preserved_unknown(first, first)["new_unknown_observations"], 0)
        changed = copy.deepcopy(first)
        changed["events"].append({**changed["events"][-1], "event_kind": "reconcile_still_indeterminate"})
        with self.assertRaisesRegex(ValueError, "boot-mismatch observer appended"):
            s.preserved_unknown(first, changed)


if __name__ == "__main__":
    unittest.main()
