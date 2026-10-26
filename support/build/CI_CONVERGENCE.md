# Product CI convergence

This record explains the observed failures on Desktop `bee137ed` and the
repairs in the next candidate. A repaired workflow is not a passing execution;
its exact source, logs and terminal result must still be recorded.

## Original native F1 preparation

[Run 40219859406](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/40219859406)
failed before guest execution. Its retained artifact `12618329681`,
`frozen-inputs/fixture-resolution.log`, reports a missing
`android_system_properties v0.1.6` download under `--offline`. Both original
Agentd and observer builds had passed. The preceding prefetch used
`cargo fetch --locked --target x86_64-unknown-linux-gnu`; fixture metadata
resolution had no platform filter and requested packages for other targets.

Both fixture metadata commands now use
`--filter-platform x86_64-unknown-linux-gnu`, matching the fetch and actual guest.
The first normalization remains offline; the second remains locked and offline.
The unchanged original fixture and the original shared-package lock-identity
check remain mandatory. A failed command now records `status=failed`, the raw
log name and error, and prints at most the final 16 KiB of that original log.
The full artifact remains authoritative.

This run compiled Desktop `0187bd578f6786c40c812c13976e4889a1aba835`
and Hepta `b3d3f2d4b01f123d7ac17575c27fb54d00094f7f`. Its ordinary
kernel build/boot result does not qualify the newer product pair. The selected
source review and a fresh build/guest execution are separate requirements.
See [the native runtime gate](../../tests/workloads/hepta_agentd_runtime/README.md).

## Native UI post-check

[Run 40219859375](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/40219859375)
had a primary Notes recovery test failure. Its artifact `12618825097` records
an empty `source-after-status.log` and successful UI metadata resolution. The
secondary failure in `native-text-metadata-after.stderr.log` was a missing
`arc-swap v1.9.2` under `--offline`, from the independent host Cargo root.
The prior UI test failure had skipped the later host test that normally warms
that root. The source guard was therefore dependent on unrelated test success.

The initial online, locked metadata stage now resolves both original product
roots before executing any tests. Post-checks remain locked/offline and retain
their original source, graph, cache and lock checks. This change does not fix or
hide the primary Notes test failure; that requires its own code regression and
execution. Worktree status and tracked diffs are also printed and retained.

## Standalone original owner worktree check

[Run 40219859366](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/40219859366)
passed its original writer/socket tests and formatting/Clippy, then failed its
source-cleanliness step. That old workflow did not print or retain untracked
status; the observed log cannot identify its exact final offending path.
The workflow also omitted `CARGO_TARGET_DIR`, and the standalone workspace has
no target ignore rule. Cargo output is now placed under `RUNNER_TEMP`, outside
the reviewed source tree. The final step records and prints HEAD/tree, full
porcelain status, tracked diff and lock SHA256 values before enforcing all
original clean-source conditions. The next actual run must establish whether
this was the cause; the historical failure remains unresolved until reproduced
or identified by actual retained status.

## README policy

The selected `bee137ed` product already treats root README as a tracked regular
file. Empty or nonempty navigation content is valid; missing, directory or
symlink README inputs are rejected. The immutable kernel/source checks remain.
No older zero-byte or nonempty-only rule is reintroduced from the divergent
`ca0b559` branch. The real source-verifier README regressions and the permission
SMP source-entry tests exercise this policy.
