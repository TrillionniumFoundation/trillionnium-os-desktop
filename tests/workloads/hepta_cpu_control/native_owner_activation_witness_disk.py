"""Independent read-only checks of original activation witnesses on ext2.

Expected candidates come from complete actual transcript DTOs, or (only for
the two earlier single-successor crash cases) the exact final canonical proof
on the actual stopped disk. A directory scan never selects an authority.
No private key bytes are read. Physical material is hashed as retained bytes.
"""
from pathlib import Path

import native_owner_activation_witness as witness
import native_owner_continuity_types as types
import native_owner_evidence as e
import native_owner_prior_boot_authority as authority
import native_owner_prior_boot_disk as physical
import native_owner_prior_boot_types as fixed
import run_native_owner as original


def resolve_final_canonical(disk, pending):
    e.obj(pending, ("selection", "previous", "root", "peer", "material_sha256", "owner"),
          "single original canonical candidate selector")
    e.require(pending["selection"] == "exact-final-canonical-proof", "unsupported activation selection")
    owner = pending["owner"]
    e.require(owner["role"] == "recovery" and owner["pid"] == pending["peer"]["pid"]
              and owner["agent_id"] == fixed.AGENT, "the two fixed crash cases require their actual final Recovery")
    issuer, issuer_file = authority.root_record(disk, fixed.AUTHORITY + "/issuer", "local-final-use-issuer")
    e.obj(issuer, ("signer_id", "policies", "head", "sequence", "writer_authorization"), "original canonical issuer")
    e.require(issuer["signer_id"] == fixed.SIGNER, "physical canonical issuer identity differs")
    proof = e.obj(issuer["writer_authorization"], ("claims", "signature_hex"), "physical canonical writer proof")
    claims = e.obj(proof["claims"], types.CLAIM_KEYS, "physical canonical complete writer claims")
    e.require(claims["issuer_id"] == issuer["signer_id"], "physical canonical proof names another original issuer")
    writer = witness.candidate_ordered({key: claims[key] for key in types.REGISTRATION_KEYS})
    e.require(writer["registered_agent_id"] == owner["agent_id"]
              and writer["spawn_generation"] == owner["spawn_generation"] and type(writer["spawn_generation"]) is int,
              "physical canonical proof is not this run's observed original successor")
    e.integer(issuer["sequence"], "actual retained original issuer highwater", e.integer(claims["sequence"], "original signed sequence", 1))
    raw_registry = disk.read(fixed.AUTHORITY + "/leases/authority-leases.json", 0, 0o600, 64 * 1024**2)
    registry = e.obj(e.json_value(raw_registry["raw"]), ("schema_version", "owner_id", "state"), "original retained registry")
    e.require(type(registry["schema_version"]) is int and registry["schema_version"] == 2
              and registry["owner_id"] == "root-authority-leases-v1", "actual original registry schema or owner differs")
    frontier, frontier_file = authority.root_record(disk, fixed.AUTHORITY, "root-authority-leases-v1")
    e.require(authority.lease_frontier(registry["state"]) == frontier,
              "actual retained original leases differ from their complete protected frontier")
    root_id = "native-cpu.root." + pending["root"]["boot_id"] + "." + str(writer["spawn_generation"])
    root = registry["state"]["leases"].get(root_id)
    e.require(root is not None and registry["state"]["leases"].get(writer["authority_lease"]["lease_id"])
              == writer["authority_lease"], "original canonical candidate or Root lease is absent from the retained registry")
    checked = types.authority(root, writer, proof, owner["current"], owner["agent_id"])
    e.require(checked["proof_sha256"] == owner["writer_proof_sha256"],
              "exact retained canonical proof differs from the actual observed original Current")
    result = witness.expectation(writer, pending["previous"], pending["root"], pending["peer"], pending["material_sha256"])
    return result, {"selection": pending["selection"], "issuer_file": issuer_file,
                    "registry_file": disk.public(raw_registry), "registry_frontier_file": frontier_file,
                    "writer_proof_sha256": checked["proof_sha256"], "issuer_sequence": issuer["sequence"],
                    "private_key_bytes_read_or_exported": False}


def verify_open(disk, expected):
    e.require(type(expected) is list and len(expected) <= 256, "bounded original activation witness list required")
    pending = [value for value in expected if value.get("selection") == "exact-final-canonical-proof"]
    e.require(not pending or len(expected) == len(pending) == 1,
              "final canonical selection cannot replace a historical multi-owner transcript")
    resolved, selections = [], []
    for value in expected:
        if value.get("selection") == "exact-final-canonical-proof":
            value, selection = resolve_final_canonical(disk, value)
            selections.append(selection)
        e.require(value.get("selection") == "complete-transcript-candidate", "unknown witness authority selector")
        resolved.append(value)
    parent = disk.directory(witness.DIRECTORY, 0, 0o700)
    entries = disk.entries(witness.DIRECTORY)
    names = [value["filename"] for value in resolved]
    e.require(len(names) == len(set(names)), "one original saved activation was counted twice")
    original_frontier = authority.frontier_name("root-cognitive-checkpoint-v1")
    e.require(set(entries) == {".", "..", original_frontier, original_frontier + ".lock",
                               *names, *(name + ".lock" for name in names)},
              "original checkpoint directory contains missing, unexpected or unsigned activation records")
    disk.regular(witness.DIRECTORY + "/" + original_frontier, 0, 0o600, 65536, 1)
    disk.regular(witness.DIRECTORY + "/" + original_frontier + ".lock", 0, 0o600, 0)
    material_seen, actual, inode_seen = {}, [], set()
    for value in resolved:
        path = witness.DIRECTORY + "/" + value["filename"]
        lock = disk.read(path + ".lock", 0, 0o600, 0, allow_empty=True)
        stored = disk.read(path, 0, 0o600, 16384)
        checked = witness.inspect(stored["raw"], value)
        for record in (lock, stored):
            e.require(record["inode"]["inode"] not in inode_seen, "two original witness records alias the same inode")
            inode_seen.add(record["inode"]["inode"])
        material_path = value["material_path"]
        if material_path not in material_seen:
            disk.directory(str(Path(material_path).parent), 0, 0o700)
            material = disk.read(material_path, 0, 0o600, original.STATE_BYTES)
            material_seen[material_path] = disk.public(material)
        material = material_seen[material_path]
        e.require(material["sha256"] == value["material_sha256"],
                  "actual original activation material differs from its independently observed retained physical bytes")
        actual.append({**checked, "record": disk.public(stored), "lock": disk.public(lock), "physical_material": material})
    return {"schema": "hepta.original-checkpoint-activation-files.v1", "passed": True,
            "readonly_extraction": True, "directory": parent, "actual_files": actual,
            "canonical_selections": selections, "original_activation_commitment_version": 1,
            "private_key_bytes_read_or_exported": False, "native_execution_verified": False,
            "g2_complete": False, "production_ready": False}


def verify(image, tool, tool_identity, expected_sha256, expected, output):
    with physical.Disk(image, expected_sha256, tool, tool_identity, output) as disk:
        result = verify_open(disk, expected)
        result.update(state_path=str(image), state_sha256=expected_sha256, tool=tool_identity, command_count=len(disk.commands))
    original.save(Path(output) / "result.json", result)
    return result


def accept_expected(transcript, files):
    e.require(files.get("passed") is True and files.get("readonly_extraction") is True
              and transcript.get("activation_witness_files_verified") is False,
              "actual original retained witness files must be independently verified once")
    expected = transcript["activation_witnesses_expected"]
    e.require(len(files["actual_files"]) == len(expected), "retained witness count differs from actual original activations")
    if all(value["selection"] == "complete-transcript-candidate" for value in expected):
        e.require({(value["observation_id"], value["payload_sha256"]) for value in expected}
                  == {(value["observation_id"], value["payload_sha256"]) for value in files["actual_files"]},
                  "physical original witnesses belong to another observed original owner chain")
    else:
        e.require(len(expected) == len(files["canonical_selections"]) == 1
                  and files["canonical_selections"][0]["writer_proof_sha256"] == expected[0]["owner"]["writer_proof_sha256"],
                  "physical witness was not selected by this exact actual final original canonical proof")
    transcript["activation_witness_files_verified"] = True
