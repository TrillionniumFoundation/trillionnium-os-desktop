"""Read the original immutable installation observation without making a head.

The source record is RetainedCheckpointGenesis::GenesisRecord. It is an
installation input: validating these bytes does not create a Current, grant,
writer, proof or local generation zero. The native campaign separately checks
actual absence, retained material, registry, issuer and both real boots.
"""
import hashlib
import re
import struct

import native_owner_continuity_types as types
import native_owner_evidence as e
import native_owner_prior_boot_types as fixed


DIRECTORY = fixed.AUTHORITY + "/checkpoint"
KEYS = ("schema_version", "initial_root", "initial_cut", "issuer_id", "verifying_key", "policies")
POLICY_KEYS = ("subject_id", "destination_id", "scope_sha256", "lifetime_ms")


def identity(agent=fixed.AGENT):
    e.require(agent == fixed.AGENT, "the actual finite native installation Agent differs")
    return "checkpoint-genesis-v1." + agent


def filename(agent=fixed.AGENT):
    return "observation-v1-" + hashlib.sha256(identity(agent).encode()).hexdigest() + ".json"


def anchor(value, agent=fixed.AGENT):
    value = e.ordered(value, e.CUT_KEYS, "original initial physical material anchor")
    e.require(value["profile"] == "hepta:cognitive:exact-current-cut:v1"
              and value["owner_agent_id"] == agent == fixed.AGENT,
              "original genesis material names another owner or recovery profile")
    for name in ("schema_digest", "state_digest"):
        e.digest(value[name], "original genesis " + name)
    return value


def policies(value, boot=None, spaces=None):
    e.require(type(value) is list and len(value) == 2,
              "original native genesis requires its complete two finite namespace policies")
    result = []
    for policy in value:
        policy = e.ordered(policy, POLICY_KEYS, "original genesis effect policy")
        e.require(policy["subject_id"] == fixed.AGENT and policy["destination_id"] == "hos2.cpu-budget.v1"
                  and type(policy["lifetime_ms"]) is int and policy["lifetime_ms"] == 5000,
                  "original genesis effect policy domain or lifetime changed")
        types.digest_array(policy["scope_sha256"], "original genesis native scope")
        result.append(policy)
    e.require(result[0]["scope_sha256"] != result[1]["scope_sha256"],
              "original genesis namespace policies alias one scope")
    e.require((boot is None) == (spaces is None), "actual namespace evidence must be complete")
    if boot is not None:
        e.byte_id(boot, "original genesis kernel boot")
        e.obj(spaces, ("manager", "recovery"), "original genesis namespace pair")
        for index, name in enumerate(("manager", "recovery")):
            space = e.byte_id(spaces[name], "original genesis " + name + " namespace")
            scope = hashlib.sha256(b"hepta.hos2.cpu-budget.scope.v1\0" + bytes(boot)
                                   + bytes(space) + struct.pack("<QQ", 2, 1)).digest()
            e.require(bytes(result[index]["scope_sha256"]) == scope,
                      "original genesis policy is not the actual first final-image namespace")
    return result


def payload(value, expected_root=None, expected_anchor=None, expected_key=None, boot=None, spaces=None):
    value = e.ordered(value, KEYS, "original retained checkpoint genesis")
    e.require(type(value["schema_version"]) is int and value["schema_version"] == 1
              and value["issuer_id"] == fixed.SIGNER,
              "original genesis record version or issuer identity differs")
    root = e.ordered(value["initial_root"], e.PEER_KEYS, "original genesis Root lifetime")
    e.require(type(root["uid"]) is int and root["uid"] == 0
              and type(root["pid"]) is int and root["pid"] == 1,
              "original native genesis requires the actual Root Process")
    e.integer(root["process_start_ticks"], "original genesis Root start", 1)
    e.require(type(root["boot_id"]) is str
              and re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", root["boot_id"])
              and any(bytes.fromhex(root["boot_id"].replace("-", ""))),
              "original initial Root boot is not its actual canonical nonzero identity")
    if expected_root is not None:
        e.require(root == expected_root, "saved original genesis belongs to another observed Root lifetime")
    if boot is not None:
        e.require(root["boot_id"] == fixed.uuid(boot), "saved initial Root boot differs from actual initial roles")
    material = anchor(value["initial_cut"])
    if expected_anchor is not None:
        e.require(material == anchor(expected_anchor), "original saved installation substituted its physical starting cut")
    key = types.digest_array(value["verifying_key"], "original genesis pinned public key")
    if expected_key is not None:
        e.require(key == expected_key, "original saved genesis differs from the independent installation public-key pin")
    return {"schema_version": 1, "initial_root": root, "initial_cut": material,
            "issuer_id": fixed.SIGNER, "verifying_key": key,
            "policies": policies(value["policies"], boot, spaces)}


def inspect(raw, *, expected_root=None, expected_anchor=None, expected_key=None, boot=None, spaces=None):
    e.require(type(raw) is bytes and 0 < len(raw) <= 16384,
              "complete bounded original Root genesis observation required")
    record = e.obj(e.json_value(raw), ("schema_version", "observation_id", "payload"),
                   "original immutable Root observation")
    e.require(type(record["schema_version"]) is int and record["schema_version"] == 1
              and record["observation_id"] == identity()
              and type(record["payload"]) is list and len(record["payload"]) <= 16384
              and all(type(value) is int and 0 <= value <= 255 for value in record["payload"]),
              "original genesis wrapper changed identity, encoding or size")
    encoded = bytes(record["payload"])
    value = payload(e.json_value(encoded), expected_root, expected_anchor, expected_key, boot, spaces)
    e.require(e.canonical(value).encode() == encoded
              and raw == e.canonical({"schema_version": 1, "observation_id": identity(),
                                     "payload": list(encoded)}).encode(),
              "original genesis observation is not its complete original serialized byte sequence")
    cut_hash = hashlib.sha256(e.canonical(value["initial_cut"]).encode()).hexdigest()
    return {"observation_id": identity(), "filename": filename(), "payload": value,
            "payload_sha256": hashlib.sha256(encoded).hexdigest(),
            "record_sha256": hashlib.sha256(raw).hexdigest(),
            "material_path": fixed.AUTHORITY + "/material/" + cut_hash
                + "/agents/" + fixed.AGENT + "/cognitive/cognitive_1.sqlite3",
            "checkpoint_or_current_created": False, "native_execution_verified": False}
