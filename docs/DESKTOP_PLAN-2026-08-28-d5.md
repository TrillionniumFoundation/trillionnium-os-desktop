# TrillionniumOS Desktop — canonical development plan

**Revision:** `2026-08-28-d5`
**Status:** ACTIVE — implementation-ready product plan
**Repository:** `TrillionniumFoundation/trillionnium-os-desktop`
**Repository mode:** `FULL_PRODUCT_REPOSITORY`
**Supersedes:** `2026-08-28-d4`

This revision converts the desktop repository from a documentation-only design
baseline into the canonical product tree. Code, contracts, tests, packaging,
manifests, documentation, and release evidence are versioned together. Local
absolute paths are development inventory only and never define product
identity.

## 0. Executive implementation lock

TrillionniumOS Desktop is a Debian-based AI-native desktop appliance. It is not
a Linux-kernel fork, an Android desktop profile, a general Linux compatibility
promise, or a browser process with ambient machine authority.

The product has one visible workspace with two explicit trust surfaces:

```text
trusted desktop shell/chrome
    + exactly one untrusted Servo content WebView
    + one Agent/human PageOwner for that content WebView
```

The shell cannot be replaced by external navigation. Agent and human input
operate on the same content WebView, DOM, JavaScript state, storage, history,
and document identity. A second hidden Agent page, hidden automation browser,
or independent browser control endpoint is forbidden. Servo may use supervised
content/network/GPU subprocesses for isolation; “one browser” means one logical
content session and PageOwner, not one operating-system PID.

System authority remains outside Servo:

```text
UEFI / Secure Boot
  -> Debian kernel, initramfs, firmware, rootfs
  -> systemd, udev, logind, D-Bus
  -> Wayland compositor, PipeWire, network/storage services
  -> hepta-sessiond (unprivileged session supervision)
  -> hepta-browserd (one content PageOwner)
  -> signed trusted shell/app surfaces
  -> typed capability services and WASI workers
  -> hepta-updated (separate minimal privileged update authority)
```

No runtime daemon that handles webpage input may also hold image-signing keys
or unrestricted update authority.

### 0.1 Non-negotiable product decisions

| ID | Decision | Enforced consequence |
| --- | --- | --- |
| `TOS-D-001` | This repository is the full product repository. | No second implementation checkout or external canonical docs tree. |
| `TOS-D-002` | Debian 13 `trixie` is the initial base; a signed snapshot is required before D1 promotion. | No rolling host package graph and no image claim from a point-release label alone. |
| `TOS-D-003` | Servo is the only content browser engine in the baseline. | No Chromium fallback and no Obscura engine crates in the runtime. |
| `TOS-D-004` | One visible workspace contains a trusted shell surface and one untrusted content WebView. | External navigation cannot replace or share a DOM trust domain with system chrome. |
| `TOS-D-005` | One content `PageOwner` owns Agent and human operations. | No hidden second page, independent WebDriver listener, or page migration. |
| `TOS-D-006` | Servo subprocesses are allowed for isolation. | Product tests count logical sessions and control endpoints, not PIDs. |
| `TOS-D-007` | Trusted apps use distinct synthetic HTTPS tuple origins. | No `hepta://app/<publisher>/<id>` path-only same-origin ambiguity. |
| `TOS-D-008` | Revisions are layered. | Ordinary DOM commits advance `mutation_epoch`, not global document identity. |
| `TOS-D-009` | Human/Agent arbitration is a formal state machine with monotonic leases. | Focus, IME, modal, navigation, capability, cancellation, and recovery transitions are testable. |
| `TOS-D-010` | UI gestures are not classified as read-only. | Click/type/press/select on external origins are potential external effects. |
| `TOS-D-011` | Browser traffic uses a controlled egress architecture before external interaction is enabled. | DNS, redirects, service workers, WebSocket, QUIC, and actual peer IP are policy inputs. |
| `TOS-D-012` | WebDriver is development/conformance tooling only unless replaced by an in-process or authenticated UDS adapter. | No production TCP WebDriver listener. |
| `TOS-D-013` | Desktop and mobile authority models are separate. | Android direct shell/ADB and owner-open crates cannot enter the desktop default graph. |
| `TOS-D-014` | Evidence and product claims are separate. | Source, schema, host test, or screenshot never proves a booted or releasable product. |

### 0.2 Current implementation checkpoint

This repository revision implements the D0 foundation:

- Rust workspace and toolchain lock;
- neutral contract primitives;
- browser-domain types and error taxonomy;
- layered revisions and deterministic arbitration state machine;
- bounded queue;
- contract schemas and golden vectors;
- Servo, Debian, repository-state, and product-boundary manifests;
- non-networked browserd self-check;
- CI and repository validation.

It does not implement Servo, a listener, a Debian image, external effects,
signed apps, capabilities, or release signing.

## 1. Normative plan assembly

This plan is intentionally modular. The following files are normative parts of
revision `2026-08-28-d5` and must be changed atomically when a decision crosses
their boundaries:

1. [`plan/PRODUCT_ARCHITECTURE.md`](plan/PRODUCT_ARCHITECTURE.md) — product
   promise, trusted/untrusted surface topology, desktop/mobile separation,
   runtime authority split, and repository layout.
2. [`plan/CONTRACT_SECURITY_TESTING.md`](plan/CONTRACT_SECURITY_TESTING.md) —
   Browser API, authenticated AgentPort, error and receipt contracts, layered
   revisions, arbitration, controlled egress, effect gates, and qualification
   evidence.
3. [`plan/WORK_PACKAGES_AND_GATES.md`](plan/WORK_PACKAGES_AND_GATES.md) —
   file-level work packages, dependencies, observable exits, governance, risk
   register, execution order, and claim boundary.
4. [`adr/`](adr/) — locked architectural decisions that explain why the
   normative direction was selected.
5. [`../contracts/`](../contracts/) and [`../manifests/`](../manifests/) —
   machine-readable wire, evidence, input, and product-boundary contracts.

The main plan controls product identity, non-negotiable decisions, current
checkpoint, stage ordering, and plan precedence. The annexes provide the full
implementation detail; they are not optional commentary.

## 2. Stage board

| Stage | Current state | Promotion gate |
| --- | --- | --- |
| `D0R` repository/reproducibility | foundation implemented | resolved Debian snapshot and automated graph/claim checks remain required for D1 |
| `D0C` contracts/control core | `D0C-01` implemented | `D0C-02` authenticated bounded UDS and `D0C-03` receipt journal |
| `D0A` Servo compatibility | pure state machine implemented | `D0A-01` pinned Servo embedder spike, then `D0A-02` trusted-shell/content composition |
| `D1` Debian QEMU substrate | not started | reproducible boot into supervised Wayland placeholder session |
| `D2` headed Servo surface | not started | one visible content WebView, native input, crash/restart evidence |
| `D3` PageOwner/AgentPort | not started | authenticated semantic operations and receipts on local fixtures |
| `D4` human/Agent collaboration | not started | same live page, formal focus/IME/preemption/recovery corpus |
| `D5` signed trusted apps | not started | isolated synthetic origins and fail-closed signature/capability checks |
| `D6` capabilities/egress/workers | not started | permit-bound services and complete browser egress mediation |
| `D7` recovery/update/effects | not started | signed rollback plus honest indeterminate-effect reconciliation |
| `D8` fixed-hardware beta | not started | reproducible hardware, security, accessibility, performance, and recovery qualification |

No later stage may be used to waive an earlier trust, contract, reproducibility,
or evidence gate. A source file is not completion; only the observable exit in
`plan/WORK_PACKAGES_AND_GATES.md` advances a work package.

## 3. Immediate execution lock

The next implementation sequence is fixed:

1. `D0A-01`: compile the pinned Servo commit and prove one headed content
   WebView, event-loop pumping, native input, navigation callbacks, and process
   topology on the development host.
2. `D0A-02`: compose trusted native/system chrome and the single untrusted
   content WebView in one visible workspace without shared DOM authority.
3. `D0C-02`: implement local authenticated UDS transport with peer identity,
   per-session nonce binding, bounded strict frames, absolute deadlines,
   cancellation, and response binding; expose no TCP/WebDriver product port.
4. `D1-01`: resolve and verify the Debian repository snapshot, then build the
   first deterministic QEMU image and supervised Wayland placeholder session.

`D0A-01` and contract-only parts of `D0C-02` may proceed in parallel. External
interactive browsing, persistent credentials, signed app installation, and
external effects remain closed until their explicit gates are satisfied.

## 4. Claim boundary

The current repository proves only the checked-in D0 foundation and whatever
its local/CI checks directly execute. It does not prove Servo integration, a
bootable image, hardware support, AgentPort authentication, network mediation,
signed applications, capability enforcement, Secure Boot, rollback, or beta
readiness. Every promotion must update `CURRENT_STATE.md`, repository-state,
contracts/manifests, tests, and evidence references atomically.
