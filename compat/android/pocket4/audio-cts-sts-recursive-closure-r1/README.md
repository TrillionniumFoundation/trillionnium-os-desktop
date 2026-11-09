# Complete the original CTS and STS provider closure for Audio

The strict Audio APEX build reached the original CTS app-security graph and stopped at five missing providers: `CompatChangeGatingTestBase`, `CtsPkgInstallerConstants`, `cts-host-utils`, `cts-statsd-atom-host-test-utils`, and `sts-host-util`. Restoring only those declarations would expose further real dependencies and source files that the sparse lock had not selected.

This patch keeps those original providers, their original sibling modules, and their consumers. A recursive audit using the frozen upstream Blueprint parser followed module dependencies, defaults, source filegroups, and the relevant original generated-provider implementations. It selected 90 additional original Blueprint files and followed 2,433 modules and 7,152 explicit dependency edges, with no unresolved or ambiguous edge in that audited closure. The source plan records the original BP byte hashes and the original empty globs; it does not manufacture files to fill upstream empty globs.

The lock grows from 317 to 321 projects. Eighteen existing projects gain exact source cones while preserving all prior cones, revisions, and purposes. Four projects are added at the gitlinks independently observed in the same frozen Android 17 superproject: Caliper, MIME support, NpuManager, and liburingutils. The bounded project capacity increases from 320 to 336. Unrestricted synchronization remains disabled.

The retained libandroid graph requires the original NPU Rust AIDL provider. Its original BP also declares the NPU SDK library. The patch preserves that complete BP and prevents duplicate sparse fallback imports for its public, system, and module-library scopes in Audio mode. Both the original NPU provider and its scope-enabling common defaults are checked by exact SHA-256. The system-server fallback and other build modes retain their previous behavior.

## Apply and verify

The baseline is the 438-file public source recorded by the preceding `audio-errorprone-provider-r1` capsule. The resulting public source has 448 files, including ten original BP fixtures. This capsule records both complete file maps. Apply after verifying the changed baseline files, or port the source changes explicitly and rerun the normal tests.

```sh
git apply --check audio-cts-sts-recursive-closure.patch
git apply audio-cts-sts-recursive-closure.patch
cargo test --locked --offline -j1 -p droidloom-source
cargo test --locked --offline -j1 -p droidloom-update android::tests::audio_
cargo build --locked --offline -j1 -p droidloom-source -p droidloom-update
```

The actual normal build passed all 18 source tests and 33 Audio tests. Four new regression tests verify the monotonic source extension, reject missing cones and substituted new-project commits, preserve the complete original provider and sibling declarations, and constrain the NPU SDK fallback to the exact original three scopes. Historical extension tests reconstruct the exact previous 317-project lock before replaying earlier changes. No test was disabled.

The static dependency audit and successful normal tool build do not establish full APEX or runtime qualification. Fresh normal source reconciliation and verification, the strict complete APEX build, actual compilation evidence, signature and contents validation, ABI checks, and device runtime acceptance remain separate gates. The original targets and missing-dependency errors remain enforced.
