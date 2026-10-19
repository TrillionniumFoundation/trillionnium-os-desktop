# R10 owner CI security diagnosis evidence

This package records the fixed `d32e795f0d24df89fc57745f6fae70fbd0642eba` owner CI observation and a separate, authorized local cargo-deny diagnosis. It is evidence for a future security migration; it does not change dependencies or grant a merge exception.

## Read first

- [中文技术报告](deny-repro-01/SECURITY_DEBT_DIAGNOSIS.md)
- [English technical report](deny-repro-01/SECURITY_DEBT_DIAGNOSIS.en.md)
- [Final exact-head CI status](final-status.json), observed 19 October 2026 at 01:56:31–32 UTC
- [Actual local execution receipt](deny-repro-01/execution.json)
- [All thirteen advisory errors](deny-repro-01/error-summary.json)
- [Two-architecture Agentd reachability](deny-repro-01/agentd-reachability.json)
- [Preservation and lossless log compression](deny-repro-01/preservation.json)
- [Additional upstream provenance](deny-repro-01/preservation-supplement.json)
- [Exclusions](exclusions.json)

The remote cargo-deny job failed, but its original log could not be retrieved. The local run independently produced thirteen errors: eight vulnerability records and five unmaintained records. Architecture required succeeded at 01:53:09 UTC; blocking-ci remained in progress with cargo-deny failing and CI required not yet present. The pull request remained open, unmerged and blocked under its normal checks. Do not label this observation as the final result of all CI jobs.

## Package layout and verification

The delivery contains a strict `files-manifest.json`, `raw-evidence.tar.xz`, primary copies using the same relative paths, and an external `artifact-manifest.json`. The archive contains `files-manifest.json` followed by every listed evidence file, in sorted order. Each entry is a regular file with an exact byte count and SHA-256. No unlisted archive entry is permitted. The archive and all primary copies are verified against the same manifest before an atomic directory rename makes the package available.

The primary copies are convenient entry points. To inspect all linked raw material, extract the archive into a new review directory: its paths match the manifest and report links. The uncompressed cargo-deny log is intentionally represented by `deny-repro-01/cargo-deny.log.xz`; `preservation.json` binds the original bytes and the verified lossless copy. The complete 13,717,460-byte raw local log also remains in the diagnostic working evidence directory. No failed-access response or failed diagnostic outcome was removed. `execution-progress.json` is an intermediate receipt; the completed result is `execution.json`.

The source and tool roots, full caches, private credentials, product binaries and compiler objects are not included. Selected public crate archives and the exact public rusqlite sparse-index bytes are deliberate source evidence, separately identified in the exclusion policy. The RustSec database is bound by commit/tree and its thirteen failing advisory source files; this package does not contain the whole database clone. Tool download receipts and hashes bind the official releases; installed tool binaries are not duplicated.

`package-security-evidence.py` is the packaging implementation copied beside the artifact manifest. It does not execute cargo, compile products, access credential stores, contact GitHub, or mutate a checkout. Its validation covers package identity, ordered members, sizes, SHA-256, primary-copy equality, lossless-log identity and unchanged source state. The manifest and artifacts describe observed execution, not proposed remediation as completed work.

