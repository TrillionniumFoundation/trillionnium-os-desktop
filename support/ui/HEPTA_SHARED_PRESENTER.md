# Original Hepta shared presenter candidate

## Status and source

`hepta-shared-presenter` is a default-off Desktop candidate. It uses the original
Hepta `hepta-control-core` and `hepta-robrix-ui` Git packages directly. Desktop
still renders with eframe/egui. This slice shares the original draft model and
presentation/action functions; it does not qualify a shared Makepad renderer,
Web runtime, mobile port, accessibility backend or production chat submission.

The upstream is [Hepta PR #3067](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/3067),
commit `56630b12b8a4c69fff2c47b95b36d88a7389c39f`,
tree `15ff893b92898185ea709e847b244e4d66ae2bf4`. Both dependency declarations pin
that full revision. `hepta-robrix-ui` has `default-features = false`: its `ui`
and `native-host` features are not enabled. The resulting Desktop dependency
lock contains neither Makepad nor a replacement UI implementation.

The Desktop source base is [PR #251 at 64736996](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/tree/64736996d310d597ffba513ee109264cd5f5f83f),
tree `363700005afb52d2ac88aab709c3e0d0f78bcc0a`. Its shared activation state
transitions are retained; a read-only frame projection exposes the same IME
confirmation fence to the candidate editor. The Objective Session adapter in PR #255 is a
separate change; this candidate must be combined by applying the actual diffs,
without replacing the newer Objective adapter with an older Session snapshot.

[`HEPTA_SHARED_PRESENTER.json`](HEPTA_SHARED_PRESENTER.json) records the exact
upstream commit, tree, package manifests, original lock, four model/presenter
files, their original tests and license files. No Hepta implementation is
vendored or copied into Desktop. The original Git checkout remains the only
source of those packages.

To build this candidate explicitly:

```sh
cargo build --manifest-path ui/Cargo.toml --workspace --bins --locked \
  --features trill-shell/hepta-shared-presenter
```

Then follow the existing [Linux host run guide](RUN.md). A default build keeps the existing editor.
The feature changes local composition; it does not make an unavailable owner
or Send action available.

## Ownership and data flow

| Data or action | Actual owner and behavior |
| --- | --- |
| Current text in each Personal/Research/Build workspace | One original `ChatWorkspace` inside `SharedComposer`; the former persistent Desktop `String` is absent when the feature is enabled. |
| Editor callback | A temporary `String` for one egui call; one complete edit is passed to original `apply_action`. It is not stored as a second draft. |
| Composer text, status and IME state | Original `project`, `PresentationAction`, `PresentationCommand` and `RoomKey`; stale original presentation keys are refused. |
| Saved local drafts and quoted context | Existing Desktop `DraftBook` and `LocalDraft` archive. These remain visibly local and unsent. They are not Hepta timeline messages or delivery receipts. |
| Host task state and commands | Existing Session, broker and freshness checks. No second transport, ledger, task cache or owner is introduced. |
| Hepta history and identity | No owner is installed by this wrapper; no Session snapshot is inserted into original chat history. Workspace labels do not become authenticated principals. |
| Send | Original `RequestSend` still yields `SendUnavailable` outside composition, and `Ignored` during composition. The Shell does not wire a new Send button. |

`ui/core/src/shared_chat.rs` is a narrow wrapper over original package APIs. It
does not expose a mutable `ChatWorkspace`, an owner-installation API, signing,
Objective preparation, history mutation or network I/O. Its read projection
borrows the original draft; it does not keep a second rendered transcript.

`ui/shell/src/conversation.rs` keeps the existing local archive. Saving checks
composition, rejected-edit status, draft/context validity and archive capacity
before asking the original presenter to clear the active text. Only after Clear
succeeds does Desktop append an immutable local capture. Neither step reports
delivery, admission, task completion or device effects.

Three host workspaces keep separate original local composer instances. This is
the existing Desktop workspace behavior, not three authenticated Hepta owners.
The synchronous widget callback captures its original `RoomKey` before editing;
this slice does not define a cross-process action bus or asynchronous room router.

## Input transaction and 16 KiB behavior

The old Desktop editor accepted text beyond its 16 KiB archive limit, kept all
of it visible, and refused Save. The original Hepta editor model enforces the
same byte limit at Edit: it rejects an over-limit or NUL-containing edit and
retains the last accepted text. This is an intentional candidate behavior
change. Feature-on and feature-off regressions assert their different results.

The candidate shows an explicit rejection message and prevents Save until the
user edits again. It never silently truncates UTF-8 or saves the older text as
though the rejected edit had succeeded. Exact-boundary and multibyte regressions
cover the original 16 KiB rule.

egui deletes a selection before inserting pasted text or an IME prediction. A
mutable adapter that rejected only the insertion could already have deleted
the selected text. The Shell therefore runs the real `TextEdit` against a
frame-local transaction, then applies its full result to the original model.
On rejection it restores the previous cursor/selection and undo contents and
requests a repaint. The real callback's IME lifecycle is retained, so rejecting
a commit does not revive an earlier active composition. The temporary layout
from the rejected callback is replaced on the requested repaint.

The actual egui `Preedit`, `Commit`, `Disabled` and confirmation-key lifecycle
continues through the existing activation guard. The wrapper forwards the
guard's composition state to original `SetComposing`. Saving, clearing and
candidate workspace/page/tab navigation respect the original guard, including
the entire Commit frame and delayed confirmation keys. Merely seeing
`composing == false` after a Commit is insufficient to move the editor.
While that same confirmation fence is active, the candidate TextEdit disables
its Return shortcut so a same-frame or delayed IME Enter does not insert an
unintended newline. This includes a delayed press and release delivered together:
the policy's pending state may clear at frame end, but that whole confirmation
frame remains fenced. A fresh Enter in a later frame after key release keeps
normal multiline editing; the default feature-off editor retains its existing
behavior.

Headless egui event tests are distinct from a physical input-method test. They
cannot establish Wayland/X11 candidate placement, touch keyboards, accessibility
tree behavior or a working screen reader. Those require the original native
host gates and real device/input evidence.

## Dependency alignment and wire compatibility

Cargo rejected the old exact Desktop pins (`serde 1.0.219` and
`serde_json 1.0.140`) together with the original package's exact
`serde 1.0.229` and `serde_json 1.0.151` requirements. The candidate aligns only
these two direct pins in `ui/Cargo.toml` and `services/hepta-os/Cargo.toml`.
Both locks were generated by Cargo from the actual Git and registry sources.

The UI lock changes the existing Serde, serde_derive and serde_json versions,
adds serde_core, zmij, unicode-normalization, tinyvec and the two original Git
packages, and removes ryu. Its other existing registry versions remain the
same. The independent observer lock also moves syn from 2.0.119 to 3.0.9 because
the new original serde_derive uses syn 3; the UI lock already contained syn 3.0.9.
No checksum or lock entry was synthesized by hand.

`ui/core/examples/wire_compatibility.rs` emits a deterministic corpus using the
real Desktop types: strict host requests, task states, old snapshot defaults,
integer boundaries, representative float bit patterns and parsed observation
rounding boundaries, Unicode/escaping, local draft/context JSON and the existing
Notes fixture JSON. Validation runs the
same example against the exact original Desktop source/lock and the candidate
source/lock. Both `wire-compatibility-v1.json` and
`wire-compatibility-aligned-v1.json` are verbatim outputs of those actual Rust
1.88 executions; neither was edited to hide a difference.

The first actual feature-on comparison found three differences. Original
`serde_json/float_roundtrip` feature unification changed f32 rounding just above
a half-ULP boundary and rejected f32 overflow that the old observer had accepted.
`HostResources.load_average_1m` now uses a field-level numeric Visitor: integer
tokens narrow directly from i64/u64, decimal tokens narrow from f64, and null or
an absent field remains `None`. The intermediate `Option<f64>` approach restored
the first cases but double-rounded two large signed/unsigned integer examples;
independent review found this, and both were reproduced as separate real red
tests before the numeric Visitor fixed them. The same six public-type tests run
against the original source/lock and the candidate. No signed request or identity
is re-encoded. The new library feature may also affect f64 decimal parsing, so
this bounded evidence establishes the retained number-dispatch path and tested
boundaries, **not bit-exact equivalence for every possible decimal JSON input**.

One lexical difference remains in the corpus: the MAX-f32 observation serializes
as `3.4028235e+38` instead of `3.4028235e38` after the registry serializer changes
from ryu to zmij. CI checks the actual output against the aligned golden, then
`verify_wire_compatibility.py` requires 51 original case strings unchanged and
allows only that exact token replacement in the remaining case. It compares the
complete stdout bytes and also proves the two finite decimal values equal with
`Decimal`; it does not canonicalize other JSON or discard the initial failures.
The result is **not 52 byte-identical cases**. A new exponent spelling or any
other change requires a separate explicit review.

The known producer reads `/proc/loadavg` into this field. The Session returns it
inside an unprivileged snapshot, the bounded JSON transport parses it into a
typed `Response`, the Shell uses it as a resource label, and `trill-ctl`
pretty-prints the typed response. In the reviewed
Desktop source, no hash, signature, authority digest, retained Objective bytes
or persisted draft identity consumes that resource observation JSON. The exact
original Objective envelope and its owner/history bindings remain separate.
This search establishes the checked-in consumer path, not a claim about unknown
external consumers or every possible JSON number. Original transport and Session
package tests remain required after dependency alignment. The existing frame-size
limit still applies to the actual emitted bytes, including the extra exponent
character; an oversized snapshot is refused rather than partially emitted.

## Explicit candidate gates

Use the A10 Rust 1.88.0 toolchain. Run from the repository root:

```sh
python3 -I tests/ui/test_shared_presenter_source.py
python3 -I tests/ui/test_wire_compatibility.py
cargo metadata --manifest-path ui/Cargo.toml --locked --format-version 1 \
  --features trill-shell/hepta-shared-presenter \
  --filter-platform x86_64-unknown-linux-gnu > /tmp/shared-presenter-metadata.json
python3 -I tests/ui/verify_shared_presenter.py \
  --metadata /tmp/shared-presenter-metadata.json
cargo test --manifest-path ui/Cargo.toml --all-targets --locked \
  -p hepta-control-core -p hepta-robrix-ui -p trill-ui-core -p trill-shell \
  --no-default-features --features trill-shell/hepta-shared-presenter
cargo clippy --manifest-path ui/Cargo.toml --all-targets --locked \
  -p trill-ui-core -p trill-shell --features trill-shell/hepta-shared-presenter \
  -- -D warnings
cargo run --quiet --manifest-path ui/Cargo.toml --locked \
  -p trill-ui-core --example wire_compatibility --features hepta-shared-presenter \
  > /tmp/shared-presenter-wire.json
cmp tests/ui/wire-compatibility-aligned-v1.json /tmp/shared-presenter-wire.json
python3 -I tests/ui/verify_wire_compatibility.py \
  --original tests/ui/wire-compatibility-v1.json \
  --candidate /tmp/shared-presenter-wire.json
```

The source gate checks the real Cargo-resolved package IDs and enabled features,
the actual Git checkout HEAD/tree, every recorded source byte and every original
package file against its Git tree blob, plus the clean package directories.
Index flags cannot hide modified modules outside the review manifest.
Same-named local replacements, mismatched Git
sources, disabled candidate validation, enabling the unqualified Makepad
renderer, modified sources and altered local license notices fail the gate.
It does not rely on a package name or a successful default-only workspace test.

The A10 workflow explicitly invokes these candidate checks in addition to the
existing default build, real host/Weston checks and Clippy gates. The README guard
migration in PR #247 and Objective feature gates in PR #255 are independent
workflow hunks that must be preserved when composing the changes.

Execution receipts must identify the source bytes and locked toolchain actually
run. An earlier core-only pass, a dependency compile, a resource-limited stop or
a queued CI job must not be recorded as a final Shell, Wayland or Makepad pass.

## Remaining integration

The next renderer slice must use the original pinned Robrix/Makepad widgets and
presenter, replace this candidate's egui composition adapter, and keep the same
original draft instance. Enabling an optional dependency alone is not renderer
unification. Desktop Session and broker continue to own existing host operations.

Chat submission needs the original authenticated SourceEnvelope/AuthBus issuer
bridge and the original durable pre-send retention/mark-started capability. The
separate FinalUse issuer for production operations does not sign chat Objectives.
Only original admission/history observations can populate delivery or task
outcomes; an unknown result must retain its original request and must not retry
automatically. Local waiter cancellation is separate from original run cancellation.

Native and Web must then exercise the same original renderer, owner projection,
keyboard/IME behavior and bounded timeline. Each platform still needs actual
build/runtime evidence, and accessibility and mobile input need their own gates.
This candidate does not change any of those statuses to complete.

## Notices

The exact original repository [LICENSE](licenses/HEPTA-LICENSE.txt) and
[NOTICE](licenses/HEPTA-NOTICE.txt), plus the original
[Robrix MIT notice](licenses/ROBRIX-MIT.txt), are retained verbatim. Their hashes
are bound to the same upstream source manifest and checked against the actual
dependency checkout. The original Robrix notice attributes Project Robius
Developers. This candidate does not import Robrix logos or separately licensed
SVG assets, or change the licenses of upstream source files.
