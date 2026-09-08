# TrillionniumOS Desktop — candidate status

**Updated:** 2026-09-08  
**Scope:** unmerged work only  
**Canonical integrated state:** [`CURRENT_STATE.md`](CURRENT_STATE.md)

## Frozen PR #73

PR #73 (`codex/d6-sensitive-log-redaction-v1`) is frozen for decomposition. It contains cumulative work across governance, contracts, transport, attestation, AgentPort, receipts, BrowserActor, Servo qualification, QEMU image work, and later-stage reference policies.

It must remain Draft and must not be merged as a single change.

Permitted changes on the frozen branch are limited to:

- repair of a current-head build or test failure;
- correction of stale or false evidence metadata;
- decomposition metadata needed to split the work safely.

New features, contracts, modules, adapters, qualification classes, and release claims must be developed in bounded successor PRs.

## Evidence rules

For every candidate:

1. evidence is bound to one exact commit SHA and its exact inputs;
2. a later push invalidates prior workflow results, artifacts, approvals, and prospective-merge conclusions;
3. skipped, cancelled, empty, historical, or differently bound runs are not current evidence;
4. source tests cannot prove an installed image;
5. QEMU cannot prove physical hardware;
6. hosted CI cannot prove signing-key custody or protected release promotion;
7. a fixture cannot be relabelled as production runtime behavior;
8. a failed or unexecuted behavior step must not emit `*_tested: true`.

## Successor sequence

The frozen branch is decomposed in the order defined by [`plan/PR73_DECOMPOSITION.md`](plan/PR73_DECOMPOSITION.md):

1. repository truth and governance;
2. contract core and browser contracts;
3. canonical codec;
4. local transport, attestation, and AgentPort;
5. receipt persistence and recovery;
6. BrowserActor, request custody, and incarnation;
7. Servo retained-node behavior;
8. headed runtime and browser daemon integration;
9. platform adapters;
10. Debian image and QEMU integration;
11. update and recovery;
12. reproducible build, hardware, signing, and release promotion.

No successor inherits a closed gate merely because the cumulative branch previously exercised related code.
