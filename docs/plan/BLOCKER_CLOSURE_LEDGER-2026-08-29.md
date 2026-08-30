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
| D0A-02/D2 | PR #33 / `codex/d0a02-proof-soundness-v4` (PR #27 is merged historical) | candidate evidence is headed-host only and still lacks independent review, protected-main settings, reviewed merge, and exact-main rerun; its claim ceiling intentionally excludes native clipboard | pass exact current-head workflow, satisfy D0T-03, merge, rerun exact main; validate clipboard ownership/lease/drag-drop independently under D4 |
| D1-01 | PR #32 / `codex/d1-01-current-main-v2` (PR #29 and #23 are superseded historical) | candidate is base-drifted from the latest main and not merged | rebase/reconstruct current main, commit signed D1 lock, reproducible build and QEMU pass, exact-main rerun |
| D2I-01 | PR #35 / `codex/d2i-current-main-v1` | source coexistence only; depends on promoted D0A-02 and D1 | same-image QEMU headed Servo integration gate |
| D3-01 | source foundation present in a development candidate; no promoted PR/head | source-level PageOwner/BrowserActor, principal attestation, receipt observation, and opt-in development AgentPort exist, but there is no exact integrated-image run, independent review, D0T-03 settings evidence, or production activation; D3 remains `BLOCKED_UPSTREAM` | finalize the candidate head, run the exact integrated-image principal/dispatch/receipt corpus (including unauthorized-peer, revision, cancellation/deadline, and indeterminate-receipt cases), obtain independent review and D0T-03 evidence, then rerun exact main |
| D4-D9 | none | dependency gates open | execute in canonical order |

Repository-setting gates for protected main, team CODEOWNERS, independent review,
and signing custody cannot be proven solely by source changes.
