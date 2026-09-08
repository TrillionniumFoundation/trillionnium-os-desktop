# contract-catalog

**Component registry ID:** `contract-catalog`
**Component path:** `contracts`
**Owner class:** `contract-security`
**Plan revision:** `2026-08-29-d6`
**Registry:** `manifests/components.v1.json`

## Status and claim ceiling

Current status: `normative_source_contracts`.

**Claim ceiling:** schemas, taxonomies, golden vectors, and policy contracts only; no runtime enforcement or promotion evidence by themselves.

This component is interpreted under the repository's evidence-tier and
invalidation rules. Source completeness and passing local tests establish only
the status above. They do not imply protected governance, integrated-main,
installed-product, physical-hardware, signing, or release authority unless the
applicable gate records independently bound evidence.

## Responsibilities

- Define versioned request, response, receipt, capability, app, governance, image, hardware, and release data models.
- Provide stable error codes and exact golden vectors shared by Rust and Python implementations.
- Describe prerequisites, evidence envelopes, claim ceilings, and invalidation behavior consumed by validators.
- Separate source capability records from evidence freshness and promotion state.

The component must keep these responsibilities explicit enough that reviewers
can identify the exact authority boundary, inputs, outputs, failure modes, and
evidence producer without inferring behavior from filenames alone.

## Non-responsibilities

- JSON files do not open sockets, authorize principals, dispatch BrowserActor work, execute effects, or sign releases.
- Schema conformance does not prove the installed product uses the schema on every path.
- A golden fixture is not runtime, hardware, or independent evidence.

These exclusions are normative. A downstream caller, workflow, fixture, or
document may not widen the component by relabeling a lower-tier result.

## Dependency and call direction

Human-reviewed contracts are consumed by Rust domain crates, Python reference tools, evidence verifiers, image scripts, and CI. Producers serialize bounded values; consumers reject unknown or malformed representations before authority decisions. Gate contracts point to machine registries rather than duplicating live GitHub state.

The allowed direction is from higher-level trusted policy into this bounded
mechanism and back through typed results. Reverse dependencies that let a lower
trust surface select policy, credentials, arbitrary paths, commands, devices,
network destinations, signing keys, or promotion state are forbidden unless a
new reviewed contract explicitly introduces that authority.

## Public interfaces and entrypoints

Registered entrypoints:

- `contracts/browser-api.v1.schema.json`
- `contracts/error-codes.v1.json`
- `contracts/golden/golden-health-1.wire.json`

Architecture references:

- `docs/plan/CONTRACT_SECURITY_TESTING.md`
- `docs/plan/GATE_CONTRACTS_AND_INVALIDATION.md`

Contract references:

- `contracts/browser-api.v1.schema.json`
- `contracts/gate-evidence-envelope.v1.schema.json`
- `contracts/repository-governance.v1.json`

Only registered entrypoints and versioned contracts are reviewable public
surfaces. An unregistered executable, workflow, package path, service unit, or
ad-hoc data format is a repository consistency failure.

## Configuration and features

Configuration is supplied through committed manifests, versioned contracts,
locked toolchain/input records, fixed workflow environment variables, or
explicit package/service profiles. Mutable upstream names, ambient host state,
unbounded workflow inputs, and undocumented feature flags are not valid
configuration. Defaults must remain least-authority and fail closed; development
or qualification profiles must be physically and semantically distinct from
production.

## State, concurrency, and failure semantics

Contracts are immutable-by-version source artifacts. Stateful behavior is represented explicitly through revisions, nonces, deadlines, lifecycle states, and append-only receipt facts rather than hidden parser state. Compatibility changes require a new version or a proven backward-compatible extension; stale evidence remains stale even if a contract still parses.

Partial completion is never upgraded to success. Timeout, cancellation,
infrastructure failure, product failure, stale evidence, and indeterminate
external outcome remain distinct states. A retry must bind to the same exact
inputs or create a new evidence identity; it must not overwrite the historical
failure packet.

## Security invariants

- ambiguous, duplicate-key, unknown-field, oversized, and noncanonical inputs fail closed
- a contract version never silently changes semantics under the same identity
- golden vectors remain exact bytes rather than illustrative examples

In addition, repository-relative paths must be canonical and read without
following symlinks where they influence authority or evidence. Structured data
must reject duplicate keys and malformed identities. Secrets and page content
must not enter logs or artifacts unless a reviewed redaction contract permits
specific bounded fields.

## Testing and evidence

Registered tests:

- `tests/test_gate_evidence_envelope.py`
- `tests/test_validate_rust_browser_codec.py`

Registered workflows:

- `.github/workflows/ci.yml`
- `.github/workflows/browser-codec-reference.yml`

Tests must include positive behavior and hostile boundary cases. Evidence must
record exact source/base/tree or image/input identities, workflow and artifact
IDs, bounded output digests, claim ceiling, and invalidation triggers. A verifier
self-test proves the verifier rejects bad fixtures; it does not prove a separate
producer generated authentic higher-tier evidence.

## Operations and troubleshooting

Use canonical JSON formatting only where byte identity is part of the contract. Validate duplicate-key rejection and upper bounds with hostile fixtures. When diagnosing drift, compare the schema version, exact file digest, generated Rust/Python interpretation, and the gate that lists the contract as an invalidation input.

Operational diagnosis starts from the first failed invariant and the exact
input object. Do not make a gate green by broadening permissions, accepting
missing fields, following symlinks, selecting a different process/device,
disabling negative cases, or rewriting expected evidence after the fact.

## Compatibility and change protocol

A contract change must update affected Rust types, codecs, golden vectors, hostile tests, architecture documents, manifests, workflow inputs, and evidence readers in one review object. Renaming or deleting an error code or field requires an explicit migration and historical-reader plan; source edits never retroactively rebind old evidence.

Every change must also update `manifests/components.v1.json` when paths,
entrypoints, ownership, references, status, security invariants, or claim
ceilings move. Run `python3 tools/validate_component_documentation.py`, the
project/repository validators, authoritative Python discovery, and the locked
Rust matrix before requesting independent review.

## D6 boundary regression and compatibility references

The candidate permit v2 schema and ADR 0006 describe the structured subject and
second-based time contract separately from historical v1. The source reference
regressions in `tests/d6/test_capability_boundary_hardening.py` cover typed input,
canonical URLs and transactional use/receipt publication. These references do
not change this component's capability or evidence tier.

## Callback-shaped engine scheduling

The optional `callback_engine_pair` / `CallbackEngineOwner` path starts an
operation on its creator thread and accepts a single-use `EngineCompletion`
from a later callback. The application continues native events between pumps;
its timer follows the original deadline and bounded cancellation-check schedule.
Ordinary Act never substitutes for the dedicated atomic semantic hook. The
existing request endpoint now wakes on abandonment and Drop as well as enqueue.
Wakes may be coalesced and are not a count of dispatched operations.
See `docs/architecture/EVENT_LOOP_COMPLETION.md` and
`contracts/event-loop-completion.v1.json` for APIs, ordering, tests and limits.
This is source/host fixture evidence only: no Servo/native event loop, process
IPC, installed image or product authority is added. The development daemon
continues selecting its synchronous fixture backend; no activation changes.


## Callback development service integration

The persistent development service now uses the callback owner with an explicit
ImmediateCallbacks bridge for its existing deterministic fixture. The main
runner waits on a private notification predicate; worker completion is published
before wake and errors retire before join. This does not implement Servo, winit,
systemd activation or an installed image. See
`docs/architecture/D3_CALLBACK_SERVICE_RUNNER.md` and
`contracts/d3-callback-service-runner.v1.json`; the source regression guard is
`tools/audit_callback_service.py`, tested by
`tests/test_callback_service_runner.py`. Existing controls and promotion limits
remain unchanged. The immediate bridge does not make a blocking backend async.
