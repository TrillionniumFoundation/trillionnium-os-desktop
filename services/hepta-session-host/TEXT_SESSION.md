# Native text adapter development and handoff

The `native-text` feature of this crate connects the existing Makepad
`ChatWorkspace` to the original Hepta Root/Agentd text worker. The original
App Server owns the thread, turns, tool events and history. This adapter owns
only bounded presentation and dispatch-ticket correlation. Its separate
Objective/Notes path remains documented in [README](README.md).

## Source and owner map

| Source | Development responsibility |
| --- | --- |
| [src/text.rs](src/text.rs) | `TextChatAdapter`: authenticated owner installation, exact prepared-input dispatch, bounded event reduction, original history and delivery reconciliation |
| [src/text_approvals.rs](src/text_approvals.rs) | Original command/file callback details, explicit approval permission and response correlation |
| [src/text_tests.rs](src/text_tests.rs) | Presentation fixtures for recovered identity, unchanged local drafts, stale connections and separate approval permission |
| [Shell native_makepad.rs](../../ui/shell/src/native_makepad.rs) | Borrow the current original workspace, poll outside Draw, queue Send/Stop/history/approval and wake the native event loop |
| [Shell native_text_config.rs](../../ui/shell/src/native_text_config.rs) | Validate the two original Root endpoint hints without accepting a principal or route override |
| [Original Hepta text session](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/9600de28f5295c1758dd7e19bcac743fe5cfc082/codex-rs/hepta-agentd/NATIVE_TEXT_SESSION.md) | Trusted startup, Root registration/pidfd, worker/issuer source map, build/test commands and the same-thread recovery protocol |

The cross-repository link is fixed at the current Cargo source
`9600de28f5295c1758dd7e19bcac743fe5cfc082`, tree
`5cf15149d0e0d2ef1ae7d1d2784ea55c99b9a658`; the
[dependency contract](../../support/ui/DEPENDENCIES.md) checks the complete
shared source and lock combination. The
[source profile](../../docs/agents/ORGAN_RELEASE_PROFILE.md) must also bind the
complete Desktop commit, actual generated locks and feature build. The
[historical eight original text integrations](../../results/integration/2026-10-24-original-owner-product/text-native-v10-v11/README.md)
are scoped process/protocol executions with fixture inputs; installed production
Root, real model credentials and final combined product acceptance remain open.

## Build and focused checks

Run from the Desktop repository root with the Cargo.lock files retained:

```sh
cargo +1.96.0 test --locked --manifest-path services/hepta-session-host/Cargo.toml --features native-text --lib text::
cargo +1.96.0 build --locked --manifest-path ui/Cargo.toml -p trill-shell --features hepta-native-makepad
```

The first command tests adapter fixtures; it does not start a production Root
or model. The second compiles the actual native renderer and this adapter.
Use the [Shell resource/build instructions](../../ui/shell/README.md#original-makepad-renderer)
before launching, the [native input guide](../../support/ui/NATIVE_MAKEPAD.md)
for the actual window gate, and the [product guide](../../support/ui/PRODUCT.md)
for a source-bound installed run. Hepta's process test and deployment-input
requirements remain in its original text manual.

## Inputs, outputs and failure boundary

`TextChatAdapter::start` accepts only the exact Root socket, expected actual
Root PID and event-loop waker. The original worker verifies UID0 peer identity
and the registered UI lifetime before returning `Authenticated`. The Root hello
supplies the existing principal/session/permission revision and exact original
Agentd/thread route. A configured socket, `Connected` event or Session health
does not install an owner.

Send reads the active original workspace's accepted text, requires 1–8192
UTF-8 bytes, and refuses during IME composition, owner expiry, recovery, pending
history, an earlier history page or capacity exhaustion. Root prepares one
original signed reference; the original workspace must accept it and return
its dispatch ticket before the worker dispatches. Rejection preserves the local
draft. An observed original admission may clear only the exact submitted draft;
a restored reference never clears a new draft with the same bytes.

`poll` reduces at most 32 worker events per call into the same workspace and
returns availability for Send, Stop and history controls. Tools/artifacts are
original timeline observations. Approval has its own permission and waits for
the original callback resolution. Stop requests original cancellation and waits
for the owner outcome. Neither enqueue success nor a transport write is a
terminal or device-effect receipt.

All events are fenced by the physical connection and original room/owner.
Refresh reconnects to the same original route and retains signed identities;
unknown delivery is reconciled without a replacement input. Root recovery and
initial history have separate barriers before Send is enabled. Large-history
preview limits do not turn unknown delivery into success. The original owner
retains unresolved identities and controls terminal retirement.

Local v4 draft recovery is independent of this protocol. Its configuration,
single-writer lock, corruption behavior and principal partitions are documented
in [product recovery](../../support/ui/PRODUCT.md#upgrade-rollback-and-uninstall).
Loading a checkpoint cannot restore a Root session, history or execution grant.
