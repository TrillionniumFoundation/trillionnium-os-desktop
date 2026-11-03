# Original Agentd native lifecycle: implementation and host evidence

The ten new gate/source files bind Desktop c5c88794bf227b1d862b2f914b02809a0090e854, tree 87bc4e4d72697a7583fb0afafe4db4b41582941c, and original Hepta 6d6097da843f5831dfaf9cee3530da512d072a15. Desktop main merge 39c1d84ebf854958f5829c0118b0c8b92a6b4926 has that same tree.

[Execution report](validation/execution-results.json) retains exact commands, seven raw logs, source identities, 38 host tests in ordinary and optimized Python, 11 unchanged ABI refusal tests, static launcher compilation, and workflow syntax checks. These are host results; Agentd, its fixture and QEMU were not executed in this workspace.

The actual [A06 artifact import](validation/final-native-ready/kernel-import/import-result.json) verified artifact 12480223660 from [successful final-head run 39898657974](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39898657974): ZIP SHA256 12f6e6ccd459358e5cc254c7aa60d1f0ca16d9930e66c0f58906c18ab9b5784e, three unchanged 7,821-file source inventories, ordinary build exits, exact kernel/initramfs/BIOS and the original raw boot/QueryAbi oracles. The [transcribed build receipt](validation/final-native-ready/kernel-import/kernel-build.json) is an import of that original build, not a new kernel build or a daemon execution. Its `original/` paths refer to the actual importer output assembled from that fixed artifact; large source inventories and binaries are retained in the original artifact, not duplicated in this text archive.

The new native workflow independently fetches both exact public source commits, downloads that same pinned original artifact, verifies it, builds the original three x86_64 executables with Rust 1.95.0 and original dependency identities, and explicitly launches the OS guest. It preserves actual success or failure artifacts. Missing or expired original evidence fails; it is never substituted with a fabricated receipt.

Until that workflow actually succeeds, original-owner native lifecycle remains unqualified. A successful no-turn lifecycle still does not close production issuer deployment, final exec role admission, same-guest persistent writer recovery/retirement, full resource accounting, autonomous recovery, Asterinas graphical desktop, or physical devices. See the [development and technical guide](../../../tests/workloads/hepta_agentd_runtime/README.md).

## Prerequisite #245 verification

The [A06 independent replay](review-inputs/pr245-a06-independent-review.json) and [G1-d independent replay](review-inputs/pr245-g1d-independent-review.json) retain the original final-head artifacts and exact source identities. #245 merged at 2026-10-23 05:42:28 UTC as 39c1d84ebf854958f5829c0118b0c8b92a6b4926 with the reviewed source tree unchanged. The final old-root counterfactual is a privilege-boundary negative, not a rerun of the earlier thread/zombie/SysTree semantic mutants.
