# Canonical source preparation and original owner build

Desktop fe55fe8e1764f4967bae295311d288d8049b6eae / tree 07cbb5e0187b4355200c2f5e0166228cecf1ecc1, Hepta a39a0871d9601ffccb5e0d95d8f39d54b3a63360 / tree e03f9b3eca364222029298496d3e4f1f5e1bf5de.

The first shared clone failed its clean-source gate. A subsequent write-tree check exposed excessive alternates nesting; it wrote no tracked files. Flattening only that new clone's alternate list recovered the two required trees. A full-history repack then failed on an object absent from either build-input tree. All three failures remain failures.

The replacement source snapshot preserves the original canonical commit and both complete build-input tree/blob closures. It explicitly declares depth 1, owns its non-thin pack, has no alternates, and passes pack integrity, connectivity, 12,345 object checks, all 11,726 tracked files (399,674,910 bytes), and the original 118-file source gate. It is not a complete-history repair. The 179,885,509-byte pack is not copied into this small archive.

The original Rust 1.96 / a39 owner built and packaged with its unchanged release/default-feature profile, locked/offline, reusing the existing exclusive target cache. Its 20,138,584-byte SHA256 6ce96a0785b2cbb51bb71fabb2973c1e04d93e213d56694b42b4d717ed55a454 passes only the separate exact-owner image descriptor. The old 8/16 MiB gate remains failed. This is a warm-cache build, not a cold-build claim.

The first kernel-pipeline attempt then exited 1 before starting OSDK. The original successful packaging script emitted an empty log; the source-owned input reader rejected zero bytes. The original zero-byte log is preserved, not filled or rewritten. The three-file candidate 309cde3ae07d7ee4f632ebe98283381c323e8551 (parent fe55) permits only this named packaging log in owner admission and its retention path. Its 50 ordinary and 17 optimized host checks, including a normal quiet child and exact empty-log readback, passed. These local candidate checks are not a canonical successor build.

Kernel compilation, actual 204-package locked graph, native execution, durable original-writer effects, whole-guest peak and global reserve are unverified. No fixture or simulated owner substitutes for the original executable. The archive retains complete small raw remote files/logs without whitespace changes; local operational scripts and local analyses are separately labeled in the index. Three larger source-diagnostic/inventory files remain on main with exact byte lengths and hashes in remote_only.
