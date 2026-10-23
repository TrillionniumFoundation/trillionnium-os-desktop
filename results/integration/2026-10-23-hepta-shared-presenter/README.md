# Original Hepta presenter candidate: source and execution archive

The 26-file source candidate is published as [Desktop draft PR #258](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/258),
source commit `0618dc8154e8b78cb91c5aa5558c597232d68023`, tree
`306a8f134adb59ebe1bfbb37b69a6ab329b276de`. Its base is PR #251 at
`64736996d310d597ffba513ee109264cd5f5f83f`. Root's independent
[full source readback](publication/root-source-readback.json) matches all 7,750
tree leaves and the 26 changed entries. This records source publication; it does
not record a successful remote Actions job.

Desktop now has a default-off candidate that directly depends on the original
`hepta-control-core` and `hepta-robrix-ui` packages at
`56630b12b8a4c69fff2c47b95b36d88a7389c39f`. The original model owns the active
draft. Desktop retains its existing Session, broker, local archive and context
observations. The renderer remains eframe/egui, and original `RequestSend`
still refuses with `SendUnavailable`. No Makepad rendering or production Send
qualification is inferred from the shared package dependency.

## Final executed gates

All Rust results below used the actual official Rust 1.88 toolchain, real Cargo
locks, one build job, debug information disabled and incremental compilation
disabled. [The execution summary](validation/final-execution-summary.json)
binds commands, exact source/lock snapshots, exit status and original raw streams.
The [source manifest](patches/review-manifest.json) separately records all 26
product paths, 12 exact Git preimages and the final bytes.

| Scope | Actual result |
| --- | --- |
| Original `hepta-control-core` | 64 passed: 42 library, 2 canonical differential, 20 controller tests |
| Original `hepta-robrix-ui` presenter-only package | 23 passed; Makepad/native-host features disabled |
| Desktop `trill-ui-core` | 42 passed: 36 library, 6 legacy observation tests |
| Three core packages together | **129 passed**, not 129 tests in Desktop core alone |
| Shared Shell, final source with explicit pinned font and `--include-ignored` | 87 passed, 0 failed/ignored/filtered |
| Final shared core + Shell invocation | 216 passed = 129 + 87; these overlap with the component rows |
| Default Shell, final source with the same explicit font and `--include-ignored` | 82 passed, 0 failed/ignored/filtered |
| Aligned original-base Session | 45 passed, 0 failed/ignored/filtered |
| Aligned original-base observer with `objective-history` | 51 passed, 0 failed/ignored/filtered |
| Default UI, shared UI and observer Clippy | All three actual `-D warnings` gates passed |
| UI rustfmt | Actual final check passed |
| Original Git provenance | Both packages and all 85 original package files passed the final actual checkout gate |
| Provenance guard tests | 10 passed |
| Strict wire-comparison tests | 8 passed normally and the same 8 passed under Python `-O` |

The earlier normal Shell invocations remain recorded as **81 default / 86 shared
passed, with 1 existing font test ignored in each**. Two separate explicit font
invocations passed **1/1 each**, with 81/86 unrelated tests filtered. The later
final-source full invocations explicitly supplied the same fixed font and used
`--include-ignored`; their 82/87 results do not rewrite those earlier receipts.

The font is the original Hepta manifest's exact public Noto SC Regular asset:
8,331,336 bytes, SHA256
`faa6c9df652116dde789d351359f3d7e5d2285a2b2a1f04a2d7244df706d5ea9`.
The [download receipt](validation/pinned-font-input-v1.json) retains its fixed
upstream URL and the original manifest/OFL/notice identities. The actual test
checked glyph coverage in both egui font families and rasterized Chinese glyph
outlines into nonzero ink. This is not a physical input-method, screen-reader,
Wayland-window or Makepad-runtime result. The public font bytes are retained
locally and reproducible from the fixed URL; the source commit does not bundle
that font asset into Desktop.

The Session/observer counts above refer to this candidate's #251 base and aligned
dependencies. They do not replace the separate #255 Objective adapter's later
64/52 results or qualify the new production owner composition.

## Compatibility fixes found by actual execution

The first feature-on 52-case comparison exposed two floating conversion changes
and one exponent spelling change. The candidate's field-level numeric Visitor
restores the old i64/u64-to-f32 dispatch and the old f64-to-f32 narrowing path.
Independent review also found that an intermediate `Option<f64>` fix would
double-round two large integer values; both cases were independently reproduced
as failing tests before the final Visitor made all six public-type cases pass.

The actual final wire outputs are identical between feature-off and feature-on.
Against the original source/lock output, **51 case values are byte-identical**.
The one remaining MAX-f32 observation changes only `3.4028235e38` to
`3.4028235e+38`. The gate requires the entire stdout to match that single exact
replacement and proves the finite decimal values equal. Both checked-in goldens
are verbatim actual Rust outputs. This is **not 52 byte-identical cases**, and it
does not prove equivalence for every possible decimal input or unknown external
consumer of raw resource JSON.

The final feature Clippy gate also caught `clone_on_copy` on the cursor state.
The patch removes only that unnecessary `clone()`; the undo history deep copy
and edit rollback semantics are retained. Final Rust formatting then adjusted
that expression's line wrap. The final Shell, core union and Clippy runs above
are bound to the resulting exact frozen bytes.

All initial comparison failures, the two stages of real red/green numeric tests,
the lint/format failures and the earlier resource-controlled stops are retained.
Historical core counts 123, 127 and 129 remain tied to their original source
identities. The 750 MiB task cache/target stop was not a compiler success or a
compiler defect. The later approved 1,250 MiB cap kept the separate global
minimums of 1.5 GiB memory available and 512 MiB free shared storage.

## Patch and composition boundaries

Apply [01-dependency-alignment.patch](patches/01-dependency-alignment.patch), then
[02-presenter-candidate.patch](patches/02-presenter-candidate.patch), against the
exact recorded base. The builder actually checked and applied both in order and
compared every resulting byte. The six dependency files and 01 patch are
unchanged from their original freeze; 01 SHA256 is
`59c0dc32e321f94cb8f6a2593ff7931cf8cf0b75be8f471f251254512121d215`.

The final freeze has **26 source files**. Older 21-file manifests and earlier
planning documents are retained as historical evidence. Preserve #247's README
guard migration and #255's later Objective source and workflow gates when
composing the branches; this candidate adds its own explicit feature gates.
Do not replace newer Session files with the old validation workspace snapshot.

The Makepad [composition design](research/makepad-integration/COMPOSITION_DESIGN.md)
and [original-source review](research/makepad-integration/review-v2.json) are
separate research artifacts. They are not part of the 26 implemented files.
The next slice must extend the original App and its one ImeRouter, preserve the
existing Desktop Session/Bridge/draft ownership and solve cross-workspace
RoomKey/late-event isolation before claiming full three-workspace support.

This archive does not qualify a fresh remote Actions run, Weston window,
physical IME, accessibility backend, mobile/Web deployment, bare-metal runtime
or production chat authority. The original unavailable-Send behavior remains.

## Reproducibility and resource handoff

[The final target release receipt](validation/target-release-final.json) records
all 3,312 build-target entries before deleting only the task's reproducible
target. It preserves per-file identities, 1,049,522,157 regular file bytes and the
actual shared-storage free-space change. Source, fixed Git packages, Cargo
cache, font/license inputs, official Rust 1.88 and all raw receipts were retained.
No subsequent Rust execution is implied by creation of this archive.

## Complete raw archive

[raw-evidence.tar.gz](raw-evidence.tar.gz) retains all 269 frozen evidence members,
9,454,247 uncompressed bytes, including every original stdout/stderr, failed
attempt, preimage and provenance record listed in [manifest.json](manifest.json).
The linked documents above are also provided directly for review. All members
were checked against their original bytes and the archive was rebuilt twice
with identical bytes; no evidence was shortened. Font binaries and reproducible
build outputs are excluded exactly as described above.
