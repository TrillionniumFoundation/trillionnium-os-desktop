"""Read the original physical Root/FinalUse records from a stopped volume.

Hash reconstruction checks original encodings; it grants no authority. No
private signing key bytes are read or exported by this module.
"""
import hashlib
import struct

import native_owner_evidence as e
import native_owner_continuity_types as original
import native_owner_prior_boot_types as t


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def frontier_name(owner):
    return "frontier-v1-" + sha(owner.encode()) + ".json"


def root_record(disk, directory, owner):
    record = disk.read(directory + "/" + frontier_name(owner), 0, 0o600, 65536)
    value = e.obj(e.json_value(record["raw"]), ("schema", "owner_id", "frontier"), "actual protected Root record")
    e.require(type(value["schema"]) is int and value["schema"] == 1 and value["owner_id"] == owner,
              "original protected Root record changed registration or schema")
    e.require(record["raw"] == e.canonical({"schema": 1, "owner_id": owner, "frontier": value["frontier"]}).encode(),
              "actual protected Root record differs from its original encoded bytes")
    return value["frontier"], disk.public(record)


def installed_pin(disk, expected, boot, agent):
    record = disk.read(t.PIN_PATH, 0, 0o600, 32768)
    e.require(record["sha256"] == expected["sha256"] and record["inode"]["bytes"] == expected["bytes"]
              and record["inode"]["inode"] == expected["inode"], "physical installed public pin differs from actual guest identity")
    value = e.obj(e.json_value(record["raw"]), ("schema_version", "agent_id", "initial_kernel_boot", "config"),
                  "actual original installed public bootstrap")
    e.require(type(value["schema_version"]) is int and value["schema_version"] == 1
              and value["agent_id"] == agent == t.AGENT and value["initial_kernel_boot"] == boot,
              "retained original installation reset its Agent or initial actual kernel boot")
    config = e.obj(value["config"], ("schema_version", "state_dir", "required_bind", "signer_id", "expected_verifying_key",
        "lease_id", "lease_revision", "writer", "checkpoint_state_dir", "consumers", "sockets", "peer_uid", "peer_gid",
        "timeout_ms", "lifetime_ms"), "original immutable installation config")
    for key, wanted in {"schema_version": 1, "state_dir": t.AUTHORITY, "signer_id": t.SIGNER,
                        "expected_verifying_key": expected["expected_verifying_key"], "lease_id": "native-cpu-root-installation",
                        "lease_revision": 1, "writer": None, "checkpoint_state_dir": t.AUTHORITY + "/checkpoint",
                        "peer_uid": 60001, "peer_gid": 60001, "timeout_ms": 5000, "lifetime_ms": 120000}.items():
        e.require(type(config[key]) is type(wanted) and config[key] == wanted, "immutable original configuration changed " + key)
    bind = e.obj(config["required_bind"], ("mountpoint", "source_path", "device", "inode"), "original fixed bind identity")
    physical = disk.directory(t.BASE + "/protected-source", 0, 0o700)
    e.require(bind == {"mountpoint": t.PROTECTED, "source_path": t.BASE + "/protected-source",
                       "device": expected["device"], "inode": physical["inode"]},
              "original installation bind does not identify the same actual physical directory")
    expected_sockets = {name: "/run/hepta-native/owner/" + name.replace("_", "-") + ".sock"
                        for name in ("observation", "issuer", "checkpoint", "device_frontier", "notes_frontier")}
    e.require(config["sockets"] == expected_sockets, "original installed authority sockets were redirected")
    e.require(config["consumers"] == {lane: {"state_dir": t.AUTHORITY + "/" + lane + "-consumer", "owner_id": t.SIGNER}
                                     for lane in ("device", "notes")}, "original installed FinalUse authorities were replaced")
    return {"file": disk.public(record), "config": value}


def keyring_digest(public_key, epoch):
    data = b"hepta.kernel.authority.final-use-issuer-trust.v1\0"
    data += struct.pack("<Q", len(t.SIGNER)) + t.SIGNER.encode() + bytes(public_key)
    data += struct.pack("<QQ", epoch, epoch)
    return list(hashlib.sha256(data).digest())


def final_use_frontier(head, nonces):
    t.revocations(head)
    data = b"hepta.kernel.authority.final-use-frontier.v1\0"
    data += struct.pack("<QQQ", head["authority_epoch"], head["revision"], len(head["revoked_grant_ids"]))
    for key in head["revoked_grant_ids"]:
        data += struct.pack("<Q", len(key.encode())) + key.encode()
    data += struct.pack("<Q", len(nonces)) + b"".join(sorted(nonces))
    return {"authority_epoch": head["authority_epoch"], "revocation_revision": head["revision"],
            "state_sha256": list(hashlib.sha256(data).digest())}


def consumers(disk, expected, installation, phase, prior=None):
    result = {}
    parent = disk.directory(t.BASE + "/consumer-local", 60001, 0o700)
    for lane, expected_frontier in zip(("device", "notes"), expected):
        directory = t.BASE + "/consumer-local/" + lane
        actual_dir = disk.directory(directory, 60001, 0o700)
        state_file = disk.read(directory + "/authority.json", 60001, 0o600, 8 * 1024**2)
        claims_file = disk.read(directory + "/authority.claims", 60001, 0o600, 8 * 1024**2, allow_empty=True)
        lock_file = disk.read(directory + "/authority.lock", 60001, 0o600, 0, allow_empty=True)
        state = e.obj(e.json_value(state_file["raw"]), ("schema", "signer_id", "trust", "head"), "original FinalUse schema-v3 state")
        e.require(type(state["schema"]) is int and state["schema"] == 3 and state["signer_id"] == t.SIGNER,
                  "original persistent FinalUse owner was reset or replaced by another schema")
        t.revocations(state["head"])
        e.require(state["trust"] == {"IssuerKeyRing": keyring_digest(installation["expected_verifying_key"], state["head"]["authority_epoch"])},
                  "actual original FinalUse file no longer binds the independently pinned original issuer")
        raw = claims_file["raw"]
        e.require(len(raw) % 40 == 0, "original FinalUse journal contains a partial claim frame")
        nonces = []
        for offset in range(0, len(raw), 40):
            epoch, nonce = struct.unpack_from(">Q", raw, offset)[0], raw[offset + 8:offset + 40]
            e.require(epoch == state["head"]["authority_epoch"] and any(nonce) and nonce not in nonces,
                      "finite original FinalUse journal has a reset epoch, zero or repeated nonce")
            nonces.append(nonce)
        expected_count = (1 if phase == "fresh" else 2) if lane == "device" else 0
        e.require(len(nonces) == expected_count, "old Unknown was reissued, or an original exact-effect claim was lost")
        protected, protected_file = root_record(disk, t.AUTHORITY + "/" + lane + "-consumer", t.SIGNER)
        e.require(final_use_frontier(state["head"], nonces) == expected_frontier == protected,
                  "actual local claim journal, protected frontier and original guest receipt disagree")
        if prior is not None:
            old = prior[lane]
            e.require(state_file["sha256"] == old["state_file"]["sha256"]
                      and actual_dir["inode"] == old["directory"]["inode"]
                      and lock_file["inode"]["inode"] == old["lock_file"]["inode"]["inode"]
                      and raw[:old["claim_bytes"]] == bytes.fromhex(old["claims_hex"]),
                      "cold-open recreated the original FinalUse directory/lock/state or discarded a retained claim")
        result[lane] = {"directory": actual_dir, "state_file": disk.public(state_file),
                        "claims_file": disk.public(claims_file), "lock_file": disk.public(lock_file),
                        "protected_file": protected_file, "frontier": protected, "claim_bytes": len(raw),
                        "claims_hex": raw.hex(), "claim_count": len(nonces)}
    result["parent"] = parent
    return result


def lease_frontier(state):
    e.obj(state, ("authority_epoch", "store_revision", "leases", "revocations", "retired_revisions"),
          "original registry state")
    data = bytearray(b"hepta.kernel.authority.lease-frontier.v2\0")
    def number(value, size=8):
        e.integer(value, "original registry integer", 0, (1 << (size * 8)) - 1)
        data.extend(value.to_bytes(size, "little"))
    def text(value):
        e.text(value, "original registry text", 512)
        number(len(value.encode()))
        data.extend(value.encode())
    for name in ("authority_epoch", "store_revision"):
        e.integer(state[name], "original registry " + name, 1)
        number(state[name])
    for name in ("leases", "revocations", "retired_revisions"):
        e.require(type(state[name]) is dict and len(state[name]) <= 16384, "bounded original registry map required")
    number(len(state["leases"]))
    for key, value in sorted(state["leases"].items()):
        e.obj(value, original.LEASE_KEYS, "actual original stored lease")
        e.require(key == value["lease_id"], "original registry map changed lease identity")
        text(key)
        number(value["schema_version"], 4)
        text(value["lease_id"])
        number(value["authority_epoch"])
        number(value["revision"])
        binding = e.obj(value["binding"], original.BINDING_KEYS, "actual original stored binding")
        for name in ("principal_id", "operation_class", "destination_id"):
            text(binding[name])
        for name in ("scope_sha256", "payload_sha256"):
            data.extend(original.digest_array(binding[name], "original stored lease digest"))
        number(value["issued_at_unix_ms"])
        number(value["expires_at_unix_ms"])
    number(len(state["retired_revisions"]))
    for key, revision in sorted(state["retired_revisions"].items()):
        text(key)
        number(revision)
    number(len(state["revocations"]))
    for key, value in sorted(state["revocations"].items()):
        e.obj(value, ("schema_version", "lease_id", "authority_epoch", "lease_revision", "store_revision",
                      "reason_sha256", "revoked_at_unix_ms"), "actual original stored revocation")
        e.require(key == value["lease_id"], "original revocation map changed lease identity")
        text(key)
        number(value["schema_version"], 4)
        text(value["lease_id"])
        for name in ("authority_epoch", "lease_revision", "store_revision"):
            number(value[name])
        data.extend(original.digest_array(value["reason_sha256"], "original stored revocation reason"))
        number(value["revoked_at_unix_ms"])
    return {"authority_epoch": state["authority_epoch"], "store_revision": state["store_revision"],
            "state_sha256": list(hashlib.sha256(data).digest())}


def registry_selection(state, observed):
    leases = [value for key, value in sorted(state["leases"].items())
              if value["binding"]["principal_id"] == observed["principal_id"] and key not in state["revocations"]
              and value["expires_at_unix_ms"] > observed["observed_unix_ms"]]
    e.require(observed["store_revision"] == state["store_revision"] and observed["leases"] == leases,
              "original complete administrative selection differs from actual retained registry rows")


def root_authority(disk, transcript, prior=None):
    phase = transcript["phase"]
    event = transcript["cut_event"] if phase == "fresh" else transcript["complete_event"]
    current = transcript["cut_current"] if phase == "fresh" else transcript["final_current"]
    authority = event["authority_before_dispatch"] if phase == "fresh" else event["authority"]
    return verify_observed_root(disk, transcript, current, authority, transcript["original_owner"], prior)


def verify_observed_root(disk, transcript, current, authority, owner, prior=None):
    """Bind explicit actual observations without manufacturing an event."""
    phase = transcript["phase"]
    head, head_file = root_record(disk, t.AUTHORITY + "/checkpoint", "root-cognitive-checkpoint-v1")
    e.require(head == current["head"] and sha(b"hepta:root:cognitive-checkpoint-head:v1\0" + e.canonical(head).encode())
              == current["token"]["head_sha256"], "physical original Current is missing, newer, or bound to another complete head")
    clock, clock_file = root_record(disk, t.AUTHORITY, "root-authority-clock-v1")
    e.obj(clock, ("boot_id", "boottime_ns", "unix_ns", "wall_ns", "ceiling_ns"), "actual original durable clock highwater")
    e.require(clock["boot_id"] == transcript["linux_boot_id"], "actual durable clock belongs to another native boot")
    for name in ("boottime_ns", "unix_ns", "wall_ns", "ceiling_ns"):
        e.integer(clock[name], "physical original clock " + name, 1)
    e.require(clock["ceiling_ns"] == clock["unix_ns"] + 1_000_000_000
              and clock["unix_ns"] >= clock["wall_ns"]
              and clock["ceiling_ns"] // 1_000_000 >= authority["clock"]["projection"]["ceiling_unix_ms"],
              "physical original one-second clock frontier regressed or changed its horizon")
    registry_file = disk.read(t.AUTHORITY + "/leases/authority-leases.json", 0, 0o600, 64 * 1024**2)
    registry = e.obj(e.json_value(registry_file["raw"]), ("schema_version", "owner_id", "state"), "original physical lease registry")
    e.require(type(registry["schema_version"]) is int and registry["schema_version"] == 2
              and registry["owner_id"] == "root-authority-leases-v1", "original registry identity/schema changed")
    registry_head, registry_head_file = root_record(disk, t.AUTHORITY, "root-authority-leases-v1")
    e.require(lease_frontier(registry["state"]) == registry_head, "physical original registry differs from its protected anti-rollback frontier")
    issuer, issuer_file = root_record(disk, t.AUTHORITY + "/issuer", "local-final-use-issuer")
    e.obj(issuer, ("signer_id", "policies", "head", "sequence", "writer_authorization"), "actual canonical original issuer state")
    expected_sequence = transcript["cut"]["issuer_sequence_at_cut"] if phase == "fresh" else authority["issuer_sequence"]
    e.require(issuer["signer_id"] == t.SIGNER and issuer["head"] == authority["revocations"]
              and type(issuer["sequence"]) is int and issuer["sequence"] == expected_sequence,
              "physical original issuer key identity, revocations or highwater changed")
    proof = e.obj(issuer["writer_authorization"], ("claims", "signature_hex"), "physical original writer proof")
    claims = e.obj(proof["claims"], original.CLAIM_KEYS, "physical original canonical writer claims")
    writer = {key: claims[key] for key in original.REGISTRATION_KEYS}
    e.require(writer == authority["writer"] and claims["sequence"] <= issuer["sequence"],
              "physical original canonical writer differs from actual source owner")
    root_id = ("native-cpu-root-installation" if phase == "fresh" else
               "native-cpu.root." + transcript["linux_boot_id"] + "." + str(owner["spawn_generation"]))
    e.require(root_id in registry["state"]["leases"], "actual finite Root session was not retained in original registry")
    checked = original.authority(registry["state"]["leases"][root_id], writer, proof, current, t.AGENT)
    e.require(checked["proof_sha256"] == authority["writer_proof_sha256"], "physical original signed writer bytes differ")
    e.require(type(issuer["policies"]) is list and len(issuer["policies"]) == 2, "original fixed two-scope CPU policy required")
    actual_scopes = set()
    for policy in issuer["policies"]:
        e.obj(policy, ("subject_id", "destination_id", "scope_sha256", "lifetime_ms"), "physical original CPU effect policy")
        e.require(policy["subject_id"] == t.AGENT and policy["destination_id"] == "hos2.cpu-budget.v1"
                  and type(policy["lifetime_ms"]) is int and policy["lifetime_ms"] == 5000,
                  "physical original effect policy domain or lifetime changed")
        actual_scopes.add(bytes(original.digest_array(policy["scope_sha256"], "actual native scope")))
    expected_scopes = {hashlib.sha256(b"hepta.hos2.cpu-budget.scope.v1\0" + bytes(transcript["native_boot_id"])
                        + bytes(space) + struct.pack("<QQ", 2, 1)).digest() for space in transcript["spaces"].values()}
    e.require(actual_scopes == expected_scopes, "cold Root did not bind original policy to its actual new kernel namespaces")
    key_inode = disk.regular(t.AUTHORITY + "/issuer/issuer.key", 0, 0o600, 32, 32)
    if prior is not None:
        e.require(key_inode == prior["key_inode"] and clock["unix_ns"] >= prior["clock"]["ceiling_ns"],
                  "original private-key inode or retained clock highwater was reset across actual boots")
        cold = transcript["adoption_event"]["cold_open"]
        registry_selection(prior["registry"], cold["registry_before"])
        e.require(cold["clock"]["projection"]["anchor_unix_ms"] >= prior["clock"]["ceiling_ns"] // 1_000_000,
                  "cold original clock observation did not cover the actual last physical highwater")
        revocations = registry["state"]["revocations"]
        for receipt in cold["revocations_applied"]:
            expected = {"schema_version": 1, **{key: receipt[key] for key in
                ("lease_id", "authority_epoch", "lease_revision", "store_revision", "reason_sha256", "revoked_at_unix_ms")}}
            e.require(revocations.get(receipt["lease_id"]) == expected,
                      "actual original registry did not retain its reported cold revocation")
        registry_selection(registry["state"], authority["registry"])
    else:
        e.require(registry["state"]["store_revision"] >= authority["registry"]["store_revision"],
                  "fault cut lost the original pre-dispatch registry revision")
        for issued in authority["registry"]["leases"]:
            e.require(registry["state"]["leases"].get(issued["lease_id"]) == issued,
                      "fault cut replaced an original pre-dispatch registered lease")
    return {"checkpoint_file": head_file, "clock_file": clock_file, "clock": clock,
            "registry_file": disk.public(registry_file), "registry_frontier_file": registry_head_file,
            "registry": registry["state"], "issuer_file": issuer_file, "issuer_sequence": issuer["sequence"],
            "writer_proof_sha256": checked["proof_sha256"], "key_inode": key_inode,
            "private_key_bytes_read_or_exported": False}
