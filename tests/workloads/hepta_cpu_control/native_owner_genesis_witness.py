"""Original no-head activation commitments and issuer reservation bytes.

These read-only checks neither sign a proof nor turn an unsigned observation
into authority. The actual original Root must admit/verify the canonical chain.
"""
import hashlib
import re

import native_owner_activation_witness as current_witness
import native_owner_continuity_types as types
import native_owner_evidence as e
import native_owner_genesis_record as genesis
import native_owner_genesis_types as t
import native_owner_prior_boot_types as fixed


DOMAIN = "hepta.original-checkpoint.genesis-activation.v1"
KEYS = ("schema_version", "genesis_sha256", "root", "peer", "candidate", "predecessor_proof")
PENDING_KEYS = ("schema_version", "purpose", "previous_sequence", "expected_state_sha256", "verifying_key",
                "admitted_at_unix_ms", "signing_bytes_sha256", "claims")
SIGNING_DOMAIN = b"hepta:root-authority:production-writer:v1\0"


def claims(value):
    value = e.ordered(value, types.CLAIM_KEYS, "original complete signed/reserved writer claims")
    e.integer(value["schema_version"], "original writer claims schema", 1, 1)
    e.require(value["issuer_id"] == fixed.SIGNER, "original writer claims name another issuer")
    e.integer(value["sequence"], "original writer sequence", 1)
    writer = current_witness.candidate_ordered({key: value[key] for key in types.REGISTRATION_KEYS})
    e.require(writer["registered_agent_id"] == fixed.AGENT and writer["local_lease_id"] == "native-cpu-original-writer"
              and type(writer["local_lease_generation"]) is int and writer["local_lease_generation"] == 1,
              "original no-head claims escaped their one first local writer generation")
    for key in ("spawn_generation", "owner_epoch"):
        e.integer(writer[key], "original no-head writer " + key, 1)
    lease = types.lease(writer["authority_lease"], fixed.AGENT, 20000,
                        "runtime.agentd.production_writer", "cognitive.owner:" + fixed.AGENT)
    e.require(lease["authority_epoch"] == 1 and value["authority_lease_sha256"] == types.sha(lease),
              "original no-head claims changed their full finite authority lease")
    value.update(writer)
    return value


def proof(value):
    value = e.ordered(value, ("claims", "signature_hex"), "complete original canonical writer proof")
    value["claims"] = claims(value["claims"])
    signature = value["signature_hex"]
    e.require(type(signature) is str and re.fullmatch(r"[0-9a-f]{128}", signature)
              and any(character != "0" for character in signature), "original canonical signature encoding differs")
    return value


def commitment(candidate, genesis_sha256, root, peer, predecessor=None):
    candidate = current_witness.candidate_ordered(candidate)
    candidate["authority_lease"]["binding"]["payload_sha256"] = [0] * 32
    return types.sha([DOMAIN, candidate, e.digest(genesis_sha256, "actual original genesis payload"),
                      e.ordered(root, e.PEER_KEYS, "actual preparing Root"),
                      e.ordered(peer, e.PEER_KEYS, "actual first-generation peer"),
                      None if predecessor is None else proof(predecessor)])


def expected(candidate, saved, root, peer, predecessor=None):
    candidate = current_witness.candidate_ordered(candidate)
    root = e.ordered(root, e.PEER_KEYS, "actual genesis preparing Root lifetime")
    peer = e.ordered(peer, e.PEER_KEYS, "actual genesis candidate Process lifetime")
    e.require(type(root["uid"]) is int and root["uid"] == 0 and type(root["pid"]) is int and root["pid"] == 1
              and type(peer["uid"]) is int and peer["uid"] == 60001 and type(peer["pid"]) is int and peer["pid"] == 2
              and root["boot_id"] == peer["boot_id"], "original genesis witness lacks its actual Root and first Manager lifetimes")
    for lifetime in (root, peer):
        e.integer(lifetime["process_start_ticks"], "actual original genesis Process start", 1)
    e.require(candidate["registered_agent_id"] == fixed.AGENT and candidate["local_lease_id"] == "native-cpu-original-writer"
              and type(candidate["local_lease_generation"]) is int and candidate["local_lease_generation"] == 1,
              "original genesis candidate changed its first local writer identity")
    e.integer(candidate["spawn_generation"], "actual original candidate spawn", 1)
    e.integer(candidate["owner_epoch"], "actual original candidate owner epoch", 1)
    lease = types.lease(candidate["authority_lease"], fixed.AGENT, 20000,
                        "runtime.agentd.production_writer", "cognitive.owner:" + fixed.AGENT)
    e.require(lease["authority_epoch"] == 1
              and lease["lease_id"] == "native-cpu.writer." + peer["boot_id"] + "." + str(candidate["spawn_generation"])
              and bytes(lease["binding"]["scope_sha256"]).hex() == types.sha([
                  fixed.AGENT, fixed.BASE + "/fleet/agents/" + fixed.AGENT + "/cognitive"])
              and bytes(lease["binding"]["payload_sha256"]).hex()
                  == commitment(candidate, saved["payload_sha256"], root, peer, predecessor),
              "first writer payload is not its complete original genesis activation commitment")
    predecessor = None if predecessor is None else proof(predecessor)
    if predecessor is None:
        e.require(candidate["owner_epoch"] == 1, "initial genesis activation invented an earlier writer")
    else:
        old = predecessor["claims"]
        e.require(candidate["spawn_generation"] > old["spawn_generation"]
                  and candidate["owner_epoch"] == old["owner_epoch"] + 1
                  and all(candidate[key] == old[key] for key in ("registered_agent_id", "local_lease_id", "local_lease_generation"))
                  and lease["lease_id"] != old["authority_lease"]["lease_id"]
                  and lease["binding"]["scope_sha256"] == old["authority_lease"]["binding"]["scope_sha256"],
                  "original unpublished replacement reset its exact signed predecessor lineage")
    value = {"schema_version": 1, "genesis_sha256": saved["payload_sha256"], "root": root, "peer": peer,
             "candidate": candidate, "predecessor_proof": predecessor}
    raw = e.canonical(value)
    identity = "checkpoint-genesis-activation-v1." + types.sha(candidate)
    return {"observation_id": identity, "filename": fixed.cut_filename(identity), "payload": value,
            "durable_payload_json": raw, "payload_sha256": hashlib.sha256(raw.encode()).hexdigest()}


def observed(value, saved, root, peer, candidate, device, predecessor=None):
    e.obj(value, ("writer", "peer", "activation"), "actual original no-head candidate observation")
    e.require(value["writer"] == candidate and value["peer"] == peer,
              "actual stored no-head candidate observation changed its canonical writer or retained Process")
    wanted = expected(candidate, saved, root, peer, predecessor)
    payload, wrapper = t.observed_record(value["activation"], wanted["observation_id"], genesis.DIRECTORY, device)
    e.require(payload == wanted["payload"] and value["activation"]["payload_json"] == wanted["durable_payload_json"],
              "actual first-candidate observation lost its complete original typed commitment")
    wanted["observed_record"] = value["activation"]
    wanted["record_sha256"] = hashlib.sha256(wrapper).hexdigest()
    return wanted


def inspect(raw, wanted):
    e.require(type(raw) is bytes and 0 < len(raw) <= 16384, "bounded actual first-candidate observation required")
    expected = e.canonical({"schema_version": 1, "observation_id": wanted["observation_id"],
                            "payload": list(wanted["durable_payload_json"].encode())}).encode()
    e.require(raw == expected, "actual first-candidate observation bytes differ from its complete original commitment")
    return {"observation_id": wanted["observation_id"], "payload_sha256": wanted["payload_sha256"],
            "record_sha256": hashlib.sha256(raw).hexdigest(), "native_execution_verified": False}


def pending(value, before, writer, public_key):
    e.obj(value, (*t.ISSUER_KEYS, "writer_reservation"), "actual original reserved issuer state")
    before = e.ordered(before, t.ISSUER_KEYS, "actual pre-admission original issuer")
    before["policies"] = genesis.policies(before["policies"])
    before["head"] = e.ordered(before["head"], ("authority_epoch", "revision", "revoked_grant_ids"), "initial revocation head")
    e.require(before["sequence"] == 0 and before["writer_authorization"] is None and value["sequence"] == 1
              and type(value["sequence"]) is int and value["writer_authorization"] is None
              and all(value[key] == before[key] for key in ("signer_id", "policies", "head")),
              "actual reserved first writer changed the original preimage, sequence or prematurely signed")
    reserve = e.ordered(value["writer_reservation"], PENDING_KEYS, "complete original pending writer reservation")
    e.integer(reserve["schema_version"], "original reservation version", 1, 1)
    e.integer(reserve["previous_sequence"], "original first reservation predecessor", 0, 0)
    e.require(reserve["purpose"] == {"kind": "initial"} and reserve["verifying_key"] == public_key
              and reserve["expected_state_sha256"] == types.sha(before),
              "original reservation purpose, public key or typed expected preimage digest differs")
    actual = claims(reserve["claims"])
    e.require(actual["sequence"] == 1 and {key: actual[key] for key in types.REGISTRATION_KEYS} == writer,
              "actual reserved original claims changed the exact prepared first candidate")
    lease = writer["authority_lease"]
    e.integer(reserve["admitted_at_unix_ms"], "original reservation admission time",
              lease["issued_at_unix_ms"], lease["expires_at_unix_ms"] - 1)
    e.require(reserve["signing_bytes_sha256"] == hashlib.sha256(SIGNING_DOMAIN + e.canonical(actual).encode()).hexdigest(),
              "actual pending original signing hash lost its domain or typed complete claims")
    reserve["claims"] = actual
    return reserve
