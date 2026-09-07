# TrillionniumOS Desktop — current state

**Updated:** 2026-09-07
**Canonical plan:** `2026-08-29-d6`
**Repository mode:** `FULL_PRODUCT_REPOSITORY`
**Integrated implementation stage:** `D0R_D0C06_D0A01_COMPILE_VALIDATED`
**Machine truth:** `manifests/project-state.v1.json`

## 1. Integrated-main truth

Integrated `main` remains the bounded d6 foundation: repository/toolchain/input
locks, Browser API and revision contracts, deterministic session arbitration,
bounded local transport, exactly-one AgentPort core, default-disabled systemd
custody, peer-attestation machinery, durable non-replaying receipt facts, and
exact-pin Servo compile compatibility.

It does not imply a promoted headed runtime, Debian/QEMU product image,
BrowserActor activation, external network/effect authority, hardware beta, or
signed release. The observed `main` SHA is `addaf73a48bae65f19f6bfe91c6264fd2ddb85a1`.

## 2. Single convergence candidate — PR #73

Draft PR #73 on `codex/d6-sensitive-log-redaction-v1` is the sole direct-to-`main` convergence
surface. PR #66 is closed and unmerged and is retained only as historical
implementation, CI and review provenance.

The committed pre-truth-refresh snapshot is:

```text
base SHA:              addaf73a48bae65f19f6bfe91c6264fd2ddb85a1
candidate SHA:         ddaf10d6e0172f9c17c04752d0b6d27ebf89a14b
candidate tree:        3a7d7025011c5393f9eac04f2522817a8e89090e
prospective merge:     afcab92e6a06ff58afde83a96b56893b0e334d3e
observed at:           2026-09-07T05:07:35Z
```

Live head, tree, prospective merge, checks, reviews and settings must be read
from GitHub. This truth refresh moves the head and invalidates the snapshot's
exact-head workflow, CodeQL and review packet by design.

## 3. Repository-controlled closure present in the candidate

The candidate contains transactional session arbitration, fail-stop authenticated
transport, canonical Browser API encoding, exactly-one AgentPort lifecycle,
production/development/qualification/fixture separation, request-scoped peer
custody and attestation, durable non-replaying receipt facts, source-only
D4-D9 policy surfaces, and machine-validated module/component documentation.

Identity-to-log remediation retains PID/UID/GID, pidfd, process birth, cgroup,
systemd unit and executable-digest checks in private runtime state while public
evidence exposes only bounded redacted conclusions.

## 4. Exact-head candidate evidence

No workflow, CodeQL result, approval or merge decision from PR #66 or any prior
PR #73 head transfers to the truth-refresh head. Closure requires all 22
permanent workflow families and CodeQL to reach non-empty terminal success on
one unchanged final object, followed by eligible current-head independent
approvals. Candidate success remains bounded and is not exact-main evidence.

## 5. D0T-03 live governance status

Source governance contracts and negative verifiers exist, but source cannot
prove GitHub platform enforcement. D0T-03 remains
`REPOSITORY_SETTING_REQUIRED` until live readback proves protected `main`,
strict required checks, code-owner/current-push review, active no-bypass rules,
protected release environments, separated identities and authenticated positive
and negative enforcement probes.

## 6. D3 source state and executable blocker

Typed PageOwner/BrowserActor source, TaskFlow principal binding, bounded queues,
revision and stale-target checks, cancellation/deadline paths, a durable receipt
observer, local-fixture runtime and explicit development-profile AgentPort wiring
are present. Cross-UID executable identity is bound to a root-owned trusted path
plus live PID/UID/GID, pidfd, start-time, cgroup and unit revalidation without
granting `CAP_SYS_PTRACE`.

D3 remains blocked on a reviewed Servo-owned retained-node semantic-action
forwarding boundary, exact integrated-image runtime evidence and independent
security review.

The D0A-02 headed-host claim ceiling remains explicit: `no_native_clipboard` and `no_clean_teardown`.

## 7. Later-stage source versus product evidence

- D4 requires promoted D3 and installed same-PageOwner native interaction.
- D5 requires installed signed-app, origin, storage, service-worker, revocation
  and publisher enforcement.
- D6 requires installed namespace, resolver, proxy, redirect, peer-IP, portal and
  bypass controls in a controlled network lab.
- D7 requires real persistent effect execution/reconciliation, update slots,
  rollback state, recovery media and physical fault qualification.
- D8 requires independent fixed-BOM 24/72-hour and repeated raw power-loss data.
- D9 requires protected release governance, offline/HSM dual control, separated
  roles, signed immutable artifacts, anti-rollback and controlled publication.

## 8. Historical provenance

PR #27, PR #23, PR #29, PR #32, PR #33, PR #35 and PR #59 remain historical candidate or
qualification provenance. PRs #60-#64 converged into closed PR #66 and then into
active PR #73. None substitutes for final PR #73 exact-head evidence,
independent review, governed merge, exact-main evidence, installed-product
execution, physical hardware or signing custody.

## 9. Promotion sequence

1. Freeze one final PR #73 head and complete all permanent exact-head lanes plus
   CodeQL.
2. Read back and independently verify D0T-03 platform enforcement.
3. Obtain the required eligible current-head independent approvals.
4. Merge normally without author/admin bypass and rerun exact `main`.
5. Execute and independently review the real Servo-owned D3 exact-image corpus.
6. Continue D4 through D9 strictly in prerequisite and evidence-tier order.
