# test-system

**Component registry ID:** `test-system`
**Component path:** `tests`
**Owner class:** `verification-engineering`
**Plan revision:** `2026-08-29-d6`
**Registry:** `manifests/components.v1.json`

## Status and claim ceiling

Current status: `authoritative_discovered_python_and_shell_corpus`.

**Claim ceiling:** deterministic source, reference, verifier, QEMU harness, and hostile-regression tests only; tests do not self-promote runtime or external evidence.

This component is interpreted under the repository's evidence-tier and
invalidation rules. Source completeness and passing local tests establish only
the status above. They do not imply protected governance, integrated-main,
installed-product, physical-hardware, signing, or release authority unless the
applicable gate records independently bound evidence.

## Responsibilities

- Exercise contracts, validators, Rust integration, transport, receipts, Servo evidence, image tooling, D3-D9 reference models, and governance policy.
- Prove discovery completeness so a green top-level command cannot silently omit nested suites.
- Provide deterministic fixtures and negative cases for malformed, ambiguous, stale, unsafe, and partially completed inputs.
- Drive QEMU boot/fault harnesses under bounded, exact-input workflows.

The component must keep these responsibilities explicit enough that reviewers
can identify the exact authority boundary, inputs, outputs, failure modes, and
evidence producer without inferring behavior from filenames alone.

## Non-responsibilities

- A test pass cannot substitute for an independently produced runtime, hardware, or HSM transaction.
- Unit fixtures do not authorize production behavior.
- Tests do not alter machine truth or mark gates promoted; promotion consumes separately bound evidence.

These exclusions are normative. A downstream caller, workflow, fixture, or
document may not widen the component by relabeling a lower-tier result.

## Dependency and call direction

The authoritative Python discovery command imports every `test_*.py` module through package-marked directories. Rust tests run through the locked workspace. Workflow-specific tests invoke fixed tools and fixtures. QEMU scripts consume prepared immutable inputs and export results for independent verifiers.

The allowed direction is from higher-level trusted policy into this bounded
mechanism and back through typed results. Reverse dependencies that let a lower
trust surface select policy, credentials, arbitrary paths, commands, devices,
network destinations, signing keys, or promotion state are forbidden unless a
new reviewed contract explicitly introduces that authority.

## Public interfaces and entrypoints

Registered entrypoints:

- `tests/test_discovery_inventory.py`
- `tests/qemu/run-d1-pipeline.sh`
- `tests/qemu/run-d2i-boot-test.sh`

Architecture references:

- `docs/plan/CONTRACT_SECURITY_TESTING.md`
- `docs/plan/GATE_CONTRACTS_AND_INVALIDATION.md`

Contract references:

- `contracts/gate-evidence-envelope.v1.schema.json`
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

Tests should be hermetic and reset mutable globals, temporary roots, sockets, journals, and fixtures. Persistent evidence belongs outside test state and is bound to exact inputs. Timeouts, process exits, partial files, and infrastructure errors are surfaced separately from assertion failures.

Every test module must also pass when loaded first in a fresh interpreter. A
leading module may not monkey-patch shared helpers to make later modules pass.
The D8 fixture-isolation regressions therefore exercise the real factory, and
the Servo evidence loader regression removes ambient ``tools/`` path state
before importing the facade. Documentation claim regressions include
Cyrillic/Greek homoglyphs, combining marks, and mixed-script declaration
prefixes while retaining ordinary multilingual prose. Run the focused modules
and authoritative discovery when loader, fixture, or claim parsing changes.

Partial completion is never upgraded to success. Timeout, cancellation,
infrastructure failure, product failure, stale evidence, and indeterminate
external outcome remain distinct states. A retry must bind to the same exact
inputs or create a new evidence identity; it must not overwrite the historical
failure packet.

## Security invariants

- every nested Python test module and case is discoverable from the authoritative command
- fixtures cannot be mistaken for product binaries, production keys, hardware, or independent attestations
- hostile tests target fail-open paths, duplicate keys, symlinks, traversal, stale state, and authority confusion

In addition, repository-relative paths must be canonical and read without
following symlinks where they influence authority or evidence. Structured data
must reject duplicate keys and malformed identities. Secrets and page content
must not enter logs or artifacts unless a reviewed redaction contract permits
specific bounded fields.

## Testing and evidence

Registered tests:

- `tests/test_discovery_inventory.py`
- `tests/test_validate_project_truth.py`
- `tests/d1/test_d1_tools.py`

Registered workflows:

- `.github/workflows/ci.yml`
- `.github/workflows/d4-d9-source-suite.yml`

Tests must include positive behavior and hostile boundary cases. Evidence must
record exact source/base/tree or image/input identities, workflow and artifact
IDs, bounded output digests, claim ceiling, and invalidation triggers. A verifier
self-test proves the verifier rejects bad fixtures; it does not prove a separate
producer generated authentic higher-tier evidence.

## Operations and troubleshooting

Run focused suites while developing, then the authoritative discovery and locked Rust matrix. On hangs, identify the specific process/test and preserve diagnostics rather than weakening timeouts globally. Ensure generated `__pycache__`, target output, sockets, images, and secrets are never committed.

Operational diagnosis starts from the first failed invariant and the exact
input object. Do not make a gate green by broadening permissions, accepting
missing fields, following symlinks, selecting a different process/device,
disabling negative cases, or rewriting expected evidence after the fact.

## Compatibility and change protocol

Every new test directory requires `__init__.py` and discovery inventory coverage. New external commands require safe argument/data binding and no shell evaluation. A new gate or source mechanism needs positive, negative, malformed, cancellation, timeout, crash, stale, and authority-boundary cases.

Every change must also update `manifests/components.v1.json` when paths,
entrypoints, ownership, references, status, security invariants, or claim
ceilings move. Run `python3 tools/validate_component_documentation.py`, the
project/repository validators, authoritative Python discovery, and the locked
Rust matrix before requesting independent review.

## Receipt persistence-cut regression

The managed reopen path re-establishes file and directory durability before it
returns a writer. Development and maintenance details are in
`docs/architecture/RECEIPT_PERSISTENCE_FAULT_MODEL.md`. The private cfg(test)
library corpus exercises 128 injected I/O-error combinations; the separate
`journal_persistence_process` Cargo test target executes 64 actual SIGKILL
cutpoint cases over the exact journal source. Neither is physical power loss
or a product fault-control interface. Run both focused targets plus the full
workspace/default/all-feature and Python discovery matrices. The independent
process test has a custom harness; libtest name filters should use `--lib`.
Module/component registration and `tests/test_receipt_persistence_cuts.py` guard
source wiring, conditional compilation, durability order and claim ceilings.

## Engine-thread host boundary

`tests/test_engine_thread_dispatch_contract.py` checks the scheduler contract,
registered sources, documentation and Cargo/rustdoc CI wiring. Real connected
AF_UNIX/codec/actor/fixture-engine/receipt tests live in
`crates/hepta-browser-actor/src/engine_dispatch/transport_tests.rs`. Thread
affinity, cancellation and late-reply cases live alongside in `tests.rs`.
These are host mechanism tests, not real Servo or image evidence.

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

## Legacy receipt migration verification

`tests/test_receipt_migration.py` checks the source/contract, fault case inventory and CI links for the explicit offline copy. Rust migration tests and the separately compiled `journal_migration_process` target use real private files and process termination. These tests do not qualify installed-service cutover, physical power loss or anti-rollback storage.
