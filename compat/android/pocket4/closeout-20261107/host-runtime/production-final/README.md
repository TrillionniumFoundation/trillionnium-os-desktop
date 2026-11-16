# Pocket4 Status / Readiness production candidate

This is the source and offline validation package for the November 7 Pocket4 closeout. The committed Droidloom source is **17ca3fa46e8b249df89ad4f12e338a524c54e640**, tree **380d6995a4e53e32ebe6526a20a57440bbe3560b**. The build and preparation receipts in this directory describe a candidate before installation. Actual deployment, new Main qualification and Storage lifecycle results belong in separate subsequent receipts; these original results must not be relabelled.

## Change and reason

A running Status request previously entered the Android readiness probe and spawned a direct child of the daemon. That observation could disturb the exact owner-child identity required by the existing Main guard. Status now reports the authenticated cell lifecycle. An explicit Readiness request retains the former fresh Android service checks. WaitReady, application launch, application listing and icon readiness gates remain in place; a lifecycle response cannot substitute for readiness.

Running Status is covered by an owned-process dispatcher regression that first proves fork denial is active, then verifies Status succeeds without changing the direct child and that fresh-readiness operations still encounter the denied spawn. Daemon polling still performs normal cleanup after an exited cell, so this package does not claim that Status is free of cleanup in every state.

The CLI Unix-socket fixtures use exclusive RAII temporary directories directly under /tmp. This fixes the original SUN_LEN failure under a long TMPDIR without weakening production package-helper behavior. CLI tests run inside a private mount/PID/network namespace with the package marker hidden, the absolute package helper bound to /dev/null, a private /run and /tmp, uid/gid 1000, no effective capabilities and no-new-privileges. The host root is never remounted through a shared superblock.

## Installed production lineage

The initial source base, 500dd3af851aaadb95537b68129b8bd889504951, did not include two features required by the installed Pocket4 system. Its initial test pass was therefore not an installation qualification.

The actual installed daemon and supervisor match the November 1 production-media artifacts:

| Component | Installed SHA-256 |
| --- | --- |
| droidloomd | 4c57f3e9e92a39f2aef700d77b56c108a88d9ba3ba3cfe82b2613b363514ef30 |
| droidloom-supervisor | 1f11ba9107ffe1fc4107d41368fbc609d067af2d7f47c2dace8fa70626ceda0d |

The production source anchor is 43c1cfc087361e9a4e5599500da1f2b8249bf38f plus its recorded native-media patch. The final candidate preserves DrmMediaDmaHeap, the real system DMA heap in the private guest device tree with mode 0444, and device-type/symlink validation. The final lib.rs and linux_plan.rs are byte-identical to that production source. Host device permissions are unchanged.

The external namespace command preserves the production TERM and forward-signals arguments. Its pre-exec parent-death hook sets SIGTERM; Android init's separate later SIGKILL protection is unchanged. The existing compat/unshare wrapper remains part of the protected installation. The actual Main launcher is Python 3.14 running that wrapper; its intermediary is util-linux unshare. The supervisor executable named in their argv must not be misreported as the launcher ELF.

The complete comparison covers 39 build inputs: 28 are identical to the production source. The 11 differing paths are documented in [production-source-comparison.json](production-source-comparison.json) and the complete [production-source-diff.patch](production-source-diff.patch). In addition to this Status/Readiness change and its tests, the newer base includes:

- Explicit, bounded original base/split APK installation through the existing authenticated owner and fresh readiness gates. Moving tempfile into runtime dependencies supports that path; Cargo.lock is unchanged.
- A read-only DevelopmentInspect command and CPU-inventory validation. Existing activation and teardown requirements remain.
- Bounded diagnostic improvements: filter retained package logs before selecting their rendered tail, reject missing/failed activity exit history, and show exact-package lifecycle samples with explicit incomplete-sample and attribution limits.
- Tests for those additions. No arbitrary exec or shell command is exposed by droidloomctl.

Applications, contracts, CPU-placement and window-policy crate inputs are identical to the production source. The exact source delta against 500dd3 is [source.patch](source.patch); it applies inside the independent Droidloom checkout, not at the root of the desktop evidence repository.

## Verification

| Verification | Actual result |
| --- | --- |
| Four release binaries, exact Rust 1.93.0, offline locked build | PASS |
| Selected dispatcher and CLI lifecycle tests under long TMPDIR | 15 PASS |
| Complete unit suites of five host runtime crates | 138 PASS, one existing private fixture ignored |
| Actual current cell.json parsed by both installed and candidate plan commands | Complete JSON plans equal |
| Active readiness consumer failure/no-fallback/owner regressions | 20 PASS |
| AST equivalence after declared consumer edits | All six scripts PASS |
| Eleven-target transaction: success, rollback, injected rename failures and refusal cases | 10 PASS locally and on Pocket4 owned temporary files |
| Installed Main, application business flows and Storage unmount/remount | Not established by these offline receipts |

The release build used one CPU, one Cargo job, 2 GiB memory, nice 10 and zero swap on its own job cgroup. The exact resource and command evidence is in [build-result.original.json](build-result.original.json); complete test records and output are in [tests-result.original.json](tests-result.original.json), [suites-result.original.json](suites-result.original.json) and test-logs/.

The production build job is 1a1b3a2f7ea-fc05-83fe. Its result SHA-256 is 9e0e11dfd42c6816424ab874e1619da76d9f71072776e424f02cd89162dafcc5. The final binary paths, lengths, source/tree identity and hashes are in [binaries.json](binaries.json).

## Consumer closure

Four actual request sites move from Status to explicit Readiness while retaining the 8-second timeout, no fallback, readiness text/state check, exact owner/argv, namespace and explicit interactive-authorization requirements:

- /usr/local/bin/android-app
- /usr/local/bin/android-app-digitalis-validation
- /usr/local/libexec/android-digitalis-observe-helper
- /usr/local/libexec/android-digitalis-validation-helper

The separate android-app-digitalis and android-digitalis-helper use process discovery, not Status RPC. Their discovery behavior is unchanged. Obsolete QA suggestion fields are removed from the retained CLI paths; the INTERACTIVE_PRODUCTION_PROTECTED gate and error semantics remain. The final digitalis helper has unchanged bytes but participates explicitly in the matched cohort.

android-desktop uses Status as a lifecycle observation and retains that behavior. Obsolete QA/v2/before-discovery entrypoints are retired by the cleanup owner only after installed consumer migration and reference checks. Their private old CLI is not upgraded through an unsupported Readiness fallback.

The complete declared edits and actual checks are [consumer.patch](consumer.patch) and [consumer-validation.json](consumer-validation.json).

## Retained failures and limits

Original SUN_LEN failure evidence remains at its original host path and hash 95e5075de61ee94e9789c4632db9eab77e29e751df8c08da33f2b633e0b9d796. Initial passing but production-incompatible binaries are not deployment inputs.

retained-failures/ preserves the new preparation parser failure, the missing Command import compile failure, and the initial PDEATHSIG worker-thread fixture failure. The latter fixture observed a different libtest thread after exec. The final regression observes the real PR_GET_PDEATHSIG value in the same pre-exec chain that arms the owned child, then runs the test executable's non-executing --list path. It verifies the actual kernel setting without presenting the failed worker-thread observation as a pass.

A derived Storage member manifest also rounded 64-bit nanosecond timestamps through JavaScript Number serialization. The untouched original held-input receipt was correct. The accepted v2 member is rebuilt using Python exact integers and explicitly supersedes the rounded derivative. Deployment metadata must always be transported as original UTF-8 bytes or parsed by an integer-preserving implementation.

The matching daemon, CLI, application service, helper scripts and reviewed Storage jar are prepared as one eleven-target upgrade with preserved install attributes and a complete rollback set. See [DEPLOYMENT.md](DEPLOYMENT.md). Source validation does not reauthorize old Main epochs, old nonce values or old incomplete business-flow records.

