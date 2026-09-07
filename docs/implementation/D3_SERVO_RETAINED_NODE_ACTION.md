# D3 Servo retained-node action adapter

## Status and claim boundary

This document describes the source-qualified candidate carried by
`codex/d3-servo-retained-node-action-v4` for blocker D3-01. The patch targets
Servo commit `670ae8a70801b162e186f81cbb5bdd2d59c39108` exactly.

The governed source job proves apply, static-policy, formatting and locked
compile compatibility. The separate `d3-retained-node-behavior` workflow runs
the retained-node corpus in Servo's real `components/servo/tests/accessibility.rs`
test harness. Neither result is installed-runtime evidence, product receipt
evidence, independent image replay, hardware qualification or release evidence.

## Problem

At the pinned Servo revision, AccessKit delivers `ActionRequested` events to
servoshell, but non-root document-tree requests stop at `TODO(#4344)`. The
missing path means an observed AccessKit `TreeId` and `NodeId` cannot be
forwarded to the DOM node retained by Servo's accessibility tree. Falling back
to screen coordinates, JavaScript evaluation, WebDriver, text search, or a
second selector pass would break D3's same-node requirement.

The initial source candidate also accepted `Action::Click` without proving that
the exact retained AccessKit node advertised Click. That allowed a caller to
attempt semantic click dispatch against a generic rendered element. The
hardening patch closes this confused-capability boundary.

## End-to-end route

1. `HeadedWindow` receives an AccessKit request. Root-tree actions remain owned
   by the embedder GUI. For a non-root tree it enumerates current webviews and
   accepts only an exact, unique match for the active grafted document `TreeId`.
2. `WebView::perform_accessibility_action` sends the original `ActionRequest`
   and a typed callback to the Constellation.
3. The Constellation rebinds the request to the webview's current active
   top-level `PipelineId`. It independently checks accessibility activation,
   exact `TreeId::from(PipelineId)`, click-only scope, and absence of action
   data.
4. Script receives the webview id, pipeline id, active-document epoch, original
   request, and callback. It repeats the tree/action checks, rejects stale or
   inactive documents, and runs an `UpdateTheRendering` reflow inside the
   current script task.
5. Layout resolves `NodeId` only through the exact current retained
   `AccessibilityTree` node and the current embedder epoch. The resolution
   returns both its retained DOM identity and whether that exact AccessKit node
   advertised the requested action.
6. Script converts the retained opaque identity back to the DOM node, verifies
   that it is connected, belongs to the same webview, is an element, is
   enabled, still has a CSS layout box, and advertised Click. Only then does it
   fire one untrusted synthetic click.
7. The callback receives one terminal `AccessibilityActionResult`.
   `Dispatched` means only that DOM event dispatch returned; it does not assert
   an external effect or a product receipt.

## Initial advertised action surface

The pinned Servo accessibility tree did not advertise actions for native
controls. This candidate adds the minimum reviewed surface required for the
behavior proof:

- native HTML `button` maps to AccessKit `Role::Button`;
- its accessible name is derived from its content;
- the retained AccessKit node advertises only `Action::Click`;
- all non-button nodes remain unadvertised for Click;
- disabled and non-rendered state is rechecked on the live retained DOM element
  immediately before dispatch.

Links, inputs, custom ARIA widgets and other AccessKit actions remain outside
this initial patch and fail closed.

## Fail-closed outcomes

The API distinguishes inactive accessibility, stale webview, stale document,
stale tree, stale node, unsupported action or action data, an action not
advertised by the retained node, a non-element target, a disabled target, and a
non-rendered target. Missing or ambiguous `TreeId` ownership is rejected in
servoshell before dispatch. Navigation and tree-generation races are rejected
again in Constellation, script and layout.

## Security invariants

The action target is the retained node identity from the accessibility tree.
No coordinate lookup, JavaScript evaluation, WebDriver command, selector
retry, text search, or role/name reselection exists in the dispatch path. Only
`Action::Click` with no `ActionData` is accepted. The exact retained node must
advertise Click. The script-thread handler performs final refresh, lookup,
capability recheck and dispatch without allowing a page-script task to
interleave between them.

## Governed source qualification

`.github/workflows/d3-integrated-runtime-evidence.yml`, job
`servo-retained-node-source`, checks out the carrier repository and immutable
Servo commit, validates the pinned AccessKit ABI, reassembles the ordered and
individually hashed base and hardening patch parts, verifies their digests and
exact changed-path allowlist, runs a clean dry-run, applies the patch, enforces
the forbidden-fallback policy, normalizes only patch-owned Rust files, rejects
every post-format path outside the allowlist, requires the core semantic files
to remain changed, and executes a locked `cargo check -p servoshell`.

## Real Servo behavior qualification

`.github/workflows/d3-retained-node-behavior.yml` applies the same immutable
combined patch and runs the filtered integration tests in Servo itself. The
corpus covers:

- a valid retained native-button click;
- one request producing exactly one terminal callback and one DOM dispatch;
- rejection of a rendered node that does not advertise Click;
- unsupported action and unexpected `ActionData`;
- removed/replaced node identity;
- accessibility deactivation and navigation/tree change;
- disabled, hidden and non-element targets;
- a dropped callback receiver without duplicate dispatch;
- regression coverage for the pinned accessibility role mapping.

The workflow emits a bounded digest manifest and keeps
`installed_runtime_proven`, product receipt integration, independent replay,
hardware, protected-environment approval and HSM signing explicitly false.

## Remaining integration work

The Trillionnium browser adapter must translate its guarded
`ElementReference` and action receipt lifecycle into this Servo API, bind
product-side session/document revisions before dispatch, install the exact
patched Servo artifact into the exact D2I image, and exercise the path through
the installed AgentPort → principal → BrowserActor → receipt journal chain.

That installed corpus must bind the image digest, process identities, request,
dispatch and terminal receipt facts, and repeat the stale/recovery cases. It is
a separate gate and must not be inferred from source or Servo test-harness CI.
