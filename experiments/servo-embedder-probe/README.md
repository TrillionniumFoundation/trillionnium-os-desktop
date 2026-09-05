# servo-embedder-probe

**Component registry ID:** `servo-embedder-probe`
**Component path:** `experiments/servo-embedder-probe`
**Owner class:** `servo-integration`
**Plan revision:** `2026-08-29-d6`
**Registry:** `manifests/components.v1.json`

## Status and claim ceiling

Current status: `exact_pin_compile_probe`.

**Claim ceiling:** compile compatibility against the pinned Servo public API only; no execution, visible frame, input delivery, recovery, image, or release claim.

This component is interpreted under the repository's evidence-tier and
invalidation rules. Source completeness and passing local tests establish only
the status above. They do not imply protected governance, integrated-main,
installed-product, physical-hardware, signing, or release authority unless the
applicable gate records independently bound evidence.

## Responsibilities

- Compile a minimal external embedder against the exact pinned Servo checkout.
- Detect API drift in builder, event-loop, WebView, input, screenshot, popup, crash, and accessibility surfaces.
- Bind qualification output to Servo commit, lockfile, toolchain, probe source, and workflow identity.
- Provide an early compatibility sentinel before expensive headed/image qualification.

The component must keep these responsibilities explicit enough that reviewers
can identify the exact authority boundary, inputs, outputs, failure modes, and
evidence producer without inferring behavior from filenames alone.

## Non-responsibilities

- The executable is not run by D0A-01 and therefore proves no pixels, input, IME, process topology, or recovery.
- It does not establish trusted chrome composition or navigation policy.
- It does not make a Servo API production-supported or independently reviewed.

These exclusions are normative. A downstream caller, workflow, fixture, or
document may not widen the component by relabeling a lower-tier result.

## Dependency and call direction

The workflow fetches the exact Servo input, verifies lock and patch identities, copies this source into Servo as a reviewed example target, and builds with Servo’s own toolchain and lockfile. Build metadata is packaged into a bounded evidence envelope; no runtime path is invoked.

The allowed direction is from higher-level trusted policy into this bounded
mechanism and back through typed results. Reverse dependencies that let a lower
trust surface select policy, credentials, arbitrary paths, commands, devices,
network destinations, signing keys, or promotion state are forbidden unless a
new reviewed contract explicitly introduces that authority.

## Public interfaces and entrypoints

Registered entrypoints:

- `experiments/servo-embedder-probe/src/main.rs`

Architecture references:

- `docs/architecture/SERVO_EMBEDDER_COMPATIBILITY.md`
- `docs/architecture/TRUSTED_WORKSPACE_COMPOSITION.md`

Contract references:

- `contracts/workspace-composition.v1.json`

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

The probe has no persistent runtime state. Its meaningful state is the immutable input tuple and compiler result. A change to the Servo pin, patch ledger, Rust channel, Cargo lock, probe source, workflow, or evidence tool invalidates the prior compile packet.

Partial completion is never upgraded to success. Timeout, cancellation,
infrastructure failure, product failure, stale evidence, and indeterminate
external outcome remain distinct states. A retry must bind to the same exact
inputs or create a new evidence identity; it must not overwrite the historical
failure packet.

## Security invariants

- Servo source, Cargo lock, and Rust toolchain identities are exact inputs
- the compile probe is never reclassified as headed or product evidence
- mutable upstream refs and local patch drift fail closed

In addition, repository-relative paths must be canonical and read without
following symlinks where they influence authority or evidence. Structured data
must reject duplicate keys and malformed identities. Secrets and page content
must not enter logs or artifacts unless a reviewed redaction contract permits
specific bounded fields.

## Testing and evidence

Registered tests:

- `tests/test_servo_exact_pin_identity.py`
- `tests/test_servo_exact_pin_workflow.py`

Registered workflows:

- `.github/workflows/servo-exact-pin.yml`

Tests must include positive behavior and hostile boundary cases. Evidence must
record exact source/base/tree or image/input identities, workflow and artifact
IDs, bounded output digests, claim ceiling, and invalidation triggers. A verifier
self-test proves the verifier rejects bad fixtures; it does not prove a separate
producer generated authentic higher-tier evidence.

## Operations and troubleshooting

Diagnose failures by comparing the pinned Servo commit and compiler diagnostics rather than loosening API expectations. Keep patches in the reviewed patch ledger. Never switch to a branch/tag or bypass Servo’s lockfile to make the probe green.

Operational diagnosis starts from the first failed invariant and the exact
input object. Do not make a gate green by broadening permissions, accepting
missing fields, following symlinks, selecting a different process/device,
disabling negative cases, or rewriting expected evidence after the fact.

## Compatibility and change protocol

Every selected Servo API must be justified in the compatibility architecture document and covered by exact-pin tests. Removing a surface requires updating the requirements manifest and downstream runtime plan. Adding a surface is a source compatibility change, not proof that the headed product uses it correctly.

Every change must also update `manifests/components.v1.json` when paths,
entrypoints, ownership, references, status, security invariants, or claim
ceilings move. Run `python3 tools/validate_component_documentation.py`, the
project/repository validators, authoritative Python discovery, and the locked
Rust matrix before requesting independent review.
