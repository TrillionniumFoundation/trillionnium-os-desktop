# A08 commit-bound source audit and actual host regression

## Fixed source and actual scope

The final executable source tested here is commit
`cf241f9c459807085e70b1ad54be21d10ca1190d`, tree
`7bd0e56ae817625355c0b6b36366eac977aa5725`. The final follow-up changes only
the Android manual, `kernel-gaps.json` status metadata and this evidence.
`source-code-identity.json` records the relevant executable Git blob IDs.

The independent target source snapshot is
`compat/android/source-audit-main-18d9fca6.json`: main commit
`18d9fca65381f0e84f130c76fa289d5186894d85`, tree
`d779baa329f7cc04fb2c2cdeb7822356d34af899`. This snapshot reads that immutable
commit while the host suite runs on the A08 branch. The embedded live scanner
inside `host-gates.json` reads the A08 checkout; it is not substituted for the
separate main snapshot.

No AOSP sync/image/APK build, Cuttlefish guest, A08 Asterinas guest probe,
physical device, Hepta workload or Android certification was executed.

## Published source identity

A00 published the two source repairs through the GitHub data API and
confirmed these identical local and remote Git trees. API publication changes
commit metadata; the raw test receipts retain the actual local commit IDs.

| Stage | Tested local commit | Published commit | Identical Git tree |
| --- | --- | --- | --- |
| Immutable source objects and UTC observation | `cfc08a3ec2d30742363153cc4b02b016e5ef697e` | `dac2f6becf7f0d1c1230dd7f91f75357ccf869cb` | `bd9fc1db6624c3f219e8f36655da549ffd0a4326` |
| Actual committed upstream lock | `cf241f9c459807085e70b1ad54be21d10ca1190d` | `73718f6247a2a5b2c4784150c7804c02584cba13` | `7bd0e56ae817625355c0b6b36366eac977aa5725` |

The final 184-test normal, optimized and complete host runs belong to local
`cf241f9`, whose tree is identical to published `73718f6`. At this source
publication handoff, A00 had advanced PR #156 to `73718f6`; the A08 owner
branch remained at `41a8c32b435f2fa9dd750ded40bd4b37cb7606c6`. Later evidence
publication or main integration is a separate stage.

The previously observed head `3ac85d8672e3afcfb70c0ee323108294ef883239` and
queued Actions run `39024900281` are an **early snapshot from before these
source repairs were published**. They are neither the latest published
source identity nor evidence of the current CI state. No CI conclusion for
the newly published source is asserted by these local test receipts.

## Reproduced defects and repair

The original generator read the worktree but labeled the result with the
requested Git ref. It could attribute a different checkout, dirty tracked
changes, untracked Binder candidates, or later-added files to an older
commit. Its observation date was also hard-coded. Five new regressions fail
on that version. `baseline-regression-result.json` identifies both the old
implementation blob and the new test input blob; this was not an unmodified
historical-tree test run.

The first repair used immutable Git blobs but still reported fixed upstream
metadata without reading the selected commit's lock. Independent review
identified that remaining provenance defect. The additional regressions
reject a missing lock, a different tag/commit/reuse policy, invalid JSON,
invalid UTF-8 and a non-object kernel section. The different-ref regression
also proves that a later lock cannot be attributed to the selected commit.
`baseline-lock-regression-result.json` records that failing intermediate
implementation. Failure counts include unittest subtests and are retained
exactly as printed.

The corrected schema 3 report resolves the ref once, reads its regular Rust
blobs and `support/upstream-lock.json` through Git object APIs, and excludes
checkout filters, local edits, untracked sources and replacement objects.
It records UTC observation time, commit/tree, individual source/lock blob
IDs, SHA256, byte lengths and modes, plus a digest of all scanned Rust
path/blob records. The report separates the expected tag, commit and reuse
policy from the actual committed lock. Missing, malformed or mismatched
lock metadata adds a `pinned_lock` source blocker. Matching those expected
metadata fields does not prove that derived kernel source equals upstream.

## Recorded runs

| Run | Actual result | Evidence |
| --- | --- | --- |
| Original source-binding/date regression | 7 tests; 5 failures; exit 1 | `baseline-regression.log`, `baseline-regression-result.json` |
| Intermediate lock-binding regression | 10 tests; unittest summary 7 failures and 2 errors, including subtests; exit 1 | `baseline-lock-regression.log`, `baseline-lock-regression-result.json` |
| Intermediate normal/optimized suites | 181/181 each, no skips, before the lock repair | `before-lock-binding/unittest*.log` and result JSON |
| Intermediate complete host run | `host_passed_only`, 181 tests, actual Java/JNI loading | `before-lock-binding/host-gates*` |
| Final normal Python | 184/184, no failures/errors/skips | `unittest.log`, `unittest-result.json` |
| Final optimized Python | 184/184, no failures/errors/skips | `unittest-optimized.log`, `unittest-optimized-result.json` |
| Final complete host run | Exit 0, `host_passed_only`, 184 tests, actual Java/JNI compilation and loading | `host-gates.json`, `host-gates-result.json`, `host-gates.log` |
| Final source integrity | 63 required inputs present, 71 checked inputs, no errors | `source-integrity.json` |
| Independent main-object verification | 16 required/lock inputs and 757 Rust inventory entries checked against Git objects; no mismatch | `main-source-verification.json` |

The earlier 181-test receipts and schema 2 snapshot are preserved byte for
byte under `before-lock-binding/`. They describe commit
`cfc08a3ec2d30742363153cc4b02b016e5ef697e`, tree
`bd9fc1db6624c3f219e8f36655da549ffd0a4326`; they do not qualify the later lock
repair. Receipt command output paths describe the original execution
locations; the earlier files were subsequently grouped into that directory.

Run commands from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/workloads/android -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -O -m unittest discover -s tests/workloads/android -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 support/android/verify_host.py --out /tmp/a08-host-gates.json
PYTHONDONTWRITEBYTECODE=1 python3 support/android/verify_source_integrity.py
python3 support/android/generate_kernel_source_audit.py --repo-root . --project-ref 18d9fca65381f0e84f130c76fa289d5186894d85 --output /tmp/a08-main-source.json
```

Each result JSON retains exact argv, source commit/tree, UTC start/end,
environment and raw-log SHA256. The host run reused the existing isolated
official Ubuntu javac launcher/JNI headers with the existing OpenJDK 17.0.20
runtime/compiler modules. Installation composition and digest remain in
[`jdk-installation.json`](../2026-10-17-source-integrity/jdk-installation.json).
No further JDK or AOSP installation occurred in this round.

## Qualification boundaries

The final host run actually compiled the C JNI shared library and the Java
harness and loaded them, printing
`HOST_JNI_INTEGRATION_PASS isa=x86_64 pid_equal=true`. Actual Linux ABI,
Binder UAPI layout and child-only seccomp probes passed. Binder device open
still returned BLOCKED/77; no Binder transaction was proven.

The fixed main source scan still returns exit 2 for Binder, seccomp and
Android MAC. Its lock metadata matches the explicit expected fields, which
does not implement those features. All Android/Asterinas runtime flags remain
false. Unit cases with fake QEMU, ADB or VINTF output remain fixture evidence.

GitHub Actions run state is independent of these local results. A queued job
has no passing conclusion, and a clean merge calculation is not an executed
integration test. A00 must preserve this distinction when integrating the
A08 sources with a later main commit.
