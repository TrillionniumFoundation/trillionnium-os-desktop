"""Exact original public DTOs for the separate two-boot observation.

These values do not construct a Root, registry, writer, FinalUse token or
checkpoint. The actual source-bound cold factory remains the authority.
"""
import hashlib
import re

import native_owner_evidence as e
import native_owner_continuity_types as original_types
from native_owner_copyout import TOPIC, diagnostic


SCENARIO = "prior-boot-unknown-v1"
AGENT = "018f4f72-5f8f-7cc1-8f55-df9fb3aa2c13"
SIGNER = "native-cpu-original-root"
BASE = "/state/hepta-native"
PROTECTED = BASE + "/protected"
AUTHORITY = PROTECTED + "/authority"
OBSERVATIONS = AUTHORITY + "/native-launch-observations"
PIN_PATH = PROTECTED + "/installation.json"
PIN_KEYS = ("path", "device", "inode", "bytes", "sha256", "expected_verifying_key")
CLOCK_KEYS = ("schema_version", "boot_id", "anchor_boottime_ns", "anchor_unix_ms", "ceiling_unix_ms")
AUTHORITY_KEYS = ("issuer_sequence", "writer_proof_sha256", "writer", "revocations", "registry", "clock")
SELECT_KEYS = ("principal_id", "store_revision", "observed_unix_ms", "leases")
REVOKE_KEYS = ("lease_id", "authority_epoch", "previous_lease_revision", "lease_revision", "store_revision",
               "reason_sha256", "revoked_at_unix_ms")
COLD_KEYS = ("previous", "previous_writer", "writer_proof_sha256", "issuer_sequence", "revocations", "registry_before",
             "revocations_applied", "registry_after", "clock", "device_frontier", "notes_frontier")
CUT_KEYS = ("schema_version", "nonce", "kernel_boot", "current_token", "occurrence_key", "payload_json",
            "material_sha256", "frontiers", "boundary", "installation", "source_database", "authority_before_sha256",
            "issuer_sequence_at_cut")
TRANSPORT_KEYS = ("pid", "database_path", "database_device", "database_inode", "ioctl_counts", "startup_retained")
OPERATION_KEYS = ("operation_id", "subject_id", "destination_id", "payload_digest", "scope_digest",
                  "policy_generation", "expected_predecessor")


def uuid(value):
    raw = bytes(e.byte_id(value, "actual native boot")).hex()
    return "-".join((raw[:8], raw[8:12], raw[12:16], raw[16:20], raw[20:]))


def file_path(value, prefix, name):
    e.text(value, name, 4096)
    e.require(value.startswith(prefix + "/") and re.fullmatch(r"/[A-Za-z0-9_.:/-]+", value)
              and all(part not in ("", ".", "..") for part in value.split("/")[1:]),
              name + " escaped its fixed physical owner directory")
    return value


def pin(value):
    e.obj(value, PIN_KEYS, "original installed public pin")
    e.require(value["path"] == PIN_PATH, "installed original pin path differs")
    e.integer(value["device"], "pin actual device")
    e.integer(value["inode"], "pin actual inode", 1)
    e.integer(value["bytes"], "pin actual bytes", 1, 32768)
    e.digest(value["sha256"], "pin actual bytes")
    original_types.digest_array(value["expected_verifying_key"], "independently installed public key")
    return value


def clock(value, linux_boot):
    e.obj(value, ("projection", "observed_unix_ms"), "original post-I/O clock observation")
    projection = e.obj(value["projection"], CLOCK_KEYS, "original durable clock projection")
    e.integer(projection["schema_version"], "clock schema", 1, 1)
    e.require(projection["boot_id"] == linux_boot, "original clock belongs to another actual boot")
    for key in CLOCK_KEYS[2:]:
        e.integer(projection[key], "original clock " + key, 1)
    observed = e.integer(value["observed_unix_ms"], "actual post-I/O clock time", 1)
    e.require(0 < projection["ceiling_unix_ms"] - projection["anchor_unix_ms"] <= 1000
              and projection["anchor_unix_ms"] <= observed <= projection["ceiling_unix_ms"],
              "original one-second durable ceiling was extended or relabeled as observed time")
    return value


def revocations(value):
    e.obj(value, ("authority_epoch", "revision", "revoked_grant_ids"), "original FinalUse revocation head")
    e.integer(value["authority_epoch"], "original authority epoch", 1)
    e.integer(value["revision"], "original revocation revision", 1)
    ids = value["revoked_grant_ids"]
    e.require(type(ids) is list and len(ids) <= 16384, "bounded original revoked-grant selection required")
    for key in ids:
        e.text(key, "original revoked grant ID", 128)
    e.require(ids == sorted(set(ids)), "original BTreeSet revocations changed ordering or repeated an ID")
    return value


def lease(value, agent):
    e.obj(value, original_types.LEASE_KEYS, "original administrative lease selection")
    e.integer(value["schema_version"], "original lease schema", 1, 1)
    e.integer(value["revision"], "selected original live lease revision", 1, 1)
    e.integer(value["authority_epoch"], "original lease epoch", 1)
    e.text(value["lease_id"], "original selected lease ID", 128)
    for key in ("issued_at_unix_ms", "expires_at_unix_ms"):
        e.integer(value[key], "original lease " + key, 1)
    binding = e.obj(value["binding"], original_types.BINDING_KEYS, "original complete lease binding")
    e.require(binding["principal_id"] == agent, "selected lease belongs to another principal")
    for key in ("scope_sha256", "payload_sha256"):
        original_types.digest_array(binding[key], "original lease " + key)
    lifetime = value["expires_at_unix_ms"] - value["issued_at_unix_ms"]
    if binding["operation_class"] == "runtime.agentd.production_writer":
        e.require(binding["destination_id"] == "cognitive.owner:" + agent and lifetime == 20_000
                  and re.fullmatch(r"native-cpu\.writer\.[0-9a-f-]{36}\.[1-9][0-9]*", value["lease_id"]),
                  "original writer lease escaped its actual finite namespace or duration")
    else:
        e.require(binding["operation_class"] == "runtime.agentd.production_operation"
                  and binding["destination_id"] == "hos2.cpu-budget.v1", "lease escaped the original native CPU domain")
        if value["lease_id"].startswith("hos2-effect."):
            e.digest(value["lease_id"].removeprefix("hos2-effect."), "original exact-effect lease ID")
            e.require(lifetime == 5000, "original exact-effect lease duration changed")
        else:
            e.require(lifetime == 120_000 and (value["lease_id"] == "native-cpu-root-installation"
                      or re.fullmatch(r"native-cpu\.root\.[0-9a-f-]{36}\.[1-9][0-9]*", value["lease_id"])),
                      "original Root session namespace or finite lifetime changed")
    return value


def selection(value, agent):
    e.obj(value, SELECT_KEYS, "original complete unretired registry observation")
    e.require(value["principal_id"] == agent, "original administrative principal differs")
    e.integer(value["store_revision"], "actual registry revision", 1)
    now = e.integer(value["observed_unix_ms"], "actual registry clock sample", 1)
    e.require(type(value["leases"]) is list and len(value["leases"]) <= 16384,
              "original complete bounded administrative lease set required")
    ids = []
    for item in value["leases"]:
        lease(item, agent)
        e.require(item["expires_at_unix_ms"] > now, "expired lease was represented as active work")
        ids.append(item["lease_id"])
    e.require(ids == sorted(set(ids)), "original complete registry selection was reordered or duplicated")
    return value


def registered_writer(value, current, owner, linux_boot, proof_sha256):
    e.obj(value, original_types.REGISTRATION_KEYS, "actual canonical original writer registration")
    binding = current["head"]["writer_binding"]
    e.require(value["registered_agent_id"] == owner["agent_id"]
              and type(value["spawn_generation"]) is int and value["spawn_generation"] == owner["spawn_generation"]
              and value["local_lease_id"] == binding["lease_id"]
              and type(value["local_lease_generation"]) is int and value["local_lease_generation"] == binding["generation"]
              and type(value["owner_epoch"]) is int and value["owner_epoch"] == binding["owner_epoch"],
              "canonical original writer does not bind this exact Supervisor owner and Current")
    issued = original_types.lease(value["authority_lease"], owner["agent_id"], 20_000,
                                  "runtime.agentd.production_writer", "cognitive.owner:" + owner["agent_id"])
    e.require(issued["lease_id"] == "native-cpu.writer." + linux_boot + "." + str(owner["spawn_generation"])
              and issued["authority_epoch"] == binding["authority_epoch"]
              and issued["expires_at_unix_ms"] // 1000 == binding["expires_at_unix_seconds"]
              and proof_sha256 == owner["writer_proof_sha256"] == binding["authority_grant_digest"],
              "original registration/proof changed its boot, actual spawn, lease expiry or Current binding")
    return value


def authority(value, current, owner, linux_boot):
    e.obj(value, AUTHORITY_KEYS, "actual retained original Root authority")
    e.integer(value["issuer_sequence"], "actual canonical issuer highwater", 1)
    proof = e.digest(value["writer_proof_sha256"], "actual retained writer proof")
    registered_writer(value["writer"], current, owner, linux_boot, proof)
    revocations(value["revocations"])
    selected = selection(value["registry"], owner["agent_id"])
    observed = clock(value["clock"], linux_boot)
    e.require(selected["observed_unix_ms"] >= observed["observed_unix_ms"],
              "original registry sample predates the authority method's actual clock observation")
    e.require(value["writer"]["authority_lease"] in selected["leases"],
              "actual active writer is missing from the complete original registry selection")
    return value


def counts(value, installs=None, queries=None):
    e.obj(value, ("install_ioctl_count", "query_ioctl_count"), "actual original FileTransport ioctl counters")
    for key, expected in (("install_ioctl_count", installs), ("query_ioctl_count", queries)):
        actual = e.integer(value[key], "actual " + key)
        if expected is not None:
            e.require(actual == expected, "old observation issued or replayed an original native ioctl")
    return value


def transport(value, pid, device, old=None, installs=None, queries=None):
    e.obj(value, TRANSPORT_KEYS, "actual original writer database/transport observation")
    e.integer(value["pid"], "actual writer PID", pid, pid)
    e.integer(value["database_device"], "actual original database device", device, device)
    e.integer(value["database_inode"], "actual original database inode", 1)
    file_path(value["database_path"], BASE + "/fleet", "actual original writable SQLite path")
    e.require(value["database_path"].endswith(".sqlite3"), "original physical writer is not a SQLite database")
    counts(value["ioctl_counts"], installs, queries)
    expected = [] if old is None else [{"occurrence_key": old["occurrence_key"], "topic": TOPIC,
                                       "payload_json": old["payload_json"], "state": "indeterminate"}]
    e.require(value["startup_retained"] == expected,
              "actual pre-monitor original owner snapshot did not retain the exact old Unknown")
    return value


def saved_cut(raw, nonce):
    e.require(type(raw) is str and 0 < len(raw.encode()) <= 16384, "bounded original Root cut bytes required")
    value = e.obj(e.json_value(raw), CUT_KEYS, "actual original saved cut payload")
    e.integer(value["schema_version"], "saved original cut schema", 1, 1)
    e.require(value["nonce"] == nonce, "saved original cut belongs to another campaign")
    e.byte_id(value["kernel_boot"], "saved actual native boot")
    token = e.obj(value["current_token"], e.TOKEN_KEYS, "saved original Current token")
    e.integer(token["publisher_epoch"], "saved publisher", 1)
    e.integer(token["counter"], "saved publisher counter")
    e.digest(token["head_sha256"], "saved actual Current head")
    e.text(value["occurrence_key"], "saved immutable original K", 512)
    request = e.request(value["payload_json"])
    e.require(request["delivery"]["boot_id"] == value["kernel_boot"], "saved K/D crossed an actual boot")
    e.digest(value["material_sha256"], "saved physical material")
    e.require(type(value["frontiers"]) is list and len(value["frontiers"]) == 2,
              "both original Device/Notes frontiers must be retained")
    for item, name in zip(value["frontiers"], ("device", "notes")):
        e.frontier(item, "saved actual " + name + " frontier")
    boundary = e.obj(value["boundary"], ("phase", "pid", "occurrence_key", "diagnostic",
                                        "observed_boottime_ns", "pending_until_boottime_ns"), "actual source EFAULT boundary")
    e.require(boundary["phase"] == "copyout_fault_boundary" and boundary["occurrence_key"] == value["occurrence_key"],
              "saved cut lacks its one actual original effect-entry boundary")
    e.integer(boundary["pid"], "original faulting PID", 2, (1 << 31) - 1)
    observed = e.integer(boundary["observed_boottime_ns"], "actual guest boundary BOOTTIME", 1)
    until = e.integer(boundary["pending_until_boottime_ns"], "original bounded callback deadline", 1)
    e.require(0 < until - observed <= 2_000_000_000, "original callback was extended or fabricated")
    diagnostic(boundary["diagnostic"], value["payload_json"])
    pin(value["installation"])
    e.digest(value["authority_before_sha256"], "original pre-dispatch authority bytes")
    e.integer(value["issuer_sequence_at_cut"], "actual cut issuer highwater", 1)
    return value


def cut_filename(observation_id):
    e.text(observation_id, "original cut observation ID", 256)
    return "observation-v1-" + hashlib.sha256(observation_id.encode()).hexdigest() + ".json"
