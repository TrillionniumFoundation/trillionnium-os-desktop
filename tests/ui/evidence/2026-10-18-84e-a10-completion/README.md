# 84e A10 CI completion — appended on 2026-10-18

This directory records the completed A10 run for **`84e08165d2e753fe1fc780e1972dbab4317e8499`**, tree `e55a0e15e01f55f98f0a9213e67d2a5792776764`. It supplements the earlier queued snapshots preserved in the [R6 index](../../../integration/hepta/evidence/2026-10-17-r6/README.md); those historical snapshots are unchanged.

The [GitHub run 39075838432](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39075838432) finished successfully at **2026-10-17 23:44:03 UTC**. Its native job `117526652552` ran from **23:41:21 to 23:44:02 UTC**. The separate source-guard job `117522687664` also succeeded. The raw API job and artifact records, the exact workflow source, and the complete native job log are retained here.

## Actual results at this exact head

| Executed group | Actual result |
| --- | --- |
| Rust UI workspace | 87 passed; 2 real-host-font/CJK tests ignored |
| Rust Hepta observer | 17 passed |
| Rust `support/ui` | 39 passed |
| Rust `tests/ui` | 8 passed |
| **Rust total** | **151 passed / 0 failed / 2 ignored** |
| Python original-process guard | 6 passed |
| Strict UI workspace/all-target Clippy, rustfmt, locked dependency checks | All job steps succeeded |
| Headless Weston client/session and compositor-restart smoke | Passed for the scopes reported by the raw logs |
| Session and Hepta-page observation | Passed using explicitly marked scripted UDS fixtures |

The six new freshness Rust regressions are included in the 151-test total. This workflow **does not yet contain** the later eight Python original-Shell capture-contract tests. Their exact local execution belongs to the [separate CI-hook evidence](../2026-10-17-original-shell-ci/README.md), and cannot be assigned to this 84e run.

The fixture receipts explicitly state `upstream_agentd_started=false`, `objective_submitted=false`, and `device_effect_tested=false`. The Hepta layout receipt also states `compositor_pixel_presentation_verified=false`. This CI exercises actual Rust clients and Session against fixtures; it is not an original-Agentd six-stage window run. The separately executed [original Shell captures](../2026-10-17-original-hepta-shell/README.md) retain their own sources, processes, pixels, and reviews.

## Downloaded artifact and byte checks

GitHub artifact `12118458392`, `a10-host-evidence`, was downloaded read-only. Its **17,399,599-byte** ZIP matches GitHub's published SHA256:

`310db3e6e60fe3823d2e5259136dcfdb074ea7d6cb330df6207548186a28445d`

Every ZIP member was read and hashed. The enclosed binary tarball matches its packaged checksum. Its four executable members were streamed through SHA256 and ELF-header checks; all are little-endian ELF64, machine 62 (x86-64), mode 0755. They were neither extracted to executable files nor run.

| Packaged ELF | Bytes | SHA256 |
| --- | ---: | --- |
| `trill-shell` | 25,818,184 | `1fa611c2bbd7ae9192961cf57400044efaee06fb4c110429565ca0f0d70f670e` |
| `trill-session` | 3,731,784 | `3bd9afb37cd26749ee4afe3971910db529cd6fefa6034abd60991c11e608a199` |
| `trill-app-window` | 24,173,728 | `dcb9952f00767a6be3ef872a47564a1520e1852bd197af2fc0ddd79096f457d5` |
| `trill-ctl` | 1,552,896 | `c3c0ffcc4bd425f0a4596a8b8a6ae6e3179edf7bc568e08c6a22401065f8b859` |

The packager copies then applies `strip --strip-debug`. Runtime fixture receipts therefore report different, pre-packaging hashes: Session `6a4090c0ca92a4b06457ca8363e638c3959075860831ac1299641e2e1a1f5c9e`, Shell `92bc75901010136045c390e319dbec177a6b21c7add0c8639cf7a504fb41164c`. The archive keeps these identities separate. The downloadable ZIP and ELF/tar bytes are omitted from Git; [artifact-members.json](artifact-members.json), [verification.json](verification.json), and [package metadata](package-metadata) preserve the checked sizes, digests, and source provenance.

## Recorded inputs

- [jobs.json](jobs.json), [artifacts.json](artifacts.json), and [runs-84e-snapshot.json](runs-84e-snapshot.json): GitHub API responses retrieved in the 2026-10-18 follow-up.
- [native-job.log.gz](native-job.log.gz): complete decoded job log returned by the GitHub connector. Its BOM and original newlines were preserved and every text chunk compared with the retrieved value before gzip.
- [source-bindings.json](source-bindings.json): exact executed head/tree and Git object identities for the workflow, UI, observer, support, and UI-test source.
- [a10-host.workflow.yml](a10-host.workflow.yml): exact source at 84e, verified against Git blob `37e346cac351e5b9ee55dd559757c2835a1c1484`.
- [artifact](artifact): unchanged small artifact files, including host checks, headless and compositor logs, fixture receipts, guard log, dependency lock, and tar checksum.
- [candidate-89-runs-034523.json](candidate-89-runs-034523.json): at **2026-10-18 03:45:23 UTC**, all three exact-`89aa8fa6` runs remained queued with null conclusion.
- [main-355-runs-034523.json](main-355-runs-034523.json): at the same readback, the four exact-`3551e1e0` main runs remained queued. No current-main kernel or ABI execution success is inferred.

The initially read PR157 and candidate-89 API snapshots are also retained. The review worktree was created from `89aa8fa62d30b00259cb33174260c134edf1a70b`; adding this evidence does not constitute a new compile or test of its eventual evidence commit. Different-head successes are never inherited by a queued run.

`SHA256SUMS` covers every retained file except itself. No compile, test, Agentd, Shell, compositor, or ELF execution was performed to create this completion archive.
