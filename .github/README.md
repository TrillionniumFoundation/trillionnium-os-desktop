# repository-automation

**Component registry ID:** `repository-automation`
**Component path:** `.github`
**Owner class:** `repository-governance`
**Plan revision:** `2026-08-29-d6`
**Registry:** `manifests/components.v1.json`

## Status and claim ceiling

Current status: `source_policy_active_live_governance_external`.

**Claim ceiling:** immutable CI orchestration and source-policy verification only; no human approval, repository administration, production signing, or release authority.

This component is interpreted under the repository's evidence-tier and
invalidation rules. Source completeness and passing local tests establish only
the status above. They do not imply protected governance, integrated-main,
installed-product, physical-hardware, signing, or release authority unless the
applicable gate records independently bound evidence.

## Responsibilities

- Run repository, Python, Rust, Servo, image, governance, and late-stage source gates against an exact Git object.
- Record bounded evidence identities while preserving each workflow claim ceiling.
- Keep concurrency, timeouts, action pins, checkout credential handling, and workflow inventory reviewable.
- Route security-sensitive paths through CODEOWNERS and the D0T-03 source contract.

The component must keep these responsibilities explicit enough that reviewers
can identify the exact authority boundary, inputs, outputs, failure modes, and
evidence producer without inferring behavior from filenames alone.

## Non-responsibilities

- It cannot create an independent human approval or count an author/bot review as independent.
- It cannot configure branch protection, organization teams, rulesets, environments, or secrets without separately granted Administration authority.
- It cannot manufacture physical hardware, elapsed endurance time, HSM custody, or production signatures.

These exclusions are normative. A downstream caller, workflow, fixture, or
document may not widen the component by relabeling a lower-tier result.

## Dependency and call direction

A GitHub push or pull-request event selects one immutable commit. Checkout runs with persisted credentials disabled, then each workflow invokes fixed local entrypoints and pinned third-party actions. Results flow outward as check runs and immutable artifacts; no workflow is permitted to write a replacement source head or silently widen a gate.

The allowed direction is from higher-level trusted policy into this bounded
mechanism and back through typed results. Reverse dependencies that let a lower
trust surface select policy, credentials, arbitrary paths, commands, devices,
network destinations, signing keys, or promotion state are forbidden unless a
new reviewed contract explicitly introduces that authority.

## Public interfaces and entrypoints

Registered entrypoints:

- `.github/CODEOWNERS`
- `.github/workflows/ci.yml`
- `.github/workflows/governance-integrity.yml`

Architecture references:

- `docs/security/D0T03_REPOSITORY_GOVERNANCE.md`
- `docs/plan/GATE_CONTRACTS_AND_INVALIDATION.md`

Contract references:

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

Workflow state is external GitHub Actions state plus immutable artifacts. Jobs are bounded by explicit timeouts and concurrency groups. Cancellation, runner unavailability, and infrastructure failure are distinct from product failure. A cancelled or skipped job is never normalized to success, and a later source/base movement invalidates the earlier packet.

Partial completion is never upgraded to success. Timeout, cancellation,
infrastructure failure, product failure, stale evidence, and indeterminate
external outcome remain distinct states. A retry must bind to the same exact
inputs or create a new evidence identity; it must not overwrite the historical
failure packet.

## Security invariants

- all external actions are pinned to reviewed 40-hex commits
- pull-request workflows are read-only and cannot approve or merge pull requests
- candidate evidence never substitutes for independent review or exact-main evidence

In addition, repository-relative paths must be canonical and read without
following symlinks where they influence authority or evidence. Structured data
must reject duplicate keys and malformed identities. Secrets and page content
must not enter logs or artifacts unless a reviewed redaction contract permits
specific bounded fields.

## Testing and evidence

Registered tests:

- `tests/test_validate_governance_integrity.py`
- `tests/test_d0t03_source.py`

Registered workflows:

- `.github/workflows/ci.yml`
- `.github/workflows/governance-integrity.yml`
- `.github/workflows/d0t03-source-contract.yml`

Tests must include positive behavior and hostile boundary cases. Evidence must
record exact source/base/tree or image/input identities, workflow and artifact
IDs, bounded output digests, claim ceiling, and invalidation triggers. A verifier
self-test proves the verifier rejects bad fixtures; it does not prove a separate
producer generated authentic higher-tier evidence.

## Operations and troubleshooting

Operators inspect the exact run, job, head SHA, tree SHA, artifact digest, and claim ceiling. A queued self-hosted job is availability information only. Administration failures must be captured before retrying; credentials are never printed. Temporary diagnostic workflows belong on isolated branches and must not become a second convergence surface.

Operational diagnosis starts from the first failed invariant and the exact
input object. Do not make a gate green by broadening permissions, accepting
missing fields, following symlinks, selecting a different process/device,
disabling negative cases, or rewriting expected evidence after the fact.

## Compatibility and change protocol

Adding or renaming a workflow requires updates to the governance contract, repository-governance manifest, action-pin manifest, gate invalidation paths, tests, this component registry, and this document. Any permission increase, pull_request_target use, source-writing step, mutable action ref, or dynamic shell execution is a security-boundary change requiring independent review.

Every change must also update `manifests/components.v1.json` when paths,
entrypoints, ownership, references, status, security invariants, or claim
ceilings move. Run `python3 tools/validate_component_documentation.py`, the
project/repository validators, authoritative Python discovery, and the locked
Rust matrix before requesting independent review.
