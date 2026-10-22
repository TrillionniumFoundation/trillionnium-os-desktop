# Qualified OS merge and native execution evidence — 2026-10-22

This packet retains complete decoded GitHub job logs and the exact pre-merge
checks, resolved review state, ordinary merge results, parents and final trees.
It adds evidence only to main `3f338ca9bb32003b293e641aa17c02488521340e`.

## Qualified merges

| PR | Exact tested head | Ordinary merge | Checks |
| --- | --- | --- | --- |
| #235 | `2ceeb4dd3ce39a136208a7212130a72d31c84766` | `14fca98d006e725098bc29002424c3274c7c64c3` | 2 successful |
| #228 | `2dad28e630f9cbd0715bec885bc28df97a52c6c0` | `a8459afda16e24dfe48c4aa9b3c73442ca17b3d7` | 2 successful |
| #230 | `0be0e42c938b1184166d6b691c5924bf72e02dfc` | `3f338ca9bb32003b293e641aa17c02488521340e` | 3 successful |

#235 preserves the original ExFAT and CPU-delivery evidence. Its independent
carrier verification is included; the historical large ZIP was not downloaded
again. #228 closes three review findings by qualifying runner-routing and
trusted-ref claims and checking actual decoded result lines. Its original
eleven evidence inputs remain unchanged. #230 repairs subprocess fixtures while
retaining the original assertions; its fresh exact-head A06 job succeeded.

## Native logs retained here

| Job | Original run | Exact source | Scope |
| --- | --- | --- | --- |
| 119605475886 | 39712071275 | `0be0e42c938b1184166d6b691c5924bf72e02dfc` | Original A06 kernel/QEMU, permission, SCM_RIGHTS, RLIMIT, CPU/SMP and ExFAT gate |
| 119605754101 | 39712124119 | `10c61be18b7478869a0f33ed39d5d84e6b5a2be7` | Original A10 Rust 1.88, headless Weston lifecycle and Clippy gate |
| 119605646906 | 39712123876 | `10c61be18b7478869a0f33ed39d5d84e6b5a2be7` | Original pinned Agentd and continuous read-only Session/objective gate |

The A10 raw log contains 307 passing Rust result occurrences, zero failed
occurrences and two existing ignored occurrences. Some suites run more than
once, so this is not a count of unique tests. The complete logs and native job
step metadata are preserved, including the original upload finalization lines.
Fresh artifact ZIP contents and their independently computed hashes are not
claimed by this packet; no fresh ZIP was downloaded while packaging it.

The original Agentd job checks out the desktop source above and separately pins
Hepta `f8c9419df6ddeb36ff8b522a50219981fb8d9345`. It does not qualify later Hepta
recovery commits, the new Notes bootstrap receiver, or production owner assembly.

## Integrity and limits

`manifest.json` records the archive SHA-256 and every uncompressed member's byte
length and SHA-256. The three decoded logs were compared byte-for-byte with their
original connector responses and lossless gzip carriers before packaging. Every
archive member was reopened and compared byte-for-byte after compression. The
pre-merge checks were verified against each exact PR head, and the three merge
parent pairs form the recorded ordinary sequence ending at main `3f338ca9`.

Extract `native-logs-and-merge-receipts.tar.xz` to inspect `jobs/`, `merges/` and
`receipts/`. Paths under `compressed_path` in the original summary receipt refer
to the acquisition workspace; the canonical retained decoded paths are the
`native_jobs[*].log_path` entries in this packet's manifest.

PR #210 remains draft pending real owner assembly. G1D's frozen trusted-image
qualification is distinct from production CapSpace grants and SQLite/business
durability. Physical desktop and device gates also remain open. Packaging this
packet reran no Rust, kernel, GUI or device tests and creates no new authority.
