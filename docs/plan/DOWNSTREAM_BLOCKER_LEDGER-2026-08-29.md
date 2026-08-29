# Downstream blocker ledger — 2026-08-29

This ledger prevents downstream source volume from being mistaken for product
progress. A package may move only when all prerequisite evidence is bound to
the exact candidate head and remains valid after integration.

| Package | Current outcome | Exact prerequisite to resume |
| --- | --- | --- |
| D3-03 concrete receipt-journal adapter | `RESUME_REQUIRED` | D3-02 lifecycle plus a reviewed adapter to `hepta-receipt-journal` and crash/disk-full corpus |
| D3-04 exact Servo BrowserActor adapter | `BLOCKED_UPSTREAM` | D0A-02 headed candidate and D2I same-image qualification on the exact integration head |
| D3-05 development-profile AgentPort activation | `BLOCKED_UPSTREAM` | D0T-03 fixture/product separation, D3-03, D3-04, exact Agent principal binding, and PID 1 image evidence |
| D4 same-page human/Agent collaboration | `BLOCKED_UPSTREAM` | complete D3 local-fixture operation corpus with durable receipts and no hidden page |
| D5 trusted shell and signed applications | `BLOCKED_UPSTREAM` | D4 plus reviewed origin, bundle-signature, storage-isolation and revocation contracts |
| D6 capability services and controlled egress | `BLOCKED_UPSTREAM` | D5 plus network namespace, resolver/egress proxy, redirect/peer-IP and worker/subresource coverage |
| D7 recovery, updates and effect reconciliation | `BLOCKED_UPSTREAM` | D6, independent signing/update custody, rollback metadata and power-loss qualification |
| D8 fixed-hardware beta | `BLOCKED_UPSTREAM` | D7, selected immutable hardware BOM, hardware lab and qualification methodology |
| D9 signed release | `REPOSITORY_SETTING_REQUIRED` | independent review teams, protected main, signing custody, exact-main reruns, SBOM/provenance and all prior gates |

No downstream package may introduce a hidden fallback engine, public WebDriver
or TCP listener, default-enabled AgentPort, ambient browser network/filesystem
authority, automatic replay of potential external effects, development keys in
a release path, or a higher-tier claim derived from lower-tier evidence.
