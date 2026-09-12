<!-- generated from manifests/modules.v1.json; do not edit by hand -->
# Module development documentation

This index is a deterministic projection of the current Cargo module registry.
Run `python3 tools/validate_documentation_integrity.py --render-index` to render it.
The module validator separately checks workspace, API inventory, references and README contracts.
Documentation coverage is source-governance evidence, not runtime or release qualification.

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
| [`hepta-browser-actor`](../../crates/hepta-browser-actor/README.md) | `crates/hepta-browser-actor` | `candidate_exact_pin_real_servo_host_vertical_slice` | concrete non-generic ServoBrowserActor bridge plus exact-pin real-Servo host qualification candidate with attested AgentPort, request custody, durable receipts and stale-reference refusal; qualification-only mailbox; no production listener, external-effect authority, installed image, hardware, signing, publication, or release authority |
| [`hepta-browser-actor-simulation`](../../crates/hepta-browser-actor-simulation/README.md) | `crates/hepta-browser-actor-simulation` | `internal_unpublished_browser_actor_simulation_and_dispatch_core` | unpublished generic actor, deterministic fixture runtime, engine-thread/callback bridges and hostile test support only; no product runtime selection, listener, real Servo integration, external effect, installed image, hardware, signing, publication, or release authority |

## Required contract

Each registered module has responsibilities, exclusions, dependency direction, public APIs,
configuration, concurrency/failures, security invariants, tests, operations and compatibility rules.
A matching index cannot establish that an implementation or a higher evidence tier is complete.

## Scope beyond Cargo

See [product subsystem coverage](PRODUCT_SUBSYSTEM_COVERAGE.md) for non-Cargo boundaries.
See [d6 annex precedence](../plan/D6_ANNEX_PRECEDENCE.md) before using an inherited d5 annex.

## Change workflow

Change code, Cargo inventory, module README and registry together; regenerate this index;
run module/documentation/repository/truth tests; obtain exact-head and prospective-merge evidence
and independent review. Only protected promotion and an exact-main rerun can update integrated truth.
