"""Strict evidence for the original native owner; no owner or effect lives here.

The producer is the reviewed original Root/Host entry. Root serializes actual
owner responses after they return. The parser rejects legacy read-only probes,
unknown schemas, rewritten K/D payloads and current-cap substitutions for old D.
The four earlier scenarios keep their finite scopes. Continuity requires its
separate retained-file gate; no scenario qualifies unbounded control or power loss.
"""
import hashlib
import json
import re


PREFIX = "HEPTA_G2_EVIDENCE_V1 "
SCENARIOS = ("steady-state-v1", "manager-exit-after-terminal-v1")
COPYOUT_SCENARIOS = ("lost-copyout-live-v1", "manager-exit-before-terminal-v1")
CONTINUITY_SCENARIOS = ("successor-renewal-v1", "history-only-after-both-owner-exit-v1")
SUPPORTED_SCENARIOS = SCENARIOS + COPYOUT_SCENARIOS + CONTINUITY_SCENARIOS
PERIOD_NS = 100_000_000
CAP_NS = 50_000_000
LEASE_NS = 300_000_000_000
MAX_SERIAL_BYTES = 8 * 1024 * 1024
MAX_EVENT_BYTES = 128 * 1024
MAX_EVENTS = 128
ROLE_IDS = {"root": 4, "manager": 1, "workload": 2, "recovery": 3}
CAPABILITIES = ("inheritable", "permitted", "effective", "bounding", "ambient")
IMAGE = re.compile(r"^\[hepta-g2\] trusted initial image committed: bytes=([0-9]+) entry=0x([0-9a-f]+)$")
ACTIVATION = re.compile(
    r"^\[hepta-g2\] initial roles activated: root=([0-9]+) manager=([0-9]+) workload=([0-9]+) recovery=([0-9]+) "
    r"workload_uid=60002 bootstrap_version=3 bytes=200 hepta_durability=false$")
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
REQUEST_KEYS = ("schema_version", "delivery", "manage_slot", "manage_generation", "expected_revision", "period_ns", "cap_ns")
DELIVERY_KEYS = ("boot_id", "space_id", "sequence")
APPLIED_KEYS = ("state", "stable_object_id", "previous_revision", "revision", "effective_ns", "consumed_ns")
USAGE_KEYS = ("boot_id", "observer_space_id", "revision", "sample_boottime_ns", "cumulative_cpu_ns", "window_start_ns",
              "window_consumed_ns", "active_cap_ns", "active_period_ns", "event_sequence", "dropped_events", "heartbeat")
WRITER_KEYS = ("lease_id", "generation", "authority_epoch", "owner_epoch", "authority_grant_digest", "fencing_token_digest",
               "expires_at_unix_seconds")
PEER_KEYS = ("uid", "pid", "boot_id", "process_start_ticks")
CUT_KEYS = ("profile", "owner_agent_id", "schema_digest", "state_digest")
TOKEN_KEYS = ("publisher_epoch", "counter", "head_sha256")
HEAD_KEYS = ("schema_version", "owner_agent_id", "publisher_epoch", "counter", "last_mutation_sequence", "writer_binding",
             "peer_lifetime", "phase", "last_current", "proposal", "last_request")
FRONTIER_KEYS = ("authority_epoch", "revocation_revision", "state_sha256")
FRONTIER_LANES = ("device_frontier", "notes_frontier")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def json_value(raw):
    def invalid(value):
        raise ValueError("non-finite JSON value: " + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def obj(value, keys, name):
    require(type(value) is dict and set(value) == set(keys), name + " fields differ from the fixed schema")
    return value


def integer(value, name, minimum=0, maximum=(1 << 64) - 1):
    require(type(value) is int and minimum <= value <= maximum, name + " is not an exact bounded integer")
    return value


def text(value, name, maximum=256):
    require(type(value) is str and 0 < len(value.encode("utf-8")) <= maximum
            and all(32 <= ord(character) < 127 for character in value), name + " is not bounded printable ASCII")
    return value


def digest(value, name):
    require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None, name + " is not SHA-256")
    return value


def byte_id(value, name):
    require(type(value) is list and len(value) == 16
            and all(type(item) is int and 0 <= item <= 255 for item in value)
            and any(value), name + " is not a nonzero original 16-byte identity")
    return value


def frontier(value, name):
    """The original FinalUseFrontier DTO, not an invented sequence or token."""
    value = obj(value, FRONTIER_KEYS, name)
    integer(value["authority_epoch"], name + " authority epoch", 1)
    integer(value["revocation_revision"], name + " revocation revision", 1)
    state = value["state_sha256"]
    require(type(state) is list and len(state) == 32
            and all(type(item) is int and 0 <= item <= 255 for item in state)
            and any(state), name + " state digest is not the original 32-byte array")
    return value


def canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def ordered(value, keys, name):
    obj(value, keys, name)
    return {key: value[key] for key in keys}


def delivery(value):
    value = ordered(value, DELIVERY_KEYS, "delivery")
    byte_id(value["boot_id"], "native boot")
    byte_id(value["space_id"], "native namespace")
    sequence = value["sequence"]
    require(type(sequence) is str and re.fullmatch(r"[0-9a-f]{16}", sequence) is not None
            and 0 < int(sequence, 16) < (1 << 64) - 1, "D sequence must preserve the original hexadecimal u64")
    return value


def request(raw):
    text(raw, "canonical original request", 32768)
    value = ordered(json_value(raw), REQUEST_KEYS, "original request")
    require(value["schema_version"] == 1 and type(value["schema_version"]) is int, "request version differs")
    value["delivery"] = delivery(value["delivery"])
    for key in ("manage_slot", "manage_generation", "expected_revision"):
        integer(value[key], key, 1, (1 << 64) - 2)
    require(type(value["period_ns"]) is int and value["period_ns"] == PERIOD_NS, "original period differs")
    integer(value["cap_ns"], "requested cap", 0, CAP_NS)
    require(canonical(value) == raw, "original request canonical bytes changed")
    return value


def observation(value, expected_request):
    require(type(value) is dict, "native terminal observation missing")
    if value.get("state") == "applied":
        value = ordered(value, APPLIED_KEYS, "Applied observation")
        byte_id(value["stable_object_id"], "stable CPU object")
        for key in APPLIED_KEYS[2:]:
            integer(value[key], "native " + key)
        require(value["previous_revision"] == expected_request["expected_revision"]
                and value["revision"] == value["previous_revision"] + 1
                and value["consumed_ns"] <= value["effective_ns"] % PERIOD_NS,
                "native Applied receipt does not bind the exact request or accounting cut")
    else:
        value = ordered(value, ("state", "status"), "NotApplied observation")
        require(value["state"] == "not_applied", "nonterminal native history cannot become a source terminal")
        integer(value["status"], "NotApplied status", 1, 7)
    return value


def terminal(raw, expected_request):
    text(raw, "canonical original terminal", 32768)
    value = ordered(json_value(raw), ("schema_version", "request", "observation"), "original terminal receipt")
    require(type(value["schema_version"]) is int and value["schema_version"] == 1, "terminal version differs")
    require(value["request"] == expected_request, "source terminal is bound to another immutable request")
    value["request"] = expected_request
    value["observation"] = observation(value["observation"], expected_request)
    require(canonical(value) == raw, "original terminal canonical bytes changed")
    return value["observation"]


def usage(value, boot_id, space_id):
    value = obj(value, USAGE_KEYS, "original native usage plus actual workload heartbeat")
    require(byte_id(value["boot_id"], "usage boot") == boot_id
            and byte_id(value["observer_space_id"], "usage namespace") == space_id,
            "usage belongs to another native boot or observing image")
    for key in USAGE_KEYS[2:]:
        integer(value[key], "usage " + key)
    now, total = value["sample_boottime_ns"], value["cumulative_cpu_ns"]
    start, consumed = value["window_start_ns"], value["window_consumed_ns"]
    require(value["revision"] > 0 and value["active_period_ns"] == PERIOD_NS
            and value["active_cap_ns"] <= CAP_NS and value["dropped_events"] == 0
            and start == now // PERIOD_NS * PERIOD_NS and consumed <= total <= now
            and consumed <= now % PERIOD_NS and total - consumed <= start,
            "native CPU sample accounting is invalid or incomplete")
    return value


def progression(before, after):
    require(after["sample_boottime_ns"] >= before["sample_boottime_ns"]
            and after["cumulative_cpu_ns"] >= before["cumulative_cpu_ns"]
            and after["event_sequence"] >= before["event_sequence"], "native usage regressed")
    if after["window_start_ns"] == before["window_start_ns"]:
        require(after["window_consumed_ns"] >= before["window_consumed_ns"], "current-window usage was reset")


def checkpoint(value, expected_peer, agent_id):
    """Check original public receipt fields without manufacturing a Root token.

    The opaque token digest is not re-signed or treated as an authority grant.
    Actual Root authentication and source provenance remain independent gates.
    """
    obj(value, ("token", "head"), "original Current receipt")
    token = obj(value["token"], TOKEN_KEYS, "checkpoint token")
    head = obj(value["head"], HEAD_KEYS, "checkpoint head")
    for key in ("publisher_epoch", "counter"):
        integer(token[key], "token " + key, 1 if key == "publisher_epoch" else 0)
        require(type(head[key]) is int and token[key] == head[key], "checkpoint token/head differ")
    digest(token["head_sha256"], "opaque original head token")
    require(type(head["schema_version"]) is int and head["schema_version"] == 1
            and head["owner_agent_id"] == agent_id and head["phase"] == "current" and head["proposal"] is None,
            "only the independent original Current cut can admit a source owner")
    integer(head["last_mutation_sequence"], "checkpoint mutation sequence")
    peer = obj(head["peer_lifetime"], PEER_KEYS, "checkpoint actual peer")
    require(peer == expected_peer, "checkpoint binds another real publisher process")
    writer = obj(head["writer_binding"], WRITER_KEYS, "checkpoint original writer")
    text(writer["lease_id"], "local original lease ID")
    for key in ("generation", "authority_epoch", "owner_epoch", "expires_at_unix_seconds"):
        integer(writer[key], "writer " + key, 1)
    for key in ("authority_grant_digest", "fencing_token_digest"):
        digest(writer[key], "writer " + key)
    cut = obj(head["last_current"], CUT_KEYS, "exact original owner cut")
    require(cut["profile"] == "hepta:cognitive:exact-current-cut:v1" and cut["owner_agent_id"] == agent_id,
            "checkpoint changed the original owner or recovery profile")
    for key in ("schema_digest", "state_digest"):
        digest(cut[key], "original " + key)
    last = head["last_request"]
    if last is not None:
        obj(last, ("request_id", "request_sha256", "command", "predecessor_token"), "last checkpoint request")
        require(type(last["request_id"]) is str and re.fullmatch(r"[0-9a-f]{32}", last["request_id"]),
                "original checkpoint request ID is malformed")
        digest(last["request_sha256"], "checkpoint request")
        require(last["command"] in ("begin_writes", "prepare_publication", "commit_publication", "fence_publisher"),
                "checkpoint last mutation command is unknown")
        predecessor = obj(last["predecessor_token"], TOKEN_KEYS, "predecessor token")
        integer(predecessor["publisher_epoch"], "predecessor publisher", 1)
        integer(predecessor["counter"], "predecessor counter")
        digest(predecessor["head_sha256"], "predecessor head")
    return value


def parse(raw, scenario, nonce):
    return _parse(raw, scenario, nonce, False)


def _parse(raw, scenario, nonce, prior_boot):
    require(type(raw) is bytes and len(raw) <= MAX_SERIAL_BYTES, "serial evidence exceeds the original bound")
    require(scenario in SUPPORTED_SCENARIOS or (prior_boot and scenario == "prior-boot-unknown-v1"),
            "unsupported original-owner scenario")
    digest(nonce, "fresh host nonce")
    decoded = raw.decode("utf-8", errors="strict").replace("\r\n", "\n")
    require(not any(marker in decoded.lower() for marker in ("kernel panic", "panicked at", "fatal exception", "g2_fail")),
            "guest reported a failure")
    lines = ANSI.sub("", decoded).splitlines()
    events = []
    for line_number, line in enumerate(lines):
        if line.startswith("HEPTA_G2_"):
            require(line.startswith(PREFIX) and len(line.encode("utf-8")) <= MAX_EVENT_BYTES,
                    "unknown or excessive G2 event envelope")
            value = obj(json_value(line[len(PREFIX):]),
                        ("schema_version", "scenario", "nonce", "event", "sequence", "payload"), "G2 event")
            require(type(value["schema_version"]) is int and value["schema_version"] == 1
                    and value["scenario"] == scenario and value["nonce"] == nonce,
                    "G2 event version, scenario or fresh nonce differs")
            require(type(value["sequence"]) is int and value["sequence"] == len(events) + 1,
                    "G2 events are missing, repeated or reordered")
            text(value["event"], "event name", 64)
            require(type(value["payload"]) is dict, "G2 payload must be an object")
            events.append((line_number, value))
        elif line.startswith(("G1D_", "G1C_", "[hepta-g1d]", "[hepta-g1c]")):
            raise ValueError("legacy role or read-only qualification cannot substitute for an original G2 owner")
    event_limit = 1024 if scenario == "successor-renewal-v1" else MAX_EVENTS
    require(1 <= len(events) <= event_limit, "bounded original-owner event stream required")
    return lines, events


def cpu_stat(raw):
    text(raw.replace("\n", " "), "original cpu.stat observation", 32768)
    values = {}
    for line in raw.splitlines():
        fields = line.split()
        require(len(fields) == 2 and fields[0] not in values and re.fullmatch(r"[0-9]+", fields[1]) is not None,
                "cpu.stat must contain unrepeated original integer observations")
        values[fields[0]] = integer(int(fields[1]), fields[0])
    required = ("hepta_watchdog_armed", "hepta_watchdog_ticks", "hepta_watchdog_due_ns", "hepta_watchdog_expires_ns",
                "hepta_watchdog_status", "hepta_watchdog_evaluated_ns", "hepta_job_stop_available", "hepta_job_stopped",
                "hepta_user_pause_intent_available", "hepta_watchdog_stable_id_low", "hepta_watchdog_stable_id_high",
                "hepta_watchdog_previous_revision", "hepta_watchdog_revision", "hepta_watchdog_effective_ns",
                "hepta_watchdog_consumed_ns")
    require(all(key in values for key in required), "original immutable watchdog receipt is incomplete")
    require(values["hepta_watchdog_armed"] == values["hepta_watchdog_status"] == values["hepta_job_stop_available"] == 1
            and values["hepta_job_stopped"] == values["hepta_user_pause_intent_available"] == 0
            and values["hepta_watchdog_ticks"] > 0, "watchdog did not perform its independent eligible restoration")
    due, expiry, evaluated = (values["hepta_watchdog_" + key] for key in ("due_ns", "expires_ns", "evaluated_ns"))
    require(due >= 5_000_000_000 and expiry == due + 25_000_000_000 and due <= evaluated < expiry
            and values["hepta_watchdog_effective_ns"] == evaluated
            and values["hepta_watchdog_previous_revision"] + 1 == values["hepta_watchdog_revision"]
            and values["hepta_watchdog_consumed_ns"] <= values["hepta_watchdog_effective_ns"] % PERIOD_NS,
            "the original 5s watchdog or immutable accounting receipt differs")
    return values


def evaluate(raw, code, timed_out, excessive, scenario, nonce, elf_info):
    """Raise on any missing boundary; success has only the named finite scope."""
    return _evaluate_boot(raw, code, timed_out, excessive, scenario, nonce, elf_info, None)


def _evaluate_boot(raw, code, timed_out, excessive, scenario, nonce, elf_info, prior_boot):
    expected_exit = 33
    if prior_boot is not None:
        from native_owner_prior_boot_evidence import PriorBootTranscript
        require(type(prior_boot) is PriorBootTranscript and scenario == "prior-boot-unknown-v1",
                "only the separate actual two-boot oracle can consume this transcript")
        expected_exit = -9 if prior_boot.phase == "fresh" else 33
    require(type(code) is int and code == expected_exit and timed_out is False and excessive is False,
            "QEMU must finish the bounded actual boot with the original success exit")
    lines, events = _parse(raw, scenario, nonce, prior_boot is not None)
    successor_markers = []
    if scenario in CONTINUITY_SCENARIOS:
        from native_owner_continuity_kernel import kernel_records
        initial, successor_markers = kernel_records(lines, events, elf_info)
        activated = [initial]
    else:
        images = [(index, IMAGE.fullmatch(line)) for index, line in enumerate(lines) if IMAGE.fullmatch(line)]
        activated = [(index, ACTIVATION.fullmatch(line)) for index, line in enumerate(lines) if ACTIVATION.fullmatch(line)]
        require(len(images) == 4 and len(activated) == 1
                and all(int(match[1]) == elf_info["bytes"] and int(match[2], 16) == elf_info["entry"] for _, match in images)
                and max(index for index, _ in images) < activated[0][0] < events[0][0],
                "all four original immutable images must commit before any actual role resumes")
        require(not any(line.startswith("[hepta-g2]") and not IMAGE.fullmatch(line) and not ACTIVATION.fullmatch(line)
                        for line in lines), "unknown kernel G2 record or loader rejection")
    role_pids = dict(zip(ROLE_IDS, map(int, activated[0][1].groups())))
    require(role_pids["root"] == 1 and len(set(role_pids.values())) == 4
            and all(0 < pid < 1 << 31 for pid in role_pids.values()), "four distinct actual role Processes required")
    values = [value for _, value in events]
    cursor = 0

    def take(name):
        nonlocal cursor
        require(cursor < len(values) and values[cursor]["event"] == name,
                "missing or reordered original event: " + name)
        value = values[cursor]["payload"]
        cursor += 1
        return value

    if prior_boot is not None:
        prior_boot.begin(take)

    roles = obj(take("roles"), ("bootstrap_version", "bootstrap_bytes", "native_boot_id", "manager_space", "recovery_space",
                                "linux_boot_id", "processes"), "roles")
    require(type(roles["bootstrap_version"]) is int and roles["bootstrap_version"] == 3
            and type(roles["bootstrap_bytes"]) is int and roles["bootstrap_bytes"] == 200,
            "the original four-role bootstrap v3 is required")
    boot_id = byte_id(roles["native_boot_id"], "native boot ID")
    spaces = {name: byte_id(roles[name + "_space"], name + " namespace") for name in ("manager", "recovery")}
    require(spaces["manager"] != spaces["recovery"], "manager and recovery namespaces alias")
    linux_boot = roles["linux_boot_id"]
    require(type(linux_boot) is str and re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", linux_boot),
            "actual Linux boot UUID required")
    processes = obj(roles["processes"], ROLE_IDS, "actual process identities")
    peers = {}
    for role, role_id in ROLE_IDS.items():
        process = obj(processes[role], ("role", "pid", "ppid", "start_ticks", "uids", "gids", "groups", "caps", "nnp", "sid"), role)
        require(type(process["role"]) is int and process["role"] == role_id
                and type(process["pid"]) is int and process["pid"] == role_pids[role]
                and type(process["ppid"]) is int and process["ppid"] == (0 if role == "root" else role_pids["root"]),
                "real role parentage differs: " + role)
        integer(process["start_ticks"], role + " actual start ticks", 1)
        uid = 0 if role == "root" else (60002 if role == "workload" else 60001)
        for key in ("uids", "gids"):
            require(type(process[key]) is list and len(process[key]) == 4
                    and all(type(item) is int and item == uid for item in process[key]), "actual " + role + " credentials differ")
        obj(process["caps"], CAPABILITIES, role + " five capabilities")
        for name in CAPABILITIES:
            integer(process["caps"][name], name)
        integer(process["nnp"], "NNP", 0, 1)
        integer(process["sid"], "actual session ID", 1, (1 << 31) - 1)
        require(type(process["groups"]) is list and all(type(item) is int and 0 <= item <= (1 << 32) - 1 for item in process["groups"]),
                "actual supplemental groups malformed")
        if role != "root":
            require(process["groups"] == [] and all(value == 0 for value in process["caps"].values()) and process["nnp"] == 1,
                    "original Host/workload privilege boundary not established")
        if role == "workload":
            require(process["sid"] == process["pid"], "workload must retain its independent actual session")
        peers[role] = {"uid": uid, "pid": process["pid"], "boot_id": linux_boot, "process_start_ticks": process["start_ticks"]}

    state = obj(take("state"), ("source", "target", "filesystem", "mount_device", "store_device", "store_inode",
                               "root_material_device", "root_material_inode"), "persistent state")
    require(state["source"] == "/dev/vda" and state["target"] == "/state" and state["filesystem"] == "ext2",
            "actual original writer must use the attached retained ext2 state")
    for key in ("mount_device", "store_device", "store_inode", "root_material_device", "root_material_inode"):
        integer(state[key], key, 1 if key.endswith("inode") else 0)
    require(state["mount_device"] == state["store_device"] == state["root_material_device"]
            and state["store_inode"] != state["root_material_inode"], "original store and independent material must use distinct retained objects")

    boundary = obj(take("boundary"), ("workload_signal_checks", "workload_host_path_checks", "workload_device_open_errno",
                                     "root_manage_status", "root_history_status"), "actual isolation observations")
    signals = boundary["workload_signal_checks"]
    require(type(signals) is list and len(signals) == 6, "workload must check all three privileged role signals")
    expected_signals = [(role_pids[role], signum) for role in ("root", "manager", "recovery") for signum in (0, 9)]
    for check, expected in zip(signals, expected_signals):
        obj(check, ("pid", "signal", "rc", "errno"), "actual signal denial")
        require(tuple(check[key] for key in ("pid", "signal", "rc", "errno")) == (*expected, -1, 1)
                and all(type(item) is int for item in check.values()), "workload can signal a privileged original owner")
    paths = boundary["workload_host_path_checks"]
    require(type(paths) is list and len(paths) == 2, "both private Host and Root material access must be refused")
    for check, kind in zip(paths, ("host-store", "root-material")):
        obj(check, ("kind", "rc", "errno"), "private path denial")
        require(check["kind"] == kind and type(check["rc"]) is int and check["rc"] == -1
                and type(check["errno"]) is int and check["errno"] == 13, "workload can access privileged owner state")
    require(type(boundary["workload_device_open_errno"]) is int and boundary["workload_device_open_errno"] == 13
            and type(boundary["root_manage_status"]) is int and boundary["root_manage_status"] == 2
            and type(boundary["root_history_status"]) is int and boundary["root_history_status"] == 2,
            "Root or workload acquired a native management/history authority")

    owners, currents, materials, frontiers, operations = {}, {}, {}, {}, {}
    adopted = None
    last_usage = None
    native_sequence = {"manager": 0, "recovery": 0}
    stable_cpu = None

    def owner_ready(role):
        payload = obj(take("owner_ready"), ("role", "pid", "agent_id", "spawn_generation", "issuer_key_sha256",
                                           "writer_proof_sha256", "current", "material_sha256", "device_frontier",
                                           "notes_frontier", "owner_lock_device", "owner_lock_inode"), "original owner readiness")
        require(payload["role"] == role and type(payload["pid"]) is int and payload["pid"] == role_pids[role],
                "original owner was not opened in its final native role Process")
        text(payload["agent_id"], "registered original agent")
        integer(payload["spawn_generation"], "real Supervisor spawn generation", 1)
        for key in ("issuer_key_sha256", "writer_proof_sha256", "material_sha256"):
            digest(payload[key], key)
        actual_frontiers = {key: frontier(payload[key], key) for key in FRONTIER_LANES}
        require(type(payload["owner_lock_device"]) is int and payload["owner_lock_device"] == state["store_device"],
                "single original writer lock must remain on the retained state filesystem")
        integer(payload["owner_lock_inode"], "original writer lock inode", 1)
        current = checkpoint(payload["current"], peers[role], payload["agent_id"])
        if role == "recovery":
            prior, old = owners["manager"], currents["manager"]["head"]
            new = current["head"]
            require(payload["agent_id"] == prior["agent_id"] and payload["spawn_generation"] > prior["spawn_generation"]
                    and payload["issuer_key_sha256"] == prior["issuer_key_sha256"]
                    and payload["writer_proof_sha256"] != prior["writer_proof_sha256"]
                    and payload["owner_lock_inode"] == prior["owner_lock_inode"]
                    and actual_frontiers == frontiers["manager"],
                    "successor reset the original identity, Supervisor generation, writer lock or FinalUse frontiers")
            old_writer, new_writer = old["writer_binding"], new["writer_binding"]
            require(adopted is not None and new["publisher_epoch"] == adopted["head"]["publisher_epoch"]
                    and new["counter"] >= adopted["head"]["counter"]
                    and new["writer_binding"] == adopted["head"]["writer_binding"]
                    and new["last_current"]["schema_digest"] == old["last_current"]["schema_digest"]
                    and new_writer["lease_id"] == old_writer["lease_id"]
                    and new_writer["generation"] == old_writer["generation"] + 1
                    and (new_writer["authority_epoch"], new_writer["owner_epoch"]) > (old_writer["authority_epoch"], old_writer["owner_epoch"])
                    and all(new_writer[key] != old_writer[key] for key in ("authority_grant_digest", "fencing_token_digest")),
                    "successor did not perform the original canonical Current/writer handoff")
        owners[role], currents[role], materials[role] = payload, current, payload["material_sha256"]
        frontiers[role] = actual_frontiers
        return payload

    owner_ready("manager")

    def prepared(name, role, cap):
        value = obj(take("prepared"), ("operation", "pid", "occurrence_key", "request_json", "payload_sha256"), "original immutable outbox")
        require(value["operation"] == name and value["pid"] == role_pids[role] and type(value["pid"]) is int,
                "operation was prepared by another owner")
        text(value["occurrence_key"], "original occurrence key K", 1024)
        require(all(value["occurrence_key"] != item["key"] for item in operations.values()), "one original K was rebound")
        req = request(value["request_json"])
        require(digest(value["payload_sha256"], "outbox payload") == hashlib.sha256(value["request_json"].encode()).hexdigest(),
                "original immutable K-to-D payload bytes differ")
        require(req["delivery"]["boot_id"] == boot_id and req["delivery"]["space_id"] == spaces[role]
                and int(req["delivery"]["sequence"], 16) == native_sequence[role] + 1 and req["cap_ns"] == cap,
                "operation changed namespace, delivery sequence or reviewed budget")
        native_sequence[role] += 1
        operations[name] = {"role": role, "key": value["occurrence_key"], "request": req,
                            "request_json": value["request_json"], "payload_sha256": value["payload_sha256"]}
        return operations[name]

    def native_result(name, expected_state):
        nonlocal last_usage, stable_cpu
        op = operations[name]
        role = op["role"]
        value = obj(take("native_result"), ("operation", "pid", "terminal_json", "before", "after"), "actual original native result")
        require(value["operation"] == name and type(value["pid"]) is int and value["pid"] == role_pids[role], "native owner differs")
        observed = terminal(value["terminal_json"], op["request"])
        require(observed["state"] == expected_state, "actual native terminal differs from the scenario")
        before = usage(value["before"], boot_id, spaces[role])
        after = usage(value["after"], boot_id, spaces[role])
        progression(before, after)
        if last_usage is not None:
            progression(last_usage, before)
        if expected_state == "applied":
            require(before["revision"] == observed["previous_revision"] and after["revision"] == observed["revision"]
                    and after["active_cap_ns"] == op["request"]["cap_ns"]
                    and before["sample_boottime_ns"] <= observed["effective_ns"] <= after["sample_boottime_ns"],
                    "actual CPU revision/cap does not bracket the original terminal")
            if stable_cpu is not None:
                require(observed["stable_object_id"] == stable_cpu, "delivery changed the controlled CPU owner")
            stable_cpu = observed["stable_object_id"]
            for sample, comparison in ((before, "before"), (after, "after")):
                if sample["window_start_ns"] == observed["effective_ns"] // PERIOD_NS * PERIOD_NS:
                    require((sample["window_consumed_ns"] <= observed["consumed_ns"] if comparison == "before"
                             else sample["window_consumed_ns"] >= observed["consumed_ns"]), "apply reset the original accounting window")
        else:
            require(observed["status"] == 2 and before["revision"] == after["revision"]
                    and op["request"]["expected_revision"] == before["revision"]
                    and before["active_cap_ns"] == after["active_cap_ns"] == CAP_NS,
                    "used recovery allowance must refuse without another native effect")
        op.update(terminal=value["terminal_json"], observation=observed)
        last_usage = after

    def source_terminal(name, role):
        op = operations[name]
        value = obj(take("source_terminal"), ("operation", "pid", "occurrence_key", "state", "terminal_json", "local_event_id",
                                             "current", "material_sha256", "device_frontier", "notes_frontier"),
                    "durable original source terminal")
        require(value["operation"] == name and type(value["pid"]) is int and value["pid"] == role_pids[role]
                and value["occurrence_key"] == op["key"] and value["terminal_json"] == op["terminal"],
                "source terminal did not retain the exact original K/D observation")
        require(value["state"] == ("committed" if op["observation"]["state"] == "applied" else "rejected"),
                "original source state is not the native terminal")
        actual_frontiers = {key: frontier(value[key], key) for key in FRONTIER_LANES}
        for lane in FRONTIER_LANES:
            prior_frontier = frontiers[role][lane]
            require(all(actual_frontiers[lane][key] == prior_frontier[key]
                        for key in ("authority_epoch", "revocation_revision")),
                    "finite owner scenario unexpectedly changed the original FinalUse revocation head")
        if op["role"] == role and "source_event" not in op:
            require(actual_frontiers["device_frontier"] != frontiers[role]["device_frontier"]
                    and actual_frontiers["notes_frontier"] == frontiers[role]["notes_frontier"],
                    "native dispatch did not preserve the actual claimed Device and untouched Notes frontiers")
        else:
            require(actual_frontiers == frontiers[role],
                    "reconciliation consumed another FinalUse nonce or reset a retained consumer frontier")
        text(value["local_event_id"], "original local terminal event ID")
        current = checkpoint(value["current"], peers[role], owners[role]["agent_id"])
        prior = currents[role]["head"]
        require(current["head"]["writer_binding"] == prior["writer_binding"]
                and current["head"]["publisher_epoch"] == prior["publisher_epoch"]
                and current["head"]["counter"] >= prior["counter"], "terminal Current changed or regressed original authority")
        if "source_event" not in op:
            require(current["head"]["counter"] > prior["counter"]
                    and current["head"]["last_current"]["state_digest"] != prior["last_current"]["state_digest"],
                    "new source terminal did not reach a newly acknowledged original Current")
            op["source_event"] = value["local_event_id"]
        else:
            require(value["local_event_id"] == op["source_event"], "recovery replaced the original durable terminal event")
        currents[role] = current
        materials[role] = digest(value["material_sha256"], "actual retained material")
        frontiers[role] = actual_frontiers
        op["source_role"] = role

    def acknowledge(name, role):
        op = operations[name]
        value = obj(take("history_ack"), ("operation", "pid", "delivery", "source_owner", "source_generation", "retired_through",
                                         "next_sequence", "current_token"), "original durable-prefix retirement")
        require(value["operation"] == name and value["pid"] == role_pids[role] and type(value["pid"]) is int
                and delivery(value["delivery"]) == op["request"]["delivery"] and op.get("source_role") == role,
                "retirement lacks the exact live source terminal or history capability")
        require(value["source_owner"] == owners[role]["agent_id"]
                and type(value["source_generation"]) is int
                and value["source_generation"] == currents[role]["head"]["writer_binding"]["generation"]
                and value["current_token"] == currents[role]["token"], "retirement changed the source owner/cut")
        through = integer(value["retired_through"], "actual retired frontier", 1)
        next_sequence = integer(value["next_sequence"], "actual next delivery sequence", 2)
        require(through == int(op["request"]["delivery"]["sequence"], 16) and next_sequence == through + 1,
                "original retirement skipped a hole, terminal or delivery")
        op["retired"] = True

    def window(name, role, cap, revision):
        nonlocal last_usage
        value = obj(take("usage_window"), ("operation", "pid", "first", "second"), "actual workload accounting window")
        require(value["operation"] == name and type(value["pid"]) is int and value["pid"] == role_pids[role], "usage owner differs")
        first = usage(value["first"], boot_id, spaces[role])
        second = usage(value["second"], boot_id, spaces[role])
        progression(first, second)
        if last_usage is not None:
            progression(last_usage, first)
        require(first["revision"] == second["revision"] == revision
                and first["active_cap_ns"] == second["active_cap_ns"] == cap
                and second["sample_boottime_ns"] >= first["sample_boottime_ns"] + 2 * PERIOD_NS
                and first["heartbeat"] > 0, "workload observation is too short or changed budget/revision")
        if cap == 0:
            require(first["cumulative_cpu_ns"] == second["cumulative_cpu_ns"]
                    and first["heartbeat"] == second["heartbeat"], "zero budget did not stop the actual workload")
        else:
            require(second["cumulative_cpu_ns"] > first["cumulative_cpu_ns"] and second["heartbeat"] > first["heartbeat"],
                    "nonzero budget did not run the actual workload")
        last_usage = second

    copyout_flags = {}
    if prior_boot is not None:
        from types import SimpleNamespace
        result = prior_boot.finish(SimpleNamespace(
            take=take, role_pids=role_pids, boot_id=boot_id, linux_boot=linux_boot, spaces=spaces,
            peers=peers, state=state, owners=owners, currents=currents, materials=materials,
            frontiers=frontiers, operations=operations, prepared=prepared,
            native_result=native_result, source_terminal=source_terminal,
            acknowledge=acknowledge, window=window))
        require(cursor == len(values), "actual prior-boot stream contains a later or unexpected owner event")
        result.update(raw_serial_sha256=hashlib.sha256(raw).hexdigest(), event_count=len(values))
        return result
    if scenario == "steady-state-v1":
        for name, cap in (("lower", 25_000_000), ("pause", 0), ("resume", CAP_NS)):
            prepared(name, "manager", cap)
            native_result(name, "applied")
            source_terminal(name, "manager")
            acknowledge(name, "manager")
            window(name, "manager", cap, operations[name]["observation"]["revision"])
    elif scenario == "manager-exit-after-terminal-v1":
        prepared("pending-retirement", "manager", 25_000_000)
        native_result("pending-retirement", "applied")
        source_terminal("pending-retirement", "manager")
        old = operations["pending-retirement"]
        retired = obj(take("manager_retired"), ("pid", "start_ticks", "root_pid", "root_start_ticks", "signal", "wait_kind",
                                               "wait_value", "pidfd_revents", "old_current_token", "old_material_sha256"), "real manager exit")
        require(all(type(retired[key]) is int for key in ("pid", "start_ticks", "root_pid", "root_start_ticks", "signal", "wait_value", "pidfd_revents"))
                and retired["pid"] == role_pids["manager"] and retired["start_ticks"] == peers["manager"]["process_start_ticks"]
                and retired["root_pid"] == 1 and retired["root_start_ticks"] == peers["root"]["process_start_ticks"]
                and retired["signal"] == retired["wait_value"] == 9 and retired["wait_kind"] == "signaled"
                and retired["pidfd_revents"] == 1 and retired["old_current_token"] == currents["manager"]["token"]
                and retired["old_material_sha256"] == materials["manager"], "manager retirement lacks exact lifetime/current/material evidence")
        watchdog = obj(take("watchdog"), ("first_cpu_stat", "second_cpu_stat", "usage"), "independent watchdog")
        first, second = cpu_stat(watchdog["first_cpu_stat"]), cpu_stat(watchdog["second_cpu_stat"])
        require(all(first[key] == second[key] for key in first if key.startswith("hepta_watchdog_") and key != "hepta_watchdog_ticks")
                and second["hepta_watchdog_ticks"] >= first["hepta_watchdog_ticks"], "watchdog immutable receipt changed after restoration")
        observed = old["observation"]
        watchdog_stable = list((second["hepta_watchdog_stable_id_low"] | (second["hepta_watchdog_stable_id_high"] << 64)).to_bytes(16, "little"))
        require(watchdog_stable == observed["stable_object_id"]
                and second["hepta_watchdog_previous_revision"] == observed["revision"]
                and second["hepta_watchdog_effective_ns"] >= observed["effective_ns"],
                "watchdog receipt is not the independent successor effect on the same CPU")
        current_usage = usage(watchdog["usage"], boot_id, spaces["recovery"])
        progression(last_usage, current_usage)
        require(current_usage["revision"] == second["hepta_watchdog_revision"] and current_usage["active_cap_ns"] == CAP_NS
                and current_usage["sample_boottime_ns"] >= second["hepta_watchdog_effective_ns"], "watchdog current CPU observation differs")
        last_usage = current_usage
        lease = obj(take("local_lease_retired"), ("lease_id", "generation", "mode", "observed_unix_seconds", "expires_at_unix_seconds"),
                    "original local lease retirement")
        prior_writer = currents["manager"]["head"]["writer_binding"]
        require(lease["mode"] == "expired" and lease["lease_id"] == prior_writer["lease_id"]
                and type(lease["generation"]) is int and lease["generation"] == prior_writer["generation"]
                and type(lease["expires_at_unix_seconds"]) is int
                and lease["expires_at_unix_seconds"] == prior_writer["expires_at_unix_seconds"]
                and integer(lease["observed_unix_seconds"], "actual original lease observation", 1) >= lease["expires_at_unix_seconds"],
                "process death alone cannot retire the original local writer lease")
        adoption = obj(take("material_adopted"), ("previous", "successor", "material_sha256"), "actual original material adoption")
        require(adoption["previous"] == currents["manager"] and adoption["material_sha256"] == materials["manager"],
                "material handoff replaced the independently retained previous Current")
        adopted = checkpoint(adoption["successor"], peers["recovery"], owners["manager"]["agent_id"])
        old_head, adopted_head = currents["manager"]["head"], adopted["head"]
        require(adopted_head["publisher_epoch"] == old_head["publisher_epoch"] + 1
                and adopted_head["counter"] == old_head["counter"] + 1
                and adopted_head["last_current"] == old_head["last_current"]
                and adopted_head["last_mutation_sequence"] == 0 and adopted_head["last_request"] is None,
                "original material adoption changed the retained cut or canonical successor transition")
        owner_ready("recovery")
        reconciled = obj(take("reconciled"), ("operation", "pid", "occurrence_key", "request_json", "terminal_json", "usage"), "original D recovery")
        require(reconciled["operation"] == "pending-retirement" and type(reconciled["pid"]) is int
                and reconciled["pid"] == role_pids["recovery"] and reconciled["occurrence_key"] == old["key"]
                and reconciled["request_json"] == old["request_json"] and reconciled["terminal_json"] == old["terminal"],
                "recovery changed K/D or substituted the watchdog/current-cap result for old D")
        terminal(reconciled["terminal_json"], old["request"])
        reconciled_usage = usage(reconciled["usage"], boot_id, spaces["recovery"])
        progression(last_usage, reconciled_usage)
        require(reconciled_usage["revision"] == second["hepta_watchdog_revision"]
                and reconciled_usage["revision"] > old["observation"]["revision"]
                and reconciled_usage["active_cap_ns"] == CAP_NS, "query/reconcile repeated an old native effect")
        last_usage = reconciled_usage
        source_terminal("pending-retirement", "recovery")
        acknowledge("pending-retirement", "recovery")
        prepared("used-recovery-allowance", "recovery", CAP_NS)
        native_result("used-recovery-allowance", "not_applied")
        source_terminal("used-recovery-allowance", "recovery")
        acknowledge("used-recovery-allowance", "recovery")
        window("used-recovery-allowance", "recovery", CAP_NS, second["hepta_watchdog_revision"])

    elif scenario in COPYOUT_SCENARIOS:
        from types import SimpleNamespace
        import native_owner_copyout

        def retain_usage(sample):
            nonlocal last_usage
            last_usage = sample

        def retain_adoption(current):
            nonlocal adopted
            adopted = current

        # These are the same parsed raw events, original owner identities and
        # evidence checks. The extension cannot replace or synthesize an event.
        copyout_flags = native_owner_copyout.run(
            scenario,
            SimpleNamespace(take=take, role_pids=role_pids, boot_id=boot_id, spaces=spaces,
                            peers=peers, state=state, owners=owners, currents=currents,
                            materials=materials, frontiers=frontiers, operations=operations,
                            prepared=prepared, owner_ready=owner_ready, acknowledge=acknowledge,
                            window=window, retain_usage=retain_usage, retain_adoption=retain_adoption),
        )
    elif scenario in CONTINUITY_SCENARIOS:
        from types import SimpleNamespace
        import native_owner_continuity

        def peek():
            return values[cursor]["event"] if cursor < len(values) else None

        def next_line():
            require(cursor < len(events), "original continuation ended before its required event")
            return events[cursor][0]

        def current_usage():
            return last_usage

        def retain_usage(sample):
            nonlocal last_usage
            last_usage = sample

        # Every object is populated by the same actual transcript. No extension
        # manufactures an owner_ready event or changes the four earlier cases.
        copyout_flags = native_owner_continuity.run(
            scenario,
            SimpleNamespace(take=take, peek=peek, next_line=next_line, current_usage=current_usage,
                            retain_usage=retain_usage, role_pids=role_pids, boot_id=boot_id, spaces=spaces,
                            peers=peers, initial_peers={name: dict(peer) for name, peer in peers.items()},
                            owners=owners, currents=currents, materials=materials, frontiers=frontiers,
                            operations=operations, native_sequence=native_sequence, prepared=prepared,
                            native_result=native_result, source_terminal=source_terminal,
                            acknowledge=acknowledge, window=window),
            successor_markers,
        )
    else:
        raise ValueError("unsupported original-owner scenario")

    complete = obj(take("complete"), ("root_pid", "operation_count", "final_owner_pid", "final_current_token"), "finite owner-cycle completion")
    final_role = "manager" if scenario in ("steady-state-v1", "lost-copyout-live-v1") + CONTINUITY_SCENARIOS else "recovery"
    require(type(complete["root_pid"]) is int and complete["root_pid"] == 1
            and type(complete["operation_count"]) is int and complete["operation_count"] == len(operations)
            and type(complete["final_owner_pid"]) is int and complete["final_owner_pid"] == role_pids[final_role]
            and complete["final_current_token"] == currents[final_role]["token"] and cursor == len(values)
            and all(operation.get("retired") is True for operation in operations.values()),
            "finite owner cycle has missing, unexpected or unretired observations")
    result = {"passed": True, "scenario": scenario, "nonce": nonce, "actual_role_pids": role_pids,
            "event_count": len(events), "operation_count": len(operations), "original_native_owner_cycle_verified": True,
            "same_boot_authenticated_successor_verified": scenario == "manager-exit-after-terminal-v1",
            "source_terminal_before_retirement_verified": True, "bounded_cpu_control_verified": True,
            "raw_serial_sha256": hashlib.sha256(raw).hexdigest(), "raw_serial_bytes": len(raw),
            "grant_renewal_verified": False, "repeated_recovery_verified": False, "after_effect_crash_verified": False,
            "cross_boot_unknown_preservation_verified": False, "power_loss_verified": False,
            "unbounded_persistent_cpu_verified": False, "production_ready": False, "g2_complete": False}
    result.update(copyout_flags)
    return result
