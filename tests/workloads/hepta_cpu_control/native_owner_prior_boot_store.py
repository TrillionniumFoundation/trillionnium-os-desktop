"""Read original durable rows from a stopped physical SQLite/WAL extraction.

These checks observe the existing source-owned journals. They never create a
database, operation, lease, claim, terminal or writer. Acceptance still needs
the original source-bound guest, exact physical extraction and both boots.
"""
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
import struct
import time

import native_owner_evidence as evidence
import native_owner_inputs as inputs


require = evidence.require
MAX_ROWS = 4096
MAX_ROW_BYTES = 8 * 1024 * 1024
MAX_DATABASE_BYTES = 256 * 1024 * 1024
EVENT_COLUMNS = ("lease_id", "event_sequence", "event_id", "occurrence_key", "owner_agent_id", "generation",
                 "fencing_token", "event_kind", "payload_json", "payload_sha256", "previous_sha256", "event_sha256",
                 "recorded_at_unix_seconds")
OUTBOX_COLUMNS = ("lease_id", "outbox_sequence", "outbox_id", "event_id", "occurrence_key", "owner_agent_id", "generation",
                  "fencing_token", "topic", "payload_json", "payload_sha256", "previous_sha256", "outbox_sha256",
                  "dispatch_state", "recorded_at_unix_seconds")
OPERATION_COLUMNS = ("operation_id", "semantic_sha256", "subject_id", "destination_id", "payload_sha256", "scope_sha256",
                     "policy_generation", "expected_predecessor_sha256", "lease_id", "event_id", "outbox_id", "owner_agent_id",
                     "generation", "fencing_token", "authority_epoch", "owner_epoch", "prepared_at_unix_seconds")
LEASE_COLUMNS = ("lease_id", "lease_sequence", "owner_agent_id", "generation", "fencing_token", "state", "previous_sha256",
                 "lease_sha256", "recorded_at_unix_seconds", "authority_epoch", "owner_epoch", "lease_expires_at_unix_seconds")
CLAIM_COLUMNS = ("operation_id", "claim_sequence", "attempt", "owner_generation", "fencing_token", "claim_state",
                 "lease_expires_at_unix_ms", "next_eligible_at_unix_ms", "previous_sha256", "claim_sha256", "recorded_at_unix_ms")
TERMINALS = {"reconcile_committed", "reconcile_rejected", "rolled_back"}


def framed(domain, parts):
    """Original memory::framing::frame_part, including the framed domain."""
    result = hashlib.sha256()
    for part in (domain, *parts):
        require(type(part) is bytes, "original digest frame must contain exact bytes")
        result.update(struct.pack(">Q", len(part)))
        result.update(part)
    return result.hexdigest()


def utf8(value):
    require(type(value) is str and "\0" not in value, "original stored text is not bounded UTF-8")
    encoded = value.encode("utf-8")
    require(0 < len(encoded) <= 65_536, "original stored text is empty or exceeds its SQL bound")
    return encoded


def u64(value):
    return struct.pack(">Q", evidence.integer(value, "original stored u64", 1, (1 << 63) - 1))


def check_digest(value):
    return evidence.digest(value, "original stored SHA-256")


def payload(row):
    require(hashlib.sha256(utf8(row["payload_json"])).hexdigest() == check_digest(row["payload_sha256"]),
            "original SQLite payload bytes differ from their immutable digest")


def operation_semantic_digest(operation):
    """Original kernel.operations model::OperationIntentV1, not its durable-model sibling."""
    value = bytearray(b"hepta.kernel.operations.operation-intent.v1\0")
    for name in ("operation_id", "subject_id", "destination_id"):
        encoded = utf8(operation[name])
        require(len(encoded) <= 512, "original operation stable ID exceeds its stored bound")
        value.extend(struct.pack(">I", len(encoded)))
        value.extend(encoded)
    for name in ("payload_sha256", "scope_sha256"):
        raw = bytes.fromhex(check_digest(operation[name]))
        require(any(raw), "original operation digest cannot be zero")
        value.extend(raw)
    value.extend(u64(operation["policy_generation"]))
    predecessor = operation["expected_predecessor_sha256"]
    value.append(0 if predecessor is None else 1)
    if predecessor is not None:
        raw = bytes.fromhex(check_digest(predecessor))
        require(any(raw), "original operation predecessor cannot be zero")
        value.extend(raw)
    return hashlib.sha256(value).hexdigest()


def operation_observation(operation):
    """Exact getter-only observation DTO emitted by the original retained writer."""
    return {"operation_id": operation["operation_id"], "subject_id": operation["subject_id"],
            "destination_id": operation["destination_id"],
            "payload_digest": list(bytes.fromhex(check_digest(operation["payload_sha256"]))),
            "scope_digest": list(bytes.fromhex(check_digest(operation["scope_sha256"]))),
            "policy_generation": operation["policy_generation"],
            "expected_predecessor": (None if operation["expected_predecessor_sha256"] is None else
                                     list(bytes.fromhex(check_digest(operation["expected_predecessor_sha256"]))))}


def row_digest(row, kind):
    if kind == "event":
        parts = [utf8(row["lease_id"]), u64(row["event_sequence"]), utf8(row["event_id"]), utf8(row["occurrence_key"]),
                 utf8(row["owner_agent_id"]), u64(row["generation"]), utf8(row["fencing_token"]), utf8(row["event_kind"]),
                 utf8(check_digest(row["payload_sha256"])), utf8(check_digest(row["previous_sha256"]))]
        return framed(b"hepta-memory:local-event:v1", parts)
    if kind == "outbox":
        parts = [utf8(row["lease_id"]), u64(row["outbox_sequence"]), utf8(row["outbox_id"]), utf8(row["event_id"]),
                 utf8(row["occurrence_key"]), utf8(row["owner_agent_id"]), u64(row["generation"]),
                 utf8(row["fencing_token"]), utf8(row["topic"]), utf8(check_digest(row["payload_sha256"])),
                 utf8(check_digest(row["previous_sha256"]))]
        return framed(b"hepta-memory:local-outbox:v1", parts)
    require(kind == "lease", "unknown original journal kind")
    require(row["state"] in ("active", "released", "rolled_back"), "unknown original local lease state")
    binding = [row[key] for key in ("authority_epoch", "owner_epoch", "lease_expires_at_unix_seconds")]
    require(all(item is None for item in binding) or all(type(item) is int and item > 0 for item in binding),
            "partial original local lease authority binding")
    bound = binding[0] is not None
    parts = [utf8(row["lease_id"]), u64(row["lease_sequence"]), utf8(row["owner_agent_id"]), u64(row["generation"]),
             utf8(row["fencing_token"]), utf8(row["state"])]
    if bound:
        parts.extend(u64(item) for item in binding)
    parts.append(utf8(check_digest(row["previous_sha256"])))
    return framed(b"hepta-memory:local-lease:v2" if bound else b"hepta-memory:local-lease:v1", parts)


def chain(rows, kind, owner, lease_id):
    require(type(rows) is list and 0 < len(rows) <= MAX_ROWS, "bounded original journal required")
    sequence_name, digest_name = kind + "_sequence", kind + "_sha256"
    previous = hashlib.sha256(("hepta-memory:local-" + kind + ":genesis:v1").encode()).hexdigest()
    for index, row in enumerate(rows, 1):
        require(row["lease_id"] == lease_id and row["owner_agent_id"] == owner
                and type(row[sequence_name]) is int and row[sequence_name] == index
                and row["previous_sha256"] == previous,
                "original SQLite journal lost its contiguous owner/lease/previous binding")
        if kind != "lease":
            payload(row)
        require(check_digest(row[digest_name]) == row_digest(row, kind), "original SQLite journal row digest differs")
        previous = row[digest_name]


def claim_chain(rows, operation):
    require(type(rows) is list and 2 <= len(rows) <= MAX_ROWS, "original entered dispatch claim history required")
    previous = hashlib.sha256(b"hepta:kernel.operations:dispatch-claim:genesis:v1").hexdigest()
    states = []
    for index, row in enumerate(rows, 1):
        require(row["operation_id"] == operation["operation_id"] and type(row["claim_sequence"]) is int
                and row["claim_sequence"] == index and row["previous_sha256"] == previous
                and row["owner_generation"] == operation["generation"]
                and row["fencing_token"] == operation["fencing_token"]
                and type(row["attempt"]) is int and row["attempt"] == 1,
                "old operation was reclaimed, renumbered or detached from its original entered writer")
        parts = [utf8(row["operation_id"]), u64(row["claim_sequence"]), struct.pack(">I", row["attempt"]),
                 u64(row["owner_generation"]), utf8(row["fencing_token"]), utf8(row["claim_state"]),
                 u64(row["lease_expires_at_unix_ms"]), u64(row["next_eligible_at_unix_ms"]), utf8(previous)]
        require(check_digest(row["claim_sha256"]) == framed(b"hepta:kernel.operations:dispatch-claim:v1", parts),
                "original dispatch claim framing/digest changed")
        previous = row["claim_sha256"]
        states.append(row["claim_state"])
    require(states[0] == "claimed" and states[-1] == "entered" and states.count("entered") == 1
            and all(state == "renewed" for state in states[1:-1]),
            "old unknown operation no longer retains its one original effect-entry claim")


def verify_old_rows(operation, outbox_rows, event_rows, leases, claims, owner, key, request_json):
    """Verify actual extracted rows; never create a production outcome."""
    request = evidence.request(request_json)
    payload_sha = hashlib.sha256(request_json.encode()).hexdigest()
    lease_id = operation["lease_id"]
    scope = (b"hepta.hos2.cpu-budget.scope.v1\0" + bytes(request["delivery"]["boot_id"])
             + bytes(request["delivery"]["space_id"])
             + struct.pack("<QQ", request["manage_slot"], request["manage_generation"]))
    require(operation["operation_id"] == key and operation["subject_id"] == operation["owner_agent_id"] == owner
            and operation["destination_id"] == "hos2.cpu-budget.v1" and operation["payload_sha256"] == payload_sha
            and operation["scope_sha256"] == hashlib.sha256(scope).hexdigest()
            and operation["expected_predecessor_sha256"] is None
            and type(operation["policy_generation"]) is int
            and operation["policy_generation"] == operation["authority_epoch"],
            "original operation row changed the immutable K, payload, owner, authority or native scope")
    for name in ("generation", "owner_epoch", "authority_epoch"):
        evidence.integer(operation[name], "original operation " + name, 1, (1 << 63) - 1)
    require(check_digest(operation["semantic_sha256"]) == operation_semantic_digest(operation),
            "original operation semantic digest differs from its complete immutable intent")
    chain(leases, "lease", owner, lease_id)
    chain(event_rows, "event", owner, lease_id)
    chain(outbox_rows, "outbox", owner, lease_id)
    active_fences = {(row["generation"], row["fencing_token"]) for row in leases if row["state"] == "active"}
    require(all((row["generation"], row["fencing_token"]) in active_fences for row in event_rows + outbox_rows),
            "original event/outbox uses a fence absent from the actual lease history")
    old_events = [row for row in event_rows if row["occurrence_key"] == key]
    old_outbox = [row for row in outbox_rows if row["occurrence_key"] == key]
    require(len(old_outbox) == 1 and len(old_events) in (2, 3), "old original operation pair or state events are missing/duplicated")
    admitted, outbox = old_events[0], old_outbox[0]
    kinds = [row["event_kind"] for row in old_events]
    require(kinds in (["admitted", "indeterminate"], ["admitted", "indeterminate", "reconcile_still_indeterminate"]),
            "old K has a terminal, rollback, late admission or invalid/downgraded outcome history")
    require(admitted["event_id"] == outbox["event_id"] == operation["event_id"]
            and outbox["outbox_id"] == operation["outbox_id"]
            and admitted["payload_json"] == outbox["payload_json"] == request_json
            and admitted["payload_sha256"] == outbox["payload_sha256"] == payload_sha
            and admitted["generation"] == outbox["generation"] == operation["generation"]
            and admitted["fencing_token"] == outbox["fencing_token"] == operation["fencing_token"]
            and outbox["topic"] == "hepta.hos2.install-budget.v1" and outbox["dispatch_state"] == "queued",
            "original immutable admission, outbox and operation row no longer form one exact pair")
    require(old_events[1]["payload_json"].startswith("dispatch_started_pending_ack:")
            and len(old_events[1]["payload_json"]) == len("dispatch_started_pending_ack:") + 64,
            "old operation lacks the original pre-effect durable Indeterminate event")
    check_digest(old_events[1]["payload_json"].split(":", 1)[1])
    claim_chain(claims, operation)
    return {"operation": operation, "admission": admitted, "outbox": outbox, "events": old_events,
            "claims": claims, "observed_state": "indeterminate", "terminal_event_count": 0,
            "original_lease_chain_rows": len(leases), "original_event_chain_rows": len(event_rows),
            "original_outbox_chain_rows": len(outbox_rows), "native_execution_verified": False}


def verify_extracted_file(path, maximum, expected_sha256, allow_empty=False):
    path = Path(path)
    require(path.is_absolute() and path.resolve(strict=True) == path and not path.is_symlink(),
            "canonical private forensic extraction required")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                and (0 if allow_empty else 1) <= before.st_size <= maximum,
                "bounded unique original database/WAL extraction required")
        digest = hashlib.sha256()
        remaining = before.st_size
        while remaining:
            part = os.read(descriptor, min(remaining, 1024 * 1024))
            require(part, "forensic extraction was truncated while hashing")
            remaining -= len(part)
            digest.update(part)
        require(not os.read(descriptor, 1) and digest.hexdigest() == check_digest(expected_sha256),
                "original database/WAL extraction differs from actual retained bytes")
        after, named = os.fstat(descriptor), path.lstat()
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                and (named.st_dev, named.st_ino, named.st_size) == (before.st_dev, before.st_ino, before.st_size),
                "original database/WAL extraction changed while hashing")
    finally:
        os.close(descriptor)


def observe_extracted_database(database, expected_database_sha256, expected_wal_sha256, owner, key, request_json):
    """Read a private stopped-disk extraction, including its actual WAL.

mode=ro preserves DB/existing-WAL bytes. SQLite may use a scratch SHM and,
when no physical WAL existed, a new zero-byte WAL in this forensic directory.
Such empty scratch files are recorded separately, never as retained guest data.
This directory is never the guest state disk or a boot input.
immutable=1 is deliberately not used, since it can ignore a retained WAL.
    """
    database = Path(database)
    verify_extracted_file(database, MAX_DATABASE_BYTES, expected_database_sha256)
    wal = database.with_name(database.name + "-wal")
    if expected_wal_sha256 is None:
        require(not wal.exists() and not wal.is_symlink(), "unexpected original WAL was omitted from its manifest")
    else:
        verify_extracted_file(wal, MAX_DATABASE_BYTES, expected_wal_sha256, allow_empty=True)
    journal = database.with_name(database.name + "-journal")
    require(not journal.exists() and not journal.is_symlink(), "a retained rollback journal cannot be silently ignored")
    started = time.monotonic()
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=1)
    connection.row_factory = sqlite3.Row
    queries = []
    scratch_wal_created = False
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.enable_load_extension(False)
        connection.set_progress_handler(lambda: 1 if time.monotonic() - started > 15 else 0, 1000)

        def read(table, columns, where, parameters, order):
            require(table in ("cognitive_operation_ledger", "cognitive_local_outbox", "cognitive_local_events",
                              "cognitive_local_leases", "cognitive_operation_dispatch_claims"), "unknown forensic table")
            schema = connection.execute("SELECT type, sql FROM sqlite_schema WHERE name=?", (table,)).fetchall()
            require(len(schema) == 1 and schema[0]["type"] == "table" and type(schema[0]["sql"]) is str
                    and schema[0]["sql"].lstrip().startswith("CREATE TABLE " + table + " ("),
                    "original durable table was replaced with a view or another schema object")
            query = "SELECT " + ", ".join(columns) + " FROM " + table + " WHERE " + where + " ORDER BY " + order + " LIMIT ?"
            rows = [dict(row) for row in connection.execute(query, (*parameters, MAX_ROWS + 1)).fetchall()]
            require(len(rows) <= MAX_ROWS and len(evidence.canonical(rows).encode()) <= MAX_ROW_BYTES,
                    "finite same-disk campaign journal exceeds its inspection bound")
            queries.append({"sql": query, "parameters": [*parameters, MAX_ROWS + 1], "row_count": len(rows)})
            return rows

        operation = read("cognitive_operation_ledger", OPERATION_COLUMNS, "operation_id=?", (key,), "operation_id")
        require(len(operation) == 1, "original old operation was removed or duplicated")
        lease = operation[0]["lease_id"]
        events = read("cognitive_local_events", EVENT_COLUMNS, "lease_id=?", (lease,), "event_sequence")
        all_old_events = read("cognitive_local_events", EVENT_COLUMNS, "occurrence_key=?", (key,), "lease_id,event_sequence")
        require(all_old_events == [row for row in events if row["occurrence_key"] == key],
                "old K has hidden source events under another local lease")
        outbox = read("cognitive_local_outbox", OUTBOX_COLUMNS, "lease_id=?", (lease,), "outbox_sequence")
        all_old_outbox = read("cognitive_local_outbox", OUTBOX_COLUMNS, "occurrence_key=?", (key,), "lease_id,outbox_sequence")
        require(all_old_outbox == [row for row in outbox if row["occurrence_key"] == key],
                "old K has hidden outbox rows under another local lease")
        leases = read("cognitive_local_leases", LEASE_COLUMNS, "lease_id=?", (lease,), "lease_sequence")
        claims = read("cognitive_operation_dispatch_claims", CLAIM_COLUMNS, "operation_id=?", (key,), "claim_sequence")
        result = verify_old_rows(operation[0], outbox, events, leases, claims, owner, key, request_json)
        result.update(database_sha256=expected_database_sha256, wal_sha256=expected_wal_sha256,
                      sqlite_version=sqlite3.sqlite_version,
                      sqlite_source_id=connection.execute("SELECT sqlite_source_id()").fetchone()[0],
                      connection_mode="ro; actual WAL retained; no immutable=1", queries=queries,
                      elapsed_seconds=time.monotonic() - started)
    finally:
        connection.close()
        verify_extracted_file(database, MAX_DATABASE_BYTES, expected_database_sha256)
        if expected_wal_sha256 is not None:
            verify_extracted_file(wal, MAX_DATABASE_BYTES, expected_wal_sha256, allow_empty=True)
        else:
            if wal.exists() or wal.is_symlink():
                verify_extracted_file(wal, 0, hashlib.sha256(b"").hexdigest(), allow_empty=True)
                scratch_wal_created = True
    result["reader_created_empty_scratch_wal"] = scratch_wal_created
    return result


def preserved_unknown(first, second):
    """Boot-mismatch Unavailable is read-only in the original reconciler.

    Unlike a target's explicit Indeterminate response, this refusal does not
    append reconcile_still_indeterminate. Keep the complete old chain exact.
    """
    require(first["observed_state"] == second["observed_state"] == "indeterminate"
            and first["terminal_event_count"] == second["terminal_event_count"] == 0,
            "old operation did not remain an unresolved original source outcome")
    for name in ("operation", "admission", "outbox", "claims"):
        require(first[name] == second[name], "old immutable " + name + " changed across actual boots")
    prior, current = first["events"], second["events"]
    require(current == prior,
            "original boot-mismatch observer appended, replaced, truncated or resolved the old event chain")
    return {"original_immutable_rows_preserved": True, "old_terminal_absent": True,
            "new_unknown_observations": len(current) - len(prior), "native_execution_verified": False}
