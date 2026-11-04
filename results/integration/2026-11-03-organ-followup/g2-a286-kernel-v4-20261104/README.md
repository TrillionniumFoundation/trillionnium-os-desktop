# a286 original kernel v4 — complete build passed

The original build completed on Desktop `a286e0f922bf8e439e8951ae1538abeac0b26477` and Hepta `a39a0871d9601ffccb5e0d95d8f39d54b3a63360`.

The [original pipeline](pipeline.json), [complete kernel log](g2-kernel.log), [OSDK log](osdk-build.log), [source inputs](kernel-build/source-inputs.json), [204-package generated lock](kernel-build/generated.Cargo.lock) and [authoritative status](process-status.json) are exact copies. OSDK exited 0 in 0.352 seconds; the original kernel command exited 0 in 173.759 seconds. Its original validator and unchanged-source checks passed. The kernel is 28,908,256 bytes, SHA256 `08b13737c465aabbebc8d14ce1ccf4da220e59c7c22756a010c8f00baa91d838`. The fixed nightly, original wrapper, source gates and size limit were not relaxed.

The [independent review](independent-review.json) records immutable operation and payload identities. The [index](evidence-index.json) distinguishes exact original bytes from reviewer-serialized transport responses. The large ELF and full source inventories remain on main; root verified their receipt identities, not a new download.

The [v3 failure](../g2-a286-kernel-v3-20261104/README.md) remains failed. This build does not grant native execution, lost-reply deduplication, G2 completion, whole-process-tree memory bounds or production qualification. The [first native attempt](../g2-a286-native-preflight-v1-20261104/README.md) stopped before QEMU.
