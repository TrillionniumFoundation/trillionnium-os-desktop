# manifest-catalog

**Component registry ID:** `manifest-catalog`
**Component path:** `manifests`
**Owner class:** `machine-truth-governance`
**Plan revision:** `2026-08-29-d6`
**Registry:** `manifests/components.v1.json`

## Status and claim ceiling

Current status: `canonical_machine_truth_and_input_locks`.

**Claim ceiling:** committed project state, gate registry, component/module inventory, and selected input identities only; no live GitHub, runtime, hardware, or release fact.

This component is interpreted under the repository's evidence-tier and
invalidation rules. Source completeness and passing local tests establish only
the status above. They do not imply protected governance, integrated-main,
installed-product, physical-hardware, signing, or release authority unless the
applicable gate records independently bound evidence.

## Responsibilities

- Record canonical integrated stage, active plan, non-claims, candidate snapshot, gate statuses, and evidence lifecycle.
- Lock Rust, Servo, Debian, e2fsprogs, action, package, patch, and product-boundary inputs.
- Register every Cargo module and non-Cargo component with reviewable documentation references.
- Expose explicit repository-setting and upstream blockers without converting them to source success.

The component must keep these responsibilities explicit enough that reviewers
can identify the exact authority boundary, inputs, outputs, failure modes, and
evidence producer without inferring behavior from filenames alone.

## Non-responsibilities

- Manifests do not query live GitHub and cannot prove branch protection, approvals, environments, or release state.
- A selected package or toolchain is not a built image.
- A status field cannot replace the workflow/artifact/hardware/signing evidence required by its gate.

These exclusions are normative. A downstream caller, workflow, fixture, or
document may not widen the component by relabeling a lower-tier result.

## Dependency and call direction

Plans and contracts define allowed vocabulary; workflows and validators consume manifests as immutable inputs; evidence producers bind output to exact manifest digests; human documents render the same state. Candidate snapshots are copied to project, repository, and docs projections and validated for exact equality.

The allowed direction is from higher-level trusted policy into this bounded
mechanism and back through typed results. Reverse dependencies that let a lower
trust surface select policy, credentials, arbitrary paths, commands, devices,
network destinations, signing keys, or promotion state are forbidden unless a
new reviewed contract explicitly introduces that authority.

## Public interfaces and entrypoints

Registered entrypoints:

- `manifests/project-state.v1.json`
- `manifests/gates.v1.json`
- `manifests/repository-state.json`
- `manifests/modules.v1.json`
- `manifests/components.v1.json`

Architecture references:

- `docs/plan/PROJECT_TRUTH_AND_EVIDENCE.md`
- `docs/plan/GATE_CONTRACTS_AND_INVALIDATION.md`

Contract references:

- `contracts/project-state.v1.schema.json`
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

Machine truth is append-and-revise source state, not a database. Freshness is explicit and separate from capability status. The pre-truth-refresh snapshot records the immediately preceding live object because a commit cannot self-reference its own SHA. Any source or base movement requires a new live read and exact-head packet.

Partial completion is never upgraded to success. Timeout, cancellation,
infrastructure failure, product failure, stale evidence, and indeterminate
external outcome remain distinct states. A retry must bind to the same exact
inputs or create a new evidence identity; it must not overwrite the historical
failure packet.

## Security invariants

- all active candidate projections bind to one identical committed snapshot
- historical candidates and stale evidence never count as active promotion evidence
- input locks use immutable digests/commits rather than mutable names

In addition, repository-relative paths must be canonical and read without
following symlinks where they influence authority or evidence. Structured data
must reject duplicate keys and malformed identities. Secrets and page content
must not enter logs or artifacts unless a reviewed redaction contract permits
specific bounded fields.

## Testing and evidence

Registered tests:

- `tests/test_validate_project_truth.py`
- `tests/test_gate_validator_input_coverage.py`

Registered workflows:

- `.github/workflows/ci.yml`
- `.github/workflows/governance-integrity.yml`

Tests must include positive behavior and hostile boundary cases. Evidence must
record exact source/base/tree or image/input identities, workflow and artifact
IDs, bounded output digests, claim ceiling, and invalidation triggers. A verifier
self-test proves the verifier rejects bad fixtures; it does not prove a separate
producer generated authentic higher-tier evidence.

## Operations and troubleshooting

Use duplicate-key-safe parsers, canonical path rules, and no-follow reads. When a validator reports drift, repair every projection in the same commit. Never hand-edit an artifact digest, mark stale evidence current, or set `merge_ready` without the required exact object and independent review.

Operational diagnosis starts from the first failed invariant and the exact
input object. Do not make a gate green by broadening permissions, accepting
missing fields, following symlinks, selecting a different process/device,
disabling negative cases, or rewriting expected evidence after the fact.

## Compatibility and change protocol

New machine inputs require a schema or documented structure, a validator, hostile tests, gate invalidation coverage, and a documentation entry. Renames must preserve historical readers. Candidate transition edits must update project-state, repository-state, docs manifest, evidence staleness, and current-state prose atomically.

Every change must also update `manifests/components.v1.json` when paths,
entrypoints, ownership, references, status, security invariants, or claim
ceilings move. Run `python3 tools/validate_component_documentation.py`, the
project/repository validators, authoritative Python discovery, and the locked
Rust matrix before requesting independent review.
