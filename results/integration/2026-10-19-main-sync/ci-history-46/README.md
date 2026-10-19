# PR193 actual original-owner Objective history CI

This is a read-only review of GitHub Actions run **39115155092**, attempt **1**, executed at desktop **46dcb2d691827f7aa3ad7903dae09d39fd338126** / tree **8d5de807c41090e3d987764daec9c235ebd022a1**, with original **hepta-private-ci@2be5fc052ae7b2e9fb08c68a3ae7e5a218ad37d5**. It is not a new execution at the later main merge, R9 source, or R9-sync candidate.

The two reviewed jobs completed successfully: [history-transport](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39115155092/job/117639353718) and [original-owner-history](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39115155092/job/117655596136). Seven checks at this head have successful API status; the other five jobs were not deeply reviewed here.

## Actual result

- Transport: **51 Rust tests**, **22 Python contract tests**, strict Clippy, default-off check and formatting passed, using Rust 1.88.0.
- Original runtime: **15 checks**, **13 online history queries**, **5 request attempts**, **4 published requests**, **0 recovery resubmissions**. Original Agentd and probe used Rust 1.95.0; three desktop CLIs used Rust 1.88.0.
- Original owner queried while running at spawn generations **1, 5, 9, 13**. Controlled owner-stopped intervals were used to inject rollback/truncation faults.
- Actual retained records cover compiled and explicit-abstain history, original-protocol harness response loss, a distinct actual submit-CLI `submit_unknown` after publication, anchors, signed-request mismatch, owner restart with RunStatus null, expiry, storage rollback/truncation, revocation, and controlled stop.

Historical publication does not establish a current run or completed device effect. The harness reply-loss case is not a `hepta-submit` CLI reply-loss qualification. Production issuer, caller request/anchor persistence and co-rollback handling, Session/Shell history integration, model turns, Operations K↔D, device effects and kernel G1/G2 remain outside this result.

## Preserved evidence and verification scope

The two original evidence ZIPs are preserved byte for byte and match their GitHub API SHA256 and byte length. They retain all **108 original members**, including complete compile/test logs, exact requests/query outputs, public test profile/trust records, fault journals, probe source/lock and runtime records. `owner/work/report.json` and `transport/checks.json` are convenient exact-byte copies. API JSON files preserve retrieved semantic payloads; full decoded job logs are retained separately.

`source/` is a read-only mirror of **36 fixed desktop Git files**, checked against the **35 owner-job** and **29 transport-job** before/after SHA bindings. Eight generated probe inputs, exact isolated profile bytes, original and generated lock digests, all 13 query output records and four CLI output records were independently matched. Full runtime JSON lines equal the report, which also equals the report embedded in the complete owner-job log.

All five ELF identities are recorded in `review.json` and the original runtime report. The successful CI packaging step verifies their AArch64 ELF headers, byte lengths and SHA256 after execution. **The 90.6 MB ELF artifact and its binary-manifest were not downloaded here.** The existing source audit independently reviewed eight original owner files; this follow-up does not claim a second independent download of all 36 contracted upstream files or independent decoding of every journal frame.

`STORAGE.json` records raw and stored hashes/lengths for the three losslessly gzip-wrapped logs (mtime 0). Original receipt bytes are unchanged. `SHA256SUMS` covers every published file except itself. The original ZIPs can be opened directly to inspect all raw logs and runtime evidence without any new workload execution. `seal_ci_review.py` records the local evidence-validation and packaging process; it requires the original unsealed review directory and is not a product or CI test.

The earlier fixed-source audit remains unchanged. Its pending-at-document-writing qualification statement is complemented by this independently retrieved actual CI result, not retroactively rewritten.
