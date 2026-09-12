# TrillionniumOS Desktop contracts, security, and testing

**Origin revision:** `2026-08-28-d5`
**Status:** inherited d5 design annex; subordinate to the active d6 plan
**Active plan:** [`2026-08-29-d6`](../DESKTOP_PLAN-2026-08-29-d6.md)
**Repository mode:** `FULL_PRODUCT_REPOSITORY`

The complete original detailed annex is preserved in
[the historical snapshot](CONTRACT_SECURITY_TESTING.d5-historical.md).
Apply [the d6 inheritance map](D6_ANNEX_PRECEDENCE.md), current machine contracts
and the narrower current claim whenever a historical statement conflicts.

## Wire, identity and effect boundary

The Browser API is closed and engine-neutral: unknown operations and fields
fail rather than becoming opaque extension authority. Canonical encoding,
resource budgets, typed errors and semantic references are owned by their
current schema/codec contracts. A parseable URL is not a trusted connection,
and an attested process is not automatically an authorized TaskFlow principal.

D3 AgentPort is development/qualification activation only, under an explicit
reviewed profile. The historical heading "Production AgentPort" does not
permit production activation. Socket custody, fresh request-scoped identity,
cancellation and absolute deadlines remain required at the final dispatch
boundary. Potential effects are never automatically replayed after uncertain
dispatch, timeout, crash, navigation or loss of response.

## Execution and durable facts

Tests must distinguish admission, dispatch, engine completion, durable terminal
receipt and response delivery. Queue acceptance is not engine execution, and
response loss is not evidence that an action never happened. Every admitted
operation must preserve request/session/peer/digest identity through the
applicable receipt lifecycle. Only current retained semantic references may
reach an action; stale or ambiguous targets cannot fall back to coordinates,
JavaScript, selectors or text search.

Human focus and IME own the relevant input boundary. Real adapter tests must
cover preemption during composition, navigation, modal states and crash
reconstruction, not just enum construction or model transitions.

## Evidence and regression requirements

Retain the d5 malformed-wire, state-machine/property, local HTML, input/IME,
origin/storage, egress, update/recovery and hardware test categories. Bind
current execution to exact source/tree, workflow, locks and output digests.
Do not transfer an old pass across head/base changes or use a skipped
environment-gated test as successful evidence.

A source validator checks source policy; a host test checks the named host
mechanism; an installed-image test checks that exact image. Physical endurance,
raw power removal and protected key custody require their own external facts.
Repository documentation tests do not claim any of these higher tiers.

## Performance and privacy

Define measurement methodology and collect boot, first-frame, input,
observe/act, receipt-sync and recovery timings alongside RSS/FD/PID/queue
limits. Hardware-specific acceptance numbers are selected with a fixed BOM
and reviewed methodology, not invented from a source test.

Diagnostics remain bounded and redacted. Receipt exports, corruption handling,
capacity exhaustion and reconciliation must preserve evidence without leaking
page content, secrets or raw process identity into generic logs.
