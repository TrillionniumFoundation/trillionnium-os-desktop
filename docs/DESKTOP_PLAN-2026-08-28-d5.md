# TrillionniumOS Desktop — canonical development plan

**Revision:** `2026-08-28-d5`
**Status:** `SUPERSEDED_HISTORICAL` — provenance only; not active or normative
**Active successor:** [`DESKTOP_PLAN-2026-08-29-d6.md`](DESKTOP_PLAN-2026-08-29-d6.md)
**Repository:** `TrillionniumFoundation/trillionnium-os-desktop`
**Repository mode:** `FULL_PRODUCT_REPOSITORY`
**Supersedes:** `2026-08-28-d4`

This revision is retained as historical provenance for the desktop repository.
The active normative plan is d6; this d5 text does not override d6 truth,
contracts, evidence, or claim ceilings. Code, contracts, tests, packaging,
manifests, documentation, and release evidence remain versioned together.
Local absolute paths are development inventory only and never define product
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
| `TOS-D-010` | UI gestures and navigation are not classified as read-only. | Navigation/click/type/press/select on external origins are potential external effects. |
| `TOS-D-011` | Browser traffic uses a controlled egress architecture before external interaction is enabled. | DNS, redirects, service workers, WebSocket, QUIC, and actual peer IP are policy inputs. |
| `TOS-D-012` | WebDriver is development/conformance tooling only unless replaced by an in-process or authenticated UDS adapter. | No production TCP WebDriver listener. |
| `TOS-D-013` | Desktop and mobile authority models are separate. | Android direct shell/ADB and owner-open crates cannot enter the desktop default graph. |
| `TOS-D-014` | Evidence and product claims are separate. | Source, schema, host test, or screenshot never proves a booted or releasable product. |
| `TOS-D-015` | The local AgentPort is packageable but default-disabled. | Unit presence is not an enabled-listener claim; the enable marker is absent until an explicit D1/D3 decision. |

### 0.2 Current implementation checkpoint

The repository is host-validated through `D0C-05`, has a committed signed
D0R-02 Debian input closure, and is compile-qualified through `D0A-01`:

- Rust 1.93 workspace, exact dependency closure, CI, and claim validation;
- neutral contract primitives and layered revision model;
- deterministic Agent/human arbitration and bounded queue;
- authenticated, bounded, nonce/sequence/digest-bound connected AF_UNIX carrier;
- canonical Browser API codec with recursive duplicate-member rejection;
- exactly-one connected AgentPort bridge and request-bound response;
- systemd socket custody, package-created service identities, pidfd/procfs/
  cgroup/unit peer attestation, and a hardened one-request connection service;
- default-disabled preset and an enable marker that is intentionally not
  shipped;
- a signed Debian 13 snapshot lock with the exact amd64 package closure needed
  as the immutable D1 input baseline;
- exact Servo commit `670ae8a70801b162e186f81cbb5bdd2d59c39108`, Servo Rust
  `1.97.1`, official `winit_minimal`, public embedder API probe, and official
  `servoshell` compile success with a zero-patch clean checkout;
- contract schemas, golden vectors, independent references, static audits, and
  exact-head Rust/Servo regression evidence.

The checkpoint proves source behavior, package mappings, signed input closure,
unit syntax, default-closed custody, and Servo compile compatibility. It does
**not** prove a booted image, enabled product listener, Servo startup, a visible
frame, or native input delivery. BrowserActor, external effects, signed apps,
capabilities, update authority, and release signing remain unimplemented or
unclaimed.

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
| `D0R` repository/reproducibility | foundation and signed Debian input closure implemented | deterministic two-build image and QEMU evidence for D1 |
| `D0C` contracts/control core | D0C-01 through D0C-05 host validated | D0C-06 durable receipt journal; D1 live PID 1 socket corpus before enablement |
| `D0A` Servo compatibility | D0A-00 state machine and D0A-01 exact-pin compile gate complete | D0A-02 headed workspace/runtime evidence |
| `D1` Debian QEMU substrate | not demonstrated | reproducible boot into supervised Wayland placeholder plus test-only D0C-05 activation corpus |
| `D2` headed Servo surface | not demonstrated | one visible content surface, native input/IME, popup refusal, crash/restart evidence |
| `D3` PageOwner/BrowserActor | not started | authorized semantic operations, durable receipts, explicit development-profile AgentPort activation |
| `D4` human/Agent collaboration | not started | same live page, formal focus/IME/preemption/recovery corpus |
| `D5` signed trusted apps | not started | isolated synthetic origins and fail-closed signature/revocation/capability checks |
| `D6` capabilities/egress/workers | not started | permit-bound services and complete browser egress mediation |
| `D7` recovery/update/effects | not started | signed rollback plus honest indeterminate-effect reconciliation |
| `D8` fixed-hardware beta | not started | reproducible hardware, security, accessibility, performance, and recovery qualification |

No later stage may waive an earlier trust, contract, reproducibility, or
evidence gate. A source file is not completion; only the observable exit in
`plan/WORK_PACKAGES_AND_GATES.md` advances a work package.

## 3. Immediate execution lock

The D0C-02 through D0C-05 preservation/merge and D0A-01 exact-pin compile items
are complete. The remaining implementation sequence is fixed:

1. `D1-01`: from the committed signed Debian baseline, resolve the complete D1
   closure, build two deterministic image candidates, boot QEMU into
   systemd/Wayland, and run the D0C-05 PID 1 activation corpus in a test-only
   transaction while keeping the immutable product candidate default-disabled.
2. `D0A-02` / D2: prove trusted workspace composition, one Servo content
   surface, local fixture first frame, pointer/keyboard/IME, popup refusal,
   process topology, and crash recovery.
3. `D0C-06`: implement the durable receipt journal before BrowserActor
   operation claims.
4. D3: bind BrowserActor/PageOwner, receipts, intended local Agent principal,
   and explicitly selected development-profile AgentPort activation on local
   fixtures.

D1 package resolution and preparation for the D0A-02 headed runtime may proceed
in parallel where they do not promote runtime claims. External interactive
browsing, persistent credentials, signed app installation, capabilities, update
authority, and external effects remain closed until their explicit D5-D8 gates
are satisfied.

## 4. Claim boundary

The current repository proves the checked-in D0 foundation, the signed D0R-02
input closure, D0C-02 through D0C-05 host behavior, and D0A-01 exact-pin compile
compatibility. It does not prove Servo integration, a visible frame, a bootable
image, live PID 1 socket activation, hardware support, BrowserActor, network
mediation, signed applications, capability enforcement, Secure Boot, rollback,
or beta readiness. Compile compatibility does not imply runtime; QEMU does not
imply bare metal; source signing code does not prove key custody; and a lower
evidence tier never implies a higher product claim. Every promotion must update
`CURRENT_STATE.md`, repository-state, contracts/manifests, tests, and evidence
references atomically.
