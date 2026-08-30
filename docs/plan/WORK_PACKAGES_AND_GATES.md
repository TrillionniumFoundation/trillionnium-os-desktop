# TrillionniumOS Desktop d5 work packages and gates

**Plan revision:** `2026-08-28-d5`
**Status:** `SUPERSEDED_HISTORICAL` — d5 provenance only; not an active normative component
**Active successor:** [`../DESKTOP_PLAN-2026-08-29-d6.md`](../DESKTOP_PLAN-2026-08-29-d6.md)
**Repository mode:** `FULL_PRODUCT_REPOSITORY`

This historical annex is retained for provenance and was versioned with
[`../DESKTOP_PLAN-2026-08-28-d5.md`](../DESKTOP_PLAN-2026-08-28-d5.md). The
active normative plan is d6; this annex does not override its executive lock,
machine truth, or claim ceilings.

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
- select Debian 13/trixie amd64;
- select Servo commit `670ae8a70801b162e186f81cbb5bdd2d59c39108`;
- record mobile reference commit and dependency exclusions.

**Remaining gate:** Debian snapshot timestamp, signed `InRelease` digests,
archive-key fingerprints, exact package closure, and package-set digest must be
resolved before D1 promotion. A point-release label alone is not an input lock.

#### `D0R-03` Graph and claim checks — IMPLEMENTED

- scan Cargo/source graph against forbidden mobile dependencies;
- validate JSON, plan/manifests, error-code alignment, and golden vectors;
- run Rust fmt, Clippy, tests, and browserd self-check in CI;
- separate historical evidence from exact-head regression checks;
- prevent a squash-merge topology from being mistaken for source tampering.

### D0C — contracts and deterministic local control core

#### `D0C-01` Domain contracts — IMPLEMENTED

- browser operation types;
- error taxonomy;
- synthetic trusted origin identity;
- machine-readable schemas and golden requests;
- initial receipt, permit, and app-manifest schemas.

#### `D0C-02` Authenticated bounded connected-stream carrier — HOST VALIDATED

- already-connected AF_UNIX stream only; no bind/listen path;
- kernel `SO_PEERCRED` peer identity and explicit peer policy;
- fresh per-connection nonce;
- fixed 88-byte versioned frame header;
- 256 KiB pre-allocation bound and SHA-256 payload binding;
- strictly increasing sequence numbers and replay refusal;
- one absolute monotonic deadline over each complete frame;
- independent wire reference and malformed-frame corpus.

**Demonstrated exit:** Rust 1.93 exact-head formatting, Clippy, tests,
browserd self-check, repository validation, and independent wire corpus pass.
No product listener is implied.

#### `D0C-03` Canonical Browser API codec — HOST VALIDATED

- recursive duplicate-member rejection;
- bounded integer-only JSON with depth/container limits;
- strict unknown-field rejection and canonical byte re-encoding;
- request/session/generation and response/error binding;
- typed navigation target validation;
- semantic-reference revision checks;
- navigation/click/type/press/select classified as potential external effects;
- independent 27-case reference and golden-wire regeneration.

**Demonstrated exit:** deterministic references, static source/contract audit,
Rust 1.93 exact-head tests, and browserd self-check pass. The codec grants no
policy authority and dispatches no browser engine.

#### `D0C-04` Exactly-one connected AgentPort bridge — HOST VALIDATED

- compose D0C-02 carrier and D0C-03 codec;
- one request and at most one handler invocation per connection;
- immutable dispatch context with peer identity, sequence, request digest,
  effect class, and effective monotonic deadline;
- handler cannot author wire identity or transport binding fields;
- canonical request-bound response and digest;
- discard late results without response commit;
- D0 fixture refuses all potential external effects and reports absent browser
  runtime honestly.

**Demonstrated exit:** source/contract audit, full Rust workspace tests, and
integrated browserd self-check pass. No BrowserActor or Servo call exists.

#### `D0C-05` Default-disabled systemd AgentPort custody — HOST VALIDATED

- systemd owns `/run/hepta/browserd/agent.sock`;
- fixed owner/group/mode/directory, backlog, and connection ceiling;
- `Accept=yes` with one short-lived inherited-stream process per connection;
- package-created `hepta-browserd` and `hepta-agent` identities;
- pidfd held through the request;
- bounded procfs UID/GID, start-time, cgroup-v2, and service-unit attestation;
- no capabilities, private network namespace, AF_UNIX only, bounded lifetime;
- preset exactly disables the socket;
- `/etc/hepta/enable-agent-port` is required but not shipped.

**Demonstrated host exit:** repository and custody audits,
`systemd-sysusers`, `systemd-analyze verify`, Rust 1.93 formatting/Clippy/tests,
browserd and connection-service self-checks pass. The host gate does not start
a product listener.

**Remaining activation gate:** D1 QEMU PID 1 must prove default-disabled
negative behavior, explicit test-marker activation, exact socket ownership,
unauthorized-peer refusal, one authorized fixture request, per-connection
teardown, kill/recovery, and marker removal from the final image.

#### `D0C-06` Durable receipt journal — NEXT

- canonical receipt encoding and schema version negotiation;
- monotonically increasing sequence and chained digest;
- atomic append, sync policy, crash truncation detection, and bounded recovery;
- separate requested/dispatched/completed/indeterminate states;
- redaction, retention, rotation, export, and privacy classification;
- no automatic replay of a potential external effect;
- test vectors for corruption, disk full, torn write, restart, and concurrent
  readers.

**Exit:** after kill/torn-write/disk-full tests, the journal exposes either the
last complete chain or a typed corruption/interruption state and never invents
completion or automatically reissues an effect.

### D0A — Servo architecture compatibility

#### `D0A-00` Pure state-machine spike — IMPLEMENTED

The current code proves layered revisions, human preemption, IME ownership,
navigation, crash recovery, and bounded queues without claiming Servo support.

#### `D0A-01` Exact pinned Servo compile compatibility — NEXT

At Servo commit `670ae8a70801b162e186f81cbb5bdd2d59c39108`, using Servo's own
locked toolchain and dependency graph, prove:

- exact clean source checkout and input hashes;
- official headed `servoshell` builds with `--locked`;
- public `Servo`, `WebView`, `WebViewBuilder`, rendering-context, delegate, and
  event-loop entry paths compile from an external crate;
- the aggregate external embedder sentinel compiles;
- the patch ledger is explicit and zero-delta unless a reviewed patch is
  required.

**Exit evidence:** exact source/toolchain hashes, build logs, selected API paths,
generated probe source, dependency provenance, and explicit non-claims. This
is compile compatibility only, not a visible-frame claim.

#### `D0A-02` Trusted workspace composition and headed runtime — NEXT

Prototype one visible workspace with native/compositor-owned trusted chrome and
exactly one untrusted Servo content surface. Prove:

- external navigation cannot replace or share the trusted chrome DOM;
- supported event-loop wake/pump and supervised shutdown;
- local fixture first frame with screenshot/hash evidence;
- pointer, keyboard, wheel, clipboard, and basic IME routing;
- navigation commit, popup/new-window interception, hit-test, and crash callback;
- content crash leaves trusted chrome visible and recovery increments session
  generation;
- process topology contains one logical content PageOwner and no hidden Agent
  page or public WebDriver listener;
- semantic/accessibility-tree access, or a bounded reviewed Servo patch list.

**Go/no-go:** if the exact pin cannot provide required embedding or semantic
hooks within the reviewed patch budget, stop promotion and revise the decision
explicitly; never add a hidden fallback engine.

### D1 — reproducible Debian QEMU substrate

- resolve signed timestamped Debian snapshot inputs;
- record archive key fingerprints, `InRelease`, package closure, kernel,
  initramfs, firmware, and build-tool digests;
- build two independent normalized rootfs/image candidates;
- prove digest identity or document the exact nondeterministic field before
  promotion;
- boot Q35/TCG with network disabled into systemd, udev, D-Bus, logind, and a
  supervised Wayland placeholder;
- verify clean shutdown and killed-service recovery;
- install D0C-05 custody while keeping the product marker absent;
- in a dedicated test image only, create the marker and prove PID 1 socket
  activation, negative/positive peer tests, connection teardown, and recovery;
- remove the marker and confirm the release candidate remains disabled.

**Exit:** a controlled builder creates digest-identical artifacts from locked
inputs; QEMU reaches the placeholder surface and records persistent machine
evidence. This is not Secure Boot or hardware qualification.

### D2 — headed Servo content surface in the image

- integrate the D0A-02 wrapper into the Debian image;
- record GPU/software mode, Servo commit, process tree, and frame timing;
- render deterministic trusted/local fixtures;
- forward native input and IME to the single content WebView;
- prove crash/restart without a second logical content session;
- optional human-driven read-only external corpus remains separate and cannot
  enable Agent mutation.

**Exit:** one visible Servo content surface accepts native input and restarts
under systemd while trusted chrome remains authoritative.

### D3 — PageOwner, BrowserActor, explicit AgentPort activation, and receipts

- bind `BrowserSession`/`PageOwner` to the single Servo content WebView;
- convert validated D0C operations to typed BrowserActor messages;
- implement navigate/observe/act/wait/extract/snapshot/close on local fixtures;
- integrate D0C-06 receipts, cancellation, and indeterminate outcomes;
- map the intended local Agent principal to the D0C-05 mechanism identity;
- enable the local socket only in an explicitly selected development profile;
- no TCP/raw WebDriver listener.

**Exit:** an authorized local Agent navigates and extracts deterministic
fixtures; unauthorized peers fail; every admitted operation carries exact
session/document/snapshot identity and durable request/dispatch/outcome
receipts.

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
- verify bundle signature, manifest, content root, CSP, version, revocation,
  anti-downgrade, publisher rotation, and offline verification;
- isolate app storage and service workers;
- distinguish trusted chrome, trusted app, and external origin visually and in
  receipts.

**Exit:** unsigned, wrong-origin, downgraded, revoked, or over-privileged bundle
is rejected; two apps cannot read each other's storage.

### D6 — capability services, workers, and controlled egress

- file/network/notification/audio portals;
- audience/resource/expiry-bound permits;
- WASI Component workers without ambient authority;
- network namespace, controlled resolver, egress proxy, redirect and peer-IP
  validation;
- cover HTTP(S), DNS, WebSocket, QUIC/WebTransport where supported, workers,
  service workers, iframes, prefetch, downloads, and external schemes;
- external observe-only corpus.

**Exit:** expired/wrong-audience permits fail; private/metadata/rebinding paths
remain unreachable; subresource and worker traffic cannot bypass policy.

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

- select an exact x86_64 hardware BOM;
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
- generated evidence is linked to exact commit and inputs;
- historical tested commits may be squash-merged; current integrity is proven
  by deterministic content regeneration and exact-head execution, not by a
  false requirement that pre-squash branch commits remain mainline ancestors.

Repository settings that cannot be represented in source are tracked as a
release gate; source files alone do not prove branch protection is enabled.

## 13. Risk register

| Risk | Consequence | Gate/mitigation |
| --- | --- | --- |
| Servo API/platform gaps | blocked sites or missing semantics | exact-pin compile/runtime spikes, patch budget, explicit unsupported result |
| trusted shell spoofing | credential/consent theft | separate surface/origin, compositor-owned indicators |
| revision churn | stale-reference livelock | layered revisions and semantic revalidation |
| Agent/human races | wrong target/effect | formal state machine, bounded queue, event replay |
| UI action side effects | unintended remote effect | classify navigation/gestures as potential effects; external mutation disabled early |
| local socket impersonation | unauthorized mechanism access | SO_PEERCRED + pidfd + procfs/cgroup/unit attestation and default-disabled custody |
| network bypass | SSRF/private-network compromise | namespace + controlled resolver/egress across all resource classes |
| browser compromise | machine takeover | process isolation, no ambient capability, portals, cgroups, LSM |
| update compromise | persistent takeover | separate minimal update authority, offline keys, rollback |
| mobile graph contamination | desktop gains raw shell/ADB authority | manifest + CI dependency firewall |
| false release claims | unsafe deployment | evidence hierarchy and machine-readable non-claims |
| single privileged supervisor | broad compromise | split session, capability, build, and update authorities |

## 14. Immediate execution order

1. Keep D0C-02 through D0C-05 exact-head regressions green and merge the
   default-disabled custody implementation without an enable marker.
2. Complete `D0A-01` exact Servo compile compatibility from the current main.
3. Resolve `D0R-02` signed Debian inputs and execute `D1-01`, including the
   D0C-05 PID 1 activation corpus in a test-only image.
4. Complete `D0A-02`/D2 local first frame, input/IME, popup refusal, process
   topology, and crash recovery.
5. Implement `D0C-06` durable receipts before BrowserActor operation claims.
6. Implement D3 BrowserActor and explicitly selected development-profile
   AgentPort activation on local fixtures.
7. Do not enable external Agent mutation, credentials, downloads, persistent
   web profiles, capabilities, update authority, or release claims before their
   D5–D8 gates.

## 15. Claim boundary

The current repository is a real implementation foundation, not a desktop OS
release. D0C-05 host validation proves source, package mapping, unit syntax,
peer-attestation behavior, and default-closed custody only. It does not prove a
booted listener. Servo compile checks do not prove a visible frame; QEMU does
not prove bare-metal support; source signing code does not prove key custody;
and lower evidence never implies a later-stage product claim. Every promotion
must update `CURRENT_STATE.md`, `docs/MANIFEST.json`,
`manifests/repository-state.json`, contracts, tests, and machine evidence
atomically.
