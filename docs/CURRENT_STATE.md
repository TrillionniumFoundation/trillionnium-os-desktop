# TrillionniumOS Desktop — current state

**Updated:** 2026-08-29  
**Canonical plan:** `2026-08-28-d5`  
**Repository mode:** `FULL_PRODUCT_REPOSITORY`  
**Implementation stage:** `D0R_D0C06_D0A01_COMPILE_VALIDATED`

## Implemented and demonstrated

The D0 foundation contains the Rust workspace, layered page revisions,
deterministic Agent/human arbitration, synthetic trusted origins, Browser API
contracts, an exact Cargo dependency closure, and fail-closed product/evidence
validation.

### Signed Debian inputs

D0R-02 is complete for Debian snapshot `20260828T000000Z` on `amd64`. The
committed lock contains 319 exact packages and package-set digest
`89918a968afafdbabe03e43794565cb1dc936f3f24a09ec81030be4a4085333a`.
This proves signed inputs and a dependency closure only; it does not imply a
rootfs, disk image, systemd boot, or Wayland session.

### Local Agent control substrate

The host-validated control path is:

```text
already-connected AF_UNIX stream
  -> SO_PEERCRED + nonce + sequence + digest transport
  -> bounded canonical Browser API codec
  -> exactly-one request-bound AgentPort handler
  -> default-disabled systemd socket custody
  -> pidfd/procfs/cgroup/unit peer attestation
```

D0C-02 supplies the authenticated bounded carrier. D0C-03 supplies canonical
messages. D0C-04 binds one validated request to one typed result and canonical
response. D0C-05 supplies hardened systemd custody and exact peer attestation.
The product socket remains disabled by preset, requires
`/etc/hepta/enable-agent-port`, and the marker is not shipped.

### Durable receipts

D0C-06 candidate `25d2d5882018b9974fc360aaf646128c6b6f175f` passed permanent workflow
run `33235926577`, together with desktop CI, Browser codec/reference regression,
and custody regression in runs `33235926576`, `33235926596`, and `33235926613`.

The demonstrated receipt substrate provides bounded versioned framing,
SHA-256 record and segment chains, strict lifecycle transitions, a
crash-recoverable single-writer lease, durable append ordering, poisoned-writer
recovery, torn-tail repair distinct from hard corruption, typed storage-full
handling, privacy-redacted export, quiescent rotation, and safe retention
selection. Unresolved potential external effects are always
`never_automatic`. The journal has no operation execution or replay API.
Evidence: `docs/evidence/2026-08-29-d0c06-durable-receipts.md`.

### Servo compile compatibility

D0A-01 candidate `01d02d692c573ccde7a99d990f2a63235d9bc69f` passed workflow run
`33230713426`, job `99042937091`, against Servo commit
`670ae8a70801b162e186f81cbb5bdd2d59c39108` with Servo's Rust `1.97.1` and
locked Cargo graph. The official `winit_minimal`, the Trillionnium public API
probe, and official `servoshell` compiled from a clean zero-patch checkout.
The status is strictly `PASS_COMPILE_COMPATIBILITY_ONLY`.

## Exact-head control-plane evidence

- D0C-02: head `786debc12aa8d790b231397c1a3341fbf89de080`, run `33167838644`.
- D0C-03: head `4cfebbe6a40ebbec32d9d1bcbfca1d513b510ebb`, run `33176689873`.
- D0C-04: head `5abd71db79b75e400c1c1d7cb0eac85a68041cae`, run `33179346462`.
- D0C-05: head `7be7121b1d2593a0e708ec9ade189ef84ab245da`, runs `33190387511`,
  `33190387553`, and `33190387564`.
- D0C-06: head `25d2d5882018b9974fc360aaf646128c6b6f175f`, runs `33235926576`,
  `33235926577`, `33235926596`, and `33235926613`.

## Not implemented or claimed

- Servo is compile-compatible but no product-owned headed runtime has started it.
- No visible first frame, native pointer/keyboard/wheel/IME delivery, live popup
  refusal, or content crash recovery has been demonstrated.
- The product AgentPort listener remains disabled and has not been started in a
  released product profile.
- QEMU PID 1, Wayland, authorized/unauthorized socket activation, teardown, and
  recovery evidence is not yet promoted.
- No TaskFlow semantic principal is mapped to the local mechanism identity.
- No BrowserActor semantic observe/act dispatch exists in the demonstrated
  product.
- No external navigation, credential use, capability, or web effect is
  authorized.
- No signed app runtime, Secure Boot, A/B update/rollback, fixed-hardware beta,
  or production release claim exists.

## Active next work

1. Finish D1-01 from the signed Debian closure: two deterministic builds, QEMU
   systemd PID 1, headless Wayland, and the test-only D0C-05 activation corpus,
   while the release candidate remains default-disabled and networkless.
2. Complete D0A-02/D2: product-owned trusted workspace, exactly one Servo
   content surface, local-fixture first frame, screenshot evidence, native
   pointer/keyboard/wheel/IME, popup refusal, and content crash recovery.
3. Bind BrowserActor/PageOwner and an explicitly selected development AgentPort
   only after the runtime gates pass, recording every admitted lifecycle fact in
   D0C-06.
4. Keep external credentials, capabilities, navigation effects, update
   authority, and release claims closed until their D5–D8 gates pass.
