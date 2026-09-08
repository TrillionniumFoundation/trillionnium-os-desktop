# TrillionniumOS Desktop — candidate status

**Updated:** 2026-09-08  
**Scope:** unmerged work and committed candidate snapshots only  
**Canonical integrated state:** [`CURRENT_STATE.md`](CURRENT_STATE.md)  
**Current claim ceiling:** [`NON_CLAIMS.md`](NON_CLAIMS.md)

Candidate state has two distinct sources:

1. the committed machine-state snapshot carried by `manifests/project-state.v1.json`; and
2. live GitHub state for current pull requests and workflows.

The committed snapshot is never treated as live GitHub state. Promotion requires qualification and review on the exact final head, followed by the required exact-main rerun.

## Committed machine-state snapshot

The current structured manifest projects these historical candidate records:

| Work package | Branch | Pull request | Recorded status |
|---|---|---:|---|
| `D1-01` | `codex/d1-01-d6-replay-v1` | PR #29 | `BASE_DRIFT` |
| `D0A-02` | `codex/d0a02-headed-runtime-v3` | PR #27 | `MODULE_CLOSED_CANDIDATE` |

These rows are a committed snapshot, not a claim that the pull requests remain open, current, mergeable, or qualified today. Live PR and CI facts must be read from GitHub.

## Live frozen convergence candidate

PR #73 (`codex/d6-sensitive-log-redaction-v1`) is frozen for decomposition. It contains cumulative work across governance, contracts, transport, attestation, AgentPort, receipts, BrowserActor, Servo qualification, QEMU image work, and later-stage reference policies.

PR #73 must remain Draft and must not be merged as one unit.

Permitted changes on the frozen branch are limited to:

- repair of a current-head build or test failure;
- correction of stale or false evidence metadata;
- decomposition metadata needed to split the work safely.

New features, contracts, modules, adapters, qualification classes, and release claims belong in bounded successor PRs.

## Evidence freshness rules

For every candidate:

1. evidence binds one exact commit SHA and its exact inputs;
2. a later push invalidates earlier workflow results, artifacts, approvals, and prospective-merge conclusions;
3. skipped, cancelled, empty, historical, or differently bound runs are not current evidence;
4. source tests cannot prove an installed image;
5. QEMU cannot prove physical hardware;
6. hosted CI cannot prove signing-key custody or protected release promotion;
7. a fixture cannot be relabelled as production runtime behavior;
8. a failed or unexecuted behavior step must not emit `*_tested: true`.

## Successor sequence

The frozen branch is decomposed through issues #79–#90 in the order defined by [`plan/PR73_DECOMPOSITION.md`](plan/PR73_DECOMPOSITION.md):

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
