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
committed pre-truth-refresh evidence snapshot is source head
`e87c63f257c9f660bc0fc104633efb39bcaca320`, tree
`e3fae0714a12b2876a07e8d332d82bb51907b750`, base
`78888fac3bee7974138ab1c5e4807511bee7fcbb`, and synthetic merge
`56f7a021bddbc3f9349c9afd2206670a7765853c`. Live head and check state must be
read from GitHub.

## Gate ledger

| Gate | Candidate state | Remaining blocker | Minimal closure action |
| --- | --- | --- | --- |
| D0T-01/D0T-02 | source checks pass on the recorded PR #60 snapshot | each later source/truth commit requires a new exact-head matrix; integrated main remains unchanged | pass the final matrix, independently review, merge, rerun exact main, update integrated truth |
| D0T-03 | source contract and negative verifier pass | `main` is unprotected; no enforced ruleset/required checks, organization-team CODEOWNERS, independent release roles, or latest-push non-author approval | configure live GitHub settings, capture API evidence, prohibit self-merge and routine admin bypass |
| D0C-02 | fail-stop transport and independent Rust/Python/fault corpus are implemented | final exact-head artifact binding and exact-main promotion | pass the final transport workflow; promote only after independent review, merge, and exact-main rerun |
| D0C-03/D0C-04 | canonical codec and exactly-one AgentPort candidate checks exist | final exact-head evidence and a promoted BrowserActor authority | pass final codec/port workflows, then bind through D3 |
| D0C-05 | production/fixture/development binary separation, socket custody, pathname custody, and negative activation checks exist | governance and D3 authority remain open | pass final custody workflows; keep production listener default-disabled |
| D0C-06 | durable facts-only receipt journal and failure corpus exist | journal is not an effect executor; exact-image lifecycle integration remains | pass final receipt workflow and exercise requested/dispatched/terminal facts in D3 |
| D0A-01 | exact Servo pin compiles in candidate evidence | final exact-head identity and exact-main promotion | rerun final head, review, merge, rerun exact main |
| D0A-02 | `MODULE_CLOSED_CANDIDATE`; causal headed-host SIGKILL/replacement evidence exists | final exact-head rerun, D0T-03, independent review, merge, exact-main; ceiling retains `no_native_clipboard` and `no_clean_teardown` | pass final headed workflow and promote only through governed merge |
| D1-01 | `MODULE_CLOSED_CANDIDATE`; reproducible QEMU PID 1/Wayland/no-net/qualification-AgentPort corpus exists | final exact-head rerun, D0T-03, independent review, merge, exact-main | pass final D1 workflow and bind exact image/input digests |
| D2I-01 | `MODULE_CLOSED_CANDIDATE`; integrated local-fixture QEMU image evidence exists | final exact-head rerun, D0T-03, independent review, merge, exact-main | pass final D2I workflow and bind one exact image digest |
| D3-01 | PageOwner/BrowserActor/principal/receipt source exists; cross-UID procfs dependency is removed by development-only static trusted-path plus live pidfd/UID/GID/start-time/cgroup/unit binding | no independent security promotion, Servo-owned atomic resolver, or exact-image D3 runtime corpus | review the existing least-authority binding; implement Servo resolver; run full D3 corpus in the exact promoted image |
| D4-01 | collaboration state/reference source and bounded tests pass | D3 runtime prerequisite is open | run same-PageOwner human/Agent/IME/clipboard/drag-drop/modal/crash corpus after D3 |
| D5-01 | trusted-app policy/source verifier passes | no promoted signed-app runtime, storage/service-worker enforcement, publisher/revocation ceremony | integrate after D4 and qualify the exact image |
| D6-01 | capability/egress policy/source verifier passes | no installed portal/network namespace/resolver/proxy/peer-IP enforcement or adversarial bypass corpus | integrate real controls after D5 and qualify the exact image/network lab |
| D7-01 | recovery/update/effect models and negative verifier pass | no real effect executor, persistent prepare/execute reconciliation, boot slots, rollback counter, recovery media, or power-loss corpus | implement after D6 and qualify with image plus hardware fault injection |
| D8-01 | source verifier correctly rejects synthetic promotion | no independent fixed-BOM hardware lab, 24/72-hour stability, suspend/input/audio/accessibility/multi-monitor, or repeated power-loss corpus | execute on fixed BOM with independent operators and immutable evidence |
| D9-01 | release verifier correctly retains negative promotion | no protected release commit, offline HSM custodians, independent signer/attestor/promoter, signed artifacts, anti-rollback, or production publication | conduct independent release ceremony only after D8 |

## Closed source blockers in PR #60

- Removed every self-modifying closure bootstrap workflow.
- Restored a fixed submitted review object and read-only checkout credentials.
- Made session transitions transactional and added explicit navigation-owner
  invariants.
- Closed Agent admission while any human lease remains.
- Added bounded event-space exploration and hidden-state rollback checks.
- Made transport permanently fail-stop after wire/protocol failure while
  preserving safe local-preflight reuse.
- Closed the cross-UID procfs source dependency with a development-only static
  trusted-path binding plus live process revalidation, without `CAP_SYS_PTRACE`.
- Preserved strict evidence-tier ceilings and negative D8/D9 promotion results.

## Non-source blockers

The following cannot be closed by another author-controlled source commit:

1. GitHub branch/ruleset/environment configuration and independent review.
2. Independent security acceptance and exact-image qualification of the D3
   static trusted-path plus live process-identity mechanism.
3. Fixed hardware and long-duration/power-loss execution.
4. Offline HSM custody and separation of release duties.
5. Protected publication and exact-main evidence after reviewed merge.

Each remains a hard stop. No source field, same-author approval, manually
written PASS record, QEMU result, fixture key, or negative verifier may be used
to manufacture a higher-tier promotion claim.
