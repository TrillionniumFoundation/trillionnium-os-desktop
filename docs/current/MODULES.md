# Current development and technical module inventory

Inventory baseline: Desktop product candidate
`d8b2bc6fb715af8ed27dfec09e3dfa8b94fa5bd2`, checked 2026-10-24.
This list follows active manifests and source owners. Archived evidence copies
are excluded. A linked manual means there is a development/technical entry;
it does not mean the implementation or platform has passed acceptance.

## Product and support Rust packages

The active non-vendored scope contains **11 product/support packages**, the
`ui/Cargo.toml` virtual workspace and **four test packages**. Each of the 11
packages has an identified manual or a shared contract below. `native-text`
is a feature of `hepta-session-host`, not a second package.

| Package / source owner | Development entry | Technical contract and remaining boundary |
| --- | --- | --- |
| `hos2-os-abi` — [libs/os-abi](../../libs/os-abi/Cargo.toml) | [codec guide](../../libs/os-abi/README.md), [golden generator](../../tests/golden/generate_hos2.py) | [HOS2](../NATIVE_ABI.md); exact bytes and opcodes, no authority issuance |
| `os-control` — [libs/os-control](../../libs/os-control/Cargo.toml) | [validation commands](../../tests/control/VALIDATION.md), [matrix runner](../../tests/control/run-validation.sh) | [API contract](../../libs/os-control/API_CONTRACT.md); original resource/delivery owners; host backends do not establish kernel IRQ/SMP safety or durable Hepta history |
| `hepta-os-observer` — [services/hepta-os](../../services/hepta-os/Cargo.toml) | [README](../../services/hepta-os/README.md), [RUN](../../services/hepta-os/RUN.md) | [transport contract](../../services/hepta-os/CONTRACT.md); bounded original-owner observation, no effect authority |
| `hepta-session-host` — [services/hepta-session-host](../../services/hepta-session-host/Cargo.toml) | [composition guide](../../services/hepta-session-host/README.md) | [native text session](../../services/hepta-session-host/TEXT_SESSION.md); original Root/Agentd owns authentication and outcomes, complete product/native guest execution separate |
| `trill-ui-boundary` — [support/ui](../../support/ui/Cargo.toml) | [UI run guide](../../support/ui/RUN.md) | [boundaries](../../support/ui/BOUNDARIES.md), [integration contracts](../../support/ui/INTEGRATION_CONTRACTS.md); Linux host prototype and owner seam |
| `a09-device-lifecycle` — [support/vmm/device_lifecycle](../../support/vmm/device_lifecycle/Cargo.toml) | [development and test guide](../../support/vmm/device_lifecycle/README.md) | Same guide defines generations, teardown and ownership; it does not qualify physical device reset or VFIO |
| `trill-ui-core` — [ui/core](../../ui/core/Cargo.toml) | [module guide](../../ui/core/README.md) | Typed host wire, observations, Notes identity/storage; application receipt differs from original-owner durable terminal |
| `trill-ui-broker` — [ui/broker](../../ui/broker/Cargo.toml) | [module guide](../../ui/broker/README.md) | Bounded admission/private Notes transport; no signer, issuer or replacement effect ledger |
| `trill-session` — [ui/session](../../ui/session/Cargo.toml) | [module guide](../../ui/session/README.md) | Process/socket lifecycle and [Objective bridge](../../ui/session/OBJECTIVE_BRIDGE.md); same-UID boundary, exact request identity and uncertain outcomes |
| `trill-shell` — [ui/shell](../../ui/shell/Cargo.toml) | [module guide](../../ui/shell/README.md) | [freshness](../../ui/shell/OBSERVATION_FRESHNESS.md), [native Makepad gate](../../support/ui/NATIVE_MAKEPAD.md); presentation/local drafts do not create owner authority |
| `trill-app-window` — [ui/app-window](../../ui/app-window/Cargo.toml) | [module guide](../../ui/app-window/README.md) | [Notes organ](../../support/ui/NOTES_ORGAN.md), [durability](../../support/ui/NOTES_DURABILITY.md); serialized application mutation, uncertain delivery and separate owner reconciliation |

The [UI workspace guide](../../ui/README.md) lists the five UI members and
the explicit default egui and original Makepad feature builds. The Linux host
product source currently selects Rust 1.96.0 and Hepta
`22e87e0dd6560a7b925e716a33011378ae07a9a2`. The kernel retains its independent
nightly. [SOURCES](../SOURCES.md) and the actual manifests own those identities.

## Test packages and support components

| Source | Development/technical owner | Scope |
| --- | --- | --- |
| [tests/control/backend_no_std](../../tests/control/backend_no_std/Cargo.toml) | [fixture contract](../../tests/control/backend_no_std/VALIDATION.md) | Public no_std backend type/compilation boundary |
| [tests/control/loom](../../tests/control/loom/Cargo.toml) | [bounded model and validation guide](../../tests/control/VALIDATION-20261017-bound.md), [matrix runner](../../tests/control/run-validation.sh) | Host scheduling model; preserve recorded bounds and original-owner contracts |
| [tests/ui](../../tests/ui/Cargo.toml) | [test plan](../../tests/ui/TESTPLAN.md) | Host contract tests plus independently scoped process/window/compositor probes |
| [tests/workloads/linux/rust](../../tests/workloads/linux/rust/Cargo.toml) | [Linux workloads](../../tests/workloads/linux/README.md) | Tokio/userland compatibility fixture; full Ubuntu and native owner gates separate |
| [support/build](../../support/build/README.md) | [foundation validation](FOUNDATION.md), [strict native tests](../../support/build/ktest/README.md) | Source inputs, OSDK, kernel build, boot and original test inventories |
| [tests/spec](../../tests/spec/) and [tests/golden](../../tests/golden/) | [foundation validation](FOUNDATION.md), [HOS2](../NATIVE_ABI.md) | Host source/contract checks and golden wire bytes, not compiled kernel behavior |
| [UI product tooling](../../support/ui/PRODUCT.md) | Product and [resource preparation](../../support/ui/NATIVE_MAKEPAD.md) guides | User install/process setup, exact file/resource identity, draft recovery and renderer choice |
| [Native Agentd workload](../../tests/workloads/hepta_agentd_runtime/README.md) | Separate reviewed source pair and explicit native build/run stages | No-turn lifecycle slice; full F1/G2 and durable device effects remain separate |
| [Native CognitiveStore workload](../../tests/workloads/hepta_cognitive_store/README.md) | [validation contract](../../tests/workloads/hepta_cognitive_store/VALIDATION.md) | Original store workload on its own reviewed source/runtime profile |

The dated control validation manuals retain their original test counts and
source revisions. Use their current runner and API contract for new execution;
their archived success counts do not qualify a changed tree.

## Vendored kernel and cross-cutting areas

The [kernel workspace manifest](../../kernel/asterinas/Cargo.toml) still has
**57 explicit members**. Their [shared development and technical manual](../modules/kernel-workspace/README.md)
indexes every member: 21 kernel/components, 20 libraries, and 16 OSTD/tooling
crates. The manual's JSON hashes retain the declared `10dae5ea` snapshot;
they are not regenerated execution evidence for this product candidate.

The strict native wrapper supports four suites; it does not accept every one
of those 57 names. Other crates use the original documented build/test entry.
`cargo-osdk` and comp-sys have their own workspaces outside that 57-member
denominator. Read [Asterinas guidelines](../../kernel/asterinas/AGENTS.md)
before changing their code.

Cross-cutting A00–A10 ownership remains in [the module index](../INDEX.md):
architecture, build, ABI, control core, compatibility, process/capability,
scheduler, memory, storage, VMM/device lifecycle, and UI. The current table
above makes the active Rust package owners explicit; it does not replace those
multi-package contracts.

## Remaining documentation requirements

There are usable entry points for the listed packages and all 57 kernel
members. Full product documentation still needs a maintained per-platform
acceptance and recovery matrix covering actual display/input, storage media,
GPU/device reset, mobile receivers and native original-owner runtime. The
existing Linux host, QEMU and Android records have different scopes.

When changing a module, update its owner guide with the changed interface,
state/authority owner, failure and recovery behavior, exact build profile and
positive/negative validation commands. Record test results separately with
their actual source identities and limits. A new README or an archived audit
does not substitute for that contract or execution evidence.
