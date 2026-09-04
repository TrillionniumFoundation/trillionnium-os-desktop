# TrillionniumOS Desktop — current state

**Updated:** 2026-09-05
**Canonical plan:** `2026-08-29-d6`
**Repository mode:** `FULL_PRODUCT_REPOSITORY`
**Integrated implementation stage:** `D0R_D0C06_D0A01_COMPILE_VALIDATED`
**Machine truth:** `manifests/project-state.v1.json`

## 1. Integrated-main truth

The integrated-main claim remains the bounded d6 foundation. It includes the
repository/toolchain/input locks, Browser API and revision contracts,
deterministic session arbitration, bounded local transport, exactly-one
AgentPort core, default-disabled systemd custody, peer-attestation machinery,
durable non-replaying receipt facts, and exact-pin Servo compile compatibility.

It does not imply a promoted headed runtime, Debian/QEMU product image,
BrowserActor activation, external network/effect authority, hardware beta, or
signed release. The live `main` head observed at `2026-09-04T17:45:12Z` was
`addaf73a48bae65f19f6bfe91c6264fd2ddb85a1`. GitHub reported branch protection disabled, no required status
contexts, and no repository rulesets, so D0T-03 remains
`REPOSITORY_SETTING_REQUIRED`.

## 2. Single convergence candidate — PR #66

Draft PR #66 on `codex/d6-gap-closure-v1` is the single direct-to-`main` convergence surface.
PRs #60 through #64 are historical implementation/review provenance, not
parallel promotion objects. The committed snapshot immediately before this
truth-refresh change is:

```text
base SHA:              addaf73a48bae65f19f6bfe91c6264fd2ddb85a1
candidate SHA:         ecb8c2ac0ec0e58277b64a5056a10a8262e8e63e
candidate tree:        f5e5cc16dcd6c088dcef6ed6c3793bd7808b4aa8
prospective merge:     8d9c1de8b3af62eb32f5cd2bca1a0230afc30115
prospective merge tree:f5e5cc16dcd6c088dcef6ed6c3793bd7808b4aa8
```

The source object was exported independently by run `33901522952`; artifact
`9947810361` has digest
`sha256:cbf0c1ca5671ffd71bbb35f58dfdfdd4726f982b388f655e6912798bd8d481c4`,
and the tracked-file checksum audit found no mismatch. Live head and check state
must always be read from GitHub rather than inferred from this committed
pre-truth-refresh snapshot.

## 3. Repository-controlled closure present in the candidate

### Session arbitration

`SessionMachine::apply` executes transactionally. A rejected event cannot leave
partially advanced revisions, ownership, navigation source, or lease state.
Every Agent observation, mutation, and navigation admission requires
`Ready + Idle + no human lease`; Human/System source labels cannot relabel
active Agent work. The bounded state-space corpus checks both public and hidden
state after rejection.

### Authenticated transport and AgentPort

The raw framed carrier is private behind a fail-stop facade. Any frame I/O,
deadline, digest, nonce, kind, challenge, or sequence error drops the owned
carrier and permanently poisons the public connection. The canonical browser
codec, exactly-one request lifecycle, systemd socket/path custody, development
static attestation, and durable requested/dispatched/terminal receipt facts are
implemented with production, development, qualification, and fixture authority
physically separated.

### Documentation and truth controls

Cargo and non-Cargo components are machine registered and mapped to technical
documentation. Project truth, gate status, candidate snapshots, evidence
freshness, action pins, and invalidation inputs are checked fail closed. The
candidate-snapshot validator now rejects cross-file snapshot drift and rejects
any active work-package branch, PR, base, or head that disagrees with the
canonical committed snapshot.

## 4. Exact-head candidate evidence at the observed snapshot

The unchanged `ecb8c2ac0ec0e58277b64a5056a10a8262e8e63e` object had terminal success for all 22 permanent
pull-request workflows, including repository/Rust, governance, transport,
codec, custody, receipts, Servo exact-pin and headed-host, D1, D2I, D3
reference/verifier, and D4-D9 source/policy lanes. Exact run identities are in
`docs/evidence/generated/pr66-live-closure-checkpoint.json`.

That matrix proves only the declared candidate/source/verifier ceilings. It does
not promote D3-D9 or become exact-main evidence. The D0A-02 headed-host result
retains the explicit non-claims `no_native_clipboard` and `no_clean_teardown`;
neither limitation is promoted away by source, host, or candidate-image success.
All 22 review threads were
resolved and one independent non-author approval was present; two are required.
This truth-refresh commit invalidates the observed matrix and approval, so the
new head requires a complete exact-head rerun and fresh current-head review.

## 5. D0T-03 live governance status

A one-shot fail-closed transaction attempted to install strict protected-main
checks, stale-review dismissal, latest-push approval, two approvals, code-owner
review, conversation resolution, no bypass, read-only Actions defaults,
squash-only merging, an organization review team, and a protected `production`
environment.

Run `33901170417` stopped before any administration API operation because the
repository secret `TRILLIONNIUM_GITHUB_ADMIN_TOKEN` was absent or unavailable.
The installed GitHub connection also lacks repository Administration scope.
Artifact `9947679279`, digest
`sha256:b97280c17a569b1cf45ba84aa251e3378c72d94163443680a6f2146f14a9d183`,
records `ADMIN_TOKEN_MISSING` and an empty operation list. No partial setting
change is claimed.

## 6. D3 source state and executable blocker

The candidate contains typed PageOwner/BrowserActor source, TaskFlow principal
binding, bounded queues, revision/stale-target checks, cancellation/deadline
paths, a durable receipt observer, a local-fixture runtime, and explicit
development-profile AgentPort wiring. The cross-UID `/proc/<pid>/exe` source
blocker is closed without `CAP_SYS_PTRACE`: the compiled, root-owned,
non-symlink `/usr/libexec/hepta-agent` path is opened and hashed while live
PID/UID/GID, pidfd liveness, start time, cgroup, and systemd-unit checks remain.

Live activation remains fail closed because the pinned Servo integration does
not yet expose a reviewed Servo-owned retained-node semantic-action forwarding
boundary, the exact integrated image has not executed the complete principal,
attestation, dispatch, receipt, cancellation, deadline, crash, recovery,
stale-reference, and indeterminate-outcome corpus, and independent security
review has not promoted that authority.

## 7. Later-stage source versus product evidence

D4-D9 source/reference workflows implement bounded policy and verification
surfaces, but they do not close their product gates:

- D4 requires a promoted D3 same-PageOwner native interaction corpus;
- D5 requires installed signed-app, origin/storage/service-worker, revocation,
  and publisher enforcement;
- D6 requires installed namespace, resolver, proxy, redirect, peer-IP, portal,
  and bypass controls;
- D7 requires a real persistent effect executor, update slots, rollback state,
  recovery media, and power-loss qualification;
- D8 requires independent fixed-BOM 24/72-hour and repeated physical power-loss
  evidence;
- D9 requires protected release governance, offline HSM custody, separated
  signers/attestors/promoter, signed immutable artifacts, anti-rollback, and
  controlled publication.

## 8. Historical provenance

PR #27 remains historical headed-host provenance. PR #23, PR #29, and PR #32
are historical D1 attempts. PR #33, PR #35, and unstable PR #59 are superseded
candidate surfaces. PRs #60-#64 are the immediate cumulative implementation and
review lineage that converged into PR #66. None substitutes for final PR #66
exact-head evidence, two independent current-head approvals, governed merge, or
exact-main evidence.

## 9. Promotion sequence

1. Re-run every permanent workflow on one final exact PR #66 head.
2. Freeze and publish its source/base/tree/prospective-merge and artifact
   identities.
3. Apply and independently read back protected-main, required-check, team
   CODEOWNERS, no-bypass, Actions-permission, and protected-environment controls.
4. Complete bounded positive and negative governance probes.
5. Obtain two latest-head independent non-author approvals; do not self-approve,
   self-merge, auto-merge, or use administrator bypass.
6. Merge normally, rerun exact `refs/heads/main`, and only then promote machine
   truth.
7. Execute and independently review the real Servo-owned D3 exact-image corpus.
8. Continue D4 through D9 strictly in prerequisite and evidence-tier order.
