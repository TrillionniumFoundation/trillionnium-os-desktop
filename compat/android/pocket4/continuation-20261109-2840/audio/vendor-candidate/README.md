# Rust vendor Audio candidate staging

The existing updater now has `audio-apex-stage-candidate`, a Rust command that
copies one complete vendor Audio APEX from a frozen successful normal full-build
receipt. The command preserves the selected official QPR1 system by creating
only `payload/vendor/apex/com.android.hardware.audio.droidloom.apex` and its
`CANDIDATE.json` in a new private directory.

**Source and tool controls are verified. Actual full Audio APEX compilation,
APEX signing, compiled compatibility, VINTF, live audio and production readiness
remain separate pending qualifications.** Every candidate records these gates
as false. No real Audio candidate, image or installation was created by this work.

## Frozen implementation

| Item | Exact identity |
| --- | --- |
| Original recipe | `4caa694f25b3da022651a1078600a0eb1a5334fc` |
| Initial staging commit | `287595503314c610355bcce85a1ff148d0569ac9` |
| Final staging commit | `207cb626934534e0c4600312d1afa8552c835df1` |
| Final tree | `530a691fdf51fc0513b294c362632dca32b6eaa2` |
| Combined patch | `audio-vendor-candidate-rust-r2.patch`, 60,537 bytes, SHA256 `d0eaf319d488b8daaae33d813a6256b7896d6e9cefb8eca6c9f52f96ca767037` |
| Durability follow-up | `audio-vendor-candidate-durability.patch`, 3,120 bytes, SHA256 `f0d1a70b843a8549d37c1a556072f64de1be9c24c020617233bf401893b23d31` |
| Final normal updater | 34,076,528 bytes, SHA256 `208084afb0b16d7a0fe93a98e9131efb1b8d81a1a66bdebebb235831d0d19589` |
| Frozen executable | `desktop:/data/pocket4-audio-qpr1-vendor-candidate-20261109-2840-r1/tools-r2/droidloom-update` |

The complete seven changed files are under `source/`. The four original files
needed for patch application are under `preimage/`. Applying the combined patch
to those exact preimages was checked locally; every reconstructed file matched
the final recorded byte length and SHA256. `SOURCE_FROZEN-r2.json` records the
source, patch, tool and final validation bindings. The producer repository is an
isolated clone; the foreground owner's recipe, shared source and outputs were
not modified.

The command uses directory descriptors opened with `O_NOFOLLOW`, exclusive
relative creation, trusted parent checks, source and destination inode identity,
bounded reads, exact SHA256 comparison and byte readback. Both staged files are
synchronized after their final permissions are applied. New directories are
synchronized from `apex` through `vendor`, `payload` and the stage root, followed
by the existing parent. Directory and file identities are checked again before
successful return. A failed command can leave partial private files, including
a manifest; only a successful command exit permits consuming the candidate.

The ZIP inspector limits the container to 256 MiB, the central directory to
256 KiB, entries to 4–256, and each required metadata member to 64 KiB decoded.
It accepts stored and DEFLATE methods, rejects duplicate and noncanonical names,
checks local/central headers and member intervals, and requires complete exact
DEFLATE consumption. Metadata interpretation does not verify container signing,
payload AVB or the payload filesystem.

The updater adds the already existing workspace `flate2` dependency. No crate
version or checksum changed in the producer lock. The first offline attempt
found two missing cached packages; the exact official `flate2 1.1.9` and
`simd-adler32 0.3.9` archives were downloaded and verified against the existing
lock before the passing offline runs. The download receipt is retained in
`locked-crates-r1/RESULT.json`; crate archives and compiled binaries are excluded
from this source capsule.

## Normal updater validation

The final normal run was durable H job `1a1c1333f88-e62c-2a`, successful exit 0
at `2026-11-09T16:45:29.108Z`. Its original result is
`validation-r3/RESULT.json`, 8,514 bytes, SHA256
`da7b0a7c59cec09d438aa7bbb1fc14fd18d1619c89ce75fbdc5d7c0e46c587ff`.
Original H request, start and exit files are included. A subsequent read of its
service observed zero main PID, empty control group, `not-found`, `inactive` and
`dead` states.

The run executed:

```console
cargo test --locked --offline -j2 -p droidloom-update audio_vendor -- --test-threads=2
cargo build --locked --offline -j2 -p droidloom-update
droidloom-update audio-apex-stage-candidate --help
```

All 18 staging controls and three ZIP/protobuf/DEFLATE controls passed, with zero
failures or ignored controls. The normal executable then consumed the actual
latest SDK-source terminal, SHA256
`ca309c277d3bcc962abbaadb1054b334ff2d0eb603bb091a991f60f4896e04ec`,
and correctly rejected it as a source-only receipt with exit 1. The destination
was absent afterward. The test receipt cannot acquire full-build qualification.

The retained `validation-r1` result is the original missing-cache failure.
`validation-r2` passed before independent review found the directory persistence
gap. The final `validation-r3` passed after that narrow source correction.
These are distinct attempts with their original results preserved.

## Portable Linux CI

The capsule contains a self-contained Cargo harness:

```console
cargo test --locked --manifest-path harness/Cargo.toml -j2 -- --test-threads=2
```

The harness uses the exact three final source/test files. Its Rust `build.rs`
compares the copies to the corresponding files under `source/` byte for byte
before compilation, and registers both sides as Cargo build inputs. Its 38
registry packages retain the versions and checksums from the producer lock.

Durable H job `1a1c13d1477-e62c-40` passed this normal locked/offline command with
21 controls at `2026-11-09T16:56:11.248Z`.
`ci-harness-validation-r3/RESULT.json` is 10,045 bytes, SHA256
`0becea3581be096b2dc685ed6dba46281a9da068a9da182db15a30457078df9a`.
Original logs and H records are included. Earlier failed harness attempts are
retained: the first detected a dependency refresh before compilation; the
second exposed Rust's external-module test path resolution. The passing layout
uses normal module paths and the original dependency subgraph.

`controls/` contains the one-off execution/collection scripts that produced
these records. The supported packaging entry point is the Rust updater command.
The earlier Python staging prototype is not included as a second entry point.

## QPR1 compatibility scope

`audit/` contains the immutable read-only extraction result for the selected
official CP3A.260905.010 / 16176746 image, the component VINTF and stable NDK
findings, and the concrete CP2A system-output exclusions. The full image digest
was recomputed; the audit did not mount or modify the image or start Android.

The candidate route preserves official ART, runtime/bionic, framework,
Connectivity and global system libraries. Its Audio V4 declarations fit the
observed QPR1 component version ranges; complete device/framework VINTF matching
and actual compiled ELF closure are still required. The selected image reports
SPL 2026-09-05. This capsule provides no November security-coverage claim.

The latest source continuation contains 58 original SDK-file records totaling
720,358,562 bytes, including three added API36 public files at the unchanged
official SDK commit. The complete original result was separately downloaded and
hash-checked under `latest-source58/RESULT.json`. That readback rechecked the
receipt bytes and its 19 successful command records; it did not independently
reread all SDK data or acquire the shared build locks. The source success does
not establish a full APEX build or runtime success.
