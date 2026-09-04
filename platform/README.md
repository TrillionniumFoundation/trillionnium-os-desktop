# platform-boundary

**Component registry ID:** `platform-boundary`
**Component path:** `platform`
**Owner class:** `platform-security`
**Plan revision:** `2026-08-29-d6`
**Registry:** `manifests/components.v1.json`

## Status and claim ceiling

Current status: `reserved_boundary_no_product_adapter`.

**Claim ceiling:** documented future compositor, input, audio, device, portal, and network adapter boundary only; no implementation or platform authority.

This component is interpreted under the repository's evidence-tier and
invalidation rules. Source completeness and passing local tests establish only
the status above. They do not imply protected governance, integrated-main,
installed-product, physical-hardware, signing, or release authority unless the
applicable gate records independently bound evidence.

## Responsibilities

- Reserve the product-owned location for native compositor, portal, input, audio, device, and network adapters.
- Document call direction from trusted policy/services into narrow platform mechanisms.
- Keep future native integration visibly separate from engine-neutral Rust models and test fixtures.
- Define the evidence expected before any adapter can be considered installed product authority.

The component must keep these responsibilities explicit enough that reviewers
can identify the exact authority boundary, inputs, outputs, failure modes, and
evidence producer without inferring behavior from filenames alone.

## Non-responsibilities

- There is currently no platform implementation in this directory.
- Reference models in crates/tools do not satisfy this boundary.
- No display, clipboard, drag/drop, audio, device, network namespace, portal, or peer-IP enforcement is claimed.

These exclusions are normative. A downstream caller, workflow, fixture, or
document may not widen the component by relabeling a lower-tier result.

## Dependency and call direction

The intended direction is trusted session policy to a typed capability service, then to a narrow platform adapter, then to the operating-system primitive. Results return as typed outcomes and durable receipt facts. Web content and Agent inputs never select arbitrary commands, device paths, destinations, or privileged operations.

The allowed direction is from higher-level trusted policy into this bounded
mechanism and back through typed results. Reverse dependencies that let a lower
trust surface select policy, credentials, arbitrary paths, commands, devices,
network destinations, signing keys, or promotion state are forbidden unless a
new reviewed contract explicitly introduces that authority.

## Public interfaces and entrypoints

Registered entrypoints:

- `No executable or installed entrypoint is currently registered.`

Architecture references:

- `docs/architecture/HUMAN_AGENT_COLLABORATION.md`
- `docs/architecture/CAPABILITY_AND_CONTROLLED_EGRESS.md`

Contract references:

- `contracts/human-agent-collaboration.v1.json`
- `contracts/capability-egress.v1.json`

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

Future adapters must treat kernel/compositor/portal state as untrusted external state, bind every operation to a principal and revision, and surface timeout, cancellation, crash, restart, and indeterminate outcomes. The current directory intentionally contains no mutable runtime state.

Partial completion is never upgraded to success. Timeout, cancellation,
infrastructure failure, product failure, stale evidence, and indeterminate
external outcome remain distinct states. A retry must bind to the same exact
inputs or create a new evidence identity; it must not overwrite the historical
failure packet.

## Security invariants

- web content and agents receive no ambient compositor, device, portal, or network authority
- future adapters must preserve typed capability and PageOwner boundaries
- placeholder documentation is never treated as installed integration

In addition, repository-relative paths must be canonical and read without
following symlinks where they influence authority or evidence. Structured data
must reject duplicate keys and malformed identities. Secrets and page content
must not enter logs or artifacts unless a reviewed redaction contract permits
specific bounded fields.

## Testing and evidence

Registered tests:

- `tests/d4/test_collaboration_reference.py`
- `tests/d6/test_capability_egress_reference.py`

Registered workflows:

- `.github/workflows/d4-collaboration.yml`
- `.github/workflows/d6-capability-egress.yml`

Tests must include positive behavior and hostile boundary cases. Evidence must
record exact source/base/tree or image/input identities, workflow and artifact
IDs, bounded output digests, claim ceiling, and invalidation triggers. A verifier
self-test proves the verifier rejects bad fixtures; it does not prove a separate
producer generated authentic higher-tier evidence.

## Operations and troubleshooting

Any new source file here is a gate-opening event. Before enabling it, add a component entrypoint, package/install path, contract, hostile tests, exact-image workflow, operational diagnostics, and explicit negative cases. Keep the default product behavior unchanged until evidence is reviewed.

Operational diagnosis starts from the first failed invariant and the exact
input object. Do not make a gate green by broadening permissions, accepting
missing fields, following symlinks, selecting a different process/device,
disabling negative cases, or rewriting expected evidence after the fact.

## Compatibility and change protocol

Platform APIs are high-authority compatibility boundaries. Changes require threat-model review, dependency/call-direction documentation, deny-by-default policy, revocation and lifecycle semantics, image integration, exact-image evidence, and independent security approval. Source presence alone never updates the gate status.

Every change must also update `manifests/components.v1.json` when paths,
entrypoints, ownership, references, status, security invariants, or claim
ceilings move. Run `python3 tools/validate_component_documentation.py`, the
project/repository validators, authoritative Python discovery, and the locked
Rust matrix before requesting independent review.
