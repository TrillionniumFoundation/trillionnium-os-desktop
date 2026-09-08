# d3-semantic-resolver-experiment

**Component registry ID:** `d3-semantic-resolver-experiment`
**Component path:** `experiments/d3-semantic-resolver-rust`
**Owner class:** `browser-actor-security`
**Plan revision:** `2026-08-29-d6`
**Registry:** `manifests/components.v1.json`

## Status and claim ceiling

Current status: `deterministic_reference_not_servo_adapter`.

**Claim ceiling:** mutex-protected local-fixture semantic resolution reference only; no Servo retained-node forwarding, product BrowserActor authority, or exact-image promotion.

This component is interpreted under the repository's evidence-tier and
invalidation rules. Source completeness and passing local tests establish only
the status above. They do not imply protected governance, integrated-main,
installed-product, physical-hardware, signing, or release authority unless the
applicable gate records independently bound evidence.

## Responsibilities

- Model the D3 semantic target table and atomic resolve-and-act behavior in isolated Rust.
- Exercise role, accessible name, visibility, structure, uniqueness, principal, and revision constraints.
- Provide deterministic fixtures for verifier and BrowserActor integration design.
- Demonstrate stale-reference and ambiguity rejection without granting engine authority.

The component must keep these responsibilities explicit enough that reviewers
can identify the exact authority boundary, inputs, outputs, failure modes, and
evidence producer without inferring behavior from filenames alone.

## Non-responsibilities

- It does not receive Servo accessibility/tree updates or retain real engine node handles.
- It does not forward pointer, keyboard, navigation, or form actions into a live WebView.
- It does not prove D3 exact-image process, dispatch, receipt, cancellation, or crash behavior.

These exclusions are normative. A downstream caller, workflow, fixture, or
document may not widen the component by relabeling a lower-tier result.

## Dependency and call direction

A test caller supplies a principal-bound semantic request to a local table. The experiment locks the table, identifies the only eligible node under the expected document/frame revision, validates the requested action, applies the bounded state transition, and returns a deterministic result. No network, socket, browser, or external effect is involved.

The allowed direction is from higher-level trusted policy into this bounded
mechanism and back through typed results. Reverse dependencies that let a lower
trust surface select policy, credentials, arbitrary paths, commands, devices,
network destinations, signing keys, or promotion state are forbidden unless a
new reviewed contract explicitly introduces that authority.

## Public interfaces and entrypoints

Registered entrypoints:

- `experiments/d3-semantic-resolver-rust/Cargo.toml`
- `experiments/d3-semantic-resolver-rust/src/lib.rs`

Architecture references:

- `docs/architecture/ATOMIC_SEMANTIC_RESOLVER.md`
- `docs/architecture/D3_INTEGRATED_RUNTIME_QUALIFICATION.md`

Contract references:

- `contracts/semantic-resolver.v1.json`
- `contracts/browser-actor.v1.json`

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

The reference table is protected by a single synchronization boundary so resolve and act cannot observe different generations. Revisions and node identity are explicit. Poison, ambiguity, stale revision, missing target, or unsupported action returns a terminal error and does not apply a partial mutation.

Partial completion is never upgraded to success. Timeout, cancellation,
infrastructure failure, product failure, stale evidence, and indeterminate
external outcome remain distinct states. A retry must bind to the same exact
inputs or create a new evidence identity; it must not overwrite the historical
failure packet.

## Security invariants

- selection, validation, and action occur under one caller-bound atomic operation
- ambiguous, invisible, stale, or multiply matched targets fail closed
- the experiment never advertises itself as a Servo-owned adapter

In addition, repository-relative paths must be canonical and read without
following symlinks where they influence authority or evidence. Structured data
must reject duplicate keys and malformed identities. Secrets and page content
must not enter logs or artifacts unless a reviewed redaction contract permits
specific bounded fields.

## Testing and evidence

Registered tests:

- `tests/d3/test_semantic_resolver_reference.py`

Registered workflows:

- `.github/workflows/d3-semantic-resolver-reference.yml`

Tests must include positive behavior and hostile boundary cases. Evidence must
record exact source/base/tree or image/input identities, workflow and artifact
IDs, bounded output digests, claim ceiling, and invalidation triggers. A verifier
self-test proves the verifier rejects bad fixtures; it does not prove a separate
producer generated authentic higher-tier evidence.

## Operations and troubleshooting

Run the dedicated Python/Rust reference corpus and inspect rejected-case coverage. A passing reference workflow means the algorithm and contract agree; it does not mean Servo exposes the necessary retained-node API. Any attempt to use this crate in production must first introduce an explicit reviewed engine adapter and exact-image evidence.

Operational diagnosis starts from the first failed invariant and the exact
input object. Do not make a gate green by broadening permissions, accepting
missing fields, following symlinks, selecting a different process/device,
disabling negative cases, or rewriting expected evidence after the fact.

## Compatibility and change protocol

Changes to matching semantics, target uniqueness, revision comparison, action taxonomy, or locking require synchronized contract, architecture, tests, workflow, and claim-ceiling updates. The boundary must remain isolated until a pinned Servo API supplies atomic retained-node action forwarding.

Every change must also update `manifests/components.v1.json` when paths,
entrypoints, ownership, references, status, security invariants, or claim
ceilings move. Run `python3 tools/validate_component_documentation.py`, the
project/repository validators, authoritative Python discovery, and the locked
Rust matrix before requesting independent review.
