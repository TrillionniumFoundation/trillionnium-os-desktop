# Build, run, and validate

Run commands from the desktop repository root. The tested toolchain is
`nightly-2026-07-21`; the host crate declares Rust 1.83 as its syntax/API minimum,
but that minimum toolchain has not been qualified in this change. Dependencies
are pinned and `Cargo.lock` is committed. No build step needs the full Hepta
workspace.

```sh
cargo +nightly-2026-07-21 test --locked --manifest-path services/hepta-os/Cargo.toml
cargo +nightly-2026-07-21 fmt --check --manifest-path services/hepta-os/Cargo.toml
cargo +nightly-2026-07-21 clippy --locked --manifest-path services/hepta-os/Cargo.toml --all-targets -- -D warnings
```

The Linux tests bind fresh private Unix sockets under `/tmp` and remove their
own fixture directories. A sandbox that disallows socket creation will return
`Operation not permitted`; that is a blocked host test, not a pass. Running the
suite in an authorized local socket environment does not require root or
system/device changes.

## Source-derived conformance

Use an authorized local checkout of the fixed private Hepta revision. The first
command verifies its exact commit and the twelve reviewed source-file hashes,
then extracts the original wire declarations and original EventBuffer code
into a **new, previously nonexistent** small verifier directory. It copies no
Agentd runtime, signing configuration, operation store, or effect owner.

```sh
python3 tests/integration/hepta/check_upstream_contract.py \
  --hepta-source /absolute/path/to/hepta-private-ci \
  --emit-reference /tmp/hepta-pinned-wire-check
cargo +nightly-2026-07-21 run --manifest-path /tmp/hepta-pinned-wire-check/Cargo.toml
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
cargo +nightly-2026-07-21 run --locked --manifest-path services/hepta-os/Cargo.toml \
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

## Live profile acceptance still required

The separate [original-Agentd gate](../../tests/integration/hepta/ORIGINAL_AGENTD.md)
now provides fixed-source build/launch commands, original-owner process
assertions, and the actual resource/artifact blockers. Its default preflight
does not compile or launch Agentd and cannot satisfy live acceptance.

For a live run, separately record the fixed Hepta executable/build features,
launcher command, trusted identity/generation/UID source, configured owners and
providers, and actual capability response. First verify only the four supported
read calls. Then qualify daemon restart, generation replacement, history loss,
and Session freshness. Do not count `--help`, the Python fixture, or source
conformance as this evidence. Authenticated objective submission and HOS2
effects require their own owner-approved provider/adapter and durable-result
acceptance, not changes to this observer's method allowlist.

Normal lifecycle advancement keeps the same source and its historical events.
A promotion race between the original runtime snapshot and event-buffer lock
may briefly discard a mixed poll and mark the last snapshot stale. The next
read may recover; this is not an automatic task retry or effect replay.
