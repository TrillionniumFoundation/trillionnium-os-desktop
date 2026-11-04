# a286 kernel v3: actual compilation, retained metadata failure

Original job `1a1a3ceade8-96a-776b` ended with exit 1, complete output,
no timeout and no cancellation. The source remained exactly Desktop
`a286e0f922bf8e439e8951ae1538abeac0b26477`, tree
`342ad0840d521e97d6de5845682cbc11a115f6f7`, with the original a39 owner
and default-off `g2-original-owner-a39-v1` profile.

The ordinary source-built OSDK installation completed in 0.503 seconds using
its explicitly retained build target. The original `support/build/kernel.sh`
then compiled for 202.642 seconds and reached `aster-core`. Its complete
[31,131-byte log](g2-kernel.log), SHA256
`e0233e883a81ea26c3da79657a496b9db0a8562521652cde2463e5110acc39fe`,
contains three `component::parse_metadata!()` panics at the original
`init.rs` call sites, each reporting `cannot get metadata`. The kernel
command returned 2; the pipeline returned 1. The log does not expose the
underlying metadata command's stderr, so it does not establish that cause.

The [4,618-byte original pipeline](pipeline.json) has SHA256
`5e9c137e8c0d2ae620fa04af59c07383ec8e390e82c6f0a556a124e7aca17d16`.
[Independent review](independent-review.json) checked all three immutable
operation-result pages and their offsets, total length and full payload hash,
then both complete original file texts, versions, sizes and SHA256 values.
The original direct job status is retained separately. Its reported process
log sizes are not represented as a separate process-read capture.

[The index](source-index.json) binds nine original or explicitly derived
files. The earlier [cache and OSDK checkpoint](../g2-a286-read-recovery-evidence-20261103/README.md)
remains unchanged. This attempt proves real compilation reached this failure;
it does not qualify a complete kernel, the actual 204-package graph gate,
guest execution, G2 persistence or global recovery memory. All original false
qualification fields and the legacy 8/16 MiB rejection remain false.
