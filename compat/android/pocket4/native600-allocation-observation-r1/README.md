# Native600 allocation observation review

This is an independently verified controller patch candidate for PR #300. It records and bounds allocation observations, retries only exit-code-1 observations within one shared deadline, and rejects incomplete totals. It has not been deployed or used for a full Android build.

## Current evidence and scope

The read-only observation in `fresh-state.json` found Native600 recipe `a538dae77820882a534ee79e0eb6d2984508a712`, tree `4c844ae9333731821c95fdf8f305f4a2d9150586`, and the 354,218-byte source lock with SHA-256 `600dc00660af69b4b8eeb497fac8f2a83f0d8b24ad3d02c2774a4df96f5ec8cf`. The active owner's recipe already includes the independently identified DeviceLock production cones and pinned `external/mime-support` provider. The older Native597 candidate is superseded and is deliberately excluded from this contribution.

Native600 r4 remains **FAILED**. The failing command reported `owned output allocation observation failed`. Its monitor invoked `du`, discarded its return code and captured stdout/stderr, and retained only that generic exception. The original errno is therefore **unknown**. A concurrent traversal race is a reproducible failure class, not a proven diagnosis of the historical failure.

The r4 evidence recorded no `soong_ui`, `soong_build`, or `ninja` observation and no effective source/compile-window witness. Resource retirement passed: memory peak 13,513,158,656 bytes, zero OOM/high/max event increments, and zero swap. Source restoration, exact 600-project materialization verification, and owned retirement passed. These facts do not qualify the engine/ART pair or any app runtime.

The retained controller preimage is exactly 40,850 bytes, SHA-256 `114a85f5e28f06d2d89b7578395eb9ed6b66768205074ab16d7414388221da31`. Its source is the ai395 path recorded in `fresh-state.json`. The supporting resource/ownership module is unchanged; its SHA-256 is `23370cf3fba43a8d6bbd8be888a28a3a7add33125cafff3cd2803f5e09e27297`. The two allocation roots are distinct sibling absolute directories on the same device, with no overlap.

The final read-only check at 2026-11-09 04:37:49 UTC again found both exact source hashes unchanged and no r5 control or qualification directory; see `final-fresh-check.json`. This is a timestamped observation, not a lease or authority to modify the live owner.

## Candidate behavior

- The baseline, monitoring, and final allocation paths use the same strict parser for exactly two NUL-terminated GNU `du` records. Empty output, missing roots, extra or repeated roots, unknown paths, malformed or negative integers, and absent terminators fail.
- Monitoring keeps each attempt's return code, exact stdout/stderr bytes in hexadecimal, timeout state, and observation metadata. A complete sample record is only an observation; successful return requires subsequent admission checks. No observation record grants build or runtime qualification.
- Only return code 1 can be resampled, at most three times within one shared 30-second decision budget. No nonzero or partial observation supplies a total. Timeout, root identity changes, malformed successful output, unexpected successful stderr, other exit statuses, and exhausted attempts fail closed.
- The common deadline is checked after successful parsing, after diagnostic persistence, and after a fresh shared disk/memory admission check. Process creation, scheduling, and uninterruptible filesystem I/O are not claimed to have a hard wall-clock bound.
- Each monitoring child receives a 64 KiB per-file `RLIMIT_FSIZE` for its two temporary log streams. Reaching either limit fails; successful observations cannot hide truncation. Three failed attempts can retain at most 384 KiB of raw stream bytes (768 KiB as hexadecimal, plus small metadata). The parent builder's file-size limit is unchanged. Baseline/final commands retain the existing owned-command log and retirement bounds.
- The strict `< 96 GiB` incremental allocation gate, resource profile, source checks, recovery paths, and existing `run_build(config)` / `monitor(row)` interfaces remain in place.

## Reproduce offline

From this directory, run:

```sh
python3 verify.py
```

To retain a new report in a fresh directory:

```sh
python3 verify.py --report-directory /tmp/native600-observer-review-result
```

The verifier checks the packaged file hashes, applies the patch to the exact preimage in a temporary directory, verifies the resulting candidate hash, and runs 20 tests against functions extracted directly from that reconstructed controller. It never imports the controller's host-specific top-level actions. The retained result and log are under `verification/`.

All file/source/hash gates use explicit runtime checks, including under `python3 -O`. The verifier removes inherited `GIT_*` variables before setting its three required Git controls. It passes its actual optimization level to the test process and verifies the child's reported level. The normal and optimized verification receipts are retained separately. Run `python3 -O test_verifier_smoke.py` for two additional smoke tests covering three actual tamper cases: changed original bytes, changed patch bytes, and a changed expected candidate SHA. Each launches the verifier under `-O` with hostile inherited Git overrides and must be rejected before a verified candidate can be reported.

The tests cover real GNU `du` across sibling roots and hardlinks; a real child exceeding the kernel-enforced log limit; the original monitor's first-failure behavior; bounded recovery; persistent failures; exact stream retention on timeout; shared and late-success deadlines; post-persistence admission; missing, duplicate, overlapping, replaced, and symlink roots; malformed totals; the actual baseline/final assignments; and the unchanged strict 96 GiB boundary. These are isolated function tests, not a full controller launch, Soong build, or runtime test.

## Adoption requires a fresh generation

**Do not execute the reconstructed r4 controller or replay its constants, configuration, or evidence. Do not rewrite r4's FAILED result.** The preimage is retained solely to make this delta reviewable and reproducible.

An authorized owner must port the reviewed delta into a fresh generation with new OUT, RESULT, temporary-work path, unit/job identity, configuration, controller/source pins, and launch bindings. Recheck the current owner and latest recipe before doing so. Any future full build needs its own admission, strict ordinary build, exact source/compile-window observations, source restoration, resource/retirement checks, artifact qualification, and runtime evidence. This capsule changes no live tree, CURRENT, owner lease, installed app, or production-readiness claim.
