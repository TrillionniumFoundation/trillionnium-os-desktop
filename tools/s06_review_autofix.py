#!/usr/bin/env python3
"""One-shot hardening for the reconstructed S06 BrowserActor slice."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"duplicate JSON key: {key}")
        output[key] = value
    return output


def reject_constant(value: str) -> Any:
    raise ValueError(f"non-JSON constant: {value}")


def load_json(path: str) -> dict[str, Any]:
    value = json.loads(
        (ROOT / path).read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicate,
        parse_constant=reject_constant,
    )
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def write_json(path: str, value: dict[str, Any]) -> None:
    (ROOT / path).write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def write_product_wrapper() -> None:
    source = r'''#![forbid(unsafe_code)]

//! Product-facing BrowserActor authority boundary.
//!
//! Construction and every request require an opaque, pidfd-backed
//! [`AttestedPeer`]. S06 deliberately exposes no caller-supplied runtime trait,
//! runtime value, generic actor parameter, ordinary handler, listener, or
//! installable binary. A future Servo adapter must be introduced as a distinct
//! concrete reviewed product type in a later gate.
//!
//! Caller-constructed principal/mechanism bindings are not part of this API:
//!
//! ```compile_fail
//! use hepta_browser_actor::PrincipalBinding;
//! ```
//!
//! Arbitrary runtime injection is not representable:
//!
//! ```compile_fail
//! use hepta_browser_actor::BrowserActor;
//! struct ForgedRuntime;
//! fn accepts_forged_runtime(_: BrowserActor<ForgedRuntime>) {}
//! ```
//!
//! The product actor deliberately does not implement the ordinary, weaker
//! `BrowserRequestHandler` compatibility trait:
//!
//! ```compile_fail
//! use hepta_agent_port::BrowserRequestHandler;
//! use hepta_browser_actor::BrowserActor;
//! fn require_ordinary_handler<T: BrowserRequestHandler>() {}
//! require_ordinary_handler::<BrowserActor>();
//! ```

use hepta_browser_actor_simulation as simulation;

pub use hepta_agent_port::{AgentPortError, DispatchContext, HandlerOutcome};
pub use hepta_agent_transport::PeerIdentity;
pub use hepta_browser_codec::{
    BrowserRequest, BrowserResponse, ElementReference, JsonObject, JsonValue, NavigationTarget,
    ObservationField, PageAction, ProfilePersistence, ProfileSpec, WaitCondition,
};
pub use hepta_peer_attestation::{AttestedPeer, ProcfsPeerAttestor};
pub use hepta_session_core::{ReceiptJournal, SessionEvent, TransitionError};
pub use simulation::{
    CancellationToken, PageOwnerSnapshot, ReceiptLifecycleObserver, TaskFlowPrincipal,
    executable_sha256, scoped_frame_id,
};

/// The only S06 product-facing BrowserActor.
///
/// The actor owns the only runtime type admitted by this source gate. Callers
/// cannot supply a trait implementation that ignores request custody or starts
/// deferred work after a terminal result. The deterministic runtime has no
/// external-network/effect authority; later engine adapters require a separate
/// concrete type, review, and promotion gate.
pub struct BrowserActor {
    inner: simulation::BrowserActor<simulation::DeterministicLocalRuntime>,
}

impl BrowserActor {
    /// Construct an actor from a live opaque attestation object.
    ///
    /// A caller-provided PID/UID/GID tuple alone is insufficient. The attested
    /// process start time, cgroup, systemd unit, and executable digest are read
    /// from the attestor-selected source and bound into the private mechanism.
    /// The local runtime is created inside the actor and cannot be substituted.
    pub fn from_attested(
        principal: TaskFlowPrincipal,
        peer: PeerIdentity,
        attestor: &ProcfsPeerAttestor,
        attested: &AttestedPeer,
    ) -> Result<Self, AgentPortError> {
        let snapshot = attested.refresh_snapshot(attestor).map_err(|error| {
            AgentPortError::Handler(format!("peer attestation refresh failed: {error}"))
        })?;
        let binding = simulation::PrincipalBinding::bind_attested(principal, peer, &snapshot)
            .map_err(|error| {
                AgentPortError::Handler(format!("principal binding failed: {error}"))
            })?;
        Ok(Self {
            inner: simulation::BrowserActor::new(
                binding,
                simulation::DeterministicLocalRuntime::default(),
            ),
        })
    }

    /// Dispatch exactly one request while retaining request-scoped peer custody.
    pub fn handle_attested(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
        attestor: &ProcfsPeerAttestor,
        attested: &AttestedPeer,
    ) -> Result<HandlerOutcome, AgentPortError> {
        self.inner
            .handle_attested(context, request, attestor, attested)
    }

    /// Return the semantic principal; mechanism identity remains private.
    pub fn principal(&self) -> &TaskFlowPrincipal {
        self.inner.principal_binding().principal()
    }

    /// Return the bounded current PageOwner snapshot, if a session exists.
    pub fn page_owner(&self) -> Option<PageOwnerSnapshot> {
        self.inner.page_owner()
    }

    /// Request cancellation for one actor-owned request identity.
    pub fn cancel_request(&mut self, request_id: impl Into<String>) {
        self.inner.cancel_request(request_id);
    }

    /// Create or retrieve the shared cancellation token for one request.
    pub fn cancellation_token(&mut self, request_id: impl Into<String>) -> CancellationToken {
        self.inner.cancellation_token(request_id)
    }

    /// Return an existing active cancellation token without creating authority.
    pub fn active_cancellation_token(&self, request_id: &str) -> Option<CancellationToken> {
        self.inner.active_cancellation_token(request_id)
    }

    /// Apply one explicit session state-machine event.
    pub fn apply_session_event(
        &mut self,
        event: SessionEvent,
        now_ms: u64,
    ) -> Result<(), TransitionError> {
        self.inner.apply_session_event(event, now_ms)
    }

    /// Create a receipt observer. Receipt facts never authorize execution.
    pub fn receipt_observer(
        &self,
        journal: ReceiptJournal,
        image_id: impl Into<String>,
    ) -> ReceiptLifecycleObserver {
        self.inner.receipt_observer(journal, image_id)
    }
}
'''
    (ROOT / "crates/hepta-browser-actor/src/lib.rs").write_text(source, encoding="utf-8")

    readme = r'''# hepta-browser-actor

**Module registry ID:** `hepta-browser-actor`
**Workspace path:** `crates/hepta-browser-actor`
**Owner class:** browser-runtime-security

This crate is the narrow product-facing authority wrapper for one PageOwner and
BrowserActor. It makes the attested entry path the only public request path.

## Authority inputs

Construction requires a semantic `TaskFlowPrincipal`, the kernel-derived
`PeerIdentity`, an opaque pidfd-backed `AttestedPeer`, and the same
`ProcfsPeerAttestor` source used for refresh. A caller-written
`MechanismIdentity`, `PrincipalBinding`, runtime trait, or runtime value is not
accepted or exported.

## Actor-owned runtime boundary

S06 exposes a non-generic `BrowserActor`. `from_attested` constructs the bounded
deterministic local runtime internally. Callers cannot provide a `PageRuntime`
implementation that skips `RequestControl`, hides deferred work, or reports a
terminal success while retaining effect authority. This runtime has no external
HTTPS, trusted-app, listener, installation, or production-effect authority.

A later Servo product adapter must be a distinct concrete reviewed type with its
own exact-pin, custody, callback, crash, and image evidence. It must not reopen a
generic public runtime injection point.

## Request path

Every product request calls `handle_attested`. The implementation checks the
original deadline, verifies peer/start-time continuity, creates one
request-scoped custody owner, propagates its verifier through internal queue and
callback controls, rechecks custody before terminal classification, and drops
custody on return or unwind. Stale custody fails before work or becomes
indeterminate after a possible effect.

The wrapper does not implement `BrowserRequestHandler`, has no ordinary `handle`
method, and does not export the internal mechanism identity or simulation
runtime traits.

## Failure and receipt semantics

Deadline, cancellation, callback loss, panic, browser crash, peer drift, and
receipt failure are fail-closed. Potential external effects are never
automatically replayed. Receipt entries are lifecycle facts, not execution
authority.

## Claim ceiling

This module establishes only a source/test product API with structurally
mandatory attested custody and an actor-owned local fixture runtime. It does not
establish a listener, product activation, Servo adapter, installed image,
physical hardware, signing, publication, or release readiness.
'''
    (ROOT / "crates/hepta-browser-actor/README.md").write_text(readme, encoding="utf-8")


def harden_contracts() -> None:
    actor = load_json("contracts/browser-actor.v1.json")
    authority = actor["authority_boundary"]
    authority.update(
        {
            "product_actor_generic_over_runtime": False,
            "caller_supplied_runtime_adapter": False,
            "runtime_trait_publicly_exported": False,
            "request_control_publicly_exported": False,
            "product_runtime_type": "actor_owned_deterministic_local_runtime",
            "deferred_work_after_terminal_success_representable": False,
        }
    )
    browser_actor = actor["browser_actor"]
    browser_actor.update(
        {
            "product_runtime_construction": "inside_from_attested",
            "generic_runtime_injection": False,
            "later_servo_adapter_requires_distinct_concrete_reviewed_type": True,
        }
    )
    actor["claim_ceiling"]["caller_supplied_runtime_authority"] = False
    write_json("contracts/browser-actor.v1.json", actor)

    engine = load_json("contracts/engine-thread-dispatch.v1.json")
    engine["implementation"] = (
        "crates/hepta-browser-actor-simulation/src/engine_dispatch.rs"
    )
    engine["required_sources"] = [
        "crates/hepta-browser-actor-simulation/src/engine_dispatch.rs",
        "crates/hepta-browser-actor-simulation/src/engine_dispatch/tests.rs",
        "crates/hepta-browser-actor-simulation/src/engine_dispatch/transport_tests.rs",
        "crates/hepta-browser-actor-simulation/src/engine_dispatch/authority_tests.rs",
    ]
    engine["required_document"] = "docs/architecture/ENGINE_THREAD_DISPATCH.md"
    engine["required_workflow"] = ".github/workflows/s06-browser-actor.yml"
    engine["tests"] = {
        "rust": (
            "cargo test --locked -p hepta-browser-actor-simulation "
            "engine_dispatch"
        ),
        "product_rustdoc": "cargo test --locked -p hepta-browser-actor --doc",
        "python": "tests/test_s06_contract_paths.py",
    }
    engine["development_daemon_switched"] = False
    write_json("contracts/engine-thread-dispatch.v1.json", engine)

    event_loop = load_json("contracts/event-loop-completion.v1.json")
    event_loop["required_sources"] = [
        "crates/hepta-browser-actor-simulation/src/engine_dispatch.rs",
        "crates/hepta-browser-actor-simulation/src/engine_dispatch/event_loop.rs",
        "crates/hepta-browser-actor-simulation/src/engine_dispatch/event_loop_tests.rs",
        "crates/hepta-browser-actor-simulation/src/engine_dispatch/event_loop_transport_tests.rs",
        "crates/hepta-browser-actor-simulation/src/engine_dispatch/immediate_callbacks.rs",
    ]
    event_loop["document"] = "docs/architecture/EVENT_LOOP_COMPLETION.md"
    event_loop["required_workflow"] = ".github/workflows/s06-browser-actor.yml"
    event_loop["tests"] = {
        "rust": (
            "cargo test --locked -p hepta-browser-actor-simulation "
            "engine_dispatch::event_loop"
        ),
        "python": "tests/test_s06_contract_paths.py",
    }
    write_json("contracts/event-loop-completion.v1.json", event_loop)


def write_architecture_documents() -> None:
    engine = r'''# Engine-thread dispatch boundary

Status: **S06 source/test candidate; no native Servo or installed runtime**

## Purpose

The internal simulation crate models one bounded in-process request/reply pair
between BrowserActor ownership and an engine-thread owner. It exists to prove
queue, deadline, cancellation, callback, cleanup, and custody semantics before a
real engine adapter is admitted.

## Ownership and limits

`engine_thread_pair` creates one non-cloneable client and one non-`Send`,
non-`Sync` owner. The queue and reply capacity are one. A preflight failure does
not enqueue. Queue-full, abandonment, endpoint loss, deadline, cancellation, or
identity revocation permanently closes the affected pair; a late result cannot
be reused by another request.

## Custody

The product wrapper does not expose this transport or its `PageRuntime` trait.
S06 constructs only an actor-owned deterministic local runtime. Internal
`RequestControl` checks deadline, cancellation and request-scoped peer custody at
bounded points. Future Servo integration must use a distinct concrete reviewed
adapter and preserve the same original request authority across engine entry,
callback completion and terminal response classification.

## Failure and effect semantics

Generic page action is unsupported. Semantic resolve-and-act remains one
runtime-owned atomic hook. A crash or post-dispatch uncertainty cannot be
converted to empty success and a potentially started effect is never
automatically replayed.

## Evidence and claim ceiling

Required source paths are recorded in
`contracts/engine-thread-dispatch.v1.json` and mechanically resolved by
`tests/test_s06_contract_paths.py`. Host tests do not establish Servo, native
event-loop latency, process IPC, installed-image behavior, hardware, signing or
release authority.
'''
    (ROOT / "docs/architecture/ENGINE_THREAD_DISPATCH.md").write_text(
        engine, encoding="utf-8"
    )

    event = r'''# Event-loop completion boundary

Status: **S06 callback fixture candidate; no native engine event loop**

## Purpose

The callback completion model separates enqueue acceptance from terminal engine
completion. `EngineCompletion` is single-use and non-cloneable. Queueing is not
execution and is never durable success.

## State and wakeups

The model permits one queued request, one active call and one completion. The
owner does not block waiting for a callback. Request enqueue, abandonment,
endpoint drop, callback result and callback drop wake the state machine.
Cancellation, deadline and request-custody checks use the original monotonic
request boundary and cannot be reset by a callback.

## Terminal classification

A dropped callback is a browser crash, not success. Retirement invalidates the
pending operation and performs cleanup at most once. Before a final reply the
actor rechecks request-scoped identity; uncertainty after a possible effect is
reported as indeterminate and is never automatically replayed.

## Product boundary

The product crate does not export the callback backend trait or accept a generic
runtime. The S06 product actor owns only the deterministic local fixture runtime.
A native Servo event loop requires a later concrete reviewed adapter, exact-pin
behavior evidence and installed-image qualification.

## Evidence and claim ceiling

Required source and document paths are recorded in
`contracts/event-loop-completion.v1.json` and mechanically checked. This source
model proves no process IPC, native event-loop latency, product listener,
external-effect authority, installed image, hardware, signing or release.
'''
    (ROOT / "docs/architecture/EVENT_LOOP_COMPLETION.md").write_text(
        event, encoding="utf-8"
    )


def write_contract_path_tests() -> None:
    source = r'''from __future__ import annotations

import copy
import json
from pathlib import Path, PurePosixPath
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = (
    "contracts/engine-thread-dispatch.v1.json",
    "contracts/event-loop-completion.v1.json",
)
PATH_FIELDS = (
    "implementation",
    "required_sources",
    "required_document",
    "document",
    "required_workflow",
)


def reject_duplicate(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"duplicate JSON key: {key}")
        output[key] = value
    return output


def reject_constant(value):
    raise ValueError(f"non-JSON constant: {value}")


def load_contract(relative: str) -> dict:
    value = json.loads(
        (ROOT / relative).read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicate,
        parse_constant=reject_constant,
    )
    if not isinstance(value, dict):
        raise ValueError(f"{relative} is not an object")
    return value


def required_paths(contract: dict) -> list[str]:
    output: list[str] = []
    for field in PATH_FIELDS:
        value = contract.get(field)
        if value is None:
            continue
        if isinstance(value, str):
            output.append(value)
        elif isinstance(value, list) and all(isinstance(item, str) for item in value):
            output.extend(value)
        else:
            raise ValueError(f"{field} must be a path or path list")
    return output


def path_errors(contract: dict) -> list[str]:
    errors: list[str] = []
    try:
        paths = required_paths(contract)
    except ValueError as error:
        return [str(error)]
    for value in paths:
        parsed = PurePosixPath(value)
        if (
            not value
            or value != value.strip()
            or parsed.is_absolute()
            or parsed.as_posix() != value
            or any(part in {"", ".", ".."} for part in parsed.parts)
            or "\\" in value
        ):
            errors.append(f"unsafe path: {value!r}")
            continue
        target = ROOT.joinpath(*parsed.parts)
        if not target.is_file():
            errors.append(f"missing required file: {value}")
    return errors


class S06ContractPathTests(unittest.TestCase):
    def test_every_declared_required_path_resolves(self) -> None:
        for relative in CONTRACTS:
            with self.subTest(contract=relative):
                contract = load_contract(relative)
                self.assertFalse(path_errors(contract), path_errors(contract))

    def test_paths_bind_the_internal_simulation_crate(self) -> None:
        engine = load_contract(CONTRACTS[0])
        event = load_contract(CONTRACTS[1])
        self.assertTrue(
            engine["implementation"].startswith(
                "crates/hepta-browser-actor-simulation/"
            )
        )
        for contract in (engine, event):
            for source in contract["required_sources"]:
                self.assertTrue(
                    source.startswith("crates/hepta-browser-actor-simulation/"),
                    source,
                )

    def test_missing_traversal_absolute_and_wrong_type_mutations_fail(self) -> None:
        baseline = load_contract(CONTRACTS[0])
        mutations = []
        for value in (
            "does/not/exist.rs",
            "../outside.rs",
            "/tmp/outside.rs",
            "crates\\outside.rs",
        ):
            candidate = copy.deepcopy(baseline)
            candidate["implementation"] = value
            mutations.append(candidate)
        candidate = copy.deepcopy(baseline)
        candidate["required_sources"] = {"path": "not-a-list"}
        mutations.append(candidate)
        for candidate in mutations:
            with self.subTest(candidate=candidate.get("implementation")):
                self.assertTrue(path_errors(candidate))

    def test_product_contract_closes_generic_runtime_injection(self) -> None:
        contract = load_contract("contracts/browser-actor.v1.json")
        authority = contract["authority_boundary"]
        actor = contract["browser_actor"]
        self.assertFalse(authority["product_actor_generic_over_runtime"])
        self.assertFalse(authority["caller_supplied_runtime_adapter"])
        self.assertFalse(authority["runtime_trait_publicly_exported"])
        self.assertFalse(authority["request_control_publicly_exported"])
        self.assertFalse(
            authority["deferred_work_after_terminal_success_representable"]
        )
        self.assertEqual(
            authority["product_runtime_type"],
            "actor_owned_deterministic_local_runtime",
        )
        self.assertFalse(actor["generic_runtime_injection"])
        self.assertTrue(
            actor["later_servo_adapter_requires_distinct_concrete_reviewed_type"]
        )


if __name__ == "__main__":
    unittest.main()
'''
    (ROOT / "tests/test_s06_contract_paths.py").write_text(source, encoding="utf-8")


def write_authority_tests() -> None:
    source = r'''from __future__ import annotations

import json
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_MEMBERS = [
    "apps/hepta-browserd",
    "apps/hepta-agent-portd",
    "crates/hepta-agent-transport",
    "crates/hepta-browser-codec",
    "crates/hepta-agent-port",
    "crates/hepta-peer-attestation",
    "crates/trillionnium-contract-core",
    "crates/hepta-browser-contracts",
    "crates/hepta-session-core",
    "crates/hepta-workspace-composition",
    "crates/hepta-browser-actor",
    "crates/hepta-browser-actor-simulation",
]


def load_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def direct_dependency_names(manifest: dict) -> set[str]:
    names: set[str] = set()
    for section in ("dependencies", "dev-dependencies", "build-dependencies"):
        names.update(manifest.get(section, {}))
    for target in manifest.get("target", {}).values():
        for section in ("dependencies", "dev-dependencies", "build-dependencies"):
            names.update(target.get(section, {}))
    return names


class BrowserActorAuthorityBoundaryTests(unittest.TestCase):
    def test_workspace_and_machine_source_state_match_exactly(self) -> None:
        workspace = load_toml(ROOT / "Cargo.toml")["workspace"]
        self.assertEqual(workspace["members"], EXPECTED_MEMBERS)
        self.assertEqual(workspace["default-members"], EXPECTED_MEMBERS)
        source_state = json.loads(
            (ROOT / "docs/source-state.v1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(source_state["schema"], "trillionnium.desktop.source-state.v1")
        self.assertEqual(source_state["workspace_members"], EXPECTED_MEMBERS)
        self.assertEqual(source_state["claim_ceiling"], "repository_source_tree_only")

    def test_only_product_wrapper_directly_depends_on_simulation_crate(self) -> None:
        dependents = []
        manifests = sorted((ROOT / "apps").glob("*/Cargo.toml")) + sorted(
            (ROOT / "crates").glob("*/Cargo.toml")
        )
        for path in manifests:
            if "hepta-browser-actor-simulation" in direct_dependency_names(load_toml(path)):
                dependents.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(dependents, ["crates/hepta-browser-actor/Cargo.toml"])
        simulation = load_toml(
            ROOT / "crates/hepta-browser-actor-simulation/Cargo.toml"
        )
        self.assertFalse(simulation["package"]["publish"])
        self.assertFalse(simulation["lib"]["doctest"])

    def test_product_api_has_no_generic_or_caller_supplied_runtime(self) -> None:
        source = (ROOT / "crates/hepta-browser-actor/src/lib.rs").read_text(
            encoding="utf-8"
        )
        for required in (
            "pub struct BrowserActor {",
            "pub fn from_attested(",
            "pub fn handle_attested(",
            "attested.refresh_snapshot(attestor)",
            "simulation::PrincipalBinding::bind_attested",
            "simulation::DeterministicLocalRuntime::default()",
            ".handle_attested(context, request, attestor, attested)",
        ):
            self.assertIn(required, source)
        for forbidden in (
            "pub struct BrowserActor<",
            "impl<R: PageRuntime>",
            "runtime: R",
            "PageRuntime,",
            "RequestControl,",
            "RuntimeReply,",
            "pub fn new(",
            "BrowserRequestHandler for BrowserActor",
            "pub use hepta_browser_actor_simulation::PrincipalBinding",
            "pub type PrincipalBinding",
            "pub use hepta_browser_actor_simulation::MechanismIdentity",
            "pub type MechanismIdentity",
            "std::thread",
            "tokio::spawn",
        ):
            self.assertNotIn(forbidden, source)
        self.assertGreaterEqual(source.count("```compile_fail"), 3)

    def test_closed_contract_requires_attestation_custody_and_owned_runtime(self) -> None:
        contract = json.loads(
            (ROOT / "contracts/browser-actor.v1.json").read_text(encoding="utf-8")
        )
        authority = contract["authority_boundary"]
        self.assertEqual(authority["product_crate"], "hepta-browser-actor")
        self.assertEqual(
            authority["implementation_crate"], "hepta-browser-actor-simulation"
        )
        self.assertFalse(authority["implementation_crate_published"])
        self.assertTrue(
            authority["only_product_wrapper_may_depend_directly_on_implementation"]
        )
        self.assertFalse(authority["caller_constructed_mechanism_identity_publicly_exported"])
        self.assertFalse(authority["principal_binding_publicly_exported"])
        self.assertFalse(authority["ordinary_browser_request_handler_implemented"])
        self.assertFalse(authority["ordinary_handle_method_exported"])
        self.assertTrue(authority["construction_requires_attested_peer"])
        self.assertTrue(authority["every_dispatch_requires_attested_peer"])
        self.assertTrue(authority["request_scoped_custody_required"])
        self.assertFalse(authority["simulation_api_is_product_authority"])
        self.assertFalse(authority["product_actor_generic_over_runtime"])
        self.assertFalse(authority["caller_supplied_runtime_adapter"])
        self.assertFalse(authority["runtime_trait_publicly_exported"])
        self.assertFalse(authority["request_control_publicly_exported"])
        self.assertFalse(authority["deferred_work_after_terminal_success_representable"])
        self.assertEqual(
            contract["principal_binding"]["source"],
            "opaque_AttestedPeer_refresh_only",
        )
        self.assertTrue(
            contract["browser_actor"]["request_authority_carried_through_runtime_control"]
        )
        self.assertTrue(
            contract["browser_actor"]["final_success_released_after_peer_revalidation"]
        )
        self.assertFalse(contract["browser_actor"]["generic_runtime_injection"])
        self.assertFalse(contract["receipts"]["journal_authorizes_execution"])
        self.assertFalse(contract["receipts"]["journal_automatically_replays_operations"])
        self.assertFalse(contract["activation"]["product_agent_port_enabled"])
        self.assertFalse(contract["activation"]["production_release_authorized"])

    def test_actor_crates_create_no_listener_or_installable_binary(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for crate in (
                ROOT / "crates/hepta-browser-actor",
                ROOT / "crates/hepta-browser-actor-simulation",
            )
            for path in sorted((crate / "src").rglob("*.rs"))
        )
        self.assertNotIn("TcpListener", source)
        self.assertNotIn("UnixListener", source)
        for crate_name in ("hepta-browser-actor", "hepta-browser-actor-simulation"):
            manifest = load_toml(ROOT / f"crates/{crate_name}/Cargo.toml")
            self.assertFalse(manifest["package"]["autobins"])
            self.assertFalse(manifest["package"]["build"])
            self.assertFalse(manifest["package"]["publish"])

    def test_authority_boundary_is_documented(self) -> None:
        wrapper = (ROOT / "crates/hepta-browser-actor/README.md").read_text(
            encoding="utf-8"
        )
        simulation = (
            ROOT / "crates/hepta-browser-actor-simulation/README.md"
        ).read_text(encoding="utf-8")
        architecture = (
            ROOT / "docs/architecture/BROWSER_ACTOR_AUTHORITY_BOUNDARY.md"
        ).read_text(encoding="utf-8")
        for text in (wrapper, architecture):
            self.assertIn("AttestedPeer", text)
            self.assertIn("request", text.lower())
            self.assertIn("custody", text.lower())
            self.assertIn("BrowserRequestHandler", text)
        self.assertIn("actor-owned", wrapper)
        self.assertIn("implementation-internal", simulation)
        self.assertIn("not a product entry point", simulation)


if __name__ == "__main__":
    unittest.main()
'''
    (ROOT / "tests/test_s06_browser_actor.py").write_text(source, encoding="utf-8")


def normalize_changed_markdown() -> None:
    for path in (
        ROOT / "crates/hepta-browser-actor/README.md",
        ROOT / "crates/hepta-browser-actor-simulation/README.md",
        ROOT / "docs/architecture/BROWSER_ACTOR_AUTHORITY_BOUNDARY.md",
        ROOT / "docs/architecture/ENGINE_THREAD_DISPATCH.md",
        ROOT / "docs/architecture/EVENT_LOOP_COMPLETION.md",
    ):
        if path.is_file():
            lines = [line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    write_product_wrapper()
    harden_contracts()
    write_architecture_documents()
    write_contract_path_tests()
    write_authority_tests()
    normalize_changed_markdown()


if __name__ == "__main__":
    main()
