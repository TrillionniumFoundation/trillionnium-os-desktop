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
6. obtains bounded current metadata through the read-only `WebView::observe_accessibility_semantics` script/layout callback and returns its real identity, role and SHA-256 values through the BrowserActor `ElementReference`;
7. calls `WebView::perform_checked_accessibility_action` with that retained typed expectation;
8. proves the callback completes exactly once and the DOM exposes `Click count 1`;
9. performs a second real navigation so the first target becomes stale at the BrowserActor document-generation boundary;
10. closes without enabling external navigation or persistent credentials.

The exact Servo source, AccessKit version, patch parts, patch digest, changed-path allowlist, product source head, product tree, workflow digest, mailbox results, and receipt evidence are recorded by the permanent workflow.

## Retained semantic expectation v1

The separately declared `manifests/lab-s08-semantic-custody.v1.json` patch follows all unchanged S07 parts. It adds the checked action and read-only observation routes through WebView, constellation and the current script thread. Observation calls reflow and measures the current layout's retained AccessKit node and complete document ancestry. The current constellation supplies the epoch; a buffered consumer `TreeUpdate` supplies no epoch proof. At this pin, the epoch advances when the active top-level pipeline changes, while ordinary retained-tree updates and read-only reflow keep it unchanged. Observation and a later checked action on that same pipeline therefore compare the actual retained snapshot without attaching a newer consumer epoch. The checked action preserves the original document/tree/node/action/DOM-element/disabled/rendered checks, then compares a newly measured typed expectation after reflow and immediately before click in the same script task. No task yield or page-script evaluation lies between the final metadata comparison and dispatch.

The closed expectation contains version `u16`, AccessKit `TreeId`, retained `NodeId`, epoch `u32`, AccessKit `Role`, name-presence `bool`, name-byte-length `u16`, ancestry-depth `u8`, state `u8`, and two `[u8; 32]` SHA-256 values. Private fields prevent mutation through public Rust getters; strict Serde rejects unknown members and incorrect primitive/array shapes. Version, length, depth and state-mask validity are rechecked before a checked action. This is an equality expectation, not signing, principal, capability or request authority.

The encoder uses already pinned `sha2 0.11.0`; only the `servo-base` Cargo dependency edge and matching lock edge are added. Its registry source/checksum is unchanged. Names use the exact reported AccessKit UTF-8 bytes, with no Unicode normalization, case folding, truncation or text lookup. An absent label differs from an empty label. Each name is at most 1,024 bytes; a complete leaf-to-document-root chain includes at most 16 nodes. Overflow, a repeated node, unavailable parent, missing retained root or a foreign tree/epoch refuses the snapshot.

All integers in the hash preimages are big-endian. The name preimage is `trillionnium.accesskit.name` followed by one NUL byte, version `u16`, name-presence byte, UTF-8 length `u16`, and those exact bytes (maximum 1,057 bytes). The structural preimage is `trillionnium.accesskit.semantic` followed by one NUL byte, version `u16`, UUID's 16 TreeId bytes, epoch `u32`, and each leaf-to-root node's NodeId `u64`, pinned Role discriminant `u8`, state `u8`, name-presence byte, UTF-8 length `u16`, and exact name bytes; the final byte is depth (maximum 16,647 bytes). Graft nodes are excluded. State bits 0 through 5 encode AccessKit hidden, disabled, read-only, busy, advertised Click and bounds-presence; all other bits are invalid. The original final DOM disabled/layout checks continue to apply even where pinned AccessKit does not report that DOM state.

The Actor frame identity is the real document TreeId UUID, and the backend key is `accesskit-node-` plus the actual NodeId as sixteen lowercase hex digits. The role is derived from the retained node, and name/structural fingerprints come from the current script/layout observation. Fixture `a`/`b` digests and fixed `main-frame`/button keys are removed. This does not replace the Actor's session/document/snapshot revisions or its approved peer/capability checks.

The additional real exact-pin corpus requires same-node label, role and ancestry changes, node replacement, disabled and hidden targets, and an earlier-epoch expectation to refuse with zero actual DOM clicks. It keeps the original S07 tests and the original S08 10 requests / 9 commands / 30 receipt facts / 1 positive click. `s08-semantic-result.json` is closed: wrong refusal, missing case, bool/float count aliases, extra fields or promoted claim ceilings fail verification. Complete source fixtures exercise this parser only; they do not constitute Servo evidence.

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
  -> completion.ensure_current_peer() before the qualification mailbox command
  -> real Servo operation
     -> current retained semantic observation / same-script-task final metadata check
  -> single-use completion
  -> BrowserActor state transition
  -> completed receipt
  -> response commit
```

A deadline, cancellation, peer revocation, retired callback, mailbox ambiguity, missing Servo response, duplicate field, oversized record, stale reference, unsupported operation, or Servo failure is fail-closed. A possible effect that loses a terminal result must remain interrupted or indeterminate and is never automatically replayed.

The mailbox uses one command file and one response file per monotonically increasing qualification sequence. Records are bounded, duplicate keys are rejected, values cannot contain control characters or the record separator, and publication uses a same-directory atomic rename. These controls make the test deterministic; they do not make the mailbox a production security boundary.

The new final script check binds current semantic metadata. It does not import the Agent/control pidfds or recheck request cancellation/deadline inside the remote test process's final script task. This package therefore does not establish final script peer/control custody, an installed native PageOwner, or a product mailbox IPC path.

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
python3 -m unittest tests.test_s08_semantic_custody -v
python3 tools/verify_s08_semantic_custody.py --source-check
cargo test --locked -p hepta-browser-actor --test s08_servo_mailbox
```

The ordinary Rust test returns without a claim when `HEPTA_S08_MAILBOX` is absent. A meaningful pass therefore requires the permanent workflow to start the exact-pin Servo test process, wait for `servo-ready`, run the product test with the same private mailbox, require both result documents, and verify their claim ceilings.

The semantic standalone source check requires explicit Rust 1.93.0. It compiles the actual extracted bounded encoder against the pin's locked dependency closure; it does not compile Servo. The workflow separately applies the complete patch against a pristine exact pin, compiles with Servo's required Rust 1.97.1, runs all original retained tests, runs the new seven-case real corpus, and verifies its result. Those new full-Servo execution facts remain pending until the corresponding immutable-source CI run succeeds.

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
