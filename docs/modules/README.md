# Module development documentation

This index covers every Cargo workspace member in the current successor source graph. `manifests/modules.v1.json` is the machine-readable inventory and `tools/validate_module_documentation.py` enforces one-to-one coverage, detailed module contracts, exact binary/feature inventory, reference existence and fail-closed claim projection.

Documentation completeness is source-governance evidence only. It does not establish a running desktop, installed image, hardware qualification, key custody or release.

## Coverage

| Module | Workspace path | Status | Claim ceiling |
| --- | --- | --- | --- |
| [`hepta-browserd`](../../apps/hepta-browserd/README.md) | `apps/hepta-browserd` | `integrated_d0_scaffold_with_candidate_actor_contracts` | deterministic D0 self-check and source composition only; no product Servo runtime, enabled AgentPort, external effect, installed image, hardware, signing, publication, or release authority |
| [`hepta-agent-portd`](../../apps/hepta-agent-portd/README.md) | `apps/hepta-agent-portd` | `candidate_profile_separated_socket_activation_service` | one-connection Linux systemd socket-activation source with a physically separate opt-in fixture; product dispatch remains unavailable and default disabled, with no BrowserActor, Servo, external effect, installed-image, hardware, signing, or release authority |
| [`hepta-agent-transport`](../../crates/hepta-agent-transport/README.md) | `crates/hepta-agent-transport` | `candidate_fail_stop_authenticated_connected_stream` | authenticated, bounded and fail-stop already-connected AF_UNIX framing only; no socket listener, semantic principal, BrowserActor, capability, external effect, installed image, hardware, signing, publication, or release authority |
| [`hepta-browser-codec`](../../crates/hepta-browser-codec/README.md) | `crates/hepta-browser-codec` | `candidate_canonical_browser_wire_boundary` | bounded canonical Browser API parsing, validation, encoding, hashing and risk classification only; no listener, peer authorization, BrowserActor dispatch, Servo execution, external effect, installed image, hardware, signing, publication, or release authority |
| [`hepta-agent-port`](../../crates/hepta-agent-port/README.md) | `crates/hepta-agent-port` | `candidate_exactly_one_agentport_lifecycle` | one authenticated connected-stream request lifecycle with bounded handler output and lifecycle observation only; no listener, semantic principal, concrete BrowserActor/Servo dispatch, external-effect authorization, installed image, hardware, signing, publication, or release authority |
| [`hepta-peer-attestation`](../../crates/hepta-peer-attestation/README.md) | `crates/hepta-peer-attestation` | `candidate_request_scoped_linux_peer_custody` | Linux process, namespace, cgroup, service-unit and trusted-executable continuity plus revocable request custody only; no semantic principal, browser authorization, product activation, external effect, installed image, hardware, signing, publication, or release authority |
| [`trillionnium-contract-core`](../../crates/trillionnium-contract-core/README.md) | `crates/trillionnium-contract-core` | `candidate_atomic_bounded_contract_primitives` | platform-neutral bounded identifiers, digests, Unix time and checked atomic revision primitives only; no transport, policy, browser, capability, external effect, installed image, hardware, signing, publication, or release authority |
| [`hepta-browser-contracts`](../../crates/hepta-browser-contracts/README.md) | `crates/hepta-browser-contracts` | `candidate_engine_neutral_browser_domain_contracts` | engine-neutral typed browser operations, navigation targets, semantic references, risk classes and stable errors only; no wire parsing, listener, runtime, capability, external effect, installed image, hardware, signing, publication, or release authority |
| [`hepta-session-core`](../../crates/hepta-session-core/README.md) | `crates/hepta-session-core` | `candidate_session_arbitration_and_managed_receipt_store` | deterministic session arbitration, bounded queueing, checked revisions and durable non-replaying receipt facts only; no browser engine, listener, OS clock, semantic policy, external effect, installed image, hardware, signing, publication, or release authority |
| [`hepta-workspace-composition`](../../crates/hepta-workspace-composition/README.md) | `crates/hepta-workspace-composition` | `candidate_engine_neutral_trusted_workspace_model` | deterministic model of one native trusted chrome surface plus one untrusted content surface, input ownership and crash recovery only; no native window, Servo instance, rendered product frame, AgentPort, external effect, installed image, hardware, signing, publication, or release authority |
| [`hepta-browser-actor`](../../crates/hepta-browser-actor/README.md) | `crates/hepta-browser-actor` | `candidate_sealed_product_browser_actor` | sealed product-facing BrowserActor with attested principal binding, request custody, deterministic local runtime and receipt observation only; no caller-injected runtime, product listener, real Servo adapter, external effect, installed image, hardware, signing, publication, or release authority |
| [`hepta-browser-actor-simulation`](../../crates/hepta-browser-actor-simulation/README.md) | `crates/hepta-browser-actor-simulation` | `internal_unpublished_browser_actor_simulation_and_dispatch_core` | unpublished generic actor, deterministic fixture runtime, engine-thread/callback bridges and hostile test support only; no product runtime selection, listener, real Servo integration, external effect, installed image, hardware, signing, publication, or release authority |

## Required contract

Every module README contains exact status/claim projections plus responsibilities, exclusions, dependency direction, public API, configuration, state/concurrency/failure semantics, security invariants, tests/evidence, operations and compatibility protocol. The validator rejects missing, duplicated, stale, undersized, symlinked or unregistered documentation.

## Change workflow

1. Change one bounded trust boundary at a time.
2. Update code, Cargo inventory, contracts, tests, README and registry together.
3. Run `python3 tools/validate_module_documentation.py` and `python3 -m unittest tests.test_module_documentation -v`.
4. Run repository/project-truth and complete Rust checks.
5. Bind evidence to the immutable exact head and prospective merge.
6. Merge only through enforced protection, then rerun the exact integrated object.
