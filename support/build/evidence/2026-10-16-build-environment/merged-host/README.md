# Merged-main host ABI verification — partial result

The original 13-file frozen package is retained byte for byte in
`original-package/`, including its original README, reports, two tar archives
and SHA256SUMS (`bce5ae22f52526db83dc34d1e80faab31845133367700047f17172a822b2fcc7`).
The outer checksum list also covers these review/publication records.

Tested local merge `b1a15d9afc456346410af658d2164ee5fa085656` and published
remote `74ee9b3d62dc85f272681c5caed3a9c328e38539` share exact tree
`73b34b91910852917d4c6bea020c8b4dc1e62e10`. Local tree, ordered parents,
all 20 source bytes/blob IDs/Git modes and the seed lock were independently
checked through immutable Git objects. Remote binding comes from the unaltered
saved publisher API receipt; this archival pass made no new network lookup.

Rust 39, Python 28, fmt and 12 HOS2 + 1 transport golden checks passed.
**The overall result remains partial.** Initial Clippy/controller exit1
reported its missing fixed-nightly component. Installing that component exited
0 without replacing the toolchain. The identical all-target `-D warnings`
retry exited101 with two `chunks_exact_to_as_chunks` errors in test helpers
`mutation_kill.rs:21` and `transport_vectors.rs:14`. Both red logs, the original
initial `success=false` report and retry receipt remain intact. No source or
lint suppression was applied by the archive/review agents.

The 17 raw archive members were independently read and checked for unique
regular paths, byte counts and SHA. The source archive contains 20 regular
files and eight directories. Git modes are 100644/100755; the original tar
permissions are 0664/0775. File types and execute bits match, while group-write
bits differ. Both mode values are recorded in source-mode-comparison.json;
the original archive was not normalized or rewritten.

These are saved host ABI codec/test results, not a kernel-device, ioctl
memory-safety, authorization, CapSpace or CPU-throttling result. The source
mutation matrix was not run this phase. No new test/probe/build/VM was run
for this review, and no live target/generated manifest or production source
was read. Only this evidence subdirectory was written.
