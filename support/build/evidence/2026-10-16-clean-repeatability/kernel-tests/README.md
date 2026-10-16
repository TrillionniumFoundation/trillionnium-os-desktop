# Full upstream kernel tests

The actual public ktest entry completed at published source [`5bcec614`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/5bcec614c1a075782b6ffaa5a5212fdee29be37d), tree `00e70e58dfa0dbf4718db55240136683f0a23310`, with outer exit **0**. [Invocation](readable/observer/invocation.json), [source binding](source-binding.json), [publisher receipt](publication-receipt.json), and [outer-completion supplement](outer-completion.posthoc.json) retain the source, environment and actual completion evidence.

| Actual guest | Upstream reported passes | Soft skips | Exercised lower bound | Raw QEMU exit |
| --- | ---: | ---: | ---: | ---: |
| OSTD | 221 | 3 | 218 | 33 |
| aster-core | 141 | 0 | 141 | 33 |
| Total | 362 | 3 | 359 | 33 for each guest |

Both guests had zero failures and filters, no timeout, a nonempty serial hash matching its QEMU record, and the final upstream completion marker. The three OSTD cases report VMX/EPT unavailable and are retained as soft skips; TCG does not establish those hardware paths. [Counts and ten actual command receipts](counts.json) and the original [runner result](readable/run/result.json) preserve the distinction. Expected-panic upstream tests remain valid. This fixed upstream regression is not A06 quota acceptance or a native HOS2 control result.

**This invocation reused target B's cache from the preceding clean A/B builds. It was not an empty-target build.** The runtime used fixed `nightly-2026-07-21`, offline dependencies and two Cargo jobs, installed the source-built OSDK with `--locked`, then ran the release OSTD and aster-core tests. The two generated locks match their exact selected input locks. Source verification checked 118 configured inputs and reports `pristine:false` for the intentional downstream derivation; no whole-tree pristine claim is made. Historical before/after Git status retains an untracked `kernel/asterinas/kernel/OSDK.toml`; its bytes were not copied, removed or changed during this archive.

The actual command from the project root was:

```sh
python3 -I support/build/ktest/run.py --output <fresh-owned-output-directory>
```

Use the [recorded invocation environment](readable/observer/invocation.json) and [runner environment](readable/run/environment.json) for a replay; every subprocess's original arguments, cwd, raw/effective exit and leader cleanup remain in [raw.tar.gz](raw.tar.gz), with stable relative member names and SHA256 in [members.json](members.json). That archive includes all 31 output files, the actual console/controller/receipt, publisher proof, eighteen source/lock inputs checked against runtime hashes, and post-run upstream-lock metadata. [Readable index](readable-index.json) provides direct access to important JSON, QEMU commands and generated locks. Original absolute execution paths are preserved as facts, while these relative archive locations remain usable.

[Artifact manifest](artifacts/manifest.json) records **fresh snapshots from this invocation's actual two `-kernel` paths**. [OSTD ELF gzip](artifacts/ostd.elf.gz) and [aster-core ELF gzip](artifacts/aster-core.elf.gz) were checked against recorded SHA256/size, stable retained-FD identity during capture, and the source path's bytes/inode afterward; each compressed copy was decompressed and verified. No prior artifact was substituted, and no compiler target tree or tool binary is included. Raw serial bytes were checked before and inside the atomic archive.

Packaging wrote only this evidence directory and ran no new VM, Cargo, Git command or kernel build. [Archive validation](archive-validation.json) records the integrity checks; [SHA256SUMS](SHA256SUMS) covers every other evidence file.
