# TrillionniumOS Desktop — current state

**Updated:** 2026-08-29  
**Canonical plan:** `2026-08-28-d5`  
**Repository mode:** `FULL_PRODUCT_REPOSITORY`  
**Implementation stage:** `D0R02_INPUT_VALIDATED_D0C05_HOST_VALIDATED`

## Implemented and demonstrated

The D0 foundation includes the Rust workspace, layered revisions, deterministic
Agent/human arbitration, synthetic trusted origins, browser contracts, exact
Cargo dependency closure, fail-closed product/evidence validation, and a signed
immutable Debian package input closure.

The local Agent path remains host-validated through D0C-05:

```text
already-connected AF_UNIX stream
  -> SO_PEERCRED + nonce + sequence + digest transport
  -> bounded canonical Browser API codec
  -> exactly-one request-bound AgentPort handler
  -> default-disabled systemd socket custody
  -> pidfd/procfs/cgroup/unit peer attestation
```

The socket remains closed by default: its preset disables it, the required
`/etc/hepta/enable-agent-port` marker is not shipped, and no product listener is
claimed.

## D0R-02 signed immutable Debian inputs

Source head `6825f9bd4bd012212559d187315bca285a6ae3d2` passed workflow run
`33196743127`. `manifests/debian-snapshot.lock.v1.json` proves snapshot
`20260828T000000Z`, three exact signed `InRelease` records,
`319` downloaded and metadata-verified packages,
and package-set SHA-256 `89918a968afafdbabe03e43794565cb1dc936f3f24a09ec81030be4a4085333a`. All rootfs, image, QEMU,
Wayland, Secure Boot and product-ready claims remain false.

## Existing exact-head host validation

- D0C-02: head `786debc12aa8d790b231397c1a3341fbf89de080`, run `33167838644`.
- D0C-03: head `4cfebbe6a40ebbec32d9d1bcbfca1d513b510ebb`, run `33176689873`.
- D0C-04: head `5abd71db79b75e400c1c1d7cb0eac85a68041cae`, run `33179346462`.
- D0C-05: head `7be7121b1d2593a0e708ec9ade189ef84ab245da`, permanent custody,
  repository-wide CI and codec/reference regression evidence committed under
  `docs/evidence/generated/`.

## Not implemented or claimed

- No deterministic rootfs or disk image has been built from the committed lock.
- QEMU PID 1 activation, live authorized/unauthorized socket tests, teardown,
  recovery and the supervised Wayland placeholder are not demonstrated.
- No product AgentPort listener is enabled.
- No BrowserActor dispatch or Servo runtime exists in the demonstrated product.
- No visible first frame, native input/IME or headed trusted workspace is
  claimed.
- No external navigation, capability, credential use or web effect is
  authorized.
- No signed app runtime, Secure Boot, update/rollback, beta or release claim
  exists.

## Active next work

1. Complete D0A-01 against Servo pin
   `670ae8a70801b162e186f81cbb5bdd2d59c39108` and Servo's own toolchain.
2. Execute D1-01 from the committed Debian lock: build two normalized
   candidates, prove equality, boot QEMU/systemd/Wayland, and run the D0C-05
   PID 1 activation corpus in a test-only image while keeping the product image
   default-disabled.
3. Complete D0A-02/D2 trusted workspace composition, one Servo content surface,
   local first frame, native pointer/keyboard/IME, popup refusal and recovery.
4. Implement D0C-06 durable receipts before BrowserActor operation claims.
5. Keep external credentials, capabilities, navigation effects, update
   authority and release claims closed until their explicit gates pass.
