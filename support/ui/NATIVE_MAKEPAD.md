# Original Makepad input and accessibility qualification

The Linux `hepta-native-makepad` profile runs Hepta's original Makepad `App`
with the existing `ChatWorkspace`, original editor, original IME router and
original timeline. Desktop supplies its Session observations and the independent
Root text adapter through `NativeChatComposition`. The native profile requires
Rust 1.96.0. Source and lock pins remain in the actual Cargo manifests; the
qualification scripts never rebuild or patch a dependency checkout.

The baseline remains `trill-shell/hepta-native-makepad` with original SDK
337566c8 and its 54-file bundle; no additional Cargo config is needed. The
separate clipboard candidate is built with
`--features trill-shell/hepta-native-clipboard-sdk` and the exact generated
all-SDK `--config`, using its own worktree/lockfile and 61-file bundle. The full
metadata/source/package procedure is in [PRODUCT](PRODUCT.md). Never combine
the candidate feature with an unprepared SDK or merge its path lock into the
baseline.

The current Linux Notes product candidate selects the distinct
`trill-shell/hepta-native-preedit-sdk` feature through
[linux-preedit-profile.json](linux-preedit-profile.json). Build it with
`build_text_product.py --profile preedit-callbacks --committed-preedit-lock`
and the explicit source inputs described in [PRODUCT](PRODUCT.md). Its
reviewed SDK provides original XIM preedit callbacks and focus/undo handling;
the declared source copy uses the separately tracked prepared lock while the
ordinary Git SDK lock remains unchanged. Do not combine the clipboard and
preedit candidate features. The preedit feature does not enable the separate
native `PasteText` UI capability. Run the owned-window qualification with
`--atomic-editable-text`, the actual build receipt and `--packaged-binary`;
unit regressions and prepared resources alone do not qualify live IME input.

## Run the owned-window qualification

First inventory installed dependencies without connecting to an existing user
display, input method or D-Bus session:

```sh
/usr/bin/python3 -B tests/ui/native-makepad/inventory.py
```

The inventory lists Xvfb, xauth, X11 input utilities, the private D-Bus/a11y
launchers, IBus, real engine XML, Python GTK 3/AT-SPI namespaces, and optional
Orca packages. It uses the installed `gi.repository.Atspi` API directly and does
not require the optional `pyatspi` wrapper. Static engine names and dynamic
`engines exec` registrations are recorded separately; an empty static list does
not mean that a dynamic engine is missing. It does not install software or run
`ibus list-engine` against the user's session. The execution harness verifies
the exact engine name with `ibus list-engine --name-only` after starting its own
private bus. It requires the real `libpinyin` engine
by default; use `--engine` only for an installed engine that accepts the same
`nihao` → `你好` sample.

The window-owner helper additionally loads `libX11.so.6` and `libXRes.so.1`.
The private X server must expose XRes protocol version 1.2 or later, including
`QueryClientIds` with `LocalClientPID`. Library presence alone does not prove
that server capability; the helper checks it on the private display at runtime.

After building the actual Shell and preparing its verified native resources,
choose a new output directory whose parent exists:

```sh
/usr/bin/python3 -B tests/ui/native-makepad/qualify.py \
  --shell /absolute/build/debug/trill-shell \
  --resources /absolute/verified-makepad-resources \
  --hepta-source /absolute/original-hepta-checkout \
  --atomic-editable-text \
  --output /absolute/new-native-ui-receipt
```

`--hepta-source` selects the original test-helper checkout. It must contain
`apps/hepta-control-ui/test/native-accessibility-smoke.py` and
`apps/hepta-control-ui/test/x11_client_owner.py`; `--atomic-editable-text` also
uses `native-editable-text-smoke.py` from that directory. This harness source
may differ from the Hepta source that produced the frozen product ELF. Keep
the helper checkout's complete commit/tree with the run's provenance; the
harness records the exact helper hashes separately from the actual ELF, its
own files, the original child cleanup guard, and the packaged asset inventory.
Selecting a newer reviewed helper does not rebuild or repin the product.
`--build-receipt` additionally verifies
an existing successful receipt containing `status: "passed"`, `exit_code: 0`,
`source_commit`, `source_tree`, and `binaries.trill-shell.{sha256,bytes}`. Without
that input, runtime behavior can pass while `build_source_identity_verified`
remains false; a hash alone does not prove which source produced a binary.

When testing an extracted or installed distribution ELF, also supply
`--packaged-binary`. This selects the receipt's distinct `packaged_binaries`
hashes after the recorded GNU strip transformation. The default checks the
unmodified Cargo output in `binaries`. Neither path accepts the other artifact
by its filename, source label or file size alone. The build retains both hashes
so actual package acceptance can be distinguished from build-output acceptance.

The harness creates its own authenticated Xvfb, D-Bus, AT-SPI and IBus processes.
All XDG runtime/config/cache/data/state paths are new private directories with
short Unix socket paths. It compiles only a private copy of installed GSettings
schemas, uses IBus's memory configuration service, and selects a US layout on
its own X display. It never passes `--replace`, inherits an existing user bus,
sets a human principal, or starts Agentd/Root/Session. A missing Session is a
local observation failure and does not prevent this input test.

Every input target is bound to the retained Shell child through the original
`x11_client_owner.py` helper. It enumerates visible windows, then obtains each
resource's client PID from the X server using XRes `LocalClientPID`. Only one
visible window belonging to that child may be selected; multiple matching
windows are rejected. A missing match remains unavailable within the existing
startup deadline, and absent or ambiguous XRes ownership fails qualification.
Window titles, classes and client-written `_NET_WM_PID` are not ownership
evidence, and there is no fallback to them when the original SDK omits that
property. The test first proves that the display rejects a client without its
cookie. Cleanup reuses the repository's waitable-child identity guard, retaining the original
child until process-group signals finish. Only owned groups are signalled.
Private cookies and IBus state are removed after the run; receipts retain
synthetic draft outputs, logs and unmodified screenshots.

The two stages assert different contracts:

| Stage | Real input path and required observations |
| --- | --- |
| Supported AT-SPI and editor | Semantic focus and text selection; the private GTK/X11 clipboard supplies a complete CJK/combining/emoji paste through the original SDK; an 18 KiB selection replacement must report the original input-limit rejection and retain text, selection and prior undo; native Ctrl+Z/Redo; semantic New draft; the old room's accessible object cannot move the new room's caret. |
| Real IBus/XIM | Only ASCII `nihao` key events, then Space, reach the original window. Real preedit must disable navigation, preserve the selected original committed room title, and leave the original v4 checkpoint byte-identical across more than one save interval. Space must produce exact `你好` in the original editor, room title and private recovery file; original undo/redo and a focus excursion to another owned window must retain correct text. |

The clipboard stage is explicitly not IME evidence. During the IBus stage,
Chinese appears only in assertions; no Unicode input, clipboard insertion,
synthetic Makepad/egui IME event or direct workspace mutation is used. The
committed-draft oracle combines the original selected-room title and original
recovery file, rather than reading private UI memory. Root/Agentd signatures,
submission and device actions are outside this test.

`receipt.json`, `atspi-receipt.json` and `ibus-receipt.json` preserve failures.
Actual `XGetImage` captures include the owned native window and the complete
private display so candidate panels can be inspected. A script pass does not
set the font-pixel or candidate-position visual-review flags. A reviewer must
inspect the original pixels for glyph coverage, clipping and caret-relative
candidate placement. Virtual X11 input does not qualify physical keyboards,
Wayland input, mobile IME, or a human Orca listening/braille evaluation.

## Atomic EditableText and the remaining native paste boundary

Upstream AccessKit Unix 0.13.1 exposes Accessible, Action, Application,
Component, Text and Value interfaces. Its
[exact interface module](https://github.com/AccessKit/accesskit/blob/405d578cdfd8496ee79020d24cfaac8c29a8a48f/platforms/unix/src/atspi/interfaces/mod.rs)
has no EditableText implementation. Hepta retains that exact source in
`codex-rs/third_party/accesskit-0.17.1` and adds a reviewed compatibility patch on
the same original Unix adapter connection. All four crates must resolve from
the same fixed Hepta source; downstream Cargo roots must repeat the patch
entries because Cargo does not inherit them from dependencies.

The patched `SetTextContents`, `InsertText`, `DeleteText`, `CopyText` and
`CutText` methods create one `EditText` request with the complete observed text
and original text-run range identities. The original App rechecks its current
`RoomKey`, active widget, actual text, original draft, grapheme boundaries,
byte limit and IME state before invoking the original editor transaction.
Copy and cut use the original `Cx::copy_to_clipboard`. No other text model,
keyboard driver or owner is introduced.

`--atomic-editable-text` requires the additional real D-Bus test from the
matching Hepta checkout. It reads the actual original editor after every
accepted request, reads back the native clipboard, exercises original undo,
refuses partial UTF-8 prefixes and offsets within a composed grapheme, checks
size/range failures and tries a stale room object. The real IBus stage also
tries a cached semantic edit while preedit is active and verifies that neither
the raw editor buffer nor committed room/checkpoint changes. Adapter dispatch
booleans alone are not evidence of an applied edit.

On the baseline, `PasteText` returns `false` and does not mutate the editor. The
original Makepad public API exposes copying but no request-scoped asynchronous
clipboard read. Its X11 KeyV path creates an uncorrelated global text event.
Reading the `XlibApp` global during its existing callback would create an
invalid reentrant mutable reference. A complete native paste implementation
requires a bounded original SDK request/response API with target identity;
it must recheck room, text revision and IME state after the clipboard response.
Do not synthesize a key or route a delayed paste to whatever field is focused.

The independent `hepta-native-clipboard-sdk` candidate supplies that bounded
read through the original SDK and declares the separate native PasteText action
only on its current editable nodes. To qualify its actual binary, add
`--request-scoped-paste` to the command above and provide its candidate resource
bundle. The harness requires native clipboard readback, undo/redo, oversize
refusal and a real delayed clipboard response after a room change. This flag
does not enable the Cargo feature or build an SDK at runtime.

A successful five-method test keeps `full_editable_text_qualified: false` and
records paste as explicitly unavailable. Physical input, Wayland, precise text
character geometry, candidate positioning and a human Orca listening/braille
session still require their own real acceptance. Keyboard/clipboard or partial
EditableText success cannot substitute for those gates.

## Dependency notices in the installed bundle

The original `NATIVE-ASSETS.json` remains the fixed 29-asset/15-notice inventory.
`NATIVE-DEPENDENCIES.json` is a separate original Hepta manifest covering six
AccessKit dependency notice/provenance files under
`dependency-notices/accesskit/`: the Apache-2.0, MIT and Chromium licenses,
`HEPTA_UPSTREAM.json`, `HEPTA_PATCH.diff`, and `HEPTA_PATCH.md`. The upstream
manifest lists retained original file hashes and patched files; the diff makes
the source changes reviewable.

`prepare_native_makepad.py` verifies the actual four Cargo-resolved package
paths, versions and source equality with the original UI/core. It copies these
six real files and records their separate inventory hash in `bundle.json`.
The native Shell verifies that manifest against its compiled original constant
and verifies all six files before creating a window. The product installer
must retain and verify these additional entries as part of the resource bundle.
Reprepare the bundle when changing this patched dependency source; an older
font-only bundle is incomplete for the new native profile.
