# TrillionniumOS Desktop — blocker closure ledger

**Plan:** `2026-08-29-d6`
**Updated:** 2026-09-05
**Integrated-main stage:** `D0R_D0C06_D0A01_COMPILE_VALIDATED`

This ledger separates source closure, candidate evidence, integrated-main
evidence, repository settings, independent review, installed-product runtime,
physical hardware, key custody, and release authority. A successful lower-tier
workflow never promotes a higher evidence tier.

## Current convergence identity

Draft PR #66 on `codex/d6-gap-closure-v1` is the single active direct-to-`main`
convergence surface. It contains the cumulative source lineage previously
reviewed through PRs #60-#64 plus the bounded self-hosted availability probes
added on `main`. Live head, tree, base, prospective merge, workflow, review, and
repository-setting state must be read from GitHub; copied identities are not
promotion evidence.

PRs #60-#64 are historical implementation and review provenance only. They are
not parallel merge surfaces, and their old approvals or workflow packets cannot
be inherited by the final PR #66 object.

## 2026-09-05 live closure checkpoint

The pre-truth-refresh PR #66 object `ecb8c2ac0ec0e58277b64a5056a10a8262e8e63e` / tree `f5e5cc16dcd6c088dcef6ed6c3793bd7808b4aa8` had 22/22
permanent workflows at terminal success, all 22 review threads resolved, and
one current-head independent non-author approval. Two approvals are required.
Live GitHub readback reported `main` at `addaf73a48bae65f19f6bfe91c6264fd2ddb85a1` with protection disabled,
no required contexts, and no repository rulesets.

The fail-closed D0T-03 transaction at control commit
`f6304383a45bfa8b17019972f19c9330da1ae7c7` (run `33901170417`) executed zero
administration operations and recorded `ADMIN_TOKEN_MISSING`; neither the
workflow secret nor the installed GitHub connection supplied Administration
authority. The immutable readback is summarized in
`docs/evidence/2026-09-05-pr66-live-closure-checkpoint.md`.

This truth-refresh change invalidates the prior exact-head matrix and approval.
No source field may mark D0T-03, governed merge, exact-main, D3 exact-image,
D4-D7 installed-product, D8 hardware, or D9 HSM gates closed.

## Gate ledger

| Gate | Candidate state | Remaining blocker | Minimal closure action |
| --- | --- | --- | --- |
| D0T-01/D0T-02 | cumulative source, immutable action pins, truth validators, module inventory, and hostile tests exist | freeze one direct-main PR #66 object and complete all exact-head/prospective-merge lanes | pass the final matrix on the unchanged object, independently review, then rerun exact main after governed merge |
| D0T-03 | source contract, workflow inventory, and negative governance verifier exist | live `main` remains unprotected; no platform-enforced strict checks, team CODEOWNERS, current-push approvals, no-bypass rule, or protected release environments | configure GitHub organization/repository settings with administration authority; capture readback and positive/negative probes |
| D0C-02 | authenticated transport is fail-stop with Rust/Python/fault corpus | exact-candidate and exact-main evidence | pass final transport lane and promote only after governed merge |
| D0C-03/D0C-04 | canonical codec and exactly-one request-bound AgentPort source exist | exact-candidate evidence and promoted BrowserActor authority | pass final codec/port lanes, preserve default-disabled product listener, and bind through D3 |
| D0C-05 | production, development, qualification, and fixture binaries plus socket/path custody are separated | D0T-03 and D3 authority remain open | pass final custody lanes; keep production listener disabled |
| D0C-06 | crash-consistent facts-only receipt journal and failure corpus exist | exact-image lifecycle and real effect reconciliation remain | exercise requested/dispatched/terminal/indeterminate facts in D3/D7 without replay authority |
| D0A-01 | exact Servo pin compile compatibility exists | exact direct-main and exact-main evidence | pass the final Servo pin lane and rerun after merge |
| D0A-02 | headed-host candidate and crash/replacement corpus exist at its bounded claim ceiling | final exact object, governance, review, merge, and exact-main rerun | retain `no_native_clipboard` and other explicit non-claims; promote only through governed exact-main evidence |
| D1-01 | reproducible Debian/QEMU PID 1, Wayland, no-net, qualification-AgentPort candidate exists | final direct-main run, governance, review, merge, and exact-main rerun | pass the final D1 lane with exact image/input digests |
| D2I-01 | integrated local-fixture QEMU image candidate exists | final direct-main run, governance, review, merge, and exact-main rerun | pass the final D2I lane and bind one exact image digest |
| D3-01 | PageOwner/BrowserActor/principal/receipt source, caller-bound atomic fixture action, and fail-closed exact-image verifier exist | pinned Servo exposes tree updates but not the required retained-node action forwarding; no independent exact-image runtime packet | implement/review a Servo-owned retained-node adapter, then execute the complete exact-image corpus with distinct attestations |
| D4-01 | collaboration state/reference and compiled policy source exist | D3 prerequisite and installed native integration are open | run same-PageOwner native input/IME/clipboard/drag-drop/modal/crash corpus after D3 |
| D5-01 | trusted-app bundle policy and verifier exist | no promoted installed runtime or publisher/revocation ceremony | integrate after D4 and qualify exact image |
| D6-01 | capability/egress policy, hostile reference corpus, and deny-by-default authority boundary exist | no installed portal/network/resolver/proxy/peer-IP enforcement | integrate real controls after D5 and run controlled network-lab corpus |
| D7-01 | update/effect/recovery models and no-replay boundaries exist | no real persistent provider, slots, rollback counter, recovery media, or physical fault corpus | integrate after D6 and qualify image plus hardware power-loss behavior |
| D8-01 | verifier and three self-hosted availability lanes exist; ROG and Pocket4 connectivity probes have run | availability labels are not BOM attestation; no independently signed 24/72-hour or required power-loss corpus | freeze exact BOM/image, execute raw physical corpus, and obtain independent lab review |
| D9-01 | release verifier and role-separation contract exist | no protected release object, offline/HSM custodians, production signatures, anti-rollback ceremony, or publication | execute the independent release ceremony only after D8 |

## Closed repository-controlled blockers in the cumulative candidate

- Removed self-modifying source workflows and write-capable PR checkout paths.
- Replaced project-truth and D3 validator source rewriting/fragment execution
  with ordinary reviewed Python modules.
- Made session transitions transactional, event-time lease-normalized, and
  authority-safe.
- Closed Agent admission while any human lease remains.
- Added bounded state-space exploration and rejected-transition rollback checks.
- Made authenticated transport permanently fail-stop after wire/protocol
  failure while preserving safe local-preflight reuse.
- Removed the development cross-UID procfs dependency by using an explicit
  root-owned trusted path plus live pidfd/PID/UID/GID/start-time/cgroup/unit
  revalidation, without granting `CAP_SYS_PTRACE`.
- Added caller-bound atomic local-fixture PageAct and a hostile exact-image
  evidence verifier while retaining `servo_adapter_exercised=false` until real
  engine evidence exists.
- Added detailed, machine-validated development documentation for all Cargo
  workspace members.
- Replaced dynamic browser command execution in the ROG probe with a static,
  reviewable command graph and registered both manual self-hosted workflows in
  the governance inventories.
- Documented self-hosted D3-D9 lane admission, evidence custody, invalidation,
  and forbidden substitutes in
  `docs/operations/SELF_HOSTED_QUALIFICATION_LANES.md`.
- Preserved all product, external-effect, hardware, signing, publication, and
  release claim ceilings.

## External and environment-bound hard stops

The following cannot be created by another author-controlled source commit or a
fixture workflow:

1. GitHub branch/ruleset/environment administration and enforced independent
   review.
2. A protected merge followed by exact-main reruns and machine-truth promotion.
3. A reviewed Servo patch or engine API that implements retained-node semantic
   action, plus independently produced exact-image D3 evidence.
4. Installed D4-D7 OS/native authority adapters and their image/network/fault
   qualification environments.
5. Fixed-BOM physical hardware, uninterrupted long-duration execution, and raw
   power-loss evidence.
6. Offline/HSM production key custody, separated release roles, signatures,
   anti-rollback state, and protected publication.

Each remains a hard stop. No source field, author-associated approval,
administrator bypass, manually written PASS record, QEMU result, runner label,
fixture key, generated evidence, or negative verifier may manufacture a higher
evidence tier.
