# TrillionniumOS Desktop d5 contracts, security, and testing

**Plan revision:** `2026-08-28-d5`
**Status:** `SUPERSEDED_HISTORICAL` — d5 provenance only; not an active normative component
**Active successor:** [`../DESKTOP_PLAN-2026-08-29-d6.md`](../DESKTOP_PLAN-2026-08-29-d6.md)
**Repository mode:** `FULL_PRODUCT_REPOSITORY`

This historical annex is retained for provenance and was versioned with
[`../DESKTOP_PLAN-2026-08-28-d5.md`](../DESKTOP_PLAN-2026-08-28-d5.md). The
active normative plan is d6; this annex does not override its executive lock,
machine truth, or claim ceilings.

## 4. Contract and transport architecture

### 4.1 Browser API

The machine-readable source is `contracts/browser-api.v1.schema.json`. The API
is engine-neutral and contains:

```text
health
session_create
session_snapshot
session_close
page_navigate
page_observe
page_act
page_wait
page_extract
```

Search-provider templates are shell configuration, not browser protocol. A
search operation is represented by validated navigation to an explicit URL.

Every request contains a bounded request ID, optional session ID, absolute
deadline, and exactly one typed operation. Unknown fields and unknown operation
variants are rejected. Raw JavaScript evaluation is not in v1.

### 4.2 Production AgentPort

The D3 production transport is a local Unix-domain socket with:

- parent directory and socket ownership fixed by systemd;
- `SO_PEERCRED` UID/GID/PID verification;
- expected systemd unit/cgroup identity where available;
- per-session random nonce and short authentication lifetime;
- maximum frame size and maximum nesting limits;
- duplicate JSON member rejection;
- strict schema/version negotiation;
- absolute monotonic deadline propagation;
- explicit cancellation;
- bounded concurrent requests and queue capacity;
- response binding to protocol, request ID, session, and generation;
- no TCP listener and no public WebDriver endpoint.

The current D0 scaffold starts no listener. Transport implementation is not
complete until adversarial framing and peer-identity tests pass.

### 4.3 Error taxonomy

`contracts/error-codes.v1.json` is normative. In particular:

- stale session/document/snapshot failures are distinct;
- queue overflow fails closed;
- human focus and IME are typed states;
- unsupported Servo behavior is not converted into a fallback engine;
- an unknown result after dispatch is `indeterminate` and is never retried
  automatically.

### 4.4 Receipts

Every admitted operation eventually produces a receipt conforming to
`contracts/receipt.v1.schema.json`. A receipt records plan/image/Servo/browserd
identity, layered revisions, source, normalized operation, monotonic timing,
status, error/challenge class, redirect evidence, and optional chained digest.
In the D3 source-only development profile, the journal observer supplies a
persisted logical monotonic sequence for the `*_monotonic_ms` fields. It proves
strict lifecycle ordering across reopen/rotation, not physical elapsed time;
an attested runtime clock is required before making that stronger claim.
The durable journal may hold several append-only lifecycle facts for one
operation (`requested`, `dispatched`, then a terminal fact); its canonical
`export_redacted_jsonl` projection aggregates those facts into one envelope
and fails closed while the lifecycle is unresolved. Journal-only forensic
JSONL is exposed separately and is not a receipt.v1 envelope.

D0 schemas do not yet prove cryptographic journal durability. Before D7, the
implementation must define canonical serialization, hash and signing algorithm,
key custody, sequence/chain rules, crash truncation detection, redaction,
retention, export, and privacy policy.

## 5. Page identity and semantic references

### 5.1 Revision layers

The browser session owns four monotonically increasing values:

| Field | Advances when | Invalidates |
| --- | --- | --- |
| `session_generation` | browser process/session recovery or recreation | every prior reference and lease |
| `document_generation` | committed top-level navigation/document replacement | every reference to the prior document |
| `semantic_snapshot_revision` | a new semantic/accessibility snapshot is published | references from the prior snapshot unless revalidated |
| `mutation_epoch` | committed DOM/event-loop mutation batch | diagnostics and revalidation hints only |

A timer, animation, unrelated DOM mutation, or framework render does not
invalidate every semantic reference merely by advancing `mutation_epoch`.

### 5.2 Element reference

A semantic reference contains session, document, snapshot, frame, structural
fingerprint, and optionally backend-node, role, and accessible-name evidence.
Before dispatch, PageOwner:

1. checks session and document generation;
2. re-resolves the target in the current frame;
3. compares semantic role/name/visibility/structure;
4. rejects ambiguity or material semantic change;
5. records the final resolved target in the receipt.

Potential external-effect actions are never automatically replayed after a
stale reference, navigation, disconnect, or crash.

## 6. Agent/human arbitration

The normative state model is implemented in `hepta-session-core` and described
in `docs/architecture/SESSION_STATE_MACHINE.md`.

Orthogonal control states:

```text
Idle
AgentObserving
AgentMutating
AgentNavigating
HumanActive
HumanImeComposing
```

Session phases:

```text
Ready
NavigationPending
ModalBlocked
CapabilityPending
Cancelling
Recovering
Closed
```

The initial safe policy serializes Agent operations against an active human
lease. Later optimization may allow read-only observation during human input
only after snapshot consistency and privacy tests demonstrate safety.

Human focus uses a bounded monotonic lease. Human focus may interrupt Agent work
and invalidates any assumption that a mutation completed uninterrupted. IME
composition explicitly owns text input. Modal, navigation, capability, cancel,
and recovery states block incompatible mutations with typed failures. A
`CancelRequested` transition is also a hard ownership boundary: it revokes any
human lease immediately, refuses new human focus/input/IME events until
`CancelCompleted`, and leaves no old lease usable after completion.

The queue is bounded FIFO. Overflow returns `queue_full`; it does not allocate
without limit, drop an older request, or silently execute outside ordering.

## 7. External effects and network architecture

### 7.1 Effect classification

The product does not equate UI verbs with effect safety:

- observe and snapshot are observational;
- scroll is normally local-only;
- click, type, press, select, navigation, downloads, and permission decisions
  may produce external effects.

P0/D0 local fixtures may exercise all actions. External origins remain
observe-only until the egress and effect barriers below are complete.

### 7.2 Browser egress

Before external interaction is enabled, browser traffic must flow through a
controlled network namespace and policy egress service. Policy evaluates:

- original URL and scheme;
- every DNS answer and rebinding change;
- actual connected peer IP;
- IPv4, IPv6, and link-local/private/metadata ranges;
- every redirect;
- HTTP, HTTPS, WebSocket, WebTransport/QUIC where supported;
- service workers, workers, iframes, prefetch, and subresources;
- proxy bypass and captive-portal behavior;
- downloads, external schemes, and certificate errors.

The browser process receives no ambient raw socket authority in the
production-shaped configuration. Trusted synthetic app origins are resolved
locally and never reach public DNS.

### 7.3 Stage effect gates

| Stage | External behavior |
| --- | --- |
| D0–D4 | deterministic local fixtures; no external Agent mutation |
| D2 | optional manually driven read-only external rendering corpus |
| D5 | trusted signed local apps only |
| D6 | allowlisted external observation through egress policy |
| D7+ | separately approved prepare/execute effects with reconciliation |

CAPTCHA solving, anti-bot evasion, stealth fingerprinting, and automatic
challenge bypass are never product features.

## 11. Test and evidence policy

### 11.1 Required test classes

- unit and property tests for contracts/state machine;
- malformed wire and fuzz corpus;
- deterministic local HTML fixtures;
- frame, shadow DOM, SPA, async render, forms, storage, history, modal, and IME;
- Agent/human event-trace replay;
- process kill, GPU reset, network loss, disk full, timeout, cancel, and power
  loss;
- origin, CSP, service-worker, storage-isolation, and app-signature tests;
- egress SSRF/rebinding/redirect/IPv6 tests;
- update rollback and recovery-media tests;
- fixed external read-only corpus after D6.

### 11.2 Evidence hierarchy

```text
source exists
  < host unit test
  < integration fixture
  < QEMU boot evidence
  < fixed-hardware evidence
  < signed release evidence
```

A lower level never implies a higher level. `CURRENT_STATE.md` and the
repository-state manifest must identify the highest demonstrated level.

### 11.3 Performance gates

D8 qualification must set hardware-specific numeric gates for boot-to-first
trusted frame, input latency, observe/act latency, RSS/FD/PID ceilings, crash
recovery, suspend/resume, and 24/72-hour stability. Values are not invented in
D0; they become normative only after hardware and measurement methodology are
selected.
