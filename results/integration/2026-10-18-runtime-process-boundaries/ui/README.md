# R9 Runtime total-age correction — source-bound Rust evidence

The final Runtime freshness implementation passed **137 Rust tests**, with
**two real-host-font tests ignored**, strict all-target Clippy, formatting,
and the locked build of all four production UI executables. The failure
baseline and intermediate compile/lint failures remain in this archive.

## Proven defect and correction

The deterministic negative test sends a Snapshot through the actual Desktop
response queue and renders the actual egui status. The successful runtime
sample has Session age **6,000 ms**, IPC round trip **20 ms**, and response
queue delay **1,991 ms**: its conservative monotonic total is **8,011 ms**.
Wall-clock rollback makes the same sample appear only 6,000 ms old. RED
actually rendered `Hepta: OBSERVED · READ ONLY`. The exact 7,000 ms control
passed in the same RED command; the regression failed. This proves the
visible predicate accepted an old sample, without a compositor or Agentd
execution claim.

Session now times the complete successful runtime read from its start and
publishes a separate nonzero successful-read sequence and upward-rounded age.
Failed reads and independent known-run reads do not renew that sample. Shell
binds it to Session, AgentId, spawn and PID, then combines the source age,
full IPC round trip and post-receipt queue age. Same-source repeated samples
retain the maximum advancing bound, without rejuvenation or repeated RTT
addition. A same-Session frame missing history cannot erase that bound.
Invalid or absent ages fail closed. The visible and runtime-layout predicates
share the same clock, while the run projection remains independently sampled.

Strict Clippy exposed an enlarged Response variant after adding the inline
optional clock. The final implementation boxes only that optional metadata;
its JSON object and timing semantics are unchanged. No lint was suppressed.
New Runtime snapshots add clock metadata even without a known run: deploy
matching Session, Shell and ctl versions. New Shell treats old missing-clock
history as unknown; old strict decoders reject the new field.

## Executed source identity

The initial RED command executed at HEAD
`777196f826f45183f43a6c74c630f70df4adf4cc` plus its retained four-file source
patch. The parent subsequently committed that exact RED scaffold/tests as
`00796f6f6e10027e12b83d37d9ab4b8ab913f72e`. This later commit was not the
HEAD recorded by the execution. Each attempt retains its original HEAD,
patch, per-file SHA-256, command, compiler identity and raw-log hash.

Final test-03, fmt-02, clippy-02 and build-01 all executed at HEAD
`09cf259676e2a81a998c14f1e1fddf4cc94b80df` plus the final working source, with identical
before/after source inventories. This is a candidate based on main f9e306f,
not a claim that 09cf was main. Their complete UI and observer source closure
SHA-256 is `d720db71872f8c263b73ab3b5ad9702a856898a32b7cfde312cfe805156d0fe0`.
`final-source.json` separately binds the eight changed implementation/test/
documentation paths. A later integration or publication commit must keep its
own identity; these executions are not relabeled as that later HEAD.

The closure includes tracked UI sources/manifests/lock, the Session's
`services/hepta-os/src` path dependency and its two manifests, and the UDS
fixture JSON. Four original source-file snapshots from each attempt are
stored by content hash, with all original paths in `archive-manifest.json`.
The exact patches preserve the remaining changes against each recorded HEAD.

## Actual attempts

| Attempt | Actual outcome |
| --- | --- |
| red-01 | Exit 101; 1 passed / 1 failed. Actual false-fresh status at total age 8,011 ms. |
| green-01 | Exit 0; 3 matching focused tests passed, including the added independent-run case. |
| test-01 | Exit 101 before workspace tests: an existing core test fixture needed the newly optional field in its Rust struct literal. |
| test-02 | Exit 0; 137 passed / 2 ignored on the initial unboxed implementation. |
| fmt-01 | Exit 0 on the initial implementation. |
| clippy-01 | Exit 101: `large_enum_variant`; no suppression or widened public Response representation. |
| test-03 | Exit 0; 137 passed / 2 ignored on the final boxed implementation. |
| fmt-02 | Exit 0 on the same final source. |
| clippy-02 | Exit 0 with `--workspace --all-targets -- -D warnings` on the same final source. |
| build-01 | Exit 0; all four production bins on the same final source. |

All attempts have `source_equal: true`. A compile error is not reported as a
failed behavioral test, and the initial GREEN results are not substituted for
the final boxed-source results.

## Final counts, read from test-03

| Actual test binary | Passed | Ignored |
| --- | ---: | ---: |
| trill-app-window unit | 11 | 1 |
| trill-ctl unit | 2 | 0 |
| trill-session unit | 30 | 0 |
| hepta_observer integration | 2 | 0 |
| hepta_run integration | 4 | 0 |
| ipc_reconnect integration | 1 | 0 |
| trill-shell unit | 63 | 1 |
| trill-ui-core unit | 24 | 0 |
| trill-ui-core doc-tests | 0 | 0 |
| **Total** | **137** | **2** |

The two ignored cases require `TRILL_UI_TEST_CJK_FONT` selecting a real host
font; this R9 gate did not run them. The real Session executable with scripted
fixed-v2 UDS responses verifies the complete slow runtime read, independent
slow known-run read, null/missing-run semantics, old-spawn failure and two
later failed polls preserving the runtime sequence while its age advances.
Desktop/egui regressions also cover 7,000/7,001 boundaries, invalid ages,
rollback, Session/source changes, missing-history middle frames, sequence
regression and visible/layout agreement.

## Four production outputs

| Executable | Bytes | SHA-256 |
| --- | ---: | --- |
| `trill-app-window` | 22,607,968 | `298b5d8eeaa60a9100071ca3ca6df0a4a1fbbe85c18e42b57d8bd687a559b0b8` |
| `trill-ctl` | 1,620,672 | `3a105e321347856d874c489b392faa547be53b1b20f48183efe53d30bc916dbb` |
| `trill-session` | 3,665,376 | `d13e823066a99cb1c5a15b4b4c9b0a80921295cd42d99bbb69cb4b8370e05710` |
| `trill-shell` | 24,552,760 | `7f95235df1a1141a5b7e2ac597c2155a9f3ec844f07997d4fbf11f308ec8d7ef` |

`attempts/build-01/production-binaries.json` records actual paths, ELF64
little-endian x86-64 headers, hashes, build-launch binding and source before/
after. `receipt.json.shell_executables` is the runner's inventory and may also
include the test executable; it is not a four-bin list. The actual final
Shell test ELF is separately identified by
`attempts/test-03/preserved-test-elf.json`. ELF bodies and Cargo caches are
excluded from this archive; RED, initial GREEN and final test ELF copies were
retained only in the original local attempt directories.

## Exact commands and environment

All commands ran from the repository root with the fixed private Rust 1.88
installation. `launch.json` contains the absolute Cargo path and tool hashes.

```sh
cargo test --manifest-path ui/Cargo.toml --locked -p trill-shell runtime_total_age_ -- --nocapture
cargo test --manifest-path ui/Cargo.toml --locked --workspace
cargo fmt --manifest-path ui/Cargo.toml --all -- --check
cargo clippy --manifest-path ui/Cargo.toml --locked --workspace --all-targets -- -D warnings
cargo build --manifest-path ui/Cargo.toml --locked --workspace --bins
```

Task-owned executable RAM paths were `CARGO_HOME=/dev/shm/trill-r9-cargo`
and `CARGO_TARGET_DIR=/dev/shm/trill-r9-target-ui`, with jobs 2,
`CARGO_PROFILE_DEV_DEBUG=0`, `CARGO_PROFILE_TEST_DEBUG=0`, and
`CARGO_INCREMENTAL=0`. The helper retains a 1,200-second owned-process-group
deadline. No timeout occurred in these attempts.

## Stored bytes and scope

Every raw stdout/stderr log and source patch is stored as gzip with mtime 0.
`archive-manifest.json` records each original raw SHA/byte length and its
stored path/SHA/byte length. Packaging verified every decompressed value
against the original bytes; original receipts and raw attempt files were
not edited. Source snapshots are exact, deduplicated text. `SHA256SUMS`
covers every stored file except itself. `independent-review.json` is a
separate read-only source/artifact review, not an extra test execution.

This package qualifies Rust behavior, typed Session IPC with a scripted peer,
egui drawing/layout predicates and native executable construction. It does
not contain a new original Agentd run, compositor pixels, model execution,
issuer admission or desktop/mobile device effects. Earlier original/native
evidence keeps its original source and binaries.
