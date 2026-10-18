# Build, run, and validate

Run commands from the desktop repository root. The current lightweight validation uses
Rust **1.88.0**; the host crate declares Rust 1.83 as its syntax/API minimum,
but that minimum toolchain has not been qualified in this change. Dependencies
are pinned and `Cargo.lock` is committed. No build step needs the full Hepta
workspace.

```sh
cargo +1.88.0 test --locked --manifest-path services/hepta-os/Cargo.toml
cargo +1.88.0 fmt --check --manifest-path services/hepta-os/Cargo.toml
cargo +1.88.0 clippy --locked --manifest-path services/hepta-os/Cargo.toml --all-targets -- -D warnings
```

The Linux tests bind fresh private Unix sockets under `/tmp` and remove their
own fixture directories. A sandbox that disallows socket creation will return
`Operation not permitted`; that is a blocked host test, not a pass. Running the
suite in an authorized local socket environment does not require root or
system/device changes.

For the optional trusted ObjectiveStart API and command, run the feature-on
suite and retain the default-off check:

```sh
cargo +1.88.0 test --locked --manifest-path services/hepta-os/Cargo.toml \
  --features objective-transport
cargo +1.88.0 clippy --locked --manifest-path services/hepta-os/Cargo.toml \
  --all-targets --features objective-transport -- -D warnings
cargo +1.88.0 check --locked --manifest-path services/hepta-os/Cargo.toml \
  --no-default-features
```

The `hepta-submit` six-argument interface, stdin ownership, complete output
schema, exit codes and lost-output handling are specified in
[OBJECTIVE_TRANSPORT.md](OBJECTIVE_TRANSPORT.md#trusted-single-attempt-command).
The caller supplies an existing signed envelope and its trusted endpoint;
these commands do not provision an issuer or enable submission in the UI.

## Optional retained-request admission history

The default-off history feature includes the existing ObjectiveStart transport
and adds a dedicated one-read client. Its full input/output and anchor ownership
contract is [OBJECTIVE_HISTORY.md](OBJECTIVE_HISTORY.md). Run the complete feature
suite so the shared transport retains its original observer/submission checks:

```sh
cargo +1.88.0 test --locked --manifest-path services/hepta-os/Cargo.toml \
  --features objective-history
cargo +1.88.0 clippy --locked --manifest-path services/hepta-os/Cargo.toml \
  --features objective-history --all-targets -- -D warnings
cargo +1.88.0 check --locked --manifest-path services/hepta-os/Cargo.toml \
  --no-default-features
cargo +1.88.0 build --locked --manifest-path services/hepta-os/Cargo.toml \
  --features objective-history --bins
```

`hepta-history` takes the current trusted endpoint/AgentId/spawn/UID/PID/request ID
and optionally the previously retained anchor sequence/chain. Supply the exact
original signed envelope on stdin, close stdin, and bound the child process.
Historical publication never implies a current run or effect, and no query
outcome authorizes resubmission. The default Session/Shell has no new command.

For actual original-owner qualification, follow
[OBJECTIVE_HISTORY_PROBE.md](../../tests/integration/hepta/OBJECTIVE_HISTORY_PROBE.md).
That separate runner requires the exact committed extension contract and
original source/lock; the older R8 fixed-source gate continues to use `f8c9419d`.
Preparation, source checks, unit tests, and actual native process qualification
are recorded separately. No build of the lightweight client requires the full
original workspace, while the real Agentd/probe does.

## Source-derived conformance

Use an authorized local checkout of the fixed Hepta revision. The first
command verifies its exact commit and the twelve reviewed source-file hashes,
then extracts the original wire declarations and original EventBuffer code
into a **new, previously nonexistent** small verifier directory. It copies no
Agentd runtime, signing configuration, operation store, or effect owner.

```sh
python3 tests/integration/hepta/check_upstream_contract.py \
  --hepta-source /absolute/path/to/hepta-private-ci \
  --emit-reference /tmp/hepta-pinned-wire-check
cargo +1.88.0 run --manifest-path /tmp/hepta-pinned-wire-check/Cargo.toml
```

After dependencies have been fetched, both Rust commands support `--offline`.
The emitted program checks four source-derived payload roundtrips, four
request roundtrips, identity/envelope encoding, the original fleet lifecycle
successor and exact Agentd serving-phase expression, and the original
EventBuffer gap/resume/ahead behavior. The small lifecycle check includes
promotion, draining, restart fencing, invalid phase/offset pairs and overflow.
The surrounding error/identity record shapes are explicit test shims; the
transition methods and accepted expression are copied from verified source.
This is stronger than merely checking
that locally invented fixtures parse, while remaining a source/fixture test.
It does not start Hepta Agentd.

## Standalone diagnostic client

```sh
cargo +1.88.0 run --locked --manifest-path services/hepta-os/Cargo.toml \
  --bin hepta-observe -- --help
```

The positional arguments are the absolute Agentd control-socket path, canonical
Agent UUID, nonzero spawn generation, expected peer UID, and optionally one
known run ID. Obtain these values from the trusted launcher or supervisor,
not from a discovered socket. The direct CLI is a trusted-host diagnostic;
renderer code must receive the Session projection instead.

```text
hepta-observe <absolute-socket> <agent-uuid> <spawn-generation> <peer-uid> [run-id]
```

The socket and its immediate canonical parent must be owned by the specified
UID, with no group/other permission bits (normally socket `0600`, parent `0700`).
Do not loosen real daemon permissions to make this profile connect. Resolve a
different deployment profile with its owner. No socket discovery, daemon
launch, credential setup, or configuration mutation occurs here.

## Session integration fixture

This fixture serves the exact reviewed read subset using test data over a real
Linux Unix socket. The first stdout line contains an explicit
`evidence_class: scripted_socket_fixture_not_hepta_daemon` plus its socket path,
Agent UUID, generation, OS UID, and actual server PID.

```sh
python3 tests/integration/hepta/agentd_fixture.py
```

In a second terminal, supply those values to `hepta-observe`, or configure the
Session's trusted launch environment described by the UI owner's run document.
The expected projection contains a running health state and three lifecycle
events, immutable spawn generation 7 and current generation 8. Terminating the
fixture with SIGTERM cleans up its private directory;
the Session should retain its last observation as stale/unavailable while its
own IPC continues to respond. The fixture has no model, policy, grant, durable
operation database, or device effects, and must never be presented as a running
Hepta production profile.

## Optional ObjectiveStart transport and source declarations

The [separate default-off feature](OBJECTIVE_TRANSPORT.md) adds no command to
`hepta-observe`, Session or Shell. These commands validate its exact wire and
single-attempt failure semantics using only disposable Linux UDS fixtures;
they do not authenticate or submit an objective to original Hepta.

```sh
cargo +1.88.0 check --locked --manifest-path services/hepta-os/Cargo.toml \
  --no-default-features --all-targets
cargo +1.88.0 test --locked --manifest-path services/hepta-os/Cargo.toml \
  --features objective-transport
cargo +1.88.0 clippy --locked --manifest-path services/hepta-os/Cargo.toml \
  --features objective-transport --all-targets -- -D warnings
cargo +1.88.0 fmt --check --manifest-path services/hepta-os/Cargo.toml
```

The feature-on test command also runs the existing observer baseline. The
new socket tests verify at most one connection, unchanged original raw ingress,
peer/source/request/run identity, exact publication/refusal payloads, unknown
delivery, strict EOF/framing and finite diagnostics. A separate small Tokio
duplex unit test forces a partial write and cancellation; compile-fail examples
protect the consuming API and opaque raw input.

For additional source-derived wire conformance, provide the fourteen exact
files named by [OBJECTIVE_UPSTREAM_CONTRACT.json](OBJECTIVE_UPSTREAM_CONTRACT.json)
under their original relative paths. An authorized checkout or a fixed-file
snapshot is accepted. Every file must match its original Git blob, SHA-256 and
size. Use a new, nonexistent output directory:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tests/integration/hepta/check_objective_wire.py \
  --source-files /absolute/path/to/fixed-original-files \
  --emit-reference /tmp/hepta-objective-wire-check
cargo +1.88.0 run --locked --offline \
  --manifest-path /tmp/hepta-objective-wire-check/Cargo.toml
```

The generated project contains original serde declarations, the original
AgentId implementation and the existing expired/all-zero wire fixture factory.
Only the request/payload enums are narrowed to ObjectiveStart and its three
response variants. The local assertion harness checks the flat `objective_run`
shape against actual original serialization and distinguishes the separate
client-facing `ObjectiveStartOutcome` shape. The small existing lock is reused
with one explicit root-package rename; no original Agentd dependency, runtime,
issuer, signature, process, effect owner or socket is constructed. Extraction
ranges and source/generated hashes are recorded with the emitted project.

## Original process and persistent Session passed; effect profiles remain

The separate [original-Agentd gate](../../tests/integration/hepta/ORIGINAL_AGENTD.md)
provides fixed-source build/launch commands and original-owner process
assertions. Its default preflight
does not compile or launch Agentd and cannot satisfy live acceptance.

The [native ARM64 run and raw evidence](../../tests/integration/hepta/evidence/2026-10-17-original-agentd-arm/README.md)
now record a passed original Agentd build/link/run on exact desktop `1974d9a9`
and original `f8c9419d`. All eight original-process checks passed, including
restart, old-spawn rejection and controlled stop; the three downloaded ELF
hashes and AArch64 headers independently match the executed report. Both
source checkouts and the original lock remained clean.

The earlier local Rust 1.95 compiler checks passed without linking or running
the process in those historical records. See the
[build review and raw evidence](../../tests/integration/hepta/BUILD_REVIEW.md).
The [live-source review](../../tests/integration/hepta/LIVE_SOURCE_REVIEW.md)
checks the actual Supervisor/Agentd startup and Session handoff against the
fixed source. It is not another executed process result.

The earlier ARM gate launched a new observer CLI for each read and used no
ready hold. Later [two original continuous Session runs](../../tests/integration/hepta/evidence/2026-10-17-original-session-runtime/README.md)
each passed the original eight checks plus eight Session checks and six real
Shell phases. The same Session persisted through Starting/Running/Draining and
old-spawn staleness; a replacement Session used new explicit trusted binding.
Actual stop samples retained either Running or Draining before becoming stale,
as recorded in each run. Those receipts distinguish reused original/probe/observer
ELFs from new UI builds and retain the failed first capture harness attempt.
Do not count `--help`, the Python fixture, or source conformance as that
original-runtime evidence. Authenticated objective submission and HOS2
effects require their own owner-approved provider/adapter and durable-result
acceptance, not changes to this observer's method allowlist. The new optional
transport is one local protocol step toward that integration, with no real
issuer/profile assembly or original submission in its tests.

The read-only original-process profile needs no AuthBus issuer or objective
profile. A future `ObjectiveStart` deployment needs independently installed
owner trust, a frozen objective profile and the separate replay checkpoint.
The running route is the original `objective_runtime` host reached through
`state_control`; it does not come from the undeclared `objective_ingress.rs`
file. Follow the [submission contract](CONTRACT.md#errors-freshness-and-unsupported-submission):
an unknown submission is not resolved by a `RunStatus` response of `null`, and
an admission receipt is not a completed HOS2/device effect. These documents do
not generate keys, enroll an issuer or provide an alternative authority path.

Normal lifecycle advancement keeps the same source and its historical events.
A promotion race between the original runtime snapshot and event-buffer lock
may briefly discard a mixed poll and mark the last snapshot stale. The next
read may recover; this is not an automatic task retry or effect replay.
