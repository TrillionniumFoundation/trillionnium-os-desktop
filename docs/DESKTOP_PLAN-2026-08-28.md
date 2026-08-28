# Trillionnium OS Desktop Edition — Development Plan

**Canonical name:** TrillionniumOS Desktop  
**Document revision:** 2026-08-28-d4  
**Status:** DESIGN BASELINE — canonical desktop documentation; implementation has not yet started  
**Product relationship:** sibling lane of the Android/mobile TrillionniumOS  
**Canonical desktop document root:** `/data/toshiba-dev/TrillionniumOS/rootfs/home/qian-qi/.openclaw/workspace/docs/trillionnium-os-desktop/`

> This document is normative for the desktop lane. The Android/mobile
> canonical plan remains normative for the mobile lane. Neither lane may
> silently change the other lane's product graph, image, authority model or
> release claim.

## 0. Executive decision

The desktop edition is a **Linux appliance / AI-native desktop shell** whose
user-visible interaction surface is a single headed Servo browser. It is not a
new kernel distribution and it is not a browser process with unrestricted
machine authority.

The implementation order is fixed:

```text
Debian stable userland + distribution kernel
        -> systemd / udev / logind / D-Bus
        -> Wayland compositor + DRM/GPU + input + audio portals
        -> hepta-osd (desktop supervisor and capability broker)
        -> hepta-browserd (one headed Servo WebView and one event loop)
        -> signed hepta:// shell and application surfaces
        -> typed capability services / WASI workers
```

The first product slice is deliberately narrow:

```text
power on
  -> Debian boots
  -> Servo shell appears
  -> Agent navigates the same page through the local API
  -> human sees and edits that same page with keyboard/mouse/IME
  -> Agent observes/extracts the resulting state
  -> a capability request is either explicitly granted or truthfully refused
```

### 0.1 Locked decisions

| ID | Decision | Consequence |
| --- | --- | --- |
| `TOS-D-001` | Start from a pinned Debian stable image, not from a Linux-kernel fork. | Kernel, firmware, initramfs and drivers remain upstream/distribution components until a measured gap proves otherwise. |
| `TOS-D-002` | Servo is the only browser runtime in the desktop baseline. | No Obscura browser-core crates, no second DOM/JS/layout engine and no Chromium backend in v1. |
| `TOS-D-003` | One desktop session owns one headed Servo `WebView`, one `PageOwner`, one JS/DOM state and one UI event loop. | Agent and human are two control inputs to the same live page; there is no page migration or second hidden browser. |
| `TOS-D-004` | `hepta-browserd` is a user-space browser control daemon, not PID 1, a compositor or a hardware authority. | `systemd`, the compositor and capability services retain their proper responsibilities. |
| `TOS-D-005` | UI extensions are signed web bundles; computation and privileged operations run out of process. | “Everything is a Servo plugin” means one UI substrate, not one trust domain or one process. |
| `TOS-D-006` | The desktop lane is a sibling product tree. | Shared Rust contracts may be reused only through explicit, versioned dependencies; the Android build graph is not modified by desktop bring-up. |
| `TOS-D-007` | P0 is read/observe and controlled interaction. | Login, persistent secrets and external side effects require later capability permits and reconciliation; CAPTCHA/anti-bot bypass is never a feature. |
| `TOS-D-008` | v1 defines one user session as one browserd process, one `BrowserActor`, one Servo `WebView`, one top-level browsing context and one event loop. | Iframes may remain inside that page; popup/new-window/tab requests are denied or reduced to navigation in the same WebView. No hidden second page is created. |
| `TOS-D-009` | The v1 desktop target is one local user seat and one visible browser surface. | Multi-user/multi-seat sessions, multiple visible windows and tabs are out of scope until a separate authority and UX decision; they must not appear accidentally through a second page owner. |

### 0.2 Explicitly superseded or excluded ideas

The following are not active desktop implementation directions:

1. Forking Linux before a bootable user-space prototype exists.
2. Treating the current Android-managed, headless Root Linux Bookworm image as
   the desktop rootfs.
3. Combining Obscura's DOM/JS/render/network crates with Servo's engine.
4. Starting a headless Servo process and attempting to turn it into a GUI page
   later. A human-capable session is headed-capable from process creation.
5. Putting arbitrary Rust dynamic libraries into Servo as an application ABI.
6. Reusing the historical GTK/Relm4 GNOME shell as the new product UI.
7. Adding an unqualified Chromium/other-browser fallback “just in case”.
8. Treating a web page, an Agent instruction or a plugin manifest as a system
   authority source.

Old notes and scaffolds may remain in recoverable history. They must not be
discovered as active desktop code or release evidence.

### 0.3 Canonical location lock

This dated plan and the files beside it are the **only canonical desktop
planning entry point** for the migrated TrillionniumOS project:

```text
/data/toshiba-dev/TrillionniumOS/rootfs/home/qian-qi/.openclaw/workspace/docs/
├── trillionnium-os/          # existing Android/mobile documentation
└── trillionnium-os-desktop/  # this desktop documentation
```

`/data/toshiba-dev/TrillionniumOS-desktop/` was an earlier staging location
created before the desktop-machine layout was verified. It is not a second
source of truth. Its old full plan is retained only in a recoverable archive;
the directory contains a redirect notice after this plan is installed.

## 1. What exists today

This section records the desktop-machine inspection on 2026-08-28 so that the
new lane does not inherit an incorrect starting assumption.

### 1.1 Active mobile source and documentation

The desktop machine contains two related mobile source trees and one
documentation control workspace. They are recorded separately so that a
desktop build never accidentally targets the wrong tree:

```text
# Android/Lineage product checkout
/data/toshiba-dev/TrillionniumOS/rootfs/home/qian-qi/android/lineage-fogos

# Rust Agent-native/release source checkout
/data/toshiba-dev/TrillionniumOS/rootfs/home/qian-qi/
  trillionnium-release-sources/p0-agent-native-integration-20260731/
  trillionnium-os

# Migrated documentation/control workspace
/data/toshiba-dev/TrillionniumOS/rootfs/home/qian-qi/.openclaw/workspace/
  docs/trillionnium-os/
```

The current mobile product contract is **Android-based AI Agent Native OS**;
its Root Linux substrate is Android-managed and headless. The mobile trees
contain no active Servo desktop, Wayland desktop or `hepta-browserd`
implementation. The mobile source, image and release authority remain
untouched by this desktop plan.

### 1.2 Historical desktop material

Earlier mobile/control trees contain Debian/GNOME/freedesktop readiness
metadata and a GTK/Relm4/Wayland shell smoke path. They do not contain a
bootable desktop image, an active Servo integration or a finished user-session
installer. The former top-level staging directory
`/data/toshiba-dev/TrillionniumOS-desktop/` is likewise not an implementation
tree. The desktop lane therefore starts as a new profile/product tree rather
than reviving a supposedly existing Servo desktop.

### 1.3 Development host

The current desktop machine is suitable as a development host (Ubuntu 24.04,
x86_64, RTX 4060), but it is not to be reformatted for this project. Bring-up
uses a Debian VM/QEMU image first and then a separately selected bare-metal
test disk or partition.

## 2. Product definition

### 2.1 User promise

Trillionnium Desktop presents one coherent AI-mediated workspace. A person
can see and manipulate the same live page that the Agent is observing and
operating. Applications feel like pages or surfaces in one shell; the Agent
can navigate, read, fill and coordinate them without screen scraping.

The “less is more / browser is everything” principle is implemented as:

- one primary visible interaction surface;
- one consistent semantic Agent API;
- one app distribution and origin model;
- a small number of typed system capabilities;
- no duplicated window, browser and automation stacks.

It does **not** mean that every privilege is placed in the browser process.

### 2.2 In scope for the desktop baseline

- UEFI/Secure Boot bootable Debian image;
- systemd-managed user session and recovery;
- Wayland display and a single-app/full-screen compositor profile;
- one headed Servo WebView with native keyboard, pointer, wheel and IME input;
- `hepta-browserd` semantic API and local authenticated transport;
- same-page Agent/human arbitration and evidence receipts;
- signed first-party `hepta://` shell/app bundles;
- typed portals for files, network, notifications, audio and secrets;
- sandboxing, resource limits, crash recovery and signed updates;
- a fixed-hardware beta qualification corpus.

### 2.3 Out of scope until a separate decision

- a general-purpose Linux desktop compatibility promise;
- a Linux kernel downstream fork;
- arbitrary third-party web pages receiving system capabilities;
- unrestricted page JavaScript or model-facing `eval` as a privileged path;
- local LLM inference as a mandatory desktop feature;
- remote GUI exposure over the public network;
- automatic CAPTCHA solving, anti-bot evasion or stealth fingerprints;
- external purchases, posts, deletions or other irreversible effects in P0;
- a second browser engine hidden behind an automatic fallback.

## 3. System architecture

```text
┌──────────────────────────────────────────────────────────────┐
│ UEFI / Secure Boot                                            │
└──────────────────────────────┬───────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ Debian stable: kernel, initramfs, firmware, drivers, rootfs   │
│ systemd (PID 1), udev, logind, D-Bus                          │
└──────────────────────────────┬───────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ Wayland compositor • DRM/KMS/GPU • input • PipeWire • portals │
│ network and storage services                                  │
└──────────────────────────────┬───────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ hepta-osd                                                     │
│ lifecycle supervisor • capability broker • update/recovery   │
└──────────────────────────────┬───────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ hepta-browserd — one BrowserSession                           │
│   one Servo WebView + RenderingContext + event loop            │
│   one BrowserActor/PageOwner + bounded arbiter                 │
│      ▲ AgentPort (local authenticated UDS)                      │
│      ▲ HumanPort (Wayland/winit keyboard, pointer, IME)         │
│      ▼ receipts, snapshots, typed capability requests           │
└──────────────────────────────┬───────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ hepta://shell and signed app bundles                          │
│ per-app origin/realm, manifest, CSP, UI-only authority         │
└──────────────────────────────┬───────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ capability services / WASI Component workers                   │
│ file • network • audio • notification • secret • device       │
│ each in its own process/namespace and short-lived permit scope │
└──────────────────────────────────────────────────────────────┘
```

### 3.1 Responsibility boundaries

| Layer | Owns | Must not own |
| --- | --- | --- |
| Linux kernel/firmware | scheduling, memory, devices, DRM interfaces, networking primitives, boot | Agent intent, page semantics or app policy |
| systemd/desktop services | process lifecycle, login/session, device discovery, audio/network/update plumbing | DOM, Agent decisions or web content trust |
| Wayland compositor | surfaces, focus, display composition and input routing | file/network/secret authorization |
| `hepta-osd` | browserd lifecycle, image generation, capability-broker plumbing, recovery | a second Agent, page DOM or hidden approval semantics |
| `hepta-browserd` | one Servo runtime, page state, semantic browser operations, arbitration, receipts | PID 1, raw device authority, unrestricted secret storage, update signing |
| Servo WebView | HTML/CSS/JS execution and rendering for the assigned origin | system-wide capability decisions |
| capability service | one typed operation over one explicitly granted capability | arbitrary browser control or Agent planning |
| Codex/Hepta TaskFlow | intent, decomposition, policy interpretation, consent, effect/reconcile semantics | direct unsupervised access to private service internals |

## 4. `hepta-browserd` desktop contract

### 4.1 One live browser, one owner

Each `BrowserSession` is created as one headed-capable Servo runtime. In v1,
one session means exactly one browserd process, one `BrowserActor`, one Servo
`WebView`, one top-level browsing context and one event-loop thread. The actor
owns the Servo handle, rendering context and page state. Servo objects that are
not `Send`/`Sync` never cross threads; background callers send typed messages
to the actor. Same-page iframes are allowed as part of that context, subject to
the observation/policy rules below.

Popup, `target=_blank`, new-window and new-tab requests do not create another
WebView or page owner in v1. The policy either rejects the request with a
typed `Unsupported`/`PolicyDenied` result or converts an explicitly allowed
request into navigation in the existing WebView. This is a product invariant,
not merely an implementation preference.

The browser is headed from creation even if its window starts minimized or
hidden by the local compositor. Showing the window later reveals the same
WebView. No headless-to-headed conversion, page reload handoff or second page
owner is permitted.

### 4.2 Agent and human are two inputs to one bounded arbiter

The actor exposes two ports:

1. **AgentPort:** local UDS, authenticated with peer credentials and a
   per-session nonce/lease. It accepts semantic operations such as
   `navigate`, `observe`, `act`, `wait` and `extract`.
2. **HumanPort:** native Wayland/winit input and focus events. It feeds pointer,
   keyboard, wheel, clipboard and IME events to the same WebView.

Both ports enter one bounded, ordered queue. The queue records:

- `session_id`, `generation` and `page_revision`;
- source (`agent` or `human`), lease and focus state;
- operation type and normalized target reference;
- dispatch, completion and interruption timestamps;
- resulting snapshot/evidence hash or typed failure.

When a human takes focus, the arbiter grants a short human lease, emits a
typed `human_focus=active` state and pauses conflicting Agent mutations. Read
observations already in flight may finish against their recorded revision;
new Agent mutations wait until the human explicitly releases focus or the
lease expires after an idle timeout. The release is recorded and the Agent
must reacquire a lease before mutating. Human edits are not invisible side
effects: `PageOwner` increments `page_revision` synchronously on every human
or Agent mutation, navigation and committed DOM change, immediately
invalidating older semantic references. An observation does not itself
increment the revision.

### 4.3 Semantic API (P0)

The public contract is intentionally engine-neutral even though v1 has one
Servo implementation:

```text
session.create(profile, ui_mode=headed)
search(engine=google|bing, query)  # allowlisted URL navigation convenience
page.navigate(url)
page.observe(fields=[role, name, text, href, bounds?])
page.act(ref, op=click|type|press|scroll|select)
page.wait(condition, timeout)
page.extract(schema)
session.snapshot()
session.close()
```

The implementation may use Servo WebDriver routes or direct embedder hooks
while the wrapper is being built. If WebDriver is used, it is an internal
adapter invoked by the same `BrowserActor`/`PageOwner` and event loop; it may
not start a second Servo/page or expose an independent listener. Raw
WebDriver is not exposed to the Agent.
Unrestricted JavaScript evaluation is disabled in the initial product
contract; any later script capability must be separately typed, audited and
origin-scoped.

`search(engine, query)` is only a convenience operation: it validates an
allowlisted engine (`google` or `bing`), URL-encodes the query and navigates
the existing top-level context to that engine's search URL. It is not a
search-provider, index, ranking service or second browser. Results are read
from the same live WebView under the same policy and receipt rules.

### 4.4 Servo integration strategy

Bring-up uses the smallest maintainable Servo wrapper:

1. pin a tested Servo commit and record it in the desktop lock manifest;
2. start from `servoshell`/official embedder patterns to prove Linux graphics,
   input and navigation;
3. provide the embedder's `EventLoopWaker`, `RenderingContext`, WebView
   builder/delegate and input forwarding;
4. run the event loop through the supported Servo spin/pump mechanism;
5. place `BrowserActor` and the local API adapter around that single owner;
6. replace temporary WebDriver translation with direct typed hooks only when
   measurements show a real need.

The exact Servo API is pinned per revision and re-qualified on upgrade. A
Servo source change is never allowed to silently change the browserd semantic
contract.

## 5. App and plugin model

“All software is a Servo plugin” is split into three explicit classes.

### 5.1 UI bundle

A UI application is a signed bundle of HTML/CSS/JS loaded under a local,
non-network origin such as:

```text
hepta://shell
hepta://app/<publisher>/<app-id>/<version>
```

Every app has a manifest, signature, content-security policy, declared
capabilities and its own origin/realm. `hepta://shell` is a trusted system
surface and cannot be replaced by network content. A web page from Google,
Bing or any other external origin is untrusted evidence, not a system plugin.

### 5.2 Compute worker

CPU-heavy or non-UI logic runs as a WASI Component/WIT worker in a separate
process or sandbox. The desktop baseline pins one Component Model/WIT version
and requires explicit interface negotiation on upgrade. A worker receives no
ambient filesystem, network, device or process authority.

### 5.3 Capability service

Files, network, audio, notifications, camera, Bluetooth, secrets, power,
updates and legacy Linux programs are exposed by typed D-Bus/UDS portals.
Each request carries a short-lived capability token, audience, operation,
resource and expiry. The browser never receives a raw root FD, unrestricted
socket or signing key.

The custom `hepta://` scheme handler, bundle signature verifier and manifest
loader are embedder-layer components to be implemented by the desktop lane;
they are not assumed to be an existing stable Servo plugin ABI. Servo's
user-content injection and embedder delegate APIs are implementation hooks,
not a promise of arbitrary native plugins. The product must not load
untrusted Rust `cdylib`s into the browser process.

## 6. Authority and safety model

### 6.1 Semantic authority

Hepta/Codex and its existing TaskFlow remain the authority for intent,
clarification, policy interpretation, consent language, retries and external
effect reconciliation. `hepta-browserd` is a mechanism/control plane: it
executes typed browser operations, records what happened and reports
indeterminate outcomes honestly.

A browser acknowledgement means only “the operation was dispatched or
observed.” It does not authorize a purchase, post, delete, credential use or
other external effect.

### 6.2 P0 capability levels

| Level | Allowed in initial desktop slice | Examples |
| --- | --- | --- |
| `ObserveOnly` | yes | navigate, snapshot, text/attribute extraction, read-only search |
| `InteractiveRead` | yes, with human/Agent arbitration | click, type, scroll, local form exploration |
| `Prepare` | fixture-only until separately qualified | fill a form and show a reviewable pending state |
| `Execute` | no in P0 | submit, purchase, publish, delete, send message |

Consent dialogs, CAPTCHA, 429, anti-bot, unsupported web features and policy
refusals are typed challenge/status results. They are not automatic fallback
triggers and are never silently bypassed.

### 6.3 Process and network isolation

The minimum production-shaped sandbox is:

- dedicated low-privilege user and per-session profile;
- namespaces, `no_new_privs`, seccomp and Landlock where available;
- cgroup v2 CPU/RSS/PID/FD/wall-clock limits;
- AppArmor or SELinux policy selected for the target distribution;
- blocked loopback/private/link-local/metadata destinations and DNS rebinding;
- redirect, iframe, worker, WebSocket and subresource policy checks;
- downloads, device access, raw sockets and system credential discovery off by
  default;
- local-only Agent socket with peer authentication; no public WebDriver port.

Seccomp alone is not treated as a complete sandbox. The browser is an
untrusted-code execution boundary even when it displays a trusted app bundle.

## 7. Base system and build strategy

### 7.1 Why Debian first

Debian supplies the bootable user-space pieces that a kernel does not:
package/build tooling, systemd, login/session management, Wayland, graphics
libraries, fonts, input/IME, audio, portals, networking, diagnostics and
update machinery. Starting there lets the team spend effort on Servo and the
AI interaction model instead of recreating a distribution.

The current stable release at the time of this plan is Debian 13 “trixie”.
The exact package snapshot, architecture and firmware set are recorded in a
desktop lock manifest; do not use an unpinned rolling host as the product
image.

### 7.2 Kernel policy

Use the Debian stable kernel/initramfs/firmware and upstream or distribution
drivers first. For the current x86_64 test machine, validate DRM/KMS, input,
audio and GPU acceleration in QEMU and then on a disposable bare-metal lane.
NVIDIA-specific packaging and proprietary-driver behavior are qualification
items, not reasons to fork the kernel.

A downstream kernel branch may be opened only after all of the following are
true:

1. a reproducible stock-kernel failure is demonstrated on a supported target;
2. the missing behavior cannot be supplied by user-space configuration or a
   supported driver/firmware update;
3. the smallest patch/config delta is reviewed and measured;
4. signed artifacts, rollback and a stock-kernel recovery path exist.

Until then, “kernel work” means selecting config, reporting bugs upstream and
packaging a tested distribution kernel.

### 7.3 Development and deployment lanes

| Lane | Purpose | Rule |
| --- | --- | --- |
| Current Ubuntu host | compile, inspect, run QEMU and local fixtures | never reformat or replace the developer host for bring-up |
| Debian QEMU image | deterministic boot and service tests | first acceptance target for every desktop stage |
| Disposable x86_64 bare-metal disk | GPU, input, suspend, audio and recovery qualification | isolated from the mobile data estate |
| Immutable release image | later beta/OTA product | only after update and rollback evidence exists |

The Android Root Linux Bookworm builder remains a mobile/headless artifact. A
desktop image may share neutral Rust crates, but it has its own package graph,
rootfs contract, image identifier and release receipts.

## 8. Repository and source layout

The **documentation** is already colocated with the mobile documentation in
the verified control workspace:

```text
/data/toshiba-dev/TrillionniumOS/rootfs/home/qian-qi/.openclaw/workspace/docs/
├── trillionnium-os/          # mobile documentation/source index
└── trillionnium-os-desktop/  # canonical desktop docs (this directory)
    ├── README.md
    ├── CURRENT_STATE.md
    ├── DESKTOP_PLAN.md              # stable index
    └── DESKTOP_PLAN-2026-08-28.md   # normative dated plan
```

At `TOS-D0`, the **implementation** tree is to be created as a separately
named desktop source checkout; its exact path and Git remote must be recorded
in a lock manifest before code is added. The implementation tree must contain
the following explicit packages (whether one repository or several is a D0
decision):

```text
contracts/       # semantic browser/capability contracts
browserd/         # Servo embedder + BrowserActor/PageOwner
osd/              # lifecycle supervisor/capability broker
apps/             # signed hepta:// bundles
workers/          # WASI components and WIT interfaces
packaging/debian/ # pinned rootfs/image recipe
platform/         # compositor, portals and device adapters
tests/            # fixtures, corpus and fault tests
manifests/        # source, package, Servo and image locks
```

No symlink, broad Cargo-workspace glob or Android build-system glob may pull
desktop binaries into the mobile product. If shared contracts are extracted
later, they become a deliberately versioned neutral package with an owner and
compatibility policy. The documentation directory is not a build input until
such a manifest explicitly says so.

## 9. Development stages

The stages below are the only active desktop sequence. Each stage has an
observable exit condition; a source file existing is not completion.

### `TOS-D0` — Product split and locks

**Work**

- create the sibling desktop tree and this plan;
- freeze product/authority matrix and mobile boundary;
- choose x86_64 QEMU target, Debian release, architecture and package source;
- pin a Servo commit and record license/SBOM provenance;
- define desktop contract versions and receipt format.

**Exit condition:** a clean manifest identifies the desktop tree, mobile tree,
Debian inputs, Servo commit, supported hardware lane and explicit exclusions.

### `TOS-D1` — Debian boot substrate

**Work**

- build a minimal bootable Debian image with stock kernel/initramfs;
- enable systemd, udev, logind, D-Bus and a local user session;
- bring up Wayland with Cage/Weston/labwc-like single-surface profile;
- add DRM/input/fonts and a minimal diagnostics shell;
- boot and shut down reproducibly in QEMU.

**Exit condition:** QEMU boots from the produced artifact into a Wayland
session, starts and stops services under systemd, and recovers from a killed
user process without touching the mobile image.

### `TOS-D2` — Servo headed shell

**Work**

- compile the pinned Servo wrapper on Debian;
- implement rendering context, event-loop wake/pump and WebView delegate;
- forward native pointer, keyboard, wheel, clipboard and basic IME events;
- load a local trusted fixture and an external read-only page;
- record GPU/software-rendering mode and engine commit in receipts.

**Exit condition:** one visible Servo window renders the fixture, accepts native
input and exits/restarts under systemd without a second browser process.

### `TOS-D3` — `hepta-browserd` actor and Agent API

**Work**

- add `BrowserSession`, `BrowserActor`, `PageOwner` and bounded arbiter;
- add local authenticated AgentPort and typed request/response schemas;
- implement `navigate`, `observe`, `act`, `wait`, `extract`, snapshot and close;
- translate to Servo/WebDriver/direct hooks behind the contract;
- add generation, page revision, stale-ref and cancellation handling.

**Exit condition:** an Agent request can navigate and extract a local fixture,
and every operation has a receipt containing session, generation, revision,
engine commit and outcome.

### `TOS-D4` — Same-page human/Agent collaboration

**Work**

- bind Wayland/winit input and focus to the same WebView owner;
- implement human/Agent leases, focus notifications and serial arbitration;
- prove Agent navigate → human sees it → human edits → Agent observes the edit;
- test DOM reorder, navigation, cancellation, window minimize/show and crash;
- cover IME, clipboard and file/permission dialog behavior explicitly.

**Exit condition:** the vertical slice works on one live page with one DOM/JS
state; no operation is routed to a hidden or second browser.

### `TOS-D5` — Shell and application bundles

**Work**

- implement `hepta://shell` and signed app-bundle manifests;
- enforce per-app origins, CSP, signature and version checks;
- ship first-party workspace/search/document/message fixtures;
- define navigation between shell and external origins without trust mixing.

**Exit condition:** an unsigned, wrong-origin or over-privileged bundle is
rejected; a signed fixture app can render and request a declared capability.

### `TOS-D6` — Capability services and workers

**Work**

- implement typed file, network, notification and audio portals;
- add WASI Component/WIT worker lifecycle and version negotiation;
- issue short-lived, audience-bound capability tokens;
- run workers/services in separate namespaces with resource limits;
- preserve raw observations and errors for Agent interpretation.

**Exit condition:** a declared capability succeeds only with a valid permit;
an undeclared or expired request is refused without granting a weaker hidden
capability or killing the browser session.

### `TOS-D7` — Security, recovery and update

**Work**

- apply low-privilege sandbox, seccomp/Landlock and cgroup limits;
- add network egress/SSRF/rebinding checks and download policy;
- add browserd watchdog, crash journal and honest indeterminate state;
- produce signed immutable/A-B image updates and rollback;
- add Secure Boot key custody and out-of-band recovery media.

**Exit condition:** power loss, browser crash, service kill and failed update
produce a recoverable state or explicit interruption; no blind duplicate
external effect is issued.

### `TOS-D8` — Fixed-hardware beta qualification

**Work**

- qualify the chosen x86_64 hardware, GPU, suspend/resume, audio, IME,
  accessibility, multi-monitor and recovery paths;
- run the web corpus and prompt-injection/untrusted-content tests;
- publish SBOM, licenses, CVE process, image hashes and rollback evidence;
- decide whether any tiny kernel config/patch is justified by measured data.

**Exit condition:** a reproducible beta image passes the agreed corpus and
recovery gates. General desktop compatibility remains a separate product
claim and is not implied by this gate.

## 10. Qualification corpus and test policy

### 10.1 Local fixtures first

Before Google/Bing or authenticated sites, use deterministic local fixtures for:

- static DOM and semantic references;
- SPA route changes and asynchronous rendering;
- forms, validation and event delegation;
- iframe and shadow-boundary observations;
- cookie/storage/history changes;
- DOM reorder and stale-reference rejection;
- human typing/IME/clipboard interleaving;
- file chooser, permission and alert behavior;
- crash, timeout, cancellation and page reload.

### 10.2 External read-only corpus

After local fixtures pass, add a small pinned corpus covering Google/Bing
read-only search, ordinary content pages, redirects, consent screens, 429 and
challenge states. The corpus records expected capability/status classes, not a
promise that a search engine will always allow automation.

### 10.3 Required evidence

Every qualification receipt records:

```text
desktop_plan_revision
image_id / package_lock
servo_commit
browserd_version
session_id / generation / page_revision
ui_mode / human_control_available
requested_operation / normalized target
final URL and redirect chain (when applicable)
snapshot or extracted-content hash
operation status and qualification status separately
challenge/failure reason, if any
```

Page content is evidence, not instruction. Text that attempts to change system
policy, reveal secrets or invoke capabilities is treated as untrusted content.

## 11. Update, recovery and lifecycle

`hepta-osd` supervises `hepta-browserd` but does not become a second scheduler
or semantic Agent. systemd owns PID 1 and service restart. The browserd journal
is a bounded mechanism journal, not an effect authority.

The desktop release path eventually uses a signed immutable image with A/B or
equivalent rollback. A failed browser update must be recoverable to the last
known-good Servo/image pair. The update service never accepts commands from
page content or an unverified app bundle.

Remote browser control is out of scope for the first desktop product. If it is
later introduced, remote-read and remote-effect permissions must be separate,
with device binding, operator authentication and an explicit threat review.

## 12. Risks and mitigations

| Risk | Impact | Mitigation / decision gate |
| --- | --- | --- |
| Servo web-platform gaps | sites or apps fail | maintain a target corpus; use explicit unsupported status; do not hide a second engine in v1 |
| GPU/NVIDIA/Wayland variation | blank window, poor performance | QEMU/software-render path first, then fixed-hardware qualification; keep stock kernel recovery |
| IME/accessibility/media gaps | human collaboration unusable | make D4/D8 gates; do not claim desktop readiness from a screenshot-only demo |
| browser or plugin compromise | machine takeover | process separation, portals, namespaces, no ambient authority, signed bundles |
| prompt injection in web content | unintended Agent action | content/effect separation, TaskFlow ownership, typed receipts and human focus state |
| stale DOM references | wrong target action | page revisions, generation fences and actor serialization |
| update failure/power loss | unusable appliance or duplicate effects | immutable A/B, journal, rollback and indeterminate reconciliation |
| kernel fork creep | long-term maintenance burden | kernel decision gate requires a measured, irreducible hardware need |
| mobile/desktop graph contamination | mobile regression or unclear releases | sibling tree, explicit pins and CI graph checks |

## 13. Immediate next actions

1. Keep the Android/mobile canonical trees and their current plan unchanged.
2. Create the separately named desktop implementation checkout and commit the
   desktop lock manifest; do not use the documentation directory as a Cargo
   workspace.
3. Build a pinned Debian 13 QEMU image with a stock kernel and a minimal
   Wayland session.
4. Compile the pinned Servo wrapper and render a local fixture.
5. Implement the smallest `BrowserActor` and AgentPort around that one WebView,
   including synchronous page-revision and human-lease rules.
6. Demonstrate the same-page human/Agent vertical slice before adding external
   search, login, persistent profiles or side effects.
7. Record every result in desktop receipts; do not promote a source-only result
   to a product or release claim.

## 14. References

### Local project evidence

- Migrated project root: `/data/toshiba-dev/TrillionniumOS/`
- Android/Lineage checkout:
  `/data/toshiba-dev/TrillionniumOS/rootfs/home/qian-qi/android/lineage-fogos`
- Rust Agent-native checkout:
  `/data/toshiba-dev/TrillionniumOS/rootfs/home/qian-qi/trillionnium-release-sources/p0-agent-native-integration-20260731/trillionnium-os`
- Mobile documentation index:
  `/data/toshiba-dev/TrillionniumOS/rootfs/home/qian-qi/.openclaw/workspace/docs/trillionnium-os/README.md`
- Desktop documentation index: this directory's `README.md` and `DESKTOP_PLAN.md`
- Historical desktop metadata: `platform/debian/`, `profile/desktop-gnome/`,
  `packaging/debian/` in retired/recoverable source trees

### External technical references

- Servo Book: <https://book.servo.org/>
- Servo embedding API: <https://doc.servo.org/servo/>
- Servo source/WebDriver server: <https://github.com/servo/servo/tree/main/components/webdriver_server>
- Debian stable releases: <https://www.debian.org/releases/stable/>
- Wayland: <https://wayland.freedesktop.org/docs/html/>
- XDG Desktop Portals: <https://flatpak.github.io/xdg-desktop-portal/docs/>
- WASI Component Model: <https://component-model.bytecodealliance.org/>
- Linux Landlock: <https://docs.kernel.org/userspace-api/landlock.html>
- Linux seccomp: <https://docs.kernel.org/userspace-api/seccomp_filter.html>
- ChromiumOS software architecture precedent:
  <https://www.chromium.org/chromium-os/chromiumos-design-docs/software-architecture/>

## 15. Terminology lock

- **TrillionniumOS:** canonical spelling of the project name. “Trollionnium OS”
  is an informal conversation spelling, not a second product.
- **Mobile edition:** the existing Android AI Agent Native OS and its
  Android-managed headless Root Linux substrate.
- **Desktop edition:** this Debian + Servo sibling lane.
- **One browser:** one visible Servo WebView, one live page owner and one
  human/Agent interaction surface per desktop session. It does not mean that
  PID 1, capability services and workers are merged into the browser process.
- **Plugin:** either a signed UI bundle, a sandboxed WASI worker or a typed
  capability service; never an untrusted library with ambient authority.
