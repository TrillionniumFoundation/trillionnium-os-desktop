"""Validate original G2 image/launcher records; never create a kernel receipt."""
import hashlib
import re

import native_owner_evidence as base
from native_owner_root_observation import PAYLOAD_KEYS, launch_observation_id
from native_owner_successor_wire import launch_receipt, match_transition, retirement_receipt


PAIR = re.compile(r"^\[hepta-g2\] successor roles activated: generation=([0-9]+) manager=([0-9]+) workload=([0-9]+) "
                  r"recovery=([0-9]+) bootstrap_version=4 bytes=240 hepta_durability=false$")
HISTORY = re.compile(r"^\[hepta-g2\] history successor activated: generation=([0-9]+) history=([0-9]+) workload=([0-9]+) "
                     r"bootstrap_version=4 bytes=240 hepta_durability=false$")


def kernel_records(lines, events, elf_info):
    records = []
    pending = []
    initial = None
    for number, line in enumerate(lines):
        if not line.startswith("[hepta-g2]"):
            continue
        image = base.IMAGE.fullmatch(line)
        if image:
            base.require(int(image[1]) == elf_info["bytes"] and int(image[2], 16) == elf_info["entry"],
                         "successor does not load the same actual reviewed original ELF")
            pending.append(number)
            continue
        activated = base.ACTIVATION.fullmatch(line)
        if activated:
            base.require(initial is None and not records and len(pending) == 4 and max(pending) < number < events[0][0],
                         "initial four actual images did not commit before the original owner")
            initial = (number, activated)
            pending = []
            continue
        pair, history = PAIR.fullmatch(line), HISTORY.fullmatch(line)
        base.require(initial is not None and (pair is not None or history is not None),
                     "unknown G2 kernel record or image rejection")
        matched = pair or history
        generation = int(matched[1])
        base.require(generation == len(records) + 1 and len(pending) == (2 if pair else 1)
                     and max(pending) < number, "actual factory image count or launch generation chain differs")
        roles = ({"manager": int(matched[2]), "workload": int(matched[3]), "recovery": int(matched[4])}
                 if pair else {"history": int(matched[2]), "workload": int(matched[3])})
        base.require(all(0 < pid < 1 << 31 for pid in roles.values()) and len(set(roles.values())) == len(roles),
                     "actual successor Process roles alias or exceed the original PID range")
        records.append({"line": number, "first_image_line": pending[0], "generation": generation,
                        "mode": 1 if pair else 2, "pids": roles})
        pending = []
    base.require(initial is not None and not pending and records, "complete original initial/successor image records required")
    return initial, records


class Launches:
    def __init__(self, boot_id, role_pids, spaces, markers):
        self.boot = boot_id
        self.markers = markers
        # This identity comes from the actual initial-role evidence. It is not
        # a fabricated Query receipt; only later raw receipts enter saved[].
        self.current = {"generation": 0, "mode": 1, "history_spaces": [spaces["manager"], spaces["recovery"]],
                        "pids": {**role_pids, "history": 0}}
        self.saved = {}
        self.observed = []
        self.seen_namespaces = {bytes(space) for space in self.current["history_spaces"]}

    def saved_event(self, value, line, predecessor_stopped_line, adoption_line):
        base.obj(value, ("boot_id", "launch_generation", "launch_receipt", "retirement_receipt", "observation_id",
                         "durable_payload_json", "durable_payload_sha256"), "original saved kernel launch")
        base.require(base.byte_id(value["boot_id"], "saved actual boot") == self.boot,
                     "Root saved an observation from another native boot")
        generation = base.integer(value["launch_generation"], "saved actual launch generation", 1)
        launched = launch_receipt(value["launch_receipt"], self.boot)
        retired = retirement_receipt(value["retirement_receipt"], self.boot)
        base.require(launched["generation"] == retired["generation"] == generation,
                     "saved original launch and retirement name different generations")
        identity = launch_observation_id(self.boot, generation)
        base.require(value["observation_id"] == identity and type(value["durable_payload_json"]) is str
                     and 0 < len(value["durable_payload_json"].encode()) <= 16_384,
                     "actual Root saved identifier or payload bound differs")
        raw_payload = value["durable_payload_json"].encode("utf-8")
        base.require(base.digest(value["durable_payload_sha256"], "actual Root saved payload")
                     == hashlib.sha256(raw_payload).hexdigest(), "Root saved payload hash does not cover its actual bytes")
        payload = base.obj(base.json_value(raw_payload), PAYLOAD_KEYS, "actual saved Root payload")
        base.require(type(payload["schema_version"]) is int and payload["schema_version"] == 1
                     and payload["operation"] == "kernel.g2.launch-observation.v1"
                     and payload["boot_id"] == self.boot and type(payload["launch_generation"]) is int
                     and payload["launch_generation"] == generation
                     and payload["launch_receipt"] == value["launch_receipt"]
                     and payload["retirement_receipt"] == value["retirement_receipt"],
                     "Root persisted a different complete launch/retirement transaction")
        if generation in self.saved:
            base.require(generation == self.current["generation"] and self.saved[generation]["event"] == value,
                         "repeated Manager/Recovery observation changed an immutable original saved file")
        else:
            match_transition(self.current, launched, retired)
            if launched["mode"] == 1:
                base.require(all(bytes(space) not in self.seen_namespaces for space in launched["history_spaces"]),
                             "fresh kernel pair reused an older original effect namespace")
                self.seen_namespaces.update(bytes(space) for space in launched["history_spaces"])
            base.require(generation <= len(self.markers), "Root invented an unobserved kernel launch")
            marker = self.markers[generation - 1]
            base.require(marker["generation"] == generation and marker["mode"] == launched["mode"]
                         and all(launched["pids"][role] == pid for role, pid in marker["pids"].items())
                         and predecessor_stopped_line < marker["first_image_line"] <= marker["line"] < adoption_line < line,
                         "actual launch did not follow original exit/reap and precede physical owner adoption")
            self.saved[generation] = {"event": value, "launch": launched, "retirement": retired}
            self.current = launched
        self.observed.append(generation)
        return launched, retired

    def finish(self):
        base.require(set(self.saved) == set(range(1, len(self.markers) + 1)),
                     "kernel launch has no matching actual Root durable observation")
        return [self.saved[generation]["event"] for generation in sorted(self.saved)]
