# DroidLoom supervisor and resident catalog source

This directory contains an independent DroidLoom source workspace for the Pocket4 supervisor and catalog repair. The `source/` subtree has **211 public files (2,928,304 bytes)**, with the original **28 Cargo workspace members and Cargo.lock preserved byte for byte**. It contains the selected host implementation, the independent Android catalog service, and the observed compile-time inputs required by the retained Rust sources.

The source tree is `1da35714e1e64b9622b784f8f4aec37d57eceffb`. Every file matches the fixed unified source manifest. Assembly checked all 48 literal Rust include calls and their 44 targets, nine explicit Rust module-path attributes, and 31 local Cargo dependency edges. The original 210-file assembly correctly rejected a newly discovered 240-byte lock-file dependency; the 211-file successor includes it. These are source-content checks, not a new whole-workspace build.

## Behavior changed

| Entry point | Resulting behavior |
| --- | --- |
| Status / CLI status | Reports cell lifecycle without a fresh Android readiness probe or a daemon child process. |
| Explicit Readiness | Performs the original fresh readiness checks under a distinct request. |
| Start / Restart with waiting, WaitReady and Launch | Retain their original readiness and failure gates. |
| ListApplications / ApplicationIcon | Use the held-current-cell pathname socket. The resident service reads fresh package/configuration data for each request; it has no host child-process fallback. |
| Independent catalog service | Uses bounded frames and output construction, closes received ancillary descriptors, admits one query at a time, and rejects terminal-state admissions. The self-signal target is restricted to its own positive PID. |

The Android service lives in its own `android/framework/droidloom-catalog/` directory. The existing InputBridge/TaskObserver JARs are not rebuilt by this path. Host peer validation retains the current init identity, held root and named directory edges. No Main guard has been weakened.

## What was actually validated

| Evidence | Actual scope and result |
| --- | --- |
| Host47, job `1a1b3abc798-fc05-8439` | 47 commands, 22 focused Rust/CLI cases, 18 pure Java protocol cases and three real owned-child lifecycle checks passed. The selected dependency union was five local crates and 45 registry crates. Four release host ELF files were produced. |
| SDK03, job `1a1b3dfea1f-fc05-8544` | Five commands, 30 Java cases (18 protocol + 12 lifetime), three owned-child checks and three DEX-structure checks passed. All 11 production Java sources compiled against the actual SDK31 public bootclasspath, then D8 produced the catalog JAR. |
| Source association | All 40 selected host/workspace files match Host47, and all 14 independent catalog inputs match SDK03. The corrected association binds the current unified manifest SHA-256 `9ff887e3edd168647ebe8c11c4ae904a5fc7e404aef8c67266d82355c21591f8`. |

The SDK03 JAR is 38,688 bytes, SHA-256 `a0e1152e1dbfb142a6f6a82f6f89f19de99fd783c5833f22ca0d3a03617505db`. Its single DEX contains 37 class definitions. Production javac used source/target 8 and class major 52; the pure host tests used `--release 17` and major 61. D8 used minimum API 31. Successful SDK compilation does not establish Android reflection, ART, init-service, self-signal or package-manager runtime behavior.

The whole 28-member workspace, its integration suites and its package/image builders have **not** been qualified by these two runs. No candidate Android service or Main deployment has run. **Whole-App readiness remains 0/45.** The earlier Main epoch is no longer a current runtime qualification. These build results do not establish the installed binaries' source provenance or attribute an earlier launch failure to this source.

Full immutable references, exact test names, artifact association and resource observations are in [build evidence](verification/build-evidence.json). Host47 reached its 1 GiB limit with 608 memory-limit events, no OOM/kill and zero observed swap; its swap limit was `max`. SDK03 peaked at 570,343,424 bytes with zero memory-event deltas and zero observed swap, also with swap limit `max`. These results do not assert that swap was disabled.

## Reproduce only the selected build

Use a fresh isolated attempt and the exact observed tools and inputs recorded in [validated commands](verification/validated-commands.json). The original admitted attempt directories and request keys are historical receipts and must not be replayed. The archived controllers retain input revalidation, empty output-directory checks, output limits, resource checks and the owned-child reaper.

The validated Rust toolchain is the explicit `1.93.0-x86_64-unknown-linux-gnu` installation. The selected compiler invocations were:

```text
cargo build --release --offline --locked -j 1 -p droidloom-supervisor -p droidloom-applications --bins --message-format=json-render-diagnostics
cargo test --release --offline --locked -j 1 -p droidloom-supervisor --lib --no-run --message-format=json-render-diagnostics
cargo test --release --offline --locked -j 1 -p droidloom-supervisor --test cli_lifecycle --no-run --message-format=json-render-diagnostics
```

Here `cargo` denotes the exact absolute executable in the command reference, together with its recorded sysroot, linker, environment and offline registry inputs. After compilation, the original controller runs the 15 named library tests and seven named CLI tests separately. A blanket `cargo test --workspace` is not the validated selection.

The Java route uses the observed complete JDK tree (511 members, 353,859,697 physical bytes), the SDK31 `android.jar` and the pinned R8 JAR. Production compilation uses `-source 8 -target 8 -bootclasspath <the fixed SDK31 android.jar>` with empty classpath/sourcepath directories; it does not use JDK `java.base` as Android API evidence. The exact five argv vectors, input hashes and output expectations are in the command reference. Retain the 30 real Java method tests and D8 checks when staging a fresh reproduction. No new build was run merely to assemble this Git subtree.

## Remaining inputs and runtime gates

[Runtime dependencies](verification/runtime-dependencies.json) lists concrete source-derived requirements. Other Cargo members need their own registry/native-library closure. For example, the dmabuf probe requires EGL/GLESv2, repository integration tests read Android contracts and `packaging/tests`, and update tests require SurfaceFlinger patch/C++ inputs or a pinned minigbm checkout. Those assets are not all present in this focused public source drop.

The original `install.sh` and `docs/BUILDING.md` are retained as source/reference inputs. Their upstream installer and package-publication workflow is not the Pocket4 reproduction route described here.

Future runtime work still needs a fresh complete Main/cell baseline, the real persistent guest mapping and init import, an owned Android API/protocol smoke test, and a reviewed deployment/rollback transaction. The existing presenter is a separate live object; it must not be replaced with the `droidloom-supervisor` namespace-entry tool. Existing limits, drop-ins, camera, compatibility library and bridge path states require explicit preservation.

The 366-byte catalog rc in `source/` is the SDK03 input. Deployment-only rc/import derivations are separate; this file does not authorize overwriting the installed 972-byte bridge rc. Historical failures, old unknown launch outcomes and retired nonces remain unchanged. Publication of this source directory does not publish, install or start the candidate.
