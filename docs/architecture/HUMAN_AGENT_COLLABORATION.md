# Human and Agent collaboration over one PageOwner

## Status and boundary

This document specifies the deterministic D4 collaboration reference model.
The current package is a **source candidate blocked by D3**. It owns no browser,
window, input device, clipboard, drag-and-drop service, credential, network, or
external-effect authority.

A passing reference corpus proves only the state-machine rules below. It does
not prove integration with BrowserActor, Servo, native input, the system
clipboard, a compositor, hardware, or release artifacts.

## Single authority surface

Human and Agent operations must target the same `PageOwner`. A target reference
is authoritative only when all of these values match the current state:

- session identity;
- PageOwner identity;
- content-surface generation;
- document generation;
- semantic snapshot revision;
- target identity.

Navigation and content recovery invalidate old document references. A target
that resolves to zero matches is missing; one that resolves to more than one
match is ambiguous. Both cases fail closed. No operation may silently select a
replacement target.

Minimization changes visibility only. It never creates a hidden page, secondary
WebView, or alternate Agent target.

## Human lease and preemption

Human interaction may acquire a bounded monotonic lease. While the lease is
active, Agent turns and Agent-originated interaction are rejected. A human
input event preempts the current Agent epoch and invalidates any Agent work
that has not yet committed against that epoch.

Lease duration is bounded, lease release is epoch-bound, and expiration is
computed from an explicit monotonic timestamp supplied by the hosting runtime.
The reference model never reads wall-clock time.

## IME ownership

IME ownership is one of `none`, `human`, or `agent`. Ownership is bound to the
current target reference and is atomic with the target. Navigation, content
crash/recovery, modal teardown, and human preemption of Agent input clear stale
IME ownership.

The source model proves ownership semantics only. It does not claim native IME
or DOM composition integration.

## Mediated clipboard

The reference clipboard stores only bounded metadata: version, SHA-256, byte
length, and writer identity. Writes use compare-and-swap against the expected
version. Reads must name the expected version. A mismatch is rejected.

The source model intentionally does not expose the clipboard plaintext in a
receipt and does not access the operating-system clipboard.

## Drag and drop

At most one drag exists. The drag is bound to its actor and a current source
reference; the drop is bound to a current destination reference. Another actor
cannot complete the drag. Navigation and content recovery cancel the drag.

This proves no desktop or browser drag-and-drop integration.

## Modal scope

Only the topmost modal target is actionable. Background target operations are
rejected while a modal is active. Navigation and content recovery clear the
entire modal stack. Closing anything other than the topmost modal fails closed.

## Receipts and trace replay

Every admitted or rejected operation creates a receipt containing:

- sequence number;
- previous-receipt hash;
- explicit monotonic time input;
- canonical operation;
- decision and reason;
- state hash before and after;
- canonical receipt hash.

The journal records facts only. It does not execute or replay external effects.
A trace replay must reproduce the same final state and byte-identical receipts.
Any receipt mutation breaks the hash chain.

## Required runtime integration after D3

After D3 is independently reviewed, merged, and qualified on exact `main`, a
later D4 integration package must bind this model to:

- the one live BrowserSession/PageOwner;
- generation-bound BrowserActor requests;
- native human input and explicit preemption signals;
- bounded IME ownership transfer;
- a mediated system clipboard portal;
- compositor and browser drag-and-drop portals;
- modal and navigation lifecycle callbacks;
- durable D0C-06 receipts around each admitted operation.

That package must include property tests, trace replay, local-fixture runtime
tests, crash/navigation/minimize/show tests, and exact-main evidence. No lower
source test can substitute for that integration gate.
