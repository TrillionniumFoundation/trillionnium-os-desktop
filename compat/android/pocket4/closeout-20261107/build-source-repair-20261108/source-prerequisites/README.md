# Pocket4 build source prerequisites

Status: **source reconstruction verified; final audio repair pending; no deployment qualification**.

This review package makes the local Droidloom builder inputs reconstructable without relying on unpublished Git objects. It contains a common text source snapshot and two separate prerequisite patches. The native and audio branches are alternatives: start each one from an empty directory and apply the common snapshot once.

## Source identity and availability

The common snapshot was read from the locally observed commit `500dd3af851aaadb95537b68129b8bd889504951`, tree `4fa612edf0cd393384ede74874dd28274f77cde8`. The source metadata names `https://github.com/denialwm/droidloom` as its upstream. A GitHub repository/object query on 2026-11-08 confirmed that repository is public but did not return the `500dd3` object. Accordingly, the package provides the exact source bytes; it does not require a reader to fetch that local commit.

`base-source.patch` creates 385 UTF-8 text files, totaling 3,603,664 source bytes. It retains the complete Cargo workspace manifests and source folders, `Cargo.lock`, `rust-toolchain.toml`, `LICENSE`, `LICENSES/`, `THIRD_PARTY.md`, packaging inputs, and documentation used by source `include_str!` references. The per-file SHA-256, byte count, and Git executable mode are recorded in `base-source-files.json`.

This is a declared build-source subset, not a full upstream Git checkout. The original base has 390 files. The five excluded paths are:

| Excluded path | Reason |
| --- | --- |
| `AGENTS.md` | Operator and device instructions; no build input |
| `m831-provenance.json` | Private machine provenance; no build input |
| `assets/screenshots/whatsapp.png` | Documentation screenshot; the only binary source-tree asset |
| `.github/FUNDING.yml` | Repository hosting metadata |
| `.github/workflows/ship.yml` | Repository CI configuration |

The native filesystem snapshot originally counted 508 files. Exactly 59 are Git metadata under `.git/`; the other 449 are the complete tracked-plus-untracked source inventory. There are no additional ignored build inputs in that snapshot. Applying the same five exclusions leaves 444 native prerequisite source files. The final native candidate also had one observed zero-byte transient editor lock; its path is explicitly recorded as an additional nonbuild exclusion in `source-manifest.json`. No active lock was removed or modified.

## Patch chains

| Patch | Meaning | Files changed | Bytes | SHA-256 |
| --- | --- | ---: | ---: | --- |
| `base-source.patch` | Empty directory to common text source snapshot | 385 added | 3,814,733 | `40ad41624358deb27ce67ea61d557e5ae5f672c19e2b0e805679caa71cf0c2aa` |
| `native-prerequisite.patch` | Common snapshot to the actual frozen native builder inputs | 6 modified, 59 added | 1,521,824 | `dc982097ea61682c6e586f3c6fc6e853ec4a10b5cb33ed6b8f1350e39624371a` |
| `../native-sparse-capacity/source.patch` | Frozen native builder to the capacity and frozen-recipe candidate | 1 modified, 2 added | 44,658 | `290eb43af731f9753759898d58bd648f44d2aea48ee08f64df7c0daf15da1a16` |
| `audio-prerequisite.patch` | Common snapshot to audio builder commit `fc90abf09eb0f09cc5f46bead149b4d324882722` | 11 modified, 10 added | 463,169 | `af0e4e87db09b39407fb6689cff451fe7dbe3a6a91f3661148f38c76e1fe10d0` |

The native prerequisite includes the existing native-generation pair/ART inputs, source locks, original provider fixtures, and builder changes. It does not import the unrelated later host status changes. Its base `tools/droidloom-source/src/lib.rs` hash is `8c3acbf900ff49888ecd37533df195758916601daffb044d5871fed052ba5d3a`; the final capacity repair produces `a91cefb336b535b38196d03c2fc05752c32b42629db3f0a16a95826e40739627`.

The audio prerequisite is a cumulative diff across the real local lineage `500dd3` → `17ca3fa` → `5957add` → `fc90abf`. It includes the prior host status/readiness changes, supervisor development changes, real PCM input patch, audio source lock, resource-budget patches, original resource fixtures, and audio builder changes. Its final local commit is `fc90abf09eb0f09cc5f46bead149b4d324882722`, tree `1f28d43707ff707affde982e2e8b505dd728ebc0`. Because this prerequisite is cumulative, do not additionally apply the older public `500dd3` → `17ca3fa` host patch to the same reconstruction.

The final audio provider repair is still being tested and is deliberately absent from this frozen prerequisite chain. Earlier intermediate audio results must not be treated as results for a later modified candidate.

The complete changed-path lists, including each preimage and postimage hash, are in `native-changed-files.json`, `audio-changed-files.json`, and `../native-sparse-capacity/changed-files.json`.

## Reconstruction

Run the following from this package directory. Each `mktemp` call creates a new directory and does not touch an existing checkout.

```sh
package_dir="$PWD"
native_dir="$(mktemp -d)"
git -C "$native_dir" init -q
git -C "$native_dir" -c core.autocrlf=false apply --index "$package_dir/base-source.patch"
git -C "$native_dir" -c core.autocrlf=false apply --index "$package_dir/native-prerequisite.patch"
git -C "$native_dir" -c core.autocrlf=false apply --index "$package_dir/../native-sparse-capacity/source.patch"

audio_dir="$(mktemp -d)"
git -C "$audio_dir" init -q
git -C "$audio_dir" -c core.autocrlf=false apply --index "$package_dir/base-source.patch"
git -C "$audio_dir" -c core.autocrlf=false apply --index "$package_dir/audio-prerequisite.patch"
```

The file inventories are exact maps of relative path to byte count, SHA-256, and executable mode. No Git commit is invented for the reconstructed directories. The manifest's `selected_subset_tree` and `target_subset_tree` values identify the real Git trees derived from those retained files; they are explicitly distinct from the original complete source trees.

## What was verified

The patches were applied in new isolated directories on Pocket4, then transferred without source modification and replayed independently on Mac. Both runs verified every retained file's bytes and executable mode:

| Reconstruction point | Exact matched source files |
| --- | ---: |
| Common snapshot | 385 |
| Native prerequisite | 444 |
| Native capacity and frozen-recipe candidate | 446 |
| Audio `fc90abf` prerequisite | 395 |

The native final reconstruction matches the actual candidate used by the native agent. The audio prerequisite reconstruction matches immutable `fc90abf` Git objects, not the still-changing audio repair working tree. `../manifest.json` binds the supplied patch and manifest bytes. `mac-replay-verification.json` records the independent second replay.

These checks prove source reconstruction. Separate focused Rust tests and normal builder compilation results belong to the repair result summaries. AOSP source projects must still be obtained at the revisions specified by the applicable source lock, and Rust registry dependencies must be resolved with `Cargo.lock` and the declared toolchain. This package does not include all AOSP source or cached Cargo crates, and it does not claim a complete native/ART build, complete audio APEX build, installation, runtime qualification, or whole-application acceptance.
