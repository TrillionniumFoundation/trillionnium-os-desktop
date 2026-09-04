# validation-toolchain

**Component registry ID:** `validation-toolchain`  
**Component path:** `tools`  
**Owner class:** `toolchain-security`  
**Plan revision:** `2026-08-29-d6`  
**Registry:** `manifests/components.v1.json`

## Status and claim ceiling

Current status: `reviewed_validation_and_evidence_toolchain`.

**Claim ceiling:** deterministic validation, reference modeling, image preparation, and evidence verification only; tools do not gain product, repository-admin, hardware, or signing authority.

This component is interpreted under the repository's evidence-tier and
invalidation rules. Source completeness and passing local tests establish only
the status above. They do not imply protected governance, integrated-main,
installed-product, physical-hardware, signing, or release authority unless the
applicable gate records independently bound evidence.

## Responsibilities

- Validate repository structure, machine truth, governance, documentation, module/component inventory, path custody, and late-stage packages.
- Implement deterministic reference models for transport, codec, semantic resolution, collaboration, capability/egress, update, reconciliation, hardware, and release policy.
- Prepare pinned image inputs and verify exact evidence envelopes, artifacts, and claim ceilings.
- Expose clear nonzero failures and machine-readable bounded outputs to CI.

The component must keep these responsibilities explicit enough that reviewers
can identify the exact authority boundary, inputs, outputs, failure modes, and
evidence producer without inferring behavior from filenames alone.

## Non-responsibilities

- Tools do not approve pull requests, configure GitHub administration, execute production effects, attest physical hardware, or access HSM keys.
- Reference implementations are not installed product adapters.
- A validator cannot turn missing evidence into success by checking its own source.

These exclusions are normative. A downstream caller, workflow, fixture, or
document may not widen the component by relabeling a lower-tier result.

## Dependency and call direction

Fixed CLI entrypoints read canonical repository-relative inputs, validate shape and identity, run bounded deterministic computation or external commands, and emit explicit results. Workflows supply immutable inputs through environment variables and arguments. Evidence verifiers consume artifacts produced by a distinct lane or identity.

The allowed direction is from higher-level trusted policy into this bounded
mechanism and back through typed results. Reverse dependencies that let a lower
trust surface select policy, credentials, arbitrary paths, commands, devices,
network destinations, signing keys, or promotion state are forbidden unless a
new reviewed contract explicitly introduces that authority.

## Public interfaces and entrypoints

Registered entrypoints:

- `tools/validate_repository.py`
- `tools/validate_project_truth.py`
- `tools/validate_governance_integrity.py`
- `tools/validate_component_documentation.py`

Architecture references:

- `docs/plan/PROJECT_TRUTH_AND_EVIDENCE.md`
- `docs/plan/CONTRACT_SECURITY_TESTING.md`

Contract references:

- `contracts/gate-evidence-envelope.v1.schema.json`
- `contracts/project-state.v1.schema.json`

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

Most tools are stateless; temporary files use isolated directories and atomic writes where required. Persistent journals/evidence are modeled explicitly. Validator facades synchronize test-overridable globals into reviewed implementation modules without dynamic source mutation. Failures accumulate deterministic diagnostics and exit nonzero.

Partial completion is never upgraded to success. Timeout, cancellation,
infrastructure failure, product failure, stale evidence, and indeterminate
external outcome remain distinct states. A retry must bind to the same exact
inputs or create a new evidence identity; it must not overwrite the historical
failure packet.

## Security invariants

- security-sensitive inputs are read without following symlinks or escaping the repository root
- JSON duplicate keys, malformed identities, partial evidence, and unknown authority fail closed
- facades import reviewed modules without source-string rewriting, exec, or compile tricks
- workflow-dispatched values are treated as bounded data, never shell source

In addition, repository-relative paths must be canonical and read without
following symlinks where they influence authority or evidence. Structured data
must reject duplicate keys and malformed identities. Secrets and page content
must not enter logs or artifacts unless a reviewed redaction contract permits
specific bounded fields.

## Testing and evidence

Registered tests:

- `tests/test_validate_repository_hardening.py`
- `tests/test_validator_loader_stability.py`
- `tests/test_component_documentation.py`

Registered workflows:

- `.github/workflows/ci.yml`
- `.github/workflows/governance-integrity.yml`

Tests must include positive behavior and hostile boundary cases. Evidence must
record exact source/base/tree or image/input identities, workflow and artifact
IDs, bounded output digests, claim ceiling, and invalidation triggers. A verifier
self-test proves the verifier rejects bad fixtures; it does not prove a separate
producer generated authentic higher-tier evidence.

## Operations and troubleshooting

Run tools from repository root with the locked Python/Rust environment. Preserve raw stderr and artifact inputs on failure. Never add network fetches without pinning and digest verification. Keep secrets out of arguments, logs, artifacts, and generated JSON. Review shell scripts for quoting, no-follow copy, and exit-status propagation.

Operational diagnosis starts from the first failed invariant and the exact
input object. Do not make a gate green by broadening permissions, accepting
missing fields, following symlinks, selecting a different process/device,
disabling negative cases, or rewriting expected evidence after the fact.

## Compatibility and change protocol

New tools require a documented owner, bounded input/output contract, hostile tests, workflow pinning/inventory, component registration, and gate invalidation coverage. Changing parser, path, subprocess, signing, or evidence semantics requires security review and exact-head reruns for every consuming gate.

Every change must also update `manifests/components.v1.json` when paths,
entrypoints, ownership, references, status, security invariants, or claim
ceilings move. Run `python3 tools/validate_component_documentation.py`, the
project/repository validators, authoritative Python discovery, and the locked
Rust matrix before requesting independent review.
