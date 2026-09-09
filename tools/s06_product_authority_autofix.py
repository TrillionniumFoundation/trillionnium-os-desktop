#!/usr/bin/env python3
"""Close the reviewed S06 raw session-state authority surface."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def patch_wrapper() -> None:
    path = ROOT / "crates/hepta-browser-actor/src/lib.rs"
    text = path.read_text(encoding="utf-8")

    insertion = r'''//!
//! Raw session-state synthesis is not part of the product API. If both the
//! generic event type and the untrusted mutator were ever reintroduced, this
//! compile-fail guard would unexpectedly compile:
//!
//! ```compile_fail
//! use hepta_browser_actor::{BrowserActor, SessionEvent};
//! fn forge_state(actor: &mut BrowserActor, event: SessionEvent) {
//!     actor.apply_session_event(event, 0).unwrap();
//! }
//! ```
'''
    anchor = '''//! ```compile_fail
//! use hepta_browser_actor::PrincipalBinding;
//! ```
'''
    text = replace_once(text, anchor, anchor + insertion, "state-ingress compile-fail guard")
    text = replace_once(
        text,
        "pub use hepta_session_core::{ReceiptJournal, SessionEvent, TransitionError};",
        "pub use hepta_session_core::ReceiptJournal;",
        "session-core public surface",
    )
    method = '''    /// Apply one explicit session state-machine event.
    pub fn apply_session_event(
        &mut self,
        event: SessionEvent,
        now_ms: u64,
    ) -> Result<(), TransitionError> {
        self.inner.apply_session_event(event, now_ms)
    }

'''
    text = replace_once(text, method, "", "raw state mutator")
    path.write_text(text, encoding="utf-8")


def patch_contract() -> None:
    path = ROOT / "contracts/browser-actor.v1.json"
    contract = json.loads(path.read_text(encoding="utf-8"))
    authority = contract["authority_boundary"]
    authority.update(
        {
            "raw_session_event_type_publicly_exported": False,
            "unauthenticated_session_event_mutation_publicly_exported": False,
            "authority_changing_state_requires_attested_request": True,
            "cancellation_helpers_are_revocation_only": True,
        }
    )
    actor = contract["browser_actor"]
    actor.update(
        {
            "generic_session_event_ingress": False,
            "product_state_transition_entry": "handle_attested_request_only",
            "caller_can_release_human_or_ime_control": False,
            "caller_can_resolve_capability_or_recovery": False,
            "caller_can_synthesize_navigation_completion": False,
            "unauthenticated_helpers_can_only_revoke_or_observe": True,
        }
    )
    contract["claim_ceiling"]["raw_product_state_mutation_authority"] = False
    path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")


def patch_tests() -> None:
    path = ROOT / "tests/test_s06_browser_actor.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '            "RuntimeReply,",\n',
        '            "RuntimeReply,",\n'
        '            "pub use hepta_session_core::{ReceiptJournal, SessionEvent",\n'
        '            "pub fn apply_session_event(",\n'
        '            ".apply_session_event(event, now_ms)",\n',
        "API forbidden surface",
    )
    text = replace_once(
        text,
        '        self.assertGreaterEqual(source.count("```compile_fail"), 3)\n',
        '        self.assertGreaterEqual(source.count("```compile_fail"), 4)\n',
        "compile-fail count",
    )
    contract_anchor = '''        self.assertFalse(authority["deferred_work_after_terminal_success_representable"])
'''
    contract_addition = '''        self.assertFalse(authority["raw_session_event_type_publicly_exported"])
        self.assertFalse(
            authority["unauthenticated_session_event_mutation_publicly_exported"]
        )
        self.assertTrue(authority["authority_changing_state_requires_attested_request"])
        self.assertTrue(authority["cancellation_helpers_are_revocation_only"])
'''
    text = replace_once(
        text,
        contract_anchor,
        contract_anchor + contract_addition,
        "contract authority assertions",
    )
    actor_anchor = '''        self.assertFalse(contract["browser_actor"]["generic_runtime_injection"])
'''
    actor_addition = '''        self.assertFalse(contract["browser_actor"]["generic_session_event_ingress"])
        self.assertEqual(
            contract["browser_actor"]["product_state_transition_entry"],
            "handle_attested_request_only",
        )
        self.assertFalse(
            contract["browser_actor"]["caller_can_release_human_or_ime_control"]
        )
        self.assertFalse(
            contract["browser_actor"]["caller_can_resolve_capability_or_recovery"]
        )
        self.assertFalse(
            contract["browser_actor"]["caller_can_synthesize_navigation_completion"]
        )
        self.assertTrue(
            contract["browser_actor"][
                "unauthenticated_helpers_can_only_revoke_or_observe"
            ]
        )
'''
    text = replace_once(
        text,
        actor_anchor,
        actor_anchor + actor_addition,
        "contract actor assertions",
    )
    doc_anchor = '''        self.assertIn("actor-owned", wrapper)
'''
    doc_addition = '''        self.assertIn("no raw", wrapper.lower())
        self.assertIn("non-generic", architecture.lower())
        self.assertIn("handle_attested", architecture)
        self.assertNotIn("BrowserActor<R>", architecture)
        self.assertNotIn("a bounded `PageRuntime` adapter", architecture)
'''
    text = replace_once(
        text,
        doc_anchor,
        doc_anchor + doc_addition,
        "document assertions",
    )
    path.write_text(text, encoding="utf-8")


def write_readme() -> None:
    path = ROOT / "crates/hepta-browser-actor/README.md"
    text = path.read_text(encoding="utf-8").rstrip()
    section = r'''

## State-ingress boundary

The product crate exports no raw `SessionEvent`, `TransitionError`, or generic
state mutator. An ordinary holder of `BrowserActor` cannot manufacture human
focus release, IME completion, navigation completion, capability resolution,
crash recovery, or session closure. Authority-changing state enters only through
`handle_attested`, which carries the bound request context and live peer custody.

`cancel_request`, `cancellation_token`, and `active_cancellation_token` can only
revoke or observe an in-flight request; they cannot grant control, clear a human
lease, mark navigation complete, or make an indeterminate effect successful.
`page_owner`, `principal`, and `receipt_observer` are read/record helpers and do
not provide a hidden state-transition path. There is no raw product state
injection API.
'''
    if "## State-ingress boundary" not in text:
        text += section
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def write_architecture() -> None:
    path = ROOT / "docs/architecture/BROWSER_ACTOR_AUTHORITY_BOUNDARY.md"
    path.write_text(
        r'''# BrowserActor authority boundary

## Purpose

S06 introduces the concrete product request owner that translates one validated
Browser API request into one bounded local-fixture runtime operation while
preserving session, cancellation, peer-custody, and receipt invariants. The weak
paths are absent from the product-facing type system rather than merely
conventionally discouraged.

## Product crate: `hepta-browser-actor`

The product API exposes one **non-generic** `BrowserActor`. Its
`from_attested` constructor accepts only:

1. a policy-selected `TaskFlowPrincipal`;
2. the kernel-derived `PeerIdentity` of the connected stream;
3. the `ProcfsPeerAttestor` or reviewed trusted-path source used at admission;
4. an opaque pidfd-backed `AttestedPeer` retaining the admitted process.

The constructor refreshes process start time, UID, GID, cgroup v2 path, systemd
unit, and executable digest, creates the private principal/mechanism binding, and
installs the bounded `DeterministicLocalRuntime` internally. It accepts no
`PageRuntime`, callback backend, thread handle, generic type parameter, or
caller-written mechanism identity.

The product crate does not export `PrincipalBinding`, `MechanismIdentity`,
`PageRuntime`, `RequestControl`, `RuntimeReply`, or a raw session event type. It
does not implement `BrowserRequestHandler`, expose an ordinary `handle`, create a
listener, or define an installable binary.

## Per-request authority

Every authority-changing product operation enters through `handle_attested`:

1. reject an expired absolute deadline before identity work;
2. refresh the same admitted identity source;
3. compare all mechanism facts to the private binding;
4. mint one non-cloneable request custody owner from the `AttestedPeer`;
5. propagate only its verifier through internal runtime controls and callbacks;
6. verify current custody at runtime/effect boundaries;
7. verify again before releasing a terminal success;
8. on post-dispatch revocation, retire the runtime and classify possible effects
   as indeterminate;
9. drop the custody owner on normal return or unwind.

A peer tuple, copied runtime snapshot, semantic principal, caller-written digest,
or ordinary `BrowserActor` holder cannot invoke an alternate dispatch path.

## State-ingress boundary

The product wrapper exports no `SessionEvent`, `TransitionError`, or
`apply_session_event`. This prevents an ordinary caller from synthesizing human
focus release, IME completion, navigation completion/failure, modal closure,
capability resolution, recovery, or session closure outside the attested request
path. Human and IME exclusion therefore cannot be cleared before a later
attested navigation by mutating the actor directly.

The public cancellation helpers are revocation-only: they may cancel or observe
one in-flight request but cannot grant Agent control or mark an operation
successful. `principal` and `page_owner` return bounded observations.
`receipt_observer` records lifecycle facts and never authorizes execution.

## Implementation crate: `hepta-browser-actor-simulation`

The unpublished implementation-internal crate retains the generic runtime,
state machine, callback bridge, deterministic fixtures, fault injection, and
hostile test corpus. Repository validation permits only the product wrapper to
depend on it directly. Its compatibility APIs and raw state-machine methods are
not product entry points and cannot be wired directly into AgentPort.

## Internal runtime and completion

The actor-owned local runtime receives an internal `RequestControl` carrying the
same absolute deadline, shared cancellation token, and request peer verifier.
Queue admission is not execution. Callback loss, panic, timeout, duplicate
completion, or peer revocation cannot be converted into success. Ambiguous
cleanup poisons and retires the runtime pair. Semantic page action remains a
single runtime-owned resolve-and-act hook and the local fixture defaults closed.

A later Servo product adapter must be introduced as a distinct concrete reviewed
type. It must preserve the same custody and completion invariants and must not
reopen a public generic runtime injection point.

## Receipt lifecycle

Requested, dispatched, and terminal facts may be written to the S05 durable
journal. Journal recovery and export do not authorize execution. Interrupted
potential external effects become indeterminate and are never automatically
replayed. Storage or publication uncertainty requires inspection/recovery before
reuse.

## Negative guarantees

The S06 gate rejects:

- a product `BrowserActor<R>` or constructor accepting a runtime value;
- public `PageRuntime`, `RequestControl`, `PrincipalBinding`, or mechanism facts;
- public raw session events or an unauthenticated session-state mutator;
- ordinary `BrowserRequestHandler` or `handle` dispatch;
- dependencies on the simulation crate outside the product wrapper;
- actor-owned TCP/Unix listeners, spawned product workers, or automatic binaries;
- optional attestation/custody or a receipt journal that authorizes work.

Compile-fail doctests prove that weak binding types, generic runtime injection,
ordinary handler use, and raw session-state synthesis are unavailable. Python
surface tests and the complete Rust simulation corpus enforce the same boundary.

## Rollback and claim ceiling

Revert the bounded S06 merge before any Servo/runtime successor. The slice adds
no listener, installed service, state migration, external HTTPS authority,
physical hardware evidence, signing, publication, or release authority. A green
exact-source and live prospective-merge gate proves only the reviewed source/test
API on its exact S05 parent.
''',
        encoding="utf-8",
    )


patch_wrapper()
patch_contract()
patch_tests()
write_readme()
write_architecture()
