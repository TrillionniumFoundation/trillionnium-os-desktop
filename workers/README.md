# wasi-worker-boundary

**Component registry ID:** `wasi-worker-boundary`
**Component path:** `workers`
**Owner class:** `sandbox-and-capability-security`
**Plan revision:** `2026-08-29-d6`
**Registry:** `manifests/components.v1.json`

## Status and claim ceiling

Current status: `reserved_wasi_component_boundary`.

**Claim ceiling:** documented future WASI Component worker boundary only; no worker runtime, ambient capability, installed component, or external effect.

This component is interpreted under the repository's evidence-tier and
invalidation rules. Source completeness and passing local tests establish only
the status above. They do not imply protected governance, integrated-main,
installed-product, physical-hardware, signing, or release authority unless the
applicable gate records independently bound evidence.

## Responsibilities

- Reserve the source boundary for future WASI Component workers with explicit WIT-style interfaces.
- Document capability injection, deterministic execution, resource limits, cancellation, and output validation requirements.
- Keep worker code distinct from trusted apps, browser content, platform adapters, and privileged services.
- Define the tests and installed-image evidence required before a worker is accepted.

The component must keep these responsibilities explicit enough that reviewers
can identify the exact authority boundary, inputs, outputs, failure modes, and
evidence producer without inferring behavior from filenames alone.

## Non-responsibilities

- No worker implementation, runtime, component registry, or WIT package is currently shipped.
- The boundary does not grant network, filesystem, process, device, credential, effect, update, signing, or publication authority.
- D5/D6 reference policy does not prove a sandboxed worker exists.

These exclusions are normative. A downstream caller, workflow, fixture, or
document may not widen the component by relabeling a lower-tier result.

## Dependency and call direction

The intended path is a trusted caller selecting a signed worker identity and typed operation, issuing narrowly scoped capabilities, invoking the worker in a resource-bounded runtime, validating typed output, and separately requesting any permitted external effect. The worker never receives raw ambient handles.

The allowed direction is from higher-level trusted policy into this bounded
mechanism and back through typed results. Reverse dependencies that let a lower
trust surface select policy, credentials, arbitrary paths, commands, devices,
network destinations, signing keys, or promotion state are forbidden unless a
new reviewed contract explicitly introduces that authority.

## Public interfaces and entrypoints

Registered entrypoints:

- `No executable or installed entrypoint is currently registered.`

Architecture references:

- `docs/architecture/CAPABILITY_AND_CONTROLLED_EGRESS.md`
- `docs/architecture/TRUSTED_APP_BUNDLES.md`

Contract references:

- `contracts/capability-permit.v1.schema.json`
- `contracts/trusted-app-bundle.v1.json`

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

Future workers must have deterministic explicit state inputs or isolated versioned storage. Host calls require deadlines and cancellation; crash or timeout returns a typed terminal/indeterminate result. Capability expiry and revocation must be checked at use time, not only at instantiation.

Partial completion is never upgraded to success. Timeout, cancellation,
infrastructure failure, product failure, stale evidence, and indeterminate
external outcome remain distinct states. A retry must bind to the same exact
inputs or create a new evidence identity; it must not overwrite the historical
failure packet.

## Security invariants

- workers receive no ambient filesystem, network, device, process, secret, or update authority
- all imports are versioned typed interfaces authorized by short-lived capabilities
- worker output cannot directly trigger external effects or release operations

In addition, repository-relative paths must be canonical and read without
following symlinks where they influence authority or evidence. Structured data
must reject duplicate keys and malformed identities. Secrets and page content
must not enter logs or artifacts unless a reviewed redaction contract permits
specific bounded fields.

## Testing and evidence

Registered tests:

- `tests/d5/test_trusted_app_bundle.py`
- `tests/d6/test_capability_egress_reference.py`

Registered workflows:

- `.github/workflows/d5-trusted-app.yml`
- `.github/workflows/d6-capability-egress.yml`

Tests must include positive behavior and hostile boundary cases. Evidence must
record exact source/base/tree or image/input identities, workflow and artifact
IDs, bounded output digests, claim ceiling, and invalidation triggers. A verifier
self-test proves the verifier rejects bad fixtures; it does not prove a separate
producer generated authentic higher-tier evidence.

## Operations and troubleshooting

Before adding a worker, freeze the runtime/toolchain, WIT interfaces, component digest, resource limits, host import list, storage scope, and logging policy. Test denied imports, oversized input/output, fuel/memory exhaustion, cancellation, crash, stale permits, and replay. Keep the feature disabled by default until exact-image review.

Operational diagnosis starts from the first failed invariant and the exact
input object. Do not make a gate green by broadening permissions, accepting
missing fields, following symlinks, selecting a different process/device,
disabling negative cases, or rewriting expected evidence after the fact.

## Compatibility and change protocol

Any new import, capability, storage namespace, runtime version, or worker digest is an authority and compatibility change. Update contracts, manifests, threat model, tests, packaging, component registry, and evidence workflows together; independent review is required before product activation.

Every change must also update `manifests/components.v1.json` when paths,
entrypoints, ownership, references, status, security invariants, or claim
ceilings move. Run `python3 tools/validate_component_documentation.py`, the
project/repository validators, authoritative Python discovery, and the locked
Rust matrix before requesting independent review.
