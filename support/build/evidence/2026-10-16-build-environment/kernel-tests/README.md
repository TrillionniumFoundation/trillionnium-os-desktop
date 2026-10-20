# Full upstream kernel tests

Actual source [`ff040c6d`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/ff040c6d5afbc4e26a249022093b8090181f6176), tree `eb16c5ef5fe8adf3a9249e19a7674cec7b2e359f`, completed the public kernel-test entry with outer exit **0**. [Source binding](source-binding.json), [publisher receipt](publication-receipt.json), [invocation](readable/observer/invocation.json), [environment](readable/run/environment.json), and [outer-completion supplement](outer-completion.posthoc.json) retain their original evidence.

| Actual guest | Reported passes | Soft skips | Exercised lower bound | Raw QEMU exit |
| --- | ---: | ---: | ---: | ---: |
| OSTD | 221 | 3 | 218 | 33 |
| aster-core | 141 | 0 | 141 | 33 |

Both guests had zero failures and filters, no timeout, unique test starts matching the upstream summary, nonempty raw serial matching its QEMU-record hash, and the final upstream completion marker. Soft skips are counted separately in [counts](counts.json); TCG cannot establish skipped VMX/EPT hardware paths. Expected-panic upstream tests remain valid. No A06 quota or native HOS2 control acceptance is claimed.

**This ktest run reused the normal build/boot target cache from this phase. It was not an empty-target build.** Runtime used fixed `nightly-2026-07-21`, offline dependencies and two Cargo jobs. OSDK was installed from the fixed downstream source with `--locked`; both generated test locks match the selected fixed input locks. Source verifier output remains original, including its intentional downstream `pristine:false` status, without claiming full-tree pristine verification. The invocation records empty Git status before and after the run. No unrelated generated manifest was read, copied, deleted or changed for packaging.

Replay the project entry `python3 -I support/build/ktest/run.py --output <fresh-owned-output>` using the recorded invocation environment. [Raw archive](raw.tar.gz) retains all completed output files, exact ten subprocess command receipts, the real controller/console/entry receipt, publisher proof, runtime-hash-matching source/lock inputs and post-run upstream-lock metadata. [Member index](members.json) and [readable index](readable-index.json) provide stable relative archive locations; absolute original paths remain historical facts.

[Artifact manifest](artifacts/manifest.json), [OSTD ELF gzip](artifacts/ostd.elf.gz) and [aster-core ELF gzip](artifacts/aster-core.elf.gz) retain fresh snapshots from this invocation’s actual QEMU-record `-kernel` paths. Retained-FD fstat identity, recorded size/SHA, source bytes/inode after capture, and gzip decompression were checked. No earlier artifact was substituted, and no target tree or tool binary is copied.

Packaging wrote only this evidence directory and started no new Cargo, VM, Git command, kernel build or test. [Archive validation](archive-validation.json) records integrity checks. [SHA256SUMS](SHA256SUMS) is generated after final review and covers every other evidence file.

Two archive-only parser attempts failed before creating evidence: a required literal space after `test NAME ...` omitted seven OSTD and one core start where the test immediately logged INFO/DEBUG/ERROR. An initial non-line-start hypothesis was disproved. The final parser keeps the exact line-start test-name/ellipsis tokens while allowing that immediate output; all 221/141 unique starts match the original summaries. [Preserved attempt records](provenance/attempts.posthoc.json), [controller/correction archive](provenance/packaging.tar.gz), and [its member hashes](provenance/members.json) retain both failures and the successful packaging retry. No actual tests were rerun and no raw serial, runner result or production assertion changed.
