"""Read complete original journals after Unknown-preserving owner handoffs.

This module never writes a production row or creates an authority. Its inputs
are the original stopped DB/WAL transaction and observations independently
checked from actual owner events. Host fixtures cannot qualify a native run.
"""
import sqlite3
import struct

import native_owner_continuity_types as types
import native_owner_evidence as e
import native_owner_genesis_sql as inventory
import native_owner_prior_boot_store as old
import native_owner_prior_boot_types as fixed


def settled_claim(rows, operation):
    """The original secondary settlement may follow its one entered claim."""
    entered = rows[:-1] if rows and rows[-1]["claim_state"] == "settled" else rows
    old.claim_chain(entered, operation)
    if len(entered) == len(rows):
        return False
    prior, settled = rows[-2:]
    e.require(all(settled[key] == prior[key] for key in
                  ("operation_id", "attempt", "owner_generation", "fencing_token",
                   "lease_expires_at_unix_ms", "next_eligible_at_unix_ms"))
              and type(settled["claim_sequence"]) is int
              and settled["claim_sequence"] == prior["claim_sequence"] + 1
              and settled["previous_sha256"] == prior["claim_sha256"],
              "secondary settlement rebound an already entered original operation")
    parts = [old.utf8(settled["operation_id"]), old.u64(settled["claim_sequence"]),
             struct.pack(">I", settled["attempt"]), old.u64(settled["owner_generation"]),
             old.utf8(settled["fencing_token"]), b"settled", old.u64(settled["lease_expires_at_unix_ms"]),
             old.u64(settled["next_eligible_at_unix_ms"]), old.utf8(settled["previous_sha256"])]
    e.require(settled["claim_sha256"] == old.framed(b"hepta:kernel.operations:dispatch-claim:v1", parts),
              "original secondary settlement digest differs")
    return True


def release_binding(value):
    """An internal projection of a verified owner_released event, not a lease."""
    e.obj(value, ("receipt", "binding"), "observed original release and Current binding")
    receipt = e.obj(value["receipt"], types.RELEASE_KEYS, "actual original release receipt")
    binding = e.obj(value["binding"], e.WRITER_KEYS, "actual released Current writer binding")
    e.require(type(receipt["schema_version"]) is int and receipt["schema_version"] == 1
              and receipt["namespace"] == "production_durable_writer"
              and receipt["owner_agent_id"] == fixed.AGENT and receipt["state"] == "released"
              and receipt["external_effect"] is False,
              "an actual original successful release is required for every new owner")
    for key in ("lease_id", "generation", "authority_grant_digest", "authority_epoch", "owner_epoch"):
        e.require(type(receipt[key]) is type(binding[key]) and receipt[key] == binding[key],
                  "original release differs from its actual acknowledged Current")
    for key in ("generation", "authority_epoch", "owner_epoch", "expires_at_unix_seconds"):
        e.integer(binding[key], "original released writer " + key, 1)
    for key in ("authority_grant_digest", "fencing_token_digest"):
        e.digest(binding[key], "original released writer " + key)
    e.digest(receipt["lease_head_digest"], "actual released lease head")
    return binding, receipt


def verify_rows(rows, previous, operations, releases, *, partial=False):
    """Check all five source tables; no hidden K, effect, fence or generation."""
    e.obj(rows, inventory.TABLES, "complete original Unknown-renewal journals")
    e.require(type(partial) is bool and type(operations) is list
              and (1 if partial else 3) <= len(operations) <= 64 and type(releases) is list
              and len(releases) in ((2 * len(operations) - 1, 2 * len(operations)) if partial
                                   else (2 * len(operations) - 1,)),
              "bounded actual Manager effects and every Manager/Recovery release are required")
    e.require(type(previous) is dict and previous.get("observed_state") == "indeterminate"
              and previous.get("terminal_event_count") == 0 and type(previous.get("lease_rows")) is list,
              "the first stopped physical Unknown is required")
    leases, events, outbox, ledger, claims = [rows[name] for name in inventory.TABLES]
    prior_operation = previous["operation"]
    old_key, lease_id = prior_operation["operation_id"], prior_operation["lease_id"]
    keys = [value["key"] for value in operations]
    e.require(len(set(keys)) == len(keys) and old_key not in keys
              and len(ledger) == len(outbox) == len(keys) + 1
              and len(events) == len(previous["events"]) + 3 * len(keys)
              and all(row["operation_id"] in {old_key, *keys} for row in claims),
              "original journals contain a missing, duplicated or unobserved operation/terminal")
    by_key = {row["operation_id"]: row for row in ledger}
    e.require(len(by_key) == len(ledger) and set(by_key) == {old_key, *keys},
              "original ledger omitted or duplicated an observed immutable K")
    retained = old.verify_old_rows(by_key[old_key], outbox, events, leases,
        [row for row in claims if row["operation_id"] == old_key], fixed.AGENT,
        old_key, previous["admission"]["payload_json"])
    old.preserved_unknown(previous, retained)

    # The original admission/lease hash check above covers the complete chains,
    # including newer terminals. Each new effect is then bound to its own
    # exact prefix, immutable native terminal and actually released fence.
    bindings = [release_binding(value) for value in releases]
    first_generation = prior_operation["generation"] + 1
    e.require([binding["generation"] for binding, _ in bindings]
              == list(range(first_generation, first_generation + len(bindings))),
              "actual released original generations were skipped, repeated or reset")
    e.require(all(binding["lease_id"] == lease_id
                  and binding["authority_epoch"] == prior_operation["authority_epoch"]
                  and binding["owner_epoch"] == prior_operation["owner_epoch"] + index + 1
                  for index, (binding, _) in enumerate(bindings)),
              "original release lineage changed its local lease, authority or owner epoch")
    groups = {}
    for row in leases:
        groups.setdefault(row["generation"], []).append(row)
    original_head = initial_lease(previous["lease_rows"], previous)
    expected_generations = [prior_operation["generation"], *(binding["generation"] for binding, _ in bindings)]
    e.require(len(leases) == 2 * len(expected_generations)
              and [row["generation"] for row in leases] == [generation for generation in expected_generations for _ in range(2)],
              "original lease journal skipped its exact terminal-to-next-generation CAS")
    expired = leases[1]
    e.require(leases[0] == original_head and expired["state"] == "rolled_back"
              and all(expired[key] == original_head[key] for key in
                      ("lease_id", "owner_agent_id", "generation", "fencing_token", "authority_epoch",
                       "owner_epoch", "lease_expires_at_unix_seconds")),
              "cold recovery did not expire the exact old lease before its next generation")
    # A lease expiry is not an operation rollback: old K's complete source
    # events were compared byte-for-byte above and must remain Indeterminate.
    active_tokens = [row["fencing_token"] for row in leases if row["state"] == "active"]
    e.require(len(active_tokens) == len(set(active_tokens)) == len(expected_generations),
              "the original lease journal reused a prior active fencing token")
    for binding, receipt in bindings:
        group = groups[binding["generation"]]
        e.require(len(group) == 2 and [row["state"] for row in group] == ["active", "released"]
                  and group[-1]["lease_sha256"] == receipt["lease_head_digest"]
                  and all(row["fencing_token"] == binding["fencing_token_digest"]
                          and row["authority_epoch"] == binding["authority_epoch"]
                          and row["owner_epoch"] == binding["owner_epoch"]
                          and row["lease_expires_at_unix_seconds"] == binding["expires_at_unix_seconds"]
                          for row in group),
                  "a new original owner did not persist its exact active-to-released lease head")

    committed = []
    for index, value in enumerate(operations):
        key, operation = value["key"], by_key[value["key"]]
        binding, _ = bindings[index * 2]
        selected = [row for row in events if row["occurrence_key"] == key]
        selected_claims = [row for row in claims if row["operation_id"] == key]
        e.require(len(selected) == 3
                  and [row["event_kind"] for row in selected] == ["admitted", "indeterminate", "reconcile_committed"],
                  "a new original effect lacks its one immutable committed source terminal")
        terminal = selected[-1]
        prefix = events[:terminal["event_sequence"] - 1]
        entry_claims = selected_claims[:-1] if selected_claims and selected_claims[-1]["claim_state"] == "settled" else selected_claims
        old.verify_old_rows(operation, outbox, prefix, leases, entry_claims,
                            fixed.AGENT, key, value["request_json"])
        e.require(operation["generation"] == binding["generation"]
                  and operation["owner_epoch"] == binding["owner_epoch"]
                  and operation["authority_epoch"] == binding["authority_epoch"]
                  and operation["fencing_token"] == binding["fencing_token_digest"]
                  and terminal["generation"] == operation["generation"]
                  and terminal["fencing_token"] == operation["fencing_token"]
                  and terminal["event_id"] == value["source_event"]
                  and terminal["payload_json"] == value["terminal"]
                  and e.terminal(terminal["payload_json"], value["request"]) == value["observation"],
                  "new source terminal changed its actual native K/D, local event, owner generation or fence")
        secondary = settled_claim(selected_claims, operation)
        committed.append({"operation": operation, "events": selected, "claims": selected_claims,
                          "secondary_settled_claim_present": secondary})
    e.require(leases[-1]["lease_sha256"] == bindings[-1][1]["lease_head_digest"],
              "a later original lease appeared after the final actual release")
    return {"old_unknown": retained, "original_immutable_rows_preserved": True,
            "old_terminal_absent": True, "new_committed_operations": committed,
            "original_expired_lease": expired,
            "released_generations": [binding["generation"] for binding, _ in bindings],
            "actual_release_head_digests": [receipt["lease_head_digest"] for _, receipt in bindings],
            "original_writer_table_rows": {name: len(value) for name, value in rows.items()},
            "native_execution_verified": False}


def initial_lease(rows, previous):
    """Bind the first stopped physical active lease, never infer it later."""
    e.require(type(rows) is list and len(rows) == 1, "the first physical original lease prefix must be complete")
    operation = previous["operation"]
    head = rows[0]
    old.chain(rows, "lease", fixed.AGENT, operation["lease_id"])
    e.require(head["state"] == "active" and head["generation"] == operation["generation"] == 1
              and head["fencing_token"] == operation["fencing_token"]
              and head["authority_epoch"] == operation["authority_epoch"]
              and head["owner_epoch"] == operation["owner_epoch"],
              "first stopped lease is not the exact initial owner of the unresolved operation")
    return head


def observe_initial_lease(connection, previous, queries):
    original_factory = connection.row_factory
    connection.row_factory = sqlite3.Row
    query = "SELECT " + ",".join(old.LEASE_COLUMNS) + " FROM cognitive_local_leases ORDER BY lease_sequence LIMIT 2"
    try:
        rows = [dict(row) for row in connection.execute(query)]
    finally:
        connection.row_factory = original_factory
    initial_lease(rows, previous)
    queries.append({"sql": query, "parameters": [], "row_count": len(rows)})
    return rows


def read_rows(connection, queries):
    """Read the complete five fixed journals in the caller's read-only snapshot."""
    rows = {}
    original_factory = connection.row_factory
    connection.row_factory = sqlite3.Row
    try:
        for name, (columns, ordering) in inventory.TABLES.items():
            query = "SELECT " + ",".join(columns) + " FROM " + name + " ORDER BY " + ordering + " LIMIT ?"
            actual = [dict(row) for row in connection.execute(query, (old.MAX_ROWS + 1,))]
            e.require(len(actual) <= old.MAX_ROWS and len(e.canonical(actual).encode()) <= old.MAX_ROW_BYTES,
                      "complete original renewal journal exceeds its unchanged forensic bound")
            queries.append({"sql": query, "parameters": [old.MAX_ROWS + 1], "row_count": len(actual)})
            rows[name] = actual
    finally:
        connection.row_factory = original_factory
    return rows


def observe(connection, previous, operations, releases, queries, *, partial=False):
    """Use the caller's one read-only snapshot, including its actual WAL."""
    return verify_rows(read_rows(connection, queries), previous, operations, releases, partial=partial)


def observe_fresh(connection, cut, queries):
    """Require the complete first stopped database, with exactly one old K."""
    rows = read_rows(connection, queries)
    leases, events, outbox, ledger, claims = [rows[name] for name in inventory.TABLES]
    e.require(len(ledger) == len(outbox) == len(leases) == 1
              and all(row["operation_id"] == cut["occurrence_key"] for row in claims)
              and all(row["occurrence_key"] == cut["occurrence_key"] for row in events),
              "first stopped original owner contains another hidden K, lease or event")
    result = old.verify_old_rows(ledger[0], outbox, events, leases, claims, fixed.AGENT,
                                cut["occurrence_key"], cut["payload_json"])
    initial_lease(leases, result)
    result["lease_rows"] = leases
    result["original_writer_table_rows"] = {name: len(value) for name, value in rows.items()}
    return result
