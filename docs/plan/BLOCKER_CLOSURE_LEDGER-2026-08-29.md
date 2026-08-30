# Blocker closure ledger

**Snapshot:** 2026-08-30 (GitHub candidate snapshot observed at `2026-08-30T10:47:03Z`)<br>
**Baseline main:** `bf6bba2ea1c49b36e11754bf27dc0c56e3da3bd1`

This ledger is a human view of `manifests/project-state.v1.json`; machine truth
wins. The D3 source foundation mentioned below is an unpromoted development
candidate; it is deliberately absent from the active candidate list until its
final PR head and evidence identities are known.

| Package | Candidate | Current blocker at snapshot | Required closure |
| --- | --- | --- | --- |
| D0T-01/D0T-02 | merged d6 baseline `bf6bba2`; later main changes hit invalidation paths | historical exact-main evidence must be refreshed on the current main before new promotion | exact-head truth/CI validation, independent review, exact-main rerun |
| D0C-02 | historical host result at `786debc12aa8d790b231397c1a3341fbf89de080` (run `33167838644`) | declared transport/workspace inputs changed after the recorded run; evidence is `STALE_EVIDENCE_REQUIRES_EXACT_HEAD_RERUN` while the bounded carrier claim ceiling remains unchanged | rerun the Rust 1.93 transport/workspace gate on the exact current head and refresh the bound evidence under review |
| D0C-03/D0C-04 | historical codec/bridge host results at `4cfebbe6a40ebbec32d9d1bcbfca1d513b510ebb` / `5abd71db79b75e400c1c1d7cb0eac85a68041cae` | codec and AgentPort inputs changed after their recorded runs; both host artifacts are stale even though source/static checks remain available | rerun the exact-head codec and AgentPort Rust gates, then update evidence freshness and promotion bindings |
| D0C-05 | historical custody result at `7be7121b1d2593a0e708ec9ade189ef84ab245da` (runs `33190387511`, `33190387553`, `33190387564`) | packaging, service, workspace, and shared validator inputs changed after the recorded runs; contract/artifact freshness is `STALE_EVIDENCE` and `merge_ready: false` even though the source-capability flag remains true | rerun the systemd custody, Rust, and claim-ceiling corpus on the exact current head before any current host promotion |
| D0C-06 | historical receipt result at `25d2d5882018b9974fc360aaf646128c6b6f175f` (runs `33235926576`, `33235926577`, `33235926596`, `33235926613`) | receipt-journal/workspace/validator inputs changed after the recorded runs; facts-only claim ceiling remains bounded but evidence is stale | rerun the permanent receipt-journal qualification and full workspace regression on the exact current head |
| D0A-01 | historical Servo compile qualification at `01d02d692c573ccde7a99d990f2a63235d9bc69f` (run `33230713426`, job `99042937091`) | repository qualification inputs and evidence tooling changed after the recorded run; compile-only result is `STALE_EVIDENCE_REQUIRES_EXACT_HEAD_RERUN` | rerun the exact-pin Servo workflow against the current candidate head and rebind the artifact digest |
| D0A-02/D2 | PR #33 / `codex/d0a02-proof-soundness-v4` (PR #27 is merged historical) | candidate evidence is headed-host only and still lacks independent review, protected-main settings, reviewed merge, and exact-main rerun; its claim ceiling intentionally excludes native clipboard | pass exact current-head workflow, satisfy D0T-03, merge, rerun exact main; validate clipboard ownership/lease/drag-drop independently under D4 |
| D1-01 | PR #32 / `codex/d1-01-current-main-v2` (PR #29 and #23 are superseded historical) | candidate is base-drifted from the latest main and not merged | rebase/reconstruct current main, commit signed D1 lock, reproducible build and QEMU pass, exact-main rerun |
| D2I-01 | PR #35 / `codex/d2i-current-main-v1` | source coexistence only; depends on promoted D0A-02 and D1 | same-image QEMU headed Servo integration gate |
| D3-01 | source foundation present in a development candidate; no promoted PR/head | source-level PageOwner/BrowserActor, principal attestation, receipt observation, and opt-in development AgentPort exist, but there is no exact integrated-image run, independent review, D0T-03 settings evidence, or production activation; D3 remains `BLOCKED_UPSTREAM` | finalize the candidate head, run the exact integrated-image principal/dispatch/receipt corpus (including unauthorized-peer, revision, cancellation/deadline, and indeterminate-receipt cases), obtain independent review and D0T-03 evidence, then rerun exact main |
| D4-D9 | none | dependency gates open | execute in canonical order |

Repository-setting gates for protected main, team CODEOWNERS, independent review,
and signing custody cannot be proven solely by source changes.
