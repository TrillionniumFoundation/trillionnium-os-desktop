# TrillionniumOS Desktop canonical development plan — d6

**Plan revision:** `2026-08-29-d6`  
**Status:** active normative plan<br>
**Repository mode:** `FULL_PRODUCT_REPOSITORY`  
**Integrated implementation stage at the d6 baseline:** `D0R_D0C06_D0A01_COMPILE_VALIDATED`  
**Baseline main commit:** `bf6bba2ea1c49b36e11754bf27dc0c56e3da3bd1`

This revision supersedes d5 as the execution plan after merge. It does not promote
candidate D1 or D2 work and it does not widen production, external-effect,
activation, signing, update, or release authority.

## 1. Executive lock

The product remains a Debian-based, AI-native desktop appliance with:

- one compositor/native trusted workspace;
- one logical untrusted Servo content surface;
- one PageOwner for human and Agent interaction;
- system capabilities outside the browser process;
- no public WebDriver or TCP Agent endpoint;
- a local AgentPort that is default-disabled and explicitly activated only in
  a reviewed development or qualification profile;
- durable, non-replaying receipts for admitted operations;
- controlled egress and effect reconciliation before any external mutation;
- signed immutable updates, rollback protection, and fixed-hardware
  qualification before release.

A source file, host test, PR, QEMU run, hardware run, or signed release proves
only its declared evidence tier. Lower evidence never implies a higher tier.

## 2. Canonical truth and precedence

The canonical truth order is:

1. `manifests/project-state.v1.json`;
2. `manifests/gates.v1.json`;
3. `docs/MANIFEST.json` and `manifests/repository-state.json`;
4. this plan and its d6 annexes;
5. `docs/CURRENT_STATE.md` and root `README.md`;
6. historical evidence and superseded plans.

All human-readable status pages must agree with the machine truth. CI must fail
when plan revision, implementation stage, completed package set, candidate
package set, or non-claims drift.

Evidence is bound to the exact tested source SHA, tested merge SHA where
applicable, base SHA, workflow revision, input-lock digests, runner image, and
output digests. Candidate evidence cannot be promoted to integrated-main
evidence without an exact-main rerun.

## 3. Product profiles

| Profile | Purpose | AgentPort | Network | Credentials/effects | Release claim |
| --- | --- | --- | --- | --- | --- |
| fixture | pure host/unit/property testing | connected pairs only | none or loopback fixture | none | none |
| qualification | QEMU/Xvfb/fixed-hardware evidence | test-only explicit activation | disabled unless the gate requires a controlled corpus | none unless the gate explicitly defines a non-production fixture | none |
| development | local engineering and deterministic fixtures | explicit marker/profile | controlled and separately enabled | no production credentials | none |
| production | signed release image | default-disabled unless a later approved product decision changes this | policy-controlled | permit/effect/reconciliation controlled | only after D8/D9 |

Test fixtures and production daemons must be physically separated. A release
artifact must not contain an executable path that silently substitutes a
fixture handler for BrowserActor.

## 4. Current demonstrated state

Integrated main demonstrates:

- D0R repository, toolchain, dependency, product-boundary, and signed Debian
  input locks;
- D0C-01, D0C-02, D0C-03, D0C-04, D0C-05, and D0C-06 contract/control foundations;
- authenticated bounded AF_UNIX connected-stream transport;
- strict canonical Browser API parsing and encoding;
- exactly-one request-bound connected AgentPort bridge;
- default-disabled systemd socket custody and peer attestation;
- crash-consistent durable receipt journaling with no execution or replay API;
- D0A-01 exact-pin Servo compile compatibility only.

Integrated main does not demonstrate:

- a product-owned headed Servo runtime;
- a booted Debian/Wayland image;
- QEMU PID 1 AgentPort activation;
- BrowserActor/PageOwner dispatch into Servo;
- TaskFlow semantic-principal mapping;
- external browsing or external effects;
- signed applications, controlled egress, updates, fixed hardware, or release.

The active D1 and D0A-02/D2 branches are candidates only. Their PR state and
latest qualification results are recorded in `manifests/project-state.v1.json`.

## 5. Evidence model

Every gate record must include:

- package and gate identifiers;
- source repository, base SHA, candidate head SHA, tested merge SHA, and
  integrated-main SHA where each exists;
- Git tree SHA;
- workflow path and workflow blob digest;
- toolchain and external source locks;
- input artifact digests;
- commands and environment;
- pass/fail/blocked outcome;
- bounded evidence artifact digests;
- claim ceiling;
- evidence tier;
- invalidation inputs.

Evidence becomes `STALE_EVIDENCE` if any listed invalidation input changes.
Failed infrastructure steps are classified separately from product
incompatibility; neither may be promoted as a pass.

## 6. Work-package state

### D0T — truth, governance, and evidence integrity

#### D0T-01 Single machine truth — active in this revision

- introduce `project-state.v1.json`;
- introduce a machine gate registry and evidence invalidation rules;
- validate cross-file plan/stage/package/non-claim consistency;
- bind build-info output to the active plan and integrated stage;
- make README and status pages derived summaries rather than independent truth.

**Exit:** exact-head CI rejects any cross-file truth drift.

#### D0T-02 Immutable CI inputs — active in this revision

- pin external GitHub Actions by commit SHA;
- use exact Rust channels and `--locked --all-targets`;
- record PR head SHA separately from merge-test SHA;
- include all transitive gate inputs in path triggers or run the canonical
  truth and repository jobs unconditionally;
- prohibit mutable action refs such as `@master`, `@main`, and version tags in
  qualification workflows.

**Exit:** exact-head CI and the action-reference audit pass.

#### D0T-03 Independent review and release separation — repository-setting gate

- organization-team CODEOWNERS for security, contracts, manifests, updates,
  signing, and release claims;
- protected `main`, required status checks, no self-approval, and no self-merge;
- signing/release authority separated from code authorship;
- break-glass procedure with after-action review.

**Exit:** settings evidence is captured and reviewed. Source files alone do not
prove this gate.

### D0R — repository and reproducibility foundation

D0R-01 through D0R-03 remain integrated. The Debian baseline lock is an input
lock, not a D1 boot or image claim. Any lock update invalidates D1 and later
image evidence.

### D0C — deterministic local control core

D0C-01 through D0C-06 remain integrated at host evidence level. D0C-06 records
facts only. The product AgentPort remains default-disabled. Before D3:

- the fixture handler must be physically separated from the product daemon;
- the semantic principal must be bound to the mechanism identity;
- durable requested/dispatched/outcome facts must wrap every admitted
  BrowserActor operation;
- potential external effects must never be automatically replayed.

### D0A — Servo compatibility

D0A-00 and D0A-01 are integrated. D0A-01 is compile compatibility only.

#### D0A-02 / D2 Headed trusted workspace — active candidate

The candidate must prove on one exact source head:

- one native trusted workspace;
- exactly one logical Servo content WebView;
- deterministic local-fixture first frame;
- native pointer, button, wheel, keyboard, and basic IME paths;
- popup/new-window and external-navigation refusal;
- trusted chrome surviving content-process termination;
- replacement content generation and stale-reference invalidation;
- process topology and bounded screenshot/hash evidence;
- no WebDriver, AgentPort activation, persistent credentials, or external
  mutation.

Clipboard is intentionally outside the D0A-02 claim ceiling. Native clipboard
ownership, lease/preemption, and drag/drop are validated by D4's human/Agent
collaboration gate; D0A-02 evidence must retain `no_native_clipboard` and must
not include executable clipboard proof as a D0A claim. This preserves the
independent D4 clipboard requirements after the headed runtime gate.

**Exit:** permanent workflow pass on candidate head, evidence promotion commit,
then exact-main rerun after merge.

### D1 — reproducible Debian/QEMU substrate

D1 must be rebased onto the current integrated main and must prove:

- signed timestamped Debian snapshot and exact package closure;
- two independent normalized rootfs/ext4/kernel/initrd builds with digest
  identity;
- Q35/TCG boot with no network device;
- systemd PID 1, udev, D-Bus, logind, supervised Wayland placeholder;
- clean shutdown and killed-service recovery;
- D0C-05 default-disabled negative case;
- test-only marker activation, exact authorized/unauthorized peer corpus,
  one-process-per-connection teardown, connection kill, and recovery;
- removal of marker/socket and final-image audit.

**Exit:** exact committed D1 lock, reproducible artifacts, passing QEMU corpus,
and exact-main regression. This is not Secure Boot or hardware qualification.

### D2I — integrated D1 + D2 image gate

D1 and D2 cannot be promoted as independent product readiness claims. The
integrated image gate must start the headed Servo workspace inside the locked
Debian/QEMU image and repeat:

- trusted first frame;
- native input and IME;
- one logical content surface;
- content-process crash/recovery;
- AgentPort default-disabled state;
- no external network device;
- bounded evidence export.

**Exit:** one exact image digest satisfies the combined gate.

### D3 — PageOwner, BrowserActor, AgentPort development activation, receipts

- bind BrowserSession/PageOwner to the single Servo WebView;
- map validated operations to typed BrowserActor messages;
- map an intended local TaskFlow principal to the attested systemd mechanism
  identity;
- enable AgentPort only in an explicitly selected development profile;
- integrate D0C-06 requested/dispatched/terminal or indeterminate receipts;
- implement cancellation and deadline propagation;
- support deterministic local fixtures only.

**Exit:** authorized local Agent operations and unauthorized failures are
durably and exactly recorded; no hidden page or public listener exists.

### D4 — human/Agent collaboration

- same PageOwner for native and Agent input;
- bounded human lease, preemption, IME ownership, clipboard, drag/drop, modal,
  navigation, crash, minimize/show;
- state-machine property tests and trace replay;
- no stale or ambiguous target silently acted upon.

### D5 — trusted shell and signed applications

- separate compositor-owned trusted chrome from untrusted content;
- synthetic HTTPS trusted-app origins;
- bundle signature, manifest, CSP, content-root, storage, service-worker,
  revocation, anti-downgrade, publisher rotation, and offline verification;
- visible and receipt-bound trust indicators.

### D6 — capabilities and controlled egress

- audience/resource/expiry-bound permits;
- file, network, notification, audio, and other portals;
- no ambient browser filesystem/device/secret authority;
- network namespace, controlled resolver, egress proxy, redirect and connected
  peer-IP validation;
- HTTP(S), DNS, WebSocket, QUIC/WebTransport, workers, service workers,
  iframes, prefetch, downloads, and external schemes covered;
- SSRF, rebinding, private/link-local/metadata, proxy-bypass, and captive-portal
  corpus.

### D7 — fault recovery, update, and effect reconciliation

- crash/session/watchdog journal;
- prepare/execute effect protocol with indeterminate reconciliation;
- signed immutable A/B or equivalent image updates;
- minimal update authority, offline recovery media, disk-full/power-loss/
  corrupt-journal/failed-update tests;
- no blind duplicate external effect.

### D8 — fixed-hardware beta qualification

- exact x86_64 hardware BOM;
- GPU/software rendering mode, input, audio, suspend/resume, accessibility,
  IME, multi-monitor, update, rollback, recovery;
- numeric boot/frame/input/observe/act/RSS/FD/PID/recovery/stability gates;
- 24/72-hour stability and power-loss corpus;
- target web, prompt-injection, origin-spoofing, and sandbox tests;
- SBOM, licenses, CVE process, hashes, and known limitations.

### D9 — signed release promotion

- protected reviewed release commit;
- provenance and SBOM bound to exact artifacts;
- offline-held signing keys and documented custody/rotation/revocation;
- update metadata, anti-rollback, recovery, and support policy;
- release notes and machine-readable non-claims;
- no release promotion by the author of the change.

## 7. Immediate execution order

1. Merge D0T-01/D0T-02 truth and CI corrections after review.
2. Repair and rerun D0A-02/D2 candidate qualification.
3. Rebase/reconstruct D1 on current main and rerun its two-step lock promotion.
4. Run the integrated D2I image gate.
5. Physically separate fixture and production AgentPort handlers.
6. Implement D3 PageOwner/BrowserActor/principal binding/receipt integration.
7. Continue D4 through D9 only in dependency order.

Parallel work is allowed only when it does not share a mutable truth file,
activation profile, release claim, or evidence identity.

## 8. Gap closure definition

A gap is closed only when all of the following are true:

- implementation and tests exist;
- exact-head workflow passes;
- evidence artifact is bounded and digest-bound;
- machine truth is updated;
- human docs are consistent;
- claim ceiling is explicit;
- invalidation inputs are recorded;
- required independent review is complete;
- after merge, exact-main regression passes.

A PR, source existence, skipped job, infrastructure failure, or historical
branch pass is not closure.

## 9. Stop and resume outcomes

Valid non-closure outcomes are:

- `BASE_DRIFT`: base changed and the package must be replayed;
- `BLOCKED_UPSTREAM`: exact upstream input or API prevents progress;
- `INFRASTRUCTURE_FAILURE`: runner/tool/cache failure before product
  qualification;
- `SECURITY_REVIEW_REQUIRED`: authority boundary changed;
- `REPOSITORY_SETTING_REQUIRED`: source change cannot prove the setting;
- `RESUME_REQUIRED`: bounded work remains after a durable checkpoint;
- `STOP_CONDITION`: proceeding would widen a frozen claim or production
  authority without approval.

Each outcome must identify exact source/base refs, evidence, owner, and the
minimal resume command or package.

## 10. Claim boundary

The repository is a real implementation foundation, not a released desktop OS.
D0 host validation does not prove QEMU, D0A-01 does not prove a visible frame,
QEMU does not prove hardware, source signing code does not prove key custody,
and candidate PR evidence does not prove integrated main. Production
activation, external effects, signing, update, and release truth remain closed
until their gates pass.
