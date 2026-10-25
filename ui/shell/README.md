# trill-shell

The native Rust presentation process, with egui/eframe and the explicitly
selected original Makepad renderer. Workspace/Chat is the default entry;
Tasks, Context and Console are workspace views.

## Ownership and code map

[main.rs](src/main.rs) owns presentation and the bounded worker handoff.
[conversation.rs](src/conversation.rs) renders typed drafts and context;
[local_drafts.rs](src/local_drafts.rs) implements explicit private export/restore
and the single-writer background recovery checkpoint. Schema v4 preserves all
workspace composers, anonymous rooms and parked principal text; it never rehydrates an execution
owner, live task observation or delivery. See [product recovery](../../support/ui/PRODUCT.md)
for configuration, shutdown, corruption and concurrent-window behavior.
[hepta_panel.rs](src/hepta_panel.rs) presents runtime observations.
[objective_panel.rs](src/objective_panel.rs) presents bounded original-owner
Objective status, cancellation, Notes controls and navigation recovery.
[native_makepad.rs](src/native_makepad.rs) adapts the original Makepad ports to
those same Desktop actions and the existing conversation workspace.

Session restart preserves the existing caller IDs and queries them through the
new trusted transport. Shell process restart reads navigation IDs from the
original owner's availability projection; restored cards begin Unknown and
cannot resend their requests. New IDs carry a workspace navigation prefix;
legacy IDs retain an unknown workspace. Neither classification supplies scope
or authority. A fresh complete traversal is required before enabling new writes,
and an unfinished/unknown request prevents minting a replacement ID. The previous
request list only selects which original status to query. Cancellation controls
are bound to the selected intent identity and remain stable when history appears.

Unsaved drafts remain local until an explicit action submits them through the
configured original host. The Notes action below is a bounded Objective request;
ordinary local conversation editing does not submit one. Never infer an owner receipt from a local animation, a queued
UI action, a first-frame marker or a running host PID. The original owner must
provide operation outcomes and reconciliation.

## Shared Notes controls

Both renderers use `ObjectivePanel`'s `notes_controls_view`,
`write_note_from_draft`, `refresh_notes_controls` and `cancel_note_request`.
Write sends one literal-text Notes Objective through the existing Session
bridge. It preserves the complete draft and refuses quoted context, empty or
over-4096-byte text, active composition, incomplete recovery navigation, stale
readiness, a host issue or an unfinished original request. A fresh known pending
application receipt also blocks a new write until the original request is
reconciled. Refresh only queries original availability/status; Cancel queues
one cancellation of the same original intent. Queue rejection is reported,
and uncertain delivery never creates a replacement intent or a repeated cancel.

The Makepad adapter implements the original `NativeNotesView` and
`request_write_note` / `request_notes_refresh` / `request_notes_cancel` ports.
It additionally checks the current room identity, source epoch, composition,
window state and visible Conversations page before forwarding an action.
The host rechecks readiness when the callback executes. The exact original API
and dependency pin are recorded in [DEPENDENCIES](../../support/ui/DEPENDENCIES.md).

Status displays the original request state separately from the current Notes
document's target, revision, short text digest and pending-receipt flag. That
readback has its own freshness clock; it is neither an exact operation receipt
nor evidence that a succeeded run saved the current document. Observed text is
never copied into the draft. On Session replacement the old document snapshot
is cleared, while original intent IDs remain available for status recovery.

Passive polling alternates availability with bounded, fair status rotation
over retained unresolved original IDs, including earlier requests. A full read
queue keeps the selected status for the next attempt; it cannot consume action
capacity. Polling never submits, cancels or replays an effect. See the
[Notes ownership and recovery contract](../../support/ui/NOTES_ORGAN.md) and
[durability manual](../../support/ui/NOTES_DURABILITY.md).

## Failure and input handling

Follow [OBSERVATION_FRESHNESS](OBSERVATION_FRESHNESS.md) for stale/unknown
projection. Keep transport work off the rendering path and distinguish failure
to enqueue from a request whose result is unknown.

IME composition, confirmation keys and semantic widget activation require
separate handling. Follow [X11_IME](../../support/ui/X11_IME.md) and
[CJK_RENDERING](../../support/ui/CJK_RENDERING.md); font coverage and a headless
layout test do not establish a working input method or accessibility bridge.

## Development

```sh
RUSTUP_TOOLCHAIN=1.96.0 cargo test --manifest-path ui/Cargo.toml -p trill-shell --locked
cargo +1.96.0 test --manifest-path ui/Cargo.toml -p trill-shell --locked objective_panel
cargo +1.96.0 test --manifest-path ui/Cargo.toml -p trill-shell --locked --features hepta-native-makepad native_makepad::notes_tests
cargo +1.96.0 clippy --manifest-path ui/Cargo.toml -p trill-shell --all-targets --locked --features hepta-native-makepad -- -D warnings
```

See [workspace setup](../README.md), [Chat contract](../../support/ui/CHAT_WORKSPACE.md)
and [host test plan](../../tests/ui/TESTPLAN.md) for owned-window and compositor
checks. If CARGO_TARGET_DIR is set, use its debug directory for the binaries.
Shared regressions cover readiness/issue and pending-receipt gates, independent
readback freshness, fair recovery under a full read queue, and Session
migration. Native callback regressions cover source fences, one original
intent and preservation of the complete draft. These commands specify scope;
actual source-paired results belong in the build receipt.

## Original Makepad renderer

The optional Linux `hepta-native-makepad` feature starts the original Hepta
Makepad `App` from the same `trill-shell` binary. Choose it with
`--renderer makepad --workspace personal|research|build`; the default renderer
remains egui. A native window borrows one fixed original `ChatWorkspace` from the
existing `DraftBook`, while retaining the existing Session Bridge, receive
reducer and observation freshness rules. Original conversation navigation stays
inside that workspace. No new runtime, chat owner or signing identity is made.

The native renderer with its authenticated text adapter requires Rust 1.96.0.
Prepare the exact Cargo-resolved resources before launching:

```sh
cargo +1.96.0 build --manifest-path ui/Cargo.toml --locked -p trill-shell --features hepta-native-makepad
cargo +1.96.0 metadata --manifest-path ui/Cargo.toml --locked --format-version 1 --features trill-shell/hepta-native-makepad > /tmp/trill-native-metadata.json
python3 support/ui/prepare_native_makepad.py --metadata /tmp/trill-native-metadata.json --output /tmp/trill-makepad-resources
TRILL_UI_MAKEPAD_RESOURCES=/tmp/trill-makepad-resources ui/target/debug/trill-shell --renderer makepad
```

The packager copies verified original resources into a new directory, including
29 assets, 15 notices and the corresponding Liberation source archive. It never
changes Cargo checkouts. Missing pinned CJK fonts and that source archive are
downloaded only while packaging; `--offline` refuses missing inputs. Startup
checks every file's size and SHA256 and configures `Cx.package_root` before the
original App registers scripts. `--page console` selects the original Console,
whose refresh button queues existing read-only Session requests and reconnects
the original chat client with its retained identities. With no explicit page,
the prior native Console/Conversation selection is restored. Window exit drops
only this client's channels; an original turn is interrupted only through Stop.

The same feature connects `NativeChatComposition::poll_chat`, `request_send`
and `request_interrupt` to `hepta_session_host::text::TextChatAdapter`. That
adapter borrows the same original `ChatWorkspace`; it does not construct an
App Server, Agentd, issuer or separate conversation store. Configure the existing
Root UI lane with both environment inputs:

```sh
export TRILL_UI_CHAT_SOCKET=/absolute/path/to/root-ui.sock
export TRILL_UI_CHAT_ROOT_PID=1234 # replace with the actual original Root PID
```

The [text adapter development and technical handoff](../../services/hepta-session-host/TEXT_SESSION.md)
maps its source, feature tests, authenticated startup, streaming, approval and
same-identity recovery to the original Hepta implementation.

These inputs select a route and expected peer; they confer no authority. The
original Root must already register this UI process with a held pidfd, its
root-owned private lane registration, and the authorized existing thread. The
worker verifies the Root peer and authenticated hello before the adapter can
install the original `OwnerSession`. The initial window can remain local while
that independent registration is prepared; Console Refresh retries the original
connection. A missing pair leaves local drafts usable; a partial or invalid
pair is shown in Console. No human principal, owner capability, Agentd thread
override, signing key or issuer is accepted from Shell configuration.

Signing and I/O run on the bounded original worker. A signed proposal must pass
the original workspace's room, owner and input checks before the adapter queues
the exact dispatch. The original notification stream updates its own timeline.
Unknown delivery retains its intent for reconciliation, and rejected admission
does not clear the composer. Closing a window cannot manufacture a terminal
outcome.

The optional original UI host port is not authentication. Send remains disabled
until an independent authenticated host binds the exact owner/thread/generation.
Native input, rendered fonts and accessibility need their own executable
acceptance; an egui screenshot or AT-SPI result is not evidence for this renderer.
The [native Makepad qualification guide](../../support/ui/NATIVE_MAKEPAD.md)
provides the owned Xvfb/AT-SPI/real-IBus harness and records the remaining
EditableText, visual review and physical-device acceptance boundaries.
