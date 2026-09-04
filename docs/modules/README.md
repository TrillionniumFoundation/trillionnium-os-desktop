# Module development documentation

This index covers every Cargo workspace member in the current d6 candidate graph.
`manifests/modules.v1.json` is the machine-readable registry, and
`tools/validate_module_documentation.py` verifies that the registry, Cargo
manifests, module READMEs, binaries, features, contracts, tests, workflows, and
referenced paths remain aligned.

A module README is a development and maintenance contract. It does not replace the
active project plan, gate registry, security model, exact-head evidence, or
integrated-main truth. When documents disagree, use the precedence defined in
`manifests/project-state.v1.json` and stop promotion until the drift is repaired.

## Coverage

| Module | Workspace path | Current status | Claim ceiling |
| --- | --- | --- | --- |
| [`hepta-browserd`](../../apps/hepta-browserd/README.md) | `apps/hepta-browserd` | `source_candidate_integrated_foundation` | compiled side-effect-free D4-D7 policy and coordination source; no integrated-image, external-effect, update, hardware, signing, or release authority |
| [`hepta-agent-portd`](../../apps/hepta-agent-portd/README.md) | `apps/hepta-agent-portd` | `profile_separated_candidate` | production binary remains fail closed; fixture, D1 qualification, and development binaries are opt-in and non-production |
| [`hepta-agent-transport`](../../crates/hepta-agent-transport/README.md) | `crates/hepta-agent-transport` | `host_validated_mechanism` | authenticated bounded connected-stream carrier only; no listener, semantic principal, browser dispatch, capability, or external effect |
| [`hepta-browser-codec`](../../crates/hepta-browser-codec/README.md) | `crates/hepta-browser-codec` | `host_validated_contract_boundary` | canonical Browser API parsing, validation, encoding, hashing, and effect classification only; no listener, authorization, or dispatch |
| [`hepta-agent-port`](../../crates/hepta-agent-port/README.md) | `crates/hepta-agent-port` | `host_validated_mechanism` | exactly one authenticated connected-stream Browser API lifecycle; no listener, principal authority, Servo dispatch, or external effect |
| [`hepta-peer-attestation`](../../crates/hepta-peer-attestation/README.md) | `crates/hepta-peer-attestation` | `host_validated_identity_mechanism` | local Linux process/service identity attestation; no semantic principal, browser authorization, or production activation |
| [`trillionnium-contract-core`](../../crates/trillionnium-contract-core/README.md) | `crates/trillionnium-contract-core` | `integrated_contract_foundation` | platform-neutral bounded identifiers, digests, time and revision primitives only |
| [`hepta-browser-contracts`](../../crates/hepta-browser-contracts/README.md) | `crates/hepta-browser-contracts` | `integrated_contract_foundation` | engine-neutral typed Browser API and risk/reference model; no wire parsing, browser runtime, capability, or effect authority |
| [`hepta-session-core`](../../crates/hepta-session-core/README.md) | `crates/hepta-session-core` | `host_validated_state_and_journal_core` | deterministic session admission, queueing, revisions, and durable non-replaying receipt facts; no browser, socket, clock, policy, or effect executor |
| [`hepta-workspace-composition`](../../crates/hepta-workspace-composition/README.md) | `crates/hepta-workspace-composition` | `headed_host_candidate_model` | engine-neutral trusted-workspace state and invariant model; no window, Servo instance, frame, clipboard, AgentPort, or external effect |
| [`hepta-browser-actor`](../../crates/hepta-browser-actor/README.md) | `crates/hepta-browser-actor` | `d3_source_candidate` | engine-neutral PageOwner/principal/dispatch/receipt core with deterministic local runtime; no promoted Servo adapter, production AgentPort, external effect, or integrated-image authority |
| [`hepta-d3-development`](../../crates/hepta-d3-development/README.md) | `crates/hepta-d3-development` | `d3_development_candidate` | explicit non-default development/qualification graph using deterministic fixture semantic resolution; no Servo, production activation, external effect, hardware, signing, or release authority |

## Required module document structure

Every module README must contain these exact top-level sections:

- `Status and claim ceiling`
- `Responsibilities`
- `Non-responsibilities`
- `Dependency and call direction`
- `Public API and binaries`
- `Configuration and features`
- `State, concurrency, and failure semantics`
- `Security invariants`
- `Testing and evidence`
- `Operations and troubleshooting`
- `Compatibility and change protocol`

The validator additionally requires:

- exact one-to-one coverage of root Cargo workspace members;
- Cargo package name, binary inventory, required binary features, and feature
  inventory to match the registry;
- a README of at least 3,000 UTF-8 bytes for every member;
- registered architecture, contract, test, and workflow paths to exist;
- module, manifest, documentation, and referenced paths not to traverse symlinks;
- explicit status, owner class, and claim ceiling for every module.

## Change workflow

1. Change one bounded module or work package at a time.
2. Update its implementation, Cargo manifest, contracts, tests, README, and
   `manifests/modules.v1.json` in the same commit or pull request.
3. Run `python3 tools/validate_module_documentation.py` before the broader
   repository and Rust suites.
4. Record exact source, tree, base, tested merge, workflow, toolchain, input, and
   output identities at the applicable evidence tier.
5. Preserve non-claims. Documentation completeness never promotes runtime,
   hardware, signing, or release authority.

## Adding a module

A new Cargo member is rejected until it has:

- a registry entry and detailed README;
- an owner class and explicit claim ceiling;
- complete binary and feature inventory;
- at least one architecture document, contract, test source, and workflow;
- dependency/call-direction and security-invariant documentation;
- repository validation, independent review, and exact-head evidence.

Removing or renaming a module requires updating all reverse references and
retained evidence readers. Historical evidence must remain interpretable and
must never be silently rebound to the new path.

## Non-Cargo components

Non-Cargo repository, packaging, experiment, evidence, and boundary components are governed separately by [`manifests/components.v1.json`](../../manifests/components.v1.json) and [`docs/components/README.md`](../components/README.md).
