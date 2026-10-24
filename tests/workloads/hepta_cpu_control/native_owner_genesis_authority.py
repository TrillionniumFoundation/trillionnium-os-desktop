"""Read original no-head and first-writer Root records from stopped ext2.

Canonical records, protected frontiers and exact inventories are checked
independently. The private issuer key is identified by inode only; its seed
is never read/exported. The real original owner separately verifies its pin.
"""
import copy
import hashlib
import struct

import native_owner_continuity_types as types
import native_owner_evidence as e
import native_owner_genesis_record as genesis
import native_owner_genesis_first as first_writer
import native_owner_genesis_types as t
import native_owner_prior_boot_authority as original
import native_owner_prior_boot_types as fixed


def observation(disk, directory, identity, expected_payload, observed=None):
    name = fixed.cut_filename(identity)
    lock = disk.read(directory + "/" + name + ".lock", 0, 0o600, 0, allow_empty=True)
    record = disk.read(directory + "/" + name, 0, 0o600, 16384)
    expected = e.canonical({"schema_version": 1, "observation_id": identity,
                            "payload": list(expected_payload.encode())}).encode()
    e.require(record["raw"] == expected, "actual original saved observation bytes differ: " + identity)
    if observed is not None:
        e.require(record["sha256"] == observed["record_sha256"]
                  and record["inode"]["inode"] == observed["inode"]
                  and record["inode"]["bytes"] == observed["record_bytes"],
                  "physical original observation does not match its actual guest-held inode")
    return {"identity": identity, "record": disk.public(record), "lock": disk.public(lock)}


def installation(disk, transcript):
    state = transcript["observed_installation"]
    directory = disk.directory(fixed.PROTECTED, 0, 0o700)
    expected = {".", "..", "authority", "bootstrap.json", "installation.json"}
    for identity in (t.INTENT_ID, t.BOOTSTRAP_ID, t.PIN_ID):
        name = fixed.cut_filename(identity)
        expected.update((name, name + ".lock"))
    for alias in ("bootstrap.json", "installation.json"):
        expected.add("initial-config-" + hashlib.sha256(alias.encode()).hexdigest() + ".lock")
    e.require(set(disk.entries(fixed.PROTECTED)) == expected,
              "original installation directory contains missing, extra or unfinished immutable inputs")
    pin = original.installed_pin(disk, state["installation"], transcript["saved_initial_intent"]["initial_kernel_boot"], fixed.AGENT)
    root_binding = transcript["saved_initial_intent"]["bootstrap"]["required_bind"]
    e.require(root_binding == pin["config"]["config"]["required_bind"] and root_binding["inode"] == directory["inode"],
              "actual physical bind, original intent and installed public pin disagree")
    intent = observation(disk, fixed.PROTECTED, t.INTENT_ID, state["intent"]["payload_json"], state["intent"])
    bootstrap = disk.read(fixed.PROTECTED + "/bootstrap.json", 0, 0o600, 16384)
    e.require(bootstrap["raw"] == e.canonical(transcript["saved_initial_intent"]["bootstrap"]).encode(),
              "actual original bootstrap alias differs from the complete retained initialization input")
    original_pin = disk.read(fixed.PIN_PATH, 0, 0o600, 16384)
    aliases = {}
    for identity, alias, source in ((t.BOOTSTRAP_ID, "bootstrap.json", bootstrap),
                                    (t.PIN_ID, "installation.json", original_pin)):
        record = observation(disk, fixed.PROTECTED, identity, source["raw"].decode())
        lock_name = "initial-config-" + hashlib.sha256(alias.encode()).hexdigest() + ".lock"
        lock = disk.read(fixed.PROTECTED + "/" + lock_name, 0, 0o600, 0, allow_empty=True)
        aliases[alias] = {"source": record, "alias": disk.public(source), "publication_lock": disk.public(lock)}
    return {"directory": directory, "pin": pin, "intent": intent, "aliases": aliases}


def checkpoint(disk, transcript):
    state = transcript["observed_installation"]
    directory = disk.directory(genesis.DIRECTORY, 0, 0o700)
    name = genesis.filename()
    canonical = original.frontier_name("root-cognitive-checkpoint-v1")
    expected = {".", "..", name, name + ".lock", canonical + ".lock"}
    activations = transcript["genesis_activations_expected"]
    names = [value["filename"] for value in activations]
    e.require(len(names) == len(set(names)) and len(names) <= 2, "original first-candidate witness was repeated or omitted")
    expected.update(names)
    expected.update(name + ".lock" for name in names)
    first_proof = None
    if transcript["phase"] == "retained":
        first_proof = transcript["retired_first_proof"] or transcript["original_authority"]["proof"]
    elif transcript["cut_mode"] == "before_head":
        first_proof = transcript["first_writer_proof"]
    if first_proof is not None:
        expected.update((first_writer.filename(), first_writer.filename() + ".lock"))
    if transcript["phase"] == "retained":
        expected.add(canonical)
    e.require(set(disk.entries(genesis.DIRECTORY)) == expected,
              "original checkpoint inventory has an unexpected head, candidate, witness or unfinished publication")
    lock = disk.read(genesis.DIRECTORY + "/" + canonical + ".lock", 0, 0o600, 0, allow_empty=True)
    actual = observation(disk, genesis.DIRECTORY, genesis.identity(), state["genesis"]["payload_json"], state["genesis"])
    raw = disk.read(genesis.DIRECTORY + "/" + name, 0, 0o600, 16384)
    checked = genesis.inspect(raw["raw"], expected_root=transcript["saved_genesis"]["payload"]["initial_root"],
        expected_anchor=state["initial_material"]["cut"], expected_key=state["installation"]["expected_verifying_key"])
    # Namespace scopes have already been checked against the actual first
    # Root page. A lone boot ID cannot infer its two actual capability spaces.
    e.require(checked["payload"] == transcript["saved_genesis"]["payload"], "physical original genesis was reconstructed")
    first_signature = None
    if first_proof is not None:
        record, first_lock = first_writer.read_record(disk, first_writer.filename())
        signature = first_writer.inspect(record["raw"], checked, first_proof)
        e.require(signature["payload"]["activation_id"] in {item["observation_id"] for item in activations},
                  "fixed first signature no longer selects a retained original first-candidate witness")
        first_signature = {**signature, "record": disk.public(record), "lock": disk.public(first_lock)}
    witnesses = []
    for candidate in activations:
        saved = observation(disk, genesis.DIRECTORY, candidate["observation_id"], candidate["durable_payload_json"],
                            candidate["observed_record"])
        witnesses.append({**saved, "payload_sha256": candidate["payload_sha256"], "candidate": candidate["payload"]["candidate"]})
    head_file = None
    if transcript["phase"] == "retained":
        head, head_file = original.root_record(disk, genesis.DIRECTORY, "root-cognitive-checkpoint-v1")
        current = transcript["final_current"]
        e.require(head == current["head"] and original.sha(b"hepta:root:cognitive-checkpoint-head:v1\0" + e.canonical(head).encode())
                  == current["token"]["head_sha256"],
                  "physical original released Current is missing, older, newer or bound to another complete head")
    launches = disk.directory(fixed.OBSERVATIONS, 0, 0o700)
    e.require(set(disk.entries(fixed.OBSERVATIONS)) == {".", ".."},
              "before-first-writer campaign contains an unrelated saved launch/cut observation")
    return {"directory": directory, "genesis": actual, "canonical_lock": disk.public(lock),
            "canonical_file": head_file, "actual_checkpoint_present": transcript["phase"] == "retained",
            "launch_observations_directory": launches, "genesis_payload_sha256": checked["payload_sha256"],
            "genesis_activations": witnesses, "first_signature": first_signature}


def unpublished_retirement(previous, transcript):
    """Reproduce only the actual revision-checked original revocation writes."""
    state = copy.deepcopy(previous["root_authority"]["registry"])
    retirement = transcript["first_owner_event"]["resumed"]["unactivated_writer"]["retirement"]
    original.registry_selection(state, retirement["registry_before"])
    for receipt in retirement["revocations_applied"]:
        identity = receipt["lease_id"]
        e.require(identity in state["leases"] and identity not in state["revocations"]
                  and state["leases"][identity]["revision"] == receipt["previous_lease_revision"]
                  and receipt["store_revision"] == state["store_revision"] + 1,
                  "original unpublished retirement does not follow its actual retained registry preimage")
        state["leases"][identity]["revision"] = receipt["lease_revision"]
        state["revocations"][identity] = {"schema_version": 1, **{key: receipt[key] for key in
            ("lease_id", "authority_epoch", "lease_revision", "store_revision", "reason_sha256", "revoked_at_unix_ms")}}
        state["store_revision"] = receipt["store_revision"]
    observed = transcript["observed_installation"]
    original.registry_selection(state, retirement["registry_after"])
    original.registry_selection(state, observed["registry"])
    e.require(original.lease_frontier(state) == observed["registry_frontier"],
              "actual cold-open registry frontier differs from its complete original unpublished retirement")
    return state


def authority(disk, transcript, previous=None, operation=None):
    state = transcript["observed_installation"]
    clock, clock_file = original.root_record(disk, fixed.AUTHORITY, "root-authority-clock-v1")
    e.obj(clock, ("boot_id", "boottime_ns", "unix_ns", "wall_ns", "ceiling_ns"), "actual original durable clock")
    e.require(clock["boot_id"] == transcript["linux_boot_id"], "physical original clock belongs to another actual boot")
    for name in ("boottime_ns", "unix_ns", "wall_ns", "ceiling_ns"):
        e.integer(clock[name], "actual durable original " + name, 1)
    e.require(clock["ceiling_ns"] == clock["unix_ns"] + 1_000_000_000 and clock["unix_ns"] >= clock["wall_ns"]
              and clock["ceiling_ns"] // 1_000_000 >= state["clock"]["projection"]["ceiling_unix_ms"],
              "actual original clock highwater regressed or changed its one-second publication horizon")
    registry_file = disk.read(fixed.AUTHORITY + "/leases/authority-leases.json", 0, 0o600, 64 * 1024**2)
    wrapper = e.obj(e.json_value(registry_file["raw"]), ("schema_version", "owner_id", "state"), "actual original registry record")
    e.require(type(wrapper["schema_version"]) is int and wrapper["schema_version"] == 2
              and wrapper["owner_id"] == "root-authority-leases-v1", "original registry owner/schema differs")
    registry = wrapper["state"]
    frontier, frontier_file = original.root_record(disk, fixed.AUTHORITY, "root-authority-leases-v1")
    e.require(original.lease_frontier(registry) == frontier, "original complete registry differs from its protected frontier")
    issuer, issuer_file = original.root_record(disk, fixed.AUTHORITY + "/issuer", "local-final-use-issuer")
    pending_first = previous is None and transcript["cut_mode"] == "writer_reserved"
    e.obj(issuer, (*t.ISSUER_KEYS, "writer_reservation") if pending_first else t.ISSUER_KEYS,
          "actual original complete issuer state")
    e.require(issuer["signer_id"] == fixed.SIGNER and issuer["head"] == state["issuer"]["head"],
              "original issuer key identity or revocation head was reset")
    genesis.policies(issuer["policies"], transcript["native_boot_id"], transcript["spaces"])
    key = disk.regular(fixed.AUTHORITY + "/issuer/issuer.key", 0, 0o600, 32, 32)
    initial_id = "native-cpu-root-installation"
    if previous is None:
        expected_ids = {initial_id}
        if transcript["cut_mode"] != "before_writer":
            candidate = transcript["first_candidate"]["writer"]
            expected_ids.add(candidate["authority_lease"]["lease_id"])
            e.require(registry["leases"].get(candidate["authority_lease"]["lease_id"]) == candidate["authority_lease"],
                      "physical original candidate lease differs from its actual reserve/signature boundary")
        e.require(issuer == transcript["actual_cut_issuer"] and frontier == state["registry_frontier"]
                  and set(registry["leases"]) == expected_ids and registry["revocations"] == {}
                  and registry["retired_revisions"] == {}, "stopped before-writer authority is not its actual unused original state")
        old = types.lease(registry["leases"][initial_id], fixed.AGENT, 120000,
                          "runtime.agentd.production_operation", "hos2.cpu-budget.v1")
        e.require(old["binding"] == transcript["saved_initial_intent"]["bootstrap"]["lease_binding"]
                  and old["authority_epoch"] == 1, "physical initial Root lease differs from retained original input")
        original.registry_selection(registry, state["registry"])
    else:
        prior = previous["root_authority"]
        e.require(key == prior["key_inode"] and clock["unix_ns"] >= prior["clock"]["ceiling_ns"]
                  and state["clock"]["projection"]["anchor_unix_ms"] >= prior["clock"]["ceiling_ns"] // 1_000_000,
                  "actual cold-open reset the original key inode or failed to cover the last physical clock ceiling")
        e.require(issuer["writer_authorization"] == transcript["first_owner_event"]["writer_proof"]
                  and type(issuer["sequence"]) is int
                  and issuer["sequence"] == transcript["original_authority"]["proof"]["claims"]["sequence"] + 1
                  and registry["authority_epoch"] == 1 and registry["retired_revisions"] == {},
                  "first original writer/effect changed its signed proof, sequence or registry epoch")
        auth = transcript["original_authority"]
        for issued in (auth["root"], auth["writer"]["authority_lease"]):
            e.require(registry["leases"].get(issued["lease_id"]) == issued,
                      "physical original registry lost its actual new finite Root/writer lease")
        if transcript["cut_mode"] != "before_writer":
            retired = unpublished_retirement(previous, transcript)
            e.require(registry["revocations"] == retired["revocations"]
                      and registry["retired_revisions"] == retired["retired_revisions"]
                      and all(registry["leases"].get(key) == value for key, value in retired["leases"].items()),
                      "actual original registry lost, rewrote or additionally revoked an unpublished predecessor")
            original_ids = set(retired["leases"]) | {auth["root"]["lease_id"], auth["writer"]["authority_lease"]["lease_id"]}
            final_revision = retired["store_revision"] + 3
        else:
            original.registry_selection(prior["registry"], state["registry"])
            old = prior["registry"]["leases"][initial_id]
            actual_old = registry["leases"].get(initial_id)
            revoked = registry["revocations"].get(initial_id)
            if revoked is None:
                e.require(actual_old == old and clock["unix_ns"] // 1_000_000 >= old["expires_at_unix_ms"]
                          and registry["revocations"] == {},
                          "original installation Root lease was neither retained expired nor actually revoked")
            else:
                expected_old = {**old, "revision": 2}
                e.obj(revoked, ("schema_version", "lease_id", "authority_epoch", "lease_revision", "store_revision",
                                "reason_sha256", "revoked_at_unix_ms"), "actual unused original Root retirement")
                reason = types.sha(["native.original.genesis-session.v1", types.lease(old, fixed.AGENT, 120000,
                    "runtime.agentd.production_operation", "hos2.cpu-budget.v1"), auth["root"]["lease_id"],
                    genesis.anchor(state["initial_material"]["cut"])])
                e.require(actual_old == expected_old and set(registry["revocations"]) == {initial_id}
                          and revoked["schema_version"] == 1 and revoked["lease_id"] == initial_id
                          and revoked["authority_epoch"] == 1 and revoked["lease_revision"] == 2
                          and revoked["store_revision"] == 3 and bytes(revoked["reason_sha256"]).hex() == reason,
                          "original Root-session handoff did not retain its exact revision-checked reason/lease")
                e.integer(revoked["revoked_at_unix_ms"], "actual original Root retirement time",
                          state["registry"]["observed_unix_ms"])
            original_ids = {initial_id, auth["root"]["lease_id"], auth["writer"]["authority_lease"]["lease_id"]}
            final_revision = 5 + (revoked is not None)
        effect_ids = set(registry["leases"]) - original_ids
        e.require(len(effect_ids) == 1 and all(name.startswith("hos2-effect.") for name in effect_ids)
                  and registry["store_revision"] == final_revision,
                  "original finite registry contains hidden/duplicate first effect admission")
        e.require(type(operation) is dict, "physical original operation is required for exact-effect lease verification")
        effect = e.ordered(registry["leases"][next(iter(effect_ids))], types.LEASE_KEYS, "actual exact-effect authority lease")
        binding = e.obj(effect["binding"], types.BINDING_KEYS, "actual exact-effect lease binding")
        expected_binding = {"principal_id": fixed.AGENT, "operation_class": "runtime.agentd.production_operation",
                            "destination_id": "hos2.cpu-budget.v1", "scope_sha256": list(bytes.fromhex(operation["scope_sha256"])),
                            "payload_sha256": list(bytes.fromhex(operation["payload_sha256"]))}
        e.require(binding == expected_binding and binding["scope_sha256"] == issuer["policies"][0]["scope_sha256"],
                  "first original effect lease escaped the actual immutable operation or new Manager scope")
        for field in ("schema_version", "authority_epoch", "revision"):
            e.integer(effect[field], "original effect " + field, 1, 1)
        start = e.integer(effect["issued_at_unix_ms"], "actual original effect lease issue", auth["writer"]["authority_lease"]["issued_at_unix_ms"])
        end = e.integer(effect["expires_at_unix_ms"], "actual original effect lease expiry", start + 1,
                        auth["writer"]["authority_lease"]["expires_at_unix_ms"])
        e.require(end - start <= 5000, "original exact-effect lease exceeded the existing policy/writer deadline")
        request = hashlib.sha256()
        for part in (b"hepta:production-outbox-operation:v2", auth["proof_sha256"].encode(), operation["lease_id"].encode(),
                     operation["operation_id"].encode(), fixed.TOPIC.encode(), operation["payload_sha256"].encode(),
                     operation["semantic_sha256"].encode()):
            request.update(struct.pack(">Q", len(part)))
            request.update(part)
        e.require(operation["expected_predecessor_sha256"] is None, "first original effect unexpectedly has a predecessor")
        request.update(b"\0")
        final_binding = {"subject_id": fixed.AGENT, "destination_id": "hos2.cpu-budget.v1",
                         "request_sha256": list(request.digest()), "scope_sha256": binding["scope_sha256"],
                         "payload_sha256": binding["payload_sha256"]}
        e.require(effect["lease_id"] == "hos2-effect." + types.sha(["runtime.hos2.effect-lease.v1", auth["proof_sha256"], final_binding]),
                  "actual registered effect ID is detached from its signed writer and complete original binding")
    return {"clock": clock, "clock_file": clock_file, "registry": registry,
            "registry_file": disk.public(registry_file), "registry_frontier": frontier,
            "registry_frontier_file": frontier_file, "issuer": issuer, "issuer_file": issuer_file,
            "key_inode": key, "private_key_bytes_read_or_exported": False}


def consumers(disk, transcript, previous=None):
    state = transcript["observed_installation"]
    if previous is None:
        parent = disk.directory(fixed.BASE + "/consumer-local", 60001, 0o700)
        e.require(set(disk.entries(fixed.BASE + "/consumer-local")) == {".", ".."},
                  "before-first-Host installation already created local FinalUse state/claims")
        initial = original.final_use_frontier(state["issuer"]["head"], [])
        protected = {}
        for lane in ("device", "notes"):
            value, file = original.root_record(disk, fixed.AUTHORITY + "/" + lane + "-consumer", fixed.SIGNER)
            e.require(value == initial, "before-first-writer protected FinalUse frontier is not its actual initial head")
            protected[lane] = {"frontier": value, "file": file}
        return {"parent": parent, "local_files_present": False, "protected": protected}
    # The original one-effect helper's exact count is one Device claim and
    # zero Notes claims. No old Unknown or prior entered operation exists here.
    result = original.consumers(disk, [transcript["final_frontiers"][lane] for lane in e.FRONTIER_LANES],
                                state["installation"], "fresh")
    e.require(all(result["parent"][key] == previous["consumers"]["parent"][key] for key in ("inode", "uid", "gid", "mode")),
              "cold first Host replaced the original physical consumer-local parent")
    result["local_files_present"] = True
    return result
