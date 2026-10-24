"""Read the original checkpoint activation commitment, never mint authority.

Only the original producer's current full-candidate commitment is accepted.
The older cut/spawn/local-generation payload is deliberately not a fallback.
Expected bytes below are independent checks of actual transcript values; they
are never installed in a guest, handed to a Root or used as signing inputs.
"""
import copy
import hashlib

import native_owner_evidence as e
import native_owner_continuity_types as t


DOMAIN = "hepta.original-checkpoint.activation.v1"
DIRECTORY = "/state/hepta-native/protected/authority/checkpoint"
RECORD_KEYS = ("schema_version", "previous_token", "material_cut_sha256", "root", "peer", "candidate")


def candidate_ordered(value):
    value = copy.deepcopy(e.ordered(value, t.REGISTRATION_KEYS, "original complete activation candidate"))
    lease = e.ordered(value["authority_lease"], t.LEASE_KEYS, "original complete activation lease")
    lease["binding"] = e.ordered(lease["binding"], t.BINDING_KEYS, "original complete activation binding")
    value["authority_lease"] = lease
    return value


def commitment(candidate, previous, root, peer):
    candidate = candidate_ordered(candidate)
    candidate["authority_lease"]["binding"]["payload_sha256"] = [0] * 32
    material = t.sha(e.ordered(previous["head"]["last_current"], e.CUT_KEYS, "original activation material anchor"))
    return t.sha([DOMAIN, candidate, e.ordered(previous["token"], e.TOKEN_KEYS, "whole original predecessor token"),
                  material, e.ordered(root, e.PEER_KEYS, "actual preparing Root lifetime"),
                  e.ordered(peer, e.PEER_KEYS, "actual candidate publisher lifetime")])


def expectation(candidate, previous, root, peer, material_sha256):
    candidate = candidate_ordered(candidate)
    agent = candidate["registered_agent_id"]
    old = e.checkpoint(previous, previous["head"]["peer_lifetime"], agent)["head"]
    root = e.ordered(root, e.PEER_KEYS, "actual preparing Root")
    peer = e.ordered(peer, e.PEER_KEYS, "actual activation publisher")
    e.require(root["uid"] == 0 and type(root["uid"]) is int and root["pid"] == 1 and type(root["pid"]) is int
              and peer["uid"] == old["peer_lifetime"]["uid"] == 60001 and type(peer["uid"]) is int
              and type(peer["pid"]) is int and 1 < peer["pid"] < 1 << 31
              and root["boot_id"] == peer["boot_id"] and peer != old["peer_lifetime"],
              "activation commitment did not capture the actual Root and distinct final publisher")
    for value in (root, peer):
        e.text(value["boot_id"], "actual activation Linux boot", 36)
        e.integer(value["process_start_ticks"], "actual activation Process start", 1)
    for name in ("spawn_generation", "owner_epoch", "local_lease_generation"):
        e.integer(candidate[name], "original activation " + name, 1)
    lease = t.lease(candidate["authority_lease"], agent, 20_000,
                    "runtime.agentd.production_writer", "cognitive.owner:" + agent)
    e.require(candidate["local_lease_id"] == old["writer_binding"]["lease_id"]
              and candidate["local_lease_generation"] == old["writer_binding"]["generation"] + 1
              and candidate["owner_epoch"] > old["writer_binding"]["owner_epoch"]
              and lease["authority_epoch"] == old["writer_binding"]["authority_epoch"]
              and lease["lease_id"] == "native-cpu.writer." + peer["boot_id"] + "." + str(candidate["spawn_generation"])
              and bytes(lease["binding"]["payload_sha256"]).hex() == commitment(candidate, previous, root, peer),
              "original activation payload does not commit to the full candidate, token, physical cut and real lifetimes")
    record = {"schema_version": 1, "previous_token": e.ordered(previous["token"], e.TOKEN_KEYS, "original witness token"),
              "material_cut_sha256": t.sha(e.ordered(old["last_current"], e.CUT_KEYS, "original material anchor")),
              "root": root, "peer": peer, "candidate": candidate}
    payload = e.canonical(record)
    identity = "checkpoint-activation-v1." + t.sha(candidate)
    filename = "observation-v1-" + hashlib.sha256(identity.encode()).hexdigest() + ".json"
    material_path = DIRECTORY.removesuffix("/checkpoint") + "/material/" + record["material_cut_sha256"]
    material_path += "/agents/" + agent + "/cognitive/cognitive_1.sqlite3"
    e.require(len(e.canonical({"schema_version": 1, "observation_id": identity, "payload": list(payload.encode())}).encode()) <= 16384,
              "original bounded Root activation record exceeds its unchanged 16 KiB encoding")
    return {"selection": "complete-transcript-candidate", "observation_id": identity, "filename": filename,
            "durable_payload_json": payload, "payload_sha256": hashlib.sha256(payload.encode()).hexdigest(),
            "material_path": material_path, "material_sha256": e.digest(material_sha256, "original activation physical material")}


def pending_final_canonical(previous, root, peer, material_sha256, owner):
    """The two old crash DTOs omit the full candidate; select it only on disk.

    Selection must use that run's exact final original canonical proof, whose
    full binding, hash and real spawn already appear in the original Current.
    No observation directory scan or latest-file choice can supply a candidate.
    """
    e.require(owner["current"]["head"]["peer_lifetime"] == peer,
              "original final canonical candidate belongs to another actual publisher")
    return {"selection": "exact-final-canonical-proof", "previous": previous, "root": root, "peer": peer,
            "material_sha256": e.digest(material_sha256, "original predecessor physical material"),
            "owner": owner}


def inspect(raw, expected):
    e.require(type(raw) is bytes and 0 < len(raw) <= 16384, "complete bounded physical Root activation record required")
    value = e.obj(e.json_value(raw), ("schema_version", "observation_id", "payload"), "original physical Root observation")
    wanted = {"schema_version": 1, "observation_id": expected["observation_id"],
              "payload": list(expected["durable_payload_json"].encode())}
    e.require(value == wanted and raw == e.canonical(wanted).encode()
              and hashlib.sha256(bytes(value["payload"])).hexdigest() == expected["payload_sha256"],
              "actual retained activation observation differs from its complete original signed commitment")
    return {"observation_id": expected["observation_id"], "filename": expected["filename"],
            "payload_sha256": expected["payload_sha256"], "record_sha256": hashlib.sha256(raw).hexdigest()}
