# D3 Servo retained-node action adapter

## Status and claim boundary

This document describes the isolated source candidate carried by `lab/d3-servo-retained-node-v3` for blocker D3-01. The patch targets Servo commit `670ae8a70801b162e186f81cbb5bdd2d59c39108` exactly. A green lab workflow proves only that the patch applies, passes the static policy guards, is formatted, and compiles through the `servoshell` dependency graph at that pin. It is not installed-runtime evidence and does not replace the independent exact-image packet required by the release plan.

## Problem

At the pinned Servo revision, AccessKit delivers `ActionRequested` events to servoshell, but non-root document-tree requests stop at `TODO(#4344)`. The missing path means an observed AccessKit `TreeId` and `NodeId` cannot be forwarded to the DOM node retained by Servo's accessibility tree. Falling back to screen coordinates, JavaScript evaluation, WebDriver, text search, or a second selector pass would break D3's same-node requirement.

## End-to-end route

1. `HeadedWindow` receives an AccessKit request. Root-tree actions remain owned by the embedder GUI. For a non-root tree it enumerates current webviews and accepts only an exact, unique match for the active grafted document `TreeId`.
2. `WebView::perform_accessibility_action` sends the original `ActionRequest` and a typed callback to the Constellation.
3. The Constellation rebinds the request to the webview's current active top-level `PipelineId`. It independently checks accessibility activation, exact `TreeId::from(PipelineId)`, click-only scope, and absence of action data.
4. Script receives the webview id, pipeline id, active-document epoch, original request, and callback. It repeats the tree/action checks, rejects stale or inactive documents, and runs an `UpdateTheRendering` reflow inside the current script task.
5. Layout resolves `NodeId` only through the current `AccessibilityTree::id_to_opaque_node` map and only when the tree id and embedder epoch still match.
6. Script converts that retained opaque identity back to the DOM node, verifies that it is connected, belongs to the same webview, is an element, is enabled, and still has a CSS layout box. It then fires one untrusted synthetic click event directly at that node.
7. The callback receives one terminal `AccessibilityActionResult`. `Dispatched` means only that the click dispatch returned; it does not assert an external side effect or receipt.

## Fail-closed outcomes

The API distinguishes inactive accessibility, stale webview, stale document, stale tree, stale node, unsupported action, non-element target, disabled target, and non-rendered target. Missing or ambiguous `TreeId` ownership is rejected in servoshell before dispatch. Navigation and tree-generation races are rejected again in Constellation/layout through the current pipeline and epoch.

## Security invariants

The action target is the retained node identity from the accessibility tree. No coordinate lookup, JavaScript evaluation, WebDriver command, selector retry, text search, or role/name reselection exists in the added path. Only `Action::Click` with no `ActionData` is accepted. The script-thread handler performs the final lookup and dispatch without allowing a page-script task to interleave between them.

## Qualification workflow

`.github/workflows/lab-d3-servo-retained-node-v3.yml` checks out both the carrier repository and the immutable Servo commit, reassembles the ordered, individually hashed unified-diff parts, verifies the aggregate patch digest and changed-path allowlist, runs `git apply --check`, applies the patch to a clean tree, enforces the forbidden-fallback policy over added lines, runs Servo formatting, bootstraps Linux dependencies using Servo's own bootstrap command, and executes a locked `cargo check -p servoshell`. It uploads a machine-readable evidence packet even on failure.

## Remaining integration work after source qualification

The Trillionnium browser adapter must translate its guarded `ElementReference` and action receipt lifecycle into this Servo API, bind product-side document/session revisions before dispatch, and exercise the path on the exact installed image. Independent replay must demonstrate success, stale-node rejection, navigation-race rejection, disabled-target rejection, unsupported-action rejection, and no fallback behavior. Those are separate gates and must not be inferred from source CI.
