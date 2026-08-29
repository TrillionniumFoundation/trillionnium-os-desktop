# TrillionniumOS Desktop — current state

**Updated:** 2026-08-29  
**Canonical plan:** `2026-08-29-d6`  
**Repository mode:** `FULL_PRODUCT_REPOSITORY`  
**Integrated implementation stage:** `D0R_D0C06_D0A01_COMPILE_VALIDATED`  
**Machine truth:** `manifests/project-state.v1.json`

## Integrated and demonstrated

The D0 foundation contains the Rust workspace, product-boundary and dependency
locks, layered page revisions, deterministic Agent/human arbitration, synthetic
trusted origins, Browser API contracts, fail-closed validation, and signed
Debian input closure.

The host-validated local control path is:

```text
already-connected AF_UNIX stream
  -> SO_PEERCRED + nonce + sequence + digest transport
  -> bounded canonical Browser API codec
  -> exactly-one request-bound AgentPort handler
  -> default-disabled systemd socket custody
  -> pidfd/procfs/cgroup/unit peer attestation
  -> durable non-replaying receipt facts
```

D0C-02 through D0C-06 are integrated at their declared host/source evidence
tiers. The product socket is disabled by preset, requires an explicit marker,
and the marker is not shipped.

D0A-01 proves exact-pin Servo compile compatibility against commit
`670ae8a70801b162e186f81cbb5bdd2d59c39108`. It is not a visible-frame or
runtime-integration claim.

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

These are historical package/evidence identities. They do not substitute for a
later exact-main rerun when an invalidation input changes.

## Active candidates and blockers

### D1-01 — PR #23

Branch `codex/d1-01-reproducible-qemu-substrate` is based on
`77bfc22619e7d9b30a3736096cf8e604a3c268ac`, behind the current integrated
baseline. Its source must be reconstructed or rebased on current main before
its Debian lock, reproducibility, QEMU PID 1, Wayland, and socket-activation
evidence can be promoted.

Status: `BASE_DRIFT`.

### D0A-02/D2 — PR #27

Branch `codex/d0a02-headed-runtime-v3` contains a substantive headed Servo
candidate, but the latest permanent workflows failed before runtime
qualification: one at the sccache/toolchain bootstrap boundary and one at an
overlay formatting gate. A repaired exact head must compile, run the headed
local fixture, exercise native input/IME and content-process recovery, produce
bounded evidence, then pass again after merge.

Status: `CI_BLOCKED`.

## Explicit non-claims

- no product-owned headed Servo runtime or visible first frame;
- no Debian image, QEMU PID 1, or Wayland boot;
- no integrated D1+D2 image;
- no production AgentPort activation;
- no TaskFlow semantic-principal mapping;
- no BrowserActor/PageOwner dispatch;
- no external navigation, credentials, capabilities, or external effects;
- no signed app runtime or controlled egress;
- no signed update/rollback, fixed-hardware beta, or production release.

## Immediate execution order

1. Close d6 truth/CI gates D0T-01 and D0T-02.
2. Repair and rerun PR #27 to a `MODULE_CLOSED_CANDIDATE`.
3. Reconstruct PR #23 on current main and complete its two-step lock/QEMU gate.
4. Run the combined D1+D2 integrated QEMU image gate.
5. Separate fixture and product AgentPort handlers, then implement D3
   PageOwner/BrowserActor/principal/receipt integration.
6. Continue D4 through D9 in dependency order.
