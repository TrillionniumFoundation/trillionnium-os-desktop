# runtime-boundary

**Component registry ID:** `runtime-boundary`
**Component path:** `runtime`
**Owner class:** `runtime-topology-security`
**Plan revision:** `2026-08-29-d6`
**Registry:** `manifests/components.v1.json`

## Status and claim ceiling

Current status: `canonical_runtime_pointer_no_duplicate_implementation`.

`runtime_internal_injector: false`

**Claim ceiling:** source-boundary documentation identifying the canonical Servo runtime and external crash injector only; no additional runtime implementation.

This component is interpreted under the repository's evidence-tier and
invalidation rules. Source completeness and passing local tests establish only
the status above. They do not imply protected governance, integrated-main,
installed-product, physical-hardware, signing, or release authority unless the
applicable gate records independently bound evidence.

## Responsibilities

- Declare the canonical headed runtime location and reject duplicate or superseded runtime implementations.
- Document trusted parent, untrusted content process, external supervisor, and evidence-verifier boundaries.
- Keep D2I and D3 runtime claim ceilings visible to build and review tooling.
- Provide a reserved location if future product runtime glue must be separated from experiments.

The component must keep these responsibilities explicit enough that reviewers
can identify the exact authority boundary, inputs, outputs, failure modes, and
evidence producer without inferring behavior from filenames alone.

## Non-responsibilities

- No executable source currently lives here.
- The directory does not implement BrowserActor dispatch, semantic resolution, AgentPort, or effects.
- It does not prove a process crash, recovery, image boot, or production activation.

These exclusions are normative. A downstream caller, workflow, fixture, or
document may not widen the component by relabeling a lower-tier result.

## Dependency and call direction

Current runtime execution flows through `experiments/servo-headed-runtime/src/main.rs`; D2I installs that exact source-derived binary, while an external systemd supervisor selects and kills the content child. D3 evidence must separately bind the PageOwner/BrowserActor path. This directory prevents an orphan source file from becoming an ambiguous authority surface.

The allowed direction is from higher-level trusted policy into this bounded
mechanism and back through typed results. Reverse dependencies that let a lower
trust surface select policy, credentials, arbitrary paths, commands, devices,
network destinations, signing keys, or promotion state are forbidden unless a
new reviewed contract explicitly introduces that authority.

## Public interfaces and entrypoints

Registered entrypoints:

- `No executable or installed entrypoint is currently registered.`

Architecture references:

- `docs/architecture/RUNTIME_TOPOLOGY_AND_FAILURE_MODEL.md`
- `docs/architecture/D3_INTEGRATED_RUNTIME_QUALIFICATION.md`

Contract references:

- `contracts/d2i-integrated-image.v1.json`
- `contracts/d3-integrated-runtime-evidence.v1.json`

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

The boundary itself is stateless. Runtime state belongs to the canonical experiment/product processes and their evidence artifacts. A second implementation, hidden injector, or unregistered binary is a consistency failure because reviewers could no longer determine which path carries authority.

Partial completion is never upgraded to success. Timeout, cancellation,
infrastructure failure, product failure, stale evidence, and indeterminate
external outcome remain distinct states. A retry must bind to the same exact
inputs or create a new evidence identity; it must not overwrite the historical
failure packet.

## Security invariants

- there is one canonical headed Servo runtime source, not parallel unbuilt implementations
- content-process fault injection is external and cannot be mistaken for an in-process product command
- runtime boundary documentation cannot activate the product listener

In addition, repository-relative paths must be canonical and read without
following symlinks where they influence authority or evidence. Structured data
must reject duplicate keys and malformed identities. Secrets and page content
must not enter logs or artifacts unless a reviewed redaction contract permits
specific bounded fields.

## Testing and evidence

Registered tests:

- `tests/d1/test_d2i_injector_safety.py`
- `tests/d3/test_d3_integrated_runtime_evidence.py`

Registered workflows:

- `.github/workflows/d2i-integrated-image.yml`
- `.github/workflows/d3-integrated-runtime-evidence.yml`

Tests must include positive behavior and hostile boundary cases. Evidence must
record exact source/base/tree or image/input identities, workflow and artifact
IDs, bounded output digests, claim ceiling, and invalidation triggers. A verifier
self-test proves the verifier rejects bad fixtures; it does not prove a separate
producer generated authentic higher-tier evidence.

## Operations and troubleshooting

When adding runtime code, first decide whether it belongs in the Servo experiment, a Cargo module, a platform adapter, or a service. Update build targets and workflow inputs before moving source. Search for all runtime paths and prove the old path is not referenced before removal.

Operational diagnosis starts from the first failed invariant and the exact
input object. Do not make a gate green by broadening permissions, accepting
missing fields, following symlinks, selecting a different process/device,
disabling negative cases, or rewriting expected evidence after the fact.

## Compatibility and change protocol

Changing the canonical runtime pointer or introducing executable source invalidates D0A-02, D2I, D3, packaging, workflows, component inventory, and architecture. The migration must remove ambiguity, retain historical evidence interpretation, and rerun exact-head and exact-main qualification.

Every change must also update `manifests/components.v1.json` when paths,
entrypoints, ownership, references, status, security invariants, or claim
ceilings move. Run `python3 tools/validate_component_documentation.py`, the
project/repository validators, authoritative Python discovery, and the locked
Rust matrix before requesting independent review.
