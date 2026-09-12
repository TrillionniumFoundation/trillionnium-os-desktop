# S08 product Servo supervision

Status: host-runtime integration candidate; not installed-image, hardware, signing, publication, or release evidence.

## Scope

This contract binds the trusted `hepta-browserd` product package to the concrete exact-pin `ServoBrowserActor`. It governs only the host boundary between the long-lived trusted browser service and one reconstructable content-runtime incarnation. BrowserActor remains the sole owner of page state, request custody, event-loop dispatch and durable receipt decisions.

The complete S08 acceptance path remains:

```text
attested AgentPort
→ hepta-browserd authority coordinator
→ BrowserActor request custody
→ exact-pin Servo command/completion path
→ durable terminal or indeterminate receipt
→ typed response
```

A source-level type alias or an isolated Servo harness is insufficient on its own. Final S08 promotion requires the exact immutable head to execute that complete path and the crash/recovery cases below.

## Trust and authority boundary

`hepta-browserd` owns service supervision, runtime-generation identity, crash-loop policy and the fail-closed replay latch. It does not duplicate BrowserActor authority, inspect secret request payloads, mint a second receipt truth, or call Servo around BrowserActor.

Only a current-generation semantic reference may be admitted. Request cancellation, deadline and peer custody must be revalidated at the BrowserActor boundary immediately before Servo dispatch. A stale reference, absent actor, open crash loop or unresolved indeterminate outcome is rejected before a new operation can be issued.

## Runtime generations and stale references

The initial content-runtime incarnation is generation one. A content-process crash advances the generation with checked arithmetic and drops the concrete actor. Generation wrap is a terminal failure; it must never wrap or reuse an identity.

Every semantic reference carries the generation that minted it. Reconstruction reserves a new generation, so all references from the crashed incarnation are stale by construction. Stale references are rejected rather than translated, refreshed or replayed implicitly.

## Crash and reconstruction protocol

A content-process crash does not terminate trusted chrome or the long-lived `hepta-browserd` supervisor. The crash transition performs, in order:

1. preserve trusted service custody and durable evidence already committed;
2. invalidate the current runtime generation;
3. drop the concrete content actor;
4. increment the bounded consecutive-crash counter;
5. enter `NeedsReconstruction`, `ReplayReconciliationRequired`, or `CrashLoopOpen`;
6. require an explicit reconstruction call before any later dispatch.

The crash transition itself never invokes the actor factory. Reconstruction is a separate auditable operation. At the configured crash threshold the supervisor opens the crash loop and refuses further reconstruction until an external recovery decision creates a new qualified service lifecycle.

## No automatic replay

The dispatch closure is invoked exactly once. Its completion must be classified as one of:

- `Completed`: one terminal result is available;
- `NotDispatched`: the adapter proved Servo did not observe the command;
- `IndeterminateAfterDispatch`: Servo may have observed the command.

`IndeterminateAfterDispatch` latches `ReplayReconciliationRequired`. While latched, all dispatch and reconstruction attempts fail closed. Only an explicit external durable-receipt reconciliation may clear the latch. Clearing the latch does not reconstruct an actor and does not replay a command.

This rule is mandatory for operations with external effects. A process crash, transport loss, timeout or missing completion after possible dispatch must never be treated as permission to retry automatically.

## Durable receipt continuity

The supervisor does not create a competing journal. BrowserActor and the session receipt journal remain authoritative for admitted, dispatched, completed and indeterminate outcomes. A generation transition must preserve all durable receipts committed before the crash and must bind post-reconstruction responses to the new generation.

Before S08 promotion, an end-to-end hostile test must show:

- a terminal receipt and response on the normal path;
- an indeterminate receipt when completion is lost after possible dispatch;
- no automatic replay after that indeterminate result;
- content-process crash with trusted chrome still alive;
- explicit actor reconstruction under a new generation;
- rejection of a semantic reference from the old generation;
- bounded crash-loop lockout;
- journal continuity across reconstruction.

## Failure and logging policy

Public errors use a closed redacted vocabulary. They may expose stable codes such as `stale_generation`, `runtime_unavailable`, `crash_loop_open`, `indeterminate_after_dispatch` and `reconstruction_failed`. They must not expose request payloads, secrets, peer credentials, Servo internals or unrestricted implementation error strings.

Generation, transition class, redacted error code, receipt identity and source commit may be recorded as evidence. Logs are supporting evidence only and never substitute for the durable receipt journal.

## Qualification

The permanent `s08-product-servo-runtime` workflow must bind both the exact pushed head and the live prospective merge. It runs the locked Rust 1.93 toolchain, format, check, Clippy, browserd tests, module-documentation validation, repository validation and project-truth validation. The existing exact-pin Servo gate remains independently responsible for real-upstream Servo execution.

Temporary source-export or self-modifying repair workflows are not part of the candidate and must be absent from the final tree. Checks from predecessor heads, export commits or another base do not transfer.

## Claim ceiling

Passing this source and host-runtime contract does not prove an installed Debian/QEMU product, Linux platform adapter completeness, physical hardware behavior, independent reproducible builds, offline/HSM signing, protected publication or release readiness. Those remain S09–S12 evidence gates and may be promoted only by their own exact-object qualification and independent authority separation.
