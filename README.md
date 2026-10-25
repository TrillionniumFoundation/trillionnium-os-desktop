# Trillionnium OS Desktop

Rust desktop and operating-system work for a Hepta-led execution platform. The
kernel is derived from Asterinas; Hepta keeps the existing authority, durable
writer, outbox and operation-history ownership.

## Start here

| Need | Entry point |
| --- | --- |
| Current candidate capabilities, evidence and unqualified product gates | [Current capabilities](docs/CURRENT_CAPABILITIES.md) |
| Latest product execution, ordinary Notes recovery and remaining gates | [2026-10-24 product execution report](results/integration/2026-10-24-product-closure/README.md) |
| Current source guards, module inventory and kernel profile verification | [Foundation guide](docs/current/FOUNDATION.md) and [active modules](docs/current/MODULES.md) |
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
and Hepta-carried patches to [Hepta `22e87e0dd6560a7b925e716a33011378ae07a9a2`](https://github.com/TrillionniumFoundation/hepta-private-ci/commit/22e87e0dd6560a7b925e716a33011378ae07a9a2),
tree `7e376f5d3509cf38e13b513ca2b87d9eecd7dc47`, and uses Rust 1.96.0.
The UI Cargo root explicitly patches all four original AccessKit crates to this
same source. `services/hepta-os` remains a local protocol/transport crate; it
does not acquire a fictitious Hepta Git dependency.

The [product execution report](results/integration/2026-10-24-product-closure/README.md)
records published Desktop `0a268d8928d76682a59c8cc0be88428845f40ce3`, tree
`d7c0d61a1519db8f4b0a7178b9f6867f85719b48`, and the selected Hepta source above.
The final app-window tests passed 48 cases with one real-font case ignored by
default; strict Clippy and the three Session/Notes binary builds passed. The
core/app suite and explicit real-font run retain their earlier v2 source
identity. Final Notes v5 passed all five ordinary save/reopen/edit checks in an
owned Xvfb session, using those exact new binary hashes, XRes PID checks and
AT-SPI controls. This verifies ordinary document recovery while preserving the
old effect receipt; it does not establish production writer completion.

Final local Python checks also passed: spec 53 cases in both normal and optimized
Python, product-source mutations 10 in both modes, Android device-organ 24,
product tooling 65, and the selected-source verifier. The report retains the
initial sandbox errors and the unchanged host rerun.

The archived [canonical SDK receipt](results/integration/2026-10-24-product-closure/closure-evidence-v3/sdk-final/canonical-build-v1/receipt.json)
now records Desktop execution commit `a7621d8022f52add679bd6edba5d0bad6772dabc`,
tree `e9026801f2686b7ea3f89759609c326f72fb2cfa`; review commit
`1f94c4b11ed7a71ec7bb9344a40c8f284da5c7e4` has the same tree and a different
commit identity. With Rust 1.96.0, the explicit clipboard feature, verified SDK,
locked offline inputs and release profile, the complete UI workspace/all-target
test command passed 318 tests with two ignored executions; strict Clippy and
all five binary builds passed. Both ignored executions are the explicit
real-host-font test, once in app-window and once in Shell. The build used a
clean source checkout and the existing target cache; it does not establish
an empty-cache or fresh-OS cleanroom build.

The [real package and installation records](results/integration/2026-10-24-product-closure/README.md#34-原-root文本和-android-所有权边界)
verify the 72-file package, its 61 resources, and administrative A1 → B2 → A3 → B4
selection with two real deployment-lock refusals. Those operations did not
launch original Root or the installed UI. The installed stripped Shell hash
`080ad7e9…` is distinct from the canonical unstripped runtime hash `e315c61f…`.

The [Makepad v3 window receipt](results/integration/2026-10-24-product-closure/closure-evidence-v3/sdk-final/orca-window-v3/receipt.json)
records seven passing atomic EditableText checks, including request-scoped
PasteText, on that canonical runtime. The full attempt failed when real IBus
preedit did not engage the original composition guard. Physical keyboard,
Wayland IME and complete Orca qualification remain unverified; ordinary Notes
and earlier windows do not confer those results.

The [v4 failure and focus readback](results/integration/2026-10-24-product-closure/closure-evidence-v4/sdk-final/orca-window-v4/ibus-failure-readback.json)
retains that failure on the same canonical executable. All recorded X11 focus
queries stayed on window `12582916`, and the observer received two visibility
events without a FocusIn/FocusOut event; meanwhile the Message entry lost its
AT-SPI focused state. The original Orca log shows speech initialization and
processing of these focus events, but the real IBus composition guard still
failed and `orca_consumer_qualified` remains false. The [21-file v4 group](results/integration/2026-10-24-product-closure/closure-evidence-v4/orca-v4-evidence-inventory.json)
preserves the failed attempt, diagnostics and two actual screenshots. It is
separate from later Android, native-suite and static-ELF results.

The [new Android execution](results/integration/2026-10-24-product-closure/closure-evidence-v4-native-android/android-unsigned-a762-final/execution-receipt.json)
rebuilds the original receiver on the exact a762 source using SDK 35 and the
verified original APK resources. Its binary Manifest is preserved; the nine
receiver source files and complete tool/JDK/JAR snapshots match before and
after. The unsigned APK is 19,402 bytes. Signing, deployment and device actions
were not performed: the retained original signer, deployed strict receiver and
original live owner still need their actual acceptance.

The independent [full native-host rerun](results/integration/2026-10-24-product-closure/closure-evidence-v4-native-android/native-full-libs-durable-short-04/result.json)
on Hepta 7ecc reports 1,065 passed, one capacity timeout and 99 skipped. A shorter
durable fixture path removed the preceding run's 16 Unix socket failures while
retaining the same eight test binaries and original deadlines; the complete
suite still exits 100. Both original wrappers stopped before their paired tests.
Separately, the [original static-entry build](results/integration/2026-10-24-product-closure/closure-evidence-v4-native-android/native-original-entry-final-02/result.json)
on Desktop a37 / Hepta 7ecc compiled and packaged successfully, then rejected
the 13,243,416-byte ELF against the unchanged 8 MiB admission limit. No native
ELF or guest execution is claimed. The [new 58-file evidence group](results/integration/2026-10-24-product-closure/closure-evidence-v4-native-android/inventory.json)
retains those terminal results and marks both paired steps as not executed.
Later IME and native optimization source changes need separate receipts.

The earlier [scoped component executions](results/integration/2026-10-24-original-owner-product/text-native-v10-v11/README.md)
keep their original source identities and package/filter scopes. Neither those
records nor the new host checks qualify an installed production Root/App Server
deployment, the original Notes writer's durable terminal, a signed Android
receiver or an Asterinas native device. The report records those remaining
original-owner and deployment inputs explicitly.

The original runtime contracts are pinned beside their owners:
[Root/Agentd text](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/22e87e0dd6560a7b925e716a33011378ae07a9a2/codex-rs/hepta-agentd/NATIVE_TEXT_SESSION.md),
[original UI composition](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/22e87e0dd6560a7b925e716a33011378ae07a9a2/apps/hepta-control-ui/rust/robrix-ui/NATIVE_COMPOSITION.md),
[Notes crash recovery](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/22e87e0dd6560a7b925e716a33011378ae07a9a2/codex-rs/hepta-agentd/NOTES_RECOVERY_QUALIFICATION.md)
and [Android target](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/22e87e0dd6560a7b925e716a33011378ae07a9a2/codex-rs/hepta-memory/PRODUCTION_ANDROID_TEXT.md).

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
The [current execution report](results/integration/2026-10-24-product-closure/README.md)
keeps canonical build, package installation and actual window results separate.
Its third evidence inventory retains 71 original files and its six historical
deferrals. A separate native/Android inventory now adds 58 terminal files, while
recording two paired steps that their failed library runs never reached.
Original production Root/App Server and Android-owner inputs are still required.

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
