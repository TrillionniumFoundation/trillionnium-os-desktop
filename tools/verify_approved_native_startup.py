#!/usr/bin/env python3
"""Closed source correspondence for the approved immutable native composition.

This structural check does not execute Servo, attest a peer, or mint approval.
Exact-pin compilation and actual native regressions remain separate gates.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
import sys
import tomllib

try:
    from .artifact_evidence import load
    from .prepare_native_product_owner import read
    from .scan_s06_public_exports import tokens
except ImportError:
    from artifact_evidence import load
    from prepare_native_product_owner import read
    from scan_s06_public_exports import tokens

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "contracts/approved-native-startup.v1.json"
QUEUE = "apps/hepta-browserd/src/product_dispatch/product_approved_queue.rs"
NATIVE = "experiments/servo-product-owner/src/approved_startup.rs"
MAX_SOURCE_BYTES = 2 * 1024 * 1024
EXPECTED = {
    "schema": "trillionnium.desktop.approved-native-startup.v1",
    "status": "SOURCE_CANDIDATE_EXACT_PIN_EXECUTION_PENDING",
    "requirements": ["G2", "G3"],
    "servo_commit": "670ae8a70801b162e186f81cbb5bdd2d59c39108",
    "default_activation": False,
    "admission": {
        "constructor": "ApprovedRetainedAdmission::from_received",
        "mechanism_policy": "externally_pinned_root_owned_retained_document",
        "attestor": "ProcfsPeerAttestor::default",
        "pair": "same_original_approved_connection_and_private_monitor",
        "public_separation": False, "principal_from_caller": False,
        "durable_seal": "existing_coordinator_private_own_managed_same_request_terminal_reread",
    },
    "ownership": {
        "native_constructor": "ClosedImmutableNativeOwner::new",
        "native_endpoint_from_caller": False,
        "native_creator_pid_and_thread": True,
        "actor_coordinator_created_on_worker": True,
        "one_shot_packet": True, "maximum_active": 1,
        "maximum_queued": 1, "maximum_result_queue": 1,
        "automatic_restart_or_replay": False,
        "foreign_process_cleanup": "forget_inherited_channels_and_native_state_process_exit_only",
    },
    "deadlines": {
        "accepted_seconds_maximum": 20, "native_seconds_maximum": 5,
        "driver_ceiling": "first_original_opaque_admission_instant",
        "queued_deadline_must_not_exceed_first": True,
        "monitor_uses_original_deadline": True, "renewal": False,
        "synchronous_native_proc_fs_preemptible": False,
    },
    "retirement": {
        "registry_acquisition": "try_lock",
        "requested_means": "atomic_denial_requested_not_completed_barrier",
        "active_cancellation_issued_means": "original_token_cancel_and_socket_shutdown_issued_not_native_barrier",
        "drop_joins_worker": False, "all_drop_bounded": False,
        "legacy_cancellation_mutex_waits_remain": True,
        "acknowledgment_is_agent_delivery_or_effect_success": False,
    },
    "profile": {
        "constructor": "closed_immutable_servo_runtime_pair",
        "content": "fixed_data_document_no_script_or_external_resource",
        "supported": ["health", "session_create", "session_snapshot", "page_observe", "session_close"],
        "unsupported": ["page_navigate", "page_act", "page_extract", "page_wait"],
        "unsupported_before_durable_admission": True,
        "close_lifecycle": "indeterminate_requires_reconciliation", "close_success": False,
    },
    "qualification": {
        "core_source": QUEUE, "native_source": NATIVE,
        "test_support": "experiments/servo-product-owner/src/approved_test_support.rs",
        "host_kernel": "apps/hepta-browserd/tests/approved_native_startup_kernel.rs",
        "native_target": "experiments/servo-product-owner/src/approved_connected_tests.rs",
        "prepare": "tools/prepare_approved_native_startup.py",
        "validator": "tools/verify_approved_native_startup.py",
        "source_tests": "tests/test_approved_native_startup.py",
        "workflow": ".github/workflows/g2-approved-native-startup.yml",
        "host_completions": "synthetic_source_callbacks_not_servo",
        "native_test_profile": "explicit_root_transient_unit_known_owned_elf_pinned_before_peer_launch",
        "native_case_names": ["actual_approved_startup_semantic_lifecycle",
                              "actual_approved_startup_policy_refusal_before_constructor"],
        "no_missing_capability_skip": True,
    },
    "api_catalog": {
        QUEUE: [
            "ApprovedQueueRetirement::is_requested", "ApprovedQueueRetirement::request",
            "ApprovedRetainedAdmission::cancellation", "ApprovedRetainedAdmission::coordinator",
            "ApprovedRetainedAdmission::deadline", "ApprovedRetainedAdmission::ensure_creating_process",
            "ApprovedRetainedAdmission::from_received",
            "ApprovedRetainedAdmission::serve", "ApprovedRetainedIngress::try_submit",
            "ApprovedRetainedObservation::original_deadline", "ApprovedRetainedObservation::report",
            "ApprovedRetainedObservation::runtime_state", "ApprovedRetainedObservation::service",
            "ApprovedRetainedQueue::try_next", "approved_retained_queue", "approved_retained_queue_before",
        ],
        NATIVE: [
            "ApprovedImmutableNativeStartup::drive", "ApprovedImmutableNativeStartup::next_wake_deadline",
            "ApprovedImmutableNativeStartup::original_deadline", "ApprovedImmutableNativeStartup::retire",
            "ApprovedImmutableNativeStartup::start", "ApprovedImmutableNativeStartup::try_observation",
        ],
    },
    "non_claims": {
        "installed_agentport_enabled": False, "browserd_main_starts_servo": False,
        "production_policy_provisioned": False, "cross_uid_live_identity_broker": False,
        "native_human_input_integrated": False, "headed_or_hardware_qualified": False,
        "all_protocol_network_confinement": False, "signing_or_release": False,
    },
}

# Signatures are independently pinned here; the JSON catalog does not approve
# a different caller-supplied endpoint, detached stream or renewed duration.
SIGNATURES = {
    QUEUE: {
        "ApprovedQueueRetirement::is_requested": "pub fn is_requested(&self) -> Result<bool, ProductDispatchError>",
        "ApprovedQueueRetirement::request": "pub fn request(&self) -> Result<ApprovedQueueRetirementState, ProductDispatchError>",
        "ApprovedRetainedAdmission::cancellation": "pub fn cancellation(&self) -> Result<ProductConnectionCancellation, ProductDispatchError>",
        "ApprovedRetainedAdmission::coordinator": "pub fn coordinator(&self, endpoint: ServoRuntimeEndpoint, journal: ReceiptJournal, image_id: String) -> Result<ProductRequestCoordinator, ProductDispatchError>",
        "ApprovedRetainedAdmission::deadline": "pub fn deadline(&self) -> Result<Instant, ProductDispatchError>",
        "ApprovedRetainedAdmission::ensure_creating_process": "pub fn ensure_creating_process(&self) -> Result<(), ProductDispatchError>",
        "ApprovedRetainedAdmission::from_received": "pub fn from_received(received: ControlRetainedAcceptedStream, selection: ApprovedAgentSelection) -> Result<Self, ProductDispatchError>",
        "ApprovedRetainedAdmission::serve": "pub fn serve(mut self, coordinator: &mut ProductRequestCoordinator) -> Result<ApprovedRetainedObservation, ProductDispatchError>",
        "ApprovedRetainedIngress::try_submit": "pub fn try_submit(&self, mut admission: ApprovedRetainedAdmission) -> Result<ProductConnectionCancellation, ProductDispatchError>",
        "ApprovedRetainedObservation::original_deadline": "pub fn original_deadline(&self) -> Instant",
        "ApprovedRetainedObservation::report": "pub fn report(&self) -> &Result<ProductControlMonitorOutcome, ProductDispatchError>",
        "ApprovedRetainedObservation::runtime_state": "pub fn runtime_state(&self) -> RuntimeState",
        "ApprovedRetainedObservation::service": "pub fn service(&self) -> &Result<ServiceEvidence, ProductDispatchError>",
        "ApprovedRetainedQueue::try_next": "pub fn try_next(&mut self) -> Result<Option<ApprovedRetainedAdmission>, ProductDispatchError>",
        "approved_retained_queue": "pub fn approved_retained_queue() -> (ApprovedRetainedIngress, ApprovedRetainedQueue, ApprovedQueueRetirement)",
        "approved_retained_queue_before": "pub fn approved_retained_queue_before(ceiling: Instant) -> Result<(ApprovedRetainedIngress, ApprovedRetainedQueue, ApprovedQueueRetirement), ProductDispatchError>",
    },
    NATIVE: {
        "ApprovedImmutableNativeStartup::drive": "pub fn drive(&mut self) -> Result<NativeDrive, ProductDispatchError>",
        "ApprovedImmutableNativeStartup::next_wake_deadline": "pub fn next_wake_deadline(&self) -> Result<Instant, ProductDispatchError>",
        "ApprovedImmutableNativeStartup::original_deadline": "pub fn original_deadline(&self) -> Result<Instant, ProductDispatchError>",
        "ApprovedImmutableNativeStartup::retire": "pub fn retire(&mut self) -> Result<ApprovedQueueRetirementState, ProductDispatchError>",
        "ApprovedImmutableNativeStartup::start": "pub fn start(admission: ApprovedRetainedAdmission, servo: Servo, context: Rc<dyn RenderingContext>, waker: Arc<dyn ServoEventLoopWaker>, journal: ReceiptJournal, image_id: String) -> Result<(Self, ApprovedRetainedIngress), ProductDispatchError>",
        "ApprovedImmutableNativeStartup::try_observation": "pub fn try_observation(&mut self) -> Result<Option<Result<ApprovedRetainedObservation, ProductDispatchError>>, ProductDispatchError>",
    },
}
ASSEMBLED_SOURCES = {
    NATIVE: "components/servo/tests/trillionnium_approved_startup.rs",
    "experiments/servo-product-owner/src/approved_test_support.rs": "components/servo/tests/trillionnium_approved_test_support.rs",
    "experiments/servo-product-owner/src/approved_connected_tests.rs": "components/servo/tests/trillionnium_approved_connected.rs",
}
ASSEMBLED_TARGET = (b'\n[[test]]\nname = "trillionnium_approved_connected"\n'
                    b'path = "tests/trillionnium_approved_connected.rs"\nharness = false\n'
                    b'\n[dev-dependencies.libc]\nworkspace = true\n')


def typed_equal(actual, expected, path="contract"):
    if type(actual) is not type(expected):
        raise ValueError(f"{path} exact type differs")
    if isinstance(expected, dict):
        if set(actual) != set(expected):
            raise ValueError(f"{path} unknown or missing fields")
        for key, value in expected.items():
            typed_equal(actual[key], value, path + "." + key)
    elif isinstance(expected, list):
        if len(actual) != len(expected):
            raise ValueError(f"{path} list length differs")
        for index, value in enumerate(expected):
            typed_equal(actual[index], value, f"{path}[{index}]")
    elif actual != expected:
        raise ValueError(f"{path} differs from closed source scope")


def source(root: Path, path: str) -> str:
    value = read(root / path)
    try:
        from .verify_approved_service_runtime import parent_source as service_runtime_parent_source
    except ImportError:
        from verify_approved_service_runtime import parent_source as service_runtime_parent_source
    value = service_runtime_parent_source(path, value.decode("utf-8", "strict")).encode("utf-8")
    if len(value) > MAX_SOURCE_BYTES:
        raise ValueError("composition source exceeds its byte bound")
    return value.decode("utf-8", "strict")


def closing(items, start):
    pairs = {"{": "}", "(": ")", "[": "]"}
    stack = [pairs[items[start]]]
    for index in range(start + 1, len(items)):
        item = items[index]
        if item in pairs:
            stack.append(pairs[item])
        elif item in pairs.values():
            if not stack or item != stack.pop():
                raise ValueError("composition source delimiter differs")
            if not stack:
                return index
    raise ValueError("composition source delimiter is unterminated")


def rust_inventory(text: str):
    """Inventory this finite source profile after stripping comments/literals.

    This is not a generic Rust parser or macro/name-resolution authority.
    Compilation remains required independently of the inventory.
    """
    items = tokens(text)
    functions, public, types = {}, {}, {}

    def walk(start, stop, owner=None):
        index = start
        while index < stop:
            item = items[index]
            if item == "impl":
                opening = items.index("{", index + 1, stop)
                header = items[index + 1:opening]
                context = ("Drop:" + header[header.index("for") + 1]
                           if header[:2] == ["Drop", "for"] else header[0])
                end = closing(items, opening)
                walk(opening + 1, end, context)
                index = end + 1
                continue
            if item == "fn":
                name = items[index + 1]
                opening = items.index("{", index + 2, stop)
                end = closing(items, opening)
                key = (owner + "::" if owner else "") + name
                if key in functions:
                    raise ValueError("duplicate composition function")
                functions[key] = items[opening + 1:end]
                if index and items[index - 1] == "pub":
                    public[key] = " ".join(items[index - 1:opening])
                index = end + 1
                continue
            if item in {"struct", "enum"}:
                name = items[index + 1]
                opening = index + 2
                while items[opening] not in {"{", "(", ";"}:
                    opening += 1
                if items[opening] == ";":
                    end = opening
                    body = []
                else:
                    end = closing(items, opening)
                    body = items[opening + 1:end]
                if name in types:
                    raise ValueError("duplicate composition type")
                types[name] = {"kind": item, "body": body,
                               "public": index > 0 and items[index - 1] == "pub"}
                index = end + 1
                continue
            if item == "{":
                index = closing(items, index) + 1
            else:
                index += 1
    walk(0, len(items))
    return {"tokens": items, "functions": functions, "public_api": public, "types": types}


def require(body, marker, label):
    wanted = tokens(marker)
    for index in range(len(body) - len(wanted) + 1):
        if body[index:index + len(wanted)] == wanted:
            return index
    raise ValueError(f"composition {label} is missing {marker}")


def contains(body, marker):
    wanted = tokens(marker)
    return any(body[index:index + len(wanted)] == wanted
               for index in range(len(body) - len(wanted) + 1))


def signature(value):
    items = tokens(value)
    # An optional trailing comma is formatting, not a different Rust API.
    return [item for index, item in enumerate(items)
            if item != "," or index + 1 == len(items) or items[index + 1] not in {")", ">"}]


def check_catalog(inventory, path):
    if sorted(inventory["public_api"]) != EXPECTED["api_catalog"][path]:
        raise ValueError("composition public API catalog differs")
    for name, expected in SIGNATURES[path].items():
        if signature(inventory["public_api"][name]) != signature(expected):
            raise ValueError(f"composition public API signature differs: {name}")


def ordered(body, markers, label):
    position = -1
    for marker in markers:
        found = require(body[position + 1:], marker, label)
        position += 1 + found


def function(inventory, name):
    try:
        return inventory["functions"][name]
    except KeyError as error:
        raise ValueError(f"composition function absent: {name}") from error


def check_queue(text: str):
    inventory = rust_inventory(text)
    check_catalog(inventory, QUEUE)
    opaque = ["ApprovedRetainedAdmission", "ApprovedRetainedObservation", "ApprovedRetainedIngress",
              "ApprovedRetainedQueue", "ApprovedQueueRetirement"]
    if {name for name, value in inventory["types"].items() if value["public"]} != set(opaque) | {"ApprovedQueueRetirementState"}:
        raise ValueError("composition public type inventory differs")
    for name in opaque:
        entry = inventory["types"].get(name)
        if entry is None or not entry["public"] or "pub" in entry["body"]:
            raise ValueError("approved pair or queue is not opaque")
        items = inventory["tokens"]
        position = next(i for i in range(len(items) - 2)
                        if items[i:i + 3] == ["pub", "struct", name]) - 1
        while position >= 0 and items[position] == "]":
            end = position
            depth = 1
            position -= 1
            while position >= 0 and depth:
                depth += (items[position] == "]") - (items[position] == "[")
                position -= 1
            if "Clone" in items[position + 1:end + 1]:
                raise ValueError("opaque paired custody or queue gains Clone")
            if position >= 0 and items[position] == "#":
                position -= 1
    for forbidden in ["into_parts", "into_inner", "from_parts", "from_snapshot", "from_observation"]:
        if any(name.split("::")[-1] == forbidden for name in inventory["public_api"]):
            raise ValueError("public composition API separates or reconstructs custody")
    items = inventory["tokens"]
    if any(name.startswith("Clone::") for name in inventory["functions"]):
        raise ValueError("composition adds an unregistered Clone implementation")
    if contains(items, "retired.store(false"):
        raise ValueError("composition resets a permanent retirement latch")
    if not contains(function(inventory, "queue_with_ceiling"), "mpsc::sync_channel(1)"):
        raise ValueError("composition queue no longer has fixed capacity one")
    ordered(function(inventory, "approved_retained_queue_before"),
            ["product_time_remaining(ceiling)?", "queue_with_ceiling(Some(ceiling))"], "fixed queue ceiling")
    ordered(function(inventory, "QueueState::current"),
            ["creating(self.owner_pid)?", "product_time_remaining(ceiling)?", "retired.load"], "queue current")
    for body in inventory["functions"].values():
        if contains(body, "Instant::now") or contains(body, "Duration::from_secs"):
            raise ValueError("composition renews an original native deadline")
    ordered(function(inventory, "ApprovedRetainedAdmission::from_received"),
            ["ApprovedRetainedProductConnection::from_received(received, selection)",
             "connection.deadline()?", "connection: Some(connection)", "monitor: Some(monitor)"], "paired admission")
    ordered(function(inventory, "ApprovedRetainedAdmission::deadline"),
            ["creating(self.owner_pid)?", "self.connection", "current != self.original_deadline",
             "product_time_remaining(self.original_deadline)?", "Ok(self.original_deadline)"], "original deadline")
    if function(inventory, "ApprovedRetainedAdmission::ensure_creating_process") != tokens("creating(self.owner_pid)"):
        raise ValueError("creator-only admission check gains other authority")
    ordered(function(inventory, "ApprovedRetainedAdmission::serve"),
            ["self.deadline()?", "coordinator.ensure_owner()?", "self.original_cancellation()?", "queue.activate",
             "self.original_scope()?",
             "self.monitor.take()", "let mut worker = ReportWorker", "worker.receiver = Some(receiver)",
             "self.deadline()?", "thread::Builder::new()", "monitor.run()",
             "self.deadline()", "coordinator.serve_approved_retained_connection", "product_time_remaining(deadline)",
             "worker.receive(remaining.min(Duration::from_millis(5)))?", "drop(worker)"], "paired worker")
    body = function(inventory, "ApprovedRetainedAdmission::serve")
    if "join" in body:
        raise ValueError("composition joins an unbounded native monitor")
    require(body, "mpsc::sync_channel(1)", "one pending monitor result")
    ordered(function(inventory, "ReportWorker::receive"),
            ["creating(self.owner_pid)?", "self.receiver", "recv_timeout(remaining)"], "owned monitor receive")
    ordered(function(inventory, "Drop:ReportWorker::drop"),
            ["creating(self.owner_pid).is_err()", "std::mem::forget(self.receiver.take())",
             "std::mem::forget(self.thread.take())"], "owned monitor fork cleanup")
    ordered(function(inventory, "ApprovedRetainedAdmission::coordinator"),
            ["self.original_scope()?", "ProductRequestCoordinator::from_approved_retained_connection", "self.deadline()?"], "coordinator construction")
    ordered(function(inventory, "ApprovedRetainedIngress::try_submit"),
            ["self.state.current()?", "admission.deadline()?", "deadline > ceiling", "admission.queue.is_some()",
             "admission.original_cancellation()?", "admission.queue = Some(self.state.clone())", "admission.deadline()?", "try_send(admission)"], "bounded admission")
    ordered(function(inventory, "ApprovedRetainedQueue::try_next"),
            ["self.state.current()?", "try_recv()", "Arc::ptr_eq", "admission.deadline()?"], "queue consumption")
    ordered(function(inventory, "QueueState::activate"),
            ["self.current()?", "self.active.try_lock()", "self.current()?", "active.is_some()",
             "*active = Some(cancellation.clone())", "drop(active)", "let guard = ActiveAdmission",
             "self.current()", "try_cancel_original(&guard.cancellation)"], "one active admission")
    ordered(function(inventory, "Drop:ActiveAdmission::drop"),
            ["creating(self.state.owner_pid).is_err()", "return", "self.state.active.try_lock()",
             "Arc::ptr_eq(&value.0, &self.cancellation.0)", "active.take()",
             "self.state.retired.store(true", "try_cancel_original(&self.cancellation)"], "active registration cleanup")
    ordered(function(inventory, "try_cancel_original"),
            ["creating(cancellation.0.owner_pid)?", "cancelled.store(true", "custodian.revoke()", "active.try_lock()", "transport.try_lock()"], "nonblocking denial")
    ordered(function(inventory, "ApprovedQueueRetirement::request"),
            ["creating(self.0.owner_pid)?", "retired.store(true", "active.try_lock()"], "retirement")
    ordered(function(inventory, "ApprovedQueueRetirement::is_requested"),
            ["creating(self.0.owner_pid)?", "retired.load"], "retirement status")
    if inventory["types"]["ApprovedQueueRetirementState"]["body"] != ["Requested", ",", "ActiveCancellationIssued", ","]:
        raise ValueError("composition denial diagnostic enum differs")
    for owner, member in [("ApprovedRetainedIngress", "sender"), ("ApprovedRetainedQueue", "receiver")]:
        ordered(function(inventory, "Drop:" + owner + "::drop"),
                ["creating(self.state.owner_pid).is_err()", f"std::mem::forget(self.{member}.take())"], "fork cleanup")
    for forbidden in ["RetirementBarrier", "CompletedBarrier", "DurableReceiptFact"]:
        if forbidden in items:
            raise ValueError("local queue diagnostics mint effect or terminal authority")
    return inventory


def check_native(text: str):
    inventory = rust_inventory(text)
    check_catalog(inventory, NATIVE)
    if [name for name, value in inventory["types"].items() if value["public"]] != ["ApprovedImmutableNativeStartup"]:
        raise ValueError("native public type inventory differs")
    entry = inventory["types"].get("ApprovedImmutableNativeStartup")
    if entry is None or not entry["public"] or "pub" in entry["body"]:
        raise ValueError("native startup owner state is not opaque")
    for field in ["ClosedImmutableNativeOwner", "ThreadId", "Instant"]:
        if field not in entry["body"]:
            raise ValueError("concrete native owner or original ownership scope missing")
    start = function(inventory, "ApprovedImmutableNativeStartup::start")
    ordered(start, ["if let Err(error) = admission.ensure_creating_process()",
                    "std::mem::forget(servo)", "std::mem::forget(context)", "std::mem::forget(waker)",
                    "return Err(error)", "admission.deadline()?", "approved_retained_queue_before(original_deadline)?",
                    "ingress.try_submit(admission)?", "queue.try_next()?", "first.deadline()?",
                    "ClosedImmutableNativeOwner::new(servo, context, waker)", "first.deadline()?",
                    "thread::Builder::new()", "spawn(move", "first.coordinator(endpoint, journal, image_id)",
                    "admission.serve(&mut coordinator)"], "native owner construction")
    require(start, "creator_thread: thread::current().id()", "native thread binding")
    require(start, "mpsc::sync_channel(1)", "one native observation result")
    ordered(start, ["std::process::id() != creator_pid", "queue.try_next()",
                    "admission.serve(&mut coordinator)", "sender.try_send(result)", "return"], "worker consumption")
    require(start, "value.runtime_state() != RuntimeState::Ready", "worker stop on uncertainty")
    current = function(inventory, "ApprovedImmutableNativeStartup::current_owner")
    ordered(current, ["self.creator_pid != std::process::id()",
                      "self.creator_thread != thread::current().id()"], "creator checks")
    ordered(function(inventory, "ApprovedImmutableNativeStartup::current"),
            ["self.current_owner()?", "self.retirement", "is_requested()?",
             "Instant::now() >= self.original_deadline"], "original native stop")
    ordered(function(inventory, "ApprovedImmutableNativeStartup::original_deadline"),
            ["self.current_owner()?", "Ok(self.original_deadline)"], "native deadline observation")
    ordered(function(inventory, "ApprovedImmutableNativeStartup::try_observation"),
            ["self.current_owner()?", "self.observations", "try_recv()"], "native local diagnostics")
    ordered(function(inventory, "ApprovedImmutableNativeStartup::next_wake_deadline"),
            ["self.current()?", "self.native", "next_wake_deadline()", "value.min(self.original_deadline)"], "wake ceiling")
    ordered(function(inventory, "ApprovedImmutableNativeStartup::drive"),
            ["self.current()", "self.native.as_mut()", "drive()"], "native drive")
    ordered(function(inventory, "ApprovedImmutableNativeStartup::retire"),
            ["self.current_owner()?", "self.retirement", "request()"], "native denial")
    drop = function(inventory, "Drop:ApprovedImmutableNativeStartup::drop")
    ordered(drop, ["self.current_owner().is_err()", "std::mem::forget(self.native.take())",
                   "std::mem::forget(self.retirement.take())", "std::mem::forget(self.observations.take())",
                   "std::mem::forget(self.worker.take())", "return", "self.retire()"], "native child cleanup")
    if "join" in inventory["tokens"]:
        raise ValueError("native startup unbounded worker join")
    for forbidden in ["ServoRuntimeEndpoint", "PageRuntime", "CallbackPageRuntime", "from_snapshot",
                      "PrincipalBinding", "UnixListener", "TcpListener", "read_snapshot"]:
        if forbidden in inventory["tokens"]:
            raise ValueError("native startup accepts alternate endpoint or observed approval")
    return inventory


def check_composition(contract, queue: str, native: str, product: str, native_owner: str):
    """Check source/contract correspondence, without executing a native target."""
    typed_equal(contract, EXPECTED)
    check_queue(queue)
    check_native(native)
    require(tokens(product), "pub const MAX_PRODUCT_CONNECTION_BUDGET: Duration = Duration::from_secs(20);",
            "existing accepted budget")
    require(tokens(native_owner), "pub const OWNER_BUDGET: Duration = Duration::from_secs(5);",
            "existing native budget")
    require(tokens(native_owner), "completion.deadline().min(local_stop)", "native original deadline minimum")


def check_native_target(text: str):
    inventory = rust_inventory(text)
    expected = EXPECTED["qualification"]["native_case_names"]
    actual = sorted(name for name in inventory["functions"]
                    if name.startswith("actual_approved_startup_"))
    if actual != sorted(expected):
        raise ValueError("native target case inventory differs")
    entry = function(inventory, "main")
    require(entry, "support::child_entry()", "retained fixture subprocess entry")
    for name in expected:
        require(entry, name + "()", "native case registration")
    return inventory


def check_prepare(text: str):
    """Bind the finite source assembly inventory; this does not run assembly."""
    try:
        module = ast.parse(text)
        assignments = {}
        for node in module.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in {"SOURCES", "TARGET"}:
                        if target.id in assignments:
                            raise ValueError("duplicate preparation inventory")
                        assignments[target.id] = ast.literal_eval(node.value)
        typed_equal(assignments, {"SOURCES": ASSEMBLED_SOURCES, "TARGET": ASSEMBLED_TARGET}, "prepare")
        function = next(node for node in module.body
                        if isinstance(node, ast.FunctionDef) and node.name == "prepare")
        calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                 and node.func.value.id == "original"]
        prerequisite = [node.lineno for node in calls if node.func.attr == "prepare"]
        writes = [node.lineno for node in calls if node.func.attr == "write_source"]
        if len(prerequisite) != 1 or len(writes) != 2 or min(writes) <= prerequisite[0]:
            raise ValueError("preparation bypasses original PIN assembly")
        locks = [node for node in ast.walk(module) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                 and node.func.value.id == "original" and node.func.attr == "verify_lock"]
        if (len(locks) != 1 or len(locks[0].keywords) != 1
                or locks[0].keywords[0].arg != "approved_startup"
                or not isinstance(locks[0].keywords[0].value, ast.Constant)
                or locks[0].keywords[0].value.value is not True):
            raise ValueError("approved startup precise lock profile differs")
    except (SyntaxError, StopIteration, TypeError) as error:
        raise ValueError("preparation source differs from the closed inventory") from error


def workflow_runs(text: str):
    """Extract only this reviewed literal-block YAML source profile.

    This correspondence check is not a YAML/Bash interpreter. YAML parsing,
    shell validation, exact-pin compilation and actual CI remain separate.
    """
    lines = text.splitlines()
    values = []
    for index, line in enumerate(lines):
        match = re.fullmatch(r"( +)run: \|", line)
        if not match:
            continue
        indentation = len(match[1])
        body = []
        for item in lines[index + 1:]:
            if item.strip() and len(item) - len(item.lstrip()) <= indentation:
                break
            if not item.lstrip().startswith("#"):
                body.append(item[indentation + 2:])
        values.append(" ".join("\n".join(body).replace("\\\n", " ").split()))
    return values


def check_workflow(text: str):
    runs = workflow_runs(text)
    compilation = [body for body in runs if "--test trillionnium_approved_connected" in body]
    command = ("cargo test --locked --profile checked-release -p servo --no-default-features "
               "--features bundled,js_jit --test trillionnium_approved_connected --no-run --message-format=json")
    if len(compilation) != 1 or command not in compilation[0]:
        raise ValueError("workflow actual compile target correspondence differs")
    execution = [body for body in runs if "for test_name in " in body]
    if len(execution) != 1:
        raise ValueError("workflow closed native case loop differs")
    loop = re.search(r"for test_name in (.+?); do\b", execution[0])
    if loop is None or loop[1].split() != EXPECTED["qualification"]["native_case_names"]:
        raise ValueError("workflow native case inventory differs")
    for marker in ['test "$count" = 2', '"$binary" "$test_name" "$unit.service"',
                   "sudo systemd-run --wait --pipe --collect --service-type=exec",
                   "python3 tools/prepare_approved_native_startup.py prepare --upstream servo",
                   "python3 tools/prepare_approved_native_startup.py verify-lock"]:
        if not any(marker in body for body in runs):
            raise ValueError("workflow explicit target invocation correspondence differs")


DIAGNOSTIC_FEATURE = "approved-native-service-error"
DIAGNOSTIC_MODULE = "apps/hepta-browserd/src/approved_native_test_support.rs"


def check_current_service_diagnostic(texts):
    """Own the physical diagnostic profile; old source views do not qualify it."""
    cargo = tomllib.loads(texts["apps/hepta-browserd/Cargo.toml"])
    typed_equal(cargo.get("features"), {DIAGNOSTIC_FEATURE: []}, "diagnostic feature")
    if cargo["package"].get("build") is not False:
        raise ValueError("diagnostic adds a build hook")
    library = texts["apps/hepta-browserd/src/lib.rs"]
    export = ('#[cfg(feature = "approved-native-service-error")]\n'
              'pub mod approved_native_test_support;\n\n')
    if library.count(export) != 1:
        raise ValueError("diagnostic default-off test-support export differs")
    if hashlib.sha256(library.replace(export, "", 1).encode()).hexdigest() != (
            "031e22ca30c47868c04df9c5532578596ecfd53852164e3e6e74132124c023df"):
        raise ValueError("diagnostic changes the original product library")
    product = texts["apps/hepta-browserd/src/product_dispatch.rs"]
    entry = ('        self.ensure_owner()?;\n'
             '        #[cfg(feature = "approved-native-service-error")]\n'
             '        let mut approved_native_service = crate::approved_native_test_support::service_entry();\n')
    capture = ('        drop(trace);\n'
               '        #[cfg(feature = "approved-native-service-error")]\n'
               '        if let Ok(Err(error)) = &result {\n'
               '            approved_native_service.capture(error);\n'
               '        }\n'
               '        match result {\n')
    if product.count(entry) != 1 or product.count(capture) != 1:
        raise ValueError("diagnostic entry/capture placement differs")
    original = product.replace(entry, '        self.ensure_owner()?;\n', 1)
    original = original.replace(capture, '        drop(trace);\n        match result {\n', 1)
    if hashlib.sha256(original.encode()).hexdigest() != (
            "5d7d7c13088095eae123fd8b208211aac9f4d6493413f833ec9436f98820d1b4"):
        raise ValueError("diagnostic changes original authority, drop or result behavior")
    startup = texts[NATIVE]
    enrolled = ('            .spawn(move || {\n'
                '                let _approved_native_actor =\n'
                '                    hepta_browserd::approved_native_test_support::enroll_actor_thread();\n')
    if startup.count(enrolled) != 1:
        raise ValueError("diagnostic actor enrollment differs")
    if hashlib.sha256(startup.replace(enrolled, '            .spawn(move || {\n', 1).encode()).hexdigest() != (
            "582242f4826110a81f26fdec3ad497a2eb1dd76fb20d1e7601d95559b3296b25"):
        raise ValueError("diagnostic changes original startup ownership")
    native = texts[EXPECTED["qualification"]["native_target"]]
    health = '    assert_eq!(string(&health, "runtime"), "actual-servo-immutable-owner");\n'
    arm = health + '    let _ = service_diagnostic::arm_create();\n'
    created = '    let session = string(&created, "session_id").to_owned();\n'
    close = '    service_diagnostic::close_after_success();\n' + created
    sample = ('            service_diagnostic::freeze_create_failure(),\n'
              '            request_marker_at_failure(trio.agent.child.stdout.as_mut())\n')
    for value in [arm, close, sample]:
        if native.count(value) != 1:
            raise ValueError("diagnostic Create/failure association differs")
    original = native.replace(arm, health, 1).replace(close, created, 1)
    original = original.replace(sample, '            request_marker_at_failure(trio.agent.child.stdout.as_mut())\n', 1)
    original = original.replace('    approved_native_test_support as service_diagnostic,\n', '', 1)
    original = original.replace('; server_service_at_failure={}; agent_request_at_failure={}',
                                '; agent_request_at_failure={}', 1)
    if hashlib.sha256(original.encode()).hexdigest() != (
            "21d8ed76607e46feb090b1c96a9f2bf7d83fd03701a7bf3a7a32346b25a53464"):
        raise ValueError("diagnostic changes the original fixture or failure sampler")
    module = texts[DIAGNOSTIC_MODULE]
    production = module.split("#[cfg(test)]", 1)[0]
    inventory = rust_inventory(production)
    public = set(re.findall(r"^pub fn (\w+)\(", production, re.M))
    if public != {"enroll_actor_thread", "arm_create", "freeze_create_failure", "close_after_success"}:
        raise ValueError("diagnostic exposes another qualification entry")
    for forbidden in ("unsafe", "println", "eprintln", "writeln", "print", "write", "flush",
                      "format", "to_string", "Debug", "Display", "clone", "String", "Vec", "Box",
                      "Mutex", "RwLock", "spawn", "sleep", "Instant", "SystemTime", "loop", "while"):
        if forbidden in inventory["tokens"]:
            raise ValueError("diagnostic retains data, adds authority or performs unbounded work")
    required = ["AtomicU8", "Cell", "PhantomData", "Rc", "compare_exchange", "fetch_or", "try_with"]
    for token in required:
        if token not in inventory["tokens"]:
            raise ValueError("diagnostic fixed state or thread scope differs")
    fields = {
        "Recorder": "slot: AtomicU8, enrollment: AtomicU8,",
        "ThreadState": "enrolled: Cell<bool>, in_service: Cell<bool>, invalid: Cell<bool>,",
        "Entry": "owns_scope: bool, eligible: bool,",
        "ActorThreadEnrollment": "owns_scope: bool, not_send_or_sync: PhantomData<Rc<()>> ,",
        "ServiceEntryGuard": "entry: Entry, not_send_or_sync: PhantomData<Rc<()>> ,",
    }
    for name, body in fields.items():
        shape = inventory["types"].get(name)
        if shape is None or shape["kind"] != "struct" or signature(" ".join(shape["body"])) != signature(body):
            raise ValueError("diagnostic retains another state or product resource")
    if '"no-capture-at-sample"' not in production:
        raise ValueError("diagnostic empty observation overclaims service progress")
    prepare = texts[EXPECTED["qualification"]["prepare"]]
    check_prepare(prepare)
    module_ast = ast.parse(prepare)
    feature = [n for n in module_ast.body if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == "DIAGNOSTIC_FEATURE" for t in n.targets)]
    if len(feature) != 1 or ast.literal_eval(feature[0].value) != DIAGNOSTIC_FEATURE:
        raise ValueError("diagnostic assembler feature differs")
    for line in ['qualified = diagnostic_manifest(manifest, root)',
                 'original.write_source(path, qualified + TARGET, manifest)',
                 'if original.read(path) != qualified + TARGET:']:
        if prepare.count(line) != 1:
            raise ValueError("diagnostic assembler does not verify the original dependency edge")


def validate(root: Path = ROOT) -> None:
    # One complete physical snapshot owns the new optional diagnostic. The
    # retained historical contract and its original guards remain unchanged.
    try:
        from . import verify_service_dispatch_denial_cutoff as physical
    except ImportError:
        import verify_service_dispatch_denial_cutoff as physical
    current = physical.inputs(root)
    physical.check(json.loads(current[physical.CONTRACT]), current)
    check_current_service_diagnostic(current)
    # Mandatory actual readiness profile plus exact bounded legacy transfer.
    try:
        from .verify_retained_control_readiness import validate as check_readiness
    except ImportError:
        from verify_retained_control_readiness import validate as check_readiness
    check_readiness(root)
    check_composition(load(root / CONTRACT), source(root, QUEUE), source(root, NATIVE),
                      source(root, "apps/hepta-browserd/src/product_dispatch.rs"),
                      source(root, "experiments/servo-product-owner/src/native_owner.rs"))
    # The additive private-scope profile pins the inexpensive root/pidfd gate
    # and unchanged full checks at all externally effective boundaries.
    try:
        from .verify_approved_composition_scope import validate as check_private_scope
    except ImportError:
        from verify_approved_composition_scope import validate as check_private_scope
    check_private_scope(root)
    # The sole opaque approved wrapper retains its complete pre-constructor
    # readback; only its adjacent private repeated check uses the denial gate.
    try:
        from .verify_approved_constructor_route import validate as check_constructor_route
    except ImportError:
        from verify_approved_constructor_route import validate as check_constructor_route
    check_constructor_route(root)
    approved = tokens(source(root, "apps/hepta-browserd/src/product_dispatch/product_approved_policy.rs"))
    ordered(approved, ["selection.admit_retained(received)", "consume_with_request_binding", "ProcfsPeerAttestor::default()",
                       "connection.ensure_control_current()?"], "existing approved live admission")
    binding = rust_inventory(source(root, "crates/hepta-peer-attestation/src/approved_policy/request_binding.rs"))
    consume_binding = function(binding, "ApprovedAgentReceivedStream::consume_with_request_binding")
    ordered(consume_binding,
            ["self.attested.request_custody()", "self.custody.verifier()",
             "PeerIdentity::from_stream(&self.stream)", "self.consume_before"],
            "same original approved custody delegation")
    expected_binding = "pub fn consume_with_request_binding<T>(self, consumer: impl FnOnce(UnixStream, Instant, ControlRequestCustody, AttestedRetainedReceiver, AttestedPeer, &str, ApprovedAgentRequestBinding) -> T) -> Result<T, ApprovedPolicyError>"
    if signature(binding["public_api"]["ApprovedAgentReceivedStream::consume_with_request_binding"]) != signature(expected_binding):
        raise ValueError("opaque original seven-argument consumption signature differs")
    if consume_binding.count("consume_before") != 1 or consume_binding.count("consumer") != 1:
        raise ValueError("opaque original consumption must delegate/invoke exactly once")
    for marker in ["self.guard.state.inspect()?", "remaining(self.guard.state.pid, self.deadline)?",
                   "owner_pid: self.guard.state.pid", "deadline: self.deadline", "guard: self.guard.clone()",
                   "peer.pid != Some(snapshot.pid)", "peer.uid != snapshot.uid", "peer.gid != snapshot.gid",
                   "consumer(stream, deadline, custody, retained, attested, principal, binding)"]:
        require(signature(" ".join(consume_binding)), marker, "original opaque pair and absolute ceiling")
    exports = tokens(source(root, "apps/hepta-browserd/src/lib.rs"))
    for name in ["ApprovedRetainedAdmission", "ApprovedRetainedIngress", "ApprovedRetainedQueue",
                 "ApprovedQueueRetirement", "approved_retained_queue_before"]:
        require(exports, name, "public library composition export")
    check_native_target(source(root, EXPECTED["qualification"]["native_target"]))
    check_prepare(source(root, EXPECTED["qualification"]["prepare"]))
    check_workflow(source(root, EXPECTED["qualification"]["workflow"]))
    # Presence is source inventory only. Exact-pin prepare/compile/execution are
    # separate gates; names and files never mean a target was actually run.
    for key in ["test_support", "host_kernel", "prepare", "workflow", "source_tests", "validator"]:
        source(root, EXPECTED["qualification"][key])


def main() -> int:
    try:
        validate()
    except (ValueError, OSError) as error:
        print(f"approved native startup source validation failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"source_contract": "PASS", "public_api_count": 22,
                      "actual_servo_execution": "PENDING", "installed_activation": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
