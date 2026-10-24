"""Actual combined SQLite/WAL transactions with fixed inert anchor vectors."""
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

import native_owner_genesis_store as exact
import native_owner_inputs as inputs
import native_owner_prior_renewal_store as observed
import test_native_owner_prior_renewal_sql as journals
from test_native_owner_prior_boot_store import KEY, OWNER, fixture


# Independently framed golden bytes for the inert SQL fixtures, not the Hepta
# schema or a production Current. Tests never use these as source evidence.
SCHEMA = "e78664c3e23ef0ede7200e76cdf560b4e0736463458470d7383c27982ce60e3b"
FRESH = "38eaf166fec4df11bb63159d3c89298261e04130dadf06bec4aae343796d5f89"
FINAL = "25d92a8ba15b43e868f4ae95200dd3e7401e590f5af85666a1f3f8e6061616ea"
SOURCE = ('''const REQUIRED_SCHEMA_OBJECTS: &[(&str, &str)] = &[
    ("cognitive_local_events", "table"),
    ("cognitive_local_leases", "table"),
    ("cognitive_local_outbox", "table"),
    ("cognitive_meta", "table"),
    ("cognitive_operation_dispatch_claims", "table"),
    ("cognitive_operation_ledger", "table"),
];
const REQUIRED_SCHEMA_ORACLE_SHA256: &str = "''' + SCHEMA + '";\n').encode()


def metadata(connection):
    connection.execute("CREATE TABLE cognitive_meta (singleton INTEGER PRIMARY KEY, owner_agent_id TEXT NOT NULL)")
    connection.execute("CREATE TABLE _sqlx_migrations (version BIGINT PRIMARY KEY, description TEXT NOT NULL)")
    connection.execute("INSERT INTO cognitive_meta VALUES(1,?)", (OWNER,))
    connection.execute("INSERT INTO _sqlx_migrations VALUES(1,'inert host renewal test only')")
    connection.commit()


def anchor(state):
    return {"profile": exact.PROFILE, "owner_agent_id": OWNER, "schema_digest": SCHEMA, "state_digest": state}


class PriorRenewalExactStoreTests(unittest.TestCase):
    def test_actual_first_snapshot_checks_complete_anchor_and_original_unknown_prefix_together(self):
        with tempfile.TemporaryDirectory(prefix="inert-first-unknown-material-") as folder:
            path = Path(folder).resolve() / "original.sqlite3"
            connection = sqlite3.connect(path)
            try:
                raw, _, _ = fixture(connection)
                metadata(connection)
                before = inputs.sha(path)
                result = observed.observe(path, before, None, exact.inventory(SOURCE), anchor(FRESH),
                                           {"occurrence_key": KEY, "payload_json": raw})
            finally:
                connection.close()
            self.assertEqual(result["exact_material"]["anchor"], anchor(FRESH))
            self.assertEqual(result["exact_material"]["logical_rows"], 17)
            self.assertEqual(len(result["lease_rows"]), 1)
            self.assertEqual(result["observed_state"], "indeterminate")
            self.assertEqual(inputs.sha(path), before)
            self.assertFalse(result["passed"])
            self.assertFalse(result["native_execution_verified"])

    def material_fixture(self):
        fixture_case = journals.PriorRenewalSQLTests(
            "test_complete_unknown_and_three_effects_survive_five_actual_readonly_release_observations")
        self.addCleanup(fixture_case.doCleanups)
        fixture_case.setUp()
        metadata(fixture_case.connection)
        return fixture_case

    def test_actual_final_snapshot_binds_all_releases_and_unrelated_logical_tables(self):
        fixture_case = self.material_fixture()
        before = inputs.sha(fixture_case.database)
        result = observed.observe(fixture_case.database, before, None, exact.inventory(SOURCE), anchor(FINAL), {},
            previous=fixture_case.previous, operations=fixture_case.operations, releases=fixture_case.releases)
        self.assertEqual(result["exact_material"]["anchor"], anchor(FINAL))
        self.assertEqual(result["exact_material"]["logical_rows"], 49)
        self.assertEqual(result["released_generations"], [2, 3, 4, 5, 6])
        self.assertEqual(result["old_unknown"]["events"], fixture_case.previous["events"])
        self.assertEqual(inputs.sha(fixture_case.database), before)
        self.assertFalse(result["native_execution_verified"])

    def test_actual_wal_change_outside_hos2_journals_cannot_hide_behind_valid_release_rows(self):
        fixture_case = self.material_fixture()
        connection = fixture_case.connection
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("UPDATE _sqlx_migrations SET description='inert newer metadata only in WAL'")
        connection.commit()
        output = fixture_case.database.parent / "private-copy"
        output.mkdir()
        copied = output / "original.sqlite3"
        wal = copied.with_name(copied.name + "-wal")
        shutil.copyfile(fixture_case.database, copied)
        shutil.copyfile(fixture_case.database.with_name(fixture_case.database.name + "-wal"), wal)
        before = inputs.sha(copied), inputs.sha(wal)
        with self.assertRaisesRegex(ValueError, "independently retained exact cut"):
            observed.observe(copied, before[0], before[1], exact.inventory(SOURCE), anchor(FINAL), {},
                previous=fixture_case.previous, operations=fixture_case.operations, releases=fixture_case.releases)
        self.assertEqual((inputs.sha(copied), inputs.sha(wal)), before)


if __name__ == "__main__":
    unittest.main()
