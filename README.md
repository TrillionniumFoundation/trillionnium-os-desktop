# Trillionnium OS Desktop

Rust desktop and operating-system work for a Hepta-led execution platform. The
kernel is derived from Asterinas; Hepta keeps the existing authority, durable
writer, outbox and operation-history ownership.

## Start here

| Need | Entry point |
| --- | --- |
| Current candidate capabilities, evidence and unqualified product gates | [Current capabilities](docs/CURRENT_CAPABILITIES.md) |
| System boundaries and component ownership | [Architecture](docs/ARCHITECTURE.md) |
| Hepta integration and original owners | [Hepta integration](docs/HEPTA_INTEGRATION.md) |
| Development and technical documentation by delivery area | [Module index](docs/INDEX.md) |
| Native text, install/recovery, Notes and Android implementation handoff | [Current module handoff](docs/agents/NATIVE_ORGAN_MODULE_HANDOFF.md) |
| Implementation sequence and remaining product work | [Roadmap](docs/ROADMAP.md) |
| Current status and historical execution records | [Status](docs/STATUS.md) |
| Kernel build, boot and source verification | [Build guide](support/build/README.md) |
| UI development and execution | [UI run guide](support/ui/RUN.md) |
| Install, launch, diagnose, upgrade, recover local drafts and uninstall | [Linux host product guide](support/ui/PRODUCT.md) |
| Session and Notes integration | [Notes organ](support/ui/NOTES_ORGAN.md) |
| Pinning and verifying one complete OS/Hepta source pair | [Release profile](docs/agents/ORGAN_RELEASE_PROFILE.md) |
| Exact current Hepta source and cross-repository module contracts | [Native organ source map](docs/SOURCES.md#hepta-native-organ) |

## Two repositories, one execution authority

[`hepta-private-ci`](https://github.com/TrillionniumFoundation/hepta-private-ci)
provides the original Agentd, authority checks, durable writer/outbox and
operation history. This repository supplies the OS boundary and the desktop
organ: Shell presents user intent, Session owns local application processes,
and each application owns its document state. Local draft recovery and an
installer do not become execution authorities. The current installable scope
is a Linux host client with specific application targets; each native guest,
general desktop-control target and mobile platform needs its own acceptance.

Build one exact pair with the [source-profile procedure](docs/agents/ORGAN_RELEASE_PROFILE.md)
and preserve the verification receipt with the binary package. A moving branch
name, a UI dependency pin or successful packaging alone cannot identify an
accepted deployment. The package's `manifest.json` records both full commits,
every shipped file digest and `effects_authorized: false`.

## Linux host entry point

The current product candidate pins the original Hepta UI/core, host packages
and Hepta-carried patches to [Hepta `489f7096b0e5754968a30fa4477bb4417d24834f`](https://github.com/TrillionniumFoundation/hepta-private-ci/commit/489f7096b0e5754968a30fa4477bb4417d24834f),
tree `4731de9117065bd773b2fcee92c815ff896b8488`, and uses Rust 1.96.0.
The UI Cargo root explicitly patches all four original AccessKit crates to this
same source. `services/hepta-os` remains a local protocol/transport crate; it
does not acquire a fictitious Hepta Git dependency.

The [latest scoped component executions](results/integration/2026-10-24-original-owner-product/text-native-v10-v11/README.md)
cover the original text thread, Legacy history, client/protocol and default
original Makepad/AccessKit packages. Exact counts and ignored/unselected tests
are in [current capabilities](docs/CURRENT_CAPABILITIES.md). These results do not
qualify the final combined Desktop workspace, release binaries, a real native
window, an installed production deployment or a signed Android receiver. The
final source profile must additionally bind the complete Desktop commit/tree,
actual Cargo-generated locks, features, binary hashes and execution receipts.

The original runtime contracts are pinned beside their owners:
[Root/Agentd text](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/489f7096b0e5754968a30fa4477bb4417d24834f/codex-rs/hepta-agentd/NATIVE_TEXT_SESSION.md),
[original UI composition](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/489f7096b0e5754968a30fa4477bb4417d24834f/apps/hepta-control-ui/rust/robrix-ui/NATIVE_COMPOSITION.md),
[Notes crash recovery](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/489f7096b0e5754968a30fa4477bb4417d24834f/codex-rs/hepta-agentd/NOTES_RECOVERY_QUALIFICATION.md)
and [Android target](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/489f7096b0e5754968a30fa4477bb4417d24834f/codex-rs/hepta-memory/PRODUCTION_ANDROID_TEXT.md).

Use the [product guide](support/ui/PRODUCT.md) to wrap verified native binaries
and install them for the current user. The generated `trillionnium-desktop`
entry point provides `run`, `doctor --live`, `stop`, `rollback` and `uninstall`.
It uses one dedicated user Session service and keeps configuration, local
composers and Notes state outside release directories. The UI remains Rust;
the launcher is bounded host packaging and process setup written with Python's
standard library. Renderer selection is explicit in the installed config;
Makepad additionally needs its original verified resources and feature build.

The normal `trill-shell/hepta-native-makepad` feature uses original SDK
`337566c8` and its 54-file resource bundle without an external SDK override.
The separate `trill-shell/hepta-native-clipboard-sdk` candidate requires the
reviewed all-crate SDK override, an independent candidate lock and its 61-file
bundle. Only that feature advertises request-scoped native PasteText. The
43 native UI and 54 AccessKit scoped tests concern the default original SDK;
they do not qualify the clipboard candidate. See the [profile procedure](support/ui/PRODUCT.md#explicit-original-sdk-clipboard-candidate)
and [real window gate](support/ui/NATIVE_MAKEPAD.md).

## Evidence and supported scope

Read the scope and source identities attached to each execution record under
[`results/integration`](results/integration). A source-profile check verifies
source identities; it does not run the product, configure production authority,
or authorize effects. Host UI, native guest, and physical-device results have
separate scopes.

The next-step document records the remaining original-owner, native daemon,
isolation, recovery and hardware work. Shared module manuals are intentional;
the dated module audit preserves its original inventory; the module index links the current nearby entries.

## Development

Use the pinned toolchains and commands in each component's run guide. Kernel
contributions also follow [Asterinas agent guidelines](kernel/asterinas/AGENTS.md).
To check the vendored kernel build inputs from a checkout that retains the
pinned upstream Git objects:

```sh
python3 support/build/verify-source.py
```

This checker protects the upstream inputs and the enumerated downstream build
changes. Project navigation and other root documentation can evolve separately.
