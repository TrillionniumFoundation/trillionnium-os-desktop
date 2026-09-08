# TrillionniumOS Desktop — blocker closure ledger

**Plan:** `2026-08-29-d6`
**Updated:** 2026-09-07
**Integrated-main stage:** `D0R_D0C06_D0A01_COMPILE_VALIDATED`

This ledger separates source closure, candidate evidence, integrated-main
evidence, repository settings, independent review, installed-product runtime,
physical hardware, key custody and release authority. A successful lower-tier
workflow never promotes a higher evidence tier.

## Current convergence identity

Draft PR #73 on `codex/d6-sensitive-log-redaction-v1` is the sole active direct-to-`main` candidate.
PR #66 is closed and unmerged and its results are historical only. The exact
clean pre-refresh snapshot is head `ddaf10d6e0172f9c17c04752d0b6d27ebf89a14b`, tree
`3a7d7025011c5393f9eac04f2522817a8e89090e`, base `addaf73a48bae65f19f6bfe91c6264fd2ddb85a1`, prospective merge
`afcab92e6a06ff58afde83a96b56893b0e334d3e` at `2026-09-07T05:07:35Z`. This refresh creates a new exact
object, so no prior workflow or approval transfers.

## Gate ledger

| Gate | Candidate state | Remaining blocker | Minimal closure action |
| --- | --- | --- | --- |
| D0T-01/D0T-02 | cumulative truth validators, immutable action pins, inventories and hostile tests exist | final PR #73 head must complete the exact-head/prospective-merge packet | pass unchanged final matrix, review, governed merge and exact-main rerun |
| D0T-03 | source contract and enforcement verifier exist | live protected-main, strict checks, code-owner/current-push review, no-bypass rule, protected release environments and separated credentials are not yet proven | configure with repository/organization administration and capture authenticated positive/negative readback |
| D0C-02 | authenticated fail-stop transport exists | final exact-head and exact-main evidence | pass transport lane, review, merge and rerun on main |
| D0C-03/D0C-04 | canonical codec and request-bound AgentPort exist | final exact-head and promoted BrowserActor authority | pass codec/port lanes and retain default-disabled product listener |
| D0C-05 | product/development/qualification/fixture binaries and custody are separated | D0T-03 and D3 authority remain open | pass custody lanes and keep production listener disabled |
| D0C-06 | crash-consistent facts-only journal and fault corpus exist | exact-image lifecycle and real effect reconciliation remain | exercise facts in D3/D7 without replay authority |
| D0A-01 | exact Servo pin compile compatibility exists | final exact-head and exact-main evidence | pass exact-pin lane and rerun after merge |
| D0A-02 | headed-host local-fixture candidate exists | governance, review, merge and exact-main rerun | retain `no_native_clipboard` and `no_clean_teardown` non-claims |
| D1-01 | reproducible Debian/QEMU PID1/Wayland/no-net candidate exists | final exact-head, governance, review, merge and exact-main | pass D1 lane with exact image/input digests |
| D2I-01 | integrated local-fixture QEMU image candidate exists | final exact-head, governance, review, merge and exact-main | pass D2I lane and bind one exact image digest |
| D3-01 | PageOwner/BrowserActor/principal/receipt source and fail-closed verifier exist | pinned Servo lacks the required retained-node action forwarding and there is no independent exact-image packet | implement/review Servo-owned adapter and execute complete exact-image corpus |
| D4-01 | collaboration state/reference source exists | promoted D3 and installed native integration are open | run same-PageOwner input/IME/clipboard/drag-drop/modal/crash corpus |
| D5-01 | trusted-app policy and verifier exist | no installed runtime or publisher/revocation ceremony | integrate after D4 and qualify the exact image |
| D6-01 | capability/egress policy and hostile corpus exist | no installed portal/network/resolver/proxy/peer-IP enforcement | integrate controls and run a controlled network-lab corpus |
| D7-01 | update/effect/recovery models and no-replay boundary exist | no persistent provider, slots, rollback counter, recovery media or physical fault corpus | integrate after D6 and qualify image plus hardware behavior |
| D8-01 | verifier and runner-availability probes exist | labels are not BOM attestation; no independent 24/72-hour or power-loss corpus | freeze BOM/image, execute raw physical corpus and obtain independent lab review |
| D9-01 | release verifier and role-separation contract exist | no protected release, offline/HSM custodians, production signatures, anti-rollback ceremony or publication | execute independent release ceremony only after D8 |

## Repository-controlled closure present

- Self-modifying source workflows and write-capable PR checkout paths are absent.
- Project-truth and documentation validators are ordinary reviewed modules.
- Session transitions and Agent admission are transactional and fail closed.
- Authenticated transport is permanently fail-stop after wire/protocol failure.
- Development executable identity uses an explicit trusted path plus live process
  revalidation without widening privileges.
- Public evidence is redacted while private attestation state remains strict.
- Source, host and candidate verifiers preserve all higher-tier claim ceilings.

## External and environment-bound hard stops

The following cannot be manufactured by another author-controlled commit or a
fixture workflow:

1. GitHub administration and enforced independent review.
2. A normal protected merge followed by exact-main reruns.
3. Reviewed Servo-owned retained-node action forwarding and independent D3
   exact-image evidence.
4. Installed D4-D7 OS/native adapters and their qualification environments.
5. Fixed-BOM hardware, uninterrupted long-duration runs and raw power-loss data.
6. Offline/HSM key custody, separated release roles, signatures, anti-rollback
   state and protected publication.

Each remains fail closed. No source field, author-associated approval,
administrator bypass, manually written PASS record, QEMU result, runner label,
fixture key or generated evidence may manufacture a higher evidence tier.
