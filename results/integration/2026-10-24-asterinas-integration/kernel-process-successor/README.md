# Retained Process successor core execution

The actual execution belongs to OS `39c1eaf89a211b91e5e687ceaf86fd033567e536` and tree `41afddf4360f18ad50d62f9647de6f2e4f602a0e`. The original
pipeline took 455.040 seconds. This archive reads the
original complete result files, source snapshots, QEMU records and retained
binary copies. It runs no test, compiler, kernel or Hepta owner.
The [publication](publication.json) records exact SHA-256 values and sizes.

| Actual execution in this pipeline | Result |
| --- | --- |
| Exact-source OSDK build | Retained SHA `017fa8958ef2d4850ad99ff4a2f507331ff49a2de212fa5f769feebc3816c0f7` |
| Ordinary complete aster-core | 373 passed; 134 required names; no failed, filtered or soft-skipped tests |
| G2 complete aster-core | 387 passed: complete ordinary 373 plus original Root3 and successor11; no failed, filtered or soft-skipped tests |
| Successful raw QEMU exits | 33 for each suite |
| Original CPU continuity and successor tests | Three continuity and five prepare/commit names individually exercised in both suites |
| G2 Process, original history and final owner-cut tests | Eleven mandatory names, individually exercised with the original Root3 |

The seven launcher regressions exercise sealed-image preparation and cancellation,
actual child-allocation release, immutable generation replay and exact-generation
ACK admission, a fresh history-only local space without effect handles, refusal
for ordinary/ended images, and failed allocation without publication. Three
history regressions retain both original frontiers, reject empty lost history as
retirement proof, and preserve original owners without a fresh effect namespace.
The final CPU-owner test forces an actual watchdog effect between prepare and
commit and compares its immutable original receipt across the final owner cut.
All fourteen G2 additions, the previous three CPU-continuity tests and the five
CPU-successor tests require their own terminal result before the suite summary.
The exact original 134-name required core inventory remains mandatory.

The exact 799744-byte G2 input has SHA `178f67705b0bd4450733e92eaed5a5febd2e4d7279d071660e64a8819409d2ec`. It is only a frozen
compilation input. The original Hepta production daemon, writer and FinalUse
owners are not executed in this pipeline. Kernel ACK gate coverage does not prove
that Root durably saved its original retirement record before acknowledgement.
The complete native launcher/ioctl and pidfd/Supervisor lifecycle needs separate
actual userspace acceptance on its final source.

This run does not execute allocator, MLSDisk, OSTD, ordinary product QueryAbi,
the socket guest or the six watchdog boots. Their prior complete same-source
execution remains in the [824720ea archive](../kernel-owner-continuity/publication.json).
The earlier [f6e837c6 two-core archive](../kernel-cpu-successor/publication.json)
also retains its original identity. Neither historical execution is relabeled
for this source or reproduced by this archive.

A production Hepta control/recovery cycle, lost reply or crash after effect,
cross-boot Unknown preservation, 300-second grant renewal, repeated production
recovery, long-term persistent CPU control, power loss, SMP, physical media and
production readiness remain outside this evidence. Native-owner, durable-G2,
actual-native-entry and production flags remain false.

All text and JSON retain their original bytes. Every `.log` is directly gzip
compressed; its decompressed SHA and byte count must reproduce the original,
including CRLF and empty logs. Larger text records may also be gzip compressed.
Binary ELF/BIOS/OSDK copies stay at their actual retained locations; only their
verified SHA/size manifest enters Git. Original Cargo-target paths in QEMU argv
are not read or rewritten. Auxiliary extracted summaries are not used in place
of the original complete `result.json` files.
