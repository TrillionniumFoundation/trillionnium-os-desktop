# TrillionniumOS Desktop — current state

**Updated:** 2026-08-30  
**Canonical plan:** `2026-08-29-d6`  
**Repository mode:** `FULL_PRODUCT_REPOSITORY`  
**Integrated implementation stage:** `D0R_D0C06_D0A01_COMPILE_VALIDATED`  
**Machine truth:** `manifests/project-state.v1.json`

## Integrated and demonstrated

D0T-01 and D0T-02 are integrated on main at
`bf6bba2ea1c49b36e11754bf27dc0c56e3da3bd1`. The repository now has one
machine-truth registry, immutable GitHub Action pins, exact locked Rust
commands, and exact-main CI evidence. This does not satisfy D0T-03: protected
main, required checks, organization-team CODEOWNERS, no self-approval/self-merge,
and release-signing dual control still require GitHub organization/repository
settings and independent reviewers.

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

The product `hepta-agent-portd` no longer links or instantiates the fixture
handler. Until D3 binds a real BrowserActor, an attested product activation
fails closed before request decoding or dispatch. The fixture binary is
feature-gated and outside the production installation graph.

D0A-01 proves exact-pin Servo compile compatibility against commit
`670ae8a70801b162e186f81cbb5bdd2d59c39108`. It is not a visible-frame or
runtime-integration claim.

## D0A-02 headed-host module-closure candidate — PR #27

Exact source head `fe0ea6169127ce1f7950618b55374d83834a462c` passed workflow run
`33289966647`, job `99199795258`, against tested merge
`0df9b9c15f51d12f34ef1af288dfae5a009f073f` and tree
`37dc62883d12f3e8917f21545e8223ff809c452d`. The immutable artifact
`9725709890` has digest
`sha256:50ce0bc82723d6c64c8d2ca2ac900651273ef65e85e9f7b7c233e60f8e628978`.

The headed-host evidence demonstrates one native trusted window, one logical
Servo content WebView at a time, loopback-fixture first frame, native pointer,
button, wheel, keyboard and basic IME paths, popup and external-navigation
refusal, exact content-process SIGKILL observation, trusted-chrome survival,
and replacement content generation 2. It does not demonstrate Debian-image
integration, AgentPort or BrowserActor activation, external browsing/effects,
hardware, or release readiness.

Status: `MODULE_CLOSED_CANDIDATE`. It still requires the evidence-promotion
commit to pass on its exact head, merge, and an exact-main rerun before
`D0A-02` can be listed as integrated.

## D1-01 candidate — PR #29; PR #23 superseded

PR #23 is retained only as historical, base-drifted work. The active D1 replay
is PR #29 on branch `codex/d1-01-d6-replay-v1`. Its earlier QEMU evidence
predates the product/fixture physical-separation change and therefore cannot be
promoted. D1 is being reconstructed so qualification traffic uses a physically
separate, qualification-only server while the product daemon remains fail
closed.

Status: `BASE_DRIFT`.

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
- D0T-01/D0T-02 and AgentPort product/fixture separation: main
  `bf6bba2ea1c49b36e11754bf27dc0c56e3da3bd1`, exact-main runs
  `33289882701`, `33289882702`, `33289882703`, `33289882704`,
  `33289882707`, and `33289882733`.

Historical package evidence does not substitute for a later exact-main rerun
when any invalidation input changes.

## Explicit non-claims

- D0A-02 is not yet integrated on main;
- no Debian image, QEMU PID 1, or Wayland boot is integrated;
- no integrated D1+D2 image exists;
- no production AgentPort activation exists;
- no TaskFlow semantic-principal mapping exists;
- no BrowserActor/PageOwner dispatch exists;
- no external navigation, credentials, capabilities, or external effects are authorized;
- no signed app runtime or controlled egress exists;
- no signed update/rollback, fixed-hardware beta, or production release exists.

## Immediate execution order

1. Promote PR #27 evidence, pass the promotion head, merge, and rerun exact main.
2. Reconstruct PR #29 with a qualification-only AgentPort server and rerun the
   two-build plus QEMU PID 1/Wayland/activation corpus.
3. Run the combined D1+D2 integrated QEMU image gate.
4. Implement D3 PageOwner/BrowserActor/principal/receipt integration.
5. Continue D4 through D9 in dependency order.
6. Independently satisfy D0T-03 repository settings and review separation.
