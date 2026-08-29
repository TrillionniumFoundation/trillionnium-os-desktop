# TrillionniumOS Desktop — current state

**Updated:** 2026-08-29  
**Canonical plan:** `2026-08-28-d5`  
**Repository mode:** `FULL_PRODUCT_REPOSITORY`  
**Implementation stage:** `D0R_D0C05_D0A01_COMPILE_VALIDATED`

## Implemented and demonstrated

The D0 foundation includes the Rust workspace, layered revisions, deterministic
Agent/human arbitration, synthetic trusted origins, browser contracts, an exact
Cargo dependency closure, and fail-closed product/evidence validation.

The signed Debian input gate is complete at snapshot `20260828T000000Z` for
`amd64`: the committed D0R-02 lock contains 319 exact packages and package-set
digest
`89918a968afafdbabe03e43794565cb1dc936f3f24a09ec81030be4a4085333a`.
This remains input/closure evidence only; no rootfs, disk image, or boot claim is
inferred from it.

The local Agent control path is host-validated through D0C-05:

```text
already-connected AF_UNIX stream
  -> SO_PEERCRED + nonce + sequence + digest transport
  -> bounded canonical Browser API codec
  -> exactly-one request-bound AgentPort handler
  -> default-disabled systemd socket custody
  -> pidfd/procfs/cgroup/unit peer attestation
```

D0C-02 provides the connected-stream carrier. D0C-03 provides the canonical
Browser API message boundary. D0C-04 binds one validated request to one typed
handler result and canonical response. D0C-05 adds package-created service
identities, one hardened inherited-stream process per accepted connection,
exact runtime peer attestation, and Debian/systemd packaging.

The socket definition remains closed by default:

- preset: `disable hepta-browserd-agent.socket`;
- required marker: `/etc/hepta/enable-agent-port`;
- marker shipped by the repository/image inputs: **no**;
- product listener demonstrated: **no**.

## Exact-head qualification

### D0A-01 Servo compile compatibility

Candidate `01d02d692c573ccde7a99d990f2a63235d9bc69f` passed workflow run
`33230713426`, job `99042937091`, against exact upstream Servo commit
`670ae8a70801b162e186f81cbb5bdd2d59c39108`.

Using Servo's Rust `1.97.1` toolchain and locked Cargo graph, the gate passed:

- locked Cargo metadata;
- the official `winit_minimal` embedder;
- the Trillionnium public embedder API probe;
- the official `servoshell`;
- exact source hashes, a clean checkout, and a zero-patch ledger;
- a tracked-only repository consistency validation.

The promoted status is strictly `PASS_COMPILE_COMPATIBILITY_ONLY`. Machine
evidence is
`docs/evidence/generated/d0a01-servo-qualification-result.json`; the review
record is `docs/evidence/2026-08-29-d0a01-servo-exact-pin.md`.

### D0C-02

Candidate `786debc12aa8d790b231397c1a3341fbf89de080` passed Ubuntu 24.04 /
Rust 1.93.0 workflow run `33167838644`. Evidence:
`docs/evidence/generated/d0c02-rust193-host-result.json`.

### D0C-03

Candidate `4cfebbe6a40ebbec32d9d1bcbfca1d513b510ebb` passed formatting, Clippy
with warnings denied, all workspace tests, the browserd self-check, the 27-case
independent reference corpus, and the source/contract audit in workflow run
`33176689873`. Evidence:
`docs/evidence/generated/d0c03-rust193-host-result.json`.

### D0C-04

Candidate `5abd71db79b75e400c1c1d7cb0eac85a68041cae` passed the 44-check
D0C-04 source/contract audit, Rust 1.93.0 formatting, Clippy, 45 workspace tests,
and the integrated browserd self-check in workflow run `33179346462`.
Evidence: `docs/evidence/generated/d0c04-rust193-host-result.json`.

### D0C-05

Source head `7be7121b1d2593a0e708ec9ade189ef84ab245da` passed:

- permanent custody workflow `33190387511`, job `98914075761`;
- repository-wide desktop CI `33190387553`;
- codec/reference and exact-head Rust regression `33190387564`.

The gates covered repository validation, the fail-closed custody audit,
`systemd-sysusers`, `systemd-analyze verify`, Rust 1.93.0 formatting, Clippy
with warnings denied, complete workspace tests, browserd self-check,
`hepta-agent-portd` self-check, and the no-listener/no-effect claim ceiling.
Evidence: `docs/evidence/generated/d0c05-rust193-host-result.json`.

## Not implemented or claimed

- Servo is compile-compatible at the exact pin but is not integrated or started
  by a product-owned headed runtime.
- No window, visible first frame, native pointer/keyboard/wheel/IME delivery,
  popup refusal, or content crash recovery has been demonstrated.
- The systemd socket is not enabled and no product listener has been started.
- QEMU PID 1 activation, authorized/unauthorized live socket tests, teardown,
  and recovery have not yet been demonstrated.
- No TaskFlow semantic principal is mapped to the local mechanism identity.
- No BrowserActor dispatch or durable receipt journal exists in the
  demonstrated product.
- No external navigation, capability, credential use, or web effect is
  authorized.
- No signed app runtime, Secure Boot, update/rollback, beta, or release claim
  exists.

## Active next work

1. Complete D1-01 using the signed Debian snapshot: resolve the full D1 package
   closure, build two deterministic candidates, boot QEMU into systemd/Wayland,
   and execute the D0C-05 PID 1 activation corpus in a test-only transaction
   while the immutable product candidate remains default-disabled.
2. Complete D0A-02/D2 trusted workspace composition, one Servo content surface,
   local fixture first frame, native pointer/keyboard/IME, popup refusal, and
   crash recovery.
3. Implement D0C-06 durable, hash-chained, crash-consistent receipts before any
   BrowserActor operation claim.
4. Bind BrowserActor/PageOwner and an explicitly selected development-profile
   AgentPort only after the preceding runtime and receipt gates pass.
5. Keep external credentials, capabilities, navigation effects, update
   authority, and release claims closed until their explicit D5-D8 gates pass.
