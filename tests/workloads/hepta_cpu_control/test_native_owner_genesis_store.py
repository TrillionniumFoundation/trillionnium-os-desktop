"""Actual temporary SQLite/WAL reads with inert data, never native evidence."""
import hashlib
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

import native_owner_genesis_store as original
import native_owner_inputs as inputs
import native_owner_prior_boot_types as fixed


# Independently enumerated and framed SQL rows, including every SQLite type
# and the actual implicit migration index. These are parser-test constants,
# not production CognitiveStore material or a source qualification receipt.
SCHEMA = "7ab519295f812a5aa988e1c43059a075b433980c2d4faba3e6b123c9accec658"
STATE = "dc5ddcfecf47a3811d45a9d9dad1b5a5a3d5838a2c41d33e2ec64840c913de4f"
SOURCE = ('''const REQUIRED_SCHEMA_OBJECTS: &[(&str, &str)] = &[
    ("cognitive_meta", "table"),
    ("evidence", "table"),
    ("evidence_key", "index"),
];
const REQUIRED_SCHEMA_ORACLE_SHA256: &str = "''' + SCHEMA + '";\n').encode()
ANCHOR = {"profile": "hepta:cognitive:exact-current-cut:v1", "owner_agent_id": fixed.AGENT,
          "schema_digest": SCHEMA, "state_digest": STATE}


def fixture(path):
    connection = sqlite3.connect(path)
    for statement in (
        "CREATE TABLE cognitive_meta (singleton INTEGER PRIMARY KEY, owner_agent_id TEXT NOT NULL)",
        "CREATE TABLE evidence (i INTEGER, r REAL, t TEXT, b BLOB, z)",
        "CREATE TABLE _sqlx_migrations (version BIGINT PRIMARY KEY, description TEXT NOT NULL)",
        "CREATE INDEX evidence_key ON evidence(i)",
    ):
        connection.execute(statement)
    connection.execute("INSERT INTO cognitive_meta VALUES(1,?)", (fixed.AGENT,))
    connection.execute("INSERT INTO evidence VALUES(-7,1.25,?,?,NULL)", ("原始材料", bytes([0, 1, 255])))
    connection.execute("INSERT INTO _sqlx_migrations VALUES(1,'inert host test only')")
    connection.commit()
    return connection


class OriginalExactMaterialTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="inert-genesis-sqlite-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.database = self.root / "original.sqlite3"
        self.connection = fixture(self.database)
        self.addCleanup(self.connection.close)
        self.inventory = original.inventory(SOURCE)

    def test_actual_readonly_sqlite_matches_all_typed_golden_rows_and_preserves_bytes(self):
        before = inputs.sha(self.database)
        result = original.observe(self.database, before, None, self.inventory, ANCHOR)
        self.assertEqual(result["anchor"], ANCHOR)
        self.assertEqual(result["logical_rows"], 8)
        self.assertEqual(inputs.sha(self.database), before)
        self.assertFalse(result["native_execution_verified"])
        self.assertFalse(result["checkpoint_or_current_created"])
        self.assertEqual(result["table_rows"]["sqlite_schema"], 5)

    def test_actual_wal_only_mutation_cannot_be_hidden_by_old_database_bytes(self):
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA wal_autocheckpoint=0")
        self.connection.execute("UPDATE evidence SET i=1000")
        self.connection.commit()
        extraction = self.root / "copy"
        extraction.mkdir(mode=0o700)
        copied = extraction / "original.sqlite3"
        wal = copied.with_name(copied.name + "-wal")
        shutil.copyfile(self.database, copied)
        # Without the physical WAL, these old main-file bytes still name the
        # old anchor. The production extraction must carry the actual WAL.
        before = inputs.sha(copied)
        self.assertEqual(original.observe(copied, before, None, self.inventory, ANCHOR)["anchor"], ANCHOR)
        shutil.copyfile(self.database.with_name(self.database.name + "-wal"), wal)
        wal_before = inputs.sha(wal)
        with self.assertRaisesRegex(ValueError, "independently retained exact cut"):
            original.observe(copied, before, wal_before, self.inventory, ANCHOR)
        self.assertEqual((inputs.sha(copied), inputs.sha(wal)), (before, wal_before))

    def test_unregistered_table_and_nonrequired_trigger_are_not_ignored(self):
        self.connection.execute("CREATE TABLE unexpected (value TEXT)")
        self.connection.commit()
        with self.assertRaisesRegex(ValueError, "unregistered logical tables"):
            original.observe(self.database, inputs.sha(self.database), None, self.inventory, ANCHOR)
        self.connection.execute("DROP TABLE unexpected")
        self.connection.execute("CREATE TRIGGER unexpected AFTER INSERT ON evidence BEGIN SELECT 1; END")
        self.connection.commit()
        with self.assertRaisesRegex(ValueError, "independently retained exact cut"):
            original.observe(self.database, inputs.sha(self.database), None, self.inventory, ANCHOR)

    def test_source_inventory_does_not_evaluate_or_skip_unknown_rust_expressions(self):
        for changed in (SOURCE.replace(b'("evidence", "table"),', b'include!("other.rs"),'),
                        SOURCE + SOURCE,
                        SOURCE.replace(b'("evidence", "table"),', b'("cognitive_meta", "table"),')):
            with self.subTest(source=hashlib.sha256(changed).hexdigest()), self.assertRaises(ValueError):
                original.inventory(changed)


if __name__ == "__main__":
    unittest.main()
