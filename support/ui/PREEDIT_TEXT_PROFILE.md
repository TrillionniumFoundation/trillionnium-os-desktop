# Explicit callback-preedit Linux text product

`linux-preedit-profile.json` selects
`trill-shell/hepta-native-preedit-sdk`, the reviewed prepared SDK, and a
61-file resource bundle. The baseline profile retains its original Git SDK
and 54 files. The clipboard candidate retains its own feature, source tree,
patches and notices. The two candidate Cargo features are mutually exclusive.
The preedit-only product does not advertise PasteText.

The original Hepta input owner, ImeRouter, TextInput, ChatWorkspace, Agentd
and writer paths remain in their pinned original source. The SDK patch makes
the existing XIM callbacks the preferred input-context style and retains that
context when optional callback spot forwarding is unsupported. It also makes
window focus gain/loss conditional on real state transitions: a redundant X11
visibility notification cannot restore an old caret or cancel live preedit,
and repeated loss cannot overwrite the saved editor. Actual SDK Window and
drawn TextInput regressions cover duplicate gain/loss, true loss/return and
other-window isolation. The explicit candidate also treats desktop IME
composition as one transaction: previews never enter undo/redo history or
committed checkpoints; a commit records one net edit; cancellation restores
the original selected text and selection. Legal edits beside composition use
committed UTF-8 coordinates without consuming adjacent combining characters.
The original drawn TextInput event regressions cover commit/cancel, ordinary
typing, consecutive compositions, selection direction, boundary edits and
checkpoint restoration. A positioning warning never grants composition or
execution authority.

## Frozen inputs and the integrated companion

The profile freezes the executing Hepta commit/tree and preparation-helper
commit/tree plus both helper scripts' SHA256. Execution and preparation must
use that same integrated original Hepta companion. The helper permits only
the four reviewed Window/TextInput source/test files in this preedit profile;
arbitrary widget changes and clipboard-profile widget changes remain refused. The
complete SDK tree, exact patch/manifest bytes and helper scripts are checked
independently. Changing the companion requires updating both profile
identities and every existing Hepta
dependency pin and lock together. The builder checks all Hepta sources in the
actual UI graph and all five committed product lockfiles against that single
execution pin.
Original-owner ancestry and Notes protocol goldens remain mandatory through
the existing release source verifier.

`preedit-sdk/` retains byte-identical copies of the canonical Hepta candidate
patch, graph-path patch, manifest, provenance note and MIT license. Its separate
`NATIVE-SDK-PATCH.json` is compiled into the explicit Desktop feature. Startup
checks that exact contract, every notice's bytes, the prepared tree and SDK
profile; a baseline or clipboard bundle cannot satisfy it. The 61 files are
the original 54 plus five SDK notices and two SDK notice/source manifests.

## Prepare an isolated source/lock combination

Use a new Desktop worktree/branch and an external output directory. Keep the
baseline Git lock on its normal branch; the prepared path-SDK lock belongs
only to this explicit candidate. The same exact feature must be used for
original metadata, candidate resolution, tests and binaries.

```sh
cargo +1.96.0 metadata --manifest-path /absolute/candidate/ui/Cargo.toml \
  --format-version 1 --locked --offline \
  --features trill-shell/hepta-native-preedit-sdk \
  > /absolute/evidence/original-native-metadata.json

python3 -B /absolute/frozen-helper/apps/hepta-control-ui/test/prepare-native-clipboard-sdk.py \
  --profile preedit-callbacks --upstream-repo /absolute/existing/makepad-git \
  --destination /absolute/new/prepared-makepad \
  --metadata /absolute/evidence/original-native-metadata.json \
  --cargo-config-output /absolute/evidence/preedit-overrides.toml

cargo +1.96.0 --config /absolute/evidence/preedit-overrides.toml metadata \
  --manifest-path /absolute/candidate/ui/Cargo.toml --format-version 1 --offline \
  --features trill-shell/hepta-native-preedit-sdk \
  > /absolute/evidence/candidate-native-metadata.json
```

Review and commit the candidate's `ui/Cargo.lock`. No source file, global Cargo
configuration or cached SDK checkout may be edited as part of resolution.
The helper prepares a new full SDK checkout, verifies the complete patched
Git tree and generates an override for every original resolved SDK crate.
Partial overrides, another SDK tree, or an old clipboard profile are refused.

## Build and retain source evidence

```sh
python3 -B support/ui/build_text_product.py --profile preedit-callbacks \
  --desktop-commit FULL_CANDIDATE_COMMIT --desktop-tree FULL_CANDIDATE_TREE \
  --hepta-repo /absolute/original-execution-hepta \
  --hepta-commit FROZEN_HEPTA_COMMIT --hepta-tree FROZEN_HEPTA_TREE \
  --sdk-helper-repo /absolute/frozen-helper \
  --sdk-original-metadata /absolute/evidence/original-native-metadata.json \
  --sdk-cargo-config /absolute/evidence/preedit-overrides.toml \
  --output /absolute/new-preedit-build --jobs 2 --offline \
  --asset-cache /absolute/verified-original-assets \
  --liberation-source /absolute/verified-liberation-source.tar.gz
```

`--sdk-helper-repo` can be omitted when preparation and execution use that
same frozen checkout. An explicit helper path must identify the same reviewed
commit/tree. Changing the frozen identity requires new complete
source/build/runtime evidence, not just a changed command argument.

The builder retains the original metadata and exact Cargo config, generates
a fresh SDK receipt from its actual build metadata, and re-verifies the full
prepared tree, SDK features/dependency edges, config and metadata after the
build. The all-SDK override applies to the shipping UI workspace and its
workspace tests. Existing observer/support/text-host contract tests retain
their own committed locks and original source graphs; all still use the one
frozen Hepta execution revision. No unused SDK patch is inserted into those
unrelated workspace locks.

The pure original `source-profile.json` and its verification receipt remain
unchanged in meaning. `package-source-profile.json` adds the separately
verified `makepad_sdk` record for packaging, and is copied into the package's
source-profile slot. Its hash is in the build receipt. The host archive also
binds the exact SDK receipt hash. The receipt distinguishes raw Cargo ELFs
from the actual stripped package ELFs and records all 61 resource hashes.
Build success leaves `window_qualified` and production authority false.

## Required actual packaged-window gate

Extract the resulting package into a new isolated directory. Run the existing
owned X11/IBus/AT-SPI harness against that exact distribution ELF and resources:

```sh
python3 -B tests/ui/native-makepad/qualify.py \
  --shell /absolute/extracted/trillionnium-desktop/bin/trill-shell \
  --resources /absolute/extracted/trillionnium-desktop/resources \
  --hepta-source /absolute/original-execution-hepta \
  --build-receipt /absolute/new-preedit-build/build-receipt.json \
  --packaged-binary --atomic-editable-text \
  --output /absolute/new-preedit-window-evidence
```

The preedit resource profile automatically requires the corresponding build
receipt, all 61 exact resource hashes, the packaged ELF binding and atomic
EditableText checks. The actual XRes-verified editor XID must select callback
XIM before and after the unchanged real IBus tests. A Position/Nothing fallback,
another window's callback log, or a later downgrade fails this gate. No log
message substitutes for preedit action fencing, committed Chinese text,
original draft recovery, original AT-SPI tests or owned-process cleanup.

Only completion of that complete workflow sets `preedit_profile_qualified`.
Candidate-window positioning and font pixels still require the existing
visual review. Physical keyboard/display, Wayland, Orca human evaluation and
authenticated original Root operations retain their separate acceptance gates.
