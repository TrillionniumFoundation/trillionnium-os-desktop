"""Exact observations of the original installation before its first writer.

No constructor here creates a checkpoint, authority lease or writer. In
particular an absent original checkpoint is never represented as head zero.
"""
import hashlib

import native_owner_continuity_types as types
import native_owner_evidence as e
import native_owner_genesis_record as genesis
import native_owner_prior_boot_types as fixed
import native_owner_successor_wire as wire


SCENARIO = "original-genesis-before-writer-v1"
SCENARIOS = (SCENARIO, "original-genesis-writer-reserved-v1", "original-genesis-before-head-v1")
INTENT_ID = "native.original.initialization.v1"
BOOTSTRAP_ID = "native.original.bootstrap.v1"
PIN_ID = "native.original.installation.pin.v1"
STATE_KEYS = ("root", "kernel_boot", "bootstrap_page", "installation", "intent", "genesis", "initial_material",
              "source_database", "clock", "registry", "registry_frontier", "issuer", "fleet_lifecycle",
              "observed_boottime_ns")
RECORD_KEYS = ("observation_id", "path", "device", "inode", "record_bytes", "record_sha256", "payload_json", "payload_sha256")
INTENT_KEYS = ("schema_version", "initial_root", "initial_kernel_boot", "initial_cut", "bootstrap")
BOOTSTRAP_KEYS = ("schema_version", "required_bind", "signer_id", "policies", "lease_id", "lease_binding", "lease_lifetime_ms")
ISSUER_KEYS = ("signer_id", "policies", "head", "sequence", "writer_authorization")
INITIAL_DATABASE = fixed.BASE + "/fleet/agents/" + fixed.AGENT + "/cognitive/cognitive_1.sqlite3"


def lifecycle(value, generation, state):
    e.obj(value, ("schema_version", "agent_id", "generation", "lifecycle"), "actual original Fleet lifecycle")
    e.require(type(value["schema_version"]) is int and value["schema_version"] == 1
              and value["agent_id"] == fixed.AGENT and type(value["generation"]) is int
              and value["generation"] == generation and value["lifecycle"] == state,
              "original Fleet lifecycle was reset, invented or skipped")
    return value


def root_bootstrap(value, kernel_boot):
    raw = wire.exact_bytes(value, 200, "actual Root initial bootstrap")
    e.require(raw[:8] == b"HOS2BOOT" and tuple(wire.word(raw, offset) for offset in (8, 16, 24)) == (3, 4, 200)
              and raw[32:96] == bytes(64) and list(raw[96:112]) == kernel_boot,
              "initial Root bootstrap changed version, role, boot or acquired a native capability")
    spaces = {"manager": wire.native_space(raw[112:128], kernel_boot, "actual initial Manager namespace"),
              "recovery": wire.native_space(raw[128:144], kernel_boot, "actual initial Recovery namespace")}
    e.require(spaces["manager"] != spaces["recovery"]
              and tuple(wire.word(raw, offset) for offset in (144, 152, 160, 192)) == (2, 3, 4, 1)
              and tuple(wire.word(raw, offset) for offset in (168, 176, 184)) == (e.CAP_NS, e.PERIOD_NS, e.LEASE_NS),
              "actual initial four-Process allocation or original finite CPU bounds changed")
    return spaces


def observed_record(value, observation_id, directory, device):
    e.obj(value, RECORD_KEYS, "actual original stored observation metadata")
    expected_path = directory + "/" + fixed.cut_filename(observation_id)
    e.require(value["observation_id"] == observation_id and value["path"] == expected_path,
              "actual original immutable observation changed its fixed identity or directory")
    e.integer(value["device"], "original observation device", device, device)
    e.integer(value["inode"], "original observation inode", 1)
    e.text(value["payload_json"], "actual saved original payload", 16384)
    payload = value["payload_json"].encode()
    wrapper = e.canonical({"schema_version": 1, "observation_id": observation_id, "payload": list(payload)}).encode()
    e.integer(value["record_bytes"], "original bounded encoded observation", len(wrapper), len(wrapper))
    e.require(len(wrapper) <= 16384
              and e.digest(value["record_sha256"], "original observation bytes") == hashlib.sha256(wrapper).hexdigest()
              and e.digest(value["payload_sha256"], "original payload bytes") == hashlib.sha256(payload).hexdigest(),
              "original observation bytes/hash do not match its complete actual serialized payload")
    return e.json_value(payload), wrapper


def intent(value, expected_pin, saved_genesis):
    value = e.ordered(value, INTENT_KEYS, "original installation intent")
    e.require(type(value["schema_version"]) is int and value["schema_version"] == 1
              and value["initial_root"] == saved_genesis["initial_root"]
              and fixed.uuid(value["initial_kernel_boot"]) == value["initial_root"]["boot_id"]
              and genesis.anchor(value["initial_cut"]) == saved_genesis["initial_cut"],
              "original initialization intent lost its real initial Root, boot or physical cut")
    bootstrap = e.obj(value["bootstrap"], BOOTSTRAP_KEYS, "original initialization bootstrap input")
    e.require(type(bootstrap["schema_version"]) is int and bootstrap["schema_version"] == 1
              and bootstrap["signer_id"] == fixed.SIGNER and bootstrap["lease_id"] == "native-cpu-root-installation"
              and type(bootstrap["lease_lifetime_ms"]) is int and bootstrap["lease_lifetime_ms"] == 120000
              and genesis.policies(bootstrap["policies"]) == saved_genesis["policies"],
              "original immutable bootstrap changed its issuer, policies or finite Root lease")
    bind = e.obj(bootstrap["required_bind"], ("mountpoint", "source_path", "device", "inode"), "original bind input")
    e.require(bind["mountpoint"] == fixed.PROTECTED and bind["source_path"] == fixed.BASE + "/protected-source",
              "original bind input was redirected")
    e.integer(bind["device"], "original physical bind device", expected_pin["device"], expected_pin["device"])
    e.integer(bind["inode"], "original physical bind inode", 1)
    binding = e.obj(bootstrap["lease_binding"], types.BINDING_KEYS, "original initialization Root binding")
    e.require(binding == {"principal_id": fixed.AGENT, "operation_class": "runtime.agentd.production_operation",
              "destination_id": "hos2.cpu-budget.v1", "scope_sha256": saved_genesis["policies"][0]["scope_sha256"],
              "payload_sha256": list(hashlib.sha256(b"native-root-installation-observation-only").digest())},
              "original installation Root lease binding differs from its actual immutable input")
    # bootstrap is an original serde_json::Value. Keep its stored byte order;
    # it is not silently rewritten into a guessed Rust struct serialization.
    return value


def unused_issuer(value, boot, spaces):
    e.obj(value, ISSUER_KEYS, "actual unused original issuer state")
    fixed.revocations(value["head"])
    e.require(value["signer_id"] == fixed.SIGNER and type(value["sequence"]) is int and value["sequence"] == 0
              and value["writer_authorization"] is None
              and value["head"] == {"authority_epoch": 1, "revision": 1, "revoked_grant_ids": []},
              "no-head installation already reserved/signed a writer or changed its initial authority head")
    genesis.policies(value["policies"], boot, spaces)
    return value


def state(value, previous=None, *, mode="before_writer"):
    e.require(mode in ("before_writer", "writer_reserved", "before_head"), "fixed original no-head cut required")
    e.obj(value, STATE_KEYS, "actual original no-checkpoint installation")
    boot = e.byte_id(value["kernel_boot"], "actual no-head kernel boot")
    spaces = root_bootstrap(value["bootstrap_page"], boot)
    root = e.obj(value["root"], e.PEER_KEYS, "actual no-head Root lifetime")
    e.require(type(root["uid"]) is int and root["uid"] == 0 and type(root["pid"]) is int and root["pid"] == 1
              and root["boot_id"] == fixed.uuid(boot), "no-head Root is not its actual initial Process")
    e.integer(root["process_start_ticks"], "actual Root start ticks", 1)
    pin = fixed.pin(value["installation"])
    material = e.obj(value["initial_material"], ("path", "sha256", "device", "inode", "cut"), "actual initial retained material")
    e.integer(material["device"], "initial retained material device", pin["device"], pin["device"])
    e.integer(material["inode"], "initial retained material inode", 1)
    e.digest(material["sha256"], "initial retained physical material bytes")
    genesis_value, wrapper = observed_record(value["genesis"], genesis.identity(), genesis.DIRECTORY, pin["device"])
    expected_root = root if previous is None else previous["root"]
    old_boot = boot if previous is None else previous["kernel_boot"]
    old_spaces = spaces if previous is None else root_bootstrap(previous["bootstrap_page"], old_boot)
    saved = genesis.inspect(wrapper, expected_root=expected_root, expected_anchor=material["cut"],
                            expected_key=pin["expected_verifying_key"], boot=old_boot, spaces=old_spaces)
    e.require(genesis_value == saved["payload"] and material["path"] == saved["material_path"],
              "original genesis or actual retained material path differs from the physical starting cut")
    intent_value, _ = observed_record(value["intent"], INTENT_ID, fixed.PROTECTED, pin["device"])
    intent_value = intent(intent_value, pin, saved["payload"])
    e.require(value["intent"]["payload_json"] == e.canonical(intent_value),
              "original typed installation intent bytes were changed or re-encoded")
    source = e.obj(value["source_database"], ("path", "device", "inode"), "actual unstarted original database")
    e.require(source["path"] == INITIAL_DATABASE, "unstarted original installation selected a recovered or foreign database")
    e.integer(source["device"], "original starting database device", pin["device"], pin["device"])
    e.integer(source["inode"], "original starting database inode", 1)
    e.require(source["inode"] != material["inode"], "initial Root material aliases the writable original database")
    clock = fixed.clock(value["clock"], root["boot_id"])
    registry = fixed.selection(value["registry"], fixed.AGENT)
    e.require(registry["observed_unix_ms"] >= clock["observed_unix_ms"] and len(registry["leases"]) <= 2,
              "before-first-Host original registry contains unrelated authority or regressed its clock")
    if mode == "before_writer":
        e.require(len(registry["leases"]) <= 1
                  and all(item["lease_id"] == "native-cpu-root-installation" for item in registry["leases"]),
                  "unstarted original registry already contains writer/effect admission")
    elif previous is not None:
        e.require(registry["leases"] == [], "original cold-open retained an unretired prior first-candidate lease")
    frontier = e.obj(value["registry_frontier"], ("authority_epoch", "store_revision", "state_sha256"),
                     "actual original registry protected frontier")
    e.integer(frontier["authority_epoch"], "initial registry epoch", 1, 1)
    minimum, maximum = ((2, 2) if mode == "before_writer" else ((3, 3) if previous is None else (3, 5)))
    e.integer(frontier["store_revision"], "original no-head registry revision", minimum, maximum)
    types.digest_array(frontier["state_sha256"], "actual initial registry state")
    e.require(registry["store_revision"] == frontier["store_revision"], "actual registry/frontier revisions differ")
    if mode == "before_writer" or (mode == "writer_reserved" and previous is None):
        unused_issuer(value["issuer"], boot, spaces)
    else:
        from native_owner_genesis_witness import proof
        issuer = e.obj(value["issuer"], ISSUER_KEYS, "actual signed unpublished original issuer")
        fixed.revocations(issuer["head"])
        e.require(issuer["signer_id"] == fixed.SIGNER and type(issuer["sequence"]) is int and issuer["sequence"] == 1
                  and issuer["head"] == {"authority_epoch": 1, "revision": 1, "revoked_grant_ids": []},
                  "signed unpublished original issuer changed its first sequence or initial authority head")
        actual = proof(issuer["writer_authorization"])
        e.require(actual["claims"]["sequence"] == 1, "unpublished original canonical proof is not the initial sequence")
        genesis.policies(issuer["policies"], old_boot, old_spaces)
    lifecycle(value["fleet_lifecycle"], 0 if mode == "before_writer" else 1,
              "stopped" if mode == "before_writer" else "starting")
    e.integer(value["observed_boottime_ns"], "actual no-head final observation time", clock["projection"]["anchor_boottime_ns"])
    if previous is not None:
        e.require(boot != previous["kernel_boot"] and root["boot_id"] != previous["root"]["boot_id"]
                  and all(spaces[lane] not in old_spaces.values() for lane in spaces),
                  "same-disk cold-open reused an old native boot or namespace")
        for key in ("installation", "intent", "genesis", "initial_material", "source_database"):
            e.require(value[key] == previous[key], "same-disk unstarted recovery reconstructed original " + key)
        if mode == "before_writer":
            e.require(value["registry_frontier"] == previous["registry_frontier"],
                      "unused cold-open changed its actual original registry")
        e.require(clock["projection"]["anchor_unix_ms"] >= previous["clock"]["projection"]["ceiling_unix_ms"],
                  "original cold clock regressed its retained previous-boot highwater")
    return {"state": value, "spaces": spaces, "intent": intent_value, "genesis": saved}
