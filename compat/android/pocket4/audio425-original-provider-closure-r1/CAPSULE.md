# Audio425 original provider closure

This capsule contains two ordered source repairs for the normal strict Audio APEX build. The first extends the prior 321-project source to 425 projects at the same frozen AOSP superproject. The second adds the complete original RKPD APEX directory at the already pinned RemoteKeyProvisioning commit. It keeps 425 projects and the same product, targets, strict missing-dependency policy and resource limits.

The frozen superproject is `28f0bbddc24d56c8ec5a8df5342ac7a292184039`. These source inputs belong to the original Android 17 release generation; their qualification does not establish compatibility with the newer QPR1 system, ART, bionic or official APEX set.

## Ordered source changes

1. Apply `audio-original-provider-closure.patch` to the exact predecessor identified by `source-delta.json`. The patch adds original provider projects and finite source directories, restores five complete upstream Blueprint bodies in Audio scope, and restores three required discovery roots. It preserves original consumers and rejected foreign discovery markers.
2. Apply `audio-rkpd-apex-source.patch` to that result. `rkpd-source-delta.json` binds the one additional same-commit `apex` directory, the original Blueprint fixture, the new exact lock hash and the source validator. The directory includes the upstream public development signing inputs from that AOSP project. This capsule does not contain device or user signing material.

The first frozen source plan retains 1,518 original Blueprint pins. The RKPD delta adds one original Blueprint. Its six-file directory is selected as a complete source directory. The original 425 plan and its planning flags remain unchanged; the later delta is an independent continuation.

The finite source limits remain 425 selected projects within a 432-project bound, a maximum of 355 selected paths within a 368-path bound, and a 1 MiB source-lock bound. URL, commit, path normalization, duplicate and monotonic-extension checks remain in force.

## Actual validation and pending work

`validation.json` records the actual normal Rust tool builds and the exact sanitized receipt hashes. The first generation passed 22 source and 36 Audio tests. The RKPD generation passed 23 source and 37 Audio tests, including reconstruction of the exact prior 425 lock, rejection of the old missing directory, Blueprint-only selection and a different revision, and preservation of other build scopes.

Normal Desktop source materialization is pending at this capsule's creation. A full strict build, whole-APEX cryptographic and content qualification, compiled bridge evidence, QPR1 compatibility and runtime audio acceptance remain pending. Static closure metadata and normal tool tests grant none of those qualifications. The 17 unresolved static-frontier entries remain recorded for the normal strict Soong invocation; this repair does not invent modules or enable missing dependencies.

## Complete allocation observations

`allocation-observer/owned_allocation.py` is the exact shared-r3 source tested on Desktop. It retains two-root behavior by default and requires an explicit `required_roots=1` for a single workspace. Only a complete exit-zero scan with exact NUL-delimited output is a measurement. The helper preserves stderr and ownership evidence, retries only the recognized transient disappearance diagnostic within three attempts and a total 30-second deadline, and reaps its own process through PIDFD ownership.

The existing 14 functional controls and three single-root controls passed independently on Linux, including a real scan of the owned workspace with the actual system `du` executable. The sanitized functional receipt is in `allocation-observer/validation.json`. It does not qualify another host or a full build's resource budget.

Run the controls in a fresh Python process:

```sh
python3 -I -B allocation-observer/run_portable_tests.py
```

On a platform without the required Linux PIDFD interfaces, the runner reports the exact 17 skipped identifiers and zero passes. `platform-requirements.json` lists those identifiers. Skips are not execution evidence.

Run the normal Rust source checks after applying the ordered patches in the complete repository:

```sh
cargo test --locked --offline -j1 -p droidloom-source
cargo test --locked --offline -j1 -p droidloom-update android::tests::audio_
cargo build --locked --offline -j1 -p droidloom-source -p droidloom-update
```

This is a fresh public reconstruction from durable actual source and validation records. It does not claim byte identity with an unpublished local prototype that became unavailable. `FILES.json` binds every delivered public file.
