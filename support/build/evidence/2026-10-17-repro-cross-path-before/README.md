# A2/B2 same-host complete-input comparison: failed

Both actual cold source builds and real Rust-kernel boots passed. Their **complete kernel ELF bytes differ**, so cross-path byte reproduction failed. The original comparison command returned 1 with final exception line `ValueError: actual boot input bytes differ`. This phase preserves that failure without rerunning the comparison script, any live check, build or VM. A2's published evidence remains unchanged; B2 is preserved independently.

| Actual loaded input | A2 | B2 | Complete bytes equal |
| --- | --- | --- | --- |
| Kernel ELF | 8,293,608 bytes; `e89063b19e5895aa64695ba27c04d7d53fd5d65e23adeb0aab06983a1a33794d` | 8,292,192 bytes; `b5fda2500d15c250d022f81bf2d30c0778244faea021a5db34aa68665d68f763` | **No** |
| Initramfs | 1,107,990 bytes; `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` | Same exact bytes and hash | Yes |
| BIOS | 262,144 bytes; `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735` | Same exact bytes and hash | Yes |

The B2 ELF is 1,416 bytes smaller. The first differing byte is offset 40 (ELF section-header table offset). Several section payloads, including `.text`, `.rodata`, `.data`, symbol and unwind data, also differ. `diagnosis/elf.json` records section layout/content hashes. Neither ELF contains either real A2/B2 source-root string; the shared virtual-root string is present. These observations do not establish the remaining nondeterminism's cause.

Both runs used producer `bdf7a08dcc0980fa85c0ba5abdf365b7d2c42e80`, complete tree `eff51eb940d1f415aedb84555752ecbc97d58faa`, derived kernel tree `6b3cab110aa6d30d5b89f99c4389c9c3e01022da`, fixed Asterinas v0.19.0 commit `c4b7ed575b7b32773475b194d2ad41fb6d03765b` and nightly `nightly-2026-07-21`. Their real source roots differ, while virtual root, profile-code hashes, Components hash and actual host match. All six mapped Cargo metadata payloads match between cases by call order; their original metadata differs because it records distinct real roots. The two serial payloads differ, while both contain every acceptance marker and recorded raw QEMU 33 without timeout.

## Original failure provenance

The original command was:

```sh
python3 compare-normalized-cloud.py
```

Its cwd was `/workspace/scratch/ae1a8cf05419`, shell `/bin/bash`, login false. Root supplied the actual tool-result exit 1 and the final exception line from its retained summary. **No independent raw exception log or complete traceback was retained**, and none is reconstructed. That distinction is explicit in `root-observation.json`.

The exact comparator script SHA256 is `5566d3648f6ffff15cb84cb2e1be280899983109b38eb1024873d1f1aae594e6`. The existing comparison directory contains only two 84-byte logs, `A2-live-recheck.log` and `B2-live-recheck.log`. Both record the actual fresh live-artifact boot check success. No `result.json` was generated because the final equality guard raised. Those two successful live checks establish valid per-case boot evidence, not equal kernel bytes. The script and both logs are preserved verbatim.

`diagnosis/inputs.json` is a **new read-only calculation from retained snapshots**, explicitly separate from the historical failed command. It lists all three complete input comparisons and the equal/different contextual inputs. No new comparison execution overwrote the original directory.

## Complete reversible evidence

This self-contained package combines all original A2/B2 evidence, shared v2 profile inputs/controller, the original comparison script and its two logs: 116 unique files. Seven identical shared original paths are deduplicated. There are 108 nonbinary tar members and eight binary logical paths represented by four unique binary payloads (two ELF files plus shared initramfs and BIOS). Every stored archive/binary chunk is at most 2 MiB, and each exact input can be reconstructed.

| Preserved evidence | Storage |
| --- | --- |
| All original per-case logs, commands/env, full serial/QEMU, metadata original/mapped pairs, rustc incoming/effective argv, pre/post source and live checks | Deterministic `raw.tar.gz` and `raw.manifest.json` |
| Original read receipts and frozen package bindings | `inputs/`, `capture.json` |
| Exact binary input bytes, deduplicated and chunked | `artifacts/manifest.json`, `artifacts/` |
| Shared 86 exact producer controls and 30 Git tree objects | `source/`, `source-binding.json` |
| Full significant serial, QEMU/policy/result/commands, original comparator and both comparison logs | `readable/`, bound by its manifest |
| Failed command attribution, scope and exact differences | `root-observation.json`, `report.json`, `diagnosis/` |

This is the explicit same-host v2 opt-in profile with synthetic embedded builder `a01-repro@a01-fixed-profile`. Actual cloud host `343e40cfefc1`, user root and uid 0 remain separate provenance. Both per-case cold-target and unchanged-custody receipts are retained. Cross-host or immutable-host reproduction is not accepted. No original target, worktree or already-published phase was modified, cleaned or deleted.

## Offline verification and reconstruction

```sh
python3 -I support/build/evidence/2026-10-17-repro-cross-path-before/verify.py
python3 -I -O support/build/evidence/2026-10-17-repro-cross-path-before/verify.py
```

A successful verifier means the **failed-comparison evidence is intact**. It verifies complete hashes/inventory, safe tar members, chunk/gzip reconstruction, exact Git commit/tree/path/blob identity, both recorded boot outcomes, all original argv/metadata inputs, original failure attribution and the expected ELF inequality. It requires neither network nor Git executable and invokes no original comparator, build, host suite, live check or VM. Sibling evidence packages are not required to verify this package.

```sh
python3 -I support/build/evidence/2026-10-17-repro-cross-path-before/verify.py --restore /absolute/new-directory
```

Optional reconstruction writes fresh verified original files and selected source controls, never executing them. Historical identities, permissions and host dependencies are not recreated.
