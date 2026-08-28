# TrillionniumOS Desktop d5 work packages and gates

**Plan revision:** `2026-08-28-d5`
**Status:** normative component of the active canonical plan
**Repository mode:** `FULL_PRODUCT_REPOSITORY`

This annex is versioned and reviewed atomically with
[`../DESKTOP_PLAN-2026-08-28-d5.md`](../DESKTOP_PLAN-2026-08-28-d5.md). If an
annex conflicts with the executive lock in the main plan, the executive lock
wins until the plan and annex are updated together.

## 10. Work-package plan and gates

### D0R — repository and reproducibility foundation

#### `D0R-01` Full product-tree conversion — IMPLEMENTED

- canonicalize this repository as code + docs + contracts + manifests;
- add license, contribution, security, ownership, and CI files;
- remove local absolute paths from normative product identity.

**Acceptance:** repository validator confirms one active plan and one product
root.

#### `D0R-02` Toolchain and input selections — IMPLEMENTED/PARTIAL

- lock Rust 1.93.0;
- select Debian 13.6/trixie amd64;
- select Servo commit `670ae8a...` for compatibility work;
- record mobile reference commit and dependency exclusions.

**Remaining gate:** Debian snapshot timestamp, signed `InRelease` digests,
key fingerprints, and package-set digest must be resolved before D1.

#### `D0R-03` Graph and claim checks — IMPLEMENTED

- scan Cargo/source graph against forbidden mobile dependencies;
- validate JSON, plan/manifests, error-code alignment, and golden vectors;
- run Rust fmt, Clippy, tests, and browserd self-check in CI.

### D0C — contracts and deterministic control core

#### `D0C-01` Domain contracts — IMPLEMENTED

- browser operation types;
- error taxonomy;
- synthetic trusted origin identity;
- machine-readable schemas and golden requests;
- initial receipt, permit, and app-manifest schemas.

#### `D0C-02` Authenticated wire carrier — NEXT

- strict bounded JSON decoder with duplicate-member rejection;
- UDS listener managed by systemd socket activation;
- peer credentials and unit/cgroup binding;
- protocol negotiation and session nonce;
- absolute deadline and cancellation;
- response/request/session binding;
- fuzz and malformed-frame corpus.

**Exit:** an unauthorized local process, stale nonce, oversized frame, duplicate
key, deadline overrun, or response mismatch is deterministically refused.

#### `D0C-03` Receipt journal — PLANNED

- canonical encoding and digest;
- append sequence and crash recovery;
- redaction and retention;
- indeterminate operation representation.

### D0A — Servo architecture compatibility

#### `D0A-00` Pure state-machine spike — IMPLEMENTED

The current code proves layered revisions, human preemption, IME ownership,
navigation, crash recovery, and bounded queues without claiming Servo support.

#### `D0A-01` Pinned Servo embedder spike — NEXT

At the locked Servo commit, prove on a developer Linux host:

- supported embedder initialization;
- event-loop wake/pump;
- rendering context and one content WebView;
- native pointer, keyboard, wheel, clipboard, basic IME;
- navigation commit and crash callbacks;
- accessibility/semantic-tree access or the exact patch required;
- screenshot and hit-test path;
- popup/new-window interception;
- process topology and supervised shutdown.

**Exit evidence:** source commit, build log, self-contained local fixture, process
map, operation log, and explicit unsupported/patch list.

#### `D0A-02` Trusted shell/content composition — NEXT

Prototype one visible workspace with trusted chrome that remains visible while
the one content WebView navigates. Evaluate native chrome versus isolated shell
WebView. Verify external content cannot access shell DOM/storage/input channel.

**Go/no-go:** if pinned Servo cannot provide the required embedding or semantic
hooks within the agreed patch budget, stop stage promotion and revise the
engine/contract decision explicitly; do not add a hidden fallback.

### D1 — reproducible Debian QEMU substrate

- resolve Debian snapshot and key/digest lock;
- build minimal bootable amd64 disk with stock Debian kernel/initramfs;
- systemd, udev, logind, D-Bus, local seat, diagnostics;
- single-surface Wayland compositor profile;
- deterministic shutdown and service restart;
- publish image manifest and SBOM.

**Exit:** clean CI or controlled builder creates a digest-identical image from
locked inputs; QEMU reaches a Wayland placeholder surface and recovers a killed
user service.

### D2 — headed Servo content shell

- integrate the D0A wrapper into the Debian image;
- record GPU/software mode, Servo commit, process tree, and frame timing;
- local trusted fixture plus manually driven read-only external rendering;
- no Agent listener yet required for first visual bring-up.

**Exit:** one visible content WebView accepts native input and restarts under
systemd without a second logical content session.

### D3 — PageOwner and authenticated Agent API

- bind BrowserSession/PageOwner to the single content WebView;
- implement D0C-02 UDS carrier;
- implement navigate/observe/act/wait/extract/snapshot/close for local fixtures;
- publish receipts and cancellation outcomes;
- no raw WebDriver listener.

**Exit:** local Agent client navigates and extracts deterministic fixtures, and
all operations carry exact session/document/snapshot identity.

### D4 — same-page human/Agent collaboration

- bind native input and focus to the same PageOwner;
- exercise human preemption, lease expiry, IME, clipboard, drag/drop, modal,
  file chooser, navigation, crash, and minimize/show;
- prove Agent navigate → human sees/edits → Agent observes the resulting state;
- run state-machine property tests and event-trace replay.

**Exit:** no event is routed to a hidden page and no stale or ambiguous target
is silently acted upon.

### D5 — trusted shell and signed applications

- finalize shell/content topology;
- implement synthetic HTTPS app interception;
- verify signed bundle, manifest, content root, CSP, version, revocation, and
  anti-downgrade;
- isolate app storage and service workers;
- distinguish trusted chrome, trusted app, and external origin visually and in
  receipts.

**Exit:** unsigned, wrong-origin, downgraded, revoked, or over-privileged bundle
is rejected; two apps cannot read each other's storage.

### D6 — capability services, workers, and controlled egress

- file/network/notification/audio portals;
- audience/resource/expiry-bound permits;
- WASI Component workers without ambient authority;
- network namespace, resolver, egress proxy, redirect and peer-IP validation;
- external observe-only corpus.

**Exit:** expired/wrong-audience permits fail; private/metadata/rebinding paths
remain unreachable; service-worker and subresource traffic cannot bypass
policy.

### D7 — recovery, updates, and effect reconciliation

- browser/session/watchdog fault journal;
- signed immutable A/B or equivalent image updates;
- minimal `hepta-updated` service and offline recovery media;
- power-loss, disk-full, corrupt-journal, failed-update tests;
- prepare/execute external effects only with explicit policy and indeterminate
  reconciliation.

**Exit:** crashes and failed updates recover or expose a truthful interrupted or
indeterminate state; no blind duplicate external effect occurs.

### D8 — fixed-hardware beta qualification

- choose exact x86_64 hardware BOM;
- qualify GPU, audio, input, suspend/resume, accessibility, IME, multi-monitor,
  update, rollback, and recovery;
- run target web corpus, prompt-injection, origin-spoofing, and sandbox tests;
- publish SBOM, licenses, CVE process, image hashes, and known limitations.

**Exit:** reproducible beta image meets machine-readable qualification gates.
General Linux desktop or arbitrary website compatibility remains unclaimed.

## 12. Repository governance

- changes arrive through reviewable branches/PRs;
- `main` requires CI before release promotion;
- security-sensitive contracts, manifests, sandbox, origin, update, and signing
  paths require CODEOWNER review;
- release tags and manifests are signed before public distribution;
- CI uses least privilege and does not hold production signing keys;
- dependencies and licenses are reviewed before entering the lock;
- generated evidence is linked to exact commit and inputs.

Repository settings that cannot be represented in source are tracked as a
release gate; source files alone do not prove branch protection is enabled.

## 13. Risk register

| Risk | Consequence | Gate/mitigation |
| --- | --- | --- |
| Servo API/platform gaps | blocked websites or missing semantics | pinned spike, patch budget, explicit unsupported result |
| trusted shell spoofing | credential/consent theft | separate surface/origin, compositor-owned indicators |
| revision churn | stale-reference livelock | layered revisions and semantic revalidation |
| Agent/human races | wrong target/effect | formal state machine, bounded queue, event replay |
| UI action side effects | unintended remote effect | classify gestures as potential effects; external mutation disabled early |
| network bypass | SSRF/private-network compromise | namespace + controlled resolver/egress across all resource classes |
| browser compromise | machine takeover | process isolation, no ambient capability, portals, cgroups, LSM |
| update compromise | persistent takeover | separate minimal update authority, offline keys, rollback |
| mobile graph contamination | desktop gains raw shell/ADB authority | manifest + CI dependency firewall |
| false release claims | unsafe deployment | evidence hierarchy and machine-readable non-claims |
| single privileged supervisor | broad compromise | split session, capability, build, and update authorities |

## 14. Immediate execution order

1. Keep this d5 plan, schemas, state machine, toolchain, and product boundary
   green in CI.
2. Complete `D0A-01` against the pinned Servo commit without introducing a TCP
   WebDriver product dependency.
3. Complete `D0A-02` and select the trusted-shell/content composition.
4. Implement `D0C-02` authenticated bounded UDS transport and fuzz it.
5. Resolve the signed Debian snapshot lock.
6. Build the first QEMU image and only then promote to D1.
7. Do not enable external Agent mutation, credentials, downloads, or persistent
   web profiles before D6/D7 gates.

## 15. Claim boundary

The current repository is a real implementation foundation, not a desktop OS
release. Passing Rust tests proves contract/state-machine behavior only.
Passing `hepta-browserd --self-check` proves no Servo, display, listener,
network, image, app-signature, capability, or update behavior. Every future
stage must update `CURRENT_STATE.md`, `docs/MANIFEST.json`, and
`manifests/repository-state.json` with both demonstrated facts and explicit
non-claims.
