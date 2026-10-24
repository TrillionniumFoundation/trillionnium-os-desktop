"""Inspect a stopped original database/WAL without altering the campaign disk.

The actual source-defined logical anchor and complete original journals are
read within one SQLite transaction. An intermediate material is accepted only
as its exact observed prefix; only the final material can close the new gate.
"""
import hashlib
from pathlib import Path
import sqlite3
import time

import native_owner_evidence as e
import native_owner_genesis_store as exact
import native_owner_prior_boot_store as original
import native_owner_prior_renewal_sql as journals


def observe(database, database_sha256, wal_sha256, schema, anchor, cut,
            *, previous=None, operations=None, releases=None, partial=False):
    e.require((previous is None and operations is None and releases is None and not partial)
              or (type(previous) is dict and type(operations) is list and type(releases) is list),
              "one exact fresh cut or observed released prefix is required")
    database = Path(database)
    original.verify_extracted_file(database, original.MAX_DATABASE_BYTES, database_sha256)
    wal = database.with_name(database.name + "-wal")
    journal = database.with_name(database.name + "-journal")
    e.require(not journal.exists() and not journal.is_symlink(), "a retained rollback journal cannot be ignored")
    if wal_sha256 is None:
        e.require(not wal.exists() and not wal.is_symlink(), "an unmanifested physical WAL cannot be ignored")
    else:
        original.verify_extracted_file(wal, original.MAX_DATABASE_BYTES, wal_sha256, allow_empty=True)
    started, queries, scratch_wal = time.monotonic(), [], False
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=1)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.enable_load_extension(False)
        connection.set_progress_handler(lambda: 1 if time.monotonic() - started > 30 else 0, 1000)
        connection.execute("BEGIN")
        material = exact.capture(connection, schema, anchor, queries)
        observed = (journals.observe_fresh(connection, cut, queries) if previous is None else
                    journals.observe(connection, previous, operations, releases, queries, partial=partial))
        connection.rollback()
        sqlite_id = connection.execute("SELECT sqlite_source_id()").fetchone()[0]
    finally:
        connection.close()
        original.verify_extracted_file(database, original.MAX_DATABASE_BYTES, database_sha256)
        if wal_sha256 is not None:
            original.verify_extracted_file(wal, original.MAX_DATABASE_BYTES, wal_sha256, allow_empty=True)
        elif wal.exists() or wal.is_symlink():
            original.verify_extracted_file(wal, 0, hashlib.sha256(b"").hexdigest(), allow_empty=True)
            scratch_wal = True
    result = {**observed, "schema": "hepta.original-prior-unknown-renewal-material.v1", "passed": False,
              "exact_material": material, "complete_original_journals_verified": True,
              "intermediate_release_prefix": partial, "database_sha256": database_sha256, "wal_sha256": wal_sha256,
              "original_schema_source_sha256": schema["original_source_sha256"],
              "sqlite_version": sqlite3.sqlite_version, "sqlite_source_id": sqlite_id,
              "connection_mode": "ro; actual WAL retained; no immutable=1", "queries": queries,
              "reader_created_empty_scratch_wal": scratch_wal,
              "elapsed_seconds": time.monotonic() - started, "native_execution_verified": False,
              "checkpoint_or_current_created": False}
    return result
