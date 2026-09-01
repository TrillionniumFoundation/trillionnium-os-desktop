# PR #60 gap-closure candidate evidence snapshot

**Plan revision:** `2026-08-29-d6`  
**Evidence tier:** candidate PR synthetic merge only  
**Promotion authority:** false

## Identity

| Field | Value |
| --- | --- |
| Repository | `TrillionniumFoundation/trillionnium-os-desktop` |
| PR | `#60` |
| Branch | `codex/d6-gap-closure-v1` |
| Base | `78888fac3bee7974138ab1c5e4807511bee7fcbb` |
| Candidate source head | `e87c63f257c9f660bc0fc104633efb39bcaca320` |
| Candidate source tree | `e3fae0714a12b2876a07e8d332d82bb51907b750` |
| Tested synthetic merge | `56f7a021bddbc3f9349c9afd2206670a7765853c` |

This snapshot precedes the machine-truth refresh that cites it. The refresh
therefore requires a new exact-head run and is not automatically covered by the
artifacts below.

## Source and host gates

The exact candidate snapshot passed:

- `desktop-ci` run `33454164142`;
- `agent-transport-reference` run `33454164033`;
- `browser-codec-reference-and-rust-gate` run `33454164174`;
- `receipt-journal` run `33454164130`;
- `agent-port-custody` run `33454164151`;
- `agent-port-path-custody` run `33454164126`;
- `governance-integrity` run `33454164215`;
- `d0t03-source-contract` run `33454163963`;
- D4-D9 source/reference and negative-promotion workflows.

The transport result includes the fail-stop public facade, independent Python
reference, Rust package tests, replay/digest/deadline/poisoning fault vectors,
deterministic golden vector, and no-listener/opaque-payload ceiling.

## Higher candidate evidence

| Gate | Workflow run | Artifact | Artifact digest | Result ceiling |
| --- | ---: | ---: | --- | --- |
| D0A-01 exact Servo pin | `33454164032` | `9781017648` | `sha256:1766545a1c872c112c0e46f36133541a3d44735998fad194f05aa8c6bfc11ec6` | compile compatibility only |
| D0A-02 headed host | `33454164056` | `9781038860` | `sha256:8f027ec3ebebfb0364ccee4f5e72de874903c2386d3c3dab5cba3166f1d4e65f` | causal headed-host local fixture only |
| D1 QEMU substrate | `33454164165` | `9781049604` | `sha256:9609711473c622301c285468e1f3c5a66c0ac2ea2675c375f157a5d371a5577e` | reproducible QEMU image; no Servo/window/hardware/release |
| D2I integrated image | `33454164136` | `9781160555` | `sha256:b840c33e30fcbb1bf267967a88af17c6681daa0fdd89111593900ca0b60274b2` | integrated QEMU local fixture; review/exact-main required |

### D0A-02

The headed-host artifact reports `PASS_CAUSAL_HEADED_HOST_ONLY`. It binds the
exact base, source head, tested merge, tree, workflow and input digests. It
observed an externally selected generation-1 Servo content process receive
`SIGKILL`, trusted chrome remain alive, and a distinct generation-2 content
process appear. Its claim ceiling excludes AgentPort, BrowserActor, native
clipboard, clean teardown, Debian/QEMU integration, external effects, and
release.

### D1

The D1 artifact reports `PASS`. Two independent builds have identical rootfs
tar, rootfs content manifest, ext4 image, kernel, initrd, and package lock.
Q35/TCG booted systemd PID 1, udev, D-Bus, logind and supervised Wayland with
no network device. The qualification-only AgentPort proved default-disabled
state, authorized and unauthorized requests, one-process-per-connection
teardown, connection-kill recovery, marker/socket removal and clean poweroff.
It did not start Servo or create a visible product window.

### D2I

The D2I artifact reports `PASS_CANDIDATE_REQUIRES_REVIEW_AND_EXACT_MAIN`. It
reconstructed the D1 substrate, built exact Servo, prepared two byte-identical
integrated images, and booted the exact image without a network device. It
verified local-fixture page input/basic IME, one logical content surface,
trusted chrome, external navigation/popup refusal, external `SIGKILL` of the
selected generation-1 content PID, and distinct generation-2 replacement.

The stricter field `actual_content_process_crash_currently_proven` remains
false because the Servo pipeline-panic callback was not observed. Product
AgentPort, external navigation/effects, persistent credentials, hardware,
Secure Boot, and release are not authorized.

## Promotion blockers

These artifacts explicitly record `promotion_authoritative: false`. Promotion
requires all of:

1. final truth-refresh exact-head rerun;
2. protected-main/ruleset/required-check and organization-team CODEOWNERS
   evidence;
3. latest-push independent non-author approval;
4. reviewed merge without administrator bypass;
5. exact-main rerun and integrated machine-truth update.

D3-D9 retain their own additional runtime, hardware, HSM, and release blockers.
