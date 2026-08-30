# TrillionniumOS Desktop — current state

**Updated:** 2026-08-30<br>
**Canonical plan:** `2026-08-29-d6`<br>
**Repository mode:** `FULL_PRODUCT_REPOSITORY`<br>
**Integrated implementation stage:** `D0R_D0C06_D0A01_COMPILE_VALIDATED`<br>
**Canonical d6 baseline:** `bf6bba2ea1c49b36e11754bf27dc0c56e3da3bd1`<br>
**Machine truth:** `manifests/project-state.v1.json`<br>
**Candidate snapshot:** GitHub API observation `2026-08-30T10:47:03Z`, observed
`origin/main` `afd42c0f90d254dfb7b04d9c45216e879840f95e`

The candidate rows below are committed snapshots, not live GitHub state. A new
main commit, workflow change, input-lock change, or candidate-head change
invalidates the corresponding evidence and requires a fresh exact-head run.

## Integrated and demonstrated

D0T-01 and D0T-02 were integrated at the canonical d6 baseline
`bf6bba2ea1c49b36e11754bf27dc0c56e3da3bd1`. Subsequent main changes touched
their declared invalidation paths, so the historical exact-main evidence must
be refreshed before a new promotion is treated as current. This does not
satisfy D0T-03: protected main, required checks, organization-team CODEOWNERS,
no self-approval/self-merge, and release-signing dual control still require
GitHub settings and independent reviewers.

The D0 foundation contains the Rust workspace, product-boundary and dependency
locks, layered page revisions, deterministic Agent/human arbitration, synthetic
trusted origins, Browser API contracts, fail-closed validation, signed Debian
input closure, and durable non-replaying receipts.

The host-validated local control path is:

```text
already-connected AF_UNIX stream
  -> SO_PEERCRED + nonce + sequence + digest transport
  -> bounded canonical Browser API codec
  -> exactly-one request-bound AgentPort core
  -> default-disabled systemd socket custody
  -> pidfd/procfs/cgroup/unit peer attestation
  -> durable non-replaying receipt facts
```

The product `hepta-agent-portd` does not link or instantiate the fixture
handler. The D3 development candidate now contains a source-level
PageOwner/BrowserActor boundary, attested principal binding, receipt
observation, and an explicitly selected development AgentPort profile. Those
changes are not D3 gate evidence: the production daemon remains
default-disabled and fails closed before request decoding or dispatch, the
development socket is opt-in and local-fixture-only, and the fixture binary is
feature-gated and outside the production installation graph.

D0A-01 proves exact-pin Servo compile compatibility against commit
`670ae8a70801b162e186f81cbb5bdd2d59c39108`. It is not a visible-frame or
runtime-integration claim.

## Active candidate snapshot

| Gate | Candidate | Head / tested merge | Base | Status and claim ceiling |
| --- | --- | --- | --- | --- |
| D0A-02 | PR #33, `codex/d0a02-proof-soundness-v4` | `f29e0989335654dfc52ca1dbd049ae1f128d4c59` / `a81f1d93ef69d73cee4239625146c991c01825f3` | `afd42c0f90d254dfb7b04d9c45216e879840f95e` | `MODULE_CLOSED_CANDIDATE`; headed host/local fixture only, no image, AgentPort, or external effects |
| D1-01 | PR #32, `codex/d1-01-current-main-v2` | `ec5e8b2caaac8981d6cdf73dae8b3c4004e6ebd0` / `c5650e892796a6864d83e8ffc6317edc291725ae` | `afd42c0f90d254dfb7b04d9c45216e879840f95e` | `BASE_DRIFT`; candidate QEMU/image evidence is not promoted |
| D2I-01 | PR #35, `codex/d2i-current-main-v1` | `14a045cb1e17841a662c59f8ec0e676e86cfec56` / none | `afd42c0f90d254dfb7b04d9c45216e879840f95e` | `BLOCKED_UPSTREAM`; source coexistence only, no integrated-image evidence |

### D0A-02 proof-soundness candidate — PR #33

The candidate's permanent workflow run `33304160993` produced artifact
`9729987669` with digest
`sha256:bcac5c08dcc4af839b0da3da52d73b0e59e8d80be5767750a243fdaff280e290`.
Its bounded headed-host corpus proves one trusted window, one authoritative
loopback-fixture WebView at a time, native pointer/button/wheel/keyboard/basic
IME paths, popup/navigation denial, causal content-process replacement, and
trusted-chrome survival. Native clipboard is intentionally outside this
headed-host gate and remains a D4 ownership/lease/drag-drop requirement.
Bounded clean Servo teardown and child reaping are also outside this gate; the
candidate claim ceiling retains `no_native_clipboard` and `no_clean_teardown`.
It does not prove Debian/QEMU integration,
BrowserActor, AgentPort activation, external effects, hardware, or release
readiness.

Status remains `MODULE_CLOSED_CANDIDATE`: independent security review,
D0T-03 settings, reviewed merge, and an exact-main rerun are still required.
The snapshot was observed against `afd42c0`; later main commits invalidate it.

### D1-01 current-main candidate — PR #32

The candidate's permanent workflow run `33304391615` produced artifact
`9730059502` with digest
`sha256:246d18c84dfc0f85ed91cb8bb8018698695002eed259ac41f2003b53ea4639ba`.
The evidence describes the signed package lock, two-build normalized image
comparison, Q35/TCG `-nic none` boot, systemd PID 1/Wayland, qualification-only
AgentPort activation, authorization/denial, teardown, recovery, marker removal,
and clean poweroff. It does not prove Servo startup, an integrated D1+D2 image,
external effects, hardware, or release readiness.

Status remains `BASE_DRIFT` until this candidate is rebased/reconstructed on the
latest main and its exact-main evidence is rerun. No QEMU/image claim is
promoted by this snapshot.

### D2I source candidate — PR #35

PR #35 composes D1 and D0A-02 source heads only. It intentionally contains no
integrated-image workflow, runtime receipt, or promotion claim. D2I remains
`BLOCKED_UPSTREAM` until promoted D0A-02 and D1 inputs are available.

## D3 source foundation — development-only, not live

The current development candidate contains the first source foundation for
D3-01:

- an engine-neutral `PageOwner`/`BrowserActor` ownership and typed-dispatch
  boundary with session, document, snapshot, and mutation revision checks;
- attested TaskFlow-principal binding that includes the mechanism identity and
  executable digest;
- D0C-06 receipt lifecycle observation with cancellation, deadlines, and
  indeterminate-outcome handling; and
- a separate, explicitly selected development AgentPort binary and systemd
  socket that accepts deterministic loopback fixtures only.

Semantic `page_act` dispatch remains intentionally fail closed in this source
candidate. `PageRuntime::dispatch_page_act` requires a runtime-owned atomic
frame/structure re-resolution and returns `unsupported` by default; the
deterministic development runtime has no DOM resolver. A Servo resolver and
its ambiguity/structure regression corpus are required before D3 can claim
semantic-action execution.

This is a source-level development profile, not a live product activation and
not a promoted gate. No D3 candidate PR/head, integrated-image run, or exact
main evidence is recorded in machine truth yet; those identities must be
updated only after the development PR reaches its final head and its evidence
is independently reviewed. D3-01 therefore remains `BLOCKED_UPSTREAM` until
D2I is promoted and the exact integrated-image principal/dispatch/receipt
corpus passes. The source work does not authorize production credentials,
external navigation/effects, a TCP or WebDriver listener, or any later-stage
claim.

## Historical candidate references

These references are retained for provenance and are not active gate evidence:

- PR #27 / `codex/d0a02-headed-runtime-v3` merged at `e25c42ef69fc2968ac2d1b002cc53f15de2e9e0f`; its headed-host evidence is
  `MERGED_HISTORICAL` and superseded by PR #33.
- PR #29 / `codex/d1-01-d6-replay-v1` closed unmerged at head
  `95fe921c833dea9560d4b1492781795c589d6140`; it is
  `SUPERSEDED_HISTORICAL` by PR #32.
- PR #23 / `codex/d1-01-reproducible-qemu-substrate` closed unmerged at head
  `9250fcb9df75792c39e85e0113cecac8b393a544`; it is
  `SUPERSEDED_HISTORICAL` by PR #32.

## Exact historical evidence

- D0C-02: head `786debc12aa8d790b231397c1a3341fbf89de080`, run `33167838644`.
- D0C-03: head `4cfebbe6a40ebbec32d9d1bcbfca1d513b510ebb`, run `33176689873`.
- D0C-04: head `5abd71db79b75e400c1c1d7cb0eac85a68041cae`, run `33179346462`.
- D0C-05: head `7be7121b1d2593a0e708ec9ade189ef84ab245da`, runs
  `33190387511`, `33190387553`, and `33190387564`.
- D0C-06: head `25d2d5882018b9974fc360aaf646128c6b6f175f`, runs
  `33235926576`, `33235926577`, `33235926596`, and `33235926613`.
- D0A-01: head `01d02d692c573ccde7a99d990f2a63235d9bc69f`, run
  `33230713426`, job `99042937091`.
- D0T-01/D0T-02 and AgentPort fixture separation: baseline main
  `bf6bba2ea1c49b36e11754bf27dc0c56e3da3bd1`, exact-main runs
  `33289882701`, `33289882702`, `33289882703`, `33289882704`,
  `33289882707`, and `33289882733`.

Historical package evidence does not substitute for a later exact-main rerun
when any invalidation input changes.

## Explicit non-claims

- no headed Servo runtime is integrated on main;
- no Debian image, QEMU PID 1, or Wayland boot is integrated on main;
- no integrated D1+D2 image exists;
- no production AgentPort activation exists;
- no production TaskFlow semantic-principal activation exists (the development
  profile's source-level attestation is not a production claim);
- no integrated-image BrowserActor/PageOwner dispatch exists;
- no external navigation, credentials, capabilities, or external effects are authorized;
- no signed app runtime or controlled egress exists;
- no signed update/rollback, fixed-hardware beta, or production release exists.

## Immediate execution order

1. Refresh D0T-01/D0T-02 exact-main truth/CI evidence after the invalidating main changes.
2. Rebase/requalify PR #33, obtain independent review and D0T-03 settings evidence, merge, and rerun exact main.
3. Rebase/reconstruct PR #32 on that exact main and rerun the two-build/QEMU corpus.
4. Build and qualify the combined D2I image represented by PR #35.
5. Finalize the D3 development candidate, record its final PR/head and
   evidence identities, run the exact integrated-image principal/dispatch/
   receipt corpus, and obtain independent review before promotion.
6. Continue D4 through D9 in dependency order.
