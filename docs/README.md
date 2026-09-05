# documentation-system

**Component registry ID:** `documentation-system`
**Component path:** `docs`
**Owner class:** `technical-governance`
**Plan revision:** `2026-08-29-d6`
**Registry:** `manifests/components.v1.json`

The non-Cargo documentation index is [`components/README.md`](components/README.md); Cargo workspace modules are indexed at [`modules/README.md`](modules/README.md).

## Status and claim ceiling

Current status: `normative_human_projection_with_machine_index`.

**Claim ceiling:** human-readable architecture, security, operations, and evidence interpretation only; live platform state and higher-tier proof remain external.

This component is interpreted under the repository's evidence-tier and
invalidation rules. Source completeness and passing local tests establish only
the status above. They do not imply protected governance, integrated-main,
installed-product, physical-hardware, signing, or release authority unless the
applicable gate records independently bound evidence.

## Responsibilities

- Publish the active plan, current-state projection, architecture, ADR, threat, operations, release, and evidence interpretation.
- Keep Cargo module and non-Cargo component documentation indexes synchronized with machine registries.
- Explain claim ceilings, invalidation paths, prerequisite order, authority boundaries, and troubleshooting procedures.
- Retain historical plans and evidence without allowing them to masquerade as current promotion truth.

The component must keep these responsibilities explicit enough that reviewers
can identify the exact authority boundary, inputs, outputs, failure modes, and
evidence producer without inferring behavior from filenames alone.

## Non-responsibilities

- Documentation does not prove a workflow ran, a branch is protected, a reviewer is independent, or a device survived a fault.
- Copied SHAs and run IDs are committed snapshots and must not be treated as live state.
- A detailed design does not grant product authority to placeholders or reference implementations.

These exclusions are normative. A downstream caller, workflow, fixture, or
document may not widen the component by relabeling a lower-tier result.

## Dependency and call direction

Machine truth in manifests and contracts is rendered into human-readable plan, state, architecture, and evidence documents. Reviewers start at the stable plan index, follow the active revision, inspect the current-state and blocker ledger, and then traverse gate-specific architecture, security, operations, and evidence files.

The allowed direction is from higher-level trusted policy into this bounded
mechanism and back through typed results. Reverse dependencies that let a lower
trust surface select policy, credentials, arbitrary paths, commands, devices,
network destinations, signing keys, or promotion state are forbidden unless a
new reviewed contract explicitly introduces that authority.

## Public interfaces and entrypoints

Registered entrypoints:

- `docs/DESKTOP_PLAN.md`
- `docs/CURRENT_STATE.md`
- `docs/MANIFEST.json`

Architecture references:

- `docs/plan/PROJECT_TRUTH_AND_EVIDENCE.md`
- `docs/architecture/RUNTIME_TOPOLOGY_AND_FAILURE_MODEL.md`

Contract references:

- `contracts/project-state.v1.schema.json`
- `contracts/gate-evidence-envelope.v1.schema.json`

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

The documentation tree has a canonical active revision plus retained historical revisions. `docs/MANIFEST.json` is a projection, not an independent source of truth, and is validated against project and repository state. Live PR/check/review/settings state is intentionally external and must be re-read at decision time.

Partial completion is never upgraded to success. Timeout, cancellation,
infrastructure failure, product failure, stale evidence, and indeterminate
external outcome remain distinct states. A retry must bind to the same exact
inputs or create a new evidence identity; it must not overwrite the historical
failure packet.

## Security invariants

- human prose cannot override machine truth or live GitHub state
- historical evidence remains labeled with its original object and claim ceiling
- documentation completeness never promotes an evidence tier

In addition, repository-relative paths must be canonical and read without
following symlinks where they influence authority or evidence. Structured data
must reject duplicate keys and malformed identities. Secrets and page content
must not enter logs or artifacts unless a reviewed redaction contract permits
specific bounded fields.

## Testing and evidence

Registered tests:

- `tests/test_d0a_claim_ceiling_docs.py`
- `tests/test_module_documentation.py`
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

Broken links, stale candidate identities, missing claim ceilings, or conflicting stage labels are failed gates. Review generated evidence with its source SHA, tested merge, workflow run, artifact digest, and freshness fields. Never edit generated evidence to simulate a rerun; rerun the producing workflow instead.

Operational diagnosis starts from the first failed invariant and the exact
input object. Do not make a gate green by broadening permissions, accepting
missing fields, following symlinks, selecting a different process/device,
disabling negative cases, or rewriting expected evidence after the fact.

## Compatibility and change protocol

Every implementation or authority-boundary change must update the affected module/component README, architecture/security text, machine registries, tests, and claim ceilings. A new plan revision requires a stable index update and explicit supersession rules. Historical files are amended only to clarify staleness, never to rewrite what was observed.

Every change must also update `manifests/components.v1.json` when paths,
entrypoints, ownership, references, status, security invariants, or claim
ceilings move. Run `python3 tools/validate_component_documentation.py`, the
project/repository validators, authoritative Python discovery, and the locked
Rust matrix before requesting independent review.

## Callback-shaped engine scheduling

The optional `callback_engine_pair` / `CallbackEngineOwner` path starts an
operation on its creator thread and accepts a single-use `EngineCompletion`
from a later callback. The application continues native events between pumps;
its timer follows the original deadline and bounded cancellation-check schedule.
Ordinary Act never substitutes for the dedicated atomic semantic hook. The
existing request endpoint now wakes on abandonment and Drop as well as enqueue.
Wakes may be coalesced and are not a count of dispatched operations.
See `docs/architecture/EVENT_LOOP_COMPLETION.md` and
`contracts/event-loop-completion.v1.json` for APIs, ordering, tests and limits.
This is source/host fixture evidence only: no Servo/native event loop, process
IPC, installed image or product authority is added. The development daemon
continues selecting its synchronous fixture backend; no activation changes.


## Callback development service integration

The persistent development service now uses the callback owner with an explicit
ImmediateCallbacks bridge for its existing deterministic fixture. The main
runner waits on a private notification predicate; worker completion is published
before wake and errors retire before join. This does not implement Servo, winit,
systemd activation or an installed image. See
`docs/architecture/D3_CALLBACK_SERVICE_RUNNER.md` and
`contracts/d3-callback-service-runner.v1.json`; the source regression guard is
`tools/audit_callback_service.py`, tested by
`tests/test_callback_service_runner.py`. Existing controls and promotion limits
remain unchanged. The immediate bridge does not make a blocking backend async.
