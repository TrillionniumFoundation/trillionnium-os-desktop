"""Actual finite owner events while an older boot's K stays unresolved.

Only the dedicated two-boot renewal reader uses these extra event keys. The
original twelve scenarios retain their exact event schemas and authority
bindings. All state below is a projection of original observations.
"""
import hashlib

import native_owner_activation_witness as witness
import native_owner_continuity as continuity
import native_owner_evidence as e
import native_owner_prior_boot_store as store
import native_owner_prior_boot_types as old


OBSERVATION_KEYS = ("pid", "occurrence_key", "request_json", "before", "after", "refusal",
                    "calls_before", "calls_after", "drain_blockers", "device_frontier", "notes_frontier")
TERMINAL_REFUSAL = "HOS2 predecessor lacks complete durable native terminal evidence"


def clone(value):
    return e.json_value(e.canonical(value))


def observe(value, transport, pid, device, cut, previous, frontiers, count, prior_transport=None):
    actual = old.transport(transport, pid, device, cut, count, count)
    if prior_transport is not None:
        e.require(all(actual[key] == prior_transport[key] for key in old.TRANSPORT_KEYS if key != "ioctl_counts"),
                  "one actual Host changed its original database or captured startup Unknown")
    e.obj(value, OBSERVATION_KEYS, "actual original old-K observation across a release")
    before = e.obj(value["before"], ("operation", "topic", "payload_json", "state"), "actual original retained operation")
    e.obj(before["operation"], old.OPERATION_KEYS, "original seven-getter operation observation")
    e.require(type(value["pid"]) is int and value["pid"] == pid
              and value["occurrence_key"] == cut["occurrence_key"]
              and value["request_json"] == before["payload_json"] == cut["payload_json"]
              and before["topic"] == old.TOPIC and before["state"] == "indeterminate"
              and before["operation"] == store.operation_observation(previous["operation"])
              and value["before"] == value["after"]
              and value["refusal"] == "native boot changed; the old D remains unknown",
              "old immutable K/D, source state or actual pre-ioctl boot refusal changed")
    old.counts(value["calls_before"], count, count)
    e.require(value["calls_before"] == value["calls_after"] == actual["ioctl_counts"],
              "old-boot observation submitted an additional Install or Query")
    e.integer(value["drain_blockers"], "actual historical Unknown drain blocker", 1, 1)
    for lane in e.FRONTIER_LANES:
        e.require(e.frontier(value[lane], "actual retained " + lane) == frontiers[lane],
                  "old-K observation consumed or reset a FinalUse claim")
    return actual


class RetainedContinuity(continuity.Continuity):
    def __init__(self, context, markers, cut, previous, stopped):
        super().__init__(context, markers)
        self.cut, self.prior, self.stopped = cut, previous, stopped
        self.operations = []
        self.releases = []
        self.retained_observations = []
        self.transports = {}
        self.initial_physical_identities = set()

    def owner_keys(self):
        return continuity.OWNER_KEYS + ("retained_prior_boot",)

    def release_keys(self):
        return continuity.RELEASE_KEYS + ("retained_prior_boot",)

    def root_lease_id(self, writer, initial):
        # This is a new actual Root session over an existing installation.
        # It must not reuse the first boot's installation lease ID.
        return "native-cpu.root." + self.c.peers["root"]["boot_id"] + "." + str(writer["spawn_generation"])

    def original_root_scope(self):
        # Root observation authority preserves its first installed binding.
        # New kernel effect namespaces are separately checked by each actual
        # final Process bootstrap and original native operation.
        return hashlib.sha256(b"hepta.hos2.cpu-budget.scope.v1\0" + bytes(self.cut["kernel_boot"])
                              + bytes(self.prior["spaces"]["manager"])
                              + (2).to_bytes(8, "little") + (1).to_bytes(8, "little")).digest()

    def retained(self, value, phase, actor, frontiers):
        e.obj(value, ("phase", "observation", "transport", "terminal_lookup"), "actual retained old-K handoff observation")
        e.require(value["phase"] == phase, "old-K sample was relabelled across Stop")
        terminal = e.obj(value["terminal_lookup"], ("error_kind", "reason"), "actual original terminal accessor refusal")
        e.require(terminal == {"error_kind": "illegal_transition", "reason": TERMINAL_REFUSAL},
                  "an arbitrary source error was substituted for the original terminal accessor branch")
        count = 1 if phase == "before_stop" and actor["role"] == "manager" else 0
        lifetime = tuple(actor["peer"][key] for key in ("pid", "boot_id", "process_start_ticks"))
        prior = self.transports.get(lifetime)
        e.require((prior is None) if phase == "owner_started" else prior is not None,
                  "actual old-K samples skipped or repeated the corresponding owner start")
        transport = observe(value["observation"], value["transport"], actor["pid"], self.c.state["store_device"],
                            self.cut, self.stopped["live_database"], frontiers, count, prior)
        if phase == "owner_started":
            physical = (transport["database_device"], transport["database_inode"])
            e.require(physical not in self.initial_physical_identities
                      and physical != (self.prior["source_database"]["database_device"],
                                       self.prior["source_database"]["database_inode"]),
                      "a newly installed original owner reused a predecessor's writable database inode")
            self.initial_physical_identities.add(physical)
            self.transports[lifetime] = clone(transport)
        self.retained_observations.append({"role": actor["role"], "peer_lifetime": clone(actor["peer"]),
                                           "sample": clone(value)})
        return transport

    def owner(self, role, initial=False):
        value = super().owner(role, initial)
        self.retained(value["retained_prior_boot"], "owner_started", self.active, self.c.frontiers[role])
        if initial:
            self.activation_witnesses.append(witness.expectation(
                value["writer"], self.prior["cut_current"], self.c.peers["root"], self.active["peer"],
                self.prior["cut_material_sha256"]))
        return value

    def operation(self, name, with_ack=True, with_window=True):
        value = super().operation(name, with_ack, with_window)
        e.require(value["key"] != self.cut["occurrence_key"]
                  and value["request"]["delivery"]["boot_id"] != self.cut["kernel_boot"],
                  "a continued effect reused the unresolved old K or old boot namespace")
        self.operations.append(clone(value))
        return value

    def release(self):
        actor = self.active
        value = super().release()
        self.retained(value["retained_prior_boot"], "before_stop", actor, self.c.frontiers[actor["role"]])
        self.releases.append(clone(value))
        return value
