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
| Dated execution records and their original source identities | [Status](docs/STATUS.md) |
| Retained successes, failures and evidence locations | [Evidence index](docs/EVIDENCE_INDEX.md) |
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

<!-- current-hepta-source:start -->
The current independent `notes_calculator_v1` candidate selects one original
Hepta source for Root, Agentd, UI/core and the carried dependency patches:

| Input | Exact identity |
| --- | --- |
| Hepta commit | [`14e2d89b3367232ec5dbe6187f09feed0f2b68d3`](https://github.com/TrillionniumFoundation/hepta-private-ci/commit/14e2d89b3367232ec5dbe6187f09feed0f2b68d3) |
| Hepta tree | `0e12d53adf6a13721fdb2feef0e974d903b92e85` |

The Desktop code handoff is
[`f5fbc7e1a533e5bec588575ab56312a3203f6d8c`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/f5fbc7e1a533e5bec588575ab56312a3203f6d8c),
tree `2998926686ce45c38ec14d6f42ab0871ba25faa1`. This identifies the candidate
source, not a completed build or installation. Every successor records its
actual Desktop commit/tree in its build receipt. All 39 Hepta Git dependencies
and patches in the three consuming manifests select the commit above and use
Rust 1.96.0. The UI Cargo root explicitly patches all four original AccessKit
crates to this source. `services/hepta-os` remains a local protocol/transport
crate without a Hepta Git dependency.

[HEPTA_SHARED_PRESENTER.json](support/ui/HEPTA_SHARED_PRESENTER.json) is the
canonical Hepta identity. The [dependency guide](support/ui/DEPENDENCIES.md)
records the six product lock roots and source/graph checks, while
[Current capabilities](docs/CURRENT_CAPABILITIES.md#current-product-pair)
records the outstanding execution gates. The joint profile needs a new original
Core thread and both original Notes/Calculator target identities; selecting it
does not migrate a Notes-only catalog, grant human admission, renew an owner
lease or qualify joint recovery. See the [Root assembly contract](services/hepta-session-host/src/product_root/DESKTOP_PROFILE.md)
and [Calculator protocol](ui/core/CALCULATOR_PROTOCOL.md).

The [evidence index](docs/EVIDENCE_INDEX.md) retains earlier component, Cargo,
kernel and UI results with their exact tested sources. Those results do not
qualify this candidate's release binaries, real window, installed deployment or
signed Android receiver. Each final source profile must bind the actual complete
Desktop commit/tree, Cargo-generated locks, features, binary hashes and execution
receipts; source and graph verification do not authorize production effects.

The original runtime contracts are pinned beside their owners:
[Root/Agentd text](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/14e2d89b3367232ec5dbe6187f09feed0f2b68d3/codex-rs/hepta-agentd/NATIVE_TEXT_SESSION.md),
[original UI composition](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/14e2d89b3367232ec5dbe6187f09feed0f2b68d3/apps/hepta-control-ui/rust/robrix-ui/NATIVE_COMPOSITION.md),
[Notes crash recovery](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/14e2d89b3367232ec5dbe6187f09feed0f2b68d3/codex-rs/hepta-agentd/NOTES_RECOVERY_QUALIFICATION.md)
and [Android target](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/14e2d89b3367232ec5dbe6187f09feed0f2b68d3/codex-rs/hepta-memory/PRODUCTION_ANDROID_TEXT.md).
<!-- current-hepta-source:end -->

The preceding 2026-11-03 checkpoint was Desktop
`745c0731aed270ee394145c6767371a6af47f49f`, tree
`fa70b1b95206d25775009c6965245d34051468a4`, with Hepta
[`a39a0871d9601ffccb5e0d95d8f39d54b3a63360`](https://github.com/TrillionniumFoundation/hepta-private-ci/commit/a39a0871d9601ffccb5e0d95d8f39d54b3a63360),
tree `e03f9b3eca364222029298496d3e4f1f5e1bf5de`. Its selection and any receipts
remain historical; they are not the current Cargo pin or successor qualification.

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
historical 43 native UI and 54 AccessKit scoped tests concern the default original SDK;
they do not qualify the clipboard candidate. See the [profile procedure](support/ui/PRODUCT.md#explicit-original-sdk-clipboard-candidate)
and [real window gate](support/ui/NATIVE_MAKEPAD.md).

The explicit `trill-shell/hepta-native-preedit-sdk` profile separately binds
prepared SDK tree `6b422b3120f5f9b5c7ada579b55f647d51bd7fcf` and its own lock.
Its [preedit contract](support/ui/PREEDIT_TEXT_PROFILE.md) requires the final
packaged window's real IBus and AT-SPI gate; earlier SDK tests remain scoped
to their original source and selected profile.

## Evidence and supported scope

Use the [evidence index](docs/EVIDENCE_INDEX.md) to find the scope and source
identities attached to each execution record. A source-profile check verifies
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
