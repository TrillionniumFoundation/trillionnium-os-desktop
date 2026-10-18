# R6 Shell observation freshness — actual RED/GREEN evidence

The final frozen source `84f0070b6e7e01238a8dac6044748b15101c9497` passed the six targeted
freshness regressions, two existing layout-predicate tests, Shell Clippy with
`-D warnings`, workspace formatting and the native workspace binary build.
This bundle retains the successful result and all preceding attempts. There
were **three GREEN attempts: two failed, the third passed**.

## Defect and resulting behavior

A Session response can wait in the Shell queue while the UI is paused. The old
pre-draw path assigned a new local receipt time when it consumed that response,
then tested only receipt age. The RED test used sample time `10000` and current
time `18001` with a just-received response. The real `hepta_panel::status`
widget produced **`Hepta: OBSERVED · READ ONLY`** for this expired observation.
The exact text is retained in `red-01/freshness-tests.log`.

The fix evaluates both the original observation timestamp and the local
monotonic receipt before painting any page. Both ages may be at most 7000 ms;
7001 ms expires the observation. Future or missing timestamps cannot appear
current. Downgrading preserves the full previous observation, the Session's
attempt timestamp and existing unknown-state diagnostics. A later fresh
Session snapshot may restore Observed. The delayed-response regression now
requires the actual widget text `STALE · CURRENT STATE UNKNOWN`.

The queue in these deterministic tests is synthetic; the Desktop receive path,
pre-draw expiry path and egui status widget are the real production code. These
tests are not original Agentd, compositor-pixel, physical display, keyboard,
device-control or objective-submission evidence. The original six-phase Shell
captures are a separate gate and are not claimed by this bundle.

## Attempts and executed code identity

| Attempt | Frozen source | Actual result | Interpretation |
| --- | --- | --- | --- |
| RED-01 | `821841baf5c106b7fc5e4b849ac94636b1b724f7` | Cargo 101; 1 passed / 5 intended failed | Old production behavior was reproduced through the actual status widget. Helper success means the expected failure was observed, not that the product passed. |
| GREEN-01 | `f0f10dff564037fabc35809a8d8bb174dc5becb9` | Cargo reused RED's test ELF; 1 passed / 5 failed | Warm-target source binding failed. Cargo printed no Shell compile line and finished its test profile in 0.15 s. This is not a GREEN source regression. |
| GREEN-02 | `f0f10dff564037fabc35809a8d8bb174dc5becb9` | Actual Shell recompile; 6 freshness + 2 layout tests passed; Clippy 101 | Strict lint rejected only the new test helper's complex sender return type. Production behavior passed its targeted assertions; the complete gate still failed. |
| GREEN-03 | `84f0070b6e7e01238a8dac6044748b15101c9497` | Actual Shell recompile; 6 + 2 passed; Clippy/fmt/workspace build all 0 | A named test sender type resolved the lint. This is the final passing source and build. |

RED extracted the real pre-draw entry while preserving its old receipt-only
semantics. Commit `f0f10dff564037fabc35809a8d8bb174dc5becb9` added the dual-clock
fix. Final commit `84f0070b6e7e01238a8dac6044748b15101c9497` only names the test sender type.
The final source tree is `9c8e3627a970f9c3f2bea9bbdde583adeb4bc313`. `source-bindings.json` also
records the UI manifest/lockfile and the Session's external `hepta-os` source
and manifest objects.

The RED test ELF SHA-256 is
`25d61caecad7fa2a9117b8968f8504d3b9fed707ee4aad9f15fcbfbe8da0462b`. GREEN-02's genuinely recompiled
test ELF is `d96e6b9de7c55fba7b3fb702fcb56c07cc506df329e47ee538bab82d2be94f70`. GREEN-03's executed
test ELF is `2139a6f1f19229a52f717eaa6b1dd5ce1b2cb68123ce7b0e39af309e718769fd`. The preserved cache diagnosis
records the older GREEN source mtime and workspace-relative dep-info: neither
absolute worktree appears in that dep-info. Assertions and source line numbers
in GREEN-01 match RED; a clean frozen HEAD alone was not sufficient proof.

## Cache, cleanup and resource limits

The R5 target was copied into a fresh task-owned disk directory, with all 2,754
regular files / 909,594,005 bytes verified by SHA-256 on source and destination.
`copy-receipt.json.gz` is the complete unchanged copy manifest, compressed with
a fixed gzip timestamp; its uncompressed SHA-256 is
`c5d2222dbbf30abc30abdd83f90b2c539d963906632f41d34a0d7f2c6bef9434`. `post-check-r5-retention.json`
rehashes the four retained R5 production ELFs after all UI tests/builds and
confirms their bytes remain unchanged. That second check is explicitly scoped
to those four ELFs, not a second full target-cache scan.

To resolve observed cross-worktree cache reuse, subsequent attempts run the
recorded command `cargo clean --manifest-path ui/Cargo.toml -p trill-shell
--locked --offline` with `CARGO_TARGET_DIR` set only to the new copied target.
Every accepted test run must then contain the actual Shell compile line for
the frozen source directory. No retained R5 target artifact was cleaned.

The helper uses Rust 1.88.0, offline locked Cargo, one build job, no incremental
or debug information, a 300-second per-command deadline, a 1-GiB disk reserve
and a 7-GiB nonreclaimable-memory stop threshold. Per-command logs, observed
exit codes, cwd, source pins, target directory, samples and timing remain in
each receipt. Each attempt includes the helper and process-group guard source
snapshot taken before execution. The guard retains and reaps its owned process
group; this build evidence does not claim arbitrary descendant-parent-death
qualification.

## Final four workspace binaries

| Binary | Bytes | SHA-256 |
| --- | ---: | --- |
| `trill-shell` | 24,154,200 | `62d0f304d6a3a53db4bc605e374470a924a56bfeb63387b1c12f9f245f17536a` |
| `trill-session` | 3,527,792 | `f152e6413742baa3349aded2283f9aff41bfe1bc552586aa260ade6327d5d16d` |
| `trill-ctl` | 1,494,736 | `ba85b891f91a88ac3ad5240535f5dd6261c47eadbcc1bb64593add0a0aa2b598` |
| `trill-app-window` | 22,627,904 | `08c3bbe84b5d6e773f367f9751a1432eaee327bf45a5b172150f34f165342510` |

`green-03/production-build.log` records compilation of `hepta-os-observer`,
`trill-session`, `trill-shell` and `trill-app-window`. The final workspace
command also verifies `trill-ctl`; it has no separate compile line in that
command. The app-window build reproduced the same bytes as R5. All four paths,
ELF x86_64 checks, sizes and hashes are recorded; four changed hashes are not
claimed. These are Linux host binaries, not target-kernel or mobile-device
execution evidence.

## Review and archive checks

Run `sha256sum -c SHA256SUMS` in this directory to verify the curated bytes.
Use `gzip -dc copy-receipt.json.gz` to inspect the complete original copy
manifest. This archive contains no target cache, executable bytes, credentials,
Xauthority cookie, private runtime state, model calls or screenshots.
