"""Read complete original lease/proof/lifecycle DTOs in native transcripts.

Digest reconstruction binds original serialized bytes. It does not mint a
lease, verify an unprovided public key, or replace the original RootSession.
The actual source-bound Host remains the signature/current-authority verifier.
"""
import hashlib
import re

from native_owner_evidence import canonical, digest, integer, obj, ordered, require, text


BINDING_KEYS = ("principal_id", "operation_class", "destination_id", "scope_sha256", "payload_sha256")
LEASE_KEYS = ("schema_version", "lease_id", "authority_epoch", "revision", "binding", "issued_at_unix_ms", "expires_at_unix_ms")
REGISTRATION_KEYS = ("registered_agent_id", "spawn_generation", "owner_epoch", "local_lease_id",
                     "local_lease_generation", "authority_lease")
CLAIM_KEYS = ("schema_version", "issuer_id", "sequence", "registered_agent_id", "spawn_generation", "owner_epoch",
              "local_lease_id", "local_lease_generation", "authority_lease", "authority_lease_sha256")
RELEASE_KEYS = ("schema_version", "namespace", "lease_id", "owner_agent_id", "generation", "authority_grant_digest",
                "authority_epoch", "owner_epoch", "state", "lease_head_digest", "external_effect")
SNAPSHOT_KEYS = ("active", "healthy", "runtime_generation", "spawn_generation", "process_system_id", "events")


def sha(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def digest_array(value, name):
    require(type(value) is list and len(value) == 32 and any(value)
            and all(type(item) is int and 0 <= item <= 255 for item in value), name + " is not the actual SHA-256 byte array")
    return value


def lease(value, agent, lifetime_ms, operation, destination):
    value = ordered(value, LEASE_KEYS, "original authority lease")
    require(type(value["schema_version"]) is int and value["schema_version"] == 1, "original authority lease version differs")
    text(value["lease_id"], "original authority lease ID", 128)
    for key in ("authority_epoch", "revision", "issued_at_unix_ms", "expires_at_unix_ms"):
        integer(value[key], "original authority " + key, 1)
    require(value["revision"] == 1 and value["expires_at_unix_ms"] - value["issued_at_unix_ms"] == lifetime_ms,
            "an original finite authority lease was replaced or extended")
    binding = ordered(value["binding"], BINDING_KEYS, "original lease binding")
    require(binding["principal_id"] == agent and binding["operation_class"] == operation
            and binding["destination_id"] == destination, "authority lease escaped its original principal/operation/destination")
    digest_array(binding["scope_sha256"], "original authority scope")
    digest_array(binding["payload_sha256"], "original authority payload")
    value["binding"] = binding
    return value


def authority(root, writer, proof, current, agent):
    root = lease(root, agent, 120_000, "runtime.agentd.production_operation", "hos2.cpu-budget.v1")
    writer = ordered(writer, REGISTRATION_KEYS, "original registered writer")
    require(writer["registered_agent_id"] == agent, "writer registration changed the original Agent")
    for key in ("spawn_generation", "owner_epoch", "local_lease_generation"):
        integer(writer[key], "registered writer " + key, 1)
    text(writer["local_lease_id"], "original local writer ID")
    writer["authority_lease"] = lease(writer["authority_lease"], agent, 20_000,
                                      "runtime.agentd.production_writer", "cognitive.owner:" + agent)
    actual = writer["authority_lease"]
    require(root["authority_epoch"] == actual["authority_epoch"]
            and root["issued_at_unix_ms"] <= actual["issued_at_unix_ms"]
            and actual["expires_at_unix_ms"] <= root["expires_at_unix_ms"],
            "writer authority is outside its actual finite Root session")
    proof = ordered(proof, ("claims", "signature_hex"), "original signed writer proof")
    claims = ordered(proof["claims"], CLAIM_KEYS, "original signed writer claims")
    require(type(claims["schema_version"]) is int and claims["schema_version"] == 1,
            "original signed writer schema differs")
    text(claims["issuer_id"], "original issuer identity", 128)
    integer(claims["sequence"], "actual canonical issuer sequence", 1)
    require(all(claims[key] == writer[key] and type(claims[key]) is type(writer[key])
                for key in REGISTRATION_KEYS), "signed proof does not bind this complete original writer registration")
    claims["authority_lease"] = actual
    require(digest(claims["authority_lease_sha256"], "signed original lease hash") == sha(actual),
            "signed authority lease digest does not cover original canonical bytes")
    signature = proof["signature_hex"]
    require(type(signature) is str and re.fullmatch(r"[0-9a-f]{128}", signature) and any(character != "0" for character in signature),
            "original writer signature spelling is invalid")
    proof["claims"] = claims
    proof_sha = sha(proof)
    inner = hashlib.sha256(b"hepta:production-authority-token-grant:v2\0" + proof_sha.encode() + signature.encode()).digest()
    fencing_sha = hashlib.sha256(inner).hexdigest()
    binding = current["head"]["writer_binding"]
    require(binding["lease_id"] == writer["local_lease_id"]
            and binding["generation"] == writer["local_lease_generation"]
            and binding["authority_epoch"] == actual["authority_epoch"]
            and binding["owner_epoch"] == writer["owner_epoch"]
            and binding["expires_at_unix_seconds"] == actual["expires_at_unix_ms"] // 1000
            and binding["authority_grant_digest"] == proof_sha and binding["fencing_token_digest"] == fencing_sha,
            "Current does not bind the actual complete signed grant and original grant-bound fence")
    return {"root": root, "writer": writer, "proof": proof, "proof_sha256": proof_sha}


def supervisor(value, spawn, pid, active, prior=None, failed_recovery=False):
    obj(value, SNAPSHOT_KEYS, "actual original Supervisor snapshot")
    require(type(value["active"]) is bool and type(value["healthy"]) is bool
            and value["active"] is active and value["healthy"] is active,
            "actual Supervisor active/health state differs")
    if active:
        require(type(value["runtime_generation"]) is int and value["runtime_generation"] == spawn + 1
                and type(value["spawn_generation"]) is int and value["spawn_generation"] == spawn
                and type(value["process_system_id"]) is int and value["process_system_id"] == pid,
                "actual Supervisor does not hold this exact spawned healthy Process")
    else:
        require(all(value[key] is None for key in ("runtime_generation", "spawn_generation", "process_system_id")),
                "stopped original Supervisor still retains a live runtime")
    events = value["events"]
    require(type(events) is list and 4 <= len(events) <= 32, "complete bounded original Supervisor events required")
    previous_generation = spawn
    for event in events:
        obj(event, ("generation", "kind", "details"), "original Supervisor event")
        generation = integer(event["generation"], "original lifecycle event generation", spawn)
        require(generation >= previous_generation, "original lifecycle generation regressed")
        previous_generation = generation
        kind, details = event["kind"], event["details"]
        if kind in ("spawned", "healthy", "drain_requested", "stop_requested", "kill_requested"):
            require(details is None, "original unit lifecycle event has invented details")
        elif kind == "lifecycle":
            obj(details, ("state",), "original lifecycle state")
            require(details["state"] in ("starting", "running", "draining", "stopped", "failed"), "unknown original lifecycle state")
        elif kind == "exited":
            obj(details, ("success", "code"), "actual original ProcessExit")
            require(type(details["success"]) is bool and (details["code"] is None
                    or type(details["code"]) is int and -(1 << 31) <= details["code"] < 1 << 31),
                    "actual ProcessExit changed its original serde projection")
        else:
            require(failed_recovery and kind == "other", "unexpected original lifecycle fault or event")
            obj(details, ("detail",), "other original lifecycle event")
            detail = text(details["detail"], "retained original Debug event", 8192)
            require(detail.startswith(("AutomaticRestartQueued { attempt: ", "DriverFault(")),
                    "unexpected original fault path during dead initial Recovery consumption")
    expected_start = [(spawn, "lifecycle", {"state": "starting"}), (spawn, "spawned", None),
                      (spawn + 1, "lifecycle", {"state": "running"}), (spawn + 1, "healthy", None)]
    require([(event["generation"], event["kind"], event["details"]) for event in events[:4]] == expected_start,
            "original Starting/Spawned/Running/Healthy transaction was skipped or replaced")
    if active:
        require(len(events) == 4, "healthy original owner contains an unexpected lifecycle transition")
    elif not failed_recovery:
        require(prior is not None and events[:len(prior["events"])] == prior["events"],
                "original Supervisor stop replaced its own retained activation events")
        expected_end = [(spawn + 2, "lifecycle", {"state": "draining"}), (spawn + 2, "stop_requested", None),
                        (spawn + 3, "lifecycle", {"state": "stopped"}),
                        (spawn + 3, "exited", {"success": True, "code": 0})]
        require([(event["generation"], event["kind"], event["details"]) for event in events[4:]] == expected_end,
                "original release did not finish its exact stop/exit-zero/reap lifecycle")
    return value


def released(value, current, agent):
    obj(value, RELEASE_KEYS, "actual original ProductionLeaseReceipt")
    require(type(value["schema_version"]) is int and value["schema_version"] == 1
            and value["namespace"] == "production_durable_writer" and value["owner_agent_id"] == agent
            and value["state"] == "released" and value["external_effect"] is False,
            "actual original writer did not report its own successful release transaction")
    binding = current["head"]["writer_binding"]
    for key in ("lease_id", "generation", "authority_grant_digest", "authority_epoch", "owner_epoch"):
        require(value[key] == binding[key] and type(value[key]) is type(binding[key]),
                "release receipt does not bind its actual Current writer")
    digest(value["lease_head_digest"], "original released lease head")
    return value
