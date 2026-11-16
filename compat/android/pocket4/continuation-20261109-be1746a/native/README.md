# Native Tradefed source and ordinary tool qualification

## Result

The exact five-cone Tradefed source patch passed 16 native-pair tests and 26 source-library tests on ai395 using the repository-pinned Rust 1.93.0. The ordinary dev-profile `droidloom-source` and `droidloom-update` binaries were built successfully and their normal help commands passed. The new `droidloom-source verify-lock` also verified 600 exact AOSP projects and eight root links.

The isolated source commit is `ff910cc50d842b5308b860340295bda44c28cf5a`, with tree `95b5934af46dc560be0559d0b5b9edccc6133867`, based on `fb55abd62b661b4c028f5a8fdf213f29b4f1ad8b`. The original recipe remained at that baseline with a clean worktree. This helper did not reconcile or mutate the shared AOSP tree, start an Android full build, change CURRENT, or qualify an Android runtime.

## Why the patch is needed

The retained native600 full build r7 failed because normal Soong could not resolve `vts-tradefed`, `cts-tradefed-tests`, `cts-v-host-tradefed-tests`, and `chdts-tradefed-tests`. The official `compatibility_test_suite_package` mutator adds Tradefed test dependencies implicitly. The patch retains complete original recursive cones for CTS Tradefed, CTS-V host, CHDTS, VTS-core Tradefed, and Deqp CTS. It also updates exact lock hashes and regression tests that reconstruct the original failed lock. It adds no stub provider and does not disable Soong dependency validation.

## Evidence entry points

- `HANDOFF.json`: source identities, binary hashes, test counts, resource results, failure history and explicit acceptance limits.
- `native-tradefed-source.patch`: the exact two-file patch, SHA256 `3b1b498bd1b2f12623960efe6a9153e943fe17806b397f3dfa9ecdb00e4d4bed`.
- `r2/QUALIFICATION-r2.json`: original successful qualification receipt with command argv, return codes, log hashes, process retirement, and original recipe verification.
- `r2/qualification-r2/`: original native tests, source tests, tool build and help outputs.
- `SETUP.json`, `qualification-r1.json`, `complete-logs/`: setup and the preserved first attempt, plus all remaining command logs.
- `jobs/`: authoritative H terminal observations and the normal CLI lock verification result.
- `setup_execution.py`, `normal_qualification_r1.py`, `normal_qualification_r2.py`: exact submitted orchestration bodies, retained as execution provenance. These create-only one-shot scripts must not be replayed in existing output directories.
- `EVIDENCE-MANIFEST.json`, `SHA256SUMS`: transport inventory; every copied remote file was matched to its reported byte count and full SHA256.

## Actual commands and outcomes

The original argv arrays and executable paths are in the receipts. The substantive commands were:

```text
cargo test --locked -j 1 -p droidloom-update native_generation_pair_build::tests -- --test-threads=1
cargo test --locked --offline -j 1 -p droidloom-source --lib -- --test-threads=1
cargo build --locked --offline -j 1 -p droidloom-update -p droidloom-source
droidloom-source verify-lock --lock <isolated-source>/android/native-generation-pair/source-lock.json
```

The successful qualification job is `1a1bf6dcd4e-5e21-511`, succeeded with exit 0 and complete durable output. The lock verification job is `1a1bf70fd8a-5e21-522`, also succeeded with exit 0. Every command child was reaped and its process group was absent at completion. CPU affinity was 10/11, CPU quota 200%, memory cap 4 GiB, measured memory peak 822362112 bytes, no OOM events and zero swap.

The first test attempt failed before compiling proc-macro2 because public `/tmp` was full. Its original cargo exit 101, H exit 1, receipt and log remain preserved. The successor bound TMPDIR/TMP/TEMP to the helper's own `tmp-r2`; it used the same source hashes and toolchain. Public `/tmp` was not cleaned or modified by this repair.

## Consumption and remaining work

Qualified binaries remain in the isolated ai395 helper root recorded by HANDOFF.json; binary payloads are deliberately excluded from this source/evidence capsule. The same Rust1.93 toolchain may be used read-only by the parallel Audio qualification.

The current owner must still adopt the exact commit/tools, perform ordinary source reconcile and materialized verification, execute a freshly bound serialized normal full build, and qualify the final QPR1 runtime and applications. No source-materialization, full-build, runtime or production acceptance is transferred from this host-tool result.
