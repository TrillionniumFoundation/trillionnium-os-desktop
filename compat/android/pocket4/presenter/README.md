# Pocket4 presenter timing repair

Status: **built, reviewed and subsequently activated in Main; fresh business acceptance remains pending**. Overall Pocket4 readiness remains **NO-GO**.

## Failure and repair

A real zero presentation timestamp caused the Android composer to reject a non-monotonic sample and exit. Android init then restarted SurfaceFlinger, zygote and system_server while the outer cell and init remained alive. The evidence is recorded in [the framework restart analysis](../evidence/framework-restart-20261104.json).

The repair validates timing at `DenialEndpoint::send_presented`, after task/frame identity checks. Zero and backward timestamps consume only optional presentation metadata and return an explicit suppressed outcome. They never become a `Presented` wire message, a fabricated timestamp, a buffer release or a fence update. Equal timestamps remain legal. Each task retains its last successfully forwarded timestamp; failed sends do not advance it, and task recreation resets it.

The Wayland callback removes its completed feedback entry before handling that outcome. Successful presentation tracing and audit run only for forwarded timing. Suppressed feedback is diagnosed at counts that are powers of two to bound log volume. Unknown task/frame identities and other protocol errors retain their strict behavior. The Android core's monotonic contract is unchanged.

## Exact source layers

The pinned upstream is `denialwm/droidloom` commit `75c5acf086f25fb8d2a31d159a57cdb4e75f85de`. The source series has two distinct layers:

1. `0001-inherited-public-preimage.patch` preserves **18 modified tracked files and 6 added public files** from the actual guard source snapshot. This includes preceding presenter/IPC guards and inherited supervisor, audio and build-tool work.
2. `0002-presentation-timing.patch` changes **4 files** for this repair: the endpoint, Wayland callback, architecture documentation and package release 20 → 21.

The recorded local candidate commit is `568f3cea524ec80d09ed42fdcff15f90b870120b`. That commit alone does not encode the entire inherited working tree. The complete two-layer patch series and the hashes of all **380 public files** define the source that was built. All changed final source files and the exact Cargo lock are included under `source/`.

A private historical provenance JSON is deliberately excluded. Its contents are not needed to reconstruct the public source manifest. The older live release's dedicated profile/source receipt was not recovered; a recorded unstripped artifact and its source pins do match the inherited snapshot, but are not pure-strip equivalents of the live release. This evidence limitation does not establish a source mismatch. The new candidate has a separate full source manifest and build receipt.

## Verify the complete source series

Provide a checkout of the exact upstream revision, then run:

```sh
python3 tools/verify_source_series.py --upstream /path/to/droidloom-upstream
```

The verifier creates a temporary source copy, applies both patches in order, checks every intermediate/final public file hash, and verifies the delivered final sources. It leaves the supplied checkout untouched. `source-lock.json` contains the three source layers, modes and patch hashes; `source-manifest.json` is the exact frozen public candidate manifest.

## Build and regression evidence

The real Unix sequenced-packet regression failed on the predecessor because zero timing reached the Android wire. The candidate passed **68 host checks**, with **one existing microbenchmark ignored**. Two existing Android composer presentation controls also passed. The eight new wire cases cover the observed zero sample and recovery, initial zero, regressions and equal samples, per-task clocks, destroy/recreate, unknown identity, failed sends, and retired tasks.

Those 70 checks cover the endpoint, IPC, Wayland and presentation contracts. They do not qualify every inherited supervisor, audio or source-builder change.

The release build used Rust 1.93.0, the exact Cargo lock, and:

```sh
cargo test --locked -j 1 -p droidloom-denial-endpoint -p droidloom-denial-ipc -p droidloom-wayland -- --test-threads=2
cargo build --release --locked -j 1 -p droidloom-wayland
```

The observed release binary is 7,026,568 bytes, SHA-256 `47f34d5f68783a372283cb63a42034d5899e270524cca40122bf28fd5e903f24`. Only source and deidentified evidence are published. The complete compiler installation and system link libraries are not archived, so an independent byte-identical rebuild is not claimed.

See [build-and-tests.json](evidence/build-and-tests.json) for the exact source, toolchain, test and artifact bindings. Runtime acceptance must install the candidate through the reviewed service boundary, preserve rollback to the actual previous release, capture a new framework epoch, and verify real app behavior from fresh observations.

## Licensing

DroidLoom's original code retains **GPL-3.0-or-later**. The original notice, full GPL text and third-party scope are included. Upstream Android and other third-party material keeps its own notices. This bundle stays under `compat/android/pocket4/presenter/`; it does not replace the Foundation repository's other runtime implementation.

## Later Main activation

Separate Main verification completed at 2026-11-04 08:55:13 UTC with the exact release hash and R16 engine. See [the activation summary](../evidence/main-activation-20261104.json). Earlier build/stage receipts retain their original time scope; activation is not application business acceptance.
