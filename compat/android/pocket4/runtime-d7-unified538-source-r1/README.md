# D7 unified Android tools and runtime source

This capsule reconstructs one complete 1,595-file producer at commit `273d1a2b554923b7b53e645560ddbe5999cbde9b`, tree `cde7467f68d2de89f688431cafd494fed147e247`.

The two complete authenticated inputs are Audio538 (1,557 files, commit `fbb235628023f5fb5d9e47064a6d2884d23534bc`, tree `23c1a126efd8975156d219af22a2d858a4dd3b2b`) and D6 (430 files, commit `7d86a66b8d95477781519cec99e53fd0e76b6f36`, tree `224fdc48b1083044cdce30a09ee4ec995a48c12d`). All 66 selected runtime files are bound to the complete D6 root. The resulting delta changes 13 existing files, adds 38, and retains the other 1,544 Audio files exactly. The current IntentResolver and AAC security fixes, original Android provider lock and all Android build-tool source are retained. Cargo.lock records the existing sha2 dependency for the supervisor without resolving a new dependency generation.

## Actual qualification evidence

The 167 original records bind this exact unified source to 289 ordinary runtime tests, four freshly built release binaries and a subsequent complete 334-test qualification of the source/updater tools. All 21 privileged runtime tests remain explicitly unqualified. The later tool check compiled five new test harnesses, ran the actual network test, the EROFS 1.9.4 metadata repack, the C++ release-queue tests and the original DMA layout test. It preserved all four existing release binaries and all 1,595 source files.

DMA used a private complete 103-file minigbm checkout at the exact original commit. That fixture and its Git metadata are excluded from the published producer. The source and binary bookends, full command logs, original H envelopes, 43 fresh PIDFD ESRCH observations, six absent cgroups and zero OOM events are included. The first independent reader's real 32 MiB debug-harness read failure remains failed; the second reader admitted only the five recorded exact artifact sizes and did not repeat Cargo or tests.

## Replay

Supply independent complete Audio538 and D6 source directories. The verifier authenticates every file, mode, Git blob and complete root, including both original raw commits. It copies only Audio's source files, creates fresh private Git metadata, checks and applies the complete patch, reverses it to the original 1,557-file root, and reapplies it to the current 1,595-file root. Both source inputs retain their complete F9 identities.

```sh
python3 -I -B verify.py --inventory-sha256 "$D7_INVENTORY_SHA256" \
  --audio-source /absolute/audio538 --runtime-source /absolute/d6 \
  --output /absolute/fresh-d7 --report /absolute/fresh-replay-report.json
```

The FILES.sha256 digest must come from the reviewed workflow or publisher. Output and report paths must be fresh, without aliases, and outside all input trees.

## Fresh CI

`run_ci.py` uses a new Cargo target outside the producer. It freshly compiles and runs all 289 ordinary runtime tests while checking the exact 21 ignored privileged identities. It separately executes the current source test and three updater tests for libueventd538. It then builds four new unified release binaries, records their Cargo provenance and all private hardlink aliases, creates independent single-link 0555 copies, and exercises all four normal CLI help entries. It compares every source byte, Git blob, mode, member and F9 after both success and failure.

Fresh CI therefore covers 293 actual tests and four newly built release products. The host's 334-test history is not counted as a fresh CI run. No private minigbm fixture, historical ELF or host Cargo cache is imported into CI.

```sh
python3 -I -B run_ci.py --inventory-sha256 "$D7_INVENTORY_SHA256" \
  --producer /absolute/fresh-d7 --target /absolute/fresh-cargo-target \
  --report /absolute/fresh-ci-report.json --jobs 2
```

## Execution boundary

This capsule publishes the unified source and its reviewable qualification history. It does not start Android, load an SELinux policy, install an APK/APEX, qualify an Android full build, satisfy the 21 privileged runtime tests, or make production execution constructible. Runtime, SELinux transition and production-ready gates remain false. Final deployment must use the qualified current unified components and separately verified Android outputs; the older runtime components embedded in preceding Android-only producer generations are not deployment inputs.
