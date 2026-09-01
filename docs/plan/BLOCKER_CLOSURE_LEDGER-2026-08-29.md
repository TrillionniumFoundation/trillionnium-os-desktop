# TrillionniumOS Desktop — blocker closure ledger

**Plan:** `2026-08-29-d6`  
**Updated:** 2026-09-01  
**Integrated-main stage:** `D0R_D0C06_D0A01_COMPILE_VALIDATED`

This ledger separates source closure, candidate evidence, integrated-main
evidence, repository settings, independent review, hardware, key custody, and
release authority. A green source/verifier workflow never promotes a higher
evidence tier.

## Current convergence identity

PR #60 on `codex/d6-gap-closure-v1` is the only active convergence surface. The
machine snapshot before this truth refresh is source head
`e87c63f257c9f660bc0fc104633efb39bcaca320`, tree
`e3fae0714a12b2876a07e8d332d82bb51907b750`, base
`78888fac3bee7974138ab1c5e4807511bee7fcbb`, and synthetic merge
`56f7a021bddbc3f9349c9afd2206670a7765853c`.

## Gate ledger

| Gate | Candidate state | Remaining blocker | Minimal closure action |
| --- | --- | --- | --- |
| D0T-01/D0T-02 | source and exact-head checks pass on the recorded PR #60 snapshot | truth-refresh changes the head; integrated main remains stale | pass the final exact-head matrix, independently review, merge, rerun exact main, then update integrated truth |
| D0T-03 | source contract and negative verifier pass | `main` is unprotected; no repository ruleset/required checks; organization-team CODEOWNERS and independent release roles are not demonstrated | configure live GitHub settings, capture API evidence, require latest-push non-author approval, prohibit self-merge/admin bypass |
| D0C-02 | fail-stop transport implementation and exact candidate reference/Rust/fault corpus pass | historical machine artifact rows remain stale until promotion; final truth head requires rerun | pass final exact-head transport workflow and bind result in PR; promote only after review/merge/exact-main |
| D0C-03/D0C-04 | canonical codec and exactly-one AgentPort candidate checks pass | historical machine artifact rows remain stale; no production BrowserActor authority | final exact-head rerun and later D3 promoted binding |
| D0C-05 | production/fixture/development binary separation, socket custody, path custody, and negative activation checks pass | live repository governance and D3 authority remain open | final exact-head rerun; keep product listener default-disabled |
| D0C-06 | receipt journal and failure corpus pass | facts-only journal is not an effect executor and machine artifact is unpromoted | final exact-head rerun; integrate requested/dispatched/terminal facts in D3 image |
| D0A-01 | exact Servo pin compile candidate passes | truth-refresh exact-head identity and exact-main promotion | rerun final head, independent review, merge, exact-main |
| D0A-02 | `MODULE_CLOSED_CANDIDATE`; headed-host causal SIGKILL/replacement evidence passes on recorded source snapshot | truth-refresh rerun, D0T-03, independent review, merge, exact-main; claim ceiling excludes native clipboard and clean teardown | pass final headed workflow and promote only through reviewed merge |
| D1-01 | `MODULE_CLOSED_CANDIDATE`; two-build reproducibility and QEMU PID 1/Wayland/no-net/qualification AgentPort corpus pass | truth-refresh rerun, D0T-03, independent review, merge, exact-main | pass final D1 workflow and promote its exact image/input digests |
| D2I-01 | `MODULE_CLOSED_CANDIDATE`; exact integrated local-fixture QEMU image evidence passes on recorded source snapshot | truth-refresh rerun, D0T-03, independent review, merge, exact-main | pass final D2I workflow and bind one image digest |
| D3-01 | PageOwner/BrowserActor/principal/receipt/development-profile source exists | cross-UID live `/proc/<pid>/exe` attestation is denied without ptrace; no Servo-owned atomic resolver or exact-image D3 corpus | select and independently review a least-authority live identity mechanism; implement Servo resolver; run full D3 corpus in exact promoted image |
| D4-01 | collaboration state/reference source and bounded tests pass | D3 runtime prerequisite is open | run same-PageOwner human/Agent/IME/clipboard/drag-drop/modal/crash trace corpus after D3 |
| D5-01 | trusted-app policy/source verifier passes | no promoted signed-app runtime, storage/service-worker enforcement, publisher/revocation ceremony | integrate after D4 and qualify exact image |
| D6-01 | capability/egress policy/source verifier passes | no installed portal/network namespace/resolver/proxy/peer-IP enforcement or adversarial bypass corpus | integrate real controls after D5 and qualify exact image/network lab |
| D7-01 | recovery/update/effect models and negative verifier pass | no real effect executor, persistent prepare/execute reconciliation, boot slots, rollback counter, recovery media, or power-loss evidence | implement after D6 and qualify under image plus hardware fault injection |
| D8-01 | source verifier correctly rejects synthetic promotion | no independent fixed-BOM hardware lab, 24/72-hour stability, suspend/input/audio/accessibility/multi-monitor and repeated power-loss corpus | execute on the fixed BOM with independent operators and immutable evidence |
| D9-01 | release verifier correctly retains negative promotion result | no protected release commit, offline HSM custodians, independent signer/attestor/promoter, signed artifacts, anti-rollback, or production publication | conduct the independent release ceremony only after D8 |

## Closed source blockers in PR #60

- Removed every self-modifying closure bootstrap workflow.
- Restored a fixed submitted review object and read-only checkout credentials.
- Made session transitions transactional and added explicit navigation owner
  invariants.
- Closed Agent admission while any human lease remains.
- Added bounded event-space exploration and hidden-state rollback checks.
- Made transport permanently fail-stop after wire/protocol failure while
  preserving safe local-preflight reuse.
- Re-ran repository, Rust, transport, codec, receipt, custody, D4-D9 source,
  exact-pin Servo, headed Servo, D1, and D2I workflows on a single recorded
  candidate source snapshot.

## Non-source blockers

The following cannot be closed by another author-controlled source commit:

1. GitHub branch/ruleset/environment configuration and independent review.
2. An independently accepted D3 cross-UID live identity mechanism.
3. Fixed hardware and long-duration/power-loss execution.
4. Offline HSM custody and separation of release duties.
5. Publication and exact-main evidence after reviewed merge.

Each remains a hard stop. No source field or passing negative verifier may be
used to manufacture a promotion claim.
