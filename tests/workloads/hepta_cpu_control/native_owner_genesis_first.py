"""Fixed original first-signature lookup; no scan, signer or authority lives here.

The original Root validates the canonical chain before saving this immutable
observation. This reader binds those exact bytes to the actual first owner's
proof hash and Current. Later canonical writers or pruned leases cannot replace
the retained sequence-one proof. Only actual build/VM gates qualify execution.
"""
import hashlib

import native_owner_activation_witness as current_witness
import native_owner_continuity_types as types
import native_owner_evidence as e
import native_owner_genesis_record as genesis
import native_owner_genesis_witness as witness
import native_owner_prior_boot_types as fixed


KEYS = ("schema_version", "genesis_sha256", "activation_id", "registration", "proof")
INITIAL_KEYS = ("root", "peer", "native_boot_id", "spaces", "owner")


def identity():
    return "checkpoint-genesis-first-writer-v1." + fixed.AGENT


def filename():
    return fixed.cut_filename(identity())


def expectation(proof, saved):
    proof = witness.proof(proof)
    claims = proof["claims"]
    writer = current_witness.candidate_ordered({key: claims[key] for key in types.REGISTRATION_KEYS})
    e.require(claims["sequence"] == writer["owner_epoch"] == writer["local_lease_generation"] == 1
              and writer["spawn_generation"] == 1,
              "fixed first-signature observation is not the original sequence-one first Supervisor candidate")
    payload = {"schema_version": 1, "genesis_sha256": saved["payload_sha256"],
               "activation_id": "checkpoint-genesis-activation-v1." + types.sha(writer),
               "registration": writer, "proof": proof}
    raw = e.canonical(payload)
    return {"observation_id": identity(), "filename": filename(), "payload": payload,
            "durable_payload_json": raw, "payload_sha256": hashlib.sha256(raw.encode()).hexdigest()}


def inspect(raw, saved, expected_proof=None):
    e.require(type(raw) is bytes and 0 < len(raw) <= 16384, "bounded original first-signature record required")
    wrapper = e.obj(e.json_value(raw), ("schema_version", "observation_id", "payload"), "original first-signature wrapper")
    e.integer(wrapper["schema_version"], "original first-signature wrapper version", 1, 1)
    encoded = wrapper["payload"]
    e.require(wrapper["observation_id"] == identity() and type(encoded) is list
              and all(type(value) is int and 0 <= value <= 255 for value in encoded),
              "original first-signature record changed its fixed identity or byte encoding")
    payload = e.obj(e.json_value(bytes(encoded)), KEYS, "original immutable first-signature payload")
    wanted = expectation(payload["proof"], saved)
    if expected_proof is not None:
        e.require(wanted["payload"]["proof"] == witness.proof(expected_proof),
                  "fixed original first-signature file was overwritten by another canonical proof")
    expected = e.canonical({"schema_version": 1, "observation_id": identity(),
                            "payload": list(wanted["durable_payload_json"].encode())}).encode()
    e.require(raw == expected, "original first-signature bytes lost their complete original typed binding")
    return {**wanted, "record_sha256": hashlib.sha256(raw).hexdigest(),
            "proof_sha256": types.sha(wanted["payload"]["proof"]), "native_execution_verified": False}


def read_record(disk, name):
    path = genesis.DIRECTORY + "/" + name
    lock = disk.read(path + ".lock", 0, 0o600, 0, allow_empty=True)
    record = disk.read(path, 0, 0o600, 16384)
    e.require(lock["inode"]["inode"] != record["inode"]["inode"], "original observation aliases its publication lock")
    return record, lock


def verify_open(disk, initial):
    e.obj(initial, INITIAL_KEYS, "actual initial original owner selector")
    root, peer, owner = initial["root"], initial["peer"], initial["owner"]
    e.require(owner["role"] == "manager" and owner["pid"] == peer["pid"] == 2
              and owner["agent_id"] == fixed.AGENT and owner["spawn_generation"] == 1,
              "fixed first-signature lookup requires the actual initial original Manager")
    genesis_file, genesis_lock = read_record(disk, genesis.filename())
    saved = genesis.inspect(genesis_file["raw"], expected_root=root,
                            boot=initial["native_boot_id"], spaces=initial["spaces"])
    e.require(hashlib.sha256(bytes(saved["payload"]["verifying_key"])).hexdigest() == owner["issuer_key_sha256"],
              "actual first owner's pinned public key differs from the original immutable genesis")
    record, lock = read_record(disk, filename())
    checked = inspect(record["raw"], saved)
    e.require(checked["proof_sha256"] == owner["writer_proof_sha256"],
              "fixed original first signature differs from the actual initial owner proof")
    value = checked["payload"]
    writer, proof = value["registration"], value["proof"]
    current = e.checkpoint(owner["current"], peer, fixed.AGENT)
    lease = writer["authority_lease"]
    fencing = hashlib.sha256(hashlib.sha256(b"hepta:production-authority-token-grant:v2\0"
        + checked["proof_sha256"].encode() + proof["signature_hex"].encode()).digest()).hexdigest()
    binding = {"lease_id": writer["local_lease_id"], "generation": 1, "authority_epoch": 1, "owner_epoch": 1,
               "authority_grant_digest": checked["proof_sha256"], "fencing_token_digest": fencing,
               "expires_at_unix_seconds": lease["expires_at_unix_ms"] // 1000}
    e.require(current["head"]["publisher_epoch"] == 1 and current["head"]["counter"] >= 1
              and current["head"]["writer_binding"] == binding,
              "actual initial Current does not bind the retained complete sequence-one grant and fence")
    expected_activation = witness.expected(writer, saved, root, peer)
    e.require(value["activation_id"] == expected_activation["observation_id"],
              "original fixed first signature points to another complete first-candidate witness")
    activation, activation_lock = read_record(disk, expected_activation["filename"])
    actual_activation = witness.inspect(activation["raw"], expected_activation)
    records = (genesis_file, genesis_lock, record, lock, activation, activation_lock)
    e.require(len({value["inode"]["inode"] for value in records}) == len(records),
              "distinct original genesis/signature/activation records alias one physical inode")
    return {"schema": "hepta.original-first-writer-files.v1", "passed": True,
            "genesis": {**saved, "record": disk.public(genesis_file), "lock": disk.public(genesis_lock)},
            "first_signature": {**checked, "record": disk.public(record), "lock": disk.public(lock)},
            "activation": {**actual_activation, "record": disk.public(activation), "lock": disk.public(activation_lock)},
            "filenames": [genesis.filename(), filename(), expected_activation["filename"]],
            "original_first_payload_commitment_verified": True, "native_execution_verified": False,
            "private_key_bytes_read_or_exported": False, "g2_complete": False, "production_ready": False}
