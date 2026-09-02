# TrillionniumOS Desktop — blocker closure ledger

**Plan:** `2026-08-29-d6`  
**Updated:** 2026-09-02  
**Integrated-main stage:** `D0R_D0C06_D0A01_COMPILE_VALIDATED`

This ledger separates source closure, candidate evidence, integrated-main
evidence, repository settings, independent review, hardware, key custody, and
release authority. A green source/verifier workflow never promotes a higher
evidence tier.

## Current convergence identity

PR #64 on `codex/full-gap-closure-execution-v1` is the single active source
convergence surface. It contains the cumulative accepted source lineage from
PRs #60 through #63 plus the ordinary-module D3 validator-loader repair. Its
live head, tree, base, prospective merge, review state, and checks must be read
from GitHub; copied historical identities are not promotion evidence.

PRs #60, #61, #62, and #63 are retained as review and implementation
provenance only after #64 is retargeted directly to `main`. They must not remain
parallel merge surfaces.

## Gate ledger

| Gate | Candidate state | Remaining blocker | Minimal closure action |
| --- | --- | --- | --- |
| D0T-01/D0T-02 | source checks pass on the current cumulative candidate | direct-main exact-head/prospective-merge matrix and exact-main promotion remain required | freeze #64, pass every required workflow, independently review, merge through governed main, rerun exact main, update integrated truth |
| D0T-03 | source contract and negative verifier pass | live `main` protection/ruleset, organization-team CODEOWNERS, independent release roles, and dynamic positive/negative acceptance are not platform-enforced | configure live GitHub settings, capture API evidence, prohibit self-merge and routine administrator bypass |
| D0C-02 | fail-stop transport and independent Rust/Python/fault corpus are implemented | direct-main artifact binding and exact-main promotion | pass the final transport workflow; promote only after independent review, merge, and exact-main rerun |
| D0C-03/D0C-04 | canonical codec and exactly-one AgentPort candidate checks exist | final direct-main evidence and a promoted BrowserActor authority | pass final codec/port workflows, then bind through D3 |
| D0C-05 | production/fixture/development binary separation, socket custody, pathname custody, and negative activation checks exist | governance and D3 authority remain open | pass final custody workflows; keep production listener default-disabled |
| D0C-06 | durable facts-only receipt journal and failure corpus exist | journal is not an effect executor; exact-image lifecycle integration remains | pass final receipt workflow and exercise requested/dispatched/terminal facts in D3 |
| D0A-01 | exact Servo pin compiles in candidate evidence | direct-main identity and exact-main promotion | rerun final head, review, merge, rerun exact main |
| D0A-02 | `MODULE_CLOSED_CANDIDATE`; causal headed-host SIGKILL/replacement evidence exists | final direct-main rerun, D0T-03, independent review, merge, exact-main; ceiling retains `no_native_clipboard` and `no_clean_teardown` | pass final headed workflow and promote only through governed merge |
| D1-01 | `MODULE_CLOSED_CANDIDATE`; reproducible QEMU PID 1/Wayland/no-net/qualification-AgentPort corpus exists | final direct-main rerun, D0T-03, independent review, merge, exact-main | pass final D1 workflow and bind exact image/input digests |
| D2I-01 | `MODULE_CLOSED_CANDIDATE`; integrated local-fixture QEMU image evidence exists | final direct-main rerun, D0T-03, independent review, merge, exact-main | pass final D2I workflow and bind one exact image digest |
| D3-01 | PageOwner/BrowserActor/principal/receipt source, caller-bound atomic fixture action, and fail-closed exact-image evidence verifier exist; cross-UID procfs dependency is removed by development-only static trusted-path plus live pidfd/UID/GID/start-time/cgroup/unit binding | no independent security promotion, no production-safe Servo-owned retained-node adapter, and no independently produced exact-image D3 runtime corpus | independently review the least-authority binding; implement a Servo retained-node resolver/action path without coordinate, DOM-order, name-only, or generic-action fallback; run the full D3 corpus in the exact promoted image |
| D4-01 | collaboration state/reference and compiled product-policy source pass | D3 runtime prerequisite and installed native integration are open | run same-PageOwner human/Agent/IME/clipboard/drag-drop/modal/crash corpus after D3 |
| D5-01 | trusted-app policy/source verifier and compiled policy core pass | no promoted signed-app runtime, storage/service-worker enforcement, publisher/revocation ceremony | integrate after D4 and qualify the exact image |
| D6-01 | capability/egress policy/source verifier and explicit authority boundary pass | no installed portal/network namespace/resolver/proxy/peer-IP enforcement or adversarial bypass corpus | integrate real controls after D5 and qualify the exact image/network lab |
| D7-01 | recovery/update/effect models and no-replay product boundary pass | no real effect executor, persistent provider reconciliation, boot slots, rollback counter, recovery media, or physical power-loss corpus | implement after D6 and qualify with image plus hardware fault injection |
| D8-01 | source verifier correctly rejects synthetic promotion | no independent fixed-BOM hardware lab, 24/72-hour stability, suspend/input/audio/accessibility/multi-monitor, or repeated power-loss corpus | execute on fixed BOM with independent operators and immutable evidence |
| D9-01 | release verifier correctly retains negative promotion | no protected release commit, offline HSM custodians, independent signer/attestor/promoter, signed artifacts, anti-rollback, or production publication | conduct independent release ceremony only after D8 |

## Closed repository-controlled blockers in the cumulative candidate

- Removed every self-modifying closure bootstrap workflow.
- Replaced project-truth and D3 validator source rewriting/fragment execution
  with ordinary reviewed Python modules.
- Restored a fixed submitted review object and read-only checkout credentials.
- Made session transitions transactional and added explicit navigation-owner
  invariants.
- Closed Agent admission while any human lease remains and normalized expiry at
  every time-bearing admission boundary.
- Added bounded event-space exploration and hidden-state rollback checks.
- Made transport permanently fail-stop after wire/protocol failure while
  preserving safe local-preflight reuse.
- Closed the cross-UID procfs source dependency with a development-only static
  trusted-path binding plus live process revalidation, without `CAP_SYS_PTRACE`.
- Added a caller-bound atomic local-fixture PageAct path and a hostile,
  fail-closed verifier for independently produced D3 exact-image evidence.
- Added machine-enforced development documentation for every Cargo workspace
  member.
- Preserved strict evidence-tier ceilings and negative D8/D9 promotion results.

## Non-source blockers

The following cannot be closed by another author-controlled source commit:

1. GitHub branch/ruleset/environment configuration and independent review.
2. Independent security acceptance and exact-image qualification of the D3
   static trusted-path plus live process-identity mechanism and a real
   Servo-owned retained-node semantic adapter.
3. Installed D4-D7 OS/native authority adapters and qualification environments.
4. Fixed hardware and long-duration/power-loss execution.
5. Offline HSM custody and separation of release duties.
6. Protected publication and exact-main evidence after reviewed merge.

Each remains a hard stop. No source field, same-author approval, manually
written PASS record, QEMU result, fixture key, generated evidence, or negative
verifier may be used to manufacture a higher-tier promotion claim.
