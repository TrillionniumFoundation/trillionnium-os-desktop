# S08 product Servo supervision

Status: compiled supervision mechanism candidate; no product startup, installed
image, hardware, signing, publication or release is established by this module.

## Scope

The candidate compiles `hepta-browserd` supervision against the concrete exact-pin
`ServoBrowserActor` type. BrowserActor remains the owner of page state, request
custody, event-loop dispatch and durable receipt decisions. The executable is
still a self-check scaffold; compiling this library does not start Servo.

Final S08 acceptance requires attested AgentPort through the product browserd
coordinator, BrowserActor custody, exact-pin Servo execution, a durable terminal
or indeterminate receipt, and a typed response. The required durable terminal or indeterminate receipt
cannot be substituted by an in-memory flag or by a qualification mailbox.

```text
attested AgentPort -> hepta-browserd -> BrowserActor -> exact-pin Servo
                  -> durable terminal or indeterminate receipt -> typed response
```

A type alias, generic supervisor test or isolated Servo harness is insufficient.
The same immutable object must execute the complete path and its hostile cases.

## Trust and authority boundary

The supervisor owns runtime generation, crash-loop state and a fail-closed replay
latch. It does not mint capabilities, infer user intent, duplicate the receipt
journal or bypass BrowserActor custody. The concrete actor must revalidate peer,
deadline, cancellation and retained semantic identity immediately before acting.

The generic mechanism is a source-level integration aid, not an independently
trusted authorization service. Its completion classification must come from the
reviewed concrete adapter, never from page content or an arbitrary client.

## Runtime generations and stale references

Generation starts at one and advances with checked arithmetic when a live actor
crashes. Duplicate crash reports while the actor is absent are refused without
advancing identity again. Zero semantic revisions are rejected. The supervisor
checks generation only; BrowserActor still validates document, snapshot, frame
and retained node identity. There is no implicit translation of stale references.

Generation exhaustion permanently enters `GenerationExhausted`, drops the actor
and refuses reference validation, dispatch, reconstruction and reconciliation.
The terminal state is committed before actor destruction so unwinding cannot
leave the old actor eligible. A new service lifecycle must not reuse persisted
session identity; durable incarnation binding remains part of the product gate.

## Crash and reconstruction protocol

A content crash must leave trusted chrome alive in the final product. The source
mechanism invalidates generation, updates the bounded crash count, commits
`NeedsReconstruction`, `ReplayReconciliationRequired` or `CrashLoopOpen`, then
drops the old actor. The crash transition never invokes the actor factory.

Reconstruction is explicit. It remains blocked after a possible dispatch and
when the crash loop is open. Factory error or panic retires this service lifecycle
instead of permitting an unbounded construction loop. A stable-cycle observation
can reset a counter only while an actor is currently ready and non-uncertain;
it never clears terminal state and is not an installed boot-health receipt.

## No automatic replay

There is no automatic replay. The uncertainty latch is set before invoking the
operation closure exactly once. `Completed` clears the transient latch only
because the reviewed adapter supplies a terminal result. `NotDispatched` clears
it only when the adapter proves Servo never observed the command.
`IndeterminateAfterDispatch`, panic or unwind preserves the latch and refuses
all later dispatch and reconstruction attempts.

The old no-argument reconciliation operation was unsafe because it accepted no
journal evidence and could also unlock a crash loop. In this candidate,
`reconcile_indeterminate()` changes no state and returns
`reconciliation_evidence_required`; terminal states return their terminal error.
There is intentionally no flag, environment variable or caller-provided boolean
that clears this latch. A future recovery operation must bind an authenticated
current journal, exact pending request/digest/receipt, runtime incarnation and
a durable reconciliation outcome before it may be accepted.

## Durable receipt continuity

The supervisor creates no competing journal. The existing session receipt writer
remains authoritative. In-memory supervision tests do not prove durable receipt
continuity, process restart recovery or an external effect outcome.

Before product promotion, execute the normal terminal receipt/response path;
lose completion after possible dispatch and retain an indeterminate receipt;
prove no automatic retry; crash content while trusted chrome survives; explicitly
reconstruct a new generation; reject the old semantic reference; preserve journal
continuity; and prove bounded crash-loop lockout. A repaired source mechanism is
not closure of these installed or real-Servo obligations.

## Failure and logging policy

Errors use a closed redacted vocabulary including `stale_generation`,
`invalid_semantic_revision`, `runtime_unavailable`, `generation_exhausted`,
`crash_loop_open`, `indeterminate_after_dispatch`,
`reconciliation_evidence_required` and `reconstruction_failed`. No request
payload, credential, unrestricted upstream error or secret identity is logged.

Record generation, transition class, redacted code, receipt identity and source
object only as bounded supporting diagnostics. Logs do not replace durable facts.
Preserve damaged or unresolved journals for authorized investigation; never erase
history to restart the service or call an uncertain effect failed merely to retry.

## Qualification

The permanent `s08-product-servo-runtime` workflow validates the exact pushed head
and the immutable event merge, with live parent readback before and after the
prospective test. It runs the locked Rust 1.93 toolchain, format, check, Clippy,
all browserd targets, the source validator and the unchanged hostile corpus plus
new regression tests. It requires at least fourteen compiled supervisor tests;
a source file outside the module graph cannot satisfy the gate.

Source checks inspect executable module/dependency wiring, generation handling,
latch placement, no unbound reconciliation and read-only workflow execution.
They are regression checks, not a formal Rust or workflow semantics proof.
Exact-pin real Servo behavior remains a separate gate. No temporary source-export
repair or self-modifying workflow is authorized, and prior-head success does not
transfer to a changed source or base object.

## Claim ceiling

This is compiled source/host-mechanism qualification only. `main.rs` still starts
no browser service, listener or real Servo runtime. Journal-bound reconciliation,
trusted-chrome survival with a real content crash, the full product vertical
slice, installed Debian/QEMU, Linux input/IME, physical hardware, independent
builds, offline/HSM signing and protected publication remain separate open gates.
