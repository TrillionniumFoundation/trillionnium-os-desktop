# TrillionniumOS Desktop — current state

**Updated:** 2026-09-01  
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
signed release. The current `main` head is `78888fac3bee7974138ab1c5e4807511bee7fcbb`;
its root README-clearing commit is unsigned and `main` remains unprotected, so
D0T-03 is still `REPOSITORY_SETTING_REQUIRED`.

## 2. Single convergence candidate — PR #60

Draft PR #60 on `codex/d6-gap-closure-v1` supersedes active development surfaces
PR #32, PR #33, PR #35, and unstable aggregate PR #59. The committed machine
snapshot records the last source object before this truth refresh:

```text
base SHA:       78888fac3bee7974138ab1c5e4807511bee7fcbb
candidate SHA:  e87c63f257c9f660bc0fc104633efb39bcaca320
candidate tree: e3fae0714a12b2876a07e8d332d82bb51907b750
tested merge:   56f7a021bddbc3f9349c9afd2206670a7765853c
```

The candidate is an ordinary Git object. Workflows have read-only repository
permissions, checkout does not persist write credentials, and the four
self-modifying `closure-overlay-bootstrap-v2` through `v5` workflows were
removed. No workflow is allowed to manufacture and push a future review object.

## 3. Core fixes completed in the candidate

### Session arbitration

`SessionMachine::apply` now executes transactionally. A rejected event cannot
leave partially advanced revisions, ownership, navigation source, or lease
state. Every Agent observation, mutation, and navigation admission requires
`Ready + Idle + no human lease`; Human/System source labels cannot relabel
active Agent work. Navigation, cancellation, recovery, and close transitions
maintain explicit ownership invariants.

A bounded integration test explores 31 event forms to depth seven, checks public
ownership invariants after every accepted transition, and compares both the
public snapshot and hidden behavioural signature after every rejected
transition.

### Authenticated transport

The raw framed carrier is private behind a fail-stop facade. Any frame I/O,
deadline, digest, nonce, kind, challenge, or sequence error drops the owned
carrier and permanently poisons the public connection. Later calls return a
stable broken-pipe transport error without attempting byte-stream
resynchronization. Pure local preflight failures do not poison because no byte
has been consumed or emitted.

The exact candidate transport workflow passed the Rust package gate, the
independent Python reference and fault corpus, the golden vector, deterministic
evidence regeneration, and the no-listener/opaque-payload claim ceiling.

## 4. Candidate-only evidence at the recorded source snapshot

### D0A-01 exact-pin Servo

Workflow `33454164032`, artifact `9781017648`, digest
`sha256:1766545a1c872c112c0e46f36133541a3d44735998fad194f05aa8c6bfc11ec6`
passed against the exact Servo lock. This remains compile compatibility only.

### D0A-02 headed host

Workflow `33454164056`, artifact `9781038860`, digest
`sha256:8f027ec3ebebfb0364ccee4f5e72de874903c2386d3c3dab5cba3166f1d4e65f`
reported `PASS_CAUSAL_HEADED_HOST_ONLY`. It bound base/head/tested-merge/tree,
observed the exact generation-1 content PID receive `SIGKILL`, retained trusted
chrome, and produced a distinct generation-2 content process. It excludes
AgentPort, BrowserActor, native clipboard, clean teardown, Debian/QEMU,
external effects, and release claims.

### D1 QEMU substrate

Workflow `33454164165`, artifact `9781049604`, digest
`sha256:9609711473c622301c285468e1f3c5a66c0ac2ea2675c375f157a5d371a5577e`
reported `PASS`. Two independent builds produced identical rootfs tar,
rootfs manifest, ext4, kernel, initrd, and package lock. Q35/TCG booted systemd
PID 1, udev, D-Bus, logind, and the supervised Wayland placeholder without a
network device. The qualification-only AgentPort proved default-disabled state,
authorized and unauthorized cases, per-connection teardown, connection-kill
recovery, marker/socket removal, and clean poweroff. It did not start Servo or
create a visible product window.

### D2I integrated image

Workflow `33454164136`, artifact `9781160555`, digest
`sha256:b840c33e30fcbb1bf267967a88af17c6681daa0fdd89111593900ca0b60274b2`
reported `PASS_CANDIDATE_REQUIRES_REVIEW_AND_EXACT_MAIN`. It rebuilt the
D1 substrate, built the exact Servo runtime, prepared the integrated image
twice with byte equality, and booted Q35/TCG without a network device. The
guest reached the local Servo fixture, verified page input and basic IME,
retained trusted chrome after an externally selected generation-1 content PID
received `SIGKILL`, and created a distinct generation-2 replacement. The
strict claim field `actual_content_process_crash_currently_proven` remains
`false` because no Servo pipeline-panic callback was observed; product
AgentPort, external effects, hardware, Secure Boot, and release remain false.

All artifacts above are PR synthetic-merge evidence with
`promotion_authoritative: false`. This truth-refresh commit invalidates their
exact-head identity and requires one final current-head rerun.

## 5. D3 source state and remaining executable blocker

The candidate contains the typed PageOwner/BrowserActor core, TaskFlow principal
binding, bounded queues, revision and stale-target checks, cancellation/deadline
paths, durable receipt observer, local-fixture runtime, and an explicitly
selected development-profile AgentPort binary.

Live development activation remains fail closed. The systemd service runs as
`hepta-browserd`, while the attested peer runs as `hepta-agent`. Linux
`PTRACE_MODE_READ_FSCREDS` denies cross-UID `/proc/<pid>/exe` reads, and the
service intentionally has no `CAP_SYS_PTRACE`. Qualification-only static
attestation is not promoted into the D3 live profile. The canonical status is
therefore `BLOCKED_UPSTREAM_CROSS_UID_PROCFS`, with
`development_source_wiring_only: true` and
`development_static_attestation_available: false`.

Resumption requires an independently reviewed mechanism that preserves distinct
service identities and binds the semantic principal to an unforgeable live
process identity without widening browser authority. It must then be exercised
inside the exact D2I image together with authorized/unauthorized principal,
page observation/action, revision, cancellation/deadline, crash, journal
recovery, and indeterminate-receipt cases.

## 6. Later-stage source versus product evidence

D4-D9 source/reference workflows pass their bounded contracts and deliberately
retain negative promotion results. They do not close their product gates:

- D4 still depends on a promoted D3 same-PageOwner runtime corpus;
- D5 needs signed-app runtime integration and persistent storage/service-worker
  enforcement;
- D6 needs installed network namespace, resolver, proxy, redirect, connected
  peer-IP, portal, and bypass controls;
- D7 needs a real persistent effect executor, boot/update slots, rollback
  counter, recovery media, and power-loss corpus;
- D8 needs independent fixed-BOM hardware, 24/72-hour stability, and repeated
  power-loss evidence;
- D9 needs protected release governance, offline HSM custody, independent
  signers/attestors/promoter, signed immutable artifacts, anti-rollback, and
  controlled publication.

## 7. Historical provenance

PR #27 remains historical headed-host provenance. PR #23, PR #29, and PR #32
are historical D1 attempts. PR #33 and PR #35 are superseded candidate
surfaces. PR #59 is superseded because its head and review identity were
unstable and it contained workflows capable of writing future source objects.
None substitutes for final PR #60 exact-head, independent-review, merge, and
exact-main evidence.

## 8. Promotion sequence

1. Finish the truth refresh and pass every exact-head PR #60 workflow.
2. Freeze that head and publish its exact source/base/tree/tested-merge and
   artifact identities in the PR record.
3. Configure protected-main/ruleset/CODEOWNERS/environment controls and capture
   reviewed settings evidence.
4. Obtain latest-push independent non-author approval; no self-approval,
   self-merge, or administrator bypass.
5. Merge only after all required checks pass, then rerun exact main and update
   integrated machine truth.
6. Resolve D3 live attestation and run the exact integrated-image D3 corpus.
7. Continue D4 through D9 strictly in prerequisite order.
