# `hepta-agent-portd` technical development contract

This package contains the product one-connection AgentPort service and a separately feature-gated fixture binary. The product binary accepts only an inherited AF_UNIX stream, verifies the local socket path and attested peer process, and then fails closed before request decoding while BrowserActor integration is absent.

This document is normative for source maintenance at the recorded claim ceiling. It does not replace `manifests/project-state.v1.json`, the gate registry, live GitHub state, exact-head evidence, installed-image qualification, or an authorized release record.

## Status and claim ceiling

Status: `candidate_profile_separated_socket_activation_service`  
Claim ceiling: `one-connection Linux systemd socket-activation source with a physically separate opt-in fixture; product dispatch remains unavailable and default disabled, with no BrowserActor, Servo, external effect, installed-image, hardware, signing, or release authority`

A narrower machine-state, gate or non-claim always wins. Source presence and documentation completeness do not promote runtime or release authority.

## Responsibilities

- Duplicate and validate the inherited stream descriptor without calling `bind` or `listen`.
- Require the expected filesystem socket pathname and exact system service identity.
- Hold pidfd-backed peer evidence through the refusal/dispatch boundary.
- Keep the D0 fixture in a non-default feature and outside the Debian product install map.

## Non-responsibilities

- Do not create a TCP, WebDriver or ad-hoc Unix listener.
- Do not convert UID/GID membership into a semantic TaskFlow principal.
- Do not link the fixture handler into the product binary or silently substitute it for BrowserActor.
- Do not ship or create the product activation marker.

## Dependency and call direction

systemd owns the listening socket and launches one short-lived service process for each accepted connection. `hepta-agent-portd` consumes `hepta-agent-transport` for kernel peer identity, `hepta-peer-attestation` for procfs/cgroup/executable continuity, and optionally `hepta-agent-port` only in the fixture feature. Product code must not depend on the fixture feature.

Relevant architecture:

- `docs/architecture/SYSTEMD_AGENT_PORT_CUSTODY.md`
- `docs/architecture/AGENT_PORT_PATHNAME_CUSTODY.md`
- `docs/architecture/REQUEST_PEER_CUSTODY.md`

The dependency direction is one-way. Lower-level mechanism and contract crates must not import application, profile, image, hardware, signing, or publication authority.

## Public API and binaries

- Binary `hepta-agent-portd` is the only production-shaped target and supports `--self-check`.
- Binary `hepta-agent-port-fixture` is available only with Cargo feature `fixture`.
- Explicit example `hepta-agent-d1-fixture` is qualification-only, selected with `--features fixture --example hepta-agent-d1-fixture`; it is not a product binary.
- The package exports no library API; its stable interface is inherited file descriptor 0, process exit status and bounded redacted diagnostics.

Registered binaries:

- `hepta-agent-portd` at `src/main.rs`; required features: `none`.
- `hepta-agent-port-fixture` at `src/bin/hepta-agent-port-fixture.rs`; required features: `fixture`.

## Configuration and features

Cargo `default` is empty. The `fixture` feature enables `hepta-agent-port` only for explicit tests. Runtime constants name `/run/hepta/browserd/agent.sock`, the `hepta-agent` user/group and `hepta-agent.service`. Packaging presets keep the socket disabled and no enable marker is shipped.

Registered Cargo features: `default`, `fixture`

The D1 example's codec and `qualification-static-attestation` dependencies are
restricted to `[dev-dependencies]`. Product builds select only
`--no-default-features --bin hepta-agent-portd`; all-target/all-feature test
outputs are never production artifacts. The detailed target, build-metadata,
identity and installation boundary is in
`docs/architecture/D1_QUALIFICATION_GRAPH.md`.

## State, concurrency, and failure semantics

Each product process owns exactly one accepted stream and one attested peer lifetime. It does not retain cross-connection state and uses `Restart=no` under the reviewed unit. Descriptor, socket-path, peer and product-handler failures are terminal. The fixture also serves one bounded request and exits.

Failures must preserve the last truthful state. A timeout, crash, peer loss, storage ambiguity or unsupported operation cannot be converted into successful completion by a caller, retry loop, fixture, log message or evidence generator.

## Security invariants

- Socket ownership and mode are only the first boundary; pidfd, start time, cgroup, unit and executable continuity are also required.
- The product path fails before decode when BrowserActor is absent.
- The fixture binary is absent from the default build/install graph and cannot authorize potential external effects.
- Unsafe descriptor conversion is isolated, documented and guarded by descriptor-type checks.
- Logs must state verified/redacted outcomes rather than serializing PID, UID, GID or opaque session identity.

Every invariant above is a review condition, not merely commentary. Weakening one requires a new threat analysis, hostile regression and explicit claim-ceiling decision.

## Testing and evidence

Primary source or test references:

- `apps/hepta-agent-portd/src/main.rs`
- `tests/test_s04_transport_custody.py`
- `tests/test_d1_qualification_graph.py`
- `tests/d1/test_d1_qualification_separation.py`

Applicable workflows:

- `.github/workflows/agent-port-custody.yml`
- `.github/workflows/s04-transport-custody.yml`
- `.github/workflows/d1-qualification-graph.yml`

Contract references:

- `contracts/agent-port-custody.v1.json`
- `contracts/request-peer-custody.v1.json`

A passing unit or hosted-CI test proves only the evidence tier named by its gate. Any source, workflow, dependency, base, head or claim change invalidates earlier evidence according to `manifests/gates.v1.json`.

## Operations and troubleshooting

- Run product and fixture self-checks separately so accidental feature leakage is visible.
- Use `systemd-analyze verify` and the custody validator before changing units, users, groups or install maps.
- A pathname mismatch, missing account, cgroup mismatch or peer exit is a security refusal, not a retry signal.
- Actual PID 1 activation remains an installed-image gate and must not be simulated by invoking the binary manually.

Operational diagnosis must retain bounded/redacted evidence and must not weaken admission, limits, ownership, sync, isolation or default-disabled controls simply to make a test pass.

## Compatibility and change protocol

Changes to inherited-FD semantics, account names, socket path, features, binaries, systemd units or install maps must update the custody contracts, negative corpus, package inventory and this registry atomically. A future BrowserActor connection requires a separate concrete adapter and cannot weaken default-disabled behavior.

Required change sequence: update implementation and Cargo metadata; update machine contracts and hostile tests; update this README and `manifests/modules.v1.json`; run module, repository, project-truth and Rust checks; obtain independent review on the immutable final head; then perform the required exact-main or higher-tier rerun after protected promotion.
