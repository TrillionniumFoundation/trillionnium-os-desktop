# Archive output custody

The current A01 archive helper now writes evidence and both indexes through pinned directory file descriptors. Child directories use mkdirat/openat without following symlinks; files use `O_CREAT|O_EXCL|O_NOFOLLOW`. Checksums come from the exact written payloads, so index generation does not traverse or reread mutable destination paths. Successful completion verifies the pinned directory chain and written file identities, then removes `.archive-incomplete`.

Failure preserves the new partial custody and its marker. There is no recursive cleanup by pathname. A moved owned directory can retain the partial files at its new location; a replacement occupying the original destination is left untouched. Empty or initially invalid source inputs still do not create a fake bundle. Existing destinations remain untouched.

| Verification | Exact result |
| --- | --- |
| Baseline `01a344c6...` mkdir-boundary child swap | Both Python modes reproduced an archive payload written through a symlink into a disposable outside directory |
| Baseline cleanup-boundary destination swap | Both modes reproduced `rmtree` deleting the foreign replacement directory and its sentinel |
| Targeted baseline red tests | 2 expected failures per mode, 4 total |
| Final archive suite | 28/28 passed with `python -I`; 28/28 with `python -I -O`; 56 test-method executions |
| Preserved source protections | All20 original scenarios retained; `read_regular` and `source_files` ASTs unchanged, including no-follow rooted traversal, hardlink rejection and size limits |
| Historical full-run and coverage archive compatibility | attempt07 (320 payloads) and attempt10 (40 payloads), each rebuilt in both modes: 4/4 CLI calls passed, 720 payload-byte comparisons equal, schema1 entry records equal, all4 checksum checks exit0 |
| Additional independent review probes | Previously observed12 successes +12 partial failures left FD count4→4; these probes are separate from the56 test-method executions |

Eight new methods cover the two reproduced races, child/root replacement after the directory FD is open, a racing pre-existing output file, a malicious manifest symlink, index generation without pathname walks/reads, and a symlink destination parent. The old duplicate-input and total-limit scenarios now assert retained owned bytes and `.archive-incomplete`, matching the requested failure-retention policy. The reserved-index scenario also rejects the incomplete-marker namespace.

The historical compatibility check restores original payload bytes from existing archive manifests, verifies their recorded source hashes, and compares the new stored gzip/plain bytes against the original Git-bound archives. Original historical files remain unchanged. Only the top-level manifest source path naturally names the reconstruction directory. This is rearchival compatibility evidence and does not rerun or upgrade the historical guest results.

The trusted-parent boundary remains explicit. Protection against root or child replacement is established **after its directory FD is opened**. A same-user writer replacing a newly created directory with a different real directory before the first stat/open can cross that initial-capture boundary; the independent review observed this case. This helper is not a sandbox against such writers or an atomic snapshot of an entire concurrently changing run. The report does not claim every possible directory swap is rejected.

The targeted change follows the two output/failure findings in A00 PR32 at `a8d51bc2...`; its older16-test implementation was not imported wholesale. Only `archive.py`, its existing `test_archive.py`, and the corresponding README changed. Kernel, OSTD, production OSDK, other-owner code and old evidence were not modified by this task.

Baseline/fixed source snapshots and `archive-custody.patch` are included. `raw.tar.gz` retains the red/green commands, selected environment, source hashes, original console output, disposable race fixtures, historical compatibility controller/results/indexes, and independent review notes. `archive-manifest.json` records every regular member by size and SHA256. Fixture symlinks are recorded as metadata and are not dereferenced. Duplicate historical payload trees and Python bytecode are excluded. Independent review output is labeled as a transcription of observed tool output, rather than an invented raw process log.

This phase is pure host Python and filesystem validation: **no new VM, kernel build, GDB or Cargo execution**.
