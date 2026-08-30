# Blocker closure ledger

**Snapshot:** 2026-08-29  
**Baseline main:** `d878fff0d809413e1f3048a87e0a8247b97d99b9`

This ledger is a human view of `manifests/project-state.v1.json`; machine truth
wins.

| Package | Candidate | Current blocker at snapshot | Required closure |
| --- | --- | --- | --- |
| D0T-01/D0T-02 | `codex/d6-plan-truth-ci-closure-v1` | new package | exact-head truth/CI validation, review, merge, main rerun |
| D1-01 | PR #23 / `codex/d1-01-reproducible-qemu-substrate` | base drift and non-mergeable candidate | reconstruct on current main, committed D1 lock, reproducible build and QEMU pass |
| D0A-02/D2 | PR #27 / `codex/d0a02-headed-runtime-v3` | mutable CI bootstrap/format gates prevented runtime qualification | repair workflows, exact-head permanent headed pass, evidence promotion, main rerun |
| D2I | none | depends on D1 and D2 | same-image QEMU headed Servo integration gate |
| D3 | none | depends on D2I and fixture/product separation | PageOwner/BrowserActor/principal/receipt integration |
| D4-D9 | none | dependency gates open | execute in canonical order |

Repository-setting gates for protected main, team CODEOWNERS, independent review,
and signing custody cannot be proven solely by source changes.
