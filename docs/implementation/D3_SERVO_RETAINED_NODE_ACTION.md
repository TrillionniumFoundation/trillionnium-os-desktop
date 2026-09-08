# S07 exact-pin Servo retained-node action boundary

## Status and claim ceiling

This document describes the bounded S07 source/test-harness candidate on
`codex/s07-servo-retained-node-v1`, based on exact S06 commit
`ea05a5eaf520365aa0086d7795d66a1d5c5537dd`. Its patch bytes were extracted
from frozen PR #73 head `62004b70385dc70557190bd7c0a72b40239cb078`
without importing that convergence branch's browser daemon, platform, image,
update, hardware, signing, or release surfaces.

The patch targets Servo commit
`670ae8a70801b162e186f81cbb5bdd2d59c39108` exactly. A green exact-head job
proves only immutable patch reconstruction, clean application, patch-owned
formatting, and the bounded retained-node corpus in Servo's real accessibility
test harness. The separately named prospective-merge job proves only that the
synthetic merge contains the same valid package and applies cleanly. Neither is
installed-product, fixed-hardware, HSM, publication, or release evidence.

## Problem and forbidden substitutes

At the pinned Servo revision, servoshell receives AccessKit action requests,
but the non-root document-tree branch stops at `TODO(#4344)`. The missing path
means the exact retained `TreeId + NodeId` observed from Servo cannot be routed
back to the current DOM node. Screen coordinates, DOM order, accessible-name
search, CSS selectors, page JavaScript, WebDriver, text search, or a later
second resolve-and-act phase would violate the same-node security property and
are forbidden.

## Reviewed route

1. Native `HeadedWindow` keeps root-tree controls in trusted chrome and routes a
   non-root request only when exactly one current WebView owns the tree.
2. `WebView::perform_accessibility_action` forwards the original AccessKit
   request and a typed callback through Constellation.
3. Constellation rebinds the request to the WebView's active top-level pipeline,
   rejects stale/ambiguous ownership, accepts only Click with no action data,
   and verifies the exact tree identity.
4. Script refreshes rendering and retained accessibility state inside one
   script-thread task, preventing page-script interleaving between final lookup
   and dispatch.
5. Layout resolves the `NodeId` only through the current retained
   `AccessibilityTree`, returning the retained DOM identity and whether that
   exact AccessKit node advertised the action.
6. Script rechecks current document ownership, connectedness, element type,
   enabled state, finalized bounds, and Click advertisement before dispatching
   one untrusted synthetic click.
7. A single typed callback reports a terminal result. `Dispatched` means DOM
   event dispatch returned; it is not an external-effect or durable-receipt
   claim.

## Initial action surface

Only native HTML buttons expose the reviewed initial `Action::Click` surface.
Links, inputs, custom ARIA widgets, non-elements, hidden or disabled elements,
nodes without finalized layout bounds, unsupported actions, and requests with
action data fail closed. No fallback widens this surface.

## Failure semantics

The boundary distinguishes inactive accessibility, stale WebView, stale
pipeline/document/tree/node, ambiguous ownership, unsupported action/data,
unadvertised action, non-element target, disabled target, target without
finalized bounds, dropped callback receiver, and browser/test harness failure.
A dropped receiver cannot trigger a second dispatch. The evidence writer sets
behavior-derived booleans only when the behavior step succeeds; a failed or
unexecuted test never becomes a positive fact.

## Immutable package

`manifests/lab-d3-servo-retained-node-action.v1.json` binds every ordered patch
part, part digest, aggregate digest, upstream Servo identity, allowed changed
path, source invariant, workflow, and claim ceiling. The fail-closed verifier:

- rejects duplicate or escaping part paths;
- verifies every part and aggregate digest;
- requires exact changed-path equality;
- requires the retained-node routing and action-advertisement tokens;
- rejects coordinate, JavaScript, WebDriver, selector, and text-search additions;
- requires replacement of the pinned servoshell TODO.

## Evidence identities

`.github/workflows/s07-servo-retained-node.yml` deliberately separates two
evidence classes:

- `exact-head-real-servo-behavior` explicitly checks out and asserts the PR head
  SHA before applying the patch and running Servo tests;
- `prospective-merge-patch-package` explicitly checks out
  `refs/pull/<number>/merge`, asserts its two parents in base/head order, and
  reruns package verification plus clean Servo dry-run application.

The exact-head corpus runs one Servo instance per Cargo process to avoid
process-global option reuse and proves exactly one executed test and one passing
terminal result for each requested test identity.

## Behavior matrix

The test harness covers a valid retained button click, exactly-once callback and
dispatch, unadvertised Click, unsupported action and data, replaced node,
stale/inactive tree, disabled/hidden/non-element targets, missing finalized
bounds, dropped callback receiver, and the pinned accessibility role-mapping
regression.

## Remaining integration

S08 must translate product-side session, WebView, document, PageOwner, semantic
revision, principal, custody, deadline, cancellation, and durable receipt facts
into this Servo entry point. It must then prove the complete AgentPort →
BrowserActor → real Servo → receipt → response path without importing a fixture
or replaying an indeterminate effect. S10 must repeat that path in an exact
installed image. Those claims are intentionally absent from S07.
