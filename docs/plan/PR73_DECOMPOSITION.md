# PR #73 decomposition ledger

**Frozen source:** PR #73  
**Base:** `main` at `addaf73a48bae65f19f6bfe91c6264fd2ddb85a1`  
**Freeze/build-repair head:** `ce176fc627b1008726044c32a6aa29b56bcec52f`  
**Purpose:** replace one 477-file convergence change with independently reviewable trust-boundary changes

## Rules

- PR #73 remains Draft and is never merged as one unit.
- Successors are reconstructed or selectively cherry-picked; do not merge the cumulative branch into a successor.
- Each successor has one primary trust boundary and an explicit exclusion list.
- A successor must build and test independently from later successors.
- Evidence, review, and approvals are produced on the exact final successor head.
- Generated files must be reproducible from reviewed source definitions.
- Rollback of one successor must leave earlier `main` valid.
- No successor may widen the claim ceiling merely by moving text or tests from PR #73.

## S01 — repository truth and governance

**Include**

- root status entry points;
- integrated/candidate/non-claim separation;
- CODEOWNERS coverage;
- PR review template;
- evidence freshness policy;
- decomposition ledger.

**Exclude**

- runtime behavior;
- contract semantics;
- qualification promotion;
- repository-setting claims not proven by live readback.

**Gate**

- documentation links resolve;
- main facts are narrower than candidate facts;
- no stale exact-head success statement;
- administrative branch protection remains an explicit external blocker.

## S02 — contract foundation

**Include**

- `crates/trillionnium-contract-core`;
- `crates/hepta-browser-contracts`;
- corresponding schemas, golden vectors, tests, and module documentation.

**Exclude**

- wire parsing;
- OS access;
- browser runtime;
- capability authority.

**Gate**

- boundary/property tests;
- checked revision behavior or an explicit reviewed saturation policy;
- Rust/schema/golden-vector correspondence;
- public API snapshot.

## S03 — canonical browser codec

**Include**

- `crates/hepta-browser-codec`;
- canonical JSON parser;
- codec contracts and cross-language corpus.

**Exclude**

- peer authentication;
- authorization;
- browser dispatch;
- network policy.

**Gate**

- bounded allocation, depth, aggregate-item, integer, and string limits;
- duplicate-key rejection;
- byte-for-byte canonical re-encoding;
- fuzz smoke and golden digest conformance.

## S04 — authenticated local transport and AgentPort

**Include**

- `crates/hepta-agent-transport`;
- `crates/hepta-peer-attestation`;
- `crates/hepta-agent-port`;
- production/qualification binary separation in `apps/hepta-agent-portd`;
- directly related systemd custody files.

**Exclude**

- BrowserActor implementation;
- real Servo behavior;
- external-effect policy;
- installed-image promotion.

**Gate**

- fail-stop framing and connection poison;
- absolute monotonic deadlines;
- pidfd/start-time/cgroup/unit/path/digest hostile tests;
- request-scoped identity custody;
- final production dependency and binary inventory.

## S05 — receipt persistence and recovery

**Include**

- `crates/hepta-session-core` receipt format, writer, reader, chain, rotation, migration, recovery, and reconciliation;
- receipt contracts and corruption corpora.

**Exclude**

- BrowserActor queueing;
- real browser effects;
- product update system.

**Gate**

- explicit fsync and directory-sync semantics;
- partial-write, disk-full, missing-segment, duplicate, rotation, and lock-owner failure tests;
- indeterminate effects remain non-replayable;
- damaged state never silently becomes a fresh empty store.

## S06 — BrowserActor lifecycle

**Include**

- `crates/hepta-browser-actor`;
- request custody integration;
- session incarnation;
- engine/event-loop callback completion;
- deterministic runtime fixtures only as test dependencies.

**Exclude**

- production Servo adapter;
- external network or effect execution;
- installed-image claims.

**Gate**

- explicit actor/session/request state models;
- bounded queues and deadlines;
- exactly-one terminal callback;
- identity loss and engine retirement tests;
- old sessions, WebViews, frames, and node references cannot resurrect.

## S07 — Servo retained-node source behavior

**Include**

- exact pinned Servo commit manifest;
- file-bounded patch stages;
- retained accessibility-tree observation and click behavior tests;
- patch verifier and source qualification workflow.

**Exclude**

- production browser daemon integration;
- installed-image execution;
- hardware and release promotion.

**Gate**

- patch applies exactly to allowed paths;
- valid click plus stale/missing/ambiguous/disabled/hidden/unsupported cases;
- no coordinate, JavaScript, WebDriver, selector, text-search, or cross-frame fallback;
- behavior evidence booleans are false unless behavior execution succeeds;
- unrelated warnings in unmodified upstream files do not masquerade as patch regressions.

## S08 — headed runtime and browser daemon integration

**Include**

- real Servo adapter;
- browser daemon supervision;
- BrowserActor invocation;
- one trusted chrome surface and one untrusted content surface;
- local-fixture vertical slice.

**Exclude**

- unrestricted external navigation;
- update/recovery;
- hardware qualification;
- signing and release.

**Gate**

- AgentPort → BrowserActor → real Servo → receipt → response;
- engine-thread ownership;
- content crash and replacement generation;
- old references fail after crash;
- no fixture substituted for product runtime.

## S09 — Linux platform adapters

**Include**

- systemd process/service custody;
- Wayland window, focus, pointer, keyboard, and IME integration;
- filesystem, entropy, monotonic clock, and bounded network adapters.

**Exclude**

- distribution-general compatibility;
- hardware qualification;
- release signing.

**Gate**

- common contract tests per adapter;
- least-privilege units;
- no unexpected listener or ambient capability;
- trusted chrome cannot be replaced or overlapped by untrusted content.

## S10 — Debian image and QEMU integration

**Include**

- locked rootfs inputs;
- production install map;
- image builder;
- QEMU boot and crash/reboot/recovery corpus.

**Exclude**

- physical hardware conclusions;
- production release.

**Gate**

- reproducible input lock;
- PID 1 and required services start;
- production image contains no development marker, fixture binary, qualification-only unit, debug listener, or world-writable authority state;
- durable receipt recovery does not replay a click after service or system restart.

## S11 — update, rollback, and recovery

**Include**

- signed metadata model;
- A/B slot state machine;
- boot-success marking;
- rollback and recovery environment;
- failure and power-cut simulation.

**Exclude**

- claims of HSM custody or physical power-loss qualification without external evidence.

**Gate**

- download/write/first-boot interruption;
- automatic bounded rollback;
- metadata expiry and rollback-attack refusal;
- last known bootable system is preserved.

## S12 — reproducible build, hardware, signing, and release

**Include**

- two-builder reproducibility;
- SBOM and provenance;
- signed tags, images, and release metadata;
- fixed-BOM hardware corpus;
- release and emergency-revocation runbooks.

**Gate**

- identical release digest from independent builders;
- signer/attestor/promoter separation;
- protected environment and no-bypass readback;
- fixed hardware display, input, GPU, network, suspend/resume, endurance, repeated power-loss, update, and recovery evidence bound to the release image digest.

## Merge train

Successors merge in sequence unless a later item is proven independent by an explicit architecture review. Every merged successor causes later branches to rebase and rerun exact-head qualification. Historical PR #73 artifacts remain diagnostic input only.
