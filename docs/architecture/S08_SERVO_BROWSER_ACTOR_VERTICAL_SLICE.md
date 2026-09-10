# S08 exact-pin Servo and BrowserActor host vertical slice

**Work package:** `S08`  
**Status:** source candidate; exact-head host qualification and independent review required  
**Servo input:** `670ae8a70801b162e186f81cbb5bdd2d59c39108`  
**Claim ceiling:** exact-pin host integration only; no installed image, physical hardware, external-effect authority, signing, publication, or release claim

## Purpose

S08 closes the gap between the sealed product-facing `BrowserActor` and a real Servo-owned `WebView` without reintroducing generic runtime injection. The product actor remains responsible for semantic principal binding, PageOwner/session identity, request custody, cancellation, deadline handling, stale-reference checks, and receipt ordering. Servo remains responsible for its event loop, WebView state, current accessibility tree, retained node identity, and the final accessibility action.

The acceptance path is:

```text
canonical Browser API bytes
  -> authenticated already-connected AF_UNIX AgentPort
  -> refreshed pidfd-backed peer custody
  -> sealed ServoBrowserActor
  -> one typed command on the native event-loop bridge
  -> exact-pin Servo WebView and retained AccessKit node
  -> single-use completion
  -> BrowserActor state transition
  -> durable completed receipt
  -> request-bound AgentPort response
```

This path is deliberately narrower than an installed desktop. It uses a loopback-only deterministic fixture and a test-only atomic mailbox between two separately compiled test processes. The mailbox proves cross-process command and completion behavior but is not a product IPC, listener, profile, or deployment mechanism.

## Concrete runtime boundary

`crates/hepta-browser-actor/src/servo_runtime.rs` defines the only product-facing S08 runtime type:

- `ServoBrowserActor` is non-generic and accepts only `ServoRuntimeEndpoint`;
- `servo_runtime_pair` creates the endpoint with a creator-thread `ServoRuntimeOwner`;
- the owner is `!Send` and `!Sync` through its `Rc`-bound callback owner;
- at most one command can be pending;
- each command contains one single-use completion token;
- the completion checks cancellation, deadline, and request-scoped peer custody;
- semantic action dispatch requires a final custody check immediately before the Servo operation;
- retirement drops pending work and never replays it.

The bridge does not import Servo, create a file, open a network socket, or decide policy. A native embedder consumes `ServoRuntimeOperation` and returns a bounded `JsonObject` or typed `ServoRuntimeError`.

## Exact-pin Servo qualification adapter

`experiments/servo-s08-runtime/accessibility_server.rs` is appended to Servo's existing accessibility integration test only after the reviewed S07 retained-node patch is verified and applied. The adapter:

1. creates a real Servo test instance and real `WebView`;
2. accepts only a loopback fixture URL supplied by the product test;
3. waits for a complete load and rebuilds the consumer accessibility tree;
4. finds one `Role::Button` with accessible label `Action target`;
5. retains the real `TreeId + NodeId` in an `ActionRequest`;
6. verifies the target metadata returned through the BrowserActor flow;
7. calls `WebView::perform_accessibility_action` through the reviewed helper;
8. proves the callback completes exactly once and the DOM exposes `Click count 1`;
9. performs a second real navigation so the first target becomes stale at the BrowserActor document-generation boundary;
10. closes without enabling external navigation or persistent credentials.

The exact Servo source, AccessKit version, patch parts, patch digest, changed-path allowlist, product source head, product tree, workflow digest, mailbox results, and receipt evidence are recorded by the permanent workflow.

## Product-side qualification process

`crates/hepta-browser-actor/tests/s08_servo_mailbox.rs` is inert unless `HEPTA_S08_MAILBOX` names an absolute private directory. Under the permanent workflow it:

- creates ten real `UnixStream` pairs and uses the production AgentPort framing and canonical codec;
- derives the mechanism peer from kernel `SO_PEERCRED`;
- creates bounded synthetic procfs facts only for systemd-unit/executable fixture identity while retaining a real pidfd for the live test process;
- constructs `ServoBrowserActor::from_attested` and calls only `handle_attested`;
- creates a private managed receipt store;
- sends health, create, two navigations, observe, wait, click, snapshot, stale click, and close requests;
- receives nine runtime commands because the stale click is rejected before runtime dispatch;
- verifies the real Servo click count is exactly one;
- verifies the second navigation advances the document generation and the old target returns `stale_document`;
- verifies all ten AgentPort operations contain requested, dispatched, and completed records with no unresolved receipt;
- emits no raw PID, UID, GID, session identifier, page text, credential, or private data in the evidence result.

The synthetic procfs directory is explicitly qualification-only. It does not prove a real systemd service, installed unit, fixed UID allocation, or production executable custody; those remain S09/S10 gates.

## State, ordering, and failure semantics

One BrowserActor request may own one callback operation. The ordering contract is:

```text
AgentPort requested receipt
  -> AgentPort dispatched receipt
  -> BrowserActor peer refresh and PageOwner preflight
  -> ServoRuntimeCommand publication
  -> final completion.ensure_current_peer()
  -> real Servo operation
  -> single-use completion
  -> BrowserActor state transition
  -> completed receipt
  -> response commit
```

A deadline, cancellation, peer revocation, retired callback, mailbox ambiguity, missing Servo response, duplicate field, oversized record, stale reference, unsupported operation, or Servo failure is fail-closed. A possible effect that loses a terminal result must remain interrupted or indeterminate and is never automatically replayed.

The mailbox uses one command file and one response file per monotonically increasing qualification sequence. Records are bounded, duplicate keys are rejected, values cannot contain control characters or the record separator, and publication uses a same-directory atomic rename. These controls make the test deterministic; they do not make the mailbox a production security boundary.

## Security invariants

- No generic `PageRuntime` implementation can be injected into `ServoBrowserActor`.
- The native Servo owner never crosses to the actor thread.
- The actor never receives a Servo object, DOM pointer, AccessKit consumer node, or raw file descriptor.
- The Servo adapter cannot author request, session, transport, receipt, or principal identity.
- Every semantic click is bound to one current accessibility tree and one retained action request.
- Navigation and click remain `potential_external_effect`; the qualification fixture is loopback-only and no external-effect capability exists.
- A stale document reference is rejected before a second Servo action command is produced.
- Receipt observation records facts but never grants execution or replay authority.
- Test-only mailbox and procfs fixtures are absent from product binaries and Debian install maps.

## Verification and evidence

The permanent workflow performs two separate evidence classes:

1. **exact source head:** full Python validation, Rust 1.93 format/check/Clippy/tests, exact Servo checkout and patch verification, exact-pin real Servo plus product integration execution, result validation, digest inventory, and artifact upload;
2. **live prospective merge:** exact parent-order validation, module/repository/source checks, patch dry-run, and S08 hostile tests. It does not inherit the exact-head runtime result automatically.

A later source push, base movement, workflow change, Servo/AccessKit input change, patch change, contract change, or evidence-claim change invalidates the affected result. After a protected merge, the exact integrated object must rerun before S08 is recorded as integrated.

## Operations and troubleshooting

Run the source controls locally with:

```bash
python3 tools/validate_s08_servo_runtime.py
python3 -m unittest discover -s tests -p 'test_s08_servo_runtime.py' -v
cargo test --locked -p hepta-browser-actor --test s08_servo_mailbox
```

The ordinary Rust test returns without a claim when `HEPTA_S08_MAILBOX` is absent. A meaningful pass therefore requires the permanent workflow to start the exact-pin Servo test process, wait for `servo-ready`, run the product test with the same private mailbox, require both result documents, and verify their claim ceilings.

When diagnosis is needed, preserve the exact source and Servo identities, both process logs, the bounded mailbox result files, the receipt-chain summary, and all SHA-256 values. Do not fix a failure by weakening custody, accepting a stale target, skipping the real Servo process, substituting the deterministic simulation runtime, deleting hostile tests, or broadening external navigation.

## Remaining gates

S08 does not close:

- real systemd and Wayland platform adapters;
- installed Debian/QEMU PID 1 execution;
- production AgentPort enablement;
- uncontrolled external navigation, credentials, downloads, portals, or effects;
- content-process crash and reconstruction in the exact installed product image;
- signed update and recovery;
- fixed-hardware endurance and raw-power-loss qualification;
- independent builders, offline/HSM key custody, protected publication, or production release.

Those facts belong to S09 through S12 and may not be inferred from this host qualification.
