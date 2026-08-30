# TrillionniumOS Desktop d5 product architecture

**Plan revision:** `2026-08-28-d5`
**Status:** `SUPERSEDED_HISTORICAL` — d5 provenance only; not an active normative component
**Active successor:** [`../DESKTOP_PLAN-2026-08-29-d6.md`](../DESKTOP_PLAN-2026-08-29-d6.md)
**Repository mode:** `FULL_PRODUCT_REPOSITORY`

This historical annex is retained for provenance and was versioned with
[`../DESKTOP_PLAN-2026-08-28-d5.md`](../DESKTOP_PLAN-2026-08-28-d5.md). The
active normative plan is d6; this annex does not override its executive lock,
machine truth, or claim ceilings.

## 1. Product and user promise

A person sees a stable desktop shell and one live content surface. The built-in
Agent can navigate, observe, and operate that same content surface without
screen-scraping a second browser. Human keyboard, pointer, wheel, clipboard,
and IME events and Agent semantic operations are reconciled by one bounded
PageOwner.

The shell provides trusted navigation, status, consent, recovery, and app
identity indicators. External pages cannot draw over, replace, or impersonate
that trusted chrome. System dialogs and capability prompts are compositor or
trusted-shell surfaces, not page DOM.

The baseline is an appliance, not a general-purpose Linux desktop. Arbitrary
native packages, X11 applications, browser extensions, raw device access, and
ambient filesystem or network authority are outside the v1 promise.

## 2. Trust and surface topology

### 2.1 Visible topology

The v1 display contract is:

```text
one local seat
one login/session
one visible top-level workspace window
├── trusted shell/chrome surface
└── one untrusted Servo content WebView
```

The shell and content may be composed by a native shell/compositor integration
or two isolated WebViews. They must not share a DOM, storage partition, service
worker scope, or JavaScript realm. The chosen implementation is decided by the
D0A compatibility spike and recorded in ADR form.

Popup, `target=_blank`, tab, and new-window requests never create a second
independently controlled content PageOwner in v1. Policy may reject them or
convert an explicitly allowed request into navigation of the existing content
WebView. Same-document iframes remain part of that content context and receive
frame-scoped semantic references.

### 2.2 Logical session versus process topology

A BrowserSession is exactly one:

- content PageOwner;
- top-level content browsing context;
- semantic operation queue;
- revision clock;
- Agent control endpoint;
- human input ownership state;
- profile/storage partition.

Servo is permitted to create supervised subprocesses for content, networking,
GPU, or crash isolation. Every subprocess belongs to the same systemd/cgroup
session tree, exposes no separate Agent endpoint, and dies when the session is
closed.

### 2.3 Trusted app origins

Trusted shell and applications use synthetic HTTPS hosts intercepted by the
embedder/network layer:

```text
https://shell.system.hepta.invalid/
https://<app-id>.<publisher>.apps.hepta.invalid/
```

Each host is a distinct tuple origin. The reserved `.invalid` suffix prevents
public DNS resolution. The implementation must define secure-context status,
certificate/interception behavior, storage partitioning, service-worker scope,
CSP, CORS, cookies, cache, install/uninstall, upgrade, downgrade, and data
migration before D5 completion.

Custom schemes may be used internally only after equivalent origin semantics
are proven against the pinned Servo revision. A path-only scheme with a shared
host is forbidden.

## 3. Desktop/mobile boundary

The company sibling `TrillionniumFoundation/trillionnium-os` is an Android
owner-open Codex product. Its default graph permits direct shell/ADB and uses a
different product authority model. Desktop may study its implementation and
extract platform-neutral primitives, but it may not silently inherit mobile
execution authority.

Allowed neutral reuse is limited to deliberately extracted packages for:

- bounded identifiers;
- digest and canonical encoding primitives;
- bounded framing and deadlines;
- portable error envelopes;
- receipt identifiers and sequencing.

Forbidden desktop default-graph dependencies include Android integration,
Lineage product trees, Root Linux, direct shell/ADB, mobile privilege broker,
mobile authority/approval semantics, and mobile release artifacts. CI scans
Cargo manifests and source paths against `manifests/product-boundary.json`.

Any future shared crate must:

1. live in a neutral repository or be vendored by exact commit;
2. have no Android, Servo, shell, ADB, TaskFlow, policy, or app dependency;
3. declare MSRV and compatibility policy;
4. be versioned and reviewed by both product owners;
5. pass both products' graph-contamination tests.

## 8. Runtime authority split

| Component | Owns | Must not own |
| --- | --- | --- |
| kernel/firmware | scheduling, memory, devices, networking primitives | Agent intent or app trust |
| systemd/logind/udev | lifecycle, seat, services, device discovery | DOM or semantic policy |
| Wayland compositor | surfaces, trusted chrome placement, input routing | secrets or app business logic |
| `hepta-sessiond` | unprivileged session lifecycle and browser process supervision | signing keys, update authority, DOM |
| `hepta-browserd` | content WebView, PageOwner, semantic operations, receipts | PID 1, raw devices, unrestricted secrets, image signing |
| trusted shell | user-visible navigation/status/consent/recovery UX | direct root or signing-key access |
| capability service | one typed resource operation | arbitrary browser control or Agent planning |
| `hepta-updated` | minimal signed update/rollback transaction | page content, Agent planning, general capability issuance |
| build pipeline | image creation, SBOM, signing request | runtime webpage input |

`hepta-osd` from d4 is therefore decomposed; no single runtime daemon owns
session, capability issuance, image generation, and updates.

## 9. Repository layout

```text
apps/hepta-browserd/          # content PageOwner daemon
crates/trillionnium-contract-core/
crates/hepta-browser-contracts/
crates/hepta-session-core/
contracts/                    # JSON schemas and golden vectors
manifests/                    # source/toolchain/product/status locks
apps/                         # future trusted shell and services
workers/                      # future WASI components
platform/                     # compositor, portals, network adapters
packaging/debian/             # image recipe after snapshot resolution
services/                     # future session/capability/update services
tests/                        # fixtures, integration, fault, corpus
tools/                        # validators and build helpers
docs/                         # plan, ADRs, architecture, security, operations
```

No symlink, path dependency, Cargo workspace glob, submodule, or build-system
glob may pull the mobile repository into this graph.
