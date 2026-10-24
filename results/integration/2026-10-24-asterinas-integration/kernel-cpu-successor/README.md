# Retained CPU successor core execution

The actual execution belongs to OS `f6e837c60b1fa65da4118535a3013e4b38c6ec98` and tree `ccaa945c9b7c64471171b83ea46ba5cef315c68b`. The original
pipeline took 385.412 seconds. This archive reads the
original result files, complete source snapshots, QEMU records and retained
binary copies. It runs no test, compiler, kernel or Hepta owner.
The [publication](publication.json) records exact SHA-256 values and sizes.

| Actual execution in this pipeline | Result |
| --- | --- |
| Exact-source OSDK build | Retained SHA `ebb6be251d96a029c11b805e093f14e9965c1e2d65f23849acac6ef06f059464` |
| Ordinary complete aster-core | 373 passed; 134 required names; no failed, filtered or soft-skipped tests |
| G2 complete aster-core | 376 passed: complete ordinary 373 plus original Root3; no failed, filtered or soft-skipped tests |
| Successful raw QEMU exits | 33 for each suite |
| CPU successor prepare/commit tests | Five mandatory names, individually exercised in both suites |

The five CPU-layer regressions cover preparation/drop without publishing authority,
both exact predecessor delegations being closed, preserving CPU debt/revision and
original delivery history, failed/stale commit retaining the current policy, and
bounded origins/watchdog registration across generations. The preceding three
CPU-owner continuity tests and the original 126 required names remain mandatory.
Each CPU-owner/successor/Root test requires its own terminal result before the
summary and cannot be accepted through a soft skip.

The exact 799744-byte G2 input has SHA `178f67705b0bd4450733e92eaed5a5febd2e4d7279d071660e64a8819409d2ec`. It is only a frozen
compilation input. The original Hepta production daemon, writer and FinalUse
owners are not executed in this pipeline.

This run does not execute allocator, MLSDisk, OSTD, ordinary product QueryAbi,
the socket guest or the six watchdog boots. Their prior complete same-source
execution remains in the [824720ea archive](../kernel-owner-continuity/publication.json).
That historical evidence is preserved and is not relabeled for this source.

The subsequently added Process successor/launcher tests, the final watchdog
receipt owner-cut and exact Root acknowledgement are outside this run. It also
does not qualify a production Hepta control/recovery cycle, lost reply or crash
after effect, cross-boot Unknown preservation, 300-second grant renewal, repeated
production recovery, long-term persistent CPU control, SMP, physical media or
production readiness. Native-owner and durable-G2 flags remain false.

All text and JSON retain their original bytes. Every `.log` is directly gzip
compressed; its decompressed SHA and byte count must reproduce the original,
including CRLF and empty logs. Larger text records may also be gzip compressed.
Binary ELF/BIOS/OSDK copies stay at their actual retained locations; only their
verified SHA/size manifest enters Git. Original Cargo-target paths in QEMU argv
are not read or rewritten. Auxiliary extracted summaries are not used in place
of the original complete `result.json` files.
