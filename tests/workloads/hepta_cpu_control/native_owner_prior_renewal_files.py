"""Exact original Root observation and FinalUse files for the new campaign.

The old cut, actual kernel launch records and their original locks form one
closed inventory. These checks never create a Root record or effect claim.
"""
import hashlib
import struct

import native_owner_evidence as e
import native_owner_prior_boot_authority as authority
import native_owner_prior_boot_types as fixed
import native_owner_root_observation as launch


def saved_observations(disk, transcript):
    fresh = transcript["phase"] == "fresh"
    cut = transcript["cut_event"] if fresh else transcript["adoption_event"]
    launches = transcript["root_launch_observations_expected"]
    e.require(type(launches) is list and (not launches if fresh else 2 <= len(launches) <= 63),
              "bounded actual second-boot kernel pair observations are required")
    directory = disk.directory(fixed.OBSERVATIONS, 0, 0o700)
    cut_name = fixed.cut_filename(cut["observation_id"])
    expected = {cut_name}
    for value in launches:
        name = launch.launch_observation_filename(value["observation_id"])
        e.require(name not in expected, "an actual Root observation was counted twice")
        expected.add(name)
    e.require(set(disk.entries(fixed.OBSERVATIONS)) == {".", "..", *expected, *(name + ".lock" for name in expected)},
              "actual Root directory contains a missing, extra or unfinished observation")
    records, locks, inodes = {}, {}, set()
    for name in sorted(expected):
        for key, target, minimum in ((records, name, 1), (locks, name + ".lock", 0)):
            record = disk.read(fixed.OBSERVATIONS + "/" + target, 0, 0o600,
                               launch.MAX_OBSERVATION_BYTES if minimum else 0, allow_empty=not minimum)
            e.require(record["inode"]["inode"] not in inodes, "original Root record and lock inodes alias")
            inodes.add(record["inode"]["inode"])
            key[name] = record
    wrapper = {"schema_version": 1, "observation_id": cut["observation_id"],
               "payload": list(cut["durable_payload_json"].encode())}
    e.require(records[cut_name]["raw"] == e.canonical(wrapper).encode()
              and hashlib.sha256(bytes(wrapper["payload"])).hexdigest() == cut["durable_payload_sha256"],
              "the original physical cut differs from its actual retained serialized bytes")
    checked_launches = []
    for value in launches:
        name = launch.launch_observation_filename(value["observation_id"])
        record = records[name]
        checked = launch.inspect_saved_launch(record["raw"], value["boot_id"], value["launch_generation"],
                                              value["durable_payload_json"])
        e.require(checked["filename"] == name and checked["payload_sha256"] == value["durable_payload_sha256"],
                  "actual original launch file differs from the returned Root receipt")
        checked_launches.append({**checked, "record": disk.public(record), "lock": disk.public(locks[name])})
    return {"directory": directory, "record": disk.public(records[cut_name]), "lock": disk.public(locks[cut_name]),
            "launch_files": checked_launches, "exact_inventory_verified": True,
            "readonly_extraction": True, "native_execution_verified": False}


def consumers(disk, expected, installation, new_effects, prior=None):
    """One old claim plus exactly one original claim per actual new effect."""
    e.integer(new_effects, "actual new Manager effects", 0, 64)
    e.require((prior is None and new_effects == 0) or (type(prior) is dict and 3 <= new_effects <= 64),
              "first-cut or complete continued-effect consumer scope required")
    result = {"parent": disk.directory(fixed.BASE + "/consumer-local", 60001, 0o700)}
    for lane, observed in zip(("device", "notes"), expected):
        directory = fixed.BASE + "/consumer-local/" + lane
        meta = disk.directory(directory, 60001, 0o700)
        e.require(set(disk.entries(directory)) == {".", "..", "authority.json", "authority.claims", "authority.lock"},
                  "original FinalUse directory contains a missing, extra or staged file")
        state = disk.read(directory + "/authority.json", 60001, 0o600, 8 * 1024**2)
        claims = disk.read(directory + "/authority.claims", 60001, 0o600, 8 * 1024**2, allow_empty=True)
        lock = disk.read(directory + "/authority.lock", 60001, 0o600, 0, allow_empty=True)
        value = e.obj(e.json_value(state["raw"]), ("schema", "signer_id", "trust", "head"), "original FinalUse state")
        e.require(type(value["schema"]) is int and value["schema"] == 3 and value["signer_id"] == fixed.SIGNER,
                  "original FinalUse persistent identity or schema changed")
        fixed.revocations(value["head"])
        e.require(value["trust"] == {"IssuerKeyRing": authority.keyring_digest(
                    installation["expected_verifying_key"], value["head"]["authority_epoch"])},
                  "original FinalUse no longer binds the independently retained issuer key")
        raw = claims["raw"]
        e.require(len(raw) % 40 == 0, "original FinalUse journal has a partial claim frame")
        nonces = []
        for offset in range(0, len(raw), 40):
            epoch, nonce = struct.unpack_from(">Q", raw, offset)[0], raw[offset + 8:offset + 40]
            e.require(epoch == value["head"]["authority_epoch"] and any(nonce) and nonce not in nonces,
                      "original claim epoch was reset or an exact-effect nonce repeated")
            nonces.append(nonce)
        e.require(len(nonces) == (1 + new_effects if lane == "device" else 0),
                  "old Unknown was redispatched or a true continued exact-effect claim was lost")
        protected, protected_file = authority.root_record(disk, fixed.AUTHORITY + "/" + lane + "-consumer", fixed.SIGNER)
        e.require(authority.final_use_frontier(value["head"], nonces) == observed == protected,
                  "local original journal, protected frontier and actual owner observations disagree")
        if prior is not None:
            old = prior[lane]
            e.require(state["sha256"] == old["state_file"]["sha256"]
                      and state["inode"] == old["state_file"]["inode"]
                      and meta["inode"] == old["directory"]["inode"]
                      and lock["inode"] == old["lock_file"]["inode"]
                      and claims["inode"]["inode"] == old["claims_file"]["inode"]["inode"]
                      and raw[:old["claim_bytes"]] == bytes.fromhex(old["claims_hex"]),
                      "continued owners recreated original FinalUse custody or discarded the old claim")
        result[lane] = {"directory": meta, "state_file": disk.public(state), "claims_file": disk.public(claims),
                        "lock_file": disk.public(lock), "protected_file": protected_file, "frontier": protected,
                        "claim_bytes": len(raw), "claims_hex": raw.hex(), "claim_count": len(nonces)}
    return result


def preserved_records(previous, pin, observations, witnesses):
    for before, after in ((previous["installation"]["file"], pin["file"]),
                          (previous["saved_observation"]["record"], observations["record"]),
                          (previous["saved_observation"]["lock"], observations["lock"])):
        e.require(before["sha256"] == after["sha256"] and before["inode"] == after["inode"],
                  "same disk recreated the original pin or saved cut/lock")
    for kind in ("genesis", "first_signature", "activation"):
        for part in ("record", "lock"):
            before = previous["activation_witnesses"]["first_writer"][kind][part]
            after = witnesses["first_writer"][kind][part]
            e.require(before["sha256"] == after["sha256"] and before["inode"] == after["inode"],
                      "same disk changed immutable original sequence-one/genesis/first-activation custody")
