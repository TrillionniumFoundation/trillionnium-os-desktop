# service-boundary

**Component registry ID:** `service-boundary`
**Component path:** `services`
**Owner class:** `service-authority-security`
**Plan revision:** `2026-08-29-d6`
**Registry:** `manifests/components.v1.json`

## Status and claim ceiling

Current status: `reserved_authority_split_no_service_implementation`.

**Claim ceiling:** documented future service decomposition only; no running portal, egress, effect, update, rollback, signing, or privileged daemon.

This component is interpreted under the repository's evidence-tier and
invalidation rules. Source completeness and passing local tests establish only
the status above. They do not imply protected governance, integrated-main,
installed-product, physical-hardware, signing, or release authority unless the
applicable gate records independently bound evidence.

## Responsibilities

- Reserve boundaries for unprivileged session supervision, capability services, controlled egress, effect execution, and minimal update/rollback authority.
- Document process identity, systemd ownership, IPC direction, persistence, and crash/restart expectations.
- Prevent future convenience daemons from accumulating unrelated authority.
- Define required installed-image and fault evidence before service activation.

The component must keep these responsibilities explicit enough that reviewers
can identify the exact authority boundary, inputs, outputs, failure modes, and
evidence producer without inferring behavior from filenames alone.

## Non-responsibilities

- There are no service implementations or installed units in this directory today.
- Existing systemd AgentPort units under packaging remain profile-separated packaging inputs, not proof of later services.
- Reference effect/update models do not execute external actions or alter boot slots.

These exclusions are normative. A downstream caller, workflow, fixture, or
document may not widen the component by relabeling a lower-tier result.

## Dependency and call direction

The intended architecture passes principal-bound typed requests from trusted policy to one narrow service. The service validates its own capability, performs one bounded mechanism, and returns a typed result that is recorded as facts. Signing and publication remain offline/separate from online update orchestration.

The allowed direction is from higher-level trusted policy into this bounded
mechanism and back through typed results. Reverse dependencies that let a lower
trust surface select policy, credentials, arbitrary paths, commands, devices,
network destinations, signing keys, or promotion state are forbidden unless a
new reviewed contract explicitly introduces that authority.

## Public interfaces and entrypoints

Registered entrypoints:

- `No executable or installed entrypoint is currently registered.`

Architecture references:

- `docs/architecture/SYSTEMD_AGENT_PORT_CUSTODY.md`
- `docs/architecture/RECOVERY_UPDATE_AND_EFFECT_RECONCILIATION.md`

Contract references:

- `contracts/agent-port-custody.v1.json`
- `contracts/recovery-update-reconciliation.v1.json`

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

Each future service must define durable versus ephemeral state, idempotency, cancellation, timeout, crash recovery, restart, and indeterminate outcomes. Effect journals record facts but do not replay authority. Update state must separate downloaded, verified, staged, activated, confirmed, and rolled-back slots.

Partial completion is never upgraded to success. Timeout, cancellation,
infrastructure failure, product failure, stale evidence, and indeterminate
external outcome remain distinct states. A retry must bind to the same exact
inputs or create a new evidence identity; it must not overwrite the historical
failure packet.

## Security invariants

- no single service may combine browser input, capability issuance, external effects, update, and signing authority
- privileged operations require narrow typed interfaces and least-privilege identities
- a reserved service name or design never counts as an installed daemon

In addition, repository-relative paths must be canonical and read without
following symlinks where they influence authority or evidence. Structured data
must reject duplicate keys and malformed identities. Secrets and page content
must not enter logs or artifacts unless a reviewed redaction contract permits
specific bounded fields.

## Testing and evidence

Registered tests:

- `tests/test_agent_port_custody_workflow.py`
- `tests/d7/test_effect_reconciliation_reference.py`

Registered workflows:

- `.github/workflows/agent-port-custody.yml`
- `.github/workflows/d7-recovery-update.yml`

Tests must include positive behavior and hostile boundary cases. Evidence must
record exact source/base/tree or image/input identities, workflow and artifact
IDs, bounded output digests, claim ceiling, and invalidation triggers. A verifier
self-test proves the verifier rejects bad fixtures; it does not prove a separate
producer generated authentic higher-tier evidence.

## Operations and troubleshooting

A service is not operational until its binary, package ownership, systemd unit, sandbox, users/groups, socket path, logs/metrics, health checks, rollback procedure, and exact-image tests exist. Operators must be able to disable it without enabling broader authority.

Operational diagnosis starts from the first failed invariant and the exact
input object. Do not make a gate green by broadening permissions, accepting
missing fields, following symlinks, selecting a different process/device,
disabling negative cases, or rewriting expected evidence after the fact.

## Compatibility and change protocol

New services require a dedicated module/component entry, contract, threat model, systemd/package integration, hostile identity and IPC tests, failure semantics, and exact-image evidence. Combining authority domains or adding ambient filesystem/network/device access is a security redesign requiring independent review.

Every change must also update `manifests/components.v1.json` when paths,
entrypoints, ownership, references, status, security invariants, or claim
ceilings move. Run `python3 tools/validate_component_documentation.py`, the
project/repository validators, authoritative Python discovery, and the locked
Rust matrix before requesting independent review.
