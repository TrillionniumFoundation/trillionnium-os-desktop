"""Evidence checks for real original-FileTransport response loss.

The only input is the unmodified transcript consumed by the original owner
oracle. This module issues no command, allocates no K/D, and constructs no
receipt or replacement event. Its two finite scopes require the reviewed
original Rust producer, original image bounds and actual guest execution.
"""
import hashlib
import struct

import native_owner_evidence as e
from native_owner_fault_wire import match_install_wire


TOPIC = "hepta.hos2.install-budget.v1"
DESTINATION = "hos2.cpu-budget.v1"
DIAGNOSTIC_KEYS = ("install_ioctl_count", "selected_ioctl_count", "efault_count", "request_sha256",
                   "request_bytes", "response_capacity", "syscall_return", "errno")
SNAPSHOT_KEYS = ("install_ioctl_count", "selected_ioctl_count", "efault_count", "armed", "last")
DISPATCH_REQUEST_KEYS = ("schema_version", "namespace", "lease_id", "occurrence_key", "topic", "payload_json",
                         "payload_sha256", "idempotency_key", "operation_scope_sha256", "operation_subject_id",
                         "operation_destination_id", "operation_semantic_sha256", "operation_policy_generation",
                         "expected_predecessor_sha256", "operation_digest")
DISPATCH_RECEIPT_KEYS = ("request", "state", "target_disposition", "target_receipt", "target_reason",
                         "local_event_id", "external_effect")
OUTCOME_KEYS = ("lease_id", "occurrence_key", "state", "event_id", "external_effect")
SOURCE_KEYS = ("operation", "pid", "occurrence_key", "state", "terminal_json", "local_event_id", "current",
               "material_sha256", "device_frontier", "notes_frontier")


def diagnostic(value, request_json):
    value = e.obj(value, DIAGNOSTIC_KEYS, "actual FileTransport copyout diagnostic")
    for key in ("install_ioctl_count", "selected_ioctl_count", "efault_count"):
        e.integer(value[key], "actual " + key, 1, 1)
    wire = value["request_sha256"]
    e.require(type(wire) is list and len(wire) == 32
              and all(type(item) is int and 0 <= item <= 255 for item in wire),
              "actual FileTransport frame digest is not the original 32-byte array")
    e.integer(value["response_capacity"], "unchanged original FileTransport response capacity", 128, 128)
    match_install_wire(request_json, bytes(wire).hex(), value["request_bytes"], value["response_capacity"])
    e.integer(value["syscall_return"], "actual ioctl return", -1, -1)
    e.integer(value["errno"], "actual ioctl EFAULT", 14, 14)
    return value


def snapshot(value, request_json=None, previous=None):
    value = e.obj(value, SNAPSHOT_KEYS, "actual FileTransport copyout snapshot")
    calls = 0 if request_json is None else 1
    for key in ("install_ioctl_count", "selected_ioctl_count", "efault_count"):
        e.integer(value[key], "descriptor " + key, calls, calls)
    e.require(value["armed"] is False, "copyout arm remained available after the original attempt")
    if request_json is None:
        e.require(value["last"] is None, "the Recovery descriptor inherited or made an Install")
    else:
        diagnostic(value["last"], request_json)
        if previous is not None:
            e.require(value["last"] == previous, "the original ioctl diagnostic changed after reconciliation")
    return value


def dispatch_receipt(value, op, owner, current):
    value = e.obj(value, DISPATCH_RECEIPT_KEYS, "original returned Indeterminate dispatch receipt")
    request = e.obj(value["request"], DISPATCH_REQUEST_KEYS, "complete original production dispatch request")
    expected = op["request"]
    writer = current["head"]["writer_binding"]
    e.integer(request["schema_version"], "original dispatch schema", 1, 1)
    e.integer(request["operation_policy_generation"], "original operation policy generation", 1)
    e.require(request["namespace"] == "production_durable_writer"
              and request["lease_id"] == writer["lease_id"]
              and request["occurrence_key"] == request["idempotency_key"] == op["key"]
              and request["topic"] == TOPIC and request["payload_json"] == op["request_json"]
              and request["payload_sha256"] == op["payload_sha256"]
              and request["operation_subject_id"] == owner["agent_id"]
              and request["operation_destination_id"] == DESTINATION
              and request["operation_policy_generation"] == writer["authority_epoch"]
              and request["expected_predecessor_sha256"] is None,
              "the original Indeterminate receipt changed K/D, owner, lease or operation domain")
    scope = (b"hepta.hos2.cpu-budget.scope.v1\0" + bytes(expected["delivery"]["boot_id"])
             + bytes(expected["delivery"]["space_id"])
             + struct.pack("<QQ", expected["manage_slot"], expected["manage_generation"]))
    e.require(e.digest(request["operation_scope_sha256"], "original operation scope")
              == hashlib.sha256(scope).hexdigest(), "original dispatch scope changed the exact native namespace/slot")
    for key in ("payload_sha256", "operation_semantic_sha256", "operation_digest"):
        e.digest(request[key], "original " + key)
    e.require(value["state"] == value["target_disposition"] == "indeterminate"
              and value["target_receipt"] is None and value["external_effect"] is False,
              "lost response was replaced by a terminal or an external-effect claim")
    e.text(value["target_reason"], "original returned provider diagnostic", 32768)
    e.text(value["local_event_id"], "original Indeterminate local event ID")
    return value


def outcome(value, op, current):
    value = e.obj(value, OUTCOME_KEYS, "original retained production outcome receipt")
    e.require(value["lease_id"] == current["head"]["writer_binding"]["lease_id"]
              and value["occurrence_key"] == op["key"] and value["state"] == "committed"
              and value["external_effect"] is False, "reconciled outcome changed the original owner, K or terminal")
    e.text(value["event_id"], "original retained terminal event ID")
    return value


class CopyoutOracle:
    def __init__(self, shared):
        self.s = shared
        self.last_usage = None
        self.before = None
        self.after = None
        self.fault_diagnostic = None
        self.indeterminate_event = None
        self.crash_boundary = None
        self.watchdog = None
        self.reconciled_count = None
        self.outcome = None

    def track(self, sample):
        if self.last_usage is not None:
            e.progression(self.last_usage, sample)
        self.last_usage = sample
        self.s.retain_usage(sample)

    def require_operation(self, value, op, name, role):
        e.require(value["operation"] == name and type(value["pid"]) is int
                  and value["pid"] == self.s.role_pids[role] and value["occurrence_key"] == op["key"],
                  "copyout evidence belongs to another original operation or actual owner")

    def prepared(self, name):
        op = self.s.prepared(name, "manager", 25_000_000)
        e.require(op["request"]["delivery"]["sequence"] == "0000000000000001",
                  "copyout qualification must use the first original D")
        delivery_hash = hashlib.sha256(e.canonical(op["request"]["delivery"]).encode()).hexdigest()
        e.require(op["key"] == "native-cpu:" + delivery_hash + ":" + name,
                  "copyout K is not the original producer's exact immutable delivery binding")
        return op

    def live_fault(self, op, name):
        value = e.obj(self.s.take("copyout_indeterminate"),
                      ("operation", "pid", "occurrence_key", "receipt", "before", "after", "copyout"),
                      "actual returned original lost-copyout observation")
        self.require_operation(value, op, name, "manager")
        receipt = dispatch_receipt(value["receipt"], op, self.s.owners["manager"], self.s.currents["manager"])
        actual = snapshot(value["copyout"], op["request_json"])
        self.fault_diagnostic = actual["last"]
        self.indeterminate_event = receipt["local_event_id"]
        self.before = e.usage(value["before"], self.s.boot_id, self.s.spaces["manager"])
        self.after = e.usage(value["after"], self.s.boot_id, self.s.spaces["manager"])
        e.require(self.before["revision"] == op["request"]["expected_revision"]
                  and self.before["active_cap_ns"] == e.CAP_NS
                  and self.after["revision"] == self.before["revision"] + 1
                  and self.after["active_cap_ns"] == op["request"]["cap_ns"],
                  "the one actual Install did not produce the one original CPU effect")
        self.track(self.before)
        self.track(self.after)

    def crash_fault(self, op, name):
        value = e.obj(self.s.take("copyout_boundary"),
                      ("operation", "pid", "occurrence_key", "request_json", "payload_sha256", "before", "diagnostic",
                       "observed_boottime_ns", "pending_until_boottime_ns", "current", "material_sha256",
                       "device_frontier", "notes_frontier"), "actual effect-before-terminal boundary")
        self.require_operation(value, op, name, "manager")
        e.require(value["request_json"] == op["request_json"] and value["payload_sha256"] == op["payload_sha256"],
                  "crash callback changed the one original K/D payload")
        self.fault_diagnostic = diagnostic(value["diagnostic"], op["request_json"])
        observed = e.integer(value["observed_boottime_ns"], "actual completed-EFAULT callback BOOTTIME", 1)
        pending = e.integer(value["pending_until_boottime_ns"], "actual bounded synchronous callback deadline", 1)
        e.require(0 < pending - observed <= 2_000_000_000,
                  "actual synchronous fault boundary is absent, expired or extended beyond two seconds")
        self.before = e.usage(value["before"], self.s.boot_id, self.s.spaces["manager"])
        e.require(self.before["revision"] == op["request"]["expected_revision"]
                  and self.before["active_cap_ns"] == e.CAP_NS and self.before["sample_boottime_ns"] <= observed,
                  "copyout boundary does not follow the original pre-effect usage sample")
        self.track(self.before)
        current = e.checkpoint(value["current"], self.s.peers["manager"], self.s.owners["manager"]["agent_id"])
        prior = self.s.currents["manager"]["head"]
        e.require(current["head"]["writer_binding"] == prior["writer_binding"]
                  and current["head"]["publisher_epoch"] == prior["publisher_epoch"]
                  and current["head"]["counter"] > prior["counter"]
                  and current["head"]["last_current"]["state_digest"] != prior["last_current"]["state_digest"],
                  "the prepared Unknown did not reach the original retained Current before the crash")
        actual_frontiers = {lane: e.frontier(value[lane], lane) for lane in e.FRONTIER_LANES}
        for lane in e.FRONTIER_LANES:
            previous = self.s.frontiers["manager"][lane]
            e.require(all(actual_frontiers[lane][key] == previous[key]
                          for key in ("authority_epoch", "revocation_revision")),
                      "copyout changed the original finite issuer epoch or revocation head")
        e.require(actual_frontiers["device_frontier"] != self.s.frontiers["manager"]["device_frontier"]
                  and actual_frontiers["notes_frontier"] == self.s.frontiers["manager"]["notes_frontier"],
                  "actual effect entry did not retain one Device claim and the untouched Notes frontier")
        self.s.currents["manager"] = current
        self.s.materials["manager"] = e.digest(value["material_sha256"], "physical retained crash material")
        self.s.frontiers["manager"] = actual_frontiers
        self.crash_boundary = value

    def retire_and_recover(self, op):
        value = e.obj(self.s.take("manager_retired"),
                      ("pid", "start_ticks", "root_pid", "root_start_ticks", "signal", "wait_kind", "wait_value",
                       "pidfd_revents", "old_current_token", "old_material_sha256", "kill_boottime_ns"),
                      "actual Manager death before the source terminal")
        for key in ("pid", "start_ticks", "root_pid", "root_start_ticks", "signal", "wait_value", "pidfd_revents"):
            e.integer(value[key], "actual exit " + key)
        killed = e.integer(value["kill_boottime_ns"], "actual pidfd SIGKILL completion BOOTTIME", 1)
        boundary = self.crash_boundary
        e.require(value["pid"] == self.s.role_pids["manager"]
                  and value["start_ticks"] == self.s.peers["manager"]["process_start_ticks"]
                  and value["root_pid"] == self.s.role_pids["root"]
                  and value["root_start_ticks"] == self.s.peers["root"]["process_start_ticks"]
                  and value["signal"] == value["wait_value"] == 9 and value["wait_kind"] == "signaled"
                  and value["pidfd_revents"] == 1
                  and value["old_current_token"] == self.s.currents["manager"]["token"]
                  and value["old_material_sha256"] == self.s.materials["manager"]
                  and boundary["observed_boottime_ns"] <= killed < boundary["pending_until_boottime_ns"],
                  "crash lacks actual same-pidfd SIGKILL/exit within the held original callback")

        value = e.obj(self.s.take("watchdog"), ("first_cpu_stat", "second_cpu_stat", "usage"),
                      "independent original five-second watchdog")
        first, second = e.cpu_stat(value["first_cpu_stat"]), e.cpu_stat(value["second_cpu_stat"])
        e.require(all(first[key] == second[key] for key in first
                      if key.startswith("hepta_watchdog_") and key != "hepta_watchdog_ticks")
                  and second["hepta_watchdog_ticks"] >= first["hepta_watchdog_ticks"]
                  and second["hepta_watchdog_previous_revision"] == op["request"]["expected_revision"] + 1,
                  "watchdog immutable receipt is not the independent successor of the lost D")
        current_usage = e.usage(value["usage"], self.s.boot_id, self.s.spaces["recovery"])
        e.require(current_usage["revision"] == second["hepta_watchdog_revision"]
                  and current_usage["active_cap_ns"] == e.CAP_NS
                  and current_usage["sample_boottime_ns"] >= second["hepta_watchdog_effective_ns"],
                  "actual post-crash CPU usage does not match the independent watchdog receipt")
        self.track(current_usage)
        self.watchdog = second

        lease = e.obj(self.s.take("local_lease_retired"),
                      ("lease_id", "generation", "mode", "observed_unix_seconds", "expires_at_unix_seconds"),
                      "original local writer lease retirement")
        prior = self.s.currents["manager"]["head"]["writer_binding"]
        e.require(lease["mode"] == "expired" and lease["lease_id"] == prior["lease_id"]
                  and type(lease["generation"]) is int and lease["generation"] == prior["generation"]
                  and type(lease["expires_at_unix_seconds"]) is int
                  and lease["expires_at_unix_seconds"] == prior["expires_at_unix_seconds"]
                  and e.integer(lease["observed_unix_seconds"], "actual original lease time", 1)
                  >= lease["expires_at_unix_seconds"], "process exit substituted for retirement of the original local lease")
        adoption = e.obj(self.s.take("material_adopted"), ("previous", "successor", "material_sha256"),
                         "actual original Unknown material adoption")
        e.require(adoption["previous"] == self.s.currents["manager"]
                  and adoption["material_sha256"] == self.s.materials["manager"],
                  "recovery did not retain the exact pre-terminal Current/material")
        adopted = e.checkpoint(adoption["successor"], self.s.peers["recovery"], self.s.owners["manager"]["agent_id"])
        old, new = self.s.currents["manager"]["head"], adopted["head"]
        e.require(new["publisher_epoch"] == old["publisher_epoch"] + 1
                  and new["counter"] == old["counter"] + 1 and new["last_current"] == old["last_current"]
                  and new["last_mutation_sequence"] == 0 and new["last_request"] is None,
                  "material adoption replaced the original Unknown cut or canonical successor")
        self.s.retain_adoption(adopted)
        self.s.owner_ready("recovery")

    def startup(self, op):
        value = e.obj(self.s.take("copyout_recovery_startup"),
                      ("pid", "occurrence_key", "capture_point", "captured", "copyout"),
                      "original factory capture before monitor startup")
        e.require(type(value["pid"]) is int and value["pid"] == self.s.role_pids["recovery"]
                  and value["occurrence_key"] == op["key"]
                  and value["capture_point"] == "original_recovery_before_monitor"
                  and type(value["captured"]) is list and len(value["captured"]) == 1,
                  "recovery lacks the one original pre-monitor Unknown observation")
        captured = e.obj(value["captured"][0], ("occurrence_key", "topic", "payload_json", "state"),
                         "actual retained startup row")
        e.require(captured["occurrence_key"] == op["key"] and captured["topic"] == TOPIC
                  and captured["payload_json"] == op["request_json"] and captured["state"] == "indeterminate",
                  "original recovery reset, resent or replaced the same Unknown K/D")
        snapshot(value["copyout"])

    def reconcile(self, op, name, role):
        value = e.obj(self.s.take("copyout_reconciled"),
                      ("operation", "pid", "occurrence_key", "request_json", "receipt", "terminal_json", "usage",
                       "before_state", "before_payload_json", "reconciled_count", "copyout"),
                      "original observer-only lost-D recovery")
        self.require_operation(value, op, name, role)
        e.require(value["request_json"] == value["before_payload_json"] == op["request_json"],
                  "reconciliation rebound the immutable K/D payload")
        count = e.integer(value["reconciled_count"], "actual bounded reconciliation count", 0, 1)
        e.require((value["before_state"], count) in (("indeterminate", 1), ("committed", 0)),
                  "single original K has an inconsistent serialized observer transition")
        self.reconciled_count = count
        self.outcome = outcome(value["receipt"], op, self.s.currents[role])
        if self.indeterminate_event is not None:
            e.require(self.outcome["event_id"] != self.indeterminate_event,
                      "the Indeterminate event was relabeled as a terminal")
        observed = e.terminal(value["terminal_json"], op["request"])
        e.require(observed["state"] == "applied", "copyout observer did not recover the original Applied D")
        sample = e.usage(value["usage"], self.s.boot_id, self.s.spaces[role])
        e.require(self.before["sample_boottime_ns"] <= observed["effective_ns"]
                  and observed["previous_revision"] == self.before["revision"],
                  "retained Applied cut predates or differs from the original operation")
        if role == "manager":
            snapshot(value["copyout"], op["request_json"], self.fault_diagnostic)
            e.require(observed["effective_ns"] <= self.after["sample_boottime_ns"]
                      and sample["revision"] == self.after["revision"] == observed["revision"]
                      and sample["active_cap_ns"] == op["request"]["cap_ns"],
                      "live observer replayed the Install or changed the original Applied revision")
        else:
            snapshot(value["copyout"])
            stable = list((self.watchdog["hepta_watchdog_stable_id_low"]
                           | (self.watchdog["hepta_watchdog_stable_id_high"] << 64)).to_bytes(16, "little"))
            e.require(observed["effective_ns"] <= self.crash_boundary["observed_boottime_ns"]
                      and observed["revision"] == self.watchdog["hepta_watchdog_previous_revision"]
                      and observed["stable_object_id"] == stable
                      and self.watchdog["hepta_watchdog_effective_ns"] >= observed["effective_ns"]
                      and sample["revision"] == self.watchdog["hepta_watchdog_revision"]
                      and sample["revision"] > observed["revision"] and sample["active_cap_ns"] == e.CAP_NS,
                      "recovery replaced old D with the watchdog result or spent another Install")
        for checked, relation in ((self.before, "before"), (self.after, "after")):
            if checked is not None and checked["window_start_ns"] == observed["effective_ns"] // e.PERIOD_NS * e.PERIOD_NS:
                e.require((checked["window_consumed_ns"] <= observed["consumed_ns"] if relation == "before"
                           else checked["window_consumed_ns"] >= observed["consumed_ns"]),
                          "the lost-copyout effect reset actual CPU accounting")
        self.track(sample)
        op.update(terminal=value["terminal_json"], observation=observed)

    def source_terminal(self, op, name, role):
        value = e.obj(self.s.take("source_terminal"), SOURCE_KEYS, "original durable lost-copyout source terminal")
        self.require_operation(value, op, name, role)
        e.require(value["state"] == self.outcome["state"] == "committed"
                  and value["terminal_json"] == op["terminal"] and value["local_event_id"] == self.outcome["event_id"],
                  "source Current does not retain the exact original outcome event and K/D terminal")
        frontiers = {lane: e.frontier(value[lane], lane) for lane in e.FRONTIER_LANES}
        for lane in e.FRONTIER_LANES:
            previous = self.s.frontiers[role][lane]
            e.require(all(frontiers[lane][key] == previous[key] for key in ("authority_epoch", "revocation_revision")),
                      "observer reconciliation changed original FinalUse epoch or revocation")
        if role == "manager":
            e.require(frontiers["device_frontier"] != self.s.frontiers[role]["device_frontier"]
                      and frontiers["notes_frontier"] == self.s.frontiers[role]["notes_frontier"],
                      "the live fault did not retain its original Device claim and untouched Notes frontier")
        else:
            e.require(frontiers == self.s.frontiers[role], "old-D observation consumed another FinalUse nonce")
        current = e.checkpoint(value["current"], self.s.peers[role], self.s.owners[role]["agent_id"])
        prior = self.s.currents[role]
        head = current["head"]
        e.require(head["writer_binding"] == prior["head"]["writer_binding"]
                  and head["publisher_epoch"] == prior["head"]["publisher_epoch"]
                  and head["counter"] >= prior["head"]["counter"],
                  "source terminal Current changed or regressed its original publisher/authority")
        if head["counter"] == prior["head"]["counter"]:
            e.require(current == prior and role == "recovery" and self.reconciled_count == 0,
                      "only an already-retained monitor terminal may reuse the exact observed Current")
        else:
            e.require(head["last_current"]["state_digest"] != prior["head"]["last_current"]["state_digest"]
                      or (role == "recovery" and self.reconciled_count == 0),
                      "new source terminal did not reach its actual changed original Current")
        if role == "recovery":
            e.require(head["last_current"]["state_digest"]
                      != self.crash_boundary["current"]["head"]["last_current"]["state_digest"],
                      "terminal Current still names the original pre-terminal Unknown cut")
        self.s.currents[role] = current
        self.s.materials[role] = e.digest(value["material_sha256"], "physical terminal material")
        self.s.frontiers[role] = frontiers
        op["source_event"] = value["local_event_id"]
        op["source_role"] = role

    def finish(self, op, name, role):
        self.reconcile(op, name, role)
        self.source_terminal(op, name, role)
        self.s.acknowledge(name, role)
        revision = op["observation"]["revision"] if role == "manager" else self.watchdog["hepta_watchdog_revision"]
        cap = op["request"]["cap_ns"] if role == "manager" else e.CAP_NS
        self.s.window(name, role, cap, revision)


def run(scenario, shared):
    e.require(scenario in e.COPYOUT_SCENARIOS, "unsupported original copyout scope")
    oracle = CopyoutOracle(shared)
    live = scenario == "lost-copyout-live-v1"
    name = "lost-copyout-live" if live else "lost-before-terminal"
    op = oracle.prepared(name)
    if live:
        oracle.live_fault(op, name)
    else:
        oracle.crash_fault(op, name)
        oracle.retire_and_recover(op)
        oracle.startup(op)
    oracle.finish(op, name, "manager" if live else "recovery")
    e.require(len(shared.operations) == 1, "copyout scenario dispatched an extra original operation")
    return {"lost_copyout_live_verified": live,
            "same_boot_authenticated_successor_verified": not live,
            "after_effect_crash_verified": not live,
            "recovered_unknown_without_install_verified": not live,
            "copyout_observer_without_install_replay_verified": True}
