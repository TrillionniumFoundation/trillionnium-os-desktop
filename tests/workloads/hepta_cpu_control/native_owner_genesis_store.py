"""Read an exact original physical anchor from a stopped SQLite/WAL copy.

This reproduces cognitive_store_recovery::capture's observation encoding.
The inventory is parsed from the reviewed original CognitiveStore source;
these observations never install a database, invent a Current or issue an
authority. SQLite opens only a private extraction, never the campaign disk.
"""
import hashlib
from pathlib import Path
import re
import sqlite3
import struct
import time

import native_owner_evidence as e
import native_owner_genesis_record as genesis
import native_owner_prior_boot_store as original


MAX_ROWS = 262144
MAX_BYTES = 128 * 1024 * 1024
MAX_ROW_BYTES = 2 * 1024 * 1024
MAX_SCHEMA_BYTES = 1024 * 1024
PROFILE = "hepta:cognitive:exact-current-cut:v1"


def inventory(raw):
    """Parse only the actual fixed Rust inventory, never Python/Rust code."""
    e.require(type(raw) is bytes and 0 < len(raw) <= MAX_SCHEMA_BYTES,
              "bounded reviewed original CognitiveStore source required")
    text = raw.decode("utf-8")
    arrays = re.findall(r"const REQUIRED_SCHEMA_OBJECTS: &\[\(&str, &str\)\] = &\[(.*?)\n\];", text, re.S)
    digests = re.findall(r'const REQUIRED_SCHEMA_ORACLE_SHA256: &str =\s*"([0-9a-f]{64})";', text)
    e.require(len(arrays) == len(digests) == 1, "original required schema declarations are missing or ambiguous")
    expression = re.compile(r'\(\s*"([A-Za-z0-9_]+)"\s*,\s*"(table|index|trigger)"\s*,?\s*\)\s*,?')
    entries = expression.findall(arrays[0])
    e.require(entries and not expression.sub("", arrays[0]).strip()
              and len(entries) == len({name for name, _ in entries}),
              "original required schema declaration contains unsupported or repeated expressions")
    return {"objects": sorted(entries), "schema_digest": digests[0],
            "original_source_sha256": hashlib.sha256(raw).hexdigest()}


def frame(digest, value):
    e.require(type(value) is bytes, "original anchor frame requires exact bytes")
    digest.update(struct.pack(">Q", len(value)))
    digest.update(value)


def quoted(value):
    e.require(type(value) is str and 0 < len(value.encode()) <= MAX_SCHEMA_BYTES and "\0" not in value,
              "original SQLite identifier is unbounded or invalid")
    return '"' + value.replace('"', '""') + '"'


def capture(connection, schema, expected, queries):
    """A read-only transaction over complete source-defined logical tables."""
    expected = genesis.anchor(expected)
    e.obj(schema, ("objects", "schema_digest", "original_source_sha256"), "reviewed original schema inventory")
    e.digest(schema["original_source_sha256"], "reviewed original CognitiveStore source")
    e.require(expected["schema_digest"] == e.digest(schema["schema_digest"], "source schema digest"),
              "actual original material uses another compiled schema inventory")
    objects = schema["objects"]
    e.require(type(objects) is list and objects == sorted(objects) and objects
              and len(objects) == len({name for name, _ in objects})
              and all(type(name) is str and re.fullmatch(r"[A-Za-z0-9_]+", name)
                      and kind in ("table", "index", "trigger") for name, kind in objects),
              "reviewed original schema inventory changed ordering or contains unsupported objects")

    def execute(sql, parameters=()):
        queries.append({"sql": sql, "parameters": list(parameters)})
        return connection.execute(sql, parameters)

    schema_hash = hashlib.sha256()
    frame(schema_hash, b"hepta:cognitive:required-schema-oracle:v1")
    frame(schema_hash, struct.pack(">Q", len(objects)))
    schema_bytes = 0
    for name, kind in objects:
        row = execute("SELECT length(CAST(sql AS BLOB)) FROM sqlite_schema WHERE name=? AND type=?", (name, kind)).fetchall()
        e.require(len(row) == 1 and type(row[0][0]) is int and row[0][0] > 0,
                  "original required schema object is missing or replaced")
        schema_bytes += row[0][0]
        e.require(schema_bytes <= MAX_SCHEMA_BYTES, "original required schema exceeds its unchanged bound")
        sql = execute("SELECT sql FROM sqlite_schema WHERE name=?", (name,)).fetchone()[0]
        e.require(type(sql) is str and len(sql.encode()) == row[0][0], "original schema bytes are incomplete")
        for value in (name.encode(), kind.encode(), sql.encode()):
            frame(schema_hash, value)
    e.require(schema_hash.hexdigest() == expected["schema_digest"],
              "physical SQLite definitions differ from the original compiled schema digest")
    owner = execute("SELECT owner_agent_id FROM cognitive_meta WHERE singleton=1 AND length(owner_agent_id)=36").fetchall()
    e.require(owner == [(expected["owner_agent_id"],)], "physical material has another or ambiguous original Agent")
    tables = sorted([name for name, kind in objects if kind == "table"] + ["_sqlx_migrations"])
    actual = execute("SELECT substr(name,1,129) FROM pragma_table_list WHERE schema='main' "
                     "AND type IN ('table','virtual') AND name NOT LIKE 'sqlite_%' ORDER BY name LIMIT 256").fetchall()
    e.require(actual == [(name,) for name in tables], "physical material contains missing or unregistered logical tables")
    tables.append("sqlite_schema")
    state_hash = hashlib.sha256()
    for value in (PROFILE, expected["owner_agent_id"], expected["schema_digest"]):
        frame(state_hash, value.encode())
    remaining_rows, remaining_bytes = MAX_ROWS, MAX_BYTES
    counts = {}
    for table in tables:
        if table == "sqlite_schema":
            columns = ["type", "name", "tbl_name", "sql"]
        else:
            length = execute("SELECT length(CAST(sql AS BLOB)) FROM sqlite_schema WHERE name=?", (table,)).fetchone()
            e.require(length is not None and type(length[0]) is int and 1 <= length[0] <= MAX_SCHEMA_BYTES,
                      "original table metadata is missing or exceeds its unchanged bound")
            columns = [row[0] for row in execute("SELECT name FROM pragma_table_info(?) ORDER BY cid", (table,))]
            e.require(1 <= len(columns) <= 64, "original logical table has an invalid column count")
        fields = [quoted(name) for name in columns]
        row_size = " + ".join("CASE typeof(" + name + ") WHEN 'null' THEN 16 WHEN 'integer' THEN 32 "
                              "WHEN 'real' THEN 32 ELSE 24+length(CAST(" + name + " AS BLOB)) END" for name in fields)
        count, size, largest = execute("SELECT COUNT(*),COALESCE(SUM(row_size),0),COALESCE(MAX(row_size),0) "
            "FROM (SELECT " + row_size + " AS row_size FROM " + quoted(table) + " LIMIT ?)", (remaining_rows + 1,)).fetchone()
        e.require(type(count) is type(size) is type(largest) is int
                  and 0 <= count <= remaining_rows and 0 <= size <= remaining_bytes
                  and 0 <= largest <= MAX_ROW_BYTES, "original logical material exceeds its unchanged row/byte bounds")
        remaining_rows -= count
        remaining_bytes -= size
        frame(state_hash, table.encode())
        frame(state_hash, struct.pack(">Q", len(columns)))
        for column in columns:
            frame(state_hash, column.encode())
        frame(state_hash, struct.pack(">q", count))
        ordering = ", ".join("typeof(" + name + "), " + name + " COLLATE BINARY" for name in fields)
        selection = ", ".join("typeof(" + name + "), " + name for name in fields)
        row_count = 0
        for row in execute("SELECT " + selection + " FROM " + quoted(table) + " ORDER BY " + ordering):
            row_count += 1
            e.require(row_count <= count and len(row) == 2 * len(columns), "original locked logical rows changed")
            for index in range(0, len(row), 2):
                kind, value = row[index:index + 2]
                if kind == "null":
                    e.require(value is None, "SQLite null observation is inconsistent")
                    frame(state_hash, b"null")
                    continue
                if kind == "integer":
                    e.require(type(value) is int and -(1 << 63) <= value < 1 << 63, "SQLite integer is not original i64")
                    data = struct.pack(">q", value)
                elif kind == "real":
                    e.require(type(value) is float, "SQLite real is not original f64")
                    data = struct.pack(">d", value)
                elif kind == "text":
                    e.require(type(value) is str, "SQLite text is not original UTF-8")
                    data = value.encode()
                else:
                    e.require(kind == "blob" and type(value) is bytes, "unsupported original SQLite value type")
                    data = value
                frame(state_hash, kind.encode())
                frame(state_hash, data)
        e.require(row_count == count, "original read-only transaction lost logical rows")
        counts[table] = count
    e.require(execute("PRAGMA quick_check(1)").fetchall() == [("ok",)], "physical original SQLite quick_check failed")
    e.require(execute("SELECT 1 FROM pragma_foreign_key_check LIMIT 1").fetchone() is None,
              "physical original SQLite foreign-key check failed")
    actual_anchor = {"profile": PROFILE, "owner_agent_id": expected["owner_agent_id"],
                     "schema_digest": schema_hash.hexdigest(), "state_digest": state_hash.hexdigest()}
    e.require(actual_anchor == expected, "complete original logical material differs from its independently retained exact cut")
    return {"anchor": actual_anchor, "table_rows": counts, "logical_rows": MAX_ROWS - remaining_rows,
            "logical_bound_bytes": MAX_BYTES - remaining_bytes, "schema_bytes": schema_bytes}


def observe(database, database_sha256, wal_sha256, schema, expected, *, unused=False, operation=None, release=None):
    e.require(type(unused) is bool and ((operation is None and release is None)
              or (not unused and type(operation) is dict and type(release) is dict)),
              "one complete original empty/committed journal observation required")
    database = Path(database)
    original.verify_extracted_file(database, original.MAX_DATABASE_BYTES, database_sha256)
    wal = database.with_name(database.name + "-wal")
    journal = database.with_name(database.name + "-journal")
    e.require(not journal.exists() and not journal.is_symlink(), "a retained rollback journal cannot be ignored")
    if wal_sha256 is None:
        e.require(not wal.exists() and not wal.is_symlink(), "unmanifested physical WAL cannot be ignored")
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
        result = capture(connection, schema, expected, queries)
        if unused or operation is not None:
            import native_owner_genesis_sql as journals
            result["original_journals"] = (journals.empty(result["table_rows"]) if unused else
                journals.committed(connection, result["table_rows"], operation, release, queries))
        connection.rollback()
        result.update(sqlite_version=sqlite3.sqlite_version,
                      sqlite_source_id=connection.execute("SELECT sqlite_source_id()").fetchone()[0])
    finally:
        connection.close()
        original.verify_extracted_file(database, original.MAX_DATABASE_BYTES, database_sha256)
        if wal_sha256 is not None:
            original.verify_extracted_file(wal, original.MAX_DATABASE_BYTES, wal_sha256, allow_empty=True)
        elif wal.exists() or wal.is_symlink():
            original.verify_extracted_file(wal, 0, hashlib.sha256(b"").hexdigest(), allow_empty=True)
            scratch_wal = True
    result.update(schema="hepta.original-exact-material-observation.v1", passed=True,
                  database_sha256=database_sha256, wal_sha256=wal_sha256,
                  original_schema_source_sha256=schema["original_source_sha256"],
                  connection_mode="ro; actual WAL retained; no immutable=1", queries=queries,
                  reader_created_empty_scratch_wal=scratch_wal, elapsed_seconds=time.monotonic() - started,
                  native_execution_verified=False, checkpoint_or_current_created=False)
    return result
