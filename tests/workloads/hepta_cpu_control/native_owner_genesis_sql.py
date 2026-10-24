"""Read original empty/committed journals inside an exact-material snapshot.

The first VM must have no original writer or operation rows. The second must
retain its one actual admitted K/D, immutable terminal and original release.
Nothing here inserts, replays, repairs, settles or issues a source operation.
"""
import hashlib
import sqlite3
import struct

import native_owner_evidence as e
import native_owner_prior_boot_store as old
import native_owner_prior_boot_types as fixed


TABLES = {
    "cognitive_local_leases": (old.LEASE_COLUMNS, "lease_id,lease_sequence"),
    "cognitive_local_events": (old.EVENT_COLUMNS, "lease_id,event_sequence"),
    "cognitive_local_outbox": (old.OUTBOX_COLUMNS, "lease_id,outbox_sequence"),
    "cognitive_operation_ledger": (old.OPERATION_COLUMNS, "operation_id"),
    "cognitive_operation_dispatch_claims": (old.CLAIM_COLUMNS, "operation_id,claim_sequence"),
}


def empty(counts):
    e.require(all(counts.get(name) == 0 and type(counts.get(name)) is int for name in TABLES),
              "before-writer material already contains an original lease, admission, operation, event or dispatch claim")
    return {"original_writer_tables": {name: 0 for name in TABLES}, "original_writer_present": False,
            "original_operation_present": False, "native_execution_verified": False}


def verify_rows(rows, operation, release):
    e.obj(rows, TABLES, "actual complete original finite writer tables")
    leases, events, outbox, operations, claims = [rows[name] for name in TABLES]
    e.require(len(operations) == len(outbox) == 1 and len(events) == 3 and 2 <= len(leases) <= old.MAX_ROWS
              and 2 <= len(claims) <= old.MAX_ROWS,
              "new original effect has missing/extra immutable operation, outbox or source events")
    candidate = operations[0]
    entered_claims = claims[:-1] if claims[-1]["claim_state"] == "settled" else claims
    # This validates the real immutable admission/effect-entry prefix using
    # the existing original framing checker; it does not replace any row.
    checked = old.verify_old_rows(candidate, outbox, events[:-1], leases, entered_claims,
                                  fixed.AGENT, operation["key"], operation["request_json"])
    old.chain(events, "event", fixed.AGENT, candidate["lease_id"])
    terminal = events[-1]
    e.require(terminal["event_kind"] == "reconcile_committed"
              and terminal["event_id"] == operation["source_event"]
              and terminal["occurrence_key"] == operation["key"]
              and terminal["payload_json"] == operation["terminal"]
              and terminal["generation"] == candidate["generation"]
              and terminal["fencing_token"] == candidate["fencing_token"],
              "physical original committed terminal is missing, replaced or detached from the observed native K/D")
    e.require(e.terminal(terminal["payload_json"], operation["request"]) == operation["observation"],
              "physical original terminal differs from the actual native observation")
    if len(entered_claims) != len(claims):
        prior, settled = claims[-2:]
        e.require(all(settled[name] == prior[name] for name in
                      ("operation_id", "attempt", "owner_generation", "fencing_token",
                       "lease_expires_at_unix_ms", "next_eligible_at_unix_ms"))
                  and settled["claim_sequence"] == prior["claim_sequence"] + 1
                  and settled["previous_sha256"] == prior["claim_sha256"],
                  "secondary original settled claim changed its already entered immutable operation")
        parts = [old.utf8(settled["operation_id"]), old.u64(settled["claim_sequence"]),
                 struct.pack(">I", settled["attempt"]), old.u64(settled["owner_generation"]),
                 old.utf8(settled["fencing_token"]), b"settled", old.u64(settled["lease_expires_at_unix_ms"]),
                 old.u64(settled["next_eligible_at_unix_ms"]), old.utf8(settled["previous_sha256"])]
        e.require(settled["claim_sha256"] == old.framed(b"hepta:kernel.operations:dispatch-claim:v1", parts),
                  "secondary original claim settlement digest differs")
    # mark_settled is explicitly secondary in the original writer. Its I/O
    # failure cannot turn a durable destination terminal into retryable work.
    e.require([item["state"] for item in leases] == ["active"] * (len(leases) - 1) + ["released"]
              and leases[-1]["lease_sha256"] == release["lease_head_digest"]
              and all(item["generation"] == release["generation"] == 1
                      and item["authority_epoch"] == release["authority_epoch"]
                      and item["owner_epoch"] == release["owner_epoch"]
                      and item["fencing_token"] == candidate["fencing_token"] for item in leases),
              "physical original lease is not the same fully released first writer")
    return {"operation": candidate, "admission": checked["admission"], "outbox": outbox[0], "events": events,
            "claims": claims, "leases": leases, "observed_state": "committed", "terminal_event_count": 1,
            "actual_release_head_digest": leases[-1]["lease_sha256"],
            "secondary_settled_claim_present": len(entered_claims) != len(claims), "native_execution_verified": False}


def committed(connection, counts, operation, release, queries):
    rows = {}
    previous = connection.row_factory
    connection.row_factory = sqlite3.Row
    try:
        for name, (columns, ordering) in TABLES.items():
            count = counts.get(name)
            e.require(type(count) is int and 0 <= count <= old.MAX_ROWS, "original finite table exceeds forensic bound")
            query = "SELECT " + ",".join(columns) + " FROM " + name + " ORDER BY " + ordering + " LIMIT ?"
            actual = [dict(row) for row in connection.execute(query, (old.MAX_ROWS + 1,))]
            e.require(len(actual) == count and len(e.canonical(actual).encode()) <= old.MAX_ROW_BYTES,
                      "complete original finite table was truncated or changed inside the read transaction")
            queries.append({"sql": query, "parameters": [old.MAX_ROWS + 1], "row_count": count})
            rows[name] = actual
    finally:
        connection.row_factory = previous
    return verify_rows(rows, operation, release)
