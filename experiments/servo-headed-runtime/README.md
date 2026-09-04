# servo-headed-runtime

**Component registry ID:** `servo-headed-runtime`
**Component path:** `experiments/servo-headed-runtime`
**Owner class:** `servo-runtime-security`
**Plan revision:** `2026-08-29-d6`
**Registry:** `manifests/components.v1.json`

## Status and claim ceiling

Current status: `headed_host_and_d2i_candidate_runtime`.

**Claim ceiling:** single local fixture, trusted chrome, native input, bounded IME, and causal content-process recovery only; no native clipboard, clean teardown guarantee, AgentPort, external effects, hardware, or release.

This component is interpreted under the repository's evidence-tier and
invalidation rules. Source completeness and passing local tests establish only
the status above. They do not imply protected governance, integrated-main,
installed-product, physical-hardware, signing, or release authority unless the
applicable gate records independently bound evidence.

## Responsibilities

- Own the headed-host and integrated-image local-fixture Servo runtime used by D0A-02 and D2I.
- Forward bounded native pointer, button, wheel, keyboard, and IME events to one WebView.
- Capture trusted/full/content pixels and causal process-topology evidence.
- Survive an externally supervised generation-1 content-child SIGKILL and create generation 2 while trusted chrome remains alive.

The component must keep these responsibilities explicit enough that reviewers
can identify the exact authority boundary, inputs, outputs, failure modes, and
evidence producer without inferring behavior from filenames alone.

## Non-responsibilities

- It does not start the production AgentPort, map semantic principals, execute external effects, or browse arbitrary origins.
- It does not prove native clipboard or a clean Servo teardown path.
- A headed-host or QEMU result does not qualify fixed hardware, signing, or publication.

These exclusions are normative. A downstream caller, workflow, fixture, or
document may not widen the component by relabeling a lower-tier result.

## Dependency and call direction

The runtime creates one native window, paints trusted chrome, renders one Servo WebView offscreen, and composites content below chrome. A local HTTP fixture supplies deterministic content. Native events enter the trusted event loop and are forwarded to Servo. An external supervisor selects the single canonical content child, sends SIGKILL, and observes replacement through the normal builder path.

The allowed direction is from higher-level trusted policy into this bounded
mechanism and back through typed results. Reverse dependencies that let a lower
trust surface select policy, credentials, arbitrary paths, commands, devices,
network destinations, signing keys, or promotion state are forbidden unless a
new reviewed contract explicitly introduces that authority.

## Public interfaces and entrypoints

Registered entrypoints:

- `experiments/servo-headed-runtime/src/main.rs`
- `experiments/servo-headed-runtime/fixture/index.html`

Architecture references:

- `docs/architecture/SERVO_EMBEDDER_COMPATIBILITY.md`
- `docs/architecture/RUNTIME_TOPOLOGY_AND_FAILURE_MODEL.md`
- `docs/architecture/D2I_INTEGRATED_IMAGE.md`

Contract references:

- `contracts/workspace-composition.v1.json`
- `contracts/d2i-integrated-image.v1.json`

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

Qualification state tracks load/frame readiness, screenshot identities, input and IME callbacks, navigation/popup denials, process generation, crash selection, trusted-window survival, and recovery. Asynchronous delegate transitions post a drive event so the loop cannot sleep after the final prerequisite. Any missing, duplicate, or inconsistent predicate produces a bounded failure record.

Partial completion is never upgraded to success. Timeout, cancellation,
infrastructure failure, product failure, stale evidence, and indeterminate
external outcome remain distinct states. A retry must bind to the same exact
inputs or create a new evidence identity; it must not overwrite the historical
failure packet.

## Security invariants

- exactly one untrusted Servo surface is composited below compositor-owned trusted chrome
- navigation is restricted to the ephemeral loopback fixture and popups are denied
- only one canonical direct content child selected by strict process identity may be killed
- runtime diagnostics never widen a failed predicate into success

In addition, repository-relative paths must be canonical and read without
following symlinks where they influence authority or evidence. Structured data
must reject duplicate keys and malformed identities. Secrets and page content
must not enter logs or artifacts unless a reviewed redaction contract permits
specific bounded fields.

## Testing and evidence

Registered tests:

- `tests/test_d0a_evidence_hardening.py`
- `tests/d1/test_d2i_contract.py`

Registered workflows:

- `.github/workflows/servo-headed-runtime.yml`
- `.github/workflows/d2i-integrated-image.yml`

Tests must include positive behavior and hostile boundary cases. Evidence must
record exact source/base/tree or image/input identities, workflow and artifact
IDs, bounded output digests, claim ceiling, and invalidation triggers. A verifier
self-test proves the verifier rejects bad fixtures; it does not prove a separate
producer generated authentic higher-tier evidence.

## Operations and troubleshooting

Use X11/Xvfb for headed-host runs and Q35/TCG for integrated-image runs. Inspect `runtime-state.json` before changing acceptance logic. Zero or multiple content-child candidates are product failures, not reasons to select heuristically. Preserve failure artifacts and the explicit no-clipboard/no-clean-teardown ceiling.

Operational diagnosis starts from the first failed invariant and the exact
input object. Do not make a gate green by broadening permissions, accepting
missing fields, following symlinks, selecting a different process/device,
disabling negative cases, or rewriting expected evidence after the fact.

## Compatibility and change protocol

Changes to window ownership, composition, input forwarding, process selection, navigation policy, screenshots, runtime-state fields, or the fixture invalidate D0A-02 and D2I evidence. Update source, contracts, tests, workflows, manifests, and evidence readers together, then rerun the exact candidate and exact main.

Every change must also update `manifests/components.v1.json` when paths,
entrypoints, ownership, references, status, security invariants, or claim
ceilings move. Run `python3 tools/validate_component_documentation.py`, the
project/repository validators, authoritative Python discovery, and the locked
Rust matrix before requesting independent review.
